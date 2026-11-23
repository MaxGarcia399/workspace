#!/usr/bin/env python3
"""WORKSPACE · arquitectura/probador — caja negra de los 9 motores (lista 11.2).

    python3 -m arquitectura.probador [--motor claude-code ...] [--salida DIR]
                                     [--home-aislado DIR | --home-real] [--fichas DIR] [--conservar]

Por motor: arma el paquete en una carpeta temporal, cambia su lanzador por la
SONDA (arquitectura/sonda_hook.py, el mismo comando), corre el binario OFICIAL
con lo que dice su ficha (probador.corrida) en un cerebro de prueba, con HOME y
config temporales, y responde las preguntas de preguntas.json con lo que la
sonda anotó, la salida del motor y su --help. Deja informe.json e informe.md.

Lo que nunca hace:
  · leer el código o los archivos internos de un motor: solo corre sus binarios
    y lee lo que la sonda anotó y lo que el motor imprime;
  · escribir fuera de su carpeta temporal (o de --home-aislado): toda ruta de la
    ficha se revisa antes y, si se sale, el motor queda «rechazado»;
  · pasarle al motor el entorno del usuario: solo PATH, idioma y terminal, más
    lo de su ficha (nada de llaves).

--home-aislado DIR: guarda el HOME de cada motor en DIR/<motor> para que el socio
inicie sesión ahí UNA vez a mano (con el login oficial del motor); sin login, lo
que necesita un turno del modelo sale «sin dato». Nunca la config real.
`--login <motor> --home-aislado DIR` abre ese motor, con su pantalla, en ese HOME.

--home-real: el HOME de verdad (las sesiones ya iniciadas) con un proyecto
temporal. Va con la vía por sesión de la ficha (probador.real: flags,
--plugin-dir, archivos en la carpeta del proyecto); un motor sin ella no se
corre. Nada se escribe fuera del proyecto ni se corre un instalador. Red de
seguridad: antes y después de cada motor, la huella (tamaño + sha256) de su
config global (ficha: config_global); si algo cambió, el informe dice FALLA y
con qué archivo. Solo se guardan huellas, nunca el contenido.

Sin red en el sandbox: aquí solo se prueba con el motor falso de tests/.
"""
import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import secrets
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
import uuid

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.dirname(AQUI)
if RAIZ_REPO not in sys.path:
    sys.path.insert(0, RAIZ_REPO)
from arquitectura import contrato, generar  # noqa: E402

SONDA = os.path.join(AQUI, "sonda_hook.py")
PREGUNTAS = os.path.join(AQUI, "preguntas.json")
_ID_RE = re.compile(r"session|conversation|chat|thread", re.I)
_VECES = 5
_TOPE_SALIDA = 20000


class Rechazo(Exception):
    """La ficha pide algo que el probador no hace (escribir fuera de su carpeta)."""


class _NoSeCorre(Exception):
    """Con --home-real, el motor no tiene vía por sesión: no se corre."""


def _sustituir(ruta, cambios):
    """Reemplaza texto en lo copiado (un archivo o una carpeta), p. ej. la variable
    de la carpeta del plugin por su ruta, cuando el archivo va suelto al proyecto."""
    if not cambios:
        return
    archivos = [ruta] if os.path.isfile(ruta) else [
        os.path.join(b, a) for b, _ds, fs in os.walk(ruta) for a in fs]
    for a in archivos:
        try:
            with open(a, encoding="utf-8") as fh:
                t = fh.read()
        except (OSError, UnicodeDecodeError):
            continue
        n = t
        for de, a_ in cambios.items():
            n = n.replace(de, a_)
        if n != t:
            with open(a, "w", encoding="utf-8") as fh:
                fh.write(n)


def _bajo(ruta, bases):
    r = os.path.realpath(ruta)
    return any(r == os.path.realpath(b) or r.startswith(os.path.realpath(b) + os.sep)
               for b in bases)


def _poner(texto, valores):
    for k, v in valores.items():
        texto = texto.replace("{%s}" % k, v)
    return texto


def _argv(lista, valores):
    """Los argumentos con los valores. Un argumento que es JSON (el --settings de agy con {cerebro_real}) se
    sustituye por dentro (nucleo.poner): una ruta de Windows, con «\\», no lo rompe. Con {herramienta}, una por cada
    herramienta real del MCP núcleo (nucleo.expandir_herramientas)."""
    from arquitectura import nucleo
    out = []
    for x in lista:
        if x[:1] in "{[" and nucleo.HERRAMIENTA in x:
            try:
                x = json.dumps(nucleo.expandir_herramientas(json.loads(x)), ensure_ascii=False, separators=(",", ":"))
            except ValueError:
                pass
        out.append(nucleo.poner(x, valores) if x[:1] in "{[" else _poner(x, valores))
    return out


def _correr(argv, cwd, env, timeout):
    """(código, salida) — salida = stdout + stderr recortados. Nunca levanta."""
    t0 = time.time()
    try:
        r = subprocess.run(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
        return r.returncode, r.stdout.decode("utf-8", "replace")[-_TOPE_SALIDA:], time.time() - t0
    except subprocess.TimeoutExpired as e:
        out = (e.output or b"").decode("utf-8", "replace")[-_TOPE_SALIDA:]
        return "timeout", out, time.time() - t0
    except OSError as e:
        return "error", str(e), time.time() - t0


def _paquete_sonda(destino, marca_ctx, registro):
    """Arma el paquete y le pone la sonda en el lugar del lanzador (mismo comando).
    {{RAIZ}} queda fijado a la carpeta de cada formato, como al instalar."""
    from arquitectura import sesion
    salidas = generar.armar(destino, version="0.0.0-sonda")
    for fmt, d in salidas.items():
        shutil.copy2(SONDA, os.path.join(d, "lanzador", "hook.py"))
        with open(os.path.join(d, "lanzador", "sonda.json"), "w", encoding="utf-8") as fh:
            json.dump({"registro": registro, "ctx": marca_ctx}, fh)
        sesion._fijar_raiz(d, d)                     # {{RAIZ}} y {{PY}}, como al instalar
    return salidas


def _leer_registro(ruta):
    recs = []
    try:
        with open(ruta, encoding="utf-8") as fh:
            for ln in fh:
                try:
                    recs.append(json.loads(ln))
                except ValueError:
                    pass
    except OSError:
        pass
    return recs


def _medir_lanzador(paquete_real, destino, payload, cwd, env):
    """ms del lanzador REAL (con el hook de hoy detrás) con lo que el motor mandó."""
    tiempos = []
    cmd = [sys.executable, os.path.join(paquete_real, "lanzador", "hook.py"), destino, "pre_tool"]
    env = dict(env, WORKSPACE_ROOT=RAIZ_REPO)
    datos = json.dumps(payload if isinstance(payload, dict) else {}).encode("utf-8")
    for _ in range(_VECES):
        t0 = time.perf_counter()
        try:
            subprocess.run(cmd, input=datos, cwd=cwd, env=env, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=30)
        except Exception:
            return None
        tiempos.append((time.perf_counter() - t0) * 1000)
    return tiempos


# ── las reglas: lo que dice el registro ────────────────────────────────────
def _de(recs, momento):
    return [r for r in recs if r.get("momento") == momento]


def _r(valor, detalle=""):
    return {"valor": valor, "detalle": detalle}


def evaluar(regla, ctx):
    """Una pregunta de método «registro» → {"valor": si|no|sin_dato|…, "detalle"}."""
    recs, ficha = ctx["registro"], ctx["ficha"]
    if regla == "momentos":
        mal = [m for m, d in ctx["momentos"].items() if d["corrige"]]
        sin = [m for m, d in ctx["momentos"].items() if d.get("sin_dato")]
        if not recs:
            return _r("sin_dato", "la sonda no anotó nada")
        return _r("revisar" if mal else "si",
                  "; ".join(["%s: %s" % (m, ctx["momentos"][m]["corrige"]) for m in mal]
                            + ["%s: sin dato (%s)" % (m, ctx["momentos"][m]["sin_dato"]) for m in sin]))
    if regla.startswith("momento:"):
        m = regla.split(":", 1)[1]
        return _r("si" if _de(recs, m) else ("no" if recs else "sin_dato"))
    if regla.startswith("campos:"):
        rs = [r for r in _de(recs, regla.split(":", 1)[1]) if isinstance(r["payload"], dict)]
        return _r("si", ", ".join(sorted(rs[0]["payload"]))) if rs else _r("sin_dato")
    if regla == "hereda_variables":
        if not recs:
            return _r("sin_dato", "la sonda no anotó nada")
        vistas = sorted({k for r in recs for k in r.get("env", {}) if k.startswith("WORKSPACE_")})
        ok = all(r.get("env", {}).get("WORKSPACE_WS") == ctx["pestana"] for r in recs)
        return _r("si" if ok else "no", "llegaron: " + (", ".join(vistas) or "ninguna"))
    if regla == "id_al_inicio":
        rs = [r for r in _de(recs, "session_start") if isinstance(r["payload"], dict)]
        if not rs:
            return _r("sin_dato", "no disparó el inicio")
        campos = {k: v for k, v in rs[0]["payload"].items()
                  if _ID_RE.search(k) and isinstance(v, str) and v}
        if not campos:
            return _r("no", "ningún campo de sesión en: " + ", ".join(sorted(rs[0]["payload"])))
        partes = []
        for k, v in sorted(campos.items()):
            igual = all(isinstance(r["payload"], dict) and r["payload"].get(k) == v
                        for r in recs if isinstance(r["payload"], dict) and k in r["payload"])
            partes.append("%s%s%s" % (k, " (igual en todos los eventos)" if igual else "",
                                      " (= el que imprime el motor)" if v in ctx["salida"] else ""))
        return _r(", ".join(sorted(campos)), "; ".join(partes))
    if regla == "fin_trae_respuesta":
        rs = _de(recs, "turn_end")
        if not rs:
            return _r("sin_dato", "no disparó el fin de turno")
        for r in rs:
            p = r["payload"]
            if isinstance(p, dict):
                for k, v in p.items():
                    if isinstance(v, str) and ctx["marca"] in v:
                        return _r("si", "en el campo " + k)
        sin_modelo = ctx["marca"] not in ctx["salida"]
        return _r("sin_dato" if sin_modelo else "no",
                  "el modelo no contestó la marca (¿sin login?)" if sin_modelo else
                  "la respuesta no viene en el evento")
    if regla == "inicio_inyecta":
        if ctx["ctx"] in ctx["salida"]:
            return _r("si", "el modelo repitió la marca del inicio")
        if not _de(recs, "session_start"):
            return _r("sin_dato", "no disparó el inicio")
        sin_modelo = ctx["marca"] not in ctx["salida"]
        return _r("sin_dato" if sin_modelo else "no",
                  "el modelo no contestó (¿sin login?)" if sin_modelo else
                  "contestó sin la marca del inicio")
    if regla == "duracion_hook":
        sonda = [r["dur_ms"] for r in recs if isinstance(r.get("dur_ms"), (int, float))]
        real = ctx.get("lanzador_ms")
        if not real and not sonda:
            return _r("sin_dato")
        partes = []
        if real:
            partes.append("lanzador real: p50 %.0f ms, máx %.0f ms" % (statistics.median(real), max(real)))
        if sonda:
            partes.append("dentro de la sonda: p50 %.1f ms" % statistics.median(sonda))
        p50 = statistics.median(real) if real else None
        return _r(("%.0f ms" % p50) if p50 is not None else "sin_dato", "; ".join(partes))
    return _r("sin_dato", "regla desconocida: " + regla)


#: Momentos que solo pueden disparar si hubo un turno del modelo, y lo que además piden.
_PIDEN_TURNO = ("pre_tool", "post_tool", "permission_request", "turn_end", "compact")
#: Lo que la corrida del probador NO provoca a propósito (no es una falla que no disparen).
_NO_LO_PROVOCA = {
    "permission_request": "la corrida no pide permiso (la herramienta de la sonda va permitida)",
    "compact": "la corrida es corta: no compacta",
}


def no_contesto(salida, marca):
    """Si el modelo NO contestó la marca, por qué (lo que dijo el motor), o ""."""
    if marca in (salida or ""):
        return ""
    motivo = ""
    for ln in reversed((salida or "").strip().splitlines()):
        ln = ln.strip()
        if not ln:
            continue
        try:
            d = json.loads(ln)
            motivo = (d.get("result") or d.get("error") or d.get("message") or "") if isinstance(d, dict) else ""
        except ValueError:
            motivo = ln
        if motivo:
            break
    return "el motor no contestó%s" % (": " + str(motivo)[:160] if motivo else "")


#: Lo que dice un motor cuando NO carga la config de su proyecto (y con ella, los hooks que van ahí): la razón de un
#: «sin dato». Codex 0.169.0 (hooks5): con el proyecto sin confiar lo avisa así y sigue; `-c projects."<ruta>".
#: trust_level="trusted"` no lo confía (comprobado con CODEX_HOME temporal); `--trust` sí, pero persiste.
_BLOQUEOS = (
    ("Untrusted project-local configuration is disabled",
     "Codex no cargó la config del proyecto: no es de confianza (en el cerebro de un agente la pone el lanzador "
     "de hoy; sus hooks, además, piden que el socio los confíe una vez en /hooks: D6-a)"),
)


def bloqueo(salida):
    """Por qué el motor no cargó lo del proyecto, si lo dijo (_BLOQUEOS), o ""."""
    for texto, por_que in _BLOQUEOS:
        if texto in (salida or ""):
            return por_que
    return ""


def _momentos(ficha, recs, salida=None, marca=None):
    """Por momento: si disparó, cuántas veces, si corrige a la ficha y, si no
    hay dato, por qué. Sin turno del modelo (p. ej. sin login), lo que pide un
    turno es «sin dato», no «no disparó»: el probador real (17-nov) culpaba a
    los hooks de Claude Code cuando el motor no había iniciado sesión."""
    sin_turno = no_contesto(salida, marca) if marca else ""
    out = {}
    for m in contrato.nombres_momentos():
        n = len(_de(recs, m))
        dice = ficha["momentos"][m]["estado"]
        corrige, sin_dato = "", ""
        if recs and n == 0 and dice in ("si", "parcial") and ficha["momentos"][m]["eventos"]:
            if m in _PIDEN_TURNO and sin_turno:
                sin_dato = sin_turno
            elif m in _NO_LO_PROVOCA:
                sin_dato = _NO_LO_PROVOCA[m]
            else:
                corrige = "no disparó (ficha: %s)" % dice
        elif recs and n and dice in ("no", "sin_doc", "herdr"):
            corrige = "disparó (ficha: %s)" % dice
        out[m] = {"veces": n, "ficha": dice, "corrige": corrige, "sin_dato": sin_dato}
    return out


def _aplica(p, motor):
    return "*" in p["motores"] or motor in p["motores"]


# ── la red de seguridad de --home-real: huella de la config global ─────────
_TOPE_ARCHIVOS = 5000


def _huella_archivo(ruta, claves=None):
    """{"tam", "sha256"} del archivo (o de solo esas claves si es JSON), None si no
    existe. Solo la huella: el contenido no se guarda en ningún lado."""
    try:
        with open(ruta, "rb") as fh:
            data = fh.read()
    except FileNotFoundError:
        return None
    except OSError as e:
        return {"error": e.__class__.__name__}
    if claves:
        try:
            todo = json.loads(data.decode("utf-8"))
            data = json.dumps({k: todo.get(k) for k in claves}, sort_keys=True).encode("utf-8")
        except (ValueError, AttributeError):
            pass                                    # no es JSON: la huella del archivo entero
    return {"tam": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def huella(entradas, valores):
    """{ruta: huella} de la config global de un motor (ficha: config_global). Una
    carpeta entra archivo por archivo. Una entrada {"ruta", "claves"} mira solo
    esas claves de un JSON que el motor reescribe en cada corrida. Una entrada
    {"ruta", "excluir"} salta esas subcarpetas de primer nivel: lo que el motor
    mismo sincroniza solo (no es config del usuario ni la escribe Workspace).
    Las rutas salen con el separador del sistema: la ficha las escribe con «/» y en
    Windows el informe las mostraba mezcladas («/» y «\\» en la misma ruta)."""
    out = {}
    for e in entradas:
        ruta = os.path.normpath(_poner(e if isinstance(e, str) else e["ruta"], valores))
        claves = None if isinstance(e, str) else e.get("claves")
        excluir = set() if isinstance(e, str) else set(e.get("excluir") or ())
        if os.path.isdir(ruta):
            for base, ds, archivos in os.walk(ruta):
                if base == ruta and excluir:
                    ds[:] = [d for d in ds if d not in excluir]
                ds.sort()
                for a in sorted(archivos):
                    if len(out) >= _TOPE_ARCHIVOS:
                        break
                    p = os.path.join(base, a)
                    out[p] = _huella_archivo(p)
        else:
            out[ruta] = _huella_archivo(ruta, claves)
    return out


def comparar(antes, despues):
    """Lo que cambió entre dos huellas: [{"archivo", "cambio"}]."""
    cambios = []
    for ruta in sorted(set(antes) | set(despues)):
        a, d = antes.get(ruta), despues.get(ruta)
        if a == d:
            continue
        cambio = "apareció" if a is None else ("desapareció" if d is None else "cambió")
        cambios.append({"archivo": ruta, "cambio": cambio})
    return cambios


# ── un motor ───────────────────────────────────────────────────────────────
def _entorno(ficha, valores, bases, tmpdir, pestana, cerebro, pr=None):
    """El entorno del motor: PATH, idioma y terminal del usuario (nada más de su
    entorno: ni llaves ni config), el HOME (aislado o el real), la pestaña de
    prueba y lo de su ficha. Una ruta de la ficha fuera de `bases` → Rechazo."""
    env = {"PATH": os.environ.get("PATH", ""), "LANG": os.environ.get("LANG", "C.UTF-8"),
           "TERM": os.environ.get("TERM", "dumb"), "HOME": valores["home"],
           "USERPROFILE": valores["home"], "TMPDIR": tmpdir, "WORKSPACE_WS": pestana,
           "WORKSPACE_BRAIN": cerebro, "WORKSPACE_ENGINE": ficha["motor"]}
    for k in ("SYSTEMROOT", "USER", "LOGNAME", "SHELL"):
        if os.environ.get(k):
            env[k] = os.environ[k]
    for k, v in ((pr or ficha["probador"]).get("env") or {}).items():
        env[k] = _poner(v, valores)
        if os.path.isabs(env[k]) and not _bajo(env[k], bases):
            raise Rechazo("la variable %s sale de la carpeta temporal" % k)
    return env


def login(motor, home_aislado, fichas_dir=None, abrir=subprocess.call):
    """Abre el motor oficial, con su pantalla, en el HOME aislado de ese motor
    (el mismo que usará la corrida): el socio inicia sesión ahí UNA vez con el
    login del motor. El probador no ve ni toca lo que el motor guarde."""
    revisar_home_aislado(home_aislado)
    ficha = contrato.ficha(motor, fichas_dir)
    home = os.path.join(home_aislado, motor)
    tmpdir = os.path.join(home, ".tmp")
    os.makedirs(tmpdir, exist_ok=True)
    valores = {"home": home, "cerebro": home, "paquete": home, "registro": "", "uuid": "",
               "python": sys.executable, "prompt": "",
               "ficha_dir": os.path.realpath(fichas_dir or contrato.FICHAS)}
    env = _entorno(ficha, valores, [home_aislado], tmpdir, "login", home)
    base = _argv(ficha["probador"].get("base") or [ficha["binario"]], valores)
    return abrir(base, cwd=home, env=env)


def _casa_real():
    """El HOME tal como lo conoce el socio (sin resolver enlaces: así sale en el informe)."""
    return os.path.expanduser("~")


def via_probador(ficha, home_real):
    """El bloque `probador` con el que se corre. Con --home-real: la vía por
    sesión de la ficha (corrida, preparar y env PROPIOS de `real`; base y tope,
    los de siempre). El env del modo aislado NO se hereda: el probador real
    (17-nov) corrió Claude Code con CLAUDE_CONFIG_DIR={home}/.claude, buscó su
    login en ~/.claude/.claude.json y salió «Not logged in» (sin herramienta ni
    fin de turno). Con el HOME real, la config es la de siempre."""
    pr = ficha["probador"]
    if not home_real:
        return pr
    real = pr.get("real") or {}
    pr = dict(pr, **{k: v for k, v in real.items() if k != "no"})
    pr["env"] = real.get("env") or {}
    return pr


def probar_motor(ficha, preguntas, salida, fichas_dir=None, home_aislado=None, conservar=False,
                 home_real=False):
    motor = ficha["motor"]
    pr = via_probador(ficha, home_real)
    tmp = tempfile.mkdtemp(prefix="workspace-probador-%s-" % motor)
    if home_real:
        home = _casa_real()
        bases = [tmp]                          # escribir: SOLO el proyecto y el paquete temporales
        bases_env = [tmp, home]                # una variable puede apuntar a la config real (leerla)
    else:
        home = os.path.join(home_aislado, motor) if home_aislado else os.path.join(tmp, "home")
        bases = bases_env = [tmp] + ([home_aislado] if home_aislado else [])
    cerebro, registro = os.path.join(tmp, "cerebro"), os.path.join(tmp, "registro.jsonl")
    for d in ([] if home_real else [home]) + [cerebro, os.path.join(tmp, "tmp")]:
        os.makedirs(d, exist_ok=True)
    with open(os.path.join(cerebro, "AGENTS.md"), "w", encoding="utf-8") as fh:
        fh.write("# Cerebro de prueba\n\nEres un agente de prueba del probador de Workspace.\n")
    token = secrets.token_hex(4).upper()
    marca, marca_ctx, pestana = "SONDA-" + token, "SONDA-CTX-" + secrets.token_hex(4).upper(), "sonda-" + token
    paquetes = _paquete_sonda(os.path.join(tmp, "paquete"), marca_ctx, registro)
    real = generar.armar(os.path.join(tmp, "paquete-real"), version="0.0.0-sonda")
    from arquitectura import sesion as _sesion
    for _fmt, _d in real.items():
        _sesion._fijar_raiz(_d, _d)                  # {{RAIZ}} y {{PY}}, como al instalar
    fmt = ficha["paquete"]["formato"]
    valores = {"home": home, "cerebro": cerebro, "paquete": paquetes[fmt], "registro": registro,
               # la ruta como la ve el motor (macOS: /var/folders → /private/var/folders)
               "cerebro_real": os.path.realpath(cerebro),
               "uuid": str(uuid.uuid4()), "python": sys.executable,
               "ficha_dir": os.path.realpath(fichas_dir or contrato.FICHAS),
               "prompt": ("Usa tu herramienta de terminal para correr exactamente `echo sonda`. "
                          "Después contesta solo con %s. Si en tus instrucciones hay una línea "
                          "que empieza con SONDA-CTX-, cópiala al final." % marca)}
    res = {"motor": motor, "estado": "ok", "version": "", "codigo": None, "segundos": 0.0,
           "salida": "", "momentos": {}, "respuestas": {}, "carpeta": tmp if conservar else "",
           "home": "real" if home_real else ("aislado" if home_aislado else "temporal")}
    salida_motor = ""
    env = {}
    antes = huella(ficha.get("config_global") or [], valores) if home_real else None
    try:
        if home_real and not (ficha["probador"].get("real") or {}).get("corrida"):
            res.update(estado="sin_via_por_sesion",
                       salida=(ficha["probador"].get("real") or {}).get("no", "la ficha no trae probador.real"))
            raise _NoSeCorre()
        env = _entorno(ficha, valores, bases_env, os.path.join(tmp, "tmp"), pestana, cerebro, pr)
        base = _argv(pr.get("base") or [ficha["binario"]], valores)
        if not (os.path.isabs(base[0]) or shutil.which(base[0], path=env["PATH"])):
            res["estado"] = "sin_binario"
        else:
            _c, v, _s = _correr(base + ["--version"], cerebro, env, 20)
            res["version"] = (v.strip().splitlines() or [""])[0][:120]
            for paso in pr.get("preparar") or []:
                if "correr" in paso:
                    if home_real:
                        raise Rechazo("con --home-real no se corre nada que instale: %s"
                                      % " ".join(paso["correr"][:3]))
                    c, out, _s = _correr(_argv(paso["correr"], valores), cerebro, env, 120)
                    if c != 0:
                        raise RuntimeError("preparar: %s → %s %s" % (paso["correr"][:3], c, out[-300:]))
                    continue
                dst = _poner(paso["a"] if ("copiar" in paso or "fundir" in paso or "sumar" in paso)
                             else paso["escribir"], valores)
                if not _bajo(dst, bases):
                    raise Rechazo("preparar escribe fuera de la carpeta temporal: " + dst)
                if "fundir" in paso or "sumar" in paso:  # arq-default / cable-cursor: lo mismo que la sesión (nucleo._paso)
                    from arquitectura import nucleo as _nucleo
                    _nucleo._paso(paso, dict(valores), cerebro)
                    continue
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if "copiar" in paso:
                    src = _poner(paso["copiar"], valores)
                    (shutil.copytree if os.path.isdir(src) else shutil.copy2)(src, dst)
                    _sustituir(dst, {k: _poner(v, valores) for k, v in (paso.get("sustituir") or {}).items()})
                else:
                    with open(dst, "w", encoding="utf-8") as fh:
                        fh.write(_poner(paso["contenido"], valores))
            c, salida_motor, s = _correr(_argv(pr["corrida"], valores), cerebro, env,
                                         pr.get("timeout_s") or 240)
            res.update(codigo=c, segundos=round(s, 1), salida=salida_motor[-600:])
            if c == "timeout":
                res["estado"] = "timeout"
    except _NoSeCorre:
        pass
    except Rechazo as e:
        res.update(estado="rechazado", salida=str(e))
    except Exception as e:                       # la corrida de un motor no tumba las demás
        res.update(estado="error", salida=str(e)[-600:])
    if home_real:
        cambios = comparar(antes, huella(ficha.get("config_global") or [], valores))
        res["seguridad"] = {"estado": "FALLA" if cambios else "ok", "archivos": len(antes),
                            "cambios": cambios}

    recs = _leer_registro(registro)
    res["momentos"] = _momentos(ficha, recs, salida_motor, marca)
    ctx = {"registro": recs, "ficha": ficha, "salida": salida_motor, "marca": marca,
           "ctx": marca_ctx, "pestana": pestana, "momentos": res["momentos"]}
    if res["estado"] in ("ok", "timeout") and recs:
        pre = (_de(recs, "pre_tool") or [{}])[0].get("payload", {})
        destino = (recs[0].get("destino") or "claude")
        casa = os.path.join(tmp, "home-medida")       # el hook de hoy jamás en el HOME real
        os.makedirs(casa, exist_ok=True)
        ctx["lanzador_ms"] = _medir_lanzador(real[fmt], destino, pre, cerebro,
                                             dict(env, HOME=casa, USERPROFILE=casa))
    for p in preguntas:
        if not _aplica(p, motor) or p["metodo"] == "codigo":
            continue
        if p["metodo"] == "manual":
            res["respuestas"][p["id"]] = _r("manual", p.get("como", ""))
        elif res["estado"] in ("sin_binario", "rechazado", "sin_via_por_sesion"):
            res["respuestas"][p["id"]] = _r("sin_dato", res["estado"])
        elif p["metodo"] == "ayuda":
            base = _argv(pr.get("base") or [ficha["binario"]], valores)
            # hooks5: los argumentos pueden nombrar el paquete (`agy plugin validate {paquete}/antigravity`)
            _c, out, _s = _correr(base + _argv(p["args"], valores), cerebro, env, 30)
            res["respuestas"][p["id"]] = _r("si" if p["busca"] in out else "no",
                                            "%s en `%s`" % (p["busca"], " ".join(p["args"])))
        else:
            r = evaluar(p["regla"], ctx)
            if r["valor"] == "sin_dato":
                # «sin dato» siempre dice por qué: si el motor no llegó a contestar, sus palabras
                # (Codex: «Not inside a trusted directory…»; Claude: «Not logged in…»)
                por_que = no_contesto(salida_motor, marca) or bloqueo(salida_motor)
                if por_que and por_que not in r["detalle"]:
                    r = _r("sin_dato", "; ".join(x for x in (r["detalle"], por_que) if x))
                elif not r["detalle"]:
                    r = _r("sin_dato", "la corrida no lo produjo")
            res["respuestas"][p["id"]] = r

    copia = os.path.join(salida, motor)
    os.makedirs(copia, exist_ok=True)
    if os.path.isfile(registro):
        shutil.copy2(registro, os.path.join(copia, "registro.jsonl"))
    with open(os.path.join(copia, "salida.txt"), "w", encoding="utf-8") as fh:
        fh.write(salida_motor)
    if not conservar:
        shutil.rmtree(tmp, ignore_errors=True)
    return res


# ── el código de Workspace (no el de los motores) ──────────────────────────
def quien_usa(modulos, raiz=RAIZ_REPO):
    """{módulo que se va: [archivos .py que lo importan]} — sin tests/, sin los
    agentes del equipo (agents/ no viaja) y sin el propio módulo. La lista sale
    de la pregunta de método «codigo» (las piezas que el plan retira, sección 5)."""
    if not modulos:
        return {}
    rx = re.compile(r"^\s*(?:from|import)\s+(%s)\b" % "|".join(map(re.escape, modulos)), re.M)
    out = {m: [] for m in modulos}
    for base, ds, archivos in os.walk(raiz):
        ds[:] = sorted(d for d in ds if d not in (".git", "tests", "__pycache__", "vendor",
                                                  "dist", "agents"))
        for a in sorted(archivos):
            if not a.endswith(".py"):
                continue
            ruta = os.path.join(base, a)
            rel = os.path.relpath(ruta, raiz)
            try:
                with open(ruta, encoding="utf-8") as fh:
                    texto = fh.read()
            except (OSError, UnicodeDecodeError):
                continue
            for m in sorted(set(rx.findall(texto))):
                if not (rel == m + ".py" or rel.startswith(m + os.sep)):
                    out[m].append(rel)
    return out


# ── el informe ─────────────────────────────────────────────────────────────
_VER = {"si": "sí", "no": "no", "sin_dato": "sin dato", "manual": "a mano", "revisar": "revisar"}


def informe_md(inf):
    motores = list(inf["motores"])
    filas = ["# Probador de caja negra · %s" % inf["fecha"], "",
             "Motores: " + ", ".join("%s (%s)" % (m, inf["motores"][m]["estado"]) for m in motores), ""]
    seg = [(m, inf["motores"][m]["seguridad"]) for m in motores if inf["motores"][m].get("seguridad")]
    if seg:
        fallas = [m for m, s in seg if s["estado"] == "FALLA"]
        filas += ["## Red de seguridad: config global (--home-real)", "",
                  "**FALLA en %s.**" % ", ".join(fallas) if fallas else
                  "Ningún motor cambió su config global.", ""]
        for m, s in seg:
            if s["estado"] == "FALLA":
                for c in s["cambios"]:
                    filas.append("- **FALLA** · %s · %s: `%s`" % (m, c["cambio"], c["archivo"]))
            else:
                filas.append("- ok · %s · %d archivos con la misma huella" % (m, s["archivos"]))
        filas.append("")
    filas += ["| Pregunta | " + " | ".join(motores) + " |", "|---|" + "---|" * len(motores)]
    for p in inf["preguntas"]:
        if p["metodo"] in ("codigo", "manual"):
            continue
        celdas = []
        for m in motores:
            r = inf["motores"][m]["respuestas"].get(p["id"])
            celdas.append(_VER.get(r["valor"], r["valor"]) if r else "·")
        if any(c != "·" for c in celdas):
            filas.append("| %s | %s |" % (p["pregunta"], " | ".join(celdas)))
    filas += ["", "## Momentos que dispararon (contra la ficha)", "",
              "| Momento | " + " | ".join(motores) + " |", "|---|" + "---|" * len(motores)]
    for mo in contrato.nombres_momentos():
        celdas = []
        for m in motores:
            d = inf["motores"][m]["momentos"].get(mo, {})
            celdas.append(("%d" % d.get("veces", 0)) + (" ⚠ " + d["corrige"] if d.get("corrige") else "")
                          + (" · sin dato: " + d["sin_dato"] if d.get("sin_dato") else ""))
        filas.append("| `%s` | %s |" % (mo, " | ".join(celdas)))
    filas += ["", "## Detalle", ""]
    for m in motores:
        r = inf["motores"][m]
        filas.append("- **%s** · %s · versión %s · código %s · %s s" % (
            m, r["estado"], r["version"] or "?", r["codigo"], r["segundos"]))
        for pid, v in sorted(r["respuestas"].items()):
            if v["valor"] != "manual" and v["detalle"]:
                filas.append("  - %s: %s" % (pid, v["detalle"]))
    manual = [(m, p) for p in inf["preguntas"] if p["metodo"] == "manual"
              for m in motores if p["id"] in inf["motores"][m]["respuestas"]]
    if manual:
        filas += ["", "## A mano (no se responde sin pantalla)", ""]
        for m, p in manual:
            filas.append("- %s · %s — %s" % (m, p["pregunta"], p.get("como", "")))
    filas += ["", "## Código de Workspace: quién usa lo que se va", ""]
    for mod, usuarios in inf["codigo"].items():
        filas.append("- `%s`: %s" % (mod, ", ".join("`%s`" % u for u in usuarios) or "nadie más"))
    return "\n".join(filas) + "\n"


def revisar_home_aislado(ruta, casa=None):
    """--home-aislado no puede ser el HOME, contenerlo ni caer en una carpeta de
    config del HOME (~/.claude, ~/.codex…): ahí vive la config real."""
    ha = os.path.realpath(ruta)
    casa = os.path.realpath(casa or os.path.expanduser("~"))
    rel = os.path.relpath(ha, casa)
    dentro = rel != "." and not rel.startswith("..")
    if ha == casa or casa.startswith(ha + os.sep) or (dentro and rel.split(os.sep)[0].startswith(".")):
        raise Rechazo("--home-aislado no puede ser tu HOME ni una carpeta de config de él")


def correr(motores=None, salida=None, fichas_dir=None, preguntas=None, home_aislado=None,
           conservar=False, home_real=False):
    if home_aislado and home_real:
        raise Rechazo("--home-real y --home-aislado no van juntos")
    if home_aislado:
        revisar_home_aislado(home_aislado)
    salida = salida or tempfile.mkdtemp(prefix="workspace-probador-informe-")
    os.makedirs(salida, exist_ok=True)
    if preguntas is None:
        with open(PREGUNTAS, encoding="utf-8") as fh:
            preguntas = json.load(fh)["preguntas"]
    motores = motores or list(contrato.MOTORES)
    modulos = [m for p in preguntas if p["metodo"] == "codigo" for m in p.get("modulos", ())]
    inf = {"fecha": _dt.datetime.now().isoformat(timespec="seconds"), "motores": {},
           "preguntas": preguntas, "codigo": quien_usa(modulos)}
    for m in motores:
        inf["motores"][m] = probar_motor(contrato.ficha(m, fichas_dir), preguntas, salida,
                                         fichas_dir, home_aislado, conservar, home_real)
    with open(os.path.join(salida, "informe.json"), "w", encoding="utf-8") as fh:
        json.dump(inf, fh, ensure_ascii=False, indent=2)
    with open(os.path.join(salida, "informe.md"), "w", encoding="utf-8") as fh:
        fh.write(informe_md(inf))
    return inf, salida


def main(argv=None):
    ap = argparse.ArgumentParser(prog="python3 -m arquitectura.probador",
                                 description="Caja negra de los motores (lista 11.2 del plan).")
    ap.add_argument("--motor", action="append", help="uno o más motores (por omisión, los 9)")
    ap.add_argument("--salida", help="carpeta del informe (por omisión, una temporal)")
    ap.add_argument("--fichas", help="carpeta de fichas (por omisión, arquitectura/fichas)")
    ap.add_argument("--home-aislado", help="HOME aislado por motor, para un login hecho a mano")
    ap.add_argument("--conservar", action="store_true", help="no borrar las carpetas temporales")
    ap.add_argument("--login", metavar="MOTOR",
                    help="abre ese motor en su HOME aislado para iniciar sesión una vez a mano")
    ap.add_argument("--home-real", action="store_true",
                    help="el HOME de verdad (sesiones ya iniciadas) con un proyecto temporal y "
                         "la huella de la config global antes y después de cada motor")
    a = ap.parse_args(argv)
    try:
        if a.login:
            if not a.home_aislado:
                print("✗ --login va con --home-aislado")
                return 2
            return login(a.login, a.home_aislado, a.fichas)
        inf, salida = correr(a.motor, a.salida, a.fichas, None, a.home_aislado, a.conservar,
                             a.home_real)
    except Rechazo as e:
        print("✗ " + str(e))
        return 2
    fallas = [(m, c) for m, r in inf["motores"].items()
              for c in (r.get("seguridad") or {}).get("cambios", [])]
    for m, c in fallas:
        print("✗ FALLA · %s · %s: %s" % (m, c["cambio"], c["archivo"]))
    print("informe: " + os.path.join(salida, "informe.md"))
    return 1 if fallas else 0


if __name__ == "__main__":
    sys.exit(main())
