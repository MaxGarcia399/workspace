#!/usr/bin/env python3
"""WORKSPACE · agent_admin — separar / cargar / sembrar agentes.

El backend de la separación harness⊥agentes y de la carga de agentes:

  separate()  Hace cada cerebro AUTODESCRIPTIVO: escribe `<brain>/.workspace/agent.json`
              (identidad portátil, dueño detectado) para cada agente del registry
              committeado, y luego VACÍA el registry committeado → el harness queda
              sin agentes. Idempotente, dry-run por default, atómico. NO borra
              `agents/<n>/` ni el cerebro — solo agrega la def al cerebro y vacía
              el registry (todo revertible por git).

  load()      Registra un agente apuntando a una carpeta de cerebro (per-máquina,
              en agents.local.json). Si la carpeta ya es autodescriptiva
              (`.workspace/agent.json`) la usa; si es un cerebro "pelón", la SIEMBRA
              con una def mínima inferida (nombre de la carpeta, dueño de socio.local).

Identidad ↔ brand (decisión MVP): la IDENTIDAD viaja en el cerebro
(`.workspace/agent.json`); el CÓDIGO de brand (statusline/banner/dashboard) sigue
harness-side por ahora (los `scripts` apuntan a `{root}/agents/<n>/brand/` para los
agentes existentes, o al brand genérico del template para nuevos). Genericizar el
brand y meterlo al cerebro = Fase 2 (es el pulido/front-end de después).

stdlib puro, falla-suave, escritura atómica. Trabaja sobre dispatch + agentsreg.
"""
import datetime
import json
import os
import re
import shutil
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import agentsreg          # noqa: E402
import dispatch           # noqa: E402

ROOT = dispatch.ROOT
BRAIN_TEMPLATE = os.path.join(ROOT, "templates", "agent", "brain")
# brand genérico del template (los agentes nuevos lo referencian; Fase 2: brand propio)
_GENERIC_BRAND = "{root}/templates/agent/workspace/brand/agent-%s.py"

# Colores CANÓNICOS (los que entienden el banner/_COLOR_CODE y el fuego). Aceptamos
# alias en español y normalizamos → arregla el bug "azul" → gris (no mapeaba en inglés).
CANON_COLORS = ("blue", "red", "green", "pink", "violet", "purple", "wine",
                "cyan", "gold", "coral", "gray")
_COLOR_ALIASES = {"azul": "blue", "rojo": "red", "verde": "green", "rosa": "pink",
                  "violeta": "violet", "morado": "purple", "vino": "wine",
                  "cian": "cyan", "celeste": "cyan", "dorado": "gold",
                  "oro": "gold", "coral": "coral", "gris": "gray"}


def norm_color(c):
    """Normaliza un color (alias español o inglés) a una clave canónica; default gray."""
    c = (c or "gray").strip().lower()
    c = _COLOR_ALIASES.get(c, c)
    return c if c in CANON_COLORS else "gray"
# campos de la def committeada que NO viajan al cerebro (se derivan o sobran)
_DROP_FIELDS = ("brain", "dir", "_dir", "aliases")


# ── tema por color (D4): un agente nace con IDENTIDAD de color, cero manual ──
# Por color canónico: (bg terminal, fg terminal, accent in-app). Base oscura
# teñida hacia el color. Deriva un tema VÁLIDO de UN color → no hace falta editar
# themes.json ni themes-cc a mano.
COLOR_THEMES = {
    "blue":   ("#0a0f1c", "#cfe0ff", "#5b8bff"),
    "cyan":   ("#08191c", "#c8f5ff", "#57d9d0"),
    "green":  ("#081610", "#cdf3d6", "#6bbf8a"),
    "gold":   ("#1a1408", "#ffeecc", "#d9a441"),
    "coral":  ("#1c0f0a", "#ffe0d6", "#e0796b"),
    "red":    ("#1c0d0a", "#ffd9d2", "#e0685a"),
    "pink":   ("#1c0a17", "#ffd9f0", "#e089c0"),
    "violet": ("#120a1c", "#e6d9ff", "#b98cff"),
    "purple": ("#140a1c", "#ecd9ff", "#a06bd0"),
    "wine":   ("#1a0810", "#ffd0dc", "#c05070"),
    "gray":   ("#121316", "#e6e8ee", "#9aa0b0"),
}


def theme_for_color(color):
    """(bg, fg, accent) del tema de un color (canónico o alias). Default gray."""
    return COLOR_THEMES.get(norm_color(color), COLOR_THEMES["gray"])


def write_agent_theme(name, display, color, out=print):
    """Registra el tema del agente (D4): entrada en <WORKSPACE>/themes.json (bg/fg del
    terminal) + themes-cc/<name>.json (tema in-app de Claude Code). Idempotente,
    falla-suave: si truena, el agente igual funciona (solo sin color propio)."""
    name = (name or "").strip().lower()
    bg, fg, accent = theme_for_color(color)
    # target overridable por env (tests herméticos apuntan a un temp; real = ROOT).
    troot = os.environ.get("WORKSPACE_THEMES_ROOT") or ROOT
    ok = True
    try:                                            # 1) terminal (themes.json, plano)
        tp = os.path.join(troot, "themes.json")
        themes = {}
        if os.path.isfile(tp):
            with open(tp, encoding="utf-8") as fh:
                themes = json.load(fh)
        themes[name] = {"bg": bg, "fg": fg}
        ok = _atomic_write_json(tp, themes) and ok
    except Exception as e:
        out("AGENT: WARN: no pude escribir themes.json (%s)" % e); ok = False
    try:                                            # 2) in-app (themes-cc/<name>.json)
        ccdir = os.path.join(troot, "themes-cc")
        os.makedirs(ccdir, exist_ok=True)
        cc = {"name": display or name.capitalize(), "base": "dark",
              "overrides": {"claude": accent, "text": fg, "inactive": "#6f6f82",
                            "suggestion": accent, "permission": accent,
                            "promptBorder": accent, "autoAccept": accent}}
        ok = _atomic_write_json(os.path.join(ccdir, "%s.json" % name), cc) and ok
    except Exception as e:
        out("AGENT: WARN: no pude escribir themes-cc/%s.json (%s)" % (name, e)); ok = False
    return ok


# ── helpers ──────────────────────────────────────────────────────────────────
def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def _atomic_write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp-%d" % os.getpid()
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, path)
        return True
    except Exception:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def _detect_owner(brain):
    """Dueño del agente = socio.local del cerebro (soporta dueños EXTERNOS, no
    solo max/fer/mau). Falla-suave → '' (sin dueño declarado)."""
    try:
        with open(os.path.join(brain, ".claude", "socio.local"),
                  encoding="utf-8") as fh:
            s = fh.read().strip().lower()
        if re.match(r"^[a-z0-9_-]+$", s):
            return s
    except Exception:
        pass
    return ""


def _definition_from_committed(cfg, brain):
    """Transforma una agent.json committeada en la def autodescriptiva que vive
    en el cerebro: quita campos derivados, agrega `owner`. `scripts` se conserva
    (brand harness-side por ahora)."""
    out = {k: v for k, v in cfg.items()
           if k not in _DROP_FIELDS and not k.startswith("_")}
    owner = _detect_owner(brain)
    if owner:
        out["owner"] = owner
    out["_note"] = ("Definición autodescriptiva del agente (WORKSPACE hub). La "
                    "identidad vive en el cerebro; el harness la carga vía "
                    "agents.local.json. Brand harness-side por ahora (Fase 2: "
                    "genericizar y mover al cerebro).")
    return out


# ── O3 · separar ─────────────────────────────────────────────────────────────
def separate(dry_run=True, empty_registry=True, out=print):
    """Hace autodescriptivos los cerebros del registry committeado y vacía el
    registry. Devuelve {written, skipped, errors, registry_emptied}. Idempotente."""
    reg = dispatch._committed_registry()
    committed = [a for a in reg.get("agents", []) if not a.get("_loaded")]
    res = {"written": [], "skipped": [], "errors": [], "registry_emptied": False}
    for entry in committed:
        name = entry.get("name", "")
        try:
            cfg = dispatch.load_agent_cfg(entry)
            brain = dispatch.resolve_brain(name, cfg)
        except Exception as e:
            res["errors"].append((name, "no se pudo cargar cfg/cerebro: %s" % e))
            out("AGENT: ERROR:%s — %s" % (name, e))
            continue
        if not brain or not os.path.isdir(brain):
            res["errors"].append((name, "cerebro inexistente: %s" % brain))
            out("AGENT: ERROR:%s — cerebro inexistente: %s" % (name, brain))
            continue
        defn = _definition_from_committed(cfg, brain)
        dest = agentsreg.agent_json_path(brain)
        if dry_run:
            verb = "actualizaría" if os.path.exists(dest) else "crearía"
            out("AGENT: DRY:%s — %s %s" % (name, verb, dest))
            res["written"].append(name)
            continue
        if _atomic_write_json(dest, defn):
            out("AGENT: SEP:%s — def escrita en %s" % (name, dest))
            res["written"].append(name)
        else:
            res["errors"].append((name, "no se pudo escribir %s" % dest))
            out("AGENT: ERROR:%s — no se pudo escribir %s" % (name, dest))
    # vaciar el registry committeado (el harness queda sin agentes)
    if empty_registry and not dry_run and not res["errors"]:
        rp = dispatch.registry_path()
        planned = reg.get("planned", []) if isinstance(reg, dict) else []
        if _atomic_write_json(rp, {"version": 1, "agents": [], "planned": planned}):
            res["registry_emptied"] = True
            out("AGENT: SEP — registry committeado vaciado (harness sin agentes)")
    elif empty_registry and dry_run:
        out("AGENT: DRY — vaciaría el registry committeado (harness sin agentes)")
    return res


# ── O4 · sembrar + cargar ────────────────────────────────────────────────────
def seed_definition(folder, name=None, owner=None, display=None, tagline="",
                    color="gris", out=print):
    """Siembra `<folder>/.workspace/agent.json` para un cerebro 'pelón' (sin def).
    Infiere name de la carpeta y owner de socio.local. Brand → genérico del
    template. Devuelve (ok, name|error). No sobrescribe una def existente."""
    folder = os.path.abspath(os.path.expanduser(folder or ""))
    if not os.path.isdir(folder):
        return False, "la carpeta no existe: %s" % folder
    dest = agentsreg.agent_json_path(folder)
    if os.path.exists(dest):
        existing = _read_json(dest)
        return True, existing.get("name", name or _name_from_folder(folder))
    name = (name or _name_from_folder(folder)).strip().lower()
    if not agentsreg.is_valid_name(name):
        return False, "no pude inferir un nombre válido de %r" % folder
    owner = owner or _detect_owner(folder)
    defn = {
        "name": name,
        "display": display or name.capitalize(),
        "tagline": tagline,
        "engine": "claude-code",
        "color": color,
        "setup": {"session_journal": True, "autonomous": False},
        "scripts": {
            "banner": "{root}/templates/agent/workspace/brand/agent-banner.py",
            "dashboard": "{root}/templates/agent/workspace/brand/agent-dashboard.py",
            "statusline": "{root}/templates/agent/workspace/brand/agent-statusline.py",
        },
        "_note": "Def sembrada por agent_admin.load (cerebro sin .workspace). "
                 "Edita color/tagline/brand a gusto.",
    }
    if owner:
        defn["owner"] = owner
    if not _atomic_write_json(dest, defn):
        return False, "no se pudo escribir %s" % dest
    out("AGENT: SEED:%s — def mínima sembrada en %s" % (name, dest))
    return True, name


# ── O5 · crear ───────────────────────────────────────────────────────────────
#: Los PASOS REALES de create(), en orden — contrato para cualquier UI que
#: quiera pintar el proceso (add_agent_tui los pinta EN VIVO). `create()` los
#: reporta por el callback `progress(key, st, note)` con st ∈ pend/run/ok/
#: warn/fail/skip. Fuente única: si create() gana un paso, se agrega AQUÍ.
CREATE_STEPS = (
    ("validar", "validar nombre y destino"),
    ("scaffold", "copiar el cerebro (template → carpeta)"),
    ("definicion", "identidad: .workspace/agent.json + socio"),
    ("registro", "registro per-máquina (agents.local.json)"),
    ("tema", "tema propio (terminal + in-app)"),
    ("cableado", "cableado del cerebro (hooks · statusline)"),
    ("launcher", "comando en PATH (launcher)"),
    ("verificacion", "verificación final"),
)
#: Pasos CRÍTICOS: si uno falla, se revierte TODO (ningún medio-cerebro).
#: Los demás son falla-suave: el agente queda usable y `workspace doctor`
#: completa lo que falte (se reporta como warn, jamás en silencio).
_CRITICAL_STEPS = ("validar", "scaffold", "definicion", "registro")


def default_brain_dest(name):
    """La carpeta DEFAULT del cerebro de un agente nuevo (la misma que usa
    create() sin brain_dest): ~/Desktop/<NOMBRE> - BRAIN."""
    return os.path.join(os.path.expanduser("~"), "Desktop",
                        "%s - BRAIN" % (name or "").strip().upper())


def _prog(progress, key, st, note=""):
    """Reporta un paso al callback de la UI. Falla-suave ABSOLUTA: un callback
    roto jamás tumba la creación."""
    if progress is None:
        return
    try:
        progress(key, st, note)
    except Exception:
        pass


def _render_tree(src, dst, subs):
    """Copia src→dst renderizando placeholders {{X}} en archivos de texto.
    Falla-suave por archivo (binario/ilegible → copia tal cual)."""
    for root, _dirs, files in os.walk(src):
        rel = os.path.relpath(root, src)
        outdir = os.path.join(dst, rel) if rel != "." else dst
        os.makedirs(outdir, exist_ok=True)
        for fn in files:
            sp, dp = os.path.join(root, fn), os.path.join(outdir, fn)
            try:
                with open(sp, encoding="utf-8") as fh:
                    text = fh.read()
                for k, v in subs.items():
                    text = text.replace(k, v)
                with open(dp, "w", encoding="utf-8") as fh:
                    fh.write(text)
            except (UnicodeDecodeError, OSError):
                shutil.copy2(sp, dp)


def _write_owner_profile(dest, display, owner, intake):
    """Siembra `STATE/users/<owner>.md` con lo que el intake dijo del DUEÑO
    (quién es · cómo trabaja · qué necesita). Ese perfil es HOT al boot (el
    CLAUDE.md del template lo lee) → el agente conoce a su dueño desde la
    PRIMERA sesión, no desde el primer feedback. Solo si hay algo que decir;
    jamás pisa un perfil existente. Falla-suave ABSOLUTA."""
    datos = {k: str((intake or {}).get(k) or "").strip()
             for k in ("dueño_quien", "dueño_como", "dueño_necesita")}
    if not owner or not any(datos.values()):
        return
    try:
        path = os.path.join(dest, "STATE", "users", "%s.md" % owner)
        if os.path.exists(path):
            return
        cuerpo = [
            "# %s — perfil de trato" % owner, "",
            "> Sembrado al crear el agente (intake del formulario «Agregar "
            "agente», %s)." % datetime.date.today().isoformat(),
            "> Documento VIVO: %s lo afina con el feedback real del dueño."
            % (display or "el agente"), "",
        ]
        for titulo, clave in (("Quién es", "dueño_quien"),
                              ("Cómo trabaja", "dueño_como"),
                              ("Qué necesita de mí", "dueño_necesita")):
            if datos[clave]:
                cuerpo += ["## %s" % titulo, "", datos[clave], ""]
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(cuerpo))
    except Exception:
        pass


def create(name, tagline="", display=None, owner="", scope="", soul="",
           skills="", color="gris", brain_dest=None, dry_run=False, out=print,
           configure=True, engine="claude-code", progress=None,
           should_cancel=None, intake=None):
    """Crea un agente NUEVO autocontenido: scaffold del cerebro desde el template
    (placeholders renderizados) + `.workspace/agent.json` RICO + socio.local + registro
    per-máquina. Con `configure=True` (default) lo deja USABLE y CON COLOR: tema
    (themes.json/-cc) + hooks + statusline + launcher (igual que `load`) → nace
    completo, sin follow-ups. `configure=False` = solo scaffold (tests herméticos).

    `engine` = el harness con el que nace (claude-code/codex/gemini — el default
    del agent.json; cambiable después per-máquina vía harnesses.set_binding).
    `progress(key, st, note)` reporta CADA paso de CREATE_STEPS en vivo (la
    pantalla «Agregar agente» lo pinta); `should_cancel()` → True cancela
    cooperativamente ENTRE pasos: antes del registro se revierte TODO, después
    el agente ya existe y solo quedan pasos de pulido (se marcan skip).
    `intake` (opcional) = dict con las respuestas CRUDAS del formulario
    «Agregar agente» (texto libre, multilínea): se guarda en el agent.json
    del cerebro («intake») y siembra `STATE/users/<owner>.md` con lo que
    dijo del dueño — así el agente nace A LA MEDIDA, no genérico.
    Devuelve (ok, name|error). No sobrescribe carpetas existentes."""
    name = (name or "").strip().lower()

    # entrada robusta: None (p.ej. EOF en el prompt) → string vacío, nunca
    # crashea. Los campos que se SUSTITUYEN en el template van a contextos
    # inline de markdown ({{TAGLINE}}/{{SCOPE}}/{{SOUL_HINT}} viven dentro de
    # una línea) → un \n crudo los rompería: se aplanan a « · ». El texto
    # multilínea COMPLETO viaja intacto en `intake`.
    def _linea(s):
        return " · ".join(p.strip() for p in str(s or "").split("\n")
                          if p.strip())
    tagline, scope = _linea(tagline), _linea(scope)
    soul, skills = _linea(soul), _linea(skills)
    color = norm_color(color)   # acepta alias español; canónico para banner/fuego
    engine = (engine or "claude-code").strip().lower()

    def _cxl():
        try:
            return bool(should_cancel and should_cancel())
        except Exception:
            return False

    _prog(progress, "validar", "run")
    if not agentsreg.is_valid_name(name):
        err = "nombre inválido: %r (minúsculas, dígitos, - o _)" % name
        _prog(progress, "validar", "fail", "nombre inválido")
        return False, err
    if not re.match(r"^[a-z0-9][a-z0-9_-]{0,31}$", engine):
        _prog(progress, "validar", "fail", "harness inválido")
        return False, "harness inválido: %r" % engine
    if dispatch.find_agent(name) or agentsreg.find(name):
        _prog(progress, "validar", "fail", "ya existe")
        return False, "ya existe un agente '%s'" % name
    if not os.path.isdir(BRAIN_TEMPLATE):
        _prog(progress, "validar", "fail", "sin template")
        return False, "falta el template del cerebro: %s" % BRAIN_TEMPLATE
    upper, display = name.upper(), (display or name.capitalize())
    dest = os.path.abspath(os.path.expanduser(
        brain_dest or default_brain_dest(name)))
    if os.path.exists(dest):
        _prog(progress, "validar", "fail", "carpeta ya existe")
        return False, "la carpeta del cerebro ya existe: %s" % dest
    owner = (owner or "").strip().lower()
    if owner and not re.match(r"^[a-z0-9_-]+$", owner):
        _prog(progress, "validar", "fail", "owner inválido")
        return False, "owner inválido: %r" % owner
    _prog(progress, "validar", "ok", "")
    if dry_run:
        out("AGENT: DRY:create %s → %s (owner=%s, color=%s, engine=%s)"
            % (name, dest, owner or "—", color, engine))
        return True, name
    if _cxl():
        _prog(progress, "scaffold", "skip", "cancelado")
        return False, "cancelado — nada quedó a medias (no se escribió nada)"
    subs = {
        "{{AGENT_NAME}}": name, "{{AGENT_DISPLAY}}": display,
        "{{AGENT_UPPER}}": upper, "{{TAGLINE}}": tagline,
        "{{SOUL_HINT}}": soul or "(sin semilla — diseñar desde cero)",
        "{{SKILL_CATS}}": skills, "{{COLOR}}": color, "{{SCOPE}}": scope,
        "{{DATE}}": datetime.date.today().isoformat(),
    }
    # scaffold + def + socio: TODO en un try con ROLLBACK (dest es nuevo — lo
    # creamos nosotros, así que borrarlo en fallo es seguro y evita medios-cerebros).
    # agent.json RICO — un agente nuevo nace al MISMO nivel que uno de equipo, no
    # empobrecido: `brain` (autocontenido), `session_env/id` PROPIOS (sin esto el
    # engine cae al default ZENITH_WS → colisión de workspace), y el bloque
    # `memory` (contrato que audita `workspace doctor` + opt-in de dreaming/fts).
    defn = {
        "name": name, "display": display, "tagline": tagline,
        "engine": engine, "brain": ".", "color": color, "theme": name,
        "session_env": upper + "_WS", "session_id_env": upper + "_WID",
        "setup": {"session_journal": True, "autonomous": False},
        "memory": {"tiering": "v1", "dreaming": True, "fts_index": False,
                   "index_contract": "STATE/INDEX.md"},
        "scripts": {"banner": _GENERIC_BRAND % "banner",
                    "dashboard": _GENERIC_BRAND % "dashboard",
                    "statusline": _GENERIC_BRAND % "statusline"},
        "_note": "Agente creado por agent_admin.create (autocontenido). "
                 "Brand genérico por ahora — personalízalo (Fase 2).",
    }
    if owner:
        defn["owner"] = owner
    # las respuestas CRUDAS del intake viajan con el cerebro (texto completo,
    # multilínea) — el agente las tiene aunque la UI solo sembró resúmenes
    if isinstance(intake, dict):
        limpio = {str(k): str(v).strip() for k, v in intake.items()
                  if str(v or "").strip()}
        if limpio:
            defn["intake"] = limpio
    # ── scaffold (crítico, con rollback) ──
    _prog(progress, "scaffold", "run")
    try:
        _render_tree(BRAIN_TEMPLATE, dest, subs)
    except Exception as e:
        shutil.rmtree(dest, ignore_errors=True)        # rollback del scaffold parcial
        _prog(progress, "scaffold", "fail", "revertido")
        return False, "falló la creación (revertida): %s" % e
    _prog(progress, "scaffold", "ok")
    # ── definición + socio (crítico, con rollback) ──
    _prog(progress, "definicion", "run")
    try:
        if not _atomic_write_json(agentsreg.agent_json_path(dest), defn):
            raise IOError("no se pudo escribir la definición .workspace/agent.json")
        if owner:
            os.makedirs(os.path.join(dest, ".claude"), exist_ok=True)
            with open(os.path.join(dest, ".claude", "socio.local"), "w",
                      encoding="utf-8") as fh:
                fh.write(owner)
            os.makedirs(os.path.join(dest, "STATE", "sessions", owner,
                                     "destilados"), exist_ok=True)
        _write_owner_profile(dest, display, owner, intake)  # falla-suave
    except Exception as e:
        shutil.rmtree(dest, ignore_errors=True)        # rollback del scaffold parcial
        _prog(progress, "definicion", "fail", "revertido")
        return False, "falló la creación (revertida): %s" % e
    _prog(progress, "definicion", "ok")
    if _cxl():                                         # cancel ANTES del registro
        shutil.rmtree(dest, ignore_errors=True)        # → revertir = nada a medias
        _prog(progress, "registro", "skip", "cancelado")
        return False, "cancelado — nada quedó a medias (carpeta revertida)"
    # ── registro per-máquina (crítico, con rollback) ──
    _prog(progress, "registro", "run")
    ok, err = agentsreg.add(name, dest)
    if not ok:
        shutil.rmtree(dest, ignore_errors=True)        # no dejar cerebro huérfano sin registrar
        _prog(progress, "registro", "fail", "revertido")
        return False, "no se pudo registrar (revertido): %s" % err
    _prog(progress, "registro", "ok")
    out("AGENT: CREATE:%s → %s" % (name, dest))
    # D4/D5 — dejar el agente USABLE y CON COLOR (no a medias): tema propio + hooks +
    # statusline + launcher, igual que `load`. Idempotente y FALLA-SUAVE: si algo
    # truena, el agente queda registrado y `workspace doctor` lo completa. `configure`
    # se apaga en tests (herméticos) o cuando el workflow orquesta la config aparte.
    # Desde aquí el agente YA EXISTE: cancelar solo salta el pulido (skip honesto).
    warn_cfg = ""
    if configure:
        if _cxl():
            for k in ("tema", "cableado", "launcher", "verificacion"):
                _prog(progress, k, "skip", "cancelado")
            out("AGENT: %s creado; configuración cancelada — `workspace "
                "doctor` la completa" % name)
            return True, name
        _prog(progress, "tema", "run")
        okt = write_agent_theme(name, display, color, out=out)   # themes.json + themes-cc
        _prog(progress, "tema", "ok" if okt else "warn",
              "" if okt else "doctor lo completa")
        try:
            import install
            _prog(progress, "cableado", "run")
            install.configure_brain(name, defn, dest, owner or "owner")
            _prog(progress, "cableado", "ok")
            _prog(progress, "launcher", "run")
            install.install_launchers([name])
            _prog(progress, "launcher", "ok")
            out("AGENT: CONFIG:%s (hooks · statusline · launcher · tema)" % name)
        except Exception as e:
            warn_cfg = str(e)
            for k in ("cableado", "launcher"):
                _prog(progress, k, "warn", "doctor lo completa")
            out("AGENT: WARN: %s registrado pero no pude configurarlo (%s) — "
                "corre `workspace doctor`" % (name, e))
    else:
        for k in ("tema", "cableado", "launcher"):
            _prog(progress, k, "skip", "configure off")
    # ── verificación final (falla-suave: reporta, no revierte) ──
    _prog(progress, "verificacion", "run")
    try:
        ph = _scan_placeholders(dest)
        okd = bool(agentsreg.load_definition(dest).get("name") == name
                   and agentsreg.find(name))
        if ph:
            _prog(progress, "verificacion", "warn",
                  "%d placeholder(s) sin llenar" % len(ph))
        elif not okd:
            _prog(progress, "verificacion", "warn", "def/registro no legible")
        elif warn_cfg:
            _prog(progress, "verificacion", "warn", "config incompleta")
        else:
            _prog(progress, "verificacion", "ok")
    except Exception:
        _prog(progress, "verificacion", "warn", "no se pudo verificar")
    return True, name


def _name_from_folder(folder):
    """'MI - BRAIN' → 'mi'; 'mi-agente' → 'mi-agente'."""
    base = os.path.basename(os.path.normpath(folder))
    base = re.split(r"[ _-]*brain\b", base, flags=re.IGNORECASE)[0]
    slug = re.sub(r"[^a-z0-9_-]+", "-", base.strip().lower()).strip("-")
    return slug[:32] or "agente"


_PLACEHOLDER_RE = re.compile(r"\{\{[A-Z_]+\}\}")


def _scan_placeholders(folder):
    """Set de placeholders {{X}} del template que quedaron SIN llenar en el cerebro.
    Si hay, es señal de que se cargó un template crudo en vez de un agente configurado
    (load no rellena; solo create lo hace). Corta temprano a las ~8 clases."""
    found = set()
    for root, dirs, files in os.walk(folder):
        if ".git" in dirs:
            dirs.remove(".git")
        for fn in files:
            if not fn.endswith((".md", ".json", ".txt")):
                continue
            try:
                with open(os.path.join(root, fn), encoding="utf-8", errors="ignore") as fh:
                    found.update(_PLACEHOLDER_RE.findall(fh.read()))
            except Exception:
                pass
            if len(found) > 8:
                return found
    return found


#: Los PASOS REALES de load(), en orden — contrato para cualquier UI que
#: quiera pintar el proceso (add_agent_tui los pinta EN VIVO, igual que
#: CREATE_STEPS). Se reportan por `progress(key, st, note)`. Fuente única:
#: si load() gana un paso, se agrega AQUÍ.
LOAD_STEPS = (
    ("validar", "validar carpeta y colisiones"),
    ("identidad", "identidad (.workspace/agent.json)"),
    ("registro", "registro per-máquina (agents.local.json)"),
    ("cableado", "cableado del cerebro (hooks · statusline · tema)"),
    ("launcher", "comando en PATH (launcher)"),
    ("verificacion", "verificación (placeholders · registro)"),
)


def inspect_brain(folder):
    """Radiografía FALLA-SUAVE de una carpeta candidata a cerebro — para UIs
    que quieren ser transparentes ANTES de cargar (solo LEE, jamás escribe).
    Barata: unos stat + un json. Devuelve dict con:
      folder exists has_def name display tagline engine owner marcas
      estado ∈ '' (no existe) / nuevo / cargado (misma carpeta ya registrada,
      recargar = re-verificar) / colision (nombre cargado desde OTRA carpeta
      → load() lo rechazaría) · cargado_de (la otra carpeta, si colisión)."""
    info = {"folder": "", "exists": False, "has_def": False, "name": "",
            "display": "", "tagline": "", "engine": "", "owner": "",
            "marcas": [], "estado": "", "cargado_de": ""}
    raw = (folder or "").strip()
    if not raw:
        return info
    try:
        fab = os.path.abspath(os.path.expanduser(raw))
        info["folder"] = fab
        info["exists"] = os.path.isdir(fab)
        if not info["exists"]:
            return info
        info["has_def"] = agentsreg.has_definition(fab)
        d = agentsreg.load_definition(fab) if info["has_def"] else {}
        info["name"] = (str(d.get("name") or "").strip().lower()
                        or _name_from_folder(fab))
        info["display"] = str(d.get("display") or "")
        info["tagline"] = str(d.get("tagline") or "")
        info["engine"] = str(d.get("engine") or "")
        info["owner"] = str(d.get("owner") or "") or _detect_owner(fab)
        info["marcas"] = [
            ("CLAUDE.md", os.path.isfile(os.path.join(fab, "CLAUDE.md"))),
            ("BOOT", os.path.isdir(os.path.join(fab, "BOOT"))),
            ("STATE", os.path.isdir(os.path.join(fab, "STATE"))),
            ("skills", os.path.isdir(os.path.join(fab, "skills"))),
        ]
        existing = agentsreg.find(info["name"])
        if not existing:
            info["estado"] = "nuevo"
        elif os.path.realpath(existing["brain"]) == os.path.realpath(fab):
            info["estado"] = "cargado"
        else:
            info["estado"] = "colision"
            info["cargado_de"] = existing["brain"]
    except Exception:
        pass
    return info


def load(folder, name=None, out=print, progress=None):
    """Carga un agente apuntando a una carpeta de cerebro. Si no es
    autodescriptiva, la siembra. Registra en agents.local.json (per-máquina).
    `progress(key, st, note)` reporta CADA paso de LOAD_STEPS en vivo (la
    pantalla «Agregar agente» lo pinta). Devuelve (ok, name|error)."""
    folder = os.path.abspath(os.path.expanduser(folder or ""))
    _prog(progress, "validar", "run")
    if not os.path.isdir(folder):
        _prog(progress, "validar", "fail", "la carpeta no existe")
        return False, "la carpeta no existe: %s" % folder
    # nombre INTENCIONADO (antes de escribir nada) para chequear colisión
    if agentsreg.has_definition(folder):
        intended = (name or agentsreg.load_definition(folder).get("name")
                    or _name_from_folder(folder)).strip().lower()
    else:
        intended = (name or _name_from_folder(folder)).strip().lower()
    # colisión: mismo nombre YA cargado desde OTRA carpeta → no pisar en silencio
    existing = agentsreg.find(intended)
    if existing and os.path.realpath(existing["brain"]) != os.path.realpath(folder):
        _prog(progress, "validar", "fail", "colisión de nombre")
        return False, ("ya hay un agente '%s' cargado desde otra carpeta (%s). "
                       "Dale otro nombre." % (intended, existing["brain"]))
    _prog(progress, "validar", "ok")
    _prog(progress, "identidad", "run")
    if not agentsreg.has_definition(folder):
        ok, res = seed_definition(folder, name=intended, out=out)
        if not ok:
            _prog(progress, "identidad", "fail", "no se pudo sembrar")
            return False, res
        intended = res
        _prog(progress, "identidad", "ok", "def mínima sembrada (no había)")
    else:
        _prog(progress, "identidad", "ok", "def existente — se respeta")
    _prog(progress, "registro", "run")
    ok, err = agentsreg.add(intended, folder)
    if not ok:
        _prog(progress, "registro", "fail", "")
        return False, err
    _prog(progress, "registro", "ok")
    out("AGENT: LOAD:%s → %s" % (intended, folder))
    # Dejar el cerebro USABLE, no solo registrado: configurar hooks/statusline/
    # launcher/tema (igual que install). Antes `load` SOLO registraba → "Agregar
    # agente" dejaba el agente a medias y parecía que "no funcionaba". Idempotente,
    # falla-suave (si truena, queda registrado y `workspace doctor` lo completa).
    warn_cfg = ""
    try:
        import install
        cfg = agentsreg.load_definition(folder) or {"name": intended}
        try:
            socio = open(install.machine_socio_path(), encoding="utf-8").read().strip()
        except Exception:
            socio = ""
        _prog(progress, "cableado", "run")
        install.configure_brain(intended, cfg, folder, socio or "owner")
        _prog(progress, "cableado", "ok")
        _prog(progress, "launcher", "run")
        install.install_launchers([intended])
        _prog(progress, "launcher", "ok")
        out("AGENT: CONFIG:%s (hooks · statusline · launcher · tema)" % intended)
    except Exception as e:
        warn_cfg = str(e)
        for k in ("cableado", "launcher"):
            _prog(progress, k, "warn", "doctor lo completa")
        out("AGENT: WARN: %s registrado pero no pude configurarlo (%s) — "
            "corre `workspace doctor`" % (intended, e))
    _prog(progress, "verificacion", "run")
    ph = _scan_placeholders(folder)
    if ph:
        out("AGENT: WARN: el cerebro tiene placeholders del template SIN llenar (%s%s). "
            "Parece un template crudo, no un agente configurado — `load` no los rellena. "
            "Usa `create` para uno nuevo, o copia el cerebro real ya configurado."
            % (", ".join(sorted(ph)[:5]), " …" if len(ph) > 5 else ""))
        _prog(progress, "verificacion", "warn",
              "%d placeholder(s) sin llenar" % len(ph))
    elif warn_cfg:
        _prog(progress, "verificacion", "warn", "config incompleta")
    else:
        _prog(progress, "verificacion", "ok")
    return True, intended


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else ""
    if cmd == "separate":
        dry = "--apply" not in args
        res = separate(dry_run=dry)
        if dry:
            print("\n(dry-run — usa: agent_admin.py separate --apply)")
        return 0 if not res["errors"] else 1
    if cmd == "load" and len(args) >= 2:
        ok, res = load(args[1])
        print(("cargado: " + res) if ok else ("error: " + res))
        return 0 if ok else 1
    if cmd == "create" and len(args) >= 2:
        import argparse
        ap = argparse.ArgumentParser(prog="agent_admin.py create")
        ap.add_argument("name")
        ap.add_argument("--tagline", default="")
        ap.add_argument("--display", default=None)
        ap.add_argument("--owner", default="")
        ap.add_argument("--color", default="gris")
        ap.add_argument("--scope", default="")
        ap.add_argument("--soul", default="")
        ap.add_argument("--brain-dest", default=None)
        ap.add_argument("--engine", default="claude-code")
        ap.add_argument("--dry-run", action="store_true")
        a = ap.parse_args(args[1:])
        ok, res = create(a.name, tagline=a.tagline, display=a.display,
                         owner=a.owner, color=a.color, scope=a.scope,
                         soul=a.soul, brain_dest=a.brain_dest,
                         engine=a.engine, dry_run=a.dry_run)
        print(("creado: " + res) if ok else ("error: " + res))
        return 0 if ok else 1
    print("uso: agent_admin.py separate [--apply] | load <carpeta> | "
          "create <name> [--tagline ... --owner ... --color ...]")
    return 2


if __name__ == "__main__":
    sys.exit(main())
