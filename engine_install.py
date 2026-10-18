#!/usr/bin/env python3
"""WORKSPACE · engine_install — instalación OFICIAL de motores por OS (U02/Z02).

Una receta por (motor, plataforma): comando del instalador oficial, URL de la
fuente oficial y prerequisitos. La UI la muestra ANTES de confirmar; nada se
ejecuta aquí (el driver corre el comando en la terminal del socio con su
confirmación). Fuentes verificadas 2026-10-10:
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
Antes de cada release: re-verificar estas URLs/comandos (pueden cambiar).

API: recipe(engine, platform=None) → dict | None
     missing_prereqs(recipe) → [str]   (qué falta para que el comando corra)
     describe(engine, platform=None) → líneas legibles (fuente/comando/prereqs)
"""
import shutil
import sys

VERIFIED = "2026-10-10"

_RECIPES = {
    "claude-code": {
        "source": "https://code.claude.com/docs/en/setup",
        "binary": "claude",
        "win32": {"cmd": ["powershell", "-NoProfile", "-Command",
                          "irm https://claude.ai/install.ps1 | iex"],
                  "needs": ["powershell"],
                  "note": "Git for Windows es opcional (habilita la herramienta Bash)."},
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
        "win32": {"cmd": ["powershell", "-NoProfile", "-Command",
                          "irm https://chatgpt.com/codex/install.ps1 | iex"],
                  "needs": ["powershell"],
                  "note": "instalador oficial de OpenAI para Windows; alternativa: "
                          "npm install -g @openai/codex (requiere Node.js)."},
        "posix": {"cmd": ["sh", "-c", "curl -fsSL https://chatgpt.com/codex/install.sh | sh"],
                  "needs": ["sh", "curl"]},
        "alt": {"cmd": ["npm", "install", "-g", "@openai/codex"], "needs": ["npm"]},
    },
    "antigravity": {
        "source": "https://www.antigravity.google/docs/cli/install/",
        "binary": "agy",
        "win32": {"cmd": ["powershell", "-NoProfile", "-Command",
                          "irm https://antigravity.google/cli/install.ps1 | iex"],
                  "needs": ["powershell"]},
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
        "win32": {"cmd": ["powershell", "-NoProfile", "-Command",
                          "& ([scriptblock]::Create((irm https://openclaw.ai/install.ps1)))"
                          " -NoOnboard"],
                  "needs": ["powershell"],
                  "note": "requiere Node 24.16+ o 26.1+ (el instalador lo pone si falta)."},
        "posix": {"cmd": ["bash", "-c", "curl -fsSL https://openclaw.ai/install.sh | "
                          "bash -s -- --no-onboard"],
                  "needs": ["bash", "curl"]},
        "alt": {"cmd": ["npm", "install", "-g", "openclaw@latest"], "needs": ["npm"]},
    },
    "hermes": {
        "source": "https://hermes-agent.nousresearch.com/docs/getting-started/installation",
        "binary": "hermes",
        "win32": {"cmd": ["powershell", "-NoProfile", "-Command",
                          "iex (irm https://hermes-agent.nousresearch.com/install.ps1)"],
                  "needs": ["powershell"]},
        "posix": {"cmd": ["bash", "-c",
                          "curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash"],
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
          "hermes": ["hermes", "--profile", "workspace", "model"]}

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
_ACCOUNT = {"claude-code": ["claude", "auth", "login"], "codex": ["codex", "login"],
            "antigravity": ["agy"], "opencode": ["opencode", "auth", "login"],
            "openclaw": ["openclaw", "--profile", "workspace", "configure",
                         "--section", "model"],
            "hermes": ["hermes", "--profile", "workspace", "model"]}


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
            "pin": r.get("pin", "")}


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
           _t("motores.inst.d.cmd", "Comando: {c}", c=" ".join(rec["cmd"]))]
    miss = missing_prereqs(rec, which)
    if miss:
        out.append(_t("motores.inst.d.miss", "Falta: {m} — instálalo antes",
                      m=", ".join(miss)))
    if rec["note"]:
        out.append(rec["note"])
    return out
