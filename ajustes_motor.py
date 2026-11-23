#!/usr/bin/env python3
"""Modelo, esfuerzo y modo de cada motor, como botones de la página (§6: «botones, no el chat»).

Cada fila sale de la ayuda OFICIAL del motor (su `--help`, su `help <tema>`, su catálogo o lo que enseña su propia
pantalla), nunca de su código. Lo que no se pudo confirmar así no está: lo que un motor no tiene no aparece, no se
inventan valores y no se fuerza un modelo por defecto.

Dos caminos, sin abrir nunca su selector:
  · «sesion»   un comando CON argumento dentro de su sesión: el servidor lo teclea en su caja de chat y confirma
               leyendo su pie (localhost_web.aplicar_ajuste).
  · «arranque» una opción al arrancar: se guarda y viaja en el siguiente arranque de su conversación («se aplica al
               reabrir»), por el passthrough de dispatch. Solo donde su adapter la agrega tal cual sin cambiar su
               arranque: en Claude Code siempre (su arranque va por el gancho); en Codex solo si RETOMA su sesión
               (`al_reanudar`: en una sesión nueva, cualquier argumento le quita su mensaje de arranque).

Fuentes (esta máquina, 17-nov-2026; la tabla del cierre de la entrega lo dice por motor):
  claude-code 2.1.326  `claude --help`: --model «alias for the latest model (e.g. 'fable', 'opus', or 'sonnet')»;
                       --effort <level> (low, medium, high, xhigh, max). `/model <alias>` en sesión NO se usa: guarda
                       el modelo como el de fábrica de TODAS sus sesiones («… and saved as your default for new
                       sessions», ~/.claude/settings.json; F3 de la prueba de punta a punta v4).
  codex 0.169.0        `codex --help`: -m/--model, -c key=value; `codex debug models` (el catálogo: modelos
                       «list» y sus supported_reasoning_levels); la clave model_reasoning_effort.
  copilot 1.0.112      `copilot help commands`: /model «use 'auto'…»; su pantalla: «enter /model fusion to switch»;
                       `copilot help config`: los valores de `model`.
"""
import re

TITULOS = {"modelo": "Modelo", "esfuerzo": "Esfuerzo", "modo": "Modo"}
NIVELES = {"none": "ninguno", "minimal": "mínimo", "low": "bajo", "medium": "medio", "high": "alto",
           "xhigh": "muy alto", "max": "máximo", "ultra": "ultra"}


def _niveles(*vs):
    return tuple((v, NIVELES[v]) for v in vs)


def _bonito(slug):
    """«claude-haiku-5.5» → «Claude Haiku 5.5» (cómo lo enseña su pie); «gpt-…» → «GPT …»."""
    return " ".join("GPT" if p == "gpt" else p[:1].upper() + p[1:] for p in slug.split("-"))


# shortcut: modelos y niveles copiados de su ayuda en estas versiones; leerlos en vivo (codex debug models, copilot help config) cuando un motor cambie su lista
# `codex debug models`, visibility «list», en su orden (priority); los niveles de cada uno, de su catálogo
_CODEX = (("gpt-6.1-sol", "GPT-6.1-Sol"), ("gpt-6-astra", "GPT-6-Astra"), ("gpt-6-sol", "GPT-6-Sol"),
          ("gpt-6-luna", "GPT-6-Luna"), ("gpt-5.6-sol", "GPT-5.6-Sol"), ("gpt-6.1-terra", "GPT-6.1 Terra"),
          ("gpt-5.6-terra", "GPT-5.6-Terra"), ("gpt-5.6-luna", "GPT-5.6-Luna"), ("gpt-5.5", "GPT-5.5"))
_TODOS = ("low", "medium", "high", "xhigh", "max", "ultra")
_CODEX_NIVELES = {"gpt-6-luna": _TODOS[:5], "gpt-5.6-luna": _TODOS[:5], "gpt-5.5": _TODOS[:4]}
# `copilot help config` → `model`, en su orden, más 'auto' de `copilot help commands`
_COPILOT = ("claude-sonnet-5.5", "claude-sonnet-5", "claude-fable-5.2", "claude-fable-5.1", "claude-fable-5",
            "claude-opus-5.5", "claude-opus-5", "claude-opus-4.8", "claude-opus-4.8-fast", "claude-sonnet-4.6",
            "claude-haiku-5.5", "claude-haiku-4.5", "gpt-6.1-sol", "gpt-6.1-terra", "gpt-6-sol", "gpt-6-luna",
            "gpt-6-astra", "gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna", "gpt-5.3-codex", "mai-code-1.1-flash",
            "gemini-4-carbon", "gemini-4-argon", "gemini-3.8-flash", "grok-4.7", "grok-4.6", "kimi-k3")

TABLA = {
    "claude-code": (
        # `--model` solo en el arranque de esa conversación, cada vez que se abre con Claude Code (F3 y F6 de la v4)
        {"k": "modelo", "via": "arranque", "flags": ("--model", "{v}"),
         "opciones": (("fable", "Fable"), ("opus", "Opus"), ("sonnet", "Sonnet"))},
        {"k": "esfuerzo", "via": "arranque", "flags": ("--effort", "{v}"),
         "opciones": _niveles("low", "medium", "high", "xhigh", "max")},
    ),
    "codex": (
        {"k": "modelo", "via": "arranque", "flags": ("-m", "{v}"), "al_reanudar": True, "opciones": _CODEX},
        {"k": "esfuerzo", "via": "arranque", "flags": ("-c", "model_reasoning_effort={v}"), "al_reanudar": True,
         "opciones": _niveles(*_TODOS), "por_modelo": {"modelo": _CODEX_NIVELES}},
    ),
    "copilot": (
        {"k": "modelo", "via": "sesion", "comando": "/model {v}",
         "opciones": (("auto", "auto"),) + tuple((s, _bonito(s)) for s in _COPILOT)},
    ),
}


def filas(motor):
    return TABLA.get(motor or "", ())


def fila(motor, k):
    return next((f for f in filas(motor) if f["k"] == k), None)


def valido(motor, k, v):
    """¿`v` es una de SUS opciones? (lo único que llega a su caja o a su línea de arranque)."""
    f = fila(motor, k)
    return bool(f) and isinstance(v, str) and any(o[0] == v for o in f["opciones"])


def etiqueta(motor, k, v):
    f = fila(motor, k)
    return next((o[1] for o in (f or {}).get("opciones", ()) if o[0] == v), v)


def comando(motor, k, v):
    """Lo que se teclea en su sesión («/model sonnet»), o None si ese ajuste no va así o `v` no es suyo."""
    f = fila(motor, k)
    if not f or f["via"] != "sesion" or not valido(motor, k, v):
        return None
    return f["comando"].format(v=v)


def es_comando(texto):
    """¿`texto` es uno de los comandos de sesión de la tabla con un valor suyo («/model sonnet»)? Lo teclea un botón:
    la página no lo pinta como mensaje tuyo ni como turno."""
    t = " ".join(str(texto or "").split())
    for motor in TABLA:
        for f in filas(motor):
            pre = f["comando"].split("{v}")[0] if f["via"] == "sesion" else ""
            if pre and t.startswith(pre) and valido(motor, f["k"], t[len(pre):]):
                return True
    return False


def argumentos(motor, valores, reanuda):
    """(argv para su arranque, {k: v} que van en él) con lo guardado `valores`. Lo que no es suyo se ignora; lo que
    solo va al retomar su sesión (`al_reanudar`) no va si `reanuda` es False."""
    argv, van = [], {}
    for f in filas(motor):
        v = (valores or {}).get(f["k"])
        if f["via"] != "arranque" or not valido(motor, f["k"], v) or (f.get("al_reanudar") and not reanuda):
            continue
        argv += [x.format(v=v) for x in f["flags"]]
        van[f["k"]] = v
    return argv, van


def para_pagina():
    """{motor: [{k, t, via, opciones: [{v, t}], por_modelo?}]}: lo que la página pinta como botones."""
    out = {}
    for motor in TABLA:
        out[motor] = [dict({"k": f["k"], "t": TITULOS[f["k"]], "via": f["via"],
                            "opciones": [{"v": v, "t": t} for v, t in f["opciones"]]},
                           **({"por_modelo": {m: list(n) for m, n in f["por_modelo"]["modelo"].items()}}
                              if f.get("por_modelo") else {}))
                      for f in filas(motor)]
    return out


# ── lo actual, de su pantalla ──
_CC_MODELO = r"((?:Fable|Opus|Sonnet|Haiku)\s+\d+(?:\.\d+)*)"
_CC_MODELO_RE = re.compile(r"◆\s+[^·│\n]+·\s+" + _CC_MODELO + r"|" + _CC_MODELO + r"\s+with\s+\w+\s+effort\b")
_CC_ESFUERZO_RE = re.compile(r"^\s*◉\s+(low|medium|high|xhigh|max)\s+·\s+/effort|\bwith\s+(low|medium|high|xhigh|max)"
                             r"\s+effort\b")
_CODEX_PIE_RE = re.compile(r"^\s*(\S.*?)\s+(default|none|minimal|low|medium|high|xhigh|max|ultra)\s+·\s+Context\b")
PIE_RENGLONES = 4           # Copilot: su modelo solo se busca en su pie (la conversación puede nombrar modelos)


def _de_abajo(pantalla):
    return [l for l in reversed((pantalla or "").splitlines()) if l.strip()]


def _claude_code(lineas):
    out = {}
    for l in lineas:                               # de abajo arriba: el pie y la barra (lo de ahora) antes que el banner
        m = "modelo" not in out and _CC_MODELO_RE.search(l)
        if m:
            t = " ".join((m.group(1) or m.group(2)).split())
            v = t.split()[0].lower()
            out["modelo"] = {"v": v if valido("claude-code", "modelo", v) else None, "t": t}
        e = "esfuerzo" not in out and _CC_ESFUERZO_RE.search(l)
        if e:
            v = e.group(1) or e.group(2)
            out["esfuerzo"] = {"v": v, "t": NIVELES[v]}
        if len(out) == 2:
            break
    return out


def _codex(lineas):
    for l in lineas:
        m = _CODEX_PIE_RE.match(l)
        if m:
            t, nivel = m.group(1).strip(), m.group(2)
            v = re.sub(r"\s+", "-", t.lower())
            return {"modelo": {"v": v if valido("codex", "modelo", v) else None, "t": t},
                    "esfuerzo": {"v": None, "t": "de fábrica"} if nivel == "default"
                    else {"v": nivel if valido("codex", "esfuerzo", nivel) else None, "t": NIVELES.get(nivel, nivel)}}
    return {}


def _copilot(lineas):
    opciones = sorted((o for o, _t in fila("copilot", "modelo")["opciones"] if o != "auto"), key=len, reverse=True)
    for l in lineas[:PIE_RENGLONES]:
        for forma in (l, re.sub(r"\s+", "-", l.lower())):     # su barra trae el id; su pie, el nombre bonito
            v = next((o for o in opciones if re.search(r"(?<![\w.])" + re.escape(o) + r"(?![\w.])", forma)), None)
            if v:
                return {"modelo": {"v": v, "t": _bonito(v)}}
    return {}


_LECTORES = {"claude-code": _claude_code, "codex": _codex, "copilot": _copilot}


def leer(motor, pantalla):
    """{k: {"v": su opción o None, "t": cómo lo dice}} de lo que enseña su pantalla ahora. Lo que no enseña no está
    (la página dice «no se sabe»)."""
    f = _LECTORES.get(motor or "")
    if not f or not pantalla:
        return {}
    try:
        return f(_de_abajo(pantalla))
    except Exception:
        return {}
