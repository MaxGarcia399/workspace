#!/usr/bin/env python3
"""WORKSPACE · multiplexer — la ABSTRACCIÓN del split (tmux | herdr) con
fallback en capas (F1 de la adopción de HERDR).

Una sola pregunta responde este módulo: "¿con QUÉ multiplexer se arma la
terminal partida (chat | wf board) y qué pasa si no se puede?". La respuesta
JAMÁS rompe el arranque:

  ui.split OFF (default)  → este módulo ni se importa (front.launch exec
                            directo de siempre; regla #1 intacta).
  ui.split ON             → open_split():
      backend efectivo herdr y herdr responde  → HerdrMultiplexer
      backend efectivo tmux (o herdr caído)    → TmuxMultiplexer (mux.split,
                                                 el flujo de SIEMPRE, con sus
                                                 propios fallbacks: sin tmux /
                                                 sin TTY / anidado / Windows →
                                                 arranque normal con aviso)
      fallo A MEDIO armado (cualquier backend) → arranque normal (exec) con
                                                 aviso — mux.fallback.

Backend: setting `ui.split_backend` = auto|tmux|herdr (default auto: herdr
si está en el PATH y responde, si no tmux). Env WORKSPACE_SPLIT_BACKEND gana
(probar sin persistir). `ui.split` (on/off) sigue siendo el MASTER: apagado,
nada de esto corre.

CÓMO ARMA HERDR LOS DOS PANES (verificado contra herdr 0.7.1 real):
  1. server por sesión:   HERDR_SESSION=<ses> herdr server   (headless,
     detached; socket en ~/.config/herdr/sessions/<ses>/herdr.sock — NO toca
     la sesión default del socio)
  2. chat (izquierda):    herdr agent start <agente> --cwd <ROOT> --
                          sh -c '<mux.chat_cmd>; herdr session stop <ses>'
     (el MISMO arranque directo de dispatch --open/--name; al salir el chat
     la sesión ENTERA se tumba — nada queda huérfano)
  3. board (derecha):     herdr pane split <chat> --direction right
                          --ratio 0.NN --no-focus   +   herdr pane run
                          <derecho> "<mux.right_pane_cmd()>"
  4. foco: queda en el chat (agent start enfoca; el split fue --no-focus)
  5. attach:              herdr session attach <ses>   (bloquea; al morir la
     sesión el cliente sale y el launcher recupera la terminal)
  6. post-attach: sesión ya no corre → `herdr session delete <ses>` (limpia
     el registro). Si el socio se DESCONECTÓ con el chat vivo, la sesión
     persiste y el dedupe re-attacha (paridad con tmux).

COSTURA F2 (panel-cliente del socket API): el pane derecho se decide en UN
punto — mux.right_pane_cmd() — compartido por AMBOS backends. En F2, para el
backend herdr, ese comando pasará de `wf board` a un cliente del socket API
de herdr (events.subscribe a pane.agent_status_changed + pane.read; socket
en $HERDR_SOCKET_PATH, que herdr inyecta al pane). Se cambia SOLO
right_pane_cmd (o una variante por-backend aquí); el armado de panes y la
selección de backend NO se tocan.

Cero dependencias (stdlib). Nada aquí corre en el camino del hub/menú.
"""
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time

import mux

HERDR = "herdr"
SERVER_WAIT_S = 5.0          # techo de espera a que el server por-sesión responda
SERVER_POLL_S = 0.15
_VERSION_TIMEOUT_S = 5
_SPLIT_PREFIX = "workspace-split-"    # las sesiones que ESTE módulo arma (reaper acotado)
_KILL_GRACE_S = 1.5                 # gracia entre SIGTERM y SIGKILL al tumbar un grupo


# ═══════════════════════════════════════════════════════════════════════════
# La interfaz + las dos implementaciones
# ═══════════════════════════════════════════════════════════════════════════

class Multiplexer:
    """Contrato mínimo de un backend del split: ¿estás disponible? y
    ábreme la sesión partida (chat | board) para este argv. `open` DEBE
    degradar solo (jamás levantar hacia el caller sin haber caído antes al
    arranque normal)."""
    name = "?"

    def available(self):
        raise NotImplementedError

    def open(self, argv):
        raise NotImplementedError


class TmuxMultiplexer(Multiplexer):
    """El backend de SIEMPRE: envuelve mux.split tal cual (picker → 2 panes
    → attach, con TODOS sus fallbacks internos). No se reescribe nada."""
    name = "tmux"

    def available(self):
        return mux.have_tmux()

    def open(self, argv):
        return mux.split(argv)


class HerdrMultiplexer(Multiplexer):
    """El backend nuevo: mismos ingredientes (mismo picker, mismo chat_cmd,
    mismo right_pane_cmd), armados sobre una sesión herdr NOMBRADA con server
    propio — la sesión default de herdr del socio no se toca."""
    name = "herdr"

    def available(self):
        return have_herdr() and herdr_responds()

    def open(self, argv):
        return herdr_split(argv)


BACKENDS = {"tmux": TmuxMultiplexer, "herdr": HerdrMultiplexer}


# ═══════════════════════════════════════════════════════════════════════════
# Selección de backend (auto | tmux | herdr) — falla-suave absoluta
# ═══════════════════════════════════════════════════════════════════════════

def have_herdr():
    return shutil.which(HERDR) is not None


def herdr_responds():
    """herdr está Y contesta (--version no necesita server). Cualquier duda
    → False: 'auto' cae a tmux, jamás a un backend a medias."""
    try:
        return subprocess.run([HERDR, "--version"], capture_output=True,
                              timeout=_VERSION_TIMEOUT_S).returncode == 0
    except Exception:
        return False


def backend_setting():
    """`ui.split_backend` efectivo (env WORKSPACE_SPLIT_BACKEND gana). Valor
    raro o settings roto → 'auto' (el default del schema)."""
    v = (os.environ.get("WORKSPACE_SPLIT_BACKEND") or "").strip().lower()
    if v not in ("auto", "tmux", "herdr"):
        try:
            import settings as _settings
            v = str(_settings.get("ui.split_backend", "auto")).strip().lower()
        except Exception:
            v = "auto"
    return v if v in ("auto", "tmux", "herdr") else "auto"


def pick_backend():
    """El multiplexer a usar. NUNCA devuelve None ni levanta:
      auto  → herdr si responde, si no tmux
      herdr → herdr si responde, si no tmux (con aviso)
      tmux  → tmux (sus fallbacks internos deciden el resto)
    tmux es el piso: mux.split ya degrada solo al arranque normal."""
    want = backend_setting()
    hx = HerdrMultiplexer()
    if want == "herdr":
        if hx.available():
            return hx
        sys.stderr.write("WORKSPACE: backend herdr pedido pero herdr no "
                         "responde — usando tmux.\n")
        return TmuxMultiplexer()
    if want == "auto" and hx.available():
        return hx
    return TmuxMultiplexer()


def open_split(argv):
    """LA puerta del split (front.launch con ui.split ON y `workspace split`).
    Elige backend y abre; un backend reventando NO tumba el arranque: cae al
    exec normal de siempre (la capa de abajo, mux.fallback)."""
    backend = None
    try:
        backend = pick_backend()
        return backend.open(argv)
    except Exception:
        # último piso: arranque normal. Se necesita el agente del argv;
        # parse_args jamás revienta.
        agent = mux.parse_args(argv or [])[0] or mux.default_agent()
        if not agent:
            print("uso: workspace split <agente> [--right N] [--plan]")
            return 2
        name = backend.name if backend is not None else "?"
        return mux.fallback(agent, "el multiplexer (%s) falló" % name)


# ═══════════════════════════════════════════════════════════════════════════
# Backend herdr — el armado (sesión nombrada, server propio, 2 panes)
# ═══════════════════════════════════════════════════════════════════════════

def inside_herdr():
    """Ya corremos DENTRO de un pane de herdr (env inyectado por herdr) —
    no anidar un attach ahí (mismo criterio que tmux-dentro-de-tmux)."""
    return bool(os.environ.get("HERDR_ENV"))


def _session_env(session):
    """Env con HERDR_SESSION=<ses>: TODOS los subcomandos van al socket de
    ESA sesión (~/.config/herdr/sessions/<ses>/), no al default del socio.

    HERDR_CONFIG_PATH → config PROPIO del split (herdr-split.toml, en ROOT):
    mouse_capture=false para que el scroll no rompa la ventana partida. Se
    aplica SOLO a las sesiones workspace-split-* (el config global del socio
    queda intacto). Best-effort: si el archivo no está, herdr usa su default."""
    env = dict(os.environ)
    env["HERDR_SESSION"] = session
    env.pop("HERDR_SOCKET_PATH", None)   # ganaría sobre HERDR_SESSION
    cfg = os.path.join(mux.ROOT, "herdr-split.toml")
    if os.path.isfile(cfg):
        env["HERDR_CONFIG_PATH"] = cfg
    return env


class _PlanOK:
    """Resultado simulado del modo --plan (éxito, sin tocar subprocess)."""
    returncode = 0
    stdout = ""
    stderr = ""


def _run(args, env, plan=False, timeout=30):
    """Un subcomando herdr. En plan: imprime y simula éxito."""
    if plan:
        print("  [plan] " + " ".join(mux._q(a) for a in args))
        return _PlanOK()
    return subprocess.run(args, env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def _json_result(proc):
    """result{} del JSON que imprimen los subcomandos de herdr (o {})."""
    try:
        return (json.loads(proc.stdout or "{}") or {}).get("result") or {}
    except Exception:
        return {}


def session_running(session, env=None):
    try:
        proc = subprocess.run([HERDR, "session", "list", "--json"],
                              env=env or os.environ.copy(),
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=15)
        for s in (json.loads(proc.stdout or "{}") or {}).get("sessions") or []:
            if s.get("name") == session:
                return bool(s.get("running"))
    except Exception:
        pass
    return False


def ensure_server(session, env, plan=False):
    """Server headless de la sesión NOMBRADA (idempotente). Detached total
    (nueva sesión de proceso, sin fds) → sobrevive al launcher, y morirá con
    `herdr session stop` cuando el chat salga. True si el socket responde."""
    if plan:
        print("  [plan] HERDR_SESSION=%s herdr server  (headless, detached)"
              % session)
        return True
    if session_running(session, env):
        return True
    try:
        subprocess.Popen([HERDR, "server"], env=env,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception:
        return False
    limit = time.time() + SERVER_WAIT_S
    while time.time() < limit:
        if session_running(session, env):
            return True
        time.sleep(SERVER_POLL_S)
    return False


def herdr_chat_cmd(agent, wid, name, session):
    """El pane izquierdo — el CONTROLADOR persistente (mux.chat_controller),
    NO el chat directo: el controlador vive siempre y corre el chat como hijo
    en su propio grupo de proceso. Así un switch de sesión (panel escribe
    desired.json + killpg del grupo del chat) NO mata el proceso raíz del
    pane → herdr no lo cierra y el controlador relanza. El `herdr session
    stop` al salir el socio lo hace el controlador INTERNAMENTE (equivalente
    del kill-session de tmux) — no se añade cola shell aquí."""
    import shlex          # comilla SEGURO metacaracteres pegados (;$()`|&) que
    #                       mux._q deja pasar; la línea corre vía sh -c
    script = os.path.join(mux.ROOT, "mux.py")
    return (shlex.quote(mux.PY) + " " + shlex.quote(script)
            + " chat-controller " + shlex.quote(str(session)) + " "
            + shlex.quote(str(agent)) + " " + shlex.quote(str(wid)) + " "
            + shlex.quote(str(name)))


def _pane_pgids(session, env):
    """Grupos de proceso (pgid) de TODOS los panes de la sesión, vía el socket
    API de herdr (`pane list` → `pane process-info`). Es lo que herdr NO mata
    al hacer `session stop`: sin esto, el `sh -c …claude…` del pane queda
    huérfano reparentado a init = la FUGA. Best-effort: cualquier fallo → set
    vacío (el `session stop` sigue corriendo igual)."""
    pgids = set()
    try:
        r = subprocess.run([HERDR, "pane", "list"], env=env,
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=15)
        panes = (_safe_json(r.stdout).get("result") or {}).get("panes") or []
    except Exception:
        panes = []
    for p in panes:
        pid = p.get("pane_id")
        if not pid:
            continue
        try:
            pi = subprocess.run([HERDR, "pane", "process-info", "--pane", pid],
                                env=env, capture_output=True, text=True,
                                encoding="utf-8", errors="replace", timeout=15)
            info = ((_safe_json(pi.stdout).get("result") or {})
                    .get("process_info") or {})
            pg = info.get("foreground_process_group_id") or info.get("shell_pid")
            if pg:
                pgids.add(int(pg))
        except Exception:
            continue
    return pgids


def _safe_json(s):
    try:
        return json.loads(s or "{}") or {}
    except Exception:
        return {}


def _clear_screen():
    """Limpia pantalla + scrollback ANTES de que herdr tome la terminal. El
    picker de sesiones (mux.pick) se dibuja en la terminal antes de armar los
    panes; sin esto queda de RESIDUO arriba del scroll (el 'menú de sesiones'
    que el socio veía al scrollear). Best-effort."""
    try:
        sys.stdout.write("\033[2J\033[3J\033[H")
        sys.stdout.flush()
    except Exception:
        pass


def _kill_pgids(pgids, grace=_KILL_GRACE_S):
    """SIGTERM (gracia) → SIGKILL a cada grupo de proceso. NUNCA se mata a sí
    mismo (excluye el pgid propio). Devuelve cuántos grupos existían al TERM."""
    try:
        mypg = os.getpgrp()
    except Exception:
        mypg = None
    targets = {int(g) for g in pgids if g and int(g) != mypg}
    if not targets:
        return 0
    hit = 0
    for g in targets:
        try:
            os.killpg(g, signal.SIGTERM)
            hit += 1
        except ProcessLookupError:
            pass
        except Exception:
            pass
    time.sleep(grace)
    for g in targets:
        try:
            os.killpg(g, signal.SIGKILL)
        except Exception:
            pass
    return hit


def _chat_pgid(session):
    """El pgid del grupo del CHAT que el controlador publica en <ctl>/chat_pgid.
    CRÍTICO: el chat corre con start_new_session=True → está en un grupo APARTE
    del pane. Matar solo el pgid del pane (el del controlador) deja al `claude`
    huérfano reparentado a init = la fuga. Devuelve {pgid} o set()."""
    try:
        import mux
        with open(os.path.join(mux.ctl_dir(session), "chat_pgid"),
                  encoding="utf-8") as fh:
            pg = int(fh.read().strip())
        return {pg} if pg > 0 else set()
    except Exception:
        return set()


def _cleanup_ctl(session):
    """rmtree del directorio de control de la sesión (best-effort)."""
    try:
        import mux
        import shutil
        shutil.rmtree(mux.ctl_dir(session), ignore_errors=True)
    except Exception:
        pass


def herdr_teardown(session, env):
    """Tumbar y borrar la sesión Y matar el grupo de procesos del pane Y el del
    CHAT (que corre en grupo aparte por start_new_session — sin esto el `claude`
    sobrevive huérfano al matar solo el pane = la fuga). Orden: leer ambos pgids
    MIENTRAS el server vive → stop → matar los pgids → delete + limpiar ctl.
    Jamás levanta."""
    pgids = _pane_pgids(session, env)
    pgids |= _chat_pgid(session)           # + el grupo del chat (aparte del pane)
    for cmd in (["session", "stop", session], ["session", "delete", session]):
        try:
            subprocess.run([HERDR] + cmd, env=env, capture_output=True,
                           timeout=15)
        except Exception:
            pass
    if pgids:
        _kill_pgids(pgids)
    _cleanup_ctl(session)


def _attach_client_sessions():
    """Sesiones workspace-split-* con un cliente `herdr session attach` VIVO =
    abiertas en una ventana AHORA. El reaper jamás las toca."""
    live = set()
    try:
        r = subprocess.run(["ps", "-axo", "command="], capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=10)
        for line in (r.stdout or "").splitlines():
            m = re.search(r"\bsession\s+attach\s+("
                          + re.escape(_SPLIT_PREFIX) + r"[A-Za-z0-9._-]+)", line)
            if m:
                live.add(m.group(1))
    except Exception:
        pass
    return live


def _running_split_sessions(env=None):
    """Sesiones workspace-split-* que herdr reporta corriendo."""
    names = set()
    try:
        r = subprocess.run([HERDR, "session", "list", "--json"],
                           env=env or os.environ.copy(), capture_output=True,
                           text=True, encoding="utf-8", errors="replace",
                           timeout=15)
        for s in _safe_json(r.stdout).get("sessions") or []:
            n = str(s.get("name", ""))
            if n.startswith(_SPLIT_PREFIX) and s.get("running"):
                names.add(n)
    except Exception:
        pass
    return names


def _orphan_split_pgids(running):
    """Grupos de proceso de wrappers de chat (`sh -c …; herdr session stop
    workspace-split-<x>`) cuya sesión YA no corre = sobrevivientes de un teardown
    incompleto (la fuga histórica). {pgid: session}. El wrapper y su claude
    comparten pgid → matar el grupo los tumba a ambos."""
    victims = {}
    try:
        r = subprocess.run(["ps", "-axo", "pgid=,command="],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=10)
    except Exception:
        return victims
    for line in (r.stdout or "").splitlines():
        m = re.search(r"session stop ("
                      + re.escape(_SPLIT_PREFIX) + r"[A-Za-z0-9._-]+)", line)
        if not m or m.group(1) in running:
            continue
        try:
            victims[int(line.split(None, 1)[0])] = m.group(1)
        except Exception:
            continue
    return victims


def _pgid_commands():
    """{pgid: comando(s) concatenados} de los procesos VIVOS. Para cruzar un
    chat_pgid con el WID esperado de SU sesión: así el reaper mata SOLO si el
    grupo aún corre el chat de ESA sesión, no un `claude` reciclado/ajeno."""
    out = {}
    try:
        r = subprocess.run(["ps", "-axo", "pgid=,command="],
                           capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=10)
        for line in (r.stdout or "").splitlines():
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            try:
                pg = int(parts[0])
            except Exception:
                continue
            out[pg] = out.get(pg, "") + " " + parts[1]
    except Exception:
        pass
    return out


def _ctl_wid(ctl_path):
    """El wid de <ctl>/desired.json (la sesión montada). '' si no se puede."""
    try:
        with open(os.path.join(ctl_path, "desired.json"),
                  encoding="utf-8") as fh:
            return str((json.load(fh) or {}).get("wid") or "")
    except Exception:
        return ""


def _orphan_ctl_pgids(running, attached, keep):
    """Grupos de CHAT huérfanos leídos de los ctl dirs (<split-ctl>/<ses>/
    chat_pgid) de sesiones workspace-split-* que YA no corren = el controlador
    murió (p.ej. teardown lo mató) pero el `claude`, en su grupo aparte por
    start_new_session, quedó vivo. {pgid: session}.

    ANTI-KILL-CIEGO + ANTI-FALSO-POSITIVO: un chat_pgid leído de un archivo
    viejo puede estar RECICLADO por el SO (post-reboot) — y el pid reciclado
    podría ser hasta el `claude` NORMAL (no-split) del socio. Por eso SOLO se
    incluye si el grupo vivo de ese pgid corre un comando que contiene el WID
    de ESA sesión (UUID único, de desired.json) — cruce específico, no un match
    genérico de 'claude'. Best-effort."""
    out = {}
    try:
        import mux
        base = mux.ctl_base()
        if not os.path.isdir(base):
            return out
        cmds = _pgid_commands()
        for name in os.listdir(base):
            if (not name.startswith(_SPLIT_PREFIX) or name in running
                    or name == keep or name in attached):
                continue
            d = os.path.join(base, name)
            try:
                with open(os.path.join(d, "chat_pgid"), encoding="utf-8") as fh:
                    pg = int(fh.read().strip())
                wid = _ctl_wid(d)
                # SOLO si el grupo vivo corre el chat de ESTA sesión (su wid en
                # el command) → jamás un pid reciclado ni un claude ajeno.
                if pg > 0 and wid and wid in cmds.get(pg, ""):
                    out[pg] = name
            except Exception:
                continue
    except Exception:
        pass
    return out


def _controller_alive(sess, cmds=None):
    """True si el CONTROLADOR del chat de `sess` sigue VIVO: su pgid
    (<ctl>/<sess>/chat_pgid) es un proceso vivo que corre el chat de ESTA
    sesión (su wid de desired.json aparece en el comando del grupo — el mismo
    cruce anti-pid-reciclado que _orphan_ctl_pgids). Una sesión detached CON
    controlador vivo es una sesión VÁLIDA en segundo plano (re-attacheable),
    NO un huérfano. `cmds` = _pgid_commands() precomputado (evita un `ps` por
    sesión). Best-effort → False (ante la duda NO declara viva → no bloquea el
    reap de un zombie real)."""
    try:
        import mux
        d = os.path.join(mux.ctl_base(), sess)
        with open(os.path.join(d, "chat_pgid"), encoding="utf-8") as fh:
            pgid = int(fh.read().strip())
        wid = _ctl_wid(d)
        cmds = _pgid_commands() if cmds is None else cmds
        return pgid > 0 and bool(wid) and wid in cmds.get(pgid, "")
    except Exception:
        return False


def reap_orphans(keep=None, env=None, plan=False):
    """Red de seguridad anti-acumulación. Tumba sesiones workspace-split-* que
    sean HUÉRFANAS DE VERDAD (detached Y con el controlador del chat MUERTO) y
    mata procesos huérfanos de teardowns incompletos — incluido el grupo del
    CHAT (aparte del pane por start_new_session), leído de los ctl dirs. NUNCA
    toca `keep`, una con ventana abierta, NI una detached con controlador VIVO
    (sesión válida en 2º plano). Devuelve (reapeadas, matados). Best-effort.

    ANTES tumbaba TODA sesión detached → al armar el split de otro agente
    (keep=ese) mataba la sesión VIVA del socio con la que estaba trabajando
    (el 'pantallaso: server is shutting down' al abrir otro agente teniendo el
    primero en 2º plano). Ahora una detached solo se reapea si su ctrl murió."""
    reaped, killed = [], 0
    try:
        attached = _attach_client_sessions()
        live_cmds = _pgid_commands()               # una vez, para el cruce vivo
        for sess in sorted(_running_split_sessions(env)):
            if sess == keep or sess in attached:
                continue
            # detached PERO con controlador vivo = sesión válida en 2º plano,
            # re-attacheable → JAMÁS reapear (era el bug del pantallaso).
            if _controller_alive(sess, live_cmds):
                continue
            if plan:
                print("  [plan] reap sesión huérfana %s" % sess)
            else:
                herdr_teardown(sess, _session_env(sess))
            reaped.append(sess)
        run_now = _running_split_sessions(env)
        # (a) wrappers viejos por-workspace (legacy, comparten pgid con su claude)
        for pgid, sess in _orphan_split_pgids(run_now).items():
            if sess == keep or sess in attached:
                continue
            if plan:
                print("  [plan] reap grupo huérfano pgid=%s (%s)" % (pgid, sess))
            else:
                killed += _kill_pgids({pgid})
        # (b) chat huérfano del controlador nuevo (grupo aparte) vía ctl dir
        for pgid, sess in _orphan_ctl_pgids(run_now, attached, keep).items():
            if plan:
                print("  [plan] reap chat huérfano (ctl) pgid=%s (%s)" % (pgid, sess))
            else:
                killed += _kill_pgids({pgid})
                _cleanup_ctl(sess)
    except Exception:
        pass
    return reaped, killed


def agent_session_name(agent):
    """Nombre de sesión herdr POR-AGENTE (`workspace-split-<agente>`). Con el
    switch de workspace desde el panel, el naming por-workspace haría que el
    dedupe abriera un SEGUNDO split con `--resume` de la MISMA conversación
    (dos clientes = corrupción de UX). Semántica: UN split por agente. Mismo
    saneo que mux.session_name (alnum/-/_ → '-'); el prefijo no cambia →
    reaper/teardown/regex intactos y las sesiones viejas por-workspace se
    siguen listando/reapeando igual."""
    slug = "".join(c if (c.isalnum() or c in "-_") else "-"
                   for c in str(agent).strip().lower()).strip("-") or "agent"
    return _SPLIT_PREFIX + slug


def herdr_split(argv=None):
    """Arma la terminal partida sobre herdr (o cae con gracia). Espejo del
    flujo de mux.split: guards → selección → dedupe → armado → attach."""
    agent, pct, plan, force_pick = mux.parse_args(argv or [])
    if not agent:
        agent = mux.default_agent()
    if not agent:
        print("uso: workspace split <agente> [--right N] [--plan] [--pick]\n"
              "     (agentes registrados:  python3 dispatch.py --list)")
        return 2

    # Guards — mismo espíritu que mux.split: cualquier impedimento → normal.
    if os.name == "nt":
        return mux.fallback(agent, "el modo split usa un multiplexer "
                                   "(Mac/Linux); en Windows va la sesión "
                                   "sencilla")
    if inside_herdr() and not plan:
        return mux.fallback(agent, "ya estás dentro de herdr; el split no "
                                   "se anida")
    if not plan and not (sys.stdin.isatty() and sys.stdout.isatty()):
        return mux.fallback(agent, "el modo split necesita una terminal "
                                   "interactiva")

    # Camino feliz SIN picker: la sesión más reciente del agente, salvo que
    # el socio fuerce el picker (--pick) o estemos en plan-mode (flujo
    # idéntico al de hoy: pick devuelve el ejemplo). None → picker de siempre.
    sel = (None if (plan or force_pick) else mux.default_session(agent)) \
        or mux.pick(agent, plan)
    if not sel:
        print("WORKSPACE: no se eligió workspace; nada que abrir.")
        return 0
    wid, name = sel
    session = agent_session_name(agent)  # POR-AGENTE: un split por agente
    env = _session_env(session)

    # Anti-acumulación: antes de armar, reap de sesiones detached y procesos
    # huérfanos de splits anteriores (jamás toca `session` ni ventanas vivas).
    if not plan:
        reap_orphans(keep=session, env=env)

    # dedupe: el AGENTE ya tiene su sesión herdr viva → re-attach a esa
    # ventana, sea cual sea el workspace montado dentro (un split por agente;
    # cambiar de workspace es trabajo del panel, no de un segundo split).
    if not plan and session_running(session, env):
        _clear_screen()
        return subprocess.run([HERDR, "session", "attach", session],
                              env=env).returncode

    if not ensure_server(session, env, plan):
        # server no subió: (MEDIUM-2) limpia best-effort por si un server tardío
        # alcanzó a asomar (no dejar huérfano ni sessions/<ws>/ basura), y
        # (MEDIUM-1) honra la cadena herdr→tmux→normal — cae al split por tmux
        # si está disponible, no directo al arranque sencillo.
        herdr_teardown(session, env)
        tmux = TmuxMultiplexer()
        if tmux.available():
            return tmux.open(argv or [])
        return mux.fallback(agent, "herdr no levantó el server de la sesión")

    # 1) chat a la IZQUIERDA — el pane raíz del workspace, con foco.
    chat = herdr_chat_cmd(agent, wid, name, session)
    r = _run([HERDR, "agent", "start", agent, "--cwd", mux.ROOT,
              "--", "sh", "-c", chat], env, plan)
    pane = (_json_result(r).get("agent") or {}).get("pane_id", "w1:p1")
    if r.returncode != 0:
        herdr_teardown(session, env)
        return mux.fallback(agent, "herdr no pudo abrir el pane del chat")

    # 2) board a la DERECHA — split sin robar el foco + comando del board.
    ratio = "%.2f" % (max(mux.RIGHT_PCT_MIN, min(mux.RIGHT_PCT_MAX, pct))
                      / 100.0)
    r2 = _run([HERDR, "pane", "split", pane, "--direction", "right",
               "--ratio", ratio, "--no-focus", "--cwd", mux.ROOT], env, plan)
    right = _json_result(r2).get("pane", {}).get("pane_id", "")
    if r2.returncode != 0 or (not plan and not right):
        herdr_teardown(session, env)
        return mux.fallback(agent, "herdr no pudo abrir el pane del board")
    r3 = _run([HERDR, "pane", "run", right or "<pane-derecho>",
               mux.right_pane_cmd(agent, wid=wid)], env, plan)
    if r3.returncode != 0:
        herdr_teardown(session, env)
        return mux.fallback(agent, "herdr no pudo lanzar el board")

    # 3) attach (bloquea). Chat sale → session stop (del chat_cmd) → el
    #    cliente cae y volvemos aquí.
    if plan:
        print("  [plan] herdr session attach " + mux._q(session))
        return 0
    _clear_screen()        # borra el picker de sesiones antes del attach
    rc = subprocess.run([HERDR, "session", "attach", session],
                        env=env).returncode

    # 4) post-attach: cerraste o desconectaste la ventana. Si NO queda OTRA
    #    ventana attacheada a esta sesión, teardown COMPLETO (mata el chat: nada
    #    de claude huérfano — la fuga). Reabrir = picker → --resume = MISMA
    #    conversación, así que la persistencia de herdr era redundante con el
    #    --resume propio de Claude Code: no se pierde nada y no se acumula.
    #    Si otra ventana sigue attacheada (mismo workspace en 2 ventanas), se
    #    respeta y el dedupe re-attacha luego.
    if session not in _attach_client_sessions():
        herdr_teardown(session, env)
    return rc
