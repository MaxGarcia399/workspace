#!/usr/bin/env python3
"""WORKSPACE · maquinas — constancia por máquina y salud del sync (sesiones v2 · C).

El problema (plan «Sesiones entre máquinas» §2 F2 y §3b): la lista de pestañas
viaja en el cerebro, pero nadie revisaba que el cerebro estuviera LLEGANDO. El
de un agente pasó semanas sin sincronizar en una Mac y nadie avisó. El dueño
no sabe ni va a revisar a mano si Obsidian Sync está conectado, ni si tiene
prendido «Sync all other types» (viene apagado y es por dispositivo).

Lo que hace este módulo, solo y sin red:

  · Cada máquina tiene un id estable en `<estado>/maquina.json` (no viaja):
        {"version": 1, "id": "<12 hex>", "etiqueta": "<hostname saneado>",
         "creada": "<ISO>"}
  · Al abrir un agente (dispatch) o el hub, `al_abrir()` deja en CADA cerebro
    registrado su constancia `STATE/maquinas/<id>.md` (un archivo por máquina:
    nunca chocan) y una sonda `STATE/maquinas/<id>.sonda.json` (unos bytes, sin
    datos). Reescribe la constancia solo si algo cambió o si pasaron más de
    10 min, para no hacer ruido de sync. Formato (frontmatter):
        maquina, etiqueta, so, version, visto,
        obsidian_abierto (true/false/null), boveda_abierta (true/false/null),
        pestanas (las del socio de esta máquina), pestanas_total (las de todo
        el cerebro: lo que se compara entre máquinas), pestanas_desde (desde
        cuándo ese total no cambia), actividad (lo más nuevo en
        STATE/sessions/), maquinas_vistas y sondas_vistas (ids de las OTRAS
        máquinas cuya constancia / sonda llega aquí).
    Nada personal: solo la etiqueta del hostname.
  · La sonda es un archivo `.json`: para Obsidian Sync es de «otros tipos».
    Si B ve la constancia de A pero no su sonda, en B está apagado «Sync all
    other types» (o hay un filtro). Eso queda en `sondas_vistas`; lo consume
    el nivel 2 (llevar la conversación de Claude Code, `.jsonl.gz`).
  · `estado(brain)` → las máquinas con su `visto`, sus pestañas, si ven las
    sondas y si están desfasadas. `avisos(brain)` → avisos de una línea:
      - otra máquina sin constancia nueva en más de 3 días mientras en esta
        hubo cambios en las sesiones (pasados 60 días se da por retirada);
      - el total de pestañas distinto entre las dos por más de 1 h (las dos
        lo vieron así a la vez durante más de una hora);
      - Obsidian cerrado en esta máquina, si el cerebro es una bóveda con Sync;
        o abierto pero sin la bóveda de este cerebro (Obsidian solo sincroniza
        las bóvedas que tiene abiertas);
      - archivos `*conflict*` en STATE/sessions/.
  · `resumen_linea(brain)` → UNA línea para el hub («PC (escritorio): vista
    hace 2 h · mismas 32 pestañas», o el primer aviso). `aviso_linea(brain)`
    → la línea para la terminal y el contexto de arranque del agente, '' si
    no hay aviso.

Ganchos:
  · el hub (front.py `_sesiones_al_abrir_hub`, en un hilo): `al_abrir()`, la
    constancia en TODOS los cerebros registrados, y `resumen_linea(cerebro)`
    en la vista simple;
  · dispatch, al abrir un agente: `al_abrir_agente(cerebro)`, SOLO la
    constancia del cerebro que se abre, con tope total de 300 ms (en un hilo:
    lo que no termine a tiempo sigue solo) y sin volver a preguntar por
    Obsidian si hay un sondeo de menos de 10 min en el estado local;
  · el contexto de arranque (neutral_hooks, session_start) y el doctor (4a).
Las constancias se leen solo hasta el segundo `---` (la cabecera). Los
temporales de más de 1 h en STATE/maquinas/ (un hilo que murió a media
escritura: el hub hace exec al abrir un agente) se borran al escribir.

Para el archivo automático (frente B) — la constancia previa de ESTA máquina:
  · `visto_previo(cerebro)` → epoch del `visto` que esta máquina tenía en ese
    cerebro ANTES de esta apertura, o None si nunca dejó constancia ahí. Se
    fija en memoria del proceso antes de reescribir la constancia propia; y
    como el hub reescribe en otro proceso (luego hace exec a dispatch), una
    reescritura que llega tras más de 1 h sin constancia (una «vuelta») se
    anota en el estado local y durante la hora siguiente cualquier proceso
    recibe ese visto anterior.
  · `copia_al_dia(cerebro)` → False si alguna otra máquina (no retirada) dice
    en su constancia haber escrito algo más nuevo (`actividad`) que lo más
    nuevo que hay en disco aquí, con 2 min de tolerancia: el sync no ha
    terminado de llegar. True si ninguna; None si no hay con qué comparar.

Detección de Obsidian por SO: Mac `pgrep -x Obsidian`; Windows `tasklist`
leído en bytes y decodificado con la página ANSI («mbcs») y errors="replace"
(con PYTHONUTF8=1 y text=True la salida OEM, cp850, tronaba); Linux
`pgrep -f obsidian`. Sin el programa → null (no se sabe, no se avisa).

Falla suave en todo: jamás frena la apertura. Stdlib, Python 3.9+, Mac,
Windows y Linux.
"""
import datetime
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import unicodedata
import uuid

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import paths as _paths  # noqa: E402  (SSOT del dir de estado)

CARPETA = ("STATE", "maquinas")
ARCHIVO_LOCAL = "maquina.json"
SONDA_SUFIJO = ".sonda.json"
SONDA = '{"sonda": 1}\n'           # unos bytes, sin datos
INTERVALO_S = 10 * 60               # reescribir aunque nada cambie
VIEJA_S = 3 * 86400                 # otra máquina sin noticias → aviso
RETIRADA_S = 60 * 86400             # más vieja que esto: se lista, no se avisa
CONTEO_S = 3600                     # totales distintos más tiempo que esto → aviso
PRESUPUESTO_S = 2.0                 # tope de al_abrir() para todos los cerebros
PRESUPUESTO_AGENTE_S = 0.3          # tope total al abrir un agente (dispatch)
SONDEO_S = 10 * 60                  # dispatch reusa un sondeo de Obsidian así de nuevo…
SONDEO_CERRADO_S = 60               # …salvo «cerrado», que se confirma antes de avisar
TMP_VIEJO_S = 3600                  # temporales huérfanos en STATE/maquinas/
LLEGADA_S = 3600                    # reescribir tras más de esto sin constancia = una vuelta
VENTANA_S = 3600                    # cuánto dura el visto previo de una vuelta entre procesos
TOLERANCIA_S = 120                  # relojes de máquinas distintas (copia_al_dia)
ARCHIVO_SONDEO = "maquina-obsidian.json"
ARCHIVO_LLEGADAS = "maquinas-llegadas.json"
INTENTOS = 8                        # reemplazo en Windows al abrir (~1.4 s peor caso)
CACHE_S = 30                        # sondeo de procesos / obsidian.json por proceso
_ID_RE = re.compile(r"^[0-9a-f]{8,32}$")
#: Orden y nombre de los campos de la constancia (el frontmatter).
CAMPOS = ("maquina", "etiqueta", "so", "version", "visto", "obsidian_abierto",
          "boveda_abierta", "pestanas", "pestanas_total", "pestanas_desde",
          "actividad", "maquinas_vistas", "sondas_vistas")
_LISTAS = ("maquinas_vistas", "sondas_vistas")
_SIN_VISTO = tuple(c for c in CAMPOS if c != "visto")

_CACHE = {}
_PREVIO = {}                        # cerebro → visto previo de esta máquina (este proceso)
_NADA = object()


# ── utilidades ──────────────────────────────────────────────────────────────
def _t(key, default, **kw):
    """i18n falla-suave: idioma activo → el `default` español."""
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


def _ahora():
    """Hora local CON zona (las constancias se comparan entre máquinas)."""
    return datetime.datetime.now().astimezone().replace(microsecond=0)


def _iso(dt):
    return dt.isoformat() if dt else None


def _fecha(s):
    """ISO → datetime con zona (una sin zona se toma como local). None si no."""
    if isinstance(s, datetime.datetime):
        d = s
    else:
        try:
            d = datetime.datetime.fromisoformat(str(s or "").strip())
        except ValueError:
            return None
    try:
        return d if d.tzinfo else d.astimezone()
    except Exception:
        return None


def _desde_epoch(ts):
    try:
        return datetime.datetime.fromtimestamp(float(ts)).astimezone().replace(microsecond=0)
    except Exception:
        return None


def _leer_json(path):
    """dict/list del archivo; {} si no existe; None si existe y no se lee."""
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}
    except Exception:
        return None


def _norm(p):
    try:
        return os.path.normcase(os.path.realpath(os.path.abspath(str(p))))
    except Exception:
        return str(p)


def _escribir(path, texto):
    import atomico
    atomico.escribir(path, texto, intentos=INTENTOS)


def _version():
    try:
        with open(os.path.join(_ROOT, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip() or "?"
    except OSError:
        return "?"


def so():
    if sys.platform == "darwin":
        return "mac"
    if os.name == "nt" or sys.platform.startswith("win"):
        return "windows"
    return "linux"


# ── la máquina (estado local, no viaja) ─────────────────────────────────────
def etiqueta_host(nombre=None):
    """Hostname saneado: minúsculas, ASCII, [a-z0-9-], sin dominio, ≤32."""
    if nombre is None:
        try:
            nombre = socket.gethostname()
        except Exception:
            nombre = ""
    n = unicodedata.normalize("NFKD", str(nombre or "")).encode("ascii", "ignore").decode()
    n = n.strip().lower().split(".")[0]
    n = re.sub(r"[^a-z0-9]+", "-", n).strip("-")[:32].strip("-")
    return n or "maquina"


def ruta_local(sdir=None):
    return os.path.join(sdir or _paths.state_dir(), ARCHIVO_LOCAL)


def _id_valido(d):
    return isinstance(d, dict) and isinstance(d.get("id"), str) and bool(_ID_RE.match(d["id"]))


class _Candado(object):
    """file_lock de olock si se puede; si no (o tarda), sigue sin candado."""

    def __init__(self, path):
        self.path, self._lk = path, None

    def __enter__(self):
        try:
            from olock import file_lock
            lk = file_lock(self.path, timeout=3)
            lk.__enter__()
            self._lk = lk
        except Exception:
            self._lk = None
        return self

    def __exit__(self, *a):
        if self._lk is not None:
            try:
                self._lk.__exit__(*a)
            except Exception:
                pass
        return False


def maquina(sdir=None, crear=True):
    """{"version", "id", "etiqueta", "creada"} de esta máquina. La primera
    vez lo crea (uuid). Uno ilegible se aparta (`maquina.json.danado-<fecha>`,
    nada se borra) y se crea otro. `crear=False` → None si no hay."""
    p = ruta_local(sdir)
    d = _leer_json(p)
    if not crear:                             # solo lectura: ni candado ni escritura
        return d if _id_valido(d) else None
    eti = etiqueta_host()
    if _id_valido(d) and d.get("etiqueta") == eti:
        return d                              # lo de siempre: sin candado
    with _Candado(p):
        d = _leer_json(p)
        if _id_valido(d):
            if d.get("etiqueta") != eti:          # cambió el nombre del equipo
                d["etiqueta"] = eti
                try:
                    _escribir(p, json.dumps(d, indent=2, ensure_ascii=False) + "\n")
                except Exception:
                    pass
            return d
        if not crear:
            return None
        if os.path.exists(p):
            try:
                os.replace(p, "%s.danado-%s" % (p, _ahora().strftime("%Y%m%d-%H%M%S")))
            except OSError:
                pass
        nuevo = {"version": 1, "id": uuid.uuid4().hex[:12], "etiqueta": eti,
                 "creada": _iso(_ahora())}
        try:
            _escribir(p, json.dumps(nuevo, indent=2, ensure_ascii=False) + "\n")
        except Exception:
            return None                       # sin estado escribible (sandbox): no hay constancia
        return nuevo


# ── Obsidian en esta máquina ────────────────────────────────────────────────
def _texto_consola(raw):
    """Bytes de un comando de consola → texto, JAMÁS levanta. En Windows la
    página ANSI («mbcs», lo que pide la spec) con errors="replace": la salida
    de tasklist viene en la OEM (cp850) y leerla con text=True bajo
    PYTHONUTF8=1 tronaba con UnicodeDecodeError. Fuera de Windows, UTF-8."""
    if isinstance(raw, str):
        return raw
    for codec in ("mbcs", "utf-8"):
        try:
            return (raw or b"").decode(codec, errors="replace")
        except LookupError:
            continue
    return (raw or b"").decode("latin-1")


def _sondear_obsidian(plataforma=None, timeout=None):
    """¿Corre Obsidian? True/False, o None si no se puede saber (también si
    el comando no contesta en `timeout` segundos)."""
    plat = plataforma or sys.platform
    try:
        if plat.startswith("win"):
            r = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Obsidian.exe", "/FO", "CSV", "/NH"],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               timeout=timeout or 4,
                               creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            if r.returncode != 0:
                return None
            return "obsidian.exe" in _texto_consola(r.stdout).lower()
        cmd = ["pgrep", "-x", "Obsidian"] if plat == "darwin" else ["pgrep", "-f", "obsidian"]
        r = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=timeout or 3)
        if r.returncode == 0:
            return True
        if r.returncode == 1:
            return False
        return None
    except Exception:                   # sin pgrep/tasklist, timeout, lo que sea
        return None


def _sondeo_guardado(max_edad):
    """El último sondeo de esta máquina (estado local) si tiene menos de
    `max_edad` s; «cerrado» solo vale SONDEO_CERRADO_S (antes de avisar se
    confirma). _NADA si no hay uno que sirva."""
    d = _leer_json(os.path.join(_paths.state_dir(), ARCHIVO_SONDEO))
    if not isinstance(d, dict) or d.get("abierto") not in (True, False):
        return _NADA
    try:
        edad = _ahora().timestamp() - float(d.get("en"))
    except (TypeError, ValueError):
        return _NADA
    tope = SONDEO_CERRADO_S if d["abierto"] is False else max_edad
    return d["abierto"] if 0 <= edad < min(tope, max_edad) else _NADA


def _guardar_sondeo(v):
    if v is None:
        return
    try:
        _escribir(os.path.join(_paths.state_dir(), ARCHIVO_SONDEO),
                  json.dumps({"abierto": v, "en": _ahora().timestamp()}) + "\n")
    except Exception:
        pass


def obsidian_abierto(max_edad=None, timeout=None):
    """¿Obsidian corre en esta máquina? Cacheado unos segundos por proceso.
    Con `max_edad` (dispatch) reusa el último sondeo guardado en el estado
    local si es así de nuevo, sin correr pgrep/tasklist. Cada sondeo nuevo
    se guarda. WORKSPACE_NO_OBSIDIAN_PROBE=1 (la suite) → None."""
    if os.environ.get("WORKSPACE_NO_OBSIDIAN_PROBE"):
        return None
    t = time.monotonic()
    c = _CACHE.get("obsidian")
    if c and t - c[0] < CACHE_S:
        return c[1]
    v = _sondeo_guardado(max_edad) if max_edad else _NADA
    if v is _NADA:
        v = _sondear_obsidian(timeout=timeout)
        _guardar_sondeo(v)
    _CACHE["obsidian"] = (t, v)
    return v


def _obsidian_json():
    """Las bóvedas que Obsidian conoce en esta máquina: [{path, open}]."""
    t = time.monotonic()
    c = _CACHE.get("vaults")
    if c and t - c[0] < CACHE_S and c[2] == os.path.expanduser("~"):
        return c[1]
    home = os.path.expanduser("~")
    cands = []
    ap = os.environ.get("APPDATA")
    if ap:
        cands.append(os.path.join(ap, "obsidian", "obsidian.json"))
    cands += [os.path.join(home, "Library", "Application Support", "obsidian", "obsidian.json"),
              os.path.join(home, ".config", "obsidian", "obsidian.json"),
              os.path.join(home, ".var", "app", "md.obsidian.Obsidian", "config", "obsidian",
                           "obsidian.json")]
    out = []
    for p in cands:
        d = _leer_json(p)
        vaults = d.get("vaults") if isinstance(d, dict) else None
        if not isinstance(vaults, dict):
            continue
        for v in vaults.values():
            if isinstance(v, dict) and isinstance(v.get("path"), str) and v["path"]:
                out.append({"path": v["path"], "open": bool(v.get("open"))})
    _CACHE["vaults"] = (t, out, home)
    return out


def boveda_abierta(brain):
    """¿La bóveda de ESTE cerebro está abierta en Obsidian (obsidian.json)?
    True/False si Obsidian la conoce; None si no está registrada aquí."""
    real, hallada = _norm(brain), None
    for v in _obsidian_json():
        if _norm(v["path"]) == real:
            if v["open"]:
                return True
            hallada = False
    return hallada


def sync_obsidian(brain):
    """¿El plugin Sync está prendido en esta bóveda? (.obsidian/core-plugins.json:
    lista vieja ["sync", …] o objeto {"sync": true}). None si no se sabe."""
    d = _leer_json(os.path.join(brain, ".obsidian", "core-plugins.json"))
    if isinstance(d, dict) and "sync" in d:
        return bool(d.get("sync"))
    if isinstance(d, list):
        return "sync" in d
    return None


# ── lo que esta máquina ve del cerebro ──────────────────────────────────────
def carpeta(brain):
    return os.path.join(brain, *CARPETA)


def _socios(brain):
    d = os.path.join(brain, "STATE", "sessions")
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return []
    return [n for n in names if not n.startswith(("_", "."))
            and os.path.isdir(os.path.join(d, n))]


def _contar(brain, socio):
    """Pestañas de un socio: el núcleo de la lista (`agent_brand.pestanas`,
    una por slug y sin las archivadas), la misma que ven los menús."""
    try:
        import agent_brand
        return len(agent_brand.pestanas(brain, socio, False))
    except Exception:
        return 0


def _socio(brain):
    try:
        import sessions_registry
        return sessions_registry.socio(brain) or ""
    except Exception:
        return ""


def _actividad(brain):
    """Lo más nuevo en STATE/sessions/<socio>/*.md (epoch) o None."""
    mx = None
    base = os.path.join(brain, "STATE", "sessions")
    for s in _socios(brain):
        d = os.path.join(base, s)
        try:
            for fn in os.listdir(d):
                if fn.endswith(".md"):
                    try:
                        m = os.path.getmtime(os.path.join(d, fn))
                    except OSError:
                        continue
                    mx = m if mx is None or m > mx else mx
        except OSError:
            continue
    return mx


def conflictos(brain, tope=20):
    """Archivos con «conflict» en el nombre bajo STATE/sessions/ (las copias
    en conflicto de Obsidian, Syncthing, Dropbox…). Rutas relativas."""
    base = os.path.join(brain, "STATE", "sessions")
    out = []
    for raiz, dirs, files in os.walk(base):
        if raiz[len(base):].count(os.sep) >= 3:
            dirs[:] = []
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in files:
            if "conflict" in f.lower():
                out.append(os.path.relpath(os.path.join(raiz, f), brain).replace(os.sep, "/"))
                if len(out) >= tope:
                    return sorted(out)
    return sorted(out)


def _vistas(brain, mi_id):
    """(ids con constancia, ids con sonda) de las OTRAS máquinas."""
    md, sondas = set(), set()
    try:
        names = os.listdir(carpeta(brain))
    except OSError:
        return [], []
    for n in names:
        if n.endswith(SONDA_SUFIJO):
            i = n[:-len(SONDA_SUFIJO)]
            if _ID_RE.match(i) and i != mi_id:
                sondas.add(i)
        elif n.endswith(".md"):
            i = n[:-3]
            if _ID_RE.match(i) and i != mi_id:
                md.add(i)
    return sorted(md), sorted(sondas)


def observar(brain, yo=None, sondear=True, registro=None, max_edad=None, timeout=None):
    """Lo que ESTA máquina ve ahora del cerebro (sin escribir nada). Con
    `sondear=False` no se pregunta por procesos: Obsidian sale de la propia
    constancia (`registro`), recién escrita al abrir. `max_edad`/`timeout`
    van a obsidian_abierto (dispatch: reusar un sondeo reciente, acotado)."""
    mi_id = (yo or {}).get("id", "")
    soc = _socio(brain)
    socios = _socios(brain)
    total = sum(_contar(brain, s) for s in socios)
    pest = (_contar(brain, soc) if soc in socios else 0) if soc else None
    md, sondas = _vistas(brain, mi_id)
    act = _actividad(brain)
    tiene = os.path.isdir(os.path.join(brain, ".obsidian"))
    if sondear:
        abierto = obsidian_abierto(max_edad=max_edad, timeout=timeout)
        boveda = boveda_abierta(brain) if tiene else None
    else:
        r = registro or {}
        abierto, boveda = r.get("obsidian_abierto"), r.get("boveda_abierta")
    return {"so": so(), "version": _version(), "socio": soc,
            "tiene_obsidian": tiene, "sync_obsidian": sync_obsidian(brain) if tiene else None,
            "obsidian_abierto": abierto, "boveda_abierta": boveda,
            "pestanas": pest, "pestanas_total": total,
            "actividad": _iso(_desde_epoch(act)) if act is not None else None,
            "maquinas_vistas": md, "sondas_vistas": sondas,
            "conflictos": conflictos(brain)}


# ── la constancia (.md en el cerebro) ───────────────────────────────────────
def _valor(v):
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(str(x) for x in v) + "]"
    return re.sub(r"[\r\n]+", " ", str(v)).strip()


def _leer_valor(k, s):
    s = s.strip()
    if k in _LISTAS:
        s = s.strip("[]")
        return sorted(x.strip() for x in s.split(",") if _ID_RE.match(x.strip()))
    if s in ("null", "~", ""):
        return None
    if s == "true":
        return True
    if s == "false":
        return False
    if k in ("pestanas", "pestanas_total"):
        try:
            return int(s)
        except ValueError:
            return None
    return s


def formatear(datos):
    lineas = ["---"] + ["%s: %s" % (k, _valor(datos.get(k))) for k in CAMPOS] + ["---", ""]
    lineas.append(_t("maquinas.md.titulo", "# Constancia de esta máquina (Workspace)"))
    lineas.append("")
    lineas.append(_t("maquinas.md.cuerpo",
                     "Workspace reescribe este archivo solo cuando abres un agente en esta "
                     "máquina. Sirve para avisar si el cerebro deja de llegar entre tus "
                     "máquinas. No lo edites ni lo borres: no guarda nada personal."))
    return "\n".join(lineas) + "\n"


def leer_constancia(path):
    """Frontmatter de una constancia → dict (solo los campos conocidos). Lee
    solo la cabecera: hasta el segundo `---` (o 64 líneas); None si no hay."""
    out = {}
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            if fh.readline().lstrip("\ufeff").strip() != "---":
                return None
            for _n, ln in zip(range(64), fh):
                if ln.strip() == "---":
                    return out
                if ":" not in ln:
                    continue
                k, v = ln.split(":", 1)
                k = k.strip()
                if k in CAMPOS:
                    out[k] = _leer_valor(k, v)
    except OSError:
        return None
    return None                                   # sin cierre: no es una constancia


def constancias(brain):
    """Las constancias de todas las máquinas en este cerebro (la del archivo
    manda: `id` = nombre del archivo)."""
    out = []
    d = carpeta(brain)
    try:
        names = sorted(os.listdir(d))
    except OSError:
        return out
    for n in names:
        if not n.endswith(".md") or not _ID_RE.match(n[:-3]):
            continue
        r = leer_constancia(os.path.join(d, n))
        if r is None:
            continue
        r["id"] = n[:-3]
        out.append(r)
    return out


def _asegurar_sonda(d, mi_id):
    p = os.path.join(d, mi_id + SONDA_SUFIJO)
    try:
        with open(p, encoding="utf-8") as fh:
            if fh.read() == SONDA:
                return
    except OSError:
        pass
    _escribir(p, SONDA)


def limpiar_temporales(brain, viejo=TMP_VIEJO_S):
    """Borra los temporales huérfanos (`*.tmp*`) de más de `viejo` s en
    STATE/maquinas/: los deja un hilo que murió a media escritura (el hub
    hace exec al abrir un agente). → cuántos borró. Falla suave."""
    d, n = carpeta(brain), 0
    try:
        names = os.listdir(d)
    except OSError:
        return 0
    limite = _ahora().timestamp() - viejo
    for f in names:
        if ".tmp" not in f:
            continue
        p = os.path.join(d, f)
        try:
            if os.path.isfile(p) and os.path.getmtime(p) < limite:
                os.unlink(p)
                n += 1
        except OSError:
            continue
    return n


def _ruta_llegadas():
    return os.path.join(_paths.state_dir(), ARCHIVO_LLEGADAS)


def _llegada(brain):
    """{"previo": epoch|None, "en": epoch} de la última vuelta de esta máquina
    a `brain` (estado local), o None."""
    d = _leer_json(_ruta_llegadas())
    e = (d.get("cerebros") or {}).get(_norm(brain)) if isinstance(d, dict) else None
    return e if isinstance(e, dict) and isinstance(e.get("en"), (int, float)) else None


def _anotar_llegada(brain, previo, en):
    """Anota una vuelta (reescribir tras más de LLEGADA_S sin constancia) para
    que otro proceso (dispatch tras el exec del hub) vea el visto previo."""
    p = _ruta_llegadas()
    try:
        with _Candado(p):
            d = _leer_json(p)
            d = d if isinstance(d, dict) else {}
            cer = d.get("cerebros") if isinstance(d.get("cerebros"), dict) else {}
            cer = {k: v for k, v in cer.items()          # sin crecer para siempre
                   if isinstance(v, dict) and en - float(v.get("en") or 0) < 30 * 86400}
            cer[_norm(brain)] = {"previo": previo, "en": en}
            _escribir(p, json.dumps({"version": 1, "cerebros": cer}, indent=1) + "\n")
    except Exception:
        pass


def _visto_en_disco(brain, yo):
    """Epoch del `visto` de la constancia de ESTA máquina en `brain`, o None."""
    if not yo:
        return None
    c = leer_constancia(os.path.join(carpeta(brain), yo["id"] + ".md"))
    v = _fecha((c or {}).get("visto"))
    return v.timestamp() if v else None


def _fijar_previo(brain, yo=None):
    """Fija (una vez por proceso) el visto previo de esta máquina en `brain`:
    el de una vuelta anotada hace menos de VENTANA_S, si la hay (la anotó
    otro proceso que ya reescribió); si no, el de la constancia en disco."""
    k = _norm(brain)
    if k in _PREVIO:
        return _PREVIO[k]
    yo = yo if yo is not None else maquina(crear=False)
    previo = _visto_en_disco(brain, yo)
    lleg = _llegada(brain)
    if lleg and 0 <= _ahora().timestamp() - float(lleg["en"]) < VENTANA_S:
        p = lleg.get("previo")
        previo = float(p) if isinstance(p, (int, float)) else None
    _PREVIO[k] = previo
    return previo


def visto_previo(brain):
    """Epoch del `visto` que ESTA máquina tenía en `brain` antes de esta
    apertura (la última vez que estuvo ahí), o None si nunca dejó constancia
    en ese cerebro (máquina o cerebro nuevos aquí, o una versión anterior):
    no se sabe si estuvo fuera.

    Contrato (frente B, archivo automático): se fija en memoria del proceso
    la primera vez que se pide o antes de reescribir la constancia propia, y
    no cambia después en el mismo proceso. Entre procesos: una reescritura
    tras más de 1 h sin constancia (una vuelta) se anota en el estado local y
    durante la hora siguiente cualquier proceso recibe ese visto anterior.
    Jamás levanta (None)."""
    try:
        return _fijar_previo(brain)
    except Exception:
        return None


def copia_al_dia(brain):
    """¿La copia de `brain` en ESTA máquina ya tiene lo último que escribieron
    las demás? Compara la `actividad` de las constancias de las otras
    máquinas (sin las retiradas ni las de un id viejo de esta) con lo más
    nuevo en disco aquí (STATE/sessions/<socio>/*.md, todas las carpetas),
    con TOLERANCIA_S de margen por los relojes.

    → False: alguna trae algo más nuevo que lo que hay aquí (el sync no ha
      terminado de llegar; no conviene decidir con esta copia).
      True: ninguna. None: no hay otras constancias con actividad (no se
      puede saber). Jamás levanta (None)."""
    try:
        yo = maquina(crear=False)
        mi_id = (yo or {}).get("id", "")
        ahora = _ahora()
        creada = _fecha((yo or {}).get("creada"))
        eti = (yo or {}).get("etiqueta") or etiqueta_host()
        mia = _actividad(brain)
        hay = False
        for r in constancias(brain):
            if r["id"] == mi_id:
                continue
            visto, act = _fecha(r.get("visto")), _fecha(r.get("actividad"))
            if not act or not visto or (ahora - visto).total_seconds() > RETIRADA_S:
                continue
            if creada and visto <= creada and r.get("etiqueta") == eti and r.get("so") == so():
                continue                              # un id viejo de esta misma máquina
            hay = True
            if mia is None or act.timestamp() > mia + TOLERANCIA_S:
                return False
        return True if hay else None
    except Exception:
        return None


def escribir(brain, yo=None, forzar=False, obs=None):
    """Deja la constancia de esta máquina en `brain` (y su sonda). Solo si
    algo cambió o si la anterior tiene más de 10 min (o `forzar`). → True si
    escribió la constancia. No crea cerebros: sin STATE/ no hace nada. Antes
    de reescribir fija visto_previo() y borra los temporales huérfanos."""
    if not brain or not os.path.isdir(os.path.join(brain, "STATE")):
        return False
    yo = yo or maquina()
    if not yo:
        return False
    d = carpeta(brain)
    path = os.path.join(d, yo["id"] + ".md")
    previo = leer_constancia(path) if os.path.exists(path) else None
    _fijar_previo(brain, yo)
    obs = obs or observar(brain, yo=yo)
    ahora = _ahora()
    desde = None
    if previo and previo.get("pestanas_total") == obs["pestanas_total"]:
        desde = previo.get("pestanas_desde")
    datos = {"maquina": yo["id"], "etiqueta": yo.get("etiqueta") or etiqueta_host(),
             "so": obs["so"], "version": obs["version"], "visto": _iso(ahora),
             "obsidian_abierto": obs["obsidian_abierto"], "boveda_abierta": obs["boveda_abierta"],
             "pestanas": obs["pestanas"], "pestanas_total": obs["pestanas_total"],
             "pestanas_desde": desde or _iso(ahora), "actividad": obs["actividad"],
             "maquinas_vistas": obs["maquinas_vistas"], "sondas_vistas": obs["sondas_vistas"]}
    os.makedirs(d, exist_ok=True)
    limpiar_temporales(brain)
    _asegurar_sonda(d, yo["id"])
    visto = _fecha((previo or {}).get("visto"))
    if previo and not forzar:
        igual = all(previo.get(k) == _leer_valor(k, _valor(datos[k])) for k in _SIN_VISTO)
        if igual and visto and 0 <= (ahora - visto).total_seconds() < INTERVALO_S:
            return False
    _escribir(path, formatear(datos))
    if not visto or (ahora - visto).total_seconds() > LLEGADA_S:
        _anotar_llegada(brain, visto.timestamp() if visto else None, ahora.timestamp())
    return True


def _cerebros_registrados():
    try:
        import messages
        return list(messages.registered_brains().values())
    except Exception:
        return []


def al_abrir(extra=(), presupuesto=PRESUPUESTO_S):
    """Al abrir el hub o un agente: la constancia en CADA cerebro registrado
    (más `extra`, primero). Con tope de tiempo; jamás levanta. → los cerebros
    donde se escribió."""
    hechos = []
    if isinstance(extra, str):
        extra = [extra]
    try:
        yo = maquina()
        if not yo:
            return hechos
        vistos, t0 = set(), time.monotonic()
        for b in list(extra or ()) + _cerebros_registrados():
            if not b or time.monotonic() - t0 > presupuesto:
                continue
            k = _norm(b)
            if k in vistos:
                continue
            vistos.add(k)
            try:
                if escribir(b, yo=yo):
                    hechos.append(b)
            except Exception:
                continue
    except Exception:
        pass
    return hechos


# ── lectura: estado, avisos y la línea del hub ──────────────────────────────
def estado(brain, sondear=True, yo=None, obs=None):
    """[esta máquina (yo=True), luego las demás] con: id, etiqueta, so,
    version, visto, hace_s, pestanas, pestanas_total, obsidian_abierto,
    boveda_abierta, sondas_vistas, maquinas_vistas, ve_sondas, anterior
    (una constancia vieja de esta misma máquina antes de cambiar de id),
    retirada (>60 días), desfasada y motivo ('vieja' | 'conteo' | '').
    `obs` = una observación ya hecha (observar) para no repetirla."""
    yo = yo if yo is not None else maquina(crear=False)
    mi_id = (yo or {}).get("id", "")
    ahora = _ahora()
    regs = constancias(brain)
    mio = next((r for r in regs if r["id"] == mi_id), None)
    obs = obs or observar(brain, yo=yo, sondear=sondear, registro=mio)
    desde = None
    if mio and mio.get("pestanas_total") == obs["pestanas_total"]:
        desde = _fecha(mio.get("pestanas_desde"))
    desde = desde or ahora
    faltan = [m for m in obs["maquinas_vistas"] if m not in obs["sondas_vistas"]]
    yo_e = dict(obs, id=mi_id, etiqueta=(yo or {}).get("etiqueta") or etiqueta_host(),
                visto=_iso(ahora), hace_s=0, yo=True, anterior=False, retirada=False,
                desfasada=False, motivo="", pestanas_desde=_iso(desde),
                ve_sondas=(not faltan) if obs["maquinas_vistas"] else None)
    out = [yo_e]
    creada = _fecha((yo or {}).get("creada"))
    act = _fecha(obs["actividad"])
    for r in regs:
        if r["id"] == mi_id:
            continue
        visto = _fecha(r.get("visto"))
        hace = (ahora - visto).total_seconds() if visto else None
        anterior = bool(creada and visto and visto <= creada
                        and r.get("etiqueta") == yo_e["etiqueta"] and r.get("so") == obs["so"])
        retirada = hace is not None and hace > RETIRADA_S
        desfasada, motivo = False, ""
        if visto and not anterior and not retirada:
            if hace > VIEJA_S and act and act > visto:
                desfasada, motivo = True, "vieja"
            else:
                tot = r.get("pestanas_total")
                if isinstance(tot, int) and tot != obs["pestanas_total"]:
                    suyo = _fecha(r.get("pestanas_desde")) or visto
                    juntos = (min(ahora, visto) - max(desde, suyo)).total_seconds()
                    if juntos > CONTEO_S:
                        desfasada, motivo = True, "conteo"
        ve = None
        if mi_id:
            if mi_id in (r.get("sondas_vistas") or []):
                ve = True
            elif mi_id in (r.get("maquinas_vistas") or []):
                ve = False
        e = {k: r.get(k) for k in CAMPOS}
        e.update(id=r["id"], hace_s=hace, yo=False, anterior=anterior, retirada=retirada,
                 desfasada=desfasada, motivo=motivo, ve_sondas=ve)
        out.append(e)
    return out


_TIPO = {"mac": "Mac", "windows": "PC", "linux": "Linux"}


def nombre(e):
    """«PC (escritorio-7k2l)»: el tipo por SO y la etiqueta."""
    tipo = _TIPO.get(str(e.get("so") or ""), _t("maquinas.otra", "Otra máquina"))
    eti = str(e.get("etiqueta") or "").strip()
    return "%s (%s)" % (tipo, eti) if eti else tipo


def _hace(seg):
    seg = max(0, int(seg or 0))
    if seg < 60:
        return _t("maquinas.hace.momento", "hace un momento")
    if seg < 3600:
        return _t("maquinas.hace.min", "hace {n} min", n=seg // 60)
    if seg < 48 * 3600:
        return _t("maquinas.hace.h", "hace {n} h", n=seg // 3600)
    return _t("maquinas.hace.dias", "hace {n} días", n=seg // 86400)


def _desde_cuando(dt, ahora):
    """«desde el lunes» (menos de una semana) o «desde el 28-oct»."""
    dt = dt.astimezone(ahora.tzinfo) if ahora.tzinfo else dt
    if (ahora - dt).total_seconds() < 6 * 86400:
        dias = _t("maquinas.dias", "lunes,martes,miércoles,jueves,viernes,sábado,domingo").split(",")
        return _t("maquinas.desde.dia", "desde el {dia}", dia=dias[dt.weekday() % len(dias)])
    meses = _t("maquinas.meses", "ene,feb,mar,abr,may,jun,jul,ago,sep,oct,nov,dic").split(",")
    return _t("maquinas.desde.fecha", "desde el {d}-{mes}", d=dt.day,
              mes=meses[(dt.month - 1) % len(meses)])


def _diferencia(suyas, mias):
    n = abs(int(suyas) - int(mias))
    if suyas < mias:
        return _t("maquinas.dif.menos", "ve {n} pestaña(s) menos que aquí", n=n)
    return _t("maquinas.dif.mas", "ve {n} pestaña(s) más que aquí", n=n)


def avisos_detalle(brain, sondear=True, est=None):
    """[{tipo, texto, accion}] — vacío si todo bien. Tipos: obsidian_cerrado,
    boveda_cerrada, vieja, conteo, conflictos."""
    est = est if est is not None else estado(brain, sondear=sondear)
    yo_e, out = est[0], []
    if yo_e.get("tiene_obsidian") and yo_e.get("sync_obsidian") is not False:
        if yo_e.get("obsidian_abierto") is False:
            out.append({"tipo": "obsidian_cerrado",
                        "texto": _t("maquinas.aviso.cerrado",
                                    "Obsidian está cerrado en esta máquina: este cerebro no se "
                                    "sincroniza hasta que lo abras"),
                        "accion": _t("maquinas.accion.cerrado",
                                     "abre Obsidian con la bóveda de este cerebro")})
        elif yo_e.get("obsidian_abierto") is True and yo_e.get("boveda_abierta") is False:
            out.append({"tipo": "boveda_cerrada",
                        "texto": _t("maquinas.aviso.boveda",
                                    "Obsidian está abierto pero sin la bóveda de este cerebro: "
                                    "solo sincroniza las bóvedas abiertas"),
                        "accion": _t("maquinas.accion.boveda",
                                     "en Obsidian, abre la bóveda «{carpeta}» (Abrir otra bóveda)",
                                     carpeta=os.path.basename(os.path.normpath(brain)))})
    ahora = _ahora()
    for e in est[1:]:
        if not e.get("desfasada"):
            continue
        if e["motivo"] == "vieja":
            out.append({"tipo": "vieja",
                        "texto": _t("maquinas.aviso.vieja",
                                    "{nombre}: sin noticias {cuando}, y aquí hubo cambios",
                                    nombre=nombre(e),
                                    cuando=_desde_cuando(_fecha(e["visto"]), ahora)),
                        "accion": _t("maquinas.accion.vieja",
                                     "en esa máquina, abre Obsidian con esta bóveda y revisa que "
                                     "Sync esté conectado")})
        elif e["motivo"] == "conteo":
            out.append({"tipo": "conteo",
                        "texto": _t("maquinas.aviso.conteo",
                                    "{nombre} {dif} desde hace más de 1 h: el sync no está llegando",
                                    nombre=nombre(e),
                                    dif=_diferencia(e["pestanas_total"], yo_e["pestanas_total"])),
                        "accion": _t("maquinas.accion.conteo",
                                     "revisa Obsidian Sync en las dos máquinas: conectado y con "
                                     "la misma bóveda remota")})
    if yo_e.get("conflictos"):
        c = yo_e["conflictos"]
        out.append({"tipo": "conflictos",
                    "texto": _t("maquinas.aviso.conflictos",
                                "{n} archivo(s) en conflicto en STATE/sessions/ ({ej})",
                                n=len(c), ej=c[0]),
                    "accion": _t("maquinas.accion.conflictos",
                                 "ábrelos y quédate con la versión buena; Workspace no los toca")})
    return out


def avisos(brain, sondear=True):
    """Los avisos de una línea (textos). Falla suave → []."""
    try:
        return [a["texto"] for a in avisos_detalle(brain, sondear=sondear)]
    except Exception:
        return []


def aviso_linea(brain, sondear=True, est=None):
    """UNA línea para la terminal y el contexto de arranque, '' si todo bien."""
    try:
        av = [a["texto"] for a in avisos_detalle(brain, sondear=sondear, est=est)]
    except Exception:
        av = []
    if not av:
        return ""
    return _t("maquinas.linea", "WORKSPACE · sync: {avisos}", avisos="; ".join(av))


def _constancia_y_aviso(brain, hasta):
    """Lo de al_abrir_agente: observar UNA vez (Obsidian: el sondeo guardado
    si es reciente; si no, uno acotado al tiempo que queda), escribir la
    constancia de este cerebro y armar la línea de aviso con lo mismo."""
    yo = maquina()
    if not yo or not brain or not os.path.isdir(os.path.join(brain, "STATE")):
        return ""
    obs = observar(brain, yo=yo, max_edad=SONDEO_S,
                   timeout=max(0.05, hasta - time.monotonic()))
    escribir(brain, yo=yo, obs=obs)
    if time.monotonic() > hasta:
        return ""                                 # fuera de tiempo: nadie la espera
    return aviso_linea(brain, est=estado(brain, yo=yo, obs=obs))


def al_abrir_agente(brain, presupuesto=None):
    """Al abrir UN agente (dispatch): solo la constancia del cerebro que se
    abre (el recorrido de todos es del hilo del hub) y la línea de aviso de
    ese cerebro, '' si no hay. Tope TOTAL de `presupuesto` s (default
    PRESUPUESTO_AGENTE_S = 0.3): el trabajo corre en un hilo y lo que no
    termine a tiempo sigue solo (sin aviso esta vez; si el proceso hace exec,
    el temporal que quede lo borra la siguiente escritura). visto_previo()
    queda fijado ANTES, en este hilo. Jamás levanta."""
    t0 = time.monotonic()
    tope = PRESUPUESTO_AGENTE_S if presupuesto is None else float(presupuesto)
    res = {}
    try:
        _fijar_previo(brain)
    except Exception:
        pass

    def _trabajo():
        try:
            res["linea"] = _constancia_y_aviso(brain, t0 + tope)
        except Exception:
            res["linea"] = ""
    try:
        th = threading.Thread(target=_trabajo, name="maquinas-al-abrir", daemon=True)
        th.start()
        th.join(max(0.0, tope - (time.monotonic() - t0)))
    except Exception:
        return ""
    return res.get("linea", "")


def resumen_linea(brain, sondear=True):
    """UNA línea para el hub: el primer aviso (+N) o la otra máquina más
    reciente («PC (escritorio): vista hace 2 h · mismas 32 pestañas»). ''
    si solo esta máquina ha abierto el cerebro. Jamás levanta."""
    try:
        est = estado(brain, sondear=sondear)
        av = [a["texto"] for a in avisos_detalle(brain, est=est)]
        if av:
            return av[0] + ((" (+%d)" % (len(av) - 1)) if len(av) > 1 else "")
        yo_e = est[0]
        otras = sorted((e for e in est[1:] if e.get("hace_s") is not None
                        and not e["anterior"] and not e["retirada"]),
                       key=lambda e: e["hace_s"])
        if not otras:
            return ""
        e = otras[0]
        if e.get("pestanas_total") == yo_e["pestanas_total"]:
            mias = yo_e["pestanas"] if yo_e["pestanas"] is not None else yo_e["pestanas_total"]
            cola = _t("maquinas.resumen.mismas", "mismas {n} pestañas", n=mias)
        elif isinstance(e.get("pestanas_total"), int):
            cola = _diferencia(e["pestanas_total"], yo_e["pestanas_total"])
        else:
            cola = ""
        linea = _t("maquinas.resumen.vista", "{nombre}: vista {hace}", nombre=nombre(e),
                   hace=_hace(e["hace_s"]))
        if cola:
            linea += " · " + cola
        if len(otras) > 1:
            linea += " · " + _t("maquinas.resumen.mas", "+{n} máquina(s)", n=len(otras) - 1)
        return linea
    except Exception:
        return ""


def _main(argv=None):
    """`python3 maquinas.py [cerebro …]` — escribe la constancia y muestra el
    estado (diagnóstico)."""
    args = list(sys.argv[1:] if argv is None else argv)
    yo = maquina()
    print("esta máquina: %s (%s)" % ((yo or {}).get("id", "?"), (yo or {}).get("etiqueta", "?")))
    for b in args or _cerebros_registrados():
        escribir(b, yo=yo)
        print("\n%s" % b)
        for e in estado(b, yo=yo):
            print("  %s%s · visto %s · pestañas %s/%s · sondas %s%s" % (
                "*" if e["yo"] else " ", nombre(e), e.get("visto"), e.get("pestanas"),
                e.get("pestanas_total"), e.get("ve_sondas"),
                (" · DESFASADA (%s)" % e["motivo"]) if e["desfasada"] else ""))
        print("  " + (resumen_linea(b) or "(solo esta máquina)"))
    return 0


if __name__ == "__main__":
    sys.exit(_main())
