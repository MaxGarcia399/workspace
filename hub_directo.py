#!/usr/bin/env python3
r"""WORKSPACE · hub_directo — la conversación directa en el hub «Paleta». SOLO PARA PROBAR: vive en la rama
zenith/marca-lab y nunca entra a main.

Cada agente tiene UNA conversación directa, y el hub y el navegador son dos vistas de ella. El hub no guarda estado
propio: es un cliente más del servidor local de la página (localhost_web + pagina_v2), con las mismas rutas que ella:
  · /api/v2/vivo (long-poll): el estado de cada agente, el turno en curso, su permiso y su pregunta;
  · /api/v2/conversacion: los turnos terminados (por versión: solo lo que cambió);
  · /api/v2/mandar, permiso, responder, parar y motor: lo que haces aquí, por la capa de control oficial de su motor.
Si la página no está prendida, el hub la prende sin abrir el navegador (localhost_fondo, la de esta máquina, con su
llave). Lo que escribes aquí aparece en el navegador y al revés; si las dos mandan a la vez, el segundo va a la cola.

  · Enter le responde al agente aquí mismo · Tab cambia de agente;
  · ^E cambia el motor de esta conversación (como en la página: la conversación sigue, con su nota de contexto);
  · ^O «Abrir en su motor»: la entrega de la Paleta (hub_paleta) al cliente oficial, en esta terminal, con lo escrito
    como primer mensaje; esa sesión vive aparte y al salir vuelves aquí;
  · ^S sus sesiones oficiales (H3), en una lista aparte: una nueva (lo mismo que ^O) y las suyas, con su motor, su
    estado y lo último que terminaron; Enter retoma la elegida en su cliente. Lo que una sesión termina llega a la
    conversación directa como una línea («◇ Terminó en Claude Code…»: pagina_sesiones, del registro de eventos);
  · Esc borra lo escrito; sin texto, para al agente que trabaja; si no trabaja, sale.

Los monitos se mueven solo en su recuadro y a pocos cuadros por segundo: brincan al elegirlos, piensan mientras su
motor trabaja (los ojos y los tres puntos) y celebran al terminar. Solo se reescriben las filas que cambian.

Sin pantalla (para ver cómo queda):
    python3 hub_directo.py --render 88x30 [--caso conversacion|permiso|pregunta|motor|sesiones|vacia] [--256]
                           [--html f]
Stdlib."""
import datetime as _dt
import http.client
import json
import os
import re
import secrets
import shutil
import socket
import sys
import threading
import time
from urllib.parse import urlencode

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
import hub_paleta as P  # noqa: E402

C, ERR = P.C, P.ERR
NAV = "navegador"
#: La cookie de la llave de la página (localhost_web.COOKIE; no se importa localhost_web: es pesado).
COOKIE = "ws_llave"
#: El long-poll: lo mismo que la página (25 s) y el tope de cada pregunta.
ESPERA_VIVO_S, TOPE_VIVO_S = 25, 35
TOPE_S = 10.0
#: skills-cierre (Fix 5): lo que puede abrir su motor dentro de la misma petición (mandar, usar una skill, contestar…)
#: espera lo que la página (60 s, su MANDAR_TOPE_MS). Antes cortaba a los 10 s y decía «No arrancó» aunque arrancara
#: (Kiro abre en 13-16 s, Cursor en 9-11, OpenClaw en ~78).
TOPE_ESCRIBIR_S = 60.0
ABREN_MOTOR = ("/api/v2/mandar", "/api/v2/skill", "/api/v2/responder", "/api/v2/archivo", "/api/v2/revision",
               "/api/v2/skill/accion")
#: Cuánto se espera a que la página recién prendida conteste.
ESPERA_SERVIDOR_S = 15.0
#: La página prendida no conoce una ruta (es de antes de una actualización y aún no se renueva): lo que dice el hub.
ACTUALIZANDO = "Workspace se está actualizando… vuelve a intentar en unos segundos."
#: La página se renovó tras una actualización (localhost_fondo.renovar).
RENOVADA = "Workspace se actualizó: reinicié la página"
#: Este hub es de antes que la página (Workspace se actualizó con él abierto): deja de escuchar y lo dice arriba.
HUB_VIEJO = "Workspace se actualizó: ciérrame y ábreme de nuevo"
#: AG2-a: la página local no prendió. El hub abre igual, sin la conversación: tus agentes se abren en su programa y
#: sus sesiones se ven; la escucha reintenta prenderla sola.
SIN_PAGINA = ("Sin conversación por ahora: la página local no prendió. Tus agentes se abren en su programa "
              "(Enter) y sus sesiones se ven; reintento sola.")
SIN_PAGINA_CORTO = "Sin la página local: esto vuelve cuando prenda (reintento sola)."
SIN_PAGINA_ABRIR = "La página local no prendió todavía: reintento sola. Si sigue así, `workspace doctor`."
#: «+ Agregar» mientras la tarjeta nueva no está en esta copia (hub_agregar): la ventana «Nuevo agente» de la página.
AGREGAR_EN_PAGINA = "Agrega tu agente con «+» en la página: la abrí en tu navegador."
AGREGAR_SIN_PAGINA = "Para agregar un agente hace falta la página local, que no prendió: reintento sola."


#: AG3-a · los idiomas en que ya está el hub de terminal. En los demás se ve en español (todo, también lo nuevo: nada
#: a medias) y una línea en tu idioma lo dice al abrir; los textos nuevos ya traen su clave ES/EN para cuando llegue.
IDIOMAS_HUB = ("es",)


def idioma_hub():
    """El idioma en que se ve el hub de terminal: el tuyo si ya está (IDIOMAS_HUB); si no, español."""
    try:
        import i18n
        code = i18n.lang()
    except Exception:
        return "es"
    return code if code in IDIOMAS_HUB else "es"


def aviso_idioma():
    """La línea, en TU idioma, para quien usa Workspace en uno en que el hub todavía no está; '' si ya está."""
    try:
        import i18n
        if i18n.lang() in IDIOMAS_HUB:
            return ""
        t = i18n.t("puertas.hub.solo_es")
        return t if isinstance(t, str) and t != "puertas.hub.solo_es" else ""
    except Exception:
        return ""


def _tp(clave, es, **kw):
    """Un texto nuevo del hub con su clave ES/EN (lang/<idioma>/puertas.py) y el español de red, en el idioma del hub
    (idioma_hub: el tuyo si ya está; si no, español)."""
    try:
        if idioma_hub() != "es":
            import i18n
            t = i18n.t(clave, **kw)
            if isinstance(t, str) and t and t != clave:
                return t
    except Exception:
        pass
    return es.format(**kw) if kw else es
#: Un hub que no está al frente no deja long-polls abiertos: a los REPOSO_FOCO_S en segundo plano (si la terminal lo
#: avisa) o a los REPOSO_S sin una tecla (si no), o mientras un motor tiene su terminal, pregunta cada REPOSO_CADA_S
#: sin esperar; una tecla, el mouse o volver al frente lo despiertan. Antes, 65 hubs abiertos en paneles de la
#: terminal tenían la página a 130 % de CPU.
REPOSO_S, REPOSO_FOCO_S, REPOSO_CADA_S = 600.0, 20.0, 30.0
#: La página de antes que tenía algo a medio hacer: cada cuánto se vuelve a intentar renovarla.
RENOVAR_CADA_S = 20.0
#: Cuánto se ve un aviso de una línea; cuánto se espera a que lo que mandaste aparezca en la conversación.
AVISO_S = 6.0
PENDIENTE_S = 10 * 60
#: Los monitos: el que piensa cambia a 4 cuadros por segundo; el que termina brinca dos veces.
PIENSA_S = 0.25
FIESTA_S = 2 * P.BRINCO_S
#: Cada cuánto se relee el uso del motor del elegido, y los motores para ^E.
USO_S, MOTORES_S = 60.0, 60.0
#: Con ^S abierta, cada cuánto se relee la lista de sesiones (la escucha vuelve en cuanto algo cambia).
SESIONES_S = 3.0
#: H4-a: una pestaña recién abierta se ve aunque su foto aún no llegue (s); cuánto se ofrece «Deshacer» al cerrarla.
TAB_PEND_S, DESHACER_S = 15.0, 60.0
#: Cada cuánto se relee la lista de skills (Skills ▾ y «/»), y cuántos renglones mueve un paso de la rueda.
SKILLS_S = 60.0
RUEDA = 3
#: Lo que devuelve Directo.raton cuando el mouse se movió sin cambiar nada: no hace falta repintar.
SIN_CAMBIO = object()
#: Con la sección Sesiones abierta, cada cuánto se relee la lista de cada agente.
SES_TODAS_S = 10.0
#: Soltar el borde del riel desde esta columna (contando desde 1) lo deja con nombres; antes, solo monitos.
RIEL_ARRASTRE_MITAD = 24
#: Lo de las secciones (motores, conexiones, permisos, apariencia) se relee si tiene más de esto; y tras «Verificar
#: ahora», cuánto se espera para releer los motores.
SECCION_S, VERIFICAR_S = 30.0, 2.0
#: El foco (H-1): lo que no se enfoca (los fondos que reciben la rueda o paran un clic) y el orden de las áreas para
#: Tab. Lo que se toca con el mouse ES lo que se enfoca: Enter hace lo mismo que su clic.
PASIVAS_FOCO = {"riel", "conv", "lista", "detalle", "menu:caja", "pan:caja", "fr:caja", "riel:borde"}
#: Lo que el mouse toca y el foco no, por su comienzo: en Inicio, las copias de ←→ (los de al lado, ◀ ▶, los
#: cuadritos), de ↑↓ (los motores de arriba y abajo), de Enter y s (sus botones) y la búsqueda (se escribe); en el
#: tablero de Agentes, sus celdas y sus filas de motores (←→↑↓).
PASIVAS_PREF = ("ini:ag:", "ini:flecha:", "ini:punto:", "ini:mot:", "ini:conv:", "ini:ses:", "ini:arch:",
                "ini:deshacer", "ini:volver:", "ini:archmas", "ini:buscar", "celda:", "trow:", "tcol:")
#: «pestanas» (H4-a): la tira de pestañas del borde (⌂, sus sesiones, su ×, «+N ▾», «+» y los avisos de Deshacer e Ir
#: a la terminal), con Tab y ←→ como todo lo demás; además, sus atajos (Ctrl+T, Ctrl+W, Ctrl+←/→, Alt+1…9).
AREAS = ("ahora", "agentes", "secciones", "lista", "detalle", "filtros", "riel", "pestanas", "chat", "panel", "franja",
         "marco", "barra")
NO = object()
_INI_AREA = {"card": "agentes", "conv": "agentes", "ses": "agentes", "todos": "agentes", "nuevo": "agentes",
             "sec": "secciones", "sub": "secciones", "web": "barra", "resp": "ahora", "abrir": "ahora", "sesiones": "ahora"}


def area_de(z):
    """El área de una zona (x, y, w, h, rid): dónde la deja Tab."""
    _x, y, _w, _h, rid = z
    p, _s, r = rid.partition(":")
    if p == "ini":
        return _INI_AREA.get(r.split(":")[0], "ahora")
    if p in ("riel", "nav"):
        return "riel"
    if p == "bar":
        return "barra" if y < 3 else "riel"
    if p in ("hdr", "in", "perm", "preg"):
        return "chat"
    if p == "tb":
        return "pestanas"
    if p in ("pan", "fr"):
        return "panel" if p == "pan" else "franja"
    if p in ("fil", "sgr"):
        return "filtros"
    if p == "sr":
        return "lista"
    if p in ("acc", "op", "cara", "color", "tab", "tono"):
        return "detalle"
    if p == "sec":
        return "marco"
    if p in MENU_P:
        return "menu"
    return "otro"


#: Cada cuánto se vuelven a pedir las sesiones del elegido mientras se ve su panel (s).
PANEL_SES_S = 15.0
#: Ajustes → Permisos: las dos que se eligen aquí (la página también tiene «editar»).
NIVELES = {"auto": "Automático", "preguntar": "Preguntarme todo"}
PAGINA = 10


# ── lo que hizo, en simple (lo mismo que la página: web/front/src/50_chat.js) ───
HERR_N = {"Read": "leyó", "Edit": "editó", "Write": "escribió", "Bash": "corrió un comando", "Ran": "corrió un comando",
          "Shell": "corrió un comando", "Explored": "exploró", "Called": "usó una herramienta", "Grep": "buscó",
          "Glob": "buscó archivos", "Task": "mandó a un ayudante", "Agent": "mandó a un ayudante",
          "WebFetch": "leyó una página", "WebSearch": "buscó en la web"}
HERR_PL = {"corrió un comando": "corrió {n} comandos", "leyó": "leyó {n} archivos", "editó": "editó {n} archivos",
           "escribió": "escribió {n} archivos", "buscó": "buscó {n} veces",
           "buscó archivos": "buscó archivos {n} veces",
           "mandó a un ayudante": "mandó a {n} ayudantes", "leyó una página": "leyó {n} páginas",
           "buscó en la web": "buscó en la web {n} veces", "exploró": "exploró {n} veces",
           "usó una herramienta": "usó {n} herramientas"}


def resumen_herr(h):
    """«corrió un comando» ×5 → «corrió 5 comandos» (resumenHerr de la página)."""
    orden, cuenta = [], {}
    for x in h or []:
        t = HERR_N.get(x.get("n"), x.get("n") or "?")
        if t not in cuenta:
            cuenta[t] = 0
            orden.append(t)
        cuenta[t] += 1
    partes = [(HERR_PL.get(t) or t + " ×{n}").replace("{n}", str(cuenta[t])) if cuenta[t] > 1 else t for t in orden]
    return " · ".join(partes[:3]) + (" y %d más" % (len(partes) - 3) if len(partes) > 3 else "")


PERMISO_T = {"permitir": "Permitir", "permitir_siempre": "Siempre", "negar": "No"}
PERMISO_HECHO = {"permitir": "Permitido", "permitir_siempre": "Permitido siempre", "negar": "Negado"}
PERM_QUE = {
    "comando": ("Quiere correr un comando", "Quiso correr un comando"),
    "crear": ("Quiere crear un archivo", "Quiso crear un archivo"),
    "cambiar": ("Quiere cambiar un archivo", "Quiso cambiar un archivo"),
    "borrar": ("Quiere borrar un archivo", "Quiso borrar un archivo"),
    "imagen": ("Quiere leer una imagen", "Quiso leer una imagen"),
    "leer": ("Quiere leer un archivo", "Quiso leer un archivo"),
    "buscar": ("Quiere buscar en sus archivos", "Quiso buscar en sus archivos"),
    "web": ("Quiere abrir una página de internet", "Quiso abrir una página de internet"),
    "otra": ("Quiere usar una de sus herramientas", "Quiso usar una de sus herramientas"),
}
#: B01 (cacería 19-nov, como la página): DÓNDE no se adivina; «de su carpeta» solo si la capa de control lo sabe.
PERM_DONDE = {"dentro": {"crear": " en su carpeta", "otro": " de su carpeta"}, "fuera": " FUERA de su carpeta"}
#: Por el nombre EXACTO de su herramienta (nunca por palabras sueltas de un título o una ruta).
PERM_NOMBRE = (("borrar", r"^(delete|remove|rm)$"),
               ("comando", r"^(bash|shell|run|run command|run shell command|execute|exec|terminal|comando|command)$"),
               ("web", r"^(webfetch|websearch|fetch|browse)$"), ("crear", r"^(write|create)$"),
               ("cambiar", r"^(edit|multiedit|notebookedit|patch|apply patch|str replace|cambio de archivos)$"),
               ("buscar", r"^(grep|glob|search|find)$"), ("leer", r"^(read)$"))
PERM_IMAGEN = re.compile(r"\.(png|jpe?g|gif|webp|svg|heic|bmp|tiff?)$", re.I)


def _datos(detalle):
    try:
        return json.loads(detalle)
    except (TypeError, ValueError):
        return None


def permiso_clase(pm, d):
    """permisoClase de la página: por el nombre exacto; si no, por las claves de su entrada (una ruta sola no dice
    qué hace con ella)."""
    n = re.sub(r"[_-]+", " ", str(pm.get("herramienta") or "").lower()).strip()
    k = ""
    if not n.startswith("mcp "):
        k = next((c for c, rx in PERM_NOMBRE if re.search(rx, n)), "")
    if not k and isinstance(d, dict):
        k = ("comando" if (d.get("command") or d.get("cmd")) else "web" if d.get("url") else
             "cambiar" if (d.get("old_string") or d.get("new_string") or d.get("edits") or d.get("diff")) else
             "crear" if ("content" in d and (d.get("file_path") or d.get("filePath") or d.get("path"))) else
             "buscar" if (d.get("pattern") or d.get("query")) else "")
    s = str(pm.get("detalle") or "") if d is None else ""
    if not k and s:
        def tiene(r):
            return re.search(r'"(%s)"\s*:' % r, s) is not None
        k = ("comando" if tiene("command|cmd") else "web" if tiene("url") else
             "cambiar" if tiene("old_string|new_string|edits|diff") else
             "crear" if tiene("content") and tiene("file_path|filePath|path") else
             "buscar" if tiene("pattern|query") else "")
    return k or "otra"


def permiso_archivo(d, crudo, archivo):
    p = archivo
    if not p:
        if isinstance(d, list):
            p = d[0] if d else None
        elif isinstance(d, dict):
            p = d.get("file_path") or d.get("filePath") or d.get("path") or d.get("file")
    if not p and d is None and crudo:
        m = re.search(r'"(?:file_path|filePath|path|file)"\s*:\s*"([^"]+)"', str(crudo))
        p = m and m.group(1)
    if not isinstance(p, str) or not p:
        return ""
    return re.split(r"[\\/]", re.sub(r"[\\/]+$", "", p))[-1][:80]


def permiso_simple(pm, ya=False):
    """→ «Quiere crear un archivo en su carpeta: «notas.md».» (permisoEnSimple de la página; `ya`: contestado). Con
    `que` (la capa de control: B01), lo que de verdad pide; sin él, lo de antes, sin decir dónde."""
    q = pm.get("que") if isinstance(pm.get("que"), dict) and pm["que"].get("clase") in PERM_QUE else None
    if q:
        k2 = "imagen" if q["clase"] == "leer" and PERM_IMAGEN.search(q.get("ruta") or "") else q["clase"]
        s = PERM_QUE[k2][1 if ya else 0]
        if k2 == "comando":
            return s + (": «%s»" % q["comando"] if q.get("comando") else "") + "."
        if q.get("ruta") and k2 != "web":
            fuera = q.get("fuera")
            s += (PERM_DONDE["fuera"] if fuera is True else
                  (PERM_DONDE["dentro"]["crear" if k2 == "crear" else "otro"] if fuera is False else "")) + \
                ": «%s»" % q["ruta"]
        return s + "."
    d = _datos(pm.get("detalle"))
    k = permiso_clase(pm, d)
    f = permiso_archivo(d, pm.get("detalle"), pm.get("archivo"))
    if k == "leer" and PERM_IMAGEN.search(f):
        k = "imagen"
    return PERM_QUE[k][1 if ya else 0] + (": «%s»" % f if f and k not in ("comando", "web", "otra") else "") + "."


def detalle_corto(nombre, detalle, archivo=""):
    """Lo técnico en una línea: su herramienta y lo que importa de su entrada (el comando, el archivo, la página)."""
    d = _datos(detalle)
    que = ""
    if isinstance(d, dict):
        que = (d.get("command") or d.get("cmd") or d.get("url") or d.get("pattern") or d.get("query")
               or permiso_archivo(d, "", archivo) or "")
        if isinstance(que, list):
            que = " ".join(str(x) for x in que)
    elif detalle:
        que = permiso_archivo(None, detalle, archivo) or str(detalle)
    que = " ".join(str(que).split())
    return " · ".join(x for x in (str(nombre or ""), que) if x)


ES_INSTRUCCION = re.compile(r"pasos\.py|\bworkspace(?:\.cmd)?\s+pasos\s+s-|\breportar_avance\b")


def nombre_skill(s):
    s = re.sub(r"\s+", " ", re.sub(r"[-_]+", " ", str(s or ""))).strip()
    return s[:1].upper() + s[1:]


def nombre_motor(m):
    return P.NOMBRE_MOTOR.get(m or "", m or "su motor")


# ── el cliente del servidor de la página ──────────────────────────────────────
class ErrorServidor(Exception):
    """Lo que contestó el servidor cuando no fue un 200 (`texto`: su error en simple), o sin conexión (status None)."""

    def __init__(self, status, texto, datos=None, tiempo=False):
        super().__init__(texto)
        self.status, self.texto, self.datos = status, texto, datos or {}
        #: La página prendida no conoce esa ruta (es de otra versión): lo que la usa, apagado y dicho en corto (no el
        #: «ruta desconocida…» del servidor: ACTUALIZANDO, y el hub renueva la página en cuanto puede)
        self.sin_ruta = status == 404 and "ruta desconocida" in str(texto)
        if self.sin_ruta:
            self.texto = ACTUALIZANDO
        #: 503: la página atiende a muchos a la vez (localhost_web: tope de long-polls); se vuelve en `reintenta` s
        self.ocupado = status == 503
        try:
            self.reintenta = max(1.0, min(60.0, float(self.datos.get("reintenta") or 5))) if self.ocupado else 0.0
        except (TypeError, ValueError):
            self.reintenta = 5.0
        #: skills-cierre (Fix 5): no contestó a tiempo (sigue abriendo su motor): lo pedido puede salir todavía
        self.tiempo = bool(tiempo)


class Servidor:
    """Habla con la página local como la página misma: su llave en la cookie y, en los POST, su Origin.
    `transporte(metodo, ruta, cabeceras, cuerpo) → (status, bytes)`: las pruebas pasan cada petición al Handler.
    `local(ruta) → (status, bytes)`: si la página prendida no conoce una ruta de LECTURA, se calcula aquí, de solo
    leer (hub_local); las escrituras van SIEMPRE a la página prendida."""

    def __init__(self, puerto, llave, transporte=None, local=None):
        self.puerto, self.llave, self.transporte, self.local = int(puerto), str(llave), transporte, local
        #: la firma del código de la página (servidor.json), si es la de antes (`vieja`: se renueva al quedar libre),
        #: si este hub es de antes que ella (`hub_viejo`) y la línea que dice el hub al conectarse (`aviso`)
        self.firma, self.vieja, self.hub_viejo, self.aviso = None, False, False, ""
        #: quién escucha (el tope de long-polls por cliente de la página)
        self.cliente = secrets.token_hex(6)

    def _pedir(self, metodo, ruta, cuerpo=None, timeout=TOPE_S, transporte=None):
        base = "127.0.0.1:%d" % self.puerto
        h = {"Host": base, "Cookie": "%s=%s" % (COOKIE, self.llave)}
        datos = None
        if metodo == "POST":
            datos = json.dumps(cuerpo or {}, ensure_ascii=False).encode("utf-8")
            h.update({"Origin": "http://" + base, "Content-Type": "application/json",
                      "Content-Length": str(len(datos))})
        try:
            if transporte is not None:
                status, crudo = transporte(ruta)
            elif self.transporte is not None:
                status, crudo = self.transporte(metodo, ruta, h, datos)
            else:
                c = http.client.HTTPConnection("127.0.0.1", self.puerto, timeout=timeout)
                try:
                    c.request(metodo, ruta, body=datos, headers=h)
                    r = c.getresponse()
                    status, crudo = r.status, r.read()
                finally:
                    c.close()
        except (OSError, http.client.HTTPException) as e:
            # (socket.timeout): contestará, pero tarde. En 3.9 socket.timeout aún no es TimeoutError (lo es desde 3.10)
            if isinstance(e, (TimeoutError, socket.timeout)):
                raise ErrorServidor(None, "La página local sigue abriendo su motor.", tiempo=True)
            raise ErrorServidor(None, "No hay conexión con la página local (%s)." % type(e).__name__)
        try:
            d = json.loads(crudo.decode("utf-8")) if crudo else {}
        except ValueError:
            d = {}
        if status != 200:
            texto = d.get("__err") if isinstance(d, dict) else ""
            raise ErrorServidor(status, str(texto or "La página contestó %d." % status),
                                d if isinstance(d, dict) else {})
        return d if isinstance(d, dict) else {}

    def get(self, ruta, timeout=TOPE_S, **q):
        r = ruta + ("?" + urlencode(q) if q else "")
        try:
            return self._pedir("GET", r, timeout=timeout)
        except ErrorServidor as e:
            if not (e.sin_ruta and self.local is not None and ruta in LEER_AQUI):
                raise
            falla = e
        try:
            return self._pedir("GET", r, transporte=self.local)  # la página prendida no la trae: aquí, solo leer
        except ErrorServidor:
            raise
        except Exception:
            raise falla

    def post(self, ruta, cuerpo):
        return self._pedir("POST", ruta, cuerpo, timeout=TOPE_ESCRIBIR_S if ruta in ABREN_MOTOR else TOPE_S)


def _fondo():
    import localhost_fondo
    return localhost_fondo


def _leer_aqui(ruta):
    import hub_local
    return hub_local.get(ruta)


#: Las rutas de lectura que se calculan aquí si la página prendida no las trae (hub_local.LEER).
LEER_AQUI = ("/api/v2/sesiones", "/api/skills", "/api/conexiones", "/api/v2/info", "/api/calendario",
             "/api/sistema/usuarios", "/api/v2/conexiones")
#: (/api/v2/chequeo no se calcula aquí: revisa y arregla lo de Workspace en el fondo, y eso es del servidor)


def _de(d, transporte=None):
    srv = Servidor(d["puerto"], d["llave"], transporte, local=None if transporte else _leer_aqui)
    srv.firma = d.get("firma")
    return srv


class ServidorSinPagina(Servidor):
    """AG2-a · el hub sin la página: la página local no prendió, y el hub abre igual. Lee aquí, en este proceso, lo que
    se puede leer (las de LEER_AQUI con hub_local, y los agentes con su monito, como la Paleta de antes leía
    localhost_front.inicio); todo lo demás (la conversación, mandar, contestar) contesta «sin la página», y la escucha
    reintenta prenderla sola (Escucha: con status None, conectar). `sin_pagina`: lo que mira el hub para apagar
    «Conversar» y lo que solo la página hace."""
    sin_pagina = True

    def __init__(self):
        super().__init__(0, "", transporte=self._aqui)
        self.cliente = ""

    @staticmethod
    def _aqui(metodo, ruta, _cabeceras, _datos):
        base = ruta.split("?", 1)[0]
        if metodo == "GET" and base in LEER_AQUI:
            return _leer_aqui(ruta)
        if metodo == "GET" and base == "/api/front/inicio":
            import localhost_front
            return 200, json.dumps(localhost_front.inicio(), ensure_ascii=False).encode("utf-8")
        raise ErrorServidor(None, _tp("puertas.hub.sin_pagina_corto", SIN_PAGINA_CORTO))


def _firma_codigo(F=None):
    """La firma del código de la página en el disco ahora (localhost_fondo.firma), o None."""
    try:
        F = F or _fondo()
        fn = getattr(F, "firma", None)
        return fn() if fn else None
    except Exception:
        return None


#: La del código con que abrió este hub: si la de la página y la del disco ya son otras, este hub es de antes.
FIRMA_AL_CARGAR = _firma_codigo()


def ocupada_en(d, crudas=None):
    """¿La página tiene algo a medio hacer? (una respuesta de /api/v2/vivo; `crudas`: las fotos de todos los agentes
    que ya tiene el hub, si la respuesta trae solo lo que cambió). Ante la duda, sí."""
    try:
        import localhost_fondo
        cuerpo = {"agentes": dict(crudas or {}, **((d or {}).get("agentes") or {}))}
        if isinstance(d, dict) and "ocupada" in d:
            cuerpo["ocupada"] = d["ocupada"]
        return localhost_fondo.ocupada_en(cuerpo)
    except Exception:
        return True


def conectar(lanzar=True, tope=ESPERA_SERVIDOR_S, fondo=None, dormir=time.sleep, reloj=time.monotonic,
             firma_hub=None):
    """La página local de esta máquina (localhost_fondo: UNA por máquina, con su llave). → Servidor o None.
      · la de hoy: se usa;
      · la de antes de una actualización (otra firma): si este hub es de hoy, se renueva (localhost_fondo.renovar:
        «Apagar» y nace la de hoy) y el Servidor trae el `aviso` RENOVADA; si tiene algo a medio hacer (o no se pudo),
        se usa así, marcada `vieja` (Escucha la renueva al quedar libre; lo que no trae dice ACTUALIZANDO);
      · `firma_hub` (la del código con que abrió el hub, FIRMA_AL_CARGAR): si el disco ya trae otra y la página no
        es la de este hub, el Servidor sale marcado `hub_viejo` (el hub deja de escuchar y pide que lo reabran);
      · si no hay (o no contesta), y `lanzar`: se prende sin abrir el navegador y se espera a que conteste."""
    F = fondo or _fondo()
    d, como = F.vivo()
    hoy = _firma_codigo(F) if firma_hub else None
    hub_viejo = bool(firma_hub and hoy and firma_hub != hoy)

    def marcar(srv, dd):
        srv.hub_viejo = hub_viejo and (dd or {}).get("firma") != firma_hub
        return srv
    if como == "vivo":
        return marcar(_de(d), d)
    d0 = d
    if como == "viejo":
        renovar = getattr(F, "renovar", None)
        if not hub_viejo and renovar is not None:   # un hub de antes no renueva: lo hace el de hoy (o el update)
            try:
                n, r = renovar(tope=tope, dormir=dormir, reloj=reloj)
            except Exception:
                n, r = d, "fallo"
            if r == "renovada" and n:
                srv = _de(n)
                srv.aviso = RENOVADA
                return marcar(srv, n)
        srv = _de(d)
        try:
            srv.get("/api/v2/info")
            srv.vieja = True
            return marcar(srv, d)
        except ErrorServidor:
            pass                                     # no tiene la conversación directa: que nazca una de hoy
    if not lanzar:
        return None
    try:
        proc = F.lanzar(abrir=False)
    except Exception:
        return None
    F._recoger(proc)
    fin = reloj() + tope
    while reloj() < fin:
        dormir(0.15)
        d, como = F.vivo()
        # la que nació (no la de antes, que sigue anotada hasta que la nueva la apaga)
        if como == "vivo" or (como == "viejo" and not (d0 and d and d.get("llave") == d0.get("llave"))):
            return marcar(_de(d), d)
    return None


def agentes_de(srv):
    """Los agentes con su monito (/api/front/inicio: lo mismo que la página). Su cerebro solo se mira en esta máquina
    para contar su memoria y sus skills en la entrega (la página no manda rutas del disco)."""
    try:
        import localhost_front
        cerebros = dict(localhost_front._cerebros())
    except Exception:
        cerebros = {}
    out = []
    for x in srv.get("/api/front/inicio").get("agentes") or []:
        aid = str(x.get("id") or "")
        if not aid:
            continue
        c = str(x.get("color") or "")
        f = str(x.get("forma") or "")
        out.append({"id": aid, "n": limpio(x.get("nombre") or aid).strip() or aid,
                    "c": c if re.match(r"^#[0-9a-fA-F]{6}$", c) else "#ffffff",
                    "f": f if f in P.PATH else sorted(P.PATH)[0], "mid": str(x.get("motor") or ""),
                    "brain": cerebros.get(aid) or ""})
    return out


def juntar(c, r):
    """La conversación por versión (juntarConversacion de la página): el servidor manda solo lo que cambió desde la
    que tenemos (`desde` = índice absoluto de su primer turno) y aquí se pega sobre lo que había."""
    if r.get("igual") and c:
        return c
    cb = (c.get("total") or 0) - len(c.get("turnos") or []) if c else 0
    if c and r.get("desde") is not None and r["desde"] >= cb:
        t = list(c.get("turnos") or [])[:r["desde"] - cb] + list(r.get("turnos") or [])
    else:
        t = list(r.get("turnos") or [])
    if r.get("n") is not None:
        t = t[max(0, len(t) - int(r["n"])):]
    return dict(r, turnos=t)


def _norm(s):
    return " ".join(str(s or "").split())


def st_de(f):
    """El estado del monito por la foto de su conversación directa."""
    if not f:
        return "duerme"
    e = f.get("estado")
    if e == "esperandote" or f.get("pregunta"):
        return "pregunta"
    return {"trabajando": "trabaja", "termino": "termino", "error": "error", "dormido": "duerme"}.get(e, "libre")


def opciones_pregunta(q):
    return ["Sí", "No"] if q.get("tipo") == "confirmar" else [str(x) for x in (q.get("opciones") or [])[:6]]


def opciones_de(pm, q):
    """Lo que se elige con ←→ y se contesta con Enter: las del permiso (si se contesta aquí) o las de la pregunta."""
    if pm:
        return [] if pm.get("en_terminal") else list(pm.get("opciones") or [])
    if q and not q.get("en_terminal"):
        return opciones_pregunta(q)
    return []


def _ts(s):
    try:      # «Z» al final: Python 3.9 (el de las Mac de clientes) no la lee en fromisoformat
        return _dt.datetime.fromisoformat(str(s).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return 0.0


#: skills-cierre (Fix 2): la foto de una página de antes no trae `skill_vigente` (se calcula aquí, como antes).
SIN_REGLA = False
ABIERTAS = ("arrancando", "corriendo", "pide")


def vigente(ejec, ahora=None, id_vigente=SIN_REGLA):
    """La skill que corre en esta conversación. La regla es UNA, la del servidor de la página: su foto la trae
    como `skill_vigente` (`id_vigente`: su id, o None si no corre ninguna) y aquí solo se busca. Con una página de
    antes (SIN_REGLA), la de siempre: la primera abierta (arrancando, corriendo, pide), de hace menos de 6 h; una que
    nunca arrancó deja de contar a los 10 min. `pausada` (se detuvo sin terminar) y `listo` no cuentan."""
    if id_vigente is not SIN_REGLA:
        return next((e for e in ejec or [] if id_vigente and e.get("id") == id_vigente
                     and e.get("estado") in ABIERTAS), None)
    ahora = time.time() if ahora is None else ahora
    for e in ejec or []:
        if e.get("estado") not in ABIERTAS:
            continue
        t = _ts(e.get("actualizado") or e.get("creado"))
        if e.get("estado") == "arrancando" and t and ahora - t > 600:
            continue
        if not t or ahora - t < 6 * 3600:
            return e
    return None


# ── el texto de la conversación, a renglones ──────────────────────────────────
def limpio(s):
    """Texto que llega de un motor, sin sus escapes (ni lo que quedaría a la vista: «[2J») ni invisibles. Un control
    suelto que quede lo vuelve espacio Term.put, que nunca escribe uno a la terminal."""
    try:
        import _width
        return _width.sane(_width.strip_ansi(str(s or "")))
    except ImportError:                                # pragma: no cover
        return str(s or "")


def md(linea, fg):
    """Un renglón con `código` y **negritas** → segmentos (texto, color, negrita)."""
    out = []
    for parte in re.split(r"(`[^`\n]+`|\*\*[^*\n]+\*\*)", linea):
        if not parte:
            continue
        if parte.startswith("`") and len(parte) > 2:
            out.append((parte[1:-1], C["tx"], False))
        elif parte.startswith("**") and len(parte) > 4:
            out.append((parte[2:-2], fg, True))
        else:
            out.append((parte, fg, False))
    return out


def _corte(s, n):
    """Cuántos caracteres de `s` caben en `n` columnas (al menos uno)."""
    w = 0
    for i, ch in enumerate(s):
        w += P._ancho(ch)
        if w > n:
            return max(1, i)
    return len(s)


def envolver(segs, ancho, sangria=0):
    """Segmentos → renglones de a lo más `ancho` columnas, por palabras (una palabra más larga se parte). Los
    renglones que siguen empiezan con `sangria` espacios."""
    ancho = max(sangria + 4, ancho)
    lineas, linea, col = [], [], 0

    def nuevo():
        return ([(" " * sangria, None, False)] if sangria else []), sangria
    for s, fg, b in segs:
        for tok in re.findall(r"\S+\s*|\s+", s):
            if col + P._ancho(tok.rstrip()) > ancho and col > sangria:
                lineas.append(linea)
                linea, col = nuevo()
                tok = tok.lstrip()
            while tok and P._ancho(tok.rstrip()) > ancho - col:
                k = _corte(tok, ancho - col)
                linea.append((tok[:k], fg, b))
                lineas.append(linea)
                linea, col = nuevo()
                tok = tok[k:]
            if tok:
                linea.append((tok, fg, b))
                col += P._ancho(tok)
    lineas.append(linea)
    return lineas


def parrafos(texto):
    """Los renglones del texto con los bloques ``` aparte: [(es_codigo, renglón)], sin vacíos repetidos ni en las
    orillas."""
    crudo = []
    partes = str(texto or "").split("```")
    for k, parte in enumerate(partes):
        if not k % 2:                                    # el salto que pega el texto a un bloque no es un renglón
            if k > 0 and parte.startswith("\n"):
                parte = parte[1:]
            if k < len(partes) - 1 and parte.endswith("\n"):
                parte = parte[:-1]
        if k % 2:
            ls = parte.split("\n")
            if len(ls) > 1 and re.match(r"^[A-Za-z0-9_-]*$", ls[0]):
                ls = ls[1:]                              # el lenguaje del bloque
            while ls and not ls[-1].strip():
                ls.pop()
            crudo += [(True, x) for x in ls]
        else:
            crudo += [(False, x) for x in parte.split("\n")]
    out = []
    for codigo, x in crudo:
        if not codigo and not x.strip():
            if out and (out[-1][0] or out[-1][1].strip()):
                out.append((False, ""))
            continue
        out.append((codigo, x))
    while out and not out[-1][0] and not out[-1][1].strip():
        out.pop()
    return out


def bloque(prefijo, pfg, texto, fg, ancho):
    """Un texto con su prefijo de 2 columnas («❯ », «● ») en su primer renglón y sangría de 2 en los demás."""
    L, primero = [], True
    for codigo, x in parrafos(texto):
        pre = (prefijo, pfg, False) if primero else ("  ", None, False)
        primero = False
        if codigo:
            L += envolver([pre, ("│ ", C["tx3"], False), (limpio(x), C["tx2"], False)], ancho, 4)
        elif not x.strip():
            L.append([])
        else:
            L += envolver([pre] + md(limpio(x), fg), ancho, 2)
    if primero:
        L.append([(prefijo, pfg, False)])
    return L


def _sub(texto, ancho):
    """Un renglón de lo que hizo («  ╰ …»), envuelto con sangría. (╰ y no ⎿: SF Mono y Menlo no traen ⎿, que caía a
    una fuente japonesa más ancha y se corría.)"""
    return envolver([("  ╰ ", C["tx3"], False), (limpio(texto), C["tx3"], False)], ancho, 4)


def _resuelto(p, ancho):
    return _sub(permiso_simple(p, True)[:-1] + " · " + PERMISO_HECHO.get(p.get("decision"), p.get("decision") or ""),
                ancho)


def _centro(texto, ancho, fg):
    pad = max(0, (ancho - P._ancho(texto)) // 2)
    return [(" " * pad + texto, fg, False)]


def lineas_sesion(x, ancho):
    """H3: lo que terminó una sesión oficial, en una línea de la conversación directa («◇ Terminó en Claude Code ·
    «Revisión»: lo último que dijo»)."""
    segs = [("◇ ", C["tx3"], False), ("Terminó en %s" % nombre_motor(x.get("motor")), C["tx2"], False)]
    if x.get("nombre"):
        segs.append((" · «%s»" % limpio(x["nombre"]), C["tx3"], False))
    if x.get("texto"):
        segs.append((": " + limpio(x["texto"]), C["tx3"], False))
    return envolver(segs, ancho, 2) + [[]]


def lineas_turno(t, a, ancho, ejec=()):
    """Un turno terminado de la conversación → renglones (con uno vacío al final)."""
    rol, texto = t.get("rol"), str(t.get("texto") or "")
    if rol == "yo":
        if ES_INSTRUCCION.search(texto):
            sk = next((e.get("skill") for e in ejec or () if e.get("id") and e["id"] in texto), "")
            L = [[("❯ ", C["tx3"], False), ("Usar la skill «%s»" % nombre_skill(sk) if sk else
                                            "La instrucción de una skill", C["tx3"], False)]]
        else:
            L = bloque("❯ ", C["tx3"], texto, C["tx"], ancho)
        if t.get("contexto"):
            L += _sub("le conté lo que hablaste con los otros motores", ancho)
    elif rol == "agente":
        if t.get("arranque"):
            return [_centro("· Listo con %s ·" % nombre_motor(t.get("motor")), ancho, C["tx3"]), []]
        herr, L = list(t.get("herr") or []), []
        if texto.strip():
            L = bloque("● ", a["c"], texto, P.T_FG, ancho)
        elif herr:
            L, herr = [[("● ", a["c"], False), (resumen_herr(herr), C["tx3"], False)]], []
        if herr:
            L += _sub(resumen_herr(herr), ancho)
        for p in t.get("permisos") or []:
            L += _resuelto(p, ancho)
        if not L:
            return []
    else:
        if not texto.strip():
            return []
        L = envolver([("  · ", C["tx3"], False), (limpio(texto), C["tx3"], False)], ancho, 4)
    return L + [[]]


def lineas_vivas(s, a, ancho):
    """Lo que pasa ahora (de la foto): lo que mandaste y aún no llega, el turno en curso con su herramienta, la cola y
    el error."""
    f = s.get("foto") or {}
    L = []
    cola = f.get("cola") or []
    p = s.get("pend")
    if p and p.get("cid") not in {x.get("id") for x in cola}:
        L += bloque("❯ ", C["tx3"], p["texto"], C["tx"], ancho)
        L += [[("  enviando…", C["tx3"], False)], []]
    if f.get("trabajando"):
        parcial = str(f.get("parcial") or "")
        espera = "espera que le contestes" if f.get("estado") == "esperandote" else "pensando…"
        L += (bloque("● ", a["c"], parcial, P.T_FG, ancho) if parcial.strip() else
              [[("● ", a["c"], False), (espera, C["tx3"], False)]])
        h = f.get("hace")
        if h:
            L += _sub(HERR_N.get(h.get("n"), h.get("n") or "?") + " · " + detalle_corto("", h.get("d"), h.get("f"))
                      if (h.get("d") or h.get("f")) else HERR_N.get(h.get("n"), h.get("n") or "?"), ancho)
        for r in f.get("resueltos") or []:
            L += _resuelto(r, ancho)
        L.append([])
    for x in cola:
        L += envolver([("  en cola · ", C["tx3"], False), ("«%s»" % P._corto(limpio(x.get("texto")), 200),
                                                          C["tx2"], False)], ancho, 4)
    err = f.get("error")
    if f.get("estado") == "error" and err:
        L += envolver([("✗ ", ERR, False), (P._corto(limpio(err.get("texto")), 300), ERR, False)], ancho, 2)
        if err.get("alternativa"):
            L += _sub("puedes seguir con %s: ^E" % nombre_motor(err["alternativa"]), ancho)
    while L and not L[-1]:
        L.pop()
    return L


_LINEAS = {}


def lineas_chat(s, ancho):
    """Toda la conversación del elegido a renglones: sus turnos (con «Siguió con X» donde cambió de motor) y lo de
    ahora. Se recuerda la última (cada cuadro de los monitos no la rehace)."""
    a = s["agentes"][s["sel"]]
    f = s.get("foto") or {}
    clave = (a["id"], ancho, id(s.get("turnos")), len(s.get("turnos") or ()), s.get("base"),
             json.dumps([f.get("estado"), f.get("trabajando"), f.get("parcial"), f.get("hace"), f.get("cola"),
                         f.get("resueltos"), f.get("error"), s.get("pend"), s.get("motores_conv"),
                         s.get("sesiones_conv")], sort_keys=True, default=str))
    if _LINEAS.get("clave") == clave:
        return _LINEAS["lineas"]
    base = s.get("base") or 0
    turnos = s.get("turnos") or []
    marcas = {m.get("i"): m.get("motor") for m in s.get("motores_conv") or [] if (m.get("i") or 0) > base}
    de_sesiones = {}
    for x in s.get("sesiones_conv") or []:
        i = x.get("i") if isinstance(x.get("i"), int) else base + len(turnos)
        if i >= base:
            de_sesiones.setdefault(min(i, base + len(turnos)), []).append(x)
    L = []
    for j, t in enumerate(turnos):
        for x in de_sesiones.get(base + j, ()):
            L += lineas_sesion(x, ancho)
        if base + j in marcas:
            L += [_centro("─── Siguió con %s ───" % nombre_motor(marcas[base + j]), ancho, C["tx3"]), []]
        L += lineas_turno(t, a, ancho, s.get("ejec") or ())
    for x in de_sesiones.get(base + len(turnos), ()):
        L += lineas_sesion(x, ancho)
    L += lineas_vivas(s, a, ancho)
    while L and not L[-1]:
        L.pop()
    _LINEAS.clear()
    _LINEAS.update(clave=clave, lineas=L)
    return L


# ── las pantallas ──────────────────────────────────────────────────────────────
def _geom(w):
    N = w < P.ANCHO_MIN
    bw = w - 2 if N else min(76, w - 4)
    return N, bw, (w - bw) // 2


def _anim(s, aid, st):
    """(fase del brinco, hacia dónde mira, qué punto se enciende) del monito `aid` en el cuadro `s["t"]`."""
    t, an = s.get("t") or 0.0, (s.get("anim") or {}).get(aid) or {}
    fase = None
    b = an.get("brinco")
    if b is not None and 0 <= t - b < P.BRINCO_S:
        fase = t - b
    fi = an.get("fiesta")
    if fase is None and fi is not None and 0 <= t - fi < FIESTA_S:
        fase = (t - fi) % P.BRINCO_S
    mira, puntos = 0, 2
    if st == "trabaja":
        k = int(t / PIENSA_S)
        mira, puntos = (0, 1, 0, -1)[k % 4], k % 3
    return fase, mira, puntos


def espera_cuadro(s):
    """Cada cuánto hay que volver a pintar los monitos (s), o None si están quietos (lo dice su juego de sprites)."""
    import hub_monitos
    e = hub_monitos.espera(s)
    try:
        import hub_inicio
        d = hub_inicio.destella(s)                    # el motor que acaba de cambiar destella
    except Exception:
        d = None
    if ((s.get("datos") or {}).get("conexiones_v") or {}).get("corriendo") and s.get("seccion"):
        d = min(d, 1.0) if d is not None else 1.0     # Conexiones: su avance mientras verifica
    e_agr = (s.get("agregar") or {}).get("espera")
    if e_agr is not None:                             # «Agregar agente»: su monito festeja o piensa, y sus pasos
        d = min(d, e_agr) if d is not None else e_agr
    v = s.get("s1")
    if v and not v.get("quieto"):                     # la entrada a S-1: sus cuadros
        import hub_s1
        if 0 <= (s.get("t") or 0) - v["t0"] < hub_s1.ENTRADA_S:
            d = min(d, 1 / 16.0) if d is not None else 1 / 16.0
    return min(x for x in (e, d) if x is not None) if (e is not None or d is not None) else None


def _monitos(T, s, w, N, y=2, L=None):
    """La fila de monitos (la de hoy): en el hub lateral, solo con menos de ANCHO_COMPACTO columnas. Con `L`, cada
    monito se toca (zona riel:<i>)."""
    ag, sel = s["agentes"], s["sel"]
    S, sp = 8, (9 if N else 13)
    vis = P._ventana(len(ag), sel, (w - 1) // sp)
    x0 = (w - sp * len(vis)) // 2 + (sp - S) // 2 + (1 if N else 0)
    for k, i in enumerate(vis):
        b, x = ag[i], x0 + k * sp
        on = i == sel
        hov = L.reg(x - 2, y - 1, S + 4, S // 2 + 4, "riel:%d" % i) if L else False
        import hub_monitos
        hub_monitos.dibujar(T, b, x, y, S, s=s, st=b["st"])
        T.center(x - 2, S + 4, y + S // 2 + 1, b["n"], C["tx"] if (on or hov) else C["tx3"], on)
        if on:
            T.center(x - 2, S + 4, y + S // 2 + 2, "━━━━" if N else "━━━━━━", b["c"])
    if vis[0] > 0:
        T.put(0, y + 2, "‹", C["tx3"])
    if vis[-1] < len(ag) - 1:
        T.put(w - 1, y + 2, "›", C["tx3"])


ESTADO_T = {"trabajando": "trabajando…", "esperandote": "te espera", "termino": "terminó", "libre": "libre",
            "dormido": "sin abrir", "error": "con un problema"}


def _encabezado(T, s, bx, bw, y, L=None):
    """«─ Zenith · Claude Code ▾ ─────── libre · 3 sesiones ─». Con `L`, el motor se toca (zona hdr:motor: abre el
    menú del motor) y se ilumina con el mouse encima."""
    a, f = s["agentes"][s["sel"]], s.get("foto") or {}
    T.hl(bx, y, bw, C["line"])
    x = T.put(bx + 1, y, " ")
    x = T.put(x, y, a["n"], a["c"], True)
    motor = nombre_motor(f.get("motor") or a.get("mid"))
    if L is None:
        x = T.put(x, y, " · ", C["tx3"])
        x = T.put(x, y, motor, C["tx2"])
    else:
        x = T.put(x, y, " ·", C["tx3"])
        lab = " %s ▾ " % motor
        hov = L.reg(x, y, P._ancho(lab), 1, "hdr:motor")
        bg = P.LIT if L.apr("hdr:motor") else (TILE_H if hov else P.T_BG)
        x = T.put(x, y, lab, C["tx"] if hov else C["tx2"], False, bg)
    cm = f.get("cambio")
    if cm and cm.get("paso") not in ("listo", "error") and cm.get("motor"):
        x = T.put(x, y, " → " + nombre_motor(cm["motor"]), C["tx2"])
    if L is None:
        T.put(x, y, " ")
    if s.get("hub_viejo"):
        der, col = HUB_VIEJO, ERR
    elif not s.get("conectado", True):
        der, col = "sin conexión con la página", ERR
    elif s.get("scroll"):
        der, col = "viendo lo de antes · AvPág baja", C["tx3"]
    elif s.get("pregunta") and not s.get("permiso"):
        der, col = "te pregunta", C["tx3"]
    else:
        der, col = ESTADO_T.get(f.get("estado"), ""), C["tx3"]
    cabe = bx + bw - 1 - x - 3
    ses = texto_sesiones(f.get("sesiones"))
    if ses and col != ERR:                            # sus sesiones oficiales (H3), si caben
        con = "%s · %s" % (der, ses) if der else ses
        der = con if P._ancho(con) <= cabe else der
    if der and P._ancho(der) <= cabe:
        T.right(bx + bw - 1, y, " %s " % der, col)


def texto_sesiones(c):
    """«2 sesiones · 1 trabaja» (la cuenta de la foto), o ''."""
    if not c or not c.get("n"):
        return ""
    t = "%d sesi%s" % (c["n"], "ón" if c["n"] == 1 else "ones")
    if c.get("te_espera"):
        t += " · %d te espera%s" % (c["te_espera"], "n" if c["te_espera"] > 1 else "")
    elif c.get("trabajando"):
        t += " · %d trabaja%s" % (c["trabajando"], "n" if c["trabajando"] > 1 else "")
    return t


def _linea(T, x, y, segs, limite):
    for s, fg, b in segs:
        if x >= limite:
            return
        k = _corte(s, limite - x) if P._ancho(s) > limite - x else len(s)
        x = T.put(x, y, s[:k], fg, b)


def _linea_corta(T, x, y, segs, limite):
    """Como _linea, pero si no cabe todo, lo último que se ve es «…»."""
    total = sum(P._ancho(s) for s, _fg, _b in segs)
    if x + total <= limite:
        _linea(T, x, y, segs, limite)
        return
    _linea(T, x, y, segs, limite - 1)
    T.put(limite - 1, y, "…", C["tx3"])


def _caja(T, x, y, w, alto, a, titulo):
    T.box(x, y, w, alto, a["c"])
    T.put(x + 2, y, " %s " % titulo, C["tx"], True)


def vigente_de(foto, ahora=None):
    """La skill que corre según la foto de su agente (con la regla del servidor si la trae)."""
    foto = foto or {}
    return vigente(foto.get("ejecuciones") or [], ahora, foto.get("skill_vigente", SIN_REGLA))


def vigente_en(s):
    """La skill que corre del agente elegido, en una instantánea (Directo.instantanea: `ejec` y `skill_vigente`)."""
    return vigente(s.get("ejec") or (), s.get("ahora"), s.get("skill_vigente", SIN_REGLA))


DETENER = " Detener "
SEGUIR, CERRAR = " Seguir ", " Cerrar "


def pendiente_en(s):
    """skills-cierre · decisión del 22-nov: la skill que se pausó en silencio porque le escribiste otra cosa a media
    pregunta (la más nueva de la conversación, sin cerrar, de las últimas 6 h), o None. Abajo dice «Quedó pendiente:
    ¿…? · Seguir · Cerrar»; solo vuelve a preguntar con Seguir."""
    ejec = list(s.get("ejec") or ())
    e = ejec[0] if ejec else None
    p = (e or {}).get("pausa") or {}
    if not e or e.get("estado") != "pausada" or p.get("motivo") != "otro_mensaje" or not p.get("pendiente") \
            or p.get("cerrada") or e.get("id") in (s.get("cerradas_skill") or ()):
        return None
    t = _ts(e.get("actualizado") or e.get("creado"))
    ahora = time.time() if s.get("ahora") is None else s["ahora"]
    return e if not t or ahora - t < 6 * 3600 else None


def franja_pendiente(e, a, w):
    """(1, dibujar): «? Quedó pendiente: ¿…?» con «Seguir» y «Cerrar» al final (zonas `in:seguir:<id>` e
    `in:cerrar:<id>`)."""
    def dibujar(T, x, y, L=None):
        der = x + w
        if L is not None and e.get("id"):
            for lab, que in ((CERRAR, "cerrar"), (SEGUIR, "seguir")):
                der -= len(lab) + 1
                hov = L.reg(der, y, len(lab), 1, "in:%s:%s" % (que, e["id"]))
                T.put(der, y, lab, (a["c"] if que == "seguir" else C["tx"]) if hov or que == "seguir" else C["tx2"],
                      hov or que == "seguir")
        _linea(T, x + 1, y, [("? ", a["c"], True), ("Quedó pendiente: ", C["tx2"], False),
                             (limpio((e.get("pausa") or {}).get("pendiente")), C["tx"], False)], der - 1)
    return 1, dibujar


def franja_skill(e, a, w):
    """(1, dibujar): la skill que corre, en una franja: su nombre, en qué paso va, su avance y (skills-cierre) su
    «Detener» al final, que se toca con el mouse (la zona `in:detener:<id>`; Enter en la caja vacía no la toca)."""
    pasos = e.get("pasos") or []
    hechos = sum(1 for p in pasos if p.get("estado") == "done")
    ahora = next((p for p in pasos if p.get("estado") == "now"), None) or \
        next((p for p in pasos if p.get("estado") != "done"), None)
    txt = (ahora or {}).get("texto") or ("" if pasos else ("Armando el plan" if e.get("estado") == "arrancando"
                                                          else "Leyendo lo que le pediste"))

    def dibujar(T, x, y, L=None):
        n = len(pasos)
        der = x + w
        if L is not None and e.get("id") and w >= 40:
            der -= len(DETENER) + 1
            hov = L.reg(der, y, len(DETENER), 1, "in:detener:" + str(e["id"]))
            T.put(der, y, DETENER, C["tx"] if hov else C["tx2"], hov)
        barra = ("▰" * min(10, hechos * 10 // n if n else 0)).ljust(10, "▱") if n else ""
        if barra:
            T.put(der - 11, y, barra[:barra.count("▰")], a["c"])
            T.put(der - 11 + barra.count("▰"), y, barra[barra.count("▰"):], C["line"])
        lim = der - (13 if barra else 1)
        segs = [("▸ ", a["c"], True), (nombre_skill(e.get("skill")), C["tx"], True)]
        if n:
            segs.append((" · paso %d de %d" % (min(n, hechos + 1), n), C["tx3"], False))
        if txt:
            segs.append((" · " + limpio(txt), C["tx2"], False))
        _linea(T, x + 1, y, segs, lim)
    return 1, dibujar


ESTADO_SES = {"trabajando": ("●", "trabajando"), "te_espera": ("?", "te espera"), "abierta": ("○", "abierta"),
              "cerrada": ("·", "cerrada")}


def hace(ts, ahora=None):
    """«hace 3 min» de una hora UTC con Z; '' si no se entiende."""
    try:
        t = _dt.datetime.fromisoformat(str(ts).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError):
        return ""
    d = max(0, int((time.time() if ahora is None else ahora) - t))
    return ("ahora" if d < 60 else "hace %d min" % (d // 60) if d < 3600 else "hace %d h" % (d // 3600)
            if d < 86400 else "hace %d d" % (d // 86400))


def _cola_vista(t, mx):
    """Lo último de lo escrito que cabe en `mx` columnas (con «…» si no cabe todo); los saltos, como ↵."""
    t = limpio(t.replace("\r\n", "\n").replace("\n", "↵"))
    if P._ancho(t) <= mx:
        return t
    k = len(t)
    while k > 0 and P._ancho(t[k - 1:]) <= mx - 1:
        k -= 1
    return "…" + t[k:]


# ── la pantalla: la piel T-2 «Bloque» (hub_bloque) y sus secciones (hub_secciones) ─────
#: Los menús que bajan de la barra: lo que se elige en cada uno empieza con su prefijo.
MENU_P = ("menu", "mo", "se", "ag", "sk", "mn", "tb")


def rid_tab(f):
    """La zona de una fila del menú «+» (H4-a)."""
    t = f.get("tipo")
    if t == "nueva":
        return "tb:nueva:" + (f.get("motor") or "")
    if t == "sesion":
        return "tb:s:" + f["slug"]
    return "tb:" + str(t)


def estado_riel(a, ahora=None, corto=False):
    """El estado del monito en palabras (§4): (texto, color, negrita). Solo «te pregunta» va en su color: es lo
    único que pide atención."""
    st = a.get("st")
    if st == "trabaja":
        return "trabajando…", C["tx2"], False
    if st == "pregunta":
        return "te pregunta", a["c"], True
    if st == "termino":
        d = a.get("desde")
        if corto or not isinstance(d, (int, float)):
            return "terminó", C["tx2"], False
        m = int(max(0.0, (time.time() if ahora is None else ahora) - d) // 60)
        return ("terminó ahora" if m < 1 else "terminó hace %d min" % m), C["tx2"], False
    if st == "duerme":
        return "sin abrir", C["tx3"], False
    if st == "error":
        return "con un problema", ERR, True
    return "libre", C["tx3"], False


def motor_riel(s, i, con_uso=True):
    """El motor de un agente del riel: el de su conversación directa (si se sabe) y, del elegido, su uso."""
    b = s["agentes"][i]
    m = (s.get("foto") or {}).get("motor") if i == s["sel"] else None
    t = nombre_motor(m or b.get("motor") or b.get("mid"))
    uso = s.get("uso") if i == s["sel"] else None
    if con_uso and isinstance(uso, (int, float)):
        t += " · %d%%" % uso
    return t


def _puerta_dev(nombre):
    """¿Copia de desarrollo con la variable de antes `nombre` puesta (para comparar lo de antes)? En una instalación de
    cliente, nunca: ahí esas variables ya no hacen nada (puertas.variable)."""
    try:
        import puertas
        return puertas.variable(nombre)
    except Exception:
        return False


def piel():
    """«h1» (H-1 «Marco relleno», el hub que se acomoda al ancho: la de hoy, la única de un cliente) o «bloque» (T-2,
    la de antes: solo en una copia de desarrollo con WORKSPACE_HUB_PIEL=bloque, para comparar)."""
    return "bloque" if _puerta_dev("WORKSPACE_HUB_PIEL") else "h1"


def pantalla_directa(w, h, s):
    """La pantalla del hub: H-1 (riel, conversación y panel del agente, según el ancho). `s`: Directo.instantanea()
    (o un ejemplo). → Term, con `zonas` (lo que se toca con el mouse), `riel` (la ventana del riel), `scroll_max` y
    `geo` (sus medidas). (La T-2 «Bloque» de antes vive en puertas_dev, que no viaja.)"""
    if piel() == "bloque":
        return __import__("puertas_dev").bloque(w, h, s)
    if s.get("agregar"):                              # «Agregar agente»: la tarjeta en Inicio (hub_agregar)
        import hub_agregar
        return hub_agregar.pantalla(w, h, s)
    if s.get("s1"):                                   # S-1, sus sesiones oficiales, en el mismo hub (H2-a)
        return pantalla_s1(w, h, s)
    if s.get("guia") and s.get("inicio") and not s.get("seccion"):   # la guía (H5-a), sobre Inicio
        import hub_guia
        import hub_inicio
        return hub_guia.pantalla(w, h, s, hub_inicio.pantalla(w, h, dict(s, guia=None, sobre="", apretado=None)))
    if s.get("inicio") and not s.get("seccion"):      # la portada: Inicio I-1
        import hub_inicio
        return hub_inicio.pantalla(w, h, s)
    import hub_h1
    return hub_h1.pantalla(w, h, s)


def _monito_en(T, s, aid):
    """(x, y, tam) del monito de `aid` en una pantalla ya pintada: la tarjeta grande de Inicio o su lugar en el riel.
    None si no se ve."""
    for x, y, zw, zh, rid in reversed(getattr(T, "zonas", None) or ()):
        if rid == "ini:card:" + aid:
            return (x, y, 16 if zw >= 16 else 8)
    i = next((n for n, b in enumerate(s.get("agentes") or ()) if b["id"] == aid), None)
    for x, y, zw, zh, rid in reversed(getattr(T, "zonas", None) or ()):
        if i is not None and rid == "riel:%d" % i and zh >= 5:
            return (x + 3, y + 1, 8)
    return None


def pantalla_s1(w, h, s):
    """S-1 en el hub: la lista de sus sesiones oficiales con su monito (hub_s1.pantalla). Al abrirla, una sola
    transición: lo de antes se apaga, el monito viaja a su lugar y las filas entran en cascada (hub_s1.entrada)."""
    import hub_s1
    v = s["s1"]
    fondo = ((s.get("datos") or {}).get("preferencias") or {}).get("fondo")
    Tf = hub_s1.pantalla(w, h, v["d"], s.get("sobre") or "", s.get("apretado"), crudo=True)
    edad = (s.get("t") or 0) - v["t0"]
    if v.get("quieto") or not 0 <= edad < hub_s1.ENTRADA_S or Tf.monito is None:
        T = P.afinar(Tf, fondo)
    else:
        base = dict(s, s1=None, sobre="", apretado=None)
        try:
            if base.get("inicio") and not base.get("seccion"):
                import hub_inicio
                Ti = hub_inicio.pantalla(w, h, base, crudo=True)
            else:
                import hub_h1
                Ti = hub_h1.pantalla(w, h, base, crudo=True)
        except Exception:
            Ti = None
        a = next((b for b in s.get("agentes") or () if b["id"] == v["agente"]), v["d"]["a"])
        T = hub_s1.entrada(Ti, Tf, dict(a, st="libre"), edad, _monito_en(Ti, base, v["agente"]) if Ti else None,
                           fondo, {"t": s.get("t"), "anim": {}, "agentes": [dict(a, st="libre")]})
    T.zonas = list(Tf.zonas)
    T.scroll_max, T.riel, T.lado, T.focos = 0, None, True, []
    T.geo = {"nivel": "s1", "panel": None, "franja": None, "cajon": None}
    return T


def pantalla_espera(w, h, texto):
    """Mientras se busca (o se prende) la página: la barra y el fondo de la piel T-2, y una línea."""
    import hub_bloque as B
    T = P.Term(w, h)
    T.fill(0, 0, w, h, B.BG)
    bh = 3 if h >= B.ALTO_BARRA else 1
    T.fill(0, 0, w, bh, B.P1)
    x = T.put(2, 1 if bh == 3 else 0, "❯", C["tx2"], True)
    T.put(x + 1, 1 if bh == 3 else 0, "workspace", C["tx"], True)
    T.center(0, w, h // 2, P._corto(texto, w - 4), C["tx2"])
    return T


# ── el hub: lo que sabe de la conversación directa y lo que hace cada tecla ─────
def _hilo(fn):
    threading.Thread(target=fn, name="hub-accion", daemon=True).start()


def _tope_campo(sec):
    """Cuánto cabe en el campo de una sección: la ruta de un cerebro (Agentes › Esta máquina), un evento (120) o un
    nombre (40)."""
    import hub_agentes_maquina as HM
    return HM.tope(sec, 120 if (sec or {}).get("kind") == "calendario" else 40)


class Directo:
    """El estado de la pantalla: lo que llega del servidor (las fotos y las conversaciones) y lo tuyo de esta
    pantalla (lo escrito, el agente elegido, lo que mandaste y aún no llega). Sin terminal: las pruebas lo manejan
    con teclas y un servidor falso. `en_fondo(fn)`: dónde corre lo que habla con el servidor (por omisión, un hilo:
    abrir un motor puede tardar y la pantalla no se congela)."""

    def __init__(self, srv, agentes, reloj=time.monotonic, ahora=time.time, en_fondo=None):
        self.srv = srv
        self.d = {"agentes": list(agentes)}
        self.lock = threading.RLock()
        self.fotos, self.conv, self.uso = {}, {}, {}
        #: skills-cierre: lo que cerraste de «Quedó pendiente» (se quita de la vista sin esperar la foto)
        self.cerradas_skill = set()
        self.motores, self.motores_t = None, 0.0
        self.v, self.e = "", ""
        self.sel, self.texto, self.scroll, self.elige = 0, "", 0, 0
        self.menu, self.aviso = None, None
        self.ses, self.ses_lista, self.confirma = None, {}, None     # ^S: sus sesiones oficiales (H3)
        self.pend, self.ocultos, self.anim = {}, {}, {}
        self.conectado = True
        self.reloj, self.ahora = reloj, ahora
        self.en_fondo = en_fondo or _hilo
        # el reposo (Escucha): la última tecla o clic, si la terminal dice que está al frente (None: no lo dice),
        # si un motor tiene su terminal, y lo que lo despierta
        self.actividad, self.en_frente, self.en_frente_t, self.cedido = reloj(), None, reloj(), False
        self.despierta = threading.Event()
        # el relevo de la página tras una actualización: este hub es de antes que ella, y si hay que renovarla
        self.hub_viejo = bool(getattr(srv, "hub_viejo", False))
        self.pide_renovar, self.renovar_t, self.repedir = False, -1e9, False
        # el hub (T-2): el menú de la barra que no es ^E ni ^S (agentes, skills, «≡ Menú»), el mouse (dónde está y
        # dónde bajó el botón), las zonas del último cuadro, la ventana del riel, el riel con nombres (se recuerda en
        # `prefs_ruta`) y su borde mientras se arrastra, y la sección abierta (Sesiones, Skills, Motores…)
        self.barra = None
        self.sobre, self.apretado = "", None
        self.zonas, self.riel_vista, self.ancho, self.sec_lado = [], None, 200, True
        self.riel0, self.riel_nombres, self.arrastre, self.prefs_ruta = None, None, None, None
        self.raton_posible = self.raton_on = False
        self.skills_todas, self.skills_cargando = None, False
        self.seccion = None
        self.ses_todas, self.ses_todas_t, self.ses_todas_cargando, self.ses_todas_error = {}, None, False, ""
        self.datos, self.cargando, self.errores = {}, set(), {}      # motores, conexiones, info, inicio
        self.sin_ruta = set()                                         # escrituras que la página prendida no trae
        self.idioma, self.idiomas = "", []
        # H-1: el panel del agente (cerrado a su franja: se recuerda), el cajón (el panel encima, pantalla media), el
        # nivel del último cuadro (XL/L/M/S) y qué se ve del panel (para pedir sus datos solo si se ve)
        self.panel_cerrado, self.cajon, self.nivel, self.panel_visto = False, False, "", False
        self.ses_cargando = set()
        # Inicio (I-1): el hub abre en la portada; `ini_foco` es la tarjeta o el mosaico elegido con ←→↑↓
        self.inicio, self.ini_foco, self.ini_focos = piel() != "bloque", "", []
        # el foco (H-1): la zona enfocada (Enter = su clic), las zonas que se enfocan [(área, rid, x, y, w, h)], lo
        # último enfocado de cada área (Tab regresa ahí), lo que buscas en Inicio y el salto por letras del riel
        self.foco, self.focos_z, self.foco_mem, self.ini_busca, self.salto = "", [], {}, "", ("", 0.0)
        # Inicio R-1: buscando (con / o un clic en buscar, aunque no lleves nada) y el motor elegido con ↑↓ que todavía
        # no está listo (no se cambia: Enter hace lo que necesita, p. ej. iniciar sesión)
        self.ini_buscando, self.ini_motor = False, {}
        self.foco_auto = True
        self.falla_t = {}                                             # cuándo falló cada pedido del fondo (respiro)
        # S-1 en el hub (H2-a): la lista de sus sesiones oficiales; su programa no arranca hasta que eliges
        self.s1 = None
        # la guía (H5-a): el paso en que va ({"paso": n}) o None; si ya se vio una vez (se recuerda en prefs_ruta)
        self.guia, self.guia_vista = None, False
        # H4-a «pestañas en el borde»: la foto de cada agente tal como llega (con su tira y la de cada pestaña; en
        # `fotos` va la de la pestaña que ves), la pestaña que ves de cada uno, la recién abierta (aún sin foto), el
        # menú «+», la última que cerraste (para «Deshacer») y lo escrito en cada pestaña
        self.crudas, self.tab_sel, self.tab_pend = {}, {}, {}
        self.tabmenu, self.deshacer, self.borradores = None, None, {}
        #: El último archivar o quitar de un agente, para su «Deshacer» (hub_agentes_maquina): {nombre, texto, t}.
        self.apartado = None
        # «Agregar agente» (hub_agregar): la tarjeta abierta (o creando en el fondo) y si en Inicio está al centro el
        # agente dormido del final de la fila (el que se toca para crear uno)
        self.agregar, self.ini_nuevo = None, False

    # ── lo que se lee ──
    def agente(self):
        ag = self.d["agentes"]
        return ag[self.sel] if ag else None

    def id_elegido(self):
        a = self.agente()
        return a["id"] if a else ""

    def _permiso(self, aid):
        pm = (self.fotos.get(aid) or {}).get("permiso")
        return pm if pm and not (pm.get("id") and self.ocultos.get(aid) == pm.get("id")) else None

    def _pregunta(self, aid):
        q = (self.fotos.get(aid) or {}).get("pregunta")
        return q if q and self.ocultos.get(aid) != q.get("id") else None

    def _trabaja(self, aid):
        return bool((self.fotos.get(aid) or {}).get("trabajando"))

    def _avisar(self, texto):
        with self.lock:
            self.aviso = (texto, self.reloj())

    # ── el reposo: un hub que no está al frente no deja long-polls abiertos ──
    def actividad_ahora(self):
        self.actividad = self.reloj()
        self.despierta.set()

    def poner_frente(self, al_frente):
        """Lo que dice la terminal (foco: «\\x1b[I» / «\\x1b[O»)."""
        self.en_frente, self.en_frente_t = bool(al_frente), self.reloj()
        if al_frente:
            self.actividad_ahora()

    def en_reposo(self):
        """¿Nadie lo está viendo? Un motor tiene su terminal; o la terminal dice que está en segundo plano (desde
        hace REPOSO_FOCO_S); o, si la terminal no lo dice, nadie tocó una tecla en REPOSO_S y su agente no trabaja."""
        if self.cedido:
            return True
        ahora = self.reloj()
        if self.en_frente is False:
            return ahora - self.en_frente_t >= REPOSO_FOCO_S
        if self.en_frente is True:
            return False
        # la terminal no lo dice: sin teclas en REPOSO_S… salvo que su agente trabaje (lo estás viendo trabajar)
        return ahora - self.actividad >= REPOSO_S and not self._trabaja(self.id_elegido())

    # ── el relevo de la página tras una actualización ──
    def tras_renovar(self, srv, aviso=RENOVADA):
        """La página de hoy en lugar de la de antes: lo que falló por «ruta desconocida» se vuelve a pedir. `aviso`:
        su línea (None: ninguna, la renovó otro)."""
        with self.lock:
            self.srv = srv
            self.sin_ruta.clear()
            for k in list(self.errores):
                self.datos.pop(k, None)
                self.falla_t.pop(k, None)
            self.errores.clear()
            self.pide_renovar = False
            self.hub_viejo = bool(getattr(srv, "hub_viejo", False))
            self.v, self.e = "", ""                   # otra época: la foto entera otra vez
            self.repedir = True                       # la sección abierta, otra vez (en el siguiente cuadro)
        if aviso:
            self._avisar(aviso)

    # ── H4-a: las pestañas de cada agente (las guarda Workspace: las mismas en la página) ──
    def tira(self, aid):
        f = self.crudas.get(aid) or {}
        return list(f.get("tabs") or []) or [{"slug": NAV, "nombre": "Conversación", "tipo": NAV}]

    def tab_de(self, aid):
        """La pestaña que ves de `aid`: la elegida si sigue en su tira (o se acaba de abrir); si no, ⌂."""
        t = self.tab_sel.get(aid) or NAV
        if t == NAV:
            return NAV
        if any(x.get("slug") == t for x in self.tira(aid)):
            return t
        pe = self.tab_pend.get(aid)
        return t if pe and pe[0] == t and self.reloj() - pe[1] < TAB_PEND_S else NAV

    def _k(self, aid):
        """La llave de su conversación (en `conv` y `pend`): el agente, la de siempre (como siempre); (agente,
        pestaña), la de otra pestaña. La misma forma que las sesiones del servidor de la página."""
        t = self.tab_de(aid)
        return aid if t == NAV else (aid, t)

    def _efectiva(self, aid, f):
        """La foto de lo que ves: la de su pestaña, con lo que es del agente (su perfil, sus pendientes). Las skills
        corren en ⌂: en otra pestaña no salen."""
        t = self.tab_de(aid)
        if not f or t == NAV:
            return f
        x = (f.get("tab_fotos") or {}).get(t) or {"estado": "libre", "existe": True, "viva": False, "cola": [],
                                                  "motor": "", "tab": t}
        return dict(x, perfil=f.get("perfil"), pend=f.get("pend"), sesiones=f.get("sesiones"), tabs=f.get("tabs"),
                    tab_fotos=f.get("tab_fotos"), ejecuciones=[], skill_vigente="", revision=None)

    def _con_tab(self, aid, cuerpo):
        """Lo que se le hace a su conversación va a la pestaña que ves (sin `tab`, la de siempre)."""
        t = self.tab_de(aid)
        return dict(cuerpo, tab=t) if t != NAV else cuerpo

    def _tira_vista(self, aid):
        """La tira para dibujarla: cada pestaña con su estado de ahora."""
        f = self.crudas.get(aid) or {}
        tf = f.get("tab_fotos") or {}
        out = []
        for x in self.tira(aid):
            sl = x.get("slug")
            ft = f if sl == NAV else (tf.get(sl) or {})
            out.append({"slug": sl, "nombre": x.get("nombre") or sl, "motor": ft.get("motor") or x.get("motor") or "",
                        "estado": ft.get("estado") or x.get("estado") or "", "terminal": bool(x.get("terminal")),
                        "solo_mirar": bool(x.get("solo_mirar") or ft.get("solo_mirar"))})
        t = self.tab_de(aid)
        if t != NAV and not any(x["slug"] == t for x in out):     # recién abierta: ya se ve
            out.append({"slug": t, "nombre": t, "motor": "", "estado": "", "terminal": False, "solo_mirar": False})
        return out

    def elegir_tab(self, aid, slug, recien=False):
        """Ves otra pestaña de `aid` (lo escrito se queda con la suya). `recien`: se acaba de abrir y su foto todavía
        no llega."""
        slug = slug or NAV
        with self.lock:
            if recien and slug != NAV:
                self.tab_pend[aid] = (slug, self.reloj())
            antes = self.tab_de(aid)
            self.tab_sel[aid] = slug
            ahora = self.tab_de(aid)
            if aid == self.id_elegido() and antes != ahora:
                self.borradores[(aid, antes)] = self.texto
                self.texto = self.borradores.pop((aid, ahora), "")
            f = self.crudas.get(aid)
            if f is not None:
                self.fotos[aid] = self._efectiva(aid, f)
            self.scroll, self.elige = 0, 0
            c = self.conv.get(self._k(aid))
            leer = c is None or c.get("fv") != (self.fotos.get(aid) or {}).get("conv")
        if leer:
            self.en_fondo(lambda: self.leer_conversacion(aid))

    def _mover_tab(self, aid, d):
        tira = self.tira(aid)
        i = next((n for n, x in enumerate(tira) if x.get("slug") == self.tab_de(aid)), 0)
        self.elegir_tab(aid, tira[(i + d) % len(tira)].get("slug"))

    def _abrir_tabs(self):
        """«+» (Ctrl+T): una conversación nueva (con su motor) o una de sus sesiones (la lista de S-1)."""
        a = self.agente()
        if a is None:
            return
        aid = a["id"]
        self._cerrar_menus()
        self.tabmenu = {"agente": aid, "i": 0, "filas": []}
        hit = self.ses_lista.get(aid)
        self.tabmenu["cargando"] = hit is None
        self._filas_tabs()

        def leer():
            self.leer_sesiones(aid, callado=True)
            with self.lock:
                if self.tabmenu is not None and self.tabmenu.get("agente") == aid:
                    self.tabmenu["cargando"] = False
                    self._filas_tabs()
        if hit is None or self.reloj() - hit[0] > SESIONES_S:
            self.en_fondo(leer)
        if self.motores is None or self.reloj() - self.motores_t > MOTORES_S:
            def cargar():
                try:
                    m = self.srv.get("/api/sistema/motores").get("motores") or []
                except ErrorServidor:
                    return
                with self.lock:
                    self.motores, self.motores_t = m, self.reloj()
                    if self.tabmenu is not None:
                        self._filas_tabs()
            self.en_fondo(cargar)

    def _filas_tabs(self):
        """Las filas del menú «+»: deshacer (si cerraste una hace poco), nueva (con el motor de siempre y con otros),
        sus sesiones (las mismas de su programa oficial) y «Todas sus sesiones…» (S-1)."""
        m = self.tabmenu
        aid = m["agente"]
        a = next((x for x in self.d["agentes"] if x["id"] == aid), {})
        base = a.get("mid") or ""
        filas = []
        dz = self.deshacer
        if dz and dz.get("agente") == aid and self.reloj() - dz["t"] < DESHACER_S:
            filas.append({"tipo": "deshacer", "nombre": dz.get("nombre") or ""})
        filas.append({"tipo": "nueva", "motor": base})

        def usable(mo):
            return bool(mo.get("listo")) and mo.get("sesion") is not False and mo.get("estado") != "sin_sesion"
        for mo in [x for x in self.motores or [] if usable(x) and x.get("id") != base][:4]:
            filas.append({"tipo": "nueva", "motor": mo["id"], "otra": True})
        abiertas = {x.get("slug") for x in self.tira(aid)}
        for r in (self.ses_lista.get(aid) or (0, []))[1]:
            if r.get("slug"):
                filas.append({"tipo": "sesion", "slug": r["slug"], "nombre": r.get("nombre") or r["slug"],
                              "motor": r.get("motor") or "", "estado": r.get("estado") or "",
                              "cuando": r.get("cuando") or "", "ya": r["slug"] in abiertas})
        filas.append({"tipo": "todas"})
        m["filas"] = filas
        m["i"] = max(0, min(m.get("i", 0), len(filas) - 1))

    def _tecla_tabmenu(self, k):
        m = self.tabmenu
        n = len(m["filas"])
        if k == "esc":
            self.tabmenu = None
        elif k in ("arriba", "abajo") and n:
            m["i"] = (m["i"] + (1 if k == "abajo" else -1)) % n
        elif k == "enter" and n:
            return self._accion_tab(m["filas"][m["i"]])
        return None

    def _accion_tab(self, f):
        aid = self.tabmenu["agente"] if self.tabmenu else self.id_elegido()
        self.tabmenu = None
        t = f.get("tipo")
        if t == "todas":
            self._abrir_s1(self.sel)
            return None
        if t == "sesion" and f.get("ya"):
            self.elegir_tab(aid, f["slug"])
            return None
        if t == "deshacer":
            ruta, cuerpo = "/api/v2/tab/deshacer", {"agente": aid}
        elif t == "nueva":
            ruta, cuerpo = "/api/v2/tab/abrir", {"agente": aid, "nueva": True, "motor": f.get("motor") or ""}
        else:
            ruta, cuerpo = "/api/v2/tab/abrir", {"agente": aid, "slug": f["slug"]}
        self._avisar("Abriendo…")

        def hacer():
            try:
                r = self.srv.post(ruta, cuerpo)
            except ErrorServidor as e:
                self._avisar(e.texto)
                return
            with self.lock:
                self.aviso = None
                if t == "deshacer":
                    self.deshacer = None
                if (r or {}).get("tab"):
                    self.elegir_tab(aid, r["tab"].get("slug"), recien=True)
                c = (r or {}).get("cerrada")
                if c:
                    self.deshacer = {"agente": aid, "nombre": c.get("nombre") or "", "t": self.reloj()}
                    self._avisar("Cerré «%s», la que llevabas más tiempo sin ver. No se borró." % (c.get("nombre") or ""))
        self.en_fondo(hacer)
        return None

    def _cerrar_tab(self, aid, slug):
        """Cierra la pestaña (no borra nada: sigue en sus sesiones y en su programa), con «Deshacer»."""
        if not slug or slug == NAV:
            self._avisar("La conversación de siempre no se cierra.")
            return
        tira = self.tira(aid)
        i = next((n for n, x in enumerate(tira) if x.get("slug") == slug), 0)
        if self.tab_de(aid) == slug:
            self.elegir_tab(aid, (tira[i - 1] if i > 0 else tira[0]).get("slug"))

        def hacer():
            try:
                r = self.srv.post("/api/v2/tab/cerrar", {"agente": aid, "tab": slug})
            except ErrorServidor as e:
                self._avisar(e.texto)
                return
            c = (r or {}).get("cerrada")
            if c:
                with self.lock:
                    self.deshacer = {"agente": aid, "nombre": c.get("nombre") or slug, "t": self.reloj()}
                self._avisar("Cerré «%s». No se borró: sigue en sus sesiones." % (c.get("nombre") or slug))
        self.en_fondo(hacer)

    def _ir_terminal(self, aid):
        """«Ir a la terminal» de la pestaña que ves: su terminal (se enfoca, o se abre con su lanzador)."""
        cuerpo = self._con_tab(aid, {"agente": aid})

        def hacer():
            try:
                r = self.srv.post("/api/v2/terminal", cuerpo)
            except ErrorServidor as e:
                self._avisar(e.texto)
                return
            d = (r or {}).get("donde") or {}
            if d.get("ventana"):                    # Windows: en una ventana de la terminal, no en el hub
                self._avisar("Ya está abierta en otra ventana." if (r or {}).get("estado") == "ya"
                             else "Abrí su terminal en una ventana nueva.")
                return
            donde = ("pestaña «%s»" % d["pestana"]) if d.get("pestana") else ""
            self._avisar({"enfocada": "La enfoqué", "ya": "Ya está abierta"}.get((r or {}).get("estado"),
                                                                              "Abriendo su terminal") +
                         (" en el hub: " + donde if donde else " en el hub") + ".")
        self.en_fondo(hacer)

    def _deshacer_tab(self):
        dz = self.deshacer
        if dz:
            self.tabmenu = {"agente": dz["agente"], "i": 0, "filas": []}
            self._accion_tab({"tipo": "deshacer"})

    def _tecla_tabs(self, k):
        """Las teclas de las pestañas, en la conversación. → NO si no es una de ellas."""
        a = self.agente()
        if a is None or self.inicio or self.seccion is not None:
            return NO
        aid = a["id"]
        if k == "ctrl-t":
            self._abrir_tabs()
        elif k == "ctrl-w":
            self._cerrar_tab(aid, self.tab_de(aid))
        elif k in ("ctrl-izquierda", "ctrl-derecha"):
            self._mover_tab(aid, 1 if k == "ctrl-derecha" else -1)
        elif isinstance(k, str) and k.startswith("alt-") and k[4:].isdigit():
            tira = self.tira(aid)
            i = int(k[4:]) - 1
            if 0 <= i < len(tira):
                self.elegir_tab(aid, tira[i].get("slug"))
        else:
            return NO
        return None

    def instantanea(self):
        """Todo lo que la pantalla necesita, de una vez (bajo el candado)."""
        if self.repedir:                              # la página se renovó: lo de la sección abierta, otra vez
            self.repedir = False
            kind = (self.seccion or {}).get("kind")
            if kind:
                try:
                    self._pedir_seccion(kind)
                except Exception:
                    pass
        with self.lock:
            ag = []
            for b in self.d["agentes"]:
                fb = self.fotos.get(b["id"]) or {}
                ult = next((x.get("texto") for x in reversed((self.conv.get(self._k(b["id"])) or {}).get("turnos")
                                                             or [])
                            if x.get("rol") == "agente" and str(x.get("texto") or "").strip()), "")
                ag.append(dict(b, st=st_de(self.fotos.get(b["id"])), motor=fb.get("motor") or b.get("mid"),
                               desde=fb.get("desde"), ultimo=" ".join(str(ult).split())[:200]))
            aid = self.id_elegido()
            f = dict(self.fotos.get(aid) or {})
            c = self.conv.get(self._k(aid)) or {}
            t = c.get("turnos") or []
            agr = self._vista_agregar()
            sel = self.sel
            if self.inicio and self.seccion is None and piel() != "bloque":
                import hub_agregar                    # AG4-a: al final de la fila duerme uno gris para crear otro
                ag.append(hub_agregar.dormido())
                if self.ini_nuevo or len(ag) == 1:
                    sel = len(ag) - 1
            av = self.aviso
            arr = self.arrastre or {}
            return {"barra": dict(self.barra) if self.barra else None, "sobre": self.sobre,
                    "apretado": self.apretado, "riel0": self.riel0, "riel_nombres": self.riel_nombres,
                    "riel_w": (arr["x"] + 1) if arr.get("x") is not None else None,
                    "seccion": dict(self.seccion) if self.seccion else None,
                    "ses_todas": {k: list(v) for k, v in self.ses_todas.items()},
                    "ses_todas_cargando": self.ses_todas_cargando, "ses_todas_error": self.ses_todas_error,
                    "datos": {k: v[1] for k, v in self.datos.items()}, "cargando": sorted(self.cargando),
                    "errores": dict(self.errores), "idioma": self.idioma, "idiomas": list(self.idiomas),
                    "sin_ruta": sorted(self.sin_ruta),
                    "fotos_ajustes": {k: (v or {}).get("ajustes") for k, v in self.fotos.items()},
                    "raton": self.raton_on, "raton_posible": self.raton_posible,
                    "skills": self._skills_vista(aid), "skills_cargando": self.skills_cargando,
                    "panel_cerrado": self.panel_cerrado, "cajon": self.cajon,
                    "inicio": self.inicio, "ini_foco": self.foco if self.inicio else self.ini_foco,
                    "foco": self.foco if piel() != "bloque" else "", "foco_area": self._area_foco(),
                    "ini_busca": self.ini_busca, "ini_buscando": self.ini_buscando,
                    "ini_motor": dict(self.ini_motor),
                    "sin_riel": self.inicio and self.seccion is not None,
                    "skills_todas_n": None if self.skills_todas is None else len(self.skills_todas[1]),
                    "panel_ses": list(self.ses_lista[aid][1]) if aid in self.ses_lista else None,
                    "panel_skills": None if self.skills_todas is None else
                    [x for x in self.skills_todas[1] if x.get("agente") == aid],
                    "agentes": ag, "sel": sel, "texto": self.texto, "foto": f, "turnos": t,
                    "base": max(0, (c.get("total") or len(t)) - len(t)), "motores_conv": c.get("motores") or [],
                    "sesiones_conv": c.get("sesiones") or [],
                    "pend": self.pend.get(self._k(aid)), "permiso": self._permiso(aid),
                    "pregunta": self._pregunta(aid),
                    # H4-a: la tira de la conversación, la pestaña que ves, el menú «+» y «Deshacer»
                    "tira": self._tira_vista(aid) if aid else [], "tab": self.tab_de(aid) if aid else NAV,
                    "tabmenu": dict(self.tabmenu, filas=list(self.tabmenu["filas"])) if self.tabmenu else None,
                    # archivar y quitar un agente: su «Deshacer», y con quién hay una conversación abierta aquí
                    "apartado": dict(self.apartado) if self.apartado else None,
                    "ini_arch_i": getattr(self, "ini_arch_i", 0),
                    "conversando": sorted(k for k, v in self.fotos.items()
                                          if (v or {}).get("estado") not in (None, "", "dormido")),
                    "deshacer": dict(self.deshacer) if self.deshacer and self.deshacer.get("agente") == aid and
                    self.reloj() - self.deshacer["t"] < AVISO_S else None,
                    "menu": self.menu, "sesiones": self.ses, "scroll": self.scroll, "elige": self.elige,
                    "conectado": self.conectado, "hub_viejo": self.hub_viejo,
                    # el de un hub de antes que la página no se va (hasta que lo reabran)
                    "aviso": av[0] if av and self.reloj() - av[1] < AVISO_S else (HUB_VIEJO if self.hub_viejo else (
                        _tp("puertas.hub.sin_pagina_corto", SIN_PAGINA_CORTO)
                        if getattr(self.srv, "sin_pagina", False) else "")),
                    "anim": {k: dict(v) for k, v in self.anim.items()}, "t": self.reloj(), "ahora": self.ahora(),
                    "hora": time.strftime("%H:%M"), "uso": (self.uso.get(aid) or (0, None))[1],
                    "ejec": f.get("ejecuciones") or [],
                    "skill_vigente": f.get("skill_vigente", SIN_REGLA),
                    "cerradas_skill": sorted(self.cerradas_skill), "s1": self._s1_vista(),
                    "guia": dict(self.guia) if self.guia else None,
                    "agregar": agr, "ini_nuevo": self.ini_nuevo, "vecinos": len(self.d["agentes"])}

    def tope_scroll(self, n):
        with self.lock:
            self.scroll = max(0, min(self.scroll, n))

    # ── lo que llega del servidor ──
    def aplicar_vivo(self, d):
        """Una respuesta de /api/v2/vivo. → los agentes cuya conversación hay que leer ya (la del elegido, si
        cambió)."""
        with self.lock:
            self.conectado = True
            if not d.get("agentes") and not d.get("completo"):
                self.v, self.e = d.get("v", self.v), d.get("e", self.e)
                return []
            previo = self.fotos
            crudas = {} if d.get("completo") else dict(self.crudas)
            crudas.update(d.get("agentes") or {})
            self.crudas = crudas
            nuevas = {aid: self._efectiva(aid, f) for aid, f in crudas.items()}     # H4-a: la de la pestaña que ves
            for aid, f in nuevas.items():
                antes = previo.get(aid) or {}
                if antes.get("estado") in ("trabajando", "esperandote") and f.get("estado") == "termino":
                    self.anim.setdefault(aid, {})["fiesta"] = self.reloj()      # terminó: celebra
                oc = self.ocultos.get(aid)
                if oc and oc not in ((f.get("permiso") or {}).get("id"), (f.get("pregunta") or {}).get("id")):
                    self.ocultos.pop(aid, None)                                 # ya no está: lo que venga se ve
            self.fotos = nuevas
            self.v, self.e = d.get("v", ""), d.get("e", "")
            aid = self.id_elegido()
            c = self.conv.get(self._k(aid)) if aid else None
            return [aid] if aid and (c is None or c.get("fv") != (nuevas.get(aid) or {}).get("conv")) else []

    def leer_conversacion(self, aid):
        """La conversación de `aid` por versión (solo lo que cambió). → True si se leyó."""
        with self.lock:
            k = self._k(aid)                          # H4-a: la de la pestaña que ves
            c0 = self.conv.get(k)
            fv = (self.fotos.get(aid) or {}).get("conv")
        q = {"agente": aid, "slug": NAV if k == aid else k[1]}
        if c0 and c0.get("v"):
            q["v"] = c0["v"]
        try:
            r = self.srv.get("/api/v2/conversacion", **q)
        except ErrorServidor:
            return False
        with self.lock:
            d = juntar(self.conv.get(k), r)
            if d is not self.conv.get(k):
                d = dict(d)
            d["fv"] = fv
            self.conv[k] = d
            self._pend_llego(aid, k)
        return True

    def _pend_llego(self, aid, k=None):
        k = k or self._k(aid)
        p = self.pend.get(k)
        if not p:
            return
        c = self.conv.get(k) or {}
        t = c.get("turnos") or []
        nuevos = t[max(0, len(t) - max(0, (c.get("total") or len(t)) - p["base"])):]
        aguja = _norm(p["texto"])[:40]
        if any(x.get("rol") == "yo" and aguja in _norm(x.get("texto")) for x in nuevos) or \
                self.ahora() - p["ts"] > PENDIENTE_S:
            self.pend.pop(k, None)

    def refrescar_uso(self):
        """El % de su plan que lleva el motor del elegido (como la Paleta: la barra de Claude Code, los límites de
        Codex), cada USO_S."""
        aid = self.id_elegido()
        hit = self.uso.get(aid)
        if not aid or (hit and self.reloj() - hit[0] < USO_S):
            return
        motor = (self.fotos.get(aid) or {}).get("motor") or (self.agente() or {}).get("mid")
        self.uso[aid] = (self.reloj(), P._uso(aid, motor))

    # ── las teclas ──
    def tecla(self, k):
        """→ None (sigue), «salir», o el plan de «Abrir en su motor» (para entregarlo al cliente oficial)."""
        if isinstance(k, P.Raton):
            r = self.raton(k)
            return None if r is SIN_CAMBIO else r
        with self.lock:
            self.foco_auto = False                    # lo moviste tú (o tecleaste): el foco ya no se acomoda solo
            if self.agregar is not None and self.agregar.visible:   # «Agregar agente»: la tarjeta
                return self._de_agregar(self.agregar.tecla(k))
            if self.s1 is not None:                   # S-1 en el hub: sus teclas (las de siempre de S-1)
                return self._tecla_s1(k)
            if self.guia is not None:                 # la guía: siguiente, atrás o sale
                return self._tecla_guia(k)
            if isinstance(k, P.Pegado):               # antes que nada: pegar «esc» no es la tecla Esc
                if self.menu is None and self.ses is None and (self.barra is None or self._slash()) and \
                        (self.seccion is None or self.seccion.get("editando")):
                    if self.seccion is not None:
                        buf = self.seccion.get("buf", "") + k.replace("\r", " ").replace("\n", " ")
                        self.seccion["buf"] = buf[:_tope_campo(self.seccion)]
                    else:
                        self.texto += k.replace("\r\n", "\n").replace("\r", "\n")
                return None
            if k == "esc" and (self.seccion or {}).get("borrar"):
                return self._accion_calendario("cancelar-borrado")
            if k == "esc" and (self.seccion or {}).get("usuario_edicion"):
                return self._accion_usuario("cancelar", None)
            if k == "ctrl-c":
                return "salir"
            if k == "f1":                             # la ayuda (otra vez F1: de vuelta)
                self._accion_barra("ayuda")
                return None
            if k == "ctrl-b":                         # el riel con nombres, o solo los monitos
                self._alternar_riel()
                return None
            if self.menu is not None:
                return self._tecla_menu(k)
            if self.tabmenu is not None:             # H4-a: el menú «+» de las pestañas
                return self._tecla_tabmenu(k)
            if self.ses is not None:
                return self._tecla_ses(k)
            if self.barra is not None:
                return self._tecla_barra(k)
            if self.cajon and k == "esc":             # el panel encima (pantalla media): Esc lo cierra
                self.cajon = False
                return None
            if piel() != "bloque":
                r = self._tecla_tabs(k)               # H4-a: Ctrl+T, Ctrl+W, Ctrl+←/→, Alt+1…9
                if r is not NO:
                    return r
                r = self._tecla_foco(k)
                if r is not NO:
                    return r
            if self.seccion is not None:
                return self._tecla_seccion(k)
            if self.inicio:
                return self._tecla_inicio(k)
            a = self.agente()
            if a is None:
                return "salir" if k == "esc" else None
            aid = a["id"]
            pm, q = self._permiso(aid), self._pregunta(aid)
            ops = opciones_de(pm, q)
            if k == "esc":
                if self.texto:
                    self.texto = ""
                elif self._trabaja(aid):
                    self._parar(a)
                elif piel() != "bloque":              # H-1: Esc sale de la caja (al riel); otra vez, a Inicio
                    if self.foco == "in:texto" and any(z[1] == "riel:%d" % self.sel for z in self.focos_z):
                        self.foco = "riel:%d" % self.sel
                    else:
                        self._ir_inicio()
                else:
                    return "salir"
            elif k in ("tab", "shift-tab"):
                self._elegir(self.sel + (1 if k == "tab" else -1))
            elif k in ("izquierda", "derecha"):
                if ops:
                    self.elige = (self.elige + (1 if k == "derecha" else -1)) % len(ops)
            elif k in ("arriba", "repag"):
                self.scroll += 1 if k == "arriba" else PAGINA
            elif k in ("abajo", "avpag"):
                self.scroll = max(0, self.scroll - (1 if k == "abajo" else PAGINA))
            elif k == "ctrl-e":
                self._abrir_menu()
            elif k == "ctrl-s" and piel() != "bloque":   # sus sesiones son de su programa oficial: S-1 (en el hub)
                self._abrir_s1(self.sel)
            elif k == "ctrl-s":
                self._abrir_sesiones()
            elif k == "ctrl-o":
                return self._plan_abrir()
            elif k == "enter":
                self._enter(a, pm, q, ops)
            elif k == "borrar":
                self.texto = self.texto[:-1]
            elif k == "ctrl-u":
                self.texto = ""
            elif k == "/" and not self.texto:         # con la caja vacía: sus skills (lo que sigues escribiendo filtra)
                self._abrir_skills(slash=True)
            elif len(k) == 1 and k.isprintable():
                self.texto += k
            return None

    def _elegir(self, i, seguir=True):
        """Elige al agente `i` (brinca). `seguir`: la ventana del riel lo sigue (con Tab; con un clic, el riel se queda
        donde está)."""
        n = len(self.d["agentes"])
        if not n:
            return
        if seguir:
            self.riel0 = None
        self.ini_nuevo = False
        self.sel, self.scroll, self.elige = i % n, 0, 0
        aid = self.id_elegido()
        self.anim.setdefault(aid, {})["brinco"] = self.reloj()
        c = self.conv.get(self._k(aid))
        if c is None or c.get("fv") != (self.fotos.get(aid) or {}).get("conv"):
            self.en_fondo(lambda: self.leer_conversacion(aid))

    def _enter(self, a, pm, q, ops):
        t = self.texto.strip()
        if pm and not t:
            if ops:
                self._contestar(a, pm, ops[self.elige % len(ops)])
            return
        if q and not q.get("en_terminal") and (t or ops):
            self._responder(a, q, t or ops[self.elige % len(ops)])
            self.texto = ""
            return
        if t:
            self._mandar(a, t)

    def _mandar(self, a, t):
        aid, cid = a["id"], "h" + secrets.token_hex(6)
        k = self._k(aid)
        c = self.conv.get(k) or {}
        self.pend[k] = {"texto": t, "ts": self.ahora(), "base": c.get("total") or 0, "cid": cid}
        self.texto, self.scroll = "", 0
        cuerpo = self._con_tab(aid, {"agente": aid, "texto": t, "cid": cid})

        def hacer():
            try:
                self.srv.post("/api/v2/mandar", cuerpo)
            except ErrorServidor as e:
                if e.tiempo:
                    # Fix 5: su motor sigue abriendo y tu mensaje sale solo: no vuelve a la caja (se mandaba dos veces)
                    self._avisar("Abriendo su motor… tu mensaje sale en cuanto abra.")
                    return
                with self.lock:
                    if (self.pend.get(k) or {}).get("cid") == cid:
                        self.pend.pop(k, None)
                    if not self.texto and self.id_elegido() == aid:
                        self.texto = t                  # lo que escribiste vuelve a la caja
                self._avisar("No salió: " + e.texto)
        self.en_fondo(hacer)

    def _contestar(self, a, pm, decision):
        aid = a["id"]
        self.ocultos[aid], self.elige = pm.get("id"), 0
        cuerpo = self._con_tab(aid, {"agente": aid, "id": pm.get("id"), "decision": decision})

        def hacer():
            try:
                self.srv.post("/api/v2/permiso", cuerpo)
            except ErrorServidor as e:
                with self.lock:
                    if self.ocultos.get(aid) == pm.get("id"):
                        self.ocultos.pop(aid, None)
                self._avisar(e.texto)
        self.en_fondo(hacer)

    def _responder(self, a, q, texto):
        aid = a["id"]
        self.ocultos[aid], self.elige = q.get("id"), 0
        k = self._k(aid)
        c = self.conv.get(k) or {}
        self.pend[k] = {"texto": texto, "ts": self.ahora(), "base": c.get("total") or 0,
                        "cid": "rq-" + str(q.get("id"))[-12:]}
        cuerpo = self._con_tab(aid, {"agente": aid, "id": q.get("id"), "texto": texto})

        def hacer():
            try:
                self.srv.post("/api/v2/responder", cuerpo)
            except ErrorServidor as e:
                if e.tiempo:                          # Fix 5: tu respuesta sale en cuanto abra su motor
                    self._avisar("Abriendo su motor… tu respuesta sale en cuanto abra.")
                    return
                with self.lock:
                    if self.ocultos.get(aid) == q.get("id"):
                        self.ocultos.pop(aid, None)
                    self.pend.pop(k, None)
                self._avisar(e.texto)
        self.en_fondo(hacer)

    def _parar(self, a):
        aid = a["id"]
        self._avisar("Le pedí a %s que pare." % a["n"])
        cuerpo = self._con_tab(aid, {"agente": aid})

        def hacer():
            try:
                self.srv.post("/api/v2/parar", cuerpo)
            except ErrorServidor as e:
                self._avisar(e.texto)
        self.en_fondo(hacer)

    def _abrir_menu(self):
        if self.motores is not None and self.reloj() - self.motores_t < MOTORES_S:
            self._menu_nuevo()
            return
        self._avisar("Viendo qué motores están listos…")

        def cargar():
            try:
                m = self.srv.get("/api/sistema/motores").get("motores") or []
            except ErrorServidor as e:
                self._avisar("No pude ver los motores: " + e.texto)
                return
            with self.lock:
                self.motores, self.motores_t = m, self.reloj()
                self.aviso = None
                self._menu_nuevo()
        self.en_fondo(cargar)

    def _menu_nuevo(self):
        """Los motores que de verdad pueden contestar (instalados y con sesión) arriba; los demás, atenuados."""
        def usable(m):
            return bool(m.get("listo")) and m.get("sesion") is not False and m.get("estado") != "sin_sesion"
        ok = [{"id": m["id"], "nombre": m.get("nombre") or nombre_motor(m["id"]), "ok": True}
              for m in self.motores or [] if usable(m)]
        no = [{"id": m["id"], "nombre": m.get("nombre") or nombre_motor(m["id"]), "ok": False,
               "sub": "sin sesión iniciada" if (m.get("sesion") is False or m.get("estado") == "sin_sesion")
               else (m.get("estado_texto") or "no está listo")} for m in self.motores or [] if not usable(m)]
        if not ok:
            self._avisar("No hay un motor listo para esta conversación.")
            return
        actual = (self.fotos.get(self.id_elegido()) or {}).get("motor") or (self.agente() or {}).get("mid")
        i = next((n for n, r in enumerate(ok) if r["id"] == actual), 0)
        self.menu = {"filas": ok + no, "i": i, "n": len(ok)}

    def _tecla_menu(self, k):
        """El menú del motor: sus motores que pueden contestar y, al final, «Motores y conexiones →» (i == n)."""
        m = self.menu
        if k == "esc":
            self.menu = None
        elif k == "arriba":
            m["i"] = (m["i"] - 1) % (m["n"] + 1)
        elif k == "abajo":
            m["i"] = (m["i"] + 1) % (m["n"] + 1)
        elif k == "enter":
            if m["i"] >= m["n"]:
                self.menu = None
                self._abrir_seccion("motores")
                return None
            fila = m["filas"][m["i"]]
            self.menu = None
            a = self.agente()
            if a and fila["id"] != ((self.fotos.get(a["id"]) or {}).get("motor") or a.get("mid")):
                self._cambiar_motor(a, fila)
        return None

    def _cambiar_motor(self, a, fila):
        aid = a["id"]
        self._avisar("Cambiando a %s…" % fila["nombre"])
        cuerpo = self._con_tab(aid, {"agente": aid, "motor": fila["id"]})

        def hacer():
            try:
                r = self.srv.post("/api/v2/motor", cuerpo)
            except ErrorServidor as e:
                self._avisar(e.texto + (" Esc lo para; luego cambia de motor." if e.status == 409 else ""))
                return
            if (r or {}).get("nueva") and (r or {}).get("tab"):
                # H4-a: una sesión de su programa es de su motor: siguió en una pestaña nueva, con lo hablado
                self.elegir_tab(aid, r["tab"].get("slug"), recien=True)
                self._avisar("Seguí con %s en una pestaña nueva («%s»), con lo que hablaron." % (
                    fila["nombre"], r["tab"].get("nombre") or ""))
                return
            self._avisar("Sigue con %s: la misma conversación." % fila["nombre"])
        self.en_fondo(hacer)

    # ── ^S: sus sesiones oficiales (H3), aparte de la conversación directa ──
    def leer_sesiones(self, aid, callado=False):
        """La lista de /api/v2/sesiones (la recuerda por agente). `callado`: la pide el panel (sin aviso si falla).
        → True si se leyó."""
        try:
            lista = self.srv.get("/api/v2/sesiones", agente=aid).get("sesiones") or []
        except ErrorServidor as e:
            with self.lock:
                self.ses_cargando.discard(aid)
                self.falla_t["ses:" + aid] = self.reloj()
                if self.ses is not None and self.ses.get("agente") == aid:
                    self.ses["cargando"] = False
            if not callado:
                self._avisar("No pude ver sus sesiones: " + e.texto)
            return False
        with self.lock:
            self.ses_cargando.discard(aid)
            self.ses_lista[aid] = (self.reloj(), lista)
            if self.ses is not None and self.ses.get("agente") == aid:
                self._filas_ses(lista)
        return True

    def _filas_ses(self, lista):
        """Su conversación directa, sus sesiones, «Nueva sesión» (lo mismo que ^O) y «Todas las sesiones →» (la
        sección). La elegida sigue elegida si sigue ahí; si no, «Nueva sesión»."""
        m = self.ses
        antes = m["filas"][m["i"]] if m.get("filas") and m["i"] < len(m["filas"]) else {}
        m["filas"] = ([{"tipo": "conv"}] + [dict(x, tipo="sesion") for x in lista if x.get("wid")] +
                      [{"tipo": "nueva"}, {"tipo": "seccion"}])
        m["cargando"] = False
        nueva = len(m["filas"]) - 2
        if antes.get("tipo") == "sesion":
            m["i"] = next((n for n, r in enumerate(m["filas"]) if r.get("wid") == antes.get("wid")), nueva)
        elif antes.get("tipo") in ("conv", "seccion"):
            m["i"] = next(n for n, r in enumerate(m["filas"]) if r.get("tipo") == antes["tipo"])
        else:
            m["i"] = nueva

    def _abrir_sesiones(self):
        aid = self.id_elegido()
        if not aid:
            return
        hit = self.ses_lista.get(aid)
        self.ses, self.confirma = {"agente": aid, "i": 1, "filas": [{"tipo": "conv"}, {"tipo": "nueva"},
                                                                     {"tipo": "seccion"}],
                                   "cargando": hit is None}, None
        if hit:
            self._filas_ses(hit[1])
        self.en_fondo(lambda: self.leer_sesiones(aid))

    def _tecla_ses(self, k):
        m = self.ses
        if k == "esc":
            self.ses, self.confirma = None, None
        elif k in ("arriba", "abajo"):
            m["i"] = (m["i"] + (1 if k == "abajo" else -1)) % len(m["filas"])
            self.confirma = None
        elif k == "enter":
            r = m["filas"][m["i"]]
            if r["tipo"] == "conv":                   # la de aquí: ya estás en ella
                self.ses, self.confirma = None, None
                self._cerrar_seccion()
                return None
            if r["tipo"] == "seccion":
                self.ses, self.confirma = None, None
                self._abrir_seccion("sesiones")
                return None
            if r["tipo"] == "nueva":
                self.ses = None
                return self._plan_abrir()
            return self._retomar(r, self.sel)
        return None

    def _retomar(self, r, i):
        """Retomar la sesión `r` del agente `i`. Si sigue abierta en su terminal, pide un segundo Enter (o clic): así
        no quedan dos clientes en la misma sesión sin querer."""
        if r.get("estado") != "cerrada" and self.confirma != r.get("wid"):
            self.confirma = r.get("wid")
            self._avisar("«%s» sigue abierta en su terminal: Enter (o clic) otra vez la abre también aquí."
                         % (limpio(r.get("nombre")) or "Esa sesión"))
            return None
        self.ses, self.confirma = None, None
        return self._plan_sesion(r, i)

    def _plan_sesion(self, r, i=None):
        """Retomar una sesión oficial: su pestaña (`--open`/`--name`, como la abre tmux) con SU motor."""
        i = self.sel if i is None else i
        p = P.plan({"tipo": "abrir", "agente": i, "texto": ""}, self.d["agentes"], motor=r.get("motor") or None)
        p["argv"] += ["--open", r["wid"]] + (["--name", r["nombre"]] if r.get("nombre") else [])
        p["sesion"] = r.get("nombre") or ""
        return p

    def _plan_abrir(self, i=None):
        """«Abrir en su motor»: el cliente oficial, con el motor de esta conversación y lo escrito como primer
        mensaje (si su motor lo acepta al abrir). Con `i`: el agente `i`, sin mensaje (una sesión nueva suya)."""
        if i is None:
            a, t, i = self.agente(), self.texto.strip(), self.sel
        else:
            ag = self.d["agentes"]
            a, t = (ag[i] if 0 <= i < len(ag) else None), ""
        if a is None:
            return None
        motor = (self.fotos.get(a["id"]) or {}).get("motor") or a.get("mid")
        return P.plan({"tipo": "enviar" if t else "abrir", "agente": i, "texto": t}, self.d["agentes"], motor=motor)

    # ── S-1 en el hub (H2-a «La lista vive en el hub») ──
    # Sus sesiones oficiales las pinta el hub con la lista que Inicio ya trae (/api/v2/sesiones); ningún programa
    # arranca hasta que eliges. Al elegir, su programa oficial con `--open <wid> --name <nombre>` (como tmux y la
    # página): sin «Cargando…», sin el letrero y sin el menú del motor. Archivar, deshacer, las archivadas y «+ Nueva
    # sesión» (con su nombre) también son de aquí, por el mismo registro que el menú de siempre (sessions_registry).
    def _abrir_s1(self, i=None, nueva=False):
        """Abre S-1 del agente `i` (el elegido si no). `nueva`: directo a escribir el nombre de una sesión nueva."""
        i = self.sel if i is None else i
        ag = self.d["agentes"]
        if not 0 <= i < len(ag):
            return None
        a = ag[i]
        self._cerrar_menus()
        aid = a["id"]
        lista, edad = None, None
        if aid in self.ses_todas:                     # la que trae Inicio
            lista = self.ses_todas[aid]
            edad = self.reloj() - self.ses_todas_t if self.ses_todas_t is not None else None
        elif aid in self.ses_lista:                   # la del panel
            edad, lista = self.reloj() - self.ses_lista[aid][0], self.ses_lista[aid][1]
        try:
            import hub_monitos_m1
            quieto = hub_monitos_m1.menos_movimiento()
        except Exception:
            quieto = False
        self.s1 = {"agente": aid, "i": i, "t0": self.reloj(), "vista": "lista", "aviso": "", "confirma": None,
                   "lista": list(lista or []), "cargando": lista is None, "n_arch": None, "arch": [],
                   "brain": a.get("brain") or "", "menu": None, "quieto": quieto, "abriendo": None}
        self._s1_menu()
        if nueva:
            self.s1["menu"].nombre = ""
        if lista is None or edad is None or not 0 <= edad < SES_TODAS_S:
            self.en_fondo(lambda: self._s1_leer(aid))  # se pone al día en su lugar
        brain = self.s1["brain"]
        if brain:
            self.en_fondo(lambda: self._s1_contar_archivadas(aid, brain))
        return None

    def _cerrar_s1(self):
        self.s1 = None
        self.sobre, self.apretado = "", None

    def _s1_items(self):
        st = self.s1
        if st["vista"] == "archivadas":
            return list(st["arch"]) or [("← Volver", "a tus sesiones", ("LIST", None, None))]
        items = [(limpio(r.get("nombre")) or "Sin nombre", "continuar", ("WS", r.get("wid"), r.get("nombre") or ""))
                 for r in st["lista"] if r.get("wid")]
        items.append(("+ Sesión nueva…", "crea una sesión con nombre", ("NEW", None, None)))
        if st.get("n_arch"):
            items.append(("Archivadas (%d)" % st["n_arch"], "las que quitaste del menú", ("ARCH", None, None)))
        return items

    def _s1_menu(self, de_nuevo=False):
        """Arma el menú de S-1 (hub_s1.Menu) con lo que se sabe; lo elegido y el nombre que escribes se quedan.
        `de_nuevo`: otra vista (la lista o las archivadas): desde la primera, como el menú de siempre."""
        import hub_s1 as S1
        st = self.s1
        viejo = st.get("menu")
        antes = viejo.items[viejo.sel][2] if viejo is not None and viejo.items and not de_nuevo else None
        items = self._s1_items()
        sel = 0
        if antes is not None:
            sel = next((n for n, it in enumerate(items) if tuple(it[2])[:2] == tuple(antes)[:2]),
                       next((n for n, it in enumerate(items) if it[2][0] == antes[0]), min(viejo.sel, len(items) - 1)))
        keys = ("au" if st["vista"] == "lista" else "u") if st["brain"] else ""
        m = S1.Menu(items, keys, sel, "ARCHIVADAS" if st["vista"] == "archivadas" else None, resumen=lambda *_: None)
        if st["vista"] == "lista":
            S1._completar_precarga(m, {str(r["wid"]): r for r in st["lista"] if r.get("wid")})
        if viejo is not None:
            m.nombre = viejo.nombre
        st["menu"] = m

    def _s1_vista(self):
        """Lo que pinta S-1 (bajo el candado), o None."""
        st = self.s1
        if st is None:
            return None
        a = next((b for b in self.d["agentes"] if b["id"] == st["agente"]), None)
        if a is None:
            return None
        motor = (self.fotos.get(a["id"]) or {}).get("motor") or a.get("mid")
        d = st["menu"].datos(dict(a, st="libre"), nombre_motor(motor), st["aviso"], self.ahora(), self.reloj())
        d["cargando"] = bool(st["cargando"]) and st["vista"] == "lista"
        return {"d": d, "t0": st["t0"], "agente": st["agente"], "quieto": st["quieto"]}

    def _s1_leer(self, aid):
        try:
            lista = self.srv.get("/api/v2/sesiones", agente=aid).get("sesiones") or []
        except ErrorServidor as e:
            with self.lock:
                st = self.s1
                if st is not None and st["agente"] == aid:
                    st["cargando"] = False
                    st["aviso"] = "No pude ver sus sesiones: " + e.texto
            return False
        with self.lock:
            self.ses_lista[aid] = (self.reloj(), lista)
            st = self.s1
            if st is not None and st["agente"] == aid:
                st["lista"], st["cargando"] = list(lista), False
                self._s1_menu()
        return True

    def _s1_contar_archivadas(self, aid, brain):
        try:
            import sessions_registry as reg
            n = len(reg.archivadas(brain, aid))
        except Exception:
            n = 0
        with self.lock:
            st = self.s1
            if st is not None and st["agente"] == aid and st["n_arch"] != n:
                st["n_arch"] = n
                self._s1_menu()

    def _s1_archivadas(self, aid, brain):
        """La vista de las archivadas (agent_ui.filas_archivadas: la misma del menú de siempre)."""
        try:
            import agent_ui
            items = agent_ui.filas_archivadas(brain, aid)
        except Exception:
            items = []
        with self.lock:
            st = self.s1
            if st is not None and st["agente"] == aid and st["vista"] == "archivadas":
                st["arch"] = list(items)
                self._s1_menu(de_nuevo=True)

    def _tecla_s1(self, k):
        st = self.s1
        m = st["menu"]
        if st.get("abriendo"):                        # ya eligió: su programa toma la terminal
            return None
        if isinstance(k, P.Pegado):
            if m.nombre is not None:
                m.nombre = (m.nombre + " ".join(str(k).split()))[:60]
            return None
        if k == "ctrl-c" and m.nombre is None:
            self._cerrar_s1()
            return None
        if isinstance(k, P.Raton):
            return None
        r = m.tecla(k)
        if r is None:
            st["aviso"], st["confirma"] = "", None
            return None
        return self._s1_resultado(r)

    def _clic_s1(self, zid):
        st = self.s1
        if st.get("abriendo") or not zid.startswith("pk:"):
            return None
        r = st["menu"].clic(zid)
        return None if r is None else self._s1_resultado(r)

    def _s1_resultado(self, r):
        """Lo que regresó S-1 (lo mismo que el menú de siempre): BACK, un índice, (tecla, índice) o («NUEVO», nombre)."""
        import hub_s1 as S1
        st = self.s1
        m = st["menu"]
        aid = st["agente"]
        if r == S1.BACK:
            if st["vista"] == "archivadas":
                st["vista"] = "lista"
                self._s1_menu(de_nuevo=True)
            else:
                self._cerrar_s1()
            return None
        if isinstance(r, tuple) and len(r) == 2 and r[0] == "NUEVO":
            return self._s1_abrir(None, r[1], nueva=True)
        if isinstance(r, tuple):
            self._s1_tecla_registro(r[0], r[1])
            return None
        if not 0 <= r < len(m.items):
            return None
        kind = tuple(m.items[r][2])
        if kind[0] == S1.ARCH:
            st["vista"], st["arch"] = "archivadas", []
            self._s1_menu(de_nuevo=True)
            brain = st["brain"]
            self.en_fondo(lambda: self._s1_archivadas(aid, brain))
            return None
        if kind[0] == S1.VOLVER:
            st["vista"] = "lista"
            self._s1_menu(de_nuevo=True)
            return None
        if kind[0] == "NEW":
            m.nombre = ""
            return None
        if kind[0] != "WS":
            return None
        wid, nombre = kind[1], kind[2] if len(kind) > 2 else m.items[r][0]
        if st["vista"] == "archivadas":               # Enter = la recupera y la abre
            try:
                import sessions_registry as reg
                reg.desarchivar(st["brain"], aid, nombre)
            except Exception:
                pass
            return self._s1_abrir(wid, nombre)
        fila = next((x for x in st["lista"] if str(x.get("wid")) == str(wid)), {})
        if fila.get("estado") in ("trabajando", "te_espera") and st.get("confirma") != wid:
            st["confirma"] = wid                       # sigue abierta en su terminal: un segundo Enter (o clic)
            st["aviso"] = ("«%s» sigue abierta en su terminal: Enter (o clic) otra vez la abre también aquí."
                           % (limpio(nombre) or "Esa sesión"))
            return None
        return self._s1_abrir(wid, nombre)

    def _s1_tecla_registro(self, tecla, i):
        """a: archiva la de la fila `i` (sale del menú en todas tus máquinas; nada se borra) · u: deshace el último."""
        st = self.s1
        m = st["menu"]
        aid, brain = st["agente"], st["brain"]
        if not brain:
            return
        kind = tuple(m.items[i][2]) if 0 <= i < len(m.items) else (None,)
        if tecla == "a" and (st["vista"] != "lista" or kind[0] != "WS"):
            return

        def hacer():
            import agent_ui
            import sessions_registry as reg
            if tecla == "a":
                ok = bool(reg.archivar(brain, aid, kind[2]))
                aviso = ("Archivada «%s» · u para deshacer" if ok else "No pude archivar «%s»") % kind[2]
                rec = []
            else:
                rec = reg.desarchivar_ultimas(brain, aid)
                ok, aviso = bool(rec), agent_ui._aviso_recuperadas(rec)
            with self.lock:
                if self.s1 is not st:
                    return
                st["aviso"] = aviso
                if ok and tecla == "a":
                    st["lista"] = [x for x in st["lista"] if str(x.get("wid")) != str(kind[1])]
                    if aid in self.ses_todas:
                        self.ses_todas[aid] = [x for x in self.ses_todas[aid] if str(x.get("wid")) != str(kind[1])]
                    st["n_arch"] = (st["n_arch"] or 0) + 1
                self._s1_menu()
            if ok and tecla == "u":
                self._s1_leer(aid)
                self._s1_contar_archivadas(aid, brain)
                if st["vista"] == "archivadas":
                    self._s1_archivadas(aid, brain)
        self.en_fondo(hacer)

    def _s1_abrir(self, wid, nombre, nueva=False):
        """El plan para abrir la sesión elegida en su programa oficial (el mismo motor de antes, cuando S-1 corría
        en él), con `--open <wid> --name <nombre>`. Una nueva lleva un id nuevo (como la página: nueva_pestana)."""
        import uuid
        st = self.s1
        nombre = " ".join(str(nombre or "").split()) or "General"
        p = self._plan_abrir(st["i"])
        if p is None:
            return None
        p["argv"] += ["--open", str(wid or uuid.uuid4()), "--name", nombre]
        p["sesion"], p["s1_hub"] = nombre, True
        st["abriendo"], st["quieto"] = nombre, True  # (si eliges a media entrada: la imagen completa de S-1)
        st["menu"].nombre = None
        st["aviso"] = "Abriendo %s en %s…" % ("«%s»" % nombre, nombre_motor(p.get("motor")))
        return p

    # ── los menús de la barra: agentes, skills y «≡ Menú» ──
    def _menu_abierto(self):
        return self.menu is not None or self.ses is not None or self.barra is not None or self.tabmenu is not None

    def _cerrar_menus(self):
        self.menu = self.ses = self.barra = self.tabmenu = None
        self.confirma = None

    def _slash(self):
        b = self.barra or {}
        return b.get("kind") == "skills" and bool(b.get("slash"))

    def _abrir_barra(self, kind):
        self._cerrar_menus()
        rid = {"agentes": "ag:%d" % self.sel, "menu": "mn:agentes"}.get(kind)
        self.barra = {"kind": kind, "rid": rid}

    def _filas_barra(self):
        """(rids que se eligen, la elegida) del menú de la barra abierto: lo mismo que se dibuja."""
        if self.barra is None:
            return [], ""
        import hub_bloque
        _t, _k, filas, _a, elegida = hub_bloque.filas_menu(self.barra["kind"], self.instantanea(), self.ancho)
        return [r["rid"] for r in filas if r.get("rid") and not r.get("dim")], elegida

    def _mover_barra(self, d):
        rids, cur = self._filas_barra()
        if rids:
            i = rids.index(cur) if cur in rids else -1
            self.barra["rid"] = rids[(i + d) % len(rids)]

    def _tecla_barra(self, k):
        m = self.barra
        if k == "esc":
            self.barra = None                         # con «/»: lo escrito se queda como texto normal
            return None
        if k in ("arriba", "abajo"):
            self._mover_barra(1 if k == "abajo" else -1)
            return None
        if k == "enter":
            _rids, cur = self._filas_barra()
            return self._accion_menu(cur) if cur else None
        if self._slash():                             # «/»: lo que escribes filtra sus skills
            if k == "borrar":
                self.texto = self.texto[:-1]
                if not self.texto.startswith("/"):
                    self.barra = None
                return None
            if k == "ctrl-u":
                self.texto, self.barra = "", None
                return None
            if isinstance(k, str) and len(k) == 1 and k.isprintable():
                self.texto += k
                m["rid"] = None
                return None
        self.barra = None                             # otra tecla: el menú se cierra y la tecla hace lo suyo
        return self.tecla(k)

    def _accion_barra(self, kind):
        """Lo que hace un botón de la barra (o su fila en «≡ Menú»): abre su menú (o lo cierra, si ya estaba
        abierto), abre su sección (Ajustes, Ayuda: otra vez, de vuelta a la conversación), abre su motor o sale."""
        if kind == "motor":
            if self.menu is not None:
                self.menu = None
            else:
                self._cerrar_menus()
                self._abrir_menu()
        elif kind == "sesiones":
            if self.ses is not None:
                self.ses, self.confirma = None, None
            else:
                self._cerrar_menus()
                self._abrir_sesiones()
        elif kind in ("agentes", "skills", "menu"):
            if (self.barra or {}).get("kind") == kind:
                self.barra = None
            elif kind == "skills":
                self._abrir_skills()
            else:
                self._abrir_barra(kind)
        elif kind in ("ajustes", "ayuda"):
            self._cerrar_menus()
            if (self.seccion or {}).get("kind") == kind:
                self._cerrar_seccion()
            else:
                self._abrir_seccion(kind)
        elif kind == "guia":                          # «? Guía» (Inicio, el pie del riel y la tecla ?)
            self._abrir_guia()
        elif kind == "abrir":
            self._cerrar_menus()
            return self._plan_abrir()
        elif kind == "inicio":
            self._ir_inicio()
        elif kind == "salir":
            return "salir"
        return None

    def _abrir_guia(self):
        """«? Guía» (o ?): el recorrido de cinco pasos sobre Inicio (hub_guia). Desde la conversación, a Inicio
        primero. Abrirla cuenta como vista: ya no sale sola."""
        self.s1 = None
        self._ir_inicio()
        self.guia = {"paso": 0}
        if not self.guia_vista:
            self.guia_vista = True
            self._guardar_prefs()

    def guia_primera_vez(self):
        """La primera vez que abres el hub (sin «guia» en sus preferencias), la guía se abre sola; una sola vez."""
        if piel() == "bloque":                        # la piel T-2 no tiene Inicio: el recorrido es de H-1
            return
        with self.lock:
            if not self.guia_vista and self.d["agentes"] and self.inicio:
                self._abrir_guia()

    def _tecla_guia(self, k):
        import hub_guia
        n = self.guia["paso"]
        if k in ("enter", "derecha", " "):
            if n + 1 >= len(hub_guia.PASOS):
                self.guia = None
            else:
                self.guia["paso"] = n + 1
        elif k in ("izquierda", "borrar"):
            self.guia["paso"] = max(0, n - 1)
        elif k in ("esc", "q", "?", "ctrl-c"):
            self.guia = None
        return None

    def _accion_menu(self, rid):
        """Enter (o clic) en una fila de un menú de la barra."""
        p, _s, resto = rid.partition(":")
        a = self.agente()
        if rid == "ag:nuevo":
            self.barra = None
            return self._abrir_agregar()
        if rid == "ag:riel":
            self.barra = None
            self._alternar_riel()
        elif rid == "ag:seccion":
            self.barra = None
            self._abrir_seccion("agentes")
        elif p == "ag" and resto.isdigit():
            self.barra = None
            self._elegir(int(resto))
            if self.seccion is not None:              # en una sección: la sección cambia a ese agente
                self._seccion_de(self.id_elegido())
        elif p == "sk":
            slash = self._slash()
            self.barra = None
            if resto == "pagina":
                self._abrir_pagina()
            elif resto == "seccion":
                self._abrir_seccion("skills")
            elif a is not None:
                if slash:
                    self.texto = ""
                self._arrancar_skill(a, resto)
        elif p == "mn":
            self.barra = None
            return self._accion_barra(resto)
        return None

    def _alternar_raton(self):
        if not self.raton_posible:
            self._avisar("Esta terminal no tiene mouse aquí (o WORKSPACE_MOUSE=0).")
            return
        self.raton_on = not self.raton_on
        self.sobre, self.apretado = "", None
        self._avisar("Mouse encendido." if self.raton_on else
                     "Mouse apagado: ya puedes seleccionar texto. En Ayuda (F1) lo prendes.")

    # ── el riel: compacto (solo monitos) o con nombres; se recuerda ──
    def _alternar_riel(self, nombres=None):
        ahora_ = self.riel_nombres if self.riel_nombres is not None else (self.nivel == "XL")
        self.riel_nombres = (not ahora_) if nombres is None else bool(nombres)
        self.sobre = ""
        self._guardar_prefs()

    def cargar_prefs(self, ruta):
        """Lo que se recuerda entre sesiones (hoy: el riel con nombres) en `ruta` (un json chico de esta máquina)."""
        self.prefs_ruta = ruta
        try:
            with open(ruta, encoding="utf-8") as fh:
                d = json.load(fh)
        except (OSError, ValueError):
            return
        if isinstance(d, dict):
            self.riel_nombres = {"nombres": True, "monitos": False}.get(d.get("riel"))
            self.panel_cerrado = d.get("panel") == "cerrado"
            self.guia_vista = d.get("guia") == "vista"

    def _guardar_prefs(self):
        if not self.prefs_ruta:
            return
        try:
            os.makedirs(os.path.dirname(self.prefs_ruta), exist_ok=True)
            tmp = self.prefs_ruta + ".tmp"
            d = {} if self.riel_nombres is None else {"riel": "nombres" if self.riel_nombres else "monitos"}
            if self.panel_cerrado:
                d["panel"] = "cerrado"
            if self.guia_vista:
                d["guia"] = "vista"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(d, fh)
            os.replace(tmp, self.prefs_ruta)
        except OSError:
            pass

    # ── sus skills (Skills ▾ y «/»): las mismas rutas que la página ──
    def _abrir_skills(self, slash=False):
        self._cerrar_menus()
        self.barra = {"kind": "skills", "rid": None, "slash": slash}
        if slash:
            self.texto = "/"
        hit = self.skills_todas
        if hit is None or self.reloj() - hit[0] >= SKILLS_S:
            self.skills_cargando = True
            self.en_fondo(self.leer_skills)

    def leer_skills(self, callado=False):
        """Las skills de todos (/api/skills, lo que pinta la página); el menú muestra las del elegido. `callado`: las
        pide el panel (sin aviso si falla). → True si se leyeron."""
        try:
            lista = self.srv.get("/api/skills").get("skills") or []
        except ErrorServidor as e:
            with self.lock:
                self.skills_cargando = False
                self.falla_t["skills"] = self.reloj()
            if not callado:
                self._avisar("No pude ver sus skills: " + e.texto)
            return False
        with self.lock:
            self.skills_todas = (self.reloj(), [x for x in lista if isinstance(x, dict) and x.get("nombre")])
            self.skills_cargando = False
        return True

    def _skills_vista(self, aid):
        lista = [x for x in (self.skills_todas or (0, []))[1] if x.get("agente") == aid]
        if self._slash() and self.texto.startswith("/"):
            f = P._sin_acentos(self.texto[1:].strip())
            if f:
                lista = [x for x in lista if f in P._sin_acentos(" ".join(
                    (x["nombre"], nombre_skill(x["nombre"]), str(x.get("descripcion") or ""))))]
        return lista[:60]

    def _arrancar_skill(self, a, nombre):
        """La arranca en SU conversación (POST /api/v2/skill, lo mismo que «Usar» en la página). skills-cierre: todos
        los caminos del hub (Skills, «/» y «Usar» del panel) pasan por aquí con la MISMA regla de la que corre (la del
        servidor): si corre otra, no arranca y se dice cómo detenerla. → True si la pidió."""
        aid, bonito = a["id"], nombre_skill(nombre)
        corre = vigente_de(self.fotos.get(aid), self.ahora())
        if corre:
            self._avisar("Ya corre «%s»: espera a que termine o detenla (Detener)." % nombre_skill(corre.get("skill")))
            return False
        self._avisar("Arrancando «%s»…" % bonito)

        def hacer():
            try:
                self._post("/api/v2/skill", {"agente": aid, "skill": nombre})
            except ErrorServidor as e:
                # Fix 5: sin respuesta a tiempo, su motor sigue abriendo: la skill arranca sola (no se pide otra vez)
                self._avisar("Abriendo su motor para «%s»…" % bonito if e.tiempo else
                             "No arrancó «%s»: %s" % (bonito, e.texto))
                return
            self._avisar("«%s» arrancó en su conversación." % bonito)
        self.en_fondo(hacer)
        return True

    def _accion_pendiente(self, a, eid, que):
        """«Seguir» / «Cerrar» de la que quedó pendiente (POST /api/v2/skill/accion, lo mismo que la página). Cerrar la
        quita de la vista al momento."""
        aid = a["id"]
        if que == "cerrar":
            with self.lock:
                self.cerradas_skill.add(eid)
        else:
            self._avisar("Sigue con lo que quedó pendiente…")

        def hacer():
            try:
                self._post("/api/v2/skill/accion", {"agente": aid, "id": eid, "accion": que})
            except ErrorServidor as err:
                if que == "cerrar":
                    with self.lock:
                        self.cerradas_skill.discard(eid)
                self._avisar("Abriendo su motor…" if err.tiempo else err.texto)
        self.en_fondo(hacer)

    def _detener_skill(self, a, e):
        """«Detener» de la skill que corre (skills-cierre): la deja pausada en el servidor (POST /api/v2/skill/accion,
        lo mismo que la página) y, si su motor trabaja en ella, le pide parar. Con una página de antes, Parar."""
        aid, bonito = a["id"], nombre_skill(e.get("skill"))
        self._avisar("Deteniendo «%s»…" % bonito)

        def hacer():
            try:
                self._post("/api/v2/skill/accion", {"agente": aid, "id": e.get("id"), "accion": "detener"})
            except ErrorServidor as err:
                if not err.sin_ruta:
                    self._avisar(err.texto)
                    return
                try:
                    self.srv.post("/api/v2/parar", {"agente": aid})
                except ErrorServidor as err2:
                    self._avisar(err2.texto)
                    return
            self._avisar("Detuve «%s»." % bonito)
        self.en_fondo(hacer)

    def _abrir_pagina(self, aviso=None):
        """La página local en el navegador (con su llave): ahí están todas sus skills. `aviso`: lo que se dice si se
        abrió (por omisión, «La abrí en tu navegador.»)."""
        puerto, llave = getattr(self.srv, "puerto", None), getattr(self.srv, "llave", None)
        if getattr(self.srv, "sin_pagina", False):     # AG2-a: no hay página que abrir (la escucha reintenta sola)
            self._avisar(_tp("puertas.hub.sin_pagina_abrir", SIN_PAGINA_ABRIR))
            return

        def hacer():
            ok = False
            if puerto and llave:
                try:
                    import webbrowser
                    ok = bool(webbrowser.open("http://127.0.0.1:%d/?k=%s" % (int(puerto), llave)))
                except Exception:
                    ok = False
            self._avisar((aviso or "La abrí en tu navegador.") if ok else "No pude abrir el navegador.")
        self.en_fondo(hacer)

    def abrir_al_empezar(self, que):
        """Dónde abre el hub (`workspace agentes` → "agentes", `tono` → "agentes:tono", `conexiones` →
        "ajustes:conexiones", `comandos` → "ayuda:comandos", `calendario`, y la tarjeta «Agregar agente»:
        "agregar:crear", "agregar:cargar" o "agregar:primera"). → None, o lo que pida (la tarjeta, para prestar la
        terminal)."""
        que = str(que or "").strip()
        if not que:
            return None
        kind, _s, sub = que.partition(":")
        if kind == "agregar":
            return self._abrir_agregar(sub or "crear")
        if sub:
            return self._activar_inicio("ini:sub:%s:%s" % (kind, sub))
        return self._activar_inicio("ini:sec:" + kind)

    def _abrir_agregar(self, modo="crear"):
        """«+ Agregar» (las seis puertas del hub, el primer arranque y `workspace onboarding`): la tarjeta «Agregar
        agente» en Inicio (AG4-a), que es de su propia rama: Directo.abrir_agregar(modo="crear"|"cargar"|"primera").
        Mientras esa rama no esté en esta copia: la ventana «Nuevo agente» de la página nueva (AG8-b), y sin página una
        línea. Nunca el formulario de antes (add_agent_tui). → None, o lo que pida la tarjeta para prestarle la
        terminal a otro programa."""
        self.barra = None
        tarjeta = getattr(type(self), "abrir_agregar", None)
        if callable(tarjeta):
            return self.abrir_agregar(modo=modo)
        if modo == "primera":                         # sin la tarjeta: Inicio vacío ya trae su «+ Agregar»
            return None
        if getattr(self.srv, "sin_pagina", False):
            self._avisar(_tp("puertas.hub.agregar_sin_pagina", AGREGAR_SIN_PAGINA))
            return None
        self._abrir_pagina(aviso=_tp("puertas.hub.agregar_en_pagina", AGREGAR_EN_PAGINA))
        return None

    def releer_agentes(self):
        """Los agentes otra vez (al volver de «Agregar agente»): el elegido sigue elegido si sigue ahí."""
        try:
            nuevos = agentes_de(self.srv)
        except Exception:
            return False
        with self.lock:
            aid = self.id_elegido()
            ids = [b["id"] for b in nuevos]
            self.d["agentes"] = nuevos
            self.sel = ids.index(aid) if aid in ids else 0
        return True

    # ── las secciones (Sesiones, Skills, Motores y conexiones, Ajustes, Agentes, Ayuda) ──
    def _abrir_seccion(self, kind):
        """Abre la sección `kind` en lugar de la conversación (el riel se queda) y pide lo que necesita."""
        self._cerrar_menus()
        self.seccion = {"kind": kind, "sel": None, "filtro": "todas", "agente": None, "abierto": False, "op": None}
        if kind == "sesiones":
            self._pedir_ses_todas()
        elif kind == "ayuda":
            self.seccion["sel"] = "ay:teclas" if piel() != "bloque" else (
                "acc:mouse" if self.raton_posible else "acc:riel")
        elif kind == "agentes":
            self.seccion["sel"] = "ag:" + self.id_elegido()
        self._pedir_seccion(kind)

    def revision_al_abrir(self):
        """Conexiones en verde (F4): al abrir el hub se le pide al servidor el chequeo rápido (el suyo hace el `stat()`
        de cada motor y, si alguno cambió, lo revisa en el fondo). Sin IA; no frena el arranque."""
        def pedir():
            d = self.srv.get("/api/v2/chequeo")
            self._anunciar_cambios(d)
            return d
        self._pedir("chequeo", pedir)

    def _anunciar_cambios(self, d):
        """Una sola vez por hub: «Copilot se actualizó a 1.0.114 · revisado al abrir: contesta…» (o lo que se rompió)
        y el aviso de un arreglo que Workspace hizo solo."""
        vistos = self.__dict__.setdefault("_cx_vistos", set())
        for m in (d or {}).get("motores") or ():
            c = m.get("cambio") or {}
            clave = ("cambio", m.get("motor"), c.get("ahora"))
            if c.get("texto") and clave not in vistos:
                vistos.add(clave)
                self._avisar(c["texto"])
        for a in (d or {}).get("avisos") or ():
            clave = ("aviso", a.get("deshacer") or a.get("fecha"))
            if a.get("texto") and clave not in vistos:
                vistos.add(clave)
                self._avisar(a["texto"] + ("  ·  Deshacer: Ajustes › Conexiones (d)" if a.get("deshacer") else ""))

    def _cerrar_seccion(self):
        """Cierra la sección. Conexiones abierta desde Ajustes (H3-b) vuelve a su grupo de Ajustes."""
        desde = (self.seccion or {}).get("desde")
        self.seccion = None
        self.confirma = None
        self.foco = ""
        if desde == "ajustes":
            self._abrir_seccion("ajustes")
            self.seccion["sel"] = "aj:cx"

    def _abrir_conexiones(self):
        """Ajustes › Conexiones › «Ver la rejilla ›»: la sección Conexiones completa (Esc vuelve a Ajustes)."""
        self._abrir_seccion("conexiones")
        self.seccion["desde"] = "ajustes"

    # ── las secciones de H-1 que faltaban: Calendario, el tono, los usuarios, el uso ──
    def _pedir_r2(self, kind):
        aid = self.id_elegido()
        if kind == "calendario":
            self._pedir("calendario", lambda: self.srv.get("/api/calendario"), tope=10.0)
            self._pedir("calendario_g", _gcal_eventos)
        elif kind == "ajustes":
            import hub_secciones_r2 as R2
            self._pedir("preferencias", R2.preferencias_locales)
            self._pedir("usuarios", lambda: self.srv.get("/api/sistema/usuarios"))
            if aid:
                self._pedir("uso:" + aid, lambda: self.srv.get("/api/front/uso", agente=aid))
        if kind in ("motores", "ajustes", "conexiones"):   # Conexiones en verde: el chequeo rápido (lo que lee la página)
            revisa = bool((self._dato("chequeo") or {}).get("revisando"))
            self._pedir("chequeo", lambda: self.srv.get("/api/v2/chequeo"), tope=2.0 if revisa else 30.0)
            self._pedir("conexiones", lambda: self.srv.get("/api/conexiones"))
        if kind == "conexiones" and (self.seccion or {}).get("lab"):   # la vista de laboratorio (modo desarrollador)
            corre = bool((self._dato("conexiones_v") or {}).get("corriendo"))
            self._pedir("conexiones_v", lambda: self.srv.get("/api/v2/conexiones", timeout=60), tope=2.0 if corre
                        else 30.0)
            self._pedir("motores", lambda: self.srv.get("/api/sistema/motores"))
        elif kind == "agentes":
            self._pedir("usuarios", lambda: self.srv.get("/api/sistema/usuarios"))
            if (self.seccion or {}).get("vista") == "tablero":
                self._pedir("motores", lambda: self.srv.get("/api/sistema/motores"))
            sel = str((self.seccion or {}).get("sel") or "")
            if sel.startswith("ag:"):
                b = sel[3:]
                self._pedir("tono:" + b, lambda: self.srv.get("/api/front/tono", agente=b))
            if (self.seccion or {}).get("tab") == "maquina":   # Esta máquina: se lee aquí (la página no la trae)
                import hub_agentes_maquina as HM
                self._pedir(HM.CLAVE, HM.leer)

    def _recargar(self, clave, fn):
        self.datos.pop(clave, None)
        self.falla_t.pop(clave, None)
        self._pedir(clave, fn)

    def _tono(self, resto):
        """Un dial del tono (Agentes › Tono): POST /api/front/tono, como la página."""
        k, _s, v = resto.rpartition(":")
        sel = str((self.seccion or {}).get("sel") or "")
        if not sel.startswith("ag:") or not v.isdigit():
            return None
        aid = sel[3:]

        def hacer():
            try:
                self._post("/api/front/tono", {"agente": aid, "niveles": {k: int(v)}})
            except ErrorServidor as e:
                self._avisar("No cambió el tono: " + e.texto)
                return
            with self.lock:
                d = (self.datos.get("tono:" + aid) or (0, {}))[1]
                if isinstance(d, dict):
                    d.setdefault("niveles", {})[k] = int(v)
            self._avisar("Listo: su tono cambió.")
        self.en_fondo(hacer)
        return None

    def _accion_usuario(self, accion, fila):
        sec = self.seccion
        if accion == "cancelar":
            sec.pop("usuario_edicion", None)
            sec.update(editando=None, error="")
            return
        if not fila or not fila.get("agente"):
            return
        filas = fila.get("usuarios") or []
        indice = min(sec.get("usuario_i", 0), max(0, len(filas) - 1))
        if accion in ("anterior", "siguiente") and filas:
            sec["usuario_i"] = (indice + (-1 if accion == "anterior" else 1)) % len(filas)
            return
        u = filas[indice] if filas else {}
        if accion != "guardar":
            titulos = {"crear": "Crear usuario", "renombrar": "Renombrar usuario",
                       "unir": "Unir a otro usuario", "soy": "¿Usar este perfil en esta máquina?"}
            if accion not in titulos or (accion != "crear" and not u):
                return
            sec["usuario_edicion"] = {"accion": accion, "usuario": u, "titulo": titulos[accion],
                                      "nota": u.get("nombre", ""), "agente": fila["agente"]}
            sec.update(editando="usuario" if accion != "soy" else None, buf="", error="")
            return
        edit = sec.get("usuario_edicion")
        if not edit or edit["agente"] != fila["agente"]:
            return
        accion, u = edit["accion"], edit["usuario"]
        nombre = sec.get("buf", "").strip()
        if accion != "soy" and not nombre:
            sec["error"] = "Escribe un nombre."
            return
        uid = u.get("nombre")
        campos = {"crear": {"nombre": nombre}, "renombrar": {"usuario": uid, "nuevo": nombre,
                  "revision": u.get("revision")}, "soy": {"usuario": uid},
                  "unir": {"origen": uid, "destino": nombre}}
        if accion == "unir" and sec.get("editando"):
            edit["nota"] = "%s → %s" % (u["nombre"], nombre)
            sec.update(editando=None, error="")
            return
        rutas = {"crear": "/api/sistema/usuario/crear", "renombrar": "/api/sistema/usuario/renombrar",
                 "soy": "/api/sistema/usuario/soy", "unir": "/api/sistema/usuario/unir"}
        cuerpo = {"agente": fila["agente"], **{k: v for k, v in campos[accion].items() if v is not None}}
        self._accion_usuario("cancelar", fila)

        def hacer():
            try:
                self._post(rutas[accion], cuerpo)
            except ErrorServidor as e:
                self._avisar(e.texto)
                return
            self._avisar("Usuarios actualizados.")
            self._recargar("usuarios", lambda: self.srv.get("/api/sistema/usuarios"))
        self.en_fondo(hacer)

    def _accion_calendario(self, acc):
        """Gestiona la agenda local con el mismo almacén que el calendario de siempre."""
        sec = self.seccion
        import hub_secciones_r2 as R2
        if acc == "agregar":
            sec["editando"], sec["buf"], sec["error"] = "nuevo", "", ""
            return None
        if acc == "cancelar-borrado":
            sec.pop("borrar", None)
            return None
        if acc == "cancelar-edicion":
            sec.update(editando=None, error="")
            return None
        if acc == "guardar":
            dia = sec.get("fecha_evento") if sec.get("editando") == "editar" else R2.dia_elegido(sec).isoformat()
            texto = sec.get("buf")
            if sec.get("editando") == "editar" and texto == sec.get("texto_original"):
                sec["editando"] = None
                return None
            ev, err = R2.leer_evento(texto, dia=dia)
            if not ev:
                sec["error"] = err
                return None
            import personal
            try:
                if sec.get("editando") == "editar":
                    ok = personal.update_event(sec["evento"], date_s=ev[0], title=ev[2], time_s=ev[1])
                else:
                    ok = personal.add_event(ev[0], ev[2], ev[1])
            except (OSError, ValueError):
                ok = False
            if not ok:
                sec["error"] = "No pude guardar el evento."
                return None
            sec["editando"], sec["error"] = None, ""
            self._avisar("Quedó en tu agenda: «%s»." % ev[2])
            self._recargar("calendario", lambda: self.srv.get("/api/calendario"))
            return None
        accion, _, eid = acc.partition(":")
        if accion not in ("editar", "borrar", "confirmar-borrado", "hecho"):
            return None
        e = next((x for x in R2.calendario_eventos(self.instantanea()) if str(x.get("id")) == eid), None)
        if not e or e.get("fuente") == "google":
            return None
        if accion == "editar":
            texto = " ".join(filter(None, (e.get("date"), e.get("time"), e.get("title"))))
            sec.update(editando="editar", evento=e["id"], fecha_evento=e.get("date"),
                       error="", buf=texto, texto_original=texto)
            return None
        if accion == "borrar":
            sec["borrar"] = e
            return None
        import personal
        if accion == "confirmar-borrado":
            if (sec.get("borrar") or {}).get("id") != e["id"]:
                return None
            sec.pop("borrar")
            ok = personal.remove_event(e["id"])
            self._avisar("Evento archivado." if ok else "No pude borrar el evento.")
        else:
            personal.toggle_done(e["id"])
            self._avisar("Marcada." if not e.get("done") else "Otra vez pendiente.")
        self._recargar("calendario", lambda: self.srv.get("/api/calendario"))
        return None

    def _seccion_de(self, aid):
        """Un monito tocado en una sección: la sección cambia a ese agente (en Sesiones, sus sesiones; otra vez el
        mismo, todas)."""
        sec = self.seccion
        if sec is None:
            return
        if sec["kind"] == "sesiones":
            sec["agente"] = None if sec.get("agente") == aid else aid
            sec["sel"] = "ses:%s:conv" % aid if sec["agente"] else sec.get("sel")
        elif sec["kind"] == "agentes":
            sec["sel"], sec["editando"] = "ag:" + aid, None
        elif sec["kind"] in ("skills", "ajustes"):
            sec["sel"], sec["op"] = None, None

    def _pedir_ses_todas(self, forzar=False):
        if self.ses_todas_cargando:
            return
        if not forzar and self.ses_todas_t is not None and self.reloj() - self.ses_todas_t < SES_TODAS_S:
            return
        self.ses_todas_cargando = True
        self.en_fondo(self.leer_ses_todas)

    def leer_ses_todas(self):
        """Las sesiones de cada agente (/api/v2/sesiones, una por agente: la misma ruta de ^S). → cuántas se
        leyeron."""
        with self.lock:
            ids = [b["id"] for b in self.d["agentes"]]
        todas, malas = {}, 0
        for aid in ids:
            try:
                todas[aid] = self.srv.get("/api/v2/sesiones", agente=aid).get("sesiones") or []
            except ErrorServidor:
                malas += 1
        with self.lock:
            self.ses_todas_cargando = False
            self.ses_todas_t = self.reloj()
            if todas or not malas:
                self.ses_todas, self.ses_todas_error = todas, ""
            else:
                self.ses_todas_error = "No pude ver las sesiones de los agentes."
        return len(todas)

    def _filas_seccion(self):
        """(rids que se eligen, el elegido) de la sección abierta: lo mismo que se dibuja."""
        if self.seccion is None:
            return [], ""
        import hub_secciones
        return hub_secciones.filas(self.seccion["kind"], self.instantanea())

    def _mover_seccion(self, d):
        rids, cur = self._filas_seccion()
        if rids:
            i = rids.index(cur) if cur in rids else -1
            self.seccion["sel"] = rids[max(0, min(len(rids) - 1, i + d))] if i >= 0 else rids[0]
            self.seccion.update(op=None, usuario_i=0)
            self.seccion.pop("usuario_edicion", None)
            self.confirma = None

    def _fila_ajuste(self, rid=None):
        import hub_secciones
        if piel() == "bloque":
            filas = hub_secciones.ajustes_filas(self.instantanea())
        else:
            import hub_secciones_r2
            filas = [f for f in hub_secciones_r2.ajustes_filas(self.instantanea()) if f.get("rid")]
        rid = rid or hub_secciones.elegida(self.seccion or {}, filas)
        return next((f for f in filas if f["rid"] == rid), None)

    def _aplicar_ajuste(self, fila, v):
        """Ajustes: elegir la opción `v` de la fila (`perm`, `modelo`, `idioma`, `riel` o `mouse`)."""
        if not fila or fila.get("dim") or v not in dict(fila.get("opciones") or ()):
            return
        self.seccion["op"] = None
        if v == fila.get("actual"):
            return
        a = self.agente()
        k = fila["rid"][3:]
        if fila.get("preferencia"):
            self._guardar_preferencia(fila["preferencia"], fila["valores"][v])
        elif k == "perm" and a:
            self._permiso_nivel(a["id"], v)
        elif k == "modelo" and a:
            self._modelo(a["id"], v, dict(fila["opciones"])[v])
        elif k == "esfuerzo" and a:
            self._modelo(a["id"], v, dict(fila["opciones"])[v], ajuste=k)
        elif k == "idioma":
            self._idioma(v)
        elif k == "riel":
            self._alternar_riel(v == "nombres")
        elif k == "mouse":
            self._alternar_raton()

    def _tecla_seccion(self, k):
        sec = self.seccion
        kind = sec["kind"]
        if kind == "encamino":                        # una sección que el hub todavía no tiene
            if k == "enter":
                self._abrir_pagina()
            elif k == "esc":
                self._cerrar_seccion()
            return None
        if sec.get("editando"):                       # el campo del nombre (Agentes)
            if k == "esc":
                sec["editando"] = None
                sec.pop("usuario_edicion", None)
            elif k == "enter":
                return self._accion_seccion("guardar")
            elif k == "borrar":
                sec["buf"] = sec.get("buf", "")[:-1]
            elif k == "ctrl-u":
                sec["buf"] = ""
            elif isinstance(k, str) and len(k) == 1 and k.isprintable() and \
                    len(sec.get("buf", "")) < _tope_campo(sec):
                sec["buf"] = sec.get("buf", "") + k
            return None
        if kind == "calendario" and k in ("izquierda", "derecha", "arriba", "abajo", "repag", "avpag", "enter"):
            import hub_secciones_r2 as R2                # ←→ un día, ↑↓ una semana, AvPág/RePág un mes
            if k == "enter":                          # Enter: la agenda de ese día
                self._enfocar_area("detalle")
                return None
            if k in ("repag", "avpag"):
                R2.mover_dia(sec, meses=1 if k == "avpag" else -1)
            else:
                R2.mover_dia(sec, {"izquierda": -1, "derecha": 1, "arriba": -7, "abajo": 7}[k])
            return None
        if kind == "conexiones" and not sec.get("lab") and \
                k in ("izquierda", "derecha", "arriba", "abajo", "enter", "r", "R", "p", "d", "m", "L"):
            import hub_conexiones as CX                  # Conexiones en verde: ←→ el motor, ↑↓ la fila, Enter su acción
            if k in ("izquierda", "derecha", "arriba", "abajo"):
                if str(self.foco or "").startswith("sr:cv:"):   # la fila enfocada es la elegida
                    sec["sel"] = self.foco[3:]
                CX.mover_v(self.instantanea(), sec, dx={"izquierda": -1, "derecha": 1}.get(k, 0),
                           dy={"arriba": -1, "abajo": 1}.get(k, 0))
                self.foco = "sr:" + str(sec.get("sel") or "")
                return None
            if str(self.foco or "").startswith("sr:cv:"):
                sec["sel"] = self.foco[3:]
            if k == "L" and not CX.es_dev():
                return None
            return self._accion_seccion({"enter": "fila", "r": "fila", "R": "revisar", "p": "reportar",
                                         "d": "deshacer", "m": "motores", "L": "lab"}[k])
        if kind == "conexiones" and sec.get("lab") and k == "esc":     # del laboratorio, de vuelta a Conexiones
            sec["lab"] = False
            sec["sel"] = None
            return None
        if kind == "conexiones" and (k in ("izquierda", "derecha", "arriba", "abajo", "enter", "v", "V", "r")):
            import hub_conexiones as CX
            if k in ("izquierda", "derecha", "arriba", "abajo"):
                if str(self.foco or "").startswith("sr:cx:"):   # la celda enfocada es la elegida
                    sec["sel"] = self.foco[3:]
                CX.mover(self.instantanea(), sec, dx={"izquierda": -1, "derecha": 1}.get(k, 0),
                         dy={"arriba": -1, "abajo": 1}.get(k, 0))
                self.foco = "sr:" + str(sec.get("sel") or "")
                return None
            return self._accion_seccion({"enter": "evidencia", "v": "verificar", "V": "verificar_todos",
                                         "r": "reparar"}[k])
        if kind == "agentes" and sec.get("vista") == "tablero" and \
                k in ("izquierda", "derecha", "arriba", "abajo", "enter"):
            return self._tecla_tablero(k)
        if k == "enter" and kind == "ajustes" and sec.get("sel") == "aj:cara":
            return self._accion_seccion("ir:agentes")
        if k in ("izquierda", "derecha") and kind == "ajustes":
            f = self._fila_ajuste()
            ops = [v for v, _t in (f or {}).get("opciones") or []]
            if ops and not f.get("dim"):
                cur = sec.get("op") if sec.get("op") in ops else f.get("actual")
                i = ops.index(cur) if cur in ops else -1
                sec["op"] = ops[(i + (1 if k == "derecha" else -1)) % len(ops)]
            return None
        if kind == "conexiones" and isinstance(k, str) and len(k) == 1 and k.isprintable() and k != "q":
            return None                               # (Conexiones no filtra: v, V y r son sus teclas)
        if piel() != "bloque":                       # escribir en una lista la filtra (type-to-search)
            if isinstance(k, str) and len(k) == 1 and k.isprintable() and not (k == "q" and not sec.get("busca")) \
                    and (k.isalnum() or sec.get("busca") or k in "áéíóúñ"):
                sec["busca"] = (sec.get("busca") or "") + k
                sec["sel"] = None
                return None
            if k == "borrar" and sec.get("busca"):
                sec["busca"] = sec["busca"][:-1]
                return None
            if k == "esc" and sec.get("busca"):
                sec["busca"] = ""
                return None
            if k == "q" and not sec.get("busca"):
                return "salir"
        if k == "esc":
            if sec.get("abierto") and not self.sec_lado:
                sec["abierto"] = False
            else:
                self._cerrar_seccion()
        elif k in ("arriba", "abajo"):
            self._mover_seccion(1 if k == "abajo" else -1)
        elif k in ("repag", "avpag"):
            self._mover_seccion(6 if k == "avpag" else -6)
        elif k in ("izquierda", "derecha") and kind == "sesiones":
            import hub_secciones
            ks = [f for f, _l in hub_secciones.FILTROS]
            i = ks.index(sec.get("filtro") or "todas")
            sec["filtro"] = ks[(i + (1 if k == "derecha" else -1)) % len(ks)]
        elif k in ("tab", "shift-tab"):
            self._elegir(self.sel + (1 if k == "tab" else -1))
            if sec.get("agente"):
                sec["agente"] = self.id_elegido()
            elif kind == "agentes":
                sec["sel"] = "ag:" + self.id_elegido()
            elif kind in ("skills", "ajustes"):
                sec["sel"], sec["op"] = None, None
        elif k == "ctrl-e":
            self._abrir_menu()
        elif k == "ctrl-s":
            self._abrir_sesiones()
        elif k == "ctrl-o":
            return self._plan_abrir()
        elif k == "enter":
            if not self.sec_lado and not sec.get("abierto"):
                sec["abierto"] = True
                return None
            return self._accion_seccion("enter")
        return None

    def _accion_seccion(self, acc):
        """Lo que hace un botón del detalle de la sección (o Enter: su acción principal)."""
        sec = self.seccion
        if sec is None:
            return None
        kind = sec["kind"]
        if kind == "agentes" and (acc.startswith("maq:") or (acc in ("guardar", "cancelar") and
                                                             sec.get("editando") == "ruta")):
            import hub_agentes_maquina as HM          # Agentes › Esta máquina (en el hub, su cerebro, quitarlo)
            return HM.accion(self, acc)
        if acc.startswith("ir:"):                     # «Abrir Agentes ›» (Ajustes › Apariencia)
            aid = self.id_elegido()
            self._abrir_seccion(acc[3:])
            self.seccion["sel"] = "ag:" + aid
            return None
        if kind == "calendario":
            return self._accion_calendario(acc)
        if kind == "conexiones":
            return self._accion_conexiones(acc)
        if kind == "ayuda" and acc == "pagina":
            self._abrir_pagina()
            return None
        if kind == "ayuda" and acc == "enter" and str(sec.get("sel") or "").startswith("ay:"):
            if str(sec.get("sel")).startswith("ay:doc:"):
                self._abrir_pagina()
            return None
        if kind == "ayuda":
            acc = (sec.get("sel") or "acc:mouse")[4:] if acc == "enter" else acc
            if acc == "mouse":
                self._alternar_raton()
            elif acc == "riel":
                self._alternar_riel()
            elif acc == "agregar":
                return self._abrir_agregar()
            return None
        if kind == "skills":
            _rids, cur = self._filas_seccion()
            a = self.agente()
            if acc == "pagina":
                self._abrir_pagina()
            elif acc == "detener" and a:
                e = vigente_de(self.fotos.get(a["id"]), self.ahora())
                if e:
                    self._detener_skill(a, e)
            elif acc in ("enter", "usar") and cur and a and "/api/v2/skill" not in self.sin_ruta:
                nombre = cur.split(":", 1)[1]
                if self._arrancar_skill(a, nombre):
                    self._cerrar_seccion()            # a su conversación: ahí se ve correr
            return None
        if kind == "motores":
            _rids, cur = self._filas_seccion()
            if acc == "conexiones":                   # «Ajustes › Conexiones ›» (H3-b)
                self._abrir_seccion("ajustes")
                self.seccion["sel"] = "aj:cx"
                return None
            if acc == "verificar_todos":
                self._avisar("Verificando los motores…")
                self._pedir_motores(forzar=True, verificar=True)
                return None
            if not cur or not cur.startswith("mot:"):
                return None
            mid = cur[4:]
            m = next((x for x in (self._dato("motores") or {}).get("motores") or [] if x.get("id") == mid), {})
            nombre = m.get("nombre") or nombre_motor(mid)
            a = self.agente()
            if acc == "modelo" and m.get("instalado"):
                foto = (self.fotos.get(a["id"]) or {}) if a else {}
                activo = foto.get("motor") or (a or {}).get("mid")
                tabla = (foto.get("ajustes") or {}).get("tabla") or []
                preferencia = next((t["k"] for t in tabla
                                    if t.get("k") in ("modelo", "esfuerzo") and t.get("opciones")), None)
                if mid == activo and preferencia and "/api/v2/ajuste" not in self.sin_ruta:
                    self._abrir_seccion("ajustes")
                    self.seccion["sel"] = "aj:" + preferencia
                    return None
                acc = "cuenta"
            acciones = {"cuenta": "account", "login": "login", "reparar": "repair", "instalar": "install"}
            if acc in acciones and m:                  # I09: la acción sin la pantalla de Motores de antes
                argv = [P.PY, os.path.join(AQUI, "motor_accion.py"), mid, acciones[acc]]
                sesion = m.get("sesion")
                if acc == "cuenta" and isinstance(sesion, bool):
                    argv.append("activa" if sesion else "sin-sesion")
                return {"programa": "motores", "argv": argv}
            if acc == "defecto" and m.get("instalado"):
                self._guardar_preferencia("modelos.default_engine", mid)
                return None
            if acc == "ofrecer" and m.get("instalado"):
                def ofrecer():
                    try:
                        self._post("/api/sistema/motor/hub", {"motor": mid, "encendido": not m.get("en_hub")})
                    except ErrorServidor as e:
                        self._avisar(e.texto)
                        return
                    self._pedir_motores(forzar=True)
                self.en_fondo(ofrecer)
                return None
            if acc in ("enter", "verificar") and m.get("instalado"):
                self._verificar_motor(mid, nombre)
            elif acc == "usar" and a and m.get("listo"):
                if mid != ((self.fotos.get(a["id"]) or {}).get("motor") or a.get("mid")):
                    self._cambiar_motor(a, {"id": mid, "nombre": nombre})
            elif acc == "abrir" and a and m.get("listo"):
                return P.plan({"tipo": "abrir", "agente": self.sel, "texto": ""}, self.d["agentes"], motor=mid)
            return None
        if kind == "ajustes":
            f = self._fila_ajuste()
            accion = (f or {}).get("accion") if acc == "enter" else acc
            if acc in ("op-ant", "op-sig") and f and f.get("opciones"):
                ops = [v for v, _ in f["opciones"]]
                actual = sec.get("op") or f.get("actual")
                i = ops.index(actual) if actual in ops else 0
                sec["op"] = ops[(i + (1 if acc == "op-sig" else -1)) % len(ops)]
                return None
            if accion == "rejilla":                   # Conexiones › «Ver la rejilla ›»
                self._abrir_conexiones()
                return None
            if accion == "verificar_cx":                # Conexiones en verde: el chequeo rápido, sin IA
                return self._revisar_cx()
            if accion == "actualizar":                # I10: la pantalla nueva (hub_actualizar), no la de antes
                return {"programa": "actualizar", "argv": [P.PY, os.path.join(AQUI, "hub_actualizar.py")]}
            if str(accion).startswith("usuario:") or (acc == "guardar" and sec.get("usuario_edicion")):
                return self._accion_usuario("guardar" if acc == "guardar" else accion[8:], f)
            if acc == "enter" and f:
                ops = [v for v, _t in f.get("opciones") or []]
                v = self.seccion.get("op")
                if v not in ops and ops:              # sin elegir con ←→: la que sigue a la de ahora
                    v = ops[(ops.index(f["actual"]) + 1) % len(ops)] if f.get("actual") in ops else ops[0]
                self._aplicar_ajuste(f, v)
            return None
        if kind == "agentes":
            _rids, cur = self._filas_seccion()
            aid = cur[3:] if cur else ""
            i = next((n for n, b in enumerate(self.d["agentes"]) if b["id"] == aid), None)
            if acc == "agregar":
                return self._abrir_agregar()
            if i is None:
                return None
            if acc == "usuarios":
                self._abrir_seccion("ajustes")
                self.seccion["sel"] = "aj:us:" + aid
                return None
            if acc == "tablero":                        # lo del cruce: conversar, usarlo, iniciar sesión…
                import hub_secciones_r2 as R2
                s = self.instantanea()
                b, mid = R2.tablero_cursor(s, self.seccion)
                if not b:
                    return None
                _lab, k = R2.tablero_accion(s, b, mid)
                if k == "conversar":
                    self._ir_conversacion(i)
                elif k == "usar":
                    if self._trabaja(aid):
                        self._avisar("%s está trabajando: cambia su motor cuando termine." % b["n"])
                        return None
                    self.fotos.setdefault(aid, {})["motor"] = mid
                    self.anim.setdefault(aid, {})["motor"] = self.reloj()
                    self._cambiar_motor(self.d["agentes"][i], {"id": mid, "nombre": nombre_motor(mid)})
                elif k == "login":
                    return self._plan_login(mid)
                else:
                    self._abrir_seccion("motores")
                    self.seccion["sel"] = "mot:" + str(mid)
                return None
            if acc in ("enter", "conversar"):
                self._elegir(i)
                self._cerrar_seccion()
            elif acc == "nombre" and "/api/front/nombre" not in self.sin_ruta:
                self.seccion["editando"], self.seccion["buf"] = "nombre", self.d["agentes"][i]["n"]
            elif acc == "guardar":
                self.seccion["editando"] = None
                self._renombrar(aid, self.seccion.get("buf") or "")
            elif acc == "cancelar":
                self.seccion["editando"] = None
            return None
        if kind == "sesiones":
            rids, cur = self._filas_seccion()
            if not cur:
                return None
            _ses, aid, wid = cur.split(":", 2)
            i = next((n for n, b in enumerate(self.d["agentes"]) if b["id"] == aid), None)
            if i is None:
                return None
            if acc == "enter":
                acc = "ir" if wid == "conv" else "retomar"
            if acc == "ir":
                self._elegir(i)
                self._cerrar_seccion()
            elif acc == "abrir" or acc == "nueva":
                return self._plan_abrir(i)
            elif acc == "retomar" and wid != "conv":
                r = next((x for x in self.ses_todas.get(aid) or [] if str(x.get("wid")) == wid), None)
                if r is not None:
                    p = self._retomar(r, i)
                    if p is not None:
                        self._cerrar_seccion()
                    return p
        return None

    def _post(self, ruta, cuerpo):
        """Una escritura, SIEMPRE a la página prendida. Si no conoce la ruta (otra versión), se anota: lo que la usa
        se ve apagado, con su razón en corto."""
        try:
            return self.srv.post(ruta, cuerpo)
        except ErrorServidor as e:
            if e.sin_ruta:
                with self.lock:
                    self.sin_ruta.add(ruta)
                    self.pide_renovar = True
                    self.despierta.set()
                e.texto = ACTUALIZANDO
            raise

    # ── los datos de las secciones de la fase B (las mismas rutas que la página) ──
    def _pedir(self, clave, fn, tope=SECCION_S):
        """Pide en el fondo lo de `clave` si no está o ya es viejo (self.datos[clave] = (cuándo, datos))."""
        hit = self.datos.get(clave)
        if clave in self.cargando or (hit and self.reloj() - hit[0] < tope):
            return
        self.cargando.add(clave)

        def hacer():
            try:
                d = fn()
            except ErrorServidor as e:
                with self.lock:
                    self.cargando.discard(clave)
                    self.errores[clave] = e.texto
                    self.falla_t[clave] = self.reloj()
                    if e.sin_ruta:                    # la página es de antes: que Escucha la renueve si puede
                        self.pide_renovar = True
                        self.despierta.set()
                return
            with self.lock:
                self.cargando.discard(clave)
                self.errores.pop(clave, None)
                self.datos[clave] = (self.reloj(), d)
        self.en_fondo(hacer)

    def _dato(self, clave, defecto=None):
        hit = self.datos.get(clave)
        return hit[1] if hit else defecto

    def _pedir_motores(self, forzar=False, verificar=False):
        if forzar:
            self.datos.pop("motores", None)
        self._pedir("motores", lambda: self.srv.get("/api/sistema/motores", **({"verificar": "1"} if verificar
                                                                                   else {})))

    def _pedir_seccion(self, kind):
        if piel() != "bloque":
            self._pedir_r2(kind)
        self._pedir_seccion_t2(kind)

    def _pedir_seccion_t2(self, kind):
        if kind == "skills":
            hit = self.skills_todas
            if hit is None or self.reloj() - hit[0] >= SKILLS_S:
                self.skills_cargando = True
                self.en_fondo(self.leer_skills)
        elif kind == "motores":
            import hub_secciones_r2 as R2
            self._pedir("preferencias", R2.preferencias_locales)
            self._pedir_motores()
            self._pedir("conexiones", lambda: self.srv.get("/api/conexiones"))
        elif kind == "ajustes":
            self._pedir("info", lambda: self.srv.get("/api/v2/info"))
            try:
                import i18n
                self.idioma, self.idiomas = i18n.lang(), list(i18n.available())
            except Exception:
                self.idioma, self.idiomas = "", []
        elif kind == "agentes":
            self._pedir("inicio", lambda: self.srv.get("/api/front/inicio"))

    def _verificar_motor(self, mid, nombre):
        """«Verificar ahora»: le vuelve a preguntar al programa (la ruta de la página de siempre) y relee los motores."""
        self._avisar("Verificando %s…" % nombre)

        def hacer():
            try:
                self._post("/api/sistema/motor/verificar", {"motor": mid})
            except ErrorServidor as e:
                self._avisar("No pude verificar %s: %s" % (nombre, e.texto))
                return
            time.sleep(VERIFICAR_S)
            try:
                d = self.srv.get("/api/sistema/motores")
            except ErrorServidor as e:
                self._avisar(e.texto)
                return
            with self.lock:
                self.datos["motores"] = (self.reloj(), d)
            m = next((x for x in d.get("motores") or [] if x.get("id") == mid), {})
            self._avisar("%s: %s." % (nombre, m.get("estado_texto") or m.get("estado") or "verificado"))
        self.en_fondo(hacer)

    def _permiso_nivel(self, aid, nivel):
        """Ajustes → Permisos: «auto» (Automático) o «preguntar» (Preguntarme todo), en su agent.json."""
        nombre = (next((b for b in self.d["agentes"] if b["id"] == aid), None) or {}).get("n", aid)

        def hacer():
            try:
                r = self._post("/api/v2/autonomia", {"agente": aid, "nivel": nivel})
            except ErrorServidor as e:
                self._avisar("No cambió: " + e.texto)
                return
            with self.lock:
                info = dict(self._dato("info") or {})
                info["permisos"] = [dict(p, nivel=nivel) if p.get("agente") == aid else p
                                    for p in info.get("permisos") or []]
                self.datos["info"] = (self.reloj(), info)
            self._avisar(str(r.get("texto") or "%s: %s." % (nombre, NIVELES.get(nivel, nivel))))
        self.en_fondo(hacer)

    def _modelo(self, aid, valor, texto, ajuste="modelo"):
        def hacer():
            try:
                self._post("/api/v2/ajuste", {"agente": aid, "ajuste": ajuste, "valor": valor})
            except ErrorServidor as e:
                self._avisar("No cambió: " + e.texto)
                return
            with self.lock:
                f = self.fotos.get(aid)
                if f is not None:
                    aj = dict(f.get("ajustes") or {})
                    aj["valores"] = dict(aj.get("valores") or {}, **{ajuste: {"actual": {"v": valor, "t": texto}}})
                    f["ajustes"] = aj
            self._avisar("Usa %s desde su siguiente mensaje." % texto)
        self.en_fondo(hacer)

    def _guardar_preferencia(self, clave, valor):
        import settings
        try:
            settings.set(clave, valor)
        except (ValueError, TypeError, OSError) as e:
            self._avisar("No se guardó: " + str(e))
            return
        import hub_secciones_r2 as R2
        self._recargar("preferencias", R2.preferencias_locales)
        self._avisar("Guardado.")

    def _idioma(self, code):
        try:
            import i18n
            i18n.set_lang(code)
            self.idioma = i18n.lang()
        except Exception as e:
            self._avisar("No cambió el idioma: %s" % type(e).__name__)
            return
        self._avisar("Idioma de Workspace: %s (este hub de prueba sigue en español)." % code)

    def _apariencia(self, aid, forma=None, color=None):
        """Su cara o su color (en esta computadora): se ve en seguida; si la página no lo guarda, vuelve."""
        i = next((n for n, b in enumerate(self.d["agentes"]) if b["id"] == aid), None)
        if i is None:
            return
        b = self.d["agentes"][i]
        antes = (b.get("f"), b.get("c"))
        self.d["agentes"][i] = dict(b, f=forma or b.get("f"), c=color or b.get("c"))
        cuerpo = {"agente": aid}
        if forma:
            cuerpo["forma"] = forma
        if color:
            cuerpo["color"] = color

        def hacer():
            try:
                self._post("/api/front/apariencia", cuerpo)
            except ErrorServidor as e:
                with self.lock:
                    j = next((n for n, x in enumerate(self.d["agentes"]) if x["id"] == aid), None)
                    if j is not None:
                        self.d["agentes"][j] = dict(self.d["agentes"][j], f=antes[0], c=antes[1])
                self._avisar("No cambió: " + e.texto)
        self.en_fondo(hacer)

    def _renombrar(self, aid, nombre):
        i = next((n for n, b in enumerate(self.d["agentes"]) if b["id"] == aid), None)
        if i is None:
            return
        orig = next((x.get("nombre_original") for x in (self._dato("inicio") or {}).get("agentes") or []
                     if x.get("id") == aid), None) or aid
        antes = self.d["agentes"][i]["n"]
        n = " ".join(nombre.split())[:40]
        self.d["agentes"][i] = dict(self.d["agentes"][i], n=n or orig)

        def hacer():
            try:
                self._post("/api/front/nombre", {"agente": aid, "nombre": "" if n == orig else n})
            except ErrorServidor as e:
                with self.lock:
                    j = next((k for k, x in enumerate(self.d["agentes"]) if x["id"] == aid), None)
                    if j is not None:
                        self.d["agentes"][j] = dict(self.d["agentes"][j], n=antes)
                self._avisar("No cambió: " + e.texto)
                return
            self._avisar("En esta computadora se llama %s." % (n or orig))
        self.en_fondo(hacer)

    # ── el mouse ──
    def vista(self, T):
        """Lo que se pintó (sus zonas, la ventana del riel y si la sección va lado a lado), para responder al
        siguiente evento del mouse."""
        with self.lock:
            self.zonas = list(getattr(T, "zonas", None) or ())
            self.riel_vista = getattr(T, "riel", None)
            self.sec_lado = bool(getattr(T, "lado", True))
            self.ancho = T.w
            G = getattr(T, "geo", None) or {}
            nv = G.get("nivel") or ""
            if nv != self.nivel:
                if self.nivel:
                    self.cajon = False                # otro ancho: el cajón se cierra (o ya hay panel)
                self.nivel = nv
            zs, vistos = [], set()
            for z in getattr(T, "zonas", None) or ():
                rid = z[4]
                if rid in PASIVAS_FOCO or rid in vistos or rid.startswith("menu:") or rid.startswith(PASIVAS_PREF):
                    continue
                vistos.add(rid)
                zs.append((area_de(z), rid, z[0], z[1], z[2], z[3]))
            self.focos_z = zs
            hay_lista = self.seccion is not None and any(z[0] == "lista" for z in zs)
            if piel() != "bloque" and (self.foco not in vistos or
                                        (self.seccion is not None and area_de((0, 9, 0, 0, self.foco)) == "lista") or
                                        (self.foco_auto and hay_lista and area_de((0, 9, 0, 0, self.foco)) != "lista")):
                self.foco = self._foco_defecto()      # (en la lista, el foco es la fila elegida; si la lista llegó
                self.foco_auto = True                 # después de abrir, el foco pasa a ella si no lo moviste)
            self.ini_focos = [f[0] for f in getattr(T, "focos", None) or ()]
            self._ini_grilla = list(getattr(T, "focos", None) or ())
            if self.inicio and self.seccion is None:
                self._pedir_inicio()
            if self.seccion is not None and self.seccion.get("kind") == "conexiones":
                self._pedir_r2("conexiones")          # su avance mientras verifica (y lo viejo, cada tanto)
            self.panel_visto = bool(G.get("panel") or G.get("franja") or G.get("cajon")) and self.seccion is None
            if self.panel_visto:
                self._pedir_panel(bool(G.get("panel") or G.get("cajon")))

    def _pedir_inicio(self):
        """Lo que Inicio enseña: las sesiones de cada agente (lo que te espera), las skills, los motores, la memoria,
        las conversaciones y el calendario. Solo lo viejo o lo que falta; con respiro si falla."""
        import hub_secciones_r2 as R2
        self._pedir("preferencias", R2.preferencias_locales)
        import hub_agentes_maquina as HM              # los archivados: se traen de vuelta desde «Agente nuevo»
        self._pedir(HM.CLAVE_INICIO, HM.leer_archivados)
        ahora_ = self.reloj()
        if ahora_ - self.falla_t.get("ses_todas", -1e9) >= SES_TODAS_S:
            self._pedir_ses_todas()
        sk = self.skills_todas
        if not self.skills_cargando and (sk is None or ahora_ - sk[0] >= SKILLS_S) and \
                ahora_ - self.falla_t.get("skills", -1e9) >= SKILLS_S:
            self.skills_cargando = True
            self.en_fondo(lambda: self.leer_skills(callado=True))
        for clave, ruta in (("motores", "/api/sistema/motores"), ("calendario", "/api/calendario")):
            if ahora_ - self.falla_t.get(clave, -1e9) >= SECCION_S:
                self._pedir(clave, (lambda r=ruta: self.srv.get(r)))

    # ── «Agregar agente» (hub_agregar): la tarjeta en Inicio ──
    def abrir_agregar(self, modo="crear"):
        """LA PUERTA de «+ Agregar» (todas): Inicio con la tarjeta abierta. `modo`: crear · cargar («Ya tengo un
        agente») · primera (con el paso «Tú»). Sin agentes y sin primer arranque hecho, «crear» es el primer arranque.
        Si una creación sigue en el fondo, la vuelve a enseñar. → None (para devolverlo desde una tecla o un clic)."""
        import hub_agregar
        import agregar_logica
        self._cerrar_menus()
        self.guia = None
        self.seccion, self.cajon, self.inicio = None, False, True
        self.ini_busca, self.ini_buscando = "", False
        if self.agregar is not None and self.agregar.paso in ("creando", "conectando", "afina"):
            self.agregar.visible = True
            return None
        if modo == "crear" and not self.d["agentes"] and agregar_logica.es_primer_arranque():
            modo = "primera"
        self.agregar = hub_agregar.Tarjeta(self, modo)
        return None

    def _vista_agregar(self):
        """Lo que pinta la tarjeta (y su paso en el fondo aunque no se vea). None si no está abierta."""
        t = self.agregar
        if t is None:
            return None
        try:
            v = t.vista()
        except Exception:
            _anotar_falla(self.prefs_ruta)
            self.agregar = None
            return None
        if t.terminado:
            self._fin_agregar(t)
            return None
        return v if t.visible else None

    def _de_agregar(self, r):
        """Lo que devolvió la tarjeta: «cerrar» (se cierra, o termina con el agente nuevo), «salir», un plan para
        ceder la terminal (entrar a su cuenta, instalar su motor) o None."""
        if r == "cerrar":
            t = self.agregar
            if t is not None and t.terminado:
                self._fin_agregar(t)
            elif t is not None and not t.visible:     # sigue creando en el fondo
                self._ir_inicio()
            else:
                self.agregar = None
                self._ir_inicio()
            return None
        return r

    def _fin_agregar(self, t):
        """La tarjeta terminó: Inicio con el agente nuevo elegido (o su conversación, o sus sesiones)."""
        self.agregar = None
        como, nombre = t.terminado, t.comando
        i = self._idx(nombre)
        if i < 0 and nombre:
            t._releer()
            i = self._idx(nombre)
        if como == "aviso":
            self._avisar(t.aviso_listo())
            return
        self.ini_nuevo = False
        if i >= 0:
            self._elegir(i)
            self.anim.setdefault(nombre, {})["fiesta"] = self.reloj()
        if como == "conversar" and i >= 0:
            self._ir_conversacion(i)
        elif como == "sesiones" and i >= 0:
            self._ir_inicio()
            self._abrir_s1(i)
        else:
            self._ir_inicio()

    # ── Inicio: ←→↑↓ entre tarjetas y mosaicos, Enter abre ──
    def _ir_inicio(self):
        self._cerrar_menus()
        self.seccion, self.cajon, self.inicio = None, False, True
        self.ini_busca, self.ini_buscando, self.ini_motor = "", False, {}
        a = self.agente()
        self.foco = "ini:card:" + a["id"] if a else ""

    def _ir_conversacion(self, i):
        """De Inicio a la conversación directa del agente `i` (brinca)."""
        self._cerrar_menus()
        self.inicio, self.seccion, self.ini_busca = False, None, ""
        if 0 <= i < len(self.d["agentes"]):
            self._elegir(i, seguir=True)
        self.foco = "in:texto"

    def _idx(self, aid):
        return next((i for i, b in enumerate(self.d["agentes"]) if b["id"] == aid), -1)

    # ── el foco (H-1): Tab entre áreas, flechas adentro, Enter = su clic, Esc un nivel atrás ──
    def _area_foco(self):
        a = next((z[0] for z in self.focos_z if z[1] == self.foco), "")
        if not a and self.foco and self.foco.startswith(("ini:", "sr:")):   # aún sin pintar (teclas seguidas)
            a = area_de((0, 9, 0, 0, self.foco))
        return a

    def _items(self, area):
        return [z for z in self.focos_z if z[0] == area]

    def _foco_defecto(self):
        """Dónde empieza el foco en esta pantalla: la tarjeta del elegido en Inicio, la fila elegida de la lista en una
        sección, la caja de escribir en la conversación."""
        rids = [z[1] for z in self.focos_z]
        if self.seccion is not None:
            import hub_secciones as S
            _r, sel = S.filas(self.seccion.get("kind"), self.instantanea_ligera())
            if "sr:" + str(sel) in rids:
                return "sr:" + str(sel)
            return next((r for a, r, *_x in self.focos_z if a == "lista"), rids[0] if rids else "")
        if self.inicio:
            a = self.agente()
            if self.ini_nuevo and "ini:card:+nuevo" in rids:
                return "ini:card:+nuevo"
            if a and "ini:card:" + a["id"] in rids:
                return "ini:card:" + a["id"]
            return next((r for r in rids if r.startswith("ini:card:")), rids[0] if rids else "")
        if "in:texto" in rids:
            return "in:texto"
        return rids[0] if rids else ""

    def instantanea_ligera(self):
        """Lo que piden las filas de las secciones (sin todo lo de la pantalla)."""
        return self.instantanea()

    def _enfocar_area(self, area):
        items = self._items(area)
        if not items:
            return
        guardado = self.foco_mem.get(area)
        if area == "riel" and any(z[1] == "riel:%d" % self.sel for z in items):
            guardado = "riel:%d" % self.sel
        elif area == "lista":
            guardado = self._foco_defecto() if self.seccion is not None else guardado
        elif area == "secciones" and str(guardado or "").startswith("ini:sub:"):
            guardado = "ini:sec:" + guardado.split(":")[2]   # Tab regresa a la sección, no a una de sus partes
        self.foco = guardado if any(z[1] == guardado for z in items) else items[0][1]

    def _mover_foco(self, k):
        """La zona más cercana hacia esa flecha, en la misma área (si no hay, se queda)."""
        cur = next((z for z in self.focos_z if z[1] == self.foco), None)
        if cur is None:
            return False
        area, _r, x, y, w, h = cur
        cx, cy = x + w / 2.0, y + h / 2.0
        mejor, puntos = None, None
        for z in self._items(area):
            if z[1] == self.foco:
                continue
            zx, zy = z[2] + z[4] / 2.0, z[3] + z[5] / 2.0
            dx, dy = zx - cx, zy - cy
            if k == "abajo" and z[3] >= y + h:
                pts = dy + abs(dx) * 0.5
            elif k == "arriba" and z[3] + z[5] <= y:
                pts = -dy + abs(dx) * 0.5
            elif k == "derecha" and z[2] >= x + w and abs(dy) < max(h, z[5]) + 1:
                pts = dx + abs(dy) * 2
            elif k == "izquierda" and z[2] + z[4] <= x and abs(dy) < max(h, z[5]) + 1:
                pts = -dx + abs(dy) * 2
            else:
                continue
            if puntos is None or pts < puntos:
                mejor, puntos = z[1], pts
        if mejor:
            self.foco = mejor
            self.foco_mem[area] = mejor
            return True
        return False

    # ── Conexiones: verificar de verdad y reparar por el camino oficial ──
    def _accion_conexiones(self, acc):
        import hub_conexiones as CX
        sec = self.seccion
        s = self.instantanea()
        if not sec.get("lab"):
            return self._accion_verde(acc)
        f, pieza = CX.cursor(s, sec)
        if acc == "evidencia":
            sec["evidencia"] = not sec.get("evidencia")
        elif acc == "verificar_todos":
            self._verificar(None)
        elif acc == "verificar" and f:
            self._verificar([f["motor"]], f.get("nombre"))
        elif acc == "reparar" and f:
            return self._reparar(s, f, pieza)
        return None

    # ── Conexiones en verde: la acción de cada fila, Revisar ahora, Reportar, Deshacer ──
    def _accion_verde(self, acc):
        import hub_conexiones as CX
        sec = self.seccion
        s = self.instantanea()
        if acc.startswith("fila:"):
            m, f = CX.accion_fila(s, sec, acc[5:])
            if m and f:
                sec["sel"] = "cv:%s:%s" % (m.get("motor"), f.get("id"))
            acc = "fila"
        if acc == "lab":
            if CX.es_dev():
                sec["lab"] = True
                sec["sel"] = None
                self._pedir_r2("conexiones")
            return None
        if acc == "motores":
            self._abrir_seccion("motores")
            return None
        if acc == "revisar" or acc == "card:revisar":
            m, _f = CX.cursor_v(s, sec)
            return self._revisar_cx(m.get("motor") if (m and acc == "card:revisar") else "")
        if acc == "deshacer":
            av = CX.aviso_reciente(s) or {}
            if not av.get("deshacer"):
                self._avisar("No hay un arreglo que deshacer.")
                return None
            return self._post_cx("/api/v2/chequeo/deshacer", {"id": av["deshacer"]})
        m, f = CX.cursor_v(s, sec)
        if acc in ("reportar", "card:reportar"):
            return self._post_cx("/api/v2/chequeo/reportar", {"motor": (m or {}).get("motor") or "",
                                                              "fila": (f or {}).get("id") or "" if acc == "reportar"
                                                              else ""})
        if acc == "card:otro":
            alt = ((m or {}).get("cambio") or {}).get("alternativa") or ""
            self._abrir_seccion("motores")
            if alt:
                self.seccion["sel"] = "mot:" + alt
            self._avisar("Elige el motor con el que siguen tus agentes%s." % (
                (" (%s salió bien)" % nombre_motor(alt)) if alt else ""))
            return None
        if acc != "fila" or not f:
            return None
        ac = f.get("accion") or {}
        if not ac:
            self._avisar("%s: funciona, nada que hacer." % (f.get("nombre") or "Esta fila"))
            return None
        if ac.get("tipo") == "arreglar":
            return self._post_cx("/api/v2/chequeo/arreglar", {"arreglo": ac.get("arreglo") or ""})
        if ac.get("tipo") == "reportar":
            return self._post_cx("/api/v2/chequeo/reportar", {"motor": m.get("motor"), "fila": f.get("id")})
        motor = ac.get("motor") or m.get("motor")
        if ac.get("abrir") == "login":
            p = self._plan_login(motor)
        elif ac.get("abrir") == "confiar":
            nom = ac.get("agente_nombre") or ac.get("agente") or "tu agente"
            i = self._idx(str(ac.get("agente") or ""))
            if i < 0:
                i = next((j for j, a in enumerate(self.d["agentes"]) if (a.get("n") or "") == nom), -1)
            if i < 0:
                self._avisar("Abre en Codex a %s y escribe /hooks." % nom)
                return None
            p = P.plan({"tipo": "abrir", "agente": i, "texto": ""}, self.d["agentes"], motor=motor)
            if isinstance(p, dict):
                p["guia"] = {"titulo": "Codex · Confiar en los avisos de Workspace",
                             "lineas": ["Se abre Codex, su programa oficial, en la carpeta de %s." % nom,
                                        "1. Escribe /hooks y Enter.",
                                        "2. Confía en los de Workspace (una sola vez) y sal con /exit.",
                                        "Al volver, Workspace revisa Codex solo."],
                             "agente": self.d["agentes"][i].get("id")}
        else:
            self._abrir_seccion("motores")
            self.seccion["sel"] = "mot:" + str(motor)
            return None
        if isinstance(p, dict):
            p["revisar_despues"] = motor
        return p

    def _post_cx(self, ruta, cuerpo):
        """Un POST de Conexiones en el fondo: su texto en el aviso de abajo y el chequeo, otra vez."""
        def hacer():
            try:
                r = self.srv.post(ruta, cuerpo)
            except ErrorServidor as e:
                self._avisar(e.texto)
                return
            self._avisar(str(r.get("texto") or "Listo."))
            self._recargar("chequeo", lambda: self.srv.get("/api/v2/chequeo"))
        self._avisar("Un momento…")
        self.en_fondo(hacer)
        return None

    def _revisar_cx(self, motor=""):
        """«Revisar ahora» (o «Volver a revisar» de un motor): el chequeo rápido, sin IA, en el servidor."""
        def hacer():
            try:
                self.srv.post("/api/v2/chequeo/revisar", {"motor": motor} if motor else {})
            except ErrorServidor as e:
                self._avisar(e.texto)
                return
            self._recargar("chequeo", lambda: self.srv.get("/api/v2/chequeo"))
        self._avisar("Revisando %s sin IA (unos segundos)…" % (nombre_motor(motor) if motor else "todo"))
        self.en_fondo(hacer)
        return None

    def _verificar(self, motores=None, nombre=""):
        """«Verificar ahora» (de todos o de un motor): la auditoría con el motor real, en el fondo y una a la vez, por
        la página (POST /api/v2/verificar). Si la página prendida no la trae, la MISMA auditoría desde aquí
        (arquitectura/verificacion.lanzar): guarda donde la página lee y su avance se ve igual."""
        if (self._dato("conexiones_v") or {}).get("corriendo"):
            self._avisar("Ya hay una verificación en marcha: espera a que termine.")
            return

        def hacer():
            try:
                r = self.srv.post("/api/v2/verificar", {"motor": motores[0]} if motores else {})
            except ErrorServidor as e:
                if e.status not in (400, 404) and not e.sin_ruta:
                    self._avisar(e.texto)
                    return
                try:
                    from arquitectura import verificacion
                    r = verificacion.lanzar(motores)
                except Exception as ex:              # pragma: no cover
                    r = {"ok": False, "motivo": str(ex)}
            if not r.get("ok"):
                self._avisar("No pude empezar la verificación: %s" % (r.get("motivo") or "ya hay una en marcha"))
                return
            self._avisar("Verificando %s de verdad (un turno corto, con un cerebro temporal)…" % (nombre or "todos"))
            self._recargar("conexiones_v", lambda: self.srv.get("/api/v2/conexiones", timeout=60))
        self.en_fondo(hacer)

    def _reparar(self, s, f, pieza):
        """«Reparar» en una celda: lleva al arreglo por el camino oficial (nunca se salta nada ni se escribe la config
        del motor) con su guía antes; al volver, otra verificación real de ese motor."""
        import hub_conexiones as CX
        rep = CX.reparacion(s, f, pieza)
        if not rep:
            self._avisar("Esta celda está bien (o no se usa en este motor): nada que reparar.")
            return None
        motor = rep["motor"]
        if rep["tipo"] == "verificar":
            self._avisar(rep["guia"][0])
            self._verificar([motor], rep.get("nombre"))
            return None
        if rep["tipo"] in ("login", "cuenta"):
            p = self._plan_login(motor)
            if rep["tipo"] == "cuenta":
                try:
                    import engine_install
                    cmd = list((engine_install.recipe(motor) or {}).get("account_cmd") or [])
                except Exception:
                    cmd = []
                p = {"programa": "cuenta", "motor": motor, "argv": cmd} if cmd and shutil.which(cmd[0]) else p
        elif rep["tipo"] == "comando":
            cmd = rep.get("comando") or []
            p = {"programa": "cuenta", "motor": motor, "argv": cmd} if cmd and shutil.which(cmd[0]) else None
            if p is None:
                self._avisar(rep["guia"][0])
                return None
        else:                                         # confiar / abrir: su programa oficial en la carpeta del agente
            i = self._idx(rep.get("agente") or "")
            if i < 0:
                return None
            p = P.plan({"tipo": "abrir", "agente": i, "texto": ""}, self.d["agentes"], motor=motor)
        if not isinstance(p, dict):
            return None
        p["guia"] = {"titulo": "%s · %s" % (rep.get("nombre") or motor, rep["etiqueta"]), "lineas": rep["guia"],
                     "agente": rep.get("agente") or self.id_elegido()}
        p["verificar_despues"] = motor
        return p

    def _tecla_tablero(self, k):
        """Agentes › Tablero: ←→ el agente (la columna), ↑↓ el motor (la fila), Enter lo del cruce."""
        import hub_secciones as S
        import hub_secciones_r2 as R2
        sec = self.seccion
        s = self.instantanea()
        if k == "enter":
            return self._accion_seccion("tablero")
        if k in ("izquierda", "derecha"):
            filas = S.agentes_filas(s)
            rids = [f["rid"] for f in filas]
            cur = S.elegida(sec, filas)
            if rids:
                j = (rids.index(cur) if cur in rids else 0) + (1 if k == "derecha" else -1)
                sec["sel"] = rids[max(0, min(j, len(rids) - 1))]
                self.foco = "sr:" + sec["sel"]
            return None
        ms = R2._motores(s) or []
        _b, mid = R2.tablero_cursor(s, sec)
        ids = [m.get("id") for m in ms]
        if ids:
            j = (ids.index(mid) if mid in ids else 0) + (1 if k == "abajo" else -1)
            sec["mot"] = ids[max(0, min(j, len(ids) - 1))]
        return None

    def _mover_mosaico(self, k):
        """Los mosaicos de Inicio: ←→ el mosaico de al lado (en orden de lectura), ↓ entra a sus sub-secciones (o
        al de abajo), ↑ al de arriba. En una sub-sección: ←→ la de al lado, ↑ su mosaico, ↓ el mosaico de abajo.
        No depende de dónde estén: se calcula con las zonas que se pintaron."""
        zs = self._items("secciones")
        mos = sorted((z for z in zs if z[1].startswith("ini:sec:")), key=lambda z: (z[3], z[2]))
        if not mos:
            return False
        f = self.foco or ""

        def subs(mid):
            return [z for z in zs if z[1].startswith("ini:sub:%s:" % mid)]

        def vecino(z, d):                             # el mosaico de abajo (d=1) o arriba (d=-1), en su columna
            cx = z[2] + z[4] / 2.0
            c = [m for m in mos if (m[3] - z[3]) * d > 0]
            if not c:
                return None
            y = min(c, key=lambda m: abs(m[3] - z[3]))[3]
            return min((m for m in c if m[3] == y), key=lambda m: abs(m[2] + m[4] / 2.0 - cx))[1]

        destino = None
        if f.startswith("ini:sub:"):
            mid = f.split(":")[2]
            ss = [z[1] for z in subs(mid)]
            padre = next((m for m in mos if m[1] == "ini:sec:" + mid), None)
            if k in ("izquierda", "derecha") and f in ss:
                j = ss.index(f) + (1 if k == "derecha" else -1)
                destino = ss[j] if 0 <= j < len(ss) else None
            elif k == "arriba":
                destino = padre and padre[1]
            elif k == "abajo":
                destino = padre and vecino(padre, 1)
        else:
            cur = next((m for m in mos if m[1] == f), None)
            if cur is None:
                return False
            if k in ("izquierda", "derecha"):
                j = mos.index(cur) + (1 if k == "derecha" else -1)
                destino = mos[j][1] if 0 <= j < len(mos) else None
            elif k == "abajo":
                ss = subs(f[8:])
                destino = ss[0][1] if ss else vecino(cur, 1)
            else:
                destino = vecino(cur, -1)
                if destino is None:                   # nada arriba: la tarjeta del elegido
                    self._ini_tarjeta()
                    return True
        if destino:
            self.foco = destino
            self.foco_mem["secciones"] = destino
        return True

    def _tecla_foco(self, k):
        """Lo que hace una tecla según el foco. NO: que la maneje lo de antes (la caja, la lista, el menú)."""
        if not self.focos_z or self.menu is not None or self.ses is not None or self.barra is not None:
            return NO
        if self.seccion is not None and self.seccion.get("editando"):
            return NO
        area = self._area_foco()
        if k in ("tab", "shift-tab"):
            areas = [a for a in AREAS if self._items(a)]
            if not areas:
                return NO
            i = areas.index(area) if area in areas else -1
            self._enfocar_area(areas[(i + (1 if k == "tab" else -1)) % len(areas)])
            return None
        if area == "chat" and self.foco == "in:texto":
            return NO                                 # la caja de escribir se queda con todo
        if area == "lista":
            return NO                                 # la lista: sus teclas (y las letras la filtran)
        if self.inicio and self.seccion is None:
            return self._tecla_inicio(k)
        if area == "riel":
            return self._tecla_riel(k)
        if k in ("arriba", "abajo", "izquierda", "derecha"):
            self._mover_foco(k)
            return None
        if k == "enter":
            return self._clic(self.foco)
        if k == "esc":
            if self.seccion is not None:              # de un botón del detalle, a la lista
                self._enfocar_area("lista")
                if self._area_foco() != "lista":
                    self._cerrar_seccion()
            else:                                     # del panel, a la caja de escribir
                self.foco = "in:texto"
            return None
        if k == "q":
            return "salir"
        if isinstance(k, str) and len(k) == 1 and k.isprintable() and self.seccion is None:
            self.foco = "in:texto"                    # escribir: a la caja (y la letra va ahí)
            return NO
        return NO

    def _tecla_riel(self, k):
        """El riel: ↑↓ otro agente (la conversación lo sigue), ←→ su motor, Enter a su caja, letras saltan al que
        empieza así, 1-9 directo, q sale, Esc a Inicio."""
        f = self.foco
        es_ag = f.startswith("riel:") and f[5:].isdigit()
        if k in ("arriba", "abajo"):
            if es_ag:                                 # el agente de al lado (aunque no se vea: la ventana lo sigue)
                i = int(f[5:]) + (1 if k == "abajo" else -1)
                if 0 <= i < len(self.d["agentes"]):
                    self._elegir(i)
                    self.foco = "riel:%d" % i
                    return None
            if self._mover_foco(k) and self.foco.startswith("riel:") and self.foco[5:].isdigit():
                self._elegir(int(self.foco[5:]), seguir=False)
            return None
        if k in ("izquierda", "derecha") and es_ag:
            self._motor_paso(int(f[5:]), 1 if k == "derecha" else -1)
            return None
        if k == "enter":
            if es_ag:
                self._elegir(int(f[5:]), seguir=False)
                self.foco = "in:texto"
                return None
            return self._clic(f)
        if k == "esc":
            self._ir_inicio()
            return None
        if k == "q":
            return "salir"
        if k == "?":                                  # ?: la guía
            self._abrir_guia()
            return None
        if k == "ctrl-s":
            self._abrir_s1(self.sel)
            return None
        if isinstance(k, str) and len(k) == 1 and k in "123456789":
            i = int(k) - 1
            if i < len(self.d["agentes"]):
                self._elegir(i)
                self.foco = "riel:%d" % i
            return None
        if isinstance(k, str) and len(k) == 1 and k.isalpha():
            pre, t0 = self.salto
            pre = (pre if self.reloj() - t0 < 1.2 else "") + k
            self.salto = (pre, self.reloj())
            q = P._sin_acentos(pre)
            i = next((n for n, b in enumerate(self.d["agentes"]) if P._sin_acentos(b["n"]).startswith(q)), None)
            if i is not None:
                self._elegir(i)
                self.foco = "riel:%d" % i
            return None
        return NO

    def _tecla_inicio(self, k):
        """Inicio R-1: ←→ otro agente (se desliza), ↑↓ su motor, Enter conversar (o lo que necesite su motor), s sus
        sesiones, n el navegador, Tab las secciones, escribir (o /) busca, 1-9 directo, q sale (Esc: en la tarjeta
        sale; en las secciones o la barra, regresa a la tarjeta; buscando, deja de buscar)."""
        import hub_inicio as I
        area = self._area_foco()
        if self.ini_busca or self.ini_buscando:
            if k == "esc":
                self.ini_busca, self.ini_buscando = "", False
                return None
            if k == "borrar":
                self.ini_busca = self.ini_busca[:-1]
                self._ini_seguir_busca()
                return None
            if k == "enter":
                r = I.busca(self.instantanea())
                self.ini_busca, self.ini_buscando = "", False
                if r and r[0] == "agente":
                    return self._ini_accion(r[1])
                if r and r[0] in ("seccion", "sub"):
                    return self._activar_inicio(("ini:sec:" if r[0] == "seccion" else "ini:sub:") + r[1])
                return None
            if isinstance(k, str) and len(k) == 1 and k.isprintable():
                self.ini_busca += k
                self._ini_seguir_busca()
                return None
            if k in ("tab", "shift-tab"):
                self.ini_busca, self.ini_buscando = "", False
        if k == "/":
            self.ini_buscando = True
            return None
        if k == "q":
            return "salir"
        if k == "esc":
            if area in ("secciones", "barra"):
                self._ini_tarjeta()
                return None
            return "salir"
        if k == "n":                                  # n: la versión del navegador (la página local)
            self._abrir_pagina()
            return None
        if k == "?":                                  # ?: la guía
            self._abrir_guia()
            return None
        if k in ("s", "ctrl-s") and (self.ini_nuevo or not self.d["agentes"]) and area == "agentes":
            return self.abrir_agregar("cargar")       # en el dormido: «Ya tengo uno»
        if k in ("s", "ctrl-s"):                       # s: sus sesiones (S-1, su programa oficial)
            a = self.agente()
            return self._activar_inicio("ini:ses:" + a["id"]) if a else None
        if k == "ctrl-a" and area == "agentes":       # ^A: archivar al de la tarjeta (se deshace con ^U)
            a = self.agente()
            return self._activar_inicio("ini:arch:" + a["id"]) if a else None
        if k == "ctrl-u" and self.apartado:           # ^U: deshacer el último archivar o quitar
            return self._activar_inicio("ini:deshacer")
        if isinstance(k, str) and len(k) == 1 and k in "123456789":
            i = int(k) - 1
            if i < len(self.d["agentes"]):
                self._ir_conversacion(i)
            return None
        if isinstance(k, str) and len(k) == 1 and (k.isalpha() or k in "áéíóúñ"):
            self.ini_busca = k
            self._ini_seguir_busca()
            return None
        f = self.foco
        if area == "agentes":
            if k in ("izquierda", "derecha"):         # ←→: el de al lado (se desliza)
                self._ini_agente(1 if k == "derecha" else -1)
                return None
            if k in ("arriba", "abajo"):              # ↑↓: su motor
                self._ini_motor_paso(-1 if k == "arriba" else 1)
                return None
            if k == "enter":
                return self._ini_accion()
            return None
        if area == "secciones" and k in ("arriba", "abajo", "izquierda", "derecha") and self._mover_mosaico(k):
            return None
        if k in ("arriba", "abajo", "izquierda", "derecha"):
            self._mover_foco(k)
            return None
        if k == "enter":
            return self._clic(f) if f.startswith("bar:") else self._activar_inicio(f)
        return None

    def _ini_tarjeta(self):
        a = self.agente()
        if self.ini_nuevo or not a:
            import agregar_logica
            self.foco = "ini:card:" + agregar_logica.NUEVO_ID
        elif a:
            self.foco = "ini:card:" + a["id"]

    def _ini_seguir_busca(self):
        """Mientras escribes, la tarjeta va al primer agente que lo dice (sin deslizarse)."""
        import hub_inicio as I
        r = I.busca(self.instantanea())
        if r and r[0] == "agente" and r[1] != self.sel:
            self._elegir(r[1])
            self._ini_tarjeta()

    def _ini_agente(self, d):
        """←→ en Inicio: el agente de al lado en el orden de Inicio (da la vuelta), que llega deslizándose."""
        import hub_inicio as I
        ids = I.orden(self.instantanea())
        if not ids:
            return
        cur = len(self.d["agentes"]) if self.ini_nuevo else self.sel      # el dormido va al final
        k = ids.index(cur) if cur in ids else 0
        self._ini_elegir(ids[(k + d) % len(ids)], d)

    def _ini_elegir(self, i, d=1):
        if i == len(self.d["agentes"]):               # el agente dormido del final de la fila
            import agregar_logica
            if not self.ini_nuevo:
                self.ini_nuevo = True
                an = self.anim.setdefault(agregar_logica.NUEVO_ID, {})
                an["desliza"], an["dir"] = self.reloj(), (1 if d > 0 else -1)
            self._ini_tarjeta()
            return
        if not 0 <= i < len(self.d["agentes"]):
            return
        if i != self.sel:
            self._elegir(i)
            an = self.anim.setdefault(self.id_elegido(), {})
            an["desliza"], an["dir"] = self.reloj(), (1 if d > 0 else -1)
        self._ini_tarjeta()

    def _ini_motor_paso(self, d):
        """↑↓ en Inicio: el motor de arriba o de abajo para el elegido. Si está listo, su conversación sigue con él (se
        ve ya y destella); si no, queda elegido sin cambiarse y Enter hace lo que necesita (iniciar sesión…)."""
        import hub_inicio as I
        a = self.agente()
        if not a or self.ini_nuevo:
            return
        ms = (self._dato("motores") or {}).get("motores")
        if ms is None:
            self._avisar("Viendo cómo está cada motor…")
            self._pedir_motores()
            return
        if self._trabaja(a["id"]):
            self._avisar("%s está trabajando: cambia su motor cuando termine." % a["n"])
            return
        actual = (self.fotos.get(a["id"]) or {}).get("motor") or a.get("mid")
        cur = self.ini_motor.get(a["id"]) or actual
        ids = [m.get("id") for m in ms]
        j = ids.index(cur) + d if cur in ids else 0
        if not 0 <= j < len(ms):
            return
        m = ms[j]
        self.anim.setdefault(a["id"], {})["motor"] = self.reloj()        # destella
        if not I.usable(m):
            self.ini_motor[a["id"]] = m["id"]
            return
        self.ini_motor.pop(a["id"], None)
        if m["id"] != actual:
            self.fotos.setdefault(a["id"], {})["motor"] = m["id"]       # se ve ya; la página lo confirma
            self._cambiar_motor(a, {"id": m["id"], "nombre": m.get("nombre") or nombre_motor(m["id"])})

    def _ini_accion(self, i=None):
        """Enter (o «Conversar ↵») en Inicio: su conversación si su motor está listo; si no, lo que necesita."""
        import hub_inicio as I
        if i is None and (self.ini_nuevo or not self.d["agentes"]):
            return self.abrir_agregar()               # Enter en el dormido: la tarjeta
        i = self.sel if i is None else i
        if i == len(self.d["agentes"]):
            return self.abrir_agregar()
        if not 0 <= i < len(self.d["agentes"]):
            return None
        s = self.instantanea()
        a = s["agentes"][i]
        _lab, _v, k = I.accion(s, a)
        mid = I.motor_de(s, a)
        if k == "conv":
            pend = self.ini_motor.pop(a["id"], None)   # el que eligió con ↑↓ ya está listo (p. ej. tras su sesión)
            actual = (self.fotos.get(a["id"]) or {}).get("motor") or a.get("mid")
            if pend and pend != actual and not self._trabaja(a["id"]):
                self.fotos.setdefault(a["id"], {})["motor"] = pend
                self._cambiar_motor(self.d["agentes"][i], {"id": pend, "nombre": nombre_motor(pend)})
            self._ir_conversacion(i)
            return None
        if k == "login":
            return self._plan_login(mid)
        self._abrir_seccion("motores")                 # instalarlo o revisarlo: su fila en Motores y conexiones
        self.seccion["sel"] = "mot:" + str(mid)
        return None

    def _plan_login(self, mid):
        """Iniciar sesión en `mid` con su programa oficial (en esta terminal, y de vuelta al hub). Sin su comando,
        Motores y conexiones."""
        nombre = nombre_motor(mid)
        try:
            import engine_install
            login = list((engine_install.recipe(mid) or {}).get("login_cmd") or [])
        except Exception:
            login = []
        if not login or not shutil.which(login[0]):
            self._abrir_seccion("motores")
            self.seccion["sel"] = "mot:" + str(mid)
            self._avisar("%s: su inicio de sesión está aquí (o en la página)." % nombre)
            return None
        try:                                          # un perfil propio que hay que preparar (Hermes): su adapter
            import importlib
            prep = getattr(importlib.import_module("engines." + str(mid).replace("-", "_")), "prepare_account", None)
            ok, por = prep() if callable(prep) else (True, "")
        except Exception:
            ok, por = True, ""
        if not ok:
            self._avisar("No pude preparar %s: %s" % (nombre, por or "su perfil"))
            return None
        return {"programa": "login", "motor": mid, "argv": login}

    # ── ←→: el motor de la conversación de ese agente ──
    def _usables(self):
        return [m for m in self.motores or [] if m.get("listo") and m.get("sesion") is not False
                and m.get("estado") != "sin_sesion"]

    def _motor_paso(self, i, d):
        ag = self.d["agentes"]
        if not 0 <= i < len(ag):
            return
        a = ag[i]
        if self.motores is None or self.reloj() - self.motores_t >= MOTORES_S:
            self._avisar("Viendo qué motores están listos… (otra vez ←→)")

            def cargar():
                try:
                    m = self.srv.get("/api/sistema/motores").get("motores") or []
                except ErrorServidor as e:
                    self._avisar("No pude ver los motores: " + e.texto)
                    return
                with self.lock:
                    self.motores, self.motores_t = m, self.reloj()
            self.en_fondo(cargar)
            return
        ok = self._usables()
        if not ok:
            self._avisar("No hay un motor listo.")
            return
        if self._trabaja(a["id"]):
            self._avisar("%s está trabajando: Esc lo para antes de cambiar de motor." % a["n"])
            return
        actual = (self.fotos.get(a["id"]) or {}).get("motor") or a.get("mid")
        ids = [m["id"] for m in ok]
        j = (ids.index(actual) + d) % len(ids) if actual in ids else 0
        m = ok[j]
        if m["id"] != actual:
            self.fotos.setdefault(a["id"], {})["motor"] = m["id"]       # se ve ya; la página lo confirma
            self.anim.setdefault(a["id"], {})["motor"] = self.reloj()   # y destella
            self._cambiar_motor(a, {"id": m["id"], "nombre": m.get("nombre") or nombre_motor(m["id"])})

    def _activar_inicio(self, rid):
        """Lo que hace una tarjeta, un mosaico o un botón de Inicio (Enter o clic)."""
        p, _s, resto = rid.partition(":")
        k, _s, arg = resto.partition(":")
        if p != "ini":
            return None
        import agregar_logica
        if arg == agregar_logica.NUEVO_ID:            # el agente dormido del final de la fila
            if k in ("ag", "punto") or (k == "card" and not (self.ini_nuevo or not self.d["agentes"])):
                self._ini_elegir(len(self.d["agentes"]), 1)
                return None
            if k == "ses":
                return self.abrir_agregar("cargar")
            if k in ("card", "conv"):
                return self.abrir_agregar()
        if k == "arch":                               # «Archivar» en su tarjeta (se deshace desde el aviso)
            import hub_agentes_maquina as HM
            return HM.desde_inicio(self, arg)
        if k == "deshacer":
            import hub_agentes_maquina as HM
            return HM.deshacer(self)
        if k == "volver":                             # un archivado, desde la tarjeta de «Agente nuevo»
            import hub_agentes_maquina as HM
            return HM._apartar(self, "volver", arg, "")
        if k == "archmas":                            # los que no cabían en la fila: los siguientes
            self.ini_arch_i = getattr(self, "ini_arch_i", 0) + 1
            return None
        if k in ("card", "conv"):                     # el monito grande o «Conversar ↵»: lo que pide su motor
            i = self._idx(arg)
            if i >= 0 and i != self.sel:
                self._ini_elegir(i)
                return None
            return self._ini_accion(i)
        if k in ("ag", "punto"):                      # uno de al lado o su cuadrito: al centro
            i = self._idx(arg)
            ids = __import__("hub_inicio").orden(self.instantanea())
            d = 1 if (i in ids and self.sel in ids and ids.index(i) > ids.index(self.sel)) else -1
            self._ini_elegir(i, d)
        elif k == "flecha":
            self._ini_agente(1 if arg == "1" else -1)
        elif k == "mot":                              # ▲ ▼ del selector
            if arg in ("arriba", "abajo"):
                self._ini_motor_paso(-1 if arg == "arriba" else 1)
            self._ini_tarjeta()
        elif k == "buscar":
            self.ini_buscando = True
        elif k == "resp":
            self._ir_conversacion(self._idx(arg))
        elif k == "ses":                              # sus sesiones (S-1): las pinta el hub, con la lista que ya trae
            i = self._idx(arg)
            if i >= 0:
                self.ini_foco = "ini:card:" + arg
                self._abrir_s1(i)
        elif k == "abrir":                            # una sesión que te espera: la abre en su programa
            aid, _s, wid = arg.partition(":")
            i = self._idx(aid)
            r = next((x for x in self.ses_todas.get(aid) or [] if str(x.get("wid")) == wid), None)
            if i >= 0 and r:
                return self._retomar(r, i)
        elif k == "sesiones":
            self._abrir_seccion("sesiones")
        elif k == "web":                              # «Abrir en el navegador ↗»
            self._abrir_pagina()
        elif k == "todos":
            self._abrir_seccion("agentes")
        elif k == "nuevo":
            return self._abrir_agregar()
        elif k == "sub":                               # una sub-sección: su sección en esa pestaña o ese grupo
            kind, _s, sub = arg.partition(":")
            if kind == "motores":                     # «Motores y conexiones»: Conexiones o la lista de Motores
                self._abrir_seccion("conexiones" if sub == "conexiones" else "motores")
                return None
            if kind == "agentes" and sub == "agregar":
                return self._abrir_agregar()
            aid = self.id_elegido()
            self._abrir_seccion(kind)
            if kind == "agentes" and sub == "tablero":
                self.seccion["vista"], self.seccion["sel"] = "tablero", "ag:" + aid
            elif kind == "agentes":
                self.seccion["tab"], self.seccion["sel"] = sub, "ag:" + aid
                self._pedir_r2("agentes")
            elif kind == "ajustes":
                import hub_secciones_r2 as R2
                self.seccion["sel"] = R2.primera_del_grupo(self.instantanea(), sub)
            elif kind == "ayuda":
                import hub_secciones_r2 as R2
                self.seccion["sel"] = R2.primera_de_ayuda(sub)
        elif k == "sec":
            import hub_inicio
            if arg in hub_inicio.EN_CAMINO:
                self._abrir_seccion("encamino")
                self.seccion["cual"] = arg
            else:
                self._abrir_seccion(arg)              # H3-b: Motores, su propia sección (Conexiones: en Ajustes)
        return None

    def _pedir_panel(self, abierto=True):
        """Lo que el panel (o su franja) enseña del elegido: sus sesiones (cada PANEL_SES_S), sus skills y cómo está
        su motor. Solo lo viejo o lo que falta; nunca dos veces a la vez."""
        aid = self.id_elegido()
        if not aid:
            return
        ahora_ = self.reloj()
        sk = self.skills_todas
        if not self.skills_cargando and (sk is None or ahora_ - sk[0] >= SKILLS_S) and \
                ahora_ - self.falla_t.get("skills", -1e9) >= SKILLS_S:
            self.skills_cargando = True
            self.en_fondo(lambda: self.leer_skills(callado=True))
        if ahora_ - self.falla_t.get("motores", -1e9) >= SECCION_S:
            self._pedir_motores()

    def zona(self, x, y):
        """La zona en (x, y): la última dibujada gana (un menú abierto, sobre lo de abajo). '' si no hay."""
        for zx, zy, zw, zh, rid in reversed(self.zonas):
            if zx <= x < zx + zw and zy <= y < zy + zh:
                return rid
        return ""

    def raton(self, ev):
        """Un evento del mouse (P.Raton). → lo mismo que tecla (None, «salir» o un plan), o SIN_CAMBIO si no cambió
        nada (el mouse se movió sin salir de su zona: no hace falta repintar)."""
        with self.lock:
            t = ev.tipo
            if self.arrastre is not None:             # arrastrando el borde del riel
                if t == "arrastra" and ev.boton == 0:
                    self.arrastre["x"] = ev.x
                    return None
                if t == "sube":
                    arr, self.arrastre, self.apretado = self.arrastre, None, None
                    x = ev.x if arr.get("x") is None else arr["x"]
                    if abs(x - arr["x0"]) < 2:        # sin arrastrar: un clic en el borde también lo abre o cierra
                        self._alternar_riel()
                    else:
                        self._alternar_riel(x + 1 >= (RIEL_ARRASTRE_MITAD))
                    return None
                if t in ("mueve", "baja"):
                    self.arrastre = None
            zid = self.zona(ev.x, ev.y)
            if t == "mueve":
                if zid == self.sobre:
                    return SIN_CAMBIO
                self.sobre = zid
                self._hover(zid)
                return None
            if t in ("rueda_arriba", "rueda_abajo"):
                self._rueda(zid, t == "rueda_arriba")
                return None
            if t == "arrastra" or ev.boton != 0:      # el arrastre no cambia el hover; el derecho y el medio, nada
                return SIN_CAMBIO
            if t == "baja":
                self.apretado = zid
                if zid == "riel:borde":
                    self.arrastre = {"x0": ev.x, "x": None}
                if zid != self.sobre:
                    self.sobre = zid
                    self._hover(zid)
                return None
            if t == "sube":                           # el clic: al soltar, sobre la misma zona en que bajó
                ap, self.apretado = self.apretado, None
                self.sobre = zid
                if ap is None or ap != zid:
                    return None
                return self._clic(zid)
            return SIN_CAMBIO

    def _idx_motor(self, mid):
        m = self.menu
        if m is None:
            return None
        if mid == "seccion":
            return m["n"]
        return next((i for i, r in enumerate(m["filas"]) if r["id"] == mid and i < m["n"]), None)

    def _idx_ses(self, wid):
        m = self.ses
        if m is None:
            return None
        if wid in ("nueva", "conv", "seccion"):
            return next((i for i, r in enumerate(m["filas"]) if r.get("tipo") == wid), None)
        return next((i for i, r in enumerate(m["filas"]) if str(r.get("wid")) == wid), None)

    def _hover(self, zid):
        """El mouse encima de una fila de un menú o de una sección la elige (como en un menú de Mac: el mouse y ↑↓
        mueven lo mismo)."""
        p, _s, resto = zid.partition(":")
        if p == "mo":
            i = self._idx_motor(resto)
            if i is not None:
                self.menu["i"] = i
        elif p == "se":
            i = self._idx_ses(resto)
            if i is not None and i != self.ses["i"]:
                self.ses["i"], self.confirma = i, None
        elif p in ("ag", "sk", "mn") and self.barra is not None:
            self.barra["rid"] = zid
        # en una sección, el mouse encima solo ilumina: lo elegido (y su detalle) cambia con el clic

    def _mover_riel(self, d):
        if not self.riel_vista:
            return
        i0, cabe, n = self.riel_vista
        if n > cabe:
            self.riel0 = max(0, min(i0 + d, n - cabe))

    def _rueda(self, zid, arriba):
        if self.s1 is not None:
            self.s1["menu"].rueda(arriba)
            return
        p = zid.partition(":")[0]
        if p in MENU_P and self._menu_abierto():      # sobre un menú abierto: mueve su fila elegida
            k = "arriba" if arriba else "abajo"
            if self.menu is not None:
                self._tecla_menu(k)
            elif self.ses is not None:
                self._tecla_ses(k)
            else:
                self._mover_barra(-1 if arriba else 1)
        elif p == "riel":                             # sobre el riel: mueve su ventana, sin cambiar de agente
            self._mover_riel(-1 if arriba else 1)
        elif self.seccion is not None:                # en una sección: mueve lo elegido de su lista
            if p in ("lista", "sr", "sgr"):
                self._mover_seccion(-1 if arriba else 1)
        elif p not in ("bar", "pan", "fr"):           # la conversación: 3 renglones por paso
            self.scroll = self.scroll + RUEDA if arriba else max(0, self.scroll - RUEDA)

    def _clic(self, zid):
        if self.agregar is not None and self.agregar.visible:       # «Agregar agente»: sus botones y campos
            return self._de_agregar(self.agregar.clic(zid))
        if self.s1 is not None:                       # S-1 en el hub: sus botones y sus filas
            return self._clic_s1(zid)
        if self.guia is not None:                     # la guía: solo su ficha se toca
            return self._tecla_guia({"guia:sig": "enter", "guia:atras": "izquierda",
                                     "guia:salir": "esc"}.get(zid, ""))
        p, _s, resto = zid.partition(":")
        if self.cajon and p not in ("pan", "fr") and not (p in MENU_P and self._menu_abierto()):
            self.cajon = False                        # un clic afuera del panel encima lo cierra (como Esc)
            self._cerrar_menus()
            return None
        if p == "ini":
            if self._menu_abierto():
                self._cerrar_menus()
                return None
            if zid.startswith("ini:card:") or zid.startswith("ini:sec:"):
                self.ini_foco = self.foco = zid
            return self._activar_inicio(zid)
        if p == "nav" and resto == "inicio":
            self._ir_inicio()
            return None
        if p == "pan":
            return self._clic_panel(resto)
        if p == "fr":
            return self._clic_franja(resto)
        if p == "bar":
            return self._accion_barra(resto)
        if p == "hdr":
            return self._accion_barra("motor" if resto == "motor" else "sesiones")
        if p == "tb":
            return self._clic_tab(resto)
        if self._menu_abierto() and p not in MENU_P:
            self._cerrar_menus()                      # un clic afuera cierra el menú, como Esc
            return None
        if p == "menu":
            return None
        if p == "mo":
            i = self._idx_motor(resto)
            if i is None:
                return None
            self.menu["i"] = i
            return self._tecla_menu("enter")
        if p == "se":
            i = self._idx_ses(resto)
            if i is None:
                return None
            if i != self.ses["i"]:
                self.ses["i"], self.confirma = i, None
            return self._tecla_ses("enter")
        if p in ("ag", "sk", "mn"):
            return self._accion_menu(zid)
        if p == "riel":
            if resto == "arriba":
                self._mover_riel(-1)
            elif resto == "abajo":
                self._mover_riel(1)
            elif resto == "borde":
                self._alternar_riel()
            elif resto == "nuevo":                    # «+ Agregar agente», al pie del riel
                return self._abrir_agregar()
            elif resto.isdigit() and int(resto) == self.sel and self.seccion is None:
                self.anim.setdefault(self.id_elegido(), {})["gel"] = self.reloj()   # picarlo: la gelatina
            elif resto.isdigit() and int(resto) < len(self.d["agentes"]):
                self._elegir(int(resto), seguir=False)
                if self.seccion is not None:          # en una sección: la sección cambia a ese agente
                    self._seccion_de(self.id_elegido())
            return None
        if self.seccion is not None:
            return self._clic_seccion(p, resto, zid)
        a = self.agente()
        if a is None:
            return None
        aid = a["id"]
        pm, q = self._permiso(aid), self._pregunta(aid)
        if p in ("perm", "preg"):
            ops = opciones_de(pm, q)
            i = int(resto) if resto.isdigit() else -1
            if 0 <= i < len(ops):
                self.elige = i
                if p == "perm" and pm:
                    self._contestar(a, pm, ops[i])
                elif p == "preg" and q and not pm:
                    self._responder(a, q, ops[i])
            return None
        if p == "in" and resto.split(":", 1)[0] in ("seguir", "cerrar"):
            que, _s2, eid = resto.partition(":")
            self._accion_pendiente(a, eid, que)
            return None
        if p == "in" and resto.startswith("detener:"):
            e = vigente_de(self.fotos.get(aid), self.ahora())
            if e and e.get("id") == resto[len("detener:"):]:
                self._detener_skill(a, e)
            return None
        if zid == "in:boton":
            if self._trabaja(aid):
                self._parar(a)
            elif self.texto.strip():
                self._enter(a, pm, q, opciones_de(pm, q))
        return None

    def _clic_tab(self, resto):
        """H4-a: una pestaña del borde (tb:t:<slug>), su × (tb:x:<slug>), «+N ▾» (tb:mas), «+» (tb:nueva), una fila
        del menú «+» o «Deshacer»."""
        a = self.agente()
        if a is None:
            return None
        aid = a["id"]
        que, _s, sl = resto.partition(":")
        if que == "t":
            self.tabmenu = None
            self.elegir_tab(aid, sl)
        elif que == "x":
            self._cerrar_tab(aid, sl)
        elif que in ("nueva", "mas") and not sl:
            if self.tabmenu is not None:
                self.tabmenu = None
            else:
                self._abrir_tabs()
                if que == "mas" and self.tabmenu is not None:      # «+N ▾»: las que no caben, primero
                    vistas = {x["slug"] for x in self._tira_vista(aid)}
                    self.tabmenu["i"] = next((i for i, f in enumerate(self.tabmenu["filas"])
                                              if f.get("ya") and f.get("slug") in vistas), 0)
        elif que == "deshacer":
            self._deshacer_tab()
        elif que == "terminal":
            self._ir_terminal(aid)
        elif self.tabmenu is not None:
            filas = self.tabmenu["filas"]
            i = next((n for n, f in enumerate(filas) if rid_tab(f) == "tb:" + resto), None)
            if i is not None:
                self.tabmenu["i"] = i
                return self._accion_tab(filas[i])
        return None

    def _clic_panel(self, resto):
        """Un clic en el panel del agente (o en el cajón): lo mismo que su menú o su sección."""
        if resto == "caja":
            if self._menu_abierto():
                self._cerrar_menus()
            return None
        if resto == "cerrar":
            if self.cajon:
                self.cajon = False
            else:                                     # «« »: a su franja (se recuerda)
                self.panel_cerrado = True
                self._guardar_prefs()
            return None
        if resto == "motor":
            return self._accion_barra("motor")
        self.menu = self.ses = self.barra = None      # (sin olvidar el «otra vez» de una sesión abierta)
        self.cajon = False
        a = self.agente()
        if a is None:
            return None
        if resto in ("modelo", "conexion"):           # su config y su conexión viven en Motores y conexiones
            mid = (self.fotos.get(a["id"]) or {}).get("motor") or a.get("mid") or ""
            self._abrir_seccion("motores")
            self.seccion["sel"] = "mot:" + mid
            if resto == "modelo":
                self._avisar("El modelo lo elige %s en su propia config: ábrelo desde aquí (Abrir %s ↗)."
                             % (nombre_motor(mid), nombre_motor(mid)))
            return None
        if resto == "todas":                          # las de este agente (otra vez su monito: las de todos)
            self._abrir_seccion("sesiones")
            self._seccion_de(a["id"])
            return None
        if resto == "skills":
            self._abrir_seccion("skills")
            return None
        if resto == "nueva" or resto == "abrir":
            return self._plan_abrir()
        if resto.startswith("ses:"):
            wid = resto[4:]
            r = next((x for x in (self.ses_lista.get(a["id"]) or (0, []))[1] if str(x.get("wid")) == wid), None)
            return self._retomar(r, self.sel) if r else None
        if resto.startswith("usar:"):                 # «Usar»: la arranca en su conversación
            self._arrancar_skill(a, resto[5:])
            return None
        if resto.startswith("detener:"):              # skills-cierre: «Detener» de su proceso
            e = vigente_de(self.fotos.get(a["id"]), self.ahora())
            if e and e.get("id") == resto[len("detener:"):]:
                self._detener_skill(a, e)
            return None
        if resto.startswith("sk:"):                   # la fila: su ficha en Skills
            self._abrir_seccion("skills")
            self.seccion["sel"] = "skill:" + resto[3:]
        return None

    def _clic_franja(self, resto):
        """La franja (el panel cerrado): «abrir», su motor; lo demás abre el panel (en la pantalla media, encima de la
        conversación; con panel, lo vuelve a abrir)."""
        if resto == "caja":
            return None
        if resto == "abrir":
            self._cerrar_menus()
            return self._plan_abrir()
        self._cerrar_menus()
        if self.nivel in ("XL", "L"):
            self.panel_cerrado = False
            self._guardar_prefs()
        else:
            self.cajon = not self.cajon               # otra vez: se cierra
        return None

    def _clic_seccion(self, p, resto, zid):
        sec = self.seccion
        if sec["kind"] == "encamino":
            if zid == "acc:pagina":
                self._abrir_pagina()
            elif zid == "sec:volver":
                self._cerrar_seccion()
            return None
        if p == "sec":
            if resto == "volver":
                self._cerrar_seccion()
            elif resto == "lista":
                sec["abierto"] = False
            return None
        if p == "tab" and sec["kind"] == "agentes":
            sec["tab"] = resto
            self._pedir_r2("agentes")
            return None
        if p == "tono":
            return self._tono(resto)
        if sec["kind"] == "conexiones" and not sec.get("lab") and (p == "cvm" or (p == "sr" and
                                                                                 resto.startswith("cv:"))):
            import hub_conexiones as CX
            if p == "cvm":
                sec["sel"] = "cv:%s:" % resto
                CX.mover_v(self.instantanea(), sec)      # su primera fila con algo
            else:
                _m, f = CX.cursor_v(self.instantanea(), sec)
                if sec.get("sel") == resto and (f or {}).get("accion"):
                    return self._accion_seccion("fila")  # otro clic en la misma fila: su acción
                sec["sel"] = resto
            self.foco = "sr:" + str(sec.get("sel") or "")
            return None
        if sec["kind"] == "conexiones" and p in ("cxm", "cxs", "cxc", "sr"):
            import hub_conexiones as CX
            f, pieza = CX.cursor(self.instantanea(), sec)
            if p == "sr":
                sec["sel"] = resto
            elif p == "cxm":
                sec["sel"] = "cx:%s:%s" % (resto, pieza)
            elif p == "cxs" and f:
                sec["sel"] = "cx:%s:%s" % (f["motor"], resto)
            elif p == "cxc":
                CX.mover(self.instantanea(), sec, dx=3 if resto == "mas" else -3)
            return None
        if sec["kind"] == "agentes" and (p in ("celda", "trow", "tcol") or (p == "fil" and resto in ("lista",
                                                                                                    "tablero"))):
            if p == "fil":
                sec["vista"] = resto
                self._pedir_r2("agentes")
            elif p == "celda":
                aid, _s2, mid = resto.partition(":")
                if sec.get("sel") == "ag:" + aid and sec.get("mot") == mid:
                    return self._accion_seccion("tablero")      # otro clic en el mismo cruce: lo hace
                sec["sel"], sec["mot"] = "ag:" + aid, mid
            elif p == "trow":
                sec["mot"] = resto
            else:
                return self._tecla_tablero("derecha" if resto == "mas" else "izquierda")
            return None
        if p == "fil" and sec["kind"] == "calendario":
            import hub_secciones_r2 as R2
            if resto in ("mes", "semana"):
                sec["filtro"] = resto
            elif resto in ("ant", "sig"):
                d = 1 if resto == "sig" else -1
                if (sec.get("filtro") or "mes") == "semana":
                    R2.mover_dia(sec, 7 * d)
                else:
                    R2.mover_dia(sec, meses=d)
            elif resto == "hoy":
                import datetime as dt
                sec["sel"] = "dia:" + dt.date.today().isoformat()
            return None
        if p == "fil":
            if resto == "agente":
                sec["agente"] = None
            else:
                sec["filtro"] = resto
            return None
        if p == "sgr":                                # el encabezado de un agente: solo sus sesiones (otra vez: todas)
            sec["agente"] = None if sec.get("agente") == resto else resto
            return None
        if p == "sr":
            if sec.get("sel") != resto:
                sec["sel"], self.confirma = resto, None
                sec.update(op=None, usuario_i=0, editando=None)
                sec.pop("usuario_edicion", None)
                sec.pop("borrar", None)
            if not self.sec_lado:
                sec["abierto"] = True
            return None
        if p == "acc":
            if sec["kind"] == "ayuda":
                sec["sel"] = zid
            return self._accion_seccion(resto)
        if p == "op" and sec["kind"] == "ajustes":
            k, _s2, v = resto.partition(":")
            sec["sel"] = "aj:" + k
            self._aplicar_ajuste(self._fila_ajuste("aj:" + k), v)
            return None
        if p in ("cara", "color") and sec["kind"] == "agentes":
            _rids, cur = self._filas_seccion()
            if cur and "/api/front/apariencia" not in self.sin_ruta:
                self._apariencia(cur[3:], **({"forma": resto} if p == "cara" else {"color": resto}))
            return None
        return None


class Escucha(threading.Thread):
    """El long-poll de /api/v2/vivo, como la página: vuelve en cuanto algo cambia (o a los 25 s). Si la página se
    va (la apagaron, o nació otra con otra llave), se vuelve a buscar; si no aparece, se prende otra vez."""

    def __init__(self, app, conectar_=conectar):
        super().__init__(name="hub-escucha", daemon=True)
        self.app, self.conectar_ = app, conectar_
        self.alto = threading.Event()
        self.fallas = 0

    def parar(self):
        self.alto.set()
        self.app.despierta.set()

    def run(self):
        while not self.alto.is_set():
            self.vuelta()

    def _dormir(self, s):
        """Espera `s` s o hasta que algo lo despierte (una tecla, volver al frente, parar). → True si hay que parar."""
        self.app.despierta.clear()
        self.app.despierta.wait(s)
        return self.alto.is_set()

    def vuelta(self):
        app = self.app
        if app.hub_viejo:                             # este hub es de antes que la página: ya no escucha
            self.alto.wait(REPOSO_CADA_S)
            return
        reposo = app.en_reposo()
        q = {"v": app.v, "e": app.e, "espera": 0 if (self.fallas or reposo) else ESPERA_VIVO_S,
             "act": app.id_elegido()}
        cliente = getattr(app.srv, "cliente", "")
        if cliente:
            q["c"] = cliente
        try:
            d = app.srv.get("/api/v2/vivo", timeout=TOPE_VIVO_S, **q)
        except ErrorServidor as e:
            if getattr(e, "ocupado", False):          # la página atiende a muchos: lo que pide, sin buscar otra
                self._dormir(e.reintenta)
                return
            self.fallas += 1
            with app.lock:
                app.conectado = False
            if self.alto.wait(min(15.0, 0.5 * 2 ** self.fallas)):
                return
            if e.status in (None, 403):
                nuevo = self.conectar_(lanzar=self.fallas >= 3)
                if nuevo is not None:
                    if getattr(nuevo, "aviso", ""):
                        app.tras_renovar(nuevo, nuevo.aviso)
                    elif getattr(nuevo, "firma", None) != getattr(app.srv, "firma", None):
                        app.tras_renovar(nuevo, None)     # la renovó otro (el update, otro hub): sin línea
                    else:
                        app.srv = nuevo
                    if getattr(nuevo, "hub_viejo", False):
                        with app.lock:
                            app.hub_viejo = True
                        app._avisar(HUB_VIEJO)
            return
        self.fallas = 0
        for aid in app.aplicar_vivo(d):
            app.leer_conversacion(aid)
        self._quizas_renovar(d)
        if (app.seccion or {}).get("kind") == "sesiones":    # con la sección abierta, las de todos al día
            app._pedir_ses_todas()
        ses = app.ses
        if ses is not None:                           # con ^S abierta, su lista al día (cada SESIONES_S)
            hit = app.ses_lista.get(ses.get("agente"))
            if not hit or app.reloj() - hit[0] >= SESIONES_S:
                app.leer_sesiones(ses.get("agente"))
        try:
            app.refrescar_uso()
        except Exception:
            pass
        if reposo and not self.alto.is_set():
            self._dormir(REPOSO_CADA_S)               # nadie lo ve: la siguiente, sin esperar y en un rato

    def _quizas_renovar(self, d):
        """La página es de antes (o algo pidió una ruta que no trae): si no tiene nada a medio hacer, nace la de hoy
        (conectar → localhost_fondo.renovar), con su línea; si tiene, se vuelve a intentar en RENOVAR_CADA_S."""
        app = self.app
        if app.hub_viejo or not (getattr(app.srv, "vieja", False) or app.pide_renovar):
            return
        if app.reloj() - app.renovar_t < RENOVAR_CADA_S:
            return
        app.renovar_t = app.reloj()
        app.pide_renovar = False
        if ocupada_en(d, app.crudas):
            return
        try:
            nuevo = self.conectar_(lanzar=False)
        except Exception:
            return
        if nuevo is not None and getattr(nuevo, "aviso", ""):
            app.tras_renovar(nuevo, nuevo.aviso)


#: Si su motor se cierra con error antes de esto (s), el hub lo dice antes de volver (y no lo borra).
FALLO_RAPIDO_S = 20.0


def _con_aviso(lanzar, app):
    """`lanzar` con el aviso de H-1: si el programa oficial se cierra con error al abrir (antes de FALLO_RAPIDO_S),
    una tarjeta debajo de lo que dijo (qué pasó y qué sigue) y Enter para volver al hub. Antes, el hub se repintaba
    encima y parecía que «ni abre». Con la piel T-2, como siempre."""
    if piel() == "bloque":
        return lanzar

    def envuelto(p):
        if p.get("guia") and not _guia(app, p["guia"]):   # «Reparar»: la guía antes; Esc no entra
            p["cancelado"] = True
            return None
        t0 = time.monotonic()
        rc = lanzar(p)
        seg = time.monotonic() - t0
        if p.get("programa") or rc in (0, None) or seg >= FALLO_RAPIDO_S:
            return rc
        try:
            import hub_carga
            ag = app.d["agentes"]
            a = ag[p["agente"]] if 0 <= p.get("agente", -1) < len(ag) else {"n": "Tu agente", "c": C["tx2"],
                                                                           "f": "bolita", "id": ""}
            mid = p.get("motor") or a.get("mid") or ""
            hub_carga.fallo(a, mid, nombre_motor(mid), rc, seg)
            hub_carga.esperar_tecla()
        except Exception:
            pass
        return rc
    return envuelto


def _guia(app, g):
    """La tarjeta H-1 con los pasos (hub_carga), arriba de la terminal, y Enter para seguir: lo que dice queda a la
    vista mientras su programa oficial corre debajo."""
    try:
        import hub_carga
        C_ = P.C
        cols, rows = shutil.get_terminal_size((100, 30))
        aid = g.get("agente") or ""
        a = next((x for x in app.d["agentes"] if x["id"] == aid), None) or (app.d["agentes"] or [{}])[0]
        a = dict({"n": "Workspace", "c": C_["tx2"], "f": "bolita", "id": ""}, **a)
        lin = [[(x, C_["tx2"], False)] for x in g.get("lineas") or ()]
        T = hub_carga.tarjeta(cols, a, [(g.get("titulo") or "", C_["tx"], True)], lin,
                              pie=[("Enter", "sigue"), ("Esc", "no, de vuelta al hub")], alto_max=rows)
        hub_carga._pinta(T, sys.stdout)
        sigue = _enter_o_esc()
        sys.stdout.write("\r\n")
        sys.stdout.flush()
        return sigue
    except Exception:
        return True


def _enter_o_esc(tope=600.0):
    """Enter → True, Esc (o ^C, o el tope) → False. Sin eco. Sin terminal: True."""
    try:
        import select
        import termios
        import tty
        fd = sys.stdin.fileno()
        viejo = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        try:
            fin = time.monotonic() + tope
            while time.monotonic() < fin:
                r, _w, _x = select.select([fd], [], [], 0.5)
                if r:
                    b = os.read(fd, 64)
                    if b"\r" in b or b"\n" in b:
                        return True
                    if b.startswith(b"\x1b") or b"\x03" in b:
                        return False
            return False
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, viejo)
    except Exception:
        return True


def _gcal_eventos():
    """Los de Google Calendar (gcal.py, solo leer), si está encendido; si no, ninguno."""
    try:
        import gcal
        return list(gcal.events()) if gcal.enabled() else []
    except Exception:
        return []


def _anotar_falla(prefs_ruta):
    """La falla de un cuadro, junto a lo que recuerda el hub (hub/errores.log), para arreglarla."""
    import traceback
    try:
        ruta = os.path.join(os.path.dirname(prefs_ruta or _ruta_prefs()), "errores.log")
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "a", encoding="utf-8") as fh:
            fh.write("%s\n%s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), traceback.format_exc()))
    except OSError:
        pass


def _ruta_prefs():
    """Dónde se recuerda lo del hub de esta máquina (el riel con nombres, el panel cerrado): junto al estado de
    Workspace. H-1 tiene el suyo (su riel con nombres depende del ancho si no lo has tocado)."""
    nombre = "bloque.json" if piel() == "bloque" else "h1.json"
    import paths                                   # la carpeta de estado sale solo de paths.state_dir()
    return os.path.join(paths.state_dir(), "hub", nombre)


#: Que la terminal avise si está al frente («\x1b[I» / «\x1b[O», hub_paleta._SECUENCIAS). Solo Mac/Linux: en Windows
#: (msvcrt) llegarían como teclas sueltas.
FOCO_ON, FOCO_OFF = ("", "") if os.name == "nt" else ("\x1b[?1004h", "\x1b[?1004l")


def correr(lanzar=P._lanzar_de_verdad, teclado=None, conectar_=None, raton=None, prefs=None, abrir=None, agregar=None):
    """El hub con la conversación directa, en esta terminal, hasta que sales. → 0; None si no hay terminal. Si la
    página local no se puede prender (AG2-a), el MISMO hub sin la conversación (ServidorSinPagina): tus agentes se
    abren en su programa y sus sesiones se ven, y la escucha reintenta prenderla sola. Nunca la Paleta ni el lanzador
    de antes. `abrir`: dónde abre (`workspace agentes` → "agentes", `tono` → "agentes:tono", el primer arranque →
    "agregar:primera"…; ver Directo.abrir_al_empezar; `agregar=modo` es lo mismo que "agregar:<modo>", como lo
    pide hub_agregar.correr). `raton`: prender el mouse (por omisión,
    P.raton_posible()). Se apaga antes de entregarle la terminal a un motor y en toda salida (también con SIGTERM o
    SIGHUP)."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return None
    if agregar and not abrir:
        abrir = "agregar:" + str(agregar)
    if _puerta_dev("WORKSPACE_HUB_DIRECTO"):          # copia de desarrollo: la Paleta de antes, para comparar
        return __import__("puertas_dev").paleta(lanzar=lanzar, teclado=teclado)
    if os.name == "nt":
        os.system("")
    if conectar_ is None:
        def conectar_(lanzar=True):
            return conectar(lanzar=lanzar, firma_hub=FIRMA_AL_CARGAR)
    colores = P._colores()
    out = sys.stdout
    pin = P.Pintor(out)
    out.write("\x1b[?1049h\x1b[?25l")
    w, h = shutil.get_terminal_size((88, 30))
    pin.pintar(pantalla_espera(w, h, "Abriendo la conversación directa…"), colores)
    try:
        srv = conectar_()
        agentes = agentes_de(srv) if srv is not None else None
    except Exception:
        srv = agentes = None
    sin_pagina = srv is None or agentes is None
    if sin_pagina:                                   # AG2-a: el hub igual, sin la conversación (la escucha reintenta)
        try:
            srv = ServidorSinPagina()
            agentes = agentes_de(srv)
        except Exception:                            # ni el registro se lee: una línea y `workspace doctor`
            out.write("\x1b[0m\x1b[?25h\x1b[?1049l")
            out.flush()
            raise
    tec = teclado or P._Teclado()                    # Windows: pone la consola en el modo del hub
    try:
        app = Directo(srv, agentes)
        lanzar = _con_aviso(lanzar, app)
        app.cargar_prefs(prefs or _ruta_prefs())
        # Windows: además, que su consola haya aceptado el modo (si no, se lee como antes, sin mouse)
        app.raton_posible = (P.raton_posible() and getattr(tec, "raton_ok", True)) if raton is None else bool(raton)
        app.raton_on = app.raton_posible
        if not abrir:                                # si abre en otro lugar (la tarjeta «Agregar»…), sin la guía encima
            app.guia_primera_vez()                   # la primera vez, la guía sola (una vez)
        if not sin_pagina:
            app.revision_al_abrir()                  # Conexiones en verde (F4): sin IA, en el fondo
        if getattr(srv, "aviso", ""):                # la página se renovó tras una actualización
            app._avisar(srv.aviso)
        if app.hub_viejo:
            app._avisar(HUB_VIEJO)
        if sin_pagina:
            app.conectado = False
            app._avisar(_tp("puertas.hub.sin_pagina", SIN_PAGINA))
        try:                                         # las variables de antes ya no hacen nada: una línea
            import puertas
            v = puertas.variables_viejas()
            if v:
                app._avisar(v)
        except Exception:
            pass
        if aviso_idioma():                           # AG3-a: el hub todavía está solo en español (en tu idioma)
            app._avisar(aviso_idioma())
        pedido = app.abrir_al_empezar(abrir)         # `workspace agentes`, `tono`… y el primer arranque
        esc = Escucha(app, conectar_)
        esc.start()
        puesto = False                               # el mouse, como está en la terminal ahora
        viejas = _senales()
    except BaseException:                            # si no arranca, la consola como estaba (el lanzador de siempre
        tec.soltar()                                 # la lee con msvcrt)
        raise
    try:
        out.write("\x1b[?2004h" + FOCO_ON)            # lo que pegas llega de una vez (no como muchos Enter)
        pintar, t_pinta, s = True, 0.0, None
        while True:
            if app.raton_on != puesto:               # al empezar, y si lo apagas o prendes en la Ayuda
                out.write(P.RATON_ON if app.raton_on else P.RATON_OFF)
                out.flush()
                if hasattr(tec, "raton"):            # Windows: los clics de la consola y su edición rápida
                    tec.raton(app.raton_on)
                puesto = app.raton_on
            w, h = shutil.get_terminal_size((88, 30))
            ahora = time.monotonic()
            espera = (espera_cuadro(s) if s else None) or 0.5
            if pintar or s is None or ahora - t_pinta >= espera or (w, h) != (pin.tam or (w, h)):
                s = app.instantanea()
                try:
                    T = pantalla_directa(w, h, s)
                except Exception:                    # una falla al dibujar un menú o una sección: de vuelta a la
                    _anotar_falla(app.prefs_ruta)    # conversación (y anotada), sin tumbar el hub
                    with app.lock:
                        app._cerrar_menus()
                        app._cerrar_seccion()
                    app._avisar("Algo falló al dibujar eso: volví a la conversación (quedó anotado).")
                    s = app.instantanea()
                    T = pantalla_directa(w, h, s)
                app.vista(T)
                app.tope_scroll(T.scroll_max)
                pin.pintar(T, colores)
                t_pinta, espera = time.monotonic(), espera_cuadro(s) or 0.5
            if isinstance(pedido, dict):            # lo que pidió abrir al empezar (la tarjeta presta la terminal)
                r, pedido = pedido, None
            else:
                k = tec.leer(max(0.0, espera - (time.monotonic() - t_pinta)))
                pintar = True
                if k in ("foco+", "foco-"):          # la terminal dice si está al frente (reposo de Escucha)
                    app.poner_frente(k == "foco+")
                    pintar = False
                    continue
                if k:
                    app.actividad_ahora()
                if isinstance(k, P.Raton):
                    r = app.raton(k)
                    if r is SIN_CAMBIO:              # el mouse se movió sin cambiar nada: no se repinta
                        pintar = False
                        continue
                elif not k:
                    continue
                else:
                    r = app.tecla(k)
            if r == "salir":
                return 0
            if isinstance(r, dict):
                out.write(FOCO_OFF + "\x1b[?2004l")
                app.cedido = True                    # su terminal la tiene otro: Escucha descansa
                if r.get("programa"):                # «Agregar agente»: su formulario de siempre, y de vuelta aquí
                    P._ceder(tec, lambda: lanzar(r), pin, puesto)
                    app.en_fondo(app.releer_agentes)
                    if r.get("programa") in ("login", "motores", "actualizar"):
                        app._pedir_motores(forzar=True)
                    if r.get("verificar_despues") and not r.get("cancelado"):   # de vuelta de «Reparar»
                        app._verificar([r["verificar_despues"]])
                    if r.get("revisar_despues") and not r.get("cancelado"):     # Conexiones: el chequeo rápido
                        app._revisar_cx(r["revisar_despues"])
                else:
                    if r.get("s1_hub"):                  # S-1 en el hub: «Abriendo…» ya se ve aquí; su programa
                        T = pantalla_directa(w, h, app.instantanea())   # toma la terminal sobre esta misma imagen
                        pin.pintar(T, colores)
                        r["_espejo"] = T
                    if _entregar(app.d, r, tec, colores, lanzar, pin, raton=puesto):
                        with app.lock:
                            app.texto = ""
                    if r.get("s1_hub"):
                        with app.lock:
                            app._cerrar_s1()
                if r.get("verificar_despues") and not r.get("programa") and not r.get("cancelado"):
                    app._verificar([r["verificar_despues"]])
                if r.get("revisar_despues") and not r.get("programa") and not r.get("cancelado"):
                    app._revisar_cx(r["revisar_despues"])
                app.cedido = False
                app.actividad_ahora()
                out.write("\x1b[?2004h" + FOCO_ON)
    except KeyboardInterrupt:
        return 0
    finally:
        esc.parar()
        try:
            out.write(FOCO_OFF + (P.RATON_OFF if puesto else "") + "\x1b[?2004l\x1b[0m\x1b[?25h\x1b[?1049l")
            out.flush()
        except (OSError, ValueError):
            pass                                     # la terminal ya se cerró
        tec.soltar()
        _senales(viejas)


def _entregar(d, p, tec, colores, lanzar, pintor=None, raton=False):
    """La entrega al programa oficial con la piel H-1 (la parte H-1 de hub_paleta._entregar): S-1 en el hub y el picker
    S-1 toman la terminal sobre la misma imagen; si no, la tarjeta «Abriendo…» con su monito (hub_carga.entrega) y Esc
    para cancelar. (La entrega de la Paleta de antes vive en puertas_dev.) → True si se abrió."""
    if piel() == "bloque":
        return __import__("puertas_dev").entregar(d, p, tec, colores, lanzar, pintor, raton)
    pintor = pintor or P.Pintor()
    a = d["agentes"][p["agente"]]
    if p.get("motor"):
        a = dict(a, mid=p["motor"])
    if p.get("copiar") and not P.copiar(p["copiar"]):
        p["aviso"] = "%s no recibe un primer mensaje al abrir y no pude copiar tu texto: escríbelo ahí." % P.motor_de(a)
    if p.get("s1_hub"):                               # S-1 en el hub (H2-a): su «Abriendo…» ya se ve; sin tarjeta
        espejo = p.pop("_espejo", None)
        P._ceder(tec, lambda: lanzar(p), pintor, raton=raton, limpiar=False, espejo=espejo, colores=colores)
        return True
    if p.get("picker_s1"):
        P._ceder(tec, lambda: lanzar(p), pintor, raton=raton, aviso=p.get("aviso"), limpiar=False)
        return True
    import hub_carga
    t0, tope = time.monotonic(), (P.ENTREGA_AVISO_S if p.get("aviso") else P.ENTREGA_S)
    while time.monotonic() - t0 < tope:
        w, h = shutil.get_terminal_size((88, 30))
        pintor.pintar(hub_carga.entrega(w, h, a, P.motor_de(a), p.get("aviso") or "", time.monotonic() - t0), colores)
        if tec.leer(0.1) == "esc":
            return False
    P._ceder(tec, lambda: lanzar(p), pintor, raton, p.get("aviso"))
    return True


def foto_inicio(w=None, h=None, colores=None):
    """`workspace --banner` (I04): Inicio del hub nuevo, sin terminal ni página — lo que verías al abrirlo, con los
    agentes del registro (ServidorSinPagina). Nada en el fondo: lo que el hub pediría a la página se queda sin pedir.
    → las filas en ANSI."""
    if w is None or h is None:
        tw, th = shutil.get_terminal_size((100, 30))
        w, h = w or tw, h or th
    srv = ServidorSinPagina()
    app = Directo(srv, agentes_de(srv), en_fondo=lambda fn: None)
    T = pantalla_directa(max(40, int(w)), max(12, int(h)), app.instantanea())
    return T.ansi(colores or P._colores())


def _senales(viejas=None):
    """SIGTERM y SIGHUP salen por el `finally` de correr (que apaga el mouse y devuelve la terminal). Con `viejas`,
    deja las de antes. Solo en el hilo principal."""
    import signal
    if threading.current_thread() is not threading.main_thread():
        return {}
    if viejas is not None:
        for sig, h in viejas.items():
            try:
                signal.signal(sig, h)
            except (ValueError, OSError, TypeError):
                pass
        return {}

    def salir(_signum, _frame):
        raise SystemExit(0)
    out = {}
    for nombre in ("SIGTERM", "SIGHUP"):
        sig = getattr(signal, nombre, None)
        if sig is None:
            continue
        try:
            out[sig] = signal.signal(sig, salir)
        except (ValueError, OSError):
            pass
    return out


# ── sin pantalla: cómo queda, con datos de ejemplo ─────────────────────────────
def ejemplo(caso="conversacion"):
    """Una instantánea de ejemplo (no son datos reales): los agentes de la maqueta y una conversación."""
    ag = [dict(a) for a in P.EJEMPLO]
    for a, st in zip(ag, ("trabaja", "termino", "libre", "duerme", "pregunta")):
        a["st"] = st
    turnos = [
        {"rol": "yo", "texto": "¿Qué falta para cerrar la guía de instalación?", "motor": "claude-code"},
        {"rol": "agente", "motor": "claude-code", "herr": [{"n": "Read"}, {"n": "Read"}, {"n": "Grep"}],
         "texto": "Faltan dos cosas:\n\n1. Probar `install.sh` en una Mac limpia.\n2. Revisar la parte de "
                  "**Windows**: el paso del PATH quedó a medias."},
        {"rol": "yo", "texto": "Empieza por la de Windows.", "motor": "claude-code"},
    ]
    foto = {"estado": "trabajando", "trabajando": True, "motor": "claude-code",
            "parcial": "Voy con Windows. El paso del PATH pide reiniciar la terminal; lo dejo explícito y",
            "hace": {"n": "Edit", "d": json.dumps({"file_path": "docs/instalar-windows.md"}), "f": ""},
            "cola": [], "ejecuciones": []}
    foto["sesiones"] = {"n": 2, "trabajando": 0, "te_espera": 0}
    ahora = time.time()

    def utc(seg):
        return _dt.datetime.fromtimestamp(ahora - seg, _dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    s = {"agentes": ag, "sel": 0, "texto": "", "foto": foto, "turnos": turnos, "base": 0,
         "motores_conv": [{"i": 0, "motor": "claude-code"}],
         "sesiones_conv": [{"i": 2, "motor": "codex", "nombre": "Instalador en Mac",
                            "texto": "Listo: install.sh ya corre en una Mac limpia.", "ts": utc(600)}],
         "pend": None, "permiso": None, "pregunta": None, "menu": None, "sesiones": None,
         "scroll": 0, "elige": 0, "conectado": True, "aviso": "", "anim": {}, "t": 0.0,
         "ahora": ahora, "hora": "14:32", "uso": 41, "ejec": []}
    if caso == "permiso":
        foto.update(estado="esperandote", parcial="", hace=None)
        s["permiso"] = foto["permiso"] = {"id": "p1", "herramienta": "Bash",
                                          "detalle": json.dumps({"command": "npm test"}),
                                          "opciones": ["permitir", "permitir_siempre", "negar"]}
        ag[0]["st"] = "pregunta"
    elif caso == "pregunta":
        foto.update(estado="libre", trabajando=False, parcial="", hace=None)
        s["pregunta"] = foto["pregunta"] = {"id": "q1", "pregunta": "¿Publico la guía nueva en el sitio?",
                                            "tipo": "confirmar", "opciones": [], "en_terminal": False}
        ahora = _dt.datetime.now().isoformat(timespec="seconds")
        s["ejec"] = [{"id": "s-1", "skill": "publicar-guia", "estado": "corriendo", "creado": ahora,
                      "actualizado": ahora, "pasos": [{"texto": "Revisar la guía", "estado": "done"},
                                                      {"texto": "Preguntarte si se publica", "estado": "now"},
                                                      {"texto": "Publicarla", "estado": "pending"}]}]
        ag[0]["st"] = "pregunta"
    elif caso == "motor":
        foto.update(estado="libre", trabajando=False, parcial="", hace=None)
        s["menu"] = {"i": 1, "n": 3, "filas": [{"id": "claude-code", "nombre": "Claude Code", "ok": True},
                                               {"id": "codex", "nombre": "Codex", "ok": True},
                                               {"id": "kiro", "nombre": "Kiro", "ok": True},
                                               {"id": "cursor", "nombre": "Cursor", "ok": False,
                                                "sub": "sin sesión iniciada"}]}
        ag[0]["st"] = "libre"
    elif caso == "sesiones":
        s["sesiones"] = {"agente": "zenith", "i": 1, "filas": [
            {"tipo": "conv"},
            {"tipo": "sesion", "wid": "w-1", "nombre": "Revisión del instalador", "motor": "claude-code",
             "estado": "trabajando", "cuando": utc(180), "ultimo": None},
            {"tipo": "sesion", "wid": "w-2", "nombre": "Instalador en Mac", "motor": "codex", "estado": "cerrada",
             "cuando": utc(600), "ultimo": {"texto": "Listo: install.sh ya corre en una Mac limpia."}},
            {"tipo": "sesion", "wid": "w-3", "nombre": "Guía de Windows", "motor": "claude-code",
             "estado": "abierta", "cuando": utc(7200), "ultimo": {"texto": "Dejé el paso del PATH explícito."}},
            {"tipo": "nueva"}, {"tipo": "seccion"}]}
        foto["sesiones"] = {"n": 3, "trabajando": 1, "te_espera": 0}
    elif caso == "vacia":
        foto.update(estado="libre", trabajando=False, parcial="", hace=None)
        s["turnos"], s["motores_conv"], s["sesiones_conv"] = [], [], []
        foto["sesiones"] = None
        ag[0]["st"] = "libre"
    return s


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="hub_directo.py", description="El hub «Paleta» con la conversación directa.")
    ap.add_argument("--render", metavar="ANCHOxALTO", help="dibuja sin terminal (p. ej. 88x30) y sale")
    ap.add_argument("--caso", default="conversacion",
                    choices=("conversacion", "permiso", "pregunta", "motor", "sesiones", "vacia"))
    ap.add_argument("--256", dest="c256", action="store_true", help="256 colores")
    ap.add_argument("--texto", default="", help="lo escrito en la caja")
    ap.add_argument("--html", help="guarda la captura en HTML")
    a = ap.parse_args(argv)
    if not a.render:
        return correr() or 0
    w, h = (int(v) for v in a.render.lower().split("x"))
    s = ejemplo(a.caso)
    s["texto"] = a.texto
    T = pantalla_directa(w, h, s)
    col = "256" if a.c256 else "24"
    if a.html:
        with open(a.html, "w", encoding="utf-8") as fh:
            fh.write(T.html(col, "Paleta directa · %dx%d · %s" % (w, h, a.caso)))
    print("\n".join(T.ansi(col)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
