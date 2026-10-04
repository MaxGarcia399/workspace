#!/usr/bin/env python3
"""WORKSPACE · hubtheme.py — motor de TEMAS a nivel harness (fase F1: web).

Un TEMA es un directorio en `themes/<id>/` con un manifiesto `theme.json`
(tokens + metadata) y, opcionalmente, un skin `web.css` scoped a
`body[data-theme="<id>"]`. Agregar un tema = dropear esa carpeta — se
auto-descubre, igual que las secciones del dev panel. Ver `themes/README.md`.

Este módulo es la ÚNICA API que consumen las superficies (hoy: dashboard.py
--dev; fases F3-F4: front.py/theme.py):

    import hubtheme
    T = hubtheme.load()            # manifiesto del tema ACTIVO (resuelto)
    T = hubtheme.load("cyberpunk") # o uno explícito (preview)
    hubtheme.available()           # [{id,label,emoji,default,swatches}, …]
    hubtheme.css(T)                # CSS del tema (tokens + skin), sin <style>
    hubtheme.style_block(T)        # '<style id="theme-css">…</style>' listo
    hubtheme.themes_payload()      # payload de GET /api/themes (lista + activo)

SELECCIÓN (precedencia, espejo del resto de WORKSPACE — env > store > default):
  1. env `WORKSPACE_THEME` (gana siempre; útil para probar y para el launcher)
  2. settings `ui.theme` (store unificado, POST /api/theme lo persiste)
  3. default `olympo`

TOKENS: el manifiesto declara `web.tokens` con claves neutrales (accent, bg,
surface, radius, font…). css() las emite como CSS vars `--th-*` scoped a
body[data-theme=<id>] Y re-liga los alias `--ds-*` que TODO el panel ya
consume — así un tema re-tematiza el panel entero sin que las secciones
(board.js/versiones.js/…) sepan de colores. El DOM NUNCA cambia por tema:
solo CSS (regla de oro de la arquitectura — research/design/temas/).

FALLA-SUAVE ABSOLUTA (mismo principio que todo el harness): tema inexistente
o manifiesto corrupto → `olympo`; themes/ ausente → olympo mínimo embebido;
settings ilegible → default. El default olympo NO emite overrides — su look
ES el `:root` del shell, por construcción cero regresión visual.

stdlib puro (3.9+), sin estado en disco propio (lee themes/ en cada llamada,
como dash.dev.js_blobs: editar un tema = refrescar el navegador).
"""
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
THEMES_DIR = os.path.join(ROOT, "themes")   # los tests lo parchan

DEFAULT_ID = "olympo"

# Manifiesto mínimo embebido: si themes/ no existe o el default está roto,
# el motor sigue funcionando (olympo = look base del shell, sin overrides).
_FALLBACK = {"id": DEFAULT_ID, "label": "Olympo", "emoji": "⛬",
             "swatches": ["#d2a64b", "#8a6d31"], "web": {"tokens": {}}}

_ID_RX = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")

# F5: un swatch DEBE ser un color CSS (viaja a un inline-style del slider del
# shell — `background:<swatch>` — y a quien consuma themes_payload()). Formas
# aceptadas: #hex (3/4/6/8) · rgb()/rgba()/hsl()/hsla() con charset numérico ·
# nombre CSS (identificador pelado). Todo lo demás se descarta al fallback.
_COLOR_RX = re.compile(
    r"^(?:#(?:[0-9a-fA-F]{3,4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})"
    r"|(?:rgb|rgba|hsl|hsla)\(\s*[0-9.,%\s/+-]{1,64}(?:deg)?[0-9.,%\s/+-]{0,64}\)"
    r"|[a-zA-Z]{1,30})$")


def _clean_swatch(v, fallback):
    """Color CSS válido o `fallback` (jamás emite un valor arbitrario)."""
    v = str(v).strip()
    return v if _COLOR_RX.match(v) else fallback

# token neutral → var DS que el panel ya consume (el alias se re-liga a nivel
# body[data-theme=…] para ganarle en cascada a body[data-pal] — back-compat).
_DS_MAP = {
    "bg": "--ds-bg", "surface": "--ds-surface", "surface2": "--ds-surface-2",
    "surface3": "--ds-surface-3", "border": "--ds-border",
    "border-hi": "--ds-border-hi", "text": "--ds-text", "dim": "--ds-dim",
    "faint": "--ds-faint", "accent": "--ds-gold", "accent-hi": "--ds-gold-hi",
    "accent-soft": "--ds-gold-soft", "accent-line": "--ds-gold-line",
    "red": "--ds-red", "amber": "--ds-amber", "blue": "--ds-blue",
    "green": "--ds-green", "grey": "--ds-grey", "radius": "--ds-radius",
    "radius-sm": "--ds-radius-sm", "fast": "--ds-fast", "med": "--ds-med",
    "sp-1": "--ds-sp-1", "sp-2": "--ds-sp-2", "sp-3": "--ds-sp-3",
    "sp-4": "--ds-sp-4", "sp-5": "--ds-sp-5",
}
# claves sin alias DS (p. ej. font, accent-2) → solo --th-<clave>


def _valid_id(tid):
    return bool(tid) and isinstance(tid, str) and bool(_ID_RX.match(tid))


def _read_manifest(tid):
    """theme.json de un tema. None si no existe / corrupto / id inválido."""
    if not _valid_id(tid):
        return None
    path = os.path.join(THEMES_DIR, tid, "theme.json")
    try:
        with open(path, encoding="utf-8") as fh:
            m = json.load(fh)
        if not isinstance(m, dict):
            return None
    except Exception:
        return None
    m["id"] = tid                                    # el dir manda, no el json
    return m


def _normalize(m):
    """Manifiesto con defaults completos (siempre las mismas claves)."""
    out = dict(_FALLBACK)
    out.update({k: v for k, v in m.items() if v is not None})
    out["id"] = m.get("id", DEFAULT_ID)
    out["label"] = str(m.get("label") or out["id"].capitalize())
    web = m.get("web") if isinstance(m.get("web"), dict) else {}
    tokens = web.get("tokens") if isinstance(web.get("tokens"), dict) else {}
    out["web"] = {"tokens": tokens, "css": web.get("css")}
    sw = m.get("swatches")
    if not (isinstance(sw, list) and len(sw) >= 2):
        acc = tokens.get("accent") or _FALLBACK["swatches"][0]
        acc2 = (tokens.get("accent-2") or tokens.get("accent-line")
                or _FALLBACK["swatches"][1])
        sw = [acc, acc2]
    # F5: solo colores CSS válidos llegan al slider (inline-style del shell)
    out["swatches"] = [_clean_swatch(sw[0], _FALLBACK["swatches"][0]),
                       _clean_swatch(sw[1], _FALLBACK["swatches"][1])]
    return out


def available():
    """Temas instalados: [{id,label,emoji,default,swatches}, …] — olympo
    primero, resto alfabético. Falla-suave: sin themes/ → solo el fallback."""
    ids = []
    try:
        for d in sorted(os.listdir(THEMES_DIR)):
            if _read_manifest(d) is not None:
                ids.append(d)
    except Exception:
        pass
    if DEFAULT_ID in ids:                       # default siempre primero
        ids.remove(DEFAULT_ID)
    ids.insert(0, DEFAULT_ID)
    out = []
    for tid in ids:
        m = _normalize(_read_manifest(tid) or dict(_FALLBACK))
        out.append({"id": m["id"], "label": m["label"],
                    "emoji": m.get("emoji", ""), "default": tid == DEFAULT_ID,
                    "swatches": m["swatches"]})
    return out


# ── picker del hub (TUI): solo temas PULIDOS ────────────────────────────────
# Feedback del socio 2026-07-04: los temas del TUI se pulen UNO a UNO al nivel
# del cockpit enriquecido; mientras tanto el picker del hub ofrece SOLO los ya
# pulidos. Es lista de EXCLUSIÓN explícita (un tema nuevo/custom pasa): los
# excluidos NO se borran del motor — siguen instalados y accesibles vía
# WORKSPACE_THEME=<id> / ui.theme directo, y salen de esta lista al pulirse.
# 2026-10-02 (pedido del socio — poda + familia rosé): el hub ofrece SOLO
# mono, cyberpunk, rose y la familia rosé nueva (durazno/lavanda/salvia/
# bruma) = settings._TUI_THEMES, que debe ir SINCRONIZADA con esta lista.
# Quedan fuera los temas de AGENTE (visten a su agente, no al hub), carmesí
# (sin bloque `tui` todavía), los skins de mockup (estudio/observatorio/
# oficina-8bit — siguen instalados para el dev panel) y `olympo` (borrado de
# themes/; available() lo sigue sintetizando como fallback embebido, por eso
# hay que excluirlo aquí explícitamente).
TUI_PENDIENTES = ("argus", "carmesi", "zenith", "atlas",
                  "estudio", "observatorio", "oficina-8bit", "olympo")


def hub_picker():
    """available() para el PICKER del hub (config TUI): oculta los temas aún
    no pulidos para el TUI (TUI_PENDIENTES). Falla-suave: si el filtro
    dejara la lista vacía (registro raro), devuelve available() completo —
    el picker jamás se queda sin opciones."""
    try:
        av = available()
        out = [t for t in av if t.get("id") not in TUI_PENDIENTES]
        return out or av
    except Exception:
        return available()


# ── picker del DEV PANEL (web): lista de INCLUSIÓN ──────────────────────────
# Pedido del socio: el switcher del dev panel solo estos (los temas de agente +
# cyberpunk), independiente del hub. Es lista POSITIVA (a diferencia de
# TUI_PENDIENTES que es de exclusión): agregar un tema al dev panel = añadirlo
# aquí. Los que no están siguen instalados (accesibles vía WORKSPACE_THEME).
WEB_THEMES = ("olympo", "zenith", "atlas", "argus", "cyberpunk", "mono")


def web_picker():
    """available() filtrado a WEB_THEMES — la lista del switcher del dev panel.
    Falla-suave: si el filtro deja la lista vacía (ningún WEB_THEME instalado),
    devuelve available() completo (el switcher jamás se queda sin opciones)."""
    try:
        av = available()
        out = [t for t in av if t.get("id") in WEB_THEMES]
        return out or av
    except Exception:
        return available()


def _settings_theme():
    # El DEV PANEL usa ui.web_theme, TOTALMENTE INDEPENDIENTE del hub/TUI
    # (ui.theme). Sin fallback a ui.theme: cambiar el tema del hub NO toca el
    # del dev panel (pedido del socio). Default propio (olympo).
    try:
        import settings
        v = settings.get("ui.web_theme", DEFAULT_ID)
        return v if isinstance(v, str) else DEFAULT_ID
    except Exception:
        return DEFAULT_ID


def resolve_id(explicit=None):
    """Id del tema activo (explicit > env WORKSPACE_THEME > settings > default).
    Un candidato sin manifiesto legible se salta (falla-suave al siguiente)."""
    for cand in (explicit, os.environ.get("WORKSPACE_THEME"), _settings_theme()):
        cand = (cand or "").strip().lower()
        if cand and _read_manifest(cand) is not None:
            return cand
    return DEFAULT_ID


def load(theme_id=None):
    """Manifiesto RESUELTO del tema activo (o del explícito). Jamás levanta:
    cualquier problema → olympo (y si ni olympo está en disco, el embebido)."""
    tid = resolve_id(theme_id)
    m = _read_manifest(tid)
    if m is None and tid != DEFAULT_ID:
        m = _read_manifest(DEFAULT_ID)
    return _normalize(m if m is not None else dict(_FALLBACK))


# ── emisión de CSS ──────────────────────────────────────────────────────────
#
# F2 — POLÍTICA DE RECURSOS EXTERNOS (defensa-en-profundidad, temas de 3ros):
# el CSS de un tema NO debe provocar fetches a hosts externos desde el panel
# (CSS no ejecuta JS, pero `@import` y `url()` SÍ disparan requests → tracking
# / exfiltración por CSS). Qué se permite en tokens y skins:
#   PERMITIDO : `url(data:…)` inline · `url(#ancla)` · rutas RELATIVAS sin
#               esquema (resuelven contra el origen del panel; el CSP del
#               dev panel — dashboard.py — las limita además a 'self').
#   BLOQUEADO : `@import` (siempre, incluso relativo) · `url()`/`image-set()`
#               con esquema (`http:`/`https:`/`javascript:`/…) o
#               protocol-relative (`//host`) · referencias con backslash
#               (los escapes CSS podrían disfrazar un esquema).
# En SKINS lo bloqueado se neutraliza en el texto crudo y DESPUÉS se
# re-verifica sobre una copia decodificada (escapes CSS resueltos, comentarios
# fuera); si aún queda algo sospechoso el skin entero se descarta. En TOKENS
# la política es más dura: un token que referenciaba algo externo se descarta
# completo (un token es un solo valor — no hay "resto" que valga la pena
# salvar). Falla-suave siempre: jamás se emite un recurso externo "porque no
# lo supimos limpiar".
#
# NOTA v2 (lo que dejó ROJO el intento v1, rama wip/theme-hardening-red):
#   · el matching de url(…) por regex `[^()]*` no cubría paréntesis anidados
#     (`url(javascript:alert(1))`) → aquí el cierre se busca por PROFUNDIDAD.
#   · _clean_value estripaba `;` ANTES de mirar url(data:…) → los data-URIs
#     (`data:image/png;base64,…`) llegaban mutilados → aquí se PROTEGEN
#     primero con placeholders y se restauran al final.
_SKIN_MAX = 256 * 1024          # F4: cap de lectura de un web.css (256 KB)
_AT_IMPORT_RX = re.compile(r"@import\b[^;{}]*;?", re.I)
_FN_OPEN_RX = re.compile(r"(?<![\w-])(url|image-set)\s*\(", re.I)
# url(data:…) SEGURO para preservar en un token: mime + params (;base64) con
# charset estricto y payload base64/percent — sin comillas, parens, <>{} ni
# nada capaz de romper la declaración o el <style>.
_DATA_URL_RX = re.compile(
    r"url\(\s*(['\"]?)"
    r"(data:[a-zA-Z0-9/+.-]+(?:;[a-zA-Z0-9=+.-]+)*,[A-Za-z0-9+/=._%~-]*)"
    r"\1\s*\)")


def _css_unescape(s):
    """Resuelve escapes CSS (\\XX… hex y \\c literal) — SOLO para escanear."""
    def _hex(m):
        try:
            cp = int(m.group(1), 16)
            return chr(cp) if 0 < cp <= 0x10FFFF else "�"
        except Exception:
            return "�"
    s = re.sub(r"\\([0-9a-fA-F]{1,6})[ \t\n]?", _hex, s)
    return re.sub(r"\\(.)", r"\1", s)


def _scan_copy(css):
    """Copia normalizada para DETECTAR evasiones: sin comentarios, escapes
    resueltos, minúsculas. Nunca se emite — solo se inspecciona."""
    css = re.sub(r"/\*.*?\*/", " ", css, flags=re.S)
    return _css_unescape(css).lower()


def _ref_ok(v):
    """¿Una referencia (el argumento de url()/image-set()) es local segura?"""
    v = str(v).strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "'\"":
        v = v[1:-1].strip()
    if not v:
        return True                     # url() vacío: no hay fetch
    if "\\" in v:
        return False                    # escapes → podría disfrazar esquema
    low = v.lower()
    if low.startswith("#") or low.startswith("data:"):
        return True
    if low.startswith("//"):
        return False                    # protocol-relative → host externo
    if re.match(r"^[a-z][a-z0-9+.-]*:", low):
        return False                    # cualquier otro esquema
    return True                         # ruta relativa (mismo origen)


def _url_inner_ok(inner):
    """¿TODO lo de adentro de un url(…)/image-set(…) es local? Valida cada
    string entrecomillado (image-set) o el valor pelado (url), y además
    cualquier token con pinta de esquema fuera de comillas."""
    inner = str(inner).strip()
    if not inner:
        return True
    if "\\" in inner:
        return False
    quoted = re.findall(r"'([^']*)'|\"([^\"]*)\"", inner)
    vals = [a or b for a, b in quoted] if quoted else [inner]
    if not all(_ref_ok(v) for v in vals):
        return False
    rest = re.sub(r"'[^']*'|\"[^\"]*\"", " ", inner) if quoted else ""
    for m in re.finditer(r"(?:^|[\s,(])\s*((?://|[a-zA-Z][\w+.-]*:)[^\s,)]*)",
                         rest):
        if not _ref_ok(m.group(1)):
            return False
    return True


def _neutralize_externals(css):
    """Neutraliza @import y url()/image-set() externos en texto CSS crudo.
    El cierre de cada llamada se busca por PROFUNDIDAD de paréntesis (una
    regex `[^()]*` no cubre `url(javascript:alert(1))` — ese hueco fue uno
    de los rojos del intento v1). Paréntesis sin cerrar → se trata todo el
    resto como argumento y se neutraliza (nunca beneficio de la duda)."""
    css = _AT_IMPORT_RX.sub("/* @import bloqueado (hubtheme F2) */", css)
    out, pos = [], 0
    while True:
        m = _FN_OPEN_RX.search(css, pos)
        if m is None:
            out.append(css[pos:])
            return "".join(out)
        i = m.end()
        depth, j = 1, i
        while j < len(css) and depth:
            if css[j] == "(":
                depth += 1
            elif css[j] == ")":
                depth -= 1
            j += 1
        inner = css[i:j - 1] if depth == 0 else css[i:]
        out.append(css[pos:m.start()])
        if depth == 0 and _url_inner_ok(inner):
            out.append(css[m.start():j])
        else:
            out.append("%s()" % m.group(1).lower())   # sin argumento = sin fetch
        pos = j


def _externals_remain(css):
    """True si la copia decodificada AÚN referencia algo externo (evasión por
    escapes / anidación) — el llamador descarta el bloque entero."""
    scan = _scan_copy(css)
    if "@import" in scan:
        return True
    for m in re.finditer(r"(?<![\w-])(?:url|image-set)\s*\(", scan):
        depth, j = 1, m.end()
        while j < len(scan) and depth:
            if scan[j] == "(":
                depth += 1
            elif scan[j] == ")":
                depth -= 1
            j += 1
        inner = scan[m.end():j - 1] if depth == 0 else scan[m.end():]
        if not _url_inner_ok(inner):
            return True
    return False


def _clean_value(v):
    """Sanea un valor de token para vivir dentro de un <style> (sin cerrar el
    bloque ni abrir reglas): fuera <, >, {, }, ; y saltos de línea. F2: sin
    recursos externos — si el valor referenciaba url()/image-set()/@import
    externo (o intenta evadir con escapes CSS), el token ENTERO se descarta
    (''). Los `url(data:…)` seguros se protegen ANTES del strip de `;` (los
    data-URIs llevan `;base64` — mutilarlos fue un rojo del intento v1)."""
    v = str(v).replace("\x00", "")     # NUL fuera: es el charset del placeholder
    protected = []

    def _keep(m):
        protected.append("url(%s)" % m.group(2))       # forma canónica, sin comillas
        return "\x00%d\x00" % (len(protected) - 1)

    v = _DATA_URL_RX.sub(_keep, v)
    v = re.sub(r"[<>{};\n\r]", "", v).strip()
    if v and ("\\" in v or "@" in v or re.search(r"url|image-set", v, re.I)):
        cleaned = _neutralize_externals(v)
        if cleaned != v or _externals_remain(cleaned):
            return ""                                  # token podrido: fuera
    return re.sub(r"\x00(\d+)\x00",
                  lambda m: protected[int(m.group(1))], v).strip()


def _clean_key(k):
    return re.sub(r"[^a-z0-9-]", "", str(k).lower())


def _skin_css(T):
    """Contenido del web.css del tema (skin scoped). '' si no hay/ilegible.
    F4: cap de 256 KB — un skin más grande se descarta (degradar, no cargar).
    F2: @import y url()/image-set() externos se neutralizan; si tras limpiar
    aún queda rastro (evasión por escapes) el skin ENTERO se descarta. En
    ambos casos degrada a un comentario CSS que explica el porqué (visible
    en el <style> servido = log in-band)."""
    name = T["web"].get("css") or "web.css"
    if os.path.basename(str(name)) != str(name):      # jaula: solo el dir del tema
        return ""
    path = os.path.join(THEMES_DIR, T["id"], str(name))
    try:
        with open(path, encoding="utf-8") as fh:
            css = fh.read(_SKIN_MAX + 1)
    except Exception:
        return ""
    if len(css) > _SKIN_MAX:                          # F4: skin gigante → skip
        return ("/* skin %s omitido: excede el cap de %d KB (hubtheme F4) */"
                % (T["id"], _SKIN_MAX // 1024))
    css = _neutralize_externals(css)                  # F2: sin fetch externo
    if _externals_remain(css):
        return ("/* skin %s omitido: referencia recursos externos que no se "
                "pudieron neutralizar (hubtheme F2) */" % T["id"])
    # nunca permitir que el skin cierre el <style> del shell
    return re.sub(r"</\s*style", r"<\\/style", css, flags=re.I)


def css(T):
    """CSS completo del tema (tokens + skin), SIN el wrapper <style>. Para el
    default olympo (sin tokens ni skin) devuelve solo un comentario — su look
    es el :root del shell; swapearlo en vivo limpia cualquier override."""
    tid = T["id"]
    parts = []
    tokens = T["web"]["tokens"]
    if tokens:
        decls = []
        for k, v in tokens.items():
            ck, cv = _clean_key(k), _clean_value(v)
            if not ck or not cv:
                continue
            decls.append("--th-%s:%s" % (ck, cv))
            if ck in _DS_MAP:                    # re-liga el alias DS a nivel body
                decls.append("%s:var(--th-%s)" % (_DS_MAP[ck], ck))
        if decls:
            parts.append('body[data-theme="%s"]{%s}' % (tid, ";".join(decls)))
    skin = _skin_css(T)
    if skin:
        parts.append(skin)
    if not parts:
        return "/* tema %s — look base del shell (:root), sin overrides */" % tid
    return "\n".join(parts)


def style_block(T):
    """Bloque <style id="theme-css"> listo para inyectar en el <head> del
    shell (dashboard.py --dev). El JS del switcher swapea su textContent."""
    return '<style id="theme-css" data-theme="%s">\n%s\n</style>' % (T["id"], css(T))


def themes_payload():
    """Payload de GET /api/themes: la lista del DEV PANEL (web_picker: solo
    WEB_THEMES) con cada tema y su css listo para aplicar en vivo + el activo +
    si el env lo tiene fijado."""
    themes = []
    for meta in web_picker():
        T = load(meta["id"])
        t = dict(meta)
        t["css"] = css(T)
        themes.append(t)
    return {"themes": themes, "active": resolve_id(),
            "env_locked": bool((os.environ.get("WORKSPACE_THEME") or "").strip())}


if __name__ == "__main__":
    import sys
    act = resolve_id()
    print("temas instalados (activo: %s):" % act)
    for t in available():
        mark = "●" if t["id"] == act else "·"
        print("  %s %-14s %s%s" % (mark, t["id"], t["label"],
                                   "  (default)" if t["default"] else ""))
    if len(sys.argv) > 1:
        print("\n--- css(%s) ---" % sys.argv[1])
        print(css(load(sys.argv[1])))
