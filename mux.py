#!/usr/bin/env python3
"""WORKSPACE · mux — terminal PARTIDA sobre tmux (opt-in).

NOTA (F1 herdr): mux.py es el BACKEND TMUX del split. La selección de
backend (tmux | herdr, setting `ui.split_backend`) vive en multiplexer.py —
las puertas de entrada (front.launch con ui.split ON y `workspace split`)
entran por multiplexer.open_split(), que delega aquí cuando el backend
efectivo es tmux. Este módulo NO conoce herdr; su flujo (split) queda
idéntico al de siempre.

`workspace split [agente]` abre UNA ventana tmux con DOS panes lado a lado:

  ┌──────────────────────────┬────────────────────┐
  │  chat del agente         │  pipeline en vivo  │
  │  (claude --resume <wid>) │  (workspace wf board)│
  └──────────────────────────┴────────────────────┘

La IZQUIERDA es exactamente el arranque de siempre — `dispatch.py <agente>
--open <wid> --name <ws> --no-banner` (el camino directo que ya soporta
`preselect` en engines/claude_code.py) — así que identidad, env de sesión y
resume NO se reimplementan. La DERECHA corre el tablero de workflows en vivo
(`wf board`, front.py), que re-pinta en sitio y es responsivo → perfecto para
un pane angosto.

Desarchivado de _shelved/mux.py (el hub multi-VENTANA, Nivel 2) y adaptado a
dos PANES en una sola ventana. OPT-IN: el arranque default (`workspace` → hub,
`<agente>` → handoff por exec) no cambia en nada.

DOS puertas de entrada, MISMO armado:
  · `workspace split [agente]`   — el subcomando manual de siempre.
  · `settings set ui.split on` — el hub (front.launch) enruta por aquí
    DESPUÉS de que el socio eligió agente en el menú: todo chat lanzado
    desde el hub abre ya partido. El hub/menú mismos JAMÁS pasan por tmux
    (corren antes y fuera); con el setting off (default) el hub ni importa
    este módulo.

El pane derecho es una SUPERFICIE EXTENSIBLE: qué corre ahí lo decide un
solo punto (right_pane_cmd) — hoy la pipeline, mañana un panel de control
con pestañas (pipeline/bus/config/delegar).

Degradación grácil (jamás rompe el arranque):
  · sin tmux instalado          → aviso + arranque normal de siempre
  · sin TTY (pipe/automation)   → aviso + arranque normal
  · ya dentro de tmux           → aviso + arranque normal (sin anidar)
  · Windows                     → sesión sencilla (asunción de ARCHITECTURE.md)

Subcomando:
  split [agente] [--right N] [--plan] [--pick]
    --right N   ancho del pane derecho en % (20–60; default 42)
    --plan      imprime los comandos tmux sin ejecutar nada
    --pick      fuerza el picker de workspaces (ignora la sesión más reciente)

Cero dependencias (stdlib, Python 3.9+).
"""
import sys, os, subprocess, shutil, signal, time

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable or "python3"
DISPATCH = os.path.join(ROOT, "dispatch.py")
FRONT = os.path.join(ROOT, "front.py")

SESSION_PREFIX = "workspace-split"    # una sesión por workspace (dedupe por nombre)
HERDR = "herdr"                     # el binario (el controlador tumba la sesión al salir)
RIGHT_PCT_DEF = 50                  # ancho del pane derecho (%): el PANEL (menú) pide
                                    # más aire que el board pelón — mitad y mitad
                                    # (pedido del socio: "más grande"). Ajustable --right.
RIGHT_PCT_MIN, RIGHT_PCT_MAX = 20, 60
BOARD_RESPAWN_S = 3                 # el board sale cuando nada corre → re-lanzarlo
# Anti-spin del controlador (idle-fix): si el chat muere INESPERADO (rc!=0)
# N veces seguidas dentro de una ventana de T s, dejamos de relanzar y hacemos
# teardown — así un Claude Code que crashea al instante no queda en hot-loop.
UNEXPECTED_MAX = 3                  # muertes inesperadas seguidas...
UNEXPECTED_WINDOW_S = 20           # ...dentro de esta ventana (s) → teardown


def _q(s):
    s = str(s)
    return "'" + s.replace("'", "'\\''") + "'" if (" " in s or "\t" in s or "'" in s) else s


class Tmux:
    """Ejecutor mínimo de tmux con modo --plan (imprime en vez de correr)."""

    def __init__(self, plan=False):
        self.plan = plan

    def run(self, args):
        if self.plan:
            print("  [plan] tmux " + " ".join(_q(a) for a in args))
            return 0
        return subprocess.run(["tmux"] + args).returncode


def have_tmux():
    return shutil.which("tmux") is not None


def inside_tmux():
    return bool(os.environ.get("TMUX"))


def session_exists(session):
    return subprocess.run(["tmux", "has-session", "-t", session],
                          capture_output=True).returncode == 0


def parse_args(argv):
    """(agente, right_pct, plan, force_pick) de la CLI. Valores malos →
    default con clamp; jamás revienta (mismo espíritu que _wf_board_args).

    NOTA (aridad): pasó de 3-tupla a 4-tupla al ganar `--pick`. Los callers
    por índice (`parse_args(...)[0]`, p.ej. multiplexer.open_split) siguen
    válidos; el unpack de 3 en multiplexer.herdr_split se actualiza en el
    chunk 2 del rediseño del split."""
    agent, pct, plan, force_pick = "", RIGHT_PCT_DEF, False, False
    i = 0
    while i < len(argv or []):
        a = argv[i]
        if a == "--plan":
            plan = True
        elif a == "--pick":
            force_pick = True
        elif a == "--right" and i + 1 < len(argv):
            try:
                pct = int(argv[i + 1])
            except ValueError:
                pass
            i += 1
        elif not a.startswith("-") and not agent:
            agent = a
        i += 1
    return agent, max(RIGHT_PCT_MIN, min(RIGHT_PCT_MAX, pct)), plan, force_pick


def default_agent():
    """Si hay EXACTAMENTE un agente registrado, ése es el default obvio.
    Con varios (o registry ilegible) → '' y el caller pide el nombre."""
    try:
        import dispatch as _dispatch
        agents = (_dispatch.load_registry() or {}).get("agents") or []
        if len(agents) == 1:
            return str(agents[0].get("name") or "")
    except Exception:
        pass
    return ""


def session_name(ws_name):
    """Nombre de sesión tmux derivado del workspace (dedupe: mismo workspace →
    misma sesión → reconectar, no duplicar)."""
    slug = "".join(c if (c.isalnum() or c in "-_") else "-"
                   for c in str(ws_name).strip().lower()).strip("-") or "ws"
    return SESSION_PREFIX + "-" + slug


def pick(agent, plan=False):
    """Menú de pestañas del agente (visual a la terminal) → (wid, name) o None.
    Es el MISMO picker del arranque normal (dispatch --pick-only). En modo
    plan no abre nada: devuelve una selección de ejemplo."""
    if plan:
        return ("<wid>", "<workspace-elegido>")
    r = subprocess.run([PY, DISPATCH, agent, "--pick-only"],
                       stdout=subprocess.PIPE, text=True,
                       encoding="utf-8", errors="replace")
    parts = (r.stdout or "").strip().split("\t")
    if len(parts) >= 3 and parts[0] == "WS":
        return parts[1], parts[2]
    return None


def default_session(agent):
    """(wid, name) de la sesión MÁS RECIENTE del agente, o None (falla-suave
    total: cualquier tropiezo → None y el caller cae al picker de siempre).

    Resuelve el cerebro SERVER-SIDE (dispatch.find_agent → load_agent_cfg →
    resolve_brain) y lee `<brain>/.claude/<agente>-workspaces.json` (lista de
    dicts per-máquina, gitignored). Ordena por max(last_opened, updated,
    created) — cada campo ISO parseado falla-suave a 0 — y devuelve la primera
    entrada con `id` y `name`. JSON roto / archivo ausente / sin entradas
    válidas → None."""
    try:
        import json
        from datetime import datetime
        import dispatch as _dispatch
        entry = _dispatch.find_agent(agent)
        if not entry:
            return None
        cfg = _dispatch.load_agent_cfg(entry)
        brain = _dispatch.resolve_brain(agent, cfg)
        if not brain:
            return None
        canonical = str(entry.get("name") or agent)
        path = os.path.join(brain, ".claude", canonical + "-workspaces.json")
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            return None

        def _ts(w, key):
            try:
                return datetime.fromisoformat(str(w.get(key))).timestamp()
            except Exception:
                return 0

        rows = [w for w in data if isinstance(w, dict)]
        rows.sort(key=lambda w: max(_ts(w, "last_opened"), _ts(w, "updated"),
                                    _ts(w, "created")), reverse=True)
        for w in rows:
            if w.get("id") and w.get("name"):
                return str(w["id"]), str(w["name"])
    except Exception:
        pass
    return None


def chat_cmd(agent, wid, name):
    """El ARRANQUE DIRECTO del chat como una línea de shell — el camino
    existente (dispatch --open/--name → preselect, sin re-picker). Es la
    pieza COMPARTIDA por los backends del split (multiplexer.py): tmux le
    añade su kill-session (left_cmd) y herdr su session stop. Identidad,
    env de sesión y resume NO se reimplementan en ningún backend.

    `--no-banner`: el banner del agente mide ~114 cols y el pane izquierdo del
    split (~98 cols) es más angosto → mostraría el nag 'agranda la ventana',
    no el banner, y `--resume` igual lo enterraría. Traer un banner al split
    necesita una variante COMPACTA (~88 cols) — tarea de diseño aparte
    (2026-07-05, pendiente con el socio). Hasta entonces, arranque limpio."""
    return (_q(PY) + " " + _q(DISPATCH) + " " + agent +
            " --open " + _q(wid) + " --name " + _q(name) + " --no-banner")


def left_cmd(agent, wid, name, session):
    """Pane IZQUIERDO (tmux): el chat — arranque directo del workspace
    elegido (chat_cmd). Al salir el chat se tumba la sesión ENTERA: el
    board no queda huérfano."""
    return (chat_cmd(agent, wid, name) +
            "; tmux kill-session -t " + _q(session) + " 2>/dev/null")


# ═══════════════════════════════════════════════════════════════════════════
# Controlador persistente del pane izquierdo (backend HERDR)
#
# herdr CIERRA un pane cuando su proceso raíz muere → matar el chat para
# cambiar de sesión tumbaba el pane entero. Solución: el pane corre este
# CONTROLADOR (vive siempre); el chat es su hijo en su PROPIO grupo de
# proceso. Switch = el panel escribe desired.json + mata SOLO el grupo del
# chat → el controlador relanza. Salida normal del socio → teardown.
# El backend tmux NO usa nada de esto (no hay switch en tmux).
# ═══════════════════════════════════════════════════════════════════════════

def ctl_base():
    """La raíz de los ctl dirs (~/.claude/workspace/split-ctl) SIN crear nada —
    para que el reaper la recorra sin ensuciarla con un dir sonda."""
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace",
                        "split-ctl")


def ctl_dir(session):
    """Directorio de control del split herdr para <session> (saneada a
    alnum/-/_): ~/.claude/workspace/split-ctl/<session>/. makedirs best-effort;
    devuelve el path aunque crear falle (los usos son falla-suave)."""
    safe = "".join(ch for ch in str(session or "")
                   if ch.isalnum() or ch in "-_")
    path = os.path.join(ctl_base(), safe)
    try:
        os.makedirs(path, exist_ok=True)
    except Exception:
        pass
    return path


def _write_text(path, text):
    """Escritura ATÓMICA best-effort (tmp + os.replace). Jamás levanta."""
    try:
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
    except Exception:
        pass


def _write_desired(ctl, wid, name):
    """desired.json = {"wid","name"} — la sesión que el pane izquierdo DEBE
    correr. El panel escribe aquí para pedir un switch. Atómico, best-effort."""
    import json
    try:
        payload = json.dumps({"wid": str(wid), "name": str(name)},
                             ensure_ascii=False)
    except Exception:
        return
    _write_text(os.path.join(ctl, "desired.json"), payload)


def _read_desired(ctl, dwid, dname):
    """(wid, name) desde desired.json; ante CUALQUIER fallo (archivo ausente,
    JSON roto, claves faltantes) → (dwid, dname). Jamás levanta."""
    import json
    try:
        with open(os.path.join(ctl, "desired.json"), encoding="utf-8") as f:
            d = json.load(f)
        return str(d["wid"]), str(d["name"])
    except Exception:
        return dwid, dname


def _ensure_split_server(session):
    """Re-asegura el server headless de la sesión split, REUSANDO la lógica de
    multiplexer (ensure_server + _session_env) — no se reimplementa aquí. True
    si el server responde. Import perezoso (multiplexer importa mux: al top
    sería circular) y falla-suave: cualquier tropiezo → False (sin server no
    hay a dónde relanzar → el caller hace teardown)."""
    try:
        import multiplexer
        return bool(multiplexer.ensure_server(
            session, multiplexer._session_env(session)))
    except Exception:
        return False


def chat_controller(session, agent, wid, name,
                    _ensure_server=None, _monotonic=None):
    """El LOOP persistente del pane izquierdo del split herdr. Lanza el chat
    (dispatch --open/--name --no-banner) como hijo en su PROPIO grupo
    (start_new_session) y publica su pgid en <ctl>/chat_pgid. Cuando el chat
    muere, según el returncode:
      · desired.json cambió (el panel pidió switch) → relanza (rc ignorado).
      · rc == 0  → salida LIMPIA (el socio hizo /exit) → teardown.
      · rc != 0  → muerte INESPERADA (sleep/App Nap mató al hijo, OOM, crash):
        NO teardown. Re-asegura el server (por si también murió) y relanza,
        preservando la sesión deseada. Sin server → teardown. Anti-spin:
        UNEXPECTED_MAX muertes seguidas en < UNEXPECTED_WINDOW_S → teardown.
    TODO best-effort: cualquier explosión dentro del loop rompe a teardown —
    jamás un pane muerto sin tumbar la sesión.

    `_ensure_server`/`_monotonic`: inyección para tests (default = el helper
    real y time.monotonic)."""
    ensure_server = _ensure_server or _ensure_split_server
    monotonic = _monotonic or time.monotonic
    ctl = ctl_dir(session)
    _write_desired(ctl, wid, name)
    # DEFENSA anti-fuga: si matan al controlador (p.ej. teardown killpg del grupo
    # del PANE), arrastramos al chat — que vive en un grupo APARTE por
    # start_new_session y si no reventaría huérfano. Handler de SIGTERM/SIGHUP.
    _cur = {"pgid": 0}

    def _reap(_signum, _frame):
        try:
            if _cur["pgid"] > 0:
                os.killpg(_cur["pgid"], signal.SIGTERM)
        except Exception:
            pass
        try:
            shutil.rmtree(ctl, ignore_errors=True)
        except Exception:
            pass
        os._exit(0)

    try:
        for _s in (signal.SIGTERM, signal.SIGHUP):
            signal.signal(_s, _reap)
    except Exception:
        pass
    deaths = []                         # timestamps monotónicos de muertes rc!=0
    while True:
        try:
            cw, cn = _read_desired(ctl, wid, name)
            started = monotonic()
            p = subprocess.Popen([PY, DISPATCH, agent, "--open", cw,
                                  "--name", cn, "--no-banner"],
                                 start_new_session=True)
            # pgid == pid por start_new_session; escritura atómica
            _cur["pgid"] = p.pid
            _write_text(os.path.join(ctl, "chat_pgid"), str(p.pid))
            p.wait()
            rc = p.returncode
            nw, nn = _read_desired(ctl, cw, cn)
            if (nw, nn) != (cw, cn):
                deaths = []             # switch deliberado: no cuenta como crash
                continue                # el panel pidió switch → relanzar
            if rc == 0:
                break                   # salida LIMPIA (/exit) → teardown
            # rc != 0 → muerte INESPERADA (sleep/App Nap/OOM/crash): relanzar,
            # salvo hot-loop (anti-spin) o server que no revive.
            now = monotonic()
            if now - started > UNEXPECTED_WINDOW_S:
                deaths = []             # corrida larga → no es hot-loop: reset
            deaths = [t for t in deaths if now - t <= UNEXPECTED_WINDOW_S]
            deaths.append(now)
            if len(deaths) >= UNEXPECTED_MAX:
                break                   # crashea al instante en loop → teardown
            if not ensure_server(session):
                break                   # sin server no hay a dónde relanzar
            continue                    # server vivo → relanzar (desired intacto)
        except Exception:
            break                       # jamás dejar el pane sin teardown
    try:
        subprocess.run([HERDR, "session", "stop", session],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", timeout=15)
    except Exception:
        pass
    try:
        shutil.rmtree(ctl, ignore_errors=True)
    except Exception:
        pass
    return 0


def right_cmd():
    """Pane DERECHO: la pipeline en vivo (`workspace wf board --follow active
    --persist`). El board SIGUE la corrida activa: workflows.start() escribe
    el run-id a la pila `~/.claude/workspace/workflows/active_run` y el cierre
    terminal la limpia — arranca un run y este pane se clava en ÉL solo (▸),
    sin cambiar de ventana. Sin active_run → prioridad global de siempre.

    `--persist`: el board NO sale cuando nada corre — se queda repintando EN
    SITIO (cursor-arriba, sin `clear`) esperando el próximo run. Por eso el
    pane lo corre UNA sola vez, sin el `while … clear … sleep` de antes: ese
    `clear` cada BOARD_RESPAWN_S s era el PARPADEO. Ahora: cero flash.

    COSTURA RESTANTE (Pieza 3 — decisión de flujo del socio): el hook/flujo
    que DETECTA el workflow de una tarea (`workspace wf match`) y lo PROPONE en
    el chat vive fuera; cuando ese flujo arranque runs, este pane ya los
    sigue solo. El armado de panes (split_cmds) no se toca."""
    return _q(PY) + " " + _q(FRONT) + " wf board --follow active --persist"


def right_pane_cmd(agent=None, wid=None):
    """SUPERFICIE EXTENSIBLE — el ÚNICO punto que decide qué corre en el pane
    derecho del split. Elige por el setting `ui.split_pane`:
      • board  (default) → la pipeline pelona en vivo (right_cmd → wf board
        --persist). Compat exacto de siempre.
      • panel  → el PANEL con menú (front.py panel): Pipeline / Bus / Config /
        Delegar + header de identidad del agente. Extensible en panel.VIEWS.
    Enriquecerlo (más vistas) NO toca split() ni el armado (split_cmds).
    Contrato: UNA línea de shell que se sostiene sola en un pane angosto y no
    termina hasta que la sesión muera. Falla-suave: sin settings → board."""
    try:
        import settings
        mode = settings.get("ui.split_pane", "board")
    except Exception:
        mode = "board"
    if mode == "panel":
        import re
        cmd = _q(PY) + " " + _q(FRONT) + " panel"
        if agent:
            # defensivo: el agente se interpola en la línea del pane; _q no cita
            # metacaracteres sin espacio (foo;id pasaría) → acotar a [\w.-]
            safe = re.sub(r"[^A-Za-z0-9_.-]", "", str(agent))
            if safe:
                cmd += " --agent " + _q(safe)
        if wid is not None:
            # mismo patrón defensivo: el wid viaja por la línea del pane →
            # acotar a [A-Za-z0-9-]; vacío tras sanear → no se añade.
            # Back-compat: sin wid la línea es byte-idéntica a la de siempre.
            wsafe = re.sub(r"[^A-Za-z0-9-]", "", str(wid))
            if wsafe:
                cmd += " --wid " + _q(wsafe)
        return cmd
    return right_cmd()


def split_cmds(session, ws_name, left, right, right_pct):
    """Los comandos tmux que arman la ventana partida. PURA (testeable):
      1. sesión detached con el chat como pane único
      2. split HORIZONTAL: pane derecho de `right_pct`% con el board
      3. foco al pane izquierdo (el chat es el protagonista)"""
    return [
        ["new-session", "-d", "-s", session, "-n", ws_name, left],
        ["split-window", "-h", "-t", session, "-l", str(right_pct) + "%", right],
        ["select-pane", "-t", session, "-L"],
    ]


def legacy_split(cmd):
    """tmux <3.1 no acepta `-l N%` en split-window → equivalente viejo `-p N`.
    PURA; se intenta solo si la forma moderna falló."""
    out, i = [], 0
    while i < len(cmd):
        if cmd[i] == "-l" and i + 1 < len(cmd) and str(cmd[i + 1]).endswith("%"):
            out += ["-p", str(cmd[i + 1])[:-1]]
            i += 2
            continue
        out.append(cmd[i])
        i += 1
    return out


def fallback(agent, reason):
    """Aviso claro + arranque NORMAL de siempre (handoff a dispatch, idéntico a
    front.launch). El modo split jamás deja al socio sin su agente."""
    sys.stderr.write("WORKSPACE: " + reason + " — abriendo normal.\n")
    if os.name == "nt":
        return subprocess.run([PY, DISPATCH, agent]).returncode
    os.execvp(PY, [PY, DISPATCH, agent])


def split(argv=None):
    """`workspace split [agente]` — arma la terminal partida (o cae con gracia)."""
    agent, pct, plan, force_pick = parse_args(argv or [])
    if not agent:
        agent = default_agent()
    if not agent:
        print("uso: workspace split <agente> [--right N] [--plan] [--pick]\n"
              "     (agentes registrados:  python3 dispatch.py --list)")
        return 2

    # Degradación grácil — cualquier impedimento → arranque normal, con aviso.
    if os.name == "nt":
        return fallback(agent, "el modo split usa tmux (Mac/Linux); "
                               "en Windows va la sesión sencilla")
    if not have_tmux() and not plan:
        return fallback(agent, "el modo split necesita tmux "
                               "(en Mac:  brew install tmux)")
    if inside_tmux() and not plan:
        return fallback(agent, "ya estás dentro de tmux; el split no se anida")
    if not plan and not (sys.stdin.isatty() and sys.stdout.isatty()):
        return fallback(agent, "el modo split necesita una terminal interactiva")

    # Camino feliz SIN picker: la sesión más reciente del agente, salvo que el
    # socio fuerce el picker (--pick) o estemos en plan-mode (flujo idéntico
    # al de hoy: pick devuelve el ejemplo). default_session None → picker.
    sel = (None if (plan or force_pick) else default_session(agent)) or pick(agent, plan)
    if not sel:
        print("WORKSPACE: no se eligió workspace; nada que abrir.")
        return 0
    wid, name = sel
    session = session_name(name)

    tx = Tmux(plan=plan)
    if not plan and session_exists(session):
        # dedupe: ese workspace YA tiene su split → reconectar, no duplicar
        return tx.run(["attach-session", "-t", session])

    for cmd in split_cmds(session, name, left_cmd(agent, wid, name, session),
                          right_pane_cmd(agent), pct):
        rc = tx.run(cmd)
        if rc != 0 and cmd and cmd[0] == "split-window":
            rc = tx.run(legacy_split(cmd))      # tmux viejo: -l N% → -p N
        if rc != 0:
            # tmux falló a medio armado → limpiar el intento y abrir normal
            subprocess.run(["tmux", "kill-session", "-t", session],
                           capture_output=True)
            return fallback(agent, "tmux no pudo armar la ventana partida")

    return tx.run(["attach-session", "-t", session])


def main():
    argv = sys.argv[1:]
    # `mux.py chat-controller <session> <agent> <wid> <name>` — el loop
    # persistente del pane izquierdo del split herdr (multiplexer lo lanza).
    if len(argv) >= 5 and argv[0] == "chat-controller":
        sys.exit(chat_controller(argv[1], argv[2], argv[3], argv[4]))
    # `mux.py split …` y `mux.py …` valen igual (split es el único modo vivo;
    # el hub multi-ventana quedó en la historia git de _shelved/mux.py).
    if argv and argv[0] == "split":
        argv = argv[1:]
    sys.exit(split(argv))


if __name__ == "__main__":
    main()
