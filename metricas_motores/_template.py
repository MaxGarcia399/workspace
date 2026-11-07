"""WORKSPACE · metricas_motores._template — PLANTILLA de parser para un motor nuevo.

El registro la IGNORA (el nombre empieza con «_»). Para un motor nuevo:
  1. copia este archivo a `metricas_motores/<motor>.py` (nombre de módulo con «_»
     en vez de «-»: claude_code.py mide «claude-code»);
  2. cambia MOTOR/VERSION y llena el mapa de campos de abajo con RUTAS EXACTAS
     del formato del motor (solo claves, nunca contenido), verificadas contra una
     sesión real del guion G1 (tests/e2e/metricas_viva.py --guardar-fixture);
  3. reescribe `_Minero.linea()` para ese formato;
  4. sigue el runbook: runbooks/agregar-motor.md §3b «Métricas al añadir un motor».

El contrato completo está en metricas_motores/__init__.py; el kit que lo exige,
en tests/test_metricas_conformidad.py. Este módulo ES un parser que cumple el
contrato, para un formato de EJEMPLO (no existe ningún motor que lo escriba):

    {"type": "session", "id": "…", "cwd": "…", "version": "1.2.3"}
    {"type": "user", "id": "…", "ts": "…", "text": "…"}
    {"type": "assistant", "id": "…", "ts": "…", "model": "…",
     "usage": {"input": n, "cached": n, "output": n, "reasoning": n},
     "tools": [{"id": "…", "name": "read|write|shell", "path": "…"}]}
    {"type": "tool_result", "id": "…", "ts": "…", "tool_id": "…", "ok": true}
    {"type": "turn_end", "ts": "…", "duration_ms": n, "interrupted": false}

Reglas que el kit revisa (no negociables):
  · Solo números y nombres: el texto se LEE para clasificar y se tira (K2).
  · «Sin dato» = None, nunca 0: lo que el motor no da va «no» en COBERTURA y el
    núcleo lo deja null; lo que falta en un tramo → tramo.sin_dato.add(campo) (K3).
  · Cada línea: tramo.reconocer() o tramo.desconocer(tipo) — si ninguna se
    reconoce, la fila sale «formato_desconocido» y el cursor no avanza (K3).
  · Huellas: tramo.nuevo(clave, ts) con una clave ESTABLE por evento (id del
    mensaje, de la herramienta…): retomar, reimportar o un respaldo reescrito
    jamás cuentan dos veces (K5, K6).
  · Tokens en semántica neutral: entrada SIN caché, cache_lectura,
    cache_escritura (+_1h), salida CON razonamiento, razonamiento (subconjunto).
  · utf-8-sig (las ayudas del núcleo ya lo hacen) y stdlib 3.9+ (K10, global).
"""
import os

import metricas as M

#: nombre del motor tal como lo usa Workspace (engines/, payload["engine"])
MOTOR = "plantilla"
#: sube a <motor>/2 cuando cambie QUÉ se cuenta (viaja en cada fila: corte de historia)
VERSION = "plantilla/1"
#: versiones EXACTAS verificadas, cada una con su golden en
#: tests/fixtures/metricas/<motor>/<versión>/ (manifest + historial + esperado.json)
VERIFIED_VERSIONS = ("1.2.3",)
#: CANARIOS = True solo si el motor publica casi a diario (Claude Code): una
#: versión no listada sale «por_canarios» en vez de «no».
# CANARIOS = True

#: Mapa de campos: UNA entrada por cada metricas.CAMPOS_COBERTURA (ni más ni
#: menos). («si", "") · ("parcial", "cuándo falta y por qué") · ("no", "motivo").
COBERTURA = {
    "motor_version": ("si", "session.version"),
    "modo_senales": ("no", "el formato de ejemplo no dice cómo se lanzó la sesión"),
    "duracion_activa_s": ("si", "turn_end.duration_ms"),
    "tiempo_humano_est_s": ("si", ""),
    "modelos": ("si", "assistant.model + assistant.usage"),
    "modelo_pedido": ("no", "el formato de ejemplo solo trae el modelo que respondió"),
    "esfuerzo": ("no", "no viene"),
    "permisos": ("no", "no viene"),
    "tokens_motor": ("no", "solo Claude Code expone el total del motor por modelo"),
    "costo_usd": ("no", "el formato de ejemplo no trae costo"),
    "facturacion": ("no", "no viene"),
    "cuota": ("no", "no viene"),
    "herramientas.llamadas": ("si", "assistant.tools[]"),
    "herramientas.errores": ("si", "tool_result.ok = false"),
    "herramientas.comandos_no_cero": ("no", "no separa el código de salida de un comando"),
    "respuestas_error": ("no", "no trae los errores del proveedor"),
    "interrupciones": ("si", "turn_end.interrupted"),
    "mensajes_usuario": ("si", "type user"),
    "skills": ("si", "herramienta read sobre …/skills/<nombre>/SKILL.md"),
    "escritos.archivos": ("parcial", "herramienta write; lo escrito por shell no se ve"),
    "escritos.entregables": ("parcial", "igual que escritos.archivos"),
    "subagentes": ("no", "no los separa"),
    "turnos": ("si", ""),
}
#: Cómo sigue una sesión (metricas.MECANISMOS_CONTINUACION).
CONTINUACION = {"retomar": "mismo_archivo", "continuar": "desconocido"}

_TIPOS = frozenset(("session", "user", "assistant", "tool_result", "turn_end"))


class _Minero(object):
    """Lee las líneas NUEVAS de un tramo. Una instancia por tramo."""

    def __init__(self, tramo):
        self.t = tramo
        self.escrituras = {}             # id de herramienta → ruta (cuenta si no falla)

    def linea(self, d):
        tipo = d.get("type")
        if tipo not in _TIPOS:
            self.t.desconocer(tipo)       # solo el NOMBRE del tipo, jamás contenido
            return
        self.t.reconocer()
        ts = M.epoch(d.get("ts"))
        if tipo == "session":
            if isinstance(d.get("version"), str):
                self.t.version = d["version"][:40]
            if self.t.cwd is None and isinstance(d.get("cwd"), str):
                self.t.cwd = d["cwd"]
            return
        clave = "%s:%s" % (tipo, d.get("id")) if d.get("id") else ""
        if tipo != "turn_end" and not self.t.nuevo(clave, ts):
            return                        # ya contado (retomar, respaldo reescrito, copia)
        if tipo == "user":
            self.t.mensajes += 1
            self.t.ts(ts)
            # el texto se usa SOLO para el largo por cubeta y sim_prev; se tira
            self.t.turno(ts, d.get("text") if isinstance(d.get("text"), str) else None, "humano")
        elif tipo == "assistant":
            self.t.ts(ts)
            self.t.respuesta(ts)
            u = d.get("usage") if isinstance(d.get("usage"), dict) else None
            if u is not None:
                ent, cache = M.entero(u.get("input")), M.entero(u.get("cached"))
                self.t.uso(d.get("model"), {
                    "entrada": ent, "salida": M.entero(u.get("output")),
                    "cache_lectura": cache, "cache_escritura": None,
                    "cache_escritura_1h": None, "razonamiento": M.entero(u.get("reasoning"))})
            for h in d.get("tools") or ():
                if not isinstance(h, dict):
                    continue
                self.t.llamadas += 1
                nombre, ruta = str(h.get("name") or ""), h.get("path")
                if nombre == "read":
                    self.t.skills_de_texto(ruta)
                elif nombre == "write" and h.get("id"):
                    self.escrituras[h["id"]] = ruta
        elif tipo == "tool_result":
            self.t.ts(ts)
            self.t.respuesta(ts)
            ruta = self.escrituras.pop(d.get("tool_id"), None)
            if d.get("ok") is False:
                self.t.errores += 1
            elif ruta:
                self.t.escrito(ruta)
        elif tipo == "turn_end":
            if self.t.nuevo("fin:%s" % d.get("ts"), ts):
                self.t.ts(ts)
                self.t.activa(d.get("duration_ms"))
                if d.get("interrupted") is True:
                    self.t.interrupciones += 1


# ── contrato ────────────────────────────────────────────────────────────────

def sesion(path):
    """Id de sesión del motor para ese transcript ('' si no se sabe)."""
    d = M.primera_linea(path)
    return str(d.get("id") or "") if d.get("type") == "session" else ""


def minar(path, cur, tramo, hasta_t=None, cola=False):
    """Mide lo NUEVO desde el cursor (`cur`, {} la primera vez). JSONL que solo
    crece → M.recorrer (cursor = offset de bytes). Un respaldo que Workspace
    reescribe entero → M.recorrer_reescrito + al_dia = M.al_dia_por_firma."""
    offset = int(cur.get("offset") or 0)
    nuevo, completo = {"offset": offset}, True
    if os.path.getsize(M.ruta_larga(path)) > offset:
        nuevo["offset"], completo = M.recorrer(path, offset, _Minero(tramo).linea, tramo,
                                               hasta_t, cola)
    return {"cursor": nuevo, "completo": completo, "costo": None,
            "desde": offset, "hasta": nuevo["offset"]}


def al_dia(path, cur):
    """importar: ¿nada nuevo? (para saltarlo sin leer)."""
    return int(cur.get("offset") or 0) >= os.path.getsize(M.ruta_larga(path))


def fuentes():
    """[(sid, ruta)] de los transcripts que existen en la máquina (importar).
    La plantilla no conoce ninguna ubicación real."""
    return []
