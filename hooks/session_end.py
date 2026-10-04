#!/usr/bin/env python3
"""WORKSPACE hook · SessionEnd — red de seguridad de captura.

Al cerrar una sesión: si la memoria de sesión NO se actualizó después del marcador
de inicio (`session_start.py`), escribe una breadcrumb automática a su `## Historial`
para no perder el rastro. Si el agente YA hizo su narrativa a mano, no hace nada.

Cleanup-only: Claude Code ignora la salida de SessionEnd (no puede bloquear ni
invocar al modelo). Opera sobre el cerebro (cwd) y su convención STATE/sessions.
Best-effort: un cierre por SIGKILL puede no dispararlo. Cero dependencias (3.9+).
"""
import sys, os, json, glob, datetime, subprocess, unicodedata, re

try:   # M1/B2 · Windows: UTF-8 en stdout/err — un hook capturado por Claude Code en
       # cp1252 reventaría al imprimir caracteres no-ASCII. No-op en Mac (UTF-8 default).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# No actuamos en transiciones de media sesión (evita falsos positivos por orden de
# disparo). Solo en cierres reales: logout, prompt_input_exit, exit, other, ...
SKIP_REASONS = {"clear", "resume"}


def _stdin():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def _marker_path(sid):
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace", "markers",
                        (sid or "unknown") + ".json")


def _slug(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _socio(brain):
    try:
        return open(os.path.join(brain, ".claude", "socio.local"),
                    encoding="utf-8").read().strip().lower()
    except Exception:
        return ""


def _git_changes(brain):
    try:
        r = subprocess.run(["git", "-C", brain, "status", "--porcelain"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=5)
        return [ln for ln in r.stdout.splitlines() if ln.strip()]
    except Exception:
        return []


def _touch_workspace_updated(brain, sid):
    """Y10 · 3 timestamps: estampa `updated` (escritura de bookkeeping, hooks
    incluidos) en la pestaña cuyo id == session_id, en .claude/*-workspaces.json.

    NUNCA toca `last_opened` (esa es SOLO interacción humana, la estampa el
    picker) ni `created`. El picker ordena por last_opened, así que este write
    no contamina el orden — `updated` es auditoría. Best-effort, atómico.
    El session_id ES el workspace id (el motor lanza con --session-id/--resume
    <wid>); si la sesión no nació de una pestaña, no matchea y no pasa nada.
    Único hook que escribe este JSON al cierre (evita writes concurrentes con
    skill_review/transcript_backup)."""
    try:
        for wf in glob.glob(os.path.join(brain, ".claude", "*-workspaces.json")):
            try:
                ws = json.load(open(wf, encoding="utf-8"))
            except Exception:
                continue
            hit = False
            for w in ws:
                if isinstance(w, dict) and w.get("id") == sid:
                    w["updated"] = datetime.datetime.now().isoformat(timespec="seconds")
                    hit = True
                    break
            if hit:
                tmp = wf + ".tmp"
                with open(tmp, "w", encoding="utf-8") as f:
                    json.dump(ws, f, indent=2, ensure_ascii=False)
                os.replace(tmp, wf)
                return
    except Exception:
        pass


def _atomic_write(path, text):
    """tmp + os.replace (F1): si el proceso muere escribiendo, el archivo de
    sesión nunca queda truncado a medias. Atómico dentro del mismo dir."""
    tmp = "%s.tmp%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.replace(tmp, path)


def _wt_log(agent, reason, res):
    """Bitácora per-máquina de la auto-limpieza de worktrees. El hook SessionEnd
    no tiene canal de salida visible (Claude Code ignora su stdout), así que el
    rastro de QUÉ se liberó (y qué se dejó por estar sucio) queda aquí para
    auditoría. Best-effort; jamás rompe."""
    try:
        d = os.path.join(os.path.expanduser("~"), ".claude", "workspace", "logs")
        os.makedirs(d, exist_ok=True)
        line = ("%s  agent=%s reason=%s removed=%s pooled=%s skipped_dirty=%s "
                "stale=%s failed=%s\n") % (
            datetime.datetime.now().isoformat(timespec="seconds"),
            agent, reason or "?", res.get("removed"), res.get("pooled"),
            res.get("skipped_dirty"), res.get("stale"), res.get("failed"))
        with open(os.path.join(d, "worktrees.log"), "a", encoding="utf-8") as fh:
            fh.write(line)
    except Exception:
        pass


def _release_worktrees(reason):
    """Auto-libera los worktrees LIMPIOS del agente que cierra esta sesión, para
    que su rama quede libre. Un worktree olvidado FIJA la rama (`git switch` da
    "already used by worktree") y bloquea al desarrollador para entrar a revisar.

    Estructural: corre en CADA cierre real de CUALQUIER agente lanzado por el
    harness — sabemos QUIÉN cierra por WORKSPACE_AGENT_NAME (lo exporta dispatch.py).
    Sin esa var (sesión no nacida del harness, o agente desconocido) no tocamos
    nada: la auto-limpieza es solo para agentes del harness. NUNCA remueve un
    worktree con cambios sin commitear (lo garantiza _worktrees.release). Los
    worktrees del POOL tibio no se destruyen: release() los devuelve al pool
    (lease liberado, ignorados intactos) — aquí solo queda el rastro en el log.
    Falla-suave TOTAL: jamás rompe el cierre (regla 6)."""
    agent = os.environ.get("WORKSPACE_AGENT_NAME", "").strip()
    if not agent:
        return
    try:
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from dash.dev import _worktrees
        res = _worktrees.release(agent=agent)
    except Exception:
        return
    if (res.get("removed") or res.get("pooled") or res.get("skipped_dirty")
            or res.get("stale")):
        _wt_log(agent, reason, res)


def _append_breadcrumb(memfile, line):
    with open(memfile, encoding="utf-8") as fh:
        txt = fh.read()
    lines = txt.splitlines()
    hidx = next((i for i, l in enumerate(lines) if l.strip().startswith("## Historial")), None)
    if hidx is None:
        lines += ["", "## Historial", line]
    else:
        nxt = next((j for j in range(hidx + 1, len(lines)) if lines[j].startswith("## ")), len(lines))
        at = nxt
        while at - 1 > hidx and lines[at - 1].strip() == "":
            at -= 1
        lines.insert(at, line)
    _atomic_write(memfile, "\n".join(lines) + "\n")


def main():
    data = _stdin()
    sid = data.get("session_id", "")
    brain = data.get("cwd", "") or os.getcwd()
    reason = data.get("reason", "")

    mp = _marker_path(sid)
    marker = {}
    if os.path.exists(mp):
        try:
            marker = json.load(open(mp, encoding="utf-8"))
        except Exception:
            marker = {}

    def cleanup():
        try:
            os.remove(mp)
        except Exception:
            pass

    if reason in SKIP_REASONS:
        return  # transición, no cierre real; deja el marcador para el cierre verdadero

    # Cierre real → libera los worktrees LIMPIOS de ESTE agente (la rama queda
    # libre para entrar a revisarla). Estructural, automático, falla-suave.
    _release_worktrees(reason)

    # Y10: cierre real → bookkeeping del hook estampa `updated` en la pestaña
    # (jamás `last_opened`, que es solo-humano y la escribe el picker).
    _touch_workspace_updated(brain, sid)

    # WORKSPACE_WS = genérico (cualquier agente); ZENITH_WS = back-compat.
    ws = (os.environ.get("WORKSPACE_WS", "") or os.environ.get("ZENITH_WS", "")
          or marker.get("ws", ""))
    started = marker.get("started")
    soc = _socio(brain)

    # Sin pestaña, sin socio, o sin marcador (sesión previa al hook) → no arriesgar ruido.
    if not ws or not soc or started is None:
        cleanup(); return

    memfile = os.path.join(brain, "STATE", "sessions", soc, _slug(ws) + ".md")
    if not os.path.exists(memfile):
        cleanup(); return  # no auto-creamos archivos estructurados curados

    # ¿Se actualizó la memoria DESPUÉS del inicio de esta sesión? → narrativa hecha.
    try:
        if os.path.getmtime(memfile) >= float(started):
            cleanup(); return
    except Exception:
        cleanup(); return

    # Me olvidé → breadcrumb mecánica.
    changes = _git_changes(brain)
    n = len(changes)
    sample = ", ".join(c[3:] for c in changes[:5])
    extra = f" ({sample}{'…' if n > 5 else ''})" if sample else ""
    line = ("- " + datetime.date.today().isoformat() + " (cierre auto) — sesión cerrada"
            + (f" [{reason}]" if reason else "") + " sin captura manual. "
            + (f"{n} archivo(s) del cerebro con cambios sin commit{extra}." if n
               else "Sin cambios sin commit.")
            + " Revisar para consolidar.")
    try:
        _append_breadcrumb(memfile, line)
    except Exception:
        pass
    cleanup()


if __name__ == "__main__":
    main()
