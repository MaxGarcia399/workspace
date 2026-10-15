#!/usr/bin/env python3
"""WORKSPACE · migrate — migraciones registradas («el pasaporte de sellos»).

POR QUÉ EXISTE: cada actualización puede necesitar ajustar algo en la máquina
del usuario (mover un archivo de estado, añadir una clave, renombrar un
artefacto). Antes eso eran scripts sueltos (`migrate_legacy.py`,
`migrate_memory_v1.py`…) o reparaciones del doctor, y nadie anotaba QUÉ se
había aplicado en cada máquina. Con equipos y clientes en versiones distintas
eso es adivinar. Patrón tomado de Omarchy (`migrations/<timestamp>.sh` + un
marcador por migración en el estado del usuario), adaptado a Workspace.

MODELO
  · Cada migración es un archivo `migrations/<YYYYMMDDHHMM>_<slug>.py`. El
    nombre (sin `.py`) es su id; el orden es el orden del nombre.
  · Al aplicarse deja un SELLO: `<state_dir>/migrations/<id>.json`. Sello
    presente = no se vuelve a correr. Sellos de migraciones que este código no
    conoce (vienen de una versión más nueva tras un rollback) se ignoran.
  · Dos clases (atributo `KIND`):
      "auto"  — segura e idempotente. Corre sola tras actualizar, de forma
                VISIBLE (una línea en el hub / en `workspace update`), nunca
                escondida. La cola se DETIENE en la primera que falle: no hay
                "saltar y seguir" (Omarchy lo tuvo y dejaba estados a medias).
      "offer" — cambio grande que se OFRECE y el usuario acepta
                (`workspace migrate --offer <id>`). Jamás bloquea la cola de
                las "auto": las auto no pueden depender de una oferta.
  · Instalación nueva: `install.py` sella todo como "first-install" (el
    instalador ya deja el estado en el formato actual).
  · Usuarios existentes que llegan a una versión con migraciones por primera
    vez no tienen sellos → corren todas: por eso TODA migración declara
    `needed(ctx)` y es idempotente. Si no aplica, se sella "not-needed".

CONTRATO de una migración (ver migrations/README.md, regla de compatibilidad):
    TITLE = {"es": "...", "en": "..."}     # qué cambia, en lenguaje de usuario
    KIND = "auto" | "offer"                 # default "auto"
    def needed(ctx) -> bool                 # opcional (default True)
    def run(ctx) -> None                    # idempotente; lanza excepción si falla

Fail-soft hacia afuera: nada de este módulo rompe el arranque del hub ni de un
agente. Si una migración falla, queda registrada en `failed.json`, la cola se
detiene y el doctor lo muestra con su acción. Stdlib, Python 3.9+.
"""
import datetime
import hashlib
import importlib.util
import json
import os
import re
import sys
import traceback

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import paths as _paths  # noqa: E402

MIGRATIONS_DIR = os.path.join(ROOT, "migrations")
_ID_RE = re.compile(r"^(\d{12})_[a-z0-9_]+$")
KINDS = ("auto", "offer")


def _t(key, default, **kw):
    try:
        import i18n
        s = i18n.t(key, **kw)
        if s != key:
            return s
    except Exception:
        pass
    try:
        return default.format(**kw) if kw else default
    except Exception:
        return default


def _lang():
    try:
        import i18n
        return i18n.lang()
    except Exception:
        return "es"


def _now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def _version(root=ROOT):
    try:
        with open(os.path.join(root, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except Exception:
        return ""


# ── dónde viven los sellos ──────────────────────────────────────────────────
def stamps_dir(home=None):
    return os.path.join(_paths.state_dir(home), "migrations")


def _stamp_path(mid, home=None):
    return os.path.join(stamps_dir(home), mid + ".json")


def _failed_path(home=None):
    return os.path.join(stamps_dir(home), "failed.json")


def _write_json_atomic(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp-%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return None


# ── descubrimiento ──────────────────────────────────────────────────────────
class Migration(object):
    """Una migración cargada. `module` es None si el archivo no se pudo
    importar (entonces `load_error` dice por qué: cuenta como fallo)."""

    def __init__(self, mid, path):
        self.id = mid
        self.path = path
        self.module = None
        self.load_error = ""

    def load(self):
        if self.module is not None or self.load_error:
            return self
        try:
            name = "workspace_migration_" + self.id
            spec = importlib.util.spec_from_file_location(name, self.path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not callable(getattr(mod, "run", None)):
                raise ValueError("la migración no define run(ctx)")
            if getattr(mod, "KIND", "auto") not in KINDS:
                raise ValueError("KIND inválido: %r" % getattr(mod, "KIND", None))
            self.module = mod
        except Exception as e:
            self.load_error = "%s: %s" % (type(e).__name__, e)
        return self

    @property
    def kind(self):
        self.load()
        return getattr(self.module, "KIND", "auto") if self.module else "auto"

    def title(self):
        self.load()
        tt = getattr(self.module, "TITLE", None) if self.module else None
        if isinstance(tt, dict):
            return tt.get(_lang()) or tt.get("es") or tt.get("en") or self.id
        return str(tt) if tt else self.id

    def needed(self, ctx):
        self.load()
        fn = getattr(self.module, "needed", None)
        return True if fn is None else bool(fn(ctx))


def discover(mdir=None):
    """Migraciones del código, en orden. Archivos con nombre fuera de contrato
    se ignoran (los cubre el test de contrato, no el runtime)."""
    mdir = mdir or MIGRATIONS_DIR
    out = []
    try:
        names = sorted(os.listdir(mdir))
    except OSError:
        return out
    for fn in names:
        if not fn.endswith(".py"):
            continue
        mid = fn[:-3]
        if _ID_RE.match(mid):
            out.append(Migration(mid, os.path.join(mdir, fn)))
    return out


# ── contexto que recibe cada migración ──────────────────────────────────────
class Context(object):
    """Lo que una migración necesita saber de la máquina. Nada de globals:
    así los tests le pasan un HOME falso y la migración no puede escaparse."""

    def __init__(self, home=None, root=ROOT, dry_run=False, log=None):
        self.home = home or os.path.expanduser("~")
        self.root = root
        self.state_dir = _paths.state_dir(self.home)
        self.dry_run = dry_run
        self._log = log
        self._brains = None

    def log(self, msg):
        if self._log:
            try:
                self._log(msg)
            except Exception:
                pass

    def brains(self):
        """[(nombre, ruta)] de los cerebros registrados que existen en disco.
        Perezoso y fail-soft (una migración que no los necesita no paga)."""
        if self._brains is None:
            out = []
            try:
                import dispatch
                import brain_resolver
                for entry in dispatch.load_registry().get("agents", []):
                    try:
                        cfg = dispatch.load_agent_cfg(entry)
                    except Exception:
                        cfg = {}
                    try:
                        res = brain_resolver.resolve(entry["name"], cfg, entry)
                        if res.get("exists"):
                            out.append((entry["name"], res.path))
                    except Exception:
                        continue
            except Exception:
                pass
            self._brains = out
        return list(self._brains)


# ── estado ──────────────────────────────────────────────────────────────────
def stamp(mid, status, home=None, note=""):
    data = {"id": mid, "status": status, "at": _now(), "version": _version()}
    if note:
        data["note"] = note
    _write_json_atomic(_stamp_path(mid, home), data)


def is_stamped(mid, home=None):
    return os.path.isfile(_stamp_path(mid, home))


def _stamp_status(mid, home=None):
    """Estado del sello ("done", "first-install", "declined"…) o "" si no hay."""
    try:
        with open(_stamp_path(mid, home), encoding="utf-8") as fh:
            return (json.load(fh) or {}).get("status", "")
    except (OSError, ValueError, AttributeError):
        return ""


def _file_sha(path):
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return ""


def failure(home=None, mdir=None):
    """{id, error, at, version, sha} de la migración que falló y SIGUE
    pendiente, o None. Un failed.json viejo (la migración ya se selló, o ya no
    existe en el código) no cuenta: no queremos avisos pegados."""
    data = _read_json(_failed_path(home))
    if not (isinstance(data, dict) and data.get("id")):
        return None
    if is_stamped(data["id"], home):
        return None
    if data["id"] not in {m.id for m in discover(mdir)}:
        return None
    return data


def _blocked_by_known_failure(queue, home=None):
    """True si la primera pendiente es la MISMA que ya falló, con el mismo
    código (archivo y versión): reintentarla daría el mismo error. Se reintenta
    sola cuando llega una versión nueva o el archivo cambia, o a mano."""
    if not queue:
        return False
    f = _read_json(_failed_path(home))
    if not (isinstance(f, dict) and f.get("id") == queue[0].id):
        return False
    return (f.get("version") == _version()
            and f.get("sha") == _file_sha(queue[0].path))


def _clear_failure(home=None):
    try:
        os.remove(_failed_path(home))
    except OSError:
        pass


def status(home=None, mdir=None):
    """Foto completa: {applied:[...], pending:[...], offers:[...], failed}.
    `pending` = auto sin sello; `offers` = ofertas sin sello (sin evaluar
    `needed`, que puede ser caro: eso lo hace `offers_available`)."""
    applied, pending, offers, declined = [], [], [], []
    for m in discover(mdir):
        if is_stamped(m.id, home):
            (declined if _stamp_status(m.id, home) == "declined" else applied).append(m.id)
        elif m.kind == "offer":
            offers.append(m.id)
        else:
            pending.append(m.id)
    return {"applied": applied, "pending": pending, "offers": offers,
            "declined": declined, "failed": failure(home)}


def _queue(home=None, mdir=None):
    return [m for m in discover(mdir) if not is_stamped(m.id, home) and m.kind == "auto"]


def has_pending(home=None, mdir=None):
    """Chequeo barato para el arranque: ¿hay auto sin sello? Solo mira nombres
    y sellos; carga un módulo únicamente si hace falta saber su KIND."""
    return bool(_queue(home, mdir))


def has_runnable_pending(home=None, mdir=None):
    """¿Hay pendientes que valga la pena correr AHORA? (excluye la cola trabada
    por un fallo conocido, que ya se reporta en el doctor)."""
    q = _queue(home, mdir)
    return bool(q) and not _blocked_by_known_failure(q, home)


# ── correr ──────────────────────────────────────────────────────────────────
def _lock(home=None):
    """Un solo runner a la vez por máquina (el hub y un `repair` en segundo
    plano podrían coincidir). Devuelve un context manager o None si olock no
    está disponible (entonces se corre sin lock: peor caso, dos runners hacen
    el mismo trabajo idempotente)."""
    try:
        import olock
        os.makedirs(stamps_dir(home), exist_ok=True)
        return olock.file_lock(os.path.join(stamps_dir(home), "runner"),
                               timeout=2)
    except Exception:
        return None


def run_pending(home=None, mdir=None, log=None, dry_run=False, force=False):
    """Corre las migraciones "auto" pendientes, en orden, deteniéndose en la
    primera que falle. Devuelve
      {applied:[(id,title)], not_needed:[id], failed:{id,title,error}|None,
       remaining:[id], busy:bool}
    `busy` = otro proceso está corriendo migraciones ahora mismo.
    Sin `force`, una cola trabada por un fallo conocido NO se reintenta (mismo
    archivo y misma versión → mismo error): se devuelve el fallo tal cual."""
    result = {"applied": [], "not_needed": [], "failed": None,
              "remaining": [], "busy": False}
    lk = _lock(home)
    if lk is not None:
        try:
            lk.__enter__()
        except Exception:
            result["busy"] = True
            return result
    try:
        ctx = Context(home=home, dry_run=dry_run, log=log)
        queue = _queue(home, mdir)
        if not force and not dry_run and _blocked_by_known_failure(queue, home):
            f = _read_json(_failed_path(home)) or {}
            result["failed"] = {"id": queue[0].id, "title": queue[0].title(),
                                "error": f.get("error", ""), "known": True}
            result["remaining"] = [x.id for x in queue]
            return result
        for i, m in enumerate(queue):
            m.load()
            try:
                if m.load_error:
                    raise RuntimeError(m.load_error)
                if not m.needed(ctx):
                    if not dry_run:
                        stamp(m.id, "not-needed", home)
                    result["not_needed"].append(m.id)
                    continue
                if dry_run:
                    result["applied"].append((m.id, m.title()))
                    continue
                m.module.run(ctx)
                stamp(m.id, "done", home)
                result["applied"].append((m.id, m.title()))
            except Exception as e:
                err = "%s: %s" % (type(e).__name__, e)
                result["failed"] = {"id": m.id, "title": m.title(), "error": err}
                result["remaining"] = [x.id for x in queue[i:]]
                if not dry_run:
                    try:
                        _write_json_atomic(_failed_path(home), {
                            "id": m.id, "error": err, "at": _now(),
                            "version": _version(), "sha": _file_sha(m.path),
                            "trace": traceback.format_exc()[-2000:]})
                    except Exception:
                        pass
                break
        if result["failed"] is None and not dry_run:
            _clear_failure(home)
        return result
    finally:
        if lk is not None:
            try:
                lk.__exit__(None, None, None)
            except Exception:
                pass


def offers_available(home=None, mdir=None):
    """[(id, title)] de ofertas sin sello que SÍ aplican a esta máquina."""
    out = []
    ctx = Context(home=home)
    for m in discover(mdir):
        if is_stamped(m.id, home) or m.kind != "offer":
            continue
        try:
            if m.load().module and m.needed(ctx):
                out.append((m.id, m.title()))
        except Exception:
            continue
    return out


def apply_offer(mid, home=None, mdir=None, log=None):
    """Aplica UNA oferta aceptada por el usuario. (ok, mensaje)."""
    for m in discover(mdir):
        if m.id != mid:
            continue
        if m.load().load_error:
            return False, m.load_error
        if m.kind != "offer":
            return False, _t("migrate.err.not_offer", "{id} no es una oferta", id=mid)
        if is_stamped(mid, home) and _stamp_status(mid, home) != "declined":
            return True, _t("migrate.offer.already", "ya estaba aplicada")
        ctx = Context(home=home, log=log)
        try:
            if not m.needed(ctx):
                stamp(mid, "not-needed", home)
                return True, _t("migrate.offer.not_needed", "no hacía falta en esta máquina")
            m.module.run(ctx)
            stamp(mid, "done", home)
            return True, m.title()
        except Exception as e:
            return False, "%s: %s" % (type(e).__name__, e)
    return False, _t("migrate.err.unknown", "no existe la migración {id}", id=mid)


def decline_offer(mid, home=None, mdir=None):
    """El usuario dijo «no gracias» a UNA oferta: se sella como `declined` y deja de
    ofrecerse (el doctor no la vuelve a mostrar). Se puede aceptar después con
    `workspace migrate --offer <id>`. (ok, mensaje)."""
    for m in discover(mdir):
        if m.id != mid:
            continue
        if m.load().load_error:
            return False, m.load_error
        if m.kind != "offer":
            return False, _t("migrate.err.not_offer", "{id} no es una oferta", id=mid)
        if is_stamped(mid, home):
            return True, _t("migrate.offer.decided", "ya habías elegido sobre este cambio")
        stamp(mid, "declined", home)
        return True, _t("migrate.offer.declined",
                        "Listo: no se aplicará y no se volverá a ofrecer. Si cambias de opinión: "
                        "workspace migrate --offer {id}", id=mid)
    return False, _t("migrate.err.unknown", "no existe la migración {id}", id=mid)


def offer_actions(mid):
    """Las dos salidas de una oferta, para el doctor y `workspace migrate`."""
    return _t("migrate.cli.offer_actions",
              "aceptar: workspace migrate --offer {id} · no gracias: workspace migrate --decline {id}",
              id=mid)


def mark_all(reason="first-install", home=None, mdir=None):
    """Sella todas las migraciones sin sello (instalación nueva: el instalador
    ya dejó el formato actual). Devuelve cuántas selló. Nunca lanza."""
    n = 0
    for m in discover(mdir):
        if not is_stamped(m.id, home):
            try:
                stamp(m.id, reason, home)
                n += 1
            except Exception:
                pass
    return n


# ── salida para humanos ─────────────────────────────────────────────────────
def summary_line(result):
    """Una línea para el hub / update. '' si no hubo nada que contar."""
    if result.get("failed") and result["failed"].get("known"):
        return ""                     # ya avisado; vive en `workspace doctor`
    if result.get("failed"):
        return _t("migrate.line.failed",
                  "⚠ Un ajuste de la actualización no se pudo aplicar ({title}). "
                  "Workspace sigue funcionando; corre `workspace doctor`.",
                  title=result["failed"]["title"])
    n = len(result.get("applied") or [])
    if n:
        return _t("migrate.line.applied", "✓ {n} ajuste(s) de la actualización aplicados.", n=n)
    return ""


def main(argv=None):
    """`workspace migrate [--status | --run | --pending | --offer <id> | --decline <id> | --dry-run]`"""
    args = list(argv if argv is not None else sys.argv[1:])
    if "--first-install" in args:
        n = mark_all("first-install")
        print(_t("migrate.cli.marked", "{n} migración(es) marcadas como aplicadas (instalación nueva).", n=n))
        return 0
    if "--pending" in args:
        # Contrato estilo `omarchy-migrate --pending`: 1 si hay pendientes.
        return 1 if has_pending() else 0
    if "--offer" in args:
        i = args.index("--offer")
        mid = args[i + 1] if i + 1 < len(args) else ""
        ok, msg = apply_offer(mid, log=print)
        print(("✓ " if ok else "✗ ") + msg)
        return 0 if ok else 1
    if "--decline" in args:
        i = args.index("--decline")
        mid = args[i + 1] if i + 1 < len(args) else ""
        ok, msg = decline_offer(mid)
        print(("✓ " if ok else "✗ ") + msg)
        return 0 if ok else 1
    if "--run" in args and "--json" in args:
        # Para el actualizador (proceso padre con el código viejo): solo JSON.
        res = run_pending(force=True)
        res["applied"] = [list(a) for a in res["applied"]]
        print(json.dumps(res, ensure_ascii=False))
        return 1 if res["failed"] else 0
    if "--run" in args or "--dry-run" in args:
        res = run_pending(log=print, dry_run="--dry-run" in args, force=True)
        if res["busy"]:
            print(_t("migrate.cli.busy", "Otro proceso está aplicando ajustes ahora mismo; reintenta en un momento."))
            return 0
        for mid, title in res["applied"]:
            print("  ✓ %s  (%s)" % (title, mid))
        for mid in res["not_needed"]:
            print("  · %s  %s" % (mid, _t("migrate.cli.not_needed", "no hacía falta")))
        if res["failed"]:
            print("  ✗ %s  (%s)\n    %s" % (res["failed"]["title"], res["failed"]["id"], res["failed"]["error"]))
            print(_t("migrate.cli.stopped", "La cola se detuvo aquí: los ajustes siguientes esperan a que este se resuelva."))
            return 1
        if not (res["applied"] or res["not_needed"]):
            print(_t("migrate.cli.none", "No hay ajustes pendientes."))
        return 0
    st = status()
    print(_t("migrate.cli.header", "Ajustes de actualización (migraciones) en esta máquina:"))
    print("  " + _t("migrate.cli.applied", "aplicados: {n}", n=len(st["applied"])))
    print("  " + _t("migrate.cli.pending", "pendientes: {n}", n=len(st["pending"])))
    for mid in st["pending"]:
        print("    · " + mid)
    offers = offers_available()
    if offers:
        print("  " + _t("migrate.cli.offers", "ofrecidos (requieren tu OK):"))
        for mid, title in offers:
            print("    · %s — %s" % (title, offer_actions(mid)))
    if st["failed"]:
        f = st["failed"]
        print("  ✗ " + _t("migrate.cli.failed", "falló: {id} — {err}", id=f["id"], err=f.get("error", "")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
