"""WORKSPACE · agents_tui — sección AGENTES: qué agentes tienes y cuáles ve el hub.

Rediseño 2026-10 (misión: transparencia · simpleza · utilidad real). Solo lo
que se puede HACER con un agente, con su estado real:

  izquierda   tus agentes en tres grupos: en el hub · fuera del hub ·
              necesitan arreglo (con la causa)
  derecha     el elegido: estado, si está en el hub, motor y cerebro, y la
              tecla de cada acción

  espacio  pone/quita del hub AL INSTANTE (el mismo espacio lo deshace)
  Enter    repara (usa la ruta encontrada si hay una)
  e ruta · m motor · x quitar del registro (confirma) · a agregar · q vuelve

Todo deriva del estado compartido (agent_state): si otra ventana cambia un
agente, la lista se actualiza sola. Las mutaciones van por agent_manage
(revalidan identidad; un fallo nunca se anuncia como éxito). Quitar del hub
o del registro NO borra nada del disco.
"""
import os
import shutil
import sys
import time

import hublayout as HL
import section_frame as SF
from theme import screen as _theme_screen  # fondo/tinta del tema

ROOT = os.path.dirname(os.path.abspath(__file__))
_t = SF.t


def word():
    return HL.section_word("agentes")


def _K():
    return SF.K()


# ── datos (estado compartido) ────────────────────────────────────────────────
def agents():
    """Agentes registrados (sanos, averiados y ocultos), cada uno como dict
    con name/display/_brain/_state."""
    try:
        import agent_state
        snap = agent_state.snapshot()
    except Exception:
        return []
    out = []
    for a in snap.registered(include_hidden=True):
        out.append({"name": a["name"], "_id": a["id"], "display": a["display"],
                    "engine": a["engine"], "_brain": a["brain"] or "",
                    "_state": dict(a)})
    return out


def group_of(cfg):
    st = cfg.get("_state") or {}
    if st.get("status") not in ("ready", "hidden"):
        return "fix"
    return "out" if st.get("hidden") else "hub"


_GROUPS = (("hub", "en el hub", "in the hub"),
           ("out", "fuera del hub", "not in the hub"),
           ("fix", "necesitan arreglo", "need fixing"))


def ordered(items):
    rank = {g: i for i, (g, _e, _n) in enumerate(_GROUPS)}
    return sorted(items, key=lambda c: (rank[group_of(c)], c.get("display", "").lower()))


def state_revision():
    try:
        import agent_state
        return agent_state.snapshot().revision
    except Exception:
        return None


def initial(name=None):
    items = ordered(agents())
    idx = next((i for i, c in enumerate(items) if c.get("name") == name), 0)
    return {"agents": items, "index": idx, "msg": "", "rev": state_revision()}


def reload_if_changed(S, force=False):
    """Relee si el estado compartido cambió (otra ventana o una acción
    propia). Conserva la selección por NOMBRE. True si cambió."""
    rev = state_revision()
    if not force and rev is not None and rev == S.get("rev"):
        return False
    cur = S["agents"][S["index"]].get("name") if S.get("agents") else None
    S["agents"] = ordered(agents())
    S["rev"] = rev
    names = [c.get("name") for c in S["agents"]]
    if cur in names:
        S["index"] = names.index(cur)
    else:
        S["index"] = min(S.get("index", 0), max(0, len(names) - 1))
        if cur and not force:
            S["msg"] = _t("agentes.gone", "{name} ya no está registrado (cambió desde otra ventana)",
                          "{name} is no longer registered (changed from another window)", name=cur)
    S.pop("confirm", None)
    return True


def _label(status):
    try:
        import agent_state
        return agent_state.label(status)
    except Exception:
        return status


def status_line(cfg):
    st = cfg.get("_state") or {}
    parts = [_label(st.get("status", "ready"))]
    if st.get("cause"):
        parts.append(st["cause"])
    if st.get("status") not in (None, "ready", "hidden") and st.get("repair"):
        parts.append("→ " + st["repair"])
    return " · ".join(parts)


# ── render ───────────────────────────────────────────────────────────────────
def pares(S=None):
    if S and S.get("input"):
        return (("Enter", _t("agentes.k.save", "guardar", "save")),
                ("Esc", _t("agentes.k.cancel", "cancelar", "cancel")))
    return (("↑↓", _t("agentes.k.pick", "elige", "pick")),
            (_t("agentes.k.space", "espacio", "space"), _t("agentes.k.hub", "en el hub", "in hub")),
            ("Enter", _t("agentes.k.fix", "repara", "fix")),
            ("e", _t("agentes.k.path", "ruta", "path")),
            ("m", _t("agentes.k.engine", "motor", "engine")),
            ("x", _t("agentes.k.remove", "quitar", "remove")),
            ("a", _t("agentes.k.add", "agregar", "add")),
            ("q", _t("agentes.k.back", "vuelve", "back")))


def _mark(K, cfg):
    g = group_of(cfg)
    if g == "fix":
        return "%s✗%s" % (K["ERR"], K["R"])
    if g == "out":
        return "%s○%s" % (K["DK"], K["R"])
    return "%s●%s" % (K["OK"], K["R"])


def _left(S, K):
    def build(iw, ih):
        out, cur_line, last = [], 0, None
        for i, cfg in enumerate(S["agents"]):
            g = group_of(cfg)
            if g != last:
                if out:
                    out.append("")
                es, en = next((e, n) for gg, e, n in _GROUPS if gg == g)
                out.append(SF.divisor(K, _t("agentes.g." + g, es, en), iw,
                                      tono={"hub": 0, "out": 6, "fix": 3}[g]))
                last = g
            st = cfg["_state"]
            val = cfg.get("engine") if g != "fix" else _label(st.get("status"))
            if i == S["index"]:
                cur_line = len(out)
            out.append(SF.row(K, cfg.get("display") or cfg["name"], val, iw,
                              sel=(i == S["index"]), mark=_mark(K, cfg),
                              value_col=K["ERR"] if g == "fix" else None))
        S["_cursor_line"] = cur_line
        return out
    return build


def _right(S, K):
    def build(iw, ih):
        cfg = S["agents"][S["index"]]
        st = cfg["_state"]
        g = group_of(cfg)
        out = []
        if S.get("input"):
            out += SF.text(K, _t("agentes.input.path2", "Nueva ruta del cerebro:",
                                 "New brain path:"), iw, K["C"] + K["BO"])
            out.append(HL.clip("  %s%s▏%s" % (K["WH"] + K["BO"], S["input"]["buf"], K["R"]), iw))
            out.append("")
            out += SF.text(K, _t("agentes.input.help", "Pega la carpeta del cerebro. Enter guarda, Esc cancela.",
                                 "Paste the brain folder. Enter saves, Esc cancels."), iw, K["DIM"])
            return out
        col = {"hub": K["OK"], "out": K["DIM"], "fix": K["ERR"]}[g]
        mark = "● " if g == "hub" else "○ " if g == "out" else "✗ "
        out += SF.text(K, mark + status_line(cfg), iw, col + K["BO"], max_lines=3)
        out.append("")
        hub_v = _t("agentes.v.in", "visible", "visible") if not st.get("hidden") \
            else _t("agentes.v.out", "oculto", "hidden")
        out.append(SF.kv(K, _t("agentes.f.hub", "hub", "hub"), hub_v, iw,
                         hint=_t("agentes.h.space", "espacio cambia", "space toggles")))
        out.append(SF.kv(K, _t("agentes.f.engine", "motor", "engine"), cfg.get("engine") or "—", iw,
                         hint=_t("agentes.h.m", "m cambia", "m changes")))
        out.append(SF.kv(K, _t("agentes.f.brain", "cerebro", "brain"),
                         HL.clip(cfg.get("_brain") or "—", max(10, iw - 30)), iw,
                         hint=_t("agentes.h.e", "e cambia", "e changes")))
        if st.get("suggested_brain"):
            out.append("")
            out += SF.text(K, _t("agentes.found", "Encontrado en {p} — Enter lo usa",
                                 "Found at {p} — Enter uses it", p=st["suggested_brain"]),
                           iw, K["C"] + K["BO"], max_lines=2)
        if S.get("confirm") == cfg["name"]:
            out.append("")
            out += SF.text(K, _t("agentes.confirm2", "x otra vez quita a {n} del registro. Cerebro y sesiones se quedan en disco.",
                                 "x again removes {n} from the registry. Brain and sessions stay on disk.",
                                 n=cfg.get("display") or cfg["name"]), iw, K["ERR"] + K["BO"], max_lines=3)
        out.append("")
        out += SF.bullets(K, [
            _t("agentes.b1", "espacio lo pone o quita del hub al instante; nada se borra",
               "space adds or removes it from the hub instantly; nothing is deleted"),
            _t("agentes.b2", "x lo quita del registro de esta máquina (pide confirmar)",
               "x removes it from this machine's registry (asks to confirm)"),
            _t("agentes.b3", "a crea o carga otro agente", "a creates or loads another agent"),
        ], iw)
        return out
    return build


def render(S, w, h):
    K = _K()
    sub = _t("agentes.sub2", "agentes — los tuyos y cuáles ve el hub",
             "agents — yours and which ones the hub shows")
    title_l = _t("agentes.box.left2", "TUS AGENTES", "YOUR AGENTS")
    if not S.get("agents"):
        empty = SF.text(K, _t("agentes.empty2", "Aún no tienes agentes. a crea o carga uno.",
                              "No agents yet. a creates or loads one."), 60, K["DIM"])
        return SF.frame(K, w, h, sub, word(), pares(S), title_l, empty, "—", [],
                        msg=S.get("msg", ""))
    S["index"] = max(0, min(S["index"], len(S["agents"]) - 1))
    cfg = S["agents"][S["index"]]
    left = _left(S, K)
    left(30, 999)                          # calcula la línea del cursor
    return SF.frame(K, w, h, sub, word(), pares(S), title_l, left,
                    (cfg.get("display") or cfg["name"]).upper(), _right(S, K),
                    msg=S.get("msg", ""), cursor_line=S.get("_cursor_line", 0),
                    focus_left=not S.get("input"))


# ── acciones ─────────────────────────────────────────────────────────────────
def _selected(S):
    return S["agents"][S["index"]] if S.get("agents") else None


def _manage(S, fn, *args):
    """Operación de agent_manage sobre el seleccionado, revalidando su
    identidad. Muestra el resultado REAL y relee el estado."""
    cfg = _selected(S)
    if not cfg:
        return False
    try:
        import agent_manage
        r = getattr(agent_manage, fn)(cfg.get("_id") or cfg.get("name"), *args,
                                      expected_brain=cfg.get("_brain") or "")
    except Exception as e:
        r = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
    S["msg"] = ("✓ " + r.get("msg", "")) if r.get("ok") else ("✗ " + str(r.get("error")))
    reload_if_changed(S, force=True)
    return bool(r.get("ok"))


def _toggle_hub(S):
    cfg = _selected(S)
    hidden = bool((cfg.get("_state") or {}).get("hidden"))
    name = cfg.get("display") or cfg["name"]
    if _manage(S, "set_hidden", not hidden):
        S["msg"] = "✓ " + (_t("agentes.m.in", "{n} vuelve al hub", "{n} is back in the hub", n=name)
                           if hidden else
                           _t("agentes.m.out", "{n} fuera del hub · espacio lo regresa",
                              "{n} removed from the hub · space brings it back", n=name))


def _repair(S):
    cfg = _selected(S)
    st = cfg.get("_state") or {}
    if st.get("suggested_brain"):
        _manage(S, "set_brain", st["suggested_brain"])
    elif group_of(cfg) == "fix":
        if st.get("status") in ("brain_missing", "definition_missing", "brain_unreadable"):
            S["input"] = {"kind": "path", "buf": ""}
        else:
            S["msg"] = status_line(cfg)
    else:
        S["msg"] = _t("agentes.m.ok", "{n} está listo — no hay nada que reparar",
                      "{n} is ready — nothing to fix", n=cfg.get("display") or cfg["name"])


def _input_key(S, key):
    inp = S["input"]
    if key in ("\x1b", "\x03"):
        S.pop("input", None)
        S["msg"] = _t("agentes.cancelled", "cancelado · nada se guardó", "cancelled · nothing saved")
    elif key in ("\r", "\n"):
        S.pop("input", None)
        _manage(S, "set_brain", inp["buf"])
    elif key in ("\x08", "\x7f"):
        inp["buf"] = inp["buf"][:-1]
    elif isinstance(key, str) and len(key) == 1 and key.isprintable():
        inp["buf"] += key
    return True


def act(S, key):
    """True = sigue · False = vuelve al hub (o pide agregar)."""
    if S.get("input"):
        return _input_key(S, key)
    if key in ("q", "Q", "\x1b", "\x03"):
        return False
    if key == "a":
        S["request"] = "add"
        return False
    if not S.get("agents"):
        return True
    if key != "x":
        S.pop("confirm", None)
    S["msg"] = ""
    n = len(S["agents"])
    if key in ("up", "down"):
        S["index"] = (S["index"] + (-1 if key == "up" else 1)) % n
    elif key == "tab":
        S["index"] = (S["index"] + 1) % n
    elif key == " ":
        _toggle_hub(S)
    elif key in ("\r", "\n"):
        _repair(S)
    elif key == "e":
        S["input"] = {"kind": "path", "buf": ""}
    elif key == "m":
        _manage(S, "cycle_engine")
    elif key == "x":
        nm = _selected(S).get("name")
        if S.get("confirm") == nm:
            S.pop("confirm", None)
            _manage(S, "unregister")
        else:
            S["confirm"] = nm
    return True


# ── loop ─────────────────────────────────────────────────────────────────────
def _size(out=None):
    try:
        sz = os.get_terminal_size(out.fileno()) if out else shutil.get_terminal_size((110, 44))
        return sz.columns, sz.lines
    except (OSError, AttributeError, ValueError):
        sz = shutil.get_terminal_size((110, 44))
        return sz.columns, sz.lines


def _draw(out, S, first=False):
    w, h = _size(out)
    lines = render(S, w, h)
    try:
        import responsive_ui
        responsive_ui.paint(out, lines, first=first)
    except Exception:
        out.write("\033[H" + "".join("\033[2K" + ln + "\r\n" for ln in lines) + "\033[J")
        out.flush()


@_theme_screen
def run(name=None):
    """Pantalla interactiva; vuelve al hub con q/Esc. Sin consola → imprime
    un frame y vuelve."""
    S = initial(name)
    try:
        import _console
        live = _console.interactive()
    except Exception:
        live = sys.stdin.isatty()
    if not live:
        for ln in render(S, 110, 44):
            print(ln)
        return None
    while True:
        if os.name == "nt":
            _loop_windows(S)
        else:
            _loop_unix(S)
        if S.pop("request", None) != "add":
            return None
        try:
            import add_agent_tui
            add_agent_tui.run()
        except Exception as e:
            S["msg"] = _t("agentes.add_unavail",
                          "agregar agente no disponible ({e})",
                          "add agent unavailable ({e})", e=type(e).__name__)
        reload_if_changed(S, force=True)


def _loop_unix(S):
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
            _draw(out, S, first)
            first = False
            if not select.select([fd], [], [], .5)[0]:
                reload_if_changed(S)
                continue                         # repinta arriba: tamaño/estado
            if not act(S, _read_key_unix(fd, select)):
                return None
    finally:
        out.write("\033[?25h\033[?1049l")
        out.flush()
        out.close()
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
        os.close(fd)


def _loop_windows(S):
    import msvcrt
    out = sys.stdout
    out.write("\033[?1049h\033[?25l")
    try:
        first = True
        while True:
            _draw(out, S, first)
            first = False
            idle, size = 0, _size(out)
            while not msvcrt.kbhit():
                time.sleep(.05)
                idle += 1
                if idle % 20 == 0 and reload_if_changed(S):
                    _draw(out, S)
                if _size(out) != size:           # ventana redimensionada
                    break
            if not msvcrt.kbhit():
                continue
            key = msvcrt.getwch()
            if key in ("\x00", "\xe0"):
                key = {"H": "up", "P": "down", "K": "left",
                       "M": "right"}.get(msvcrt.getwch(), "")
            elif key == "\t":
                key = "tab"
            if not act(S, key):
                return None
    finally:
        out.write("\033[?25h\033[?1049l")
        out.flush()


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="workspace agentes")
    ap.add_argument("agent", nargs="?")
    a = ap.parse_args(argv)
    run(a.agent)
    return 0


# ── lienzo de mapas ────────────────────────────────────────────────────────────
class _API:
    HL = HL


class _FallbackCanvas:
    """Clon mínimo de agent_create_ui._MapCanvas si aquel no importa."""
    def __init__(self, api, K, width, height):
        self.api, self.K, self.width, self.height = api, K, width, height
        self.cells = [[[" ", K["DK"]] for _ in range(width)] for _ in range(height)]

    def put(self, x, y, value, color=None, limit=None):
        if not 0 <= y < self.height:
            return
        text = HL.clip(" ".join(str(value).split()),
                       limit if limit is not None else max(0, self.width - x))
        for ch in text:
            size = HL.vis(ch)
            if size == 0:
                continue
            if 0 <= x and x + size <= self.width:
                self.cells[y][x] = [ch, color or self.K["WH"]]
                for c in range(1, size):
                    self.cells[y][x + c] = ["", color or self.K["WH"]]
            x += size

    def edge(self, x1, y1, x2, y2, active=True):
        col = self.K["B2"] if active else self.K["DK"]
        if y1 == y2:
            for x in range(min(x1, x2), max(x1, x2) + 1):
                self.put(x, y1, "─", col)
        elif x1 == x2:
            for y in range(min(y1, y2), max(y1, y2) + 1):
                self.put(x1, y, "│", col)

    def lines(self):
        out = []
        for row in self.cells:
            s, prev = "", None
            for ch, col in row:
                if col != prev:
                    s += self.K["R"] + col
                    prev = col
                s += ch
            out.append(s + self.K["R"])
        return out


def _canvas_type():
    try:
        from agent_create_ui import _MapCanvas
        return _MapCanvas
    except Exception:
        return _FallbackCanvas


def _mk(K, w, h):
    return _canvas_type()(_API, K, w, h)


if __name__ == "__main__":
    raise SystemExit(main())
