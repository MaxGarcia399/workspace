#!/usr/bin/env python3
"""WORKSPACE · escritorio/cliente — lo que el monito de escritorio y `ws` saben de Workspace.

Son un cliente más de la página local (/api/v2), igual que el hub: usan SU cliente (hub_directo.Servidor: la llave en
la cookie y el Origin en los POST) y sus palabras para los permisos (hub_directo.permiso_simple). Nada de backend
propio y nada de contestar por ti: un permiso del motor sale como tarjeta y solo se contesta con tu clic o tu tecla.

  · conectar(): la página viva de esta máquina. Si no hay, la prende el Workspace instalado ($WORKSPACE_ROOT), nunca
    esta copia: así una rama de prueba jamás reemplaza la página viva por otro código.
  · Puente: de la foto de /api/v2/vivo a los eventos del monito (estado, parcial, respuesta, pregunta, permiso, uso)
    y de lo que haces (mandar, responder, permiso, elegir, terminal) a /api/v2. Sin hilos ni red propios: quien lo usa
    (escritorio/puente.py, escritorio/ws.py) le pasa cada respuesta de /vivo y manda lo que él emite.

Modo escritorio (F0.5, D1-a): el monito y `ws` hablan en la conversación del ESCRITORIO de cada agente (`canal`
«escritorio» en /api/v2), aparte de la de la página y del hub. Lo que tenías enfrente al abrir la barra (`contexto`:
app, ventana, url, selección) viaja con tu mensaje y se quita con la ✕ del chip (D3-a). «Seguir en la página» lleva el
hilo a la página y la abre en ese agente; los archivos que enseña se abren por /api/front/abrir (nada de shell desde
la página del monito).
E1 (entregas en la burbuja): la tarjeta de cada entrega pide su ruta real a la página (/api/v2/entrega: solo dentro de
su cerebro; la app hace la miniatura, la Vista rápida, copiar y arrastrar con ella); los encargos (lo largo, en su
conversación de trabajo) salen de la foto de cada agente y se avisan aunque no sea el elegido (el monito te toca).
Stdlib."""
import json
import os
import secrets
import subprocess
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
import hub_directo as H  # noqa: E402
import paths  # noqa: E402
try:
    from escritorio import frases as F  # noqa: E402  (las palabras del monito: qué pide y qué hace, en simple)
except ImportError:                    # pragma: no cover (una copia sin él: las de la página)
    F = None

ErrorServidor = H.ErrorServidor
#: La foto de la página → el estado del monito.
ESTADO_DE = {"trabajando": "pensando", "esperandote": "pregunta", "termino": "listo", "error": "error",
             "dormido": "duerme", "libre": "reposo"}
TRABAJA = ("trabajando", "esperandote")
FORMAS = ("bolita", "pico", "cuadrito", "gatito", "fantasma", "nube")
#: Lo que se espera a que la página prendida conteste; el long-poll de /vivo.
ESPERA_LANZAR_S, ESPERA_VIVO_S, TOPE_VIVO_S = 20.0, 25, 35
#: Con un turno tuyo sin respuesta todavía, /vivo vuelve antes para revisar la conversación.
ESPERA_TURNO_S = 4
MAX_TEXTO = 4000
#: La conversación del monito (modo escritorio, D1-a).
CANAL = "escritorio"
#: Lo que viaja de lo que tenías enfrente (lo demás lo descarta la página igual).
CONTEXTO_CAMPOS = ("app", "bundle", "ventana", "url", "seleccion")
#: Un archivo que sueltas en el monito: lo mismo que acepta la página (/api/adjunto).
MAX_ADJUNTO = 20 * 1024 * 1024
#: E1 · los botones de la barra según lo que tienes enfrente (A9-a: 3 o 4, editables por la oficina en
#: <estado>/escritorio/botones.json, con esta misma forma). «accion»: monito (se lo pide al monito: lo libre basta),
#: entregable (el menú de plantillas → la tarjeta de encargo), pasar («Pásaselo a…») o panel (abre el panel grande).
BOTONES = {
    "texto": [{"t": "Resume", "accion": "monito", "pide": "Resume lo que seleccioné, en corto."},
              {"t": "Mejora", "accion": "monito", "pide": "Mejora la redacción de lo que seleccioné. Dame solo el texto."},
              {"t": "Tradúcelo", "accion": "monito", "pide": "Traduce lo que seleccioné (al inglés si está en español; si "
                                                             "no, al español). Dame solo el texto."},
              {"t": "Contesta", "accion": "monito", "pide": "Escribe una respuesta corta a esto que seleccioné. Dame solo "
                                                            "el texto."}],
    "archivo": [{"t": "Resume esto", "accion": "monito", "pide": "Resume este archivo en corto.", "con_archivo": True},
                {"t": "Hazme un entregable", "accion": "entregable"},
                {"t": "Revisa el archivo", "accion": "monito", "con_archivo": True,
                 "pide": "Revisa este archivo de verdad (no la pantalla): qué no cuadra, errores y riesgos, en corto."},
                {"t": "Pásaselo a…", "accion": "pasar"}],
    "pagina": [{"t": "Resume", "accion": "monito", "pide": "Resume lo que tengo enfrente, en corto."},
               {"t": "Guárdalo", "accion": "monito", "pide": "Guarda una nota con lo importante de lo que tengo enfrente."},
               {"t": "Hazme un entregable", "accion": "entregable"}],
    "nada": [{"t": "¿Qué tengo pendiente?", "accion": "monito", "pide": "¿Qué tengo pendiente? En corto."},
             {"t": "Mis entregas", "accion": "panel", "panel": "entregas"},
             {"t": "Mis encargos", "accion": "panel", "panel": "encargos"},
             {"t": "Hazme un entregable", "accion": "entregable"}],
}
ACCIONES_BOTON = ("monito", "entregable", "pasar", "panel")
#: Lo que la burbuja enseña de la conversación del monito en el panel grande (los últimos turnos).
HISTORIAL_MAX = 40


# ── dejar rastro (ronda 2 · E14) y la versión de la app (E7) ─────────────────────
#: app.log del monito llevaba vacío desde el 21-nov: si algo fallaba, no quedaba rastro. La app manda su stderr a
#: <estado>/escritorio/app.log (escritorio/mac/…/Bitacora.swift) y el puente, que lo hereda, anota ahí lo suyo.
#: Nunca lo que escribe el socio ni lo que contesta su agente: solo lo que falla.
MAX_LINEA = 2000
#: Lo que se le dice al socio si la app abierta no es la de estas fuentes (la de antes de actualizar Workspace).
APP_VIEJA = ("Workspace se actualizó, pero este Compañero es el de antes: algunas cosas nuevas no le van a salir. "
             "Ciérralo desde su carita en la barra de menú y vuelve a abrirlo.")
#: Cada cuánto se vuelve a comparar (no en cada mensaje).
REVISAR_VERSION_S = 120


def anotar(texto, flujo=None):
    """Una línea a app.log: «2026-11-22 14:05:01 puente · texto» (un renglón, acotado). Nunca levanta."""
    try:
        t = str(texto).replace("\r", " ").replace("\n", " ⏎ ")
        if len(t) > MAX_LINEA:
            t = t[:MAX_LINEA - 1] + "…"
        f = flujo if flujo is not None else sys.stderr
        f.write("%s puente · %s\n" % (time.strftime("%Y-%m-%d %H:%M:%S"), t))
        if hasattr(f, "flush"):
            f.flush()
    except Exception:
        pass


def _pid_vivo(pid):
    try:
        from control import hijos
        return bool(hijos.vivo(int(pid)))
    except Exception:
        return False                    # sin poder saberlo (en Windows nunca os.kill(pid, 0)): no se afirma nada


def aviso_del_renombre(estado=None):
    """El renombre de la app (migración 202611222200_renombre_companero) dejó dicho, en <estado>/escritorio/renombre.json,
    que hay que contárselo al socio UNA vez. → la línea (en su idioma), y queda marcado como dicho; None si no hay nada
    que decir (o ya se dijo). Nunca levanta: un aviso no rompe el puente."""
    try:
        from escritorio import abrir as A
        ruta = os.path.join(estado or A.carpeta(), "renombre.json")
        with open(ruta, encoding="utf-8") as fh:
            d = json.load(fh)
        if not isinstance(d, dict) or d.get("dicho") is not False:
            return None
        aviso = d.get("aviso")
        try:
            import i18n
            idioma = i18n.lang()
        except Exception:
            idioma = "es"
        texto = (aviso.get(idioma) or aviso.get("es")) if isinstance(aviso, dict) else aviso
        if not isinstance(texto, str) or not texto.strip():
            return None
        d["dicho"] = True
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, ruta)
        return texto.strip()[:300]
    except Exception:
        return None


def comparar_version(estado=None):
    """¿La app del monito que está ABIERTA salió de las fuentes de esta copia? → {"al_dia": True | False | None, "app",
    "fuentes"}. La app deja dicho de cuáles salió al arrancar (<estado>/escritorio/app.version.json: Bitacora.swift);
    aquí se comparan con las de ahora (la misma huella con que abrir.py decide si recompila). None = no se sabe (no hay
    app abierta, es de antes de esto, no es una Mac…): no se afirma nada. Nunca levanta."""
    out = {"al_dia": None, "app": "", "fuentes": ""}
    try:
        from escritorio import abrir as A
        with open(os.path.join(estado or A.carpeta(), "app.version.json"), encoding="utf-8") as fh:
            d = json.load(fh)
        huella = str(d.get("huella") or "")
        if not huella or not _pid_vivo(d.get("pid")):
            return out
        nombres = {A.BUNDLE_ID: A.NOMBRE_APP, A.BUNDLE_ID_PRUEBA: A.NOMBRE_APP_PRUEBA, A.BUNDLE_ID_DEV: A.NOMBRE_APP_DEV}
        bundle = str(d.get("bundle") or "")
        if bundle not in nombres:
            return out
        fuentes = A.huella_fuentes(A.PAQUETE, A.info_plist(bundle, nombres[bundle]))
        return {"al_dia": huella == fuentes, "app": huella, "fuentes": fuentes}
    except Exception:
        return out


# ── conectar ─────────────────────────────────────────────────────────────────
#: Lo que nunca hereda una página que prende el monito (o probar_rama): la identidad de la pestaña, de herdr o de la
#: sesión de Claude Code de quien la prende (lo mismo que borra envlimpio.sh). Se quedan la raíz y el «sin actualizar».
_ENTORNO_FUERA = ("WORKSPACE_", "ZENITH_", "HERDR_", "CLAUDE_CODE_")
_ENTORNO_QUEDA = ("WORKSPACE_ROOT", "WORKSPACE_NO_AUTOUPDATE")


def entorno_limpio(base=None):
    """El entorno para prender una página: sin la identidad de la terminal que lo pide (su panel de herdr, su pestaña,
    su sesión). Con ella, el motor que abre la página registraba ESE panel como su terminal."""
    try:
        from control import entorno as E
        es_id = E.es_identidad
    except Exception:
        es_id = lambda k: False  # noqa: E731
    out = {}
    for k, v in (os.environ if base is None else base).items():
        if k in _ENTORNO_QUEDA:
            out[k] = v
        elif k.startswith(_ENTORNO_FUERA) or k in ("CLAUDECODE", "CLAUDE_PID", "CLAUDE_EFFORT") or es_id(k):
            continue
        else:
            out[k] = v
    return out


def raiz_instalada():
    """El Workspace que prende la página si no hay una viva: SOLO el instalado (el del comando `workspace`,
    paths.installed_root). Nunca esta copia ni otra de desarrollo: prendida con tu estado de verdad se volvería LA
    página de la máquina con otro código (para probar una rama: escritorio/probar_rama.py). '' si no hay instalado."""
    r = paths.installed_root() or ""
    return r if r and os.path.isfile(os.path.join(r, "front.py")) else ""


#: Probar una rama (escritorio/probar_rama.py): el archivo con el puerto y la llave de la página de ESA copia. Con él, el
#: monito habla solo con ella (nunca con la de siempre, ni prende otra).
VAR_PAGINA = "WORKSPACE_ESCRITORIO_PAGINA"


def pagina_de_prueba(ruta=None):
    """La página de la rama que se está probando → Servidor, o None si no está viva."""
    ruta = ruta or os.environ.get(VAR_PAGINA) or ""
    try:
        with open(ruta, encoding="utf-8") as fh:
            d = json.load(fh)
        srv = H.Servidor(int(d["puerto"]), str(d["llave"]))
        srv.get("/api/v2/info", timeout=3)
        return srv
    except (OSError, ValueError, KeyError, TypeError, ErrorServidor):
        return None


def conectar(lanzar=True, tope=ESPERA_LANZAR_S, fondo=None, popen=subprocess.Popen, dormir=time.sleep,
             reloj=time.monotonic):
    """La página local viva (la de esta máquina, con su llave) → hub_directo.Servidor, o None.
    Con `lanzar` y sin página viva: la prende el Workspace instalado, sin abrir el navegador, y espera a que conteste.
    Probando una rama (WORKSPACE_ESCRITORIO_PAGINA): solo la página de esa rama."""
    if os.environ.get(VAR_PAGINA):
        return pagina_de_prueba()
    srv = H.conectar(lanzar=False, fondo=fondo)
    if srv is not None or not lanzar:
        return srv
    raiz = raiz_instalada()
    if not raiz:
        return None                       # sin Workspace instalado no se prende nada (y nunca desde una copia)
    kw = {"creationflags": 0x208} if os.name == "nt" else {"start_new_session": True}
    try:
        popen([sys.executable or "python3", os.path.join(raiz, "front.py"), "web", "--fondo", "--sin-navegador"],
              stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=raiz,
              env=dict(entorno_limpio(), WORKSPACE_ROOT=raiz), **kw)
    except OSError:
        return None
    fin = reloj() + tope
    while reloj() < fin:
        dormir(0.25)
        srv = H.conectar(lanzar=False, fondo=fondo)
        if srv is not None:
            return srv
    return None


def entregables():
    """T1-b · las carpetas de entregables (<cerebro>/deliverables) de los cerebros cargados en esta máquina, con su ruta
    de verdad (sin enlaces). El portero de la app las vuelve a revisar: ahí abrir un documento puede ir sin preguntar."""
    out = []
    try:
        import agentsreg
        for a in agentsreg.agents():
            d = os.path.join(os.path.realpath(os.path.expanduser(str(a.get("brain") or ""))), "deliverables")
            if os.path.isdir(d) and d not in out:
                out.append(d)
    except Exception:
        return []
    return out[:50]


def agentes(srv):
    """Los agentes con su monito, como los pinta la página (/api/front/inicio): id, nombre, color, forma y motor."""
    out = []
    for x in srv.get("/api/front/inicio").get("agentes") or []:
        aid = str(x.get("id") or "")
        if not aid:
            continue
        c = str(x.get("color") or "")
        f = str(x.get("forma") or "")
        a = {"id": aid, "n": H.limpio(x.get("nombre") or aid).strip() or aid,
             "c": c.lower() if len(c) == 7 and c.startswith("#") else "#ffffff",
             "f": f if f in FORMAS else "bolita", "motor": str(x.get("motor") or "")}
        if str(x.get("status") or "") in SIN_CARPETA_ST:
            a["sin_carpeta"] = True             # se sigue viendo, pero no se elige solo ni se le manda a ciegas
        out.append(a)
    return out


#: agent_state: la carpeta de su cerebro no está en esta computadora (se movió, se borró, no ha terminado de
#: sincronizar) o no se puede leer. Con ella así, su primer mensaje fallaba con «Esa pestaña ya no está».
SIN_CARPETA_ST = ("brain_missing", "brain_unreadable")
SIN_CARPETA = "No encuentro la carpeta de %s en esta computadora. Si se está sincronizando, espera a que termine."
SIN_AGENTES = "Todavía no tienes agentes. Agrega el primero en Workspace."


def elegir_sano(lista, elegido=""):
    """A quién se elige al abrir: el recordado si está y tiene su carpeta; si no, el primero que la tiene; si ninguno
    la tiene, el recordado o el primero (para que el aviso diga cuál falta); sin agentes, ''."""
    ids = [a["id"] for a in lista]
    sanos = [a["id"] for a in lista if not a.get("sin_carpeta")]
    if elegido in sanos:
        return elegido
    if sanos:
        return sanos[0]
    return elegido if elegido in ids else (ids[0] if ids else "")


def ruta_elegido():
    """Dónde se recuerda el último agente que elegiste (lo comparten la app y `ws`)."""
    return os.path.join(paths.state_dir(), "escritorio", "elegido.json")


def ruta_botones():
    """Los botones de la barra de esta oficina (si los cambió): <estado>/escritorio/botones.json."""
    return os.path.join(paths.state_dir(), "escritorio", "botones.json")


def escribir_botones(ruta=None):
    """botones.json con los de fábrica, si todavía no existe (nunca encima de los de la oficina). → su ruta o ''."""
    ruta = ruta or ruta_botones()
    if os.path.exists(ruta):
        return ruta
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "w", encoding="utf-8") as fh:
            json.dump(BOTONES, fh, ensure_ascii=False, indent=2)
        return ruta
    except OSError:
        return ""


def abrir_en_su_editor(ruta):
    """Un archivo de texto en el editor de texto del sistema (no lo corre: TextEdit, el Bloc de notas)."""
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-t", ruta], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        elif os.name == "nt":
            subprocess.Popen(["notepad.exe", ruta], creationflags=0x08000000)
        else:
            subprocess.Popen(["xdg-open", ruta], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL)
        return True
    except OSError:
        return False


def leer_botones(ruta=None):
    """Los botones de la barra: los de la oficina (botones.json) donde sean válidos; si no, los de fábrica. Cada
    contexto con 1 a 4 botones; cada botón con su texto y una acción conocida (lo demás se ignora)."""
    out = {k: [dict(b) for b in v] for k, v in BOTONES.items()}
    try:
        with open(ruta or ruta_botones(), encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return out
    if not isinstance(d, dict):
        return out
    for k in BOTONES:
        lista = d.get(k)
        if not isinstance(lista, list):
            continue
        buenos = []
        for b in lista[:4]:
            if not isinstance(b, dict) or b.get("accion") not in ACCIONES_BOTON:
                continue
            t = H.limpio(str(b.get("t") or "")).strip()[:40]
            if not t or (b["accion"] == "monito" and not str(b.get("pide") or "").strip()):
                continue
            x = {"t": t, "accion": b["accion"]}
            if b["accion"] == "monito":
                x["pide"] = H.limpio(str(b["pide"])).strip()[:400]
                if b.get("con_archivo"):
                    x["con_archivo"] = True
            if b["accion"] == "panel":
                x["panel"] = b.get("panel") if b.get("panel") in ("conversacion", "entregas", "encargos") else "entregas"
            buenos.append(x)
        if buenos:
            out[k] = buenos
    return out


def leer_elegido(ruta=None):
    try:
        with open(ruta or ruta_elegido(), encoding="utf-8") as fh:
            return str(json.load(fh).get("agente") or "")
    except (OSError, ValueError, AttributeError):
        return ""


def guardar_elegido(agente, ruta=None):
    ruta = ruta or ruta_elegido()
    try:
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        tmp = ruta + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"agente": agente}, fh)
        os.replace(tmp, ruta)
    except OSError:
        pass


def _nivel_de(op):
    """Fable v2: lo que el socio marcó en la tarjeta de un encargo (su nivel), solo como sí/no y solo si lo marcó."""
    return {k: True for k in ("comandos", "internet", "como_pagina") if op.get(k) is True}


def texto_limpio(s):
    """Lo que escribió su motor, sin escapes ni invisibles, CON sus saltos de línea (hub_directo.limpio es para un
    renglón: volvía espacio cada salto, y en la burbuja el 🧠 del final quedaba pegado al texto, a la vista)."""
    return "\n".join(H.limpio(ln).rstrip() for ln in str(s or "").replace("\r\n", "\n").split("\n"))


# ── lo que se dice en una línea ──────────────────────────────────────────────
def linea_uso(u, motor=""):
    """El uso del motor en una línea (lo mismo que la caja de la página: pintarUsoCaja). '' si no informa nada."""
    u = u or {}
    partes = []
    if u.get("contexto") is not None:
        partes.append("contexto %s %%" % u["contexto"])
    v = u.get("ventana")
    if isinstance(v, dict) and v.get("libre") is not None:
        m = v.get("minutos")
        dur = "ventana" if not m else ("%d min" % m if m % 60 else "%d h" % (m // 60))
        partes.insert(0, "%s: %s %% libre" % (dur, v["libre"]))
    if u.get("semana_usada") is not None:
        partes.append("semana %s %% usado" % u["semana_usada"])
    if u.get("gasto"):
        partes.append("gasto %s" % u["gasto"])
    if not partes:
        return ""
    return "Uso · " + " · ".join(partes)


#: Lo que el socio puede contestar en una tarjeta del monito. «Siempre» no va en el monito: ahí Workspace pregunta todo
#: lo que no es libre aunque el motor lo recuerde (D-79), así que prometía algo que no pasa. «permitir_turno»: esto y
#: lo del mismo tipo en esa carpeta, solo en este trabajo (lo cumple la capa de control; solo si el pedido se agrupa).
DECISIONES_MONITO = ("permitir", "permitir_turno", "negar")


def _palabras(pm, carpeta=""):
    """{texto, ya, detalle, grupo} de un permiso: las que ya trae la foto de la página (`frase`: escritorio/frases con
    la carpeta del agente y su tarea de ahora), o las de escritorio/frases aquí, o las de la página. Nunca levanta."""
    fr = pm.get("frase")
    if isinstance(fr, dict) and fr.get("texto"):
        return fr
    if F is not None:
        try:
            d = F.permiso(pm, carpeta=carpeta)
            if isinstance(d, dict) and d.get("texto"):
                return d
        except Exception:
            pass
    detalle = str(pm.get("detalle") or "")
    try:
        detalle = json.dumps(json.loads(detalle), ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        pass
    tecnico = "\n".join(x for x in (str(pm.get("herramienta") or ""), detalle) if x)
    return {"texto": H.permiso_simple(pm), "ya": H.permiso_simple(pm, ya=True), "detalle": tecnico, "grupo": None}


def evento_permiso(aid, pm, motor="", monito=False, carpeta=""):
    """La tarjeta de permiso de su motor en palabras de todos los días (qué quiere hacer, con qué y dónde): lo técnico
    solo en «Ver detalle». `monito`: la conversación del monito (sin «Siempre»; «esto y lo parecido en este trabajo»
    cuando el pedido se agrupa)."""
    if not pm:
        return {"t": "permiso", "agente": aid, "id": None}
    p = _palabras(pm, carpeta)
    ops = [o for o in (pm.get("opciones") or []) if o in H.PERMISO_T or o == "permitir_turno"]
    grupo = p.get("grupo") if isinstance(p.get("grupo"), dict) else None
    if monito:
        ops = [o for o in ops if o != "permitir_siempre"]
        if grupo and "permitir" in ops and "permitir_turno" not in ops:
            ops.insert(ops.index("permitir") + 1, "permitir_turno")
    ev = {"t": "permiso", "agente": aid, "id": pm.get("id") or None, "texto": str(p.get("texto") or "")[:400],
          "ya": str(p.get("ya") or "")[:400], "detalle": str(p.get("detalle") or "")[:1200],
          "corto": H.detalle_corto(pm.get("herramienta"), pm.get("detalle"), pm.get("archivo"))[:200],
          "opciones": ops, "en_terminal": bool(pm.get("en_terminal")), "motor": H.nombre_motor(motor) if motor else "",
          "leyo": bool(pm.get("leyo"))}
    if grupo and "permitir_turno" in ops:
        ev["grupo"] = {"texto": str(grupo.get("texto") or "")[:160], "nota": str(grupo.get("nota") or "")[:240]}
    return ev


def hace_simple(hace):
    """Lo que está haciendo su motor, en una línea de todos los días («Leyendo «README.md»»); '' si no dice nada útil."""
    if not hace:
        return ""
    if F is not None:
        try:
            t = F.hace(hace.get("n"), hace.get("d"), hace.get("f") or "")
            if isinstance(t, str):
                return t[:160]
        except Exception:
            pass
    return H.detalle_corto(hace.get("n"), hace.get("d"), hace.get("f"))[:160]


def evento_pregunta(aid, q):
    if not q:
        return {"t": "pregunta", "agente": aid, "id": None}
    return {"t": "pregunta", "agente": aid, "id": q.get("id") or None, "texto": str(q.get("pregunta") or ""),
            "opciones": [] if q.get("en_terminal") else H.opciones_pregunta(q), "en_terminal": bool(q.get("en_terminal"))}


#: E1 · lo que la burbuja le pide al puente de entregas y encargos (cada uno, Puente._op_<nombre>).
OPS_ENTREGAS = ("entrega", "encargar", "encargo", "encargo_permiso", "encargo_responder", "pasar", "historial",
                "entregas", "ver_pagina", "botones", "botones_editar")
#: E1 · «Hazme un entregable ▾» (los mismos de encargos.PLANTILLAS, en su orden).
PLANTILLAS = [{"id": "resumen", "t": "Resumen ejecutivo", "d": "Word · 1 página"},
              {"id": "presentacion", "t": "Presentación", "d": "PowerPoint · 5 láminas"},
              {"id": "tabla", "t": "Tabla limpia", "d": "Excel · con totales y formato"},
              {"id": "minuta", "t": "Minuta con pendientes", "d": "Word · quién, qué y cuándo"},
              {"id": "correo", "t": "Correo listo", "d": "texto para copiar"}]


def evento_encargo(aid, e, motor=""):
    """Un encargo de la foto → lo que pinta la burbuja: su estado, su avance, lo que entregó y, si te necesita, su
    pregunta o el permiso de su conversación de trabajo (con las palabras de la página)."""
    x = {k: e.get(k) for k in ("id", "titulo", "pedido", "plantilla", "estado", "base", "destino", "carpeta", "de",
                               "creado", "terminado", "visto", "resumen", "error") if e.get(k) not in (None, "")}
    x["visto"] = bool(e.get("visto"))
    if isinstance(e.get("pasos"), dict):
        x["pasos"] = e["pasos"]
    x["archivos"] = [{"ruta": str(a.get("ruta") or "")[:1000], "titulo": str(a.get("titulo") or "")[:120]}
                     for a in (e.get("archivos") or []) if isinstance(a, dict) and a.get("ruta")][:6]
    if isinstance(e.get("permiso"), dict):
        x["permiso"] = evento_permiso(aid, e["permiso"], motor)
        if e["permiso"].get("leyo"):
            x["permiso"]["leyo_archivo"] = texto_limpio(str(e["permiso"]["leyo"]))[:120]
    if isinstance(e.get("pregunta"), dict):
        x["pregunta"] = evento_pregunta(aid, e["pregunta"])
    return x


def estado_de(f):
    """La foto de un agente → el estado del monito y, si usa una herramienta, cuál (en una línea)."""
    if not f:
        return "duerme", ""
    e = f.get("estado")
    if f.get("permiso") or f.get("pregunta"):
        return "pregunta", ""
    hace = f.get("hace") if e == "trabajando" else None
    if hace:
        frase = f.get("hace_frase")
        return "haciendo", (frase[:160] if isinstance(frase, str) and frase else hace_simple(hace))
    return ESTADO_DE.get(e, "reposo"), ""


# ── el puente ────────────────────────────────────────────────────────────────
def contexto_limpio(c):
    """Lo que tenías enfrente, solo con sus campos de texto (None si no trae la app)."""
    if not isinstance(c, dict):
        return None
    out = {k: str(c[k])[:4000] for k in CONTEXTO_CAMPOS if isinstance(c.get(k), str) and c[k].strip()}
    return out if out.get("app") else None


def enlace_pagina(srv, agente=""):
    """El link de la página local con su llave (la pone en la cookie y entra) y, detrás de #, el agente que abre."""
    url = "http://127.0.0.1:%d/?k=%s" % (int(srv.puerto), srv.llave)
    return url + ("#a=" + agente if agente else "")


def abrir_en_el_navegador(url):
    import webbrowser
    try:
        return bool(webbrowser.open(url))
    except Exception:
        return False


class PaginaSinCanal(Exception):
    """La página viva no tiene la conversación del monito (otra versión de Workspace): hablarle mezclaría el monito con
    la conversación de la página. `texto`: lo que se le dice al socio."""

    def __init__(self, texto):
        super().__init__(texto)
        self.texto = texto


PAGINA_VIEJA = ("Tu Workspace es de una versión anterior a la mía, así que todavía no puedo platicar aquí sin mezclarme "
                "con la página. Actualiza Workspace y vuelvo solo.")


def entiende_canal(srv, canal=CANAL):
    """¿La página viva entiende la conversación `canal`? (lo dice /api/v2/info → canales). Una de antes no lo dice."""
    try:
        return canal in (srv.get("/api/v2/info").get("canales") or [])
    except (ErrorServidor, AttributeError, TypeError):
        return False


def hizo_de(x):
    """Ronda 2 (C3): lo que hizo en ese turno, para la línea gris de la burbuja («Leyó tu ventana · Señaló 1 lugar»): el
    nombre de cada herramienta y su detalle corto, tal como los guardó la página. [] si no usó ninguna."""
    out = []
    for h in (x.get("herr") or []) if isinstance(x, dict) and isinstance(x.get("herr"), list) else []:
        if isinstance(h, dict) and h.get("n"):
            out.append({"n": str(h["n"])[:80], "d": H.limpio(str(h.get("d") or ""))[:120]})
    return out[:60]


def nota_de(x):
    """Un aviso de la conversación (no un mensaje) que se dice en el hilo: que cambió su motor (así sabes que de ahí en
    adelante es otra sesión) o que la plática siguió en la página. '' si no es uno de esos."""
    if not isinstance(x, dict) or x.get("rol") != "sistema":
        return ""
    if x.get("tipo") == "motor":
        m = H.nombre_motor(str(x.get("motor") or "")) if x.get("motor") else "otro motor"
        return "Desde aquí te contesta con %s (le cambiaron el motor)." % m
    if x.get("tipo") == "a_la_pagina":
        return "Esta plática siguió en la página de Workspace."
    return ""


#: Lo que el monito dice cuando algo no salió, en simple (el error de la página va detrás, si ayuda).
NO_ABRIO = "No pude abrir ese archivo: ya no está en su carpeta, o se movió."
NO_SIGUIO = "No pude pasar la plática a la página. Inténtalo otra vez en un momento."
NO_SUBIO = "No pude subir «%s»: %s"


class Puente:
    """De la página al monito y del monito a la página. `emitir(evento)` recibe cada evento (un dict con "t").
    `recordar(agente)`: dónde se guarda el agente elegido (None: no se guarda). `canal`: la conversación (la del
    escritorio). `abrir_url(url)`: cómo se abre la página («Seguir en la página»)."""

    def __init__(self, srv, emitir, recordar=None, reloj=time.time, canal=CANAL, abrir_url=abrir_en_el_navegador,
                 abrir_archivo=abrir_en_su_editor):
        self.srv, self.emitir, self.recordar, self.reloj = srv, emitir, recordar, reloj
        self.canal, self.abrir_url, self.abrir_archivo = canal, abrir_url, abrir_archivo
        self.lista, self.elegido = [], ""
        self.v, self.e = "", ""
        self.fotos = {}
        self.turnos = {}             # agente → {"marca": índice del primer turno nuevo, "visto": ya trabajó, "t": hora}
        #: El candado de las manos: el id del turno que salió de la burbuja (la app solo mira con ese id abierto).
        self.turno_manos = None      # (agente, id) o None
        self.dicho = {}              # agente → lo último que se emitió de cada cosa (no se repite)
        #: Los permisos que ya contestaste (por agente): aunque la foto de la página todavía los traiga un momento, o
        #: vuelvas a elegir al agente, su tarjeta no vuelve a salir.
        self.decididos = {}          # agente → {id: decisión}
        #: E7: ya se le dijo que la app abierta es la de antes (una vez) y cuándo se comparó por última vez.
        self.version_dicha, self.revisado = False, 0.0

    # — arrancar y elegir —
    def arrancar(self, elegido=""):
        if self.canal and not entiende_canal(self.srv, self.canal):
            raise PaginaSinCanal(PAGINA_VIEJA)
        self.lista = agentes(self.srv)
        if self.canal == CANAL:
            self._niveles()
        self.elegido = elegir_sano(self.lista, elegido)
        self.emitir({"t": "agentes", "agentes": self.lista, "elegido": self.elegido, "entregables": entregables()})
        if self.canal == CANAL:
            self.emitir({"t": "botones", "botones": leer_botones(), "plantillas": PLANTILLAS})
            if self.elegido:
                self._op_historial(self.elegido, {})       # la plática de antes: la burbuja sabe en qué hilo estás
            self._revisar_version()
            # el renombre a «Workspace Compañero»: se dice UNA vez, en la burbuja (la migración lo dejó anotado)
            renombre = aviso_del_renombre()
            if renombre:
                anotar("renombre: se le dijo al socio")
                self.emitir({"t": "aviso", "texto": renombre})
        return self.elegido

    def _revisar_version(self):
        """E7: si la app abierta no salió de las fuentes de esta copia (Workspace se actualizó con el monito abierto),
        queda anotado y se le dice al socio, una vez. Se mira al arrancar y, a lo más cada REVISAR_VERSION_S, al mandar."""
        if self.version_dicha or (self.revisado and time.monotonic() - self.revisado < REVISAR_VERSION_S):
            return
        self.revisado = time.monotonic()
        v = comparar_version()
        if v["al_dia"] is False:
            self.version_dicha = True
            anotar("la app abierta (%s) no es la de estas fuentes (%s): hay que cerrarla y volver a abrirla"
                   % (v["app"][:16], v["fuentes"][:16]))
            self.emitir({"t": "aviso", "texto": APP_VIEJA})

    def _niveles(self):
        """E1: lo que su conversación de trabajo puede hacer sin preguntarte (el nivel de la página, Configuración →
        Permisos): la tarjeta de encargo lo dice con datos de Workspace, no del modelo."""
        try:
            per = {str(x.get("agente")): x for x in self.srv.get("/api/v2/info").get("permisos") or [] if isinstance(x, dict)}
        except (ErrorServidor, AttributeError, TypeError):
            return
        for a in self.lista:
            x = per.get(a["id"]) or {}
            if x.get("nivel"):
                a["nivel"] = str(x["nivel"])
            # Fable v2: quién lo lee y si Workspace acota sus encargos (la tarjeta lo dice con datos de Workspace)
            if x.get("motor_nombre"):
                a["motor_nombre"] = str(x["motor_nombre"])[:60]
            if "encargo_acotado" in x:
                a["encargo_acotado"] = bool(x["encargo_acotado"])

    def _motor(self, aid):
        f = self.fotos.get(aid) or {}
        return f.get("motor") or next((a["motor"] for a in self.lista if a["id"] == aid), "")

    def _decir(self, aid, clave, ev):
        """Emite `ev` solo si cambió desde la última vez (por agente y por clave)."""
        d = self.dicho.setdefault(aid, {})
        firma = json.dumps(ev, sort_keys=True, ensure_ascii=False)
        if d.get(clave) == firma:
            return
        d[clave] = firma
        self.emitir(ev)

    def _todo(self, aid):
        """Lo de un agente, de nuevo (al elegirlo): su estado, su pregunta, su permiso y su uso."""
        self.dicho.pop(aid, None)
        self._pintar(aid, self.fotos.get(aid))

    def _q(self, **q):
        """Los parámetros de una ruta v2, con el canal del monito."""
        if self.canal:
            q["canal"] = self.canal
        return q

    def _cuerpo(self, **c):
        if self.canal:
            c["canal"] = self.canal
        return c

    def vivo(self, espera=0, timeout=None):
        """Una vuelta del long-poll de /api/v2/vivo (la del canal del monito)."""
        return self.srv.get("/api/v2/vivo", timeout=timeout or TOPE_VIVO_S, **self._q(v=self.v, e=self.e, espera=espera))

    # — lo que llega de /vivo —
    def al_vivo(self, d):
        """Una respuesta de /api/v2/vivo. → cuánto esperar en la siguiente (s)."""
        self.v, self.e = d.get("v") or self.v, d.get("e") or self.e
        for aid, f in (d.get("agentes") or {}).items():
            self.fotos[aid] = f
            t = self.turnos.get(aid)
            if t and f and f.get("estado") in TRABAJA:
                t["visto"] = True
            if aid == self.elegido:
                self._pintar(aid, f)
            if self.canal == CANAL and isinstance(f, dict) and "encargos" in f:
                # E1: los encargos de TODOS (el monito te toca aunque no sea el agente elegido)
                self._decir(aid, "encargos", {"t": "encargos", "agente": aid,
                                              "lista": [evento_encargo(aid, e, self._motor(aid))
                                                        for e in f.get("encargos") or [] if isinstance(e, dict)]})
            if self.canal == CANAL and isinstance(f, dict) and "fichas" in f:
                # ronda 2 · P5-a: los permisos de su motor de TODOS, como fichas del monito (escritorio/fichas_motor.py)
                from escritorio import fichas_motor
                self._decir(aid, "fichas", fichas_motor.evento(
                    aid, f["fichas"], H.nombre_motor(self._motor(aid)) if self._motor(aid) else "",
                    self.decididos.get(aid),
                    lambda pm, aid=aid: evento_permiso(aid, pm, self._motor(aid), monito=True)))
        for aid in list(self.turnos):
            self._revisar_turno(aid)
        return ESPERA_TURNO_S if self.turnos else ESPERA_VIVO_S

    def _pintar(self, aid, f):
        st, hace = estado_de(f)
        ev = {"t": "estado", "agente": aid, "estado": st}
        if hace:
            ev["hace"] = hace
        self._decir(aid, "estado", ev)
        f = f or {}
        if f.get("parcial") and f.get("estado") == "trabajando":
            self._decir(aid, "parcial", {"t": "parcial", "agente": aid, "texto": texto_limpio(f["parcial"])[-MAX_TEXTO:]})
        self._decir(aid, "pregunta", evento_pregunta(aid, f.get("pregunta")))
        if self.canal == CANAL:
            # su motor no puede mirar tu pantalla desde el monito (todavía): una línea en la barra, y no viaja nada de ella
            sm = str(f.get("sin_manos") or "")
            self._decir(aid, "manos", {"t": "manos", "agente": aid, "sin": bool(sm), "texto": sm[:300]})
        pm = f.get("permiso")
        if isinstance(pm, dict) and pm.get("id") and pm["id"] in self.decididos.get(aid, {}):
            pm = None                       # ya lo contestaste: la foto tarda en enterarse, la tarjeta no vuelve
        self._decir(aid, "permiso", evento_permiso(aid, pm, self._motor(aid), monito=self.canal == CANAL))
        lic = f.get("licencia") if isinstance(f.get("licencia"), dict) else None
        if self.canal == CANAL and (lic or "licencia" in self.dicho.get(aid, {})):
            self._decir(aid, "licencia", {"t": "licencia", "agente": aid, "texto": str((lic or {}).get("texto") or "")[:200],
                                          "usadas": int((lic or {}).get("usadas") or 0),
                                          "ultima": str((lic or {}).get("ultima") or "")[:200]})
        linea = linea_uso(f.get("uso"), self._motor(aid))
        if linea:
            self._decir(aid, "uso", {"t": "uso", "agente": aid, "linea": linea})
        err = f.get("error")
        if f.get("estado") == "error" and isinstance(err, dict) and err.get("texto"):
            self._decir(aid, "error", {"t": "aviso", "agente": aid, "grave": True,
                                       "texto": "Algo se atoró de su lado: %s" % H.limpio(err["texto"])[:400]})

    def _revisar_turno(self, aid):
        """¿Ya terminó el turno que mandaste? Con su respuesta en la conversación: se emite y se olvida."""
        t = self.turnos.get(aid)
        f = self.fotos.get(aid) or {}
        if not t or f.get("estado") in TRABAJA or f.get("abriendo"):
            return
        if not t["visto"] and self.reloj() - t["t"] < 3 and not f.get("estado") in ("termino", "error"):
            return                                   # todavía no lo toma su motor
        try:
            c = self.srv.get("/api/v2/conversacion", **self._q(agente=aid))
        except ErrorServidor:
            return
        desde = int(c.get("desde") or (int(c.get("total") or 0) - len(c.get("turnos") or [])))
        nuevos = (c.get("turnos") or [])[max(0, t["marca"] - desde):]
        suyos = [x for x in nuevos if x.get("rol") == "agente"]
        texto = "\n\n".join(texto_limpio(x.get("texto") or "").strip() for x in suyos if (x.get("texto") or "").strip())
        # los archivos que enseñó (mostrar_archivo, o un enlace a uno de su cerebro): tarjetas en la burbuja
        archivos, vistos = [], set()
        for x in suyos:
            for a in x.get("archivos") or []:
                if isinstance(a, dict) and a.get("ruta") and a["ruta"] not in vistos and len(archivos) < 6:
                    vistos.add(a["ruta"])
                    archivos.append({"ruta": str(a["ruta"])[:1000], "titulo": str(a.get("titulo") or "")[:120]})
        if not texto and not archivos:
            if f.get("estado") == "error" or (t["visto"] and self.reloj() - t["t"] > 600):
                self.turnos.pop(aid, None)            # falló o se perdió: lo dice su estado (y el ▮ se apaga)
                self._cerrar_manos(aid)
                self.emitir({"t": "fin", "agente": aid})
            return
        self.turnos.pop(aid, None)
        self._cerrar_manos(aid)
        self.dicho.setdefault(aid, {}).pop("parcial", None)
        ev = {"t": "respuesta", "agente": aid, "texto": texto[-MAX_TEXTO * 3:]}
        if archivos:
            ev["archivos"] = archivos
        hizo = [h for x in suyos for h in hizo_de(x)][:60]      # ronda 2 (C3): lo que hizo, aparte de lo que dijo
        if hizo:
            ev["herr"] = hizo
        self.emitir(ev)
        self._uso(aid)

    def _uso(self, aid):
        try:
            u = self.srv.get("/api/v2/uso", **self._q(agente=aid)).get("uso") or {}
        except ErrorServidor:
            return
        linea = linea_uso(u, self._motor(aid))
        if linea:
            self._decir(aid, "uso", {"t": "uso", "agente": aid, "linea": linea})

    def _sin_carpeta(self, aid):
        """El aviso si a `aid` no se le puede escribir (no hay agentes, o su carpeta no está aquí), o ''. Antes de
        negarse vuelve a mirar: la carpeta pudo terminar de llegar (un sync) desde que se abrió."""
        if not aid:
            return "" if self.lista else SIN_AGENTES
        a = next((x for x in self.lista if x["id"] == aid), None)
        if a is None or not a.get("sin_carpeta"):
            return ""
        try:
            self.lista = agentes(self.srv)
        except (ErrorServidor, AttributeError, TypeError):
            return SIN_CARPETA % a["n"]
        a2 = next((x for x in self.lista if x["id"] == aid), None)
        return SIN_CARPETA % a["n"] if a2 is not None and a2.get("sin_carpeta") else ""

    def _marca(self, aid):
        try:
            c = self.srv.get("/api/v2/conversacion", **self._q(agente=aid))
            return int(c.get("total") or 0)
        except (ErrorServidor, TypeError, ValueError):
            return 0

    # — lo que haces —
    def comando(self, op):
        """Lo que mandó el monito (o `ws`). → True si salió."""
        k = op.get("op")
        aid = str(op.get("agente") or self.elegido)
        try:
            if k == "elegir":
                if aid in [a["id"] for a in self.lista]:
                    self.elegido = aid
                    if self.recordar:
                        self.recordar(aid)
                    self._todo(aid)
                    self._uso(aid)
                    if self.canal == CANAL:
                        self._op_historial(aid, {})
                return True
            if k in ("mandar", "responder"):
                texto = str(op.get("texto") or "").strip()[:MAX_TEXTO]
                if not texto:
                    return False
                falta = self._sin_carpeta(aid)
                if falta:
                    self.emitir({"t": "aviso", "agente": aid, "grave": True, "texto": falta})
                    return False
                marca = self._marca(aid)
                previo = self.turnos.get(aid)
                if previo and (self.fotos.get(aid) or {}).get("estado") in TRABAJA:
                    marca = previo["marca"]     # trabaja en lo de antes: lo tuyo va en fila y su respuesta trae las dos
                if k == "mandar":
                    cuerpo = self._cuerpo(agente=aid, texto=texto, cid="e" + secrets.token_hex(6))
                    # D3-a: lo que tenía enfrente, salvo que lo quitaste con la ✕ del chip
                    ctx = None if op.get("sin_contexto") else contexto_limpio(op.get("contexto"))
                    if ctx and self.canal:
                        cuerpo["contexto"] = ctx
                    self.srv.post("/api/v2/mandar", cuerpo)
                else:
                    self.srv.post("/api/v2/responder", self._cuerpo(agente=aid, id=str(op.get("id") or ""),
                                                                    texto=texto))
                self.turnos[aid] = {"marca": marca, "visto": False, "t": self.reloj()}
                self.dicho.setdefault(aid, {}).pop("parcial", None)
                self._abrir_manos(aid)
                if self.canal == CANAL:
                    self._revisar_version()
                return True
            if k == "permiso":
                d = str(op.get("decision") or "")
                pid = str(op.get("id") or "")
                if d not in H.PERMISO_T and d not in DECISIONES_MONITO:
                    return False
                ya = self.decididos.setdefault(aid, {})
                if pid and pid in ya:
                    return True                     # el mismo pedido, ya contestado: una vez basta
                self.srv.post("/api/v2/permiso", self._cuerpo(agente=aid, id=pid, decision=d))
                if pid:
                    ya[pid] = d
                    if len(ya) > 200:
                        for viejo in list(ya)[:100]:
                            ya.pop(viejo, None)
                self._decir(aid, "permiso", {"t": "permiso", "agente": aid, "id": None})
                return True
            if k == "permiso_despues":          # ronda 2 · P2-b: una ficha que quedó para después
                from escritorio import fichas_motor
                return fichas_motor.op_despues(self, aid, op)
            if k == "contexto":
                # lo que tenía enfrente al abrir la barra (la app del monito): su chip en la barra, que se quita con ✕
                self.emitir({"t": "contexto", "contexto": contexto_limpio(op.get("contexto"))})
                return True
            if k == "abrir":
                return self._abrir(aid, op)
            if k == "seguir":
                return self._seguir(aid)
            if k == "adjuntar":
                return self._adjuntar(aid, op)
            if k in OPS_ENTREGAS:
                return getattr(self, "_op_" + k)(aid, op)
            if k == "terminal":
                self.srv.post("/api/v2/terminal", {"agente": aid})
                return True
            if k == "parar":
                self.srv.post("/api/v2/parar", self._cuerpo(agente=aid))
                self._cerrar_manos(aid)
                return True
        except ErrorServidor as e:
            anotar("no salió «%s» (%s): %s" % (k, aid, e.texto))      # E14: que quede rastro (nunca lo que escribiste)
            self.emitir({"t": "aviso", "agente": aid, "grave": True, "texto": e.texto})
            return False
        return False

    # — el candado de las manos: un id por turno que salió de la burbuja —
    def _abrir_manos(self, aid):
        """Un turno del escritorio empieza (mandaste o contestaste desde el monito): la app abre el candado de sus manos
        con este id y solo atiende ver/leer/señalar mientras siga abierto. Solo en la conversación del escritorio."""
        if self.canal != CANAL:
            return
        if self.turno_manos:
            self.emitir({"t": "turno", "abierto": False, "id": self.turno_manos[1]})
        self.turno_manos = (aid, secrets.token_hex(16))
        self.emitir({"t": "turno", "abierto": True, "id": self.turno_manos[1], "agente": aid})

    def _cerrar_manos(self, aid):
        if self.turno_manos and self.turno_manos[0] == aid:
            self.emitir({"t": "turno", "abierto": False, "id": self.turno_manos[1]})
            self.turno_manos = None

    # — los botones de la burbuja —
    def _abrir(self, aid, op):
        """«Abrir» / «Mostrar en Finder» de la tarjeta de un archivo: por la página (/api/front/abrir, que solo abre lo
        que vive dentro de su cerebro). Nada de shell desde la página del monito."""
        ruta, modo = str(op.get("ruta") or "")[:1000], "revelar" if op.get("modo") == "revelar" else "abrir"
        if not ruta:
            return False
        que = "revelado" if modo == "revelar" else "abierto"
        if os.environ.get("WORKSPACE_MONITO_SISTEMA") == "ensayo":       # pruebas de punta a punta: no abre nada
            self.emitir({"t": "hecho", "agente": aid, "que": que, "ok": True, "ruta": ruta, "ensayo": True})
            return True
        try:
            r = self.srv.post("/api/front/abrir", {"agente": aid, "ruta": ruta, "modo": modo})
        except ErrorServidor:
            self.emitir({"t": "hecho", "agente": aid, "que": "no_abierto", "ok": False, "ruta": ruta, "texto": NO_ABRIO})
            return False
        ev = {"t": "hecho", "agente": aid, "que": "revelado" if (r or {}).get("revelado") else que, "ok": True, "ruta": ruta}
        if (r or {}).get("revelado") and modo != "revelar":
            ev["ejecutable"] = True
        self.emitir(ev)
        return True

    def _seguir(self, aid):
        """«Seguir en la página»: el hilo de aquí pasa a la conversación de la página (pagina_v2.seguir_en_la_pagina) y
        la página se abre en ese agente."""
        try:
            r = self.srv.post("/api/v2/seguir", {"agente": aid})
        except ErrorServidor:
            self.emitir({"t": "aviso", "agente": aid, "texto": NO_SIGUIO})
            return False
        abierta = bool(self.abrir_url and self.abrir_url(enlace_pagina(self.srv, aid)))
        self.emitir({"t": "seguido", "agente": aid, "turnos": int(r.get("turnos") or 0), "abierta": abierta})
        return True

    # — E1: entregas y encargos —
    def _op_entrega(self, aid, op):
        """La tarjeta de una entrega pide su ruta real (la página la valida: solo dentro de su cerebro). La app la
        intercepta (miniatura, Vista rápida, copiar, arrastrar) y la burbuja recibe lo demás."""
        ruta = str(op.get("ruta") or "")[:1000]
        if not ruta:
            return False
        try:
            r = self.srv.post("/api/v2/entrega", {"agente": aid, "ruta": ruta})
        except ErrorServidor:
            self.emitir({"t": "entrega", "agente": aid, "ruta": ruta, "mal": True})
            return False
        # «ruta»: la que pidió la tarjeta (así la encuentra); «actual»: la de la página (relativa a su cerebro)
        ev = {"t": "entrega", "agente": aid, "ruta": ruta, "actual": str(r.get("ruta") or ruta)}
        for k in ("abs", "nombre", "ext", "tam", "version", "versiones", "carpeta", "ejecutable"):
            if k in r:
                ev[k] = r[k]
        self.emitir(ev)
        return True

    def _op_encargar(self, aid, op):
        """El encargo que armó la app (lo que pediste, el archivo de verdad, la plantilla) tras tu clic, o un «Pedir
        cambios» de una tarjeta (`base`). `ref`: con qué tarjeta va (la burbuja la cambia a su avance)."""
        cuerpo = {"agente": aid, "pedido": str(op.get("pedido") or "")[:MAX_TEXTO]}
        for k in ("titulo", "plantilla", "archivo", "base", "archivo_nombre", "archivo_datos"):
            v = op.get(k)
            if isinstance(v, str) and v:
                cuerpo[k] = v
        cuerpo.update(_nivel_de(op))
        ref = str(op.get("ref") or "")[:64]
        if not cuerpo["pedido"].strip():
            return False
        try:
            r = self.srv.post("/api/v2/encargar", cuerpo)
        except ErrorServidor as e:
            self.emitir({"t": "encargo", "agente": aid, "ref": ref, "ok": False, "texto": e.texto})
            return False
        self.emitir({"t": "encargo", "agente": aid, "ref": ref, "ok": True, "id": str(r.get("id") or ""),
                     "en_cola": bool(r.get("en_cola")), "carpeta": str(r.get("carpeta") or ""),
                     "destino": str(r.get("destino") or "")})
        return True

    def _op_encargo(self, aid, op):
        """visto · parar · reintentar."""
        acc = op.get("accion")
        if acc not in ("visto", "parar", "reintentar"):
            return False
        try:
            self.srv.post("/api/v2/encargo", {"agente": aid, "id": str(op.get("id") or ""), "accion": acc})
        except ErrorServidor as e:
            self.emitir({"t": "aviso", "agente": aid, "texto": e.texto})
            return False
        return True

    def _op_encargo_permiso(self, aid, op):
        """El permiso que pide su conversación de TRABAJO mientras hace un encargo (su nivel de la página): solo con tu
        clic, igual que en la página."""
        d = str(op.get("decision") or "")
        if d not in H.PERMISO_T:
            return False
        self.srv.post("/api/v2/permiso", {"agente": aid, "id": str(op.get("id") or ""), "decision": d})
        return True

    def _op_encargo_responder(self, aid, op):
        texto = str(op.get("texto") or "").strip()[:MAX_TEXTO]
        if not texto:
            return False
        self.srv.post("/api/v2/responder", {"agente": aid, "id": str(op.get("id") or ""), "texto": texto})
        return True

    def _op_pasar(self, aid, op):
        """«Pásaselo a…»: la entrega (o el archivo de verdad, de la app) a otro agente, como encargo suyo."""
        a = str(op.get("a") or "")
        cuerpo = {"de": aid, "a": a}
        for k in ("ruta", "nota", "archivo_nombre", "archivo_datos"):
            v = op.get(k)
            if isinstance(v, str) and v:
                cuerpo[k] = v
        cuerpo.update(_nivel_de(op))
        ref = str(op.get("ref") or "")[:64]
        try:
            r = self.srv.post("/api/v2/pasar", cuerpo)
        except ErrorServidor as e:
            self.emitir({"t": "pasado", "agente": aid, "a": a, "ref": ref, "ok": False, "texto": e.texto})
            return False
        self.emitir({"t": "pasado", "agente": aid, "a": a, "ref": ref, "ok": True, "id": str(r.get("id") or "")})
        return True

    def _op_historial(self, aid, op):
        """La conversación del monito con este agente (el panel grande, «Conversación»): sus últimos turnos, limpios."""
        try:
            c = self.srv.get("/api/v2/conversacion", **self._q(agente=aid))
        except ErrorServidor:
            return False
        turnos = []
        for x in (c.get("turnos") or [])[-HISTORIAL_MAX:]:
            nota = nota_de(x)
            if nota:
                turnos.append({"rol": "nota", "texto": nota})
                continue
            if x.get("rol") not in ("yo", "agente"):
                continue
            t = {"rol": x["rol"], "texto": texto_limpio(x.get("texto") or "")[-MAX_TEXTO:]}
            arch = [{"ruta": str(a["ruta"])[:1000], "titulo": str(a.get("titulo") or "")[:120]}
                    for a in (x.get("archivos") or []) if isinstance(a, dict) and a.get("ruta")][:6]
            if arch:
                t["archivos"] = arch
            # ronda 2 (C3): su hora (se ve al pasar el ratón; separa los días) y lo que hizo (una línea gris)
            try:
                if float(x.get("t") or 0) > 0:
                    t["t"] = round(float(x["t"]), 1)
            except (TypeError, ValueError):
                pass
            hizo = hizo_de(x) if x["rol"] == "agente" else []
            if hizo:
                t["herr"] = hizo
            turnos.append(t)
        self.emitir({"t": "historial", "agente": aid, "turnos": turnos})
        return True

    def _op_entregas(self, aid, op):
        try:
            r = self.srv.get("/api/v2/entregas", agente=aid)
        except ErrorServidor:
            return False
        self.emitir({"t": "entregas", "agente": aid, "lista": [x for x in (r.get("entregas") or [])
                                                               if isinstance(x, dict)][:30]})
        return True

    def _op_ver_pagina(self, aid, op):
        """«Ver en la página» de un encargo: la página en ese agente (su conversación de trabajo), sin mover nada."""
        return bool(self.abrir_url and self.abrir_url(enlace_pagina(self.srv, aid)))

    def _op_botones(self, aid, op):
        self.emitir({"t": "botones", "botones": leer_botones(), "plantillas": PLANTILLAS})
        return True

    def _op_botones_editar(self, aid, op):
        """«Editar los botones de la barra» (panel grande): el archivo de la oficina, con los de fábrica si no existía,
        abierto en su editor de texto. Se lee de nuevo cada vez que abres la barra."""
        ruta = escribir_botones()
        return bool(ruta and self.abrir_archivo(ruta))

    def _adjuntar(self, aid, op):
        """Un archivo que soltaste en el monito: a su cerebro (/api/adjunto, como el clip de la página); su ruta viaja
        con tu siguiente mensaje."""
        nombre, datos = str(op.get("nombre") or "archivo")[:120], str(op.get("datos") or "")
        if not datos or len(datos) > MAX_ADJUNTO * 4 // 3 + 8:
            self.emitir({"t": "adjunto", "agente": aid, "nombre": nombre, "mal": "pasa de 20 MB"})
            return False
        try:
            r = self.srv.post("/api/adjunto", {"agente": aid, "nombre": nombre, "datos": datos})
        except ErrorServidor as e:
            self.emitir({"t": "adjunto", "agente": aid, "nombre": nombre, "mal": e.texto})
            return False
        self.emitir({"t": "adjunto", "agente": aid, "nombre": nombre, "ruta": str(r.get("ruta") or "")})
        return True
