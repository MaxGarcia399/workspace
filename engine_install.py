#!/usr/bin/env python3
"""WORKSPACE · engine_install — instalación OFICIAL de motores por OS (U02/Z02).

Una receta por (motor, plataforma): comando del instalador oficial, URL de la
fuente oficial y prerequisitos. La UI la muestra ANTES de confirmar; nada se
ejecuta aquí (el driver corre el comando en la terminal del socio con su
confirmación). En Windows, los instaladores en PowerShell no se corren como
one-liner `irm … | iex`: Workspace baja el script oficial y el driver corre el
ARCHIVO (ver _ps1/runnable). Fuentes verificadas 2026-10-10:
  · Claude Code — https://code.claude.com/docs/en/setup : instalador nativo
    recomendado (curl … install.sh | bash · irm … install.ps1 | iex); npm
    sigue soportado pero exige Node.js 22+ (alternativa, no default).
  · Codex CLI — https://learn.chatgpt.com/docs/codex/cli : instalador
    standalone POSIX (curl … chatgpt.com/codex/install.sh | sh). En Windows la
    doc no publica comando nativo → npm (@openai/codex), que exige npm.
  · Antigravity CLI — https://www.antigravity.google/docs/cli/install/ :
    scripts oficiales separados para POSIX y PowerShell.
  · Hermes Agent — https://hermes-agent.nousresearch.com/docs/getting-started/
    installation (2026-10-15): install.sh (POSIX) e install.ps1 (PowerShell);
    el binario queda en ~/.local/bin (POSIX) o %LOCALAPPDATA%\\hermes\\bin.
  · GitHub Copilot CLI — https://docs.github.com/en/copilot/how-tos/copilot-cli/
    set-up-copilot-cli/install-copilot-cli (2026-10-28): npm `@github/copilot`
    (Node.js 22+) en macOS/Linux y WinGet `GitHub.Copilot` en Windows. El cask
    de Homebrew NO (Gatekeeper; ver la receta).
Antes de cada release: re-verificar estas URLs/comandos (pueden cambiar).

API: recipe(engine, platform=None) → dict | None  (con "aviso": la línea que
     se dice ANTES de instalar si el instalador oficial abre un diálogo)
     missing_prereqs(recipe) → [str]   (qué falta para que el comando corra)
     describe(engine, platform=None) → líneas legibles (fuente/comando/prereqs)
     shown(cmd) → [str]   (cómo se le muestra un comando antes de correrlo)
     runnable(cmd) → contexto con el argv que de verdad corre (Windows: baja
                     el instalador oficial a un .ps1 temporal y lo borra)
"""
import contextlib
import os
import shutil
import sys
import tempfile

VERIFIED = "2026-10-10"

#: Instaladores OFICIALES en PowerShell (Windows), SIN cradle. VERIFICADO
#: 2026-11-05: el one-liner del proveedor (`irm <url> | iex` y sus variantes
#: `iex (irm …)` y `& ([scriptblock]::Create((irm …)))`) como LÍNEA DE COMANDOS
#: de un `powershell -Command` que lanza Workspace lo bloquea Microsoft
#: Defender (protección en tiempo real por defecto, ML en la nube, detección
#: FastPath: «Trojan:Win32/Commando.C!ml», evento 1116 con la CmdLine): el
#: proceso no llega a crearse (WinError 5, «Acceso denegado») y el socio ve una
#: alerta de troyano a nombre de Workspace. Visto con Kiro y Cursor; Claude
#: Code, Codex, Antigravity, OpenClaw y Hermes son la misma clase. Lo normal de
#: un instalador: Workspace baja el script oficial por HTTPS (fetch), lo deja
#: en un .ps1 temporal, lo corre con `-File` (Defender escanea el archivo y
#: AMSI el script, como siempre; nada se esconde) y lo borra (runnable). La
#: receta guarda la URL en el lugar del archivo: corrida tal cual, PowerShell
#: no baja nada. `manual` = el one-liner del proveedor, solo para mostrarlo.
PS1_HEAD = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File"]
#: Cómo se muestra el .ps1 temporal antes de bajarlo (mkstemp le pone el resto).
PS1_SHOWN = "%TEMP%\\workspace-install-….ps1"
FETCH_TIMEOUT = 30                   # segundos por operación de red
FETCH_MAX = 2 * 1024 * 1024          # los install.ps1 oficiales pesan KB
#: Mismos tokens de plataforma que el one-liner oficial (`irm` de Windows
#: PowerShell 5.1) y el nombre de Workspace: el servidor entrega lo mismo.
FETCH_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) WindowsPowerShell/5.1 Workspace-Install/1"


def _ps1(url, manual, args=(), note=""):
    """Receta win32 «bajar y correr»: PS1_HEAD + URL (lugar del archivo) +
    los argumentos que el one-liner oficial le pasa al script."""
    p = {"cmd": PS1_HEAD + [url] + list(args), "needs": ["powershell"], "manual": manual}
    if note:
        p["note"] = note
    return p


_RECIPES = {
    "claude-code": {
        "source": "https://code.claude.com/docs/en/setup",
        "binary": "claude",
        "win32": _ps1("https://claude.ai/install.ps1",
                      "irm https://claude.ai/install.ps1 | iex",
                      note="Git for Windows es opcional (habilita la herramienta Bash)."),
        "posix": {"cmd": ["bash", "-c", "curl -fsSL https://claude.ai/install.sh | bash"],
                  "needs": ["bash", "curl"]},
        "alt": {"cmd": ["npm", "install", "-g", "@anthropic-ai/claude-code"],
                "needs": ["npm"], "note": "requiere Node.js 22+; sin sudo"},
    },
    "codex": {
        "source": "https://learn.chatgpt.com/docs/codex/cli",
        "binary": "codex",
        # Instalador OFICIAL de Windows (VERIFICADO 2026-10-16: chatgpt.com/codex/
        # install.ps1 responde y deja codex.exe; npm dejaba codex.cmd).
        "win32": _ps1("https://chatgpt.com/codex/install.ps1",
                      "irm https://chatgpt.com/codex/install.ps1 | iex",
                      note="instalador oficial de OpenAI para Windows; alternativa: "
                           "npm install -g @openai/codex (requiere Node.js)."),
        "posix": {"cmd": ["sh", "-c", "curl -fsSL https://chatgpt.com/codex/install.sh | sh"],
                  "needs": ["sh", "curl"]},
        "alt": {"cmd": ["npm", "install", "-g", "@openai/codex"], "needs": ["npm"]},
    },
    "antigravity": {
        "source": "https://www.antigravity.google/docs/cli/install/",
        "binary": "agy",
        "win32": _ps1("https://antigravity.google/cli/install.ps1",
                      "irm https://antigravity.google/cli/install.ps1 | iex"),
        "posix": {"cmd": ["bash", "-c",
                          "curl -fsSL https://antigravity.google/cli/install.sh | bash"],
                  "needs": ["bash", "curl"]},
    },
    # opencode 2 (VERIFICADO 2026-10-15). OJO: `opencode-ai` (npm) y
    # opencode.ai/install son opencode 1, que NO crea una sesión con el id que
    # le damos («Session not found: ses_ws…»). opencode 2 vive en
    # opencode.ai/v2/install y en el paquete npm `@opencode/cli`; su
    # postinstall copia el binario (npm 11+ bloquea scripts sin permiso).
    "opencode": {
        "source": "https://opencode.ai/v2/docs",
        "binary": "opencode",
        "win32": {"cmd": ["npm", "install", "-g", "@opencode/cli",
                          "--allow-scripts=@opencode/cli"],
                  "needs": ["npm"],
                  "note": "opencode 2 (paquete @opencode/cli); npm requiere Node.js."},
        "posix": {"cmd": ["bash", "-c", "curl -fsSL https://opencode.ai/v2/install | bash"],
                  "needs": ["bash", "curl"]},
        "alt": {"cmd": ["npm", "install", "-g", "@opencode/cli",
                        "--allow-scripts=@opencode/cli"], "needs": ["npm"]},
    },
    # `latest` (política «la más nueva por defecto», 2026-10-16): Workspace se
    # adapta a la versión y solo frena bugs comprobados (engines/openclaw.
    # KNOWN_BROKEN). Sin onboarding del instalador: la cuenta y el proveedor se
    # conectan en «cuenta y proveedor» (perfil propio).
    "openclaw": {
        "source": "https://docs.openclaw.ai/install",
        "binary": "openclaw",
        # El one-liner oficial le pasa `-NoOnboard` al script (su param()):
        # con -File va después de la ruta, igual que en scriptblock::Create.
        "win32": _ps1("https://openclaw.ai/install.ps1",
                      "& ([scriptblock]::Create((irm https://openclaw.ai/install.ps1)))"
                      " -NoOnboard", args=["-NoOnboard"],
                      note="requiere Node 24.16+ o 26.1+ (el instalador lo pone si falta)."),
        "posix": {"cmd": ["bash", "-c", "curl -fsSL https://openclaw.ai/install.sh | "
                          "bash -s -- --no-onboard"],
                  "needs": ["bash", "curl"]},
        "alt": {"cmd": ["npm", "install", "-g", "openclaw@latest"], "needs": ["npm"]},
    },
    "hermes": {
        "source": "https://hermes-agent.nousresearch.com/docs/getting-started/installation",
        "binary": "hermes",
        "win32": _ps1("https://hermes-agent.nousresearch.com/install.ps1",
                      "iex (irm https://hermes-agent.nousresearch.com/install.ps1)"),
        "posix": {"cmd": ["bash", "-c",
                          "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"],
                  "needs": ["bash", "curl"]},
    },
    # Kiro CLI (AWS) — instalador oficial (kiro.dev/downloads, 2026-10-28). POSIX:
    # en macOS copia «Kiro CLI.app» a /Applications y la abre una vez (crea
    # ~/.local/bin/kiro-cli y kiro-cli-chat); en Linux deja ~/.local/bin. Windows
    # 11: MSI en C:\Program Files\Kiro-Cli\ (install.ps1). Homebrew (`brew install
    # --cask kiro-cli`) la doc oficial no lo soporta y no abre la app: `kiro-cli
    # chat` falla hasta abrirla (engines/kiro.install_problem). Se actualiza solo.
    "kiro": {
        "source": "https://kiro.dev/downloads/",
        "binary": "kiro-cli",
        "win32": _ps1("https://cli.kiro.dev/install.ps1",
                      "irm 'https://cli.kiro.dev/install.ps1' | iex",
                      note="requiere Windows 11; corre en PowerShell o Windows Terminal."),
        "posix": {"cmd": ["bash", "-c", "curl -fsSL https://cli.kiro.dev/install | bash"],
                  "needs": ["bash", "curl"]},
    },
    # GitHub Copilot CLI (doc oficial, 2026-10-28; `latest`). macOS/Linux: el
    # paquete npm OFICIAL (exige Node.js 22+), NO el cask de Homebrew: en la Mac
    # el binario del cask quedó retenido por Gatekeeper y el postflight de brew
    # (`copilot completion bash|zsh|fish`) abría «No se abrió copilot», un
    # diálogo que el socio no puede cerrar y que lo empuja a mandarlo a la
    # papelera (VERIFICADO 2026-10-28; npm 1.0.105 abre sin diálogo). Windows:
    # WinGet (binario nativo, sin el .cmd de npm; el CLI pide PowerShell 6+).
    "copilot": {
        "source": "https://docs.github.com/en/copilot/how-tos/copilot-cli/"
                  "set-up-copilot-cli/install-copilot-cli",
        "binary": "copilot",
        "win32": {"cmd": ["winget", "install", "GitHub.Copilot"],
                  "needs": ["winget"]},
        "posix": {"cmd": ["npm", "install", "-g", "@github/copilot"],
                  "needs": ["npm"]},
        "alt": {"cmd": ["npm", "install", "-g", "@github/copilot"], "needs": ["npm"]},
    },
    # Cursor CLI (doc: cursor.com/docs/cli/installation): POSIX deja
    # ~/.local/bin/{agent,cursor-agent} (visto al instalar en la Mac); Windows,
    # %LOCALAPPDATA%\cursor-agent con cursor-agent.cmd (A-VERIFICAR en la PC:
    # nunca se ha instalado desde Motores en Windows). El cask de
    # Homebrew `cursor-cli` NO va de alternativa: en macOS 26.5 sus módulos
    # nativos sin notarizar quedan en cuarentena y el CLI no arranca
    # («library load disallowed by system policy»).
    "cursor": {
        "source": "https://cursor.com/docs/cli/installation",
        "binary": "cursor-agent",
        "win32": _ps1("https://cursor.com/install?win32=true",
                      "irm 'https://cursor.com/install?win32=true' | iex"),
        "posix": {"cmd": ["bash", "-c", "curl https://cursor.com/install -fsS | bash"],
                  "needs": ["bash", "curl"]},
    },
}

# Claude: `claude auth login` (VERIFICADO 2.1.302); `claude` a secas abría Claude
# Code completo en la carpeta de Workspace en vez de solo iniciar sesión.
_LOGIN = {"claude-code": ["claude", "auth", "login"], "codex": ["codex", "login"], "antigravity": ["agy"],
          "opencode": ["opencode", "auth", "login"],
          # Setup OFICIAL COMPLETO de OpenClaw (vanilla: tal como lo diseñó el
          # proveedor) en el perfil PROPIO de Workspace. VERIFICADO 2026.5.12:
          # empieza por «Where will the Gateway run?» y sigue con modelos,
          # canales, etc.; el cliente configura lo que quiera. Workspace no ve
          # la llave y solo re-asegura lo del cerebro (engines/openclaw.py).
          # VERIFICADO 2026.10.4: `configure` a secas empieza por el Gateway y el
          # socio no llegaba a elegir proveedor. El gateway del perfil lo prepara
          # Workspace (openclaw_gateway.py) → directo a la sección de modelo/proveedor.
          "openclaw": ["openclaw", "--profile", "workspace", "configure",
                       "--section", "model"],
          # Setup OFICIAL COMPLETO de Hermes (`hermes setup`: proveedor, modelo,
          # herramientas…) en el perfil PROPIO de Workspace (lo crea antes
          # engines/hermes.prepare_account). `hermes model` solo cambia
          # proveedor/modelo.
          # `model` = el selector OFICIAL de proveedor (incluye iniciar sesión)
          # y modelo — el mismo que Hermes abre solo si falta proveedor.
          # VERIFICADO v0.22.2: `setup` puede dejar una sesión OAuth sin
          # activar como proveedor (y el chat vuelve a pedir el asistente).
          "hermes": ["hermes", "--profile", "workspace", "model"],
          # Kiro: la cuenta ES el proveedor (Builder ID, Identity Center, Google,
          # GitHub); el modelo se elige dentro del chat (`/model`). 2.34.0.
          "kiro": ["kiro-cli", "login"],
          # GitHub Copilot: OAuth oficial (navegador o código de dispositivo).
          "copilot": ["copilot", "login"],
          # Cursor: su login OFICIAL (navegador; NO_OPEN_BROWSER=1 imprime el
          # enlace). La cuenta es la de Cursor; el modelo se elige dentro del TUI.
          "cursor": ["cursor-agent", "login"]}

#: «Cuenta y proveedor» (pantalla Motores, SIEMPRE disponible): abre el setup
#: OFICIAL de cada motor, VANILLA, tal como lo diseñó el proveedor. Principio de
#: producto: el cliente configura su cuenta, proveedor y todo lo demás DENTRO de
#: cada motor; Workspace no tiene sistema de providers, no guarda llaves y no
#: fija ajustes del motor (única excepción: lo que necesita del cerebro, que
#: re-asegura el adapter). Verificado contra cada CLI (2026-10-15):
#:   claude-code → `claude auth login` (cuenta Anthropic: suscripción o Console)
#:   codex       → `codex login`
#:   antigravity → `agy` (no tiene subcomando de login: el propio agy pide entrar)
#:   opencode    → `opencode auth login` (OpenRouter, Anthropic, OpenAI…)
#:   openclaw    → `openclaw --profile workspace configure --section model` (proveedor y
#:                 modelo; el gateway del perfil lo prepara Workspace — `onboard` es
#:                 el primer uso del proveedor: aviso de seguridad + gateway/servicio)
#:   hermes      → `hermes --profile workspace model` (proveedor —con su inicio de
#:                 sesión— y modelo, en el perfil propio; v0.22.2)
#:   kiro        → `kiro-cli login` (cuenta de Kiro; el modelo, con `/model` en el chat)
#:   copilot     → `copilot login` (cuenta de GitHub con Copilot; el modelo se
#:                 elige dentro de Copilot con /model, VERIFICADO 1.0.105)
#:   cursor      → `cursor-agent login` (cuenta de Cursor; el modelo, con /model
#:                 dentro del TUI; 2026.10.22)
#: Kiro, Copilot y Cursor no tienen selector de modelo FUERA del chat y su
#: login no sirve con la sesión ya iniciada (Kiro 2.34.0: «Already logged in»,
#: rc 1). Este comando es solo para SIN sesión; con sesión, Motores muestra el
#: menú que declara el adapter (`account_menu`: ver la cuenta, abrir el motor,
#: cambiar de cuenta con confirmación).
_ACCOUNT = {"claude-code": ["claude", "auth", "login"], "codex": ["codex", "login"],
            "antigravity": ["agy"], "opencode": ["opencode", "auth", "login"],
            "openclaw": ["openclaw", "--profile", "workspace", "configure",
                         "--section", "model"],
            "hermes": ["hermes", "--profile", "workspace", "model"],
            "kiro": ["kiro-cli", "login"],
            "copilot": ["copilot", "login"],
            "cursor": ["cursor-agent", "login"]}


def _t(key, es, **kw):
    """i18n falla-suave (Motores muestra estas notas/diagnósticos): `key` en
    el idioma activo; sin i18n / clave faltante → `es` inline (paridad)."""
    s = es
    try:
        import i18n
        v = i18n.t(key)
        if v != key:
            s = v
    except Exception:
        s = es
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


#: nota de receta (texto ES de _RECIPES) → clave i18n. La receta guarda la
#: fuente ES; recipe() la entrega en el idioma activo.
_NOTE_KEYS = {
    "Git for Windows es opcional (habilita la herramienta Bash).":
        "motores.inst.note.git_win",
    "requiere Node.js 22+; sin sudo": "motores.inst.note.node22",
    "instalador oficial de OpenAI para Windows; alternativa: "
    "npm install -g @openai/codex (requiere Node.js).": "motores.inst.note.codex_win",
}


def _note(es):
    k = _NOTE_KEYS.get(es)
    return _t(k, es) if (k and es) else es


def _plat(platform):
    return "win32" if (platform or sys.platform).startswith("win") else "posix"


def recipe(engine, platform=None):
    """Receta oficial para el motor en la plataforma (o None si no hay)."""
    r = _RECIPES.get(engine)
    if not r:
        return None
    p = r.get(_plat(platform))
    if not p:
        return None
    return {"engine": engine, "platform": _plat(platform), "source": r["source"],
            "binary": r["binary"], "cmd": list(p["cmd"]), "needs": list(p["needs"]),
            "note": _note(p.get("note", "")), "login_cmd": list(_LOGIN.get(engine, [])),
            "account_cmd": list(_ACCOUNT.get(engine) or _LOGIN.get(engine, [])),
            "alt": dict(r["alt"]) if r.get("alt") else None, "verified": VERIFIED,
            "pin": r.get("pin", ""), "manual": p.get("manual", ""),
            "aviso": _aviso(engine, platform)}


def _aviso(engine, platform=None):
    """Aviso de UNA línea antes de instalar: el diálogo del sistema que va a
    salir y qué contestar (UAC de Codex/Kiro en Windows, el ítem en segundo
    plano de Kiro en Mac). '' si no hay. Ver avisos_sistema."""
    plat = "win32" if _plat(platform) == "win32" else (platform or sys.platform)
    try:
        import avisos_sistema
        return avisos_sistema.motor(engine, plat)
    except Exception:
        return ""


def reinstall(engine, info=None, platform=None):
    """Comandos para reinstalar un motor que macOS bloquea (engine_gatekeeper)
    o cuya instalación quedó incompleta (Kiro por cask): si vino de un cask de
    Homebrew, primero `brew uninstall --cask <cask>` (si no, npm choca con su
    enlace en el PATH y el programa retenido seguiría ganando), luego la receta
    OFICIAL. Jamás `--zap` (Kiro: mandaría a la papelera ~/.kiro y la sesión).
    Nada se ejecuta aquí: Motores muestra los comandos y pide Enter. [] si no
    hay receta."""
    rec = recipe(engine, platform)
    if not rec:
        return []
    cask = str((info or {}).get("cask") or "")
    pre = [["brew", "uninstall", "--cask", cask]] if cask else []
    return pre + [list(rec["cmd"])]


# ── Windows: bajar el instalador oficial y correr el ARCHIVO (sin cradle) ────
class DownloadError(Exception):
    """No se pudo bajar el instalador oficial: el mensaje (una línea, en el
    idioma activo) es para el socio y no se ejecutó nada."""


def script_url(cmd):
    """URL del instalador oficial si `cmd` es una receta «bajar y correr»
    (_ps1); None si es un comando normal (npm, winget, bash -c … en POSIX)."""
    cmd = list(cmd or [])
    n = len(PS1_HEAD)
    if len(cmd) > n and cmd[:n] == PS1_HEAD and "://" in str(cmd[n]):
        return str(cmd[n])
    return None


def with_file(cmd, path):
    """El argv de la receta con `path` en el lugar de la URL."""
    n = len(PS1_HEAD)
    return list(cmd[:n]) + [path] + list(cmd[n + 1:])


def fetch_line(url):
    """Lo que Workspace hace antes del comando (se imprime y se muestra)."""
    return _t("motores.inst.fetch", "Workspace baja {u} y lo corre:", u=url)


def shown(cmd, fmt=" ".join):
    """Cómo se le muestra `cmd` al socio ANTES de correrlo: `fmt(cmd)` tal cual
    o, si es «bajar y correr», qué baja Workspace y el comando que de verdad
    corre (con el .ps1 temporal). → [str] (una entrada por renglón lógico)."""
    url = script_url(cmd)
    if not url:
        return [fmt(list(cmd))]
    return [fetch_line(url), fmt(with_file(cmd, PS1_SHOWN))]


def _why(e):
    code = getattr(e, "code", None)
    if isinstance(code, int):
        return "HTTP %d" % code
    return str(getattr(e, "reason", "") or "") or str(e) or e.__class__.__name__


def _failed(url, why):
    return DownloadError(_t("motores.inst.fetch_failed",
                            "no pude bajar el instalador oficial {u} ({e}) — no se "
                            "ejecutó nada; revisa tu conexión o proxy", u=url, e=why))


def fetch(url, urlopen=None):
    """Baja el instalador oficial `url` a un .ps1 temporal único → su ruta.
    Solo HTTPS (también la URL final, tras redirecciones), con timeout y tope
    de tamaño; la URL sale únicamente de la receta. Si algo falla →
    DownloadError y no queda archivo. PowerShell 5.1 lee un .ps1 sin BOM en la
    página de códigos ANSI: a un script UTF-8 con acentos se le antepone el BOM
    (mismo texto que entrega `irm`)."""
    if not str(url).lower().startswith("https://"):
        raise _failed(url, _t("motores.inst.fetch.not_https", "no es HTTPS"))
    import urllib.request
    opener = urlopen or urllib.request.urlopen
    try:
        req = urllib.request.Request(url, headers={"User-Agent": FETCH_UA})
        with opener(req, timeout=FETCH_TIMEOUT) as resp:
            final = getattr(resp, "url", None)     # la URL tras redirecciones
            if not isinstance(final, str) or not final:
                final = url
            if not final.lower().startswith("https://"):
                raise _failed(url, _t("motores.inst.fetch.not_https", "no es HTTPS"))
            data = resp.read(FETCH_MAX + 1)
    except DownloadError:
        raise
    except Exception as e:                 # red, HTTP 4xx/5xx, TLS, timeout
        raise _failed(url, _why(e))
    if len(data) > FETCH_MAX:
        raise _failed(url, _t("motores.inst.fetch.too_big", "pesa más de {n} MB",
                              n=FETCH_MAX // (1024 * 1024)))
    if not data.strip():
        raise _failed(url, _t("motores.inst.fetch.empty", "llegó vacío"))
    if not data.startswith((b"\xef\xbb\xbf", b"\xff\xfe", b"\xfe\xff")):
        try:
            data.decode("ascii")
        except UnicodeDecodeError:
            try:
                data.decode("utf-8")
                data = b"\xef\xbb\xbf" + data
            except UnicodeDecodeError:
                pass
    fd, path = tempfile.mkstemp(prefix="workspace-install-", suffix=".ps1")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(data)
    except Exception as e:                 # disco lleno, antivirus, permisos
        _remove(path)
        raise _failed(url, _why(e))
    except BaseException:                  # Ctrl+C
        _remove(path)
        raise
    return path


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


@contextlib.contextmanager
def runnable(cmd, urlopen=None):
    """El argv que de verdad corre `cmd`. Comando normal → tal cual (nada se
    baja). «Bajar y correr» (Windows) → baja el instalador oficial (fetch;
    DownloadError si no se pudo) y entrega PS1_HEAD + el .ps1 temporal + los
    argumentos de la receta; al salir lo borra, también si el comando falla o
    con Ctrl+C."""
    url = script_url(cmd)
    if not url:
        yield list(cmd)
        return
    path = fetch(url, urlopen)
    try:
        yield with_file(cmd, path)
    finally:
        _remove(path)


def missing_prereqs(rec, which=shutil.which):
    """Prerequisitos ausentes del comando (p.ej. npm sin Node instalado).
    El socio lo ve ANTES de confirmar en vez de un exit críptico después."""
    if not rec:
        return []
    return [n for n in rec.get("needs", []) if not which(n)]


def diagnose_exit(rec, returncode, which=shutil.which):
    """Explicación del resultado de una instalación (sin adivinar red)."""
    if returncode == 0:
        if rec and not which(rec["binary"]):
            return _t("motores.inst.not_in_path",
                      "el instalador terminó bien pero `{b}` no está en el "
                      "PATH de esta terminal — elige «ya lo instalé: recargar» o "
                      "abre una terminal nueva", b=rec["binary"])
        return ""
    miss = missing_prereqs(rec, which)
    if miss:
        return _t("motores.inst.missing",
                  "falta {m} para correr el instalador", m=", ".join(miss))
    return _t("motores.inst.failed",
              "el instalador terminó con código {rc} — revisa la salida "
              "arriba (red, permisos o proxy) y la guía oficial: {u}",
              rc=returncode, u=(rec or {}).get("source", ""))


def describe(engine, platform=None, which=shutil.which):
    rec = recipe(engine, platform)
    if not rec:
        return [_t("motores.inst.d.none",
                   "sin instalador oficial registrado para {e}", e=engine)]
    out = [_t("motores.inst.d.source", "Fuente oficial: {u} (verificada {d})",
              u=rec["source"], d=rec["verified"]),
           _t("motores.inst.d.cmd", "Comando: {c}", c=" ".join(shown(rec["cmd"])))]
    if rec["manual"]:                      # el one-liner del proveedor, a mano
        out.append(_t("motores.inst.d.manual", "A mano, en PowerShell: {c}", c=rec["manual"]))
    miss = missing_prereqs(rec, which)
    if miss:
        out.append(_t("motores.inst.d.miss", "Falta: {m} — instálalo antes",
                      m=", ".join(miss)))
    if rec["note"]:
        out.append(rec["note"])
    if rec["aviso"]:
        out.append(rec["aviso"])
    return out
