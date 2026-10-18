"""AUTOMÁTICA: el destilador de memoria se retiró; sus sobras se archivan solas.

Desde esta versión ningún proceso corre una IA sin ventana en tu máquina ni
espera tu aprobación para la memoria (decisión del dueño, 2026-10-16). Se
retiraron el destilador (`dream.py`) y el revisor de skills en segundo plano;
la revisión de skills, si la tienes encendida, la hace tu agente al abrir la
siguiente sesión, a la vista.

Qué hace en cada cerebro registrado (nada se borra):
  · `STATE/DESTILADO.md` (la bandeja de candidatos para aprobar a mano) pasa a
    `STATE/memoria-archivo/DESTILADO-<huella>.md`; su candado `.lock`, si
    quedó, va al respaldo de la máquina.
  · `skills/_propuestas/<nombre>/` (skills propuestas esperando aprobación):
    si la revisión de skills está APAGADA para ese agente, pasan a
    `skills/_archive/propuestas-<huella>/<nombre>/`; si está encendida se
    quedan, y la próxima revisión le pide a tu agente integrarlas o archivarlas.
Antes de mover se copia todo a `<estado>/backups/<id>/<agente>/`.
Un cerebro que no se puede mover (solo lectura, disco externo, iCloud sin
conexión) se salta y se avisa: no frena a los demás ni a las migraciones
siguientes, y `workspace doctor --fix` lo reintenta (archivar(), la otra
puerta).

Cerebros compartidos (regla 4; QA del 2026-10-18): los sellos son por máquina,
así que cada máquina archiva SU copia, a veces antes de recibir lo que hizo la
otra. Por eso el nombre sale del CONTENIDO (`<huella>`, la misma en cualquier
máquina) y no del día: con la fecha, la PC archivaba el 17 y la Mac el 18 y
Obsidian dejaba dos copias del mismo texto. Y lo que ya está archivado con el
mismo contenido (otra máquina, quizá con la versión anterior y la fecha en el
nombre) no se archiva otra vez: el original sobra y queda en el respaldo.

Compatibilidad hacia atrás: una versión anterior de Workspace sigue
funcionando sin esos archivos (los vuelve a crear vacíos si los necesita).
"""
import hashlib
import os
import shutil

TITLE = {"es": "La memoria ya no espera tu aprobación: las propuestas viejas se archivaron solas",
         "en": "Memory no longer waits for your approval: old proposals were archived automatically"}
KIND = "auto"
MID = "202610162300_sin_destilado"

DESTILADO = os.path.join("STATE", "DESTILADO.md")
ARCHIVO = os.path.join("STATE", "memoria-archivo")
PROPUESTAS = os.path.join("skills", "_propuestas")
ARCHIVE = os.path.join("skills", "_archive")


def _brains(ctx):
    out, seen = [], set()
    for name, brain in ctx.brains():
        key = os.path.normcase(os.path.realpath(brain))
        if key not in seen:
            seen.add(key)
            out.append((name, brain))
    return out


def _proposals(brain):
    d = os.path.join(brain, PROPUESTAS)
    try:
        return sorted(n for n in os.listdir(d)
                      if not n.startswith(("_", ".")) and os.path.isdir(os.path.join(d, n)))
    except OSError:
        return []


def _review_on(brain):
    try:
        import importlib.util
        here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        spec = importlib.util.spec_from_file_location(
            "_sr_mig", os.path.join(here, "hooks", "skill_review.py"))
        sr = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(sr)
        return bool(sr.review_enabled(brain))
    except Exception:
        return False       # ante la duda, se archivan (no se pierde nada)


def _norm(data):
    """Bytes comparables entre máquinas: sin BOM y con saltos \\n."""
    if data.startswith(b"\xef\xbb\xbf"):
        data = data[3:]
    return data.replace(b"\r\n", b"\n")


def _visibles(path):
    """[(ruta relativa, ruta)] de lo que Obsidian sincroniza dentro de `path`:
    nada que empiece con punto (.usage.json es de cada máquina)."""
    out = []
    for dp, dns, fns in os.walk(path):
        dns[:] = sorted(d for d in dns if not d.startswith("."))
        for f in sorted(fns):
            if not f.startswith("."):
                p = os.path.join(dp, f)
                out.append((os.path.relpath(p, path).replace(os.sep, "/"), p))
    return out


def huella(path):
    """Huella del CONTENIDO de un archivo o una carpeta, la misma en cualquier
    máquina (sin BOM, saltos \\n, sin lo oculto). Da el nombre del archivado:
    dos máquinas que archivan el mismo cerebro, en días distintos, antes de
    sincronizarse, llegan al MISMO nombre."""
    h = hashlib.sha256()
    if os.path.isdir(path):
        for rel, p in _visibles(path):
            with open(p, "rb") as fh:
                h.update(rel.encode("utf-8") + b"\0"
                         + hashlib.sha256(_norm(fh.read())).digest())
    else:
        with open(path, "rb") as fh:
            h.update(_norm(fh.read()))
    return h.hexdigest()


def _listdir(path):
    try:
        return sorted(os.listdir(path))
    except OSError:
        return []


def _ya_archivado(src, previos):
    """Lo ya archivado con el MISMO contenido que `src` (otra máquina lo
    archivó, quizá con la versión anterior y la fecha en el nombre), o None."""
    h = huella(src)
    for p in previos:
        try:
            if huella(p) == h:
                return p
        except OSError:
            continue
    return None


def _destino(src, previos, nuevo):
    """Dónde archivar `src`: lo ya archivado con el mismo contenido o
    `nuevo(huella)`. None si no se pudo leer (iCloud sin descargar, permisos):
    needed() no puede lanzar —detendría la cola entera—; archivar() lo intenta
    y, si falla, ese cerebro se salta y se avisa."""
    try:
        return _ya_archivado(src, previos) or nuevo(huella(src)[:8])
    except OSError:
        return None


def _work(brain):
    """[(accion, origen, destino)] pendientes en este cerebro. El destino sale
    del contenido: si ya está archivado igual, el destino es ese archivado."""
    jobs = []
    src = os.path.join(brain, DESTILADO)
    if os.path.isfile(src):
        arch = os.path.join(brain, ARCHIVO)
        previos = [os.path.join(arch, n) for n in _listdir(arch)
                   if n.upper().startswith("DESTILADO") and n.lower().endswith(".md")
                   and os.path.isfile(os.path.join(arch, n))]
        jobs.append(("destilado", src, _destino(
            src, previos, lambda h: os.path.join(arch, "DESTILADO-%s.md" % h))))
    if os.path.exists(src + ".lock"):
        jobs.append(("lock", src + ".lock", None))
    props = _proposals(brain)
    if props and not _review_on(brain):
        root = os.path.join(brain, ARCHIVE)
        for n in props:
            p = os.path.join(brain, PROPUESTAS, n)
            previos = [os.path.join(root, d, n) for d in _listdir(root)
                       if os.path.isdir(os.path.join(root, d, n))]
            jobs.append(("propuesta", p, _destino(
                p, previos, lambda h, n=n: os.path.join(root, "propuestas-%s" % h, n))))
    return jobs


def needed(ctx):
    return any(_work(brain) for _name, brain in _brains(ctx))


def _free(path):
    """Un destino que no pise nada: agrega -2, -3… si ya existe."""
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    k = 2
    while os.path.exists("%s-%d%s" % (root, k, ext)):
        k += 1
    return "%s-%d%s" % (root, k, ext)


def pendiente(brain):
    """True si este cerebro todavía tiene sobras del destilador que archivar."""
    return bool(_work(brain))


def archivar(brain, state_dir, name, dry_run=False):
    """El trabajo en UN cerebro: lo usan la migración, `workspace doctor
    --fix` y cargar un agente (las otras puertas). Idempotente, respaldo antes
    de mover, nada se pierde: lo que ya estaba archivado igual solo se quita del
    origen. → cuántas sobras archivó; lanza si no pudo (quien llama lo avisa)."""
    jobs = _work(brain)
    backup = os.path.join(state_dir, "backups", MID, name)
    moved = 0
    for kind, src, dest in jobs:
        rel = os.path.relpath(src, brain)
        bk = os.path.join(backup, rel)
        if dry_run:
            continue
        if kind != "lock" and dest is None:
            raise OSError("no se pudo leer %s" % rel.replace(os.sep, "/"))
        os.makedirs(os.path.dirname(bk), exist_ok=True)
        if os.path.isdir(src):
            shutil.copytree(src, _free(bk))   # cada archivado con su respaldo
        else:
            shutil.copy2(src, bk)
        if kind == "lock":
            os.remove(src)        # ya está en el respaldo; no es contenido
            continue
        if os.path.exists(dest) and huella(dest) == huella(src):
            _sobra(src, dest)     # ya archivado igual (otra máquina): no otra copia
            moved += 1
            continue
        dest = _free(dest)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.move(src, dest)
        moved += 1
    return moved


def _sobra(src, dest):
    """`src` ya está archivado en `dest` con el mismo contenido: lo que solo
    tenga esta copia (lo oculto, que Obsidian no sincroniza: .usage.json…) pasa
    a `dest` y `src` se quita (también quedó en el respaldo de la máquina)."""
    if not os.path.isdir(src):
        os.remove(src)
        return
    for dp, _dns, fns in os.walk(src):
        for f in fns:
            p = os.path.join(dp, f)
            q = os.path.join(dest, os.path.relpath(p, src))
            if not os.path.lexists(q):
                os.makedirs(os.path.dirname(q), exist_ok=True)
                shutil.move(p, q)
    shutil.rmtree(src)


def run(ctx):
    for name, brain in _brains(ctx):
        # Un cerebro que falla no traba la cola (revisión 0.3.4): antes su
        # excepción detenía esta migración, memoria v1 y toda la que viniera
        # después, sin reintento hasta la siguiente versión.
        try:
            moved = archivar(brain, ctx.state_dir, name, dry_run=ctx.dry_run)
        except Exception as e:
            ctx.log("%s: sobras del destilador sin archivar (%s: %s); `workspace doctor --fix` "
                    "lo reintenta" % (name, type(e).__name__, e))
            continue
        if moved:
            ctx.log("%s: %d sobra(s) del destilador archivada(s) (respaldo en la máquina)"
                    % (name, moved))
