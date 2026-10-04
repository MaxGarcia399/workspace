"""WORKSPACE · engines/_ui.py — UI compartida de los motores WRAPPER.

Banner del cerebro + picker de pestañas para los motores que envuelven un
CLI oficial ajeno (codex, antigravity, …). NO es un motor (el prefijo `_`
lo excluye de available_engines); reusa los helpers probados de
engines/claude_code.py en vez de duplicarlos — claude-code es el harness de
REFERENCIA y su launch no cambia.

Caveat honesto del banner (SESIONES-MULTI-HARNESS.md §1): en un TUI
full-screen (codex entra a alt-screen) el banner se ve un instante y queda
TAPADO durante el chat; reaparece al salir. En CLIs inline se queda arriba.
Falla-suave absoluta: nada de aquí rompe un launch.
"""
import os
import shutil
import subprocess
import sys

from engines import claude_code as _cc


def show_brain_banner(cfg, engine_label=""):
    """Mismo patrón que claude_code.launch: clear → banner del CEREBRO
    renderizado a buffer con width-check (jamás mostrarlo roto) → fallback
    al banner genérico derivado de la def del agente. El banner sale
    CENTRADO (greeter unificado) y `engine_label` ("Codex · gpt-…") se
    exporta en WORKSPACE_ENGINE_LABEL para que el banner muestre el
    motor+modelo REAL de la corrida (regla del socio: siempre visible)."""
    if engine_label:
        os.environ["WORKSPACE_ENGINE_LABEL"] = str(engine_label)
    try:
        sys.stdout.write("\033[2J\033[3J\033[H")
        sys.stdout.flush()
    except Exception:
        pass
    banner = (cfg.get("_scripts") or {}).get("banner")
    cols = shutil.get_terminal_size((80, 24)).columns
    if banner and os.path.exists(banner):
        try:
            rendered = subprocess.run(
                [_cc._py(), banner], capture_output=True, text=True,
                encoding="utf-8", errors="replace",
                env=_cc._utf8_env()).stdout
            if rendered.strip():
                need = _cc._max_visual_width(rendered)
                if need <= cols:
                    pad = " " * max(0, (cols - need) // 2)
                    sys.stdout.write("\n".join(
                        (pad + ln if ln.strip() else ln)
                        for ln in rendered.split("\n")))
                    sys.stdout.flush()
                else:
                    _cc._too_narrow_banner(cfg, cols, need)
                return
        except Exception:
            pass
    _cc._generic_banner(cfg)


def pick_tab(cfg, preselect=None):
    """El MISMO picker de pestañas de Claude Code (dashboard --pick, ya con
    el color del tema del hub) corriendo antes de CUALQUIER motor — es un
    subproceso, agnóstico del harness. Devuelve (wid_claude, nombre) o None
    (sin dashboard / error / elección vacía → el motor lanza como siempre)."""
    if preselect and preselect.get("wid"):
        return preselect["wid"], preselect.get("name", "")
    try:
        choice = _cc.pick(cfg)
    except Exception:
        choice = ""
    parts = (choice or "").split("\t")
    if len(parts) >= 3 and parts[0] == "WS":
        return parts[1], parts[2]
    return None


def export_tab_env(cfg, wid, name):
    """Exporta los env de pestaña (genéricos + específicos del agente) para
    statuslines/hijos — paridad con claude_code.launch."""
    try:
        os.environ["WORKSPACE_WS"] = name
        os.environ["WORKSPACE_WID"] = wid
        os.environ[cfg.get("session_env", "ZENITH_WS")] = name
        os.environ[cfg.get("session_id_env", "ZENITH_WID")] = wid
    except Exception:
        pass
