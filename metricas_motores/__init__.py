"""WORKSPACE · metricas_motores — parsers de métricas, UNO por motor (enchufables).

Por qué un paquete aparte: los formatos de cada motor cambian por versión y
cada motor guarda su historial distinto (JSONL que solo crece, exports que se
reescriben, SQLite…). El núcleo (metricas.py: cursores, huellas, filas,
atribución, candado) no conoce ningún formato; cada motor trae su lector
aquí. Agregar un motor = agregar `metricas_motores/<motor>.py` con el contrato
de abajo: se descubre solo (registro()), sin tocar el núcleo ni una lista.
Un motor que Workspace lanza y que NO tiene parser se declara en SIN_PARSER
con su motivo (lo exige el kit de conformidad).

CONTRATO de un módulo parser (esquema g2, F1.1):

    MOTOR = "codex"                 # nombre del motor (el de engines/, payload["engine"])
    VERSION = "codex/2"             # sube cuando cambie QUÉ se cuenta (viaja en cada fila)
    VERIFIED_VERSIONS = ("0.164.0",)
        Versiones EXACTAS del motor verificadas con su golden (fixtures en
        tests/fixtures/metricas/<motor>/<versión>/). La fila dice
        captura.verificado = "si" si la versión está aquí.
    CANARIOS = True                 # opcional: una versión no listada sale
        "por_canarios" (no "no"): para motores que publican casi a diario
        (Claude Code); la vigilan los canarios de `metricas salud`.
    COBERTURA = {campo: (estado, motivo), …}
        Un par por CADA campo de metricas.CAMPOS_COBERTURA (ni más ni
        menos), estado en metricas.ESTADOS_COBERTURA:
          "si"      — el motor lo da (motivo puede ser "");
          "parcial" — a veces null en un tramo (tramo.sin_dato.add(campo)),
                      o aproximado: el motivo dice cuándo y por qué;
          "no"      — el motor no lo da: el NÚCLEO lo deja null en toda fila
                      (nunca 0), aunque el parser cuente algo.
    CONTINUACION = {"retomar": m, "continuar": m}
        Cómo sigue una sesión (m en metricas.MECANISMOS_CONTINUACION):
        retomar = la misma sesión otra vez; continuar = sesión nueva que
        sigue a otra (copia de historial, cadena…).

    def minar(path, cur, tramo, hasta_t=None, cola=False) -> dict
        Mide lo NUEVO de `path` a partir de `cur` (el cursor de esa sesión:
        lo define el parser — offset de bytes, ids vistos…; {} la primera
        vez). Llena `tramo` (metricas.Tramo, ver abajo). Respeta `hasta_t`
        (time.monotonic): lo que no alcance queda en el cursor para el
        próximo tramo (completo=False).
        Devuelve {"cursor": {cursor nuevo}, "completo": bool,
                  "costo": (usd, fuente, detalle) | None,
                  "desde"/"hasta": marcas opcionales para captura}.
        El id del tramo lo pone el núcleo (huella del rango de cursores).
        Puede levantar OSError (transcript ilegible): el núcleo deja recibo.

    def sesion(path) -> str         # id de sesión del motor para ese transcript

Opcionales:
    def fuentes() -> [(sid, path)]  # transcripts que existen en la máquina (importar)
    def cabecera(path) -> (cwd, ts) # default: metricas.cabecera (cwd/timestamp en JSONL)
    def al_dia(path, cur) -> bool   # importar: ¿nada nuevo? (para saltarlo barato)
    def transcript_de_cierre(brain, payload) -> path
                                    # al cerrar sin transcript_path en el payload
    def raices() -> [(carpeta, profundidad)]
    def es_fuente(nombre) -> bool   # juntas: el núcleo indexa las fuentes con caché
                                    # por mtime de carpeta (sin leer nada que no cambió);
                                    # sin ellas, usa fuentes() en cada enumeración
    SIN_RECIBO_VACIO = True         # una corrida sin nada nuevo NO deja fila
    RECONSTRUIBLE = True            # la fuente solo crece y captura.hasta es su corte
                                    # en bytes: `reconstruir` la re-mide igual. Sin
                                    # esto (respaldos reescritos, totales de sesión),
                                    # reconstruir conserva filas y estado TAL CUAL

Lo que el parser llena en el Tramo:
  · Por CADA línea: tramo.reconocer() si entendió su tipo (aunque no cuente
    nada), o tramo.desconocer(tipo) si no (solo el NOMBRE del tipo). El
    núcleo cuenta las leídas; leídas sin ninguna reconocida (o
    tramo.formato_desconocido = True) = formato desconocido: la fila va con
    todo lo medido en null, estado «formato_desconocido» y el cursor NO
    avanza.
  · Eventos: tramo.nuevo/ver(clave, ts) (huellas: nada se cuenta dos veces),
    tramo.ts, uso(modelo, tokens), activa(ms), llamadas, errores,
    interrupciones, mensajes, skill(nombre, ruta)/skills_de_texto, escrito.
  · Turnos (sin texto): turno(ts, texto, origen, ausente) al empezar cada
    pedido; respuesta(ts) en cada evento de la respuesta; compactacion();
    cerrar_turno() antes de sumar totales que no son de un turno.
  · g2: modelo_pedido, esfuerzo, permisos, facturacion, costo_tipo,
    tokens_motor, ver_cuota(q), comandos_no_cero, respuesta_error(código),
    senal(nombre, valor), degradada, sin_dato, avisos.
Ayudas del núcleo (metricas.*): recorrer() para JSONL que solo crecen (cursor
= offset de bytes), recorrer_reescrito() → (cursor, completo) +
al_dia_por_firma() para respaldos que Workspace reescribe enteros en cada
cierre, primera_linea(), epoch/iso/entero/numero/nombre_modelo/clase_error;
Tramo.leer/anotar para el estado compartido del motor. Lo que el transcript
no trae (versión del motor) lo completa el núcleo, solo de cachés y en vivo.

Reglas para todo parser: solo números y nombres (jamás texto de mensajes ni de
herramientas: se LEE para clasificar, no se guarda), «sin dato» = None,
tolerante a versiones (claves faltantes → None, nunca revienta), utf-8-sig
(las ayudas ya lo hacen), stdlib 3.9+.
"""
import importlib
import pkgutil

#: Motores que Workspace lanza y que NO tienen parser, con el motivo. Su
#: cierre deja solo el recibo (captura.estado = "sin_parser").
SIN_PARSER = {
    "gemini": ("Workspace no respalda ni ubica el historial de Gemini CLI al "
               "cerrar (session_continuity no tiene captura para gemini): sin una "
               "fuente estable no hay qué medir; queda el recibo."),
}

_REGISTRO = None


def registro():
    """{motor: módulo} de los parsers válidos de este paquete. Falla-suave por
    módulo: uno roto no tumba a los demás (ese motor queda «sin parser»).
    Válido = lo mínimo para MEDIR (MOTOR, VERSION, minar, sesion); el resto
    del contrato lo revisa contrato() (el kit de conformidad lo exige)."""
    global _REGISTRO
    if _REGISTRO is None:
        reg = {}
        for m in pkgutil.iter_modules(__path__):
            if m.name.startswith("_"):
                continue
            try:
                mod = importlib.import_module("%s.%s" % (__name__, m.name))
            except Exception:
                continue
            motor = getattr(mod, "MOTOR", None)
            if (isinstance(motor, str) and motor and getattr(mod, "VERSION", None)
                    and callable(getattr(mod, "minar", None))
                    and callable(getattr(mod, "sesion", None))):
                reg[motor] = mod
        _REGISTRO = reg
    return _REGISTRO


def parser(motor):
    return registro().get(motor)


def contrato(mod):
    """Problemas del módulo `mod` contra el contrato g2 ([] = cumple)."""
    import metricas as M
    probs = []
    for k in ("MOTOR", "VERSION"):
        if not (isinstance(getattr(mod, k, None), str) and getattr(mod, k)):
            probs.append("%s: falta o no es texto" % k)
    for k in ("minar", "sesion"):
        if not callable(getattr(mod, k, None)):
            probs.append("%s(): falta" % k)
    vv = getattr(mod, "VERIFIED_VERSIONS", None)
    if not (isinstance(vv, tuple) and all(isinstance(v, str) and v and v.strip() == v
                                          for v in vv)):
        probs.append("VERIFIED_VERSIONS: debe ser una tupla de versiones exactas")
    cob = getattr(mod, "COBERTURA", None)
    if not isinstance(cob, dict):
        probs.append("COBERTURA: falta (dict campo → (estado, motivo))")
    else:
        faltan = [c for c in M.CAMPOS_COBERTURA if c not in cob]
        sobran = [c for c in cob if c not in M.CAMPOS_COBERTURA]
        if faltan:
            probs.append("COBERTURA: faltan %s" % ", ".join(faltan))
        if sobran:
            probs.append("COBERTURA: campos que no son del esquema: %s" % ", ".join(sobran))
        for c, v in cob.items():
            if not (isinstance(v, tuple) and len(v) == 2 and v[0] in M.ESTADOS_COBERTURA
                    and isinstance(v[1], str)):
                probs.append("COBERTURA[%s]: debe ser (si|parcial|no, motivo)" % c)
            elif v[0] != "si" and not v[1].strip():
                probs.append("COBERTURA[%s]: «%s» sin motivo" % (c, v[0]))
    cont = getattr(mod, "CONTINUACION", None)
    if not (isinstance(cont, dict) and set(cont) == {"retomar", "continuar"}
            and all(v in M.MECANISMOS_CONTINUACION for v in cont.values())):
        probs.append("CONTINUACION: debe ser {retomar, continuar} con mecanismos de "
                     "metricas.MECANISMOS_CONTINUACION")
    return probs


def verificado(mod, version):
    """captura.verificado de una fila: "si" (versión exacta verificada),
    "por_canarios" (no listada, pero el parser se vigila por canarios) o
    "no" (no listada, o versión desconocida, o sin parser)."""
    if mod is None or not version:
        return "no"
    if version in (getattr(mod, "VERIFIED_VERSIONS", None) or ()):
        return "si"
    return "por_canarios" if getattr(mod, "CANARIOS", False) is True else "no"
