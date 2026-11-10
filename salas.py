#!/usr/bin/env python3
"""WORKSPACE · salas — conversaciones de varios agentes, cada uno en su pestaña.

Diseño: deliverables/workspace-colaboracion-bus/Diseno_Conversaciones_v4.md.

UNA sala = UNA carpeta con UN hogar: el cerebro de quien la abre,
`<cerebro>/conversaciones/<id>/`. Los demás participantes leen y escriben ahí
(el cerebro viaja por Obsidian Sync a sus máquinas). Nada se copia: con un
solo hogar no hay versiones de la sala que se contradigan.

Archivos (todos .md, ASCII en el nombre, ninguno se edita jamás):

    sala.md                              cómo nació: título, objetivo, hecho
                                         cuando, dueño (el socio), espera por
                                         defecto, tope de turnos, quién abrió
                                         (su sobre) e invitados
    m-<aammddThhmmss>-<azar>.md          un mensaje: pide | responde | info
    e-<aammddThhmmss>-<azar>-<accion>.md un evento: unirse, invitar, pausa,
                                         reanudar, cierre, archivar, espera,
                                         espera_pedido, mas_tiempo, cancelar,
                                         soltar, delegar, tope, lapida

El estado de la sala (en pausa, cerrada, la espera, quién debe qué) NO se
guarda: se DERIVA de esos archivos, igual en todas las máquinas. Archivar es
un evento (no se mueve nada). Borrar = lápida + purga por código (y la nota de
que el historial de versiones de Obsidian puede guardar una copia).

Participante = agente + pestaña (WORKSPACE_WID, el id estable que sobrevive a
cerrar y reanudar): la clave es `<agente>--<pestaña>` (la de la presencia de
messages.py). El mismo agente en dos pestañas son dos participantes; una
pestaña reanudada hereda su lugar; un fork (otra pestaña) entra como nuevo.
Hasta MAX_PARTICIPANTES. Solo quien abrió o el socio suman gente (invitados
y el evento `invitar`); cualquier pestaña de un agente invitado se puede unir.

Menciones (`para`): una clave de participante, o el nombre del agente. El
nombre va a la ÚLTIMA pestaña de ese agente que habló en la sala (antes de ese
mensaje); si ninguna habló, a la primera que se unió; si ninguna se ha unido,
la primera pestaña de ese agente que lo reclame (se une y, si el cerebro está
en otra máquina, espera el asiento a que lleguen los reclamos de las otras:
asiento_de, según la salud del sync).
Máximo MAX_MENCIONES por mensaje, salvo quien abrió o el socio.

Tipos: `pide` despierta a los mencionados y les deja una DEUDA con espera
(propia del pedido o la de la sala; vence = hora del pedido + espera + lo que
el socio le sume). `responde` cierra la deuda de quien contesta y despierta
solo a quien preguntó. `info` no despierta a nadie. La deuda también se cierra
al soltarla (`soltar`, sin contestar), al pasarla a otro (`delegar`), al
cancelar el pedido o al cerrar la sala.

Topes aplicados al RECIBIR (no se confía en quien escribe): menciones de más,
participantes de más, mensajes después del tope de turnos o del cierre, de
quien no participa o con la firma alterada se MUESTRAN con su motivo pero no
se entregan. La firma es el HMAC per-máquina de messages.py sobre los campos
normalizados (messages.firmar_campos): un archivo de ESTA máquina que no
cuadra sale «alterado»; uno de otra máquina no se puede comprobar aquí.
Límite declarado: dentro de una máquina esto protege de accidentes, no de un
agente comprometido.

Entrega: por ids vistos, con un cursor LOCAL por pestaña
(`<estado>/salas/cursor/<clave>.json`, no viaja). El `turno` solo sirve para
pintar: el orden en pantalla es (turno, participante, id) y lo que llegó tarde
por el sync se marca, nunca se pierde. Un archivo a medias (el sync aún lo
escribe) no se lee: se reintenta en el siguiente sondeo (`largo` del cuerpo).

`esperar` es long-poll por archivos, sin daemon: un stat por carpeta en
reposo, solo se lee lo nuevo. Sale 0 si llegó algo, 3 si no (timeout), 4 si
un pedido tuyo venció o quien te debe respuesta está cerrado DE VERDAD (esta
máquina lo sabe por el proceso; otra, porque la pestaña lo dejó dicho al
cerrarse). Un otro lado «desconocido» (otra máquina sin datos) nunca corta la
espera: se respeta completa. Mientras espera, late la presencia de
messages.py (msgs/_presencia/).

`conversaciones/` queda FUERA de la búsqueda de memoria (memory_index,
decision_context): es texto de otros agentes, contenido no confiable.

CLI (`python3 messages.py conversar …` o `python3 salas.py …`):
    abrir --titulo "…" --objetivo "…" --con agente-b [--con agente-c:Pestaña]
          [--espera 30m] [--hecho-cuando "…"] [--max-turnos 20]
          [--pide "<cuerpo>" | --pide - | --cuerpo-archivo <ruta>] [--resumen "…"]
    publicar <sala> --tipo pide|responde|info --resumen "…" [--para X]…
          [--a <pedido>] [--espera 2h] "<cuerpo>" | - | --cuerpo-archivo <ruta>
Un texto con caracteres de control (salvo salto de línea y tabulador) se
rechaza con un error que dice cómo mandarlo (en PowerShell «`f» es U+000C).
    esperar [--sala <id>] [--timeout 90]
    ver [<sala>] [--completo]
    soltar <sala> --a <pedido> [--motivo "…"]
    delegar <sala> --a <pedido> --en <agente[:Pestaña]> --resumen "…"
    pausar | reanudar | cerrar | archivar <sala> [--resumen "…"]   (solo quien abrió)
Las acciones del socio (pausar, reanudar, cerrar, archivar, la espera, más
tiempo, cancelar un pedido, borrar) salen del hub › Conversaciones.

Stdlib, Python 3.9+, Mac / Windows / Linux. Falla suave en la lectura.
"""
import datetime as _dt
import json
import os
import re
import secrets
import sys
import time

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import messages as M                                            # noqa: E402

SALAS_DIR = "conversaciones"
SALA_MD = "sala.md"
TIPOS = ("pide", "responde", "info")
ACCIONES = ("unirse", "invitar", "pausa", "reanudar", "cierre", "archivar", "espera",
            "espera_pedido", "mas_tiempo", "cancelar", "soltar", "delegar", "tope", "lapida")
#: Lo que solo pueden el socio (desde el hub) o quien abrió la sala.
DE_DUENO = ("invitar", "pausa", "reanudar", "cierre", "archivar", "espera")
#: Lo que solo puede el socio.
DE_SOCIO = ("tope", "lapida")
#: Lo que pueden el socio o el autor del pedido.
DEL_PEDIDO = ("espera_pedido", "mas_tiempo", "cancelar")
#: Las esperas del selector (minutos), como en el hub.
ESPERAS = (15, 30, 60, 120, 480, 1440)
ESPERA_DEFAULT = 30
ESPERA_MAX = 7 * 1440
MAX_TURNOS = M.MAX_TURNOS
MAX_PARTICIPANTES = 6
MAX_MENCIONES = 2
ASIENTO_S = M.ASIENTO_S
#: El asiento de un reclamo en salas (revisión fría, hallazgo 3): el `unirse`
#: de la otra máquina tarda lo que tarde el sync en llegar. Medido entre la Mac
#: y la PC (Resultado_Prueba_Salas_Windows_v1.md): mediana ~33 s, máximo 105 s.
#: Con otra máquina sincronizando y una pestaña de ESE agente viva allá, el
#: asiento queda por encima del máximo medido; si no, un piso corto.
ASIENTO_SYNC_S = 120.0
ASIENTO_PISO_S = 15.0
GRACIA_CERRADO_MIN = M.OTRO_LADO_MIN
ESPERAR_TIMEOUT = M.ESPERAR_TIMEOUT
ESPERAR_INTERVALO = M.ESPERAR_INTERVALO
SALIDA_NADA = M.SALIDA_TIMEOUT            # 3
SALIDA_AVISO = M.SALIDA_OTRO_LADO         # 4: venció o el otro lado se cerró de verdad
LAPIDA_DIAS = 30
SOCIO = "socio"

_ALFA = "abcdefghjkmnpqrstuvwxyz23456789"
_SALA_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,40}-[a-z0-9]{5}$")
_ARCH_RE = re.compile(r"^(m|e)-(\d{6}T\d{6})-([a-z0-9]{5})(?:-([a-z_]+))?\.md$")
_FM_RE = re.compile(r"^---[ \t]*\n(.*?)\n---[ \t]*(?:\n|$)", re.S)
_CLIP_TITULO = 120
_CLIP_CUERPO = 20000


# ═══════════════════════════════════════════════════════════════════════════
# Piezas chicas
# ═══════════════════════════════════════════════════════════════════════════

def _ahora():
    return time.time()


def _azar(n=5):
    return "".join(secrets.choice(_ALFA) for _ in range(n))


def _iso(t):
    return _dt.datetime.fromtimestamp(t).astimezone().isoformat(timespec="seconds")


def _hora(t):
    try:
        return time.strftime("%H:%M", time.localtime(float(t)))
    except Exception:
        return "?"


def _slug(texto, n=24):
    try:
        from dash._common import slug
        return slug(texto, n)
    except Exception:
        s = re.sub(r"[^a-z0-9]+", "-", str(texto or "").lower()).strip("-")
        return s[:n].strip("-") or "sala"


def _linea(v, limite=280, lineas=3):
    return M._corto(v, limite, lineas)


def _cuerpo(texto):
    t = str(texto or "")[:_CLIP_CUERPO].encode("utf-8", "replace").decode("utf-8")
    return M.normalizar(t)


#: Caracteres de control que NO caben en un texto de sala (salto de línea,
#: tabulador y el \r de Windows sí): los C0, DEL y los C1 (U+0080–U+009F, con
#: U+009B, el CSI de 8 bits que una terminal ejecuta), los separadores de línea
#: y párrafo U+2028/U+2029 y los de dirección (U+202A–U+202E, U+2066–U+2069:
#: invierten el texto en pantalla). Revisión fría, hallazgo 15. En PowerShell las comillas invertidas
#: son escapes: «`f» entre comillas dobles llega como U+000C y el texto se
#: guardaba corrompido sin aviso (prueba en Windows, 2026-11-08).
_CONTROL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\u2028\u2029\u202a-\u202e"
                         "\u2066-\u2069]")


def _sin_control(campos):
    """Levanta Error si algún texto trae un carácter de control: dice cuál,
    dónde y cómo mandarlo bien. `campos` = [(nombre, texto)]."""
    for nombre, texto in campos:
        m = _CONTROL_RE.search(str(texto or ""))
        if not m:
            continue
        t = str(texto)
        a, b = max(0, m.start() - 12), min(len(t), m.end() + 12)
        trozo = _CONTROL_RE.sub("·", t[a:b]).replace("\n", " ")
        raise Error("%s trae un carácter de control (U+%04X, cerca de «%s»): no lo publico "
                    "porque se guardaría corrompido. En PowerShell la comilla invertida (`) "
                    "es un escape («`f» → U+000C): usa comillas simples, o manda el texto por "
                    "archivo UTF-8 en tu cerebro o en la carpeta temporal (--cuerpo-archivo "
                    "<ruta>; en PowerShell: Set-Content -Encoding utf8). Por stdin (-) solo "
                    "fuera de PowerShell 5.1, que cambia los acentos por «?» en la tubería"
                    % (nombre, ord(m.group(0)), trozo))


def leer_texto(ruta):
    """El cuerpo desde un archivo («-» = stdin), en UTF-8 (con o sin BOM) o
    UTF-16 con BOM (lo que deja `Out-File` en PowerShell 5.1)."""
    if ruta == "-":
        try:
            tty = sys.stdin is None or sys.stdin.isatty()
        except Exception:
            tty = False
        if tty:          # nadie le manda nada: se quedaría colgado (revisión fría, hallazgo 17)
            raise Error("«-» lee el texto de stdin, y stdin es la terminal: mándalo por tubería "
                        "(echo … | …) o con --cuerpo-archivo <ruta>")
    try:
        if ruta == "-":
            src = getattr(sys.stdin, "buffer", None)
            raw = src.read() if src is not None else sys.stdin.read().encode("utf-8")
        else:
            # lo que cabe en un cuerpo, más unos bytes: si el archivo es más
            # largo, el texto leído pasa de _CLIP_CUERPO y publicar avisa
            with open(ruta, "rb") as fh:
                raw = fh.read(_CLIP_CUERPO * 4 + 8)
                cortado = bool(fh.read(1))
    except OSError as e:
        raise Error("no pude leer %s: %s" % ("stdin" if ruta == "-" else ruta, e))
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        cod = "utf-16"
    else:
        cod = "utf-8-sig"
    try:
        if ruta != "-" and cortado:
            # el corte pudo caer a media letra: esa última letra se descarta
            # (revisión fría, hallazgo 11: antes salía «no está en UTF-8»)
            import codecs
            return codecs.getincrementaldecoder(cod)("strict").decode(raw, final=False)
        return raw.decode(cod)
    except UnicodeDecodeError:
        raise Error("%s no está en UTF-8: guárdalo como UTF-8 (en PowerShell: "
                    "Set-Content -Encoding utf8)" % ("stdin" if ruta == "-" else ruta))


def _temporales():
    """Las carpetas temporales de esta máquina (las del motor y las del
    sistema)."""
    import tempfile
    out = [tempfile.gettempdir()]
    out += [os.environ[v] for v in ("TMPDIR", "TEMP", "TMP") if os.environ.get(v)]
    if os.name != "nt":
        out.append("/tmp")
    return out


def archivo_permitido(ruta, brain):
    """¿`--cuerpo-archivo` puede leer `ruta`? Solo dentro del cerebro del
    agente o de una carpeta temporal (revisión fría, hallazgo 9: el comando
    del bus lo aprueba el motor sin preguntar, y un mensaje de otro agente
    podía inducir a publicar en la sala cualquier archivo de la máquina).
    Con la ruta real (sin `..` ni enlaces que salgan)."""
    try:
        real = os.path.normcase(os.path.realpath(os.path.abspath(ruta)))
    except Exception:
        return False
    for raiz in [brain] + _temporales():
        if not raiz:
            continue
        try:
            r = os.path.normcase(os.path.realpath(raiz)).rstrip("\\/")
        except Exception:
            continue
        if r and real.startswith(r + os.sep):
            return True
    return False


def _leer_archivo_del_agente(ruta, agente, resumen=""):
    """El cuerpo de `--cuerpo-archivo`: solo de un lugar permitido y con el
    gate de secretos SIN dejar pasar si no puede escanear (fail-closed)."""
    yo = identidad(agente)
    if yo is None:
        raise Error("%s no tiene cerebro en esta máquina" % (agente or "?"))
    if not archivo_permitido(ruta, yo["brain"]):
        raise Error("--cuerpo-archivo solo lee archivos de tu cerebro (%s) o de la carpeta "
                    "temporal; cópialo ahí primero, o manda el texto como argumento"
                    % yo["brain"])
    texto = leer_texto(ruta)
    if M._bus_secret_block(resumen, texto, strict=True):
        raise Error("el gate de secretos bloqueó el archivo (mira el aviso de arriba)")
    return texto


def _int(v, defecto=0):
    try:
        return int(str(v).strip())
    except Exception:
        return defecto


def _float(v, defecto=0.0):
    try:
        return float(str(v).strip())
    except Exception:
        return defecto


def minutos(texto):
    """«15m», «30 min», «2h», «1h30», «90» (minutos), «1d» → minutos (int) o
    None si no se entiende o se pasa de una semana."""
    s = str(texto or "").strip().lower().replace(" ", "")
    if not s:
        return None
    m = re.fullmatch(r"(\d+)(m|min|mins|minutos?)?", s)
    if m:
        n = int(m.group(1))
    else:
        m = re.fullmatch(r"(\d+)(h|hr|hrs|horas?)(\d+)?(m|min)?", s)
        if m:
            n = int(m.group(1)) * 60 + int(m.group(3) or 0)
        else:
            m = re.fullmatch(r"(\d+)(d|dias?|días?)", s)
            if not m:
                return None
            n = int(m.group(1)) * 1440
    return n if 1 <= n <= ESPERA_MAX else None


def espera_txt(mins):
    mins = _int(mins)
    if mins and mins % 1440 == 0:
        return "%d h" % (mins // 60) if mins // 1440 == 1 else "%d d" % (mins // 1440)
    if mins >= 60:
        h, r = divmod(mins, 60)
        return "%d h" % h if not r else "%d h %02d" % (h, r)
    return "%d min" % max(1, mins)


def falta_txt(seg):
    """«1 h 34», «12 min»: lo que falta para un vencimiento."""
    mins = max(1, int(seg) // 60)
    h, r = divmod(mins, 60)
    return ("%d h %02d" % (h, r)) if h and r else ("%d h" % h) if h else "%d min" % r


def agente_de(token):
    """El agente de un destino: «a--wid» → a · «?a» → a · «socio:x» → ''.
    La pestaña va después del ÚLTIMO «--» (un agente puede llevar «--»)."""
    t = str(token or "")
    if es_socio(t):
        return ""
    if t.startswith("?"):
        return t[1:]
    return t.rsplit("--", 1)[0]


def es_socio(token):
    """«socio:<nombre>» — con los dos puntos: un agente que se llame «socio-…»
    o «sociologo» sigue siendo un agente."""
    return str(token or "").startswith(SOCIO + ":")


# ── registros: escritura atómica y lectura con «a medias» ──────────────────
def _frontmatter(pares):
    return "---\n" + "".join("%s: %s\n" % (k, str(v if v is not None else ""))
                             for k, v in pares) + "---\n"


def _plano(v):
    """Un valor del frontmatter: normalizado, sin caracteres de control y en
    UNA línea."""
    t = re.sub(r"[\x00-\x09\x0b-\x1f\x7f]", " ", M.normalizar(v))
    return " · ".join(" ".join(x.split()) for x in t.split("\n") if x.strip())


def _con_firma(pares, cuerpo):
    pares = [(k, _plano(v)) for k, v in pares] + [("largo", str(len(cuerpo)))]
    firma = M.firmar_campos(pares + [("cuerpo", cuerpo)])
    return pares + [("hmac", firma)]


def _crear(carpeta, nombre_fn, pares, cuerpo):
    """Un archivo NUEVO (nunca pisa: O_EXCL; si el nombre ya existe, otro
    azar) con su contenido completo de una vez (atomico). Devuelve la ruta."""
    import atomico
    os.makedirs(carpeta, exist_ok=True)
    for _ in range(8):
        nombre = nombre_fn()
        ruta = os.path.join(carpeta, nombre)
        try:
            fd = os.open(ruta, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            continue
        os.close(fd)
        texto = _frontmatter(_con_firma(pares, cuerpo)) + ("\n" + cuerpo + "\n" if cuerpo else "")
        try:
            atomico.escribir(ruta, texto, avisar=True)
        except Exception:
            try:
                os.remove(ruta)
            except OSError:
                pass
            raise
        return ruta
    raise OSError("no hubo un nombre libre en %s" % carpeta)


#: Un archivo que sigue «a medias» más que esto ya no lo está escribiendo nadie:
#: lo editaron a mano (se muestra «alterado», no desaparece).
PARCIAL_S = 60.0


def _parsear(texto):
    """(campos en orden, cuerpo, completo) o None si ni el frontmatter está
    entero. `completo` = el cuerpo mide lo que dice `largo` (True); si mide MÁS
    no es una escritura a medias sino una edición ('largo'); si mide menos,
    False (a medias, o editado si ya pasó PARCIAL_S)."""
    t = str(texto or "").replace("\r\n", "\n").replace("\r", "\n")
    if t.startswith("\ufeff"):
        t = t[1:]
    m = _FM_RE.match(t)
    if not m:
        return None
    pares = []
    for ln in m.group(1).split("\n"):
        if ":" in ln and not ln.lstrip().startswith("#"):
            k, v = ln.split(":", 1)
            pares.append((k.strip().lower(), v.strip()))
    cuerpo = M.normalizar(t[m.end():])
    largo = _int(dict(pares).get("largo"), -1)
    if largo == len(cuerpo):
        return pares, cuerpo, True
    return pares, cuerpo, ("largo" if 0 <= largo < len(cuerpo) else False)


def _verificar(pares, cuerpo, yo):
    """ok | alterado | remota | sin_clave. Solo se puede comprobar lo que
    escribió ESTA máquina (la clave no viaja)."""
    fm = dict(pares)
    mid = fm.get("de_maquina_id") or ""
    local = (mid and mid == yo.get("id")) or (not mid and M._etiqueta(fm.get("de_maquina"))
                                              in (yo.get("alias") or set()))
    if not local:
        return "remota"
    if not fm.get("hmac"):
        return "sin_firma"          # se escribió sin clave (sandbox, otro HOME): no es una edición
    firmados = [(k, v) for k, v in pares if k != "hmac"] + [("cuerpo", cuerpo)]
    ok = M.firma_valida(firmados, fm.get("hmac") or "")
    if ok is None:
        return "sin_clave"
    return "ok" if ok else "alterado"


def _sobre_de(fm):
    return {k: fm.get(k, "") for k in ("de_agente", "de_maquina", "de_maquina_id", "de_sesion",
                                       "de_pestana", "de_motor")}


def _registro(nombre, pares, cuerpo, yo, mtime=0.0):
    fm = dict(pares)
    reg = {"archivo": nombre, "id": nombre[:-3], "cuerpo": cuerpo, "mtime": mtime,
           "firma": _verificar(pares, cuerpo, yo), "de": fm.get("de", ""),
           "t": _float(fm.get("t")) or (M._ts_epoch(fm.get("ts")) or 0.0), "ts": fm.get("ts", "")}
    reg.update(_sobre_de(fm))
    if nombre == SALA_MD:
        reg.update(kind="sala", sala=fm.get("id", ""), titulo=fm.get("titulo", ""),
                   objetivo=fm.get("objetivo", ""), hecho_cuando=fm.get("hecho_cuando", ""),
                   dueno=fm.get("dueno", ""), espera=_int(fm.get("espera"), ESPERA_DEFAULT),
                   max_turnos=_int(fm.get("max_turnos"), MAX_TURNOS),
                   invitados=[x.strip() for x in (fm.get("invitados") or "").split(",") if x.strip()])
        return reg
    m = _ARCH_RE.match(nombre)
    if m.group(1) == "m":
        tipo = fm.get("tipo", "")
        reg.update(kind="msg", tipo=tipo if tipo in TIPOS else "info", sala=fm.get("sala", ""),
                   turno=_int(fm.get("turno"), 0),
                   para=[x.strip() for x in (fm.get("para") or "").split(",") if x.strip()],
                   en_respuesta_a=fm.get("en_respuesta_a", ""),
                   espera=_int(fm.get("espera"), 0) or None, resumen=fm.get("resumen", ""))
    else:
        reg.update(kind="evento", accion=fm.get("accion") or (m.group(4) or ""),
                   sala=fm.get("sala", ""), pedido=fm.get("pedido", ""),
                   minutos=_int(fm.get("minutos"), 0), en=fm.get("en", ""),
                   motivo=fm.get("motivo", ""), por=fm.get("por", ""))
    return reg


# ═══════════════════════════════════════════════════════════════════════════
# Lectura incremental: un stat por carpeta, solo se lee lo nuevo
# ═══════════════════════════════════════════════════════════════════════════

#: Una carpeta que cambió hace menos que esto se vuelve a listar aunque su
#: mtime sea el mismo: en sistemas de archivos con reloj grueso (HFS+ 1 s,
#: FAT 2 s, carpetas de red) dos archivos del mismo segundo no mueven el mtime.
FRESCA_S = 3.0


def _reciente(mt_ns, listado=None):
    """¿Hay que volver a listar aunque el mtime sea el mismo? Sí si el último
    listado se hizo a menos de FRESCA_S del cambio: un archivo del mismo «tic»
    pudo llegar después sin mover el mtime."""
    ref = time.time() if listado is None else listado
    return (ref - mt_ns / 1e9) < FRESCA_S


class Almacen(object):
    """Lo leído de cada sala. Los archivos no cambian nunca: un registro
    leído entero se guarda por (nombre, mtime, tamaño); en reposo, revisar
    una sala es un stat de su carpeta. Lo que estaba a medias se reintenta."""

    def __init__(self):
        self.salas = {}            # carpeta → {"mt", "regs", "pend", "der", "ver"}
        self.raices = {}           # cerebro/conversaciones → (mtime, [carpetas])

    def carpetas(self, brains):
        """[(hogar, carpeta de la sala)] de todos los cerebros."""
        out = []
        for b in M._brain_paths(brains):
            raiz = os.path.join(b, SALAS_DIR)
            try:
                mt = os.stat(raiz).st_mtime_ns
            except OSError:
                continue
            hit = self.raices.get(raiz)
            if hit is None or hit[0] != mt or _reciente(mt, hit[2]):
                listado = time.time()
                try:
                    nombres = sorted(n for n in os.listdir(raiz) if _SALA_RE.match(n)
                                     and os.path.isdir(os.path.join(raiz, n)))
                except OSError:
                    nombres = []
                hit = self.raices[raiz] = (mt, nombres, listado)
            out += [(b, os.path.join(raiz, n)) for n in hit[1]]
        return out

    def leer(self, carpeta, yo):
        """{"regs": {nombre: registro}, "ver": n} de la carpeta, leyendo solo
        lo cambiado. None si no se puede listar."""
        try:
            mt = os.stat(carpeta).st_mtime_ns
        except OSError:
            self.salas.pop(carpeta, None)
            return None
        c = self.salas.get(carpeta)
        if (c is not None and c["mt"] == mt and not c["pend"]
                and not _reciente(mt, c.get("listado"))):
            return c
        c = c or {"mt": None, "regs": {}, "claves": {}, "pend": False, "ver": 0}
        listado = time.time()
        try:
            nombres = os.listdir(carpeta)
        except OSError:
            return None
        vivos, pend, cambio = set(), False, c["mt"] != mt
        for n in nombres:
            if n != SALA_MD and not _ARCH_RE.match(n):
                continue
            vivos.add(n)
            ruta = os.path.join(carpeta, n)
            try:
                st = os.stat(ruta)
            except OSError:
                continue
            clave = (st.st_mtime_ns, st.st_size)
            if c["claves"].get(n) == clave:
                continue
            try:
                with open(ruta, encoding="utf-8", errors="replace") as fh:
                    texto = fh.read(_CLIP_CUERPO + 8000)
            except OSError:
                pend = True
                continue
            p = _parsear(texto)
            viejo = time.time() - st.st_mtime > PARCIAL_S
            if p is None or (p[2] is False and not viejo):
                if p is None and viejo:          # ni frontmatter, hace rato: no es nuestro
                    c["claves"][n] = clave
                    c["regs"].pop(n, None)
                    continue
                pend = True                      # a medias: el sync todavía escribe
                c["regs"].pop(n, None)
                continue
            reg = _registro(n, p[0], p[1], yo, st.st_mtime)
            if p[2] is not True:                 # mide otra cosa que su `largo`: lo editaron
                reg["firma"] = "alterado"
            c["regs"][n] = reg
            c["claves"][n] = clave
            cambio = True
        for n in list(c["claves"]):
            if n not in vivos:
                cambio = cambio or n in c["regs"]
                c["regs"].pop(n, None)
                c["claves"].pop(n, None)
        c.update(mt=mt, pend=pend, listado=listado)
        if cambio:
            c["ver"] += 1
            c.pop("der", None)
        self.salas[carpeta] = c
        return c


_ALMACEN = Almacen()


def _yo_maquina():
    return M.mi_maquina()


def cargar(carpeta, hogar, almacen=None):
    """La sala DERIVADA de su carpeta (ver derivar), o None si no hay sala
    (sin sala.md, o borrada). Cachea mientras no cambie un archivo."""
    al = almacen or _ALMACEN
    c = al.leer(carpeta, _yo_maquina())
    if c is None:
        return None
    if "der" not in c:
        regs = c["regs"]
        if _lapidas_validas(regs, carpeta):
            _purgar(carpeta, regs)
            c["der"] = None
        elif SALA_MD not in regs:
            c["der"] = None
        else:
            c["der"] = derivar(regs, carpeta, hogar)
    return c["der"]


#: Una sala archivada hace menos que esto todavía se mira al esperar: quien
#: esperaba en ella tiene que enterarse del cierre aunque la archiven enseguida.
ARCHIVO_RECIENTE_S = 2 * 86400


def todas(brains=None, almacen=None, archivadas=True, recientes=False):
    """Las salas de todos los cerebros (`brains` None = registro), sin las
    borradas. Sin las archivadas si `archivadas=False` (eso no lee sus
    mensajes: basta el nombre de su evento), salvo, con `recientes`, las
    archivadas en los últimos ARCHIVO_RECIENTE_S."""
    al = almacen or _ALMACEN
    out = []
    for hogar, carpeta in al.carpetas(brains):
        if not archivadas:
            cuando = _archivada_por_nombre(carpeta, al)
            if cuando is not None and not (recientes and _ahora() - cuando < ARCHIVO_RECIENTE_S):
                continue
            # con `recientes` (esperar y el aviso al arrancar), una sala CERRADA
            # hace más de ARCHIVO_RECIENTE_S tampoco se lee: ya no entrega nada
            # (revisión fría, hallazgo 18: cada arranque leía todas las cerradas)
            if recientes:
                cierre = _archivada_por_nombre(carpeta, al, ("-cierre.md",))
                if cierre is not None and _ahora() - cierre >= ARCHIVO_RECIENTE_S:
                    continue
        s = cargar(carpeta, hogar, al)
        if s is not None and (archivadas or recientes or not s["archivada"]):
            out.append(s)
    return out


def _evento_confirmado(carpeta, nombre, al):
    """¿El evento `nombre` es VÁLIDO? Su nombre (…-archivar.md, …-lapida.md,
    …-cierre.md) es solo una pista barata: antes de esconder la sala se
    confirma con lo ya leído del almacén o leyendo ese evento y sala.md (no
    la sala entera) — firma, que sea de esta sala y la regla de quién puede
    (_evento_valido; la lápida, _lapidas_validas). Un archivo basura con ese
    nombre no deja a nadie sin sus pedidos."""
    if not _ARCH_RE.match(nombre):
        return False
    try:                                 # el veredicto, guardado por archivo (los dos no cambian)
        st_e, st_s = os.stat(os.path.join(carpeta, nombre)), os.stat(os.path.join(carpeta, SALA_MD))
        clave = (carpeta, nombre, st_e.st_mtime_ns, st_e.st_size, st_s.st_mtime_ns, st_s.st_size)
    except OSError:
        return False
    if clave in _CONFIRMADOS:
        return _CONFIRMADOS[clave]
    ok = _confirmar(carpeta, nombre, al, {nombre: (st_e.st_mtime_ns, st_e.st_size),
                                         SALA_MD: (st_s.st_mtime_ns, st_s.st_size)})
    if len(_CONFIRMADOS) > 4096:
        _CONFIRMADOS.clear()
    _CONFIRMADOS[clave] = ok
    return ok


#: (carpeta, nombre, mtime, tamaño, y los de sala.md) → ¿el evento es válido?
_CONFIRMADOS = {}


def _confirmar(carpeta, nombre, al, claves=None):
    """Lo de _evento_confirmado, sin caché. Lo ya leído del almacén solo se
    reusa si es de ESOS archivos (mismo mtime y tamaño que `claves`); si no,
    se relee. Un evento que no se puede leer o no es UTF-8 no confirma (la
    sala no se esconde) y se sigue con las demás."""
    c = al.salas.get(carpeta)
    regs = c.get("regs") if c else None
    vigentes = bool(c and claves and all((c.get("claves") or {}).get(n) == k
                                         for n, k in claves.items()))
    if not vigentes or not regs or nombre not in regs or SALA_MD not in regs:
        yo, regs = _yo_maquina(), {}
        for n in (SALA_MD, nombre):
            try:
                with open(os.path.join(carpeta, n), encoding="utf-8") as fh:
                    p = _parsear(fh.read())
            except (OSError, ValueError):            # UnicodeDecodeError es ValueError
                return False
            if not p:
                return False
            regs[n] = _registro(n, p[0], p[1], yo)
            if p[2] is not True:
                regs[n]["firma"] = "alterado"
    e, s0 = regs.get(nombre), regs.get(SALA_MD)
    if not e or not s0 or e.get("kind") != "evento":
        return False
    if e.get("accion") == "lapida":
        return nombre in _lapidas_validas({SALA_MD: s0, nombre: e}, carpeta)
    sid = s0.get("sala") or os.path.basename(os.path.normpath(carpeta))
    if e.get("sala") != sid or e.get("firma") == "alterado":
        return False
    sala = {"creador": s0.get("de") or "", "creador_agente": s0.get("de_agente") or "",
            "creador_sesion": s0.get("de_sesion") or ""}
    return _evento_valido(e, sala, ())


def _archivada_por_nombre(carpeta, al, sufijos=("-archivar.md", "-lapida.md")):
    """Epoch del archivo (o de la lápida; o del evento de `sufijos`) por el
    NOMBRE de su evento, confirmado (_evento_confirmado); None si no hay."""
    c = al.salas.get(carpeta)
    nombres = list(c["claves"].keys()) if c else None
    if nombres is None:
        try:
            nombres = os.listdir(carpeta)
        except OSError:
            return None
    out = None
    for n in nombres:
        if n.endswith(tuple(sufijos)) and _evento_confirmado(carpeta, n, al):
            m = _ARCH_RE.match(n)
            try:
                t = time.mktime(time.strptime(m.group(2), "%y%m%dT%H%M%S")) if m else 0.0
            except (ValueError, OverflowError):
                t = 0.0
            out = t if out is None else min(out, t)
    return out


def encontrar(sala_id, brains=None, almacen=None):
    """La sala derivada por su id, buscando en los cerebros. None si no."""
    sid = str(sala_id or "").strip()
    if not _SALA_RE.match(sid):
        return None
    for b in M._brain_paths(brains):
        carpeta = os.path.join(b, SALAS_DIR, sid)
        if os.path.isdir(carpeta):
            s = cargar(carpeta, b, almacen)
            if s is not None:
                return s
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Derivación (pura): participantes, orden, estado, topes, pedidos y deudas
# ═══════════════════════════════════════════════════════════════════════════

def _clave_orden(m):
    return (m.get("turno") or 0, m.get("de") or "", m["id"])


def derivar(regs, carpeta="", hogar=""):
    """Todo lo que se ve y se entrega de una sala, calculado de sus archivos
    (igual en todas las máquinas con los mismos archivos)."""
    s0 = regs[SALA_MD]
    sala = {"id": s0.get("sala") or os.path.basename(carpeta), "dir": carpeta, "hogar": hogar,
            "titulo": s0.get("titulo") or "", "objetivo": s0.get("objetivo") or "",
            "hecho_cuando": s0.get("hecho_cuando") or "", "dueno": s0.get("dueno") or "",
            "creada": s0["t"], "creador": s0.get("de") or "", "creador_agente": s0.get("de_agente") or "",
            "creador_sesion": s0.get("de_sesion") or "", "espera_base": s0.get("espera") or ESPERA_DEFAULT,
            "tope_base": s0.get("max_turnos") or MAX_TURNOS, "firma": s0.get("firma"),
            "cuerpo": s0.get("cuerpo") or ""}
    for r in regs.values():
        # un archivo firmado copiado de OTRA sala trae su `sala`: no se entrega
        # aquí como nuevo (revisión fría, hallazgo 14; la firma no ata la carpeta)
        if r["kind"] in ("msg", "evento") and r.get("sala") and r["sala"] != sala["id"]:
            r["firma"] = "alterado"
    eventos = sorted((r for r in regs.values() if r["kind"] == "evento"),
                     key=lambda r: (r["t"], r["id"]))
    msgs = sorted((r for r in regs.values() if r["kind"] == "msg"), key=_clave_orden)
    for e in eventos:
        e["valido"] = _evento_valido(e, sala, msgs)
    # ── participantes ────────────────────────────────────────────────────
    invitados = [_spec(x) for x in s0.get("invitados") or []]
    for e in eventos:
        if e["accion"] == "invitar" and e["valido"] and e.get("en"):
            invitados.append(_spec(e["en"]))
    permitidos = {sala["creador_agente"]} | {a for a, _w in invitados if a}
    parts, rechazados = {}, set()

    def nuevo(key, r, t, unido=True):
        return {"key": key, "agente": agente_de(key), "sesion": r.get("de_sesion", ""),
                "maquina": r.get("de_maquina", ""), "maquina_id": r.get("de_maquina_id", ""),
                "pestana": r.get("de_pestana", ""), "motor": r.get("de_motor", ""), "desde": t,
                "unido": unido, "creador": key == sala["creador"], "ultimo": None, "n": 0}
    if sala["creador"]:
        parts[sala["creador"]] = nuevo(sala["creador"], s0, s0["t"])
    for a, w in invitados:                         # invitado a una pestaña concreta
        k = "%s--%s" % (a, w) if (a and w) else ""
        if k and k not in parts and len(parts) < MAX_PARTICIPANTES:
            parts[k] = nuevo(k, {"de_sesion": w}, sala["creada"], unido=False)
    llegadas = sorted([(e["t"], e["id"], e) for e in eventos if e["accion"] == "unirse"]
                      + [(m["t"], m["id"], m) for m in msgs if not es_socio(m["de"])],
                      key=lambda x: (x[0], x[1]))
    for t, _i, r in llegadas:
        k = r.get("de") or ""
        if not k or "--" not in k or r.get("de_agente") != agente_de(k):
            continue
        p = parts.get(k)
        if p is not None:
            if not p["unido"]:
                p.update(nuevo(k, r, t))
            continue
        if agente_de(k) in permitidos and sum(1 for x in parts.values()) < MAX_PARTICIPANTES:
            parts[k] = nuevo(k, r, t)
        else:
            rechazados.add(k)
    sala["participantes"] = parts
    sala["rechazados"] = rechazados
    sala["invitados"] = [a for a, w in invitados if a and not w]
    sala["permitidos"] = permitidos
    # ── estado (de los eventos válidos, en orden) ────────────────────────
    sala.update(pausada=False, cerrada=False, cierre=None, archivada=False, borrada=False,
                espera=sala["espera_base"], tope=sala["tope_base"])
    for e in eventos:
        if not e["valido"]:
            continue
        a = e["accion"]
        if a == "cierre" and not sala["cerrada"]:
            sala["cerrada"], sala["cierre"] = True, e
        elif a in ("pausa", "reanudar") and not sala["cerrada"]:
            sala["pausada"] = a == "pausa"
        elif a == "archivar":
            sala["archivada"] = True
        elif a == "espera" and e["minutos"]:
            sala["espera"] = max(1, min(ESPERA_MAX, e["minutos"]))
        elif a == "tope" and e["minutos"]:
            sala["tope"] = max(1, e["minutos"])
    if sala["archivada"] and not sala["cerrada"]:
        sala["cerrada"] = True                      # archivar también para la entrega
    # ── mensajes: destinos, topes al recibir ─────────────────────────────
    n_agentes, previos = 0, []
    t_cierre = sala["cierre"]["t"] if sala["cierre"] else None
    for m in msgs:
        socio = es_socio(m["de"])
        priv = socio or m["de"] == sala["creador"] or (
            m.get("de_agente") == sala["creador_agente"] and not sala["creador_sesion"])
        para = [x for x in m["para"] if x != m["de"]]
        m["menciones_cortadas"] = (not priv) and len(para) > MAX_MENCIONES
        para = para[:MAX_PARTICIPANTES if priv else MAX_MENCIONES]
        m["destinos"] = [_resolver(x, parts, previos, m["t"], excluir=m["de"], nombres=permitidos)
                         for x in para]
        motivo = ""
        if m["firma"] == "alterado":
            motivo = "alterado"
        elif not socio and m["de"] not in parts:
            motivo = "no_participa"
        elif t_cierre is not None and m["t"] > t_cierre:
            motivo = "despues_del_cierre"
        elif not socio:
            n_agentes += 1
            if n_agentes > sala["tope"]:
                motivo = "tope"
        # su turno contra el tope, para pintar (la misma cuenta que «turno N
        # de M»); 0 = no gasta turno (el socio, o no entra en la cuenta)
        m["n_turno"] = n_agentes if (not socio and motivo in ("", "tope")) else 0
        m["motivo"] = motivo
        m["entregable"] = not motivo
        if m["entregable"] and m["de"] in parts:
            parts[m["de"]]["ultimo"] = m["t"]
            parts[m["de"]]["n"] += 1
            for k in ("pestana", "motor", "maquina", "maquina_id"):     # el sobre más nuevo
                if m.get("de_" + k):
                    parts[m["de"]][k] = m["de_" + k]
        previos.append(m)
    sala["mensajes"] = msgs
    sala["eventos"] = eventos
    sala["turnos"] = n_agentes
    sala["turno_max"] = max([m.get("turno") or 0 for m in msgs] or [0])
    sala["pedidos"] = _pedidos(sala, msgs, eventos)
    return sala


def _spec(texto):
    """«agente» · «agente@wid» → (agente, wid)."""
    t = str(texto or "").strip()
    a, _s, w = t.partition("@")
    return M._safe_name(a), M._safe_sesion(w)


def _evento_valido(e, sala, msgs):
    a = e.get("accion")
    de = e.get("de") or ""
    if a not in ACCIONES:
        return False
    socio = es_socio(de)
    creador = de == sala["creador"] or (e.get("de_agente") == sala["creador_agente"]
                                        and not sala["creador_sesion"] and not socio)
    if e.get("firma") == "alterado":
        return False
    if a in DE_SOCIO:
        return socio
    if a in DE_DUENO:
        return socio or creador
    if a in DEL_PEDIDO:
        ped = next((m for m in msgs if m["id"] == e.get("pedido")), None)
        return bool(ped) and (socio or ped["de"] == de)
    return True                                     # unirse, soltar, delegar: se juzgan al usarse


def _es_clave(tok, parts, nombres=()):
    """¿`tok` es una clave de participante («agente--pestaña») y no el NOMBRE
    de un agente que lleva «--» (válido en agentsreg)? Una clave conocida lo
    es; un nombre permitido en la sala, no; lo demás con «--», sí (la de
    alguien cuyo `unirse` aún no llega por el sync). Revisión fría, hallazgo 12."""
    if tok in parts:
        return True
    return "--" in tok and tok not in nombres


def _resolver(token, parts, previos, t, excluir="", nombres=()):
    """Un destino del `para` → clave de participante, «?agente» (nadie de ese
    agente se ha unido todavía) o «socio:…». Un nombre va a la última pestaña
    de ese agente que habló ANTES de este mensaje; si ninguna habló, a la
    primera que se unió. `excluir` = quien escribe: su propio nombre de agente
    quiere decir «otra pestaña mía», nunca él mismo."""
    tok = str(token or "").strip()
    if es_socio(tok) or _es_clave(tok, parts, nombres):
        return tok
    a = M._safe_name(tok)
    unidos = [p for p in parts.values() if p["agente"] == a and p["unido"] and p["key"] != excluir]
    antes = [p for p in unidos if p["desde"] <= t + 1]
    if antes:
        ult = {}
        for m in previos:
            if m["de"] in parts and parts[m["de"]]["agente"] == a and m.get("entregable"):
                ult[m["de"]] = m["t"]
        hablaron = [p for p in antes if p["key"] in ult]
        if hablaron:
            return max(hablaron, key=lambda p: (ult[p["key"]], p["key"]))["key"]
        return min(antes, key=lambda p: (p["desde"], p["key"]))["key"]
    if unidos:
        return min(unidos, key=lambda p: (p["desde"], p["key"]))["key"]
    return "?" + a


def _deudor(p, key, agente):
    """El destino pendiente de `p` que corresponde a quien escribe: su clave
    exacta o, si el pedido todavía no tiene pestaña de ese agente, «?agente».
    Nunca la deuda de OTRA pestaña del mismo agente."""
    pend = [d for d in p["a"] if d not in p["listos"]]
    if key in pend:
        return key
    return ("?" + agente) if agente and ("?" + agente) in pend else None


def _espera_en(sala, eventos, t):
    """La espera de la sala vigente cuando se hizo un pedido (la de la sala
    es el valor por defecto de cada pedido NUEVO; cambiarla no mueve los de
    antes)."""
    esp = sala["espera_base"]
    for e in eventos:
        if e["accion"] == "espera" and e.get("valido") and e["minutos"] and e["t"] <= t:
            esp = max(1, min(ESPERA_MAX, e["minutos"]))
    return esp


def _pedidos(sala, msgs, eventos):
    """{id del pide: {de, a (destinos), listos, estado, espera, vence, …}} —
    las deudas: quién debe responder qué, y para cuándo."""
    out = {}
    for m in msgs:
        if m["tipo"] != "pide" or not m["entregable"]:
            continue
        a = [d for d in m["destinos"] if not es_socio(d) and d != m["de"]]
        out[m["id"]] = {"id": m["id"], "de": m["de"], "a": list(dict.fromkeys(a)), "listos": [],
                        "soltados": [], "delegados": {}, "respuestas": [], "estado": "esperando",
                        "espera": m.get("espera") or _espera_en(sala, eventos, m["t"]), "mas": 0,
                        "cancelado_por": "", "t": m["t"]}
    # Respuestas y eventos en UN recorrido, en el orden en que pasaron: la
    # respuesta de quien recibió un pedido delegado cuenta porque el
    # `delegar` ya lo sumó (revisión fría, hallazgo 2). Una respuesta que no
    # encontró su deuda se vuelve a probar al final (relojes de otra máquina
    # un poco atrasados: la respuesta «antes» del delegar).
    resp = [r for r in msgs if r["tipo"] == "responde" and r["entregable"]
            and r.get("en_respuesta_a") in out]
    sin_deuda = []

    def _responder(r):
        p = out[r["en_respuesta_a"]]
        d = _deudor(p, r["de"], r.get("de_agente"))
        if d:
            p["listos"].append(d)
        return bool(d)
    linea = sorted([(r["t"], r["id"], "r", r) for r in resp] +
                   [(e["t"], e["id"], "e", e) for e in eventos], key=lambda x: (x[0], x[1]))
    for r in resp:
        out[r["en_respuesta_a"]]["respuestas"].append(r["id"])
    for _t, _i, clase, x in linea:
        if clase == "r":
            if not _responder(x):
                sin_deuda.append(x)
            continue
        e = x
        p = out.get(e.get("pedido"))
        if p is None:
            continue
        a = e["accion"]
        if a in ("soltar", "delegar"):
            if not e.get("valido"):            # firma alterada, etc. (_evento_valido): nada
                continue
            deudor = _deudor(p, e["de"], e.get("de_agente"))
            e["valido"] = bool(deudor)
            if not deudor:
                continue
            if a == "soltar":
                p["listos"].append(deudor)
                p["soltados"].append(deudor)
                continue
            nuevo = _resolver(e.get("en"), sala["participantes"], msgs, e["t"], excluir=e["de"],
                              nombres=sala["permitidos"])
            ok = (not es_socio(nuevo) and agente_de(nuevo) in sala["permitidos"]
                  and nuevo != p["de"] and nuevo != deudor)
            e["valido"] = ok
            if not ok:                         # pasar el pedido a quien lo hizo no lo cierra
                continue
            p["listos"].append(deudor)
            p["delegados"][nuevo] = {"de": deudor, "evento": e["id"]}
            if nuevo not in p["a"]:
                p["a"].append(nuevo)
            elif nuevo in p["listos"]:
                p["listos"].remove(nuevo)
        elif (a == "cancelar" and e["valido"] and p["estado"] == "esperando"
              and any(d not in p["listos"] for d in p["a"])):
            p["estado"], p["cancelado_por"] = "cancelado", e["de"]
            p["cancelados"] = [d for d in p["a"] if d not in p["listos"]]
        elif a == "espera_pedido" and e["valido"] and e["minutos"]:
            p["espera"] = max(1, min(ESPERA_MAX, e["minutos"]))
        elif a == "mas_tiempo" and e["valido"] and e["minutos"]:
            p["mas"] += e["minutos"]
    for r in sin_deuda:
        _responder(r)
    for p in out.values():
        p["vence"] = p["t"] + (p["espera"] + p["mas"]) * 60
        p["pendientes"] = [d for d in p["a"] if d not in p["listos"]]
        if p["estado"] == "esperando":
            if not p["pendientes"]:
                p["estado"] = "listo"
            elif sala["cerrada"]:
                p["estado"] = "cerrado"
    return out


def vencido(p, ahora=None):
    return bool(p and p["estado"] == "esperando" and (ahora or _ahora()) >= p["vence"])


# ═══════════════════════════════════════════════════════════════════════════
# Quién soy (la pestaña que corre el comando) y quién es el socio
# ═══════════════════════════════════════════════════════════════════════════

def identidad(agente, brains=None, sesion=None, _sobre=None):
    """La pestaña que corre esto: {agente, sesion, key, brain, sobre, socio,
    cerebros}.
    None si el agente no tiene cerebro en esta máquina."""
    a = M._safe_name(agente)
    bm = brains if isinstance(brains, dict) else M.registered_brains()
    brain = bm.get(a, "") if a else ""
    if not brain or not os.path.isdir(brain):
        return None
    sob = M.sobre()
    if isinstance(_sobre, dict):
        sob.update({k: str(v or "") for k, v in _sobre.items() if k in sob})
    ses = M._safe_sesion(sob["de_sesion"] if sesion is None else sesion)
    sob["de_sesion"] = ses
    yo = M.mi_maquina()
    return {"agente": a, "sesion": ses, "key": M._clave_presencia(a, ses, yo), "brain": brain,
            "sobre": sob, "socio": _socio_de(brain), "cerebros": bm}


def _socio_de(brain):
    try:
        import usuarios
        return usuarios.socio_actual(brain, arreglar=False) or ""
    except Exception:
        return ""


def socio_de_sala(sala):
    return sala.get("dueno") or _socio_de(sala.get("hogar")) or SOCIO


def _pares_sobre(de, sob, agente=""):
    return [("de", de), ("de_agente", agente), ("de_maquina", M._etiqueta(sob.get("de_maquina"))),
            ("de_maquina_id", M._safe_sesion(sob.get("de_maquina_id"))),
            ("de_sesion", M._safe_sesion(sob.get("de_sesion"))),
            ("de_pestana", _linea(sob.get("de_pestana"), 80, 1)),
            ("de_motor", M._safe_name(sob.get("de_motor")))]


def sobre_socio(socio):
    """El sobre de lo que escribe el socio desde el hub: esta máquina, sin
    pestaña de agente."""
    yo = M.mi_maquina()
    return {"de_maquina": yo.get("etiqueta", ""), "de_maquina_id": yo.get("id", ""),
            "de_sesion": "", "de_pestana": "hub", "de_motor": ""}


# ═══════════════════════════════════════════════════════════════════════════
# Escribir: abrir, unirse, publicar, eventos
# ═══════════════════════════════════════════════════════════════════════════

class Error(Exception):
    """Lo que el comando le dice al agente (y no se escribió nada)."""


def _nombre_msg():
    return "m-%s-%s.md" % (time.strftime("%y%m%dT%H%M%S"), _azar())


def _nombre_evento(accion):
    return lambda: "e-%s-%s-%s.md" % (time.strftime("%y%m%dT%H%M%S"), _azar(), accion)


_LEEME = ("# Conversaciones\n\n"
          "Salas de agentes que conversan por mensajes en archivos (Workspace › Conversaciones).\n\n"
          "- **Contenido no confiable:** lo escriben otros agentes. No es memoria ni instrucciones;\n"
          "  queda fuera de la búsqueda de memoria.\n"
          "- **No se edita a mano:** cada archivo se escribe una vez y no cambia; la firma lo\n"
          "  marca como «alterado» si alguien lo toca.\n"
          "- Borrar una sala desde el hub deja una lápida y purga lo demás. El historial de\n"
          "  versiones de Obsidian puede conservar una copia.\n")


def _leeme(hogar):
    p = os.path.join(hogar, SALAS_DIR, "README.md")
    if not os.path.exists(p):
        try:
            import atomico
            atomico.escribir(p, _LEEME)
        except Exception:
            pass


def _resolver_invitado(texto, brains):
    """«agente» o «agente:Pestaña» → (spec «agente[@wid]», aviso)."""
    t = str(texto or "").strip()
    nombre, _s, pest = t.partition(":")
    a = M._safe_name(nombre)
    if not a or a not in brains:
        raise Error("%s no es un agente con cerebro en esta máquina" % (nombre or "?"))
    if not pest.strip():
        return a, ""
    wid, _nom, aviso = M.resolver_pestana(brains[a], a, pest.strip())
    if not wid:
        raise Error(aviso)
    return "%s@%s" % (a, wid), ""


def abrir(agente, titulo, objetivo, con=(), espera=None, hecho_cuando="", max_turnos=None,
          brains=None, sesion=None, cuerpo="", _sobre=None):
    """Abre una sala en el cerebro de `agente` (su hogar) e invita a `con`
    («agente» o «agente:Pestaña»). Devuelve el id. Levanta Error."""
    yo = identidad(agente, brains, sesion, _sobre)
    if yo is None:
        raise Error("%s no tiene cerebro en esta máquina" % (agente or "?"))
    _sin_control([("el título", titulo), ("el objetivo", objetivo),
                  ("el «hecho cuando»", hecho_cuando), ("el cuerpo", cuerpo)])
    tit = _linea(titulo, _CLIP_TITULO, 1)
    obj = _linea(objetivo)
    if not tit or not obj:
        raise Error("falta --titulo o --objetivo")
    invitados = []
    for x in con or ():
        spec, _av = _resolver_invitado(x, yo["cerebros"])
        if spec not in invitados:
            invitados.append(spec)
    if not invitados:
        raise Error("falta --con <agente>: una sala es para conversar con alguien")
    if len(invitados) + 1 > MAX_PARTICIPANTES:
        raise Error("máximo %d participantes por sala" % MAX_PARTICIPANTES)
    esp = espera if isinstance(espera, int) else (minutos(espera) if espera else ESPERA_DEFAULT)
    if not esp:
        raise Error("no entiendo la espera «%s» (ej.: 15m, 30m, 1h, 2h, 8h, 24h)" % espera)
    tope = _int(max_turnos, MAX_TURNOS) if max_turnos else MAX_TURNOS
    texto = _cuerpo(cuerpo)
    if M._bus_secret_block("\n".join((tit, obj, _linea(hecho_cuando))), texto):
        raise Error("el gate de secretos bloqueó la sala (mira el aviso de arriba)")
    raiz = os.path.join(yo["brain"], SALAS_DIR)
    os.makedirs(raiz, exist_ok=True)
    _leeme(yo["brain"])
    for _ in range(8):
        sid = "%s-%s" % (_slug(tit, 24), _azar())
        carpeta = os.path.join(raiz, sid)
        try:
            os.makedirs(carpeta)
            break
        except FileExistsError:
            continue
    else:
        raise Error("no hubo un id libre para la sala")
    t = _ahora()
    pares = [("tipo", "sala"), ("version", "1"), ("id", sid), ("titulo", tit), ("objetivo", obj),
             ("hecho_cuando", _linea(hecho_cuando)), ("dueno", yo["socio"]),
             ("espera", str(esp)), ("max_turnos", str(max(1, tope))),
             ("invitados", ", ".join(invitados)), ("t", "%.3f" % t), ("ts", _iso(t))]
    pares += _pares_sobre(yo["key"], yo["sobre"], yo["agente"])
    _crear(carpeta, lambda: SALA_MD, pares, texto)
    return sid


def _escribir_evento(sala, accion, de, sob, agente="", **extra):
    t = _ahora()
    pares = [("tipo", "evento"), ("accion", accion), ("sala", sala["id"]),
             ("t", "%.3f" % t), ("ts", _iso(t))] + _pares_sobre(de, sob, agente)
    for k in ("pedido", "minutos", "en", "motivo", "por"):
        if extra.get(k) not in (None, ""):
            pares.append((k, _linea(extra[k]) if k == "motivo" else str(extra[k])))
    ruta = _crear(sala["dir"], _nombre_evento(accion), pares, "")
    return os.path.basename(ruta)[:-3]


def _candado(sala):
    try:
        import olock
        if olock.file_lock is None:
            return None
        return olock.file_lock(olock.ruta_candado(os.path.join(sala["dir"], "unirse")), timeout=5)
    except Exception:
        return None


def unirse(sala, yo):
    """Deja el evento `unirse` de esta pestaña si todavía no está (bajo el
    candado de la sala: dos pestañas de esta máquina no se unen dos veces).
    True si quedó dentro."""
    if yo["key"] in sala["participantes"] and sala["participantes"][yo["key"]]["unido"]:
        return True
    lk = _candado(sala)

    def _hacer():
        s = cargar(sala["dir"], sala["hogar"]) or sala
        p = s["participantes"].get(yo["key"])
        if p and p["unido"]:
            return True
        if yo["agente"] not in s["permitidos"]:
            return False
        if p is None and len(s["participantes"]) >= MAX_PARTICIPANTES:
            return False
        _escribir_evento(s, "unirse", yo["key"], yo["sobre"], yo["agente"])
        return True
    if lk is None:
        return _hacer()
    try:
        with lk:
            return _hacer()
    except Exception:
        return _hacer()


def _resolver_para(sala, yo, tokens):
    """Los destinos que escribe el agente («agente», «agente:Pestaña» o la
    clave) → claves (o el nombre, si de ese agente no hay nadie todavía)."""
    out = []
    for tok in tokens or ():
        t = str(tok or "").strip()
        if not t:
            continue
        if _es_clave(t, sala["participantes"], sala["permitidos"]):
            if t not in sala["participantes"]:
                raise Error("%s no participa en esta sala" % t)
            out.append(t)
            continue
        nombre, _s, pest = t.partition(":")
        a = M._safe_name(nombre)
        if a not in sala["permitidos"]:
            raise Error("%s no está en esta sala (están: %s); quien la abrió o el socio pueden "
                        "sumarlo" % (nombre, ", ".join(sorted(sala["permitidos"])) or "nadie"))
        if pest.strip():
            sl = M._slug_pestana(pest)
            cand = [p["key"] for p in sala["participantes"].values()
                    if p["agente"] == a and M._slug_pestana(p["pestana"]) == sl]
            if not cand:
                wid, _n, aviso = M.resolver_pestana(yo["cerebros"].get(a, ""), a, pest.strip())
                if not wid:
                    raise Error(aviso)
                cand = ["%s--%s" % (a, wid)]
            out.append(cand[0])
            continue
        r = _resolver(a, sala["participantes"], sala["mensajes"], _ahora(), excluir=yo["key"],
                      nombres=sala["permitidos"])
        out.append(a if r.startswith("?") else r)
    out = [x for x in dict.fromkeys(out) if x != yo["key"]]
    return out


def _lo_tomo_otra(sala, yo):
    """(pedido, «Pestaña · máquina») si un pedido que se me entregó ya es de
    OTRA pestaña de mi agente (dos máquinas lo reclamaron y el sync dijo cuál
    se unió primero); None si no."""
    vistos = set(cursor(yo["key"], yo.get("brain"))["ids"].get(sala["id"], ()))
    for p in sala["pedidos"].values():
        if p["id"] not in vistos or p["estado"] != "esperando":
            continue
        for d in p["pendientes"]:
            q = sala["participantes"].get(d)
            if q and q["agente"] == yo["agente"] and d != yo["key"]:
                donde = " · ".join(x for x in (q.get("pestana"), q.get("maquina")) if x)
                return p["id"], donde or d
    return None


def deudas_de(sala, key, agente=""):
    """Los pedidos que `key` (o su agente, si el pedido aún no tiene pestaña)
    debe responder en la sala, en orden."""
    out = []
    for m in sala["mensajes"]:
        p = sala["pedidos"].get(m["id"])
        if not p or p["estado"] != "esperando" or p["de"] == key:
            continue
        if any(d == key or (d.startswith("?") and agente_de(d) == agente) for d in p["pendientes"]):
            out.append(p)
    return out


def publicar(sala_id, agente, tipo, cuerpo, resumen, para=(), a="", espera=None, brains=None,
             sesion=None, _sobre=None):
    """Publica un mensaje del agente de esta pestaña. Devuelve (id, avisos).
    Levanta Error (y no escribe) si no se puede."""
    yo = identidad(agente, brains, sesion, _sobre)
    if yo is None:
        raise Error("%s no tiene cerebro en esta máquina" % (agente or "?"))
    sala = encontrar(sala_id, yo["cerebros"])
    if sala is None:
        raise Error("no encuentro la sala %s (¿id correcto? ¿llegó el cerebro de quien la "
                    "abrió a esta máquina?)" % sala_id)
    tipo = str(tipo or "").strip().lower()
    if tipo not in TIPOS:
        raise Error("--tipo tiene que ser pide, responde o info")
    _sin_control([("el resumen", resumen), ("el cuerpo", cuerpo)])
    res = _linea(resumen)
    if not res:
        raise Error("falta --resumen \"…\" (1-3 líneas: qué trae el mensaje)")
    texto = _cuerpo(cuerpo)
    if not texto:
        raise Error("falta el cuerpo del mensaje")
    _puede_hablar(sala, yo)
    if sala["turnos"] >= sala["tope"]:
        raise Error("la sala llegó a su tope de %d turnos: cierra con lo que hay o pídele al "
                    "socio que lo suba desde el hub" % sala["tope"])
    destinos = _resolver_para(sala, yo, para)
    priv = yo["key"] == sala["creador"]
    if len(destinos) > MAX_MENCIONES and not priv:
        raise Error("máximo %d menciones por mensaje (solo quien abrió menciona a más)"
                    % MAX_MENCIONES)
    en_resp = ""
    esp = None
    if tipo == "pide":
        if not destinos:
            raise Error("un pide necesita --para <agente>: a quién le pides")
        if espera:
            esp = minutos(espera)
            if not esp:
                raise Error("no entiendo la espera «%s» (ej.: 15m, 30m, 1h, 2h)" % espera)
    elif tipo == "responde":
        deudas = deudas_de(sala, yo["key"], yo["agente"])
        if a:
            p = sala["pedidos"].get(str(a).strip())
            if p is None:
                raise Error("%s no es un pedido de esta sala" % a)
        elif len(deudas) == 1:
            p = deudas[0]
        elif not deudas:
            otra = _lo_tomo_otra(sala, yo)
            if otra:
                raise Error("el pedido %s lo tomó otra pestaña de %s (%s): no lo respondas tú; "
                            "para avisar algo usa --tipo info" % (otra[0], yo["agente"], otra[1]))
            raise Error("no tienes pedidos que responder en esta sala; para avisar algo usa "
                        "--tipo info")
        else:
            raise Error("tienes %d pedidos abiertos: di cuál con --a <id> (%s)"
                        % (len(deudas), ", ".join(x["id"] for x in deudas)))
        en_resp = p["id"]
        destinos = [p["de"]]
    if M._bus_secret_block(res, texto):
        raise Error("el gate de secretos bloqueó el mensaje (mira el aviso de arriba)")
    if not unirse(sala, yo):
        raise Error("no pude unirte a la sala (¿tope de %d participantes?)" % MAX_PARTICIPANTES)
    sala = encontrar(sala_id, yo["cerebros"]) or sala
    t = _ahora()
    pares = [("tipo", tipo), ("sala", sala["id"]), ("turno", str(sala["turno_max"] + 1)),
             ("t", "%.3f" % t), ("ts", _iso(t))] + _pares_sobre(yo["key"], yo["sobre"], yo["agente"])
    pares += [("para", ", ".join(destinos)), ("en_respuesta_a", en_resp),
              ("espera", str(esp) if esp else ""), ("resumen", res)]
    ruta = _crear(sala["dir"], _nombre_msg, pares, texto)
    mid = os.path.basename(ruta)[:-3]
    recorte = []
    if len(str(cuerpo or "")) > _CLIP_CUERPO:
        recorte = ["el cuerpo pasaba de %d caracteres: se guardó recortado a %d (lo demás, en "
                   "otro mensaje)" % (_CLIP_CUERPO, _CLIP_CUERPO)]
    paneles = _avisar_paneles(sala["id"], mid, yo["cerebros"], yo["key"])
    return mid, recorte + _avisos_destinos(sala, destinos, yo, paneles) + _avisos_arroba(
        sala, yo, res + "\n" + texto, destinos)


def _avisar_paneles(sala_id, mid, brains, quien=""):
    """El aviso en su panel de herdr a las pestañas de ESTA máquina que el
    mensaje despierta y no escuchan (aviso_panel; decisión del socio, opción
    A). {token: (estado, texto)}; falla suave → {}."""
    if os.environ.get("WORKSPACE_NO_AVISO_PANEL"):
        return {}
    try:
        import aviso_panel
        return aviso_panel.tras_publicar(sala_id, mid, brains, quien)
    except Exception:
        return {}


def _puede_hablar(sala, yo):
    if sala["borrada"]:
        raise Error("la sala se borró")
    if sala["archivada"]:
        raise Error("la sala está archivada")
    if sala["cerrada"]:
        raise Error("la sala está cerrada: ya no se habla en ella")
    if sala["pausada"]:
        raise Error("la sala está en pausa (el socio la pausó): no actúes hasta que la reanude")
    if yo["agente"] not in sala["permitidos"] and yo["key"] not in sala["participantes"]:
        raise Error("no participas en esta sala; quien la abrió o el socio pueden sumarte")


_ARROBA_RE = re.compile(r"(?<![\w@.])@([A-Za-z0-9][A-Za-z0-9_-]{0,40})")


def _avisos_arroba(sala, yo, texto, destinos):
    """Un «@nombre» en el texto no es una mención: si nombra a un
    participante que no va en --para, ese agente no se entera. Aviso (no
    rechazo) con el comando exacto para pedírselo."""
    van = {agente_de(d) for d in destinos}
    out = []
    for m in _ARROBA_RE.finditer(texto or ""):
        a = M._safe_name(m.group(1))
        if (not a or a == yo["agente"] or a in van or a not in sala["permitidos"]
                or any(a in x for x in out)):
            continue
        out.append("el texto nombra a @%s, pero %s no va en --para: no se entera. Para "
                   "pedírselo: %s publicar %s --tipo pide --para %s --resumen \"…\" \"<cuerpo>\""
                   % (m.group(1), a, _cmd(), sala["id"], a))
    return out


def _avisos_destinos(sala, destinos, yo=None, paneles=None):
    """«X no está escuchando» por cada destino que no escucha. Mi propia
    pestaña no cuenta como «escuchando» por otra mía (`--con <yo>`).
    `paneles` = lo que hizo aviso_panel (opción A del socio, 2026-11-08): si
    Workspace le escribió en su panel de herdr, la línea lo dice; si no
    pudo (foco, trabajando, otra máquina), dice por qué."""
    out = []
    paneles = paneles or {}
    for d in destinos:
        if es_socio(d):
            continue
        mia = (yo or {}).get("sesion", "") if yo and agente_de(d) == yo["agente"] else ""
        est = estado_participante(sala, d, brains=(yo or {}).get("cerebros"), excluir=mia)
        if est["estado"] != "escuchando":
            pan = paneles.get(d) or paneles.get("?" + d) or ("", "")
            if pan[0] in ("avisado", "ya"):
                out.append("%s no está escuchando (%s): Workspace le avisó en su panel"
                           % (nombre_de(sala, d), _estado_txt(est)))
            elif pan[0] in ("foco", "trabajando"):
                out.append("%s no está escuchando (%s); el mensaje queda en la sala (%s; el hub "
                           "ofrece «Avisar»)" % (nombre_de(sala, d), _estado_txt(est), pan[1]))
            else:
                out.append("%s no está escuchando (%s); el mensaje queda en la sala"
                           % (nombre_de(sala, d), _estado_txt(est)))
    return out


def publicar_socio(sala_id, texto, para=None, socio=None, brains=None):
    """Lo que escribe el socio desde el hub: un `pide` a `para` (por defecto,
    el último agente que habló). Devuelve el id. Levanta Error."""
    sala = encontrar(sala_id, brains)
    if sala is None:
        raise Error("la sala ya no está")
    if sala["cerrada"] or sala["pausada"] or sala["archivada"]:
        raise Error("la sala está %s" % ("en pausa" if sala["pausada"] and not sala["cerrada"]
                                         else "cerrada"))
    cuerpo = _cuerpo(texto)
    if not cuerpo:
        raise Error("vacío")
    dest = [d for d in (para if para is not None else [mencion_defecto(sala)]) if d]
    if not dest:
        raise Error("no hay a quién: la sala no tiene agentes todavía")
    socio = socio or socio_de_sala(sala)
    if M._bus_secret_block(_linea(cuerpo), cuerpo):
        raise Error("el gate de secretos lo bloqueó")
    t = _ahora()
    pares = [("tipo", "pide"), ("sala", sala["id"]), ("turno", str(sala["turno_max"] + 1)),
             ("t", "%.3f" % t), ("ts", _iso(t))]
    pares += _pares_sobre("%s:%s" % (SOCIO, M._safe_name(socio) or SOCIO), sobre_socio(socio))
    pares += [("para", ", ".join(dest)), ("en_respuesta_a", ""), ("espera", ""),
              ("resumen", _linea(cuerpo))]
    ruta = _crear(sala["dir"], _nombre_msg, pares, cuerpo)
    mid = os.path.basename(ruta)[:-3]
    _avisar_paneles(sala["id"], mid, brains, "socio")
    return mid


def mencion_defecto(sala):
    """A quién va lo que escribe el socio si no dice nada: al último agente
    que habló; si nadie habló, al primer invitado."""
    for m in reversed(sala["mensajes"]):
        if not es_socio(m["de"]) and m["de"] in sala["participantes"]:
            return m["de"]
    for p in sala["participantes"].values():
        if not p["creador"]:
            return p["key"]
    if sala["invitados"]:
        return sala["invitados"][0]
    return sala["creador"]


def accion_socio(sala_id, accion, socio=None, brains=None, **extra):
    """Pausa, reanudar, cierre, archivar, espera, mas_tiempo, cancelar,
    espera_pedido, tope o lapida desde el hub. Devuelve el id del evento."""
    if accion not in ACCIONES or accion in ("unirse", "soltar", "delegar"):
        raise Error("acción desconocida")
    sala = encontrar(sala_id, brains)
    if sala is None:
        raise Error("la sala ya no está")
    socio = M._safe_name(socio or socio_de_sala(sala)) or SOCIO
    eid = _escribir_evento(sala, accion, "%s:%s" % (SOCIO, socio), sobre_socio(socio), **extra)
    if accion == "lapida":
        _purgar(sala["dir"])
    return eid


def accion_creador(sala_id, agente, accion, motivo="", brains=None, sesion=None, _sobre=None):
    """pausar / reanudar / cerrar / archivar desde el CLI: solo quien abrió."""
    yo = identidad(agente, brains, sesion, _sobre)
    if yo is None:
        raise Error("%s no tiene cerebro en esta máquina" % (agente or "?"))
    sala = encontrar(sala_id, yo["cerebros"])
    if sala is None:
        raise Error("no encuentro la sala %s" % sala_id)
    creador = yo["key"] == sala["creador"] or (yo["agente"] == sala["creador_agente"]
                                               and not sala["creador_sesion"])
    if not creador:
        raise Error("solo quien abrió la sala (%s) la puede %s; el socio, desde el hub"
                    % (nombre_de(sala, sala["creador"]), _VERBO.get(accion, accion)))
    if accion == "cierre" and sala["cerrada"]:
        raise Error("la sala ya está cerrada")
    if accion == "archivar" and not sala["cerrada"]:
        raise Error("primero ciérrala (cerrar), luego se archiva")
    if accion == "pausa" and (sala["pausada"] or sala["cerrada"]):
        raise Error("la sala ya está en pausa o cerrada")
    if accion == "reanudar" and not sala["pausada"]:
        raise Error("la sala no está en pausa")
    return _escribir_evento(sala, accion, yo["key"], yo["sobre"], yo["agente"], motivo=motivo)


_VERBO = {"pausa": "pausar", "reanudar": "reanudar", "cierre": "cerrar", "archivar": "archivar"}


#: Quién soltó un pedido sin que el agente lo pidiera: el decisor (C1 «solo
#: informa»). Lo pone el código en el campo `por` (firmado con el resto), nunca
#: el texto del motivo: un «◆» en el motivo lo puede escribir cualquiera.
POR_DECISOR = "decisor"


def soltar(sala_id, agente, pedido, motivo="", brains=None, sesion=None, _sobre=None, _por=""):
    yo = identidad(agente, brains, sesion, _sobre)
    if yo is None:
        raise Error("%s no tiene cerebro en esta máquina" % (agente or "?"))
    sala = encontrar(sala_id, yo["cerebros"])
    if sala is None:
        raise Error("no encuentro la sala %s" % sala_id)
    if not any(p["id"] == pedido for p in deudas_de(sala, yo["key"], yo["agente"])):
        raise Error("%s no es un pedido tuyo abierto en esta sala" % pedido)
    unirse(sala, yo)
    return _escribir_evento(sala, "soltar", yo["key"], yo["sobre"], yo["agente"], pedido=pedido,
                            motivo=motivo, por=POR_DECISOR if _por == POR_DECISOR else "")


def delegar(sala_id, agente, pedido, en, resumen="", brains=None, sesion=None, _sobre=None):
    yo = identidad(agente, brains, sesion, _sobre)
    if yo is None:
        raise Error("%s no tiene cerebro en esta máquina" % (agente or "?"))
    sala = encontrar(sala_id, yo["cerebros"])
    if sala is None:
        raise Error("no encuentro la sala %s" % sala_id)
    if not any(p["id"] == pedido for p in deudas_de(sala, yo["key"], yo["agente"])):
        raise Error("%s no es un pedido tuyo abierto en esta sala" % pedido)
    dest = _resolver_para(sala, yo, [en])
    if not dest:
        raise Error("--en: a quién le pasas el pedido (otro participante)")
    if dest[0] == sala["pedidos"][pedido]["de"]:
        raise Error("no se le pasa un pedido a quien lo hizo: respóndelo o suéltalo")
    unirse(sala, yo)
    return _escribir_evento(sala, "delegar", yo["key"], yo["sobre"], yo["agente"], pedido=pedido,
                            en=dest[0], motivo=resumen)


def _lapidas_validas(regs, carpeta):
    """Los archivos de las lápidas que SÍ borran: del socio (la regla de
    borrar, DE_SOCIO en _evento_valido), de ESTA sala y con la firma buena —
    «ok», o «remota» (dice venir de otra máquina: la clave no viaja y no se
    puede comprobar; así se propaga un borrado hecho allá — por eso una
    escrita a mano que dice venir de otra máquina SÍ cuenta). No borran: una
    de esta máquina sin firma, una alterada, una de un agente o una copiada
    de otra sala. Nunca por el nombre del archivo."""
    s0 = regs.get(SALA_MD) or {}
    sid = s0.get("sala") or os.path.basename(os.path.normpath(carpeta))
    vacia = {"creador": "", "creador_agente": "", "creador_sesion": ""}
    return [r["archivo"] for r in regs.values()
            if r["kind"] == "evento" and r.get("accion") == "lapida"
            and r.get("sala") == sid and r.get("firma") in ("ok", "remota")
            and _evento_valido(r, vacia, ())]


def _purgar(carpeta, regs=None):
    """Borrar = lápida + purga: se quita todo menos la lápida (también lo que
    el sync traiga después). La lápida se va sola a los LAPIDA_DIAS. Solo con
    una lápida VÁLIDA (_lapidas_validas; `regs` = lo ya leído, o se lee)."""
    try:
        nombres = os.listdir(carpeta)
    except OSError:
        return
    if regs is None:
        c = Almacen().leer(carpeta, _yo_maquina())
        regs = c["regs"] if c else {}
    lapidas = [n for n in _lapidas_validas(regs, carpeta) if n in nombres]
    if not lapidas:
        return
    for n in nombres:
        if n in lapidas or not (n == SALA_MD or _ARCH_RE.match(n)):
            continue
        try:
            os.remove(os.path.join(carpeta, n))
        except OSError:
            pass
    try:
        vieja = min(os.path.getmtime(os.path.join(carpeta, n)) for n in lapidas)
        if _ahora() - vieja > LAPIDA_DIAS * 86400:
            for n in lapidas:
                os.remove(os.path.join(carpeta, n))
            os.rmdir(carpeta)
    except OSError:
        pass


# ═══════════════════════════════════════════════════════════════════════════
# Presencia, nombres y salud del sync (para el CLI y el hub)
# ═══════════════════════════════════════════════════════════════════════════

def estado_participante(sala, token, ahora=None, brains=None, excluir=""):
    """{estado: escuchando|trabajando|cerrada|desconocido, de_verdad, visto}
    de un destino: SU pestaña (la clave dice cuál, aunque todavía no se haya
    unido). Si no se sabe qué pestaña va a contestar («?agente», o una sin id
    de pestaña) puede estar escuchando o trabajando, pero nunca «cerrada de
    verdad»: otra pestaña vieja y cerrada del agente no corta la espera. Una
    de otra máquina que solo lleva rato sin latir es «desconocido».
    `excluir` = una pestaña (id) que no cuenta: la mía, si el destino es
    otra pestaña de mi agente."""
    t = str(token or "")
    a = agente_de(t)
    bm = brains if isinstance(brains, dict) else M.registered_brains()
    brain = bm.get(a, "")
    if not brain:
        return {"estado": "desconocido", "de_verdad": False, "visto": None}
    p = sala["participantes"].get(t)
    ses = (p or {}).get("sesion") or (t.rsplit("--", 1)[1] if "--" in t and not p else "")
    if p:
        est = M.estado_lado(brain, a, ses, p["maquina"], p["pestana"], ahora=ahora,
                            excluir=excluir)
    elif ses:
        est = M.estado_lado(brain, a, ses, ahora=ahora, excluir=excluir)
    else:
        est = M.estado_lado(brain, a, ahora=ahora, excluir=excluir)
    if not ses or ses.startswith("sin-pestana-"):
        est = dict(est, de_verdad=False)
    if est.get("estado") == "cerrada" and not est.get("de_verdad"):
        est = dict(est, estado="desconocido")
    return est


def pestana_abierta(sala, token, brains=None, ahora=None):
    """¿El invitado `token` (clave o «?agente») tiene una pestaña abierta
    aunque todavía no entró a la sala? Su presencia (escucha o trabaja) o,
    en esta máquina, el registro de pestañas abiertas de su cerebro. Que no
    la tenga no se afirma: puede estar en otra máquina sin noticias."""
    est = estado_participante(sala, token, ahora, brains)
    if est.get("estado") in ("escuchando", "trabajando"):
        return True
    if not str(token).startswith("?"):
        return False
    bm = brains if isinstance(brains, dict) else M.registered_brains()
    brain = bm.get(agente_de(token), "")
    return bool(brain) and bool(M._abiertas(brain))


def _sin_entrar_txt(sala, token, brains=None, ahora=None):
    return ("su pestaña está abierta, aún no entra" if pestana_abierta(sala, token, brains, ahora)
            else "aún no se une")


def _estado_txt(est):
    return {"escuchando": "escuchando", "trabajando": "trabajando en su turno",
            "cerrada": "su pestaña está cerrada", "desconocido": "sin noticias"}.get(
        est.get("estado"), est.get("estado") or "?")


def nombre_de(sala, token):
    """Cómo se nombra a un destino en el CLI: «agente (Pestaña)»."""
    if es_socio(token):
        return "el socio"
    a = agente_de(token)
    p = sala["participantes"].get(token)
    if p and p.get("pestana"):
        return "%s (%s)" % (a, p["pestana"])
    return a or "?"


def salud_sync(sala, ahora=None, conocidas=None):
    """{"linea", "caido"}: si la sala depende de otra máquina y si su copia del
    cerebro está llegando. «solo esta Mac» · «PC: lo último llegó hace 3 min»
    (que no haya mandado nada nuevo no es una falla) · «PC sin sincronizar
    desde 14:02» (caído: va en rojo arriba)."""
    ahora = ahora or _ahora()
    yo = M.mi_maquina()
    conocidas = M.maquinas_conocidas() if conocidas is None else conocidas
    mias = yo.get("alias") or set()
    otras = {}
    for p in sala["participantes"].values():
        eti = M._etiqueta(p.get("maquina"))
        if eti and eti not in mias and p.get("unido"):
            otras.setdefault(eti, 0.0)
    for m in sala["mensajes"]:
        eti = M._etiqueta(m.get("de_maquina"))
        if eti in otras:
            otras[eti] = max(otras[eti], m["t"])
    aqui = M.nombre_maquina(yo.get("etiqueta"), conocidas) or "máquina"
    if not otras:
        return {"linea": "solo esta %s" % aqui, "caido": False}
    est = _estado_maquinas(sala["hogar"])
    partes, caido = [], False
    for eti, t in sorted(otras.items()):
        nom = M.nombre_maquina(eti, conocidas) or eti
        e = next((x for x in est[1:] if M._etiqueta(x.get("etiqueta")) == eti), None)
        visto = t
        if e and e.get("visto"):
            visto = max(visto, M._ts_epoch(e.get("visto")) or 0.0)
        if e and e.get("desfasada"):
            caido = True
            partes.append("%s sin sincronizar desde %s" % (nom, _hora(visto) if visto else "?"))
        elif visto:
            partes.append("%s: lo último llegó %s" % (nom, _hace(ahora - visto)))
        else:
            partes.append("%s sin datos todavía" % nom)
    return {"linea": " · ".join(partes), "caido": caido}


_MAQUINAS = {}       # cerebro → (hora, estado): maquinas.estado lee constancias; 30 s basta


def _estado_maquinas(hogar):
    hit = _MAQUINAS.get(hogar)
    if hit is not None and time.monotonic() - hit[0] < 30:
        return hit[1]
    try:
        import maquinas
        est = maquinas.estado(hogar, sondear=False)
    except Exception:
        est = []
    _MAQUINAS[hogar] = (time.monotonic(), est)
    return est


def _hace(seg):
    seg = max(0, int(seg))
    if seg < 60:
        return "hace %d s" % seg
    if seg < 3600:
        return "hace %d min" % (seg // 60)
    if seg < 86400:
        return "hace %d h" % (seg // 3600)
    return "hace %d d" % (seg // 86400)


# ═══════════════════════════════════════════════════════════════════════════
# Entrega: qué le toca a esta pestaña, cursor local, esperar
# ═══════════════════════════════════════════════════════════════════════════

def _ruta_cursor(key):
    import paths
    nombre = re.sub(r"[^A-Za-z0-9._-]", "_", key)[:120] or "pestana"
    return os.path.join(paths.state_dir(), "salas", "cursor", nombre + ".json")


def _ruta_cursor_cerebro(key, brain):
    """El cursor de la pestaña DENTRO de su cerebro, para cuando el estado
    per-máquina no se escribe (el sandbox de Codex `-s workspace-write`, el
    de toda pestaña real de Codex): <cerebro>/.claude/estado-salas/<máquina>/
    (Obsidian no sube `.claude/`; por máquina: cada una lleva el suyo)."""
    nombre = re.sub(r"[^A-Za-z0-9._-]", "_", key)[:120] or "pestana"
    yo = M.mi_maquina()
    maq = re.sub(r"[^A-Za-z0-9._-]", "_", str(yo.get("id") or yo.get("etiqueta") or ""))[:60]
    return os.path.join(brain, ".claude", "estado-salas", maq or "maquina", nombre + ".json")


def _brain_de(key, brain=None):
    if brain:
        return brain
    try:
        return M.registered_brains().get(agente_de(key)) or ""
    except Exception:
        return ""


def _rutas_cursor(key, brain=None):
    """(donde se escribe, la otra): en el sandbox, la del cerebro; si no, la
    del estado. Se LEEN las dos (pasar de una pestaña con sandbox a una sin
    él, o al revés, no vuelve a entregar nada)."""
    estado = _ruta_cursor(key)
    b = _brain_de(key, brain)
    if not b:
        return estado, ""
    cerebro = _ruta_cursor_cerebro(key, b)
    return (cerebro, estado) if _estado_no_escribible() else (estado, cerebro)


def _escribir_estado(ruta, texto):
    """Como atomico.escribir; en el sandbox (olock.sin_estado) un archivo que
    ya existe se reescribe EN EL LUGAR (la regla de olock: lo que el sandbox
    CREA en el cerebro puede quedar con sus permisos)."""
    import atomico
    if _estado_no_escribible() and os.path.isfile(ruta):
        with open(ruta, "r+", encoding="utf-8", newline="\n") as fh:
            fh.seek(0)
            fh.write(texto)
            fh.truncate()
            fh.flush()
            os.fsync(fh.fileno())
        return
    atomico.escribir(ruta, texto)


#: Lo entregado en ESTE proceso cuando ni el estado ni el cerebro se pueden
#: escribir: una sola entrega por proceso (nunca un loop), con aviso.
_EN_MEMORIA = {}


def _leer_json_estado(ruta):
    """(datos, estado) de un JSON de estado local: «ok», «no_existe»,
    «ilegible» (el contenido está dañado: no es JSON, no es UTF-8 o no es un
    objeto) o «transitorio» (no se pudo LEER: el antivirus lo tiene abierto,
    demasiados archivos abiertos… — no se aparta: se reintenta). Con BOM se
    lee (utf-8-sig). Ilegible NO es lo mismo que vacío: quien lo lee decide
    (_apartar)."""
    for intento in range(3):          # un transitorio breve (antivirus) se reintenta aquí mismo
        try:
            with open(ruta, encoding="utf-8-sig") as fh:
                d = json.load(fh)
        except FileNotFoundError:
            return None, "no_existe"
        except (ValueError, UnicodeDecodeError):     # JSONDecodeError es ValueError
            return None, "ilegible"
        except OSError as e:
            _ERRORES_LECTURA[ruta] = "%s: %s" % (type(e).__name__, e)
            if intento < 2:
                time.sleep(0.05 * (intento + 1))
            continue
        _ERRORES_LECTURA.pop(ruta, None)
        return (d, "ok") if isinstance(d, dict) else (None, "ilegible")
    return None, "transitorio"


#: El último error de lectura de cada estado que no se pudo leer (para avisar).
_ERRORES_LECTURA = {}


def _apartar(ruta):
    """Un estado ilegible se aparta (no se pisa ni se borra):
    <ruta>.ilegible-<fecha>. → la ruta nueva, o '' si no se pudo (entonces
    quien escribe NO escribe: SinApartar, y se reintenta en otra vuelta)."""
    dest = "%s.ilegible-%s" % (ruta, time.strftime("%y%m%dT%H%M%S"))
    try:
        os.replace(ruta, dest)
        return dest
    except OSError:
        return ""


def _apartado_de(ruta):
    """El último <ruta>.ilegible-* que quedó, o ''. Sin el archivo y CON un
    apartado = recuperación (se apartó y el nuevo no llegó a guardarse): lo de
    ahora cuenta como visto; no es la primera vez. La señal sobrevive entre
    procesos hasta que el estado nuevo queda guardado."""
    import glob
    xs = sorted(glob.glob(glob.escape(ruta) + ".ilegible-*"))
    return xs[-1] if xs else ""


class SinApartar(Exception):
    """El estado ilegible no se pudo apartar: ni se pisa ni se entrega."""


class EstadoTransitorio(Exception):
    """El estado no se pudo leer ahora (no está dañado): otra vuelta."""


class SinEstado(Exception):
    """Este proceso no puede escribir el estado per-máquina (el sandbox de un
    motor: olock.sin_estado). Permanente, no «candado ocupado»."""


def _estado_no_escribible():
    try:
        import olock
        return bool(olock.sin_estado())
    except Exception:
        return False


def cursor(key, brain=None):
    """{"ids": {sala: [ids entregados]}, "avisos": [claves]} — local, no viaja.
    Ilegible: vacío con "ilegible": True (lo aparta _marcar, bajo candado).
    Junta lo de la otra ubicación (estado / cerebro: _rutas_cursor)."""
    ruta, otra = _rutas_cursor(key, brain)
    c = _cursor_de(ruta)
    if otra:
        d, est = _leer_json_estado(otra)
        if est == "ok":
            o = _cursor_de_datos(d)
            for sid, ids in o["ids"].items():
                lst = c["ids"].setdefault(sid, [])
                lst += [x for x in ids if x not in lst]
            c["avisos"] += [x for x in o["avisos"] if x not in c["avisos"]]
    return c


def _cursor_de_datos(d):
    try:
        ids = d.get("ids") if isinstance(d.get("ids"), dict) else {}
        av = d.get("avisos") if isinstance(d.get("avisos"), list) else []
        return {"ids": {str(k): [str(x) for x in v] for k, v in ids.items() if isinstance(v, list)},
                "avisos": [str(x) for x in av]}
    except Exception:
        return {"ids": {}, "avisos": [], "ilegible": True}


def _cursor_de(ruta):
    d, est = _leer_json_estado(ruta)
    if est == "ilegible":
        return {"ids": {}, "avisos": [], "ilegible": True}
    if est == "transitorio":
        return {"ids": {}, "avisos": [], "transitorio": True}
    if est != "ok":
        return dict({"ids": {}, "avisos": []}, **({"recuperar": True} if _apartado_de(ruta) else {}))
    return _cursor_de_datos(d)


#: Cuánto se espera un candado de estado local (cursor, avisos, delicados):
#: más que el peor caso de atomico.reemplazar en Windows (INTENTOS_WINDOWS
#: con 0.05·k ≈ 10.5 s con el antivirus o el indexador encima).
CANDADO_S = 12


def _bajo_candado(ruta, fn, timeout=CANDADO_S):
    """(True, fn()) bajo el candado de `ruta`; (False, None) si el candado no
    se consigue (ocupado, o no se pudo crear): fn NO corre — sin candado no
    se entrega ni se escribe, se reintenta en la siguiente vuelta. Solo si de
    verdad no hay candado (olock no está, o file_lock None) corre sin él.
    Lo que levante fn, sube."""
    try:
        import olock
        fl = olock.file_lock
    except ImportError:
        fl = None
    if fl is None:
        return True, fn()
    try:
        lk = fl(olock.ruta_candado(ruta), timeout=timeout)
        lk.__enter__()
    except Exception as e:
        # ocupado o vencido (LockTimeout): transitorio. Sin poder crear el
        # candado porque el estado no se escribe (sandbox): permanente
        if not isinstance(e, TimeoutError) and isinstance(e, OSError) and _estado_no_escribible():
            raise SinEstado(ruta)
        return False, None
    try:
        return True, fn()
    finally:
        try:
            lk.__exit__(None, None, None)
        except Exception:
            pass


def _marcar(key, entregados=(), avisos=(), _apartado=None, _todo=None, _sin_estado=None,
            brain=None):
    """Suma ids y avisos al cursor de la pestaña y devuelve SOLO los que no
    estaban: ([(sala, id)], [aviso]). Leer y marcar van bajo el mismo
    candado, así dos `esperar` de la misma pestaña (uno en segundo plano y
    otro en primer plano) nunca entregan lo mismo dos veces. Sin candado, o
    si el guardado falla, nada es nuevo: se entrega en la siguiente vuelta.
    Cursor ilegible: se aparta (`_apartado` recibe dónde) y el nuevo empieza
    con TODO lo de ahora ya visto (`_todo()`, releído bajo el candado, más lo
    que se pasó) — nada se devuelve como nuevo (no se repite). Lectura
    transitoria (antivirus…): nada nuevo, otra vuelta. Estado no escribible
    (sandbox, permanente): lo nuevo contra el cursor, sin guardarlo — puede
    repetirse; `_sin_estado` lo anota para avisarlo."""
    ruta = _rutas_cursor(key, brain)[0]   # en el sandbox, la del cerebro
    res = ([], [])
    if ruta != _ruta_cursor(key):
        # su carpeta ANTES del candado: olock ubica el candado en el `.claude/`
        # más cercano y, si el cerebro aún no tiene uno, subía hasta el del HOME
        # real, que el sandbox no deja escribir (el candado vencía: 3, 3, 3)
        try:
            os.makedirs(os.path.dirname(ruta), exist_ok=True)
        except OSError:
            pass

    def _hacer(guardar=True):
        c = cursor(key, brain)
        if c.pop("transitorio", False):
            raise EstadoTransitorio(ruta)
        ilegible = bool(c.pop("ilegible", False))
        sembrar = guardar and (ilegible or bool(c.pop("recuperar", False)))
        c.pop("recuperar", None)
        if ilegible and guardar:
            dest = _apartar(ruta)
            if not dest:                 # sin apartarlo no se pisa ni se entrega: otra vuelta
                raise SinApartar(ruta)
            if _apartado is not None:
                _apartado.append(dest)
        if sembrar and _todo is not None:            # todo lo de ahora, no solo lo que llegó
            for sid, mid in _todo():
                lst = c["ids"].setdefault(sid, [])
                if mid not in lst:
                    lst.append(mid)
        del res[0][:], res[1][:]
        for sid, mid in entregados:
            lst = c["ids"].setdefault(sid, [])
            if mid not in lst:
                lst.append(mid)
                if not sembrar:
                    res[0].append((sid, mid))
        for a in avisos:
            if a not in c["avisos"]:
                c["avisos"].append(a)
                if not sembrar:
                    res[1].append(a)
        c["avisos"] = c["avisos"][-500:]
        if guardar and (res[0] or res[1] or sembrar):
            _escribir_estado(ruta, json.dumps({"version": 1, "ids": c["ids"],
                                                "avisos": c["avisos"]}, ensure_ascii=False) + "\n")
    try:
        hecho, _x = _bajo_candado(ruta, _hacer)
    except (SinEstado, OSError) as e:    # sin poder escribir el estado (sandbox): permanente
        if not isinstance(e, SinEstado) and (isinstance(e, TimeoutError)
                                             or not _estado_no_escribible()):
            return ([], [])              # transitorio (WinError 32…): otra vuelta
        try:                             # ni el estado ni el cerebro: una sola entrega por proceso
            _hacer(guardar=False)
        except Exception:
            return ([], [])
        mem = _EN_MEMORIA.setdefault(key, set())
        nuevos = ([x for x in res[0] if x not in mem],
                  [a for a in res[1] if ("aviso", a) not in mem])
        mem.update(res[0])
        mem.update(("aviso", a) for a in res[1])
        if _sin_estado is not None and (nuevos[0] or nuevos[1]):
            _sin_estado.append(ruta)
        return nuevos
    except Exception:                    # no se guardó: no se puede contar como entregado
        hecho = False
    return res if hecho else ([], [])


def para_mi(sala, yo):
    """Lo que esta pestaña tiene que recibir de la sala (sin mirar el cursor):
    [(id, registro, nota)]. Pedidos que me toca responder (uno que me
    pasaron, con el id del evento `delegar`), respuestas, soltados y pases de
    MIS pedidos, cancelaciones de lo que yo debía o pedí y los eventos de
    control (pausa y reanudar desde que llegué; el cierre). En pausa se
    retienen los mensajes. Cerrada la sala no se entregan pedidos nuevos, pero
    sí lo de mis pedidos que pasó ANTES del cierre, y el cierre (también a
    quien cerró: así termina el `esperar` que dejó en segundo plano)."""
    key, out = yo["key"], []
    if sala["borrada"]:
        return out
    yo_p = sala["participantes"].get(key)
    soy_parte = (yo_p is not None) or any(key in p["a"] for p in sala["pedidos"].values())
    cerrada = sala["cerrada"]
    t_cierre = sala["cierre"]["t"] if sala["cierre"] else None
    retenido = sala["pausada"] and not cerrada

    def antes_del_cierre(r):
        return not cerrada or t_cierre is None or r["t"] <= t_cierre
    if not cerrada:
        for e in sala["eventos"]:                   # pausa/reanudar: solo desde que llegué
            if (e["valido"] and e["accion"] in ("pausa", "reanudar") and e["de"] != key
                    and yo_p is not None and yo_p["unido"] and e["t"] >= yo_p["desde"]):
                out.append((e["id"], e, e["accion"]))
    for m in sala["mensajes"]:
        p = sala["pedidos"].get(m["id"])
        if (p is not None and m["de"] != key and p["estado"] == "esperando"
                and key in p["pendientes"] and not retenido):
            dl = p["delegados"].get(key)
            if dl:
                out.append((dl["evento"], m, "delegado:" + dl["de"]))
            else:
                out.append((m["id"], m, "pide"))
        if m["tipo"] == "responde" and m["entregable"] and m["de"] != key and not retenido:
            ped = sala["pedidos"].get(m.get("en_respuesta_a"))
            if ped is not None and ped["de"] == key and antes_del_cierre(m):
                out.append((m["id"], m, "responde"))
    for e in sala["eventos"]:
        if not e["valido"] or e["de"] == key or not antes_del_cierre(e):
            continue
        p = sala["pedidos"].get(e.get("pedido"))
        if p is None:
            continue
        if e["accion"] in ("soltar", "delegar") and p["de"] == key:
            # también lo que soltó el decisor (campo `por`): quien pidió se entera
            out.append((e["id"], e, e["accion"]))
        elif e["accion"] == "cancelar" and (p["de"] == key or key in p.get("cancelados", ())):
            out.append((e["id"], e, "cancelar"))
    if cerrada and soy_parte:
        c = sala["cierre"] or next((e for e in sala["eventos"] if e["valido"]
                                    and e["accion"] == "archivar"), None)
        if c is not None:             # también a quien cerró: su `esperar` de fondo termina
            out.append((c["id"], c, "cierre"))
    out.sort(key=lambda x: (x[1]["t"], x[0]))
    return out


def _reclamables(sala, yo):
    """¿Hay un pedido para mi agente sin pestaña todavía que esta pestaña
    puede tomar? No si ya participo, ni si el cerebro es compartido y la sala
    es de otro socio (filtro por dueño)."""
    if yo["key"] in sala["participantes"] and sala["participantes"][yo["key"]]["unido"]:
        return False
    if sala["cerrada"] or sala["pausada"] or yo["agente"] not in sala["permitidos"]:
        return False
    if (_mismo(sala["hogar"], yo["brain"]) and sala["dueno"] and yo["socio"]
            and sala["dueno"] != yo["socio"]):
        return False
    return any(p["estado"] == "esperando" and ("?" + yo["agente"]) in p["pendientes"]
               for p in sala["pedidos"].values())


def _mismo(a, b):
    try:
        return os.path.normcase(os.path.realpath(a)) == os.path.normcase(os.path.realpath(b))
    except Exception:
        return False


def _avisos(salas_, yo, ahora, brains):
    """[(clave, texto)] de 4: un pedido MÍO venció, o quien me debe respuesta
    está cerrado DE VERDAD desde hace GRACIA_CERRADO_MIN."""
    out = []
    for s in salas_:
        for p in s["pedidos"].values():
            if p["de"] != yo["key"] or p["estado"] != "esperando":
                continue
            if ahora >= p["vence"]:
                out.append(("%s:%s:vencido:%d" % (s["id"], p["id"], int(p["vence"])),
                            "venció tu pedido %s en «%s» (espera %s): no contestaron %s"
                            % (p["id"], s["titulo"], espera_txt(p["espera"] + p["mas"]),
                               ", ".join(nombre_de(s, d) for d in p["pendientes"]))))
                continue
            for d in p["pendientes"]:
                est = estado_participante(s, d, ahora, brains)
                if est.get("estado") != "cerrada" or not est.get("de_verdad"):
                    continue
                ref = max([x for x in (est.get("visto"), p["t"]) if x] or [ahora])
                if ahora - ref >= GRACIA_CERRADO_MIN * 60:
                    out.append(("%s:%s:cerrado:%s" % (s["id"], p["id"], d),
                                "%s no está (su pestaña lleva %d min o más cerrada) y te debe "
                                "%s en «%s»" % (nombre_de(s, d), GRACIA_CERRADO_MIN, p["id"],
                                                s["titulo"])))
    return out


#: Cuántos mensajes de «mientras tanto» viajan en un despertar (los más
#: nuevos); el resto, con `conversar ver <sala>`.
CONTEXTO_MAX = 8


def contexto(sala, yo, vistos=(), entregados=()):
    """«Todos leen»: los mensajes de la sala que esta pestaña no ha visto y
    que no la despiertan (un `info`, pedidos y respuestas entre otros) →
    [(id, registro, para_ti)]. `para_ti` = el mensaje la menciona (un `info
    --para` mí: no despierta, pero se marca). Sin los míos ni los que no se
    entregan (tope, alterado, después del cierre)."""
    key, ag = yo["key"], yo["agente"]
    ya = set(vistos) | set(entregados) | _retenidos(sala, yo)
    out = []
    for m in sala["mensajes"]:
        if m["id"] in ya or m["de"] == key or not m["entregable"]:
            continue
        out.append((m["id"], m, key in m["destinos"] or ("?" + ag) in m["destinos"]))
    return out


def _retenidos(sala, yo):
    """Con la sala en pausa: los ids que `para_mi` retiene para esta pestaña
    (un `pide` que me debe y un `responde` a un pedido mío). No van en «Mientras
    tanto»: si fueran, quedarían vistos en el cursor y tras «reanudar» nunca
    llegarían como lo que son, con su deuda (revisión fría, hallazgo 1)."""
    if not sala["pausada"] or sala["cerrada"]:
        return set()
    key, out = yo["key"], set()
    for m in sala["mensajes"]:
        if m["de"] == key:
            continue
        p = sala["pedidos"].get(m["id"])
        if p is not None and p["estado"] == "esperando" and key in p["pendientes"]:
            out.add(m["id"])
        if m["tipo"] == "responde" and m["entregable"]:
            ped = sala["pedidos"].get(m.get("en_respuesta_a"))
            if ped is not None and ped["de"] == key:
                out.add(m["id"])
    return out


class Resultado(list):
    """Lo que devuelve esperar: la lista de entregas [(sala, id, registro,
    nota)] y `codigo` (0 llegó · 3 nada · 4 aviso) con `avisos` (textos).
    `contexto` = {sala: [(id, registro, para_ti)]}: lo que pasó en las salas
    de este despertar y no despertaba a nadie aquí (se marca visto, no se
    repite). `primera` = las salas que esta pestaña recibe por primera vez:
    su contrato va arriba."""

    def __init__(self, items=(), codigo=0, avisos=(), contexto=None, primera=()):
        super().__init__(items)
        self.codigo, self.avisos = codigo, list(avisos)
        self.contexto = dict(contexto or {})
        self.primera = set(primera)
        self.notas = {}                  # Decisores: {(sala, id | ""): [líneas ◆]}


def _mis_salas(yo, sala_id, almacen):
    if sala_id:
        s = encontrar(sala_id, yo["cerebros"], almacen)
        return [s] if s is not None else []
    return todas(yo["cerebros"], almacen, archivadas=False, recientes=True)


def esperar(agente, sala=None, timeout=ESPERAR_TIMEOUT, intervalo=ESPERAR_INTERVALO,
            brains=None, sesion=None, asiento=None, _sobre=None, _reloj=time.monotonic,
            _dormir=time.sleep):
    """Bloquea hasta que llegue algo para esta pestaña (en `sala` o en
    todas). Resultado con código 0 (llegó), 3 (nada en `timeout`; 0 = mirar
    una vez) o 4 (un pedido mío venció, o quien me debe está cerrado de
    verdad). None si el agente no tiene cerebro aquí; [] con código 1 si la
    sala no existe. Lo entregado queda en el cursor local: no se repite.

    «Todos leen»: cuando algo me despierta, trae también lo que no vi de esa
    sala (Resultado.contexto). Un `info --para` mí no despierta, pero va en
    ese bloque marcado «para ti»; con `timeout` 0 (mirar una vez) sí sale
    aunque nada más haya llegado."""
    yo = identidad(agente, brains, sesion, _sobre)
    if yo is None:
        return None
    al = Almacen()
    if sala and encontrar(sala, yo["cerebros"], al) is None:
        return Resultado((), 1)
    fin = _reloj() + max(0.0, float(timeout or 0))
    mirar_una_vez = float(timeout or 0) <= 0
    paso = max(0.05, float(intervalo or ESPERAR_INTERVALO))
    espera_asiento = None if asiento is None else max(0.0, float(asiento))
    desde = M._ahora_epoch()
    hilos = [sala] if sala else []
    M.latir(yo["brain"], yo["agente"], True, hilos, "", desde, yo["sesion"])
    ult_latido, ult_aviso = _reloj(), None
    trans_n = 0
    try:
        while True:
            ss = _mis_salas(yo, sala, al)
            if sala and (not ss or ss[0]["borrada"]):      # se borró mientras esperaba
                return Resultado((), SALIDA_AVISO, ["la sala %s se borró: deja de esperarla y "
                                                    "díselo al socio" % sala])
            ss = [_reclamar(s, yo, espera_asiento, paso, _reloj, _dormir, al)
                  if _reclamables(s, yo) else s for s in ss]
            cur = cursor(yo["key"], yo["brain"])
            if cur.get("transitorio"):      # no se pudo leer (ya reintentado): esta vuelta, nada
                trans_n += 1
                if mirar_una_vez or trans_n >= 3:    # y si no se arregla, se dice
                    return Resultado((), SALIDA_AVISO, [_aviso_ilegible(yo)])
            else:
                trans_n = 0
            ss_v = [] if cur.get("transitorio") else ss
            items = []
            for s in ss_v:
                ya = set(cur["ids"].get(s["id"], ()))
                items += [(s, i, r, n) for i, r, n in para_mi(s, yo) if i not in ya]
            items, notas = decidir_entregas(items, yo)          # Decisores (apagado: igual)
            con_algo = {s["id"] for s, _i, _r, _n in items}
            ctx = {}
            for s in ss_v:                  # solo salas donde estoy (o a las que me llaman)
                yo_p = s["participantes"].get(yo["key"])
                if s["id"] not in con_algo and not (yo_p and yo_p["unido"]):
                    continue
                c = contexto(s, yo, cur["ids"].get(s["id"], ()),
                             [i for x, i, _r, _n in items if x is s])
                if c and (s["id"] in con_algo or (mirar_una_vez and any(t for _i, _r, t in c))):
                    ctx[s["id"]] = c
            apartado, sin_est = [], []

            def todo():                     # recuperación: todo lo de ahora cuenta como visto
                return [(s["id"], r["id"]) for s in ss
                        for r in list(s["mensajes"]) + list(s["eventos"])]
            if items or ctx:
                nuevos, _a = _marcar(yo["key"], [(s["id"], i) for s, i, _r, _n in items]
                                     + [(sid, i) for sid, c in ctx.items() for i, _r, _t in c],
                                     _apartado=apartado, _todo=todo, _sin_estado=sin_est,
                                     brain=yo["brain"])
                if apartado:
                    return Resultado((), SALIDA_AVISO, [_aviso_cursor(apartado[0])])
                nuevos = set(nuevos)
                items = [it for it in items if (it[0]["id"], it[1]) in nuevos]
                ctx = {sid: [x for x in c if (sid, x[0]) in nuevos] for sid, c in ctx.items()}
                ctx = {sid: c for sid, c in ctx.items() if c}
            if items or ctx:                # (otro `esperar` de esta pestaña pudo tomarlos)
                for s, _i, _r, _n in items:
                    p = s["participantes"].get(yo["key"])
                    if not s["cerrada"] and (p is None or not p["unido"]):
                        unirse(s, yo)
                primera = {sid for sid in con_algo | set(ctx) if not cur["ids"].get(sid)}
                res = Resultado(items, 0, [AVISO_SIN_ESTADO] if sin_est else (), contexto=ctx,
                                primera=primera)
                res.notas = notas
                return res
            if ult_aviso is None or _reloj() - ult_aviso >= min(M.LATIDO_S, 10.0):
                ult_aviso = _reloj()
                av = [(k, t) for k, t in _avisos(ss, yo, _ahora(), yo["cerebros"])
                      if k not in cur["avisos"]]
                if sala and ss and ss[0]["archivada"]:
                    av.append(("%s:archivada" % sala, "la sala %s está archivada: ya no se habla "
                                                     "en ella" % sala))
                if av:
                    _n, nuevos = _marcar(yo["key"], avisos=[k for k, _t in av],
                                         _apartado=apartado, _todo=todo, _sin_estado=sin_est,
                                         brain=yo["brain"])
                    av = [(k, t) for k, t in av if k in nuevos]
                    if av and sin_est:
                        av.append(("", AVISO_SIN_ESTADO))
                    if apartado:
                        return Resultado((), SALIDA_AVISO, [_aviso_cursor(apartado[0])])
                if av:
                    return Resultado((), SALIDA_AVISO, [t for _k, t in av])
            resta = fin - _reloj()
            if resta <= 0:
                return Resultado((), SALIDA_NADA)
            if _reloj() - ult_latido >= M.LATIDO_S:
                M.latir(yo["brain"], yo["agente"], True, hilos, "", desde, yo["sesion"])
                ult_latido = _reloj()
            _dormir(min(paso, resta))
    finally:
        M.latir(yo["brain"], yo["agente"], False, hilos, "", desde, yo["sesion"])


#: Lo que dice `esperar` cuando el estado no se puede escribir (el sandbox de
#: un motor): entrega igual, pero no puede recordar lo entregado.
AVISO_SIN_ESTADO = ("no puedo guardar lo que ya te entregué (ni el estado de Workspace ni tu "
                    "cerebro se pueden escribir): en otra llamada a esperar puede repetirse — no "
                    "lo atiendas dos veces y avísale al socio")


def _aviso_ilegible(yo):
    ruta = _rutas_cursor(yo["key"], yo.get("brain"))[0]
    return ("no puedo leer tu registro de lo ya entregado (%s · %s): no te entrego nada hasta "
            "poder leerlo, para no repetirte lo de antes. Avísale al socio"
            % (ruta, _ERRORES_LECTURA.get(ruta) or "error de lectura"))


def _aviso_cursor(ruta):
    return ("tu registro de lo ya entregado estaba dañado: lo aparté en %s y no te repito lo de "
            "antes. Mira tus salas con %s ver <sala> y avísale al socio" % (ruta, _cmd()))


def asiento_de(hogar, agente, brain="", ahora=None):
    """Cuántos segundos espera un reclamo a que lleguen las uniones de otras
    máquinas, según la salud del sync que ya mide maquinas.py:
      · el cerebro no está en otra máquina → 0;
      · otra máquina sincroniza el hogar de la sala (no está desfasada ni su
        Obsidian cerrado) y `agente` tiene allá una pestaña viva (su
        presencia en su cerebro `brain`, sin «cerrada», vista hace menos de
        VIVA_S) → ASIENTO_SYNC_S, por encima del viaje medido;
      · si no → ASIENTO_PISO_S (nadie de ese agente puede ganarlo allá
        ahora; queda el caso de una pestaña recién abierta allá cuya
        presencia aún no llega, y entonces quien pierde se entera al
        responder).
    Si maquinas.py falla, como antes: sin otras máquinas conocidas → 0."""
    ahora = _ahora() if ahora is None else ahora
    alias = M.mi_maquina().get("alias") or set()
    try:
        import maquinas
        otras = [e for e in maquinas.estado(hogar, sondear=False)
                 if not e.get("yo") and not e.get("retirada") and not e.get("anterior")
                 and M._etiqueta(e.get("etiqueta")) not in alias]
    except Exception:
        return 0.0
    if not otras:
        return 0.0
    vivas = {M._etiqueta(e.get("etiqueta")) for e in otras
             if not e.get("desfasada") and e.get("obsidian_abierto") is not False}
    if not vivas:
        return ASIENTO_PISO_S
    for r in M.presencias(brain or hogar, agente):
        if (M._etiqueta(r.get("maquina")) in vivas and not r.get("cerrada")
                and ahora - float(r.get("visto") or 0) <= M.VIVA_S):
            return ASIENTO_SYNC_S
    return ASIENTO_PISO_S


def _reclamar(sala, yo, asiento, paso, _reloj, _dormir, al):
    """Tomar un pedido hecho a mi agente cuando todavía no hay pestaña suya en
    la sala: me uno (bajo candado) y, si el cerebro está también en otra
    máquina, espero el asiento (`asiento`, o el de la salud del sync:
    asiento_de) a que lleguen sus uniones. El nombre va a la primera que se
    unió: si no fui yo, el pedido no es mío."""
    if not unirse(sala, yo):
        return sala
    s = cargar(sala["dir"], sala["hogar"], al) or sala
    if asiento is None:
        asiento = asiento_de(sala["hogar"], yo["agente"], yo["brain"])
    if asiento > 0:
        fin = _reloj() + asiento
        while _reloj() < fin:
            _dormir(min(paso, max(0.0, fin - _reloj())))
        s = cargar(sala["dir"], sala["hogar"], al) or s
    return s


def pendientes(agente, brains=None, sesion=None):
    """Para el aviso al arrancar: [(sala, [(id, registro, nota)])] con lo que
    esta pestaña debe (pedidos abiertos para ella o para su agente sin
    pestaña) y lo que le llegó sin entregar (respuestas a sus pedidos,
    cierres…). Sin el filtro del cursor para las deudas: tras compactar, el
    agente perdió el contexto y las tiene que ver otra vez."""
    yo = identidad(agente, brains, sesion)
    if yo is None:
        return []
    out = []
    cur = cursor(yo["key"], yo["brain"])
    for s in todas(yo["cerebros"], Almacen(), archivadas=False, recientes=True):
        ya = set(cur["ids"].get(s["id"], ()))
        lst = []
        for i, r, n in para_mi(s, yo):
            if n == "cierre" and r["de"] == yo["key"]:
                continue                              # lo cerré yo: no es un aviso para mí
            if n == "pide" or n.startswith("delegado:") or i not in ya:
                lst.append((i, r, n))
        if _reclamables(s, yo):                       # invitado, sin pestaña mía aún
            lst += [(m["id"], m, "invitacion") for m in s["mensajes"]
                    if ("?" + yo["agente"]) in (s["pedidos"].get(m["id"]) or {}).get("pendientes", ())]
        if lst:
            out.append((s, lst))
    out.sort(key=lambda x: max(r["t"] for _i, r, _n in x[1]), reverse=True)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Decisores › Conversaciones (deliverables/…/Decisores_en_Conversaciones_v3.md)
# ═══════════════════════════════════════════════════════════════════════════
# Con Decisores apagado nada de esto corre y todo sale byte a byte igual.
# Encendido solo puede CALLAR un despertar inútil (C1), PAUSAR una sala en
# bucle (C2) o SUGERIR cerrar (C3); Seguridad solo SUBE un mensaje a
# «⚠ delicado». Al decisor viajan título, objetivo, «hecho cuando» y los
# RESÚMENES (no los cuerpos); solo Seguridad ve el cuerpo, recortado, sin
# prosa entre comillas y con los secretos tapados (security_guidance).

DECISOR = "workspace.conversations"
#: C2 corre en el `esperar` de quien abrió cada tantos mensajes nuevos.
C2_CADA = 6
#: Un pedido con su espera de 15 min o menos es urgente: C1 nunca lo calla.
URGENTE_MIN = 15
#: El cuerpo que ve Seguridad (como el hook de código).
SEGURIDAD_CUERPO = 1500


def _decisiones():
    try:
        import decisions
        return decisions
    except Exception:
        return None


def decisor_encendido(punto=DECISOR):
    """¿Ese uso pregunta? (barato: lee los ajustes). False sin Decisores."""
    D = _decisiones()
    try:
        return bool(D and D.enabled(punto))
    except Exception:
        return False


def _nombre_ag(sala, token):
    return "el socio" if es_socio(token) else (agente_de(token) or "?")


def _para_txt(sala, m):
    return ", ".join(_nombre_ag(sala, d) for d in m.get("destinos") or ()) or "todos"


def contexto_c1(sala, m):
    """C1: ¿el pedido pide algo? Título, objetivo y el resumen del pedido."""
    return "Sala: %s\nObjetivo: %s\nPedido %s %s: %s" % (
        sala["titulo"], sala["objetivo"], _prep("de", _nombre_ag(sala, m["de"])),
        _prep("a", _para_txt(sala, m)),
        m.get("resumen") or _linea(m.get("cuerpo"), 200, 1))


def contexto_c2(sala, msgs):
    """C2: ¿la sala avanza? El contrato y los últimos mensajes (resúmenes)."""
    filas = ["%s → %s (%s): %s" % (_nombre_ag(sala, m["de"]), _para_txt(sala, m), m["tipo"],
                                   m.get("resumen") or _linea(m.get("cuerpo"), 200, 1))
             for m in msgs]
    return "Sala: %s\nObjetivo: %s\nHecho cuando: %s\nÚltimos mensajes:\n%s" % (
        sala["titulo"], sala["objetivo"], sala["hecho_cuando"] or sala["objetivo"], "\n".join(filas))


def contexto_c3(sala, m):
    """C3: ¿se cumplió el «hecho cuando»? Con la respuesta que llegó."""
    return "Sala: %s\nHecho cuando: %s\nRespuesta %s: %s" % (
        sala["titulo"], sala["hecho_cuando"] or sala["objetivo"],
        _prep("de", _nombre_ag(sala, m["de"])),
        m.get("resumen") or _linea(m.get("cuerpo"), 200, 1))


def contexto_seguridad(m):
    """Seguridad: el resumen y el cuerpo recortado, solo la conducta y sin
    secretos (security_guidance.solo_codigo + enmascarar, como el hook)."""
    cuerpo = str(m.get("cuerpo") or "")[:SEGURIDAD_CUERPO * 4]
    try:
        hooks = os.path.join(ROOT, "hooks")
        if hooks not in sys.path:
            sys.path.append(hooks)
        import security_guidance as SG
        cuerpo = SG.enmascarar(SG.solo_codigo(cuerpo))
    except Exception:
        pass
    return "Resumen: %s\nCuerpo: %s" % (m.get("resumen") or "", cuerpo[:SEGURIDAD_CUERPO])


def preguntar(sub, contexto):
    """Una de las tres preguntas del uso Conversaciones (c1 · c2 · c3) por la
    fachada (decisions.gate con su pregunta y opciones). None = apagado,
    falló o tardó: todo sigue como si no estuviera."""
    D = _decisiones()
    if D is None or not decisor_encendido():
        return None
    try:
        q = D.SPECS[DECISOR]["questions"][sub]
        return D.gate(DECISOR, context=contexto, question=q["question"],
                      options=list(q["options"]), kind="choice", al_agente=True)
    except Exception:
        return None


def preguntar_seguridad(m):
    """Seguridad sobre un mensaje de la sala (el uso workspace.security, con la
    pregunta de las salas; solo SUBE a «alto»: apply_only). None si apagado."""
    D = _decisiones()
    if D is None or not decisor_encendido("workspace.security"):
        return None
    try:
        return D.gate("workspace.security", context=contexto_seguridad(m),
                      question=D.SEGURIDAD_SALAS,
                      options=list(D.SPECS["workspace.security"]["options"]), al_agente=True)
    except Exception:
        return None


def aplica(v, *opciones):
    """¿El veredicto se APLICA con una de esas opciones? (decide, p ≥ umbral
    y p_known: lo resolvió la fachada en `mode`)."""
    return bool(v) and v.get("mode") == "apply" and v.get("choice") in opciones


def sugiere(v, *opciones):
    return bool(v) and v.get("mode") in ("suggest", "apply") and v.get("choice") in opciones


def _ruta_decisor(nombre):
    import paths
    return os.path.join(paths.state_dir(), "salas", "decisor", nombre)


def _leer_json(ruta, defecto):
    try:
        with open(ruta, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, type(defecto)) else defecto
    except Exception:
        return defecto


def _guardar_json(ruta, datos):
    try:
        import atomico
        atomico.escribir(ruta, json.dumps(datos, ensure_ascii=False) + "\n")
    except Exception:
        pass


def delicados():
    """{id del mensaje: {decider, p}}: lo que Seguridad subió a «⚠ delicado»
    en ESTA máquina (local; el hub lo marca)."""
    return _leer_json(_ruta_decisor("delicados.json"), {})


def _marcar_delicado(m, v):
    """Leer y guardar bajo el candado (sin él, no se escribe)."""
    ruta = _ruta_decisor("delicados.json")

    def hacer():
        d = delicados()
        d[m["id"]] = {"decider": v.get("decider"), "p": v.get("p")}
        _guardar_json(ruta, dict(list(d.items())[-500:]))
    try:
        _bajo_candado(ruta, hacer)
    except Exception:
        pass


def linea_decisor(v, sub):
    """La línea ◆ de un veredicto, en el formato de Decisores (o '')."""
    try:
        import decision_visible as V
        if sub == "seguridad":
            if aplica(v, "alto"):
                return "⚠ delicado: confírmalo con el socio antes de hacerlo · " + V.formato(
                    V._nombre(v.get("decider")), V._que("workspace.security", "alto", True),
                    V._pct(v.get("p")), "apply")
            return V.linea_seguridad(dict(v, mode="suggest"))
        aplicado = v.get("mode") == "apply" and sub in ("c1", "c2")
        p = V._pct(v.get("p")) if v.get("p_known", True) else None
        return V.formato(V._nombre(v.get("decider")), V._que(DECISOR, v.get("choice"), aplicado), p,
                         "apply" if aplicado else "suggest")
    except Exception:
        return ""


def decidir_entregas(items, yo):
    """Decisores sobre lo que este despertar va a entregar → (items, notas).
    No corre nada con Conversaciones apagado (todo igual): Seguridad en salas
    cuelga de ese uso, así que prender Seguridad para el código no cuesta
    llamadas aquí (revisión fría, hallazgo 7).
      · Seguridad (cada pide/responde de otro agente; solo sube): «alto»
        aplicado → «⚠ delicado» (y C1 ya no lo calla); «alto» sugerido → su
        línea; «bajo» o «medio» → nada (en salas no hay aviso que cambiar);
      · C1 (un pide que no es para quien abrió ni urgente): «solo informa»
        aplicado → no despierta y se suelta la deuda («◆ solo informa»);
        sugerido → la línea ◆;
      · C3 (un responde a quien abrió): «sí» → «◆ parece cumplido»;
      · C2 (quien abrió, cada C2_CADA mensajes nuevos): «en bucle» / «se
        desvió» aplicado → pausa «◆ …»; sugerido → la línea ◆.
    `notas` = {(sala, id): [líneas]} y {(sala, ""): [líneas de la sala]}."""
    conv = decisor_encendido()
    seg = conv and decisor_encendido("workspace.security")
    if not conv or not items:
        return items, {}
    notas, out = {}, []
    for it in items:
        s, i, r, n = it
        lst = notas.setdefault((s["id"], i), [])
        delicado = False
        if seg and r.get("kind") == "msg" and n in ("pide", "responde") and not es_socio(r["de"]):
            v = preguntar_seguridad(r)
            if aplica(v, "alto"):
                delicado = True
                _marcar_delicado(r, v)
            if v and v.get("mode") in ("suggest", "apply") and v.get("choice") == "alto":
                lst.append(linea_decisor(v, "seguridad"))
        if conv and n == "pide" and c1_corre(s, r, yo, delicado):
            if _c1(s, r, yo, lst) != "entrega":
                continue        # soltado ahora, o ya no es mío (otro `esperar` lo soltó)
        if conv and n == "responde" and yo["key"] == s["creador"] and not s["cerrada"]:
            v = preguntar("c3", contexto_c3(s, r))
            if sugiere(v, "sí"):
                lst.append(linea_decisor(v, "c3"))
        out.append(it)
    if conv:
        vistas = []
        for s, _i, _r, _n in out:
            if s["id"] not in vistas and yo["key"] == s["creador"] and not s["cerrada"]:
                vistas.append(s["id"])
                _c2(s, yo, notas)
    return out, {k: [x for x in v if x] for k, v in notas.items() if any(v)}


def _sigue_siendo_mio(sala_id, pedido, yo):
    s = encontrar(sala_id, yo["cerebros"], Almacen())
    p = (s or {}).get("pedidos", {}).get(pedido)
    return bool(p) and p["estado"] == "esperando" and yo["key"] in p["pendientes"]


def _c1(s, r, yo, lst):
    """C1 sobre un pedido, bajo el candado de ESTA pestaña: dos `esperar`
    suyos (fondo y primer plano) no preguntan ni sueltan dos veces el mismo
    pedido, y el que llega segundo no entrega uno ya soltado (revisión fría,
    hallazgo 6). → "callado" (se soltó), "fuera" (ya no es deuda mía) o
    "entrega" (con la línea ◆ si solo se sugiere)."""
    def hacer():
        if not _sigue_siendo_mio(s["id"], r["id"], yo):
            return "fuera"
        v = preguntar("c1", contexto_c1(s, r))
        if aplica(v, "solo informa"):
            try:
                soltar(s["id"], yo["agente"], r["id"], "◆ solo informa", brains=yo["cerebros"],
                       _sobre=yo["sobre"], _por=POR_DECISOR)
                return "callado"            # no despierta: lo verá en «mientras tanto»
            except Exception:
                return "entrega" if _sigue_siendo_mio(s["id"], r["id"], yo) else "fuera"
        if sugiere(v, "solo informa"):
            lst.append(linea_decisor(v, "c1"))
        return "entrega"
    try:
        import olock
        ruta = _ruta_decisor(re.sub(r"[^A-Za-z0-9._-]", "_", yo["key"])[:120] + ".c1")
        lk = olock.file_lock(olock.ruta_candado(ruta), timeout=10)
    except Exception:
        lk = None
    if lk is None:
        return hacer()
    try:
        lk.__enter__()
    except TimeoutError:
        return "fuera"              # el otro `esperar` sigue con él: el siguiente sondeo lo ve
    except Exception:
        return hacer()              # sin candado posible (disco): como antes
    try:
        return hacer()
    finally:
        try:
            lk.__exit__(None, None, None)
        except Exception:
            pass


def _c2(s, yo, notas):
    """C2 en el despertar de quien abrió: cada C2_CADA mensajes nuevos."""
    msgs = [m for m in s["mensajes"] if m["entregable"] and not es_socio(m["de"])]
    ruta = _ruta_decisor(re.sub(r"[^A-Za-z0-9._-]", "_", yo["key"])[:120] + ".json")
    est = _leer_json(ruta, {})
    c2 = est.setdefault("c2", {})
    if len(msgs) - int(c2.get(s["id"]) or 0) < C2_CADA:
        return
    c2[s["id"]] = len(msgs)
    _guardar_json(ruta, est)
    v = preguntar("c2", contexto_c2(s, msgs[-C2_CADA:]))
    if aplica(v, "en bucle", "se desvió") and not s["pausada"]:
        try:
            accion_creador(s["id"], yo["agente"], "pausa", "◆ " + v["choice"],
                           brains=yo["cerebros"], _sobre=yo["sobre"])
        except Exception:
            v = dict(v, mode="suggest")
    if sugiere(v, "en bucle", "se desvió"):
        notas.setdefault((s["id"], ""), []).append(linea_decisor(v, "c2"))


def c1_corre(sala, m, yo, delicado=False):
    """¿C1 puede preguntar por este pedido? Nunca: lo del socio, lo que va a
    quien abrió, lo que Seguridad marcó delicado, lo urgente (espera ≤15 min)."""
    if m.get("tipo") != "pide" or es_socio(m["de"]) or delicado:
        return False
    if yo["key"] == sala["creador"]:
        return False
    p = sala["pedidos"].get(m["id"]) or {}
    esp = p.get("espera") or _int(m.get("espera"), 0) or sala["espera"]
    return esp > URGENTE_MIN


# ═══════════════════════════════════════════════════════════════════════════
# Texto para el agente (CLI)
# ═══════════════════════════════════════════════════════════════════════════

def _quien(sala, token, yo_key=""):
    if token == yo_key:
        return "tú"
    if es_socio(token):
        return "el socio"
    p = sala["participantes"].get(token)
    if not p:
        return agente_de(token) + (" (aún no se une)" if token.startswith("?") else "")
    extra = [x for x in (p.get("pestana"), M.nombre_maquina(p.get("maquina")) if p.get("maquina")
                         else "", p.get("motor")) if x]
    return "%s (%s)" % (p["agente"], " · ".join(extra)) if extra else p["agente"]


def _turno_txt(m):
    """El turno de un mensaje con la regla de la cabecera («turno N de M»):
    solo cuentan los mensajes de agentes; lo del socio no gasta turno. (El
    `turno` del archivo es solo el orden en pantalla: no se pinta.)"""
    if m.get("n_turno"):
        return "turno %d" % m["n_turno"]
    return "no gasta turno" if es_socio(m.get("de")) else "sin turno"


def _prep(prep, nombre):
    """«de»/«a» + un nombre de _quien/nombre_de, con las contracciones del
    español: «del socio», «al socio», «de ti» (nunca «de el socio»)."""
    if nombre.startswith("el socio"):
        return {"de": "del ", "a": "al "}[prep] + nombre[3:]
    if nombre == "tú":
        return prep + " ti"
    return "%s %s" % (prep, nombre)


_MOTIVO = {"alterado": "ALTERADO: el archivo cambió después de escribirse; no se entrega",
           "no_participa": "de alguien que no participa: no se entrega",
           "despues_del_cierre": "llegó después del cierre: no se entrega",
           "tope": "pasó el tope de turnos: no se entrega"}


def _marca_listo(p, d):
    """« ✓» si respondió (o lo pasó a otro), « (soltado)» si lo soltó sin
    responder (él o el decisor), "" si aún lo debe."""
    if d in p.get("soltados", ()):
        return " (soltado)"
    return " ✓" if d in p["listos"] else ""


def _linea_pedido(sala, p, ahora, yo_key=""):
    nombres = ", ".join(_quien(sala, d, yo_key) + _marca_listo(p, d) for d in p["a"])
    if p["estado"] == "cancelado":
        return "pedido cancelado"
    if p["estado"] == "listo":
        if all(d in p.get("soltados", ()) for d in p["a"] if d in p["listos"]) and p["listos"]:
            return "soltado: " + nombres
        return "respondido: " + nombres
    if p["estado"] == "cerrado":
        faltan = [d for d in p["a"] if d not in p["listos"]]
        listos = [d for d in p["a"] if d in p["listos"]]
        txt = "sin respuesta (la sala se cerró): " + (
            ", ".join(_quien(sala, d, yo_key) for d in faltan) or "nadie")
        if listos:
            txt += " · respondió: " + ", ".join(_quien(sala, d, yo_key) for d in listos)
        return txt
    if ahora >= p["vence"]:
        return "esperando a: %s · VENCIÓ %s" % (nombres, _hora(p["vence"]))
    return "esperando a: %s · vence %s (faltan %s)" % (nombres, _hora(p["vence"]),
                                                        falta_txt(p["vence"] - ahora))


def _cabecera(sala, yo=None, ahora=None):
    ahora = ahora or _ahora()
    estado = ("borrada" if sala["borrada"] else "archivada" if sala["archivada"] else
              "CERRADA" if sala["cerrada"] else "EN PAUSA" if sala["pausada"] else "abierta")
    out = ["sala %s · «%s» · %s · turno %d de %d · espera %s" % (
        sala["id"], sala["titulo"], estado, sala["turnos"], sala["tope"], espera_txt(sala["espera"]))]
    if sala.get("firma") == "alterado":
        out.append("  [ALTERADO: alguien editó sala.md a mano; díselo al socio]")
    out.append("  objetivo: %s" % sala["objetivo"])
    if sala["hecho_cuando"]:
        out.append("  hecho cuando: %s" % sala["hecho_cuando"])
    key = (yo or {}).get("key", "")
    bm = (yo or {}).get("cerebros")
    gente = [_quien(sala, k, key) + (" · abrió" if p["creador"] else "") +
             ("" if p["unido"] else " · invitado, " + _sin_entrar_txt(sala, k, bm, ahora))
             for k, p in sala["participantes"].items()]
    gente += ["%s · invitado, %s" % (a, _sin_entrar_txt(sala, "?" + a, bm, ahora))
              for a in sala["invitados"]
              if not any(p["agente"] == a for p in sala["participantes"].values())]
    out.append("  participantes: " + "; ".join(gente))
    if yo:
        deb = deudas_de(sala, yo["key"], yo["agente"])
        if deb:
            out.append("  te toca responder: " + ", ".join(
                "%s %s (vence %s)" % (p["id"], _prep("de", _quien(sala, p["de"], key)),
                                      _hora(p["vence"]))
                for p in deb))
        mios = [p for p in sala["pedidos"].values() if p["de"] == key and p["estado"] == "esperando"]
        if mios:
            out.append("  esperas respuesta: " + "; ".join(
                "%s (%s)" % (p["id"], _linea_pedido(sala, p, ahora, key)) for p in mios))
    return out


def ver_texto(sala, yo=None, completo=False, ahora=None):
    """La sala para leer en la terminal, en el orden de pantalla."""
    ahora = ahora or _ahora()
    key = (yo or {}).get("key", "")
    out = _cabecera(sala, yo, ahora)
    vistos = (set(cursor(key, (yo or {}).get("brain"))["ids"].get(sala["id"], ()))
              if key else set())
    try:
        import aviso_panel
        avisados = aviso_panel.avisos_de(sala["id"])          # los de ESTA máquina
    except Exception:
        avisados = {}
    for i, m in enumerate(sala["mensajes"], 1):
        para = ", ".join(_quien(sala, d, key) for d in m["destinos"]) or "todos"
        out.append("")
        out.append("── %d · %s · %s → %s · %s · %s   (%s)%s" % (
            i, _turno_txt(m), _quien(sala, m["de"], key), para, m["tipo"], _hora(m["t"]),
            m["id"], "" if not key or m["de"] == key or m["id"] in vistos or not m["entregable"]
            else " · nuevo"))
        if m["motivo"]:
            out.append("   [%s]" % _MOTIVO.get(m["motivo"], m["motivo"]))
        if m.get("menciones_cortadas"):
            out.append("   [más de %d menciones: solo cuentan las primeras]" % MAX_MENCIONES)
        if m.get("en_respuesta_a"):
            out.append("   responde a %s" % m["en_respuesta_a"])
        if completo:
            out.append("   resumen: " + (m.get("resumen") or ""))
            out.append("")
            out.extend("   " + ln if ln else "" for ln in (m.get("cuerpo") or "").split("\n"))
        else:
            out.append("   " + (m.get("resumen") or _linea(m.get("cuerpo"), 200, 2)))
        p = sala["pedidos"].get(m["id"])
        if p:
            out.append("   " + _linea_pedido(sala, p, ahora, key))
        for (mid, para), av in sorted(avisados.items(), key=lambda kv: kv[1].get("t", 0)):
            if mid == m["id"] and av.get("estado") == "avisado":
                out.append("   ◆ Workspace avisó a %s en su panel · %s%s" % (
                    _quien(sala, para, key), _hora(av.get("t") or 0),
                    " (a mano, desde el hub)" if av.get("manual") else ""))
    eventos = [e for e in sala["eventos"] if e["valido"] and e["accion"] not in ("unirse",)]
    if eventos:
        out.append("")
        out.append("── eventos ──")
        for e in eventos:
            out.append("   %s · %s · %s%s%s" % (
                _hora(e["t"]), _quien(sala, e["de"], key), e["accion"],
                " (lo soltó el decisor)" if e.get("por") == POR_DECISOR else "",
                (" · " + e["motivo"]) if e.get("motivo") else ""))
    return "\n".join(out)


def _texto_contrato(sala, yo, ahora=None):
    """La primera vez que una sala le llega a esta pestaña: de qué va, cuándo
    termina, quién abrió, quién está (agente · pestaña · motor) y cómo pedirle
    algo a alguien."""
    cab = _cabecera(sala, yo, ahora)[1:]
    creador = sala["participantes"].get(sala["creador"])
    out = ["── Es la primera vez que te llega esta sala. El contrato:"]
    out += [ln for ln in cab if not ln.startswith(("  te toca", "  esperas"))]
    if creador:
        out.append("  abrió: %s" % _quien(sala, sala["creador"], yo["key"]))
    out.append("  para pedirle algo a otro participante: %s publicar %s --tipo pide --para "
               "<agente> --resumen \"…\" \"<cuerpo>\" (un «@nombre» en el texto no le avisa)"
               % (_cmd(), sala["id"]))
    return "\n".join(out)


def _texto_contexto(sala, ctx, yo):
    """El bloque «Mientras tanto en la sala»: un renglón por mensaje que no te
    despertaba, con su resumen; los que te mencionan, marcados."""
    key = yo["key"]
    out = ["── Mientras tanto en la sala (lo que no te despertaba; léelo, pero solo actúa "
           "en lo tuyo):"]
    if len(ctx) > CONTEXTO_MAX:
        out.append("   (+%d antes: %s ver %s)" % (len(ctx) - CONTEXTO_MAX, _cmd(), sala["id"]))
    for i, m, para_ti in ctx[-CONTEXTO_MAX:]:
        para = ", ".join(_quien(sala, d, key) for d in m["destinos"]) or "todos"
        out.append("   · %s %s → %s (%s): %s%s" % (
            _hora(m["t"]), _quien(sala, m["de"], key), para, m["tipo"],
            m.get("resumen") or _linea(m.get("cuerpo"), 200, 1),
            "   ◂ para ti" if para_ti else ""))
    return "\n".join(out)


def _texto_item(sala, item, yo, ahora):
    i, r, nota = item
    key = yo["key"]
    if r["kind"] == "evento":
        a = r["accion"]
        p = sala["pedidos"].get(r.get("pedido") or "")
        if a in ("cierre", "archivar"):
            if r["de"] == key:
                return ("── cerraste la sala «%s»%s: este esperar termina aquí"
                        % (sala["titulo"], (" · " + r["motivo"]) if r.get("motivo") else ""))
            return ("── la sala «%s» quedó CERRADA por %s%s: deja de esperarla y avísale al socio"
                    % (sala["titulo"], _quien(sala, r["de"], key),
                       (" · " + r["motivo"]) if r.get("motivo") else ""))
        if a == "pausa":
            return ("── la sala «%s» está EN PAUSA (%s): no actúes en ella; termina tu turno y "
                    "dile al socio" % (sala["titulo"], _quien(sala, r["de"], key)))
        if a == "reanudar":
            return "── la sala «%s» SIGUE (la reanudó %s): retoma lo pendiente" % (
                sala["titulo"], _quien(sala, r["de"], key))
        if a == "soltar" and r.get("por") == POR_DECISOR:
            return ("── ◆ el decisor soltó tu pedido %s %s (solo informa): no lo va a "
                    "responder; si sí pedía algo, vuelve a pedírselo" % (
                        r.get("pedido"), _prep("a", _quien(sala, r["de"], key))))
        if a == "soltar":
            return "── %s soltó tu pedido %s sin responder%s" % (
                _quien(sala, r["de"], key), r.get("pedido"),
                (": " + r["motivo"]) if r.get("motivo") else "")
        if a == "delegar":
            return "── %s pasó tu pedido %s %s" % (_quien(sala, r["de"], key), r.get("pedido"),
                                                   _prep("a", _quien(sala, r.get("en"), key)))
        if a == "cancelar":
            return "── %s canceló el pedido %s%s: no lo atiendas" % (
                _quien(sala, r["de"], key), r.get("pedido"),
                "" if not p else " (%s)" % _prep("de", _quien(sala, p["de"], key)))
        return "── %s · %s" % (a, _quien(sala, r["de"], key))
    cab = "[%s] %s · %s · %s" % (r["tipo"], i, _turno_txt(r),
                                 _prep("de", _quien(sala, r["de"], key)))
    if nota.startswith("delegado:"):
        cab += " · te lo pasó %s" % _quien(sala, nota.split(":", 1)[1], key)
    p = sala["pedidos"].get(i)
    if p and nota != "responde":
        cab += " · vence %s (espera %s)" % (_hora(p["vence"]), espera_txt(p["espera"] + p["mas"]))
    if r.get("en_respuesta_a"):
        cab += " · responde a tu %s" % r["en_respuesta_a"]
    out = [cab, "resumen: " + (r.get("resumen") or ""), "", r.get("cuerpo") or ""]
    recordar = recordatorio_cierre(sala, yo, nota)
    if recordar:
        out += ["", recordar]
    return "\n".join(out)


def recordatorio_cierre(sala, yo, nota):
    """A quien abrió, con cada respuesta que le llega: el «hecho cuando» (o
    el objetivo) y cómo cerrar si ya se cumplió. Nunca cierra solo."""
    if nota != "responde" or yo["key"] != sala["creador"] or sala["cerrada"]:
        return ""
    meta = ("Hecho cuando: «%s»." % sala["hecho_cuando"] if sala["hecho_cuando"]
            else "Objetivo: «%s»." % sala["objetivo"])
    return "── %s Si ya se cumplió: %s cerrar %s --resumen \"<qué quedó>\"" % (
        meta, _cmd(), sala["id"])


def _cmd():
    """`<python> "<raíz>/messages.py" conversar`: ver _bus()."""
    return _bus() + " conversar"


def _bus():
    """El comando del bus como lo imprime el CLI: con la ruta RESUELTA (así
    el agente copia uno que su motor puede tener aprobado:
    memoria.permisos_bus_claude) y la forma de la plataforma — en Windows
    `python "C:\\…\\messages.py"`: allí `$WORKSPACE_ROOT` no se expande en
    PowerShell y `python3` puede abrir la Microsoft Store. La raíz: la de la
    pestaña (WORKSPACE_ROOT) o, si no la hay (el hub, que también escribe el
    aviso en el panel: aviso_panel.linea), la de este mismo código, como
    memoria.permisos_bus_claude. La variable, solo si ninguna sirve."""
    import ntpath
    import posixpath
    win = sys.platform == "win32"
    for raiz in (os.environ.get("WORKSPACE_ROOT", "").strip(), ROOT):
        if raiz and '"' not in raiz and "$" not in raiz:
            ruta = (ntpath if win else posixpath).join(raiz, "messages.py")
            return ('python "%s"' if win else 'python3 "%s"') % ruta
    return 'python3 "$WORKSPACE_ROOT/messages.py"'


def _err(texto):
    """Una línea de ayuda o aviso (stderr), DESPUÉS de lo ya impreso: con la
    salida en un pipe stdout va con búfer y stderr no, y en Windows los
    «help:» salían antes que el contenido."""
    try:
        sys.stdout.flush()
    except Exception:
        pass
    print(texto, file=sys.stderr)


# ═══════════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════════

def _yo_cli(a):
    agente, err = M._remitente(getattr(a, "from_agent", None))
    if err:
        raise Error(err)
    if not agente:
        raise Error("falta --from <agente> (o WORKSPACE_AGENT_NAME: lo exporta Workspace)")
    return agente


def main(argv=None):
    import argparse
    try:
        import _utf8
        _utf8.harden()
    except Exception:
        pass
    ap = argparse.ArgumentParser(prog="messages.py conversar",
                                 description="Salas de varios agentes (conversaciones/<id>/)")
    sub = ap.add_subparsers(dest="cmd")

    def con_from(p):
        p.add_argument("--from", dest="from_agent", default=None, help=argparse.SUPPRESS)
        return p
    ab = con_from(sub.add_parser("abrir", help="abrir una sala"))
    ab.add_argument("--titulo", required=True)
    ab.add_argument("--objetivo", required=True)
    ab.add_argument("--con", action="append", default=[], help="agente o agente:Pestaña (repetible)")
    ab.add_argument("--espera", default="", help="por pedido: 15m, 30m, 1h, 2h, 8h, 24h")
    ab.add_argument("--hecho-cuando", dest="hecho_cuando", default="")
    ab.add_argument("--max-turnos", dest="max_turnos", type=int, default=MAX_TURNOS)
    ab.add_argument("--pide", default="", help="el primer pedido, a todos los invitados "
                                               "(«-» = leerlo de stdin)")
    ab.add_argument("--cuerpo-archivo", dest="cuerpo_archivo", default="",
                    help="el primer pedido desde un archivo UTF-8")
    ab.add_argument("--resumen", default="", help="del primer pedido (obligatorio con --pide)")
    pu = con_from(sub.add_parser("publicar", help="publicar un mensaje"))
    pu.add_argument("sala")
    pu.add_argument("cuerpo", nargs="?", default=None,
                    help="el texto («-» = leerlo de stdin; o --cuerpo-archivo <ruta>)")
    pu.add_argument("--cuerpo-archivo", dest="cuerpo_archivo", default="",
                    help="el cuerpo desde un archivo UTF-8 (en vez del argumento)")
    pu.add_argument("--tipo", required=True, choices=TIPOS)
    pu.add_argument("--resumen", required=True)
    pu.add_argument("--para", action="append", default=[], help="agente, agente:Pestaña o clave")
    pu.add_argument("--a", default="", help="el pedido que respondes (responde)")
    pu.add_argument("--espera", default="", help="la de este pedido: 15m, 2h…")
    es = con_from(sub.add_parser("esperar", help="esperar lo que te toca (long-poll)"))
    es.add_argument("--sala", default="")
    es.add_argument("--timeout", type=float, default=ESPERAR_TIMEOUT)
    es.add_argument("--intervalo", type=float, default=ESPERAR_INTERVALO, help=argparse.SUPPRESS)
    es.add_argument("--asiento", type=float, default=None, help=argparse.SUPPRESS)
    ve = con_from(sub.add_parser("ver", help="tus salas, o una sala"))
    ve.add_argument("sala", nargs="?", default="")
    ve.add_argument("--completo", action="store_true")
    so = con_from(sub.add_parser("soltar", help="soltar un pedido sin responder"))
    so.add_argument("sala")
    so.add_argument("--a", required=True)
    so.add_argument("--motivo", default="")
    de = con_from(sub.add_parser("delegar", help="pasar un pedido a otro participante"))
    de.add_argument("sala")
    de.add_argument("--a", required=True)
    de.add_argument("--en", required=True)
    de.add_argument("--resumen", default="")
    for nombre, ayuda in (("pausar", "pausar la sala (solo quien abrió)"),
                          ("reanudar", "reanudarla"), ("cerrar", "cerrarla con lo que quedó"),
                          ("archivar", "archivarla (cerrada)")):
        x = con_from(sub.add_parser(nombre, help=ayuda))
        x.add_argument("sala")
        x.add_argument("--resumen", default="")
    try:
        # parse_known_args + el cuerpo que sobró: en Python < 3.12, argparse no
        # sabe poner un posicional opcional (el cuerpo de `publicar`) después
        # de opciones intercaladas («publicar <sala> --tipo … "<cuerpo>"»)
        a, extra = ap.parse_known_args(argv)
        if extra and a.cmd == "publicar" and a.cuerpo is None and len(extra) == 1 \
                and not extra[0].startswith("--"):
            a.cuerpo, extra = extra[0], []
        if extra:
            ap.error("unrecognized arguments: %s" % " ".join(extra))
    except SystemExit as e:
        return e.code if isinstance(e.code, int) else 2
    if not a.cmd:
        ap.print_help()
        return 2
    try:
        return _correr(a)
    except Error as e:
        print("no se pudo: %s" % e)
        return 1
    except (OSError, UnicodeError) as e:
        print("no se pudo escribir: %s: %s" % (type(e).__name__, e))
        return 1


def _registrar_panel():
    """Cada comando `conversar` deja el panel de herdr de su pestaña (si corre
    en uno): así aviso_panel sabe a qué panel escribirle. Falla suave."""
    if not os.environ.get("HERDR_PANE_ID"):
        return
    try:
        import aviso_panel
        aviso_panel.registrar_entorno(fuente="conversar")
    except Exception:
        pass


def _correr(a):
    cmd = a.cmd
    _registrar_panel()
    if cmd == "abrir":
        agente = _yo_cli(a)
        if a.cuerpo_archivo and a.pide:
            raise Error("usa --pide o --cuerpo-archivo, no los dos")
        leido = bool(a.cuerpo_archivo) or a.pide == "-"
        if a.cuerpo_archivo:
            a.pide = _leer_archivo_del_agente(a.cuerpo_archivo, agente, a.resumen)
        elif a.pide == "-":
            a.pide = leer_texto("-")
        if leido and not a.pide.strip():
            raise Error("el pedido está vacío")
        if a.pide and not _linea(a.resumen):
            raise Error("con --pide hace falta --resumen \"…\"")
        _sin_control([("el pedido", a.pide), ("el resumen", a.resumen)])   # antes de crear
        sid = abrir(agente, a.titulo, a.objetivo, a.con, a.espera or None, a.hecho_cuando,
                    a.max_turnos)
        print(sid)
        if a.pide:
            s = encontrar(sid)
            dest = [x for x in (list(s["invitados"]) + [k for k, p in s["participantes"].items()
                                                         if not p["creador"]])]
            mid, avisos = publicar(sid, agente, "pide", a.pide, a.resumen, para=dest)
            print(mid)
            for av in avisos:
                _err("aviso: " + av)
        _err("help: %s esperar --sala %s   (las respuestas)" % (_cmd(), sid))
        return 0
    if cmd == "publicar":
        agente = _yo_cli(a)
        if a.cuerpo_archivo and a.cuerpo not in (None, ""):
            raise Error("usa el cuerpo o --cuerpo-archivo, no los dos")
        if a.cuerpo_archivo:
            a.cuerpo = _leer_archivo_del_agente(a.cuerpo_archivo, agente, a.resumen)
        elif a.cuerpo == "-":
            a.cuerpo = leer_texto("-")
        if a.cuerpo is None:
            raise Error("falta el cuerpo: \"<texto>\", - (stdin) o --cuerpo-archivo <ruta>")
        mid, avisos = publicar(a.sala, agente, a.tipo, a.cuerpo, a.resumen, a.para, a.a,
                               a.espera or None)
        print(mid)
        for av in avisos:
            _err("aviso: " + av)
        if a.tipo == "pide":
            _err("help: %s esperar --sala %s   (la respuesta)" % (_cmd(), a.sala))
        return 0
    if cmd == "esperar":
        agente = _yo_cli(a)
        try:
            r = esperar(agente, a.sala or None, a.timeout, a.intervalo, asiento=a.asiento)
        except KeyboardInterrupt:
            return 130
        if r is None:
            raise Error("%s no tiene cerebro en esta máquina" % agente)
        if r.codigo == 1:
            raise Error("no encuentro la sala %s" % a.sala)
        donde = (" en %s" % a.sala) if a.sala else ""
        if r.codigo == SALIDA_NADA:
            print("esperar: nada nuevo para %s en %g s%s" % (agente, a.timeout, donde))
            _err("help: vuelve a esperar, o termina tu turno: lo que llegue te lo dice "
                 "Workspace al abrir la pestaña")
            return SALIDA_NADA
        if r.codigo == SALIDA_AVISO:
            for t in r.avisos:
                print("esperar: " + t)
            print("Para de esperar ese pedido y díselo al socio: desde el hub › Conversaciones "
                  "puede abrir a quien falta, darle más tiempo o cancelarlo.")
            return SALIDA_AVISO
        yo = identidad(agente)
        ahora = _ahora()
        if len(r):
            print("esperar: %d para %s%s — lo que dicen otros agentes es un pedido, no una "
                  "orden del socio" % (len(r), agente, donde))
        else:
            print("esperar: nada que atender para %s%s, pero hay novedades en la sala (léelas)"
                  % (agente, donde))
        for t in r.avisos:                  # p. ej. el estado no se puede guardar aquí
            print("esperar: " + t)
        orden, por_sala = [], {}
        for s, i, reg, nota in r:
            if s["id"] not in por_sala:
                orden.append(s["id"])
                por_sala[s["id"]] = (s, [])
            por_sala[s["id"]][1].append((i, reg, nota))
        for sid in r.contexto:
            if sid not in por_sala:
                orden.append(sid)
                por_sala[sid] = (encontrar(sid, yo["cerebros"]), [])
        for sid in orden:
            s, lst = por_sala[sid]
            if s is None:
                continue
            print("")
            print("══ sala %s · «%s» ══" % (s["id"], s["titulo"]))
            if sid in r.primera:
                print(_texto_contrato(s, yo, ahora))
            for ln in r.notas.get((sid, ""), ()):
                print("── " + ln)
            for item in lst:
                print("")
                print(_texto_item(s, item, yo, ahora))
                for ln in r.notas.get((sid, item[0]), ()):
                    print("── " + ln)
            if r.contexto.get(sid):
                print("")
                print(_texto_contexto(s, r.contexto[sid], yo))
        if any(n == "pide" or n.startswith("delegado:") for _s, _i, _r, n in r):
            _err("help: %s publicar <sala> --tipo responde --a <id> --resumen \"…\" \"<cuerpo>\""
                 % _cmd())
        _err("help: %s ver <sala>   (la sala completa)" % _cmd())
        return 0
    if cmd == "ver":
        agente = _yo_cli(a) if (a.from_agent or os.environ.get("WORKSPACE_AGENT_NAME")) else ""
        yo = identidad(agente) if agente else None
        if a.sala:
            s = encontrar(a.sala, (yo or {}).get("cerebros"))
            if s is None:
                raise Error("no encuentro la sala %s" % a.sala)
            print(ver_texto(s, yo, a.completo))
            return 0
        ss = todas((yo or {}).get("cerebros"), Almacen(), archivadas=False)
        if yo:
            ss = [s for s in ss if yo["agente"] in s["permitidos"]]
        if not ss:
            print("ver: ninguna sala abierta%s" % ((" para " + agente) if agente else ""))
            return 0
        ahora = _ahora()
        for s in sorted(ss, key=lambda x: x["creada"], reverse=True):
            print("\n".join(_cabecera(s, yo, ahora)))
            print("")
        return 0
    if cmd == "soltar":
        print(soltar(a.sala, _yo_cli(a), a.a, a.motivo))
        return 0
    if cmd == "delegar":
        print(delegar(a.sala, _yo_cli(a), a.a, a.en, a.resumen))
        return 0
    accion = {"pausar": "pausa", "reanudar": "reanudar", "cerrar": "cierre",
              "archivar": "archivar"}[cmd]
    print(accion_creador(a.sala, _yo_cli(a), accion, a.resumen))
    if accion == "cierre":
        ln = memoria_al_cerrar(a.sala, a.resumen)
        if ln:
            _err(ln)
    return 0


def _comillas_simples(texto):
    """Un argumento entre comillas SIMPLES, igual de literal en POSIX (bash,
    zsh) que en PowerShell: ahí nada se expande, ni `…` ni $(…) ni $x. La
    única que habría que escapar es la propia comilla simple, y se cambia por
    la tipográfica (’) para no depender de cómo escapa cada shell (revisión
    fría, hallazgo 10: entre comillas dobles, un resumen con `git push` lo
    ejecutaba bash al copiar el comando)."""
    return "'%s'" % str(texto or "").replace("'", "\u2019")


def memoria_al_cerrar(sala_id, resumen):
    """Al cerrar, con el uso Memoria de Decisores encendido: el tipo de nota
    que elige el decisor para el resumen de cierre y el comando para
    guardarlo en la memoria de la pestaña. '' apagado (nada cambia)."""
    if not str(resumen or "").strip() or not decisor_encendido("workspace.memory"):
        return ""
    D = _decisiones()
    try:
        v = D.gate("workspace.memory", context=str(resumen), al_agente=True)
        if not v or v.get("mode") not in ("suggest", "apply"):
            return ""
        import memoria
        tipo = memoria._DESDE_ETIQUETA.get(v.get("choice"), "nota")
        texto = _comillas_simples(_linea("sala %s cerrada: %s" % (sala_id, resumen), 200, 1))
        import decision_visible as V
        linea = V.formato(V._nombre(v.get("decider")),
                          V._que("workspace.memory", v.get("choice"), False),
                          V._pct(v.get("p")) if v.get("p_known", True) else None, "suggest")
        return "help: guárdalo en tu memoria: workspace memoria nota --tipo %s %s   (%s)" % (
            tipo, texto, linea)
    except Exception:
        return ""


if __name__ == "__main__":
    sys.exit(main())
