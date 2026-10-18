"""WORKSPACE · agents_tui — sección AGENTES: tus agentes y sus opciones.

REDISEÑO 2026-10-14 (concepto Omarchy, pedido del dueño): una caja centrada
(section_box) y VERTICAL. Arriba tus agentes —escala a cualquier cantidad— con
● en el hub · ○ fuera del hub · ✗ necesita arreglo. Abajo, bajo una regla con
su nombre, SUS opciones como lista: en el hub · motor · su
cerebro sin preguntar · revisión de skills · quitar de esta máquina (un
agente averiado empieza por «reparar»).

  ↑↓ elige · Enter/→ entra a sus opciones (↑↓ y Enter cambia; Esc/← sale)
  a agregar (crear o cargar; sin agentes, se abre directo) · i cómo
  funciona · q vuelve

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
import section_box as SB
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
    en_agregar = _en_agregar(S)
    cur = _selected(S).get("name") if _selected(S) else None
    S["agents"] = ordered(agents())
    S["rev"] = rev
    names = [c.get("name") for c in S["agents"]]
    if en_agregar:
        S["index"] = len(names)
    elif cur in names:
        S["index"] = names.index(cur)
    else:
        S["index"] = min(S.get("index", 0), max(0, len(names) - 1))
        if cur and not force:
            S["msg"] = _t("agentes.gone", "{name} ya no está registrado (cambió desde otra ventana)",
                          "{name} is no longer registered (changed from another window)", name=cur)
    S.pop("confirm", None)
    S.pop("_prefs", None)
    if cur not in names:
        S["focus"] = "list"                  # su agente ya no está: no tocar otro
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


# ── REDISEÑO 2026-10-14 (concepto Omarchy): la cajita ─────────────────────
# Una caja centrada y vertical: arriba tus agentes (escala a muchos, con ● en
# el hub · ○ fuera · ✗ necesita arreglo); abajo, el elegido con SUS opciones
# como lista; la flecha al final de su fila dice hacia dónde lleva ←/→. Enter (o →) entra a esas opciones, ↑↓ las recorre y
# Enter cambia la elegida; Esc (o ←) regresa a la lista. Lo didáctico (qué es
# un agente, qué hace cada opción, qué significan las marcas) vive en `i`.
DETAIL_W = 46


def prefs_of(S, cfg):
    """Preferencias del agente (agent_manage.preferences), con caché por
    nombre: se relee al cambiar el estado o tras un cambio propio."""
    cache = S.setdefault("_prefs", {})
    name = cfg.get("name")
    if name not in cache:
        try:
            import agent_manage
            r = agent_manage.preferences(cfg.get("_id") or name,
                                         expected_brain=cfg.get("_brain") or "")
        except Exception as e:
            r = {"ok": False, "error": "%s: %s" % (type(e).__name__, e)}
        cache[name] = r
    return cache[name]


def _yes(on):
    return _t("agentes.p.yes", "sí", "yes") if on else _t("agentes.p.no", "no", "no")


#: Averías de MOTOR (agent_state.ENGINE_STATUSES): el agente se abre igual y
#: aquí se le puede cambiar el motor sin salir de «necesitan arreglo».
_ENGINE_DOWN = ("engine_missing", "engine_unknown")


def options(S, cfg):
    """Las opciones del agente elegido, en orden: [(clave, etiqueta, valor)].
    Primero los AJUSTES (interruptores y motor), luego las ACCIONES (ruta,
    quitar). Un agente averiado empieza por «reparar» y no ofrece lo que no
    aplica. `valor` de un interruptor = True/False; de una acción = ""."""
    st = cfg.get("_state") or {}
    g = group_of(cfg)
    out = []
    if g == "fix":
        out.append(("repair", _t("agentes.o.repair", "reparar", "repair"),
                    _label(st.get("status", ""))))
        if st.get("status") in _ENGINE_DOWN:
            # solo le falta el motor: se le puede poner otro desde aquí
            out.append(("engine", _t("agentes.f.engine", "motor", "engine"),
                        cfg.get("engine") or "—"))
    else:
        out.append(("hub", _t("agentes.o.hub", "en el hub", "in the hub"),
                    not st.get("hidden")))
        out.append(("engine", _t("agentes.f.engine", "motor", "engine"),
                    cfg.get("engine") or "—"))
        pr = prefs_of(S, cfg)
        if pr.get("ok"):
            out.append(("perm", _t("agentes.o.perm", "su cerebro sin preguntar",
                                   "its brain without asking"),
                        pr.get("autonomy") == "brain"))
            out.append(("review", _t("agentes.o.review", "revisión de skills",
                                     "skill review"), bool(pr.get("skill_review"))))
    out.append(("brain", _t("agentes.o.brain", "cambiar la ruta del cerebro",
                            "change the brain's path"), ""))
    out.append(("remove", _t("agentes.o.remove", "quitar de esta máquina",
                             "remove from this machine"), ""))
    return out


_ACCIONES = ("brain", "remove")


def _short_path(p):
    home = os.path.expanduser("~")
    return ("~" + p[len(home):]) if p and p.startswith(home) else p


def _clip_left(p, w):
    """Ruta que no cabe → se recorta por la IZQUIERDA: el nombre de la
    carpeta (lo que la identifica) siempre queda a la vista."""
    if HL.vis(p) <= w:
        return p
    return "…" + p[-(max(1, w - 1)):]


def _mark(cfg):
    return {"hub": "●", "out": "○", "fix": "✗"}[group_of(cfg)]


def _en_agregar(S):
    """¿El cursor está en el renglón «+ agregar agente» (el último de la lista)?"""
    return bool(S.get("agents")) and S.get("index", 0) >= len(S["agents"])


def _chips(S):
    if S.get("input"):
        return (("Enter", _t("agentes.k.save", "guardar", "save")),
                ("Esc", _t("agentes.k.cancel", "cancelar", "cancel")))
    if S.get("focus") == "detail":
        return (("↑↓", _t("agentes.k.option", "opción", "option")),
                ("Enter", _t("agentes.k.change", "cambia", "change")),
                ("←", _t("agentes.k.to_list", "a la lista", "to the list")),
                ("i", _t("agentes.k.info", "cómo funciona", "how it works")))
    if _en_agregar(S):
        return (("↑↓", _t("agentes.k.pick", "elige", "pick")),
                ("Enter", _t("agentes.k.add", "agregar", "add")),
                ("i", _t("agentes.k.info", "cómo funciona", "how it works")),
                ("q", _t("agentes.k.back", "vuelve", "back")))
    return (("↑↓", _t("agentes.k.pick", "elige", "pick")),
            ("→", _t("agentes.k.to_opts", "a sus opciones", "to its options")),
            ("a", _t("agentes.k.add", "agregar", "add")),
            ("i", _t("agentes.k.info", "cómo funciona", "how it works")),
            ("q", _t("agentes.k.back", "vuelve", "back")))


def _list_w(S):
    noms = [c.get("display") or c["name"] for c in S.get("agents") or []]
    return max(16, min(24, max([HL.vis(n) for n in noms] + [10]) + 6))


def box_w(S):
    return max(_list_w(S), DETAIL_W)


def _detalle(S, K, cfg, iw):
    """La parte de abajo: SOLO las opciones del agente (nombre, estado y
    ruta viven en el cuadro de i). Ajustes con su interruptor o valor; una
    regla tenue; acciones con «›». Devuelve (líneas, fila del cursor)."""
    if S.get("input"):
        out = [HL.clip("%s%s%s" % (K["C"] + K["BO"], _t("agentes.input.path2",
                                                         "Nueva ruta del cerebro:",
                                                         "New brain path:"), K["R"]), iw),
               HL.clip("%s%s▏%s" % (K["WH"] + K["BO"], S["input"]["buf"], K["R"]), iw),
               "",
               HL.clip("%s%s%s" % (K["DIM"], _t("agentes.input.help2",
                                                "pega la carpeta del cerebro",
                                                "paste the brain folder"), K["R"]), iw)]
        return out, 1
    activo = S.get("focus") == "detail"
    ops = options(S, cfg)
    S["opt"] = max(0, min(S.get("opt", 0), len(ops) - 1))
    lab_w = max(HL.vis(o[1]) for o in ops if o[0] not in _ACCIONES) + 2
    out, fila = [], 0
    for n, (key, lab, val) in enumerate(ops):
        if key in _ACCIONES and (n == 0 or ops[n - 1][0] not in _ACCIONES):
            out.append("  %s%s%s" % (K["DK"], K["SEP"] * max(1, iw - 2), K["R"]))
        on = activo and n == S["opt"]
        if on:
            fila = len(out)
        cur = ("%s%s %s" % (K["C"] + K["BO"], K["PTR"], K["R"])) if on else "  "
        if key == "remove" and S.get("confirm") == cfg["name"]:
            lab = _t("agentes.o.remove_confirm", "Enter otra vez quita · nada se borra",
                     "Enter again removes · nothing is deleted")
            out.append(HL.clip("%s%s%s%s%s" % (cur, K["ERR"] + K["BO"], lab, K["R"], ""), iw))
            continue
        tinta = (K["WH"] + K["BO"]) if on else (K["ERR"] if key == "repair" else K["GREY"])
        if key in _ACCIONES:
            flecha = "%s›%s" % ((K["C"] + K["BO"]) if on else K["DK"], K["R"])
            hueco = max(1, iw - 2 - HL.vis(lab) - 1)
            out.append(HL.clip("%s%s%s%s%s%s" % (cur, tinta, lab, K["R"], " " * hueco, flecha), iw))
            continue
        if isinstance(val, bool):
            valor = "%s %s%s%s" % (SB.switch(K, val), K["OK"] if val else K["DIM"],
                                    _yes(val), K["R"])
        elif key == "engine":
            valor = "%s%s%s" % ((K["C"] + K["BO"]) if on else K["B2"], val, K["R"])
            if on:
                valor += "%s  Enter cambia%s" % (K["DK"], K["R"]) if HL.vis(val) + 14 < iw - 2 - lab_w else ""
        else:
            valor = "%s%s%s" % (K["ERR"], val, K["R"])
        out.append(HL.clip("%s%s%s%s%s" % (cur, tinta, HL.pad(lab, lab_w), K["R"], valor), iw))
    return out, fila


#: Filas visibles de la lista de agentes (más → se desplaza con «▲/▼ n más»).
LIST_ROWS = 8


def _cuerpo(S, K, iw):
    """VERTICAL: tus agentes arriba (la flecha al final del elegido: ▸ → abre
    sus opciones · ◂ ← regresa) y, bajo una regla con su nombre, sus opciones."""
    abajo = S.get("focus") == "detail" or bool(S.get("input"))
    items = [(c.get("display") or c["name"], _mark(c)) for c in S["agents"]]
    # al final, SIEMPRE, el renglón para agregar uno (crear o cargar)
    items.append(("+ " + _t("agentes.add_row", "agregar agente", "add agent"), "", "", "B2"))
    arriba = SB.pick_list(K, items, S["index"], iw, min(len(items), LIST_ROWS),
                          sel_tail="◂" if abajo else "▸")
    if _en_agregar(S):
        S["_cur"] = next((i for i, ln in enumerate(arriba)
                          if SB._ANSI.sub("", ln).startswith("› ")), 0)
        abajo_txt = [
            "  %s%s%s" % (K["GREY"], _t("agentes.add_hint",
                                        "crea uno nuevo o carga uno que ya tienes",
                                        "create a new one or load one you already have"), K["R"]),
            "  %s▸ %s%s" % (K["B2"], _t("agentes.add_enter", "Enter para empezar",
                                         "Enter to start"), K["R"])]
        return SB.stack(K, arriba, [HL.clip(x, iw) for x in abajo_txt], iw,
                        label=_t("agentes.add_row", "agregar agente", "add agent"))
    cfg = S["agents"][S["index"]]
    opciones, _fila = _detalle(S, K, cfg, iw)
    etiqueta = "%s · %s" % (cfg.get("display") or cfg["name"],
                            _t("agentes.opts", "opciones", "options"))
    # en terminales bajas la caja se desplaza: que siga a la opción elegida
    S["_cur"] = len(arriba) + 2 + _fila if abajo else next(
        (i for i, ln in enumerate(arriba) if SB._ANSI.sub("", ln).startswith("› ")), 0)
    return SB.stack(K, arriba, opciones, iw, label=etiqueta, active=abajo)


def info_blocks(S, K):
    """El cuadro de i: primero el agente ELEGIDO (estado, motor y dónde vive
    su cerebro), luego qué es un agente y qué hace cada opción."""
    sel = []
    cfg = _selected(S)
    if cfg:
        ruta = _short_path(cfg.get("_brain") or "—")
        filas = [(_t("agentes.f.status", "estado", "status"), status_line(cfg), False),
                 (_t("agentes.f.engine", "motor", "engine"), cfg.get("engine") or "—", False),
                 (_t("agentes.f.brain", "cerebro", "brain"), ruta, True)]
        kw = max(HL.vis(e) for e, _v, _r in filas) + 2

        def _datos(iw):
            out = []
            for etq, val, es_ruta in filas:
                ancho = max(8, iw - kw)
                # la ruta se recorta por la IZQUIERDA: la carpeta siempre se ve
                partes = [_clip_left(val, ancho)] if es_ruta else SB._wrap(val, ancho)[:2]
                for n, parte in enumerate(partes):
                    out.append("%s%s%s%s%s%s" % (K["C"] + K["BO"], HL.pad(etq if n == 0 else "", kw),
                                                 K["R"], K["GREY"], parte, K["R"]))
            return out
        sel = [("h", cfg.get("display") or cfg["name"]), ("lines", _datos)]
        sel.append(("gap",))
    return sel + [
        ("flow", [(_t("agentes.info.n1", "su cerebro", "its brain"),
                   _t("agentes.info.c1", "tu carpeta: memoria y skills",
                      "your folder: memory and skills")),
                  (_t("agentes.info.n2", "un motor", "an engine"),
                   _t("agentes.info.c2", "uno de seis: Claude Code, Codex…",
                      "one of six: Claude Code, Codex…")),
                  (_t("agentes.info.n3", "tu agente", "your agent"),
                   _t("agentes.info.c3", "con tu propia cuenta", "with your own account"))]),
        ("gap",),
        ("p", _t("agentes.info.p1",
                 "Un agente es su cerebro (una carpeta de archivos tuya, fuera de "
                 "Workspace) trabajando en un motor. Cambiar el motor no cambia quién "
                 "es ni lo que sabe: cada pestaña guarda su memoria en el cerebro y "
                 "cualquier motor la recibe igual al abrir.",
                 "An agent is its brain (a folder of your own files, outside Workspace) "
                 "working in an engine. Changing the engine doesn't change who it is or "
                 "what it knows: each tab keeps its memory in the brain and every engine "
                 "gets it the same way when it opens.")),
        ("h", _t("agentes.info.h_opts", "sus opciones", "its options")),
        ("kv", [(_t("agentes.o.hub", "en el hub", "in the hub"),
                 _t("agentes.info.o_hub", "si aparece en el hub; quitarlo no borra nada",
                    "whether it shows in the hub; hiding it deletes nothing")),
                (_t("agentes.f.engine", "motor", "engine"),
                 _t("agentes.info.o_engine", "con qué programa corre",
                    "which program runs it")),
                (_t("agentes.o.brain", "cambiar la ruta del cerebro", "change the brain's path"),
                 _t("agentes.info.o_brain", "si moviste su carpeta, aquí la apuntas de nuevo",
                    "if you moved its folder, point to it again here")),
                (_t("agentes.o.perm", "su cerebro sin preguntar", "its brain without asking"),
                 _t("agentes.info.o_perm", "lee y escribe ahí sin pedirte permiso",
                    "reads and writes there without asking you")),
                (_t("agentes.o.review", "revisión de skills", "skill review"),
                 _t("agentes.info.o_review",
                    "al abrir cada sesión revisa la anterior y mejora sus skills, a la vista; "
                    "usa un poco de tu suscripción",
                    "when each session opens it reviews the previous one and improves its "
                    "skills, in plain sight; uses a little of your subscription")),
                (_t("agentes.o.remove", "quitar de esta máquina", "remove from this machine"),
                 _t("agentes.info.o_remove", "su cerebro y sesiones se quedan en disco",
                    "its brain and sessions stay on disk"))]),
        ("gap",),
        ("dim", _t("agentes.info.marks",
                   "● en el hub · ○ fuera del hub · ✗ necesita arreglo · «+ agregar agente» "
                   "(al final de la lista, o la tecla a) crea o carga uno",
                   "● in the hub · ○ not in the hub · ✗ needs fixing · «+ add agent» "
                   "(at the end of the list, or the a key) creates or loads one")),
    ]


def render(S, w, h):
    K = _K()
    if S.get("info"):
        return SB.info_frame(K, w, h, word(), _t("agentes.info.title",
                                                  "CÓMO FUNCIONAN TUS AGENTES",
                                                  "HOW YOUR AGENTS WORK"),
                             info_blocks(S, K), state=S["info"], box_w=66)
    titulo = _t("agentes.box.title", "AGENTES", "AGENTS")
    if not S.get("agents"):
        vacio = [_t("agentes.empty2", "Aún no tienes agentes. a crea o carga uno.",
                    "No agents yet. a creates or loads one.")]
        return SB.frame(K, w, h, word(), titulo, vacio, _chips(S), msg=S.get("msg", ""),
                        box_w=48)
    S["index"] = max(0, min(S["index"], len(S["agents"])))      # el último = «+ agregar»
    return SB.frame(K, w, h, word(), titulo, lambda iw: _cuerpo(S, K, iw), _chips(S),
                    msg=S.get("msg", ""), cursor_line=lambda: S.get("_cur", 0), box_w=box_w(S),
                    stable_rows=min(len(S["agents"]) + 1, LIST_ROWS) + 2 + 7)


# ── acciones ─────────────────────────────────────────────────────────────────
def _selected(S):
    if not S.get("agents") or _en_agregar(S):
        return None
    return S["agents"][S["index"]]


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
                           _t("agentes.m.out2", "{n} fuera del hub · Enter lo regresa",
                              "{n} removed from the hub · Enter brings it back", n=name))


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


def _change(S):
    """Enter sobre la opción elegida."""
    cfg = _selected(S)
    ops = options(S, cfg)
    key = ops[max(0, min(S.get("opt", 0), len(ops) - 1))][0]
    if key != "remove":
        S.pop("confirm", None)
    if key == "hub":
        _toggle_hub(S)
    elif key == "engine":
        _manage(S, "cycle_engine")
    elif key == "brain":
        S["input"] = {"kind": "path", "buf": ""}
    elif key == "repair":
        _repair(S)
    elif key == "perm":
        on = prefs_of(S, cfg).get("autonomy") == "brain"
        _manage(S, "set_autonomy", "ask" if on else "brain")
    elif key == "review":
        _manage(S, "set_skill_review", not prefs_of(S, cfg).get("skill_review"))
    elif key == "remove":
        if S.get("confirm") == cfg["name"]:
            S.pop("confirm", None)
            if _manage(S, "unregister"):
                S["focus"] = "list"
        else:
            S["confirm"] = cfg["name"]
    S.pop("_prefs", None)


def act(S, key):
    """True = sigue · False = vuelve al hub (o pide agregar)."""
    if S.get("input"):
        return _input_key(S, key)
    if SB.info_key(S, key):
        return True
    if key == "\x03":
        return False
    if key == "a":
        S["request"] = "add"
        return False
    if not S.get("agents"):
        return key not in ("q", "Q", "\x1b")
    S["msg"] = ""
    if S.get("focus") == "detail":
        n = len(options(S, _selected(S)))
        if key in ("\x1b", "left", "q", "Q"):
            S["focus"] = "list"
            S.pop("confirm", None)
        elif key in ("up", "down"):
            S["opt"] = (S.get("opt", 0) + (-1 if key == "up" else 1)) % n
            S.pop("confirm", None)
        elif key in ("\r", "\n", " "):
            _change(S)
        return True
    if key in ("q", "Q", "\x1b"):
        return False
    n = len(S["agents"]) + 1                     # + el renglón «+ agregar agente»
    if key in ("up", "down", "tab"):
        S["index"] = (S["index"] + (-1 if key == "up" else 1)) % n
        S["opt"] = 0
    elif key in ("\r", "\n", "right", " ") and _en_agregar(S):
        S["request"] = "add"
        return False
    elif key in ("\r", "\n", "right", " "):
        S["focus"] = "detail"
        S["opt"] = 0
    return True


# ── loop ─────────────────────────────────────────────────────────────────────
def _open_add(S):
    """Agregar agente (crear o cargar) y volver a Agentes con la lista al día
    y el cursor sobre el agente nuevo (si se creó o cargó uno)."""
    antes = {c.get("name") for c in S.get("agents") or []}
    try:
        import add_agent_tui
        add_agent_tui.run()
    except Exception as e:
        S["msg"] = _t("agentes.add_unavail",
                      "agregar agente no disponible ({e})",
                      "add agent unavailable ({e})", e=type(e).__name__)
    reload_if_changed(S, force=True)
    nuevos = [n for n, c in enumerate(S.get("agents") or []) if c.get("name") not in antes]
    if nuevos:
        S["index"], S["focus"] = nuevos[0], "list"


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
    if not S.get("agents"):
        S["request"] = "add"                 # sin agentes: directo a agregar
    while True:
        if S.get("request") == "add":
            S.pop("request", None)
            _open_add(S)
            if not S.get("agents"):
                return None                  # canceló sin crear nada: al hub
            continue
        if os.name == "nt":
            _loop_windows(S)
        else:
            _loop_unix(S)
        if S.get("request") != "add":
            return None


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
