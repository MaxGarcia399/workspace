#!/usr/bin/env python3
"""WORKSPACE · neutral_transcript — schema neutral de transcripts + ingesters.

La capa de INDEPENDENCIA DE DATOS del harness (promoción a producción del
spike `research/spikes/datos-normalizacion/`, rama `spike/model-agnostic-datos`,
validado contra 144 transcripts reales con equivalencia byte a byte):
la memoria de WORKSPACE se construye sobre un schema de transcript PROPIO
(`workspace.transcript` v1), no sobre el `.jsonl` de ningún vendor. Cada motor
aporta un ingester que normaliza su formato crudo al schema; los consumidores
(la revisión de skills, el respaldo, la memoria) jamás ven el formato del vendor.

DERIVACIÓN DEL SCHEMA (consejo de la 2ª opinión, research/model-agnostic-
2a-opinion.md: derivar de lo que la destilación consume HOY, no de motores
hipotéticos). Lo que `dream.sanitize_transcript` extrae, con evidencia:

  - turnos de diálogo user/assistant con SOLO texto visible
    (thinking / tool_result / attachments / snapshots → fuera)
  - filtro de inyecciones del harness (ruido por-vendor)
  - meta: session_id, title, git_branch, cwd, first_ts, last_ts, n_lines
  - files_touched: paths de tools de escritura, VERBATIM (ley 3)

El schema es deliberadamente LOSSY respecto al crudo: thinking/reasoning,
cuerpos de tool_result e imágenes quedan fuera POR DISEÑO (higiene de recall
OpenClaw §11 — la destilación jamás los usa). El crudo respaldado (Y2b) sigue
siendo la fuente de último recurso; los docs neutrales son DERIVADOS
(normalización on-read, cero migración destructiva). `schema_version` existe
para evolucionarlo si memoria v2 algún día pide más.

FORMA (dict JSON-serializable, stdlib puro):

{
  "schema": "workspace.transcript",
  "schema_version": 1,
  "session": {
    "id": "<session id, requerido>",
    "engine": "claude-code | codex | …",     ← provenance del vendor
    "title": "",                              ← "" si el vendor no lo tiene
    "cwd": "", "git_branch": "",
    "first_ts": "", "last_ts": "",            ← ISO-8601 o ""
    "source_path": "",                        ← provenance del archivo crudo
    "n_source_lines": 0                       ← líneas del crudo (gate trivial)
  },
  "turns": [
    {"role": "user"|"assistant", "ts": "", "text": "<texto visible>",
     "noise": false,          ← true = inyección del harness / no-diálogo
     "tool_calls": [{"name": "", "id": "", "input": {…}}]}
  ],
  "files_touched": ["<paths verbatim, dedupe conservando orden>"]
}

INGESTERS:

  parse_claude_code(path)  ~/.claude/projects/<enc>/<sid>.jsonl
      Shape VERIFICADO: contra el código consumidor histórico (el parser
      nativo de dream), el fixture de la suite y 144 transcripts reales
      (spike 2026-07-02: 144/144 equivalentes, 0 difs, 0 errores).

  parse_codex(path)        ~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl
      ⚠ APROXIMACIÓN DOCUMENTADA — A-VERIFICAR CONTRA UN ROLLOUT REAL.
      Basada en fuentes públicas (openai/codex discussion #3827; DEV
      "Reverse engineering Codex CLI rollout traces"; deepwiki openai/codex):
      cada línea = {"timestamp","type","payload"} con type ∈ {session_meta,
      response_item, event_msg, turn_context}. Funcional contra el fixture
      de la suite; los puntos A-VERIFICAR están marcados en el código.

  detect_format(path) / ingest(path)  — detección por shape; NUNCA adivina
      (formato desconocido → None; el caller decide su fallback).

  sanitized_view(doc) → (texto, meta) — el adaptador hacia la destilación:
      reproduce EXACTO el contrato del sanitizador histórico de dream
      (mismos labels [SOCIO]/[AGENTE], mismos keys de meta, mismo truncado
      head+tail). La suite lo clava byte a byte (tests/test_neutral_transcript).

Los identificadores se copian VERBATIM (identifierPolicy: strict, ley 3 de
la destilación). `noise` existe porque cada vendor inyecta ruido distinto
(Claude: <system-reminder>; Codex: <user_instructions>/<environment_context>)
y el filtro pertenece al INGESTER, no al consumidor.

Cero dependencias (stdlib, Python 3.9+). Falla-suave: líneas corruptas se
saltan; un archivo ilegible levanta OSError (el caller decide). Amputable
(C10): sus consumidores fallan suave si este módulo no está.
"""
import json
import os  # noqa: F401  (paridad de entorno con el resto del harness)
import re

SCHEMA_NAME = "workspace.transcript"
SCHEMA_VERSION = 1

VALID_ROLES = ("user", "assistant")

# claves requeridas (el resto es opcional-con-default; ver empty_*)
_SESSION_KEYS = ("id", "engine", "title", "cwd", "git_branch",
                 "first_ts", "last_ts", "source_path", "n_source_lines")
_TURN_KEYS = ("role", "ts", "text", "noise", "tool_calls")

# Cota de la vista sanitizada (heredada del sanitizador de dream.py, retirado
# el 2026-10-16). La usan sus consumidores directos (revisión de skills).
MAX_SANITIZED_CHARS = 60_000
_TRUNC_MARKER = "\n\n[… TRUNCADO por el harness: transcript largo …]\n\n"

# tools de escritura por vendor → files_touched (verbatim, ley 3)
CLAUDE_WRITE_TOOLS = ("Write", "Edit", "NotebookEdit")

# prefijos de ruido inyectado por el harness, por vendor
CLAUDE_NOISE_PREFIXES = ("<system-reminder", "<command-name", "<command-message",
                         "<local-command", "<task-notification", "<cross-session-message",
                         "<bash-stdout", "<bash-stderr", "[Request interrupted")
CODEX_NOISE_PREFIXES = ("<user_instructions>", "<environment_context>",
                        "<ENVIRONMENT_CONTEXT>",  # A-VERIFICAR: casing real
                        "# AGENTS.md instructions for")  # codex 2026-10: el AGENTS.md llega como «user»


# ── constructores + validación del schema ──────────────────────────────────
def empty_session(**kw):
    s = {"id": "", "engine": "", "title": "", "cwd": "", "git_branch": "",
         "first_ts": "", "last_ts": "", "source_path": "",
         "n_source_lines": 0}
    s.update(kw)
    return s


def empty_doc(**session_kw):
    return {"schema": SCHEMA_NAME, "schema_version": SCHEMA_VERSION,
            "session": empty_session(**session_kw),
            "turns": [], "files_touched": []}


def make_turn(role, text, ts="", noise=False, tool_calls=None):
    return {"role": role, "ts": ts or "", "text": text or "",
            "noise": bool(noise), "tool_calls": list(tool_calls or [])}


def make_tool_call(name, input_=None, id_=""):
    return {"name": name or "", "id": id_ or "", "input": dict(input_ or {})}


def validate(doc):
    """Valida un doc contra el schema. Devuelve lista de problemas ([] = ok).
    Falla-suave por diseño: reporta, no levanta."""
    problems = []
    if not isinstance(doc, dict):
        return ["doc no es dict"]
    if doc.get("schema") != SCHEMA_NAME:
        problems.append("schema != %s" % SCHEMA_NAME)
    if doc.get("schema_version") != SCHEMA_VERSION:
        problems.append("schema_version != %d" % SCHEMA_VERSION)
    ses = doc.get("session")
    if not isinstance(ses, dict):
        problems.append("session ausente o no-dict")
    else:
        for k in _SESSION_KEYS:
            if k not in ses:
                problems.append("session.%s ausente" % k)
        if not ses.get("id"):
            problems.append("session.id vacío (requerido)")
    turns = doc.get("turns")
    if not isinstance(turns, list):
        problems.append("turns ausente o no-list")
        turns = []
    for i, t in enumerate(turns):
        if not isinstance(t, dict):
            problems.append("turns[%d] no es dict" % i)
            continue
        for k in _TURN_KEYS:
            if k not in t:
                problems.append("turns[%d].%s ausente" % (i, k))
        if t.get("role") not in VALID_ROLES:
            problems.append("turns[%d].role inválido: %r" % (i, t.get("role")))
        if not isinstance(t.get("tool_calls", []), list):
            problems.append("turns[%d].tool_calls no es list" % i)
    if not isinstance(doc.get("files_touched"), list):
        problems.append("files_touched ausente o no-list")
    return problems


# ── infraestructura común de parseo ────────────────────────────────────────
def _iter_jsonl(path):
    """Itera (n_lineas_no_vacias_hasta_aqui, dict|None) — None = línea
    corrupta/no-dict (se cuenta pero no se parsea; mismo conteo que el
    sanitizador histórico de dream, que suma n_lines ANTES de json.loads)."""
    with open(path, encoding="utf-8", errors="replace") as fh:
        n = 0
        for raw in fh:
            raw = raw.strip()
            if not raw:
                continue
            n += 1
            try:
                d = json.loads(raw)
            except ValueError:
                yield n, None
                continue
            yield n, (d if isinstance(d, dict) else None)


def _dedupe(items):
    seen = set()
    return [x for x in items if not (x in seen or seen.add(x))]


# ── Claude Code ────────────────────────────────────────────────────────────
def parse_claude_code(path):
    """.jsonl de Claude Code → doc neutral. Espejo fiel de lo que el
    sanitizador histórico de dream extrae, PERO conservando la estructura
    (turnos + tool_calls) en vez de aplanar a texto."""
    doc = empty_doc(engine="claude-code", source_path=path)
    ses = doc["session"]
    files, n_lines = [], 0
    for n, d in _iter_jsonl(path):
        n_lines = n
        if d is None:
            continue
        t = d.get("type")
        if t == "custom-title":
            ses["title"] = d.get("customTitle", "") or ses["title"]
            continue
        if t not in ("user", "assistant"):
            continue
        # mismas semánticas que el parser nativo (get con default=prev)
        ses["id"] = d.get("sessionId", ses["id"])
        ses["git_branch"] = d.get("gitBranch", ses["git_branch"])
        ses["cwd"] = d.get("cwd", ses["cwd"])
        ts = d.get("timestamp", "")
        if ts:
            ses["first_ts"] = ses["first_ts"] or ts
            ses["last_ts"] = ts
        msg = d.get("message") or {}
        content = msg.get("content")
        texts, tool_calls = [], []
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                bt = block.get("type")
                if bt == "text":
                    texts.append(block.get("text", ""))
                elif bt == "tool_use":
                    inp = block.get("input") or {}
                    inp = inp if isinstance(inp, dict) else {}
                    tool_calls.append(make_tool_call(
                        block.get("name", ""), inp, block.get("id", "")))
                    fp = inp.get("file_path")
                    if fp and block.get("name") in CLAUDE_WRITE_TOOLS:
                        files.append(fp)
                # thinking / tool_result / imágenes → fuera (higiene §11)
        text = "\n".join(x for x in texts if x and x.strip())
        if not text.strip() and not tool_calls:
            continue
        # isMeta (nota de imagen, caveat de comandos) e isCompactSummary (el
        # resumen al compactar) llegan como «user» pero los escribe el harness
        noise = (t == "user"
                 and (text.lstrip().startswith(CLAUDE_NOISE_PREFIXES)
                      or bool(d.get("isMeta")) or bool(d.get("isCompactSummary"))))
        doc["turns"].append(make_turn(
            t, text, ts=ts, noise=noise, tool_calls=tool_calls))
    ses["n_source_lines"] = n_lines
    doc["files_touched"] = _dedupe(files)
    return doc


# ── Codex CLI (⚠ A-VERIFICAR contra un rollout real) ──────────────────────
_PATCH_FILE_RX = re.compile(
    r"\*\*\*\s+(?:Add|Update|Delete)\s+File:[ \t]+([^\n]+)")


def _patch_files(args, args_raw):
    """Paths tocados por un apply_patch. Busca los marcadores del formato
    de patch de Codex en los VALORES decodificados de `arguments` (pitfall
    del spike: el raw trae \\n escapado y el regex se comería el patch
    entero); fallback al raw des-escapado si arguments no fue JSON."""
    if isinstance(args, dict) and not args.get("_raw"):
        hay = "\n".join(v for v in args.values() if isinstance(v, str))
    else:
        hay = str(args_raw).replace("\\n", "\n")
    return [m.group(1).strip() for m in _PATCH_FILE_RX.finditer(hay)]


def parse_codex(path):
    """rollout-*.jsonl de Codex CLI → doc neutral.

    ⚠ APROXIMACIÓN basada en fuentes públicas. Decisiones documentadas
    (todas A-VERIFICAR contra un rollout real de Codex):
    - Diálogo: SOLO response_item type=message. Los event_msg
      user_message/agent_message se IGNORAN (las fuentes reportan que
      duplican los response_item → tomarlos ambos duplicaría turnos).
    - reasoning / function_call_output / token_count → fuera (equivalen a
      thinking / tool_result de Claude; higiene §11).
    - files_touched: de function_call apply_patch, buscando
      "*** Add/Update/Delete File: <path>" en `arguments` (formato del
      apply_patch tool de Codex). Escrituras vía `shell` heredoc NO se
      capturan (limitación documentada).
    - Codex no tiene título de sesión (custom-title es de Claude) → "".
    - git branch: payload de session_meta trae `git.branch` en versiones
      recientes; si falta, "".
    """
    doc = empty_doc(engine="codex", source_path=path)
    ses = doc["session"]
    files, n_lines = [], 0
    for n, d in _iter_jsonl(path):
        n_lines = n
        if d is None:
            continue
        t = d.get("type")
        ts = d.get("timestamp", "")
        payload = d.get("payload")
        payload = payload if isinstance(payload, dict) else {}
        if t == "session_meta":
            ses["id"] = payload.get("session_id") or payload.get("id", ses["id"]) or ses["id"]
            ses["cwd"] = payload.get("cwd", ses["cwd"]) or ses["cwd"]
            git = payload.get("git")
            if isinstance(git, dict):
                ses["git_branch"] = git.get("branch", "") or ses["git_branch"]
            pts = payload.get("timestamp", "") or ts
            if pts:
                ses["first_ts"] = ses["first_ts"] or pts
                ses["last_ts"] = pts
            continue
        if t != "response_item":
            continue        # event_msg / turn_context → fuera (ver docstring)
        pt = payload.get("type")
        if ts:
            ses["first_ts"] = ses["first_ts"] or ts
            ses["last_ts"] = ts
        if pt == "message":
            role = payload.get("role", "")
            if role not in VALID_ROLES:
                continue    # system/developer → no es diálogo socio↔agente
            texts = []
            content = payload.get("content")
            if isinstance(content, str):
                texts.append(content)
            elif isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") in (
                            "input_text", "output_text", "text"):
                        texts.append(block.get("text", ""))
            text = "\n".join(x for x in texts if x and x.strip())
            if not text.strip():
                continue
            noise = (role == "user"
                     and text.lstrip().startswith(CODEX_NOISE_PREFIXES))
            doc["turns"].append(make_turn(role, text, ts=ts, noise=noise))
        elif pt == "function_call":
            name = payload.get("name", "")
            args_raw = payload.get("arguments", "")
            try:
                args = json.loads(args_raw)
                args = args if isinstance(args, dict) else {"_args": args}
            except (TypeError, ValueError):
                args = {"_raw": str(args_raw)[:2000]}
            tc = make_tool_call(name, args, payload.get("call_id", ""))
            # tool call = turno del asistente sin texto (igual que Claude)
            doc["turns"].append(make_turn(
                "assistant", "", ts=ts, tool_calls=[tc]))
            if name == "apply_patch":
                files.extend(_patch_files(args, args_raw))
        # reasoning / function_call_output / otros → fuera
    ses["n_source_lines"] = n_lines
    doc["files_touched"] = _dedupe(files)
    return doc


_AGY_REQUEST = re.compile(r"<USER_REQUEST>(.*?)</USER_REQUEST>", re.S)


def parse_antigravity(path):
    """Official hook transcript: visible completed dialogue only.

    GENERIC contains tool output, not assistant dialogue. Never ingest
    thinking, tools, system messages, or recursively search for text.
    """
    from pathlib import Path
    name = Path(path).stem
    sid = name[len("antigravity-"):] if name.startswith("antigravity-") else (Path(path).parents[2].name if name == "transcript" else name)
    doc = empty_doc(id=sid, engine="antigravity", source_path=str(path))
    steps = {}
    for n, row in _iter_jsonl(path):
        doc["session"]["n_source_lines"] = n
        if not isinstance(row, dict):
            continue
        kind, source = row.get("type"), row.get("source")
        role = {("USER_INPUT", "USER_EXPLICIT"): "user",
                ("PLANNER_RESPONSE", "MODEL"): "assistant"}.get((kind, source))
        text, idx = row.get("content"), row.get("step_index")
        if (not role or row.get("status") != "DONE" or
                not isinstance(text, str) or not text.strip() or
                type(idx) is not int or idx < 0):
            continue
        if role == "user":
            # agy envuelve lo que escribió el socio: <USER_REQUEST>…</USER_REQUEST>
            # + <ADDITIONAL_METADATA> (hora local). Solo cuenta lo de adentro.
            m = _AGY_REQUEST.search(text)
            if m and m.group(1).strip():
                text = m.group(1).strip()
        ts = row.get("created_at")
        steps[idx] = make_turn(role, text, ts if isinstance(ts, str) else "")
    doc["turns"] = [steps[k] for k in sorted(steps)]
    if doc["turns"]:
        doc["session"]["first_ts"] = doc["turns"][0]["ts"]
        doc["session"]["last_ts"] = doc["turns"][-1]["ts"]
    return doc


# ── OpenCode ───────────────────────────────────────────────────────────────
#: Marca de la cabecera del .jsonl que arma session_continuity.capture_opencode
#: a partir del export OFICIAL (`opencode session export <id>`). Cada mensaje
#: va ENVUELTO (`opencode_message`) para que ningún consumidor lo confunda con
#: el formato de Claude Code (ambos usan type user/assistant).
OPENCODE_HEADER = "opencode_session"
OPENCODE_MESSAGE = "opencode_message"


def _ms_iso(ms):
    import datetime
    try:
        return datetime.datetime.fromtimestamp(
            float(ms) / 1000.0, datetime.timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def parse_opencode(path):
    """Export oficial de opencode → doc neutral. Solo diálogo VISIBLE: el
    texto del usuario y las partes `text` de la respuesta. Jamás reasoning,
    herramientas ni marcas idle (misma regla que Antigravity)."""
    doc = empty_doc(id="", engine="opencode", source_path=str(path))
    for n, row in _iter_jsonl(path):
        doc["session"]["n_source_lines"] = n
        if not isinstance(row, dict):
            continue
        if row.get("type") == OPENCODE_HEADER:
            doc["session"]["id"] = str(row.get("id") or "")
            doc["session"]["title"] = str(row.get("title") or "")
            doc["session"]["cwd"] = str(row.get("directory") or "")
            continue
        if row.get("type") != OPENCODE_MESSAGE or not isinstance(row.get("message"), dict):
            continue
        m = row["message"]
        if isinstance(m.get("info"), dict) and isinstance(m.get("parts"), list):
            # opencode 1 (VERIFICADO 1.19.3): {"info": {"role", "time"},
            # "parts": [{"type": "text"|"step-start"|…, "text"}]}
            info = m["info"]
            text = "\n".join(p.get("text", "") for p in m["parts"]
                             if isinstance(p, dict) and p.get("type") == "text"
                             and isinstance(p.get("text"), str)).strip()
            if info.get("role") in ("user", "assistant") and text:
                doc["turns"].append(make_turn(info["role"], text,
                                              _ms_iso((info.get("time") or {}).get("created"))))
            continue
        ts = _ms_iso((m.get("time") or {}).get("created"))
        if m.get("type") == "user":
            text = m.get("text")
            if isinstance(text, str) and text.strip():
                doc["turns"].append(make_turn("user", text, ts))
        elif m.get("type") == "assistant":
            parts = m.get("content") if isinstance(m.get("content"), list) else []
            text = "\n".join(p.get("text", "") for p in parts
                             if isinstance(p, dict) and p.get("type") == "text"
                             and isinstance(p.get("text"), str)).strip()
            if text:
                doc["turns"].append(make_turn("assistant", text, ts))
    if doc["turns"]:
        doc["session"]["first_ts"] = doc["turns"][0]["ts"]
        doc["session"]["last_ts"] = doc["turns"][-1]["ts"]
    return doc


# ── OpenClaw ───────────────────────────────────────────────────────────────
#: OpenClaw 2026.5.12 (VERIFICADO): agents/<id>/sessions/<sessionId>.jsonl.
#: 1ª línea {"type":"session","version":N,"id":…,"cwd":…}; los turnos son
#: {"type":"message","message":{"role":"user|assistant","content":[{type,text}]}}.
#: OpenClaw antepone al texto del usuario un sobre con la fecha
#: («[Thu 2026-10-15 10:27 CST] …»): se quita, no es diálogo.
_OPENCLAW_ENVELOPE = re.compile(
    r"^\[(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{4}-\d{2}-\d{2} \d{2}:\d{2}[^\]]*\]\s*")


def _is_openclaw_header(d):
    return (d.get("type") == "session" and type(d.get("version")) is int
            and bool(d.get("id")) and "cwd" in d)


def parse_openclaw(path):
    """Transcript de sesión de OpenClaw → doc neutral. Solo diálogo VISIBLE:
    partes `text` de user/assistant. Jamás thinking, herramientas, resultados
    de herramientas, errores ni eventos del runtime (model_change, custom…)."""
    doc = empty_doc(id="", engine="openclaw", source_path=str(path))
    for n, row in _iter_jsonl(path):
        doc["session"]["n_source_lines"] = n
        if not isinstance(row, dict):
            continue
        if _is_openclaw_header(row):
            doc["session"]["id"] = str(row.get("id") or "")
            doc["session"]["cwd"] = str(row.get("cwd") or "")
            continue
        if row.get("type") != "message" or not isinstance(row.get("message"), dict):
            continue
        m = row["message"]
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        content = m.get("content")
        if isinstance(content, str):          # export 2026.9+/10.x: user como string
            content = [{"type": "text", "text": content}]
        parts = content if isinstance(content, list) else []
        text = "\n".join(p.get("text", "") for p in parts
                         if isinstance(p, dict) and p.get("type") == "text"
                         and isinstance(p.get("text"), str)).strip()
        if role == "user":
            text = _OPENCLAW_ENVELOPE.sub("", text).strip()
        if text:
            ts = row.get("timestamp")
            doc["turns"].append(make_turn(role, text, ts if isinstance(ts, str) else ""))
    if doc["turns"]:
        doc["session"]["first_ts"] = doc["turns"][0]["ts"]
        doc["session"]["last_ts"] = doc["turns"][-1]["ts"]
    return doc


# ── Hermes Agent ───────────────────────────────────────────────────────────
#: Marca de la cabecera del .jsonl que arma session_continuity.capture_hermes a
#: partir del export OFICIAL (`hermes sessions export --format jsonl`, v0.18.2
#: VERIFICADO): un registro por sesión con `messages` [{role, content,
#: timestamp (epoch), reasoning, tool_calls…}]. Cada mensaje va ENVUELTO
#: (`hermes_message`) para que ningún consumidor lo confunda con otro formato.
HERMES_HEADER = "hermes_session"
HERMES_MESSAGE = "hermes_message"
_THINK_BLOCK = re.compile(r"<think>.*?</think>\s*", re.S)


def _epoch_iso(sec):
    import datetime
    try:
        return datetime.datetime.fromtimestamp(
            float(sec), datetime.timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError, OverflowError, OSError):
        return ""


def _hermes_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content
                         if isinstance(p, dict) and p.get("type") in ("text", "input_text", "output_text")
                         and isinstance(p.get("text"), str))
    return ""


def parse_hermes(path):
    """Export oficial de Hermes → doc neutral. Solo diálogo VISIBLE: texto de
    user/assistant. Jamás reasoning, herramientas (rol tool / tool_calls) ni
    mensajes de sistema."""
    doc = empty_doc(id="", engine="hermes", source_path=str(path))
    for n, row in _iter_jsonl(path):
        doc["session"]["n_source_lines"] = n
        if not isinstance(row, dict):
            continue
        if row.get("type") == HERMES_HEADER:
            doc["session"]["id"] = str(row.get("id") or "")
            doc["session"]["title"] = str(row.get("title") or "")
            doc["session"]["cwd"] = str(row.get("cwd") or "")
            continue
        if row.get("type") != HERMES_MESSAGE or not isinstance(row.get("message"), dict):
            continue
        m = row["message"]
        role = m.get("role")
        if role not in ("user", "assistant"):
            continue
        text = _hermes_text(m.get("content"))
        if role == "assistant":
            text = _THINK_BLOCK.sub("", text)
        text = text.strip()
        if text:
            doc["turns"].append(make_turn(role, text, _epoch_iso(m.get("timestamp"))))
    if doc["turns"]:
        doc["session"]["first_ts"] = doc["turns"][0]["ts"]
        doc["session"]["last_ts"] = doc["turns"][-1]["ts"]
    return doc


# ── detección + entrada única ──────────────────────────────────────────────
_CODEX_TYPES = {"session_meta", "response_item", "event_msg", "turn_context",
                "compacted"}
_CLAUDE_TYPES = {"user", "assistant", "custom-title", "file-history-snapshot",
                 "attachment", "queue-operation", "last-prompt", "system",
                 "agent-name", "mode", "permission-mode", "summary"}


def detect_format(path, probe_lines=25):
    """Husmea las primeras líneas y devuelve 'claude-code' | 'codex' | None.
    None = shape desconocido (el caller decide su fallback; JAMÁS se
    adivina — regla del spike, evita normalizar basura en silencio)."""
    codex = claude = 0
    try:
        for n, d in _iter_jsonl(path):
            if d is None:
                if n >= probe_lines:
                    break
                continue
            t = d.get("type")
            if t == OPENCODE_HEADER:
                return "opencode"
            if t == HERMES_HEADER:
                return "hermes"
            if _is_openclaw_header(d):
                return "openclaw"
            if (t in {"USER_INPUT", "PLANNER_RESPONSE", "GENERIC", "SYSTEM_MESSAGE"}
                    and type(d.get("step_index")) is int
                    and "source" in d and "status" in d):
                return "antigravity"
            if t in _CODEX_TYPES and "payload" in d:
                codex += 1
            elif t in _CLAUDE_TYPES:
                claude += 1
            if n >= probe_lines:
                break
    except OSError:
        return None
    if codex and codex >= claude:
        return "codex"
    if claude:
        return "claude-code"
    return None


PARSERS = {"claude-code": parse_claude_code, "codex": parse_codex,
           "antigravity": parse_antigravity, "opencode": parse_opencode,
           "openclaw": parse_openclaw, "hermes": parse_hermes}


def ingest(path):
    """Archivo de sesión de cualquier vendor conocido → doc neutral.
    Devuelve None si el shape no se reconoce (nunca adivina, nunca revienta
    por contenido — solo OSError si el archivo es ilegible)."""
    fmt = detect_format(path)
    if fmt is None:
        return None
    return PARSERS[fmt](path)


# ── adaptador hacia la destilación ─────────────────────────────────────────
def sanitized_view(doc, max_chars=MAX_SANITIZED_CHARS):
    """doc neutral → (texto_sanitizado, metadatos) con EXACTAMENTE el
    contrato del sanitizador de dream: mismos keys de meta, mismos labels
    [SOCIO]/[AGENTE], mismo truncado head+tail. Es el puente por el que la
    destilación consume el schema neutral; la equivalencia byte a byte la
    clava la suite (y la clavó el spike sobre 144 transcripts reales)."""
    ses = doc.get("session", {})
    meta = {"session_id": ses.get("id", ""),
            "title": ses.get("title", ""),
            "git_branch": ses.get("git_branch", ""),
            "cwd": ses.get("cwd", ""),
            "first_ts": ses.get("first_ts", ""),
            "last_ts": ses.get("last_ts", ""),
            "n_lines": ses.get("n_source_lines", 0),
            "files_touched": list(doc.get("files_touched", []))}
    turns = []
    for t in doc.get("turns", []):
        text = (t.get("text") or "").strip()
        if not text or t.get("noise"):
            continue
        who = "SOCIO" if t.get("role") == "user" else "AGENTE"
        turns.append("[%s] %s" % (who, text))
    text = "\n\n".join(turns)
    if len(text) > max_chars:
        half = max_chars // 2
        text = text[:half] + _TRUNC_MARKER + text[-half:]
    return text, meta
