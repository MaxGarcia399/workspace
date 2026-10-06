#!/usr/bin/env python3
"""WORKSPACE · personalidad — el TONO de cada agente en diales de 1 a 5.

Idea del socio (2026-09-24): «niveles de personalidad para los agentes —
amabilidad, sarcasmo, longitud— que lo pueda cambiar y realmente vea
reflejado un cambio en las respuestas». v2 (mismo día): más diales, **por
agente**, en **pantalla propia** (`workspace tono`) y **en tiempo real**.

CÓMO SE APLICA (y por qué NO se reescriben los .md del cerebro)
---------------------------------------------------------------
  a) Reescribir `BOOT/*.md` → es la IDENTIDAD del agente (N3), está
     versionada y **sincroniza a todo el equipo**: mover un dial en Windows
     le cambiaría el carácter a otro socio. Además, churn en git en cada toque.
  b) Reescribir `CLAUDE.md` → mismo problema de sync y se lee una sola vez.
  c) **Inyección por hook (esto).** Dos listeners:
       · `session_start` → el bloque COMPLETO (los diales con su
         instrucción) al abrir la pestaña.
       · `user_prompt`   → una LÍNEA compacta en CADA mensaje ⇒ mover un
         dial se siente **al siguiente mensaje, sin reiniciar la sesión**.
     Per-máquina, sin git, sin sync. Con todo en 3 no viaja ni un token.

ALMACÉN — `~/.claude/workspace/tono.json` (per-máquina, gitignored):

    {"schema": 2,
     "global":  {"longitud": 2},
     "agentes": {"zenith": {"sarcasmo": 4}}}

Resolución: valor del AGENTE > valor GLOBAL > 3 (neutro). Solo se guarda lo
que NO está en neutro, así que un archivo vacío = comportamiento de siempre.

LÍMITE DURO: los diales modulan ESTILO. Jamás identidad, reglas N1/N2/N3,
seguridad ni la honestidad de lo que se reporta — el bloque inyectado lo dice
explícito. Un dial no es una puerta trasera para pedir que te mientan bonito.

Cero dependencias (stdlib, Python 3.9+). Mac y Windows.
"""
import json
import os
import sys
import uuid

# i18n (lado cliente): la pantalla TONO y el mini-panel del dashboard se ven en
# el idioma activo. Falla-suave — sin el módulo, `_t()` devuelve el español
# inline (paridad EXACTA con el flujo de hoy; ES byte-idéntico con lang=es).
try:
    import i18n
except Exception:
    i18n = None


def _t(key, es, **kw):
    """Traducción de `key` con el español inline `es` como red de seguridad:
    sin i18n o con clave faltante → `es`. Con **kw aplica .format(**kw)."""
    if i18n is None:
        s = es
    else:
        try:
            v = i18n.t(key)
            s = v if v != key else es
        except Exception:
            s = es
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


def _lang():
    if i18n is None:
        return "es"
    try:
        return i18n.lang()
    except Exception:
        return "es"


SCHEMA = 2
NEUTRO = 3

# ── los diales ─────────────────────────────────────────────────────────────
# `niveles` guarda la INSTRUCCIÓN que leerá el agente (no una etiqueta). El 3
# no tiene texto a propósito: es "como siempre", y por eso un setup sin tocar
# no inyecta absolutamente nada.
#
# `_DIAL_SRC` es la FUENTE en español (y la red de seguridad inline de i18n).
# `DIALS` se expone vía `__getattr__` y devuelve estos mismos diales con el
# label/corto/polos/niveles en el IDIOMA ACTIVO — así la pantalla TONO y el
# mini-panel del dashboard (que lee `d["corto"]`/`d["eje"]`) se traducen sin
# tocar su código. Con lang=es es byte-idéntico a `_DIAL_SRC`.
_DIAL_SRC = (
    {"key": "amabilidad", "label": "Amabilidad", "corto": "amab",
     "eje": ("seco", "cálido"),
     "niveles": {
         1: "Sin cortesías ni preámbulos: dato, resultado y punto.",
         2: "Trato directo; nada de adornos sociales.",
         4: "Trato cálido: reconoce el esfuerzo del socio y acompaña con una "
            "línea humana.",
         5: "Trato muy cálido y cercano: celebra los avances y cuida el ánimo "
            "del socio además de resolver."}},
    {"key": "franqueza", "label": "Franqueza", "corto": "fran",
     "eje": ("suave", "brutal"),
     "niveles": {
         1: "Señala los problemas con mucho tacto, envueltos en contexto.",
         2: "Suaviza las críticas; primero lo que sí funciona.",
         4: "Di sin rodeos qué está mal y por qué, aunque incomode.",
         5: "Brutalmente honesto: si una idea es mala, la primera frase lo "
            "dice. Sin colchones."}},
    {"key": "sarcasmo", "label": "Sarcasmo", "corto": "sarc",
     "eje": ("literal", "mordaz"),
     "niveles": {
         1: "Cero ironía. Literal y neutro siempre.",
         2: "Ironía mínima, solo si es evidente que cae bien.",
         4: "Permítete ironía seca y algún comentario filoso — nunca a costa "
            "del socio ni de la precisión del dato.",
         5: "Mordaz con las situaciones (el código, los bugs, tú mismo). "
            "Jamás con el socio, y jamás sacrificando exactitud por el chiste."}},
    {"key": "humor", "label": "Humor", "corto": "hum",
     "eje": ("serio", "juguetón"),
     "niveles": {
         1: "Registro serio de principio a fin.",
         2: "Alguna ligereza ocasional.",
         4: "Juega con el lenguaje y suelta bromas cuando encajan.",
         5: "Tono juguetón y ocurrente; busca el remate ingenioso sin perder "
            "el hilo del trabajo."}},
    {"key": "longitud", "label": "Longitud", "corto": "long",
     "eje": ("breve", "amplio"),
     "niveles": {
         1: "Responde en UNA línea. Si no cabe, manda el detalle a un archivo "
            "y da la ruta.",
         2: "Máximo 3 frases. Lo esencial primero; el detalle, a archivo.",
         4: "Desarrolla: contexto, razón de la decisión y qué sigue.",
         5: "Exhaustivo: alternativas consideradas, trade-offs y riesgos "
            "además del resultado."}},
    {"key": "formalidad", "label": "Formalidad", "corto": "form",
     "eje": ("cuate", "formal"),
     "niveles": {
         1: "Lenguaje coloquial y relajado, como un cuate del equipo.",
         2: "Informal pero claro.",
         4: "Registro profesional y cuidado.",
         5: "Registro formal de consultoría: sin coloquialismos, estructura "
            "explícita."}},
    {"key": "tecnicismo", "label": "Tecnicismo", "corto": "tec",
     "eje": ("llano", "jerga"),
     "niveles": {
         1: "Explica en lenguaje llano; traduce todo término técnico.",
         2: "Términos técnicos solo cuando no haya equivalente simple.",
         4: "Usa el vocabulario técnico preciso sin traducirlo.",
         5: "Habla de ingeniero a ingeniero: jerga, nombres de patrones y "
            "detalles de implementación sin diluir."}},
    {"key": "didactica", "label": "Didáctica", "corto": "did",
     "eje": ("resultado", "enseña"),
     "niveles": {
         1: "Solo el resultado. Nada de explicar el cómo ni el porqué.",
         2: "Resultado y, a lo sumo, una línea de porqué.",
         4: "Explica el porqué de la decisión para que el socio aprenda el "
            "patrón.",
         5: "Enseña: razona el porqué, señala el principio general y qué "
            "buscar la próxima vez."}},
    {"key": "iniciativa", "label": "Iniciativa", "corto": "inic",
     "eje": ("espera", "anticipa"),
     "niveles": {
         1: "Haz EXACTAMENTE lo pedido. Antes de extender el alcance, "
            "pregunta.",
         2: "Cíñete a lo pedido; sugiere lo demás en una línea al final.",
         4: "Propón el siguiente paso y ejecuta lo obvio sin pedir permiso.",
         5: "Anticipa: ejecuta lo pedido y además lo que claramente hace "
            "falta para que sirva, informando qué hiciste de más."}},
    {"key": "emojis", "label": "Emojis", "corto": "emo",
     "eje": ("ninguno", "muchos"),
     "niveles": {
         1: "Cero emojis.",
         2: "Emojis solo donde el formato del harness ya los usa.",
         4: "Usa emojis para marcar estados y secciones.",
         5: "Emojis generosos en títulos, listas y estados."}},
)
#: Las CLAVES de los diales, en orden. Son independientes del idioma: sirven
#: para pertenencia (`_limpio`, `set_nivel`) y para el CLI sin reconstruir nada.
_DIAL_KEYS = tuple(d["key"] for d in _DIAL_SRC)

#: DIALS traducidos, memoizados por idioma. El catálogo es estático, así que
#: cachear por código es seguro; si el idioma cambia en vivo, la clave nueva
#: reconstruye (nunca sirve datos rancios).
_DIALS_CACHE = {}


def _dials():
    """Los diales en el IDIOMA ACTIVO (label/corto/polos/niveles). Mismas
    claves y mismo orden que `_DIAL_SRC`; solo cambian los textos visibles."""
    code = _lang()
    out = _DIALS_CACHE.get(code)
    if out is not None:
        return out
    built = []
    for src in _DIAL_SRC:
        k = src["key"]
        built.append({
            "key": k,
            "label": _t("tono.dial.%s.label" % k, src["label"]),
            "corto": _t("tono.dial.%s.corto" % k, src["corto"]),
            "eje": (_t("tono.dial.%s.pole.lo" % k, src["eje"][0]),
                    _t("tono.dial.%s.pole.hi" % k, src["eje"][1])),
            "niveles": {n: _t("tono.dial.%s.lvl.%d" % (k, n), txt)
                        for n, txt in src["niveles"].items()},
        })
    out = tuple(built)
    _DIALS_CACHE[code] = out
    return out


def _by_key():
    """{key: dial} en el idioma activo."""
    return {d["key"]: d for d in _dials()}


def __getattr__(name):
    """`personalidad.DIALS` / `._BY_KEY` se resuelven al idioma activo. (PEP
    562: solo dispara para atributos del MÓDULO, no para nombres locales.)"""
    if name == "DIALS":
        return _dials()
    if name == "_BY_KEY":
        return _by_key()
    raise AttributeError("module %r has no attribute %r" % (__name__, name))


# Presets: mueven varios diales de golpe (lo que el socio llamó «modos»).
PRESETS = {
    "cliente": {"formalidad": 5, "sarcasmo": 1, "humor": 1, "emojis": 1,
                "amabilidad": 4, "tecnicismo": 2},
    "taller": {"formalidad": 1, "sarcasmo": 4, "franqueza": 5,
               "longitud": 2, "tecnicismo": 5},
    "express": {"longitud": 1, "amabilidad": 2, "didactica": 1,
                "iniciativa": 4},
    "maestro": {"didactica": 5, "longitud": 4, "tecnicismo": 2,
                "amabilidad": 4},
}


# ── almacén ────────────────────────────────────────────────────────────────
def path():
    """Ruta del store. `WORKSPACE_TONO` la pisa (tests herméticos)."""
    p = os.environ.get("WORKSPACE_TONO")
    if p:
        return p
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace",
                        "tono.json")


def _empty():
    return {"schema": SCHEMA, "global": {}, "agentes": {}}


def _limpio(d):
    """Solo diales conocidos con valor 1-5 distinto del neutro."""
    out = {}
    for k, v in (d or {}).items():
        if k not in _DIAL_KEYS:
            continue
        try:
            v = int(v)
        except (TypeError, ValueError):
            continue
        if 1 <= v <= 5 and v != NEUTRO:
            out[k] = v
    return out


def load():
    """El store. Ausente/corrupto → vacío. Jamás levanta (lo llama un hook)."""
    try:
        with open(path(), encoding="utf-8") as f:
            raw = json.load(f)
        if not isinstance(raw, dict):
            return _empty()
        out = _empty()
        out["global"] = _limpio(raw.get("global"))
        ags = raw.get("agentes")
        if isinstance(ags, dict):
            for name, vals in ags.items():
                v = _limpio(vals)
                if v:
                    out["agentes"][str(name).lower()] = v
        return out
    except Exception:
        return _empty()


def save(data):
    """Escritura ATÓMICA (tmp + os.replace). True si quedó en disco."""
    tmp = ""
    try:
        dest = path()
        d = os.path.dirname(dest)
        if d and not os.path.isdir(d):
            os.makedirs(d, exist_ok=True)
        tmp = "%s.tmp-%d-%s" % (dest, os.getpid(), uuid.uuid4().hex[:8])
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, dest)
        return True
    except Exception:
        try:
            if tmp:
                os.unlink(tmp)
        except Exception:
            pass
        return False


# ── resolución ─────────────────────────────────────────────────────────────
def niveles(agente=None):
    """{dial: 1-5} efectivos: agente > global > neutro."""
    data = load()
    out = {k: NEUTRO for k in _DIAL_KEYS}
    out.update(data.get("global") or {})
    if agente:
        out.update((data.get("agentes") or {}).get(str(agente).lower()) or {})
    return out


def activos(agente=None):
    """Solo lo que está movido del neutro — lo que de verdad cambia algo."""
    return {k: v for k, v in niveles(agente).items() if v != NEUTRO}


def resumen(agente=None, corto=True):
    """`sarc 4 · long 2` para pintar en el hub. '' si todo está en neutro."""
    act = activos(agente)
    if not act:
        return ""
    dials = _dials()
    etq = {d["key"]: (d["corto"] if corto else d["label"]) for d in dials}
    return " · ".join("%s %d" % (etq[d["key"]], act[d["key"]])
                      for d in dials if d["key"] in act)


def set_nivel(dial, valor, agente=None):
    """Fija un dial (1-5). Neutro = se borra la entrada. True si guardó."""
    if dial not in _DIAL_KEYS:
        return False
    try:
        v = int(valor)
    except (TypeError, ValueError):
        return False
    if not 1 <= v <= 5:
        return False
    data = load()
    if agente:
        ag = str(agente).lower()
        tabla = dict(data["agentes"].get(ag) or {})
    else:
        tabla = dict(data["global"])
    if v == NEUTRO:
        tabla.pop(dial, None)
    else:
        tabla[dial] = v
    if agente:
        ag = str(agente).lower()
        if tabla:
            data["agentes"][ag] = tabla
        else:
            data["agentes"].pop(ag, None)
    else:
        data["global"] = tabla
    return save(data)


def aplicar_preset(nombre, agente=None):
    """Mueve varios diales de golpe (PRESETS). True si aplicó."""
    preset = PRESETS.get(str(nombre).lower())
    if not preset:
        return False
    ok = True
    for k, v in preset.items():
        ok = set_nivel(k, v, agente) and ok
    return ok


def reset(agente=None):
    """Todo a neutro. Sin agente = borra el global (los overrides quedan)."""
    data = load()
    if agente:
        data["agentes"].pop(str(agente).lower(), None)
    else:
        data["global"] = {}
    return save(data)


def agentes_registrados():
    """Nombres de los agentes que ve el hub. Es `dispatch.load_registry()` —
    el registry EFECTIVO (los committeados + los cargados per-maquina), la
    misma fuente que pinta la caja AGENTES del menu. `agentsreg.agents()` NO
    sirve aqui: solo lista los cargados a mano en esta maquina (uno), y la
    pantalla mostraria un agente cuando el socio ve cuatro."""
    try:
        import dispatch
        reg = dispatch.load_registry() or {}
        return [a["name"] for a in (reg.get("agents") or ()) if a.get("name")]
    except Exception:
        pass
    try:
        import agentsreg
        return [a.get("name") for a in (agentsreg.agents() or ())
                if a.get("name")]
    except Exception:
        return []


def agente_de(cwd=None):
    """Nombre del agente dueño de `cwd` (su cerebro). '' si no se puede.
    Primero el env que exporta el launcher; si no, se resuelve por ruta."""
    env = os.environ.get("WORKSPACE_AGENT_NAME")
    if env:
        return env.strip().lower()
    real = os.path.realpath(cwd or os.getcwd())
    try:
        import dispatch
        for a in (dispatch.load_registry() or {}).get("agents") or ():
            b = a.get("brain") or ""
            try:
                if b and os.path.realpath(b) == real:
                    return (a.get("name") or "").lower()
            except Exception:
                continue
    except Exception:
        pass
    # ultimo recurso: el nombre de la carpeta del cerebro (`C:/MI-AGENTE - BRAIN`
    # -> zenith). Barato y suele acertar; si no, se queda en global.
    base = os.path.basename(real).lower()
    for sep in (" - ", "-", "_"):
        if sep in base:
            base = base.split(sep)[0]
    return base.strip() if base else ""


# ── lo que se le inyecta al agente ─────────────────────────────────────────
_LIMITE = ("Esto ajusta **estilo**, nada más: no cambia tu identidad, ni las "
           "reglas N1/N2/N3, ni la seguridad, ni la honestidad de lo que "
           "reportas. Si un dial chocara con decir la verdad o con una regla, "
           "gana la regla.")


def bloque(agente=None):
    """Texto COMPLETO para el arranque de sesión. "" si todo es neutro."""
    act = activos(agente)
    if not act:
        return ""
    out = [_t("tono.block.title",
              "## Tono de esta sesión (config del socio en esta máquina)")]
    for d in _dials():
        v = act.get(d["key"])
        txt = d["niveles"].get(v) if v else None
        if txt:
            out.append("- **%s %d/5** — %s" % (d["label"], v, txt))
    out += ["", _t("tono.limit", _LIMITE)]
    return "\n".join(out)


def linea(agente=None):
    """Recordatorio COMPACTO para inyectar en cada mensaje (tiempo real).
    Lleva la instrucción viva de cada dial movido, en una sola línea por dial
    para que cambiar un nivel se sienta al SIGUIENTE mensaje sin reabrir la
    sesión. "" si todo es neutro (coste cero)."""
    act = activos(agente)
    if not act:
        return ""
    trozos = []
    for d in _dials():
        v = act.get(d["key"])
        txt = d["niveles"].get(v) if v else None
        if txt:
            trozos.append("%s %d/5: %s" % (d["label"], v, txt))
    return _t("tono.inject.prefix", "[tono activo] ") + "  ".join(trozos)


# ── CLI ────────────────────────────────────────────────────────────────────
def _barra(v):
    return "".join("█" if i < v else "░" for i in range(5))


def _uso():
    return ("uso:\n"
            "  workspace tono                      pantalla interactiva\n"
            "  workspace tono ver [agente]         imprime los diales\n"
            "  workspace tono <dial> <1-5>         global\n"
            "  workspace tono <agente> <dial> <1-5>  solo ese agente\n"
            "  workspace tono preset <%s> [agente]\n"
            "  workspace tono reset [agente]\n\n"
            "diales: %s"
            % ("|".join(sorted(PRESETS)),
               ", ".join(_DIAL_KEYS)))


def imprimir(agente=None):
    niv = niveles(agente)
    suffix = (_t("tono.cli.agent_suffix", "  ·  agente: %s" % agente,
                 name=agente) if agente
              else _t("tono.cli.global_suffix", "  ·  global"))
    print(_t("tono.cli.header", "Tono%s  ·  3 = como siempre" % suffix,
             suffix=suffix) + "\n")
    for d in _dials():
        v = niv[d["key"]]
        nota = d["niveles"].get(v) or _t("tono.cli.default", "por defecto")
        print("  %-11s %s %d/5  %-11s %s"
              % (d["key"], _barra(v), v,
                 "%s→%s" % d["eje"] if v != NEUTRO else "", nota[:52]))
    if not activos(agente):
        print("\n  " + _t("tono.cli.all_neutral",
                          "(todo en neutro: no se inyecta nada)"))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-h", "--help", "help"):
        print(_uso())
        return 0
    if not argv or argv[0] in ("ui", "--ui", "pantalla"):
        try:
            import tono_tui
            return tono_tui.run()
        except Exception as e:
            print("tono: no pude abrir la pantalla (%s)" % e, file=sys.stderr)
            return imprimir()
    conocidos = set(agentes_registrados())
    if argv[0] in ("ver", "list", "ls"):
        return imprimir(argv[1].lower() if len(argv) > 1 else None)
    if argv[0] in ("reset", "neutro"):
        ag = argv[1].lower() if len(argv) > 1 else None
        reset(ag)
        print("tono en neutro%s" % (" para %s" % ag if ag else " (global)"))
        return 0
    if argv[0] in ("preset", "modo"):
        if len(argv) < 2:
            print(_uso(), file=sys.stderr)
            return 2
        ag = argv[2].lower() if len(argv) > 2 else None
        if not aplicar_preset(argv[1], ag):
            print("preset desconocido (hay: %s)" % ", ".join(sorted(PRESETS)),
                  file=sys.stderr)
            return 2
        print("preset «%s» aplicado%s" % (argv[1],
                                          " a %s" % ag if ag else " (global)"))
        return 0
    ag = None
    if argv[0].lower() in conocidos and len(argv) >= 3:
        ag, argv = argv[0].lower(), argv[1:]
    if len(argv) >= 2:
        if not set_nivel(argv[0], argv[1], ag):
            print("dial o valor inválido — %s" % _uso(), file=sys.stderr)
            return 2
        print("%s → %s/5%s" % (_by_key()[argv[0]]["label"], argv[1],
                               " (solo %s)" % ag if ag else " (global)"))
        print("(aplica al siguiente mensaje; el bloque completo, al abrir "
              "sesión nueva)")
        return 0
    print(_uso(), file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
