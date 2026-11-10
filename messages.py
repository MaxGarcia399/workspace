#!/usr/bin/env python3
"""WORKSPACE · messages — bus de mensajes inter-agente sobre archivos (Sprint-1).

El filesystem ES el bus: un mensaje = UN archivo Markdown con frontmatter en
`<cerebro-del-destinatario>/msgs/<id>.md`. Sin daemon, sin red, sin protocolo
nuevo — git/Obsidian-sync lo transportan y cualquier socio lo audita a mano.
(Diseño fuente: documento interno del equipo.)

Schema del archivo (frontmatter YAML-plano + cuerpo Markdown libre):

    ---
    id: 20260612T101530-zenith-atlas-encargo-dashboard-f3
    from: zenith                 # agente o socio que envía
    to: atlas                    # agente destinatario (su cerebro es el buzón)
    type: encargo                # encargo | handoff | broadcast | reply
    status: pending              # pending | claimed | done | rejected
    subject: Dashboard F3 — research de la vista feed
    requires_approval: false     # true ⇒ el socio aprueba/rechaza desde el menú
    ts: 2026-06-12T10:15:30
    hilo: <id del primer mensaje>   # ┐ opcionales · modo colaboración
    en_respuesta_a: <id>            # │ el mensaje que contesta
    proyecto: <slug>                # │ agrupa hilos; separa pestañas
    de_maquina: <etiqueta>          # │ ┐ el SOBRE: lo estampa el código desde
    de_maquina_id: <id>             # │ │ maquinas.maquina() y el entorno de la
    de_sesion: <id de pestaña>      # │ │ pestaña (WORKSPACE_WID / _WS / el motor);
    de_pestana: <nombre visible>    # │ │ el modelo nunca lo escribe. Sin esas
    de_motor: <motor>               # │ ┘ variables, el campo no va.
    para_maquina: <etiqueta>        # │ solo esa máquina lo atiende
    para_sesion: <id de pestaña>    # │ solo esa pestaña lo atiende
    resumen: <1-3 líneas, ≤280>     # │ obligatorio en el CLI si hay hilo
    objetivo: / hecho_cuando: / max_turnos:   # ┘ contrato, en el 1er mensaje
    resolved:                    # ISO al cerrar (done/rejected); vacío antes
    ---

    Cuerpo libre (alcance, entregable esperado, contexto…).

Semántica de `requires_approval`: el mensaje es una SOLICITUD; `done` =
aprobado, `rejected` = rechazado. Para el resto: `claimed` = el agente lo
tomó, `done` = entregado.

Modo colaboración (dos agentes conversan por el bus en la sesión visible del
socio; nada sin ventana). Los campos marcados son opcionales: un mensaje sin
ellos se lee, se lista y se verifica como siempre, y solo se escriben los que
traen valor. `colaborar iniciar` abre el hilo (hilo = su propio id) dentro de
un proyecto; su `para_*` va vacío (salvo `--maquina`): lo toma la primera
pestaña que lo reclame. `reply` hereda hilo y proyecto si el original los
tiene (una respuesta a un encargo de siempre sigue siendo de siempre) y su
`para_*` es el `de_*` del original: vuelve a la máquina y a la pestaña que
preguntó. `type: cierre` cierra el hilo con el resultado. Con máquina y
pestaña, el mismo agente en dos máquinas (un cerebro sincronizado) o en dos
pestañas no se contesta a sí mismo ni atiende lo de la otra.

Un hilo nuevo sin destino lo pueden reclamar dos MÁQUINAS a la vez (el
candado del archivo no cruza Obsidian Sync). Desempate fijo: quien lo reclama
deja `msgs/_reclamos/<id>--<máquina>.md` con su hora y, si el cerebro está en
otra máquina, espera ASIENTO_S a que lleguen los reclamos de las demás; gana
el de menor (hora, máquina) — todas calculan lo mismo con los mismos
archivos. La que pierde no lo entrega, y si el sync llegó tarde, `reply` y
`colaborar cerrar` se niegan a hablar en ese hilo («me retiro»).

API (la usan Zenith/Atlas/Argus y la sección MENSAJES de front.py):

    send(from_agent, to_agent, type, subject, body="", requires_approval=False)
        → escribe el .md en el cerebro del destinatario; devuelve lista de ids
          escritos (to_agent="all" hace fan-out a todos menos el emisor).
    inbox(brain, agent, statuses=("pending",))   → pendientes PARA ese agente.
    all_messages(brains=None, statuses=None)     → todos, más reciente primero.
    set_status(msg_id, status)                   → edición ATÓMICA y acotada
          del frontmatter (solo `status:` + `resolved:` al cerrar).
    find(msg_id) / registered_brains()           → lookup y resolución.

CLI (para agentes en terminal):
    python3 messages.py send --from zenith --to atlas --type encargo \
        --subject "..." [--body "..."] [--approval] [--resumen "..."]
    python3 messages.py inbox <agente>
    python3 messages.py list [--status pending]
    python3 messages.py status <msg_id> <pending|claimed|done|rejected>
    python3 messages.py reply <msg_id> "<texto>" [--from <agente>] [--resumen "..."]
    python3 messages.py colaborar iniciar --con agente-b --proyecto <slug> \
        --tarea "..." --resumen "..." [--maquina <etiqueta|mac|pc>] [--pestana "<nombre>"] \
        [--from agente-a]
    python3 messages.py esperar agente-a [--hilo <id>] [--proyecto <slug>] [--timeout 90]
    python3 messages.py colaborar cerrar <id> --resultado "..." --resumen "..." \
        [--from agente-a]
    python3 messages.py hilo <id> [--completo]   # la conversación, en orden
    python3 messages.py conversar <abrir|publicar|esperar|ver|soltar|delegar|…>
        # salas de varios agentes (salas.py): una sala con un hogar,
        # menciones y deudas con espera; el modo de colaborar vigente

`esperar` es long-poll por archivos (sin daemon, sin watchdog): lo corre el
propio agente, en segundo plano si su motor avisa al terminar, o en primer
plano con timeout corto y en bucle. Entrega los mensajes PENDIENTES de un hilo
dirigidos a ese agente, a esta máquina y a esta pestaña (o sin pestaña: el
primero de un hilo nuevo), los marca `claimed` con compare-and-set bajo el
candado del mensaje (de dos pestañas que esperan, una sola lo toma; el «visto»
es el status, sin archivos ocultos) y sale 0; al vencer el timeout sale 3 (el
2 es el de un error de argumentos). Un `cierre` recibido marca `done` lo de
ese hilo. Los mensajes sin `hilo` (encargos de siempre) no lo despiertan: para
esos está `inbox`.

Presencia (sin daemon): mientras `esperar` bloquea, late cada LATIDO_S en
`msgs/_presencia/<agente>--<pestaña>.md` (quién, máquina, pestaña, motor,
hilos, si escucha, cuándo se le vio y la huella del proceso). estado_lado()
dice de cada lado si está escuchando, trabajando (viva pero en su turno) o
cerrada: en esta máquina con el proceso y el registro de pestañas abiertas,
en otra por la hora del último latido. Con `--hilo`, `esperar` sale con 4 si
el otro lado lleva OTRO_LADO_MIN cerrado; `reply` y `colaborar iniciar`
avisan en una línea si quien recibe no está escuchando.

Garantías: cero dependencias (stdlib, Python 3.9+), Mac/Windows; append-only
(send JAMÁS sobrescribe — sufijo -N ante colisión) y la única edición permitida
es set_status (escritura atómica vía tmp + os.replace); anti-traversal (ids y
nombres saneados + guard realpath dentro de msgs/); falla-suave ABSOLUTA (toda
la API devuelve []/None/False en vez de levantar). Cada send/set_status emite
un record `agent_msg` al rastro N10 (events.py) — mismo dato, dos lectores.
"""
import datetime as _dt
import os
import re
import sys
import time

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:                                      # N8 — lock cross-platform (amputable)
    from olock import file_lock, LockTimeout
except Exception:                         # sin olock → degrada a sin-lock
    file_lock, LockTimeout = None, None

# helpers compartidos del framework dash (read_frontmatter/inside/slug…).
# Falla-suave: si dash/ no está (instalación rota), fallbacks mínimos locales.
try:
    from dash._common import inside as _inside, read_file as _read_file, \
        read_frontmatter as _read_frontmatter, slug as _slug
except Exception:                                    # pragma: no cover - defensa
    def _inside(base, path):
        b, p = os.path.realpath(base), os.path.realpath(path)
        return p == b or p.startswith(b + os.sep)

    def _read_file(path, limit=120_000):
        try:
            with open(path, encoding="utf-8", errors="replace") as fh:
                return fh.read(limit)
        except Exception:
            return ""

    def _read_frontmatter(text):
        fm = {}
        m = re.match(r"^---\s*\n(.*?)\n---", text or "", re.S)
        if m:
            for line in m.group(1).splitlines():
                if ":" in line and not line.strip().startswith("#"):
                    k, v = line.split(":", 1)
                    fm[k.strip().lower()] = v.strip()
        return fm

    def _slug(text, maxlen=60):
        s = re.sub(r"[^a-z0-9]+", "-", str(text or "").lower()).strip("-")
        return s[:maxlen].strip("-") or "item"


MSGS_DIR = "msgs"
TYPES = ("encargo", "handoff", "broadcast", "reply", "diff-review", "cierre")
STATUSES = ("pending", "claimed", "done", "rejected", "awaiting-diff-gate")
FINAL = ("done", "rejected")                # cierran el mensaje → sellan resolved
#: Campos opcionales del modo colaboración, en el orden en que se escriben y se
#: firman. Un mensaje sin ninguno se escribe y se verifica como antes.
CAMPOS_COLAB = ("hilo", "en_respuesta_a", "proyecto",
                # el sobre: lo estampa el código (sobre()), nunca el modelo
                "de_maquina", "de_maquina_id", "de_sesion", "de_pestana", "de_motor",
                "para_maquina", "para_sesion", "resumen",
                # contrato del hilo (solo en su primer mensaje)
                "objetivo", "hecho_cuando", "max_turnos")
MAX_TURNOS = 20               # tope de mensajes por hilo si el que lo abre no da otro
#: La pestaña: id ESTABLE que exporta el motor al elegirla (sobrevive a cerrar
#: y reanudar; WORKSPACE_SESSION_ID, en cambio, es nuevo en cada apertura).
SESION_ENV = "WORKSPACE_WID"
PESTANA_ENV = "WORKSPACE_WS"                  # su nombre visible
MOTOR_ENV = "WORKSPACE_SESSION_ENGINE"        # la marca del lanzador (engines.mark_session_engine)
RECLAMOS_DIR = "_reclamos"    # msgs/_reclamos/<id>--<máquina>.md: viaja (es .md), _scan no lo lee
ASIENTO_S = 10.0              # s que un reclamo disputado espera los de otras máquinas
PRESENCIA_DIR = "_presencia"  # msgs/_presencia/<agente>--<pestaña>.md: el latido de `esperar`
LATIDO_S = 60                 # cada cuánto late `esperar` (no más seguido: es ruido de sync)
FRESCA_S = 150                # otra máquina: «escuchando» si su último latido es así de nuevo
VIVA_S = 20 * 60              # otra máquina: «trabajando» si se le vio hace menos que esto
OTRO_LADO_MIN = 10            # `esperar` se rinde si el otro lado lleva esto cerrado
SALIDA_OTRO_LADO = 4          # exit de `esperar` cuando el otro lado no está
_CLIP_RESUMEN = 280
ESPERAR_TIMEOUT = 90          # s · cabe en el timeout por defecto de la shell de los motores
ESPERAR_INTERVALO = 2.0       # s entre sondeos (un listado de msgs/; solo se parsea lo cambiado)
SALIDA_TIMEOUT = 3            # exit de `esperar` sin mensajes (2 = error de argparse)

_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")   # sin / \ ni '.' inicial
_NAME_RE = re.compile(r"[^a-z0-9_-]")
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---[ \t]*\r?\n?", re.S)
_CLIP_SUBJECT = 160
_CLIP_BODY = 20_000


# ── HMAC de autenticidad (F1.5 cond 5) ──────────────────────────────────────
# `from`/`requires_approval` del frontmatter son FORJABLES (cualquiera escribe un
# .md). Para el procesamiento AUTÓNOMO de alto riesgo (write-scoped), firmamos el
# mensaje con un HMAC per-máquina: quien escribe con este messages.py firma; un
# .md forjado a mano (o de otra máquina) NO valida → no se auto-procesa. Clave
# per-máquina en ~/.workspace/bus/hmac.key (gitignored, NO se sincroniza). v1
# single-machine (opt-in en la Mac del socio); la auth cross-máquina es F2.
# Amputable: sin la clave, verify() = False (fail-closed para autónomo).
def _hmac_key_path():
    return os.path.join(os.path.expanduser("~"), ".workspace", "bus", "hmac.key")


def _hmac_key():
    """Clave HMAC per-máquina (la crea al primer uso). None si no se pudo."""
    p = _hmac_key_path()
    try:
        if os.path.isfile(p):
            with open(p, "rb") as fh:
                k = fh.read().strip()
            if k:
                return k
        os.makedirs(os.path.dirname(p), exist_ok=True)
        k = os.urandom(32).hex().encode("ascii")
        fd = os.open(p, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        try:
            os.write(fd, k)
        finally:
            os.close(fd)
        return k
    except FileExistsError:
        try:
            with open(p, "rb") as fh:
                return fh.read().strip() or None
        except OSError:
            return None
    except OSError:
        return None


def _campos_colab(d):
    """{campo: valor} de CAMPOS_COLAB sacados de `d` (dict o None), como texto."""
    d = d if isinstance(d, dict) else {}
    return {k: str(d.get(k) or "").strip() for k in CAMPOS_COLAB}


def _sign(sender, to, mtype, subj, approval, ts, body, extra=None):
    """HMAC-SHA256 del mensaje completo (incluye requires_approval y ts → no
    forjables). `extra` = dict con los CAMPOS_COLAB: si trae alguno, entran
    todos a la firma (nombre=valor, en orden fijo); sin ninguno la firma es
    idéntica a la de antes, así los mensajes viejos siguen validando. Devuelve
    hexdigest o "" si no hay clave (amputable)."""
    import hashlib
    import hmac as _hmac
    key = _hmac_key()
    if not key:
        return ""
    # el body se firma NORMALIZADO igual que lo devuelve _parse (.strip()) — si no,
    # el '\n' final del archivo escrito rompería el roundtrip firma/verify.
    # Saltos de línea normalizados: al releer, universal-newlines convierte
    # \r\n y \r sueltos en \n — un body con CRLF fallaba verify() y el
    # autónomo lo trataba como forjado (auditoría 2026-07).
    nbody = str(body or "").replace("\r\n", "\n").replace("\r", "\n").strip()
    partes = [str(sender), str(to), str(mtype), str(subj),
              "1" if approval else "0", str(ts), nbody]
    campos = _campos_colab(extra)
    if any(campos.values()):          # quitar o agregar uno a mano rompe la firma
        partes += ["%s=%s" % (k, campos[k]) for k in CAMPOS_COLAB]
    payload = "\x1f".join(partes)
    return _hmac.new(key, payload.encode("utf-8", "replace"), hashlib.sha256).hexdigest()


def normalizar(valor):
    """Un campo como se FIRMA: saltos de línea unificados (\\r\\n y \\r → \\n),
    sin espacios al final de cada línea ni en los bordes. Así un archivo que
    pasó por Windows, Obsidian o el sync (CRLF, espacios colgando) firma igual
    y la firma solo se rompe si cambió el contenido."""
    s = str(valor if valor is not None else "").replace("\r\n", "\n").replace("\r", "\n")
    return "\n".join(ln.rstrip() for ln in s.split("\n")).strip()


def firmar_campos(pares):
    """HMAC-SHA256 (clave per-máquina, la misma de los mensajes) de una lista
    ordenada de (campo, valor), cada valor normalizado. '' si no hay clave.
    Para quien guarda registros propios sobre el bus (salas.py) sin duplicar
    la clave ni el algoritmo."""
    import hashlib
    import hmac as _hmac
    key = _hmac_key()
    if not key:
        return ""
    payload = "\x1f".join("%s=%s" % (str(k), normalizar(v)) for k, v in pares)
    return _hmac.new(key, payload.encode("utf-8", "replace"), hashlib.sha256).hexdigest()


def firma_valida(pares, firma):
    """True/False si `firma` cuadra con los campos; None si en esta máquina no
    hay clave (no se puede saber: nunca se reporta como alterado). Con clave,
    una firma que ni se puede comparar (p. ej. con letras no ASCII:
    compare_digest levanta) es False, no «sin clave» (revisión fría,
    hallazgo 14)."""
    try:
        import hmac as _hmac
        if not _hmac_key():
            return None
        got = firmar_campos(pares)
    except Exception:
        return None
    try:
        return bool(got and firma) and _hmac.compare_digest(str(got).encode("utf-8"),
                                                            str(firma).encode("utf-8"))
    except Exception:
        return False


def verify(msg):
    """True si el `hmac` del mensaje valida con la clave per-máquina. False si
    falta, no valida, o no hay clave (fail-closed: el autónomo NO procesa lo no
    autenticado). Los mensajes viejos (sin hmac) → False → no se auto-procesan."""
    try:
        import hmac as _hmac
        if not isinstance(msg, dict):
            return False
        want = msg.get("hmac") or ""
        if not want:
            return False
        got = _sign(msg.get("from", ""), msg.get("to", ""), msg.get("type", ""),
                    msg.get("subject", ""), bool(msg.get("requires_approval")),
                    msg.get("ts", ""), msg.get("body", ""), extra=msg)
        return bool(got) and _hmac.compare_digest(got, want)
    except Exception:
        return False


def _safe_name(name):
    """Nombre de agente saneado (minúsculas, [a-z0-9_-], ≤24). '' si no queda nada."""
    return _NAME_RE.sub("", str(name or "").strip().lower())[:24]


def _safe_id(mid):
    """Id de mensaje válido (sin / \\ ni '.' inicial) o ''."""
    mid = str(mid or "").strip()
    return mid if _ID_RE.match(mid) else ""


# ── Máquina, pestaña y textos cortos (modo colaboración) ───────────────────
def _etiqueta(valor):
    """Etiqueta de máquina saneada con la MISMA regla que maquinas.etiqueta_host
    (minúsculas, ASCII, [a-z0-9-]): una sola línea, segura en el frontmatter.
    '' si viene vacía."""
    s = str(valor or "").strip()
    if not s:
        return ""
    try:
        import maquinas
        return maquinas.etiqueta_host(s)
    except Exception:
        return re.sub(r"[^a-z0-9]+", "-", s.lower().split(".")[0]).strip("-")[:32]


def mi_maquina():
    """ESTA máquina: {"etiqueta", "id", "alias"} — la etiqueta y el id de
    maquinas.maquina() (sin `maquina.json` todavía: la del hostname y sin id)
    y el conjunto de nombres con los que un mensaje puede dirigirse a ella
    (etiqueta guardada, la del hostname actual, el id). Solo lee: no crea el
    estado. Vacío si no se sabe."""
    try:
        import maquinas
        d = maquinas.maquina(crear=False) or {}
        actual = maquinas.etiqueta_host()
        eti = str(d.get("etiqueta") or actual)
        ident = str(d.get("id") or "")
        return {"etiqueta": eti, "id": ident,
                "alias": {x for x in (eti, actual, ident) if x}}
    except Exception:
        return {"etiqueta": "", "id": "", "alias": set()}


def _safe_sesion(valor):
    """Id de pestaña saneado ([A-Za-z0-9._-], ≤64) o ''."""
    return re.sub(r"[^A-Za-z0-9._-]", "", str(valor or "").strip())[:64]


def mi_sesion():
    """Id de la pestaña en la que corre este proceso (WORKSPACE_WID, que el
    motor exporta al elegirla y que se conserva al cerrarla y reanudarla). ''
    fuera de una pestaña de Workspace (motor lanzado a mano): entonces los
    mensajes van sin `de_sesion` y se reparten como antes de las pestañas."""
    return _safe_sesion(os.environ.get(SESION_ENV))


def sobre():
    """El sobre de quien escribe desde ESTE proceso: máquina (etiqueta + id),
    pestaña (id estable + nombre visible) y motor. Sale del estado de la
    máquina y del entorno que el lanzador de Workspace exporta al abrir la
    pestaña — nunca de lo que diga el modelo. Lo que no se sabe va vacío (y
    no se escribe): un motor abierto fuera del hub no inventa pestaña."""
    yo = mi_maquina()
    return {"de_maquina": _etiqueta(yo.get("etiqueta")),
            "de_maquina_id": _safe_sesion(yo.get("id")),
            "de_sesion": mi_sesion(),
            "de_pestana": _corto(os.environ.get(PESTANA_ENV), 80, 1),
            "de_motor": _safe_name(os.environ.get(MOTOR_ENV))}


def _corto(texto, limite=_CLIP_RESUMEN, lineas=3):
    """Texto libre → UNA línea segura para el frontmatter: sin caracteres de
    control, hasta `lineas` líneas unidas con « · », recortado a `limite`."""
    s = re.sub(r"[\x00-\x09\x0b-\x1f\x7f]", " ", str(texto or ""))
    partes = [" ".join(ln.split()) for ln in s.splitlines() if ln.strip()][:lineas]
    out = " · ".join(partes)
    return out if len(out) <= limite else out[:limite - 1].rstrip() + "…"


def _proyecto(valor):
    """Slug de proyecto ([a-z0-9-], ≤40) o '' si no hay."""
    return _slug(valor, 40) if str(valor or "").strip() else ""


def _constancias(brain):
    try:
        import maquinas
        return maquinas.constancias(brain) if brain else []
    except Exception:
        return []


def resolver_maquina(valor, brain=""):
    """`--maquina` → (etiqueta, aviso). Acepta la etiqueta o el id de una
    máquina, o su tipo («mac», «pc»/«windows», «linux») si en el cerebro hay
    UNA sola de ese tipo (sus constancias STATE/maquinas/). Si no casa con
    ninguna conocida, se usa tal cual y `aviso` lo dice (nadie lo atendería)."""
    eti = _etiqueta(valor)
    if not eti or not brain:
        return eti, ""
    conocidas = _constancias(brain)
    if not conocidas:
        return eti, ""
    for c in conocidas:
        if eti in (_etiqueta(c.get("etiqueta")), c.get("id")):
            return _etiqueta(c.get("etiqueta")) or eti, ""
    tipo = {"mac": "mac", "pc": "windows", "windows": "windows", "win": "windows",
            "linux": "linux"}.get(eti)
    del_tipo = [c for c in conocidas if tipo and c.get("so") == tipo and c.get("etiqueta")]
    if len(del_tipo) == 1:
        return _etiqueta(del_tipo[0].get("etiqueta")), ""
    nombres = ", ".join(sorted({_etiqueta(c.get("etiqueta")) for c in conocidas
                                if c.get("etiqueta")}))
    return eti, ("ninguna máquina conocida se llama «%s» (conocidas: %s)"
                 % (eti, nombres or "ninguna"))


def _me_toca(m, agente, alias, sesion=""):
    """¿El mensaje `m` (para `agente`) le toca a ESTA máquina y ESTA pestaña?
    No si va dirigido a otra máquina (`para_maquina`) o a otra pestaña
    (`para_sesion`), ni si es mío para mí mismo y salió de aquí (de esta
    máquina y de esta pestaña, o sin pestaña). Sin campos: sí, como siempre."""
    para = _etiqueta(m.get("para_maquina"))
    if para and para not in alias:
        return False
    ps = _safe_sesion(m.get("para_sesion"))
    if ps and ps != sesion:
        return False
    de = _etiqueta(m.get("de_maquina"))
    if (de and de in alias and m.get("from") == m.get("to") == agente
            and _safe_sesion(m.get("de_sesion")) in ("", sesion)):
        return False
    return True


def registered_brains():
    """{agente: ruta_del_cerebro} de los agentes del registry, resueltos igual
    que el dispatcher (paths.local.json → agent.json). Solo cerebros que
    existen en esta máquina. Falla-suave: {}."""
    out = {}
    try:
        import dispatch
        for entry in dispatch.load_registry().get("agents", []):
            try:
                cfg = dispatch.load_agent_cfg(entry)
            except Exception:
                cfg = {}
            b = dispatch.resolve_brain(entry["name"], cfg)
            if b and os.path.isdir(b):
                out[entry["name"]] = b
    except Exception:
        pass
    return out


def _brain_paths(brains):
    """Normaliza el parámetro `brains` (None → registry · dict → values ·
    lista → tal cual) a una lista de rutas sin duplicados (realpath)."""
    if brains is None:
        brains = registered_brains()
    paths = list(brains.values()) if isinstance(brains, dict) else list(brains or [])
    seen, out = set(), []
    for p in paths:
        if not p:
            continue
        key = os.path.normcase(os.path.realpath(p))
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def _emit(action, m):
    """Espejo al rastro unificado N10 (events.py). Best-effort, jamás levanta."""
    try:
        import events
        events.record("agent_step",
                      payload={"event": "agent_msg", "action": action,
                               "id": m.get("id", ""), "from": m.get("from", ""),
                               "to": m.get("to", ""), "type": m.get("type", ""),
                               "status": m.get("status", "")},
                      source="messages", agent=m.get("to", ""),
                      brain=m.get("brain", ""))
    except Exception:
        pass


def _atomic_write(path, text):
    """Escribe `text` en `path` vía tmp + os.replace (atómico en el mismo dir):
    nunca queda un mensaje a medias aunque el proceso muera escribiendo. Con
    el helper común (atomico): reintenta si Windows tiene el archivo abierto
    un instante (antivirus, Obsidian) y, si no se logra, borra el temporal,
    lo dice en stderr y relanza — el bus ya no falla en silencio."""
    import atomico
    atomico.escribir(path, text, avisar=True)


def _bus_secret_block(subj, body, strict=False):
    """A7 · True (y avisa a stderr CÓMO saltarlo) si subject+body trae un secreto
    sin exención. El bus se sincroniza por Obsidian a TODOS los cerebros, así que
    un secreto pegado en una delegación llega a todo el equipo antes de cualquier
    WARN post-hoc. Pasamos por el MISMO gate duro de las escrituras al cerebro
    (escapes: `workspace:allow-secret` por línea / WORKSPACE_ALLOW_SECRET).
    `strict` (F1.5 cond 5): FAIL-CLOSED — sin secret_scan BLOQUEA (el relay
    autónomo NO envía sin escanear). Interactivo: fail-open (no rompe el bus)."""
    try:
        import secret_scan
    except Exception:
        if strict:
            # relay autónomo: sin gate NO se envía (fail-closed). Un dispatch
            # sandbox no debe filtrar al vault sin escaneo.
            try:
                print("⚠ relay autónomo BLOQUEADO: secret_scan no disponible "
                      "(fail-closed)", file=sys.stderr)
            except Exception:
                pass
            return True
        # interactivo · fail-open pero JAMÁS mudo (falla-suave, no muda): rastro a
        # stderr ANTES de dejar pasar; el envío NO se bloquea (no romper el bus).
        try:
            print("⚠ bus sin gate de secretos (secret_scan no disponible) — "
                  "el mensaje se envía SIN escanear", file=sys.stderr)
        except Exception:
            pass
        return False
    text = (subj or "") + "\n" + (body or "")
    # STRICT (relay autónomo): NO delegar la decisión a gate_text. gate_text es
    # fail-soft POR DISEÑO (regla 6: un crash no bloquea) y devuelve [] tanto si
    # el override de entorno está activo como si el escáner se cayó — o sea, los
    # dos caminos reales por los que el gate queda ciego eran fail-OPEN aquí,
    # pese a que el docstring promete fail-closed. Auditoría 2026-07: solo el
    # ImportError estaba cubierto.
    if strict:
        # (a) WORKSPACE_ALLOW_SECRET es un escape INTERACTIVO (el socio decide con
        # el contenido enfrente). El relay autónomo no tiene a quién preguntarle:
        # si el daemon heredó la env var del shell del socio, bloquea igual.
        try:
            if secret_scan.env_override_active():
                try:
                    print("⚠ relay autónomo BLOQUEADO: WORKSPACE_ALLOW_SECRET está "
                          "activo — el override es interactivo, no aplica al bus "
                          "autónomo (fail-closed)", file=sys.stderr)
                except Exception:
                    pass
                return True
        except Exception:
            return True          # ni eso se pudo evaluar → bloquear
        # (b) escanear directo: si scan_text levanta, BLOQUEAR (no publicar sin gate).
        try:
            findings = secret_scan.scan_text(text)
        except Exception as exc:
            try:
                print("⚠ relay autónomo BLOQUEADO: el escáner falló (%s) — no se "
                      "publica sin escanear (fail-closed)" % type(exc).__name__,
                      file=sys.stderr)
            except Exception:
                pass
            return True
        if findings:
            try:
                print(secret_scan.block_message(findings, "mensaje del bus"),
                      file=sys.stderr)
            except Exception:
                pass
            return True
        return False
    try:
        findings = secret_scan.gate_text(text, where="mensaje del bus")
        if findings:
            try:
                print(secret_scan.block_message(findings, "mensaje del bus"),
                      file=sys.stderr)
            except Exception:
                pass
            return True
    except Exception:
        # interactivo → fail-open (no romper el bus). El strict ya retornó arriba,
        # así que aquí `strict` es False; se deja explícito por si eso cambia.
        return bool(strict)
    return False


# ═══════════════════════════════════════════════════════════════════════════
# Escritura: send (append-only — jamás sobrescribe)
# ═══════════════════════════════════════════════════════════════════════════

def send(from_agent, to_agent, type, subject, body="", requires_approval=False,
         brains=None, strict=False, hilo="", en_respuesta_a="", proyecto="",
         para_maquina="", para_sesion="", resumen="", contrato=None, nuevo_hilo=False,
         _sobre=None):
    """Escribe el mensaje en `<cerebro-destinatario>/msgs/<id>.md`.

    `to_agent="all"` (o type="broadcast" sin destinatario) → fan-out: un
    archivo por cada agente registrado distinto del emisor, cada uno con su
    propio id. `brains` (opcional) debe ser dict {agente: cerebro}; None →
    registry. `strict` (F1.5): secret-gate FAIL-CLOSED (relay autónomo — sin
    secret_scan NO envía). Modo colaboración (todo opcional): `hilo` y
    `en_respuesta_a` (ids), `proyecto` (slug), `para_maquina` (etiqueta),
    `para_sesion` (pestaña), `resumen` (1-3 líneas), `contrato` (dict con
    objetivo/hecho_cuando/max_turnos, para el primer mensaje) y
    `nuevo_hilo=True` (el hilo es el id de este mismo mensaje). El sobre
    (`de_*`) lo pone solo, desde sobre(); `_sobre` existe SOLO para que las
    pruebas lo fijen — ningún comando lo expone. El resumen y el contrato
    pasan por el gate de secretos y todo entra a la firma. Devuelve la lista
    de ids escritos ([] si nada)."""
    try:
        mtype = str(type or "").strip().lower()
        sender = _safe_name(from_agent)
        subj = " ".join(str(subject or "").split())[:_CLIP_SUBJECT]
        if mtype not in TYPES or not sender or not subj:
            return []
        ct = contrato if isinstance(contrato, dict) else {}
        try:
            turnos = int(ct.get("max_turnos") or 0)
        except (TypeError, ValueError):
            turnos = 0
        de = sobre()
        if isinstance(_sobre, dict):
            de.update({k: str(v or "") for k, v in _sobre.items() if k in de})
        extra = {"hilo": _safe_id(hilo), "en_respuesta_a": _safe_id(en_respuesta_a),
                 "proyecto": _proyecto(proyecto),
                 "de_maquina": _etiqueta(de["de_maquina"]),
                 "de_maquina_id": _safe_sesion(de["de_maquina_id"]),
                 "de_sesion": _safe_sesion(de["de_sesion"]),
                 "de_pestana": _corto(de["de_pestana"], 80, 1),
                 "de_motor": _safe_name(de["de_motor"]),
                 "para_maquina": _etiqueta(para_maquina),
                 "para_sesion": _safe_sesion(para_sesion),
                 "resumen": _corto(resumen),
                 "objetivo": _corto(ct.get("objetivo")),
                 "hecho_cuando": _corto(ct.get("hecho_cuando")),
                 "max_turnos": str(turnos) if turnos > 0 else ""}
        bm = brains if isinstance(brains, dict) else registered_brains()
        to_raw = str(to_agent or "").strip().lower()
        if to_raw in ("all", "*", "todos") or (mtype == "broadcast" and not to_raw):
            targets = [a for a in sorted(bm) if _safe_name(a) != sender]
        else:
            targets = [to_raw]
        gbody = (str(body or "").replace("\r\n", "\n")
                 .replace("\r", "\n"))[:_CLIP_BODY]
        # A7 · gate de secretos ANTES de escribir: el cuerpo se sincroniza a todos
        # los cerebros; un secreto ahí ya es una fuga de equipo. Bloquea (no envía
        # nada) y dice cómo saltarlo; falla-suave si secret_scan no está.
        cortos = "\n".join(extra[k] for k in ("resumen", "objetivo", "hecho_cuando")
                           if extra[k])
        if _bus_secret_block(subj + ("\n" + cortos if cortos else ""), gbody,
                             strict=strict):
            return []
        ts = _dt.datetime.now()
        ids = []
        for target in targets:
            to = _safe_name(target)
            brain = bm.get(target) or bm.get(to) or ""
            if not to or not brain or not os.path.isdir(brain):
                continue
            mid = _write_one(brain, sender, to, mtype, subj,
                             gbody, bool(requires_approval), ts,
                             extra=extra, nuevo_hilo=nuevo_hilo)
            if mid:
                ids.append(mid)
        return ids
    except Exception:
        return []


def _write_one(brain, sender, to, mtype, subj, body, approval, ts, extra=None,
               nuevo_hilo=False):
    """Un archivo de mensaje en `brain/msgs/`. Devuelve el id o None. `extra`:
    CAMPOS_COLAB (solo se escriben los que traen valor); `nuevo_hilo` → el
    hilo es el id que este mensaje reclama."""
    try:
        mdir = os.path.join(brain, MSGS_DIR)
        os.makedirs(mdir, exist_ok=True)
        base = "%s-%s-%s-%s-%s" % (ts.strftime("%Y%m%dT%H%M%S"),
                                   sender, to, mtype, _slug(subj, 40))
        mid, n, fd, fp = base, 1, None, ""
        while fd is None:
            fp = os.path.join(mdir, mid + ".md")
            if not _ID_RE.match(mid) or not _inside(mdir, fp):
                return None                          # anti-traversal (defensa doble)
            try:                  # O_EXCL: reclama el id de forma atómica — dos
                fd = os.open(fp,  # sends del mismo segundo NO se pisan (TOCTOU)
                             os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:                  # append-only: sufijo -N
                n += 1
                mid = "%s-%d" % (base, n)
        os.close(fd)
        ts_iso = ts.isoformat(timespec="seconds")
        gbody = body.rstrip() + "\n" if body.strip() else ""
        campos = _campos_colab(extra)
        if nuevo_hilo:
            campos["hilo"] = mid
        # HMAC de autenticidad (F1.5 cond 5): firma from/to/type/subject/approval/
        # ts/body (+ los del modo colaboración si los hay) → el autónomo rechaza
        # mensajes forjados. Amputable (clave ausente → "" → no rompe; el
        # autónomo cae a no-procesar).
        sig = _sign(sender, to, mtype, subj, approval, ts_iso, gbody, extra=campos)
        lineas_colab = "".join("%s: %s\n" % (k, campos[k]) for k in CAMPOS_COLAB if campos[k])
        text = ("---\n"
                "id: %s\n"
                "from: %s\n"
                "to: %s\n"
                "type: %s\n"
                "status: pending\n"
                "subject: %s\n"
                "requires_approval: %s\n"
                "ts: %s\n"
                "%s"
                "hmac: %s\n"
                "resolved:\n"
                "---\n\n%s" % (mid, sender, to, mtype, subj,
                               "true" if approval else "false",
                               ts_iso, lineas_colab, sig, gbody))
        try:
            _atomic_write(fp, text)                  # contenido completo o nada
        except Exception:
            try:
                os.remove(fp)                        # no dejar el claim vacío
            except OSError:
                pass
            return None
        _emit("send", {"id": mid, "from": sender, "to": to, "type": mtype,
                       "status": "pending", "brain": brain})
        return mid
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Lectura: inbox / all_messages / find (read-only, falla-suave)
# ═══════════════════════════════════════════════════════════════════════════

def _parse(path, brain=""):
    """Un msgs/*.md → dict normalizado, o None si no parsea como mensaje."""
    text = _read_file(path, 60_000)
    fm = _read_frontmatter(text)
    if not fm or "from" not in fm:
        return None
    try:
        mt = os.path.getmtime(path)
    except OSError:
        mt = 0
    return {
        "id": os.path.basename(path)[:-3],           # el filename ES el id (estable)
        "from": fm.get("from", ""),
        "to": fm.get("to", ""),
        "type": fm.get("type", ""),
        "status": fm.get("status", "pending") or "pending",
        "subject": fm.get("subject", ""),
        "requires_approval": str(fm.get("requires_approval", "")).strip().lower()
                             in ("true", "1", "yes", "si", "sí"),
        "ts": fm.get("ts", ""),
        "hmac": fm.get("hmac", ""),
        "resolved": fm.get("resolved", ""),
        # modo colaboración ('' en los mensajes de antes)
        **{k: fm.get(k, "") for k in CAMPOS_COLAB},
        "body": _FM_RE.sub("", text, count=1).strip(),
        "path": path,
        "brain": brain or os.path.dirname(os.path.dirname(path)),
        "mtime": mt,
    }


def _scan(brain):
    """Todos los mensajes de `brain/msgs/`. Salta README, `_*` y ocultos."""
    out = []
    mdir = os.path.join(brain or "", MSGS_DIR)
    if not brain or not os.path.isdir(mdir):
        return out
    try:
        files = sorted(os.listdir(mdir))
    except OSError:
        return out
    for f in files:
        if (not f.endswith(".md") or f.startswith(("_", "."))
                or f.lower() == "readme.md"):
            continue
        fp = os.path.join(mdir, f)
        if not os.path.isfile(fp) or not _inside(mdir, fp):
            continue
        m = _parse(fp, brain)
        if m:
            out.append(m)
    return out


def inbox(brain, agent, statuses=("pending",)):
    """Mensajes PARA `agent` en `brain/msgs/` con status en `statuses`
    (default: solo pendientes), más reciente primero. Falla-suave: []."""
    try:
        a = _safe_name(agent)
        out = [m for m in _scan(brain)
               if (not a or m["to"] == a)
               and (not statuses or m["status"] in statuses)]
        out.sort(key=lambda m: (m.get("ts") or "", m["id"]), reverse=True)
        return out
    except Exception:
        return []


def all_messages(brains=None, statuses=None, limit=200):
    """Todos los mensajes de todos los cerebros (`brains`=None → registry),
    más reciente primero. `statuses` filtra; `limit` acota. Falla-suave: []."""
    try:
        out = []
        for b in _brain_paths(brains):
            out.extend(_scan(b))
        if statuses:
            out = [m for m in out if m["status"] in statuses]
        out.sort(key=lambda m: (m.get("ts") or "", m["id"]), reverse=True)
        return out[:max(0, int(limit))]
    except Exception:
        return []


def find(msg_id, brains=None):
    """Mensaje por id (= filename sin .md) buscando en los cerebros. None si no."""
    try:
        mid = str(msg_id or "").strip()
        if not _ID_RE.match(mid):
            return None
        for b in _brain_paths(brains):
            mdir = os.path.join(b, MSGS_DIR)
            fp = os.path.join(mdir, mid + ".md")
            if os.path.isfile(fp) and _inside(mdir, fp):
                return _parse(fp, b)
        return None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Edición acotada: set_status (lo ÚNICO que este módulo reescribe)
# ═══════════════════════════════════════════════════════════════════════════

def set_status(msg_id, status, brains=None, solo_si=None):
    """Cambia `status:` en el frontmatter del mensaje (y sella `resolved:` si
    el status es final: done/rejected). Edición ATÓMICA (tmp + os.replace) y
    ACOTADA: solo esas líneas — cuerpo y demás campos quedan intactos.
    `solo_si` (tupla de status): compare-and-set — cambia solo si el status
    que hay en disco, leído DENTRO del candado, es uno de esos; si el candado
    no llega a tiempo no se arriesga (False). Así de dos pestañas de una
    máquina que reclaman, gana una.
    True si quedó en disco; False en cualquier otro caso (falla-suave)."""
    try:
        status = str(status or "").strip().lower()
        mid = str(msg_id or "").strip()
        if status not in STATUSES or not _ID_RE.match(mid):
            return False
        m = find(mid, brains)
        if not m:
            return False
        path = m["path"]

        def _rmw():
            # G: read-modify-write del frontmatter SERIALIZADO. _atomic_write ya
            # era atómico, pero el ciclo leer→reescribir no — dos set_status sobre
            # el mismo mensaje podían perder una transición.
            with open(path, encoding="utf-8") as fh:
                text = fh.read()
            fmatch = re.match(r"^---\s*\n(.*?)\n---", text, re.S)
            if not fmatch:
                return False
            if solo_si is not None:
                actual = (_read_frontmatter(text).get("status") or "pending").strip().lower()
                if actual not in solo_si:
                    return False
            lines, hit, sealed = [], False, False
            for ln in fmatch.group(1).splitlines():
                key = ln.split(":", 1)[0].strip().lower() if ":" in ln else ""
                if key == "status":
                    lines.append("status: " + status)
                    hit = True
                elif key == "resolved" and status in FINAL:
                    lines.append("resolved: " + _dt.datetime.now().isoformat(timespec="seconds"))
                    sealed = True
                elif key == "resolved" and status not in FINAL:
                    lines.append("resolved:")    # K: reabrir → limpiar el sello rancio
                else:
                    lines.append(ln)
            if not hit:
                lines.append("status: " + status)
            # edge: mensaje editado a mano sin línea `resolved:` — séllala al cerrar.
            if status in FINAL and not sealed:
                lines.append("resolved: " + _dt.datetime.now().isoformat(timespec="seconds"))
            new = text[:fmatch.start(1)] + "\n".join(lines) + text[fmatch.end(1):]
            _atomic_write(path, new)
            return True

        if file_lock is not None:
            try:
                with file_lock(path, timeout=5):
                    okw = _rmw()
            except LockTimeout:
                # degrada a sin-lock (mejor que perder el cambio), salvo un
                # compare-and-set: sin candado no hay garantía de un solo ganador.
                okw = False if solo_si is not None else _rmw()
        else:
            okw = _rmw()
        if not okw:
            return False
        m["status"] = status
        _emit("status", m)
        return True
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════
# CLI mínimo (para que los agentes manden/lean desde Bash)
# ═══════════════════════════════════════════════════════════════════════════

def reply(msg_id, body, from_agent=None, brains=None, resumen=""):
    """Responde a un mensaje existente sin re-escribir from/to: el que responde es su
    destinatario original (`to`), y va de vuelta a su remitente (`from`), type='reply',
    subject 'Re: <orig>'. Hace natural la ida y vuelta de delegación.

    Modo colaboración: hereda `hilo` y `proyecto` si el original los tiene, anota
    `en_respuesta_a` y vuelve a la máquina y a la pestaña de las que salió el
    original. Contestar = atendido: el original queda `done` si era para quien
    contesta y seguía pending/claimed — salvo que pida aprobación del socio (ahí
    `done` sería «aprobado», y eso no lo decide un agente). Devuelve los ids
    escritos ([] si el mensaje no existe / falla — falla-suave)."""
    m = find(msg_id, brains)
    if not m:
        return []
    frm = _safe_name(from_agent) if from_agent else m.get("to", "")
    if m.get("hilo") and hilo_de_otra_maquina(m["id"], frm, brains):
        return []                     # perdí el desempate: el hilo es de otra máquina
    to = m.get("from", "")
    subj = m.get("subject", "")
    if not subj.lower().startswith("re:"):
        subj = "Re: " + subj
    ids = send(frm, to, "reply", subj, body, brains=brains,
               hilo=_safe_id(m.get("hilo")), en_respuesta_a=m["id"],
               proyecto=m.get("proyecto", ""), para_maquina=m.get("de_maquina", ""),
               para_sesion=m.get("de_sesion", ""), resumen=resumen)
    if (ids and m.get("to") == frm and not m.get("requires_approval")
            and m.get("status") in ("pending", "claimed")):
        set_status(m["id"], "done", [m["brain"]], solo_si=("pending", "claimed"))
    return ids


# ═══════════════════════════════════════════════════════════════════════════
# Modo colaboración: hilo · esperar · iniciar · cerrar
# ═══════════════════════════════════════════════════════════════════════════

def _id_de_hilo(msg_id, brains=None):
    """Id del hilo al que pertenece `msg_id` (su `hilo`, o él mismo si es la
    raíz o no se encuentra). '' si el id no es válido."""
    mid = _safe_id(msg_id)
    if not mid:
        return ""
    m = find(mid, brains)
    return (_safe_id(m.get("hilo")) or mid) if m else mid


def _orden_causal(msgs):
    """Ordena un hilo: por `ts`; dentro del mismo segundo, el que contesta va
    después de lo que contesta (profundidad por `en_respuesta_a`)."""
    por_id = {m["id"]: m for m in msgs}
    prof = {}

    def _prof(m, vistos=()):
        if m["id"] in prof:
            return prof[m["id"]]
        padre = por_id.get(m.get("en_respuesta_a") or "")
        d = 0 if (padre is None or padre["id"] in vistos) else \
            1 + _prof(padre, vistos + (m["id"],))
        prof[m["id"]] = d
        return d

    return sorted(msgs, key=lambda m: (m.get("ts") or "", _prof(m), m["id"]))


def mensajes_hilo(msg_id, brains=None):
    """Todos los mensajes del hilo de `msg_id` (cualquiera del hilo sirve), de
    todos los cerebros, en orden de conversación. Falla-suave: []."""
    try:
        hid = _id_de_hilo(msg_id, brains)
        if not hid:
            return []
        out, vistos = [], set()
        for b in _brain_paths(brains):
            for m in _scan(b):
                if (m["id"] == hid or m.get("hilo") == hid) and m["id"] not in vistos:
                    vistos.add(m["id"])
                    out.append(m)
        return _orden_causal(out)
    except Exception:
        return []


def _tope_turnos(msgs):
    """(mensajes del hilo, tope de su contrato) — el tope sale del primer
    mensaje (`max_turnos`), MAX_TURNOS si no lo dice."""
    if not msgs:
        return 0, MAX_TURNOS
    hid = _safe_id(msgs[0].get("hilo")) or msgs[0]["id"]
    raiz = next((m for m in msgs if m["id"] == hid), msgs[0])
    try:
        tope = int(raiz.get("max_turnos") or 0) or MAX_TURNOS
    except (TypeError, ValueError):
        tope = MAX_TURNOS
    return len(msgs), tope


def _aviso_tope(msgs):
    n, tope = _tope_turnos(msgs)
    if n <= tope:
        return ""
    return ("aviso: el hilo lleva %d mensajes y su tope era %d — ciérralo "
            "(colaborar cerrar) o pregúntale al socio si sigue" % (n, tope))


def aviso_turnos(msg_id, brains=None):
    """UNA línea si el hilo de `msg_id` ya pasó el tope de turnos de su
    contrato; '' si no. Solo avisa: cerrar lo decide el agente con su socio."""
    return _aviso_tope(mensajes_hilo(msg_id, brains))


def _pendientes(brain, agente, cache):
    """Mensajes `pending` para `agente` en `brain/msgs/`. `cache` (dict que el
    llamador conserva entre sondeos) guarda lo ya parseado por (mtime, tamaño):
    en reposo cada sondeo es un listado del directorio, sin leer archivos."""
    mdir = os.path.join(brain, MSGS_DIR)
    out = []
    try:
        entradas = list(os.scandir(mdir))
    except OSError:
        return out
    for e in entradas:
        f = e.name
        if (not f.endswith(".md") or f.startswith(("_", "."))
                or f.lower() == "readme.md"):
            continue
        try:
            st = e.stat()
        except OSError:
            continue
        clave = (st.st_mtime_ns, st.st_size)
        hit = cache.get(f)
        if hit is None or hit[0] != clave:
            m = _parse(e.path, brain) if (e.is_file() and _inside(mdir, e.path)) else None
            cache[f] = hit = (clave, m)
        m = hit[1]
        if m and m["to"] == agente and m["status"] == "pending":
            out.append(m)
    return out


def _cerrar_mios(hid, agente, brain, alias, sesion):
    """Marca `done` lo que queda abierto (pending/claimed) del hilo `hid` para
    `agente` en esta máquina y esta pestaña. Devuelve cuántos."""
    n = 0
    for m in _scan(brain):
        if (m.get("hilo") == hid or m["id"] == hid) and m["to"] == agente \
                and m["status"] in ("pending", "claimed") \
                and _me_toca(m, agente, alias, sesion):
            n += bool(set_status(m["id"], "done", [brain]))
    return n


def esperar(agent, hilo="", proyecto="", timeout=ESPERAR_TIMEOUT,
            intervalo=ESPERAR_INTERVALO, brains=None, sesion=None, asiento=None,
            cerrado_min=OTRO_LADO_MIN, latido=LATIDO_S,
            _reloj=time.monotonic, _dormir=time.sleep):
    """Bloquea hasta que haya en el buzón de `agent` mensajes PENDIENTES de un
    hilo (o del hilo de `hilo`, o de los hilos de `proyecto`) que le toquen a
    esta máquina y a esta pestaña (`sesion`; None = la del entorno). Los
    reclama con compare-and-set (pending → claimed bajo el candado: de dos
    pestañas que esperan, una sola lo recibe; la otra lo ignora) y los
    devuelve en orden, con el status nuevo. Un mensaje sin destino (el primero
    de un hilo) en un cerebro que está también en otra máquina pasa además por
    el desempate entre máquinas (_desempate: hasta `asiento` s más, default
    ASIENTO_S); si lo gana otra, no se entrega. Un `cierre` recibido marca
    `done` lo del hilo. [] si vence `timeout` (0 = mira una vez y vuelve);
    None si el agente no tiene cerebro aquí. Sondeo de archivos con stdlib:
    sin daemon, sin señales.

    Presencia: mientras espera, late cada `latido` s (latir) y, con `hilo`,
    revisa el otro lado: si lleva `cerrado_min` minutos cerrado (o nunca se le
    vio), devuelve SinOtroLado (vacío, con `lado`) en vez de esperar de más."""
    try:
        a = _safe_name(agent)
        bm = brains if isinstance(brains, dict) else registered_brains()
        brain = bm.get(a) if a else ""
        if not brain or not os.path.isdir(brain):
            return None
        hid = _id_de_hilo(hilo, bm) if hilo else ""       # cualquier id del hilo sirve
        proy = _proyecto(proyecto)
        ses = mi_sesion() if sesion is None else _safe_sesion(sesion)
        yo = mi_maquina()
        alias = yo["alias"]
        espera_asiento = ASIENTO_S if asiento is None else max(0.0, float(asiento))
        fin = _reloj() + max(0.0, float(timeout or 0))
        paso = max(0.05, float(intervalo or ESPERAR_INTERVALO))
        cache = {}
        desde = _ahora_epoch()
        hilos = [hid] if hid else []
        latir(brain, a, True, hilos, proy, desde, ses)
        ult_latido, ult_revision = _reloj(), None
        while True:
            nuevos = [m for m in _pendientes(brain, a, cache)
                      if m.get("hilo") and (not hid or m["hilo"] == hid)
                      and (not proy or m.get("proyecto") == proy)
                      and _me_toca(m, a, alias, ses)]
            nuevos.sort(key=lambda m: (m.get("ts") or "", m["id"]))
            ganados, disputados = [], []
            for m in nuevos:
                if set_status(m["id"], "claimed", [brain], solo_si=("pending",)):
                    m["status"] = "claimed"
                    (disputados if _disputable(m) else ganados).append(m)
            if disputados:
                otras = _otras_maquinas(brain, alias)
                # rival = otra máquina que también podría reclamarlo; quien lo
                # mandó a sí mismo desde otra máquina no compite (no se contesta)
                con_rival = [m for m in disputados if otras - (
                    {_etiqueta(m.get("de_maquina"))} if m["from"] == m["to"] else set())]
                ganados += [m for m in disputados if m not in con_rival]
                if con_rival:
                    ganados += _desempate(brain, con_rival, yo, ses, espera_asiento,
                                          paso, _reloj, _dormir)
            ganados.sort(key=lambda m: (m.get("ts") or "", m["id"]))
            for m in ganados:
                if m.get("type") == "cierre":
                    _cerrar_mios(m["hilo"], a, brain, alias, ses)
                    m["status"] = "done"
            if ganados:
                latir(brain, a, False, hilos, proy, desde, ses)   # ahora trabaja
                return ganados
            if hid and cerrado_min and (ult_revision is None
                                        or _reloj() - ult_revision >= latido):
                ult_revision = _reloj()
                ausente = _otro_lado_ausente(hid, a, bm, cerrado_min)
                if ausente:
                    latir(brain, a, False, hilos, proy, desde, ses)
                    return SinOtroLado(ausente, cerrado_min)
            resta = fin - _reloj()
            if resta <= 0:
                return []
            if _reloj() - ult_latido >= latido:
                latir(brain, a, True, hilos, proy, desde, ses)
                ult_latido = _reloj()
            _dormir(min(paso, resta))
    except Exception:
        return []


def _disputable(m):
    """Sin máquina ni pestaña de destino (el primer mensaje de un hilo): lo
    puede reclamar cualquier máquina donde el agente esté esperando."""
    return not m.get("para_maquina") and not m.get("para_sesion")


def _clave_maquina(yo):
    return _safe_sesion(yo.get("id") or yo.get("etiqueta")) or "maquina"


def _reclamos(brain, mid):
    """[(hora, clave_de_máquina, etiqueta)] de los reclamos de `mid` que hay en
    el cerebro (los de las otras máquinas, cuando el sync los trae), en orden."""
    d = os.path.join(brain, MSGS_DIR, RECLAMOS_DIR)
    pref = mid + "--"
    out = []
    try:
        nombres = os.listdir(d)
    except OSError:
        return out
    for n in nombres:
        if not (n.startswith(pref) and n.endswith(".md")):
            continue
        fm = _read_frontmatter(_read_file(os.path.join(d, n), 4000))
        try:
            hora = float(fm.get("ts") or "")
        except ValueError:
            continue
        out.append((hora, n[len(pref):-3], fm.get("maquina", "")))
    return sorted(out)


def _reclamar(brain, mid, yo, ses):
    """Deja el reclamo de ESTA máquina sobre `mid` (uno por máquina: si ya
    está, se conserva el primero)."""
    d = os.path.join(brain, MSGS_DIR, RECLAMOS_DIR)
    p = os.path.join(d, "%s--%s.md" % (mid, _clave_maquina(yo)))
    if os.path.exists(p) or not _inside(os.path.join(brain, MSGS_DIR), p):
        return
    os.makedirs(d, exist_ok=True)
    _atomic_write(p, "---\nts: %.6f\nmaquina: %s\nsesion: %s\n---\n"
                  % (time.time(), _etiqueta(yo.get("etiqueta")), ses))


def _gana_otra(brain, mid, yo):
    """Etiqueta de la máquina que ganó el reclamo de `mid` si NO es esta; ''
    si gané yo o nadie lo reclamó."""
    rs = _reclamos(brain, mid)
    if not rs or rs[0][1] == _clave_maquina(yo):
        return ""
    return rs[0][2] or rs[0][1]


def _otras_maquinas(brain, alias=()):
    """Etiquetas de las OTRAS máquinas (no retiradas) en las que está este
    cerebro, según sus constancias. Vacío = no hay con quién disputar."""
    try:
        import maquinas
        return {_etiqueta(e.get("etiqueta")) or str(e.get("id") or "?")
                for e in maquinas.estado(brain, sondear=False)
                if not e.get("yo") and not e.get("retirada") and not e.get("anterior")
                and _etiqueta(e.get("etiqueta")) not in alias}
    except Exception:
        return set()


def _desempate(brain, disputados, yo, ses, asiento, paso, _reloj, _dormir):
    """Los `disputados` (ya claimed aquí) que esta máquina gana: deja su
    reclamo y espera hasta `asiento` s a que lleguen los de las demás; en
    cuanto otra gana uno, ese se suelta (lo atiende la otra)."""
    for m in disputados:
        _reclamar(brain, m["id"], yo, ses)
    vivos = list(disputados)
    fin = _reloj() + asiento
    while vivos:
        vivos = [m for m in vivos if not _gana_otra(brain, m["id"], yo)]
        resta = fin - _reloj()
        if not vivos or resta <= 0:
            break
        _dormir(min(paso, resta))
    return vivos


def hilo_de_otra_maquina(msg_id, agente, brains=None):
    """Si el hilo de `msg_id` lo ganó OTRA máquina de `agente` en el desempate,
    su etiqueta ('' si no): entonces esta no habla en él. Quien abrió el hilo
    nunca compite."""
    try:
        hid = _id_de_hilo(msg_id, brains)
        raiz = find(hid, brains) if hid else None
        a = _safe_name(agente)
        if not raiz or raiz.get("to") != a or not _disputable(raiz):
            return ""
        yo = mi_maquina()
        if raiz.get("from") == a and _etiqueta(raiz.get("de_maquina")) in yo["alias"]:
            return ""
        return _gana_otra(raiz["brain"], hid, yo)
    except Exception:
        return ""


def resolver_pestana(brain, agente, nombre):
    """`--pestana "<nombre visible>"` → (id estable, nombre, aviso). Busca el
    nombre en las presencias del agente (sirven entre máquinas) y en el
    registro de pestañas de Workspace (sessions_registry.tabs: su id es el
    WORKSPACE_WID con que se abre). Si no existe o hay más de una con ese
    nombre, ('', '', aviso)."""
    sl = _slug_pestana(nombre)
    if not sl or not brain:
        return "", "", "falta el nombre de la pestaña"
    cand, todas = {}, set()
    for r in presencias(brain, agente):
        if r.get("pestana"):
            todas.add(r["pestana"])
        if r.get("sesion") and _slug_pestana(r.get("pestana")) == sl:
            cand[_safe_sesion(r["sesion"])] = r["pestana"]
    try:
        import sessions_registry as SR
        for t in SR.tabs(brain, agente):
            todas.add(t.get("name") or "")
            wid = _safe_sesion((t.get("resume") or {}).get("claude-code"))
            if wid and t.get("slug") == sl:
                cand[wid] = t.get("name") or nombre
    except Exception:
        pass
    if len(cand) == 1:
        sid, nom = next(iter(cand.items()))
        return sid, nom, ""
    if cand:
        return "", "", ("hay %d pestañas «%s» de %s con distinto id: di la máquina con "
                        "--maquina o renombra una" % (len(cand), nombre, agente))
    conocidas = ", ".join(sorted(x for x in todas if x)[:8]) or "ninguna"
    return "", "", "%s no tiene ninguna pestaña «%s» (conocidas: %s)" % (agente, nombre,
                                                                        conocidas)


def iniciar(from_agent, con, tarea, proyecto, resumen, maquina="", objetivo="",
            hecho_cuando="", max_turnos=MAX_TURNOS, brains=None, pestana=""):
    """Abre un hilo: un `encargo` de `from_agent` a `con` dentro de `proyecto`,
    cuyo hilo es su propio id, con su resumen y el contrato (objetivo, cuándo
    está hecho, tope de turnos). Sin `maquina`, sin destino: lo toma la
    primera pestaña del otro que lo reclame (desempate entre máquinas en
    esperar). Con `pestana` (nombre visible), va solo a esa pestaña del otro
    (resolver_pestana; si no existe o es ambigua, no se manda). Devuelve
    (ids, aviso): `aviso` no vacío si la máquina o la pestaña no casan, o si
    hablo con otra pestaña mía sin que Workspace haya abierto esta (sin
    WORKSPACE_WID, la otra pestaña de esta máquina no lo recibiría)."""
    try:
        texto = str(tarea or "").strip()
        dest = _safe_name(con)
        proy = _proyecto(proyecto)
        if (not texto or not dest or not proy or not _corto(resumen)
                or str(con).strip().lower() in ("all", "*", "todos")):
            return [], ""
        bm = brains if isinstance(brains, dict) else registered_brains()
        para, aviso = resolver_maquina(maquina, bm.get(dest, "")) if maquina else ("", "")
        psn = ""
        if pestana:
            psn, _nom, av = resolver_pestana(bm.get(dest, ""), dest, pestana)
            if not psn:
                return [], av
        yo = mi_maquina()
        if (_safe_name(from_agent) == dest and not mi_sesion()
                and (not para or para in yo["alias"])):
            aviso = ("esta pestaña no la abrió Workspace (sin WORKSPACE_WID): otra pestaña tuya "
                     "en esta máquina no va a recibir el hilo; ábrelas desde Workspace")
        primera = next((ln.strip() for ln in texto.splitlines() if ln.strip()), texto)
        ids = send(from_agent, dest, "encargo", "Colaboración: " + primera, texto,
                   brains=bm, proyecto=proy, para_maquina=para, para_sesion=psn,
                   resumen=resumen, contrato={"objetivo": objetivo, "hecho_cuando": hecho_cuando,
                             "max_turnos": max_turnos or MAX_TURNOS},
                   nuevo_hilo=True)
        return ids, aviso
    except Exception:
        return [], ""


def cerrar(msg_id, resultado, resumen, from_agent=None, brains=None):
    """Cierra el hilo de `msg_id` con un mensaje `type: cierre` que trae el
    resultado, para el otro lado: contesta al último mensaje que recibí en el
    hilo (o, si no recibí ninguno, va a quien le escribí), a su máquina y su
    pestaña. Marca `done` lo que me quedaba abierto del hilo. Devuelve los ids
    escritos ([] si nada)."""
    try:
        bm = brains if isinstance(brains, dict) else registered_brains()
        hilo = mensajes_hilo(msg_id, bm)
        if not hilo or not str(resultado or "").strip() or not _corto(resumen):
            return []
        hid = _safe_id(hilo[0].get("hilo")) or hilo[0]["id"]
        m0 = find(msg_id, bm) or hilo[-1]
        yo = _safe_name(from_agent) or m0.get("to", "")
        if hilo_de_otra_maquina(hid, yo, bm):
            return []
        alias = mi_maquina()["alias"]
        ses = mi_sesion()
        recibidos = [m for m in hilo if m["to"] == yo and _me_toca(m, yo, alias, ses)]
        if recibidos:
            ult = recibidos[-1]
            dest, para, psn = ult["from"], ult.get("de_maquina", ""), ult.get("de_sesion", "")
        else:
            ult = ([m for m in hilo if m["from"] == yo] or hilo)[-1]
            dest, para, psn = ult["to"], ult.get("para_maquina", ""), ult.get("para_sesion", "")
        raiz = re.sub(r"^(re:\s*)+", "", hilo[0].get("subject", ""), flags=re.I)
        ids = send(yo, dest, "cierre", "Cierre: " + raiz, resultado, brains=bm,
                   hilo=hid, en_respuesta_a=ult["id"], proyecto=hilo[0].get("proyecto", ""),
                   para_maquina=para, para_sesion=psn, resumen=resumen)
        if ids and bm.get(yo):
            _cerrar_mios(hid, yo, bm[yo], alias, ses)
        return ids
    except Exception:
        return []


def _fmt(m):
    flag = " [!]" if (m["requires_approval"] and m["status"] == "pending") else ""
    return "%-9s %s -> %s · %s · %s%s   (%s)" % (
        "[" + m["status"] + "]", m["from"] or "?", m["to"] or "?",
        m["type"] or "?", m["subject"][:60], flag, m["id"])


def es_de_quien_abrio(m, raiz):
    """¿`m` lo escribió el lado que abrió el hilo? Un lado es el agente en su
    máquina; si el hilo es del agente consigo mismo (otra pestaña o máquina
    suya), también cuenta la pestaña."""
    mismo = (m["from"] == raiz["from"]
             and _etiqueta(m.get("de_maquina")) == _etiqueta(raiz.get("de_maquina")))
    if mismo and raiz["from"] == raiz["to"]:
        mismo = _safe_sesion(m.get("de_sesion")) == _safe_sesion(raiz.get("de_sesion"))
    return mismo


def lados_hilo(msgs, brains):
    """Los dos lados de un hilo (lista de mensajes en orden), cada uno con lo
    que dice el sobre de su ÚLTIMO mensaje: [quien abrió, el otro]. Un lado es
    (agente, máquina): el mismo agente en dos máquinas son dos lados. El otro
    lado, si todavía no escribió, es a quien se le escribió. Los mensajes del
    socio (no es un agente con cerebro) no son un lado."""
    if not msgs:
        return []
    bm = brains if isinstance(brains, dict) else {}
    hid = _safe_id(msgs[0].get("hilo")) or msgs[0]["id"]
    raiz = next((m for m in msgs if m["id"] == hid), msgs[0])

    def lado(m, de=True):
        p = "de_" if de else "para_"
        return {"agente": m["from"] if de else m["to"],
                "maquina": _etiqueta(m.get(p + "maquina")), "sesion": m.get(p + "sesion", ""),
                "pestana": m.get("de_pestana", "") if de else "",
                "motor": m.get("de_motor", "") if de else "",
                "brain": bm.get(m["from"] if de else m["to"], "")}
    a = b = None
    for m in msgs:
        if bm and m["from"] not in bm:
            continue
        if es_de_quien_abrio(m, raiz):
            a = lado(m)
        else:
            b = lado(m)
    a = a or lado(raiz)
    b = b or lado(raiz, de=False)
    return [a, b]


def cerrar_por_socio(msg_id, socio, motivo="", brains=None):
    """El socio cierra el hilo (desde el hub): un `cierre` a CADA lado, a su
    última máquina y pestaña. Cada agente lo recibe con `esperar` y para. Es
    un mensaje más por la API: nadie edita archivos a mano. Devuelve los ids."""
    try:
        bm = brains if isinstance(brains, dict) else registered_brains()
        msgs = mensajes_hilo(msg_id, bm)
        if not msgs or any(m.get("type") == "cierre" for m in msgs):
            return []
        hid = _safe_id(msgs[0].get("hilo")) or msgs[0]["id"]
        raiz = next((m for m in msgs if m["id"] == hid), msgs[0])
        asunto = re.sub(r"^(re:\s*)+", "", raiz.get("subject", ""), flags=re.I)
        cuerpo = (motivo or "").strip() or "El socio cerró este hilo desde el hub."
        ids = []
        for lado in lados_hilo(msgs, bm):
            if not lado["brain"]:
                continue
            ids += send(socio or "socio", lado["agente"], "cierre", "Cierre: " + asunto, cuerpo,
                        brains=bm, hilo=hid, en_respuesta_a=msgs[-1]["id"],
                        proyecto=raiz.get("proyecto", ""), para_maquina=lado["maquina"],
                        para_sesion=lado["sesion"],
                        resumen="El socio cerró el hilo: dejen de esperarlo.")
        return ids
    except Exception:
        return []


# ═══════════════════════════════════════════════════════════════════════════
# Presencia: el que escucha avisa que sigue ahí (sin daemon)
# ═══════════════════════════════════════════════════════════════════════════
# `esperar` es la prueba de vida: mientras bloquea, cada LATIDO_S deja un
# archivo chico por pestaña en el cerebro de quien escucha. Es .md (Obsidian
# Sync lo lleva sin «otros tipos») en `msgs/_presencia/` (sin punto: las
# carpetas con punto no viajan). En la misma máquina se confirma con el
# proceso; entre máquinas, por la hora del último latido (minutos).

def _ahora_epoch():
    return time.time()


def _clave_presencia(agente, ses, yo):
    return "%s--%s" % (_safe_name(agente) or "agente",
                       _safe_sesion(ses) or "sin-pestana-" + _clave_maquina(yo))


def _dir_presencia(brain):
    return os.path.join(brain, MSGS_DIR, PRESENCIA_DIR)


def _marca_proceso():
    """pid + hora de inicio de ESTE proceso (la huella de sessions_registry:
    un pid reciclado no pasa por vivo)."""
    try:
        import sessions_registry as SR
        return SR._marca_proceso()
    except Exception:
        return {"pid": os.getpid(), "ctime": None, "t0": time.time()}


def _proceso_vivo(marca):
    try:
        import sessions_registry as SR
        return bool(SR._proceso_vivo(marca))
    except Exception:
        return False


def latir(brain, agente, escuchando, hilos=(), proyecto="", desde=None, sesion=None,
          cerrada=False):
    """Escribe la presencia de esta pestaña: quién, dónde, si está dentro de
    `esperar` y cuándo se le vio. `cerrada=True` lo deja al cerrar la
    pestaña (neutral_hooks, session_end): así OTRA máquina sabe que se cerró
    de verdad y no solo que lleva rato sin latir. Falla-suave: False si no se
    pudo."""
    import json
    try:
        yo, ses = mi_maquina(), (mi_sesion() if sesion is None else _safe_sesion(sesion))
        de = sobre()
        d = _dir_presencia(brain)
        os.makedirs(d, exist_ok=True)
        p = os.path.join(d, _clave_presencia(agente, ses, yo) + ".md")
        if not _inside(os.path.join(brain, MSGS_DIR), p):
            return False
        ahora = _ahora_epoch()
        previo = _read_frontmatter(_read_file(p, 4000)) if os.path.exists(p) else {}
        try:
            edad = ahora - float(previo.get("visto") or 0)
        except ValueError:
            edad = ahora
        hs = ", ".join(_safe_id(h) for h in hilos if _safe_id(h))
        if (previo.get("escuchando") == ("true" if escuchando else "false")
                and (previo.get("cerrada") == "true") == bool(cerrada)
                and (previo.get("hilos") or "") == hs and edad < LATIDO_S):
            return True                       # mismo estado y latido reciente: sin ruido
        marca = _marca_proceso()
        campos = (("agente", _safe_name(agente)), ("sesion", ses),
                  ("pestana", de["de_pestana"]), ("motor", de["de_motor"]),
                  ("maquina", _etiqueta(yo.get("etiqueta"))), ("maquina_id", yo.get("id") or ""),
                  ("hilos", hs),
                  ("proyecto", _proyecto(proyecto)),
                  ("escuchando", "true" if escuchando else "false"),
                  ("cerrada", "true" if cerrada else "false"),
                  ("desde", "%.3f" % (desde or ahora)), ("visto", "%.3f" % ahora),
                  ("visto_iso", _dt.datetime.fromtimestamp(ahora).astimezone()
                   .isoformat(timespec="seconds")),
                  ("proc", json.dumps(marca, separators=(",", ":"))))
        _atomic_write(p, "---\n" + "".join("%s: %s\n" % kv for kv in campos) + "---\n")
        return True
    except Exception:
        return False


def presencias(brain, agente=None):
    """Las presencias que hay en el cerebro (de `agente`, o de todos), como
    dicts con `visto`/`desde` en epoch y `escuchando` booleano."""
    out = []
    d = _dir_presencia(brain or "")
    try:
        nombres = sorted(os.listdir(d))
    except OSError:
        return out
    a = _safe_name(agente) if agente else ""
    for n in nombres:
        if not n.endswith(".md") or (a and not n.startswith(a + "--")):
            continue
        fm = _read_frontmatter(_read_file(os.path.join(d, n), 4000))
        if not fm.get("agente"):
            continue
        try:
            fm["visto"] = float(fm.get("visto") or 0)
            fm["desde"] = float(fm.get("desde") or 0)
        except ValueError:
            continue
        fm["escuchando"] = fm.get("escuchando") == "true"
        fm["cerrada"] = fm.get("cerrada") == "true"
        fm["hilos"] = [h.strip() for h in (fm.get("hilos") or "").split(",") if h.strip()]
        out.append(fm)
    return out


_ORDEN_ESTADO = {"escuchando": 3, "trabajando": 2, "cerrada": 1, "desconocido": 0}


def _es_local(rec, alias):
    return _etiqueta(rec.get("maquina")) in alias or (rec.get("maquina_id") or "-") in alias


def _estado_de(rec, alias, abiertas, ahora):
    """escuchando / trabajando / cerrada de UNA presencia. Una presencia que
    se marcó al cerrar la pestaña (`cerrada`) está cerrada en cualquier
    máquina: no hay que adivinar por la hora del último latido."""
    import json
    local = _es_local(rec, alias)
    edad = ahora - float(rec.get("visto") or 0)
    if rec.get("cerrada") is True and not (local and _slug_pestana(rec.get("pestana")) in abiertas):
        return "cerrada"
    if local:
        try:
            marca = json.loads(rec.get("proc") or "{}")
        except ValueError:
            marca = {}
        if rec.get("escuchando") and edad <= FRESCA_S and _proceso_vivo(marca):
            return "escuchando"
        if _slug_pestana(rec.get("pestana")) in abiertas:
            return "trabajando"
        return "cerrada"
    if rec.get("escuchando") and edad <= FRESCA_S:
        return "escuchando"
    return "trabajando" if edad <= VIVA_S else "cerrada"


def _slug_pestana(nombre):
    try:
        import sessions_registry as SR
        return SR._slug(nombre or "") if nombre else ""
    except Exception:
        return _slug(nombre or "", 60) if nombre else ""


def _abiertas(brain):
    """Pestañas de `brain` abiertas en una ventana viva de ESTA máquina (el
    registro que el lanzador ya lleva)."""
    try:
        import sessions_registry as SR
        return SR.abiertas_en_ventanas(brain)
    except Exception:
        return set()


def estado_lado(brain, agente, sesion="", maquina="", pestana="", ahora=None, excluir=""):
    """¿Cómo está un lado del hilo? {"estado": escuchando | trabajando |
    cerrada | desconocido, "visto": epoch o None, "pestana", "maquina",
    "de_verdad"}. Con `sesion`, esa pestaña; sin ella, la mejor de las del
    agente (un hilo nuevo lo toma cualquiera). En esta máquina manda el
    proceso (y el registro de pestañas abiertas); en otra, la hora del último
    latido. `de_verdad` = la cerrada se SABE (esta máquina, o la pestaña lo
    dejó dicho al cerrarse); una de otra máquina que solo lleva rato sin latir
    es una suposición (False). `excluir` = una pestaña (id) que no cuenta (la
    de quien pregunta, cuando busca OTRA pestaña de su mismo agente)."""
    try:
        ahora = _ahora_epoch() if ahora is None else ahora
        alias = mi_maquina()["alias"]
        abiertas = _abiertas(brain) if brain else set()
        ses = _safe_sesion(sesion)
        fuera = _safe_sesion(excluir) if excluir else ""
        recs = [r for r in presencias(brain, agente)
                if (not ses or _safe_sesion(r.get("sesion")) == ses)
                and not (fuera and _safe_sesion(r.get("sesion")) == fuera)]
        mejor = {"estado": "desconocido", "visto": None, "pestana": pestana or "",
                 "maquina": _etiqueta(maquina), "de_verdad": False}
        for r in recs:
            e = _estado_de(r, alias, abiertas, ahora)
            if (_ORDEN_ESTADO[e], r["visto"]) > (_ORDEN_ESTADO[mejor["estado"]],
                                                 mejor["visto"] or 0):
                mejor = {"estado": e, "visto": r["visto"], "pestana": r.get("pestana") or "",
                         "maquina": _etiqueta(r.get("maquina")),
                         "de_verdad": e == "cerrada" and (_es_local(r, alias)
                                                          or r.get("cerrada") is True)}
        if mejor["estado"] in ("desconocido", "cerrada"):
            local = not maquina or _etiqueta(maquina) in alias
            sl = _slug_pestana(pestana)
            if local and sl and sl in abiertas:
                mejor["estado"] = "trabajando"          # abierta, aún sin `esperar`
                mejor["de_verdad"] = False
            elif local and pestana and mejor["estado"] == "desconocido":
                mejor["estado"] = "cerrada"             # aquí se sabe: no está abierta
                mejor["de_verdad"] = True
        return mejor
    except Exception:
        return {"estado": "desconocido", "visto": None, "pestana": pestana or "",
                "maquina": _etiqueta(maquina), "de_verdad": False}


def _ts_epoch(ts):
    try:
        return _dt.datetime.fromisoformat(str(ts)).timestamp()
    except Exception:
        return None


def otro_lado(msg_id, agente, brains=None):
    """El OTRO lado del hilo visto desde `agente` en esta máquina y pestaña:
    su último mensaje dice quién, en qué pestaña y máquina. Si todavía no
    habló, a quién le escribí. None si no se sabe."""
    try:
        bm = brains if isinstance(brains, dict) else registered_brains()
        msgs = mensajes_hilo(msg_id, bm)
        if not msgs:
            return None
        a, alias, ses = _safe_name(agente), mi_maquina()["alias"], mi_sesion()

        def mio(m):
            return (m["from"] == a and _etiqueta(m.get("de_maquina")) in alias
                    and _safe_sesion(m.get("de_sesion")) in ("", ses))
        suyos = [m for m in msgs if not mio(m) and m["from"] in bm]
        if suyos:
            m = suyos[-1]
            return {"agente": m["from"], "sesion": m.get("de_sesion", ""),
                    "maquina": m.get("de_maquina", ""), "pestana": m.get("de_pestana", ""),
                    "motor": m.get("de_motor", ""), "brain": bm.get(m["from"], ""),
                    "ts": _ts_epoch(m.get("ts"))}
        raiz = msgs[0]
        if mio(raiz) and raiz["to"] in bm:
            return {"agente": raiz["to"], "sesion": raiz.get("para_sesion", ""),
                    "maquina": raiz.get("para_maquina", ""), "pestana": "", "motor": "",
                    "brain": bm.get(raiz["to"], ""), "ts": _ts_epoch(raiz.get("ts"))}
        return None
    except Exception:
        return None


class SinOtroLado(list):
    """Resultado de `esperar` cuando el otro lado lleva rato cerrado: vacío
    (como un timeout, para quien no lo distinga) y con `lado` adentro."""

    def __init__(self, lado, minutos):
        super().__init__()
        self.lado, self.minutos = lado, minutos


def _otro_lado_ausente(hid, agente, bm, minutos, ahora=None):
    """El lado ausente si el otro lado del hilo está cerrado (o nunca se le
    vio) desde hace `minutos` o más; None si no."""
    lado = otro_lado(hid, agente, bm)
    if not lado or not lado.get("brain"):
        return None
    ahora = _ahora_epoch() if ahora is None else ahora
    est = estado_lado(lado["brain"], lado["agente"], lado.get("sesion"), lado.get("maquina"),
                      lado.get("pestana"), ahora=ahora)
    if est["estado"] in ("escuchando", "trabajando"):
        return None
    ref = max([x for x in (est.get("visto"), lado.get("ts")) if x] or [ahora])
    return dict(lado, estado=est["estado"]) if ahora - ref >= minutos * 60 else None


#: Nombre para mostrar por tipo de máquina (el `so` de su constancia).
_TIPO_MAQUINA = {"mac": "Mac", "windows": "PC", "linux": "Linux"}


def maquinas_conocidas(brains=None):
    """{etiqueta: so} de las máquinas que conocen estos cerebros (sus
    constancias STATE/maquinas/) más ESTA máquina. Para mostrar, no para
    enrutar. Falla-suave: {}."""
    out = {}
    try:
        import maquinas
        for b in _brain_paths(brains):
            for c in maquinas.constancias(b):
                eti, so = _etiqueta(c.get("etiqueta")), str(c.get("so") or "")
                if eti and so:
                    out[eti] = so
        eti = _etiqueta(mi_maquina().get("etiqueta"))
        if eti:
            out[eti] = maquinas.so()
    except Exception:
        pass
    return out


def nombre_maquina(etiqueta, conocidas=None):
    """La etiqueta corta para mostrar: «Mac», «PC», «Linux»; con el hostname
    entre paréntesis solo si hay dos máquinas conocidas del mismo tipo. Si no
    se sabe el tipo, la etiqueta tal cual."""
    eti = _etiqueta(etiqueta)
    if not eti:
        return ""
    conocidas = maquinas_conocidas() if conocidas is None else conocidas
    so = conocidas.get(eti)
    tipo = _TIPO_MAQUINA.get(so or "")
    if not tipo:
        return eti
    mismas = sum(1 for v in conocidas.values() if v == so)
    return tipo if mismas <= 1 else "%s (%s)" % (tipo, eti)


def etiqueta_lado(lado, lados, conocidas=None):
    """Cómo se nombra un lado del hilo: el agente; si los dos lados son el
    mismo agente, «agente · <pestaña>» (o la máquina, si no hay pestaña o es
    la misma)."""
    otros = [x for x in lados if x is not lado]
    if not otros or otros[0]["agente"] != lado["agente"]:
        return lado["agente"] or "?"
    o = otros[0]
    if lado.get("pestana") and lado.get("pestana") != o.get("pestana"):
        return "%s · %s" % (lado["agente"], lado["pestana"])
    m = nombre_maquina(lado.get("maquina"), conocidas) if lado.get("maquina") else ""
    return "%s · %s" % (lado["agente"], m) if m else lado["agente"] or "?"


def _quien(agente, maquina="", motor="", pestana="", conocidas=None):
    """«agente-a» con lo que se sepa de su lado: «agente-a (Mac · claude-code ·
    «Diseño»)». La máquina va corta (nombre_maquina)."""
    extra = [x for x in (nombre_maquina(maquina, conocidas) if maquina else "", motor,
                         "«%s»" % pestana if pestana else "") if x]
    return (agente or "?") + (" (%s)" % " · ".join(extra) if extra else "")


def _resumen_de(m):
    """El `resumen` del mensaje o, si no trae (mensajes de antes), sus primeras
    líneas del cuerpo en corto."""
    return m.get("resumen") or _corto(m.get("body"), 200, 2) or m.get("subject", "")


def _ver_hilo(msgs, completo=False, brains=None):
    """La conversación para leer en la terminal: cabecera con el contrato y,
    por mensaje, quién → a quién, tipo y status; luego su resumen (o, con
    `completo`, el asunto y el cuerpo)."""
    hid = _safe_id(msgs[0].get("hilo")) or msgs[0]["id"]
    raiz = next((m for m in msgs if m["id"] == hid), msgs[0])
    n, tope = _tope_turnos(msgs)
    gente = sorted({x for m in msgs for x in (m["from"], m["to"]) if x})
    conocidas = maquinas_conocidas()
    lados = lados_hilo(msgs, brains if isinstance(brains, dict) else registered_brains())
    if len(lados) == 2 and lados[0]["agente"] == lados[1]["agente"]:
        gente = [etiqueta_lado(ld, lados, conocidas) for ld in lados]
    cerrado = any(m.get("type") == "cierre" for m in msgs)
    out = ["hilo %s · %s · %d mensajes (tope %d)%s%s" % (
        hid, " ↔ ".join(gente) or "?", n, tope,
        " · proyecto " + raiz["proyecto"] if raiz.get("proyecto") else "",
        " · CERRADO" if cerrado else "")]
    for campo, etiqueta in (("objetivo", "objetivo"), ("hecho_cuando", "hecho cuando")):
        if raiz.get(campo):
            out.append("  %s: %s" % (etiqueta, raiz[campo]))
    for i, m in enumerate(msgs, 1):
        out.append("")
        out.append("── %d · %s · %s → %s · %s · %s   (%s)" % (
            i, m.get("ts") or "?",
            _quien(m["from"], m.get("de_maquina"), m.get("de_motor"), m.get("de_pestana"),
                   conocidas),
            _quien(m["to"], m.get("para_maquina"), conocidas=conocidas),
            m.get("type") or "?", m.get("status") or "?", m["id"]))
        if completo:
            out.append("   " + (m.get("subject") or ""))
            if m.get("resumen"):
                out.append("   resumen: " + m["resumen"])
            out.append("")
            out.extend("   " + ln if ln else "" for ln in (m.get("body") or "").splitlines())
        else:
            out.append("   " + _resumen_de(m))
    if n > tope:
        out += ["", _aviso_tope(msgs)]
    return "\n".join(out)


def _remitente(valor):
    """(agente, error) en los comandos del modo colaboración: manda el agente
    de esta sesión (WORKSPACE_AGENT_NAME, lo exporta el lanzador); un --from
    distinto sería un sobre escrito por el modelo y se rechaza. Fuera de una
    sesión de Workspace vale --from."""
    env = _safe_name(os.environ.get("WORKSPACE_AGENT_NAME", ""))
    dado = _safe_name(valor)
    if env and dado and dado != env:
        return "", ("--from %s no es el agente de esta sesión (%s): el remitente "
                    "lo pone Workspace" % (dado, env))
    return env or dado, ""


def _avisar_si_no_escucha(agente, sesion="", maquina="", pestana=""):
    """Una línea (stderr) si quien recibe no está escuchando: el mensaje queda
    en su buzón y el agente se lo dice al socio."""
    try:
        brain = registered_brains().get(_safe_name(agente), "")
        if not brain:
            return
        est = estado_lado(brain, agente, sesion, maquina, pestana)
        if est["estado"] != "escuchando":
            print("aviso: %s no está escuchando (%s); el mensaje queda en su buzón"
                  % (agente, est["estado"]), file=sys.stderr)
    except Exception:
        pass


def _me_retiro(otra):
    return ("este hilo lo tomó otra máquina (%s) — me retiro; díselo al socio" % otra)


def _bus_cmd():
    """El comando del bus como lo imprimen los help: (salas._bus): con la ruta
    RESUELTA y la forma de la plataforma — en Windows `python "C:\\…\\messages.py"`
    (`python3` puede abrir la Microsoft Store y una ruta relativa solo sirve
    desde la carpeta de Workspace); en Mac/Linux `python3 "/…/messages.py"`."""
    try:
        import salas
        return salas._bus()
    except Exception:
        return "python3 messages.py"


def main(argv=None):
    import argparse
    try:
        import _utf8                      # Windows: stdout cp1252 revienta con «→»/acentos
        _utf8.harden()
    except Exception:
        pass
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["conversar"]:         # las salas de varios agentes viven en salas.py
        import salas
        return salas.main(argv[1:])
    ap = argparse.ArgumentParser(prog="messages.py",
                                 description="Bus de mensajes inter-agente de WORKSPACE (msgs/*.md)")
    sub = ap.add_subparsers(dest="cmd")
    s = sub.add_parser("send", help="enviar un mensaje")
    s.add_argument("--from", dest="from_agent", required=True)
    s.add_argument("--to", dest="to_agent", required=True, help="agente o 'all'")
    s.add_argument("--type", default="encargo", choices=TYPES)
    s.add_argument("--subject", required=True)
    s.add_argument("--body", default="")
    s.add_argument("--approval", action="store_true",
                   help="requiere aprobación humana (un socio la da desde el menú)")
    s.add_argument("--resumen", default="", help="1-3 líneas (≤%d)" % _CLIP_RESUMEN)
    i = sub.add_parser("inbox", help="pendientes de un agente")
    i.add_argument("agent")
    ls = sub.add_parser("list", help="todos los mensajes")
    ls.add_argument("--status", default="", help="filtrar por status")
    st = sub.add_parser("status", help="cambiar el status de un mensaje")
    st.add_argument("msg_id")
    st.add_argument("new_status", choices=STATUSES)
    rp = sub.add_parser("reply", help="responder a un mensaje (from/to se infieren)")
    rp.add_argument("msg_id")
    rp.add_argument("body")
    rp.add_argument("--from", dest="from_agent", default=None)
    rp.add_argument("--resumen", default="",
                    help="1-3 líneas; obligatorio si el mensaje es de un hilo")
    es = sub.add_parser("esperar", help="esperar mensajes de hilos (long-poll)")
    es.add_argument("agent")
    es.add_argument("--hilo", default="", help="solo ese hilo (cualquier id del hilo)")
    es.add_argument("--proyecto", default="", help="solo los hilos de ese proyecto")
    es.add_argument("--timeout", type=float, default=ESPERAR_TIMEOUT,
                    help="segundos (default %d; 0 = mirar una vez)" % ESPERAR_TIMEOUT)
    es.add_argument("--intervalo", type=float, default=ESPERAR_INTERVALO,
                    help=argparse.SUPPRESS)
    hl = sub.add_parser("hilo", help="la conversación de un hilo, en orden")
    hl.add_argument("msg_id")
    hl.add_argument("--completo", action="store_true", help="con el cuerpo de cada mensaje")
    co = sub.add_parser("colaborar", help="abrir o cerrar un hilo de colaboración")
    cos = co.add_subparsers(dest="accion")
    ci = cos.add_parser("iniciar", help="abrir un hilo con otro agente")
    ci.add_argument("--con", required=True, help="el otro agente")
    ci.add_argument("--proyecto", required=True, help="slug del proyecto")
    ci.add_argument("--tarea", required=True, help="qué hay que sacar (el cuerpo)")
    ci.add_argument("--resumen", required=True, help="1-3 líneas (≤%d)" % _CLIP_RESUMEN)
    ci.add_argument("--maquina", default="", help="etiqueta, id o tipo (mac/pc/linux)")
    ci.add_argument("--pestana", default="", help="nombre visible de una pestaña del otro")
    ci.add_argument("--objetivo", default="")
    ci.add_argument("--hecho-cuando", dest="hecho_cuando", default="")
    ci.add_argument("--max-turnos", dest="max_turnos", type=int, default=MAX_TURNOS)
    ci.add_argument("--from", dest="from_agent", default=None)
    cc = cos.add_parser("cerrar", help="cerrar un hilo con el resultado")
    cc.add_argument("msg_id")
    cc.add_argument("--resultado", required=True)
    cc.add_argument("--resumen", required=True, help="1-3 líneas (≤%d)" % _CLIP_RESUMEN)
    cc.add_argument("--from", dest="from_agent", default=None)
    sub.add_parser("conversar", help="salas de varios agentes: abrir, publicar, esperar, ver… "
                                     "(messages.py conversar -h)")
    a = ap.parse_args(argv)

    if a.cmd == "send":
        ids = send(a.from_agent, a.to_agent, a.type, a.subject, a.body, a.approval,
                   resumen=a.resumen)
        for mid in ids:
            print(mid)
        return 0 if ids else 1
    if a.cmd == "inbox":
        # AXI: cabecera con agregados + estado vacío explícito + next-steps.
        # UN solo _scan (vía inbox statuses=None); pendientes se filtran en RAM.
        agent = _safe_name(a.agent) or a.agent
        brain = registered_brains().get(_safe_name(a.agent), "")
        todos = inbox(brain, a.agent, statuses=None)     # T real: pending+claimed+done+rejected
        msgs = [m for m in todos if m["status"] == "pending"]
        if msgs:
            print("inbox: %d pendientes para %s (de %d totales)"
                  % (len(msgs), agent, len(todos)))
            for m in msgs:
                print(_fmt(m))
            print("help: %s status <id> done   (o: claimed / rejected)" % _bus_cmd(),
                  file=sys.stderr)
            print("help: %s reply <id> \"<texto>\"   (from/to se infieren)" % _bus_cmd(),
                  file=sys.stderr)
        else:
            print("inbox: 0 mensajes pendientes para %s" % agent)
            print("help: %s list   (todos los mensajes del bus)" % _bus_cmd(),
                  file=sys.stderr)
            print("help: %s send --from %s --to <agente> "
                  "--type encargo --subject \"...\" --body \"...\"" % (_bus_cmd(), agent),
                  file=sys.stderr)
        return 0
    if a.cmd == "list":
        for m in all_messages(statuses=(a.status,) if a.status else None):
            print(_fmt(m))
        return 0
    if a.cmd == "status":
        ok = set_status(a.msg_id, a.new_status)
        print("ok" if ok else "no se pudo (¿id correcto? ¿cerebro resuelto?)")
        return 0 if ok else 1
    if a.cmd == "reply":
        orig = find(a.msg_id)
        frm = a.from_agent
        if orig and orig.get("hilo"):
            if not _corto(a.resumen):
                print("no se pudo responder: el mensaje es de un hilo, falta --resumen \"…\" "
                      "(1-3 líneas)")
                return 1
            frm, err = _remitente(a.from_agent)
            if err:
                print("no se pudo responder: " + err)
                return 1
            otra = hilo_de_otra_maquina(orig["id"], frm or orig.get("to", ""))
            if otra:
                print("no se pudo responder: " + _me_retiro(otra))
                return 1
        ids = reply(a.msg_id, a.body, frm or None, resumen=a.resumen)
        for mid in ids:
            print(mid)
        if not ids:
            print("no se pudo responder (¿id correcto? ¿cerebro resuelto?)")
        elif orig and orig.get("hilo"):
            aviso = aviso_turnos(ids[0])
            if aviso:
                print(aviso, file=sys.stderr)
            _avisar_si_no_escucha(orig["from"], orig.get("de_sesion"),
                                  orig.get("de_maquina"), orig.get("de_pestana"))
        return 0 if ids else 1
    if a.cmd == "esperar":
        agente = _safe_name(a.agent) or a.agent
        try:
            msgs = esperar(a.agent, hilo=a.hilo, proyecto=a.proyecto,
                           timeout=a.timeout, intervalo=a.intervalo)
        except KeyboardInterrupt:
            return 130
        if msgs is None:
            print("esperar: %s no tiene cerebro en esta máquina" % agente)
            return 1
        if isinstance(msgs, SinOtroLado):
            lado = msgs.lado
            print("esperar: %s no está (%s hace %d min o más); para y díselo al socio: "
                  "puede abrirlo desde el hub › Conversaciones"
                  % (_quien(lado.get("agente"), lado.get("maquina"), lado.get("motor"),
                            lado.get("pestana")), lado.get("estado") or "cerrada", msgs.minutos))
            return SALIDA_OTRO_LADO
        donde = ((" · hilo " + a.hilo) if a.hilo else "") + \
                ((" · proyecto " + a.proyecto) if a.proyecto else "")
        if not msgs:
            print("esperar: nada nuevo para %s en %g s%s" % (agente, a.timeout, donde))
            print("help: vuelve a esperar; si ya pasó tu tope de espera, para y díselo "
                  "al socio (¿está abierto el otro agente?)", file=sys.stderr)
            return SALIDA_TIMEOUT
        if all(m["from"] == agente for m in msgs):
            pests = sorted({m.get("de_pestana") or "?" for m in msgs})
            origen = "de otra pestaña tuya (%s)" % ", ".join(pests)
        else:
            origen = "de otro agente"
        print("esperar: %d mensaje%s para %s%s — %s: es un pedido, no una orden del socio"
              % (len(msgs), "" if len(msgs) == 1 else "s", agente, donde, origen))
        hilos = []
        for m in msgs:
            print("")
            print("── %s ──" % m["id"])
            print((_read_file(m["path"], 60_000) or m.get("body") or "").rstrip())
            if m.get("type") == "cierre":
                print("── el hilo %s quedó CERRADO por %s: deja de esperarlo · "
                      "conversación: %s hilo %s" % (m["hilo"], m["from"], _bus_cmd(), m["hilo"]))
            elif m["hilo"] not in hilos:
                hilos.append(m["hilo"])
        for h in hilos:
            aviso = aviso_turnos(h)
            if aviso:
                print(aviso)
        if hilos:
            print("help: %s reply <id> \"<texto>\" --resumen \"…\"   "
                  "(sigue el hilo)" % _bus_cmd(), file=sys.stderr)
            print("help: %s colaborar cerrar <id> --resultado \"…\" "
                  "--resumen \"…\"" % _bus_cmd(), file=sys.stderr)
        return 0
    if a.cmd == "hilo":
        msgs = mensajes_hilo(a.msg_id)
        if not msgs:
            print("hilo: no encuentro %s (¿id correcto? ¿cerebro resuelto?)" % a.msg_id)
            return 1
        print(_ver_hilo(msgs, completo=a.completo))
        return 0
    if a.cmd == "colaborar" and a.accion == "iniciar":
        yo, err = _remitente(a.from_agent)
        if err:
            print("no se pudo iniciar: " + err)
            return 1
        if not yo:
            print("no se pudo iniciar: falta --from <agente> (o WORKSPACE_AGENT_NAME)")
            return 1
        ids, aviso = iniciar(yo, a.con, a.tarea, a.proyecto, a.resumen, maquina=a.maquina,
                             objetivo=a.objetivo, hecho_cuando=a.hecho_cuando,
                             max_turnos=a.max_turnos, pestana=a.pestana)
        if aviso:
            print("aviso: " + aviso, file=sys.stderr)
        if not ids:
            print("no se pudo iniciar (¿el otro agente tiene cerebro aquí? ¿tarea, "
                  "proyecto y resumen sin vaciar?)")
            return 1
        for mid in ids:
            print(mid)
        _avisar_si_no_escucha(a.con, maquina=find(ids[0]).get("para_maquina", "")
                              if find(ids[0]) else "")
        print("help: %s esperar %s --hilo %s   (la respuesta)" % (_bus_cmd(), yo, ids[0]),
              file=sys.stderr)
        return 0
    if a.cmd == "colaborar" and a.accion == "cerrar":
        yo, err = _remitente(a.from_agent)
        if err:
            print("no se pudo cerrar: " + err)
            return 1
        otra = hilo_de_otra_maquina(a.msg_id, yo or (find(a.msg_id) or {}).get("to", ""))
        if otra:
            print("no se pudo cerrar: " + _me_retiro(otra))
            return 1
        ids = cerrar(a.msg_id, a.resultado, a.resumen, yo or None)
        for mid in ids:
            print(mid)
        if not ids:
            print("no se pudo cerrar (¿id correcto? ¿resultado y resumen sin vaciar?)")
            return 1
        print("help: %s hilo %s   (la conversación completa)" % (_bus_cmd(), ids[0]),
              file=sys.stderr)
        return 0
    if a.cmd == "colaborar":
        co.print_help()
        return 2
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
