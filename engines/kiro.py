"""WORKSPACE · engines/kiro.py — motor Kiro (AWS · CLI `kiro-cli`).

Hace ejecutable un agente sobre Kiro CLI, el agente de terminal de AWS (antes
Amazon Q Developer CLI). La cuenta es la de Kiro (Builder ID, IAM Identity
Center, Google o GitHub; o una llave KIRO_API_KEY para corridas sin ventana) y
el modelo lo elige el socio dentro de Kiro. Vendor-neutral, enchufable por
nombre — dispatch.py lo carga solo ("kiro" → engines/kiro.py).

🔴 INVARIANTE DE SEGURIDAD: las credenciales las gestiona el BINARIO OFICIAL
(`kiro-cli login`). WORKSPACE jamás lee, extrae ni reusa tokens: el estado se
consulta con `kiro-cli whoami --format json` (solo el tipo de cuenta).

Tres formas de correr (contrato de WORKSPACE):
  · INTERACTIVO — `launch()`: banner + wrapper neutral
    (interactive.run_official_cli_interactive: session_start → `kiro-cli chat`
    en el cerebro → session_end).
  · HEADLESS one-shot — `run_turn()`: `kiro-cli chat --no-interactive` con el
    mensaje por stdin (doc oficial «headless»). A-VERIFICAR con una cuenta.
  · CAPTURA — la sesión de la pestaña se lee de sus archivos
    (V2: `~/.kiro/sessions/cli/<uuid>.jsonl`; V3:
    `~/.kiro/sessions/<huella>/sess_<uuid>/`), sin abrir el CLI: el CLI de
    Kiro sin cuenta abre el navegador para iniciar sesión.

HECHOS VERIFICADOS con el binario real (kiro-cli 2.34.0, macOS, HOME desechable
y una llave FALSA de API: el motor escribe la sesión con el mensaje del socio y
un error de credencial, sin costo):
  · `kiro-cli chat` interactivo abre el motor «V3» (TUI nuevo). Guarda cada
    sesión en `~/.kiro/sessions/<sha256(cwd)[:16]>/sess_<uuid>/session.json`
    (+ `messages.jsonl` desde el primer mensaje) y la indexa en
    `~/.kiro/session-index/<huella>.jsonl`. El id lo crea Kiro (no acepta uno
    propio); al salir imprime «Resume with: kiro-cli --resume-id sess_…».
  · `--resume-id sess_<uuid>` retoma la MISMA sesión (muestra el historial);
    con un id que no existe se queda en «Launching…» sin crear nada: por eso
    el adapter valida que la sesión exista antes de retomar.
  · Un argumento posicional (`kiro-cli chat "<mensaje>"`) ENVÍA ese mensaje al
    abrir (queda en messages.jsonl) → arranque del cerebro en sesión nueva.
  · La 1ª vez en una carpeta, V3 pregunta «Trust this workspace?». La opción
    oficial `--trust-workspace` (2.34+) confía SOLO esa carpeta, SOLO en ese
    arranque y no guarda nada (verificado: sin entrada en
    `~/.kiro/workspace-roots/`). Es el mecanismo más acotado: el cerebro abre
    sin preguntar y sin escribir config. Opt-out: WORKSPACE_KIRO_NO_AUTOTRUST=1.
  · Leer el cerebro no pide permiso: la sesión nace con
    `allowed_read_paths = [cwd]` (V2) y la política por defecto de V3 permite
    `fs_read` en `./**` (doc oficial «permissions»). Workspace no escribe
    permisos.
  · `whoami --format json`: sin sesión `{"account":null}` (rc=1); con llave
    `{"accountType":"ApiKey",…}` (rc=0, no la valida). No abre el navegador.
  · Mensaje del socio en messages.jsonl:
    `{"id","timestamp","payload":{"type":"user","content":"…",…}}`. La de la
    respuesta, VERIFICADA en 3.1.0 por caja negra (la captura de sesiones V3
    reales sale «decoded»): `payload.type == "assistant"`, texto en `content`.
  · Lee AGENTS.md de la raíz, siempre incluido (doc oficial «steering»,
    https://kiro.dev/docs/steering/) → mismo AGENTS.md PUNTERO que
    codex/opencode.
  · Instalado solo con Homebrew, `kiro-cli chat` falla («failed to launch
    ~/.local/bin/kiro-cli-chat») hasta que la app «Kiro CLI» corre una vez: el
    instalador oficial la abre él mismo. `install_problem()` lo detecta.

VERIFICADO con la 2.35.1 y una cuenta real (macOS, 2026-10-29): `kiro-cli
chat` volvió a abrir el motor V2 («An early release of Kiro CLI V3 is now
available! Try it out: kiro-cli --v3»; `--list-sessions` dice `"source":
"v2"`). Cada sesión son archivos sueltos `~/.kiro/sessions/cli/<uuid>.json`
(`session_id`, `cwd`, `created_at`, `updated_at`, `title`) + `.jsonl` (un
registro por línea: `{"version":"v1","kind":"Prompt"|"AssistantMessage"|
"ToolResults","data":{"content":[{"kind":"text","data":"…"},…],"meta":
{"timestamp":<epoch>}}}`) + `.history`. El id es el uuid PELADO, y
`--resume-id <uuid>` la retoma (al salir: «Resume with: kiro-cli --resume-id
<uuid>»). Con solo V3 en el adapter, la captura salía «missing» y la pestaña
nunca se ataba: se leen los dos almacenes.

CONFIG EN EL CEREBRO, NADA EN LA GLOBAL: todo lo que Workspace le da a Kiro
vive en el agente `workspace` del PROYECTO (`<cerebro>/.kiro/agents/
workspace.json`; doc «custom agents», https://kiro.dev/docs/custom-agents/:
el del proyecto gana al global del mismo nombre y solo carga con la carpeta
de confianza, por eso va `--trust-workspace`), elegido POR CORRIDA
(`--agent workspace`) salvo que el socio elija agente o motor. La identidad va
en el AGENTS.md (no hace falta `.kiro/steering/`) y Workspace no usa hooks de
Kiro. Lo que una versión anterior dejaba en `~/.kiro` (el agente global y los
segmentos de la barra) lo quita la migración 202611052341_kiro_config_en_el_cerebro.

El agente sirve en las dos líneas (doc «agent configuration reference»: V3
carga un archivo con `permissions` aunque traiga los campos de 2.x):
  · MEMORIA SIN PEDIR PERMISO: la herramienta MCP de Workspace (memoria_mcp:
    `guardar_nota`, `guardar_resumen`, `ver_memoria`, sin terminal); 2.x la
    aprueba con `allowedTools` (`@workspace-memoria/<herramienta>`) y V3 con
    `permissions.rules` (capacidad `mcp`). Antes el agente era global y
    aprobaba la RUTA de un comando con una regex: en Windows, con Kiro 3.0,
    `${function:<ruta>}=…` la reemplazaba.
  · ESCRIBIR EN EL CEREBRO SIN PREGUNTAR con autonomía «brain» (la de
    fábrica): 2.x `toolsSettings.fs_write.allowedPaths` y V3 una regla `allow`
    de `fs_write`, las dos `./**` (la carpeta donde abre Kiro = el cerebro).
    Fuera del cerebro pregunta; `.kiro/` se niega siempre. Con «ask» pregunta
    todo, como antes. Nunca `--trust-tools=fs_write` ni `--trust-all-tools`.
    VERIFICADO 3.1.0 en vivo (V2 y V3 sin ventana, y el arranque de Workspace
    en un pty; cerebro temporal): tests/e2e/kiro_permisos.py.

BARRA: la nativa de Kiro, sin tocar. Su doc solo documenta prenderle
segmentos (fecha, hora, uso y créditos) desde `/settings display` (doc «slash
commands», https://kiro.dev/docs/reference/slash-commands/), así que eso lo
decide el socio ahí. Con `--agent workspace` Kiro muestra el agente en uso.

Cero dependencias (stdlib, 3.9+). Mac/Windows/Linux. Falla-suave.
"""
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)
import arbol_procesos  # noqa: E402  (Windows: al vencer el tiempo muere el árbol entero)

META = {"name": "kiro", "needs": ["kiro-cli"], "auth": "oauth"}

#: Matriz de capacidades (contrato harness-os §3; la consume harnesses.py).
#: TODAS las claves de capabilities.ENGINE_KEYS (lo exige test_capabilities).
CAPABILITIES = {
    "launch": "wrapper",              # TUI oficial envuelto en el ciclo neutral
    "inject_context": "project-doc",  # AGENTS.md puntero → doc de identidad
    "mcp": True,                      # Kiro soporta MCP (su propia config: `kiro-cli mcp`)
    "hooks": "wrapper",               # solo inicio/cierre del wrapper neutral; sus hooks
                                      # nativos (agentSpawn, userPromptSubmit…) NO se cablean
    "sessions": "workspace",          # pestañas del registro neutral: Kiro crea la sesión,
                                      # se ata al cerrar y se retoma con --resume-id
    "status_live": False,             # sin now.json desde dentro (sin hooks por turno)
    "headless": True,                 # run_turn (`chat --no-interactive`); A-VERIFICAR con cuenta
    "statusline": False,              # su barra nativa, sin tocar: los segmentos
                                      # se prenden en `/settings display` (lo único
                                      # que documenta Kiro)
}

BINARY = "kiro-cli"

#: Versiones del CLI oficial con las que se VERIFICARON las lecturas de este
#: adapter (engine_versions: doctor avisa si la instalada es de otra línea).
#: 2.34.0 (macOS, 2026-10-28). 2.35.1 (macOS, cuenta real, 2026-10-29: chat V2,
#: sesiones en sessions/cli/; checklist e2e con dos agentes). Kiro anuncia la
#: 3.0 para fin de octubre de 2026 y se actualiza solo: verificar y agregar en
#: cuanto llegue. 2.35.2 (2026-10-29): memoria sin permiso con el agente
#: `workspace` y los segmentos de la barra (memoria_motores en vivo, pty).
# 2.37.0 (2026-10-31) y 2.37.1 (2026-11-02): la batería e2e completa en vivo
# con cuenta real (checklist, escenarios, memoria, la X y un crash, barra).
# 3.0.0 (2026-11-03, V3 de fábrica): NO verificada en esta Mac. La memoria va por
# la herramienta MCP con un agente válido en V3 según la doc (`permissions.rules`,
# capacidad `mcp`); el motor V3 se probó en vivo con `--v3` en 2.37.1 (2026-11-05).
# 3.1.0 (2026-11-05, macOS, cuenta real, sin ventana): el agente del cerebro carga
# en V2 y V3; escribir en el cerebro no pregunta, fuera pregunta y `.kiro/` se
# niega (tests/e2e/kiro_permisos.py). Las sesiones (§3.2) siguen sin verificar en 3.x.
VERIFIED_VERSIONS = ("2.34.0", "2.35.1", "2.35.2", "2.37.0", "2.37.1")
#: `--trust-workspace` existe desde la 2.34 (doc oficial «permissions»).
TRUST_FLAG_SINCE = (2, 34)

# 🔴 EL HARNESS NO FIJA MODELO (regla de producto). El modelo lo elige el socio
# dentro de Kiro (`/model`, `chat.defaultModel`) — este adapter JAMÁS pasa
# `--model` en el launch ni lee esa config. En run_turn, `model` es solo un
# override OPCIONAL para smokes/eval (nunca un default).

_NO_AUTOTRUST_ENV = "WORKSPACE_KIRO_NO_AUTOTRUST"
#: Lo que una versión anterior de Workspace prendió en la barra de Kiro (en su
#: config global), anotado en el estado de Workspace: SOLO para deshacerlo
#: (migración y desinstalador). Workspace ya no escribe esa config.
_STATUSLINE_STATE = "kiro-statusline.json"
_ANSI = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]")
_UUID = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
#: Id de una sesión V3 (`sess_<uuid>`, carpeta propia).
_SID = re.compile(r"sess_" + _UUID)
#: Id de una sesión V2 (el uuid pelado; archivos en `sessions/cli/`).
_V2_SID = re.compile(_UUID)


def _exe(override=None):
    """Ruta al binario. override=None → PATH; override="" → no hay (tests);
    override="/ruta" → esa ruta."""
    if override is None:
        return shutil.which(BINARY)
    return override or None


def _env_motor():
    """El env para correr el CLI del motor: sin NADA de la bóveda
    (secret_store.engine_env). Falla-suave: sin secret_store, el heredado."""
    try:
        import secret_store
        return secret_store.engine_env()
    except Exception:
        return None


def _sin_consola():
    """Windows: lo que corre al cerrar va sin consola (ver opencode)."""
    return ({"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)}
            if os.name == "nt" else {})


# ── macOS: no ejecutar un programa que Gatekeeper retiene ───────────────────
def gatekeeper_block(exe=None):
    """None si macOS deja correr `kiro-cli`; si no, {path, cask, files, why}
    (engine_gatekeeper.check): Workspace NO lo ejecuta (cada llamada abriría el
    diálogo de macOS) y Motores ofrece reinstalar con la receta oficial. El
    cask `kiro-cli` deja «Kiro CLI.app» con cuarentena pero notarizada y
    engrapada: no se bloquea (VERIFICADO 2026-10-29)."""
    exe = exe or _exe()
    if not exe:
        return None
    try:
        import engine_gatekeeper as _gk
        info = _gk.check(exe)
        return dict(info, why=_gk.message(info)) if info else None
    except Exception:
        return None


# ── cuenta ──────────────────────────────────────────────────────────────────
def _whoami(exe, runner=None):
    """`kiro-cli whoami --format json` → (True|False|None, tipo de cuenta).
    False solo cuando Kiro dice que no hay cuenta (`{"account": null}`); una
    salida que no se entiende es «no sé» (None), jamás «sin sesión». Nunca
    abre el navegador ni lee tokens. `runner` es knob de test. Con el programa
    retenido por macOS no se ejecuta (gatekeeper_block) → «no sé»."""
    if gatekeeper_block(exe):
        return None, ""
    cmd = [exe, "whoami", "--format", "json"]
    try:
        if runner is not None:
            r = runner(cmd)
        else:
            r = arbol_procesos.run(cmd, capture_output=True, text=True, timeout=20,
                                   encoding="utf-8", errors="replace",
                                   stdin=subprocess.DEVNULL, env=_env_motor(), **_sin_consola())
        out = getattr(r, "stdout", "") or ""
        if isinstance(out, bytes):
            out = out.decode("utf-8", "replace")
        out = _ANSI.sub("", out)
        i = out.find("{")
        data = json.loads(out[i:out.rfind("}") + 1]) if i >= 0 else None
    except Exception:
        return None, ""
    if not isinstance(data, dict):
        return None, ""
    if "account" in data and data.get("account") is None:
        return False, ""
    kind = data.get("accountType")
    acc = data.get("account")
    if kind is None and isinstance(acc, dict):
        kind = acc.get("accountType") or acc.get("type")
    if kind or acc:
        return True, str(kind or "cuenta")[:40]
    return None, ""


def session_active(exe_override=None, runner=None):
    """¿Hay una cuenta de Kiro activa? True/False, o None si no se pudo saber.
    Sin binario → False."""
    exe = _exe(exe_override)
    if not exe:
        return False
    return _whoami(exe, runner=runner)[0]


def available(exe_override=None):
    """LISTO para ejecutar agentes: binario en PATH (el login lo resuelve Kiro)."""
    return bool(_exe(exe_override))


def install_problem(exe=None, home=None):
    """'' si la instalación sirve; si no, el aviso para el socio. macOS: con
    solo Homebrew, `kiro-cli chat` busca `~/.local/bin/kiro-cli-chat`, que crea
    la app «Kiro CLI» al correr la primera vez (el instalador oficial la abre).
    VERIFICADO 2.34.0: sin ese archivo, «failed to launch …/kiro-cli-chat»."""
    exe = exe or _exe()
    if not exe or sys.platform != "darwin":
        return ""
    try:
        real = os.path.realpath(exe)
    except OSError:
        return ""
    if ".app/Contents/MacOS/" not in real.replace("\\", "/"):
        return ""
    home = home or os.path.expanduser("~")
    if os.path.exists(os.path.join(home, ".local", "bin", "kiro-cli-chat")):
        return ""
    return ("la instalación de Kiro CLI está incompleta: abre una vez la app «Kiro CLI» "
            "(Aplicaciones) o instálalo con su instalador oficial "
            "(curl -fsSL https://cli.kiro.dev/install | bash)")


#: Cask de Homebrew de Kiro (`brew info --cask kiro-cli`, 2026-10-29): la app en
#: /Applications y el enlace `<prefijo>/bin/kiro-cli`. `brew uninstall --cask`
#: SIN `--zap` no toca ~/.kiro ni ~/Library/Application Support/kiro-cli (la
#: sesión): el zap sí los manda a la papelera, por eso Workspace nunca lo usa.
CASK = "kiro-cli"


def _cask_of(exe):
    """'kiro-cli' si `exe` es el enlace que deja el cask de Homebrew
    (`<prefijo>/bin/kiro-cli` con `<prefijo>/Caskroom/kiro-cli`), si no ''.
    Solo mira carpetas."""
    try:
        prefix = os.path.dirname(os.path.dirname(os.path.abspath(str(exe))))
        return CASK if os.path.isdir(os.path.join(prefix, "Caskroom", CASK)) else ""
    except Exception:
        return ""


def install_block(exe=None, home=None):
    """None si la instalación sirve; si no {why, cask, detail}: `kiro-cli chat`
    no abre porque falta `~/.local/bin/kiro-cli-chat` (cask sin abrir la app;
    VERIFICADO 2.34.0). Barato: solo archivos, sin subprocesos (install_problem).
    La cuenta sí funciona (`whoami` y `login` son del programa principal), pero
    Motores ya no dice «listo»: dice «instalación incompleta» y ofrece reparar
    con la receta oficial (antes quita el cask: engine_install.reinstall)."""
    exe = exe or _exe()
    falta = install_problem(exe, home=home) if exe else ""
    if not falta:
        return None
    why = falta
    try:
        import engine_gatekeeper as _gk
        why = _gk.text(
            "motores.kiro.incompleta2",
            "instalación incompleta: `kiro-cli chat` no abre (falta "
            "~/.local/bin/kiro-cli-chat); repárala con la receta oficial",
            "incomplete install: `kiro-cli chat` won't open (~/.local/bin/kiro-cli-chat "
            "is missing); repair it with the official recipe")
    except Exception:
        pass
    return {"why": why, "cask": _cask_of(exe), "detail": falta}


def _version(exe, runner=None):
    if gatekeeper_block(exe):              # `--version` también abriría el diálogo
        return None
    try:
        import engine_versions
        return engine_versions.parse(engine_versions.installed_version(exe, runner=runner))
    except Exception:
        return None


def status(exe_override=None, runner=None):
    """Estado honesto del motor (doctor / plan / harnesses.registry). Solo
    inspecciona: binario en PATH + `kiro-cli whoami` (sin tokens)."""
    exe = _exe(exe_override)
    if not exe:
        return {"engine": "kiro", "binary": BINARY, "binary_in_path": False,
                "session_active": False, "ready": False,
                "auth": "cuenta de Kiro vía `kiro-cli login`"}
    blk = gatekeeper_block(exe)
    if blk:
        return {"engine": "kiro", "binary": BINARY, "binary_in_path": True,
                "session_active": None, "ready": False, "gatekeeper": blk,
                "detail": blk["why"],
                "auth": "cuenta de Kiro vía `kiro-cli login`; WORKSPACE nunca ve el token"}
    rota = install_block(exe) if exe_override is None else None
    falta = (rota or {}).get("detail", "")
    active, kind = _whoami(exe, runner=runner)
    st = {"engine": "kiro", "binary": BINARY, "binary_in_path": True,
          "session_active": active, "account_type": kind, "install_block": rota,
          # ready = binario + cuenta (o desconocido: no se bloquea por una
          # lectura fallida; sí cuando Kiro dice que no hay cuenta).
          "ready": active is not False and not falta,
          "auth": "cuenta de Kiro vía `kiro-cli login` (Builder ID, Identity Center, "
                  "Google o GitHub); WORKSPACE nunca ve el token"}
    if falta:
        st["detail"] = falta
    elif active is False:
        st["detail"] = "sin sesión en Kiro: `kiro-cli login`"
    return st


def account_menu(active=None, exe=None):
    """«cuenta y proveedor» en Motores (engines_tui._account), según la sesión.

    Kiro NO tiene selector de proveedor ni de modelo fuera del chat
    (VERIFICADO 2.34.0, `kiro-cli --help-all` y `chat --help`): la cuenta ES el
    proveedor (Builder ID, Identity Center, Google, GitHub) y el modelo se
    elige dentro del chat con /model (o `chat.defaultModel`, config del socio
    que Workspace no escribe). Con sesión, `kiro-cli login` falla («Already
    logged in, please logout … first», rc 1): por eso no se corre a ciegas.
      · sin sesión (False) → None: Motores corre el login oficial;
      · con sesión o sin saber → {"model": "/model", "actions": [(clave, argv)]}:
        ver la cuenta (`whoami`, lo imprime Kiro), ver los modelos
        (`chat --list-models`, lectura), abrir Kiro (`chat` en una carpeta
        vacía) y cambiar de cuenta (`logout` + `login`, Motores lo confirma).
    Si la instalación está incompleta (cask sin abrir la app), lo que pasa
    por `kiro-cli-chat` no sirve: se omite y se avisa en `warn`."""
    if active is False:
        return None
    exe = exe or _exe()
    falta = install_problem(exe) if exe else ""
    acts = [("whoami", [BINARY, "whoami"])]
    if active is None:
        acts.append(("login", [BINARY, "login"]))
    if not falta:
        abrir = [BINARY, "chat"] + (["--trust-workspace"] if exe and _trust_flag_ok(exe, [])
                                    else [])
        acts += [("models", [BINARY, "chat", "--list-models"]), ("open", abrir)]
    acts.append(("switch", [[BINARY, "logout"], [BINARY, "login"]]))
    warn = ""
    if falta:
        try:
            import engine_gatekeeper as _gk
            warn = _gk.text(
                "motores.kiro.incompleta",
                "instalación incompleta: `kiro-cli chat` no abre hasta que corras una vez "
                "la app «Kiro CLI» (o reinstales con la receta oficial)",
                "incomplete install: `kiro-cli chat` won't open until you run the «Kiro "
                "CLI» app once (or reinstall with the official recipe)")
        except Exception:
            warn = falta
    return {"model": "/model", "actions": acts, "warn": warn}


# ── headless ────────────────────────────────────────────────────────────────
def _clean_text(out):
    return _ANSI.sub("", out or "").strip()


def run_turn(prompt, *, model=None, cwd=None, timeout=120, exe_override=None,
             runner=None, runner_turn=None, check_login=True):
    """UN turno HEADLESS: `kiro-cli chat --no-interactive --trust-tools=` con
    el mensaje por STDIN (doc oficial: sin argumento posicional, Kiro lee la
    entrada estándar completa). `--trust-tools=` no pre-aprueba ninguna
    herramienta: sin persona que conteste, lo que pediría permiso se niega.
    Devuelve (ok, texto). `runner`/`exe_override` son knobs de test (`runner`
    sirve a la consulta de cuenta y al turno; `runner_turn`, solo al turno:
    headless antepone el sandbox del SO).

    Antes se consulta la cuenta: sin ella, `kiro-cli chat` abre el NAVEGADOR
    para iniciar sesión aunque sea sin ventana (VERIFICADO 2.34.0). Con una
    credencial mala, Kiro imprime «Error: …» y no termina: el timeout corta."""
    exe = _exe(exe_override)
    if not exe:
        return False, "kiro-cli no está en PATH"
    blk = gatekeeper_block(exe)
    if blk:
        return False, "kiro: " + blk["why"]
    if check_login and _whoami(exe, runner=runner)[0] is False:
        return False, "kiro: sin sesión — inicia con `kiro-cli login`"
    cmd = [exe, "chat", "--no-interactive", "--trust-tools=", "--wrap", "never"]
    if model:
        cmd += ["--model", model]
    try:
        if cwd:
            os.makedirs(cwd, exist_ok=True)
        import secret_store
        env = secret_store.engine_env()   # el motor no hereda la bóveda
        env["WORKSPACE_NO_AUTOUPDATE"] = "1"
        turn = runner_turn or runner
        if turn is not None:
            r = turn(cmd, cwd=cwd or None, env=env, timeout=timeout,
                     input=prompt or "")
        else:
            r = arbol_procesos.run(cmd, cwd=cwd or None, env=env, timeout=timeout,
                                   input=(prompt or "").encode("utf-8"),
                               capture_output=True)
        rc = getattr(r, "returncode", 1)
        raw_out = getattr(r, "stdout", b"") or b""
        out = raw_out.decode("utf-8", "replace") if isinstance(raw_out, bytes) \
            else str(raw_out)
        raw = getattr(r, "stderr", b"") or b""
        err = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else str(raw)
        text = _clean_text(out)
        if rc != 0 or text.startswith("Error:") or _clean_text(err).startswith("Error:"):
            return False, "kiro chat exit %d: %s" % (rc, (_clean_text(err) or text)[:300])
        return True, text
    except subprocess.TimeoutExpired:
        return False, "kiro chat: timeout tras %ss" % timeout
    except OSError as e:
        return False, "kiro chat: no pude preparar la corrida: %s" % e
    except Exception as e:
        return False, "kiro chat: fallo al invocar: %s" % e


# ── sesiones (archivos de Kiro V3 y V2; solo lectura) ───────────────────────
def _valid_session_id(sid):
    """Id de una sesión de Kiro: V3 `sess_<uuid>` o V2 el uuid pelado."""
    sid = str(sid or "")
    return bool(_SID.fullmatch(sid) or _V2_SID.fullmatch(sid))


def _is_v2_id(sid):
    return bool(_V2_SID.fullmatch(str(sid or "")))


def _kiro_dir(home=None):
    """Carpeta global de Kiro: `~/.kiro`, o la de KIRO_HOME (doc «configuration
    scopes», https://kiro.dev/docs/configuration/: una ruta ABSOLUTA; si es
    relativa, la raíz del disco, el HOME o una carpeta que lo contiene, Kiro
    usa `~/.kiro`). `home`: el HOME (el desinstalador pasa el suyo)."""
    home = home or os.path.expanduser("~")
    kh = os.environ.get("KIRO_HOME", "").strip()
    if kh and os.path.isabs(kh):
        p = os.path.normcase(os.path.abspath(kh)).rstrip("\\/")
        h = os.path.normcase(os.path.abspath(home)).rstrip("\\/")
        raiz = not p or os.path.dirname(p) == p or p.endswith(":")
        if not raiz and p != h and not (h + os.sep).startswith(p + os.sep):
            return os.path.abspath(kh)
    return os.path.join(home, ".kiro")


def sessions_root():
    return os.path.join(_kiro_dir(), "sessions")


def _hashes(brain):
    """Huellas de carpeta con las que Kiro guarda las sesiones de `brain`:
    sha256 de la ruta, 16 hex (VERIFICADO 2.34.0). Se prueban la ruta real y
    la absoluta (un enlace simbólico cambia la que ve Kiro)."""
    out = []
    for p in (os.path.realpath(str(brain)), os.path.abspath(str(brain))):
        h = hashlib.sha256(p.encode("utf-8")).hexdigest()[:16]
        if h not in out:
            out.append(h)
    return out


def _norm(p):
    return os.path.normcase(os.path.realpath(str(p or "")))


def _read_json(path):
    try:
        with open(path, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _iso_epoch(ts):
    try:
        import datetime
        return datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return None


def _of_brain(meta, brain):
    """¿La sesión es de este cerebro? V3: `workspacePaths`/`rootPaths`; V2:
    `cwd`."""
    want = _norm(brain)
    for k in ("workspacePaths", "rootPaths"):
        for p in (meta or {}).get(k) or []:
            if isinstance(p, str) and _norm(p) == want:
                return True
    cwd = (meta or {}).get("cwd")
    return isinstance(cwd, str) and bool(cwd) and _norm(cwd) == want


def _v2_dir(root=None):
    """Carpeta de las sesiones V2 (`<sessions>/cli/`, una por archivo)."""
    return os.path.join(root or sessions_root(), "cli")


def _list_v3(brain, root=None, since=None):
    root = root or sessions_root()
    dirs = [os.path.join(root, h) for h in _hashes(brain)
            if os.path.isdir(os.path.join(root, h))]
    if not dirs and since is not None:
        try:
            dirs = [d for d in glob.glob(os.path.join(root, "*"))
                    if os.path.isdir(d) and os.path.getmtime(d) >= since - 5]
        except OSError:
            dirs = []
    out = []
    for d in dirs:
        for sd in glob.glob(os.path.join(d, "sess_*")):
            sid = os.path.basename(sd)
            if not _SID.fullmatch(sid):
                continue
            meta_path = os.path.join(sd, "session.json")
            meta = _read_json(meta_path)
            if not meta or not _of_brain(meta, brain):
                continue
            created = _iso_epoch(meta.get("createdAt"))
            if created is None:
                try:
                    created = os.path.getmtime(meta_path)
                except OSError:
                    created = 0.0
            out.append({"id": sid, "created": created, "dir": sd, "store": "v3",
                        "meta": meta_path, "messages": os.path.join(sd, "messages.jsonl"),
                        "title": str(meta.get("title") or "")})
    return out


def _list_v2(brain, root=None, since=None):
    """Sesiones V2 de este cerebro. Con `since`, solo las que cambiaron desde
    entonces (la carpeta es de TODOS los proyectos: no se abren las viejas)."""
    d = _v2_dir(root)
    try:
        names = os.listdir(d)
    except OSError:
        return []
    out = []
    for n in names:
        sid = n[:-5] if n.endswith(".json") else ""
        if not _is_v2_id(sid):
            continue
        meta_path = os.path.join(d, n)
        try:
            mtime = os.path.getmtime(meta_path)
        except OSError:
            continue
        if since is not None and mtime < since - 5:
            continue
        meta = _read_json(meta_path)
        if not meta or not _of_brain(meta, brain):
            continue
        created = _iso_epoch(meta.get("created_at"))
        out.append({"id": sid, "created": mtime if created is None else created, "dir": d,
                    "store": "v2", "meta": meta_path,
                    "messages": os.path.join(d, sid + ".jsonl"),
                    "title": str(meta.get("title") or "")})
    return out


def list_sessions(brain, root=None, since=None):
    """[{id, created, dir, store, meta, messages, title}] de las sesiones de
    este cerebro, leyendo sus archivos (jamás el CLI). V3: primero las
    carpetas de su huella; si no hay ninguna (otra forma de ruta, otro
    sistema), las carpetas que cambiaron desde `since`. V2: los `.json` de
    `sessions/cli/` con el `cwd` del cerebro. Falla-suave → []."""
    return _list_v3(brain, root=root, since=since) + _list_v2(brain, root=root, since=since)


def known_ids(brain, root=None):
    """Lo que ya había al abrir una pestaña nueva (`before` de
    find_new_session): las sesiones V3 de este cerebro. Las V2 no se listan
    (habría que abrir las de todos los proyectos): una V2 vieja ya queda fuera
    por su `created_at` anterior a t0, y dos pestañas a la vez las separa la
    marca."""
    return [s["id"] for s in _list_v3(brain, root=root)]


def session_files(brain, sid, root=None):
    """{store, meta, messages[, dir]} de la sesión `sid` de este cerebro, o
    None si no existe (o es de otro cerebro)."""
    sid = str(sid or "")
    root = root or sessions_root()
    if _is_v2_id(sid):
        d = _v2_dir(root)
        meta_path = os.path.join(d, sid + ".json")
        meta = _read_json(meta_path)
        if meta and str(meta.get("session_id") or sid) == sid and _of_brain(meta, brain):
            return {"store": "v2", "meta": meta_path,
                    "messages": os.path.join(d, sid + ".jsonl")}
        return None
    if not _SID.fullmatch(sid):
        return None
    cands = [os.path.join(root, h, sid) for h in _hashes(brain)]
    try:
        cands += [d for d in glob.glob(os.path.join(root, "*", sid)) if d not in cands]
    except OSError:
        pass
    for sd in cands:
        meta = _read_json(os.path.join(sd, "session.json"))
        if meta and str(meta.get("id") or sid) == sid and _of_brain(meta, brain):
            return {"store": "v3", "dir": sd, "meta": os.path.join(sd, "session.json"),
                    "messages": os.path.join(sd, "messages.jsonl")}
    return None


def session_dir(brain, sid, root=None):
    """Dónde vive la sesión `sid` de este cerebro ('' si no existe): la
    carpeta de una V3 o el `.json` de una V2."""
    f = session_files(brain, sid, root=root)
    return (f.get("dir") or f["meta"]) if f else ""


def _first_user_text(path):
    """Texto del primer mensaje del socio de una sesión, de su `.jsonl` (V3
    `payload.type == "user"`, V2 `kind == "Prompt"`). Acepta la carpeta V3."""
    if os.path.isdir(path):
        path = os.path.join(path, "messages.jsonl")
    try:
        with open(path, encoding="utf-8-sig", errors="replace") as fh:
            for ln in fh:
                try:
                    row = json.loads(ln)
                except ValueError:
                    continue
                if not isinstance(row, dict):
                    continue
                p = row.get("payload")
                if isinstance(p, dict) and p.get("type") == "user":
                    c = p.get("content")
                    if isinstance(c, str):
                        return c
                    if isinstance(c, list):
                        return " ".join(str(x.get("text") or "") for x in c
                                        if isinstance(x, dict))
                    return ""
                if row.get("kind") == "Prompt" and isinstance(row.get("data"), dict):
                    import neutral_transcript as nt
                    return nt._kiro_v2_text(row["data"].get("content"))
    except OSError:
        pass
    return ""


def find_new_session(brain, find, root=None):
    """La sesión que creó ESTA pestaña. `find` = {t0, before, marker}:
    candidatas = ids que no estaban antes de abrir, creados después de t0; de
    ellas, la que trae la marca de la pestaña en su primer mensaje (también si
    es una sola: si esta pestaña no llegó a crear la suya, no se apropia la de
    otra). Sin marca, solo una candidata única. Ambigua o ninguna → ''."""
    t0 = float((find or {}).get("t0") or 0)
    before = set((find or {}).get("before") or [])
    cands = [s for s in list_sessions(brain, root=root, since=t0)
             if s["id"] not in before and float(s.get("created") or 0) >= t0 - 5]
    if not cands:
        return ""
    marker = str((find or {}).get("marker") or "")
    if not marker:
        return cands[0]["id"] if len(cands) == 1 else ""
    hits = [s["id"] for s in cands if marker in _first_user_text(s["messages"])]
    return hits[0] if len(hits) == 1 else ""


def session_marker(cfg, tab_name):
    """Marca de la pestaña en el mensaje de arranque: con dos pestañas
    abriendo a la vez, distingue cuál sesión es de cuál. La MISMA de opencode
    (saneada en Windows, donde viaja como argumento); la captura busca esta
    misma marca."""
    from engines.opencode import session_marker as _marca
    return _marca(cfg, tab_name)


# ═══════════════════════════════════════════════════════════════════════════
# inject_context — identidad del agente vía AGENTS.md (contrato harness-os §3)
# ═══════════════════════════════════════════════════════════════════════════
# Kiro lee AGENTS.md de la raíz del proyecto (siempre incluido; doc oficial
# «steering»). Se reusa el MISMO puntero que codex/opencode/openclaw/hermes
# (misma marca WORKSPACE:GENERATED, mismo bloque de pestaña): si el socio
# alterna motores en el mismo cerebro, cada launch re-sincroniza el puntero
# idempotente. Nada en `.kiro/steering/` del cerebro (sería paralelo a la
# identidad común): `.kiro` es nombre reservado en la raíz.
def inject_context(cfg, session_context=""):
    """inject_context de Kiro (ver engines/opencode.inject_agents_md)."""
    from engines import opencode
    return opencode.inject_agents_md(cfg, session_context=session_context, engine="kiro")


def _identity_doc(cfg):
    from engines import opencode
    return opencode._identity_doc(cfg)


# ── argv interactivo ────────────────────────────────────────────────────────
#: Opciones con las que el socio elige sesión a mano: su elección gana.
_SESSION_FLAGS = ("-r", "--resume", "--resume-id", "--resume-picker", "--list",
                  "--sessions")
#: Opciones con las que el socio elige otro motor de Kiro (V1/V2): ahí
#: `--trust-workspace` (solo V3) no se agrega.
_ENGINE_FLAGS = ("--v2", "--legacy-ui", "--classic", "--agent-engine")


def _has_flag(passthrough, flags):
    for a in passthrough or []:
        a = str(a)
        if a in flags or any(a.startswith(f + "=") for f in flags if f.startswith("--")):
            return True
    return False


def _has_session_flag(passthrough):
    return _has_flag(passthrough, _SESSION_FLAGS)


def _session_from_passthrough(passthrough):
    """El id de `--resume-id X` / `--resume-id=X` que pasó el socio, o ''."""
    args = [str(a) for a in passthrough or []]
    for i, a in enumerate(args):
        if a.startswith("--resume-id="):
            sid = a.split("=", 1)[1]
        elif a == "--resume-id" and i + 1 < len(args):
            sid = args[i + 1]
        else:
            continue
        return sid if _valid_session_id(sid) else ""
    return ""


def _trust_flag_ok(exe, passthrough):
    """¿Va `--trust-workspace`? Solo con 2.34+ (o versión ilegible: el flag es
    de la línea verificada), sin opt-out y sin que el socio pida V1/V2."""
    if os.environ.get(_NO_AUTOTRUST_ENV, "").strip():
        return False
    if _has_flag(passthrough, _ENGINE_FLAGS + ("--trust-workspace",)):
        return False
    v = _version(exe) if exe else None
    return v is None or tuple(v[:2]) >= TRUST_FLAG_SINCE


def _interactive_argv(passthrough, session_id="", trust=True, boot="", extra=()):
    """argv DESPUÉS de `kiro-cli`: `chat` [+ `--trust-workspace`] [+ `extra`:
    el agente de la memoria, memoria_mcp] [+ `--resume-id <id>`] +
    passthrough del socio [+ mensaje de arranque posicional]. El harness NO
    fija modelo; lo que pase el socio va tal cual y gana."""
    args = list(passthrough or [])
    argv = ["chat"]
    if trust:
        argv.append("--trust-workspace")
    argv += list(extra or ())
    if session_id and not _has_session_flag(args):
        argv += ["--resume-id", session_id]
    argv += args
    if boot:
        argv.append(boot)
    return argv


# ── barra: lo que prendió una versión anterior (solo para deshacerlo) ───────
def settings_path(home=None):
    """Config GLOBAL de Kiro (`~/.kiro/settings/cli.json`, doc «settings
    reference»). Workspace ya no la escribe."""
    return os.path.join(_kiro_dir(home), "settings", "cli.json")


def _state_path(home=None):
    import paths
    return os.path.join(paths.state_dir(home), _STATUSLINE_STATE)


def _read_state(home=None):
    try:
        return _read_obj(_state_path(home))
    except (OSError, ValueError):
        return {}


def statusline_de_workspace(home=None):
    """{config de Kiro: {clave: [segmentos]}} que prendió una versión anterior
    de Workspace (no lo que ya tenía el socio), según SU propio registro en el
    estado de Workspace: lo único que la migración y el desinstalador revierten."""
    out = {}
    pr = _read_state(home).get("prendidos")
    if not isinstance(pr, dict):
        return out
    for sp, keys in pr.items():
        if not isinstance(keys, dict):
            continue
        segs = {str(k): [str(x) for x in v if isinstance(x, str)]
                for k, v in keys.items() if isinstance(k, str) and isinstance(v, list)}
        segs = {k: v for k, v in segs.items() if v}
        if segs:
            out[str(sp)] = segs
    return out


def olvidar_statusline(sp, home=None):
    """Quita `sp` de lo anotado como «prendido por Workspace» (ya se revirtió).
    Lo demás del registro queda: con él, una versión anterior (si el socio
    vuelve a ella) no vuelve a prender nada. Escritura atómica. → bool."""
    try:
        st = _read_state(home)
        pr = st.get("prendidos")
        if not isinstance(pr, dict) or sp not in pr:
            return True
        pr = {k: v for k, v in pr.items() if k != sp}
        if pr:
            st["prendidos"] = pr
        else:
            st.pop("prendidos", None)
        path = _state_path(home)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(st, fh, indent=1)
        os.replace(tmp, path)
        return True
    except (OSError, ValueError, TypeError):
        return False


def clean_statusline(data, prendidos):
    """(dict nuevo, ¿quitó?) de la config de Kiro sin los segmentos que
    prendió Workspace (`prendidos` = {clave: [segmentos]}) y que siguen
    prendidos; lo demás (lo del socio, otras claves) queda. Una clave que
    queda vacía se quita (vacía = de fábrica, como la deja Kiro)."""
    if not isinstance(data, dict):
        return data, False
    new, quito = dict(data), False
    for key, segs in (prendidos or {}).items():
        obj = new.get(key)
        if not isinstance(obj, dict):
            continue
        resto = {s: v for s, v in obj.items() if not (s in segs and v is True)}
        if resto == obj:
            continue
        quito = True
        if resto:
            new[key] = resto
        else:
            del new[key]
    return new, quito


def _read_obj(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, dict):
        raise ValueError("not an object")
    return data


def _autonomy(cfg):
    """Autonomía del agente (contrato común, engines/_ui.autonomy): «brain»
    (la de fábrica) o «ask». Falla-suave → «ask» (sin permisos de más)."""
    try:
        from engines import _ui
        return _ui.autonomy(cfg)
    except Exception:
        return "ask"


def _banner(cfg):
    """Arranque visible mínimo (Windows-safe: sin glifos 0x2600–0x27BF)."""
    name = str(cfg.get("display") or cfg.get("name", "agente")).upper()
    C, D = "\033[38;5;170m", "\033[38;5;240m"
    try:
        from engines import _ui
        C, D = _ui.theme_cols(C, D)
    except Exception:
        pass
    R = "\033[0m"; B = "\033[1m"
    bar = C + "═" * 52 + R
    try:
        sys.stdout.write("\033[2J\033[3J\033[H")
        print("\n  %s" % bar)
        print("    %s%s%s%s   %svía Kiro%s" % (B, C, name, R, D, R))
        print("  %s\n" % bar)
        sys.stdout.flush()
    except Exception:
        pass


def _offer_login(exe):
    """En una terminal: ¿iniciar sesión en Kiro ahora (`kiro-cli login`, su
    flujo oficial)? True si se abrió. Sin terminal o «no» → False."""
    try:
        if not (sys.stdin.isatty() and sys.stdout.isatty()):
            return False
        ans = input("  ¿Inicias sesión ahora? Se abre el inicio de sesión oficial de Kiro [S/n] ")
    except (EOFError, KeyboardInterrupt):
        return False
    if ans.strip().lower() in ("n", "no"):
        return False
    try:
        subprocess.call([exe, "login"], env=_env_motor())
    except Exception:
        return False
    return True


def _login_gate(exe):
    """Sin cuenta, `kiro-cli chat` abre el navegador por su cuenta dentro de la
    pestaña. Se ofrece iniciar sesión AHORA y, si sigue faltando, no se abre a
    ciegas salvo que el socio lo pida. True = abrir la pestaña."""
    if _whoami(exe)[0] is not False:
        return True
    print("WORKSPACE: Kiro no tiene una sesión iniciada.")
    if _offer_login(exe) and _whoami(exe)[0] is not False:
        return True
    print("  Sin sesión, Kiro abre su propio inicio de sesión en el navegador. Inicia "
          "sesión en Motores › Kiro › cuenta (o `kiro-cli login`).")
    try:
        import engine_versions as _EV
        return _EV.allow_anyway()
    except Exception:
        return True


def launch(cfg, passthrough, *, plan=False, preselect=None, show_banner=True):
    """Arranca un agente EN KIRO (interactivo). Delega al wrapper neutral de
    interactive.py (session_start → `kiro-cli chat` → session_end). plan=True
    NO lanza: imprime el wiring + chequeos."""
    brain = cfg.get("_brain", "")
    exe = _exe()

    if plan:
        line = "─" * 66
        print(line)
        print("  WORKSPACE · plan de arranque — motor KIRO — agente: %s"
              % cfg.get("display", cfg.get("name")))
        print(line)
        print("  motor       : kiro  (CLI oficial `kiro-cli` de AWS; cuenta del socio por "
              "`kiro-cli login`; WORKSPACE nunca ve el token)")
        print("  modelo      : lo elige el SOCIO dentro de Kiro (Workspace no pasa --model)")
        print("  cerebro     : %s" % brain)
        print("  identidad   : AGENTS.md puntero → %s (inject_context; marca "
              "WORKSPACE:GENERATED compartida con codex/opencode)" % _identity_doc(cfg))
        print("  pestañas    : picker compartido + registro neutral — Kiro crea la sesión, "
              "se ata al cerrar y se retoma con `--resume-id`; memoria de la pestaña "
              "INVISIBLE en el AGENTS.md")
        print("  confianza   : `--trust-workspace` (solo esta carpeta, solo este arranque, "
              "no guarda nada)")
        try:
            import memoria_mcp
            print("  memoria     : " + memoria_mcp.plan_line(
                "kiro", brain, passthrough, _version(exe) if exe else None,
                autonomia=_autonomy(cfg)))
        except Exception:
            pass
        print("  barra       : la nativa de Kiro, sin tocar (uso y créditos se prenden en "
              "su /settings display)")
        print("  config      : solo en el cerebro (.kiro/agents/workspace.json); nada en "
              "~/.kiro")
        print("  sesiones    : ~/.kiro/sessions/cli/<id>.jsonl (V2, el chat por defecto "
              "desde la 2.35) o ~/.kiro/sessions/<huella>/sess_<id>/ (V3); captura al "
              "cerrar: copia legible")
        print("  flujo       : pestaña → inject_context → banner → "
              "interactive.run_official_cli_interactive('kiro') → kiro-cli chat")
        print(line)
        print("  [%s] binario kiro-cli en PATH: %s"
              % ("✓" if exe else "✗ FALTA", exe or "(no está — Motores › Kiro › instalar)"))
        blk = gatekeeper_block(exe) if exe else None
        if blk:
            print("  [✗] macOS: %s (no se ejecuta: Motores › Kiro › reinstalar)" % blk["why"])
        elif exe:
            try:
                import engine_versions
                ver = engine_versions.installed_version(exe) or "?"
            except Exception:
                ver = "?"
            print("  [✓] versión: %s" % ver)
            falta = install_problem(exe)
            if falta:
                print("  [✗] instalación: %s" % falta)
        print("  [%s] cerebro: %s"
              % ("✓" if brain and os.path.isdir(brain) else "✗ FALTA", brain))
        print(line)
        return

    if not exe:
        print("WORKSPACE: kiro-cli no está en PATH — instálalo (Motores › Kiro › instalar) "
              "e inicia sesión con `kiro-cli login`.")
        sys.exit(1)
    blk = gatekeeper_block(exe)
    if blk:
        # Ejecutarlo abriría el diálogo de macOS (y volvería en cada llamada).
        print("WORKSPACE: Kiro — %s. Motores › Kiro › reinstalar." % blk["why"])
        sys.exit(1)
    falta = install_problem(exe)
    if falta:
        import engine_versions
        print("WORKSPACE: " + falta)
        if not engine_versions.allow_anyway():
            sys.exit(1)
    if not _login_gate(exe):
        sys.exit(1)

    # El agente `workspace` del cerebro (por corrida), antes del bloque de la
    # pestaña (sus instrucciones nombran la herramienta solo si quedó lista):
    # la memoria sin pedir permiso y, con autonomía «brain», escribir en el
    # cerebro sin preguntar. Falla-suave: [] → `workspace memoria` pidiendo
    # permiso y Kiro preguntando por cada escritura, como antes.
    try:
        import memoria_mcp
        extra = memoria_mcp.preparar("kiro", brain=brain, exe=exe, passthrough=passthrough,
                                     version=_version(exe), autonomia=_autonomy(cfg))
    except Exception:
        extra = []

    # Pestañas NEUTRALES (sessions_registry): el MISMO picker que los demás
    # motores. El id de Kiro de la pestaña sale del registro; si no hay
    # (pestaña nueva), Kiro crea la sesión y la captura la ata al cerrar.
    tab, session_id, session_blk = None, "", ""
    agent = str(cfg.get("name") or "")
    cfg.setdefault("_engine", "kiro")
    os.environ["WORKSPACE_ENGINE_LABEL"] = "Kiro · modelo de tu config"
    try:
        from engines import _ui
        import sessions_registry as _reg
        if not (preselect and preselect.get("wid")):
            from engines import claude_code as _cc0
            _cc0.session_preflight(cfg, "kiro")
        tab = _ui.pick_tab(cfg, preselect=preselect)
        if not tab:
            from engines import claude_code as _cc
            _cc.warn_no_tab(_cc.LAST_PICK_ERROR)
        if tab:
            wid, wname = tab
            _ui.export_tab_env(cfg, wid, wname)
            _reg.ensure_tab(brain, agent, wname, claude_wid=wid)
            session_id = _reg.resume_id(brain, agent, wname, "kiro") or ""
            if session_id and not session_dir(brain, session_id):
                # Atada pero ya no existe (borrada en Kiro, otra máquina): con
                # un id que no existe, Kiro se queda en «Launching…». Se suelta
                # y la pestaña abre como nueva.
                if _valid_session_id(session_id):
                    _reg.unbind(brain, agent, wname, "kiro", session_id)
                session_id = ""
            session_blk = _reg.session_doc_block(brain, wname, engine="kiro",
                                                 resumed=bool(session_id))
    except Exception as e:
        tab, session_id, session_blk = None, "", ""
        try:
            from engines import claude_code as _cc
            err = "no pude preparar la pestaña (%s: %s)" % (type(e).__name__, e)
            _cc._session_log(cfg, "kiro", err)
            _cc.warn_no_tab(err)
        except Exception:
            pass

    resumed = bool(session_id)
    find = None
    if _has_session_flag(passthrough):
        session_id = ""                    # el socio eligió sesión a mano
    elif tab and not session_id:
        find = {"t0": time.time(),
                "before": known_ids(brain),
                "marker": session_marker(cfg, tab[1])}

    first_prompt = ""
    inj = inject_context(cfg, session_context=session_blk)
    if not inj.get("ok") and inj.get("detail"):
        print("WORKSPACE: identidad NO inyectada (%s) — Kiro arrancará genérico."
              % inj["detail"])
    if tab and session_blk and inj.get("action") == "custom" \
            and not inj.get("session") and not resumed:
        try:
            import sessions_registry as _reg
            first_prompt = _reg.first_prompt_context(brain, tab[1], engine="kiro")
            if os.name == "nt":
                import memoria
                first_prompt = memoria.argv_seguro(first_prompt)
            print("WORKSPACE: no pude anexar la memoria al AGENTS.md del socio — irá en "
                  "el primer mensaje (visible).")
        except Exception:
            first_prompt = ""

    if show_banner:
        try:
            from engines import _ui
            _ui.show_brain_banner(cfg)
        except Exception:
            _banner(cfg)
    # Lo que la herramienta de memoria rehízo en el cerebro (alguien lo había
    # cambiado): una línea cada uno, DESPUÉS del banner (que limpia la pantalla).
    try:
        import memoria_mcp
        for aviso in memoria_mcp.avisos():
            print(aviso)
    except Exception:
        pass

    # Arranque del cerebro como codex/opencode: un launch PELADO de una sesión
    # NUEVA arranca solo (mensaje posicional: VERIFICADO, Kiro lo envía al
    # abrir); al retomar no se inyecta nada. Lo que pase el socio manda.
    boot = first_prompt or ("" if (passthrough or resumed) else
                            "Lee %s e inicia el cerebro. Al terminar, confirma en una "
                            "línea breve." % _identity_doc(cfg))
    if boot and os.name == "nt":
        import memoria
        boot = memoria.argv_seguro(boot)
    if boot and find:
        boot += " (%s)" % find["marker"]
    argv = _interactive_argv(passthrough, session_id=session_id,
                             trust=_trust_flag_ok(exe, passthrough), boot=boot, extra=extra)

    real_sid = session_id or _session_from_passthrough(passthrough)
    if real_sid:
        os.environ["WORKSPACE_KIRO_SESSION"] = real_sid
    else:
        os.environ.pop("WORKSPACE_KIRO_SESSION", None)
    if find:
        os.environ["WORKSPACE_KIRO_FIND"] = json.dumps(find)
    else:
        os.environ.pop("WORKSPACE_KIRO_FIND", None)

    _doc_dirty = []

    def _ctx_sink(ctx):
        # Contexto neutral de arranque → INVISIBLE al AGENTS.md junto con el
        # bloque de la pestaña; solo si no se pudo escribir, se imprime.
        try:
            merged = "\n\n".join(p for p in (session_blk, (ctx or "").strip()) if p)
            if not merged:
                return
            r = inject_context(cfg, session_context=merged)
            if r.get("ok") and (r.get("action") != "custom"
                                or r.get("session") == "appended"):
                _doc_dirty.append(True)
            elif (ctx or "").strip():
                print("[WORKSPACE · contexto de arranque]\n%s\n" % ctx.strip())
        except Exception:
            pass

    try:
        import interactive
        rc = interactive.run_official_cli_interactive(
            "kiro", brain=brain or None, argv=argv, context_sink=_ctx_sink,
            pending={"tab": tab[1] if tab else "", "agent": agent, "resume_id": session_id})
    except Exception as e:
        print("WORKSPACE: no pude lanzar Kiro interactivo (%s: %s)"
              % (type(e).__name__, e))
        sys.exit(1)
    found = os.environ.get("WORKSPACE_KIRO_SESSION", "")
    if find and tab and _valid_session_id(found):
        try:
            import sessions_registry as _reg
            _reg.bind(brain, agent, tab[1], "kiro", found)
        except Exception:
            pass
    # Limpieza (igual que opencode): el bloque de la pestaña era de ESTA
    # corrida; si otra pestaña sigue viva en el cerebro, el bloque es el suyo.
    try:
        import pending_runs
        otra = bool(brain) and pending_runs.live_in_brain(brain, exclude=pending_runs.current())
    except Exception:
        otra = False
    if (session_blk or _doc_dirty) and not otra:
        try:
            inject_context(cfg)
        except Exception:
            pass
    if not otra and brain:
        try:
            import pending_runs
            pending_runs.clean_docs("kiro", brain)
        except Exception:
            pass
    try:
        import pending_runs
        pending_runs.done()
    except Exception:
        pass
    sys.exit(rc if isinstance(rc, int) else 0)


def pick(cfg):
    """El picker de pestañas COMPARTIDO (registro neutral): la misma elección
    cruda que claude_code.pick — lo usa el hub tmux (mux.py). Falla-suave → ''."""
    try:
        from engines import _ui
        cfg.setdefault("_engine", "kiro")
        return _ui.pick_keep_label(cfg, "Kiro · modelo de tu config")
    except Exception:
        return ""
