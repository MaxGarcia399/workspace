#!/usr/bin/env python3
"""WORKSPACE hook · SessionEnd — limpieza del cierre.

Al cerrar una sesión: libera los worktrees LIMPIOS del agente, estampa
`updated` en la pestaña (.claude/*-workspaces.json) y borra el marcador de
inicio (`session_start.py`).

Memoria v1 (2026-10-17): ya NO escribe la nota «(cierre auto) — sesión cerrada
sin captura manual»: era ruido (75 en una sola ficha, 4 de cada 12 líneas
inyectadas; Panorama, hallazgo 13). Lo que pasó en la sesión lo guarda el
agente con `workspace memoria nota` y, sin IA, `memoria_cierre.py` arma la
maleta de la pestaña con el extracto de la conversación.

Cleanup-only: Claude Code ignora la salida de SessionEnd (no puede bloquear ni
invocar al modelo). Best-effort: un cierre por SIGKILL puede no dispararlo.
Cero dependencias (3.9+).
"""
import sys, os, json, glob, datetime

try:   # M1/B2 · Windows: UTF-8 en stdout/err — un hook capturado por Claude Code en
       # cp1252 reventaría al imprimir caracteres no-ASCII. No-op en Mac (UTF-8 default).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# No actuamos en transiciones de media sesión (evita falsos positivos por orden de
# disparo). Solo en cierres reales: logout, prompt_input_exit, exit, other, ...
SKIP_REASONS = {"clear", "resume"}

#: Raíz del harness (padre de hooks/).
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _dev_worktrees_path():
    """Ruta de dash/dev/_worktrees.py: solo existe en la build de desarrollo
    (make-dist.sh quita dash/dev/ de la del cliente)."""
    return os.path.join(_ROOT, "dash", "dev", "_worktrees.py")


def _stdin():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def _state_dir():
    """Dir de estado per-máquina vía el resolver único (`paths.py`, en la raíz
    de WORKSPACE = padre de hooks/). append (no insert) para no alterar qué
    módulo homónimo de hooks/ gana en sys.path."""
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.append(_root)
    import paths
    return paths.state_dir()


def _marker_path(sid):
    return os.path.join(_state_dir(), "markers",
                        (sid or "unknown") + ".json")


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
        d = os.path.join(_state_dir(), "logs")
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
    """Auto-libera los worktrees LIMPIOS de la SESIÓN que cierra, para que su
    rama quede libre. Un worktree olvidado FIJA la rama (`git switch` da
    "already used by worktree") y bloquea al desarrollador para entrar a revisar.

    Estructural: corre en CADA cierre real de CUALQUIER agente lanzado por el
    harness — sabemos QUIÉN cierra por WORKSPACE_AGENT_NAME y QUÉ sesión por
    WORKSPACE_SESSION_ID/_PID (los exporta dispatch.py; `workspace worktree`
    los guarda como dueños del árbol). POR SESIÓN, no por agente: otra pestaña
    viva del mismo agente puede estar trabajando en SU worktree, y soltárselo
    la deja en HEAD suelto (sus commits siguientes no quedan en la rama y el
    pool puede reciclarle la carpeta). Suelta además los HUÉRFANOS del agente:
    su proceso dueño murió sin cerrar (cierre abrupto) y su pestaña no los
    retomó al relanzarse (eso lo hace session_start.py) — la auto-limpieza de
    siempre, sin tocar jamás una sesión viva. El pid de ESTA sesión no se exige
    vivo: en Windows, cerrar la consola mata primero al python del launcher. No
    se toca nada:
      · sin WORKSPACE_AGENT_NAME (sesión no nacida del harness);
      · sin WORKSPACE_SESSION_ID (launcher previo a este registro: no sabemos
        cuáles son suyos — quedan para `workspace worktree prune`);
      · en las sesiones de fondo del harness (revisor de skills, headless:
        WORKSPACE_REVIEW_RUNNING), que heredan el entorno de quien las lanzó.
    NUNCA remueve un worktree con cambios sin commitear (lo garantiza
    _worktrees.release). Los worktrees del POOL tibio no se destruyen: release()
    los devuelve al pool (lease liberado, ignorados intactos) — aquí solo queda
    el rastro en el log. Falla-suave TOTAL: jamás rompe el cierre (regla 6)."""
    agent = os.environ.get("WORKSPACE_AGENT_NAME", "").strip()
    if not agent or os.environ.get("WORKSPACE_REVIEW_RUNNING"):
        return
    # Build de cliente: sin dash/dev/ no hay worktrees que liberar — ni se
    # intenta (antes el import fallaba en silencio en CADA cierre).
    if not os.path.isfile(_dev_worktrees_path()):
        return
    try:
        sys.path.insert(0, _ROOT)
        from dash.dev import _worktrees
        session, _pid = _worktrees.current_session()
        if not session:
            return
        res = _worktrees.release(agent=agent, session=session, orphans=True)
    except Exception:
        return
    if (res.get("removed") or res.get("pooled") or res.get("skipped_dirty")
            or res.get("stale")):
        _wt_log(agent, reason, res)


def main():
    data = _stdin()
    sid = data.get("session_id", "")
    brain = data.get("cwd", "") or os.getcwd()
    reason = data.get("reason", "")

    # Motores envueltos (codex/agy/opencode/openclaw/hermes): session_start escribió el
    # marcador con el run_id del wrapper, pero close_payload reemplaza
    # session_id por el id del VENDOR → buscar por run_id primero (sin esto
    # el marcador de esos motores nunca se encontraba ni se limpiaba).
    mp = _marker_path(data.get("run_id") or sid)
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

    # Cierre real → libera los worktrees LIMPIOS de ESTA sesión (la rama queda
    # libre para entrar a revisarla); los de otras pestañas vivas del mismo
    # agente no se tocan. Estructural, automático, falla-suave.
    _release_worktrees(reason)

    # Y10: cierre real → bookkeeping del hook estampa `updated` en la pestaña
    # (jamás `last_opened`, que es solo-humano y la escribe el picker).
    _touch_workspace_updated(brain, sid)

    cleanup()


if __name__ == "__main__":
    main()
