#!/usr/bin/env python3
"""WORKSPACE hook · SessionStart — estampa un marcador de inicio de sesión.

Lo usa `session_end.py` como red de seguridad: si la memoria de la sesión NO se
tocó después de este marcador, el cierre escribe una breadcrumb automática.

Per-máquina y efímero (`~/.claude/workspace/markers/<session_id>.json`). NO toca el
vault sincronizado. Lee JSON de stdin (session_id, cwd, source). Silencioso.
Cero dependencias (stdlib, Python 3.9+).

F3 (Turing 2026-06-25) — early-warning de secretos: el gate DURO solo cubre
los chokepoints que WORKSPACE controla (dream._write_brain_file). Un secreto que
el socio pega a mano en un `.md` del cerebro NO pasa por ahí y Obsidian Sync lo
sube sin barrera. Como red más temprana y visible, al ABRIR sesión escaneamos
el working tree del cerebro y, si hay un secreto sin exención, lo advertimos en
el contexto inicial (additionalContext) — WARN, jamás bloquea (el hook no puede
bloquear el arranque; regla 6 falla-suave). Es defensa en profundidad sobre el
WARN de `doctor fase 9`; no cierra el hueco de Sync (ver AUDIT F3)."""
import sys, os, json, time, subprocess

try:   # M1/B2 · Windows: UTF-8 en stdout/err — un hook capturado por Claude Code en
       # cp1252 reventaría al inyectar contexto con caracteres no-ASCII. No-op en Mac.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


def _stdin():
    try:
        return json.loads(sys.stdin.read() or "{}")
    except Exception:
        return {}


def _marker_path(sid):
    d = os.path.join(os.path.expanduser("~"), ".claude", "workspace", "markers")
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, (sid or "unknown") + ".json")


def _git_head(brain):
    try:
        return subprocess.run(["git", "-C", brain, "rev-parse", "HEAD"],
                              capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=5).stdout.strip()
    except Exception:
        return ""


# F3 · cota dura: el scan corre en CADA arranque, no puede ser lento ni romper.
_SECRET_SCAN_MAX_FINDINGS = 5


def _secret_warning(brain):
    """Si el working tree del cerebro trae un secreto sin exención, devuelve un
    texto de aviso (para additionalContext); si no, "". Falla-suave SIEMPRE: un
    error de import/escaneo devuelve "" y el arranque sigue intacto (regla 6).
    El aviso NUNCA incluye el secreto (enmascarado por el propio scanner)."""
    try:
        # secret_scan vive en la raíz del repo WORKSPACE, no en hooks/
        sys.path.insert(0, os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        import secret_scan
        if secret_scan.env_override_active():
            # F3-audit: el socio activó el escape global. NO callamos — banner
            # persistente en CADA boot mientras la env var siga puesta, para que
            # nadie deje el interruptor pegado sin darse cuenta.
            return ("⚠ Detección de secretos DESACTIVADA por "
                    "%s — quítala para reactivar la protección."
                    % secret_scan.ENV_OVERRIDE)
        findings, _ = secret_scan.scan_brain(brain)
    except Exception:
        return ""
    if not findings:
        return ""
    shown = findings[:_SECRET_SCAN_MAX_FINDINGS]
    lines = ["⚠ SECRETO(S) POSIBLE(S) EN EL CEREBRO (%d) — Obsidian Sync los "
             "sube SIN barrera; el gate duro solo cubre las escrituras del "
             "harness, no lo que pegas a mano:" % len(findings)]
    for x in shown:
        lines.append("  · %s:%s [%s] %s" % (x.get("path", "?"),
                                            x.get("line", "?"),
                                            x["class"], x["excerpt"]))
    if len(findings) > len(shown):
        lines.append("  · (+%d más)" % (len(findings) - len(shown)))
    lines.append("Acción: mueve la clave a una env var o a .gitignore; si ya "
                 "se commiteó, RÓTALA. Falso positivo → marca la línea con "
                 "`workspace:allow-secret`.")
    return "\n".join(lines)


def main():
    data = _stdin()
    sid = data.get("session_id", "")
    if not sid:
        return
    source = data.get("source", "")
    brain = data.get("cwd", "") or os.getcwd()
    p = _marker_path(sid)

    # En compaction NO re-estampamos: movería el baseline a media sesión y la red
    # de seguridad creería que no actualicé la memoria desde la compactación.
    if source == "compact" and os.path.exists(p):
        return

    marker = {
        "started": time.time(),
        "source": source,
        "brain": brain,
        # WORKSPACE_WS = genérico (lo exporta el motor para cualquier agente);
        # ZENITH_WS queda como fallback de back-compat (sesiones pre-generalización).
        "ws": os.environ.get("WORKSPACE_WS", "") or os.environ.get("ZENITH_WS", ""),
        "git_head": _git_head(brain),
    }
    try:
        # Serializar ANTES de abrir + encoding explícito: sin utf-8, Windows
        # abre en cp1252 y un ws/branch con no-ASCII ("Presentación", coreano)
        # revienta A MEDIA escritura → marcador truncado que nadie puede leer.
        blob = json.dumps(marker, ensure_ascii=False)
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(blob)
    except Exception:
        pass

    # F3 · early-warning de secretos en el working tree del cerebro (WARN-only,
    # falla-suave). Solo emitimos si hay hallazgo, para no ensuciar el arranque.
    warn = _secret_warning(brain)
    if warn:
        try:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": warn}}))
        except Exception:
            pass


if __name__ == "__main__":
    main()
