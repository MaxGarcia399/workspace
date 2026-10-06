#!/usr/bin/env python3
"""WORKSPACE · i18n — la CAPA de internacionalización del lado CLIENTE.

FASE 0 (fundación). Aquí vive el contrato que todas las fases siguientes
siguen para traducir pantalla por pantalla. NO traduce nada por sí sola: solo
resuelve el idioma activo y busca cadenas en los catálogos `lang/<code>.py`.

Principios (no negociables):
  · **ES es el default y la FUENTE.** Sin `ui.lang` guardado y sin
    `WORKSPACE_LANG`, todo sale EXACTO como siempre (español), byte-idéntico.
  · **Falla-suave SIEMPRE.** `t()` jamás levanta: clave faltante en el idioma
    activo → se busca en `es` → si tampoco está, se devuelve la propia clave.
    Un catálogo roto/ausente = dict vacío, nunca un crash.
  · **Solo lo que VE EL CLIENTE.** Las pantallas/comandos de desarrollo
    (gateados por `_has_dev_panel()`, stripeados del distro) se quedan en
    español — no pasan por esta capa.

API pública:
  · t(key, **kw)   → cadena del idioma activo (fallback es → key); con kwargs
                     aplica .format(**kw) (falla-suave: si el format truena,
                     devuelve la cadena cruda).
  · lang()         → código del idioma activo: WORKSPACE_LANG (env, gana) →
                     settings `ui.lang` → "es". Cacheado (lectura corta), con
                     invalidación al guardar — mismo espíritu que la paleta.
  · set_lang(code) → persiste `ui.lang` vía settings (atómico) e invalida el
                     cache. Devuelve el código normalizado.
  · available()    → [("es","Español"), ("en","English")] — orden de oferta.
  · refresh()      → invalida el cache del idioma (para procesos de vida larga
                     o tests que cambian el setting por fuera).

Cómo se AGREGA una cadena traducible (lo que siguen las fases 1+): ver
`lang/README.md`. Resumen: clave namespaced por pantalla (`"menu.github.label"`),
texto español actual copiado TAL CUAL en `lang/es.py`, traducción en
`lang/en.py`, y en el código `i18n.t("clave")` donde iba el literal.

Cero dependencias (stdlib, Python 3.9+). Mac y Windows.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

#: Idiomas ofrecidos, en orden de presentación. Agregar uno = sumar su par
#: aquí + crear `lang/<code>.py` con su STRINGS. (El default duro es "es".)
_SUPPORTED = (("es", "Español"), ("en", "English"))
_DEFAULT = "es"

#: Catálogos cargados (code -> STRINGS dict). Memoizados: un catálogo es
#: estático, se importa una sola vez por proceso.
_CATALOGS = {}

#: Cache del idioma resuelto desde settings (la parte que toca disco). None =
#: sin resolver todavía. WORKSPACE_LANG NO se cachea (gana en vivo, por tick).
_lang_cache = None


def _codes():
    return {c for c, _ in _SUPPORTED}


def available():
    """[(code, nombre_nativo)] en orden de oferta — lo consume el toggle del
    menú y el paso 0 del onboarding."""
    return list(_SUPPORTED)


def _load_catalog(code):
    """STRINGS del idioma `code`: el MERGE de todos los módulos por pantalla de
    `lang/<code>/*.py` (descubrimiento dinámico), memoizado. Cada módulo exporta
    su `STRINGS` ya namespaceado por pantalla; aquí se funden en un solo dict.
    Falla-suave POR MÓDULO: uno roto/ausente se salta y sigue con los demás
    (una pantalla a medio traducir no tumba al resto). Back-compat: si existe un
    `lang/<code>.py` PLANO (modelo viejo), también se mergea.

    Esta fusión es lo que permite el FAN-OUT de traducción: un agente = un
    módulo (`lang/es/<pantalla>.py` + `lang/en/<pantalla>.py`), sin colisiones."""
    if code in _CATALOGS:
        return _CATALOGS[code]
    merged = {}

    def _merge(modname):
        try:
            mod = __import__(modname, fromlist=["STRINGS"])
            s = getattr(mod, "STRINGS", None)
            if isinstance(s, dict):
                merged.update(s)
        except Exception:
            pass                         # módulo roto/ausente → se salta

    pkg_dir = os.path.join(ROOT, "lang", code)
    if os.path.isdir(pkg_dir):
        for fn in sorted(os.listdir(pkg_dir)):
            if fn.endswith(".py") and not fn.startswith("_"):
                _merge("lang.%s.%s" % (code, fn[:-3]))
    else:
        _merge("lang.%s" % code)         # back-compat: catálogo plano
    _CATALOGS[code] = merged
    return merged


def lang():
    """Código del idioma activo. Precedencia: env WORKSPACE_LANG (gana, en
    vivo) → settings `ui.lang` (cacheado) → "es". Falla-suave total."""
    env = os.environ.get("WORKSPACE_LANG")
    if env:
        code = env.strip().lower()
        if code in _codes():
            return code
    global _lang_cache
    if _lang_cache is not None:
        return _lang_cache
    code = _DEFAULT
    try:
        import settings
        v = settings.get("ui.lang", _DEFAULT)
        if isinstance(v, str) and v.strip().lower() in _codes():
            code = v.strip().lower()
    except Exception:
        code = _DEFAULT
    _lang_cache = code
    return code


def set_lang(code):
    """Persiste `ui.lang` (vía settings, atómico) e invalida el cache. Código
    no soportado → ValueError SIN escribir. Devuelve el código normalizado.
    Nota: WORKSPACE_LANG (si está) sigue ganando en `lang()` — es deliberado
    (el env es un override de prueba)."""
    code = (code or "").strip().lower()
    if code not in _codes():
        raise ValueError("idioma no soportado: %r (usa %s)"
                         % (code, "/".join(c for c, _ in _SUPPORTED)))
    global _lang_cache
    try:
        import settings
        settings.set("ui.lang", code)
    except Exception:
        # No se pudo persistir (store raro): igual reflejamos el cambio en el
        # proceso vivo para que la UI responda; el siguiente arranque reevalúa.
        pass
    _lang_cache = code
    return code


def refresh():
    """Invalida el cache del idioma — la próxima `lang()` reevalúa desde
    settings. Para pantallas de vida larga o tests que tocan el setting por
    fuera de `set_lang`."""
    global _lang_cache
    _lang_cache = None


def t(key, **kw):
    """Cadena traducida de `key` en el idioma activo. Falla-suave en cascada:
    idioma activo → catálogo `es` → la propia `key`. Con **kw aplica
    .format(**kw) (si el format truena, devuelve la cadena cruda). JAMÁS
    levanta."""
    try:
        code = lang()
    except Exception:
        code = _DEFAULT
    s = _load_catalog(code).get(key)
    if s is None and code != _DEFAULT:
        s = _load_catalog(_DEFAULT).get(key)
    if s is None:
        s = key
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


# ── CLI de diagnóstico (opcional, útil en dev) ──────────────────────────────
def _main(argv):
    if not argv:
        print("idioma activo: %s" % lang())
        print("soportados: %s" % ", ".join("%s (%s)" % (c, n)
                                            for c, n in _SUPPORTED))
        return 0
    cmd = argv[0]
    if cmd == "lang":
        print(lang())
        return 0
    if cmd == "set" and len(argv) > 1:
        print(set_lang(argv[1]))
        return 0
    if cmd == "t" and len(argv) > 1:
        print(t(argv[1]))
        return 0
    print("uso: i18n.py [lang | set <code> | t <key>]", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
