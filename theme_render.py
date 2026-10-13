#!/usr/bin/env python3
"""WORKSPACE · theme_render — UNA paleta semántica, todas las superficies.

Lección de Omarchy (acción 8 del reporte): un tema declara una paleta
SEMÁNTICA (accent, background, foreground, muted…) y cada consumidor sale de
ella por PLANTILLA. Aquí las plantillas viven en `templates/theme/`:

    osc.json.tpl                   fondo/tinta/cursor de la terminal (OSC 10/11/12)
    tui.json.tpl                   bloque `tui` (roles ANSI del recinto)
    web.json.tpl                   `web.tokens` del dev panel
    engine-<motor>.json.tpl        tema DENTRO del motor (hoy: claude-code)

Agregar un motor = dropear `engine-<motor>.json.tpl` (y anotarlo en ENGINES).
Codex y Antigravity quedan con el hook VACÍO a propósito: su formato de tema
in-app no está documentado/verificado — no se inventa (ver ENGINES).

De dónde sale la paleta de un tema (`palette_from_manifest`):
  1. el bloque `palette` de `themes/<id>/theme.json` (ADITIVO, opcional);
  2. si falta una clave, se DERIVA de lo que el tema ya declara (`web.tokens`,
     `tui.osc`, `tui.roles`, `swatches`) — los 14 temas existentes ya tienen
     paleta sin tocarlos;
  3. `complete()` rellena el resto con mezclas (`mix`) y neutros oscuros.

Regla de compatibilidad: lo HECHO A MANO GANA. Un bloque `tui`/`web.tokens`
explícito pisa al renderizado (clave por clave), y `stage_write` jamás pisa un
archivo que el usuario editó tras generarlo. Sin `palette` en el manifiesto,
tuitheme/hubtheme pintan EXACTAMENTE lo de siempre (nada cambia en pantalla).

ESCRITURA ATÓMICA (staging): `stage_write` renderiza todo a temporales y
reemplaza de un golpe; si algo falla, lo anterior queda intacto ("el TUI jamás
se rompe por un tema"). Hook opcional `theme-set` (estilo Omarchy): un script
del usuario en `<estado>/hooks/` que corre tras cambiar ui.theme, con timeout
y falla-suave (`run_theme_set_hook`).

stdlib puro (3.9+). Ninguna función pública levanta salvo `render()` (que es
la que DEBE fallar antes de escribir nada).
"""
import hashlib
import json
import os
import re
import subprocess
import sys
import threading

import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)

ROOT = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(ROOT, "templates", "theme")   # los tests lo parchan

_HEX_RX = re.compile(r"^#[0-9a-fA-F]{6}$")
_ID_RX = re.compile(r"^[a-z0-9][a-z0-9_-]{0,39}$")

# ── la paleta semántica ─────────────────────────────────────────────────────
SEMANTIC_KEYS = ("background", "foreground", "cursor", "accent", "accent_2",
                 "accent_hi", "muted", "faint", "surface", "border",
                 "success", "warning", "danger", "info")

# Derivación desde lo que un manifiesto YA declara (primera fuente válida gana).
# (bloque, clave) — bloque: tokens = web.tokens · osc = tui.osc · roles = tui.roles
_DERIVE = {
    "background": (("tokens", "bg"), ("osc", "bg")),
    "foreground": (("tokens", "text"), ("osc", "fg"), ("roles", "text")),
    "cursor":     (("osc", "cursor"),),
    "accent":     (("tokens", "accent"), ("roles", "accent"), ("swatch", 0)),
    "accent_2":   (("tokens", "accent-2"), ("roles", "mid"), ("swatch", 1)),
    "accent_hi":  (("tokens", "accent-hi"), ("roles", "hi")),
    "muted":      (("tokens", "dim"), ("roles", "dim")),
    "faint":      (("tokens", "faint"), ("roles", "grey")),
    "surface":    (("tokens", "surface"),),
    "border":     (("tokens", "border"), ("roles", "inactive_alt")),
    "success":    (("tokens", "green"), ("roles", "ok")),
    "warning":    (("tokens", "amber"),),
    "danger":     (("tokens", "red"), ("roles", "err")),
    "info":       (("tokens", "blue"),),
}

# Neutros de último recurso (oscuro, legible). El gris de background/foreground
# es el mismo del preset 'gray' de los agentes (agent_admin.COLOR_THEMES).
_BASE = {"background": "#121316", "foreground": "#e6e8ee", "accent": "#d2a64b",
         "success": "#8fc3a8", "warning": "#dcba84", "danger": "#dd7d88",
         "info": "#8fb8d8"}

# Motores: plantilla in-app conocida, o None = hook documentado SIN plantilla
# (formato no verificable → no se inventa; el motor solo recibe la paleta OSC
# de terminal, que sirve con cualquier CLI). Agregar un motor = poner aquí su
# archivo y dropear la plantilla en templates/theme/.
ENGINES = {
    "claude-code": "engine-claude-code.json.tpl",   # ~/.claude/themes/<n>.json (custom:<n>)
    "codex": None,          # sin formato de tema in-app documentado (2026-10)
    "antigravity": None,    # idem — no se inventa
}


def _hex(v):
    return v.lower() if isinstance(v, str) and _HEX_RX.match(v) else None


def _rgb(h):
    return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)


def mix(a, b, pct):
    """Mezcla lineal en RGB: `pct` (0..1) hacia `b`. mix(bg, fg, .15) = el bg
    un 15% hacia el texto (superficies, bordes). Hex → hex."""
    pct = max(0.0, min(1.0, float(pct)))
    ra, rb = _rgb(a), _rgb(b)
    return "#%02x%02x%02x" % tuple(int(round(x + (y - x) * pct)) for x, y in zip(ra, rb))


def _lum(h):
    def ch(c):
        c = c / 255.0
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(h)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def palette_from_manifest(m):
    """Paleta semántica PARCIAL de un manifiesto (solo hex válidos). El bloque
    `palette` manda; lo que falte se deriva de web.tokens / tui.osc / tui.roles
    / swatches. Acepta `accent-2` o `accent_2`. Jamás levanta → {}."""
    try:
        if not isinstance(m, dict):
            return {}
        web = m.get("web") if isinstance(m.get("web"), dict) else {}
        tui = m.get("tui") if isinstance(m.get("tui"), dict) else {}
        src = {"tokens": web.get("tokens") if isinstance(web.get("tokens"), dict) else {},
               "osc": tui.get("osc") if isinstance(tui.get("osc"), dict) else {},
               "roles": tui.get("roles") if isinstance(tui.get("roles"), dict) else {}}
        sw = m.get("swatches") if isinstance(m.get("swatches"), list) else []
        out = {}
        for key, chain in _DERIVE.items():
            for blk, k in chain:
                if blk == "swatch":
                    v = _hex(sw[k]) if len(sw) > k else None
                else:
                    v = _hex(src[blk].get(k))
                if v:
                    out[key] = v
                    break
        pal = m.get("palette") if isinstance(m.get("palette"), dict) else {}
        for k, v in pal.items():
            kk = str(k).replace("-", "_")
            if kk in SEMANTIC_KEYS and _hex(v):
                out[kk] = _hex(v)
        return out
    except Exception:
        return {}


def complete(p):
    """Paleta COMPLETA (todas las SEMANTIC_KEYS + `base`) a partir de una
    parcial: lo declarado se respeta; lo ausente se deriva por mezcla."""
    p = {k: _hex(v) for k, v in dict(p or {}).items() if _hex(v)}
    bg = p.get("background") or _BASE["background"]
    fg = p.get("foreground") or _BASE["foreground"]
    acc = p.get("accent") or _BASE["accent"]
    out = {"background": bg, "foreground": fg, "accent": acc,
           "cursor": p.get("cursor") or acc,
           "accent_2": p.get("accent_2") or mix(acc, fg, .35),
           "accent_hi": p.get("accent_hi") or mix(acc, fg, .40),
           "muted": p.get("muted") or mix(fg, bg, .35),
           "faint": p.get("faint") or mix(fg, bg, .55),
           "surface": p.get("surface") or mix(bg, fg, .04),
           "border": p.get("border") or mix(bg, fg, .15)}
    for k in ("success", "warning", "danger", "info"):
        out[k] = p.get(k) or _BASE[k]
    out["base"] = "light" if _lum(bg) > 0.5 else "dark"
    return out


def hub_palette(theme_id, themes_dir=None):
    """Paleta COMPLETA del tema del hub `theme_id` (themes/<id>/theme.json).
    None si el id es inválido o el manifiesto no existe/está roto."""
    if not (isinstance(theme_id, str) and _ID_RX.match(theme_id)):
        return None
    if themes_dir is None:
        try:
            import hubtheme
            themes_dir = hubtheme.THEMES_DIR
        except Exception:
            themes_dir = os.path.join(ROOT, "themes")
    try:
        with open(os.path.join(themes_dir, theme_id, "theme.json"), encoding="utf-8") as fh:
            m = json.load(fh)
    except Exception:
        return None
    if not isinstance(m, dict):
        return None
    return complete(palette_from_manifest(m))


# ── el motor de plantillas ──────────────────────────────────────────────────
# Sintaxis (mínima, sin lógica — una plantilla no ejecuta nada):
#   {{ clave }}                    valor de la paleta (o de `extra`, p.ej. name)
#   {{ mix a b 15% }}              a mezclado 15% hacia b (a/b = claves o #hex)
#   {{ alpha clave 0.12 }}         rgba(r,g,b,0.12) — para tokens web
_EXPR_RX = re.compile(r"\{\{\s*(.*?)\s*\}\}")


def _val(tok, ctx):
    if _HEX_RX.match(tok):
        return tok.lower()
    if tok in ctx:
        return ctx[tok]
    raise KeyError("clave desconocida en plantilla: %r" % tok)


def _eval(expr, ctx):
    parts = expr.split()
    if not parts:
        raise ValueError("expresión vacía")
    if parts[0] == "mix" and len(parts) == 4:
        pct = parts[3].rstrip("%")
        return mix(_val(parts[1], ctx), _val(parts[2], ctx), float(pct) / 100.0)
    if parts[0] == "alpha" and len(parts) == 3:
        a = float(parts[2])
        if not 0.0 <= a <= 1.0:
            raise ValueError("alpha fuera de rango: %r" % parts[2])
        r, g, b = _rgb(_val(parts[1], ctx))
        return "rgba(%d,%d,%d,%s)" % (r, g, b, parts[2])
    if len(parts) == 1:
        return _val(parts[0], ctx)
    raise ValueError("expresión desconocida: %r" % expr)


def template_path(target):
    """Ruta de la plantilla de `target` ('osc'|'tui'|'web'|'engine-<motor>')."""
    return os.path.join(TEMPLATES_DIR, "%s.json.tpl" % target)


def render(target, palette, **extra):
    """Renderiza la plantilla `target` con la paleta (completada) → dict.
    LEVANTA si la plantilla falta, usa una clave desconocida o no produce JSON
    válido: es a propósito — el error ocurre ANTES de escribir nada.
    `extra` agrega variables de texto (p.ej. name) — se escapan para JSON."""
    ctx = complete(palette)
    for k, v in extra.items():
        ctx[k] = json.dumps(str(v), ensure_ascii=False)[1:-1]
    with open(template_path(target), encoding="utf-8") as fh:
        text = fh.read()
    out = _EXPR_RX.sub(lambda mt: _eval(mt.group(1), ctx), text)
    data = json.loads(out)
    if not isinstance(data, dict):
        raise ValueError("la plantilla %s no produce un objeto JSON" % target)
    return data


def _safe(target, palette, **extra):
    try:
        return render(target, palette, **extra)
    except Exception:
        return None


def osc(palette):
    """{bg, fg, cursor} para theme.apply_colors. None si falla."""
    return _safe("osc", palette)


def tui(palette):
    """Bloque `tui` completo (roles/stars/fire/ember/off/osc). None si falla."""
    return _safe("tui", palette)


def web_tokens(palette):
    """`web.tokens` del dev panel. None si falla."""
    return _safe("web", palette)


def engine_supported(engine):
    """¿El motor tiene plantilla de tema in-app (y existe en disco)?"""
    tpl = ENGINES.get(engine or "")
    return bool(tpl) and os.path.isfile(os.path.join(TEMPLATES_DIR, tpl))


def engine_theme(engine, palette, name):
    """Tema in-app del `engine` para la paleta → dict, o None si el motor no
    tiene plantilla (codex/antigravity hoy) o el render falla."""
    if not engine_supported(engine):
        return None
    return _safe("engine-%s" % engine, palette, name=name)


def hub_engine_palette():
    """Paleta semántica del tema ELEGIDO en el hub (ui.theme) con el fondo
    elegido aparte (ui.background) ya aplicado. None si no se resuelve."""
    try:
        import tuitheme
        pal = hub_palette(tuitheme.resolve_id())
        if not pal:
            return None
        pal = dict(pal)
        try:
            import theme
            bg = theme.background_color(pal.get("background"))
        except Exception:
            bg = None
        if bg:
            pal["background"] = bg
        return pal
    except Exception:
        return None


def engine_theme_path(engine, name, home=None):
    """Dónde lee el motor su tema in-app (hoy solo claude-code), o None."""
    if engine != "claude-code" or not _ID_RX.match(str(name or "")):
        return None
    return os.path.join(home or os.path.expanduser("~"), ".claude", "themes",
                        "%s.json" % name)


def sync_engine_theme(engine, name, display=None, brain=None, home=None):
    """El tema DENTRO del motor sigue al tema del hub (el socio 2026-10-12: el
    tema y el fondo del hub pintan TODO, también la sesión de cada agente).
    Regenera <home>/.claude/themes/<name>.json desde hub_engine_palette() y,
    si el settings.local.json del cerebro no nombra ningún tema, le pone
    custom:<name>. Lo HECHO A MANO GANA: un tema editado a mano no se pisa
    (stage_write) y un `theme` que el socio ya puso en settings no se toca.
    Devuelve el resultado de stage_write, o None si no aplica. Jamás levanta."""
    try:
        dst = engine_theme_path(engine, name, home)
        if not dst or not engine_supported(engine):
            return None
        pal = hub_engine_palette()
        data = engine_theme(engine, pal, display or str(name).capitalize()) if pal else None
        if data is None:
            return None
        res = stage_write([(dst, json_text(data), True)], home)
        if brain:
            sp = os.path.join(brain, ".claude", "settings.local.json")
            try:
                with open(sp, encoding="utf-8") as fh:
                    st = json.load(fh)
                if isinstance(st, dict) and not st.get("theme"):
                    st["theme"] = "custom:%s" % name
                    stage_write([(sp, json_text(st), False)], home)
            except Exception:
                pass                                 # sin settings: el install lo crea
        return res
    except Exception:
        return None


def overlay(rendered, explicit):
    """`explicit` (hecho a mano) sobre `rendered`, un nivel de dicts anidados
    (roles/stars/glyphs/osc se mezclan clave a clave). Lo explícito gana."""
    out = dict(rendered or {})
    for k, v in (explicit or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            merged = dict(out[k])
            merged.update(v)
            out[k] = merged
        else:
            out[k] = v
    return out


# ── escritura atómica + "lo hecho a mano gana" ──────────────────────────────
# Registro de lo que GENERAMOS: <estado>/theme-render.json = {ruta: sha256}.
# Un archivo existente cuyo hash ya no coincide con el registrado = el usuario
# lo editó → no se pisa. Sin registro (archivo de una versión anterior, que lo
# escribía siempre) = se presume generado: se reescribe como antes y desde ahí
# queda registrado. El registro vive en el perfil, NUNCA junto al archivo
# (~/.claude/themes/ es de Claude Code: no le dejamos basura que pueda leer).
def _record_path(home=None):
    return os.path.join(_paths.state_dir(home), "theme-render.json")


def _sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_record(home=None):
    try:
        with open(_record_path(home), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _key(path):
    return os.path.normcase(os.path.abspath(path))


def is_handmade(path, home=None):
    """True si `path` existe y fue editado después de que lo generamos."""
    try:
        with open(path, encoding="utf-8") as fh:
            cur = fh.read()
    except Exception:
        return False
    rec = _read_record(home).get(_key(path))
    return bool(rec) and rec != _sha(cur)


def json_text(data):
    """Serialización canónica (la misma de agent_admin._atomic_write_json)."""
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def stage_write(files, home=None):
    """Escribe `files` = [(ruta, texto, respetar_hecho_a_mano), …] en bloque:
      1. descarta los hechos a mano (si respetar=True) y los idénticos;
      2. escribe TODOS a temporales en su mismo dir (staging);
      3. si alguno falló → borra temporales, nada cambia;
      4. os.replace de cada uno; si un replace falla, restaura los ya
         reemplazados desde su contenido previo.
    Devuelve {"ok", "written", "kept" (hecho a mano), "error"}. Jamás levanta."""
    res = {"ok": True, "written": [], "kept": [], "error": ""}
    plan = []
    for path, text, respect in files:
        try:
            if respect and is_handmade(path, home):
                res["kept"].append(path)
                continue
            prev = None
            if os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    prev = fh.read()
                if prev == text:
                    plan.append((path, text, prev, None, respect))   # idéntico: solo registrar
                    continue
            plan.append((path, text, prev, path + ".tmp-theme-%d" % os.getpid(), respect))
        except Exception as e:
            res.update(ok=False, error="%s: %s" % (path, e))
            return res
    staged = []
    try:
        for path, text, prev, tmp, _r in plan:
            if tmp is None:
                continue
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.write(text)
            staged.append(tmp)
    except Exception as e:
        for t in staged:
            try:
                os.remove(t)
            except OSError:
                pass
        res.update(ok=False, error="staging: %s" % e)
        return res
    done = []
    try:
        for path, text, prev, tmp, _r in plan:
            if tmp is None:
                continue
            os.replace(tmp, path)
            done.append((path, prev))
    except Exception as e:
        for path, prev in reversed(done):            # rollback: lo anterior vuelve
            try:
                if prev is None:
                    os.remove(path)
                else:
                    with open(path, "w", encoding="utf-8") as fh:
                        fh.write(prev)
            except Exception:
                pass
        for _p, _t, _pr, tmp, _r in plan:
            if tmp:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
        res.update(ok=False, error="replace: %s" % e)
        return res
    res["written"] = [p for p, _t, _pr, tmp, _r in plan if tmp]
    mark_generated([(p, t) for p, t, _pr, _tmp, r in plan if r], home)
    return res


def mark_generated(entries, home=None):
    """Registra [(ruta, texto)] como GENERADOS por nosotros (para que una
    edición posterior del usuario se detecte y se respete). Falla-suave: sin
    registro, el archivo simplemente se presume generado (lo de siempre)."""
    if not entries:
        return
    try:
        rec = _read_record(home)
        for path, text in entries:
            rec[_key(path)] = _sha(text)
        rp = _record_path(home)
        os.makedirs(os.path.dirname(rp), exist_ok=True)
        tmp = rp + ".tmp-%d" % os.getpid()
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, ensure_ascii=False, indent=1, sort_keys=True)
        os.replace(tmp, rp)
    except Exception:
        pass


# ── hook theme-set (opcional, del usuario) ──────────────────────────────────
HOOK_TIMEOUT = 10   # s — el hook jamás retiene al hub más que esto


def hook_path(home=None):
    """Script del usuario que corre tras cambiar ui.theme, o None. Busca en
    <estado>/hooks/: theme-set.py (cualquier OS, con este Python) o
    theme-set (POSIX, ejecutable) / theme-set.cmd|.bat (Windows)."""
    d = os.path.join(_paths.state_dir(home), "hooks")
    names = ["theme-set.py"] + (["theme-set.cmd", "theme-set.bat"]
                                if os.name == "nt" else ["theme-set"])
    for n in names:
        p = os.path.join(d, n)
        if os.path.isfile(p) and (n.endswith((".py", ".cmd", ".bat"))
                                  or os.access(p, os.X_OK)):
            return p
    return None


def run_theme_set_hook(theme_id, home=None):
    """Lanza el hook theme-set con el id nuevo como argumento, SIN bloquear:
    un hilo daemon lo mata al vencer HOOK_TIMEOUT. Falla-suave absoluta;
    kill-switch: env WORKSPACE_NO_THEME_HOOK=1. Devuelve el Popen o None."""
    try:
        if os.environ.get("WORKSPACE_NO_THEME_HOOK"):
            return None
        hp = hook_path(home)
        if not hp:
            return None
        cmd = ([sys.executable, hp] if hp.endswith(".py") else [hp]) + [str(theme_id)]
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)

        def _reap():
            try:
                proc.wait(timeout=HOOK_TIMEOUT)
            except Exception:
                try:
                    if os.name == "nt":      # un .cmd lanza hijos: matar el árbol entero
                        subprocess.call(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    else:
                        proc.kill()
                except Exception:
                    pass
        threading.Thread(target=_reap, daemon=True).start()
        return proc
    except Exception:
        return None


# ── compat: presets de prueba que ya no viajan en themes.json ───────────────
# "prueba", "midas", "midas2" eran agentes de prueba del equipo que se colaron
# al themes.json del repo antes de que los temas de agente fueran per-máquina
# (6ad4e74). Salieron del repo; si una máquina tiene un agente con ese nombre,
# la migración (ver themes/README.md) copia su paleta a themes.local.json.
LEGACY_PRESETS = {
    "prueba": {"bg": "#121316", "fg": "#e6e8ee"},
    "midas": {"bg": "#121316", "fg": "#e6e8ee"},
    "midas2": {"bg": "#121316", "fg": "#e6e8ee"},
}


def legacy_presets_needed(agent_names, home=None):
    """Nombres de LEGACY_PRESETS que son agentes de esta máquina y aún no
    tienen entrada en themes.local.json (lo que la migración debe adoptar)."""
    try:
        with open(os.path.join(_paths.state_dir(home), "themes.local.json"),
                  encoding="utf-8") as fh:
            local = json.load(fh)
        if not isinstance(local, dict):
            local = {}
    except Exception:
        local = {}
    names = {str(n).strip().lower() for n in (agent_names or ())}
    return sorted(n for n in LEGACY_PRESETS if n in names and n not in local)


def adopt_legacy_presets(agent_names, home=None):
    """Idempotente: añade a themes.local.json la paleta legada de cada agente
    devuelto por legacy_presets_needed (sin tocar ninguna otra entrada).
    Devuelve la lista adoptada ([] si no había nada que hacer)."""
    need = legacy_presets_needed(agent_names, home)
    if not need:
        return []
    path = os.path.join(_paths.state_dir(home), "themes.local.json")
    try:
        with open(path, encoding="utf-8") as fh:
            local = json.load(fh)
        if not isinstance(local, dict):
            return []                                # corrupto/raro: no se pisa
    except FileNotFoundError:
        local = {}
    except Exception:
        return []
    for n in need:
        local[n] = dict(LEGACY_PRESETS[n])
    r = stage_write([(path, json_text(local), False)], home)
    return need if r["ok"] else []


if __name__ == "__main__":
    # demo: `python3 theme_render.py <tema> [osc|tui|web|engine-claude-code]`
    tid = sys.argv[1] if len(sys.argv) > 1 else "bruma"
    tgt = sys.argv[2] if len(sys.argv) > 2 else None
    pal = hub_palette(tid)
    if pal is None:
        print("tema desconocido: %s" % tid)
        sys.exit(1)
    data = render(tgt, pal, name=tid.capitalize()) if tgt else pal
    print(json.dumps(data, ensure_ascii=False, indent=2))
