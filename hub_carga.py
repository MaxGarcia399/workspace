#!/usr/bin/env python3
r"""WORKSPACE · hub_carga — las pantallas de paso al cliente oficial con la piel H-1 y el monito M-1 (la versión de
Zenith). SOLO PARA PROBAR: vive en la rama zenith/hub-h1 y nunca entra a main.

Del hub de prueba al motor pasan varias pantallas que eran del estilo de antes. Con la marca del hub de prueba
(WORKSPACE_HUB_S1=1, la misma de S-1; el hub de siempre no la pone) se ven así:
  · «Abriendo…» en el hub (la entrega): su monito grande, a quién y con qué programa, y Esc para cancelar;
  · «Cargando…» de dispatch y de los motores que preparan su pestaña (cargando.mostrar);
  · el letrero gigante del agente antes de su motor (engines: show_brain_banner y el de Claude Code);
  · «Abriendo «sesión»…» al salir de S-1 (y el renglón «— cargando…» del menú ya no sale);
  · el aviso cuando su motor se cierra solo al abrir: qué pasó y qué sigue, sin borrar lo que dijo el motor.
Todo es una tarjeta H-1 arriba de la pantalla: lo que se imprima después sale debajo (no tapa nada). Falla-suave:
jamás frena una apertura. Stdlib."""
import json
import os
import shutil
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)


def activo(env=None):
    """I11 · S-1 y sus pantallas de paso (la piel H-1) son las de siempre: también al escribir el comando del agente,
    sin el hub. Solo una copia de desarrollo con WORKSPACE_HUB_S1=0 enseña el menú de antes (para comparar)."""
    env = os.environ if env is None else env
    if str(env.get("WORKSPACE_HUB_S1") or "").strip() != "0":
        return True
    try:
        import puertas
        return not puertas.dev()
    except Exception:
        return True


def _agente(nombre=""):
    """El agente que se abre: su id de WORKSPACE_AGENT_NAME, su nombre de WORKSPACE_AGENT_UI; color y forma de la
    página (hub_s1.agente)."""
    aid = str(os.environ.get("WORKSPACE_AGENT_NAME") or "").strip()
    try:
        ctx = json.loads(os.environ.get("WORKSPACE_AGENT_UI") or "{}")
    except ValueError:
        ctx = {}
    try:
        import hub_s1
        return hub_s1.agente(aid or nombre, ctx.get("name") or nombre or aid)
    except Exception:
        return {"id": aid, "n": ctx.get("name") or nombre or aid or "Tu agente", "c": "#c9c9d1", "f": "bolita",
                "st": "libre"}


def _motor():
    try:
        import hub_s1
        return hub_s1.motor_texto()
    except Exception:
        return ""


def tarjeta(w, a, titulo, lineas=(), pie=None, tono="carga", alto_max=None, t=None):
    """La tarjeta H-1 (un Term de w × su alto): el monito M-1 a la izquierda, el título y sus líneas a la derecha y,
    abajo, `pie` [(tecla, qué)]. `tono`: «carga» (borde del agente a media fuerza) o «error» (ámbar)."""
    import hub_paleta as P
    import hub_bloque as B
    import hub_h1 as H
    import hub_monitos as MON
    C = P.C
    grande = (alto_max or 30) >= 24 and w >= 90
    tam = 16 if grande else 8
    mw, mh = MON.medidas(tam)
    cw = min(96, w - 4)
    texto_w = cw - mw - 10
    renglones = []
    for ln in lineas:
        segs_ = ln if isinstance(ln, list) else [(ln, C["tx2"], False)]
        import hub_directo as D
        renglones += D.envolver(segs_, texto_w) or [[]]
    alto = max(mh + 4, len(renglones) + 6) + (2 if pie else 0)
    T = P.Term(w, alto)
    T.fill(0, 0, w, alto, B.BG)
    x0 = (w - cw) // 2
    L = B.Lienzo(T, {})
    linea = P.mix(B.WARN, B.BG, 0.25) if tono == "error" else None
    H.area(L, x0, 0, cw, alto, B.P1, foco_a=a if tono != "error" else None, linea=linea)
    s = {"t": time.monotonic() if t is None else t, "anim": {}, "agentes": [a]}
    MON.dibujar(T, dict(a, st="libre"), x0 + 4, 2, tam, s=s, st="pregunta" if tono == "error" else "libre",
                signo=tono != "error")
    tx = x0 + mw + 7
    import hub_directo as D
    D._linea_corta(T, tx, 2, titulo, x0 + cw - 3)
    y = 4
    for r in renglones:
        D._linea(T, tx, y, r, x0 + cw - 3)
        y += 1
    if pie:
        xk = tx
        for k, lab in pie:
            if xk + B.W(k) + B.W(lab) + 4 > x0 + cw - 2:
                break
            xk = T.key(xk, alto - 2, k, lab)
    T.flat()
    return P.afinar(T)


def _pinta(T, out, limpiar=True, colores=None):
    """La tarjeta arriba de la pantalla (o donde va el cursor, sin limpiar) y el cursor debajo de ella."""
    import hub_paleta as P
    colores = colores or P._colores()
    filas = T.ansi(colores)
    s = ("\x1b[0m\x1b[2J\x1b[3J\x1b[H" if limpiar else "\r\n") + "\r\n".join(filas) + "\x1b[0m\r\n"
    out.write(s)
    out.flush()
    return len(s)


def mostrar(sub="", out=None, titulo=None, linea=None):
    """«Cargando…» (o lo que diga `titulo`) con la piel H-1: la tarjeta del agente arriba. → True si pintó."""
    out = out or sys.stdout
    if os.environ.get("WORKSPACE_NO_CARGA"):
        return False
    if os.environ.get("WORKSPACE_HUB_S1_AVISO_VISIBLE") == "1" and titulo is None:
        return True                                 # S-1 del hub ya dejó «Abriendo…» a la vista: nada encima
    try:
        if not out.isatty():
            return False
    except (AttributeError, ValueError):
        return False
    try:
        import hub_paleta as P
        C = P.C
        cols, rows = shutil.get_terminal_size((100, 30))
        a = _agente(sub.split(" · ")[0] if sub else "")
        motor = _motor()
        tit = titulo or [(a["n"], a["c"], True), ("  ·  " + motor if motor else "", C["tx3"], False)]
        lin = [linea or [("Cargando…", C["tx"], True)]]
        if sub and " · " in sub:
            lin.append([("«%s»" % sub.split(" · ", 1)[1], C["tx2"], False)])
        _pinta(tarjeta(cols, a, tit, lin, alto_max=rows), out)
        return True
    except Exception:
        return False


#: Los programas que tardan en pintar lo suyo (medido en esta Mac, 19-nov): lo dice la tarjeta mientras tanto.
LENTOS = {"Cursor": "Cursor tarda en abrir: hasta un minuto (lo de abajo se queda quieto mientras).",
          "OpenClaw": "OpenClaw enciende su gateway: la primera pestaña tarda unos segundos.",
          "Hermes": "Hermes tarda unos segundos en abrir."}


def abriendo(nombre_sesion="", out=None, motor=None, limpiar=True):
    """«Abriendo «sesión» en <Motor>…»: lo que se ve entre S-1 (o el letrero del agente) y su motor."""
    out = out or sys.stdout
    try:
        import hub_paleta as P
        C = P.C
        cols, rows = shutil.get_terminal_size((100, 30))
        a = _agente()
        motor = motor or _motor() or "su programa"
        tit = [(a["n"], a["c"], True), ("  ·  " + motor, C["tx3"], False)]
        lin = [[("Abriendo ", C["tx"], True), (("«%s»" % nombre_sesion) if nombre_sesion else "una sesión nueva",
                                               a["c"], True), (" en %s…" % motor, C["tx"], True)],
               [("Su programa oficial toma esta terminal en un momento; al salir de él vuelves al hub.",
                 C["tx3"], False)]]
        lento = next((v for k, v in LENTOS.items() if k.lower() in motor.lower()), "")
        if lento:                                   # los que tardan: que no parezca que «ni abre»
            lin.append([(lento, B_WARN(), False)])
        _pinta(tarjeta(cols, a, tit, lin, alto_max=rows), out, limpiar)
        return True
    except Exception:
        return False


def linea(texto, out=None):
    """Un aviso de una línea de la apertura (respaldo, usuarios, «encendiendo OpenClaw»…) debajo de la tarjeta, con
    los colores de H-1 (sin el «WORKSPACE:» de antes). → True si lo escribió."""
    out = out or sys.stdout
    try:
        import hub_paleta as P
        import hub_bloque as B
        t = " ".join(str(texto or "").split())
        for pre in ("WORKSPACE:", "WORKSPACE ·"):
            if t.startswith(pre):
                t = t[len(pre):].strip()
        if not t:
            return False
        cols = shutil.get_terminal_size((100, 30)).columns
        x0 = max(0, (cols - min(96, cols - 4)) // 2) + 3
        T = P.Term(cols, 1)
        T.fill(0, 0, cols, 1, B.BG)
        xx = T.put(x0, 0, "· ", P.C["tx3"], True)
        T.put(xx, 0, B.corto(t, cols - xx - 2), P.C["tx2"])
        out.write(T.ansi(P._colores())[0] + "\x1b[0m\r\n")
        out.flush()
        return True
    except Exception:
        return False


# ── lo que eligió en S-1 (para que el paso al motor diga qué abre) ────────────
def _ruta_eleccion():
    import paths                                   # la carpeta de estado sale solo de paths.state_dir()
    return os.path.join(paths.state_dir(), "hub", "s1-eleccion.json")


def anotar_eleccion(agente, nombre):
    try:
        r = _ruta_eleccion()
        os.makedirs(os.path.dirname(r), exist_ok=True)
        with open(r + ".tmp", "w", encoding="utf-8") as fh:
            json.dump({"agente": agente, "nombre": nombre, "t": time.time()}, fh)
        os.replace(r + ".tmp", r)
    except OSError:
        pass


def eleccion_reciente(agente=None, tope=90.0):
    """El nombre de la sesión que eligió en S-1 hace menos de `tope` s (del mismo agente), o None."""
    try:
        with open(_ruta_eleccion(), encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return None
    agente = agente or str(os.environ.get("WORKSPACE_AGENT_NAME") or "")
    if time.time() - float(d.get("t") or 0) > tope or (agente and d.get("agente") and d["agente"] != agente):
        return None
    return str(d.get("nombre") or "")


def letrero(out=None):
    """En lugar del letrero gigante del agente (antes o después de S-1): «Abriendo «sesión»…» si ya eligió, o
    «Cargando…». → True si pintó (entonces no va el letrero)."""
    if os.environ.get("WORKSPACE_HUB_S1_AVISO_VISIBLE") == "1":
        return True
    n = eleccion_reciente()
    return abriendo(n, out) if n is not None else mostrar("", out)


# ── el aviso del hub cuando su motor se cierra solo al abrir ──────────────────
#: Lo que se sabe de cada motor cuando se cierra al abrir: qué hacer.
SIGUIENTE = {
    "copilot": "Si dice «--assisted-approval is only supported…», actualiza Workspace (ya no lo pasa). Si pide "
               "sesión: `copilot login`.",
    "cursor": "Revisa que haya iniciado sesión: `cursor-agent login` (o ábrelo una vez a mano).",
    "codex": "Si pide revisar sus hooks, elige en su pantalla; si pide sesión: `codex login`.",
    "kiro": "Si pide sesión: `kiro-cli login`.",
    "opencode": "Revisa su proveedor: `opencode auth login`.",
    "hermes": "Revisa su configuración: `hermes setup`.",
    "openclaw": "La primera vez tarda en encender su gateway: vuelve a intentarlo en unos segundos.",
    "antigravity": "Revisa que haya iniciado sesión en Antigravity.",
    "claude-code": "Si pide sesión: `claude /login`.",
}


def fallo(a, motor_id, motor_n, rc, segundos, out=None):
    """La tarjeta del aviso (sin limpiar: lo que dijo el motor queda arriba) → la cadena que se escribió."""
    import hub_paleta as P
    C = P.C
    out = out or sys.stdout
    cols, rows = shutil.get_terminal_size((100, 30))
    tit = [("%s no se abrió en %s" % (a["n"], motor_n), C["tx"], True)]
    lin = [[("Su programa se cerró solo al abrir (código %s, a los %.1f s). Lo que dijo quedó arriba." %
             (rc, segundos), C["tx2"], False)],
           [("Qué sigue: ", B_WARN(), True), (SIGUIENTE.get(motor_id, "Revisa su motor en Motores y conexiones "
                                                                     "(↻ Verificar ahora)."), C["tx2"], False)]]
    T = tarjeta(cols, a, tit, lin, pie=[("Enter", "vuelve al hub")], tono="error", alto_max=rows)
    return _pinta(T, out, limpiar=False)


def B_WARN():
    import hub_bloque as B
    return B.WARN


def esperar_tecla(entrada=None, tope=600.0):
    """Espera Enter o Esc (o `tope` s) en la terminal, sin eco. Falla-suave."""
    try:
        import termios
        import tty
        import select
        fd = (entrada or sys.stdin).fileno()
        viejo = termios.tcgetattr(fd)
        tty.setcbreak(fd)
        try:
            fin = time.monotonic() + tope
            while time.monotonic() < fin:
                r, _w, _x = select.select([fd], [], [], 0.5)
                if r:
                    b = os.read(fd, 64)
                    if b"\r" in b or b"\n" in b or b"\x1b" in b or b"\x03" in b:
                        return True
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, viejo)
    except Exception:
        return False
    return False


# ── la entrega en el hub («Abriendo…», con Esc para cancelar) ─────────────────
def entrega(w, h, a, motor_n, aviso="", avance=0.0, t=None):
    """La pantalla del hub mientras entrega la terminal a su programa oficial: el fondo, y al centro la tarjeta del
    agente con «Abriendo su programa oficial…» y Esc para cancelar."""
    import hub_paleta as P
    import hub_bloque as B
    C = P.C
    T = P.Term(w, h)
    T.fill(0, 0, w, h, B.BG)
    if w < P.MIN_W or h < P.MIN_H:
        T.center(0, w, h // 2, "Abriendo…", C["tx2"])
        return P.afinar(T)
    tit = [(a["n"], a["c"], True), ("  ·  " + motor_n, C["tx3"], False)]
    puntos = "." * (1 + int(avance * 3) % 3)
    lin = [[("Abriendo su programa oficial" + puntos, C["tx"], True)],
           [("Ahí eliges con qué sesión seguir. Al salir de él vuelves aquí.", C["tx3"], False)]]
    if aviso:
        lin.append([(aviso, B.WARN, False)])
    k = tarjeta(w, a, tit, lin, pie=[("Esc", "cancela")], alto_max=h, t=t)
    y0 = max(1, (h - k.h) // 2)
    for y in range(k.h):
        for x in range(w):
            c = k.at(x, y)
            d = T.at(x, y0 + y)
            if d is not None and c is not None:
                d.ch, d.fg, d.bg, d.b = c.ch, c.fg, c.bg, c.b
    return P.afinar(T)
