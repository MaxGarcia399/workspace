"""WORKSPACE · control — la capa de control oficial: UNA interfaz para que la
página hable con cualquier motor sin leer su pantalla ni teclear en ella
(contrato en control/base.py).

    import control
    c = control.conector("opencode", cwd=cerebro, url="http://127.0.0.1:4096")
    sid = c.abrir()
    c.mandar("hola")
    for ev in c.eventos(timeout=60): …

Cada motor va por su vía OFICIAL, con su binario y el login del socio; aquí
nada lee ni guarda tokens. VIAS dice, por motor, qué vía usa, si la página
ve la misma conversación que la terminal, qué hace SIN preguntar
(`sin_preguntar`: escribir y/o comando; así es el motor, no un fallo) y si es
«solo mirar» (`solo_mirar`: la página no escribe y ofrece «Ir a la terminal»;
`puede_escribir(motor)`)."""
import importlib

from control.base import DECISIONES, ESTADOS, TIPOS, Conector, ErrorControl, apagar  # noqa: F401

#: motor → (módulo, clase, ¿es ACP?)
_CLASES = {
    "claude-code": ("control.claude_code", "ClaudeCode", False),
    "opencode": ("control.opencode", "OpenCode", False),
    "openclaw": ("control.openclaw", "OpenClaw", False),
    "hermes": ("control.hermes", "Hermes", False),
    "codex": ("control.codex", "Codex", False),
    "copilot": ("control.acp", "ACP", True),
    "cursor": ("control.acp", "ACP", True),
    "kiro": ("control.acp", "ACP", True),
    "antigravity": ("control.acp", "ACP", True),
    "openclaw-acp": ("control.openclaw", "OpenClawACP", True),
    "hermes-acp": ("control.acp", "ACP", True),
}

#: VERIFICADO con el probador real (17-nov): lo que el motor hace sin pedir
#: permiso por su vía de control (no tiene «preguntar»).
_SIN_PREGUNTAR_OPENCLAW = ("escribir", "comando")
_AVISO_OPENCLAW = ("OpenClaw no pide permiso: escribe y corre comandos sin preguntar (su modo de "
                   "permisos de la sesión).")

#: Lo que la página dice de cada motor.
VIAS = {
    "claude-code": {"via": "claude -p --resume (stream-json), una corrida por mensaje",
                    "misma_conversacion": True,
                    "aviso": "Escribe desde la página solo con su terminal cerrada."},
    "opencode": {"via": "servidor oficial (API HTTP + eventos)", "misma_conversacion": True},
    # Desde la página (18-nov) el connect del gateway se rechazó por client.id/mode; ya van
    # con los de su doc, pero hasta que el probador real lo pase, se escribe por su puente
    # ACP, que sí lo pasó.
    "openclaw": {"via": "gateway (WebSocket)", "misma_conversacion": True,
                 "sin_preguntar": _SIN_PREGUNTAR_OPENCLAW, "solo_mirar": True,
                 "escribir_por": "openclaw-acp", "aviso": _AVISO_OPENCLAW},
    "openclaw-acp": {"via": "ACP (puente oficial al gateway)", "misma_conversacion": False,
                     "sin_preguntar": _SIN_PREGUNTAR_OPENCLAW, "aviso": _AVISO_OPENCLAW},
    # Probador real (0.22.5, 17 y 18-nov): el WebSocket de `hermes serve` da 403 y su ayuda
    # no dice qué pide. Hasta que una corrida lo abra: solo mirar (escribir, por hermes-acp).
    "hermes": {"via": "gateway (JSON-RPC)", "misma_conversacion": True, "solo_mirar": True,
               "escribir_por": "hermes-acp",
               "aviso": "Hermes: solo mirar. Para escribirle, «Ir a la terminal» (o su chat ACP "
                        "aparte)."},
    # Probador real (18-nov, ronda 5): pidió aprobación para escribir el archivo, pero corrió
    # `touch` sin pedirla. Ni `hermes acp --help` ni la config del perfil workspace traen una
    # opción para que pregunte por todo comando (no se toca nada global ni se lee su código).
    "hermes-acp": {"via": "ACP (nativo de Hermes)", "misma_conversacion": False,
                   "sin_preguntar": ("comando",),
                   "aviso": "Hermes pide aprobación para algunas acciones (escribir archivos), pero "
                            "corre otros comandos sin preguntar, aunque Workspace esté en «preguntar»."},
    # Probador real (18-nov, ronda 5): con approvalPolicy on-request no preguntó por `touch`; su
    # sandbox lo bloqueó («Operation not permitted»). Su --help solo trae on-request («The model
    # decides when to ask») y never: no hay una política de «preguntar siempre».
    "codex": {"via": "app-server (JSON-RPC)", "misma_conversacion": False,
              "aviso": "Uso personal: el app-server con login de ChatGPT no se permite en "
                       "productos vendidos. Codex pregunta cuando el modelo lo decide (on-request, "
                       "la única política suya que pregunta); un comando que su sandbox bloquea "
                       "falla sin preguntar."},
    # Probador real (17-nov): «Error: You have exceeded your monthly quota» llegó como texto
    # del agente (agent_message_chunk) con stopReason end_turn, sin señal estructurada.
    "copilot": {"via": "ACP", "misma_conversacion": False,
                "aviso": "Copilot manda sus errores de cuota como texto de la respuesta: la página "
                         "los muestra como respuesta (no hay señal para marcarlos como error)."},
    "cursor": {"via": "ACP", "misma_conversacion": False, "sin_preguntar": ("escribir",),
               # VERIFICADO con el probador real (17-nov): las ediciones van sin
               # session/request_permission; el comando de terminal sí lo pidió. cable-cursor
               # (19-nov, 2026.11.19-f005e9d, caja negra por ACP): también las de FUERA de su
               # carpeta (creó /tmp/… sin pedir); por eso «Preguntarme todo» no se ofrece (B02).
               "aviso": "Cursor aplica sin preguntar las ediciones, también fuera de su carpeta (así "
                        "funciona su modo agent); los comandos sí los pregunta."},
    "kiro": {"via": "ACP", "misma_conversacion": False},
    "antigravity": {"via": "ACP", "misma_conversacion": False,
                    "aviso": "Antigravity con tu cuenta personal de Google solo se usa en su terminal: Google "
                             "prohíbe usarla en otras apps y puede suspender tu acceso. Para escribirle desde "
                             "aquí, pon una API key de Google AI Studio (o una cuenta de empresa)."},
}

#: A3-a (22-nov, decisión del dueño): con la cuenta personal de Google, la página NO le escribe a Antigravity
#: (sus términos, punto 6: «in connection with products not provided by us» → suspensión). Solo mirar e «Ir a
#: la terminal». Con API key de AI Studio o cuenta empresarial, la página sí.
SOLO_TERMINAL_CON_CUENTA_PERSONAL = ("antigravity",)


def _cuenta_personal(motor):
    """¿Este motor está con una cuenta personal que sus términos no dejan usar desde otra app? Falla-cerrado:
    si no se puede saber, se trata como personal (no se escribe)."""
    if motor not in SOLO_TERMINAL_CON_CUENTA_PERSONAL:
        return False
    try:
        from engines import antigravity as A
        return A.account_kind() == A.CUENTA_GOOGLE
    except Exception:
        return True


def motores():
    return list(_CLASES)


def puede_escribir(motor):
    """¿La página puede mandar mensajes a este motor? False = «solo mirar»: la
    página muestra la conversación y el botón «Ir a la terminal»."""
    return motor in VIAS and not VIAS[motor].get("solo_mirar") and not _cuenta_personal(motor)


def para_escribir(motor):
    """Por qué conector escribe la página a este motor: él mismo; o, si es
    «solo mirar», el que diga `escribir_por` (OpenClaw → su puente ACP, Hermes
    → su ACP: chats aparte); o None = solo «Ir a la terminal»."""
    if puede_escribir(motor):
        return motor
    otro = VIAS.get(motor, {}).get("escribir_por")
    return otro if otro and puede_escribir(otro) else None


def conector(motor, pestana=None, tope_abrir=None, **opciones):
    """Un conector (todavía cerrado) para `motor`. Las opciones van a su
    clase (cwd, cmd, url, grabar, …). `pestana` = la pestaña de la página
    ({"ws", "wid", "agente", "cerebro"}): el motor arranca con ESAS variables
    de identidad y sin las de otra pestaña (control/entorno.py). `tope_abrir`
    = segundos para que el motor termine de abrir (por defecto 45)."""
    if motor not in _CLASES:
        raise ErrorControl("motor sin capa de control: %s (hay: %s)" % (motor, ", ".join(_CLASES)))
    if _cuenta_personal(motor):                     # A3-a: ninguna vía (chat, skills, encargos) lo abre así
        raise ErrorControl(VIAS[motor]["aviso"])
    modulo, clase, es_acp = _CLASES[motor]
    cls = getattr(importlib.import_module(modulo), clase)
    c = cls(motor, **opciones) if es_acp else cls(**opciones)
    c.pestana = pestana
    if tope_abrir is not None:
        c.tope_abrir = float(tope_abrir)
    return c
