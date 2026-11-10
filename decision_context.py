#!/usr/bin/env python3
"""WORKSPACE · decision_context — el CONTEXTO que lleva una pregunta de Decisores → Preguntar.

Cinco niveles, de menos a más (los hooks NO usan esto: siguen con su contexto
mínimo de siempre):
  nada      solo la pregunta
  pestana   el resumen guardado de la pestaña más reciente del agente (el de
            fábrica, igual que antes)
  sesiones  los resúmenes de las pestañas que el socio elija
  memoria   la memoria curada del agente: STATE/MEMORY.md, STATE/INDEX.md y su
            memoria de Claude Code (motores/claude-code/memoria/<socio>/)
  cerebro   TODO el cerebro si cabe en el presupuesto; si no (lo normal), lo
            MÁS RELEVANTE para la pregunta y sus opciones; si casi nada
            coincide (o aún no hay pregunta), LO MÁS RECIENTE: la memoria y
            los índices primero y luego las notas y sesiones más nuevas.
            Siempre llena el presupuesto; el medidor, `v` y lo que se manda
            salen de la MISMA cuenta y dicen qué selección fue.

Presupuesto (tokens de CONTEXTO) = límite del decisor (META `context_tokens`,
MEDIDO; el ajuste `decisions.model_limits` solo puede bajarlo) − su
sobrecarga fija por llamada (META `overhead_tokens`) − pregunta y opciones −
un colchón de max(1000, 10 % del límite); y nunca más que
`decisions.context_budget` si es > 0.

Tokens POR CONTENIDO, no un cociente global: un pre-tokenizador como el de
los modelos (Qwen2 / Llama 3) corta el texto en piezas y cada clase pesa lo
suyo — una palabra de ≤ 6 letras (con su espacio) es 1 token y las largas,
1 por cada 4.5 letras; cada DÍGITO, 1; cada racha de puntuación, 1 por cada
1.5 signos; cada salto de línea o espacio suelto, 1; letras de otras
escrituras más caras (CJK/hangul: 1 por carácter). Medido con Jev
(2026-11-07) en textos sintéticos: prosa 4.16 caracteres/token, tabla
numérica 1.25, dígitos 1.00, markdown 2.62 — el modelo queda a ±1.5 % de
cada uno. Encima, un FACTOR por decisor se calibra solo (promedio móvil)
con lo que el decisor de verdad contó (`usage.input_tokens`); vive en
`<estado>/decisions_calibration.json`, no en los ajustes.

Si aun así no cabe, ask() RECORTA el contexto a 0.6× y luego 0.4× y 0.25× del
primer intento (vuelve a rankear y a llenar; hasta 3 reintentos), usando
también lo que el «no cupo» demuestra; ese tope solo vale para esa pregunta
(no ensucia la cuenta de los demás cerebros). Se anota una sola vez.

Privacidad (todo, en cada nivel):
  · secretos: cada fragmento pasa por decisions.redact (secret_scan); sin el
    detector, el contexto va VACÍO;
  · fuera: binarios, carpetas de trabajo (.git, .obsidian, .claude, tmp,
    scratch, caché…), conversaciones crudas (motores/*/conversaciones, la
    maleta), archivos de llaves (.env, *.key, *.pem…), lo muy grande;
  · PRIVADO (convención nueva, no había una): un .md con `privado: true` (o
    private / confidencial / confidential) en su frontmatter, o dentro de una
    carpeta `privado/` (o `private/`), jamás se envía.

Relevancia: SQLite FTS5 en memoria (bm25, el mismo tokenizador que
memory_index) sobre trozos de los archivos, con un empujón a lo que el índice
de memoria del cerebro (memory_index, si existe) ya rankea alto; sin FTS5,
un ranker de palabras (idf). Solo lee. Stdlib. Falla-suave.

Cerebro grande (un cerebro real pesa ~8 MB): todo lo caro se hace UNA vez por
archivo y se guarda en memoria con su firma (ruta + tamaño + fecha): el texto
ya sin secretos, sus trozos y los tokens de cada trozo; el índice FTS5 se arma
una vez por escaneo y se reusa. Una pregunta nueva solo vuelve a rankear (no
redacta ni tokeniza). El armado en frío cede el GIL entre archivos y se
detiene un poco mientras el socio teclea (typing()).
"""
import collections
import json
import math
import os
import re
import stat
import sys
import threading
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

LEVELS = ("nada", "pestana", "sesiones", "memoria", "cerebro")
DEFAULT_LEVEL = "pestana"
#: Niveles que mandan contenido del cerebro (aviso la primera vez con un
#: decisor en la nube).
BRAIN_LEVELS = ("memoria", "cerebro")
#: El pre-tokenizador (como el de Qwen2 / Llama 3; sin \p, letras = [^\W\d_]).
_PIECE = re.compile(r"(?i:'s|'t|'re|'ve|'m|'ll|'d)|[^\r\n\w]?[^\W\d_]+|\d"
                    r"| ?[^\s\w]+[\r\n]*|\s*[\r\n]+|\s+(?!\S)|\s+|_+")
#: Pesos medidos con Jev (ver arriba): palabra corta = 1 token; larga, 1 cada
#: WORD_CHARS letras; puntuación, 1 cada PUNCT_CHARS signos.
WORD_SHORT = 6
WORD_CHARS = 4.5
PUNCT_CHARS = 1.5
#: Factor de corrección por decisor (calibrado): rango sano y peso de cada
#: muestra nueva en el promedio móvil.
FACTOR_RANGE = (0.5, 2.0)
FACTOR_ALPHA = 0.3
#: Solo calibran las llamadas con contexto grande (en una chica la
#: sobrecarga fija domina y la cuenta sale torcida).
CALIBRATE_MIN_TOKENS = 1500
#: Colchón del presupuesto: max(estos tokens, esta fracción del límite).
SAFETY_TOKENS = 1000
SAFETY_FRACTION = 0.10
#: Si el decisor dice que no cupo: cada reintento manda a lo más esta
#: fracción del PRIMER intento (y lo que el «no cupo» demuestra).
SHRINK_STEPS = (0.6, 0.4, 0.25)
#: «lo más relevante» si lo que coincide con la pregunta es al menos esto de
#: lo que se manda; si no, «lo más reciente».
RELEVANT_SHARE = 0.5
TEXT_EXT = (".md", ".txt")
MAX_FILE_BYTES = 256 * 1024
CHUNK_CHARS = 1600
TAB_SUMMARY_CHARS = 4000
#: Carpetas que NUNCA se leen (por nombre, en cualquier nivel del cerebro).
SKIP_DIRS = frozenset((".git", ".obsidian", ".trash", ".claude", ".cursor", ".kiro",
                       ".agents", ".codex", ".gemini", ".github", "node_modules",
                       "__pycache__", ".venv", "venv", "tmp", "temp", ".tmp", "scratch",
                       ".cache", "cache", "_shelved"))
#: Carpetas privadas (convención): su contenido no sale.
PRIVATE_DIRS = frozenset(("privado", "private", "_privado", "_private"))
#: Conversaciones y registros: no son conocimiento curado y llevan palabras de
#: otras personas — las conversaciones crudas de los motores, la maleta, los
#: chats (mensajes directos y el canal del equipo), el bus de mensajes entre
#: agentes (msgs/), las salas de Conversaciones (conversaciones/: texto de otros
#: agentes, no confiable) y el archivo frío de bitácoras. Se cuentan en «excluidos».
_SKIP_REL = re.compile(r"^(motores/[^/]+/conversaciones/|STATE/sessions/[^/]+/maleta/|chats/|msgs/"
                       r"|conversaciones/"
                       r"|STATE/log-archive/)", re.I)
#: Nombres que delatan llaves o credenciales (también en español: claves,
#: llaves, contraseñas, credenciales, secretos — con cualquier extensión).
_SECRET_NAME = re.compile(r"(^\.env|secret|credential|credencial|password|passwd|contrase[nñ]a"
                          r"|apikey|api[_-]key|\.pem$|\.key$|\.p12$|^id_rsa|^id_ed25519"
                          r"|(?:^|[^a-záéíóúñ])(?:claves?|llaves?)(?:[^a-záéíóúñ]|$))", re.I)
PRIVATE_KEYS = ("privado", "privada", "private", "confidencial", "confidential")
#: El frontmatter, aunque haya renglones en blanco (o un BOM) antes.
_FM = re.compile(r"^\ufeff?\s*---[ \t]*\r?\n(.*?)\r?\n---[ \t]*(\r?\n|$)", re.S)
_TRUE = ("true", "sí", "si", "yes", "1", "on", "y", "verdadero")
_TAG_KEYS = ("tags", "tag", "etiquetas")
_ITEM = re.compile(r"^\s*-\s*(.*)$")


# ── cuentas ──────────────────────────────────────────────────────────────────
def _meta(decider_id):
    try:
        import decisions as D
        return D.meta(decider_id) or {}
    except Exception:
        return {}


def _letters_cost(w):
    """Tokens de las letras de UNA palabra (sin su carácter previo)."""
    if w.isascii():
        k = len(w)
        return 1 if k <= WORD_SHORT else int(math.ceil(k / WORD_CHARS))
    lat = wide = other = 0
    for ch in w:
        o = ord(ch)
        if o < 0x0250 or 0x1E00 <= o <= 0x1EFF:      # latinas (con acentos, ñ, ü…)
            lat += 1
        elif o >= 0x2E80:                            # CJK, kana, hangul: ~1 por carácter
            wide += 1
        else:                                        # griego, cirílico, árabe, devanagari…
            other += 1
    n = wide + int(math.ceil(other / 2.0))
    if lat:
        n += 1 if lat <= WORD_SHORT else int(math.ceil(lat / WORD_CHARS))
    return max(1, n)


def raw_tokens(text):
    """Tokens estimados POR CONTENIDO (sin el factor del decisor)."""
    if not text:
        return 0
    n = 0
    for p in _PIECE.findall(text):
        if p.isdigit():
            n += 1
        elif p[-1].isalpha():
            n += _letters_cost(p if p[0].isalpha() else p[1:])
        elif p.isspace():
            n += 1
        else:
            n += max(1, int(math.ceil(len(p.strip()) / PUNCT_CHARS)))
    return n


def _cal_path():
    import paths
    return os.path.join(paths.state_dir(), "decisions_calibration.json")


def _cal_read():
    try:
        with open(_cal_path(), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _sane(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if FACTOR_RANGE[0] <= v <= FACTOR_RANGE[1] else None


def base_factor(decider_id):
    """El factor de fábrica del decisor (META `token_factor`) o 1.0."""
    return _sane(_meta(decider_id).get("token_factor")) or 1.0


def token_factor(decider_id=None):
    """Factor de corrección con que se cuenta para este decisor: el
    calibrado si lo hay; si no, el de fábrica."""
    if not decider_id:
        return 1.0
    e = _cal_read().get(decider_id)
    return _sane((e or {}).get("factor") if isinstance(e, dict) else None) or \
        base_factor(decider_id)


def overhead(decider_id):
    """Tokens fijos que gasta el decisor en cada llamada (META `overhead_tokens`)."""
    try:
        return max(0, int(_meta(decider_id).get("overhead_tokens") or 0))
    except (TypeError, ValueError):
        return 0


def tokens(text, decider_id=None, factor=None):
    """Tokens de un texto para este decisor: por contenido × su factor."""
    raw = raw_tokens(text)
    if not raw:
        return 0
    f = factor if factor else token_factor(decider_id)
    return int(math.ceil(raw * f))


def calibrate(decider_id, raw_sent, input_tokens):
    """Tras una llamada que SALIÓ: mueve el factor del decisor hacia lo que de
    verdad contó ((tokens de entrada − sobrecarga) ÷ tokens estimados de lo
    que se mandó). Solo con contexto grande. → el factor nuevo o None."""
    try:
        raw_sent, used = int(raw_sent or 0), int(input_tokens or 0)
    except (TypeError, ValueError):
        return None
    if not decider_id or raw_sent < CALIBRATE_MIN_TOKENS:
        return None
    net = used - overhead(decider_id)
    if net <= 0:
        return None
    sample = _sane(net / float(raw_sent))
    if sample is None:
        return None
    hecho = {}

    def mover(data):
        # bajo el candado (decisions._actualizar_estado): dos decisores que
        # calibran a la vez no se borran el factor (Greptile 0.8.x, 6)
        e = data.get(decider_id) if isinstance(data.get(decider_id), dict) else {}
        old = _sane(e.get("factor")) or base_factor(decider_id)
        hecho["new"] = new = old + FACTOR_ALPHA * (sample - old)
        data[decider_id] = {"factor": round(new, 4), "n": int(e.get("n") or 0) + 1,
                            "last": round(sample, 4), "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
        return data
    import decisions
    decisions._actualizar_estado(_cal_path(), mover)
    return hecho.get("new")


def proven_factor(decider_id, raw_sent):
    """Un «no cupo» con `raw_sent` tokens estimados demuestra que el factor
    real es MAYOR que (límite real − sobrecarga) ÷ raw_sent. Solo para los
    reintentos de esa pregunta (no se guarda)."""
    try:
        real = int(_meta(decider_id).get("context_tokens") or 0)
    except (TypeError, ValueError):
        real = 0
    lim = (real or limit(decider_id)) - overhead(decider_id)
    if raw_sent <= 0 or lim <= 0:
        return None
    return lim / float(raw_sent)


def cost_usd(n_tokens, decider_id):
    """Costo de ENTRADA estimado (la salida de Jev es gratis); None si el
    decisor no declara precio; 0.0 si es local."""
    m = _meta(decider_id)
    if m.get("local"):
        return 0.0
    price = m.get("price_in_per_m")
    if price is None:
        return None
    return float(n_tokens) / 1_000_000.0 * float(price)


def fmt_tokens(n):
    """≈850 · ≈1.2k · ≈28k."""
    n = int(n or 0)
    if n < 1000:
        return "%d" % n
    if n < 10000:
        return "%.1fk" % (n / 1000.0)
    return "%dk" % int(round(n / 1000.0))


def fmt_limit(n):
    """Un LÍMITE, redondeado hacia abajo (lo que de verdad cabe): 32 768 → 32k."""
    n = int(n or 0)
    if n < 1000:
        return "%d" % n
    if n < 10000:
        return ("%.1fk" % (int(n / 100) / 10.0)).replace(".0k", "k")
    return "%dk" % (n // 1000)


def fmt_exact(n):
    """32 768 (con espacio de miles)."""
    return "{:,}".format(int(n or 0)).replace(",", " ")


def fmt_cost(c):
    """$0.0012 · $0.000014 (los centavos de centavo también se ven)."""
    if c is None:
        return "$ n/d"
    if c <= 0:
        return "$0"
    if c < 0.0001:
        return "$%.6f" % c
    return "$%s" % ("%.2g" % c if c < 1 else "%.2f" % c)


#: El presupuesto PRUDENTE (interno) de un modelo que no declara su límite:
#: se usa para no mandar de más, pero jamás se muestra como si fuera suyo.
LIMITE_PRUDENTE = 8000


def declared_limit(decider_id):
    """El límite que se puede DECIR: el META `context_tokens` del modelo o el
    que fijó el socio (decisions.model_limits); None si no hay ninguno."""
    try:
        base = int(_meta(decider_id).get("context_tokens") or 0)
    except (TypeError, ValueError):
        base = 0
    if base > 0:
        return limit(decider_id)
    try:
        import settings
        v = int((settings.get("decisions.model_limits") or {}).get(decider_id) or 0)
        return v if v > 0 else None
    except Exception:
        return None


def limit(decider_id):
    """Límite de entrada del decisor: su META `context_tokens` (medido). El
    ajuste `decisions.model_limits` puede BAJARLO (más barato y rápido),
    nunca subirlo más allá de lo que el modelo admite. Sin ninguno de los
    dos, LIMITE_PRUDENTE (interno: declared_limit dice None)."""
    base = 0
    try:
        base = int(_meta(decider_id).get("context_tokens") or 0)
    except (TypeError, ValueError):
        base = 0
    try:
        import settings
        over = settings.get("decisions.model_limits") or {}
        v = int(over.get(decider_id) or 0)
        if v > 0:
            return min(v, base) if base else v
    except Exception:
        pass
    return base or LIMITE_PRUDENTE


def _q_raw(question="", options=(), criteria=None):
    return (raw_tokens(question) + sum(raw_tokens(o) for o in (options or ()))
            + sum(raw_tokens(str(c)) for c in (criteria or {}).values() if c))


def budget(decider_id, question="", options=(), factor=None, criteria=None):
    """Tokens disponibles para el CONTEXTO: límite − sobrecarga − pregunta,
    opciones y descripciones − colchón (max(1000, 10 %)); y no más que
    `decisions.context_budget` si es > 0."""
    lim = limit(decider_id)
    f = factor if factor else token_factor(decider_id)
    margen = (overhead(decider_id) + int(math.ceil(_q_raw(question, options, criteria) * f))
              + max(SAFETY_TOKENS, int(lim * SAFETY_FRACTION)))
    b = lim - margen
    try:
        import settings
        cap = int(settings.get("decisions.context_budget") or 0)
        if cap > 0:
            b = min(b, cap)
    except Exception:
        pass
    return max(0, b)


# ── privacidad ───────────────────────────────────────────────────────────────
def _limpio(v):
    """El valor de un `clave: valor` del frontmatter, sin comillas ni el
    comentario del final (`true  # ojo`)."""
    v = v.strip()
    if " #" in v:
        v = v.split(" #", 1)[0]
    return v.strip().strip("'\"").strip().lower()


def is_private_text(text):
    """¿El frontmatter dice que es privado? `privado|private|confidencial|
    confidential` con true/sí/yes/1/on (también `"privado": true`, con un
    comentario al final, o con renglones en blanco antes del frontmatter), o
    una etiqueta privado/private/confidencial en `tags` (en línea, entre
    corchetes o en lista)."""
    m = _FM.match(text or "")
    if not m:
        return False
    lines = m.group(1).splitlines()
    for i, ln in enumerate(lines):
        k, sep, v = ln.partition(":")
        if not sep:
            continue
        key = k.strip().strip("'\"").strip().lower()
        if key in PRIVATE_KEYS and _limpio(v) in _TRUE:
            return True
        if key in _TAG_KEYS:
            val = v.strip()
            if " #" in val:                               # un comentario al final
                val = val.split(" #", 1)[0].strip()
            if val:
                items = val.strip("[]").split(",")
            else:
                items = []
                for nxt in lines[i + 1:]:
                    im = _ITEM.match(nxt)
                    if not im:
                        break
                    items.append(im.group(1))
            if any(x.strip().strip("'\"").lstrip("#").strip().lower() in PRIVATE_KEYS for x in items):
                return True
    return False


def _rel(brain, path):
    return os.path.relpath(path, brain).replace(os.sep, "/")


def socio_activo(brain):
    """El socio de esta máquina en este cerebro (sessions_registry.socio:
    identidad → .claude/socio.local → …), en minúsculas; '' si no se sabe."""
    try:
        import sessions_registry as reg
        return str(reg.socio(brain) or "").strip().lower()
    except Exception:
        return ""


def _ajeno(rel, socio):
    """¿Es de OTRA persona (o del cliente)? → 'socio' · 'cliente' · ''.
    En un cerebro compartido no salen: las sesiones de otros socios
    (STATE/sessions/<otro>/), los perfiles salvo el propio (STATE/users/),
    la bandeja de entrada de todos (STATE/inbox/), la memoria de motor de
    otros (motores/*/memoria/<otro>/) y los insumos del cliente (lo que
    empieza con `_` dentro de deliverables/). Sin saber quién eres, nada
    personal de nadie."""
    low = rel.lower().split("/")
    if len(low) >= 4 and low[0] == "state" and low[1] == "sessions" and (not socio or low[2] != socio):
        return "socio"
    if len(low) >= 3 and low[0] == "state" and low[1] == "users":
        nombre = low[2][:-3] if (len(low) == 3 and low[2].endswith(".md")) else low[2]
        if not socio or nombre != socio:
            return "socio"
    if len(low) >= 3 and low[0] == "state" and low[1] == "inbox":
        return "socio"
    if len(low) >= 5 and low[0] == "motores" and low[2] == "memoria" and (not socio or low[3] != socio):
        return "socio"
    if low[0] == "deliverables" and any(x.startswith("_") for x in rel.split("/")[1:]):
        return "cliente"
    return ""


def _excluido(brain, path, size, socio):
    """None = se lee; '' = no es texto de un cerebro (no cuenta); si no, el
    motivo que se cuenta en «excluidos» (conversacion · llaves · socio ·
    cliente)."""
    name = os.path.basename(path)
    if not name.lower().endswith(TEXT_EXT) or size <= 0 or size > MAX_FILE_BYTES:
        return ""
    rel = _rel(brain, path)
    if _SKIP_REL.search(rel):
        return "conversacion"
    if _SECRET_NAME.search(name):
        return "llaves"
    return _ajeno(rel, socio) or None


def _skip_file(brain, path, size, socio=None):
    if socio is None:
        socio = socio_activo(brain)
    return _excluido(brain, path, size, socio) is not None


def _cuenta_textos(d):
    """Cuántos archivos de texto hay bajo una carpeta que no se lee (privada)."""
    n = 0
    try:
        for _r, _ds, fs in os.walk(d):
            n += sum(1 for f in fs if f.lower().endswith(TEXT_EXT))
            if n > 100000:
                break
    except OSError:
        pass
    return n


def read_text(path, info=None):
    """Texto de un archivo de texto; '' si es binario, ilegible o privado
    (`info["privado"] = True` si fue por privado)."""
    try:
        with open(path, "rb") as fh:
            raw = fh.read(MAX_FILE_BYTES + 1)
    except OSError:
        return ""
    if len(raw) > MAX_FILE_BYTES or b"\x00" in raw[:8192]:
        return ""
    text = raw.decode("utf-8", "replace")
    if is_private_text(text):
        if info is not None:
            info["privado"] = True
        return ""
    return text


def _dentro(brain, path):
    """¿`path` (ya resuelto, sin enlaces) queda dentro del cerebro real?"""
    try:
        rb = os.path.realpath(brain)
        real = os.path.realpath(path)
        return os.path.normcase(os.path.commonpath([rb, real])) == os.path.normcase(rb)
    except (OSError, ValueError):
        return False


def _rel_dentro(brain, path):
    """La ruta de `path` relativa al cerebro (dado tal cual o ya resuelto), o
    None si queda fuera."""
    ap = os.path.abspath(path)
    for raiz in (os.path.abspath(brain), os.path.realpath(brain)):
        try:
            r = os.path.relpath(ap, raiz)
        except ValueError:                 # otra unidad (Windows)
            continue
        if not (r == os.pardir or r.startswith(os.pardir + os.sep)):
            return r
    return None


def _fiel(brain, path):
    """¿`path` es DE VERDAD esa ruta dentro del cerebro? Su ruta real (sin
    symlinks ni junctions en el camino) es la misma ruta dentro del cerebro
    real. En Windows islink() no ve un junction (solo los symlinks; VERIFICADO
    2026-11-09 por ssh en la PC: os.walk entra y realpath lo resuelve), así
    que se compara la ruta real — revisor sobre ed793cd8, A."""
    rel = _rel_dentro(brain, path)
    if rel is None:
        return False
    esperado = os.path.normpath(os.path.join(os.path.realpath(brain), rel))
    try:
        return os.path.normcase(os.path.realpath(path)) == os.path.normcase(esperado)
    except (OSError, ValueError):
        return False


def _hard_link(st):
    """¿Un archivo con otra ruta para el MISMO contenido (st_nlink > 1)? Puede
    ser privado/ o lo de otro socio con otro nombre: no se lee."""
    return stat.S_ISREG(st.st_mode) and getattr(st, "st_nlink", 1) > 1


def _archivo_seguro(brain, path, socio=None):
    """¿Se puede leer `path` (que NO viene de _walk) para mandarlo a un
    decisor? Los MISMOS controles que el recorrido: un archivo normal (no un
    enlace) sin hard links, cuya ruta real es la suya dentro del cerebro, sin
    carpetas privadas ni de las que nunca se leen en el camino, de texto y
    que no es de otro socio ni de lo que nunca sale. Lo privado por
    frontmatter lo mira read_text (Greptile final 0.9.0, 5)."""
    try:
        st = os.lstat(path)
    except OSError:
        return False
    rel = _rel_dentro(brain, path)
    if rel is None or not stat.S_ISREG(st.st_mode) or _hard_link(st) or not _fiel(brain, path):
        return False
    partes = rel.replace(os.sep, "/").split("/")[:-1]
    if any(x.lower() in PRIVATE_DIRS or x.lower() in SKIP_DIRS or x.startswith(".")
           for x in partes):
        return False
    if socio is None:
        socio = socio_activo(brain)
    return _excluido(brain, os.path.join(brain, rel), st.st_size, socio) is None


def _walk(brain, base=None, stats=None):
    """Archivos candidatos bajo `base` (default: todo el cerebro), sin las
    carpetas que nunca se leen, las privadas ni lo de otros socios. Si se da
    `stats`, cuenta lo excluido por motivo. → [(path, size)]. Jamás sigue un
    enlace (symlink): ni a un archivo (stat/open leerían el destino, que puede
    ser privado/, de otro socio o de fuera) ni a una carpeta, tampoco la de
    partida (Greptile 0.8.x, 3). Tampoco entra a una carpeta cuya ruta real no
    es la suya (un junction de Windows, que islink() no ve) ni lee un archivo
    con hard links (st_nlink > 1); lo saltado se cuenta como «enlace» en los
    excluidos (revisor sobre ed793cd8, A)."""
    out = []
    base = base or brain
    if os.path.islink(base) or not _dentro(brain, base) or not _fiel(brain, base):
        if stats is not None and os.path.isdir(base):
            stats["enlace"] = stats.get("enlace", 0) + 1
        return out
    socio = socio_activo(brain)

    def saltado():
        if stats is not None:
            stats["enlace"] = stats.get("enlace", 0) + 1
    for root, dirs, files in os.walk(base):
        rroot = os.path.realpath(root)
        quedan = []
        for d in sorted(dirs):
            dl = d.lower()
            if dl in SKIP_DIRS or d.startswith("."):
                continue
            if dl in PRIVATE_DIRS:
                if stats is not None:
                    stats["privado"] = stats.get("privado", 0) + _cuenta_textos(os.path.join(root, d))
                continue
            full = os.path.join(root, d)
            try:
                real = os.path.realpath(full)
            except (OSError, ValueError):
                real = ""
            if os.path.islink(full) or os.path.normcase(real) != os.path.normcase(
                    os.path.join(rroot, d)):
                saltado()                  # junction o symlink: su contenido es de otro lado
                continue
            quedan.append(d)
        dirs[:] = quedan
        for fn in sorted(files):
            p = os.path.join(root, fn)
            try:
                st = os.lstat(p)
            except OSError:
                continue
            if not stat.S_ISREG(st.st_mode):
                if stat.S_ISLNK(st.st_mode):
                    saltado()
                continue                   # un enlace (o algo que no es archivo): no se sigue
            if _hard_link(st):
                saltado()
                continue
            motivo = _excluido(brain, p, st.st_size, socio)
            if motivo is None:
                out.append((p, st.st_size))
            elif motivo and stats is not None:
                stats[motivo] = stats.get(motivo, 0) + 1
    return out


def scan_brain(brain):
    """Todas las fuentes de texto del cerebro, ya filtradas (privacidad y
    otros socios incluidos). SIN caché: el texto crudo (sin redactar) no se
    queda en la memoria del hub; lo que se reusa es el índice ya redactado
    (corpus). → [(rel, texto)]."""
    brain = os.path.realpath(brain)
    out = []
    for p, _s in _walk(brain):
        t = read_text(p)
        if t.strip():
            out.append((_rel(brain, p), t))
    return out


def mtimes(brain):
    """{rel: fecha de modificación} de lo que se lee del cerebro — con stat,
    sin leer ni guardar el contenido."""
    brain = os.path.realpath(brain)
    return {_rel(brain, p): _mtime(p) for p, _s in _walk(brain)}


def _mtime(p):
    try:
        return os.path.getmtime(p)
    except OSError:
        return 0


# ── fuentes por nivel ────────────────────────────────────────────────────────
def _agent(name):
    try:
        import agentsreg
        return agentsreg.find(name)
    except Exception:
        return None


def memory_sources(brain):
    """La memoria curada: STATE/MEMORY.md, STATE/INDEX.md y la memoria de
    Claude Code del socio de esta máquina (formato v2). → [(rel, texto)]."""
    out = []
    for rel in ("STATE/MEMORY.md", "STATE/INDEX.md"):
        p = os.path.join(brain, *rel.split("/"))
        try:
            st = os.lstat(p)
        except OSError:
            continue
        if not stat.S_ISREG(st.st_mode) or _hard_link(st) or not _fiel(brain, p):
            continue                       # un enlace, junction o hard link no se sigue
        size = st.st_size
        if not _skip_file(brain, p, size):
            t = read_text(p)
            if t.strip():
                out.append((rel, t))
    try:
        import memoria
        d = memoria.claude_memoria_dir(brain)
    except Exception:
        d = ""
    if d and os.path.isdir(d):
        for p, _s in _walk(brain, d):
            t = read_text(p)
            if t.strip():
                out.append((_rel(brain, p), t))
    return out


def memory_excluded(brain):
    """Lo que «Memoria» NO manda por ser de otros socios o privado: la memoria
    de motor de los demás (motores/*/memoria/<otro>/) y lo privado o con
    nombre de llaves de la propia."""
    n = 0
    socio = socio_activo(brain)
    base = os.path.join(brain, "motores")
    try:
        motores = sorted(os.listdir(base))
    except OSError:
        motores = []
    for m in motores:
        d = os.path.join(base, m, "memoria")
        try:
            subs = sorted(os.listdir(d))
        except OSError:
            continue
        for x in subs:
            px = os.path.join(d, x)
            if not os.path.isdir(px):
                continue
            if not socio or x.lower() != socio:
                n += _cuenta_textos(px)
            else:
                fuera = {}
                for p, _s in _walk(brain, px, stats=fuera):
                    info = {}
                    read_text(p, info)
                    n += 1 if info.get("privado") else 0
                n += sum(fuera.values())
    return n


def resumen_pestana(brain, nombre, limit=1200):
    """(texto, privado) del resumen (checkpoint) de una pestaña para mandarlo
    a un decisor, con los MISMOS filtros que Cerebro: nada si el checkpoint o
    la propia pestaña son privados (`privado: true`…), de otro socio o no son
    archivos normales (un enlace no cuenta). Greptile 0.8.x, 2: antes se
    mandaba el JSON del checkpoint sin mirar su frontmatter."""
    try:
        import sessions_registry as reg
        import session_continuity as sc
        socio = socio_activo(brain)
        for p in (reg._md_path(str(brain), nombre), str(sc.checkpoint_path(brain, nombre))):
            if not p or not os.path.exists(p):
                continue
            st = os.lstat(p)
            if not stat.S_ISREG(st.st_mode) or _hard_link(st) or not _fiel(brain, p) \
                    or _ajeno(_rel(brain, p), socio):
                return "", True
            info = {}
            read_text(p, info)
            if info.get("privado"):
                return "", True
        return sc.context(brain, nombre, limit=limit) or "", False
    except Exception:
        return "", False


def tab_list(name):
    """Las pestañas del agente con su resumen (para «Sesiones…»), la más
    reciente primero. → [{"name", "slug", "text", "tokens"}]."""
    a = _agent(name)
    if not a:
        return []
    brain = a["brain"]
    try:
        import sessions_registry as reg
        tabs = sorted(reg._pestanas(brain), key=lambda t: reg.ultimo_uso(t), reverse=True)
    except Exception:
        return []
    out = []
    for t in tabs:
        nombre = t.get("name", "")
        txt, privado = resumen_pestana(brain, nombre, TAB_SUMMARY_CHARS)
        if not txt and not privado:
            # sin checkpoint, el texto de la pestaña: con los MISMOS controles
            # (un alias.md enlazado a privado/ no se lee — Greptile final, 5)
            p = t.get("archivo") or ""
            txt = read_text(p)[:TAB_SUMMARY_CHARS] if p and _archivo_seguro(brain, p) else ""
        out.append({"name": nombre, "slug": t.get("slug", ""), "text": txt,
                    "tokens": raw_tokens(txt)})
    return out


def sources(level, name, tabs=None):
    """Las fuentes crudas de un nivel para el agente `name`: [(etiqueta, texto)]."""
    if level == "nada":
        return []
    a = _agent(name)
    if level == "pestana":
        try:
            import decisions
            c = decisions.agent_context(name)
        except Exception:
            c = {"tab": "", "text": ""}
        return [("pestaña «%s»" % c["tab"], c["text"])] if c.get("text") else []
    if not a:
        return []
    brain = a["brain"]
    if level == "sesiones":
        quiero = set(tabs or ())
        return [("pestaña «%s»" % t["name"], t["text"]) for t in tab_list(name)
                if t["slug"] in quiero and t["text"]]
    if level == "memoria":
        return memory_sources(brain)
    if level == "cerebro":
        return scan_brain(brain)
    return []


# ── el índice del cerebro (caché por archivo: ruta + tamaño + fecha) ─────────
#: path → {"sig", "label", "text" (redactado), "full_raw", "chunks": [(k, texto, raw)], "mtime"}
_FILES = {}
#: realpath(cerebro) → el corpus armado (trozos, tokens, FTS5, fechas). LRU:
#: a lo más CACHE_BRAINS cerebros y ~CACHE_MAX_BYTES entre todos (un cerebro
#: de 8 MB pesaba ~74 MB en el hub y nada se soltaba); el más reciente se
#: queda aunque solo él pase del tope. `free()` suelta todo (al salir de la
#: sección).
_CORPUS = collections.OrderedDict()
_CORPUS_LOCK = threading.Lock()
#: El orden LRU se toca con su propio candado (rápido): el camino caliente no
#: espera a una construcción, y nadie recorre el diccionario mientras cambia.
_ORDEN_LOCK = threading.Lock()
#: free() sube la generación: una construcción en curso la ve y se cancela.
_GEN = [0]
CACHE_BRAINS = 2
CACHE_MAX_BYTES = 48 * 1024 * 1024
_TECLEO = [0.0]
#: Mientras el socio teclea (hace menos de esto), el armado en frío espera.
TYPING_QUIET_S = 0.4


def typing():
    """La sección avisa que el socio está tecleando: el armado en frío del
    índice cede el paso (no compite con la pantalla)."""
    _TECLEO[0] = time.time()


def _pausa():
    """Entre archivo y archivo: soltar el GIL; si el socio teclea, esperar."""
    if time.time() - _TECLEO[0] < TYPING_QUIET_S:
        time.sleep(0.02)
    else:
        time.sleep(0)


def _red_version():
    """Lo que cambia el resultado de redactar además del archivo: la llave
    del entorno y la bóveda (decisions.redact quita sus valores literales)."""
    try:
        import decisions
        return decisions.redaction_version()
    except Exception:
        return hash(os.environ.get("TYPESAFE_API_KEY") or "")


def _file_entry(brain, path, size, mtime, red_ver):
    """La entrada en caché de un archivo (la arma si cambió su firma)."""
    sig = (size, mtime, red_ver)
    e = _FILES.get(path)
    if e is not None and e["sig"] == sig:
        return e, False
    lb = _rel(brain, path)
    info = {}
    txt = read_text(path, info)
    red = _redact(txt) if txt.strip() else ""
    chunks = []
    if red.strip():
        chunks = [(k, c, raw_tokens(_bloque(lb, c))) for _lb, k, c in _chunks(lb, red)]
    e = {"sig": sig, "label": lb, "text": red, "mtime": mtime, "chunks": chunks,
         "full_raw": raw_tokens(_bloque(lb, red)) if red.strip() else 0,
         "privado": bool(info.get("privado"))}
    _FILES[path] = e
    return e, True


def _fts(chunks):
    """Índice FTS5 en memoria de los trozos (o None si no hay FTS5)."""
    try:
        import sqlite3
        con = sqlite3.connect(":memory:", check_same_thread=False)
        con.execute("CREATE VIRTUAL TABLE c USING fts5(body, "
                    "tokenize='unicode61 remove_diacritics 2')")
        con.executemany("INSERT INTO c(rowid, body) VALUES (?, ?)",
                        ((i, ch[2]) for i, ch in enumerate(chunks)))
        return con
    except Exception:
        return None


def corpus(brain):
    """El cerebro listo para preguntar: {"firma", "chunks": [(etiqueta, k,
    texto)], "costo": [tokens crudos por trozo], "files": [(etiqueta, texto,
    tokens crudos)], "total_raw", "mtimes", "fts", "lock"} — redactado y
    contado UNA vez por archivo (caché por ruta + tamaño + fecha). None si no
    hay cerebro."""
    try:
        brain = os.path.realpath(brain)
        fuera = {}
        files = _walk(brain, stats=fuera)
    except Exception:
        return None
    red_ver = _red_version()
    firma = (tuple((p, sz, _mtime(p)) for p, sz in files), red_ver)
    hit = _CORPUS.get(brain)
    if hit is not None and hit["firma"] == firma:
        hit["excluded"] = sum(fuera.values()) + hit.get("privados", 0)
        _usado(brain)
        return hit
    with _CORPUS_LOCK:
        gen = _GEN[0]
        hit = _CORPUS.get(brain)
        if hit is not None and hit["firma"] == firma:
            _usado(brain)
            return hit
        entries, privados = [], 0
        for p, sz in files:
            if _GEN[0] != gen:                  # free() pidió soltar todo: se cancela
                _vaciar()
                return None
            e, nuevo = _file_entry(brain, p, sz, _mtime(p), red_ver)
            if nuevo:
                _pausa()
            privados += 1 if e.get("privado") else 0
            if e["text"].strip():
                entries.append(e)
        vivos = {p for p, _sz in files}
        for p in [q for q in _FILES if q.startswith(brain + os.sep) and q not in vivos]:
            _FILES.pop(p, None)                 # lo que se borró del cerebro
        chunks, costo = [], []
        for e in entries:
            for k, c, r in e["chunks"]:
                chunks.append((e["label"], k, c))
                costo.append(r)
        if _GEN[0] != gen:
            _vaciar()
            return None
        viejo = hit.get("fts") if hit else None
        cp = {"firma": firma, "chunks": chunks, "costo": costo,
              "files": [(e["label"], e["text"], e["full_raw"]) for e in entries],
              "total_raw": sum(e["full_raw"] for e in entries),
              "mtimes": {e["label"]: e["mtime"] for e in entries},
              "fts": _fts(chunks) if chunks else None, "lock": threading.Lock(), "words": None,
              "privados": privados, "excluded": sum(fuera.values()) + privados}
        cp["bytes"] = _peso(entries, chunks, cp["fts"])
        if _GEN[0] != gen:                      # free() llegó mientras se armaba el índice
            _cerrar(cp)
            _vaciar()
            return None
        with _ORDEN_LOCK:
            _CORPUS[brain] = cp
        _usado(brain)
        if viejo is not None:
            _cerrar(hit)
        _recortar(brain)
        return cp


def _peso(entries, chunks, fts=None):
    """≈ bytes en memoria de un corpus, con los tamaños REALES de los objetos
    (sys.getsizeof: texto, trozos, tuplas, entradas) más las páginas del índice
    FTS5 y un margen de 1.5× por lo que ningún getsizeof ve (el asignador, los
    índices de Python). La estimación de antes (3 × caracteres) se quedaba
    ~3× corta."""
    py = 0
    for e in entries:
        py += sys.getsizeof(e) + sys.getsizeof(e["text"]) + sys.getsizeof(e["chunks"])
        py += sum(sys.getsizeof(c) + sys.getsizeof(t) + 64 for t in e["chunks"] for c in (t[1],))
    py += sys.getsizeof(chunks) + sum(sys.getsizeof(t) for t in chunks)
    db = 0
    if fts is not None:
        try:
            db = (fts.execute("PRAGMA page_count").fetchone()[0]
                  * fts.execute("PRAGMA page_size").fetchone()[0])
        except Exception:
            db = 3 * sum(len(e["text"]) for e in entries)
    return int(1.5 * (py + db)) + _PESO_FIJO


#: Lo que un corpus deja en el proceso además de sus objetos (arenas del
#: asignador, temporales de la redacción): medido en un cerebro de 8 MB, la
#: memoria del proceso creció 58 MB con 59 estimados; en uno de 5.5 MB, 21 con
#: 16. Mejor estimar de más: el tope es para que el hub no crezca sin fin.
_PESO_FIJO = 4 * 1024 * 1024


def _usado(brain):
    with _ORDEN_LOCK:
        try:
            _CORPUS.move_to_end(brain)
        except KeyError:
            pass


def _cerrar(cp):
    """Cierra el FTS5 de un corpus bajo SU candado (un hilo del medidor puede
    estar rankeando con él)."""
    if not cp:
        return
    lk = cp.get("lock")
    try:
        if lk is not None:
            lk.acquire()
        con, cp["fts"] = cp.get("fts"), None
        if con is not None:
            con.close()
    except Exception:
        pass
    finally:
        if lk is not None:
            try:
                lk.release()
            except Exception:
                pass


def _soltar(brain):
    """Saca un cerebro de las cachés (su corpus y sus archivos)."""
    with _ORDEN_LOCK:
        cp = _CORPUS.pop(brain, None)
    _cerrar(cp)
    pre = brain + os.sep
    for p in [q for q in list(_FILES) if q.startswith(pre)]:
        _FILES.pop(p, None)


def _recortar(actual):
    """LRU: fuera los cerebros menos usados mientras haya más de CACHE_BRAINS
    o pesen más de CACHE_MAX_BYTES entre todos (el actual nunca)."""
    while True:
        with _ORDEN_LOCK:
            if len(_CORPUS) <= 1:
                return
            total = sum(c.get("bytes", 0) for c in list(_CORPUS.values()))
            if len(_CORPUS) <= CACHE_BRAINS and total <= CACHE_MAX_BYTES:
                return
            viejo = next(iter(_CORPUS))
        if viejo == actual:
            return
        _soltar(viejo)


def _vaciar():
    with _ORDEN_LOCK:
        cps = list(_CORPUS.values())
        _CORPUS.clear()
    for cp in cps:
        _cerrar(cp)
    _FILES.clear()


def free():
    """Suelta TODO lo que Decisores guarda en memoria (al salir de la
    sección) sin esperar: si una construcción está en curso, se cancela (ve
    la generación nueva entre archivo y archivo, suelta todo y su hilo —daemon—
    termina solo); antes, salir de la sección esperaba hasta ~6 s."""
    _GEN[0] += 1
    if _CORPUS_LOCK.acquire(False):
        try:
            _vaciar()
        finally:
            _CORPUS_LOCK.release()


def cache_bytes():
    """≈ bytes de las cachés (para pruebas y el doctor)."""
    return sum(c.get("bytes", 0) for c in _CORPUS.values())


def _rank_corpus(cp, query, brain):
    """Rankear con el índice ya armado del cerebro (sin redactar ni tokenizar)."""
    terms = _terms(query)
    if not terms or not cp["chunks"]:
        return {}
    scores = {}
    with cp["lock"]:
        con = cp.get("fts")
        if con is not None:
            try:
                match = " OR ".join('"%s"' % t.replace('"', "") for t in terms)
                rows = con.execute("SELECT rowid, bm25(c) FROM c WHERE c MATCH ?", (match,)).fetchall()
                scores = {int(r): -float(sc) for r, sc in rows}
            except Exception:
                con = None
        if con is None:
            if cp.get("words") is None:
                cp["words"] = [set(_WORD.findall(ch[2].lower())) for ch in cp["chunks"]]
            docs = cp["words"]
            n = len(docs) or 1
            df = {t: sum(1 for d in docs if t in d) for t in terms}
            for i, d in enumerate(docs):
                sc = sum(math.log(1 + n / (1 + df[t])) for t in terms if t in d)
                if sc > 0:
                    scores[i] = sc
    return _boost(scores, cp["chunks"], terms, brain)


# ── armar el contexto ────────────────────────────────────────────────────────
def _redact(text):
    try:
        import decisions
        return decisions.redact(text)
    except Exception:
        return ""


def _chunks(label, text):
    """Trozos de ~CHUNK_CHARS por párrafos (un párrafo enorme se corta)."""
    out, cur = [], ""
    for par in re.split(r"\n\s*\n", text):
        par = par.strip()
        if not par:
            continue
        while len(par) > CHUNK_CHARS:
            if cur:
                out.append(cur)
                cur = ""
            out.append(par[:CHUNK_CHARS])
            par = par[CHUNK_CHARS:]
        if cur and len(cur) + len(par) + 2 > CHUNK_CHARS:
            out.append(cur)
            cur = par
        else:
            cur = (cur + "\n\n" + par) if cur else par
    if cur:
        out.append(cur)
    return [(label, i, c) for i, c in enumerate(out)]


_WORD = re.compile(r"\w+", re.UNICODE)


def _terms(query):
    seen, out = set(), []
    for w in _WORD.findall((query or "").lower()):
        if len(w) > 2 and w not in seen:
            seen.add(w)
            out.append(w)
    return out[:64]


def _rank_fts(chunks, terms):
    import sqlite3
    con = sqlite3.connect(":memory:")
    try:
        con.execute("CREATE VIRTUAL TABLE c USING fts5(body, "
                    "tokenize='unicode61 remove_diacritics 2')")
        con.executemany("INSERT INTO c(rowid, body) VALUES (?, ?)",
                        [(i, ch[2]) for i, ch in enumerate(chunks)])
        match = " OR ".join('"%s"' % t.replace('"', "") for t in terms)
        rows = con.execute("SELECT rowid, bm25(c) FROM c WHERE c MATCH ?", (match,)).fetchall()
    finally:
        con.close()
    return {int(r): -float(s) for r, s in rows}


def _rank_words(chunks, terms):
    docs = [set(_WORD.findall(ch[2].lower())) for ch in chunks]
    n = len(docs) or 1
    df = {t: sum(1 for d in docs if t in d) for t in terms}
    out = {}
    for i, d in enumerate(docs):
        s = sum(math.log(1 + n / (1 + df[t])) for t in terms if t in d)
        if s > 0:
            out[i] = s
    return out


def rank(chunks, query, brain=None):
    """{índice de trozo: puntaje} — mayor = más relevante (solo los que algo
    tienen que ver). FTS5 bm25 + empujón del índice de memoria; sin FTS5,
    palabras con idf."""
    terms = _terms(query)
    if not terms or not chunks:
        return {}
    try:
        scores = _rank_fts(chunks, terms)
    except Exception:
        scores = _rank_words(chunks, terms)
    return _boost(scores, chunks, terms, brain)


def _boost(scores, chunks, terms, brain):
    """+1 a los trozos de lo que el índice de memoria del cerebro ya rankea alto."""
    if brain and scores:
        try:
            import memory_index
            top = memory_index.query(brain, " ".join(terms), top=10)
            alto = {os.path.realpath(r["path"]) for r in top}
        except Exception:
            alto = set()
        if alto:
            for i in list(scores):
                p = os.path.realpath(os.path.join(brain, *chunks[i][0].split("/")))
                if p in alto:
                    scores[i] += 1.0
    return scores


def _bloque(label, txt):
    return "### %s\n%s\n" % (label, txt.strip())


def _assemble(parts, factor=1.0):
    """[(etiqueta, texto)] → (texto, [(etiqueta, tokens)], tokens crudos)."""
    out, srcs, order, raw = [], {}, [], 0
    for label, txt in parts:
        bloque = _bloque(label, txt)
        out.append(bloque)
        r = raw_tokens(bloque)
        raw += r
        if label not in srcs:
            order.append(label)
            srcs[label] = 0
        srcs[label] += int(math.ceil(r * factor))
    return "\n".join(out), [(lb, srcs[lb]) for lb in order], raw


#: Fuentes que van primero en «lo más reciente»: la memoria y los índices.
_MEMORIA = re.compile(r"(^|/)(MEMORY|INDEX|index)\.md$|^motores/[^/]+/memoria/")


def _representativo(trozos, brain, fechas=None):
    """Orden de «lo más reciente»: memoria e índices primero; luego las notas
    y sesiones más nuevas; cada archivo en su orden."""
    if fechas is None:
        fechas = mtimes(brain) if brain else {}
    orden = {}
    for i, (lb, k, _t) in enumerate(trozos):
        orden.setdefault(lb, len(orden))

    def clave(i):
        lb, k, _t = trozos[i]
        return (0 if _MEMORIA.search(lb) else 1, -fechas.get(lb, 0.0), orden[lb], k)
    return sorted(range(len(trozos)), key=clave)


def _select(trozos, costo, puntos, tope_raw, orden_rep):
    """Primero lo que coincide (por puntaje) y, en lo que sobre, lo
    representativo. → (elegidos, tokens usados, tokens de lo que coincide)."""
    elegidos, usados = [], 0
    for i in sorted(puntos, key=lambda k: -puntos[k]):
        if usados + costo[i] > tope_raw:
            continue
        elegidos.append(i)
        usados += costo[i]
    relevantes = usados
    ya = set(elegidos)
    for i in orden_rep:
        if i in ya or usados + costo[i] > tope_raw:
            continue
        elegidos.append(i)
        ya.add(i)
        usados += costo[i]
    return elegidos, usados, relevantes


def _build_corpus(cp, level, question, options, f, presupuesto, brain, vacio):
    """build() para «cerebro» con el índice en caché: no redacta ni tokeniza."""
    if not cp or not cp["files"]:
        return vacio
    fuera = cp.get("excluded", 0)
    if int(math.ceil(cp["total_raw"] * f)) <= presupuesto:
        texto = "\n".join(_bloque(lb, tx) for lb, tx, _r in cp["files"])
        srcs = [(lb, int(math.ceil(r * f))) for lb, _tx, r in cp["files"]]
        return {"level": level, "mode": "todo", "text": texto, "sources": srcs,
                "tokens": int(math.ceil(cp["total_raw"] * f)), "raw": cp["total_raw"],
                "budget": presupuesto, "factor": f, "excluded": fuera}
    trozos, costo = cp["chunks"], cp["costo"]
    puntos = _rank_corpus(cp, " ".join([question or ""] + list(options or ())), brain)
    elegidos, usados, relevantes = _select(trozos, costo, puntos, presupuesto / f,
                                           _representativo(trozos, brain, cp["mtimes"]))
    if not elegidos:
        return dict(vacio, mode="relevante")
    modo = "relevante" if relevantes >= RELEVANT_SHARE * usados else "reciente"
    elegidos.sort(key=lambda i: (trozos[i][0], trozos[i][1]))
    texto = "\n".join(_bloque(trozos[i][0], trozos[i][2]) for i in elegidos)
    por, orden = {}, []
    for i in elegidos:
        lb = trozos[i][0]
        if lb not in por:
            orden.append(lb)
            por[lb] = 0
        por[lb] += costo[i]
    return {"level": level, "mode": modo, "text": texto,
            "sources": [(lb, int(math.ceil(por[lb] * f))) for lb in orden],
            "tokens": int(math.ceil(usados * f)), "raw": usados, "budget": presupuesto, "factor": f,
            "excluded": fuera}


def build(level, name, question="", options=(), decider_id="rules", tabs=None, cap_raw=None,
          factor=None):
    """build() con «excluded»: cuántos archivos NO van por ser de otros socios,
    del cliente o privados (Cerebro y Memoria; la vista `v` lo cuenta)."""
    ctx = _build(level, name, question, options, decider_id, tabs, cap_raw, factor)
    if level == "memoria" and "excluded" not in ctx:
        a = _agent(name)
        try:
            ctx["excluded"] = memory_excluded(a["brain"]) if a else 0
        except Exception:
            ctx["excluded"] = 0
    ctx.setdefault("excluded", 0)
    return ctx


def _build(level, name, question="", options=(), decider_id="rules", tabs=None, cap_raw=None,
           factor=None):
    """El contexto de una pregunta. → {"level", "mode": "todo" | "relevante" |
    "reciente" | "vacío", "text", "sources": [(etiqueta, tokens)], "tokens",
    "raw", "budget", "factor"}. Todo redactado; jamás excede el presupuesto
    (ni `cap_raw`, el recorte de ask() en tokens por contenido). Si no cabe
    todo: primero lo que coincide con la pregunta y, en lo que sobre, lo
    representativo (memoria e índices, luego lo más nuevo). «cerebro» usa el
    índice en caché (corpus). Falla-suave."""
    level = level if level in LEVELS else DEFAULT_LEVEL
    f = factor if factor else token_factor(decider_id)
    presupuesto = budget(decider_id, question, options, factor=f)
    if cap_raw is not None:
        presupuesto = max(0, min(presupuesto, int(cap_raw * f)))
    vacio = {"level": level, "mode": "vacío", "text": "", "sources": [], "tokens": 0, "raw": 0,
             "budget": presupuesto, "factor": f}
    if level == "nada" or presupuesto <= 0:
        return vacio
    if level == "cerebro":
        a = _agent(name)
        if not a:
            return vacio
        return _build_corpus(corpus(a["brain"]), level, question, options, f, presupuesto,
                             a["brain"], vacio)
    try:
        crudas = sources(level, name, tabs)
    except Exception:
        crudas = []
    limpias = [(lb, _redact(tx)) for lb, tx in crudas]
    limpias = [(lb, tx) for lb, tx in limpias if tx.strip()]
    if not limpias:
        return vacio
    texto, srcs, raw = _assemble(limpias, f)
    if int(math.ceil(raw * f)) <= presupuesto:
        return {"level": level, "mode": "todo", "text": texto, "sources": srcs,
                "tokens": int(math.ceil(raw * f)), "raw": raw, "budget": presupuesto, "factor": f}
    a = _agent(name)
    brain = a["brain"] if a and level == "memoria" else None
    trozos = [ch for lb, tx in limpias for ch in _chunks(lb, tx)]
    costo = [raw_tokens(_bloque(t[0], t[2])) for t in trozos]
    puntos = rank(trozos, " ".join([question or ""] + list(options or ())), brain)
    elegidos, usados, relevantes = _select(trozos, costo, puntos, presupuesto / f,
                                           _representativo(trozos, brain))
    if not elegidos:
        return dict(vacio, mode="relevante")
    modo = "relevante" if relevantes >= RELEVANT_SHARE * usados else "reciente"
    elegidos.sort(key=lambda i: (trozos[i][0], trozos[i][1]))
    texto, srcs, raw = _assemble([(trozos[i][0], trozos[i][2]) for i in elegidos], f)
    while int(math.ceil(raw * f)) > presupuesto and elegidos:      # los encabezados juntos
        elegidos.pop()
        texto, srcs, raw = _assemble([(trozos[i][0], trozos[i][2]) for i in elegidos], f)
    return {"level": level, "mode": modo, "text": texto, "sources": srcs,
            "tokens": int(math.ceil(raw * f)), "raw": raw, "budget": presupuesto, "factor": f}


def estimate(level, name, decider_id="rules", tabs=None, question="", options=()):
    """Para el medidor: la MISMA cuenta que build() (y que `v` y el envío):
    → {"tokens", "mode", "total", "budget", "fixed"}. Si todo cabe no hace
    falta rankear; si no, arma el contexto con la pregunta y opciones de
    ahora. `tokens` = el contexto; `fixed` = lo que lleva CADA pregunta aunque
    no lleve contexto (la sobrecarga del decisor, META `overhead_tokens`, + la
    pregunta y sus opciones): lo que se manda y se cobra es tokens + fixed."""
    f = token_factor(decider_id)
    presupuesto = budget(decider_id, question, options, factor=f)
    r = _estimate(level, name, decider_id, tabs, question, options, f, presupuesto)
    r["fixed"] = fixed_tokens(decider_id, question, options, factor=f)
    return r


def fixed_tokens(decider_id, question="", options=(), factor=None):
    """Lo que lleva CADA pregunta aunque no lleve contexto: la sobrecarga del
    decisor (META `overhead_tokens`) + la pregunta y sus opciones."""
    f = factor if factor else token_factor(decider_id)
    return overhead(decider_id) + int(math.ceil(_q_raw(question, options) * f))


def _estimate(level, name, decider_id, tabs, question, options, f, presupuesto):
    if level == "nada":
        return {"tokens": 0, "mode": "vacío", "total": 0, "budget": presupuesto}
    if level == "cerebro":
        a = _agent(name)
        cp = corpus(a["brain"]) if a else None
        total = int(math.ceil(cp["total_raw"] * f)) if cp else 0
        if total <= 0:
            return {"tokens": 0, "mode": "vacío", "total": 0, "budget": presupuesto}
        if total <= presupuesto:
            return {"tokens": total, "mode": "todo", "total": total, "budget": presupuesto}
        ctx = build(level, name, question, options, decider_id, tabs, factor=f)
        return {"tokens": ctx["tokens"], "mode": ctx["mode"], "total": total, "budget": presupuesto}
    try:
        crudas = sources(level, name, tabs)
    except Exception:
        crudas = []
    total = int(math.ceil(sum(raw_tokens(_bloque(lb, tx)) for lb, tx in crudas if tx.strip()) * f))
    if total <= 0:
        return {"tokens": 0, "mode": "vacío", "total": 0, "budget": presupuesto}
    if total <= presupuesto:
        return {"tokens": total, "mode": "todo", "total": total, "budget": presupuesto}
    ctx = build(level, name, question, options, decider_id, tabs, factor=f)
    return {"tokens": ctx["tokens"], "mode": ctx["mode"], "total": total, "budget": presupuesto}


def ask(level, name, question, options, decider_id, tabs=None, timeout_ms=10000, log=True):
    """Decisores → Preguntar con contexto: arma el contexto y pregunta. Si el
    decisor dice que NO CUPO (context_too_large), reintenta con a lo más 0.6×,
    luego 0.4× y 0.25× del primer intento (vuelve a rankear y a llenar) y con
    el factor que el «no cupo» demuestra — hasta 3 reintentos. Se anota UNA
    vez en la bitácora (el resultado final y cuántos intentos llevó).
    → (respuesta de consult + "attempts", "shrunk_to" (tokens del contexto
       que cupo tras recortar, o None), "sent_tokens" (≈ tokens de la PRIMERA
       petición, con el factor final), "ctx_level", "ctx_mode", "ctx_tokens"),
       contexto final)."""
    import decisions as D
    f = token_factor(decider_id)
    q_raw = _q_raw(question, options)
    cap, intentos, primero = None, 0, None
    while True:
        ctx = build(level, name, question, options, decider_id, tabs, cap_raw=cap, factor=f)
        if primero is None:
            primero = ctx["raw"]
        r = D.consult(D.MANUAL, "choice", question, options, ctx["text"], decider=decider_id,
                      timeout_ms=timeout_ms, level="ask", log=False,
                      context_max=len(ctx["text"]) + 1)
        intentos += 1
        if (r.get("ok") or r.get("error") != "context_too_large" or not ctx["text"]
                or intentos > len(SHRINK_STEPS)):
            break
        prueba = proven_factor(decider_id, ctx["raw"] + q_raw)
        if prueba:
            f = max(f, min(FACTOR_RANGE[1] * 2, prueba * 1.05))
        # siempre avanza: ≤ el paso × el PRIMER intento y < el intento anterior
        cap = int(min(primero * SHRINK_STEPS[intentos - 1], ctx["raw"] * 0.95))
        if cap <= 0:
            break
    r["attempts"] = intentos
    r["shrunk_to"] = ctx["tokens"] if (intentos > 1 and r.get("ok")) else None
    r["sent_tokens"] = int(math.ceil((primero + q_raw) * f)) + overhead(decider_id)
    r["ctx_level"], r["ctx_mode"], r["ctx_tokens"] = ctx["level"], ctx["mode"], ctx["tokens"]
    if log:
        r["id"] = D.record(D.MANUAL, "choice", question, options, r, ledger_meta(ctx))
    return r, ctx


def ledger_meta(ctx):
    """Lo ÚNICO que va a la bitácora del contexto: nivel, modo, las fuentes
    (nombres, hasta 50) y los tokens. Nunca el contenido."""
    if not ctx:
        return None
    labels = [lb for lb, _t in ctx.get("sources") or []]
    return {"level": ctx.get("level"), "mode": ctx.get("mode"), "tokens": ctx.get("tokens", 0),
            "sources": labels[:50], "n_sources": len(labels)}


# ── aviso de la nube (una sola vez por decisor) ──────────────────────────────
def needs_cloud_notice(level, decider_id):
    """¿Toca avisar que este nivel manda contenido del cerebro a la nube?"""
    if level not in BRAIN_LEVELS:
        return False
    try:
        import decisions as D
        if D.meta(decider_id).get("local", True):
            return False
        import settings
        return not (settings.get("decisions.notices") or {}).get(decider_id)
    except Exception:
        return False


def mark_cloud_notice(decider_id):
    try:
        import settings
        cur = dict(settings.get("decisions.notices") or {})
        cur[decider_id] = True
        settings.set("decisions.notices", cur)
        return True
    except Exception:
        return False

