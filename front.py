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
sys.dont_write_bytecode = True   # no generar __pycache__ (mantiene limpio el sync)
if os.name == "nt":
    os.system("")  # habilita ANSI en Windows 10+ (no-op en consolas viejas) — igual que doctor.py
import _utf8; _utf8.harden()  # B2 · UTF-8 en stdout/err (cp1252 reventaría con box-drawing)

ROOT = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable or "python3"
DISPATCH = os.path.join(ROOT, "dispatch.py")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "banner"))
import render  # noqa: E402
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


# Agentes de SISTEMA: motores internos del harness que NO son dioses del
# altar (pedido del socio 2026-10-02: «Workspace Doctor» no debe salir como
# agente). Filtrado SOLO-display en el hub: dispatch/launch/update los siguen
# viendo (lanzarlos directo y actualizar su cerebro funciona igual).
_SYSTEM_AGENTS = frozenset({"doctor"})


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
    porción del picker estático y keybinds deriva de aquí la sección «menú»
    de la pantalla «Atajos» — una sección nueva del hub aparece SOLA en los
    tres lugares (y gana tecla re-mapeable) sin tocar nada más."""
    out = []
    # «GitHub» (ex-«Ramas», 2026-10-04): la sección creció — conserva el mapa
    # local de ramas/worktrees (git_tui, tecla m) y suma la capa GitHub
    # multi-repo vía el CLI gh (github_tui, gated por `gh auth status`).
    # Ya NO es dev-only: es producto. El token __ramas__ se conserva
    # (keybinds y ruteo estables).
    out.append(("__ramas__", _t("menu.github.label", "GitHub"),
                _t("menu.github.tag",
                   "tus repos: ramas locales + PRs, issues y releases")))
    # «Dev» (sección del hub, 2026-10-04): transparencia del proceso de
    # desarrollo — referencia de comandos + mapa del detrás (pipeline, repos,
    # qué sube, versión, estado). SOLO el dueño/dev: gate por-archivos (igual
    # que «Ramas») + dev_tui.is_dev() (canal main / marker per-máquina).
    # Falla-suave ABSOLUTA: sin dev_tui, el menú queda exactamente como antes.
    try:
        import dev_tui as _dtui
        if _has_dev_panel() and _dtui.is_dev():
            out.append(("__devmap__", "Dev",
                        "el detrás de workspace — comandos + mapa"))
    except Exception:
        pass
    # «Actualizaciones» (ex-«Doctor», renombre user-facing 2026-10-02): mismo
    # token __doctor__ y mismos comandos (workspace doctor/update) por debajo.
    out += [("__cal__", _t("menu.cal.label", "Calendario"),
             _t("menu.cal.tag",
                "tu agenda del día, editable a pantalla completa")),
            ("__tono__", _t("menu.tono.label", "Tono"),
             _t("menu.tono.tag",
                "los diales de personalidad de tus agentes")),
            ("__keybinds__", _t("menu.keybinds.label", "Atajos"),
             _t("menu.keybinds.tag", "re-mapea las teclas rápidas del hub")),
            ("__doctor__", _t("menu.updates.label", "Actualizaciones"),
             _t("menu.updates.tag", "revisar · reparar · actualizar")),
            ("__agentes__", _t("menu.agents.label", "Agentes"),
             _t("menu.agents.tag", "configuración y cerebro de cada agente")),
            ("__add_agent__", _t("menu.add_agent.label", "Agregar agente"),
             _t("menu.add_agent.tag", "crear o cargar un agente")),
            # El control de IDIOMA ya NO vive en el MENÚ: es un CUADRO propio
            # del hub (layout `dia`), bajo PERSONALIZACIÓN — navegable+Enter,
            # como tema/fondo. Ver groups "idioma" + hublayout._dia_idioma_body.
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
        out.append((p, p.capitalize(), "próximamente", False))
    # Chat: extraído a la rama feat/chat (se retoma a fondo después). El código
    # (chat_tui.py/chat.py/chat_daemon.py) ya no vive en main — fuera del hub.
    # «Config» salió del MENÚ (pedido del socio 2026-10-02): la sección se va a
    # rehacer; mientras tanto no se lista ni se navega. El subsistema sigue
    # vivo (config_tui.py + ruteo __config__/loopback intactos) — re-exponerla
    # = re-agregar la entrada aquí y en opts de _menu_machinery.
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
    _solo_hub = ("__cal__", "__tono__", "__keybinds__")
    out += [(tok, lbl, tag, True) for tok, lbl, tag in menu_entries()
            if tok not in _solo_hub]
    return out


def build_info_rows():
    reg = registry()
    active = [a["name"] for a in reg.get("agents", [])]
    planned = reg.get("planned", [])
    ag = " · ".join(active) + (
        (" · " + '/'.join(planned) + " "
         + _t("hub.hero.soon_paren", "(pronto)")) if planned else "")
    # motor: binding EFECTIVO (harness-os) — antes iba fijo 'claude-code'.
    # Falla-suave: sin harnesses.py, el texto de siempre.
    motor_txt = _t("hub.hero.engine_default",
                   "claude-code · Anthropic (sin API key)")
    try:
        import harnesses as _h
        engs = sorted({_h.binding(a.get("name", ""),
                                  a.get("engine") or "claude-code")[0]
                       for a in reg.get("agents", [])})
        if engs == ["claude-code"]:
            pass                                   # el texto rico de siempre
        elif len(engs) == 1:
            motor_txt = engs[0]
        elif engs:
            motor_txt = " · ".join(engs) + _t("hub.hero.engine_per_agent",
                                              "  (por agente — tecla m)")
    except Exception:
        pass
    # cerebros: derivada del registry real (no literal) — un cliente NO debe ver
    # nombres internos del equipo. Vacío → genérico.
    cerebros = (" · ".join(f"{a.upper()}-BRAIN" for a in active) + " · sync"
                if active else _t("hub.hero.v.config_first",
                                  "configura tu primer agente"))
    user = os.environ.get("USER") or os.environ.get("USERNAME", "")   # USER no existe en Windows
    try:                                              # usuario real per-máquina (lo escribe install)
        sloc = open(os.path.join(os.path.expanduser("~"), ".claude", "workspace",
                                 "socio.local"), encoding="utf-8").read().strip()
    except Exception:
        sloc = ""
    socio = sloc or user or "—"
    socio = (socio[:1].upper() + socio[1:]) if socio != "—" else socio
    mach = "Mac" if sys.platform == "darwin" else ("Windows" if os.name == "nt" else "Linux")
    # «directo»: un cliente NO debe ver un nombre interno del equipo. Si ya hay
    # agentes cargados, el ejemplo usa el primero REAL; sin agentes, genérico.
    agente_ej = active[0] if active else _t("hub.hero.agent_generic", "tu-agente")
    return [
        ("##", _t("hub.hero.h.harness", "El harness")),
        (_t("hub.hero.k.agents", "agentes"), ag),
        (_t("hub.hero.k.engine", "motor"), motor_txt),
        (_t("hub.hero.k.brains", "cerebros"), cerebros),
        (_t("hub.hero.k.autoclose", "cierre auto"),
         _t("hub.hero.v.capture", "captura de sesión activa")),
        ("", ""),
        ("##", _t("hub.hero.h.setup", "Tu setup")),
        (_t("hub.hero.k.user", "usuario"), socio),
        (_t("hub.hero.k.machine", "máquina"), mach),
        (_t("hub.hero.k.base", "base"),
         _t("hub.hero.v.base", "instalador + workspace doctor ✓")),
        ("", ""),
        ("##", _t("hub.hero.h.howto", "Cómo entrar")),
        (_t("hub.hero.k.menu", "menú"),
         _t("hub.hero.v.menu", "elige un agente abajo ↓")),
        (_t("hub.hero.k.direct", "directo"),
         _t("hub.hero.v.direct", "escribe su nombre: {name}", name=agente_ej)),
        ("", ""), ("", ""), ("", ""),
    ]


def _row(disp, tag, selected, selectable, w):
    if not selectable:
        return f"      {GREY}{disp.ljust(w)}{R}{GREY}{tag}{R}"
    if selected:
        return f"    {C}{GPTR} {WH}{disp.ljust(w)}{R}{DIM}{tag}{R}"
    return f"      {DIM}{disp.ljust(w)}{R}{GREY}{tag}{R}"


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


# Defaults DUROS del mapa de salto (paridad si keybinds.py faltara): mismo
# contenido que keybinds.defaults(). La fuente de verdad en runtime es el
# REGISTRO per-máquina (keybinds.py — pantalla «Atajos» del MENÚ).
_JUMP_FALLBACK = {"menu.__ramas__": "r", "menu.__devmap__": "v",
                  "menu.__cal__": "c", "menu.__tono__": "o",
                  "menu.__keybinds__": "k", "menu.__doctor__": "u",
                  "menu.__add_agent__": "g", "menu.__agentes__": "b",
                  "accion.motor": "m", "accion.info": "i"}


def _jump_map(agents, opts):
    """Teclas rápidas del hub — DATA-DRIVEN: salen del registro per-máquina
    (keybinds.effective(); overrides en ~/.claude/workspace/keybinds.json, la
    pantalla «Atajos» los edita). La semántica es UNA por familia y SIEMPRE
    se pinta la tecla junto a su opción (transparencia):
      · AGENTES (default 1-9 por posición) → APUNTA al agente sin lanzarlo
        (ahí aplican motor/info/Enter); la MISMA tecla otra vez — o Enter —
        lo lanza. Del 10º agente en adelante, sin tecla (flechas).
      · MENÚ (default r/c/o/k/u/g por token) → abre la opción directo.
        `__shell__` no entra al mapa: su tecla visible es `q`, que ya hace
        exactamente eso.
      · ACCIONES (default m=motor · i=info) → operan sobre el agente
        APUNTADO sin lanzarlo (quick()).
      · PERSONALIZACIÓN → sin tecla (ciclar un setting persistente con una
        tecla ciega es error fácil); flechas + Enter, y el CLICK sí llega.
    Devuelve (mapa, display, acciones):
      mapa     {'1': ('agent', 0), 'c': ('opt', 1), …}  → lo consume jump()
      display  {'agents': {i: '1'…}, 'opts': {j: 'c'…, j_shell: 'q'},
                'acciones': {'motor': 'm', 'info': 'i'}} → lo pintan los
               layouts junto a cada ítem (y los hints del pie).
      acciones {'m': 'motor', 'i': 'info'}              → lo consume quick()
    PURA respecto a la sesión (agents/opts fijos); falla-suave ABSOLUTA:
    sin keybinds.py o registro roto → los defaults de siempre."""
    try:
        import keybinds as _kb
        eff = _kb.effective()
    except Exception:
        eff = {("agente.%d" % (i + 1)): str(i + 1) for i in range(9)}
        eff.update(_JUMP_FALLBACK)
    mapa, da, do = {}, {}, {}
    for i in range(min(9, len(agents))):
        k = eff.get("agente.%d" % (i + 1), "")
        if k and k not in mapa:
            mapa[k] = ("agent", i)
            da[i] = k
    for j, (tok, _lbl) in enumerate(opts):
        if tok == "__shell__":
            do[j] = "q"                     # q ya ES «Terminal normal»
            continue
        k = eff.get("menu." + tok, "")
        if k and k not in mapa:
            mapa[k] = ("opt", j)
            do[j] = k
    acc = {}
    for aid, nombre in (("accion.motor", "motor"), ("accion.info", "info")):
        k = eff.get(aid, "")
        if k and k not in mapa and k not in acc:
            acc[k] = nombre
    return mapa, {"agents": da, "opts": do,
                  "acciones": {v: k for k, v in acc.items()}}, acc


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
    w = max(len(d) for _, d, _, _ in it) + 2
    idx = _first_selectable(it)

    def draw(first):
        if not first:
            out.write(f"\033[{n}A")
        for i, (nm, disp, tag, sel) in enumerate(it):
            out.write("\r\033[K" + _row(disp, tag, i == idx, sel, w) + "\r\n")
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
    w = max(len(d) for _, d, _, _ in it) + 2
    idx = _first_selectable(it)

    def draw(first):
        if not first:
            tout.write(f"\033[{n}A")
        for i, (nm, disp, tag, sel) in enumerate(it):
            tout.write("\r\033[K" + _row(disp, tag, i == idx, sel, w) + "\r\n")
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
        inp = open("/dev/tty", "r"); out = open("/dev/tty", "w")
    except Exception:
        inp, out = sys.stdin, sys.stderr
    out.write("\n")
    sel = [i for i, x in enumerate(it) if x[3]]
    for k, i in enumerate(sel, 1):
        out.write(f"    {C}{k}{R}  {WH}{it[i][1]}{R}   {DIM}{it[i][2]}{R}\n")
    out.write(f"\n  {DIM}Número y Enter: {R}"); out.flush()
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

    pidfile = os.path.join(os.path.expanduser("~"), ".claude", "workspace", "dashboard-dev.pid")

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

    logdir = os.path.join(os.path.expanduser("~"), ".claude", "workspace")
    try:
        os.makedirs(logdir, exist_ok=True)
        log = open(os.path.join(logdir, "dashboard-dev.log"), "a")
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

    pidfile = os.path.join(os.path.expanduser("~"), ".claude", "workspace", "proyectos.pid")

    if "stop" in args or "--stop" in args:
        _dev_kill(port, pidfile)                  # el killer por puerto+pidfile es genérico
        print(f"{C}WORKSPACE proyectos detenido.{R}")
        return 0

    if running():                                 # relanzar = servir el código de HOY
        print(f"{DIM}  reiniciando la app de proyectos con el código actual…{R}")
        _dev_kill(port, pidfile)
        for _ in range(20):
            if not running():
                break
            time.sleep(0.15)

    logdir = os.path.join(os.path.expanduser("~"), ".claude", "workspace")
    try:
        os.makedirs(logdir, exist_ok=True)
        log = open(os.path.join(logdir, "proyectos.log"), "a")
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
    print(f"{C}WORKSPACE proyectos{R} (mapa de proyectos) → {url}  {DIM}(app aparte del dashboard){R}")
    print(f"{DIM}  reabrir/refrescar: workspace proyectos   ·   detener: workspace proyectos stop{R}")
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
        return -1, "", "timeout (¿sin conexión?)"


def _update_repo(label, path, transport="git"):
    """Pull --ff-only de UN repo en su rama actual. Imprime una línea de estado.
    Devuelve 'updated' | 'uptodate' | 'managed' | 'skipped' (⚠, nunca aborta el resto).
    `transport='obsidian-sync'` (cerebros gestionados por Obsidian Sync) = canal
    SANO: ✓ verde y 'managed', no cuenta como repo saltado."""
    pad = f"  {label:<22}"
    if transport == "obsidian-sync":
        print(f"{pad}{C}✓{R} {DIM}gestionado por Obsidian Sync (sin git){R}")
        return "managed"
    if not os.path.isdir(os.path.join(path, ".git")):
        print(f"{pad}{B}⚠{R} {DIM}no es repo git (instalación por sync) — sin auto-update{R}")
        return "skipped"
    rc, remotes, _ = _git(path, "remote", timeout=10)
    if rc != 0 or not remotes:
        print(f"{pad}{B}⚠{R} {DIM}sin remote configurado — nada que jalar{R}")
        return "skipped"
    _, dirty, _ = _git(path, "status", "--porcelain", timeout=15)
    if dirty:
        print(f"{pad}{B}⚠{R} cambios locales sin commitear {DIM}— no jalo encima; "
              f"commitea/guarda y reintenta{R}")
        return "skipped"
    _, branch, _ = _git(path, "rev-parse", "--abbrev-ref", "HEAD", timeout=10)
    _, old, _ = _git(path, "rev-parse", "--short", "HEAD", timeout=10)
    rc, out, err = _git(path, "pull", "--ff-only", timeout=90)   # rama ACTUAL (stable/main…)
    if rc != 0:
        low = (out + " " + err).lower()
        if "no tracking information" in low or "no remote ref" in low or "couldn't find remote ref" in low:
            print(f"{pad}{B}⚠{R} {DIM}la rama '{branch}' no rastrea a origin — "
                  f'git -C "{path}" branch --set-upstream-to=origin/{branch}{R}')
        elif "could not resolve" in low or "unable to access" in low or "timeout" in low or "connection" in low:
            print(f"{pad}{B}⚠{R} {DIM}sin conexión con origin (¿offline?) — se queda como está{R}")
        elif "not possible to fast-forward" in low or "divergent" in low:
            print(f"{pad}{B}⚠{R} historia divergente {DIM}— resuélvelo a mano: "
                  f'git -C "{path}" pull --ff-only{R}')
        else:
            print(f"{pad}{B}⚠{R} {DIM}{(err or out).splitlines()[-1] if (err or out) else 'pull falló'}{R}")
        return "skipped"
    _, new, _ = _git(path, "rev-parse", "--short", "HEAD", timeout=10)
    if new and new != old:
        print(f"{pad}{C}✓{R} actualizado a {C}{new}{R} {DIM}(rama {branch}){R}")
        return "updated"
    print(f"{pad}{C}✓{R} {DIM}ya al día (rama {branch}){R}")
    return "uptodate"


def cmd_update(args=None):
    """`workspace update` — deja la máquina del socio al día y verificada, en uno:
      1. git pull --ff-only de WORKSPACE (en su rama actual: stable para el equipo, main para quien desarrolla).
      2. git pull --ff-only de cada cerebro registrado (resueltos con dispatch.resolve_brain).
      3. workspace doctor (REPARA) al final → además de verificar, arregla hooks/launchers/tema.
    Así un solo `workspace update` deja la máquina al día Y auto-curada (flujo de self-heal
    remoto: el equipo pushea un fix → el usuario corre update → su máquina se repara sola).
    Seguro e idempotente: repo sucio / offline / sin remote → ⚠ y sigue con los demás.
    `workspace update --check` solo diagnostica (no repara); `workspace update --no-check` salta el doctor."""
    args = list(args or [])
    print(f"{C}WORKSPACE update{R} {DIM}— harness + cerebros, en su rama actual…{R}\n")

    # repos: WORKSPACE + cada cerebro registrado (misma resolución que el dispatcher)
    repos = [("WORKSPACE", ROOT, "git")]
    try:
        import dispatch
        for entry in dispatch.load_registry().get("agents", []):
            try:
                cfg = dispatch.load_agent_cfg(entry)
            except Exception:
                cfg = {}
            brain = dispatch.resolve_brain(entry["name"], cfg)
            if brain and os.path.isdir(brain):
                repos.append((f"cerebro {entry['name']}", brain,
                              dispatch.brain_transport(entry["name"], brain)))
            else:
                repos.append((f"cerebro {entry['name']}", None, "git"))
    except Exception as e:
        print(f"  {B}⚠{R} {DIM}no pude leer el registry de agentes ({e}) — solo actualizo WORKSPACE{R}")

    seen, skipped = set(), 0
    try:
        for label, path, transport in repos:
            if path is None:
                print(f"  {label:<22}{B}⚠{R} {DIM}cerebro no resuelto — corre `workspace doctor`{R}")
                skipped += 1
                continue
            key = os.path.normcase(os.path.realpath(path))
            if key in seen:
                continue
            seen.add(key)
            if _update_repo(label, path, transport) == "skipped":
                skipped += 1
    except FileNotFoundError:
        print(f"\n{B}git no está instalado en esta máquina.{R} Instálalo y vuelve a correr `workspace update`.")
        return 1

    if skipped:
        print(f"\n{DIM}  {skipped} repo(s) quedaron sin actualizar (⚠ arriba) — el resto sí jaló.{R}")

    if "--no-check" in args:
        print(f"\n{C}✓ Update terminado.{R} {DIM}(doctor omitido por --no-check){R}")
        return 0

    check_only = "--check" in args
    if check_only:
        print(f"\n{DIM}  Verificando la instalación (workspace doctor --check)…{R}")
    else:
        print(f"\n{DIM}  Verificando y reparando la instalación (workspace doctor)…{R}")
    try:
        # `--from-update`: el doctor NO vuelve a ofrecer update (ya venimos de update;
        # evita recursión/loop).
        rc = cmd_doctor((["--check"] if check_only else []) + ["--from-update"])
    except Exception as e:
        print(f"  {B}⚠{R} {DIM}el doctor falló ({type(e).__name__}: {e}) — "
              f"corre `workspace doctor` a mano{R}")
        return 1
    return rc or 0


def _menu_header():
    return (f"  {C}{_t('hub.menu_header.title', '◆ ¿A dónde entras?')}{R}"
            f"   {DIM}{_t('hub.menu_header.hint', '↑↓ · Enter · q = terminal normal')}{R}")


AGENT_COLORS = {"zenith": "blue", "atlas": "red", "argus": "green",
                "turing": "cyan"}


# Medición de ancho COMPARTIDA (_width.py — la MISMA del hub/config): ANSI
# completo (CSI/OSC/ESC de 2 bytes, no solo SGR), combinantes/zero-width = 0,
# CJK/Hangul = 2. Antes front tenía su propio regex solo-SGR y su propia tabla
# → un glifo de tema medía distinto aquí que en config_tui y descuadraba.
from _width import strip_ansi as _strip_ansi, sane as _wsane, eaw as _eaw  # noqa: E402
def _vis(s):
    # Ancho VISUAL (no len) — ver _width.py. Crítico para el padding/centrado
    # del recinto: un nombre coreano (누리) mal medido sobre-rellena la línea,
    # la envuelve (wrap) y descuadra el redibujo.
    return sum(_eaw(c) for c in _wsane(_strip_ansi(s)))
def _ctr(s):
    pad = max(0, ((render.W + 4) - _vis(s)) // 2)
    return " " * pad + s
def _rgt(s, margin=1):
    """Alinea `s` a la DERECHA del bloque de contenido (content_w = render.W+4),
    con un pequeño margen. Para el indicador de versión abajo-derecha del hub.
    Respeta el ancho visual (ANSI/CJK). Si no cabe, no rellena (no rompe layout)."""
    pad = max(0, (render.W + 4) - _vis(s) - margin)
    return " " * pad + s
def _shimmer(text, ph, base, hi):
    """Barrido luminoso: una ventana brillante recorre el texto (animación de herramientas)."""
    n = len(text); pos = ph % (n + 6)
    return "".join((hi if abs(i - pos) <= 1 else base) + c for i, c in enumerate(text)) + R


# ── Estrellas lejanas: campo ESTÁTICO y determinista por (fila,col). No anima → no
#    parpadea ni rompe el TUI (se dibuja una vez en full_draw, el redraw no lo toca).
#    Apagar con WORKSPACE_NO_STARS=1 (el env SIEMPRE gana) o `settings set ui.stars off`. ──
if TH:
    _STAR_DIM, _STAR_MID, _STAR_HI = TH.STAR_DIM, TH.STAR_MID, TH.STAR_HI
else:
    _STAR_DIM = [fg(236), fg(237), fg(239), fg(240)]  # tenues (la mayoría: "a lo lejos")
    _STAR_MID = [fg(243), fg(246)]                    # medias
    _STAR_HI = fg(251)                                # raras brillantes (acento)
# Glifos del cielo. En Windows Terminal varios dingbats brillantes (✦ U+2726, ✧ U+2727,
# rango 0x2600-0x27BF) se dibujan a DOBLE ancho mientras el cielo los cuenta como 1 celda →
# descuadra los márgenes y deja "glitches" de estrellitas. En Windows usamos solo glifos
# angostos garantizados (·, ⋆ U+22C6, *, +). Mac mantiene los dingbats (ahí miden 1).
if os.name == "nt":
    _GLYPH_D = ["·", "·", ".", "·", "·"]
    _GLYPH_H = ["*", "⋆", "+", "·"]
else:
    _GLYPH_D = ["·", "·", "˙", ".", "·"]
    _GLYPH_H = ["✦", "⋆", "✧", "*"]
# un tema puede traer SUS glifos de cielo (p. ej. oficina-8bit: píxeles ASCII);
# los overrides de los temas del repo son angostos-seguros en ambos OS.
if GL.get("star_d"):
    _GLYPH_D = list(GL["star_d"])
if GL.get("star_h"):
    _GLYPH_H = list(GL["star_h"])
def _ui_setting_on(name):
    """Setting bool ui.* del store unificado (settings.py, misma raíz).
    Falla-suave → True (el look de siempre). El env WORKSPACE_NO_* se chequea
    APARTE en cada sitio de consumo y SIEMPRE gana."""
    try:
        import settings as _settings
        return _settings.enabled("ui." + name, default=True)
    except Exception:
        return True


STARS = (not os.environ.get("WORKSPACE_NO_STARS")) and _ui_setting_on("stars")


def _hsh(a, b):
    x = ((a * 73856093) ^ (b * 19349663) ^ 0x9E3779B9) & 0xFFFFFFFF
    x ^= x >> 13; x = (x * 0x85EBCA6B) & 0xFFFFFFFF; x ^= x >> 16
    return x


def _starline(width, row, mod=29, hi_floor=90):
    """Una fila de cielo: puntos blancos dispersos, deterministas por (row, col).
    `mod` controla la densidad (mayor = más ralo) y `hi_floor` cuántas son brillantes
    (mayor = menos grandes); el caller los varía con la altura para dar profundidad."""
    if width <= 0:
        return ""
    cells = []
    for c in range(width):
        h = _hsh(row, c)
        if h % mod == 0:                                 # ~1/mod densidad → dispersas
            t = (h >> 6) % 100
            if t < 70:                                   # tenues (mayoría)
                cells.append(_STAR_DIM[(h >> 10) % len(_STAR_DIM)] + _GLYPH_D[(h >> 14) % len(_GLYPH_D)] + R)
            elif t < hi_floor:                           # medias
                cells.append(_STAR_MID[(h >> 10) % len(_STAR_MID)] + "·" + R)
            else:                                        # brillantes (raras, menos hacia abajo)
                cells.append(_STAR_HI + _GLYPH_H[(h >> 14) % len(_GLYPH_H)] + R)
        else:
            cells.append(" ")
    return "".join(cells)


def _heartbeat_line():
    """Fila de info del heartbeat para el banner — hermana de `agentes`/`motor`:
    etiqueta tenue `latido` + valores dorados con separadores `·`, mismo patrón que
    build_info_rows. Solo glifos angostos ASCII + `·` (Windows-safe: NADA del rango
    0x2600-0x27BF ni emojis — ver runbooks/windows-support.md).
    Falla-suave ABSOLUTA: si heartbeat.py / usage.json / el backlog no existen
    o cualquier cosa truena → "" (la línea se omite; el banner JAMÁS se rompe)."""
    try:
        import heartbeat
        st = heartbeat.state()
        mode = st.get("mode") or "?"
        if mode == "off":
            return f"{DIM}latido  {GREY}off{DIM} · cola en espera{R}"
        b = st.get("budget") or {}
        pct = b.get("pct")
        uso = "?" if pct is None else f"{round(pct)}%"
        ln = (f"{DIM}latido  {C}{mode}{DIM} · cola {C}{st.get('count', 0)}{DIM}"
              f" · uso 5h {C}{uso}{R}")
        if b.get("ok") is not True:                  # tope alcanzado o dato desconocido
            ln += f"{DIM} · {B}presupuesto en pausa{R}"
        return ln
    except Exception:
        return ""


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
            ver = "v" + short if oks and short else branch
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
        uso = "uso 5h " + ("?" if pct is None else f"{round(pct)}%")
        parts = [HB_TAGS.get(mode, ""), f"cola {st.get('count', 0)}"]
        nxt = st.get("next")
        if nxt and mode != "off":
            nxt = nxt if len(nxt) <= 30 else nxt[:29] + "…"
            parts.append(f"next {nxt}")
        parts.append(uso)
        if b.get("ok") is not True:                  # tope alcanzado o dato desconocido
            parts.append("presupuesto en pausa")
        ln = " · ".join(p for p in parts if p)
        if len(ln) > render.W and nxt:               # no desbordar el bloque (rompería el redraw)
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


def _franja(agents):
    """Franja fina (reemplaza la caja gruesa): tagline + estado del harness, centrado."""
    orn = f"{DK}{GSEP * 12}{C} {GORN} {DK}{GSEP * 12}{R}"
    try:                                              # versión del harness (saber qué build corre un cliente)
        _v = open(os.path.join(ROOT, "VERSION"), encoding="utf-8").read().strip()
    except Exception:
        _v = ""
    tag = f"{DIM}{_t('hub.franja.tag', 'WORKSPACE · OS de agentes')}{(' · v' + _v) if _v else ''}{R}"
    # Sin listas de nombres (agentes/cerebros) aquí: cada agente ya se rotula bajo
    # su fuego. Solo el estado compacto del harness para no saturar ni desbordar.
    # El motor ya NO va fijo: es el binding EFECTIVO (harnesses.binding) — con
    # motores mezclados dice `N motores` y el detalle vive en la caja AGENTES.
    l2 = (f"{DIM}{_t('hub.franja.engine', 'motor')}  {C}{_motor_summary(agents)}"
          f"{DIM}{_t('hub.franja.engine_suffix', ' · sin API key · sync')}{R}")
    out = [_ctr(orn), "", _ctr(tag), "", _ctr(l2)]
    hb = _heartbeat_line()
    if hb:
        out.append(_ctr(hb))
    return out


def _wordmark_reflection():
    """Franja-REFLEJO ░ bajo el wordmark del recinto clásico (toque de grises
    2026-10-02): la silueta de las 2 últimas filas del ANSI Shadow en orden
    espejo, B2 → DK desvaneciéndose — el mismo gesto que al socio le gustó en el
    Tono y que ya viven los layouts `dia`/`centro` (hublayout.title_reflection).
    Mismo centrado que render.wordmark_plain(). Falla-suave ABSOLUTA → []."""
    try:
        rows = render.WORD
        pad = " " * max(0, ((render.W + 4) - max(len(r) for r in rows)) // 2)
        out = []
        for tint, row in ((B2, rows[-1]), (DK, rows[-2])):
            sil = "".join(" " if ch == " " else "░" for ch in row)
            out.append(f"{pad}{tint}{sil}{R}")
        return out
    except Exception:
        return []


def _menu_machinery(tout):
    """Estado + closures de RENDER del recinto: altar, cielo, full_draw/redraw.
    Compartido por los dos drivers de input (_animated_loop_unix y
    _animated_loop_windows): aquí vive TODO lo que pinta y la semántica del menú
    (nav/activate/tick); en los drivers solo vive el mecanismo de teclado y el
    reloj. Misma salida en ambas plataformas."""
    reg = registry()
    # Registry de HARNESSES (harness-os): binding efectivo por agente + ciclo
    # con la tecla `m`. Falla-suave ABSOLUTA: sin harnesses.py el hub queda
    # exactamente como antes (sin selector; el engine mostrado = agent.json).
    try:
        import harnesses as _harn
    except Exception:
        _harn = None
    agents = []
    for a in reg.get("agents", []):
        m = _meta(a)
        try:
            brain = a.get("brain") or dispatch.resolve_brain(a["name"], m)
        except Exception:
            brain = ""
        eng_default = m.get("engine") or a.get("engine") or "claude-code"
        if _harn:
            try:
                eng_eff, eng_src = _harn.binding(a["name"], eng_default)
            except Exception:
                eng_eff, eng_src = eng_default, "agente"
        else:
            eng_eff, eng_src = eng_default, "agente"
        agents.append({"name": a["name"],
                       "display": m.get("display_hub", m.get("display", a["name"])),
                       "color": m.get("color", AGENT_COLORS.get(a["name"], "red")),
                       "brain": brain,
                       "tagline": m.get("tagline", ""),
                       "engine": eng_default,
                       "engine_eff": eng_eff,      # binding EFECTIVO (lo que lanzará dispatch)
                       "engine_src": eng_src,      # 'local' (per-máquina) | 'agente' (agent.json)
                       "active": True})
    for p in reg.get("planned", []):
        agents.append({"name": p, "display": p.capitalize(), "brain": "",
                       "color": AGENT_COLORS.get(p, "red"), "tagline": "",
                       "active": False})
    NA = len(agents)
    # «Config» fuera del MENÚ (el socio 2026-10-02) — se rehace después; el
    # subsistema (config_tui) sigue vivo, solo no se lista. Ver items().
    # «Dev» fuera del MENÚ (el socio 2026-10-02) — el panel vive en `workspace
    # dev` (ruteo de __dev__ intacto). «Proyectos» fuera del MENÚ (el socio
    # 2026-10-02) — la app vive en `workspace proyectos`. Las opciones salen
    # del registro CANÓNICO (menu_entries: GitHub siempre, «Dev» gated al
    # dueño/dev, Calendario/Tono/Atajos/Actualizaciones/Agregar/Terminal) —
    # misma fuente que items() y que la sección «menú» de keybinds.
    opts = [(tok, lbl) for tok, lbl, _tag in menu_entries()]
    # TECLAS RÁPIDAS (registro keybinds, re-mapeable en «Atajos»): mapa
    # tecla→ítem + display por sección + acciones (motor/info). Lo consumen
    # jump()/quick() (drivers) y lo PINTAN los layouts junto a cada opción.
    JUMP, JKEYS, AKEYS = _jump_map(agents, opts)
    hb = _hb_snapshot()                               # snapshot del latido (para el status vivo del layout)
    # 3ª sección del recinto: CONFIGS rápidas (pins editables — ui.hub_pins).
    # El id interno del grupo sigue siendo "latido" (legacy, invisible al
    # socio) para no regar el ruteo; la sección se llama CONFIGS y hoy
    # muestra/edita los pins (latido.mode es UNO de ellos). Se muestra si hay
    # pins (por default los hay); sin pins la sección se OMITE (falla-suave).
    def _pins_now():
        """CONFIGS ancladas (ui.hub_pins) → [{key,label,value}]. Falla-suave
        TOTAL: cualquier problema → []."""
        try:
            import settings as _st
            return _st.hub_pins_resolved()
        except Exception:
            return []

    def _lang_opts():
        """Opciones del cuadro IDIOMA → [(code, nombre_nativo, es_activo)].
        Falla-suave TOTAL: sin i18n → [] (el cuadro se OMITE, jamás levanta)."""
        try:
            import i18n as _i18n
            active = _i18n.lang()
            return [(c, n, c == active) for c, n in _i18n.available()]
        except Exception:
            return []
    groups = ["dioses", "tools"] + (["latido"] if _pins_now() else [])
    # CALENDARIO: sección navegable propia, y solo si el LAYOUT activo la
    # dibuja (hublayout marca `"cal": True` en su entrada del registro). Así
    # `clasico` y `centro` no ganan una sección fantasma que no pintan.
    # (`_laybox` se arma más abajo; aquí se resuelve el layout directo.)
    # «idioma»: sección navegable PROPIA (cuadro bajo PERSONALIZACIÓN) — dos
    # opciones ES/EN visibles, ◄► mueve el cursor y Enter aplica (i18n.set_lang)
    # con flip EN VIVO. UNIVERSAL: va en TODOS los layouts (clasico/centro/dia)
    # y en la ventana alta/doble, no solo en pantalla completa (regla dura del
    # estilo TUI, 2026-10-05). Cada layout dibuja el cuadro bajo su caja de
    # personalización/«TEMAS Y AJUSTES». Va ANTES de "cal" en el orden de ↑↓.
    groups.append("idioma")
    try:                        # import local: `_hl` se importa mas abajo
        import hublayout as _hl0
        if (_hl0.active() or {}).get("cal"):
            groups.append("cal")
    except Exception:
        pass
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
    S = {"cal_off": 0, "cal_mode": "", "cal_buf": "", "cal_msg": "",
         "group": _g0, "gsel": 0, "asel": 0, "ph": 0, "msg": "", "hb_msg": "",
         "hb_mode": _hb0, "cfg_focus": 0, "lang_focus": _lf0,
         "hb_focus": HB_MODES.index(_hb0) if _hb0 in HB_MODES else 0,
         "frame": 0, "ign_start": 0, "BH": 0, "row0": 0,
         # frame de ANIMACIÓN de layouts con anim=True (centro): avanza a
         # cadencia BAJA en tick() — los sprites solo cambian de glifo
         "anim": 0,
         # indicador de versión abajo-derecha (calculado una vez por sesión, sin red)
         "ver_line": _hub_version_line()}

    def gk():
        return groups[S["group"]]

    # ── LAYOUT del hub (hublayout.py — eje independiente del tema): con un
    #    layout NO-clasico activo, el dibujo se delega a su renderer con los
    #    MISMOS datos (agentes+estado, acciones, latido) y la MISMA semántica
    #    de teclado (nav/activate intactos). clasico → lay=None y NADA del
    #    camino nativo cambia (paridad por construcción). Falla-suave
    #    ABSOLUTA: sin hublayout / renderer roto → recinto clásico. ──
    try:
        import hublayout as _hl
    except Exception:
        _hl = None
    _laybox = {"lay": None}
    try:
        _laybox["lay"] = _hl.active() if _hl else None
    except Exception:
        _laybox["lay"] = None

    _LAYP = TH
    _LDATA = None            # solo existe con layout alternativo (ver abajo)
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
                  "hb_modes": HB_MODES, "hb_tags": HB_TAGS,
                  "version": _ver, "version_text": _hub_version_text()[0],
                  # motor REAL en uso (antes iba fijo 'claude-code'): resumen
                  # de los bindings efectivos; cycle_engine lo refresca.
                  "motor": _motor_summary(agents),
                  # teclas de SALTO (1-9 · q) por sección: los layouts las
                  # pintan JUNTO a cada opción (transparencia). Sin "keys" en
                  # data (banner/tests) renderizan como siempre.
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
                "msg": S["msg"], "hb_msg": S["hb_msg"],
                # ALTO real: layouts que llenan la pantalla (cockpit) lo usan;
                # los demás lo ignoran. El resize ya re-dibuja completo.
                "h": S["term_h"],
                # frame de animación (layouts anim=True — sprites del centro)
                "anim": S.get("anim", 0),
                # calendario navegable (layouts con "cal": True)
                "cal_off": S.get("cal_off", 0),
                "cal_mode": S.get("cal_mode", ""),
                "cal_buf": S.get("cal_buf", ""),
                "cal_msg": S.get("cal_msg", "")}
        lines = _laybox["lay"]["render"](_LDATA, view, _LAYP, S["term_w"])
        S["hit"] = tuple(view.get("hit") or ())
        return lines

    def section_title(txt, on, hint=None):
        if hint is None:
            hint = _t("hub.classic.section_hint", "◄ ► elegir")
        mark = f"{GPTR} " if on else "  "
        body = f"{C}{BO}{mark}{txt}{R}" if on else f"{DK}{mark}{txt}{R}"
        tail = f"   {DIM}{hint}{R}" if on else ""
        return _ctr(body + tail)

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
            disp = "on" if newv is True else ("off" if newv is False
                                              else str(newv))
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
                    S["hb_msg"] = (f"{p['label']} → {disp} (guardado · ajusta el "
                                   f"rc a mano)")
                    return
            S["hb_msg"] = f"{p['label']} → {disp} (guardado)"
        except Exception:
            S["hb_msg"] = f"no pude cambiar «{p['label']}» — queda igual"

    def apply_lang():
        """Enter/espacio en el cuadro IDIOMA: aplica el idioma ENFOCADO
        (i18n.set_lang, persiste ui.lang) y refresca las etiquetas del MENÚ
        para que el hub flipee EN VIVO (el ● del cuadro se mueve solo: lee
        i18n.lang() en cada render). Los tokens del menú NO cambian con el
        idioma → jump/akeys/asel siguen válidos; solo se reconstruyen las
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

    def toggle_redlight():
        """Tecla rápida del hub (`l`): enciende/apaga el MODO LUZ ROJA
        (ui.redlight) — pantalla en rojo nocturno. Persiste el bool y deja un
        aviso visible; la paleta se re-resuelve EN VIVO al siguiente frame
        (tuitheme memoiza por este flag → sync_theme detecta el cambio y
        repinta). Falla-suave ABSOLUTA: cualquier problema deja un aviso y el
        recinto sigue igual."""
        try:
            import settings as _st
            newv = not bool(_st.enabled("ui.redlight", default=False))
            _st.set("ui.redlight", newv)
            S["msg"] = (_t("hub.redlight.on", "luz roja ON — modo noche")
                        if newv else
                        _t("hub.redlight.off", "luz roja OFF"))
        except Exception:
            S["msg"] = _t("hub.redlight.fail",
                          "no pude cambiar la luz roja — queda igual")

    # Divisor entre secciones con FADE de grises (toque 2026-10-02, mismo
    # juego que el reflejo del Tono): el centro apenas más claro (GREY) y los
    # extremos hundidos (DK) — la regla gana profundidad sin cambiar de ancho.
    SEP = _ctr(f"{DK}{GSEP * 8}{GREY}{GSEP * 8}{DK}{GSEP * 8}{R}")

    def block_lines():
        """Bloque interactivo (centrado): DIOSES → HERRAMIENTAS → LATIDO.
        Con un LAYOUT alternativo activo devuelve las líneas de ESE layout
        (misma fuente para el hub interactivo y `--banner`)."""
        if _laybox["lay"]:
            try:
                return _lay_lines()
            except Exception:
                _laybox["lay"] = None        # layout roto → recinto clásico
        return _classic_block_lines()

    def _classic_block_lines():
        """El bloque clásico de SIEMPRE (intacto — paridad del default).
        Cada sección va dividida por un separador y tiene su PROPIO renglón de
        avisos — la confirmación del latido jamás se cuela bajo HERRAMIENTAS.
        Devuelve SIEMPRE el mismo nº de líneas (BH estable para el redraw)."""
        # ── DIOSES (altar de urnas) ──
        L = [section_title(_t("hub.section.gods", "DIOSES"), gk() == "dioses"), ""]
        t = min(1.0, max(0, S["frame"] - S["ign_start"]) / 5.0)  # encendido en ~0.16s (refresco ~30fps)
        ig = t * (2.0 - t)                              # ease-out: prende rápido y se asienta (agresivo)
        L += render.altar(agents, S["gsel"], S["ph"], ig,
                          keys=JKEYS.get("agents"))     # tecla de salto visible bajo cada urna
        # Selector de HARNESS inline (harness-os): binding efectivo del agente
        # seleccionado + hint de la tecla. SIEMPRE 1 línea (BH estable) — sin
        # agentes va vacía. El punto distingue override local (●) de default
        # del agent.json (sin marca).
        if NA and gk() == "dioses":
            _a = agents[S["gsel"]]
            _e = _a.get("engine_eff") or _a.get("engine") or "?"
            _loc = f" {C}●{R}" if _a.get("engine_src") == "local" else ""
            L.append(_ctr(f"{DIM}{_t('hub.classic.engine_prefix', 'motor ▸ ')}{R}{C}{_e} ▾{R}{_loc}"
                          f"  {DK}{_t('hub.classic.engine_change', 'm cambia')}{R}"))
        else:
            L.append("")
        L.append(_ctr(f"{DIM}{S['msg']}{R}") if S["msg"] else "")   # aviso de DIOSES (urna no invocada)
        # ── HERRAMIENTAS ──
        L += ["", SEP, "", section_title(_t("hub.section.menu", "MENÚ"), gk() == "tools"), ""]
        btns = []
        for j, (tok, lbl) in enumerate(opts):
            # tecla de SALTO visible dentro del botón («5 Ramas» … «q Terminal
            # normal») — transparencia: el dígito vive junto a su opción.
            k = JKEYS["opts"].get(j, "")
            lbl = f"{k} {lbl}" if k else lbl
            if j == S["asel"] and gk() == "tools":
                # ACTIVO + foco: dorado brillante, negrita, shimmer luminoso
                btns.append(f"{C}{BO}{GBL} {R}{_shimmer(lbl, S['ph'], C, WH)}{C}{BO} {GBR}{R}")
            elif j == S["asel"]:
                # ACTIVO sin foco: brackets dorados + texto blanco+negrita — inconfundible
                btns.append(f"{C}{GBL} {BO}{WH}{lbl}{R}{C} {GBR}{R}")
            else:
                # INACTIVO con PROFUNDIDAD (grises, 2026-10-02): los vecinos
                # inmediatos de la selección conservan el ámbar tenue; de dos
                # lugares en adelante se hunden a gris oscuro — el menú se lee
                # como un foco con penumbra alrededor, no una lista plana.
                lejos = abs(j - S["asel"]) >= 2
                btns.append(f"{INACTIVE_HB if lejos else INACTIVE}  {lbl}  {R}")
        # Reflow ESTABLE de los botones: con teclas de salto + «Atajos» la
        # fila única ya no cabe en content_w (desbordar rompe el redraw con
        # drift). Corte por anchos visuales reales — el ancho de cada botón
        # NO depende de la selección (lbl+4 siempre), así el nº de filas
        # solo depende de opts (BH estable).
        filas, fila, fw = [], [], 0
        for b in btns:
            bw = _vis(b)
            extra = 2 if fila else 0
            if fila and fw + extra + bw > content_w:
                filas.append(fila); fila, fw = [], 0
            fila.append(b); fw += bw + extra
        if fila:
            filas.append(fila)
        for f in filas:
            L.append(_ctr("  ".join(f)))
        pins = _pins_now()
        if pins:
            # ── CONFIGS rápidas (pins EDITABLES — ui.hub_pins) ──────────────
            # Reemplaza al radio del latido suelto: latido.mode es UN pin más.
            # ◄► mueve el cursor entre pins · Enter/espacio CICLA el valor del
            # enfocado (enum → siguiente choice · bool → on/off) y persiste.
            # Falla-suave TOTAL y CONTEO ESTABLE (los pins de la sesión son
            # fijos → el bloque no altera el BH del redraw; el ciclado solo
            # cambia el TEXTO del valor, no el nº de líneas).
            L += ["", SEP, ""]
            focus = gk() == "latido"
            L.append(section_title(_t("hub.section.personalization", "PERSONALIZACIÓN"), focus,
                                   hint=_t("hub.classic.pers_hint", "◄ ► elige · Enter/espacio cambia")))
            L.append("")
            cf = S["cfg_focus"] % len(pins)
            for i, p in enumerate(pins):
                lab, val = p["label"], p["value"]
                if focus and i == cf:
                    # ENFOCADO: brackets dorados + valor brillante (mismo
                    # lenguaje de foco que MENÚ y el ex-radio del latido).
                    L.append(_ctr(f"{C}{BO}{GBL} {R}{DIM}{lab}  {R}"
                                  f"{_shimmer(val, S['ph'], C, WH)}"
                                  f"{C}{BO} {GBR}{R}"))
                else:
                    L.append(_ctr(f"{DK}▸ {DIM}{lab}  {C}{BO}{val}{R}"))
            # confirmación/aviso de CONFIGS: renglón propio DENTRO de su
            # sección (jamás colado bajo MENÚ) — SIEMPRE reservado (BH estable).
            L.append(_ctr(f"{DIM}{S['hb_msg']}{R}") if S["hb_msg"] else "")
            # (el hint «Config ▸ para más ajustes» se retiró con la entrada
            #  Config del MENÚ — el socio 2026-10-02; la sección se rehará)
        # ── IDIOMA · LANGUAGE (bajo PERSONALIZACIÓN) — en TODOS los layouts ──
        _langs = _lang_opts()
        if _langs:
            L += ["", SEP, "", section_title(_t("hub.section.lang", "IDIOMA · LANGUAGE"),
                                             gk() == "idioma",
                                             hint=_t("hub.classic.lang_hint", "◄ ► elige · Enter cambia")), ""]
            lf = S["lang_focus"] % len(_langs)
            for i, (code, name, act) in enumerate(_langs):
                marca = f"{C}●{R}" if act else f"{DK}·{R}"
                if gk() == "idioma" and i == lf:
                    L.append(_ctr(f"{C}{BO}{GBL} {R}{marca} "
                                  f"{_shimmer(name, S['ph'], C, WH)}"
                                  f"{C}{BO} {GBR}{R}"))
                else:
                    tinta = WH if act else DIM
                    L.append(_ctr(f"{DK}▸ {R}{marca} {tinta}{name}{R}"))
        L.append("")
        # Indicador de versión ABAJO-DERECHA: rama + estado de sync/update. Siempre
        # el mismo nº de líneas (BH estable) — si no hay git, la línea va vacía.
        ver = S.get("ver_line", "")
        L.append(_rgt(ver) if ver else "")
        return L

    # ╔══════════════════════════════════════════════════════════════════════╗
    # ║ NO TOCAR ESTA FÓRMULA DE PANTALLA (costó MUCHO afinarla, 2026-06-08).  ║
    # ║ Banner pegado arriba + sin scrollbar en Terminal.app de Mac:           ║
    # ║   • clear = "\033[2J\033[3J\033[H"  EN ESTE ORDEN (pantalla→scroll-     ║
    # ║     back→home). El orden inverso (3J antes que 2J) corre el viewport.  ║
    # ║   • imprimir EN FLUJO + redibujar con cursor-up "\033[{BH}A".          ║
    # ║   • greeter = `workspace` directo (NADA de precmd/sleep/clear extra).    ║
    # ║   • EVITAR DENTRO DEL FRAME: autowrap-off (\033[?7l), posicionamiento  ║
    # ║     absoluto por fila, y \033[3J SUELTO o antes de 2J (rompen scroll). ║
    # ║   • ALT-SCREEN (\033[?1049h): ahora SÍ se usa, pero SOLO como envoltura ║
    # ║     en animated_menu (entrar/salir) para BLOQUEAR el scroll (pedido de  ║
    # ║     el equipo, jun). El DIBUJO interno sigue estas reglas igual. Opt-out ║
    # ║     WORKSPACE_NO_ALTSCREEN=1 si una terminal lo odia. Probar en Terminal.app.║
    # ╚══════════════════════════════════════════════════════════════════════╝
    # (Windows Terminal honra esta MISMA fórmula — el driver Windows la usa tal cual.)
    # REACTIVO AL ANCHO: margen izq = (ancho terminal − ancho contenido)/2 → centrado.
    # Se recalcula en cada resize y se repinta. (Init: 2J3J; resize/redraw: home + \033[K
    # en su lugar — NUNCA \033[2J a media sesión, que deja basura en Terminal.app.)
    content_w = render.W + 4
    # ancho mínimo utilizable: los layouts alternativos operan más angosto
    # que el recinto clásico (que necesita content_w para su arte centrado).
    S["min_w"] = (_hl.MIN_W if (_laybox["lay"] and _hl) else content_w)

    def gsize():
        try:
            ts = os.get_terminal_size(tout.fileno())
            return ts.columns, ts.lines      # ANCHO REAL (centramos a él; ya no forzamos content_w)
        except Exception:
            return content_w, 40

    S["term_w"], S["term_h"] = gsize()

    def _lm():
        return " " * max(0, (S["term_w"] - content_w) // 2)

    def _starwrap(ln, row):
        """Envuelve una línea del banner en cielo: estrellas en los márgenes (y a
        todo lo ancho si la línea va vacía), con un gutter limpio que no toca el texto."""
        LM = _lm(); lmn = len(LM)
        if not STARS:
            return (LM + ln) if ln else ""
        m = 25 + (row * 12) // max(1, S["term_h"])       # profundidad sutil: denso arriba → ralo abajo
        hf = 90 + (row * 10) // max(1, S["term_h"])      # brillantes se desvanecen hacia abajo (10% → ~0%)
        if not ln:                                       # línea vacía → cielo de ancho completo
            return _starline(S["term_w"] - 1, row, m, hf)
        body = ln + " " * max(0, content_w - _vis(ln))    # gutter limpio alrededor del banner
        right = max(0, (S["term_w"] - 1) - lmn - content_w)
        return _starline(lmn, row, m, hf) + body + _starline(right, row + 977, m, hf)

    def _narrow_draw(first):
        """Functional compact hub: same keyboard and actions, no width gate."""
        import responsive_ui as _responsive
        w, h = S['term_w'], S['term_h']
        S['narrow'] = False
        S['compact'] = True
        S['hit'] = ()                 # no stale mouse regions from rich layout
        if _responsive.vertical(w, h):
            if 'cal' in groups:
                if gk() == 'cal':
                    S['group'] = groups.index('tools')
                groups.remove('cal')
            row_width = w - 11
            def keyed(label, key):
                return _hl.pad(_hl.clip(label, max(1, row_width - len(key) - 2)), max(1, row_width - len(key))) + key
            agent_rows = [keyed(a['display'] + ' · ' + a.get('engine_eff', '?'), str(JKEYS.get('agents', {}).get(i, ''))) for i,a in enumerate(agents)]
            menu_rows = [keyed(label, str(JKEYS.get('opts', {}).get(i, ''))) for i,(_,label) in enumerate(opts)]
            pin_rows = [str(p.get('label', p.get('key', ''))) + ' · ' + str(p.get('value', '')) for p in _pins_now()]
            lang_rows = [('● ' if act else '· ') + name
                         for _code, name, act in _lang_opts()]
            lines = _responsive.vertical_hub(agent_rows, menu_rows, pin_rows, w, h,
                        gk(), S['gsel'], S['asel'], S['cfg_focus'],
                        langs=lang_rows, lang_idx=S['lang_focus'])
            _responsive.paint(tout, lines, first)
            S['BH'], S['row0'] = len(lines), 0
            return S['BH']
        group = gk()
        rows, selected = [], 0
        if group == 'dioses':
            selected = S['gsel']
            for i, agent in enumerate(agents):
                mark = '> ' if i == selected else '  '
                rows.append(mark + agent['display'] + ' · ' + agent.get('engine_eff', '?'))
            rows += ['', _t('hub.narrow.agents_hint',
                            'm motor · Enter abre · i información'),
                     S.get('msg', '')]
        elif group == 'tools':
            selected = S['asel']
            for i, (_, label) in enumerate(opts):
                rows.append(('> ' if i == selected else '  ') + label)
        elif group == 'latido':
            selected = S['cfg_focus']
            for i, pin in enumerate(_pins_now()):
                rows.append(('> ' if i == selected else '  ') + str(pin.get('label') or pin.get('key', ''))
                            + ' · ' + str(pin.get('value', '')))
            rows += ['', _t('hub.narrow.cfg_hint',
                            'Enter cambia · configuración disponible en el menú'),
                     S.get('hb_msg', '')]
        elif group == 'idioma':
            selected = S['lang_focus']
            for i, (_code, name, act) in enumerate(_lang_opts()):
                rows.append(('> ' if i == selected else '  ')
                            + ('● ' if act else '· ') + name)
            rows += ['', _t('hub.narrow.lang_hint',
                            'Enter cambia el idioma · Enter switches language')]
        else:
            import datetime as _dt
            day = _dt.date.today() + _dt.timedelta(days=S['cal_off'])
            rows = [str(day), _t('hub.narrow.cal_hint',
                                 'Flechas: día/semana · Enter evento'),
                    S.get('cal_buf', ''), S.get('cal_msg', '')]
        title = 'WORKSPACE · ' + {
            'dioses': _t('hub.section.agents', 'AGENTES'),
            'tools': _t('hub.section.menu', 'MENÚ'),
            'latido': _t('hub.section.configs', 'CONFIGS'),
            'cal': _t('hub.section.calendar', 'CALENDARIO'),
            'idioma': _t('hub.section.lang', 'IDIOMA · LANGUAGE')}.get(group, group)
        _nav = "↑↓ %s · ◄► %s · Enter %s · q %s" % (
            _t('common.hint.section', 'sección'),
            _t('common.hint.pick', 'elige'),
            _t('common.hint.enter', 'entra'),
            _t('common.hint.terminal', 'terminal'))
        rows += ['', _nav]
        lines = _responsive.hub_frame(rows, w, h, focus=selected, title=title,
                                      hint=_nav)
        _responsive.paint(tout, lines, first)
        S['BH'] = len(lines)
        S['row0'] = 0
        return S['BH']

    def _lay_full_draw(first):
        """Pantalla completa de un LAYOUT alternativo. MISMA fórmula de
        pantalla del recinto (2J3JH inicial · home + \\033[K después — ver el
        recuadro de abajo); solo cambia el CONTENIDO. Sin cielo: la
        estructura la dicta el layout (el cielo del clásico queda intacto).
        Renderer roto → se anula el layout y se cae al recinto clásico."""
        try:
            lines = _lay_lines()
        except Exception:
            _laybox["lay"] = None
            S["min_w"] = content_w
            return full_draw(first)
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
        nonlocal _LAYP, SEP
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
        SEP = _ctr(DK + GSEP * 8 + GREY + GSEP * 8 + DK + GSEP * 8 + R)
        for role in ('B','B2','C','WH','DIM','DK','R','BO','WCOL','FIRE','OFF'):
            if hasattr(p, role):
                setattr(render, role, getattr(p, role))
        render._TH, render._INACTIVE, render._GL = p, p.INACTIVE, p.GLYPHS
        render._EMBER_REST = p.EMBER
        import theme
        if p.OSC:
            theme.apply_colors(p.OSC)
        else:
            theme.apply("workspace")
        return True

    def full_draw(first=False):
        sync_theme()
        if S["term_w"] < max(100, S["min_w"]) or S["term_h"] < 32:                     # demasiado angosta → pantalla segura
            return _narrow_draw(first)
        S["narrow"] = False
        S["compact"] = False
        if _laybox["lay"] and _laybox["lay"].get("cal") and "cal" not in groups:
            groups.append("cal")
        if _laybox["lay"]:
            return _lay_full_draw(first)
        _ac = JKEYS.get("acciones") or {}
        # atajos clave BAJO el wordmark, legibles (tecla en acento, acción
        # en gris — hublayout.keyline, el lenguaje de hints de todo el hub);
        # sin hublayout cae a la línea DIM de siempre (falla-suave)
        _act = {"motor": _t("common.hint.engine", "motor"),
                "info": _t("common.hint.info", "información")}
        _key = _t("common.hint.key", "tecla")
        _pares = ([("↑↓", _t("common.hint.menu", "menú")),
                   ("◄►", _t("common.hint.pick", "elige")),
                   ("Enter", _t("common.hint.enter", "entra")),
                   (_key, _t("common.hint.aim_open", "apunta/abre"))]
                  + [(_ac[n], _act[n]) for n in ("motor", "info") if _ac.get(n)]
                  + [("l", _t("common.hint.redlight", "luz roja")),
                     ("q", _t("common.hint.terminal", "terminal"))])
        if _hl:
            hdr = _ctr(_hl.keyline(_hl.cols(TH), _pares,
                                   max(20, S["term_w"] - 4)))
        else:
            _hx = "".join(f" · {_ac[n]} {_act[n]}" for n in ("motor", "info")
                          if _ac.get(n))
            hdr = _ctr(f"{DIM}↑↓ {_pares[0][1]} · ◄► {_pares[1][1]} · "
                       f"Enter {_pares[2][1]} · "
                       f"{_key} {_t('common.hint.aim_open', 'apunta/abre')}"
                       f"{_hx} · l {_t('common.hint.redlight', 'luz roja')}"
                       f" · q {_t('common.hint.terminal', 'terminal')}{R}")
        upper = (list(render.wordmark_plain()) + _wordmark_reflection() + [""]
                 + _franja(agents) + ["", hdr, ""])      # cielo + banner (+ reflejo ░ en grises)
        lower = block_lines()                            # bloque interactivo: lo repinta redraw()
        top = max(2, (S["term_h"] - (len(upper) + len(lower))) * 2 // 5)   # ~0.4
        out = "\033[2J\033[3J\033[H" if first else "\033[H"
        row = 0
        for ln in ([""] * top) + upper:                  # cielo + banner
            out += "\r\033[K" + _starwrap(ln, row) + "\r\n"; row += 1
        S["row0"] = row                                  # fila absoluta donde arranca el bloque interactivo
        for ln in lower:                                 # bloque interactivo (con cielo en sus márgenes)
            out += "\r\033[K" + _starwrap(ln, row) + "\r\n"; row += 1
        bottom_n = max(0, S["term_h"] - row - 1)         # relleno de cielo hasta el fondo (estático)
        for _ in range(bottom_n):
            out += "\r\033[K" + _starwrap("", row) + "\r\n"; row += 1
        if bottom_n:
            out += f"\033[{bottom_n}A"                   # estaciona el cursor justo tras `lower`
        tout.write(out); tout.flush()
        S["BH"] = len(lower)                             # alto del bloque que redraw() reescribe
        return S["BH"]

    def redraw():
        if sync_theme():
            return full_draw(first=False)
        if S.get('compact'):
            return full_draw(first=False)

        if S.get("narrow"):                          # pantalla angosta = estática, sin arte que repintar
            return
        if _laybox["lay"]:
            try:
                lines = _lay_lines()
            except Exception:
                _laybox["lay"] = None                # layout roto → recinto clásico
                S["min_w"] = content_w
                return full_draw(first=False)
            if len(lines) != S["BH"]:                # altura cambió (defensa) → repintado completo
                return full_draw(first=False)
            tout.write(f"\033[{S['BH']}A")
            for ln in lines:
                tout.write("\r\033[K" + ln + "\r\n")
            tout.flush()
            return
        tout.write(f"\033[{S['BH']}A")               # sube BH líneas y reescribe el bloque
        r = S["row0"]
        for ln in block_lines():
            tout.write("\r\033[K" + _starwrap(ln, r) + "\r\n"); r += 1
        tout.flush()

    def check_resize():
        nw, nh = gsize()                             # ¿cambió el tamaño? → re-centra
        if (nw, nh) != (S["term_w"], S["term_h"]):
            S["term_w"], S["term_h"] = nw, nh
            full_draw(first=False)

    def tick():
        """Un paso del reloj (~30fps): resize + parpadeo de la llama + ignición."""
        check_resize()
        if sync_theme():
            full_draw(first=False)
        if _laybox["lay"]:
            # layouts con anim=True (centro): avanza el frame de sprites a
            # cadencia BAJA (~0.83s = 25 ticks) y redibuja el bloque — el
            # MISMO redraw con cursor-up de un keypress, jamás full-screen
            # de alta frecuencia (lección del cielo estático en Mac).
            if _laybox["lay"].get("anim"):
                S["frame"] += 1
                if S["frame"] % 25 == 0:
                    S["anim"] = S.get("anim", 0) + 1
                    redraw()
            return                                   # sin llama que animar
        S["frame"] += 1
        flick = (S["frame"] % 3 == 0)                # la llama parpadea a ~10fps (constante)
        if flick:
            S["ph"] += 1
        if flick or (S["frame"] - S["ign_start"]) <= 5:   # redibuja solo si cambió (parpadeo o ignición)
            redraw()

    def nav(d):
        """Flechas — misma semántica en ambas plataformas: ↑↓ sube/baja de
        sección (dioses → MENÚ → CONFIGS, con tope), ◄► anterior/siguiente
        dentro de la sección. En CONFIGS ◄► mueve el CURSOR entre pins — el
        valor lo cicla Enter/espacio (activate/cycle)."""
        S["msg"] = ""; S["hb_msg"] = ""
        if S.get("cal_mode") == "add":
            return                                   # escribiendo: flechas no navegan
        if gk() == "cal" and d in ("up", "down"):
            # dentro del calendario ↑↓ mueven de SEMANA; solo se sale de la
            # sección cuando el salto se iría del mes (arriba por el borde
            # de arriba, abajo por el de abajo) — igual que un calendario.
            import datetime as _dt
            hoy = _dt.date.today()
            cur = hoy + _dt.timedelta(days=S["cal_off"])
            nxt = cur + _dt.timedelta(days=-7 if d == "up" else 7)
            if nxt.month == cur.month:
                S["cal_off"] += -7 if d == "up" else 7
                return
        if d == "up":
            S["group"] = max(0, S["group"] - 1)
        elif d == "down":
            S["group"] = min(len(groups) - 1, S["group"] + 1)
        elif d in ("left", "right"):
            step = -1 if d == "left" else +1
            if gk() == "cal":
                import datetime as _dt
                hoy = _dt.date.today()
                cur = hoy + _dt.timedelta(days=S["cal_off"])
                nxt = cur + _dt.timedelta(days=step)
                if nxt.month == cur.month:           # el mes es el límite
                    S["cal_off"] += step
                return
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
        (urna aún no invocada; CONFIGS: Enter CICLA el pin enfocado)."""
        if S.get("narrow"):                          # angosto: nada que ver → no lanzar a ciegas
            return None
        if gk() == "dioses":
            if NA == 0:                                  # harness sin agentes
                S["msg"] = "sin agentes — ve a HERRAMIENTAS › Agregar agente"
                return None
            if agents[S["gsel"]]["active"]:
                return agents[S["gsel"]]["name"]
            S["msg"] = f"{agents[S['gsel']]['display']} aún no se invoca — llega pronto."
            return None
        if gk() == "latido":
            cycle_pin()
            return None
        if gk() == "idioma":
            apply_lang()
            return None
        if gk() == "cal":
            _cal_enter()
            return None
        return opts[S["asel"]][0]

    def _cal_fecha():
        import datetime as _dt
        return _dt.date.today() + _dt.timedelta(days=S.get("cal_off", 0))

    def _cal_enter():
        """Enter en el CALENDARIO: abre el alta o guarda lo escrito. El texto
        acepta una hora al principio (`18:00 Junta con Miguel`) — se parte y
        se guarda como hora del evento; sin hora, queda de día entero."""
        if S.get("cal_mode") != "add":
            S["cal_mode"], S["cal_buf"], S["cal_msg"] = "add", "", ""
            return
        txt = (S.get("cal_buf") or "").strip()
        S["cal_mode"], S["cal_buf"] = "", ""
        if not txt:
            S["cal_msg"] = ""
            return
        hora = ""
        primera = txt.split(" ", 1)
        if len(primera) == 2 and ":" in primera[0]:
            import re as _re
            if _re.match(r"^\d{1,2}:\d{2}$", primera[0]):
                hora, txt = primera[0], primera[1].strip()
        try:
            import personal
            ok = personal.add_event(_cal_fecha().isoformat(), txt, hora)
            S["cal_msg"] = ("guardado: %s" % txt[:40]) if ok \
                else "no pude guardarlo"
        except Exception:
            S["cal_msg"] = "no pude guardarlo"

    def key(ch):
        """Teclas sueltas. Con el alta abierta el hub se vuelve un campo de
        texto: TODO carácter imprimible entra al buffer (por eso los drivers
        consultan `cal_mode` antes de tratar la `q` como salir)."""
        if S.get("cal_mode") != "add":
            return False
        if ch in ("\x1b",):                          # Esc: cancelar
            S["cal_mode"], S["cal_buf"], S["cal_msg"] = "", "", "cancelado"
            return True
        if ch in ("\x7f", "\b", "\x08"):             # borrar
            S["cal_buf"] = S["cal_buf"][:-1]
            return True
        if ch and ch.isprintable() and len(S["cal_buf"]) < 80:
            S["cal_buf"] += ch
            return True
        return True                                  # en modo alta, se traga

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

    def cycle_engine():
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
            S["msg"] = f"{a['display']} aún no se invoca — sin motor que elegir."
            return
        if _harn is None:
            S["msg"] = "selector de motor no disponible (falta harnesses.py)"
            return
        try:
            res = _harn.cycle(a["name"], a.get("engine") or "claude-code")
        except Exception as e:
            res = {"ok": False, "error": f"{type(e).__name__}: {e}"}
        if not res.get("ok"):
            S["msg"] = f"no pude cambiar el motor: {res.get('error', '?')}"
            return
        a["engine_eff"], a["engine_src"] = res["engine"], res["source"]
        donde = ("guardado per-máquina" if res["source"] == "local"
                 else "default del agente")
        S["msg"] = f"motor de {a['display']} ▸ {res['engine']}  ({donde})"
        if _LDATA is not None:                       # refresca el pill/statusline
            _LDATA["motor"] = _motor_summary(agents)

    def jump(ch):
        """TECLA rápida de salto. Dos familias, dos verbos (keybinds):
          · agente → APUNTA sin lanzar (el poder real: ya apuntado aplican
            motor/info/Enter); la MISMA tecla otra vez = lanzarlo (confirmar
            repitiendo — sigue siendo instantáneo: «11» abre el agente 1).
          · opción del MENÚ → abre directo (pantallas reversibles, q/Esc
            regresan — no necesitan confirmación).
        Devuelve nombre/token a lanzar, o None (apuntado/sin ítem). Los
        drivers lo llaman SOLO fuera del alta del calendario."""
        t = JUMP.get(ch)
        if t is None or S.get("narrow"):
            return None
        kind, idx = t
        S["msg"] = ""; S["hb_msg"] = ""
        if kind == "agent":
            ya = (gk() == "dioses" and S["gsel"] == idx)
            S["group"] = groups.index("dioses")
            S["gsel"] = idx; S["ign_start"] = S["frame"]
            if not ya:
                return None                 # 1er toque: APUNTA (no lanza)
            return activate()               # mismo agente otra vez: ENTRA
        S["group"] = groups.index("tools")
        S["asel"] = idx
        return activate()

    def agent_info():
        """Acción `info` (default i): DETALLE del agente APUNTADO en la fila
        de aviso — el status en vivo sin lanzarlo ni cambiar de ventana:
        motor efectivo (y su origen), dónde vive el cerebro, tarea viva."""
        if S.get("narrow") or not NA:
            return
        S["group"] = groups.index("dioses")     # el aviso vive en AGENTES
        a = agents[S["gsel"]]
        if not a.get("active"):
            S["msg"] = f"{a['display']} aún no se invoca — llega pronto."
            return
        eng = a.get("engine_eff") or a.get("engine") or "?"
        orig = "override local" if a.get("engine_src") == "local" \
            else "default del agente"
        brain = (a.get("brain") or "").replace(os.path.expanduser("~"), "~") \
            or "—"
        now = _agent_now(a.get("brain")) or {}
        tarea = (now.get("task") or "").strip()
        vivo = f"ahora: {tarea}" if tarea else "sin tarea viva"
        S["msg"] = (f"{a['display']} ▸ motor {eng} ({orig}) · "
                    f"cerebro {brain} · {vivo}")

    def quick(ch):
        """Acción rápida re-mapeable (keybinds) sobre el agente APUNTADO —
        sin lanzarlo: motor (cicla el harness, ya persistía per-máquina) ·
        info (detalle en una línea). Desde cualquier sección: primero
        enfoca AGENTES (la acción siempre refiere al apuntado del altar)."""
        act = AKEYS.get(ch)
        if act == "motor":
            if gk() != "dioses":
                S["group"] = groups.index("dioses")
            cycle_engine()
        elif act == "info":
            agent_info()

    def click(x, y):
        """Click IZQUIERDO (SGR, 1-based). Hit-test contra las regiones que
        el layout reportó en su último render (S['hit'] — filas 0-based del
        bloque, que en layouts se pinta desde la fila 1 de la pantalla).
        MISMO contrato que el dígito: click = saltar + entrar; en un pin de
        PERSONALIZACIÓN = enfocar + ciclar (lo que haría Enter ahí). Sin
        regiones (clásico / layouts sin hit-map) → no-op, jamás lanza a
        ciegas. Escribiendo en el alta del calendario → no-op (no saltar a
        media captura)."""
        if S.get("narrow") or S.get("cal_mode") == "add":
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
            return None
        return None

    return types.SimpleNamespace(S=S, agents=agents, opts=opts, groups=groups,
                                 key=key,
                                 laybox=_laybox,
                                 block_lines=block_lines,
                                 gsize=gsize, full_draw=full_draw, redraw=redraw,
                                 tick=tick, nav=nav, activate=activate, space=space,
                                 toggle_redlight=toggle_redlight,
                                 cycle_engine=cycle_engine, jump=jump,
                                 click=click, quick=quick, jkeys=JKEYS,
                                 jump_set=frozenset(JUMP),
                                 akeys=dict(AKEYS),
                                 akeys_set=frozenset(AKEYS))


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
                    if a is None and M.S.get("cal_mode") == "add":
                        M.key("\x1b")                              # Esc cancela el alta
                    if a == "A": M.nav("up")                       # ↑ → dioses
                    elif a == "B": M.nav("down")                   # ↓ → herramientas
                    elif a == "D": M.nav("left")                   # ◄
                    elif a == "C": M.nav("right")                  # ►
                    elif isinstance(a, tuple) and a[0] == "mouse":
                        res = M.click(a[1], a[2])                  # click = saltar + entrar
                        if res is not None:
                            return res
                elif ch in ("\r", "\n"):
                    act = True
                elif ch == " " and M.S.get("cal_mode") != "add":
                    M.space()                                          # espacio → cicla pin en CONFIGS (no-op fuera)
                elif ch and ch.lower() in M.akeys_set \
                        and M.S.get("cal_mode") != "add":
                    M.quick(ch.lower())                                # acción rápida: motor/info del apuntado (keybinds)
                elif ch in M.jump_set and M.S.get("cal_mode") != "add":
                    res = M.jump(ch)                                   # salto directo (tecla visible junto al ítem)
                    if res is not None:
                        return res
                elif ch in ("l", "L") and M.S.get("cal_mode") != "add":
                    M.toggle_redlight()                               # `l` → luz roja (modo noche) on/off EN VIVO
                elif ch in ("q", "Q", "\x03") and M.S.get("cal_mode") != "add":
                    return "__shell__"                                 # q → Terminal normal
                elif M.key(ch):                                        # alta del calendario: al buffer
                    pass
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
    if not sys.stdin.isatty():
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
            elif ch in ("\r", "\n"):
                act = True
            elif ch == " " and M.S.get("cal_mode") != "add":
                M.space()                                          # espacio → cicla pin en CONFIGS (no-op fuera)
            elif ch and ch.lower() in M.akeys_set \
                    and M.S.get("cal_mode") != "add":
                M.quick(ch.lower())                                # acción rápida: motor/info del apuntado (keybinds)
            elif ch in M.jump_set and M.S.get("cal_mode") != "add":
                res = M.jump(ch)                                   # salto directo (tecla visible junto al ítem)
                if res is not None:
                    return res
            elif ch in ("l", "L") and M.S.get("cal_mode") != "add":
                M.toggle_redlight()                               # `l` → luz roja (modo noche) on/off EN VIVO
            elif ch in ("q", "Q", "\x03") and M.S.get("cal_mode") != "add":
                return "__shell__"                                 # q → Terminal normal
            elif M.key(ch):                                        # alta del calendario: al buffer
                pass
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
    if not sys.stdin.isatty():
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


def animated_menu(it, rows):
    """Recinto de los dioses: wordmark + caja de info + menús de selección.
    Orden: DIOSES (altar de urnas, ◄►, fuego por color), HERRAMIENTAS
    (Dashboard / Doctor / Actualizar / Terminal, ◄►, barrido luminoso),
    LATIDO (radio-group auto/manual/off de la cola — ◄► mueve el foco,
    Enter aplica; solo aparece si heartbeat existe). ↑↓ cambia de menú.
    Enter elige. Devuelve nombre/token o None.
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
            return {"ok": False, "reason": "no es repo git (instalación por sync)"}
        rc, remotes, _ = _git(ROOT, "remote", timeout=8)
        if rc != 0 or not remotes:
            return {"ok": False, "reason": "sin remote configurado"}
        rc, branch, _ = _git(ROOT, "rev-parse", "--abbrev-ref", "HEAD", timeout=8)
        if rc != 0 or not branch or branch == "HEAD":
            return {"ok": False, "reason": "rama no determinable (HEAD suelto)"}
        # fetch SOLO esa rama (no bloquea el resto si falla)
        rc, _, err = _git(ROOT, "fetch", "--quiet", "origin", branch, timeout=timeout)
        if rc != 0:
            low = (err or "").lower()
            if any(k in low for k in ("could not resolve", "unable to access",
                                      "timeout", "connection", "offline")):
                return {"ok": False, "reason": "sin conexión con origin (¿offline?)"}
            return {"ok": False, "reason": "no se pudo verificar updates"}
        rc, cnt, _ = _git(ROOT, "rev-list", "--count", "HEAD..origin/%s" % branch, timeout=8)
        if rc != 0:
            return {"ok": False, "reason": "no se pudo comparar con origin"}
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
        return {"ok": False, "reason": "git no está instalado"}
    except Exception as e:
        return {"ok": False, "reason": "%s" % e}


def _offer_update(interactive):
    """Tras las fases del doctor: chequea update y (si hay y es interactivo) lo
    ofrece. NO bloquea: si no se puede verificar, avisa suave y sigue. En NO
    interactivo (CI/instalación) NUNCA promptea — a lo mucho reporta que hay update.
    Devuelve el rc de cmd_update si se ejecutó, o None si no se actualizó."""
    print(f"\n{DIM}  Buscando actualizaciones del harness…{R}")
    info = _update_available()
    if not info.get("ok"):
        print(f"  {DIM}· no se pudo verificar updates ({info.get('reason','?')}) — sin problema, sigues como estás.{R}")
        return None
    if info["behind"] <= 0:
        print(f"  {C}·{R} {DIM}estás al día (rama {info['branch']}).{R}")
        return None

    n = info["behind"]
    print(f"  {B}↓ hay {n} actualización{'es' if n != 1 else ''} disponible{'s' if n != 1 else ''}{R} "
          f"{DIM}(rama {info['branch']}):{R}")
    for sha, subj in info["commits"][:12]:
        print(f"      {C}{sha}{R}  {subj}")
    if n > len(info["commits"][:12]):
        print(f"      {DIM}… y {n - 12} más{R}")

    if not interactive:
        # CI / instalación / pipe: NUNCA promptear. Solo informar.
        print(f"  {DIM}· corre `workspace update` para aplicarla.{R}")
        return None

    try:
        ans = input(f"\n  {C}¿Actualizar ahora? [s/N]{R} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    if ans not in ("s", "si", "sí", "y", "yes"):
        print(f"  {DIM}· ok, no actualizo. Cuando quieras: `workspace update`.{R}")
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
    puede correrlo ahí (p. ej. reparar necesitaría preguntar «¿quién eres?»):
    entonces AQUÍ se rutea al camino clásico de terminal (cmd_doctor/
    cmd_update — el engine interno sigue llamándose doctor), que sí promptea.
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
        print(f"\n  {B}Actualizaciones{R} {DIM}— ¿qué quieres hacer?{R}\n")
        print(f"    {C}1{R}  Revisar nomás      {DIM}— diagnóstico, no toca nada{R}")
        print(f"    {C}2{R}  Revisar y reparar  {DIM}— arregla hooks, launchers, tema…{R}")
        print(f"    {C}3{R}  Actualizar todo    {DIM}— trae lo nuevo + repara (recomendado){R}")
        print(f"    {C}q{R}  Volver\n")
        try:
            ans = input(f"  {C}Opción [1]:{R} ").strip().lower()
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
    # update-offer: solo fuera del flujo de `workspace update` (anti-recursión).
    if not from_update:
        try:
            _offer_update(interactive=sys.stdin.isatty() and sys.stdout.isatty())
        except Exception as e:
            # fail-open absoluto: el doctor JAMÁS se rompe por el chequeo de update.
            print(f"  {DIM}· chequeo de update omitido ({type(e).__name__}).{R}")
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
    try:
        ctx = doctor.build_ctx()
    except Exception as e:
        print(f"  {B}⚠{R} {DIM}no pude leer el registry de agentes "
              f"({type(e).__name__}: {e}) — corre `workspace doctor`{R}")
        return 0
    brains = doctor._resolved_brains(ctx)
    if not brains:
        print(f"  {DIM}No hay cerebros resueltos que recablear. "
              f"Corre `workspace doctor` para resolverlos.{R}")
        return 0
    done, failed = [], []
    for a in ctx["agents"]:
        name, brain = a["name"], a["brain"]
        if not (brain and os.path.isdir(brain)):
            continue
        try:
            install.render_hooks_only(a["cfg"], brain)        # RMW de hooks (fuente única P0-3)
            install.ensure_gitignore(brain, install.GITIGNORE_LINES)
            done.append(name)
        except Exception as e:
            failed.append(f"{name} ({type(e).__name__})")
    print(f"  {C}WORKSPACE repair{R} {DIM}— hooks recableados (settings.local.json){R}")
    line = f"  {C}✓{R} {len(done)} cerebro(s): {', '.join(done) or '—'}"
    if failed:
        line += f"   {B}⚠{R} {len(failed)} con error: {', '.join(failed)}"
    print(line)
    return 0


def cmd_release(args):
    """`workspace release [mensaje] [--ref REF] [--dist RUTA] [--dry-run]` — corta y
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

    print(f"  {B}Construyendo distro desde `{ref}` ({sha})…{R}")
    env = dict(os.environ, DIR=dist)
    print(f"  {DIM}$ DIR={dist} bash make-dist.sh {ref}{R}")
    if not dry and subprocess.call(["bash", script, ref], env=env):
        print("WORKSPACE: make-dist falló (¿el gate anti-fuga? revisa arriba)."); return 1
    run(["git", "-C", dist, "add", "-A"])
    if dry:
        print(f"  {DIM}$ git -C {dist} commit -m 'release {sha}'{R}")
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
                              f"release {sha}"]) != 0:
            print(f"\n  ✗ El commit del distro FALLÓ (identidad git / hook); "
                  f"no publico un release a medias.")
            return 1
    rc = run(["git", "-C", dist, "push"])
    if dry:
        print(f"\n  {DIM}(dry-run: no se ejecutó nada){R}")
    elif rc == 0:
        print(f"\n  {C}✓ Distribución publicada{R} (release {sha}). "
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
        print("WORKSPACE: no encuentro uninstall.py en el harness.")
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
        print("WORKSPACE: no pude cargar el bus automático (bus_daemon.py): %s" % e)
        return 1
    return bus_daemon.main(args)


def cmd_calendario(args):
    """`workspace calendario` - pantalla completa para EDITAR la agenda: mes
    navegable, eventos del dia, alta/edicion/baja con una tecla. El hub deja
    agregar con Enter; esto es para todo lo demas. Logica: calendario_tui."""
    try:
        import calendario_tui
    except Exception as e:
        print("WORKSPACE: no pude cargar calendario_tui.py: %s" % e)
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
        print("WORKSPACE: no pude cargar personalidad.py: %s" % e)
        return 1
    return personalidad.main(args)


def cmd_personal(kind, args):
    """`workspace foco [texto|--clear]` y `workspace agenda [add|rm|list]` — el
    dato PERSONAL del socio (foco del día + agenda) que pinta la caja HOY del
    layout `dia`. Store local per-máquina: ~/.claude/workspace/personal.json
    (no se sincroniza, no lo ve nadie más). La lógica vive en personal.py."""
    try:
        import personal
    except Exception as e:
        print("WORKSPACE: no pude cargar personal.py: %s" % e)
        return 1
    return personal.main([kind] + list(args))


def cmd_voice(args):
    """`workspace voice` — dictado por voz GLOBAL, local (whisper.cpp). TOGGLE:
    1er toque graba el micro; 2º transcribe y PEGA en el cursor. `--check`
    reporta qué falta. Se enlaza a un atajo de teclado (Atajos de macOS)."""
    try:
        import voice
    except Exception as e:
        print("WORKSPACE: no pude cargar la voz (voice.py): %s" % e)
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
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace", "mail.json")


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
            f"{B}✗ Faltan credenciales SMTP.{R}\n"
            f"  {DIM}El correo sale por SMTP de Gmail con una App Password "
            f"(2FA activado), NO tu contraseña normal.{R}\n"
            f"  {DIM}Crea una en: https://myaccount.google.com/apppasswords{R}\n\n"
            f"  Configúralas de UNA de estas formas:\n"
            f"    1) {C}workspace mail --setup{R}  {DIM}(te las pide y crea "
            f"~/.claude/workspace/mail.json con permisos 0600){R}\n"
            f"    2) variables de entorno {C}WORKSPACE_SMTP_USER{R} y "
            f"{C}WORKSPACE_SMTP_PASS{R}\n"
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
    print(f"{B}WORKSPACE · configurar correo (SMTP){R}")
    print(f"  {DIM}Necesitas una App Password de Google (con 2FA activado), "
          f"no tu contraseña normal.{R}")
    print(f"  {DIM}Crear: https://myaccount.google.com/apppasswords{R}\n")
    try:
        # Solo se piden interactivamente los campos REQUERIDOS (user + pass);
        # host/port toman default Gmail salvo que se pasen por flag. Así
        # `workspace mail --setup --user X --pass Y` es no-interactivo.
        if not user:
            user = input("  Correo (user) [ej. tucorreo@dominio.com]: ").strip()
        if not passwd:
            import getpass
            passwd = getpass.getpass("  App Password (16 chars, no se muestra): ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\n  cancelado.")
        return 1
    host = host or "smtp.gmail.com"
    port = port or 587
    if not user or not passwd:
        print(f"  {B}✗ Falta el correo o la App Password — no escribí nada.{R}")
        return 2
    path = _mail_save_creds(user, passwd, host or "smtp.gmail.com", port or 587)
    print(f"\n  {C}✓ Guardado en {path}{R} {DIM}(permisos 0600, per-máquina, "
          f"fuera de git){R}")
    print(f"  {DIM}Prueba: workspace mail --to {user} --subject ping "
          f"--body hola --dry-run{R}")
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
                f"{B}✗ Autenticación rechazada por el servidor.{R}\n"
                f"  {DIM}¿Es una App Password válida (2FA activado), no tu "
                f"contraseña normal? Regenera en "
                f"https://myaccount.google.com/apppasswords{R}\n"
                f"  {DIM}({type(e).__name__}){R}")
        server.sendmail(sender, recipients, msg.as_string())
    except smtplib.SMTPException as e:
        return False, (f"{B}✗ Error enviando el correo{R} "
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


def cmd_mail(args):
    """`workspace mail` — envía correo por SMTP de Gmail (App Password, sin OAuth).

    Default seguro: usa --dry-run para previsualizar antes de mandar. Las
    credenciales viven SOLO per-máquina (env o ~/.claude/workspace/mail.json)."""
    args = list(args or [])
    if "--help" in args or "-h" in args:
        print(_MAIL_USAGE)
        return 0

    # ── parseo manual (controla return codes; consistente con el resto) ──
    to_vals, subject, body, body_file, sender = [], None, None, None, None
    user_flag, pass_flag, host_flag, port_flag = None, None, None, None
    dry = setup = False
    i = 0

    def _val(i, flag):
        if i + 1 >= len(args):
            raise ValueError(f"{flag} requiere un valor")
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
                print(f"WORKSPACE: opción desconocida '{a}'\n")
                print(_MAIL_USAGE)
                return 2
    except ValueError as e:
        print(f"WORKSPACE: {e}\n")
        print(_MAIL_USAGE)
        return 2

    if setup:
        return _mail_setup(user_flag, pass_flag, host_flag, port_flag)

    # ── cuerpo: --body directo o --body-file ──
    if body is not None and body_file is not None:
        print("WORKSPACE: usa --body O --body-file, no ambos.")
        return 2
    if body_file is not None:
        try:
            with open(os.path.expanduser(body_file), encoding="utf-8") as fh:
                body = fh.read()
        except OSError as e:
            print(f"WORKSPACE: no pude leer --body-file '{body_file}' "
                  f"({type(e).__name__}: {e})")
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
        print(f"WORKSPACE: faltan {', '.join(missing)}\n")
        print(_MAIL_USAGE)
        return 2

    # ── credenciales (también define el remitente por default) ──
    creds, err = _mail_load_creds()
    if err:
        print(err)
        return 1
    sender = sender or creds["user"]

    # ── preview (siempre) ──
    preview = body if len(body) <= 500 else body[:500] + "…"
    print(f"{B}── correo ──{R}")
    print(f"  {DIM}de:     {R}{sender}")
    print(f"  {DIM}para:   {R}{', '.join(recipients)}")
    print(f"  {DIM}asunto: {R}{subject}")
    print(f"  {DIM}cuerpo:{R}")
    for line in (preview.splitlines() or [""]):
        print(f"    {line}")

    if dry:
        print(f"\n  {DIM}(dry-run: no se envió nada){R}")
        return 0

    ok, send_err = _mail_send(creds, sender, recipients, subject, body)
    if not ok:
        print("\n" + send_err)
        return 1
    print(f"\n  {C}✓ Enviado a {', '.join(recipients)}{R}")
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
        verbo = "reapear" if plan else "reapeadas"
        print("WORKSPACE split reap: %d sesión(es) %s · %d grupo(s) huérfano(s) %s"
              % (len(reaped), verbo, killed, "por matar" if plan else "matados"))
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


def _usage():
    """Uso CLI de `workspace` (sin abrir la TUI). Un renglón por comando.
    Los comandos de DEV/EQUIPO (flujo de ramas, release, dev panel, paridad) solo
    se listan en una build de DEV (_has_dev_panel); el cliente ve solo producto."""
    product = (
        "uso: workspace [comando]\n"
        "\n"
        "  (sin comando)       abre el recinto (menú interactivo de agentes)\n"
        "  doctor [--check]    diagnóstico / reparación del harness\n"
        "  update              actualiza el harness (pull + doctor)\n"
        "  repair              re-renderiza los hooks de cada cerebro\n"
        "  proyectos [stop]    app «Proyectos»: mapa de todos tus proyectos + agente\n"
        "  eval <agente>       corre el golden set del agente\n"
        "  wf                  workflows declarativos (new · list · run · status · resume · stats)\n"
        "  split [agente]      terminal partida (tmux o herdr): chat | wf board (opt-in;\n"
        "                      para TODO chat del hub: settings set ui.split on;\n"
        "                      backend: settings set ui.split_backend auto|tmux|herdr)\n"
        "  foco [texto]        el foco del día (lo pinta la caja HOY del layout dia)\n"
        "  agenda [add|rm]     tu agenda local (eventos con fecha/hora)\n"
        "  tono                pantalla del TONO de los agentes (diales 1-5)\n"
        "  onboarding          flujo guiado de primer uso (motores · apariencia · agente)\n"
        "  calendario          editor de agenda (mes + alta/edicion/baja)\n"
        "  mail                enviar correo (SMTP per-máquina; default --dry-run)\n"
        "  uninstall           desinstala WORKSPACE de esta máquina\n")
    dev = (
        "  dev                 panel de developer (versiones / ramas)\n"
        "  board               tablero del dev panel (agentes-first)\n"
        "  feature | integrate | promote | release | publish   flujo de ramas\n"
        "  worktree | wt       worktrees con dueño (list · rm · pool · prune)\n"
        "  parity-check        checklist de paridad Mac/Windows\n")
    meta = (
        "  --banner            imprime banner + menú estático (no interactivo)\n"
        "  -h, --help          este uso\n")
    return product + (dev if _has_dev_panel() else "") + meta


def _tty_out():
    """Stream del fallback estático del menú: /dev/tty si es ABRIBLE — existir
    no basta: en cron/headless `open()` truena con OSError (Errno 6, device not
    configured) aunque el nodo exista. Falla-suave → stderr."""
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
    if len(sys.argv) > 1 and sys.argv[1] in ("-h", "--help", "help", "ayuda"):
        print(_usage())
        sys.exit(0)
    # ── Build de CLIENTE: gate de la superficie DEV/EQUIPO ──
    # Los comandos de _DEV_CMDS (flujo de ramas, release/publish, dev panel,
    # tablero, paridad) dependen de archivos que NO viajan a la distro (p.ej.
    # cmd_dev busca dashboard-dev.html) → en una build sin dev panel tronarían.
    # Si un cliente los invoca: mensaje limpio + salida ≠0, NUNCA un traceback.
    # En build de DEV (_has_dev_panel) pasan tal cual, sin cambio de conducta.
    if (len(sys.argv) > 1 and sys.argv[1] in _DEV_CMDS and not _has_dev_panel()):
        sys.stderr.write(
            f"WORKSPACE: '{sys.argv[1]}' es un comando de desarrollo, "
            f"no disponible en esta instalación.\n\n" + _usage())
        sys.exit(2)
    if len(sys.argv) > 1 and sys.argv[1] in ("parity-check", "parity", "paridad"):
        sys.exit(cmd_parity_check(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] in ("update", "--update", "up"):
        sys.exit(cmd_update(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] in ("versiones", "ramas"):
        import git_tui
        sys.exit(git_tui.run())
    if len(sys.argv) > 1 and sys.argv[1] == "dev":
        sys.exit(cmd_dev(sys.argv[2:]))
    # App «Proyectos» (pantalla completa, puerto propio) — la abre el hub o esto.
    if len(sys.argv) > 1 and sys.argv[1] in ("proyectos", "proyecto", "mapa"):
        sys.exit(cmd_proyectos(sys.argv[2:]))
    # API de terminal del tablero del dev panel (agentes-first). Solo-dev.
    if len(sys.argv) > 1 and sys.argv[1] in ("board", "tablero"):
        sys.exit(cmd_board(sys.argv[2:]))
    # Backend del Centro de Control: misiones (3 fases) + estado agregado +
    # delegación estructurada por el bus. La lógica vive en dash/centro/.
    if len(sys.argv) > 1 and sys.argv[1] == "centro":
        sys.exit(cmd_centro(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] in ("doctor", "--doctor", "doc"):
        sys.exit(cmd_doctor(sys.argv[2:]))
    # `repair`/`fix`: subset rápido del doctor — re-renderiza SOLO los hooks de
    # cada cerebro (cierra la deriva de un pull/branch-switch). El auto-render
    # tras un pull con cambios (dispatch.maybe_autoupdate) spawnea justo esto.
    if len(sys.argv) > 1 and sys.argv[1] in ("repair", "fix"):
        sys.exit(cmd_repair(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] in ("eval", "evals"):
        sys.exit(cmd_eval(sys.argv[2:]))
    # Dictado por voz global (local, whisper.cpp): toggle grabar→transcribir→pegar.
    # Se enlaza a un atajo de teclado del sistema; cubre todos los chats de agente.
    if len(sys.argv) > 1 and sys.argv[1] in ("voice", "voz", "dictado"):
        sys.exit(cmd_voice(sys.argv[2:]))
    # Delegación autónoma segura (bus automático v1): daemon que atiende el bus
    # solo para agentes opt-in, con enforcement por construcción (sandbox+read-only).
    if len(sys.argv) > 1 and sys.argv[1] in ("bus",):
        sys.exit(cmd_bus(sys.argv[2:]))
    # Dato PERSONAL del socio: el FOCO del día y la AGENDA que pinta la caja
    # HOY del layout `dia`. Local a esta máquina (personal.py).
    if len(sys.argv) > 1 and sys.argv[1] in ("foco", "focus"):
        sys.exit(cmd_personal("foco", sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "agenda":
        sys.exit(cmd_personal("agenda", sys.argv[2:]))
    # Niveles de personalidad de los agentes (tono.*) — ver personalidad.py.
    if len(sys.argv) > 1 and sys.argv[1] in ("tono", "personalidad"):
        sys.exit(cmd_tono(sys.argv[2:]))
    # Onboarding de primer uso, re-ejecutable a mano (onboarding_tui.py).
    if len(sys.argv) > 1 and sys.argv[1] in ("onboarding", "bienvenida"):
        try:
            import onboarding_tui
            sys.exit(onboarding_tui.run(force=True))
        except Exception as e:
            print(f"onboarding no disponible ({type(e).__name__}: {e})")
            sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] in ("calendario", "cal"):
        sys.exit(cmd_calendario(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] in ("uninstall", "--uninstall", "remove"):
        sys.exit(cmd_uninstall(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "release":
        sys.exit(cmd_release(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "publish":
        sys.exit(cmd_publish(sys.argv[2:]))
    # Enviar correo por SMTP (Gmail App Password). Acción HACIA AFUERA: el
    # default seguro es --dry-run; las credenciales viven per-máquina.
    if len(sys.argv) > 1 and sys.argv[1] == "mail":
        sys.exit(cmd_mail(sys.argv[2:]))
    # Flujo de ramas (feature → main → stable): le ahorra tecleo al socio e imprime
    # cada git que corre (para que vea el git real mientras lo aprende).
    if len(sys.argv) > 1 and sys.argv[1] == "feature":
        sys.exit(cmd_feature(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "integrate":
        sys.exit(cmd_integrate(sys.argv[2:]))
    # Worktrees con DUEÑO: toma una rama en un worktree aparte y registra qué
    # agente la trabaja (el dashboard de DEV la marca "en uso").
    if len(sys.argv) > 1 and sys.argv[1] in ("worktree", "wt"):
        sys.exit(cmd_worktree(sys.argv[2:]))
    if len(sys.argv) > 1 and sys.argv[1] == "promote":
        sys.exit(cmd_promote(sys.argv[2:]))
    # Workflows declarativos (workflows/MAPA.md): specs congelados + runner
    # con verify determinista por paso — hermano del flujo de ramas.
    if len(sys.argv) > 1 and sys.argv[1] in ("wf", "workflow", "workflows"):
        sys.exit(cmd_wf(sys.argv[2:]))
    # Panel del pane derecho del split (ui.split_pane=panel): superficie con
    # menú (Pipeline / Bus / Config / Delegar) + identidad del agente. Vive en
    # panel.py; extensible en panel.VIEWS. Lo corre mux.right_pane_cmd().
    if len(sys.argv) > 1 and sys.argv[1] in ("panel", "menu"):
        sys.exit(cmd_panel(sys.argv[2:]))
    # Terminal PARTIDA (opt-in): chat + pipeline en vivo en una ventana tmux.
    # NO toca el arranque default — solo se entra escribiendo `workspace split`.
    if len(sys.argv) > 1 and sys.argv[1] == "split":
        sys.exit(cmd_split(sys.argv[2:]))
    # ── CLI hygiene: un subcomando DESCONOCIDO imprime uso y sale con 2 — NUNCA
    #    cae a la TUI interactiva (un typo o un script headless no deben terminar
    #    dentro del recinto, y sin tty eso tronaba). `--banner` sí sigue al hub.
    if len(sys.argv) > 1 and sys.argv[1] != "--banner":
        sys.stderr.write(f"WORKSPACE: comando desconocido '{sys.argv[1]}'\n\n" + _usage())
        sys.exit(2)
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
    # El harness arranca VACÍO de agentes: es un producto que se distribuye a clientes
    # y ellos conectan sus PROPIOS cerebros explícitamente ("Agregar agente → cargar
    # ruta"). NO auto-descubrimos cerebros del disco al bootear (eso metía un agente
    # sin que el usuario lo pidiera). El descubrimiento sigue disponible como acción
    # MANUAL (menú Agregar agente → Descubrir, o `agentsreg.py discover`).
    import theme
    _osc = getattr(TH, "OSC", None) if TH else None
    if _osc:
        theme.apply_colors(_osc)                  # tema no-default: SU fondo/tinta (tui.osc)
    else:
        theme.apply("workspace")                    # olympo: el recinto dorado de siempre
    _set_term_title("WORKSPACE")                  # la pestaña dice WORKSPACE, no el proceso
    # Aviso si la ventana es muy angosta: el hub (altar/banner) se dibuja a ~content_w
    # columnas; en una terminal más chica el arte se envuelve y "se rompe". La app de
    # escritorio ya abre la Terminal dimensionada; esto cubre el lanzamiento manual.
    try:
        _cols = os.get_terminal_size().columns
        if _cols < render.W + 4:
            sys.stderr.write(
                f"\n  {B2}"
                + _t("hub.narrow.too_small",
                     "⚠ Tu terminal mide {cols} columnas; el hub necesita "
                     "≥{need}.", cols=_cols, need=render.W + 4)
                + f"{R} "
                + _t("hub.narrow.too_small2",
                     "Agranda o maximiza la ventana para que el diseño no se "
                     "rompa.") + "\n")
    except Exception:
        pass
    it = items()
    rows = build_info_rows()
    if "--banner" in sys.argv:
        # LAYOUT alternativo activo (WORKSPACE_LAYOUT / ui.layout): el banner
        # estático ES el layout — así cada estructura se prueba sin tty
        # (`WORKSPACE_LAYOUT=hud python3 front.py --banner`). Con el default
        # `clasico` NO se entra aquí: el banner de siempre, byte-idéntico.
        _lay_on = False
        try:
            import hublayout as _hl_banner
            _lay_on = _hl_banner.active() is not None
        except Exception:
            _lay_on = False
        if _lay_on:
            try:
                print("\n".join(_menu_machinery(sys.stdout).block_lines()))
                return
            except Exception:
                pass                                 # falla-suave → banner clásico
        print(render.banner_str(rows))
        hb = _heartbeat_line()
        if hb:
            print("\n" + _ctr(hb))
        print("\n" + _menu_header() + "\n")
        # Vista ESTÁTICA del menú interactivo (mismas secciones y orden que el
        # recinto animado: DIOSES → HERRAMIENTAS → LATIDO) — para pruebas.
        # Falla-suave: si la machinery truena, cae a la lista plana del picker.
        try:
            print("\n".join(_menu_machinery(sys.stdout).block_lines()))
        except Exception:
            w = max(len(d) for _, d, _, _ in it) + 2
            for i, (nm, disp, tag, sel) in enumerate(it):
                print(_row(disp, tag, i == _first_selectable(it), sel, w))
        print()
        return
    while True:
        name = animated_menu(it, rows)            # altar de urnas (devuelve nombre/token)
        if name is None:                          # fallback: sin tty / Windows / WORKSPACE_NO_ANIM
            t = _tty_out()                        # /dev/tty ABRIBLE o stderr (headless no truena)
            hb = _heartbeat_line()
            t.write(render.banner_str(rows) + ("\n\n" + _ctr(hb) if hb else "")
                    + "\n\n" + _menu_header() + "\n\n"); t.flush()
            name = it[run_picker(it)][0]
        sys.stdout.write("\033[2J\033[3J\033[H"); sys.stdout.flush()   # limpia menú + scrollback al salir
        # Acciones que REGRESAN al recinto tras ejecutarse (pantalla TUI propia).
        # Falla-suave: si el módulo no está o truena, un aviso y el menú sigue
        # vivo (jamás crashea el boot). El recinto se reconstruye al re-entrar
        # al loop → relee el registry (un agente recién agregado ya aparece).
        loopback = {"__config__": ("config", "config_tui"),
                    "__ramas__": ("github", "github_tui"),
                    "__devmap__": ("dev", "dev_tui"),
                    "__keybinds__": ("atajos", "keybinds_tui"),
                    "__add_agent__": ("agregar agente", "add_agent_tui"),
                    "__agentes__": ("agentes", "agents_tui")}
        if name not in loopback:
            break
        label, modname = loopback[name]
        try:
            __import__(modname).run()
        except Exception as e:
            print(f"{DIM}{label} no disponible ({type(e).__name__}: {e}) — "
                  f"el menú sigue normal{R}")
    if name == "__dev__":                         # abrir el panel de DEV (versiones/ramas) y al shell
        theme.reset(); cmd_dev([]); return
    if name == "__proyectos__":                   # abrir la app «Proyectos» y al shell
        theme.reset(); cmd_proyectos([]); return
    if name == "__cal__":                         # editor de calendario
        theme.reset(); cmd_calendario([]); return
    if name == "__tono__":                        # pantalla del TONO de los agentes
        theme.reset(); cmd_tono([]); return
    if name == "__doctor__":                      # submenú: el socio ELIGE qué hacer
        theme.reset(); _doctor_submenu(); return
    if name == "__shell__":                       # "Terminal normal" / q → salir al shell
        theme.reset(); return                     # restaura colores por defecto en el shell
    launch(name)                                  # launch() limpia y lanza el agente (aplica SU tema)


if __name__ == "__main__":
    main()
