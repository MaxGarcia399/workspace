"""Trae a Workspace el estado de la instalación anterior (antes de cambiar de nombre).

Quien venía de la versión con el nombre anterior tiene sus agentes registrados,
ajustes y definiciones en las carpetas viejas. Sin esto, al actualizarse vería
el hub vacío hasta correr `workspace migrar-legado --apply` a mano.

Solo hace la parte SEGURA y aditiva de `migrate_legacy.apply()`:
  · estado per-máquina: copia lo que falte (jamás pisa un archivo existente);
  · definición del agente en cada cerebro: crea `.workspace/agent.json` y deja
    la vieja intacta;
  · registro: reapunta cerebros que vivían dentro del estado viejo.
Todo con respaldo (`migrate_legacy` lo deja en <estado>/backups/…). No toca
lanzadores, perfiles de terminal ni settings, y NO retira nada: eso sigue
siendo `workspace migrar-legado` (plan → --apply → --retire), a la vista.
"""

TITLE = {"es": "Traer agentes y ajustes de la instalación anterior",
         "en": "Bring agents and settings over from the previous install"}
KIND = "auto"

_SAFE_KINDS = ("estado", "definición", "registro")
# Respaldos (transcripts, backups) pueden pesar GB y no hacen falta para
# trabajar: se quedan donde están y `migrar-legado` los ofrece a la vista.
_HEAVY = ("transcripts-backup", "backups", "logs")


def _heavy(path):
    parts = set(str(path).replace("\\", "/").split("/"))
    return bool(parts & set(_HEAVY))


def _safe_items():
    import migrate_legacy
    det = migrate_legacy.detect()
    items = [it for it in det.get("items", [])
             if it.get("kind") in _SAFE_KINDS and it.get("action") in ("migrar", "reapuntar")
             and not (it.get("kind") == "estado" and _heavy(it.get("path", "")))]
    return det, items


def needed(ctx):
    _, items = _safe_items()
    return bool(items)


def run(ctx):
    """Varias pasadas: la definición de cada cerebro solo se ve DESPUÉS de copiar
    el registro de agentes (la detección lee el registro actual)."""
    import migrate_legacy
    for _ in range(3):
        det, items = _safe_items()
        if not items:
            return
        res = migrate_legacy.apply({"workspace": det.get("workspace"), "items": items,
                                    "roots": det.get("roots", [])})
        if not res.get("done"):
            break
    # Lo que no se pudo copiar (p. ej. un cerebro sin permisos) NO bloquea la cola
    # de ajustes: queda a la vista en `workspace doctor` (fase 5d, restos de la
    # instalación anterior) con su acción `workspace migrar-legado`.
    _, items = _safe_items()
    if items:
        msg = {"es": "%d elemento(s) de la instalación anterior quedan para "
                     "`workspace migrar-legado`",
               "en": "%d item(s) from the previous install are left for "
                     "`workspace migrar-legado`"}
        try:
            import i18n
            lang = i18n.lang()
        except Exception:
            lang = "es"
        ctx.log(msg.get(lang, msg["es"]) % len(items))
