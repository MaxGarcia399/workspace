#!/usr/bin/env python3
"""WORKSPACE · engine_versions — deriva de versión de los motores.

Por qué existe (2026-10-15): la Mac tenía OpenClaw 2026.5.12 y Hermes 0.18.2;
un Windows recién instalado bajó 2026.10.4 y 0.22.2, que cambiaron su config
(`agents.list` → `agents.entries`) y su `status` (resumen sin credenciales).
Todo «servía en la Mac» y en la máquina nueva decía «sin sesión». Un cliente
nuevo SIEMPRE instala la última versión, no la que probamos.

Contrato: las versiones PROBADAS de cada motor son UNA sola lista, la
`versiones_probadas` de su ficha (arquitectura/fichas/<motor>.json: con las
que se corre la prueba a fondo del motor real; el canario de nuestras máquinas
la amplía cuando una versión nueva sale verde). Conexiones en verde (F1):
antes Motores leía la `VERIFIED_VERSIONS` del parser de métricas y la ficha
decía otra cosa (Kiro 3.5.0 «nueva» en Motores y «probada» en su ficha); esa
lista del parser sigue siendo solo de las métricas (con qué transcript se
probó su lector). El adapter no declara otra. `doctor` y Motores comparan
contra la instalada y, si no es una de esas, lo DICEN sin alarmar (una versión
nueva es informativa: C8-a): así el «no funciona» llega con su causa probable.
tests/test_engine_versions.py lo exige.

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


def motor_de(mod):
    """El id del motor de un adapter («engines.claude_code» → «claude-code»)."""
    return str(getattr(mod, "__name__", "")).rsplit(".", 1)[-1].replace("_", "-")


def probadas_de_la_ficha(motor):
    """`versiones_probadas` de la ficha del motor (lista de textos), o None si no tiene ficha."""
    try:
        import json
        import os
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "arquitectura", "fichas",
                         str(motor) + ".json")
        with open(p, encoding="utf-8") as fh:
            vv = json.load(fh).get("versiones_probadas")
        return [str(v) for v in vv] if isinstance(vv, list) else None
    except Exception:
        return None


def _lista(mod):
    """(la lista de la ficha del motor, el mismo conjunto) o (None, set()) si el motor no tiene ficha. La forma de
    dos valores queda por compatibilidad: antes eran la lista del parser y las que tenían un «pasa»."""
    vv = probadas_de_la_ficha(motor_de(mod))
    if vv is None:
        return None, set()
    return vv, set(vv)


def verified(mod):
    """Versiones PROBADAS del motor del adapter `mod`, parseadas y ordenadas: las de `versiones_probadas` de su ficha
    (la lista única). Un `VERIFIED_VERSIONS` propio solo lo traen los dobles de las pruebas."""
    vv = getattr(mod, "VERIFIED_VERSIONS", None)
    if vv is None:
        vv = _lista(mod)[0]
    out = []
    for v in vv or ():
        p = parse(v)
        if p:
            out.append(p)
    return sorted(set(out))


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
            import arbol_procesos   # Windows: al vencer muere el árbol (.cmd → node)
            env = None
            try:                        # el motor no hereda la bóveda
                import secret_store
                env = secret_store.engine_env()
            except Exception:
                pass
            # sin ventana: la página corre sin consola (localhost_fondo) y en Windows cada `--version` abría
            # la suya, visible un instante («Revisar ahora» en Conexiones: una por motor)
            r = arbol_procesos.run([exe, "--version"], capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=timeout,
                                   stdin=subprocess.DEVNULL, env=env, **arbol_procesos.sin_ventana())
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
    """('ok'|'newer'|'older'|'unsupported'|'broken'|'unknown', instalada,
    probadas) para el `--version` del motor. 'ok' = es una de las probadas;
    'newer' / 'older' = más nueva / más vieja que la probada más nueva (la que
    muestra `probadas`, con cuántas más hay). 'unsupported' = más vieja que MIN_SUPPORTED del adapter (no
    funciona: se bloquea con su UPGRADE_HINT). 'untested' = el motor tiene
    ficha pero su lista de probadas está vacía. 'unknown' = sin ficha, o no se pudo
    leer la instalada. 'broken' = bug conocido en ESTA plataforma
    (KNOWN_BROKEN; detalle con broken())."""
    have = parse(version_text)
    if broken(mod, version_text):
        return "broken", _fmt(have), ""
    floor = parse(getattr(mod, "MIN_SUPPORTED", "") or "")
    if have and floor and have < floor:
        return "unsupported", _fmt(have), _fmt(floor) + "+"
    ver = verified(mod)
    if have and not ver and getattr(mod, "VERIFIED_VERSIONS", None) is None \
            and _lista(mod)[0] is not None:
        return "untested", _fmt(have), ""
    if not have or not ver:
        return "unknown", have and _fmt(have), ""
    rango = _fmt(ver[-1]) + (" (y %d más)" % (len(ver) - 1) if len(ver) > 1 else "")
    if have in ver:
        return "ok", _fmt(have), rango
    return ("newer" if have > ver[-1] else "older"), _fmt(have), rango
