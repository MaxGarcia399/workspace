"""WORKSPACE · metricas_motores.cursor — parser de métricas de Cursor CLI (`cursor-agent`).

Fuente: el respaldo que Workspace deja al cerrar
(`<estado>/transcripts-backup/<enc>/cursor-<uuid>.jsonl`; session_continuity.
capture_cursor), copia ENVUELTA del transcript que escribe el propio CLI en
`~/.cursor/projects/<ruta>/agent-transcripts/<uuid>/<uuid>.jsonl`. Se
REESCRIBE entero en cada cierre → cursor por filas (metricas.recorrer_reescrito)
y huellas por línea (`huella` = chat + hash del contenido + cuántas iguales
antes; las líneas del CLI no traen id ni hora).

Formato VERIFICADO con una sesión real del guion G1 (Cursor CLI 2026.11.05,
macOS, cuenta de Cursor, grok-4.7-low, 2026-11-06; golden en
tests/fixtures/metricas/cursor/2026.11.5/: engine_versions lee «2026.11.05» como
2026.11.5, que es lo que dice la fila). Solo claves:
  · cabecera {type: "cursor_session", id, cwd, source} (la arma Workspace).
  · {type: "cursor_message", huella, message: …} con message:
      {role: "user", message: {content: [{type: "text", text}]}}   (el CLI
          antepone <timestamp>…</timestamp> y envuelve el pedido en <user_query>)
      {role: "assistant", message: {content: [{type: "text", text},
                                              {type: "tool_use", name, input}]}}
          name visto: Read {path}, Write {path, contents}, Shell {command,
          description}.
      {type: "turn_ended", status: "success"}
  El CLI REESCRIBE su transcript: la línea `turn_ended` del turno anterior
  desaparece y queda una sola al final (el respaldo del segundo cierre no es
  prefijo del primero; las huellas evitan contar dos veces). No trae horas,
  modelo, tokens, costo ni el resultado de cada herramienta: todo eso queda
  null («no» en COBERTURA), nunca 0.
"""
import os
import re

import metricas as M
from metricas_motores.claude_code import _rutas_leidas  # misma regla de lectores

MOTOR = "cursor"
VERSION = "cursor/2"
#: Versiones EXACTAS verificadas con su golden (tests/fixtures/metricas/cursor/<versión>/),
#: tal como las lee engine_versions (la fila lleva esa misma forma).
VERIFIED_VERSIONS = ("2026.11.5",)
_SIN = "el transcript del CLI no lo trae (2026.11.05)"
COBERTURA = {
    "motor_version": ("parcial", "el respaldo no la trae: la caché de engine_versions al "
                                 "cerrar en vivo; null en la historia importada"),
    "modo_senales": ("no", "el transcript no dice cómo se lanzó la sesión (2026.11.05)"),
    "duracion_activa_s": ("no", "el transcript del CLI no trae horas (2026.11.05)"),
    "tiempo_humano_est_s": ("no", "sin horas por mensaje (2026.11.05)"),
    "modelos": ("no", "el transcript no trae modelo ni tokens (2026.11.05)"),
    "modelo_pedido": ("no", _SIN),
    "esfuerzo": ("no", _SIN),
    "permisos": ("no", _SIN),
    "tokens_motor": ("no", _SIN),
    "costo_usd": ("no", _SIN),
    "facturacion": ("no", _SIN),
    "cuota": ("no", _SIN),
    "herramientas.llamadas": ("si", "partes tool_use de la respuesta"),
    "herramientas.errores": ("no", "el transcript no trae el resultado de cada herramienta "
                                   "(2026.11.05)"),
    "herramientas.comandos_no_cero": ("no", "no trae el código de salida de Shell (2026.11.05)"),
    "respuestas_error": ("no", "turn_ended no dice si un error fue del proveedor (2026.11.05)"),
    "interrupciones": ("no", "turn_ended.status = success visto; «aborted» sin verificar (la G1 "
                             "mínima no interrumpe) y el CLI reescribe esa línea al final "
                             "(2026.11.05)"),
    "mensajes_usuario": ("si", "role user"),
    "skills": ("si", "tool_use cuya entrada nombra …/skills/<nombre>/SKILL.md"),
    "escritos.archivos": ("parcial", "tool_use Write (sin su resultado: un Write que falló "
                                     "también cuenta); lo escrito por Shell no se ve"),
    "escritos.entregables": ("parcial", "igual que escritos.archivos"),
    "subagentes": ("no", "el transcript principal no los separa (2026.11.05)"),
    "turnos": ("si", "cada mensaje del socio abre uno (sin horas)"),
}
CONTINUACION = {"retomar": "respaldo_reescrito", "continuar": "desconocido"}
_TIPOS = frozenset(("cursor_session", "cursor_message"))
#: Herramientas que escriben archivos, en minúsculas. VERIFICADO: write (Write
#: en 2026.11.05). Los demás nombres son probables y sin golden.
_ESCRITURA = ("write", "edit", "strreplace", "multiedit", "edit_file", "write_file",
              "search_replace", "applypatch", "apply_patch")
_RUTA = ("path", "file_path", "filePath", "target_file", "targetFile")


class _Minero(object):
    def __init__(self, tramo):
        self.t = tramo

    def linea(self, d):
        if d.get("type") not in _TIPOS:
            self.t.desconocer(d.get("type"))
            return
        if d.get("type") == "cursor_session":
            self.t.reconocer()
            if self.t.cwd is None and isinstance(d.get("cwd"), str):
                self.t.cwd = d["cwd"]
            return
        m = d.get("message") if isinstance(d.get("message"), dict) else None
        if m is None:
            self.t.desconocer("cursor_message:sin_message")
            return
        if m.get("type") == "turn_ended":
            self.t.reconocer()
            return                        # fin de turno: interrupciones «no» (ver COBERTURA)
        role = m.get("role")
        if role not in ("user", "assistant"):
            self.t.desconocer("rol:%s" % role if isinstance(role, str) else None)
            return
        self.t.reconocer()
        clave = "l:%s" % d["huella"] if isinstance(d.get("huella"), str) else ""
        if not self.t.nuevo(clave, None):
            return                        # ya contado (respaldo reescrito, importar)
        cont = m.get("message") if isinstance(m.get("message"), dict) else {}
        partes = [p for p in cont.get("content") or () if isinstance(p, dict)]
        if role == "user":
            self.t.mensajes += 1
            texto = "\n".join(str(p.get("text") or "") for p in partes if p.get("type") == "text")
            # el texto se usa SOLO para el largo por cubeta y sim_prev; se tira
            self.t.turno(None, texto, "humano")
            return
        for p in partes:
            if p.get("type") != "tool_use":
                continue
            self.t.llamadas += 1
            inp = p.get("input") if isinstance(p.get("input"), dict) else {}
            ruta = next((inp[k] for k in _RUTA if isinstance(inp.get(k), str)), None)
            self.t.skills_de_texto(ruta)
            if isinstance(inp.get("command"), str):
                # como claude-code/4: solo cuenta si un lector (cat, head…) la LEE
                for r in _rutas_leidas(inp["command"]):
                    self.t.skills_de_texto(r)
            if str(p.get("name") or "").lower() in _ESCRITURA and ruta:
                self.t.escrito(ruta)


# ── contrato ────────────────────────────────────────────────────────────────

def sesion(path):
    d = M.primera_linea(path)
    if d.get("type") == "cursor_session" and d.get("id"):
        return str(d["id"])
    m = re.match(r"cursor-(.+)\.jsonl$", os.path.basename(path))
    return m.group(1) if m else ""


def cabecera(path):
    d = M.primera_linea(path)
    if d.get("type") == "cursor_session":
        return d.get("cwd"), None
    return None, None


def minar(path, cur, tramo, hasta_t=None, cola=False):
    nuevo, completo = M.recorrer_reescrito(path, cur, _Minero(tramo).linea, tramo, hasta_t)
    return {"cursor": nuevo, "completo": completo, "costo": None}


def al_dia(path, cur):
    return M.al_dia_por_firma(path, cur)


def raices():
    """Los respaldos de Workspace: <estado>/transcripts-backup/<enc>/."""
    import paths
    return [(os.path.join(paths.state_dir(), "transcripts-backup"), 1)]


def es_fuente(nombre):
    return nombre.startswith("cursor-") and nombre.endswith(".jsonl")


def fuentes():
    """Respaldos `cursor-<uuid>.jsonl` de <estado>/transcripts-backup/<enc>/."""
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
            names = os.listdir(full) if os.path.isdir(full) else ()
        except OSError:
            continue
        for n in names:
            if es_fuente(n):
                p = os.path.join(full, n)
                out.append((sesion(p), p))
    return out
