#!/usr/bin/env python3
"""WORKSPACE · arquitectura/contrato — carga y valida los datos de F0.

  · momentos.json    el contrato de los 8 momentos del hook
  · mcp_nucleo.json  la lista del MCP núcleo
  · fichas/*.json    una ficha por motor, contra ficha.esquema.json

El validador es un subconjunto de JSON Schema (type, enum, required,
properties, additionalProperties, items, min/max, pattern, $ref local):
cero dependencias. `tabla_momentos()` arma la tabla de engines/EVENTS.md desde
las fichas (una prueba cuida que el documento no se aleje de los datos).

CLI:  python3 -m arquitectura.contrato            valida todo; sale 1 si algo falla
      python3 -m arquitectura.contrato --tabla    imprime la tabla de los momentos
"""
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
FICHAS = os.path.join(AQUI, "fichas")
ESQUEMA = os.path.join(AQUI, "ficha.esquema.json")
#: Los 9 motores, en el orden de las tablas del plan.
MOTORES = ("claude-code", "codex", "copilot", "cursor", "kiro", "antigravity",
           "opencode", "openclaw", "hermes")
#: Lo que el MCP núcleo NO lleva en F0 (otra actualización).
FUERA_DEL_NUCLEO = ("sala", "decid", "decisor")


def cargar(nombre):
    with open(os.path.join(AQUI, nombre), encoding="utf-8") as fh:
        return json.load(fh)


def momentos():
    return cargar("momentos.json")


def nombres_momentos():
    return tuple(m["nombre"] for m in momentos()["momentos"])


def mcp_nucleo():
    return cargar("mcp_nucleo.json")


def esquema():
    with open(ESQUEMA, encoding="utf-8") as fh:
        return json.load(fh)


def ficha(motor, carpeta=None):
    with open(os.path.join(carpeta or FICHAS, motor + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def sin_via(sesion, sistema=None):
    """Por qué la vía por sesión de una ficha no va en este sistema ('' si va): su «no», o el de `no_en` para este
    sistema (os.name; cable-kiro: Kiro en Windows, sin verificar con qué shell corre sus hooks)."""
    s = sesion or {}
    return s.get("no") or (s.get("no_en") or {}).get(sistema or os.name) or ""


def fichas(carpeta=None):
    """{motor: ficha} de las 9, en el orden de MOTORES."""
    return {m: ficha(m, carpeta) for m in MOTORES}


# ── validador (subconjunto de JSON Schema) ─────────────────────────────────
_TIPOS = {"object": dict, "array": list, "string": str, "boolean": bool, "null": type(None)}


def _es_tipo(valor, tipo):
    if tipo == "integer":
        return isinstance(valor, int) and not isinstance(valor, bool)
    if tipo == "number":
        return isinstance(valor, (int, float)) and not isinstance(valor, bool)
    return isinstance(valor, _TIPOS[tipo])


def validar(valor, sch, raiz=None, ruta="$"):
    """Lista de errores («ruta: qué») de `valor` contra `sch`; vacía = válido."""
    raiz = raiz if raiz is not None else sch
    if "$ref" in sch:
        destino = raiz
        for parte in sch["$ref"].lstrip("#/").split("/"):
            destino = destino[parte]
        return validar(valor, destino, raiz, ruta)
    errs = []
    if "type" in sch:
        tipos = sch["type"] if isinstance(sch["type"], list) else [sch["type"]]
        if not any(_es_tipo(valor, t) for t in tipos):
            return ["%s: se esperaba %s" % (ruta, "|".join(tipos))]
    if "enum" in sch and valor not in sch["enum"]:
        errs.append("%s: %r no es uno de %s" % (ruta, valor, sch["enum"]))
    if isinstance(valor, str):
        if len(valor) < sch.get("minLength", 0):
            errs.append("%s: muy corto" % ruta)
        if "maxLength" in sch and len(valor) > sch["maxLength"]:
            errs.append("%s: muy largo" % ruta)
        if "pattern" in sch and not re.search(sch["pattern"], valor):
            errs.append("%s: %r no cumple %s" % (ruta, valor, sch["pattern"]))
    if isinstance(valor, (int, float)) and not isinstance(valor, bool):
        if "minimum" in sch and valor < sch["minimum"]:
            errs.append("%s: menor que %s" % (ruta, sch["minimum"]))
        if "maximum" in sch and valor > sch["maximum"]:
            errs.append("%s: mayor que %s" % (ruta, sch["maximum"]))
    if isinstance(valor, list):
        if len(valor) < sch.get("minItems", 0):
            errs.append("%s: menos de %d elementos" % (ruta, sch["minItems"]))
        if "maxItems" in sch and len(valor) > sch["maxItems"]:
            errs.append("%s: más de %d elementos" % (ruta, sch["maxItems"]))
        if "items" in sch:
            for i, v in enumerate(valor):
                errs += validar(v, sch["items"], raiz, "%s[%d]" % (ruta, i))
    if isinstance(valor, dict):
        props = sch.get("properties", {})
        for k in sch.get("required", ()):
            if k not in valor:
                errs.append("%s: falta %s" % (ruta, k))
        extra = sch.get("additionalProperties", True)
        for k, v in valor.items():
            if k in props:
                errs += validar(v, props[k], raiz, "%s.%s" % (ruta, k))
            elif extra is False:
                errs.append("%s: sobra %s" % (ruta, k))
            elif isinstance(extra, dict):
                errs += validar(v, extra, raiz, "%s.%s" % (ruta, k))
    return errs


# ── reglas de F0 ───────────────────────────────────────────────────────────
def errores_ficha(f, motor=None):
    """Esquema + coherencia: el nombre de archivo es el motor; un momento con
    estado si/parcial nombra al menos un evento oficial."""
    errs = validar(f, esquema())
    if errs:
        return errs
    if motor and f["motor"] != motor:
        errs.append("$.motor: %r no es %r (nombre del archivo)" % (f["motor"], motor))
    for nombre, m in f["momentos"].items():
        if m["estado"] in ("si", "servidor") and not m["eventos"]:
            errs.append("$.momentos.%s: estado %s sin evento oficial" % (nombre, m["estado"]))
    n = f["nucleo"]
    if n["chat"]["via"] == "argv" and (n["tono"]["via"] != "argv" or not n["tono"].get("argv")):
        errs.append("$.nucleo.chat: la guía por argv va con el tono, y su tono no va por argv")
    return errs + errores_real(f) + errores_sesion(f) + errores_peligrosos(f)


def errores_sesion(f):
    """La vía por sesión del lanzamiento: argumentos o archivos en el proyecto (nada
    en {home}), un perfil propio en el proyecto (cable-kiro) o del motor por agente (cable-hermes: `perfil_agente`
    + `preparar`), o «no» con la razón; no las dos."""
    s = f.get("sesion") or {}
    errs = []
    if bool(s.get("argv") or s.get("archivos") or s.get("perfil")) == ("no" in s):
        errs.append("$.sesion: o argv/archivos/perfil o no, una de las dos")
    if bool(s.get("perfil_agente")) != bool(s.get("preparar")):
        errs.append("$.sesion: perfil_agente y preparar van juntos (quién arma el perfil del agente)")
    if any("{home}" in a for a in s.get("argv") or ()):
        errs.append("$.sesion.argv: nada de {home}: solo por sesión")
    for i, paso in enumerate(s.get("archivos") or []):
        if "correr" in paso or not str(paso.get("a", "")).startswith("{cerebro}/"):
            errs.append("$.sesion.archivos[%d]: solo se copia a {cerebro}/" % i)
    return errs


def errores_real(f):
    """--home-real: la vía por sesión de la ficha nunca escribe fuera del proyecto
    temporal ni corre un instalador. Trae corrida o «no» con la razón, no las dos."""
    real = f["probador"].get("real")
    if real is None:
        return ["$.probador.real: falta (la vía por sesión, o «no» con la razón)"]
    errs = []
    if ("corrida" in real) == ("no" in real):
        errs.append("$.probador.real: o corrida o no, una de las dos")
    for i, paso in enumerate(real.get("preparar") or []):
        if "correr" in paso:
            errs.append("$.probador.real.preparar[%d]: con el HOME real no se corre nada" % i)
        dst = paso.get("a") or paso.get("escribir") or ""
        if not dst.startswith("{cerebro}/"):
            errs.append("$.probador.real.preparar[%d]: solo se escribe en {cerebro}/" % i)
    return errs


def errores_peligrosos(f):
    """Ninguna corrida del probador (real o aislada) usa un flag `--dangerously-*`
    (encargo arq-hooks: si el motor lo exige, se busca la vía de confianza
    oficial; si no la hay, se marca y no se usa)."""
    pr = f["probador"]
    errs = []
    for donde, argv in (("corrida", pr.get("corrida")), ("real.corrida", (pr.get("real") or {}).get("corrida"))):
        for a in argv or []:
            if isinstance(a, str) and a.startswith("--dangerously"):
                errs.append("$.probador.%s: %s no se usa" % (donde, a))
    return errs


def errores_momentos():
    errs = []
    data = momentos()
    nombres = [m["nombre"] for m in data["momentos"]]
    if len(nombres) != 8 or len(set(nombres)) != 8:
        errs.append("momentos: tienen que ser 8 y distintos")
    import events                                  # el vocabulario N9 de hoy
    for m in data["momentos"]:
        if m["n9"] is not None and m["n9"] not in events.EVENTS:
            errs.append("momentos.%s: n9 %r no está en events.EVENTS" % (m["nombre"], m["n9"]))
        for s in m["devuelve"]:
            if s not in data["salidas"]:
                errs.append("momentos.%s: salida %r sin definir" % (m["nombre"], s))
    return errs


def errores_mcp():
    errs = []
    data = mcp_nucleo()
    vistos = set()
    for h in data["herramientas"]:
        n = h["nombre"]
        if not re.match(r"^[a-z][a-z0-9_]{2,40}$", n) or n in vistos:
            errs.append("mcp.%s: nombre inválido o repetido" % n)
        vistos.add(n)
        if any(p in n for p in FUERA_DEL_NUCLEO):
            errs.append("mcp.%s: salas y decisores van fuera de F0" % n)
        ent = h.get("entrada", {})
        if ent.get("type") != "object" or ent.get("additionalProperties") is not False:
            errs.append("mcp.%s: la entrada es un objeto cerrado" % n)
        for c in ent.get("required", ()):
            if c not in ent.get("properties", {}):
                errs.append("mcp.%s: requiere %s sin definirlo" % (n, c))
        for e in h.get("errores", ()):
            if e not in data["errores"]:
                errs.append("mcp.%s: error %s sin definir" % (n, e))
        if not h.get("reemplaza") or not h.get("salida"):
            errs.append("mcp.%s: falta salida o qué reemplaza" % n)
    # el plan dijo «unas 10»; el modo chat (19-nov) sumó mostrar_archivo: el tope sube poco, la lista sigue corta
    if not 6 <= len(vistos) <= 14:
        errs.append("mcp: unas 10 herramientas, 14 a lo más (hay %d)" % len(vistos))
    return errs


def errores(carpeta=None):
    """Todo F0 de una vez: momentos, MCP y las 9 fichas."""
    errs = errores_momentos() + errores_mcp()
    for m in MOTORES:
        errs += ["fichas/%s.json %s" % (m, e) for e in errores_ficha(ficha(m, carpeta), m)]
    return errs


# ── la tabla de engines/EVENTS.md ──────────────────────────────────────────
_ESTADO = {"si": "", "parcial": " (parcial)", "sin_doc": " (sin doc)", "no": "no",
           "herdr": "lo ve herdr", "servidor": " (por servidor)"}


def _celda(m):
    eventos = " · ".join("`%s`" % e for e in m["eventos"])
    if not eventos:
        return _ESTADO[m["estado"]].strip(" ()") or "—"
    return eventos + _ESTADO[m["estado"]]


def tabla_momentos(carpeta=None):
    fs = fichas(carpeta)
    filas = ["| Momento | " + " | ".join(fs[m]["nombre"] for m in MOTORES) + " |",
             "|---|" + "---|" * len(MOTORES)]
    for mo in momentos()["momentos"]:
        celdas = [_celda(fs[m]["momentos"][mo["nombre"]]) for m in MOTORES]
        filas.append("| `%s` (%s) | %s |" % (mo["nombre"], mo["etiqueta"], " | ".join(celdas)))
    return "\n".join(filas)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if "--tabla" in argv:
        print(tabla_momentos())
        return 0
    errs = errores()
    for e in errs:
        print("✗ " + e)
    print("✓ contrato F0 válido" if not errs else "✗ %d errores" % len(errs))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(AQUI))
    sys.exit(main())
