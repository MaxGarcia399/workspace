#!/usr/bin/env python3
"""WORKSPACE · comandos_tui — sección COMANDOS del hub (lanzador).

Todo lo que puedes escribir en la terminal, agrupado, con lo justo
(rediseño 2026-10-14: una caja centrada y vertical):
  arriba  los comandos por grupo (tus agentes · tu día · trabajo · esta
          máquina; «desarrollo» solo en modo dev), en una ventana fija
  abajo   el elegido: cómo se escribe, qué hace y qué hace Enter
  i       abre a la DERECHA un segundo cuadro con el mapa del elegido (vertical),
          cuándo te sirve y sus otros nombres; cambia al moverte por la lista
          (en una ventana angosta ocupa la caja)
  ↑↓ elige · ◄► grupo · / busca (nombre, alias o qué hace) · Enter ejecuta · q vuelve

Todo sale del catálogo único (comandos.py): nombres en el idioma de la UI,
mismos datos que `workspace --help` y `workspace comandos --json`.

Enter EJECUTA (equivalente a Super+Space de Omarchy): sale del TUI limpio,
corre `workspace <cmd>` y, si vino del hub, espera Enter y vuelve al hub.
  · los marcados peligrosos piden «¿Seguro? s/n» aquí mismo;
  · los que necesitan argumentos solo muestran cómo se escriben;
  · los no ejecutables (el hub, `<agente>`, esta misma lista) avisan.
Mismo lenguaje que Agentes/Actualizaciones (section_box).
"""
import os
import subprocess
import sys
import time

import comandos as C
import hublayout as HL
import section_box as SB
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
            ("Enter", _t("comandos.k.run", "ejecuta", "run")),
            ("/", _t("comandos.k.find", "busca", "find")),
            ("i", _t("comandos.k.hide", "oculta la explicación", "hides the explanation")
             if S.get("panel") else _t("comandos.k.info", "cómo funciona", "how it works")),
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


# ══ REDISEÑO 2026-10-14 (concepto Omarchy, pedido del dueño) ═══════════════
# Una caja centrada y VERTICAL: la lista agrupada (ventana fija con «▲/▼ n
# más», no se sacude al moverte) y, bajo una regla con su nombre, cómo se
# escribe el elegido, qué hace y qué hace Enter. Lo didáctico (cuándo te
# sirve, sus otros nombres, su mapa y cómo funciona la lista) va en `i`.
BOX_W = 56
#: Filas MÍNIMAS de la lista (encabezados de grupo incluidos); con alto de
#: sobra la ventana crece y, si cabe, se ve la lista entera.
LIST_ROWS = 8
#: Lo que ocupa todo lo demás en pantalla (wordmark, botones, bordes,
#: búsqueda y el detalle del elegido).
_RESTO = 30


def _lista(S, K, iw):
    rows = visible(S)
    gname = {g[0]: (g[2] if _en() else g[1]) for g in S["groups"]}
    gids = [g[0] for g in S["groups"]]
    lines, last = [], None                      # [(línea, índice del comando | None)]
    for n, c in enumerate(rows):
        if c["group"] != last:
            if last is not None:
                lines.append(("", None))
            lines.append((SF.divisor(K, gname.get(c["group"], c["group"]), iw,
                                     tono=gids.index(c["group"]) * 2), None))
            last = c["group"]
        on = (n == S["i"])
        cur = ("%s›%s " % (K["C"] + K["BO"], K["R"])) if on else "  "
        tinta = (K["C"] + K["BO"]) if on else K["GREY"]
        lines.append((HL.clip("%s%s%s%s" % (cur, tinta, _name(c), K["R"]), iw), n))
    if not rows:
        return [HL.clip("%s%s%s" % (K["DK"], _t("comandos.none", "ningún comando coincide",
                                                 "no command matches"), K["R"]), iw)]
    alto = S.get("_rows", LIST_ROWS)
    if len(lines) <= alto:
        return [ln for ln, _n in lines]
    # ventana FIJA de `alto` filas con el elegido a la vista
    filas = alto - 2
    sel = next(k for k, (_ln, n) in enumerate(lines) if n == S["i"])
    start = max(0, min(sel - filas // 2, len(lines) - filas))
    arriba = sum(1 for _ln, n in lines[:start] if n is not None)
    abajo = sum(1 for _ln, n in lines[start + filas:] if n is not None)

    def mas(flecha, k):
        return ("%s%s %s%s" % (K["DIM"], flecha, _t("comandos.more", "{n} más", "{n} more", n=k),
                               K["R"])) if k else ""
    vista = lines[start:start + filas]
    # que la ventana no termine en un encabezado (o un hueco) sin sus comandos
    sobra = 0
    while vista and vista[-1][1] is None:
        vista.pop()
        sobra += 1
    return ([mas("▲", arriba)] + [ln for ln, _n in vista] + [""] * sobra
            + [mas("▼", abajo)])


def _detalle(S, K, iw):
    """El elegido: cómo se escribe, qué hace y qué hace Enter."""
    c = current(S)
    if c is None:
        return []
    out = [SB.stack(K, [], [], iw, label=_name(c))[1]]
    out += ["  %s%s%s" % (K["C"] + K["BO"], ln, K["R"])
            for ln in SB._wrap(C.usage_of(c), max(8, iw - 2))[:2]]
    out += ["  %s%s%s" % (K["GREY"], ln, K["R"])
            for ln in SB._wrap(C.summary_of(c), max(8, iw - 2))[:3]]
    out += ["  %s▸ %s%s" % (K["B2"], ln, K["R"]) for ln in SB._wrap(_hint(c), max(8, iw - 4))[:1]]
    return [HL.clip(ln, iw) for ln in out]


def _cuerpo(S, K, iw):
    out = []
    if S.get("filtering") or S.get("query"):
        out += [HL.clip(" %s/ %s%s%s%s" % (K["C"] + K["BO"], K["WH"] + K["BO"], S["query"],
                                           "▏" if S.get("filtering") else "", K["R"]), iw), ""]
    lista = _lista(S, K, iw)
    S["_cursor"] = len(out) + next((k for k, ln in enumerate(lista)
                                    if SB._ANSI.sub("", ln).startswith("› ")), 0)
    return out + lista + [""] + _detalle(S, K, iw)


#: Ancho del cuadro lateral de `i` (mapa vertical + explicación).
PANEL_W = 40


def _parte(txt, ancho):
    """Las etiquetas de los mapas traen «larga|corta»: la larga si cabe."""
    largo, _, corto = str(txt).partition("|")
    return largo if HL.vis(largo) <= ancho or not corto else corto


def _mapa_vertical(K, spec, iw):
    """El mapa del comando de arriba hacia abajo: cada paso en su cajita y,
    entre uno y otro, la flecha con lo que lo lleva al siguiente."""
    nodes, caps, _nota = spec
    box = K["BOX"]
    tl, tr, bl, br, v, hh = box[0], box[1], box[2], box[3], box[4], box[5]
    tinta = {"wh": K["WH"], "c": K["C"], "ok": K["OK"]}
    mid = iw // 2
    out = []
    for i, (lab, tono) in enumerate(nodes):
        lab = _parte(lab, iw - 6)
        a = HL.vis(lab) + 2
        lp = " " * max(0, mid - (a + 2) // 2)
        out += [lp + "%s%s%s%s%s" % (K["B2"], tl, hh * a, tr, K["R"]),
                lp + "%s%s%s %s%s%s %s%s%s" % (K["B2"], v, K["R"], tinta.get(tono, K["WH"]) + K["BO"],
                                               lab, K["R"], K["B2"], v, K["R"]),
                lp + "%s%s%s%s%s" % (K["B2"], bl, hh * a, br, K["R"])]
        if i < len(nodes) - 1:
            cap = _parte(caps[i], iw - mid - 3) if i < len(caps) else ""
            out.append(" " * mid + "%s│%s" % (K["DK"], K["R"])
                       + ("  %s%s%s" % (K["DIM"], cap, K["R"]) if cap else ""))
            out.append(" " * mid + "%s▼%s" % (K["C"] + K["BO"], K["R"]))
    return [HL.clip(ln, iw) for ln in out]


def _panel(S, K, iw):
    """El cuadro de la derecha: el mapa del comando elegido (vertical), su
    nota, cuándo te sirve y sus otros nombres. Cambia al moverte."""
    c = current(S)
    if c is None:
        return []
    out = []
    spec = C.command_map(c["id"])
    if spec:
        out += _mapa_vertical(K, spec, iw) + [""]
        if spec[2]:
            out += ["%s%s%s" % (K["DIM"], ln, K["R"]) for ln in SB._wrap(spec[2], iw)[:3]]
            out.append("")
    out.append(SF.divisor(K, _t("comandos.when", "cuándo", "when"), iw, tono=4))
    out += ["%s%s%s" % (K["GREY"], ln, K["R"]) for ln in SB._wrap(C.when_of(c), iw)[:4]]
    al = C.shown_aliases(c)
    if al and c["dispatch"]:
        out.append("")
        out += ["%s%s%s" % (K["DIM"], ln, K["R"]) for ln in SB._wrap(
            _t("comandos.also", "también: {names}", "also: {names}", names=" · ".join(al)), iw)[:2]]
    return [HL.clip(ln, iw) for ln in out]


def info_blocks(S, K):
    """El cuadro de `i`: el comando elegido a fondo (cómo se escribe, qué
    hace, cuándo te sirve, otros nombres y su mapa) y cómo funciona la lista."""
    c = current(S)
    blocks = []
    if c is not None:
        blocks += [("h", _name(c)), ("code", C.usage_of(c)), ("p", C.summary_of(c))]
        kv = [(_t("comandos.when", "cuándo", "when"), C.when_of(c))]
        al = C.shown_aliases(c)
        if al and c["dispatch"]:
            kv.append((_t("comandos.also_k", "también", "also"), " · ".join(al)))
        blocks += [("kv", kv)]
        if C.command_map(c["id"]):
            blocks += [("gap",), ("lines", lambda iw, c=c: _mini_map(K, c["id"], iw, 7) or [])]
        blocks += [("gap",)]
    blocks += [
        ("h", _t("comandos.info.h_list", "cómo funciona esta lista", "how this list works")),
        ("kv", [("↑↓", _t("comandos.k.pick", "elige", "pick")),
                ("◄►", _t("comandos.info.group", "salta de grupo", "jumps between groups")),
                ("/", _t("comandos.info.find", "busca por nombre, otro nombre o lo que hace",
                         "searches by name, other name or what it does")),
                ("Enter", _t("comandos.info.enter", "lo ejecuta: sale, corre «workspace <comando>» y vuelve al hub",
                             "runs it: leaves, runs «workspace <command>» and comes back to the hub"))]),
        ("p", _t("comandos.info.p1",
                 "Los que necesitan algo más (un agente, un correo) solo te muestran cómo se escriben; "
                 "los que cambian tu instalación (actualizar, desinstalar) piden confirmación.",
                 "The ones that need something else (an agent, an email) only show you how to type them; "
                 "the ones that change your installation (update, uninstall) ask for confirmation.")),
        ("p", _t("comandos.info.p2",
                 "Es la misma lista que «workspace ayuda»; tus agentes la leen con «workspace comandos --json».",
                 "It's the same list as «workspace help»; your agents read it with «workspace commands --json».")),
    ]
    return blocks


def render(S, w, h):
    rows = visible(S)
    S["i"] = max(0, min(S.get("i", 0), max(0, len(rows) - 1)))
    K = SF.K()
    S["_pair"] = bool(S.get("panel")) and SB.pair_fits(w, BOX_W, PANEL_W)
    if S.get("panel") and not S["_pair"]:
        # angosta: no cabe el cuadro al lado → la explicación ocupa la caja
        return SB.info_frame(K, w, h, HL.section_word("comandos"),
                             _t("comandos.info.title", "CÓMO FUNCIONAN LOS COMANDOS",
                                "HOW COMMANDS WORK"),
                             info_blocks(S, K), state=S.setdefault("info", {"scroll": 0}),
                             box_w=66)
    side = None
    if S["_pair"]:
        c = current(S)
        side = (_t("comandos.panel", "CÓMO FUNCIONA", "HOW IT WORKS")
                + (" · " + _name(c).upper() if c else ""), lambda iw: _panel(S, K, iw), PANEL_W)
    S["_rows"] = max(LIST_ROWS, h - _RESTO)
    alto = 2 + S["_rows"] + 1 + 7
    if side:
        # el cuadro más alto de todos: moverse por la lista no sacude la caja
        i0 = S["i"]
        for k in range(len(rows)):
            S["i"] = k
            alto = max(alto, len(_panel(S, K, PANEL_W)))
        S["i"] = i0
    # alto de referencia: búsqueda (2) + lista + aire + regla + detalle (hasta 6)
    return SB.frame(K, w, h, HL.section_word("comandos"), _t("comandos.box", "COMANDOS", "COMMANDS"),
                    lambda iw: _cuerpo(S, K, iw), pares(S), msg=S.get("msg", ""),
                    cursor_line=lambda: S.get("_cursor", 0), box_w=BOX_W,
                    stable_rows=alto, side=side)


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
    if key in SB.INFO_KEYS:                  # i / ? abre o cierra el cuadro de la explicación
        S["panel"] = not S.get("panel")
        S.pop("info", None)
        return True
    if S.get("panel") and not S.get("_pair"):
        # angosta: la explicación ocupa la caja → ↑↓ la desplazan, Esc/q la cierran
        st = S.setdefault("info", {"scroll": 0})
        if key in ("up", "down"):
            st["scroll"] = max(0, st.get("scroll", 0) + (-1 if key == "up" else 1))
        elif key in ("q", "Q", "\x1b"):
            S["panel"] = False
            S.pop("info", None)
        return key != "\x03"
    if S.get("panel") and key == "\x1b" and not S.get("query"):
        S["panel"] = False                   # Esc oculta el cuadro; q vuelve al hub
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
        # WORKSPACE_DESDE_COMANDOS: el comando sabe que el hub sigue abierto
        # detrás (p. ej. «bienvenida» no abre otro hub al terminar)
        rc = subprocess.call(command_argv(c), cwd=HERE,
                             env=dict(os.environ, WORKSPACE_DESDE_COMANDOS="1"))
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
