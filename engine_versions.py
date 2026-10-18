#!/usr/bin/env python3
"""WORKSPACE · engine_versions — deriva de versión de los motores.

Por qué existe (2026-10-15): la Mac tenía OpenClaw 2026.5.12 y Hermes 0.18.2;
un Windows recién instalado bajó 2026.10.4 y 0.22.2, que cambiaron su config
(`agents.list` → `agents.entries`) y su `status` (resumen sin credenciales).
Todo «servía en la Mac» y en la máquina nueva decía «sin sesión». Un cliente
nuevo SIEMPRE instala la última versión, no la que probamos.

Contrato: un adapter declara `VERIFIED_VERSIONS = ("x.y.z", …)` — las versiones
del CLI oficial con las que se verificaron sus lecturas (status, sesiones,
config). `doctor` compara contra la instalada y, si es de una línea más nueva
(mayor.menor) que la más nueva verificada — o más vieja que la más vieja —,
lo AVISA (no falla): así el «no funciona» llega con su causa probable.
tests/test_engine_versions.py exige la declaración a todo motor nuevo.

Cero dependencias (stdlib, 3.9+). Falla-suave: nada aquí lanza.
"""
import re

_VER = re.compile(r"(?<![\d.])v?(\d+)\.(\d+)(?:\.(\d+))?")


def parse(text):
    """Primera versión «x.y[.z]» de un texto (`--version`) → tupla de ints, o
    None. «Hermes Agent v0.22.2 (2026.9.24)» → (0, 22, 2)."""
    m = _VER.search(str(text or ""))
    if not m:
        return None
    return tuple(int(g) for g in m.groups() if g is not None)


def verified(mod):
    """Versiones verificadas que declara el adapter, parseadas y ordenadas."""
    out = []
    for v in getattr(mod, "VERIFIED_VERSIONS", None) or ():
        p = parse(v)
        if p:
            out.append(p)
    return sorted(out)


def _fmt(t):
    return ".".join(str(x) for x in t)


_CACHE = {}
#: Caché en disco (entre procesos: cada arranque de agente es un proceso nuevo
#: y `openclaw --version` cuesta 2-3 s de node). Se invalida si el binario
#: cambia (mtime) y, por si un instalador no lo toca, a las 12 h.
_DISK_TTL = 12 * 3600


def _disk_cache_path():
    try:
        import os
        import paths
        return os.path.join(paths.state_dir(), "engine-versions.json")
    except Exception:
        return ""


def _disk_get(exe, mtime):
    import json
    import time
    p = _disk_cache_path()
    try:
        with open(p, encoding="utf-8") as fh:
            row = (json.load(fh) or {}).get(exe) or {}
        if row.get("mtime") == mtime and time.time() - float(row.get("at", 0)) < _DISK_TTL:
            return row.get("out")
    except Exception:
        pass
    return None


def _disk_put(exe, mtime, out):
    import json
    import os
    import time
    p = _disk_cache_path()
    if not p:
        return
    try:
        try:
            with open(p, encoding="utf-8") as fh:
                d = json.load(fh) or {}
        except Exception:
            d = {}
        d[exe] = {"mtime": mtime, "out": out, "at": time.time()}
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(d, fh)
        os.replace(tmp, p)
    except Exception:
        pass


def installed_version(exe, runner=None, timeout=15):
    """Salida de `<exe> --version` ('' si no se pudo), cacheada por ruta (en
    memoria y en disco): el hub, Motores y cada arranque la piden, y cada
    llamada puede arrancar node."""
    try:                    # la clave cambia si el binario se reinstala
        import os
        mtime = os.path.getmtime(exe)
    except Exception:
        mtime = None
    key = (exe, mtime)
    if runner is None and key in _CACHE:
        return _CACHE[key]
    if runner is None:
        hit = _disk_get(exe, mtime)
        if hit:
            _CACHE[key] = hit
            return hit
    out = ""
    try:
        if runner is not None:
            r = runner([exe, "--version"])
        else:
            import subprocess
            env = None
            try:                        # el motor no hereda la bóveda
                import secret_store
                env = secret_store.engine_env()
            except Exception:
                pass
            r = subprocess.run([exe, "--version"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=timeout,
                               stdin=subprocess.DEVNULL, env=env)
        if getattr(r, "returncode", 1) == 0:
            out = (getattr(r, "stdout", "") or "").strip()
    except Exception:
        out = ""
    if runner is None:
        _CACHE[key] = out
        if out:
            _disk_put(exe, mtime, out)
    return out


def broken(mod, version_text, platform=None, mode=None):
    """Bug CONOCIDO del motor en esta plataforma y versión (KNOWN_BROKEN del
    adapter) → {'why', 'hint'}; None si no aplica. Una entrada con `modes`
    solo cuenta si el llamador pide ese `mode` (ej.: OpenClaw 2026.10.x en
    Windows falla SOLO en `tui --local`, el modo de respaldo sin gateway)."""
    import sys
    have = parse(version_text)
    if not have:
        return None
    plat = platform or sys.platform
    for b in getattr(mod, "KNOWN_BROKEN", None) or ():
        try:
            if plat not in tuple(b.get("platforms") or (plat,)):
                continue
            if b.get("modes") and mode not in tuple(b["modes"]):
                continue
            lo, hi = parse(b.get("from") or "0.0"), parse(b.get("to") or "99999.0")
            if lo <= have <= hi:
                return {"why": str(b.get("why") or ""), "hint": str(b.get("hint") or "")}
        except Exception:
            continue
    return None


#: Salida para quien quiera probar una versión frenada (política «la más
#: nueva por defecto», 2026-10-16): un bloqueo sin salida le quita la
#: decisión al socio.
ANYWAY_ENV = "WORKSPACE_ABRIR_IGUAL"


def allow_anyway(prompt="  ¿Abrir de todos modos? [s/N] "):
    """True si el socio quiere abrir igual una versión frenada: variable
    WORKSPACE_ABRIR_IGUAL=1, o un «s» en la terminal. Sin terminal → False."""
    import os
    import sys
    if os.environ.get(ANYWAY_ENV, "").strip().lower() in ("1", "true", "si", "sí", "yes"):
        return True
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return False
        return input(prompt).strip().lower() in ("s", "si", "sí", "y", "yes")
    except (EOFError, KeyboardInterrupt, OSError):
        return False


def drift(mod, version_text):
    """('ok'|'newer'|'older'|'unsupported'|'broken'|'unknown', instalada, rango)
    para el
    `--version` del motor. 'unsupported' = más vieja que MIN_SUPPORTED del
    adapter (no funciona: se bloquea con su UPGRADE_HINT). 'unknown' = el
    adapter no declara versiones o no se pudo leer la instalada. 'broken' =
    bug conocido en ESTA plataforma (KNOWN_BROKEN; detalle con broken())."""
    have = parse(version_text)
    if broken(mod, version_text):
        return "broken", _fmt(have), ""
    floor = parse(getattr(mod, "MIN_SUPPORTED", "") or "")
    if have and floor and have < floor:
        return "unsupported", _fmt(have), _fmt(floor) + "+"
    ver = verified(mod)
    if not have or not ver:
        return "unknown", have and _fmt(have), ""
    rango = _fmt(ver[0]) if len(ver) == 1 else "%s–%s" % (_fmt(ver[0]), _fmt(ver[-1]))
    if have[:2] > ver[-1][:2]:
        return "newer", _fmt(have), rango
    if have[:2] < ver[0][:2]:
        return "older", _fmt(have), rango
    return "ok", _fmt(have), rango
