#!/usr/bin/env python3
"""WORKSPACE · pantalla_motor — la terminal de un motor, leída como chat.

Lo que muestra el panel de herdr de un motor (texto plano o con colores) se
convierte aquí en lo que pinta el chat simple del navegador y en lo que decide
si se le puede escribir:

  · pregunta_de: el menú que el motor espera que contestes (permiso, pregunta
    con opciones, «¿confías en esta carpeta?»), con números o sin ellos;
  · lectura: ¿hay un menú abierto?, ¿se ve trabajando? Es la puerta de
    aviso_panel.escribir: con un menú en pantalla jamás se teclea texto + Enter,
    diga lo que diga herdr de su estado;
  · subagentes_de y uso_de: los ayudantes y el gasto que el motor muestra;
  · _de_pantalla: tus mensajes y las respuestas, sin barras, pies, cajas de
    entrada ni las líneas que imprime Workspace al lanzar el motor.

Todo es lectura pura, sin E/S. Lo prueban las pantallas reales de
tests/fixtures/pantallas/ (test_motores_pantallas.py). Primero van las pistas
de forma (sangría, marcas, separadores, barras con «·»); los textos exactos de
un motor solo donde no hay otra señal. Stdlib, Python 3.9+.
"""
import hashlib
import re

# el texto hacia la página (recortar, ocultar llaves) no lee pantalla: vive en texto_pagina (F3)
from texto_pagina import _limpio, _recorta, _sin_secretos  # noqa: F401

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
_CAJA = set("─━│┃┄┅┆┇┈┉┊┋┌┍┎┏┐┑┒┓└┕┖┗┘┙┚┛├┝┞┟┠┡┢┣┤┥┦┧┨┩┪┫┬┭┮┯┰┱┲┳┴┵┶┷┸┹┺┻┼╋═║╒╓╔╕╖╗╘╙╚╛╜╝╞╟╠╡╢╣╤╥╦╧╨╩╪╫╬╭╮╯╰▀▄█▌▐░▒▓▔▕▖▗▘▙▚▛▜▝▞▟■□▪▫╹╻")
MAX_TURNOS = 160


# ═══════════════════════════════════════════════════════════════════════════
# Piezas de forma (sirven a todos los motores)
# ═══════════════════════════════════════════════════════════════════════════

_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")


def sin_tenue(pantalla):
    """La pantalla (con colores, `--format ansi`) sin el texto atenuado (SGR 2, «dim») ni en cursiva (SGR 3). Es lo que
    los motores pintan y no está escrito: la sugerencia gris de Claude Code en su caja («❯ abre la v2…») o el ejemplo
    en cursiva de Hermes («Plan a feature, then build it step by step», 17-nov). Sin esto,
    la caja se lee ocupada y nada se teclea (los mensajes se quedan en cola). Los colores 38/48 (que llevan un `2` de
    parámetro en «38;2;r;g;b») no cuentan como atenuado."""
    s = str(pantalla or "")
    out, tenue, pos = [], False, 0
    for m in _SGR_RE.finditer(s):
        if not tenue:
            out.append(s[pos:m.start()])
        cods = [c for c in m.group(1).split(";")] if m.group(1) else ["0"]
        i = 0
        while i < len(cods):
            c = cods[i]
            if c in ("38", "48", "58"):                     # color extendido: 5;n o 2;r;g;b, no son atributos
                i += 3 if (i + 1 < len(cods) and cods[i + 1] == "5") else 5
                continue
            if c in ("2", "3"):                             # atenuado o cursiva: así pintan su ejemplo
                tenue = True                                 # (Claude Code: gris «dim»; Hermes: cursiva)
            elif c in ("0", "", "22", "23"):
                tenue = False
            i += 1
        pos = m.end()
    if not tenue:
        out.append(s[pos:])
    return "".join(out)


def _plano(pantalla):
    """Renglones sin colores ni retornos de carro, sin espacios al final."""
    return [_ANSI_RE.sub("", l).rstrip() for l in str(pantalla or "").replace("\r", "").split("\n")]


def _sangria(ln):
    return len(ln) - len(ln.lstrip())


def _es_caja(s, umbral=0.6):
    """Un renglón que es (casi) solo dibujo de caja: separador, borde, barra de bloques."""
    v = [c for c in s if not c.isspace()]
    return bool(v) and sum(c in _CAJA for c in v) >= len(v) * umbral


# «──── Prueba corpus claude-code ─», «── ⠋ computing… · 3s ──── Lista de colores ─»: separador con título
_REGLA_TITULO_RE = re.compile(r"^\s*[─━═]{2,}\s.*\s[─━═]+\s*$")


def _es_regla(s):
    return _es_caja(s) or bool(_REGLA_TITULO_RE.match(s))


def _sin_bordes(ln):
    """«│ texto │» → «texto» (cajas de diálogo, también anidadas). La sangría DENTRO de la
    caja se conserva: las opciones de un menú siguen alineadas entre sí."""
    for _ in range(3):
        m = re.match(r"^\s*[│┃║]\s?", ln)
        if m:
            ln = ln[m.end():]
        n = re.search(r"\s*[│┃║]\s*$", ln)
        if n and n.start() > 0:
            ln = ln[:n.start()]
        elif n:
            ln = ""
        if not m and not n:
            break
    return ln.rstrip()


def es_barra(s):
    """Una barra de estado (la de Workspace bajo la caja, el pie de cada motor): 4 o más
    trozos cortos separados por « · », con algún número o «…». Una frase de la respuesta
    casi nunca tiene esa forma (un «◆ decisor: … · 92 % · aplicado» tiene 3)."""
    t = s.strip()
    if t.count(" · ") + t.count("·← ") < 3:
        return False
    partes = [p.strip() for p in re.split(r"\s+·\s*|\s{3,}", t) if p.strip()]
    if len(partes) < 4 or max(len(p) for p in partes) > 48:
        return False
    return any(re.search(r"\d|…", p) for p in partes)


# lo que imprime Workspace al lanzar el motor (dispatch, maquinas, memoria_mcp, secret_store):
# no es de la conversación. «WORKSPACE · sync: …», «WORKSPACE: …», «[WORKSPACE] agente …»,
# «  respaldo: captured · conversación …» y la segunda fila de su barra («5h ███░░ 30% usado · …»)
_WS_LANZA_RE = re.compile(r"^\s*(?:\[WORKSPACE\]\s|WORKSPACE(?:\s*·\s*[\w-]+:|:\s))|^\s*respaldo: \S+ · "
                          r"|[░▒▓█]{3,}\s*\d{1,3}% (?:usado|used)\b")
# en el arranque, antes del motor: el aviso de un decisor («◆ <nombre>: … · 56 % · sugerido»)
# y los avisos de Workspace («⚠ No pude leer tus llaves…»), pegados a la columna 0
_WS_AVISO_RE = re.compile(r"^(?:◆ [^:]{1,40}: |⚠ )")


# ═══════════════════════════════════════════════════════════════════════════
# ¿Trabaja? Lo que cada motor pinta mientras piensa o corre algo
# ═══════════════════════════════════════════════════════════════════════════

_TRABAJANDO_RE = re.compile(
    r"esc to interrupt|esc interrupt|ctrl\+c to stop|\bis working\b|type to redirect|Type to steer"
    r"|\bWorking\s*(?:\(|…|\.\.\.)|\bThinking\s*(?:…|\.\.\.)|\brunning • \d|computing\.\.\.|Delegating\.\.\."
    r"|Writing command|Sending message|\(esc to cancel\)|^\s*esc to cancel\b|\bInitializing(?:\.\.\.|…| ·)"
    r"|^\s*[✻✳✶✢✽·*]\s+\w+…\s*\(\d")                       # Claude Code: «✳ Mulling… (3s · ↓ 124 tokens…»
# un spinner braille al empezar el renglón (tras «──», «┃» o espacios): «⠋ running», «⢿  Working...»
_SPINNER_RE = re.compile(r"^\s*(?:[─━]+\s+)?(?:[┃│]\s*)?[⠀-⣿]{1,2}\s+\S")
_ARTE_BRAILLE_RE = re.compile(r"^\s*[⠀-⣿]{4,}")     # un logo dibujado en braille (Kiro, Hermes)


def _linea_trabajando(ln):
    s = ln.strip()
    return bool(s) and not _ARTE_BRAILLE_RE.match(ln) and bool(_TRABAJANDO_RE.search(ln) or _SPINNER_RE.match(ln))


def trabajando_en_pantalla(pantalla):
    """¿Se ve al motor trabajando? Solo cuenta el pie (los últimos renglones con algo):
    ahí cada motor pinta su spinner, «Working…», «esc to interrupt», «running • 4s»."""
    lineas = [l for l in _plano(pantalla) if l.strip()][-15:]
    return any(_linea_trabajando(l) for l in lineas)


# ── la caja de chat del motor: lo ÚNICO donde la página teclea (F14) ──
# El prompt al pie: «❯ …» (Claude Code), «› …» (Codex, Kiro), «→ …» (Cursor), «> …» (Antigravity), «workspace ❯ …» (Hermes).
# N3: Kiro con algo escrito lo pega al «›» («›Prueba de mensaje…», partido en renglones sangrados 1): también es su caja.
_CAJA_PROMPT_RE = re.compile(r"^\s*(?:[^\s›❯>→│┃]{1,12}\s+)?[›❯>→](?:(?:\s+|(?<=›)(?=\S))(.*?))?\s*$")
# su texto de ejemplo cuando está vacía (pantallas reales del corpus)
_CAJA_EJEMPLO_RE = re.compile(
    r"^(?:Try \".*|Ask Codex to do anything|Explain this codebase|Summarize recent commits|Implement \{feature\}"
    r"|Find and fix a bug in @filename|Write tests for @filename|Improve documentation in @filename"
    r"|Run /review on my current changes|Use /skills to list available skills|ask a question or describe a task.*"
    r"|Add a follow-up(?: ctrl\+c to stop)?|Turn these notes into a to-do list|Accept-edits mode:.*|type to redirect.*"
    r"|Kiro is working\b.*|Initializing · type to queue.*"            # los avisos de Kiro trabajando o iniciando
    r"|Press Ctrl\+C again to exit)$", re.I)                           # Cursor tras un ctrl+c (H10)
# un diálogo del motor que no siempre trae opciones numeradas (actualizar, confiar en la carpeta, sí/no)
# («⚠ update available» de Hermes y la cabecera «✨ Update available!» de Codex son avisos, no diálogos: no cuentan)
_DIALOGO_RE = re.compile(r"Update now|Press enter to (?:continue|confirm)|Do you trust|trust (?:this|the files in this) "
                         r"folder|\[y/N\]|\[Y/n\]|\(y/n\)", re.I)


def _bloque(plano, k, m):
    """Lo escrito en la caja cuyo prompt es `plano[k]`: su renglón y los que siguen del mismo texto partido, hasta un
    renglón vacío, una regla o uno que empieza más a la derecha que el texto. Ahí ya es el pie del motor («Opus 5.5»,
    «93% left», el «/sessions to resume» de Kiro), que no es la caja: un mensaje corto se encontraría en él."""
    col = m.start(1) if m.group(1) else len(plano[k])
    filas = [m.group(1) or ""]
    for l in plano[k + 1:]:
        s = l.strip()
        if not s or _es_regla(s) or len(l) - len(l.lstrip()) > col:
            break
        filas.append(s)
    return " ".join(filas)


def caja_de_entrada(pantalla, abajo=12, alto=0):
    """La caja de chat del motor, si es lo que hay al pie de su pantalla: {"texto": lo que tiene escrito, "" si está
    vacía o con su texto de ejemplo; "bloque": lo escrito entero aunque ocupe varios renglones, sin el pie del motor}.
    None si al pie hay un menú, un diálogo o nada que sea una caja (arrancando, la shell): ahí la página
    no teclea. Cuatro formas, de pantallas reales: el prompt al pie, la caja «┃ … ╹▀▀▀» (OpenCode, Copilot), el hueco
    entre las dos reglas del pie (OpenClaw) y la caja de Hermes con un texto largo, ya sin su prompt (_caja_entre_reglas).
    `alto`: los renglones que puede ocupar lo que se tecleó (un texto largo, partido, sube su prompt): la caja se busca
    en los últimos `abajo + alto`, sin pasar de la segunda regla (arriba ya es la conversación); un menú o un diálogo,
    siempre al pie (los últimos `abajo`), de su caja para abajo (dialogo_al_pie)."""
    plano = _plano(pantalla)
    while plano and not plano[-1].strip():
        plano.pop()
    if not plano or pregunta_de("\n".join(plano)) is not None:
        return None
    hallada = _caja(plano, abajo, alto)
    if hallada is None or _pista_al_pie(plano, abajo, hallada[1]):
        return None
    return hallada[0]


def _caja(plano, abajo, alto):
    """(la caja como la da caja_de_entrada, el índice en `plano` de su primer renglón) o None, sin mirar diálogos."""
    lineas = [k for k, l in enumerate(plano) if l.strip()]          # los renglones con algo (su índice en `plano`)
    donde = lineas[-(abajo + alto):]
    pie = [plano[k] for k in donde]

    def texto(t):
        t = " ".join((t or "").split())
        return "" if _CAJA_EJEMPLO_RE.match(t) else t
    reglas = 0
    for i in range(len(pie) - 1, -1, -1):
        s = pie[i].strip()
        if s.startswith("╹"):                                       # «┃ … ╹▀▀▀»: sus renglones, sin el del modelo
            filas, j = [], donde[i] - 1                             # seguidos: tras un renglón vacío ya es la conversación
            while j >= 0 and plano[j].strip().startswith("┃"):
                filas.insert(0, plano[j].strip()[1:].strip())
                j -= 1
            if len(filas) > 1 and " · " in filas[-1]:
                filas.pop()
            t = texto(" ".join(f for f in filas if f))
            return ({"texto": t, "bloque": t}, j + 1) if filas else None
        if _es_regla(s):
            reglas += 1
            if reglas == 2:
                break
            continue
        m = _CAJA_PROMPT_RE.match(pie[i])
        if m and not re.match(r"^\d{1,2}[.)]\s", m.group(1) or ""):
            return {"texto": texto(m.group(1)), "bloque": _bloque(plano, donde[i], m)}, donde[i]
    if len(pie) >= 2 and _es_regla(pie[-1].strip()):                 # el hueco entre las dos reglas del pie
        for j in range(len(pie) - 2, max(-1, len(pie) - 6 - alto), -1):
            if _es_regla(pie[j].strip()):
                t = texto(" ".join(l.strip() for l in pie[j + 1:-1]))
                return {"texto": t, "bloque": t}, donde[j]
    r = _caja_entre_reglas(plano)
    if r and donde and r[0] >= donde[0]:
        t = texto(" ".join(plano[k].strip() for k in range(r[0] + 1, r[1]) if plano[k].strip()))
        return {"texto": t, "bloque": t}, r[0]
    return None


PIE_BARRAS = 2              # bajo la caja de Hermes, su barra de estado (uno o dos renglones)
REGLA_ANCHA = 0.75          # una regla «de lado a lado»: al menos esta parte de la regla más ancha de la pantalla


def _caja_entre_reglas(plano):
    """F1 (E2E v4): con un texto largo, la caja de Hermes ya no enseña su «❯»: el principio se corrió dentro de ella y
    solo quedan sus últimos renglones, entre las dos reglas del pie. Esa caja es lo que hay entre las DOS ÚLTIMAS reglas
    cuando las dos van de lado a lado (las de tus mensajes y sus respuestas, en Hermes, miden 40 columnas; se comparan
    con la regla más ancha: sin cortes de renglón, un párrafo es más ancho que la pantalla) y debajo solo queda su barra
    de estado: a lo más PIE_BARRAS renglones de barra, sin prompt (en Kiro trabajando, debajo está su «›» y entre sus
    reglas, la conversación). → (i, j): los índices de las dos reglas en `plano`, o None."""
    idx = [k for k, l in enumerate(plano) if l.strip()]
    reglas = [k for k in idx if _es_regla(plano[k].strip())]
    if len(reglas) < 2:
        return None
    ancho = max(len(plano[k].strip()) for k in reglas)
    abajo, arriba = reglas[-1], reglas[-2]
    pie = [k for k in idx if k > abajo]
    if len(pie) > PIE_BARRAS or any(not es_barra(plano[k].strip()) or _CAJA_PROMPT_RE.match(plano[k]) for k in pie):
        return None
    if abajo - arriba < 2 or min(len(plano[abajo].strip()), len(plano[arriba].strip())) < REGLA_ANCHA * ancho:
        return None
    return arriba, abajo


def dialogo_al_pie(pantalla, abajo=12):
    """¿En sus últimos `abajo` renglones hay un menú o un diálogo del motor (actualizar, confiar en la carpeta, sí/no),
    aunque no traiga opciones numeradas? Ahí no se teclea nada. Solo cuenta de su caja de chat para abajo (si se ve una):
    lo de arriba es la conversación. F7 (E2E v4): un mensaje tuyo viejo en la pantalla de Copilot citaba el «enter
    select · esc back» del menú de Codex, su caja vacía no se reconocía y la cola decía «te pregunta algo»."""
    plano = _plano(pantalla)
    while plano and not plano[-1].strip():
        plano.pop()
    hallada = _caja(plano, abajo, 0) if plano else None
    return _pista_al_pie(plano, abajo, hallada[1] if hallada else -1)


def _pista_al_pie(plano, abajo, desde):
    """¿Una pista de menú o un diálogo en los últimos `abajo` renglones con algo, del índice `desde` para abajo?"""
    return any(k >= desde and (_PISTA_MENU_RE.search(plano[k]) or _DIALOGO_RE.search(plano[k]))
               for k in [k for k, l in enumerate(plano) if l.strip()][-abajo:])


def al_pie(pantalla, n=3):
    """Los últimos `n` renglones con algo de su pantalla, sin bordes ni reglas: lo que la página enseña cuando no ve su
    caja de chat («al pie de su pantalla se ve…»)."""
    lineas = [_sin_bordes(l).strip() for l in _plano(pantalla) if l.strip() and not _es_regla(l.strip())]
    return [l for l in lineas if l][-n:]


def lectura(pantalla):
    """Lo que la pantalla dice de la pestaña, más allá del estado de herdr (que no reconoce
    a todos los motores y a veces dice «idle» trabajando o «done» con un menú abierto):
    {"menu": bool, "trabajando": bool, "firma": str}. `firma` cambia si cambia lo visible."""
    plano = "\n".join(_plano(pantalla)).rstrip("\n")
    menu = pregunta_de(plano) is not None
    return {"menu": menu, "trabajando": (not menu) and trabajando_en_pantalla(plano),
            "firma": hashlib.sha1(plano.encode("utf-8", "replace")).hexdigest()[:16]}


# ═══════════════════════════════════════════════════════════════════════════
# Preguntas: una lista de opciones al pie, con una marcada
# ═══════════════════════════════════════════════════════════════════════════

_OPCION_RE = re.compile(r"^(\s*)([❯›>▶➤●◉→]?)(\s*)(\d{1,2})[.)]\s+(\S.*?)\s*$")
_OPCION_SIN_NUM_RE = re.compile(r"^(\s*)([❯›>▶➤→])(\s+)(\S.*?)\s*$")
_PISTA_RE = re.compile(r"(Enter to|Esc to|↑/↓|↑↓|to navigate|to select|to confirm|to cancel|to close|Tab to"
                       r"|enter submit|esc dismiss|Press enter)", re.I)
# la pista de un MENÚ (moverse y elegir), no la de cualquier pie
_PISTA_MENU_RE = re.compile(r"↑\s*/?\s*↓|to navigate|to select|enter (?:to )?(?:select|submit|confirm)|Press enter to confirm",
                            re.I)
_PREGUNTA_PERMISO_RE = re.compile(r"requires approval|approval|permission|permiso|allow\b", re.I)
# N2: un permiso por el avance de una skill (comando de Workspace o su herramienta): la página lo dice así, con
# Permitir y No (las opciones de su menú que dicen sí y no; si no se ven las dos, la pregunta va tal cual)
_AVANCE_RE = re.compile(r"\bworkspace(?:\.cmd)?\s+pasos\b|\bpasos\.py\b|\breportar_avance\b")
_OPCION_SI_RE = re.compile(r"\s*(?:yes\b|allow\b|run\b|approve|accept|proceed|s[ií]\b|permitir)", re.I)
_OPCION_NO_RE = re.compile(r"\s*(?:no\b|deny\b|reject|skip\b|cancel|rechaz|denegar)", re.I)
# H12: tras «Skip & tell the agent what to do instead», Cursor abre otra entrada que espera tu texto
_PIDE_TEXTO_RE = re.compile(r"^\s*[→›>❯]\s*(\S.*?)\s*\(Enter to send, empty to skip, Esc to cancel\)", re.I)


def _es_pie(ln):
    """Lo que hay DEBAJO de un menú y no es parte de él: pistas de teclas, separadores,
    la barra de Workspace, el pie del motor, la caja de entrada vacía («? ❯», «>»)."""
    s = ln.strip()
    if not s:
        return True
    if _es_regla(s) or _PISTA_RE.search(s) or es_barra(s) or _WS_LANZA_RE.search(s):
        return True
    if re.match(r"^(?:\S{1,3}\s+)?[❯›>]\s*$", s):
        return True
    return bool(_RUIDO_COMUN_RE.search(s) or _CODEX_RUIDO_RE.search(s) or _CLAUDE_RUIDO_RE.search(s)
                or _linea_trabajando(ln))


def _sin_panel_lateral(lineas):
    """Los renglones sin el panel de la DERECHA de su pantalla. N2 (prueba de punta a punta v3, 17-nov): Claude Code
    con su panel de archivos cambiados abierto. Cada renglón traía «│<lo del panel>» en la misma columna, y su
    permiso («Do you want to proceed?») no se reconocía: la página enseñó la tarjeta genérica.
    Es panel si un «│» cae en la misma columna (lejos de la izquierda) en el 80 % de los renglones con texto, y a su
    derecha hay texto en varios: el borde derecho de una caja de diálogo no tiene nada después. Un carácter ancho
    a la izquierda corre el «│» una o dos posiciones; se corta igual. Si no hay panel, los renglones tal cual."""
    llenas = [l for l in lineas if l.strip()]
    cuenta = {}
    for l in llenas:
        for i in range(40, len(l)):
            if l[i] == "│":
                cuenta[i] = cuenta.get(i, 0) + 1
    col = max(cuenta, key=cuenta.get, default=None)
    if col is None or len(llenas) < 6 or cuenta[col] < 0.8 * len(llenas) \
            or sum(1 for l in llenas if l[col + 1:].strip()) < 3:
        return lineas
    out = []
    for l in lineas:
        p = l.rfind("│", 0, col + 1)
        out.append(l[:p].rstrip() if p >= col - 2 else l)
    return out


def _cabe(previa, siguiente, ancho):
    """¿La primera palabra de `siguiente` cabía en el renglón de `previa`? Si no cabía, el
    motor partió el renglón por el ancho (es continuación); si cabía, es otro renglón."""
    palabra = (siguiente.strip().split() or [""])[0]
    return len(previa) + 1 + len(palabra) <= ancho


def pregunta_de(pantalla):
    """La pregunta que el motor espera que contestes, de lo que se ve en su terminal:
    {"texto", "detalle", "opciones": [{"n", "texto"[, "desc"]}], "sel"} o None.

    Cuenta una lista de opciones AL FINAL de la pantalla (debajo solo puede haber pistas
    de teclas, separadores, barras y la caja de entrada vacía):
      · numeradas con UNA marcada (❯ › > →), como Claude Code, Codex, Copilot, Hermes;
      · numeradas sin marca de texto (OpenCode marca la elegida solo con color): solo si
        debajo está la pista del menú (↑↓ select · enter submit); `sel` es None;
      · sin número, con una marcada y las demás alineadas con ella (Kiro «❯ Allow once»,
        Cursor «→ Run (once) (y)»): solo con la pista del menú debajo o la pregunta arriba.
    Una lista numerada en la respuesta del agente no tiene nada de eso: no es pregunta.
    `n` es el número de la opción (o su lugar, si no trae número). La descripción de una
    opción (el renglón de abajo que no es continuación) va en `desc`."""
    crudas = str(pantalla or "").replace("\r", "").split("\n")
    while crudas and not _ANSI_RE.sub("", crudas[-1]).strip():
        crudas.pop()                               # el final vacío no cuenta (ni para _corte)
    crudas = crudas[-45:]
    planas = _sin_panel_lateral([_ANSI_RE.sub("", l).rstrip() for l in crudas])
    borde = [bool(re.match(r"^\s*[│┃║]", l)) for l in planas]
    lineas = [_sin_bordes(l) for l in planas]
    if not lineas:
        return None
    pide = next((m for m in (_PIDE_TEXTO_RE.match(l) for l in [x for x in lineas if x.strip()][-3:]) if m), None)
    if pide:                                       # H12: Cursor te pide un texto (tras «Skip & tell the agent…»)
        return {"texto": pide.group(1), "detalle": "", "sel": 1, "opciones": [
            {"n": 1, "texto": "Seguir sin eso", "desc": "Enter vacío: que siga sin hacerlo", "teclas": ["enter"]},
            {"n": 2, "texto": "Cancelar", "desc": "Esc", "teclas": ["esc"]}]}
    ancho = max(60, max(len(l) for l in lineas))
    i = len(lineas) - 1
    pista_menu = False
    while i >= 0 and _es_pie(lineas[i]):
        if _PISTA_MENU_RE.search(lineas[i]):
            pista_menu = True
        i -= 1
    if i < 0:
        return None
    r = _opciones_numeradas(lineas, i, ancho, pista_menu) or _opciones_sin_numero(lineas, i, pista_menu)
    if not r:
        return None
    ops, sel, tope = r
    return _arma_pregunta(lineas, borde, planas, ops, sel, tope)


def _opciones_numeradas(lineas, i, ancho, pista_menu):
    """Sube desde `i` juntando «N. texto»; entre opciones puede haber vacíos, separadores
    («4. Chat about this» de Claude Code va bajo un «────»), la continuación de una opción
    larga o su descripción. → (opciones, sel, índice sobre la primera) o None."""
    ops, pend, fin, tope = [], [], i, i
    while i >= 0:
        ln = lineas[i]
        m = _OPCION_RE.match(ln)
        if m:
            col = len(m.group(1)) + len(m.group(2)) + len(m.group(3)) + len(m.group(4)) + 2
            texto, desc, previa = m.group(5), [], ln
            pend.reverse()
            for p in pend:
                if _sangria(p) < col - 1:
                    return _cierra_numeradas(ops, tope, fin, pista_menu)
                if not desc and not _cabe(previa, p, ancho):
                    texto += " " + p.strip()          # el renglón no cabía: es la misma opción
                    previa = p
                else:
                    desc.append(p.strip())
            ops.append((int(m.group(4)), texto, bool(m.group(2)), " ".join(desc)))
            pend = []
            i -= 1
            tope = i
            continue
        s = ln.strip()
        if not s or _es_regla(s):
            i -= 1
            continue
        if len(pend) < 4 and _sangria(ln) >= 2 and not _PISTA_RE.search(ln):
            pend.append(ln)
            i -= 1
            continue
        break
    return _cierra_numeradas(ops, tope, fin, pista_menu)


def _cierra_numeradas(ops, tope, fin, pista_menu):
    ops = list(reversed(ops))
    if len(ops) < 2 or [o[0] for o in ops] != list(range(1, len(ops) + 1)) or fin - tope > 40:
        return None
    marcadas = sum(o[2] for o in ops)
    if marcadas == 1:
        sel = next(o[0] for o in ops if o[2])
    elif marcadas == 0 and pista_menu:
        sel = None                                  # la elegida va solo en color (OpenCode)
    else:
        return None
    return [{"n": o[0], "texto": o[1], "desc": o[3]} for o in ops], sel, tope


def _opciones_sin_numero(lineas, i, pista_menu):
    """«❯ Allow once / Deny once / …» (Kiro), «→ Run (once) (y) / Add Shell(ls)… (tab)» (Cursor):
    un bloque al pie con UNA marcada y las demás alineadas con su texto."""
    j = i
    while j >= 0 and lineas[j].strip() and not _es_regla(lineas[j].strip()):
        j -= 1
    bloque = list(range(j + 1, i + 1))
    marcadas = [k for k in bloque if _OPCION_SIN_NUM_RE.match(lineas[k])]
    if len(marcadas) != 1:
        return None
    k = marcadas[0]
    m = _OPCION_SIN_NUM_RE.match(lineas[k])
    col = len(m.group(1)) + len(m.group(2)) + len(m.group(3))
    arriba = k
    while arriba - 1 > j and _sangria(lineas[arriba - 1]) == col and not _OPCION_SIN_NUM_RE.match(lineas[arriba - 1]):
        arriba -= 1
    abajo = k
    while abajo + 1 <= i and _sangria(lineas[abajo + 1]) == col:
        abajo += 1
    if abajo != i:
        return None                                 # debajo de las opciones hay otra cosa: no es un menú
    textos = [m.group(4) if x == k else lineas[x].strip() for x in range(arriba, abajo + 1)]
    if len(textos) < 2 or any(len(t) > 90 for t in textos):
        return None
    # la pregunta, pegada encima de las opciones (en el mismo bloque, sin renglón vacío en medio)
    pregunta = any(lineas[x].strip().endswith("?") or _PREGUNTA_PERMISO_RE.search(lineas[x])
                   for x in range(max(j + 1, arriba - 3), arriba))
    if not (pista_menu or pregunta):
        return None                                 # un borrador de varios renglones en la caja no es un menú
    ops = [{"n": x + 1, "texto": t, "desc": ""} for x, t in enumerate(textos)]
    return ops, k - arriba + 1, arriba - 1


def _arma_pregunta(lineas, borde, planas, ops, sel, tope):
    """La pregunta y su detalle (lo de arriba de las opciones, hasta el borde del diálogo)."""
    i, arriba, idx, limite = tope, [], [], None
    en_caja = 0 <= tope + 1 < len(borde) and borde[tope + 1]
    while i >= 0 and len(arriba) < 14:
        crudo = planas[i].strip()
        if crudo.startswith(("╭", "┌", "╔")) or (_es_regla(lineas[i].strip()) and not borde[i]) \
                or (en_caja and not borde[i]):
            limite = i                              # el borde de arriba del diálogo
            break
        t = lineas[i].strip().strip("─━╭╮╰╯ ").strip()
        if t and not _es_caja(t, 0.5) and not _PISTA_RE.search(t):
            arriba.append(re.sub(r"^[▸•●◆*-]\s+", "", t))
            idx.append(i)
        i -= 1
    arriba.reverse()
    idx.reverse()
    # la pregunta es el renglón con «?» más cercano a las opciones, que EMPIEZA una pregunta
    # (mayúscula o «¿»); «Reason: …?» o «Motivo: …?» son detalle, no la pregunta
    k = max((j for j, t in enumerate(arriba) if t.rstrip().endswith("?") and (t[:1].isupper() or t.startswith("¿"))
             and not re.match(r"^\w+:\s", t)), default=-1)
    if k < 0:                                       # sin «?»: el permiso («… requires approval»)
        k = max((j for j, t in enumerate(arriba) if _PREGUNTA_PERMISO_RE.search(t)), default=-1)
    if k >= 0:
        texto, detalle = arriba[k], arriba[k + 1:] or arriba[max(0, k - 3):k]
        inicio = idx[k]
    else:
        texto, detalle = (arriba[-1] if arriba else ""), arriba[-4:-1]
        inicio = idx[-4] if len(idx) >= 4 else (idx[0] if idx else tope + 1)
    if limite is not None:
        inicio = limite
        t = lineas[limite - 1].strip() if limite >= 1 and _es_regla(lineas[limite].strip()) else ""
        if t and len(t) <= 30 and not re.search(r"[.:;?!)]$", t) and (limite < 2 or not lineas[limite - 2].strip()):
            inicio = limite - 1                     # el título del diálogo sobre su borde («Command»)
    # dentro de una caja («┃» de OpenCode, «│» de Copilot/Hermes): el diálogo empieza con la caja
    o = tope + 1
    if 0 <= o < len(borde) and borde[o]:
        b = o
        while b - 1 >= 0 and (borde[b - 1] or planas[b - 1].strip().startswith(("╭", "┌", "╔"))):
            b -= 1
        inicio = min(inicio, b)
    out = {"texto": _sin_secretos(texto)[:300], "detalle": _sin_secretos(" · ".join(detalle))[:400],
           "opciones": [], "sel": sel, "_corte": len(lineas) - inicio}
    for o in ops[:9]:
        d = {"n": o["n"], "texto": _sin_secretos(o["texto"])[:200]}
        if o.get("desc"):
            d["desc"] = _sin_secretos(o["desc"])[:200]
        out["opciones"].append(d)
    # solo el diálogo (de su borde de arriba al pie) y su detalle: la instrucción de la skill, más arriba, no cuenta
    if _AVANCE_RE.search(" ".join([texto] + detalle + lineas[inicio:])):
        si = next((o["n"] for o in out["opciones"] if _OPCION_SI_RE.match(o["texto"])), None)
        no = next((o["n"] for o in out["opciones"] if _OPCION_NO_RE.match(o["texto"])), None)
        if si and no:
            out.update(comando="avance", permitir=si, negar=no)
    return out


def _sin_pregunta(pantalla):
    """La pantalla sin el diálogo de la pregunta (opciones, pistas): eso no es conversación."""
    p = pregunta_de(pantalla)
    if not p:
        return pantalla
    ls = str(pantalla).replace("\r", "").split("\n")
    while ls and not _ANSI_RE.sub("", ls[-1]).strip():
        ls.pop()                                   # pregunta_de mira las últimas 45 sin contar el final vacío
    return "\n".join(ls[:max(0, len(ls) - p["_corte"])])


# ── la opción elegida cuando solo se ve por el color (OpenCode) ──
_SGR_RE = re.compile(r"\x1b\[([0-9;]*)m")


def _colores(ln):
    """[(carácter, color de letra)] de un renglón con colores SGR."""
    out, color, pos = [], "", 0
    for m in re.finditer(r"\x1b\[[0-9;?]*[ -/]*[@-~]", ln):
        for c in ln[pos:m.start()]:
            out.append((c, color))
        pos = m.end()
        sg = _SGR_RE.fullmatch(m.group(0))
        if sg:
            codigos = (sg.group(1) or "0").split(";")
            j = 0
            while j < len(codigos):
                c = codigos[j]
                if c in ("0", "", "39"):
                    color = ""
                elif c in ("38",) and j + 1 < len(codigos):
                    largo = 5 if codigos[j + 1] == "2" else 3
                    color = ";".join(codigos[j:j + largo])
                    j += largo - 1
                elif c in ("48",) and j + 1 < len(codigos):
                    j += (4 if codigos[j + 1] == "2" else 2)
                elif c.isdigit() and (30 <= int(c) <= 37 or 90 <= int(c) <= 97):
                    color = c
                j += 1
    for c in ln[pos:]:
        out.append((c, color))
    return out


def seleccion_por_color(ansi, pregunta):
    """La opción elegida de `pregunta` (de pregunta_de) en un menú que la marca SOLO con
    color: la única cuyo número (o primera letra) tiene un color distinto al de las demás.
    → su `n`, o None si no se puede saber."""
    if not pregunta or not ansi:
        return None
    filas = [_colores(l) for l in str(ansi).replace("\r", "").split("\n")]
    planas = ["".join(c for c, _ in f) for f in filas]
    colores = {}
    for o in pregunta.get("opciones") or []:
        cab = re.compile(r"^\s*(?:[│┃║]\s*)?[❯›>▶➤●◉→]?\s*%s[.)]\s+%s" % (o["n"], re.escape(o["texto"][:20])))
        cab2 = re.compile(r"^\s*(?:[│┃║]\s*)?\s*%s" % re.escape(o["texto"][:20]))
        for f, p in zip(reversed(filas), reversed(planas)):
            m = cab.match(p) or cab2.match(p)
            if m:
                k = len(p) - len(p.lstrip())
                while k < len(p) and p[k] in "│┃║ ":
                    k += 1
                colores[o["n"]] = f[k][1] if k < len(f) else ""
                break
    if len(colores) < 2:
        return None
    cuenta = {}
    for c in colores.values():
        cuenta[c] = cuenta.get(c, 0) + 1
    unicos = [n for n, c in colores.items() if cuenta[c] == 1]
    return unicos[0] if len(unicos) == 1 and len(cuenta) == 2 else None


# ═══════════════════════════════════════════════════════════════════════════
# Subagentes vivos
# ═══════════════════════════════════════════════════════════════════════════

_TIEMPO = r"((?:\d+h\s*)?(?:\d+m\s*)?\d+s)"
# Claude Code, al pie: «◯ general-purpose  Sleep 25 test agent 1    5s · ↓ 43.3k tokens»
_SUB_LINEA_RE = re.compile(r"^\s*[○◌◯◉●⏺•]\s+(?!main\b)([\w.-]{2,40})\s{2,}(.+?)\s{2,}" + _TIEMPO +
                           r"(?:\s*·\s*[↓↑]?\s*([\d.,]+\s*[kKmM]?\s*tokens))?\s*$")
# Codex, en la conversación: «• Started `/root/prueba_uno`» … «• Completed `/root/prueba_uno`»
_SUB_CODEX_RE = re.compile(r"^\s*[•●⏺]?\s*(Started|Spawned|Completed|Finished|Closed)\s+`?(/root/[\w./-]+|agent\s+[\w.-]+)`?\s*$")
# OpenCode: «⠴ General Subagent — Prueba subagente 1» (el spinner: sigue corriendo; «✓»: terminó)
_SUB_OC_RE = re.compile(r"^\s*([⠀-⣿✓✔])\s+(\w[\w-]*)\s+Subagent\s+[—–-]\s+(.+?)\s*$")
# Antigravity, al pie: «● Agent(research: Subagente de prueba 2) · Gemini 4 Argon  Working · 5s»
_SUB_AGY_RE = re.compile(r"^\s*[●○◯◉]\s+Agent\(([\w-]+):\s*(.+?)\)\s*(?:·\s*.+?)?\s{2,}\S.*?\s*·\s*" + _TIEMPO + r"\s*$")
# Hermes, bajo «Subagents · 2 live»: «● Responde solamente con … · 1s · running»
_SUB_ESTADO_RE = re.compile(r"^\s*[●○◯◉]\s+(.+?)\s+·\s+" + _TIEMPO + r"\s+·\s+(?:running|working|queued|starting|pending)\s*$",
                            re.I)
_SUB_ESPERA_RE = re.compile(r"(?:Waiting for|Esperando a|Running)\s+(\d+)\s+(?:background\s+)?"
                            r"(?:agents?|subagentes?|agentes?|subagents?)\b|\bSubagents · (\d+) live\b", re.I)


def _es_linea_sub(ln):
    return bool(_SUB_LINEA_RE.match(ln) or _SUB_AGY_RE.match(ln) or _SUB_ESTADO_RE.match(ln))


def subagentes_de(pantalla):
    """Los ayudantes que el motor tiene corriendo, de lo que muestra su pantalla:
    {"lista": [{"tipo", "tarea", "tiempo", "tokens"}], "esperando": n} o None."""
    todas = _plano(pantalla)
    lineas = todas[-60:]
    lista, esperando = [], 0
    vivos = []                                     # Codex: los que arrancaron y aún no terminan
    for ln in todas:
        m = _SUB_CODEX_RE.match(ln)
        if m:
            nombre = m.group(2).split("/")[-1]
            if m.group(1) in ("Started", "Spawned"):
                if nombre not in vivos:
                    vivos.append(nombre)
            elif nombre in vivos:
                vivos.remove(nombre)
    for nombre in vivos:
        lista.append({"tipo": "subagente", "tarea": _recorta(nombre.replace("_", " "), 160), "tiempo": "", "tokens": ""})
    for k, ln in enumerate(lineas):
        m = _SUB_LINEA_RE.match(ln)
        if m:
            lista.append({"tipo": _recorta(m.group(1), 40), "tarea": _sin_secretos(m.group(2).strip())[:160],
                          "tiempo": _recorta(m.group(3).strip(), 16), "tokens": _recorta((m.group(4) or "").strip(), 24)})
            continue
        m = _SUB_AGY_RE.match(ln)
        if m:
            lista.append({"tipo": _recorta(m.group(1), 40), "tarea": _sin_secretos(m.group(2).strip())[:160],
                          "tiempo": _recorta(m.group(3), 16), "tokens": ""})
            continue
        m = _SUB_ESTADO_RE.match(ln)
        if m:
            lista.append({"tipo": "subagente", "tarea": _sin_secretos(m.group(1).strip())[:160],
                          "tiempo": _recorta(m.group(2), 16), "tokens": ""})
            continue
        m = _SUB_OC_RE.match(ln)
        if m and m.group(1) not in "✓✔":
            lista.append({"tipo": _recorta(m.group(2), 40), "tarea": _sin_secretos(m.group(3).strip())[:160],
                          "tiempo": "", "tokens": ""})
            continue
        e = _SUB_ESPERA_RE.search(ln)
        if e and not _espera_vieja(lineas, k):
            esperando = int(e.group(1) or e.group(2))
    if not lista and not esperando:
        return None
    return {"lista": lista[:12], "esperando": max(esperando, len(lista))}


def _espera_vieja(lineas, k):
    """«Waiting for 2 background agents» que ya quedó en la historia: después de él (antes del
    separador de la caja de entrada) el motor escribió otro mensaje a la columna 0."""
    for ln in lineas[k + 1:]:
        s = ln.strip()
        if s and _es_regla(s):
            return False
        if re.match(r"^[⏺•●❯›>]\s", ln):
            return True
    return False


# ═══════════════════════════════════════════════════════════════════════════
# Límites y gasto: lo que cada motor ya muestra al pie
# ═══════════════════════════════════════════════════════════════════════════

_USO_PCT = [  # (clave, regex, ¿el número es «lo que queda»?)
    ("contexto", re.compile(r"(?:contexto|context)\s*\[[^\]]*\]\s*(\d{1,3})\s*%", re.I), False),
    ("sesion", re.compile(r"(?:uso sesión|session use|uso sesion)\s*\[[^\]]*\]\s*(\d{1,3})\s*%", re.I), False),
    ("semana", re.compile(r"(?:uso semanal|weekly use)\s*\[[^\]]*\]\s*(\d{1,3})\s*%", re.I), False),
    ("contexto", re.compile(r"\bContext (\d{1,3})% left", re.I), True),
    ("sesion", re.compile(r"\b5h (\d{1,3})% left", re.I), True),
    ("semana", re.compile(r"\bweekly (\d{1,3})% left", re.I), True),
    ("contexto", re.compile(r"\b(?:contexto|context) (\d{1,3})%(?! left)", re.I), False),
    ("contexto", re.compile(r"[\d.,]+\s*[KkMm]?\s*\((\d{1,3})%\)"), False),
]
_USO_REINICIA_RE = re.compile(r"(?:se reinicia en|resets? in)\s+((?:\d+[dhm]\s*){1,3})", re.I)
_USO_GASTO_RE = re.compile(r"\$(\d+(?:\.\d{1,2})?)(?:\s+spent)?")
_USO_CREDITOS_RE = re.compile(r"(\d[\d.,]*)\s+(créditos IA|AI credits|solicitudes premium|premium requests)", re.I)


def uso_de(pantalla):
    """Contexto, ventana de 5 h, semana (en % USADO), cuándo se reinicia y gasto, de lo que el
    motor muestra al pie. Solo lo que aparece; {} si nada."""
    texto = _ANSI_RE.sub("", str(pantalla or ""))
    out = {}
    for k, rx, queda in _USO_PCT:
        if k in out:
            continue
        m = rx.search(texto)
        if m:
            v = max(0, min(100, int(m.group(1))))
            out[k] = 100 - v if queda else v
    m = _USO_REINICIA_RE.search(texto)
    if m:
        out["reinicia"] = _recorta(" ".join(m.group(1).split()), 16)
    m = _USO_GASTO_RE.search(texto)
    if m:
        out["gasto"] = "$" + m.group(1)
    m = _USO_CREDITOS_RE.search(texto)
    if m:
        out["creditos"] = _recorta(m.group(1) + " " + m.group(2), 40)
    return out


# ═══════════════════════════════════════════════════════════════════════════
# La conversación desde la pantalla
# ═══════════════════════════════════════════════════════════════════════════

_PROMPT_RE = re.compile(r"^\s*(?:[›❯>]|→)\s+(.+)$")
# «workspace ❯ Turn these notes…», «☤ ❯ type to redirect…»: la caja de entrada con su texto de ejemplo
_PROMPT_PREFIJO_RE = re.compile(r"^\s*[^\s›❯>→]{1,12}\s+[›❯](?:\s|$)")
_PROMPT_SOLO_RE = re.compile(r"^\s*(?:\S{1,3}\s+)?[›❯>→]\s*$")
_PROMPT_PEGADO_RE = re.compile(r"^›(?=\S)")      # la caja de Kiro con algo escrito: «›Prueba de mensaje…» (N3)
_HORA_RE = re.compile(r"\s{2,}\d{1,2}:\d{2}(?:\s?[ap]\.?\s?m\.?)?\s*$", re.I)     # «… un bloque   17:01» (Copilot)
# «(ctrl+o to expand)», «(⌃t to expand)», «(↓ to manage)», «(shift+tab to cycle)»: pistas de teclas
_PISTA_TECLA_RE = re.compile(r"\s*\([^()]*\bto (?:expand|collapse|manage|view|cycle|interrupt|cancel|select|navigate)\b[^()]*\)",
                             re.I)
_VERBOS = r"Ran|Read|Write|Edit|Bash|Search|Grep|Glob|Explored|Called|Edited|Wrote|List|Shell|Tool|WebFetch|WebSearch"
# verbos que en una frase son comunes («Running the tests…»): solo cuentan con la viñeta o el ícono del motor
_VERBOS_CON_MARCA = r"Running|Searched|Fetch|Spawned|Spawning|Exited|Update|Clarify|Delegate"
_MARCA_HERR = r"(?:[•●⏺◆✔✗⋯○↓]\s*|[^\w\s\-*+#>]{1,2}\s+)"
_HERR_RE = re.compile(r"^\s*(?:%s?(%s)|%s(%s)|(%s)(?=\())\b(?:\((.*)\)|[ :,]\s*(.*))?\s*$"     # o «Fetch(…)» a media vuelta
                      % (_MARCA_HERR, _VERBOS, _MARCA_HERR, _VERBOS_CON_MARCA, _VERBOS_CON_MARCA))
# «$ ls -1 "…" 14s» (Cursor), «💻 $ ls -1 + 1 command  0.3s» (Hermes): un comando de la terminal
_CMD_RE = re.compile(r"^\s*(?:💻\s*)?\$\s+(\S.*?)(?:\s+(?:\d+m\s?)?[\d.]+m?s|\s+Waiting for approval\.*)?\s*$")
# «    workspace-memoria decidir» (Cursor): una herramienta de un servidor MCP
_MCP_RE = re.compile(r"^\s{4,}([a-z][\w]*(?:-[\w]+)+)\s+([a-z][\w]*)\s*$")
# el razonamiento resumido («Thought for 1s…», «▸ Thought for 9s, 249 tokens», «+ Thought · 16ms»)
_PENSAR_RE = re.compile(r"^\s*(?:[•●○▸+]\s*)?Thought(?:\s+for\s+[\d.]+\s*m?\s*[\d.]*s?\b|\s+·|\s*$)")

# el logo y la barra de Claude Code (y la de Workspace debajo de su caja)
_CLAUDE_RUIDO_RE = re.compile(
    r"(^\s*[▐▛▜▝▘▗▖█▀▄▌]{2,}|Claude Code v\d|with (low|medium|high|xhigh|max) effort|^\s*(contexto|uso sesión|uso semanal|context|session use|weekly use)\s*\["
    r"|◆ \w+\s+·|dato tras el 1er|se reinicia en|^\s*activa \d|auto mode on|shift\+tab to cycle|^\s*[❯>]\s*Try \"|\? for shortcuts"
    r"|^\s*⏵⏵|bypass permissions|accept edits on|plan mode on|^\s*[●⏺]\s+main\s*$|Waiting for \d+ background agent|^\s*─{3,}|^\s*[❯>›]\s*$"
    r"|^\s*[✻✳✶✢✽]\s+\S+ for \d|^\s*(?:[⏺●]\s+)?Agent \"[^\"]*\" (?:is waiting|finished|completed|failed)\b.*·)")
# la cabecera, el aviso de actualización, los tiempos y el texto de ejemplo de la caja de Codex
_CODEX_RUIDO_RE = re.compile(
    r"(Update available!|codex/install\.sh|See full release notes|openai/codex/releases|^\s*>_ OpenAI Codex"
    r"|^\s*(model|directory|approval|sandbox|session):\s|Worked for \d+[smh]|^\s*\+ Show details|^\s*~/"
    r"|^\s*(Ask Codex to do anything|Explain this codebase|Summarize recent commits|Implement \{feature\}"
    r"|Find and fix a bug in @filename|Write tests for @filename|Improve documentation in @filename"
    r"|Run /review on my current changes|Use /skills to list available skills)\s*$"
    r"|f2 to view|\[Pasted Content \d+ chars\]|← for agents|^\s*[+…]\s*\d+ (?:\w+ ){0,2}(?:lines?|items?)\b|\(\^?[⌃^]t to expand\)"
    r"|^\s*(?:└\s*)?Tip: |New activity · |Back to bottom|^\s*pasos: |^\s*✔ You approved \w+ to run"
    r"|^\s*[•●]?\s*(?:Waiting for agents|Finished waiting)\s*$)")
# F1 (E2E): líneas de estado y del arranque que salían como mensajes del agente (textos del informe): la barra de
# esfuerzo de Claude Code, su «Update installed», el aviso y el «Resumed session» de Hermes, el banner de Workspace
# al abrir un motor («… · OpenCode · modelo de tu config») y «Calling 1 MCP tool» de Antigravity
_ESTADO_RUIDO_RE = re.compile(
    r"^\s*◉\s+\S+\s+·\s+/effort|Update installed\s*·\s*/restart|^\s*⚠\s*update available\s*$|^\s*↻\s+Resumed session\b"
    r"|·\s*(?:modelo de tu config|auto \(cuenta [^)]*\))\s*$|^\s*Calling \d+ MCP tools?\b", re.I)
_RUIDO_COMUN_RE = re.compile(
    r"esc to interrupt|esc interrupt|ctrl\+c to stop|\? for shortcuts|shift\+tab|auto mode|context left|% left\b"
    r"|/help for commands|Try \"|uso semanal|uso sesión|^\s*contexto\s*\[|^\s*NO_REPLY\s*$"
    r"|^\s*(?:[✦•]\s*)?Tip: |^\s*Press (?:ctrl|⌃|shift|alt|f\d)\S* to ")
# lo propio de cada motor (cabeceras, pies, avisos), donde no hay una pista de forma
_RUIDO_MOTOR = {
    "kiro": re.compile(r"^\s*▸ (?:Credits:|What's new)|Welcome to Kiro|Learn more: https://kiro\.|kiro-cli --v2"
                       r"|Initializing\b|\bmessages? queued\b|/sessions to resume|/copy to clipboard"),
    "antigravity": re.compile(r"Antigravity CLI \d|\(Google AI Pro\)|^\s*accept-edits · |Accept-edits mode:"),
    "hermes": re.compile(r"^\s*☤\s+\S+\s*$|^\s*─ (?:\d+m\s?)?[\d.]+m?s\b.*·|Welcome to Hermes Agent|^\s*✦ Tip:"),
    "openclaw": re.compile(r"openclaw tui - ws://|^\s*ws-[0-9a-f]{8,}\s*$|^\s*session agent:|^\s*connected \| \w+"
                           r"|^\s*agent \S+ \(\S+\) \| session|^\s*tokens [\d.]+k?/[\d.]+[km]\b|Model route changed:"
                           r"|running • \d+[smh]? \| connected"),
    "cursor": re.compile(r"^\s*Cursor Agent\s*$|^\s*v\d{4}\.\d+\.\d+-[0-9a-f]+\s*$|^\s*\d+ tasks?\s*$"),
    "copilot": re.compile(r"^\s*\S+(?:\s\S+)?(?:\s{3,}\S+(?:\s\S+)?){3,}\s*$|Discover Copilot|^\s*● (?:Disabled tools:|MCP Servers reloaded:)"
                          r"|AIC used\s*$"),
}
# un ruido cuyos renglones de abajo (sangrados, o «╰ …») también lo son
_RUIDO_CON_HIJOS_RE = re.compile(r"^\s*▸ What's new|^\s*(?:[✦•]\s*)?(?:└\s*)?Tip: |^\s*[•●]?\s*(?:Waiting for agents|Finished waiting)\s*$")
_LANZADOS_RE = re.compile(r"^\s*(?:[⏺●•]\s+)?\d+ (?:background )?(?:agents?|subagents?) launched\b")
_ESTILO_YO = {"kiro": "separador", "cursor": "caja", "openclaw": "caja"}
_VIÑETA_RE = re.compile(r"^\s*(?:[•●⏺◆▸○◯◈✓✗✔⎿└├│╰$>→›❯↳↩🔀💻🧠⠀-⣿]|\d+[.)]\s|[-*+]\s|```)")


def _es_ruido(ln, motor):
    """(¿es ruido?, ¿sus renglones de abajo también?) para un renglón ya sin bordes."""
    s = ln.strip()
    if not s:
        return False, False
    if _PENSAR_RE.match(ln):
        return True, True
    if _RUIDO_CON_HIJOS_RE.search(ln):
        return True, True
    if _WS_LANZA_RE.search(ln) or es_barra(s) or _linea_trabajando(ln) or _ARTE_BRAILLE_RE.match(ln):
        return True, False
    if _RUIDO_COMUN_RE.search(ln) or _ESTADO_RUIDO_RE.search(ln) or _CLAUDE_RUIDO_RE.search(ln) or _CODEX_RUIDO_RE.search(ln) \
            or _CODEX_RUIDO_RE.search(re.sub(r"^\s*[›❯>]\s+", "", ln)) or _es_linea_sub(ln):
        return True, False
    rx = _RUIDO_MOTOR.get(motor)
    if rx is not None and rx.search(ln):
        return True, False
    if _PROMPT_PREFIJO_RE.match(ln):
        return True, False                         # la caja de entrada con su texto de ejemplo
    sin_pista = _PISTA_TECLA_RE.sub("", ln)
    if sin_pista != ln and (not sin_pista.strip() or _PROMPT_RE.match(sin_pista)):
        return True, False                         # «› Message from @x (ctrl+o to expand)»: un aviso del motor
    return False, False


def _marca_preambulo(L, ruido):
    """Lo que Workspace imprime ANTES del motor (el banner del cerebro, su lema, los avisos):
    renglones del principio que son dibujo, vacíos, avisos o el lema centrado."""
    for i, ln in enumerate(L):
        s = ln.strip()
        if not s or _es_caja(s, 0.5) or _WS_LANZA_RE.search(ln) or _WS_AVISO_RE.match(ln) \
                or (_sangria(ln) >= 6 and " · " in s):
            ruido[i] = True
            continue
        break


def _marca_cajas(L, ruido):
    """Una caja completa (de «╭» a «╰», pegada a la izquierda) es un banner, un aviso o un
    diálogo del motor (bienvenida, actualización, herramientas disponibles): no es conversación."""
    i = 0
    while i < len(L):
        s = L[i]
        if re.match(r"^\s{0,1}[╭┌]", s):
            col = s.index(s.strip()[0])
            for j in range(i + 1, min(len(L), i + 80)):
                if re.match(r"^\s*[╰└]", L[j]) and L[j].index(L[j].strip()[0]) == col and _es_caja(L[j].strip()):
                    for k in range(i, j + 1):
                        ruido[k] = True
                    i = j
                    break
        i += 1


def _marca_caja_entrada(L, ruido):
    """La caja de entrada: el ÚLTIMO renglón con prompt (y sus continuaciones) cuando debajo solo
    hay ruido. Su texto es el de ejemplo («Ask Codex to do anything», «Add a follow-up») o un
    borrador sin mandar: ninguno es un mensaje tuyo."""
    ultimo = None
    for i, ln in enumerate(L):
        if not ruido[i] and (_PROMPT_RE.match(ln) or _PROMPT_SOLO_RE.match(ln) or _PROMPT_PEGADO_RE.match(ln)):
            ultimo = i
    if ultimo is None:
        return
    j = ultimo + 1
    while j < len(L) and not ruido[j] and L[j].strip() and _sangria(L[j]) > _sangria(L[ultimo]):
        j += 1
    # debajo de la caja siempre hay algo del motor (su pie, un separador); si no hay nada, ese
    # renglón es tu último mensaje (p. ej. con el diálogo de una pregunta ya recortado). H10: salvo que sea su
    # texto de ejemplo («ask a question or describe a task ↵» de Kiro es su último renglón cuando no enseña su pista)
    # o lo escrito en la caja de Kiro, pegado a su «›» (N3: tus mensajes de Kiro nunca llevan «›»)
    debajo = [k for k in range(j, len(L)) if L[k].strip()]
    m = _PROMPT_RE.match(L[ultimo])
    ejemplo = bool(m) and bool(_CAJA_EJEMPLO_RE.match(" ".join(m.group(1).split())))
    if ejemplo or _PROMPT_PEGADO_RE.match(L[ultimo]) or (debajo and all(ruido[k] for k in debajo)):
        for k in range(ultimo, j):
            ruido[k] = True


def _plano_yo(ln):
    """¿Puede ser un renglón de un mensaje tuyo sin marca? Texto corrido, sin viñeta, sin
    herramienta, sin lista ni código."""
    return not (_VIÑETA_RE.match(ln) or _HERR_RE.match(ln) or _CMD_RE.match(ln) or _PROMPT_RE.match(ln))


def _yo_por_separador(L, ruido):
    """Kiro: tu mensaje va sin prompt, sangrado 2, justo debajo de un separador «────»."""
    out = {}
    for i, ln in enumerate(L):
        if not (ln.strip() and _es_caja(ln.strip()) and len(ln.strip()) >= 20):
            continue
        j, run = i + 1, []
        while j < len(L) and not ruido[j] and re.match(r"^  \S", L[j]) and _plano_yo(L[j]):
            run.append(j)
            j += 1
        if run:
            out[run[0]] = run
    return out


_NOTA_INI = "[Workspace · contexto]"      # la nota que la página antepone a tu mensaje (localhost_web._CTX_INI)


def _yo_por_caja(L, ruido, mios=()):
    """Cursor y OpenClaw: tu mensaje va en una caja de color (en texto plano, un párrafo
    aislado por dos renglones vacíos arriba y abajo). Los bloques así alternan: tu mensaje,
    la respuesta, tu mensaje… Un bloque es tuyo si es UN párrafo de texto corrido con la
    misma sangría y el anterior no fue tuyo.
    H11 (E2E v2): un mensaje tuyo que no pasaba la regla (la nota «[Workspace · contexto] …», o un renglón partido
    que empieza con «- K6-GRIS») corría la alternancia desde ahí: tus mensajes salían como suyos y sus respuestas
    como tuyas. La nota sí empieza un mensaje tuyo, y lo que la página le tecleó (`mios`) es tuyo siempre: ancla la
    alternancia (el de hasta arriba puede venir cortado: basta su cola)."""
    conocidos = {re.sub(r"\s+", "", m) for m in mios or () if m and m.strip()}
    segs, cur, corrida, maxima = [], [], 0, 0
    for i, ln in enumerate(L):
        if ruido[i]:
            maxima, corrida = max(maxima, corrida), 0
            continue
        if not ln.strip():
            corrida += 1
            continue
        maxima = max(maxima, corrida)
        if cur and maxima >= 2:
            segs.append(cur)
            cur = []
        elif cur and maxima == 1:
            cur.append(None)
        cur.append(i)
        corrida = maxima = 0
    if cur:
        segs.append(cur)
    out, previo_yo = {}, False
    for n, seg in enumerate(segs):
        plano = re.sub(r"\s+", "", "".join(L[k] for k in seg if k is not None))
        conocido = bool(plano) and any(c == plano or (n == 0 and len(plano) >= 16 and c.endswith(plano))
                                       for c in conocidos)
        yo = conocido or (None not in seg and _plano_yo(L[seg[0]])
                          and (re.match(r"^\s*[\w¿¡«\"'(]", L[seg[0]]) or L[seg[0]].lstrip().startswith(_NOTA_INI))
                          and all(_sangria(L[k]) == _sangria(L[seg[0]]) and _plano_yo(L[k]) for k in seg)
                          and not previo_yo)
        if yo:
            out[seg[0]] = seg
        previo_yo = bool(yo)
    return out


def _herr_de(h):
    """«Ran (ls -1 …)» / «Fetch(https://…)» / «Read, globbed 13 files» → {"n", "d"}."""
    d = (h.group(4) if h.group(4) is not None else (h.group(5) or "")).strip()
    if d.startswith("(") and d.endswith(")") and d.count("(") == 1:
        d = d[1:-1].strip()
    d = re.sub(r"\s{2,}(?:\d+m\s?)?[\d.]+m?s$", "", d).lstrip(",: ")         # «…  0.1s»: el tiempo que tardó
    if d == "Call":
        d = ""                                     # «• Tool Call» (Kiro)
    return {"n": _recorta(h.group(1) or h.group(2) or h.group(3), 40), "d": _limpio(d, 160)}


def _grupo(herr):
    """«Explored», «Read 2 files», «Read, globbed 13 files»: un grupo cuyos renglones de abajo
    son herramientas, no salida."""
    return not herr["d"] or bool(re.match(r"^(?:\d|globbed\b)", herr["d"]))


def _de_pantalla(texto, motor, mios=()):
    """Lo que muestra la terminal → turnos aproximados: tus mensajes (con el prompt del
    motor, o como cada motor los separa) y lo demás como respuesta del agente, con sus
    herramientas; sin bordes, barras, pies, cajas de entrada ni líneas de Workspace.
    `mios`: los textos que la página le tecleó a ese panel (anclan tus mensajes donde la pantalla no los marca)."""
    if motor == "opencode":
        return _de_pantalla_opencode(texto)
    L = [_sin_bordes(_ANSI_RE.sub("", l)) for l in str(texto or "").replace("\r", "").split("\n")]
    ruido, hijos = [False] * len(L), [False] * len(L)
    _marca_preambulo(L, ruido)
    _marca_cajas(L, ruido)
    for i, ln in enumerate(L):
        if not ruido[i]:
            ruido[i], hijos[i] = _es_ruido(ln, motor)
    _marca_caja_entrada(L, ruido)
    caja = _caja_entre_reglas(L)
    if caja:                       # F1: la caja de Hermes con un texto largo, ya sin su «❯»: no es una respuesta en curso
        for k in range(caja[0] + 1, caja[1]):
            ruido[k] = True
    for i in range(1, len(L)):
        if ruido[i - 1] and not ruido[i] and _sangria(L[i]) >= 60 and len(L[i].strip()) <= 40:
            ruido[i] = True        # el final de un pie alineado a la derecha que el ancho partió («~/Desktop/DOC -» / «BRAIN»)
    estilo = _ESTILO_YO.get(motor)
    yo_ini = (_yo_por_separador(L, ruido) if estilo == "separador"
              else _yo_por_caja(L, ruido, mios) if estilo == "caja" else {})
    yo_resto = {k for run in yo_ini.values() for k in run[1:] if k is not None}
    tecleados = {re.sub(r"\s+", "", m): " ".join(m.split()) for m in mios or () if m and m.strip()}

    turnos, actual = [], None
    en_yo = en_ruido = False
    herr_col, herr_grupo, herr_cab = None, False, None    # la herramienta cuya salida se está saltando

    def empuja(rol, linea=None, herr=None, nuevo=False):
        nonlocal actual
        if nuevo or actual is None or actual["rol"] != rol:
            actual = {"rol": rol, "texto": "", "ts": "", "herr": []}
            turnos.append(actual)
        if linea is not None:
            actual["texto"] += linea + "\n"
        if herr:
            actual["herr"].append(herr)
    for i, ln in enumerate(L):
        s = ln.strip()
        if not s:
            en_yo = en_ruido = False
            herr_col = None
            if actual is not None:
                actual["texto"] += "\n"
            continue
        if i in yo_ini:
            empuja("yo", " ".join(L[k].strip() for k in yo_ini[i] if k is not None), nuevo=True)
            en_yo, herr_col = False, None
            continue
        if i in yo_resto:
            continue
        if _es_regla(s):
            en_yo = en_ruido = False
            herr_col = None
            continue
        if ruido[i]:
            en_ruido = en_ruido or hijos[i]
            continue
        if en_ruido and (_sangria(ln) > 0 or s[0] in "╰└⎿" or s[0].islower()) and not _VIÑETA_RE.match(ln.lstrip("╰└⎿ ")):
            continue                               # lo de abajo de un ruido (el razonamiento, una pista partida)
        en_ruido = False
        ln = _PISTA_TECLA_RE.sub("", ln).rstrip()
        s = ln.strip()
        # la salida de una herramienta: lo sangrado (o con └ ⎿ ╰) bajo ella, hasta un vacío o una viñeta
        if herr_col is not None:
            hijo = re.sub(r"^\s*[└├⎿╰]\s*", "", ln)
            sub = _HERR_RE.match(hijo)
            if herr_grupo and sub and _sangria(ln) >= herr_col:
                if actual and actual["herr"] and actual["herr"][-1] is herr_cab and not herr_cab["d"]:
                    actual["herr"].pop()           # «Explored» sin detalle: lo dicen sus herramientas
                empuja("agente", herr=_herr_de(sub))
                continue
            if _sangria(ln) > herr_col or (s[0] in "└├⎿╰│" and _sangria(ln) >= herr_col):
                continue
            herr_col = None
        # tu mensaje largo sigue en renglones sangrados bajo el «›»/«>» (hasta un vacío o una viñeta)
        if en_yo and actual is not None and actual["rol"] == "yo" and re.match(r"^\s+\S", ln) \
                and not re.match(r"^\s*[•●⏺◆✔✗⋯└├]", ln):
            actual["texto"] = actual["texto"].rstrip("\n") + " " + s + "\n"
            continue
        # N4: o partido sin sangría a media palabra (Hermes): sigue siendo tuyo mientras arme lo que la página le tecleó
        if en_yo and actual is not None and actual["rol"] == "yo" and tecleados:
            junto = re.sub(r"\s+", "", actual["texto"] + s)
            k = next((c for c in tecleados if c.startswith(junto)), None)
            if k is not None:
                actual["texto"] = (tecleados[k] if k == junto else actual["texto"].rstrip("\n") + " " + s) + "\n"
                continue
        en_yo = False
        m = _PROMPT_RE.match(ln)
        if m and len(m.group(1).strip()) > 1:
            empuja("yo", _HORA_RE.sub("", m.group(1)).strip())
            en_yo = True
            continue
        sc = _SUB_CODEX_RE.match(ln)
        if sc:
            nombre = sc.group(2).split("/")[-1].replace("_", " ")
            if sc.group(1) in ("Started", "Spawned"):
                empuja("agente", herr={"n": "Agent", "d": _limpio(nombre, 160), "sub": True, "tipo": "subagente"})
            continue
        if _LANZADOS_RE.match(ln):                  # «2 background agents launched» y debajo, cada uno
            j = i + 1
            while j < len(L) and re.match(r"^\s*[├└]\s*\S", L[j]):
                empuja("agente", herr={"n": "Agent", "d": _limpio(re.sub(r"^\s*[├└]\s*", "", L[j]), 160), "sub": True,
                                       "tipo": "subagente"})
                ruido[j] = True
                j += 1
            continue
        ln2 = re.sub(r"^(\s*)[└├⎿]\s*", r"\1", ln)       # «└ Read X», «⎿ $ ls»: el detalle de una herramienta
        h = _HERR_RE.match(ln2)
        c = _CMD_RE.match(ln2)
        mc = _MCP_RE.match(ln2)
        if h or c or mc:
            herr = _herr_de(h) if h else ({"n": "Bash", "d": _limpio(c.group(1), 160)} if c
                                          else {"n": _recorta(mc.group(1), 40), "d": _limpio(mc.group(2), 160)})
            empuja("agente", herr=herr)
            herr_col, herr_grupo, herr_cab = _sangria(ln2), bool(h) and _grupo(herr), herr
            continue
        empuja("agente", re.sub(r"^\s*[•●⏺]\s+|^(\s*)⎿\s+", r"\1", ln))
    return _cierra_turnos(turnos)


def _cierra_turnos(turnos):
    """Texto final de cada turno: sin vacíos de más, sin un párrafo repetido justo debajo de sí
    mismo (Hermes redibuja su respuesta al cambiar de ancho y la pantalla guarda las copias),
    sin llaves; fuera los turnos vacíos."""
    out = []
    for t in turnos:
        parrafos = []
        for p in re.split(r"\n{2,}", t["texto"].strip("\n")):
            if not parrafos or p.strip() != parrafos[-1].strip():
                parrafos.append(p)
        t["texto"] = _sin_secretos("\n\n".join(parrafos).strip())[:12000]
        if t["texto"] or t["herr"]:
            out.append(t)
    return out[-MAX_TURNOS:]


# ── OpenCode: pantalla completa, bloques con «┃» a la izquierda y barra lateral a la derecha ──
_OC_RUIDO_RE = re.compile(r"(^\s*\+ Thought\b|Build ·|^\s*\(\d+ earlier lines\)|^\s*Exited with code \d+|ctrl\+p commands"
                          r"|^\s*[\d,.]+K? tokens\b|\$\d+\.\d\d(\s+spent)?\s*$|^\s*esc interrupt|^\s*Context\s*$"
                          r"|^\s*Press ctrl\+\w to |^\s*[⠀-⣿]\s+Writing command)")
_OC_EXPLORA_RE = re.compile(r"^\s*→\s*(\w[\w ]*?)(?::\s*|\s+)(.*)$")
_OC_LATERAL_RE = re.compile(r"^(?:[\d,.]+K? tokens|\d+% used|\$\d+\.\d\d spent|Context|LSP|MCP|Modified Files|Todo)$")
_OC_COL_LATERAL = 80       # la barra lateral de OpenCode empieza a la derecha de esta columna


def _sin_lateral_oc(ln):
    """Quita lo que la barra lateral de OpenCode pega al final del renglón (tokens,
    % usado, gasto, título de la sesión). → (renglón limpio, ¿traía barra lateral?)."""
    m = re.match(r"^(.*?)(\s{4,})(\S(?:(?!\s{4,}).)*)$", ln)      # el ÚLTIMO hueco ancho
    if not m:
        return ln, False
    principal, cola = m.group(1), m.group(3)
    inicio = len(m.group(1)) + len(m.group(2))
    vacio = not principal.strip(" ┃")
    if _OC_LATERAL_RE.match(cola) or (vacio and inicio >= _OC_COL_LATERAL):
        return principal.rstrip(), True
    return ln, False


def _de_pantalla_opencode(texto):
    """OpenCode pinta bloques con «┃» a la izquierda, cada uno con un renglón vacío arriba:
      · si empieza con «$ » (o con el spinner de un comando que corre) es una herramienta
        (se resume; su salida no se muestra);
      · si empieza con «# » es el resultado de una herramienta (la pregunta ya contestada);
      · el bloque pegado al «╹» de abajo es la caja de entrada; el de hasta arriba sin su
        renglón vacío quedó cortado por la pantalla (no se sabe qué era);
      · si no, es lo que escribió el socio.
    Lo demás (sangrado, sin «┃») es la respuesta; «Thought», «Build ·» y similares son ruido.
    Los renglones que el ancho partió se juntan; los que cabían enteros (código) no."""
    filas = [_sin_lateral_oc(_ANSI_RE.sub("", ln).rstrip()) for ln in str(texto or "").replace("\r", "").split("\n")]
    filas = [ln for ln, lateral in filas if not (lateral and not ln.strip(" ┃"))]
    ancho = max([60] + [len(ln) for ln in filas if ln.strip() and not re.match(r"^\s*[┃╹]", ln)])
    turnos, actual = [], None
    previa = None              # el último renglón de texto de la respuesta (para juntar los partidos)

    def turno(rol, nuevo=False):
        nonlocal actual
        if nuevo or actual is None or actual["rol"] != rol:
            actual = {"rol": rol, "texto": "", "ts": "", "herr": []}
            turnos.append(actual)
        return actual
    bloques, k = [], 0
    while k < len(filas):                          # los bloques «┃» y lo de fuera, en orden
        m = re.match(r"^\s*┃\s?(.*)$", filas[k])
        if not m:
            bloques.append(("fuera", filas[k], k))
            k += 1
            continue
        ini, cuerpo = k, []
        while k < len(filas) and re.match(r"^\s*┃", filas[k]):
            cuerpo.append(re.match(r"^\s*┃\s?(.*)$", filas[k]).group(1).strip())
            k += 1
        # cortado: hasta arriba, sin su renglón vacío de arriba pero con el de abajo (la forma de un
        # bloque de OpenCode al que la pantalla le comió la cabeza)
        arriba = ini == 0 or (ini == 1 and not filas[0].strip())
        cortado = arriba and cuerpo[:1] != [""] and cuerpo[-1:] == [""]
        entrada = k < len(filas) and filas[k].strip().startswith("╹")
        bloques.append(("bloque", (cuerpo, cortado, entrada), ini))
    for tipo, dato, _ in bloques:
        if tipo == "bloque":
            previa = None
            cuerpo, cortado, entrada = dato
            utiles = [c for c in cuerpo if c and not _OC_RUIDO_RE.search(c)]
            if not utiles or cortado or entrada:
                continue
            primero = utiles[0]
            if primero.startswith("$ "):
                turno("agente")["herr"].append({"n": "Bash", "d": _limpio(primero[2:].strip(), 160)})
            elif re.match(r"^[⠀-⣿]\s+\S", primero):
                turno("agente")["herr"].append({"n": "Bash", "d": _limpio(primero[1:].strip(), 160)})
            elif primero.startswith("# "):
                turno("agente")["herr"].append({"n": _recorta(primero[2:].strip(), 40),
                                                "d": _limpio(" · ".join(utiles[1:]), 160)})
            else:
                turno("yo", nuevo=True)["texto"] = " ".join(utiles) + "\n"
            continue
        ln = dato
        if not ln.strip():
            previa = None
            if actual is not None and actual["rol"] == "agente":
                actual["texto"] += "\n"
            continue
        if _OC_RUIDO_RE.search(ln) or ln.strip().startswith(("╹", "╻")) or _es_caja(ln.strip(), 0.5) \
                or _linea_trabajando(ln) or _ESTADO_RUIDO_RE.search(ln):                     # «⠋ Thinking»: un spinner no es un turno (F1/F2)
            previa = None
            continue
        sa = _SUB_OC_RE.match(ln)
        if sa:
            turno("agente")["herr"].append({"n": "Agent", "d": _limpio(sa.group(3), 160), "sub": True,
                                            "tipo": _recorta(sa.group(2), 40)})
            previa = None
            continue
        e = _OC_EXPLORA_RE.match(ln)
        if e:
            turno("agente")["herr"].append({"n": _recorta(e.group(1).strip(), 40), "d": _limpio(e.group(2).strip(), 160)})
            previa = None
            continue
        t = turno("agente")
        if previa is not None and not _cabe(previa, ln, ancho) and not re.match(r"^\s*(?:[-*•]|\d+[.)])\s", ln):
            t["texto"] = t["texto"].rstrip("\n") + " " + ln.strip() + "\n"     # el ancho partió el renglón
        else:
            t["texto"] += ln.strip() + "\n"
        previa = ln
    return _cierra_turnos(turnos)


def _sin_arranques(turnos):
    """Quita los mensajes de arranque que manda Workspace («Inicia el cerebro.», «Lee BRAIN.md…»):
    no son lo que pidió el socio. Lo que el agente contesta a ese arranque (hasta tu siguiente
    mensaje) queda marcado `arranque`: la página lo enseña como «Listo con X», no como un mensaje.
    Tampoco son tuyos los comandos que teclea un botón de modelo o esfuerzo («/model sonnet», §6), ni lo que su
    motor contesta a ellos hasta tu siguiente mensaje (en los motores que se leen de pantalla)."""
    import ajustes_motor
    try:
        import memoria
        prefijos = tuple(memoria._ARRANQUES) + (memoria._SEMILLA,)
    except Exception:
        prefijos = ("Lee BRAIN.md", "Inicia el cerebro")
    out, tras, ajuste = [], False, False
    for t in turnos:
        if t.get("rol") == "yo":
            ajuste = ajustes_motor.es_comando(t.get("texto"))
            tras = not ajuste and str(t.get("texto") or "").lstrip().startswith(prefijos)
            if tras or ajuste:
                continue
        elif ajuste:
            continue
        elif str(t.get("texto") or "").lstrip().startswith(prefijos):
            tras = True                         # el prompt de arranque leído de pantalla como si fuera del agente (F11)
            continue
        elif tras:
            t = dict(t, arranque=True)
        out.append(t)
    return out


# ── errores del motor (sin crédito, límite del plan, sesión vencida, saturado, sin red) ─────────────
# Solo frases que los motores pintan cuando algo FALLA, y solo en las últimas líneas de la pantalla: una
# conversación que habla de «rate limits» no es un error. Lo más específico primero.
_ERRORES = (
    ("login", re.compile(r"(please run /login|run /login|not logged in|oauth token has expired|"
                         r"authentication[_ ]error|unauthorized|please log ?in|"
                         r"session (?:has )?expired|login required|inicia sesi[oó]n)", re.I)),
    # W1 (17-nov): la llave de un PROVEEDOR vencida o inválida (Hermes con OpenRouter: «❌ OpenRouter rejected
    # the request… HTTP 401: API key expired»). Después de «login»: «Invalid API key · Please run /login» de
    # Claude Code se arregla con /login. Con una marca de falla ANTES en el renglón (401, error, rejected,
    # failed, ❌, ✗) o el código del proveedor (invalid_api_key): un agente que HABLA de llaves no es un error.
    ("llave", re.compile(r"((?:\b401\b|\berror\b|rejected|failed|❌|✗).*?"
                         r"(?:api[ _-]?key (?:has |was )?(?:expired|revoked|invalid)|"
                         r"api[ _-]?key is (?:invalid|expired|revoked)|"
                         r"(?:invalid|incorrect|expired|revoked)[ _-]api[ _-]?key)"
                         r"|\b(?:invalid|incorrect)_api_key\b)", re.I)),
    ("creditos", re.compile(r"(credit balance is too low|insufficient (?:credits|balance|funds)|"
                            r"quota exceeded|exceeded your (?:current |monthly )?quota|billing (?:details|hard limit)|"   # «monthly»: Copilot (F10)
                            r"out of credits|no credits? (?:left|remaining)|payment required|"
                            r"exceeded your (?:monthly )?premium requests|sin cr[eé]ditos?)", re.I)),
    ("limite", re.compile(r"(usage limit reached|hit your (?:usage )?limits?|limit reached|"
                          r"reached (?:your|the) (?:usage |weekly |5-hour )?limit|resource_exhausted|"
                          r"l[ií]mite de uso)", re.I)),
    ("sobrecarga", re.compile(r"(overloaded_error|overloaded|api error: 5\d\d|internal server error|"
                              r"service unavailable|bad gateway)", re.I)),
    ("velocidad", re.compile(r"(429 too many requests|too many requests|rate[_ ]limit(?:ed| exceeded| error))", re.I)),
    ("red", re.compile(r"(connection error|network error|econnrefused|enotfound|etimedout|"
                       r"request timed out|stream error|failed to connect|unable to connect)", re.I)),
)
ERROR_LINEAS = 14


def error_de(pantalla):
    """{"tipo", "texto"} del error que el motor muestra al final de su pantalla; None si no hay."""
    lineas = [x.strip() for x in _ANSI_RE.sub("", str(pantalla or "")).replace("\r", "").split("\n")]
    lineas = [x for x in lineas if x][-ERROR_LINEAS:]
    for tipo, rx in _ERRORES:
        for x in reversed(lineas):
            m = rx.search(x)
            if m:
                return {"tipo": tipo, "texto": _recorta(x.strip(" │|>⎿•-*"), 200)}
    return None
