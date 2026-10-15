#!/usr/bin/env python3
"""WORKSPACE · capabilities.py — matriz de capacidades EFECTIVAS (OS + motor + deps).

Fuente única de «qué puede hacer Workspace AQUÍ» (U05 / W-F06 / W-F07 / Z23).
La UI y el manual (manual/*/compatibilidad.md, recalculado por
tests/test_manual_compat.py) derivan de aquí; NO comparan `sys.platform` por
su cuenta para decidir disponibilidad (lo vigila tests/test_capabilities.py).
El doctor ya no tiene fase de capacidades: revisa solo lo esencial.

Estados por capacidad (contrato):
  supported           funciona en este OS + motor con lo instalado
  unsupported         no existe en este OS o este motor (con motivo)
  missing_dependency  existiría, pero falta algo (qué y cómo obtenerlo)
  off                 soportada pero apagada por el socio
  unknown             no verificable sin ejecutar/loguear (se dice, no se inventa)

Capacidades: voice · split · panel · status_live · headless.

Datos: CAPABILITIES/META de engines/*.py + checks BARATOS de OS (PATH, archivos
de config). Sin red, sin login, sin lanzar motores. Falla-suave: un error se
reporta como `unknown`, nunca rompe el hub.
"""
import os
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

STATES = ("supported", "unsupported", "missing_dependency", "off", "unknown")
KEYS = ("voice", "split", "panel", "status_live", "headless")
#: Claves que TODO engine debe declarar en CAPABILITIES (contrato + matriz).
ENGINE_KEYS = ("launch", "inject_context", "mcp", "hooks", "sessions",
               "status_live", "headless")
OS_LABEL = {"darwin": "macOS", "win32": "Windows", "linux": "Linux"}


def current_os():
    """'darwin' | 'win32' | 'linux' — desde sys.platform, leído en CADA llamada
    (tests lo mockean). sys.platform es autoritativo y estable por proceso."""
    p = sys.platform
    if p == "darwin":
        return "darwin"
    if p.startswith(("win", "cygwin", "msys")):
        return "win32"
    return "linux"


def os_label(os_id=None):
    return OS_LABEL.get(os_id or current_os(), os_id or "?")


def _t(key, default, **kw):
    """i18n falla-suave (patrón de updater/migrate): idioma activo; sin
    catálogo/clave → el `default` español."""
    try:
        import i18n
        s = i18n.t(key, **kw)
        if s != key:
            return s
    except Exception:
        pass
    try:
        return default.format(**kw) if kw else default
    except Exception:
        return default


def cap(state, detail="", remedy="", source=""):
    assert state in STATES, state
    return {"state": state, "detail": detail, "remedy": remedy, "source": source}


# ── capacidades de Workspace (OS + dependencias) ─────────────────────────────
def voice(os_id=None, which=None):
    os_id = os_id or current_os()
    if os_id != "darwin":
        return cap("unsupported", _t("doctor.caps.voice.1", "dictado por voz: solo macOS por ahora (Windows/Linux en F3; este SO: %s)") % os_label(os_id), source="os")
    try:
        import voice as _v
    except Exception as exc:
        return cap("unknown", _t("doctor.caps.voice.2", "voz no evaluable: %s") % type(exc).__name__)
    which = which or shutil.which
    missing = []
    if not any(which(n) for n in getattr(_v, "WHISPER_NAMES", ())):
        missing.append("whisper.cpp")
    try:
        if not os.path.isfile(_v.default_model()):
            missing.append(_t("doctor.caps.voice.3", "modelo whisper"))
    except Exception:
        missing.append(_t("doctor.caps.voice.4", "modelo whisper"))
    if not (which("ffmpeg") or which("sox") or which("rec")):
        missing.append(_t("doctor.caps.voice.5", "grabador (ffmpeg/sox)"))
    if not which("osascript"):
        missing.append("osascript")
    if missing:
        return cap("missing_dependency", _t("doctor.caps.missing", "falta: ") + ", ".join(missing),
                   _t("doctor.caps.voice.6", "workspace voice --setup (o brew install whisper-cpp ffmpeg)"), source="deps")
    return cap("supported", _t("doctor.caps.voice.7", "dictado local listo"), source="deps")


def split(os_id=None, which=None):
    os_id = os_id or current_os()
    if os_id == "win32":
        return cap("unsupported", _t("doctor.caps.split.1", "split usa tmux/herdr (Mac/Linux); en Windows abre la sesión sencilla"), source="os")
    which = which or shutil.which
    if which("tmux") or which("herdr"):
        return cap("supported", _t("doctor.caps.split.2", "multiplexer presente"), source="deps")
    return cap("missing_dependency", _t("doctor.caps.split.3", "falta tmux (o herdr)"),
               "brew install tmux · apt install tmux", source="deps")


def panel(os_id=None, which=None):
    """Controles del panel (cambiar/nueva sesión) viven DENTRO del split."""
    sp = split(os_id, which)
    if sp["state"] == "unsupported":
        return cap("unsupported", _t("doctor.caps.panel.1", "controles del panel requieren el split (Mac/Linux); en Windows el panel es solo lectura"),
                   source="os")
    if sp["state"] != "supported":
        return cap(sp["state"], _t("doctor.caps.panel.2", "panel depende del split: ") + sp["detail"],
                   sp["remedy"], sp["source"])
    return cap("supported", _t("doctor.caps.panel.3", "dentro del split"), source="deps")


# ── capacidades del motor ───────────────────────────────────────────────────
def engine_caps(engine_id):
    """(CAPABILITIES dict | None, META dict) del engine — sin lanzar nada."""
    try:
        import dispatch
        mod = dispatch.load_engine(engine_id)
    except Exception:
        mod = None
    if mod is None:
        return None, {}
    caps = getattr(mod, "CAPABILITIES", None)
    return (dict(caps) if isinstance(caps, dict) else None,
            dict(getattr(mod, "META", None) or {}))


def _engine_bool(engine_id, key, caps, meta, which):
    if caps is None:
        return cap("unknown", _t("doctor.caps.engine_unloadable", "motor %s no cargable") % engine_id, source="engine")
    if not caps.get(key):
        return cap("unsupported", _t("doctor.caps.engine_lacks", "%s no ofrece %s") % (engine_id, key), source="engine")
    missing = [b for b in (meta.get("needs") or []) if not which(b)]
    if missing:
        return cap("missing_dependency", _t("doctor.caps.engine_bool.1", "falta en PATH: ") + ", ".join(missing),
                   _t("doctor.caps.engine_bool.2", "instala el CLI oficial de %s") % engine_id, source="deps")
    return cap("supported", _t("doctor.caps.engine_declares", "%s declara %s") % (engine_id, key), source="engine")


def matrix(engine_id=None, os_id=None, which=None):
    """Matriz {clave: cap} para este OS (+ motor si se da)."""
    os_id = os_id or current_os()
    which = which or shutil.which
    out = {"voice": voice(os_id, which), "split": split(os_id, which),
           "panel": panel(os_id, which)}
    if engine_id:
        caps, meta = engine_caps(engine_id)
        out["status_live"] = _engine_bool(engine_id, "status_live", caps, meta, which)
        out["headless"] = _engine_bool(engine_id, "headless", caps, meta, which)
    else:
        for k in ("status_live", "headless"):
            out[k] = cap("unknown", _t("doctor.caps.matrix.1", "sin motor"), source="engine")
    return out


def label(state):
    """Texto corto para UI."""
    es = {"supported": "disponible", "unsupported": "no soportado",
          "missing_dependency": "falta dependencia", "off": "OFF",
          "unknown": "sin verificar"}
    if state not in es:
        return state
    return _t("doctor.caps.state." + state, es[state])


def main(argv=None):
    import json
    argv = list(sys.argv[1:] if argv is None else argv)
    engine = argv[0] if argv else None
    print(json.dumps({"os": current_os(), "engine": engine,
                      "capabilities": matrix(engine)}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
