"""WORKSPACE · metricas_motores.kiro — parser de métricas de Kiro CLI (`kiro-cli`).

Fuente: el respaldo que Workspace deja al cerrar
(`<estado>/transcripts-backup/<enc>/kiro-<sess_…>.jsonl`; session_continuity.
capture_kiro), copia envuelta de `messages.jsonl` de la sesión V3. Se
REESCRIBE entero en cada cierre → cursor por filas (metricas.recorrer_reescrito)
y huellas por id de mensaje (Kiro los hace únicos: `<toolCallId>-call` /
`-result`, `<turnId>-turn-start` / `-turn-end` / `-usage`).

Formato VERIFICADO con una sesión real del guion G1 (Kiro CLI 3.1.0, agente V3
de fábrica, macOS, cuenta de Kiro, claude-haiku-5.5, 2026-11-06; golden en
tests/fixtures/metricas/kiro/3.1.0/). Solo claves:
  · cabecera {type: "kiro_session", id, title, cwd, created, updated} (la arma
    Workspace; `updated` cambia en cada cierre).
  · {type: "kiro_message", message: {id, timestamp, payload: {type, …}}} con
    payload.type:
      user          content (lo que escribió el socio); syntheticUserMessageReason
                    marcaría los que no escribió (no visto en la G1).
      turn_start / turn_end   turnId (turn_end.stopReason: end_turn visto).
      assistant     content, operationType (Reasoning | Say); reasoningModelId
                    solo en los de razonamiento.
      tool_call     toolCallId, toolName (read_file, fs_write, execute_bash),
                    kind (read | edit | execute), args{path|command}, filePath,
                    status (approved | failed).
      tool_result   toolCallId, success; execute_bash termina su content con
                    «Exit Code: N» (un comando que sale con ≠ 0 es success = false).
      usage_summary promptTurnSummaries[]{unit: credit, usage}, elapsedTime (ms):
                    créditos de Kiro, no USD ni tokens.
      agent_note, steering_inclusion, session_start, session_metadata
      (contextUsage), pending_interaction / interaction_resolved (permisos de
      herramientas), session_event → se reconocen y no cuentan.
  Tokens, modelo pedido y costo en USD no aparecen (3.1.0). Las sesiones V2
  (`kiro-cli chat --v2`, filas {kind, data}) NO se reconocen: sin golden, la
  fila sale «formato_desconocido» (todo null), jamás un 0.
"""
import os
import re

import metricas as M
from metricas_motores.claude_code import _rutas_leidas  # misma regla de lectores

MOTOR = "kiro"
VERSION = "kiro/1"
#: Versiones EXACTAS verificadas con su golden (tests/fixtures/metricas/kiro/<versión>/).
VERIFIED_VERSIONS = ("3.1.0",)
_SIN = "messages.jsonl no lo trae (3.1.0)"
COBERTURA = {
    "motor_version": ("parcial", "el respaldo no la trae: la caché de engine_versions al "
                                 "cerrar en vivo; null en la historia importada"),
    "modo_senales": ("no", "messages.jsonl no dice cómo se lanzó la sesión (3.1.0)"),
    "duracion_activa_s": ("parcial", "turn_start → turn_end de cada turno; un turno cortado no "
                                     "trae turn_end"),
    "tiempo_humano_est_s": ("si", ""),
    "modelos": ("no", "sin tokens: usage_summary trae créditos de Kiro (3.1.0)"),
    "modelo_pedido": ("no", _SIN),
    "esfuerzo": ("no", _SIN),
    "permisos": ("no", "solo pending_interaction por herramienta, no el modo de la sesión "
                       "(3.1.0)"),
    "tokens_motor": ("no", _SIN),
    "costo_usd": ("no", "usage_summary cuenta créditos de Kiro, no USD (3.1.0)"),
    "facturacion": ("no", _SIN),
    "cuota": ("no", _SIN),
    "herramientas.llamadas": ("si", "payload tool_call"),
    "herramientas.errores": ("si", "tool_result.success = false (salvo un comando que salió "
                                   "con ≠ 0)"),
    "herramientas.comandos_no_cero": ("si", "execute_bash con success = false y «Exit Code: N» "
                                            "≠ 0 al final de su salida"),
    "respuestas_error": ("no", "sin verificar cómo registra un error del proveedor (3.1.0)"),
    "interrupciones": ("no", "turn_end.stopReason = end_turn visto; la interrupción no se "
                             "verificó (la G1 mínima no interrumpe; 3.1.0)"),
    "mensajes_usuario": ("si", "payload user sin syntheticUserMessageReason"),
    "skills": ("si", "tool_call kind read sobre …/skills/<nombre>/SKILL.md"),
    "escritos.archivos": ("parcial", "tool_call kind edit que salió bien; lo escrito por "
                                     "execute_bash no se ve"),
    "escritos.entregables": ("parcial", "igual que escritos.archivos"),
    "subagentes": ("no", "no los separa (sin verificar; 3.1.0)"),
    "turnos": ("si", "cada mensaje del socio abre uno"),
}
#: Retomar = la misma sesión (--resume-id) y Workspace reescribe el respaldo.
CONTINUACION = {"retomar": "respaldo_reescrito", "continuar": "desconocido"}
_TIPOS = frozenset(("kiro_session", "kiro_message"))
#: tipos de payload VISTOS en 3.1.0 que se reconocen y no cuentan
_SIN_CONTAR = frozenset(("agent_note", "steering_inclusion", "session_start",
                         "session_metadata", "pending_interaction", "interaction_resolved",
                         "session_event", "usage_summary"))
_CUENTAN = frozenset(("user", "turn_start", "turn_end", "assistant", "tool_call",
                      "tool_result"))
_EXIT = re.compile(r"Exit Code: (-?\d+)\s*$")


def _salida_no_cero(content):
    """¿La salida de execute_bash termina con «Exit Code: N», N ≠ 0? (solo para
    clasificar: el texto no se guarda)."""
    m = _EXIT.search(content) if isinstance(content, str) else None
    return bool(m) and int(m.group(1)) != 0


class _Minero(object):
    def __init__(self, tramo, abiertos=None):
        self.t = tramo
        #: turnId → ts de turn_start (sigue en el cursor si el tramo se corta)
        self.inicio = dict(abiertos) if isinstance(abiertos, dict) else {}
        self.escrituras = {}          # toolCallId → ruta (cuenta si no falla)
        self.comandos = set()         # toolCallId de execute

    def linea(self, d):
        if d.get("type") not in _TIPOS:
            self.t.desconocer(d.get("type"))
            return
        if d.get("type") == "kiro_session":
            self.t.reconocer()
            if self.t.cwd is None and isinstance(d.get("cwd"), str):
                self.t.cwd = d["cwd"]
            return
        m = d.get("message") if isinstance(d.get("message"), dict) else {}
        p = m.get("payload") if isinstance(m.get("payload"), dict) else None
        if p is None:
            # V2 ({kind, data}) u otra forma: sin golden, no se adivina
            k = m.get("kind")
            self.t.desconocer("kind:%s" % k if isinstance(k, str) else "sin_payload")
            return
        tipo = p.get("type")
        if tipo in _SIN_CONTAR:
            self.t.reconocer()
            return
        if tipo not in _CUENTAN:
            self.t.desconocer("payload:%s" % (tipo if isinstance(tipo, str) else "?"))
            return
        self.t.reconocer()
        ts = M.epoch(m.get("timestamp"))
        if tipo == "turn_start":
            if ts is not None and p.get("turnId") is not None:
                self.inicio[str(p["turnId"])] = ts
            return
        if not self.t.nuevo("m:%s" % m["id"] if m.get("id") else "", ts):
            return                    # ya contado (respaldo reescrito, importar)
        if tipo == "user":
            if p.get("syntheticUserMessageReason"):
                return
            self.t.mensajes += 1
            self.t.ts(ts)
            c = p.get("content")
            if isinstance(c, list):
                c = "\n".join(str(x.get("text") or "") for x in c if isinstance(x, dict))
            # el texto se usa SOLO para el largo por cubeta y sim_prev; se tira
            self.t.turno(ts, c if isinstance(c, str) else None, "humano")
        elif tipo == "turn_end":
            self.t.ts(ts)
            t0 = self.inicio.pop(str(p.get("turnId")), None)
            if t0 is not None and ts is not None and ts >= t0:
                self.t.activa((ts - t0) * 1000.0)
        elif tipo == "assistant":
            self.t.ts(ts)
            self.t.respuesta(ts)
        elif tipo == "tool_call":
            self.t.ts(ts)
            self.t.respuesta(ts)
            self.t.llamadas += 1
            args = p.get("args") if isinstance(p.get("args"), dict) else {}
            ruta = args.get("path") if isinstance(args.get("path"), str) else p.get("filePath")
            tid = p.get("toolCallId")
            kind = p.get("kind")
            if kind == "read" and isinstance(ruta, str):
                self.t.skills_de_texto(ruta)
            elif kind == "edit" and isinstance(ruta, str) and tid:
                self.escrituras[tid] = ruta
            elif kind == "execute" and tid:
                self.comandos.add(tid)
                if isinstance(args.get("command"), str):
                    # como claude-code/4: solo cuenta si un lector la LEE
                    for r in _rutas_leidas(args["command"]):
                        self.t.skills_de_texto(r)
        elif tipo == "tool_result":
            self.t.ts(ts)
            self.t.respuesta(ts)
            tid = p.get("toolCallId")
            ruta = self.escrituras.pop(tid, None)
            comando = tid in self.comandos
            self.comandos.discard(tid)
            if p.get("success") is False:
                if comando and _salida_no_cero(p.get("content")):
                    # un comando que terminó con ≠ 0 no es un error de la herramienta
                    self.t.comandos_no_cero += 1
                else:
                    self.t.errores += 1
            elif ruta:
                self.t.escrito(ruta)


# ── contrato ────────────────────────────────────────────────────────────────

def sesion(path):
    d = M.primera_linea(path)
    if d.get("type") == "kiro_session" and d.get("id"):
        return str(d["id"])
    m = re.match(r"kiro-(sess_[0-9a-fA-F-]+|[0-9a-fA-F-]{36})\.jsonl$", os.path.basename(path))
    return m.group(1) if m else ""


def cabecera(path):
    d = M.primera_linea(path)
    if d.get("type") == "kiro_session":
        return d.get("cwd"), M.epoch(d.get("created"))
    return None, None


def minar(path, cur, tramo, hasta_t=None, cola=False):
    mo = _Minero(tramo, cur.get("turnos_abiertos"))
    nuevo, completo = M.recorrer_reescrito(path, cur, mo.linea, tramo, hasta_t)
    nuevo["turnos_abiertos"] = mo.inicio
    return {"cursor": nuevo, "completo": completo, "costo": None}


def al_dia(path, cur):
    return M.al_dia_por_firma(path, cur)


def raices():
    """Los respaldos de Workspace: <estado>/transcripts-backup/<enc>/."""
    import paths
    return [(os.path.join(paths.state_dir(), "transcripts-backup"), 1)]


def es_fuente(nombre):
    return nombre.startswith("kiro-") and nombre.endswith(".jsonl")


def fuentes():
    """Respaldos `kiro-<sess>.jsonl` de <estado>/transcripts-backup/<enc>/."""
    import paths
    out = []
    base = os.path.join(paths.state_dir(), "transcripts-backup")
    try:
        dirs = os.listdir(base)
    except OSError:
        return out
    for d in dirs:
        full = os.path.join(base, d)
        try:
            files = os.listdir(full) if os.path.isdir(full) else ()
        except OSError:
            continue
        for f in files:
            if es_fuente(f):
                p = os.path.join(full, f)
                sid = sesion(p)
                if sid:
                    out.append((sid, p))
    return out
