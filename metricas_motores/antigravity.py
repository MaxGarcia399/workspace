"""WORKSPACE · metricas_motores.antigravity — parser de métricas de Antigravity.

Fuente: el respaldo `<estado>/transcripts-backup/<enc>/antigravity-<cid>.jsonl`,
copia EXACTA del log documentado `~/.gemini/antigravity-cli/brain/<cid>/
.system_generated/logs/transcript.jsonl` (session_continuity.
capture_antigravity). Se recopia entero en cada cierre → cursor por filas
(metricas.recorrer_reescrito) y huellas por (sesión, step_index).

Formato VERIFICADO (solo claves; agy 1.4.7, 2026-10; mapa F1): una fila por
paso {step_index, source, type, status, created_at (resolución 1 s)}.
  · USER_INPUT con source USER_EXPLICIT → mensaje del usuario.
  · PLANNER_RESPONSE → input_tokens (SIN la caché: verificado, la caché leída
    supera a la entrada), output_tokens, cache_read_tokens; tool_calls[]
    {name, args{Path}} — **args.Path es un string JSON con comillas**.
  · GENERIC con status ERROR → error de herramienta.
NO trae: modelo, versión, costo (suscripción), cwd ni marca de interrupción.
  · Modelo y cuota: solo los guarda la statusline de Workspace
    (<estado>/antigravity-usage.json: el ÚLTIMO visto, sin atarlo a una
    sesión). Se usan solo si se observaron durante este tramo (ventana de
    tiempo) y la fila lo avisa (`modelo_de_la_statusline`); si no, el modelo
    queda «desconocido» y la cuota null.
  · Versión: la caché de engine_versions al cerrar en vivo (núcleo).
  · Cerebro al importar: la carpeta <enc> del respaldo (núcleo).
"""
import json
import os
import re

import metricas as M

MOTOR = "antigravity"
VERSION = "antigravity/3"
VERIFIED_VERSIONS = ("1.4.7",)
COBERTURA = {
    "motor_version": ("parcial", "el log no la trae: la caché de engine_versions al "
                                 "cerrar en vivo; null en la historia importada"),
    "modo_senales": ("no", "el log no dice cómo se lanzó la sesión"),
    "duracion_activa_s": ("parcial", "aproximada: del pedido al último paso del turno "
                                     "(resolución de 1 s)"),
    "tiempo_humano_est_s": ("si", ""),
    "modelos": ("parcial", "tokens por paso, pero el modelo solo si la statusline lo vio "
                           "durante el tramo; si no, «desconocido»"),
    "modelo_pedido": ("no", "el log no lo trae"),
    "esfuerzo": ("no", "el log no lo trae"),
    "permisos": ("no", "el log no lo trae"),
    "tokens_motor": ("no", "solo Claude Code expone el total del motor por modelo"),
    "costo_usd": ("no", "el log no trae costo (suscripción)"),
    "facturacion": ("no", "el log no lo trae"),
    "cuota": ("parcial", "de la statusline de Workspace, si se observó durante el tramo"),
    "herramientas.llamadas": ("si", ""),
    "herramientas.errores": ("si", "pasos con status ERROR"),
    "herramientas.comandos_no_cero": ("no", "no se separa el código de salida"),
    "respuestas_error": ("no", "el log no trae los errores del proveedor"),
    "interrupciones": ("no", "el log no las marca (el paso queda DONE)"),
    "mensajes_usuario": ("si", "USER_INPUT con source USER_EXPLICIT"),
    "skills": ("si", "read_file/view_file"),
    "escritos.archivos": ("parcial", "write/edit/replace; lo escrito por terminal no se ve"),
    "escritos.entregables": ("parcial", "igual que escritos.archivos"),
    "subagentes": ("no", "el log no los separa"),
    "turnos": ("si", ""),
}
CONTINUACION = {"retomar": "respaldo_reescrito", "continuar": "desconocido"}

_ESCRITURA = ("write_file", "edit_file", "replace_file_content", "write_to_file")
_LECTURA = ("read_file", "view_file")
#: margen para dar por buena la observación de la statusline (s)
_VENTANA_ANTES, _VENTANA_DESPUES = 120.0, 900.0


def _ruta_arg(v):
    """args.Path viene como string JSON ('"\\/x\\/y"'); a veces ya plano."""
    if isinstance(v, str):
        try:
            x = json.loads(v)
            return x if isinstance(x, str) else v
        except ValueError:
            return v
    return None


class _Minero(object):
    def __init__(self, tramo):
        self.t = tramo
        self.turno = None            # created del USER_INPUT que abrió el turno
        self.ultimo = None           # último paso del turno

    def _cerrar_turno(self):
        if self.turno is not None and self.ultimo is not None and self.ultimo >= self.turno:
            self.t.activa((self.ultimo - self.turno) * 1000.0)
        self.turno = self.ultimo = None

    def linea(self, d):
        idx = d.get("step_index")
        # cada fila es un PASO: {step_index, type}; los tipos de paso son
        # muchos y cambian (se cuentan todos), lo que no es un paso no se entiende
        if not (isinstance(idx, int) and isinstance(d.get("type"), str) and d["type"]):
            self.t.desconocer(d.get("type") if isinstance(d.get("type"), str) else None)
            return
        self.t.reconocer()
        ts = M.epoch(d.get("created_at"))
        if not self.t.nuevo("s:%s:%s" % (self.t.sid, idx) if idx is not None else "", ts):
            return
        tipo = d.get("type")
        if tipo == "USER_INPUT":
            if d.get("source") == "USER_EXPLICIT":
                self._cerrar_turno()
                self.t.mensajes += 1
                self.t.ts(ts)
                self.turno = self.ultimo = ts
                self.t.turno(ts, d.get("content") if isinstance(d.get("content"), str) else None,
                             "humano")
            return
        self.t.ts(ts)
        self.t.respuesta(ts)
        if self.turno is not None and ts is not None:
            self.ultimo = ts
        if tipo == "PLANNER_RESPONSE":
            if any(d.get(k) is not None for k in ("input_tokens", "output_tokens")):
                # el uso va YA, en su turno; el modelo (de la statusline) se pone
                # al final, renombrando «desconocido» (K4: antes, todo en fin())
                self.t.uso(None, {
                    "entrada": M.entero(d.get("input_tokens")),
                    "salida": M.entero(d.get("output_tokens")),
                    "cache_lectura": M.entero(d.get("cache_read_tokens")),
                    "cache_escritura": None, "cache_escritura_1h": None,
                    "razonamiento": None})
            for tc in d.get("tool_calls") or ():
                if not isinstance(tc, dict):
                    continue
                self.t.llamadas += 1
                args = tc.get("args") if isinstance(tc.get("args"), dict) else {}
                nombre = str(tc.get("name") or "")
                ruta = _ruta_arg(args.get("Path") or args.get("AbsolutePath")
                                 or args.get("TargetFile"))
                if nombre in _LECTURA:
                    self.t.skills_de_texto(ruta)
                elif nombre in _ESCRITURA:
                    self.t.escrito(ruta)
        elif d.get("status") == "ERROR":
            self.t.errores += 1

    def fin(self):
        self._cerrar_turno()
        modelo = None
        snap = _statusline()
        if snap and self.t.t0 is not None and self.t.t1 is not None:
            at = M.numero(snap.get("at"))
            if at is not None and self.t.t0 - _VENTANA_ANTES <= at <= self.t.t1 + _VENTANA_DESPUES:
                modelo = snap.get("model") or None
                usados = [M.numero(b.get("used_percent")) for b in snap.get("buckets") or ()
                          if isinstance(b, dict)]
                usados = [u for u in usados if u is not None]
                if usados:
                    self.t.ver_cuota({"primaria": {"usado_pct": round(max(usados), 2),
                                                   "ventana_min": None}})
                if modelo:
                    self.t.avisos.add("modelo_de_la_statusline")
        nombre = M.nombre_modelo(modelo) if modelo else None
        if nombre and "desconocido" in self.t.modelos:
            m = self.t.modelos.pop("desconocido")
            acc = self.t.modelos.setdefault(nombre, dict({k: None for k in M.CAMPOS_TOKENS},
                                                         llamadas=0))
            acc["llamadas"] += m.get("llamadas") or 0
            for k in M.CAMPOS_TOKENS:
                if m.get(k) is not None:
                    acc[k] = (acc[k] or 0) + m[k]
            for tu in self.t.turnos:
                if tu.get("modelo") == "desconocido":
                    tu["modelo"] = nombre


def _statusline():
    try:
        import antigravity_usage
        return antigravity_usage.read_snapshot()
    except Exception:
        return None


# ── contrato ────────────────────────────────────────────────────────────────

def sesion(path):
    m = re.match(r"antigravity-(.+)\.jsonl$", os.path.basename(path))
    return m.group(1) if m else ""


def cabecera(path):
    """El log no trae cwd: (None, primer created_at). El núcleo ubica el
    cerebro por la carpeta del respaldo."""
    return None, M.epoch(M.primera_linea(path).get("created_at"))


def minar(path, cur, tramo, hasta_t=None, cola=False):
    mo = _Minero(tramo)
    # turno abierto al final del tramo anterior: sigue desde su último paso
    # medido (así N cortes suman el mismo tiempo activo que una pasada)
    ref = M.numero(cur.get("turno_ref"))
    if ref is not None:
        mo.turno = mo.ultimo = ref
    nuevo, completo = M.recorrer_reescrito(path, cur, mo.linea, tramo, hasta_t)
    nuevo["turno_ref"] = mo.ultimo if mo.turno is not None else None
    tramo.cerrar_turno()     # el uso sin modelo se asigna en fin(), fuera de los turnos
    mo.fin()
    return {"cursor": nuevo, "completo": completo, "costo": None}


def al_dia(path, cur):
    return M.al_dia_por_firma(path, cur)


def raices():
    """Los respaldos de Workspace: <estado>/transcripts-backup/<enc>/."""
    import paths
    return [(os.path.join(paths.state_dir(), "transcripts-backup"), 1)]


def es_fuente(nombre):
    return nombre.startswith("antigravity-") and nombre.endswith(".jsonl")


def fuentes():
    """Respaldos `antigravity-<cid>.jsonl` (no el snapshot .db)."""
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
            if f.startswith("antigravity-") and f.endswith(".jsonl"):
                p = os.path.join(full, f)
                sid = sesion(p)
                if sid:
                    out.append((sid, p))
    return out
