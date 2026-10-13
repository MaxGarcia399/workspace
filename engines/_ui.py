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


def theme_cols(accent, dim):
    """(acento, tenue) del TEMA del hub para los banners mínimos de respaldo
    de los motores; los colores fijos dados quedan si tuitheme no está."""
    try:
        import tuitheme
        P = tuitheme.palette()
        return P.C, P.DIM
    except Exception:
        return accent, dim


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
    except Exception as e:
        choice = ""
        _cc.LAST_PICK_ERROR = "selector de pestañas falló (%s: %s)" % (
            type(e).__name__, e)
        _cc._session_log(cfg, cfg.get("_engine") or "?", _cc.LAST_PICK_ERROR)
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
        se, we = _cc.session_env_names(cfg)   # SSOT: default derivado del nombre
        os.environ[se] = name
        os.environ[we] = wid
    except Exception:
        pass


# ── barra MÍNIMA de Workspace para motores sin statusline propia (U10/Z10) ──
# agy (Antigravity CLI) no expone hook de statusline (verificado con
# `agy --help`, 2026-10-10: sin opción de barra/status). En vez de inventar
# hooks o secuestrar la pantalla del TUI, Workspace muestra lo que SÍ sabe:
#   · una línea al arrancar con agente · pestaña · motor · permisos ·
#     guardado de memoria;
#   · el TÍTULO de la ventana de terminal (OSC 0) con lo mismo en corto —
#     persiste mientras el TUI full-screen está arriba y no lo tapa.
# Tokens/costo NO se muestran como números: el CLI no los publica
# (desconocido ≠ 0).

def status_fields(cfg, tab=None, engine_label="", perms="", saving=""):
    """Campos REALES de la barra; los desconocidos se dicen como tales."""
    return [("agente", str(cfg.get("display") or cfg.get("name") or "?")),
            ("pestaña", (tab[1] if tab else "") or "sin pestaña"),
            ("motor", engine_label or str(cfg.get("_engine") or "?")),
            ("permisos", perms or "los del CLI"),
            ("memoria", saving or "desconocido"),
            ("tokens", "no publicados por el CLI")]


def status_line(fields):
    return " · ".join("%s %s" % (k, v) for k, v in fields)


def show_status_bar(fields, out=None):
    """Imprime la barra mínima y fija el título de la terminal (si es tty).
    Falla-suave: jamás rompe un launch."""
    out = out or sys.stdout
    try:
        out.write("\033[2m[WORKSPACE] %s\033[0m\n" % status_line(fields))
        if getattr(out, "isatty", lambda: False)():
            short = " · ".join(v for _k, v in fields[:4])
            out.write("\033]0;%s\007" % short.replace("\007", ""))
        out.flush()
    except Exception:
        pass


def clear_title(out=None):
    out = out or sys.stdout
    try:
        if getattr(out, "isatty", lambda: False)():
            out.write("\033]0;\007")
            out.flush()
    except Exception:
        pass
