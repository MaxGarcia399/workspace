#!/usr/bin/env python3
"""WORKSPACE · front — la puerta del harness.

`workspace` → banner rico de WORKSPACE (wordmark + emblema + panel del harness, dorado)
+ menú de AGENTES. Eliges uno → se lanza ese agente con SU banner y su flujo normal.
Escribir el agente directo (`zenith`) lo abre sin pasar por aquí.

Cero dependencias (stdlib, Python 3.9+). El menú interactivo va a /dev/tty
(Windows: msvcrt + stdout — ver runbooks/windows-support.md).
  --banner   imprime banner + menú estático y sale (no interactivo; para pruebas)
"""
import sys, os, json, subprocess, types
import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)
sys.dont_write_bytecode = True   # no generar __pycache__ (mantiene limpio el sync)
if os.name == "nt":
    os.system("")  # habilita ANSI en Windows 10+ (no-op en consolas viejas) — igual que doctor.py
import _utf8; _utf8.harden()  # B2 · UTF-8 en stdout/err (cp1252 reventaría con box-drawing)

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable or "python3"
DISPATCH = os.path.join(ROOT, "dispatch.py")
sys.path.insert(0, ROOT)
import dispatch  # noqa: E402  (registry merge: committeado + agentes cargados per-máquina)
# i18n (lado cliente): traduce las cadenas que ve el cliente. Falla-suave
# ABSOLUTA — sin el módulo, _t() devuelve el español inline (paridad exacta).
try:
    import i18n  # noqa: E402
except Exception:
    i18n = None


def _t(key, es, **kw):
    """Cadena traducida de `key`, con el español inline `es` como red de
    seguridad: sin i18n o con clave faltante → `es` (idéntico a hoy). Con
    **kw aplica .format(**kw) (falla-suave: si el format truena, cruda)."""
    if i18n is None:
        s = es
    else:
        try:
            v = i18n.t(key)
            s = v if v != key else es
        except Exception:
            s = es
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


def fg(n):
    return f"\033[38;5;{n}m"


# ── PALETA por TEMA (tuitheme.py): mismo concepto de tema que el web
#    (hubtheme.py) — env WORKSPACE_THEME > settings ui.theme > olympo.
#    Default olympo = la paleta dorada de SIEMPRE (paridad exacta: mismos
#    índices 256). Falla-suave ABSOLUTA: sin tuitheme → literales dorados. ──
try:
    import tuitheme
    TH = tuitheme.palette()
except Exception:
    TH = None
if TH:
    B, B2, C, WH = TH.B, TH.B2, TH.C, TH.WH
    DIM, DK, GREY = TH.DIM, TH.DK, TH.GREY
    R, BO, ERR = TH.R, TH.BO, TH.ERR
    OK = TH.OK
    # HERRAMIENTAS/DIOSES inactivos y radios del LATIDO: roles del tema
    # (en olympo: ámbar 136 y gris 238 — los de siempre).
    INACTIVE, INACTIVE_HB = TH.INACTIVE, TH.INACTIVE_HB
    GL = TH.GLYPHS
else:
    # paleta dorada (consistente con el banner)
    B = fg(214); B2 = fg(178); C = fg(221); WH = fg(230); DIM = fg(136); DK = fg(94); GREY = fg(242)
    R = "\033[0m"; BO = "\033[1m"
    ERR = fg(196)
    OK = fg(108)      # verde (paso/run verde en `workspace wf`) — mismo rol que config
    # HERRAMIENTAS y DIOSES: inactivos en ámbar tenue (136) — dorado apagado, no gris.
    # Mantiene la identidad dorada del recinto. Windows-safe: solo ANSI color, sin glifos.
    INACTIVE = fg(136)
    # LATIDO: modos no-seleccionados en gris (238) — contrasta con el radio-button activo.
    # El gris tiene sentido aquí porque hay un indicador de selección explícito (o)/( ).
    INACTIVE_HB = fg(238)
    GL = {"box": "╭╮╰╯│─", "pointer": "❯", "bracket_l": "❮", "bracket_r": "❯",
          "orn": "✦", "sep": "─", "base": "▁", "star_d": None, "star_h": None}
# glifos del tema (cursor/brackets/ornamento/separador) — olympo: los de siempre
GPTR, GBL, GBR = GL["pointer"], GL["bracket_l"], GL["bracket_r"]
GORN, GSEP = GL["orn"], GL["sep"]


def _set_term_title(txt):
    """Título de la ventana/pestaña de la terminal (OSC 0, estándar xterm —
    lo honran Terminal.app, iTerm2 y Windows Terminal). La pestaña decía
    «WORKSPACE — front.py» (lo que la terminal infiere del proceso/perfil);
    el hub se presenta WORKSPACE (rename 2026-10-02). Falla-suave total:
    sin tty o terminal rara → no pasa nada."""
    try:
        if sys.stdout.isatty():
            sys.stdout.write("\033]0;%s\007" % txt)
            sys.stdout.flush()
    except Exception:
        pass


def _read_json(p):
    try:
        return json.load(open(p, encoding="utf-8"))
    except Exception:
        return {}


# Agentes de SISTEMA: el filtro vive en el SSOT (dispatch.SYSTEM_AGENTS) para que
# TODA pantalla que liste agentes para el socio comparta la misma fuente. Alias
# local por legibilidad; consumidores nuevos usan `dispatch.visible_agents()`.
_SYSTEM_AGENTS = dispatch.SYSTEM_AGENTS


def registry():
    """Registry EFECTIVO: committeado + agentes CARGADOS per-máquina (merge de
    dispatch). Así el menú muestra los agentes cargados, no solo los del repo
    (que se distribuye vacío). Falla-suave → lectura directa del archivo.
    Los agentes de SISTEMA (_SYSTEM_AGENTS) se OCULTAN de todo lo que pinta
    el hub (altar, picker, info) — el registry real queda intacto."""
    try:
        reg = dispatch.load_registry()
    except Exception:
        reg = _read_json(os.path.join(ROOT, "agents", "registry.json"))
    try:
        ags = [a for a in (reg.get("agents") or [])
               if a.get("name") not in _SYSTEM_AGENTS]
        if len(ags) != len(reg.get("agents") or []):
            reg = dict(reg, agents=ags)
    except Exception:
        pass
    return reg


def agent_meta(d):
    return _read_json(os.path.join(ROOT, "agents", d, "agent.json"))


def _meta(entry):
    """Metadata (display/tagline/...) de una entrada del registry. Para un
    agente CARGADO la lee de su cerebro (<brain>/.workspace/agent.json); para uno
    committeado, de agents/<dir>/agent.json. Falla-suave → {}."""
    try:
        if entry.get("_loaded") or entry.get("brain"):
            return dispatch.load_agent_cfg(entry)
    except Exception:
        return {}
    return agent_meta(entry.get("dir", entry.get("name", "")))


def _has_dev_panel():
    """True si el dashboard de DEV está presente (dash/dev se excluye de la distro).
    Gate dev-only para la entrada «Dev» del hub: un cliente no tiene estos archivos."""
    return os.path.isfile(os.path.join(ROOT, "dashboard-dev.html"))


def _has_proyectos():
    """True si la app «Proyectos» viaja en este árbol (proyectos.py + su front).
    Mismo gate por-archivos que _has_dev_panel: la entrada del hub aparece solo
    si la app está — sacarla de una distro es borrar sus archivos, sin tocar el
    menú ni el ruteo."""
    return (os.path.isfile(os.path.join(ROOT, "proyectos-app.html"))
            and os.path.isfile(os.path.join(ROOT, "proyectos.py")))


def menu_entries():
    """Registro CANÓNICO del MENÚ del hub: [(token, etiqueta, tagline)] en el
    orden del recinto, gates incluidos (Dev solo dueño/dev). ÚNICA fuente:
    `_menu_machinery` arma sus opts de aquí, `items()` toma de aquí su
    porción del picker estático — una sección nueva del hub aparece SOLA en
    los dos lugares sin tocar nada más."""
    out = []
    # «GitHub» (token __ramas__, github_tui) quedó APARCADA fuera de la 0.2.0
    # (rama feat/github) mientras se rehace: sin entrada, sin tecla ni ruteo.
    # «Dev» (sección del hub, 2026-10-04): transparencia del proceso de
    # desarrollo — referencia de comandos + mapa del detrás (pipeline, repos,
    # qué sube, versión, estado). SOLO el dueño/dev: gate por-archivos (igual
    # que «Ramas») + dev_tui.is_dev() (canal main / marker per-máquina).
    # Falla-suave ABSOLUTA: sin dev_tui, el menú queda exactamente como antes.
    # «Comandos» (ex-«Dev», 2026-10-11): la referencia de comandos ES
    # producto — la ve todo el mundo. Los comandos de desarrollo solo
    # aparecen en modo dev (comandos_dev.py no viaja en la distribución).
    # El token __devmap__ se conserva (atajos y ruteo estables).
    out.append(("__devmap__", _t("menu.comandos.label", "Comandos"),
                _t("menu.comandos.tag", "lo que puedes escribir en la terminal")))
    # «Actualizaciones» (ex-«Doctor», renombre user-facing 2026-10-02): mismo
    # token __doctor__ y mismos comandos (workspace doctor/update) por debajo.
    out += [("__cal__", _t("menu.cal.label", "Calendario"),
             _t("menu.cal.tag",
                "tu agenda del día, editable a pantalla completa")),
            ("__tono__", _t("menu.tono.label", "Tono"),
             _t("menu.tono.tag",
                "los diales de personalidad de tus agentes")),
            # «Atajos» salió del hub (pedido del dueño 2026-10-14: «no sirve
            # tanto»): las cifras 1-9 siguen el orden de tus agentes. La
            # pantalla y su registro quedaron APARCADOS en la rama feat/atajos.
            ("__doctor__", _t("menu.updates.label", "Actualizaciones"),
             _t("menu.updates.tag", "revisar · reparar · actualizar")),
            # «Agentes» (2026-10-09): transparencia por agente — config,
            # cerebro real, skills, rutas y ciclo de vida (agents_tui).
            ("__motores__", _t("menu.engines.label", "Motores"),
             _t("menu.engines.tag", "estado, capacidades y conexiones")),
            ("__agentes__", _t("menu.agents.label", "Agentes"),
             _t("menu.agents.tag", "cerebro, permisos y skills de cada agente")),
            # «Agregar agente» vive DENTRO de Agentes (tecla a; sin agentes,
            # Agentes abre directo el formulario) — decisión del dueño
            # 2026-10-14. El token __add_agent__ sigue ruteando (loopback).
            # El control de IDIOMA ya NO vive en el MENÚ: es una entrada
            # propia del hub (Idioma › en el lanzador). Ver el grupo "idioma".
            ("__shell__", _t("menu.shell.label", "Terminal normal"),
             _t("menu.shell.tag", "tu shell de siempre · tecla q"))]
    return out


def items():
    """(name, display, tagline, selectable). Activos primero, planeados en gris."""
    reg = registry()
    out = []
    for a in reg.get("agents", []):
        m = _meta(a)
        out.append((a["name"], m.get("display", a["name"]), m.get("tagline", ""), True))
    for p in reg.get("planned", []):
        out.append((p, p.capitalize(), _t("hub.agent.soon_tag", "próximamente"),
                    False))
    # Chat: extraído a la rama feat/chat (se retoma a fondo después). El código
    # (chat_tui.py/chat.py/chat_daemon.py) ya no vive en main — fuera del hub.
    # La vieja pantalla «Config» (config_tui) se retiró en 0.3.0: los ajustes
    # viven en Personalización (pins del hub), en cada pantalla y en
    # `python3 settings.py set`.
    # Dashboard general: extraído a la rama feat/dashboard (se retoma después). El
    # código (dashboard.html, dash/<secciones>, cmd_dashboard, modo NORMAL de
    # dashboard.py) ya no vive en main — fuera del hub. En main solo queda el dev panel.
    # «Dev» salió del MENÚ (pedido del socio 2026-10-02): el panel sigue vivo
    # vía `workspace dev` (cmd_dev + ruteo de __dev__ intactos) — solo dejó
    # de ocupar un lugar en el hub. Re-exponerlo = re-agregar la entrada aquí
    # y en opts de _menu_machinery (gate: _has_dev_panel()).
    # «Proyectos» salió del MENÚ (pedido del socio 2026-10-02): la app sigue viva
    # vía `workspace proyectos` (cmd_proyectos + ruteo de __proyectos__ intactos)
    # — solo dejó de ocupar un lugar en el hub. Re-exponerla = re-agregar la
    # entrada en menu_entries() (gate: _has_proyectos()).
    # El MENÚ sale del registro canónico (menu_entries — gates incluidos);
    # el picker estático solo lista SU porción: cal/tono/atajos son pantallas
    # del recinto animado y no entran aquí (decisión previa, intacta).
    _solo_hub = ("__cal__", "__tono__")
    out += [(tok, lbl, tag, True) for tok, lbl, tag in menu_entries()
            if tok not in _solo_hub]
    return out


def _row(disp, tag, selected, selectable, w):
    if not selectable:
        return f"      {GREY}{disp.ljust(w)}{R}{GREY}{tag}{R}"
    if selected:
        return f"    {C}{GPTR} {WH}{disp.ljust(w)}{R}{DIM}{tag}{R}"
    return f"      {DIM}{disp.ljust(w)}{R}{GREY}{tag}{R}"


def _static_cols():
    """Ancho disponible para la vista ESTÁTICA (picker sin hub animado)."""
    try:
        import shutil
        return max(20, shutil.get_terminal_size((100, 40)).columns)
    except Exception:
        return 100


def _static_header():
    """Cabecera de la vista ESTÁTICA (ui.anim apagado, sin tty animable o el
    hub animado falló): el wordmark compacto del hub + la versión — el mismo
    lenguaje del lanzador, nada del recinto viejo. Sin hublayout → el nombre
    llano. Devuelve líneas."""
    w = _static_cols()
    try:
        import hublayout as _HL
        K = _HL.cols(TH) if TH else _HL.cols(types.SimpleNamespace(
            B=B, B2=B2, C=C, WH=WH, DIM=DIM, DK=DK, GREY=GREY, R=R, BO=BO,
            GLYPHS=GL))
        out = [""] + _HL.big_title(K, w, 0, compact=True, center=True)
        try:
            ver = open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()
        except Exception:
            ver = ""
        if ver:
            v = "v" + ver
            out.append(" " * max(0, ((w - 1) - _HL.vis(v)) // 2)
                       + "%s%s%s" % (K["DIM"], v, K["R"]))
        return out + [""]
    except Exception:
        return ["", f"  {C}{BO}WORKSPACE{R}", ""]


def _picker_hints():
    return ((u"↑↓", _t("common.hint.move", "mueve")),
            ("Enter", _t("common.hint.enter", "entra")),
            ("1-9", _t("hub.static.hint.direct", "directo")),
            ("q", _t("common.hint.quit", "sale")))


def _picker_lines(it, idx, w=None):
    """La lista ESTÁTICA con el lenguaje del lanzador: la MISMA caja
    «WORKSPACE» (borde del tema), filas `❯ etiqueta ··· descripción`, un
    separador entre agentes y menú, y los atajos como chips al pie. Altura
    FIJA (no depende de la selección) → el redibujo sube len(líneas).
    Falla-suave: sin hublayout → las filas llanas de siempre (_row)."""
    w = w or _static_cols()
    try:
        import hublayout as _HL
        K = _HL.cols(TH) if TH else _HL.cols(types.SimpleNamespace(
            B=B, B2=B2, C=C, WH=WH, DIM=DIM, DK=DK, GREY=GREY, R=R, BO=BO,
            GLYPHS=GL))
        lw = max([_HL.vis(d) for _, d, _, _ in it] + [8])
        tw = max([_HL.vis(t) for _, _, t, _ in it] + [0])
        pw = max(24, min((w - 1) - 2, 2 + lw + 3 + tw + 4 + 2))
        iw = pw - 4
        body = []
        prev_agent = None
        for i, (nm, disp, tag, sel) in enumerate(it):
            es_menu = str(nm).startswith("__")
            if prev_agent is True and es_menu:
                body.append("%s%s%s" % (K["DK"], K["SEP"] * iw, K["R"]))
            prev_agent = not es_menu
            on = (i == idx)
            cur = ("%s%s%s " % (K["C"] + K["BO"], K["PTR"], K["R"])) if on else "  "
            tinta = (K["C"] + K["BO"]) if on else (K["INACTIVE"] if sel else K["DK"])
            lab = _HL.clip(disp, max(1, iw - 2))
            ln = "%s%s%s%s" % (cur, tinta, lab, K["R"])
            libre = iw - 2 - _HL.vis(lab) - 3
            if tag and libre > 4:
                t = _HL.clip(tag, libre)
                ln += " " * max(3, iw - 2 - _HL.vis(lab) - _HL.vis(t)) \
                    + "%s%s%s" % (K["B2"] if on else K["DIM"], t, K["R"])
            body.append(ln)
        box = _HL.full_box(_t("hub.lanzador.root", "WORKSPACE"), body, K, pw,
                           len(body), True, border=K["C"],
                           label=K["C"] + K["BO"])
        lp = " " * max(0, ((w - 1) - pw) // 2)
        out = [_HL.clip(lp + ln, w - 1) for ln in box]
        hint = _HL.keyline(K, _picker_hints(), w - 2)
        if hint:
            out.append(" " * max(0, ((w - 1) - _HL.vis(hint)) // 2) + hint)
        return out
    except Exception:
        wd = max(len(d) for _, d, _, _ in it) + 2
        return [_row(disp, tag, i == idx, sel, wd)
                for i, (nm, disp, tag, sel) in enumerate(it)]


def _first_selectable(it):
    for i, x in enumerate(it):
        if x[3]:
            return i
    return 0


def _step(idx, d, it):
    n = len(it)
    j = idx
    for _ in range(n):
        j = (j + d) % n
        if it[j][3]:
            return j
    return idx


def _jump_map(agents, opts=None):
    """Teclas rápidas del hub: las CIFRAS de tus agentes, en su orden (en el
    lanzador cada letra escribe en la búsqueda; `q` sale y es fija). La
    cifra N APUNTA al agente N sin lanzarlo; la MISMA tecla otra vez — o
    Enter — lo lanza. Del 10º agente en adelante, sin tecla (flechas o
    búsqueda). `opts` se ignora (compatibilidad). Desde 2026-10-14 no se
    re-mapean (la pantalla «Atajos» quedó aparcada en feat/atajos): un
    keybinds.json viejo ya no cambia nada.
    Devuelve (mapa, display):
      mapa     {'1': ('agent', 0), …}         → lo consume jump()
      display  {'agents': {0: '1', …}}         → para quien quiera pintarlas"""
    n = min(9, len(agents))
    mapa = {str(i + 1): ("agent", i) for i in range(n)}
    return mapa, {"agents": {i: str(i + 1) for i in range(n)}}


def _tty_key(tin):
    """Un byte del tty como str ASCII ('' si EOF o byte no-ASCII). El tty se
    abre SIN buffer (buffering=0): con un TextIOWrapper buffereado, read(1)
    sobre-lee al buffer de userspace y select() sobre el fd deja de ver los
    bytes pendientes — las flechas se romperían con el timeout de _esc_tail."""
    b = tin.read(1)
    if not b:
        return ""
    return b.decode("ascii", "ignore") if isinstance(b, bytes) else b


def _esc_tail(tin, timeout=0.05):
    """Cola de una secuencia de escape CSI, leída SOLO si ya llegó (select con
    timeout corto). ESC suelto → None (no-op; antes un read() bloqueante en raw
    congelaba el menú). Devuelve:
      · 'A'/'B'/'C'/'D'      — flechas (contrato de siempre)
      · ('mouse', x, y)      — click IZQUIERDO SGR-1006 (press; 1-based).
                               Rueda/release/drag se tragan y devuelven '_csi'.
      · '_csi'               — otra CSI completa, CONSUMIDA. Crítico con los
                               dígitos de salto: antes `[1;5A` (ctrl-flecha)
                               dejaba ';5A' en el buffer y ese '5' ahora sería
                               un salto fantasma. Se drena TODO el CSI siempre.
      · None                 — ESC suelto / secuencia ilegible.
    Mouse X10 (`[M` + 3 bytes, terminal sin SGR): se tragan los 3 bytes crudos
    (podrían ser 'q' y botar el hub como tecla fantasma) y devuelve '_csi'."""
    import select
    r, _, _ = select.select([tin], [], [], timeout)
    if not r or _tty_key(tin) != "[":
        return None
    seq = ""
    while True:                              # drena el CSI completo
        r, _, _ = select.select([tin], [], [], timeout)
        if not r:
            return None
        c = _tty_key(tin)
        if not c:
            return None
        if c == "M" and not seq:             # X10: 3 bytes crudos, jamás teclas
            for _ in range(3):
                r, _, _ = select.select([tin], [], [], timeout)
                if r:
                    tin.read(1)
            return "_csi"
        seq += c
        if c.isalpha() or c == "~":          # byte final del CSI
            break
        if len(seq) > 24:                    # ráfaga ilegible: no colgarse
            return None
    if seq in ("A", "B", "C", "D"):
        return seq
    if seq.startswith("<") and seq[-1] in "Mm":          # mouse SGR-1006
        try:
            b, x, y = (int(v) for v in seq[1:-1].split(";"))
        except Exception:
            return "_csi"
        # press ('M') del botón IZQUIERDO sin rueda/drag; shift/alt/ctrl
        # (bits 4/8/16) no invalidan el click
        if seq[-1] == "M" and (b & ~28) == 0:
            return ("mouse", x, y)
        return "_csi"                        # rueda/release/otros: consumidos
    return "_csi"


def _run_picker_windows(it):
    # Windows: navegación con flechas vía msvcrt (paridad con la rama Unix de abajo).
    import msvcrt
    out = sys.stderr
    n = len(it)
    idx = _first_selectable(it)
    drawn = [0]

    def draw(first):
        if not first and drawn[0]:
            out.write(f"\033[{drawn[0]}A")
        lines = _picker_lines(it, idx)
        for ln in lines:
            out.write("\r\033[K" + ln + "\r\n")
        drawn[0] = len(lines)
        out.flush()

    draw(True)
    while True:
        ch = msvcrt.getwch()
        if ch in ("\x00", "\xe0"):          # prefijo de tecla especial (flechas)
            a = msvcrt.getwch()
            if a == "H":
                idx = _step(idx, -1, it)
            elif a == "P":
                idx = _step(idx, +1, it)
            else:
                continue
        elif ch in ("\r", "\n"):
            if it[idx][3]:
                break
            continue
        elif ch in ("q", "Q", "\x03"):
            idx = next((i for i, x in enumerate(it) if x[0] == "__shell__"), idx); break
        elif ch.isdigit() and 1 <= int(ch) <= n and it[int(ch) - 1][3]:
            idx = int(ch) - 1; break
        else:
            continue
        draw(False)
    return idx


def run_picker(it):
    if sys.platform == "win32":
        # msvcrt lee de la CONSOLA, no de stdin: sin consola interactiva real
        # (pipe/archivo/NUL) esperaría una tecla para siempre → lista numerada
        # sobre stdin (EOF → Terminal normal, determinista). W-F04.
        if not _interactive_console():
            return _numbered(it)
        try:
            return _run_picker_windows(it)
        except Exception:
            return _numbered(it)
    try:
        import termios, tty
        # binario sin buffer: select() en _esc_tail ve TODO lo pendiente
        tin = open("/dev/tty", "rb", buffering=0); tout = open("/dev/tty", "w")
    except Exception:
        return _numbered(it)
    n = len(it)
    idx = _first_selectable(it)
    drawn = [0]

    def draw(first):
        if not first and drawn[0]:
            tout.write(f"\033[{drawn[0]}A")
        lines = _picker_lines(it, idx)
        for ln in lines:
            tout.write("\r\033[K" + ln + "\r\n")
        drawn[0] = len(lines)
        tout.flush()

    draw(True)
    fd = tin.fileno(); old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            ch = _tty_key(tin)
            if ch == "\x1b":
                a = _esc_tail(tin)          # ESC suelto → None (no congela ni traga teclas)
                if a == "A":
                    idx = _step(idx, -1, it)
                elif a == "B":
                    idx = _step(idx, +1, it)
            elif ch in ("\r", "\n"):
                if it[idx][3]:
                    break
            elif ch in ("q", "Q", "\x03"):
                idx = next((i for i, x in enumerate(it) if x[0] == "__shell__"), idx); break
            elif ch.isdigit() and 1 <= int(ch) <= n and it[int(ch) - 1][3]:
                idx = int(ch) - 1; break
            else:
                continue
            termios.tcsetattr(fd, termios.TCSADRAIN, old); draw(False); tty.setraw(fd)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)
    return idx


def _numbered(it):
    try:
        # En Windows "/dev/tty" sería el archivo C:/dev/tty, no la consola.
        if os.name == "nt":
            raise OSError
        inp = open("/dev/tty", "r"); out = open("/dev/tty", "w")
    except Exception:
        inp, out = sys.stdin, sys.stderr
    out.write("\n")
    sel = [i for i, x in enumerate(it) if x[3]]
    for k, i in enumerate(sel, 1):
        out.write(f"    {C}{k}{R}  {WH}{it[i][1]}{R}   {DIM}{it[i][2]}{R}\n")
    out.write(f"\n  {DIM}{_t('banner.dash.number_enter', 'Número y Enter: ')}{R}"); out.flush()
    try:
        k = int((inp.readline() or "").strip())
        if 1 <= k <= len(sel):
            return sel[k - 1]
    except Exception:
        pass
    # EOF / input no interactivo / inválido → Terminal normal, NUNCA auto-lanzar
    # un agente (un pipe o automation no debe terminar dentro de Claude Code).
    return next((i for i, x in enumerate(it) if x[0] == "__shell__"), _first_selectable(it))


def _split_on():
    """True si el socio prendió la terminal PARTIDA para el hub
    (`settings set ui.split on`). DEFAULT: False — el arranque de siempre.
    Falla-suave absoluta: cualquier duda → False (jamás desviar el handoff
    por error). El hub/menú de arriba no dependen de esto: el gate se
    consulta SOLO al lanzar, después de elegir agente."""
    try:
        import settings as _settings
        return bool(_settings.enabled("ui.split", default=False))
    except Exception:
        return False


def launch(name):
    sys.stdout.write("\033[2J\033[3J\033[H"); sys.stdout.flush()   # limpia + scrollback para el banner del agente
    os.environ["WORKSPACE_FROM_HUB"] = "1"   # Esc en el menú de sesiones regresa aquí
    # Terminal PARTIDA (opt-in, ui.split — APAGADO por default): SOLO aquí,
    # DESPUÉS de que el socio eligió agente en el menú, el chat abre con 2
    # panes (chat | panel del pipeline) vía multiplexer.open_split — la
    # abstracción elige backend (ui.split_backend: auto|tmux|herdr) y arma
    # el MISMO split de `workspace split`. El hub/menú de arriba NO pasan por
    # ningún multiplexer jamás. open_split cae solo al arranque normal ante
    # cualquier impedimento (sin tmux/herdr, sin TTY, anidado, Windows o
    # fallo a medio armado), con aviso — nunca rompe el arranque.
    if _split_on():
        try:
            import multiplexer
            sys.exit(multiplexer.open_split([name]))
        except SystemExit:
            raise
        except Exception:
            pass   # el modo partido JAMÁS rompe el arranque → camino de siempre
    if os.name == "nt":   # Windows: exec no reemplaza el proceso (consola rota) → subprocess (igual que dispatch._exec)
        sys.exit(subprocess.run([PY, DISPATCH, name]).returncode)
    os.execvp(PY, [PY, DISPATCH, name])   # handoff directo: al salir del agente, vuelves al shell


def _dev_kill(port, pidfile):
    """Mata CUALQUIER dashboard de dev en `port` + limpia el pidfile. Idempotente,
    cross-platform, falla-suave. Lo usan `workspace dev stop` Y el arranque (que
    siempre reinicia fresco). Mata por puerto (no solo por pidfile) para barrer
    también servers zombie de corridas viejas."""
    import subprocess
    if os.name == "nt":
        pid = ""
        try:
            pid = open(pidfile, encoding="utf-8").read().strip()
        except Exception:
            pass
        if pid.isdigit():
            subprocess.run(["taskkill", "/PID", pid, "/T", "/F"], capture_output=True, text=True, encoding="utf-8", errors="replace")
        # además, barre lo que escuche en el puerto (zombies sin pidfile)
        try:
            out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True,
                                 text=True, encoding="utf-8", errors="replace").stdout
            for line in out.splitlines():
                if (":%d " % port) in line and "LISTENING" in line:
                    z = line.split()[-1]
                    if z.isdigit() and z != pid:
                        subprocess.run(["taskkill", "/PID", z, "/T", "/F"],
                                       capture_output=True, text=True,
                                       encoding="utf-8", errors="replace")
        except Exception:
            pass
    else:
        # mata TODO lo que escuche en el puerto (cubre zombies de código viejo)
        subprocess.run("lsof -ti tcp:%d | xargs kill 2>/dev/null" % port, shell=True)
    try:
        os.remove(pidfile)
    except Exception:
        pass


def _dev_desktop_app():
    """Ruta a la app nativa del dev panel (WORKSPACE.app, Tauri) si está instalada.
    Solo macOS. Devuelve None si no existe → el hub cae al navegador (parity para
    Windows, teammates sin la app, o máquinas sin buildear). La app envuelve
    `dashboard.py` en una ventana WKWebView; su ciclo de vida REUSA un server ya
    corriendo y NO lo mata al cerrar (por eso el hub puede arrancarlo fresco antes
    y abrir la app apuntando a ese server)."""
    if sys.platform != "darwin":
        return None
    for cand in (
        "/Applications/WORKSPACE.app",
        os.path.expanduser("~/Applications/WORKSPACE.app"),
        os.path.expanduser("~/Desktop/workspace-desktop/src-tauri/target/release/bundle/macos/WORKSPACE.app"),
    ):
        if os.path.isdir(cand):
            return cand
    return None


def cmd_dev(args):
    """`workspace dev` — abre el dashboard de DEV «mission control de developer»:
    git-graph + cambio de rama con 1 click, SIN terminal. SUPERFICIE APARTE del
    dashboard normal. Local-only, mismo guard de token. Puerto propio (def 9121).

    SIEMPRE reinicia fresco: si ya hay un server en el puerto (incl. de código
    viejo), lo mata y arranca con el código ACTUAL — re-correr `workspace dev` tras
    un cambio SIEMPRE sirve lo nuevo (antes reusaba el viejo: footgun). También
    barre servers zombie. `workspace dev stop` lo detiene. No va a clientes."""
    import socket, subprocess, webbrowser, time
    port = 9121                                   # ≠ 9120 del dashboard normal (coexisten)
    if "--port" in args:
        try:
            port = int(args[args.index("--port") + 1])
        except Exception:
            pass
    url = f"http://127.0.0.1:{port}"

    def running():
        try:
            socket.create_connection(("127.0.0.1", port), 0.3).close()
            return True
        except Exception:
            return False

    pidfile = os.path.join(_paths.state_dir(), "dashboard-dev.pid")

    if "stop" in args or "--stop" in args:
        _dev_kill(port, pidfile)
        print(f"{C}WORKSPACE dev detenido.{R}")
        return 0

    # SIEMPRE arranca fresco con el código actual: mata lo que haya (server viejo /
    # zombie) y espera a que el puerto se libere antes de relanzar.
    if running():
        print(f"{DIM}  reiniciando el dev panel con el código actual…{R}")
        _dev_kill(port, pidfile)
        for _ in range(20):
            if not running():
                break
            time.sleep(0.15)

    logdir = _paths.state_dir()
    try:
        os.makedirs(logdir, exist_ok=True)
        log = open(os.path.join(logdir, "dashboard-dev.log"), "a", encoding="utf-8")
    except Exception:
        log = subprocess.DEVNULL
    kw = {"creationflags": 0x208} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen(
        [PY, os.path.join(ROOT, "dashboard.py"), "--dev", "--no-open", "--port", str(port)],
        stdout=log, stderr=log, stdin=subprocess.DEVNULL, **kw)
    try:
        os.makedirs(os.path.dirname(pidfile), exist_ok=True)
        open(pidfile, "w", encoding="utf-8").write(str(proc.pid))
    except Exception:
        pass
    for _ in range(25):
        if running():
            break
        time.sleep(0.15)
    # El server ya está fresco (código actual). Preferimos la APP NATIVA (ventana
    # propia, sin barra de URL); la app detecta este server corriendo y lo REUSA
    # (no arranca otro ni lo mata al cerrar → el server persiste como con `workspace
    # dev`). Sin app instalada → navegador, como siempre.
    app = _dev_desktop_app()
    if app:
        subprocess.run(["open", app])
        surface = f"{DIM}(app nativa){R}"
    else:
        webbrowser.open(url)
        surface = f"{DIM}(en el navegador — instala WORKSPACE.app para ventana nativa){R}"
    print(f"{C}WORKSPACE dev{R} (mission control) → {url}  {surface}")
    print(f"{DIM}  reabrir/refrescar: workspace dev   ·   detener: workspace dev stop{R}")
    return 0


def cmd_proyectos(args):
    """`workspace proyectos` — abre la app «Proyectos»: una sola página con TODOS
    tus proyectos como mapa conceptual, el detalle de cada nodo a la izquierda y
    el chat con el agente que elijas a la derecha.

    APP INDEPENDIENTE (la primera de la serie): puerto propio (def 9122), server
    propio (proyectos.py) y datos propios — coexiste con el dashboard (9120) y el
    dev panel (9121) sin pisarlos. Mismo contrato de arranque que `workspace dev`:
    SIEMPRE reinicia fresco (mata el server viejo/zombie del puerto y relanza con
    el código actual), pidfile + log per-máquina, `stop` lo detiene. Local-only,
    guard de token del dashboard."""
    import socket, subprocess, webbrowser, time
    port = 9122                                   # ≠ 9120 (dashboard) · ≠ 9121 (dev)
    if "--port" in args:
        try:
            port = int(args[args.index("--port") + 1])
        except Exception:
            pass
    url = f"http://127.0.0.1:{port}"

    def running():
        try:
            socket.create_connection(("127.0.0.1", port), 0.3).close()
            return True
        except Exception:
            return False

    pidfile = os.path.join(_paths.state_dir(), "proyectos.pid")

    if "stop" in args or "--stop" in args:
        _dev_kill(port, pidfile)                  # el killer por puerto+pidfile es genérico
        print(f"{C}" + _t("cli.proy.stopped", "WORKSPACE proyectos detenido.")
              + f"{R}")
        return 0

    if running():                                 # relanzar = servir el código de HOY
        print(f"{DIM}  " + _t("cli.proy.restarting", "reiniciando la app de "
                               "proyectos con el código actual…") + f"{R}")
        _dev_kill(port, pidfile)
        for _ in range(20):
            if not running():
                break
            time.sleep(0.15)

    logdir = _paths.state_dir()
    try:
        os.makedirs(logdir, exist_ok=True)
        log = open(os.path.join(logdir, "proyectos.log"), "a", encoding="utf-8")
    except Exception:
        log = subprocess.DEVNULL
    kw = {"creationflags": 0x208} if os.name == "nt" else {"start_new_session": True}
    proc = subprocess.Popen(
        [PY, os.path.join(ROOT, "proyectos.py"), "--no-open", "--port", str(port)],
        stdout=log, stderr=log, stdin=subprocess.DEVNULL, **kw)
    try:
        os.makedirs(os.path.dirname(pidfile), exist_ok=True)
        open(pidfile, "w", encoding="utf-8").write(str(proc.pid))
    except Exception:
        pass
    for _ in range(25):
        if running():
            break
        time.sleep(0.15)
    webbrowser.open(url)
    print(f"{C}WORKSPACE proyectos{R} "
          + _t("cli.proy.map", "(mapa de proyectos)") + f" → {url}  {DIM}"
          + _t("cli.proy.separate", "(app aparte del dashboard)") + f"{R}")
    print(f"{DIM}  " + _t("cli.proy.hint", "reabrir/refrescar: workspace "
                           "proyectos   ·   detener: workspace proyectos stop")
          + f"{R}")
    return 0


def _git(path, *args, timeout=30):
    """git -C <path> <args> con captura. (rc, stdout, stderr). Nunca lanza (salvo
    FileNotFoundError si git no existe — la maneja el caller una sola vez)."""
    try:
        r = subprocess.run(["git", "-C", path] + list(args),
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=timeout)
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except subprocess.TimeoutExpired:
        return -1, "", _t("cli.git.timeout", "timeout (¿sin conexión?)")


def _update_repo(label, path, transport="git"):
    """Pull --ff-only de UN repo en su rama actual. Imprime una línea de estado.
    Devuelve 'updated' | 'uptodate' | 'managed' | 'skipped' (⚠, nunca aborta el resto).
    `transport='obsidian-sync'` (cerebros gestionados por Obsidian Sync) = canal
    SANO: ✓ verde y 'managed', no cuenta como repo saltado."""
    pad = f"  {label:<22}"
    if transport == "obsidian-sync":
        print(f"{pad}{C}✓{R} {DIM}"
              + _t("cli.repo.obsidian", "carpeta local (no se actualiza por git)")
              + f"{R}")
        return "managed"
    if not os.path.isdir(os.path.join(path, ".git")):
        print(f"{pad}{B}⚠{R} {DIM}"
              + _t("cli.repo.not_git", "no es repo git (instalación por sync) — "
                   "sin auto-update") + f"{R}")
        return "skipped"
    rc, remotes, _ = _git(path, "remote", timeout=10)
    if rc != 0 or not remotes:
        print(f"{pad}{B}⚠{R} {DIM}"
              + _t("cli.repo.no_remote", "sin remote configurado — nada que jalar")
              + f"{R}")
        return "skipped"
    _, dirty, _ = _git(path, "status", "--porcelain", timeout=15)
    if dirty:
        print(f"{pad}{B}⚠{R} "
              + _t("cli.repo.dirty", "cambios locales sin commitear")
              + f" {DIM}— "
              + _t("cli.repo.dirty_hint", "no jalo encima; commitea/guarda y "
                   "reintenta") + f"{R}")
        return "skipped"
    _, branch, _ = _git(path, "rev-parse", "--abbrev-ref", "HEAD", timeout=10)
    _, old, _ = _git(path, "rev-parse", "--short", "HEAD", timeout=10)
    rc, out, err = _git(path, "pull", "--ff-only", timeout=90)   # rama ACTUAL (stable/main…)
    if rc != 0:
        low = (out + " " + err).lower()
        if "no tracking information" in low or "no remote ref" in low or "couldn't find remote ref" in low:
            print(f"{pad}{B}⚠{R} {DIM}"
                  + _t("cli.repo.no_upstream", "la rama '{branch}' no rastrea a "
                       "origin", branch=branch)
                  + f' — git -C "{path}" branch --set-upstream-to=origin/{branch}{R}')
        elif "could not resolve" in low or "unable to access" in low or "timeout" in low or "connection" in low:
            print(f"{pad}{B}⚠{R} {DIM}"
                  + _t("cli.repo.offline", "sin conexión con origin (¿offline?) — "
                       "se queda como está") + f"{R}")
        elif "not possible to fast-forward" in low or "divergent" in low:
            print(f"{pad}{B}⚠{R} "
                  + _t("cli.repo.diverged", "historia divergente")
                  + f" {DIM}— "
                  + _t("cli.repo.diverged_hint", "resuélvelo a mano:")
                  + f' git -C "{path}" pull --ff-only{R}')
        else:
            _last = ((err or out).splitlines()[-1] if (err or out)
                     else _t("cli.repo.pull_failed", "pull falló"))
            print(f"{pad}{B}⚠{R} {DIM}{_last}{R}")
        return "skipped"
    _, new, _ = _git(path, "rev-parse", "--short", "HEAD", timeout=10)
    if new and new != old:
        print(f"{pad}{C}✓{R} " + _t("cli.repo.updated_to", "actualizado a")
              + f" {C}{new}{R} {DIM}("
              + _t("cli.repo.branch", "rama {branch}", branch=branch) + f"){R}")
        return "updated"
    print(f"{pad}{C}✓{R} {DIM}"
          + _t("update.harness.uptodate", "ya al día") + " ("
          + _t("cli.repo.branch", "rama {branch}", branch=branch) + f"){R}")
    return "uptodate"


def _print_harness_update(res):
    """Una línea (o dos) que cuentan qué pasó con el harness, en lenguaje de
    usuario. `res` = updater.update_harness()."""
    import updater
    pad = f"  {'WORKSPACE':<22}"
    st = res.get("status")
    if st == updater.UPDATED:
        frm = res.get("from_version") or res.get("from", "")[:7]
        to = res.get("to_version") or res.get("to", "")[:7]
        ver = (f"v{frm} → v{to}" if frm != to else f"v{to} ({res.get('to', '')[:7]})")
        print(f"{pad}{C}✓{R} {_t('update.harness.updated', 'actualizado')} {C}{ver}{R} "
              f"{DIM}("
              + _t("cli.update.changes", "{n} cambio(s)",
                   n=len(res.get('commits') or []))
              + " · " + _t("cli.repo.branch", "rama {branch}",
                           branch=res.get('branch')) + f"){R}")
        mig = res.get("migrations") or {}
        try:
            import migrate as _mig
            line = _mig.summary_line(mig) if not mig.get("error") else ""
        except Exception:
            line = ""
        if line:
            print(f"  {'':<22}{DIM}{line}{R}")
        return
    if st == updater.UPTODATE:
        print(f"{pad}{C}✓{R} {DIM}{_t('update.harness.uptodate', 'ya al día')} "
              f"(v{res.get('from_version') or '?'} · "
              + _t("cli.repo.branch", "rama {branch}", branch=res.get('branch'))
              + f"){R}")
        return
    if st == updater.ROLLED_BACK:
        print(f"{pad}{B}⚠{R} {_t('update.harness.rolled_back', 'la versión nueva no arrancó en esta máquina: volví a la anterior')}"
              f" {DIM}(v{res.get('from_version') or '?'}){R}")
        if res.get("detail"):
            print(f"  {'':<22}{DIM}{res['detail'][:160]}{R}")
        print(f"  {'':<22}{DIM}{_t('update.harness.held_hint', 'Se queda así hasta que publiquemos un arreglo; no tienes que hacer nada.')}{R}")
        return
    if st == updater.HELD:
        h = updater.hold() or {}
        if h.get("kind") == "manual":
            msg = _t("update.harness.paused_manual",
                     "volviste a la versión anterior; la v{v} queda en pausa hasta que "
                     "publiquemos una más nueva", v=h.get("bad_version") or "?")
        else:
            msg = _t("update.harness.held", "versión fijada: la última publicada no "
                     "arrancó aquí y aún no hay una más nueva")
        print(f"{pad}{B}⚠{R} {DIM}{msg} — workspace update --force{R}")
        return
    if st == updater.ROLLBACK_FAILED:
        print(f"{pad}{B}⚠{R} {updater.reason_text('reset_failed')}")
        print(f"  {'':<22}{DIM}{_t('update.harness.rollback_failed_hint', 'Corre `workspace doctor`; si sigue, `workspace doctor --bundle` y envíanos el zip.')}{R}")
        return
    print(f"{pad}{B}⚠{R} {DIM}{updater.reason_text(res.get('reason'))}{R}")


def _cmd_update_auto(args):
    """`workspace update --auto` muestra el modo; `--auto <modo>` lo cambia."""
    import updater
    i = args.index("--auto")
    val = args[i + 1].lower() if i + 1 < len(args) else ""
    alias = {"on": "auto", "si": "auto", "sí": "auto", "avisar": "notify",
             "aviso": "notify", "no": "off", "apagado": "off", "apagar": "off"}
    val = alias.get(val, val)
    if val:
        if val not in updater.AUTO_MODES:
            print(_t("cli.update.auto_usage",
                     "uso: workspace update --auto [auto|notify|off]"))
            return 2
        try:
            updater.set_auto_mode(val)
        except Exception as e:
            print(f"{B}⚠{R} " + _t("cli.update.auto_save_fail",
                                    "no pude guardar el ajuste: {err}", err=e))
            return 1
    print(_t("cli.update.auto_head", "Actualizaciones") + " "
          + updater.auto_mode_text())
    if os.environ.get("WORKSPACE_NO_AUTOUPDATE") and val and val != "off":
        print(f"{DIM}  " + _t("cli.update.auto_env", "ojo: WORKSPACE_NO_AUTOUPDATE=1 "
                               "está puesto en tu terminal y manda sobre el "
                               "ajuste; quítalo para que valga «{val}».", val=val)
              + f"{R}")
    print(f"{DIM}  " + _t("cli.update.auto_change", "Cambia con: workspace update "
                           "--auto auto | notify | off · `workspace update` "
                           "instala cuando quieras.") + f"{R}")
    return 0


def cmd_update(args=None):
    """`workspace update` — deja la máquina del socio al día y verificada, en uno:
      1. Harness: updater.update_harness (candado → anota de dónde sale → avanza
         solo en fast-forward → comprueba que la versión nueva ARRANCA aquí →
         si no, vuelve sola a la anterior → aplica los ajustes registrados).
      2. git pull --ff-only de cada cerebro registrado (resueltos con brain_resolver).
      3. workspace doctor (REPARA) al final, en un proceso NUEVO si el harness
         cambió: así el doctor que corre es el de la versión nueva.
    Seguro e idempotente: repo sucio / offline / sin remote → ⚠ y sigue con los demás.
    `--check` solo diagnostica · `--no-check` salta el doctor · `--force` reintenta
    una versión fijada · `--rollback` vuelve a la versión anterior al último update ·
    `--auto [auto|notify|off]` muestra o elige si se actualiza solo."""
    args = list(args or [])
    if "--rollback" in args:
        return _cmd_update_rollback(args)
    if "--auto" in args:
        return _cmd_update_auto(args)
    print(f"{C}WORKSPACE update{R} {DIM}— "
          + _t("cli.update.head", "harness + cerebros, en su rama actual…")
          + f"{R}\n")
    import updater
    hres = updater.update_harness(ROOT, mode="manual", force="--force" in args)
    if hres.get("reason") == "git_missing":
        print(f"\n{B}" + _t("cli.update.no_git", "git no está instalado en esta "
                             "máquina.") + f"{R} "
              + _t("cli.update.no_git_hint", "Instálalo y vuelve a correr "
                   "`workspace update`."))
        return 1
    _print_harness_update(hres)
    skipped = 1 if hres.get("status") in (updater.SKIPPED, updater.BUSY,
                                           updater.HELD, updater.ROLLED_BACK) else 0

    # cerebros: cada uno con su pull de siempre (son datos del usuario)
    repos = []
    try:
        import dispatch
        import brain_resolver                     # Z20: resolver canónico único
        for entry in dispatch.load_registry().get("agents", []):
            try:
                cfg = dispatch.load_agent_cfg(entry)
            except Exception:
                cfg = {}
            if dispatch.is_system_agent(entry, cfg):
                continue                          # motor interno: no es del usuario
            res = brain_resolver.resolve(entry["name"], cfg, entry)
            brain = res.path
            if res.get("exists"):
                repos.append((_t("cli.update.brain_label", "cerebro {name}",
                                 name=entry['name']), brain,
                              dispatch.brain_transport(entry["name"], brain)))
            else:
                repos.append((_t("cli.update.brain_label", "cerebro {name}",
                                 name=entry['name']), None, "git"))
    except Exception as e:
        print(f"  {B}⚠{R} {DIM}"
              + _t("cli.update.registry_fail", "no pude leer el registry de "
                   "agentes ({err}) — solo actualizo WORKSPACE", err=e) + f"{R}")

    seen = {os.path.normcase(os.path.realpath(ROOT))}
    try:
        for label, path, transport in repos:
            if path is None:
                print(f"  {label:<22}{B}⚠{R} {DIM}"
                      + _t("cli.update.brain_unresolved", "cerebro no resuelto — "
                           "corre `workspace doctor`") + f"{R}")
                skipped += 1
                continue
            key = os.path.normcase(os.path.realpath(path))
            if key in seen:
                continue
            seen.add(key)
            if _update_repo(label, path, transport) == "skipped":
                skipped += 1
    except FileNotFoundError:
        print(f"\n{B}" + _t("cli.update.no_git", "git no está instalado en esta "
                             "máquina.") + f"{R} "
              + _t("cli.update.no_git_hint", "Instálalo y vuelve a correr "
                   "`workspace update`."))
        return 1

    if skipped:
        print(f"\n{DIM}  " + _t("cli.update.skipped", "{n} repo(s) quedaron sin "
                                "actualizar (⚠ arriba) — el resto sí jaló.",
                                n=skipped) + f"{R}")

    if "--no-check" in args:
        print(f"\n{C}" + _t("cli.update.done", "✓ Update terminado.") + f"{R} {DIM}"
              + _t("cli.update.no_check", "(doctor omitido por --no-check)")
              + f"{R}")
        return 0

    check_only = "--check" in args
    if check_only:
        print(f"\n{DIM}  " + _t("cli.update.verifying", "Verificando la "
                                "instalación (workspace doctor --check)…") + f"{R}")
    else:
        print(f"\n{DIM}  " + _t("cli.update.verifying_fix", "Verificando y "
                                "reparando la instalación (workspace doctor)…")
              + f"{R}")
    # `--from-update`: el doctor NO vuelve a ofrecer update (evita recursión).
    dargs = (["--check"] if check_only else []) + ["--from-update"]
    try:
        if hres.get("status") == updater.UPDATED:
            # código nuevo en disco → el doctor NUEVO, en su propio proceso
            return subprocess.call([sys.executable, os.path.join(ROOT, "front.py"),
                                    "doctor"] + dargs)
        rc = cmd_doctor(dargs)
    except Exception as e:
        print(f"  {B}⚠{R} {DIM}"
              + _t("cli.update.doctor_failed", "el doctor falló ({err}) — corre "
                   "`workspace doctor` a mano", err=f"{type(e).__name__}: {e}")
              + f"{R}")
        return 1
    return rc or 0


def _cmd_update_rollback(args):
    """`workspace update --rollback` — vuelve a la versión anterior al último
    update y la deja fijada hasta que se publique una más nueva. Muestra qué
    va a hacer y pide confirmación (salvo --yes)."""
    import updater
    e = updater.rollback_target(ROOT)
    if not e:
        print(f"  {DIM}{_t('update.rollback.none', 'No hay una actualización reciente a la que volver desde esta versión.')}{R}")
        return 1
    to_v = e.get("to_version") or e["to"][:7]
    frm_v = e.get("from_version") or e["from"][:7]
    when = (e.get("at") or "")[:16].replace("T", " ")
    print("  " + _t("update.rollback.plan",
                    "Volver de v{to} a v{frm} (la que tenías antes del update del {at}).",
                    to=to_v, frm=frm_v, at=when))
    print(f"  {DIM}" + _t("update.rollback.keeps",
                          "Tus agentes, cerebros y ajustes no se tocan. La versión nueva "
                          "queda en pausa hasta que publiquemos una más reciente.") + f"{R}")
    if "--yes" not in args and "-y" not in args:
        try:
            if not sys.stdin.isatty():
                print(f"  {DIM}" + _t("update.rollback.need_yes",
                                      "(sin terminal interactiva: añade --yes para confirmar)") + f"{R}")
                return 1
            ans = input("  " + _t("update.rollback.confirm", "¿Continuar? [s/N]") + " ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return 1
        if ans not in ("s", "si", "sí", "y", "yes"):
            return 1
    out = updater.rollback(ROOT)
    if out["ok"]:
        print(f"  {C}✓{R} " + _t("update.rollback.done", "Listo: estás en v{v}.",
                                  v=out.get("to_version") or out["to"][:7]))
        return 0
    msg = updater.reason_text(out["reason"]) if out["reason"] in updater.REASONS else out["reason"]
    print(f"  {B}⚠{R} {msg}")
    return 1


def _changelog_section(version, lang=None):
    """Viñetas de la sección `## <version>` del CHANGELOG del idioma activo
    (CHANGELOG.md = español, CHANGELOG.en.md = inglés; si falta uno se usa el
    otro). [] si no hay sección. Lectura pura, falla-suave."""
    try:
        lang = lang or (i18n.lang() if i18n else "es")
    except Exception:
        lang = "es"
    names = (["CHANGELOG.en.md", "CHANGELOG.md"] if lang == "en"
             else ["CHANGELOG.md", "CHANGELOG.en.md"])
    for fn in names:
        try:
            with open(os.path.join(ROOT, fn), encoding="utf-8") as fh:
                lines = fh.read().splitlines()
        except OSError:
            continue
        out, inside = [], False
        for ln in lines:
            if ln.startswith("## "):
                if inside:
                    break
                inside = ln[3:].strip().split(" ")[0].lstrip("v") == version
                continue
            if not inside:
                continue
            if ln.strip().startswith(("- ", "* ")):
                out.append(ln.strip()[2:].strip())
            elif out and ln.startswith("  ") and ln.strip():
                out[-1] += " " + ln.strip()       # viñeta que sigue en la línea de abajo
        if out:
            return out
    return []


def cmd_version(args=None):
    """`workspace version` (`--version`, `-V`) — qué versión corre ESTA máquina,
    de dónde viene, su última actualización y sus ajustes. Para que un cliente
    (y quien le da soporte) sepa exactamente qué tiene, sin abrir git."""
    import platform
    import updater
    args = list(args or [])
    cur = updater.current(ROOT)
    v = cur.get("version") or "?"
    if "--short" in args:
        print(v)
        return 0
    print(f"  {C}{BO}" + _t("version.title", "Workspace v{v}", v=v) + f"{R}")
    if cur.get("sha"):
        print(f"  {DIM}" + _t("version.commit", "código: {sha} · rama {branch}",
                              sha=cur["short"], branch=cur.get("branch") or "?") + f"{R}")
    try:
        import capabilities
        osname = capabilities.os_label()
    except Exception:
        osname = "?"
    print(f"  {DIM}" + _t("version.python", "Python {py} · {os}",
                          py=platform.python_version(), os=osname) + f"{R}")
    last = updater.last_update()
    if last:
        print(f"  {DIM}" + _t("version.last_update", "última actualización: {at} (v{frm} → v{to})",
                              at=(last.get("at") or "")[:16].replace("T", " "),
                              frm=last.get("from_version") or "?",
                              to=last.get("to_version") or "?") + f"{R}")
    h = updater.hold()
    if h:
        bad = h.get("bad_version") or h.get("bad", "")[:7]
        if h.get("kind") == "manual":
            print(f"  {B}" + _t("version.paused_manual", "⚠ volviste a la versión anterior: "
                                "la v{v} queda en pausa hasta una más nueva", v=bad) + f"{R}")
        else:
            print(f"  {B}" + _t("version.held", "⚠ versión fijada: la v{v} no arrancó en esta "
                                "máquina; esperando una más nueva", v=bad) + f"{R}")
    try:
        import migrate
        ms = migrate.status()
        print(f"  {DIM}" + _t("version.migrations", "ajustes aplicados: {n} · pendientes: {p}",
                              n=len(ms["applied"]), p=len(ms["pending"])) + f"{R}")
        if ms.get("failed"):
            print(f"  {B}" + _t("version.migration_failed", "⚠ un ajuste falló: {id} — corre "
                                "`workspace doctor`", id=ms["failed"]["id"]) + f"{R}")
    except Exception:
        pass
    notes = _changelog_section(v)
    if notes:
        print("\n  " + _t("version.changes", "Novedades de esta versión:"))
        for n in notes[:10]:
            print(f"   · {n}")
        print(f"  {DIM}" + _t("version.changelog_hint", "Historial completo: CHANGELOG.md") + f"{R}")
    return 0


def _apply_pending_migrations():
    """Al abrir el hub: si una actualización dejó ajustes pendientes (p. ej. la
    hizo una versión anterior del actualizador, o se corrió `git pull` a mano),
    aplicarlos AQUÍ, a la vista: una línea y una pausa breve para leerla. Nunca
    rompe el arranque. Silencioso si no hay nada."""
    try:
        import migrate
        if not migrate.has_runnable_pending():
            return
        res = migrate.run_pending()
        line = migrate.summary_line(res)
        if line:
            sys.stderr.write(f"\n  {B2}{line}{R}\n")
            sys.stderr.flush()
            import time
            time.sleep(1.6)
    except Exception:
        pass


AGENT_COLORS = {"zenith": "blue", "atlas": "red", "argus": "green",
                "turing": "cyan"}


# Medición de ancho COMPARTIDA (_width.py — la MISMA del hub): ANSI
# completo (CSI/OSC/ESC de 2 bytes, no solo SGR), combinantes/zero-width = 0,
# CJK/Hangul = 2. Antes front tenía su propio regex solo-SGR y su propia tabla
# → un glifo de tema medía distinto aquí que en otra pantalla y descuadraba.
from _width import strip_ansi as _strip_ansi, sane as _wsane, eaw as _eaw  # noqa: E402
def _vis(s):
    # Ancho VISUAL (no len) — ver _width.py. Crítico para el padding/centrado
    # del recinto: un nombre coreano (누리) mal medido sobre-rellena la línea,
    # la envuelve (wrap) y descuadra el redibujo.
    return sum(_eaw(c) for c in _wsane(_strip_ansi(s)))
# Ancho del bloque de texto de los fallbacks estáticos (picker sin tty).
_BLOCK_W = 72


def _ui_setting_on(name):
    """Setting bool ui.* del store unificado (settings.py, misma raíz).
    Falla-suave → True (el look de siempre). El env WORKSPACE_NO_* se chequea
    APARTE en cada sitio de consumo y SIEMPRE gana."""
    try:
        import settings as _settings
        return _settings.enabled("ui." + name, default=True)
    except Exception:
        return True


def _code_stamp():
    """(VERSION, HEAD) del código en disco — para saber si una actualización
    cambió el código mientras el hub corría. Falla-suave → ("", "")."""
    ver = head = ""
    try:
        with open(os.path.join(ROOT, "VERSION"), encoding="utf-8") as fh:
            ver = fh.read().strip()
    except Exception:
        pass
    try:
        r = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=4)
        head = (r.stdout or "").strip() if r.returncode == 0 else ""
    except Exception:
        pass
    return (ver, head)


def _restart_hub():
    """Reabre el hub con el código nuevo (tras una actualización)."""
    argv = [sys.executable, os.path.abspath(__file__)] + sys.argv[1:]
    if os.name == "nt":   # Windows: exec no reemplaza el proceso (consola rota) → subprocess (igual que dispatch._exec)
        sys.exit(subprocess.run(argv).returncode)
    os.execv(sys.executable, argv)


def _hub_version_text():
    """Texto PLANO (sin ANSI) del indicador de versión para abajo-derecha del hub:
    rama actual + estado de sync — para que el socio (y clientes) SIEMPRE sepan en qué
    versión están y en qué punto del tiempo. Sin RED (no hace fetch — usa el ref
    `origin/main` ya presente). Windows-safe (solo ASCII + `·` + ↑↓). Falla-suave
    ABSOLUTA: si no es repo git / git no está / cualquier cosa truena → "".

    Ejemplos: "main · al día" · "main · ↑3 sin publicar" · "main · ↓2 update"
    · "feat/x" · (cliente) "v1a2b3c · al día" / "v1a2b3c · update disponible".
    Devuelve (texto, hay_update_bool) — el caller decide el color del hint."""
    try:
        import subprocess as _sp
        def g(*a):
            try:
                r = _sp.run(["git", "-C", ROOT] + list(a),
                            capture_output=True, text=True, encoding="utf-8",
                            errors="replace", timeout=4)
                return (r.returncode == 0, (r.stdout or "").strip())
            except Exception:
                return (False, "")
        ok, inside = g("rev-parse", "--is-inside-work-tree")
        if not ok or inside != "true":
            return ("", False)
        _, branch = g("rev-parse", "--abbrev-ref", "HEAD")
        if not branch or branch == "HEAD":
            oks, short = g("rev-parse", "--short", "HEAD")
            branch = ("(detached " + short + ")") if oks and short else "(detached)"
        has_origin = g("rev-parse", "--verify", "--quiet", "origin/main")[0]
        update = False
        # Distro de cliente: registry vacío → es un cliente. Mostramos versión (sha
        # corto) + si hay update vs origin/main (lo que usa `workspace update`).
        is_client = not registry().get("agents")
        def _count(rng):
            okc, out = g("rev-list", "--count", rng)
            try:
                return int(out) if okc else 0
            except ValueError:
                return 0
        if is_client:
            oks, short = g("rev-parse", "--short", "HEAD")
            try:                # versión legible (VERSION) antes que el sha
                _vf = open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()
            except Exception:
                _vf = ""
            ver = ("v" + _vf) if _vf else ("v" + short if oks and short else branch)
            try:                # versión fijada tras una vuelta atrás: no es "update
                import updater  # disponible" — es una espera deliberada
                if updater.hold():
                    return (ver + " · " + _t("hub.ver.held", "versión fijada"), False)
            except Exception:
                pass
            if has_origin and _count("HEAD..origin/main") > 0:
                update = True
                return (ver + " · " + _t("hub.ver.update_available",
                                         "update disponible"), True)
            return (ver + " · " + _t("hub.ver.uptodate", "al día"), False)
        # Equipo: rama + sync vs origin/main (si la rama es main) o solo la rama.
        if branch == "main" and has_origin:
            ahead = _count("origin/main..main")
            behind = _count("main..origin/main")
            if behind > 0:
                return ("main · " + _t("hub.ver.behind_update", "↓{n} update",
                                       n=behind), True)
            if ahead > 0:
                return ("main · " + _t("hub.ver.ahead_unpushed",
                                       "↑{n} sin publicar", n=ahead), False)
            return ("main · " + _t("hub.ver.uptodate", "al día"), False)
        return (branch, False)
    except Exception:
        return ("", False)


def _hub_version_line():
    """La fila coloreada (ANSI) del indicador de versión, lista para imprimir.
    "" si no aplica (no repo / git ausente). El hint de update va en ámbar."""
    txt, update = _hub_version_text()
    if not txt:
        return ""
    # rama/versión en dorado tenue; el separador y el resto en gris; update → ámbar.
    if update:
        # resaltar la cola (update) en ámbar/bold
        if " · " in txt:
            head, tail = txt.split(" · ", 1)
            return f"{DIM}{head}{R}{DK} · {R}{B}{tail}{R}"
        return f"{B}{txt}{R}"
    if " · " in txt:
        head, tail = txt.split(" · ", 1)
        return f"{C}{head}{R}{DK} · {DIM}{tail}{R}"
    return f"{C}{txt}{R}"


# ── LATIDO en el menú: control manual de la cola/heartbeat ──────────────────
# Diseño v2 (2026-06-11, feedback del socio): sección propia AL FONDO del menú —
# orden DIOSES → HERRAMIENTAS → LATIDO, cada una dividida por un separador y
# con su PROPIO renglón de avisos (nada se cuela bajo otra sección).
# Radio-group de verdad: ◄► mueve el FOCO entre auto/manual/off SIN aplicar
# nada; Enter SELECCIONA la opción enfocada (heartbeat.set_mode) y el (o) se
# mueve ahí. Distinción visual: SELECCIONADO = (o) dorado bold (modo aplicado)
# · ENFOCADO = ❮ ❯ (cursor, mismo lenguaje que HERRAMIENTAS) · resto apagado.
# Así se ve "estoy parado en manual pero auto sigue seleccionado hasta Enter".
# Debajo, línea de estado tenue (tag del modo · cola N · next · uso 5h) —
# solo ASCII + `·` (Windows-safe).
#
# Panel lateral derecho con la cola (idea original del socio): EVALUADO Y
# DESCARTADO (2026-06-11). Un layout de 2 columnas obliga a componer altar +
# starfield + centrado por celdas y arriesga la fórmula del clear, el resize
# y Windows (doble-ancho de glifos descuadra márgenes — ya rompió antes); el
# mouse en terminal es frágil cross-platform. La gestión pesada de la cola
# (reorder ▲▼, mouse) YA vive en el dashboard — el banner solo controla el
# modo. Prioridad #1: no romper el TUI.
#
# Falla-suave ABSOLUTA: sin heartbeat.py la sección se omite y el menú queda
# como antes (DIOSES + HERRAMIENTAS); un set_mode fallido solo deja un aviso.
HB_MODES = ("auto", "manual", "off")
HB_TAGS = {"auto": "el cron lanza solo",
           "manual": "el cron solo avisa, tú lanzas",
           "off": "latido apagado"}


def _hb_tags():
    """HB_TAGS en el idioma de la UI (HB_TAGS = la fuente ES)."""
    return {m: _t("hub.hb.tag." + m, tag) for m, tag in HB_TAGS.items()}


def _agent_now(brain, max_age_h=6):
    """Tarea EN VIVO de un agente (<brain>/STATE/now.json — la publica su
    adapter/status). {'task','state'} o None si no hay / viejo / roto.
    Solo la consumen los LAYOUTS alternativos (hublayout) para la lista de
    agentes con estado. Falla-suave absoluta: jamás levanta."""
    try:
        import time
        p = os.path.join(brain or "", "STATE", "now.json")
        if not os.path.isfile(p):
            return None
        if (time.time() - os.path.getmtime(p)) > max_age_h * 3600:
            return None                     # rancio: mejor idle que un status viejo
        d = _read_json(p)
        task = str(d.get("task") or "").strip()
        if not task:
            return None
        return {"task": task.splitlines()[0],
                "state": str(d.get("state") or "working")}
    except Exception:
        return None


def _hb_snapshot():
    """heartbeat.state() o None si heartbeat no existe / truena (falla-suave)."""
    try:
        import heartbeat
        st = heartbeat.state()
        return st if isinstance(st, dict) and st.get("mode") else None
    except Exception:
        return None


def _set_hb_mode(mode):
    """Aplica el modo vía heartbeat.set_mode(). True si quedó guardado."""
    try:
        import heartbeat
        heartbeat.set_mode(mode)
        return True
    except Exception:
        return False


def _latido_status(st, mode=None):
    """Línea de estado bajo el control del latido: tag del modo · cola N ·
    next · uso 5h · pausa. Texto plano (el caller la pinta DIM), solo glifos
    angostos ASCII + `·` (Windows-safe). Cabe en el ancho del banner: si se
    pasa, suelta el `next`. Falla-suave: cualquier problema → ""."""
    try:
        mode = mode or st.get("mode") or "?"
        b = st.get("budget") or {}
        pct = b.get("pct")
        uso = _t("hub.hb.usage5h", "uso 5h {uso}",
                 uso=("?" if pct is None else f"{round(pct)}%"))
        parts = [_hb_tags().get(mode, ""),
                 _t("hub.hb.queue", "cola {n}", n=st.get("count", 0))]
        nxt = st.get("next")
        if nxt and mode != "off":
            nxt = nxt if len(nxt) <= 30 else nxt[:29] + "…"
            parts.append(f"next {nxt}")
        parts.append(uso)
        if b.get("ok") is not True:                  # tope alcanzado o dato desconocido
            parts.append(_t("hub.hb.paused", "presupuesto en pausa"))
        ln = " · ".join(p for p in parts if p)
        if len(ln) > _BLOCK_W and nxt:               # no desbordar el bloque
            ln = " · ".join(p for p in parts if p and not p.startswith("next "))
        return ln
    except Exception:
        return ""


def _motor_summary(agents):
    """Resumen del MOTOR en uso para franja/statusline: con un solo harness
    efectivo entre los agentes activos, su nombre; con varios, `N motores`
    (el detalle por agente vive en la caja AGENTES). Falla-suave → el default
    del harness ('claude-code'), que era el texto fijo de antes."""
    try:
        engs = sorted({(a.get("engine_eff") or a.get("engine") or "").strip()
                       for a in (agents or []) if a.get("active")} - {""})
        if len(engs) == 1:
            return engs[0]
        if engs:
            return _t("hub.franja.engines_n", "{n} motores", n=len(engs))
    except Exception:
        pass
    return "claude-code"


def _hub_agents():
    """(agents, revision) para el hub desde el estado compartido (agent_state).
    Cada entrada conserva el shape histórico (name/display/color/brain/
    tagline/engine/engine_eff/engine_src/active) que consumen layouts y
    drivers; `active` = lanzable. Los averiados llevan `status_label` (lo
    pintan los layouts en lugar de «pronto») y `cause`/`repair`.
    Falla-suave: sin agent_state → lista vacía (jamás agentes inventados)."""
    try:
        import agent_state
        snap = agent_state.snapshot()
    except Exception:
        return [], None
    out = []
    for a in snap.for_hub():
        ok = a.launchable
        out.append({"name": a["name"], "id": a["id"],
                    "display": a["display"],
                    "color": a["color"] or AGENT_COLORS.get(a["name"], "red"),
                    "brain": a["brain"],
                    "tagline": a["tagline"] if ok else (a["cause"] or a["tagline"]),
                    "engine": a["engine_default"] or "claude-code",
                    "engine_eff": a["engine"],
                    "engine_src": a["engine_source"],
                    "status": a["status"],
                    "status_label": "" if ok else agent_state.label(a["status"]),
                    "cause": a["cause"], "repair": a["repair"],
                    "active": ok})
    for p in snap.planned:
        out.append({"name": p, "display": p.capitalize(), "brain": "",
                    "color": AGENT_COLORS.get(p, "red"), "tagline": "",
                    "status": "planned", "active": False})
    return out, snap.revision


def _unavailable_msg(a):
    """Aviso de un agente que el hub NO puede lanzar: su estado real (y cómo
    repararlo) si está registrado pero averiado; «todavía no disponible» solo
    para un planeado. Lo usan Enter y la información (Tab)."""
    if a.get("status") and a.get("status") != "planned":
        return f"{a['display']}: {a.get('status_label') or a['status']}" + (
            f" — {a['repair']}" if a.get("repair") else "")
    return _t("hub.agent.not_yet", "{name} todavía no está disponible.",
              name=a["display"])


def _menu_machinery(tout):
    """Estado + closures de RENDER del recinto: altar, cielo, full_draw/redraw.
    Compartido por los dos drivers de input (_animated_loop_unix y
    _animated_loop_windows): aquí vive TODO lo que pinta y la semántica del menú
    (nav/activate/tick); en los drivers solo vive el mecanismo de teclado y el
    reloj. Misma salida en ambas plataformas."""
    # Agentes del hub DERIVADOS del estado compartido (agent_state, U12/Z13):
    # registrado ≠ lanzable. Un averiado se ve (con su causa) para repararlo,
    # pero active=False → Enter no lo lanza a un exec fallido. La lista se
    # RECONSTRUYE en tick() cuando la revisión del estado cambia (otra ventana
    # cargó/quitó/reparó un agente) — ver _reload_agents.
    try:
        import harnesses as _harn
    except Exception:
        _harn = None
    agents, _agents_rev = _hub_agents()
    NA = len(agents)
    # «Dev» fuera del MENÚ (el socio 2026-10-02) — el panel vive en `workspace
    # dev` (ruteo de __dev__ intacto). «Proyectos» fuera del MENÚ (el socio
    # 2026-10-02) — la app vive en `workspace proyectos`. Las opciones salen
    # del registro CANÓNICO (menu_entries: GitHub siempre, «Dev» gated al
    # dueño/dev, Calendario/Tono/Actualizaciones/Agregar/Terminal) —
    # misma fuente que items().
    opts = [(tok, lbl) for tok, lbl, _tag in menu_entries()]
    # TECLAS RÁPIDAS (las cifras de tus agentes, en su orden): las
    # cifras de los agentes → jump() (drivers).
    JUMP, JKEYS = _jump_map(agents)
    _JUMP_SET = set(JUMP)          # VIVO: _reload_agents lo actualiza en sitio
    hb = _hb_snapshot()                               # snapshot del latido (para el status vivo del layout)
    # LANZADOR (hublayout): el hub oficial y único. Su PERSONALIZACIÓN sale
    # de hublayout.lanzador_pins() — los pins de front y los pintados deben
    # ser LA MISMA lista (cfg_focus indexa ambos).
    try:
        import hublayout as _hlz
    except Exception:
        _hlz = None
    # El id interno del grupo de PERSONALIZACIÓN sigue siendo "latido"
    # (legacy, invisible al socio) para no regar el ruteo. Sin pins el
    # grupo se OMITE (falla-suave).
    def _pins_now():
        """Pins de PERSONALIZACIÓN → [{key,label,value}]. Falla-suave TOTAL:
        cualquier problema → []."""
        try:
            if _hlz is not None:
                return _hlz.lanzador_pins()
            import settings as _st
            return _st.hub_pins_resolved()
        except Exception:
            return []

    def _lang_opts():
        """Opciones de IDIOMA → [(code, nombre_nativo, es_activo)].
        Falla-suave TOTAL: sin i18n → [] (la sección se OMITE, jamás levanta)."""
        try:
            import i18n as _i18n
            active = _i18n.lang()
            return [(c, n, c == active) for c, n in _i18n.available()]
        except Exception:
            return []
    groups = ["dioses", "tools"] + (["latido"] if _pins_now() else [])
    groups.append("idioma")
    # Estado mutable compartido (los drivers lo mutan vía nav/activate/tick):
    #   group índice en `groups` (dioses / tools / latido=CONFIGS) · gsel/asel
    #   selección · cfg_focus pin ENFOCADO en CONFIGS (cursor) · hb_mode/hb_focus
    #   estado legado del latido (lo leen los layouts alternos vía view) · msg
    #   aviso de DIOSES · hb_msg aviso de CONFIGS (cada sección tiene el suyo;
    #   nada se cuela bajo otra) · ph fase de la llama · frame reloj ·
    #   ign_start frame del encendido · BH/row0 geometría.
    _hb0 = (hb or {}).get("mode")
    # con 0 agentes (harness recién separado / descargado) arrancamos en
    # HERRAMIENTAS, no en el altar vacío — ahí está "Agregar agente".
    _g0 = 0 if NA else (groups.index("tools") if "tools" in groups else 0)
    # cursor del cuadro IDIOMA: arranca sobre el idioma ACTIVO.
    try:
        import i18n as _i18n0
        _langs0 = [c for c, _ in _i18n0.available()]
        _lf0 = _langs0.index(_i18n0.lang()) if _i18n0.lang() in _langs0 else 0
    except Exception:
        _lf0 = 0
    S = {"group": _g0, "gsel": 0, "asel": 0, "ph": 0, "msg": "", "hb_msg": "",
         "hb_mode": _hb0, "cfg_focus": 0, "lang_focus": _lf0,
         "hb_focus": HB_MODES.index(_hb0) if _hb0 in HB_MODES else 0,
         "frame": 0, "ign_start": 0, "BH": 0, "row0": 0,
         # LANZADOR: nivel (None = raíz), búsqueda y fila de su lista
         "lz_level": None, "lz_q": "", "lz_sel": 0,
         # indicador de versión abajo-derecha (calculado una vez por sesión, sin red)
         "ver_line": _hub_version_line()}

    def gk():
        return groups[S["group"]]

    # ── El hub se dibuja con el LANZADOR (hublayout.render_lanzador) con los
    #    datos de la sesión y la semántica de teclado de abajo. Falla-suave
    #    ABSOLUTA: sin hublayout / renderer roto → la vista angosta de texto
    #    (responsive_ui), que conserva todas las acciones. ──
    _hl = _hlz
    _laybox = {"lay": None}
    try:
        _laybox["lay"] = _hl.active() if _hl else None
    except Exception:
        _laybox["lay"] = None

    _LAYP = TH
    _LDATA = None
    if _laybox["lay"]:
        for ag in agents:                    # estado vivo (una vez por sesión)
            now = _agent_now(ag.get("brain")) or {}
            ag["task"], ag["state"] = now.get("task", ""), now.get("state", "")
        try:
            _ver = open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()
        except Exception:
            _ver = ""
        _LAYP = TH or types.SimpleNamespace(
            B=B, B2=B2, C=C, WH=WH, DIM=DIM, DK=DK, GREY=GREY, R=R, BO=BO,
            INACTIVE=INACTIVE, INACTIVE_HB=INACTIVE_HB, ERR=ERR, GLYPHS=GL)
        _LDATA = {"agents": agents, "opts": opts, "hb": hb,
                  "hb_modes": HB_MODES, "hb_tags": _hb_tags(),
                  "version": _ver, "version_text": _hub_version_text()[0],
                  # motor REAL en uso: resumen de los bindings efectivos;
                  # cycle_engine lo refresca.
                  "motor": _motor_summary(agents),
                  # teclas de SALTO (1-9 · q): el lanzador las usa al buscar
                  "keys": JKEYS}

    def _lay_lines():
        """Líneas del hub según el layout activo (contrato de hublayout:
        render(data, view, P, w) → list[str], altura estable). El layout
        puede reportar su HIT-MAP (regiones clickeables) en view['hit'];
        se guarda en S['hit'] para que click() hit-testee contra el ÚLTIMO
        frame realmente pintado (resize/degradación incluidos)."""
        view = {"focus": gk(), "gsel": S["gsel"], "asel": S["asel"],
                "hb_mode": S["hb_mode"], "hb_focus": S["hb_focus"],
                "cfg_focus": S["cfg_focus"], "lang_focus": S["lang_focus"],
                # LANZADOR: nivel (None = raíz), búsqueda y fila seleccionada
                "lz_level": S.get("lz_level"), "lz_q": S.get("lz_q", ""),
                "lz_sel": S.get("lz_sel", 0),
                "msg": S["msg"], "hb_msg": S["hb_msg"],
                # ALTO real: el lanzador reparte cabecera/caja/chips en él
                "h": S["term_h"]}
        lines = _laybox["lay"]["render"](_LDATA, view, _LAYP, S["term_w"])
        S["hit"] = tuple(view.get("hit") or ())
        return lines

    def cycle_pin():
        """Enter/espacio en CONFIGS: CICLA el valor del pin ENFOCADO
        (enum → siguiente choice · bool → on/off) y PERSISTE vía
        settings.next_pin_value (valida + guarda + sync de latido.json si
        aplica). Falla-suave ABSOLUTA: set inválido/roto → aviso en
        S['hb_msg'], jamás rompe el recinto. La confirmación vive DENTRO de
        la sección CONFIGS (renglón propio, como el latido de antes)."""
        pins = _pins_now()
        if not pins:
            S["hb_msg"] = ""
            return
        i = S["cfg_focus"] % len(pins)
        p = pins[i]
        try:
            import settings as _st
            newv = _st.next_pin_value(p["key"])
            disp = _st.pin_value_display(p["key"], newv)
            # ui.autostart: además de persistir el bool, reescribe el bloque del
            # greeter del rc (install.set_terminal_autostart) para que el cambio
            # surta efecto en la próxima terminal. Falla-suave: si el rc está
            # editado a mano (no se reconoce el bloque) la preferencia queda
            # guardada igual y lo decimos — jamás truena el recinto.
            if p["key"] == "ui.autostart":
                rc = ""
                try:
                    import install
                    rc = install.set_terminal_autostart(bool(newv)) or ""
                except Exception:
                    rc = ""
                if not rc:
                    S["hb_msg"] = _t("hub.pin.saved_rc",
                                     "{label} → {val} (guardado · ajusta el "
                                     "rc a mano)", label=p["label"], val=disp)
                    return
            S["hb_msg"] = _t("hub.pin.saved", "{label} → {val} (guardado)",
                             label=p["label"], val=disp)
        except Exception:
            S["hb_msg"] = _t("hub.pin.fail", "no pude cambiar «{label}» — queda "
                             "igual", label=p["label"])

    def apply_lang():
        """Enter/espacio en el cuadro IDIOMA: aplica el idioma ENFOCADO
        (i18n.set_lang, persiste ui.lang) y refresca las etiquetas del MENÚ
        para que el hub flipee EN VIVO (el ● del cuadro se mueve solo: lee
        i18n.lang() en cada render). Los tokens del menú NO cambian con el
        idioma → jump/asel siguen válidos; solo se reconstruyen las
        LABELS. Falla-suave ABSOLUTA: cualquier problema → no-op silencioso,
        el hub sigue vivo."""
        nonlocal opts
        try:
            import i18n as _i18n
            langs = _i18n.available()
            code = langs[S["lang_focus"] % len(langs)][0]
            _i18n.set_lang(code)
        except Exception:
            return
        try:                                     # re-pintar el MENÚ en el nuevo idioma
            opts = [(tok, lbl) for tok, lbl, _tag in menu_entries()]
            if _LDATA is not None:
                _LDATA["opts"] = opts
        except Exception:
            pass

    def _plain_lines():
        """Bloque de TEXTO llano (sin layout): agentes y menú numerados. Es
        la red si el renderer del lanzador falla en `--banner`/sin tty."""
        L = ["WORKSPACE", ""]
        for i, a in enumerate(agents):
            L.append("  %s · %s" % (a.get("display") or a.get("name"),
                                    a.get("engine_eff") or a.get("engine") or "?"))
        L.append("")
        for _tok, lbl in opts:
            L.append("  " + lbl)
        return L

    def block_lines():
        """Bloque del hub: las líneas del LANZADOR (misma fuente para el hub
        interactivo y `--banner`). Renderer roto → texto llano."""
        if _laybox["lay"]:
            try:
                return _lay_lines()
            except Exception:
                _laybox["lay"] = None
        return _plain_lines()

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║ NO TOCAR ESTA FÓRMULA DE PANTALLA (costó MUCHO afinarla, 2026-06-08).  ║
    # ║   • clear = "\033[2J\033[3J\033[H"  EN ESTE ORDEN (pantalla→scroll-     ║
    # ║     back→home). El orden inverso (3J antes que 2J) corre el viewport.  ║
    # ║   • redibujar con home + "\033[K" por línea — NUNCA \033[2J a media    ║
    # ║     sesión, que deja basura en Terminal.app.                           ║
    # ║   • ALT-SCREEN (\033[?1049h) SOLO como envoltura en animated_menu      ║
    # ║     (entrar/salir) para BLOQUEAR el scroll. Opt-out                   ║
    # ║     WORKSPACE_NO_ALTSCREEN=1 si una terminal lo odia.                  ║
    # ╚══════════════════════════════════════════════════════════════════════╝
    # (Windows Terminal honra esta MISMA fórmula — el driver Windows la usa tal cual.)
    # Ventana mínima para el hub completo = la caja FIJA del lanzador + su pie
    # (hublayout.lanzador_min_size); por debajo, la vista angosta.
    def _min_size():
        try:
            return _hl.lanzador_min_size(_LDATA)
        except Exception:
            return (40, 20)

    content_w = _min_size()[0]
    S["min_w"] = content_w

    def gsize():
        try:
            ts = os.get_terminal_size(tout.fileno())
            return ts.columns, ts.lines      # ANCHO REAL (centramos a él; ya no forzamos content_w)
        except Exception:
            return max(content_w, 100), 40

    S["term_w"], S["term_h"] = gsize()

    def _narrow_draw(first):
        """RED DE SEGURIDAD — solo si el LANZADOR no se puede dibujar
        (hublayout ausente o su render truena). Texto llano con la semántica
        de grupos (↑↓ sección · ◄► elige): mismas acciones, sin depender de
        hublayout ni de su marco. Una ventana chica NO cae aquí: el lanzador
        se adapta solo (cede wordmark y chips, recorta la caja)."""
        w, h = S['term_w'], S['term_h']
        S['narrow'] = False
        S['compact'] = True
        S['hit'] = ()                 # no stale mouse regions from rich layout
        group = gk()
        rows, selected = [], 0
        mk = lambda on: (GPTR + ' ') if on else '  '   # noqa: E731
        if group == 'dioses':
            selected = S['gsel']
            for i, agent in enumerate(agents):
                rows.append(mk(i == selected) + str(agent.get('display') or agent.get('name'))
                            + ' · ' + str(agent.get('engine_eff') or agent.get('engine') or '?'))
            rows += ['', S.get('msg', '')]
        elif group == 'tools':
            selected = S['asel']
            for i, (_, label) in enumerate(opts):
                rows.append(mk(i == selected) + label)
        elif group == 'latido':
            selected = S['cfg_focus']
            for i, pin in enumerate(_pins_now()):
                rows.append(mk(i == selected) + str(pin.get('label') or pin.get('key', ''))
                            + ' · ' + str(pin.get('value', '')))
            rows += ['', S.get('hb_msg', '')]
        elif group == 'idioma':
            selected = S['lang_focus']
            for i, (_code, name, act) in enumerate(_lang_opts()):
                rows.append(mk(i == selected) + ('● ' if act else '· ') + name)
        title = 'WORKSPACE · ' + {
            'dioses': _t('hub.section.agents', 'AGENTES'),
            'tools': _t('hub.section.menu', 'MENÚ'),
            'latido': _t('hub.section.personalization', 'PERSONALIZACIÓN'),
            'idioma': _t('hub.section.lang', 'IDIOMA · LANGUAGE')}.get(group, group)
        _nav = "↑↓ %s · ◄► %s · Enter %s · q %s" % (
            _t('common.hint.section', 'sección'),
            _t('common.hint.pick', 'elige'),
            _t('common.hint.enter', 'entra'),
            _t('common.hint.quit', 'sale'))
        lines = ['', ' %s%s%s%s' % (C, BO, title, R), '']
        lines += ['   ' + (WH if r.startswith(GPTR) else DIM) + r + R for r in rows]
        lines += ['', ' %s%s%s' % (DIM, _nav, R)]

        def _fit(ln):
            out, used = [], 0
            for tok in __import__('re').split(r'(\x1b\[[0-9;]*m)', ln):
                if tok.startswith('\x1b['):
                    out.append(tok)
                    continue
                for ch in tok:
                    cw = _eaw(ch)
                    if used + cw > max(1, w - 1):
                        return ''.join(out) + R
                    out.append(ch)
                    used += cw
            return ''.join(out)
        lines = [_fit(x) for x in lines[:max(1, h - 1)]]
        tout.write(('\033[2J\033[3J\033[H' if first else '\033[H')
                   + '\r\n'.join('\r\033[K' + x for x in lines) + '\033[J')
        tout.flush()
        S['BH'] = len(lines)
        S['row0'] = 0
        return S['BH']

    def _lay_full_draw(first):
        """Pantalla completa del LANZADOR (2J3JH inicial · home + \\033[K
        después — ver el recuadro de arriba). Renderer roto → vista angosta."""
        try:
            lines = _lay_lines()
        except Exception:
            _laybox["lay"] = None
            return _narrow_draw(first)
        out = "\033[2J\033[3J\033[H" if first else "\033[H"
        row = 0
        for ln in lines:
            out += "\r\033[K" + ln + "\r\n"; row += 1
        bottom_n = max(0, S["term_h"] - row - 1)
        for _ in range(bottom_n):
            out += "\r\033[K\r\n"; row += 1
        if bottom_n:
            out += f"\033[{bottom_n}A"                   # cursor justo tras el bloque
        tout.write(out); tout.flush()
        S["row0"] = 0
        S["BH"] = len(lines)
        return S["BH"]

    def sync_theme():
        nonlocal _LAYP
        import tuitheme
        p = tuitheme.palette()
        if p is globals().get('TH'):
            return False
        globals()['TH'] = p
        for role in ('B','B2','C','WH','DIM','DK','GREY','R','BO','ERR','OK','INACTIVE','INACTIVE_HB'):
            globals()[role] = getattr(p, role)
        globals()['GL'] = p.GLYPHS
        for name, key in (('GPTR','pointer'),('GBL','bracket_l'),('GBR','bracket_r'),('GORN','orn'),('GSEP','sep')):
            globals()[name] = p.GLYPHS[key]
        _LAYP = p
        import theme
        if p.OSC:
            theme.apply_colors(p.OSC)
        else:
            theme.reset()                    # sin OSC: colores de la terminal
        return True

    def full_draw(first=False):
        sync_theme()
        # SIEMPRE el lanzador: en una ventana más chica que su caja él mismo
        # cede (wordmark → compacto → nada · chips → una línea · caja
        # recortada al ancho). La vista de texto llano es solo la red si el
        # renderer no está o truena (antes una ventana chica mostraba el hub
        # VIEJO: marco propio, grupos ↑↓/◄► y «Pantalla completa recomendada»).
        if not _laybox["lay"]:
            return _narrow_draw(first)
        S["narrow"] = False
        S["compact"] = False
        return _lay_full_draw(first)

    def redraw():
        if sync_theme() or S.get("compact"):
            return full_draw(first=False)
        if S.get("narrow"):                          # pantalla angosta = estática
            return
        try:
            lines = _lay_lines()
        except Exception:
            _laybox["lay"] = None                    # renderer roto → vista angosta
            return full_draw(first=False)
        if len(lines) != S["BH"]:                    # altura cambió (defensa) → repintado completo
            return full_draw(first=False)
        tout.write(f"\033[{S['BH']}A")
        for ln in lines:
            tout.write("\r\033[K" + ln + "\r\n")
        tout.flush()

    def check_resize():
        nw, nh = gsize()                             # ¿cambió el tamaño? → re-centra
        if (nw, nh) != (S["term_w"], S["term_h"]):
            S["term_w"], S["term_h"] = nw, nh
            full_draw(first=False)

    def _reload_agents(force=False):
        """Reconstruye la lista de agentes si el estado compartido cambió
        (otra ventana/terminal cargó, quitó, reparó o re-enlazó un agente).
        Conserva la selección por NOMBRE (no por índice) y muta en sitio las
        estructuras que los drivers ya tienen (agents, JUMP, JKEYS).
        Devuelve True si cambió algo."""
        nonlocal NA, _agents_rev
        try:
            import agent_state
            if not force and (_agents_rev is None
                              or not agent_state.changed(_agents_rev)):
                return False
        except Exception:
            return False
        cur = agents[S["gsel"]]["name"] if agents and S["gsel"] < len(agents) else None
        new, rev = _hub_agents()
        if _laybox["lay"]:
            for ag in new:
                now = _agent_now(ag.get("brain")) or {}
                ag["task"], ag["state"] = now.get("task", ""), now.get("state", "")
        agents[:] = new
        _agents_rev = rev
        NA = len(agents)
        names = [a["name"] for a in agents]
        S["gsel"] = names.index(cur) if cur in names else 0
        j, jk = _jump_map(agents)
        JUMP.clear(); JUMP.update(j)
        JKEYS.clear(); JKEYS.update(jk)
        _JUMP_SET.clear(); _JUMP_SET.update(JUMP)
        if _LDATA is not None:
            _LDATA["motor"] = _motor_summary(agents)
        if cur and cur not in names:
            S["msg"] = _t("hub.agent.gone", "{name} ya no está registrado "
                          "(cambió desde otra ventana)", name=cur)
        return True

    def tick():
        """Un paso del reloj (~30fps): resize, agentes cambiados en otra
        ventana y tema cambiado. El lanzador no anima nada."""
        check_resize()
        import time
        # U12: el estado de agentes se revisa cada 2 s (firma barata por stat,
        # sin red/login) — una carga/retiro en otra ventana aparece sin reiniciar.
        if time.monotonic() - S.get("agents_checked_at", 0) >= 2:
            S["agents_checked_at"] = time.monotonic()
            if _reload_agents():
                full_draw(first=False)
        if sync_theme():
            full_draw(first=False)
        S["frame"] += 1

    def _lz():
        """¿El hub se está dibujando con el LANZADOR? (no en la vista
        angosta/vertical de respaldo, que conserva su semántica)."""
        return bool(_laybox["lay"] and not S.get("compact")
                    and _LDATA is not None)

    # ── LANZADOR: una sola lista que se recorre (hublayout.lanzador_items).
    #    Estado propio: lz_level (None = raíz · tools/latido/idioma), lz_q
    #    (búsqueda) y lz_sel (fila). Las ACCIONES son las de siempre: antes
    #    de ejecutar se apunta el grupo/índice de front (gsel/asel/cfg_focus/
    #    lang_focus) y se llama a la misma rutina que usan los demás layouts.
    def _lz_items():
        return _hlz.lanzador_items(_LDATA, S.get("lz_level"),
                                   S.get("lz_q", ""))

    def _lz_reset_sel(prefer=None):
        """Selección al primer seleccionable (o a la fila `prefer`)."""
        its = _lz_items()
        if prefer is not None:
            for i, it in enumerate(its):
                if (it.get("kind"), it.get("idx")) == prefer:
                    S["lz_sel"] = i
                    return
        S["lz_sel"] = _hlz.lanzador_first(its)

    def _lz_cur():
        its = _lz_items()
        i = S.get("lz_sel", 0)
        if 0 <= i < len(its) and its[i].get("kind") in _hlz._LZ_SELECTABLE:
            return its[i]
        S["lz_sel"] = _hlz.lanzador_first(its)
        i = S["lz_sel"]
        return its[i] if 0 <= i < len(its) else {}

    def _lz_point(it):
        """Apunta el estado de front al ítem (para reusar las acciones)."""
        k, i = it.get("kind"), it.get("idx")
        if k == "agent":
            S["group"] = groups.index("dioses"); S["gsel"] = i
        elif k == "opt":
            S["group"] = groups.index("tools"); S["asel"] = i
        elif k == "pin" and "latido" in groups:
            S["group"] = groups.index("latido"); S["cfg_focus"] = i
        elif k == "lang":
            S["group"] = groups.index("idioma"); S["lang_focus"] = i

    def _lz_drill(g):
        S["lz_level"], S["lz_q"] = g, ""
        if g in groups:
            S["group"] = groups.index(g)
        _lz_reset_sel()

    def _lz_activate():
        """Enter en el lanzador: agente → lanza (rutina de siempre) · `›` →
        entra al submenú · opción del menú → la abre · pin → lo cicla ·
        idioma → lo aplica."""
        it = _lz_cur()
        k = it.get("kind")
        if k == "sub":
            _lz_drill(it["idx"])
            return None
        if k not in ("agent", "opt", "pin", "lang"):
            return None
        _lz_point(it)
        return _activate_core()

    def lz_key(ch):
        """Tecla imprimible con el lanzador activo — regla «escribe primero»:
        toda letra/carácter imprimible ESCRIBE en la búsqueda (los atajos de
        una letra ceden). Excepciones con la búsqueda VACÍA: `q` sale y los
        dígitos 1-9 apuntan/lanzan agentes (devuelve False → el driver sigue
        con su ruteo de siempre). ⌫ borra. True = consumida."""
        if not _lz() or not ch:
            return False
        q = S.get("lz_q", "")
        if ch in ("\x7f", "\b", "\x08"):
            if q:
                S["lz_q"] = q[:-1]
                S["msg"] = ""; S["hb_msg"] = ""
                _lz_reset_sel()
            return True
        if not ch.isprintable() or ch in ("\t", "\r", "\n"):
            return False
        if not q and (ch in ("q", "Q") or ch.isdigit() or ch == " "):
            return False
        if len(q) < 40:
            S["lz_q"] = q + ch
            S["msg"] = ""; S["hb_msg"] = ""
            _lz_reset_sel()
        return True

    def tab():
        """Tab en el lanzador: INFORMACIÓN del agente seleccionado (la acción
        `info` de siempre); en una fila `›`, entra. Fuera: no-op."""
        if not _lz():
            return
        it = _lz_cur()
        if it.get("kind") == "agent":
            _lz_point(it)
            agent_info()
        elif it.get("kind") == "sub":
            _lz_drill(it["idx"])

    def back():
        """Esc / ◄ en el lanzador: con búsqueda la limpia; en un submenú
        regresa a la raíz (sobre la fila de ese submenú); en la raíz sin
        búsqueda no hace nada. Fuera del lanzador: no-op (como siempre)."""
        if not _lz():
            return
        S["msg"] = ""; S["hb_msg"] = ""
        if S.get("lz_q"):
            S["lz_q"] = ""
            _lz_reset_sel()
            return
        lvl = S.get("lz_level")
        if lvl:
            S["lz_level"] = None
            S["group"] = groups.index("dioses")
            _lz_reset_sel(prefer=("sub", lvl))

    def _lz_nav(d):
        if d in ("up", "down"):
            S["lz_sel"] = _hlz.lanzador_step(_lz_items(), S.get("lz_sel", 0),
                                             -1 if d == "up" else +1)
            it = _lz_cur()
            if it.get("kind") == "agent":        # el agente apuntado ES gsel
                S["group"] = groups.index("dioses"); S["gsel"] = it["idx"]
                S["ign_start"] = S["frame"]
        elif d == "left":
            it = _lz_cur()
            if it.get("kind") == "agent":        # ‹ motor › — ← = el anterior
                _lz_point(it)
                cycle_engine(-1)
            else:
                back()
        elif d == "right":
            it = _lz_cur()
            if it.get("kind") == "sub":
                _lz_drill(it["idx"])
            elif it.get("kind") == "agent":      # → = el siguiente motor
                _lz_point(it)
                cycle_engine()

    def nav(d):
        """Flechas — misma semántica en ambas plataformas: ↑↓ sube/baja de
        sección (dioses → MENÚ → CONFIGS, con tope), ◄► anterior/siguiente
        dentro de la sección. En CONFIGS ◄► mueve el CURSOR entre pins — el
        valor lo cicla Enter/espacio (activate/cycle).
        LANZADOR: UNA lista — ↑↓ la recorren, ◄ regresa (como Esc) y ► entra
        a una fila `›` o cicla el motor del agente seleccionado."""
        S["msg"] = ""; S["hb_msg"] = ""
        if _lz():
            _lz_nav(d)
            return
        if d == "up":
            S["group"] = max(0, S["group"] - 1)
        elif d == "down":
            S["group"] = min(len(groups) - 1, S["group"] + 1)
        elif d in ("left", "right"):
            step = -1 if d == "left" else +1
            if gk() == "dioses":
                if NA:                                   # 0 agentes → altar vacío, no navegar (evita % 0)
                    S["gsel"] = (S["gsel"] + step) % NA; S["ign_start"] = S["frame"]
            elif gk() == "latido":
                pins = _pins_now()
                if pins:                                 # cursor entre pins (evita % 0)
                    S["cfg_focus"] = (S["cfg_focus"] + step) % len(pins)
            elif gk() == "idioma":
                try:
                    import i18n as _i18n
                    n = max(1, len(_i18n.available()))
                except Exception:
                    n = 2
                S["lang_focus"] = (S["lang_focus"] + step) % n
            else:
                S["asel"] = (S["asel"] + step) % len(opts)

    def activate():
        """Enter. Devuelve nombre/token a lanzar, o None si no se lanza nada
        (urna aún no invocada; CONFIGS: Enter CICLA el pin enfocado). Con el
        LANZADOR, Enter actúa sobre la fila seleccionada de su lista."""
        if _lz():
            return _lz_activate()
        return _activate_core()

    def _activate_core():
        """Enter sobre el grupo/índice enfocado (la semántica de siempre)."""
        if S.get("narrow"):                          # angosto: nada que ver → no lanzar a ciegas
            return None
        if gk() == "dioses":
            if NA == 0:                                  # harness sin agentes
                S["msg"] = _t("hub.agent.none_go_add", "sin agentes — Menú "
                              "› Agregar agente")
                return None
            a = agents[S["gsel"]]
            if a["active"]:
                # revalida contra el estado ACTUAL antes de lanzar: si otra
                # ventana lo retiró/averió, cancelar con aviso (no redirigir).
                try:
                    import agent_state
                    ok, cur, why = agent_state.revalidate(a.get("id") or a["name"], a.get("brain"))
                    if ok and not cur.launchable:
                        ok, why = False, agent_state.label(cur["status"])
                except Exception:
                    ok, why = True, ""
                if ok:
                    return a["name"]
                S["msg"] = _t("hub.agent.not_launched", "{name}: {why} — no se "
                              "lanza (revisa Agentes)", name=a["display"], why=why)
                _reload_agents(force=True)
                return None
            S["msg"] = _unavailable_msg(a)
            return None
        if gk() == "latido":
            cycle_pin()
            return None
        if gk() == "idioma":
            apply_lang()
            return None
        return opts[S["asel"]][0]

    def space():
        """Barra espaciadora — SOLO actúa en CONFIGS (cicla el pin enfocado,
        igual que Enter); en el resto de secciones no-op (no lanza a ciegas)."""
        if S.get("narrow"):
            return
        S["msg"] = ""
        if gk() == "latido":
            cycle_pin()
        elif gk() == "idioma":
            apply_lang()

    def cycle_engine(step=1):
        """Tecla `m` en AGENTES: cicla el HARNESS del agente seleccionado entre
        los instalados (harnesses.cycle) y lo PERSISTE per-máquina (settings
        agentes.<n>.engine — dispatch lo honra al lanzar; el agent.json del
        equipo no se toca, eso es N3). Binding automático: el siguiente Enter
        ya lanza con ese motor. Falla-suave ABSOLUTA: cualquier problema deja
        un aviso en S['msg'] y el recinto sigue vivo."""
        if S.get("narrow") or gk() != "dioses" or not NA:
            return
        a = agents[S["gsel"]]
        if not a.get("active"):
            S["msg"] = _t("hub.agent.not_yet_engine", "{name} todavía no está "
                          "disponible — sin motor que elegir.", name=a["display"])
            return
        if _harn is None:
            S["msg"] = _t("hub.engine.no_selector", "selector de motor no "
                          "disponible (falta harnesses.py)")
            return
        try:
            res = _harn.cycle(a["name"], a.get("engine") or "claude-code",
                              step=step)
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        if not res.get("ok"):
            S["msg"] = _t("hub.engine.change_fail", "no pude cambiar el motor: "
                          "{err}", err=res.get("error", "?"))
            return
        a["engine_eff"], a["engine_src"] = res["engine"], res["source"]
        donde = (_t("hub.engine.saved_local", "guardado per-máquina")
                 if res["source"] == "local"
                 else _t("hub.engine.agent_default", "default del agente"))
        S["msg"] = _t("hub.engine.changed", "motor de {name} ▸ {engine}  "
                      "({where})", name=a["display"], engine=res["engine"],
                      where=donde)
        if _LDATA is not None:                       # refresca el pill/statusline
            _LDATA["motor"] = _motor_summary(agents)

    def jump(ch):
        """CIFRA rápida de un agente (su posición): APUNTA sin lanzar (ya
        apuntado aplican ←→ motor, Tab información y Enter); la MISMA cifra
        otra vez = lanzarlo (confirmar repitiendo — sigue siendo
        instantáneo: «11» abre el agente 1). Devuelve el nombre a lanzar, o
        None (apuntado/sin ítem)."""
        t = JUMP.get(ch)
        if t is None or S.get("narrow"):
            return None
        kind, idx = t
        S["msg"] = ""; S["hb_msg"] = ""
        if kind == "agent" and _lz():
            ya = (S.get("lz_level") is None and not S.get("lz_q")
                  and _lz_cur().get("kind") == "agent"
                  and _lz_cur().get("idx") == idx)
            S["lz_level"], S["lz_q"] = None, ""
            _lz_reset_sel(prefer=("agent", idx))
            S["group"] = groups.index("dioses")
            S["gsel"] = idx; S["ign_start"] = S["frame"]
            return activate() if ya else None
        if kind == "agent":
            ya = (gk() == "dioses" and S["gsel"] == idx)
            S["group"] = groups.index("dioses")
            S["gsel"] = idx; S["ign_start"] = S["frame"]
            if not ya:
                return None                 # 1er toque: APUNTA (no lanza)
            return activate()               # mismo agente otra vez: ENTRA
        return None

    def agent_info():
        """Acción `info` (Tab): DETALLE del agente APUNTADO en la fila
        de aviso — el status en vivo sin lanzarlo ni cambiar de ventana:
        motor efectivo (y su origen), dónde vive el cerebro, tarea viva."""
        if S.get("narrow") or not NA:
            return
        S["group"] = groups.index("dioses")     # el aviso vive en AGENTES
        a = agents[S["gsel"]]
        if not a.get("active"):
            S["msg"] = _unavailable_msg(a)       # su estado real, no «pronto»
            return
        eng = a.get("engine_eff") or a.get("engine") or "?"
        orig = _t("hub.engine.local_override", "override local") \
            if a.get("engine_src") == "local" \
            else _t("hub.engine.agent_default", "default del agente")
        brain = (a.get("brain") or "").replace(os.path.expanduser("~"), "~") \
            or "—"
        now = _agent_now(a.get("brain")) or {}
        tarea = (now.get("task") or "").strip()
        vivo = (_t("hub.agent.now_task", "ahora: {task}", task=tarea) if tarea
                else _t("hub.agent.no_live_task", "sin tarea viva"))
        S["msg"] = _t("hub.agent.info", "{name} ▸ motor {eng} ({orig}) · "
                      "cerebro {brain} · {live}", name=a["display"], eng=eng,
                      orig=orig, brain=brain, live=vivo)

    def click(x, y):
        """Click IZQUIERDO (SGR, 1-based). Hit-test contra las regiones que
        el layout reportó en su último render (S['hit'] — filas 0-based del
        bloque, que en layouts se pinta desde la fila 1 de la pantalla).
        MISMO contrato que el dígito: click = saltar + entrar; en un pin de
        PERSONALIZACIÓN = enfocar + ciclar (lo que haría Enter ahí). Sin
        regiones (clásico / layouts sin hit-map) → no-op, jamás lanza a
        ciegas. Escribiendo en el alta del calendario → no-op (no saltar a
        media captura)."""
        if S.get("narrow"):
            return None
        for (row, x0, x1, kind, idx) in S.get("hit") or ():
            if y - 1 != row or not (x0 <= x - 1 < x1):
                continue
            S["msg"] = ""; S["hb_msg"] = ""
            if kind == "agent":
                # mismo contrato que la tecla: 1er click APUNTA (sin
                # lanzar); click sobre el YA apuntado = lanzarlo
                ya = (gk() == "dioses" and S["gsel"] == idx)
                S["group"] = groups.index("dioses")
                S["gsel"] = idx; S["ign_start"] = S["frame"]
                return activate() if ya else None
            if kind == "opt":
                S["group"] = groups.index("tools")
                S["asel"] = idx
                return activate()
            if kind == "pin" and "latido" in groups:
                S["group"] = groups.index("latido")
                S["cfg_focus"] = idx
                cycle_pin()
            if kind == "lang" and "idioma" in groups:
                S["group"] = groups.index("idioma")
                S["lang_focus"] = idx
                apply_lang()
            if kind == "lz":
                # fila del LANZADOR: un agente se apunta y, ya apuntado, se
                # lanza (contrato de siempre); cualquier otra fila entra /
                # abre / cicla / aplica de un click.
                its = _lz_items()
                if not (0 <= idx < len(its)):
                    return None
                ya = (S.get("lz_sel") == idx)
                S["lz_sel"] = idx
                if its[idx].get("kind") == "agent":
                    _lz_point(its[idx])
                    S["ign_start"] = S["frame"]
                    return activate() if ya else None
                return activate()
            if kind == "crumb":                  # migas de pan = regresar
                back()
            return None
        return None

    return types.SimpleNamespace(S=S, agents=agents, opts=opts, groups=groups,
                                 laybox=_laybox,
                                 block_lines=block_lines,
                                 gsize=gsize, full_draw=full_draw, redraw=redraw,
                                 tick=tick, nav=nav, activate=activate, space=space,
                                 tab=tab, back=back, lz_key=lz_key,
                                 cycle_engine=cycle_engine, jump=jump,
                                 click=click, jkeys=JKEYS,
                                 jump_set=_JUMP_SET)


def _animated_loop_unix(tin, M):
    """Driver Unix/Mac: tty raw + select como reloj (~30fps). La semántica y el
    render viven en M (machinery); aquí SOLO la mecánica de input. Comportamiento
    idéntico al loop original pre-refactor (2026-06-08) — no cambiar sin probar
    en Terminal.app del socio."""
    import termios, tty, select
    fd = tin.fileno(); old = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        while True:
            r, _, _ = select.select([tin], [], [], 0.033)  # ~30fps de refresco (ignición fluida)
            if r:
                ch = _tty_key(tin); act = False
                if ch == "\x1b":
                    a = _esc_tail(tin)      # ESC suelto → None (no congela la animación)
                    if a is None:
                        M.back()                                   # Esc suelto: lanzador → limpia/regresa
                    if a == "A": M.nav("up")                       # ↑ → dioses
                    elif a == "B": M.nav("down")                   # ↓ → herramientas
                    elif a == "D": M.nav("left")                   # ◄
                    elif a == "C": M.nav("right")                  # ►
                    elif isinstance(a, tuple) and a[0] == "mouse":
                        res = M.click(a[1], a[2])                  # click = saltar + entrar
                        if res is not None:
                            return res
                elif M.lz_key(ch):                                 # lanzador: escribe en la búsqueda
                    pass
                elif ch == "\t":
                    M.tab()                                            # Tab → info del agente (lanzador)
                elif ch in ("\r", "\n"):
                    act = True
                elif ch == " ":
                    M.space()                                          # espacio → cicla pin en CONFIGS (no-op fuera)
                elif ch in M.jump_set:
                    res = M.jump(ch)                                   # cifra de un agente: apunta · otra vez entra
                    if res is not None:
                        return res
                elif ch in ("q", "Q", "\x03"):
                    return "__shell__"                                 # q → Terminal normal
                if act:
                    res = M.activate()
                    if res is not None:
                        return res
                M.redraw()
            else:
                M.tick()
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old)   # restaura tty (fórmula simple que funcionaba)


def _animated_loop_windows(M, max_frames=None):
    """Driver Windows: msvcrt para el teclado + time.sleep(0.033) como reloj (mismo
    paso ~30fps que el select de Unix). Las flechas llegan como secuencia de dos
    chars: prefijo '\\x00' o '\\xe0' + letra (H=arriba, P=abajo, K=izq, M=der).
    `max_frames` corta el loop tras N frames sin teclado — SOLO para pruebas
    automatizadas (None en uso real)."""
    import msvcrt, time
    if not _interactive_console():
        return None   # sin consola interactiva (pipe/automation) → fallback estático, no girar a 30fps
    while True:
        if msvcrt.kbhit():
            ch = msvcrt.getwch(); act = False
            if ch in ("\x00", "\xe0"):          # prefijo de tecla especial (flechas)
                a = msvcrt.getwch()
                if a == "H": M.nav("up")                           # ↑ → dioses
                elif a == "P": M.nav("down")                       # ↓ → herramientas
                elif a == "K": M.nav("left")                       # ◄
                elif a == "M": M.nav("right")                      # ►
            elif M.lz_key(ch):                                     # lanzador: escribe en la búsqueda
                pass
            elif ch == "\t":
                M.tab()                                            # Tab → info del agente (lanzador)
            elif ch == "\x1b":
                M.back()                                           # Esc → limpia/regresa (lanzador)
            elif ch in ("\r", "\n"):
                act = True
            elif ch == " ":
                M.space()                                          # espacio → cicla pin en CONFIGS (no-op fuera)
            elif ch in M.jump_set:
                res = M.jump(ch)                                   # cifra de un agente: apunta · otra vez entra
                if res is not None:
                    return res
            elif ch in ("q", "Q", "\x03"):
                return "__shell__"                                 # q → Terminal normal
            if act:
                res = M.activate()
                if res is not None:
                    return res
            M.redraw()
        else:
            time.sleep(0.033)                   # reloj: mismo paso que select(0.033) en Unix
            M.tick()
            if max_frames is not None and M.S["frame"] >= max_frames:
                return None


def _animated_menu_windows(max_frames=None):
    """Altar en Windows: render a sys.stdout (no hay /dev/tty; el ANSI ya quedó
    habilitado arriba con os.system("")). Misma fórmula de pantalla que en Mac —
    Windows Terminal la honra tal cual. Cualquier excepción la captura el caller
    (animated_menu) y degrada al picker estático."""
    import msvcrt  # noqa: F401 — si no hay consola Windows real, truena aquí (→ fallback)
    if not _interactive_console():
        return None   # $PROFILE cargado en pipe/automation: no pintar ni animar nada
    tout = sys.stdout
    M = _menu_machinery(tout)
    alt = not os.environ.get("WORKSPACE_NO_ALTSCREEN")    # buffer alterno = bloquea scroll (opt-out)
    try:
        if alt:
            tout.write("\033[?1049h\033[?25l"); tout.flush()
        M.full_draw(first=True)
        return _animated_loop_windows(M, max_frames)
    finally:
        if alt:
            tout.write("\033[?25h\033[?1049l")  # restaura cursor + buffer normal
        tout.write(R); tout.flush()             # nunca dejar atributos ANSI colgados


def animated_menu(it, rows=None):
    """El hub interactivo: el LANZADOR (hublayout.render_lanzador) — una
    lista de agentes y secciones que se filtra al escribir. Enter elige.
    Devuelve nombre/token o None (`rows` se ignora: compatibilidad).
    El render es compartido (_menu_machinery); el input es por plataforma: Unix usa
    termios/tty/select sobre /dev/tty, Windows usa msvcrt sobre stdout. Cualquier
    falla devuelve None ⇒ main() cae al banner estático + run_picker."""
    if os.environ.get("WORKSPACE_NO_ANIM") or not _ui_setting_on("anim"):
        return None
    if sys.platform == "win32":
        try:
            return _animated_menu_windows()
        except Exception:
            return None                          # degrada con gracia al picker simple
    try:
        import termios, tty, select  # noqa: F401 — sin modo raw no hay altar
        # binario sin buffer: select() (reloj del loop y _esc_tail) ve TODO lo pendiente
        tin = open("/dev/tty", "rb", buffering=0); tout = open("/dev/tty", "w")
    except Exception:
        return None
    alt = not os.environ.get("WORKSPACE_NO_ALTSCREEN")    # buffer alterno = bloquea scroll (opt-out)
    # MOUSE SGR (mismo combo probado del pane del split — panel.py): clicks
    # como eventos \033[<b;x;y(M|m) → click = saltar + entrar. Costo honesto:
    # con el reporting activo, seleccionar texto en el hub pide Option/Shift+
    # arrastre (como en el pane). Opt-out: WORKSPACE_NO_MOUSE=1. Se revierte
    # SIEMPRE en el finally — jamás se hereda al agente lanzado.
    mouse = not os.environ.get("WORKSPACE_NO_MOUSE")
    try:
        M = _menu_machinery(tout)
    except Exception:
        return None
    try:
        if alt:
            tout.write("\033[?1049h\033[?25l"); tout.flush()   # buffer alterno (sin scrollback) + oculta cursor
        if mouse:
            tout.write("\033[?1000h\033[?1006h"); tout.flush() # clicks SGR (igual que panel.py)
        M.full_draw(first=True)
        return _animated_loop_unix(tin, M)
    except Exception:
        return None
    finally:
        if mouse:
            tout.write("\033[?1000l\033[?1006l"); tout.flush() # mouse SIEMPRE off al salir
        if alt:
            tout.write("\033[?25h\033[?1049l"); tout.flush()   # restaura cursor + buffer normal (con su scrollback)


def _update_available(timeout=12):
    """¿Hay actualización del harness? Compara local vs remoto SIN bloquear.
    Hace `git fetch` y compara HEAD con origin/<rama actual>. Devuelve un dict:
      {ok:True, behind:N, branch, commits:[(sha, subject)…]} si hay update (N>0),
      {ok:True, behind:0, branch} si está al día,
      {ok:False, reason:"…"} si no se pudo verificar (sin git/remote/red).
    Fail-open SIEMPRE: cualquier fallo → ok:False con razón suave (nunca lanza).
    Cliente (distro) degrada igual: compara contra SU remoto; sin remoto/red → suave."""
    try:
        if not os.path.isdir(os.path.join(ROOT, ".git")):
            return {"ok": False, "reason": _t("cli.upd.reason.not_git",
                                              "no es repo git (instalación por sync)")}
        rc, remotes, _ = _git(ROOT, "remote", timeout=8)
        if rc != 0 or not remotes:
            return {"ok": False, "reason": _t("cli.upd.reason.no_remote",
                                              "sin remote configurado")}
        rc, branch, _ = _git(ROOT, "rev-parse", "--abbrev-ref", "HEAD", timeout=8)
        if rc != 0 or not branch or branch == "HEAD":
            return {"ok": False, "reason": _t("cli.upd.reason.detached",
                                              "rama no determinable (HEAD suelto)")}
        # fetch SOLO esa rama (no bloquea el resto si falla)
        rc, _, err = _git(ROOT, "fetch", "--quiet", "origin", branch, timeout=timeout)
        if rc != 0:
            low = (err or "").lower()
            if any(k in low for k in ("could not resolve", "unable to access",
                                      "timeout", "connection", "offline")):
                return {"ok": False, "reason": _t("cli.upd.reason.offline",
                                                  "sin conexión con origin (¿offline?)")}
            return {"ok": False, "reason": _t("cli.upd.reason.unverified",
                                              "no se pudo verificar updates")}
        rc, cnt, _ = _git(ROOT, "rev-list", "--count", "HEAD..origin/%s" % branch, timeout=8)
        if rc != 0:
            return {"ok": False, "reason": _t("cli.upd.reason.no_compare",
                                              "no se pudo comparar con origin")}
        try:
            behind = int(cnt)
        except ValueError:
            behind = 0
        commits = []
        if behind > 0:
            rc, log, _ = _git(ROOT, "log", "--format=%h\x1f%s", "-30",
                              "HEAD..origin/%s" % branch, timeout=10)
            if rc == 0 and log:
                for line in log.splitlines():
                    parts = line.split("\x1f", 1)
                    if len(parts) == 2:
                        commits.append((parts[0], parts[1]))
        return {"ok": True, "behind": behind, "branch": branch, "commits": commits}
    except FileNotFoundError:
        return {"ok": False, "reason": _t("cli.upd.reason.no_git",
                                          "git no está instalado")}
    except Exception as e:
        return {"ok": False, "reason": "%s" % e}


def _offer_update(interactive):
    """Tras las fases del doctor: chequea update y (si hay y es interactivo) lo
    ofrece. NO bloquea: si no se puede verificar, avisa suave y sigue. En NO
    interactivo (CI/instalación) NUNCA promptea — a lo mucho reporta que hay update.
    Devuelve el rc de cmd_update si se ejecutó, o None si no se actualizó."""
    print(f"\n{DIM}  " + _t("cli.offer.searching",
                            "Buscando actualizaciones del harness…") + f"{R}")
    info = _update_available()
    if not info.get("ok"):
        print(f"  {DIM}" + _t("cli.offer.unverified", "· no se pudo verificar "
                               "updates ({reason}) — sin problema, sigues como "
                               "estás.", reason=info.get('reason', '?')) + f"{R}")
        return None
    if info["behind"] <= 0:
        print(f"  {C}·{R} {DIM}" + _t("cli.offer.uptodate", "estás al día (rama "
                                       "{branch}).", branch=info['branch']) + f"{R}")
        return None

    n = info["behind"]
    _avail = (_t("cli.offer.available_one", "↓ hay 1 actualización disponible")
              if n == 1 else
              _t("cli.offer.available_many", "↓ hay {n} actualizaciones "
                 "disponibles", n=n))
    print(f"  {B}{_avail}{R} "
          f"{DIM}(" + _t("cli.repo.branch", "rama {branch}", branch=info['branch'])
          + f"):{R}")
    for sha, subj in info["commits"][:12]:
        print(f"      {C}{sha}{R}  {subj}")
    if n > len(info["commits"][:12]):
        print(f"      {DIM}" + _t("cli.offer.more", "… y {n} más", n=n - 12) + f"{R}")

    if not interactive:
        # CI / instalación / pipe: NUNCA promptear. Solo informar.
        print(f"  {DIM}" + _t("cli.offer.run_update", "· corre `workspace update` "
                               "para aplicarla.") + f"{R}")
        return None

    try:
        ans = input(f"\n  {C}" + _t("cli.offer.prompt", "¿Actualizar ahora? [s/N]")
                    + f"{R} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if ans not in ("s", "si", "sí", "y", "yes"):
        print(f"  {DIM}" + _t("cli.offer.declined", "· ok, no actualizo. Cuando "
                               "quieras: `workspace update`.") + f"{R}")
        return None
    print()
    # aplica la actualización (misma lógica que `workspace update`), SIN volver a
    # correr el doctor (--no-check) — ya venimos del doctor; evita recursión/loop.
    return cmd_update(["--no-check"])


def _doctor_submenu():
    """«Actualizaciones» en el hub (ex-«Doctor»): un solo punto de entrada
    (decisión del socio 2026-06-25: Doctor y Actualizar separados confunden).
    Desde 2026-10-02 la pantalla `actualizaciones_tui` corre el flujo ENTERO
    en vivo (pasos ✓/●/⚠/✗, progreso, resumen y pendientes — estilo
    WORKSPACE) y devuelve None al terminar. Devuelve un token SOLO cuando no
    puede correrlo ahí (p. ej. el motor del doctor no carga): entonces AQUÍ
    se rutea al camino clásico de terminal (cmd_doctor/cmd_update).
    Falla-suave doble: sin TTY (CI/pipe) cae al diagnóstico de solo-lectura;
    sin la pantalla (módulo roto) cae al submenú de texto de antes."""
    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        return cmd_doctor(["--check"])            # no-interactivo → nunca promptea
    tok = None
    try:
        import actualizaciones_tui
        tok = actualizaciones_tui.run(version_text=_hub_version_text()[0])
    except Exception:
        # pantalla no disponible → el submenú plano de siempre (jamás crashea)
        _o1 = _t("actualizaciones.fallback.o1", "Revisar nomás")
        _o2 = _t("actualizaciones.fallback.o2", "Revisar y reparar")
        _o3 = _t("actualizaciones.fallback.o3", "Actualizar todo")
        print(f"\n  {B}{_t('actualizaciones.fallback.header', 'Actualizaciones')}{R} "
              f"{DIM}{_t('actualizaciones.fallback.q', '— ¿qué quieres hacer?')}{R}\n")
        print(f"    {C}1{R}  {_o1:<17}{DIM}{_t('actualizaciones.fallback.o1d', '— diagnóstico, no toca nada')}{R}")
        print(f"    {C}2{R}  {_o2:<17}{DIM}{_t('actualizaciones.fallback.o2d', '— arregla hooks, launchers, tema…')}{R}")
        print(f"    {C}3{R}  {_o3:<17}{DIM}{_t('actualizaciones.fallback.o3d', '— trae lo nuevo + repara (recomendado)')}{R}")
        print(f"    {C}q{R}  {_t('actualizaciones.fallback.back', 'Volver')}\n")
        try:
            ans = input(f"  {C}{_t('actualizaciones.fallback.prompt', 'Opción [1]:')}{R} ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print(); return None
        tok = {"q": None, "volver": None, "salir": None,
               "3": "update", "2": "repair"}.get(ans, "check")
    if tok == "update":
        return cmd_update([])                     # pull harness+cerebros y REPARA (self-heal)
    if tok == "repair":
        return cmd_doctor([])                     # fases que REPARAN + ofrece update al final
    if tok == "check":
        return cmd_doctor(["--check"])            # solo lectura, lo seguro
    return None                                   # volver al hub sin tocar nada


def cmd_doctor(args):
    """`workspace doctor` — instalador-reparador por fases (idempotente). AL FINAL,
    si es interactivo, ofrece la actualización del harness si hay una disponible
    (fusión Doctor+Actualizar — un solo punto de entrada en el hub).
    `workspace doctor --check` solo diagnostica (tabla de salud, no escribe nada).
    `workspace doctor --from-update` corre las fases SIN ofrecer update (lo invoca
    `workspace update` internamente → evita recursión)."""
    import doctor
    args = list(args or [])
    from_update = "--from-update" in args
    doctor_args = [a for a in args if a != "--from-update"]
    rc = doctor.main(doctor_args)
    # W-F11: `--check` es diagnóstico LOCAL — buscar updates hace `git fetch`,
    # así que solo con verificación remota explícita (--remote/--fetch).
    local_only = (("--check" in doctor_args or "-c" in doctor_args)
                  and not ("--remote" in doctor_args or "--fetch" in doctor_args))
    if local_only and not from_update:
        print(f"\n  {DIM}" + _t("cli.doctor.local_only", "· updates del harness: "
                                "sin consultar remoto (diagnóstico local). "
                                "`workspace doctor --check --remote` o "
                                "`workspace update` para verificarlo.") + f"{R}")
    # update-offer: solo fuera del flujo de `workspace update` (anti-recursión).
    if not from_update and not local_only:
        try:
            _offer_update(interactive=sys.stdin.isatty() and sys.stdout.isatty())
        except Exception as e:
            # fail-open absoluto: el doctor JAMÁS se rompe por el chequeo de update.
            print(f"  {DIM}" + _t("cli.doctor.update_skipped", "· chequeo de "
                                   "update omitido ({err}).",
                                   err=type(e).__name__) + f"{R}")
    return rc


def cmd_repair(args=None):
    """`workspace repair` (alias `fix`) — subset RÁPIDO del doctor: re-renderiza
    SOLO el bloque `hooks` de cada cerebro registrado (modo fix), idempotente.

    Es la herramienta para que "un update jamás deje hooks stale": un `git pull`
    o branch-switch que renombró un hook o sumó un listener en events.py deja
    settings.local.json desincronizado y NADA lo re-renderiza — `workspace repair`
    lo recablea en segundos. Salta prereqs/siblings/secrets/budget/skill-gating
    (eso es trabajo del doctor completo). NUNCA toca `permissions`/`theme`/
    `statusLine`: solo el bloque `hooks` gestionado (render_hooks_only, la misma
    fuente única que usan install y doctor). Exit 0 salvo error duro de entorno.

    Reusa doctor.build_ctx() y la misma iteración de cerebros del doctor."""
    import doctor
    import install
    list(args or [])
    # Ajustes registrados pendientes (migrate.py). `repair` es lo que el
    # auto-update lanza tras traer código nuevo — también el de versiones
    # anteriores al actualizador nuevo —, así una máquina que se actualizó con
    # código viejo igual recibe sus ajustes con el código nuevo.
    try:
        import migrate
        if migrate.has_runnable_pending():
            line = migrate.summary_line(migrate.run_pending())
            if line:
                print(f"  {line}")
    except Exception:
        pass
    try:
        ctx = doctor.build_ctx()
    except Exception as e:
        print(f"  {B}⚠{R} {DIM}"
              + _t("cli.repair.registry_fail", "no pude leer el registry de "
                   "agentes ({err}) — corre `workspace doctor`",
                   err=f"{type(e).__name__}: {e}") + f"{R}")
        return 0
    brains = doctor._resolved_brains(ctx)
    if not brains:
        print(f"  {DIM}" + _t("cli.repair.none", "No hay cerebros resueltos que "
                               "recablear. Corre `workspace doctor` para "
                               "resolverlos.") + f"{R}")
        return 0
    done, failed = [], []
    for a in ctx["agents"]:
        name, brain = a["name"], a["brain"]
        if not (brain and os.path.isdir(brain)):
            continue
        try:
            install.render_hooks_only(a["cfg"], brain)        # RMW de hooks (fuente única P0-3)
            done.append(name)
        except Exception as e:
            failed.append(f"{name} ({type(e).__name__})")
    print(f"  {C}WORKSPACE repair{R} {DIM}— "
          + _t("cli.repair.head", "hooks recableados (settings.local.json)")
          + f"{R}")
    line = f"  {C}✓{R} " + _t("cli.repair.done", "{n} cerebro(s): {names}",
                               n=len(done), names=', '.join(done) or '—')
    if failed:
        line += f"   {B}⚠{R} " + _t("cli.repair.failed", "{n} con error: {names}",
                                    n=len(failed), names=', '.join(failed))
    print(line)
    return 0


def _oldest_supported_python():
    """[[comando]] del Python 3.9 de esta máquina si existe (python3.9 o el
    lanzador `py` de Windows), o []. Solo para el gate de release del equipo."""
    import shutil
    for cand in (["python3.9"], ["py", "-3.9"], ["py", "-V:3.9"]):
        if not shutil.which(cand[0]):
            continue
        try:
            r = subprocess.run(cand + ["-c", "import sys; print(sys.version_info[:2])"],
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=20)
            if r.returncode == 0 and "(3, 9)" in (r.stdout or ""):
                return [cand]
        except Exception:
            continue
    return []


def _release_gate(ref, dist=None):
    """(versión, [problemas]) para publicar `ref` a clientes. Problemas = cosas
    que bloquean: VERSION ausente o no SemVer, sin sección en CHANGELOG.md /
    CHANGELOG.en.md, el README público (dist/README.md) sin las novedades de
    ESTA versión en los dos idiomas, o la misma versión ya publicada (tag
    v<ver> en el distro). Lectura pura.

    Por qué el README: es la portada que ve quien llega al repo público. Si
    cada release no lo toca, se queda contando una versión vieja (pasó: decía
    que las actualizaciones no eran opcionales cuando ya lo eran)."""
    import re as _re
    probs = []

    def show(path):
        r = subprocess.run(["git", "-C", ROOT, "show", "%s:%s" % (ref, path)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace")
        return r.stdout if r.returncode == 0 else None

    ver = (show("VERSION") or "").strip()
    if not _re.match(r"^\d+\.\d+\.\d+$", ver):
        probs.append("VERSION debe ser un número X.Y.Z (hoy: %r)." % ver)
        return ver, probs
    log = show("CHANGELOG.md") or ""
    if not _re.search(r"^## v?%s\b" % _re.escape(ver), log, _re.M):
        probs.append("CHANGELOG.md no tiene la sección `## %s` — describe qué cambia "
                     "para el usuario antes de publicar." % ver)
    log_en = show("CHANGELOG.en.md") or ""
    if not _re.search(r"^## v?%s\b" % _re.escape(ver), log_en, _re.M):
        probs.append("CHANGELOG.en.md no tiene la sección `## %s` — los clientes en "
                     "inglés también leen las novedades." % ver)
    readme = show("dist/README.md") or ""
    v = _re.escape(ver)
    for head, lang in ((r"^### What's new in v%s\s*$" % v, "What's new in v%s" % ver),
                       (r"^### Novedades de la v%s\s*$" % v, "Novedades de la v%s" % ver)):
        if not _re.search(head, readme, _re.M):
            probs.append("el README público (dist/README.md) no tiene `### %s` — "
                         "actualízalo con lo nuevo (y revisa que el resto siga siendo "
                         "cierto) antes de publicar." % lang)
    if dist and os.path.isdir(os.path.join(dist, ".git")):
        r = subprocess.run(["git", "-C", dist, "rev-parse", "-q", "--verify",
                            "refs/tags/v%s" % ver], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode == 0:
            probs.append("la v%s ya se publicó — sube VERSION (y su sección del "
                         "CHANGELOG) antes de otro release." % ver)
    return ver, probs


RELEASE_CHECKLIST = "runbooks/publicar-release.md"


def _release_checklist_ok(args, stdin=None):
    """Lo que se publica le llega solo a cada cliente: nadie publica sin haber hecho
    el checklist de `runbooks/publicar-release.md` (suite, transición, cliente real,
    motores). `--checklist-ok` lo confirma (scripts/agentes que ya lo hicieron); en
    una terminal se pregunta; sin terminal y sin el flag, se niega."""
    if "--checklist-ok" in args:
        return True
    stdin = stdin or sys.stdin
    print(f"  {B}Antes de publicar:{R} sigue {RELEASE_CHECKLIST} —")
    print(f"  {DIM}suite completa · transición desde las versiones que tienen los clientes · "
          f"cliente real (su install + su `workspace update`) · borrar e instalar de cero · "
          f"motores si tocaste permisos/hooks/barras.{R}")
    try:
        interactive = stdin.isatty()
    except Exception:
        interactive = False
    if not interactive:
        print("  ✗ No publico sin confirmar el checklist: vuelve a correr con --checklist-ok "
              "cuando lo hayas hecho.")
        return False
    try:
        ans = input("  ¿Hiciste todo el checklist? [s/N]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        ans = ""
    if ans in ("s", "si", "sí", "y", "yes"):
        return True
    print(f"  {DIM}Cancelado: no se publicó nada.{R}")
    return False


def cmd_release(args):
    """`workspace release [mensaje] [--ref REF] [--dist RUTA] [--dry-run] [--checklist-ok]` — corta y
    PUBLICA la distribución EXTERNA en UN comando: make-dist DESDE `stable` (committeado,
    determinista) → al repo de distribución (workspace-harness) → commit + push. El push
    lo dispara el socio al correr esto (es su acción, no automática). Solo del repo de
    EQUIPO (necesita make-dist.sh).

    El build SIEMPRE sale de `stable` por default (nunca del WIP de la rama actual), así
    los clientes nunca reciben la punta de desarrollo de `main` por accidente. Override
    para pruebas: `--ref <branch/commit/tag>`.

    ⚠ Esto va a los CLIENTES externos (workspace-harness). Para publicar al EQUIPO
    (las ramas main + stable de este repo) usa `workspace publish`."""
    import subprocess
    script = os.path.join(ROOT, "make-dist.sh")
    if not os.path.isfile(script):
        print("WORKSPACE: `release` no disponible (no es el repo de equipo).")
        return 1
    dry = "--dry-run" in args
    # make-dist.sh corre con bash; en Windows sin Git-for-Windows en el PATH el
    # subprocess.call de abajo tronaba con FileNotFoundError crudo. Guard temprano
    # con mensaje accionable (mismo tono que los demás guards de release). En
    # dry-run no se ejecuta bash → no se exige.
    import shutil
    if not dry and not shutil.which("bash"):
        print("WORKSPACE: `release` necesita `bash` (corre make-dist.sh) y no está "
              "en el PATH.")
        print("  En Windows: instala Git for Windows y añade su bash al PATH")
        print(r"  (suele vivir en C:\Program Files\Git\bin\bash.exe).")
        return 1
    ref = "stable"
    if "--ref" in args:
        try:
            ref = args[args.index("--ref") + 1]
        except IndexError:
            print("WORKSPACE: --ref requiere un branch/commit/tag.")
            return 2
    dist = os.environ.get("WORKSPACE_DIST") or os.path.join(
        os.path.expanduser("~"), "Desktop", "workspace-harness")
    if "--dist" in args:
        try:
            dist = os.path.expanduser(args[args.index("--dist") + 1])
        except IndexError:
            pass
    # mensaje posicional: ignora los valores de --ref/--dist
    skip = set()
    for flag in ("--ref", "--dist"):
        if flag in args:
            skip.add(args.index(flag) + 1)
    msg = next((a for i, a in enumerate(args)
                if not a.startswith("-") and i not in skip), "") or "release"
    if not os.path.isdir(os.path.join(dist, ".git")):
        print(f"WORKSPACE: no encuentro el repo de distribución (git) en {dist}.")
        print("  Clónalo una vez:  gh repo clone <tu-org>/workspace-harness "
              f'"{dist}"')
        print("  o pásalo:  workspace release --dist /ruta/workspace-harness")
        return 1

    # SEGURIDAD: el ref debe existir localmente o no construimos nada determinista.
    sha = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", ref],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
    if sha.returncode != 0:
        print(f"WORKSPACE: el ref `{ref}` no existe localmente — no construyo.")
        if ref == "stable":
            print("  El repo de equipo necesita la rama `stable` (promueve con "
                  "`workspace publish`).")
        return 1
    sha = sha.stdout.strip()

    def run(cmd, cwd=None):
        print(f"  {DIM}$ {' '.join(cmd)}{R}")
        return 0 if dry else subprocess.call(cmd, cwd=cwd)

    # Aviso NO bloqueante: stable detrás de main (commits en main que stable no tiene).
    if ref == "stable":
        behind = subprocess.run(
            ["git", "-C", ROOT, "rev-list", "--count", "stable..main"],
            capture_output=True, text=True, encoding="utf-8", errors="replace")
        if behind.returncode == 0:
            n = behind.stdout.strip()
            if n.isdigit() and int(n) > 0:
                print(f"  {B}⚠ stable está {n} commits detrás de main{R} — si querías "
                      "incluir eso, corre `workspace publish`/promueve antes.")

    # El build sale del ref committeado (stable), no del working tree → determinista.
    # No auto-commiteamos: solo avisamos si hay cambios sin commitear.
    dirty = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace").stdout.strip()
    if dirty:
        print(f"  {DIM}Tienes cambios sin commitear (no afectan al release; "
              f"el release sale de `{ref}`).{R}")

    # GATE de versión (patrón Omarchy/Try Omarchy): cada release lleva número
    # nuevo y su sección en el CHANGELOG — es lo que el cliente ve en
    # `workspace version` y en la pantalla Actualizaciones.
    ver, problems = _release_gate(ref, dist)
    if problems:
        print(f"  {B}✗ El release no está listo:{R}")
        for pr in problems:
            print(f"    · {pr}")
        return 1
    if not dry and not _release_checklist_ok(args):
        return 1
    print(f"  {B}Construyendo distro v{ver} desde `{ref}` ({sha})…{R}")
    env = dict(os.environ, DIR=dist)
    print(f"  {DIM}$ DIR={dist} bash make-dist.sh {ref}{R}")
    if not dry and subprocess.call(["bash", script, ref], env=env):
        print("WORKSPACE: make-dist falló (¿el gate anti-fuga? revisa arriba)."); return 1
    # El árbol que recibirá el CLIENTE (sin tests ni herramientas de equipo)
    # tiene que arrancar: es el mismo selftest que corre su actualizador.
    # Con TU Python y, si está instalado, con el más viejo que soportamos (3.9):
    # un cliente con 3.9 es justo quien rompería una sintaxis nueva.
    if not dry and os.path.isfile(os.path.join(dist, "selftest.py")):
        for py in [[sys.executable]] + _oldest_supported_python():
            if subprocess.call(py + [os.path.join(dist, "selftest.py")]) != 0:
                print("WORKSPACE: el distro NO pasa su selftest con %s (arriba el "
                      "detalle) — no publico algo que no arranca en el cliente."
                      % " ".join(py)); return 1
    run(["git", "-C", dist, "add", "-A"])
    if dry:
        print(f"  {DIM}$ git -C {dist} commit -m 'release v{ver} ({sha})'{R}")
    else:
        # H3: `git commit` con nada staged sale rc!=0 IGUAL que un commit que
        # falla de verdad (identidad git / hook). Antes ambos caían al push, y un
        # push "up-to-date" reportaba "✓ publicada" con el distro VIEJO.
        # `diff --cached --quiet`: rc 0 = nada staged (no-op benigno) · rc 1 = hay
        # cambios para commitear.
        if subprocess.call(["git", "-C", dist, "diff", "--cached", "--quiet"]) == 0:
            print(f"  {DIM}El distro no cambió desde el último release — nada "
                  f"nuevo que publicar.{R}")
        elif subprocess.call(["git", "-C", dist, "commit", "-m",
                              f"release v{ver} ({sha})"]) != 0:
            print(f"\n  ✗ El commit del distro FALLÓ (identidad git / hook); "
                  f"no publico un release a medias.")
            return 1
    # Etiqueta v<versión> en el distro y en el repo de equipo (local): así
    # cualquiera sabe qué código corresponde a la versión que ve un cliente.
    run(["git", "-C", dist, "tag", "-a", f"v{ver}", "-m", f"Workspace v{ver}"])
    if not dry:
        subprocess.call(["git", "-C", ROOT, "tag", "-a", f"v{ver}", ref,
                         "-m", f"Workspace v{ver}"],
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    rc = run(["git", "-C", dist, "push", "--follow-tags"])
    if dry:
        print(f"\n  {DIM}(dry-run: no se ejecutó nada){R}")
    elif rc == 0:
        print(f"\n  {C}✓ Distribución publicada{R} (v{ver} · {sha}). "
              "Los clientes la reciben con `workspace update`.")
    else:
        print(f"\n  ✗ El push falló (credenciales/red).")
    return rc


def cmd_publish(args):
    """`workspace publish [--dry-run]` — publica el repo de EQUIPO en UN comando:
    `git push origin main stable` (las dos ramas del equipo). El equipo lo recibe
    con `workspace update`. Solo del repo de EQUIPO (necesita make-dist.sh).

    ⚠ Esto es para el EQUIPO. Para CLIENTES externos (workspace-harness) usa
    `workspace release`."""
    import subprocess
    script = os.path.join(ROOT, "make-dist.sh")
    if not os.path.isfile(script):
        print("WORKSPACE: `publish` no disponible (no es el repo de equipo).")
        return 1
    dry = "--dry-run" in args

    def run(cmd, cwd=None):
        print(f"  {DIM}$ {' '.join(cmd)}{R}")
        return 0 if dry else subprocess.call(cmd, cwd=cwd)

    # Las dos ramas del repo de equipo deben existir localmente.
    have = subprocess.run(["git", "-C", ROOT, "branch", "--format=%(refname:short)"],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace").stdout.split()
    missing = [b for b in ("main", "stable") if b not in have]
    if missing:
        print(f"WORKSPACE: faltan ramas locales: {', '.join(missing)}. "
              "El repo de equipo necesita `main` y `stable`.")
        return 1

    # Working tree sucio → avisar, no commitear a ciegas (decide el socio).
    dirty = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace").stdout.strip()
    if dirty:
        print(f"  {B}⚠ Hay cambios sin commitear.{R} {DIM}`publish` solo empuja lo "
              f"ya commiteado; commitea (o stashea) antes de publicar.{R}")

    rc = run(["git", "-C", ROOT, "push", "origin", "main", "stable"])
    if dry:
        print(f"\n  {DIM}(dry-run: no se ejecutó nada){R}")
    elif rc == 0:
        print(f"\n  {C}✓ Publicado al equipo{R} (main + stable). "
              "El equipo lo recibe con `workspace update`.")
        print(f"  {DIM}(Para clientes externos es `workspace release`.){R}")
    else:
        print(f"\n  ✗ El push falló (credenciales/red).")
    return rc


# ──────────────────────────────────────────────────────────────────────────
# Flujo de ramas (feature → main → stable). Comandos que le ahorran tecleo al
# socio PERO imprimen CADA git que corren (requisito: que vea el git real mientras
# lo aprende). Mismo criterio que publish/release: solo en el repo de EQUIPO
# (tiene make-dist.sh) y todos con --dry-run.
# ──────────────────────────────────────────────────────────────────────────

def _branch_guard():
    """Helpers comunes del flujo de ramas. Devuelve (ok, run, dry, subprocess)
    o (False, …) si no es el repo de equipo. `run(cmd)` imprime `$ <cmd>` con
    los colores de publish/release y respeta dry-run; `dry` es bool del flag.

    Nota: la firma fija dry/printer la decide cada comando (necesita el flag
    parseado), así que esto solo valida el repo y devuelve subprocess."""
    import subprocess
    if not os.path.isfile(os.path.join(ROOT, "make-dist.sh")):
        return False, None
    return True, subprocess


def _git_ref_exists(subprocess, ref):
    """True si `ref` (rama/commit) existe localmente."""
    r = subprocess.run(["git", "-C", ROOT, "rev-parse", "--verify", "--quiet", ref],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.returncode == 0


def _current_branch(subprocess):
    r = subprocess.run(["git", "-C", ROOT, "rev-parse", "--abbrev-ref", "HEAD"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return r.stdout.strip()


def _is_dirty(subprocess):
    r = subprocess.run(["git", "-C", ROOT, "status", "--porcelain"],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return bool(r.stdout.strip())


def _suite_green(subprocess, dry):
    """Corre la suite (tests/run.py). Devuelve True si verde. En dry-run NO la
    corre (solo imprime el comando) y devuelve True para no abortar el dry."""
    cmd = [sys.executable, os.path.join(ROOT, "tests", "run.py")]
    print(f"  {DIM}$ {' '.join(cmd)}{R}")
    if dry:
        return True
    return subprocess.call(cmd) == 0


def _test_integrity_warn(base, dry):
    """Guard anti-trampa de tests (phase-gates B2/D3, automatizados) — SEÑAL
    ask-user, NUNCA bloqueo duro. Detecta cuando el cambio DEBILITA la suite
    (tests borrados sin reemplazo, asserts vaciados a pass/assertTrue(True)/
    skipTest) aunque esté verde, vía `dash/dev/test_integrity.py` sobre
    `git diff <base>...HEAD -- tests/`.

    Contrato:
      · sin señal / chequeo imposible (git ausente, no-repo, error) → True en
        silencio — FAIL-OPEN absoluto, jamás rompe el flujo de release.
      · señal + tty → banner WARN con los nombres + confirmación explícita;
        el socio decide (s = sigue, N = detiene A SU petición → False).
      · señal + no-interactivo → banner WARN visible y CONTINÚA (True).
    En dry-run no corre (el dry no ejecuta nada real)."""
    if dry:
        return True
    try:
        from dash.dev import test_integrity
        res = test_integrity.check(base=base)
        if not res or not res.get("flagged"):
            return True
        print(f"\n  {B}⚠ GUARD DE TESTS: este cambio DEBILITA la suite{R} "
              f"{DIM}(aunque corra verde):{R}")
        for reason in (res.get("reasons") or []):
            print(f"    {B}·{R} {reason}")
        print(f"  {DIM}Gates B2/D3 (protocols/phase-gates): la suite verde no "
              f"certifica nada si encogió.{R}")
        if sys.stdin.isatty() and sys.stdout.isatty():
            try:
                ans = input(f"  {C}¿Continuar de todos modos? [s/N]{R} ").strip().lower()
            except Exception:
                return True     # sin respuesta legible → señal ya dada, sigue
            if ans not in ("s", "si", "sí", "y", "yes"):
                print(f"  ✗ Detenido a tu petición — {DIM}restaura los tests (o "
                      f"contesta `s` si el cambio es intencional) y reintenta.{R}")
                return False
        else:
            print(f"  {DIM}(no interactivo: WARN registrado, el flujo continúa){R}")
        return True
    except Exception:
        return True             # fail-open absoluto: el guard jamás rompe nada


def cmd_feature(args):
    """`workspace feature <nombre> [--fix] [--dry-run]` — empieza una rama de feature
    desde `main` actualizado, en un comando, imprimiendo cada git.

    - `<nombre>` kebab-case (sin espacios). Default `feat/<nombre>`; `--fix` → `fix/<nombre>`.
    - Working tree sucio → NO procede (cambiar de rama con WIP es peligroso).
    - Corre: checkout main → (pull --ff-only si hay origin/main) → checkout -b <rama>.
    Solo del repo de EQUIPO."""
    import re
    ok, subprocess = _branch_guard()
    if not ok:
        print("WORKSPACE: `feature` no disponible (no es el repo de equipo).")
        return 1
    dry = "--dry-run" in args
    fix = "--fix" in args
    name = next((a for a in args if not a.startswith("-")), "")
    if not name:
        print("uso: workspace feature <nombre> [--fix]")
        print(f"  {DIM}ej: workspace feature menu-de-archivo   →  rama feat/menu-de-archivo{R}")
        return 2
    # kebab-case: minúsculas, dígitos y guiones; sin espacios; no empieza/termina en '-'.
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        print(f"WORKSPACE: '{name}' no es kebab-case válido.")
        print(f"  {DIM}usa minúsculas, dígitos y guiones; sin espacios ni mayúsculas.{R}")
        print(f"  {DIM}ej: workspace feature menu-de-archivo{R}")
        return 2
    branch = ("fix/" if fix else "feat/") + name

    def run(cmd, cwd=None):
        print(f"  {DIM}$ {' '.join(cmd)}{R}")
        return 0 if dry else subprocess.call(cmd, cwd=cwd)

    if _is_dirty(subprocess) and not dry:
        print(f"  {B}⚠ Hay cambios sin commitear.{R} {DIM}Cambiar de rama con WIP es "
              f"peligroso: commitea o stashea primero, luego corre esto.{R}")
        return 1
    # La rama destino no debe existir ya.
    if _git_ref_exists(subprocess, branch) and not dry:
        print(f"WORKSPACE: la rama `{branch}` ya existe. "
              f"{DIM}Bórrala o usa otro nombre.{R}")
        return 1

    rc = run(["git", "-C", ROOT, "checkout", "main"])
    if rc != 0 and not dry:
        print(f"\n  ✗ No pude cambiar a `main` (¿conflictos/WIP?)."); return rc
    # pull --ff-only solo si hay tracking de origin/main (sin remoto/red: avisa y sigue).
    if _git_ref_exists(subprocess, "origin/main") or dry:
        rc = run(["git", "-C", ROOT, "pull", "--ff-only"])
        if rc != 0 and not dry:
            print(f"  {B}⚠ No pude actualizar main (sin red o divergió){R} {DIM}— "
                  f"sigo con lo que tienes local.{R}")
    else:
        print(f"  {DIM}(sin origin/main: no hay nada que jalar; sigo){R}")
    rc = run(["git", "-C", ROOT, "checkout", "-b", branch])
    if rc != 0 and not dry:
        print(f"\n  ✗ No pude crear la rama `{branch}`."); return rc
    if dry:
        print(f"\n  {DIM}(dry-run: no se ejecutó nada){R}")
    else:
        print(f"\n  {C}✓ Estás en `{branch}`{R} — ya puedes trabajar.")
        print(f"  {DIM}Al terminar: `workspace integrate` (mete tu rama a main).{R}")
    return 0


def cmd_integrate(args):
    """`workspace integrate [--dry-run] [--delete]` — mete la rama ACTUAL a `main`
    (una por una), corriendo la suite antes y después, imprimiendo cada git.

    - Solo desde una rama de feature (no main/stable).
    - Working tree sucio → NO procede.
    - Suite ANTES; si está roja → ABORTA (no integres roto).
    - Corre: checkout main → merge --no-ff <rama>. Conflicto → te lo deja a ti.
    - Suite OTRA VEZ en main tras el merge.
    - Por DEFAULT la rama se CONSERVA tras integrar (modelo rama-workspace:
      persiste para seguir iterando/pusheando). Pasa `--delete` (alias `--remove`)
      para borrarla con `git branch -d` cuando ya terminaste la feature
      (la `-d` se niega si no está mergeada; no forzamos). Fallo → nunca borra.
    Solo del repo de EQUIPO."""
    ok, subprocess = _branch_guard()
    if not ok:
        print("WORKSPACE: `integrate` no disponible (no es el repo de equipo).")
        return 1
    dry = "--dry-run" in args
    delete = "--delete" in args or "--remove" in args
    feature = _current_branch(subprocess)
    if feature in ("main", "stable"):
        print(f"WORKSPACE: estás en `{feature}` — no es una rama de feature. "
              f"{DIM}Ponte en tu rama (`workspace feature …`) e intégrala.{R}")
        return 1
    # Detached HEAD: rev-parse --abbrev-ref devuelve literalmente "HEAD".
    # Sin este guard, `merge --no-ff HEAD` sería un no-op y se reportaría
    # "integrado" sin integrar nada (los commits quedan atrás al checkout main).
    if feature == "HEAD":
        print(f"WORKSPACE: estás en detached HEAD — no hay rama que integrar. "
              f"{DIM}Ponte en una rama de feature (`workspace feature …`) e intégrala.{R}")
        return 1
    if not feature and not dry:
        print("WORKSPACE: no pude detectar la rama actual."); return 1
    feature = feature or "<rama-actual>"

    def run(cmd, cwd=None):
        print(f"  {DIM}$ {' '.join(cmd)}{R}")
        return 0 if dry else subprocess.call(cmd, cwd=cwd)

    if _is_dirty(subprocess) and not dry:
        print(f"  {B}⚠ Hay cambios sin commitear.{R} {DIM}Commitea (o stashea) tu "
              f"trabajo antes de integrar.{R}")
        return 1

    # Suite ANTES: no integres roto.
    print(f"  {B}Corriendo la suite antes de integrar…{R}")
    if not _suite_green(subprocess, dry):
        print(f"\n  ✗ {B}Suite ROJA — aborto sin tocar main.{R} "
              f"{DIM}Arregla los tests en `{feature}` y reintenta.{R}")
        return 1

    # Guard anti-trampa de tests (B2/D3): ¿la rama DEBILITA la suite aunque
    # esté verde? SEÑAL ask-user, fail-open — solo detiene si el socio dice no.
    if not _test_integrity_warn("main", dry):
        return 1

    rc = run(["git", "-C", ROOT, "checkout", "main"])
    if rc != 0 and not dry:
        print(f"\n  ✗ No pude cambiar a `main`."); return rc
    # --no-edit: acepta el mensaje de merge auto-generado sin abrir el editor
    # (sin él, `merge --no-ff` lanza $EDITOR a media ejecución en un tty).
    rc = run(["git", "-C", ROOT, "merge", "--no-ff", "--no-edit", feature])
    if rc != 0 and not dry:
        # Conflicto: NO lo resuelvo yo; dejo main en estado de conflicto para que lo vea.
        print(f"\n  {B}⚠ El merge dio conflicto.{R} main quedó a mitad del merge.")
        print(f"  {DIM}1) Resuelve los conflictos a mano (los archivos marcados).{R}")
        print(f"  {DIM}2) `git add <archivos>` y `git commit` para cerrar el merge.{R}")
        print(f"  {DIM}   (o `git merge --abort` para deshacer y volver al estado previo).{R}")
        return rc

    # Suite OTRA VEZ en main (post-integración).
    print(f"\n  {B}Corriendo la suite en main (post-integración)…{R}")
    green = _suite_green(subprocess, dry)
    if dry:
        # En dry-run mostramos lo que pasaría con la rama según el flag.
        if delete:
            print(f"  {DIM}$ git -C {ROOT} branch -d {feature}{R}")
        else:
            print(f"  {DIM}(--delete no pasado: la rama `{feature}` se conservaría){R}")
        print(f"\n  {DIM}(dry-run: no se ejecutó nada){R}")
        return 0
    if green:
        # Éxito real (mergeada a main + suite VERDE). Modelo rama-workspace:
        # por DEFAULT la rama se conserva para seguir iterando/pusheando. Solo
        # con `--delete` la borramos (`-d`, no `-D`: se niega si no está mergeada
        # → seguro). Ya estamos en `main` (el checkout de arriba): borrar no choca.
        if delete:
            rc_del = subprocess.call(["git", "-C", ROOT, "branch", "-d", feature])
            if rc_del == 0:
                print(f"\n  {C}✓ `{feature}` integrado a main{R} — suite VERDE · "
                      f"{DIM}rama `{feature}` borrada (--delete).{R}")
            else:
                # `branch -d` se negó (p.ej. git no la ve mergeada): NO forzamos.
                # El integrate ya fue exitoso; solo dejamos la rama.
                print(f"\n  {C}✓ `{feature}` integrado a main{R} — suite VERDE.")
                print(f"  {B}⚠ No pude borrar `{feature}` automáticamente{R} {DIM}(git la "
                      f"considera no-mergeada). Bórrala a mano si quieres: "
                      f"git branch -d {feature}{R}")
        else:
            print(f"\n  {C}✓ `{feature}` integrado a main{R} — suite VERDE · "
                  f"{DIM}rama `{feature}` conservada (sigue trabajándola; "
                  f"`--delete` para borrarla).{R}")
    else:
        print(f"\n  {B}⚠ Integrado, pero la suite quedó ROJA en main{R} — "
              f"arréglalo antes de promover.")
        print(f"  {DIM}La rama `{feature}` NO se borró (integrate no fue limpio).{R}")
    print(f"  {DIM}Siguiente paso: `workspace promote` (main → stable).{R}")
    return 0 if green else 1


def cmd_promote(args):
    """`workspace promote [--dry-run]` — promueve `main` → `stable` (lo bendecido),
    corriendo la suite antes, imprimiendo cada git.

    - Working tree sucio → NO procede.
    - Suite ANTES; si está roja → ABORTA (no promuevas roto).
    - Corre: checkout stable → merge --ff-only main → checkout main.
    - Si stable divergió (ff-only falla) → informa, no fuerza. Solo del repo de EQUIPO."""
    ok, subprocess = _branch_guard()
    if not ok:
        print("WORKSPACE: `promote` no disponible (no es el repo de equipo).")
        return 1
    dry = "--dry-run" in args

    def run(cmd, cwd=None):
        print(f"  {DIM}$ {' '.join(cmd)}{R}")
        return 0 if dry else subprocess.call(cmd, cwd=cwd)

    if _is_dirty(subprocess) and not dry:
        print(f"  {B}⚠ Hay cambios sin commitear.{R} {DIM}Commitea (o stashea) antes "
              f"de promover.{R}")
        return 1

    # Suite ANTES: no promuevas roto.
    print(f"  {B}Corriendo la suite antes de promover…{R}")
    if not _suite_green(subprocess, dry):
        print(f"\n  ✗ {B}Suite ROJA — aborto, no promuevo.{R} "
              f"{DIM}Arregla main y reintenta.{R}")
        return 1

    # Guard anti-trampa de tests (B2/D3): ¿lo que se promueve DEBILITÓ la suite
    # vs stable? SEÑAL ask-user, fail-open — solo detiene si el socio dice no.
    if not _test_integrity_warn("stable", dry):
        return 1

    rc = run(["git", "-C", ROOT, "checkout", "stable"])
    if rc != 0 and not dry:
        print(f"\n  ✗ No pude cambiar a `stable`."); return rc
    rc = run(["git", "-C", ROOT, "merge", "--ff-only", "main"])
    if rc != 0 and not dry:
        # stable divergió: no forzamos. El socio decide el merge manual.
        print(f"\n  {B}⚠ `stable` divergió de main (fast-forward no es posible).{R}")
        print(f"  {DIM}Revisa qué tiene stable que main no; si lo quieres unir a mano:{R}")
        print(f"  {DIM}  git merge --no-ff main   (estando en stable){R}")
        print(f"  {DIM}No lo fuerzo por ti.{R}")
        # volvemos a main para no dejarlo en stable a medias
        run(["git", "-C", ROOT, "checkout", "main"])
        return rc
    # Volvemos a main (estado de trabajo normal del socio).
    rc_back = run(["git", "-C", ROOT, "checkout", "main"])
    if dry:
        print(f"\n  {DIM}(dry-run: no se ejecutó nada){R}")
        return 0
    # H2: si el checkout-de-vuelta a main FALLÓ (p.ej. main tomado por un
    # worktree), el socio quedó en `stable` — sus próximos commits caerían en la
    # rama que va a clientes. NO declarar éxito a ciegas: avisar fuerte.
    if rc_back != 0 or _current_branch(subprocess) != "main":
        cur = _current_branch(subprocess) or "?"
        print(f"\n  {B}⚠ stable se promovió, PERO no pude volver a `main` "
              f"(estás en `{cur}`).{R}")
        print(f"  {DIM}Cambia a main A MANO antes de seguir (git -C {ROOT} "
              f"checkout main) — si no, tus próximos commits caen en `stable`, "
              f"que va a clientes.{R}")
        return 1
    sha = subprocess.run(["git", "-C", ROOT, "rev-parse", "--short", "stable"],
                         capture_output=True, text=True, encoding="utf-8",
                         errors="replace").stdout.strip()
    print(f"\n  {C}✓ stable promovido a {sha}{R} (= main).")
    print(f"  {DIM}Repártelo: `workspace publish` (equipo) · `workspace release` (clientes).{R}")
    return 0


# ── workflows (`workspace wf`) — pipelines declarativos sobre el runner F1 ─────
# Glifos SEMÁNTICOS por estado (Windows-safe: todos < U+2600, igual que el hub):
#   ✓ verde · ◐ corriendo (paso actual) · ⏸ esperando al socio · ✗ rojo ·
#   · pendiente · ⊘ stub declarado (agent sin driver — jamás verde fingido).
_WF_RUN_BADGE = {
    # estado de RUN → (glifo, etiqueta corta) — el color se resuelve al pintar
    "done":         ("✓", "done"),
    "failed":       ("✗", "failed"),
    "paused_human": ("⏸", "paused-human"),
    "running":      ("◐", "running"),
    "rejected":     ("⊗", "rejected"),   # gate RECHAZADO por el socio (terminal)
}


def _wf_status_color(status):
    """Color del estado global de un run (rol semántico de la paleta)."""
    return {"done": OK, "failed": ERR, "paused_human": B2,
            "running": B, "rejected": ERR}.get(status, DIM)


def _wf_fmt_dur(secs):
    """Segundos → duración corta legible ("8s" · "3m12s" · "1h04m").
    PURA; None/negativo → "" (mejor callar que mentir)."""
    try:
        s = int(secs)
    except (TypeError, ValueError):
        return ""
    if s < 0:
        return ""
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m"


def _wf_iso_secs(a, b):
    """Segundos entre dos timestamps isoformat del runner (t0/t1, created/
    updated). PURA; cualquier dato raro → None (jamás revienta la vista)."""
    import datetime
    try:
        d = (datetime.datetime.fromisoformat(str(b))
             - datetime.datetime.fromisoformat(str(a))).total_seconds()
    except (TypeError, ValueError):
        return None
    return d if d >= 0 else None


def _wf_step_dur(st):
    """Duración legible de UN paso ("12s") si su estado la trae (t0/t1 —
    los pone el runner al correrlo); "" si no. PURA."""
    if not st.get("t0") or not st.get("t1"):
        return ""
    return _wf_fmt_dur(_wf_iso_secs(st["t0"], st["t1"]))


def _wf_run_elapsed(state, now=None):
    """Tiempo transcurrido del RUN, legible: created→updated si ya no avanza
    solo (terminal/pausado), created→ahora si sigue corriendo. `now`
    inyectable (isoformat) para tests. "" si el estado no trae fechas."""
    created = state.get("created")
    if not created:
        return ""
    if state.get("status") == "running":
        import datetime
        end = now or datetime.datetime.now().isoformat(timespec="seconds")
    else:
        end = state.get("updated") or created
    return _wf_fmt_dur(_wf_iso_secs(created, end))


def _wf_progress(state):
    """(pasos verdes, total) de un run — el `n/total` de toda vista wf."""
    steps = state.get("steps") or []
    return sum(1 for s in steps if s.get("status") == "ok"), len(steps)


def _wf_step_glyph(st, is_current):
    """(glifo, color) de UN paso. `is_current` = el paso donde el run está
    parado AHORA (status running) — se pinta ◐ en acento, es el que avanza."""
    status = st.get("status")
    if status == "ok":
        if st.get("stub"):
            return "⊘", DIM                  # stub declarado: omitido, tenue
        return "✓", OK
    if status == "skipped":
        return "⊝", DIM                      # when: falso — omitido, tenue
    if status == "fail":
        return "✗", ERR
    if status == "rejected":
        return "⊗", ERR                      # el socio rechazó este gate
    if status == "waiting_human":
        return "⏸", B2
    if is_current:
        return "◐", B                        # el paso corriendo, resaltado
    return "·", GREY                         # pendiente, tenue


def _wf_run_lines(state):
    """Vista CHECKLIST de un run → lista de líneas (con ANSI), lista para
    imprimir. Función PURA: solo LEE `state`, no muta ni toca disco —
    # futuro: --watch re-lee el run y re-pinta esto a cadencia baja."""
    lines = [""]
    status = state.get("status", "?")
    badge, label = _WF_RUN_BADGE.get(status, ("·", str(status)))
    scol = _wf_status_color(status)
    done, total = _wf_progress(state)
    lines.append(f"  {B}{state.get('workflow', '?')}{R} "
                 f"v{state.get('version', '?')} · "
                 f"{DIM}{state.get('run_id', '?')}{R}"
                 + (f"  {DIM}[dry]{R}" if state.get("dry") else ""))
    elapsed = _wf_run_elapsed(state)
    lines.append(f"  {scol}{badge} {label}{R} · {done}/{total} pasos verdes"
                 + (f"  {DIM}· ⏱ {elapsed}{R}" if elapsed else "")
                 + f"  {DIM}· {state.get('updated', '')}{R}")
    lines.append("")

    steps = state.get("steps") or []
    cur = state.get("current", -1)
    # etiqueta base por paso (texto plano) para ALINEAR la columna del detalle
    labels = []
    for st in steps:
        lab = f"{st.get('id', '?')} ({st.get('kind', '?')})"
        if int(st.get("attempts") or 0) > 1:
            lab += f" ×{st['attempts']}"
        if st.get("stub"):
            lab += " [stub]"
        if st.get("dry"):
            lab += " [dry]"
        labels.append(lab)
    lab_w = max((_vis(x) for x in labels), default=0)

    for i, st in enumerate(steps):
        is_current = (status == "running" and i == cur
                      and st.get("status") == "pending")
        glyph, gcol = _wf_step_glyph(st, is_current)
        pad = " " * max(0, lab_w - _vis(labels[i]))
        detail = (st.get("detail") or "").split("\n")[0]
        # cuánto tardó el paso (t0/t1 del runner) — solo pasos que EJECUTARON
        # (ok/fail); un gate en pausa o un skipped con "0s" sería ruido
        dur = _wf_step_dur(st) if st.get("status") in ("ok", "fail") else ""
        if dur:
            detail = f"⏱ {dur}" + (f" · {detail}" if detail else "")
        if is_current:
            # el paso que AVANZA ahora mismo — brillante, señalado y UBICADO
            # (paso N/total: se lee al instante por dónde va el pipeline)
            row = (f"    {gcol}{glyph} {BO}{WH}{labels[i]}{R}{pad}"
                   f"   {B}← paso actual ({i + 1}/{len(steps)}){R}")
        else:
            name_col = GREY if st.get("status") == "pending" \
                else (DIM if (st.get("stub")
                              or st.get("status") == "skipped") else "")
            row = f"    {gcol}{glyph}{R} {name_col}{labels[i]}{R}{pad}"
            if detail:
                dcol = ERR if st.get("status") == "fail" else DIM
                row += f"   {dcol}— {detail}{R}"
        lines.append(row.rstrip())
        v = st.get("verify")
        if isinstance(v, dict) and v.get("detail"):
            vmark, vcol = {True: ("✓", OK), False: ("✗", ERR)}.get(
                v.get("ok"), ("·", DIM))
            lines.append(f"        {vcol}verify {vmark}{R} {DIM}{v['detail']}{R}")
        arts = st.get("artifacts")
        if isinstance(arts, dict):
            for k, val in sorted(arts.items()):
                lines.append(f"        {DIM}→ {k}: {val}{R}")

    # pie: la ACCIÓN sugerida según el estado global
    rid = state.get("run_id", "?")
    if status == "done":
        lines += ["", f"  {OK}✓ run completo{R}"]
    elif status == "paused_human":
        lines += ["", f"  {B2}⏸ en pausa (esperando al socio){R} — "
                      f"{DIM}decidir: workspace wf decide {rid} <paso> "
                      f"approve|reject [--note …] · aprobar y seguir: "
                      f"workspace wf resume {rid}{R}"]
    elif status == "rejected":
        lines += ["", f"  {ERR}⊗ run RECHAZADO por el socio{R} — "
                      f"{DIM}terminal (la anotación queda en el paso); "
                      f"retomar el trabajo = run nuevo.{R}"]
    elif status == "failed":
        lines += ["", f"  {ERR}✗ run FALLIDO{R} — {DIM}arregla la causa y "
                      f"`workspace wf resume {rid}` re-corre el paso rojo.{R}"]
    elif status == "running":
        lines += ["", f"  {B}◐ corriendo{R} — "
                      f"{DIM}re-mirar: workspace wf show {rid}{R}"]
    return lines


def _wf_runs_lines(runs):
    """`workspace wf runs` → lista de líneas: una fila por run persistido
    (más reciente primero), con estado, progreso y cuándo. PURA (state→líneas)
    # futuro: --watch re-pinta esto también."""
    if not runs:
        return ["  (sin runs todavía — `workspace wf run <spec>`)"]
    lines = ["", f"  {B}runs recientes{R} {DIM}(más nuevo primero){R}", ""]
    names = [str(st.get("workflow", "?")) for st in runs]
    name_w = max(_vis(n) for n in names)
    for st, name in zip(runs, names):
        status = st.get("status", "?")
        badge, label = _WF_RUN_BADGE.get(status, ("·", str(status)))
        scol = _wf_status_color(status)
        done, total = _wf_progress(st)
        when = str(st.get("updated", "")).replace("T", " ")
        pad = " " * max(0, name_w - _vis(name))
        lines.append(
            f"    {scol}{badge}{R} {name}{pad}  "
            f"{scol}{label:<12}{R} {done:>2}/{total:<2} pasos  "
            f"{DIM}{when}  {st.get('run_id', '?')}{R}"
            + (f" {DIM}[dry]{R}" if st.get("dry") else ""))
    lines += ["", f"  {DIM}detalle: workspace wf show <run-id> · "
                  f"en vivo, varias a la vez: workspace wf board{R}"]
    return lines


def _wf_print_run(state):
    """Imprime la vista checklist de un run (render puro en _wf_run_lines)."""
    print("\n".join(_wf_run_lines(state)))


# ── wf watch — el pipeline EN VIVO (re-lee el run y re-pinta el checklist) ──
def _wf_watch_over(state):
    """¿El run ya NO va a avanzar solo? (corte del watch). Función PURA
    state → bool: solo `running` sigue mirándose; done/failed/paused_human
    son terminales (paused necesita al socio, no tiene sentido mirarlo), y
    un estado desconocido también corta (jamás loop infinito sobre algo que
    no entendemos)."""
    return (state or {}).get("status") != "running"


def _wf_watch_lines(state, interval):
    """Encabezado del watch + checklist (reusa _wf_run_lines tal cual)."""
    if _wf_watch_over(state):
        status = (state or {}).get("status", "?")
        _badge, label = _WF_RUN_BADGE.get(status, ("·", str(status)))
        scol = _wf_status_color(status)
        head = (f"  {scol}■ watch terminado{R} {DIM}— run {label}, "
                f"ya no avanza solo{R}")
    else:
        head = (f"  {B}◉ en vivo{R} {DIM}· cada {interval:g}s · "
                f"Ctrl-C para salir{R}")
    return ["", head] + _wf_run_lines(state)


def _wf_watch_paint(lines, prev_n, out):
    """Re-pinta EN SITIO: sube el cursor `prev_n` líneas y reescribe cada una
    con \\r\\033[K (mismo idioma que el hub — nada de alt-screen ni 2J a media
    sesión). Si el render nuevo es más corto, limpia el sobrante. Devuelve
    cuántas líneas quedaron pintadas (el prev_n del siguiente tick)."""
    if prev_n:
        out.write(f"\033[{prev_n}A")
    for ln in lines:
        out.write("\r\033[K" + ln + "\n")
    extra = prev_n - len(lines)
    if extra > 0:
        out.write("\r\033[K\n" * extra)
        out.write(f"\033[{extra}A")
    out.flush()
    return len(lines)


def _wf_watch(rid, interval=1.0, max_ticks=None, is_tty=None, sleep=None):
    """`workspace wf watch <run-id>` — mira el run avanzar: re-lee el estado del
    disco y re-pinta el checklist a cadencia baja hasta que el run llega a
    estado terminal (done/failed/paused_human) o el socio hace Ctrl-C.

    Testeable sin colgarse: el corte vive en _wf_watch_over (pura) y
    `max_ticks` acota el loop; `is_tty`/`sleep` son inyectables. Sin TTY
    (pipe/CI) → UN render estático y sale, jamás loop. rc: 1 si el run quedó
    failed, 0 en todo lo demás (incl. Ctrl-C)."""
    import time
    import workflows as wf
    if is_tty is None:
        is_tty = sys.stdout.isatty()
    if sleep is None:
        sleep = time.sleep
    interval = max(0.5, min(60.0, float(interval)))   # cadencia BAJA, con tope

    state = wf.load_run(rid)
    if not is_tty:
        # pipe/redirección: render único estático, sin loop (CI-safe)
        print("\n".join(_wf_run_lines(state)))
        if not _wf_watch_over(state):
            print(f"  {DIM}(sin TTY: render único — re-mirar: "
                  f"workspace wf show {rid}){R}")
        return 1 if state.get("status") == "failed" else 0

    out = sys.stdout
    prev_n, ticks = 0, 0
    out.write("\033[?25l")                        # cursor oculto (se restaura)
    try:
        while True:
            prev_n = _wf_watch_paint(_wf_watch_lines(state, interval),
                                     prev_n, out)
            if _wf_watch_over(state):             # terminal → render final queda
                return 1 if state.get("status") == "failed" else 0
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                return 0                          # tope de ticks (tests/corte)
            sleep(interval)
            try:
                state = wf.load_run(rid)          # re-leer del disco
            except Exception:
                pass  # lectura transitoria fallida: conservar el último estado
    except KeyboardInterrupt:
        out.write("\n")
        print(f"  {DIM}watch detenido — el run sigue en disco: "
              f"workspace wf show {rid}{R}")
        return 0
    finally:
        out.write("\033[?25h")                    # restaurar cursor SIEMPRE
        out.flush()


def _wf_watch_args(rest):
    """(run-id, interval) de `wf watch` — `--interval S` con valor consumido
    para que el posicional no se confunda (mismo patrón que _wf_flags)."""
    interval, consumed = 1.0, set()
    for i, a in enumerate(rest):
        if a == "--interval" and i + 1 < len(rest):
            try:
                interval = float(rest[i + 1])
            except ValueError:
                pass
            consumed.add(i + 1)
    rid = next((a for i, a in enumerate(rest)
                if not a.startswith("-") and i not in consumed), "")
    return rid, interval


# ── wf board — VARIOS pipelines EN VIVO, lado a lado (split responsivo) ─────
# La idea del split-terminal: un panel por corrida, cada uno con su checklist
# avanzando. Reusa la disciplina del watch (re-lee del disco, re-pinta EN SITIO
# a cadencia baja, jamás alt-screen) y los glifos/colores de _wf_step_glyph.
# Ancho SIEMPRE visual (clip/pad de hublayout — la misma vara del hub).
from hublayout import clip as _wclip, pad as _wpad  # noqa: E402

_WF_BOARD_MIN_PANEL = 30   # ancho mínimo ÚTIL de un panel (debajo: 1 columna)
_WF_BOARD_MAX_PANEL = 46   # tope: paneles más anchos no leen mejor
_WF_BOARD_GAP = 2          # aire entre columnas
_WF_BOARD_MAX_COLS = 4     # más de 4 pipelines lado a lado ya no se sigue
_WF_BOARD_MIN_LINES = 10   # piso del frame (chrome 5 + panel mínimo 5) — con
                           # terminales más bajas se rinde a este piso (honesto)


def _wf_board_cols(w, n):
    """Nº de columnas del tablero según el ancho REAL de la terminal (y cuántos
    paneles hay). PURA. Angosto → 1 (apilado); ~80 → 2; ~120 → 3; ancho → 4."""
    if n <= 0:
        return 1
    per = _WF_BOARD_MIN_PANEL + _WF_BOARD_GAP
    fit = (max(0, w - 1) + _WF_BOARD_GAP) // per
    return max(1, min(_WF_BOARD_MAX_COLS, n, fit))


def _wf_board_pick(runs, top=4, follow=None):
    """QUÉ corridas van al tablero: las que CORREN primero, luego las pausadas
    (esperan al socio), luego las recientes terminales — tope `top`. `runs`
    ya viene más-reciente-primero (list_runs); el sort es estable, así que
    dentro de cada grupo se conserva la recencia. → (mostradas, nº ocultas).

    `follow` (run-id): esa corrida va PRIMERO pase lo que pase — el tablero
    la sigue (workflows.active_run() / `--follow`). Un follow que no está
    entre `runs` no cambia nada (compat: sin follow, prioridad de hoy)."""
    rank = {"running": 0, "paused_human": 1}
    orden = sorted(runs, key=lambda st: rank.get((st or {}).get("status"), 2))
    if follow and any((st or {}).get("run_id") == follow for st in orden):
        orden = ([st for st in orden if (st or {}).get("run_id") == follow]
                 + [st for st in orden if (st or {}).get("run_id") != follow])
    shown = orden[:max(1, int(top))]
    return shown, max(0, len(runs) - len(shown))


def _wf_board_over(states):
    """¿El tablero ya NO va a cambiar solo? (corte del loop, espejo de
    _wf_watch_over). PURA: sigue vivo solo si ALGUNA corrida está running."""
    return not any((st or {}).get("status") == "running"
                   for st in (states or []))


def _wf_board_rc(states):
    """rc del board al cortar: 1 si alguna corrida mostrada quedó failed
    (mismo contrato que watch), 0 en todo lo demás."""
    return 1 if any((st or {}).get("status") == "failed"
                    for st in (states or [])) else 0


def _wf_panel_lines(state, w, k_max=None, followed=False):
    """UN panel del tablero: el pipeline de UNA corrida en `w` columnas
    visuales EXACTAS por línea (bordes alineados por construcción — todo el
    contenido pasa por pad/clip). PURA. `k_max` acota las líneas de pasos
    (presupuesto de altura); si no caben todos, muestra una VENTANA que
    incluye el paso actual y cierra con `⋯ +n`. Glifos/colores: los MISMOS
    de _wf_step_glyph — cero lógica de estado duplicada. `followed`: esta
    corrida es la SEGUIDA (--follow / active_run) — marca `▸` en el título
    y borde en acento; solo color/marca, el ancho visual no cambia."""
    inner = max(1, w - 4)                       # "│ " + contenido + " │"
    status = state.get("status", "?")
    # borde en ACENTO si la corrida AVANZA ahora (o es la seguida) — se
    # distingue de un vistazo (solo color: el ancho visual no cambia)
    bcol = B if (status == "running" or followed) else GREY

    def row(content):
        return f"{bcol}│{R} " + _wpad(content, inner) + f" {bcol}│{R}"

    badge, label = _WF_RUN_BADGE.get(status, ("·", str(status)))
    scol = _wf_status_color(status)
    done, total = _wf_progress(state)

    # borde superior con el nombre del workflow integrado (▸ = seguida)
    name = _wclip(("▸ " if followed else "")
                  + str(state.get("workflow", "?")), max(1, w - 8))
    fill = max(0, w - 5 - _vis(name))
    lines = [f"{bcol}╭─{R} {B}{name}{R} {bcol}{'─' * fill}╮{R}"]
    elapsed = _wf_run_elapsed(state)
    lines.append(row(f"{scol}{badge} {label}{R} {DIM}· {done}/{total} "
                     f"verdes{R}" + (f" {DIM}· ⏱ {elapsed}{R}"
                                     if elapsed else "")
                     + (f" {DIM}[dry]{R}" if state.get("dry") else "")))
    lines.append(row(f"{DIM}{state.get('run_id', '?')}{R}"))

    steps = state.get("steps") or []
    cur = state.get("current", -1)
    n = len(steps)
    if k_max is None or k_max >= n:
        start, k = 0, n
    elif k_max >= 2:
        k = k_max - 1                           # 1 línea para el `⋯ +n`
        # ventana que SIEMPRE incluye el paso donde el run está parado
        anchor = cur if 0 <= cur < n else next(
            (i for i, s in enumerate(steps)
             if s.get("status") not in ("ok", "skipped")), 0)
        start = max(0, min(anchor, n - k))
    else:
        start, k = 0, 0                         # ni un paso cabe: solo resumen
    for i in range(start, start + k):
        st = steps[i]
        is_current = (status == "running" and i == cur
                      and st.get("status") == "pending")
        glyph, gcol = _wf_step_glyph(st, is_current)
        lab = f"{st.get('id', '?')} ({st.get('kind', '?')})"
        if int(st.get("attempts") or 0) > 1:
            lab += f" ×{st['attempts']}"
        if is_current:
            lines.append(row(f"{gcol}{glyph} {BO}{WH}{lab}{R}"))
            continue
        name_col = GREY if st.get("status") == "pending" \
            else (DIM if (st.get("stub")
                          or st.get("status") == "skipped") else "")
        cell = f"{gcol}{glyph}{R} {name_col}{lab}{R}"
        if st.get("status") == "fail":
            detail = (st.get("detail") or "").split("\n")[0]
            if detail:
                cell += f" {ERR}— {detail}{R}"
        lines.append(row(cell))
    hidden = n - k
    if hidden > 0:
        lines.append(row(f"{DIM}⋯ +{hidden} pasos{R}"))
    lines.append(f"{bcol}╰{'─' * max(0, w - 2)}╯{R}")
    return lines


def _wf_board_lines(shown, w, h, interval=1.0, live=True, extra=0,
                    follow=None):
    """El FRAME completo del tablero → lista de líneas. PURA (states → líneas).
    Garantías (las verifica la suite barriendo anchos Y alturas):
      · ninguna línea excede w-1 columnas visibles (nada de wrap fantasma);
      · len(líneas) ≤ max(h-1, _WF_BOARD_MIN_LINES) — si el presupuesto no da,
        primero recorta pasos por panel (ventana + `⋯ +n`), luego SUELTA
        paneles (nunca desborda hacia abajo).
    Layout: columnas lado a lado si el ancho da (2/3/4), apilado si no.
    `follow` (run-id): esa corrida se marca como SEGUIDA (▸ en su panel y en
    el encabezado); sin follow, el frame es idéntico al de hoy."""
    import math
    w = max(8, int(w or 80))
    budget = max(_WF_BOARD_MIN_LINES, int(h or 24) - 1)
    avail = budget - 5                          # chrome: 3 arriba + 2 abajo
    shown = list(shown or [])
    extra = int(extra)

    if not shown:
        return ["", f"  {DIM}(sin corridas — `workspace wf run <spec>`){R}"]

    # presupuesto de altura: pasos por panel; si ni con 1 cabe, soltar paneles
    while True:
        ncols = _wf_board_cols(w, len(shown))
        nrows = math.ceil(len(shown) / ncols)
        k_max = avail // nrows - 4              # 4 = bordes + estado + run-id
        if k_max >= 1 or len(shown) <= 1:
            break
        shown.pop()                             # suelta la menos prioritaria
        extra += 1
    k_max = max(1, k_max)

    prefix = "  " if w >= 30 else ""
    usable = w - 1 - len(prefix)
    panel_w = min(_WF_BOARD_MAX_PANEL,
                  max(6, (usable - _WF_BOARD_GAP * (ncols - 1)) // ncols))

    corriendo = sum(1 for s in shown if s.get("status") == "running")
    if _wf_board_over(shown):
        head = (f"  {DIM}■ tablero wf — nada corriendo ya "
                f"(render final){R}")
    elif live:
        head = (f"  {B}◉ tablero wf{R} {DIM}· {len(shown) + extra} corridas "
                f"({corriendo} corriendo) · cada {interval:g}s · "
                f"Ctrl-C para salir{R}")
    else:
        head = (f"  {B}◉ tablero wf{R} {DIM}· {len(shown) + extra} corridas "
                f"({corriendo} corriendo){R}")
    seguida = bool(follow) and any((s or {}).get("run_id") == follow
                                   for s in shown)
    if seguida:
        head += f" {DIM}· ▸ siguiendo {follow}{R}"

    panels = [_wf_panel_lines(
        st, panel_w, k_max,
        followed=seguida and (st or {}).get("run_id") == follow)
        for st in shown]
    grid, blank = [], " " * panel_w
    for r0 in range(0, len(panels), ncols):
        fila = panels[r0:r0 + ncols]
        alto = max(len(p) for p in fila)
        for j in range(alto):
            cells = [p[j] if j < len(p) else blank for p in fila]
            grid.append((prefix
                         + (" " * _WF_BOARD_GAP).join(cells)).rstrip())

    foot = f"  {DIM}detalle: workspace wf show <run-id>"
    if extra > 0:
        foot += f" · +{extra} corridas más: workspace wf runs"
    foot += R
    lines = ["", head, ""] + grid + ["", foot]
    if h < _WF_BOARD_MIN_LINES + 1:
        import responsive_ui as UI
        return UI.frame(lines, w, h, title='CORRIDAS',
                        exit_hint='workspace wf show <id>')
    # red de seguridad: NINGUNA línea sale más ancha que w-1 (clip visual)
    return [ln if _vis(ln) <= w - 1 else _wclip(ln, w - 1) for ln in lines]


def _wf_board(top=4, interval=1.0, max_ticks=None, is_tty=None, sleep=None,
              size=None, follow=None, persist=False):
    """`workspace wf board` — el tablero EN VIVO: varias corridas a la vez, cada
    una como panel con su pipeline avanzando. Misma disciplina que watch:
    re-lee del disco, re-pinta EN SITIO (cursor-arriba, sin alt-screen) a
    cadencia baja; corta solo cuando NADA corre (o Ctrl-C, limpio).

    `follow`: run-id → esa corrida va primero y marcada (▸); el literal
    `active` → se lee workflows.active_run() EN CADA tick (la costura del
    split: arranca un run y el pane derecho se clava en él solo). Sin
    active_run (o follow inexistente) → comportamiento de hoy, intacto.

    `persist`: cuando nada corre, NO sale — se queda repintando EN SITIO
    (cursor-arriba, sin `clear`) esperando el próximo run. Es la costura del
    split: el pane derecho lo corre UNA vez con --persist, sin loop externo
    de `clear` → cero parpadeo (antes el pane re-lanzaba el board cada 3s con
    `clear`, y ese clear era el flash). Sin --persist: comportamiento de hoy
    (sale al terminar, para `wf board` de una pasada).

    Testeable sin colgarse: corte en _wf_board_over (pura), `max_ticks` acota
    el loop; `is_tty`/`sleep`/`size` inyectables. Sin TTY (pipe/CI) → UN
    render estático y sale. rc: 1 si alguna corrida mostrada quedó failed."""
    import time
    import shutil
    import workflows as wf
    if is_tty is None:
        is_tty = sys.stdout.isatty()
    if sleep is None:
        sleep = time.sleep
    if size is None:
        size = lambda: shutil.get_terminal_size((100, 30))  # noqa: E731
    interval = max(0.5, min(60.0, float(interval)))
    limit = max(15, int(top) * 3)

    def _wh():
        try:
            w, h = size()
            return int(w), int(h)
        except Exception:
            return 100, 30

    def _fid():
        """El run-id a seguir en ESTE tick (`active` se re-lee del disco:
        el pane retargetea solo cuando otro run arranca). Falla-suave."""
        if follow == "active":
            try:
                return wf.active_run()
            except Exception:
                return None
        return follow

    def _con_seguida(rr, fid):
        """El run seguido entra al tablero aunque no esté entre los últimos
        `limit` (p. ej. corrida vieja retomada). Un fid ilegible/inexistente
        se ignora — jamás tumba el board."""
        if fid and not any((r or {}).get("run_id") == fid for r in rr):
            try:
                return [wf.load_run(fid)] + rr
            except Exception:
                pass
        return rr

    runs = wf.list_runs(limit=limit)
    if not runs:
        print("  (sin runs todavía — `workspace wf run <spec>`)")
        return 0
    if not is_tty:
        # pipe/redirección: render único estático, sin loop (CI-safe)
        fid = _fid()
        shown, extra = _wf_board_pick(_con_seguida(runs, fid), top, fid)
        w, h = _wh()
        print("\n".join(_wf_board_lines(shown, w, h, interval,
                                        live=False, extra=extra,
                                        follow=fid)))
        if not _wf_board_over(shown):
            print(f"  {DIM}(sin TTY: render único — en vivo: "
                  f"workspace wf board){R}")
        return _wf_board_rc(shown)

    out = sys.stdout
    prev_n, ticks = 0, 0
    prev_lines = None                           # último frame pintado (dedupe)
    # persist = el pane derecho del split → PANTALLA ALTERNA (buffer sin
    # scrollback): pane FIJO, sin apilar y sin scroll que rompa. `wf board`
    # suelto (no persist) sigue inline en la terminal del socio, como siempre.
    alt = persist
    out.write(("\033[?1049h\033[2J\033[H" if alt else "") + "\033[?25l")
    try:
        while True:
            fid = _fid()                        # follow POR tick (active_run
            shown, extra = _wf_board_pick(      # fresco: retarget en vivo)
                _con_seguida(runs, fid), top, fid)
            w, h = _wh()                        # tamaño POR tick (resize vivo)
            new_lines = _wf_board_lines(shown, w, h, interval, live=True,
                                        extra=extra, follow=fid)
            if new_lines != prev_lines:         # repinta SOLO si cambió → en
                prev_n = _wf_watch_paint(new_lines, prev_n, out)  # idle (nada
                prev_lines = new_lines          # corre) no repinta = cero flicker
            if _wf_board_over(shown) and not persist:
                return _wf_board_rc(shown)      # nada corre → frame final queda
            # persist: nada corre pero seguimos vivos, repintando EN SITIO
            # (sin clear) hasta que aparezca otro run → cero parpadeo.
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                return 0                        # tope de ticks (tests/corte)
            sleep(interval)
            nuevos = wf.list_runs(limit=limit)  # re-leer del disco
            if nuevos:
                runs = nuevos                   # lectura vacía transitoria:
                                                # conserva el último estado
    except KeyboardInterrupt:
        out.write("\n")
        print(f"  {DIM}tablero detenido — los runs siguen en disco: "
              f"workspace wf runs{R}")
        return 0
    finally:
        out.write("\033[?25h" + ("\033[?1049l" if alt else ""))  # cursor + buffer
        out.flush()


def _wf_board_args(rest):
    """(top, interval, follow, persist) de `wf board` — flags con valor
    consumido (mismo patrón que _wf_watch_args). Valores malos → default,
    jamás revienta. `--follow <run-id>` fija la corrida a seguir; `--follow
    active` (la costura del split) la lee de workflows.active_run() en cada
    tick. `--persist` (flag): no salir cuando nada corre — repinta en sitio
    esperando el próximo run (lo usa el pane derecho del split, sin parpadeo)."""
    top, interval, follow, persist = 4, 1.0, None, False
    for i, a in enumerate(rest):
        if a == "--persist":
            persist = True
        if a == "--interval" and i + 1 < len(rest):
            try:
                interval = float(rest[i + 1])
            except ValueError:
                pass
        elif a == "--top" and i + 1 < len(rest):
            try:
                top = max(1, min(12, int(rest[i + 1])))
            except ValueError:
                pass
        elif a == "--follow" and i + 1 < len(rest) \
                and not rest[i + 1].startswith("-"):
            follow = rest[i + 1]
    return top, interval, follow, persist


def _wf_flags(rest):
    """Parsea flags con valor de `wf run/resume` (--driver/--backend/--model/
    --param). Devuelve (vals, params, consumidos) — `consumidos` son los
    índices de los VALORES de flags, para que el posicional (spec/run-id) no
    se confunda con ellos (p. ej. `--driver real <spec>`)."""
    vals, params, consumed = {}, {}, set()
    for i, a in enumerate(rest):
        if a in ("--driver", "--backend", "--model") and i + 1 < len(rest):
            vals[a] = rest[i + 1]
            consumed.add(i + 1)
        elif a == "--param" and i + 1 < len(rest) and "=" in rest[i + 1]:
            k, _, v = rest[i + 1].partition("=")
            params[k.strip()] = v.strip()
            consumed.add(i + 1)
    return vals, params, consumed


def _wf_driver(vals):
    """`--driver` → callable driver (o None = stub honesto, el DEFAULT).
    Levanta ValueError con detalle si el nombre no existe."""
    from workflows import driver as wfdriver
    return wfdriver.resolve(vals.get("--driver"),
                            backend=vals.get("--backend"),
                            model=vals.get("--model"))


def cmd_wf(args):
    """`workspace wf new <nombre> | list | match "<texto>" | run <spec> [--dry]
    [--param k=v]
    [--driver real [--backend B] [--model M]] | runs | show <run-id> [--watch] |
    watch <run-id> [--interval S] | board [--top N] [--interval S]
    [--follow <run-id>|active] |
    status [<run-id>] | decide <run-id> <paso> approve|reject [--note …] |
    gate <run-id> [--step <paso>] [--open] |
    resume <run-id> [--driver real …] | stats` —
    pipelines declarativos (workflows/MAPA.md):
    specs congelados + runner con verify determinista por paso. Hermano de
    feature/integrate/promote. `new` ANDAMIA un spec guiado (nace válido,
    con notas por campo — semilla del workflow-que-crea-workflows). DEFAULT:
    los pasos agent son STUBS declarados;
    `--driver real` (opt-in) los despacha vía headless con tools OFF
    (contrato read-execute-commit, workflows/driver.py). `--dry` jamás
    despacha."""
    import workflows as wf
    sub = args[0] if args else "list"
    rest = args[1:]
    if sub == "new":
        # andamiar un spec GUIADO: esqueleto comentado (det·agent·human) que
        # nace VÁLIDO — un socio no-programador parte de algo que funciona.
        name = next((a for a in rest if not a.startswith("-")), "")
        if not name:
            print("uso: workspace wf new <nombre>   "
                  "(p. ej. workspace wf new mi-flujo)")
            print(f"  {DIM}crea workflows/specs/<nombre>.json — un esqueleto "
                  f"guiado con un paso de cada tipo (det · agent · human) y "
                  f"notas que explican cada campo{R}")
            return 2
        try:
            path = wf.new_spec(name)
        except FileExistsError as e:
            print(f"WORKSPACE: {e}")
            return 2
        except ValueError as e:
            print(f"WORKSPACE: {e}")
            return 2
        base = os.path.basename(path)[:-5]
        # reporte del validador — el esqueleto nace válido por contrato, pero
        # el socio merece VER el resultado del check, no fe:
        try:
            wf.load_spec(base)
            print(f"\n  {B}◆ workflow `{base}` creado{R} — esqueleto guiado "
                  f"con 3 pasos de ejemplo {DIM}(det · agent · human){R}")
            print(f"  {OK}✓ validado{R} {DIM}(validate_spec: forma, contrato "
                  f"y referencias en orden){R}")
        except (ValueError, FileNotFoundError) as e:
            print(f"\n  {B}◆ workflow `{base}` creado{R} — 📄 {path}")
            print(f"  {ERR}✗ el validador encontró un problema:{R} {e}")
            return 1
        print(f"  📄 {path}")
        print(f"\n  {DIM}siguiente:{R}")
        print(f"    · edita el archivo — cada paso trae una `note:` que "
              f"explica sus campos")
        print(f"    · {B}workspace wf run {base} --dry{R} {DIM}— ensayo: valida "
              f"y muestra qué haría, sin ejecutar nada{R}")
        print(f"    · {B}workspace wf run {base}{R} {DIM}— correr de verdad · "
              f"verlo en vivo: workspace wf board{R}")
        return 0
    if sub == "match":
        # candidatos DETERMINISTAS para un texto de tarea (cero LLM): la base
        # del propose-first — el agente PROPONE en el chat («hay un workflow
        # para esto, ¿lo corro?»); aquí solo se calcula, jamás se arranca nada.
        texto = " ".join(a for a in rest if not a.startswith("-")).strip()
        if not texto:
            print("uso: workspace wf match \"<texto de la tarea>\"")
            print(f"  {DIM}devuelve los workflows candidatos — por "
                  f"`triggers:` del spec; sin triggers, por nombre/nota. "
                  f"Solo propone: no corre nada.{R}")
            return 2
        cands = wf.match_specs(texto)
        if not cands:
            print(f"  {DIM}ninguno — ningún workflow coincide con esa tarea "
                  f"(specs: workspace wf list){R}")
            return 1
        print(f"\n  {B}workflows candidatos{R} {DIM}para:{R} {texto}")
        for c in cands:
            print(f"    · {B}{c['name']}{R} {DIM}— empata: "
                  f"{', '.join(c['hits'])} ({c['via']}){R}")
        print(f"\n  {DIM}correr el mejor: workspace wf run "
              f"{cands[0]['name']}{R}")
        return 0
    if sub in ("list", "ls"):
        specs = wf.list_specs()
        if not specs:
            print("  (sin specs en workflows/specs/)")
            return 0
        print(f"\n  {B}workflows disponibles{R} {DIM}(workflows/specs/){R}")
        for s in specs:
            if "error" in s:
                print(f"    ✗ {s['name']} — {DIM}{s['error']}{R}")
                continue
            kinds = " ".join(f"{k}:{n}" for k, n in sorted(s["kinds"].items()))
            print(f"    · {s['name']} v{s['version']} — {s['steps']} pasos "
                  f"{DIM}({kinds}){R}")
        print(f"\n  {DIM}correr: workspace wf run <spec> [--dry] "
              f"[--param k=v]{R}")
        return 0

    if sub in ("steps", "pasos", "catalogo", "catálogo"):
        # el catálogo VIVO de pasos det (la "API de datos" del autor, que
        # workflows/AUTHORING.md referencia): nombre + qué produce cada uno.
        # Un autor consulta esto para escribir `run:`/`reads:`/`when:` sin
        # leer el fuente — y para saber qué NO existe (= primitiva nueva).
        from workflows import steps as _steplib
        names = _steplib.known()
        print(f"\n  {B}pasos det registrados{R} {DIM}(steps.known() · úsalos en "
              f"run:/verify:){R}")
        for n in names:
            prod = _steplib.produces_of(n)
            if prod is None:
                pstr = f"{DIM}(contrato opaco){R}"
            elif prod:
                pstr = f"{DIM}produce: {', '.join(prod)}{R}"
            else:
                pstr = f"{DIM}(no produce artefactos){R}"
            print(f"    · {n}  {pstr}")
        print(f"\n  {DIM}el que necesites NO está aquí = primitiva nueva → es "
              f"código (Turing+revisión), no composición. Guía: "
              f"workflows/AUTHORING.md{R}")
        return 0
    if sub == "run":
        vals, params, consumed = _wf_flags(rest)
        name = next((a for i, a in enumerate(rest)
                     if not a.startswith("-") and i not in consumed), "")
        if not name:
            print("uso: workspace wf run <spec> [--dry] [--param k=v] "
                  "[--driver real [--backend B] [--model M]]")
            return 2
        dry = "--dry" in rest or "--dry-run" in rest
        try:
            drv = _wf_driver(vals)
            state = wf.start(name, dry=dry, params=params, driver=drv)
        except (ValueError, FileNotFoundError) as e:
            print(f"WORKSPACE: {e}")
            return 2
        _wf_print_run(state)
        return 0 if state["status"] in ("done", "paused_human") else 1
    if sub == "resume":
        vals, _params, consumed = _wf_flags(rest)
        rid = next((a for i, a in enumerate(rest)
                    if not a.startswith("-") and i not in consumed), "")
        if not rid:
            print("uso: workspace wf resume <run-id> "
                  "[--driver real [--backend B] [--model M]]")
            return 2
        try:
            drv = _wf_driver(vals)
            state = wf.resume(rid, driver=drv)
        except FileNotFoundError:
            print(f"WORKSPACE: no conozco el run '{rid}' (ver `workspace wf runs`)")
            return 2
        except ValueError as e:
            print(f"WORKSPACE: {e}")
            return 2
        _wf_print_run(state)
        # `rejected` = decisión del socio APLICADA con éxito (terminal, no error)
        return 0 if state["status"] in ("done", "paused_human", "rejected") else 1
    if sub == "decide":
        # registrar la decisión del socio sobre un gate PAUSADO (v1.3):
        # solo ESCRIBE decisions[paso] — aplicarla es `workspace wf resume`.
        note, rest2 = "", list(rest)
        if "--note" in rest2:
            i = rest2.index("--note")
            if i + 1 < len(rest2):
                note = rest2[i + 1]
                del rest2[i:i + 2]
            else:
                rest2.remove("--note")
        pos = [a for a in rest2 if not a.startswith("-")]
        if len(pos) < 3:
            print("uso: workspace wf decide <run-id> <paso> approve|reject "
                  "[--note \"…\"]")
            return 2
        rid, step, decision = pos[0], pos[1], pos[2]
        try:
            rec = wf.record_decision(rid, step, decision, note)
        except FileNotFoundError:
            print(f"WORKSPACE: no conozco el run '{rid}' (ver `workspace wf runs`)")
            return 2
        except ValueError as e:
            print(f"WORKSPACE: {e}")
            return 2
        mark = f"{OK}✓ APPROVE{R}" if rec["decision"] == "approve" \
            else f"{ERR}⊗ REJECT{R}"
        print(f"\n  {mark} registrado para el paso {B}{step}{R} de {DIM}{rid}{R}"
              + (f"\n  {DIM}nota: {rec['note']}{R}" if rec["note"] else ""))
        print(f"  {DIM}aplicar la decisión: workspace wf resume {rid}{R}")
        return 0
    if sub == "gate":
        # (re)genera el HTML Lavish del gate en pausa (workflows/lavish.py)
        # y opcionalmente lo abre en el browser (`--open`). No muta el run.
        from workflows import lavish
        rest2 = list(rest)
        step = ""
        if "--step" in rest2:
            i = rest2.index("--step")
            if i + 1 < len(rest2):
                step = rest2[i + 1]
                del rest2[i:i + 2]
        opn = "--open" in rest2
        rid = next((a for a in rest2 if not a.startswith("-")), "")
        if not rid:
            print("uso: workspace wf gate <run-id> [--step <paso>] [--open]  "
                  "(lista: workspace wf runs)")
            return 2
        try:
            state = wf.load_run(rid)
        except (FileNotFoundError, ValueError):
            print(f"WORKSPACE: no conozco el run '{rid}' (ver `workspace wf runs`)")
            return 2
        waiting = [s["id"] for s in state.get("steps") or []
                   if s.get("status") == "waiting_human"]
        if not step:
            step = waiting[0] if waiting else ""
        if not step or step not in waiting:
            print(f"WORKSPACE: el run '{rid}' no está esperando decisión"
                  + (f" en el paso '{step}'" if step else "")
                  + " — el gate Lavish presenta un paso en pausa.")
            return 2
        try:
            path = lavish.write_gate(state, step)
        except (ValueError, OSError) as e:
            print(f"WORKSPACE: no pude generar el gate: {e}")
            return 2
        print(f"\n  {B}◆ gate Lavish{R} del paso {B}{step}{R} — "
              f"decide en el browser (Aprobar/Rechazar + anotación)")
        print(f"  📄 {path}")
        if opn:
            lavish.open_in_browser(path)
        else:
            print(f"  {DIM}abrir: workspace wf gate {rid} --open · aplicar la "
                  f"decisión: workspace wf resume {rid}{R}")
        return 0
    if sub == "runs":
        # lista de corridas persistidas (render puro en _wf_runs_lines)
        print("\n".join(_wf_runs_lines(wf.list_runs(limit=15))))
        return 0
    if sub == "watch":
        rid, interval = _wf_watch_args(rest)
        if not rid:
            print("uso: workspace wf watch <run-id> [--interval S]  "
                  "(lista: workspace wf runs)")
            return 2
        try:
            return _wf_watch(rid, interval=interval)
        except (FileNotFoundError, ValueError):
            print(f"WORKSPACE: no conozco el run '{rid}' "
                  f"(ver `workspace wf runs`)")
            return 2
    if sub in ("board", "tablero"):
        # el split de pipelines: varias corridas EN VIVO, lado a lado;
        # --follow <run-id>|active clava el tablero en UNA corrida (▸)
        top, interval, follow, persist = _wf_board_args(rest)
        return _wf_board(top=top, interval=interval, follow=follow,
                         persist=persist)
    if sub in ("status", "show"):
        if "--watch" in rest:
            # `wf show <id> --watch` = alias de `wf watch <id>` (aditivo)
            return cmd_wf(["watch"] + [a for a in rest if a != "--watch"])
        rid = next((a for a in rest if not a.startswith("-")), "")
        if rid:
            try:
                _wf_print_run(wf.load_run(rid))
                return 0
            except (FileNotFoundError, ValueError):
                print(f"WORKSPACE: no conozco el run '{rid}' "
                      f"(ver `workspace wf runs`)")
                return 2
        if sub == "show":
            print("uso: workspace wf show <run-id>  (lista: workspace wf runs)")
            return 2
        print("\n".join(_wf_runs_lines(wf.list_runs(limit=10))))
        return 0
    if sub == "stats":
        agg = wf.stats()
        if not agg:
            print("  (sin runs todavía — nada que medir)")
            return 0
        for wname, w in sorted(agg.items()):
            print(f"\n  {B}{wname}{R} — {w['runs']} runs "
                  f"{DIM}(done {w['done']} · failed {w['failed']} · "
                  f"paused {w['paused']} · rejected {w.get('rejected', 0)} · "
                  f"dry {w['dry']}){R}")
            for sid, row in w["steps"].items():
                if not row["runs"]:
                    continue
                print(f"    · {sid}: {row['runs']} corridas · "
                      f"{row['fails']} fallos · {row['attempts']} intentos")
        return 0
    print("uso: workspace wf new <nombre> | list | match \"<texto>\" | "
          "run <spec> [--dry] [--param k=v] "
          "[--driver real] | runs | show <run-id> [--watch] | "
          "watch <run-id> [--interval S] | board [--top N] [--interval S] "
          "[--follow <run-id>|active] | "
          "status [<run-id>] | decide <run-id> <paso> approve|reject "
          "[--note …] | gate <run-id> [--step <paso>] [--open] | "
          "resume <run-id> [--driver real] | stats")
    return 2


def _valid_branch_name(branch):
    """¿Es `branch` un nombre de rama SEGURO para pasar a git/derivar una ruta?

    Guarda anti-inyección/escape-de-ruta (regresión que el merge de feat dejó
    caer; contrato heredado del cmd_worktree previo): solo letras/dígitos y
    `._/-` (permite el prefijo `feat/…`). Rechaza vacío, `-` inicial (git lo
    leería como flag), `/` al inicio/fin, y `..` (git lo prohíbe en refs y evita
    escapes de ruta al derivar el worktree)."""
    import re
    return bool(branch) and bool(re.fullmatch(r"[A-Za-z0-9._/-]+", branch)) \
        and not branch.startswith("-") and ".." not in branch \
        and not branch.endswith("/") and not branch.startswith("/")


def _worktree_slug(branch):
    """Nombre de carpeta para el worktree de `branch` (sin '/')."""
    return branch.replace("/", "-")


def _worktree_path(branch):
    """Ruta del worktree de `branch`: hermano de ROOT, en `<repo>-trees/<slug>`
    (misma convención que los worktrees ya existentes del equipo)."""
    parent = os.path.dirname(ROOT)
    return os.path.join(parent, os.path.basename(ROOT) + "-trees",
                        _worktree_slug(branch))


def cmd_worktree(args):
    """`workspace worktree …` — toma una rama en un worktree aparte y REGISTRA al
    agente dueño, para que el dashboard de DEV marque la rama como "en uso por
    <agente>" (no la toques) vs libre.

      workspace worktree <rama> [--agent <nombre>]   reusa un árbol tibio del pool
                                                   (o crea worktree) + registra dueño
      workspace worktree rm <rama>                   quita worktree + limpia registry
      workspace worktree list                        lista worktrees (con su dueño)
      workspace worktree pool                        estado del pool tibio
      workspace worktree pool free <name>            devuelve un lease colgado
                                                   (solo si el árbol está limpio)
      workspace worktree prune [--agent <x>] [-n]    barre los worktrees LIMPIOS
                                                   colgados + limpia el registry

    POOL TIBIO: los worktrees creados aquí se enrolan a un pool per-máquina; al
    liberarse (SessionEnd/prune) NO se destruyen — quedan detached y limpios con
    sus IGNORADOS intactos (node_modules/.venv), y el próximo `workspace worktree`
    los reusa sin reinstalar deps. Regla de oro intacta: nada sucio se toca.

    `prune` es el fallback MANUAL de la auto-limpieza del harness (el hook
    SessionEnd libera solo los worktrees del agente que cierra). NUNCA remueve un
    worktree con cambios sin commitear; `-n`/`--dry-run` muestra qué haría.

    El registry es per-máquina (no se versiona): ~/.claude/workspace/worktree-owners.json.
    Solo del repo de EQUIPO. Imprime cada git que corre."""
    ok, subprocess = _branch_guard()
    if not ok:
        print("WORKSPACE: `worktree` no disponible (no es el repo de equipo).")
        return 1
    from dash.dev import _worktrees, _git as devgit

    sub = args[0] if args else ""

    # ── list (alias: ls): el git real + el dueño registrado de cada rama ─────
    if sub in ("list", "ls"):
        cmd = ["git", "-C", ROOT, "worktree", "list"]
        print(f"  {DIM}$ {' '.join(cmd)}{R}")
        subprocess.call(cmd)
        owners = _worktrees.load_owners()
        wt = devgit._worktree_branches(ROOT)
        if wt:
            print()
            for branch, path in sorted(wt.items()):
                agent = (owners.get(branch) or {}).get("agent") or "?"
                print(f"  {C}{branch}{R} {DIM}· en uso por{R} {B}{agent}{R}")
        else:
            print(f"  {DIM}(sin worktrees separados — todas las ramas libres){R}")
        return 0

    # ── prune: barre worktrees LIMPIOS colgados (fallback manual de la auto-
    #    limpieza estructural; jamás toca uno con cambios sin commitear) ────────
    if sub == "prune":
        agent = None
        if "--agent" in args:
            i = args.index("--agent")
            if i + 1 < len(args):
                agent = args[i + 1]
        dry = "--dry-run" in args or "-n" in args
        res = _worktrees.release(agent=agent, dry_run=dry)
        scope = f" de {B}{agent}{R}" if agent else ""
        head = "[dry-run] " if dry else ""
        if res["removed"]:
            verb = "se removerían" if dry else "removidos"
            print(f"  {C}✓ {head}worktrees limpios {verb}{scope}:{R} "
                  + ", ".join(res["removed"]))
        if res.get("pooled"):
            verb = "volverían" if dry else "devueltos"
            print(f"  {C}✓ {head}árboles tibios {verb} al pool{scope}:{R} "
                  + ", ".join(res["pooled"]))
        if res["skipped_dirty"]:
            print(f"  {B}⚠ cambios sin commitear (intactos):{R} "
                  + ", ".join(res["skipped_dirty"]))
        if res["stale"]:
            print(f"  {DIM}· entradas huérfanas limpiadas del registry:{R} "
                  + ", ".join(res["stale"]))
        if res["failed"]:
            print(f"  {DIM}· no se pudo confirmar/remover (se dejan):{R} "
                  + ", ".join(res["failed"]))
        if not any(res.values()):
            print(f"  {DIM}(sin worktrees colgados{scope} — nada que limpiar){R}")
        return 0

    # ── pool: estado del pool tibio + rescate manual de leases colgados ──────
    if sub == "pool":
        act = args[1] if len(args) > 1 else ""
        if act == "free":
            name = args[2] if len(args) > 2 else ""
            if not name:
                print("uso: workspace worktree pool free <name>")
                return 2
            st = _worktrees.pool_return(name=name)
            msgs = {
                "freed": f"  {C}✓ `{name}` devuelto al pool{R} {DIM}(libre, "
                         f"ignorados intactos).{R}",
                "dirty": f"  {B}⚠ `{name}` tiene cambios sin commitear{R} "
                         f"{DIM}— intocable (regla de oro). Revísalo a mano.{R}",
                "missing": f"  {DIM}· `{name}`: el árbol ya no existe — token "
                           f"limpiado.{R}",
                "not_pooled": f"  {DIM}· `{name}`: no hay lease con ese nombre "
                              f"(ver `workspace worktree pool`).{R}",
            }
            print(msgs.get(st, f"  {B}⚠ no pude devolver `{name}`{R} "
                                f"{DIM}(git falló — se queda como está).{R}"))
            return 0 if st in ("freed", "missing") else 1
        entries = _worktrees.pool_list()
        if not entries:
            print(f"  {DIM}(pool vacío — los worktrees que crees aquí se "
                  f"enrolan solos y quedan tibios al liberarse){R}")
            return 0
        for e in entries:
            lease = e.get("lease") or {}
            extra = (f" {DIM}· lease:{R} {B}{lease.get('agent', '?')}{R}"
                     f"{DIM} ({lease.get('branch') or '—'}){R}"
                     if e["state"] == "leased" else "")
            mark = {"free": C + "libre " + R, "leased": B + "en uso" + R,
                    "dirty": B + "sucio " + R}.get(e["state"], e["state"])
            print(f"  {mark}  {e['name']}  {DIM}{e['path']}{R}{extra}")
        return 0

    # ── rm: quita el worktree y limpia el registry ───────────────────────────
    if sub in ("rm", "remove", "delete"):
        branch = next((a for a in args[1:] if not a.startswith("-")), "")
        if not branch:
            print("uso: workspace worktree rm <rama>")
            return 2
        if not _valid_branch_name(branch):
            print(f"WORKSPACE: '{branch}' no es un nombre de rama válido.")
            print(f"  {DIM}usa letras, dígitos, '.', '_', '/' y '-' (ej: feat/menu).{R}")
            return 2
        # Ruta real del árbol: la del registry si existe (un árbol reusado del
        # pool NO vive en la ruta derivada de la rama); fallback a la derivada.
        entry = _worktrees.load_owners().get(branch)
        entry = entry if isinstance(entry, dict) else {}
        wt_path = (entry.get("path") or "").strip() or _worktree_path(branch)
        cmd = ["git", "-C", ROOT, "worktree", "remove", wt_path]
        print(f"  {DIM}$ {' '.join(cmd)}{R}")
        rc = subprocess.call(cmd)
        # Limpia el registry pase lo que pase: la entrada NO debe quedar colgada.
        _worktrees.clear(branch)
        if rc == 0:
            # El árbol ya no existe → su token del pool (si había) sale también.
            _worktrees.pool_drop(path=wt_path)
        if rc != 0:
            print(f"\n  {B}⚠ `git worktree remove` falló{R} {DIM}(¿ruta distinta o "
                  f"cambios sin commitear en el worktree?). Registry limpiado igual.{R}")
            return rc
        print(f"\n  {C}✓ Worktree de `{branch}` removido{R} — la rama queda libre.")
        return 0

    # ── crear: worktree de <rama> + registrar al agente dueño ────────────────
    # rama posicional: ignora el VALOR de --agent (mismo skip-set que cmd_release;
    # sin él, `worktree --agent turing feat/x` tomaba "turing" como rama).
    skip = set()
    if "--agent" in args:
        skip.add(args.index("--agent") + 1)
    branch = next((a for i, a in enumerate(args)
                   if not a.startswith("-") and i not in skip), "")
    if not branch:
        print("uso: workspace worktree <rama> [--agent <nombre>]")
        print(f"  {DIM}ej: workspace worktree feat/chat --agent turing{R}")
        return 2
    if not _valid_branch_name(branch):
        print(f"WORKSPACE: '{branch}' no es un nombre de rama válido.")
        print(f"  {DIM}usa letras, dígitos, '.', '_', '/' y '-' (ej: feat/menu).{R}")
        return 2
    # ── typo-guard (fix `worktree ls`): un subcomando desconocido de UNA palabra
    #    NO debe convertirse en rama+worktree fantasma. Una rama NUEVA debe LUCIR
    #    como rama ('/' o '-', ej. feat/x, fix-y); una palabra suelta que además
    #    no es ref existente se trata como typo → uso y exit 2, jamás `add -b`.
    if ("/" not in branch and "-" not in branch
            and not _git_ref_exists(subprocess, branch)):
        print(f"WORKSPACE: '{branch}' no es un subcomando de `worktree` ni una rama "
              f"existente.")
        print(f"  {DIM}subcomandos: list (ls) · rm <rama> · pool · prune{R}")
        print(f"  {DIM}para crear una rama nueva usa un nombre con '/' o '-' "
              f"(ej: feat/{branch}).{R}")
        return 2
    agent = None
    if "--agent" in args:
        i = args.index("--agent")
        if i + 1 < len(args):
            agent = args[i + 1]

    wt_path = _worktree_path(branch)
    if os.path.exists(wt_path):
        print(f"WORKSPACE: ya existe {wt_path}. "
              f"{DIM}Quítalo con `workspace worktree rm {branch}` o usa otra rama.{R}")
        return 1

    # ── Pool tibio: ANTES de crear uno nuevo, reusar un árbol libre+limpio ───
    # pool_acquire reclama atómicamente (dos gets concurrentes jamás reciben el
    # mismo árbol), verifica limpieza y lo deja pristino PRESERVANDO ignorados
    # (node_modules/.venv sobreviven → cero reinstalación de deps).
    got = None
    try:
        got = _worktrees.pool_acquire(repo=ROOT, agent=agent, branch=branch)
    except Exception:
        got = None                     # el pool jamás bloquea la creación normal
    if got:
        tree = got["path"]
        r = subprocess.run(["git", "-C", tree, "rev-parse", "--verify",
                            "--quiet", branch], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        if r.returncode == 0:          # rama existente → tomarla en el árbol
            cmd = ["git", "-C", tree, "switch", branch]
        else:
            # Rama nueva → nace donde está ROOT (paridad con `worktree add -b`).
            h = subprocess.run(["git", "-C", ROOT, "rev-parse", "HEAD"],
                               capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            start = h.stdout.strip() if h.returncode == 0 else ""
            cmd = (["git", "-C", tree, "switch", "-c", branch]
                   + ([start] if start else []))
        print(f"  {DIM}$ {' '.join(cmd)}{R}")
        rc = subprocess.call(cmd)
        if rc == 0:
            _worktrees.register(branch, agent, tree, pool=True)
            print(f"\n  {C}✓ Worktree de `{branch}`{R} en {DIM}{tree}{R} "
                  f"{C}(árbol tibio reusado del pool){R}")
            print(f"  {DIM}dueño: {B}{agent or '?'}{R}{DIM} — deps/ignorados "
                  f"preservados; al liberarse vuelve al pool.{R}")
            return 0
        # switch falló (¿rama tomada en otro worktree?) → devolver el árbol
        # (está limpio: recién reseteado) y caer a la creación normal.
        _worktrees.pool_return(path=tree)
        print(f"  {DIM}(no pude tomar `{branch}` en el árbol del pool — "
              f"creo un worktree nuevo){R}")

    exists = _git_ref_exists(subprocess, branch)
    # Rama existente → la tomamos; no existe → la creamos en el worktree (-b).
    cmd = (["git", "-C", ROOT, "worktree", "add", wt_path, branch] if exists
           else ["git", "-C", ROOT, "worktree", "add", "-b", branch, wt_path])
    print(f"  {DIM}$ {' '.join(cmd)}{R}")
    rc = subprocess.call(cmd)
    if rc != 0:
        print(f"\n  ✗ No pude crear el worktree de `{branch}` "
              f"{DIM}(¿la rama ya está tomada en otro worktree?).{R}")
        return rc

    _worktrees.register(branch, agent, wt_path, pool=True)
    # Enrolado al pool (nace leased): al liberarse se devuelve TIBIO — el
    # próximo `workspace worktree` lo reusa con node_modules/.venv intactos.
    try:
        _worktrees.pool_enroll(wt_path, ROOT, agent=agent, branch=branch,
                               leased=True)
    except Exception:
        pass                           # el pool es mejora, nunca rompe el alta
    print(f"\n  {C}✓ Worktree de `{branch}`{R} en {DIM}{wt_path}{R}")
    print(f"  {DIM}dueño: {B}{agent or '?'}{R}{DIM} — el dashboard de DEV la marcará "
          f"\"en uso\".{R}")
    return 0


def cmd_uninstall(args):
    """`workspace uninstall` — desinstala WORKSPACE de ESTA máquina (comando + launchers,
    estado per-máquina, bloques de shell, tema y la carpeta del harness). NO toca los
    cerebros (agentes) ni los transcripts. Confirma salvo --yes; --dry-run para ver."""
    import subprocess
    script = os.path.join(ROOT, "uninstall.py")
    if not os.path.isfile(script):
        print(_t("cli.uninstall.missing",
                 "WORKSPACE: no encuentro uninstall.py en el harness."))
        return 1
    return subprocess.call([sys.executable, script] + list(args or []))


def cmd_eval(args):
    """`workspace eval <agente>` — corre el golden set del agente → scorecard
    (mide la calidad antes de lanzar; protocols/agent-creation/03-QUALITY-BAR.md)."""
    import eval_runner, datetime
    name = next((a for a in (args or []) if not a.startswith("-")), "")
    if not name:
        print("uso: workspace eval <agente> [--limit N] [--json]")
        return 2
    entry = dispatch.find_agent(name)
    if not entry:
        print(f"WORKSPACE: no conozco al agente '{name}'  (dispatch.py --list)")
        return 1
    try:
        cfg = dispatch.load_agent_cfg(entry)
        brain = dispatch.resolve_brain(entry["name"], cfg)
    except Exception as e:
        print(f"WORKSPACE: no pude resolver el cerebro de '{name}': {e}")
        return 1
    if not brain or not os.path.isdir(brain):
        print(f"WORKSPACE: no encuentro el cerebro de '{name}'")
        return 1
    limit = None
    if "--limit" in args:
        try:
            limit = int(args[args.index("--limit") + 1])
        except (ValueError, IndexError):
            print("WORKSPACE: --limit requiere un entero")
            return 2
    rep = eval_runner.run(brain, limit=limit,
                          stamp=datetime.date.today().isoformat())
    if "--json" in args:
        import json as _json
        print(_json.dumps(rep, ensure_ascii=False, indent=2))
    if rep.get("error") == "empty":            # sin golden set ≠ fallo real
        print(f"WORKSPACE: '{name}' no tiene golden set "
              f"(STATE/evals/golden-set.jsonl) — no pasa el launch gate")
        return 3
    return 0 if rep.get("results") else 1


def cmd_bus(args):
    """`workspace bus <watch|stop|log|once|status>` — delegación autónoma segura
    (bus automático v1). watch = daemon que atiende el bus solo para agentes
    opt-in (turing+atlas), con enforcement por construcción (sandbox + tools
    read-only). stop = kill-switch. Ver research/design/bus-automatico/PLAN.md."""
    try:
        import bus_daemon
    except Exception as e:
        print(_t("cli.load_fail", "WORKSPACE: no pude cargar {what}: {err}",
                 what="bus_daemon.py", err=e))
        return 1
    return bus_daemon.main(args)


def cmd_calendario(args):
    """`workspace calendario` - pantalla completa para EDITAR la agenda: mes
    navegable, eventos del dia, alta/edicion/baja con una tecla. El hub deja
    agregar con Enter; esto es para todo lo demas. Logica: calendario_tui."""
    try:
        import calendario_tui
    except Exception as e:
        print(_t("cli.load_fail", "WORKSPACE: no pude cargar {what}: {err}",
                 what="calendario_tui.py", err=e))
        return 1
    return calendario_tui.run()


def cmd_tono(args):
    """`workspace tono [dial] [1-5]` — los NIVELES de personalidad de los
    agentes (amabilidad · sarcasmo · longitud · formalidad · iniciativa).
    Se guardan como settings `tono.*` (per-máquina) y los inyecta el hook
    SessionStart al abrir sesión. Lógica y textos: personalidad.py."""
    try:
        import personalidad
    except Exception as e:
        print(_t("cli.load_fail", "WORKSPACE: no pude cargar {what}: {err}",
                 what="personalidad.py", err=e))
        return 1
    return personalidad.main(args)


def cmd_personal(kind, args):
    """`workspace agenda [add|rm|list]` — tu agenda local, la que muestra el
    Calendario.
    Store local per-máquina: ~/.claude/workspace/personal.json
    (no se sincroniza, no lo ve nadie más). La lógica vive en personal.py."""
    try:
        import personal
    except Exception as e:
        print(_t("cli.load_fail", "WORKSPACE: no pude cargar {what}: {err}",
                 what="personal.py", err=e))
        return 1
    return personal.main([kind] + list(args))


def cmd_voice(args):
    """`workspace voice` — dictado por voz GLOBAL, local (whisper.cpp). TOGGLE:
    1er toque graba el micro; 2º transcribe y PEGA en el cursor. `--check`
    reporta qué falta; `--setup` lo instala. Se enlaza a un atajo de teclado
    (Atajos de macOS)."""
    try:
        import voice
    except Exception as e:
        print(_t("cli.load_fail", "WORKSPACE: no pude cargar {what}: {err}",
                 what="voice.py", err=e))
        return 1
    return voice.main(args)


# ──────────────────────────────────────────────────────────────────────────
#  workspace mail — enviar correo por SMTP (Gmail App Password, sin OAuth)
#
#  Credenciales SOLO per-máquina: env (WORKSPACE_SMTP_USER/PASS) o el archivo
#  ~/.claude/workspace/mail.json (0600, FUERA de git). NUNCA hardcodeadas ni
#  escritas al repo. El comando es acción HACIA AFUERA → default seguro:
#  --dry-run para previsualizar; sin envío automático silencioso.
# ──────────────────────────────────────────────────────────────────────────
def _mail_config_path():
    """Ruta del archivo de credenciales SMTP per-máquina (función, no constante:
    respeta el HOME parchado en tests). En Windows cae en el perfil del usuario."""
    return os.path.join(_paths.state_dir(), "mail.json")


def _mail_load_creds():
    """Resuelve las credenciales SMTP. Prioridad: (1) env WORKSPACE_SMTP_USER /
    WORKSPACE_SMTP_PASS, (2) ~/.claude/workspace/mail.json. host/port: env
    WORKSPACE_SMTP_HOST / WORKSPACE_SMTP_PORT → mail.json → default Gmail.

    Devuelve (creds, error). creds = {user, pass, host, port} si user y pass
    están; si falta cualquiera → (None, mensaje claro de cómo configurarlas)."""
    cfg = _read_json(_mail_config_path())     # {} si no existe / ilegible
    user = os.environ.get("WORKSPACE_SMTP_USER") or cfg.get("user")
    passwd = os.environ.get("WORKSPACE_SMTP_PASS") or cfg.get("pass")
    host = os.environ.get("WORKSPACE_SMTP_HOST") or cfg.get("host") or "smtp.gmail.com"
    port = os.environ.get("WORKSPACE_SMTP_PORT") or cfg.get("port") or 587
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 587
    if not user or not passwd:
        msg = (
            f"{B}{_t('mail.creds.missing', '✗ Faltan credenciales SMTP.')}{R}\n"
            f"  {DIM}{_t('mail.creds.why', 'El correo sale por SMTP de Gmail con una App Password (2FA activado), NO tu contraseña normal.')}{R}\n"
            f"  {DIM}{_t('mail.creds.create', 'Crea una en: https://myaccount.google.com/apppasswords')}{R}\n\n"
            f"  {_t('mail.creds.ways', 'Configúralas de UNA de estas formas:')}\n"
            f"    1) {C}workspace mail --setup{R}  {DIM}"
            f"{_t('mail.creds.way1', '(te las pide y crea ~/.claude/workspace/mail.json con permisos 0600)')}{R}\n"
            f"    2) {_t('mail.creds.way2', 'variables de entorno')} {C}WORKSPACE_SMTP_USER{R} "
            f"{_t('mail.creds.and', 'y')} {C}WORKSPACE_SMTP_PASS{R}\n"
        )
        return None, msg
    return {"user": user, "pass": passwd, "host": host, "port": port}, None


def _mail_save_creds(user, passwd, host="smtp.gmail.com", port=587):
    """Escribe mail.json (0600) per-máquina. Devuelve la ruta."""
    path = _mail_config_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 587
    data = {"user": user, "pass": passwd, "host": host, "port": port}
    # Crear con 0600 desde el inicio (no exponer el secreto ni un instante).
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.write("\n")
    finally:
        # os.chmod por si el archivo ya existía con otros permisos (en Windows
        # es parcialmente no-op; el archivo queda en el perfil del usuario).
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    return path


def _mail_parse_recipients(values):
    """Aplana --to repetible y/o separado por comas → lista limpia, sin dups
    preservando el orden."""
    out = []
    for v in values:
        for part in str(v).split(","):
            addr = part.strip()
            if addr and addr not in out:
                out.append(addr)
    return out


def _mail_setup(user=None, passwd=None, host=None, port=None):
    """`workspace mail --setup` — crea ~/.claude/workspace/mail.json (0600) con la
    App Password. Toma valores de flags o, si faltan, los pide por prompt."""
    print(f"{B}{_t('mail.setup.title', 'WORKSPACE · configurar correo (SMTP)')}{R}")
    print(f"  {DIM}{_t('mail.setup.need', 'Necesitas una App Password de Google (con 2FA activado), no tu contraseña normal.')}{R}")
    print(f"  {DIM}{_t('mail.setup.create', 'Crear: https://myaccount.google.com/apppasswords')}{R}\n")
    try:
        # Solo se piden interactivamente los campos REQUERIDOS (user + pass);
        # host/port toman default Gmail salvo que se pasen por flag. Así
        # `workspace mail --setup --user X --pass Y` es no-interactivo.
        if not user:
            user = input(_t("mail.setup.ask_user", "  Correo (user) [ej. tucorreo@dominio.com]: ")).strip()
        if not passwd:
            import getpass
            passwd = getpass.getpass(_t("mail.setup.ask_pass", "  App Password (16 chars, no se muestra): ")).strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  " + _t("mail.setup.cancelled", "cancelado."))
        return 1
    host = host or "smtp.gmail.com"
    port = port or 587
    if not user or not passwd:
        print(f"  {B}{_t('mail.setup.missing', '✗ Falta el correo o la App Password — no escribí nada.')}{R}")
        return 2
    path = _mail_save_creds(user, passwd, host or "smtp.gmail.com", port or 587)
    print(f"\n  {C}{_t('mail.setup.saved', '✓ Guardado en {path}', path=path)}{R} "
          f"{DIM}{_t('mail.setup.saved_note', '(permisos 0600, per-máquina, fuera de git)')}{R}")
    print(f"  {DIM}{_t('mail.setup.try', 'Prueba: workspace mail --to {user} --subject ping --body hola --dry-run', user=user)}{R}")
    return 0


def _mail_send(creds, sender, recipients, subject, body):
    """Envía el correo MIME (UTF-8) por STARTTLS. Devuelve (ok, error_msg).
    Errores de auth/conexión se traducen a mensajes claros (no stacktrace)."""
    import smtplib
    from email.mime.text import MIMEText
    from email.utils import formatdate

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = subject
    msg["From"] = sender
    msg["To"] = ", ".join(recipients)
    msg["Date"] = formatdate(localtime=True)

    try:
        server = smtplib.SMTP(creds["host"], creds["port"], timeout=30)
    except (OSError, smtplib.SMTPException) as e:
        return False, (f"{B}✗ No pude conectar a {creds['host']}:{creds['port']}{R} "
                       f"{DIM}({type(e).__name__}: {e}){R}")
    try:
        server.ehlo()
        server.starttls()
        server.ehlo()
        try:
            server.login(creds["user"], creds["pass"])
        except smtplib.SMTPAuthenticationError as e:
            return False, (
                f"{B}{_t('mail.send.auth', '✗ Autenticación rechazada por el servidor.')}{R}\n"
                f"  {DIM}{_t('mail.send.auth_hint', '¿Es una App Password válida (2FA activado), no tu contraseña normal? Regenera en https://myaccount.google.com/apppasswords')}{R}\n"
                f"  {DIM}({type(e).__name__}){R}")
        server.sendmail(sender, recipients, msg.as_string())
    except smtplib.SMTPException as e:
        return False, (f"{B}{_t('mail.send.error', '✗ Error enviando el correo')}{R} "
                       f"{DIM}({type(e).__name__}: {e}){R}")
    finally:
        try:
            server.quit()
        except Exception:
            pass
    return True, None


_MAIL_USAGE = (
    "uso: workspace mail --to <correo> --subject \"<asunto>\" --body \"<texto>\"\n"
    "                  [--to otro@x.com] [--from <correo>] [--body-file <ruta>]\n"
    "                  [--dry-run|-n]\n"
    "     workspace mail --setup        (configura la App Password de Gmail)\n\n"
    "  --to        destinatario; repetible y/o separado por comas\n"
    "  --subject   asunto\n"
    "  --body      cuerpo (texto)         | --body-file <ruta> lee el cuerpo de un archivo\n"
    "  --from      remitente (default: el usuario configurado)\n"
    "  --dry-run   muestra a quién/asunto/preview SIN enviar\n"
    "  --setup     crea ~/.claude/workspace/mail.json (0600) con tus credenciales\n\n"
    "  Credenciales (per-máquina, NUNCA en git): env WORKSPACE_SMTP_USER/PASS, o\n"
    "  ~/.claude/workspace/mail.json. Requiere una App Password de Google (2FA).\n"
)



def _mail_usage():
    """Uso de `workspace mail` en el idioma de la UI (fuente: _MAIL_USAGE)."""
    return _t("mail.usage", _MAIL_USAGE)

def cmd_mail(args):
    """`workspace mail` — envía correo por SMTP de Gmail (App Password, sin OAuth).

    Default seguro: usa --dry-run para previsualizar antes de mandar. Las
    credenciales viven SOLO per-máquina (env o ~/.claude/workspace/mail.json)."""
    args = list(args or [])
    if "--help" in args or "-h" in args:
        print(_mail_usage())
        return 0

    # ── parseo manual (controla return codes; consistente con el resto) ──
    to_vals, subject, body, body_file, sender = [], None, None, None, None
    user_flag, pass_flag, host_flag, port_flag = None, None, None, None
    dry = setup = False
    i = 0

    def _val(i, flag):
        if i + 1 >= len(args):
            raise ValueError(_t("mail.err.needs_value", "{flag} requiere un valor",
                                flag=flag))
        return args[i + 1]

    try:
        while i < len(args):
            a = args[i]
            if a == "--to":
                to_vals.append(_val(i, a)); i += 2
            elif a == "--subject":
                subject = _val(i, a); i += 2
            elif a == "--body":
                body = _val(i, a); i += 2
            elif a == "--body-file":
                body_file = _val(i, a); i += 2
            elif a == "--from":
                sender = _val(i, a); i += 2
            elif a in ("--dry-run", "-n"):
                dry = True; i += 1
            elif a == "--setup":
                setup = True; i += 1
            elif a == "--user":
                user_flag = _val(i, a); i += 2
            elif a == "--pass":
                pass_flag = _val(i, a); i += 2
            elif a == "--host":
                host_flag = _val(i, a); i += 2
            elif a == "--port":
                port_flag = _val(i, a); i += 2
            else:
                print(_t("mail.err.unknown_opt",
                         "WORKSPACE: opción desconocida '{opt}'", opt=a) + "\n")
                print(_mail_usage())
                return 2
    except ValueError as e:
        print(f"WORKSPACE: {e}\n")
        print(_mail_usage())
        return 2

    if setup:
        return _mail_setup(user_flag, pass_flag, host_flag, port_flag)

    # ── cuerpo: --body directo o --body-file ──
    if body is not None and body_file is not None:
        print(_t("mail.err.body_both", "WORKSPACE: usa --body O --body-file, no ambos."))
        return 2
    if body_file is not None:
        try:
            with open(os.path.expanduser(body_file), encoding="utf-8") as fh:
                body = fh.read()
        except OSError as e:
            print(_t("mail.err.body_file",
                     "WORKSPACE: no pude leer --body-file '{path}' ({err})",
                     path=body_file, err="%s: %s" % (type(e).__name__, e)))
            return 2

    recipients = _mail_parse_recipients(to_vals)
    missing = []
    if not recipients:
        missing.append("--to")
    if not subject:
        missing.append("--subject")
    if body is None:
        missing.append("--body / --body-file")
    if missing:
        print(_t("mail.err.missing", "WORKSPACE: faltan {what}",
                 what=", ".join(missing)) + "\n")
        print(_mail_usage())
        return 2

    # ── credenciales (también define el remitente por default) ──
    creds, err = _mail_load_creds()
    if err:
        print(err)
        return 1
    sender = sender or creds["user"]

    # ── preview (siempre) ──
    preview = body if len(body) <= 500 else body[:500] + "…"
    print(f"{B}{_t('mail.preview.title', '── correo ──')}{R}")
    print(f"  {DIM}{_t('mail.preview.from', 'de:     ')}{R}{sender}")
    print(f"  {DIM}{_t('mail.preview.to', 'para:   ')}{R}{', '.join(recipients)}")
    print(f"  {DIM}{_t('mail.preview.subject', 'asunto: ')}{R}{subject}")
    print(f"  {DIM}{_t('mail.preview.body', 'cuerpo:')}{R}")
    for line in (preview.splitlines() or [""]):
        print(f"    {line}")

    if dry:
        print(f"\n  {DIM}{_t('mail.preview.dry', '(dry-run: no se envió nada)')}{R}")
        return 0

    ok, send_err = _mail_send(creds, sender, recipients, subject, body)
    if not ok:
        print("\n" + send_err)
        return 1
    print(f"\n  {C}{_t('mail.sent', '✓ Enviado a {to}', to=', '.join(recipients))}{R}")
    return 0


# ═══════════════════════════════════════════════════════════════════════════
# workspace board — API de terminal del tablero «Proyectos» del dev panel
# ═══════════════════════════════════════════════════════════════════════════
# Contrato token-eficiente para que los AGENTES (y el socio) lean/editen el MISMO
# board.json que pinta el dev panel, sin levantar el server ni gastar HTTP/token:
# acceso DIRECTO al archivo vía dash.dev.board (reusa sus api_*). Salida compacta
# por default; --json para parseo barato. DEV-ONLY: si dash/dev no está (distro a
# clientes), avisa y sale !=0 — nunca un traceback.
_BOARD_STATUSES = ("idea", "pending", "in-progress", "done")
_STATUS_MARK = {"idea": "·", "pending": "○", "in-progress": "◐", "done": "●"}


def _board_mod():
    """Importa dash.dev.board o None si no está (distro a cliente: dash/dev se
    excluye en make-dist). None → cmd_board avisa solo-dev y sale !=0."""
    try:
        from dash.dev import board as _b
        return _b
    except Exception:
        return None


def _board_flags(rest, valued=(), bools=()):
    """Parser mínimo: separa `rest` en (positionals, opts, error). `valued` =
    flags que toman valor (--project x); `bools` = flags sin valor (--json).
    Soporta también --flag=valor. error != None → uso inválido."""
    pos, opts = [], {}
    i = 0
    while i < len(rest):
        a = rest[i]
        if a in bools:
            opts[a.lstrip("-")] = True
            i += 1
        elif a in valued:
            if i + 1 >= len(rest):
                return None, None, "falta el valor de %s" % a
            opts[a.lstrip("-")] = rest[i + 1]
            i += 2
        elif a.startswith("--") and "=" in a:
            k, v = a[2:].split("=", 1)
            opts[k] = v
            i += 1
        else:
            pos.append(a)
            i += 1
    return pos, opts, None


def _board_err(msg):
    print(f"{ERR}✗ {msg}{R}", file=sys.stderr)
    return 1


def _board_proj_view(b, p, include_archived=False):
    """Vista serializable de UN proyecto (reusa el filtro de board)."""
    items = []
    for it in (p.get("items") or []):
        ci = b._clean_item(it, include_archived)
        if ci is not None:
            items.append(ci)
    return {"id": p.get("id"), "title": p.get("title", ""), "tag": p.get("tag"),
            "notes": p.get("notes", "") or "", "archived": bool(p.get("archived")),
            "items": items}


def _board_print_tree(items, depth=1):
    for it in items:
        mark = _STATUS_MARK.get(it.get("status"), "·")
        pad = "  " * depth
        date = it.get("date")
        extra = f"  {DIM}⌚{date}{R}" if date else ""
        note = f"  {DIM}— {it['notes'].splitlines()[0][:50]}{R}" if it.get("notes") else ""
        print(f"{pad}{C}{mark}{R} {it.get('title','')}  "
              f"{DIM}[{it.get('status')}]{R} {GREY}{it.get('id')}{R}{extra}{note}")
        kids = it.get("children") or []
        if kids:
            _board_print_tree(kids, depth + 1)


def _board_list(b, rest):
    pos, opts, err = _board_flags(rest, valued=("--project",), bools=("--json",))
    if err:
        return _board_err(err)
    raw = b.load_board()
    if opts.get("project"):
        p, perr = b.resolve_project(raw, opts["project"])
        if perr:
            return _board_err(perr)
        view = {"projects": [_board_proj_view(b, p)], "inbox": []}
    else:
        full = b.api_board({})
        view = {"projects": full["projects"], "inbox": full["inbox"]}
    if opts.get("json"):
        print(json.dumps(view, ensure_ascii=False, indent=2))
        return 0
    projs = view["projects"]
    if not projs and not view["inbox"]:
        print(f"{DIM}(tablero vacío — usa `workspace board capture \"…\"` o "
              f"`add-project`){R}")
        return 0
    for p in projs:
        tag = f"  {DIM}#{p['tag']}{R}" if p.get("tag") else ""
        print(f"{BO}{B}▸ {p.get('title','')}{R}  {GREY}{p.get('id')}{R}{tag}")
        _board_print_tree(p.get("items") or [])
    if view["inbox"]:
        print(f"\n{BO}{B}▸ Inbox{R}")
        for c in view["inbox"]:
            print(f"  {C}•{R} {c.get('text','')}  {GREY}{c.get('id')}{R}")
    return 0


def _board_capture(b, rest):
    text = " ".join(rest).strip()
    if not text:
        return _board_err("falta el texto: workspace board capture \"<idea>\"")
    res = b.api_capture({"text": text})
    if not res.get("ok"):
        return _board_err(res.get("error", "no se pudo capturar"))
    print(f"{C}✓ idea capturada:{R} {res['id']}")
    return 0


def _board_add_project(b, rest):
    pos, opts, err = _board_flags(rest, valued=("--tag",))
    if err:
        return _board_err(err)
    title = " ".join(pos).strip()
    if not title:
        return _board_err("falta el título: workspace board add-project \"<título>\"")
    payload = {"title": title}
    if opts.get("tag"):
        payload["tag"] = opts["tag"]
    res = b.api_add_project(payload)
    if not res.get("ok"):
        return _board_err(res.get("error", "no se pudo crear el proyecto"))
    print(f"{C}✓ proyecto creado:{R} {res['id']}")
    return 0


def _board_add_item(b, rest):
    pos, opts, err = _board_flags(
        rest, valued=("--project", "--title", "--status", "--note", "--parent"))
    if err:
        return _board_err(err)
    if not opts.get("project"):
        return _board_err("falta --project <id|nombre>")
    title = opts.get("title") or " ".join(pos).strip()
    if not title:
        return _board_err("falta --title \"<tema>\"")
    raw = b.load_board()
    p, perr = b.resolve_project(raw, opts["project"])
    if perr:
        return _board_err(perr)
    status = opts.get("status", "idea")
    if status not in _BOARD_STATUSES:
        return _board_err("estado inválido: %r (usa %s)"
                          % (status, " | ".join(_BOARD_STATUSES)))
    payload = {"project_id": p["id"], "title": title, "status": status}
    if opts.get("parent"):
        payload["parent_item_id"] = opts["parent"]
    res = b.api_add_item(payload)
    if not res.get("ok"):
        return _board_err(res.get("error", "no se pudo crear el tema"))
    if opts.get("note"):
        b.api_update_item({"project_id": p["id"], "item_id": res["id"],
                           "notes": opts["note"]})
    print(f"{C}✓ tema creado:{R} {res['id']}")
    return 0


def _board_set_status(b, rest):
    if len(rest) < 2:
        return _board_err("uso: workspace board set-status <item-id> <estado>")
    iid, status = rest[0], rest[1]
    if status not in _BOARD_STATUSES:
        return _board_err("estado inválido: %r (usa %s)"
                          % (status, " | ".join(_BOARD_STATUSES)))
    raw = b.load_board()
    p, item = b.find_item_anywhere(raw, iid)
    if item is None:
        return _board_err("tema desconocido: «%s»" % iid)
    res = b.api_update_item({"project_id": p["id"], "item_id": iid, "status": status})
    if not res.get("ok"):
        return _board_err(res.get("error", "no se pudo actualizar"))
    print(f"{C}✓ {iid} → {status}{R}")
    return 0


def _board_note(b, rest):
    pos, opts, err = _board_flags(rest, bools=("--append",))
    if err:
        return _board_err(err)
    if len(pos) < 2:
        return _board_err("uso: workspace board note <item-id> \"<texto>\" [--append]")
    iid = pos[0]
    text = " ".join(pos[1:]).strip()
    raw = b.load_board()
    p, item = b.find_item_anywhere(raw, iid)
    if item is None:
        return _board_err("tema desconocido: «%s»" % iid)
    if opts.get("append") and (item.get("notes") or "").strip():
        text = item["notes"].rstrip() + "\n" + text
    res = b.api_update_item({"project_id": p["id"], "item_id": iid, "notes": text})
    if not res.get("ok"):
        return _board_err(res.get("error", "no se pudo actualizar la nota"))
    print(f"{C}✓ nota de {iid} actualizada{R}")
    return 0


def _board_show(b, rest):
    pos, opts, err = _board_flags(rest, bools=("--json",))
    if err:
        return _board_err(err)
    if not pos:
        return _board_err("uso: workspace board show <item-id> [--json]")
    iid = pos[0]
    raw = b.load_board()
    p, item = b.find_item_anywhere(raw, iid)
    if item is None:
        return _board_err("tema desconocido: «%s»" % iid)
    clean = b._clean_item(item, include_archived=True)
    clean["project"] = {"id": p.get("id"), "title": p.get("title", "")}
    if opts.get("json"):
        print(json.dumps(clean, ensure_ascii=False, indent=2))
        return 0
    print(f"{BO}{clean.get('title','')}{R}  {GREY}{clean.get('id')}{R}")
    print(f"  {DIM}proyecto:{R} {p.get('title','')}  {GREY}{p.get('id')}{R}")
    print(f"  {DIM}estado:{R}   {clean.get('status')}")
    if clean.get("date"):
        print(f"  {DIM}fecha:{R}    {clean['date']}")
    links = clean.get("links") or {}
    if links.get("branch"):
        print(f"  {DIM}rama:{R}     {links['branch']}")
    if links.get("files"):
        print(f"  {DIM}archivos:{R} {', '.join(links['files'])}")
    if clean.get("children"):
        print(f"  {DIM}subtemas:{R} {len(clean['children'])}")
    if clean.get("archived"):
        print(f"  {DIM}archivado:{R} sí")
    if clean.get("notes"):
        print(f"  {DIM}notas:{R}\n    " + clean["notes"].replace("\n", "\n    "))
    return 0


def _board_archive(b, rest):
    if not rest:
        return _board_err("uso: workspace board archive <item-id>")
    iid = rest[0]
    raw = b.load_board()
    p, item = b.find_item_anywhere(raw, iid)
    if item is None:
        return _board_err("tema desconocido: «%s»" % iid)
    res = b.api_archive_item({"project_id": p["id"], "item_id": iid})
    if not res.get("ok"):
        return _board_err(res.get("error", "no se pudo archivar"))
    print(f"{C}✓ {iid} archivado{R}")
    return 0


def _board_help():
    print(f"""{BO}{B}workspace board{R} — API de terminal del tablero de Proyectos (dev panel)

  {BO}list{R} [--project <id|nombre>] [--json]   árbol de proyectos y temas
  {BO}capture{R} "<idea>"                          anota una idea suelta al inbox
  {BO}add-project{R} "<título>" [--tag <x>]        crea un proyecto (imprime id)
  {BO}add-item{R} --project <id|nombre> --title "<t>" [--status idea|pending|in-progress|done]
            [--note "<n>"] [--parent <item-id>]    crea un tema/subtema (imprime id)
  {BO}set-status{R} <item-id> <idea|pending|in-progress|done>
  {BO}note{R} <item-id> "<texto>" [--append]       setea (o agrega con --append) la nota
  {BO}show{R} <item-id> [--json]                    detalle de un tema
  {BO}archive{R} <item-id>                          archiva un tema (no lo borra)

  {DIM}--json en list/show = salida estable para parsear sin gastar tokens.
  Opera DIRECTO sobre board.json (no levanta server). exit 0 = ok, !=0 = error.{R}""")


def cmd_board(args):
    """`workspace board` — contrato de terminal del tablero «Proyectos» del dev
    panel. Agentes-first: lectura/edición token-eficiente del MISMO board.json
    (vía dash.dev.board), sin server ni HTTP. DEV-ONLY (dash/dev se excluye del
    distro a clientes): si no está, avisa y sale !=0 en vez de un traceback."""
    b = _board_mod()
    if b is None:
        print(f"{DIM}workspace board — comando solo-dev (no disponible en esta "
              f"instalación).{R}", file=sys.stderr)
        return 2
    if not args or args[0] in ("-h", "--help", "help"):
        _board_help()
        return 0 if args else 2
    sub, rest = args[0], args[1:]
    handlers = {
        "list": _board_list, "ls": _board_list,
        "capture": _board_capture,
        "add-project": _board_add_project,
        "add-item": _board_add_item,
        "set-status": _board_set_status, "status": _board_set_status,
        "note": _board_note,
        "show": _board_show,
        "archive": _board_archive,
    }
    h = handlers.get(sub)
    if h is None:
        print(f"{ERR}✗ subcomando desconocido: {sub}{R}", file=sys.stderr)
        _board_help()
        return 2
    try:
        return h(b, rest)
    except Exception as e:
        print(f"{ERR}✗ workspace board {sub}: {type(e).__name__}: {e}{R}",
              file=sys.stderr)
        return 1


def cmd_centro(args):
    """`workspace centro` — terminal del BACKEND del Centro de Control (misiones
    con 3 fases + estado agregado de agentes + delegación por el bus). La
    lógica vive en dash/centro/ (cli.py parsea e imprime); aquí solo se
    despacha. Falla-suave: sin dash/centro (instalación rota) avisa y sale !=0."""
    try:
        from dash.centro import cli as _centro_cli
    except Exception as e:
        print(f"{DIM}workspace centro — backend no disponible "
              f"({type(e).__name__}: {e}).{R}", file=sys.stderr)
        return 2
    return _centro_cli.main(args)


def cmd_parity_check(args):
    """`workspace parity-check` — corre los items `[auto]` de la Fase 3 (PARIDAD)
    del protocolo phase-gates y escupe un REPORTE FECHADO (SHA + plataforma +
    cada item ✓/✗/⚠ + resumen). El artefacto verificable de la compuerta de
    paridad (se pega al inbox / al commit de promoción). Lo observable (C) y los
    items que no se pueden evaluar quedan ⚠ (manual). Falla-suave: nunca crashea.

      --with-suite   además corre la suite (B). Lenta; por default B = ⚠.

    Exit: 0 si no hay ningún ✗ (fail); 1 si hay al menos un ✗."""
    import datetime
    from dash.dev import parity_check as pc

    with_suite = "--with-suite" in args
    ctx = pc.context()
    results = pc.evaluate(with_suite=with_suite)
    s = pc.summary(results)

    sym = {"ok": f"{C}✓{R}", "fail": f"{ERR}✗{R}", "warn": f"{B2}⚠{R}"}
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    print(f"\n  {BO}{B}WORKSPACE · parity-check{R}  {DIM}— Fase 3 · PARIDAD (items [auto]){R}")
    print(f"  {GREY}{now} · {ctx['platform']} (os.name={ctx['os_name']}){R}")
    sha = ctx.get("main_sha") or ctx.get("head_sha") or "?"
    print(f"  {GREY}main {sha or '?'} · rama {ctx.get('branch') or '(detached)'} · {ctx['repo']}{R}\n")

    for r in results:
        mark = sym.get(r["estado"], "?")
        print(f"  {mark}  {BO}{r['item']:<3}{R} {r['detalle']}")

    tail = (f"\n  {BO}Resumen{R}: {C}{s['ok']} ok{R} · "
            f"{ERR}{s['fail']} fail{R} · {B2}{s['warn']} warn{R} "
            f"({s['total']} items)")
    if not with_suite:
        tail += f"\n  {DIM}B no corrida — usa `workspace parity-check --with-suite` para incluir la suite.{R}"
    print(tail)
    print(f"  {DIM}⚠ = verificación manual / observable (C·E1·E2). La compuerta cierra "
          f"con AMBAS máquinas sin ✗.{R}\n")
    return 1 if s["fail"] else 0


def cmd_panel(args):
    """`workspace panel [--agent <name>]` — el PANEL del pane derecho del split.
    Superficie extensible (panel.VIEWS): Pipeline / Bus / Config / Delegar +
    header de identidad. Lo lanza mux.right_pane_cmd() cuando ui.split_pane=
    panel; también corre suelto para probarlo. Falla-suave: panel.py aislado."""
    import panel
    return panel.run(argv=["panel"] + list(args))


def cmd_agentes(args):
    """`workspace agentes [descubrir|reubicar|estado]` (Z03/U03).
      descubrir [--root <ruta>] [--json]  candidatos + sugerencias de reparación,
                                          SIN registrar nada (agentsreg discover)
      descubrir --register                registra explícitamente los NUEVOS
      reubicar <agente> <ruta> [--force]  repara la ruta del cerebro (override
                                          por máquina; no toca el cerebro)
      estado [--json]                     estado compartido (agent_state)
      (sin subcomando)                    pantalla Agentes (TTY) o estado (sin TTY)"""
    args = list(args or [])
    sub = args[0].lower() if args else ""
    import agentsreg
    if sub in ("descubrir", "discover", "buscar"):
        return agentsreg.main(["discover"] + args[1:])
    if sub in ("reubicar", "relocate", "reparar"):
        if len(args) < 3:
            print(_t("cli.agentes.relocate_usage", "uso: workspace agentes "
                     "reubicar <agente> <ruta> [--force]"))
            return 2
        return agentsreg.main(["relocate"] + args[1:])
    import agent_state
    if sub in ("estado", "status", "list", "ls") or not (
            sys.stdin.isatty() and sys.stdout.isatty()):
        return agent_state.main([a for a in args[1:] if a == "--json"]
                                if sub else [])
    import agents_tui
    return agents_tui.main(args)


def cmd_split(args):
    """`workspace split [agente]` — terminal PARTIDA (opt-in): una ventana con
    el chat del agente a la izquierda y la pipeline en vivo (`wf board`) a
    la derecha. ADITIVO: el arranque default (`workspace` hub / `<agente>`
    handoff) no cambia en nada. El backend (tmux | herdr) lo elige
    multiplexer.pick_backend (setting ui.split_backend, default auto). Sin
    multiplexer, sin TTY, anidado o en Windows → fallback grácil al arranque
    normal, con aviso. La lógica tmux vive en mux.py; la herdr y la
    selección, en multiplexer.py."""
    import multiplexer
    # `workspace split reap` — limpia sesiones split detached + procesos huérfanos
    # (mismo reaper que corre solo al armar un split). Útil como botón manual.
    if args and args[0] in ("reap", "limpiar", "--reap"):
        plan = any(a in ("--plan", "--dry-run") for a in args[1:])
        reaped, killed = multiplexer.reap_orphans(plan=plan)
        if plan:
            print(_t("cli.split.reap_plan", "WORKSPACE split reap: {n} sesión(es) "
                     "reapear · {k} grupo(s) huérfano(s) por matar",
                     n=len(reaped), k=killed))
        else:
            print(_t("cli.split.reap_done", "WORKSPACE split reap: {n} sesión(es) "
                     "reapeadas · {k} grupo(s) huérfano(s) matados",
                     n=len(reaped), k=killed))
        for s in reaped:
            print("  · " + s)
        return 0
    return multiplexer.open_split(args)


# ── Comandos de DEV/EQUIPO: NO son de producto (flujo de ramas, release/publish,
#    panel de developer, tablero, paridad). Solo viajan/aplican en una build de
#    DEV; en la build de CLIENTE se OCULTAN del --help y se gatean en el dispatch
#    (mensaje limpio + salida ≠0, nunca traceback). ÚNICA fuente de «qué es dev»
#    para el ruteo — alias incluidos. El gate build-dev-vs-cliente es _has_dev_panel(). ──
_DEV_CMDS = {
    "dev",
    "board", "tablero",
    "feature", "integrate", "promote", "release", "publish",
    "worktree", "wt",
    "parity-check", "parity", "paridad",
}


def _resolve_handler(word):
    """Handler del subcomando `word` (cualquier nombre/alias del catálogo) o
    None si no existe. Falla-suave: sin comandos.py → None (uso + exit 2)."""
    try:
        import comandos
        cid = comandos.resolve(word)
    except Exception:
        return None
    return _dispatch_table().get(cid) if cid else None


def _run_onboarding(_args):
    # Onboarding de primer uso, re-ejecutable a mano (onboarding_tui.py).
    try:
        import onboarding_tui
        rc = onboarding_tui.run(force=True)
    except Exception as e:
        print(_t("cli.unavailable", "{what} no disponible ({err})",
                 what="onboarding", err=f"{type(e).__name__}: {e}"))
        return 0
    # «✦ ir al hub» abre el hub DE VERDAD (pedido del dueño 2026-10-14: antes
    # te dejaba en la terminal y había que abrir otra ventana). En un proceso
    # nuevo: así arranca con el tema y los agentes recién elegidos. Si lo
    # lanzó el hub (Comandos), no: ese hub sigue abierto y retoma solo.
    if onboarding_tui.ULTIMA_SALIDA == "fin" and not os.environ.get("WORKSPACE_DESDE_COMANDOS"):
        _abre_hub()
    return rc


def _abre_hub():
    """El hub en un proceso nuevo, sin subcomando (exec en Mac/Linux; en
    Windows exec no reemplaza el proceso y rompe la consola → subprocess)."""
    argv = [sys.executable, os.path.abspath(__file__)]
    if os.name == "nt":
        sys.exit(subprocess.run(argv).returncode)
    os.execv(sys.executable, argv)


def _run_dev(args):
    # `dev setup` = onboarding de DESARROLLO (U11); `dev` a secas = panel.
    if args[:1] == ["setup"]:
        import dev_setup
        return dev_setup.main(args[1:])
    return cmd_dev(args)


def _run_module(modname, fn="main", pass_args=True):
    """Handler perezoso: importa `modname` solo al correr el comando."""
    def _h(args):
        mod = __import__(modname)
        return getattr(mod, fn)(args) if pass_args else getattr(mod, fn)()
    return _h


def _dispatch_table():
    """{id del catálogo (comandos.py): handler(args) → exit code}. ÚNICA tabla
    de ruteo de front.main: los NOMBRES (ES/EN/alias, incluidos los viejos)
    viven en el catálogo; aquí solo qué corre cada id. Se arma en cada
    llamada (lookup tardío: los tests parchean front.cmd_*). El lint
    (comandos.check + tests/test_comandos_catalog.py) exige catálogo ⇔ tabla."""
    return {
        "help": lambda a: (print(_usage()) or 0),
        "comandos": lambda a: cmd_comandos(a),
        "update": lambda a: cmd_update(a),
        "version": lambda a: cmd_version(a),
        # Ajustes registrados que viajan con cada actualización (migrate.py).
        "migrate": _run_module("migrate"),
        "doctor": lambda a: cmd_doctor(a),
        # `repair`/`fix`: subset rápido del doctor — re-renderiza SOLO los
        # hooks de cada cerebro (dispatch.maybe_autoupdate spawnea justo esto).
        "repair": lambda a: cmd_repair(a),
        "configurar-desarrollo": _run_module("dev_setup"),     # U11
        # Migración recuperable del harness viejo: --plan por default;
        # --apply / --retire / --rollback explícitos (migrate_legacy.py).
        "migrar-legado": _run_module("migrate_legacy"),
        "uninstall": lambda a: cmd_uninstall(a),
        "agentes": lambda a: cmd_agentes(a),
        # Niveles de personalidad de los agentes (tono.*) — ver personalidad.py.
        "tono": lambda a: cmd_tono(a),
        "onboarding": _run_onboarding,
        # Tu AGENDA (la muestra el Calendario). Local a esta máquina
        # (personal.py).
        "agenda": lambda a: cmd_personal("agenda", a),
        "calendario": lambda a: cmd_calendario(a),
        # App «Proyectos» (pantalla completa, puerto propio) — la abre el hub o esto.
        "proyectos": lambda a: cmd_proyectos(a),
        # Enviar correo por SMTP (Gmail App Password). Acción HACIA AFUERA: el
        # default seguro es --dry-run; las credenciales viven per-máquina.
        "mail": lambda a: cmd_mail(a),
        # Workflows declarativos (workflows/MAPA.md): specs congelados + runner.
        "wf": lambda a: cmd_wf(a),
        # Terminal PARTIDA (opt-in): solo se entra escribiendo `workspace split`.
        "split": lambda a: cmd_split(a),
        "eval": lambda a: cmd_eval(a),
        # ── ocultos (rutean, no se anuncian) ──
        # Backend del Centro de Control (dash/centro/).
        "centro": lambda a: cmd_centro(a),
        # Dictado por voz global (local, whisper.cpp).
        "voz": lambda a: cmd_voice(a),
        # Delegación autónoma segura (bus automático v1, opt-in).
        "bus": lambda a: cmd_bus(a),
        "memoria": _run_module("session_continuity"),
        # Pane derecho del split (panel.py; lo corre mux.right_pane_cmd()).
        "panel": lambda a: cmd_panel(a),
        # ── DEV/EQUIPO (el gate _DEV_CMDS corta antes en la build de cliente) ──
        "parity-check": lambda a: cmd_parity_check(a),
        "dev": _run_dev,
        "board": lambda a: cmd_board(a),
        # Flujo de ramas (feature → main → stable): imprime cada git que corre.
        "feature": lambda a: cmd_feature(a),
        "integrate": lambda a: cmd_integrate(a),
        "promote": lambda a: cmd_promote(a),
        "release": lambda a: cmd_release(a),
        "publish": lambda a: cmd_publish(a),
        # Worktrees con DUEÑO (el dashboard de DEV los marca "en uso").
        "worktree": lambda a: cmd_worktree(a),
    }


def _comandos_dev_mode():
    try:
        import dev_tui
        return dev_tui.is_dev()
    except Exception:
        return False


def cmd_comandos(args):
    """`workspace comandos` — el catálogo único, para gente y para agentes:
      (sin args)      pantalla Comandos (con consola) · uso en texto (sin ella)
      --json          catálogo estable para agentes de IA (ambos idiomas)
      --markdown      capítulo del manual, derivado (--lang es|en opcional)
      --check         lint: catálogo ⇔ ruteo, resúmenes ES/EN, colisiones
      --all           (con --json/--markdown) incluye ocultos y desarrollo"""
    import comandos
    lang = None
    if "--lang" in args:
        i = args.index("--lang")
        lang = args[i + 1] if i + 1 < len(args) else None
    dev = _has_dev_panel() and ("--all" in args or _comandos_dev_mode())
    if "--check" in args:
        probs = comandos.check(_dispatch_table().keys(), _DEV_CMDS)
        for p in probs:
            print("✗ " + p)
        if not probs:
            print(_t("cli.comandos.check_ok", "✓ catálogo de comandos sano "
                     "({n} comandos)", n=len(comandos.all_commands())))
        return 1 if probs else 0
    if "--json" in args:
        print(json.dumps(comandos.as_json(lang, dev=dev, hidden="--all" in args),
                         ensure_ascii=False, indent=2))
        return 0
    if "--markdown" in args or "--md" in args:
        # El Markdown es el capítulo del MANUAL público: sin comandos del equipo
        # salvo que se pidan explícitamente con --all.
        sys.stdout.write(comandos.as_markdown(lang, dev=_has_dev_panel() and "--all" in args))
        return 0
    if args:
        sys.stderr.write(_t("cli.comandos.usage", "uso: workspace comandos "
                            "[--json | --markdown | --check]") + "\n")
        return 2
    if not _interactive_console():
        print(_usage())
        return 0
    try:
        import comandos_tui
        rc = comandos_tui.run(standalone=True)
        return rc if isinstance(rc, int) else 0
    except Exception as e:
        print(_t("cli.unavailable", "{what} no disponible ({err})",
                 what="comandos", err=f"{type(e).__name__}: {e}"))
        print(_usage())
        return 0


def _usage(lang=None):
    """Uso CLI de `workspace` (sin abrir la TUI), DERIVADO del catálogo único
    (comandos.py): un renglón por comando, agrupado, en el idioma de la UI.
    Los comandos de DEV/EQUIPO (flujo de ramas, release, dev panel, paridad)
    solo se listan en una build de DEV (_has_dev_panel); el cliente ve solo
    producto. Nadie lista comandos a mano aquí: agregar uno = su ficha en
    comandos.py + su handler en _dispatch_table (el lint de tests lo exige)."""
    import comandos
    return comandos.usage_text(lang, dev=_has_dev_panel())


def _interactive_console():
    """¿stdin Y stdout son una consola interactiva REAL? (_console.interactive:
    en Windows NUL engaña a isatty() — se exige GetConsoleMode). Es la puerta
    del hub/picker: sin consola real NO se dibuja ni se espera teclado (W-F04).
    Falla-suave: módulo ausente → isatty de ambos (comportamiento anterior)."""
    try:
        import _console
        return _console.interactive()
    except Exception:
        try:
            return sys.stdin.isatty() and sys.stdout.isatty()
        except Exception:
            return False


def _headless_exit():
    """Contrato NO interactivo del hub (`workspace` sin subcomando con stdin o
    stdout redirigidos — pipe, archivo, NUL, CI): salida DETERMINISTA, sin
    picker msvcrt bloqueante ni animación. Devuelve el exit code:
      · vino del GREETER (perfil de shell cargado por un script/automation)
        → 0 en silencio: el shell sigue y no ensucia la salida del script;
      · invocación directa → aviso + uso en stderr y 2 (como un comando
        mal usado: el hub necesita terminal)."""
    if os.environ.get("WORKSPACE_GREETER"):
        return 0
    sys.stderr.write(
        _t("cli.headless", "WORKSPACE: el menú necesita una terminal "
           "interactiva (stdin/stdout redirigidos o sin consola).") + "\n"
        + "  " + _t("cli.headless_hint", "Vista estática: workspace --banner · "
                    "comandos: workspace --help") + "\n\n"
        + _usage())
    sys.stderr.flush()
    return 2


def _tty_out():
    """Stream del fallback estático del menú: /dev/tty si es ABRIBLE — existir
    no basta: en cron/headless `open()` truena con OSError (Errno 6, device not
    configured) aunque el nodo exista. Falla-suave → stderr. En Windows,
    stderr: "/dev/tty" sería el archivo C:/dev/tty."""
    if os.name == "nt":
        return sys.stderr
    try:
        return open("/dev/tty", "w")
    except OSError:
        return sys.stderr


def _greeter_preview_skip():
    """True si este arranque vino del GREETER (~/.zshrc) y hay un token fresco
    de preview del dev-panel (dash/dev/_preview.mark_greeter_skip): la ventana
    la abrió «ver esta rama»/«terminal» sobre un worktree y el menú de main NO
    debe taparla. Consume el token (un solo uso) e informa en una línea qué
    sigue. Falla-suave: cualquier error → False (greeter normal)."""
    if not os.environ.get("WORKSPACE_GREETER"):
        return False
    try:
        from dash.dev import _preview as _pv
        tok = _pv.consume_greeter_skip()
    except Exception:
        return False
    if not tok:
        return False
    what = tok.get("branch") or tok.get("path") or "worktree"
    print("· preview del dev-panel (%s): sigo de largo al worktree — sin menú"
          % what)
    return True


def main():
    # Bóveda de secretos per-máquina → env (Regla de Oro): las API keys viven
    # en ~/.claude/workspace/secrets.local (gitignoreado, 0600), NUNCA en el
    # repo/settings. Cargarlas aquí, al arrancar, hace que connectors._resolve_key
    # y los CLIs lanzados como subproceso las vean vía os.environ. El env real
    # del sistema gana (setdefault). Falla-suave: sin bóveda, no pasa nada.
    try:
        import secret_store
        secret_store.load_into_env()
    except Exception:
        pass
    # ── Build de CLIENTE: gate de la superficie DEV/EQUIPO ──
    # Los comandos de _DEV_CMDS (flujo de ramas, release/publish, dev panel,
    # tablero, paridad) dependen de archivos que NO viajan a la distro (p.ej.
    # cmd_dev busca dashboard-dev.html) → en una build sin dev panel tronarían.
    # Si un cliente los invoca: mensaje limpio + salida ≠0, NUNCA un traceback.
    # En build de DEV (_has_dev_panel) pasan tal cual, sin cambio de conducta.
    if (len(sys.argv) > 1 and sys.argv[1] in _DEV_CMDS and not _has_dev_panel()):
        sys.stderr.write(
            _t("cli.dev_only", "WORKSPACE: '{cmd}' es un comando de desarrollo, "
               "no disponible en esta instalación.", cmd=sys.argv[1])
            + "\n\n" + _usage())
        sys.exit(2)
    # ── Subcomandos: nombre/alias → id (catálogo comandos.py) → handler
    #    (_dispatch_table). Una sola puerta: aquí no se compara sys.argv[1] a
    #    mano (el lint de tests lo vigila), así ayuda, pantalla y ruteo no
    #    pueden divergir. `--banner` no es subcomando: sigue al hub.
    if len(sys.argv) > 1 and sys.argv[1] != "--banner":
        handler = _resolve_handler(sys.argv[1])
        # CLI hygiene: un subcomando DESCONOCIDO imprime uso y sale con 2 —
        # NUNCA cae a la TUI interactiva (un typo o un script headless no
        # deben terminar dentro del recinto, y sin tty eso tronaba).
        if handler is None:
            sys.stderr.write(_t("cli.unknown_cmd", "WORKSPACE: comando "
                                "desconocido '{cmd}'", cmd=sys.argv[1])
                             + "\n\n" + _usage())
            sys.exit(2)
        sys.exit(handler(sys.argv[2:]))
    # ── Ventana de PREVIEW del dev-panel: hazte a un lado ──
    # El greeter de ~/.zshrc corre ESTE hub (el de main, ruta absoluta del
    # launcher) en cada shell interactiva de login — también en la ventana que
    # «ver esta rama» / «terminal» del dev-panel acaba de abrir sobre un
    # worktree, tapando el worktree con el hub de main (el bug «abre en main»).
    # dash/dev/_preview escribe un token de un solo uso antes de abrir esa
    # ventana; si está fresco, este hub NO arranca y deja seguir la sesión:
    # prompt en el worktree («terminal») o el hub DE ESA RAMA vía el .command
    # («hub»). Solo aplica cuando nos invocó el greeter (WORKSPACE_GREETER).
    if "--banner" not in sys.argv and _greeter_preview_skip():
        return
    # ── Contrato NO interactivo (W-F04/Z19): sin consola real en stdin Y stdout
    #    (pipe cerrado, archivo, NUL — que en Windows engaña a isatty) el hub NO
    #    arranca: ni onboarding, ni OSC de tema, ni altar, ni picker msvcrt que
    #    espera teclado para siempre. `--banner` sigue siendo la vista estática.
    #    Va ANTES de onboarding/theme para no escribir nada al stdout redirigido.
    if "--banner" not in sys.argv and not _interactive_console():
        sys.exit(_headless_exit())
    # ── ONBOARDING de primer uso (repo público): sin flag, sin agentes y con
    #    TTY → flujo guiado ANTES del hub (onboarding_tui.maybe_run decide con
    #    sus propias guardas — subcomando/--banner, env, flag, adopción); si
    #    corrió, re-exec para que el recinto arranque ya con el tema y los
    #    agentes recién elegidos (la paleta de este proceso se fijó al
    #    importar). Fail-soft total: cualquier problema → el hub normal.
    try:
        import onboarding_tui
        if onboarding_tui.maybe_run():
            os.execv(sys.executable,
                     [sys.executable, os.path.abspath(__file__)]
                     + sys.argv[1:])
    except Exception:
        pass
    _apply_pending_migrations()                   # ajustes de una actualización, a la vista
    # El harness arranca VACÍO de agentes: es un producto que se distribuye a clientes
    # y ellos conectan sus PROPIOS cerebros explícitamente ("Agregar agente → cargar
    # ruta"). NO auto-descubrimos cerebros del disco al bootear (eso metía un agente
    # sin que el usuario lo pidiera). El descubrimiento sigue disponible como acción
    # MANUAL (menú Agregar agente → Descubrir, o `agentsreg.py discover`).
    import theme
    theme.apply_current()                         # fondo/tinta del tema (tui.osc) o los de la terminal
    _set_term_title("WORKSPACE")                  # la pestaña dice WORKSPACE, no el proceso
    it = items()
    if "--banner" in sys.argv:
        # Vista ESTÁTICA del hub (el lanzador sin tty) — para pruebas y para
        # ver el hub sin abrirlo. Falla-suave: si la machinery truena, cae a
        # la lista plana del picker.
        try:
            print("\n".join(_menu_machinery(sys.stdout).block_lines()))
        except Exception:
            print("\n".join(_static_header()
                            + _picker_lines(it, _first_selectable(it))))
        print()
        return
    while True:
        name = animated_menu(it)                  # el lanzador (devuelve nombre/token)
        if name is None:                          # fallback: sin tty / WORKSPACE_NO_ANIM
            t = _tty_out()                        # /dev/tty ABRIBLE o stderr (headless no truena)
            # vista ESTÁTICA con el lenguaje del lanzador (wordmark compacto +
            # versión; la lista en su caja la pinta run_picker)
            t.write("\n".join(_static_header()) + "\n"); t.flush()
            name = it[run_picker(it)][0]
        sys.stdout.write("\033[2J\033[3J\033[H"); sys.stdout.flush()   # limpia menú + scrollback al salir
        # Acciones que REGRESAN al recinto tras ejecutarse (pantalla TUI propia).
        # Falla-suave: si el módulo no está o truena, un aviso y el menú sigue
        # vivo (jamás crashea el boot). El recinto se reconstruye al re-entrar
        # al loop → relee el registry (un agente recién agregado ya aparece).
        loopback = {"__devmap__": (_t("menu.comandos.label", "Comandos").lower(),
                                   "comandos_tui"),
                    "__add_agent__": (_t("menu.add_agent.label",
                                         "Agregar agente").lower(),
                                      "add_agent_tui"),
                    "__agentes__": (_t("menu.agents.label", "Agentes").lower(),
                                    "agents_tui"),
                    "__motores__": (_t("menu.engines.label", "Motores").lower(),
                                    "engines_tui"),
                    # Calendario, Tono y Actualizaciones también REGRESAN al
                    # hub (Esc/q): antes salían al shell (pedido del socio
                    # 2026-10-12: «Esc regresa al hub en todas las secciones»).
                    "__cal__": (_t("menu.cal.label", "Calendario").lower(),
                                lambda: cmd_calendario([])),
                    "__tono__": (_t("menu.tono.label", "Tono").lower(),
                                 lambda: cmd_tono([])),
                    "__doctor__": (_t("menu.updates.label",
                                      "Actualizaciones").lower(),
                                   _doctor_submenu)}
        if name not in loopback:
            break
        label, target = loopback[name]
        stamp = _code_stamp() if name == "__doctor__" else None
        theme.HOSTED = True                       # la sección deja el tema puesto al volver
        try:
            if callable(target):
                target()
            else:
                __import__(target).run()
        except Exception as e:
            print(f"{DIM}" + _t("cli.loopback_fail", "{what} no disponible "
                                 "({err}) — el menú sigue normal", what=label,
                                 err=f"{type(e).__name__}: {e}") + f"{R}")
        finally:
            theme.HOSTED = False
        # Si Actualizaciones instaló código nuevo, este proceso sigue con el
        # VIEJO en memoria: se reabre el hub en vez de volver a él.
        if stamp is not None and _code_stamp() != stamp:
            _restart_hub()
    if name == "__dev__":                         # abrir el panel de DEV (versiones/ramas) y al shell
        theme.reset(); cmd_dev([]); return
    if name == "__proyectos__":                   # abrir la app «Proyectos» y al shell
        theme.reset(); cmd_proyectos([]); return
    if name == "__shell__":                       # "Terminal normal" / q → salir al shell
        theme.reset(); return                     # restaura colores por defecto en el shell
    launch(name)                                  # launch() limpia y lanza el agente (aplica SU tema)


if __name__ == "__main__":
    main()
