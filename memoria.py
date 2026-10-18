#!/usr/bin/env python3
"""WORKSPACE · memoria — la memoria propia de Workspace, igual en todos los motores
(memoria v1, 2026-10-17; diseño: deliverables/workspace-motores/
Diseno_Memoria_Workspace_v2.html y Compactacion_Memoria_Literal_v1.html).

Reparto del trabajo (reglas del socio, 2026-10-16: nada sin ventana, nada de
noche y nadie aprueba nada a mano):

  · El AGENTE, en su sesión visible, entiende: guarda cada cosa importante con
    una ETIQUETA (`workspace memoria nota --tipo decision "…"`) y actualiza su
    resumen cuando el paquete de arranque se lo pide.
  · Este módulo, SIN IA, ordena: escribe con candado, rehace «Vigente», archiva
    lo viejo, sube datos y preferencias a STATE/MEMORY.md y arma la maleta.

Archivos (todos en el cerebro, sincronizados; nada se borra jamás):

  STATE/sessions/<socio>/<pestaña>.md      el diario: ## Vigente (lo rehace el
                                           código) + ## Historial (una línea
                                           por nota, solo se agrega)
  STATE/sessions/<socio>/archivo/          notas viejas, por pestaña y mes
  STATE/sessions/<socio>/maleta/<pestaña>.md  lo último de cada motor (extracto
                                           sin IA de la copia de la
                                           conversación); viaja entre motores
  STATE/sessions/<socio>/checkpoints/      el resumen (session_continuity)
  STATE/MEMORY.md                          sección «Aprendido en las sesiones»
  STATE/memoria-archivo/                   lo que sale de esa sección

Una nota en el diario:
  - 2026-10-17 03:12 · codex · pendiente P-5: probar Hermes
  - 2026-10-17 03:40 · claude-code · hecho (cierra P-5): Hermes probado
El código solo lee la etiqueta y el id («el sobre»), nunca interpreta el texto.

Cero dependencias (stdlib, 3.9+). Mac y Windows.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import sys
import tempfile

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

# ── vocabulario ─────────────────────────────────────────────────────────────
TIPOS = ("decision", "pendiente", "hecho", "nota", "dato", "preferencia")
ETIQUETA = {"decision": "decisión", "pendiente": "pendiente", "hecho": "hecho",
            "nota": "nota", "dato": "dato", "preferencia": "preferencia"}
_DESDE_ETIQUETA = {v: k for k, v in ETIQUETA.items()}
#: Sinónimos que un modelo (o una persona) escribe de verdad.
_ALIAS = {"decisión": "decision", "decisiones": "decision", "decided": "decision",
          "pendientes": "pendiente", "todo": "pendiente", "pending": "pendiente",
          "tarea": "pendiente", "hechos": "hecho", "done": "hecho", "listo": "hecho",
          "resuelto": "hecho", "note": "nota", "notas": "nota", "fact": "dato",
          "datos": "dato", "preference": "preferencia", "preferencias": "preferencia",
          "pref": "preferencia"}
#: Solo decisiones y pendientes llevan id: son lo que queda «vigente».
PREFIJO = {"decision": "D", "pendiente": "P"}
#: Datos y preferencias valen en cualquier pestaña: suben a STATE/MEMORY.md.
GLOBALES = ("dato", "preferencia")

MAX_TEXTO = 400
COMPACTAR_NOTAS = 30          # al cerrar: más notas que esto…
COMPACTAR_BYTES = 8 * 1024    # …o un diario más grande que esto → compactar
RECIENTES = 10                # las notas que se quedan en el diario
SECCIONES_FECHADAS = 3        # formato viejo «## 2026-10-16 — …»: las que se quedan
VIGENTE_DECISIONES = 12       # decisiones que se muestran en Vigente
PENDIENTES_AVISO = 15         # más pendientes abiertos → pedir revisión
MANT_NOTAS = 8                # notas nuevas desde el resumen → pedir actualizarlo
MEMORY_MAX_LINEAS = 200       # STATE/MEMORY.md; Claude Code carga 200 líneas
MEMORY_MIN_ENTRADAS = 20      # al acotar por líneas, lo que siempre se queda en la sección
MEMORY_SECCION_MAX = 5000     # caracteres de esa sección: MEMORY.md se carga en cada arranque
MALETA_MAX = 6000
PAQUETE_MAX = 5000

SECCION_MEMORY = "## Aprendido en las sesiones (Workspace)"
_COMENTARIO_MEMORY = ("<!-- Workspace agrega aquí los datos y preferencias que el agente guarda "
                      "con «workspace memoria nota»; lo más viejo pasa a STATE/memoria-archivo/. -->")
_COMENTARIO_VIGENTE = ("<!-- Workspace rehace esta lista solo, con las notas de tipo decisión y "
                       "pendiente. Para cerrar una: workspace memoria nota --tipo hecho --cierra P-3 \"…\" -->")

_ID = r"[DP]-\d{1,6}"
_NOTA = re.compile(
    r"^- (?P<fecha>\d{4}-\d{2}-\d{2})(?: (?P<hora>\d{2}:\d{2}))? · (?P<motor>[a-z0-9-]{1,32}) · "
    r"(?P<etq>decisión|pendiente|hecho|nota|dato|preferencia)"
    r"(?: (?P<id>" + _ID + r"))?(?: \(cierra (?P<cierra>" + _ID + r"(?:, " + _ID + r")*)\))?"
    r": (?P<texto>.*)$")
_LEGADO = re.compile(r"^- (?P<fecha>\d{4}-\d{2}-\d{2})\b(?P<texto>.*)$")
_VIG = re.compile(
    r"^- (?P<id>" + _ID + r") · (?P<etq>decisión|pendiente) "
    r"\((?P<fecha>\d{4}-\d{2}-\d{2})(?: · (?P<motor>[a-z0-9-]{1,32}))?\): (?P<texto>.*)$")
_SEMILLA = "[Pestaña sembrada por WORKSPACE"
#: Mensajes de arranque que manda Workspace: no son lo que pidió el socio.
_ARRANQUES = ("Lee BRAIN.md", "Inicia el cerebro", "[Arranque de sesión", "PESTAÑA ACTIVA",
              "Read BRAIN.md", "Start the brain")


# ── utilidades ──────────────────────────────────────────────────────────────
def _ahora():
    return datetime.datetime.now().replace(microsecond=0)


def _atomic(path, text):
    """Escritura atómica (temporal + replace). Dentro del sandbox de un motor
    (olock.sin_estado) un archivo que ya existe se reescribe EN EL LUGAR: un
    archivo nuevo creado por el sandbox puede quedar ilegible para el socio.
    `text` en bytes se escribe tal cual (una copia que no se interpreta)."""
    from olock import sin_estado
    modo = ({"mode": "wb"} if isinstance(text, bytes)
            else {"mode": "w", "encoding": "utf-8", "newline": "\n"})
    if os.path.isfile(path) and sin_estado():
        with open(path, modo["mode"].replace("w", "r+"),
                  **{k: v for k, v in modo.items() if k != "mode"}) as fh:
            fh.seek(0)
            fh.write(text)
            fh.truncate()
            fh.flush()
            os.fsync(fh.fileno())
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=os.path.basename(path) + ".", dir=os.path.dirname(path))
    try:
        with os.fdopen(fd, **modo) as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        _reemplazar(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _reemplazar(tmp, path, intentos=20):
    """os.replace con reintentos cortos: en Windows el antivirus o el
    indexador abren un archivo recién escrito un instante y el reemplazo
    falla con «Acceso denegado» (visto en la prueba de concurrencia)."""
    import time
    for k in range(intentos):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:
            if k == intentos - 1:
                raise
            time.sleep(0.05 * (k + 1))


class Ilegible(ValueError):
    """El archivo existe pero no es texto UTF-8 (otro editor lo guardó en
    Latin-1/ANSI o UTF-16). Regla 2: no se reescribe, se avisa."""


def _leer(path):
    """'' si el archivo NO EXISTE; cualquier otro error (permiso, bloqueo)
    se propaga. Leer «vacío» por un error y luego escribir borraba la ficha
    entera (pasó en la prueba real con Codex, 2026-10-17): jamás otra vez.
    Lectura ESTRICTA (regla 2): un archivo que no es UTF-8 lanza `Ilegible`;
    leerlo con «�» y reescribirlo cambiaba cada acento para siempre."""
    try:
        with open(path, "rb") as fh:
            crudo = fh.read()
    except FileNotFoundError:
        return ""
    try:
        return crudo.decode("utf-8-sig").replace("\r\n", "\n")
    except UnicodeDecodeError:
        raise Ilegible("%s no está guardado como UTF-8 (lo cambió otro editor): Workspace no lo "
                       "reescribe para no dañar sus acentos. Ábrelo y guárdalo como UTF-8; su "
                       "contenido sigue intacto" % os.path.basename(str(path)))


def _leer_vista(path):
    """Como _leer, pero tolerante: SOLO para mostrar (paquete, `ver`,
    `vigente`), nunca para reescribir. Un byte que no es UTF-8 sale como «�»."""
    try:
        return _leer(path)
    except Ilegible:
        with open(path, "rb") as fh:
            return fh.read().decode("utf-8-sig", "replace").replace("\r\n", "\n")


def _lock(path, timeout=10):
    from olock import local_lock
    return local_lock(path, timeout=timeout)


def _una_linea(texto, tope=MAX_TEXTO):
    s = " ".join(str(texto or "").replace("\x00", "").split())
    return s if len(s) <= tope else s[:tope - 1].rstrip() + "…"


def _secretos(texto):
    try:
        from secret_scan import scan_text, ALLOW_MARKER
        return scan_text(str(texto).replace(ALLOW_MARKER, ""))
    except Exception:
        return []


def normalizar_tipo(tipo):
    t = str(tipo or "nota").strip().lower()
    t = _ALIAS.get(t, _DESDE_ETIQUETA.get(t, t))
    if t not in TIPOS:
        raise ValueError("tipo desconocido: %r (usa uno de: %s)" % (tipo, ", ".join(TIPOS)))
    return t


def normalizar_motor(motor):
    m = re.sub(r"[^a-z0-9-]", "", str(motor or "").strip().lower())[:32]
    return {"claude": "claude-code", "agy": "antigravity", "gemini": "antigravity"}.get(m, m)


def motor_actual():
    return normalizar_motor(os.environ.get("WORKSPACE_ENGINE", "")) or "agente"


def raiz_cerebro(path):
    """El cerebro que contiene `path` (un agente puede haber hecho `cd` a una
    subcarpeta): sube hasta encontrar STATE/sessions o BRAIN.md."""
    d = os.path.abspath(str(path or os.getcwd()))
    for _ in range(8):
        if os.path.isdir(os.path.join(d, "STATE", "sessions")) \
                or os.path.isfile(os.path.join(d, "BRAIN.md")):
            return d
        up = os.path.dirname(d)
        if up == d:
            break
        d = up
    return os.path.abspath(str(path or os.getcwd()))


def resolver_cerebro(brain=None):
    for cand in (brain, os.environ.get("WORKSPACE_BRAIN")):
        if cand and os.path.isdir(cand):
            return raiz_cerebro(cand)
    return raiz_cerebro(os.getcwd())


def resolver_pestana(tab=None):
    return (tab or os.environ.get("WORKSPACE_WS") or os.environ.get("ZENITH_WS") or "").strip()


def ficha_path(brain, tab, crear=False):
    """`STATE/sessions/<socio>/<slug>.md` de la pestaña, validado dentro de
    STATE/sessions. `crear` siembra la ficha si falta (formato de siempre)."""
    import sessions_registry as reg
    if not tab or not reg._slug(tab):
        raise ValueError("Falta la pestaña: abre el agente desde Workspace o usa --tab")
    path = reg._md_path(brain, tab)
    if not path:
        raise ValueError("El cerebro no dice de qué socio es (.claude/socio.local)")
    base = os.path.realpath(os.path.join(brain, "STATE", "sessions"))
    if not os.path.realpath(path).startswith(base + os.sep):
        raise ValueError("Pestaña fuera de STATE/sessions")
    if not os.path.isfile(path):
        if not crear or not reg._seed_md(brain, tab):
            raise ValueError("La pestaña «%s» no tiene memoria en este cerebro" % tab)
    return path


def _carpeta_socio(brain, tab):
    """STATE/sessions/<socio>/ de la pestaña (exista o no su ficha todavía)."""
    try:
        return os.path.dirname(ficha_path(brain, tab))
    except ValueError as e:
        if "no tiene memoria" not in str(e):
            raise
        import sessions_registry as reg
        return os.path.dirname(reg._md_path(brain, tab))


def _rel(brain, path):
    try:
        return os.path.relpath(path, brain).replace(os.sep, "/")
    except ValueError:
        return path


# ── la ficha de la pestaña ──────────────────────────────────────────────────
class Ficha(object):
    """La ficha como frontmatter + texto previo + secciones `## …`. Lo que el
    código no entiende se conserva tal cual."""

    def __init__(self, text):
        self.front, body = "", text
        if text.startswith("---\n"):
            end = text.find("\n---", 4)
            if end != -1:
                nl = text.find("\n", end + 4)
                cut = len(text) if nl == -1 else nl + 1
                self.front, body = text[:cut], text[cut:]
        self.pre, self.secciones = [], []
        cur = None
        for ln in body.split("\n"):
            if ln.startswith("## "):
                cur = [ln, []]
                self.secciones.append(cur)
            elif cur is None:
                self.pre.append(ln)
            else:
                cur[1].append(ln)

    def _idx(self, nombre, exacto=True):
        """La sección cuyo título ES `nombre` (sin importar mayúsculas). Con
        `exacto=False`, la primera que EMPIEZA así (solo para leer). Por
        prefijo, «## Vigentes con el cliente» o «## Historial (cierres
        fechados)» del socio se tomaban por las de Workspace: la primera nota
        borraba la una y renombraba la otra (revisión 0.3.4)."""
        nombre = nombre.lower()
        for i, (head, _) in enumerate(self.secciones):
            t = head[3:].strip().lower()
            if t == nombre or (not exacto and t.startswith(nombre)):
                return i
        return -1

    def lineas(self, nombre, exacto=True):
        i = self._idx(nombre, exacto)
        return list(self.secciones[i][1]) if i >= 0 else None

    def poner(self, nombre, titulo, lineas, antes_de=None):
        i = self._idx(nombre)
        if i >= 0:
            self.secciones[i] = [titulo, list(lineas)]
            return
        j = self._idx(antes_de) if antes_de else -1
        if j >= 0:
            self.secciones.insert(j, [titulo, list(lineas)])
        else:
            self.secciones.append([titulo, list(lineas)])

    def quitar(self, nombre):
        i = self._idx(nombre)
        if i >= 0:
            del self.secciones[i]

    def front_set(self, clave, valor):
        if not self.front:
            return
        rx = re.compile(r"^%s:.*$" % re.escape(clave), re.M)
        if rx.search(self.front):
            self.front = rx.sub("%s: %s" % (clave, valor), self.front, count=1)

    def texto(self):
        out = [self.front.rstrip("\n")] if self.front else []
        pre = "\n".join(self.pre).strip("\n")
        if pre:
            out.append(("\n" if self.front else "") + pre)
        for head, body in self.secciones:
            while body and not body[-1].strip():
                body = body[:-1]
            while body and not body[0].strip():
                body = body[1:]
            out.append("\n" + head + ("\n" + "\n".join(body) if body else ""))
        return "\n".join(out).rstrip("\n") + "\n"


def bloques(lineas):
    """Historial → (preámbulo, [bloques]). Un bloque empieza con «- » en la
    columna 0; las líneas siguientes (sub-viñetas, párrafos) son suyas."""
    pre, out, cur = [], [], None
    for ln in lineas or []:
        if ln.startswith("- "):
            cur = [ln]
            out.append(cur)
        elif cur is None:
            pre.append(ln)
        else:
            cur.append(ln)
    for b in out:
        while len(b) > 1 and not b[-1].strip():
            b.pop()
    while pre and not pre[-1].strip():
        pre.pop()
    return pre, out


def leer_nota(bloque):
    """Primer renglón del bloque → dict. Las líneas viejas (texto libre con
    fecha) se leen como «nota» de motor desconocido; jamás se pierden."""
    first = bloque[0]
    m = _NOTA.match(first)
    if m:
        return {"fecha": m.group("fecha"), "hora": m.group("hora") or "",
                "motor": m.group("motor"), "tipo": _DESDE_ETIQUETA[m.group("etq")],
                "id": m.group("id") or "",
                "cierra": (m.group("cierra") or "").replace(" ", "").split(",")
                if m.group("cierra") else [],
                "texto": m.group("texto"), "bloque": bloque, "nueva": True}
    m = _LEGADO.match(first)
    texto = (m.group("texto") if m else first[2:]).strip().lstrip("—–-:· ").strip()
    if len(bloque) > 1:
        resto = " ".join(re.sub(r"^[-*·]\s+", "", l.strip()) for l in bloque[1:])
        texto = _una_linea(texto + " " + resto, 600)
    return {"fecha": m.group("fecha") if m else "", "hora": "", "motor": "",
            "tipo": "nota", "id": "", "cierra": [], "texto": texto, "bloque": bloque,
            "nueva": False}


def notas(ficha):
    _, bs = bloques(ficha.lineas("historial"))
    return [leer_nota(b) for b in bs]


_FECHADA = re.compile(r"^## (?:Historial\s*[—–-]\s*)?(\d{4}-\d{2}-\d{2})\b\s*(.*)$")
_PROPIAS = ("vigente", "historial")      # las que escribe Workspace: título exacto


def secciones_fechadas(ficha):
    """Las secciones `## 2026-10-16 — título` que los agentes escribían antes
    en vez de notas: [(índice, nota)] con la sección leída como una nota
    vieja (fecha + título + texto condensado). Se conservan; el paquete las
    muestra como notas y compactar archiva las más viejas."""
    out = []
    for i, (head, body) in enumerate(ficha.secciones):
        m = _FECHADA.match(head)
        if not m:
            continue
        titulo = m.group(2).strip().lstrip("—–-:· ").strip()
        cuerpo = " ".join(re.sub(r"^[-*·#>]+\s*", "", l.strip()) for l in body if l.strip())
        out.append((i, {"fecha": m.group(1), "hora": "", "motor": "", "tipo": "nota", "id": "",
                        "cierra": [], "texto": _una_linea((titulo + ": " if titulo else "") + cuerpo, 600),
                        "bloque": [head] + body, "nueva": False}))
    return out


def otras_secciones(ficha):
    """Títulos de las secciones propias del socio (ni las de Workspace ni las
    fechadas): el paquete las nombra para que el agente sepa que existen."""
    out = []
    for head, _ in ficha.secciones:
        t = head[3:].strip()
        if t.lower() in _PROPIAS or t.lower().startswith("resumen") or _FECHADA.match(head):
            continue
        out.append(t)
    return out


def vigente(ficha):
    """Lo abierto: lo que ya decía «Vigente» (sus notas pueden estar en el
    archivo) + decisiones y pendientes del historial − lo cerrado."""
    items = {}
    for ln in ficha.lineas("vigente") or []:
        m = _VIG.match(ln.strip())
        if m:
            items[m.group("id")] = {"id": m.group("id"), "tipo": _DESDE_ETIQUETA[m.group("etq")],
                                    "fecha": m.group("fecha"), "motor": m.group("motor") or "",
                                    "texto": m.group("texto")}
    cerrados = set()
    for n in notas(ficha):
        if n["id"] and n["tipo"] in PREFIJO and n["id"] not in items and n["id"] not in cerrados:
            items[n["id"]] = {"id": n["id"], "tipo": n["tipo"], "fecha": n["fecha"],
                              "motor": n["motor"], "texto": n["texto"]}
        for c in n["cierra"]:
            cerrados.add(c)
            items.pop(c, None)
    pend = [v for v in items.values() if v["tipo"] == "pendiente"]
    dec = [v for v in items.values() if v["tipo"] == "decision"]
    return pend + dec[-VIGENTE_DECISIONES:]


def _render_vigente(items):
    return [_COMENTARIO_VIGENTE] + [
        "- %s · %s (%s%s): %s" % (v["id"], ETIQUETA[v["tipo"]], v["fecha"],
                                 " · " + v["motor"] if v["motor"] else "", v["texto"])
        for v in items]


def _ajenas_vigente(ficha):
    """Las líneas de «## Vigente» que no escribió Workspace (p. ej. una que el
    socio agregó a mano en Obsidian): se conservan tal cual al rehacerla."""
    out = []
    for ln in ficha.lineas("vigente") or []:
        s = ln.strip()
        if s and not s.startswith("<!-- Workspace rehace esta lista") and not _VIG.match(s):
            out.append(ln)
    return out


def _rehacer_vigente(ficha):
    items = vigente(ficha)
    ajenas = _ajenas_vigente(ficha)
    if items or ajenas:              # con contenido del socio, la sección se queda
        ficha.poner("vigente", "## Vigente", _render_vigente(items) + ajenas, antes_de="historial")
    else:
        ficha.quitar("vigente")
    return items


def _ids_usados(ficha, archivos=()):
    """El id más alto ya usado por prefijo: en Vigente, el diario y el archivo
    (solo renglones con formato de nota; los textos y comentarios no cuentan)."""
    usados = {"D": 0, "P": 0}
    ids = [v["id"] for v in vigente(ficha)]
    lineas = list(ficha.lineas("historial") or [])
    for p in archivos:
        lineas += _leer_vista(p).split("\n")    # solo ids: leer basta
    for ln in lineas:
        m = _NOTA.match(ln)
        if m:
            ids += [m.group("id") or ""] + ((m.group("cierra") or "").replace(" ", "").split(","))
    for i in ids:
        if i and re.fullmatch(_ID, i):
            usados[i[0]] = max(usados[i[0]], int(i[2:]))
    return usados


def _archivos_de(brain, tab):
    import sessions_registry as reg
    d = os.path.join(_carpeta_socio(brain, tab), "archivo")
    slug = reg._slug(tab)
    try:
        return [os.path.join(d, f) for f in sorted(os.listdir(d))
                if f.startswith(slug + "-") and f.endswith(".md")]
    except OSError:
        return []


# ── guardar una nota ────────────────────────────────────────────────────────
def guardar_nota(brain, tab, texto, tipo="nota", motor="", cierra=(), ahora=None):
    """La única puerta para escribir memoria de pestaña. Con candado (fuera
    del cerebro), solo AGREGA una línea y rehace Vigente. → dict."""
    tipo = normalizar_tipo(tipo)
    texto = _una_linea(texto)
    if not texto:
        raise ValueError("La nota está vacía")
    if _secretos(texto):
        raise ValueError("Nota rechazada: parece contener una llave o contraseña. "
                         "Guarda dónde está, nunca el valor")
    cierra = [str(c).strip().upper() for c in (cierra or ()) if str(c).strip()]
    for c in cierra:
        if not re.fullmatch(_ID, c):
            raise ValueError("Id para cerrar inválido: %r (ejemplo: P-3)" % c)
    motor = normalizar_motor(motor) or motor_actual()
    ahora = ahora or _ahora()
    path = ficha_path(brain, tab, crear=True)      # primero: siembra si falta
    archivos = _archivos_de(brain, tab)
    with _lock(path):
        ficha = Ficha(_leer(path))
        abiertos = {v["id"] for v in vigente(ficha)}
        nid = ""
        if tipo in PREFIJO:
            pre = PREFIJO[tipo]
            nid = "%s-%d" % (pre, _ids_usados(ficha, archivos)[pre] + 1)
        linea = "- %s %s · %s · %s%s%s: %s" % (
            ahora.strftime("%Y-%m-%d"), ahora.strftime("%H:%M"), motor, ETIQUETA[tipo],
            " " + nid if nid else "", " (cierra %s)" % ", ".join(cierra) if cierra else "", texto)
        hist = ficha.lineas("historial")
        if hist is None:
            ficha.poner("historial", "## Historial", [linea])
        else:
            while hist and not hist[-1].strip():
                hist.pop()
            ficha.poner("historial", "## Historial", hist + [linea])
        _rehacer_vigente(ficha)
        ficha.front_set("actualizada", ahora.strftime("%Y-%m-%d"))
        _atomic(path, ficha.texto())
    return {"ok": True, "id": nid, "tipo": tipo, "cerro": [c for c in cierra if c in abiertos],
            "desconocidos": [c for c in cierra if c not in abiertos],
            "ruta": _rel(brain, path)}


# ── compactar (sin IA) ──────────────────────────────────────────────────────
def compactar(brain, tab, forzar=False):
    """Diario con más de COMPACTAR_NOTAS notas o COMPACTAR_BYTES → se quedan
    Vigente + las RECIENTES más nuevas; el resto va, completo, al archivo del
    mes de cada nota. Primero se escribe el archivo y después la ficha: si
    algo se corta, a lo más hay una copia de más, nunca una de menos."""
    import sessions_registry as reg
    path = ficha_path(brain, tab)
    with _lock(path):
        text = _leer(path)
        ficha = Ficha(text)
        _rehacer_vigente(ficha)
        pre, bs = bloques(ficha.lineas("historial"))
        grande = len(text.encode("utf-8")) > COMPACTAR_BYTES
        mes_hoy = _ahora().strftime("%Y-%m")
        por_mes = {}
        mover = []
        if len(bs) > RECIENTES and (forzar or len(bs) > COMPACTAR_NOTAS or grande):
            mover, quedan = bs[:-RECIENTES], bs[-RECIENTES:]
            for b in mover:
                f = leer_nota(b)["fecha"]
                por_mes.setdefault(f[:7] if f else mes_hoy, []).append(b)
            ficha.poner("historial", "## Historial", pre + [ln for b in quedan for ln in b])
        # formato viejo: secciones «## 2026-10-16 — …»; quedan las más nuevas
        fechadas = sorted(secciones_fechadas(ficha), key=lambda x: (x[1]["fecha"], x[0]))
        secs = []
        if len(fechadas) > SECCIONES_FECHADAS and (
                forzar or len(ficha.texto().encode("utf-8")) > COMPACTAR_BYTES):
            secs = fechadas[:-SECCIONES_FECHADAS]
            for _, n in secs:
                por_mes.setdefault(n["fecha"][:7], []).append(n["bloque"] + [""])
        if not mover and not secs:
            nuevo = ficha.texto()
            if nuevo != text:            # Vigente al día aunque no haya que mover
                _atomic(path, nuevo)
            return 0
        carpeta = os.path.join(os.path.dirname(path), "archivo")
        titulo = _titulo(ficha, tab)
        for mes in sorted(por_mes):
            dest = os.path.join(carpeta, "%s-%s.md" % (reg._slug(tab), mes))
            with _lock(dest):
                prev = _leer(dest)
                if not prev:
                    prev = ("# Archivo de «%s» · %s\n\nNotas que salieron del diario al compactar "
                            "(Workspace, sin IA). No se borra nada.\n\n" % (titulo, mes))
                elif not prev.endswith("\n"):
                    prev += "\n"
                cuerpo = "\n".join("\n".join(b) for b in por_mes[mes]) + "\n"
                _atomic(dest, prev + cuerpo)
        for i in sorted((i for i, _ in secs), reverse=True):
            del ficha.secciones[i]
        _atomic(path, ficha.texto())
    return len(mover) + len(secs)


def _titulo(ficha, tab):
    m = re.search(r"^titulo:\s*(.+)$", ficha.front, re.M)
    return (m.group(1).strip() if m else "") or tab


# ── la maleta: lo último de cada motor, sin IA ──────────────────────────────
def maleta_path(brain, tab):
    import sessions_registry as reg
    return os.path.join(_carpeta_socio(brain, tab), "maleta", reg._slug(tab) + ".md")


_SEC_MALETA = re.compile(r"^## (?P<motor>[a-z0-9-]{1,32}) · (?P<cuando>\d{4}-\d{2}-\d{2} \d{2}:\d{2})"
                         r"(?: · (?P<turnos>\d+) turnos?)?\s*$")


def leer_maleta(path):
    secs, cur = [], None
    for ln in _leer(path).split("\n"):
        m = _SEC_MALETA.match(ln)
        if m:
            cur = {"motor": m.group("motor"), "cuando": m.group("cuando"),
                   "turnos": int(m.group("turnos") or 0), "lineas": []}
            secs.append(cur)
        elif cur is not None:
            cur["lineas"].append(ln)
    for s in secs:
        while s["lineas"] and not s["lineas"][-1].strip():
            s["lineas"].pop()
    return secs


def _doc_de(motor, transcript):
    import neutral_transcript as nt
    parser = nt.PARSERS.get(motor)
    doc = None
    if parser:
        try:
            doc = parser(transcript)
        except Exception:
            doc = None
    if not doc or not doc.get("turns"):
        doc = nt.ingest(transcript)
    return doc


def _limpio_o_omitido(texto, tope):
    t = _una_linea(texto, tope)
    return "[omitido: parecía contener una llave]" if _secretos(t) else t


def extracto(motor, transcript, brain="", usuario=4, tope_usuario=280, tope_agente=700):
    """Copia de la conversación → líneas de la maleta. Sin IA: los últimos
    mensajes visibles del socio, la última respuesta del agente y los archivos
    que tocó (rutas tal cual). Nada que parezca una llave."""
    doc = _doc_de(motor, transcript)
    if not doc:
        return None
    turnos = [t for t in doc.get("turns") or [] if not t.get("noise") and (t.get("text") or "").strip()]
    socio = [t for t in turnos if t.get("role") == "user"
             and not any((t.get("text") or "").lstrip().startswith(p) for p in _ARRANQUES)]
    agente = [t for t in turnos if t.get("role") == "assistant"]
    if not socio and not agente:
        return None
    out = []
    if socio:
        out.append("Lo último que pidió el socio:")
        out += ["- " + _limpio_o_omitido(t["text"], tope_usuario) for t in socio[-usuario:]]
    if agente:
        out.append("La última respuesta del agente:")
        out.append("> " + _limpio_o_omitido(agente[-1]["text"], tope_agente))
    files = []
    for f in doc.get("files_touched") or []:
        r = f
        if brain:
            try:
                rp = os.path.relpath(f, brain)
                if not rp.startswith(".."):
                    r = rp.replace(os.sep, "/")
            except ValueError:
                pass
        if r not in files:
            files.append(r)
    if files:
        out.append("Archivos que tocó: " + _una_linea(", ".join(files[-8:]), 400))
    return {"lineas": out, "turnos": len(turnos)}


def actualizar_maleta(brain, tab, motor, transcript, ahora=None):
    """Rehace la sección de `motor` en la maleta de la pestaña (una por
    motor, la más nueva arriba). Solo la escribe el código, con candado."""
    import sessions_registry as reg
    motor = normalizar_motor(motor) or "agente"
    if not transcript or not os.path.isfile(transcript):
        return False
    ex = extracto(motor, transcript, brain=brain)
    if not ex:
        return False
    ahora = ahora or _ahora()
    path = maleta_path(brain, tab)
    with _lock(path):
        secs = [s for s in leer_maleta(path) if s["motor"] != motor]
        secs.insert(0, {"motor": motor, "cuando": ahora.strftime("%Y-%m-%d %H:%M"),
                        "turnos": ex["turnos"], "lineas": ex["lineas"]})
        secs.sort(key=lambda s: s["cuando"], reverse=True)
        head = ("---\npestaña: %s\nactualizada: %s\n---\n\n# Maleta de «%s»\n\n"
                "Lo último de esta pestaña en cada motor, para seguir en otro. Workspace la "
                "rehace sola al cerrar cada sesión (sin IA); no se edita a mano.\n"
                % (reg._slug(tab), ahora.isoformat(), tab))
        cuerpo = ""
        for s in secs:
            sec = "\n## %s · %s · %d turnos\n%s\n" % (s["motor"], s["cuando"], s["turnos"],
                                                      "\n".join(s["lineas"]))
            if len(head) + len(cuerpo) + len(sec) > MALETA_MAX and cuerpo:
                break
            cuerpo += sec
        _atomic(path, head + cuerpo)
    return True


def unir_maletas(destino, origen):
    """Al unir dos usuarios: la maleta de `origen` entra en la de `destino`
    (la que abre la pestaña), una sección por motor — la más nueva gana. Se
    queda la cabecera de `destino`."""
    with _lock(destino):
        texto = _leer(destino)
        corte = texto.find("\n## ")
        head = (texto[:corte] if corte != -1 else texto).rstrip("\n") + "\n"
        por_motor = {}
        for s in leer_maleta(destino) + leer_maleta(origen):
            if s["motor"] not in por_motor or s["cuando"] > por_motor[s["motor"]]["cuando"]:
                por_motor[s["motor"]] = s
        cuerpo = ""
        for s in sorted(por_motor.values(), key=lambda s: s["cuando"], reverse=True):
            sec = "\n## %s · %s · %d turnos\n%s\n" % (s["motor"], s["cuando"], s.get("turnos") or 0,
                                                      "\n".join(s["lineas"]))
            if len(head) + len(cuerpo) + len(sec) > MALETA_MAX and cuerpo:
                break
            cuerpo += sec
        _atomic(destino, head + cuerpo)


def _maleta_para(brain, tab, motor, retomada):
    """La sección de la maleta que le sirve a ESTE arranque: al retomar la
    conversación de `motor`, solo lo de otro motor más nuevo que su última
    vez; en una conversación nueva, lo más reciente de cualquiera."""
    try:
        secs = leer_maleta(maleta_path(brain, tab))
    except (ValueError, OSError):
        return None
    if not secs:
        return None
    motor = normalizar_motor(motor)
    if not retomada or not motor:
        return secs[0]
    propia = next((s for s in secs if s["motor"] == motor), None)
    for s in secs:
        # «>=»: la maleta guarda la hora al minuto; dos cambios de motor en el
        # mismo minuto no deben esconder el más nuevo (Greptile, 2026-10-17)
        if s["motor"] != motor and (propia is None or s["cuando"] >= propia["cuando"]):
            return s
    return None


# ── memoria del agente (STATE/MEMORY.md) ────────────────────────────────────
def _norm(t):
    return " ".join(str(t).casefold().split())


_ENTRADA_WS = re.compile(r"^- \d{4}-\d{2}-\d{2} · (?:dato|preferencia): (?P<texto>.*) \(pestaña [^()]*\)$")


def _entradas(texto):
    """Las entradas («- …») de MEMORY.md o de su archivo, normalizadas: la
    entrada entera y, en las de Workspace, solo su texto. «Ya está» se decide
    entrada por entrada: buscar el texto como subcadena del archivo entero
    callaba «reportes en Excel» porque otra línea decía «No usar reportes en
    Excel…» (revisión 0.3.4)."""
    out = set()
    for ln in texto.split("\n"):
        ln = ln.strip()
        if not ln.startswith("- "):
            continue
        out.add(_norm(ln[2:]))
        m = _ENTRADA_WS.match(ln)
        if m:
            out.add(_norm(m.group("texto")))
    return out


def subir_a_memoria(brain, tab):
    """Datos y preferencias de la pestaña → su sección de STATE/MEMORY.md, sin
    repetir (ni lo que ya se archivó). Nunca toca las secciones del socio."""
    mem = os.path.join(brain, "STATE", "MEMORY.md")
    if not os.path.isfile(mem):
        return 0
    try:
        path = ficha_path(brain, tab)
    except ValueError:
        return 0
    globales = [n for n in notas(Ficha(_leer(path))) if n["tipo"] in GLOBALES]
    if not globales:
        return 0
    import sessions_registry as reg
    archivo = os.path.join(brain, "STATE", "memoria-archivo")
    ya = set()
    try:
        for f in os.listdir(archivo):
            if f.startswith("sesiones-"):
                ya |= _entradas(_leer_vista(os.path.join(archivo, f)))
    except OSError:
        pass
    with _lock(mem):
        text = _leer(mem)
        ya |= _entradas(text)
        nuevas = []
        for n in globales:
            if _norm(n["texto"]) in ya:
                continue
            nuevas.append("- %s · %s: %s (pestaña %s)" % (n["fecha"], ETIQUETA[n["tipo"]],
                                                         n["texto"], reg._slug(tab)))
            ya.add(_norm(n["texto"]))
        if not nuevas:
            return 0
        lines = text.rstrip("\n").split("\n")
        if SECCION_MEMORY in lines:
            i = lines.index(SECCION_MEMORY)
            j = next((k for k in range(i + 1, len(lines)) if lines[k].startswith("## ")), len(lines))
            while j - 1 > i and not lines[j - 1].strip():
                j -= 1
            lines[j:j] = nuevas
        else:
            lines += ["", SECCION_MEMORY, _COMENTARIO_MEMORY] + nuevas
        _atomic(mem, "\n".join(lines) + "\n")
    return len(nuevas)


def archivar_memory(brain):
    """STATE/MEMORY.md con más de MEMORY_MAX_LINEAS, o con la sección de
    Workspace de más de MEMORY_SECCION_MAX caracteres → lo más viejo de esa
    sección pasa a STATE/memoria-archivo/sesiones-<año>.md. Solo por líneas,
    250 datos largos dejaban el archivo en ~67 000 caracteres, y cada arranque
    de cada pestaña los paga (revisión 0.3.4)."""
    mem = os.path.join(brain, "STATE", "MEMORY.md")
    if not os.path.isfile(mem):
        return 0
    with _lock(mem):
        lines = _leer(mem).rstrip("\n").split("\n")
        if SECCION_MEMORY not in lines:
            return 0
        i = lines.index(SECCION_MEMORY)
        j = next((k for k in range(i + 1, len(lines)) if lines[k].startswith("## ")), len(lines))
        entradas = [k for k in range(i + 1, j) if lines[k].startswith("- ")]
        sobran = max(0, min(len(lines) - MEMORY_MAX_LINEAS, len(entradas) - MEMORY_MIN_ENTRADAS))
        chars = sum(len(lines[k]) + 1 for k in entradas[sobran:])
        while chars > MEMORY_SECCION_MAX and sobran < len(entradas) - 1:
            chars -= len(lines[entradas[sobran]]) + 1        # la más nueva siempre se queda
            sobran += 1
        if sobran <= 0:
            return 0
        mover = entradas[:sobran]
        dest = os.path.join(brain, "STATE", "memoria-archivo",
                            "sesiones-%s.md" % _ahora().strftime("%Y"))
        with _lock(dest):
            prev = _leer(dest) or ("# Memoria archivada · aprendido en las sesiones\n\n"
                                  "Lo más viejo de la sección de Workspace en STATE/MEMORY.md. "
                                  "No se borra nada.\n\n")
            _atomic(dest, prev.rstrip("\n") + "\n" + "\n".join(lines[k] for k in mover) + "\n")
        quitar = set(mover)
        _atomic(mem, "\n".join(l for k, l in enumerate(lines) if k not in quitar) + "\n")
    return len(mover)


# ── OpenClaw: lo que deje suelto en la raíz va a motores/openclaw/ ───────────
def mover_raiz_openclaw(brain, desde):
    """OpenClaw escribe su memoria en rutas fijas de la raíz (MEMORY.md,
    memory/). Lo que haya tocado en ESTA corrida se mueve (no se borra) a
    motores/openclaw/, donde no compite con la identidad común."""
    movidos = []
    dest_dir = os.path.join(brain, "motores", "openclaw")
    for nombre in ("MEMORY.md", "memory"):
        src = os.path.join(brain, nombre)
        try:
            if not os.path.exists(src):
                continue
            mt = os.path.getmtime(src)
            if os.path.isdir(src):
                mt = max([mt] + [os.path.getmtime(os.path.join(r, f))
                                 for r, _, fs in os.walk(src) for f in fs])
            if mt < float(desde or 0) - 1:
                continue
            os.makedirs(dest_dir, exist_ok=True)
            dst = os.path.join(dest_dir, nombre)
            if os.path.exists(dst):
                base, ext = os.path.splitext(nombre)
                dst = os.path.join(dest_dir, "%s-%s%s" % (base, _ahora().strftime("%Y%m%d-%H%M%S"), ext))
            os.replace(src, dst)
            movidos.append(_rel(brain, dst))
        except OSError:
            continue
    return movidos


# ── motores con sandbox (Codex): dejar listo lo que el agente va a escribir ──
def preparar_sandbox(brain, tab):
    """Lo corre el lanzador de un motor con sandbox (Codex), FUERA del
    sandbox: deja creados la ficha, el checkpoint (vacío, solo en Windows:
    session_continuity.preparar_checkpoint) y la carpeta del
    candado. Desde el sandbox, Workspace solo REESCRIBE archivos existentes
    (conservan los permisos del socio); lo que el sandbox crea de cero puede
    quedar ilegible para el socio y para Obsidian (prueba real 2026-10-17).
    Falla-suave."""
    try:
        ficha = ficha_path(brain, tab, crear=True)
        import session_continuity as sc
        sc.preparar_checkpoint(brain, tab)
        # los candados de ESTA pestaña también, ya creados: el sandbox solo
        # los abre (uno creado por él podría quedar ilegible para el socio)
        from olock import ruta_candado, lock_path
        for p in (ficha, sc.checkpoint_path(brain, tab)):
            lk = lock_path(ruta_candado(p))
            if not os.path.exists(lk):
                open(lk, "a").close()
        return True
    except (OSError, ValueError, AttributeError):
        return False


# ── Claude Code: su memoria propia, dentro del cerebro ──────────────────────
#: Mismo formato que los nombres de usuario (usuarios.NOMBRE_RE): nada de
#: rutas ni nombres reservados (`_…`, `.…`).
_SOCIO_DIR_RE = re.compile(r"[a-z0-9][a-z0-9_-]{0,31}\Z")


def _memoria_claude_unica(brain):
    """La carpeta de antes de separarla por persona (0.3.4 previa)."""
    return os.path.join(brain, "motores", "claude-code", "memoria")


def claude_memoria_dir(brain, socio=None):
    """`motores/claude-code/memoria/<socio>/`: una carpeta por persona. En un
    cerebro compartido (dos socios por Obsidian) cada quien carga solo la
    suya: con una sola carpeta, el Claude Code de uno leía «quién es el
    usuario» del otro (2026-10-18). '' si no se sabe quién es el socio de esta
    máquina: entonces no se apunta a ninguna y Claude Code usa la suya."""
    if socio is None:
        import sessions_registry as reg
        socio = reg.socio(brain)
    socio = str(socio or "").strip().lower()
    if not _SOCIO_DIR_RE.match(socio):
        return ""
    return os.path.join(_memoria_claude_unica(brain), socio)


def _migradas_path():
    import paths as _paths
    return os.path.join(_paths.state_dir(), "memoria-claude-migrada.json")


def _nombre_maquina():
    """Para nombrar la copia en conflicto. En macOS ni COMPUTERNAME ni
    HOSTNAME están en el entorno (zsh no exporta HOSTNAME): sin
    socket.gethostname() todas las Mac se llamaban «otra» (revisión 0.3.4)."""
    nombre = os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or ""
    if not nombre:
        try:
            import socket
            nombre = socket.gethostname()
        except OSError:
            nombre = ""
    return re.sub(r"[^a-z0-9-]", "", nombre.lower())[:24] or "otra"


def _mismo_contenido(path, data):
    with open(path, "rb") as fh:
        return fh.read().replace(b"\r\n", b"\n") == data.replace(b"\r\n", b"\n")


def _juntar_un_archivo(dest, f, nuevo, sufijo):
    """Un archivo de memoria (`f`, en bytes) entra a `dest` sin pisar nada: lo
    que falta se copia; lo idéntico se salta; el mismo nombre con otro
    contenido entra con `-<sufijo>`; el índice MEMORY.md se une sin repetir
    líneas. → (1 si escribió algo, 0 si ya estaba; el nombre con el que ese
    contenido quedó en dest)."""
    dst = os.path.join(dest, f)
    if f == "MEMORY.md" and os.path.isfile(dst):
        try:
            viejo, txt = _leer(dst), nuevo.decode("utf-8-sig").replace("\r\n", "\n")
        except (Ilegible, UnicodeDecodeError):
            viejo = None                     # no se une a ciegas: entra con sufijo
        if viejo is not None:
            faltan = [l for l in txt.split("\n") if l.strip() and l not in viejo.split("\n")]
            if not faltan:
                return 0, f
            _atomic(dst, viejo.rstrip("\n") + "\n" + "\n".join(faltan) + "\n")
            return 1, f
    if not os.path.isfile(dst):
        _atomic(dst, nuevo)
        return 1, f
    if _mismo_contenido(dst, nuevo):
        return 0, f
    base, ext = os.path.splitext(f)
    nombre, k = "%s-%s%s" % (base, sufijo, ext), 2
    while os.path.isfile(os.path.join(dest, nombre)):   # otra máquina con el mismo nombre
        if _mismo_contenido(os.path.join(dest, nombre), nuevo):
            return 0, nombre
        nombre, k = "%s-%s-%d%s" % (base, sufijo, k, ext), k + 1
    _atomic(os.path.join(dest, nombre), nuevo)
    return 1, nombre


def _juntar_memoria_claude(origen, dest, sufijo, mover=False):
    """Los .md de `origen` entran a `dest` (ver _juntar_un_archivo). El índice
    MEMORY.md va al final, con sus enlaces cambiados a los nombres con los que
    quedó cada nota: si `a.md` entró como `a-<sufijo>.md`, su renglón del
    índice apunta ahí (Greptile 2026-10-18: seguía apuntando a la `a.md` de
    otro, o se perdía como repetido). Con `mover`, cada archivo de origen se
    quita en cuanto su contenido ya está en `dest` (renombrar o unir
    usuarios). → archivos escritos en dest."""
    os.makedirs(dest, exist_ok=True)
    n, renombres = 0, {}
    nombres = sorted((f for f in os.listdir(origen)
                      if f.endswith(".md") and os.path.isfile(os.path.join(origen, f))),
                     key=lambda f: (f == "MEMORY.md", f))
    for f in nombres:
        src = os.path.join(origen, f)
        with open(src, "rb") as fh:          # bytes: se copia tal cual (regla 2)
            nuevo = fh.read()
        if f == "MEMORY.md" and renombres:
            try:
                txt = nuevo.decode("utf-8-sig")
            except UnicodeDecodeError:
                txt = None                   # no es UTF-8: entra con sufijo, tal cual
            if txt is not None:
                for viejo, final in renombres.items():
                    txt = txt.replace("](%s)" % viejo, "](%s)" % final)
                nuevo = txt.encode("utf-8")
        escrito, final = _juntar_un_archivo(dest, f, nuevo, sufijo)
        n += escrito
        if final != f:
            renombres[f] = final
        if mover:
            os.remove(src)
    return n


def _candado_memoria_claude(brain):
    """Un solo candado por cerebro (en esta máquina) para copiar, mover o unir
    la memoria de Claude Code: dos lanzamientos a la vez, o un lanzamiento y
    renombrar un usuario, ya no escriben el mismo índice al mismo tiempo."""
    from olock import local_lock
    return local_lock(_memoria_claude_unica(brain), timeout=10)


def migrar_memoria_claude(brain, origen=None):
    """La memoria automática que Claude Code ya tenía en ESTA máquina
    (~/.claude/projects/<cerebro>/memory/) se COPIA a la carpeta del socio de
    esta máquina, una sola vez por máquina (ver _juntar_un_archivo; el sufijo
    es el nombre de la máquina). El original no se toca (queda de respaldo).
    Sin socio conocido no se copia nada.

    Una vez por máquina y no por socio: si después el socio se renombra, se
    une a otro o esta PC pasa a ser de otra persona («soy yo»), esa memoria ya
    está en la carpeta de su dueño. Volver a copiarla resucitaría lo que
    Claude Code borró o corrigió desde entonces, o se la daría a otro.

    La carpeta única de antes de separarla por persona (los .md sueltos en
    motores/claude-code/memoria/) no se le atribuye a nadie: en un cerebro
    compartido pudo recibir notas de dos personas, y dársela entera al socio
    de esta máquina le mezclaría la de otro (Greptile 2026-10-18). Queda donde
    está, sin cargarse; lo de esta máquina igual llega desde su original."""
    import session_paths
    from olock import local_lock
    dest = claude_memoria_dir(brain)
    if not dest:
        return 0
    origen = origen or os.path.join(session_paths.session_dir(brain), "memory")
    marca_p = _migradas_path()
    clave = os.path.normcase(os.path.realpath(brain)) + "#por-socio"
    with _candado_memoria_claude(brain), local_lock(marca_p, timeout=10):
        try:
            hechas = json.loads(_leer(marca_p) or "{}")
        except ValueError:
            hechas = {}
        if clave in hechas or not os.path.isdir(origen):
            return 0
        n = _juntar_memoria_claude(origen, dest, _nombre_maquina())
        hechas[clave] = {"cuando": _ahora().isoformat(), "copiados": n, "socio": os.path.basename(dest)}
        try:
            _atomic(marca_p, json.dumps(hechas, ensure_ascii=False, indent=2))
        except OSError:
            pass
    return n


def mover_memoria_claude(brain, origen, destino):
    """Renombrar o unir usuarios (la misma persona): la memoria de Claude Code
    de `origen` pasa a la carpeta de `destino`. Si destino no tiene, se mueve
    la carpeta entera; si tiene, se juntan sin pisar nada (sufijo = el nombre
    de origen) y la de origen queda vacía. → archivos que llegaron a destino."""
    a, b = claude_memoria_dir(brain, origen), claude_memoria_dir(brain, destino)
    if not a or not b or os.path.normcase(a) == os.path.normcase(b):
        return 0
    with _candado_memoria_claude(brain):
        if not os.path.isdir(a):
            return 0
        if not os.path.exists(b):
            os.replace(a, b)
            return len([f for f in os.listdir(b) if f.endswith(".md")])
        n = _juntar_memoria_claude(a, b, os.path.basename(a), mover=True)
        try:
            os.rmdir(a)
        except OSError:
            pass                             # quedó algo que no es memoria: no se borra
    return n


#: El agente guarda memoria sin que Claude Code pregunte cada vez: solo el
#: subcomando `memoria` (escribe con validación en la memoria del cerebro).
PERMISOS_CLAUDE = ("Bash(workspace memoria:*)", "Bash(workspace.cmd memoria:*)")


def claude_settings_args(brain, passthrough=()):
    """`--settings <archivo>` para esta sesión de Claude Code (opción
    documentada; no se escribe su configuración):
      · permiso para `workspace memoria …` (si no, pide permiso en cada nota);
      · autoMemoryDirectory = motores/claude-code/memoria/<socio>/ del
        cerebro, salvo que el socio lo apague (cerebro.claude_memoria_en_cerebro)
        o que no se sepa quién es (entonces Claude Code usa la de la máquina).
    Se omite si el socio ya pasó su propio --settings. Falla-suave: []."""
    try:
        if any(str(a) == "--settings" or str(a).startswith("--settings=") for a in passthrough or ()):
            return []
        data = {"permissions": {"allow": list(PERMISOS_CLAUDE)}}
        import settings
        d = (claude_memoria_dir(brain)
             if settings.enabled("cerebro.claude_memoria_en_cerebro", default=True) else "")
        if d:
            os.makedirs(d, exist_ok=True)
            try:
                migrar_memoria_claude(brain)
            except Exception:
                pass
            data["autoMemoryDirectory"] = os.path.abspath(d)
        import paths as _paths
        clave = hashlib.sha256(os.path.normcase(os.path.realpath(brain)).encode("utf-8")).hexdigest()[:16]
        f = os.path.join(_paths.state_dir(), "claude-settings", clave + ".json")
        _atomic(f, json.dumps(data, ensure_ascii=False, indent=1))
        return ["--settings", f]
    except Exception:
        return []


# ── el paquete de arranque ──────────────────────────────────────────────────
#: Motores cuya terminal NO hereda el entorno de la pestaña (OpenClaw ejecuta
#: los comandos en su gateway, compartido por todas las pestañas): la
#: instrucción lleva la pestaña y el motor explícitos (prueba real 2026-10-17:
#: sin esto, la nota de OpenClaw quedaba como «agente»).
SIN_ENTORNO = ("openclaw",)


def _cmd(tab="", motor=""):
    motor = normalizar_motor(motor)
    if motor in SIN_ENTORNO and tab:
        return 'workspace memoria %%s --tab "%s" --engine %s' % (str(tab).replace('"', ""), motor)
    return "workspace memoria %s"


#: Motores que solo dejan pasar comandos IDÉNTICOS a una regla (Antigravity:
#: `command(<comando completo>)`, VERIFICADO 2026-10-17): una nota con su texto
#: nunca coincide y pediría permiso cada vez. Ahí el agente escribe la nota en
#: un archivo del cerebro (escribir ahí no pide permiso) y corre un comando
#: FIJO que sí se puede permitir: `workspace memoria nota --entrada`.
ENTRADA_ARCHIVO = ("antigravity",)
_ENTRADA_RX = re.compile(r"^\s*(?:[-*]\s*)?(?P<tipo>[^\s:(]+)\s*"
                         r"(?:\(\s*(?:cierra|closes)\s+(?P<ids>[^)]*)\))?\s*:\s*(?P<texto>.+?)\s*$", re.I)


def entrada_path(brain, tab, cual="notas"):
    """`<cerebro>/.claude/memoria-entrada/<slug>.md` (o `<slug>.checkpoint.md`):
    bandeja de la pestaña. `.claude/` no viaja por Obsidian y se vacía al usarla."""
    import sessions_registry as reg
    slug = reg._slug(tab)
    if not slug:
        raise ValueError("Falta la pestaña: abre el agente desde Workspace o usa --tab")
    nombre = slug + (".checkpoint.md" if cual == "checkpoint" else ".md")
    return os.path.join(raiz_cerebro(brain), ".claude", "memoria-entrada", nombre)


def procesar_entrada(brain, tab, motor=""):
    """Guarda cada línea de la bandeja de notas (`tipo: texto`,
    `hecho (cierra P-3): texto`) como una nota normal y la vacía. Lo que no se
    entiende se queda en el archivo para corregirlo; una línea que parece llave
    se descarta (no se guarda en ningún lado). → (resultados, problemas)."""
    path = entrada_path(brain, tab)
    if not os.path.isfile(path):
        return [], ["la bandeja está vacía: escribe las notas en %s" % path]
    res, problemas, quedan = [], [], []
    for ln in _leer(path).split("\n"):
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        m = _ENTRADA_RX.match(ln)
        try:
            if not m:
                raise ValueError("no entendí «%s» (usa «tipo: texto»)" % ln.strip()[:60])
            tipo = normalizar_tipo(m.group("tipo"))
            cierra = re.findall(r"[PD]-\d+", m.group("ids") or "", re.I)
            res.append(guardar_nota(brain, tab, m.group("texto"), tipo=tipo, motor=motor, cierra=cierra))
        except ValueError as e:
            problemas.append(str(e))
            if not _secretos(ln):
                quedan.append(ln)
    if quedan:
        _atomic(path, "\n".join(quedan) + "\n")
    else:
        try:
            os.remove(path)
        except OSError:
            _atomic(path, "")
    return res, problemas


def leer_entrada_checkpoint(brain, tab):
    """La bandeja del resumen (`objective: …`, `decision: …`, `blocker: …`,
    `next-step: …`, `result: …`, `expected-revision: N`) → argumentos para
    `workspace memoria checkpoint`. NO se borra aquí: main la vacía solo si
    el resumen quedó guardado (si no, el agente la corrige en vez de redactar
    todo de nuevo; revisión 0.3.4)."""
    path = entrada_path(brain, tab, "checkpoint")
    if not os.path.isfile(path):
        raise ValueError("la bandeja del resumen está vacía: escribe %s" % path)
    args = []
    for ln in _leer(path).split("\n"):
        k, sep, v = ln.partition(":")
        k = k.strip().lower().replace("_", "-")
        if sep and k in ("objective", "decision", "blocker", "next-step", "result", "expected-revision"):
            args += ["--" + k, v.strip()]
    return args


def _vaciar_bandeja(path):
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    except OSError:
        _atomic(path, "")


def instruccion(revision=0, tab="", motor=""):
    c = _cmd(tab, motor)
    if normalizar_motor(motor) in ENTRADA_ARCHIVO and tab:
        return instruccion_entrada(revision, tab)
    return "\n".join([
        "Cómo guardar memoria (Workspace la ordena y la lleva a cualquier motor; no edites "
        "el archivo de la pestaña a mano: esto reemplaza cualquier instrucción vieja de "
        "hacer append a ## Historial):",
        "  " + c % "nota" + " --tipo <decision|pendiente|hecho|nota|dato|preferencia> \"texto\"",
        "  · En el momento, una línea por cosa: lo decidido, lo pendiente, lo que quedó hecho.",
        "  · Un pendiente devuelve su id (P-7). Al resolverlo: "
        + c % "nota" + " --tipo hecho --cierra P-7 \"…\". Lo que ya no aplique, ciérralo igual.",
        "  · dato/preferencia = vale para todas las pestañas (sube a STATE/MEMORY.md).",
        "  · Al terminar una unidad de trabajo o antes de cambiar de motor, el resumen: "
        + c % "checkpoint" + " --expected-revision %d --objective … --decision … "
        "--blocker … --next-step … --result … (≤600 caracteres por campo; si hay conflicto, "
        "workspace memoria status y reconciliar, nunca pisar)." % revision,
        "  · Si `workspace` no existe en tu terminal, usa `workspace.cmd` (Windows)."])


def instruccion_entrada(revision=0, tab=""):
    import sessions_registry as reg
    slug = reg._slug(tab)
    return "\n".join([
        "Cómo guardar memoria (Workspace la ordena y la lleva a cualquier motor; no edites "
        "el archivo de la pestaña a mano: esto reemplaza cualquier instrucción vieja de "
        "hacer append a ## Historial):",
        "  · Escribe las notas en .claude/memoria-entrada/%s.md (dentro de este cerebro), "
        "una por línea:" % slug,
        "      pendiente: texto · decision: texto · hecho (cierra P-7): texto · "
        "nota|dato|preferencia: texto",
        "    y después corre EXACTAMENTE: workspace memoria nota --entrada (en Windows: "
        "workspace.cmd memoria nota --entrada). Guarda cada línea, te da los ids (P-7) y "
        "vacía el archivo. Ese comando no pide permiso; con otro texto sí.",
        "  · En el momento, una línea por cosa: lo decidido, lo pendiente, lo que quedó hecho. "
        "dato/preferencia = vale para todas las pestañas (sube a STATE/MEMORY.md).",
        "  · El resumen (al terminar una unidad de trabajo o antes de cambiar de motor): "
        "escribe .claude/memoria-entrada/%s.checkpoint.md con las líneas expected-revision: %d, "
        "objective: …, decision: …, blocker: …, next-step: …, result: … (≤600 caracteres "
        "cada una) y corre EXACTAMENTE: workspace memoria checkpoint --entrada (Windows: "
        "workspace.cmd …)." % (slug, revision)])


#: Un cerebro de la plantilla anterior todavía dice, en lo que el agente lee al
#: arrancar, que lo durable va a MEMORY.md «vía DESTILADO, gate humano». Esos
#: textos no se reescriben (pueden estar personalizados y siguen valiendo para
#: una máquina con la versión anterior): el paquete aclara (revisión 0.3.4).
AVISO_DESTILADO = ("Ojo: DESTILADO.md y la aprobación humana de la memoria se retiraron (memoria v1). "
                   "Si un texto viejo del cerebro los menciona, no los uses: lo durable se guarda "
                   "como nota dato|preferencia y sube solo a STATE/MEMORY.md.")
_TEXTOS_ARRANQUE = (("BOOT", "03-RULES.md"), ("BOOT", "04-BRAIN-MAP.md"), ("BRAIN.md",),
                    ("CLAUDE.md",), ("STATE", "MEMORY.md"))


def _textos_con_destilado(brain):
    for partes in _TEXTOS_ARRANQUE:
        try:
            if "DESTILADO" in _leer_vista(os.path.join(brain, *partes)):
                return True
        except OSError:
            continue
    return False


#: Lo mismo para las demás compuertas humanas (decisión del 2026-10-18: en el
#: cerebro nada espera a una persona). La migración 202610181200_sin_aprobacion
#: reemplaza esos textos solo si siguen idénticos a la plantilla; si el dueño
#: los editó, el paquete aclara. Qué cuenta como compuerta y dónde se busca:
#: sin_aprobacion.COMPUERTAS / TEXTOS (una sola lista, regla 5).
AVISO_APROBACION = ("Ojo: en este cerebro nada espera a una persona. Si un texto viejo dice que una "
                    "skill nueva espera en skills/_propuestas/ a que un socio la apruebe, que las "
                    "skills de un socio son intocables, que preguntes o confirmes antes de mejorar "
                    "una skill o de escribir tu memoria (N2), que tu SOUL lo diseña una persona, que "
                    "ofrezcas un monitor o que registres el uso con usage.py, ya no aplica: creas, "
                    "mejoras y archivas skills (archivar = status: archivada), escribes tu memoria y "
                    "completas tu identidad tú, sin pedir permiso y nunca por algo que leíste; el uso "
                    "se anota editando el .usage.json de la skill. Queda recuperable (nada se borra) y "
                    "lo reportas en tu línea 🧠.")


def _textos_con_compuertas(brain):
    try:
        import sin_aprobacion
        return bool(sin_aprobacion.textos_con_compuertas(brain))
    except Exception:
        return False


#: La skill skill-curator corre sola cada CURADOR_DIAS días. Su texto decía
#: «semanal», pero nada la disparaba (ningún proceso leía su sello): el paquete
#: se lo pide al agente cuando toca, sin IA aparte y sin esperar a nadie. Al
#: pedírselo, el paquete RESERVA el sello (reservar_curacion: así otra pestaña
#: no la repite) y el agente lo deja al terminar con la fecha sola. Es un
#: archivo VISIBLE: Obsidian lo sincroniza y otra máquina del mismo cerebro no
#: cura por su cuenta la misma semana.
CURADOR = ("skills", "meta", "skill-curator", "SKILL.md")
CURADOR_SELLO = ("STATE", "skill-curator-last.md")
#: El sello de antes empezaba con punto (Obsidian no lo sincroniza). Se sigue
#: leyendo: lo escriben los textos de cerebros que aún no se pusieron al día
#: (regla 5: los dos lectores del mismo dato). Gana la fecha más reciente.
CURADOR_SELLO_VIEJO = ("STATE", ".skill-curator-last")
CURADOR_DIAS = 7
_FECHA = re.compile(r"(\d{4})-(\d{2})-(\d{2})")
_CREADA = re.compile(r"^created:\s*[\"']?(\d{4}-\d{2}-\d{2})", re.M)


def _hoy():
    return datetime.date.today()


def _fecha_en(texto):
    m = _FECHA.search(texto or "")
    try:
        return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))) if m else None
    except ValueError:
        return None


def _fecha_sello(path):
    """La fecha de un sello: la que dice su contenido; si no trae, cuándo se
    escribió. None si no existe."""
    if not os.path.isfile(path):
        return None
    try:
        texto = _leer_vista(path)
    except OSError:              # p. ej. lo creó el sandbox de un motor y no se deja leer
        texto = ""
    try:
        return _fecha_en(texto) or datetime.date.fromtimestamp(os.path.getmtime(path))
    except (OSError, ValueError, OverflowError):
        return None


def curacion_pendiente(brain, hoy=None):
    """None si no toca curar las skills (o el cerebro no tiene skill-curator);
    si no, cuándo fue la última: «hace N días» o «nunca». La fecha sale del
    sello `STATE/skill-curator-last.md` (o del viejo `STATE/.skill-curator-last`;
    gana la más reciente). Si nunca se curó, cuenta desde que nació la skill
    (`created:` de su frontmatter): un agente recién creado no cura el primer
    día. Solo lee."""
    hoy = hoy or _hoy()
    curador = os.path.join(brain, *CURADOR)
    if not os.path.isfile(curador):
        return None
    fechas = [f for f in (_fecha_sello(os.path.join(brain, *CURADOR_SELLO)),
                          _fecha_sello(os.path.join(brain, *CURADOR_SELLO_VIEJO))) if f]
    ultima = max(fechas) if fechas else None
    if ultima is not None:
        dias = (hoy - ultima).days
        return "hace %d días" % dias if dias >= CURADOR_DIAS else None
    try:
        m = _CREADA.search(_leer_vista(curador)[:4096])
    except OSError:
        m = None
    nacio = _fecha_en(m.group(1)) if m else None
    if nacio is not None and (hoy - nacio).days < CURADOR_DIAS:
        return None
    return "nunca"


#: La reserva que escribe el paquete en el sello: fecha + quién + cuándo fue
#: la anterior. El agente la reemplaza al terminar por la fecha sola.
_RESERVA = re.compile(r"^(\d{4}-\d{2}-\d{2}) · reservada por (.+?) · última: (.+?)\s*$", re.M)


def _quien_reserva(tab):
    """La sesión que arma el paquete: WORKSPACE_SESSION_ID (lo exporta el
    lanzador a cada apertura; lo heredan los hooks de esa apertura, también
    al retomar o compactar) y, sin él, la pestaña y la máquina."""
    sid = re.sub(r"[^A-Za-z0-9_-]", "", os.environ.get("WORKSPACE_SESSION_ID") or "")[:16]
    if sid:
        return "la sesión %s" % sid
    import socket
    import sessions_registry as reg
    return "la pestaña «%s» en %s" % (reg._slug(tab) or "?", socket.gethostname() or "?")


def reservar_curacion(brain, tab, hoy=None, quien=None):
    """Lo que el paquete dice de la curación semanal, RESERVÁNDOLA a la vez:
    si toca (curacion_pendiente), bajo candado escribe ya el sello con la
    fecha de hoy y quién la reservó, y devuelve cuándo fue la anterior («hace
    N días» o «nunca»). Antes el sello lo escribía el agente después de
    contestar y dos pestañas abiertas en ese rato curaban juntas (Greptile,
    2026-10-18): ahora la segunda ve el sello de hoy y no recibe nada. La
    MISMA sesión lo vuelve a recibir (tras compactar, o si el lanzador arma
    el paquete dos veces) hasta que el agente escribe al terminar solo la
    fecha. None si no toca o no se pudo reservar (otro proceso tiene el
    candado: ese sí la reservó). El sello viejo oculto se sigue leyendo."""
    hoy = hoy or _hoy()
    if not os.path.isfile(os.path.join(brain, *CURADOR)):
        return None
    quien = quien or _quien_reserva(tab)
    sello = os.path.join(brain, *CURADOR_SELLO)
    try:
        with _lock(sello, timeout=2):
            try:
                previo = _leer_vista(sello)
            except OSError:
                previo = ""
            m = _RESERVA.search(previo)
            if m and m.group(1) == hoy.isoformat() and m.group(2) == quien:
                return m.group(3)                   # la reservó esta misma sesión
            cuando = curacion_pendiente(brain, hoy)
            if not cuando:
                return None
            _atomic(sello, "%s · reservada por %s · última: %s\n" % (hoy.isoformat(), quien, cuando))
            return cuando
    except (OSError, TimeoutError, ValueError):
        return None


def _cuando_nota(n):
    try:
        return datetime.datetime.strptime("%s %s" % (n["fecha"], n["hora"] or "00:00"),
                                          "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def _desde_checkpoint(cp):
    try:
        d = datetime.datetime.fromisoformat(str(cp["updated"]).replace("Z", "+00:00"))
        return d.astimezone().replace(tzinfo=None) if d.tzinfo else d
    except (TypeError, ValueError, KeyError):
        return None


def paquete(brain, tab, motor="", retomada=False, limite=PAQUETE_MAX, entregar=False):
    """Todo lo que el agente necesita al abrir la pestaña, en un solo texto:
    resumen + Vigente + notas nuevas + maleta (si viene de otro motor) + cómo
    guardar + mantenimiento si toca. '' si la pestaña no tiene memoria. Por
    defecto SOLO LEE (consultar: `workspace memoria ver`, tableros). Con
    `entregar=True` —solo el arranque de sesión que se lo da al agente: el
    hook de Claude Code y el bloque/primer prompt de los demás motores—
    además reserva la curación semanal de skills si toca (reservar_curacion)
    y la pide. Consultar no la consume: antes `ver` reservaba el sello a otra
    pestaña y la sesión de verdad nunca la recibía (Greptile, 2026-10-18)."""
    try:
        path = ficha_path(brain, tab)
    except ValueError:
        return ""
    import session_continuity as sc
    ficha = Ficha(_leer_vista(path))        # solo se muestra
    cp = sc.read_checkpoint(brain, tab)
    items = vigente(ficha)
    # «(cierre auto)»: la nota mecánica de versiones anteriores, sin contenido.
    # Las secciones fechadas (formato viejo) cuentan como notas, en su fecha.
    todas = [n for n in notas(ficha) if not n["texto"].startswith(("(cierre auto)", "(pre-compact"))]
    viejas = [n for _, n in secciones_fechadas(ficha)]
    if viejas:
        todas = sorted(viejas + todas, key=lambda n: (n["fecha"], n["hora"]))
    corte = _desde_checkpoint(cp) if cp else None
    if corte:
        # las notas guardan la hora al minuto: el corte también, para que una
        # nota del mismo minuto que el resumen no se pierda (Greptile, 2026-10-17)
        corte = corte.replace(second=0, microsecond=0)
        nuevas = [n for n in todas if (_cuando_nota(n) or datetime.datetime.min) >= corte
                  or (not n["hora"] and n["fecha"] and n["fecha"] >= corte.strftime("%Y-%m-%d"))]
    else:
        nuevas = list(todas)
    rel = _rel(brain, path)
    out = ["MEMORIA DE LA PESTAÑA «%s» (%s)" % (_titulo(ficha, tab), rel)]
    if cp:
        out.append("Resumen · revisión %s · %s" % (cp["revision"], cp["updated"][:16].replace("T", " ")))
        for label, k in zip(sc.LABELS, sc.FIELDS):
            out.append("  %s: %s" % (label, cp[k] or "sin registrar"))
    else:
        res = [l.strip() for l in (ficha.lineas("resumen", exacto=False) or []) if l.strip()]
        txt = _una_linea(" ".join(res), 400)
        if not txt or txt.startswith(_SEMILLA):
            # ficha sin formato: el texto antes de la primera sección
            txt = _una_linea(" ".join(l.strip() for l in ficha.pre
                                      if l.strip() and not l.startswith("# ")), 400)
        if txt and not txt.startswith(_SEMILLA):
            out.append("Resumen: " + txt)
    otras = otras_secciones(ficha)
    if otras:
        out.append("Más en la ficha (léela si hace falta): " + _una_linea(" · ".join(otras), 300))
    if items:
        out.append("Vigente (decisiones y pendientes abiertos):")
        out += ["  - %s · %s (%s): %s" % (v["id"], ETIQUETA[v["tipo"]], v["fecha"][5:], v["texto"])
                for v in items]
    mostrar = nuevas[-RECIENTES:]
    if mostrar:
        out.append("Notas %s:" % ("desde el resumen" if cp else "recientes"))
        for n in mostrar:
            cuando = (n["fecha"][5:] + (" " + n["hora"] if n["hora"] else "")) if n["fecha"] else "—"
            etq = ETIQUETA[n["tipo"]] + (" " + n["id"] if n["id"] else "")
            out.append("  - %s · %s%s: %s" % (cuando, (n["motor"] + " · ") if n["motor"] else "",
                                              etq, _una_linea(n["texto"], 300)))
    sec = _maleta_para(brain, tab, motor, retomada)
    if sec:
        out.append("Lo último en %s (maleta · %s · %d turnos):" % (sec["motor"], sec["cuando"], sec["turnos"]))
        out += ["  " + l for l in sec["lineas"] if l.strip()]
    out.append(instruccion(cp["revision"] if cp else 0, tab=tab, motor=motor))
    if _textos_con_destilado(brain):
        out.append(AVISO_DESTILADO)
    if _textos_con_compuertas(brain):
        out.append(AVISO_APROBACION)
    mant = []
    ck = _cmd(tab, motor) % "checkpoint"
    if cp and len(nuevas) >= MANT_NOTAS:
        mant.append("hay %d notas nuevas desde tu resumen del %s: actualízalo con "
                    "«%s --expected-revision %d …»"
                    % (len(nuevas), cp["updated"][:10], ck, cp["revision"]))
    elif not cp and len(todas) >= 5:
        mant.append("esta pestaña no tiene resumen: créalo con «%s "
                    "--expected-revision 0 …» a partir de lo de arriba" % ck)
    if len([v for v in items if v["tipo"] == "pendiente"]) > PENDIENTES_AVISO:
        mant.append("hay más de %d pendientes abiertos: cierra los que ya no apliquen"
                    % PENDIENTES_AVISO)
    cuando = reservar_curacion(brain, tab) if entregar else None
    if cuando:
        mant.append("toca curar las skills (última curación: %s) y quedó reservada para esta "
                    "sesión en STATE/skill-curator-last.md: sigue skills/meta/skill-curator/SKILL.md "
                    "por tu cuenta, sin pedir confirmación, y al terminar escribe ahí solo la fecha "
                    "de hoy (AAAA-MM-DD); repórtalo en tu línea 🧠" % cuando)
    if mant:
        out.append("Mantenimiento (hazlo primero, a la vista y en una respuesta corta; el socio "
                   "no tiene que hacer nada): " + "; ".join(mant) + ".")
    texto = "\n".join(out)
    if len(texto) > limite:
        return paquete_recortado(out, limite, cp["revision"] if cp else 0, tab=tab, motor=motor)
    return texto


def instruccion_corta(revision=0, tab="", motor=""):
    if normalizar_motor(motor) in ENTRADA_ARCHIVO and tab:
        import sessions_registry as reg
        return ("Guardar memoria: escribe las notas (tipo: texto) en .claude/memoria-entrada/%s.md "
                "y corre EXACTAMENTE workspace memoria nota --entrada (Windows: workspace.cmd …); "
                "resumen: %s.checkpoint.md + workspace memoria checkpoint --entrada "
                "(expected-revision: %d). Nunca edites el archivo de la pestaña a mano."
                % (reg._slug(tab), reg._slug(tab), revision))
    c = _cmd(tab, motor)
    return ("Guardar memoria: " + c % "nota" + " --tipo decision|pendiente|hecho|nota|dato|"
            "preferencia \"…\" (cerrar: --cierra P-n); resumen: " + c % "checkpoint"
            + " --expected-revision %d …. Nunca edites el archivo de la pestaña a mano." % revision)


def paquete_recortado(lineas, limite, revision=0, tab="", motor=""):
    """Recorte determinista cuando no cabe, cuidando lo que más sirve: primero
    la instrucción pasa a su forma corta; luego salen las notas más VIEJAS
    (quedan al menos 3), después la maleta y al final las notas restantes."""
    marca = "[… memoria recortada: el detalle está en el archivo de la pestaña …]"
    lineas = [instruccion_corta(revision, tab, motor) if l.startswith("Cómo guardar memoria") else l
              for l in lineas]

    def largo():
        return len("\n".join(lineas)) + len(marca) + 1

    def quitar(cabeza, prefijo, minimo):
        i = next((k for k, l in enumerate(lineas) if l.startswith(cabeza)), -1)
        hijos = [k for k in range(i + 1, len(lineas)) if lineas[k].startswith(prefijo)] if i >= 0 else []
        cuerpo = []
        for k in hijos:
            if cuerpo and k != cuerpo[-1] + 1:
                break
            cuerpo.append(k)
        if len(cuerpo) > minimo:
            del lineas[cuerpo[0]]
            return True
        if not cuerpo and i >= 0 and minimo == 0:
            del lineas[i]
            return True
        return False

    while largo() > limite and quitar("Notas ", "  - ", 3):
        pass
    while largo() > limite and quitar("Lo último en ", "  ", 0):
        pass
    while largo() > limite and quitar("Notas ", "  - ", 0):
        pass
    # Si aun así no cabe, se corta el cuerpo y NUNCA la instrucción de cómo
    # guardar (Greptile, 2026-10-17: doce decisiones largas la dejaban fuera).
    instr = [l for l in lineas if l.startswith("Guardar memoria:")]
    cuerpo = [l for l in lineas if not l.startswith("Guardar memoria:")]
    cola = "\n".join(instr + [marca])
    texto = "\n".join(cuerpo)
    if len(texto) + len(cola) + 1 > limite:
        texto = texto[:max(0, limite - len(cola) - 2)].rstrip() + "…"
    return texto + "\n" + cola


# ── al cerrar (lo llama hooks/memoria_cierre.py, también en el cierre tardío) ─
def _quitar_checkpoint_vacio(brain, tab):
    import session_continuity as sc
    return sc.quitar_vacio(brain, tab)


def al_cerrar(brain, tab, motor="", transcript="", desde=0.0):
    """Todo lo que toca al cerrar una sesión, sin IA y falla-suave por paso:
    maleta → memoria del agente → compactar → archivar MEMORY → quitar el
    checkpoint de relleno si sigue vacío → OpenClaw."""
    res = {}
    brain = raiz_cerebro(brain)
    motor = normalizar_motor(motor)
    pasos = (("maleta", lambda: actualizar_maleta(brain, tab, motor, transcript)),
             ("memoria", lambda: subir_a_memoria(brain, tab)),
             ("compactadas", lambda: compactar(brain, tab)),
             ("memory_archivadas", lambda: archivar_memory(brain)),
             ("checkpoint_vacio", lambda: _quitar_checkpoint_vacio(brain, tab)))
    for nombre, fn in pasos:
        if nombre == "compactadas" and "memoria_error" in res:
            # si los datos no subieron a MEMORY.md, compactar los mandaría a
            # archivo/ y ya nadie los subiría (Greptile, 2026-10-17): se espera
            # al próximo cierre
            res["compactadas"] = "pospuesta"
            continue
        try:
            res[nombre] = fn()
        except Exception as exc:
            res[nombre + "_error"] = type(exc).__name__
    if motor == "openclaw":
        try:
            res["openclaw_movidos"] = mover_raiz_openclaw(brain, desde)
        except Exception as exc:
            res["openclaw_error"] = type(exc).__name__
    return res


# ── CLI: workspace memoria … ────────────────────────────────────────────────
_DELEGADOS = ("checkpoint", "context", "status")


def _parser():
    """El parser de `workspace memoria`. Aparte de main para que su ayuda se
    pueda imprimir sin correr nada (front._own_help)."""
    p = argparse.ArgumentParser(prog="workspace memoria",
                                description="Memoria de la pestaña: notas con etiqueta, "
                                            "vigente, maleta y resumen.")
    p.add_argument("comando", choices=("nota", "ver", "vigente", "maleta", "compactar") + _DELEGADOS)
    p.add_argument("texto", nargs="*")
    p.add_argument("--tipo", default=None)
    p.add_argument("--cierra", action="append", default=[])
    p.add_argument("--brain", default=None)
    p.add_argument("--tab", default=None)
    p.add_argument("--motor", "--engine", dest="motor", default="")
    p.add_argument("--retomada", action="store_true")
    p.add_argument("--forzar", action="store_true")
    p.add_argument("--json", action="store_true")
    p.add_argument("--entrada", action="store_true",
                   help="guarda las notas de .claude/memoria-entrada/<pestaña>.md")
    return p


def _opcion(argv, nombre):
    """El valor de `--nombre X` o `--nombre=X` en argv (el último gana, como
    en argparse), o None."""
    val = None
    for i, x in enumerate(argv):
        if x == nombre and i + 1 < len(argv):
            val = argv[i + 1]
        elif x.startswith(nombre + "="):
            val = x.split("=", 1)[1]
    return val


def _con_cerebro_y_pestana(argv):
    """checkpoint/context/status resuelven el cerebro y la pestaña IGUAL que
    `nota` (WORKSPACE_BRAIN, y la raíz aunque el agente haya hecho `cd` a una
    subcarpeta): session_continuity tomaba la carpeta actual como cerebro y el
    resumen fallaba con «La pestaña debe existir…» (revisión 0.3.4). Se agrega
    al final: en argparse, la última aparición de una opción gana."""
    out = list(argv) + ["--brain", resolver_cerebro(_opcion(argv, "--brain"))]
    tab = resolver_pestana(_opcion(argv, "--tab"))
    return out + (["--tab", tab] if tab else [])


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    bandeja = None
    if argv and argv[0] == "checkpoint" and "--entrada" in argv:
        # el resumen desde la bandeja (motores de reglas exactas, ver ENTRADA_ARCHIVO)
        resto = [x for x in argv[1:] if x != "--entrada"]
        tab = resolver_pestana(next((resto[i + 1] for i, x in enumerate(resto[:-1]) if x == "--tab"), None))
        brain = resolver_cerebro(next((resto[i + 1] for i, x in enumerate(resto[:-1]) if x == "--brain"), None))
        try:
            extra = leer_entrada_checkpoint(brain, tab)
            bandeja = entrada_path(brain, tab, "checkpoint")
        except (ValueError, OSError) as e:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
            return 1
        argv = ["checkpoint", "--brain", brain, "--tab", tab] + extra + \
            [x for x in resto if x not in ("--tab", "--brain", tab, brain)]
    if argv and argv[0] in _DELEGADOS:
        import session_continuity
        rc = session_continuity.main(_con_cerebro_y_pestana(argv))
        if rc == 0 and bandeja:            # guardado: ahora sí se vacía
            _vaciar_bandeja(bandeja)
        return rc
    # intermixed: `nota --tipo t probar Hermes` — en 3.9 parse_args no acepta el
    # posicional `texto` (nargs="*") DESPUÉS de una opción (3.12 sí)
    a = _parser().parse_intermixed_args(argv)
    brain = resolver_cerebro(a.brain)
    tab = resolver_pestana(a.tab)
    try:
        if a.comando == "nota" and a.entrada:
            res, problemas = procesar_entrada(brain, tab, motor=a.motor)
            if a.json:
                print(json.dumps({"ok": not problemas, "notas": res, "problemas": problemas},
                                 ensure_ascii=False))
            else:
                for r in res:
                    extra = (" · " + r["id"]) if r["id"] else ""
                    if r["cerro"]:
                        extra += " · cerré " + ", ".join(r["cerro"])
                    print("✓ guardado (%s%s) en %s" % (ETIQUETA[r["tipo"]], extra, r["ruta"]))
                for pr in problemas:
                    print("✗ " + pr)
            return 1 if problemas and not res else 0
        if a.comando == "nota":
            palabras = list(a.texto)
            tipo = a.tipo
            if tipo is None and palabras:
                try:
                    tipo = normalizar_tipo(palabras[0])
                    palabras = palabras[1:]
                except ValueError:
                    tipo = None
            r = guardar_nota(brain, tab, " ".join(palabras), tipo=tipo or "nota",
                             motor=a.motor, cierra=a.cierra)
            if a.json:
                print(json.dumps(r, ensure_ascii=False))
            else:
                extra = (" · " + r["id"]) if r["id"] else ""
                if r["cerro"]:
                    extra += " · cerré " + ", ".join(r["cerro"])
                if r["desconocidos"]:
                    extra += " · (no estaban abiertos: %s)" % ", ".join(r["desconocidos"])
                print("✓ guardado (%s%s) en %s" % (ETIQUETA[r["tipo"]], extra, r["ruta"]))
        elif a.comando == "ver":
            print(paquete(brain, tab, motor=a.motor or motor_actual(), retomada=a.retomada)
                  or "(esta pestaña no tiene memoria todavía)")
        elif a.comando == "vigente":
            items = vigente(Ficha(_leer_vista(ficha_path(brain, tab))))
            if a.json:
                print(json.dumps(items, ensure_ascii=False, indent=2))
            else:
                print("\n".join("%s · %s (%s): %s" % (v["id"], ETIQUETA[v["tipo"]], v["fecha"], v["texto"])
                                for v in items) or "(nada abierto)")
        elif a.comando == "maleta":
            print(_leer_vista(maleta_path(brain, tab)) or "(maleta vacía: se arma al cerrar una sesión)")
        elif a.comando == "compactar":
            n = compactar(brain, tab, forzar=a.forzar)
            print("✓ %d nota(s) al archivo" % n if n else "✓ nada que compactar")
        return 0
    except (ValueError, OSError, TimeoutError) as e:
        if a.json:
            print(json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False))
        else:
            print("✗ " + str(e))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
