#!/usr/bin/env python3
"""Lanzador FIJO del hook de Workspace dentro del paquete de cada motor.

    python3 "<paquete>/lanzador/hook.py" <destino> <momento>

destino = «claude» en el plugin con formato de Claude Code (lo cargan Claude
Code, Copilot, OpenClaw y Antigravity), o el id del motor en los otros formatos.
momento = uno de los 8 del contrato (arquitectura/momentos.json).

El comando no cambia entre versiones (la confianza por huella de Codex): la
lógica vive en el harness, y los hooks del proyecto (Codex, Antigravity: hooks5)
llaman a su copia FIJA, la de arquitectura/sesion.lanzador_fijo. En cada momento (F1):

1. Traduce el JSON del motor a los campos neutrales (traductor.py).
2. Lo anota en el registro de eventos de su pestaña (arquitectura/registro.py):
   el estado en vivo. La pestaña sale de WORKSPACE_BRAIN + WORKSPACE_WID (o
   WORKSPACE_WS) que pone Workspace al abrir; si el motor no hereda el entorno,
   del número de conversación que se guardó al abrir. Sin pestaña, no anota.
3. Si la sesión lo pide (WORKSPACE_PAQUETE_HOOKS=1: el cerebro ya no cablea los
   hooks de hoy por su cuenta), corre el hook neutral de hoy con el evento N9.
   Hoy solo el destino «claude» (el resto: traductor de salida, más adelante).
4. Al abrir (F6), si la sesión la abrió el núcleo (WORKSPACE_NUCLEO_AL_ABRIR o
   WORKSPACE_TONO_SISTEMA en su entorno) y la ficha del motor lo manda por el hook:
   el paquete de la pestaña y el tono, en la forma que su motor lee (salida()).
   El hook de hoy ve esas variables y no lo repite.

5. Antes de cada herramienta (F7), lo prohibido en los 9: leer llaves o secretos (prohibidos.py). Se mira
   primero, aunque no se encuentre Workspace, y se niega: sale con 2 y el motivo en stderr (lo que leen
   Claude Code, Codex, Copilot, Kiro y los que copian su forma) y, en stdout, la forma JSON de su dialecto.
6. Modo escritorio (decisión del dueño, 21-nov): en la conversación del monito (WORKSPACE_VIA=escritorio), Claude Code
   pregunta («ask», su vía oficial: pasa por la tarjeta de la burbuja aunque una regla o su modo lo dejaran) todo lo que
   no es ver, señalar, preguntar, enseñar un archivo, anotar o leer en su carpeta (libres_escritorio.py). Un «deny» gana.
   Y la herramienta de ayudantes (Agent/Task…) se NIEGA ahí, en todos los motores con aviso (ronda 2, E8): lo largo
   es un encargo o sigue en la página.

Si no niega, sale con 0; stdout lleva solo la respuesta para el motor.
"""
import json
import os
import subprocess
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import comun  # noqa: E402
import libres_escritorio as escritorio  # noqa: E402
import prohibidos  # noqa: E402
import traductor  # noqa: E402


class Negado(Exception):
    """El hook niega la herramienta (F7: lo prohibido). `args[0]` es el motivo."""

#: momento neutral → evento N9 de hoy (engines/EVENTS.md). None = aún sin evento.
N9 = {"session_start": "session_start", "user_prompt": "user_prompt",
      "pre_tool": "pre_tool", "post_tool": "post_tool", "permission_request": None,
      "turn_end": "turn_end", "compact": "pre_compact", "session_end": "session_end"}
#: Destinos donde el hook de hoy puede correr (su salida ya es la del motor).
ENCHUFADOS = ("claude",)
TOPE_S = 60


def _correr(raiz, evento, raw):
    try:
        r = subprocess.run([sys.executable, os.path.join(raiz, "workspace_hook.py"), evento],
                           input=raw, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=TOPE_S)
        return r.stdout or b""
    except Exception:
        return b""


def _motor(destino, env):
    return env.get("WORKSPACE_ENGINE", "").strip() or ("claude-code" if destino == "claude" else destino)


def _anotar(raiz, destino, momento, payload, env):
    """El momento al registro de su pestaña. Nunca levanta."""
    try:
        if raiz not in sys.path:
            sys.path.insert(0, raiz)
        from arquitectura import registro
        neutral = traductor.traducir(destino, momento, payload, env)
        sid = neutral.pop("session_id", "")
        brain = env.get("WORKSPACE_BRAIN", "").strip()
        pestana = (env.get("WORKSPACE_WID") or env.get("WORKSPACE_WS") or "").strip()
        via = env.get("WORKSPACE_VIA", "")
        if not (brain and pestana):
            # sin el entorno de la pestaña (un servicio compartido: el servidor de OpenCode, el gateway de OpenClaw):
            # por su número de conversación; el índice dice también si era una conversación de la página
            fila = registro.indice(sid) if hasattr(registro, "indice") else None
            hallada = (fila["brain"], fila["pestana"]) if fila else registro.pestana_de(sid)
            if not hallada:
                return False
            brain, pestana = hallada
            via = (fila or {}).get("via") or via
        motor = env.get("WORKSPACE_ENGINE", "").strip() or destino
        neutral.pop("cwd", None)
        if via in ("pagina", "escritorio"):
            neutral["via"] = "pagina"          # una corrida de la página (o del escritorio): no es su terminal
        ok = registro.anotar(brain, pestana, momento, motor, sid, neutral)
        if ok:                                 # para el doctor: los hooks de este motor llegan (a lo más 1/min)
            from arquitectura import salud
            salud.marcar(motor, "hooks", neutral.get("via") or "terminal", cerebro=brain)
        return ok
    except Exception:
        return False


def _maleta(raiz, destino, env):
    """F5: al cerrar, la maleta de este motor desde los eventos de su pestaña (arquitectura/maleta), sin IA. Las
    corridas de la página tienen la suya. Nunca levanta."""
    try:
        brain = env.get("WORKSPACE_BRAIN", "").strip()
        pestana = (env.get("WORKSPACE_WID") or env.get("WORKSPACE_WS") or "").strip()
        tab = env.get("WORKSPACE_WS", "").strip()
        if not (brain and pestana and tab) or env.get("WORKSPACE_VIA") in ("pagina", "escritorio"):
            return False                   # sin la pestaña: la rehace el próximo arranque (maleta.al_abrir)
        if raiz not in sys.path:
            sys.path.insert(0, raiz)
        from arquitectura import maleta
        motor = env.get("WORKSPACE_ENGINE", "").strip() or destino
        # hooks5 y cierre de la auditoría: su maleta sigue saliendo de lo de hoy (solo sus hooks, o sus avisos no dan
        # tu mensaje o su respuesta: maleta.maleta_de_hoy)
        if getattr(maleta, "maleta_de_hoy", maleta.solo_hooks)(motor):
            return False
        return maleta.escribir(brain, pestana, tab, motor)
    except Exception:
        return False


def al_abrir(raiz, destino, payload, env):
    """El texto que el núcleo entrega en el hook de inicio de esta sesión ('' si nada va por aquí)."""
    if not (env.get("WORKSPACE_NUCLEO_AL_ABRIR") or env.get("WORKSPACE_TONO_SISTEMA")):
        return ""                                  # la sesión no la abrió el núcleo: lo de hoy
    brain = env.get("WORKSPACE_BRAIN", "").strip()
    tab = env.get("WORKSPACE_WS", "").strip()
    if not brain:
        return ""
    try:
        if raiz not in sys.path:
            sys.path.insert(0, raiz)
        from arquitectura import nucleo
        source = traductor.traducir(destino, "session_start", payload, env).get("source") or "startup"
        return nucleo.al_abrir_por_hook(brain, tab, _motor(destino, env), source)
    except Exception:
        return ""


def salida(destino, texto, previa=b""):
    """El texto al modelo en el hook de inicio, como lo lee cada dialecto (ficha · session_start ·
    inyectar), junto a lo que ya devolvió el hook de hoy (`previa`)."""
    if not texto:
        return previa
    if destino == "kiro":                          # su stdout va al contexto
        return (previa.rstrip() + b"\n\n" if previa.strip() else b"") + texto.encode("utf-8")
    if destino == "cursor":
        return json.dumps({"additional_context": texto}, ensure_ascii=False).encode("utf-8")
    if destino in ("claude", "codex"):             # hookSpecificOutput (Claude Code; Codex copia su forma)
        data = {}
        try:
            data = json.loads(previa.decode("utf-8")) if previa.strip() else {}
        except (ValueError, UnicodeDecodeError):
            data = {}
        data = data if isinstance(data, dict) else {}
        hso = data.get("hookSpecificOutput") if isinstance(data.get("hookSpecificOutput"), dict) else {}
        antes = str(hso.get("additionalContext") or "").strip()
        hso.update(hookEventName="SessionStart", additionalContext=(antes + "\n\n" + texto) if antes else texto)
        data["hookSpecificOutput"] = hso
        return json.dumps(data, ensure_ascii=False).encode("utf-8")
    return previa


def _entorno_hermes(payload, momento, env):
    """cable-hermes: Hermes corre los avisos de su perfil en su gateway multiplexado, con el entorno de la pestaña
    que lo arrancó (otra). Este lanzador vive en el perfil del agente (workspace-paquete/lanzador/): el cerebro y la
    raíz de Workspace salen de su perfil.json, y la pestaña, de la dueña de la sesión (engines/hermes.entorno_de_aviso).
    → (entorno, anotar). Sin perfil.json o si algo falla: no anota (lo prohibido ya se miró antes)."""
    try:
        aqui = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        with open(os.path.join(aqui, "perfil.json"), encoding="utf-8") as fh:
            pj = json.load(fh)
        raiz = str(pj.get("raiz") or "")
        if not raiz or not os.path.isfile(os.path.join(raiz, "engines", "hermes.py")):
            return env, False
        if raiz not in sys.path:
            sys.path.insert(1, raiz)
        from engines import hermes as _h
        return _h.entorno_de_aviso(payload, pj, momento, env)
    except Exception:
        return env, False


def marcar_en_uso(archivo=None):
    """La carpeta de esta versión del paquete queda «en uso» (su fecha), para que la poda de versiones viejas
    (arquitectura/sesion._podar) no la borre mientras una sesión abierta la carga: sus hooks y su MCP la llaman
    en cada evento. Solo la del estado de Workspace (…/arquitectura/paquete/<versión>). Nunca levanta."""
    try:
        version = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(archivo or __file__))))
        if os.path.basename(os.path.dirname(version)) == "paquete":
            os.utime(version)
            return version
    except OSError:
        pass
    return ""


def preguntar_en_escritorio(destino, payload, env, previa=b""):
    """Modo escritorio en Claude Code: lo que no es libre en el monito pregunta («ask»), junto a lo que ya devolvió el
    hook de hoy (un «deny» suyo gana). `previa` tal cual si no toca."""
    if destino != "claude" or (env.get("WORKSPACE_ENGINE") or "claude-code").strip() != "claude-code":
        return previa
    motivo = escritorio.claude_pregunta(payload, env)
    if not motivo:
        return previa
    try:
        data = json.loads(previa.decode("utf-8")) if previa.strip() else {}
    except (ValueError, UnicodeDecodeError):
        data = {}
    data = data if isinstance(data, dict) else {}
    hso = data.get("hookSpecificOutput") if isinstance(data.get("hookSpecificOutput"), dict) else {}
    if hso.get("permissionDecision") == "deny" or data.get("decision") in ("block", "deny"):
        return previa
    hso.update(hookEventName="PreToolUse", permissionDecision="ask", permissionDecisionReason=motivo)
    data["hookSpecificOutput"] = hso
    return json.dumps(data, ensure_ascii=False).encode("utf-8")


def main(argv, env=None):
    env = os.environ if env is None else env
    try:
        raw = sys.stdin.buffer.read() or b""     # siempre: el motor no debe ver la tubería rota
    except Exception:
        raw = b""
    if len(argv) < 2 or argv[1] not in N9:
        return b""
    destino, momento = argv[0], argv[1]
    if momento in ("session_start", "user_prompt"):
        marcar_en_uso()
    try:
        payload = json.loads(raw.decode("utf-8-sig") or "{}")
    except ValueError:
        payload = {}
    if momento == "pre_tool":
        motivo = prohibidos.motivo(payload, env)
        if motivo:
            raise Negado("Workspace no deja leer %s desde un agente." % motivo)
        cambio = prohibidos.motivo_escribir(payload, env)
        if cambio:
            raise Negado("Workspace no deja cambiar %s desde un agente: eso se cambia en el menú de Compañero." % cambio)
        ayudantes = escritorio.sin_ayudantes(payload, env)
        if ayudantes:                       # monito ronda 2 (E8): en el monito no hay ayudantes
            raise Negado(ayudantes)
    if destino == "hermes":
        env, anotar = _entorno_hermes(payload, momento, env)
        if not anotar:
            return b""
    raiz = comun.raiz_workspace(os.path.join("arquitectura", "registro.py"), env)
    if not raiz:
        return preguntar_en_escritorio(destino, payload, env) if momento == "pre_tool" else b""
    _anotar(raiz, destino, momento, payload, env)
    if momento == "session_end":
        _maleta(raiz, destino, env)
    texto = al_abrir(raiz, destino, payload, env) if momento == "session_start" else ""
    if destino not in ENCHUFADOS or not N9[momento] or env.get("WORKSPACE_PAQUETE_HOOKS") != "1":
        out = salida(destino, texto)
        return preguntar_en_escritorio(destino, payload, env, out) if momento == "pre_tool" else out
    out = _correr(raiz, N9[momento], raw)
    if momento == "pre_tool":
        out = preguntar_en_escritorio(destino, payload, env, out)
    herramienta = traductor.traducir(destino, momento, payload, env).get("tool_name")
    if momento == "post_tool" and herramienta in traductor.ESCRITURA:
        out = _correr(raiz, "post_tool_write", raw) or out
    return salida(destino, texto, out)


if __name__ == "__main__":
    codigo = 0
    try:
        salida = main(sys.argv[1:])
        if salida:
            sys.stdout.buffer.write(salida)
    except Negado as n:
        codigo = 2      # lo prohibido: niega (stderr = el motivo que ve el modelo)
        try:
            forma = prohibidos.negar(sys.argv[1] if len(sys.argv) > 1 else "", n.args[0])
            if forma:
                sys.stdout.buffer.write(json.dumps(forma, ensure_ascii=False).encode("utf-8"))
            sys.stderr.write(n.args[0] + "\n")
        except Exception:
            pass
    except Exception:
        pass            # falla abierto: el hook jamás frena al motor (salvo lo prohibido)
    sys.exit(codigo)
