#!/usr/bin/env python3
"""WORKSPACE · hublayout — motor de LAYOUTS del hub (front.py).

Segundo eje de apariencia, INDEPENDIENTE del tema: el TEMA (hubtheme/tuitheme,
ui.theme) decide paleta y glifos; el LAYOUT (este módulo, ui.layout) decide la
ESTRUCTURA del hub — qué se dibuja y dónde. Cualquier layout combina con
cualquier tema: los renderers pintan SOLO con la paleta/glifos del tema activo
(P de tuitheme.palette()) — aquí no se hardcodea ni un color.

REGISTRO: `REGISTRY` (abajo) — cada layout es una entrada {id, label, render}.
`clasico` es el recinto centrado de SIEMPRE y su render vive en
front.py (render=None ⇒ front usa su camino nativo, intacto: paridad por
construcción — nadie cambia de look salvo que elija otro layout).

SELECCIÓN (precedencia, espejo de ui.theme): env `WORKSPACE_LAYOUT` >
settings `ui.layout` > default `dia`. Id desconocido → dia
(falla-suave absoluta; el hub jamás se rompe por un layout).

CONTRATO de un renderer:
    render(data, view, P, w) -> list[str]
  · data (estable en la sesión): agents [{name, display, tagline, color,
    active, task, state}] · opts [(token, label)] · hb (heartbeat.state() o
    None) · hb_modes · hb_tags · version · version_text · motor.
  · view (estado vivo de la selección): focus ('dioses'|'tools'|'latido') ·
    gsel · asel · hb_mode · hb_focus · msg · hb_msg · h (ALTO real de la
    terminal, opcional — 0/ausente ⇒ el layout usa su altura natural; un
    layout puede usarlo para LLENAR la pantalla; para un (data, w, h) fijo
    la altura sigue sin depender de la selección).
  · P: paleta del TEMA (tuitheme.palette() o el fallback dorado de front).
  · w: ancho REAL de la terminal — el renderer se adapta (reflow/colapso) y
    NINGUNA línea excede w-1 columnas visibles (desbordar rompe el redraw).
  · El nº de líneas NO depende de la selección (mismo (data, w) ⇒ mismo
    len()): front redibuja el bloque con cursor-up, la altura debe ser
    estable. Las filas de aviso (msg/hb_msg) van SIEMPRE reservadas.
  · Windows-safe: nada del rango U+2600–U+27BF ni emojis en arte fijo — solo
    box-drawing/geometría (<0x2600) y los glifos que ya provee el tema.

stdlib puro (3.9+), falla-suave absoluta (sin settings → default).
"""
import datetime
import json
import os
import re
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
DEFAULT_ID = "dia"
MIN_W = 40          # ancho mínimo de los layouts alternativos (clasico usa el suyo)

# Medición de ancho COMPARTIDA (_width.py): escapes ANSI completos (CSI/OSC/
# ESC de 2 bytes -- medir solo `\x1b[...m` dejaba pasar secuencias que CUENTAN
# como ancho y el borde derecho "bailaba" fila a fila), saneo NFC/zero-width/
# controles y ancho por caracter Hangul-safe. Los alias conservan los nombres
# historicos de este modulo (los usan sus tests y docstrings).
from _width import ANSI as _ANSI, sane as _sane, eaw as _cw   # noqa: E402

_RESET = "\x1b[0m"


# -- helpers de texto ANSI (ancho VISUAL, no len) ----------------------------
def _plain(s):
    return _ANSI.sub("", str(s))


def vis(s):
    """Ancho visual de una línea ANSI (ver _sane/_cw — mide lo que la
    terminal pinta, no len()). Los escapes se quitan ANTES de sanear (un
    BEL que termina un OSC no es un control del texto)."""
    return sum(_cw(c) for c in _sane(_plain(s)))


def clip(s, w):
    """Recorta una línea ANSI a ≤w columnas visibles preservando los códigos
    de color (y cerrando con reset si el recorte dejó códigos fuera — que el
    color no sangre al borde/padding). Sanea la línea (_sane) SIEMPRE: todo
    lo impreso pasa por clip/pad y sale medible."""
    if w <= 0:
        return ""
    s = _sane(s)
    if vis(s) <= w:
        return s
    out, used, i = [], 0, 0
    while i < len(s) and used < w - 1:
        m = _ANSI.match(s, i)
        if m:
            out.append(m.group(0))
            i = m.end()
            continue
        c = s[i]
        cw = _cw(c)
        if used + cw > w - 1:
            break
        out.append(c)
        used += cw
        i += 1
    tail = "…" + (_RESET if _ANSI.search(s, i) else "")
    return "".join(out) + tail


def pad(s, w):
    """Rellena a EXACTAMENTE w columnas visibles (clip si excede)."""
    s = _sane(s)
    s = clip(s, w) if vis(s) > w else s
    return s + " " * max(0, w - vis(s))


def cols(P):
    """Paleta segura para un renderer: dict con las claves que TODO layout
    puede usar, con fallback benigno si el namespace no trae alguna.
    Idempotente: un dict ya normalizado pasa tal cual (los helpers públicos
    aceptan paleta o dict)."""
    if isinstance(P, dict):
        return P

    def g(a, d=""):
        return getattr(P, a, d) or ""
    gl = getattr(P, "GLYPHS", None) or {}
    box = gl.get("box") or "╭╮╰╯│─"
    return {"B": g("B"), "B2": g("B2"), "C": g("C"), "WH": g("WH"),
            "DIM": g("DIM"), "DK": g("DK"), "GREY": g("GREY"),
            "R": g("R"), "BO": g("BO"),
            "INACTIVE": g("INACTIVE", g("DIM")), "ERR": g("ERR", g("B")),
            # semánticos del tema (verde/rojo) para puntos de estado, ✓limpio
            # y el log de actividad — fallback benigno a los roles básicos
            "OK": g("OK", g("C")), "BAD": g("BAD", g("ERR", g("B"))),
            # acento APAGADO del tema (P.OFF — violeta/magenta tenue en
            # cyberpunk, oro apagado en olympo): bordes tenues con color de
            # tema, NO gris (feedback cockpit-v7 2026-07-04)
            "OFF": g("OFF", g("DK")),
            # tema MONOCROMO declarado (o terminal sin color): quien pinte
            # color propio fuera de los roles debe ceder — ver _agent_ink.
            "MONO": bool(getattr(P, "MONO", False)),
            "PTR": gl.get("pointer") or "❯",
            "BL": gl.get("bracket_l") or "❮",
            "BR": gl.get("bracket_r") or "❯",
            "SEP": gl.get("sep") or "─", "BOX": box,
            # iconos de los widgets (rama git, limpio, latido, bus) — vienen
            # del TEMA (tuitheme los declara y un tema Windows los overridea)
            "BRANCH": gl.get("branch") or "⎇", "CHECK": gl.get("check") or "✓",
            "HEART": gl.get("heart") or "♥", "MAIL": gl.get("mail") or "✉",
            "WCOL": _wcol6(P)}


def _wcol6(P):
    """Gradiente de 6 colores del wordmark del TEMA (P.WCOL); si el
    namespace no lo trae (fallback de front sin tuitheme) → gradiente con
    los roles básicos (B2→B→C). Siempre len 6."""
    try:
        wc = list(getattr(P, "WCOL", None) or [])
        if len(wc) == 6:
            return wc
    except Exception:
        pass
    def g(a):
        return getattr(P, a, "") or ""
    return [g("B2"), g("B2"), g("B"), g("B"), g("C"), g("C")]


# ── fuentes de sistema BARATAS para el cockpit (memo con TTL corto) ─────────
# Solo datos REALES con fuente local: worktrees (git) y bus (messages.py).
# Falla-suave ABSOLUTA → None y el layout OMITE el dato (nada inventado).
# TTL corto (no memo eterno): un hub abierto horas mostraría git/bus RANCIOS.
# Sigue sin haber subprocess por keypress: el refresh cuesta 1 comando cada
# _SYS_TTL segundos. Un valor SEMBRADO a mano (tests) no trae timestamp y se
# respeta tal cual — mismo contrato de siempre.
_SYS_CACHE = {}
_SYS_CACHE_TS = {}
_SYS_TTL = 8.0            # segundos


def _sys_fresh(key):
    """True si _SYS_CACHE[key] sigue vigente (sembrado sin timestamp ⇒ sí)."""
    if key not in _SYS_CACHE:
        return False
    ts = _SYS_CACHE_TS.get(key)
    return ts is None or (time.monotonic() - ts) <= _SYS_TTL


def _worktrees():
    """Nº de worktrees LIGADOS del repo del harness (git worktree list,
    sin contar el checkout principal). None si no hay git/repo — el
    caller omite el dato. Memo con TTL (no subprocess por keypress)."""
    if not _sys_fresh("wt"):
        val = None
        try:
            import subprocess
            r = subprocess.run(["git", "-C", ROOT, "worktree", "list",
                                "--porcelain"], capture_output=True,
                               text=True, encoding="utf-8",
                               errors="replace", timeout=4)
            if r.returncode == 0:
                n = sum(1 for ln in (r.stdout or "").splitlines()
                        if ln.startswith("worktree "))
                val = max(0, n - 1) if n else None
        except Exception:
            val = None
        _SYS_CACHE["wt"] = val
        _SYS_CACHE_TS["wt"] = time.monotonic()
    return _SYS_CACHE["wt"]


def _bus_pending():
    """Mensajes PENDIENTES en el bus (messages.py, msgs/ de los cerebros
    registrados). None si el bus no está / sin cerebros — se omite.
    Guarda también el desglose por destinatario (_SYS_CACHE['bus_by'], del
    MISMO escaneo — gratis). Memo con TTL; solo lectura."""
    if not _sys_fresh("bus"):
        val, by = None, {}
        try:
            import messages
            brains = messages.registered_brains()
            if brains:
                msgs = messages.all_messages(brains=brains,
                                             statuses=("pending",))
                val = len(msgs)
                for m in msgs:
                    to = m.get("to") or "?"
                    by[to] = by.get(to, 0) + 1
        except Exception:
            val, by = None, {}
        _SYS_CACHE["bus"] = val
        _SYS_CACHE["bus_by"] = by
        _SYS_CACHE_TS["bus"] = time.monotonic()
    return _SYS_CACHE["bus"]


def _git_info():
    """Estado git REAL del repo del harness con UN solo comando (`git status
    --porcelain -b`): rama, commits ahead/behind del upstream y working tree
    limpio/sucio. None si no hay git/repo — el caller OMITE el widget (nada
    inventado). Memo con TTL (no subprocess por keypress)."""
    if not _sys_fresh("git"):
        info = None
        try:
            import subprocess
            r = subprocess.run(["git", "-C", ROOT, "status", "--porcelain",
                                "-b"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=4)
            lines = (r.stdout or "").splitlines()
            if r.returncode == 0 and lines and lines[0].startswith("## "):
                head = lines[0][3:]
                branch = head.split("...", 1)[0].strip()
                if branch.startswith("No commits yet on "):
                    branch = branch[len("No commits yet on "):]
                if branch == "HEAD (no branch)":
                    branch = "(detached)"
                m = re.search(r"\[ahead (\d+)", head)
                ahead = int(m.group(1)) if m else 0
                m = re.search(r"behind (\d+)", head)
                behind = int(m.group(1)) if m else 0
                # del MISMO comando salen dos datos más (gratis): cuántos
                # archivos trae el working tree («± 14» dice más que
                # «sucio») y si la rama TIENE upstream (sin él, «al día
                # con origin» sería un invento). Los consumidores viejos
                # (branch_widget) siguen leyendo `dirty` igual.
                cambios = sum(1 for ln in lines[1:] if ln.strip())
                info = {"branch": branch, "ahead": ahead, "behind": behind,
                        "dirty": bool(cambios), "changes": cambios,
                        "upstream": "..." in head}
        except Exception:
            info = None
        _SYS_CACHE["git"] = info
        _SYS_CACHE_TS["git"] = time.monotonic()
    return _SYS_CACHE["git"]


def _git_log(n=12):
    """Últimos n commits REALES del repo del harness (`git log --pretty`):
    [{'h' hash corto, 'ts' epoch, 's' asunto}], más reciente primero. None
    si no hay git/repo — el caller omite. Memo con TTL (cero subprocess por
    keypress; alimenta la sección ACTIVIDAD)."""
    if not _sys_fresh("gitlog"):
        val = None
        try:
            import subprocess
            r = subprocess.run(["git", "-C", ROOT, "log", "-n", str(n),
                                "--pretty=%h%x1f%ct%x1f%s"],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=4)
            if r.returncode == 0:
                out = []
                for ln in (r.stdout or "").splitlines():
                    p = ln.split("\x1f")
                    if len(p) == 3:
                        try:
                            ts = float(p[1])
                        except ValueError:
                            ts = 0.0
                        out.append({"h": p[0], "ts": ts, "s": p[2]})
                val = out or None
        except Exception:
            val = None
        _SYS_CACHE["gitlog"] = val
        _SYS_CACHE_TS["gitlog"] = time.monotonic()
    return _SYS_CACHE["gitlog"]


def _git_hours(hours=12):
    """Commits REALES del harness por HORA en las últimas `hours` horas
    (`git log --since`): {'counts': [int × hours, viejo→nuevo], 'peak':
    epoch del commit más reciente de la hora pico o None}. Repo sin
    commits recientes → counts en cero (dato real, no invento); sin
    git/repo → None y el caller OMITE el widget. Memo con TTL (alimenta
    el sparkline del MONITOR)."""
    if not _sys_fresh("githours"):
        val = None
        try:
            import subprocess
            r = subprocess.run(["git", "-C", ROOT, "log",
                                "--since=%d.hours" % hours, "--pretty=%ct"],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=4)
            if r.returncode == 0:
                now = time.time()
                counts = [0] * hours
                last = [0.0] * hours              # ts más reciente por hora
                for tok in (r.stdout or "").split():
                    try:
                        ts = float(tok)
                    except ValueError:
                        continue
                    age = int((now - ts) // 3600)
                    if 0 <= age < hours:
                        i = hours - 1 - age
                        counts[i] += 1
                        last[i] = max(last[i], ts)
                peak = None
                if any(counts):
                    i = max(range(hours), key=lambda j: counts[j])
                    peak = last[i] or None
                val = {"counts": counts, "peak": peak}
        except Exception:
            val = None
        _SYS_CACHE["githours"] = val
        _SYS_CACHE_TS["githours"] = time.monotonic()
    return _SYS_CACHE["githours"]


def _branches():
    """Nº de ramas LOCALES del repo del harness (`git for-each-ref
    refs/heads`). None sin git/repo — el caller omite el tile. Memo TTL."""
    if not _sys_fresh("branches"):
        val = None
        try:
            import subprocess
            r = subprocess.run(["git", "-C", ROOT, "for-each-ref",
                                "--format=%(refname:short)", "refs/heads"],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=4)
            if r.returncode == 0:
                val = sum(1 for ln in (r.stdout or "").splitlines()
                          if ln.strip())
        except Exception:
            val = None
        _SYS_CACHE["branches"] = val
        _SYS_CACHE_TS["branches"] = time.monotonic()
    return _SYS_CACHE["branches"]


def _git_ramas(n=8):
    """Ramas LOCALES del repo del harness por commit más reciente, con UN
    comando (`git for-each-ref --sort=-committerdate`): {'total': N,
    'ramas': [{'name','cur','ts','ahead','behind'}, …]} — `ts` epoch del
    último commit, ahead/behind vs SU upstream (0 sin upstream). None sin
    git/repo — el caller OMITE la lista (nada inventado). Memo con TTL:
    un subprocess cada _SYS_TTL, JAMÁS por redraw (la lección del mapa).
    Alimenta el panel RAMAS del layout `dia`."""
    if not _sys_fresh("ramas"):
        val = None
        try:
            import subprocess
            r = subprocess.run(
                ["git", "-C", ROOT, "for-each-ref", "refs/heads",
                 "--sort=-committerdate",
                 "--format=%(HEAD)%1f%(refname:short)%1f"
                 "%(committerdate:unix)%1f%(upstream:track)"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=4)
            if r.returncode == 0:
                ramas = []
                for ln in (r.stdout or "").splitlines():
                    p = ln.split("\x1f")
                    if len(p) != 4 or not p[1]:
                        continue
                    try:
                        ts = float(p[2])
                    except ValueError:
                        ts = 0.0
                    m = re.search(r"ahead (\d+)", p[3])
                    ah = int(m.group(1)) if m else 0
                    m = re.search(r"behind (\d+)", p[3])
                    bh = int(m.group(1)) if m else 0
                    ramas.append({"name": p[1], "cur": p[0] == "*",
                                  "ts": ts, "ahead": ah, "behind": bh})
                if ramas:
                    val = {"total": len(ramas), "ramas": ramas[:max(1, n)]}
        except Exception:
            val = None
        _SYS_CACHE["ramas"] = val
        _SYS_CACHE_TS["ramas"] = time.monotonic()
    return _SYS_CACHE["ramas"]


def _iso_epoch(ts):
    """Epoch de un ts ISO `YYYY-MM-DDTHH:MM:SS` (frontmatter del bus).
    None si no parsea — el caller cae al mtime del archivo."""
    try:
        return time.mktime(time.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S"))
    except Exception:
        return None


def _bus_recent(n=12):
    """Últimos n mensajes del bus (messages.py, CUALQUIER status — es un log,
    no un inbox): [{'ts' epoch, 'from', 'to', 'type', 'subject', 'status'}],
    más reciente primero. None si el bus no está / sin cerebros. Memo con
    TTL; solo lectura (alimenta la sección ACTIVIDAD)."""
    if not _sys_fresh("busrec"):
        val = None
        try:
            import messages
            brains = messages.registered_brains()
            if brains:
                out = []
                for m in messages.all_messages(brains=brains, limit=n):
                    out.append({"ts": _iso_epoch(m.get("ts"))
                                or float(m.get("mtime") or 0),
                                "from": m.get("from") or "?",
                                "to": m.get("to") or "?",
                                "type": m.get("type") or "",
                                "subject": m.get("subject") or "",
                                "status": m.get("status") or ""})
                val = out or None
        except Exception:
            val = None
        _SYS_CACHE["busrec"] = val
        _SYS_CACHE_TS["busrec"] = time.monotonic()
    return _SYS_CACHE["busrec"]


def hb_brief(data, hb_mode=None):
    """'latido auto · cola 0 · uso 5h 5%' — resumen plano del heartbeat para
    cabeceras/statuslines. '' si no hay latido. Solo ASCII + '·' (Win-safe)."""
    hb = data.get("hb")
    if not hb:
        return ""
    try:
        mode = hb_mode or hb.get("mode") or "?"
        b = hb.get("budget") or {}
        pct = b.get("pct")
        uso = "?" if pct is None else "%d%%" % round(pct)
        out = "latido %s · cola %s · uso 5h %s" % (mode, hb.get("count", 0), uso)
        if b.get("ok") is not True:
            out += " · presupuesto en pausa"
        return out
    except Exception:
        return ""


def radio_row(data, view, K):
    """Fila del radio-group del LATIDO — la MISMA semántica que el recinto
    clásico: (o) = modo APLICADO · brackets del tema = opción ENFOCADA
    (cursor; Enter la aplica) · resto apagado. '' si no hay latido."""
    if not data.get("hb"):
        return ""
    focus = view.get("focus") == "latido"
    parts = []
    for j, m in enumerate(data.get("hb_modes") or ("auto", "manual", "off")):
        sel = (m == view.get("hb_mode"))
        radio = "(o)" if sel else "( )"
        if focus and j == view.get("hb_focus", 0):
            parts.append("%s%s%s %s%s%s %s%s%s %s%s" % (
                K["C"], K["BO"], K["BL"], K["R"],
                (K["C"] + K["BO"]) if sel else K["DIM"], radio + K["R"],
                K["BO"] + K["WH"], m, K["R"], K["C"] + K["BO"] + K["BR"], K["R"]))
        elif sel:
            parts.append("%s%s %s %s %s" % (K["C"], K["BO"], radio, m, K["R"]))
        else:
            parts.append("%s %s %s %s" % (K["DIM"], radio, m, K["R"]))
    return "  ".join(parts)


def radio_row_compact(data, view, K):
    """radio_row APRETADO para columnas angostas (SISTEMA del vsplit):
    `(o)auto ( )manual ( )off` — MISMA semántica ((o) aplicado · brackets
    del tema = opción enfocada), sin aire interno. '' si no hay latido."""
    K = cols(K)
    if not data.get("hb"):
        return ""
    focus = view.get("focus") == "latido"
    parts = []
    for j, m in enumerate(data.get("hb_modes") or ("auto", "manual", "off")):
        sel = (m == view.get("hb_mode"))
        radio = "(o)" if sel else "( )"
        rcol = (K["C"] + K["BO"]) if sel else K["DIM"]
        cell = "%s%s%s%s%s%s" % (rcol, radio, K["R"],
                                 (K["WH"] + K["BO"]) if sel else K["DIM"],
                                 m, K["R"])
        if focus and j == view.get("hb_focus", 0):
            cell = "%s%s%s%s%s%s%s" % (K["C"] + K["BO"], K["BL"], K["R"],
                                       cell, K["C"] + K["BO"], K["BR"],
                                       K["R"])
        parts.append(cell)
    return " ".join(parts)


def agent_status(a, K, selected=False):
    """(glifo, color, texto) del estado vivo de un agente para las listas:
    ● tarea en curso (now.json) · ○ idle · '· pronto' planeado."""
    if not a.get("active"):
        return "·", K["DK"], "pronto"
    task = (a.get("task") or "").strip()
    if task:
        return "●", (K["C"] if selected else K["B"]), task
    return "○", K["GREY"], (a.get("tagline") or "idle")


def action_cell(j, lbl, view, K, key=""):
    """Una acción estilizada: la seleccionada con brackets del tema (foco en
    tools ⇒ dorado bold), el resto apagado. Ancho visual FIJO por acción
    (len(lbl)+4, +2 con tecla) — la selección no cambia la geometría de la
    fila. `key`: tecla de SALTO directo pintada DENTRO de la celda («5 Tono»)
    — la tecla siempre junto a su opción."""
    kd = ("%s%s %s" % (K["DIM"], key, K["R"])) if key else ""
    if j == view.get("asel", 0) and view.get("focus") == "tools":
        return "%s%s%s %s%s%s%s%s%s %s%s" % (
            K["C"], K["BO"], K["BL"], K["R"], kd, K["BO"], K["WH"], lbl,
            K["R"], K["C"] + K["BO"] + K["BR"], K["R"])
    if j == view.get("asel", 0):
        return "%s%s %s%s%s%s%s%s %s%s" % (
            K["C"], K["BL"], K["R"] + kd, K["BO"] + K["WH"], lbl, K["R"],
            K["C"], "", K["BR"], K["R"])
    kd = ("%s%s %s" % (K["DK"], key, K["R"])) if key else ""
    return "%s %s%s%s%s" % (K["INACTIVE"], K["R"] + kd + K["INACTIVE"]
                            if key else "", lbl, " ", K["R"])


def action_rows(data, view, K, w, indent="  ", gap="   "):
    """Fila(s) de ACCIONES con reflow ESTABLE: el corte de línea se calcula
    con anchos planos (len(lbl)+4 (+2 con tecla de salto), independientes de
    la selección) — así la altura no cambia al mover el cursor, solo con
    (data, w). Con data["keys"] cada celda pinta su tecla de salto."""
    opts = list(data.get("opts") or ())
    jk = (data.get("keys") or {}).get("opts") or {}
    rows, cur, curw = [], [], 0
    avail = max(16, w - 1 - vis(indent))
    for j, (_tok, lbl) in enumerate(opts):
        cellw = vis(lbl) + 4 + (2 if jk.get(j) else 0)   # ' lbl ' + brackets
        extra = (len(gap) if cur else 0)
        if cur and curw + extra + cellw > avail:
            rows.append(cur)
            cur, curw = [], 0
        cur.append(j)
        curw += cellw + extra
    if cur:
        rows.append(cur)
    out = []
    for row in rows:
        cells = [action_cell(j, opts[j][1], view, K, key=jk.get(j, ""))
                 for j in row]
        out.append(clip(indent + gap.join(cells), w - 1))
    return out or [""]


HINT = "↑↓ sección · ◄► elige · Enter entra · q terminal"
HINT_PAIRS = (("↑↓", "sección"), ("◄►", "elige"), ("Enter", "entra"),
              ("q", "terminal"))


# ── HINTS DE TECLADO COMPARTIDOS (cabecera + pie de cada pantalla) ──────────
# Pedido del socio 2026-10-04: los atajos no pueden vivir SOLO en una línea
# tenue al pie. Arriba, junto al nombre de la pantalla, van los 3-4 CLAVE
# (tecla en acento, acción legible) y el pie conserva la lista completa con
# el mismo lenguaje visual. UNA fuente de verdad por pantalla: la MISMA
# tupla de pares ((tecla, acción), …) alimenta cabecera (recortada a lo
# esencial) y pie (completa) — una pantalla nueva hereda el patrón llamando
# screen_header()/foot_hints(), no copiando render.

def keyline(K, items, w, txt_col=None):
    """`tecla acción · tecla acción` en UNA línea que SIEMPRE cabe en w:
    tecla en acento+bold, acción en texto tenue, separador `·` apagado.
    Si no cabe entera cede pares del final conservando el PRIMERO (cómo
    moverse) y el ÚLTIMO (cómo salir) — un atajo recortado a media palabra
    no enseña nada. "" si ni un par cabe. `items` = ((tecla, acción), …)."""
    K = cols(K)
    tc = txt_col if txt_col is not None else K["DIM"]
    sep = " %s·%s " % (K["DK"], K["R"])
    pares = [(str(a), str(b)) for a, b in items]
    while pares:
        line = sep.join("%s%s%s%s%s%s" % (K["C"] + K["BO"], a, K["R"],
                                          (" " + tc) if b else "", b,
                                          K["R"] if b else "")
                        for a, b in pares)
        if vis(line) <= w:
            return line
        pares.pop(len(pares) - 2 if len(pares) > 1 else 0)
    return ""


def top_hints(K, items, w, h=0, max_pairs=4, min_h=30):
    """La zona de atajos CLAVE de la CABECERA — centrada bajo el subtítulo
    de la pantalla, tecla en acento y acción en gris LEGIBLE (no DIM: esta
    línea nació para VERSE al instante). Recorta a los primeros pares + el
    último (salir). [] cuando debe ceder (alto < min_h o ancho sin sitio):
    es redundancia del pie — cede ANTES que el contenido esencial; el pie
    completo queda siempre."""
    K = cols(K)
    if h and h < min_h:
        return []
    pares = list(items)
    if max_pairs and len(pares) > max_pairs:
        pares = pares[:max_pairs - 1] + [pares[-1]]
    line = keyline(K, pares, max(10, w - 3), txt_col=K["GREY"])
    if not line:
        return []
    return [" " * max(0, ((w - 1) - vis(line)) // 2) + line]


def foot_hints(K, items, w):
    """El pie de atajos COMPLETO — UNA línea (altura estable, el pie jamás
    crece), mismo lenguaje que la cabecera pero con la lista entera y la
    acción tenue. Reemplaza a la vieja línea DK plana."""
    return " " + keyline(cols(K), items, max(10, w - 3))


def screen_header(K, w, h, sub, hints=None, compact_h=30, refl_min_h=0,
                  hints_min_h=None):
    """Cabecera COMPARTIDA de las pantallas-sección del hub (tono /
    calendario / atajos / github / dev / …): wordmark centrado + reflejo +
    subtítulo + atajos clave (top_hints) + regla + aire. `refl_min_h` > 0
    cede el reflejo bajo ese alto (pantallas densas); `hints_min_h` idem
    para la fila de atajos (default: el mismo umbral del wordmark
    compacto). Devuelve las líneas iniciales del render."""
    K = cols(K)
    L = [""]
    bt = big_title(K, w, h, indent=" ", compact=(h < compact_h), center=True)
    L += bt
    if len(bt) > 1 and h >= refl_min_h:
        L += title_reflection(K, w, indent=" ", center=True)
    L.append(" " * max(0, ((w - 1) - vis(sub)) // 2)
             + "%s%s%s" % (K["DIM"], sub, K["R"]))
    if hints:
        L += top_hints(K, hints, w, h,
                       min_h=(hints_min_h if hints_min_h is not None
                              else compact_h))
    L.append("%s%s%s%s%s" % (K["B2"], K["BOX"][5] * 3, K["DK"],
                             K["BOX"][5] * max(1, w - 5), K["R"]))
    L.append("")
    return L


def section_mark(txt, on, K):
    """Título de sección `▐ TÍTULO` — la enfocada en acento bold, el resto
    apagado (mismo lenguaje foco/apagado que el recinto clásico)."""
    if on:
        return "%s▐ %s%s%s%s" % (K["B"], K["C"] + K["BO"], txt, K["R"], "")
    return "%s▐ %s%s" % (K["DK"], txt, K["R"])


def latido_lines(data, view, K, w, indent="  "):
    """Bloque del LATIDO compartido (radio-group + estado + fila de aviso).
    [] si no hay heartbeat (estable: depende de data, no de la selección)."""
    if not data.get("hb"):
        return []
    hb = data["hb"]
    st = []
    try:
        b = hb.get("budget") or {}
        pct = b.get("pct")
        st.append("cola %s" % hb.get("count", 0))
        st.append("uso 5h %s" % ("?" if pct is None else "%d%%" % round(pct)))
        if b.get("ok") is not True:
            st.append("presupuesto en pausa")
    except Exception:
        pass
    out = [clip(indent + radio_row(data, view, K) + "   %s%s%s"
                % (K["DK"], " · ".join(st), K["R"]), w - 1)]
    out.append(clip("%s%s%s%s" % (indent, K["DIM"], view.get("hb_msg") or "",
                                  K["R"]), w - 1) if view.get("hb_msg")
               else "")                       # aviso del latido SIEMPRE reservado
    return out


# ── CONFIGS ancladas al hub (ui.hub_pins) — acceso rápido a unos pocos
# settings SEGUROS desde el recinto, sin abrir la Config completa ───────────
def hub_pins():
    """Los settings ANCLADOS al hub (ui.hub_pins) resueltos a
    [{key, label, value}] para la sección CONFIGS. La resolución vive en
    settings (settings.hub_pins_resolved) — el recinto clásico la comparte sin
    depender de hublayout. Falla-suave TOTAL: cualquier problema → []."""
    try:
        import settings
        return settings.hub_pins_resolved()
    except Exception:
        return []


def hub_pins_lines(K, w, indent="  ", hint=True, view=None):
    """Bloque de CONFIGS ancladas EDITABLES: una fila `▸ label   valor` por
    pin (label tenue, valor en acento) con las etiquetas alineadas. Con
    `view` (focus + cfg_focus) el pin ENFOCADO se resalta (cursor ▸ en acento
    + valor blanco bold — mismo lenguaje de foco que el resto del recinto) y
    el hint pasa a `◄► elige · Enter/espacio cambia`; sin view es
    display-only (`Config ▸ para editar`). [] si no hay pins (nada inventado
    — la sección simplemente no crece). Altura ESTABLE: depende solo de
    ui.hub_pins + el valor efectivo, ni de la selección ni del frame."""
    K = cols(K)
    pins = hub_pins()
    if not pins:
        return []
    foc = (view or {}).get("focus") == "latido"
    cf = ((view or {}).get("cfg_focus", 0) % len(pins)) if view else -1
    labw = min(max((vis(p["label"]) for p in pins), default=0),
               max(6, (w - vis(indent)) // 2))
    out = []
    for i, p in enumerate(pins):
        lab = pad(clip(p["label"], labw), labw)
        val = clip(p["value"], max(1, w - vis(indent) - labw - 5))
        if foc and i == cf:                              # pin ENFOCADO
            row = "%s%s▸ %s%s%s  %s%s%s" % (indent, K["C"] + K["BO"], K["DIM"],
                                            lab, K["R"], K["WH"] + K["BO"],
                                            val, K["R"])
        else:
            row = "%s%s▸ %s%s%s  %s%s%s" % (indent, K["DK"], K["DIM"], lab,
                                            K["R"], K["C"] + K["BO"], val,
                                            K["R"])
        out.append(clip(row, w - 1))
    if hint:
        htxt = "◄► elige · Enter/espacio cambia" if foc else \
               "Config ▸ para editar"
        out.append(clip("%s%s%s%s" % (indent, K["DK"], htxt, K["R"]), w - 1))
    return out


# ── LENGUAJE DE DISEÑO COMPARTIDO (feedback aprobado 2026-07-03) ────────────
# Los 5 layouts alternativos comparten estos widgets; cada layout conserva su
# ESTRUCTURA propia. Todo con dato REAL (git/heartbeat/now.json/bus) — si la
# fuente no está, el widget se OMITE limpio.

# Fuente ASCII "ANSI Shadow" por letra (6 filas): bloques █ con sombra ╗╔║═╝╚
# — box-drawing/bloques estándar < U+2600 (Windows-safe). EMPOTRADA (sin
# figlet): solo las letras del título; agregar aquí si el título cambia.
# Tabla canónica de la fuente (A-Z · 0-9): templates/agent/workspace/brand/agent-banner.py
_SHADOW = {
    "W": ("██╗    ██╗", "██║    ██║", "██║ █╗ ██║", "██║███╗██║",
          "╚███╔███╔╝", " ╚══╝╚══╝ "),
    "R": ("██████╗ ", "██╔══██╗", "██████╔╝", "██╔══██╗",
          "██║  ██║", "╚═╝  ╚═╝"),
    "K": ("██╗  ██╗", "██║ ██╔╝", "█████╔╝ ", "██╔═██╗ ",
          "██║  ██╗", "╚═╝  ╚═╝"),
    "A": (" █████╗ ", "██╔══██╗", "███████║", "██╔══██║",
          "██║  ██║", "╚═╝  ╚═╝"),
    "C": (" ██████╗", "██╔════╝", "██║     ", "██║     ",
          "╚██████╗", " ╚═════╝"),
    "E": ("███████╗", "██╔════╝", "█████╗  ", "██╔══╝  ",
          "███████╗", "╚══════╝"),
    "O": (" ██████╗ ", "██╔═══██╗", "██║   ██║", "██║   ██║",
          "╚██████╔╝", " ╚═════╝ "),
    "L": ("██╗     ", "██║     ", "██║     ", "██║     ",
          "███████╗", "╚══════╝"),
    "Y": ("██╗   ██╗", "╚██╗ ██╔╝", " ╚████╔╝ ", "  ╚██╔╝  ",
          "   ██║   ", "   ╚═╝   "),
    "M": ("███╗   ███╗", "████╗ ████║", "██╔████╔██║", "██║╚██╔╝██║",
          "██║ ╚═╝ ██║", "╚═╝     ╚═╝"),
    "P": ("██████╗ ", "██╔══██╗", "██████╔╝", "██╔═══╝ ",
          "██║     ", "╚═╝     "),
    "U": ("██╗   ██╗", "██║   ██║", "██║   ██║", "██║   ██║",
          "╚██████╔╝", " ╚═════╝ "),
    "S": ("███████╗", "██╔════╝", "███████╗", "╚════██║",
          "███████║", "╚══════╝"),
}


def _shadow_rows(word="WORKSPACE"):
    """Las 6 filas ANSI Shadow de `word` (sin color). WORKSPACE = 75 cols."""
    rows = ["", "", "", "", "", ""]
    for ch in word:
        g = _SHADOW.get(ch.upper())
        if not g:
            continue
        for r in range(6):
            rows[r] += g[r]
    return rows


_SHADOW_GLYPHS = frozenset("╔╗╚╝║═")     # el "tubo" de la fuente ANSI Shadow


def _neon_row(row, core, shade, R):
    """Una fila del título en NEÓN (feedback cockpit-v7 2026-07-04): el
    núcleo █ de las letras en `core` (gradiente brillante bold) y la SOMBRA
    de la fuente (╔╗╚╝║═) en `shade` (tono tenue del acento, no gris) — la
    letra se lee como tubo de luz con profundidad. Solo color: mismos
    caracteres, mismo ancho visual."""
    parts, prev = [], None
    for ch in row:
        kind = ("c" if ch == "█"
                else ("s" if ch in _SHADOW_GLYPHS else " "))
        if kind != prev:
            parts.append(R + (core if kind == "c"
                              else (shade if kind == "s" else "")))
            prev = kind
        parts.append(ch)
    parts.append(R)
    return "".join(parts)


def big_title(K, w, h=0, indent=" ", right="", compact=False,
              center=False):
    """Título WORKSPACE GRANDE en ANSI Shadow, look NEÓN: núcleo █ con el
    GRADIENTE del tema activo (WCOL fila a fila: magenta→violeta→cian en
    cyberpunk, dorado en olympo) en bold + la sombra de la fuente (╔╗╚╝║═)
    en el acento medio TENUE (no gris — profundidad de tubo neón) + un
    widget opcional arriba a la derecha (`right`, p.ej. la rama git).
    RESPONSIVO: si el ancho no da (o el alto h viene y es chico, o el caller
    pide compact — ver _fit) cae al wordmark compacto de UNA línea — jamás
    desborda. K = paleta o cols().

    `center` (opt-in por layout — pedido del socio 2026-09-23): el wordmark se
    centra en el ancho REAL. El indent se recalcula por CAMINO (el bloque
    grande centra sus 75 columnas; el wordmark compacto centra SU línea, que
    es mucho más corta — centrar ambos con el mismo indent dejaba el
    compacto tirado a la derecha). Si el widget `right` ya no cabe junto al
    bloque centrado se OMITE: la rama sigue en la statusline del pie."""
    K = cols(K)
    rows = _shadow_rows()
    tw = max(len(r) for r in rows)
    grande = (not compact) and (w - 1) >= (vis(indent) + tw) \
        and (not h or h >= 24)
    if center and grande:
        indent = " " * max(0, ((w - 1) - tw) // 2)
    ind = vis(indent)
    if grande and w - 1 >= ind + tw:
        wc = K["WCOL"]
        out = []
        for r, row in enumerate(rows):
            ln = indent + _neon_row(row, wc[r % len(wc)] + K["BO"],
                                    K["B2"], K["R"])
            if r == 0 and right and w - 1 >= ind + tw + 2 + vis(right):
                ln += " " * (w - 1 - ind - tw - vis(right)) + right
            out.append(clip(ln, w - 1))
        return out
    if center:                                   # el compacto centra SU ancho
        indent = " " * max(0, ((w - 1) - vis("▛▀ WORKSPACE")) // 2)
    ln = "%s%s▛▀ %sWORKSPACE%s" % (indent, K["B"] + K["BO"], K["C"], K["R"])
    if right:
        gapw = w - 1 - vis(ln) - vis(right)
        if gapw >= 2:
            ln += " " * gapw + right
    return [clip(ln, w - 1)]


def title_reflection(K, w, indent=" ", center=False):
    """Fila-REFLEJO bajo el título neón (feedback cockpit-v7 2026-07-04):
    la silueta ░ de las 2 últimas filas del ANSI Shadow en orden ESPEJO
    (la base primero) y tonos apagados del acento que se desvanecen —
    luz de letrero sobre piso oscuro. Degrada suave: en mono (sin color)
    no hay reflejo ([]) — ░ gris sería ruido, no luz. Solo geometría
    < U+2600 (Windows-safe)."""
    K = cols(K)
    if not (K["B2"] or K["DK"]):                 # mono → sin reflejo
        return []
    rows = _shadow_rows()
    if center:                                   # mismo eje que el título
        indent = " " * max(0, ((w - 1) - max(len(r) for r in rows)) // 2)
    out = []
    for tint, row in ((K["B2"], rows[-1]), (K["DK"], rows[-2])):
        sil = "".join(" " if ch == " " else "░" for ch in row)
        out.append(clip("%s%s%s%s" % (indent, tint, sil, K["R"]), w - 1))
    return out


def branch_widget(K):
    """`⎇ feat/x ↑81 ✓limpio` — widget de RAMA con git real, coloreado por
    elemento (feedback 2026-07-04): rama en tinta hi del tema, ↑N en acento,
    ↓N en acento medio, ✓limpio en VERDE / ±sucio en warn. '' si no hay repo
    (el caller lo omite)."""
    K = cols(K)
    g = _git_info()
    if not g:
        return ""
    out = "%s%s %s%s%s" % (K["B2"], K["BRANCH"], K["C"], g["branch"],
                           K["R"])
    if g.get("ahead"):
        out += " %s↑%d%s" % (K["B"] + K["BO"], g["ahead"], K["R"])
    if g.get("behind"):
        out += " %s↓%d%s" % (K["B2"], g["behind"], K["R"])
    if g.get("dirty"):
        out += " %s±sucio%s" % (K["B2"] + K["BO"], K["R"])
    else:
        out += " %s%slimpio%s" % (K["OK"], K["CHECK"], K["R"])
    return out


def instrument_bar(data, view, K, w, indent=" "):
    """Barra de INSTRUMENTOS — pills + gauges con dato real:
    `▐◈ claude-code▌ ▐♥ auto▌  uso 5h ▐██████▌░░ 52%  cap 90%  ⌥ wt 18
    ✉ bus 24`. Cada segmento SOLO si su fuente existe (motor · heartbeat ·
    git worktree · bus); en angosto suelta segmentos por la derecha — una
    sola línea, jamás desborda."""
    K = cols(K)

    def pill(icon, txt, icol):
        return "%s▐%s%s%s %s%s%s%s▌%s" % (K["DK"], K["R"], icol + K["BO"],
                                          icon, K["WH"], txt, K["R"],
                                          K["DK"], K["R"])
    segs = []
    if data.get("motor"):
        segs.append(pill("◈", data["motor"], K["B"]))
    hb = data.get("hb")
    if hb:
        segs.append(pill(K["HEART"], view.get("hb_mode") or hb.get("mode")
                         or "?", K["B2"]))
        b = hb.get("budget") or {}
        pct = b.get("pct")
        if pct is not None:
            barw = 8
            fill = max(0, min(barw, int(round(barw * pct / 100.0))))
            # gauge VÍVIDO (feedback 2026-07-04): relleno en tinta hi bold
            # (cian brillante en cyberpunk, dorado claro en olympo), vacío
            # punteado tenue, % en texto brillante, cap en warn
            fcol = (K["C"] + K["BO"]) if b.get("ok") is not False \
                else (K["ERR"] + K["BO"])
            seg = "%suso 5h %s▐%s▌%s%s%s %s%s%d%%%s" % (
                K["DIM"], fcol, "█" * fill, K["DK"], "░" * (barw - fill),
                K["R"], K["WH"], K["BO"], round(pct), K["R"])
            if b.get("ok") is not True:
                seg += " %sEN PAUSA%s" % (K["B2"] + K["BO"], K["R"])
            segs.append(seg)
            if b.get("cap") is not None:
                segs.append("%scap %s%d%%%s" % (K["DIM"], K["B2"] + K["BO"],
                                                round(b["cap"]), K["R"]))
    wt = _worktrees()
    if wt:                    # 0 worktrees no es informacion: es relleno
        segs.append("%s⌥ %swt %s%s%s" % (K["B2"], K["DIM"], K["WH"], wt,
                                         K["R"]))
    bus = _bus_pending()
    if bus is not None:
        segs.append("%s%s %sbus %s%s%s" % (K["B2"], K["MAIL"], K["DIM"],
                                           K["WH"], bus, K["R"]))
    while segs:
        ln = indent + "  ".join(segs)
        if vis(ln) <= w - 1:
            return clip(ln, w - 1)       # clip = saneo (tab/NFD no descuadran)
        segs.pop()                       # angosto: suelta el menos vital
    return ""


def rich_agent_rows(data, view, K, w, indent="  ", dense=False):
    """Filas RICAS de agentes (2 líneas c/u): `▸ Nombre  ● estado` y debajo
    `↳ tarea/rol` (now.json vía data) — llenan el panel con dato real. +
    fila de aviso (view.msg) SIEMPRE reservada. Altura = 2·agentes + 1
    (depende solo de data — estable para el redraw). Con dense=True (alto
    chico — ver _fit) colapsa a UNA línea por agente: `▸ Nombre ● estado ↳
    tarea` (altura agentes + 1)."""
    K = cols(K)
    agents = list(data.get("agents") or ())
    focus = view.get("focus") == "dioses"
    gsel = min(view.get("gsel", 0), max(0, len(agents) - 1))
    namew = min(14, max([vis(a.get("display", "")) for a in agents] or [6]))
    out = []
    for i, a in enumerate(agents):
        sel = (i == gsel)
        task = (a.get("task") or "").strip()
        if task:
            # puntos de estado con COLOR real (feedback 2026-07-04):
            # ◐ tinta hi = busy declarado en el now.json · ● VERDE = activo
            # con tarea · ○ tenue = idle · '· pronto' = planeado
            est = (a.get("state") or "").strip() or "activo"
            if est.lower() in ("busy", "ocupado", "corriendo", "running"):
                glyph, gcol = "◐", K["C"] + K["BO"]
            else:
                glyph, gcol = "●", K["OK"] + K["BO"]
            sub = task
        elif a.get("active"):
            glyph, gcol, est = "○", K["DIM"], "idle"
            sub = a.get("tagline") or "sin tarea publicada"
        else:
            glyph, gcol, est = "·", K["DK"], "pronto"
            sub = a.get("tagline") or "próximamente"
        mark = ("%s▸ %s" % (K["B"] + K["BO"], K["R"])) if (sel and focus) \
            else "  "
        ncol = (K["WH"] + K["BO"]) if sel else (
            K["INACTIVE"] if a.get("active") else K["DK"])
        scol = K["GREY"] if sel else K["DIM"]
        # la tarea viva del seleccionado en tinta brillante; el conector ↳
        # en acento medio cuando hay tarea (la fila "prende" con dato real)
        tcol = (K["WH"] if sel else K["GREY"]) if task else scol
        acol = K["B2"] if task else K["DK"]
        if dense:
            out.append(clip("%s%s%s%s%s  %s%s %s%s%s %s↳%s %s%s%s" % (
                indent, mark, ncol, pad(a.get("display", ""), namew),
                K["R"], gcol, glyph, scol, est, K["R"], acol, K["R"],
                tcol, sub, K["R"]), w - 1))
            continue
        out.append(clip("%s%s%s%s%s  %s%s %s%s%s" % (
            indent, mark, ncol, pad(a.get("display", ""), namew), K["R"],
            gcol, glyph, scol, est, K["R"]), w - 1))
        out.append(clip("%s    %s↳%s %s%s%s" % (
            indent, acol, K["R"], tcol, sub, K["R"]), w - 1))
    if not agents:
        out.append(clip("%s%ssin agentes — Agregar agente en MENÚ%s"
                        % (indent, K["DIM"], K["R"]), w - 1))
    out.append(clip("%s%s%s%s" % (indent, K["DIM"], view.get("msg") or "",
                                  K["R"]), w - 1) if view.get("msg")
               else "")                       # fila de aviso SIEMPRE reservada
    return out


def full_box(title, body, K, pw, ih, focused=False, border=None, label=None):
    """Caja COMPLETA `╭─ TITULO ───╮` + `│ … │` × ih + `╰────╯` (glifos box
    del tema) con la etiqueta FLOTANDO sobre el borde superior. body se
    recorta/rellena a EXACTAMENTE ih filas; cada línea EXACTA a pw columnas
    visibles — el borde derecho queda en UNA columna recta (componer lado a
    lado / llenar el alto).

    `border` (feedback cockpit-v7 2026-07-04): color de ACENTO del borde —
    la caja entera se pinta en ese tono del tema (cian AGENTES, violeta
    SISTEMA, magenta tenue ACTIVIDAD), las 4 esquinas en su versión BRIGHT
    (bold) — menú de programa complejo; enfocada = borde entero bright.
    `label` pisa el color de la etiqueta. Sin `border` → el look clásico
    (enfocada tinta hi / tenue), intacto para status/grid."""
    K = cols(K)
    box = K["BOX"]
    tl, tr, bl, br, v, hh = box[0], box[1], box[2], box[3], box[4], box[5]
    if border:
        hcol = border + K["BO"]                      # esquinas con acento
        bcol = hcol if focused else border
        tcol = label or (border + K["BO"])
        if focused and not label:
            tcol = K["WH"] + K["BO"]                 # la etiqueta PRENDE
    else:
        # look clásico: enfocada = tinta hi bold · sin foco = acento medio
        # (labels de sección con color de tema, no gris — feedback 2026-07-04)
        tcol = label or ((K["C"] + K["BO"]) if focused else K["B2"])
        bcol = K["DIM"] if focused else K["DK"]
        hcol = bcol
    inner = pw - 4                                   # '│ ' + ' │'
    t = clip(title, max(1, pw - 7))                  # título jamás desborda
    fill = max(1, pw - vis(t) - 5)                   # ╭─ t ──…──╮ = pw exacto
    out = [clip("%s%s%s %s%s%s %s%s%s%s%s%s" % (
        hcol, tl + hh, K["R"], tcol, t, K["R"], bcol, hh * fill, K["R"],
        hcol, tr, K["R"]), pw)]
    rows = list(body[:ih]) + [""] * max(0, ih - len(body))
    for ln in rows:
        out.append("%s%s%s %s %s%s%s" % (bcol, v, K["R"], pad(ln, inner),
                                         bcol, v, K["R"]))
    out.append("%s%s%s%s%s%s%s%s" % (hcol, bl, K["R"], bcol, hh * (pw - 2),
                                     K["R"], hcol, br + K["R"]))
    return out


def vfill(L, view, tail=1):
    """LLENAR el alto: si view.h viene y el bloque mide menos de h-1 líneas,
    inserta blancos ANTES de las últimas `tail` (el pie queda abajo). Nunca
    recorta. Para (data, w, h) fijos la altura no depende de la selección."""
    h = view.get("h") or 0
    need = (h - 1) - len(L) if h else 0
    if need > 0:
        at = max(0, len(L) - tail)
        L[at:at] = [""] * need
    return L


# ── ACTIVIDAD: log de eventos REALES (bus + git) — compartido ───────────────
# Feedback 2026-07-04: llenar el vacío con datos reales. Cualquier layout
# puede adoptar activity_section() (el cockpit vsplit la reemplazó por el
# MONITOR; el helper queda disponible para otros layouts/paneles).

def _act_when(epoch):
    """`HH:MM` si el evento es de hoy, `dd/mm` si no (compacto, Win-safe)."""
    try:
        if not epoch:
            return "--:--"
        lt, ln = time.localtime(epoch), time.localtime(time.time())
        return time.strftime("%H:%M" if lt[:3] == ln[:3] else "%d/%m", lt)
    except Exception:
        return "--:--"


def activity_rows(K, w, limit=12):
    """Filas del log de ACTIVIDAD, dato REAL mezclado por tiempo (desc):
    mensajes del bus (`✉ from → to  tipo asunto`) y commits del harness
    (`◆ hash asunto`), timestamp + glifo + color por elemento. Cada fila
    ≤ w columnas. [] si ninguna fuente está (el caller pinta placeholder)."""
    K = cols(K)
    ev = [(m.get("ts") or 0, "bus", m) for m in (_bus_recent(limit) or ())]
    ev += [(c.get("ts") or 0, "git", c) for c in (_git_log(limit) or ())]
    ev.sort(key=lambda e: e[0], reverse=True)
    out = []
    for ts, kind, m in ev[:limit]:
        when = "%s%s%s" % (K["DK"], _act_when(ts), K["R"])
        if kind == "bus":
            pend = (" %s· pendiente%s" % (K["B2"] + K["BO"], K["R"])
                    if m.get("status") == "pending" else "")
            ln = "%s  %s%s%s %s%s%s %s→%s %s%s%s  %s%s%s %s%s%s%s" % (
                when, K["B2"] + K["BO"], K["MAIL"], K["R"],
                K["WH"], m.get("from") or "?", K["R"], K["DK"], K["R"],
                K["WH"], m.get("to") or "?", K["R"],
                K["C"], m.get("type") or "msg", K["R"],
                K["DIM"], m.get("subject") or "", K["R"], pend)
        else:
            ln = "%s  %s◆%s %s%s%s %s%s%s" % (
                when, K["OK"] + K["BO"], K["R"], K["C"], m.get("h") or "",
                K["R"], K["DIM"], m.get("s") or "", K["R"])
        out.append(clip(ln, w))
    return out


def activity_section(K, pw, ih=None, focused=False, limit=12):
    """Caja completa ACTIVIDAD (full-width, pw columnas exactas): últimos
    eventos reales del bus + commits git, estilo log. `ih` fija el alto
    interior (es LA caja que absorbe el alto sobrante del cockpit; None →
    natural, ≤6). Borde en el acento APAGADO del tema (magenta/violeta
    tenue, no gris) con la etiqueta encendida en el acento — cockpit-v7.
    Sin fuentes → placeholder tenue y la caja CIERRA igual."""
    K = cols(K)
    pw = max(16, pw)
    rows = activity_rows(K, pw - 4, limit=limit)
    n_bus = len(_bus_recent(limit) or ())
    n_git = len(_git_log(limit) or ())
    bits = ([("bus %d" % n_bus)] if n_bus else []) \
        + ([("git %d" % n_git)] if n_git else [])
    title = "ACTIVIDAD" + ((" · " + " · ".join(bits)) if bits else "")
    if not rows:
        rows = ["%ssin actividad registrada — el log llega solo (bus/git)%s"
                % (K["DIM"], K["R"])]
    if ih is None:
        ih = min(len(rows), 6)
    off = K.get("OFF") or K["DK"]
    return full_box(title, rows, K, pw, max(1, ih), focused,
                    border=off, label=K["B"] + K["BO"])


# ── WIDGETS DE MONITOR compartidos (cockpit vsplit 2026-07-04) ──────────────
# Piezas REUTILIZABLES para cualquier panel de telemetría (el MONITOR del
# cockpit hoy; el monitor de pipelines mañana): gauge, bar_chart, sparkline y
# stat_tiles. Puros (valor → línea(s) ANSI), pintan SOLO con la paleta del
# tema (cols()) y solo geometría/bloques < U+2600 (Windows-safe). El
# "movimiento" es el DATO: el widget se redibuja con valores frescos al tick
# — cero animación decorativa.

_SPARKS = "▁▂▃▄▅▆▇█"                     # U+2581–2588 (bloques estándar)


def gauge(K, width, pct, col=None):
    """`▐████░░░░▌ NN%` — medidor horizontal: relleno █ brillante (tinta hi
    bold; `col` lo pisa — p.ej. warn para presupuesto), vacío ░ tenue, % en
    texto brillante. '' si pct es None/no numérico (el caller omite)."""
    K = cols(K)
    try:
        p = max(0.0, min(100.0, float(pct)))
    except (TypeError, ValueError):
        return ""
    width = max(3, int(width))
    fill = max(0, min(width, int(round(width * p / 100.0))))
    fcol = col or (K["C"] + K["BO"])
    return "%s▐%s%s%s%s%s▌%s %s%s%d%%%s" % (
        fcol, "█" * fill, K["R"], K["DK"], "░" * (width - fill), fcol,
        K["R"], K["WH"], K["BO"], round(p), K["R"])


def bar_chart(K, rows, width):
    """Barras horizontales `nombre ███ N` (una línea por fila, escala al
    máximo): la fila pico en tinta hi brillante, el resto en acento. rows =
    [(etiqueta, n)]; [] si no hay filas (el caller omite el widget)."""
    K = cols(K)
    try:
        rows = [(str(lb), int(n)) for lb, n in rows if n is not None]
    except (TypeError, ValueError):
        return []
    if not rows:
        return []
    mx = max(n for _, n in rows) or 1
    namew = min(10, max(vis(lb) for lb, _ in rows))
    numw = max(len(str(n)) for _, n in rows)
    barw = max(3, min(18, width - namew - numw - 2))
    out = []
    for lb, n in rows:
        fill = int(round(barw * n / float(mx)))
        if n > 0:
            fill = max(1, fill)
        bcol = (K["C"] + K["BO"]) if n == mx else K["B"]
        out.append("%s%s%s %s%s%s %s%s%s" % (
            K["GREY"], pad(clip(lb, namew), namew), K["R"],
            bcol, "█" * fill, K["R"], K["WH"], n, K["R"]))
    return out


def sparkline(K, values, col=None):
    """`▁▂▃▄▅▇█` — serie compacta escalada al máximo (cero = ▁, pico = █;
    todo real: una serie plana de ceros se pinta plana). '' sin valores."""
    K = cols(K)
    try:
        vals = [max(0.0, float(v)) for v in values]
    except (TypeError, ValueError):
        return ""
    if not vals:
        return ""
    mx = max(vals)
    body = "".join(
        _SPARKS[0] if (mx <= 0 or v <= 0)
        else _SPARKS[max(1, min(7, int(v * 8 / mx)))]
        for v in vals)
    return (col or (K["C"] + K["BO"])) + body + K["R"]


def stat_tiles(K, pairs, width):
    """Tiles compactos `etiqueta VALOR · etiqueta VALOR` con reflow a ≤width
    columnas por línea (etiqueta tenue, valor brillante, separador apagado).
    [] sin pares. El reflow usa anchos PLANOS — altura estable."""
    K = cols(K)
    pairs = [(str(lb), str(v)) for lb, v in pairs]
    if not pairs:
        return []
    out, cur, curw = [], [], 0
    for lb, v in pairs:
        cellw = vis(lb) + 1 + vis(v)
        extra = 3 if cur else 0                       # ' · '
        if cur and curw + extra + cellw > width:
            out.append(cur)
            cur, curw = [], 0
        cur.append("%s%s %s%s%s%s" % (K["DIM"], lb, K["WH"], K["BO"], v,
                                      K["R"]))
        curw += cellw + extra
    if cur:
        out.append(cur)
    sep = " %s·%s " % (K["DK"], K["R"])
    return [clip(sep.join(row), width) for row in out]


def compact_agent_rows(data, view, K, w, indent=""):
    """Filas COMPACTAS de agentes (1 línea c/u, boceto vsplit aprobado):
    `▸ ● Nombre  tarea/rol` — puntero de selección, punto de estado con
    color real (◐ busy · ● activo · ○ idle · · pronto), nombre y la tarea
    viva (now.json) o el rol. + fila de aviso (view.msg) SIEMPRE reservada.
    Altura = agentes + 1 (solo depende de data — estable)."""
    K = cols(K)
    agents = list(data.get("agents") or ())
    focus = view.get("focus") == "dioses"
    gsel = min(view.get("gsel", 0), max(0, len(agents) - 1))
    namew = min(12, max([vis(a.get("display", "")) for a in agents] or [6]))
    out = []
    for i, a in enumerate(agents):
        sel = (i == gsel)
        task = (a.get("task") or "").strip()
        if task:
            est = (a.get("state") or "").strip().lower()
            if est in ("busy", "ocupado", "corriendo", "running"):
                glyph, gcol = "◐", K["C"] + K["BO"]
            else:
                glyph, gcol = "●", K["OK"] + K["BO"]
            sub = task
        elif a.get("active"):
            glyph, gcol = "○", K["DIM"]
            sub = a.get("tagline") or "idle"
        else:
            glyph, gcol = "·", K["DK"]
            sub = a.get("tagline") or "pronto"
        mark = ("%s▸ %s" % (K["B"] + K["BO"], K["R"])) if (sel and focus) \
            else "  "
        ncol = (K["WH"] + K["BO"]) if sel else (
            K["INACTIVE"] if a.get("active") else K["DK"])
        tcol = (K["WH"] if sel else K["GREY"]) if task else K["DIM"]
        out.append(clip("%s%s%s%s%s %s%s%s  %s%s%s" % (
            indent, mark, gcol, glyph, K["R"], ncol,
            pad(a.get("display", ""), namew), K["R"], tcol, sub, K["R"]),
            w - 1))
    if not agents:
        out.append(clip("%s%ssin agentes — Agregar agente en SISTEMA%s"
                        % (indent, K["DIM"], K["R"]), w - 1))
    out.append(clip("%s%s%s%s" % (indent, K["DIM"], view.get("msg") or "",
                                  K["R"]), w - 1) if view.get("msg")
               else "")                       # fila de aviso SIEMPRE reservada
    return out


def monitor_body(data, K, inner, hours=12):
    """Cuerpo del panel MONITOR (dato real, se refresca al tick): gauges de
    uso 5h y presupuesto (heartbeat), bus por agente en barras (messages.py),
    commits/hora en sparkline + pico (git log) y tiles ramas/wt/cola/
    agentes. CADA widget solo si su fuente existe — sin fuente se OMITE y la
    caja cierra igual (nada inventado). Independiente de la selección
    (altura estable). Compartido: cualquier layout/panel puede adoptarlo."""
    K = cols(K)
    lw = 7                                            # columna de etiquetas
    out = []

    def lbl(t):
        return "%s%s%s " % (K["B2"], pad(t, lw), K["R"])
    hb = data.get("hb")
    if hb:
        b = hb.get("budget") or {}
        # el gauge mide gw+2 (el marco) + ' NN%' (4) tras la etiqueta
        # (lw+1): reservar lw+7 — con lw+6 el % se recortaba a '…' en
        # columnas angostas (MONITOR del centro, feedback 2026-07-04).
        # Cap 20: en paneles anchos el gauge se estira (lados anchos).
        gw = max(6, min(20, inner - lw - 7))
        if b.get("pct") is not None:
            warn = (K["ERR"] + K["BO"]) if b.get("ok") is False else None
            ln = lbl("uso 5h") + gauge(K, gw, b["pct"], col=warn)
            if b.get("ok") is not True:
                ln += " %sEN PAUSA%s" % (K["B2"] + K["BO"], K["R"])
            out.append(clip(ln, inner))
        if b.get("cap") is not None:                  # tope, en tono warn
            out.append(clip(lbl("presup") + gauge(K, gw, b["cap"],
                                                  col=K["B2"] + K["BO"]),
                            inner))
    bus = _bus_pending()
    by = _SYS_CACHE.get("bus_by") or {}
    if bus is not None and by:
        if out:
            out.append("")
        rows = sorted(by.items(), key=lambda kv: (-kv[1], kv[0]))[:4]
        for i, ln in enumerate(bar_chart(K, rows, inner - lw - 1)):
            out.append(clip((lbl("bus") if i == 0 else " " * (lw + 1)) + ln,
                            inner))
    gh = _git_hours(hours)
    if gh:
        if out:
            out.append("")
        # la etiqueta refleja el DATO servido (el memo no cachea por
        # ventana: si otra vista pidió 12h, no rotular 24h — nada inventado)
        nh = len(gh.get("counts") or ()) or hours
        out.append(clip("%scommits%s/%dh%s" % (K["B2"], K["DIM"], nh,
                                               K["R"]), inner))
        ln = " " + sparkline(K, gh.get("counts") or ())
        if gh.get("peak"):
            ln += " %spico %s%s%s" % (K["DIM"], K["WH"],
                                      _act_when(gh["peak"]), K["R"])
        out.append(clip(ln, inner))
    tiles = []
    br = _branches()
    if br is not None:
        tiles.append(("ramas", br))
    wt = _worktrees()
    if wt is not None:
        tiles.append(("wt", wt))
    if hb:
        tiles.append(("cola", hb.get("count", 0)))
    tiles.append(("agentes", len(data.get("agents") or ())))
    rows = stat_tiles(K, tiles, inner)
    if rows:
        if out:
            out.append("")
        out += rows
    return out


def _fit(impl, data, view, K, w):
    """Responsivo en ALTO (desbordar la pantalla rompe el redraw con
    cursor-up): renderiza con el título GRANDE permitido; si view.h viene y
    el bloque excede h-1 líneas degrada en orden — título compacto → filas
    de agente densas (1 línea). Si ni así cabe (terminal mínima) devuelve
    lo más denso. Para un (data, w, h) fijo la altura sigue sin depender de
    la selección."""
    h = view.get("h") or 0
    L = impl(data, view, K, w, False, False)
    if not h or len(L) <= h - 1:
        return L
    for compact, dense in ((True, False), (True, True)):
        L = impl(data, view, K, w, compact, dense)
        if len(L) <= h - 1:
            return L
    return L


# ── LAYOUT: hud — HUD de consola (todo a la izquierda) ──────────────────────
def render_hud(data, view, K, w):
    """`hud` (ver _hud_lines) — título grande si cabe en alto (_fit)."""
    return _fit(_hud_lines, data, view, K, w)


def _hud_lines(data, view, K, w, compact=False, dense=False):
    """`hud`: consola alineada a la IZQUIERDA — título GRANDE ANSI Shadow
    (gradiente del tema) + widget de rama + línea de build + barra de
    instrumentos; AGENTES en filas ricas, ACCIONES, LATIDO y el prompt ❯ al
    pie. Nada centrado, sin cajas — llena el alto (view.h)."""
    K = cols(K)
    L = big_title(K, w, view.get("h") or 0, indent="",
                  right=branch_widget(K), compact=compact)
    build = " · ".join(p for p in (
        ("v" + data["version"]) if data.get("version") else "",
        data.get("version_text") or "", data.get("motor") or "") if p)
    L.append(clip("  %s%s%s" % (K["DIM"], build, K["R"]), w - 1))
    L.append(clip("%s%s%s" % (K["DK"], K["SEP"] * (w - 1), K["R"]), w - 1))
    L.append(clip(instrument_bar(data, view, K, w, indent="  "), w - 1))
    L.append("")
    L.append(section_mark("AGENTES", view.get("focus") == "dioses", K))
    L += rich_agent_rows(data, view, K, w, dense=dense)
    L.append("")
    L.append(section_mark("MENÚ", view.get("focus") == "tools", K))
    L += action_rows(data, view, K, w)
    if data.get("hb"):
        L.append("")
        L.append(section_mark("PERSONALIZACIÓN", view.get("focus") == "latido", K))
        L += latido_lines(data, view, K, w)
    L.append("")
    L.append(clip("%s%s %s▌%s" % (K["C"] + K["BO"], K["PTR"], K["WH"],
                                  K["R"]), w - 1))
    L.append(clip(" " + foot_hints(K, HINT_PAIRS, w), w - 1))
    return vfill(L, view, tail=2)


# ── LAYOUT: cockpit — split VERTICAL con MONITOR vivo ───────────────────────
# Rediseño 2026-07-04 (boceto aprobado por el socio): título neón full-width +
# barra de instrumentos arriba; DOS columnas — izquierda el layout (cajas
# AGENTES + SISTEMA compactas, apiladas), derecha un MONITOR de telemetría
# SIEMPRE visible que llena el alto (gauges, bus en barras, sparkline de
# commits, tiles — monitor_body). Statusline al pie. El "movimiento" son los
# DATOS (TTL corto), cero animación decorativa. Todo dato real: sin fuente
# barata el widget se omite.


def _vsplit_sys_body(data, view, K, inner, dense=False):
    """Cuerpo COMPACTO del panel SISTEMA (boceto vsplit): radio del latido,
    cola, rama ⎇ (git real) y las ACCIONES directas (`❮Config❯ Dev …`).
    La telemetría pesada vive en el MONITOR — aquí solo control + estado
    esencial. Sin fuente → la fila se omite limpio."""
    K = cols(K)
    hb = data.get("hb")
    lw = 6                                            # columna de etiquetas
    out = []

    def lbl(t):
        return "%s%s%s " % (K["B2"], pad(t, lw), K["R"])
    if hb:
        out.append(clip(lbl("latido") + radio_row_compact(data, view, K),
                        inner))
        out.append(clip("%s%s%s" % (K["DIM"], view.get("hb_msg") or "",
                                    K["R"]), inner)
                   if view.get("hb_msg") else "")     # aviso reservado
        out.append(clip(lbl("cola") + "%s%s%s" % (
            K["WH"], hb.get("count", 0), K["R"]), inner))
    bw = branch_widget(K)
    if bw:
        out.append(clip(lbl("rama") + bw, inner))
    if not dense:
        out.append("")
    out += action_rows(data, view, K, inner + 1, indent="", gap="  ")
    return out


def bottom_statusline(data, view, K, w):
    """Statusline inferior COMPARTIDA (cockpit/status): motor · rama (widget
    git real) · latido · cola · uso │ hints de teclado. Si no cabe todo,
    suelta segmentos de la izquierda (los hints de teclado tienen prioridad
    — el socio siempre sabe cómo moverse)."""
    K = cols(K)
    segs = ["%s%s%s" % (K["WH"], data.get("motor") or "?", K["R"])]
    bw = branch_widget(K)
    if bw:
        segs.append(bw)
    hbb = hb_brief(data, view.get("hb_mode"))
    if hbb:
        segs += ["%s%s%s" % (K["DIM"], p, K["R"]) for p in hbb.split(" · ")]
    if data.get("version_text"):
        segs.append("%s%s%s" % (K["DIM"], data["version_text"], K["R"]))
    # con teclas de salto activas (data.keys) el hint las anuncia — es el
    # recordatorio del pie (la tecla de cada ítem vive PINTADA junto a él:
    # apunta al agente — otra vez entra — / abre la opción; motor/info
    # salen del registro keybinds, re-mapeable en «Atajos»); sin "keys" en
    # data (banner/tests) el hint de siempre, byte-idéntico
    _jk = data.get("keys") or {}
    _ac = _jk.get("acciones") or {}
    if _jk.get("agents") or _jk.get("opts"):
        pares = [("↑↓", "mueve"), ("◄►", "elige"), ("Enter", "entra"),
                 ("tecla", "salta")]
        pares += [(_ac[n], n) for n in ("motor", "info") if _ac.get(n)]
        pares.append(("q", "sale"))
    else:
        pares = [("↑↓", "mueve"), ("◄►", "elige"), ("Enter", "entra"),
                 ("m", "motor"), ("q", "sale")]
    # tecla en acento + acción tenue (keyline): el pie se LEE de un vistazo
    hints = keyline(K, pares, w - 1)
    sep = " %s│%s " % (K["DK"], K["R"])
    while segs:
        left = "%s▐%s " % (K["DK"], K["R"]) + sep.join(segs)
        gapw = w - 1 - vis(left) - vis(hints)
        if gapw >= 2:
            return clip(left + " " * gapw + hints, w - 1)   # saneada exacta
        segs.pop()                                    # suelta el menos vital
    return clip(hints, w - 1)


def render_cockpit(data, view, K, w):
    """`cockpit` (ver _cockpit_lines) — título grande si cabe (_fit)."""
    return _fit(_cockpit_lines, data, view, K, w)


def _cockpit_lines(data, view, K, w, compact=False, dense=False):
    """`cockpit` (split VERTICAL aprobado 2026-07-04): margen superior sutil
    + título WORKSPACE GRANDE en ANSI Shadow NEÓN (núcleo en gradiente del
    TEMA, sombra tenue, fila-reflejo ░) + widget de rama + línea de build +
    regla con acento + barra de instrumentos; luego DOS columnas — IZQUIERDA
    las cajas AGENTES (borde cian/hi) y SISTEMA (borde violeta/mid)
    COMPACTAS y apiladas, DERECHA la caja MONITOR (borde magenta tenue,
    monitor_body: gauges + bus en barras + sparkline de commits + tiles)
    que LLENA el alto — telemetría siempre visible. Statusline inferior.
    En angosto las cajas se APILAN (el MONITOR debajo, absorbe el alto
    sobrante; con alto chico cede — compact/dense). Todo dato con fuente
    real; lo demás se omite."""
    K = cols(K)
    focus = view.get("focus")
    h = view.get("h") or 0
    hchar = K["BOX"][5]
    # ── 1) aire arriba + título grande neón (+ rama) + reflejo + build ──
    L = [] if compact else [""]                  # margen superior sutil
    bt = big_title(K, w, h, indent=" ", right=branch_widget(K),
                   compact=compact)
    L += bt
    if len(bt) > 1:                              # título grande → reflejo neón
        L += title_reflection(K, w, indent=" ")
    build = " · ".join(p for p in (
        ("v" + data["version"]) if data.get("version") else "",
        data.get("version_text") or "", data.get("motor") or "") if p)
    L.append(clip(" %s%s%s" % (K["DIM"], build, K["R"]), w - 1))
    # ── 2) regla con tramo de ACENTO + barra de instrumentos ──
    L.append(clip("%s%s%s%s%s" % (K["B2"], hchar * 3, K["DK"],
                                  hchar * max(1, w - 5), K["R"]), w - 1))
    L.append(clip(instrument_bar(data, view, K, w, indent=" "), w - 1))
    L.append("")
    top_n = len(L)
    status = bottom_statusline(data, view, K, w)
    ags = list(data.get("agents") or ())
    ag_title = "AGENTES · %d" % len(ags) if ags else "AGENTES"
    moff = K.get("OFF") or K["DK"]               # borde MONITOR: acento tenue
    mlabel = K["B"] + K["BO"]                    # etiqueta encendida
    # dense (alto chico): sin aire entre cajas ni antes de la statusline
    gap1, tail = (0, 1) if dense else (1, 2)
    if w - 1 >= 84:                              # ── split VERTICAL ──
        lw = max(28, min(44, (w - 3) * 2 // 5))
        rw = w - 1 - lw - 2
        ab = compact_agent_rows(data, view, K, lw - 3)
        sb = _vsplit_sys_body(data, view, K, lw - 4, dense=dense)
        mb = monitor_body(data, K, rw - 4)
        left = full_box(ag_title, ab, K, lw, len(ab), focus == "dioses",
                        border=K["C"])
        left += [""] * gap1
        left += full_box("SISTEMA", sb, K, lw, len(sb),
                         focus in ("tools", "latido"), border=K["B2"])
        # el MONITOR llena el alto disponible (≥ la columna izquierda);
        # sin h (--banner) usa su alto natural
        mtot = max(len(left), len(mb) + 2)
        if h:
            mtot = max(len(left), (h - 1) - top_n - tail)
        mon = full_box("MONITOR · vivo", mb, K, rw, max(1, mtot - 2),
                       False, border=moff, label=mlabel)
        left += [""] * (mtot - len(left))
        for i in range(mtot):
            L.append(clip(pad(left[i], lw) + "  " + mon[i], w - 1))
    else:                                        # ── angosto: APILADOS ──
        pw = w - 1
        ab = compact_agent_rows(data, view, K, pw - 3)
        sb = _vsplit_sys_body(data, view, K, pw - 4, dense=dense)
        mb = monitor_body(data, K, pw - 4)
        ihl, ihr = len(ab), len(sb)              # alto = contenido (compactas)
        mon_ih = 0
        if h:
            # total = top_n + (ihl+2) + gap1 + (ihr+2) [+ mon_ih+2] + tail
            avail = (h - 1) - top_n - ihr - 4 - gap1 - tail
            if not dense and avail - ihl >= 3:
                mon_ih = avail - ihl - 2         # el MONITOR absorbe el resto
            else:
                ihl = max(ihl, avail)            # sin lugar: el panel llena
        elif not dense:
            mon_ih = min(max(len(mb), 1), 10)
        L += full_box(ag_title, ab, K, pw, ihl, focus == "dioses",
                      border=K["C"])
        if gap1:
            L.append("")
        L += full_box("SISTEMA", sb, K, pw, ihr,
                      focus in ("tools", "latido"), border=K["B2"])
        if mon_ih:
            L += full_box("MONITOR · vivo", mb, K, pw, mon_ih, False,
                          border=moff, label=mlabel)
    # ── 4) statusline inferior ──
    L += ([""] if tail == 2 else []) + [status]
    return L


# ── LAYOUT: split — sidebar de agentes + rail vertical (estilo tmux) ────────
def render_split(data, view, K, w):
    """`split` (ver _split_lines) — título grande si cabe (_fit)."""
    return _fit(_split_lines, data, view, K, w)


def _split_lines(data, view, K, w, compact=False, dense=False):
    """`split`: título GRANDE ANSI Shadow + widget de rama + regla ═══; DOS
    columnas — izquierda AGENTES en filas ricas, derecha SISTEMA + ACCIONES
    con un rail vertical `│` (estilo tmux) que se EXTIENDE para llenar el
    alto; barra de instrumentos + hint al pie. En angosto (<72) se apila."""
    K = cols(K)
    focus = view.get("focus")
    h = view.get("h") or 0
    rail = K["BOX"][4]
    L = big_title(K, w, h, indent=" ", right=branch_widget(K),
                  compact=compact)
    build = " · ".join(p for p in (
        "os de agentes",
        ("v" + data["version"]) if data.get("version") else "",
        data.get("version_text") or "", data.get("motor") or "") if p)
    L.append(clip(" %s%s%s" % (K["DIM"], build, K["R"]), w - 1))
    L.append(clip("%s%s%s" % (K["DK"], "═" * (w - 1), K["R"]), w - 1))

    def title(txt, on):
        return "%s%s%s" % ((K["C"] + K["BO"]) if on else K["DK"], txt, K["R"])

    def sistema(inner):
        out = [title("SISTEMA", focus == "latido"),
               clip("%smotor%s  %s%s · %s%s" % (
                   K["DK"], K["R"], K["DIM"], data.get("motor") or "",
                   data.get("version_text") or "", K["R"]), inner)]
        if data.get("hb"):
            out += [clip(x, inner) for x in
                    latido_lines(data, view, K, inner + 1, indent="")]
        out.append("")
        out.append(title("MENÚ", focus == "tools"))
        out += action_rows(data, view, K, inner + 1, indent="", gap="  ")
        return out

    bar = clip(instrument_bar(data, view, K, w, indent=" "), w - 1)
    hint = clip(foot_hints(K, HINT_PAIRS, w), w - 1)
    if w < 72:                                   # angosto: columnas APILADAS
        inner = w - 4
        L.append(" " + title("AGENTES", focus == "dioses"))
        L += [" " + clip(x, w - 2)
              for x in rich_agent_rows(data, view, K, w - 1, indent="",
                                       dense=dense)]
        L.append("")
        L += [" %s%s%s %s" % (K["DK"], rail, K["R"], clip(x, inner))
              for x in sistema(inner)]
        L += ["", bar, hint]
        return vfill(L, view, tail=2)
    lw = max(24, (w - 4) * 2 // 5)
    inner = w - 1 - lw - 4                       # ' ' + col izq + ' │ '
    left = [title("AGENTES", focus == "dioses")]
    left += rich_agent_rows(data, view, K, lw + 1, indent="",
                            dense=dense)
    right_col = sistema(inner)
    n = max(len(left), len(right_col)) + 1       # una fila de aire con rail
    if h:                                        # el rail LLENA el alto
        n = max(n, (h - 1) - len(L) - 2)         # bar + hint al pie
    left += [""] * (n - len(left))
    right_col += [""] * (n - len(right_col))
    for i in range(n):
        L.append(clip(" %s %s%s%s %s" % (pad(left[i], lw), K["DK"], rail,
                                         K["R"], right_col[i]), w - 1))
    L += [bar, hint]
    return L


# ── LAYOUT: status — pestañas de agentes + statusline (estilo vim/tmux) ─────
def render_status(data, view, K, w):
    """`status` (ver _status_lines) — título grande si cabe (_fit)."""
    return _fit(_status_lines, data, view, K, w)


def _status_lines(data, view, K, w, compact=False, dense=False):
    """`status`: título GRANDE ANSI Shadow + widget de rama; fila de
    PESTAÑAS de agentes (activa `▏nombre▕`), regla, ZONA DE FOCO en caja
    COMPLETA con el detalle del seleccionado (perfil + qué hace ahora),
    ACCIONES + LATIDO, y al pie barra de instrumentos + statusline tipo
    vim/tmux. Llena el alto (view.h)."""
    K = cols(K)
    agents = list(data.get("agents") or ())
    focus = view.get("focus")
    gsel = min(view.get("gsel", 0), max(0, len(agents) - 1))
    h = view.get("h") or 0
    L = big_title(K, w, h, indent=" ", right=branch_widget(K),
                  compact=compact)
    # ── pestañas ──
    tabs = []
    for i, a in enumerate(agents):
        nm = a.get("display", "")
        if i == gsel:
            col = (K["C"] + K["BO"]) if focus == "dioses" else (K["WH"] + K["BO"])
            tabs.append("%s▏%s▕%s" % (col, nm, K["R"]))
        elif a.get("active"):
            tabs.append("%s %s %s" % (K["INACTIVE"], nm, K["R"]))
        else:
            tabs.append("%s %s %s" % (K["DK"], nm, K["R"]))
    brand = ("%sv%s · %s%s" % (K["DIM"], data["version"],
                               data.get("motor") or "", K["R"])) \
        if data.get("version") else ""
    row = "  ".join(tabs) if tabs else "%s(sin agentes)%s" % (K["DIM"], K["R"])
    gapw = w - 2 - vis(row) - vis(brand)
    L.append(clip(" " + (row + " " * gapw + brand if gapw >= 2 and brand
                         else row), w - 1))
    L.append(clip("%s%s%s" % (K["DK"], K["SEP"] * (w - 1), K["R"]), w - 1))
    L.append("")
    # ── zona de foco: el agente seleccionado, en caja completa ──
    body = []
    if agents:
        a = agents[gsel]
        glyph, gcol, txt = agent_status(a, K, True)
        body.append(clip("%s%s%s %s— %s%s" % (
            K["WH"] + K["BO"], a.get("display", ""), K["R"], K["DIM"],
            a.get("tagline") or ("próximamente" if not a.get("active")
                                 else "sin tagline"), K["R"]), w - 7))
        if (a.get("task") or "").strip():
            ahora = "ahora: %s" % txt
        elif a.get("active"):
            ahora = "idle · sin tarea publicada"
        else:
            ahora = "pronto"
        body.append(clip("%s%s%s %s↳ %s%s" % (gcol, glyph, K["R"],
                                              K["GREY"], ahora, K["R"]),
                         w - 7))
    else:
        body.append(clip("%ssin agentes — Agregar agente en MENÚ%s"
                         % (K["DIM"], K["R"]), w - 7))
        body.append("")
    body.append(clip("%s%s%s" % (K["DIM"], view.get("msg") or "", K["R"]),
                     w - 7) if view.get("msg") else "")   # aviso reservado
    L += [clip(" " + x, w - 1)
          for x in full_box("FOCO", body, K, min(w - 2, 96), len(body),
                            focus == "dioses")]
    L.append("")
    # ── acciones (+ latido) ──
    L.append("  %sMENÚ%s" % ((K["C"] + K["BO"]) if focus == "tools"
                                 else K["DK"], K["R"]))
    L += action_rows(data, view, K, w)
    if data.get("hb"):
        L.append("")
        L += latido_lines(data, view, K, w)
    L.append("")
    # ── pie: barra de instrumentos + statusline (hints priorizados) ──
    L.append(clip(instrument_bar(data, view, K, w, indent=" "), w - 1))
    L.append(bottom_statusline(data, view, K, w))
    return vfill(L, view, tail=2)


# ── LAYOUT: grid — tarjetas de agentes con borde reactivo al estado ─────────
def _card(a, K, cw, selected, focused):
    """Tarjeta 4×cw de un agente. El BORDE es reactivo: seleccionada =
    acento brillante (bold con foco), con tarea viva = acento, idle =
    tenue, planeada = apagada."""
    box = K["BOX"]
    tl, tr, bl, br, v, h = box[0], box[1], box[2], box[3], box[4], box[5]
    if selected:
        bcol = (K["C"] + K["BO"]) if focused else K["WH"]
    elif (a.get("task") or "").strip():
        bcol = K["B"]
    elif a.get("active"):
        bcol = K["DIM"]
    else:
        bcol = K["DK"]
    nm = clip(a.get("display", ""), max(1, cw - 7))
    fill = max(1, cw - vis(nm) - 5)
    task = (a.get("task") or "").strip()
    if task:
        glyph, gcol, txt = "●", (K["C"] if selected else K["B"]), task
    elif a.get("active"):
        glyph, gcol, txt = "○", K["GREY"], "idle"
    else:
        glyph, gcol, txt = "·", K["DK"], "pronto"
    inner = cw - 4
    top = "%s%s %s%s%s%s %s%s%s" % (bcol, tl + h, (K["WH"] + K["BO"])
                                    if selected else bcol, nm, K["R"], bcol,
                                    h * fill, tr, K["R"])
    l1 = "%s%s%s %s%s%s %s%s%s %s%s%s" % (
        bcol, v, K["R"], gcol, glyph, K["R"],
        K["GREY"] if selected else K["DIM"], pad(clip(txt, inner - 2),
                                                 inner - 2), K["R"],
        bcol, v, K["R"])
    tag = a.get("tagline") or ""
    l2 = "%s%s%s %s%s%s %s%s%s" % (bcol, v, K["R"], K["DK"],
                                   pad(clip(tag, inner), inner), K["R"],
                                   bcol, v, K["R"])
    bot = "%s%s%s%s%s" % (bcol, bl, h * (cw - 2), br, K["R"])
    return [pad(top, cw), pad(l1, cw), pad(l2, cw), pad(bot, cw)]


def render_grid(data, view, K, w):
    """`grid` (ver _grid_lines) — título grande si cabe (_fit)."""
    return _fit(_grid_lines, data, view, K, w)


def _grid_lines(data, view, K, w, compact=False, dense=False):
    """`grid`: título GRANDE ANSI Shadow + widget de rama + barra de
    instrumentos; los agentes como TARJETAS completas en cuadrícula (2×2 con
    4 agentes; columnas según el ancho) con borde/acento reactivo al estado
    + acciones y LATIDO abajo. Llena el alto (view.h)."""
    K = cols(K)
    agents = list(data.get("agents") or ())
    focus = view.get("focus")
    L = big_title(K, w, view.get("h") or 0, indent=" ",
                  right=branch_widget(K), compact=compact)
    L.append(clip(instrument_bar(data, view, K, w, indent=" "), w - 1))
    L.append("")
    if agents:
        ncols = max(1, min(len(agents), (w - 2) // 26))
        cw_card = min(34, max(18, (w - 2 - (ncols - 1) * 2) // ncols))
        for base in range(0, len(agents), ncols):
            chunk = agents[base:base + ncols]
            cards = [_card(a, K, cw_card, base + j == view.get("gsel", 0),
                           focus == "dioses")
                     for j, a in enumerate(chunk)]
            for r in range(4):
                L.append(clip(" " + "  ".join(c[r] for c in cards), w - 1))
    else:
        L.append(clip(" %ssin agentes — Agregar agente abajo%s"
                      % (K["DIM"], K["R"]), w - 1))
    L.append(clip(" %s%s%s" % (K["DIM"], view.get("msg") or "", K["R"]),
                  w - 1) if view.get("msg") else "")
    L.append("")
    L.append(" %sMENÚ%s" % ((K["C"] + K["BO"]) if focus == "tools"
                                else K["DK"], K["R"]))
    L += action_rows(data, view, K, w, indent=" ")
    if data.get("hb"):
        L.append("")
        L += latido_lines(data, view, K, w, indent=" ")
    L.append("")
    L.append(clip(foot_hints(K, HINT_PAIRS, w), w - 1))
    return vfill(L, view, tail=1)


# ── LAYOUT: centro — mission control (workstations + sprites + DETALLES) ────
# TABLERO COMPLETO (boceto del socio 2026-07-04 + feedback de pulido: usa el
# espacio, más color, datos vivos en lados y arriba): tira izquierda con
# AGENTES (marca de color por agente, navegable) + CONFIGS + MONITOR, al
# centro un grid de WORKSTATIONS (cubículos GRANDES con sprite 6×18 de 4
# frames según el estado REAL de now.json; escalera big → std → mini según
# el alto), a la derecha DETALLES del seleccionado (estado, tarea, worktree,
# bus, misiones — dash.centro.estado) + ACTIVIDAD (bus/git). La animación es
# SOLO cambio de glifo dentro de las celdas del sprite (view.anim, cadencia
# ~0.8s del tick del hub — jamás redibujo full-screen de alta frecuencia);
# la altura NO depende del frame.
# Datos: snapshot del Centro (memo TTL) → sin fuente, el dato se OMITE.

# Color de MARCA por agente (mismo espíritu que FIRES del recinto clásico:
# identidad instantánea de quién es). Pares (brillante, tenue) en 256; en
# mono/16 degrada a los roles del tema (nada de 256 crudo donde no pinta).
_SPRITE_FG = {"blue": (75, 25), "red": (203, 95), "green": (114, 22),
              "cyan": (51, 30), "gold": (220, 136), "magenta": (213, 96)}


def _agent_ink(color, K):
    """(brillante, tenue) ANSI del color de marca del agente; fallback a los
    acentos del TEMA si el tema es monocromo, si el color no está en el mapa o
    si la terminal no da 256 colores. Jamás levanta."""
    K = cols(K)
    if K.get("MONO"):            # tema B/N: la marca cede a los roles del tema
        return K["C"], K["DIM"]  # (si no, el 256 hardcodeado lo mancha)
    try:
        import tuitheme
        if tuitheme.color_mode() in ("mono", "16"):
            return K["C"], K["DIM"]
    except Exception:
        pass
    pair = _SPRITE_FG.get((color or "").strip().lower())
    if not pair:
        return K["C"], K["DIM"]
    return "\x1b[38;5;%dm" % pair[0], "\x1b[38;5;%dm" % pair[1]


def _centro_snapshot():
    """Snapshot AGREGADO del Centro (dash.centro.estado.snapshot(): now.json
    fresco + worktrees por dueño + inbox del bus + misiones). None si el
    backend no está — el layout OMITE esos datos (nada inventado). Memo con
    TTL (_SYS_TTL): el refresh cuesta una pasada cada ~8s, no por frame."""
    if not _sys_fresh("centro"):
        val = None
        try:
            from dash.centro import estado
            val = estado.snapshot()
        except Exception:
            val = None
        _SYS_CACHE["centro"] = val
        _SYS_CACHE_TS["centro"] = time.monotonic()
    return _SYS_CACHE["centro"]


def _centro_agents(data):
    """Copias de data.agents ENRIQUECIDAS con el snapshot del Centro: tarea/
    estado frescos (now.json, rancio >6h ⇒ idle — mismo criterio que front),
    worktree(s) del agente, bus pendiente y misiones. Sin snapshot → los
    datos de sesión de front tal cual. Solo lectura, jamás levanta."""
    snap = _centro_snapshot() or {}
    by = {}
    for s in snap.get("agentes") or ():
        if isinstance(s, dict) and s.get("name"):
            by[s["name"]] = s
    out = []
    for a in data.get("agents") or ():
        a = dict(a)
        s = by.get(a.get("name"))
        if s:
            now = s.get("now") or {}
            task = (now.get("task") or "").strip()
            ep = _iso_epoch(now.get("updated") or now.get("since"))
            stale = ep is not None and (time.time() - ep) > 6 * 3600
            a["task"] = "" if (stale or not task) else task.splitlines()[0]
            a["state"] = "" if stale else (now.get("state") or "")
            # ÚLTIMA tarea publicada — el mismo dato, SIN el filtro de rancio.
            # `task` se vacía a >6h (idle honesto), pero el dato existe: el
            # agente sí publicó eso. Guardarlo deja que el cubículo diga
            # "última: X · hace 2h" en vez de un hueco (2026-07-15).
            a["_last_task"] = task.splitlines()[0] if task else ""
            a["_last_upd"] = ep
            wts = [w_.get("branch") or "" for w_ in (s.get("worktrees") or ())
                   if isinstance(w_, dict)]
            a["_wt"], a["_wt_n"] = (wts[0] if wts else ""), len(wts)
            a["_wts"] = [b for b in wts if b]    # lista completa (DETALLES)
            a["_upd"] = ep if (ep is not None and not stale) else None
            a["_inbox"] = s.get("inbox_pending")
            a["_mis"] = s.get("misiones") if isinstance(s.get("misiones"),
                                                        dict) else None
        out.append(a)
    return out


def _wrap(txt, w, maxl):
    """Corta texto plano en ≤maxl líneas de ≤w columnas (por palabras; una
    palabra imposible se recorta con clip). [] si no hay texto."""
    txt = " ".join(str(txt or "").split())
    if not txt or w <= 0 or maxl <= 0:
        return []
    out, cur = [], ""
    for word in txt.split(" "):
        cand = (cur + " " + word) if cur else word
        if vis(cand) <= w:
            cur = cand
        else:
            if cur:
                out.append(cur)
            if len(out) >= maxl:
                return [clip(x, w) for x in out]
            cur = word
    if cur:
        out.append(cur)
    return [clip(x, w) for x in out[:maxl]]


def _scr_rows(task, w, rows, anim):
    """Filas EXACTAS (`rows` de ancho `w`) de una PANTALLA con el dato
    VIVO: el texto envuelto si cabe — con un cursor ▌ que late — o una
    VENTANA que corre con el frame (marquee) si no. Solo cambia el glifo
    con anim, jamás el ancho (clip/pad: ni un char ancho desborda)."""
    txt = " ".join(str(task or "").split())
    cap = w * rows
    if vis(txt) < cap:                           # cabe: wrap + cursor
        lines = _wrap(txt, w, rows) or [""]
        cur = "▌" if int(anim) % 2 == 0 else " "
        if vis(lines[-1]) < w:
            lines[-1] += cur
        lines += [""] * rows
        return [pad(clip(x, w), w) for x in lines[:rows]]
    loop = txt + " ··· "                         # marquee circular
    off = (int(anim) * 2) % len(loop)
    ven = (loop + loop)[off:off + cap]
    return [pad(clip(ven[i * w:(i + 1) * w], w), w) for i in range(rows)]


def _scr_standby(w, anim):
    """Fila de pantalla NEUTRA apagada (agente idle, sin tarea publicada):
    solo el LED de standby que late — nada inventado, cero dato falso."""
    led = "▪" if int(anim) % 2 == 0 else "·"
    return pad(" " * (w // 2 - 1) + led, w)


def _as_bg(seq):
    """Un escape de FRENTE (38;…) como escape de FONDO (48;…). Sirve para
    pintar los DOS píxeles de una celda con '▀' (fg=arriba, bg=abajo)."""
    return seq.replace("[38;2;", "[48;2;").replace("[38;5;", "[48;5;")


# ── PERSONAJE PIXEL del cubículo (rediseño 2026-07-15, dirección del socio:
# "haz un diseño que sea como un personaje pixel, como de juego 2d retro").
# El puesto dibujado no se parecía a nada real; un personaje sí se lee.
# Cada celda de terminal = 2 PÍXELES verticales (glifo '▀': fg=arriba,
# bg=abajo), así que 7 filas = lienzo de 14 px — tamaño NES. Los mapas son
# pixel-art de verdad, no geometría.
#   '#' piel/manos/pies (WH, lo más brillante) · '+' pelo y ropa (la MARCA del
#   agente: color en temas con color, gris en mono) · '.' vacío.
# Anima el PIXEL, jamás la geometría (alto fijo: 14 px big · 6 px std).
# CABEZA = IDENTIDAD (9 filas) · CUERPO = ESTADO (5 filas).
# Estética CERRADA con el socio (2026-07-15, tras 4 iteraciones y un rango
# comparativo): CHIBI de OJOS GRANDES en SILUETA BLANCA PURA. Las reglas que
# la definen — romperlas es romper el diseño:
#   · CERO gris. Blanco sólido sobre negro; el gris ensuciaba y peleaba con
#     el chrome del hub (línea fina + negro + blancos que golpean).
#   · El detalle es ESPACIO NEGATIVO: los ojos y los cortes son HUECOS, no
#     píxeles pintados. Se dibuja quitando.
#   · Sin tono, la IDENTIDAD vive en el CONTORNO: cada agente trae su pelo.
#   · Los OJOS van GRANDES (2×2 px) y BAJOS: es lo que hace que lea como
#     personaje y no como muñeco. En silueta pura son casi el único rasgo
#     que queda — vale gastarlo en grande.
_PIX_HEAD = {
    "zenith": [                               # moño arriba
        ".....##.....",
        "...######...",
        "..########..",
        ".##########.",
        ".##.####.##.",
        ".##.####.##.",
        ".##########.",
        "..########..",
        "....####....",
    ],
    "iris": [                                 # pelo largo hasta los hombros
        "...######...",
        "..########..",
        ".##########.",
        ".##########.",
        ".##.####.##.",
        ".##.####.##.",
        ".##########.",
        ".##########.",
        ".##..##..##.",
    ],
    "atlas": [                                # prolijo, plano
        "............",
        "..########..",
        ".##########.",
        ".##########.",
        ".##.####.##.",
        ".##.####.##.",
        ".##########.",
        "..########..",
        "....####....",
    ],
    "argus": [                                # rapado, cabeza compacta
        "............",
        "...######...",
        "..########..",
        "..########..",
        "..#.####.#..",
        "..#.####.#..",
        "..########..",
        "...######...",
        "....####....",
    ],
    "turing": [                               # despeinado: picos
        "..#.##.#....",
        ".##########.",
        ".##########.",
        ".##########.",
        ".##.####.##.",
        ".##.####.##.",
        ".##########.",
        "..########..",
        "....####....",
    ],
}
_PIX_HEAD_DEF = _PIX_HEAD["atlas"]            # agente desconocido: neutro
_PIX_BODY_IDLE = [
    "..########..",
    ".##.####.##.",                           # brazos a los lados
    "....####....",
    "...##..##...",
    "..###..###..",
]
_PIX_BODY_WORK = [
    ".##.####.##.",                           # brazos ARRIBA: tecleando
    "..########..",
    "....####....",
    "...##..##...",
    "..###..###..",
]
_PIX_BODY_WIDE = [                            # Argus: complexión más ancha
    ".##########.",
    "###.####.###",
    "..########..",
    "...##..##...",
    "..###..###..",
]
_PIX_STD_IDLE = [                             # BUSTO (std): a 6 px de alto no
    "..####..",                               # cabe el cuerpo; cabeza+hombros
    ".######.",                               # sí. Mismos ojos grandes.
    ".#.##.#.",
    ".#.##.#.",
    ".######.",
    "..####..",
]
_PIX_STD_BLINK = [ln.replace("#.##.#", "######") for ln in _PIX_STD_IDLE]


def _pix_blink(head):
    """Parpadeo: cierra los OJOS (los huecos se rellenan). Busca el patrón,
    así sirve para CUALQUIER cabeza sin declarar índices por agente. El de 10
    va primero: el de 8 es subcadena suya."""
    return [ln.replace("##.####.##", "##########")
              .replace("#.####.#", "########") for ln in head]


def _pix_char(a, anim):
    """El personaje (14 filas de píxel): CABEZA por agente + CUERPO por pose.
    Agente desconocido → cabeza neutra (jamás revienta)."""
    name = (a.get("name") or a.get("display") or "").strip().lower()
    head = _PIX_HEAD.get(name, _PIX_HEAD_DEF)
    f = int(anim) % 4
    working = bool((a.get("task") or "").strip())
    if not working and f == 3:                # idle: parpadea 1 de cada 4
        head = _pix_blink(head)
    if name == "argus":
        body = _PIX_BODY_WIDE
    elif working and f % 2:
        body = _PIX_BODY_WORK                 # teclea en frames alternos
    else:
        body = _PIX_BODY_IDLE
    return list(head) + list(body)


def _pix_rows(grid, K, ink, shade=None, edge=None):
    """Mapa de píxeles → filas de half-blocks (2 px por celda). Ancho fijo,
    alto = len(grid)//2. 4 tonos: '#' piel · '+' pelo/ropa · '-' sombra ·
    '=' contorno. Jamás levanta."""
    K = cols(K)
    # '#' es LA SILUETA → va con la tinta (blanco puro activo · apagado si el
    # puesto es planeado). Antes '#' era piel fija en WH y '+' la ropa; con la
    # silueta de un solo tono eso dejaba al personaje SIEMPRE blanco, incluso
    # planeado. Los demás tonos quedan por si un mapa futuro los usa.
    col = {"#": ink, "+": shade or K["GREY"],
           "-": shade or K["GREY"], "=": edge or K["DK"]}
    out = []
    for i in range(0, len(grid), 2):
        top = grid[i]
        bot = grid[i + 1] if i + 1 < len(grid) else "." * len(top)
        ln = ""
        for x in range(len(top)):
            t = top[x]
            b = bot[x] if x < len(bot) else "."
            if t == "." and b == ".":
                ln += " "
            elif b == ".":
                ln += col[t] + "▀" + K["R"]
            elif t == ".":
                ln += col[b] + "▄" + K["R"]
            elif t == b:
                ln += col[t] + "█" + K["R"]
            else:
                ln += col[t] + _as_bg(col[b]) + "▀" + K["R"]
        out.append(ln)
    return out


def _pix_pose(a, anim, big):
    """Pose del personaje: big = cuerpo entero (identidad por cabeza) ·
    std = BUSTO (a 6 px no cabe una cara entera; cabeza+hombros sí)."""
    if big:
        return _pix_char(a, anim)
    f = int(anim) % 4
    blink = (not (a.get("task") or "").strip()) and f == 3
    return _PIX_STD_BLINK if blink else _PIX_STD_IDLE


def _ws_sprite_pix(a, K, anim, big=False):
    """El personaje del cubículo. La MARCA del agente pinta pelo+ropa: color
    en temas con color, gris en mono (_agent_ink ya cede). Puesto planeado =
    todo apagado."""
    K = cols(K)
    bright, _dimc = _agent_ink(a.get("color"), K)
    # SILUETA BLANCA PURA: el agente activo va en el acento del tema — blanco
    # puro en mono, su marca en temas con color. Nada de gris: el tono medio
    # ensucia y pelea con el chrome (línea fina + negro + blancos que golpean).
    # El ESTADO lo cuentan la POSE y la línea de abajo, jamás el brillo.
    ink = K["DK"] if not a.get("active") else bright   # planeado: apagado
    return _pix_rows(_pix_pose(a, anim, big), K, ink)


def _ws_sprite(a, K, anim):
    """Sprite ESTÁNDAR (3 filas × 12 columnas): la vista sobre-el-hombro
    del puesto en chico — monitor con UNA fila de pantalla VIVA (marquee
    de la tarea del now.json / `!!` bloqueado / LED standby / apagada si
    el puesto está planeado) y la persona como silueta (hombros ▟██▙ en
    el color de marca) sobre el borde del escritorio. Solo bloques
    < U+2600 (Windows-safe); anima el GLIFO, jamás la geometría."""
    K = cols(K)
    bright, dimc = _agent_ink(a.get("color"), K)
    task = (a.get("task") or "").strip()
    # CHASIS del puesto: GREY, no DK. Con DK (#3a en mono / apagado en
    # cualquier tema) el mueble desaparece sobre el fondo y el cubículo
    # se ve VACÍO aunque tenga dibujo (feedback del socio 2026-07-15).
    # El chasis debe LEERSE; la pantalla sigue mandando el contraste.
    dk, R = K["GREY"], K["R"]
    W = 10
    if not a.get("active"):                      # puesto vacío (planeado)
        pcol, scol, scr, homb = dk, dk, " " * W, "▀" * 4
    elif task:                                   # TRABAJANDO: pantalla viva
        pcol, homb = bright + K["BO"], "▟██▙"
        if (a.get("state") or "").strip().lower() == "blocked":
            scr, scol = "!!".center(W), K["BAD"] + K["BO"]
        else:
            scr, scol = _scr_rows(task, W, 1, anim)[0], K["WH"]
    else:                                        # IDLE: standby que late
        pcol, homb = dimc, "▟██▙"
        scr, scol = _scr_standby(W, anim), K["DIM"]
    return [
        "%s▗%s▖%s" % (dk, "▄" * W, R),
        "%s▐%s%s%s▌%s" % (dk, scol, scr, dk, R),
        "%s▀▀▀▀%s%s%s▀▀▀▀%s" % (dk, pcol, homb, dk, R),
    ]


def _ws_sprite_big(a, K, anim):
    """Sprite GRANDE (7 filas × 16 columnas — rediseño 2026-07-04, dirección
    del socio: figura LIMPIA, nada de pirámide): vista sobre-el-hombro del
    puesto — MONITOR ancho arriba (DOS filas de pantalla de 14 columnas),
    base con soporte, teclado con las manos y la persona (nuca ▄██▄ +
    hombros ▟████▙) sobre el borde del escritorio. La PANTALLA muestra el
    DATO REAL VIVO: la tarea del agente (envuelta con cursor ▌ que late;
    larga → marquee que corre con el frame), `!!` en rojo si está
    bloqueado, LED de standby si está idle y APAGADA si el puesto está
    planeado (sin fuente → nada inventado). Manos ▟█▙/▙█▟ tecleando cuando
    trabaja, ▗█▖ quietas idle. Solo bloques/geometría < U+2600
    (Windows-safe); anima el GLIFO a la cadencia baja del tick (~0.8s),
    jamás la geometría (7×16 SIEMPRE — altura estable)."""
    K = cols(K)
    bright, dimc = _agent_ink(a.get("color"), K)
    f = int(anim) % 4
    task = (a.get("task") or "").strip()
    # CHASIS del puesto: GREY, no DK. Con DK (#3a en mono / apagado en
    # cualquier tema) el mueble desaparece sobre el fondo y el cubículo
    # se ve VACÍO aunque tenga dibujo (feedback del socio 2026-07-15).
    # El chasis debe LEERSE; la pantalla sigue mandando el contraste.
    dk, R = K["GREY"], K["R"]
    W = 14
    if not a.get("active"):                      # puesto vacío: todo apagado
        pcol, scol = dk, dk
        sa, sb = " " * W, " " * W
        manos, head, homb = "▂▂▂", "    ", None   # escritorio plano
    elif task:                                   # TRABAJANDO
        pcol = bright + K["BO"]
        manos = "▟█▙" if f % 2 == 0 else "▙█▟"   # teclea
        head, homb = "▄██▄", "▟████▙"
        if (a.get("state") or "").strip().lower() == "blocked":
            sa, sb, scol = "!!".center(W), " " * W, K["BAD"] + K["BO"]
        else:
            sa, sb = _scr_rows(task, W, 2, anim)
            scol = K["WH"]
    else:                                        # IDLE
        pcol = dimc
        manos, head, homb = "▗█▖", "▄██▄", "▟████▙"
        sa, sb, scol = _scr_standby(W, anim), " " * W, K["DIM"]
    r7 = ("%s%s%s" % (dk, "▀" * 16, R)) if homb is None else \
        ("%s▀▀▀▀▀%s%s%s▀▀▀▀▀%s" % (dk, pcol, homb, dk, R))
    return [
        "%s▗%s▖%s" % (dk, "▄" * W, R),
        "%s▐%s%s%s▌%s" % (dk, scol, sa, dk, R),
        "%s▐%s%s%s▌%s" % (dk, scol, sb, dk, R),
        "%s▝▀▀▀▀▀▀██▀▀▀▀▀▀▘%s" % (dk, R),
        "  %s▂▂▂▂▂%s%s%s%s▂▂▂▂▂%s " % (dk, R, pcol, manos, dk, R),
        "      %s%s%s      " % (pcol, head, R),
        r7,
    ]


def _ws_status(a, K, selected):
    """`● tarea…` — línea de estado del cubículo (mismo lenguaje de puntos
    de estado que las listas de agentes)."""
    K = cols(K)
    task = (a.get("task") or "").strip()
    if task:
        est = (a.get("state") or "").strip().lower()
        glyph, gcol = ("◐", K["C"] + K["BO"]) if est in (
            "busy", "ocupado", "corriendo", "running") \
            else ("●", K["OK"] + K["BO"])
        txt, tcol = task, (K["WH"] if selected else K["GREY"])
    elif a.get("active"):
        # idle HONESTO (2026-07-15): si el agente publicó algo antes, decirlo.
        # El dato existe en now.json — `task` lo vacía a >6h, `_last_task` lo
        # conserva. Cuesta media línea y le quita el hueco al cubículo.
        glyph, gcol, tcol = "○", K["DIM"], K["DIM"]
        last = (a.get("_last_task") or "").strip()
        txt = ("idle · última: " + last) if last else "idle"
    else:
        glyph, gcol, txt, tcol = "·", K["DK"], "pronto", K["DK"]
    return "%s%s%s %s%s%s" % (gcol, glyph, K["R"], tcol, txt, K["R"])


# ── CUBÍCULOS del mission-control (rediseño 2026-07-08, dirección del socio:
# volver a cuadritos en GRID con AIRE entre ellos — NADA de jerarquía ni
# aristas; interior LIMPIO y legible) ───────────────────────────────────────
def _ws_card(a, K, wsw, anim, selected, focused, size="std"):
    """Un CUBÍCULO simple: cajita ┌─ Nombre ─┐ con el sprite del puesto y
    UNA línea de estado `● tarea` (○ idle · · pronto). Borde en el color de
    MARCA del agente (vivo si trabaja, tenue idle, apagado planeado);
    seleccionado = acento del tema (el cubículo 'prende'). Interior LIMPIO:
    sin worktree/bus/misiones/aristas (eso vive en DETALLES). Altura SOLO por
    size (jamás por el frame): std = 6 filas (borde + sprite 3 + estado +
    borde) · mini = 3 filas (persona inline + estado)."""
    K = cols(K)
    box = K["BOX"]
    tl, tr, bl, br, v, hh = box[0], box[1], box[2], box[3], box[4], box[5]
    bright, dimc = _agent_ink(a.get("color"), K)
    task = (a.get("task") or "").strip()
    if selected:
        bcol = (K["C"] + K["BO"]) if focused else K["WH"]
    elif task:
        bcol = bright                            # marca VIVA: está trabajando
    elif a.get("active"):
        bcol = dimc
    else:
        bcol = K["DK"]
    ncol = (K["WH"] + K["BO"]) if selected else (
        (bright + K["BO"]) if a.get("active") else K["DK"])
    nm = clip(a.get("display", ""), max(1, wsw - 7))
    fill = max(1, wsw - vis(nm) - 5)
    inner = wsw - 4
    top = "%s%s %s%s%s %s%s%s%s" % (bcol, tl + hh, ncol, nm, K["R"], bcol,
                                    hh * fill, tr, K["R"])
    bot = "%s%s%s%s%s" % (bcol, bl, hh * (wsw - 2), br, K["R"])

    def row(ln):
        return "%s%s%s %s %s%s%s" % (bcol, v, K["R"], pad(ln, inner),
                                     bcol, v, K["R"])
    if size == "mini":
        f = int(anim) % 2
        hands = ("▟█▙" if f == 0 else "▙█▟") if task else "▗█▖"
        pcol = (bright + K["BO"]) if task else (dimc if a.get("active")
                                                else K["DK"])
        ln = "%s%s%s %s" % (pcol, hands if a.get("active") else " · ", K["R"],
                            _ws_status(a, K, selected))
        return [top, row(ln), bot]
    # ── EL PUESTO, dibujado (rediseño 2026-07-15, dirección del socio: "en las
    # cajitas quiero un diseñito... que se vea bonito... que cambie conforme el
    # tamaño de la ventana"). El arte ya era bueno — la PANTALLA muestra la
    # tarea REAL viva — pero se pintaba con DK: en un tema B/N eso es #3a3a3a
    # sobre negro, o sea invisible. No le faltaba dibujo: le faltaba LUZ.
    # Escalera responsive: big (7 filas, teclado+manos) → std (3) → mini (1).
    out = [top]
    big = (size == "big")
    sprite = _ws_sprite_pix(a, K, anim, big=big)
    sw = 12 if big else 8                        # ancho del lienzo del pixel
    lead = max(0, (inner - sw) // 2)
    for s in sprite:
        out.append(row(" " * lead + s))
    out.append(row(_ws_status(a, K, selected)))
    out.append(bot)
    return out


def _cards_dims(cw, n):
    """(ncols, wsw, gx) del grid de cubículos: hasta 3 columnas según el
    ancho + pasillo GX entre columnas.
    Rediseño 2026-07-15 (socio: "que se llene bien esa parte central"): el
    cubículo ahora lleva TEXTO (tarea/tagline), no un sprite de 12 celdas, así
    que necesita cuerpo — mínimo 24 por columna (antes 18: a ese ancho la
    tarea se cortaba en 3 palabras) y tope 40 (antes 30). Con menos ancho
    prefiere MENOS columnas y cajas GRANDES: mejor 2 cubículos legibles que 3
    ilegibles."""
    gx = 3
    ncols = 1
    for c in (3, 2):
        if c <= n and c * 18 + (c - 1) * gx <= cw:
            ncols = c
            break
    wsw = min(30, (cw - (ncols - 1) * gx) // ncols)
    return ncols, max(14, wsw), gx


def _ws_cards_grid(ags, view, K, cw, ch, anim, size="std"):
    """El PISO del mission-control como GRID de CUBÍCULOS ESPACIADOS: 2-3 por
    fila según el ancho, con pasillo entre columnas y una fila de AIRE entre
    filas; el bloque centrado horizontal y (con ch>0) verticalmente. Cada
    cubículo lo pinta _ws_card (interior limpio). ch<=0 ⇒ altura NATURAL
    (apilado/--banner). La geometría depende solo de (agentes, cw, ch, size),
    jamás de la selección ni del frame (la altura es estable)."""
    K = cols(K)
    if not ags:
        base = [clip("%ssin agentes — el piso está vacío%s"
                     % (K["DIM"], K["R"]), cw)]
        return (base + [""] * ch)[:ch] if ch > 0 else base
    gsel = min(view.get("gsel", 0), len(ags) - 1)
    focused = view.get("focus") == "dioses"
    n = len(ags)
    ncols, wsw, gx = _cards_dims(cw, n)
    nrows = (n + ncols - 1) // ncols
    gy = 1                                        # una fila de aire entre filas
    # ESCALERA RESPONSIVE (2026-07-15, socio: "que cambie conforme el tamaño
    # de la ventana"): con alto Y ancho de sobra el puesto se despliega GRANDE
    # (_ws_sprite_big: monitor ancho de 2 líneas + teclado + manos); si no
    # cabe baja a std y luego a mini. Alto por cubículo: big 10 · std 6 · mini 3.
    if ch > 0 and size != "mini":
        if size == "std" and wsw >= 22 \
                and nrows * 10 + (nrows - 1) * gy <= ch:
            size = "big"                          # hay lugar: el puesto crece
        elif nrows * 6 + (nrows - 1) * gy > ch:
            size = "mini"                         # no cabe std → mini
    lines = []
    for base in range(0, n, ncols):
        if lines:
            lines += [""] * gy
        chunk = ags[base:base + ncols]
        cards = [_ws_card(a, K, wsw, anim, base + j == gsel, focused,
                          size=size) for j, a in enumerate(chunk)]
        used = wsw * len(chunk) + gx * (len(chunk) - 1)
        lead = " " * max(0, (cw - used) // 2)
        pad_gx = " " * gx
        for r in range(len(cards[0])):
            lines.append(clip(lead + pad_gx.join(c[r] for c in cards), cw))
    if ch <= 0:
        return lines
    top = max(0, (ch - len(lines)) // 2)          # centrado vertical
    return ([""] * top + lines + [""] * ch)[:ch]


def _centro_agent_rows(data, view, K, w, indent="", inbox_badge=True,
                       solo_nombre=False):
    """Tira AGENTES del centro (1 línea c/u): `▸ ▮ Nombre ● ⎇ ✉N tarea` —
    el bloque ▮ va en el color de MARCA del agente (identidad instantánea,
    feedback 2026-07-04: más color), punto de estado semántico (◐ busy ·
    ● activo · ○ idle · · pronto), señales vivas del snapshot si la fila
    respira (worktree ⎇ y bus ✉N pendientes — solo con fuente) y la tarea
    viva (now.json) o el rol. + fila de aviso (view.msg) SIEMPRE reservada.
    Altura = agentes + 1 (solo depende de data — estable)."""
    K = cols(K)
    agents = list(data.get("agents") or ())
    focus = view.get("focus") == "dioses"
    gsel = min(view.get("gsel", 0), max(0, len(agents) - 1))
    namew = min(12 if w >= 40 else 10,
                max([vis(a.get("display", "")) for a in agents] or [6]))
    out = []
    for i, a in enumerate(agents):
        bright, _dimc = _agent_ink(a.get("color"), K)
        sel = (i == gsel)
        task = (a.get("task") or "").strip()
        if task:
            est = (a.get("state") or "").strip().lower()
            glyph, gcol = (("◐", K["C"] + K["BO"])
                           if est in ("busy", "ocupado", "corriendo",
                                      "running")
                           else ("●", K["OK"] + K["BO"]))
            sub = task
        elif a.get("active"):
            glyph, gcol, sub = "○", K["DIM"], (a.get("tagline") or "idle")
        else:
            glyph, gcol, sub = "·", K["DK"], (a.get("tagline") or "pronto")
        mark = ("%s▸ %s" % (K["B"] + K["BO"], K["R"])) if (sel and focus) \
            else "  "
        brand = (bright + K["BO"]) if a.get("active") else K["DK"]
        ncol = (K["WH"] + K["BO"]) if sel else (
            K["INACTIVE"] if a.get("active") else K["DK"])
        tcol = (K["WH"] if sel else K["GREY"]) if task else K["DIM"]
        badges = ""                              # señales vivas del snapshot
        if w >= 26:                              # solo si la fila respira
            if (a.get("_wt") or "").strip():
                badges += "%s%s%s " % (K["B2"], K["BRANCH"], K["R"])
            # el buzón por agente se puede apagar (`inbox_badge=False`): en el
            # layout `dia` el bus ya está resumido en PULSO y ese `✉38` solo
            # le comía columnas al nombre y la tarea (pedido del socio
            # 2026-09-24). `centro` lo conserva.
            if inbox_badge and a.get("_inbox"):
                badges += "%s%s%s%s " % (K["B2"], K["MAIL"], a["_inbox"],
                                         K["R"])
        if solo_nombre:
            # `dia`: la lista es para ELEGIR, no para informar — el nombre y
            # su punto de estado, nada más (pedido del socio 2026-09-24: fuera
            # taglines y «última sesión»; lo que hace el agente ya se ve en
            # PESTAÑAS).
            out.append(clip("%s%s%s▮%s %s%s%s %s%s%s" % (
                indent, mark, brand, K["R"], ncol, a.get("display", ""),
                K["R"], gcol, glyph, K["R"]), w - 1))
            continue
        out.append(clip("%s%s%s▮%s %s%s%s %s%s%s %s%s%s%s" % (
            indent, mark, brand, K["R"], ncol,
            pad(a.get("display", ""), namew), K["R"], gcol, glyph, K["R"],
            badges, tcol, sub, K["R"]), w - 1))
    if not agents:
        out.append(clip("%s%ssin agentes — MENÚ ▸ Agregar agente%s"
                        % (indent, K["DIM"], K["R"]), w - 1))
    out.append(clip("%s%s%s%s" % (indent, K["DIM"], view.get("msg") or "",
                                  K["R"]), w - 1) if view.get("msg")
               else "")                       # fila de aviso SIEMPRE reservada
    return out


def _centro_strip(K, w, indent=" "):
    """Tira de OPERACIONES bajo los instrumentos (feedback 2026-07-04:
    llenar ARRIBA con datos vivos): misiones del taskboard por fase,
    energía de la cuenta y avisos de liveness — todo del snapshot del
    Centro. [] si el snapshot no está (nada inventado, la fila se OMITE).
    En angosto suelta segmentos por la derecha — jamás desborda."""
    K = cols(K)
    snap = _centro_snapshot() or {}
    segs = []
    tb = snap.get("taskboard")
    if isinstance(tb, dict) and isinstance(tb.get("total"), int):
        fases = "  ".join(
            "%s%s %s%s%s" % (K["DIM"], p, K["WH"] + K["BO"], tb.get(p, 0),
                             K["R"])
            for p in ("plan", "exec", "review", "done"))
        segs.append("%s◧ %smisiones %s%d%s  %s" % (
            K["B"] + K["BO"], K["DIM"], K["WH"] + K["BO"], tb["total"],
            K["R"], fases))
    cta = snap.get("cuenta")
    if isinstance(cta, dict) and cta.get("energia_pct") is not None:
        segs.append("%senergia %s" % (K["DIM"],
                                      gauge(K, 8, cta["energia_pct"],
                                            col=K["OK"] + K["BO"])))
    warns = snap.get("warns")
    if isinstance(warns, list) and warns:
        segs.append("%s▲ %d aviso%s%s" % (K["ERR"] + K["BO"], len(warns),
                                          "" if len(warns) == 1 else "s",
                                          K["R"]))
    if not segs:
        return []
    while segs:
        ln = indent + "   ".join(segs)
        if vis(ln) <= w - 1:
            return [clip(ln, w - 1)]
        segs.pop()                               # angosto: suelta el menos vital
    return []


def _detalles_body(a, K, inner):
    """Cuerpo del panel DETALLES del agente seleccionado: identidad + estado
    vivo (now.json) + worktree + bus + misiones + rol. Cada dato SOLO si su
    fuente existe. El caller fija la altura (full_box ih) — aquí solo
    contenido."""
    K = cols(K)
    if a is None:
        return [clip("%ssin agentes — MENÚ ▸ Agregar agente%s"
                     % (K["DIM"], K["R"]), inner)]
    bright, _dimc = _agent_ink(a.get("color"), K)
    out = [clip("%s%s%s%s" % (K["WH"] + K["BO"], a.get("display", ""),
                              K["R"], ("  %s%s%s" % (K["DIM"],
                                                     a.get("engine"), K["R"]))
                if a.get("engine") else ""), inner),
           clip("%s%s%s" % (bright, "─" * min(inner, 18), K["R"]), inner)]
    task = (a.get("task") or "").strip()
    if task:
        est = (a.get("state") or "working").strip()
        upd = a.get("_upd")                      # hora real del now.json
        when = ("  %s%s%s" % (K["DK"], _act_when(upd), K["R"])) if upd \
            else ""
        out.append(clip("%s●%s %s%s%s%s" % (K["OK"] + K["BO"], K["R"],
                                            K["WH"], est, K["R"], when),
                        inner))
        out += [clip("%s%s%s" % (K["GREY"], ln, K["R"]), inner)
                for ln in _wrap(task, inner - 1, 3)]
    elif a.get("active"):
        out.append(clip("%s○ idle · sin tarea publicada%s"
                        % (K["DIM"], K["R"]), inner))
    else:
        out.append(clip("%s· pronto%s" % (K["DK"], K["R"]), inner))
    wts = [b for b in (a.get("_wts") or ()) if b] \
        or ([a["_wt"].strip()] if (a.get("_wt") or "").strip() else [])
    if wts:
        shown = min(len(wts), 2 if inner >= 26 else 1)  # panel ancho: 2 ramas
        extra = " +%d" % (len(wts) - shown) if len(wts) > shown else ""
        body = (" %s·%s " % (K["DIM"], K["WH"])).join(wts[:shown])
        out.append(clip("%s%s %s%s%s%s%s" % (K["B2"], K["BRANCH"], K["WH"],
                                             body, K["DIM"], extra, K["R"]),
                        inner))
    if a.get("_inbox") is not None:
        out.append(clip("%s%s %sbus %s%s pendientes%s" % (
            K["B2"], K["MAIL"], K["DIM"], K["WH"], a["_inbox"], K["R"]),
            inner))
    mis = a.get("_mis")
    if mis:
        out.append(clip("%smisiones %s%s%s" % (
            K["DIM"], K["WH"],
            " · ".join("%s %s" % (p, mis.get(p, 0))
                       for p in ("plan", "exec", "review", "done")),
            K["R"]), inner))
    tag = (a.get("tagline") or "").strip()
    if tag:
        out.append("")
        out += [clip("%s%s%s" % (K["DIM"], ln, K["R"]), inner)
                for ln in _wrap(tag, inner - 1, 3)]
    return out


def _dia_agentes_body(data, view, K, inner, aviso=True, hits=None):
    """AGENTES del layout `dia`: una fila por agente que USA el ancho —
    tecla de SALTO directo (si data trae "keys"), semáforo de ESTADO, nombre
    y, a la derecha, el estado en palabra.

        ▸1 ▮ Zenith                activo
         2 ▮ Atlas                  listo

    La tecla vive JUNTO a su opción (transparencia del salto: el dígito hace
    flechas+Enter de un golpe — front._jump_map). Sin "keys" en data
    (banner/tests viejos) la fila es la de siempre, byte-idéntica. `hits`
    (lista opcional): se le anexan (fila_relativa_0based, "agent", i) — el
    hit-map que el mouse usa para click = saltar + entrar.

    El cuadrito ▮ ya NO es marca de identidad por agente (con muchos agentes
    el arcoíris no escala — pedido del socio 2026-10-02): es un SEMÁFORO de
    estado, SIEMPRE en roles del tema (jamás 256 hardcodeado). 4 estados:
        activo  — corriendo (tarea viva + state busy)   → K.OK (verde)
        en uso  — sesión abierta con tarea, sin busy    → K.C  (acento)
        listo   — agente activo, sin tarea viva         → K.DIM (tenue)
        pronto  — planeado / apagado                    → K.DK  (más tenue)
    Cuadrito y palabra comparten color: una sola señal, dos lecturas.

    El nombre del agente seleccionado toma el tono brillante del gradiente
    del wordmark (K.WCOL), que es el mismo lenguaje del título: la selección
    se lee sin buscar el cursor."""
    K = cols(K)
    agentes = list(data.get("agents") or ())
    foco = view.get("focus") == "dioses"
    gsel = min(view.get("gsel", 0), max(0, len(agentes) - 1))
    wc = K["WCOL"]
    jk = (data.get("keys") or {}).get("agents") or {}
    out = []
    for i, a in enumerate(agentes):
        sel = (i == gsel)
        tarea = (a.get("task") or "").strip()
        est = (a.get("state") or "").strip().lower()
        if tarea:
            # palabras CORTAS: en una columna de 20 «trabajando» se
            # corta, y un estado recortado no es un estado
            if est in ("busy", "ocupado", "corriendo", "running",
                       "working"):
                palabra, pcol = "activo", K["OK"]
            else:
                palabra, pcol = "en uso", K["C"]
        elif a.get("active"):
            palabra, pcol = "listo", K["DIM"]
        else:
            palabra, pcol = "pronto", K["DK"]
        cursor = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if (
            sel and foco) else " "
        # semáforo: mismo tono que la palabra; BOLD solo con vida (tarea) —
        # lo quieto se queda tenue y el ojo va directo a lo que corre
        marca = (pcol + K["BO"]) if tarea else pcol
        ncol = (wc[i % len(wc)] + K["BO"]) if sel else (
            K["INACTIVE"] if a.get("active") else K["DK"])
        nombre = a.get("display", "")
        nombre_txt = "%s%s%s" % (ncol, nombre, K["R"])
        if hits is not None:
            hits.append((len(out), "agent", i))
        if jk:
            # tecla de salto en la columna del hueco del cursor: «▸1 ▮ …».
            # La del agente seleccionado+foco sube a DIM (se lee primero);
            # el resto en DK (penumbra, no satura la columna).
            kd = "%s%s%s" % (K["DIM"] if (sel and foco) else K["DK"],
                             jk.get(i, " "), K["R"])
            hueco = max(1, inner - 5 - vis(nombre_txt) - vis(palabra))
            out.append(clip("%s%s %s▮%s %s%s%s%s%s" % (
                cursor, kd, marca, K["R"], nombre_txt, " " * hueco,
                pcol, palabra, K["R"]), inner))
            continue
        hueco = max(1, inner - 4 - vis(nombre_txt) - vis(palabra))
        out.append(clip("%s %s▮%s %s%s%s%s%s" % (
            cursor, marca, K["R"], nombre_txt, " " * hueco,
            pcol, palabra, K["R"]), inner))
    if not agentes:
        out.append(clip("%ssin agentes — MENÚ ▸ Agregar agente%s"
                        % (K["DIM"], K["R"]), inner))
    else:
        # Selector de HARNESS inline (harness-os): el binding efectivo del
        # agente SELECCIONADO, valor a la derecha (mismo lenguaje que
        # CONFIGS) + ▾ de "ciclable". `m` lo cambia (front.cycle_engine) y
        # queda guardado per-máquina (● = override local). SIEMPRE 1 línea
        # (la altura de la caja no depende de la selección).
        a = agentes[gsel]
        eng = (a.get("engine_eff") or a.get("engine") or "?").strip() or "?"
        loc = "%s●%s " % (K["C"], K["R"]) if a.get("engine_src") == "local" \
            else ""
        lab = "%smotor%s" % (K["DIM"] if foco else K["DK"], K["R"])
        val = "%s%s%s %s▾%s" % ((K["C"] + K["BO"]) if foco else K["B2"],
                                eng, K["R"], K["DK"], K["R"])
        # adaptativo: con etiqueta si cabe; si no, solo el valor a la derecha
        # (en la columna de `dia` inner≈20 y `motor claude-code ▾` no entra).
        if vis(lab) + vis(loc) + vis(val) + 3 <= inner:
            hueco = max(1, inner - 2 - vis(lab) - vis(loc) - vis(val))
            out.append(clip("  %s%s%s%s" % (lab, " " * hueco, loc, val),
                            inner))
        else:
            hueco = max(0, inner - 2 - vis(loc) - vis(val))
            out.append(clip("  %s%s%s" % (" " * hueco, loc, val), inner))
    if aviso:
        out.append(clip("%s%s%s" % (K["DIM"], view.get("msg") or "",
                                    K["R"]), inner)
                   if view.get("msg") else "")
    return out


# Grupos del MENÚ: lo que ABRE una superficie vs lo que opera el harness. El
# separador entre ambos le da ritmo a la columna (y deja de ser una lista de
# ocho cosas indistinguibles).
_DIA_MENU_SISTEMA = ("__doctor__", "__add_agent__", "__shell__")


def _dia_menu_body(data, view, K, inner, separador=True, hits=None):
    """MENÚ del layout `dia`: UNA opción por fila (con ocho entradas, dos por
    renglón se encimaban), con el cursor a la izquierda, la tecla de SALTO
    junto a cada opción (si data trae "keys" — «❯5 Ramas» … « q Terminal
    normal») y el elegido en el tono brillante del gradiente del wordmark.
    Una regla tenue separa las superficies de las operaciones del harness.
    Sin "keys" la columna es la de siempre. `hits` (lista opcional): se le
    anexan (fila_relativa_0based, "opt", j) para el hit-map del mouse."""
    K = cols(K)
    foco = view.get("focus") == "tools"
    sel = view.get("asel", 0)
    wc = K["WCOL"]
    jk = (data.get("keys") or {}).get("opts") or {}
    out, puesto = [], False
    for j, (tok, lbl) in enumerate(data.get("opts") or ()):
        if separador and tok in _DIA_MENU_SISTEMA and not puesto:
            puesto = True
            out.append("%s%s%s" % (K["DK"], K["SEP"] * max(3, inner - 2),
                                   K["R"]))
        activo = (j == sel)
        if hits is not None:
            hits.append((len(out), "opt", j))
        # tecla de salto en su propia columna, alineada bajo el cursor: la
        # de la opción activa+foco en DIM (se lee primero), el resto en DK.
        kd = ""
        if jk:
            kd = "%s%s%s" % (K["DIM"] if (activo and foco) else K["DK"],
                             jk.get(j, " "), K["R"])
        if activo and foco:
            out.append(clip("%s%s%s%s %s%s%s%s" % (
                K["C"] + K["BO"], K["PTR"], K["R"], kd,
                wc[j % len(wc)], K["BO"], lbl, K["R"]), inner) if jk else
                clip("%s%s %s%s%s%s" % (
                    K["C"] + K["BO"], K["PTR"], wc[j % len(wc)], K["BO"],
                    lbl, K["R"]), inner))
        elif activo:
            out.append(clip("%s%s%s%s %s%s%s" % (
                K["DK"], K["PTR"], K["R"], kd, K["WH"], lbl, K["R"]), inner)
                if jk else
                clip("%s%s %s%s%s" % (K["DK"], K["PTR"], K["WH"],
                                      lbl, K["R"]), inner))
        else:
            # PROFUNDIDAD en grises (toque 2026-10-02, el juego del Tono):
            # los vecinos de la selección conservan el tono inactivo del
            # tema; de 3 lugares en adelante se hunden a DK — la columna
            # se lee como un foco con penumbra, no una lista plana.
            tinta = K["DK"] if abs(j - sel) >= 3 else K["INACTIVE"]
            out.append(clip(" %s %s%s%s" % (kd, tinta, lbl, K["R"]), inner)
                       if jk else
                       clip("  %s%s%s" % (tinta, lbl, K["R"]), inner))
    return out or [""]


# Etiquetas CORTAS de los pins: el label del schema («Tema del hub», «Modo del
# latido») se recorta a «Tema del …» en una columna de 22 y deja de informar.
_DIA_PIN_CORTO = {"ui.background": "fondo", "ui.theme": "tema", "ui.layout": "layout",
                  "latido.mode": "latido", "ui.split": "split",
                  "ui.stars": "estrellas", "ui.anim": "animación"}


def _dia_cfg_body(data, view, K, inner, hint=True, hits=None):
    """CONFIGS del layout `dia`: etiqueta corta a la izquierda, VALOR a la
    derecha, cursor en el pin enfocado. Que el valor esté alineado a la
    derecha es lo que hace la columna legible de un vistazo (antes el label
    se comía el ancho y el valor quedaba recortado). Sin dígito de salto
    (el presupuesto 1-9 es de agentes+MENÚ — ver front._jump_map), pero SÍ
    clickeable: `hits` (lista opcional) recibe (fila_relativa, "pin", i) y
    el click enfoca + cicla el pin (lo que haría Enter)."""
    K = cols(K)
    try:
        import settings as _st
        pins = _st.hub_pins_resolved()
    except Exception:
        pins = []
    if not pins:
        return []
    foco = view.get("focus") == "latido"
    cf = view.get("cfg_focus", 0) % max(1, len(pins))
    out = []
    for i, p in enumerate(pins):
        if hits is not None:
            hits.append((len(out), "pin", i))
        lab = _DIA_PIN_CORTO.get(p.get("key", ""), "") or \
            (p.get("label") or "").split(" ")[0].lower()
        val = str(p.get("value", ""))
        sel = (i == cf)
        cursor = "%s%s%s" % (K["C"] + K["BO"], K["PTR"], K["R"]) if (
            sel and foco) else " "
        lab_txt = "%s%s%s" % (K["WH"] if sel else K["DIM"], lab, K["R"])
        hueco = max(1, inner - 2 - vis(lab_txt) - vis(val))
        out.append(clip("%s %s%s%s%s%s" % (
            cursor, lab_txt, " " * hueco,
            (K["C"] + K["BO"]) if sel else K["B2"], val, K["R"]), inner))
    if view.get("hb_msg"):
        out.append(clip("%s%s%s" % (K["DIM"], view["hb_msg"], K["R"]), inner))
    elif hint:
        out.append(clip("%sEnter cambia%s" % (K["DK"], K["R"]), inner))
    return out


def _centro_menu_body(data, view, K, inner):
    """Cuerpo de la caja MENÚ del centro: las ACCIONES del recinto
    (Config/Doctor/Agregar agente/Terminal) — misma sección MENÚ que en
    clásico, enfocable (focus == 'tools')."""
    K = cols(K)
    return action_rows(data, view, K, inner + 1, indent="", gap="  ") or [""]


def _centro_cfg_body(data, view, K, inner, dense=False):
    """Cuerpo de la caja CONFIGS rápidas del centro: los pins EDITABLES
    (ui.hub_pins) — MISMO bloque que en clásico (latido.mode es UN pin más;
    el radio del latido suelto ya no existe). Enfocable (focus == 'latido'):
    el pin bajo el cursor se resalta y con la fila de aviso reservada dentro.
    Falla-suave: sin pins la caja no crece."""
    K = cols(K)
    out = hub_pins_lines(K, inner + 1, indent="", hint=not dense, view=view)
    if out:
        # aviso del cambio (S['hb_msg']) DENTRO de la sección — SIEMPRE
        # reservado (BH estable), como el latido de antes.
        out.append(clip("%s%s%s" % (K["DIM"], view.get("hb_msg") or "",
                                    K["R"]), inner)
                   if view.get("hb_msg") else "")
    return out


def _centro_cols(w):
    """Anchuras (lw, rw, cw) de las 3 columnas del centro. Lados ANCHOS
    (feedback del socio: quedaban achocados en terminales anchas —
    selección incómoda y dato vivo que no cabía): izquierda 26% cap 44,
    derecha 30% cap 52. INVARIANTE: el centro conserva cw ≥ 30 siempre
    que w-1 ≥ 85 (los cubículos big piden ≥ 26) — si los pisos de los
    lados lo invaden, cede la derecha."""
    lw = max(24, min(44, (w - 1) * 26 // 100))
    rw = max(28, min(52, (w - 1) * 30 // 100))
    cw = w - 1 - lw - rw - 4
    if cw < 30:
        rw -= 30 - cw
        cw = 30
    return lw, rw, cw


def render_centro(data, view, K, w):
    """`centro` (ver _centro_lines) — título grande si cabe (_fit)."""
    return _fit(_centro_lines, data, view, K, w)


def _centro_lines(data, view, K, w, compact=False, dense=False):
    """`centro` — Centro de Control, TABLERO COMPLETO (feedback del socio
    2026-07-04: usa el espacio, más color, datos vivos en lados y arriba):
    título neón + instrumentos + tira de OPERACIONES (misiones/energía/
    avisos del snapshot); TRES columnas — IZQUIERDA las 3 SECCIONES del hub
    (AGENTES — marca de color por agente, navegable: ↑↓ sección · ◄► elige —
    · MENÚ · CONFIGS rápidas, iguales que en clásico) + MONITOR
    (gauges/bus/commits, absorbe el alto sobrante), CENTRO el PISO de la
    oficina (_ws_cards_grid: cubículos ┌─ Nombre ─┐ repartidos en grid con
    aire, sprites que animan por frame — escalera std → mini según el alto),
    DERECHA DETALLES (alto FIJO, borde en
    la marca del seleccionado) + ACTIVIDAD (bus+git, absorbe el alto).
    En angosto
    (<85) se apila. La altura llena view.h exacto y no depende de la
    selección ni del frame de animación."""
    K = cols(K)
    focus = view.get("focus")
    h = view.get("h") or 0
    anim = int(view.get("anim") or 0)
    hchar = K["BOX"][5]
    ags = _centro_agents(data)
    dsel = ags[min(view.get("gsel", 0), len(ags) - 1)] if ags else None
    ldata = dict(data, agents=ags)               # tarea/estado FRESCOS
    # ── título + build + regla + instrumentos + operaciones ──
    L = [] if (compact or dense) else [""]
    bt = big_title(K, w, h, indent=" ", right=branch_widget(K),
                   compact=compact)
    L += bt
    if len(bt) > 1:
        L += title_reflection(K, w, indent=" ")
    build = " · ".join(p for p in (
        "centro de control",
        ("v" + data["version"]) if data.get("version") else "",
        data.get("version_text") or "", data.get("motor") or "") if p)
    L.append(clip(" %s%s%s" % (K["DIM"], build, K["R"]), w - 1))
    L.append(clip("%s%s%s%s%s" % (K["B2"], hchar * 3, K["DK"],
                                  hchar * max(1, w - 5), K["R"]), w - 1))
    L.append(clip(instrument_bar(data, view, K, w, indent=" "), w - 1))
    L += _centro_strip(K, w)                     # [] sin snapshot (se omite)
    L.append("")
    top_n = len(L)
    status = bottom_statusline(data, view, K, w)
    gap1, tail = (0, 1) if dense else (1, 2)
    ag_title = "AGENTES · %d" % len(ags) if ags else "AGENTES"
    doff = K.get("OFF") or K["DK"]
    dlabel = K["B"] + K["BO"]
    if w - 1 >= 85:                              # ── TRES COLUMNAS ──
        lw, rw, cw = _centro_cols(w)
        # 3 SECCIONES iguales que en clásico: AGENTES · MENÚ · CONFIGS
        ab = _centro_agent_rows(ldata, view, K, lw - 3)
        menu = _centro_menu_body(data, view, K, lw - 4)
        cfg = _centro_cfg_body(data, view, K, lw - 4, dense=dense)
        left = full_box(ag_title, ab, K, lw, len(ab), focus == "dioses",
                        border=K["C"])
        left += [""] * gap1
        left += full_box("MENÚ", menu, K, lw, len(menu),
                         focus == "tools", border=K["B2"])
        if cfg:
            left += [""] * gap1
            left += full_box("PERSONALIZACIÓN", cfg, K, lw, len(cfg),
                             focus == "latido", border=K["B2"])
        # workstations: GRID de CUBÍCULOS espaciados (rediseño 2026-07-08 —
        # cuadritos con aire, sin jerarquía ni aristas); std → mini según alto
        size_fit = "mini" if dense else "std"
        ws = _ws_cards_grid(ags, view, K, cw, 0, anim, size=size_fit)  # natural
        # lados anchos ⇒ MÁS dato real: sparkline de 24h si el MONITOR
        # respira, más eventos en ACTIVIDAD y conteos por fuente en su
        # título (todo con fuente viva; sin fuente se OMITE — nada inventado)
        mb = monitor_body(ldata, K, lw - 4, hours=24 if lw >= 34 else 12)
        act = activity_rows(K, rw - 4, limit=12)
        n_bus = len(_bus_recent(12) or ())
        n_git = len(_git_log(12) or ())
        act_bits = (["bus %d" % n_bus] if n_bus else []) \
            + (["git %d" % n_git] if n_git else [])
        act_t = "ACTIVIDAD" + ((" · " + " · ".join(act_bits)) if act_bits
                               else "")
        # DETALLES se AJUSTA al contenido del seleccionado (feedback: el
        # hueco vacío cuando el agente trae poco) — piso 7, techo 13;
        # ACTIVIDAD absorbe el alto que DETALLES suelte. No mueve la altura
        # total (la columna derecha se rellena a ch exacto).
        det_body = _detalles_body(dsel, K, rw - 4)
        det_ih = max(7, min(13, len(det_body)))
        if h:
            ch = max(4, (h - 1) - top_n - tail)
        else:                                    # natural (--banner sin alto)
            lnat = len(left) + ((min(len(mb), 8) + 2 + gap1) if mb else 0)
            rnat = det_ih + 2 + ((min(len(act), 6) + 2 + gap1) if act
                                 else 0)
            ch = max(lnat, len(ws), rnat, 14)
        # el piso llena ch exacto: cubículos centrados en el alto disponible
        ws = _ws_cards_grid(ags, view, K, cw, ch, anim, size=size_fit)
        # derecha: DETALLES fijo (borde = marca del seleccionado) +
        # ACTIVIDAD absorbe el resto del alto
        rest_r = ch - (det_ih + 2) - gap1 - 2
        if not (act and rest_r >= 3):
            det_ih = max(1, ch - 2)              # sin lugar → DETALLES llena
        dborder = _agent_ink(dsel.get("color"), K)[1] if dsel else doff
        right = full_box("DETALLES", det_body, K,
                         rw, det_ih, False, border=dborder, label=dlabel)
        if act and rest_r >= 3:
            right += [""] * gap1
            right += full_box(act_t, act, K, rw, rest_r, False,
                              border=doff, label=dlabel)
        # izquierda: MONITOR absorbe el resto del alto
        rest_l = ch - len(left) - gap1 - 2
        if mb and rest_l >= 3:
            left += [""] * gap1
            left += full_box("MONITOR · vivo", mb, K, lw, rest_l, False,
                             border=doff, label=dlabel)
        left += [""] * max(0, ch - len(left))
        ws += [""] * max(0, ch - len(ws))
        right += [""] * max(0, ch - len(right))
        for i in range(ch):
            L.append(clip(pad(left[i], lw) + "  " + pad(ws[i], cw) + "  "
                          + right[i], w - 1))
    else:                                        # ── angosto: APILADO ──
        pw = w - 1
        ab = _centro_agent_rows(ldata, view, K, pw - 3)
        L += full_box(ag_title, ab, K, pw, len(ab), focus == "dioses",
                      border=K["C"])
        L += _ws_cards_grid(ags, view, K, pw, 0, anim,
                            size="mini" if dense else "std")
        db = _detalles_body(dsel, K, pw - 4)
        ihd = 6 if dense else 8
        L += full_box("DETALLES", db, K, pw, ihd, False, border=doff,
                      label=dlabel)
        # 3 SECCIONES iguales que en clásico: AGENTES (arriba) · MENÚ · CONFIGS
        menu = _centro_menu_body(data, view, K, pw - 4)
        L += full_box("MENÚ", menu, K, pw, len(menu),
                      focus == "tools", border=K["B2"])
        cfg = _centro_cfg_body(data, view, K, pw - 4, dense=dense)
        if cfg:
            L += full_box("PERSONALIZACIÓN", cfg, K, pw, len(cfg),
                          focus == "latido", border=K["B2"])
    L += ([""] if tail == 2 else []) + [status]
    return vfill(L, view, tail=tail)


# ── LAYOUT: dia — «El día»: tu día al centro + pulso vivo a la derecha ──────
# Dirección del socio (2026-09-23, HUB-REDISENO-2026-09.md opción A): la
# columna IZQUIERDA del centro se queda igual (AGENTES · MENÚ · CONFIGS —
# mismas cajas, misma navegación ↑↓ ◄►); el resto del hub deja de ser
# decoración y pasa a ser INFORMACIÓN: al centro TU DÍA (reloj, fecha,
# avance del día, foco, agenda, pendientes con deadline) y a la derecha el
# PULSO VIVO del harness (uso 5h + cuánto falta para el reset, qué agente
# está corriendo qué herramienta AHORA, ritmo de tool-calls, bus y
# actividad).
#
# Todo dato tiene FUENTE REAL y su propio TTL — sin fuente el widget se
# OMITE (jamás se inventa un número):
#   · foco/agenda  → personal.py  (~/.claude/workspace/personal.json, local)
#   · pendientes   → STATE/PENDIENTES.md del cerebro (dash._common)
#   · uso 5h/reset → heartbeat.state().budget
#   · ahora/ritmo  → ~/.claude/workspace/telemetry/*.jsonl (hooks N-telem)
#   · bus/commits  → messages.py + git (los memos compartidos de arriba)
# La altura NO depende de la selección ni del frame (contrato del redraw).

# Dígitos en la MISMA fuente del wordmark (ANSI Shadow) — pedido del socio
# 2026-09-24: "que el diseño del reloj sea el mismo que el de las letras del
# título". Se pintan con `_neon_row` y el gradiente del tema, idéntico al
# título. Cada dígito se acolcha a un ANCHO FIJO (_DIA_CELL) para que la hora
# no baile al pasar de 11 a 12 (un '1' es más angosto que un '8').
_DIA_SHADOW = {
    "0": (" █████╗ ", "██╔══██╗", "██║  ██║", "██║  ██║", "╚█████╔╝",
          " ╚════╝ "),
    "1": (" ██╗", "███║", "╚██║", " ██║", " ██║", " ╚═╝"),
    "2": ("██████╗ ", "╚════██╗", " █████╔╝", "██╔═══╝ ", "███████╗",
          "╚══════╝"),
    "3": ("██████╗ ", "╚════██╗", " █████╔╝", " ╚═══██╗", "██████╔╝",
          "╚═════╝ "),
    "4": ("██╗  ██╗", "██║  ██║", "███████║", "╚════██║", "     ██║",
          "     ╚═╝"),
    "5": ("███████╗", "██╔════╝", "███████╗", "╚════██║", "███████║",
          "╚══════╝"),
    "6": (" █████╗ ", "██╔════╝", "██████╗ ", "██╔══██╗", "╚█████╔╝",
          " ╚════╝ "),
    "7": ("███████╗", "╚════██║", "    ██╔╝", "   ██╔╝ ", "   ██║  ",
          "   ╚═╝  "),
    "8": (" █████╗ ", "██╔══██╗", "╚█████╔╝", "██╔══██╗", "╚█████╔╝",
          " ╚════╝ "),
    "9": (" █████╗ ", "██╔══██╗", "╚██████║", " ╚═══██║", " █████╔╝",
          " ╚════╝ "),
    ":": ("   ", "██╗", "╚═╝", "██╗", "╚═╝", "   "),
}
_DIA_CELL = 8                    # ancho fijo por dígito — «HH:MM» = 35 col
# (los glifos ya traen su propio aire lateral: se pegan SIN separador,
#  igual que las letras del wordmark)

_DIA_MESES_LARGO = ("enero", "febrero", "marzo", "abril", "mayo", "junio",
                    "julio", "agosto", "septiembre", "octubre", "noviembre",
                    "diciembre")
_DIA_MESES = ("ene", "feb", "mar", "abr", "may", "jun",
              "jul", "ago", "sep", "oct", "nov", "dic")
_DIA_DIAS = ("lunes", "martes", "miércoles", "jueves", "viernes",
             "sábado", "domingo")

# Dígitos 3×5 en bloques (Windows-safe: solo U+2588 y espacio). El reloj
# grande es TEXTO, no arte: se redibuja con la hora, no con el frame.
_DIA_GLYPHS = {
    "0": ("███", "█ █", "█ █", "█ █", "███"),
    "1": ("  █", "  █", "  █", "  █", "  █"),
    "2": ("███", "  █", "███", "█  ", "███"),
    "3": ("███", "  █", "███", "  █", "███"),
    "4": ("█ █", "█ █", "███", "  █", "  █"),
    "5": ("███", "█  ", "███", "  █", "███"),
    "6": ("███", "█  ", "███", "█ █", "███"),
    "7": ("███", "  █", "  █", "  █", "  █"),
    "8": ("███", "█ █", "███", "█ █", "███"),
    "9": ("███", "█ █", "███", "  █", "███"),
    ":": (" ", "█", " ", "█", " "),
    " ": (" ", " ", " ", " ", " "),
}


def _dia_personal():
    """Foco + próximos eventos (personal.py). Memo TTL corto: son dos
    lecturas de UN json chico. Sin módulo/archivo → {} y se omite."""
    if not _sys_fresh("personal"):
        val = {}
        try:
            import personal
            hoy = datetime.date.today()
            dias = set()
            for e in personal.events():
                try:
                    d = datetime.datetime.strptime(e["date"],
                                                   "%Y-%m-%d").date()
                except Exception:
                    continue
                if (d.year, d.month) == (hoy.year, hoy.month):
                    dias.add(d.day)
            mes = {}
            for e in personal.events():
                try:
                    d = datetime.datetime.strptime(e["date"],
                                                   "%Y-%m-%d").date()
                except Exception:
                    continue
                if (d.year, d.month) == (hoy.year, hoy.month):
                    mes.setdefault(d.day, []).append(
                        {"time": e.get("time") or "",
                         "title": e.get("title") or "",
                         "done": bool(e.get("done")),
                         "prio": e.get("prio") or ""})
            for v in mes.values():
                v.sort(key=lambda x: x["time"] or "99:99")
            # `foco` y `upcoming` salieron del memo cuando la caja HOY paso
            # a ser calendario: nadie los pinta ya, y calcularlos cada 5s
            # era trabajo para nadie. El foco se consulta con `workspace
            # foco`; lo que viene se lee en la rejilla y en el dia a dia.
            # GOOGLE (gcal.py, fase 1 solo-lectura): se FUSIONA aqui para que
            # rejilla y paneles lo pinten sin tocar su codigo. gcal nunca
            # toca la red en este camino (cache + refresh en fondo) y falla
            # suave: sin URL/red la agenda local queda idantica.
            try:
                import gcal
                for d_num, g_evs in (gcal.events_month(hoy.year,
                                                       hoy.month) or {}).items():
                    dias.add(d_num)
                    for e in g_evs:
                        mes.setdefault(d_num, []).append(
                            {"time": e.get("time") or "",
                             "title": e.get("title") or "", "g": True})
            except Exception:
                pass
            for v in mes.values():
                # prioridad alta primero, luego hora; las HECHAS al final
                v.sort(key=lambda x: (1 if x.get("done") else 0,
                                      0 if x.get("prio") == "alta" else 1,
                                      x["time"] or "99:99"))
            # ATRASADAS: pendientes de días pasados (cualquier mes) — se
            # superficializan en PRÓXIMOS para que no se pierdan de vista
            try:
                atr = personal.overdue()
            except Exception:
                atr = []
            val = {"dias_mes": dias, "mes": mes, "atrasadas": atr}
        except Exception:
            val = {}
        _SYS_CACHE["personal"] = val
        _SYS_CACHE_TS["personal"] = time.monotonic()
    return _SYS_CACHE["personal"]


def _dia_brain():
    """Cerebro del que se leen los PENDIENTES: el del socio (zenith) si está
    registrado, si no el primero con ruta. None → la sección se omite."""
    cand = {}
    for s in (_centro_snapshot() or {}).get("agentes") or ():
        if isinstance(s, dict) and s.get("brain"):
            cand[s.get("name")] = s["brain"]
    if not cand:
        try:
            import agentsreg
            for a in agentsreg.agents() or ():
                if isinstance(a, dict) and a.get("brain"):
                    cand[a.get("name")] = a["brain"]
        except Exception:
            pass
    if not cand:
        return None
    return cand.get("zenith") or next(iter(cand.values()))


def _dia_pendientes():
    """Pendientes ABIERTOS del cerebro (STATE/PENDIENTES.md), los de
    deadline más cerca primero. TTL largo (60s): es leer y parsear un .md.
    Sin cerebro/archivo → [] y la sección se omite."""
    if not _sys_fresh("pend"):
        val = []
        try:
            from dash import _common as _C
            brain = _dia_brain()
            hoy = datetime.date.today()
            for it in _C.read_pendientes(brain) or ():
                if it.get("status") != "open":
                    continue
                dl, dias = (it.get("deadline") or "").strip(), None
                if dl:
                    iso = _C.parse_date(dl) or (dl if len(dl) == 10 else "")
                    try:
                        d = datetime.datetime.strptime(iso[:10],
                                                       "%Y-%m-%d").date()
                        dias = (d - hoy).days
                    except Exception:
                        dias = None
                val.append({"title": it.get("title") or "",
                            "who": (it.get("who") or "").strip(),
                            "section": it.get("section") or "",
                            "dias": dias})
            # orden de URGENCIA real: vencido RECIENTE primero (-1 antes
            # que -120: lo que se te acaba de pasar es lo accionable), luego
            # lo que viene por cercanía, y al final lo que no tiene fecha.
            def _urg(x):
                d = x["dias"]
                if d is None:
                    return (2, 0)
                return (0, -d) if d < 0 else (1, d)
            val.sort(key=_urg)
        except Exception:
            val = []
        _SYS_CACHE["pend"] = val
        _SYS_CACHE_TS["pend"] = time.monotonic()
    return _SYS_CACHE["pend"]


def _dia_telemetry(mins=20):
    """Pulso REAL del harness desde `~/.claude/workspace/telemetry/*.jsonl`
    (los hooks escriben una línea por tool_start/tool_end al instante):
      {"last": {"agent","tool","ts"} | None, "per_min": [int × mins]}
    Se lee solo la COLA de cada archivo (32 KB) — nunca el historial
    completo. Memo TTL 4s. Sin telemetría → None y los widgets se omiten."""
    if not _sys_fresh("tele"):
        val = None
        try:
            d = os.path.join(os.path.expanduser("~"), ".claude", "workspace",
                             "telemetry")
            now = time.time()
            per = [0] * mins
            last = None
            names = [n for n in os.listdir(d) if n.endswith(".jsonl")]
            for n in names[:12]:
                p = os.path.join(d, n)
                try:
                    if now - os.path.getmtime(p) > 86400:
                        continue          # archivo viejo: ni lo abras
                    with open(p, "rb") as f:
                        f.seek(0, os.SEEK_END)
                        size = f.tell()
                        f.seek(max(0, size - 32768))
                        chunk = f.read().decode("utf-8", "replace")
                except Exception:
                    continue
                for ln in chunk.splitlines()[1:]:
                    ln = ln.strip()
                    if not ln.startswith("{") or '"tool_start"' not in ln:
                        continue
                    try:
                        ev = json.loads(ln)
                    except Exception:
                        continue
                    ts = ev.get("ts")
                    if not isinstance(ts, (int, float)):
                        continue
                    age = (now - ts) / 60.0
                    if 0 <= age < mins:
                        per[mins - 1 - int(age)] += 1
                    if last is None or ts > last["ts"]:
                        last = {"agent": ev.get("agent") or "",
                                "tool": ev.get("tool") or "", "ts": ts}
            val = {"last": last, "per_min": per} if (last or any(per)) else None
        except Exception:
            val = None
        _SYS_CACHE["tele"] = val
        _SYS_CACHE_TS["tele"] = time.monotonic()
    return _SYS_CACHE["tele"]


def _dia_tabs(limit=6):
    """PESTAÑAS vivas del socio — la pregunta del socio: «¿qué sesión ya terminó
    de pensar y cuál sigue trabajando?». Se cruzan TRES fuentes reales, sin
    inventar nada:

      · `~/.claude/workspace/markers/<session_id>.json` — lo estampa el hook
        SessionStart: {brain, ws (nombre de la PESTAÑA), started}.
      · telemetría `<enc>.jsonl` — tool_start/tool_end POR session_id: si
        hay más starts que ends, esa pestaña tiene una herramienta CORRIENDO.
      · mtime del transcript `~/.claude/projects/<enc>/<sid>.jsonl` — última
        actividad REAL aunque el turno no haya usado herramientas (el agente
        escribiendo su respuesta también mueve el archivo).

    Estado derivado:  ● trabajando (tool abierta) · ◐ pensando (<30s sin
    cerrar turno) · ✓ te toca (terminó y espera tu mensaje) · ○ en reposo.
    Memo TTL 4s. Sin markers → [] y la caja se OMITE."""
    if not _sys_fresh("tabs"):
        val = []
        try:
            import session_paths
            base = os.path.join(os.path.expanduser("~"), ".claude", "workspace")
            mdir = os.path.join(base, "markers")
            now = time.time()
            # Actividad por sesión (una pasada por la cola de cada archivo).
            # `ultimo` guarda el ÚLTIMO evento de cada sesión: si fue un
            # tool_start, esa pestaña tiene una herramienta corriendo AHORA.
            # Se mira el último evento y no un contador start-end porque un
            # contador se desincroniza para siempre si un hook se pierde
            # (timeout, cierre a la fuerza) y la pestaña se queda
            # «trabajando» eternamente.
            act, ultimo, tool = {}, {}, {}
            tdir = os.path.join(base, "telemetry")
            for n in (os.listdir(tdir) if os.path.isdir(tdir) else ()):
                if not n.endswith(".jsonl"):
                    continue
                fp = os.path.join(tdir, n)
                try:
                    if now - os.path.getmtime(fp) > 172800:
                        continue
                    with open(fp, "rb") as f:
                        f.seek(0, os.SEEK_END)
                        size = f.tell()
                        f.seek(max(0, size - 65536))
                        chunk = f.read().decode("utf-8", "replace")
                except Exception:
                    continue
                for ln in chunk.splitlines()[1:]:
                    if not ln.startswith("{"):
                        continue
                    try:
                        ev = json.loads(ln)
                    except Exception:
                        continue
                    sid, ts = ev.get("session_id"), ev.get("ts")
                    if not sid or not isinstance(ts, (int, float)):
                        continue
                    if ts >= act.get(sid, 0):
                        act[sid] = ts
                        ultimo[sid] = ev.get("event") or ""
                        tool[sid] = ev.get("tool") or ""
            for n in (os.listdir(mdir) if os.path.isdir(mdir) else ()):
                if not n.endswith(".json"):
                    continue
                sid = n[:-5]
                try:
                    with open(os.path.join(mdir, n), encoding="utf-8") as f:
                        m = json.load(f)
                except Exception:
                    continue
                brain = m.get("brain") or ""
                last = act.get(sid, 0)
                try:                             # transcript: actividad REAL
                    tp = os.path.join(session_paths.session_dir(brain),
                                      sid + ".jsonl")
                    last = max(last, os.path.getmtime(tp))
                except Exception:
                    pass
                if not last:
                    continue
                edad = now - last
                # Ventanas (afinadas con el socio 2026-09-24):
                #   trabajando — el último evento fue un tool_start reciente
                #   pensando   — actividad hace <30s sin tool abierta (el
                #                agente está redactando)
                #   te toca    — terminó y te espera: SOLO 15 min, para que
                #                el panel no se quede en «listo» toda la
                #                tarde
                #   dormida    — sigue abierta pero sin actividad
                #   (>36h)     — ni se pinta: es un marker huérfano de una
                #                terminal que murió sin cerrar sesión
                trabajando = (ultimo.get(sid) == "tool_start"
                              and (now - act.get(sid, 0)) < 120)
                if trabajando:
                    est, det = "trabajando", tool.get(sid, "")
                elif edad < 30:
                    est, det = "pensando", ""
                elif edad < 15 * 60:
                    est, det = "te toca", ""
                elif edad < 36 * 3600:
                    est, det = "dormida", ""
                else:
                    continue
                val.append({"sid": sid, "ws": m.get("ws") or "",
                            "brain": brain,
                            "agente": os.path.basename(
                                brain.rstrip("\\/")).split(" ")[0].lower(),
                            "estado": est, "tool": det, "edad": edad})
            # UNA fila por SESIÓN ABIERTA. (El primer intento deduplicaba
            # por nombre de pestaña y estaba MAL: el socio tenía tres
            # sesiones llamadas «General» y el panel mostraba una sola. El
            # nombre no identifica nada; el session_id sí. Los markers de
            # sesiones CERRADAS los borra hooks/session_end.py, así que lo
            # que queda aquí son sesiones vivas o terminales muertas — a
            # esas las corta la ventana de 36h de arriba.)
            orden = {"trabajando": 0, "pensando": 1, "te toca": 2,
                     "dormida": 3}
            val.sort(key=lambda t: (orden.get(t["estado"], 9), t["edad"]))
            val = val[:max(1, limit)]
            # nombres repetidos → se desempatan con el inicio del id (tres
            # pestañas «General» son indistinguibles sin esto)
            vistos = {}
            for t in val:
                vistos[t["ws"]] = vistos.get(t["ws"], 0) + 1
            for t in val:
                if vistos.get(t["ws"], 0) > 1:
                    t["ws"] = "%s·%s" % (t["ws"], t["sid"][:4])
        except Exception:
            val = []
        _SYS_CACHE["tabs"] = val
        _SYS_CACHE_TS["tabs"] = time.monotonic()
    return _SYS_CACHE["tabs"]


_DIA_TAB_EST = {
    "trabajando": ("●", "trabajando", "OK"),
    "pensando": ("◐", "pensando", "C"),
    "te toca": ("✓", "te toca", "B"),
    "dormida": ("·", "dormida", "DK"),
}


def _dia_tabs_rows(K, inner, limit=6, rico=False):
    """Filas de PESTAÑAS. En forma RICA cada sesión ocupa DOS líneas —
    nombre arriba y, debajo, el estado EN PALABRAS con su herramienta y la
    edad (`trabajando · Bash · 3s`) — porque un glifo solo no dice si el
    agente está pensando o esperándote. En forma compacta, una línea."""
    K = cols(K)
    out = []
    filas = _dia_tabs(limit)
    for n, t in enumerate(filas):
        est = t["estado"]
        glifo, palabra, rol = _DIA_TAB_EST.get(est, ("○", est, "DK"))
        gcol = K[rol] + (K["BO"] if rol != "DK" else "")
        nombre = t["ws"] or t["agente"] or t["sid"][:8]
        edad = _dia_hace(time.time() - t["edad"]).replace("hace ", "")
        if not rico:
            cola = "%s %s" % (t["tool"], edad) if (est == "trabajando"
                                                   and t["tool"]) else edad
            room = max(6, inner - 2 - vis(cola) - 1)
            out.append(clip("%s%s%s %s%s%s %s%s%s" % (
                gcol, glifo, K["R"],
                (K["WH"] + K["BO"]) if est in ("trabajando", "pensando")
                else K["GREY"], pad(clip(nombre, room), room), K["R"],
                K["DK"], cola, K["R"]), inner))
            continue
        if n:
            out.append("")
        # la EDAD se va con el nombre (alineada a la derecha) para que la
        # línea de abajo quede entera para el estado y su herramienta
        hueco = max(1, inner - 2 - vis(nombre) - vis(edad))
        out.append(clip("%s%s%s %s%s%s%s%s%s%s" % (
            gcol, glifo, K["R"],
            (K["WH"] + K["BO"]) if est in ("trabajando", "pensando")
            else K["GREY"], clip(nombre, inner - 4), K["R"],
            " " * hueco, K["DK"], edad, K["R"]), inner))
        detalle = palabra
        if est == "trabajando" and t["tool"]:
            detalle += "%s · %s%s" % (K["DK"], K["B2"], t["tool"])
        out.append(clip("  %s%s%s" % (
            (K[rol] if rol != "DK" else K["DK"]), detalle, K["R"]), inner))
    return out


def _dia_ramas_rows(K, inner, maxb=4):
    """Filas del panel RAMAS del `dia` (pedido del socio 2026-10-02): el estado
    git del harness de un VISTAZO — rama actual + working tree, sync vs
    origin, último commit y las ramas más recientes — para no entrar a la
    pantalla «Ramas» solo a checar. TODO sale de los memos TTL de arriba
    (_git_info / _git_log / _git_ramas / _worktrees): CERO subprocess en el
    camino del redraw. Sin git/repo → [] y la caja se OMITE. El orden es de
    PRIORIDAD: si el alto recorta, se pierde el pie, no la rama actual."""
    K = cols(K)
    g = _git_info()
    if not g:
        return []
    out = []
    # 1 · rama actual (tinta hi) + working tree a la derecha: «✓ limpio»
    #     en verde o «± N» en acento bold (N archivos sin commitear)
    if g.get("dirty"):
        nch = g.get("changes")
        est_p = ("± %d" % nch) if nch else "± sucio"
        est_c = K["B2"] + K["BO"]
    else:
        est_p = "%s limpio" % K["CHECK"]
        est_c = K["OK"]
    room = max(4, inner - 3 - vis(est_p))
    out.append(clip("%s%s%s %s%s%s %s%s%s" % (
        K["B2"], K["BRANCH"], K["R"],
        K["C"] + K["BO"], pad(clip(g.get("branch") or "?", room), room),
        K["R"], est_c, est_p, K["R"]), inner))
    # 2 · sync vs upstream: ↑ por subir / ↓ por bajar; al día si hay
    #     upstream y nada pendiente; sin upstream se calla (no se inventa)
    ah, bh = g.get("ahead") or 0, g.get("behind") or 0
    if ah or bh:
        seg = ""
        if ah:
            seg += "%s↑%d%s " % (K["B"] + K["BO"], ah, K["R"])
        if bh:
            seg += "%s↓%d%s " % (K["B2"], bh, K["R"])
        out.append(clip("  %s%svs origin%s" % (seg, K["DK"], K["R"]), inner))
    elif g.get("upstream"):
        out.append(clip("  %sal día con origin%s" % (K["DK"], K["R"]),
                        inner))
    now = time.time()
    # 3 · último commit: hash + hace cuánto, y el asunto debajo
    log = _git_log(12) or ()
    if log:
        c = log[0]
        edad = _dia_hace(c.get("ts"), now).replace("hace ", "") \
            if c.get("ts") else ""
        hueco = max(1, inner - vis(c.get("h") or "") - vis(edad))
        out.append("")
        out.append(clip("%s%s%s%s%s%s%s" % (
            K["C"], c.get("h") or "", K["R"], " " * hueco,
            K["DK"], edad, K["R"]), inner))
        out.append(clip("  %s%s%s" % (
            K["GREY"], clip(c.get("s") or "", inner - 2), K["R"]), inner))
    # 4 · ramas recientes (● la actual) con su track y la edad del commit
    lista = ((_git_ramas() or {}).get("ramas") or ())[:max(0, maxb)]
    if lista:
        out.append("")
    for b in lista:
        glifo, gcol = ("●", K["OK"] + K["BO"]) if b.get("cur") \
            else ("·", K["DK"])
        cp, cc = [], []
        if b.get("ahead"):
            cp.append("↑%d" % b["ahead"])
            cc.append("%s↑%d%s" % (K["B"], b["ahead"], K["R"]))
        if b.get("behind"):
            cp.append("↓%d" % b["behind"])
            cc.append("%s↓%d%s" % (K["B2"], b["behind"], K["R"]))
        edad = _dia_hace(b.get("ts"), now).replace("hace ", "") \
            if b.get("ts") else ""
        if edad:
            cp.append(edad)
            cc.append("%s%s%s" % (K["DK"], edad, K["R"]))
        colap = " ".join(cp)
        room = max(4, inner - 2 - (vis(colap) + 1 if colap else 0))
        nombre = clip(b.get("name") or "", room)
        hueco = max(1, inner - 2 - vis(nombre) - vis(colap))
        out.append(clip("%s%s%s %s%s%s%s%s" % (
            gcol, glifo, K["R"],
            (K["WH"] + K["BO"]) if b.get("cur") else K["GREY"], nombre,
            K["R"], " " * hueco, " ".join(cc)), inner))
    # 5 · pie: worktrees ligados (solo si hay — 0 es relleno, no dato)
    wt = _worktrees()
    if wt:
        out.append("")
        out.append(clip("%s⌥ %s%d worktree%s%s" % (
            K["B2"], K["DIM"], wt, "s" if wt != 1 else "", K["R"]), inner))
    return out


def _dia_hace(ts, now=None):
    """«hace 2m» / «hace 3h» / «ayer» — corto y honesto. '' sin ts."""
    try:
        s = max(0, int((now or time.time()) - float(ts)))
    except (TypeError, ValueError):
        return ""
    if s < 60:
        return "hace %ds" % s
    if s < 3600:
        return "hace %dm" % (s // 60)
    if s < 86400:
        return "hace %dh" % (s // 3600)
    return "hace %dd" % (s // 86400)


def shadow_clock(K, w, anim=0):
    """Reloj GRANDE en la MISMA fuente y el MISMO neón que el wordmark
    (núcleo █ con el gradiente del tema fila a fila + la sombra ╔╗╚╝║═ en el
    acento tenue). Centrado en `w`; los dos puntos parpadean con el tick.
    [] si no cabe — el caller baja al reloj de bloques."""
    K = cols(K)
    txt = time.strftime("%H:%M")
    celdas = []
    for ch in txt:
        g = _DIA_SHADOW.get(ch)
        if not g:
            continue
        if ch == ":" and anim % 2:               # parpadeo (ancho estable)
            g = tuple(" " * len(x) for x in g)
        ancho = len(g[0]) if ch == ":" else _DIA_CELL
        celdas.append([x.center(ancho) for x in g])
    if not celdas:
        return []
    tw = sum(len(c[0]) for c in celdas)
    if tw > w:
        return []
    wc = K["WCOL"]
    pad_l = " " * max(0, (w - tw) // 2)
    return [pad_l + _neon_row("".join(c[r] for c in celdas),
                              wc[r % len(wc)] + K["BO"], K["B2"], K["R"])
            for r in range(6)]


def big_clock(K, w, anim=0, secs=False):
    """Reloj GRANDE (5 filas de bloques) centrado en `w`, con los dos
    puntos parpadeando al tick de animación. Si no cabe (w < 20) devuelve
    UNA línea con la hora en texto — misma información, menos aire."""
    K = cols(K)
    t = time.localtime()
    txt = time.strftime("%H:%M:%S" if secs else "%H:%M", t)
    if w < (len(txt) * 4):
        return [clip("%s%s%s%s" % (K["WH"], K["BO"], txt, K["R"]), w)]
    if anim % 2:                                 # parpadeo de los ':'
        txt = txt.replace(":", " ")
    rows = []
    for r in range(5):
        cells = [_DIA_GLYPHS.get(ch, _DIA_GLYPHS[" "])[r] for ch in txt]
        rows.append(" ".join(cells))
    pad_l = max(0, (w - max(len(r) for r in rows)) // 2)
    return ["%s%s%s%s%s" % (" " * pad_l, K["C"] + K["BO"], r, K["R"], "")
            for r in rows]


def _dia_fecha_line(K, w):
    """`martes 23 sep · semana 39 · día 61%` — fecha larga, semana ISO y
    avance REAL del día (00:00→24:00), centrado. Puro stdlib."""
    K = cols(K)
    now = datetime.datetime.now()
    pct = (now.hour * 60 + now.minute) * 100.0 / 1440.0
    fecha = "%s %d %s" % (_DIA_DIAS[now.weekday()], now.day,
                          _DIA_MESES[now.month - 1])
    sem = now.isocalendar()[1]
    txt = "%s%s%s  %s·%s  semana %s%d%s" % (
        K["WH"], fecha, K["R"], K["DK"], K["R"], K["DIM"], sem, K["R"])
    bar = gauge(K, max(6, min(18, w - 12)), pct, col=K["B2"] + K["BO"])
    lines = []
    for ln in (txt, "%sdía%s %s" % (K["DIM"], K["R"], bar)):
        pad_l = max(0, (w - vis(ln)) // 2)
        lines.append(" " * pad_l + ln)
    return lines


_DIA_SEMANA = ("lu", "ma", "mi", "ju", "vi", "sá", "do")


def _dia_deadlines_mes():
    """{día del mes: [títulos]} con los deadlines de `STATE/PENDIENTES.md`
    que caen en el mes en curso. {} si no hay cerebro o no hay fechas."""
    out = {}
    hoy = datetime.date.today()
    for it in _dia_pendientes() or ():
        d = it.get("dias")
        if d is None or d < 0:
            continue
        f = hoy + datetime.timedelta(days=d)
        if (f.year, f.month) == (hoy.year, hoy.month):
            out.setdefault(f.day, []).append(it.get("title") or "")
    return out


# ── FRANJA del titulo: pixel art que LLENA los margenes ─────────────────────
# Un objeto (monitor, columna) solo cabe con margen ancho y desaparecia en
# terminales normales; ademas dejaba la franja medio vacia. Esto es una
# SILUETA de barras — skyline / ecualizador — que se genera al ancho que haya:
# con 2 columnas de margen ya se ve, y con 25 llena las 25. Deterministica por
# columna (no parpadea entre frames) y solo con bloques <U+2600.
def _dia_franja_alturas(m, filas, semilla=0):
    """Altura (1..filas) de cada una de las `m` barras. Deterministica: la
    misma franja en cada frame, sin azar en tiempo de render."""
    out = []
    for c in range(m):
        h = _hsh_franja(c + semilla)
        # se permite altura 0: sin huecos, la franja se lee como un muro
        # macizo en vez de como una silueta
        out.append(h % max(2, filas))
    return out


def _hsh_franja(x):
    """Hash entero barato y estable (mismo espiritu que el cielo de front)."""
    x = (x * 73856093) ^ 0x9E3779B9
    x &= 0xFFFFFFFF
    x ^= x >> 13
    x = (x * 0x85EBCA6B) & 0xFFFFFFFF
    return x ^ (x >> 16)


def _dia_franja_col(K, m, filas, lado=0):
    """Las `filas` lineas de una franja de ancho `m`.

    DEGRADADO (dither) en vez de barras: denso en el borde exterior y
    desvaneciendose hacia el wordmark, con una inclinacion diagonal para que
    el ojo entre hacia el titulo. Llena cualquier ancho —de 1 a 30 columnas—
    y siempre se lee compuesto; un patron aleatorio llenaba igual pero se
    leia como ruido. El tono baja con el gradiente del wordmark, asi que la
    franja es literalmente el mismo material que el titulo."""
    K = cols(K)
    wc = K["WCOL"]
    esc = ("█", "▓", "▒", "░", " ")
    out = []
    for r in range(filas):
        celdas = []
        for c in range(m):
            # distancia al borde EXTERIOR, normalizada
            d = (m - 1 - c) if lado == 0 else c
            t = (d + 1.0) / max(1, m)
            # diagonal: el degradado cae un poco mas arriba en cada fila
            t += 0.10 * ((filas - 1 - r) - (filas - 1) / 2.0) / max(1, filas)
            idx = 0 if t > 0.80 else 1 if t > 0.62 else 2 if t > 0.44                 else 3 if t > 0.24 else 4
            celdas.append(esc[idx])
        out.append("%s%s%s" % (wc[r % len(wc)], "".join(celdas), K["R"]))
    return out


def _dia_flanquear(K, filas, w):
    """Llena los DOS margenes del titulo con la franja de barras. Deja un
    espacio de aire contra el wordmark y se dibuja desde 2 columnas — por eso
    ahora se ve en cualquier terminal. Si ni eso hay, devuelve el titulo tal
    cual: el adorno cede, nunca al reves."""
    if not filas or len(filas) < 3:
        return filas
    sangria = min((len(f) - len(f.lstrip(" "))) for f in filas if f.strip())
    ancho = max(vis(f) for f in filas)
    # un solo espacio de aire contra el wordmark: con dos, en terminales de
    # 80 columnas no quedaba margen y la franja no aparecia (que es justo lo
    # que el socio no veia)
    m_izq = max(0, sangria - 1)
    m_der = max(0, (w - 1) - ancho - 1)
    m = min(m_izq, m_der)
    if m < 1:
        return filas
    izq = _dia_franja_col(K, m, len(filas), 0)
    der = _dia_franja_col(K, m, len(filas), 1)
    out = []
    for i, f in enumerate(filas):
        cuerpo = f[m:] if f.startswith(" " * m) else f
        fila = izq[i] + cuerpo
        hueco = (w - 1) - vis(fila) - m
        if hueco > 0:
            fila += " " * hueco + der[i]
        out.append(fila)
    return out


def _dia_caps(K, txt, tono=0, cola="", w=0):
    """Titulo de seccion: versalita en UN tono del gradiente del wordmark,
    con la cola (contador, nombre) en tenue.

    Hubo un intento de espaciar las letras (`A G E N T E S`) para imitar el
    aire del wordmark: al socio no le gusto y se revirtio. Queda anotado para
    no volver a proponerlo."""
    K = cols(K)
    wc = K["WCOL"]
    return "%s%s%s%s" % (wc[tono % len(wc)] + K["BO"], str(txt).upper(),
                         K["R"],
                         ("%s · %s%s" % (K["DIM"], cola, K["R"]))
                         if cola else "")


def _dia_titulo_col(K, txt, w, tono=0):
    """Título de COLUMNA dentro de la caja del calendario: versalita (mayús)
    centrada sobre una regla tenue, en un tono del gradiente del wordmark.

        ──── DÍA 26 ────

    Es el mismo gesto que la etiqueta flotante de `full_box`, pero sin gastar
    un marco entero: dentro de una caja, otro borde pesa demasiado."""
    K = cols(K)
    partes = str(txt).split(" ")
    cola = partes[-1] if (len(partes) > 1 and partes[-1].isdigit()) else ""
    nombre = " ".join(partes[:-1]) if cola else txt
    etq = " %s " % _dia_caps(K, nombre, tono, cola)
    resto = max(0, w - vis(etq))
    izq = resto // 2
    # La division insinua, no marca: regla fina en el tono MAS APAGADO del
    # tema. Dos pasadas de suavizado (B2 -> DK) hasta que dejo de competir
    # con el contenido que separa.
    return "%s%s%s%s%s%s" % (
        K["DK"], K["SEP"] * izq, etq, K["DK"], K["SEP"] * (resto - izq),
        K["R"])


def _dia_prio_tag(K, e):
    """`! ` — prioridad ALTA en el acento del tema. '' si es normal."""
    return "%s%s!%s " % (K["C"], K["BO"], K["R"]) \
        if e.get("prio") == "alta" else ""


def _dia_tachado(K, txt):
    """HECHA: tachada y atenuada. Sin strikethrough queda solo atenuada."""
    return "\033[9m%s%s%s\033[29m" % (K["DK"], txt, K["R"])


def _dia_wrap_t(txt, w, maxl):
    """Título envuelto a ≤maxl líneas con «…» cuando quedó texto fuera —
    truncado honesto, no silencioso (afinado paneles 2026-10-02)."""
    lns = _wrap(txt, w, maxl + 1)
    if len(lns) > maxl:
        lns = lns[:maxl]
        lns[-1] = clip(lns[-1] + "…", w)
    return lns


def _dia_bloques_fit(bloques, alto, K, w):
    """Apila bloques (listas de líneas, uno por evento) SIN cortar ninguno a
    la mitad: lo que no cabe se vuelve una línea «+n más». Así los paneles
    reciben muchas tareas largas sin romperse ni encimar nada (afinado
    2026-10-02). Siempre ≤ alto líneas."""
    out, resto = [], 0
    for i, b in enumerate(bloques):
        quedan = len(bloques) - i
        # reservar 1 línea para el «+n más» si aún vienen bloques detrás
        tope = alto - (1 if quedan > 1 else 0)
        if out and len(out) + len(b) > tope:
            resto = quedan
            break
        if len(out) + len(b) > alto:       # ni el primero cabe entero
            out += b[:max(0, alto - len(out) - 1)]
            out.append(clip("%s…%s" % (K["DK"], K["R"]), w))
            return out[:alto]
        out += b
    while out and out[-1] == "":
        out.pop()
    if resto:
        out.append(clip("%s+%d más%s" % (K["DK"], resto, K["R"]), w))
    return out[:alto]


def _dia_lado_izq(K, w, dia, alto):
    """Columna IZQUIERDA: el día seleccionado, hora y nombre de cada evento y
    sus deadlines. El detalle vive aquí para que la rejilla se quede limpia.
    Hechas tachadas al final; corte por EVENTO entero + «+n más» (nunca un
    título a la mitad)."""
    K = cols(K)
    hoy = datetime.date.today()
    try:
        f = hoy.replace(day=dia)
    except ValueError:
        f = hoy
    pers = _dia_personal() or {}
    evs = (pers.get("mes") or {}).get(dia) or []
    dls = _dia_deadlines_mes().get(dia) or []
    if not evs and not dls:
        return [clip("%s%s%s" % (K["DK"], "sin nada", K["R"]), w)][:alto]
    bloques = []
    for t in dls:                          # lo que VENCE, primero: es lo duro
        b = [clip("%s▪ vence%s" % (K["B"] + K["BO"], K["R"]), w)]
        for ln in _dia_wrap_t(t, w, 2):
            b.append(clip("%s%s%s" % (K["GREY"], ln, K["R"]), w))
        b.append("")
        bloques.append(b)
    for e in evs:
        # los de Google (gcal) llevan ` ◦g` — el MISMO pip hueco de la
        # rejilla, sin robar ancho: el origen se lee sin ensuciar la columna
        hora = e.get("time") or "todo el día"
        if e.get("done"):
            b = [clip("%s%s%s" % (K["DK"], hora, K["R"]), w)]
            for ln in _dia_wrap_t(e.get("title") or "", w, 2):
                b.append(clip(_dia_tachado(K, ln), w))
        else:
            b = [clip("%s%s%s%s" % (
                K["B2"] + K["BO"], hora, K["R"],
                " %s◦%s%sg%s" % (K["B2"], K["R"], K["DIM"], K["R"])
                if e.get("g") else ""), w)]
            lns = _dia_wrap_t(e.get("title") or "", w - 2, 2) \
                if e.get("prio") == "alta" \
                else _dia_wrap_t(e.get("title") or "", w, 2)
            for j, ln in enumerate(lns):
                b.append(clip("%s%s%s%s" % (
                    _dia_prio_tag(K, e) if j == 0 else "", K["GREY"], ln,
                    K["R"]), w))
        b.append("")
        bloques.append(b)
    return _dia_bloques_fit(bloques, alto, K, w)


def _dia_lado_der(K, w, alto, desde_dia):
    """Columna DERECHA: lo que VIENE en el mes — día, hora y nombre. Arriba,
    si las hay, el aviso de ATRASADAS (pendientes de días pasados que no
    deben perderse de vista). Las hechas no salen (ya no «vienen»); corte
    por EVENTO entero + «+n más»."""
    K = cols(K)
    hoy = datetime.date.today()
    pers = _dia_personal() or {}
    mes = pers.get("mes") or {}
    dls = _dia_deadlines_mes()
    cab = []
    atr = pers.get("atrasadas") or ()
    if atr:
        rojo = (K["BAD"] or K["B"]) + K["BO"]
        cab.append(clip("%s▲ %d atrasada%s%s" % (
            rojo, len(atr), "s" if len(atr) != 1 else "", K["R"]), w))
        for ln in _dia_wrap_t(atr[0].get("title") or "", w - 2, 1):
            cab.append(clip("  %s%s%s" % (K["GREY"], ln, K["R"]), w))
        cab.append("")
    bloques = []
    for d in sorted(set(list(mes.keys()) + list(dls.keys()))):
        if d < hoy.day:
            continue
        for e in mes.get(d, ()):
            if e.get("done"):
                continue
            b = [clip("%s%2d%s %s%s%s%s" % (
                K["WH"] + K["BO"], d, K["R"], K["B2"],
                e.get("time") or "", K["R"],
                " %s◦%s%sg%s" % (K["B2"], K["R"], K["DIM"], K["R"])
                if e.get("g") else ""), w)]
            pre = _dia_prio_tag(K, e)
            for j, ln in enumerate(_dia_wrap_t(e.get("title") or "",
                                               w - 3 - (2 if pre else 0),
                                               2)):
                b.append(clip("   %s%s%s%s" % (pre if j == 0 else "",
                                               K["GREY"], ln, K["R"]), w))
            bloques.append(b)
        for t in dls.get(d, ()):
            b = [clip("%s%2d%s %s▪%s" % (
                K["WH"] + K["BO"], d, K["R"], K["B"] + K["BO"], K["R"]), w)]
            for ln in _dia_wrap_t(t, w - 3, 1):
                b.append(clip("   %s%s%s" % (K["GREY"], ln, K["R"]), w))
            bloques.append(b)
    if not cab and not bloques:
        return [clip("%snada más%s" % (K["DK"], K["R"]), w)][:alto]
    return (cab + _dia_bloques_fit(bloques, max(0, alto - len(cab)),
                                   K, w))[:alto]


def _dia_calendario(K, w, alto=0, sel=0, focus=False, modo="", buf="",
                    aviso=""):
    """El MES a todo el ancho de la caja — la pieza central del layout
    (dirección del socio 2026-09-24). Es además una SECCIÓN NAVEGABLE: front.py
    le da foco propio (◄► día · ↑↓ semana · Enter agrega un evento) porque
    el registro de este layout declara `"cal": True`.

        septiembre 2026
     lu      ma      mi      ju      vi      sá      do
              1       2       3       4       5       6
                      ●
      7       8       9     [10]     11      12      13

    · HOY en vídeo inverso · el día bajo el CURSOR entre corchetes · día con
      evento subrayado · día con deadline en el acento de aviso. Todo con
      atributos ANSI o con corchetes: la rejilla nunca cambia de ancho y se
      distingue igual en el tema `mono`.
    · La rejilla ESTIRA: el ancho sobrante se reparte entre las 7 columnas
      en vez de dejar dos márgenes muertos a los lados.
    · Debajo, el panel del día seleccionado (`_dia_panel_dia`).
    """
    K = cols(K)
    import calendar as _cal
    hoy = datetime.date.today()
    pers = _dia_personal() or {}
    mes = pers.get("mes") or {}
    dl = _dia_deadlines_mes()
    if w < 7 * 3:
        return []
    # TRES COLUMNAS cuando el ancho da (>=66): panel del dia | rejilla |
    # lo que viene. La rejilla deja de comerse todo el ancho y el DETALLE
    # (horas y nombres) vive a los lados, que es justo lo que el socio pidio:
    # el calendario limpio y los datos alrededor.
    # Cuantos paneles caben al lado de la rejilla: DOS (dia | mes | viene)
    # desde 48 columnas de caja, UNO (el detalle del dia) desde 36, y con
    # menos, la rejilla sola. La rejilla nunca baja de 24 columnas: los
    # lados se quedan con lo que sobre, no al reves.
    # DOS paneles o ninguno: con uno solo, la rejilla queda empujada a un
    # lado y el bloque se ve chueco (el ojo espera simetria). Sin sitio para
    # los dos, la rejilla va CENTRADA y el detalle del dia, debajo.
    n_lados = 2 if w >= 50 else 0
    lados = n_lados > 0
    # dos rieles de 3 columnas (" | ") separan las tres zonas
    lado_w = max(10, min(16, (w - 30) // 2)) if lados else 0
    rej_w = w - (lado_w * 2 + 6) if lados else w
    celda = max(3, rej_w // 7)
    extra = rej_w - celda * 7
    anchos = [celda + (1 if i < extra else 0) for i in range(7)]
    sel_fecha = hoy + datetime.timedelta(days=int(sel or 0))
    sel_dia = sel_fecha.day if sel_fecha.month == hoy.month else hoy.day
    semanas = _cal.Calendar(firstweekday=0).monthdayscalendar(hoy.year,
                                                              hoy.month)
    # Filas por semana: 3 (número + marcas + aire) es la forma que se ve
    # grande; 2 mete las marcas sin aire; 1 es la rejilla pelada.
    por_semana = 1
    for cand in (3, 2):
        if alto >= 2 + len(semanas) * cand + 2:
            por_semana = cand
            break
    doble = por_semana >= 2

    def cel(txt, col="", i=0):
        # números a la DERECHA de su celda, como un calendario de papel
        return "%s%s%s" % (col, txt.rjust(anchos[i] - 1) + " ",
                           K["R"] if col else "")

    out = []
    # Cabecera: versalita del mes sobre regla tenue (mismo gesto que la
    # etiqueta de una caja) y debajo los dias de la semana.
    out.append(_dia_titulo_col(K, _DIA_MESES_LARGO[hoy.month - 1] if lados
                               else "%s %d" % (
                                   _DIA_MESES_LARGO[hoy.month - 1],
                                   hoy.year), rej_w, 2))
    out.append("".join(cel(d, K["DK"], i)
                       for i, d in enumerate(_DIA_SEMANA)))
    out.append("")
    # Énfasis de celda (cursor=inverso, hoy/evento=subrayado): en modo MONO
    # NO se emite ANSI crudo (contrato "mono = cero ANSI" / NO_COLOR). El resto
    # de K[...] ya es "" en mono; estos escapes hardcodeados eran la única fuga.
    inv0, inv1 = ("", "") if K.get("MONO") else ("\033[7m", "\033[27m")
    und0, und1 = ("", "") if K.get("MONO") else ("\033[4m", "\033[24m")
    bloques = []
    for semana in semanas:
        fila, marcas = [], []
        for i, d in enumerate(semana):
            if not d:
                fila.append(" " * anchos[i])
                marcas.append(" " * anchos[i])
                continue
            txt = str(d)
            cuerpo = txt.rjust(anchos[i] - 1) + " "
            if d == sel_dia and focus:
                # con celdas anchas, corchetes; con celdas de 3 no caben
                # y el cursor pasa a video inverso (mismo peso, cero ancho)
                if anchos[i] >= 5:
                    cuerpo = ("[%s]" % txt).rjust(anchos[i] - 1) + " "
                    fila.append("%s%s%s%s" % (K["C"], K["BO"], cuerpo,
                                              K["R"]))
                else:
                    fila.append("%s%s%s%s%s%s"
                                % (inv0, K["C"], K["BO"], cuerpo, inv1, K["R"]))
            elif d == hoy.day:
                # hoy: inverso cuando el cursor usa corchetes; si el
                # cursor ya ocupa el inverso (celdas angostas), hoy va
                # subrayado para que los dos se distingan
                if anchos[i] >= 5 or not focus:
                    fila.append("%s%s%s%s%s%s"
                                % (inv0, K["C"], K["BO"], cuerpo, inv1, K["R"]))
                else:
                    fila.append("%s%s%s%s%s%s"
                                % (und0, K["C"], K["BO"], cuerpo, und1, K["R"]))
            elif d in dl:
                fila.append("%s%s%s%s" % (K["B"], K["BO"], cuerpo, K["R"]))
            elif d in mes:
                # día CON evento: número encendido (blanco bold) — el dorado
                # apagado de antes se perdía entre los días vacíos, que era
                # justo lo que el socio no veía (rediseño 2026-10-01)
                fila.append("%s%s%s%s%s"
                            % (und0, K["WH"] + K["BO"], cuerpo, und1, K["R"]))
            else:
                # sabado y domingo en un tono mas apagado: la semana laboral
                # salta a la vista sin leer los encabezados
                fila.append("%s%s%s" % (K["DK"] if i >= 5 else K["GREY"],
                                        cuerpo, K["R"]))
            # CONTEO en vez de pips (pedido del socio 2026-10-02): el número
            # de tareas que FALTAN ese día — oro encendido; rojo si el día
            # ya pasó (atrasadas); ✓ tenue si todo quedó hecho. ▪ sigue
            # marcando deadline del cerebro. Si el número no cabe, «9+».
            evd = mes.get(d) or ()
            pend = sum(1 for e in evd if not e.get("done"))
            done = len(evd) - pend
            cupo = max(1, anchos[i] - 1) - (1 if d in dl else 0)
            m, nv = "", (1 if d in dl else 0)
            if pend > 0 and cupo >= 1:
                txt = str(pend) if len(str(pend)) <= cupo else "9+"
                if len(txt) > cupo:
                    txt = "+"
                col = (K["BAD"] or K["B"]) if d < hoy.day else K["B"]
                m += "%s%s%s%s" % (col, K["BO"], txt, K["R"])
                nv += len(txt)
            elif done > 0 and cupo >= 1:
                m += "%s✓%s" % (K["DK"], K["R"])
                nv += 1
            if d in dl:
                m += "%s%s▪%s" % (K["B"], K["BO"], K["R"])
            marcas.append(" " * max(0, anchos[i] - 1 - nv) + m + " "
                          if m else " " * anchos[i])
        bloques.append([("".join(fila))]
                       + ([("".join(marcas))] if doble else []))
    filas_bloques = sum(len(b) for b in bloques)
    # Con paneles a los lados el detalle del dia YA se ve a la izquierda: el
    # panel de abajo solo queda para escribir (el alta) o para un aviso.
    if lados and modo != "add" and not aviso:
        panel = []
    else:
        panel = _dia_panel_dia(K, rej_w if lados else w, sel_dia, focus,
                               modo, buf, aviso,
                               max(0, alto - len(out) - filas_bloques - 1))             if alto else []
    # AIRE: lo que sobre se reparte ENTRE las semanas (apilarlo al final
    # dejaba un hueco muerto abajo). Así el mes ocupa todo su alto.
    sobra = max(0, alto - len(out) - filas_bloques - len(panel)) if alto else 0
    huecos = max(1, len(bloques) - 1)
    for i, b in enumerate(bloques):
        out += b
        if i < len(bloques) - 1 and sobra > 0:
            out += [""] * (sobra // huecos + (1 if sobra % huecos > i else 0))
    out += panel
    if not lados:
        return [clip(x, w) for x in out]
    # composicion de las tres columnas: la rejilla ya esta en `out` (ancho
    # rej_w); los lados se rellenan al mismo alto y se pegan con un carril.
    # Las tres columnas comparten cabecera: cada una con su versalita sobre
    # regla, y un RIEL vertical tenue entre ellas (el mismo recurso del
    # layout `split`). Sin esto las tres zonas se leian como un solo bloque
    # de texto suelto — que es justo lo que al socio no le cuadraba.
    etq_izq = _dia_titulo_col(
        K, "%s %d" % (_DIA_DIAS[sel_fecha.weekday()][:3], sel_dia),
        lado_w, 0)
    etq_der = _dia_titulo_col(K, "próximos", lado_w, 4)
    cuerpo = out[:]
    izq = _dia_lado_izq(K, lado_w, sel_dia, len(cuerpo) - 1)
    der = _dia_lado_der(K, lado_w, len(cuerpo) - 1, sel_dia)
    # riel fino y APAGADO: separa sin robarle peso a la rejilla
    riel = "%s %s %s" % (K["DK"], K["BOX"][4], K["R"])
    filas = [pad(etq_izq, lado_w) + riel + pad(cuerpo[0], rej_w) + riel
             + pad(etq_der, lado_w)]
    for i in range(1, len(cuerpo)):
        a = izq[i - 1] if i - 1 < len(izq) else ""
        c = der[i - 1] if i - 1 < len(der) else ""
        filas.append(pad(a, lado_w) + riel + pad(cuerpo[i], rej_w) + riel
                     + pad(c, lado_w))
    return [clip(f, w) for f in filas]


def _dia_panel_dia(K, w, dia, focus, modo, buf, aviso, maxl):
    """Bajo la rejilla, el DÍA seleccionado: su fecha larga, lo que tiene y
    cómo agregarle algo. Con el alta abierta (`modo == "add"`) se vuelve un
    campo de texto: lo que el socio teclea entra aquí y Enter lo guarda en
    `personal.json`. Sin foco muestra el día de hoy, que es lo útil de un
    vistazo. [] si no hay alto."""
    if maxl < 2:
        return []
    K = cols(K)
    hoy = datetime.date.today()
    try:
        f = hoy.replace(day=dia)
    except ValueError:
        f = hoy
    pers = _dia_personal() or {}
    evs = (pers.get("mes") or {}).get(dia) or []
    dls = _dia_deadlines_mes().get(dia) or []
    # MISMA versalita sobre regla que las columnas de arriba: sin esto el
    # panel de abajo parecia texto suelto colgando de la rejilla.
    etq = "%s %d" % (_DIA_DIAS[f.weekday()], dia)
    out = ["", _dia_titulo_col(K, etq, w, 0 if focus else 3)]
    if modo == "add":
        out.append(clip(" %s▸%s %s%s%s█%s" % (
            K["B"] + K["BO"], K["R"], K["WH"], buf, K["C"] + K["BO"],
            K["R"]), w))
        out.append(clip("   %sempieza con 18:00 para ponerle hora  ·  "
                        "Enter guarda  ·  Esc cancela%s"
                        % (K["DK"], K["R"]), w))
        return out[:maxl]
    cupo = max(1, maxl - 3)
    for e in evs[:cupo]:
        if e.get("done"):
            out.append(clip("  %s%s%s %s" % (
                K["DK"], (e.get("time") or " · "), K["R"],
                _dia_tachado(K, e.get("title") or "")), w))
        else:
            out.append(clip("  %s%s%s %s%s%s%s%s" % (
                K["B2"], (e.get("time") or " · "), K["R"],
                _dia_prio_tag(K, e), K["GREY"],
                e.get("title") or "", K["R"],
                " %s◦%s%sg%s" % (K["B2"], K["R"], K["DIM"], K["R"])
                if e.get("g") else ""), w))
    if len(evs) > cupo:
        out.append(clip("  %s+%d más%s" % (K["DK"], len(evs) - cupo,
                                           K["R"]), w))
    for t in dls[:2]:
        out.append(clip("  %s▪%s %s%s%s" % (
            K["B"] + K["BO"], K["R"], K["GREY"], t, K["R"]), w))
    if not evs and not dls:
        out.append(clip("  %ssin nada este día%s" % (K["DK"], K["R"]), w))
    if aviso:
        out.append(clip("  %s%s%s" % (K["B2"], aviso, K["R"]), w))
    elif focus:
        out.append(clip("  %sEnter agrega un evento aquí%s"
                        % (K["DK"], K["R"]), w))
    return out[:maxl]


def _dia_reset_seg(data, K):
    """`reset 0h51m` — lo ÚNICO que la caja PULSO tenía y no vive en otro
    sitio (el uso 5h, el tope y el bus ya están en la barra de instrumentos;
    qué corre ahora, en PESTAÑAS). Se cuelga de la barra en vez de ocupar una
    caja entera. '' si el latido no reporta `resets_at`."""
    K = cols(K)
    b = (data.get("hb") or {}).get("budget") or {}
    rs = b.get("resets_at")
    if not isinstance(rs, (int, float)):
        return ""
    h, m = divmod(int(max(0, rs - time.time())) // 60, 60)
    return "%sreset %s%s%dh%02dm%s" % (K["DIM"], K["WH"], K["BO"], h, m,
                                       K["R"])


# Los diales agrupados por lo que gobiernan. Los encabezados dan RITMO a la
# caja (y se ganan su fila: con alto de sobra el bloque se lee como una ficha,
# no como una lista suelta).
_DIA_TONO_GRUPOS = (("trato", ("amabilidad", "franqueza", "sarcasmo",
                               "humor")),
                    ("forma", ("longitud", "formalidad", "tecnicismo",
                               "emojis")),
                    ("trabajo", ("didactica", "iniciativa")))


def _dia_slider(K, v, i, ancho=5):
    """`━━━●─` — un slider, no una barra de carga: el recorrido hasta el
    nivel en el GRADIENTE del wordmark (K.WCOL, el mismo neón del título) y
    la perilla ● encima. `i` elige el tono del gradiente, así la caja entera
    degrada de arriba abajo como lo hace el título."""
    wc = K["WCOL"]
    col = wc[i % len(wc)] + K["BO"]
    v = max(1, min(ancho, int(v)))
    return "%s%s%s%s%s%s%s" % (col, "━" * (v - 1), "●", K["R"],
                               K["DK"], "─" * (ancho - v), K["R"])


def _dia_tono_box(agente, K, inner, alto=0):
    """Los diez diales del agente seleccionado. Tres formas según el alto:

      · RICA (alto ≥ 14) — grupos con encabezado, slider con el gradiente
        del wordmark y el POLO en palabras (`cálido`, `brutal`, `llano`…):
        se lee sin tener que acordarse de qué significa un 4.
      · MEDIA (alto ≥ 10) — un dial por fila, sin grupos.
      · COMPACTA — dos columnas, que es lo único que cabe en poco alto.

    Los diales en neutro van apagados: se ven, pero no gritan."""
    K = cols(K)
    try:
        import personalidad as _pers
    except Exception:
        return []
    niv = _pers.niveles(agente)
    by = {d["key"]: d for d in _pers.DIALS}

    def fila(d, i):
        v = niv.get(d["key"], _pers.NEUTRO)
        movido = v != _pers.NEUTRO
        polo = (d["eje"][0] if v < _pers.NEUTRO else
                d["eje"][1] if v > _pers.NEUTRO else "—")
        ln = "%s%s%s %s" % ((K["GREY"] if movido else K["DK"]),
                            pad(d["corto"][:4], 4), K["R"],
                            _dia_slider(K, v, i))
        resto = inner - 4 - 1 - 5 - 1
        if resto >= 3:
            ln += " %s%s%s" % ((K["WH"] if movido else K["DK"]),
                               clip(polo, resto), K["R"])
        return ln

    if alto >= 14:                              # ── forma RICA ──
        out, i = [], 0
        for n, (titulo, claves) in enumerate(_DIA_TONO_GRUPOS):
            if n:
                out.append("")
            regla = K["SEP"] * max(1, inner - vis(titulo) - 3)
            out.append("%s%s %s%s%s" % (K["DK"], titulo, K["DK"], regla,
                                        K["R"]))
            for k in claves:
                out.append(fila(by[k], i))
                i += 1
        return [clip(x, inner) for x in out]
    if alto >= 10:                              # ── forma MEDIA ──
        return [clip(fila(d, i), inner)
                for i, d in enumerate(_pers.DIALS)]
    # ── forma COMPACTA: dos columnas ──
    if inner >= 24:
        lab, num, sep = 4, True, "  "
    elif inner >= 21:
        lab, num, sep = 4, False, " "
    elif inner >= 19:
        lab, num, sep = 3, False, " "
    else:
        lab, num, sep = 4, True, "  "
    celda = lab + 1 + 5 + (1 if num else 0)
    por_fila = 2 if (celda * 2 + len(sep)) <= inner else 1
    filas, cur = [], []
    for i, d in enumerate(_pers.DIALS):
        v = niv.get(d["key"], _pers.NEUTRO)
        movido = v != _pers.NEUTRO
        txt = "%s%s%s %s" % ((K["GREY"] if movido else K["DK"]),
                             pad(d["corto"][:lab], lab), K["R"],
                             _dia_slider(K, v, i))
        if num:
            txt += "%s%d%s" % ((K["WH"] + K["BO"]) if movido else K["DK"],
                               v, K["R"])
        cur.append(txt)
        if len(cur) == por_fila:
            filas.append(sep.join(cur))
            cur = []
    if cur:
        filas.append(sep.join(cur))
    return [clip(f, inner) for f in filas]


def _dia_sel_rows(ags, view, K, inner, modo="full"):
    """Bajo AGENTES, lo del agente SELECCIONADO: qué está haciendo ahora (la
    tarea viva de now.json, completa — la fila de la lista la recorta) y su
    TONO en barras (los diales que tiene movidos; se eligen en MENÚ ▸ Tono).

    `modo` fija la altura, que NO puede depender de la selección (contrato
    del redraw): "full" = 5 filas · "corto" = 3 (estado + tono) · None = 0.
    El caller degrada a `corto` cuando la columna no cabe entera."""
    K = cols(K)
    if not modo:
        return []
    n = 4 if modo == "full" else 2
    rows = [""] * n
    if not ags:
        return rows
    a = ags[min(view.get("gsel", 0), len(ags) - 1)]
    task = (a.get("task") or "").strip()
    if task:
        est = (a.get("state") or "").strip().lower()
        busy = est in ("busy", "ocupado", "corriendo", "running", "working")
        head = "%s%s%s %s%s%s" % (
            (K["C"] if busy else K["OK"]) + K["BO"], "◐" if busy else "●",
            K["R"], K["DIM"], "trabajando" if busy else "en curso", K["R"])
    else:
        last = (a.get("_last_task") or "").strip()
        when = _dia_hace(a.get("_last_upd")) if a.get("_last_upd") else ""
        head = "%s○ %s%s%s" % (K["DK"], K["DIM"],
                               ("última · " + when) if (last and when)
                               else ("última" if last else "sin tarea"),
                               K["R"])
        task = last or (a.get("tagline") or "")
    rows[1] = clip(head, inner)
    if modo == "full":
        for i, ln in enumerate(_wrap(task, inner - 2, 2)):
            rows[2 + i] = clip("  %s%s%s" % (K["GREY"], ln, K["R"]), inner)
    return rows


def _dia_hoy_body(view, K, inner, ih):
    """Cuerpo de la caja HOY: reloj + fecha/avance del dia + CALENDARIO, que
    se lleva TODO el alto restante (direccion del socio 2026-09-24). Las viejas
    secciones FOCO / AGENDA / PENDIENTES salieron de aqui: la agenda y los
    deadlines se leen ahora en la rejilla del mes y en el dia a dia de
    abajo; el foco se fija y se consulta con `workspace foco`.

    Degrada en dos pasos: reloj grande + calendario -> reloj de una linea +
    calendario. El calendario NUNCA se cede: es la pieza."""
    K = cols(K)
    anim = int(view.get("anim") or 0)

    def compose(big):
        out = []
        if big:
            reloj = shadow_clock(K, inner, anim) or big_clock(K, inner, anim)
            out += [""] + reloj + [""]
        else:
            reloj = time.strftime("%H:%M")
            out += [clip(" " * max(0, (inner - 5) // 2)
                         + "%s%s%s" % (K["C"] + K["BO"], reloj, K["R"]),
                         inner)]
        out += _dia_fecha_line(K, inner)
        cal = _dia_calendario(K, inner, alto=max(0, ih - len(out) - 1),
                              sel=view.get("cal_off", 0),
                              focus=view.get("focus") == "cal",
                              modo=view.get("cal_mode", ""),
                              buf=view.get("cal_buf", ""),
                              aviso=view.get("cal_msg", ""))
        if cal:
            out += [""] + cal
        return out

    for big in (True, False):
        body = compose(big)
        if len(body) <= ih:
            return body
    return body[:ih]


def render_dia(data, view, K, w):
    """`dia` (ver _dia_lines) — título grande si cabe (_fit)."""
    return _fit(_dia_lines, data, view, K, w)


def _dia_lines(data, view, K, w, compact=False, dense=False):
    """`dia` — «El día». Cabecera igual que el centro (wordmark +
    instrumentos + tira de operaciones) y TRES columnas: IZQUIERDA las 3
    secciones navegables del hub (AGENTES · MENÚ · CONFIGS — idénticas al
    layout `centro`), CENTRO la caja HOY (reloj, fecha, avance del día,
    foco, agenda, pendientes) y DERECHA el PULSO vivo + ACTIVIDAD. En
    angosto (<85) se apila. La altura llena view.h exacto y no depende de
    la selección ni del frame."""
    K = cols(K)
    focus = view.get("focus")
    h = view.get("h") or 0
    hchar = K["BOX"][5]
    ags = _centro_agents(data)
    dsel = ags[min(view.get("gsel", 0), len(ags) - 1)] if ags else None
    ldata = dict(data, agents=ags)               # tarea/estado FRESCOS
    L = [] if (compact or dense) else [""]
    bt = big_title(K, w, h, indent=" ", right=branch_widget(K),
                   compact=compact, center=True)
    if len(bt) > 1:
        bt = _dia_flanquear(K, bt, w)
    L += bt
    if len(bt) > 1:
        L += title_reflection(K, w, indent=" ", center=True)
    # Subtítulo MÍNIMO (poda de ruido, el socio 2026-09-24): el motor y la rama ya
    # viven en la barra de instrumentos y en la statusline — repetirlos tres
    # veces no informa, decora. Queda versión + estado de actualización.
    build = " · ".join(p for p in (
        ("v" + data["version"]) if data.get("version") else "",
        data.get("version_text") or "") if p)
    # el subtítulo se cuelga del MISMO eje que el wordmark (centrado suelto
    # bajo un título centrado se ve accidental)
    L.append(clip(" " * max(0, ((w - 1) - vis(build)) // 2)
                  + "%s%s%s" % (K["DIM"], build, K["R"]), w - 1))
    # Regla bajo el subtítulo con FADE de grises (toque 2026-10-02): arranque
    # en acento (B2), un respiro apenas más claro (GREY) a un tercio y el
    # resto hundido en DK — profundidad sutil, mismo ancho de siempre.
    _m = max(1, w - 5)
    _a, _b = _m * 2 // 5, max(0, min(10, _m // 5))
    L.append(clip("%s%s%s%s%s%s%s%s%s" % (
        K["B2"], hchar * 3, K["DK"], hchar * _a, K["GREY"], hchar * _b,
        K["DK"], hchar * max(0, _m - _a - _b), K["R"]), w - 1))
    # Sin barra de instrumentos ni tira de operaciones (el socio 2026-09-24: «es
    # ruido entre el título y las secciones»). Motor, rama y latido siguen
    # en la statusline del pie, que es donde se buscan.
    L.append("")
    top_n = len(L)
    status = bottom_statusline(data, view, K, w)
    gap1, tail = (0, 1) if dense else (1, 2)
    ag_title = "AGENTES · %d" % len(ags) if ags else "AGENTES"
    doff = K.get("OFF") or K["DK"]
    dlabel = K["B"] + K["BO"]
    if w - 1 >= 85:                              # ── TRES COLUMNAS ──
        # Columnas PROPIAS de `dia` (las del centro daban 26%/30% a los
        # lados y ahogaban la caja HOY — el reloj no cabía y los pendientes
        # se recortaban a la mitad). Aquí la estrella es el CENTRO.
        lw = max(24, min(30, (w - 1) * 22 // 100))
        rw = max(24, min(36, (w - 1) * 26 // 100))
        cw = w - 1 - lw - rw - 4
        if cw < 38:                              # el centro nunca se ahoga
            rw = max(24, rw - (38 - cw))
            cw = w - 1 - lw - rw - 4
        def _left(modo):
            """La columna izquierda entera. `modo` es cuanto AIRE se permite:
            "full" (fila de aviso + separador del menu + hint de configs) ->
            "medio" (sin aviso) -> "denso" (sin nada opcional). Las 3
            secciones NAVEGABLES van completas SIEMPRE: se cede el adorno,
            jamas una opcion ni el borde de una caja. Devuelve (filas, hits):
            hits = hit-map RELATIVO a la columna (fila 0-based, kind, idx) —
            cada cuerpo reporta sus filas y aqui se les suma el offset de su
            caja (+1 por el borde superior)."""
            aire = (modo == "full")
            ha, hm, hc = [], [], []
            ab = _dia_agentes_body(ldata, view, K, lw - 4, aviso=aire,
                                   hits=ha)
            menu = _dia_menu_body(data, view, K, lw - 4,
                                  separador=(modo != "denso"), hits=hm)
            cfg = _dia_cfg_body(data, view, K, lw - 4, hint=aire, hits=hc)
            # Los titulos de las tres cajas toman tonos SUCESIVOS del
            # gradiente del wordmark (K.WCOL): la columna se lee como una
            # sola pieza degradada, igual que el titulo de arriba.
            out = full_box(_dia_caps(K, "agentes", 0, str(len(ags)), w=lw - 7), ab,
                           K, lw, len(ab), focus == "dioses",
                           border=K["C"], label=K["R"])
            lh = [(1 + r, kk, ii) for (r, kk, ii) in ha]
            out += [""] * gap1
            base = len(out)
            out += full_box(_dia_caps(K, "menú", 2, w=lw - 7), menu, K, lw, len(menu),
                            focus == "tools", border=K["B2"], label=K["R"])
            lh += [(base + 1 + r, kk, ii) for (r, kk, ii) in hm]
            if cfg:
                out += [""] * gap1
                base = len(out)
                out += full_box(_dia_caps(K, "personalización", 4, w=lw - 7), cfg, K, lw,
                                len(cfg), focus == "latido",
                                border=K["B2"], label=K["R"])
                lh += [(base + 1 + r, kk, ii) for (r, kk, ii) in hc]
            return out, lh
        left, lhits = _left("full")
        if h:
            ch = max(6, (h - 1) - top_n - tail)
        else:                                    # natural (--banner sin alto)
            ch = max(len(left), 24)
        for modo in ("medio", "denso"):          # degradacion en dos pasos
            if len(left) <= ch:
                break
            left, lhits = _left(modo)
        # CENTRO: la caja HOY llena el alto completo de la fila
        center = full_box(_dia_caps(K, "hoy", 1, w=cw - 7),
                          _dia_hoy_body(view, K, cw - 4, ch - 2),
                          K, cw, ch - 2, focus == "cal", border=K["B"],
                          label=K["R"])
        # DERECHA: PULSO (alto ajustado al contenido) + ACTIVIDAD absorbe
        # Derecha = PULSO + PESTAÑAS. ACTIVIDAD (el log bus/git) se fue: eran
        # 12 filas casi idénticas («✉ turing → zenith» ×5) y el bus ya está
        # resumido por agente dentro de PULSO. Lo que SÍ no se veía en ningún
        # lado es qué sesión trabaja y cuál ya terminó de pensar.
        # Arriba del PULSO, el TONO del agente SELECCIONADO: aquí hay ancho
        # para barras de verdad (en la columna izquierda quedaba achocado —
        # pedido del socio 2026-09-24). Cambia al moverte entre agentes.
        # DERECHA = TONO (alto fijo, lo que mide) + RAMAS (absorbe todo
        # lo demas). La caja PULSO se retiro a pedido del socio: su gauge de uso
        # 5h, el tope y el bus ya viven en la barra de instrumentos, y lo
        # unico exclusivo que tenia -- el countdown al reset -- se colgo de
        # la barra. PESTANAS vivio aqui hasta 2026-10-02; el socio pidio en su
        # lugar el estado git de un vistazo (las sesiones se ven en la
        # statusline y el picker).
        # Reparto de la columna: RAMAS reemplazó a PESTAÑAS en este slot
        # (pedido del socio 2026-10-02): el estado git del harness de un
        # vistazo — rama actual + sync + último commit + ramas recientes —
        # para no entrar a la pantalla «Ramas» solo a checar. Todo sale de
        # los memos TTL de arriba: CERO subprocess en el camino del redraw
        # (la lección del mapa). Sin git/repo → la caja se OMITE limpio.
        # (El subsistema de PESTAÑAS sigue vivo — _dia_tabs/_dia_tabs_rows
        # quedan para otros consumidores; solo cambió qué pinta el slot.)
        ramas = _dia_ramas_rows(K, rw - 4)
        ramas_ih = min(len(ramas), 12) if ramas else 0
        alto_tono = ch - ((ramas_ih + 2 + gap1) if ramas_ih else 0) - 2
        tono = _dia_tono_box(dsel.get("name") if dsel else None, K, rw - 4,
                             alto=alto_tono)
        right = []
        libre_r = ch
        if tono and libre_r >= len(tono) + 4:
            titulo = _dia_caps(K, "tono", 3,
                               (dsel.get("display") or dsel.get("name"))
                               if dsel else "", w=rw - 7)
            # TONO se queda con el sobrante (hasta 2 filas de aire); lo que
            # reste vuelve a RAMAS, asi la columna llena el alto exacto
            # sin dejar un hueco muerto abajo.
            ih_t = max(len(tono), min(alto_tono, len(tono) + 2))
            right += full_box(titulo, tono, K, rw, ih_t, False,
                              border=K["B"], label=dlabel)
            right += [""] * gap1
            libre_r -= ih_t + 2 + gap1
        if ramas and libre_r >= 3:
            ih_p = max(1, libre_r - 2)
            nb = (_git_ramas() or {}).get("total") or _branches()
            etq = _dia_caps(K, "ramas", 5, str(nb) if nb else "", w=rw - 7)
            # el borde PRENDE en acento cuando hay trabajo sin commitear —
            # el mismo gesto que PESTAÑAS hacia con una sesion trabajando
            sucio = bool((_git_info() or {}).get("dirty"))
            right += full_box(etq, ramas, K, rw, ih_p, False,
                              border=(K["B2"] if sucio else doff),
                              label=dlabel)
        left += [""] * max(0, ch - len(left))
        center += [""] * max(0, ch - len(center))
        right += [""] * max(0, ch - len(right))
        base = len(L)
        for i in range(ch):
            L.append(clip(pad(left[i], lw) + "  " + pad(center[i], cw) + "  "
                          + right[i], w - 1))
        # hit-map ABSOLUTO del frame (filas 0-based del bloque): la columna
        # izquierda ocupa x ∈ [0, lw). Filas degradadas fuera de ch no
        # existen en pantalla → fuera del mapa.
        view["hit"] = [(base + r, 0, lw, kk, ii)
                       for (r, kk, ii) in lhits if r < ch]
    else:                                        # ── angosto: APILADO ──
        # En una columna el alto es el recurso escaso: las secciones
        # NAVEGABLES (agentes/menú/configs) son intocables — sin ellas el hub
        # deja de ser un menú — así que HOY se lleva lo que sobre y PULSO
        # solo aparece si queda sitio. Presupuesto EXACTO: el bloque nunca
        # excede h-1 (desbordar rompe el redraw con cursor-up).
        pw = w - 1
        ha, hm, hc = [], [], []
        ab = _dia_agentes_body(ldata, view, K, pw - 4, aviso=not dense,
                               hits=ha)
        menu = _dia_menu_body(data, view, K, pw - 4, separador=not dense,
                              hits=hm)
        cfg = _dia_cfg_body(data, view, K, pw - 4, hint=not dense, hits=hc)
        fijos = full_box(ag_title, ab, K, pw, len(ab), focus == "dioses",
                         border=K["C"])
        fh = [(1 + r, kk, ii) for (r, kk, ii) in ha]
        basef = len(fijos)
        fijos += full_box("MENÚ", menu, K, pw, len(menu), focus == "tools",
                          border=K["B2"])
        fh += [(basef + 1 + r, kk, ii) for (r, kk, ii) in hm]
        if cfg:
            basef = len(fijos)
            fijos += full_box("PERSONALIZACIÓN", cfg, K, pw, len(cfg),
                              focus == "latido", border=K["B2"])
            fh += [(basef + 1 + r, kk, ii) for (r, kk, ii) in hc]
        libre = ((h - 1) - len(L) - len(fijos) - tail) if h else 18
        hoy_ih = max(0, min(12 if dense else 16, libre - 2))
        if hoy_ih >= 4:
            L += full_box("HOY", _dia_hoy_body(view, K, pw - 4, hoy_ih),
                          K, pw, hoy_ih, False, border=K["B"], label=dlabel)
            libre -= hoy_ih + 2
        # hit-map ABSOLUTO (apilado: las secciones ocupan todo el ancho)
        view["hit"] = [(len(L) + r, 0, pw, kk, ii) for (r, kk, ii) in fh]
        L += fijos
        tono = _dia_tono_box(dsel.get("name") if dsel else None, K, pw - 4)
        if tono and libre >= len(tono) + 3:
            L += full_box("TONO · %s" % (dsel.get("display") or "")
                          if dsel else "TONO", tono, K, pw, len(tono),
                          False, border=K["B"], label=dlabel)
            libre -= len(tono) + 2
        ramas = _dia_ramas_rows(K, pw - 4)
        if ramas and libre >= 4:
            nb = (_git_ramas() or {}).get("total") or _branches()
            L += full_box("RAMAS · %d" % nb if nb else "RAMAS", ramas,
                          K, pw, min(len(ramas), libre - 2), False,
                          border=doff, label=dlabel)
    L += ([""] if tail == 2 else []) + [status]
    return vfill(L, view, tail=tail)


# ── REGISTRO ────────────────────────────────────────────────────────────────
# Orden = orden del picker. `clasico` primero (default). render=None ⇒ el
# camino nativo de front.py (el recinto centrado de siempre, byte-idéntico).
#
# BASE 2026-07-08 (dirección del socio): SOLO dos layouts EXPUESTOS —
# `clasico` (default) y `centro` (mission control). Los demás renderers
# siguen en el módulo (código intacto, sus tests los invocan directo) pero
# NO se registran: no aparecen en el picker ni son seleccionables por
# ui.layout. Para volver a exponer uno: agrégalo a _ENABLED.
_ENABLED = ("clasico", "centro", "dia")


def _all_layouts():
    """TODOS los renderers del módulo (expuestos o no). El registro EFECTIVO
    (`_registry`) filtra por `_ENABLED`."""
    return (
        {"id": "clasico", "label": "Clásico — recinto centrado",
         "render": None},
        {"id": "hud", "label": "HUD de consola — alineado a la izquierda",
         "render": render_hud},
        {"id": "cockpit", "label": "Cockpit — split vertical + monitor vivo",
         "render": render_cockpit},
        {"id": "split", "label": "Split — sidebar de agentes + rail",
         "render": render_split},
        {"id": "status", "label": "Status — pestañas + statusline",
         "render": render_status},
        {"id": "grid", "label": "Grid — tarjetas de agentes",
         "render": render_grid},
        # anim=True: front avanza view.anim a cadencia BAJA (~0.8s) y
        # redibuja el bloque — los sprites solo cambian de glifo.
        {"id": "centro", "label": "Centro — mission control (cubículos)",
         "render": render_centro, "anim": True},
        # anim=True: el reloj grande y el pulso vivo se refrescan al tick
        # bajo (~0.83s) — el dato manda, la animación es solo el parpadeo
        # de los dos puntos del reloj.
        # cal=True: front.py le da al calendario su propia SECCION navegable
        # (◄► dia · ↑↓ semana · Enter agrega evento).
        {"id": "dia", "label": "El día — calendario + agentes",
         "render": render_dia, "anim": True, "cal": True},
    )


def _registry():
    """Layouts EXPUESTOS (los de `_ENABLED`, en el orden de `_ENABLED`).
    Todo lo demás (available/_by_id/resolve/picker) deriva de aquí, así que
    con recortar esto basta para que los otros ni se vean ni se seleccionen."""
    byid = {L["id"]: L for L in _all_layouts()}
    return tuple(byid[i] for i in _ENABLED if i in byid)


def available():
    """Layouts instalados: [{id, label, default}] — clasico primero."""
    return [{"id": L["id"], "label": L["label"],
             "default": L["id"] == DEFAULT_ID} for L in _registry()]


def _by_id(lid):
    for L in _registry():
        if L["id"] == lid:
            return L
    return None


def _settings_layout():
    try:
        import settings
        v = settings.get("ui.layout", DEFAULT_ID)
        return v if isinstance(v, str) else DEFAULT_ID
    except Exception:
        return DEFAULT_ID


def resolve_id(explicit=None):
    """Id del layout activo: explicit > env WORKSPACE_LAYOUT > ui.layout >
    DEFAULT_ID. Candidato desconocido → se salta (falla-suave al siguiente).
    JAMÁS levanta: cualquier problema → DEFAULT_ID."""
    try:
        for cand in (explicit, os.environ.get("WORKSPACE_LAYOUT"),
                     _settings_layout()):
            cand = (cand or "").strip().lower()
            if cand and _by_id(cand) is not None:
                return cand
    except Exception:
        pass
    return DEFAULT_ID


def active(explicit=None):
    """La entrada del layout activo si NO es el nativo, o None (⇒ front usa
    su camino clásico intacto). Jamás levanta."""
    try:
        L = _by_id(resolve_id(explicit))
        if L is None or L["render"] is None:
            return None
        return L
    except Exception:
        return None


if __name__ == "__main__":
    act = resolve_id()
    print("layouts instalados (activo: %s):" % act)
    for L in available():
        mark = "●" if L["id"] == act else "·"
        print("  %s %-10s %s%s" % (mark, L["id"], L["label"],
                                   "  (default)" if L["default"] else ""))
