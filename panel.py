#!/usr/bin/env python3
"""El PANEL del pane derecho de la terminal partida — superficie extensible.

Reemplaza (opt-in por `ui.split_pane=panel`) al board pelón del pane derecho
por un panel con MENÚ de vistas y un header de identidad del agente. Las
vistas viven en un REGISTRO (`VIEWS`): agregar una es añadir un dict con su
`render(ctx, w, h) -> [str]` (+ opcionales `on_key`/`on_click`/`hint`). Hoy:
Sesiones (las sesiones del agente + switch del pane izquierdo) · Workflows
(el wf board en vivo) · Bus (el inbox del agente) · Config (settings clave) ·
Delegar (cómo mandar tareas).

Cableado:
  • el pane derecho corre `python3 front.py panel --agent <name>` (mux.right_pane_cmd
    lo elige cuando ui.split_pane=panel). front.cmd_panel() → panel.run().
  • navegación: con el pane ENFOCADO (prefix+→ en herdr), teclas 1-9 / ←→ / Tab
    cambian de vista; el header lo dice. Sin foco, el panel sigue vivo mostrando
    la vista activa (la Pipeline se refresca sola).

Anti-parpadeo (mismo patrón que el board): repinta EN SITIO (cursor-arriba, sin
`clear`) y SOLO si el frame cambió → en idle no repinta. Sin TTY (pipe/CI) →
render único de la vista activa y sale.

Falla-suave ABSOLUTA: cualquier vista que reviente cae a un aviso de una línea;
el panel jamás tumba el pane. Identidad/bus se resuelven best-effort.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def fg(n):
    return "\033[38;5;%dm" % n


R = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"

# ── Paleta de ROLES (diseño de Iris, tema olympo) — cada índice 256 tiene UN
#    trabajo; nunca se mezclan. La regla de oro de coherencia del panel:
#    ACCENT = "dónde estoy" · HI = "qué importa AHORA" · OK/ERR = "cómo salió".
#    La identidad del agente (violet de Iris, dorado de Zenith…) va aparte, la
#    trae ctx.ident.col — se usa SOLO para el nombre y el marcador ▸ de "actual".
ACCENT = fg(214)       # título de vista · subrayado de la tab activa · firma ✦
HI = fg(221)           # dato que importa ahora (paso actual, sesión actual, n/total)
TEXT = fg(230)         # texto normal (nombres de pasos/sesiones/mensajes)
MID = fg(178)          # metadatos secundarios (versión, tipo, sub-encabezados)
FAINT = fg(136)        # tenue (timestamps, contadores, sub-líneas de detalle)
RULE = fg(94)          # separadores ─── · rieles inactivos ┈ · bordes de caja
GREY = fg(242)         # inactivos: tabs/opciones apagadas, deshabilitado
OK = fg(108)           # ✓ completado / hecho
ERR = fg(196)          # ✗ falló
BAD = fg(174)          # ⊗ rechazado · avisos no-fatales · modo destructivo

# Alias de compat (código viejo del panel aún los referencia). Apuntan a los
# roles nuevos para que TODO el panel hable la misma paleta.
SEP = RULE             # separadores/inactivos → dark 94
LBL = MID              # etiquetas → mid 178
VAL = TEXT             # valores → text 230
WARN = MID             # avisos suaves → mid 178
ACC = ACCENT           # acento por defecto (lo pisa el color del agente)


def _apply_theme():
    """Resuelve la paleta del TEMA activo (setting ui.theme: olympo · cyberpunk
    · …) y la aplica a los roles de color del panel. Antes estaban hardcodeados
    en olympo (dorado) → el panel salía dorado aunque el socio tuviera otro tema
    (bug que notó el socio con cyberpunk). Los roles mapean 1:1 a tuitheme.palette()
    (B=accent, C=hi, WH=text, B2=mid, DIM=dim, DK=dark, GREY, OK, ERR, BAD).
    tuitheme MEMOIZA por (tema, modo-color) → barato por-frame. Falla-suave
    ABSOLUTA: sin tuitheme quedan los defaults olympo de arriba. La identidad
    del agente (violet de Iris…) es aparte — NO la pisa el tema."""
    global ACCENT, HI, TEXT, MID, FAINT, RULE, GREY, OK, ERR, BAD
    global SEP, LBL, VAL, WARN, ACC
    try:
        import tuitheme
        TH = tuitheme.palette()
        ACCENT, HI, TEXT, MID = TH.B, TH.C, TH.WH, TH.B2
        FAINT, RULE, GREY = TH.DIM, TH.DK, TH.GREY
        OK, ERR, BAD = TH.OK, TH.ERR, TH.BAD
        SEP, LBL, VAL, WARN, ACC = RULE, MID, TEXT, MID, ACCENT
    except Exception:
        pass


def _strip(s):
    import re
    return re.sub(r"\033\[[0-9;]*m", "", s)


def _safe(s):
    """Neutraliza inyección ANSI/OSC/cursor de strings de ARCHIVO (subjects del
    bus, from/to, identidad) antes de pintarlos. TODA secuencia peligrosa
    (OSC \\033]…, CSI \\033[…, clear, mover cursor) empieza con ESC \\x1b, así
    que quitar ESC + control chars (C0 + DEL) la desarma; el color lo pone el
    panel DESPUÉS de sanear. Colapsa whitespace; deja texto/acentos/emoji.
    Mismo espíritu que _note_txt del statusline (que ya trataba esto como
    amenaza — los msgs son archivos sync'd desde otros cerebros/máquinas)."""
    import re
    s = re.sub(r"[\x00-\x1f\x7f]", "", str(s or ""))   # incl. \x1b, \n, \t
    return re.sub(r"\s+", " ", s).strip()


def _vw(s):
    """Ancho visual (sin ANSI; CJK/emoji = 2). Falla-suave."""
    import unicodedata
    s = _strip(s)
    w = 0
    for ch in s:
        if unicodedata.combining(ch):
            continue
        w += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return w


def _clip(s, w):
    """Recorta a `w` cols visibles con … (respeta ANSI a lo bruto: mide sin
    color pero corta por caracteres — suficiente para líneas de datos)."""
    if _vw(s) <= w:
        return s
    import re
    parts = re.split(r"(\033\[[0-9;]*m)", s)
    out, used = [], 0
    for p in parts:
        if p.startswith("\033["):
            out.append(p)
            continue
        for ch in p:
            cw = _vw(ch)
            if used + cw > w - 1:
                return "".join(out) + "…" + R
            out.append(ch)
            used += cw
    return "".join(out)


# ═══════════════════════════════════════════════════════════════════════════
# Contexto: agente + cerebro (best-effort, nunca crashea)
# ═══════════════════════════════════════════════════════════════════════════
def _resolve_agent(argv):
    for i, a in enumerate(argv):
        if a == "--agent" and i + 1 < len(argv):
            return argv[i + 1].strip().lower()
    return (os.environ.get("WORKSPACE_AGENT") or "").strip().lower() or None


def _resolve_wid(argv):
    """El `--wid` del argv (mismo patrón que _resolve_agent) — el workspace
    montado en el pane IZQUIERDO del split (mux.right_pane_cmd lo pasa ya
    saneado a [A-Za-z0-9-]). None si no viene."""
    for i, a in enumerate(argv or []):
        if a == "--wid" and i + 1 < len(argv):
            v = str(argv[i + 1]).strip()
            if v:
                return v
    return None


def _resolve_brain(agent):
    # PRIORIDAD: el --agent EXPLÍCITO manda → su cerebro del registry. Antes se
    # usaba WORKSPACE_BRAIN del entorno primero, pero ese lo hereda el pane del
    # agente ambiente (p. ej. el pane derecho arranca con WORKSPACE_BRAIN de otro)
    # → `panel --agent turing` mostraba la identidad equivocada. El env es solo
    # fallback cuando no hay --agent (correr `workspace panel` suelto).
    if agent:
        try:
            import dispatch
            reg = dispatch.load_registry() if hasattr(dispatch, "load_registry") else {}
            # el registry es {version, agents:[{name, brain}, …], planned} —
            # los agentes son una LISTA, no un dict top-level
            ags = reg.get("agents", []) if isinstance(reg, dict) else []
            for a in ags:
                if isinstance(a, dict) and (a.get("name") or "").lower() == agent:
                    p = a.get("brain") or a.get("path")
                    if p:
                        return os.path.abspath(os.path.expanduser(p))
        except Exception:
            pass
    b = os.environ.get("WORKSPACE_BRAIN")
    if b and b.strip():
        return os.path.abspath(os.path.expanduser(b.strip()))
    return None


def _identity(agent, brain):
    """{display, emoji, color(256), tagline} — best-effort."""
    ident = {"display": (agent or "agente").capitalize(), "emoji": "",
             "tagline": "", "col": ACC}
    try:
        import agent_brand
        ii = agent_brand.resolve_identity(brain)
        pal = agent_brand.palette(brain)
        # saneo anti-inyección: display/emoji/tagline vienen de archivos del
        # cerebro (agent.json / BOOT/01-IDENTITY.md) → _safe antes de pintar
        ident["display"] = _safe(ii.get("display")) or ident["display"]
        ident["emoji"] = _safe(ii.get("emoji"))
        ident["tagline"] = _safe(ii.get("tagline"))
        # color 256 del agente desde su paleta (cae al acento si no)
        c = None
        for k in ("C", "accent", "primary"):
            c = getattr(pal, k, None) if pal is not None else None
            if c:
                break
        if isinstance(c, str) and c.startswith("\033"):
            ident["col"] = c
    except Exception:
        pass
    return ident


def _banner_script(agent, brain):
    """Ruta al script de banner del agente (para el emblema). 1º agent.json del
    cerebro (scripts.banner, tokens {root}/{brain}); 2º convención. None si no
    hay. Best-effort."""
    try:
        if brain:
            import json
            aj = os.path.join(brain, ".workspace", "agent.json")
            if os.path.isfile(aj):
                b = ((json.load(open(aj, encoding="utf-8")).get("scripts")
                      or {}).get("banner") or "")
                if b:
                    p = os.path.normpath(b.replace("{root}", ROOT)
                                         .replace("{brain}", brain))
                    if os.path.isfile(p):
                        return p
    except Exception:
        pass
    p = os.path.join(ROOT, "agents", agent or "", "brand",
                     "%s-banner.py" % (agent or ""))
    return p if (agent and os.path.isfile(p)) else None


def _emblem_lines(agent, brain, w):
    """Emblema compacto del agente para el header (best-effort). Corre el banner
    del agente con `--emblem`; ACOTA la salida a ≤10 filas (un banner completo
    ~28 filas → se descarta: así un script sin soporte --emblem no ensucia el
    header). Vacío ante cualquier fallo."""
    if not agent:
        return []
    script = _banner_script(agent, brain)
    if not script:
        return []
    try:
        import subprocess
        py = sys.executable or "python3"
        cols = max(12, min(24, int(w) - 4))            # emblema chico de header
        r = subprocess.run([py, script, "--emblem", "--width", str(cols)],
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=6,
                           env=dict(os.environ, WORKSPACE_BRAIN=(brain or "")))
        if r.returncode != 0:
            return []
        lines = [ln for ln in (r.stdout or "").splitlines() if ln.strip()]
        return lines if 0 < len(lines) <= 8 else []    # cap anti-banner-completo
    except Exception:
        return []


class Ctx:
    def __init__(self, agent, brain, ident, emblem=None):
        self.agent = agent
        self.brain = brain
        self.ident = ident
        self.emblem = emblem or []
        # ── estado vivo del panel (rediseño split) ──
        self.current_wid = None      # wid montado en el pane izquierdo (--wid)
        self.current_ws = None       # nombre resuelto por wid (display)
        self.notice = ""             # línea de estado del footer (_safe al pintar)
        self.close_mode = False      # modo-cerrar armado (tecla x)
        self.cache_sesiones = None   # (ts, data) — cache TTL de _sessions_data
        self.hits_rel = {}           # hit-map RELATIVO del body (lo escribe la vista)
        self.hits = {}               # hit-map ABSOLUTO del frame (lo traduce render)
        self.pending_switch = None   # (wid, name) — el loop lo ejecuta
        self.pending_new = None      # True → el loop crea una sesión nueva


# ═══════════════════════════════════════════════════════════════════════════
# VISTAS — registro. Cada render(ctx, w, h) devuelve [str] (líneas ya-coloreadas).
# Agregar una vista = un dict más en VIEWS. Falla-suave por vista.
# ═══════════════════════════════════════════════════════════════════════════
LM = " "                                   # margen izq global (1 col, diseño Iris)
_SPIN = "◐◓◑◒"                             # el paso corriendo RESPIRA (1 frame/s)


def _tick():
    """Frame de animación 0-3 por segundo de reloj. El panel repinta cada 1s →
    el spinner gira gratis. Falla-suave → 0 (sin animación, sigue legible)."""
    try:
        import time
        return int(time.time()) % 4
    except Exception:
        return 0


def _step_glyph(status, stub, is_current, tick=0):
    """(glifo, color) de UN paso — la LEYENDA ÚNICA de estados (misma en todas
    las vistas, diseño Iris §0.2). is_current = el paso donde el run está parado
    AHORA: respira en HI. PURA."""
    if status == "ok":
        return ("⊘", FAINT) if stub else ("✓", OK)   # stub = verde-no-real
    if status == "skipped":
        return "⊝", GREY
    if status == "fail":
        return "✗", ERR
    if status == "rejected":
        return "⊗", BAD
    if status == "waiting_human":
        return "⏸", MID
    if is_current:
        return _SPIN[tick % len(_SPIN)], HI          # corriendo AHORA
    return "○", GREY                                  # pendiente


def _wf_rel(iso, now=None):
    """'hace 5m' · 'hace 1h' · 'ayer' · '2d' desde un isoformat. PURA;
    dato raro → ''."""
    import datetime
    try:
        t = datetime.datetime.fromisoformat(str(iso))
    except (TypeError, ValueError):
        return ""
    now = now or datetime.datetime.now()
    s = (now - t).total_seconds()
    if s < 0:
        return ""
    if s < 90:
        return "hace %ds" % int(s)
    if s < 5400:
        return "hace %dm" % int(s / 60)
    if s < 86400:
        return "hace %dh" % int(s / 3600)
    if s < 172800:
        return "ayer"
    return "%dd" % int(s / 86400)


def _bar(done, total, width):
    """Barra de progreso: llenos █ [accent], vacíos ░ [dark]. PURA."""
    width = max(4, int(width))
    total = max(1, int(total))
    filled = max(0, min(width, round(done / total * width)))
    return (ACCENT + "█" * filled + R + RULE + "░" * (width - filled) + R)


def _wf_active_lines(state, w, h):
    """El RUN ACTIVO en grande (diseño Iris §B): identidad + barra + pipeline
    vertical con el paso actual en CAJA. Ventanea alrededor del paso actual si
    no caben todos. PURA salvo el reloj (spinner/elapsed)."""
    import front
    out = []
    inner = max(20, w - 2)                 # ancho útil (1 col margen c/lado)
    status = state.get("status", "?")
    steps = state.get("steps") or []
    done, total = front._wf_progress(state)
    tick = _tick()

    # ── cabecera de identidad del run ──
    name = str(state.get("workflow", "?"))
    ver = "v%s" % state.get("version", "?")
    dry = state.get("dry")
    drytag = (BAD + "dry: SÍ" + R) if dry else (FAINT + "dry: no" + R)
    left = TEXT + BOLD + _clip(name, inner - 14) + R + " " + MID + ver + R
    out.append(LM + left + _pad_right(_strip(left), inner, drytag))

    # ── barra de progreso + n/total + ⏱ ──
    elapsed = front._wf_run_elapsed(state)
    bar_w = max(8, inner - 21)                  # deja aire a "n / total  ⏱ …"
    meta = HI + BOLD + "%d / %d" % (done, total) + R
    if elapsed:
        meta += "   " + FAINT + "⏱ " + elapsed + R
    out.append(LM + _bar(done, total, bar_w) + "   " + meta)
    out.append("")

    if not steps:
        out.append(LM + FAINT + "sin pasos" + R)
        return out

    cur = state.get("current", -1)
    # índice del paso "protagonista": el current running/waiting, si no el 1er
    # no-terminal, si no el último (para runs done/failed muestra el desenlace)
    star = cur if 0 <= cur < len(steps) else next(
        (i for i, s in enumerate(steps)
         if s.get("status") in ("pending", "waiting_human")), len(steps) - 1)

    # presupuesto de filas: la caja cuesta 3, cada paso compacto 1 + riel 1.
    # ventana centrada en el protagonista (algunos hechos arriba, pendientes abajo).
    budget = max(6, h - 3)
    above = max(1, (budget - 4) // 2)
    lo = max(0, star - above)
    hi = min(len(steps), lo + budget - 2)
    lo = max(0, hi - (budget - 2))

    agent_rail = _AGENT_COL[0]             # color de identidad (riel del flujo)
    blocks = []                            # cada paso = un bloque de líneas
    for i in range(lo, hi):
        st = steps[i]
        sstat = st.get("status")
        is_cur = (i == star and sstat in ("pending", "waiting_human")
                  and status in ("running", "paused_human"))
        glyph, gcol = _step_glyph(sstat, st.get("stub"), is_cur, tick)
        label = _safe(st.get("id")) or "?"
        blk = []
        if is_cur:
            # ── LA CAJA: el paso actual, protagonista imposible de perder ──
            waiting = (sstat == "waiting_human")
            bcol = MID if waiting else ACCENT
            tag = "TE TOCA A TI" if waiting else "AQUÍ VAMOS"
            bw = inner - 2                     # ancho interior (entre los ┃)

            def _boxrow(interior, bcol=bcol, bw=bw):
                # envuelve una fila-interior (ya-coloreada) en ┃…┃ a ancho EXACTO
                # bw: clipa si excede (jamás desborda el borde), padea si falta.
                interior = _clip(interior, bw)
                gap = max(0, bw - _vw(interior))
                return (LM + bcol + "┃" + R + interior + " " * gap
                        + bcol + "┃" + R)

            blk.append(LM + bcol + "╭" + "─" * bw + "╮" + R)
            lab = _clip(label, bw - _vw(tag) - 8)
            hrow = ("  " + gcol + glyph + R + "  " + TEXT + BOLD + lab + R)
            hrow += " " * max(1, bw - _vw(hrow) - _vw(tag) - 1) \
                + HI + BOLD + tag + R + " "
            blk.append(_boxrow(hrow))
            det = (_safe(st.get("detail")) or "").split("·")[0].strip()
            dur = front._wf_step_dur(st)
            sub = "     " + FAINT + _clip(det or "trabajando…", bw - 14) + R
            if dur:
                sub += FAINT + "  ⏱ " + dur + R
            blk.append(_boxrow(sub))
            blk.append(LM + bcol + "╰" + "─" * bw + "╯" + R)
        else:
            done_step = sstat in ("ok", "skipped")
            ncol = FAINT if (st.get("stub") or (done_step and sstat == "skipped")) \
                else (TEXT if done_step else GREY)
            right = ""
            dur = front._wf_step_dur(st) if sstat in ("ok", "fail") else ""
            if dur:
                right = FAINT + dur + R
            elif sstat == "waiting_human":
                right = MID + "en espera" + R
            elif sstat == "pending":
                right = FAINT + "pendiente" + R
            elif sstat == "rejected":
                right = BAD + "rechazado" + R
            row = LM + gcol + glyph + R + " " + ncol + _clip(label, inner - 14) + R
            blk.append(row + _pad_right(_strip(row) + " ", w - 1, right))
        blocks.append(blk)

    # riel de altura ADAPTATIVA: reparte el alto SOBRANTE entre los tramos para
    # que la pipeline LLENE el pane (línea de metro), no se apiñe arriba dejando
    # media pantalla vacía. Solo crece si hay hueco (spare>0) → jamás desborda.
    top_extra = 1 if lo > 0 else 0
    bot_extra = 1 if hi < len(steps) else 0
    content = sum(len(b) for b in blocks)
    gaps = max(1, len(blocks) - 1)
    used = 3 + top_extra + content + bot_extra   # 3 = header/bar/blank ya en out
    rail_h = min(3, 1 + max(0, (h - used) // gaps))

    if lo > 0:
        out.append(LM + FAINT + "  ⋮ %d paso%s antes" % (lo, "" if lo == 1 else "s") + R)
    for j, blk in enumerate(blocks):
        out.extend(blk)
        if j < len(blocks) - 1:
            out.extend([LM + agent_rail + "┃" + R] * rail_h)
    if hi < len(steps):
        rem = len(steps) - hi
        out.append(LM + FAINT + "  ⋮ %d más" % rem + R)

    # ── desenlace terminal ──
    if status == "done":
        out.append("")
        out.append(LM + OK + "✓ %d / %d · completado" % (done, total)
                   + (" en " + front._wf_run_elapsed(state) if front._wf_run_elapsed(state) else "") + R)
    elif status in ("failed", "rejected"):
        bad_i = next((i for i, s in enumerate(steps)
                      if s.get("status") in ("fail", "rejected")), None)
        who = _safe(steps[bad_i].get("id")) if bad_i is not None else ""
        out.append("")
        out.append(LM + ERR + "✗ se detuvo" + (" en «%s»" % who if who else "") + R)
    return out


def _pad_right(plain_left, width, right_colored):
    """Empuja `right_colored` (con ANSI) al borde derecho `width`, dado el ancho
    VISUAL ya-medido de la izquierda (`plain_left` = texto sin ANSI). Devuelve
    el relleno + el bloque derecho. PURA."""
    gap = max(1, int(width) - _vw(plain_left) - _vw(right_colored))
    return " " * gap + right_colored


def _wf_idle_lines(runs, w, h):
    """SIN run activo (diseño Iris §C): runs recientes limpios + invitación."""
    out = [LM + MID + "runs recientes" + R, ""]
    inner = max(20, w - 2)
    cap = max(1, min(len(runs), h - 6))
    import front
    for st in runs[:cap]:
        sstat = st.get("status")
        gmap = {"done": ("✓", OK), "failed": ("✗", ERR), "rejected": ("⊗", BAD),
                "paused_human": ("⏸", MID), "running": ("◐", HI)}
        glyph, gcol = gmap.get(sstat, ("·", GREY))
        done, total = front._wf_progress(st)
        name = _safe(st.get("workflow")) or "?"
        ver = "v%s" % st.get("version", "?")
        rel = _wf_rel(st.get("updated"))
        prog = (OK if sstat == "done" else FAINT) + "%d/%d" % (done, total) + R
        left = (LM + gcol + glyph + R + " " + TEXT + _clip(name, inner - 24) + R
                + "  " + MID + ver + R + "  " + FAINT + rel + R)
        out.append(left + _pad_right(_strip(left) + " ", w - 1, prog))
    out += ["", LM + RULE + "┈" * inner + R, ""]
    inv1 = "corre un workflow y aquí lo verás"
    inv2 = "crecer paso a paso, en vivo."
    out.append(_center(FAINT + inv1 + R, w))
    out.append(_center(FAINT + inv2 + R + " " + ACCENT + "✦" + R, w))
    return out


def _center(colored, w):
    """Centra una línea ya-coloreada en `w` (mide sin ANSI). PURA."""
    pad = max(0, (int(w) - _vw(colored)) // 2)
    return " " * pad + colored


def _title(label, w, right=""):
    """Fila de título de vista (ACCENT bold) + su regla (diseño Iris §0.3).
    `right` = badge/hint YA coloreado, empujado al borde derecho. PURA."""
    left = LM + ACCENT + BOLD + label + R
    line = (left + _pad_right(_strip(left), w - 1, right)) if right else left
    return [_clip(line, w), RULE + ("─" * max(10, w)) + R]


def _view_pipeline(ctx, w, h):
    """La vista Workflows: si hay run activo → la pipeline EN GRANDE en vivo
    (§B); si no → runs recientes + invitación (§C). Diseño de Iris."""
    global _AGENT_COL
    _AGENT_COL = ((ctx.ident or {}).get("col") or ACCENT,)
    import workflows as wf
    fid = None
    try:
        fid = wf.active_run()
    except Exception:
        pass
    state = None
    if fid:
        try:
            state = wf.load_run(fid)
        except Exception:
            state = None
    if state and (state.get("steps") or state.get("status") == "running"):
        stt = state.get("status")
        badge = {"running": HI + _SPIN[_tick()] + " corriendo" + R,
                 "paused_human": MID + "⏸ te toca a ti" + R,
                 "done": OK + "✓ completado" + R,
                 "failed": ERR + "✗ falló" + R,
                 "rejected": BAD + "⊗ rechazado" + R}.get(stt, GREY + str(stt) + R)
        head = _title("workflows", w, badge)
        try:
            return head + _wf_active_lines(state, w, max(6, h - 2))
        except Exception as e:
            return head + [LM + WARN + "run activo (detalle no disponible): %s"
                           % str(e)[:40] + R]
    head = _title("workflows", w, GREY + "○ en reposo" + R)
    try:
        runs = wf.list_runs(limit=12)
    except Exception:
        runs = []
    if not runs:
        return head + ["", _center(FAINT + "aún no corre ningún workflow" + R, w),
                       _center(FAINT + "corre uno y aparece aquí, en vivo " + R
                               + ACCENT + "✦" + R, w)]
    return head + _wf_idle_lines(runs, w, max(6, h - 2))


_AGENT_COL = (ACCENT,)                      # color de identidad para el riel


def _view_bus(ctx, w, h):
    """El bus (diseño Iris §E1): inbox del agente — pendientes con from/subject,
    ● no-leído / ○ leído, marca `ok?` (rojo-suave) si requieren aprobación."""
    import messages
    if not ctx.agent:
        return _title("bus", w) + [
            "", _center(FAINT + "abre el panel con --agent para ver tu inbox" + R, w)]
    try:
        pend = messages.inbox(ctx.brain, ctx.agent) or []
    except Exception:
        pend = []
    badge = (HI + BOLD + "%d nuevo%s" % (len(pend), "" if len(pend) == 1 else "s")
             + R) if pend else GREY + "vacío" + R
    out = _title("bus · inbox", w, badge)
    if not pend:
        out += ["", _center(FAINT + "nada por atender ✓" + R, w)]
        return out
    out.append("")
    cap = max(1, (h - 5) // 4)                  # ~4 filas por mensaje
    for m in pend[:cap]:
        who = _safe(m.get("from")) or "?"
        subj = _safe(m.get("subject")) or "(sin asunto)"
        ap = (BAD + BOLD + "ok?" + R) if m.get("requires_approval") else ""
        head = LM + HI + "●" + R + " " + TEXT + BOLD + _clip(who, w - 10) + R
        out.append(head + (_pad_right(_strip(head) + " ", w - 1, ap) if ap else ""))
        out.append(LM + "  " + _clip(TEXT + subj + R, w - 4))
        meta = FAINT + "┈ " + (_wf_rel(m.get("ts")) or "") + R
        typ = _safe(m.get("type"))
        if typ:
            meta += FAINT + " · " + R + MID + typ + R
        out.append(LM + "  " + meta)
        out.append("")
    left = len(pend) - cap
    if left > 0:
        out.append(LM + GREY + "○ %d más" % left + R)
    out.append("")
    out.append(LM + FAINT + "responder: en el chat · el bus sincroniza solo" + R)
    return out


def _view_config(ctx, w, h):
    """Config (diseño Iris §E2): tarjeta de identidad + settings clave, dos
    columnas alineadas, solo-lectura. El nombre y el color pintan en el color
    del agente (autoreferencia). Nada aquí es accionable → tonos apagados."""
    import settings
    col = (ctx.ident or {}).get("col") or ACCENT
    disp = _safe((ctx.ident or {}).get("display")) or (ctx.agent or "agente").capitalize()
    emj = _safe((ctx.ident or {}).get("emoji"))
    brain = ctx.brain or ""
    home = os.path.expanduser("~")
    if brain.startswith(home):
        brain = "~" + brain[len(home):]
    rows = [("agente", col + disp + ((" " + emj) if emj else "") + R)]
    # color legible desde agent.json (best-effort), pintado en su propio color
    try:
        import json
        with open(os.path.join(ctx.brain, ".workspace", "agent.json"),
                  encoding="utf-8") as _fh:
            c = json.load(_fh).get("color")
        if c:
            rows.append(("color", col + _safe(c) + R))
    except Exception:
        pass
    rows.append(("cerebro", TEXT + _clip(brain, w - 14) + R))
    for k, lbl in [("ui.split", "split"), ("ui.split_pane", "pane der."),
                   ("ui.split_backend", "backend"), ("latido.mode", "latido"),
                   ("ui.theme", "tema")]:
        try:
            v = settings.get(k, None)
        except Exception:
            v = None
        if v is None:
            continue
        vcol = OK if v in (True, "on", "auto", "panel") else TEXT
        rows.append((lbl, vcol + str(v) + R))
    out = _title("config", w, GREY + "solo lectura" + R)
    for lbl, val in rows:
        out.append(LM + MID + lbl.ljust(10) + R + " " + val)
    out += ["", LM + FAINT + "┈ se edita en workspace config / agent.json" + R]
    return out


def _view_delegar(ctx, w, h):
    """Delegar (diseño Iris §E3): a QUIÉN mandarle una tarea por el bus — lista
    de agentes del equipo, misma gramática (▸/número) que Sesiones. El envío se
    hace desde el chat ('dile a X…'); aquí está el mapa + el comando honesto."""
    out = _title("delegar", w, FAINT + "manda una tarea" + R)
    col = (ctx.ident or {}).get("col") or ACCENT
    out.append("")
    out.append(LM + MID + "¿a quién?" + R)
    out.append("")
    agents = []
    try:
        import dispatch
        reg = dispatch.load_registry() if hasattr(dispatch, "load_registry") else {}
        for a in (reg.get("agents", []) if isinstance(reg, dict) else []):
            nm = _safe(a.get("name"))
            if nm and nm.lower() != (ctx.agent or ""):
                agents.append((nm, _safe(a.get("scope") or a.get("tagline") or "")))
    except Exception:
        pass
    for i, (nm, role) in enumerate(agents[:max(1, h - 8)], 1):
        line = (LM + GREY + "  " + str(i) + R + "  " + TEXT + nm.capitalize() + R)
        if role:
            line += "   " + FAINT + _clip(role, w - _vw(nm) - 10) + R
        out.append(_clip(line, w))
    if not agents:
        out.append(LM + FAINT + "(sin otros agentes registrados)" + R)
    out += ["", LM + FAINT + "en el chat: «dile a <agente> que…» — yo mando "
            "el bus" + R]
    return out


# ═══════════════════════════════════════════════════════════════════════════
# Vista SESIONES (VIEW 0) — listar/cambiar/cerrar sesiones del agente.
# Los imports de multiplexer/subprocess viven DENTRO de cada función en
# try/except: los tests de render (y una máquina sin herdr) corren igual.
# ═══════════════════════════════════════════════════════════════════════════
def _socio(brain):
    """El socio del cerebro: `<brain>/.claude/socio.local` (strip().lower()).
    Fallback: si `<brain>/STATE/sessions/` tiene EXACTAMENTE un subdir, ese.
    Cualquier fallo → ''."""
    try:
        p = os.path.join(brain, ".claude", "socio.local")
        if os.path.isfile(p):
            with open(p, encoding="utf-8") as fh:
                s = fh.read().strip().lower()
            if s:
                return s
    except Exception:
        pass
    try:
        sd = os.path.join(brain, "STATE", "sessions")
        subs = [d for d in os.listdir(sd)
                if os.path.isdir(os.path.join(sd, d))]
        if len(subs) == 1:
            return subs[0]
    except Exception:
        pass
    return ""


def _sessions_data(ctx, ttl=5.0, now=None):
    """Los datos de la vista Sesiones, con cache TTL (default 5s) en
    `ctx.cache_sesiones` — cero subprocess por tick del loop de 1s. Devuelve
    {"rows": […], "open_now": […]}:

      rows      — sesiones del agente (agent_brand.merged_sessions del cerebro
                  + workspaces.json per-máquina): {wid, name, estado,
                  actualizada, brain, switchable}. switchable = bool(wid).
      open_now  — sesiones herdr `workspace-split-*` VIVAS: {name, attached,
                  own} (own = la propia HERDR_SESSION).

    Falla-suave ABSOLUTA: sin cerebro / sin herdr / cualquier excepción → el
    bloque afectado queda vacío; el peor caso total es {"rows": [], "open_now": []}."""
    import time as _time
    if now is None:
        now = _time.time
    t = now()
    cache = getattr(ctx, "cache_sesiones", None)
    if cache and 0 <= (t - cache[0]) < ttl:
        return cache[1]
    data = {"rows": [], "open_now": []}
    try:
        try:
            import json
            import agent_brand
            brain = ctx.brain
            workspaces = []
            try:
                path = os.path.join(brain, ".claude",
                                    "%s-workspaces.json" % ctx.agent)
                with open(path, encoding="utf-8") as fh:
                    workspaces = json.load(fh)
                if not isinstance(workspaces, list):
                    workspaces = []
            except Exception:
                workspaces = []

            def _lh(w):
                # epoch de last_opened → created del PROPIO dict (no se toca
                # ~/.claude/projects); ISO roto falla-suave → 0.0
                from datetime import datetime
                for key in ("last_opened", "created"):
                    v = w.get(key)
                    if v:
                        try:
                            return datetime.fromisoformat(str(v)).timestamp()
                        except Exception:
                            pass
                return 0.0

            merged = agent_brand.merged_sessions(brain, _socio(brain),
                                                 workspaces, last_human=_lh)
            for m in merged:
                wid = m.get("id")
                data["rows"].append({
                    "wid": wid,
                    "name": m.get("name") or "",
                    "estado": m.get("_estado") or "",
                    "actualizada": m.get("_actualizada") or "",
                    "brain": bool(m.get("_brain")),
                    "switchable": bool(wid),
                })
        except Exception:
            pass
        try:
            import multiplexer
            own = os.environ.get("HERDR_SESSION")
            # solo la sesión herdr de ESTE agente (la propia): antes se listaban
            # TODAS las workspace-split-* (cross-agente) → en el panel de Atlas
            # aparecían las de zenith/harness ("una que no tenés") y clickearlas
            # cerraba sesiones ajenas. Las zombies de otros agentes las barre el
            # reaper (reap_orphans / `workspace split reap`), no este panel.
            mine = None
            try:
                mine = multiplexer.agent_session_name(ctx.agent) if ctx.agent else None
            except Exception:
                mine = None
            attached = multiplexer._attach_client_sessions()
            for n in sorted(multiplexer._running_split_sessions()):
                if n != own and n != mine:
                    continue
                data["open_now"].append({"name": n, "attached": n in attached,
                                         "own": n == own})
        except Exception:
            pass
        # current_ws: nombre resuelto por wid del PRIMER _sessions_data (si no
        # matchea queda None y la marca ▸ simplemente no aparece — falla-suave)
        try:
            if getattr(ctx, "current_wid", None) and not getattr(ctx, "current_ws", None):
                for r in data["rows"]:
                    if r.get("wid") == ctx.current_wid:
                        ctx.current_ws = r.get("name")
                        break
        except Exception:
            pass
    except Exception:
        data = {"rows": [], "open_now": []}
    ctx.cache_sesiones = (t, data)
    return data


def _view_sesiones(ctx, w, h):
    """Vista Sesiones: las sesiones del agente (1-9 = cambiar la del pane
    izquierdo) + las herdr vivas (`abiertas ahora`; x arma modo-cerrar).
    Render PURO sobre _sessions_data. Escribe `ctx.hits_rel` (fila relativa
    del body 0-based → acción) mientras pinta — render() lo traduce a
    absoluto. Falla-suave: sin datos pinta vacío, jamás levanta."""
    hits = {}
    try:
        data = _sessions_data(ctx)
    except Exception:
        data = {"rows": [], "open_now": []}
    rows = data.get("rows") or []
    open_now = data.get("open_now") or []
    col = (ctx.ident or {}).get("col") or ACCENT
    closing = getattr(ctx, "close_mode", False)
    badge = (BAD + BOLD + "¿cuál cierro? 1-9 · esc" + R) if closing \
        else GREY + "x cerrar" + R
    out = _title("sesiones", w, badge)
    if not rows:
        out += ["", _center(FAINT + "sin sesiones todavía" + R, w)]
        # NO retorna: la cola (abiertas ahora + aviso de solo-lectura del
        # backend) se pinta igual — el loop de filas simplemente no itera.
    # presupuesto: título (2) + colas (abiertas ahora / aviso solo-lectura)
    reserved = 2 + ((len(open_now) + 2) if open_now else 0) \
        + (0 if os.environ.get("HERDR_SESSION") else 2)
    cap = max(1, h - reserved)
    num, shown, skipped = 0, 0, 0
    for r in rows:
        wid = r.get("wid")
        name = _safe(r.get("name")) or "(sin nombre)"
        estado = _safe(r.get("estado"))
        act = _safe(r.get("actualizada"))
        if shown >= cap:                       # cap por ALTURA del pane
            skipped += 1
            continue
        if not r.get("switchable"):
            # sin wid local → no switcheable: tenue, sin letra
            out.append(_clip(LM + FAINT + "  · " + name
                             + " (en otra máquina — no local)" + R, w))
            shown += 1
            continue
        num += 1
        cur = (ctx.current_wid is not None and wid == ctx.current_wid)
        # cola derecha: estado (color por tipo) + fecha (tenue)
        el = estado.lower()
        ecol = OK if any(x in el for x in ("abiert", "activ", "viv")) \
            else (MID if "guard" in el else (GREY if "cerr" in el else FAINT))
        right = ((ecol + estado + R + "  ") if estado else "") \
            + (FAINT + act + R if act else "")
        if closing:
            mark = BAD + "⊘" + R
            ncol = TEXT
        elif cur:
            mark = col + BOLD + "▸" + R
            ncol = HI + BOLD
        else:
            mark = " "
            ncol = TEXT
        # LETRA (a-i) en vez de número: los números son de las TABS (1-5), las
        # sesiones se cambian por su letra o con click. Más allá de 9 → '·'
        # (sin atajo de teclado, pero clickeable igual).
        let = chr(ord("a") + num - 1) if num <= 9 else "·"
        numc = (HI + BOLD if cur else FAINT) + let + R
        left = LM + mark + " " + numc + "  " + ncol + _clip(name, w - 22) + R
        hits[len(out)] = ("switch", wid, r.get("name") or "")
        out.append(left + _pad_right(_strip(left) + " ", w - 1, right))
        shown += 1
        if cur:
            for e in (getattr(ctx, "emblem", None) or [])[:2]:
                out.append("       " + _clip(e, max(1, w - 8)))
                shown += 1
    if skipped:
        out.append(LM + FAINT + "  ⋮ +%d más" % skipped + R)
    # crear nueva sesión — CLICKEABLE (hit ("new",)); la tecla `n` hace lo
    # mismo. El loop la ejecuta con _new_session (registra el workspace + monta
    # el pane en él por el controlador persistente). Solo tiene sentido dentro
    # del split herdr; fuera es informativa (el switch/creación exige el
    # controlador). Se pinta igual para no dejar hueco.
    out.append("")
    if os.environ.get("HERDR_SESSION"):
        hits[len(out)] = ("new",)
        out.append(_clip(LM + ACCENT + "＋" + R + " " + TEXT + "nueva sesión"
                         + R + "   " + FAINT + "n o click" + R, w))
    else:
        out.append(_clip(LM + FAINT + "＋ nueva sesión: abre el split herdr "
                         + "para crear desde aquí" + R, w))
    if open_now:
        out.append("")
        out.append(LM + MID + "abiertas ahora" + R)
        letters = "abcdefghij"
        li = 0
        for s in open_now:
            nm = _safe(s.get("name")) or "?"
            if s.get("own"):
                out.append(_clip(LM + "  " + ACCENT + "·" + R + " " + TEXT + nm
                                 + R + "  " + HI + "← estás aquí" + R, w))
                continue
            lt = letters[li % len(letters)]
            li += 1
            if s.get("attached"):
                out.append(_clip(LM + FAINT + "  " + lt + " · " + nm
                                 + " (attacheada)" + R, w))
            else:
                hits[len(out)] = ("close", s.get("name"))
                out.append(_clip(LM + ACCENT + "  " + lt + R + " · " + TEXT + nm
                                 + R + " " + FAINT + "(detached)" + R, w))
    if not os.environ.get("HERDR_SESSION"):
        out.append("")
        out.append(LM + FAINT + "cambio de sesión: en el split herdr" + R)
    ctx.hits_rel = hits
    return out


def _sess_key(ctx, k, w, h):
    """Teclas de la vista Sesiones. Modelo CLARO (fix del "no me deja cambiar de
    sección"): los DÍGITOS 1-5 son de las TABS y NO se consumen aquí — caen al
    fallback global, así "2" SIEMPRE lleva a Workflows como dice la tab. Las
    SESIONES se cambian con su LETRA (a,b,c…) o con click. x/X arma el modo-
    cerrar; en él, la letra de una sesión 'abierta ahora' la cierra. Una letra
    sin sesión no se consume (cae al global, inofensiva)."""
    try:
        if k in ("x", "X"):
            ctx.close_mode = not ctx.close_mode
            return True
        # `n` = crear sesión nueva (el loop la ejecuta tras repintar el aviso).
        # La 'n' nunca es letra de sesión (el teclado llega hasta 'i' = 9ª) →
        # apropiársela no roba ningún atajo. Crear cancela el modo-cerrar.
        if k in ("n", "N"):
            ctx.pending_new = True
            ctx.close_mode = False
            return True
        # SOLO letras se manejan aquí; dígitos y demás → global (cambian de TAB)
        if not (isinstance(k, str) and len(k) == 1 and k.isalpha()):
            if getattr(ctx, "close_mode", False):   # Esc/otra tecla desarma
                ctx.close_mode = False
                return True
            return False
        kl = k.lower()
        try:
            data = _sessions_data(ctx)
        except Exception:
            data = {"rows": [], "open_now": []}
        idx = ord(kl) - ord("a")               # a→0 · b→1 … i→8
        if getattr(ctx, "close_mode", False):
            ctx.close_mode = False
            det = [s for s in (data.get("open_now") or [])
                   if not s.get("attached") and not s.get("own")]
            if 0 <= idx < len(det):
                ctx.notice = _close_session(ctx, det[idx].get("name"))
            return True
        sw = [r for r in (data.get("rows") or [])
              if r.get("switchable")][:9]        # a–i (9 sesiones por teclado)
        if 0 <= idx < len(sw):
            r = sw[idx]
            if r.get("wid") == ctx.current_wid:
                ctx.notice = "ya estás en esa sesión"
            else:
                ctx.pending_switch = (r.get("wid"), r.get("name"))
            return True
        return False                           # letra sin sesión → no consume
    except Exception:
        return True                            # falla-suave: no cae al global


def _sess_click(ctx, x, y, w, h):
    """Click en la vista Sesiones vía el hit-map ABSOLUTO del último render
    (ctx.hits, filas 1-based del frame). True = consumido."""
    try:
        hit = (getattr(ctx, "hits", None) or {}).get(y)
        if not hit:
            return False
        if hit[0] == "new":
            ctx.pending_new = True             # el loop la crea tras repintar
            ctx.close_mode = False             # crear cancela el modo-cerrar
            return True
        if hit[0] == "switch":
            if getattr(ctx, "close_mode", False):
                ctx.close_mode = False         # en modo-cerrar no se switchea
                return True
            if hit[1] == ctx.current_wid:
                ctx.notice = "ya estás en esa sesión"
            else:
                ctx.pending_switch = (hit[1], hit[2])
            return True
        if hit[0] == "close":
            if getattr(ctx, "close_mode", False):
                ctx.close_mode = False
                ctx.notice = _close_session(ctx, hit[1])
            else:
                ctx.notice = "x arma el modo cerrar"
            return True
        return False
    except Exception:
        return True


def _stamp_opened(ctx, wid):
    """Best-effort tras un switch: estampa last_opened+updated (ISO now) en la
    entrada `id == wid` del workspaces.json del agente, escritura ATÓMICA
    (tmp + os.replace, mismo formato que mark_opened del dashboard). Si falla,
    solo se pierde el ordenamiento — regenerable. Jamás levanta."""
    try:
        import json
        from datetime import datetime
        path = os.path.join(ctx.brain or "", ".claude",
                            "%s-workspaces.json" % ctx.agent)
        with open(path, encoding="utf-8") as fh:
            ws = json.load(fh)
        if not isinstance(ws, list):
            return
        now = datetime.now().isoformat(timespec="seconds")
        for w in ws:
            if isinstance(w, dict) and w.get("id") == wid:
                w.setdefault("created", now)
                w["last_opened"] = now
                w["updated"] = now
                break
        else:
            return
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(ws, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
    except Exception:
        pass


def _controller_switch(ctx, wid, name, killpg=None):
    """CORE compartido por _switch_left y _new_session: monta el pane IZQUIERDO
    del split herdr en (wid, name) por la mecánica del CONTROLADOR PERSISTENTE
    (mux.chat_controller) y hace el commit. Devuelve (ok, msg): ok True → msg
    None (el caller pone el texto de éxito, que difiere: 'cambiado' vs 'nueva
    sesión'); ok False → msg = el error listo para ctx.notice. JAMÁS levanta.

    Diseño: el pane izquierdo corre un controlador que vive siempre; el chat es
    su hijo en su PROPIO grupo de proceso. Cambiar/crear sesión = escribir la
    sesión deseada en <ctl>/desired.json + matar SOLO el grupo del chat
    (<ctl>/chat_pgid) → el controlador relanza `dispatch --open <wid>` y el pane
    NUNCA se cierra (antes se mataba el proceso raíz del pane y herdr lo cerraba
    → el board se iba a pantalla completa).

    Pasos: guards de split (nt / fuera del split / mux) → leer/validar chat_pgid
    → guard anti-suicidio (jamás killpg del propio grupo, os.getpgrp()) →
    escribir desired ATÓMICO → SIGTERM al grupo del chat (ProcessLookupError =
    ya murió → seguir) → verificación best-effort session_running → commit +
    estampar last_opened. Sin polling: el controlador relanza async → RÁPIDO.

    NO incluye el guard wid==current (eso es propio del switch; un wid nuevo
    jamás iguala al actual). `killpg` inyectable para tests."""
    try:
        import signal

        # ── guards (el nt PRIMERO: os.killpg no existe en Windows y
        #    `killpg = os.killpg` daría AttributeError con notice equivocada) ──
        if os.name == "nt":
            return False, "switch solo en Mac/Linux"
        if killpg is None:
            killpg = os.killpg
        session = os.environ.get("HERDR_SESSION")
        if not session:
            return False, "fuera del split herdr — solo lectura"
        try:
            import mux
        except Exception:
            return False, "switch falló: mux no disponible"
        ctl = mux.ctl_dir(session)

        # ── pgid del grupo del chat vigente (lo publica el controlador) ──
        #    Se lee y valida ANTES de escribir desired: si no hay pgid válido
        #    abortamos SIN tocar desired.json, así el controlador no queda con
        #    una sesión "deseada" nueva mientras el pane sigue en la vieja
        #    (evita un relanzamiento fantasma cuando el socio sale normal).
        try:
            with open(os.path.join(ctl, "chat_pgid"), encoding="utf-8") as fh:
                pgid = int(fh.read().strip())
        except Exception:
            pgid = 0
        if pgid <= 0:
            return False, "no encuentro el chat (¿sesión vieja? reabrí el split)"
        if pgid == os.getpgrp():               # guard anti-suicidio
            return False, "pgid sospechoso — no toco nada"

        # ── pedir el switch: desired.json = {wid, name} (atómico) ──
        mux._write_desired(ctl, wid, name)

        # ── matar SOLO el grupo del chat (el controlador relanza) ──
        try:
            killpg(pgid, signal.SIGTERM)
        except ProcessLookupError:
            pass                               # ya murió → el loop relanza igual
        except Exception as e:
            # killpg falló por otra razón (EPERM…): revertir desired a la sesión
            # ACTUAL para que el controlador no relance solo al salir el socio.
            # OJO: NO caer al name/wid NUEVO (destino) — eso relanzaría igual;
            # sin current_wid conocido, borrar desired (el controlador cae a los
            # valores con que fue lanzado).
            try:
                if ctx.current_wid:
                    mux._write_desired(ctl, ctx.current_wid,
                                       ctx.current_ws or ctx.current_wid)
                else:
                    os.remove(os.path.join(ctl, "desired.json"))
            except Exception:
                pass
            return False, "no pude cambiar el chat: " + str(e)[:40]

        # ── verificación best-effort: ¿la sesión herdr sigue viva? ──
        import multiplexer
        if not multiplexer.session_running(session, dict(os.environ)):
            return False, "la sesión se cerró — reabrí el split"

        # ── commit ──
        ctx.current_wid, ctx.current_ws = wid, name
        ctx.cache_sesiones = None
        _stamp_opened(ctx, wid)
        return True, None
    except Exception as e:
        return False, "switch falló: " + str(e)[:60]


def _switch_left(ctx, wid, name, runner=None, killpg=None, sleep=None):
    """Cambia la sesión del pane IZQUIERDO del split herdr a (wid, name) —
    mecánica del CONTROLADOR PERSISTENTE (mux.chat_controller), delegada al
    core compartido _controller_switch. Devuelve SIEMPRE un string de una línea
    para ctx.notice; JAMÁS propaga excepción al loop ni escribe a stdout/stderr.

    Guards propios del switch (antes de tocar el controlador): nt → fuera del
    split → wid actual (no-op). Lo demás (chat_pgid, killpg, verificación,
    commit + estampar last_opened) vive en _controller_switch.

    `runner/killpg/sleep` inyectables (firma estable para tests; runner y sleep
    ya no se usan — el mecanismo nuevo no consulta el socket)."""
    try:
        # ── guards del switch (el nt PRIMERO: ver _controller_switch) ──
        if os.name == "nt":
            return "switch solo en Mac/Linux"
        if not os.environ.get("HERDR_SESSION"):
            return "fuera del split herdr — solo lectura"
        if wid == ctx.current_wid:
            return "ya estás en esa sesión"
        ok, msg = _controller_switch(ctx, wid, name, killpg=killpg)
        return ("cambiado → " + str(name)) if ok else msg
    except Exception as e:
        return "switch falló: " + str(e)[:60]


def _register_workspace(ctx, wid, name, now=None):
    """Agrega una entrada nueva {name,id,created,last_opened,updated} al
    `<agente>-workspaces.json` del agente — escritura ATÓMICA (tmp + os.replace),
    MISMO schema/formato que add_workspace del picker (agent-dashboard.py) y que
    _stamp_opened. Archivo ausente/roto → lista nueva. True si quedó registrada.
    Falla-suave ABSOLUTA: cualquier tropiezo → False (jamás levanta).

    `now` = callable → datetime (default datetime.now), inyectable para tests."""
    try:
        import json
        if now is None:
            from datetime import datetime
            now = datetime.now
        path = os.path.join(ctx.brain or "", ".claude",
                            "%s-workspaces.json" % ctx.agent)
        try:
            with open(path, encoding="utf-8") as fh:
                ws = json.load(fh)
            if not isinstance(ws, list):
                ws = []
        except Exception:
            ws = []                            # ausente/roto → arrancar lista
        try:
            ts = now().isoformat(timespec="seconds")
        except Exception:
            ts = ""
        ws.append({"name": name, "id": wid,
                   "created": ts, "last_opened": ts, "updated": ts})
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(ws, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _new_session(ctx, name=None, wid=None, killpg=None, now=None):
    """Crea una sesión NUEVA y monta el pane IZQUIERDO en ella. Análogo a
    _switch_left: SIEMPRE devuelve un string de una línea para ctx.notice;
    JAMÁS levanta; mismos guards de split (nt / HERDR_SESSION).

    Mecanismo de sesión FRESCA (confirmado en engines/claude_code.py): un wid
    (uuid4) SIN su .jsonl en el session-dir hace que `dispatch --open <wid>
    --name <name>` lance `claude --session-id <wid> --name <name>` = conversación
    NUEVA (un wid CON .jsonl daría `--resume <wid>`). Basta, pues, con generar un
    wid nuevo, registrarlo en el <agente>-workspaces.json y pedir el switch por
    el controlador persistente (desired.json + kill del grupo del chat) — el
    controlador relanza `dispatch --open <wid>` y arranca fresco.

    `name/wid/now/killpg` inyectables para tests. En producción: uuid4 +
    timestamp legible (código normal, NO un workflow)."""
    try:
        # ── guards del split (antes de generar/registrar nada) ──
        if os.name == "nt":
            return "sesión nueva solo en Mac/Linux"
        if not os.environ.get("HERDR_SESSION"):
            return "fuera del split herdr — solo lectura"

        # ── identidad de la sesión nueva (name legible + wid fresco) ──
        if now is None:
            from datetime import datetime
            now = datetime.now
        stamp = ""
        try:
            stamp = now().strftime("%d %b %H:%M")     # ej. "08 jul 14:03"
        except Exception:
            stamp = ""
        name = _safe(name) or (("sesión " + stamp).strip() if stamp
                               else "sesión nueva")
        if not wid:
            import uuid
            wid = str(uuid.uuid4())

        # ── registrar el workspace (atómico) ──
        if not _register_workspace(ctx, wid, name, now=now):
            return "no pude registrar la sesión nueva"

        # ── montar el pane en ella por el controlador persistente ──
        ok, msg = _controller_switch(ctx, wid, name, killpg=killpg)
        ctx.cache_sesiones = None              # la lista ganó una entrada
        return ("nueva sesión → " + str(name)) if ok else msg
    except Exception as e:
        return "no pude crear la sesión: " + str(e)[:60]


def _close_session(ctx, sess):
    """Cierra una sesión herdr `workspace-split-*` DETACHED (teardown completo:
    stop → kill pgids → delete — la solución probada a la fuga). Guards
    duros: jamás la propia HERDR_SESSION, jamás una attacheada. Devuelve el
    mensaje para ctx.notice; jamás levanta."""
    try:
        sess = str(sess or "")
        if not sess:
            return "sesión inválida"
        if sess == os.environ.get("HERDR_SESSION"):
            return "esa es esta ventana — cerrá el chat izquierdo"
        import multiplexer
        try:
            attached = multiplexer._attach_client_sessions()
        except Exception:
            attached = set()
        if sess in attached:
            return "tiene ventana abierta — cerrala desde ahí"
        try:
            multiplexer.herdr_teardown(sess, multiplexer._session_env(sess))
            msg = "cerrada " + sess
        except Exception:
            msg = "no pude cerrar " + sess
        ctx.cache_sesiones = None              # invalidar: la lista cambió
        ctx.close_mode = False
        return msg
    except Exception:
        return "no pude cerrar " + str(sess)[:40]


VIEWS = [
    {"key": "sesiones", "label": "Sesiones", "render": _view_sesiones,
     "on_key": _sess_key, "on_click": _sess_click,
     "hint": "a-i o click = sesión · n nueva · 1-5 = sección · x cerrar"},
    {"key": "workflows", "label": "Workflows", "render": _view_pipeline},
    {"key": "bus", "label": "Bus", "render": _view_bus},
    {"key": "config", "label": "Config", "render": _view_config},
    {"key": "delegar", "label": "Delegar", "render": _view_delegar},
]


# ═══════════════════════════════════════════════════════════════════════════
# Render del panel completo: header de identidad + tabs + cuerpo de la vista
# ═══════════════════════════════════════════════════════════════════════════
def _tab_spans(w):
    """(col inicial 1-based, ancho visual) de cada tab — MISMO layout que pinta
    _header: LM + segmentos 'N Label' separados por 2 espacios. Fuente ÚNICA
    para el subrayado dorado y el hit-testing del click (no se desincronizan).
    PURA."""
    spans = []
    col = 1 + len(LM)                           # tras el margen izq → col 2
    for i, v in enumerate(VIEWS):
        wv = _vw("%d %s" % (i + 1, v["label"]))
        spans.append((col, wv))
        col += wv + 2                           # separador de 2 espacios
    return spans


def _header(ctx, w, active):
    """Header de 4 filas FIJAS (diseño Iris §A): identidad · regla · tabs ·
    subrayado dorado bajo la tab activa (el 'estás aquí' de una pestaña física).
    Saneo en el punto de render (defensa en profundidad; _safe idempotente)."""
    ident = ctx.ident
    disp = _safe(ident.get("display")) or "Agente"
    emj = _safe(ident.get("emoji"))
    tg = _safe(ident.get("tagline"))
    col = ident.get("col") or ACCENT
    emoji = (emj + " ") if emj else ""
    # fila 1 · identidad: nombre en el color del AGENTE (violet/dorado…), tagline
    # tenue tras un ' · ' (recortada — no roba la fila)
    line = LM + col + BOLD + emoji + disp + R
    if tg:
        room = max(6, w - _vw(emoji + disp) - 5)
        line += " " + FAINT + "· " + _clip(tg, room) + R
    ident_line = _clip(line, w)
    # fila 2 · regla (separa identidad de navegación)
    rule = RULE + ("─" * max(10, w)) + R
    # fila 3 · tabs: activa en HI bold, resto GREY; número pegado al nombre
    cells = []
    for i, v in enumerate(VIEWS):
        seg = "%d %s" % (i + 1, v["label"])
        cells.append((HI + BOLD if i == active else GREY) + seg + R)
    tabs = _clip(LM + "  ".join(cells), w)
    # fila 4 · subrayado-segmento: corrida de ─ en accent SOLO bajo la activa
    spans = _tab_spans(w)
    under = ""
    if 0 <= active < len(spans):
        start, wv = spans[active]
        under = " " * (start - 1) + ACCENT + "─" * wv + R
    return [ident_line, rule, tabs, _clip(under, w)]


def _tab_at(x, y, w, top=0):
    """(x,y) 1-based de un click → índice de la tab bajo el cursor, o None.
    Las tabs viven en la fila `top + 3` (identidad=+1, regla=+2, tabs=+3,
    subrayado=+4; `top` = filas de emblema, hoy 0). Comparte _tab_spans con el
    pintado → click y subrayado nunca se desalinean. PURA."""
    if y != top + 3:
        return None
    for i, (start, wv) in enumerate(_tab_spans(w)):
        if start <= x <= start + wv - 1:
            return i
        if start > w:
            break
    return None


def render(ctx, w, h, active):
    """El frame completo (lista de líneas). PURA y testeable. Cada línea se
    clipa a `w` (no se envuelve → el repintado in-situ cuenta bien las filas)
    y el total se acota a `h` (no desborda → el cursor-arriba no se rompe).

    Hit-map: resetea `ctx.hits_rel` ANTES del body (la vista lo escribe al
    pintar) y lo traduce a `ctx.hits` ABSOLUTO (filas 1-based del frame:
    len(head)+1+rel). Footer: línea con `ctx.notice` (saneada _safe + _clip)
    si no está vacía; el hint de teclas es el de la vista (`"hint"`) o el
    global."""
    _apply_theme()                                 # colores del tema activo
    head = _header(ctx, w, active)
    hint = VIEWS[active].get("hint") or \
        ("1-%d o click · ←→/Tab · prefix+→ enfoca" % len(VIEWS))
    notice = _safe(getattr(ctx, "notice", "") or "")
    foot = [""]
    if notice:
        foot.append("  " + WARN + _clip(notice, max(1, w - 2)) + R)
    foot.append(SEP + "  " + hint + R)
    budget = max(1, h - len(head) - len(foot))     # filas reales para el cuerpo
    ctx.hits_rel = {}
    try:
        body = VIEWS[active]["render"](ctx, w, budget) or []
    except Exception as e:
        body = ["", "  " + WARN + "vista '%s' falló: %s" % (VIEWS[active]["key"],
                str(e)[:60]) + R]
    # relativo (0-based dentro del body) → absoluto (1-based del frame); las
    # filas clipadas por el presupuesto no dejan hits fantasma
    ctx.hits = {len(head) + 1 + rel: acc
                for rel, acc in (getattr(ctx, "hits_rel", {}) or {}).items()
                if 0 <= rel < min(len(body), budget)}
    # el cuerpo LLENA el alto del pane (footer anclado abajo, no colgando del
    # contenido corto): se rellena con líneas vacías hasta el presupuesto.
    body = body[:budget] + [""] * max(0, budget - len(body))
    frame = head + body + foot
    return [_clip(x, w) for x in frame][:h]         # sin wrap · sin overflow



# ═══════════════════════════════════════════════════════════════════════════
# Loop interactivo (repinta en sitio + lee teclas con timeout). Injectable.
# ═══════════════════════════════════════════════════════════════════════════
def _paint(lines, prev_n, out):
    """Repinta EN SITIO (cursor-arriba, \\r\\033[K por línea). Igual que el board."""
    if prev_n:
        out.write("\033[%dA" % prev_n)
    for ln in lines:
        out.write("\r\033[K" + ln + "\n")
    extra = prev_n - len(lines)
    if extra > 0:
        out.write("\r\033[K\n" * extra)
        out.write("\033[%dA" % extra)
    out.flush()
    return len(lines)


def _enter_raw():
    """Pone la terminal en modo RAW (sin eco) UNA vez para todo el loop y
    devuelve los attrs viejos (o None). CLAVE: sin esto, entre lecturas la
    terminal vuelve a modo cocido y ECHA las secuencias de mouse (la rueda
    escribía 'cosas raras' en el pane). Falla-suave: sin termios → None."""
    try:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        tty.setraw(fd)
        return old
    except Exception:
        return None


def _exit_raw(old):
    """Restaura los attrs de terminal guardados por _enter_raw. Best-effort."""
    if old is None:
        return
    try:
        import termios
        termios.tcsetattr(sys.stdin.fileno(), termios.TCSADRAIN, old)
    except Exception:
        pass


def _parse_key(data):
    """Del buffer CRUDO (ráfaga entera) devuelve el PRIMER token accionable:
    ('mouse',x,y) para click izquierdo, 'right'/'left'/'tab', o un char. Saltea
    rueda/release de mouse y CSI ajenas (drena todo, sin dejar bytes espurios).
    Ráfaga solo-de-rueda → None (consumida, sin acción)."""
    import re as _re
    i, n = 0, len(data)
    while i < n:
        b = data[i:i + 1]
        if b == b"\x1b":
            if data[i:i + 3] == b"\x1b[<":                 # mouse SGR
                m = _re.match(rb"\x1b\[<(\d+);(\d+);(\d+)([Mm])", data[i:])
                if m:
                    btn = int(m.group(1))
                    if (m.group(4) == b"M" and (btn & 0b11) == 0
                            and not (btn & 64)):            # click izq, no rueda
                        return ("mouse", int(m.group(2)), int(m.group(3)))
                    i += m.end()                            # rueda/release → saltar
                    continue
                i += 1
                continue
            nxt = data[i + 2:i + 3]                         # flechas CSI
            if data[i:i + 2] == b"\x1b[" and nxt == b"C":
                return "right"
            if data[i:i + 2] == b"\x1b[" and nxt == b"D":
                return "left"
            i += 3 if data[i:i + 2] == b"\x1b[" else 1      # otra CSI/ESC → saltar
            continue
        if b == b"\t":
            return "tab"
        ch = b.decode("utf-8", "ignore")
        if ch and ch.isprintable():
            return ch
        i += 1
    return None


def _read_key(timeout):
    """Un token accionable si hay input en `timeout`s, o None. Asume RAW ya
    puesto por run() (_enter_raw). DRENA toda la ráfaga disponible (una rueda
    genera cientos de bytes) y la parsea de una — cero bytes sueltos que en el
    siguiente tick se lean como basura. Falla-suave: cualquier error → None."""
    import select
    fd = sys.stdin.fileno()
    try:
        r, _, _ = select.select([fd], [], [], timeout)
        if not r:
            return None
        data = b""
        while True:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            data += chunk
            r2, _, _ = select.select([fd], [], [], 0)      # ¿queda más ráfaga?
            if not r2:
                break
        return _parse_key(data)
    except Exception:
        return None


def run(agent=None, argv=None, is_tty=None, max_ticks=None,
        read_key=None, size=None, interval=0.5, emblem=None):
    """El panel. Injectable para tests (is_tty/read_key/size/max_ticks/emblem)."""
    import shutil
    argv = argv if argv is not None else sys.argv
    agent = agent or _resolve_agent(argv)
    brain = _resolve_brain(agent)
    ctx = Ctx(agent, brain, _identity(agent, brain))
    ctx.current_wid = _resolve_wid(argv)   # el workspace del pane izquierdo
    if is_tty is None:
        is_tty = sys.stdout.isatty()
    if size is None:
        size = lambda: shutil.get_terminal_size((80, 30))  # noqa: E731
    if read_key is None:
        read_key = _read_key

    def wh():
        try:
            w, h = size()
            return max(1, int(w)), max(1, int(h))
        except Exception:
            return 80, 30

    # emblema DESACTIVADO por pedido del socio (quedaba raro en el header): el
    # panel es solo lista + menú, sin arte. El código de _emblem_lines queda por
    # si se reactiva (setting futuro). Tests pueden inyectar `emblem` igual.
    ctx.emblem = list(emblem) if emblem is not None else []

    active = 0
    if not is_tty:                              # pipe/CI: render único, sin loop
        w, h = wh()
        sys.stdout.write("\n".join(render(ctx, w, h, active)) + "\n")
        return 0

    out = sys.stdout
    # PANTALLA ALTERNA (\033[?1049h): buffer sin scrollback → el pane queda
    # FIJO. Mata dos bugs de un tiro: (a) el "stacking" (en la pantalla normal
    # cada repintado dejaba historia; al hacer scroll se veían frames apilados);
    # (b) el scroll que "rompía todo" (no hay a dónde scrollear). El pane
    # izquierdo (chat) tiene su propio buffer: NO se toca. + MOUSE SGR
    # (\033[?1000h;1006h): los clicks llegan como eventos → se navegan las tabs
    # con el mouse, y la rueda ya no scrollea el pane (el app consume el evento).
    # Todo se revierte SIEMPRE en el finally (pane limpio al cerrar la sesión).
    out.write("\033[?1049h\033[?25l\033[2J\033[H\033[?1000h\033[?1006h")
    out.flush()
    _raw = _enter_raw()             # RAW persistente: sin eco de las secuencias
    prev_n, prev_lines, ticks = 0, None, 0                # de mouse entre ticks
    try:
        while True:
            w, h = wh()
            lines = render(ctx, w, h, active)
            if lines != prev_lines:             # dedupe → cero flicker en idle
                prev_n = _paint(lines, prev_n, out)
                prev_lines = lines
            ticks += 1
            if max_ticks is not None and ticks >= max_ticks:
                return 0
            k = read_key(interval)
            if k in (None, "q"):                # 'q' no cierra el pane (vive con la sesión)
                continue
            # ── ENRUTADO: chrome global (tabs) → la vista → fallback global ──
            view = VIEWS[active]
            if isinstance(k, tuple) and k and k[0] == "mouse":
                # las tabs son chrome global y GANAN siempre. Header de 4 filas
                # FIJAS (identidad·regla·tabs·subrayado) → las tabs en la fila 3
                # (top=0; el emblema ya no vive en el header, diseño Iris §A).
                hit = _tab_at(k[1], k[2], w)
                if hit is not None:
                    active = hit
                else:
                    oc = view.get("on_click")
                    if oc is not None:
                        try:
                            oc(ctx, k[1], k[2], w, h)
                        except Exception:
                            pass                 # falla-suave: el click se pierde
                    # sin consumo → nada (un click en el cuerpo no navega)
            else:
                consumed = False
                ok = view.get("on_key")
                if ok is not None:
                    try:
                        consumed = bool(ok(ctx, k, w, h))
                    except Exception:
                        consumed = True          # falla-suave: no cae al global
                if not consumed:
                    # fallback global EXACTO de siempre (dígito=tab, tab/←→)
                    if k == "tab" or k == "right":
                        active = (active + 1) % len(VIEWS)
                    elif k == "left":
                        active = (active - 1) % len(VIEWS)
                    elif isinstance(k, str) and k and k in "123456789"[:len(VIEWS)]:
                        active = int(k) - 1      # dígito ASCII de una vista real
                        #   (k and … evita "" (in cualquier str = True); k.isdigit()
                        #   daría True con '²' → int() crashea; y "" in "1.." True)
            # ── switch pendiente: feedback YA (repintar con el aviso) y recién
            #    entonces bloquear en _switch_left — todo DENTRO del alt-screen
            if getattr(ctx, "pending_switch", None):
                swid, sname = ctx.pending_switch
                ctx.pending_switch = None
                ctx.notice = "cambiando a %s…" % _safe(sname)
                lines = render(ctx, w, h, active)
                if lines != prev_lines:
                    prev_n = _paint(lines, prev_n, out)
                    prev_lines = lines
                ctx.notice = _switch_left(ctx, swid, sname)
            # ── crear sesión NUEVA pendiente: mismo patrón que el switch —
            #    feedback YA (repintar con el aviso) y recién entonces el
            #    trabajo pesado (registrar + montar el pane), todo en alt-screen
            if getattr(ctx, "pending_new", None):
                ctx.pending_new = None
                ctx.notice = "creando sesión nueva…"
                lines = render(ctx, w, h, active)
                if lines != prev_lines:
                    prev_n = _paint(lines, prev_n, out)
                    prev_lines = lines
                ctx.notice = _new_session(ctx)
    except KeyboardInterrupt:
        return 0
    finally:
        # revertir TODO: raw off (attrs viejos) · mouse off · cursor on · buffer
        _exit_raw(_raw)
        out.write("\033[?1000l\033[?1006l\033[?25h\033[?1049l")
        out.flush()


if __name__ == "__main__":
    # Arranque directo (equivale a `front.py panel`): el pane derecho del split
    # corre esto. El agente llega por --agent (mux.right_pane_cmd lo pasa).
    sys.exit(run(argv=sys.argv) or 0)
