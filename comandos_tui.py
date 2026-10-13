#!/usr/bin/env python3
"""WORKSPACE · comandos_tui — sección COMANDOS del hub (lanzador).

Todo lo que puedes escribir en la terminal, agrupado, con lo justo:
  izquierda  los comandos por grupo (tus agentes · tu día · trabajo · esta
             máquina; «desarrollo» solo en modo dev)
  derecha    el elegido: cómo se escribe, qué hace, cuándo te sirve y sus
             otros nombres
  ↑↓ elige · / busca (nombre, alias o qué hace) · Enter ejecuta · q vuelve

Todo sale del catálogo único (comandos.py): nombres en el idioma de la UI,
mismos datos que `workspace --help` y `workspace comandos --json`.

Enter EJECUTA (equivalente a Super+Space de Omarchy): sale del TUI limpio,
corre `workspace <cmd>` y, si vino del hub, espera Enter y vuelve al hub.
  · los marcados peligrosos piden «¿Seguro? s/n» aquí mismo;
  · los que necesitan argumentos solo muestran cómo se escriben;
  · los no ejecutables (el hub, `<agente>`, esta misma lista) avisan.
Mismo lenguaje que Atajos/Tono (section_frame).
"""
import os
import subprocess
import sys
import time

import comandos as C
import hublayout as HL
import section_frame as SF
from theme import screen as _theme_screen  # fondo/tinta del tema

_t = SF.t
HERE = os.path.dirname(os.path.abspath(__file__))


def _en():
    return C.lang() == "en"


def is_dev():
    try:
        import dev_tui
        return dev_tui.is_dev()
    except Exception:
        return False


def catalog(dev=None):
    """(grupos, comandos) visibles: producto siempre (sin ocultos);
    desarrollo solo en modo dev y si comandos_dev viaja en este árbol."""
    dev = is_dev() if dev is None else dev
    return C.groups(dev), C.visible(dev)


def initial(dev=None):
    groups, cmds = catalog(dev)
    return {"groups": groups, "all": cmds, "query": "", "filtering": False,
            "i": 0, "msg": "", "confirm": None, "chosen": None}


def _name(c):
    return C.display_name(c)


def _haystack(c):
    """Dónde busca `/`: todos los nombres visibles, uso y resumen (ES+EN)."""
    parts = C.names_of(c, hidden=False) + [C.usage_of(c, "es"), C.usage_of(c, "en"),
                                           c["summary"]["es"], c["summary"]["en"]]
    return " ".join(parts).casefold()


def visible(S):
    q = S.get("query", "").casefold().strip()
    out = []
    for g in S["groups"]:
        for c in S["all"]:
            if c["group"] != g[0]:
                continue
            if q and q not in _haystack(c):
                continue
            out.append(c)
    return out


def current(S):
    rows = visible(S)
    if not rows:
        return None
    return rows[max(0, min(S.get("i", 0), len(rows) - 1))]


def pares(S):
    if S.get("confirm"):
        return (("s", _t("comandos.k.yes", "sí, ejecuta", "yes, run")),
                ("n", _t("comandos.k.no", "no", "no")))
    if S.get("filtering"):
        return (("Enter", _t("comandos.k.done", "listo", "done")),
                ("Esc", _t("comandos.k.clear", "borrar filtro", "clear filter")))
    return (("↑↓", _t("comandos.k.pick", "elige", "pick")),
            ("◄►", _t("comandos.k.group", "grupo", "group")),
            ("/", _t("comandos.k.find", "busca", "find")),
            ("Enter", _t("comandos.k.run", "ejecuta", "run")),
            ("q", _t("comandos.k.back", "vuelve", "back")))


def _hint(c):
    """Qué hace Enter con este comando (una línea, para el detalle)."""
    if not c["runnable"]:
        return _t("comandos.hint.norun", "se escribe en la terminal", "type it in the terminal")
    if c["requires_args"]:
        return _t("comandos.hint.args", "necesita argumentos: escríbelo en la terminal",
                  "needs arguments: type it in the terminal")
    if c["dangerous"]:
        return _t("comandos.hint.danger", "Enter lo ejecuta (pide confirmación)",
                  "Enter runs it (asks for confirmation)")
    return _t("comandos.hint.run", "Enter lo ejecuta", "Enter runs it")


def _also(c):
    al = C.shown_aliases(c)
    if not al or not c["dispatch"]:
        return ""
    return _t("comandos.also", "también: {names}", "also: {names}", names=" · ".join(al))


def _detail_lines(S, K, c, tw):
    txt = SF.text(K, C.usage_of(c), tw, K["C"] + K["BO"], max_lines=3) + [""]
    txt += SF.text(K, C.summary_of(c), tw, K["WH"], max_lines=4) + [""]
    txt += [SF.divisor(K, _t("comandos.when", "cuándo", "when"), tw, tono=4)]
    txt += SF.text(K, C.when_of(c), tw, K["DIM"], max_lines=3)
    also = _also(c)
    if also:
        txt += SF.text(K, also, tw, K["DIM"], max_lines=2)
    txt += SF.text(K, "▸ " + _hint(c), tw, K["B2"], max_lines=2)
    return txt


def _left(S, K):
    def build(iw, ih):
        rows = visible(S)
        out, cur_line, last = [], 0, None
        if S.get("filtering") or S.get("query"):
            out.append(HL.clip(" %s/ %s%s%s" % (K["C"] + K["BO"], K["WH"] + K["BO"], S["query"],
                                                "▏" if S.get("filtering") else "") + K["R"], iw))
            out.append("")
        gname = {g[0]: (g[2] if _en() else g[1]) for g in S["groups"]}
        gids = [g[0] for g in S["groups"]]
        for n, c in enumerate(rows):
            if c["group"] != last:
                if last is not None:
                    out.append("")
                out.append(SF.divisor(K, gname.get(c["group"], c["group"]), iw,
                                      tono=gids.index(c["group"]) * 2))
                last = c["group"]
            if n == S["i"]:
                cur_line = len(out)
            out.append(SF.row(K, _name(c), "", iw, sel=(n == S["i"])))
        if not rows:
            out += SF.text(K, _t("comandos.none", "ningún comando coincide", "no command matches"), iw, K["DK"])
        S["_cursor"] = cur_line
        return out
    return build


def _right(S, K):
    def build(iw, ih):
        c = current(S)
        if c is None:
            return []
        out = _detail_lines(S, K, c, iw)
        mp = _mini_map(K, c["id"], iw, max(0, ih - len(out) - 2))
        if mp:
            out.append("")
            out.append(SF.divisor(K, _t("comandos.map", "cómo funciona", "how it works"), iw, tono=2))
            out += mp
        return out
    return build


def _mini_map(K, name, iw, ih):
    """Mapa conceptual del comando con el MISMO renderer que los mapas del
    hub (brain_view.pipeline: cajas unidas, tramos rotulados, nota). None si
    no hay mapa o no cabe — la caja queda con el texto, sin mapa mutilado."""
    spec = C.command_map(name)
    if not spec or ih < 5 or iw < 30:
        return None
    nodes, caps, nota = spec
    try:
        import agents_tui
        import brain_view
        return brain_view.pipeline(HL, K, agents_tui._mk, iw, min(ih, 7), nodes, caps, nota)
    except Exception:
        return None


def _columns(S):
    """[(grupo, nombre-grupo, [(índice global, comando)…])…] de lo visible."""
    rows = visible(S)
    cols = []
    for g in S["groups"]:
        items = [(n, c) for n, c in enumerate(rows) if c["group"] == g[0]]
        if items:
            cols.append((g[0], g[2] if _en() else g[1], items))
    return cols


def _grid_box(S, K, w):
    """Caja de comandos en COLUMNAS por grupo (aprovecha el ancho): ↑↓
    dentro del grupo, ◄► entre grupos."""
    cols = _columns(S)
    iw = w - 6
    cw = max(16, iw // max(1, len(cols)))
    height = max((len(items) for _g, _n, items in cols), default=0)
    lines = []
    head = ""
    for k, (_gid, name, _items) in enumerate(cols):
        head += HL.pad(SF.divisor(K, name, cw - 2, tono=k * 2), cw)
    lines.append(HL.clip(head, iw))
    for r in range(height):
        ln = ""
        for _gid, _gn, items in cols:
            if r < len(items):
                n, c = items[r]
                ln += HL.pad(SF.row(K, _name(c), "", cw - 1, sel=(n == S["i"])), cw)
            else:
                ln += " " * cw
        lines.append(HL.clip(ln, iw))
    if S.get("filtering") or S.get("query"):
        lines.insert(0, HL.clip(" %s/ %s%s%s%s" % (K["C"] + K["BO"], K["WH"] + K["BO"], S["query"],
                                                   "▏" if S.get("filtering") else "", K["R"]), iw))
    if not cols:
        lines = SF.text(K, _t("comandos.none", "ningún comando coincide", "no command matches"), iw, K["DK"])
    return HL.full_box(_t("comandos.box", "COMANDOS", "COMMANDS"), lines, K, w - 2, len(lines), True,
                       border=K["C"])


def _detail_box(S, K, w, max_h):
    """El comando elegido: a la izquierda cómo se escribe / qué hace /
    cuándo; a la derecha su mapa conceptual (si cabe)."""
    c = current(S)
    if c is None:
        return []
    iw = w - 6
    tw = max(30, min(56, iw * 45 // 100))
    mw = iw - tw - 2
    txt = _detail_lines(S, K, c, tw)
    mp = _mini_map(K, c["id"], mw, 7) if mw >= 30 else None
    if mp:
        body = []
        n = max(len(txt), len(mp))
        for k in range(n):
            a = txt[k] if k < len(txt) else ""
            b = mp[k] if k < len(mp) else ""
            body.append(HL.pad(a, tw) + "  " + b)
    else:
        body = txt
        mp2 = _mini_map(K, c["id"], iw, 7)
        if mp2 and len(body) + len(mp2) + 1 <= max_h - 2:
            body += [""] + mp2
    body = body[:max(1, max_h - 2)]
    return HL.full_box(_name(c).upper(), body, K, w - 2, len(body), False,
                       border=K["B2"], label=K["B"] + K["BO"])


def render(S, w, h):
    """Ancho (≥110): comandos en columnas arriba y el detalle (texto + mapa)
    abajo — sin cajas medio vacías. Angosto: la lista + detalle de siempre."""
    rows = visible(S)
    S["i"] = max(0, min(S.get("i", 0), max(0, len(rows) - 1)))
    cols = _columns(S)
    w, h = max(1, int(w)), max(2, int(h))
    need = max((len(it) for _g, _n, it in cols), default=0) + 4
    if w >= 110 and len(cols) * 16 <= w - 6 and h >= need + 22:
        K = SF.K()
        L = HL.screen_header(K, w, h, _t("comandos.sub", "comandos — lo que puedes escribir en la terminal",
                                         "commands — what you can type in the terminal"),
                             word=HL.section_word("comandos"), compact_h=40)
        for ln in _grid_box(S, K, w):
            L.append(HL.clip(" " + ln, w - 1))
        foot = HL.instruction_buttons(K, pares(S), w - 1)
        room = (h - 1) - len(L) - 2 - len(foot)
        for ln in _detail_box(S, K, w, room):
            L.append(HL.clip(" " + ln, w - 1))
        L += [""] * max(0, (h - 1) - len(L) - 2 - len(foot))
        L.append("")
        L.append(" %s%s%s" % (K["B2"], S.get("msg", ""), K["R"]) if S.get("msg") else "")
        L.extend(foot)
        return [HL.clip(x, w - 1) for x in L[:h - 1]]
    K = SF.K()
    left = _left(S, K)
    left(40, 999)
    c = current(S)
    title_r = _name(c).upper() if c else "—"
    return SF.frame(K, w, h, _t("comandos.sub", "comandos — lo que puedes escribir en la terminal",
                                "commands — what you can type in the terminal"),
                    HL.section_word("comandos"), pares(S),
                    _t("comandos.box", "COMANDOS", "COMMANDS"), left, title_r, _right(S, K),
                    msg=S.get("msg", ""), cursor_line=S.get("_cursor", 0), header_hints=False)


def _enter(S):
    """Enter sobre el comando elegido. True = sigue el TUI; False = sale
    para ejecutarlo (S["chosen"])."""
    c = current(S)
    if c is None:
        return True
    usage = C.usage_of(c)
    if not c["runnable"]:
        S["msg"] = _t("comandos.msg.norun", "«{u}» se escribe en la terminal",
                      "«{u}» is typed in the terminal", u=usage)
        return True
    if c["requires_args"]:
        S["msg"] = _t("comandos.msg.args", "necesita argumentos — escribe: {u}",
                      "needs arguments — type: {u}", u=usage)
        return True
    if c["dangerous"]:
        S["confirm"] = c["id"]
        S["msg"] = _t("comandos.msg.confirm", "¿Seguro? s/n — se va a correr «workspace {n}»",
                      "Sure? y/n — this will run «workspace {n}»", n=_name(c))
        return True
    S["chosen"] = c
    return False


def act(S, key):
    if S.get("confirm"):
        cid = S.pop("confirm")
        S["confirm"] = None
        if key in ("s", "S", "y", "Y"):
            c = C.get(cid)
            if c is not None:
                S["chosen"] = c
                return False
        S["msg"] = _t("comandos.msg.cancel", "cancelado — no se corrió nada",
                      "cancelled — nothing ran")
        return True
    if S.get("filtering"):
        if key in ("\r", "\n"):
            S["filtering"] = False
        elif key == "\x1b":
            S.update(filtering=False, query="", i=0)
        elif key in ("\x7f", "\b", "\x08"):
            S["query"] = S["query"][:-1]
            S["i"] = 0
        elif key in ("up", "down"):
            n = len(visible(S))
            if n:
                S["i"] = (S["i"] + (-1 if key == "up" else 1)) % n
        elif isinstance(key, str) and len(key) == 1 and key.isprintable():
            S["query"] += key
            S["i"] = 0
        return True
    if key in ("q", "Q", "\x1b", "\x03"):
        if S.get("query") and key == "\x1b":
            S.update(query="", i=0)
            return True
        return False
    S["msg"] = ""
    n = len(visible(S))
    if key in ("\r", "\n"):
        return _enter(S)
    if key in ("up", "down") and n:
        S["i"] = (S["i"] + (-1 if key == "up" else 1)) % n
    elif key in ("left", "right") and n:
        cols = _columns(S)
        for k, (_g, _nm, items) in enumerate(cols):
            idx = [i for i, _c in items]
            if S["i"] in idx:
                r = idx.index(S["i"])
                _g2, _n2, other = cols[(k + (1 if key == "right" else -1)) % len(cols)]
                S["i"] = other[min(r, len(other) - 1)][0]
                break
    elif key == "/":
        S["filtering"] = True
    return True


def command_argv(c):
    """argv para correr `c` igual que si lo escribieras: `workspace <nombre>`
    (por el front.py de ESTE árbol, con el mismo Python)."""
    return [sys.executable, os.path.join(HERE, "front.py"), c["names"]["es"]]


def execute(c, back_to_hub=True):
    """Corre el comando FUERA del TUI (pantalla normal, consola heredada). Si
    vino del hub, espera Enter antes de volver (para que leas la salida).
    Devuelve el exit code. Falla-suave: un error se informa, no truena."""
    print("\n→ workspace %s\n" % _name(c))
    sys.stdout.flush()
    try:
        rc = subprocess.call(command_argv(c), cwd=HERE)
    except Exception as e:
        print("✗ %s: %s" % (type(e).__name__, e))
        rc = 1
    if back_to_hub:
        try:
            input("\n" + _t("comandos.back_hub", "Enter para volver al hub ",
                            "Enter to go back to the hub "))
        except (EOFError, KeyboardInterrupt, OSError):
            pass
    return rc


def _size(out):
    try:
        sz = os.get_terminal_size(out.fileno())
        return sz.columns, sz.lines
    except (OSError, AttributeError, ValueError):
        return 110, 40


def _loop(S):
    """El TUI en pantalla alterna; vuelve cuando el usuario sale o elige un
    comando (S["chosen"]). La pantalla alterna SIEMPRE se restaura antes de
    devolver — el comando corre ya en la pantalla normal."""
    import responsive_ui
    if os.name == "nt":
        import msvcrt
        out = sys.stdout
        out.write("\033[?1049h\033[?25l")
        try:
            first = True
            while True:
                w, h = _size(out)
                responsive_ui.paint(out, render(S, w, h), first=first)
                first = False
                while not msvcrt.kbhit():
                    time.sleep(.03)
                    if _size(out) != (w, h):     # ventana redimensionada
                        break
                if not msvcrt.kbhit():
                    continue
                key = msvcrt.getwch()
                if key in ("\x00", "\xe0"):
                    key = {"H": "up", "P": "down", "K": "left", "M": "right"}.get(msvcrt.getwch(), "")
                if not act(S, key):
                    return
        finally:
            out.write("\033[?25h\033[?1049l")
            out.flush()
    import select
    import termios
    import tty
    from add_agent_tui import _read_key_unix
    fd = os.open("/dev/tty", os.O_RDWR)
    out = open("/dev/tty", "w", encoding="utf-8")
    old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        out.write("\033[?1049h\033[?25l")
        first = True
        while True:
            w, h = _size(out)
            responsive_ui.paint(out, render(S, w, h), first=first)
            first = False
            if not select.select([fd], [], [], .3)[0]:
                continue                         # repinta: la ventana pudo cambiar
            if not act(S, _read_key_unix(fd, select)):
                return
    finally:
        out.write("\033[?25h\033[?1049l")
        out.flush()
        out.close()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        os.close(fd)


@_theme_screen
def run(standalone=False):
    """Desde el hub (default): al ejecutar un comando, espera Enter y
    devuelve None → el hub se vuelve a pintar (patrón loopback de front).
    Standalone (`workspace comandos`): corre el comando y devuelve su exit
    code, sin esperar."""
    S = initial()
    try:
        import _console
        live = _console.interactive()
    except Exception:
        live = sys.stdin.isatty()
    if not live:
        print("\n".join(render(S, 110, 44)))
        return None
    _loop(S)
    c = S.get("chosen")
    if c is None:
        return None
    rc = execute(c, back_to_hub=not standalone)
    return rc if standalone else None


if __name__ == "__main__":
    run(standalone=True)
