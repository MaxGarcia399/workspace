"""Read-only Connections section, including the small-window layout."""
import json
import os
import re
import sys
import time

import hublayout as HL
import mcp_inventory as inventory
import responsive_ui
import section_box as SB
import section_frame as SF
from theme import screen as _theme_screen

# Un punto por estado, con su forma propia: el color solo no es la única pista.
MARKS = {"manual": ("●", "OK"), "registered": ("○", "B2"), "unreadable": ("▲", "BAD"),
         "unsupported": ("✕", "DIM"), "absent": ("·", "DK")}
MARK_ORDER = ("manual", "registered", "unreadable", "unsupported", "absent")
SIDE_W = 44
NAME_MAX = 22


def t(key, **kw):
    import i18n
    return i18n.t("mcps.ui." + key, **kw) if kw else i18n.t("mcps.ui." + key)


def initial(data=None):
    return {"data": inventory.scan() if data is None else data,
            "row": 0, "engine": 0, "first": 0, "detail": False, "scroll": 0,
            "projects": [], "project": -2}


def names(state):
    data = state["data"]
    out = sorted({r["name"] for r in data["records"]})
    if any(f["state"] == "unreadable" for f in data["files"]):
        out.insert(0, None)
    return out


def selected(state):
    rows = names(state)
    if not rows:
        return None
    state["row"] = max(0, min(state["row"], len(rows) - 1))
    return rows[state["row"]]


def wrap(text, width):
    # Origins and long variable names must remain readable, including in a pane.
    text = re.sub(r"[\x00-\x1f\x7f]", "", str(text))
    result = []
    for paragraph in SF.wrap(text, width):
        line = ""
        for char in paragraph:
            if line and HL.vis(line + char) > width:
                result.append(line)
                line = ""
            line += char
        result.append(line)
    return result or [""]


def display_path(path):
    home = os.path.expanduser("~")
    return "~" + path[len(home):] if path.startswith(home + os.sep) else path


def _detail_parts(state, width):
    """(línea, rol) del detalle del servicio y motor elegidos; el rol solo
    sirve para pintar (title · status · body · dim)."""
    name = selected(state)
    engine, title = inventory.ENGINES[state["engine"]]
    status, origins = inventory.cell(state["data"], name, engine)
    parts = [(ln, "title") for ln in wrap(title + " / " + (name or t("file_errors")), width)]
    parts += [(ln, status) for ln in wrap(t(status), width)] + [("", "body")]
    if status == "unreadable":
        parts += [(ln, "body") for ln in wrap(t("read_error"), width)] + [("", "body")]
    for origin in origins:
        body = wrap(t("origin") + ": " + display_path(origin["path"]), width)
        body += wrap(t("scope") + ": " + t(origin["scope"]), width)
        if origin.get("project"):
            body += wrap(t("project") + ": " + display_path(origin["project"]), width)
        if origin.get("state") == "unreadable":
            body += wrap(t("unreadable"), width)
        if origin.get("agents"):
            body += wrap(t("agents") + ": " + ", ".join(origin["agents"]), width)
        if "variables" in origin:
            body += wrap(t("variables") + ": " + (", ".join(origin["variables"]) or "—"), width)
        parts += [(ln, "body") for ln in body] + [("", "body")]
    if not origins:
        parts += [(ln, "body") for ln in wrap(t("absent_note"), width)]
    return parts + [(ln, "dim") for ln in wrap(t("no_probe"), width)]


def detail_lines(state, width):
    return [line for line, _ in _detail_parts(state, width)]


def _detail_styled(state, K, width):
    roles = {"title": K["WH"] + K["BO"], "body": K["GREY"], "dim": K["DIM"]}
    roles.update({status: K[col] for status, (_, col) in MARKS.items()})
    return ["%s%s%s" % (roles[role], line, K["R"]) if line else ""
            for line, role in _detail_parts(state, width)]


def _legend(K, iw):
    """Un punto con su forma por estado y su palabra (sin letras sueltas), en las
    líneas que hagan falta; cada «punto palabra» queda entero en una línea."""
    items = ["%s%s%s %s%s%s" % (K[MARKS[st][1]], MARKS[st][0], K["R"], K["GREY"], t("legend_" + st), K["R"])
             for st in MARK_ORDER]
    lines, cur = [], ""
    for item in items:
        if cur and HL.vis(cur) + 3 + HL.vis(item) > iw:
            lines.append(cur)
            cur = ""
        cur = (cur + "   " if cur else "") + item
    return lines + [cur]


def _layout(state, iw, rows):
    """Qué motores se ven: (nombre_w, anchos, primero, cuántos, flechas). Si no
    caben los nueve, una ventana con ❮ ❯ que sigue al motor elegido."""
    name_w = max(14, min(NAME_MAX, max([HL.vis(n or t("file_errors")) for n in rows] or [0]) + 1))
    widths = [max(HL.vis(title), 4) + 2 for _, title in inventory.ENGINES]
    total = len(widths)
    fixed = 2 + name_w
    if fixed + sum(widths) <= iw:
        state["first"], state["_nvis"] = 0, total
        return name_w, widths, 0, total, False
    avail = max(widths[0], iw - fixed - 4)

    def count(first):
        used, n = 0, 0
        for width in widths[first:]:
            if used + width > avail:
                break
            used, n = used + width, n + 1
        return max(1, n)
    first = max(0, min(state.get("first", 0), total - 1))
    engine = state["engine"]
    if engine < first:
        first = engine
    while engine >= first + count(first) and first < total - 1:
        first += 1
    n = count(first)
    state["first"], state["_nvis"] = first, n
    return name_w, widths, first, n, True


def _center(text, vis, width):
    left = max(0, (width - vis) // 2)
    return " " * left + text + " " * max(0, width - vis - left)


def _table(state, K, iw, hit):
    rows = names(state)
    selected(state)
    name_w, widths, first, n, arrows = _layout(state, iw, rows)
    engines = list(range(first, first + n))
    more = len(widths) - n
    out = []
    if more:
        out.append(" " * max(0, iw - HL.vis(t("more_engines", n=more))) + K["DIM"] + t("more_engines", n=more) + K["R"])
    left_on = first > 0
    right_on = first + n < len(widths)
    x = 2 + name_w
    header = K["DIM"] + K["BO"] + HL.pad(t("service"), x) + K["R"]
    hit["hdr"] = len(out)
    hit["arrows"] = {}
    if arrows:
        hit["arrows"]["left"] = x
        header += (K["C"] + K["BO"] if left_on else K["DK"]) + K["BL"] + K["R"] + " "
        x += 2
    hit["engines"] = []
    for e in engines:
        title = inventory.ENGINES[e][1]
        hit["engines"].append((x, x + widths[e], e))
        ink = K["C"] + K["BO"] if e == state["engine"] else K["GREY"]
        header += ink + _center(title, HL.vis(title), widths[e]) + K["R"]
        x += widths[e]
    if arrows:
        hit["arrows"]["right"] = x + 1
        header += " " + (K["C"] + K["BO"] if right_on else K["DK"]) + K["BR"] + K["R"]
    out.append(header)
    hit["rows"] = {}
    for idx, name in enumerate(rows):
        on = idx == state["row"]
        marker = (K["C"] + K["BO"] + K["PTR"] + K["R"] + " ") if on else "  "
        label = HL.pad(HL.clip(name or t("file_errors"), name_w), name_w)
        line = marker + (K["WH"] + K["BO"] if on else K["GREY"]) + label + K["R"]
        if arrows:
            line += "  "
        for e in engines:
            status, _ = inventory.cell(state["data"], name, inventory.ENGINES[e][0])
            glyph, col = MARKS[status]
            if on and e == state["engine"]:
                cell = "%s[%s%s%s%s]%s" % (K["C"] + K["BO"], K[col], glyph, K["R"], K["C"] + K["BO"], K["R"])
                line += _center(cell, 3, widths[e])
            else:
                line += _center(K[col] + glyph + K["R"], 1, widths[e])
        hit["rows"][len(out)] = idx
        out.append(line)
    if not rows:
        out.append(K["DIM"] + t("empty") + K["R"])
    hit["cursor"] = hit["hdr"] + 1 + state["row"]
    return out


def _body(state, K, iw, paired, hit):
    body = _table(state, K, iw, hit)
    body.append("")
    if not paired and names(state):
        name = selected(state)
        engine, title = inventory.ENGINES[state["engine"]]
        status, _ = inventory.cell(state["data"], name, engine)
        head = title + " / " + (name or t("file_errors"))
        body.append(HL.clip(K["WH"] + K["BO"] + head + K["R"], iw))
        glyph, col = MARKS[status]
        body += [K[col] + (glyph + " " if i == 0 else "  ") + ln + K["R"]
                 for i, ln in enumerate(wrap(t(status), max(10, iw - 2)))]
        body.append("")
    body += _legend(K, iw)
    body.append(K["DIM"] + HL.clip(t("legend_registered_note"), iw) + K["R"])
    project = state["projects"][state["project"]] if state["project"] >= 0 else \
        t("all_projects" if state["project"] == -2 else "user_profile")
    body += ["", K["DIM"] + HL.clip(project, iw) + K["R"]]
    return body


def _chips(state):
    if state["detail"]:
        return (("↑↓", t("k_scroll")), ("Esc", t("k_back")), ("q", t("k_quit")))
    return (("↑↓", t("k_service")), ("←→", t("k_engine")), ("Enter", t("k_detail")),
            ("r", t("k_reread")), ("p", t("k_brain")), ("q", t("k_quit")))


def render(state, w, h):
    w, h = max(1, w), max(2, h)
    K = SB.K()
    word = HL.section_word("conexiones")
    title = t("title") + " · " + t("readonly")
    hit = state["_hit"] = {}
    if state["detail"]:
        pw, iw = SB.widths(w, max(30, w - 10))
        body = _detail_styled(state, K, iw)
        lines = SB.frame(K, w, h, word, t("detail") + " · " + title, body, _chips(state),
                         box_w=max(30, w - 10), scroll=state["scroll"])
        state["scroll"] = max(0, min(state["scroll"], SB.frame.last_max_scroll))
        return lines
    W = max(1, w - 1)
    side_pw = SIDE_W + 4 + 2 * SB.PAD
    all_iw = 2 + NAME_MAX + sum(max(HL.vis(tt), 4) + 2 for _, tt in inventory.ENGINES)
    paired = W - SB.SIDE_GAP - side_pw - (4 + 2 * SB.PAD) >= 40 + 2 * SB.PAD
    if paired:
        box_w = min(all_iw, W - SB.SIDE_GAP - side_pw - (4 + 2 * SB.PAD))
    else:
        box_w = min(all_iw, W - (4 + 2 * SB.PAD))
    pw, iw = SB.widths(w, box_w)
    built = {}

    def table(width):
        built["body"] = _body(state, K, width, paired, hit)
        return built["body"]
    side = None
    if paired:
        side = (t("detail"), lambda sw: _detail_styled(state, K, sw), SIDE_W)
    lines = SB.frame(K, w, h, word, title, table, _chips(state),
                     cursor_line=lambda: hit.get("cursor", 0),
                     box_w=box_w, stable_rows=18, side=side)
    # coordenadas de pantalla (0-based) para los clics
    top, col = SB.frame.last_body_row, SB.frame.last_body_col
    hit["abs_rows"] = {top + i: idx for i, idx in hit.get("rows", {}).items()}
    hit["abs_hdr"] = top + hit.get("hdr", 0)
    hit["col"] = col
    hit["paired"] = paired
    return lines


def _click(state, x, y):
    hit = state.get("_hit") or {}
    if state["detail"] or not hit:
        return
    bx, by = (x - 1) - hit.get("col", 0), y - 1
    if by == hit.get("abs_hdr"):
        arrows = hit.get("arrows") or {}
        n = state.get("_nvis", 1)
        if arrows.get("left") is not None and bx == arrows["left"]:
            state["first"] = max(0, state["first"] - 1)
        elif arrows.get("right") is not None and bx == arrows["right"]:
            state["first"] = min(len(inventory.ENGINES) - n, state["first"] + 1)
        else:
            for x0, x1, e in hit.get("engines", ()):
                if x0 <= bx < x1:
                    state["engine"] = e
            return
        state["engine"] = max(state["first"], min(state["engine"], state["first"] + n - 1))
        return
    if by in hit.get("abs_rows", {}):
        state["row"] = hit["abs_rows"][by]
        for x0, x1, e in hit.get("engines", ()):
            if x0 <= bx < x1:
                state["engine"] = e
        if not hit.get("paired"):
            state["detail"], state["scroll"] = True, 0
        selected(state)


def refresh(state):
    project = [state["projects"][state["project"]]] if state["project"] >= 0 else (state["projects"] if state["project"] == -2 else [])
    state["data"] = inventory.scan(projects=project)
    state["scroll"] = 0


def act(state, key):
    xy = SB.parse_mouse(key)
    if xy is not None:
        _click(state, *xy)
        return True
    if key in ("q", "\x03", "\x1b"):
        if state["detail"] and key == "\x1b":
            state["detail"] = False
            return True
        return False
    if key in ("\r", "\n", "enter"):
        state["detail"] = not state["detail"]
        state["scroll"] = 0
    elif key in ("left", "right", "h", "l"):
        state["engine"] = (state["engine"] + (-1 if key in ("left", "h") else 1)) % len(inventory.ENGINES)
        state["scroll"] = 0
    elif key in ("up", "down", "k", "j"):
        delta = -1 if key in ("up", "k") else 1
        field = "scroll" if state["detail"] else "row"
        state[field] = max(0, state[field] + delta)
        selected(state)
    elif key == "r":
        refresh(state)
    elif key == "p":
        state["project"] += 1
        if state["project"] >= len(state["projects"]):
            state["project"] = -2
        refresh(state)
    return True


render = responsive_ui.renderer(render, "CONEXIONES")
act = responsive_ui.action(act)


def project_choices():
    import dispatch
    result = []
    try:
        entries = dispatch.load_registry().get("agents", []) or []
    except Exception:
        return []
    for entry in entries:
        try:
            cfg = dispatch.load_agent_cfg(entry)
            path = dispatch.resolve_brain(entry["name"], cfg)
            if path and os.path.isdir(path):
                result.append(os.path.abspath(path))
        except Exception:
            continue
    return sorted(set(result))


def _draw(out, state, first=False):
    w, h = SF.size()
    responsive_ui.paint(out, render(state, w, h), first=first)


def _loop(state):
    """Teclado en Mac/Linux y Windows; los clics (SGR-1006) solo en Mac/Linux,
    como Modelos de decisión: en Windows, por ahora, solo teclado."""
    if os.name == "nt":
        out = sys.stdout
        out.write("\033[?1049h\033[?25l")
        _draw(out, state, first=True)
        keys = SB.WinKeyReader()
        try:
            while True:
                key = keys.get(0.5)
                if key is None:
                    _draw(out, state)
                    continue
                if key and not act(state, key):
                    return
                if not keys.pending():
                    _draw(out, state)
        except KeyboardInterrupt:
            pass
        finally:
            out.write("\033[?25h\033[?1049l")
            out.flush()
        return
    import termios
    import tty
    fd = os.open("/dev/tty", os.O_RDWR)
    old = termios.tcgetattr(fd)
    try:
        with open("/dev/tty", "w", encoding="utf-8") as out:
            tty.setraw(fd)
            out.write("\033[?1049h\033[?25l\033[?1000h\033[?1006h")
            keys = SB.KeyReader(fd, mouse=True)
            try:
                _draw(out, state, first=True)
                while True:
                    key = keys.get(0.5)
                    if key is None:
                        _draw(out, state)
                        continue
                    if not key:
                        continue
                    if not act(state, key):
                        return
                    if not keys.pending():
                        _draw(out, state)
            except KeyboardInterrupt:
                pass
            finally:
                out.write("\033[?1000l\033[?1006l\033[?25h\033[?1049l")
                out.flush()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        os.close(fd)


def _interactivo():
    """¿Consola de verdad? `isatty()` no basta en Windows: NUL es un dispositivo de
    caracteres (isatty True) y la pantalla esperaba teclas para siempre. _console es la
    regla compartida de Workspace (la misma de Decisores, Modelos y Conversaciones)."""
    try:
        import _console
        return _console.interactive()
    except Exception:
        try:
            return sys.stdin.isatty() and sys.stdout.isatty()
        except Exception:
            return False


def main(args=None):
    args = list(sys.argv[1:] if args is None else args)
    if "--counts" in args:
        print(json.dumps(inventory.counts(inventory.scan(projects=project_choices())), sort_keys=True))
        return 0
    choices = project_choices()
    state = initial(inventory.scan(projects=choices))
    state["projects"] = choices
    if not _interactivo():
        print("\n".join(render(state, 110, 36)))
        return 0
    _loop(state)
    return 0


@_theme_screen
def run():
    return main([])


def cli(args=None):
    args = list(sys.argv[1:] if args is None else args)
    return main(args) if "--counts" in args else run()


if __name__ == "__main__":
    # ARCHIVO MÍNIMO por una versión (se borra en la versión 2): esta pantalla ya no se abre. Quien la corre
    # directo, o un hub que quedó abierto durante la actualización, llega a lo nuevo (puertas.redirigir).
    import puertas
    sys.exit(puertas.redirigir('conexiones', sys.argv[1:]))
