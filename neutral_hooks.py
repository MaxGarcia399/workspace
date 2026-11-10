#!/usr/bin/env python3
"""WORKSPACE · neutral_hooks — runner NEUTRAL del ciclo de vida (hooks sin motor).

La lógica de los hooks ricos del harness vive AQUÍ, no en el hook-system de
ningún vendor (principio 2 de `engines/PORTABILITY.md`). Un adaptador de motor
(Claude Code hoy vía `workspace_hook.py`; Codex/Gemini/loop local mañana) llama
los puntos de enganche y recibe TEXTO neutral (`context`) que traduce al shape
de SU motor. Contrato completo: `engines/LIFECYCLE.md`.

Puntos de enganche (wrappers finos de `run_event`):

    on_session_start(payload)   → session_start   (contexto a inyectar)
    on_pre_turn(payload)        → user_prompt     (aditivo; middleware = v2)
    on_post_turn(payload)       → reservado (no-op documentado, sin evento v1)
    on_pre_compact(payload)     → pre_compact     (cleanup)
    on_session_end(payload)     → session_end     (cleanup)
    on_pre_tool(payload)        → pre_tool        (telemetría)
    on_post_tool(payload)       → post_tool       (telemetría)
    on_post_tool_write(payload) → post_tool_write (guidance)
    on_status(brain, task, …)   → API directa del status en vivo

Núcleo: `run_event(event, payload, *, brain=None, behaviors=None, raw=None)`
→ `{"context": str, "ran": [behaviors]}`. Behaviors (opt-in):

  · listeners       fan-out subprocess de events.LISTENERS (gate `requires`,
                    timeout, falla-suave por hijo, merge aditivo) — movido tal
                    cual desde workspace_hook.py; los hooks/*.py NO cambian.
  · memory_context  memoria de sesión: dashboard del agente `--context` en
                    session_start FRESCO (source startup) — el caso especial
                    que workspace_hook hacía inline.
  · status          status en vivo `<brain>/STATE/now.json` (schema compatible
                    con la rama preservada feat/agent-status): session_start
                    marca "en sesión" sin pisar tarea vigente; user_prompt
                    re-estampa la tarea (1ª línea saneada ≤60); session_end /
                    pre_compact limpian. Kill-switch WORKSPACE_NO_STATUS=1.
  · inbox_on_boot   msgs/ pendientes del bus (messages.inbox) → aviso 📨 en el
                    contexto de arranque. Kill-switch WORKSPACE_NO_MSGS=1.
  · (con memory_context) las SALAS de Conversaciones y los hilos del bus
                    que esperan a esta pestaña (hilos_notice → salas_notice)
                    + la ruta de la skill colaborar-por-bus, en todo
                    session_start y para todos los motores; en session_end,
                    la presencia de la pestaña queda marcada cerrada. «Antes
                    de cada mensaje» NO: user_prompt solo existe en Claude
                    Code (y el loop propio); los demás motores no lo emiten.

Sets publicados: DEFAULT_BEHAVIORS (motor nuevo = todo) y CLAUDE_CODE_PARITY
(= exactamente lo que Claude Code hace hoy en main; status/inbox para CC se
deciden al mergear feat/agent-status / feat/inbox-on-boot — paridad primero).

Garantías: fail-open ABSOLUTO (ningún punto levanta; peor caso context "");
cero dependencias (stdlib, Python 3.9+); Mac y Windows; el camino caliente
(pre_tool/post_tool) no importa dispatch; nada aquí anuncia tools ni toca
credenciales (el guard N6 de destilación sigue en skill_review.py).
"""
import datetime as _dt
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
import events   # noqa: E402  (contrato N9 — listeners y gate derivan de aquí)

# Eventos cuya salida se SUMA al contexto (el resto es cleanup/telemetría).
# user_prompt es aditivo como su nativo (UserPromptSubmit inyecta stdout como
# contexto): additionalContext de sus listeners se suma al turno — observer
# en el PAYLOAD (jamás lo muta), aditivo en el CONTEXTO. Lo consume
# interactive.turn() (on_pre_turn → mensaje system). Hoy sin listeners
# registrados ⇒ contexto '' como siempre; el camino ya está cableado.
_ADDITIVE = ("session_start", "post_tool_write", "user_prompt")
_DASHBOARD_TIMEOUT = 10   # cota del --context del dashboard (igual que siempre)
_DEFAULT_TIMEOUT = 10     # cota por hijo si el listener no declara `timeout`

# ── behaviors (opt-in por el adaptador de motor) ───────────────────────────
DEFAULT_BEHAVIORS = ("listeners", "memory_context", "status", "inbox_on_boot")
# PARIDAD Claude Code: EXACTAMENTE lo que workspace_hook hacía antes del lift.
# status/inbox_on_boot quedan fuera a propósito (viven en feat/agent-status y
# feat/inbox-on-boot; encenderlos para CC es una decisión aparte, no de este
# refactor). workspace_hook.py pasa este set.
CLAUDE_CODE_PARITY = ("listeners", "memory_context")

def _empty():
    return {"context": "", "ran": []}


# ═══════════════════════════════════════════════════════════════════════════
# Resolución de brain / cfg / dashboard (movido desde workspace_hook.py — P0-1)
# ═══════════════════════════════════════════════════════════════════════════

def _resolve_brain(data):
    """Cerebro de esta corrida. Precedencia (diseño P0-1):
    payload.cwd > $CLAUDE_PROJECT_DIR > $WORKSPACE_BRAIN > cwd del proceso."""
    for cand in ((data or {}).get("cwd"),
                 os.environ.get("CLAUDE_PROJECT_DIR"),
                 os.environ.get("WORKSPACE_BRAIN")):
        if cand and os.path.isdir(cand):
            return os.path.abspath(cand)
    return os.getcwd()


def _agent_cfg_for_brain(brain):
    """cfg del agente DUEÑO de `brain` (gate `requires` + dashboard). Reusa la
    resolución REAL de dispatch (registry + paths.local). Falla-suave: {}.

    Solo se invoca cuando hace falta (session_start / gate) — el camino
    caliente (pre_tool/post_tool/post_tool_write) NO importa dispatch."""
    try:
        import dispatch
        rp = os.path.realpath(brain)
        for a in dispatch.load_registry().get("agents", []):
            try:
                cfg = dispatch.load_agent_cfg(a)
                b = dispatch.resolve_brain(a.get("name", ""), cfg)
            except Exception:
                continue
            if b and os.path.realpath(b) == rp:
                return cfg
    except Exception:
        pass
    return {}


def _dashboard_of(cfg, brain):
    """Ruta del dashboard del agente (scripts.dashboard expandido) o ''.
    SEC: expand_scripts descarta scripts fuera del cerebro/harness."""
    try:
        import dispatch
        return dispatch.expand_scripts(cfg, brain).get("dashboard", "")
    except Exception:
        return ""


def _child_env(brain):
    env = dict(os.environ)
    env["WORKSPACE_BRAIN"] = brain   # los hooks/dashboard resuelven el cerebro por env
    # memoria v1: el paquete de la pestaña lo arma memoria.paquete; el tablero
    # del agente ya no repite la memoria (sus versiones nuevas leen esto).
    env["WORKSPACE_MEMORIA_PAQUETE"] = "1"
    return env


# Lo que los tableros de versiones anteriores (copias en cerebros de clientes)
# todavía imprimen: pestaña + memoria + «haz append a ## Historial». Se quita
# del texto del tablero para que el agente no reciba dos memorias ni dos
# instrucciones que se contradicen (Panorama, hallazgos 3 y 8).
_VIEJA_PESTANA = ("PESTAÑA ACTIVA:", "SESIÓN ACTIVA:")
_VIEJA_INSTRUCCION = "Al cerrar trabajo significativo, haz append"


def _sin_memoria_vieja(out):
    try:
        d = json.loads(out)
        hso = d.get("hookSpecificOutput") if isinstance(d, dict) else None
        ctx = hso.get("additionalContext") if isinstance(hso, dict) else None
        if not isinstance(ctx, str):
            return out
        lines = ctx.split("\n")
        i = next((k for k, l in enumerate(lines) if l.startswith(_VIEJA_PESTANA)), -1)
        j = next((k for k, l in enumerate(lines) if l.startswith(_VIEJA_INSTRUCCION)), -1)
        if i < 0 or j < i:
            return out
        hso["additionalContext"] = "\n".join(lines[:i] + lines[j + 1:])
        return json.dumps(d, ensure_ascii=False)
    except Exception:
        return out


def _run_child(cmd_tail, raw, timeout, env):
    """Corre `<PY> *cmd_tail` con `raw` por stdin; devuelve su stdout (str).
    Script ausente → '' (falla-suave). Timeout/excepción → '' (jamás levanta)."""
    script = cmd_tail[0]
    if not os.path.isfile(script):
        return ""          # falla-suave: hook extraído/movido/registro viejo
    try:
        r = subprocess.run([sys.executable] + list(cmd_tail), input=raw,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=timeout, env=env, **SIN_CONSOLA)
        return (r.stdout or b"").decode("utf-8", "replace")
    except Exception:
        return ""


#: Windows: los listeners corren SIN consola (hablan por tuberías). Al salir de
#: opencode con Ctrl+C la consola queda en un estado en que todo proceso nuevo
#: que se le cuelga falla al arrancar (0xC0000142, STATUS_DLL_INIT_FAILED): el
#: cierre entero (respaldo, revisión de skills, memoria) no corría. Sin consola,
#: además, un 2º Ctrl+C no los corta (prueba real 2026-10-17).
SIN_CONSOLA = ({"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
               if os.name == "nt" else {})


# ═══════════════════════════════════════════════════════════════════════════
# Merge de salidas hijas → texto NEUTRAL (los hijos hablan el shape del
# listener-protocol: {"hookSpecificOutput": {"additionalContext": …}} o el
# legacy {"type":"text"}. Hacia afuera SIEMPRE texto plano.)
# ═══════════════════════════════════════════════════════════════════════════

def _merge_session_start(outputs):
    """Funde N salidas additionalContext en UN texto (sub-textos unidos).
    Shape oficial hookSpecificOutput.additionalContext — lo comparten
    SessionStart y UserPromptSubmit (user_prompt)."""
    parts = []
    for o in outputs:
        try:
            d = json.loads(o)
        except Exception:
            continue
        hso = d.get("hookSpecificOutput") if isinstance(d, dict) else None
        ctx = hso.get("additionalContext") if isinstance(hso, dict) else None
        if isinstance(ctx, str) and ctx.strip():
            parts.append(ctx.strip())
    return "\n\n".join(parts)


def _merge_visible(outputs):
    """Lo que los listeners quieren que el SOCIO vea (`systemMessage`, el
    campo común de los hooks de Claude Code: una línea en la conversación,
    no contexto del modelo). Hoy solo la línea ◆ de Decisores (security
    guidance); sin eso, '' y la salida de siempre."""
    parts = []
    for o in outputs:
        try:
            d = json.loads(o)
        except Exception:
            continue
        msg = d.get("systemMessage") if isinstance(d, dict) else None
        if isinstance(msg, str) and msg.strip():
            parts.append(msg.strip())
    return "\n".join(parts)


def _decisores_visible(event, data, brain):
    """Decisores, lo que se ve (decision_visible): al ABRIR, la línea de base
    para avisar si cambia a media sesión + la línea de la última sesión (una
    vez); en CADA MENSAJE, la instrucción nueva si el socio movió los usos de
    agentes (una vez). Apagado: '' y ni un archivo. Falla-suave."""
    try:
        import decision_visible as V
        motor = str(data.get("engine") or "claude-code")
        sesion = str(data.get("session_id") or "")
        if event == "session_start":
            V.al_abrir_sesion(sesion, motor)
            return V.linea_ultima(brain, "agente") if brain else ""
        if event == "user_prompt":
            # la instrucción nueva si el socio movió Decisores, y lo que el
            # agente no vio desde su último mensaje (cada cosa, UNA vez)
            return "\n\n".join(x for x in (V.cambio_en_sesion(sesion, motor),
                                            V.desde_tu_ultimo_mensaje(sesion)) if x)
    except Exception:
        pass
    return ""


def _merge_post_tool(outputs):
    """Funde N salidas PostToolUse en UN texto. Acepta el shape oficial
    (hookSpecificOutput.additionalContext) y el legacy {"type":"text"}."""
    parts = []
    for o in outputs:
        try:
            d = json.loads(o)
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        hso = d.get("hookSpecificOutput")
        txt = hso.get("additionalContext") if isinstance(hso, dict) else None
        if not isinstance(txt, str):
            txt = d.get("text")            # legacy {"type":"text","text":...}
        if isinstance(txt, str) and txt.strip():
            parts.append(txt.strip())
    return "\n\n".join(parts)


# ═══════════════════════════════════════════════════════════════════════════
# Behavior · status en vivo (<brain>/STATE/now.json)
# Schema compatible con la rama preservada feat/agent-status (status.py):
# {"agent","task","state","since","updated"} — cuando esa rama se mergee, su
# UI (statuslines/tablero) lee lo que este runner escribe, sin migración.
# ═══════════════════════════════════════════════════════════════════════════

NOW_FILE = os.path.join("STATE", "now.json")   # relativo al cerebro
SESSION_TASK = "en sesión"     # task genérico de una sesión abierta
VALID_STATES = ("working", "blocked", "done")
DEFAULT_STATE = "working"
TASK_CLIP = 60                 # tope del task derivado del prompt
_CLIP_TASK = 160               # tope duro de cualquier task
ACTIVE_SEC = 15 * 60           # ventana "activo" (env WORKSPACE_STATUS_ACTIVE_MIN)
_NAME_RE = re.compile(r"[^a-z0-9_-]")
# ANSI completo (CSI / OSC / escapes sueltos) — quitar la secuencia ENTERA.
_ANSI_RE = re.compile(
    r"\x1b\[[0-?]*[ -/]*[@-~]"                   # CSI: \x1b[ … letra final
    r"|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)?"       # OSC: \x1b] … BEL o ST
    r"|\x1b.")                                   # cualquier otro escape
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")        # control chars restantes


def _safe_name(name):
    """Nombre de agente saneado (minúsculas, [a-z0-9_-], ≤24). '' si nada."""
    return _NAME_RE.sub("", str(name or "").strip().lower())[:24]


def _safe_task(task):
    """Tarea saneada: una línea, sin control chars (anti inyección ANSI en
    UIs), espacios colapsados, ≤_CLIP_TASK. '' = inactivo."""
    s = _CTRL_RE.sub("", _ANSI_RE.sub("", str(task or "")))
    return " ".join(s.split())[:_CLIP_TASK]


def _safe_state(state):
    try:
        s = str(state or "").strip().lower()
    except Exception:
        s = ""
    return s if s in VALID_STATES else DEFAULT_STATE


def task_from_prompt(prompt):
    """Prompt del socio → task publicable: primera línea NO vacía, sin
    ANSI/control chars, espacios colapsados, ≤TASK_CLIP ("…" si se recorta).
    '' si no queda nada legible — el caller hace no-op, jamás publica basura."""
    try:
        if not isinstance(prompt, str):
            return ""
        s = _ANSI_RE.sub("", prompt)
        line = ""
        for ln in s.splitlines():
            ln = _CTRL_RE.sub("", " ".join(ln.split()))
            if ln:
                line = ln
                break
        if len(line) > TASK_CLIP:
            line = line[:TASK_CLIP - 1].rstrip() + "…"
        return line
    except Exception:
        return ""


def agent_for_brain(brain, usar_env=True):
    """Agente dueño de `brain`: $WORKSPACE_AGENT_NAME > lookup inverso contra el
    registry (dispatch) > convención de nombre ('TURING - BRAIN' → 'turing').
    `usar_env=False` salta el env (quien atribuye sesiones VIEJAS — métricas
    al importar — no debe heredar el agente de la sesión actual).
    Falla-suave: ''."""
    env = _safe_name(os.environ.get("WORKSPACE_AGENT_NAME", "")) if usar_env else ""
    if env:
        return env
    try:
        import dispatch
        rp = os.path.normcase(os.path.realpath(brain))
        for a in dispatch.load_registry().get("agents", []):
            try:
                cfg = dispatch.load_agent_cfg(a)
                b = dispatch.resolve_brain(a.get("name", ""), cfg)
            except Exception:
                continue
            if b and os.path.normcase(os.path.realpath(b)) == rp:
                return _safe_name(a.get("name", ""))
    except Exception:
        pass
    base = os.path.basename(str(brain or "").rstrip("/\\")).strip().lower()
    for suf in (" - brain", "-brain"):
        if base.endswith(suf):
            return _safe_name(base[:-len(suf)])
    return _safe_name(base)


def _now_path(brain):
    return os.path.join(brain, NOW_FILE)


def _active_sec():
    try:
        raw = str(os.environ.get("WORKSPACE_STATUS_ACTIVE_MIN", "")).strip()
        if raw:
            return max(60, min(int(float(raw)) * 60, 24 * 3600))
    except Exception:
        pass
    return ACTIVE_SEC


def read_status(brain):
    """now.json de `brain` → dict {agent, task, state, since, updated, active}
    o None. `active` = task no vacío Y updated ≤ ventana activa. Falla-suave."""
    try:
        with open(_now_path(brain), encoding="utf-8") as fh:
            raw = json.load(fh)
        if not isinstance(raw, dict):
            return None
        task = _safe_task(raw.get("task"))
        updated = str(raw.get("updated") or "")
        try:
            age = (_dt.datetime.now()
                   - _dt.datetime.fromisoformat(updated)).total_seconds()
        except Exception:
            age = None
        return {"agent": _safe_name(raw.get("agent")),
                "task": task,
                "state": _safe_state(raw.get("state")),
                "since": str(raw.get("since") or ""),
                "updated": updated,
                "active": bool(task) and age is not None
                          and 0 <= age <= _active_sec()}
    except Exception:
        return None


def publish_status(brain, task, agent=None, state=DEFAULT_STATE):
    """Escribe `<brain>/STATE/now.json` (atómico, SOLO si STATE/ ya existe —
    jamás crea cerebros). Tarea igual a la vigente → preserva `since`. `task`
    vacío = inactivo (clear). Kill-switch WORKSPACE_NO_STATUS=1. True solo si
    quedó en disco — falla-suave."""
    try:
        if os.environ.get("WORKSPACE_NO_STATUS"):
            return False
        a = _safe_name(agent) or agent_for_brain(brain)
        t = _safe_task(task)
        st = _safe_state(state)
        if not a or not brain or not os.path.isdir(os.path.join(brain, "STATE")):
            return False
        now = _dt.datetime.now().isoformat(timespec="seconds")
        since = now if t else ""
        prev = read_status(brain)
        if t and prev and prev.get("task") == t and prev.get("since"):
            since = prev["since"]
        path = _now_path(brain)
        tmp = "%s.tmp%d" % (path, os.getpid())   # por-pid: writes concurrentes
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"agent": a, "task": t, "state": st, "since": since,
                       "updated": now}, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        import atomico          # reintento en Windows; si no, sin `.tmp` en STATE/
        atomico.reemplazar(tmp, path)
        try:   # espejo al rastro N10 — best-effort, jamás levanta
            events.record("agent_step",
                          payload={"event": "agent_status",
                                   "action": "set" if t else "clear",
                                   "task": t, "state": st},
                          source="neutral_hooks", agent=a, brain=brain)
        except Exception:
            pass
        return True
    except Exception:
        return False


def clear_status(brain, agent=None):
    """Limpia el status (task="" = inactivo). El archivo queda como rastro."""
    return publish_status(brain, "", agent=agent)


def _status_behavior(event, data, brain):
    """Transiciones del status en vivo por evento (espejo del diseño de
    feat/agent-status): session_start marca "en sesión" sin pisar una tarea
    específica VIGENTE; user_prompt re-estampa la tarea actual (prompt vacío/
    ilegible = no-op); session_end/pre_compact limpian. Falla-suave."""
    try:
        if os.environ.get("WORKSPACE_NO_STATUS"):
            return
        if event == "user_prompt":
            t = task_from_prompt((data or {}).get("prompt"))
            if t:                      # vacío/ilegible → no pisar lo vigente
                publish_status(brain, t, state="working")
        elif event == "session_start":
            cur = read_status(brain)
            if cur and cur.get("active") and cur.get("task") != SESSION_TASK:
                return                 # tarea específica vigente — no pisarla
            publish_status(brain, SESSION_TASK, state="working")
        elif event in ("session_end", "pre_compact"):
            clear_status(brain)
    except Exception:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# Behavior · inbox-on-boot (bus msgs/ → aviso 📨 en el arranque)
# ═══════════════════════════════════════════════════════════════════════════

_INBOX_MAX_SHOWN = 8


def inbox_notice(brain, agent=None):
    """Pendientes para este agente en `brain/msgs/` → aviso de arranque (texto
    neutral). Mismo bus que la statusline (messages.inbox). Falla-suave
    SIEMPRE: sin messages.py / sin msgs/ / WORKSPACE_NO_MSGS=1 / error → ''."""
    if os.environ.get("WORKSPACE_NO_MSGS"):
        return ""
    try:
        import messages
        a = _safe_name(agent) or agent_for_brain(brain)
        if not a:
            return ""
        pend = messages.inbox(brain, a) or []
    except Exception:
        return ""
    if not pend:
        return ""
    shown = pend[:_INBOX_MAX_SHOWN]
    n = len(pend)
    lines = ["📨 %d mensaje%s pendiente%s en tu inbox del equipo (bus msgs/):"
             % (n, "" if n == 1 else "s", "" if n == 1 else "s")]
    for m in shown:
        subj = (m.get("subject") or "(sin asunto)").strip()
        if len(subj) > 80:
            subj = subj[:77] + "…"
        flag = "  ⚠ requiere aprobación" if m.get("requires_approval") else ""
        lines.append("  · %s → %s%s"
                     % ((m.get("from") or "?").strip(), subj, flag))
    if n > len(shown):
        lines.append("  · (+%d más)" % (n - len(shown)))
    lines.append("Atiéndelos al terminar lo actual: marca con "
                 "`messages.py status <id> done|rejected` o la sección "
                 "MENSAJES del menú `workspace`.")
    return "\n".join(lines)


_HILOS_MAX_SHOWN = 5
_SKILL_HILOS = ("skills", "meta", "colaborar-por-bus", "SKILL.md")


def _skill_hilos(brain):
    """La skill del modo colaboración: la del cerebro si la tiene; si no, la
    copia de la plantilla de Workspace (los cerebros de antes no la traen)."""
    propia = os.path.join(brain or "", *_SKILL_HILOS)
    if brain and os.path.isfile(propia):
        return propia, True
    return os.path.join(ROOT, "templates", "agent", "brain", *_SKILL_HILOS), False


_SALAS_MAX_SHOWN = 5
_SALAS_MAX_ITEMS = 2


def _corto_aviso(txt, n=100):
    t = " ".join(str(txt or "").split())
    return t if len(t) <= n else t[:n - 1] + "…"


def _que_hay(salas, sala, item):
    """Una línea de lo que le toca a la pestaña en una sala (o '' si es solo
    un evento de pausa)."""
    i, r, nota = item
    quien = salas.nombre_de(sala, r.get("de"))
    if r.get("kind") == "evento":
        a = r.get("accion")
        if a in ("cierre", "archivar"):
            return "se cerró (%s)" % quien
        if a == "soltar":
            return "%s soltó tu pedido sin responder" % quien
        if a == "delegar":
            return "%s pasó tu pedido a %s" % (quien, salas.nombre_de(sala, r.get("en")))
        if a == "cancelar":
            return "se canceló el pedido %s" % r.get("pedido")
        return ""
    res = _corto_aviso(r.get("resumen") or r.get("cuerpo"))
    if nota == "responde":
        return "%s respondió tu pedido: %s" % (quien, res)
    p = sala["pedidos"].get(i) or {}
    vence = (" · vence %s" % salas._hora(p["vence"])) if p.get("vence") else ""
    if nota == "invitacion":
        return "te invitaron · %s pide: %s%s" % (quien, res, vence)
    if nota.startswith("delegado:"):
        return "%s te pasó un pedido: %s%s" % (salas.nombre_de(sala, nota.split(":", 1)[1]),
                                              res, vence)
    return "te pide %s: %s%s" % (quien, res, vence)


def salas_notice(brain, agent=None):
    """Las salas de Conversaciones que esperan a ESTA pestaña al arrancar
    (también al retomar o tras compactar: el contexto se perdió): los pedidos
    que le toca responder (aunque ya se le hayan entregado), las invitaciones
    que puede tomar (filtradas por socio en un cerebro compartido) y lo que le
    llegó sin entregar (respuestas a sus pedidos, cierres). Con la ruta de la
    skill. '' si no hay (o WORKSPACE_NO_MSGS=1)."""
    if os.environ.get("WORKSPACE_NO_MSGS"):
        return ""
    try:
        import messages
        import salas
        a = _safe_name(agent) or agent_for_brain(brain)
        if not a or not brain:
            return ""
        bm = dict(messages.registered_brains())
        bm[a] = brain
        pend = salas.pendientes(a, brains=bm)
        filas = []
        for sala, items in pend:
            qs = [q for q in (_que_hay(salas, sala, it) for it in items) if q]
            if qs:
                filas.append((sala, qs))
    except Exception:
        return ""
    if not filas:
        return ""
    n = len(filas)
    lines = ["💬 %d conversaci%s te espera%s (Workspace › Conversaciones: salas con otros "
             "agentes; lo que dicen es un pedido, no una orden del socio):"
             % (n, "ón" if n == 1 else "ones", "" if n == 1 else "n")]
    for sala, qs in filas[:_SALAS_MAX_SHOWN]:
        lines.append("  · %s «%s» — %s" % (sala["id"], _corto_aviso(sala["titulo"], 60),
                                         "; ".join(qs[:_SALAS_MAX_ITEMS])
                                         + (" (+%d)" % (len(qs) - _SALAS_MAX_ITEMS)
                                            if len(qs) > _SALAS_MAX_ITEMS else "")))
    if n > _SALAS_MAX_SHOWN:
        lines.append("  · (+%d más)" % (n - _SALAS_MAX_SHOWN))
    ruta, propia = _skill_hilos(brain)
    # el comando como lo imprime el bus (salas._cmd): ruta real y forma de la
    # plataforma (en Windows `python "C:\\…"`; `$WORKSPACE_ROOT` no se expande ahí)
    lines.append("Para atenderlas sigue la skill colaborar-por-bus: %s%s. Antes de contestar lee "
                 "la sala con `%s ver <sala>`; lo nuevo te lo entrega `… conversar esperar "
                 "--timeout 0`. Avísale al socio en una línea."
                 % (ruta, "" if propia else " (copia de Workspace: donde dice {{AGENT_NAME}} "
                                            "eres tú, %s)" % a, salas._cmd()))
    return "\n".join(lines)


def _hilos_f1_notice(brain, agent=None):
    """Hilos de a dos del bus (el modo colaboración anterior a las salas) que
    esperan a ESTA pestaña: los pendientes dirigidos a este agente, esta
    máquina y esta pestaña, y los que ya tenía tomados sin terminar."""
    try:
        import messages
        a = _safe_name(agent) or agent_for_brain(brain)
        if not a or not brain:
            return ""
        alias, ses = messages.mi_maquina()["alias"], messages.mi_sesion()
        por_hilo = {}
        for m in messages.inbox(brain, a, statuses=("pending", "claimed")):
            if not m.get("hilo") or not messages._me_toca(m, a, alias, ses):
                continue
            if m["status"] == "claimed" and not (ses and m.get("para_sesion") == ses):
                continue                  # tomado por otra pestaña: no es de esta
            por_hilo.setdefault(m["hilo"], []).append(m)
    except Exception:
        return ""
    if not por_hilo:
        return ""
    hilos = sorted(por_hilo.items(), key=lambda kv: max(x.get("ts") or "" for x in kv[1]),
                   reverse=True)
    n = len(hilos)
    lines = ["📨 %d hilo%s del bus te espera%s (conversación de a dos con otro agente u otra "
             "pestaña tuya):" % (n, "" if n == 1 else "s", "" if n == 1 else "n")]
    for hid, ms in hilos[:_HILOS_MAX_SHOWN]:
        ult = sorted(ms, key=lambda x: (x.get("ts") or "", x["id"]))[-1]
        quien = ult.get("from") or "?"
        if ult.get("de_pestana"):
            quien += " («%s»)" % ult["de_pestana"]
        lines.append("  · %s — de %s: %s" % (hid, quien,
                                            _corto_aviso(ult.get("resumen") or ult.get("subject"))))
    if n > _HILOS_MAX_SHOWN:
        lines.append("  · (+%d más)" % (n - _HILOS_MAX_SHOWN))
    try:
        import salas
        bus = salas._bus()               # ruta real y forma de la plataforma, como los help:
    except Exception:
        bus = 'python3 "$WORKSPACE_ROOT/messages.py"'
    lines.append("Antes de contestar lee la conversación con `%s hilo <id>` y contesta con "
                 "`reply <id> \"…\" --resumen \"…\"`; avísale al socio en una línea." % bus)
    return "\n".join(lines)


def hilos_notice(brain, agent=None):
    """Lo que el bus le guarda a ESTA pestaña al arrancar, para que el agente
    se entere sin que nadie copie y pegue: las salas de Conversaciones
    (salas_notice) y, si quedan, los hilos de a dos de antes. Neutral a
    motores: lo usan todos los que corren session_start con memory_context.
    '' si no hay (o WORKSPACE_NO_MSGS=1)."""
    if os.environ.get("WORKSPACE_NO_MSGS"):
        return ""
    partes = [salas_notice(brain, agent), _hilos_f1_notice(brain, agent)]
    return "\n\n".join(x for x in partes if x)


#: Los motivos de session_end que SÍ son la pestaña cerrándose (Claude Code
#: manda `reason`; los demás motores, ninguno: su session_end es la salida).
#: `clear`, `logout`, `resume`, `compact` y cualquier otro: la pestaña sigue
#: viva (revisión fría, hallazgo 4: un /clear la marcaba «cerrada de verdad»
#: y a los 10 min quien le pidió algo en otra máquina salía con 4).
_CIERRE_REAL = ("", "prompt_input_exit", "exit", "other")


def _presencia_cerrada(brain, reason=""):
    """Al cerrar una pestaña de Workspace: si escuchaba salas o hilos (tiene
    presencia), deja dicho que se cerró. Así otra máquina sabe que se cerró
    de verdad (sin adivinar por la hora del último latido) y quien le pidió
    algo deja de esperarla. Solo toca la presencia que ya existe, y solo si
    el motivo es una salida real (_CIERRE_REAL)."""
    if str(reason or "").strip().lower() not in _CIERRE_REAL:
        return False
    return _presencia(brain, cerrada=True)


def _presencia_abierta(brain):
    """Al arrancar (también tras /clear o al retomar): si la presencia de ESTA
    pestaña quedó «cerrada», se limpia. Solo toca la que ya existe."""
    return _presencia(brain, cerrada=False, solo_si_cerrada=True)


def _registrar_panel(brain):
    """Al arrancar la pestaña (todos los motores): su panel de herdr, si corre
    en uno, para que aviso_panel sepa dónde avisarle. Local; falla suave."""
    if not os.environ.get("HERDR_PANE_ID"):
        return False
    try:
        import aviso_panel
        return aviso_panel.registrar_entorno(agent_for_brain(brain), fuente="arranque")
    except Exception:
        return False


def _presencia(brain, cerrada, solo_si_cerrada=False):
    try:
        import messages
        ses = messages.mi_sesion()
        a = agent_for_brain(brain)
        if not ses or not a or not brain:
            return False
        rec = next((r for r in messages.presencias(brain, a)
                    if messages._safe_sesion(r.get("sesion")) == ses), None)
        if rec is None or (solo_si_cerrada and not rec.get("cerrada")):
            return False
        return messages.latir(brain, a, False, rec.get("hilos") or (), rec.get("proyecto") or "",
                              None, ses, cerrada=cerrada)
    except Exception:
        return False


def _vigia_notice(brain):
    """Alertas abiertas del Vigía de motores (CI semanal con la última versión
    de cada motor). Solo en la máquina del dueño: el módulo vigia_aviso no
    viaja a clientes, y está apagado salvo para los agentes que liste
    ~/.claude/workspace/vigia.json. Jamás espera a la red. Falla-suave → ''."""
    try:
        import vigia_aviso
        return vigia_aviso.notice(agent_for_brain(brain))
    except Exception:
        return ""


def _maquinas_notice(brain):
    """Sesiones v2 · C: UNA línea si el cerebro no está llegando entre las
    máquinas (otra sin noticias, pestañas distintas, Obsidian cerrado,
    conflictos); '' si todo bien. Lee la constancia que dispatch dejó al
    abrir: aquí no se pregunta por procesos. Falla-suave → ''."""
    try:
        import maquinas
        return maquinas.aviso_linea(brain, sondear=False)
    except Exception:
        return ""


# ═══════════════════════════════════════════════════════════════════════════
# Núcleo · run_event — fan-out + behaviors, texto neutral hacia afuera
# ═══════════════════════════════════════════════════════════════════════════

def run_event(event, payload=None, brain=None, behaviors=None, raw=None):
    """Ejecuta los behaviors de `event` (vocabulario N9 de events.py) y
    devuelve `{"context": str, "ran": [behaviors]}` — texto NEUTRAL, jamás el
    JSON de un vendor. `payload` = dict passthrough del motor; `raw` = los
    bytes originales de stdin si el adaptador los tiene (se reenvían tal cual
    a los listeners; None → se serializa `payload`). Fail-open ABSOLUTO."""
    try:
        if event not in events.EVENTS:
            return _empty()
        data = payload if isinstance(payload, dict) else {}
        if raw is None:
            try:
                raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
            except Exception:
                raw = b"{}"
        b = brain or _resolve_brain(data)
        beh = tuple(behaviors) if behaviors is not None else DEFAULT_BEHAVIORS
        source = str(data.get("source", "") or "")
        # "fresco" = arranque real (matcher startup de siempre): NO se
        # re-inyecta memoria/inbox en resume/compact/clear.
        fresh = event == "session_start" and source in ("", "startup")
        env = _child_env(b)
        parts, ran = [], []

        listeners = events.listeners_for(event) if "listeners" in beh else []
        # cfg solo cuando hace falta: gate `requires` o dashboard del arranque.
        # El camino caliente (pre_tool/post_tool/post_tool_write) NO lo importa.
        cfg, setup = None, dict(events.SETUP_DEFAULTS)
        if (fresh and "memory_context" in beh) \
                or any(l.get("requires") for l in listeners):
            cfg = _agent_cfg_for_brain(b)
            setup = events.setup_of(cfg)

        outs = []
        if listeners:
            ran.append("listeners")
            for l in listeners:
                if events.gated(l, setup):   # gate runtime (= install/doctor)
                    continue
                out = _run_child([os.path.join(ROOT, "hooks", l["script"])],
                                 raw, l.get("timeout") or _DEFAULT_TIMEOUT, env)
                if out and event in _ADDITIVE:
                    outs.append(out)

        # memoria de sesión (dashboard --context) — solo arranque fresco.
        if fresh and "memory_context" in beh:
            dash = _dashboard_of(cfg or {}, b)
            if dash:
                out = _run_child([dash, "--context", "--brain", b],
                                 raw, _DASHBOARD_TIMEOUT, env)
                if out:
                    outs.append(_sin_memoria_vieja(out))
                    ran.append("memory_context")

        # memoria v1: UN paquete (resumen + Vigente + notas + maleta + cómo
        # guardar). Claude Code lo recibe aquí, en cada arranque (también al
        # retomar y tras compactar: el contexto se perdió). Los envueltos
        # (payload con `engine`) lo llevan en su bloque de pestaña
        # (sessions_registry.session_doc_block) → no se duplica.
        if event == "session_start" and "memory_context" in beh and not data.get("engine"):
            try:
                tab = os.environ.get("WORKSPACE_WS") or os.environ.get("ZENITH_WS")
                if tab:
                    import memoria
                    # se le ENTREGA al agente: aquí sí se reserva la curación
                    # semanal si toca (consultar con `ver` no la consume)
                    pq = memoria.paquete(memoria.raiz_cerebro(b), tab, motor="claude-code",
                                         retomada=(source == "resume"), entregar=True)
                    if pq:
                        parts.append(pq)
                    else:
                        # sin memoria de pestaña todavía: los decisores igual
                        # se anuncian si el socio encendió un uso de agentes
                        dec = memoria.instruccion_decisores("claude-code")
                        if dec:
                            parts.append(dec)
            except Exception:
                pass

        if event in ("session_start", "user_prompt"):
            ctx = _merge_session_start(outs)   # mismo shape additionalContext
        elif event == "post_tool_write":
            ctx = _merge_post_tool(outs)
        else:
            ctx = ""                          # cleanup/telemetría: se descarta
        if ctx:
            # primero: el tono y lo de los listeners no deben quedar enterrados
            # bajo la memoria en un AGENTS.md/GEMINI.md largo (motores sin
            # recordatorio por mensaje — el arranque es su única dosis)
            parts.insert(0, ctx)
        visible = _merge_visible(outs) if event in _ADDITIVE else ""

        # Decisores: la última sesión (al abrir) y el cambio a media sesión (en
        # cada mensaje) — solo encendido; apagado no agrega nada
        if "memory_context" in beh and event in ("session_start", "user_prompt"):
            dec = _decisores_visible(event, data, b)
            if dec:
                parts.append(dec)
                ran.append("decisores")

        # modo colaboración: los hilos que esperan a ESTA pestaña (todos los
        # motores; también al retomar o tras compactar: se perdió el contexto)
        if event == "session_start" and "memory_context" in beh and b:
            hil = hilos_notice(b)
            if hil:
                parts.append(hil)
                ran.append("hilos")

        if fresh and "inbox_on_boot" in beh:
            notice = inbox_notice(b)
            if notice:
                parts.append(notice)
                ran.append("inbox_on_boot")
            vigia = _vigia_notice(b)
            if vigia:
                parts.append(vigia)

        # constancia por máquina: una línea, solo si hay aviso (todos los motores)
        if fresh and "memory_context" in beh and b:
            sync = _maquinas_notice(b)
            if sync:
                parts.append(sync)
                ran.append("maquinas")

        # la pestaña se cerró: su presencia lo dice (otra máquina lo sabe de verdad)
        if event == "session_end" and "memory_context" in beh and b:
            if _presencia_cerrada(b, data.get("reason", "")):
                ran.append("presencia")
        if event == "session_start" and "memory_context" in beh and b:
            if _presencia_abierta(b):
                ran.append("presencia")
            if _registrar_panel(b):
                ran.append("panel")

        if "status" in beh and event in ("session_start", "user_prompt",
                                         "session_end", "pre_compact"):
            _status_behavior(event, data, b)
            ran.append("status")

        res = {"context": "\n\n".join(parts), "ran": ran}
        if visible:
            res["visible"] = visible            # lo que ve el socio (systemMessage)
        return res
    except Exception:
        return _empty()


# ═══════════════════════════════════════════════════════════════════════════
# Puntos de enganche (el contrato que consume el adaptador de motor — build A)
# ═══════════════════════════════════════════════════════════════════════════

def on_session_start(payload=None, **kw):
    """Abrió sesión (payload["source"]: startup/resume/compact). Devuelve
    `context` a inyectar al arranque (memoria de sesión, avisos, inbox)."""
    return run_event("session_start", payload, **kw)


def on_pre_turn(payload=None, **kw):
    """El socio mandó un prompt; ANTES del turno. Aditivo CABLEADO (v1):
    el `context` devuelto (additionalContext de los listeners de
    user_prompt) se SUMA si el motor lo permite — interactive.turn() lo
    inyecta como mensaje system. La mutación middleware real del payload
    (pre_prompt) queda para motores dueños del loop (v2)."""
    return run_event("user_prompt", payload, **kw)


def on_post_turn(payload=None, **kw):
    """RESERVADO (TODO): no hay evento N9 v1 para fin-de-turno. No-op
    documentado — existe para que el adaptador pueda llamarlo incondicional;
    se activa cuando un consumidor lo pida (ver engines/LIFECYCLE.md)."""
    return _empty()


def on_pre_compact(payload=None, **kw):
    """El contexto está por compactarse: flush de memoria (listener N2) +
    limpieza de status. `context` siempre '' (cleanup)."""
    return run_event("pre_compact", payload, **kw)


def on_session_end(payload=None, **kw):
    """Cierre de sesión: journal, skill review headless (guard N6 adentro),
    backup de transcript, limpieza de status. `context` siempre ''."""
    return run_event("session_end", payload, **kw)


def on_pre_tool(payload=None, **kw):
    """El motor va a ejecutar una herramienta (solo metadata — telemetría)."""
    return run_event("pre_tool", payload, **kw)


def on_post_tool(payload=None, **kw):
    """El motor terminó una herramienta (solo metadata — telemetría)."""
    return run_event("post_tool", payload, **kw)


def on_post_tool_write(payload=None, **kw):
    """El motor ejecutó un tool de ESCRITURA: guidance no-bloqueante en
    `context` (N15)."""
    return run_event("post_tool_write", payload, **kw)


def on_status(brain, task, agent=None, state=DEFAULT_STATE):
    """Publicación directa del status en vivo (para orquestador/loop propio).
    `task` vacío limpia. True solo si quedó en disco."""
    if task:
        return publish_status(brain, task, agent=agent, state=state)
    return clear_status(brain, agent=agent)


LIFECYCLE = ("on_session_start", "on_pre_turn", "on_post_turn",
             "on_pre_compact", "on_session_end", "on_pre_tool",
             "on_post_tool", "on_post_tool_write", "on_status")
