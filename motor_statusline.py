"""WORKSPACE · motor_statusline — la barra de Workspace en la statusLine NATIVA
de los motores que la traen con comando: GitHub Copilot y Cursor.

Los dos aceptan `statusLine: {type:"command", command, padding, …}` en su
config de USUARIO y le pasan al comando el JSON de la sesión por stdin (forma
parecida a la de Claude Code). VERIFICADO en una pty con los binarios reales,
en carpetas de config desechables y sin mandar ningún mensaje a un modelo:

GitHub Copilot 1.0.105 (`copilot help config` → statusLine)
  · solo la lee de $COPILOT_HOME/settings.json (~/.copilot); la del repo
    (.github/copilot/settings.json y settings.local.json) NO la activa, ni con
    la carpeta de confianza. Sin flag ni variable por corrida (COPILOT_HOME
    movería cuentas y sesiones);
  · corre con /bin/sh (cmd.exe en Windows) al abrir y tras cada evento; hereda
    el entorno de Copilot (los WORKSPACE_* del arranque) y tiene /dev/tty;
  · su línea se APILA debajo del pie nativo; una salida vacía no deja renglón;
  · JSON: model.{id,display_name}, context_window.{current_context_tokens,
    current_context_used_percentage, used_percentage, …}, cost.{total_premium_
    requests, total_lines_added/removed}, ai_used.{total_nano_aiu,formatted},
    workspace.current_dir, cwd, allow_all_enabled. Sin cuota del plan (la
    pinta el pie nativo) ni rama.

Cursor (`statusLine` de `cli-config.json`; changelog oficial: «Custom status
line. Point statusLine at your own command and render its output (with live
token usage data) in the prompt footer», https://cursor.com/docs/cli/changelog;
no hay página de doc del esquema). Lo de abajo es doc o caja negra, nunca su
código:
  · solo en la config de usuario (doc: «Only permissions can be configured at
    the project level», https://cursor.com/docs/cli/reference/configuration):
    $CURSOR_CONFIG_DIR → $XDG_CONFIG_HOME/cursor → ~/.cursor (caja negra:
    tests/test_motores_cursor.py · CursorBinarioReal);
  · REEMPLAZA las filas nativas del pie aunque imprima vacío (equipo de Cursor
    en su foro: «Footer replacement is currently intended», https://forum.
    cursor.com/t/cursor-cli-custom-statusline-replaces-native-footer-and-
    cannot-preserve-auto-review-state/166364): por eso la barra de Cursor imprime
    SIEMPRE y repone lo que el JSON trae (modelo, %, auto-run, vim, carpeta ·
    rama fuera de Workspace);
  · JSON: se vieron en vivo con cuenta `model.display_name` (ya trae los
    parámetros) y `model.param_summary` (2026-10-29) y la barra dentro y fuera
    de Workspace (e2e v6, 2026-11-02); `autorun` lo nombra el equipo de Cursor
    en ese hilo. El resto (`model.max_mode`, `context_window.used_percentage`,
    `render_width_chars`, `vim.mode`, `cwd`, `workspace.current_dir`) se lee
    FALLA-SUAVE (si no viene, no se pinta) y es A-VERIFICAR con
    tests/e2e/cursor_caja_negra.py --aislado, que vuelca las claves reales y
    dice si el comando pasa por una shell. El comando es una sola ruta (el
    shim), así que sirve con o sin shell.

Regla mínimo invasivo: una statusLine que no es de Workspace es del socio y
JAMÁS se toca; una nuestra vieja o rota se repara; el resto del archivo queda
igual (lectura-modificación-escritura atómica). Opt-out por motor
(WORKSPACE_COPILOT_NO_STATUSLINE / WORKSPACE_CURSOR_NO_STATUSLINE): al abrir,
Workspace QUITA la suya y el motor queda como lo diseñó el proveedor. El
comando apunta a un shim estable en ~/.local/bin (el mismo de Antigravity,
parametrizado) que resuelve el harness al correr. Sin credenciales: no abre
~/.copilot/config.json y no imprime el JSON.
"""
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

import antigravity_usage as _shim     # el MISMO shim de Antigravity

MAX_BYTES = 65536
SCRIPT = "motor_statusline.py"

#: Por motor: nombre visible, shim, marca, opt-out, claves extra de la
#: statusLine, ¿reemplaza la fila nativa? y ¿respaldo del archivo antes de la
#: primera escritura? (cli-config.json de Cursor guarda `authInfo`: no se copia).
SPECS = {
    "copilot": {"label": "GitHub Copilot", "shim": "workspace-copilot-statusline",
                "mark": "# WORKSPACE · statusLine de GitHub Copilot",
                "optout": "WORKSPACE_COPILOT_NO_STATUSLINE",
                "extra": {"padding": 1}, "replaces_native": False, "backup": True},
    "cursor": {"label": "Cursor", "shim": "workspace-cursor-statusline",
               "mark": "# WORKSPACE · statusLine de Cursor",
               "optout": "WORKSPACE_CURSOR_NO_STATUSLINE",
               "extra": {"padding": 0}, "replaces_native": True, "backup": False},
}
_BACKUP_SUFFIX = ".workspace-statusline-backup"


def _spec(engine):
    try:
        return SPECS[engine]
    except KeyError:
        raise ValueError("motor sin statusLine de Workspace: %r" % (engine,))


def settings_path(engine, env=None):
    """Archivo de config de USUARIO del motor donde vive su statusLine."""
    _spec(engine)
    try:
        if engine == "copilot":
            from engines.copilot import copilot_home
            return Path(copilot_home(env)) / "settings.json"
        from engines.cursor import config_dir
        return Path(config_dir(env)) / "cli-config.json"
    except Exception:
        base = ".copilot" if engine == "copilot" else ".cursor"
        name = "settings.json" if engine == "copilot" else "cli-config.json"
        return Path.home() / base / name


def opted_out(engine, env=None):
    env = os.environ if env is None else env
    return bool(str(env.get(_spec(engine)["optout"]) or "").strip())


def shim_text(engine, root=None, python=None):
    s = _spec(engine)
    return _shim.shim_text(root=root, python=python, script=SCRIPT, mark=s["mark"],
                           motor=s["label"], args=(engine,))


def _python():
    if os.name == "nt":
        try:
            import install
            return install.win_python()
        except Exception:
            pass
    return sys.executable or "python3"


def bridge_config(engine, home=None):
    """statusLine que Workspace quiere: el shim (POSIX) o, en Windows / sin
    shim, Python + este archivo + el motor. Cursor en Windows corre su
    statusLine con cmd.exe y no la pinta si el script va entre comillas
    (VERIFICADO 2026-11-06): sin comillas cuando se puede, con las carpetas
    en 8.3 (antigravity_usage.win_cmdline). Copilot, como siempre."""
    s = _spec(engine)
    shim = _shim.ensure_shim(home, name=s["shim"], text=shim_text(engine), mark=s["mark"])
    me = str(Path(__file__).resolve())
    if shim is not None:
        command = shlex.join([str(shim)])
    elif os.name == "nt":
        if engine == "cursor":
            command = _shim.win_cmdline([_python(), me, engine])
        else:
            command = subprocess.list2cmdline([_python(), me, engine])
    else:
        command = shlex.join([_python(), me, engine])
    return dict({"type": "command", "command": command}, **s["extra"])


def is_ours(engine, command):
    """¿Esta statusLine es la de Workspace PARA ESTE motor (actual, vieja o con
    ruta muerta)?"""
    s = _spec(engine)
    c = str(command or "")
    if s["shim"] in c:
        return True
    if SCRIPT in c:
        tail = c.split(SCRIPT, 1)[1].replace('"', " ").replace("'", " ").split()
        return bool(tail) and tail[0] == engine
    return False


def _read(path):
    """(dict, texto) del archivo; ({}, None) si no existe. ValueError si no es
    un objeto JSON o pesa demasiado."""
    if not path.exists():
        return {}, None
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("too big")
    text = path.read_text(encoding="utf-8")
    data = json.loads(text) if text.strip() else {}
    if not isinstance(data, dict):
        raise ValueError("not an object")
    return data, text


def _write(path, data, mode=None):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".%s-" % path.stem, dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        if mode is not None:
            os.chmod(tmp, mode)
        os.replace(tmp, str(path))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def inspect(engine, path=None, env=None):
    """SOLO LEE (plan): 'absent' | 'ours' | 'custom' | 'off' | 'blocked'."""
    env = os.environ if env is None else env
    if opted_out(engine, env):
        return "off"
    path = Path(path or settings_path(engine, env))
    try:
        if path.is_symlink():
            return "blocked"
        data, _txt = _read(path)
    except (OSError, ValueError):
        return "blocked"
    if "statusLine" not in data:
        return "absent"
    ex = data.get("statusLine")
    if not isinstance(ex, dict) or not is_ours(engine, ex.get("command")):
        return "custom"
    return "off" if ex.get("enabled", True) is False else "ours"


def plan_line(engine, env=None):
    """Una línea para el plan de arranque (solo lee)."""
    s = _spec(engine)
    st = inspect(engine, env=env)
    what = {"absent": "se agrega la de Workspace al abrir",
            "ours": "la de Workspace (se re-asegura al abrir)",
            "custom": "la tuya; Workspace no la toca",
            "off": "apagada (%s=1 la quita, o enabled:false)" % s["optout"],
            "blocked": "no se puede leer: Workspace no la toca"}.get(st, st)
    tail = (" · reemplaza la fila nativa del pie (modelo, %, carpeta y rama "
            "van en la de Workspace)") if s["replaces_native"] else \
        " · se apila bajo el pie nativo"
    return "statusLine nativa de %s (%s) → %s%s" % (
        s["label"], settings_path(engine, env), what, tail)


def ensure_statusline(engine, path=None, home=None, env=None):
    """Al abrir un agente en el motor: crea la nuestra si no hay ninguna,
    REPARA una nuestra vieja/rota y respeta la del socio (y una nuestra que él
    apagó con enabled:false). Con el opt-out del motor, QUITA la nuestra.
    → 'ready' | 'repaired' | 'custom' | 'off' | 'blocked'. Nunca ejecuta
    comandos del socio ni toca otras claves."""
    s = _spec(engine)
    env = os.environ if env is None else env
    path = Path(path or settings_path(engine, env))
    try:
        if path.is_symlink():
            return "blocked"
        data, text = _read(path)
        ex = data.get("statusLine")
        ours = isinstance(ex, dict) and is_ours(engine, ex.get("command"))
        if opted_out(engine, env):
            if ours:
                del data["statusLine"]
                _write(path, data, path.stat().st_mode & 0o777)
            return "off"
        if "statusLine" in data:
            if not ours:
                return "custom"
            if ex.get("enabled", True) is False:
                return "off"
            want = bridge_config(engine, home)
            if ex.get("command") == want["command"]:
                return "ready"
            fixed = dict(ex)
            fixed["command"] = want["command"]
            fixed.setdefault("type", "command")
            data["statusLine"] = fixed
            status = "repaired"
        else:
            data["statusLine"] = bridge_config(engine, home)
            status = "ready"
        mode = None
        if text is not None:
            mode = path.stat().st_mode & 0o777
            backup = path.with_name(path.stem + _BACKUP_SUFFIX + path.suffix)
            if s["backup"] and not backup.exists():
                with open(str(backup), "w", encoding="utf-8") as fh:
                    fh.write(text)
                os.chmod(str(backup), 0o600)
        _write(path, data, mode)
        return status
    except (OSError, ValueError, TypeError, AttributeError):
        return "blocked"


def clean_settings(engine, data):
    """(dict nuevo, quitó?) sin la statusLine de Workspace (desinstalar)."""
    if not isinstance(data, dict):
        return data, False
    sl = data.get("statusLine")
    if not (isinstance(sl, dict) and is_ours(engine, sl.get("command"))):
        return data, False
    new = dict(data)
    del new["statusLine"]
    return new, True


def in_workspace(engine, payload, env=None):
    """¿Sesión de Workspace? Lanzada por Workspace en este motor, o abierta
    dentro del cerebro de un agente."""
    env = os.environ if env is None else env
    if str(env.get("WORKSPACE_SESSION_ENGINE") or "") == engine:
        return True
    ws = payload.get("workspace") if isinstance(payload.get("workspace"), dict) else {}
    where = ws.get("current_dir") or payload.get("cwd") or ""
    if not where:
        return False
    from workspace_status import agent_for_dir
    return bool(agent_for_dir(where))


def terminal_width(default=100):
    """Ancho real: la salida del comando es un tubo, pero la terminal está en
    /dev/tty (CONOUT$ en Windows). Respaldo: $COLUMNS, luego `default`."""
    dev = "CONOUT$" if os.name == "nt" else "/dev/tty"
    try:
        fd = os.open(dev, os.O_RDWR if os.name == "nt" else os.O_RDONLY)
        try:
            cols = os.get_terminal_size(fd).columns
            if cols > 0:
                return cols
        finally:
            os.close(fd)
    except OSError:
        pass
    try:
        cols = int(os.environ.get("COLUMNS") or 0)
        if cols > 0:
            return cols
    except ValueError:
        pass
    return default


def render(engine, payload, env=None, width=None):
    """Líneas de la barra para `payload` (lista; vacía = nada que pintar)."""
    import workspace_status as W
    env = os.environ if env is None else env
    if opted_out(engine, env):
        return []
    if engine == "copilot":
        if not in_workspace(engine, payload, env):
            return []            # fuera de Workspace, Copilot queda vanilla
        if width is None:
            width = terminal_width() - SPECS["copilot"]["extra"]["padding"] - 1
        return W.copilot_lines(payload, env=env, width=max(16, width))
    if engine == "cursor":
        if width is None:
            try:
                width = int(payload.get("render_width_chars") or 0) - 1
            except (TypeError, ValueError):
                width = 0
            if width <= 0:
                width = terminal_width() - 5
        return W.cursor_lines(payload, env=env, width=max(16, width),
                              workspace=in_workspace(engine, payload, env))
    return []


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    try:                          # Windows: la barra sale en UTF-8 (cp1252 truena)
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    try:
        engine = argv[0] if argv else ""
        if engine not in SPECS:
            return
        # el lector único (_utf8): BYTES → UTF-8 y tolera el BOM; más de
        # MAX_BYTES, basura o algo que no es objeto → {} → sin barra
        import _utf8
        data = _utf8.json_de_stdin(limite=MAX_BYTES)
        if not data:
            return
        lines = render(engine, data)
        if lines:
            print("\n".join(lines))
    except Exception:
        pass
    # Solo el texto de la barra va a stdout; jamás diagnósticos ni el JSON.


if __name__ == "__main__":
    main()
