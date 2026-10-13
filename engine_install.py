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
        "win32": {"cmd": ["npm", "install", "-g", "@openai/codex"],
                  "needs": ["npm"],
                  "note": "la doc oficial no publica instalador nativo para Windows; "
                          "npm requiere Node.js instalado."},
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
}

_LOGIN = {"claude-code": ["claude"], "codex": ["codex", "login"], "antigravity": ["agy"]}


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
    "la doc oficial no publica instalador nativo para Windows; "
    "npm requiere Node.js instalado.": "motores.inst.note.codex_win",
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
            "alt": dict(r["alt"]) if r.get("alt") else None, "verified": VERIFIED}


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
                      "PATH de esta terminal — usa Recargar (r) o abre una "
                      "terminal nueva", b=rec["binary"])
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
