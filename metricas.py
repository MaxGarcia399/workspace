#!/usr/bin/env python3
"""WORKSPACE · metricas — registro LOCAL del desempeño de cada sesión de agente (F1).

Por qué existe: Workspace ya «ve» casi todo lo que pasa en una sesión (los
motores escriben tokens, modelo, duración, herramientas y sus errores en su
historial), pero no guardaba nada: el lector de memoria tira los tokens a
propósito, la statusline los muestra y los olvida, y la retención acaba
borrando los historiales. Este módulo junta esos números al CERRAR cada sesión,
los atribuye (máquina, usuario, agente, pestaña, motor) y los conserva. La
sección de Desempeño (fase posterior) se construye encima de este registro.

Principios (spec F1, no negociables):
  · Pasivo: nada depende de que el agente o el usuario anoten algo.
  · Solo números y nombres: jamás texto de mensajes ni de herramientas. Lo
    único textual que se guarda son nombres de skills, nombres de modelos y
    rutas RELATIVAS bajo deliverables/ del cerebro.
  · Local: `<estado>/metricas/` (≈ ~/.claude/workspace/metricas/), fuera del
    cerebro y fuera de Obsidian Sync. Workspace no los envía a nadie.
  · Fail-open absoluto: si algo falla, el cierre de la sesión sigue igual.
  · Honesto: «sin dato» es null, nunca 0. El costo se guarda solo si el motor
    lo da (`costo_fuente`). Cada fila lleva la versión del motor y del parser.

Núcleo vs. parsers. Este módulo NO sabe leer ningún motor: los parsers viven
en `metricas_motores/<motor>.py`, uno por motor, y se descubren solos (ver el
contrato en metricas_motores/__init__.py). Agregar un motor = agregar un
archivo ahí; el núcleo (cursores, huellas, filas, atribución, candado) no se
toca. Un motor sin parser deja solo el recibo (quién, qué, cuándo) con
`captura.estado = "sin_parser"` y lo medible en null. No se inventa.

Archivos en `<estado>/metricas/`:
  maquina.json            id anónimo y aleatorio de esta máquina (sin hostname
                          ni usuario del sistema).
  corridas-AAAA-MM.jsonl  una fila por tramo de sesión (mes UTC del fin del
                          tramo). Idempotente por (motor, sesion_motor, tramo).
  corridas-AAAA-MM.claves índice clave → huella de contenido de ese mes:
                          registrar no relee el mes; una clave repetida con
                          otro contenido es un conflicto (log), no se pisa.
  cursores.json           hasta dónde se midió cada sesión (lo define cada
                          parser: offset de bytes, subagentes…): retomar una
                          sesión no cuenta dos veces lo ya medido.
  motores.json            estado compartido de cada motor (aparte de los
                          cursores: perder uno no borra el otro): acumulado de
                          costo donde continuó una sesión, últimos contadores
                          de cada sesión de Hermes, pestaña de las que
                          continúan a otra…
  cola/                   cierres que no alcanzaron el candado (con su
                          atribución): los procesa el siguiente cierre o
                          `importar`.
  aviso.json              cuándo se mostró el aviso de privacidad.
  cambios.jsonl           bitácora automática: versión de Workspace, del motor,
                          modelo, huella del cerebro o de una skill que
                          cambiaron (ultimo_visto.json guarda lo último visto).
  salud.json              el último autodiagnóstico (`salud`): solo números.
  apagado.json            ventanas con las métricas apagadas: lo hecho dentro
                          no se mide nunca (tampoco al volver a encender). Las
                          marcan `workspace metricas apagar|encender` y el
                          ajuste (de toda la máquina). Además, `excluidas`:
                          las sesiones cerradas con WORKSPACE_NO_METRICAS (el
                          interruptor de emergencia, que es de un proceso),
                          por sesión, huella de la fuente o —sin ninguna de
                          las dos— cerebro, con sus ventanas. Nunca se podan.
  recibos-AAAA-MM.jsonl   un recibo por cierre (CAMPOS_RECIBO), escrito al
                          EMPEZAR el cierre, antes del candado: quién, qué,
                          dónde y los bytes de cada fuente (como huella con
                          sal). Denominador de cobertura y llave para
                          reconstruir. Jamás se exporta.
  latidos.jsonl           inicio y fin de cada cierre (ms, resultado, error):
                          un inicio sin fin = el runner lo mató por tiempo.
  sal.json                sal LOCAL de las huellas de pestañas y entregables
                          (aparte de maquina.json; jamás se exporta).
  nombres.json            huella → nombre legible (pestañas, entregables),
                          para mostrárselo al propio usuario. Local y borrable.
  goteo.json              (por generación) frontera del goteo, pendientes
                          (tramos a medias, sesiones abiertas) y cuándo quedó
                          al día.
  generacion.json         generación vigente del registro: {actual, previa,
                          historial}. La 1 vive en la raíz (filas, índice,
                          cursores, motores, vistos, turnos); `reconstruir`
                          re-mide todo a gen/<n>/ y cambia el puntero de forma
                          atómica (deshacer_reconstruccion() vuelve a la
                          anterior, que queda intacta). Lo demás es de la
                          máquina y no cambia con la generación.
  vistos/<motor>-AAAA-MM.txt
                          huellas (sha1 recortado) de lo ya contado. Hace falta
                          porque Claude Code, al continuar una sesión en otra
                          («continued-in»), COPIA el historial del padre al
                          archivo nuevo con los mismos ids y timestamps
                          (verificado: 152 de 256 mensajes de un hijo eran
                          copia). Se fragmenta por el mes del timestamp
                          ORIGINAL de cada línea: la copia lo conserva, así que
                          cae en el mismo fragmento y solo se cargan los meses
                          que aparecen en el tramo.

Escritura en orden con «pendiente» (write-ahead) para que un cierre cortado a
la mitad (el motor mata al hook por tiempo) nunca duplique ni pierda en
silencio: 1) el tramo queda como pendiente en cursores.json con sus cambios
al estado del motor, y sus huellas nuevas en vistos/pendientes/; 2) se
escribe la fila; 3) las huellas pasan a los fragmentos; 4) motores.json y
cursores.json avanzan. Al leer, un pendiente cuya fila existe se confirma
(cursor, cambios y huellas); si no existe, se descarta con sus huellas y el
tramo se vuelve a medir. Todo fallo o postergación queda en
<estado>/logs/metricas.log (nombres, ids y números).

Esquema de una fila g2 (corridas-AAAA-MM.jsonl; claves en CAMPOS_FILA):
  schema (2; las F1 = 1 se leen traducidas, traducir()), generacion, run_id,
  maquina, instalacion (dev | cliente), workspace_version, plataforma,
  origen (interactivo | importado), modo (interactivo | autonomo | headless |
  eval | prueba, derivado de modo_senales: entrypoint, originator, source,
  ruta_temporal, review_running, eval, headless), motor, motor_version,
  agente, cerebro («<carpeta>#<sha1 corto de su ruta real>»: jamás la ruta
  absoluta), cerebro_huella (archivos de identidad), pestana_h (huella con
  sal local; el nombre solo en nombres.json), socio, socio_id (cédula
  u-xxxx), atribucion (registrada | inferida | null), sesion_motor, tramo
  (huella del rango medido; «r:<run_id>» en un recibo; «u…» con formato
  desconocido), inicio, fin, tz_min, duracion_pared_s, duracion_activa_s,
  tiempo_humano_est_s, modelos, modelo_pedido, modelo_servido, esfuerzo,
  permisos, tokens_motor{modelos, cuadre}, costo_usd + costo_fuente +
  costo_tipo (equivalente_api | facturado | estimado | gratis) (+
  costo_detalle), facturacion, cuota{inicio, fin}, herramientas{llamadas,
  errores, comandos_no_cero}, respuestas_error{4xx, 5xx, bloqueado},
  interrupciones, mensajes_usuario, skills[{nombre, huella}],
  escritos{archivos, entregables[{h, ext, sha256_8, bytes}]}, subagentes,
  captura{estado, parser, verificado (si | no | por_canarios), degradada,
  captura_motor, leidas, reconocidas, desconocidas{tipo: n},
  lineas_ignoradas, duplicadas, copias, avisos…}.
  · `modelos` es el TOTAL de la sesión, subagentes incluidos. `subagentes`
    es un desglose informativo de esa parte: NO se suma aparte.
  · null = la fuente no lo mide (COBERTURA «no» del parser, o no hubo punto
    de partida seguro); 0 = se midió y fue cero.
  · Formato desconocido (se leyeron líneas y no se reconoció ninguna): todo
    lo medido en null, captura.estado = formato_desconocido y el cursor NO
    avanza.
  · Lo que solo vale «ahora» (versión de Workspace, huellas del cerebro, de
    las skills y de los entregables) no se pone en la historia importada.

turnos-AAAA-MM.jsonl: esqueleto por turno (CAMPOS_TURNO), sin texto, con
tiempos relativos al inicio del tramo; local, 90 días, jamás se exporta.

La historia se importa sola (goteo, F1.1): cada cierre en vivo le dedica lo
que le sobra (≤ _GOTEO_S) y avanza una frontera de lo más viejo a lo más
nuevo (goteo.json, por generación), recogiendo antes los tramos a medias y
las sesiones que estaban abiertas. Una sesión que se mide por primera vez y
continúa a otra (mismo primer timestamp, nacida después, en la misma
carpeta) hace medir antes a su padre. `workspace metricas importar` sigue
existiendo para hacerlo todo de una vez.

Semántica neutral de tokens por modelo (todos los parsers la respetan):
`entrada` = entrada SIN caché, `cache_lectura`, `cache_escritura`
(+ `cache_escritura_1h`, subconjunto de 1 h), `salida` (incluye el
razonamiento) y `razonamiento` (subconjunto). `llamadas` = respuestas del
modelo contadas.

Apagado: WORKSPACE_NO_METRICAS=1 (gana siempre; es del proceso: el hook no
mide y excluye esa sesión desde que empezó, por fuente) o `workspace metricas
apagar` (= setting `hooks.metricas`, ventana de toda la máquina). Encendido
por defecto.

Privacidad (F1.1): `socio` solo sin ambigüedad; carpeta 0700; el aviso de
una línea se muestra una vez (hub, CLI) y la historia de ANTES del aviso se
importa sin persona ni pestaña (salvo `importar --mio`); exportar va sin
persona (el desglose por cédula exige ≥5 personas y ≥20 sesiones por celda,
con horas redondeadas); turnos, nombres y recibos jamás se exportan; las
métricas jamás entran al contexto del agente.

CLI (`workspace metricas …`): estado · salud [--json] (código 0/1/2) ·
importar [--mio] · exportar --json <archivo> [--por-persona] · borrar
--mio|--todo|--antes AAAA-MM · reconstruir [--deshacer] · apagar · encender.

Cero dependencias (stdlib, Python 3.9+). Mac, Windows y Linux.
"""
import datetime as _dt
import hashlib
import json
import os
import re
import sys
import time
import uuid

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import paths as _paths  # noqa: E402  SSOT del dir de estado (test_state_dir_guard)
import events as _events  # noqa: E402  eco_de_otro_motor (la regla del runner)
import atomico  # noqa: E402
from atomico import ruta_larga  # noqa: E402,F401  rutas de 260+ en Windows (parsers: M.ruta_larga)

# Corrido como script (`python3 metricas.py …`), los parsers que hacen
# `import metricas` deben ver ESTE módulo, no una segunda copia.
sys.modules.setdefault("metricas", sys.modules[__name__])

#: Esquema de la fila. 1 = F1; 2 = g2 (F1.1). Las filas F1 se leen traducidas
#: a la forma g2 (traducir()); en disco no se reescriben.
SCHEMA = 2
#: Generación del registro: `reconstruir` re-mide la historia a una
#: generación nueva y cambia el puntero (generacion.json) de forma atómica.
#: La generación 1 vive en la raíz de metricas/ (ahí quedaron las filas F1).
GENERACION_INICIAL = 1
ORIGENES = ("interactivo", "importado")

# ── esquema g2 congelado (F1.1, F1.1_Decisiones_v2.md) ─────────────────────
#: Claves de una fila (medida o recibo), en orden. `costo_detalle` es opcional.
CAMPOS_FILA = (
    "schema", "generacion", "run_id", "maquina", "instalacion", "workspace_version",
    "plataforma", "origen", "modo", "modo_senales", "motor", "motor_version", "agente",
    "cerebro", "cerebro_huella", "pestana_h", "socio", "socio_id", "atribucion",
    "sesion_motor", "tramo", "inicio", "fin", "tz_min", "duracion_pared_s",
    "duracion_activa_s", "tiempo_humano_est_s", "modelos", "modelo_pedido",
    "modelo_servido", "esfuerzo", "permisos", "tokens_motor", "costo_usd",
    "costo_fuente", "costo_tipo", "facturacion", "cuota", "herramientas",
    "respuestas_error", "interrupciones", "mensajes_usuario", "skills", "escritos",
    "subagentes", "captura")
#: Claves de fila.captura (siempre) — más avisos/desde/hasta/error si aplican.
CAMPOS_CAPTURA = ("estado", "parser", "verificado", "degradada", "captura_motor",
                  "leidas", "reconocidas", "desconocidas", "lineas_ignoradas",
                  "duplicadas", "copias")
ESTADOS_CAPTURA = ("ok", "parcial", "formato_desconocido", "sin_parser",
                   "sin_transcript", "error")
VERIFICADO = ("si", "no", "por_canarios")
COSTO_TIPOS = ("equivalente_api", "facturado", "estimado", "gratis")
MODOS = ("interactivo", "autonomo", "headless", "eval", "prueba")
SENALES_MODO = ("entrypoint", "originator", "source", "ruta_temporal",
                "review_running", "eval", "headless")
CLASES_ERROR = ("4xx", "5xx", "bloqueado")
#: Esqueleto por turno (turnos-AAAA-MM.jsonl): local, 90 días, nunca se exporta.
CAMPOS_TURNO = ("schema", "generacion", "motor", "sesion_motor", "tramo", "n", "t_rel_s",
                "largo", "origen_turno", "ausente", "sim_prev", "resp_ini_rel_s",
                "resp_fin_rel_s", "modelo", "tokens", "herramientas", "errores",
                "interrupcion", "compactacion")
ORIGENES_TURNO = ("humano", "cola", "notificacion", "automatico")
#: Cubetas del largo del pedido (caracteres): <50, <200, <1000, >=1000.
CUBETAS_LARGO = ((50, "<50"), (200, "<200"), (1000, "<1000"))
LARGO_MAYOR = ">=1000"
#: Libro de recibos (recibos-AAAA-MM.jsonl): uno por cierre, escrito al EMPEZAR.
CAMPOS_RECIBO = ("schema", "run_id", "t", "motor", "motor_version", "sesion_motor",
                 "pestana_h", "socio", "socio_id", "agente", "cerebro", "cerebro_huella",
                 "plataforma", "workspace_version", "instalacion", "tz_min",
                 "modo_senales", "captura_motor", "fuentes", "apagado")
#: latidos.jsonl: inicio y fin de cada cierre (el runner mata por tiempo sin rastro).
CAMPOS_LATIDO = ("t", "fase", "run_id", "motor", "ms", "resultado", "error")
#: cambios.jsonl: bitácora automática de intervenciones.
CAMPOS_CAMBIO = ("t", "campo", "clave", "antes", "despues")

#: Campos que cada parser clasifica en su COBERTURA {campo: (estado, motivo)}
#: con estado si | parcial | no. «no» → el núcleo deja null ese campo en TODA
#: fila del motor (nunca 0); «parcial» → puede venir null en un tramo
#: (tramo.sin_dato) y se dice por qué. Punto = subcampo.
CAMPOS_COBERTURA = (
    "motor_version", "modo_senales", "duracion_activa_s", "tiempo_humano_est_s",
    "modelos", "modelo_pedido", "esfuerzo", "permisos", "tokens_motor", "costo_usd",
    "facturacion", "cuota", "herramientas.llamadas", "herramientas.errores",
    "herramientas.comandos_no_cero", "respuestas_error", "interrupciones",
    "mensajes_usuario", "skills", "escritos.archivos", "escritos.entregables",
    "subagentes", "turnos")
ESTADOS_COBERTURA = ("si", "parcial", "no")
#: CONTINUACION de un parser: {"retomar": m, "continuar": m}, m de aquí.
#:   mismo_archivo       — la sesión sigue escribiendo en la misma fuente
#:   respaldo_reescrito  — Workspace reescribe el respaldo entero al cerrar
#:   copia_historial     — una sesión NUEVA copia el historial de la anterior
#:   cadena              — sesión nueva con sus propios contadores y su padre
#:   no_aplica           — el motor no lo permite
#:   desconocido         — no verificado
MECANISMOS_CONTINUACION = ("mismo_archivo", "respaldo_reescrito", "copia_historial",
                           "cadena", "no_aplica", "desconocido")
ENV_APAGADO = "WORKSPACE_NO_METRICAS"
SETTING = "hooks.metricas"

#: Tiempo máximo que el cierre en vivo dedica a medir. Lo que no alcance queda
#: en el cursor y se mide en el siguiente cierre de esa sesión (o al importar).
PRESUPUESTO_VIVO = 6.0
#: Cerrando con la X (Windows mata la consola ~5 s después y el cierre normal
#: tiene 4 s de gracia para TODO): las métricas no usan más que esto.
PRESUPUESTO_X = 3.5
_CANDADO_VIVO = 3.0         # el cierre no espera más que esto por el candado
_CANDADO_IMPORTAR = 60.0
_LOTE_IMPORTAR = 40         # tope de sesiones por toma del candado al importar
_LOTE_IMPORTAR_S = 1.0      # …y de tiempo: un cierre en vivo espera ≤ _CANDADO_VIVO
_RESERVA_S = 1.0            # del presupuesto vivo, lo que se guarda para escribir
_GOTEO_S = 1.5              # goteo: lo que cada cierre dedica a la historia, como tope
_GOTEO_QUIETO_S = 600       # con la historia al día, el goteo vuelve a mirar cada tanto
_PADRES_S = 0.5             # buscar al padre de una sesión nueva, como tope
_TOPE_LISTA = 50            # tope de skills / entregables por fila
_CADA_BYTES = 256 * 1024   # cada cuánto se mira el reloj al leer
_BYTES_POR_S = 50 * 1024 * 1024   # lectura que se supone (conservadora) antes de leer entero
_TOPE_COLA = 200           # cierres en cola como máximo (los más viejos se descartan)
_COLA_QUIETA_S = 300        # al importar, una última línea sin \n de un archivo
                            # quieto hace más de esto se da por completa
_FUENTE_ACTIVA_S = 600      # al importar, una fuente modificada hace menos de
                            # esto es de una sesión abierta: la mide su cierre
_TOPE_TURNOS = 2000         # turnos por tramo como máximo
_TOPE_DESCONOCIDAS = 20     # tipos desconocidos distintos por tramo
_HUECO_HUMANO_S = 600.0     # tope de un hueco en tiempo_humano_est_s
_PEDIDOS_SIM = 5            # sim_prev: contra cuántos pedidos anteriores
_SIM_CHARS = 2000           # sim_prev: cuántos caracteres de cada pedido
_HUELLA_MAX_BYTES = 8 * 1024 * 1024    # entregables más grandes: sin sha256 (queda el tamaño)
#: hasta cuándo (time.monotonic) un cierre puede sacar huellas de archivos
_PLAZO_HUELLAS = [None]

#: Campos de tokens por modelo (semántica en el docstring del módulo).
CAMPOS_TOKENS = ("entrada", "salida", "cache_lectura", "cache_escritura",
                 "cache_escritura_1h", "razonamiento")
#: Nombre de una skill a partir de una ruta …/skills/[categoría/]<nombre>/SKILL.md
#: (también con «\» de Windows y dentro de un comando de shell).
SKILL_RE = re.compile(
    r"skills[\\/](?:[^\s'\"`<>|;&]*?[\\/])?([^\\/\s'\"`<>|;&]+)[\\/]SKILL\.md",
    re.IGNORECASE)
#: …y la ruta entera del SKILL.md (grupo 1) con su nombre (grupo 2).
_SKILL_RUTA_RE = re.compile(
    r"([^\s'\"`<>|;&]*skills[\\/](?:[^\s'\"`<>|;&]*?[\\/])?([^\\/\s'\"`<>|;&]+)[\\/]SKILL\.md)",
    re.IGNORECASE)
#: Tokens por turno (sin el subconjunto de 1 h de caché).
_TOKENS_TURNO = ("entrada", "salida", "cache_lectura", "cache_escritura", "razonamiento")
_NOMBRE_RE = re.compile(r"[^A-Za-z0-9_.:@+/-]")   # «/»: proveedor/modelo
_TS_RE = re.compile(r"^(\d{4})-(\d\d)-(\d\d)[T ](\d\d):(\d\d):(\d\d)(?:[.,](\d+))?"
                    r"\s*(Z|[+-]\d\d:?\d\d)?$")


# ═══════════════════════════════════════════════════════════════════════════
# Rutas, apagado, máquina, textos
# ═══════════════════════════════════════════════════════════════════════════

def carpeta():
    """<estado>/metricas. WORKSPACE_METRICAS_DIR la redirige (pruebas y
    verificación contra datos reales sin tocar el resto del estado)."""
    otra = os.environ.get("WORKSPACE_METRICAS_DIR")
    return os.path.abspath(otra) if otra else os.path.join(_paths.state_dir(), "metricas")


def _ruta(*partes):
    return os.path.join(carpeta(), *partes)


_PRIVADA = set()


def _mkdirs(d):
    """Toda carpeta de metricas/ nace por aquí: primero la raíz en 0700
    (_asegurar_carpeta), después la pedida, también 0700. Así no importa qué
    escritura llegue primero (revisión F1.1 #10)."""
    _asegurar_carpeta()
    if d:
        os.makedirs(ruta_larga(d), mode=0o700, exist_ok=True)


def _asegurar_carpeta():
    """metricas/ con permisos 0700 (POSIX): lo de una persona lo lee solo
    ella. En Windows vive bajo el perfil del usuario, cuya ACL ya lo limita
    a esa cuenta (y a los administradores)."""
    d = carpeta()
    if d in _PRIVADA:
        return d
    try:
        os.makedirs(d, mode=0o700, exist_ok=True)
        if os.name != "nt" and (os.stat(d).st_mode & 0o077):
            os.chmod(d, 0o700)
        _PRIVADA.add(d)
    except OSError:
        pass
    return d


def apagado():
    """True si la recolección está apagada: env WORKSPACE_NO_METRICAS (gana
    siempre) o el setting `hooks.metricas` en off. Falla-suave → encendida."""
    return apagado_por_entorno() or apagado_por_ajuste()


def apagado_por_entorno():
    """El interruptor de emergencia: es de ESTE proceso (y sus hijos), no de
    la máquina."""
    return bool(os.environ.get(ENV_APAGADO))


def apagado_por_ajuste():
    """El ajuste `hooks.metricas` (de toda la máquina)."""
    try:
        import settings
        return not settings.enabled(SETTING, default=True)
    except Exception:
        return False


def _estado_apagado():
    return _leer_json(_ruta("apagado.json"), {})


def _cambiar_apagado(fn):
    """Lee-modifica-escribe apagado.json con su candado (lo tocan procesos
    distintos: el ajuste, cada cierre con el interruptor)."""
    try:
        from olock import file_lock
        p = _ruta("apagado.json")
        _asegurar_carpeta()
        with file_lock(p, timeout=2.0):
            # lectura estricta: un apagado.json que existe y no se pudo abrir
            # (Windows: otro proceso lo reemplaza) NO se toma por vacío —se
            # perderían las ventanas y exclusiones— y uno roto se aparta
            d = _leer_estado_json(p)
            if fn(d):
                _escribir_json(p, d)
    except Exception as exc:
        _log("apagado_fallo", error=type(exc).__name__)


def _marcar_apagado(cuando=None):
    """Abre la ventana «apagado» del AJUSTE (si no hay una abierta): lo hecho
    dentro no se mide nunca, ni al volver a encender. Es de toda la máquina,
    como el ajuste. El interruptor de emergencia NO usa esta ventana: deja una
    exclusión por fuente (excluir_cierre)."""
    def fn(d):
        if d.get("desde"):
            return False
        d["desde"] = cuando or time.time()
        return True
    _cambiar_apagado(fn)


def _marcar_encendido(cuando=None):
    """Cierra la ventana del ajuste, si la hay (el ajuste volvió a encendido)."""
    def fn(d):
        if not d.get("desde"):
            return False
        d.setdefault("intervalos", []).append([d.pop("desde"), cuando or time.time()])
        return True
    _cambiar_apagado(fn)


#: más que esto en la lista vieja «fuentes» → se compacta al formato por clave
_TOPE_EXCLUIDAS = 500
#: sin `started` ni sesión ni transcript, la red de seguridad cubre esto hacia atrás
_VENTANA_SIN_INICIO_S = 12 * 3600


def _claves_excluidas(motor, sid=None, ruta_h=None, cerebro=None):
    out = []
    if sid:
        out.append("%s|s:%s" % (motor, sid))
    if ruta_h:
        out.append("%s|r:%s" % (motor, ruta_h))
    if cerebro:
        out.append("%s|c:%s" % (motor, cerebro))
    return out


def _sumar_ventana(ventanas, a, b):
    """Agrega [a, b] a la lista de ventanas de una clave, fundiendo las que
    se tocan. Nunca quita tiempo excluido."""
    vs = sorted([list(v) for v in ventanas] + [[a, b]])
    out = []
    for x, y in vs:
        if out and x <= out[-1][1]:
            out[-1][1] = max(out[-1][1], y)
        else:
            out.append([x, y])
    return out


def _compactar_excluidas(d):
    """La lista vieja «fuentes» (una entrada por cierre) pasa al formato por
    clave «excluidas» {motor|s:sesión · motor|r:huella · motor|c:cerebro:
    [[desde, hasta]…]}: más chico y JAMÁS pierde una exclusión (lo excluido
    no se vuelve a medir)."""
    ex = d.setdefault("excluidas", {})
    for e in d.pop("fuentes", None) or ():
        if not isinstance(e, dict):
            continue
        a, b = numero(e.get("desde")), numero(e.get("hasta"))
        if a is None or b is None:
            continue
        for k in _claves_excluidas(e.get("motor"), e.get("sesion"), e.get("ruta_h"),
                                   e.get("cerebro")):
            ex[k] = _sumar_ventana(ex.get(k) or [], a, b)
    return d


def excluir_cierre(payload):
    """El interruptor WORKSPACE_NO_METRICAS al cerrar: la sesión que se cierra
    queda EXCLUIDA desde que empezó (`started` del payload o el primer
    timestamp de su transcript; si no hay ninguno, desde siempre) hasta
    ahora. Es POR FUENTE (motor + sesión y la huella de su ruta): no apaga a
    los otros procesos, ni lo deshace un cierre ajeno, y el goteo o importar
    de cualquier proceso respetan la exclusión. Si no se sabe ni la sesión
    ni el transcript (Codex con el respaldo apagado y una resolución
    ambigua), la red de seguridad es el CEREBRO + la ventana `started`→ahora.
    Nunca se poda. No mide nada ni deja recibo."""
    data = payload if isinstance(payload, dict) else {}
    if eco_de_otro_motor(data):
        return None       # sin sesión de Claude Code que excluir (ni, sin id, todo el cerebro)
    try:
        motor = str(data.get("engine") or "claude-code")
        p = parser(motor)
        tpath = str(data.get("transcript_path") or "")
        brain = _cerebro(data)
        if p is not None and not (tpath and os.path.isfile(ruta_larga(tpath))):
            buscar = getattr(p, "transcript_de_cierre", None)
            if buscar:
                try:
                    tpath = buscar(brain, data) or ""
                except Exception:
                    tpath = ""
        run_id = str(data.get("run_id") or "") or None
        sid = str(data.get("session_id") or "") or None
        if sid and sid == run_id:
            sid = None
        inicio = epoch(data.get("started"))
        desdes = [x for x in (inicio,) if x]
        if p is not None and tpath and os.path.isfile(ruta_larga(tpath)):
            try:
                sid = p.sesion(tpath) or sid
                _cwd, ts = getattr(p, "cabecera", cabecera)(tpath)
                if ts:
                    desdes.append(ts)
            except Exception:
                pass
        else:
            tpath = ""
        ahora = time.time()
        entrada = {"motor": motor, "sesion": sid,
                   "ruta_h": huella_local("fuente", os.path.abspath(tpath)) if tpath else None,
                   "cerebro": None, "desde": min(desdes) if desdes else 0.0, "hasta": ahora}
        if not (entrada["sesion"] or entrada["ruta_h"]):
            # red de seguridad: sin saber cuál, todo lo del motor en ese cerebro
            # dentro de la ventana de la corrida
            entrada.update(cerebro=cerebro_id(brain),
                           desde=inicio or ahora - _VENTANA_SIN_INICIO_S)
            if not entrada["cerebro"]:
                return None

        def fn(d):
            _compactar_excluidas(d)
            ex = d.setdefault("excluidas", {})
            for k in _claves_excluidas(motor, entrada["sesion"], entrada["ruta_h"],
                                       entrada["cerebro"]):
                ex[k] = _sumar_ventana(ex.get(k) or [], entrada["desde"], entrada["hasta"])
            return True
        _cambiar_apagado(fn)
        return entrada
    except Exception as exc:
        _log("excluir_fallo", error=type(exc).__name__)
        return None


_APAGADO_MEMO = {}


def _excluidas_de(motor, sid, path, brain=None):
    """[(desde, hasta)] de las exclusiones por fuente (y, de red de
    seguridad, por cerebro) que valen para esa sesión."""
    out = []
    try:
        p = _ruta("apagado.json")
        try:
            firma = os.stat(p).st_mtime_ns
        except OSError:
            return out
        memo = _APAGADO_MEMO.get(p)
        if not memo or memo[0] != firma:
            memo = (firma, _compactar_excluidas(dict(_estado_apagado())).get("excluidas") or {})
            _APAGADO_MEMO[p] = memo
        ex = memo[1]
        if not ex:
            return out
        claves = _claves_excluidas(
            motor, sid, huella_local("fuente", os.path.abspath(path)) if path else None,
            cerebro_id(brain) if brain else None)
        for k in claves:
            for a, b in ex.get(k) or ():
                a, b = numero(a), numero(b)
                if a is not None and b is not None:
                    out.append((a, b))
    except Exception:
        pass
    return out


def intervalos_apagado():
    """[(desde, hasta)] en epoch con las métricas apagadas (la abierta, hasta
    el infinito)."""
    d = _estado_apagado()
    out = [(float(a), float(b)) for a, b in d.get("intervalos") or ()
           if isinstance(a, (int, float)) and isinstance(b, (int, float))]
    if isinstance(d.get("desde"), (int, float)):
        out.append((float(d["desde"]), float("inf")))
    return out


def _t(key, es, **kw):
    """Texto de la CLI en el idioma de la UI (lang/<code>/metricas.py); el
    español del código es la red."""
    try:
        import i18n
        v = i18n.t(key, **kw)
        if v != key:
            return v
    except Exception:
        pass
    try:
        return es.format(**kw) if kw else es
    except Exception:
        return es


def _leer_json(path, default):
    """JSON local de metricas/ o `default` si no existe o no se entiende.
    utf-8-sig: tolera el BOM del Bloc de notas. En Windows, abrir un archivo
    justo mientras otro proceso lo reemplaza da PermissionError: se reintenta
    un instante en vez de leerlo como vacío."""
    for i in range(4):
        try:
            with open(ruta_larga(path), encoding="utf-8-sig") as fh:
                v = json.load(fh)
            return v if isinstance(v, type(default)) else default
        except PermissionError:
            time.sleep(0.02 * (i + 1))
        except (OSError, ValueError):
            return default
    return default


class EstadoOcupado(TimeoutError):
    """El estado (cursores, motores…) no se pudo leer por un instante: otro
    proceso lo está reemplazando (Windows no deja abrir un archivo a mitad de
    os.replace). Se trata como el candado ocupado: el cierre se encola."""


def _leer_estado_json(path, intentos=6):
    """Como _leer_json para el ESTADO (cursores, motores): un archivo ausente
    es {}, pero uno que existe y no se pudo abrir NO se toma por vacío (se
    volvería a medir todo, con el costo doble): reintenta y, si sigue
    ocupado, levanta EstadoOcupado. Un JSON roto que persiste se aparta y
    queda en el log."""
    for i in range(intentos):
        try:
            with open(ruta_larga(path), encoding="utf-8-sig") as fh:
                v = json.load(fh)
            return v if isinstance(v, dict) else {}
        except FileNotFoundError:
            return {}
        except OSError:
            if i == intentos - 1:
                raise EstadoOcupado(path)
        except ValueError:
            if i == intentos - 1:
                try:
                    os.replace(path, "%s.roto-%d" % (path, int(time.time())))
                except OSError:
                    pass
                _log("estado_roto", archivo=os.path.basename(path))
                return {}
        time.sleep(0.02 * (i + 1))
    return {}


def _escribir_json(path, data):
    """Escritura atómica (tmp por proceso + os.replace). En Windows el
    reemplazo falla si otro proceso tiene abierto el destino en ese instante:
    se reintenta un poco antes de rendirse."""
    _mkdirs(os.path.dirname(path))
    guardar(path, json.dumps(data, ensure_ascii=False, separators=(",", ":")))


def guardar(destino, datos):
    """EL guardado atómico de métricas (texto o bytes): temporal único en la
    misma carpeta + _reemplazar. Lo usan el estado, el índice, exportar, las
    reescrituras y los sidecars de los parsers (regla 5: una sola copia). Si
    algo falla, el temporal se borra y el error sube. Las rutas pasan por
    ruta_larga: el sidecar de un respaldo con una ruta larga (Hermes: id de 64
    caracteres) llegaba a 260+ con el temporal, y en Windows no se escribía."""
    tmp = _tmp_de(destino)
    try:
        if isinstance(datos, (bytes, bytearray)):
            with open(ruta_larga(tmp), "wb") as fh:
                fh.write(datos)
        else:
            with open(ruta_larga(tmp), "w", encoding="utf-8", newline="\n") as fh:
                fh.write(datos)
        _reemplazar(tmp, destino)
    finally:
        _quitar_tmp(tmp)


def _quitar_tmp(tmp):
    try:
        if os.path.exists(ruta_larga(tmp)):
            os.remove(ruta_larga(tmp))
    except OSError:
        pass


def _tmp_de(path):
    """Temporal ÚNICO por proceso e hilo, en la misma carpeta (regla 1: pid y
    sufijo aleatorio; la salud corre en un hilo aparte en el hub)."""
    return "%s.%d.%s.tmp" % (path, os.getpid(), uuid.uuid4().hex[:8])


def _reemplazar(tmp, path, intentos=10):
    """os.replace(tmp, path) que aguanta Windows: ahí el reemplazo (y el
    borrado) fallan con PermissionError mientras OTRO proceso tiene abierto el
    destino (un lector sin candado: estado, salud, el hub). Se reintenta
    ~1 s; si no, el temporal se borra y el error sube (nunca se deja basura
    ni se finge que quedó escrito)."""
    try:
        for i in range(intentos):
            try:
                os.replace(ruta_larga(tmp), ruta_larga(path))
                return
            except PermissionError:
                if i == intentos - 1:
                    raise
                time.sleep(0.02 * (i + 1))
    finally:
        _quitar_tmp(tmp)


_MAQUINA = {}


def maquina_id():
    """Id anónimo de esta máquina: aleatorio, creado UNA vez en
    metricas/maquina.json. Sin hostname ni usuario del sistema. None si no se
    pudo crear ni leer. Cacheado por carpeta (importar escribe miles de filas)."""
    p = _ruta("maquina.json")
    if not _MAQUINA.get(p):
        _MAQUINA[p] = _maquina_id(p)
    return _MAQUINA[p]


def _maquina_id(p):
    d = _leer_json(p, {})
    if re.fullmatch(r"[0-9a-f]{32}", str(d.get("id") or "")):
        return d["id"]
    nuevo = {"id": uuid.uuid4().hex, "creado": iso(time.time())}
    try:
        _mkdirs(carpeta())
        if os.path.exists(p):              # existe pero ilegible: se rehace
            _escribir_json(p, nuevo)
            _log("maquina_regenerada")
            return nuevo["id"]
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(nuevo, fh)
        return nuevo["id"]
    except FileExistsError:                # otro proceso ganó la carrera
        d = _leer_json(p, {})
        return d.get("id") if re.fullmatch(r"[0-9a-f]{32}", str(d.get("id") or "")) else None
    except OSError:
        return None


def _crear_una_vez(p, campo, generar):
    """Lee `campo` de un JSON local o lo crea UNA vez (O_EXCL, 0600). Otro
    proceso que gane la carrera manda. None si no se pudo."""
    d = _leer_json(p, {})
    if d.get(campo):
        return d[campo]
    nuevo = {campo: generar(), "creado": iso(time.time())}
    try:
        _mkdirs(os.path.dirname(p))
        if os.path.exists(p):              # existe pero ilegible: se rehace
            _escribir_json(p, nuevo)
            return nuevo[campo]
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(nuevo, fh)
        return nuevo[campo]
    except FileExistsError:
        return _leer_json(p, {}).get(campo)
    except OSError:
        return None


#: reconstruir escribe en la generación NUEVA antes de cambiar el puntero
_GEN_FORZADA = []


def puntero():
    """generacion.json: {actual, previa, historial}. {} = generación 1."""
    return _leer_json(_ruta("generacion.json"), {})


def generacion():
    """Generación en la que se lee y escribe: la vigente (generacion.json →
    «actual»), o la que está construyendo `reconstruir`."""
    if _GEN_FORZADA:
        return _GEN_FORZADA[-1]
    v = puntero().get("actual")
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 1 else GENERACION_INICIAL


def _dir_gen(n=None):
    """Carpeta de una generación: la 1 es la raíz de metricas/ (ahí viven las
    filas F1); las demás, metricas/gen/<n>/."""
    n = generacion() if n is None else n
    return carpeta() if n == GENERACION_INICIAL else os.path.join(carpeta(), "gen", str(n))


def _g(*partes):
    """Ruta de un archivo de la GENERACIÓN (filas, índice, cursores, estado
    del motor, huellas, turnos). Lo demás (máquina, sal, nombres, recibos,
    latidos, apagado, cola) es de la máquina y no cambia con la generación."""
    return os.path.join(_dir_gen(), *partes)


_SAL = {}


def _sal():
    """Sal LOCAL de las huellas de pestañas y entregables (sal.json, aparte
    de maquina.json: sobrevive a un id de máquina nuevo). Jamás se exporta."""
    p = _ruta("sal.json")
    if not _SAL.get(p):
        _SAL[p] = _crear_una_vez(p, "sal", lambda: uuid.uuid4().hex + uuid.uuid4().hex)
    return _SAL[p]


def huella_local(tipo, nombre):
    """Huella con sal local de un nombre legible (pestaña, entregable): 12 hex.
    El nombre solo queda en nombres.json (local, borrable, nunca se exporta).
    None si no hay nombre."""
    if not nombre:
        return None
    if tipo == "fuente":
        # Windows: la misma ruta llega con otra capitalización según quién la
        # da (payload del motor, entorno, recorrido de carpetas); sin esto, una
        # exclusión o un recibo no reconocía su propia fuente. Mac/Linux: igual.
        nombre = os.path.normcase(nombre)
    sal = _sal() or ""
    h = hashlib.sha256(("%s|%s|%s" % (sal, tipo, nombre)).encode("utf-8", "replace"))
    return h.hexdigest()[:12]


_NOMBRES_NUEVOS = {}


def _nombrar(tipo, nombre):
    """huella_local + anota el nombre legible para nombres.json (se guarda al
    final del cierre con _guardar_nombres)."""
    h = huella_local(tipo, nombre)
    if h:
        _NOMBRES_NUEVOS[h] = [tipo, str(nombre)[:300]]
    return h


def _guardar_nombres():
    """Agrega los nombres nuevos a nombres.json (candado propio, atómico).
    Falla-suave: perder un nombre solo quita la etiqueta legible."""
    if not _NOMBRES_NUEVOS:
        return
    nuevos = dict(_NOMBRES_NUEVOS)
    try:
        from olock import file_lock
        p = _ruta("nombres.json")
        _mkdirs(carpeta())
        with file_lock(p, timeout=1.0):
            d = _leer_json(p, {})
            antes = len(d)
            for h, v in nuevos.items():
                d.setdefault(h, v)
            if len(d) != antes:
                _escribir_json(p, d)
        for h in nuevos:
            _NOMBRES_NUEVOS.pop(h, None)
    except Exception as exc:
        _log("nombres_fallo", error=type(exc).__name__)


def procedencia(motor):
    """Lo que un sidecar dice de sí mismo: esquema, quién lo escribió y la
    versión del motor (de la caché, sin lanzarlo)."""
    return {"schema": 1, "escrito_por": "workspace/%s" % (workspace_version() or "?"),
            "motor_version": _version_cacheada(motor)}


def nombres():
    """{huella: [tipo, nombre]} local (para mostrarle al propio usuario)."""
    return _leer_json(_ruta("nombres.json"), {})


_CONTEXTO = {}


def workspace_version():
    """Versión de Workspace de ESTE árbol (archivo VERSION). None si no hay."""
    if "version" not in _CONTEXTO:
        v = None
        try:
            with open(os.path.join(ROOT, "VERSION"), encoding="utf-8-sig") as fh:
                v = fh.read().strip()[:40] or None
        except OSError:
            pass
        _CONTEXTO["version"] = v
    return _CONTEXTO["version"]


def plataforma():
    return {"darwin": "mac", "win32": "windows"}.get(sys.platform, sys.platform.rstrip("0123456789") or None)


def instalacion():
    """«dev» si Workspace corre desde un checkout de desarrollo (dash/dev/
    existe: make-dist lo quita de la build de cliente), si no «cliente».
    Marca automática de los datos internos: no entran a normas ni ventas."""
    if "instalacion" not in _CONTEXTO:
        _CONTEXTO["instalacion"] = ("dev" if os.path.isdir(os.path.join(ROOT, "dash", "dev"))
                                    else "cliente")
    return _CONTEXTO["instalacion"]


def tz_min(e=None):
    """Desfase de la hora local respecto de UTC (minutos) en el instante `e`."""
    try:
        off = _dt.datetime.fromtimestamp(float(e if e else time.time())).astimezone().utcoffset()
        return int(off.total_seconds() // 60) if off is not None else None
    except (TypeError, ValueError, OverflowError, OSError):
        return None


_HUELLA_CEREBRO = {}


def cerebro_huella(brain):
    """Huella de los archivos de identidad del cerebro (doc de identidad +
    BOOT/NN-*.md, sin el perfil del socio): 12 hex del sha256 de nombres y
    contenidos. Cambia cuando cambia quién es el agente. None si no hay."""
    if not brain:
        return None
    try:
        import brain_identity
        docs = [(rel, p) for rel, p in brain_identity.core_docs(brain, socio="")
                if not rel.startswith("STATE/")]
    except Exception:
        return None
    if not docs:
        return None
    try:
        firma = tuple((rel, os.stat(p).st_size, os.stat(p).st_mtime_ns) for rel, p in docs)
    except OSError:
        return None
    hit = _HUELLA_CEREBRO.get(brain)
    if hit and hit[0] == firma:
        return hit[1]
    h = hashlib.sha256()
    try:
        for rel, p in docs:
            h.update(rel.encode("utf-8") + b"\0")
            with open(p, "rb") as fh:
                h.update(fh.read())
            h.update(b"\0")
    except OSError:
        return None
    _HUELLA_CEREBRO[brain] = (firma, h.hexdigest()[:12])
    return _HUELLA_CEREBRO[brain][1]


def _ruta_temporal(brain):
    """¿El cerebro vive en una carpeta temporal? (pruebas, demos)."""
    if not brain:
        return None
    import tempfile
    r = os.path.normcase(os.path.realpath(brain)).replace("\\", "/")
    bases = {os.path.normcase(os.path.realpath(tempfile.gettempdir())).replace("\\", "/")}
    if os.name != "nt":
        bases.update(("/tmp", "/private/tmp", "/var/tmp", "/private/var/folders",
                      "/var/folders"))
    return any(r == b or r.startswith(b.rstrip("/") + "/") for b in bases)


def modo_de(senales):
    """`modo` derivado de las señales crudas (también se guarda en la fila):
    prueba (cerebro en carpeta temporal) > eval > headless (sdk / exec) >
    autónomo (sesión de fondo del harness o lanzada por otra herramienta) >
    interactivo."""
    s = senales if isinstance(senales, dict) else {}
    if s.get("ruta_temporal"):
        return "prueba"
    if s.get("eval"):
        return "eval"
    ep, orig, src = (str(s.get(k) or "").lower() for k in ("entrypoint", "originator", "source"))
    if s.get("headless") or ep.startswith("sdk") or orig == "codex_exec" or src == "exec":
        return "headless"
    if s.get("review_running") or src in ("tool", "subagent", "mcp"):
        return "autonomo"
    return "interactivo"


def clase_error(v):
    """Clase de una respuesta de error del PROVEEDOR: código HTTP o etiqueta
    del motor → 4xx | 5xx | bloqueado | None (no se reconoce)."""
    if isinstance(v, int) and not isinstance(v, bool):
        return "5xx" if 500 <= v <= 599 else ("4xx" if 400 <= v <= 499 else None)
    s = str(v or "").lower()
    if not s:
        return None
    if any(x in s for x in ("content", "block", "refus", "safety", "policy", "moderat")):
        return "bloqueado"
    if any(x in s for x in ("server", "overload", "unavailable", "internal", "timeout",
                            "gateway", "5xx")):
        return "5xx"
    if any(x in s for x in ("invalid", "rate", "auth", "permission", "not_found", "quota",
                            "billing", "credit", "bad_request", "too_large", "4xx")):
        return "4xx"
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Utilidades públicas para los parsers (metricas_motores/)
# ═══════════════════════════════════════════════════════════════════════════

def epoch(v):
    """ISO-8601 (con Z u offset; sin zona = UTC) o epoch en s/ms → segundos
    UTC (float). None si no se entiende."""
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        x = float(v)
        if x <= 0:
            return None
        return x / 1000.0 if x > 1e11 else x
    if not isinstance(v, str):
        return None
    m = _TS_RE.match(v.strip())
    if not m:
        return None
    try:
        y, mo, d, h, mi, s = (int(g) for g in m.groups()[:6])
        frac = float("0." + m.group(7)) if m.group(7) else 0.0
        base = _dt.datetime(y, mo, d, h, mi, s, tzinfo=_dt.timezone.utc).timestamp()
        zona = m.group(8)
        if zona and zona != "Z":
            signo = -1 if zona[0] == "-" else 1
            zz = zona[1:].replace(":", "")
            base -= signo * (int(zz[:2]) * 3600 + int(zz[2:4]) * 60)
        return base + frac
    except (ValueError, OverflowError):
        return None


def iso(e):
    try:
        return _dt.datetime.fromtimestamp(float(e), _dt.timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _mes(e):
    try:
        return _dt.datetime.fromtimestamp(float(e), _dt.timezone.utc).strftime("%Y-%m")
    except (TypeError, ValueError, OverflowError, OSError):
        return "0000-00"


def entero(v):
    return v if isinstance(v, int) and not isinstance(v, bool) else None


def numero(v):
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def nombre_limpio(s, tope=80):
    """Nombre de skill saneado (sin espacios ni control): '' si nada."""
    return _NOMBRE_RE.sub("", str(s or ""))[:tope]


_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def nombre_modelo(s, tope=120):
    """Nombre de modelo tal como lo da el motor (Antigravity: «Gemini 4
    Argon (Medium)»): sin caracteres de control ni espacios de más."""
    return " ".join(_CONTROL_RE.sub("", str(s or "")).split())[:tope]


def recorrer(path, desde, fn, tramo, hasta_t=None, cola=False):
    """Lee el JSONL `path` desde el byte `desde` y llama fn(obj) por cada
    línea COMPLETA. → (offset_nuevo, completo). La línea a medio escribir no se
    consume (se lee la próxima vez), salvo `cola` (archivo quieto: se da por
    completa). `hasta_t` (time.monotonic) corta a mitad con completo=False.
    Una línea que no es JSON, o cuyo manejo revienta, se cuenta en
    tramo.ignoradas: un parser jamás tumba la medición entera."""
    pos = desde
    reloj = _Reloj(hasta_t)
    tope = tramo.tope_de(path)
    with open(ruta_larga(path), "rb") as fh:
        fh.seek(desde)
        for raw in fh:
            if not raw.endswith(b"\n") and not cola:
                break
            if tope is not None and pos + len(raw) > tope:
                tramo.cortado_por_tope = True       # lo demás es de un cierre posterior
                return pos, True
            if reloj.vencido(len(raw)):
                return pos, False
            pos += len(raw)
            obj = _objeto(raw, tramo)
            if obj is None:
                continue
            try:
                fn(obj)
            except Exception:
                tramo.ignoradas += 1
    return pos, True


def _objeto(raw, tramo):
    """Una línea JSONL (bytes) → dict, o None. Cuenta `leidas` (toda línea no
    vacía) e `ignoradas` (no es un objeto JSON). utf-8-sig: el BOM de Windows
    al principio de un archivo no rompe la primera línea."""
    linea = raw.strip()
    if not linea:
        return None
    tramo.leidas += 1
    try:
        obj = json.loads(linea.decode("utf-8-sig", "replace"))
    except ValueError:
        tramo.ignoradas += 1
        return None
    if not isinstance(obj, dict):
        tramo.ignoradas += 1
        return None
    return obj


def primera_linea(path):
    """El primer objeto JSON de un JSONL (cabeceras de los respaldos), con
    utf-8-sig. {} si no hay o no se entiende."""
    try:
        with open(ruta_larga(path), "rb") as fh:
            d = json.loads(fh.readline().decode("utf-8-sig", "replace") or "{}")
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


class _Reloj(object):
    """Mira la hora cada _CADA_BYTES leídos o cada 64 líneas: hay líneas de
    varios MB (Claude Code guarda los pedidos a la API enteros), así que
    contar solo líneas dejaba pasar el presupuesto de largo."""

    def __init__(self, hasta_t):
        self.hasta_t = hasta_t
        self.bytes = 0
        self.lineas = 0

    def vencido(self, n_bytes):
        if self.hasta_t is None:
            return False
        if self.bytes >= _CADA_BYTES or self.lineas >= 64:
            self.bytes = self.lineas = 0
            if time.monotonic() > self.hasta_t:
                return True
        self.bytes += n_bytes
        self.lineas += 1
        return False


def firma_archivo(path):
    """(tamaño, mtime_ns) para saber sin leer si un archivo cambió."""
    st = os.stat(ruta_larga(path))
    return [st.st_size, st.st_mtime_ns]


def recorrer_reescrito(path, cur, fn, tramo, hasta_t=None):
    """Para respaldos que Workspace REESCRIBE enteros en cada cierre (exports
    oficiales de OpenCode/OpenClaw, la copia del log de Antigravity): las
    filas ya medidas vuelven a estar al principio. Cursor = cuántas filas se
    midieron + huella de la última; si la fila n-1 sigue igual, se sigue
    desde ahí. Si no (el motor recortó o reescribió la historia) se relee
    todo y las huellas por id (tramo.nuevo) evitan contar dos veces.
    `hasta_t` corta entre filas: el cursor queda en la última medida (sin
    firma, así no parece al día) y se sigue en el próximo tramo.
    → (cursor nuevo {"n", "ultima", "firma"}, completo)."""
    if hasta_t is not None:
        # el reloj se mira ANTES de leer entero: si no alcanza a leerlo, ni se abre
        # (el cursor queda igual y se sigue en el próximo tramo)
        try:
            tam = os.path.getsize(ruta_larga(path))
        except OSError:
            tam = 0
        if time.monotonic() + tam / _BYTES_POR_S > hasta_t:
            return ({"n": cur.get("n"), "ultima": cur.get("ultima"), "firma": None}, False)
    with open(ruta_larga(path), "rb") as fh:
        filas = [raw for raw in fh.read().split(b"\n") if raw.strip()]
    n = int(cur.get("n") or 0)
    desde = 0
    if n and n <= len(filas) and \
            hashlib.sha1(filas[n - 1]).hexdigest()[:16] == cur.get("ultima"):
        desde = n
    elif n:
        tramo.avisos.add("respaldo_reescrito")
    reloj = _Reloj(hasta_t)
    tope = tramo.tope_de(path)
    hasta = len(filas)
    if tope is not None:          # cierre encolado: solo las filas que ya tenía
        acumulado, hasta = 0, 0
        for raw in filas:
            acumulado += len(raw) + 1
            if acumulado > tope:
                break
            hasta += 1
        if hasta < len(filas):
            tramo.cortado_por_tope = True
    for i in range(desde, hasta):
        raw = filas[i]
        if reloj.vencido(len(raw)):
            return ({"n": i, "ultima": hashlib.sha1(filas[i - 1]).hexdigest()[:16] if i else None,
                     "firma": None}, False)
        obj = _objeto(raw, tramo)
        if obj is None:
            continue
        try:
            fn(obj)
        except Exception:
            tramo.ignoradas += 1
    if hasta < len(filas):
        return ({"n": hasta, "ultima": hashlib.sha1(filas[hasta - 1]).hexdigest()[:16]
                 if hasta else None, "firma": None}, True)
    return ({"n": len(filas),
             "ultima": hashlib.sha1(filas[-1]).hexdigest()[:16] if filas else None,
             "firma": firma_archivo(path)}, True)


def al_dia_por_firma(path, cur):
    """`al_dia` de los parsers de respaldos reescritos: misma firma = nada nuevo."""
    return cur.get("firma") == firma_archivo(path)


class Vistos(object):
    """Índice de huellas por motor y mes. `ya(clave, ts)` dice si esa línea ya
    se contó (aquí o en otro archivo) y, si no, la marca a nombre del `dueno`
    actual (la sesión que se está midiendo). Las nuevas se escriben con
    guardar(); las de una sesión cuya fila no se pudo escribir se sueltan con
    olvidar() (si no, al volver a medir ese tramo saldrían «ya contadas»)."""

    def __init__(self, motor):
        self.motor = re.sub(r"[^a-z0-9_-]", "", str(motor).lower()) or "motor"
        self._meses = {}
        self.nuevas = {}             # mes → {huella: dueño}
        self.dueno = None

    def _archivo(self, mes):
        return _g("vistos", "%s-%s.txt" % (self.motor, mes))

    def _cargar(self, mes):
        """{huella: dueño corto | None} del fragmento del mes. Una línea es
        «huella\tdueño» (g2) o solo «huella» (F1: sin dueño = de otra sesión)."""
        s = self._meses.get(mes)
        if s is None:
            s = {}
            try:
                with open(self._archivo(mes), encoding="ascii", errors="ignore") as fh:
                    for ln in fh:
                        h, _, d = ln.strip().partition("\t")
                        if h:
                            s.setdefault(h, d or None)
            except OSError:
                pass
            self._meses[mes] = s
        return s

    def ya(self, clave, ts):
        """None = nueva (queda marcada) · "propia" = ya contada en esta misma
        sesión (otra línea del mismo mensaje, o el mismo evento en un tramo
        anterior de ESTA sesión) · "copia" = la contó OTRA sesión (historial
        copiado al continuar una sesión). El dueño de cada huella queda
        guardado: medir en N cortes da lo mismo que de una vez (A2-2)."""
        mes = _mes(ts) if ts else "0000-00"
        h = hashlib.sha1(clave.encode("utf-8", "replace")).hexdigest()[:16]
        nuevas = self.nuevas.setdefault(mes, {})
        if h in nuevas:
            return "propia" if nuevas[h] == self.dueno else "copia"
        guardadas = self._cargar(mes)
        if h in guardadas:
            return "propia" if self.dueno and guardadas[h] == _dueno_corto(self.dueno) else "copia"
        nuevas[h] = self.dueno
        return None

    def olvidar(self, dueno):
        for hs in self.nuevas.values():
            for h in [h for h, d in hs.items() if d == dueno]:
                del hs[h]

    def de(self, dueno):
        """{mes: [huellas]} que marcó `dueno` en esta corrida."""
        return {mes: sorted(h for h, d in hs.items() if d == dueno)
                for mes, hs in self.nuevas.items()
                if any(d == dueno for d in hs.values())}

    def fijar(self, por_mes, dueno=None):
        """Agrega huellas {mes: [huellas]} de `dueno` a los fragmentos
        (repetir es inofensivo: al leer, la primera manda)."""
        d = _dueno_corto(dueno) if dueno else None
        for mes, hs in (por_mes or {}).items():
            if not hs:
                continue
            p = self._archivo(mes)
            _mkdirs(os.path.dirname(p))
            with open(p, "a", encoding="ascii", newline="\n") as fh:
                fh.write(_sin_corte(p) + "".join(
                    (h + "\t" + d if d else h) + "\n" for h in hs))
            cargadas = self._cargar(mes)
            for h in hs:
                cargadas.setdefault(h, d)

    def guardar(self, dueno):
        """Fija las huellas nuevas de `dueno` y las suelta de `nuevas`."""
        self.fijar(self.de(dueno), dueno)
        self.olvidar(dueno)


_FALTA = object()


def _dueno_corto(dueno):
    """Dueño de una huella en disco: 8 hex de la sesión («motor:sid»)."""
    return hashlib.sha1(str(dueno).encode("utf-8", "replace")).hexdigest()[:8]


def _suma(a, b):
    if b is None:
        return a
    return (a or 0) + b


class Tramo(object):
    """Acumulador de UN tramo: solo números y nombres. Los parsers lo llenan;
    el núcleo lo convierte en fila."""

    def __init__(self, motor, brain, vistos, sid="", compartido=None):
        self.motor = motor
        self.brain = brain or ""
        self.vistos = vistos
        self.sid = sid or ""
        #: estado del MOTOR que cruza sesiones (metricas/motores.json): p. ej.
        #: el acumulado de costo donde una sesión continuó, o los últimos
        #: contadores de cada sesión de Hermes. Se lee con leer() y se cambia
        #: SOLO con anotar(): el núcleo guarda los cambios con el pendiente del
        #: tramo (si el proceso muere, se reaplican o se descartan con él).
        self.compartido = compartido if compartido is not None else {}
        self.cambios = {}            # {clave: {subclave: valor}}
        self._previos = {}           # para deshacer si la fila no queda
        self.hijos = []              # sesiones que continúan a esta (sid)
        self.pista_pestana = None    # nombre de pestaña que el MOTOR guardó (si hay)
        self.avisos = set()          # lo que no se pudo medir con certeza
        #: campos que ESTA fuente no puede medir → null en la fila (nunca 0):
        #: "interrupciones", "errores", "duracion_activa_s"
        self.sin_dato = set()
        self.copias = 0              # líneas copiadas de otra sesión
        self.excluir = []            # [(desde, hasta)] con las métricas apagadas
        #: cierre ENCOLADO: {ruta: bytes} que tenía cada archivo al encolarlo;
        #: se mide solo hasta ahí (lo posterior es de otro cierre)
        self.tope = None
        self.cortado_por_tope = False
        self.excluidas = 0           # eventos de esas ventanas (no se cuentan)
        self.modelos = {}
        self.sub = None              # tokens de subagentes, si hubo
        self.sub_archivos = set()
        self.llamadas = 0
        self.errores = 0
        self.interrupciones = 0
        self.mensajes = 0
        self.activa_ms = None
        self.skills = set()
        self.escritos = set()
        self.entregables = set()
        self.t0 = None
        self.t1 = None
        self.version = None
        self.cwd = None
        self.cuota = None            # la ÚLTIMA vista en el tramo (fin)
        self.cuota_inicio = None     # la PRIMERA (ver_cuota)
        self.ignoradas = 0
        self.duplicadas = 0
        self.nuevos = 0              # eventos nuevos contados (= hubo actividad)
        # ── g2 ──
        #: líneas leídas (las cuenta el núcleo), reconocidas (el parser
        #: entendió su tipo: reconocer()) y desconocidas por tipo
        #: (desconocer(tipo): solo NOMBRES de esquema). Leídas sin ninguna
        #: reconocida = formato desconocido → null y el cursor no avanza.
        self.leidas = 0
        self.reconocidas = 0
        self.desconocidas = {}
        self.formato_desconocido = False   # el parser lo detectó por estructura
        self.degradada = False       # fuente sin lo que la hace confiable (sin sidecar…)
        self.modelo_pedido = None
        self.esfuerzo = None
        self.permisos = None
        self.facturacion = None
        self.costo_tipo = None       # COSTO_TIPOS: lo pone el parser junto con el costo
        #: tokens según el TOTAL del motor ({modelo: CAMPOS_TOKENS}), para el
        #: cuadre contra lo contado por mensaje (Claude Code: modelUsage)
        self.tokens_motor = None
        self.comandos_no_cero = 0    # comandos que terminaron con código ≠ 0 (no son errores)
        self.respuestas_error = dict.fromkeys(CLASES_ERROR, 0)
        self.senales = {}            # señales crudas de modo que da la FUENTE
        self.skill_rutas = {}        # nombre → ruta del SKILL.md leído (su huella)
        self.turnos = []             # esqueleto por turno (sin texto): ver turno()
        self._turno = None
        self._pedidos = []           # n-gramas de los últimos pedidos (solo en memoria)

    def tope_de(self, path):
        """Bytes hasta donde medir `path` (None = sin tope). Un archivo que no
        existía al encolar tiene tope 0."""
        if not self.tope:
            return None
        return int(self.tope.get(os.path.abspath(path)) or 0)

    def leer(self, clave, sub, defecto=None):
        return (self.compartido.get(clave) or {}).get(sub, defecto)

    def anotar(self, clave, sub, valor, solo_si_falta=False):
        """Cambia el estado compartido del motor (visible enseguida para los
        tramos siguientes del mismo lote) y lo registra para el pendiente."""
        tabla = self.compartido.setdefault(clave, {})
        if solo_si_falta and sub in tabla:
            return
        prev = self._previos.setdefault(clave, {})
        if sub not in prev:
            prev[sub] = tabla.get(sub, _FALTA)
        tabla[sub] = valor
        self.cambios.setdefault(clave, {})[sub] = valor

    def deshacer(self):
        """Devuelve el estado compartido a como estaba antes de este tramo."""
        for clave, subs in self._previos.items():
            tabla = self.compartido.setdefault(clave, {})
            for sub, v in subs.items():
                if v is _FALTA:
                    tabla.pop(sub, None)
                else:
                    tabla[sub] = v
        self._previos, self.cambios = {}, {}

    def ver(self, clave, ts, actividad=True):
        """None si el evento es nuevo (y, con `actividad`, cuenta como
        actividad del tramo); "propia" / "copia" si ya estaba contado (ver
        Vistos.ya). `clave` = identidad estable de la línea en el motor (id de
        mensaje, de herramienta, de turno…); sin clave se cuenta siempre."""
        if ts is not None and any(a <= ts < b for a, b in self.excluir):
            self.excluidas += 1      # hecho con las métricas apagadas: no se mide
            return "excluida"
        if clave and self.vistos is not None:
            k = self.vistos.ya(clave, ts)
            if k:
                self.duplicadas += 1
                if k == "copia":
                    self.copias += 1
                return k
        if actividad:
            self.nuevos += 1
        return None

    def nuevo(self, clave, ts):
        """¿Es nuevo este evento? (atajo de ver() para lo que sí es actividad)."""
        return self.ver(clave, ts) is None

    def ts(self, e):
        if e is None:
            return
        self.t0 = e if self.t0 is None else min(self.t0, e)
        self.t1 = e if self.t1 is None else max(self.t1, e)

    def uso(self, modelo, toks, sub=False):
        """Suma un uso (dict con CAMPOS_TOKENS, valores int o None) a su modelo."""
        nombre = nombre_modelo(modelo) or "desconocido"
        m = self.modelos.setdefault(nombre, dict({k: None for k in CAMPOS_TOKENS}, llamadas=0))
        if self._turno is not None and not sub:
            self._turno["modelo"] = nombre
        m["llamadas"] += 1
        for k in CAMPOS_TOKENS:
            m[k] = _suma(m[k], toks.get(k))
        if sub:
            if self.sub is None:
                self.sub = dict({k: None for k in CAMPOS_TOKENS}, llamadas_modelo=0)
            self.sub["llamadas_modelo"] += 1
            for k in CAMPOS_TOKENS:
                self.sub[k] = _suma(self.sub[k], toks.get(k))

    def activa(self, ms):
        ms = numero(ms)
        if ms is not None and ms >= 0:
            self.activa_ms = (self.activa_ms or 0) + ms

    def skill(self, nombre, ruta=None):
        """Una skill usada. `ruta` = el SKILL.md leído: el núcleo saca su
        huella al cerrar en vivo (qué versión de la skill se usó)."""
        n = nombre_limpio(nombre)
        if n and (n in self.skills or len(self.skills) < _TOPE_LISTA):
            self.skills.add(n)
            if isinstance(ruta, str) and ruta and n not in self.skill_rutas:
                self.skill_rutas[n] = ruta

    def skills_de_texto(self, texto):
        """Skills cuyo SKILL.md aparece en una ruta o comando (el nombre y,
        para su huella, la ruta; el texto no se guarda)."""
        if isinstance(texto, str) and "skill.md" in texto.lower():
            for nombre, ruta in _rutas_skill(texto):
                self.skill(nombre, ruta)

    # ── g2: clasificación de líneas, señales y contadores nuevos ─────────────

    def reconocer(self):
        """El parser entendió el TIPO de la línea (aunque no cuente nada)."""
        self.reconocidas += 1

    def desconocer(self, tipo):
        """Línea de un tipo que el parser no conoce: se cuenta por NOMBRE de
        tipo (saneado; jamás contenido). Tope de tipos distintos."""
        n = nombre_limpio(tipo if isinstance(tipo, str) else
                          ("sin_tipo" if tipo is None else type(tipo).__name__), 40) or "otro"
        if n not in self.desconocidas and len(self.desconocidas) >= _TOPE_DESCONOCIDAS:
            n = "otros"
        self.desconocidas[n] = self.desconocidas.get(n, 0) + 1

    def ver_cuota(self, q):
        """Cuota vista en el tramo: la primera queda como inicio, la última como fin."""
        if q:
            if self.cuota_inicio is None:
                self.cuota_inicio = q
            self.cuota = q

    def respuesta_error(self, v):
        """Una respuesta de error del PROVEEDOR (código o etiqueta → clase_error)."""
        c = clase_error(v) if v not in CLASES_ERROR else v
        if c:
            self.respuestas_error[c] += 1

    def senal(self, nombre, valor):
        """Señal cruda de modo que trae la fuente (entrypoint, originator,
        source): solo enums saneados; la primera manda."""
        if nombre in SENALES_MODO and nombre not in self.senales and valor is not None:
            v = valor if isinstance(valor, bool) else (nombre_limpio(valor, 40) or None)
            if v is not None:
                self.senales[nombre] = v

    # ── g2: esqueleto por turno (sin texto) ──────────────────────────────────

    def _foto(self):
        toks = dict.fromkeys(_TOKENS_TURNO, 0)
        for m in self.modelos.values():
            for k in _TOKENS_TURNO:
                toks[k] += m.get(k) or 0
        return {"llamadas": self.llamadas, "errores": self.errores,
                "interrupciones": self.interrupciones, "toks": toks}

    def turno(self, ts, texto=None, origen="humano", ausente=None):
        """Empieza un turno: un pedido al agente (humano, cola, notificación o
        automático). `texto` se usa SOLO para su largo por cubeta y para
        sim_prev (similitud con los 5 pedidos anteriores del tramo) y se
        descarta: jamás se guarda. Lo que cuente el parser hasta el próximo
        turno (tokens, herramientas, errores…) queda en este turno."""
        self.cerrar_turno()
        if len(self.turnos) >= _TOPE_TURNOS:
            return
        largo = sim = None
        origen = origen if origen in ORIGENES_TURNO else "automatico"
        if isinstance(texto, str):
            largo = _cubeta(len(texto))
            if origen == "humano":
                ng = _ngramas(texto)
                if ng and self._pedidos:
                    sim = round(max(_jaccard(ng, p) for p in self._pedidos), 3)
                if ng:
                    self._pedidos = (self._pedidos + [ng])[-_PEDIDOS_SIM:]
        self._turno = {"ts": ts, "largo": largo, "origen_turno": origen,
                       "ausente": ausente if isinstance(ausente, bool) else None,
                       "sim_prev": sim, "r0": None, "r1": None, "modelo": None,
                       "compactacion": False, "foto": self._foto()}

    def respuesta(self, ts):
        """Un evento de la RESPUESTA del agente (modelo o herramienta) en `ts`:
        marca inicio y fin de la respuesta del turno abierto."""
        t = self._turno
        if t is None or ts is None:
            return
        t["r0"] = ts if t["r0"] is None else min(t["r0"], ts)
        t["r1"] = ts if t["r1"] is None else max(t["r1"], ts)

    def compactacion(self):
        """El motor compactó el contexto durante el turno abierto."""
        if self._turno is not None:
            self._turno["compactacion"] = True

    def cerrar_turno(self):
        """Cierra el turno abierto con lo contado desde que empezó."""
        t, self._turno = self._turno, None
        if t is None:
            return
        f0, f1 = t.pop("foto"), self._foto()
        t["tokens"] = {k: f1["toks"][k] - f0["toks"][k] for k in _TOKENS_TURNO}
        t["herramientas"] = f1["llamadas"] - f0["llamadas"]
        t["errores"] = f1["errores"] - f0["errores"]
        t["interrupcion"] = f1["interrupciones"] > f0["interrupciones"]
        self.turnos.append(t)

    def tiempo_humano(self):
        """Suma de los huecos entre el fin de una respuesta y el siguiente
        pedido HUMANO, con tope de _HUECO_HUMANO_S por hueco. Sin turnos en el
        tramo no hay huecos: 0 (lo que el motor no da lo anula COBERTURA)."""
        if not self.turnos:
            return 0.0
        total, previo = 0.0, None
        for t in self.turnos:
            if previo is not None and t["origen_turno"] == "humano" and t["ts"] is not None:
                fin = previo["r1"] if previo["r1"] is not None else previo["ts"]
                if fin is not None and t["ts"] > fin:
                    total += min(t["ts"] - fin, _HUECO_HUMANO_S)
            previo = t
        return round(total, 1)

    def escrito(self, ruta):
        if not isinstance(ruta, str) or not ruta.strip():
            return
        r = ruta.strip().replace("\\", "/")
        self.escritos.add(r.lower() if os.name == "nt" else r)
        rel = _entregable(r, self.brain)
        if rel and len(self.entregables) < _TOPE_LISTA:
            self.entregables.add(rel)


#: Una ruta absoluta sola (no un comando): /…, ~/…, C:\… o C:/…, sin
#: comillas, saltos ni operadores de shell.
_RUTA_SOLA_RE = re.compile(r"^(?:[/~]|[A-Za-z]:[\\/])[^\n\"'&|;<>`]*$")


def _rutas_skill(texto):
    """[(nombre, ruta del SKILL.md)] en una ruta o un comando. Una ruta sola
    (Read) vale entera aunque tenga espacios («MI AGENTE - CEREBRO»); en un
    comando, las rutas entre comillas y luego las sueltas."""
    t = texto.strip()
    if _RUTA_SOLA_RE.match(t) and t.lower().endswith("skill.md"):
        m = SKILL_RE.search(t)
        return [(m.group(1), t)] if m else []
    out = []
    for q in re.findall(r"\"([^\"]+)\"|'([^']+)'", t):
        r = q[0] or q[1]
        m = SKILL_RE.search(r)
        if m and r.lower().endswith("skill.md"):
            out.append((m.group(1), r))
    vistos = {n for n, _ in out}
    for m in _SKILL_RUTA_RE.finditer(t):
        if m.group(2) not in vistos:
            out.append((m.group(2), m.group(1)))
    return out


def _cubeta(n):
    for tope, nombre in CUBETAS_LARGO:
        if n < tope:
            return nombre
    return LARGO_MAYOR


def _ngramas(texto):
    """3-gramas de caracteres (minúsculas, espacios colapsados) de los
    primeros _SIM_CHARS: similitud sin depender del idioma. Solo en memoria."""
    t = " ".join(str(texto).lower().split())[:_SIM_CHARS]
    return frozenset(t[i:i + 3] for i in range(max(0, len(t) - 2)))


def _jaccard(a, b):
    return len(a & b) / float(len(a | b)) if a and b else 0.0


def _entregable(ruta, brain):
    """'deliverables/…' si `ruta` (ya con «/») cae bajo <brain>/deliverables/;
    '' si no. Solo la parte relativa: jamás la ruta absoluta del usuario."""
    if ruta.startswith("deliverables/"):
        return ruta
    if not brain:
        return ""
    bases = set()
    # también el cerebro tal como llegó si empieza con «/»: en Windows,
    # abspath de «/tmp/fx/brain» (las goldens anonimizadas del kit) le pone
    # la unidad, y la ruta del transcript, que no la trae, dejaba de calzar
    crudo = [brain] if brain.replace("\\", "/").startswith("/") else []
    for b in [os.path.abspath(brain), os.path.realpath(brain)] + crudo:
        bases.add(b.replace("\\", "/").rstrip("/") + "/deliverables/")
    cmp_r = ruta.lower() if os.name == "nt" else ruta
    for b in bases:
        cmp_b = b.lower() if os.name == "nt" else b
        if cmp_r.startswith(cmp_b) and len(ruta) > len(b):
            return "deliverables/" + ruta[len(b):]
    return ""


# ═══════════════════════════════════════════════════════════════════════════
# Registro de parsers (metricas_motores/)
# ═══════════════════════════════════════════════════════════════════════════

def parser(motor):
    """El módulo parser de `motor` o None (motor sin parser: solo recibo)."""
    try:
        import metricas_motores
        return metricas_motores.parser(motor)
    except Exception:
        return None


def parsers():
    try:
        import metricas_motores
        return dict(metricas_motores.registro())
    except Exception:
        return {}


def minar(engine, transcript_path, desde=None, vistos=None, brain=None,
          hasta_t=None, cola=False, sid=None, compartido=None, tope=None):
    """Mide lo NUEVO de un transcript a partir del cursor `desde` (dict del
    cursor de esa sesión; None = desde el principio), con el parser de
    `engine`. Solo números y nombres.

    → {"tramo": Tramo, "cursor": {cursor nuevo}, "completo": bool,
       "tramo_id": str, "costo": (usd, fuente, detalle) | None,
       "desde"/"hasta": marcas opcionales del parser}
    OSError si el transcript no se puede leer; ValueError si no hay parser."""
    p = parser(engine)
    if p is None:
        raise ValueError("sin parser para %s" % engine)
    cur = desde if isinstance(desde, dict) else {}
    if sid is None:
        try:
            sid = p.sesion(transcript_path)
        except Exception:
            sid = ""
    tramo = Tramo(engine, brain, vistos if vistos is not None else Vistos(engine),
                  sid=sid, compartido=compartido)
    tramo.excluir = intervalos_apagado() + _excluidas_de(engine, sid, transcript_path, brain)
    tramo.tope = tope
    res = p.minar(transcript_path, dict(cur), tramo, hasta_t=hasta_t, cola=cola)
    tramo.cerrar_turno()
    res["tramo"] = tramo
    res.setdefault("completo", True)
    res.setdefault("costo", None)
    # id del tramo = huella del RANGO medido (cursor de antes → de después):
    # único de verdad aunque un respaldo reescrito repita su número de filas,
    # y el mismo si un reintento mide exactamente lo mismo
    desde_ = {k: cur.get(k) for k in res["cursor"]}
    res["tramo_id"] = "t" + hashlib.sha1(json.dumps(
        [desde_, res["cursor"]], sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    # formato desconocido (se leyó y no se reconoció nada): la fila va con
    # los contadores en null, el cursor NO avanza (la fuente sigue protegida
    # y un parser arreglado la mide después) y el id sale solo del punto de
    # partida: repetir el cierre no apila filas
    res["formato_desconocido"] = bool(tramo.leidas and (tramo.formato_desconocido
                                                        or not tramo.reconocidas))
    if res["formato_desconocido"]:
        res["tramo_id"] = "u" + hashlib.sha1(json.dumps(
            [desde_], sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]
    return res


# ═══════════════════════════════════════════════════════════════════════════
# Cursores (write-ahead) y registro de filas
# ═══════════════════════════════════════════════════════════════════════════

def _clave(fila):
    tramo = str(fila.get("tramo") or "")
    if tramo.startswith("r:"):
        # el recibo de una corrida es UNO aunque cambie el id de sesión entre
        # intentos (captura fallida = run_id; reintento = id del motor)
        return "%s|-|%s" % (fila.get("motor"), tramo)
    return "%s|%s|%s" % (fila.get("motor"), fila.get("sesion_motor"), tramo)


#: Lo que define el CONTENIDO de una fila para saber si una clave repetida es
#: la misma fila (reintento) o otra distinta (conflicto que no se pisa).
_CAMPOS_CONTENIDO = ("motor", "sesion_motor", "tramo", "modelos", "herramientas",
                     "mensajes_usuario", "interrupciones", "costo_usd",
                     "duracion_activa_s", "skills", "escritos")


def _huella_fila(fila):
    if str(fila.get("tramo") or "").startswith("r:"):
        # un recibo de la misma corrida es la misma fila: el primero manda
        partes = [fila.get("motor"), fila.get("tramo")]
    elif fila.get("schema") == 1:
        partes = [fila.get(k) for k in _CAMPOS_CONTENIDO]   # F1: tal cual se indexó
    else:
        # g2: solo lo MEDIDO. Las huellas de skills y entregables se toman al
        # cerrar (un reintento puede ver otro archivo): no definen la fila
        partes = [fila.get(k) for k in _CAMPOS_CONTENIDO]
        partes[_CAMPOS_CONTENIDO.index("skills")] = sorted(
            s.get("nombre") for s in fila.get("skills") or () if isinstance(s, dict))
        esc = fila.get("escritos") if isinstance(fila.get("escritos"), dict) else None
        if esc is not None:
            partes[_CAMPOS_CONTENIDO.index("escritos")] = [
                esc.get("archivos"), sorted(e.get("h") for e in esc.get("entregables") or ()
                                            if isinstance(e, dict))]
    return hashlib.sha1(json.dumps(partes, sort_keys=True, default=str)
                        .encode("utf-8")).hexdigest()[:16]


def _mes_fila(fila):
    e = epoch(fila.get("fin")) or epoch(fila.get("inicio")) or time.time()
    return _mes(e)


def _archivo_mes(mes):
    return _g("corridas-%s.jsonl" % mes)


def _archivo_claves(mes):
    return _g("corridas-%s.claves" % mes)


class FilaEnConflicto(Exception):
    """Misma clave (motor|sesión|tramo) con contenido distinto."""


_CLAVES_CACHE = {}


def _claves_mes(mes):
    """{clave: huella} de un mes, desde su índice `corridas-AAAA-MM.claves`
    (una línea por fila: «clave\thuella\tbyte_final_en_el_jsonl»; no se
    relee el mes entero en cada cierre). Si el .jsonl llegó más lejos que el
    índice (el proceso murió entre la fila y su clave), solo se lee esa cola
    y se repara el índice; si no cuadra de otro modo, se rehace. Cache por
    (tamaño, mtime) de ambos archivos."""
    idx, filas_p = _archivo_claves(mes), _archivo_mes(mes)
    try:
        tam = os.path.getsize(filas_p)
    except OSError:
        tam = None
    if tam is None:
        return {}
    try:
        st = os.stat(idx)
    except OSError:
        st = None
    firma = (tam, st.st_size if st else None, st.st_mtime_ns if st else None)
    hit = _CLAVES_CACHE.get(idx)
    if hit and hit[0] == firma:
        return hit[1]
    claves, hasta = {}, 0
    if st is not None:
        try:
            with open(idx, encoding="utf-8", errors="replace") as fh:
                for ln in fh:
                    partes = ln.rstrip("\n").split("\t")
                    if len(partes) >= 2 and partes[0]:
                        claves.setdefault(partes[0], partes[1])
                        if len(partes) >= 3 and partes[2].isdigit():
                            hasta = max(hasta, int(partes[2]))
        except OSError:
            pass
    if st is None or hasta > tam or (hasta == 0 and tam and claves):
        claves = _rehacer_claves(mes)                # no cuadran: se rehace
    elif hasta < tam:
        claves = _reparar_claves(mes, claves, hasta)  # filas sin su clave
    try:
        st = os.stat(idx)
        firma = (os.path.getsize(filas_p), st.st_size, st.st_mtime_ns)
    except OSError:
        pass
    _CLAVES_CACHE[idx] = (firma, claves)
    return claves


def _filas_desde(path, desde=0):
    """(clave, huella, byte_final) de cada fila del .jsonl a partir de `desde`."""
    out = []
    try:
        with open(path, "rb") as fh:
            fh.seek(desde)
            pos = desde
            for raw in fh:
                pos += len(raw)
                try:
                    d = json.loads(raw.decode("utf-8", "replace"))
                except ValueError:
                    continue
                if isinstance(d, dict):
                    out.append((_clave(d), _huella_fila(d), pos))
    except OSError:
        pass
    return out


def _rehacer_claves(mes):
    claves, lineas = {}, []
    for c, h, pos in _filas_desde(_archivo_mes(mes)):
        if c not in claves:
            claves[c] = h
        lineas.append("%s\t%s\t%d\n" % (c, h, pos))
    guardar(_archivo_claves(mes), "".join(lineas))
    return claves


def _reparar_claves(mes, claves, hasta):
    nuevas = _filas_desde(_archivo_mes(mes), hasta)
    if nuevas:
        _log("indice_reparado", mes=mes, filas=len(nuevas))
        idx = _archivo_claves(mes)
        with open(idx, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(_sin_corte(idx) + "".join("%s\t%s\t%d\n" % x for x in nuevas))
        for c, h, _pos in nuevas:
            claves.setdefault(c, h)
    return claves


def _sin_corte(path):
    """'' o '\n': una última línea cortada no se pega a la siguiente."""
    try:
        with open(ruta_larga(path), "rb") as fh:
            fh.seek(-1, os.SEEK_END)
            return "" if fh.read(1) == b"\n" else "\n"
    except OSError:
        return ""


def registrar(fila):
    """Append de `fila` a metricas/corridas-AAAA-MM.jsonl (mes UTC de su fin)
    y de su clave al índice del mes, con candado. Idempotente por (motor,
    sesion_motor, tramo): → True si la escribió, False si ya estaba IGUAL.
    Misma clave con otro contenido → FilaEnConflicto (no se pisa ni se
    duplica: el caller no avanza y lo deja en el log)."""
    from olock import file_lock
    mes = _mes_fila(fila)
    path = _archivo_mes(mes)
    _mkdirs(os.path.dirname(path))
    clave, huella = _clave(fila), _huella_fila(fila)
    with file_lock(path, timeout=10):
        previa = _claves_mes(mes).get(clave)
        if previa is not None:
            if previa == huella:
                return False
            raise FilaEnConflicto(clave)
        with open(path, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(_sin_corte(path)
                     + json.dumps(fila, ensure_ascii=False, separators=(",", ":")) + "\n")
            fh.flush()
            final = fh.tell()
        # la clave lleva el byte final de su fila: si el proceso muere entre
        # las dos escrituras, la próxima lectura ve el .jsonl más largo que el
        # índice y repara solo esa cola (la fila jamás se duplica)
        idx = _archivo_claves(mes)
        with open(idx, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(_sin_corte(idx) + "%s\t%s\t%d\n" % (clave, huella, final))
        _CLAVES_CACHE.pop(_archivo_claves(mes), None)
    return True


def _existe(mes, clave):
    return bool(mes) and clave in _claves_mes(mes)


# ── estado: cursores por sesión + estado compartido por motor ──────────────

def _vistos_pendiente(ck):
    return _g("vistos", "pendientes",
                 hashlib.sha1(ck.encode("utf-8")).hexdigest()[:20] + ".json")


def _borrar(path, intentos=10):
    """Borra `path`. → True si ya no existe (borrado o ausente), False si no se
    pudo (sin permisos o, en Windows, abierto por otro proceso tras ~1 s de
    reintentos). Quien reporta un borrado lo cuenta solo con True (regla 3)."""
    for i in range(intentos):
        try:
            os.remove(path)
            return True
        except FileNotFoundError:
            return True
        except PermissionError:
            if i == intentos - 1:
                break
            time.sleep(0.02 * (i + 1))
        except OSError:
            break
    return not os.path.exists(path)


def _aplicar(motores, motor, cambios):
    est = motores.setdefault(motor, {})
    for clave, subs in (cambios or {}).items():
        if isinstance(subs, dict):
            est.setdefault(clave, {}).update(subs)


def _leer_estado():
    """(cursores, motores, hubo_recuperacion). cursores.json = por sesión;
    motores.json = estado compartido de cada motor (aparte: perder un
    archivo no borra el otro). Los pendientes se resuelven aquí: si su fila
    existe, el cursor avanza, se aplican sus cambios al motor y se fijan sus
    huellas; si no existe, se descartan (huellas incluidas) y el tramo se
    vuelve a medir."""
    curs = _leer_estado_json(_g("cursores.json"))
    if not isinstance(curs.get("sesiones"), dict):
        curs = {"schema": SCHEMA, "sesiones": {}}
    motores = _leer_estado_json(_g("motores.json"))
    viejo = curs.pop("motores", None)          # formato anterior (dentro de cursores)
    if isinstance(viejo, dict):
        for m, est in viejo.items():
            motores.setdefault(m, est)
    hubo = viejo is not None
    for ck, cur in curs["sesiones"].items():
        p = cur.pop("pendiente", None) if isinstance(cur, dict) else None
        if not isinstance(p, dict):
            continue
        hubo = True
        pv = _vistos_pendiente(ck)
        if _existe(p.get("mes"), p.get("clave")):
            _avanzar(cur, p.get("cursor") or {})
            _aplicar(motores, p.get("motor"), p.get("cambios"))
            if p.get("motor"):
                Vistos(p["motor"]).fijar(_leer_json(pv, {}), ck)
        else:
            _log("pendiente_descartado", sesion=ck)
        _borrar(pv)
    return curs, motores, hubo


def _avanzar(cur, nuevo):
    cur.update(nuevo)
    cur["tramos"] = int(cur.get("tramos") or 0) + 1
    cur["medido"] = iso(time.time())


# ── cola: cierres que no alcanzaron el candado ─────────────────────────────

def _marcas(path):
    """{ruta: bytes} del transcript, sus archivos hermanos (sidecars del
    respaldo) y sus subagentes, ahora: hasta dónde mide un cierre encolado."""
    import glob
    out = {}
    if not path:
        return out
    raiz = path[:-len(".jsonl")] if path.endswith(".jsonl") else path
    for c in [path] + glob.glob(glob.escape(raiz) + ".*") + \
            glob.glob(os.path.join(glob.escape(raiz), "subagents", "*.jsonl")):
        try:
            out[os.path.abspath(c)] = os.path.getsize(ruta_larga(c))
        except OSError:
            pass
    return out


def _encolar(tr):
    """Guarda el cierre (payload + atribución de ESE momento + hasta dónde
    llegaba cada archivo) para que lo procese el siguiente cierre o
    `importar`. Sin candado: archivo único. La cola tiene tope: lo más viejo
    se descarta (y queda en el log)."""
    d = _ruta("cola")
    _mkdirs(d)
    p = os.path.join(d, "%d-%s.json" % (int(time.time() * 1000), uuid.uuid4().hex[:8]))
    item = {k: tr.get(k) for k in ("motor", "brain", "atrib", "run_id", "data", "path", "sid")}
    item["tope"] = _marcas(tr.get("path"))
    _escribir_json(p, item)
    try:
        nombres = sorted(f for f in os.listdir(d) if f.endswith(".json"))
        for f in nombres[:max(0, len(nombres) - _TOPE_COLA)]:
            _borrar(os.path.join(d, f))
            _log("cola_descartada", archivo=f)
    except OSError:
        pass
    return p


def _tomar_cola(maximo=20):
    d = _ruta("cola")
    try:
        nombres = sorted(f for f in os.listdir(d) if f.endswith(".json"))[:maximo]
    except OSError:
        return []
    out = []
    for f in nombres:
        p = os.path.join(d, f)
        tr = _leer_json(p, {})
        if tr.get("motor") and tr.get("sid") and tr.get("path"):
            out.append((p, tr))
        else:
            _log("cola_ilegible", archivo=f)
            _borrar(p)
    return out


# ── rastro de fallos ────────────────────────────────────────────────────────

def _log(evento, **campos):
    """<estado>/logs/metricas.log: qué falló o se postergó (nombres, ids y
    números; jamás contenido). Falla-suave."""
    try:
        d = os.path.join(_paths.state_dir(), "logs")
        os.makedirs(d, exist_ok=True)
        rec = dict({k: str(v)[:200] for k, v in campos.items()},
                   evento=evento, ts=iso(time.time()))
        with open(os.path.join(d, "metricas.log"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


class _Candado(object):
    """El candado ÚNICO de metricas/ (cursores + huellas + filas)."""

    def __init__(self, timeout):
        self.timeout = timeout
        self._lk = None

    def __enter__(self):
        # reconstruir YA tiene el candado y mide con _lote, que lo pide otra
        # vez: dentro de una reconstrucción de este proceso no se vuelve a
        # tomar (un segundo flock del mismo proceso se bloquearía)
        if _GEN_FORZADA:
            return self
        from olock import file_lock
        _asegurar_carpeta()
        self._lk = file_lock(_ruta("estado"), timeout=self.timeout)
        self._lk.__enter__()
        return self

    def __exit__(self, *exc):
        if self._lk is not None:
            lk, self._lk = self._lk, None
            return lk.__exit__(*exc)
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Atribución
# ═══════════════════════════════════════════════════════════════════════════

def _slug(nombre):
    """Slug de pestaña: el MISMO que usa STATE/sessions/<socio>/<slug>.md."""
    try:
        import agent_brand
        return agent_brand.slug(nombre) or None
    except Exception:
        return re.sub(r"[^a-z0-9]+", "-", str(nombre or "").lower()).strip("-") or None


def _raiz(path):
    try:
        import memoria
        return memoria.raiz_cerebro(path)
    except Exception:
        return os.path.abspath(path)


def _cedula_id(brain, socio):
    if not socio:
        return None
    try:
        import usuarios
        for c in usuarios.cedulas(brain):
            if c.get("id") and (c.get("nombre") == socio or socio in (c.get("alias") or ())):
                return c["id"]
    except Exception:
        pass
    return None


def _agente(brain, usar_env=True):
    try:
        import neutral_hooks
        return neutral_hooks.agent_for_brain(brain, usar_env=usar_env) or None
    except Exception:
        return None


#: Cómo se supo quién y dónde (campo `atribucion` de cada fila):
#:   "registrada" — Workspace lo anotó al correr: la pestaña del entorno o del
#:                  payload al cerrar en vivo (y el socio de esta máquina), o,
#:                  para la historia, un recibo de continuity / el atado
#:                  sesión→pestaña de sessions_registry.
#:   "inferida"   — deducido sin que Workspace lo anotara para ESA sesión: la
#:                  pestaña de la sesión de la que continúa, o el nombre que
#:                  Workspace le puso a la sesión del motor al crearla
#:                  (`claude --name <pestaña>`) cuando coincide con una
#:                  pestaña que existe.
#:   null         — no se sabe. Una fila de la historia sin pestaña NO toma
#:                  el socio actual de la máquina (sería adivinar).
REGISTRADA, INFERIDA = "registrada", "inferida"


def _atribucion_vivo(brain, data):
    """Quién y dónde, al cerrar: el socio de ESTA máquina para ese cerebro (y
    su cédula), la pestaña del entorno o del payload, el agente del entorno o
    del registry/carpeta. Solo lee: jamás escribe en el cerebro."""
    socio = _socio_sin_ambiguedad(brain)
    tab = (os.environ.get("WORKSPACE_WS") or os.environ.get("ZENITH_WS")
           or data.get("tab") or "").strip()
    pestana = _slug(tab) if tab else None
    return {"agente": _agente(brain), "pestana": pestana, "socio": socio,
            "socio_id": _cedula_id(brain, socio),
            "atribucion": REGISTRADA if (pestana or socio) else None}


def _socio_de_pestana(brain, slug):
    """El socio dueño de la pestaña `slug`: la ÚNICA carpeta de
    STATE/sessions/ que la tiene (dos o ninguna → None)."""
    if not slug:
        return None
    try:
        import usuarios
        cands = [s for s in usuarios.carpetas(brain)
                 if os.path.isfile(os.path.join(brain, "STATE", "sessions", s, slug + ".md"))]
        return cands[0] if len(cands) == 1 else None
    except Exception:
        return None


def _con_pestana(brain, base, slug, como):
    """Atribución por la pestaña. El socio, solo sin ambigüedad (revisión
    #8): el de ESTA cuenta del sistema para el cerebro, y siempre que la
    pestaña no sea de otro socio (una pestaña ajena llega por Obsidian y no
    dice quién corrió la sesión en esta máquina). Si no, null."""
    de_la_pestana = _socio_de_pestana(brain, slug)
    de_la_cuenta = _socio_sin_ambiguedad(brain)
    socio = de_la_cuenta if de_la_pestana in (None, de_la_cuenta) else None
    return dict(base, pestana=slug, socio=socio, socio_id=_cedula_id(brain, socio),
                atribucion=como)


class _MapaImport(object):
    """Atribución de la historia, con las APIs públicas de lo que Workspace
    anota al correr: recibos de continuity (session_continuity.receipts) y el
    atado sesión→pestaña de esta máquina (sessions_registry.owner). Lo que
    no esté ahí se intenta inferir DESPUÉS de medir (inferir())."""

    def __init__(self):
        self._recibos = {}

    def _de_recibos(self, brain):
        idx = self._recibos.get(brain)
        if idx is None:
            idx = {}
            try:
                import session_continuity
                for r in (session_continuity.receipts(brain).get("runs") or {}).values():
                    if isinstance(r, dict) and r.get("session_id") and r.get("tab"):
                        idx[(r.get("engine") or "claude-code", str(r["session_id"]))] = r["tab"]
            except Exception:
                pass
            self._recibos[brain] = idx
        return idx

    def de(self, brain, motor, sid):
        base = {"agente": _agente(brain, usar_env=False), "pestana": None,
                "socio": None, "socio_id": None, "atribucion": None}
        tab = self._de_recibos(brain).get((motor, sid))
        slug = _slug(tab) if tab else None
        if not slug:
            try:
                import sessions_registry
                slug = sessions_registry.owner(brain, motor, sid) or None
            except Exception:
                slug = None
        return _con_pestana(brain, base, slug, REGISTRADA) if slug else base

    @staticmethod
    def inferir(brain, atrib, tramo):
        """Sin pestaña registrada: la de la sesión de la que continúa (el
        padre anotó su `continued-in`), o la pista que el motor guardó (el
        nombre que Workspace le dio a la sesión) si es una pestaña que existe."""
        padre = ((tramo.compartido.get("padres") or {}).get(tramo.sid) or {})
        if padre.get("pestana"):
            return _con_pestana(brain, atrib, padre["pestana"], INFERIDA)
        slug = _slug(tramo.pista_pestana) if tramo.pista_pestana else None
        if slug and _socio_de_pestana(brain, slug):
            return _con_pestana(brain, atrib, slug, INFERIDA)
        return atrib


# ═══════════════════════════════════════════════════════════════════════════
# Filas
# ═══════════════════════════════════════════════════════════════════════════

def cerebro_id(brain):
    """Cómo se nombra el cerebro en una fila: «<carpeta>#<sha1 corto de su
    ruta real>». Distingue dos cerebros con el mismo nombre sin guardar la
    ruta absoluta (que trae el usuario del sistema)."""
    if not brain:
        return None
    real = os.path.realpath(brain)
    # normcase: en Windows «C:\Users» y «c:\users» son el mismo cerebro (en
    # Mac y Linux no cambia nada: las filas ya escritas conservan su id)
    clave = os.path.normcase(real)
    return "%s#%s" % (os.path.basename(real.rstrip("\\/")) or "cerebro",
                      hashlib.sha1(clave.encode("utf-8", "replace")).hexdigest()[:8])


def _senales_workspace(brain, data, origen):
    """Señales de modo que pone WORKSPACE (no la fuente): cerebro en carpeta
    temporal y, en vivo, la sesión de fondo del harness (revisor/headless:
    WORKSPACE_REVIEW_RUNNING), una corrida de evals (WORKSPACE_EVAL_RUNNING)
    o un cierre que el payload marca headless."""
    s = {"ruta_temporal": _ruta_temporal(brain)}
    if origen == "interactivo":
        s["review_running"] = bool(os.environ.get("WORKSPACE_REVIEW_RUNNING"))
        if os.environ.get("WORKSPACE_EVAL_RUNNING"):
            s["eval"] = True
        if isinstance(data, dict) and data.get("headless") is True:
            s["headless"] = True
    return s


def _base_fila(motor, origen, brain, atrib, sesion, tramo_id, run_id, senales=None):
    """Lo común a toda fila g2 (medida o recibo), con TODAS las claves de
    CAMPOS_FILA (null = sin dato). Lo que solo vale «ahora» (versión de
    Workspace, huella del cerebro) no se pone en la historia importada."""
    if not run_id:      # estable: el mismo tramo da el mismo run_id al reintentar
        run_id = hashlib.sha1(("%s|%s|%s" % (motor, sesion, tramo_id))
                              .encode("utf-8")).hexdigest()[:32]
    vivo = origen == "interactivo"
    sen = {k: (senales or {}).get(k) for k in SENALES_MODO}
    fila = dict.fromkeys(CAMPOS_FILA)
    fila.update({
        "schema": SCHEMA, "generacion": generacion(), "run_id": run_id,
        "maquina": maquina_id(), "instalacion": instalacion(),
        "workspace_version": workspace_version() if vivo else None,
        "plataforma": plataforma(), "origen": origen,
        "modo": modo_de(sen), "modo_senales": sen,
        "motor": motor, "agente": atrib.get("agente"),
        "cerebro": cerebro_id(brain),
        "cerebro_huella": cerebro_huella(brain) if vivo else None,
        "pestana_h": atrib.get("pestana_h") or _nombrar("pestana", atrib.get("pestana")),
        "socio": atrib.get("socio"), "socio_id": atrib.get("socio_id"),
        "atribucion": atrib.get("atribucion"),
        "sesion_motor": sesion, "tramo": tramo_id})
    return fila


def _captura(estado, p, version, data, t=None):
    c = dict.fromkeys(CAMPOS_CAPTURA)
    c.update({"estado": estado, "parser": getattr(p, "VERSION", None),
              "verificado": _verificado(p, version),
              "captura_motor": (nombre_limpio((data or {}).get("capture_state"), 40) or None)
              if isinstance(data, dict) else None})
    if t is not None:
        c.update({"degradada": bool(t.degradada), "leidas": t.leidas,
                  "reconocidas": t.reconocidas, "desconocidas": dict(t.desconocidas),
                  "lineas_ignoradas": t.ignoradas, "duplicadas": t.duplicadas,
                  "copias": t.copias})
    return c


def _verificado(p, version):
    try:
        import metricas_motores
        return metricas_motores.verificado(p, version)
    except Exception:
        return "no"


#: costo_fuente de F1 → costo_tipo (para traducir filas viejas)
_TIPO_POR_FUENTE = (("claude-code:cost-state", "equivalente_api"),
                    ("hermes:actual_cost_usd", "facturado"),
                    ("hermes:estimated_cost_usd", "estimado"),
                    ("opencode:", "estimado"), ("openclaw:", "estimado"))


def _costo_tipo_de_fuente(fuente):
    f = str(fuente or "")
    for pre, tipo in _TIPO_POR_FUENTE:
        if f.startswith(pre):
            return tipo
    return None


def _servido(modelos):
    """El modelo que más respuestas dio (sin los cubos internos ni «desconocido»)."""
    cands = [(m.get("llamadas") or 0, n) for n, m in (modelos or {}).items()
             if isinstance(m, dict) and n != "desconocido" and not n.endswith(":internas")]
    return max(cands)[1] if cands else None


def _suma_tokens(modelos):
    tot = 0
    for m in (modelos or {}).values():
        if isinstance(m, dict):
            tot += sum(m.get(k) or 0 for k in ("entrada", "salida", "cache_lectura",
                                                "cache_escritura"))
    return tot


def _tokens_motor(t):
    """{modelos: lo que dice el TOTAL del motor, cuadre: contado/motor}. El
    cuadre fuera de ~1 es señal (llamadas laterales, formato roto), no error."""
    if not t.tokens_motor:
        return None
    motor_ = _suma_tokens(t.tokens_motor)
    return {"modelos": t.tokens_motor,
            "cuadre": round(_suma_tokens(t.modelos) / float(motor_), 4) if motor_ else None}


def _huella_archivo(path, tope=_HUELLA_MAX_BYTES):
    """(sha256[:8] | None, bytes | None) de un archivo; sin huella (pero con
    su tamaño) si pasa el tope o se acaba el plazo del cierre."""
    try:
        tam = os.path.getsize(path)
    except OSError:
        return None, None
    plazo = _PLAZO_HUELLAS[0]
    if tam > tope or (plazo is not None and time.monotonic() > plazo):
        return None, tam
    h = hashlib.sha256()
    try:
        with open(path, "rb") as fh:
            for bloque in iter(lambda: fh.read(1024 * 1024), b""):
                if plazo is not None and time.monotonic() > plazo:
                    return None, tam
                h.update(bloque)
    except OSError:
        return None, tam
    return h.hexdigest()[:8], tam


def _ruta_real(ruta, t, brain):
    r = os.path.expanduser(str(ruta).strip())
    if os.path.isabs(r):
        return r
    base = t.cwd if t.cwd and os.path.isdir(t.cwd) else brain
    return os.path.join(base, r) if base else r


def _skills_g2(t, brain, vivo):
    out = []
    for n in sorted(t.skills):
        huella = None
        if vivo and t.skill_rutas.get(n):
            huella = _huella_archivo(_ruta_real(t.skill_rutas[n], t, brain), 1024 * 1024)[0]
        out.append({"nombre": n, "huella": huella})
    return out


def _entregables_g2(t, brain, vivo):
    """Cada entregable: huella con sal de su ruta relativa (el nombre legible
    solo en nombres.json), extensión y, al cerrar en vivo, sha256 y tamaño."""
    out = []
    for rel in sorted(t.entregables):
        ext = os.path.splitext(rel)[1].lower()
        e = {"h": _nombrar("entregable", rel),
             "ext": (_NOMBRE_RE.sub("", ext)[:12] or None) if ext else None,
             "sha256_8": None, "bytes": None}
        if vivo and brain:
            e["sha256_8"], e["bytes"] = _huella_archivo(os.path.join(brain, *rel.split("/")))
        out.append(e)
    return out


#: tramo.sin_dato con nombres de F1 → campo de COBERTURA
_SIN_DATO_F1 = {"errores": "herramientas.errores"}
#: lo que un formato desconocido deja en null (todo lo medido)
_MEDIDOS = ("duracion_activa_s", "tiempo_humano_est_s", "modelos", "modelo_pedido",
            "modelo_servido", "esfuerzo", "permisos", "tokens_motor", "costo_usd",
            "costo_fuente", "costo_tipo", "facturacion", "cuota", "herramientas",
            "respuestas_error", "interrupciones", "mensajes_usuario", "skills",
            "escritos", "subagentes")


def cobertura_no(p):
    """Campos que el parser `p` declara «no» en su COBERTURA."""
    cob = getattr(p, "COBERTURA", None)
    if not isinstance(cob, dict):
        return set()
    return {c for c, v in cob.items() if isinstance(v, (tuple, list)) and v and v[0] == "no"}


def _poner_null(fila, campo):
    if "." in campo:
        a, b = campo.split(".", 1)
        if isinstance(fila.get(a), dict):
            fila[a][b] = None
    elif campo in fila:
        fila[campo] = None


def _aplicar_cobertura(fila, p, t):
    """Lo que el motor no da (COBERTURA «no») o no dio en este tramo
    (tramo.sin_dato) queda en null: nunca un 0 que parezca medido."""
    nulos = cobertura_no(p) | {_SIN_DATO_F1.get(c, c) for c in t.sin_dato}
    for campo in nulos:
        if campo != "turnos":
            _poner_null(fila, campo)
    if "turnos" in nulos:
        fila["tiempo_humano_est_s"] = None
    if "modelos" in nulos:
        fila["modelo_servido"] = None
    if fila.get("costo_usd") is None:
        fila["costo_fuente"] = fila["costo_tipo"] = None


def _fila_medida(motor, origen, brain, atrib, sesion, res, run_id, tramo_id=None, data=None):
    t = res["tramo"]
    vivo = origen == "interactivo"
    senales = dict(t.senales)
    senales.update({k: v for k, v in _senales_workspace(brain, data, origen).items()
                    if v is not None})
    fila = _base_fila(motor, origen, brain, atrib, sesion, tramo_id or res["tramo_id"], run_id,
                      senales)
    usd, fuente, detalle = res["costo"] or (None, None, None)
    p = parser(motor)
    version = t.version
    if version is None and vivo:
        # el transcript no la trae: la del binario instalado AHORA, solo de la
        # caché de engine_versions (jamás se lanza el motor en el cierre). En
        # la historia no: la instalada hoy no es la de esa sesión.
        version = _version_cacheada(motor)
    fila.update({
        "motor_version": version,
        "inicio": iso(t.t0) if t.t0 else None,
        "fin": iso(t.t1) if t.t1 else None,
        "tz_min": tz_min(t.t1 or t.t0),
        "duracion_pared_s": round(t.t1 - t.t0, 1) if t.t0 is not None and t.t1 is not None else None,
        "duracion_activa_s": round(t.activa_ms / 1000.0, 1) if t.activa_ms is not None else None,
        "tiempo_humano_est_s": t.tiempo_humano(),
        "modelos": t.modelos,
        "modelo_pedido": nombre_modelo(t.modelo_pedido) or None,
        "modelo_servido": _servido(t.modelos),
        "esfuerzo": nombre_limpio(t.esfuerzo, 40) or None,
        "permisos": nombre_limpio(t.permisos, 80) or None,
        "tokens_motor": _tokens_motor(t),
        "costo_usd": usd,
        "costo_fuente": fuente if usd is not None else None,
        "costo_tipo": ((t.costo_tipo if t.costo_tipo in COSTO_TIPOS else None)
                       or _costo_tipo_de_fuente(fuente)) if usd is not None else None,
        "facturacion": nombre_limpio(t.facturacion, 60) or None,
        "cuota": {"inicio": t.cuota_inicio, "fin": t.cuota} if t.cuota else None,
        "herramientas": {"llamadas": t.llamadas, "errores": t.errores,
                         "comandos_no_cero": t.comandos_no_cero},
        "respuestas_error": dict(t.respuestas_error),
        "interrupciones": t.interrupciones,
        "mensajes_usuario": t.mensajes,
        "skills": _skills_g2(t, brain, vivo),
        "escritos": {"archivos": len(t.escritos), "entregables": _entregables_g2(t, brain, vivo)},
        # sin subagentes = {"n": 0} (se midió: no hubo); null solo si el motor
        # no los da (COBERTURA «no», lo aplica _aplicar_cobertura)
        "subagentes": (dict(t.sub, n=len(t.sub_archivos)) if t.sub is not None
                       else {"n": len(t.sub_archivos)}),
        "captura": _captura("ok" if res["completo"] else "parcial", p, version, data, t),
    })
    if t.mensajes and not _suma_tokens(t.modelos) and "modelos" not in cobertura_no(p):
        t.avisos.add("sin_tokens")       # hubo mensajes y ningún token: ¿formato cambió?
    if t.avisos:
        fila["captura"]["avisos"] = sorted(t.avisos)
    _aplicar_cobertura(fila, p, t)
    if res.get("formato_desconocido"):
        # se leyó y no se reconoció nada: ningún número es confiable
        for k in _MEDIDOS:
            fila[k] = None
        fila["captura"]["estado"] = "formato_desconocido"
    for k in ("desde", "hasta"):
        if res.get(k) is not None:
            fila["captura"][k] = res[k]
    if detalle:
        fila["costo_detalle"] = detalle
    return fila


def _turnos_de(fila, t, p):
    """Filas de turnos-AAAA-MM.jsonl del tramo (tiempos relativos al inicio
    del tramo; sin texto). [] si el motor no da turnos o no hubo."""
    if "turnos" in cobertura_no(p) or "turnos" in t.sin_dato or not t.turnos \
            or fila["captura"]["estado"] == "formato_desconocido":
        return []
    base = t.t0
    # lo que el motor no da (COBERTURA «no») o no dio en este tramo
    # (sin_dato) va null también en el turno, como en la fila (K4)
    nulos = cobertura_no(p) | {_SIN_DATO_F1.get(c, c) for c in t.sin_dato}

    def rel(x):
        return round(x - base, 1) if x is not None and base is not None else None
    out = []
    for i, tu in enumerate(t.turnos):
        tu = dict(tu)
        if "interrupciones" in nulos:
            tu["interrupcion"] = None
        if "herramientas.errores" in nulos:
            tu["errores"] = None
        if "herramientas.llamadas" in nulos:
            tu["herramientas"] = None
        if "modelos" in nulos or "turnos.tokens" in nulos:
            tu["tokens"] = None
        if "modelos" in nulos:
            tu["modelo"] = None
        out.append({"schema": SCHEMA, "generacion": fila["generacion"], "motor": fila["motor"],
                    "sesion_motor": fila["sesion_motor"], "tramo": fila["tramo"], "n": i,
                    "t_rel_s": rel(tu["ts"]), "largo": tu["largo"],
                    "origen_turno": tu["origen_turno"], "ausente": tu["ausente"],
                    "sim_prev": tu["sim_prev"], "resp_ini_rel_s": rel(tu["r0"]),
                    "resp_fin_rel_s": rel(tu["r1"]), "modelo": tu["modelo"],
                    "tokens": tu["tokens"], "herramientas": tu["herramientas"],
                    "errores": tu["errores"], "interrupcion": tu["interrupcion"],
                    "compactacion": tu["compactacion"]})
    return out


def _fila_recibo(motor, origen, brain, atrib, sesion, run_id, data, estado, error=None):
    """Recibo sin medición (motor sin parser, transcript ausente o error):
    quién, qué y cuándo; lo medible queda en null."""
    inicio = epoch(data.get("started"))
    tardio = data.get("close_mode") == "reconciled"   # cierre tardío: fin desconocido
    fin = None if tardio else time.time()
    fila = _base_fila(motor, origen, brain, atrib, sesion,
                      "r:%s" % (run_id or "%s-%d" % (sesion, int(inicio or time.time()))),
                      run_id, _senales_workspace(brain, data, origen))
    p = parser(motor)
    version = _version_cacheada(motor)
    fila.update({
        "motor_version": version,
        "inicio": iso(inicio) if inicio else None,
        "fin": iso(fin) if fin else None,
        "tz_min": tz_min(fin or inicio),
        "duracion_pared_s": round(fin - inicio, 1) if inicio and fin and fin >= inicio else None,
        "captura": _captura(estado, p, version, data),
    })
    if error:
        fila["captura"]["error"] = error
    return fila


# ── lectura: cualquier esquema → forma g2 ───────────────────────────────────

def traducir(fila):
    """Fila tal como está en disco → forma g2 (todas las claves de
    CAMPOS_FILA). Las F1 (schema 1) conservan `schema: 1` (así se sabe que se
    midieron con F1) y lo que F1 no tenía queda en null. Jamás se reescriben
    en disco: la migración real es `reconstruir`."""
    if not isinstance(fila, dict) or fila.get("schema") != 1:
        return fila
    g = dict.fromkeys(CAMPOS_FILA)
    g.update({k: v for k, v in fila.items() if k != "pestana"})
    g["generacion"] = GENERACION_INICIAL
    g["pestana_h"] = huella_local("pestana", fila.get("pestana"))
    if isinstance(fila.get("skills"), list):
        g["skills"] = [{"nombre": s, "huella": None} for s in fila["skills"] if isinstance(s, str)]
    esc = fila.get("escritos")
    if isinstance(esc, dict):
        ents = []
        for rel in esc.get("entregables") or ():
            if isinstance(rel, str):
                ext = os.path.splitext(rel)[1].lower()
                ents.append({"h": huella_local("entregable", rel),
                             "ext": (_NOMBRE_RE.sub("", ext)[:12] or None) if ext else None,
                             "sha256_8": None, "bytes": None})
        g["escritos"] = {"archivos": esc.get("archivos"), "entregables": ents}
    h = fila.get("herramientas")
    if isinstance(h, dict):
        g["herramientas"] = {"llamadas": h.get("llamadas"), "errores": h.get("errores"),
                             "comandos_no_cero": None}
    if fila.get("cuota"):
        g["cuota"] = {"inicio": None, "fin": fila["cuota"]}
    if fila.get("costo_usd") is not None:
        g["costo_tipo"] = _costo_tipo_de_fuente(fila.get("costo_fuente"))
    g["modelo_servido"] = _servido(fila.get("modelos"))
    cap = dict.fromkeys(CAMPOS_CAPTURA)
    cap.update(fila.get("captura") or {})
    g["captura"] = cap
    return g


#: el binario de cada motor (= interactive.INTERACTIVE_CLIS[motor]["binary"];
#: un test vigila que coincidan). Importar `interactive` en el cierre costaba
#: ~30 ms (urllib, http) en cada proceso de cierre.
_BINARIOS = {"antigravity": "agy", "claude-code": "claude", "codex": "codex",
             "opencode": "opencode", "openclaw": "openclaw", "hermes": "hermes",
             "gemini": "gemini", "kiro": "kiro-cli", "copilot": "copilot",
             "cursor": "cursor-agent"}


def _version_cacheada(motor):
    """Versión del motor SIN ejecutarlo: la caché en disco de
    engine_versions (la llenan el hub y el doctor). None si no está."""
    try:
        import shutil
        import engine_versions
        binario = _BINARIOS.get(motor)
        if binario is None:
            import interactive
            binario = (interactive.INTERACTIVE_CLIS.get(motor) or {}).get("binary")
        exe = shutil.which(binario or "")
        if not exe:
            return None
        row = (_leer_json(engine_versions._disk_cache_path(), {}).get(exe) or {})
        if row.get("mtime") != os.path.getmtime(exe):
            return None
        v = engine_versions.parse(row.get("out"))
        return ".".join(str(x) for x in v) if v else None
    except Exception:
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Procesar un lote de sesiones bajo el candado
# ═══════════════════════════════════════════════════════════════════════════

def _lote(trabajos, origen_lote, presupuesto_s=None, candado_s=None, limite_s=None, fin_t=None,
          con_cola=True):
    """Cada trabajo: {motor, path, sid, brain, atrib, run_id, data, cola,
    inferir}. Mide lo nuevo de cada sesión y registra sus filas bajo el
    candado, en este orden (un proceso muerto a la mitad no duplica ni pierde):

      1. cada tramo queda como PENDIENTE en cursores.json, con sus cambios al
         estado del motor, y sus huellas nuevas en vistos/pendientes/;
      2. se escriben las filas;
      3. las huellas pasan a los fragmentos del mes;
      4. se escriben motores.json y cursores.json ya avanzados.

    Antes, procesa la cola de cierres que no alcanzaron el candado.
    `presupuesto_s` (o el plazo absoluto `fin_t`, en time.monotonic) acota la
    espera del candado y el tiempo de MEDIR, dejando margen para escribir;
    `limite_s` (importar) suelta el candado tras ese tiempo: → (filas
    escritas, trabajos que quedaron para otra toma)."""
    escritas, restantes = [], []
    if fin_t is None and presupuesto_s:
        fin_t = time.monotonic() + presupuesto_s
    if candado_s is None:
        candado_s = _CANDADO_VIVO
    if fin_t is not None:            # la espera también sale del presupuesto
        candado_s = max(0.1, min(candado_s, fin_t - time.monotonic() - _RESERVA_S))
    with _Candado(candado_s):
        t_ini = time.monotonic()
        hasta_t = max(t_ini + 0.5, fin_t - _RESERVA_S) if fin_t is not None else None
        # las huellas de entregables y skills salen del mismo plazo
        _PLAZO_HUELLAS[0] = (fin_t - _RESERVA_S / 2.0) if fin_t is not None else None
        curs, motores, sucio = _leer_estado()
        cola = _tomar_cola() if con_cola else []
        # orden: un cierre ENCOLADO de la misma sesión va antes que el propio
        # (mide hasta su fin; el propio, lo demás); después lo propio; al final
        # el resto de la cola, solo con el tiempo que sobre
        propias = {(t["motor"], t["sid"]) for t in trabajos}
        misma = [(a, t) for a, t in cola if (t.get("motor"), t.get("sid")) in propias]
        otras = [(a, t) for a, t in cola if (t.get("motor"), t.get("sid")) not in propias]
        items = ([("cola", a, t) for a, t in misma] + [("propio", None, t) for t in trabajos]
                 + [("cola", a, t) for a, t in otras])
        vistos = {}
        pendientes = []
        a_medias = []
        hechos, de_la_cola = 0, []
        for kind, archivo, tr in items:
            if kind == "propio" and limite_s is not None and hechos \
                    and time.monotonic() - t_ini > limite_s:
                break
            if kind == "cola" and archivo not in [a for a, _ in misma] and fin_t is not None \
                    and time.monotonic() > fin_t - _RESERVA_S:
                continue                     # sin tiempo: sigue en la cola
            if kind == "propio":
                hechos += 1
            else:
                de_la_cola.append(archivo)
            motor = tr["motor"]
            origen = tr.get("origen") or origen_lote
            ck = "%s:%s" % (motor, tr["sid"])
            cur = curs["sesiones"].setdefault(ck, {})
            v = vistos.setdefault(motor, Vistos(motor))
            v.dueno = ck
            compartido = motores.setdefault(motor, {})
            try:
                res = minar(motor, tr["path"], desde=cur, vistos=v, brain=tr["brain"],
                            hasta_t=hasta_t, cola=tr.get("cola", False), sid=tr["sid"],
                            compartido=compartido, tope=tr.get("tope"))
            except Exception as exc:
                v.olvidar(ck)
                if not cur:
                    curs["sesiones"].pop(ck, None)
                _log("minar_fallo", motor=motor, sesion=tr["sid"], error=type(exc).__name__)
                if tr.get("data") is not None:      # en vivo: queda el recibo
                    pendientes.append({"ck": None, "fila": _fila_recibo(
                        motor, origen, tr["brain"], tr["atrib"], tr["sid"], tr.get("run_id"),
                        tr["data"], "error", type(exc).__name__)})
                continue
            nuevo = dict(res["cursor"])
            t = res["tramo"]
            atrib = tr["atrib"]
            if tr.get("inferir") and not atrib.get("pestana"):
                atrib = _MapaImport.inferir(tr["brain"], atrib, t)
                tr["atrib"] = atrib
            if res.get("formato_desconocido"):
                # se leyó y no se entendió nada: fila en null, el cursor NO
                # avanza, sin huellas ni cambios al estado del motor
                v.olvidar(ck)
                t.deshacer()
                if not cur:
                    curs["sesiones"].pop(ck, None)
                _log("formato_desconocido", motor=motor, sesion=tr["sid"], version=t.version,
                     leidas=t.leidas, tipos=",".join(sorted(t.desconocidas)))
                pendientes.append({"ck": None, "fila": _fila_medida(
                    motor, origen, tr["brain"], atrib, tr["sid"], res, tr.get("run_id"),
                    data=tr.get("data"))})
                continue
            for hijo in t.hijos:     # quien continúe esta sesión hereda su pestaña
                t.anotar("padres", hijo, {"padre": tr["sid"], "pestana": atrib.get("pestana")},
                         solo_si_falta=True)
            fila = None
            if t.nuevos:
                fila = _fila_medida(motor, origen, tr["brain"], atrib, tr["sid"], res,
                                    tr.get("run_id"), data=tr.get("data"))
            elif tr.get("data") is not None and tr.get("run_id") and not getattr(
                    parser(motor), "SIN_RECIBO_VACIO", False) \
                    and tr["run_id"] not in (cur.get("corridas") or ()):
                # corrida envuelta sin nada nuevo en su transcript: igual deja su
                # recibo (lo medido es cero de verdad: se leyó y no hubo nada)
                fila = _fila_medida(motor, origen, tr["brain"], atrib, tr["sid"], res,
                                    tr["run_id"], tramo_id="r:%s" % tr["run_id"],
                                    data=tr.get("data"))
                fila["inicio"] = fila["inicio"] or iso(epoch(tr["data"].get("started")))
            if fila is None:
                # nada que registrar (solo líneas sin eventos o copias ya
                # contadas): el cursor avanza igual, sin tramo nuevo
                if any(cur.get(k) != val for k, val in nuevo.items()) or t.cambios:
                    cur.update(nuevo)
                    sucio = True
                v.guardar(ck)
                if not cur:
                    curs["sesiones"].pop(ck, None)
                continue
            if tr.get("plantilla"):
                _aplicar_plantilla(fila, tr["plantilla"])
            if tr.get("data") is not None and tr.get("run_id"):
                # la corrida ya dejó su fila: cerrarla otra vez (el cierre
                # tardío de pending_runs, un reintento) no deja otra (K5a)
                vistas_ = [x for x in cur.get("corridas") or () if x != tr["run_id"]]
                nuevo["corridas"] = (vistas_ + [tr["run_id"]])[-20:]
            cur["pendiente"] = {"clave": _clave(fila), "mes": _mes_fila(fila), "cursor": nuevo,
                                "motor": motor, "cambios": t.cambios}
            pendientes.append({"ck": ck, "fila": fila, "nuevo": nuevo, "v": v, "t": t, "tr": tr})
        restantes = list(trabajos[hechos:])
        if not pendientes and not sucio and not de_la_cola:
            return escritas, restantes
        # 1) pendientes y sus huellas, juntos
        for pe in pendientes:
            if pe["ck"]:
                _escribir_json(_vistos_pendiente(pe["ck"]), pe["v"].de(pe["ck"]))
        _escribir_json(_g("cursores.json"), curs)
        # 2) filas · 3) huellas firmes
        for pe in pendientes:
            ck = pe["ck"]
            try:
                if registrar(pe["fila"]):
                    escritas.append(pe["fila"])
            except FilaEnConflicto as exc:
                # misma clave, otro contenido: no se pisa, no se avanza, no se
                # fijan huellas — y queda dicho
                _log("fila_en_conflicto", clave=str(exc))
                if ck:
                    curs["sesiones"][ck].pop("pendiente", None)
                    pe["v"].olvidar(ck)
                    pe["t"].deshacer()
                    _borrar(_vistos_pendiente(ck))
                continue
            except Exception as exc:
                # como si el proceso muriera aquí: los pendientes se resuelven
                # en la próxima lectura (fila escrita → avanza; si no → se mide otra vez)
                _log("registrar_fallo", error=type(exc).__name__)
                return escritas, restantes
            if ck:
                pe["v"].guardar(ck)
                _borrar(_vistos_pendiente(ck))
                cur = curs["sesiones"][ck]
                cur.pop("pendiente", None)
                _avanzar(cur, pe["nuevo"])
                if pe["fila"]["captura"]["estado"] == "parcial" and pe.get("tr"):
                    a_medias.append(_pendiente_de(pe["tr"]))   # el goteo lo termina
                # el esqueleto por turno va DESPUÉS de su fila (si el proceso
                # muere aquí, se pierden turnos de un tramo, nunca filas)
                _escribir_turnos(pe["fila"], _turnos_de(pe["fila"], pe["t"],
                                                        parser(pe["fila"]["motor"])))
        # 4) estado del motor y cursores ya avanzados
        _escribir_json(_g("motores.json"), motores)
        _escribir_json(_g("cursores.json"), curs)
        for archivo in de_la_cola:
            _borrar(archivo)
        if a_medias:
            _goteo_pendientes(a_medias)
    _guardar_nombres()
    return escritas, restantes


_RETENCION_TURNOS_DIAS = 90


def _escribir_turnos(fila, turnos):
    """Agrega los turnos del tramo a turnos-AAAA-MM.jsonl (el mes de su fila)
    y borra los meses enteros fuera de la retención. Bajo el candado de
    métricas; falla-suave (los turnos son secundarios)."""
    if not turnos:
        return
    try:
        p = _g("turnos-%s.jsonl" % _mes_fila(fila))
        with open(p, "a", encoding="utf-8", newline="\n") as fh:
            fh.write(_sin_corte(p) + "".join(
                json.dumps(x, ensure_ascii=False, separators=(",", ":")) + "\n" for x in turnos))
        _podar_turnos()
    except Exception as exc:
        _log("turnos_fallo", error=type(exc).__name__)


def _podar_turnos(ahora=None):
    """Retención de 90 días: un mes de turnos se borra cuando TODO el mes
    quedó más atrás que eso."""
    limite = (ahora or time.time()) - _RETENCION_TURNOS_DIAS * 86400
    for f in os.listdir(_dir_gen()):
        m = re.match(r"turnos-(\d{4})-(\d\d)\.jsonl$", f)
        if not m:
            continue
        y, mo = int(m.group(1)), int(m.group(2))
        fin_mes = _dt.datetime(y + (mo == 12), mo % 12 + 1, 1,
                               tzinfo=_dt.timezone.utc).timestamp()
        if fin_mes < limite:
            _borrar(_g(f))


def _padres_sin_medir(tr, p, hasta):
    """Una sesión que se mide por PRIMERA vez puede continuar a otra (Claude
    Code copia el historial del padre al archivo nuevo con sus mismos ids y
    timestamps). Si el padre todavía no se midió, se mide ANTES: así la copia
    cae como duplicado en el hijo y no como suya. Se reconoce por el primer
    timestamp copiado, entre las fuentes de la misma carpeta que nacieron
    antes — del índice de fuentes (sin leer cabeceras). Acotado por `hasta`
    (time.monotonic). → trabajos de los padres."""
    motor, path = tr["motor"], tr["path"]
    curs = _leer_estado_json(_g("cursores.json")).get("sesiones") or {}
    if curs.get("%s:%s" % (motor, tr["sid"])):
        return []                        # ya se midió antes: no es nueva
    try:
        _cwd, ts = getattr(p, "cabecera", cabecera)(path)
        nac = _nacimiento(path)
    except OSError:
        return []
    if ts is None:
        return []
    d = os.path.dirname(os.path.abspath(path))
    al_dia = getattr(p, "al_dia", None)
    aviso = fecha_aviso()
    mapa = _MapaImport()
    cands = []
    for e in _indice_fuentes(hasta):
        if time.monotonic() > hasta:
            _log("padre_sin_tiempo", motor=motor, sesion=tr["sid"])
            break
        if e["motor"] != motor or e["ruta"] == path or os.path.dirname(e["ruta"]) != d:
            continue
        if e["nac"] >= nac or e["ts"] is None or abs(e["ts"] - ts) > 0.001:
            continue
        q, sid2 = e["ruta"], e["sid"]
        cur2 = curs.get("%s:%s" % (motor, sid2)) or {}
        try:
            if cur2 and al_dia and al_dia(q, cur2):
                continue
        except Exception:
            continue
        atrib, inferir = mapa.de(tr["brain"], motor, sid2), True
        if not _MIO[0] and (aviso is None or e["ts"] < aviso):
            # historia de ANTES del aviso: sin persona ni pestaña (revisión #6)
            atrib, inferir = _anonimo(atrib), False
        cands.append((e["nac"], {
            "motor": motor, "sid": sid2, "path": q, "brain": tr["brain"],
            "atrib": atrib, "run_id": None, "data": None, "inferir": inferir,
            "origen": "importado",
            "cola": (time.time() - os.path.getmtime(q)) > _COLA_QUIETA_S}))
    return [t for _, t in sorted(cands, key=lambda x: (x[0], x[1]["path"]))]


# ── índice de fuentes: enumerar la máquina sin leer lo que no cambió ────────

_INDICE_TTL_S = 600         # cada tanto se rehace entero (relojes de carpeta gruesos)


def _nac_de(st):
    b = getattr(st, "st_birthtime", None)
    if b is None:
        b = st.st_ctime if os.name == "nt" else st.st_mtime
    return float(b)


def _indice_dir(motor, par, d, prof, viejo, nuevo, completo, cab, hasta, estado):
    """Entradas de las fuentes bajo `d` (a `prof` carpetas de profundidad).
    Una carpeta cuyo mtime no cambió no se vuelve a listar ni a leer. Si se
    acaba el plazo (`hasta`), los archivos nuevos que falten no se leen: la
    carpeta queda marcada para listarla otra vez y el índice, incompleto."""
    try:
        st = os.stat(d)
    except OSError:
        return []
    k = "%s|%s" % (motor, d)
    e = viejo.get(k)
    if not (e and e.get("m") == st.st_mtime_ns and not completo):
        try:
            nombres_ = os.listdir(d)
        except OSError:
            return []
        prev = (e or {}).get("f") or {}
        f, sub = {}, []
        cortada = False
        for n in nombres_:
            q = os.path.join(d, n)
            if prof > 0:
                if os.path.isdir(q):
                    sub.append(n)
                continue
            try:
                if not par.es_fuente(n):
                    continue
                st2 = os.stat(q)
            except Exception:
                continue
            nac = _nac_de(st2)
            vieja = prev.get(n)
            if vieja and vieja[1] == nac and vieja[0] and vieja[2] is not None:
                f[n] = vieja                      # el mismo archivo: ya se leyó
                continue
            if hasta is not None and time.monotonic() > hasta:
                estado["incompleto"] = True      # se lee en otra vuelta
                cortada = True
                continue
            try:
                sid = par.sesion(q)
                ts = cab(par)(q)[1]
            except Exception:
                continue
            if sid:
                f[n] = [sid, nac, ts]
        e = {"m": None if cortada else st.st_mtime_ns, "sub": sorted(sub), "f": f}
    nuevo[k] = e
    out = [{"motor": motor, "sid": v[0], "ruta": os.path.join(d, n), "nac": v[1], "ts": v[2]}
           for n, v in e["f"].items()]
    if prof > 0:
        for n in e["sub"]:
            out += _indice_dir(motor, par, os.path.join(d, n), prof - 1, viejo, nuevo,
                               completo, cab, hasta, estado)
    return out


_INDICE_MEMO = {}


def _indice_fuentes(hasta=None, estado=None):
    """[{motor, sid, ruta, nac, ts}] de todas las fuentes de la máquina, con
    un índice en disco (indice_fuentes.json, estado de la máquina) que se
    invalida por carpeta (mtime): una carpeta sin cambios no se lista, y un
    archivo ya visto no se vuelve a abrir (sesión y primer timestamp
    cacheados). Así el goteo y el cierre no enumeran la máquina cada vez.
    Con `hasta` (time.monotonic) lo NUEVO solo se lee mientras haya tiempo:
    la primera vez en una máquina grande el índice se arma en varias
    vueltas (estado["incompleto"] lo dice). Los parsers sin
    raices()/es_fuente() se enumeran con fuentes()."""
    estado = estado if estado is not None else {}
    p = _ruta("indice_fuentes.json")
    idx = _leer_json(p, {})
    if idx.get("v") != 1:
        idx = {"v": 1, "dirs": {}, "t": 0}
    completo = time.time() - float(idx.get("t") or 0) > _INDICE_TTL_S
    viejo, nuevo = idx.get("dirs") or {}, {}

    def cab(par):
        return getattr(par, "cabecera", cabecera)
    out = []
    for motor, par in sorted(parsers().items()):
        raices = getattr(par, "raices", None)
        if callable(raices) and callable(getattr(par, "es_fuente", None)):
            try:
                rs = list(raices())
            except Exception:
                rs = []
            for raiz, prof in rs:
                out += _indice_dir(motor, par, raiz, int(prof), viejo, nuevo, completo, cab,
                                   hasta, estado)
            continue
        try:
            for sid, path in par.fuentes() if callable(getattr(par, "fuentes", None)) else ():
                try:
                    out.append({"motor": motor, "sid": sid, "ruta": path,
                                "nac": _nacimiento(path), "ts": None})
                except OSError:
                    continue
        except Exception:
            continue
    if completo or nuevo != viejo:
        try:
            refresco = completo and not estado.get("incompleto")
            _escribir_json(p, {"v": 1, "dirs": nuevo,
                               "t": time.time() if refresco else idx.get("t") or 0})
        except OSError:
            pass
    return out


def _fuentes(hasta=None, estado=None):
    """{(motor, sid): ruta} de los transcripts de la máquina (del índice). Si
    una sesión está en dos lugares (original y respaldo), gana el MÁS LARGO:
    el respaldo es una copia byte a byte, así que los cursores valen igual."""
    por = {}
    for e in _indice_fuentes(hasta, estado):
        por.setdefault((e["motor"], e["sid"]), []).append(e["ruta"])
    out = {}
    for k, rutas in por.items():
        if len(rutas) == 1:
            out[k] = rutas[0]
            continue
        mejor = None
        for r in rutas:
            try:
                tam = os.path.getsize(r)
            except OSError:
                continue
            if mejor is None or tam > mejor[1]:
                mejor = (r, tam)
        if mejor:
            out[k] = mejor[0]
    return out


def _fuentes_ordenadas(hasta=None, estado=None):
    """[(nacimiento, ruta_h, ruta, motor, sid)] de lo más viejo a lo más nuevo
    (padre antes que hijo: el hijo nace después), sin duplicados por sesión.
    La frontera del goteo se guarda con la huella de la ruta, no la ruta."""
    elegidas = _fuentes(hasta, estado)
    out = []
    for e in _indice_fuentes():
        if elegidas.get((e["motor"], e["sid"])) == e["ruta"]:
            out.append((e["nac"], huella_local("fuente", e["ruta"]), e["ruta"], e["motor"],
                        e["sid"]))
    out.sort()
    return out


# ── goteo: la historia se importa sola, un poco en cada cierre ──────────────

_TOPE_PEND_GOTEO = 20       # pendientes que mira cada goteo, como tope


def _pendiente_de(tr):
    """Lo que el goteo necesita para terminar el tramo de `tr`: la sesión y la
    huella de su fuente (jamás la ruta), el id del cerebro y, si venía de un
    cierre en vivo, su atribución (pestaña como huella) y su corrida."""
    d = {"ruta_h": huella_local("fuente", tr["path"]), "motor": tr["motor"], "sid": tr["sid"],
         "cerebro": cerebro_id(tr.get("brain"))}
    if tr.get("data") is not None:
        a = dict(tr.get("atrib") or {})
        if a.get("pestana") and not a.get("pestana_h"):
            a["pestana_h"] = huella_local("pestana", a["pestana"])
        a.pop("pestana", None)
        d.update(atrib=a, run_id=tr.get("run_id"), origen="interactivo")
    return d


def _pendientes(g):
    """Las pendientes de goteo.json (las de antes, con la ruta, se convierten)."""
    out = []
    for d in g.get("pendientes") or ():
        if not isinstance(d, dict):
            continue
        if d.get("ruta") and not d.get("ruta_h"):
            d = dict(d, ruta_h=huella_local("fuente", d.pop("ruta")))
        if d.get("ruta_h") and d.get("motor") and d.get("sid"):
            out.append(d)
    return out


def _goteo_pendientes(nuevos):
    """Agrega fuentes al goteo (tramos a medias, sesiones abiertas): una por
    sesión, la más reciente manda."""
    try:
        from olock import file_lock
        p = _g("goteo.json")
        _mkdirs(os.path.dirname(p))
        with file_lock(p, timeout=1.0):
            g = _leer_json(p, {})
            pend = {(d["motor"], d["sid"]): d for d in _pendientes(g)}
            for d in nuevos:
                pend.pop((d["motor"], d["sid"]), None)
                pend[(d["motor"], d["sid"])] = d
            g["pendientes"] = list(pend.values())[-_TOPE_COLA:]
            _escribir_json(p, g)
    except Exception as exc:
        _log("goteo_fallo", error=type(exc).__name__)


def fuentes_protegidas():
    """Rutas de fuentes que la retención (nightly) no debe borrar: las de
    cerebros de Workspace cuyo cursor no llegó al final (incluye formato
    desconocido, que no avanza) y las pendientes del goteo. Con las métricas
    apagadas, ninguna (no hay consumidor)."""
    if apagado():
        return set()
    curs = _leer_estado_json(_g("cursores.json")).get("sesiones") or {}
    conocidos, mapa = _cerebros_conocidos(), _MapaImport()
    fuentes_ = _fuentes()
    out = set()
    for (motor, sid), path in fuentes_.items():
        _t_, motivo = _trabajo(motor, sid, path, {}, curs, conocidos, mapa)
        if motivo not in ("al_dia", "fuera", "errores", "filtro"):
            out.add(path)
    for d in _pendientes(_leer_json(_g("goteo.json"), {})):
        r = fuentes_.get((d["motor"], d["sid"]))
        if r:
            out.add(r)
    return out


def goteo(presupuesto_s=_GOTEO_S, fin_t=None):
    """Importa la historia DE A POCO: cada cierre en vivo le dedica lo que le
    sobra (≤ _GOTEO_S), y TODO —enumerar incluido— respeta ese tope.

      1. lo pendiente (tramos a medias, sesiones que estaban abiertas), a lo
         más _TOPE_PEND_GOTEO por vez: una que sigue abierta se reconoce con
         un stat, sin leerla;
      2. una FRONTERA (nacimiento, huella de la ruta) sobre las fuentes del
         índice, de lo más viejo a lo más nuevo: cada fuente se examina una
         vez y una que crece la mide su propio cierre. Con la frontera al
         final («al día»), no vuelve a recorrerla hasta _GOTEO_QUIETO_S,
         aunque haya pestañas abiertas en otras ventanas (esas son
         pendientes, del paso 1).

    Reemplaza a la importación inicial de F1. → filas escritas."""
    if fin_t is None:
        fin_t = time.monotonic() + presupuesto_s
    limite = min(fin_t, time.monotonic() + presupuesto_s)
    if limite - time.monotonic() < 0.2:
        return 0
    g = _leer_json(_g("goteo.json"), {})
    pend = _pendientes(g)
    al_dia = bool(g.get("al_dia_t")) and time.time() - float(g["al_dia_t"]) < _GOTEO_QUIETO_S
    if al_dia and not pend:
        return 0
    curs = _leer_estado_json(_g("cursores.json")).get("sesiones") or {}
    conocidos, mapa = _cerebros_conocidos(), _MapaImport()
    por_id = {cerebro_id(b): b for b in conocidos.values()}
    resumen = {}
    trabajos, examinadas, siguen, resueltas = [], [], [], set()
    fuentes_ = None
    ind = {}
    for d in pend[:_TOPE_PEND_GOTEO]:               # 1) lo pendiente
        if time.monotonic() > limite:
            break
        if fuentes_ is None:
            fuentes_ = _fuentes(limite, ind)
        k = (d["motor"], d["sid"])
        r = fuentes_.get(k)
        if not r:
            if not ind.get("incompleto"):
                resueltas.add(k)                    # la fuente ya no existe
            continue
        try:
            quieta = time.time() - os.path.getmtime(r) >= _FUENTE_ACTIVA_S
        except OSError:
            resueltas.add(k)
            continue
        if _FUENTE_ACTIVA_S and not quieta:
            siguen.append(d)                        # sigue abierta: ni se lee
            continue
        brain = por_id.get(d.get("cerebro"))
        t, motivo = _trabajo(d["motor"], d["sid"], r, resumen, curs, conocidos, mapa,
                             cerebro_de=lambda *_a, _b=brain: _b)
        if t:
            t.pop("_orden", None)
            if d.get("origen") == "interactivo":    # el resto de un cierre en vivo
                t.update(atrib=d.get("atrib") or t["atrib"], run_id=d.get("run_id"),
                         origen="interactivo", inferir=False)
            trabajos.append(t)
        elif motivo == "abiertas":
            siguen.append(d)
        else:
            resueltas.add(k)                        # al día, ajena o ilegible: fuera
    frontera = tuple(g.get("frontera") or ())
    nueva, al_final = frontera, al_dia
    ordenadas = (_fuentes_ordenadas(limite, ind)
                 if not al_dia and time.monotonic() < limite else [])
    if ind.get("incompleto"):
        # el índice de la máquina todavía se está armando (máquina grande, primera
        # vez): la frontera no avanza sobre una lista a medias; se sigue armando
        ordenadas, al_final = [], False
    if ordenadas:                                   # 2) la frontera
        al_final = True
        for nac, rh, r, m, sid in ordenadas:
            if frontera and (nac, rh) <= (frontera[0], frontera[1]):
                continue
            if time.monotonic() > limite or len(trabajos) >= _LOTE_IMPORTAR:
                al_final = False
                break
            t, motivo = _trabajo(m, sid, r, resumen, curs, conocidos, mapa)
            if motivo == "abiertas":
                siguen.append({"ruta_h": rh, "motor": m, "sid": sid, "cerebro": None})
            elif t:
                t.pop("_orden", None)
                trabajos.append(t)
            examinadas.append((nac, rh, r))
    escritas, restantes = [], []
    if trabajos:
        try:
            escritas, restantes = _lote(trabajos, "importado", candado_s=0.2,
                                        fin_t=limite + _RESERVA_S, limite_s=presupuesto_s)
        except TimeoutError:
            return 0                                # el candado está ocupado: el próximo
    no_hechas = {(t["motor"], t["sid"]): t for t in restantes}
    rutas_no_hechas = {t["path"] for t in restantes}
    for nac, rh, r in examinadas:                   # la frontera avanza hasta la
        if r in rutas_no_hechas:                    # última examinada que se hizo
            al_final = False
            break
        nueva = (nac, rh)
    hechas = {(t["motor"], t["sid"]) for t in trabajos} - set(no_hechas)
    try:
        from olock import file_lock
        p = _g("goteo.json")
        _mkdirs(os.path.dirname(p))
        with file_lock(p, timeout=1.0):
            g2 = _leer_json(p, {})
            quedan = {(d["motor"], d["sid"]): d for d in _pendientes(g2)
                      if (d["motor"], d["sid"]) not in hechas
                      and (d["motor"], d["sid"]) not in resueltas}
            for d in siguen + [_pendiente_de(t) for t in no_hechas.values()]:
                quedan.setdefault((d["motor"], d["sid"]), d)
            vieja = tuple(g2.get("frontera") or ())
            if nueva:
                g2["frontera"] = list(max(vieja, nueva)) if vieja else list(nueva)
            g2["pendientes"] = list(quedan.values())[-_TOPE_COLA:]
            g2.pop("pendientes_v1", None)
            if al_final and not al_dia:
                g2["al_dia_t"] = time.time()        # la frontera llegó al final
            elif not al_final:
                g2.pop("al_dia_t", None)
            _escribir_json(p, g2)
    except Exception as exc:
        _log("goteo_fallo", error=type(exc).__name__)
    return len(escritas)


def _procesar_cola(fin_t=None):
    """Si hay cierres en cola y el candado está libre, los procesa con el
    tiempo que le quede a ESTE cierre (sin esperar el candado)."""
    try:
        if os.path.isdir(_ruta("cola")) and os.listdir(_ruta("cola")):
            _lote([], "interactivo", candado_s=0.2, fin_t=fin_t)
    except TimeoutError:
        pass
    except Exception as exc:
        _log("cola_fallo", error=type(exc).__name__)


def _cerebro(data):
    for cand in (os.environ.get("WORKSPACE_BRAIN"), data.get("cwd")):
        if cand and os.path.isdir(cand):
            return _raiz(cand)
    return _raiz(os.getcwd())


_TOPE_LATIDOS = 2 * 1024 * 1024   # latidos.jsonl: al pasar esto se queda la mitad nueva


def _anexar(path, registro, despues=None):
    """Append de UNA línea JSON bajo el candado del archivo (revisión #9: en
    Windows `a` no es atómico entre procesos — Python busca el final y
    escribe —, así que dos cierres a la vez podían pisarse). `despues` corre
    dentro del mismo candado (la rotación de latidos). Si el candado no llega
    a tiempo, se escribe igual: mejor una línea que ninguna.

    Por eso el anexo va con atomico.anexar: en Windows, con cuatro procesos
    anexando a la vez (~30 ms cada anexo), el candado no llegaba en el
    segundo de plazo en ~1 de cada 25, y ese `open(…, "a")` sin candado
    pisaba la línea de otro (PC, 2026-11-06: 12 de 600 recibos perdidos y
    líneas partidas). atomico.anexar la pone al final sin pisar nada, con o
    sin candado."""
    _mkdirs(os.path.dirname(path))
    linea = json.dumps(registro, ensure_ascii=False, separators=(",", ":")) + "\n"

    def escribir():
        atomico.anexar(path, _sin_corte(path) + linea)
        if despues:
            despues()
    try:
        from olock import file_lock
        with file_lock(path, timeout=1.0):
            escribir()
            return
    except TimeoutError:
        _log("anexar_sin_candado", archivo=os.path.basename(path))
    escribir()


def _latido(fase, rid, motor, ms=None, resultado=None, error=None):
    """latidos.jsonl: inicio y fin de cada cierre. Un inicio sin su fin es un
    cierre que el runner mató por tiempo (no deja otro rastro). Falla-suave."""
    try:
        p = _ruta("latidos.jsonl")

        def rotar():                         # dentro del candado del archivo
            if fase == "fin" and os.path.getsize(p) > _TOPE_LATIDOS:
                with open(p, "rb") as fh:
                    fh.seek(-(_TOPE_LATIDOS // 2), os.SEEK_END)
                    cola = fh.read().split(b"\n", 1)[-1]
                guardar(p, cola)
        _anexar(p, {"t": iso(time.time()), "fase": fase, "run_id": rid, "motor": motor,
                    "ms": ms, "resultado": resultado, "error": error}, despues=rotar)
        return True
    except Exception:
        return False


def _error_de(exc):
    """Nombre del error para un latido: tipo y, si es de disco, su errno."""
    import errno as _errno
    n = getattr(exc, "errno", None)
    return "%s:%s" % (type(exc).__name__, _errno.errorcode.get(n, n)) if n else type(exc).__name__


def _recibo(rid, motor, brain, atrib, sid, data, tpath):
    """El recibo del cierre, ANTES del candado y de medir: el denominador de
    cobertura y la llave para reconstruir (recibos-AAAA-MM.jsonl). Quién,
    qué, dónde y cuántos bytes tenía cada fuente al cerrar; jamás contenido
    ni rutas (la fuente va como huella con sal)."""
    ahora = time.time()
    if data.get("run_id") and _recibo_existe(rid, ahora):
        return None             # la misma corrida otra vez: un recibo por corrida (K5a)
    fuentes = [{"ruta_h": huella_local("fuente", r), "bytes": b, "filas": None}
               for r, b in sorted(_marcas(tpath).items())]
    sen = {k: v for k, v in _senales_workspace(brain, data, "interactivo").items()}
    rec = {
        "schema": SCHEMA, "run_id": rid, "t": iso(ahora), "motor": motor,
        "motor_version": _version_cacheada(motor), "sesion_motor": sid,
        "pestana_h": _nombrar("pestana", atrib.get("pestana")),
        "socio": atrib.get("socio"), "socio_id": atrib.get("socio_id"),
        "agente": atrib.get("agente"), "cerebro": cerebro_id(brain),
        "cerebro_huella": cerebro_huella(brain), "plataforma": plataforma(),
        "workspace_version": workspace_version(), "instalacion": instalacion(),
        "tz_min": tz_min(ahora), "modo_senales": {k: sen.get(k) for k in SENALES_MODO},
        "captura_motor": nombre_limpio(data.get("capture_state"), 40) or None,
        "fuentes": fuentes,
        "apagado": [[a, None if b == float("inf") else b] for a, b in intervalos_apagado()],
    }
    _anexar(_ruta("recibos-%s.jsonl" % _mes(ahora)), rec)
    _guardar_nombres()          # si el runner mata el proceso, el nombre ya quedó
    return rec


def _recibo_existe(rid, ahora):
    """¿Ya hay recibo de esta corrida (este mes o el anterior)?"""
    aguja = ('"run_id":%s' % json.dumps(rid)).encode("utf-8")
    for mes in {_mes(ahora), _mes(ahora - 32 * 86400)}:
        try:
            with open(_ruta("recibos-%s.jsonl" % mes), "rb") as fh:
                if aguja in fh.read():
                    return True
        except OSError:
            continue
    return False


def recibos():
    """Todos los recibos (orden de los archivos de mes). Locales: jamás se
    exportan."""
    try:
        nombres_ = sorted(f for f in os.listdir(carpeta())
                          if f.startswith("recibos-") and f.endswith(".jsonl"))
    except OSError:
        return
    for f in nombres_:
        try:
            with open(_ruta(f), encoding="utf-8", errors="replace") as fh:
                for ln in fh:
                    try:
                        d = json.loads(ln)
                    except ValueError:
                        continue
                    if isinstance(d, dict):
                        yield d
        except OSError:
            continue


#: ¿Este cierre lo disparó OTRO motor (Copilot, Cursor) con los ganchos de
#: Claude Code del cerebro? Medir el eco dejaba una fila falsa de «claude-code»
#: con el id de sesión de otro motor. La regla vive en events (la aplica el
#: runner a TODOS los listeners de session_end); aquí queda como defensa para
#: quien llame a al_cerrar / excluir_cierre directo.
eco_de_otro_motor = _events.eco_de_otro_motor


def al_cerrar(payload, presupuesto_s=PRESUPUESTO_VIVO):
    """Cierre de UNA sesión (hooks/metricas_cierre.py): Claude Code por su
    SessionEnd nativo (transcript_path, session_id, cwd) y los motores
    envueltos por interactive/pending_runs (engine, run_id, started, tab,
    session_id, transcript_path). → la fila escrita o None. Jamás levanta.

    Orden: latido de inicio → RECIBO (sin candado: si el runner mata al
    proceso o el candado no llega, el cierre igual quedó contado) → medir
    bajo el candado (o encolar) → latido de fin con el resultado. Un recibo
    sin transcript no necesita el candado (no toca cursores). Todo fallo
    queda en el log y en el latido; disco lleno o sin permisos no rompe el
    cierre de la sesión."""
    data = payload if isinstance(payload, dict) else {}
    if eco_de_otro_motor(data):
        return None                   # lo mide el cierre de su wrapper
    motor = str(data.get("engine") or "claude-code")
    t0 = time.monotonic()
    if data.get("closed_by") == "x":
        # la X: lo que ya pasó desde que llegó también cuenta
        ya = max(0.0, time.time() - (numero(data.get("x_at")) or time.time()))
        presupuesto_s = max(0.5, min(presupuesto_s, PRESUPUESTO_X - ya))
    fin_t = t0 + presupuesto_s                       # TODO el cierre cabe aquí
    rid = str(data.get("run_id") or "") or uuid.uuid4().hex
    estado = {"resultado": None, "error": None}

    def ms():
        return int((time.monotonic() - t0) * 1000)
    try:
        if apagado_por_entorno():
            excluir_cierre(data)          # ESTA sesión, desde que empezó
            return None
        if apagado_por_ajuste():
            _marcar_apagado()
            return None
        _asegurar_carpeta()
        _latido("inicio", rid, motor)
        _marcar_encendido()
        fila = _cerrar(data, motor, rid, fin_t, presupuesto_s, estado)
        return fila
    except FilaEnConflicto as exc:
        _log("fila_en_conflicto", clave=str(exc))
        estado.update(resultado="conflicto")
        return None
    except Exception as exc:
        _log("cierre_fallo", motor=motor, error=_error_de(exc))
        estado.update(resultado="error", error=_error_de(exc))
        return None
    finally:
        if estado["resultado"] is not None:
            _latido("fin", rid, motor, ms(), estado["resultado"], estado["error"])


def _cerrar(data, motor, rid, fin_t, presupuesto_s, estado):
    brain = _cerebro(data)
    p = parser(motor)
    tpath = str(data.get("transcript_path") or "")
    if p is not None and not (tpath and os.path.isfile(ruta_larga(tpath))):
        buscar = getattr(p, "transcript_de_cierre", None)
        if buscar:          # p. ej. Codex con el respaldo apagado
            try:
                tpath = buscar(brain, data) or ""
            except Exception:
                tpath = ""
    atrib = _atribucion_vivo(brain, data)
    run_id = str(data.get("run_id") or "") or None
    sid = str(data.get("session_id") or "") or None
    if sid and sid == run_id:
        sid = None        # la captura no encontró la sesión: es el id de Workspace
    medible = p is not None and tpath and os.path.isfile(ruta_larga(tpath))
    if medible:
        try:
            sid = p.sesion(tpath) or sid
        except Exception:
            pass
    rec = None
    try:
        rec = _recibo(rid, motor, brain, atrib, sid, data, tpath if medible else "")
    except Exception as exc:
        # sin recibo (disco lleno, sin permisos…): se sigue midiendo igual
        _log("recibo_fallo", motor=motor, error=_error_de(exc))
        estado["error"] = "recibo:" + _error_de(exc)
    if not medible:
        fila = _fila_recibo(motor, "interactivo", brain, atrib, sid, run_id, data,
                            "sin_parser" if p is None else "sin_transcript")
        escrita = registrar(fila)
        _guardar_nombres()
        _registrar_cambios(rec, None)
        _procesar_cola(fin_t)
        estado["resultado"] = "recibo"
        return fila if escrita else None
    tr = {"motor": motor, "brain": brain, "atrib": atrib, "run_id": run_id,
          "data": data, "path": tpath, "sid": sid or "run:%s" % (run_id or "?")}
    padres = []
    try:
        padres = _padres_sin_medir(tr, p, min(fin_t - _RESERVA_S, time.monotonic() + _PADRES_S))
    except Exception as exc:
        _log("padres_fallo", motor=motor, error=type(exc).__name__)
    try:
        filas_, _resto = _lote(padres + [tr], "interactivo", fin_t=fin_t)
    except TimeoutError:
        _encolar(tr)
        _log("candado_ocupado_en_cola", motor=motor, sesion=tr["sid"])
        estado["resultado"] = "cola"
        return None
    propias = [f for f in filas_ if f.get("sesion_motor") == tr["sid"]
               and f.get("motor") == motor]
    fila = (propias or [None])[0]
    estado["resultado"] = ("formato_desconocido" if fila and fila["captura"]["estado"]
                           == "formato_desconocido" else ("fila" if fila else "sin_cambios"))
    _registrar_cambios(rec, fila)
    try:            # lo que sobre del presupuesto, a la historia
        goteo(fin_t=fin_t - _RESERVA_S)
    except Exception as exc:
        _log("goteo_fallo", error=type(exc).__name__)
    return fila


# ═══════════════════════════════════════════════════════════════════════════
# Importar la historia que ya existe en la máquina
# ═══════════════════════════════════════════════════════════════════════════

def cabecera(path, n=80):
    """(cwd, primer timestamp) de las primeras líneas de un JSONL: busca `cwd`
    en la línea o en su `payload`. Los parsers con otra forma la redefinen."""
    cwd, ts = None, None
    try:
        with open(ruta_larga(path), "rb") as fh:
            for i, raw in enumerate(fh):
                if i >= n or (cwd and ts):
                    break
                try:
                    d = json.loads(raw.decode("utf-8", "replace"))
                except ValueError:
                    continue
                if not isinstance(d, dict):
                    continue
                pl = d.get("payload") if isinstance(d.get("payload"), dict) else {}
                c = d.get("cwd") or pl.get("cwd")
                if cwd is None and isinstance(c, str) and c:
                    cwd = c
                e = epoch(d.get("timestamp"))
                if ts is None and e:
                    ts = e
    except OSError:
        pass
    return cwd, ts


def _nacimiento(path):
    """Fecha de creación del archivo (Mac: st_birthtime; Windows: st_ctime);
    donde no existe (Linux) cae a mtime."""
    try:
        st = os.stat(ruta_larga(path))
    except OSError:
        return 0.0
    b = getattr(st, "st_birthtime", None)
    if b is None:
        b = st.st_ctime if os.name == "nt" else st.st_mtime
    return float(b)


def _cerebros_conocidos():
    """{normcase(realpath): realpath} de los cerebros del registry."""
    out = {}
    try:
        import dispatch
        for a in dispatch.load_registry().get("agents", []):
            try:
                cfg = dispatch.load_agent_cfg(a)
                b = dispatch.resolve_brain(a.get("name", ""), cfg)
            except Exception:
                continue
            if b and os.path.isdir(b):
                out[os.path.normcase(os.path.realpath(b))] = os.path.realpath(b)
    except Exception:
        pass
    return out


def _cerebro_por_carpeta(path, conocidos):
    """El cerebro conocido cuya carpeta de respaldo (session_paths) es la
    carpeta de `path`. None si ninguno."""
    try:
        import session_paths
        enc = os.path.basename(os.path.dirname(os.path.abspath(path)))
        for b in conocidos.values():      # la ruta real (con su caja en Windows)
            if os.path.basename(session_paths.session_dir(b)) == enc:
                return b
    except Exception:
        pass
    return None


def _es_cerebro(brain, conocidos):
    """¿Es un cerebro de Workspace? Del registry, o cableado por Workspace
    (su settings.local.json llama al runner de hooks)."""
    if os.path.normcase(os.path.realpath(brain)) in conocidos:
        return True
    try:
        with open(os.path.join(brain, ".claude", "settings.local.json"),
                  encoding="utf-8", errors="replace") as fh:
            return "workspace_hook" in fh.read()
    except OSError:
        return False


_RESUMEN = {"sesiones": 0, "filas": 0, "fuera": 0, "al_dia": 0, "abiertas": 0, "errores": 0}


def _trabajo(motor, sid, path, resumen, curs, conocidos, mapa, todas=False, cerebro_de=None,
             solo=None, antes_de=None):
    """El trabajo de medir UNA fuente de la historia, o (None, motivo):
    abiertas | al_dia | errores | fuera | filtro. Cuenta en `resumen`."""
    r = resumen.setdefault(motor, dict(_RESUMEN))
    r["sesiones"] += 1
    p = parser(motor)
    try:
        mtime = os.path.getmtime(path)
        al_dia = getattr(p, "al_dia", None)
        if not todas and al_dia and al_dia(path, curs.get("%s:%s" % (motor, sid)) or {}):
            r["al_dia"] += 1
            return None, "al_dia"
        if not todas and _FUENTE_ACTIVA_S and time.time() - mtime < _FUENTE_ACTIVA_S:
            # sesión abierta (otra pestaña): la mide SU cierre; importarla
            # a medias la partiría en tramos que no son suyos (A2-2)
            r["abiertas"] += 1
            return None, "abiertas"
        cwd, ts = getattr(p, "cabecera", cabecera)(path)
    except Exception:
        r["errores"] += 1
        return None, "errores"
    brain = _raiz(cwd) if cwd and os.path.isdir(cwd) else None
    if not brain:
        # logs sin cwd (Antigravity): el respaldo vive en
        # transcripts-backup/<enc>/ y <enc> es la codificación del cerebro
        brain = _cerebro_por_carpeta(path, conocidos)
    if not (brain and _es_cerebro(brain, conocidos)) and cerebro_de:
        brain = cerebro_de(motor, sid) or brain
    if not brain or not _es_cerebro(brain, conocidos):
        r["fuera"] += 1
        return None, "fuera"
    if solo and os.path.normcase(os.path.realpath(brain)) != solo:
        return None, "filtro"
    if antes_de is not None and (ts or mtime) > antes_de:
        return None, "filtro"   # (el hijo copia el primer timestamp del padre: empate = entra)
    atrib, inferir = mapa.de(brain, motor, sid), True
    aviso = fecha_aviso()
    if not _MIO[0] and (aviso is None or (ts or mtime) < aviso):
        # historia de ANTES de que el usuario viera el aviso: sin persona ni
        # pestaña (salvo `importar --mio`)
        atrib, inferir = _anonimo(atrib), False
    return {"motor": motor, "sid": sid, "path": path, "brain": brain,
            "atrib": atrib, "run_id": None, "data": None,
            "inferir": inferir, "cola": (time.time() - mtime) > _COLA_QUIETA_S,
            "_orden": (ts or mtime, _nacimiento(path))}, None


def _sesiones(resumen, curs, cerebro=None, antes_de=None, excluir=None, todas=False,
              cerebro_de=None):
    """Los trabajos de importar (y de reconstruir) en ORDEN de medición: las
    sesiones de cerebros de Workspace que hay en la máquina. `todas` = no se
    saltan las abiertas ni las al día (reconstruir re-mide todo).
    `cerebro_de(motor, sid)` → ruta del cerebro que ya se conocía de esa
    sesión (reconstruir: el de sus filas viejas) cuando su fuente no lo dice."""
    solo = os.path.normcase(os.path.realpath(cerebro)) if cerebro else None
    conocidos = _cerebros_conocidos()
    mapa = _MapaImport()
    trabajos = []
    for (motor, sid), path in _fuentes().items():
        if excluir and (motor, sid) == tuple(excluir):
            continue
        t, _motivo = _trabajo(motor, sid, path, resumen, curs, conocidos, mapa, todas=todas,
                              cerebro_de=cerebro_de, solo=solo, antes_de=antes_de)
        if t:
            trabajos.append((t.pop("_orden"), t))
    # El padre de una sesión continuada se mide ANTES que sus hijos: así la
    # copia del historial cae como duplicado en el hijo (y no al revés), y el
    # padre deja anotado su punto de continuación (costo, pestaña). El hijo
    # copia el primer timestamp del padre: el empate lo rompe la fecha de
    # CREACIÓN del archivo (el hijo nace después).
    trabajos.sort(key=lambda x: (x[0], x[1]["path"]))
    return [t for _, t in trabajos]


def importar(progreso=None, cerebro=None, antes_de=None, excluir=None, presupuesto_s=None,
             mio=False):
    """Mide los transcripts que YA existen en la máquina (cada parser dice
    dónde: Claude Code en ~/.claude/projects y transcripts-backup/, Codex en
    ~/.codex/sessions…) con origen «importado» y atribución inferida. Solo
    sesiones de cerebros de Workspace. Idempotente con los mismos cursores:
    importar dos veces da las mismas filas. → resumen por motor.

    Filtros (la importación inicial acotada de al_cerrar): `cerebro` = solo
    ese; `antes_de` = solo sesiones que empezaron antes (epoch); `excluir` =
    (motor, sid) que no se toca; `presupuesto_s` = tope de tiempo total.
    `mio`: la historia anterior al aviso se atribuye igual (por defecto va
    sin persona ni pestaña)."""
    _MIO[0] = bool(mio)
    try:
        return _importar(progreso, cerebro, antes_de, excluir, presupuesto_s)
    finally:
        _MIO[0] = False


def _importar(progreso, cerebro, antes_de, excluir, presupuesto_s):
    if apagado():
        if apagado_por_ajuste():
            _marcar_apagado()
        return {"apagado": True}
    _marcar_encendido()
    fin_t = time.monotonic() + presupuesto_s if presupuesto_s else None
    resumen = {}
    # solo para saltar lo que ya está al día (sin candado: no resuelve nada)
    curs = _leer_json(_g("cursores.json"), {}).get("sesiones") or {}
    lista = _sesiones(resumen, curs, cerebro=cerebro, antes_de=antes_de, excluir=excluir)
    hechos = 0
    while True:
        lote = lista[hechos:hechos + _LOTE_IMPORTAR]
        espera = _CANDADO_IMPORTAR
        if fin_t is not None:        # acotada: jamás espera más que su presupuesto
            espera = max(0.1, min(espera, fin_t - time.monotonic()))
        try:
            escritas, restantes = _lote(lote, "importado", candado_s=espera,
                                        limite_s=_LOTE_IMPORTAR_S, fin_t=fin_t)
        except TimeoutError:
            _log("importar_candado_ocupado", pendientes=len(lista) - hechos)
            break
        except Exception as exc:
            _log("importar_fallo", error=type(exc).__name__)
            for t in lote:
                resumen.setdefault(t["motor"], dict(_RESUMEN))["errores"] += 1
            escritas, restantes = [], []
        for f in escritas:
            resumen.setdefault(f["motor"], dict(_RESUMEN))["filas"] += 1
        hechos += len(lote) - len(restantes)
        if progreso:
            try:
                progreso(hechos, len(lista))
            except Exception:
                pass
        if hechos >= len(lista):
            break
        if fin_t is not None and time.monotonic() > fin_t:
            _log("importacion_acotada_incompleta", pendientes=len(lista) - hechos)
            break
        time.sleep(0.05)       # suelta el candado: un cierre en vivo pasa aquí
    return resumen


# ═══════════════════════════════════════════════════════════════════════════
# Reconstruir: re-medir la historia a una generación nueva (y volver atrás)
# ═══════════════════════════════════════════════════════════════════════════

#: lo que de una fila solo se supo al CERRAR (no está en el transcript): la
#: fila re-medida lo hereda de la fila vieja del mismo corte
_DE_LA_PLANTILLA = ("run_id", "origen", "agente", "pestana_h", "socio", "socio_id",
                    "atribucion", "workspace_version", "cerebro_huella", "instalacion")


def _aplicar_plantilla(fila, vieja):
    """La fila re-medida conserva de la vieja lo que solo se supo al cerrar:
    quién y dónde, la versión de Workspace, la huella del cerebro, las
    señales de Workspace, la versión del motor si el transcript no la trae y
    las huellas de skills y entregables (por nombre / huella)."""
    for k in _DE_LA_PLANTILLA:
        if vieja.get(k) is not None:
            fila[k] = vieja[k]
    if fila.get("motor_version") is None and vieja.get("motor_version"):
        fila["motor_version"] = vieja["motor_version"]
        p = parser(fila["motor"])
        fila["captura"]["verificado"] = _verificado(p, fila["motor_version"])
    sen = dict(fila.get("modo_senales") or {})
    for k, v in (vieja.get("modo_senales") or {}).items():
        if sen.get(k) is None and v is not None:
            sen[k] = v
    fila["modo_senales"] = {k: sen.get(k) for k in SENALES_MODO}
    fila["modo"] = modo_de(fila["modo_senales"])
    cm = (vieja.get("captura") or {}).get("captura_motor")
    if cm and fila["captura"].get("captura_motor") is None:
        fila["captura"]["captura_motor"] = cm
    huellas = {s.get("nombre"): s.get("huella") for s in vieja.get("skills") or ()
               if isinstance(s, dict)}
    for s in fila.get("skills") or ():
        if s.get("huella") is None:
            s["huella"] = huellas.get(s["nombre"])
    ents = {e.get("h"): e for e in (vieja.get("escritos") or {}).get("entregables") or ()
            if isinstance(e, dict)}
    for e in (fila.get("escritos") or {}).get("entregables") or ():
        v = ents.get(e["h"]) or {}
        if e.get("sha256_8") is None:
            e["sha256_8"], e["bytes"] = v.get("sha256_8"), v.get("bytes")


def _generaciones():
    try:
        return sorted(int(x) for x in os.listdir(os.path.join(carpeta(), "gen")) if x.isdigit())
    except OSError:
        return []


def _atrib_de(vieja):
    return {"agente": vieja.get("agente"), "pestana": None, "pestana_h": vieja.get("pestana_h"),
            "socio": vieja.get("socio"), "socio_id": vieja.get("socio_id"),
            "atribucion": vieja.get("atribucion")}


def reconstruir(progreso=None):
    """Re-mide TODA la historia de la máquina a una generación nueva y cambia
    el puntero de forma atómica; la generación anterior queda intacta
    (deshacer_reconstruccion() vuelve a ella). Es también la migración F1 →
    g2: las filas F1 se re-miden con los parsers de hoy.

    Cómo: bajo el candado (los cierres en vivo se encolan y la cola se mide
    DESPUÉS, ya en la generación nueva), sesión por sesión en el orden de
    importar (padres antes que hijos). Cada sesión se corta donde se cortó
    antes (captura.hasta de sus filas viejas), así cada tramo re-medido
    hereda lo que solo se supo al cerrar (pestaña, socio, versión de
    Workspace…); los cierres que solo dejaron recibo dan cortes más, con el
    recibo como plantilla; lo que nunca se midió queda como importado. Las
    filas cuya fuente ya no existe (la retención la borró) y los recibos sin
    medición pasan tal cual, con el aviso `fuente_perdida`.

    Fiel o no toca: los motores cuyo parser no es RECONSTRUIBLE (respaldos
    que Workspace reescribe enteros y totales por sesión: OpenCode, OpenClaw,
    Hermes, Antigravity) no se pueden volver a cortar como se cortaron; sus
    filas, cursores, estado y huellas pasan TAL CUAL (resumen
    «motores_conservados»). Lo que un cierre escribe mientras tanto (filas-
    recibo, que no esperan el candado) se copia antes de cambiar el
    puntero. → resumen."""
    if apagado():
        if apagado_por_ajuste():
            _marcar_apagado()
        return {"apagado": True}
    with _Candado(_CANDADO_IMPORTAR):
        vieja = generacion()
        viejas = list(filas())
        claves_antes = {_clave(f) for f in viejas}
        pt = puntero()
        usadas = {vieja, GENERACION_INICIAL} | {x for x in (pt.get("previa"),) if isinstance(x, int)}
        usadas |= {h.get("generacion") for h in pt.get("historial") or ()
                   if isinstance(h, dict) and isinstance(h.get("generacion"), int)}
        nueva = max(usadas) + 1
        destino = _dir_gen(nueva)
        if os.path.exists(destino):            # restos de una reconstrucción cortada
            import shutil
            shutil.rmtree(destino)
        _mkdirs(destino)
        _GEN_FORZADA.append(nueva)
        try:
            resumen = _reconstruir_en(viejas, progreso)
            # lo que escribieron los cierres DURANTE la reconstrucción (las
            # filas-recibo no esperan el candado) también pasa, antes del puntero
            nuevas_viejas = [f for f in _filas_crudas(vieja) if _clave(f) not in claves_antes]
            for f in nuevas_viejas:
                resumen["filas"] += _copiar_crudo(f)
            resumen["escritas_durante"] = len(nuevas_viejas)
        finally:
            _GEN_FORZADA.pop()
        pt = puntero()
        hist = list(pt.get("historial") or [])
        hist.append({"generacion": nueva, "desde": vieja, "t": iso(time.time()),
                     "filas_antes": len(viejas), "filas": resumen["filas"]})
        _escribir_json(_ruta("generacion.json"),
                       {"actual": nueva, "previa": vieja, "historial": hist[-20:]})
    _log("reconstruido", generacion=nueva, desde=vieja, filas=resumen["filas"])
    resumen.update(generacion=nueva, previa=vieja)
    return resumen


def _gen_del_puntero():
    """La generación vigente según el puntero (aunque reconstruir esté
    escribiendo en otra)."""
    v = puntero().get("actual")
    return v if isinstance(v, int) and not isinstance(v, bool) and v >= 1 else GENERACION_INICIAL


def _filas_crudas(gen):
    """Las filas de una generación TAL COMO ESTÁN en disco (sin traducir),
    una por clave."""
    return _filas_crudas_dir(_dir_gen(gen))


def _filas_crudas_dir(d):
    try:
        nombres_ = sorted(f for f in os.listdir(d) if f.startswith("corridas-")
                          and f.endswith(".jsonl"))
    except OSError:
        return
    for f in nombres_:
        vistas = set()
        try:
            with open(os.path.join(d, f), encoding="utf-8", errors="replace") as fh:
                for ln in fh:
                    try:
                        x = json.loads(ln)
                    except ValueError:
                        continue
                    if isinstance(x, dict) and _clave(x) not in vistas:
                        vistas.add(_clave(x))
                        yield x
        except OSError:
            continue


def _copiar_crudo(f):
    """Una fila de la generación vieja a la nueva, TAL CUAL (su `generacion`
    dice dónde se midió)."""
    try:
        return 1 if registrar(f) else 0
    except FilaEnConflicto:
        return 0


def _conservar_motor(motor, vieja):
    """Un motor que no se puede re-medir fiel pasa a la generación nueva TAL
    CUAL: sus filas (crudas), sus cursores, su estado compartido, sus huellas,
    sus turnos y sus pendientes del goteo. Así el próximo cierre sigue donde
    iba, sin volver a medir nada. → filas copiadas."""
    n = 0
    for f in _filas_crudas(vieja):
        if f.get("motor") == motor:
            n += _copiar_crudo(f)
    dv, dn = _dir_gen(vieja), _dir_gen()
    curs_v = _leer_estado_json(os.path.join(dv, "cursores.json"))
    curs_n = _leer_estado_json(os.path.join(dn, "cursores.json"))
    curs_n.setdefault("schema", SCHEMA)
    ses = curs_n.setdefault("sesiones", {})
    for ck, cur in (curs_v.get("sesiones") or {}).items():
        if ck.startswith(motor + ":") and isinstance(cur, dict):
            ses[ck] = {k: v for k, v in cur.items() if k != "pendiente"}
    _escribir_json(os.path.join(dn, "cursores.json"), curs_n)
    mot_v = _leer_estado_json(os.path.join(dv, "motores.json"))
    if motor in mot_v:
        mot_n = _leer_estado_json(os.path.join(dn, "motores.json"))
        mot_n[motor] = mot_v[motor]
        _escribir_json(os.path.join(dn, "motores.json"), mot_n)
    v = Vistos(motor)
    try:
        for f in os.listdir(os.path.join(dv, "vistos")):
            m = re.match(r"%s-(\d{4}-\d\d)\.txt$" % re.escape(v.motor), f)
            if not m:
                continue
            por = {}
            with open(os.path.join(dv, "vistos", f), encoding="ascii", errors="ignore") as fh:
                for ln in fh:
                    h, _, dueno = ln.strip().partition("\t")
                    if h:
                        por.setdefault(dueno, []).append(h)
            dest = v._archivo(m.group(1))
            _mkdirs(os.path.dirname(dest))
            with open(dest, "a", encoding="ascii", newline="\n") as fh:
                for dueno, hs in por.items():
                    fh.write("".join((h + "\t" + dueno if dueno else h) + "\n" for h in hs))
    except OSError:
        pass
    try:
        for f in os.listdir(dv):
            if re.match(r"turnos-\d{4}-\d\d\.jsonl$", f):
                with open(os.path.join(dv, f), encoding="utf-8", errors="replace") as fh:
                    lineas = [ln for ln in fh if '"motor":"%s"' % motor in ln.replace(" ", "")]
                if lineas:
                    dest = os.path.join(dn, f)
                    with open(dest, "a", encoding="utf-8", newline="\n") as fh:
                        fh.write(_sin_corte(dest) + "".join(
                            ln if ln.endswith("\n") else ln + "\n" for ln in lineas))
    except OSError:
        pass
    pend = [d for d in _pendientes(_leer_json(os.path.join(dv, "goteo.json"), {}))
            if d.get("motor") == motor]
    if pend:
        _goteo_pendientes(pend)
    return n


def _plantilla_de_recibo(rec):
    """Un recibo como plantilla de un corte que no dejó fila."""
    return {"run_id": rec.get("run_id"), "origen": "interactivo", "agente": rec.get("agente"),
            "pestana_h": rec.get("pestana_h"), "socio": rec.get("socio"),
            "socio_id": rec.get("socio_id"),
            "atribucion": REGISTRADA if (rec.get("pestana_h") or rec.get("socio")) else None,
            "workspace_version": rec.get("workspace_version"),
            "cerebro_huella": rec.get("cerebro_huella"), "instalacion": rec.get("instalacion"),
            "modo_senales": rec.get("modo_senales"), "motor_version": rec.get("motor_version"),
            "captura": {"captura_motor": rec.get("captura_motor")}}


def _reconstruir_en(viejas, progreso=None):
    vieja = _gen_del_puntero()
    por_sesion = {}
    for f in viejas:
        por_sesion.setdefault((f.get("motor"), f.get("sesion_motor")), []).append(f)
    resumen = {"sesiones": 0, "filas": 0, "copiadas": 0, "fuente_perdida": 0, "errores": 0,
               "conservadas": 0, "motores_conservados": []}
    fieles = {m for m, p in parsers().items() if getattr(p, "RECONSTRUIBLE", False) is True}
    # los motores que no se pueden re-medir fiel pasan TAL CUAL (filas y estado)
    conservar = sorted({f.get("motor") for f in viejas if f.get("motor") in parsers()
                        and f.get("motor") not in fieles})
    for m in conservar:
        resumen["conservadas"] += _conservar_motor(m, vieja)
    resumen["motores_conservados"] = conservar
    if conservar:
        _log("reconstruir_conserva", motores=",".join(conservar))
    recibos_por = {}
    for r in recibos():
        recibos_por.setdefault((r.get("motor"), r.get("sesion_motor")), []).append(r)
    # el cerebro de una sesión que ya se midió: el de sus filas (por su id),
    # entre los cerebros conocidos y los que aparecen en las cabeceras
    por_id = {cerebro_id(b): b for b in _cerebros_conocidos().values()}

    def cerebro_de(motor, sid):
        for f in por_sesion.get((motor, sid)) or ():
            if f.get("cerebro") in por_id:
                return por_id[f["cerebro"]]
        return None
    porm = {}
    lista = [t for t in _sesiones(porm, {}, todas=True, cerebro_de=cerebro_de)
             if t["motor"] in fieles]
    for k in [k for k in por_sesion if k[0] in conservar]:
        del por_sesion[k]                            # ya pasaron tal cual
    for i, tr in enumerate(lista):
        resumen["sesiones"] += 1
        filas_ses = por_sesion.pop((tr["motor"], tr["sid"]), [])
        cortes = sorted({f["captura"]["hasta"]: f for f in filas_ses
                         if not str(f.get("tramo") or "").startswith("r:")
                         and isinstance((f.get("captura") or {}).get("hasta"), int)}.items())
        # los cierres que dejaron recibo pero no fila (el runner los mató, o
        # nunca se midieron): sus bytes al cerrar son un corte más, con el
        # recibo como plantilla — solo después del último corte con fila
        ultimo = cortes[-1][0] if cortes else 0
        rh = huella_local("fuente", os.path.abspath(tr["path"]))
        hechos = {h for h, _f in cortes}
        for rec in sorted(recibos_por.get((tr["motor"], tr["sid"])) or (),
                          key=lambda r: r.get("t") or ""):
            b = next((x.get("bytes") for x in rec.get("fuentes") or ()
                      if x.get("ruta_h") == rh and isinstance(x.get("bytes"), int)), None)
            if b is not None and b > ultimo and b not in hechos:
                cortes.append((b, _plantilla_de_recibo(rec)))
                hechos.add(b)
                ultimo = b
        trabajos = []
        for hasta, f in cortes:
            trabajos.append(dict(tr, tope={os.path.abspath(tr["path"]): hasta},
                                 atrib=_atrib_de(f), inferir=False, plantilla=f, cola=True))
        trabajos.append(dict(tr, cola=True))          # lo que quede, como importado
        for t in trabajos:
            try:
                escritas, _r = _lote([t], "importado", con_cola=False)
                resumen["filas"] += len(escritas)
            except Exception as exc:
                resumen["errores"] += 1
                _log("reconstruir_fallo", motor=tr["motor"], sesion=tr["sid"],
                     error=type(exc).__name__)
                break
        # los recibos de corridas sin medición de esta sesión pasan tal cual
        for f in filas_ses:
            if str(f.get("tramo") or "").startswith("r:"):
                resumen["copiadas"] += _copiar(f)
        if progreso:
            try:
                progreso(i + 1, len(lista))
            except Exception:
                pass
    for filas_ses in por_sesion.values():      # la fuente ya no existe
        for f in filas_ses:
            perdida = not str(f.get("tramo") or "").startswith("r:")
            resumen["copiadas"] += _copiar(f, perdida)
            resumen["fuente_perdida"] += perdida
    resumen["filas"] += resumen["copiadas"]
    return resumen


def _copiar(f, fuente_perdida=False):
    """Una fila vieja (ya en forma g2) a la generación nueva."""
    g = json.loads(json.dumps(f))
    g["generacion"] = generacion()
    if fuente_perdida:
        cap = g.setdefault("captura", {})
        cap["avisos"] = sorted(set(cap.get("avisos") or ()) | {"fuente_perdida"})
    try:
        return 1 if registrar(g) else 0
    except FilaEnConflicto:
        return 0


def deshacer_reconstruccion():
    """Vuelve a la generación anterior (cambio atómico de puntero). La
    generación de la que se sale queda en disco. → la generación vigente."""
    with _Candado(_CANDADO_IMPORTAR):
        pt = puntero()
        if not isinstance(pt.get("previa"), int):
            return generacion()
        actual = generacion()
        hist = list(pt.get("historial") or [])
        hist.append({"generacion": pt["previa"], "desde": actual, "t": iso(time.time()),
                     "deshacer": True})
        _escribir_json(_ruta("generacion.json"),
                       {"actual": pt["previa"], "previa": actual, "historial": hist[-20:]})
    _log("reconstruccion_deshecha", generacion=pt["previa"], desde=actual)
    return pt["previa"]


# ═══════════════════════════════════════════════════════════════════════════
# Lectura: estado y exportación de agregados
# ═══════════════════════════════════════════════════════════════════════════

def filas():
    """Todas las filas registradas (orden de los archivos de mes), en forma
    g2: las de F1 pasan por traducir()."""
    try:
        nombres = sorted(f for f in os.listdir(_dir_gen())
                         if f.startswith("corridas-") and f.endswith(".jsonl"))
    except OSError:
        return
    for f in nombres:
        vistas = set()               # una fila repetida (versión anterior,
        try:                         # muerte a media escritura) cuenta una vez
            with open(_g(f), encoding="utf-8", errors="replace") as fh:
                for ln in fh:
                    try:
                        d = json.loads(ln)
                    except ValueError:
                        continue
                    if isinstance(d, dict):
                        c = _clave(d)
                        if c in vistas:
                            continue
                        vistas.add(c)
                        yield traducir(d)
        except OSError:
            continue


def estado():
    """Resumen para verificar a ojo: cuántas filas, desde cuándo, por motor y
    por agente."""
    n, desde, hasta = 0, None, None
    motores, agentes = {}, {}
    for f in filas():
        n += 1
        ini = f.get("inicio") or f.get("fin")
        if ini:
            desde = ini if desde is None or ini < desde else desde
            fin = f.get("fin") or ini
            hasta = fin if hasta is None or fin > hasta else hasta
        m = motores.setdefault(str(f.get("motor")), {"filas": 0, "sesiones": set()})
        m["filas"] += 1
        m["sesiones"].add(f.get("sesion_motor"))
        a = str(f.get("agente") or "—")
        agentes[a] = agentes.get(a, 0) + 1
    return {"carpeta": carpeta(), "apagado": apagado(), "generacion": generacion(),
            "maquina": _leer_json(_ruta("maquina.json"), {}).get("id"),
            "parsers": sorted(parsers()),
            "filas": n, "desde": desde, "hasta": hasta,
            "por_motor": {k: {"filas": v["filas"], "sesiones": len(v["sesiones"])}
                          for k, v in sorted(motores.items())},
            "por_agente": dict(sorted(agentes.items()))}


#: el desglose por persona solo existe en celdas con al menos esto
_MIN_PERSONAS, _MIN_SESIONES = 5, 20
_SUMABLES = ("duracion_activa_s", "duracion_pared_s", "tiempo_humano_est_s", "costo_usd",
             "mensajes_usuario", "interrupciones")


def _acumular(g, f):
    """Suma una fila a un grupo de agregados (solo números y nombres)."""
    g["filas"] += 1
    g["_ses"].add((f.get("motor"), f.get("sesion_motor")))
    met = g["metricas"]

    def sumar(nombre, v):
        v = numero(v)
        if v is None:
            return
        s = met.setdefault(nombre, {"suma": 0, "filas": 0})
        s["suma"] = round(s["suma"] + v, 6)
        s["filas"] += 1
    for c in _SUMABLES:
        sumar(c, f.get(c))
    h = f.get("herramientas") if isinstance(f.get("herramientas"), dict) else {}
    sumar("herramientas_llamadas", h.get("llamadas"))
    sumar("herramientas_errores", h.get("errores"))
    sumar("comandos_no_cero", h.get("comandos_no_cero"))
    e = f.get("escritos") if isinstance(f.get("escritos"), dict) else {}
    sumar("archivos_escritos", e.get("archivos"))
    if isinstance(e.get("entregables"), list):
        sumar("entregables_escritos", len(e["entregables"]))
    for mod, toks in (f.get("modelos") or {}).items():
        if not isinstance(toks, dict):
            continue
        acc = g["modelos"].setdefault(mod, {})
        for c in ("llamadas",) + CAMPOS_TOKENS:
            v = entero(toks.get(c))
            if v is not None:
                acc[c] = acc.get(c, 0) + v
    for s in f.get("skills") or ():
        n = s.get("nombre") if isinstance(s, dict) else s
        if isinstance(n, str) and n:
            g["skills"][n] = g["skills"].get(n, 0) + 1
    tipo = f.get("costo_tipo")
    if f.get("costo_usd") is not None:
        g["costo_tipo"][str(tipo)] = g["costo_tipo"].get(str(tipo), 0) + 1


def _grupo_vacio(**claves):
    return dict(claves, filas=0, _ses=set(), metricas={}, modelos={}, skills={}, costo_tipo={})


def _a_horas(met):
    """Duraciones → horas redondeadas (el desglose por persona no da minutos)."""
    out = {}
    for k, v in met.items():
        if k.startswith("duracion_") or k == "tiempo_humano_est_s":
            out[k.replace("_s", "_h") if k.endswith("_s") else k] = {
                "suma": int(round(v["suma"] / 3600.0)), "filas": v["filas"]}
        else:
            out[k] = v
    return out


def agregados(por_persona=False):
    """Solo agregados, SIN personas: por mes UTC, agente, motor, modo e
    instalación (dev = datos internos). Cada métrica dice cuántas filas la
    tenían (`filas`): «sin dato» no se suma como cero. Jamás sesiones,
    pestañas, rutas, nombres ni turnos.

    `por_persona`: una celda solo se desglosa por cédula (socio_id) si tiene
    al menos _MIN_PERSONAS personas Y _MIN_SESIONES sesiones, y con las horas
    redondeadas; si no, se dice por qué y no se desglosa."""
    grupos, personas = {}, {}
    for f in filas():
        mes = _mes(epoch(f.get("fin")) or epoch(f.get("inicio")) or 0)
        k = (mes, f.get("agente"), f.get("motor"), f.get("modo"), f.get("instalacion"))
        g = grupos.get(k)
        if g is None:
            g = grupos[k] = _grupo_vacio(mes=mes, agente=f.get("agente"), motor=f.get("motor"),
                                         modo=f.get("modo"), instalacion=f.get("instalacion"))
        _acumular(g, f)
        if por_persona and f.get("socio_id"):
            pk = personas.setdefault(k, {})
            gp = pk.get(f["socio_id"])
            if gp is None:
                gp = pk[f["socio_id"]] = _grupo_vacio(socio_id=f["socio_id"])
            _acumular(gp, f)
    out = []
    for k in sorted(grupos, key=lambda x: tuple(str(i) for i in x)):
        g = grupos[k]
        g["sesiones"] = len(g.pop("_ses"))
        if por_persona:
            pk = personas.get(k) or {}
            if len(pk) >= _MIN_PERSONAS and g["sesiones"] >= _MIN_SESIONES:
                filas_p = []
                for sid in sorted(pk):
                    gp = pk[sid]
                    gp["sesiones"] = len(gp.pop("_ses"))
                    gp["metricas"] = _a_horas(gp["metricas"])
                    filas_p.append(gp)
                g["por_persona"] = filas_p
            else:
                g["por_persona"] = None
                g["por_persona_motivo"] = "menos de %d personas o %d sesiones en la celda" % (
                    _MIN_PERSONAS, _MIN_SESIONES)
        out.append(g)
    return out


def exportar(destino, por_persona=False):
    """Escribe el archivo de agregados (JSON) en `destino` ('-' = stdout).
    Nunca lleva turnos, nombres, recibos ni datos de persona (salvo el
    desglose por cédula de `por_persona`, con umbral)."""
    doc = {"schema": SCHEMA, "tipo": "workspace.metricas.agregados",
           "generado": iso(time.time()), "generacion": generacion(),
           "maquina": _leer_json(_ruta("maquina.json"), {}).get("id"),
           "por_persona": bool(por_persona),
           "nota": ("solo agregados por mes, agente, motor, modo e instalación: sin "
                    "conversación, sesiones, pestañas, rutas ni personas" if not por_persona else
                    "agregados; el desglose por cédula solo en celdas con al menos %d personas "
                    "y %d sesiones, con horas redondeadas" % (_MIN_PERSONAS, _MIN_SESIONES)),
           "grupos": agregados(por_persona)}
    texto = json.dumps(doc, ensure_ascii=False, indent=2)
    if destino == "-":
        sys.stdout.write(texto + "\n")
    else:
        d = os.path.dirname(os.path.abspath(destino))
        os.makedirs(ruta_larga(d), exist_ok=True)
        guardar(destino, texto + "\n")
    return doc


# ═══════════════════════════════════════════════════════════════════════════
# Privacidad: aviso, borrar lo tuyo, persona solo sin ambigüedad
# ═══════════════════════════════════════════════════════════════════════════

TEXTO_AVISO = ("Workspace guarda en esta computadora números de cada sesión (duración, tokens, "
               "costo, errores, skills), nunca tu conversación. Workspace no los envía a nadie. "
               "Ver: `workspace metricas` · Apagar: `workspace metricas apagar` · Borrar lo "
               "tuyo: `workspace metricas borrar --mio`.")


#: la misma, para el renglón del hub (que recorta al ancho de la terminal)
TEXTO_AVISO_CORTO = ("Workspace guarda números de cada sesión en esta computadora, nunca tu "
                     "conversación, y no los envía · ver, apagar o borrar lo tuyo: "
                     "`workspace metricas`")


def texto_aviso(corto=False):
    if corto:
        return _t("metricas.notice_short", TEXTO_AVISO_CORTO)
    return _t("metricas.notice", TEXTO_AVISO)


def fecha_aviso():
    """Cuándo se mostró el aviso por primera vez (epoch) o None. La historia
    de ANTES se importa sin persona ni pestaña (salvo `importar --mio`)."""
    v = _leer_json(_ruta("aviso.json"), {}).get("mostrado")
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else None


def marcar_aviso(cuando=None):
    """Anota que el aviso ya se mostró (y entra a la bitácora de cambios)."""
    if fecha_aviso() is not None:
        return False
    t = time.time() if cuando is None else cuando
    try:
        _escribir_json(_ruta("aviso.json"), {"mostrado": t,
                                             "workspace_version": workspace_version()})
        _cambio("aviso_mostrado", None, None, iso(t))
        return True
    except OSError:
        return False


def aviso_pendiente(marcar=True, corto=False):
    """El aviso de una línea si todavía no se mostró (una vez tras actualizar,
    y al importar la historia); None si ya. Con `marcar`, queda mostrado."""
    if fecha_aviso() is not None or apagado():
        return None
    if marcar:
        marcar_aviso()
    return texto_aviso(corto)


#: importar --mio: la historia anterior al aviso se atribuye igual
_MIO = [False]


def _anonimo(atrib):
    return {"agente": atrib.get("agente"), "pestana": None, "socio": None, "socio_id": None,
            "atribucion": None}


def _socio_sin_ambiguedad(brain):
    """El socio de ESTA cuenta del sistema para ese cerebro, solo si no hay
    duda: su `.claude/socio.local` nombra a un usuario del cerebro y el
    socio.local de la máquina (si hay) no dice otro. Si no, None."""
    try:
        import usuarios
        s = usuarios.socio_actual(brain, arreglar=False) or None
        if not s or not (usuarios.resolver(brain, s) or s in usuarios.carpetas(brain)):
            return None
        maq = os.path.join(_paths.state_dir(), "socio.local")
        if os.path.isfile(maq):
            with open(maq, encoding="utf-8", errors="replace") as fh:
                m = re.sub(r"[^a-z0-9_-]", "", fh.read().strip().lower())
            if m and (usuarios.resolver(brain, m) or m) != s:
                return None
        return s
    except Exception:
        return None


def _cerebros_con_filas():
    """{cerebro_id: ruta} de los cerebros de esta cuenta: los del registry y
    los que tienen filas y se reconocen por las cabeceras de las fuentes (un
    cerebro que ya no está en el registry también tiene filas)."""
    ids = set()
    for _n, d in _dirs_generaciones():
        for f in _filas_crudas_dir(d):
            if f.get("cerebro"):
                ids.add(f["cerebro"])
    out = {}
    conocidos = _cerebros_conocidos()
    for b in conocidos.values():          # los del registry, siempre (son de esta cuenta)
        out[cerebro_id(b)] = b
    if ids - set(out):
        for (motor, _sid), path in _fuentes().items():
            p = parser(motor)
            try:
                cwd, _ts = getattr(p, "cabecera", cabecera)(path)
            except Exception:
                continue
            b = _raiz(cwd) if cwd and os.path.isdir(cwd) else _cerebro_por_carpeta(path,
                                                                                     conocidos)
            if b and cerebro_id(b) in ids and cerebro_id(b) not in out:
                out[cerebro_id(b)] = b
            if not ids - set(out):
                break
    return out


def _mis_socios():
    """(nombres, cédulas, ambiguos) de quien usa ESTA cuenta del sistema: los
    socios sin ambigüedad de los cerebros con filas. `ambiguos` = ids de los
    cerebros donde no se sabe quién es (y que sí tienen filas con persona)."""
    nombres_, ids, ambiguos = set(), set(), []
    for cid, b in sorted(_cerebros_con_filas().items()):
        s = _socio_sin_ambiguedad(b)
        if s:
            nombres_.add(s)
            c = _cedula_id(b, s)
            if c:
                ids.add(c)
        elif _tiene_filas_con_persona(cid):
            ambiguos.append(cid)
    return nombres_, ids, ambiguos


def _tiene_filas_con_persona(cid):
    for _n, d in _dirs_generaciones():
        for f in _filas_crudas_dir(d):
            if f.get("cerebro") == cid and (f.get("socio") or f.get("socio_id")):
                return True
    return False


def _dirs_generaciones():
    gens = {GENERACION_INICIAL} | set(_generaciones())
    return [(n, _dir_gen(n)) for n in sorted(gens) if os.path.isdir(_dir_gen(n))]


def _contar_lineas(path):
    try:
        with open(path, "rb") as fh:
            return sum(1 for _ in fh)
    except OSError:
        return 0


def _reescribir_jsonl(path, quedarse, despues=None):
    """Reescribe un JSONL con las líneas que `quedarse(obj)` acepta (o
    transforma: devuelve el objeto a escribir o None), bajo el candado del
    archivo: el mismo del append (recibos, latidos, cambios) y de registrar
    (filas). `despues` corre dentro del candado. → líneas quitadas."""
    from olock import file_lock
    with file_lock(path, timeout=10):
        n = _reescribir_jsonl_(path, quedarse)
        if despues:
            despues()
        return n


def _reescribir_jsonl_(path, quedarse):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            lineas = fh.readlines()
    except OSError:
        return 0
    out, quitadas = [], 0
    for ln in lineas:
        try:
            d = json.loads(ln)
        except ValueError:
            out.append(ln if ln.endswith("\n") else ln + "\n")
            continue
        nuevo = quedarse(d) if isinstance(d, dict) else d
        if nuevo is None:
            quitadas += 1
        else:
            out.append(json.dumps(nuevo, ensure_ascii=False, separators=(",", ":")) + "\n")
    if not out:
        if not _borrar(path):
            raise PermissionError(path)
        return quitadas
    guardar(path, "".join(out))
    return quitadas


def borrar(mio=False, todo=False, antes=None):
    """`workspace metricas borrar`. Alcanza TODAS las generaciones.

    --todo: filas, turnos, recibos, nombres, latidos, cambios, salud, cola,
            sal e id de máquina; los cursores y huellas quedan (sin lo que
            traían de pestañas) para que lo borrado no se vuelva a importar.
    --mio:  las filas y turnos de quien usa esta cuenta (sus socios sin
            ambigüedad), sus nombres de pestaña y entregables; sus recibos
            quedan DISOCIADOS (sin socio ni pestaña).
    --antes AAAA-MM: todo lo de los meses anteriores.
    → resumen de lo borrado."""
    if not (mio or todo or antes):
        raise ValueError("borrar: falta --mio, --todo o --antes AAAA-MM")
    if antes is not None and not re.fullmatch(r"\d{4}-\d\d", str(antes)):
        raise ValueError("borrar --antes: AAAA-MM")
    res = {"filas": 0, "turnos": 0, "recibos": 0, "nombres": 0, "archivos": 0, "cola": 0,
           "ambiguos": [], "no_borrados": []}
    mis_n, mis_i, res["ambiguos"] = _mis_socios() if mio else (set(), set(), [])

    # Lo que no se pudo borrar o reescribir (sin permisos o, en Windows,
    # abierto por otro proceso) se dice, no se cuenta como borrado (regla 3),
    # y el resto sigue: un archivo trabado no deja a medias todo lo demás.
    def quitar(p):
        if _borrar(p):
            return True
        res["no_borrados"].append(os.path.basename(p))
        return False

    def reescribir(p, fn, **kw):
        try:
            return _reescribir_jsonl(p, fn, **kw)
        except (OSError, TimeoutError) as exc:
            _log("borrar_fallo", archivo=os.path.basename(p), error=_error_de(exc))
            res["no_borrados"].append(os.path.basename(p))
            return 0

    def es_mia(f):
        return bool((f.get("socio") and f["socio"] in mis_n)
                    or (f.get("socio_id") and f["socio_id"] in mis_i))
    huellas_mias, tramos_mios = set(), set()
    with _Candado(_CANDADO_IMPORTAR):
        for n, d in _dirs_generaciones():
            _GEN_FORZADA.append(n)
            try:
                for f in sorted(os.listdir(d)):
                    m = re.match(r"(corridas|turnos)-(\d{4}-\d\d)\.(jsonl|claves)$", f)
                    if not m:
                        continue
                    p = os.path.join(d, f)
                    if todo or (antes and m.group(2) < antes):
                        n_lin = _contar_lineas(p) if m.group(3) == "jsonl" else 0
                        if quitar(p):
                            if m.group(3) == "jsonl":
                                res["filas" if m.group(1) == "corridas" else "turnos"] += n_lin
                            res["archivos"] += 1
                    elif mio and m.group(1) == "corridas" and m.group(3) == "jsonl":
                        def quedarse(fila):
                            if es_mia(fila):
                                tramos_mios.add((fila.get("motor"), fila.get("sesion_motor"),
                                                 fila.get("tramo")))
                                huellas_mias.add(fila.get("pestana_h") or traducir(fila).get(
                                    "pestana_h"))
                                for e in (traducir(fila).get("escritos") or {}).get(
                                        "entregables") or ():
                                    huellas_mias.add(e.get("h"))
                                return None
                            return fila
                        def indice(p=p, mes=m.group(2)):
                            _CLAVES_CACHE.pop(_archivo_claves(mes), None)
                            if os.path.exists(p):
                                _rehacer_claves(mes)
                            else:
                                _borrar(_archivo_claves(mes))
                        res["filas"] += reescribir(p, quedarse, despues=indice)
                if mio:
                    for f in sorted(os.listdir(d)):
                        if re.match(r"turnos-\d{4}-\d\d\.jsonl$", f):
                            res["turnos"] += reescribir(
                                os.path.join(d, f), lambda t: None if (
                                    t.get("motor"), t.get("sesion_motor"), t.get("tramo"))
                                in tramos_mios else t)
                if todo or mio:
                    _limpiar_estado_de_gen(d)
            finally:
                _GEN_FORZADA.pop()
        # lo de la máquina
        for f in sorted(os.listdir(carpeta())):
            p = _ruta(f)
            m = re.match(r"recibos-(\d{4}-\d\d)\.jsonl$", f)
            if m:
                if todo or (antes and m.group(1) < antes):
                    n_lin = _contar_lineas(p)
                    if quitar(p):
                        res["recibos"] += n_lin
                elif mio:
                    def disociar(r):
                        if es_mia(r):
                            huellas_mias.add(r.get("pestana_h"))
                            return dict(r, socio=None, socio_id=None, pestana_h=None)
                        return r
                    reescribir(p, disociar)
            elif f in ("latidos.jsonl", "cambios.jsonl"):
                if todo:
                    quitar(p)
                elif antes:
                    reescribir(p, lambda x: None if str(x.get("t") or "")[:7] < antes else x)
        if mio:
            # un cierre encolado tuyo volvería a escribir lo tuyo (revisión #7)
            for archivo, item in _tomar_cola(maximo=_TOPE_COLA):
                if es_mia(item.get("atrib") or {}) and quitar(archivo):
                    res["cola"] += 1
        if todo:
            for f in ("nombres.json", "salud.json", "sal.json", "maquina.json", "aviso.json"):
                if os.path.exists(_ruta(f)) and quitar(_ruta(f)):
                    res["archivos"] += 1
            import shutil
            shutil.rmtree(_ruta("cola"), ignore_errors=True)
            _MAQUINA.clear()
            _SAL.clear()
        elif mio and huellas_mias:
            from olock import file_lock
            try:
                with file_lock(_ruta("nombres.json"), timeout=5):
                    d = _leer_json(_ruta("nombres.json"), {})
                    antes_n = len(d)
                    for h in huellas_mias:
                        d.pop(h, None)
                    _escribir_json(_ruta("nombres.json"), d)
                    res["nombres"] = antes_n - len(d)
            except (OSError, TimeoutError) as exc:
                _log("borrar_fallo", archivo="nombres.json", error=_error_de(exc))
                res["no_borrados"].append("nombres.json")
    _log("borrado", mio=mio, todo=todo, antes=antes, filas=res["filas"],
         no_borrados=len(res["no_borrados"]))
    return res


def _limpiar_estado_de_gen(d):
    """Saca del estado de una generación lo que identifica pestañas o
    archivos (el padre → su pestaña, escrituras pendientes, la atribución
    de lo pendiente del goteo). Los cursores y huellas quedan."""
    p = os.path.join(d, "motores.json")
    m = _leer_json(p, {})
    for est in m.values():
        if isinstance(est, dict) and isinstance(est.get("padres"), dict):
            for v in est["padres"].values():
                if isinstance(v, dict):
                    v["pestana"] = None
    if m:
        _escribir_json(p, m)
    p = os.path.join(d, "cursores.json")
    c = _leer_json(p, {})
    for cur in (c.get("sesiones") or {}).values():
        if isinstance(cur, dict):
            cur.pop("pend_escr", None)
    if c:
        _escribir_json(p, c)
    p = os.path.join(d, "goteo.json")
    g = _leer_json(p, {})
    for x in g.get("pendientes") or ():
        if isinstance(x, dict):
            x.pop("atrib", None)
    if g:
        _escribir_json(p, g)


# ═══════════════════════════════════════════════════════════════════════════
# cambios.jsonl: bitácora automática de intervenciones
# ═══════════════════════════════════════════════════════════════════════════

def _cambio(campo, clave, antes, despues):
    try:
        _anexar(_ruta("cambios.jsonl"), {"t": iso(time.time()), "campo": campo, "clave": clave,
                                         "antes": antes, "despues": despues})
    except Exception as exc:
        _log("cambios_fallo", error=_error_de(exc))


def _registrar_cambios(rec, fila):
    """Al cerrar: compara con lo último visto en esta máquina (versión de
    Workspace, del motor, modelo, huella del cerebro y de cada skill leída) y
    anota cada cambio en cambios.jsonl. Falla-suave."""
    vistos = {}
    if rec:
        vistos[("workspace_version", None)] = rec.get("workspace_version")
        vistos[("motor_version", rec.get("motor"))] = rec.get("motor_version")
        vistos[("cerebro_huella", rec.get("cerebro"))] = rec.get("cerebro_huella")
    if fila:
        if fila.get("modelo_servido"):
            vistos[("modelo", fila.get("motor"))] = fila["modelo_servido"]
        if fila.get("motor_version"):
            vistos[("motor_version", fila.get("motor"))] = fila["motor_version"]
        for s in fila.get("skills") or ():
            if isinstance(s, dict) and s.get("huella"):
                vistos[("skill", s.get("nombre"))] = s["huella"]
    vistos = {k: v for k, v in vistos.items() if v is not None}
    if not vistos:
        return
    try:
        from olock import file_lock
        p = _ruta("ultimo_visto.json")
        with file_lock(p, timeout=1.0):
            ult = _leer_json(p, {})
            cambio = False
            for (campo, clave), v in sorted(vistos.items(), key=lambda x: str(x[0])):
                k = "%s|%s" % (campo, clave or "")
                if ult.get(k) != v:
                    _cambio(campo, clave, ult.get(k), v)
                    ult[k] = v
                    cambio = True
            if cambio:
                _escribir_json(p, ult)
    except Exception as exc:
        _log("cambios_fallo", error=_error_de(exc))


def cambios():
    p = _ruta("cambios.jsonl")
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            return [json.loads(x) for x in fh if x.strip()]
    except (OSError, ValueError):
        return []


# ═══════════════════════════════════════════════════════════════════════════
# workspace metricas salud: el autodiagnóstico
# ═══════════════════════════════════════════════════════════════════════════

#: con menos cierres que esto, lo estadístico no alarma
_MIN_CIERRES = 20
#: umbrales (A2 y A4 de la auditoría F1.1). Fracciones 0–1.
UMBRALES = {
    "cobertura_min": 0.98, "cobertura_urgente": 0.90,
    "recibos_sin_fila_max": 0.02, "fallas_captura_max": 0.10,
    "p95_cierre_ms_max": 4500, "cortados_max": 0.05,
    "cola_max": 20, "cola_vieja_dias_max": 3, "sin_medir_dias_max": 7,
    "ignoradas_max": 0.005, "ceros_sospechosos_max": 0.01, "cuadre_alto_max": 0.10,
    # canarios por motor×versión (últimas 20 filas o 7 días, con al menos 5)
    "canario_desconocidas_max": 0.02, "canario_ignoradas_max": 0.01,
    "canario_sin_tokens_max": 0.05, "canario_si_null_max": 0.05,
    "canario_recibos_sin_medicion_max": 0.10,
    "sin_filas_dias_usuario": 7,
}
_CANARIO_FILAS, _CANARIO_DIAS, _CANARIO_MIN = 20, 7, 5
#: avisos al USUARIO: solo estos tres (el resto es para el equipo)
AVISOS_USUARIO = ("no_escribe", "sin_filas", "interruptor")


def _latidos():
    p = _ruta("latidos.jsonl")
    out = []
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            for ln in fh:
                try:
                    d = json.loads(ln)
                except ValueError:
                    continue
                if isinstance(d, dict):
                    out.append(d)
    except OSError:
        pass
    return out


def _eventos_log(tope=2 * 1024 * 1024):
    """{evento: n} de la cola de metricas.log."""
    p = os.path.join(_paths.state_dir(), "logs", "metricas.log")
    out = {}
    try:
        with open(p, "rb") as fh:
            tam = os.path.getsize(p)
            if tam > tope:
                fh.seek(tam - tope)
                fh.readline()
            for ln in fh:
                try:
                    ev = json.loads(ln.decode("utf-8", "replace")).get("evento")
                except (ValueError, AttributeError):
                    continue
                if ev:
                    out[ev] = out.get(ev, 0) + 1
    except OSError:
        pass
    return out


def _frac(a, b):
    return round(a / float(b), 4) if b else None


def _p95(xs):
    xs = sorted(xs)
    return xs[int(round(0.95 * (len(xs) - 1)))] if xs else None


def _puede_escribir():
    try:
        _asegurar_carpeta()
        p = _ruta(".prueba-%d" % os.getpid())
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("x")
        os.remove(p)
        return True
    except OSError:
        return False


def _tokens_de(f):
    return _suma_tokens(f.get("modelos"))


def _canarios(rows, recs, ahora):
    """Por motor×versión, sobre las últimas 20 filas o 7 días (al menos 5)."""
    grupos = {}
    for f in rows:
        if str(f.get("tramo") or "").startswith("r:"):
            continue
        grupos.setdefault("%s@%s" % (f.get("motor"), f.get("motor_version")), []).append(f)
    rec_por = {}
    for r in recs:
        if r.get("fuentes"):
            rec_por.setdefault("%s@%s" % (r.get("motor"), r.get("motor_version")), []).append(r)
    medidas = {(f.get("motor"), f.get("sesion_motor")) for f in rows}
    out = {}
    for k, fs in grupos.items():
        fs.sort(key=lambda f: f.get("fin") or f.get("inicio") or "")
        recientes = [f for f in fs if (epoch(f.get("fin")) or 0) > ahora - _CANARIO_DIAS * 86400]
        muestra = recientes if len(recientes) >= _CANARIO_FILAS else fs[-_CANARIO_FILAS:]
        if len(muestra) < _CANARIO_MIN:
            continue
        cap = [f.get("captura") or {} for f in muestra]
        leidas = sum(c.get("leidas") or 0 for c in cap)
        con_msg = [f for f in muestra if (f.get("mensajes_usuario") or 0) > 0]
        p = parser(muestra[0].get("motor"))
        si = [c for c, v in (getattr(p, "COBERTURA", None) or {}).items()
              if isinstance(v, tuple) and v and v[0] == "si" and c != "turnos"]
        celdas = nulos = 0
        for f in muestra:
            if (f.get("captura") or {}).get("estado") == "formato_desconocido":
                continue
            for c in si:
                a, _, b = c.partition(".")
                v = f.get(a)
                v = v.get(b) if b and isinstance(v, dict) else (None if b else v)
                celdas += 1
                nulos += v is None
        recs_k = rec_por.get(k) or []
        sin_med = [r for r in recs_k if (r.get("motor"), r.get("sesion_motor")) not in medidas
                   and (epoch(r.get("t")) or ahora) < ahora - 3600]
        out[k] = {
            "filas": len(muestra),
            "desconocidas": _frac(sum(sum((c.get("desconocidas") or {}).values()) for c in cap),
                                  leidas),
            "ignoradas": _frac(sum(c.get("lineas_ignoradas") or 0 for c in cap), leidas),
            # un motor que no da tokens (COBERTURA modelos «no»: Cursor, Kiro) no
            # tiene este canario: sin tokens es lo esperado, no un formato roto
            "sin_tokens": (None if "modelos" in cobertura_no(p) else
                           _frac(sum(1 for f in con_msg if not _tokens_de(f)), len(con_msg))),
            "si_null": _frac(nulos, celdas),
            "recibos_sin_medicion": _frac(len(sin_med), len(recs_k)),
        }
    return out


def _escaneo(rows, ahora):
    """Lo caro (doctor / CLI): cobertura de las fuentes quietas de cerebros de
    Workspace y bytes sin medir, contra los cursores."""
    curs = _leer_json(_g("cursores.json"), {}).get("sesiones") or {}
    conocidos, mapa = _cerebros_conocidos(), _MapaImport()
    quietas = al_dia = viejas_sin_medir = 0
    ultima_actividad = None
    for (motor, sid), path in _fuentes().items():
        try:
            mtime = os.path.getmtime(path)
        except OSError:
            continue
        t, motivo = _trabajo(motor, sid, path, {}, curs, conocidos, mapa, todas=False)
        if motivo in ("fuera", "errores", "filtro"):
            continue
        ultima_actividad = max(ultima_actividad or 0, mtime)
        if ahora - mtime < 3600:
            continue                                # todavía no está quieta
        quietas += 1
        if motivo == "al_dia":
            al_dia += 1
        elif ahora - mtime > UMBRALES["sin_medir_dias_max"] * 86400:
            viejas_sin_medir += 1
    ultima_fila = max([epoch(f.get("fin")) or 0 for f in rows] or [0]) or None
    return {"fuentes_quietas": quietas, "cobertura": _frac(al_dia, quietas),
            "fuentes_sin_medir_viejas": viejas_sin_medir,
            "horas_desde_ultima_fila": round((ahora - ultima_fila) / 3600.0, 1)
            if ultima_fila else None,
            "horas_actividad_sin_fila": round(max(0.0, (ultima_actividad or 0) -
                                                  (ultima_fila or 0)) / 3600.0, 1)
            if ultima_actividad else None}


def salud(escanear=True, escribir=True):
    """El autodiagnóstico de las métricas: semáforo (0 verde · 1 equipo · 2
    usuario), solo números y nombres. Al USUARIO solo le llegan 3 avisos
    (no se puede escribir, 7 días sin filas habiendo sesiones, el
    interruptor de emergencia contra el ajuste); lo demás es para el equipo
    (doctor y paquete de diagnóstico). Lo estadístico no alarma con menos de
    _MIN_CIERRES cierres. Escribe salud.json."""
    ahora = time.time()
    rows = list(filas())
    recs = list(recibos())
    lat = _latidos()
    log = _eventos_log()
    inicios = {l.get("run_id"): l for l in lat if l.get("fase") == "inicio"}
    fines = {l.get("run_id"): l for l in lat if l.get("fase") == "fin"}
    cortados = [r for r, l in inicios.items() if r not in fines
                and (epoch(l.get("t")) or ahora) < ahora - 60]
    try:
        cola = sorted(f for f in os.listdir(_ruta("cola")) if f.endswith(".json"))
    except OSError:
        cola = []
    cola_vieja = None
    if cola:
        try:
            cola_vieja = round((ahora - int(cola[0].split("-")[0]) / 1000.0) / 86400.0, 2)
        except ValueError:
            cola_vieja = None
    medidas = [f for f in rows if not str(f.get("tramo") or "").startswith("r:")]
    leidas = sum((f.get("captura") or {}).get("leidas") or 0 for f in medidas)
    por_mv, n_fallas = {}, 0
    for f in rows:
        cap = f.get("captura") or {}
        falla = (cap.get("estado") in ("sin_transcript", "error")
                 or cap.get("captura_motor") in ("missing", "failed"))
        n_fallas += falla
        a = por_mv.setdefault("%s@%s" % (f.get("motor"), f.get("motor_version")), [0, 0])
        a[0] += 1
        a[1] += falla
    sospechosos = 0
    for f in medidas:
        h = f.get("herramientas") or {}
        llam = sum((m.get("llamadas") or 0) for m in (f.get("modelos") or {}).values())
        if ((_tokens_de(f) and not llam)
                or ((h.get("errores") or 0) > (h.get("llamadas") or 0))
                or ((f.get("duracion_activa_s") or 0) > (f.get("duracion_pared_s") or 0) + 1
                    and f.get("duracion_pared_s") is not None)
                or (epoch(f.get("fin")) or 0) > ahora + 300):
            sospechosos += 1
    cuadres = [(f.get("tokens_motor") or {}).get("cuadre") for f in rows]
    cuadres = [c for c in cuadres if isinstance(c, (int, float))]
    medidas_sesiones = {(f.get("motor"), f.get("sesion_motor")) for f in rows}
    recs_med = [r for r in recs if r.get("fuentes")
                and (epoch(r.get("t")) or ahora) < ahora - 3600]
    met = {
        "cierres": len(inicios), "filas": len(rows), "recibos": len(recs),
        "p95_cierre_ms": _p95([l["ms"] for l in fines.values() if isinstance(l.get("ms"), int)]),
        "cortados": _frac(len(cortados), len(inicios)),
        "cierres_con_error": sum(1 for l in fines.values() if l.get("resultado") == "error"),
        "cola": len(cola), "cola_vieja_dias": cola_vieja,
        "cola_descartadas": log.get("cola_descartada", 0),
        "recibos_sin_fila": _frac(sum(1 for r in recs_med if (r.get("motor"), r.get("sesion_motor"))
                                      not in medidas_sesiones), len(recs_med)),
        "fallas_captura": _frac(n_fallas, len(rows)),
        "ignoradas": _frac(sum((f.get("captura") or {}).get("lineas_ignoradas") or 0
                               for f in medidas), leidas),
        "formato_desconocido": sum(1 for f in rows if (f.get("captura") or {}).get("estado")
                                   == "formato_desconocido"),
        "ceros_sospechosos": _frac(sospechosos, len(medidas)),
        "cuadre_alto": _frac(sum(1 for c in cuadres if c > 1.03), len(cuadres)),
        "cuadre_bajo": _frac(sum(1 for c in cuadres if c < 0.97), len(cuadres)),
        "conflictos": log.get("fila_en_conflicto", 0),
        "pendientes_descartados": log.get("pendiente_descartado", 0),
        "maquina_regenerada": log.get("maquina_regenerada", 0),
    }
    if escanear:
        met.update(_escaneo(rows, ahora))
    canarios = _canarios(rows, recs, ahora)
    U = UMBRALES
    estad = met["cierres"] >= _MIN_CIERRES
    alarmas = []

    def alarma(codigo, cond, estadistica=True):
        if cond and (estad or not estadistica):
            alarmas.append(codigo)
    if met.get("cobertura") is not None:
        alarma("cobertura_urgente", met["cobertura"] < U["cobertura_urgente"])
        alarma("cobertura", U["cobertura_urgente"] <= met["cobertura"] < U["cobertura_min"])
    alarma("recibos_sin_fila", (met["recibos_sin_fila"] or 0) > U["recibos_sin_fila_max"])
    for k, (n, malos) in sorted(por_mv.items()):
        alarma("fallas_captura:" + k, n >= _CANARIO_MIN and malos / float(n) > U["fallas_captura_max"])
    alarma("p95_cierre", (met["p95_cierre_ms"] or 0) > U["p95_cierre_ms_max"])
    alarma("cortados", (met["cortados"] or 0) > U["cortados_max"])
    alarma("cola", met["cola"] > U["cola_max"], False)
    alarma("cola_vieja", (cola_vieja or 0) > U["cola_vieja_dias_max"], False)
    alarma("cola_descartadas", met["cola_descartadas"] > 0, False)
    alarma("fuentes_sin_medir", (met.get("fuentes_sin_medir_viejas") or 0) > 0)
    alarma("ignoradas", (met["ignoradas"] or 0) > U["ignoradas_max"])
    alarma("formato_desconocido", met["formato_desconocido"] > 0, False)
    alarma("ceros_sospechosos", (met["ceros_sospechosos"] or 0) > U["ceros_sospechosos_max"])
    alarma("cuadre_alto", (met["cuadre_alto"] or 0) > U["cuadre_alto_max"])
    alarma("conflictos", met["conflictos"] > 0, False)
    alarma("pendientes_descartados", met["pendientes_descartados"] > 0, False)
    alarma("maquina_regenerada", met["maquina_regenerada"] > 0, False)
    for k, c in sorted(canarios.items()):
        for nombre, lim in (("desconocidas", "canario_desconocidas_max"),
                            ("ignoradas", "canario_ignoradas_max"),
                            ("sin_tokens", "canario_sin_tokens_max"),
                            ("si_null", "canario_si_null_max"),
                            ("recibos_sin_medicion", "canario_recibos_sin_medicion_max")):
            alarma("canario_%s:%s" % (nombre, k), (c.get(nombre) or 0) > U[lim], False)
    avisos = []
    if not _puede_escribir():
        avisos.append("no_escribe")
    if (met.get("horas_actividad_sin_fila") or 0) > U["sin_filas_dias_usuario"] * 24:
        avisos.append("sin_filas")
    try:
        import settings
        encendido = settings.enabled(SETTING, default=True)
    except Exception:
        encendido = True
    if os.environ.get(ENV_APAGADO) and encendido:
        avisos.append("interruptor")
    codigo = 2 if avisos else (1 if alarmas else 0)
    doc = {"schema": SCHEMA, "t": iso(ahora), "estado": codigo,
           "semaforo": ("verde", "amarillo", "rojo")[codigo], "generacion": generacion(),
           "min_cierres": _MIN_CIERRES, "estadistico": estad, "metricas": met,
           "canarios": canarios, "alarmas": alarmas, "avisos": avisos}
    if escribir:
        try:
            _escribir_json(_ruta("salud.json"), doc)
        except OSError:
            pass
    return doc


_TEXTO_AVISO_SALUD = {
    "no_escribe": ("metricas.health.cant_write",
                   "Workspace no puede escribir sus métricas en {p}: revisa permisos o espacio."),
    "sin_filas": ("metricas.health.no_rows",
                  "Hace más de 7 días que no se registra ninguna sesión aunque las hay: corre "
                  "`workspace doctor`."),
    "interruptor": ("metricas.health.env_wins",
                    "WORKSPACE_NO_METRICAS las mantiene apagadas aunque el ajuste diga "
                    "encendidas."),
}


def salud_en_segundo_plano(cada_s=86400):
    """salud.json a diario, FUERA del cierre: el hub lo pide al abrir y corre
    en un hilo (lee todas las filas: con 20 k, ~0.7 s). Jamás bloquea."""
    try:
        p = _ruta("salud.json")
        if os.path.exists(p) and time.time() - os.path.getmtime(p) < cada_s:
            return None
        import threading

        def correr():
            # en un hilo del hub: un fallo jamás se pinta sobre la TUI
            try:
                salud(escanear=False, escribir=True)
            except BaseException as exc:      # noqa: B902 — hasta SystemExit, al log
                _log("salud_fallo", error=type(exc).__name__)
        th = threading.Thread(target=correr, name="metricas-salud", daemon=True)
        th.start()
        return th
    except Exception:
        return None


def linea_hub(ancho=None):
    """Una línea para el hub: el aviso de privacidad (una sola vez) o, si el
    último salud.json trae uno, el aviso al USUARIO. '' si nada. Jamás
    calcula ni levanta: lee lo que ya hay.

    Con `ancho` (columnas que el hub puede pintar): si el aviso corto no cabe
    entero NO se da por mostrado — el hub lo cortaría y el usuario nunca
    leería que Workspace no envía nada ni cómo apagarlo; sale completo al
    abrir el siguiente agente (dispatch._metricas_al_abrir)."""
    try:
        if fecha_aviso() is None and not apagado():
            txt = texto_aviso(corto=True)
            if ancho is not None and len(txt) > ancho:
                return ""
            a = aviso_pendiente(corto=True)
            if a:
                return a
        for c in _leer_json(_ruta("salud.json"), {}).get("avisos") or ():
            if c in _TEXTO_AVISO_SALUD:
                k, es = _TEXTO_AVISO_SALUD[c]
                return _t(k, es, p=carpeta())
    except Exception:
        pass
    return ""


def _imprimir_salud(doc):
    print(_t("metricas.health.title", "Salud de las métricas · {s}",
             s=_t("metricas.health." + doc["semaforo"], doc["semaforo"])))
    for a in doc["avisos"]:
        k, es = _TEXTO_AVISO_SALUD[a]
        print("  " + _t(k, es, p=carpeta()))
    m = doc["metricas"]
    print("  " + _t("metricas.health.summary",
                    "cierres: {c} · filas: {f} · cobertura: {cov} · p95 del cierre: {p} ms",
                    c=m["cierres"], f=m["filas"],
                    cov="—" if m.get("cobertura") is None else "%d %%" % round(m["cobertura"] * 100),
                    p="—" if m["p95_cierre_ms"] is None else m["p95_cierre_ms"]))
    if doc["alarmas"]:
        print("  " + _t("metricas.health.team", "para el equipo (doctor --bundle): {a}",
                        a=", ".join(doc["alarmas"][:8]) + (" …" if len(doc["alarmas"]) > 8 else "")))
    elif not doc["estadistico"]:
        print("  " + _t("metricas.health.few", "todavía pocos cierres para alarmar (mínimo {n})",
                        n=doc["min_cierres"]))


# ═══════════════════════════════════════════════════════════════════════════
# CLI · workspace metricas …
# ═══════════════════════════════════════════════════════════════════════════

_SUB = {"estado": "estado", "status": "estado",
        "importar": "importar", "import": "importar",
        "exportar": "exportar", "export": "exportar",
        "apagar": "apagar", "off": "apagar",
        "encender": "encender", "on": "encender",
        "salud": "salud", "health": "salud",
        "borrar": "borrar", "delete": "borrar",
        "reconstruir": "reconstruir", "rebuild": "reconstruir"}


#: banderas en inglés → las de la CLI
_BANDERAS = {"--mine": "--mio", "--all": "--todo", "--before": "--antes",
             "--undo": "--deshacer", "--per-person": "--por-persona"}


def _uso():
    return _t("metricas.usage",
              "uso: workspace metricas [estado | importar [--mio] | exportar --json <archivo> "
              "[--por-persona] | salud [--json] | borrar --mio|--todo|--antes AAAA-MM | "
              "reconstruir [--deshacer] | apagar | encender]")


def _imprimir_estado(e):
    print(_t("metricas.title", "Métricas de Workspace · {estado}",
             estado=(_t("metricas.off", "apagadas") if e["apagado"]
                     else _t("metricas.on", "encendidas"))))
    print("  " + _t("metricas.where", "carpeta: {p}", p=e["carpeta"]))
    print("  " + _t("metricas.parsers", "motores medidos: {m}",
                    m=", ".join(e["parsers"]) or "—"))
    if not e["filas"]:
        print("  " + _t("metricas.empty", "sin registros todavía (se llenan al cerrar "
                                          "cada sesión; `workspace metricas importar` "
                                          "mide la historia)"))
        return
    print("  " + _t("metricas.rows", "filas: {n} · desde {d} hasta {h}",
                    n=e["filas"], d=e["desde"] or "—", h=e["hasta"] or "—"))
    print("  " + _t("metricas.by_engine", "por motor:") + " " + " · ".join(
        _t("metricas.engine_row", "{m} {f} ({s} sesiones)", m=m, f=v["filas"], s=v["sesiones"])
        for m, v in e["por_motor"].items()))
    print("  " + _t("metricas.by_agent", "por agente:") + " " + " · ".join(
        "%s %d" % (a, n) for a, n in e["por_agente"].items()))


def _mostrar_aviso():
    a = aviso_pendiente()
    if a:
        print(a)


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    sub = _SUB.get(args[0].lower()) if args else "estado"
    if sub is None:
        print(_uso())
        return 2
    rest = [_BANDERAS.get(x, x) for x in args[1:]]
    if sub == "estado":
        e = estado()
        if "--json" in rest:
            print(json.dumps(e, ensure_ascii=False, indent=2))
        else:
            _mostrar_aviso()
            _imprimir_estado(e)
        return 0
    if sub in ("apagar", "encender"):
        try:
            import settings
            settings.set(SETTING, sub == "encender")
        except Exception as exc:
            print(_t("metricas.setting_fail", "no pude guardar el ajuste: {err}", err=exc))
            return 1
        (_marcar_encendido if sub == "encender" else _marcar_apagado)()
        print(_t("metricas.now_on", "Métricas encendidas: se mide desde ahora. Lo que hiciste "
                                    "mientras estaban apagadas no se mide.")
              if sub == "encender" else
              _t("metricas.now_off", "Métricas apagadas: lo que hagas desde ahora no se mide, "
                                     "tampoco cuando las vuelvas a encender."))
        if os.environ.get(ENV_APAGADO) and sub == "encender":
            print(_t("metricas.env_wins", "Aviso: {env} está definido y las mantiene apagadas.",
                     env=ENV_APAGADO))
        return 0
    if sub == "importar":
        if apagado():
            print(_t("metricas.import_off", "Las métricas están apagadas: no importo nada."))
            return 1
        _mostrar_aviso()
        print(_t("metricas.importing", "Midiendo la historia de esta máquina…"))
        r = importar(mio="--mio" in rest)
        for motor, v in sorted(r.items()):
            print("  " + _t("metricas.import_row",
                            "{m}: {s} sesiones · {f} filas nuevas · {a} ya medidas · "
                            "{o} fuera de cerebros · {e} errores",
                            m=motor, s=v["sesiones"], f=v["filas"], a=v["al_dia"],
                            o=v["fuera"], e=v["errores"]))
        return 0
    if sub == "exportar":
        if "--json" not in rest or rest.index("--json") + 1 >= len(rest):
            print(_uso())
            return 2
        destino = rest[rest.index("--json") + 1]
        doc = exportar(destino, por_persona="--por-persona" in rest)
        if destino != "-":
            print(_t("metricas.exported", "Agregados en {p} ({n} grupos).",
                     p=os.path.abspath(destino), n=len(doc["grupos"])))
        return 0
    if sub == "salud":
        doc = salud(escanear=True, escribir=True)
        if "--json" in rest:
            print(json.dumps(doc, ensure_ascii=False, indent=2))
        else:
            _imprimir_salud(doc)
        return doc["estado"]
    if sub == "borrar":
        antes = rest[rest.index("--antes") + 1] if "--antes" in rest and \
            rest.index("--antes") + 1 < len(rest) else None
        try:
            r = borrar(mio="--mio" in rest, todo="--todo" in rest, antes=antes)
        except ValueError:
            print(_uso())
            return 2
        print(_t("metricas.deleted", "Borrado: {f} filas · {t} turnos · {r} recibos · "
                                     "{n} nombres. Lo borrado no se vuelve a importar.",
                 f=r["filas"], t=r["turnos"], r=r["recibos"], n=r["nombres"]))
        if r.get("ambiguos"):
            print(_t("metricas.delete_who", "En {c} no sé quién eres en esta computadora, así "
                                            "que ahí no borré nada: elige tu usuario en "
                                            "Workspace → Usuarios («soy yo en esta PC») y vuelve a correr "
                                            "`workspace metricas borrar --mio`.",
                     c=", ".join(x.split("#")[0] for x in r["ambiguos"])))
        if r.get("no_borrados"):
            print(_t("metricas.delete_locked", "No pude borrar o reescribir {n} archivo(s) de "
                                               "métricas ({a}): otro programa los tiene abiertos "
                                               "o faltan permisos. Cierra el hub y tus agentes y "
                                               "vuelve a correr el mismo comando.",
                     n=len(r["no_borrados"]), a=", ".join(sorted(set(r["no_borrados"])))))
            return 1
        return 0
    if sub == "reconstruir":
        if "--deshacer" in rest:
            g = deshacer_reconstruccion()
            print(_t("metricas.rebuild_undone", "De vuelta en la generación {g}.", g=g))
            return 0
        if apagado():
            print(_t("metricas.import_off", "Las métricas están apagadas: no importo nada."))
            return 1
        print(_t("metricas.rebuilding", "Re-midiendo toda la historia a una generación nueva…"))
        r = reconstruir()
        print(_t("metricas.rebuilt", "Generación {g} lista ({f} filas; antes, la {p}). Para "
                                     "volver: `workspace metricas reconstruir --deshacer`.",
                 g=r["generacion"], f=r["filas"], p=r["previa"]))
        if r.get("motores_conservados"):
            print(_t("metricas.rebuild_kept", "Sin re-medir (sus respaldos no se pueden volver "
                                              "a cortar igual): {m}. Sus filas quedan como "
                                              "estaban.", m=", ".join(r["motores_conservados"])))
        return 0
    return 2


if __name__ == "__main__":
    try:                              # Windows: «·», «→» y acentos por una tubería
        import _utf8
        _utf8.harden()
    except Exception:
        pass
    sys.exit(main())
