#!/usr/bin/env python3
"""WORKSPACE · docs_hub — el CONTENIDO de la sección «Documentación».

Todo lo que hace Workspace, en 13 capítulos y en el orden en que lo vives
(abrir, trabajar, cerrar…). Este archivo es la ÚNICA fuente: la pantalla
(docs_tui) solo lo pinta. Cada capítulo trae, en español y en inglés:

  · corto / titulo   el nombre en la lista y el encabezado del capítulo
  · mapa             cajas en fila para brain_view.pipeline:
                     (nodos, tramos, nota) — nodo = («largo|corto», color)
  · puntos           3–4 frases cortas (o `filas`: pares cuándo → qué)
  · apaga            «no se apaga: …» cuando no hay ajuste que lo cambie

y, sin idioma:

  · compruebalo      lo que lo demuestra: ("cerebro", ruta dentro del
                     cerebro) · ("estado", ruta en la carpeta de estado de
                     esta PC) · ("comando", "workspace …")
  · ajuste           la clave de settings que lo apaga (o None)
  · vivo             la función de «en esta PC»: una línea con el dato real
                     del agente elegido, SOLO LECTURA (jamás escribe nada) y
                     falla-suave (cualquier problema → «—»)

Cómo se mantiene verdadera: tests/test_docs_hub.py falla si una ruta, un
comando o un ajuste citado aquí deja de existir en el código o la plantilla.
Si cambias lo que hace Workspace, cambia aquí lo que se cuenta.

Cero dependencias (stdlib, 3.9+). Mac, Linux y Windows.
"""
import datetime
import json
import os
import re
import shutil
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

LANGS = ("es", "en")
#: Lo que se muestra cuando un dato en vivo no se puede leer.
NADA = "—"
#: Los seis motores: (id, nombre, programa). tests/test_docs_hub lo compara
#: con engines/<id>.py (META «needs»).
MOTORES = (("claude-code", "Claude Code", "claude"), ("codex", "Codex", "codex"),
           ("antigravity", "Antigravity", "agy"), ("opencode", "OpenCode", "opencode"),
           ("openclaw", "OpenClaw", "openclaw"), ("hermes", "Hermes", "hermes"))
#: La carpeta de estado tal como se le muestra a la persona (paths.state_dir
#: con el HOME como «~»; el test lo compara).
ESTADO_TXT = "~/.claude/workspace"


def lang():
    try:
        import i18n
        code = i18n.lang()
        return code if code in LANGS else "es"
    except Exception:
        return "es"


def _t(key, es, en=None, **kw):
    """i18n falla-suave: catálogo (lang/*/docs.py) → inline ES/EN."""
    s = es
    try:
        import i18n
        v = i18n.t(key, **kw) if kw else i18n.t(key)
        if v != key:
            return v
        if en is not None and i18n.lang() == "en":
            s = en
    except Exception:
        pass
    try:
        return s.format(**kw) if kw else s
    except Exception:
        return s


# ── utilidades de solo lectura ──────────────────────────────────────────────
def estado_dir():
    import paths
    return paths.state_dir()


def corto(path):
    """Ruta para mostrar: el HOME como «~» y barras normales."""
    home = os.path.expanduser("~")
    p = str(path or "")
    if p and os.path.normcase(p).startswith(os.path.normcase(home)):
        p = "~" + p[len(home):]
    return p.replace("\\", "/")


def _norm(p):
    try:
        return os.path.normcase(os.path.realpath(p))
    except Exception:
        return os.path.normcase(str(p or ""))


def _leer(path, tope=None):
    with open(path, "rb") as fh:
        if tope:
            fh.seek(0, 2)
            fh.seek(max(0, fh.tell() - tope))
        return fh.read().decode("utf-8", "replace")


def _cuando(ts):
    """Fecha corta y humana: «hoy 11:19», «ayer 09:02» o «2026-10-12»."""
    try:
        d = datetime.datetime.fromtimestamp(float(ts))
    except Exception:
        return NADA
    hoy = datetime.date.today()
    if d.date() == hoy:
        return _t("docs.when.today", "hoy {h}", "today {h}", h=d.strftime("%H:%M"))
    if d.date() == hoy - datetime.timedelta(days=1):
        return _t("docs.when.yesterday", "ayer {h}", "yesterday {h}", h=d.strftime("%H:%M"))
    return d.strftime("%Y-%m-%d")


def _kb(n):
    txt = "%.1f" % (max(0, n) / 1024.0)
    return (txt if lang() == "en" else txt.replace(".", ",")) + " KB"


def _socio(brain):
    try:
        import sessions_registry as reg
        return reg.socio(brain)
    except Exception:
        return ""


def _pestanas(brain):
    """[(slug, ruta, mtime, bytes)] de las pestañas del usuario de esta PC,
    la más reciente primero. Solo lista; no abre ni crea nada."""
    soc = _socio(brain)
    if not brain or not soc:
        return []
    d = os.path.join(brain, "STATE", "sessions", soc)
    out = []
    try:
        nombres = os.listdir(d)
    except OSError:
        return []
    for f in nombres:
        if not f.endswith(".md") or f.startswith(("_", ".")) or f.lower() == "readme.md":
            continue
        p = os.path.join(d, f)
        if os.path.isfile(p):
            st = os.stat(p)
            out.append((f[:-3], p, st.st_mtime, st.st_size))
    return sorted(out, key=lambda x: -x[2])


def _brain(c):
    b = (c or {}).get("brain") or ""
    return b if b and os.path.isdir(b) else ""


# ── «en esta PC»: una línea real del agente elegido (solo lectura) ─────────
def _vivo_carpeta(c):
    b = _brain(c)
    if not b:
        return NADA
    ok = _t("docs.vivo.yes", "✓", "✓")
    partes = ["%s %s" % (n, ok if os.path.exists(os.path.join(b, n)) else NADA)
              for n in ("BRAIN.md", "BOOT", "STATE", "skills", "wiki")]
    return "%s/ · %s" % (os.path.basename(os.path.normpath(b)), " · ".join(partes))


def _vivo_motores(c):
    nombre = dict((i, n) for i, n, _p in MOTORES)
    aqui = [n for _i, n, prog in MOTORES if shutil.which(prog)]
    eng = (c or {}).get("engine") or ""
    return _t("docs.vivo.engines", "motor de este agente: {m} · instalados: {lista}",
              "this agent's engine: {m} · installed: {lista}",
              m=nombre.get(eng, eng or NADA), lista=", ".join(aqui) or NADA)


def _vivo_pestana(c):
    tabs = _pestanas(_brain(c))
    if not tabs:
        return _t("docs.vivo.no_tabs", "todavía no hay pestañas con memoria",
                  "no tabs with memory yet")
    slug, _p, _m, size = tabs[0]
    return _t("docs.vivo.tabs", "pestañas: {n} · la última: {t} ({kb})",
              "tabs: {n} · the latest: {t} ({kb})", n=len(tabs), t=slug, kb=_kb(size))


def _vivo_trabajas(c):
    tabs = _pestanas(_brain(c))
    if not tabs:
        return _t("docs.vivo.no_notes", "todavía no hay notas en este agente",
                  "no notes in this agent yet")
    import memoria as M
    slug, path, _m, _s = tabs[0]
    ficha = M.Ficha(_leer(path))
    return _t("docs.vivo.notes", "pestaña {t} · notas: {n} · abiertas: {a}",
              "tab {t} · notes: {n} · open: {a}", t=slug, n=len(M.notas(ficha)),
              a=len(M.vigente(ficha)))


def _ultimo_cierre(brain):
    """El último registro de cierre de ESTE cerebro en logs/memoria.log."""
    path = os.path.join(estado_dir(), "logs", "memoria.log")
    if not os.path.isfile(path):
        return None
    meta = _norm(brain)
    for ln in reversed(_leer(path, tope=256 * 1024).splitlines()):
        try:
            rec = json.loads(ln)
        except ValueError:
            continue
        if isinstance(rec, dict) and rec.get("brain") and _norm(rec["brain"]) == meta:
            return rec
    return None


def _vivo_cerrar(c):
    b = _brain(c)
    if not b:
        return NADA
    rec = _ultimo_cierre(b)
    if not rec:
        return _t("docs.vivo.no_close", "todavía no hay cierres anotados en esta PC",
                  "no closes logged on this PC yet")
    try:
        ts = datetime.datetime.fromisoformat(str(rec.get("ts"))).timestamp()
    except Exception:
        ts = None
    fallas = sorted(k for k in rec if k == "error" or k.endswith("_error"))
    marca = ("✗ " + ", ".join(fallas)) if fallas else "✓"
    return _t("docs.vivo.close", "último cierre: {cuando} {marca} ({motor})",
              "last close: {cuando} {marca} ({motor})",
              cuando=_cuando(ts) if ts else NADA, marca=marca, motor=rec.get("engine") or NADA)


def _vivo_tiempo(c):
    b = _brain(c)
    if not b:
        return NADA
    soc = _socio(b)
    n = 0
    if soc:
        try:
            d = os.path.join(b, "STATE", "sessions", soc, "archivo")
            n = len([f for f in os.listdir(d) if f.endswith(".md")])
        except OSError:
            n = 0
    try:
        lineas = len(_leer(os.path.join(b, "STATE", "MEMORY.md")).rstrip("\n").split("\n"))
    except OSError:
        lineas = 0
    import memoria as M
    return _t("docs.vivo.time", "archivo/: {n} · MEMORY.md: {l} de {max} líneas",
              "archivo/: {n} · MEMORY.md: {l} of {max} lines",
              n=n, l=lineas, max=M.MEMORY_MAX_LINEAS)


def _vivo_usuarios(c):
    b = _brain(c)
    if not b:
        return NADA
    import usuarios as U
    yo = U.socio_actual(b, arreglar=False)
    n = len([x for x in U.cedulas(b) if x.get("id")])
    if not yo:
        return _t("docs.vivo.users_none", "esta PC todavía no eligió usuario · con cédula: {n}",
                  "this PC has not picked a user yet · with an ID: {n}", n=n)
    return _t("docs.vivo.users", "eres «{yo}» · usuarios con cédula: {n}",
              "you are «{yo}» · users with an ID: {n}", yo=yo, n=n)


def _vivo_viaja(c):
    name = (c or {}).get("name") or ""
    t = "obsidian-sync"
    if name:
        import dispatch
        t = dispatch.brain_transport(name)
    via = "git" if t == "git" else "Obsidian"
    return _t("docs.vivo.travel", "este cerebro viaja por {via} · lo de esta PC: {d}",
              "this brain travels through {via} · this PC's own: {d}",
              via=via, d=corto(estado_dir()))


def _hooks_conectados(b):
    try:
        cfg = json.loads(_leer(os.path.join(b, ".claude", "settings.local.json")))
    except (OSError, ValueError):
        return None
    h = cfg.get("hooks") if isinstance(cfg, dict) else None
    return len(h) if isinstance(h, dict) else 0


def _vivo_toca(c):
    b = _brain(c)
    eng = (c or {}).get("engine") or ""
    if not b:
        return NADA
    si = _t("docs.vivo.yes", "✓", "✓")
    if eng == "codex":
        from engines import codex
        cfg = codex._codex_config_path()
        head = '[projects."%s"]' % codex._toml_key_escape(os.path.realpath(b))
        try:
            ok = any(ln.strip() == head for ln in _leer(cfg).splitlines())
        except OSError:
            ok = False
        return _t("docs.vivo.touch_codex", "{f}: tu cerebro como carpeta de confianza {m}",
                  "{f}: your brain as a trusted folder {m}", f=corto(cfg), m=si if ok else NADA)
    if eng == "antigravity":
        from engines import antigravity
        cfg = os.path.join(antigravity._agy_home(), "settings.json")
        try:
            data = json.loads(_leer(cfg))
            tw = data.get("trustedWorkspaces") if isinstance(data, dict) else None
            ok = any(_norm(x) == _norm(b) for x in (tw or []) if isinstance(x, str))
        except (OSError, ValueError):
            ok = False
        return _t("docs.vivo.touch_agy", "{f}: tu cerebro, de confianza {m}",
                  "{f}: your brain, trusted {m}", f=corto(cfg), m=si if ok else NADA)
    if eng in ("openclaw", "hermes"):
        if eng == "openclaw":
            from engines import openclaw
            d = openclaw.state_dir()
        else:
            from engines import hermes
            d = hermes.profile_dir()
        return _t("docs.vivo.touch_profile", "perfil propio: {d} {m}", "own profile: {d} {m}",
                  d=corto(d), m=si if os.path.isdir(d) else NADA)
    if eng == "opencode":
        return _t("docs.vivo.touch_opencode", "OpenCode: nada fuera del cerebro",
                  "OpenCode: nothing outside the brain")
    n = _hooks_conectados(b)
    if n is None:
        return _t("docs.vivo.touch_cc_none", ".claude/settings.local.json: todavía no existe",
                  ".claude/settings.local.json: not there yet")
    return _t("docs.vivo.touch_cc", ".claude/settings.local.json · eventos conectados: {n}",
              ".claude/settings.local.json · events connected: {n}", n=n)


def _modo_txt(m):
    return {"auto": _t("docs.mode.auto", "automático", "automatic"),
            "notify": _t("docs.mode.notify", "solo avisa", "notify only"),
            "off": _t("docs.mode.off", "apagado", "off")}.get(m, m)


def _vivo_red(c):
    import updater
    modo = _modo_txt(updater.auto_mode())
    stamp = os.path.join(estado_dir(), "last_update_check")
    if not os.path.exists(stamp):
        return _t("docs.vivo.net_never", "todavía no buscó versión nueva en esta PC · modo: {m}",
                  "has not looked for a new version on this PC yet · mode: {m}", m=modo)
    return _t("docs.vivo.net", "última búsqueda de versión: {c} · modo: {m}",
              "last version check: {c} · mode: {m}", c=_cuando(os.path.getmtime(stamp)), m=modo)


def _vivo_nohace(c):
    import secret_store
    n = len(secret_store.names())
    if not n:
        return _t("docs.vivo.secrets_none", "secrets.local: ninguna llave guardada",
                  "secrets.local: no keys stored")
    return _t("docs.vivo.secrets", "llaves en secrets.local: {n}, solo para el hub",
              "keys in secrets.local: {n}, for the hub only", n=n)


def _vivo_actualizar(c):
    import updater
    v = updater.read_version() or NADA
    u = updater.last_update()
    if not u:
        return _t("docs.vivo.update_none", "versión {v} · todavía sin actualizaciones en esta PC",
                  "version {v} · no updates on this PC yet", v=v)
    return _t("docs.vivo.update", "versión {v} · última actualización: {f}",
              "version {v} · last update: {f}", v=v, f=str(u.get("at") or NADA)[:10])


def _vivo_ajustes(c):
    import settings
    cambiados = []
    for _lab, _pal, clave, _def in AJUSTES_CLAVE:
        spec = settings._BY_KEY.get(clave)
        if spec is not None and settings.get(clave) != spec.get("default"):
            cambiados.append(clave)
    if not cambiados:
        return _t("docs.vivo.settings_same", "todo como viene de fábrica",
                  "everything as it ships")
    return _t("docs.vivo.settings", "distintos de fábrica: {k}", "changed from default: {k}",
              k=", ".join(cambiados))


# ── los capítulos ───────────────────────────────────────────────────────────
#: Los ajustes del capítulo 13: (etiqueta es/en, palabra de fábrica es/en,
#: clave, valor de fábrica). El test compara clave y valor con SETTINGS_SCHEMA.
AJUSTES_CLAVE = (
    (("actualizaciones", "updates"), ("auto", "auto"), "otros.auto_update", "auto"),
    (("telemetría local", "local telemetry"), ("apagada", "off"), "hooks.telemetry", False),
    (("respaldo de sesiones", "session backup"), ("encendido", "on"),
     "hooks.transcript_backup", True),
    (("antes de compactar", "before compacting"), ("guarda", "saves"),
     "hooks.memory_flush", True),
    (("avisos de seguridad", "security notices"), ("encendidos", "on"),
     "hooks.security_guidance", True),
    (("revisión de skills", "skill review"), ("apagada", "off"), "hooks.skill_review", False),
    (("memoria de Claude", "Claude Code memory"), ("en el cerebro", "in the brain"),
     "cerebro.claude_memoria_en_cerebro", True),
    (("abrir con la terminal", "open with terminal"), ("apagado", "off"),
     "ui.autostart", False),
)

#: Etiqueta humana de cada ajuste citado en «se apaga en».
AJUSTE_ETIQUETA = {
    "hooks.security_guidance": ("avisos de seguridad (Claude Code)",
                                "security notices (Claude Code)"),
    "cerebro.claude_memoria_en_cerebro": ("memoria de Claude Code en el cerebro",
                                          "Claude Code memory in the brain"),
    "otros.auto_update": ("actualizaciones automáticas", "automatic updates"),
}


def _cap(cid, es, en, compruebalo, ajuste, vivo):
    return {"id": cid, "es": es, "en": en, "compruebalo": compruebalo,
            "ajuste": ajuste, "vivo": vivo}


CAPITULOS = (
    _cap("carpeta",
         es={"corto": "tu agente es una carpeta",
             "titulo": "Tu agente es una carpeta",
             "mapa": ((("tú y tu agente|tú + agente", "c"), ("el cerebro|cerebro", "wh"),
                       ("Workspace", "ok")),
                      ("identidad · skills · wiki|identidad", "memoria · usuarios|memoria"),
                      "todo es texto: lo puedes abrir y leer"),
             "puntos": (
                 "Tu agente es una carpeta normal: su cerebro. Lo que es, lo que sabe y lo que "
                 "recuerda está en archivos de texto que puedes abrir.",
                 "Tú y tu agente escriben la identidad (BRAIN.md y BOOT/), las skills y la wiki. "
                 "Workspace las siembra al crear el agente y no reescribe lo tuyo; si una "
                 "actualización ordena algo ahí, antes guarda un respaldo.",
                 "Workspace escribe la memoria: cada pestaña en STATE/sessions/, su parte de "
                 "STATE/MEMORY.md y los usuarios en STATE/users/.",
                 "Para los motores deja .claude/ y .workspace/ (conexiones y datos del agente) y "
                 "AGENTS.md o GEMINI.md, que apuntan al cerebro."),
             "apaga": "no se apaga: es tu agente"},
         en={"corto": "your agent is a folder",
             "titulo": "Your agent is a folder",
             "mapa": ((("you and your agent|you + agent", "c"), ("the brain|brain", "wh"),
                       ("Workspace", "ok")),
                      ("identity · skills · wiki|identity", "memory · users|memory"),
                      "it is all text: you can open and read it"),
             "puntos": (
                 "Your agent is a regular folder: its brain. What it is, what it knows and what "
                 "it remembers live in text files you can open.",
                 "You and your agent write the identity (BRAIN.md and BOOT/), the skills and the "
                 "wiki. Workspace seeds them when the agent is created and does not rewrite what "
                 "is yours; if an update tidies something there, it saves a backup first.",
                 "Workspace writes the memory: each tab in STATE/sessions/, its part of "
                 "STATE/MEMORY.md and the users in STATE/users/.",
                 "For the engines it keeps .claude/ and .workspace/ (connections and agent data) "
                 "and AGENTS.md or GEMINI.md, which point to the brain."),
             "apaga": "can't be turned off: it is your agent"},
         compruebalo=("cerebro", ""), ajuste=None, vivo=_vivo_carpeta),

    _cap("motores",
         es={"corto": "los motores",
             "titulo": "Los motores: Workspace no es el motor",
             "mapa": ((("Workspace", "c"), ("el motor|motor", "wh"), ("tu proveedor|proveedor", "dk")),
                      ("prepara y abre|abre", "con tu cuenta|tu cuenta"),
                      "el motor y tu cuenta son tuyos"),
             "puntos": (
                 "Workspace no es el motor: abre el programa oficial que ya usas (Claude Code, "
                 "Codex, Antigravity, OpenCode, OpenClaw o Hermes) dentro de la carpeta de tu agente.",
                 "El motor habla con su proveedor con tu propia cuenta. Esa conversación es del "
                 "motor, no de Workspace.",
                 "Cada agente tiene su motor. En el hub lo cambias con ←→ sobre el agente; se "
                 "guarda en esta PC.",
                 "Todos leen el mismo cerebro y la misma memoria: puedes empezar en un motor y "
                 "seguir en otro."),
             "apaga": "no se apaga: el motor de cada agente lo eliges tú"},
         en={"corto": "the engines",
             "titulo": "The engines: Workspace is not the engine",
             "mapa": ((("Workspace", "c"), ("the engine|engine", "wh"), ("your provider|provider", "dk")),
                      ("prepares and opens|opens", "your account|account"),
                      "the engine and your account are yours"),
             "puntos": (
                 "Workspace is not the engine: it opens the official program you already use "
                 "(Claude Code, Codex, Antigravity, OpenCode, OpenClaw or Hermes) inside your "
                 "agent's folder.",
                 "The engine talks to its provider with your own account. That conversation "
                 "belongs to the engine, not to Workspace.",
                 "Each agent has its engine. In the hub you change it with ←→ on the agent; it "
                 "is saved on this PC.",
                 "They all read the same brain and the same memory: you can start in one engine "
                 "and continue in another."),
             "apaga": "can't be turned off: you pick each agent's engine"},
         compruebalo=("cerebro", ".workspace/agent.json"), ajuste=None, vivo=_vivo_motores),

    _cap("pestana",
         es={"corto": "abrir una pestaña",
             "titulo": "Abrir una pestaña",
             "mapa": ((("pestaña", "c"), ("paquete", "wh"), ("motor", "ok")),
                      ("sin IA", "al arrancar|arranque"),
                      "resumen · vigente · notas nuevas · maleta (≤ 5000 car.)"),
             "puntos": (
                 "Cada pestaña tiene su propia memoria: un diario en "
                 "STATE/sessions/<usuario>/<pestaña>.md.",
                 "Al abrirla, Workspace arma un paquete sin IA: el resumen, lo vigente "
                 "(decisiones y pendientes), las notas nuevas y la maleta con lo último que pasó, "
                 "aunque haya sido en otro motor.",
                 "Es el mismo paquete en los seis motores: Claude Code lo recibe por su hook de "
                 "inicio; los demás, en AGENTS.md o GEMINI.md.",
                 "Por eso puedes cerrar en un motor y abrir en otro: el nuevo sabe en qué quedó "
                 "el anterior."),
             "apaga": "no se apaga: es la memoria de la pestaña"},
         en={"corto": "opening a tab",
             "titulo": "Opening a tab",
             "mapa": ((("tab", "c"), ("package", "wh"), ("engine", "ok")),
                      ("no AI", "at start|start"),
                      "summary · open items · new notes · handoff (≤ 5000 chars)"),
             "puntos": (
                 "Each tab has its own memory: a journal in STATE/sessions/<user>/<tab>.md.",
                 "When you open it, Workspace builds a package without AI: the summary, what is "
                 "open (decisions and pending items), the new notes and the handoff with the latest "
                 "that happened, even in another engine.",
                 "It is the same package on all six engines: Claude Code gets it through its "
                 "start hook; the others, in AGENTS.md or GEMINI.md.",
                 "That is why you can close in one engine and open in another: the new one "
                 "knows where the last one left off."),
             "apaga": "can't be turned off: it is the tab's memory"},
         compruebalo=("comando", "workspace memoria ver --tab {pestana}"), ajuste=None,
         vivo=_vivo_pestana),

    _cap("trabajas",
         es={"corto": "mientras trabajas",
             "titulo": "Mientras trabajas",
             "mapa": ((("tu agente", "c"), ("el diario|diario", "wh"), ("Vigente", "ok")),
                      ("nota con etiqueta|nota", "sin IA"),
                      "decisión · pendiente · hecho · nota · dato · preferencia"),
             "puntos": (
                 "Tu agente guarda lo importante en el momento, con una etiqueta, usando "
                 "workspace memoria nota.",
                 "Decisiones y pendientes reciben un número (D-3, P-7) y quedan en Vigente "
                 "hasta que se cierran. Datos y preferencias valen para todas las pestañas.",
                 "Una nota que parece una llave o contraseña se rechaza. En Antigravity, el "
                 "agente escribe sus notas en .claude/memoria-entrada/<pestaña>.md y las guarda "
                 "con un comando fijo.",
                 "El tono que elegiste va en el arranque (en Claude Code y Hermes, también en "
                 "cada mensaje). Si escribe código riesgoso en Claude Code, recibe un aviso que "
                 "no bloquea."),
             "apaga": ""},
         en={"corto": "while you work",
             "titulo": "While you work",
             "mapa": ((("your agent", "c"), ("the journal|journal", "wh"), ("Open items|open", "ok")),
                      ("labelled note|note", "no AI"),
                      "decision · pending · done · note · fact · preference"),
             "puntos": (
                 "Your agent saves what matters as it happens, with a label, using "
                 "workspace memoria nota.",
                 "Decisions and pending items get a number (D-3, P-7) and stay open until they "
                 "are closed. Facts and preferences apply to every tab.",
                 "A note that looks like a key or password is rejected. In Antigravity, the "
                 "agent writes its notes in .claude/memoria-entrada/<tab>.md and saves them with "
                 "a fixed command.",
                 "The tone you chose goes in at the start (in Claude Code and Hermes, with every "
                 "message too). If it writes risky code in Claude Code, it gets a notice that "
                 "never blocks."),
             "apaga": ""},
         compruebalo=("cerebro", "STATE/sessions/"), ajuste="hooks.security_guidance",
         vivo=_vivo_trabajas),

    _cap("cerrar",
         es={"corto": "cerrar",
             "titulo": "Cerrar una sesión, también con la X",
             "mapa": ((("cierras", "c"), ("maleta", "wh"), ("MEMORY.md", "ok")),
                      ("sin IA, al instante|sin IA", "datos y preferencias|datos"),
                      "lo que no alcance se termina al reabrir"),
             "puntos": (
                 "Al cerrar, sin IA y en un instante, Workspace arma la maleta: tus últimos "
                 "mensajes, la última respuesta y, en Claude Code y Codex, los archivos que se "
                 "tocaron.",
                 "Los datos y preferencias de la pestaña suben a STATE/MEMORY.md. Si el diario "
                 "creció mucho, se ordena (capítulo 6).",
                 "En Windows, si cierras la ventana con la X, Workspace usa hasta 4 segundos; lo "
                 "que falte lo termina la próxima vez que abras el agente. Claude Code lo hace "
                 "con su propio cierre.",
                 "Cada cierre queda anotado en esta PC, también si algo falló."),
             "apaga": "no se apaga: es la memoria"},
         en={"corto": "closing",
             "titulo": "Closing a session, even with the X",
             "mapa": ((("you close", "c"), ("handoff", "wh"), ("MEMORY.md", "ok")),
                      ("no AI, instantly|no AI", "facts and preferences|facts"),
                      "whatever doesn't fit is finished on reopen"),
             "puntos": (
                 "When you close, without AI and in an instant, Workspace packs the handoff: "
                 "your last messages, the last answer and, in Claude Code and Codex, the files "
                 "that were touched.",
                 "The tab's facts and preferences move up to STATE/MEMORY.md. If the journal "
                 "grew a lot, it gets tidied (chapter 6).",
                 "On Windows, if you close the window with the X, Workspace uses up to 4 "
                 "seconds; whatever is left is finished the next time you open the agent. "
                 "Claude Code does it with its own close.",
                 "Every close is logged on this PC, also when something failed."),
             "apaga": "can't be turned off: it is the memory"},
         compruebalo=("estado", "logs/memoria.log"), ajuste=None, vivo=_vivo_cerrar),

    _cap("tiempo",
         es={"corto": "la memoria en el tiempo",
             "titulo": "La memoria con el tiempo",
             "mapa": ((("diario", "c"), ("archivo/ del mes|archivo/", "wh")),
                      ("más de 30 notas u 8 KB|> 30 notas",),
                      "MEMORY.md: más de 200 líneas → memoria-archivo/"),
             "puntos": (
                 "Cuando el diario de una pestaña pasa de 30 notas u 8 KB, al cerrar se quedan "
                 "lo vigente y las 10 notas más recientes.",
                 "Las demás se mueven, completas, a STATE/sessions/<usuario>/archivo/: un "
                 "archivo por pestaña y por mes.",
                 "Si STATE/MEMORY.md pasa de 200 líneas, lo más viejo de la parte de Workspace "
                 "va a STATE/memoria-archivo/.",
                 "Nada se borra: todo sigue siendo texto que puedes abrir y buscar."),
             "apaga": "no se apaga: nada se borra, solo se ordena"},
         en={"corto": "memory over time",
             "titulo": "Memory over time",
             "mapa": ((("journal", "c"), ("month's archivo/|archivo/", "wh")),
                      ("over 30 notes or 8 KB|> 30 notes",),
                      "MEMORY.md: over 200 lines → memoria-archivo/"),
             "puntos": (
                 "When a tab's journal goes over 30 notes or 8 KB, on close it keeps what is "
                 "open and the 10 most recent notes.",
                 "The rest move, whole, to STATE/sessions/<user>/archivo/: one file per tab "
                 "and per month.",
                 "If STATE/MEMORY.md goes over 200 lines, the oldest of Workspace's part moves "
                 "to STATE/memoria-archivo/.",
                 "Nothing is deleted: it all stays text you can open and search."),
             "apaga": "can't be turned off: nothing is deleted, only tidied"},
         compruebalo=("cerebro", "STATE/memoria-archivo/"), ajuste=None, vivo=_vivo_tiempo),

    _cap("usuarios",
         es={"corto": "usuarios",
             "titulo": "Usuarios: quién usa cada agente",
             "mapa": ((("esta PC", "wh"), ("usuario", "c"), ("sus pestañas|pestañas", "ok")),
                      ("soy yo", "cédula fija|cédula"),
                      "el nombre es una etiqueta; la cédula nunca cambia"),
             "puntos": (
                 "Cada persona que usa el agente tiene un perfil en STATE/users/ con una "
                 "cédula: un ID que nunca cambia.",
                 "Si cambias un nombre, el viejo queda como alias: otra máquina que todavía use "
                 "el nombre viejo entra sola al nuevo.",
                 "Al abrir un agente, Workspace da cédula a quien no la tenga y corrige esta PC "
                 "si usa un nombre viejo. Te avisa en una línea.",
                 "Unir dos usuarios y «soy yo en esta PC» se hacen en la sección Usuarios. Nada "
                 "se borra."),
             "apaga": "no se apaga: así cada máquina sabe quién eres"},
         en={"corto": "users",
             "titulo": "Users: who uses each agent",
             "mapa": ((("this PC", "wh"), ("user", "c"), ("their tabs|tabs", "ok")),
                      ("that's me", "fixed ID|ID"),
                      "the name is a label; the ID never changes"),
             "puntos": (
                 "Everyone who uses the agent has a profile in STATE/users/ with an ID that "
                 "never changes.",
                 "If you rename someone, the old name stays as an alias: another machine that "
                 "still uses it lands on the new one by itself.",
                 "When you open an agent, Workspace gives an ID to anyone without one and fixes "
                 "this PC if it uses an old name. It tells you in one line.",
                 "Merging two users and «that's me on this PC» are done in the Users section. "
                 "Nothing is deleted."),
             "apaga": "can't be turned off: it is how each machine knows who you are"},
         compruebalo=("cerebro", "STATE/users/"), ajuste=None, vivo=_vivo_usuarios),

    _cap("viaja",
         es={"corto": "qué viaja y qué no",
             "titulo": "Qué viaja y qué no",
             "mapa": ((("esta PC", "wh"), ("Obsidian", "c"), ("tu otra PC|otra PC", "wh")),
                      ("el cerebro|cerebro", "el cerebro|cerebro"),
                      ESTADO_TXT + "/ se queda en cada máquina"),
             "puntos": (
                 "El cerebro viaja: memoria, usuarios, skills y wiki llegan a tus otras máquinas "
                 "por Obsidian (o por git, si así lo elegiste).",
                 "Se queda en esta PC " + ESTADO_TXT + "/: ajustes, registros, respaldos y "
                 "llaves (secrets.local). Nunca viaja.",
                 "La memoria propia de Claude Code se guarda en el cerebro, una carpeta "
                 "por persona (motores/claude-code/memoria/<socio>/), así también viaja.",
                 "AGENTS.md y GEMINI.md llevan la memoria de la pestaña solo mientras está "
                 "abierta: al cerrar, Workspace la quita."),
             "apaga": ""},
         en={"corto": "what travels, what stays",
             "titulo": "What travels and what stays",
             "mapa": ((("this PC", "wh"), ("Obsidian", "c"), ("your other PC|other PC", "wh")),
                      ("the brain|brain", "the brain|brain"),
                      ESTADO_TXT + "/ stays on each machine"),
             "puntos": (
                 "The brain travels: memory, users, skills and wiki reach your other machines "
                 "through Obsidian (or git, if you chose it).",
                 "What stays on this PC is " + ESTADO_TXT + "/: settings, logs, backups and "
                 "keys (secrets.local). It never travels.",
                 "Claude Code's own memory is kept in the brain, one folder per person "
                 "(motores/claude-code/memoria/<partner>/), so it travels too.",
                 "AGENTS.md and GEMINI.md carry the tab's memory only while it is open: on "
                 "close, Workspace takes it out."),
             "apaga": ""},
         compruebalo=("estado", ""), ajuste="cerebro.claude_memoria_en_cerebro",
         vivo=_vivo_viaja),

    _cap("toca",
         es={"corto": "qué toca en cada motor",
             "titulo": "Qué toca en cada motor, y qué nunca",
             "mapa": ((("Workspace", "c"), ("config del motor|config", "wh")),
                      ("solo lo mínimo|lo mínimo",),
                      "nunca: tus llaves, tu modelo ni saltarse permisos"),
             "puntos": (
                 "Claude Code: el .claude/settings.local.json de tu cerebro y su tema; si no "
                 "tenías un valor, que guarde tus sesiones 365 días. Lo demás va en cada arranque.",
                 "Codex: tu cerebro como carpeta de confianza. Antigravity: en su settings.json, "
                 "confianza y permisos para tu cerebro y su barra (con respaldo). OpenCode: nada "
                 "fuera del cerebro.",
                 "OpenClaw y Hermes usan un perfil propio de Workspace. El de Hermes se crea sin "
                 "copiar tu .env: el proveedor se conecta en Motores › «cuenta y proveedor».",
                 "Nunca: tus credenciales, tu modelo (salvo que lo elijas) ni modos que se "
                 "saltan los permisos."),
             "apaga": "no se apaga: es lo mínimo para abrir cada motor"},
         en={"corto": "engines: what it touches",
             "titulo": "What it touches in each engine, and what never",
             "mapa": ((("Workspace", "c"), ("engine config|config", "wh")),
                      ("only the minimum|minimum",),
                      "never: your keys, your model or skipping permissions"),
             "puntos": (
                 "Claude Code: your brain's .claude/settings.local.json and its theme; if you "
                 "had no value, keeping your sessions 365 days. The rest goes in at each start.",
                 "Codex: your brain as a trusted folder. Antigravity: in its settings.json, trust "
                 "and permissions for your brain and its status bar (with a backup). OpenCode: "
                 "nothing outside the brain.",
                 "OpenClaw and Hermes use Workspace's own profile. Hermes' is created without "
                 "copying your .env: the provider is connected in Engines › «account and provider».",
                 "Never: your credentials, your model (unless you pick it) or modes that skip "
                 "permissions."),
             "apaga": "can't be turned off: it is the minimum to open each engine"},
         compruebalo=("cerebro", ".claude/settings.local.json"), ajuste=None, vivo=_vivo_toca),

    _cap("red",
         es={"corto": "lo que sale a la red",
             "titulo": "Lo que sale a la red",
             "mapa": ((("el hub|hub", "ok"), ("un agente|agente", "wh"), ("el motor|motor", "dk")),
                      ("nada", "¿versión nueva?|¿nueva?"),
                      "el motor habla con su proveedor: eso es del motor"),
             "filas": (
                 ("al abrir el hub", "nada", "ok"),
                 ("al abrir un agente", "¿hay versión nueva? (git; como mucho cada 6 h)", "c"),
                 ("actualizar, doctor", "Workspace y tus cerebros en git", "c"),
                 ("en Motores", "cada motor revisa si tienes sesión", "c"),
                 ("instalar un motor", "su instalador oficial, si confirmas", "c"),
                 ("crear un agente", "«obtener skills»: GitHub y skills.sh; viene apagado", "c"),
                 ("Google Calendar", "si lo conectas: solo lectura", "c"),
                 ("workspace correo", "tu servidor de correo, al enviar", "c"),
                 ("dictado (Mac)", "baja su modelo una vez; luego es local", "c"),
                 ("en tu PC", "OpenClaw: 127.0.0.1", "ok"),
                 ("proveedor por API", "solo si configuras uno, con tu llave", "c"),
                 ("tu agente", "su motor habla con su proveedor", "dk"),
                 ("nunca salen", "tu memoria, tus notas, los registros", "ok")),
             "apaga": ""},
         en={"corto": "what goes online",
             "titulo": "What goes online",
             "mapa": ((("the hub|hub", "ok"), ("an agent|agent", "wh"), ("the engine|engine", "dk")),
                      ("nothing", "new version?|new?"),
                      "the engine talks to its provider: that's the engine's"),
             "filas": (
                 ("opening the hub", "nothing", "ok"),
                 ("opening an agent", "new version? (git, every 6 h at most)", "c"),
                 ("update, doctor", "Workspace and your brains in git", "c"),
                 ("in Engines", "each engine checks your sign-in", "c"),
                 ("install an engine", "its official installer, if you confirm", "c"),
                 ("creating an agent", "«get skills»: GitHub and skills.sh; off by default", "c"),
                 ("Google Calendar", "if you connect it: read-only", "c"),
                 ("workspace mail", "your mail server, when sending", "c"),
                 ("dictation (Mac)", "gets its model once; then it's local", "c"),
                 ("on your PC", "OpenClaw: 127.0.0.1", "ok"),
                 ("API provider", "only if you set one up, with your key", "c"),
                 ("your agent", "its engine talks to its provider", "dk"),
                 ("never leaves", "your memory, your notes, the logs", "ok")),
             "apaga": ""},
         compruebalo=("estado", "update/"), ajuste="otros.auto_update", vivo=_vivo_red),

    _cap("nohace",
         es={"corto": "lo que no hace",
             "titulo": "Lo que Workspace no hace",
             "mapa": ((("tú abres", "c"), ("tu agente|agente", "ok"), ("Workspace ordena|ordena", "wh")),
                      ("a la vista", "al cerrar, sin IA|sin IA"),
                      "nada corre sin ventana ni de noche"),
             "puntos": (
                 "No hay IA escondida ni en segundo plano: tu agente trabaja en la sesión que "
                 "tienes abierta, frente a ti.",
                 "No programa trabajos de noche ni tareas del sistema: nada de cron, launchd ni "
                 "Programador de tareas.",
                 "No guarda las llaves de tus proveedores: cada motor maneja su cuenta. Las de "
                 "Google Calendar se quedan en el hub; los motores no las reciben.",
                 "Solo usa IA sin ventana si tú lo pides: al personalizar un agente nuevo o con "
                 "workspace evaluar."),
             "apaga": "no se apaga: así está hecho"},
         en={"corto": "what it never does",
             "titulo": "What Workspace does not do",
             "mapa": ((("you open", "c"), ("your agent|agent", "ok"), ("Workspace tidies|tidies", "wh")),
                      ("in plain sight|in sight", "on close, no AI|no AI"),
                      "nothing runs without a window or at night"),
             "puntos": (
                 "No hidden or background AI: your agent works in the session you have open, in "
                 "front of you.",
                 "It schedules no night jobs or system tasks: no cron, no launchd, no Task "
                 "Scheduler.",
                 "It does not keep your providers' keys: each engine handles its own account. "
                 "Google Calendar's stay in the hub; the engines never get them.",
                 "It only uses AI without a window when you ask: personalizing a new agent or "
                 "with workspace eval."),
             "apaga": "can't be turned off: that's how it is built"},
         compruebalo=("estado", "events/"), ajuste=None, vivo=_vivo_nohace),

    _cap("actualizar",
         es={"corto": "actualizar y desinstalar",
             "titulo": "Actualizar y desinstalar",
             "mapa": ((("versión nueva|nueva", "c"), ("¿arranca aquí?|¿arranca?", "wh"), ("al día", "ok")),
                      ("baja", "sí"),
                      "si no arranca, vuelve sola a la anterior"),
             "puntos": (
                 "Al abrir un agente, Workspace busca versión nueva como mucho cada 6 horas y la "
                 "instala. Puedes pedir que solo avise o que no busque.",
                 "Si la versión nueva no arranca en tu PC, vuelve sola a la anterior. Con "
                 "workspace actualizar --rollback regresas tú.",
                 "Si una versión cambia algo en tus cerebros (por ejemplo, las instrucciones de "
                 "memoria), lo hace sola y con respaldo, y solo donde el texto sigue como lo dejó "
                 "Workspace: lo que tú escribiste no se toca. Un agente que cargas después lo "
                 "recibe al cargarlo.",
                 "Desinstalar guarda un zip de la carpeta de estado en tu Escritorio (sin "
                 "sesiones ni llaves) y te ofrece limpiar también los hooks de tus cerebros y lo "
                 "que dejó en cada motor.",
                 "Tus cerebros y tus conversaciones se quedan siempre. Si limpias también los "
                 "motores, las conversaciones de los perfiles de Workspace en OpenClaw y Hermes "
                 "no se borran: se mueven a una carpeta de respaldo junto a cada perfil. "
                 "Reinstalar respeta lo que elegiste, como abrir el hub con la terminal."),
             "apaga": ""},
         en={"corto": "update and uninstall",
             "titulo": "Updating and uninstalling",
             "mapa": ((("new version|new", "c"), ("starts here?|starts?", "wh"), ("up to date", "ok")),
                      ("gets", "yes"),
                      "if it fails to start, it rolls back on its own"),
             "puntos": (
                 "When you open an agent, Workspace checks for a new version at most every 6 "
                 "hours and installs it. You can ask it to only notify you or not to check.",
                 "If the new version does not start on your PC, it goes back to the previous "
                 "one by itself. With workspace update --rollback you go back yourself.",
                 "If a version changes something in your brains (for example, the memory "
                 "instructions), it does it on its own and with a backup, and only where the text "
                 "is still as Workspace left it: what you wrote is left alone. An agent you load "
                 "later gets it when you load it.",
                 "Uninstalling saves a zip of the state folder on your Desktop (without sessions "
                 "or keys) and offers to also clean your brains' hooks and what it left in each "
                 "engine.",
                 "Your brains and your conversations always stay. If you also clean the "
                 "engines, the conversations in Workspace's OpenClaw and Hermes profiles are not "
                 "deleted: they are moved to a backup folder next to each profile. Reinstalling "
                 "respects what you chose, like opening the hub with the terminal."),
             "apaga": ""},
         compruebalo=("comando", "workspace version"), ajuste="otros.auto_update",
         vivo=_vivo_actualizar),

    _cap("ajustes",
         es={"corto": "ajustes",
             "titulo": "Los ajustes que cambian todo lo anterior",
             "mapa": ((("tú eliges|eliges", "c"), ("settings.json", "wh"), ("Workspace", "ok")),
                      ("en esta PC", "lo lee"),
                      "no viajan: cada máquina tiene los suyos"),
             "puntos": (
                 "La apariencia se cambia en Personalización; cada agente, en Agentes; las "
                 "actualizaciones, con workspace actualizar --auto.",
                 "Los demás, desde la carpeta de Workspace: python3 settings.py set <clave> "
                 "on|off (en Windows, python)."),
             "apaga": "no se apaga: aquí se apaga todo lo demás"},
         en={"corto": "settings",
             "titulo": "The settings that change all of the above",
             "mapa": ((("you choose|choose", "c"), ("settings.json", "wh"), ("Workspace", "ok")),
                      ("saved here|here", "reads it|reads"),
                      "they don't travel: each machine has its own"),
             "puntos": (
                 "Appearance is changed in Personalization; each agent, in Agents; updates, with "
                 "workspace update --auto.",
                 "The rest, from the Workspace folder: python3 settings.py set <key> on|off "
                 "(on Windows, python)."),
             "apaga": "can't be turned off: this is where everything else is turned off"},
         compruebalo=("estado", "settings.json"), ajuste=None, vivo=_vivo_ajustes),
)


# ── El mapa de la memoria ───────────────────────────────────────────────────
# Primer renglón de la sección (y la tecla m), su única entrada: desde la
# 0.5.1 ya no está en la portada del hub. Es el árbol REAL del cerebro del
# agente elegido —el agente → sus carpetas → sus archivos, como la vista del
# cerebro de «Agregar agente»— y, abajo, lo que vive fuera (esta PC y la
# conversación de su motor). Cada paso (todo el recorrido, abrir, trabajar,
# cerrar, retomar, personas, motores, aprender) ilumina los archivos que toca,
# con su orden (①②…), su color (lee · escribe · de cada persona ·
# compartido) y qué le pasa a cada uno. docs_mapa.py lo pinta.
#   MAPA_ARBOL / MAPA_FUERA: (id, carpeta, hojas); hoja = (id, ruta, resumen
#   es, resumen en[, solo para el motor «x»]); una ruta con palabras va como
#   {"es": …, "en": …} (mapa_plantilla).
#   MAPA_PASOS: por idioma, titulo, explica y ruta = ((hoja, orden, acción,
#   qué le pasa[, filtro de motor]), …); filtro = «claude-code», «!claude-code»
#   (todos menos ese) o «antigravity».
# Los textos llevan {cerebro} {usuario} {pestana} {motor} {puntero} {como}
# {conversacion_dir} {conversacion} {retoma} {notas} {recibo} {usuarios}:
# mapa_rellenar los cambia por lo real del agente elegido (mapa_valores, solo
# lectura). tests/test_docs_mapa.py falla si una ruta o un comando citado deja
# de existir o si el dibujo no cabe.

#: Lo propio de cada motor en el mapa (rutas y comandos, sin idioma). La
#: carpeta de conversaciones de Claude Code se calcula para el cerebro elegido
#: (session_paths.session_dir).
MOTOR_RUTAS = {
    "claude-code": {"puntero": "CLAUDE.md", "conversacion_dir": "~/.claude/projects/<cerebro>/",
                    "conversacion": "<id>.jsonl", "retoma": "claude --resume <id>",
                    "notas": "workspace memoria nota"},
    "codex": {"puntero": "AGENTS.md", "conversacion_dir": "~/.codex/sessions/AAAA/MM/DD/",
              "conversacion": "rollout-<id>.jsonl", "retoma": "codex resume <id>",
              "notas": "workspace memoria nota"},
    "antigravity": {"puntero": "GEMINI.md",
                    "conversacion_dir": "~/.gemini/antigravity-cli/conversations/",
                    "conversacion": "<id>.db", "retoma": "agy --conversation <id>",
                    "notas": "workspace memoria nota --entrada"},
    "opencode": {"puntero": "AGENTS.md", "conversacion_dir": "opencode export <id>",
                 "conversacion": "", "retoma": "opencode --session <id>",
                 "notas": "workspace memoria nota"},
    # OpenClaw 2026.9+: las conversaciones de cada agente viven en su SQLite
    # (session_continuity._capture_openclaw_export) y la pestaña se retoma con
    # su clave en el perfil de Workspace (engines/openclaw._interactive_argv).
    "openclaw": {"puntero": "AGENTS.md", "conversacion_dir": "~/.openclaw-workspace/agents/<id>/agent/",
                 "conversacion": "openclaw-agent.sqlite",
                 "retoma": "openclaw --profile workspace tui --session <id>",
                 "notas": "workspace memoria nota --tab {pestana} --engine openclaw"},
    "hermes": {"puntero": "AGENTS.md", "conversacion_dir": "hermes sessions export <id>",
               "conversacion": "", "retoma": "hermes --resume <id>",
               "notas": "workspace memoria nota"},
}


_EST = ESTADO_TXT + "/"

#: Las carpetas del cerebro que toca la memoria, en el orden del árbol.
MAPA_ARBOL = (
    ("brain", "BRAIN.md", (
        ("puntero", "{puntero} → BRAIN.md", "la entrada de tu motor", "your engine's entry point"),
        ("lectura", {"es": "orden de lectura", "en": "reading order"}, "BOOT → STATE → índices",
         "BOOT → STATE → indexes"))),
    ("boot", "BOOT/", (
        ("soul", "00-SOUL.md · 01-IDENTITY.md", "quién es tu agente", "who your agent is"),
        ("reglas", "03-RULES.md · 04-BRAIN-MAP.md", "sus reglas y su mapa", "its rules and its map"))),
    ("state", "STATE/", (
        ("memory", "MEMORY.md", "lo que vale para todas las pestañas", "what holds for every tab"),
        ("perfil", "users/{usuario}.md", "tu perfil: cédula y trato", "your profile: ID and manner"),
        ("pestana", "sessions/{usuario}/{pestana}.md", "la memoria de esta pestaña",
         "this tab's memory"),
        ("maleta", "sessions/{usuario}/maleta/{pestana}.md", "lo último de cada motor",
         "the latest from each engine"),
        ("archivo", "sessions/{usuario}/archivo/", "notas viejas, completas", "old notes, whole"),
        ("memarch", "memoria-archivo/", "lo viejo de MEMORY.md", "the old part of MEMORY.md"),
        ("curador", "skill-curator-last.md", "la fecha de la última curación",
         "the date of the last curation"))),
    ("skills", "skills/", (
        ("index", "INDEX-LITE.md", "el catálogo de skills", "the skill catalog"),
        ("skill", {"es": "<categoría>/<skill>/SKILL.md", "en": "<category>/<skill>/SKILL.md"},
         "cada skill y su .usage.json",
         "each skill and its .usage.json"))),
    ("wiki", "wiki/", (
        ("wikiidx", {"es": "index.md → [[notas]]", "en": "index.md → [[notes]]"},
         "conocimiento bajo demanda", "knowledge on demand"),)),
    ("motores", "motores/", (
        ("cmem", "claude-code/memoria/{usuario}/", "la memoria propia de Claude Code",
         "Claude Code's own memory"),)),
    (".claude", ".claude/", (
        ("socio", "socio.local = {usuario}", "quién eres en esta PC (no viaja)",
         "who you are on this PC (stays)"),
        ("hooks", "settings.local.json", "los hooks de Claude Code", "Claude Code's hooks",
         "claude-code"),
        ("entrada", "memoria-entrada/{pestana}.md", "donde Antigravity deja sus notas",
         "where Antigravity leaves its notes", "antigravity"))),
)

#: Lo que vive FUERA del cerebro (no viaja): esta PC y el almacén del motor.
MAPA_FUERA = (
    ("pc", _EST, (
        ("sesiones", "sessions-local.json", "con qué sesión sigue cada pestaña",
         "which session continues each tab"),
        ("recibo", "{recibo}", "el recibo de cada cierre", "each close's receipt"),
        ("respaldo", "transcripts-backup/", "respaldo de las conversaciones",
         "conversation backups"))),
    ("motor", "{motor}", (
        ("conv", "{conversacion_dir}{conversacion}", "la conversación de tu motor",
         "your engine's conversation"),)),
)


def _paso(pid, num, compruebalo, es, en):
    return {"id": pid, "num": num, "compruebalo": compruebalo, "es": es, "en": en}


MAPA_PASOS = (
    _paso("todo", "◆", ("cerebro", ""),
          es={"titulo": "todo el recorrido", "corto": "todo",
              "explica": "Así recuerda tu agente, de principio a fin: al abrir, el motor lee quién "
                         "es y lo que recuerda (①–⑤) y Workspace le da el resumen de la pestaña (⑥); mientras "
                         "trabajan, tu agente anota (⑦); al cerrar, Workspace lee la conversación (⑧) "
                         "y guarda lo último, lo que vale para siempre y lo viejo (⑨–⑪), y en esta PC "
                         "deja el recibo para retomar (⑫).",
              "ruta": (
                  ("puntero", "①", "lee", "{motor} entra por aquí"),
                  ("cmem", "①", "lee", "Claude Code la carga al arrancar", "claude-code"),
                  ("lectura", "②", "lee", "le dice qué leer y en qué orden"),
                  ("soul", "③", "lee", "quién es"),
                  ("reglas", "③", "lee", "sus reglas"),
                  ("memory", "④", "lee", "se lee al arrancar"),
                  ("perfil", "⑤", "lee", "cómo tratarte"),
                  ("pestana", "⑥", "lee", "Workspace la resume"),
                  ("maleta", "⑥", "lee", "lo último de otro motor"),
                  ("hooks", "⑥", "lee", "entrega el resumen", "claude-code"),
                  ("pestana", "⑦", "escribe", "tu agente anota"),
                  ("cmem", "⑦", "escribe", "y guarda lo suyo", "claude-code"),
                  ("conv", "⑧", "lee", "al cerrar, Workspace la lee"),
                  ("maleta", "⑨", "escribe", "queda lo último"),
                  ("memory", "⑩", "escribe", "suben datos y gustos"),
                  ("archivo", "⑪", "escribe", "las notas viejas"),
                  ("memarch", "⑪", "escribe", "lo viejo, si pasa de 200 líneas"),
                  ("recibo", "⑫", "escribe", "el recibo del cierre"),
                  ("sesiones", "⑫", "escribe", "para retomar la próxima vez"))},
          en={"titulo": "the whole path", "corto": "all",
              "explica": "This is how your agent remembers, end to end: on open, the engine reads who "
                         "it is and what it remembers (①–⑤) and Workspace gives it the tab's summary (⑥); while you work, "
                         "your agent takes notes (⑦); on close, Workspace reads the conversation (⑧) and "
                         "saves the latest, what holds for good and the old (⑨–⑪), and on this PC it "
                         "leaves the receipt to resume (⑫).",
              "ruta": (
                  ("puntero", "①", "lee", "{motor} comes in here"),
                  ("cmem", "①", "lee", "Claude Code loads it at start", "claude-code"),
                  ("lectura", "②", "lee", "tells it what to read and in what order"),
                  ("soul", "③", "lee", "who it is"),
                  ("reglas", "③", "lee", "its rules"),
                  ("memory", "④", "lee", "read at start"),
                  ("perfil", "⑤", "lee", "how to treat you"),
                  ("pestana", "⑥", "lee", "Workspace summarizes it"),
                  ("maleta", "⑥", "lee", "the latest from another engine"),
                  ("hooks", "⑥", "lee", "delivers the summary", "claude-code"),
                  ("pestana", "⑦", "escribe", "your agent takes notes"),
                  ("cmem", "⑦", "escribe", "and keeps its own", "claude-code"),
                  ("conv", "⑧", "lee", "on close, Workspace reads it"),
                  ("maleta", "⑨", "escribe", "the latest stays here"),
                  ("memory", "⑩", "escribe", "facts and preferences move up"),
                  ("archivo", "⑪", "escribe", "the old notes"),
                  ("memarch", "⑪", "escribe", "the old part, past 200 lines"),
                  ("recibo", "⑫", "escribe", "the close receipt"),
                  ("sesiones", "⑫", "escribe", "to resume next time"))}),

    _paso("abrir", "1", ("comando", "workspace memoria ver --tab {pestana}"),
          es={"titulo": "abrir", "corto": "abrir",
              "explica": "Al abrir una pestaña pasan dos cosas: {motor} lee solo su identidad y tu "
                         "perfil, en el orden que pide BRAIN.md, y Workspace le arma sin IA el "
                         "resumen de esa pestaña (hasta 5000 caracteres) con lo último que pasó, "
                         "aunque haya sido en otro motor.",
              "ruta": (
                  ("puntero", "①", "lee", "{motor} lo abre al arrancar"),
                  ("cmem", "①", "lee", "Claude Code la carga al arrancar", "claude-code"),
                  ("lectura", "②", "lee", "le dice qué leer"),
                  ("soul", "③", "lee", "quién es"),
                  ("reglas", "③", "lee", "sus reglas"),
                  ("memory", "④", "lee", "lo de todos"),
                  ("perfil", "⑤", "lee", "cómo tratarte"),
                  ("socio", "⑥", "persona", "Workspace sabe que eres {usuario}"),
                  ("pestana", "⑦", "lee", "Workspace la resume, sin IA"),
                  ("maleta", "⑦", "lee", "lo último de otro motor"),
                  ("hooks", "⑧", "lee", "el hook se lo entrega", "claude-code"),
                  ("puntero", "⑧", "lee", "y ahí le llega el resumen", "!claude-code"))},
          en={"titulo": "open", "corto": "open",
              "explica": "When you open a tab two things happen: {motor} reads its identity and your "
                         "profile on its own, in the order BRAIN.md asks for, and Workspace builds "
                         "without AI that tab's summary (up to 5000 characters) with the latest that "
                         "happened, even if it was in another engine.",
              "ruta": (
                  ("puntero", "①", "lee", "{motor} opens it at start"),
                  ("cmem", "①", "lee", "Claude Code loads it at start", "claude-code"),
                  ("lectura", "②", "lee", "tells it what to read"),
                  ("soul", "③", "lee", "who it is"),
                  ("reglas", "③", "lee", "its rules"),
                  ("memory", "④", "lee", "everyone's"),
                  ("perfil", "⑤", "lee", "how to treat you"),
                  ("socio", "⑥", "persona", "Workspace knows you are {usuario}"),
                  ("pestana", "⑦", "lee", "Workspace summarizes it, no AI"),
                  ("maleta", "⑦", "lee", "the latest from another engine"),
                  ("hooks", "⑧", "lee", "the hook delivers it", "claude-code"),
                  ("puntero", "⑧", "lee", "and the summary arrives there", "!claude-code"))}),

    _paso("trabajar", "2", ("cerebro", "STATE/sessions/"),
          es={"titulo": "trabajar", "corto": "trabajar",
              "explica": "Mientras trabajan, tu agente guarda lo importante en el momento con "
                         "{notas}: decisiones y pendientes quedan en «Vigente» hasta que se cierran; "
                         "datos y preferencias, en el historial. Si aprende algo que se repite, lo "
                         "guarda como skill.",
              "ruta": (
                  ("pestana", "①", "escribe", "tu agente anota: decisiones, pendientes, datos"),
                  ("entrada", "①", "escribe", "Antigravity escribe aquí y un comando lo guarda",
                   "antigravity"),
                  ("cmem", "②", "escribe", "Claude Code guarda lo que decide recordar",
                   "claude-code"),
                  ("skill", "③", "escribe", "si aprende algo, lo guarda como skill"))},
          en={"titulo": "work", "corto": "work",
              "explica": "While you work, your agent saves what matters as it happens with {notas}: "
                         "decisions and pending items stay in «Open items» until they are closed; facts "
                         "and preferences, in the history. If it learns something that repeats, it "
                         "saves it as a skill.",
              "ruta": (
                  ("pestana", "①", "escribe", "your agent notes decisions, pending items, facts"),
                  ("entrada", "①", "escribe", "Antigravity writes here and a command saves it",
                   "antigravity"),
                  ("cmem", "②", "escribe", "Claude Code keeps what it decides to remember",
                   "claude-code"),
                  ("skill", "③", "escribe", "if it learns something, it saves it as a skill"))}),

    _paso("cerrar", "3", ("cerebro", "STATE/MEMORY.md"),
          es={"titulo": "cerrar", "corto": "cerrar",
              "explica": "Al cerrar, también con la X, Workspace lee la conversación que guardó "
                         "{motor} y, sin IA, deja la maleta para la próxima vez, sube datos y "
                         "preferencias a lo de todos y archiva lo viejo. En esta PC deja el recibo del "
                         "cierre, un respaldo y con qué sesión retomar.",
              "ruta": (
                  ("conv", "①", "lee", "Workspace la lee, sin IA"),
                  ("maleta", "②", "escribe", "lo último, para la próxima vez"),
                  ("memory", "③", "escribe", "suben datos y preferencias"),
                  ("archivo", "④", "escribe", "si la pestaña creció: notas viejas, completas"),
                  ("memarch", "④", "escribe", "si MEMORY.md pasa de 200 líneas"),
                  ("recibo", "⑤", "escribe", "el recibo del cierre, también si falló"),
                  ("respaldo", "⑤", "escribe", "un respaldo de la conversación"),
                  ("sesiones", "⑥", "escribe", "con qué sesión retomar"))},
          en={"titulo": "close", "corto": "close",
              "explica": "When you close, even with the X, Workspace reads the conversation {motor} "
                         "kept and, without AI, leaves the handoff for next time, moves facts and "
                         "preferences up to everyone's and archives the old. On this PC it leaves the "
                         "close receipt, a backup and which session to resume.",
              "ruta": (
                  ("conv", "①", "lee", "Workspace reads it, no AI"),
                  ("maleta", "②", "escribe", "the latest, for next time"),
                  ("memory", "③", "escribe", "facts and preferences move up"),
                  ("archivo", "④", "escribe", "if the tab grew: old notes, whole"),
                  ("memarch", "④", "escribe", "if MEMORY.md goes over 200 lines"),
                  ("recibo", "⑤", "escribe", "the close receipt, also if it failed"),
                  ("respaldo", "⑤", "escribe", "a backup of the conversation"),
                  ("sesiones", "⑥", "escribe", "which session to resume"))}),

    _paso("retomar", "4", ("estado", ""),
          es={"titulo": "retomar", "corto": "retomar",
              "explica": "La próxima vez, en esta PC Workspace sabe con qué sesión de {motor} sigue la "
                         "pestaña y la retoma. Si abres en otro motor u otra PC, tu agente arranca con "
                         "la maleta y el resumen de siempre.",
              "ruta": (
                  ("sesiones", "①", "lee", "Workspace busca la sesión de «{pestana}»"),
                  ("conv", "②", "lee", "{motor} la retoma: {retoma}"),
                  ("maleta", "③", "lee", "en otro motor u otra PC: lo último"),
                  ("pestana", "③", "lee", "y el resumen de siempre"))},
          en={"titulo": "resume", "corto": "resume",
              "explica": "Next time, on this PC Workspace knows which {motor} session continues the tab "
                         "and resumes it. If you open in another engine or on another PC, your agent "
                         "starts from the handoff and the usual summary.",
              "ruta": (
                  ("sesiones", "①", "lee", "Workspace finds «{pestana}»'s session"),
                  ("conv", "②", "lee", "{motor} resumes it: {retoma}"),
                  ("maleta", "③", "lee", "in another engine or PC: the latest"),
                  ("pestana", "③", "lee", "and the usual summary"))}),

    _paso("personas", "5", ("cerebro", "STATE/users/"),
          es={"titulo": "cada persona", "corto": "personas",
              "explica": "Cada PC dice quién la usa. Con eso Workspace carga solo tus pestañas y tu "
                         "perfil; las de los demás ({usuarios}) están en el mismo cerebro, pero tu "
                         "agente no las carga. Quién es, la memoria de todos y las skills son "
                         "compartidas.",
              "ruta": (
                  ("socio", "①", "persona", "esta PC es de {usuario}"),
                  ("perfil", "②", "persona", "tu perfil, junto a los de los demás"),
                  ("pestana", "③", "persona", "tus pestañas, en tu carpeta"),
                  ("maleta", "③", "persona", "tu maleta"),
                  ("cmem", "④", "persona", "tu memoria de Claude Code", "claude-code"),
                  ("memory", "·", "compartido", "de todos"),
                  ("soul", "·", "compartido", "el mismo para todos"),
                  ("index", "·", "compartido", "de todos"))},
          en={"titulo": "each person", "corto": "people",
              "explica": "Each PC says who uses it. With that Workspace loads only your tabs and your "
                         "profile; everyone else's ({usuarios}) are in the same brain, but your agent "
                         "does not load them. Who it is, everyone's memory and the skills are shared.",
              "ruta": (
                  ("socio", "①", "persona", "this PC belongs to {usuario}"),
                  ("perfil", "②", "persona", "your profile, next to everyone else's"),
                  ("pestana", "③", "persona", "your tabs, in your folder"),
                  ("maleta", "③", "persona", "your handoff"),
                  ("cmem", "④", "persona", "your Claude Code memory", "claude-code"),
                  ("memory", "·", "compartido", "everyone's"),
                  ("soul", "·", "compartido", "the same for everyone"),
                  ("index", "·", "compartido", "everyone's"))}),

    _paso("motores", "6", ("cerebro", ".workspace/agent.json"),
          es={"titulo": "los motores", "corto": "motores",
              "explica": "Los seis motores leen el mismo cerebro y la misma memoria; solo cambia por "
                         "dónde entra el resumen y dónde guarda cada uno su conversación. En el árbol, "
                         "{motor}; abajo, los seis:",
              "ruta": (
                  ("puntero", "①", "lee", "{motor} entra por aquí"),
                  ("hooks", "②", "lee", "el resumen entra por el hook de inicio", "claude-code"),
                  ("puntero", "②", "lee", "el resumen va en un bloque mientras está abierta",
                   "!claude-code"),
                  ("conv", "③", "lee", "aquí guarda {motor} su conversación"),
                  ("sesiones", "④", "lee", "retoma: {retoma}"),
                  ("cmem", "·", "compartido", "solo Claude Code tiene memoria propia aquí",
                   "claude-code"))},
          en={"titulo": "the engines", "corto": "engines",
              "explica": "All six engines read the same brain and the same memory; only where the "
                         "summary comes in and where each keeps its conversation change. In the tree, "
                         "{motor}; below, all six:",
              "ruta": (
                  ("puntero", "①", "lee", "{motor} comes in here"),
                  ("hooks", "②", "lee", "the summary comes in through the start hook", "claude-code"),
                  ("puntero", "②", "lee", "the summary goes in a block while it is open",
                   "!claude-code"),
                  ("conv", "③", "lee", "{motor} keeps its conversation here"),
                  ("sesiones", "④", "lee", "resumes: {retoma}"),
                  ("cmem", "·", "compartido", "only Claude Code has its own memory here",
                   "claude-code"))}),

    _paso("aprende", "7", ("cerebro", "skills/"),
          es={"titulo": "lo que aprende", "corto": "aprende",
              "explica": "Si algo se repite o le corriges cómo hacerlo, tu agente lo guarda como skill, "
                         "sin pedir permiso, y te lo cuenta. Una vez por semana las cura: las que no se "
                         "usan quedan archivadas; nada se borra. También completa quién es con lo que "
                         "le cuentas.",
              "ruta": (
                  ("index", "①", "lee", "antes de una tarea, revisa el catálogo"),
                  ("skill", "②", "escribe", "crea o mejora, sin pedir permiso"),
                  ("curador", "③", "lee", "una vez por semana toca curar"),
                  ("skill", "④", "escribe", "sin uso: status: archivada"),
                  ("soul", "⑤", "escribe", "completa quién es con lo que le cuentas"))},
          en={"titulo": "what it learns", "corto": "learns",
              "explica": "If something repeats or you correct how to do it, your agent saves it as a "
                         "skill, without asking, and tells you. Once a week it curates them: the unused "
                         "ones are archived; nothing is deleted. It also completes who it is with what "
                         "you tell it.",
              "ruta": (
                  ("index", "①", "lee", "before a task, it checks the catalog"),
                  ("skill", "②", "escribe", "creates or improves, without asking"),
                  ("curador", "③", "lee", "once a week it is time to curate"),
                  ("skill", "④", "escribe", "unused: status: archivada"),
                  ("soul", "⑤", "escribe", "completes who it is with what you tell it"))}),
)

#: El renglón del mapa en la lista de la sección (antes del capítulo 1) y lo
#: que se ve a la derecha mientras está elegido. Con la tecla m, es la única
#: forma de abrir el mapa (el hub ya no lo ofrece en su portada).
MAPA_INTRO = {
    "es": {"corto": "el mapa de la memoria",
           "titulo": "Cómo recuerda tu agente",
           "mapa": ((("tu agente", "c"), ("su cerebro|cerebro", "wh"), ("sus archivos|archivos", "ok")),
                    ("→", "→"),
                    "el árbol real, paso a paso y en colores"),
           "puntos": (
               "El árbol real del cerebro del agente elegido, como en «Agregar agente», con lo que "
               "vive fuera: esta PC y la conversación de su motor.",
               "Cada paso ilumina los archivos que toca, en orden (①②…) y en colores: lo que se lee, "
               "lo que se escribe y lo que es de cada persona. ← → cambia de paso; Tab, de agente."),
           "abre": "Enter o m: abre el mapa"},
    "en": {"corto": "the memory map",
           "titulo": "How your agent remembers",
           "mapa": ((("your agent", "c"), ("its brain|brain", "wh"), ("its files|files", "ok")),
                    ("→", "→"),
                    "the real tree, step by step and in colors"),
           "puntos": (
               "The real brain tree of the chosen agent, as in «Add agent», with what lives outside: "
               "this PC and its engine's conversation.",
               "Each step lights up the files it touches, in order (①②…) and in colors: what is read, "
               "what is written and what belongs to each person. ← → changes step; Tab, agent."),
           "abre": "Enter or m: opens the map"},
}

#: El paso «los motores» del mapa: cómo vive la memoria cada uno de los seis,
#: en el orden de MOTORES. Columnas («largo|corto»; la tabla usa la corta): abre
#: (cómo recibe el paquete) · notas (cómo guarda) · cierra (de dónde lee
#: Workspace su conversación al cerrar) · retoma; `detalle` = la explicación.
def _motor(mid, nombre, es, en):
    return {"id": mid, "nombre": nombre, "compruebalo": ("cerebro", ""), "es": es, "en": en}


MAPA_MOTORES = (
    _motor("claude-code", "Claude Code",
           es={"abre": "su hook de inicio", "notas": "workspace memoria nota",
               "cierra": "su conversación (.jsonl)", "retoma": "--resume <id>",
               "detalle": "Lee CLAUDE.md, que apunta a BRAIN.md, y recibe el paquete por su hook "
                          "de inicio, también al retomar y al compactar. En cada mensaje recibe "
                          "tu tono. Al cerrar, Workspace lee su conversación y arma la maleta. "
                          "Su memoria propia vive en el cerebro, una carpeta por persona."},
           en={"abre": "its start hook", "notas": "workspace memoria nota",
               "cierra": "its conversation (.jsonl)", "retoma": "--resume <id>",
               "detalle": "It reads CLAUDE.md, which points to BRAIN.md, and gets the package "
                          "through its start hook, also when resuming and compacting. With each "
                          "message it gets your tone. On close, Workspace reads its "
                          "conversation and packs the handoff. Its own memory lives in the "
                          "brain, one folder per person."}),
    _motor("codex", "Codex",
           es={"abre": "bloque en AGENTS.md", "notas": "workspace memoria nota",
               "cierra": "su registro de la sesión|su registro", "retoma": "codex resume <id>",
               "detalle": "Lee AGENTS.md, que apunta a BRAIN.md. Mientras la pestaña está "
                          "abierta, Workspace le agrega ahí el paquete y lo quita al cerrar. "
                          "Guarda notas desde su terminal protegida. Al cerrar, Workspace "
                          "busca su registro de esa sesión y arma la maleta."},
           en={"abre": "block in AGENTS.md", "notas": "workspace memoria nota",
               "cierra": "its session log|its log", "retoma": "codex resume <id>",
               "detalle": "It reads AGENTS.md, which points to BRAIN.md. While the tab is open, "
                          "Workspace adds the package there and removes it on close. It saves "
                          "notes from its protected terminal. On close, Workspace finds the log "
                          "of that session and packs the handoff."}),
    _motor("antigravity", "Antigravity",
           es={"abre": "bloque en GEMINI.md", "notas": "bandeja + comando fijo|bandeja",
               "cierra": "su conversación guardada|su conversación",
               "retoma": "--conversation <id>",
               "detalle": "Workspace le arma GEMINI.md al abrir, con la ruta de tu cerebro y el "
                          "paquete, y lo deja como estaba al cerrar. Escribe sus notas en "
                          ".claude/memoria-entrada/<pestaña>.md y las guarda con un comando "
                          "fijo. Al cerrar, Workspace copia su conversación y arma la maleta."},
           en={"abre": "block in GEMINI.md", "notas": "tray + fixed command|tray",
               "cierra": "its saved conversation|its conversation",
               "retoma": "--conversation <id>",
               "detalle": "Workspace builds its GEMINI.md on open, with your brain's path and "
                          "the package, and leaves it as it was on close. It writes its notes "
                          "in .claude/memoria-entrada/<tab>.md and saves them with a fixed "
                          "command. On close, Workspace copies its conversation and packs the "
                          "handoff."}),
    _motor("opencode", "OpenCode",
           es={"abre": "bloque en AGENTS.md", "notas": "workspace memoria nota",
               "cierra": "su exportación oficial|exportación", "retoma": "--session <id>",
               "detalle": "Lee AGENTS.md con el paquete mientras la pestaña está abierta. "
                          "Guarda notas con workspace memoria nota. Al cerrar, Workspace "
                          "exporta la conversación con el comando oficial de OpenCode y arma "
                          "la maleta."},
           en={"abre": "block in AGENTS.md", "notas": "workspace memoria nota",
               "cierra": "its official export|export", "retoma": "--session <id>",
               "detalle": "It reads AGENTS.md with the package while the tab is open. It saves "
                          "notes with workspace memoria nota. On close, Workspace exports the "
                          "conversation with OpenCode's official command and packs the "
                          "handoff."}),
    _motor("openclaw", "OpenClaw",
           es={"abre": "bloque en AGENTS.md", "notas": "nota con su pestaña|nota --tab",
               "cierra": "su sesión exportada|su sesión", "retoma": "--session <clave>",
               "detalle": "Usa un perfil propio de Workspace y lee AGENTS.md con el paquete. "
                          "Como sus comandos corren en un servicio compartido, guarda notas "
                          "diciendo la pestaña (workspace memoria nota --tab --engine). Su "
                          "memoria propia está apagada; lo que deje suelto se mueve a "
                          "motores/openclaw/."},
           en={"abre": "block in AGENTS.md", "notas": "note with its tab|note --tab",
               "cierra": "its exported session|its session", "retoma": "--session <key>",
               "detalle": "It uses Workspace's own profile and reads AGENTS.md with the "
                          "package. Since its commands run in a shared service, it saves notes "
                          "naming the tab (workspace memoria nota --tab --engine). Its own "
                          "memory is off; whatever it leaves loose moves to motores/openclaw/."}),
    _motor("hermes", "Hermes",
           es={"abre": "AGENTS.md con copia|AGENTS.md", "notas": "workspace memoria nota",
               "cierra": "su sesión exportada|su sesión", "retoma": "--resume <id>",
               "detalle": "Usa un perfil propio de Workspace, con su memoria propia apagada. Su "
                          "AGENTS.md lleva una copia de la identidad y de tu perfil, y el "
                          "paquete mientras la pestaña está abierta; si su filtro de seguridad "
                          "lo frena, arranca sin él. Recibe tu tono en cada mensaje. Al cerrar, "
                          "Workspace exporta la sesión y arma la maleta."},
           en={"abre": "AGENTS.md with a copy|AGENTS.md", "notas": "workspace memoria nota",
               "cierra": "its exported session|its session", "retoma": "--resume <id>",
               "detalle": "It uses Workspace's own profile, with its own memory off. Its "
                          "AGENTS.md carries a copy of the identity and of your profile, plus "
                          "the package while the tab is open; if its safety filter stops it, it "
                          "starts without it. It gets your tone with each message. On close, "
                          "Workspace exports the session and packs the handoff."}),
)

def mapa_texto(parte, lg=None):
    """El texto de un paso del mapa, de un motor o de MAPA_INTRO en el idioma
    `lg` (o el activo)."""
    lg = lg or lang()
    return parte[lg] if lg in LANGS else parte["es"]


def mapa_plantilla(hoja, lg=None):
    """La ruta de una hoja del árbol en el idioma `lg` (o el activo): casi
    todas son iguales en los dos; las que llevan palabras, {"es": …, "en": …}."""
    p = hoja[1]
    if isinstance(p, dict):
        return p.get(lg or lang()) or p["es"]
    return p


def mapa_valores(ctx=None, lg=None):
    """Lo real del agente elegido para el mapa: su carpeta, tu usuario, tu
    última pestaña, los demás usuarios del cerebro y lo propio de su motor. SOLO
    LECTURA (jamás crea ni escribe nada) y falla-suave: lo que no se sabe
    queda como <tú>, <pestaña>…"""
    import hashlib
    lg = lg or lang()
    en = lg == "en"
    v = {"cerebro": "<your agent>/" if en else "<tu agente>/", "usuario": "<you>" if en else "<tú>",
         "pestana": "<tab>" if en else "<pestaña>", "motor": "<engine>" if en else "<su motor>",
         "recibo": "continuity/<…>.json"}
    v["usuarios"] = "<the others>" if en else "<los demás>"
    eng = str((ctx or {}).get("engine") or "")
    rutas = MOTOR_RUTAS.get(eng) or {}
    v["puntero"] = rutas.get("puntero") or "CLAUDE.md · AGENTS.md · GEMINI.md"
    v["retoma"] = rutas.get("retoma") or "--resume <id>"
    v["notas"] = rutas.get("notas") or "workspace memoria nota"
    v["conversacion_dir"] = rutas.get("conversacion_dir") or ("<its folder>" if en else "<su carpeta>")
    v["conversacion"] = rutas.get("conversacion") or ""
    v["motor"] = next((n for i, n, _p in MOTORES if i == eng), v["motor"])
    m = next((x for x in MAPA_MOTORES if x["id"] == eng), None)
    v["como"] = str(m[lg]["abre"]).partition("|")[0] if m else (
        "its start hook or AGENTS.md" if en else "su hook o AGENTS.md")
    b = _brain(ctx)
    if not b:
        return v
    try:
        v["cerebro"] = corto(b).rstrip("/\\") + "/"
        soc = _socio(b)
        if soc:
            v["usuario"] = soc
        tabs = _pestanas(b)
        if tabs:
            v["pestana"] = tabs[0][0]
        try:
            gente = sorted(f[:-3] for f in os.listdir(os.path.join(b, "STATE", "users"))
                           if f.endswith(".md") and not f.startswith(("_", ".")) and f.lower() != "readme.md")
        except OSError:
            gente = []
        otros = [g for g in gente if g.lower() != str(v["usuario"]).lower()]
        v["usuarios"] = " · ".join(otros) if otros else (
            "nobody else, for now" if en else "nadie más, por ahora")
        if eng == "claude-code":
            import session_paths
            v["conversacion_dir"] = corto(session_paths.session_dir(b)).rstrip("/\\") + "/"
        if tabs and eng:
            # la sesión del motor que sigue esta pestaña en esta PC (solo lee)
            import sessions_registry as reg
            rid = reg.resume_id(b, str((ctx or {}).get("name") or ""), tabs[0][0], eng)
            if rid:
                corto_id = rid if len(rid) <= 12 else rid[:8] + "…"
                for k in ("conversacion", "retoma", "conversacion_dir"):
                    v[k] = v[k].replace("<id>", corto_id)
        clave = hashlib.sha256(os.path.realpath(b).encode()).hexdigest()
        v["recibo"] = "continuity/%s….json" % clave[:8]
    except Exception:
        pass
    return v


_LLAVE = re.compile(r"\{(\w+)\}")


def mapa_rellenar(texto, valores):
    """`{usuario}` → lo real (o se deja tal cual si no hay valor)."""
    return _LLAVE.sub(lambda m: str(valores.get(m.group(1), m.group(0))), str(texto))


# ── API para la pantalla ────────────────────────────────────────────────────
def capitulos():
    return CAPITULOS


def texto(cap, lg=None):
    """El texto del capítulo en el idioma `lg` (o el activo); EN cae a ES."""
    lg = lg or lang()
    return cap.get(lg) or cap["es"]


def ajustes(lg=None):
    """[(etiqueta, «de fábrica · clave»)] del capítulo de ajustes."""
    i = 1 if (lg or lang()) == "en" else 0
    return [(lab[i], "%s · %s" % (pal[i], clave)) for lab, pal, clave, _d in AJUSTES_CLAVE]


def filas(cap, lg=None):
    """Las filas «cuándo → qué» del capítulo (la red) o «ajuste → de fábrica ·
    clave» (los ajustes): [(clave, valor, color)]."""
    if cap["id"] == "ajustes":
        return [(a, b, "wh") for a, b in ajustes(lg)]
    return list(texto(cap, lg).get("filas") or ())


def apaga(cap, lg=None):
    """La línea de «se apaga en»: el ajuste con su nombre humano, o el «no se
    apaga: …» del capítulo."""
    lg = lg or lang()
    k = cap.get("ajuste")
    if k:
        lab = AJUSTE_ETIQUETA.get(k, (k, k))[1 if lg == "en" else 0]
        return "%s · %s" % (lab, k)
    return texto(cap, lg).get("apaga") or NADA


def ultima_pestana(ctx):
    tabs = _pestanas(_brain(ctx))
    return tabs[0][0] if tabs else ""


def comando(cap, ctx=None, completo=False):
    """El comando de «compruébalo» listo para copiar: con la pestaña real y,
    si `completo`, con --brain (desde otra carpeta no sabría qué cerebro)."""
    kind, target = cap["compruebalo"]
    if kind != "comando":
        return ""
    tab = ultima_pestana(ctx) if ctx else ""
    cmd = target.replace("{pestana}", tab or _t("docs.tab_ph", "<pestaña>", "<tab>"))
    b = _brain(ctx)
    if completo and b and "{pestana}" in target:
        cmd += ' --brain "%s"' % b
    return cmd


def ruta(cap, ctx=None):
    """Ruta absoluta de «compruébalo» (archivo o carpeta) o '' si es un
    comando o falta el agente."""
    kind, target = cap["compruebalo"]
    if kind == "cerebro":
        b = _brain(ctx)
        return os.path.join(b, *[p for p in target.split("/") if p]) if b else ""
    if kind == "estado":
        return os.path.join(estado_dir(), *[p for p in target.split("/") if p])
    return ""


def mostrar(cap, ctx=None, lg=None):
    """Cómo se ve «compruébalo» en pantalla (corto, sin --brain)."""
    kind, target = cap["compruebalo"]
    if kind == "comando":
        return comando(cap, ctx)
    if kind == "cerebro":
        return target or _t("docs.brain_folder", "la carpeta del cerebro", "the brain folder")
    return ESTADO_TXT + "/" + target


def en_esta_pc(cap, ctx=None):
    """La línea de «en esta PC». SOLO LECTURA; jamás levanta."""
    try:
        v = cap["vivo"](ctx or {})
        return str(v) if v else NADA
    except Exception:
        return NADA


if __name__ == "__main__":
    # Vista en texto de todos los capítulos (para revisar sin abrir el hub).
    for n, c in enumerate(CAPITULOS, 1):
        tx = texto(c)
        print("%2d. %s" % (n, tx["titulo"]))
        for p in tx.get("puntos") or ():
            print("    · " + p)
        for k, v, _tono in tx.get("filas") or ():
            print("    · %s: %s" % (k, v))
        print("    compruébalo: %s · se apaga en: %s" % (mostrar(c), apaga(c)))
