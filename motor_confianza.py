#!/usr/bin/env python3
"""WORKSPACE · motor_confianza — la confianza que Workspace dejó en Codex y en
Antigravity para el cerebro de un agente, y cómo quitarla.

Qué escribe Workspace al abrir un agente (y nada más):
  · Codex (engines/codex.ensure_trusted): en `~/.codex/config.toml` (o
    `$CODEX_HOME/config.toml`) el bloque
        [projects."<cerebro>"]
        trust_level = "trusted"
    solo si ese cerebro no tenía ya una entrada, de ninguna forma.
  · Antigravity (engines/antigravity.ensure_brain_access): en
    `~/.gemini/antigravity-cli/settings.json` (o `$ANTIGRAVITY_CLI_HOME`) el
    cerebro en `trustedWorkspaces` y la regla `write_file(<cerebro>)` (o
    `read_file(<cerebro>)` con autonomía «ask») en `permissions.allow`.
  · Antigravity con autonomía full (ensure_agent_project): el proyecto
    `~/.gemini/config/projects/workspace-<agente>.json` con `command(*)`.

Lo usan `uninstall.py --limpiar-todo` (todos los cerebros) y quitar un agente
desde Agentes (agent_manage.unregister → quitar_de_agente: SOLO ese cerebro).
Reglas de las dos, las mismas:
  · solo lo que tiene EXACTAMENTE la forma que escribe Workspace: un bloque de
    Codex con otra clave o un comentario, otra regla, otra ruta (aunque sea
    vecina: `<cerebro> 2`, `<cerebro>/sub`), un proyecto con algo agregado →
    es del socio y se queda;
  · nunca se sigue un enlace simbólico ni se lee un archivo enorme o roto (no
    se toca);
  · escritura atómica que conserva los permisos del archivo; el resto del
    archivo queda byte a byte (TOML) o con las mismas claves (JSON).
Límite honesto: Codex escribe el MISMO bloque cuando el socio acepta su
pregunta «¿confías en esta carpeta?»; para el cerebro de un agente de
Workspace no se puede distinguir quién lo escribió (uninstall ya lo trataba así).

Stdlib, Python 3.9+, Mac/Linux/Windows. Falla-suave en quitar_de_agente.
"""
import json
import os
import tempfile
import time

_MAX = 1024 * 1024


# ── rutas e ids: los MISMOS que usa cada motor al escribir ───────────────────
def _cx():
    from engines import codex
    return codex


def _agy():
    from engines import antigravity
    return antigravity


def raiz(brain):
    """La forma en que Workspace escribe la ruta del cerebro en las dos configs
    (realpath: ensure_trusted y ensure_brain_access)."""
    return os.path.realpath(os.path.abspath(os.path.expanduser(str(brain))))


def codex_config():
    return _cx()._codex_config_path()


def agy_settings():
    return os.path.join(_agy()._agy_home(), "settings.json")


def agy_project_path(agent):
    """(id, ruta) del proyecto de agy del agente, o ("", "") sin nombre."""
    pid = _agy().project_id(agent)
    return (pid, os.path.join(_agy()._projects_dir(), pid + ".json")) if pid else ("", "")


# ── Codex ────────────────────────────────────────────────────────────────────
def strip_codex_trust(text, brain_roots, escape=None):
    """(texto nuevo, [cerebros]) del config.toml de Codex sin los bloques
    `[projects."<cerebro>"]` que agregó Workspace: solo si el bloque dice
    EXACTAMENTE `trust_level = "trusted"` (otra clave o un comentario = del
    socio, se deja). `escape`: el de engines/codex (por defecto)."""
    escape = escape or _cx()._toml_key_escape
    heads = {'[projects."%s"]' % escape(r): r for r in brain_roots}
    lines = (text or "").splitlines(True)
    out, gone, i, at_end = [], [], 0, False
    while i < len(lines):
        h = lines[i].strip()
        if h in heads:
            j = i + 1
            while j < len(lines) and not lines[j].lstrip().startswith("["):
                j += 1
            body = [ln.strip() for ln in lines[i + 1:j] if ln.strip()]
            if body == ['trust_level = "trusted"']:
                gone.append(heads[h])
                at_end = j >= len(lines)
                i = j
                continue
        out.append(lines[i])
        i += 1
    new = "".join(out)
    if gone and at_end and new.strip():
        new = new.rstrip("\n") + "\n"
    return new, gone


# ── Antigravity ──────────────────────────────────────────────────────────────
def limpiar_agy_cerebros(data, brain_roots):
    """(dict nuevo, {"confianza": n, "reglas": n}) del settings.json de
    Antigravity sin los cerebros de `brain_roots` en `trustedWorkspaces` ni
    sus reglas `write_file(<cerebro>)`/`read_file(<cerebro>)`. Lo demás
    (otras rutas, otras reglas, el resto de claves) queda igual."""
    cuenta = {"confianza": 0, "reglas": 0}
    if not isinstance(data, dict):
        return data, cuenta
    new = json.loads(json.dumps(data))
    roots = set(brain_roots)
    trusted = new.get("trustedWorkspaces")
    if isinstance(trusted, list):
        kept = [t for t in trusted if not (isinstance(t, str) and t in roots)]
        cuenta["confianza"] = len(trusted) - len(kept)
        if cuenta["confianza"]:
            new["trustedWorkspaces"] = kept
    perms = new.get("permissions")
    allow = perms.get("allow") if isinstance(perms, dict) else None
    if isinstance(allow, list):
        files = {"%s(%s)" % (k, r) for r in roots for k in ("write_file", "read_file")}
        kept = [x for x in allow if not (isinstance(x, str) and x in files)]
        cuenta["reglas"] = len(allow) - len(kept)
        if cuenta["reglas"]:
            perms["allow"] = kept
    return new, cuenta


def _read_json(path):
    """dict del JSON, o None (no existe, enlace, enorme, roto o no es objeto)."""
    try:
        if os.path.islink(path) or not os.path.isfile(path) or os.path.getsize(path) > _MAX:
            return None
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _read_text(path):
    try:
        if os.path.islink(path) or not os.path.isfile(path) or os.path.getsize(path) > _MAX:
            return None
        with open(path, encoding="utf-8", newline="") as fh:
            return fh.read()
    except (OSError, ValueError):
        return None


def agy_project_ours(path, pid, grant=None):
    """¿El proyecto de agy es el que crea Workspace, sin nada agregado? (mismo
    id que su nombre, sin recursos y como mucho la regla de autonomía full)."""
    grant = grant or _agy().FULL_GRANT
    d = _read_json(path)
    if d is None or d.get("id") != pid:
        return False
    # Cualquier cosa que no escribió Workspace (otra clave, reglas deny/ask,
    # recursos) = el socio lo editó → no se borra (Greptile, 2026-10-17).
    if set(d) - {"id", "name", "projectResources", "permissionGrants"}:
        return False
    if d.get("projectResources"):
        return False
    pg = d.get("permissionGrants") or {}
    if not isinstance(pg, dict) or set(pg) - {"permissionGrants", "v2Migrated"}:
        return False
    inner = pg.get("permissionGrants") or {}
    if not isinstance(inner, dict) or set(inner) - {"allow"}:
        return False
    allow = inner.get("allow") or []
    return isinstance(allow, list) and all(r == grant for r in allow)


# ── escribir ─────────────────────────────────────────────────────────────────
def escribir(path, text):
    """Atómico (temporal al lado + os.replace) y con los MISMOS permisos del
    original (la config de un motor puede ser 0600). Reintenta un instante si
    Windows tiene el archivo abierto (antivirus, indexador)."""
    mode = os.stat(path).st_mode & 0o777
    fd, tmp = tempfile.mkstemp(prefix="." + os.path.basename(path) + ".", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as fh:
            fh.write(text)
        if os.name != "nt":
            os.chmod(tmp, mode)
        for k in range(20):
            try:
                os.replace(tmp, path)
                break
            except PermissionError:
                if k == 19:
                    raise
                time.sleep(0.05 * (k + 1))
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# ── quitar un agente ─────────────────────────────────────────────────────────
def quitar_de_agente(brain, agent="", otros_cerebros=(), otros_agentes=()):
    """Quita lo que Workspace escribió en Codex y Antigravity para el cerebro
    de UN agente que se quita: su bloque de confianza de Codex, su entrada en
    `trustedWorkspaces` y sus reglas de archivos en agy, y su proyecto
    `workspace-<agente>` de agy si sigue tal cual lo creó Workspace.

    `otros_cerebros`: los cerebros de los agentes que SIGUEN registrados; si
    alguno es el mismo cerebro, su confianza se queda (la usa ese otro agente).
    `otros_agentes`: sus nombres (un proyecto de agy con el mismo id se queda).
    → lista de lo quitado: "codex", "agy_confianza", "agy_reglas",
    "agy_proyecto". Falla-suave por motor: nunca lanza."""
    hechos = []
    if not brain:
        return hechos
    r = raiz(brain)
    compartido = any(raiz(o) == r for o in otros_cerebros or () if o)
    if not compartido:
        try:
            cfg = codex_config()
            txt = _read_text(cfg)
            if txt is not None:
                nuevo, gone = strip_codex_trust(txt, [r])
                if gone:
                    escribir(cfg, nuevo)
                    hechos.append("codex")
        except Exception:
            pass
        try:
            ap = agy_settings()
            data = _read_json(ap)
            if data is not None:
                nuevo, cuenta = limpiar_agy_cerebros(data, [r])
                if cuenta["confianza"] or cuenta["reglas"]:
                    escribir(ap, json.dumps(nuevo, indent=2, ensure_ascii=False) + "\n")
                    if cuenta["confianza"]:
                        hechos.append("agy_confianza")
                    if cuenta["reglas"]:
                        hechos.append("agy_reglas")
        except Exception:
            pass
    try:
        pid, p = agy_project_path(agent)
        if pid and pid not in {agy_project_path(a)[0] for a in otros_agentes or () if a}:
            if agy_project_ours(p, pid):
                os.unlink(p)
                hechos.append("agy_proyecto")
    except Exception:
        pass
    return hechos
