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
    resolved:                    # ISO al cerrar (done/rejected); vacío antes
    ---

    Cuerpo libre (alcance, entregable esperado, contexto…).

Semántica de `requires_approval`: el mensaje es una SOLICITUD; `done` =
aprobado, `rejected` = rechazado. Para el resto: `claimed` = el agente lo
tomó, `done` = entregado.

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
        --subject "..." [--body "..."] [--approval]
    python3 messages.py inbox <agente>
    python3 messages.py list [--status pending]
    python3 messages.py status <msg_id> <pending|claimed|done|rejected>

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
TYPES = ("encargo", "handoff", "broadcast", "reply", "diff-review")
STATUSES = ("pending", "claimed", "done", "rejected", "awaiting-diff-gate")
FINAL = ("done", "rejected")                # cierran el mensaje → sellan resolved

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


def _sign(sender, to, mtype, subj, approval, ts, body):
    """HMAC-SHA256 del mensaje completo (incluye requires_approval y ts → no
    forjables). Devuelve hexdigest o "" si no hay clave (amputable)."""
    import hashlib
    import hmac as _hmac
    key = _hmac_key()
    if not key:
        return ""
    # el body se firma NORMALIZADO igual que lo devuelve _parse (.strip()) — si no,
    # el '\n' final del archivo escrito rompería el roundtrip firma/verify.
    payload = "\x1f".join([str(sender), str(to), str(mtype), str(subj),
                           "1" if approval else "0", str(ts), str(body or "").strip()])
    return _hmac.new(key, payload.encode("utf-8", "replace"), hashlib.sha256).hexdigest()


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
                    msg.get("ts", ""), msg.get("body", ""))
        return bool(got) and _hmac.compare_digest(got, want)
    except Exception:
        return False


def _safe_name(name):
    """Nombre de agente saneado (minúsculas, [a-z0-9_-], ≤24). '' si no queda nada."""
    return _NAME_RE.sub("", str(name or "").strip().lower())[:24]


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
    nunca queda un mensaje a medias aunque el proceso muera escribiendo."""
    tmp = "%s.tmp%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)
    os.replace(tmp, path)


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
    try:
        findings = secret_scan.gate_text((subj or "") + "\n" + (body or ""),
                                         where="mensaje del bus")
        if findings:
            try:
                print(secret_scan.block_message(findings, "mensaje del bus"),
                      file=sys.stderr)
            except Exception:
                pass
            return True
    except Exception:
        return False
    return False


# ═══════════════════════════════════════════════════════════════════════════
# Escritura: send (append-only — jamás sobrescribe)
# ═══════════════════════════════════════════════════════════════════════════

def send(from_agent, to_agent, type, subject, body="", requires_approval=False,
         brains=None, strict=False):
    """Escribe el mensaje en `<cerebro-destinatario>/msgs/<id>.md`.

    `to_agent="all"` (o type="broadcast" sin destinatario) → fan-out: un
    archivo por cada agente registrado distinto del emisor, cada uno con su
    propio id. `brains` (opcional) debe ser dict {agente: cerebro}; None →
    registry. `strict` (F1.5): secret-gate FAIL-CLOSED (relay autónomo — sin
    secret_scan NO envía). Devuelve la lista de ids escritos ([] si nada)."""
    try:
        mtype = str(type or "").strip().lower()
        sender = _safe_name(from_agent)
        subj = " ".join(str(subject or "").split())[:_CLIP_SUBJECT]
        if mtype not in TYPES or not sender or not subj:
            return []
        bm = brains if isinstance(brains, dict) else registered_brains()
        to_raw = str(to_agent or "").strip().lower()
        if to_raw in ("all", "*", "todos") or (mtype == "broadcast" and not to_raw):
            targets = [a for a in sorted(bm) if _safe_name(a) != sender]
        else:
            targets = [to_raw]
        gbody = str(body or "")[:_CLIP_BODY]
        # A7 · gate de secretos ANTES de escribir: el cuerpo se sincroniza a todos
        # los cerebros; un secreto ahí ya es una fuga de equipo. Bloquea (no envía
        # nada) y dice cómo saltarlo; falla-suave si secret_scan no está.
        if _bus_secret_block(subj, gbody, strict=strict):
            return []
        ts = _dt.datetime.now()
        ids = []
        for target in targets:
            to = _safe_name(target)
            brain = bm.get(target) or bm.get(to) or ""
            if not to or not brain or not os.path.isdir(brain):
                continue
            mid = _write_one(brain, sender, to, mtype, subj,
                             gbody, bool(requires_approval), ts)
            if mid:
                ids.append(mid)
        return ids
    except Exception:
        return []


def _write_one(brain, sender, to, mtype, subj, body, approval, ts):
    """Un archivo de mensaje en `brain/msgs/`. Devuelve el id o None."""
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
        # HMAC de autenticidad (F1.5 cond 5): firma from/to/type/subject/approval/
        # ts/body → el autónomo rechaza mensajes forjados. Amputable (clave
        # ausente → "" → no rompe; el autónomo cae a no-procesar).
        sig = _sign(sender, to, mtype, subj, approval, ts_iso, gbody)
        text = ("---\n"
                "id: %s\n"
                "from: %s\n"
                "to: %s\n"
                "type: %s\n"
                "status: pending\n"
                "subject: %s\n"
                "requires_approval: %s\n"
                "ts: %s\n"
                "hmac: %s\n"
                "resolved:\n"
                "---\n\n%s" % (mid, sender, to, mtype, subj,
                               "true" if approval else "false",
                               ts_iso, sig, gbody))
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

def set_status(msg_id, status, brains=None):
    """Cambia `status:` en el frontmatter del mensaje (y sella `resolved:` si
    el status es final: done/rejected). Edición ATÓMICA (tmp + os.replace) y
    ACOTADA: solo esas líneas — cuerpo y demás campos quedan intactos.
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
                okw = _rmw()          # degrada a sin-lock (mejor que perder el cambio)
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

def reply(msg_id, body, from_agent=None, brains=None):
    """Responde a un mensaje existente sin re-escribir from/to: el que responde es su
    destinatario original (`to`), y va de vuelta a su remitente (`from`), type='reply',
    subject 'Re: <orig>'. Hace natural la ida y vuelta de delegación. Devuelve los ids
    escritos ([] si el mensaje no existe / falla — falla-suave)."""
    m = find(msg_id, brains)
    if not m:
        return []
    frm = _safe_name(from_agent) if from_agent else m.get("to", "")
    to = m.get("from", "")
    subj = m.get("subject", "")
    if not subj.lower().startswith("re:"):
        subj = "Re: " + subj
    return send(frm, to, "reply", subj, body, brains=brains)


def _fmt(m):
    flag = " [!]" if (m["requires_approval"] and m["status"] == "pending") else ""
    return "%-9s %s -> %s · %s · %s%s   (%s)" % (
        "[" + m["status"] + "]", m["from"] or "?", m["to"] or "?",
        m["type"] or "?", m["subject"][:60], flag, m["id"])


def main(argv=None):
    import argparse
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
    a = ap.parse_args(argv)

    if a.cmd == "send":
        ids = send(a.from_agent, a.to_agent, a.type, a.subject, a.body, a.approval)
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
            print("help: python3 messages.py status <id> done   (o: claimed / rejected)",
                  file=sys.stderr)
            print("help: python3 messages.py reply <id> \"<texto>\"   (from/to se infieren)",
                  file=sys.stderr)
        else:
            print("inbox: 0 mensajes pendientes para %s" % agent)
            print("help: python3 messages.py list   (todos los mensajes del bus)",
                  file=sys.stderr)
            print("help: python3 messages.py send --from %s --to <agente> "
                  "--type encargo --subject \"...\" --body \"...\"" % agent,
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
        ids = reply(a.msg_id, a.body, a.from_agent)
        for mid in ids:
            print(mid)
        if not ids:
            print("no se pudo responder (¿id correcto? ¿cerebro resuelto?)")
        return 0 if ids else 1
    ap.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
