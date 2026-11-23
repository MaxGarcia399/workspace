#!/usr/bin/env python3
"""Encargos · lo que la conversación de TRABAJO puede hacer en UN encargo (Fable v2 §2.2, recomendación 1).

Un encargo le lleva a su conversación de trabajo un archivo de verdad del socio (un Excel de un proveedor, un PDF que
le mandaron): contenido que escribieron otros. Por eso el encargo NO hereda el nivel de la página («Automático» corre
comandos sin preguntar): tiene el suyo, el más chico que sirve, y subirlo es una elección del socio en la tarjeta de
ESE encargo.

De fábrica («archivos»):
  · leer y escribir SOLO en la carpeta de ese encargo (deliverables/<proyecto>/), sin tocar los insumos del cliente
    (prefijo «_», como `_insumos/`, donde va la copia del archivo de verdad);
  · leer (sin cambiar) lo que dice quién es y cómo trabaja: BRAIN.md, CLAUDE.md, AGENTS.md, BOOT/ y skills/ (sus
    plantillas). Nada de STATE/ (su memoria, que puede traer de otros clientes), wiki/ ni otras entregas;
  · del núcleo, solo contar su avance, enseñar un archivo, preguntarle al socio y leer sus skills; nada de memoria;
  · sin comandos, sin internet y sin otras herramientas (otros servidores MCP pueden mandar datos fuera).
Con «comandos» (casilla de la tarjeta): también correr comandos (un comando también puede usar internet: la tarjeta
lo dice). Con «internet»: también buscar y leer páginas.

Lo cumple, en Claude Code (el motor donde Workspace lo puede acotar por turno), con tres capas que no dependen del
modelo: `--permission-mode dontAsk` (lo que no está permitido se niega sin preguntar), las reglas del `--settings` del
turno (permitir solo eso, negar comandos e internet) y ESTE aviso de antes de cada herramienta (un «deny» gana sobre
cualquier regla del socio o del cerebro). Las marcas vienen del entorno del turno:
  WORKSPACE_ENCARGO_ID · WORKSPACE_ENCARGO_NIVEL («archivos», «archivos,comandos», …) · WORKSPACE_ENCARGO_ESCRIBE (la
  carpeta del encargo) · WORKSPACE_ENCARGO_CEREBRO (su cerebro).

    python3 encargo_regimen.py          ← el aviso de Claude Code (PreToolUse): el JSON del motor por stdin
Solo stdlib y sin Workspace (corre aunque el harness no esté). Nunca levanta: ante la duda, niega."""
import json
import os
import sys

ENV_ID, ENV_NIVEL, ENV_ESCRIBE, ENV_CEREBRO = ("WORKSPACE_ENCARGO_ID", "WORKSPACE_ENCARGO_NIVEL",
                                              "WORKSPACE_ENCARGO_ESCRIBE", "WORKSPACE_ENCARGO_CEREBRO")
#: Lo que se puede subir, por encargo (las casillas de la tarjeta). «archivos» va siempre.
EXTRAS = ("comandos", "internet")
#: Lo que dice quién es y cómo trabaja (solo leer): su identidad y sus skills (sus plantillas).
LEE_DEL_CEREBRO = ("BRAIN.md", "CLAUDE.md", "AGENTS.md", "BOOT", "skills")
#: Del núcleo de Workspace, lo que un encargo usa sin salir de su carpeta.
NUCLEO = ("reportar_avance", "mostrar_archivo", "preguntar", "skills_lista", "skill_leer", "usar_skill", "tarea_actual")
PREFIJOS_NUCLEO = ("mcp__plugin_workspace_workspace__", "mcp__workspace__")
#: Claude Code: lo que no sale de la conversación (cargar herramientas, su lista de tareas, leer una skill).
INTERNAS = ("ToolSearch", "TodoWrite", "TodoRead", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "Skill")
LEER = ("Read", "Glob", "Grep", "LS", "NotebookRead")
ESCRIBIR = ("Write", "Edit", "MultiEdit", "NotebookEdit")
COMANDOS = ("Bash", "BashOutput", "KillShell", "KillBash")
INTERNET = ("WebFetch", "WebSearch")


def nivel_de(env):
    """{"comandos": bool, "internet": bool} del entorno del turno ("archivos" va siempre)."""
    partes = {p.strip() for p in str((env or {}).get(ENV_NIVEL) or "").split(",")}
    return {k: k in partes for k in EXTRAS}


def es_encargo(env):
    return bool(str((env or {}).get(ENV_ID) or "").strip())


def _real(ruta, base=None):
    r = os.path.expanduser(str(ruta))
    if not os.path.isabs(r):
        r = os.path.join(str(base or os.getcwd()), r)
    return os.path.realpath(r)


def dentro(ruta, carpeta, cwd=None):
    """¿`ruta` cae dentro de `carpeta` (o es ella)? Un enlace que sale, sale. Nunca levanta."""
    try:
        if not ruta or not carpeta:
            return False
        real, base = _real(ruta, cwd or carpeta), os.path.realpath(str(carpeta))
        return real == base or real.startswith(base.rstrip(os.sep) + os.sep)
    except Exception:
        return False


def _insumo(ruta, carpeta, cwd=None):
    """¿Es un insumo del cliente (algo con prefijo «_» dentro de la carpeta del encargo)? Esos no se tocan."""
    try:
        rel = os.path.relpath(_real(ruta, cwd or carpeta), os.path.realpath(str(carpeta)))
        return any(p.startswith("_") for p in rel.split(os.sep) if p not in ("", "."))
    except Exception:
        return True


def puede_leer(ruta, env, cwd=None):
    carpeta, cerebro = (env or {}).get(ENV_ESCRIBE) or "", (env or {}).get(ENV_CEREBRO) or ""
    if dentro(ruta, carpeta, cwd):
        return True
    return bool(cerebro) and any(dentro(ruta, os.path.join(cerebro, x), cwd) for x in LEE_DEL_CEREBRO)


def puede_escribir(ruta, env, cwd=None):
    carpeta = (env or {}).get(ENV_ESCRIBE) or ""
    return dentro(ruta, carpeta, cwd) and not _insumo(ruta, carpeta, cwd) and \
        os.path.realpath(_real(ruta, cwd or carpeta)) != os.path.realpath(str(carpeta))


def _fijo(patron):
    """La parte fija (sin comodines) de un patrón de Glob: «deliverables/x/*.md» → «deliverables/x»; «**/*» → ''."""
    partes = []
    for p in str(patron).replace("\\", "/").split("/"):
        if any(c in p for c in "*?[{"):
            break
        partes.append(p)
    return "/".join(partes)


def _nucleo(nombre):
    for p in PREFIJOS_NUCLEO:
        if nombre.startswith(p):
            return nombre[len(p):]
    return None


def decidir(payload, env):
    """'' si la herramienta pasa en este encargo; si no, por qué se niega (en simple, para el modelo y la bitácora).
    Fuera de un encargo, '' (no es asunto de este aviso). Ante la duda, niega."""
    try:
        if not es_encargo(env):
            return ""
        p = payload if isinstance(payload, dict) else {}
        nombre = str(p.get("tool_name") or "")
        entrada = p.get("tool_input") if isinstance(p.get("tool_input"), dict) else {}
        cwd = p.get("cwd") or (env or {}).get(ENV_ESCRIBE) or ""
        n = nivel_de(env)
        if not nombre:
            return "Workspace no sabe qué herramienta es: en un encargo, no."
        if nombre in INTERNAS:
            return ""
        if nombre in COMANDOS:
            return "" if n["comandos"] else ("En este encargo no corres comandos (el socio no los marcó en su tarjeta). "
                                             "Entrega en texto (.md, .csv o .html) y díselo en tu resumen.")
        if nombre in INTERNET:
            return "" if n["internet"] else "En este encargo no usas internet (el socio no lo marcó en su tarjeta)."
        if nombre in ESCRIBIR:
            ruta = entrada.get("file_path") or entrada.get("notebook_path") or ""
            if puede_escribir(ruta, env, cwd):
                return ""
            return ("En este encargo solo guardas en su carpeta (%s), sin tocar los insumos del cliente (lo que empieza "
                    "con «_»)." % (env or {}).get(ENV_ESCRIBE, ""))
        if nombre in LEER:
            ruta = entrada.get("file_path") or entrada.get("notebook_path") or entrada.get("path") or ""
            patron = str(entrada.get("pattern") or "")
            if not ruta and patron.startswith(("/", "~")):
                ruta = patron
            if not ruta and nombre == "Glob" and patron:
                ruta = _fijo(patron)                    # «deliverables/x/*»: lo fijo del patrón, desde su carpeta (cwd)
            if not ruta:
                ruta = cwd
            if puede_leer(ruta, env, cwd) and not (patron.startswith(("/", "~")) and not puede_leer(patron, env, cwd)):
                return ""
            return ("En este encargo solo lees su carpeta y lo que dice quién eres (BRAIN.md, BOOT/, skills/): ni tu "
                    "memoria ni otras entregas.")
        h = _nucleo(nombre)
        if h is not None:
            return "" if h in NUCLEO else ("En un encargo no se usa «%s» del núcleo (lo leído de un archivo ajeno no "
                                           "va a tu memoria)." % h)
        if nombre.startswith("mcp__"):
            return "" if n["internet"] else "En este encargo no usas otros servidores (pueden mandar datos fuera)."
        if nombre in ("Task", "Agent"):
            return ""                                        # sus herramientas pasan por este mismo aviso
        return "En este encargo no se usa «%s»." % nombre
    except Exception:
        return "Workspace no pudo revisar esta herramienta: en un encargo, no."


def ajustes_claude(carpeta, cerebro, nivel, negar_base=(), hook=None, python=None):
    """El `--settings` del turno de un encargo en Claude Code: permitir solo lo del encargo (en «dontAsk», lo demás se
    niega sin preguntar), negar comandos e internet si no se marcaron, y ESTE aviso antes de cada herramienta."""
    carpeta, cerebro = os.path.realpath(str(carpeta)), os.path.realpath(str(cerebro))

    def abs_(r):
        return "/" + r if r.startswith("/") else r             # «//ruta»: absoluta en las reglas de Claude Code
    permitir = ["Read(%s/**)" % abs_(carpeta), "Edit(%s/**)" % abs_(carpeta), "Write(%s/**)" % abs_(carpeta)]
    for x in LEE_DEL_CEREBRO:
        destino = os.path.join(cerebro, x)
        permitir.append("Read(%s)" % abs_(destino) if x.endswith(".md") else "Read(%s/**)" % abs_(destino))
    permitir += list(INTERNAS) + ["%s%s" % (PREFIJOS_NUCLEO[0], h) for h in NUCLEO]
    negar = list(negar_base)
    negar += ["Edit(%s/_*/**)" % abs_(carpeta), "Edit(%s/_*)" % abs_(carpeta)]
    if nivel.get("comandos"):
        permitir.append("Bash")
    else:
        negar += list(COMANDOS)
    if nivel.get("internet"):
        permitir += list(INTERNET)
    else:
        negar += list(INTERNET)
    negar += ["%s%s" % (PREFIJOS_NUCLEO[0], h) for h in ("memoria_nota", "memoria_checkpoint", "personalizar")]
    out = {"permissions": {"allow": permitir, "deny": [x for i, x in enumerate(negar) if x not in negar[:i]]}}
    if hook:
        out["hooks"] = {"PreToolUse": [{"matcher": "*", "hooks": [
            {"type": "command", "command": "%s %s" % (_comillas(python or sys.executable), _comillas(hook)),
             "timeout": 30}]}]}
    return out


def _comillas(s):
    s = str(s)
    return "'" + s.replace("'", "'\\''") + "'" if any(c in s for c in " '\"$`\\") else s


def main():
    try:
        payload = json.loads((sys.stdin.read() or "{}"))
    except Exception:
        payload = {}
    motivo = decidir(payload, os.environ)
    if motivo:
        sys.stdout.write(json.dumps({"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                                            "permissionDecisionReason": motivo}}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
