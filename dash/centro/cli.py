#!/usr/bin/env python3
"""WORKSPACE · dash.centro.cli — `workspace centro`: la terminal del Centro de Control.

Agent-first y token-eficiente: los agentes (y el front, y el socio en una terminal)
leen y mutan el MISMO backend (dash.centro.*) sin server ni HTTP. Toda salida
tiene forma `--json` ESTABLE (el contrato para scripts/front) y una forma
humana compacta.

    LECTURA
      workspace centro status   [--json]            snapshot agregado de agentes
      workspace centro board    [--json] [--archived] [--fase F] [--agente A]
      workspace centro ver <id> [--json]            una misión (con historial)

    MUTACIÓN SEGURA
      workspace centro nueva --titulo T --agente A [--proyecto P] [--rama R]
                           [--modelo heredar|rapido|profundo] [--done "criterio"]…
                           [--fase plan|exec] [--por QUIEN] [--json]
      workspace centro fase <id> <plan|exec|review|done> --por QUIEN [--json]
      workspace centro progreso <id> <pct> [--por QUIEN] [--json]
      workspace centro delegar <id> --por QUIEN [--idea "…"] [--approval] [--json]
      workspace centro delegar --titulo T --agente A --por QUIEN […]   (crea+delega)
      workspace centro archivar <id> / restaurar <id>  [--por QUIEN]

La máquina de fases y sus reglas viven en dash.centro.tareas (una sola fuente);
aquí solo se parsean argumentos y se imprime. Exit: 0 ok · 1 rechazo/error ·
2 uso inválido.
"""
import json
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from dash.centro import delegar as _delegar          # noqa: E402
from dash.centro import estado as _estado            # noqa: E402
from dash.centro import tareas as _tareas            # noqa: E402

PHASE_GLYPH = {"plan": "◇", "exec": "◐", "review": "▣", "done": "●"}


def _flags(rest, valued=(), bools=(), multi=()):
    """Parser mínimo (mismo estilo que front._board_flags): (pos, opts, err).
    `multi` = flags con valor repetibles (acumulan lista)."""
    pos, opts = [], {}
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in bools:
            opts[a.lstrip("-")] = True
            i += 1
        elif a in multi:
            if i + 1 >= len(rest):
                return None, None, "falta el valor de %s" % a
            opts.setdefault(a.lstrip("-"), []).append(rest[i + 1])
            i += 2
        elif a in valued:
            if i + 1 >= len(rest):
                return None, None, "falta el valor de %s" % a
            opts[a.lstrip("-")] = rest[i + 1]
            i += 2
        elif a.startswith("--") and "=" in a:
            k, v = a[2:].split("=", 1)
            if "--" + k in multi:
                opts.setdefault(k, []).append(v)
            else:
                opts[k] = v
            i += 1
        else:
            pos.append(a)
            i += 1
    return pos, opts, None


def _out(obj):
    print(json.dumps(obj, ensure_ascii=False, indent=2))
    return 0 if obj.get("ok", True) else 1


def _err(msg):
    print("✗ %s" % msg, file=sys.stderr)
    return 1


def _mission_line(m):
    g = PHASE_GLYPH.get(m["phase"], "·")
    pct = (" %3d%%" % m["progress"]) if m["phase"] == "exec" else ""
    extra = " [archivada]" if m.get("archived") else ""
    return "%s %-7s %-8s %s%s · %s%s" % (g, m["phase"], m["agent"] or "?",
                                         m["id"], pct, m["title"], extra)


# ── subcomandos ──────────────────────────────────────────────────────────────
def _cmd_status(rest):
    pos, opts, err = _flags(rest, bools=("--json",))
    if err:
        return _err(err)
    snap = _estado.snapshot()
    if opts.get("json"):
        return _out(snap)
    c = snap.get("cuenta")
    if c:
        stale = " (viejo)" if c.get("stale") else ""
        print("cuenta  · energía %.0f%% (5h usado %.0f%%)%s · contexto última sesión %s%%"
              % (c["energia_pct"], c["five_hour_pct"], stale,
                 c.get("context_pct") if c.get("context_pct") is not None else "?"))
    else:
        print("cuenta  · sin dato (usage.json ausente — la statusline lo stampea)")
    lat = snap.get("latido")
    if lat:
        q = " · silencio AHORA" if lat.get("quiet") else ""
        print("latido  · modo %s · tope %s%%%s" % (lat.get("mode"),
                                                   lat.get("budget", {}).get("cap"), q))
    tb = snap.get("taskboard")
    if tb:
        print("misiones· plan %d · exec %d · review %d · done %d"
              % (tb.get("plan", 0), tb.get("exec", 0),
                 tb.get("review", 0), tb.get("done", 0)))
    for a in snap.get("agentes", []):
        now = a.get("now")
        task = ("%s %s" % (now["state"], now["task"])) if now else "—"
        inbox = a.get("inbox_pending")
        wt = len(a.get("worktrees") or [])
        print("  %-8s %s · inbox %s · worktrees %d"
              % (a["name"], task[:60], "?" if inbox is None else inbox, wt))
    for w in snap.get("warns", []):
        print("  %s" % w)
    return 0


def _cmd_board(rest):
    pos, opts, err = _flags(rest, valued=("--fase", "--agente"),
                            bools=("--json", "--archived"))
    if err:
        return _err(err)
    ms = _tareas.list_missions(include_archived=bool(opts.get("archived")),
                               phase=opts.get("fase"), agent=opts.get("agente"))
    if opts.get("json"):
        return _out({"ok": True, "missions": ms})
    if not ms:
        print("taskboard: sin misiones (crea una: workspace centro nueva "
              "--titulo \"…\" --agente <a>)")
        return 0
    for m in ms:
        print(_mission_line(m))
    return 0


def _cmd_ver(rest):
    pos, opts, err = _flags(rest, bools=("--json",))
    if err or not pos:
        return _err(err or "falta el id de la misión")
    m = _tareas.get_mission(pos[0])
    if m is None:
        return _err("misión desconocida: %s" % pos[0])
    if opts.get("json"):
        return _out({"ok": True, "mission": m})
    print(_mission_line(m))
    if m.get("project"):
        print("  proyecto: %s" % m["project"])
    if m.get("branch"):
        print("  rama:     %s" % m["branch"])
    print("  modelo:   %s" % m["model"])
    for c in m.get("done_cuando", []):
        print("  done si:  %s" % c)
    for i in m.get("msg_ids", []):
        print("  msg:      %s" % i)
    for h in m.get("history", []):
        print("  %s  %s (%s)" % (h.get("t", "?"), h.get("ev", "?"), h.get("by", "?")))
    return 0


def _mk_kwargs(opts):
    return dict(project=opts.get("proyecto", ""), branch=opts.get("rama", ""),
                model=opts.get("modelo", "heredar"),
                idea_ref=opts.get("idea-ref"),
                done_cuando=opts.get("done") or [],
                phase=opts.get("fase", "plan"))


_NUEVA_VALUED = ("--titulo", "--agente", "--proyecto", "--rama", "--modelo",
                 "--fase", "--por", "--idea", "--idea-ref")


def _cmd_nueva(rest):
    pos, opts, err = _flags(rest, valued=_NUEVA_VALUED, bools=("--json",),
                            multi=("--done",))
    if err:
        return _err(err)
    if not opts.get("titulo") or not opts.get("agente"):
        return _err("uso: workspace centro nueva --titulo \"…\" --agente <a> "
                    "[--proyecto P --rama R --modelo M --done \"criterio\" --fase plan|exec]")
    res = _tareas.create(opts["titulo"], opts["agente"],
                         by=opts.get("por", ""), **_mk_kwargs(opts))
    if opts.get("json"):
        return _out(res)
    if not res.get("ok"):
        return _err(res.get("error", "?"))
    print("misión creada: %s (fase %s)" % (res["id"], opts.get("fase", "plan")))
    return 0


def _cmd_fase(rest):
    pos, opts, err = _flags(rest, valued=("--por",), bools=("--json",))
    if err or len(pos) < 2:
        return _err(err or "uso: workspace centro fase <id> <plan|exec|review|done> --por <quien>")
    res = _tareas.transition(pos[0], pos[1], opts.get("por", ""))
    if opts.get("json"):
        return _out(res)
    if not res.get("ok"):
        return _err(res.get("error", "?"))
    print("misión %s → fase %s" % (pos[0], res["phase"]))
    return 0


def _cmd_progreso(rest):
    pos, opts, err = _flags(rest, valued=("--por",), bools=("--json",))
    if err or len(pos) < 2:
        return _err(err or "uso: workspace centro progreso <id> <0-100> [--por <quien>]")
    try:
        pct = int(pos[1])
    except ValueError:
        return _err("progreso inválido (entero 0-100)")
    res = _tareas.set_progress(pos[0], pct, by=opts.get("por", ""))
    if opts.get("json"):
        return _out(res)
    if not res.get("ok"):
        return _err(res.get("error", "?"))
    print("misión %s → %d%%" % (pos[0], pct))
    return 0


def _cmd_delegar(rest):
    pos, opts, err = _flags(rest, valued=_NUEVA_VALUED, bools=("--json", "--approval"),
                            multi=("--done",))
    if err:
        return _err(err)
    by = opts.get("por", "")
    if not by:
        return _err("falta --por <quien> (quién delega)")
    if pos:                                   # misión existente
        res = _delegar.delegar(pos[0], by, idea=opts.get("idea", ""),
                               requires_approval=bool(opts.get("approval")))
    elif opts.get("titulo") and opts.get("agente"):   # crear + delegar
        res = _delegar.delegar_nueva(opts["titulo"], opts["agente"], by,
                                     idea=opts.get("idea", ""),
                                     requires_approval=bool(opts.get("approval")),
                                     **_mk_kwargs(opts))
    else:
        return _err("uso: workspace centro delegar <id> --por <quien>  |  "
                    "workspace centro delegar --titulo \"…\" --agente <a> --por <quien>")
    if opts.get("json"):
        return _out(res)
    if not res.get("ok"):
        return _err(res.get("error", "?"))
    print("encargo enviado: %s" % ", ".join(res.get("msg_ids", [])))
    return 0


def _cmd_archivar(rest):
    pos, opts, err = _flags(rest, valued=("--por",), bools=("--json",))
    if err or not pos:
        return _err(err or "falta el id de la misión")
    res = _tareas.archive(pos[0], by=opts.get("por", ""))
    if opts.get("json"):
        return _out(res)
    if not res.get("ok"):
        return _err(res.get("error", "?"))
    print("misión %s archivada" % pos[0])
    return 0


def _cmd_restaurar(rest):
    pos, opts, err = _flags(rest, valued=("--por",), bools=("--json",))
    if err or not pos:
        return _err(err or "falta el id de la misión")
    res = _tareas.restore(pos[0], by=opts.get("por", ""))
    if opts.get("json"):
        return _out(res)
    if not res.get("ok"):
        return _err(res.get("error", "?"))
    print("misión %s restaurada" % pos[0])
    return 0


def _help():
    print(__doc__.strip().split("\n\n", 1)[1]
          if "\n\n" in (__doc__ or "") else (__doc__ or ""))


HANDLERS = {
    "status": _cmd_status, "estado": _cmd_status,
    "board": _cmd_board, "list": _cmd_board, "ls": _cmd_board,
    "ver": _cmd_ver, "show": _cmd_ver,
    "nueva": _cmd_nueva, "new": _cmd_nueva,
    "fase": _cmd_fase,
    "progreso": _cmd_progreso, "progress": _cmd_progreso,
    "delegar": _cmd_delegar,
    "archivar": _cmd_archivar,
    "restaurar": _cmd_restaurar,
}


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        _help()
        return 0 if args else 2
    sub, rest = args[0], args[1:]
    h = HANDLERS.get(sub)
    if h is None:
        print("✗ subcomando desconocido: %s" % sub, file=sys.stderr)
        _help()
        return 2
    try:
        return h(rest)
    except Exception as e:
        print("✗ workspace centro %s: %s: %s" % (sub, type(e).__name__, e),
              file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
