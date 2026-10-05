#!/usr/bin/env python3
"""WORKSPACE · keybinds — registro DATA-DRIVEN de las teclas rápidas del hub.

El mapa tecla→acción del recinto (saltos a agentes, opciones del MENÚ y
acciones rápidas sobre el agente apuntado) dejó de ser hardcodeado: vive
aquí como un REGISTRO con defaults en código y overrides PER-MÁQUINA en
`~/.claude/workspace/keybinds.json` (solo se guardan las diferencias — un
archivo vacío/ausente = defaults puros). La pantalla «Atajos»
(keybinds_tui, MENÚ del hub) edita este registro; front._jump_map y los
drivers lo consumen. Falla-suave ABSOLUTA: archivo roto/ilegible → defaults.

La sección «menú» ya NO se lista a mano (2026-10-04): se DERIVA del menú
real del hub (front.menu_entries — gates incluidos, p. ej. «Dev» solo el
dueño/dev). Una sección nueva aparece aquí sola, con su tecla default
conocida (_MENU_DEFAULTS) o auto-derivada de su etiqueta, y es re-mapeable
como cualquier otra. Sin front.py → _MENU_BASE (paridad de siempre).

Contrato:
  · una ACCIÓN = id estable (`agente.3` · `menu.__cal__` · `accion.motor`)
    con etiqueta, descripción y tecla default. El id es el ancla: re-mapear
    jamás cambia qué HACE la acción, solo con qué tecla se dispara.
  · una TECLA = UN carácter imprimible; letra → minúscula. Las RESERVADAS
    del recinto (q espacio Enter Esc flechas Tab) y las letras apartadas
    por otras pantallas (t a e x f d n p) no se pueden asignar.
  · COLISIONES: una tecla pertenece a UNA acción. `set_key` rechaza la
    repetida con el nombre de quién la tiene; `effective()` además se
    defiende solo (override duplicado/ilegal → se ignora y cae al default;
    default tapado por un override ajeno → esa acción queda SIN tecla, y
    la pantalla lo muestra — nunca dos acciones con la misma tecla).

Cero dependencias (stdlib, Python 3.9+). Mac y Windows.
"""
import json
import os

# ── registro de ACCIONES (orden = orden de la pantalla «Atajos») ───────────
# (id, tecla_default, etiqueta, descripción)
_AGENTES = tuple(
    ("agente.%d" % n, str(n), "agente %d" % n,
     "apunta al agente %d del altar SIN lanzarlo (ahí aplican motor/info/"
     "Enter); la misma tecla otra vez — o Enter — lo lanza" % n)
    for n in range(1, 10))

# Teclas que JAMÁS se asignan: q (salir — contrato del recinto), espacio
# (cicla pins), y las letras apartadas por otras pantallas/convenciones del
# equipo (t a e x f d n p). Enter/Esc/Tab/flechas no son "un carácter
# imprimible", así que el validador ya las rechaza solo.
RESERVADAS = frozenset("q taexfdnp".replace(" ", "")) | frozenset((" ",))

# ── sección «menú»: DERIVADA del menú REAL del hub (front.menu_entries) ───
# Una sección nueva del MENÚ (Dev, GitHub, futuras) aparece aquí SOLA —
# con tecla default estable si es conocida, o auto-derivada de su etiqueta
# — y queda re-mapeable en «Atajos» sin tocar este archivo.
#
# _MENU_BASE = PARIDAD/fallback (sin front.py o roto → exactamente el
# registro de siempre) + la fuente de las teclas default CONOCIDAS y de las
# descripciones curadas por token. El orden/la presencia los manda el hub.
_MENU_BASE = (
    ("menu.__ramas__", "r", "GitHub",
     "abre tus repos: mapa local de ramas + PRs/issues/releases vía gh"),
    ("menu.__devmap__", "v", "Dev",
     "abre el detrás de workspace: referencia de comandos + mapa del "
     "pipeline (solo el dueño/dev la ve)"),
    ("menu.__cal__", "c", "Calendario",
     "abre el editor de agenda a pantalla completa"),
    ("menu.__tono__", "o", "Tono",
     "abre los diales de personalidad de tus agentes"),
    ("menu.__keybinds__", "k", "Atajos",
     "abre esta pantalla — re-mapea cualquiera de estas teclas"),
    ("menu.__doctor__", "u", "Actualizaciones",
     "revisar · reparar · actualizar el harness"),
    ("menu.__add_agent__", "g", "Agregar agente",
     "crear o cargar un agente nuevo"),
)
_MENU_DEFAULTS = {a[0]: a[1] for a in _MENU_BASE}
_MENU_DESCS = {a[0]: a[3] for a in _MENU_BASE}

_ACCIONES = (
    ("accion.motor", "m", "ciclar motor",
     "cambia el MOTOR del agente apuntado (claude-code/codex/…) sin "
     "lanzarlo — se guarda per-máquina; el siguiente Enter ya usa ese motor"),
    ("accion.info", "i", "detalle del agente",
     "muestra en una línea el agente apuntado: motor efectivo (y su "
     "origen), dónde vive su cerebro y su tarea viva — sin lanzarlo"),
)


def _menu_real():
    """[(token, etiqueta, tagline)] del MENÚ REAL del hub, gates incluidos
    (front.menu_entries — la MISMA lista que pinta el recinto). __shell__
    no entra: su tecla es `q`, contrato del recinto. Falla-suave ABSOLUTA:
    sin front / error → None (se usa _MENU_BASE, paridad de siempre)."""
    try:
        import front as _front
        ent = [(str(t), str(l), str(g)) for t, l, g in _front.menu_entries()
               if t != "__shell__"]
        return ent or None
    except Exception:
        return None


def _tecla_auto(label, usadas):
    """Default auto para un token SIN tecla conocida: la primera letra/cifra
    de su etiqueta que no esté reservada ni tomada; si ninguna sirve, la
    primera libre del alfabeto; si nada queda, '' (sin tecla — la pantalla
    lo muestra y se re-mapea con Enter, jamás ambigua)."""
    import string
    for ch in str(label).lower() + string.ascii_lowercase + string.digits:
        if (ch.isalnum() and ch not in RESERVADAS and ch not in usadas):
            return ch
    return ""


def _armar_menu():
    """La sección «menú» del registro, derivada del hub real (o _MENU_BASE
    en fallback): [(id, tecla_default, etiqueta, descripción)]. Teclas
    conocidas primero (estables entre versiones); tokens nuevos reciben
    auto-default sin colisionar con agentes (1-9) ni acciones (m/i)."""
    real = _menu_real()
    if real is None:
        return _MENU_BASE
    usadas = {a[1] for a in _AGENTES} | {a[1] for a in _ACCIONES}
    usadas |= {_MENU_DEFAULTS[("menu." + t)] for t, _l, _g in real
               if ("menu." + t) in _MENU_DEFAULTS}
    menu = []
    for tok, lbl, tag in real:
        aid = "menu." + tok
        k = _MENU_DEFAULTS.get(aid)
        if k is None:
            k = _tecla_auto(lbl, usadas)
            if k:
                usadas.add(k)
        desc = _MENU_DESCS.get(aid) or ("abre «%s» — %s" % (lbl, tag)
                                        if tag else "abre «%s»" % lbl)
        menu.append((aid, k, lbl, desc))
    return tuple(menu)


# El registro vivo (módulo-level por compatibilidad). refresh() lo re-arma
# — p. ej. si el gate de una sección cambió dentro del mismo proceso.
_MENU = _armar_menu()
REGISTRO = _AGENTES + _MENU + _ACCIONES
GRUPOS = (("agentes", tuple(a[0] for a in _AGENTES)),
          ("menú", tuple(a[0] for a in _MENU)),
          ("acciones rápidas", tuple(a[0] for a in _ACCIONES)))
_BY_ID = {a[0]: a for a in REGISTRO}


def refresh():
    """Re-deriva la sección «menú» del hub real (gates re-evaluados) y
    re-arma el registro. Para pantallas de vida larga y tests."""
    global _MENU, REGISTRO, GRUPOS, _BY_ID
    _MENU = _armar_menu()
    REGISTRO = _AGENTES + _MENU + _ACCIONES
    GRUPOS = (("agentes", tuple(a[0] for a in _AGENTES)),
              ("menú", tuple(a[0] for a in _MENU)),
              ("acciones rápidas", tuple(a[0] for a in _ACCIONES)))
    _BY_ID = {a[0]: a for a in REGISTRO}
    return GRUPOS

def _path():
    """keybinds.json junto al settings store (respeta HOME parchado en
    tests). Falla-suave: sin settings.py, la ruta canónica directa."""
    try:
        import settings as _st
        return os.path.join(os.path.dirname(_st.store_path()),
                            "keybinds.json")
    except Exception:
        return os.path.join(os.path.expanduser("~"), ".claude", "workspace",
                            "keybinds.json")


def defaults():
    """{id: tecla_default} — el mapa de fábrica, siempre completo."""
    return {a[0]: a[1] for a in REGISTRO}


def overrides():
    """Los overrides GUARDADOS per-máquina ({id: tecla}); {} si no hay
    archivo o está roto (falla-suave)."""
    try:
        with open(_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        binds = data.get("binds") if isinstance(data, dict) else None
        return {k: v for k, v in (binds or {}).items()
                if k in _BY_ID and isinstance(v, str)}
    except Exception:
        return {}


def _save(binds):
    """Persiste los overrides (atómico: tmp + rename). False si no pudo."""
    try:
        p = _path()
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "binds": binds}, fh,
                      ensure_ascii=False, indent=2)
        os.replace(tmp, p)
        return True
    except Exception:
        return False


def _norm(key):
    """Normaliza una tecla candidata → str de 1 char minúscula, o ''."""
    if not isinstance(key, str) or len(key) != 1 or not key.isprintable():
        return ""
    return key.lower()


def effective():
    """{id: tecla} EFECTIVO: defaults + overrides válidos, defendido contra
    colisiones (ver contrato arriba). Acción cuya tecla quedó tomada por
    otra → '' (sin tecla — visible en la pantalla, jamás ambigua)."""
    ov = overrides()
    eff, usadas = {}, set()
    for aid, dflt, _lbl, _d in REGISTRO:
        k = _norm(ov.get(aid, "")) or dflt
        if k in RESERVADAS or k in usadas:
            k = dflt if (dflt not in usadas and dflt not in RESERVADAS) \
                else ""
        if k:
            usadas.add(k)
        eff[aid] = k
    return eff


def by_key():
    """{tecla: id} del mapa efectivo (sin entradas vacías)."""
    return {k: aid for aid, k in effective().items() if k}


def label(aid):
    return _BY_ID.get(aid, ("", "", aid, ""))[2]


def desc(aid):
    return _BY_ID.get(aid, ("", "", "", ""))[3]


def default_of(aid):
    return _BY_ID.get(aid, ("", "", "", ""))[1]


def es_custom(aid):
    """True si la acción tiene override guardado (≠ default)."""
    ov = overrides()
    return aid in ov and _norm(ov[aid]) not in ("", default_of(aid))


def set_key(aid, key):
    """Asigna `key` a la acción `aid` y PERSISTE. Devuelve (ok, msg) —
    el msg siempre dice qué pasó (guardado / reservada / colisión con
    quién / inválida). Asignar el default borra el override (queda limpio)."""
    if aid not in _BY_ID:
        return False, "acción desconocida"
    k = _norm(key)
    if not k:
        return False, "tecla inválida — debe ser UN carácter imprimible"
    if k in RESERVADAS:
        return False, "«%s» está reservada (q sale · t/a/e/x/f/d/n/p son " \
                      "de otras pantallas)" % key
    dueño = by_key().get(k)
    if dueño and dueño != aid:
        return False, "«%s» ya la usa %s — libérala primero" \
            % (k, label(dueño))
    ov = overrides()
    if k == default_of(aid):
        ov.pop(aid, None)                 # volver al default = sin override
    else:
        ov[aid] = k
    if not _save(ov):
        return False, "no pude guardar el registro — queda igual"
    return True, "%s → «%s» · guardado ✓" % (label(aid), k)


def clear(aid):
    """Quita el override de `aid` (vuelve a su default). (ok, msg)."""
    ov = overrides()
    if aid in ov:
        ov.pop(aid)
        if not _save(ov):
            return False, "no pude guardar — queda igual"
    return True, "%s → default «%s» ✓" % (label(aid), default_of(aid))


def reset_all():
    """Borra TODOS los overrides (defaults de fábrica). (ok, msg)."""
    if not _save({}):
        return False, "no pude guardar — queda igual"
    return True, "todas las teclas en default ✓"


def imprimir():
    """Listado plano (fallback sin terminal interactiva)."""
    eff = effective()
    print("atajos del hub (per-máquina: %s)" % _path())
    for titulo, ids in GRUPOS:
        print("\n%s" % titulo)
        for aid in ids:
            k = eff.get(aid) or "—"
            marca = " ●" if es_custom(aid) else ""
            print("  %-18s %s%s" % (label(aid), k, marca))
    return 0


if __name__ == "__main__":
    raise SystemExit(imprimir())
