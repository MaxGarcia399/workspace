"""WORKSPACE · metricas_motores.hermes — parser de métricas de Hermes Agent.

Fuentes (las dos las deja Workspace al cerrar, sin lanzar nada más):
  1. el respaldo `<estado>/transcripts-backup/<enc>/hermes-<id>.jsonl`
     (session_continuity.capture_hermes, con el export OFICIAL `hermes
     sessions export`): cabecera {type: "hermes_session", id, chain, cwd,
     started_at, ended_at} + filas {type: "hermes_message", session, message}.
     Trae los mensajes, pero PIERDE todos los contadores de la sesión.
  2. un SIDECAR solo de números y nombres, `hermes-<id>.totales.json`, que
     capture_hermes escribe (guardar_totales) con los contadores de cada
     sesión de la cadena, sacados del MISMO export. Aditivo: quien lee el
     respaldo no cambia.
El respaldo se REESCRIBE entero en cada cierre → cursor por filas
(metricas.recorrer_reescrito) y huellas por (sesión, id de mensaje).

Formato VERIFICADO (solo claves; Hermes 0.22.5, 2026-10; mapa F1):
  · Por SESIÓN (export): model; input_tokens (SIN la caché, estilo
    Anthropic: 6 de entrada con 31834 de caché leída), output_tokens (se toma
    con el razonamiento incluido, como lo cuenta el proveedor),
    cache_read_tokens, cache_write_tokens, reasoning_tokens; api_call_count;
    estimated_cost_usd + actual_cost_usd (null) + cost_status "estimated";
    tool_names (string JSON) con "version". No hay tokens por mensaje.
  · Por MENSAJE: role user | assistant | tool; assistant.tool_calls[]
    {id, function{name, arguments (string JSON con path)}};
    assistant.display_metadata.interrupted; tool.content = string JSON del
    resultado: error si trae `error` (no vacío) o `not_found: true` — la clave
    not_found existe también en lecturas que salieron bien (false).
  · Duración de turno: NO existe (null). La pared sale de los timestamps.
Los contadores de cada sesión son ACUMULADOS: el tramo toma la diferencia
contra los últimos medidos de ESA sesión, guardados a nivel motor (no por
archivo: el respaldo de la sesión que continúa trae la cadena entera) y
MONÓTONOS: un respaldo más viejo medido después no los hace retroceder (ese
tramo mide 0 de esa sesión y queda en el log). Una
sesión que aparece por primera vez parte de cero (cada sesión de la cadena
—compresión— lleva los suyos; supuesto documentado).
"""
import json
import os
import re

import metricas as M

MOTOR = "hermes"
VERSION = "hermes/3"
VERIFIED_VERSIONS = ("0.22.5",)
COBERTURA = {
    "motor_version": ("parcial", "solo del sidecar de totales (tool_names.version)"),
    "modo_senales": ("no", "el export no dice cómo se lanzó la sesión"),
    "duracion_activa_s": ("no", "Hermes no registra la duración de cada turno"),
    "tiempo_humano_est_s": ("si", ""),
    "modelos": ("parcial", "solo totales por sesión del sidecar (sin tokens por "
                           "mensaje); sin sidecar, null"),
    "modelo_pedido": ("no", "el export solo trae el modelo de la sesión"),
    "esfuerzo": ("no", "el export no lo trae"),
    "permisos": ("no", "el export no lo trae"),
    "tokens_motor": ("no", "solo Claude Code expone el total del motor por modelo"),
    "costo_usd": ("parcial", "actual_cost_usd si existe; si no, estimated_cost_usd "
                             "(estimado); solo con el sidecar"),
    "facturacion": ("no", "el export no lo trae"),
    "cuota": ("no", "el export no lo trae"),
    "herramientas.llamadas": ("si", ""),
    "herramientas.errores": ("parcial", "heurística: resultado con `error` no vacío o "
                                        "not_found: true"),
    "herramientas.comandos_no_cero": ("no", "no se separa el código de salida"),
    "respuestas_error": ("no", "el export no trae los errores del proveedor"),
    "interrupciones": ("si", "display_metadata.interrupted"),
    "mensajes_usuario": ("si", ""),
    "skills": ("si", "read_file"),
    "escritos.archivos": ("parcial", "write_file/patch/edit_file; lo escrito por terminal "
                                     "no se ve"),
    "escritos.entregables": ("parcial", "igual que escritos.archivos"),
    "subagentes": ("no", "el export no los separa"),
    "turnos": ("parcial", "sin tokens por turno (Hermes solo da totales por sesión)"),
}
CONTINUACION = {"retomar": "respaldo_reescrito", "continuar": "cadena"}
_TIPOS = frozenset(("hermes_session", "hermes_message"))

SUFIJO_TOTALES = ".totales.json"
_ESCRITURA = ("write_file", "patch", "edit_file", "replace", "write")
_LECTURA = ("read_file",)
_CONTADORES = ("input_tokens", "output_tokens", "cache_read_tokens",
               "cache_write_tokens", "reasoning_tokens", "api_call_count",
               "estimated_cost_usd", "actual_cost_usd")


def ruta_totales(path):
    return (path[:-len(".jsonl")] if path.endswith(".jsonl") else path) + SUFIJO_TOTALES


def _version(tool_names):
    try:
        d = json.loads(tool_names) if isinstance(tool_names, str) else tool_names
        v = d.get("version") if isinstance(d, dict) else None
        return v[:40] if isinstance(v, str) else None
    except ValueError:
        return None


def _registro(d):
    """Un registro de sesión del export → solo números y nombres."""
    out = {"id": str(d.get("id") or ""), "model": M.nombre_modelo(d.get("model")) or None,
           "cost_status": d.get("cost_status") if isinstance(d.get("cost_status"), str) else None,
           "version": _version(d.get("tool_names"))}
    for k in _CONTADORES:
        out[k] = M.numero(d.get(k)) if k.endswith("_usd") else M.entero(d.get(k))
    return out


def guardar_totales(cadena, destino):
    """Los registros de la cadena exportada → `destino` (solo números y
    nombres; atómico). Lo llama capture_hermes al cerrar."""
    filas = [_registro(d) for d in cadena if isinstance(d, dict) and d.get("id")]
    # atómico, aguanta un lector abierto y la ruta larga de Windows (el id
    # local-<64 hex> + «.totales.json» + el temporal pasaban de 260)
    M.guardar(destino, json.dumps(dict(M.procedencia(MOTOR), sesiones=filas),
                                  ensure_ascii=False))
    return filas


def _json(s):
    if isinstance(s, dict):
        return s
    try:
        d = json.loads(s) if isinstance(s, str) and s.lstrip().startswith("{") else None
        return d if isinstance(d, dict) else None
    except ValueError:
        return None


class _Minero(object):
    def __init__(self, tramo):
        self.t = tramo
        self.escrituras = {}         # tool_call_id → ruta
        self.fallidas = set()

    def linea(self, d):
        if d.get("type") not in _TIPOS:
            self.t.desconocer(d.get("type"))
            return
        self.t.reconocer()
        if d.get("type") == "hermes_session":
            if self.t.cwd is None and isinstance(d.get("cwd"), str):
                self.t.cwd = d["cwd"]
            return
        m = d.get("message") if d.get("type") == "hermes_message" else None
        if not isinstance(m, dict):
            return
        ses = d.get("session") or m.get("session_id") or self.t.sid
        ts = M.epoch(m.get("timestamp"))
        if not self.t.nuevo("m:%s:%s" % (ses, m["id"]) if m.get("id") is not None else "", ts):
            return
        rol = m.get("role")
        self.t.ts(ts)
        if rol == "user":
            self.t.mensajes += 1
            self.t.turno(ts, m.get("content") if isinstance(m.get("content"), str) else None,
                         "humano")
            return
        self.t.respuesta(ts)
        if rol == "assistant":
            dm = m.get("display_metadata")
            if isinstance(dm, dict) and dm.get("interrupted") is True:
                self.t.interrupciones += 1
            for tc in m.get("tool_calls") or ():
                if not isinstance(tc, dict):
                    continue
                self.t.llamadas += 1
                fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
                nombre = str(fn.get("name") or "")
                ruta = (_json(fn.get("arguments")) or {}).get("path")
                if nombre in _LECTURA:
                    self.t.skills_de_texto(ruta)
                elif nombre in _ESCRITURA and tc.get("id"):
                    self.escrituras[tc["id"]] = ruta
        elif rol == "tool":
            r = _json(m.get("content")) or {}
            if r.get("error") or r.get("not_found") is True:
                self.t.errores += 1
                self.fallidas.add(m.get("tool_call_id"))

    def fin(self):
        for tid, ruta in self.escrituras.items():
            if tid not in self.fallidas:
                self.t.escrito(ruta)


def _con_totales(path, cur, tramo):
    """Tokens, llamadas y costo del tramo: diferencia de los contadores de
    cada sesión de Hermes contra los últimos ya medidos DE ESA SESIÓN. Se
    guardan a nivel motor (estado compartido), no por archivo: el sidecar de
    la sesión nueva trae los contadores de TODA la cadena [A, B] y el de A ya
    se midió desde el respaldo de A (revisión 2026-10-26: se contaba doble).
    → (costo, fuente)."""
    try:
        with open(M.ruta_larga(ruta_totales(path)), encoding="utf-8-sig") as fh:
            sesiones = (json.load(fh) or {}).get("sesiones") or []
    except (OSError, ValueError, AttributeError):
        # sin el sidecar (historia previa a F1, o la captura falló): ni
        # tokens ni costo — null, nunca 0
        tramo.avisos.add("sin_totales_del_export")
        tramo.degradada = True
        tramo.sin_dato.update(("modelos", "costo_usd"))
        return None, None
    if tramo.mensajes and not any(isinstance(x, dict) and any(x.get(k) for k in _CONTADORES)
                                  for x in sesiones):
        tramo.avisos.add("totales_vacios")      # el sidecar llegó sin números
    costo, fuente = None, None
    for s in sesiones:
        if not isinstance(s, dict) or not s.get("id"):
            continue
        if isinstance(s.get("version"), str):
            tramo.version = s["version"]
        p = tramo.leer("totales", s["id"]) or {}
        if any(s.get(k) is not None and p.get(k) is not None and s[k] < p[k]
               for k in _CONTADORES):
            # un respaldo más VIEJO de esa sesión (medido después de uno más
            # nuevo): los totales guardados son monótonos — no retroceden, y
            # este tramo mide 0 de esa sesión (revisión 2026-10-26)
            tramo.avisos.add("totales_retroceden")
            M._log("totales_retroceden", motor=MOTOR, sesion=s["id"])
            continue
        delta = {k: s[k] - (p.get(k) or 0) for k in _CONTADORES if s.get(k) is not None}
        guardado = dict(p)
        guardado.update({k: s.get(k) for k in _CONTADORES if s.get(k) is not None})
        tramo.anotar("totales", s["id"], guardado)
        if not delta or not any(delta.values()):
            continue
        if tramo.excluidas:
            # hubo actividad con las métricas apagadas: el acumulado no se
            # puede partir por hora → sin tokens ni costo en este tramo
            tramo.avisos.add("periodo_apagado")
            continue
        llamadas = delta.get("api_call_count") or 0
        toks = {"entrada": delta.get("input_tokens"), "salida": delta.get("output_tokens"),
                "cache_lectura": delta.get("cache_read_tokens"),
                "cache_escritura": delta.get("cache_write_tokens"), "cache_escritura_1h": None,
                "razonamiento": delta.get("reasoning_tokens")}
        if llamadas or any(toks.values()):
            m = tramo.modelos.setdefault(s.get("model") or "desconocido",
                                         dict({k: None for k in M.CAMPOS_TOKENS}, llamadas=0))
            m["llamadas"] += llamadas
            for k, v in toks.items():
                if v is not None:
                    m[k] = (m[k] or 0) + v
            tramo.nuevos += 1
        # costo: el real si Hermes lo tiene; si no, el ESTIMADO (y se dice)
        if delta.get("actual_cost_usd") is not None:
            costo, fuente = (costo or 0.0) + delta["actual_cost_usd"], "hermes:actual_cost_usd"
        elif delta.get("estimated_cost_usd") is not None:
            costo = (costo or 0.0) + delta["estimated_cost_usd"]
            fuente = fuente or "hermes:estimated_cost_usd (estimado)"
    return costo, fuente


# ── contrato ────────────────────────────────────────────────────────────────

def sesion(path):
    d = M.primera_linea(path)
    if d.get("type") == "hermes_session" and d.get("id"):
        return str(d["id"])
    m = re.match(r"hermes-(.+)\.jsonl$", os.path.basename(path))
    return m.group(1) if m else ""


def cabecera(path):
    d = M.primera_linea(path)
    if d.get("type") == "hermes_session":
        return d.get("cwd"), M.epoch(d.get("started_at"))
    return None, None


def minar(path, cur, tramo, hasta_t=None, cola=False):
    mo = _Minero(tramo)
    nuevo, completo = M.recorrer_reescrito(path, cur, mo.linea, tramo, hasta_t)
    mo.fin()
    tramo.cerrar_turno()     # los totales de la sesión no son de ningún turno
    tramo.sin_dato.add("turnos.tokens")   # Hermes no da tokens por mensaje: null, no 0
    usd, fuente = None, None
    side = ruta_totales(path)
    if completo and not tramo.cortado_por_tope:   # a medias: los totales, después
        usd, fuente = _con_totales(path, cur, tramo)
        if os.path.isfile(M.ruta_larga(side)):
            nuevo["firma_totales"] = M.firma_archivo(side)
    costo = (round(usd, 6), fuente, None) if usd is not None else None
    return {"cursor": nuevo, "completo": completo, "costo": costo}


def al_dia(path, cur):
    side = ruta_totales(path)
    return (M.al_dia_por_firma(path, cur)
            and (not os.path.isfile(M.ruta_larga(side))
                 or cur.get("firma_totales") == M.firma_archivo(side)))


def raices():
    """Los respaldos de Workspace: <estado>/transcripts-backup/<enc>/."""
    import paths
    return [(os.path.join(paths.state_dir(), "transcripts-backup"), 1)]


def es_fuente(nombre):
    return nombre.startswith("hermes-") and nombre.endswith(".jsonl")


def fuentes():
    """Respaldos `hermes-<id>.jsonl` de <estado>/transcripts-backup/<enc>/."""
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
            if f.startswith("hermes-") and f.endswith(".jsonl"):
                p = os.path.join(full, f)
                sid = sesion(p)
                if sid:
                    out.append((sid, p))
    return out
