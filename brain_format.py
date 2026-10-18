#!/usr/bin/env python3
"""WORKSPACE · brain_format — lleva un cerebro al formato v2 (identidad neutral
`BRAIN.md`), de forma SEGURA, IDEMPOTENTE y DETERMINISTA.

Una sola función, `ensure_brain_format(brain)`, llamada desde TRES puertas para
que ningún cerebro se quede atrás (los sellos de migración son por máquina y
una instalación nueva los da todos por hechos):
  1. la migración 202610151600_brain_identity_neutral (`workspace update`);
  2. `agent_admin.load` (al cargar un agente);
  3. `workspace doctor --fix` (fase 4c).

Qué hace con un cerebro VIEJO (solo `CLAUDE.md` con la identidad):
  respaldo → `BRAIN.md` = copia BYTE A BYTE de `CLAUDE.md` (atómico, solo si no
  existe) → verifica bytes → `CLAUDE.md` pasa a puntero generado (`@BRAIN.md`)
  → `motores/` con su README si falta → líneas con el nombre anterior del producto que vengan TAL CUAL
  del template viejo se renombran (si el cliente las editó, no se tocan).

Reglas (formato v2, decisión del dueño 2026-10-15):
  · NUNCA borra (solo `undo`, a pedido explícito y si nada cambió después).
    `undo` solo pisa o quita lo que hoy es EXACTAMENTE lo que escribió la
    migración, verifica cada respaldo (sha) antes de tocar nada, se niega si
    falta `BRAIN.md` y habría que restaurar `CLAUDE.md` (o el cerebro quedaría
    sin identidad), y si ya no queda nada que deshacer lo dice y sale bien.
  · Si `CLAUDE.md` ya apunta a `BRAIN.md` (marca o `@BRAIN.md`) y `BRAIN.md`
    falta (Obsidian aún no lo trae a esta máquina, se borró…) o es a su vez un
    puntero (lo que dejó una versión anterior), NUNCA se copia el puntero como
    identidad: estado `missing`, no se toca nada (ni con opt-out) y `doctor` lo
    marca como error.
  · Un `CLAUDE.md` editado por el cliente se mueve tal cual: no es motivo de salto.
  · Se SALTA y se reporta, sin tocar nada, cualquier cerebro raro: identidad
    personalizada (`identity_doc` propio), `CLAUDE.md` inexistente/ilegible/
    enlace/demasiado grande, cerebro dentro del propio harness, archivos de
    conflicto de sync al lado, o `CLAUDE.md` modificado hace muy poco (sync en
    curso). Ese cerebro sigue funcionando con el formato viejo (release A).
  · Salida determinista (mismos bytes en cualquier máquina): sin fechas ni rutas
    absolutas en lo que se escribe en el cerebro. Dos máquinas que migran el
    mismo cerebro sincronizado llegan a lo mismo.

Stdlib puro, Python 3.9+. Nunca levanta hacia el que llama: los errores vuelven
en el resultado (`state="error"`).
"""
import hashlib
import json
import os
import re
import time

import brain_identity as bi

ROOT = os.path.dirname(os.path.abspath(__file__))
MID = "202610151600_brain_identity_neutral"

#: Margen para no pisar un `CLAUDE.md` que se acaba de modificar (posible sync
#: de Obsidian en curso desde otra máquina). Se reintenta por otra puerta.
MIN_AGE_SECONDS = 120
MAX_IDENTITY_BYTES = 1024 * 1024

_LEGACY_DATA = os.path.join(ROOT, "migrations", "data", "legacy_template_lines.json")
_MOTORES_README = os.path.join(ROOT, "templates", "agent", "brain", "motores", "README.md")
_PLACEHOLDER = re.compile(r"\{\{[A-Z_]+\}\}")

# Estados (resultado["state"])
MIGRATED = "migrated"          # viejo → v2 en esta corrida
COMPLETED = "completed"        # medio migrado (BRAIN.md ya estaba) → completado
OK = "ok"                      # ya estaba en v2 (puede haber resincronizado el puntero)
SKIPPED = "skipped"            # raro: no se tocó (ver reason)
CONFLICT = "conflict"          # BRAIN.md y CLAUDE.md distintos: no se tocó
MISSING = "missing"            # CLAUDE.md apunta a BRAIN.md y BRAIN.md falta: no se tocó
ERROR = "error"


# ── utilidades ──────────────────────────────────────────────────────────────
def _sha(data):
    return hashlib.sha256(data).hexdigest()


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def _file_sha(path):
    """sha del archivo; None si no existe, '' si no se pudo leer."""
    if not os.path.isfile(path):
        return None
    try:
        return _sha(_read_bytes(path))
    except OSError:
        return ""


def _atomic_write(path, data):
    """Escritura atómica de BYTES (tmp en la misma carpeta + os.replace)."""
    tmp = "%s.workspace-tmp-%d" % (path, os.getpid())
    try:
        with open(tmp, "wb") as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _norm(data):
    """Contenido normalizado para comparar (fin de línea y espacios finales)."""
    txt = data.decode("utf-8", "replace").replace("\r\n", "\n")
    return "\n".join(ln.rstrip() for ln in txt.split("\n")).strip()


def _first_heading(data):
    """Primer encabezado `# …` de la identidad (contenido SINCRONIZADO →
    determinista entre máquinas; el agent.json vive en `.workspace/`, que
    Obsidian no sincroniza)."""
    for ln in data.decode("utf-8", "replace").splitlines():
        s = ln.strip()
        if s.startswith("# ") and len(s) > 2:
            return s[2:].strip()[:80]
    return ""


def has_import(text):
    """¿`@BRAIN.md` en su propia línea y FUERA de bloques de código? (Claude
    Code no expande imports dentro de ``` ni entre backticks)."""
    fence = False
    for ln in str(text or "").splitlines():
        s = ln.strip()
        if s.startswith("```") or s.startswith("~~~"):
            fence = not fence
            continue
        if not fence and s == "@" + bi.IDENTITY_DOC:
            return True
    return False


def _is_pointer(data):
    """¿Estos bytes son un puntero a BRAIN.md (marca generada o `@BRAIN.md`)
    y no una identidad?"""
    txt = data.decode("utf-8", "replace")
    return bi.is_identity_pointer(txt) or has_import(txt)


def _heading_source(identity_bytes):
    """La identidad tal como quedará tras renombrar las líneas con el nombre anterior del
    template viejo: el encabezado del puntero sale de AHÍ, así una segunda
    corrida no lo vuelve a cambiar (idempotencia)."""
    rows = _legacy_table().get(bi.LEGACY_IDENTITY_DOC) or []
    try:
        return _rename_lines(identity_bytes, rows)[0] if rows else identity_bytes
    except UnicodeDecodeError:
        return identity_bytes


def _pointer_bytes(identity_bytes, current=None):
    """Puntero generado + zona libre del dueño (lo de abajo de la marca de fin
    del puntero actual se conserva tal cual)."""
    gen = bi.pointer_text(_first_heading(_heading_source(identity_bytes)))
    body = gen[:gen.index(bi.POINTER_END) + len(bi.POINTER_END)]
    tail = "\n"
    if current is not None:
        cur = current.decode("utf-8", "replace")
        if bi.POINTER_END in cur:
            t = cur[cur.index(bi.POINTER_END) + len(bi.POINTER_END):]
            tail = t if t else "\n"
    return (body + tail).encode("utf-8")


def write_pointer(brain):
    """Escribe el CLAUDE.md puntero de un cerebro v2 con el MISMO generador
    que usan la migración, `load` y el doctor (_pointer_bytes), conservando la
    zona libre del dueño. Lo usa «crear agente»: antes escribía su propia
    plantilla y el primer doctor la reescribía (B11). Devuelve True si
    escribió. Lanza si falta BRAIN.md (quien llama revierte)."""
    ident = _read_bytes(os.path.join(brain, bi.IDENTITY_DOC))
    claude = os.path.join(brain, bi.LEGACY_IDENTITY_DOC)
    cur = _read_bytes(claude) if os.path.isfile(claude) else None
    want = _pointer_bytes(ident, cur)
    if want == cur:
        return False
    _atomic_write(claude, want)
    return True


def _cfg_for(brain, cfg=None):
    if cfg is not None:
        return cfg
    try:
        with open(os.path.join(brain, ".workspace", "agent.json"), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def _inside(child, parent):
    c, p = os.path.realpath(child), os.path.realpath(parent)
    return c == p or c.startswith(p + os.sep)


def _conflict_files(brain):
    """Archivos de conflicto de sync junto a la identidad (Obsidian, Syncthing,
    Dropbox…: el nombre trae «conflict»)."""
    try:
        names = os.listdir(brain)
    except OSError:
        return []
    out = []
    for n in names:
        low = n.lower()
        if "conflict" in low and (low.startswith("claude") or low.startswith("brain")):
            out.append(n)
    return sorted(out)


# ── tabla de líneas con el nombre anterior (template viejo) ───────────────
_TABLE = None


def patron_linea(linea):
    """(regex, {marcador: grupo}) de UNA línea de la plantilla: cada `{{X}}`
    es comodín (lo que el instanciador rellenó; el mismo marcador repetido
    debe valer lo mismo) y el resto se compara LITERAL, entera. Lo comparten
    esta tabla y sin_aprobacion (regla 5: una sola forma de reconocer una
    línea de la plantilla)."""
    parts, last, seen = [], 0, {}
    for m in _PLACEHOLDER.finditer(linea):
        parts.append(re.escape(linea[last:m.start()]))
        tok = m.group(0)
        if tok in seen:
            parts.append("(?P=%s)" % seen[tok])
        else:
            g = "p%d" % len(seen)
            seen[tok] = g
            parts.append("(?P<%s>.+?)" % g)
        last = m.end()
    parts.append(re.escape(linea[last:]))
    return re.compile("".join(parts) + r"\Z"), seen


def _legacy_table():
    """{archivo: [(regex, nueva, nombres_placeholder)]} desde el JSON generado.
    Placeholders `{{X}}` = comodín (lo que el instanciador rellenó); el resto de
    la línea se compara LITERAL. Una línea editada por el cliente no coincide."""
    global _TABLE
    if _TABLE is not None:
        return _TABLE
    table = {}
    try:
        with open(_LEGACY_DATA, encoding="utf-8") as fh:
            data = json.load(fh).get("files") or {}
    except Exception:
        data = {}
    for rel, rows in data.items():
        out = []
        for row in rows:
            old, new = row.get("old", ""), row.get("new", "")
            names = _PLACEHOLDER.findall(old)
            if any(n not in names for n in _PLACEHOLDER.findall(new)):
                continue                      # no se podría rellenar la nueva
            rx, seen = patron_linea(old)
            out.append((rx, new, seen))
        table[rel] = out
    _TABLE = table
    return table


def _rename_lines(data, rows):
    """(nuevos_bytes, n_cambiadas). Conserva finales de línea."""
    txt = data.decode("utf-8")
    out, n = [], 0
    for ln in txt.splitlines(True):
        body = ln.rstrip("\r\n")
        eol = ln[len(body):]
        for rx, new, seen in rows:
            m = rx.match(body)
            if m:
                rep = new
                for tok, g in seen.items():
                    rep = rep.replace(tok, m.group(g))
                if rep != body:
                    body = rep
                    n += 1
                break
        out.append(body + eol)
    return "".join(out).encode("utf-8"), n


def _legacy_targets(brain):
    """[(ruta_absoluta, filas)] de archivos del cerebro cubiertos por la tabla.
    Las filas de `CLAUDE.md` del template viejo aplican a `BRAIN.md` (ahí vive
    ahora ese contenido)."""
    out = []
    for rel, rows in _legacy_table().items():
        target = bi.IDENTITY_DOC if rel == bi.LEGACY_IDENTITY_DOC else rel
        path = os.path.join(brain, *target.split("/"))
        if rows and os.path.isfile(path) and not os.path.islink(path):
            out.append((path, rows))
    return out


# ── respaldo / manifiesto ───────────────────────────────────────────────────
def _backup_dir(state_dir, brain, name=None):
    real = os.path.realpath(brain)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", name or os.path.basename(real)) or "cerebro"
    return os.path.join(state_dir, "backups", MID, "%s-%s" % (safe, _sha(real.encode())[:8]))


def _manifest_path(bdir):
    return os.path.join(bdir, "manifest.json")


def _load_manifest(bdir):
    try:
        with open(_manifest_path(bdir), encoding="utf-8") as fh:
            m = json.load(fh)
        return m if isinstance(m, dict) else {}
    except Exception:
        return {}


def _save_manifest(bdir, man):
    os.makedirs(bdir, exist_ok=True)
    tmp = _manifest_path(bdir) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(man, fh, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(tmp, _manifest_path(bdir))


def _backup_file(bdir, man, brain, path):
    """Copia `path` al respaldo (una sola vez: la primera versión es la que se
    restaura) y anota su sha original."""
    rel = os.path.relpath(path, brain).replace(os.sep, "/")
    files = man.setdefault("files", {})
    if rel in files:
        return
    data = _read_bytes(path)
    dest = os.path.join(bdir, "files", *rel.split("/"))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as fh:
        fh.write(data)
    files[rel] = {"orig_sha": _sha(data), "written_sha": ""}


def _note_written(man, brain, path, data):
    """Anota el sha de lo que la migración va a dejar en `path`. Se llama ANTES
    de escribir: si la escritura falla o se corta, `undo` ya sabe qué esperar
    y no pisa lo que el dueño edite después. Solo se actualiza si lo que hay
    hoy es lo esperado (lo que escribió antes, su original respaldado, nada si
    lo crea, o ya lo nuevo): si alguien lo cambió en medio, lo nuevo puede
    llevar cambios del dueño que el respaldo no tiene (p. ej. notas en la zona
    libre de un puntero que se regenera) → queda la marca anterior y `undo` se
    niega a pisarlo."""
    rel = os.path.relpath(path, brain).replace(os.sep, "/")
    info = man.setdefault("files", {}).setdefault(rel, {"orig_sha": "", "written_sha": ""})
    new, cur = _sha(data), _file_sha(path)
    if cur in {info.get("written_sha"), info.get("orig_sha"), new} - {"", None} \
            or (cur is None and not info.get("orig_sha")):
        info["written_sha"] = new


def nota_cambio_de_workspace(brain, rel, antes, despues, state_dir):
    """Otro ajuste DE WORKSPACE (no del dueño) reescribió `rel` después de
    esta migración: memoria v1 cambia la §2.5 de BRAIN.md y el README de
    sesiones (memoria_textos); sin_aprobacion, los textos que pedían
    aprobación. Si lo que había era EXACTAMENTE lo que esta migración dejó, el
    manifiesto pasa a esperar lo nuevo y `undo` sigue funcionando; sin esto se
    negaba en todos esos cerebros desde el primer día (revisión 0.3.4). Una
    edición del dueño en medio no coincide: queda la marca anterior y `undo`
    se sigue negando a pisarla. `despues=None` = Workspace ARCHIVÓ `rel` (lo
    movió a otra carpeta; nada se borra: sin_aprobacion pasa
    skills/_propuestas/README.md a skills/_archive/): `undo` deja de esperarlo
    en su lugar. → True si anotó."""
    base = os.path.join(state_dir, "backups", MID)
    tail = "-" + _sha(os.path.realpath(brain).encode())[:8]
    try:
        names = sorted(n for n in os.listdir(base) if n.endswith(tail))
    except OSError:
        return False
    hecho = False
    for n in names:
        bdir = os.path.join(base, n)
        man = _load_manifest(bdir)
        files = man.get("files") or {}
        info = files.get(rel)
        if info and info.get("written_sha") == _sha(antes):
            if despues is None:
                del files[rel]
            else:
                info["written_sha"] = _sha(despues)
            _save_manifest(bdir, man)
            hecho = True
    return hecho


# ── opt-out tras un undo (por máquina) ──────────────────────────────────────
def _optout_path(state_dir):
    return os.path.join(state_dir, "brain-format", "optout.json")


def _optouts(state_dir):
    try:
        with open(_optout_path(state_dir), encoding="utf-8") as fh:
            d = json.load(fh)
        return set(d) if isinstance(d, list) else set()
    except Exception:
        return set()


def _add_optout(state_dir, brain):
    s = _optouts(state_dir)
    s.add(os.path.realpath(brain))
    os.makedirs(os.path.dirname(_optout_path(state_dir)), exist_ok=True)
    with open(_optout_path(state_dir), "w", encoding="utf-8") as fh:
        json.dump(sorted(s), fh, ensure_ascii=False, indent=2)


# ── clasificación (solo lectura) ────────────────────────────────────────────
def classify(brain, cfg=None, state_dir=None, now=None, min_age=MIN_AGE_SECONDS):
    """(estado, motivo) SIN tocar nada. Estados: 'old' (migrable), 'half'
    (BRAIN.md + CLAUDE.md sin marca, igual), 'v2', 'v2-no-pointer',
    'v2-client-pointer' (puntero del cliente con @BRAIN.md), 'v2-no-brain'
    (CLAUDE.md ya apunta a BRAIN.md y BRAIN.md falta), 'v2-brain-pointer'
    (BRAIN.md es otro puntero, no la identidad), 'conflict', 'skip'."""
    brain = str(brain or "")
    if not brain or not os.path.isdir(brain):
        return "skip", "la carpeta del cerebro no existe"
    if _inside(brain, ROOT):
        return "skip", "cerebro dentro del propio Workspace (semilla/template)"
    # El opt-out (deshacer a pedido en esta máquina) solo frena lo que
    # ESCRIBIRÍA. Un cerebro sin identidad no escribe nada y se reporta igual:
    # si no, el doctor diría OK justo en la máquina que deshizo.
    optout = bool(state_dir) and os.path.realpath(brain) in _optouts(state_dir)
    optout_why = "migración deshecha a pedido en esta máquina (opt-out)"
    cfg = _cfg_for(brain, cfg)
    explicit = bi.safe_doc_name(cfg.get("identity_doc"))
    if explicit and explicit not in (bi.IDENTITY_DOC, bi.LEGACY_IDENTITY_DOC):
        return "skip", "identidad personalizada (identity_doc = %s)" % explicit
    claude = os.path.join(brain, bi.LEGACY_IDENTITY_DOC)
    brainmd = os.path.join(brain, bi.IDENTITY_DOC)
    for p in (claude, brainmd):
        if os.path.islink(p):
            return "skip", "%s es un enlace simbólico" % os.path.basename(p)
    has_c, has_b = os.path.isfile(claude), os.path.isfile(brainmd)
    if has_b:
        try:
            b, b_err = _read_bytes(brainmd), None
        except OSError as e:
            b, b_err = None, e
        if b is not None and _is_pointer(b):
            # BRAIN.md es OTRO puntero (el que una versión anterior copió como
            # identidad cuando faltaba BRAIN.md): no hay identidad en ningún lado
            return "v2-brain-pointer", ("BRAIN.md es un puntero que se importa a sí mismo, no la "
                                        "identidad (lo dejó así una versión anterior): no se tocó nada")
        if optout:
            return "skip", optout_why
        if not has_c:
            return "v2-no-pointer", "falta el puntero CLAUDE.md"
        try:
            c = _read_bytes(claude)
        except OSError as e:
            return "skip", "CLAUDE.md ilegible (%s)" % e
        txt = c.decode("utf-8", "replace")
        if bi.is_identity_pointer(txt):
            return "v2", ""
        if has_import(txt):
            return "v2-client-pointer", "CLAUDE.md propio del cliente con @BRAIN.md"
        if b is None:
            return "skip", "BRAIN.md ilegible (%s)" % b_err
        if _norm(c) == _norm(b):
            return "half", "BRAIN.md ya existe con el mismo contenido"
        return "conflict", "BRAIN.md y CLAUDE.md tienen identidades distintas"
    if not has_c:
        return "skip", "no hay archivo de identidad (ni CLAUDE.md ni BRAIN.md)"
    try:
        st = os.stat(claude)
    except OSError as e:
        return "skip", "CLAUDE.md ilegible (%s)" % e
    if st.st_size > MAX_IDENTITY_BYTES:
        return "skip", "CLAUDE.md demasiado grande (%d bytes)" % st.st_size
    try:
        data = _read_bytes(claude)
    except OSError as e:
        return "skip", "CLAUDE.md ilegible (%s)" % type(e).__name__
    if _is_pointer(data):
        # CLAUDE.md YA apunta a BRAIN.md y BRAIN.md no está (Obsidian aún no
        # lo trae a esta máquina, se borró o se renombró): copiarlo como
        # identidad dejaría al agente sin ella. No se toca nada; doctor avisa.
        return "v2-no-brain", ("CLAUDE.md ya apunta a BRAIN.md pero BRAIN.md no está "
                               "(¿Obsidian aún no lo sincroniza, o se borró?): no se tocó nada")
    if optout:
        return "skip", optout_why
    conf = _conflict_files(brain)
    if conf:
        return "skip", "archivos de conflicto de sync al lado: %s" % ", ".join(conf[:3])
    t = time.time() if now is None else now
    if min_age and t - st.st_mtime < min_age:
        return "skip", "CLAUDE.md se modificó hace menos de %d s (posible sync en curso)" % min_age
    try:
        data.decode("utf-8")
    except UnicodeDecodeError as e:
        return "skip", "CLAUDE.md ilegible (%s)" % type(e).__name__
    return "old", ""


# ── la función ──────────────────────────────────────────────────────────────
def ensure_brain_format(brain, cfg=None, state_dir=None, name=None, dry_run=False,
                        now=None, min_age=MIN_AGE_SECONDS):
    """Lleva `brain` al formato v2. Devuelve {state, reason, changed:[rutas
    relativas], legacy_lines:int}. Nunca levanta. `dry_run` = solo dice qué
    haría (para `needed()` y para doctor sin --fix)."""
    res = {"brain": str(brain), "state": OK, "reason": "", "changed": [], "legacy_lines": 0}
    try:
        if state_dir is None:
            import paths
            state_dir = paths.state_dir()
        kind, why = classify(brain, cfg, state_dir=state_dir, now=now, min_age=min_age)
        res["reason"] = why
        if kind == "skip":
            res["state"] = SKIPPED
            return res
        if kind == "conflict":
            res["state"] = CONFLICT
            return res
        if kind in ("v2-no-brain", "v2-brain-pointer"):
            res["state"] = MISSING
            return res
        claude = os.path.join(brain, bi.LEGACY_IDENTITY_DOC)
        brainmd = os.path.join(brain, bi.IDENTITY_DOC)
        bdir = _backup_dir(state_dir, brain, name)
        man = _load_manifest(bdir)
        man.setdefault("realpath", os.path.realpath(brain))
        man.setdefault("mid", MID)
        plan = []                                     # (ruta, bytes nuevos)

        if kind == "old":
            res["state"] = MIGRATED
            ident = _read_bytes(claude)
            plan.append((brainmd, ident, "create"))
            plan.append((claude, _pointer_bytes(ident), "write"))
        elif kind == "half":
            res["state"] = COMPLETED
            ident = _read_bytes(brainmd)
            plan.append((claude, _pointer_bytes(ident), "write"))
        elif kind == "v2-no-pointer":
            ident = _read_bytes(brainmd)
            plan.append((claude, _pointer_bytes(ident), "create"))
        elif kind == "v2":
            ident = _read_bytes(brainmd)
            cur = _read_bytes(claude)
            want = _pointer_bytes(ident, cur)
            if want != cur:
                plan.append((claude, want, "write"))
        else:                                         # v2-client-pointer
            ident = None

        if dry_run:
            res["changed"] = [os.path.relpath(p, brain).replace(os.sep, "/") for p, _, _ in plan]
            if kind in ("v2", "v2-no-pointer", "v2-client-pointer", "old", "half"):
                res["changed"] += _dry_extras(brain, assume_v2=True)
            if not res["changed"] and res["state"] in (MIGRATED, COMPLETED):
                res["state"] = OK
            return res

        # 1) identidad + puntero (orden seguro ante caídas: BRAIN.md primero)
        for path, data, mode in plan:
            if os.path.isfile(path):
                _backup_file(bdir, man, brain, path)
            elif mode == "create":
                man.setdefault("created", [])
                rel = os.path.relpath(path, brain).replace(os.sep, "/")
                if rel not in man["created"]:
                    man["created"].append(rel)
            _note_written(man, brain, path, data)     # ANTES de escribir
            _save_manifest(bdir, man)
            if mode == "create" and os.path.exists(path) and path == brainmd:
                # otra máquina lo creó en medio: solo seguir si es idéntico
                if _read_bytes(path) != data:
                    res["state"] = CONFLICT
                    res["reason"] = "BRAIN.md apareció con otro contenido durante la migración"
                    return res
            else:
                _atomic_write(path, data)
            if _read_bytes(path) != data:
                raise IOError("verificación de bytes falló en %s" % os.path.basename(path))
            res["changed"].append(os.path.relpath(path, brain).replace(os.sep, "/"))

        # 2) motores/ con su README (solo agrega)
        mdir = os.path.join(brain, "motores")
        readme = os.path.join(mdir, "README.md")
        if not os.path.exists(readme) and os.path.isfile(_MOTORES_README):
            data = _read_bytes(_MOTORES_README)
            if not os.path.isdir(mdir):
                man.setdefault("created", [])
                if "motores/" not in man["created"]:
                    man["created"].append("motores/")
            os.makedirs(mdir, exist_ok=True)
            man.setdefault("created", [])
            if "motores/README.md" not in man["created"]:
                man["created"].append("motores/README.md")
            _note_written(man, brain, readme, data)
            _save_manifest(bdir, man)
            _atomic_write(readme, data)
            res["changed"].append("motores/README.md")

        # 3) líneas con el nombre anterior que vienen TAL CUAL del template viejo
        for path, rows in _legacy_targets(brain):
            try:
                cur = _read_bytes(path)
                new, n = _rename_lines(cur, rows)
            except (OSError, UnicodeDecodeError):
                continue
            if n and new != cur:
                _backup_file(bdir, man, brain, path)
                _note_written(man, brain, path, new)
                _save_manifest(bdir, man)
                _atomic_write(path, new)
                res["legacy_lines"] += n
                rel = os.path.relpath(path, brain).replace(os.sep, "/")
                if rel not in res["changed"]:
                    res["changed"].append(rel)

        if not res["changed"] and res["state"] in (MIGRATED, COMPLETED):
            res["state"] = OK
        return res
    except Exception as e:
        res["state"] = ERROR
        res["reason"] = "%s: %s" % (type(e).__name__, e)
        return res


def _dry_extras(brain, assume_v2=False):
    """Qué más tocaría ensure (motores/ y líneas con el nombre anterior), sin escribir."""
    out = []
    if not os.path.exists(os.path.join(brain, "motores", "README.md")) and os.path.isfile(_MOTORES_README):
        out.append("motores/README.md")
    targets = _legacy_targets(brain)
    if assume_v2 and not os.path.isfile(os.path.join(brain, bi.IDENTITY_DOC)):
        # cerebro viejo: las filas de CLAUDE.md se aplicarán al BRAIN.md copiado
        rows = _legacy_table().get(bi.LEGACY_IDENTITY_DOC) or []
        claude = os.path.join(brain, bi.LEGACY_IDENTITY_DOC)
        if rows and os.path.isfile(claude):
            targets.append((claude, rows))
    for path, rows in targets:
        try:
            _, n = _rename_lines(_read_bytes(path), rows)
        except (OSError, UnicodeDecodeError):
            continue
        if n:
            rel = os.path.relpath(path, brain).replace(os.sep, "/")
            out.append(bi.IDENTITY_DOC if rel == bi.LEGACY_IDENTITY_DOC else rel)
    return out


# ── chequeo para doctor (solo lectura) ──────────────────────────────────────
def _identity_backup(state_dir, brain):
    """Respaldo en ESTA máquina de la identidad de `brain` (su CLAUDE.md de
    antes de migrar): ruta si existe, está sano y no es un puntero; si no, ''."""
    if not state_dir:
        return ""
    base = os.path.join(state_dir, "backups", MID)
    tail = "-" + _sha(os.path.realpath(brain).encode())[:8]
    try:
        names = sorted(n for n in os.listdir(base) if n.endswith(tail))
    except OSError:
        return ""
    for n in names:
        files = _load_manifest(os.path.join(base, n)).get("files") or {}
        info = files.get(bi.LEGACY_IDENTITY_DOC) or {}
        src = os.path.join(base, n, "files", bi.LEGACY_IDENTITY_DOC)
        try:
            data = _read_bytes(src)
        except OSError:
            continue
        if info.get("orig_sha") == _sha(data) and not _is_pointer(data):
            return src
    return ""


def check(brain, cfg=None, state_dir=None, now=None):
    """[(nivel, mensaje)] — nivel 'ok' | 'warn' | 'error'. Solo lectura."""
    kind, why = classify(brain, cfg, state_dir=state_dir, now=now, min_age=0)
    if kind in ("v2-no-brain", "v2-brain-pointer"):
        if kind == "v2-no-brain":
            msg = ("falta BRAIN.md, la identidad a la que apunta CLAUDE.md: el agente "
                   "arrancaría sin ella. No se tocó nada")
        else:
            msg = ("BRAIN.md no tiene la identidad: es un puntero que se importa a sí mismo "
                   "(lo dejó así una versión anterior) y el agente arranca sin ella. "
                   "No se tocó nada")
        bak = _identity_backup(state_dir, brain)
        if bak:
            msg += " — respaldo de la identidad en esta máquina: %s" % bak
        return [("error", msg)]
    if kind == "v2":
        txt = _read_bytes(os.path.join(brain, bi.LEGACY_IDENTITY_DOC)).decode("utf-8", "replace")
        if not has_import(txt):
            return [("warn", "CLAUDE.md perdió `@BRAIN.md`: Claude Code no cargaría la identidad")]
        return [("ok", "formato v2 (identidad en BRAIN.md)")]
    if kind == "v2-client-pointer":
        return [("ok", "formato v2 (CLAUDE.md propio del cliente, con @BRAIN.md)")]
    if kind == "v2-no-pointer":
        return [("warn", "falta CLAUDE.md (puntero): Claude Code no cargaría la identidad")]
    if kind == "old":
        return [("warn", "formato viejo (identidad en CLAUDE.md): pendiente de pasar a BRAIN.md")]
    if kind == "half":
        return [("warn", "migración a medias (BRAIN.md listo, falta el puntero)")]
    if kind == "conflict":
        return [("warn", "conflicto: BRAIN.md y CLAUDE.md tienen identidades distintas — no se toca; revísalo")]
    return [("ok", "formato viejo, se respeta: %s" % why)]


# ── deshacer (a pedido) ─────────────────────────────────────────────────────
def _free_zone(data):
    """Zona libre del dueño en un CLAUDE.md puntero (lo de abajo de la marca de
    fin), normalizada; '' si no hay."""
    txt = data.decode("utf-8", "replace")
    i = txt.find(bi.POINTER_END)
    return _norm(txt[i + len(bi.POINTER_END):].encode("utf-8")) if i >= 0 else ""


def _undo_plan(bdir, man, brain):
    """(motivo, restaurar, quitar) SIN tocar nada; `motivo` no vacío = no se
    deshace este cerebro. Un archivo respaldado se restaura solo si hoy es
    EXACTAMENTE lo que escribió la migración y su respaldo existe con el sha
    original; lo creado se quita solo si sigue idéntico; y nunca se deja el
    cerebro sin identidad. `restaurar` = [(rel, bytes verificados)]; los dos
    vacíos = ya no queda nada que deshacer (p. ej. un 2º «deshacer»)."""
    has_brainmd = os.path.isfile(os.path.join(brain, bi.IDENTITY_DOC))
    no_brainmd = ("BRAIN.md no está en esta máquina (¿Obsidian aún no lo sincroniza, o se "
                  "borró?): espera a que termine o restáuralo antes de deshacer")
    files = man.get("files") or {}
    created = [r for r in (man.get("created") or []) if not r.endswith("/")]
    restore, remove, changed, bad = [], [], [], []
    for rel, info in sorted(files.items()):
        orig, w = info.get("orig_sha"), info.get("written_sha")
        p = os.path.join(brain, *rel.split("/"))
        cur = _file_sha(p)
        if not orig:                                  # lo creó la migración
            if rel in created and cur is not None:
                (remove if w and cur == w else changed).append(rel)
            continue
        if cur == orig:
            continue                                  # sigue (o volvió) a su original
        if not w or cur != w:
            changed.append(rel)                       # editado/borrado después, o sin constancia
            continue
        try:
            data = _read_bytes(os.path.join(bdir, "files", *rel.split("/")))
        except OSError:
            data = None
        if data is None or _sha(data) != orig:
            bad.append(rel)                           # respaldo faltante o dañado
            continue
        restore.append((rel, data))
    for rel in created:                               # creado sin sha anotado (versión anterior)
        if rel not in files and os.path.isfile(os.path.join(brain, *rel.split("/"))):
            changed.append(rel)
    if changed:
        return ("se editó después de migrar (%s): no se deshace para no perder cambios"
                % ", ".join(sorted(set(changed))[:4])), [], []
    if bad:
        return ("el respaldo de %s falta o está dañado: no se deshace (no se tocó nada)"
                % ", ".join(bad[:4])), [], []
    claude, back = bi.LEGACY_IDENTITY_DOC, dict(restore).get(bi.LEGACY_IDENTITY_DOC)
    if back is not None and not has_brainmd:
        # CLAUDE.md sigue siendo el puntero y BRAIN.md falta en esta máquina
        # (sync a medias, iCloud, borrado): no se sabe cuál es la identidad
        # vigente y restaurar la vieja la propagaría por Obsidian.
        return no_brainmd, [], []
    if back is not None:
        # La versión anterior anotaba la ÚLTIMA escritura: un puntero regenerado
        # con notas del dueño en su zona libre «coincidía». Esas notas no están
        # en el respaldo → no se pisan.
        try:
            fz = _free_zone(_read_bytes(os.path.join(brain, claude)))
        except OSError:
            fz = ""
        if fz and fz != _free_zone(back):
            return ("CLAUDE.md tiene notas tuyas debajo de la marca de fin: no se deshace "
                    "para no perderlas"), [], []
    # Nunca dejar el cerebro sin identidad: si BRAIN.md no queda, el CLAUDE.md
    # que queda (el respaldo que se restaura, o el de hoy) debe ser la
    # identidad, no un puntero a un BRAIN.md que no existe.
    if bi.IDENTITY_DOC in remove or not has_brainmd:
        left = back
        if left is None:
            try:
                left = _read_bytes(os.path.join(brain, claude))
            except OSError:
                left = None
        if left is None or _is_pointer(left):
            return (no_brainmd if not has_brainmd else
                    "deshacer dejaría el cerebro sin identidad (CLAUDE.md quedaría como "
                    "puntero a un BRAIN.md que no existe): no se deshace"), [], []
    return "", restore, remove


def undo_all(state_dir):
    """Deshace la migración en los cerebros con respaldo en esta máquina.
    Por cerebro: restaura los archivos respaldados y quita lo creado, SOLO si
    lo que hay hoy es exactamente lo que escribió la migración (sha), cada
    respaldo existe con su sha original y el cerebro no se queda sin
    identidad. Si no, se niega para ese cerebro SIN tocar nada y explica.
    Devuelve [(cerebro, estado, mensaje)]; estado ∈ {'undone','refused','none'}."""
    base = os.path.join(state_dir, "backups", MID)
    out = []
    try:
        dirs = sorted(os.listdir(base))
    except OSError:
        return out
    for d in dirs:
        bdir = os.path.join(base, d)
        man = _load_manifest(bdir)
        brain = man.get("realpath") or ""
        if not brain or not os.path.isdir(brain):
            out.append((brain or d, "none", "el cerebro ya no existe en esta máquina"))
            continue
        why, restore, remove = _undo_plan(bdir, man, brain)
        if why:
            out.append((brain, "refused", why))
            continue
        try:
            # restaurar y VERIFICAR antes de quitar nada: BRAIN.md jamás se
            # borra si CLAUDE.md no volvió a ser la identidad
            for rel, data in restore:
                p = os.path.join(brain, *rel.split("/"))
                _atomic_write(p, data)
                if _file_sha(p) != _sha(data):
                    raise IOError("verificación de bytes falló en %s" % rel)
        except Exception as e:
            out.append((brain, "refused", "no pude restaurar (%s: %s): se detuvo sin borrar "
                        "nada" % (type(e).__name__, e)))
            continue
        for rel in sorted(remove, key=len, reverse=True):
            try:
                os.remove(os.path.join(brain, *rel.split("/")))
            except OSError:
                pass
        for rel in sorted((r for r in man.get("created") or [] if r.endswith("/")),
                          key=len, reverse=True):
            try:
                os.rmdir(os.path.join(brain, *rel.rstrip("/").split("/")))   # solo si quedó vacía
            except OSError:
                pass
        # el opt-out se deja también si no quedaba nada (2º «deshacer», o la
        # migración falló antes de escribir): es lo que el dueño pidió
        _add_optout(state_dir, brain)
        out.append((brain, "undone", "restaurado al formato viejo" if restore or remove else
                    "no quedaba nada que deshacer: todo está como antes de migrar"))
    return out
