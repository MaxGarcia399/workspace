"""WORKSPACE · metricas_motores.opencode — parser de métricas de OpenCode.

Fuente: el respaldo que Workspace deja al cerrar
(`<estado>/transcripts-backup/<enc>/opencode-<ses_…>.jsonl`), hecho con el
export OFICIAL (`opencode session export <id>`; session_continuity.
capture_opencode). Se REESCRIBE entero en cada cierre → cursor por filas
(metricas.recorrer_reescrito) y huellas por id de mensaje.

Formato VERIFICADO (solo claves; OpenCode 2.1.4, 2026-10; mapa F1):
  · cabecera {type: "opencode_session", id, directory, created, updated}.
    El respaldo NO guarda `info` del export (tokens/costo de la sesión): no
    hace falta, los de cada mensaje suman lo mismo (verificado).
  · {type: "opencode_message", message: {id, type, time{created, completed}}}
    con message.type:
      user        → mensaje del usuario.
      assistant   → model{id, providerID}; tokens{input, output, reasoning,
                    cache{read, write}} (los turnos interrumpidos o fallidos
                    no traen tokens); cost (lo da el motor; 0 en modelos
                    gratis); content[] con {type: "tool", name,
                    state{status: completed|error, input{path|filePath}}}.
      idle        → outcome: succeeded | failed | interrupted (fin del turno).
      model-switched → se ignora.
  Tokens: `input` ya viene SIN la caché (cache.read/write aparte). `output`
  se toma SIN el razonamiento: OpenCode cobra `reasoning` aparte a precio de
  salida, así que salida = output + reasoning y razonamiento = reasoning
  (supuesto documentado: el binario no se pudo inspeccionar).
  Versión: no viene; el núcleo la toma de la caché de engine_versions al
  cerrar en vivo.

Totales de la sesión (sidecar `opencode-<id>.totales.json`, solo números):
`info.tokens`/`info.cost` del export INCLUYEN llamadas internas de OpenCode
que no son mensajes (el título de la sesión). Verificado con una sesión real
por OpenRouter: info = 463 entrada / 40 salida / $0.00924925 frente a 6 / 27 /
$0.009197 sumando mensajes. Con un punto de partida seguro (los totales del
tramo anterior, o cero en el primer tramo de una sesión que no trae copias),
el costo del tramo es la diferencia de info.cost y lo que info suma por
encima de los mensajes va a `opencode:internas` (llamadas: null). Sin punto
de partida (tramos medidos antes de existir el sidecar) → se usan solo los
mensajes y se avisa.
"""
import json
import os
import re

import metricas as M

MOTOR = "opencode"
VERSION = "opencode/3"
VERIFIED_VERSIONS = ("2.1.4",)
COBERTURA = {
    "motor_version": ("parcial", "el respaldo no la trae: la caché de engine_versions al "
                                 "cerrar en vivo; null en la historia importada"),
    "modo_senales": ("no", "el export no dice cómo se lanzó la sesión"),
    "duracion_activa_s": ("si", "de cada user al idle que cierra su turno"),
    "tiempo_humano_est_s": ("si", ""),
    "modelos": ("si", ""),
    "modelo_pedido": ("no", "el export solo trae el modelo que respondió"),
    "esfuerzo": ("no", "el export no lo trae"),
    "permisos": ("no", "el export no lo trae"),
    "tokens_motor": ("no", "info.tokens se usa para las llamadas internas "
                           "(opencode:internas), no como total por modelo"),
    "costo_usd": ("parcial", "diferencia de info.cost con el sidecar de totales; sin "
                             "sidecar (historia previa a F1), la suma por mensaje"),
    "facturacion": ("no", "el export no lo trae"),
    "cuota": ("no", "el export no lo trae"),
    "herramientas.llamadas": ("si", ""),
    "herramientas.errores": ("si", "state.status = error"),
    "herramientas.comandos_no_cero": ("no", "el export no separa el código de salida"),
    "respuestas_error": ("si", "assistant.error: el status HTTP o un type provider.*"),
    "interrupciones": ("si", "idle.outcome = interrupted"),
    "mensajes_usuario": ("si", ""),
    "skills": ("si", "herramienta read"),
    "escritos.archivos": ("parcial", "write/edit/patch; lo escrito por bash no se ve"),
    "escritos.entregables": ("parcial", "igual que escritos.archivos"),
    "subagentes": ("no", "el export no los separa"),
    "turnos": ("si", ""),
}
CONTINUACION = {"retomar": "respaldo_reescrito", "continuar": "desconocido"}
_TIPOS = frozenset(("opencode_session", "opencode_message"))

_ESCRITURA = ("write", "edit", "patch", "multiedit")
SUFIJO_TOTALES = ".totales.json"
INTERNAS = "opencode:internas"
_CAMPOS = ("input", "output", "reasoning", "cache_read", "cache_write")


def ruta_totales(path):
    return (path[:-len(".jsonl")] if path.endswith(".jsonl") else path) + SUFIJO_TOTALES


def _totales_de(info):
    tok = info.get("tokens") if isinstance(info.get("tokens"), dict) else {}
    cache = tok.get("cache") if isinstance(tok.get("cache"), dict) else {}
    return {"input": M.entero(tok.get("input")), "output": M.entero(tok.get("output")),
            "reasoning": M.entero(tok.get("reasoning")),
            "cache_read": M.entero(cache.get("read")), "cache_write": M.entero(cache.get("write")),
            "cost": M.numero(info.get("cost"))}


def guardar_totales(info, destino):
    """`info` del export oficial → `destino` (solo números; atómico). Lo
    llama capture_opencode al cerrar."""
    data = _totales_de(info if isinstance(info, dict) else {})
    data.update(M.procedencia(MOTOR))
    M.guardar(destino, json.dumps(data))  # atómico, lector abierto y ruta larga (Windows)
    return data


def _ms(v):
    v = M.numero(v)
    return v / 1000.0 if v else None


class _Minero(object):
    def __init__(self, tramo):
        self.t = tramo
        self.turno = None            # created del user que abrió el turno
        self.costo = None
        self.suma = dict.fromkeys(_CAMPOS, 0)   # lo que suman los mensajes
        self.asistentes = 0          # respuestas del modelo en el tramo…
        self.con_tokens = 0          # …y cuántas traían `tokens`

    def linea(self, d):
        if d.get("type") not in _TIPOS:
            self.t.desconocer(d.get("type"))
            return
        self.t.reconocer()
        if d.get("type") == "opencode_session":
            if self.t.cwd is None and isinstance(d.get("directory"), str):
                self.t.cwd = d["directory"]
            return
        m = d.get("message") if d.get("type") == "opencode_message" else None
        if not isinstance(m, dict):
            return
        tipo = m.get("type")
        tiempos = m.get("time") if isinstance(m.get("time"), dict) else {}
        ts = _ms(tiempos.get("created"))
        if not self.t.nuevo("m:%s" % m["id"] if m.get("id") else "", ts):
            return
        if tipo == "user":
            self.t.mensajes += 1
            self.t.ts(ts)
            self.turno = ts
            self.t.turno(ts, m.get("text") if isinstance(m.get("text"), str) else None, "humano")
        elif tipo == "assistant":
            self._asistente(m, ts, _ms(tiempos.get("completed")))
        elif tipo == "idle":
            self.t.ts(ts)
            if m.get("outcome") == "interrupted":
                self.t.interrupciones += 1
            if self.turno is not None and ts is not None and ts >= self.turno:
                self.t.activa((ts - self.turno) * 1000.0)
            self.turno = None

    def _asistente(self, m, ts, fin):
        self.t.ts(ts)
        self.t.ts(fin)
        self.t.respuesta(ts)
        self.t.respuesta(fin)
        self.asistentes += 1
        err = m.get("error") if isinstance(m.get("error"), dict) else None
        if err is not None:
            # error del PROVEEDOR (un 400, un bloqueo): por su status HTTP o un
            # type provider.*; «aborted» es una interrupción, no del proveedor
            status, tipo = M.entero(err.get("status")), str(err.get("type") or "")
            if status is not None or tipo.startswith("provider"):
                clase = M.clase_error(status) or M.clase_error(tipo)
                if clase:
                    self.t.respuesta_error(clase)
                else:
                    self.t.avisos.add("error_del_proveedor_sin_clase")
        mod = m.get("model") if isinstance(m.get("model"), dict) else {}
        nombre = "/".join(x for x in (mod.get("providerID"), mod.get("id"))
                          if isinstance(x, str) and x) or None
        tok = m.get("tokens")
        if isinstance(tok, dict):
            self.con_tokens += 1
            cache = tok.get("cache") if isinstance(tok.get("cache"), dict) else {}
            salida, razon = M.entero(tok.get("output")), M.entero(tok.get("reasoning"))
            for k, v in (("input", tok.get("input")), ("output", salida), ("reasoning", razon),
                         ("cache_read", cache.get("read")), ("cache_write", cache.get("write"))):
                self.suma[k] += M.entero(v) or 0
            self.t.uso(nombre, {
                "entrada": M.entero(tok.get("input")),
                "salida": None if salida is None and razon is None else (salida or 0) + (razon or 0),
                "cache_lectura": M.entero(cache.get("read")),
                "cache_escritura": M.entero(cache.get("write")),
                "cache_escritura_1h": None,
                "razonamiento": razon,
            })
        c = M.numero(m.get("cost"))
        if c is not None:
            self.costo = (self.costo or 0.0) + c
        for p in m.get("content") or ():
            if not (isinstance(p, dict) and p.get("type") == "tool"):
                continue
            self.t.llamadas += 1
            st = p.get("state") if isinstance(p.get("state"), dict) else {}
            inp = st.get("input") if isinstance(st.get("input"), dict) else {}
            ruta = inp.get("path") or inp.get("filePath")
            if st.get("status") == "error":
                self.t.errores += 1
            nombre_h = str(p.get("name") or "").lower()
            if nombre_h == "read":
                self.t.skills_de_texto(ruta)
            elif nombre_h in _ESCRITURA and st.get("status") == "completed":
                self.t.escrito(ruta)


# ── contrato ────────────────────────────────────────────────────────────────

def sesion(path):
    d = M.primera_linea(path)
    if d.get("type") == "opencode_session" and d.get("id"):
        return str(d["id"])
    m = re.match(r"opencode-(.+)\.jsonl$", os.path.basename(path))
    return m.group(1) if m else ""


def cabecera(path):
    d = M.primera_linea(path)
    if d.get("type") == "opencode_session":
        return d.get("directory"), _ms(d.get("created"))
    return None, None


def _leer_totales(path):
    try:
        with open(M.ruta_larga(ruta_totales(path)), encoding="utf-8-sig") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _con_totales(cur, mo, tramo, tot):
    """(costo, tokens internos) con los totales de la sesión, si hay punto de
    partida seguro; (None, None) si no."""
    if not any(tot.get(k) for k in _CAMPOS + ("cost",)) and any(mo.suma.values()):
        tramo.avisos.add("totales_vacios")      # el sidecar llegó sin números
    if isinstance(cur.get("totales"), dict):
        base = cur["totales"]
    elif not int(cur.get("n") or 0) and not tramo.copias:
        base = {}                               # primer tramo de una sesión propia
    else:
        tramo.avisos.add("totales_sin_punto_de_partida")
        return None, None
    delta = {}
    for k in _CAMPOS + ("cost",):
        v, b = tot.get(k), base.get(k)
        if v is None:
            continue
        if b is not None and v < b:
            tramo.avisos.add("totales_sin_punto_de_partida")
            return None, None
        delta[k] = v - (b or 0)
    extra = {k: max(0, (delta.get(k) or 0) - mo.suma[k]) for k in _CAMPOS}
    return delta.get("cost"), extra


def minar(path, cur, tramo, hasta_t=None, cola=False):
    mo = _Minero(tramo)
    # un turno que quedó abierto en el tramo anterior (el user ya se midió,
    # su idle llega ahora): su tiempo activo se cuenta aquí, una vez
    mo.turno = M.numero(cur.get("turno_abierto"))
    nuevo, completo = M.recorrer_reescrito(path, cur, mo.linea, tramo, hasta_t)
    nuevo["turno_abierto"] = mo.turno       # None al cerrarse (el cursor se actualiza)
    costo = None
    if mo.costo is not None:
        costo = (round(mo.costo, 6), "opencode:message.cost", None)
    # a medias (presupuesto, o cierre encolado que mide hasta su fin): los
    # totales de la sesión, después
    tot = _leer_totales(path) if completo and not tramo.cortado_por_tope else None
    if not os.path.isfile(M.ruta_larga(ruta_totales(path))):
        tramo.degradada = True       # respaldo sin sidecar (historia previa a F1)
    if tot and tramo.excluidas:
        # actividad con las métricas apagadas: el total de la sesión no se
        # puede partir por hora → solo mensajes (filtrados), y la base avanza
        tramo.avisos.add("periodo_apagado")
        nuevo["totales"] = {k: tot.get(k) for k in _CAMPOS + ("cost",)}
        nuevo["firma_totales"] = M.firma_archivo(ruta_totales(path))
    elif tot:
        usd, extra = _con_totales(cur, mo, tramo, tot)
        if mo.asistentes and not mo.con_tokens:
            # respuestas sin `tokens` (formato cambiado): lo de los totales NO
            # es «interno»; sin tokens por mensaje, los modelos van null (K3d)
            extra = None
            tramo.sin_dato.add("modelos")
            tramo.avisos.add("sin_tokens")
        if usd is not None:
            costo = (round(usd, 6), "opencode:info.cost",
                     {"mensajes_usd": round(mo.costo or 0.0, 6)})
            if usd > 0:
                tramo.nuevos += 1
        if extra and any(extra.values()):
            # lo que la sesión gastó fuera de los mensajes (título, etc.)
            tramo.modelos[INTERNAS] = {
                "llamadas": None, "entrada": extra["input"],
                "salida": extra["output"] + extra["reasoning"],
                "cache_lectura": extra["cache_read"], "cache_escritura": extra["cache_write"],
                "cache_escritura_1h": None, "razonamiento": extra["reasoning"]}
            tramo.nuevos += 1
        nuevo["totales"] = {k: tot.get(k) for k in _CAMPOS + ("cost",)}
        nuevo["firma_totales"] = M.firma_archivo(ruta_totales(path))
    if costo is not None:
        hubo_tokens = any(m.get("salida") or m.get("entrada") for m in tramo.modelos.values())
        tramo.costo_tipo = "gratis" if costo[0] == 0 and hubo_tokens else "estimado"
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
    return nombre.startswith("opencode-") and nombre.endswith(".jsonl")


def fuentes():
    """Respaldos `opencode-<ses>.jsonl` de <estado>/transcripts-backup/<enc>/."""
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
            if f.startswith("opencode-") and f.endswith(".jsonl"):
                p = os.path.join(full, f)
                sid = sesion(p)
                if sid:
                    out.append((sid, p))
    return out
