#!/usr/bin/env python3
"""WORKSPACE · conversaciones — nivel 2 de sesiones: la conversación de Claude
Code viaja con el cerebro a tus otras máquinas. Opcional y APAGADO de fábrica.

Permiso POR CEREBRO (vale igual para todas las máquinas y personas que lo
usan): `llevar_conversacion: claude-code | off` en el frontmatter de
`STATE/cerebro.md` (el archivo del id del cerebro de identidad.py; si no existe
se crea con su escritor). Se cambia con `workspace sesiones conversacion
on|off|ver`. Si el cerebro no ha decidido, manda el ajuste de la máquina
`sesiones.llevar_conversacion` (off | claude-code; de fábrica off; pensado para
crecer a codex). En un cerebro compartido, todos los que lo usan pueden ver esas
conversaciones: para privacidad, un cerebro aparte. El tope
`sesiones.conversacion_max_mb` es de cada máquina (de fábrica 4, cabe en
Obsidian Sync Standard, que acepta 5 MB por archivo).

Al cerrar — `guardar()`, desde hooks/transcript_backup.py (SessionEnd) y
hooks/memory_flush.py (PreCompact) — deja la copia en
`<cerebro>/motores/claude-code/conversaciones/<socio>/<id>.jsonl.gz`:
  · solo la conversación de una PESTAÑA de Workspace (las corridas sueltas en
    el cerebro no ensucian el sync);
  · solo si cambió (sha256 del contenido descomprimido);
  · no sube si la copia comprimida pasa el tope, ni si secret_scan encuentra
    algo que parece una llave: la conversación se queda en esta máquina y queda
    un aviso de una línea que sale al abrir esa pestaña aquí;
  · si la copia del cerebro siguió en otra máquina (es más nueva y no es esta
    misma conversación con menos líneas), no se pisa; si la de aquí es la más
    nueva, la del cerebro se respalda en transcripts-backup/ antes de pisarla;
  · escritura atómica (temporal + reemplazo con reintento en Windows).

Al abrir — `al_abrir()`, desde engines/claude_code.launch justo antes de
decidir entre `--resume` y `--session-id`:
  · solo de la carpeta del socio resuelto (`conversaciones/<socio>/`): jamás
    la conversación de otra persona;
  · sin .jsonl local y con copia en el cerebro → se restaura byte a byte en
    session_paths.session_dir(cerebro) de esta máquina y el motor usa --resume;
  · con .jsonl local: si la copia del cerebro es más vieja, gana la local; si es
    más nueva (siguió en otra máquina), la local se respalda en
    transcripts-backup/ y se trae la del cerebro;
  · si algo falla, devuelve el aviso y deja todo como estaba: el motor cae a lo
    de siempre (--session-id si no hay conversación local). Nunca lanza ni
    bloquea la apertura.

Verificado en vivo (Claude Code 2.1.318 en Mac, 2026-11-05): `claude --resume
<id>` retoma un .jsonl copiado a la carpeta de otro proyecto aunque sus
registros traigan otro `cwd` (también una ruta de Windows que aquí no existe),
en `-p` y en interactivo. Por eso se restaura tal cual: `cwd` NO se reescribe.

Gancho del frente C (sesiones v2 §C, maquinas.py): si alguna máquina no recibe
los archivos que no son notas (su `sondas_vistas` no trae a las demás), el aviso
dice dónde prender «Sync all other types». Importación perezosa: sin
maquinas.py no se avisa nada.

Es un archivo del usuario entre sus máquinas: no se toca código ni config de
Claude Code. El .gitignore del cerebro lleva `motores/*/conversaciones/`
(install.GITIGNORE_LINES + migración) para que el espejo de git nunca las suba.
Stdlib, Python 3.9+, Mac/Windows/Linux. Falla suave en todo.
"""
import datetime
import gzip
import hashlib
import json
import os
import re
import shutil
import struct
import sys
import zlib

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

#: Motores con nivel 2 (los valores del ajuste distintos de «off»).
MOTORES = ("claude-code",)
#: La línea del .gitignore del cerebro (install.GITIGNORE_LINES la incluye).
GITIGNORE_LINE = "motores/*/conversaciones/"
TOPE_MB_FABRICA = 4
#: Una conversación de texto no comprime más que esto: una más grande ni se
#: intenta comprimir (no pasaría el tope y gastaría el tiempo del cierre).
RATIO_MAX = 25
_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}\Z")
_SOCIO_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}\Z")
_TS_RE = re.compile(rb'"timestamp"\s*:\s*"([0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9:.]+(?:Z|[+-][0-9:]+)?)"')
_COLA_TS = 256 * 1024
# Escapes JSON que parten las líneas que secret_scan ancla (VAR=valor al final
# de una línea dentro de un resultado de herramienta).
_ESC_RE = re.compile(r'\\r\\n|\\[nt"]')
_ESC = {"\\r\\n": "\n", "\\n": "\n", "\\t": "\t", '\\"': '"'}
_MAX_AVISOS = 50


# ── permiso: el del cerebro; si no decidió, el ajuste de la máquina ────────
PERMISO_CLAVE = "llevar_conversacion"
_PERMISO_RE = re.compile(r"^llevar_conversacion:[ \t]*([^\s#]*)[ \t]*(?:#.*)?$")


def modo_maquina():
    """El ajuste de ESTA máquina, `sesiones.llevar_conversacion` ('off' ante
    cualquier duda: sin settings.py, store roto o un valor desconocido)."""
    try:
        import settings
        v = str(settings.get("sesiones.llevar_conversacion", "off") or "off")
    except Exception:
        return "off"
    v = v.strip().lower()
    return v if v in MOTORES else "off"


def _cerebro_md(brain):
    try:
        import identidad
        return os.path.join(brain, *identidad.ID_REL)
    except Exception:
        return os.path.join(brain, "STATE", "cerebro.md")


def _frontmatter(lineas):
    """(i, j): el frontmatter son lineas[i+1:j]; (None, None) si no hay."""
    if lineas and lineas[0].strip() == "---":
        for j in range(1, len(lineas)):
            if lineas[j].strip() == "---":
                return 0, j
    return None, None


def permiso_cerebro(brain):
    """Lo que decidió ESE cerebro: 'claude-code', 'off' (u otro motor futuro),
    o '' si no ha decidido. Si un choque de sync dejó dos valores distintos,
    'off' (el mismo en todas las máquinas, y del lado de la privacidad)."""
    if not brain:
        return ""
    try:
        with open(_cerebro_md(brain), "rb") as fh:
            texto = fh.read(16384).decode("utf-8", "replace").replace("\r\n", "\n")
    except OSError:
        return ""
    lineas = texto.lstrip("\ufeff").split("\n")
    i, j = _frontmatter(lineas)
    if i is None:
        return ""
    vals = set()
    for ln in lineas[i + 1:j]:
        m = _PERMISO_RE.match(ln.strip())
        if m:
            v = m.group(1).strip().strip("\"'").lower()
            vals.add("claude-code" if v in ("on", "si", "sí", "true", "yes") else
                     "off" if v in ("", "no", "false", "apagado") else v)
    if not vals:
        return ""
    return vals.pop() if len(vals) == 1 else "off"


def modo(brain=None):
    """El valor efectivo para `brain`: el permiso del cerebro si lo decidió; si
    no, el ajuste de la máquina. 'off' ante cualquier duda."""
    v = permiso_cerebro(brain) if brain else ""
    if not v:
        return modo_maquina()
    return v if v in MOTORES else "off"


def origen(brain):
    """'cerebro' si el cerebro decidió; 'maquina' si manda el ajuste local."""
    return "cerebro" if (brain and permiso_cerebro(brain)) else "maquina"


def activo(motor="claude-code", brain=None):
    return modo(brain) == motor


def fijar_permiso(brain, valor):
    """Guarda el permiso de ESTE cerebro en el frontmatter de STATE/cerebro.md
    (viaja con el cerebro: lo ven todas las máquinas y personas que lo usan).
    Si el archivo no existe, primero lo crea identidad (con su formato y su id,
    sin duplicarlo). Solo toca la línea `llevar_conversacion:`; el resto queda
    byte a byte. ValueError con un mensaje simple si no se puede."""
    valor = str(valor or "").strip().lower()
    if valor not in MOTORES + ("off",):
        raise ValueError("valor inválido: %s (usa %s u off)" % (valor, "/".join(MOTORES)))
    if not brain or not os.path.isdir(os.path.join(brain, "STATE")):
        raise ValueError("no parece un cerebro (le falta STATE/)")
    import identidad
    identidad.asegurar_id(brain)
    path = _cerebro_md(brain)
    from olock import local_lock
    with local_lock(path, timeout=5):
        try:
            with open(path, "rb") as fh:
                raw = fh.read()
        except FileNotFoundError:
            raise ValueError("no pude crear STATE/cerebro.md")
        try:
            texto = raw.decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError("STATE/cerebro.md no está en UTF-8: no lo toco")
        bom = texto.startswith("\ufeff")
        cuerpo = texto[1:] if bom else texto
        eol = "\r\n" if "\r\n" in cuerpo else "\n"
        lineas = cuerpo.replace("\r\n", "\n").split("\n")
        linea = "%s: %s" % (PERMISO_CLAVE, valor)
        i, j = _frontmatter(lineas)
        if i is None:
            nuevas = ["---", linea, "---"] + lineas
        else:
            fm = [ln for ln in lineas[i + 1:j] if not _PERMISO_RE.match(ln.strip())]
            nuevas = lineas[:i + 1] + fm + [linea] + lineas[j:]
        nuevo = ("\ufeff" if bom else "") + eol.join(nuevas)
        if nuevo != texto:
            identidad._escribir_texto(path, nuevo)   # frente C: helper común (reintento)
    if permiso_cerebro(brain) != valor:
        raise ValueError("no pude guardar el permiso en STATE/cerebro.md")
    return valor


# ── ajustes de la máquina ───────────────────────────────────────────────────


def tope_bytes():
    try:
        import settings
        mb = int(settings.get("sesiones.conversacion_max_mb", TOPE_MB_FABRICA))
    except Exception:
        mb = TOPE_MB_FABRICA
    return max(1, mb) * 1024 * 1024


# ── rutas ───────────────────────────────────────────────────────────────────
def id_valido(sid):
    return bool(_ID_RE.match(str(sid or "")))


def carpeta(brain, socio=None, motor="claude-code"):
    """`<cerebro>/motores/<motor>/conversaciones/<socio>/`, una carpeta por
    persona. '' si no se sabe quién es el socio de esta máquina."""
    if socio is None:
        try:
            import sessions_registry
            socio = sessions_registry.socio(brain)
        except Exception:
            socio = ""
    socio = str(socio or "").strip().lower()
    if not brain or not _SOCIO_RE.match(socio):
        return ""
    return os.path.join(brain, "motores", motor, "conversaciones", socio)


def copia_path(brain, sid, socio=None):
    """La copia comprimida de la conversación `sid` en el cerebro ('' si el id
    o el socio no sirven para armar una ruta segura)."""
    if not id_valido(sid):
        return ""
    d = carpeta(brain, socio)
    return os.path.join(d, str(sid) + ".jsonl.gz") if d else ""


def _local_path(brain, sid):
    import session_paths
    return session_paths.session_file(brain, sid)


def _candado_local(sid):
    """Candado de la conversación LOCAL `sid`, en `<estado>/locks/` (nunca junto
    al .jsonl: ~/.claude es de Claude Code y ahí no se crea nada)."""
    import paths
    from olock import file_lock
    return file_lock(os.path.join(paths.state_dir(), "locks", "conversacion-" + str(sid)),
                     timeout=3)


def _respaldos_dir(brain):
    """`<estado>/transcripts-backup/<enc>/`: la misma carpeta del respaldo Y2b
    (hooks/transcript_backup.py), fuera del cerebro."""
    import paths
    import session_paths
    return os.path.join(paths.state_dir(), "transcripts-backup",
                        os.path.basename(session_paths.session_dir(brain)))


def _sello():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def _ruta_respaldo(brain, sid, tipo, ext):
    """Ruta NUEVA en transcripts-backup/ (jamás pisa un respaldo anterior)."""
    d = _respaldos_dir(brain)
    os.makedirs(d, exist_ok=True)
    base = "%s.%s-%s" % (sid, tipo, _sello())
    p, n = os.path.join(d, base + ext), 1
    while os.path.exists(p):
        n += 1
        p = os.path.join(d, "%s-%d%s" % (base, n, ext))
    return p


def _humano(ruta):
    casa = os.path.expanduser("~")
    return ("~" + ruta[len(casa):]) if casa and ruta.startswith(casa + os.sep) else ruta


# ── lectura y escritura ─────────────────────────────────────────────────────
def _escribir(path, data):
    """Escritura atómica con reintento en Windows (temporal + reemplazo).
    Si falla del todo, el temporal se borra y la excepción sube."""
    import memoria
    os.makedirs(os.path.dirname(path), exist_ok=True)
    memoria._atomic(path, data)   # frente C: helper común


def _mtime_gz(raw_gz):
    """El MTIME de la cabecera gzip: la hora del .jsonl de origen al guardarlo."""
    try:
        return struct.unpack("<I", raw_gz[4:8])[0]
    except Exception:
        return 0


def _leer_copia(path):
    """(contenido descomprimido, mtime de origen) o (None, 0) si no hay copia.
    Una copia dañada (CRC, truncada a medio sync) LANZA ValueError."""
    try:
        with open(path, "rb") as fh:
            gz = fh.read()
    except FileNotFoundError:
        return None, 0
    try:
        data = gzip.decompress(gz)
    except (OSError, EOFError, zlib.error) as exc:
        raise ValueError("copia dañada (%s)" % type(exc).__name__)
    return data, _mtime_gz(gz)


def _parece_conversacion(data):
    """La primera línea con algo es un objeto JSON (formato .jsonl de Claude Code)."""
    for ln in data.split(b"\n", 50)[:50]:
        ln = ln.strip()
        if not ln:
            continue
        try:
            return isinstance(json.loads(ln.decode("utf-8")), dict)
        except Exception:
            return False
    return False


def _ultimo_ts(data):
    """La marca de tiempo más reciente de las últimas líneas (None si no hay).
    Si la cola no trae ninguna (un último registro enorme), se busca en todo."""
    mejor = _max_ts(data[-_COLA_TS:])
    if mejor is None and len(data) > _COLA_TS:
        mejor = _max_ts(data)
    return mejor


def _max_ts(data):
    mejor = None
    for m in _TS_RE.finditer(data):
        s = m.group(1).decode("ascii", "replace").replace("Z", "+00:00")
        try:
            t = datetime.datetime.fromisoformat(s)
        except ValueError:
            continue
        if t.tzinfo is None:
            t = t.replace(tzinfo=datetime.timezone.utc)
        if mejor is None or t > mejor:
            mejor = t
    return mejor


def _mas_nueva(a, b, mtime_a, mtime_b):
    """¿La conversación `a` es más reciente que `b`? Por la última marca de
    tiempo de sus registros; sin marcas, por la hora de los archivos."""
    ta, tb = _ultimo_ts(a), _ultimo_ts(b)
    if ta is not None and tb is not None:
        return ta > tb
    return float(mtime_a or 0) > float(mtime_b or 0)


def _secretos(data):
    """Hallazgos de secret_scan (lista; vacía = limpio) o None si no se pudo
    revisar (entonces NO se sube). El escape de emergencia del escáner
    (WORKSPACE_ALLOW_SECRET) se respeta y deja su rastro, como en todo el gate."""
    try:
        import secret_scan
        txt = _ESC_RE.sub(lambda m: _ESC[m.group(0)], data.decode("utf-8", "replace"))
        if secret_scan.env_override_active():
            return secret_scan.gate_text(txt, where="conversación de Claude Code")
        return secret_scan.scan_text(txt)
    except Exception:
        return None


# ── estado local: avisos pendientes (por máquina, fuera del cerebro) ────────
def _estado_path():
    import paths
    return os.path.join(paths.state_dir(), "conversaciones.json")


def _estado_leer():
    try:
        with open(_estado_path(), encoding="utf-8") as fh:
            data = json.load(fh)
    except Exception:
        data = {}
    if not isinstance(data, dict):
        data = {}
    data["version"] = 1
    if not isinstance(data.get("avisos"), dict):
        data["avisos"] = {}
    return data


def _estado_cambiar(fn):
    """Lee-modifica-escribe el estado local bajo su candado. Devuelve lo que
    devuelva `fn`. Falla suave: None."""
    p = _estado_path()
    try:
        from olock import file_lock
        with file_lock(p, timeout=3):
            data = _estado_leer()
            out = fn(data)
            avisos = data["avisos"]
            if len(avisos) > _MAX_AVISOS:
                for k in sorted(avisos, key=lambda k: str(avisos[k].get("ts", "")))[:-_MAX_AVISOS]:
                    avisos.pop(k, None)
            _escribir(p, json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
            return out
    except Exception:
        return None


def _anotar_aviso(sid, linea):
    def fn(data):
        data["avisos"][sid] = {"linea": linea,
                               "ts": datetime.datetime.now().isoformat(timespec="seconds")}
    _estado_cambiar(fn)


def _quitar_aviso(sid):
    try:
        if sid not in _estado_leer()["avisos"]:
            return                              # nada que escribir
    except Exception:
        return
    _estado_cambiar(lambda data: data["avisos"].pop(sid, None))


def tomar_aviso(sid):
    """El aviso pendiente del último guardado de `sid` ('' si no hay). Sale
    una vez: al tomarlo se borra."""
    try:
        if sid not in _estado_leer()["avisos"]:
            return ""
    except Exception:
        return ""
    v = _estado_cambiar(lambda data: data["avisos"].pop(sid, None))
    return str((v or {}).get("linea") or "")


def _log(rec):
    """Rastro local (<estado>/logs/conversaciones.log): qué se guardó o trajo y
    por qué no, para diagnosticar entre máquinas sin adivinar."""
    try:
        import paths
        d = os.path.join(paths.state_dir(), "logs")
        os.makedirs(d, exist_ok=True)
        rec = dict(rec, ts=datetime.datetime.now().isoformat(timespec="seconds"))
        with open(os.path.join(d, "conversaciones.log"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ── gancho del frente C: ¿alguna máquina no recibe los «otros tipos»? ───────
def _importar_maquinas():
    """maquinas.py del frente C, o None si todavía no está (perezoso)."""
    try:
        import maquinas
        return maquinas
    except Exception:
        return None


def maquinas_sin_otros_tipos(brain):
    """Etiquetas de las máquinas que NO reciben los archivos que no son notas
    (`.jsonl.gz` incluido). Gancho del frente C (maquinas.py), importación
    perezosa: sin el módulo, o con una API distinta, devuelve [] y no se avisa.

    Contrato que se lee de `maquinas.estado(brain)` (una fila dict por máquina):
      · `ve_sondas` (bool), si C ya da el veredicto; si no,
      · `id` + `sondas_vistas` (ids de las máquinas cuya sonda ve esa máquina):
        le falta alguna de las otras ⇒ en esa máquina está apagado «Sync all
        other types» (o hay un filtro).
    `etiqueta` es el nombre que se muestra."""
    try:
        mod = _importar_maquinas()
        filas = [f for f in (mod.estado(brain) or []) if isinstance(f, dict)] if mod else []
    except Exception:
        return []
    ids = [str(f.get("id")) for f in filas if f.get("id")]
    malas = []
    for f in filas:
        nombre = str(f.get("etiqueta") or f.get("id") or "").strip()
        if not nombre:
            continue
        if isinstance(f.get("ve_sondas"), bool):
            if not f["ve_sondas"]:
                malas.append(nombre)
            continue
        vistas = f.get("sondas_vistas")
        if not isinstance(vistas, (list, tuple)) or not f.get("id"):
            continue
        otras = set(ids) - {str(f["id"])}
        if otras - {str(x) for x in vistas}:
            malas.append(nombre)
    return malas


def _aviso_sonda(brain):
    """Una vez al día como mucho: dónde prender «Sync all other types»."""
    hoy = datetime.date.today().isoformat()
    if _estado_leer().get("sonda_dia") == hoy:
        return ""
    malas = maquinas_sin_otros_tipos(brain)
    if not malas:
        return ""

    def fn(data):
        if data.get("sonda_dia") == hoy:
            return False
        data["sonda_dia"] = hoy
        return True
    if not _estado_cambiar(fn):
        return ""
    quien = ", ".join("«%s»" % m for m in malas[:3])
    return ("%s no %s la conversación de tus pestañas: en Obsidian › Ajustes › Sync, "
            "prende «Sync all other types» (va en cada dispositivo)."
            % (quien, "recibe" if len(malas) == 1 else "reciben"))


# ── pertenencia: solo viaja la conversación de una pestaña ──────────────────
def _es_de_claude_code(payload):
    motor = str((payload or {}).get("engine") or "").strip()
    return motor in ("", "claude-code")


def _es_de_pestana(brain, sid, env):
    if str(env.get("WORKSPACE_WID") or "").strip() == sid:
        return True
    try:
        import sessions_registry
        return bool(sessions_registry.owner(brain, "claude-code", sid))
    except Exception:
        return False


def _raiz(transcript, brain, env):
    """El cerebro DUEÑO de `transcript`: el de WORKSPACE_BRAIN o el del `cwd`
    del hook, solo si su carpeta de sesiones de Claude Code (session_paths) es
    la del transcript. Un WORKSPACE_BRAIN heredado de otra sesión (un `claude`
    abierto dentro de otro) jamás manda la conversación a otro cerebro. ''
    si ninguno es el dueño."""
    import memoria
    import session_paths

    def real(p):
        return os.path.normcase(os.path.realpath(p))
    carpeta = real(os.path.dirname(os.path.abspath(transcript)))
    for cand in (env.get("WORKSPACE_BRAIN"), brain):
        if not cand:
            continue
        root = memoria.raiz_cerebro(cand)
        if real(session_paths.session_dir(root)) == carpeta:
            return root
    return ""


# ── al cerrar ───────────────────────────────────────────────────────────────
def guardar(brain, transcript, payload=None, env=None):
    """Guarda la conversación `transcript` (.jsonl de Claude Code) en el
    cerebro. Devuelve {"estado", "aviso", "ruta"}; nunca lanza.

    estados: apagado · no_aplica · sin_pestana · sin_socio · sin_cambios ·
    guardada · grande · secreto · sin_revisar · otra_mas_nueva · error."""
    env = os.environ if env is None else env
    res = {"estado": "apagado", "aviso": "", "ruta": ""}
    try:
        return _guardar(brain, str(transcript or ""), payload or {}, env, res)
    except Exception as exc:
        res.update(estado="error", aviso="")
        _log({"accion": "guardar", "estado": "error", "error": type(exc).__name__})
        return res


def _guardar(brain, transcript, payload, env, res):
    if not (transcript.endswith(".jsonl") and os.path.isfile(transcript)) \
            or not _es_de_claude_code(payload):
        res["estado"] = "no_aplica"
        return res
    sid = os.path.basename(transcript)[:-len(".jsonl")]
    root = _raiz(transcript, brain, env)
    if not (root and id_valido(sid)):
        res["estado"] = "no_aplica"
        return res
    if not activo("claude-code", root):          # permiso del cerebro o de la máquina
        res["estado"] = "apagado"
        return res
    if not _es_de_pestana(root, sid, env):
        res["estado"] = "sin_pestana"
        return res
    import sessions_registry
    socio = sessions_registry.socio(root)
    destino = copia_path(root, sid, socio)
    if not destino:
        res["estado"] = "sin_socio"
        return res
    pestana = str(env.get("WORKSPACE_WS") or sid[:8]).strip()
    tope = tope_bytes()
    tope_mb = tope // (1024 * 1024)

    def no_sube(estado, linea, retirar=False):
        bk = _retirar(destino, root, sid) if retirar else ""
        if bk:
            linea = linea[:-1] + " (saqué del cerebro la copia anterior, ya no estaba al día)."
        res.update(estado=estado, aviso=linea)
        _anotar_aviso(sid, linea)
        _log({"accion": "guardar", "estado": estado, "id": sid, "retirada": bk})
        return res

    from olock import local_lock
    with local_lock(destino, timeout=5):
        try:
            previo, mtime_previo = _leer_copia(destino)
        except ValueError:
            previo, mtime_previo = None, 0          # dañada: se reemplaza
        tam = os.path.getsize(transcript)
        if tam > tope * RATIO_MAX:
            return no_sube("grande", "la conversación de «%s» pesa %.0f MB: se queda en esta "
                           "máquina (el tope para llevarla es %d MB comprimida; ajuste "
                           "sesiones.conversacion_max_mb)." % (pestana, tam / 1048576.0, tope_mb),
                           retirar=previo is not None and _empieza_con(transcript, previo))
        with open(transcript, "rb") as fh:
            raw = fh.read()
        mtime = int(os.stat(transcript).st_mtime)
        if previo is not None and hashlib.sha256(previo).digest() == hashlib.sha256(raw).digest():
            res["estado"] = "sin_cambios"
            _quitar_aviso(sid)
            return res
        continua = previo is not None and raw.startswith(previo)
        if previo is not None and not continua \
                and _mas_nueva(previo, raw, mtime_previo, mtime):
            return no_sube("otra_mas_nueva", "la conversación de «%s» siguió en otra máquina: "
                           "no pisé la del cerebro; la de aquí se queda en esta máquina."
                           % pestana)
        gz = gzip.compress(raw, 6, mtime=mtime)   # determinista: mismos bytes, mismo archivo
        if len(gz) > tope:
            return no_sube("grande", "la conversación de «%s» pesa %.1f MB comprimida y el "
                           "tope es %d MB: se queda en esta máquina (ajuste "
                           "sesiones.conversacion_max_mb)." % (pestana, len(gz) / 1048576.0, tope_mb),
                           retirar=continua)
        # La parte que ya estaba en el cerebro ya pasó por el escáner al subir.
        hallazgos = _secretos(raw[len(previo):] if continua else raw)
        if hallazgos is None:
            return no_sube("sin_revisar", "no pude revisar si la conversación de «%s» trae "
                           "llaves: se queda en esta máquina." % pestana, retirar=continua)
        if hallazgos:
            return no_sube("secreto", "la conversación de «%s» trae algo que parece una llave: "
                           "se queda en esta máquina." % pestana, retirar=continua)
        if previo is not None and not continua:
            # La de aquí es la más nueva pero la del cerebro no es su principio:
            # se respalda (fuera del cerebro) antes de pisarla. Nada se pierde.
            shutil.copy2(destino, _ruta_respaldo(root, sid, "cerebro", ".jsonl.gz"))
        try:
            _escribir(destino, gz)
        except OSError as exc:
            return no_sube("error", "no pude guardar la conversación de «%s» en el cerebro "
                           "(%s): se queda en esta máquina." % (pestana, type(exc).__name__))
    _quitar_aviso(sid)
    res.update(estado="guardada", ruta=destino)
    _log({"accion": "guardar", "estado": "guardada", "id": sid, "bytes": len(gz)})
    return res


def _empieza_con(transcript, previo):
    """¿El .jsonl de aquí empieza con la copia del cerebro? (sin leerlo entero)"""
    try:
        with open(transcript, "rb") as fh:
            return fh.read(len(previo)) == previo
    except OSError:
        return False


def _retirar(destino, root, sid):
    """La copia del cerebro es el principio de la de aquí (ya no está al día) y
    la nueva no puede subir: sale del cerebro a transcripts-backup/ de esta
    máquina (nada se borra), para que otra máquina no retome una conversación
    vieja sin saberlo. Solo con la copia más vieja: una que siguió en otra
    máquina jamás se toca. Devuelve la ruta del respaldo ('' si no aplicó)."""
    try:
        if not os.path.isfile(destino):
            return ""
        bk = _ruta_respaldo(root, sid, "cerebro", ".jsonl.gz")
        shutil.copy2(destino, bk)
        os.remove(destino)
        return bk
    except OSError:
        return ""


# ── al abrir ────────────────────────────────────────────────────────────────
def al_abrir(brain, sid, pestana=""):
    """Antes de que el motor decida entre --resume y --session-id: trae la
    conversación del cerebro si aquí no está o si la del cerebro es más nueva.
    Devuelve las líneas de aviso (lista, vacía = nada que decir). Nunca lanza:
    si algo falla, todo queda como estaba y el motor sigue como siempre."""
    if not id_valido(sid) or not activo("claude-code", brain):
        return []
    pestana = str(pestana or sid[:8])
    avisos = []
    try:
        pend = tomar_aviso(sid)
        if pend:
            avisos.append(pend)
        linea = _traer(brain, sid, pestana)
        if linea:
            avisos.append(linea)
    except Exception as exc:
        local_existe = False
        try:
            local_existe = os.path.exists(_local_path(brain, sid))
        except Exception:
            pass
        avisos.append("no pude traer la conversación de «%s» del cerebro (%s): %s"
                      % (pestana, _motivo(exc),
                         "sigo con la de esta máquina." if local_existe
                         else "abro la pestaña sin ella."))
        _log({"accion": "traer", "estado": "error", "id": sid, "error": type(exc).__name__})
    try:
        s = _aviso_sonda(brain)
        if s:
            avisos.append(s)
    except Exception:
        pass
    return avisos


def _motivo(exc):
    txt = str(exc) if isinstance(exc, ValueError) else type(exc).__name__
    return txt[:80]


def _traer(brain, sid, pestana):
    # Solo la carpeta del socio resuelto en esta máquina: la conversación de
    # otra persona del mismo cerebro jamás se trae (copia_path → <socio>/).
    copia = copia_path(brain, sid)
    if not copia or not os.path.isfile(copia):
        return ""
    local = _local_path(brain, sid)
    with _candado_local(sid):
        if not os.path.exists(local):
            data, mtime = _leer_copia(copia)
            if data is None:
                return ""
            if not _parece_conversacion(data):
                raise ValueError("la copia no parece una conversación")
            _poner_local(local, data, mtime)
            _log({"accion": "traer", "estado": "restaurada", "id": sid})
            return ""
        # Choque: hay conversación aquí y en el cerebro.
        st = os.stat(local)
        with open(copia, "rb") as fh:
            cabecera = fh.read(10)
        if _mtime_gz(cabecera) <= st.st_mtime + 1:
            return ""                     # la de aquí es igual o más nueva: gana la local
        data, mtime = _leer_copia(copia)
        if data is None or not _parece_conversacion(data):
            raise ValueError("la copia no parece una conversación")
        with open(local, "rb") as fh:
            aqui = fh.read()
        if data == aqui or aqui.startswith(data):
            return ""                     # la del cerebro es el principio de la de aquí
        if not (data.startswith(aqui) or _mas_nueva(data, aqui, mtime, st.st_mtime)):
            return ""                     # la del cerebro es más vieja: gana la local
        bk = _ruta_respaldo(brain, sid, "antes-de-traer", ".jsonl")
        shutil.copy2(local, bk)
        _poner_local(local, data, mtime)
        _log({"accion": "traer", "estado": "reemplazada", "id": sid, "respaldo": bk})
        return ("traje la conversación de «%s» del cerebro (siguió en otra máquina); la "
                "de esta máquina quedó en %s" % (pestana, _humano(bk)))


def _poner_local(local, data, mtime):
    """Deja la conversación en la carpeta de sesiones de Claude Code de esta
    máquina, byte a byte (sin reescribir `cwd`: ver el docstring del módulo),
    con la hora de su origen."""
    _escribir(local, data)
    if mtime:
        try:
            os.utime(local, (mtime, mtime))
        except OSError:
            pass
