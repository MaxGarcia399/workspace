#!/usr/bin/env python3
"""WORKSPACE hook · revisión de skills — la hace el AGENTE, en su sesión, a la vista.

Hasta 2026-10-16 este hook lanzaba, al cerrar la sesión, un revisor SIN VENTANA
(`claude -p`, `codex exec`, `agy -p`) en segundo plano, y las skills nuevas se
quedaban en skills/_propuestas/ esperando que alguien las aprobara. El dueño
retiró ese diseño: en la máquina del cliente no corre ningún agente sin
ventana, y el proceso de memoria/skills no espera aprobación humana.

Ahora son dos momentos, y ninguno lanza procesos:
  · AL CERRAR (`main`, evento session_end): si la opción está encendida y la
    sesión tuvo sustancia (lo que se HABLÓ, contado en la vista neutral; no el
    tamaño del transcript), guarda una VISTA NEUTRA de la sesión (sin thinking,
    sin tools, sin el crudo del vendor) y deja la revisión PENDIENTE en la
    COLA de ESA pestaña (0.9.1: antes la tomaba la primera sesión que abriera,
    de cualquier pestaña o motor; y una repetición y una nueva conviven, a lo
    más COLA_MAX por pestaña y MAX_PENDIENTES por cerebro). Todo en
    `<cerebro>/.claude/skill-review/` (carpeta oculta: Obsidian no la
    sincroniza y queda en el .gitignore del cerebro). La vista vive hasta que
    se revisa o vence (VENCE_SECONDS, 7 días).
  · AL ABRIR (`start_main`, evento session_start, vía skill_review_start.py):
    si esa pestaña tiene una revisión pendiente, se la entrega al agente como
    parte de su contexto de arranque. El agente la hace en esa sesión, a la
    vista del socio y con su misma cuenta, y la REPORTA (`workspace revision
    resultado …` o la herramienta revision_resultado). Se entrega UNA vez. La
    limpieza de vistas nunca borra la de un pendiente ni una de menos de
    PODA_MIN_SECONDS, y un pendiente sin vista no se gasta: queda con rastro
    en <estado>/logs/skill-review.log y caduca a las 24 h (SIN_VISTA_SECONDS)
    si la vista no aparece.
  · SE COMPRUEBA (0.9.1): cuando termina la sesión que la recibió (o, si se
    cayó, al volver a abrir la pestaña). Cuenta el reporte, cruzado con ESE
    SKILL.md (cambió después de la entrega y lo escribió esa sesión); sin
    reporte, solo el bloque 🧠 exacto que pide la tarea, dicho DESPUÉS de la
    entrega. Si no hubo resultado, la revisión vuelve a pendiente UNA vez
    («repetida») y el hub la muestra: «1 revisión de skills pendiente · Hacer
    ahora». La segunda sin resultado queda «no se hizo»; la que nadie cierra
    vence a los 7 días. Todo se anota en Decisores («¿pasó?») si la decisión
    vino de ahí.
  · Todo lo que toca los pendientes va bajo el candado del cerebro
    (`.claude/locks/`, olock.local_lock): dos cierres a la vez, o un cierre y
    un arranque, ya no se pisan (revisor 0.9.0, #18).

La opción NO cambia: viene apagada; `"skill_review": true|false` en el
agent.json del agente gana; si no dice nada, manda `hooks.skill_review`
(settings); WORKSPACE_NO_SKILL_REVIEW=1 gana siempre. Throttle por cerebro
(máx. una cada 2 h) y las sesiones triviales no se revisan.

Las skills NUEVAS se crean directo en skills/<categoría>/ (como ya hace el
Skill Loop durante la conversación; quedan en el git del cerebro para
deshacer). Si quedaron propuestas viejas en skills/_propuestas/, la revisión
pide integrarlas (copiándolas, sin comandos que el motor pregunte) y marcarlas
resueltas; sin_aprobacion las archiva en skills/_archive/: nada espera a un
humano.

Guard N6 (LOG-ONLY): la sesión es contenido NO confiable; antes de guardar la
vista se pasa por hooks/untrusted.py (findings a untrusted-findings/, jamás
aborta) y la tarea lleva la cláusula de endurecimiento. Probar sin escribir:
WORKSPACE_REVIEW_DRYRUN=1. Cero deps (stdlib, 3.9+). Mac y Windows.
"""
import sys, os, json, time, datetime, re, uuid, hashlib

try:   # Windows: UTF-8 en stdout/err (un hook capturado en cp1252 reventaría).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# hooks/ al FINAL del path: importado desde el hub (la fila «Hacer ahora»), un
# hooks/ al principio taparía módulos de la raíz con el mismo nombre
# (personalidad.py); corrido como hook, su carpeta ya es sys.path[0]
if os.path.dirname(os.path.abspath(__file__)) not in sys.path:
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
try:
    import untrusted
except Exception:
    untrusted = None

SKIP_REASONS = {"resume"}            # no revisar en continuaciones de sesión
MIN_TRANSCRIPT_LINES = 25            # (histórico) tamaño de un transcript «con sustancia»
#: Sesión trivial (0.9.1): se mide en la VISTA NEUTRAL — lo que se habló —, no
#: en las líneas crudas del transcript (una sesión de Copilot de 2 mensajes,
#: «inicia el cerebro» / «cerebro iniciado», pasaba el filtro de 25 líneas).
MIN_VISTA_LINEAS = 8
MIN_TURNOS_SOCIO = 2
#: Una vista más nueva que esto no se poda: un cierre lento (esperando al
#: decisor) todavía no escribió su pendiente (revisor 0.9.0, #18).
PODA_MIN_SECONDS = 120
#: Cuántas veces se entrega una revisión sin resultado (la 2.ª es la última).
INTENTOS = 2
#: Un pendiente (o una entrega que nunca se cerró) vence a los 7 días: se
#: retira y se borra su vista (es la conversación en texto). El mismo freno
#: de la v2 del diseño (revisor 0.9.1, P2).
VENCE_SECONDS = 7 * 24 * 3600
#: Cola por pestaña: la repetición y lo nuevo conviven (revisor 0.9.1, P1),
#: hasta este tope; y como mucho MAX_PENDIENTES por cerebro (cada uno guarda
#: su vista). Lo que pasa del tope se retira, el más viejo primero.
COLA_MAX = 3
MAX_PENDIENTES = 8
#: Holgura entre la hora de la entrega y la del transcript (relojes, escritura).
HOLGURA_S = 5
#: Candado de todo lo que toca los pendientes de un cerebro.
CANDADO_CIERRE_S = 5.0
CANDADO_ABRIR_S = 2.0
THROTTLE_SECONDS = 2 * 3600          # máx 1 revisión por cerebro cada 2 h
KEEP_VIEWS = 3                       # vistas viejas que se conservan por cerebro
REVIEW_DIR = os.path.join(".claude", "skill-review")   # dentro del cerebro
PROPUESTAS = os.path.join("skills", "_propuestas")


def _stdin():
    """Lector único de los hooks (_utf8, en la raíz): BYTES → UTF-8 (en
    Windows stdin es cp1252 y una ruta con «José» llegaba rota)."""
    try:
        _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if _root not in sys.path:
            sys.path.append(_root)
        import _utf8
        return _utf8.json_de_stdin()
    except Exception:
        return {}


def _state_dir():
    """Dir de estado per-máquina (paths.py en la raíz de WORKSPACE)."""
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _root not in sys.path:
        sys.path.append(_root)
    import paths
    return paths.state_dir()


def _throttle_path(brain):
    enc = re.sub(r"[^a-zA-Z0-9]", "-", brain)
    return os.path.join(_state_dir(), "review-throttle", enc + ".stamp")


def _review_dir(brain):
    return os.path.join(brain, REVIEW_DIR)


def _pending_path(brain, clave="", pid=""):
    """Un pendiente de la COLA de una pestaña (`clave`, `pid`); sin pestaña,
    `pending.json` (el de siempre: lo toma la primera sesión que abra, como
    antes de la 0.9.1)."""
    if not clave:
        return os.path.join(_review_dir(brain), "pending.json")
    return os.path.join(_review_dir(brain), "pending-%s~%s.json" % (clave, _limpio(pid, 24)))


def _clave_de(nombre):
    """La pestaña de un archivo `pending-<clave>~<id>.json` o `delivered-<clave>.json`."""
    n = os.path.basename(str(nombre))
    for pre in ("pending", "delivered"):
        if n.startswith(pre) and n.endswith(".json"):
            return n[len(pre):-len(".json")].lstrip("-").split("~")[0]
    return ""


def _pendientes(brain):
    """[(ruta, clave, registro)] de los pendientes legibles del cerebro, del
    más viejo al más nuevo (los ilegibles quedan fuera)."""
    d = _review_dir(brain)
    try:
        nombres = [n for n in os.listdir(d) if n.startswith("pending") and n.endswith(".json")]
    except OSError:
        return []
    out = []
    for n in nombres:
        rec, est = _leer_json(os.path.join(d, n))
        if est == "ok":
            out.append((os.path.join(d, n), _clave_de(n), rec))
        elif est != "no_existe":
            _aviso_cola(brain, "pendiente_no_legible")
    out.sort(key=lambda x: float(x[2].get("t") or 0))
    return out


def _cola(brain, clave):
    """La cola de una pestaña: la repetición primero (es la última vez), luego
    lo más viejo."""
    cola = [x for x in _pendientes(brain) if x[1] == clave
            and os.path.basename(x[0]) != "pending.json"]
    return sorted(cola, key=lambda x: (not x[2].get("repetida"), float(x[2].get("t") or 0)))


def _delivered_path(brain, clave=""):
    """La revisión ENTREGADA a una pestaña, esperando su comprobación."""
    return os.path.join(_review_dir(brain), "delivered%s.json" % (("-" + clave) if clave else ""))


def _limpio(x, tope=60):
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(x or "").strip())[:tope]


def pestana_actual(data=None, env=None):
    """La pestaña de esta sesión: {wid, nombre, agente, motor, sesion}. La
    exporta Workspace al abrirla (WORKSPACE_WID / WORKSPACE_WS); sin ellas
    (un motor sin pestaña, una prueba) queda vacía y la revisión es «sin
    pestaña», la de siempre."""
    env = os.environ if env is None else env
    data = data if isinstance(data, dict) else {}
    return {"review_key": str(env.get("WORKSPACE_REVIEW_SOURCE_KEY") or "")
            if env.get("WORKSPACE_REVIEW_BATCH") else "",
            "wid": str(env.get("WORKSPACE_WID") or "").strip(),
            "nombre": str(env.get("WORKSPACE_WS") or env.get("ZENITH_WS")
                          or data.get("tab") or "").strip(),
            "agente": str(env.get("WORKSPACE_AGENT_NAME") or "").strip(),
            "motor": str(data.get("engine") or env.get("WORKSPACE_SESSION_ENGINE")
                         or "claude-code").strip(),
            "sesion": str(data.get("session_id") or "").strip()}


def clave_pestana(p):
    """La clave del pendiente de una pestaña: su id estable (WORKSPACE_WID, el
    mismo con que el hub la abre); si no, su nombre; sin pestaña, ''."""
    if p.get("review_key") and re.fullmatch(r"[A-Za-z0-9._-]{1,70}", p["review_key"]):
        return p["review_key"]
    if p.get("wid"):
        return "w-" + _limpio(p["wid"])
    if p.get("nombre"):
        return "n-" + _limpio(p["nombre"].lower())
    return ""


#: El monito de escritorio (ronda 2, E1-a, decisión del dueño 22-nov): en su conversación (WORKSPACE_VIA=escritorio,
#: su pestaña «escritorio») la revisión NUNCA se entrega: el socio pidió otra cosa desde una burbuja y cada paso de la
#: tarea le salía como una tarjeta de permiso (3 con un agente, casi 2 minutos antes de empezar lo que pidió). Se queda
#: para la próxima vez que ese agente abra en su terminal o en la página, que la adoptan (_adoptar_del_monito).
MONITO = "escritorio"


def en_monito(data=None, env=None):
    """¿Esta sesión es la conversación del monito de escritorio? Lo dice el entorno de su pestaña (WORKSPACE_VIA, o su
    pestaña «escritorio»: así lo marcan todos los motores que abre la página) y, para un motor cuyo aviso corre en un
    servicio compartido sin ese entorno (el gateway de OpenClaw, el servidor de OpenCode), el índice de su
    conversación (arquitectura/registro). Nunca levanta."""
    env = os.environ if env is None else env
    try:
        if str(env.get("WORKSPACE_VIA") or "").strip() == MONITO:
            return True
        if str(env.get("WORKSPACE_WS") or "").strip() == MONITO:
            return True
        if env.get("WORKSPACE_VIA") or env.get("WORKSPACE_WID"):
            return False                     # tiene su pestaña y no es la del monito
        sid = str((data or {}).get("session_id") or "").strip() if isinstance(data, dict) else ""
        if not sid:
            return False
        _root_import("paths")                # la raíz de Workspace, en el path
        from arquitectura import registro
        fila = registro.indice(sid) if hasattr(registro, "indice") else None
        return str((fila or {}).get("via") or "") == MONITO
    except Exception:
        return False


def _del_monito(rec):
    """¿Ese pendiente lo dejó una conversación del monito? (los de antes de esta regla solo traen su pestaña)."""
    return isinstance(rec, dict) and (rec.get("canal") == MONITO
                                      or str(rec.get("pestana") or "").strip() == MONITO)


def _adoptar_del_monito(brain, clave, pest):
    """Bajo el candado: si esta pestaña (su terminal o la página) no tiene nada en su cola, toma UNA revisión que
    dejó el monito (la más vieja; la repetida primero) y la pasa a SU cola: así la entrega, el reporte y el juicio son
    los de esta pestaña, como cualquier otra. Sin pestaña (sin clave) pasa al pending.json de siempre si está libre.
    → True si adoptó."""
    try:
        if any(not _ya_entregada(brain, x[2]) for x in _cola(brain, clave)) if clave else \
                os.path.exists(_pending_path(brain)):
            return False
        del_monito = [x for x in _pendientes(brain)
                      if x[1] != clave and os.path.basename(x[0]) != "pending.json" and _del_monito(x[2])
                      and not _ya_entregada(brain, x[2])]
        del_monito.sort(key=lambda x: (not x[2].get("repetida"), float(x[2].get("t") or 0)))
        for ruta, _c, rec in del_monito:
            nuevo = dict(rec, canal="", adoptada_de=MONITO, wid=pest.get("wid") or "",
                         pestana=pest.get("nombre") or "")
            nuevo.pop("al_mensaje", None)
            destino = _pending_path(brain, clave, rec.get("id") or uuid.uuid4().hex[:12])
            if os.path.exists(destino):
                continue
            _write_json(destino, nuevo)      # primero la copia: si falla, el del monito sigue
            try:
                os.remove(ruta)
            except OSError:
                try:
                    os.remove(destino)
                except OSError:
                    pass
                continue
            _log({"evento": "adoptada_del_monito", "cerebro": os.path.basename(os.path.normpath(brain)),
                  "vista": _nombre_vista(rec.get("view"))})
            return True
    except Exception:
        pass
    return False


def _candado(brain, timeout):
    """El candado de los pendientes de ESTE cerebro, en `<cerebro>/.claude/
    locks/` (olock.local_lock: no viaja por Obsidian ni iCloud). None si no
    hay candado posible (sin olock): se sigue como antes."""
    olock = _root_import("olock")
    if olock is None:
        return None
    return olock.local_lock(os.path.join(_review_dir(brain), "pendientes"), timeout=timeout)


def _socio(brain):
    """Socio activo del cerebro: la MISMA resolución que las pestañas
    (sessions_registry.socio → identidad de la máquina, sesiones v2). Si no
    se resuelve, el socio.local de antes; si tampoco, «equipo»."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__))) \
            if os.path.basename(os.path.dirname(os.path.abspath(__file__))) == "hooks" \
            else os.path.dirname(os.path.abspath(__file__))
        if root not in sys.path:
            sys.path.insert(0, root)
        import sessions_registry
        s = re.sub(r"[^a-z0-9_-]", "", (sessions_registry.socio(brain) or "").lower())
        if s:
            return s
    except Exception:
        pass
    try:
        s = open(os.path.join(brain, ".claude", "socio.local"),
                 encoding="utf-8").read()
        s = re.sub(r"[^a-z0-9_-]", "", s.strip().lower())
        return s or "equipo"
    except Exception:
        return "equipo"


def _notify_path(brain):
    """Canal de avisos del cerebro (ruta RELATIVA al cerebro). Lo usa también
    skill_audit (herramienta de desarrollo). Inbox diario del socio si existe
    STATE/inbox/; si no, STATE/needs-review.md si existe; si no, el inbox."""
    today = datetime.date.today().isoformat()
    inbox = os.path.join("STATE", "inbox", "%s-%s.md" % (_socio(brain), today))
    if os.path.isdir(os.path.join(brain, "STATE", "inbox")):
        return inbox
    if os.path.exists(os.path.join(brain, "STATE", "needs-review.md")):
        return os.path.join("STATE", "needs-review.md")
    return inbox


def _setting_on(key):
    """Setting bool del store unificado. Falla-suave → False (opcional)."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)
        import settings as _settings
        return _settings.enabled(key, default=False)
    except Exception:
        return False


def _root_import(name):
    """Importa un módulo de la raíz de WORKSPACE. None si no se puede."""
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if root not in sys.path:
        sys.path.append(root)
    try:
        return __import__(name)
    except Exception:
        return None


def _agent_def(brain):
    """<cerebro>/.workspace/agent.json o {}. Falla-suave."""
    ar = _root_import("agentsreg")
    try:
        if ar is not None:
            d = ar.load_definition(brain)
            return d if isinstance(d, dict) else {}
        with open(os.path.join(brain, ".workspace", "agent.json"),
                  encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def brain_root(cwd, env=None):
    """La RAÍZ del cerebro de la sesión (el cwd puede ser una subcarpeta).
    1) subir hasta la carpeta con la definición de un agente; 2) WORKSPACE_BRAIN;
    3) el cwd tal cual."""
    env = os.environ if env is None else env
    ar = _root_import("agentsreg")
    start = os.path.abspath(cwd or os.getcwd())
    cur = start
    while True:
        try:
            has = ar.has_definition(cur) if ar is not None else os.path.isfile(
                os.path.join(cur, ".workspace", "agent.json"))
        except Exception:
            has = False
        if has:
            return cur
        up = os.path.dirname(cur)
        if up == cur:
            break
        cur = up
    wb = str(env.get("WORKSPACE_BRAIN") or "").strip()
    if wb and os.path.isdir(wb):
        return wb
    return start


MODOS = ("off", "on_open", "on_close", "button")
SOLO_BOTON = ("hermes", "openclaw")


def _ajuste_revision(brain, campo, key):
    d = _agent_def(brain)
    if campo in d:
        return d[campo]
    settings = _root_import("settings")
    try:
        return settings.get_stored(key) if settings is not None else None
    except Exception:
        return None


def review_engine(brain, origen=""):
    value = _ajuste_revision(brain, "skill_review_engine", "hooks.skill_review_engine")
    return str(value) if value and value != "session" else (
        origen or _agent_def(brain).get("engine") or "claude-code")


def review_mode(brain, origen=""):
    """Elección explícita > booleano anterior; instalaciones nuevas apagadas.

    Motores sin escritura al panel solo ofrecen el botón. El kill-switch
    siempre gana, también con una elección explícita del agente.
    """
    if os.environ.get("WORKSPACE_NO_SKILL_REVIEW"):
        return "off"
    mode = _ajuste_revision(brain, "skill_review_mode", "hooks.skill_review_mode")
    if mode not in MODOS:
        v = _agent_def(brain).get("skill_review")
        on = v if isinstance(v, bool) else _setting_on("hooks.skill_review")
        mode = "on_open" if on else "off"
    if mode != "off" and review_engine(brain, origen) in SOLO_BOTON:
        return "button"
    return mode


def review_enabled(brain):
    return review_mode(brain) != "off"


def motores_revision():
    """Motor fijo: solo instalaciones reales; nunca instala ni inicia sesión."""
    try:
        import harnesses
        return ["session"] + [x["id"] for x in harnesses.registry() if x.get("installed") and x.get("binaries_ok")]
    except Exception:
        return ["session"]


def _vista(transcript, engine=""):
    """(texto de la vista NEUTRA, turnos) de la sesión, o ('', None) si el
    formato no se reconoce o no hay diálogo visible. El agente jamás lee el
    crudo del vendor."""
    nt = _root_import("neutral_transcript")
    if nt is None:
        return "", None
    try:
        doc = nt.ingest(transcript)
        if not doc:
            return "", None
        text, meta = nt.sanitized_view(doc)
        if not text.strip():
            return "", None
        head = ["# Sesión a revisar (vista neutral de Workspace)", "",
                "- motor: %s" % ((doc.get("session") or {}).get("engine") or engine or "?")]
        files = meta.get("files_touched") or []
        if files:
            head.append("- archivos tocados: %s" % ", ".join(str(f) for f in files[:40]))
        return "\n".join(head) + "\n\n" + text + "\n", doc.get("turns") or []
    except Exception:
        return "", None


def trivial(turnos):
    """¿Sesión trivial? Por lo que se habló (la vista neutral): menos de
    MIN_VISTA_LINEAS líneas de diálogo o menos de MIN_TURNOS_SOCIO mensajes
    del socio."""
    socio, lineas = 0, 0
    for t in turnos or ():
        txt = (t.get("text") or "").strip()
        if not txt or t.get("noise"):
            continue
        if t.get("role") == "user":
            socio += 1
        lineas += sum(1 for ln in txt.splitlines() if ln.strip())
    return socio < MIN_TURNOS_SOCIO or lineas < MIN_VISTA_LINEAS


def _escribir_vista(outdir, texto):
    os.makedirs(outdir, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    path = os.path.join(outdir, "sesion-%s-%d.md" % (stamp, os.getpid()))
    _escribir(path, texto)
    return path


def write_neutral_transcript(transcript, outdir, engine=""):
    """Vista NEUTRA de la sesión (neutral_transcript) en `outdir`: el agente
    jamás lee el crudo del vendor. '' si el formato no se reconoce o no hay
    diálogo visible."""
    texto, _turnos = _vista(transcript, engine)
    if not texto:
        return ""
    try:
        return _escribir_vista(outdir, texto)
    except Exception:
        return ""


def _nombre_vista(view):
    """Nombre de archivo de una vista (sin la ruta; acepta las dos barras)."""
    return os.path.basename(str(view or "").replace("\\", "/"))


def _vista_del_pendiente(outdir):
    """Nombre de la vista que referencia el pending.json de `outdir`, o ''."""
    try:
        with open(os.path.join(outdir, "pending.json"), encoding="utf-8") as fh:
            return _nombre_vista(json.load(fh).get("view"))
    except Exception:
        return ""


def _vistas_protegidas(outdir):
    """Las vistas que señala CUALQUIER pendiente o entrega de `outdir` (una
    por pestaña, 0.9.1): ninguna se poda."""
    out = set()
    try:
        nombres = os.listdir(outdir)
    except OSError:
        return out
    for n in nombres:
        if (n.startswith("pending") or n.startswith("delivered")) and n.endswith(".json"):
            try:
                with open(os.path.join(outdir, n), encoding="utf-8") as fh:
                    v = _nombre_vista((json.load(fh) or {}).get("view"))
                if v:
                    out.add(v)
            except Exception:
                continue
    return out


def _prune_views(outdir, keep=KEEP_VIEWS, ahora=None):
    """Deja solo las `keep` vistas más recientes (no se acumulan), MÁS las que
    señala un pendiente o una entrega aunque sean más viejas, MÁS las de menos
    de PODA_MIN_SECONDS (un cierre lento aún no escribe su pendiente: antes la
    poda de otro cierre se la llevaba — revisor 0.9.0, #18)."""
    protegidas = _vistas_protegidas(outdir)
    ahora = time.time() if ahora is None else ahora
    try:
        views = sorted((f for f in os.listdir(outdir)
                        if f.startswith("sesion-") and f.endswith(".md")), reverse=True)
        for k, f in enumerate(views):
            if f in protegidas:
                continue
            p = os.path.join(outdir, f)
            try:
                edad = ahora - os.path.getmtime(p)
                # las `keep` más recientes se quedan, pero ninguna más de 7 días
                if edad < PODA_MIN_SECONDS or (k < keep and edad <= VENCE_SECONDS):
                    continue
                os.remove(p)
            except OSError:
                pass
    except OSError:
        pass


def _quitar_vista(outdir, view):
    """Borra la vista de una revisión ya resuelta o vencida, si ningún otro
    pendiente o entrega la señala (privacidad: la conversación se guarda hasta
    que se revisa o vence)."""
    v = _nombre_vista(view)
    if not v.startswith("sesion-") or v in _vistas_protegidas(outdir):
        return
    try:
        os.remove(os.path.join(outdir, v))
    except OSError:
        pass


def _escribir(path, texto):
    """Escritura atómica con temporal ÚNICO que se borra si algo falla
    (atomico): en Windows quedaban `*.tmp-<pid>` (revisor 0.9.0, #18)."""
    at = _root_import("atomico")
    if at is not None:
        at.escribir(path, texto, fsync=False)
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp-%d" % (path, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(texto)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _write_json(path, data):
    _escribir(path, json.dumps(data, ensure_ascii=False, indent=1))


def _leer_json(path):
    """(dict, estado): ok, no_existe, ilegible o error_lectura transitorio."""
    try:
        with open(path, encoding="utf-8-sig") as fh:
            d = json.load(fh)
    except FileNotFoundError:
        return None, "no_existe"
    except OSError:
        return None, "error_lectura"
    except (ValueError, UnicodeError):
        return None, "ilegible"
    except Exception:
        return None, "error_lectura"
    return (d, "ok") if isinstance(d, dict) else (None, "ilegible")


def _ensure_gitignore(brain):
    """La carpeta de revisión no se versiona (trae texto de la sesión). Dos
    capas: un `.gitignore` propio DENTRO de la carpeta («*», git lo respeta
    sin importar el del cerebro) y la línea en el `.gitignore` del cerebro.
    Un `.gitignore` del cerebro que no es UTF-8 (ANSI, o UTF-16 de `>>` en
    PowerShell 5) no se toca (regla 2): antes hacía reventar el cierre y la
    vista quedaba sin ignorar (revisión 0.3.4). → True si quedó protegida."""
    protegida = False
    try:
        d = _review_dir(brain)
        os.makedirs(d, exist_ok=True)
        propio = os.path.join(d, ".gitignore")
        if not os.path.isfile(propio):
            with open(propio, "w", encoding="utf-8", newline="\n") as fh:
                fh.write("*\n")
        protegida = True
    except OSError:
        pass
    line = ".claude/skill-review/"
    gi = os.path.join(brain, ".gitignore")
    try:
        try:
            with open(gi, "rb") as fh:
                have = fh.read().decode("utf-8-sig")
        except FileNotFoundError:
            have = ""
        if line not in [l.strip() for l in have.splitlines()]:
            with open(gi, "a", encoding="utf-8", newline="") as fh:
                fh.write(("" if not have or have.endswith("\n") else "\n") + line + "\n")
        protegida = True
    except (OSError, ValueError):        # UnicodeDecodeError: no se entiende, no se toca
        pass
    return protegida


# ── la tarea que recibe el agente al abrir ──────────────────────────────────
REVIEW_PROMPT = """\
REVISIÓN DE SKILLS PENDIENTE (Workspace · tu opción «Revisión de skills» está encendida).
Antes de seguir con lo que pida el socio, dedica un momento a revisar la sesión anterior
y a mejorar la biblioteca de skills de este cerebro, siguiendo el Skill Loop de BRAIN.md.

{guard}

1. Lee la sesión anterior (vista neutral de Workspace): {transcript}
2. SEÑALES para actuar — activo pero conservador; NO actúes sobre tareas one-shot:
   el socio corrigió un approach o el ESTILO/tono/formato (señal de primera clase);
   4+ pasos de una tarea repetible; se halló el camino tras un error; un pitfall no
   obvio; el socio dijo «siempre que…» / «cada vez que…».
3. ORDEN (patch-first): a) parchea la skill que se usó; b) la más cercana al tema;
   c) una sección de apoyo en una existente; d) último recurso: una skill NUEVA, a
   nivel de clase, directo en skills/<categoría>/<nombre>/SKILL.md (skill-creator) y
   registrada en skills/README.md. No fragmentes: una skill sirve a todos.
4. REGISTRO DE USO (convención N12): por cada skill USADA o PARCHADA actualiza, con tus
   herramientas de archivos (sin comandos), skills/<categoría>/<nombre>/.usage.json —
   {{"schema": 1, "use_count": N, "view_count": N, "patch_count": N, "last_used":
   "<ISO-8601 UTC>"}} (al parchar, también "last_patched"; si no existe, use_count
   empieza en el `used_count:` del frontmatter + 1).
   NO edites el `used_count:` del frontmatter — quedó congelado como valor histórico.
5. LÍMITES: escribe solo dentro de skills/. No toques BOOT/, wiki/, deliverables/ ni STATE/.
{propuestas}
Sé breve y quirúrgico. Si no hay nada que valga la pena, no inventes.
AL TERMINAR, avísale a Workspace qué pasó (así lo comprueba; si no, te la vuelve a pedir):
   {reporte}
y dilo en una línea de tu bloque 🧠 («🧠 Skill mejorada: `<nombre>`», «🧠 Skill creada:
`<nombre>`» o «🧠 check ✓ — nada que aprender»). Luego sigue con lo que pida el socio.
"""

#: Cómo reporta el agente el resultado: la herramienta MCP si la tiene (no pide
#: permiso) y, si no, el comando SOLO en su línea. F4 (prueba de punta a punta
#: v4): con la terminal primero, Antigravity la encadenó con otro comando
#: (`… && workspace memoria resumen --help`) y pidió permiso al arrancar.
#: Sin el id de la entrega (una tarea de antes de 0.9.2).
REPORTE_CLI = ("con la herramienta revision_resultado del servidor workspace-memoria, si la tienes "
               "(no pide permiso); si no, con este comando, solo, en su propia línea (sin encadenarlo "
               "con otros): workspace revision resultado creada|mejorada|nada [<categoría>/<skill>]")
#: Con el id de la entrega: lo puede copiar CUALQUIER motor, también uno que no
#: exporta la clave de su pestaña al shell de sus herramientas (Greptile 0.9.2,
#: #2). Tenerlo prueba que esa sesión recibió ESTA tarea.
REPORTE_CLI_ENTREGA = ("con la herramienta revision_resultado del servidor workspace-memoria, con "
                       "entrega \"{id}\", si la tienes (no pide permiso); si no, con este comando, solo, "
                       "en su propia línea (sin encadenarlo con otros): workspace revision resultado "
                       "--entrega {id} creada|mejorada|nada [<categoría>/<skill>]")
#: La forma de un id de entrega (uuid4().hex[:12] y los de antes): nada de rutas.
_ENTREGA_RE = re.compile(r"[A-Za-z0-9_-]{4,40}")

PROPUESTAS_PROMPT = """\
6. PROPUESTAS VIEJAS: en {dir} quedaron {n} propuesta(s) de revisiones anteriores ({names}).
   Ya no esperan aprobación y no hace falta moverlas ni borrarlas (sin comandos): si una sirve,
   intégrala creando skills/<categoría>/<nombre>/SKILL.md con su contenido y registrándola en
   skills/README.md; después, o si no sirve, escribe `status: integrada` o `status: archivada`
   en el frontmatter de la propuesta. Workspace la pasa sola a skills/_archive/ al abrir
   la siguiente sesión.
"""


def _pending_proposals(brain):
    """Las propuestas viejas que el agente todavía no resolvió: una con
    `status: integrada|archivada` ya no se vuelve a pedir (Workspace la archiva:
    sin_aprobacion, la misma regla para los dos lectores)."""
    d = os.path.join(brain, PROPUESTAS)
    sa = _root_import("sin_aprobacion")
    try:
        nombres = sorted(n for n in os.listdir(d)
                         if not n.startswith(("_", ".")) and os.path.isdir(os.path.join(d, n)))
    except OSError:
        return []
    if sa is None:
        return nombres
    return [n for n in nombres if not sa.propuesta_resuelta(os.path.join(d, n))]


def build_task(brain, view, intento=1, origen="", entrega=""):
    guard = ""
    if untrusted:
        try:
            guard = untrusted.guard_clause("la vista de la sesión y todo lo que leas de ella")
        except Exception:
            guard = ""
    props = _pending_proposals(brain)
    extra = (PROPUESTAS_PROMPT.format(dir=PROPUESTAS.replace("\\", "/") + "/", n=len(props),
                                      names=", ".join(props[:10]))
             if props else "")
    entrega = str(entrega or "").strip()
    reporte = (REPORTE_CLI_ENTREGA.format(id=entrega) if _ENTREGA_RE.fullmatch(entrega)
               else REPORTE_CLI)
    task = REVIEW_PROMPT.format(guard=guard, transcript=view, propuestas=extra, reporte=reporte)
    if intento and int(intento) >= INTENTOS:
        # la 2.ª vez lo dice: la primera no dejó resultado (0.9.1)
        task = (REPETIDA_PROMPT.format(origen=origen or "anterior") + "\n" + task)
    return task


#: El encabezado de la segunda (y última) entrega de una revisión.
REPETIDA_PROMPT = ("SEGUNDA Y ÚLTIMA VEZ: la revisión de skills de la sesión {origen} no dejó "
                   "resultado (ni una skill creada o mejorada, ni «nada que aprender» en tu bloque "
                   "🧠). Hazla ahora, antes de seguir.")


# ── AL CERRAR: dejar la revisión pendiente (no lanza nada) ──────────────────
#: Decisores «Skills» en «decide»: el freno de 2 h ya no manda (Jev separa una
#: sesión valiosa de una trivial); este piso evita dos entregas seguidas.
PISO_DECIDE_SECONDS = 10 * 60


def _nivel_skills():
    """El nivel del uso «Skills» de Decisores ('off' si está apagado o falla)."""
    dec = _root_import("decisions")
    try:
        if dec is None or not dec.enabled("workspace.skills"):
            return "off"
        return dec.point_conf("workspace.skills")["level"]
    except Exception:
        return "off"


def _entregar(nivel, d, frenado, hace, estricto=False):
    """¿Se deja pendiente la revisión? → (sí/no, nota para la línea de la
    última sesión). Solo con «decide» Y una respuesta sobre el umbral (mode
    apply) decide Jev: «sí» entrega —con el piso de 10 min—, «no» no. Todo lo
    demás (apagado, observe, suggest, «decide» bajo el umbral o sin
    probabilidad, un fallo, la pausa) es lo de siempre: el freno de 2 h
    decide. Prueba real 2026-11-07: un «sí» al 71 % (bajo el 90) no se
    entregaba, aunque sin Decisores sí se habría entregado."""
    dec = _root_import("decisions")
    if dec is None or not dec.decisores_activos():
        nivel, d = "off", None
    if estricto and nivel != "off":
        si = isinstance(d, dict) and str(d.get("choice") or "").strip().lower() in ("sí", "si")
        return bool(si), "" if si else "sin_si"
    if nivel == "decide" and isinstance(d, dict) and d.get("mode") == "apply":
        si = str(d.get("choice") or "").strip().lower() in ("sí", "si")
        if si and hace is not None and hace < PISO_DECIDE_SECONDS:
            return False, "throttled"
        return si, ""
    if frenado:
        return False, "throttled"
    # lo de siempre: se entrega; si la sugerencia de Jev era «no», la línea de
    # la última sesión lo aclara (no contradice lo que pasó)
    no = isinstance(d, dict) and str(d.get("choice") or "").strip().lower() == "no"
    return True, ("delivered" if no else "")


def _resultado(d, resultado, detalle=""):
    """Decisores («¿pasó?»): lo que pasó con la revisión de la decisión `d`
    (un dict con `id`, o el id). Sin decisión (uso apagado): nada."""
    if isinstance(d, list):
        for item in d:
            _resultado(item, resultado, detalle)
        return
    eid = d.get("id") if isinstance(d, dict) else d
    if not eid:
        return
    dec = _root_import("decisions")
    try:
        if dec is not None:
            dec.record_result(eid, resultado, detalle=detalle)
    except Exception:
        pass


def main(argv=None):
    if os.environ.get("WORKSPACE_NO_SKILL_REVIEW"):
        return  # el env SIEMPRE gana
    data = _stdin()
    brain = brain_root(data.get("cwd", ""))
    if not review_enabled(brain):
        return
    transcript = data.get("transcript_path", "")
    if data.get("reason", "") in SKIP_REASONS or not transcript or not os.path.exists(transcript):
        return
    pest = pestana_actual(data)
    pest["monito"] = en_monito(data)
    # 1) ¿la revisión que recibió ESTA pestaña dejó resultado? (0.9.1)
    batch = os.environ.get("WORKSPACE_REVIEW_BATCH")
    visible = _root_import("skill_review_visible") if batch else None
    if not (visible is not None and visible.stopped(batch)):
        comprobar(brain, pest, transcript)
    if batch:
        return  # una revisión nunca genera otra revisión de sí misma
    # 2) ¿esta sesión deja una revisión?
    try:
        with open(transcript, encoding="utf-8", errors="ignore") as f:
            txt = f.read()
    except Exception:
        return
    texto, turnos = _vista(transcript, data.get("engine", ""))
    if not texto or trivial(turnos):
        return          # formato no reconocido (jamás el crudo) o sesión trivial
    tp = _throttle_path(brain)
    hace = None
    try:
        if os.path.exists(tp):
            hace = time.time() - os.path.getmtime(tp)
    except Exception:
        hace = None
    frenado = hace is not None and hace < THROTTLE_SECONDS
    # Con el uso «Skills» apagado, EXACTAMENTE lo de siempre: frenado → nada.
    # Encendido, Jev igual se consulta (y se anota) aunque el freno no deje
    # entregar: observe/suggest siguen al freno; decide decide (_entregar).
    estricto = _ajuste_revision(brain, "skill_review_mode", "hooks.skill_review_mode") in MODOS
    nivel = _nivel_skills() if frenado or estricto else None
    if frenado and nivel == "off":
        return
    findings = []
    if untrusted:   # guard N6, LOG-ONLY: observa, jamás aborta
        try:
            findings = untrusted.scan_and_log(txt, source=transcript, brain=brain)
        except Exception:
            findings = []
    if os.environ.get("WORKSPACE_REVIEW_DRYRUN"):
        print("[skill_review dry-run] dejaría pendiente la revisión de %s" % brain)
        if findings:
            print("  guard N6 (log-only): %d finding(s) → %s" % (
                len(findings), [f["class"] for f in findings]))
        return
    outdir = _review_dir(brain)
    # ANTES de escribir la vista (texto de la conversación): que git la ignore
    if not _ensure_gitignore(brain):
        return
    try:
        view = _escribir_vista(outdir, texto)
    except Exception:
        return
    d = _decisor(view)
    if nivel is None:
        nivel = _nivel_skills() if d is not None else "off"
    entregar, nota = _entregar(nivel, d, frenado, hace, estricto=estricto)
    _anotar_visible(brain, data, d, nota)
    clave = clave_pestana(pest)
    if entregar:
        _dejar_pendiente(brain, clave, pest, view, findings, d, tp)
        if review_mode(brain, pest.get("motor")) == "on_close" and not pest.get("monito"):
            visible = _root_import("skill_review_visible")
            mux = _root_import("multiplexer")
            try:
                if visible is not None and mux is not None and mux.inside_herdr():
                    visible.launch(automatic=True)
            except Exception:
                _aviso_cola(brain, "lanzamiento_fallido")
    else:
        if nota != "throttled":
            _resultado(d, "saltada")         # «decide» dijo «no»: su efecto es saltarla
        elif isinstance(d, dict) and d.get("mode") == "apply":
            _resultado(d, "frenada")         # su «sí» lo frenó el piso de 10 min
        else:
            _resultado(d, "frenada_regla")   # observa/sugiere: la frenó la regla de 2 h
        _podar(brain)


def _podar(brain):
    lk = _candado(brain, CANDADO_CIERRE_S)
    try:
        if lk is not None:
            lk.__enter__()
    except Exception:
        return                       # otro proceso la tiene: ese poda
    try:
        _ordenar(brain)
    finally:
        if lk is not None:
            lk.__exit__(None, None, None)


def _dejar_pendiente(brain, clave, pest, view, findings, d, tp):
    """Bajo el candado del cerebro: el pendiente de ESTA pestaña va a SU cola
    (la repetición de una anterior y lo nuevo conviven: revisor 0.9.1, P1),
    el freno, los vencidos y la poda. Sin pestaña, el pending.json de siempre
    (uno: el anterior que no se entregó queda «se perdió»)."""
    rec = {"id": uuid.uuid4().hex[:12], "view": view, "engine": pest.get("motor") or "claude-code",
           "ts": datetime.datetime.now().isoformat(timespec="seconds"), "t": round(time.time(), 3),
           "findings": len(findings), "decisor": d, "decision": (d or {}).get("id"),
           "agente": pest.get("agente") or _agent_def(brain).get("name") or "",
           "wid": pest.get("wid") or "", "pestana": pest.get("nombre") or "",
           "sesion": pest.get("sesion") or "", "intento": 1}
    if pest.get("monito"):
        rec["canal"] = MONITO            # no se entrega ahí: la adopta su terminal o la página
    pp = _pending_path(brain, clave, rec["id"])
    try:
        lk = _candado(brain, CANDADO_CIERRE_S)
        if lk is None:
            _log({"evento": "cola_sin_candado", "motivo": "no_disponible"})
            _aviso_cola(brain, "cola_sin_candado")
            return
        lk.__enter__()
    except Exception as exc:
        _log({"evento": "cola_sin_candado", "motivo": type(exc).__name__})
        _aviso_cola(brain, "cola_sin_candado")
        return                       # no leer, guardar ni ordenar fuera del candado
    try:
        if not clave:
            viejo, est = _leer_json(pp)
            if est == "ok" and viejo.get("decision") and viejo.get("decision") != rec["decision"]:
                _resultado(viejo.get("decision"), "perdida", detalle="la reemplazó otra sesión")
        try:
            _write_json(pp, rec)
            os.makedirs(os.path.dirname(tp), exist_ok=True)
            open(tp, "w").close()
        except Exception:
            pass
        else:
            _resultado(d, "pendiente", detalle=rec["pestana"])
            if clave and _ajuste_revision(brain, "skill_review_mode", "hooks.skill_review_mode") in MODOS:
                # lo que una tanda VIVA ya reservó no se reagrupa ni se borra: su
                # receptora lo busca por esos ids. Las sesiones nuevas forman su
                # propio grupo para la siguiente tanda (Greptile 0.9.2, conf. #2)
                reservados = _reservados(brain, clave)
                _agrupar_tanda(brain, clave, {item[2]["id"] for item in _cola(brain, clave)
                                              if item[2].get("id") not in reservados})
        _ordenar(brain)
    finally:
        if lk is not None:
            lk.__exit__(None, None, None)


def _retirar(brain, ruta, rec, resultado, detalle):
    """Quita un pendiente (o una entrega) y anota por qué; su vista se va con
    la poda en cuanto nadie más la señale."""
    try:
        os.remove(ruta)
    except OSError:
        return False
    _quitar_vista(os.path.dirname(ruta), rec.get("view"))
    _resultado(rec.get("decision"), resultado, detalle=detalle)
    _log({"evento": "pendiente_" + resultado, "cerebro": os.path.basename(os.path.normpath(brain)),
          "vista": _nombre_vista(rec.get("view"))})
    return True


def _ordenar(brain, ahora=None):
    """Bajo el candado: vence lo de más de VENCE_SECONDS (pendientes y entregas
    que nunca se cerraron), recorta cada cola a COLA_MAX y el cerebro a
    MAX_PENDIENTES (la repetición se queda; lo nuevo más viejo se va primero)
    y poda las vistas que ya nadie señala."""
    ahora = time.time() if ahora is None else ahora
    d = _review_dir(brain)
    try:
        nombres = os.listdir(d)
    except OSError:
        return
    for n in nombres:
        if n.startswith("delivered") and n.endswith(".json"):
            rec, est = _leer_json(os.path.join(d, n))
            if est == "ok" and rec.get("entregada_t") and \
                    ahora - float(rec["entregada_t"]) > VENCE_SECONDS:
                _retirar(brain, os.path.join(d, n), rec, "vencida", "sin cerrar en 7 días")
    vivos = []
    for ruta, clave, rec in _pendientes(brain):
        if ahora - float(rec.get("t_origen") or rec.get("t") or ahora) > VENCE_SECONDS:
            _retirar(brain, ruta, rec, "vencida", "7 días sin revisar")
        else:
            vivos.append((ruta, clave, rec))
    por_clave = {}
    for x in vivos:
        por_clave.setdefault(x[1], []).append(x)
    sobran = []
    for clave, cola in por_clave.items():
        cola.sort(key=lambda x: (bool(x[2].get("repetida")), float(x[2].get("t") or 0)), reverse=True)
        sobran += cola[COLA_MAX:]
    restantes = [x for x in vivos if x not in sobran]
    if len(restantes) > MAX_PENDIENTES:
        restantes.sort(key=lambda x: (bool(x[2].get("repetida")), float(x[2].get("t") or 0)),
                       reverse=True)
        sobran += restantes[MAX_PENDIENTES:]
    for ruta, _clave, rec in sobran:
        _retirar(brain, ruta, rec, "perdida", "tope de revisiones pendientes")
    _prune_views(d)


def _anotar_visible(brain, data, d, nota):
    """suggest/decide: el veredicto se ve UNA vez al abrir la siguiente sesión
    (decision_visible). observe y apagado: nada."""
    if not isinstance(d, dict):
        return
    vis = _root_import("decision_visible")
    if vis is None:
        return
    try:
        tab = (os.environ.get("WORKSPACE_WS") or os.environ.get("ZENITH_WS")
               or str(data.get("tab") or ""))
        vis.anotar_cierre(brain, "workspace.skills", d, sesion=str(data.get("session_id") or ""),
                          tab=tab, nota=nota)
    except Exception:
        pass


# ── AL ABRIR: entregar la revisión pendiente al agente (una vez) ────────────
def archivar_resueltas(brain):
    """Al abrir CADA sesión (con o sin revisión encendida): las propuestas
    viejas que el agente ya marcó `status: integrada|archivada` pasan a
    skills/_archive/ con sin_aprobacion.archivar_propuestas_resueltas — la
    misma lógica y el mismo candado que las tres puertas. La tarea promete que
    «Workspace la pasa sola a skills/_archive/» y antes solo pasaba al
    actualizar, al cargar o con `doctor --fix` (Greptile, 2026-10-18).
    Barato (sin skills/_propuestas/ no hace nada) y falla-suave: con el
    candado ocupado o cualquier error, queda para la próxima sesión."""
    if not brain or not os.path.isdir(os.path.join(brain, PROPUESTAS)):
        return []
    sa = _root_import("sin_aprobacion")
    if sa is None:
        return []
    try:
        return sa.archivar_propuestas_resueltas(brain, timeout=1.0)
    except Exception:
        return []


# ── Decisores · uso «Skills» (apagado de fábrica) ────────────────────────────
#: Lo que el decisor ve de la sesión: el inicio de la vista neutral (ya sin
#: thinking, sin tools ni crudo del vendor); la fachada además quita secretos.
DECISOR_CONTEXTO = 6000


def _decisor(view):
    """AL CERRAR: ¿esta sesión amerita crear o mejorar una skill? Se guarda en
    el pendiente {mode, choice, p, …} y se APLICA al abrir (start_context).
    None si el uso está apagado, falla o tarda: la revisión sigue como hoy."""
    dec = _root_import("decisions")
    if dec is None:
        return None
    try:
        if not dec.enabled("workspace.skills"):
            return None
        with open(view, encoding="utf-8", errors="replace") as fh:
            ctx = fh.read(DECISOR_CONTEXTO * 2)
        # la fachada redacta y DESPUÉS recorta (un secreto en el corte no sale a medias)
        v = dec.gate("workspace.skills", context=ctx, context_max=DECISOR_CONTEXTO)
        return {k: v.get(k) for k in ("mode", "choice", "p", "decider", "id", "message")} \
            if v else None
    except Exception:
        return None


def _con_decisor(task, d):
    """La tarea de revisión según el veredicto guardado al cerrar:
    None/observe → igual que hoy · suggest → + la estimación (decide el
    agente) · apply «no» → no se entrega (None) · apply «sí» → + la línea."""
    dec = _root_import("decisions")
    if dec is None or not dec.decisores_activos():
        return task
    if not isinstance(d, dict) or d.get("mode") not in ("suggest", "apply"):
        return task
    if d.get("mode") == "apply" and str(d.get("choice") or "").strip().lower() == "no":
        return None
    linea = str(d.get("message") or "").strip()
    return task + ("\n" + linea + "\n" if linea else "")


#: Un pendiente cuya vista no está NO se gasta: sigue para la próxima apertura
#: y cada intento deja una línea en <estado>/logs/skill-review.log. Antes de
#: este plazo, el siguiente cierre que deje revisión lo reemplaza (la vista
#: nueva sí existe). Si la vista no aparece y pasa este plazo desde el primer
#: intento fallido, la apertura siguiente lo retira: pending.json →
#: perdido.json (con sus intentos) y la línea «pendiente_retirado» en el log.
SIN_VISTA_SECONDS = 24 * 3600


def _log(rec):
    """Rastro mínimo (<estado>/logs/skill-review.log, el mismo patrón que
    memoria.log): qué pasó con un pendiente. Nunca contenido de la sesión:
    solo el nombre del cerebro y el de la vista, sin rutas."""
    try:
        d = os.path.join(_state_dir(), "logs")
        os.makedirs(d, exist_ok=True)
        rec = dict(rec, ts=datetime.datetime.now().isoformat(timespec="seconds"))
        with open(os.path.join(d, "skill-review.log"), "a", encoding="utf-8") as fh:
            fh.write(json.dumps({k: (v if isinstance(v, int) else str(v)[:200])
                                 for k, v in rec.items()}, ensure_ascii=False) + "\n")
    except Exception:
        pass


# ── estado LOCAL (por máquina, no viaja): entregas hechas y lo que no se pudo
#    escribir en el cerebro ───────────────────────────────────────────────────
ENTREGADAS_MAX = 300


def _local_path():
    return os.path.join(_state_dir(), "skill-review", "estado.json")


def _local():
    d, est = _leer_json(_local_path())
    return d if est == "ok" else {}


def _local_cambiar(fn):
    """Lee-modifica-escribe el estado local (con su propio candado). Jamás levanta."""
    try:
        olock = _root_import("olock")
        lk = olock.file_lock(_local_path(), timeout=2) if olock is not None else None
        if lk is not None:
            lk.__enter__()
        try:
            path = _local_path()
            d, estado = _leer_json(path)
            if estado == "ilegible":
                backup = path + "." + time.strftime("%Y%m%d-%H%M%S", time.gmtime()) + "-" + uuid.uuid4().hex[:8] + ".bak"
                os.replace(path, backup)
                _log({"evento": "estado_local_ilegible", "respaldo": os.path.basename(backup)})
                return                     # no ejecutar la mutación sobre un vacío inventado
            if estado not in ("ok", "no_existe"):
                _log({"evento": "estado_local_sin_lectura"})
                return                     # un error de lectura no se aparta ni se pisa
            d = d if estado == "ok" else {}
            fn(d)
            _write_json(path, d)
        finally:
            if lk is not None:
                lk.__exit__(None, None, None)
    except Exception:
        pass


def _id_de(pending):
    """El id de un pendiente (los de antes de la 0.9.1 no lo traen: el nombre
    de su vista lo identifica igual)."""
    return str(pending.get("id") or _nombre_vista(pending.get("view")) or "")


def _ya_entregada(brain, pending):
    """¿Esta revisión ya se entregó? Por el estado local de ESTA máquina o por
    la entrega anotada en el cerebro. Con iCloud, OneDrive o Dropbox, el
    pendiente que se movió a entregada puede REAPARECER (la nube lo baja de
    nuevo): antes se entregaba dos veces (revisor 0.9.0, #18)."""
    pid = _id_de(pending)
    if not pid:
        return False
    if pid in (_local().get("entregadas") or []):
        return True
    try:
        for n in os.listdir(_review_dir(brain)):
            if n.startswith("delivered") and n.endswith(".json"):
                d, est = _leer_json(os.path.join(_review_dir(brain), n))
                if est == "ok" and d.get("id") and str(d.get("id")) == pid:
                    return True
    except OSError:
        pass
    return False


def _marcar_entregada(pid):
    def fn(d):
        lst = [x for x in (d.get("entregadas") or []) if x != pid] + [pid]
        d["entregadas"] = lst[-ENTREGADAS_MAX:]
        sv = d.get("sin_vista")
        if isinstance(sv, dict):
            sv.pop(pid, None)
    _local_cambiar(fn)


def _vista_vigente(brain, view):
    """La vista del pendiente si existe: la ruta guardada o, si el cerebro
    cambió de lugar, el mismo archivo en su carpeta de revisión actual. ''
    si no está."""
    view = str(view or "")
    if not view:
        return ""
    if os.path.isfile(view):
        return view
    nombre = _nombre_vista(view)
    if nombre.startswith("sesion-") and nombre.endswith(".md"):
        alt = os.path.join(_review_dir(brain), nombre)
        if os.path.isfile(alt):
            return alt
    return ""


def _desde_creacion(pending):
    """Cuándo se dejó el pendiente (epoch), o None."""
    try:
        return int(float(pending.get("t")))
    except (TypeError, ValueError):
        pass
    try:
        return int(time.mktime(time.strptime(str(pending.get("ts") or "")[:19],
                                             "%Y-%m-%dT%H:%M:%S")))
    except (ValueError, OverflowError):
        return None


def _sin_vista(brain, pp, pending):
    """El pendiente apunta a una vista que no está: NO se gasta. Cuenta el
    intento en el propio pendiente (`sin_vista`), deja rastro y, pasado
    SIN_VISTA_SECONDS desde el primer intento, lo retira a perdido.json.
    Llamado bajo el candado del cerebro (un cierre que lo reemplaza no se
    pisa). Si la carpeta no deja escribir, los intentos van al estado LOCAL,
    el rastro se deja UNA vez y el plazo cuenta desde que se dejó el
    pendiente: antes el log crecía en cada apertura y nunca se retiraba
    (revisor 0.9.0, #18)."""
    nombre = _nombre_vista(pending.get("view"))
    pid = _id_de(pending)
    sv = pending.get("sin_vista") if isinstance(pending.get("sin_vista"), dict) else {}
    ahora = int(time.time())
    try:
        desde = int(sv.get("desde_ts"))
    except (TypeError, ValueError):
        desde = ahora
    try:
        intentos = int(sv.get("intentos") or 0) + 1
    except (TypeError, ValueError):
        intentos = 1
    pending2 = dict(pending, sin_vista={"intentos": intentos, "desde_ts": desde})
    retirar = ahora - desde >= SIN_VISTA_SECONDS
    try:
        _write_json(pp, pending2)
        if retirar:
            os.replace(pp, os.path.join(os.path.dirname(pp), "perdido.json"))
        escrito = True
    except Exception:
        escrito = False
    if escrito:
        _log({"evento": "pendiente_retirado" if retirar else "pendiente_sin_vista",
              "cerebro": os.path.basename(os.path.normpath(brain)), "vista": nombre,
              "intentos": intentos})
        if retirar:
            _resultado(pending.get("decision"), "perdida", detalle="sin vista")
        return
    # la carpeta no deja escribir: el estado local lleva la cuenta
    out = {}

    def fn(d):
        lsv = d.setdefault("sin_vista", {})
        r = lsv.get(pid) if isinstance(lsv.get(pid), dict) else None
        primero = r is None
        if primero:
            r = {"intentos": 0, "desde_ts": _desde_creacion(pending) or ahora}
        r["intentos"] = int(r.get("intentos") or 0) + 1
        out["retirar"] = ahora - int(r.get("desde_ts") or ahora) >= SIN_VISTA_SECONDS
        out["primero"], out["intentos"] = primero, r["intentos"]
        if out["retirar"]:
            lsv.pop(pid, None)
            ret = [x for x in (d.get("retiradas") or []) if x != pid] + [pid]
            d["retiradas"] = ret[-ENTREGADAS_MAX:]
        else:
            lsv[pid] = r
    _local_cambiar(fn)
    if out.get("primero") or out.get("retirar"):
        _log({"evento": "pendiente_retirado" if out.get("retirar") else "pendiente_sin_vista",
              "cerebro": os.path.basename(os.path.normpath(brain)), "vista": nombre,
              "intentos": int(out.get("intentos") or 1), "carpeta": "sin permiso de escritura"})
    if out.get("retirar"):
        _resultado(pending.get("decision"), "perdida", detalle="sin vista")


def _retirada_local(pending):
    return _id_de(pending) in (_local().get("retiradas") or [])


def _origen_txt(pending):
    """«de ayer 16:21» / «del 8-nov 16:21»: cuándo se cerró la sesión revisada."""
    t = _desde_creacion(dict(pending, t=pending.get("t_origen") or pending.get("t")))
    if not t:
        return ""
    d = datetime.datetime.fromtimestamp(t)
    hoy = datetime.date.today()
    if d.date() == hoy:
        return "de hoy %s" % d.strftime("%H:%M")
    if d.date() == hoy - datetime.timedelta(days=1):
        return "de ayer %s" % d.strftime("%H:%M")
    return "del %d-%s %s" % (d.day, ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep",
                                     "oct", "nov", "dic")[d.month - 1], d.strftime("%H:%M"))


def _entrega_activa(brain, clave):
    rec, est = _leer_json(_delivered_path(brain, clave))
    return est == "ok" and bool(rec.get("entregada_t"))



def _entregar_pendiente(brain, pp, pending, pest, via="arranque"):
    """Bajo el candado: el pendiente pasa a entregado (de ESA pestaña), queda
    anotado en el estado local y en Decisores, y devuelve la tarea ('' si ya
    se había entregado, si no hay vista o si «decide» dijo «no»)."""
    clave = _clave_de(pp) or clave_pestana(pest)
    if not isinstance(pending, dict):
        return ""
    if _leer_json(_delivered_path(brain, clave))[1] == "error_lectura":
        return ""                            # no se sabe si hay una viva: no se pisa
    if _entrega_activa(brain, clave):
        return ""                            # la siguiente espera sin consumirse
    if _ya_entregada(brain, pending) or _retirada_local(pending):
        try:
            os.remove(pp)                    # reapareció (la nube): se descarta, con rastro
        except OSError:
            pass
        _log({"evento": "pendiente_duplicado", "cerebro": os.path.basename(os.path.normpath(brain)),
              "vista": _nombre_vista(pending.get("view"))})
        return ""
    view = _vista_vigente(brain, pending.get("view"))
    if not view:
        _sin_vista(brain, pp, pending)
        return ""
    task = _tarea(brain, pending, view)
    rec = dict(pending, entregada_t=round(time.time(), 3), via=via,
               tanda=os.environ.get("WORKSPACE_REVIEW_BATCH") or "",
               sesion_receptora=pest.get("sesion") or "", motor_receptor=pest.get("motor") or "",
               wid_receptor=pest.get("wid") or "", clave=clave)
    rec.pop("indice", None)
    bruto = os.environ.get("WORKSPACE_REVIEW_INDEX")
    if str(bruto or "").isdigit():
        rec["indice"] = int(bruto)
    rec.pop("al_mensaje", None)
    dp = _delivered_path(brain, clave)
    escrita = False
    try:
        if task is not None:
            _write_json(dp, rec)
            escrita = True
        os.remove(pp)
    except OSError:
        if escrita:                          # dos fases: nunca una entrega activa sin que la
            try:                             # tarea se haya devuelto (no se gasta el reintento)
                os.remove(dp)
            except OSError:                  # ni el rollback pudo: que quede rastro, no silencio
                _log({"evento": "rollback_fallido",
                      "cerebro": os.path.basename(os.path.normpath(brain)),
                      "vista": _nombre_vista(pending.get("view"))})
        return ""
    _marcar_entregada(_id_de(pending))
    if task is None:                       # «decide» dijo «no» (pendiente de antes de 0.9.1)
        _resultado(pending.get("decision"), "saltada")
        return ""
    _resultado(pending.get("decision"), "entregada", detalle=pest.get("nombre") or "")
    return task


def _tarea(brain, pending, view):
    """El texto de la tarea de un pendiente (None si «decide» dijo «no»)."""
    intento = int(pending.get("intento") or 1)
    return _con_decisor(build_task(brain, view, intento=intento, origen=_origen_txt(pending),
                                   entrega=str(pending.get("id") or "")),
                        pending.get("decisor"))


def _bajo_candado(brain, timeout, fn, defecto=""):
    lk = _candado(brain, timeout)
    try:
        if lk is not None:
            lk.__enter__()
    except Exception:
        return defecto                       # otro cierre/arranque: la siguiente apertura lo ve
    try:
        return fn()
    finally:
        if lk is not None:
            lk.__exit__(None, None, None)


def _ilegible(brain, pp):
    try:
        os.replace(pp, os.path.join(os.path.dirname(pp), "perdido.json"))
    except OSError:
        pass
    _log({"evento": "pendiente_ilegible", "cerebro": os.path.basename(os.path.normpath(brain))})


def _reservados(brain, clave):
    """Los ids que una tanda viva ya reservó (skill_review_visible.reservados);
    sin ese módulo o si falla, ninguno (se agrupa como antes)."""
    visible = _root_import("skill_review_visible")
    try:
        return set(visible.reservados(brain, clave)) if visible is not None else set()
    except Exception:
        return set()


def _agrupar_tanda(brain, clave, ids):
    """Bajo el candado del cerebro: una vista, una entrega, un juicio.

    Solo agrupa los ids fotografiados al empezar la tanda. Las sesiones que
    cierren mientras tanto esperan la próxima. Los ilegibles se conservan.
    """
    seleccion = []
    partes = []
    for ruta, c, rec in _cola(brain, clave):
        if rec.get("id") not in ids or _ya_entregada(brain, rec):
            continue
        view = _vista_vigente(brain, rec.get("view"))
        if not view:
            continue
        try:
            with open(view, encoding="utf-8") as f:
                texto = f.read()
        except (OSError, UnicodeError):
            _aviso_cola(brain, "pendiente_no_legible")
            continue
        seleccion.append((ruta, rec))
        partes.append("## Sesión " + str(rec.get("id")) + "\n\n" + texto)
    if len(seleccion) < 2:
        return
    cohortes = {}
    for ruta, item in seleccion:
        key = (int(item.get("intento") or 1), bool(item.get("repetida")))
        cohortes.setdefault(key, set()).add(item["id"])
    if len(cohortes) > 1:
        for compatibles in cohortes.values():
            _agrupar_tanda(brain, clave, compatibles)
        return  # una sesión nueva nunca hereda el último intento de otra
    primero = seleccion[0][1]
    ultimo = seleccion[-1][1]
    sesiones = []
    for _, item in seleccion:
        sesiones.extend(item.get("sesiones_agrupadas") or [item["id"]])
    # el id de CADA pendiente anterior, también el de un grupo intermedio:
    # quien lo reservó con ese id lo sigue encontrando (`sesiones_agrupadas`
    # cuenta sesiones; esto es solo para encontrar)
    anteriores = []
    for _, item in seleccion:
        anteriores.extend([item["id"]] + list(item.get("ids_anteriores") or ())
                          + list(item.get("sesiones_agrupadas") or ()))
    rec = dict(primero, id=uuid.uuid4().hex[:12],
               t=max(float(x[1].get("t") or 0) for x in seleccion),
               t_origen=min(float(x[1].get("t_origen") or x[1].get("t") or time.time()) for x in seleccion),
               ts=ultimo.get("ts"), engine=ultimo.get("engine"), sesion=ultimo.get("sesion"),
               view=_escribir_vista(_review_dir(brain), "\n\n".join(partes)),
               sesiones_agrupadas=list(dict.fromkeys(sesiones)),
               ids_anteriores=list(dict.fromkeys(anteriores)),
               intento=int(primero.get("intento") or 1))
    decisiones = []
    for _, item in seleccion:
        decision = item.get("decision")
        decisiones.extend(decision if isinstance(decision, list) else [decision] if decision else [])
    rec["decision"] = list(dict.fromkeys(decisiones))
    # Escribir primero: si falla, TODOS los pendientes originales siguen.
    _write_json(_pending_path(brain, clave, rec["id"]), rec)
    for ruta, item in seleccion:
        os.remove(ruta)
        _marcar_entregada(_id_de(item))  # una copia tardía de la nube no se vuelve a agrupar


def start_context(brain, data=None, env=None):
    """Texto para el contexto de arranque, o '' si no hay nada que entregar.
    Entrega UNO de la cola de ESTA pestaña (la repetición primero; o, sin
    pestaña, el pending.json de siempre, que toma la primera que abra), UNA
    vez, y solo si la pestaña no tiene ya una entregada sin comprobar: si la
    sesión que la recibió terminó sin su cierre (se cayó), se juzga aquí con
    lo que reportó. Antes archiva las propuestas que el agente ya resolvió.
    Si la vista del pendiente no está, NO se consume (_sin_vista). Todo bajo
    el candado del cerebro."""
    archivar_resueltas(brain)
    if os.environ.get("WORKSPACE_NO_SKILL_REVIEW") or not review_enabled(brain):
        return ""
    if en_monito(data, env):
        return ""                            # E1-a: en el monito, nunca; espera a su terminal o a la página
    pest = pestana_actual(data, env)
    if not os.environ.get("WORKSPACE_REVIEW_BATCH"):
        if (review_mode(brain, pest.get("motor")) != "on_open"
                or review_engine(brain, pest.get("motor")) != pest.get("motor")):
            return ""
    clave = clave_pestana(pest)
    d = _review_dir(brain)
    try:
        if not any(n.startswith(("pending", "delivered")) for n in os.listdir(d)):
            return ""
    except OSError:
        return ""

    def hacer():
        _ordenar(brain)
        dp = _delivered_path(brain, clave)
        rec, est = _leer_json(dp)
        if est == "error_lectura":           # NO es «sin entrega»: no se pisa con otra
            _log({"evento": "entrega_no_legible", "cerebro": os.path.basename(os.path.normpath(brain))})
            return ""
        if est == "ok" and rec.get("entregada_t"):
            receptora, actual = rec.get("sesion_receptora"), pest.get("sesion")
            panel_anterior = rec.get("via") == "panel" and (
                not receptora or (actual and receptora != actual))
            if (panel_anterior and not receptora
                    and str((data or {}).get("source") or "").lower() in ("compact", "resume")):
                return ""                    # la MISMA sesión, aún sin ligar: sigue viva
            if panel_anterior:
                # Al abrir no tenemos el transcript de la sesión que cayó:
                # ni un reporte ni un mtime aislado acreditan que la hizo.
                if not _retirar(brain, dp, rec, "sin_comprobar", "sesión del panel sin cierre"):
                    return ""
            elif receptora and actual and receptora != actual:
                if isinstance(rec.get("reporte"), dict):
                    # Sin el transcript de la sesión que cayó no se sabe QUIÉN escribió
                    # la skill (otra pestaña, la nube): el reporte no se acredita como
                    # «sí». Igual que en el panel: sin comprobar, y deja de bloquear.
                    if not _retirar(brain, dp, rec, "sin_comprobar", "sesión sin cierre"):
                        return ""
                else:
                    _juzgar(brain, dp, rec, "")      # sin reporte no hay «sí» que dar: 2.ª vez
            else:
                return ""                    # la misma sesión sigue con su revisión
        if not os.environ.get("WORKSPACE_REVIEW_BATCH"):
            _adoptar_del_monito(brain, clave, pest)      # lo que dejó el monito, ahora de esta pestaña
        batch_ids = set(str(os.environ.get("WORKSPACE_REVIEW_IDS") or "").split(","))
        if os.environ.get("WORKSPACE_REVIEW_BATCH") and clave:
            _agrupar_tanda(brain, clave, batch_ids)
        candidatos = [x[0] for x in _cola(brain, clave)
                      if not os.environ.get("WORKSPACE_REVIEW_BATCH")
                      or x[2].get("id") in batch_ids
                      or bool(set(x[2].get("sesiones_agrupadas") or ()) & batch_ids)
                      or bool(set(x[2].get("ids_anteriores") or ()) & batch_ids)] if clave else []
        candidatos.append(_pending_path(brain))
        for pp in candidatos:
            pending, est = _leer_json(pp)
            if est == "no_existe":
                continue
            if est == "ilegible":            # no es un pendiente: fuera, con rastro
                _ilegible(brain, pp)
                _aviso_cola(brain, "pendiente_no_legible")
                continue
            if est != "ok":                  # no se pudo leer (permisos, nube): se deja tal cual
                _log({"evento": "pendiente_no_legible",
                      "cerebro": os.path.basename(os.path.normpath(brain))})
                _aviso_cola(brain, "pendiente_no_legible")
                continue
            if os.path.basename(pp) == "pending.json" and clave and \
                    os.path.exists(_delivered_path(brain, "")):
                return ""
            return _entregar_pendiente(brain, pp, pending, pest)
        return ""
    return _bajo_candado(brain, CANDADO_ABRIR_S, hacer)


def _vincular_receptora_panel(brain, clave, pest):
    """Bajo candado: el primer mensaje identifica a la sesión del panel."""
    sesion = pest.get("sesion")
    if not sesion:
        return
    path = _delivered_path(brain, clave)
    rec, estado = _leer_json(path)
    if (estado == "ok" and rec.get("via") == "panel" and rec.get("entregada_t")
            and not rec.get("sesion_receptora")):
        rec["sesion_receptora"] = sesion
        _write_json(path, rec)


def mensaje_context(brain, data=None, env=None):
    """EN CADA MENSAJE (solo Claude Code emite este evento): si el socio pulsó
    «Hacer ahora» con la pestaña abierta (ocupada o con el foco), la tarea le
    llega aquí, UNA vez. Sin pendientes en el cerebro: un `listdir` y nada más."""
    try:
        d = _review_dir(brain)
        if not os.path.isdir(d) or not any(n.startswith(("pending", "delivered")) for n in os.listdir(d)):
            return ""
        if os.environ.get("WORKSPACE_NO_SKILL_REVIEW") or not review_enabled(brain):
            return ""
        if en_monito(data, env):
            return ""                        # E1-a: tampoco con «Hacer ahora»
        pest = pestana_actual(data, env)
        clave = clave_pestana(pest)
        if not clave:
            return ""

        def hacer():
            _vincular_receptora_panel(brain, clave, pest)
            for pp, _c, p2 in _cola(brain, clave):
                if p2.get("al_mensaje"):
                    return _entregar_pendiente(brain, pp, p2, pest, via="mensaje")
            return ""
        return _bajo_candado(brain, CANDADO_ABRIR_S, hacer)
    except Exception:
        return ""


def start_main():
    data = _stdin()
    try:
        txt = start_context(brain_root(data.get("cwd", "")), data)
        if txt:
            sys.stdout.write(json.dumps(
                {"hookSpecificOutput": {"hookEventName": "SessionStart",
                                        "additionalContext": txt}},
                ensure_ascii=False))
    except Exception:
        pass                             # jamás rompe el arranque
    return 0


# ── SE COMPRUEBA: ¿la revisión entregada dejó resultado? (0.9.1) ─────────────
#: El reporte EXPLÍCITO del agente (`workspace revision resultado …`) manda.
#: Sin él, solo cuenta el bloque 🧠 EXACTO que pide la tarea, dicho por el
#: agente DESPUÉS de la entrega, en ESA sesión (revisor 0.9.1, P1: antes
#: cualquier «🧠 check … review» o cualquier SKILL.md del cerebro contaban).
_SENAL = (
    ("creada", re.compile(r"🧠\s*Skill\s+(?:creada|created)\s*:\s*`([^`\n]+)`", re.I)),
    ("mejorada", re.compile(r"🧠\s*Skill\s+(?:mejorada|improved)\s*:\s*`([^`\n]+)`", re.I)),
    ("nada", re.compile(r"🧠\s*check\s*✓\s*[—–-]\s*(?:nada que aprender|revisi[oó]n sin cambios|"
                        r"nothing to learn|review: no changes)()", re.I)),
)
_SKILLS_FUERA = ("_archive", "_propuestas", ".git")
_REPORTES = ("creada", "mejorada", "nada")
_RESULTADO_DE = {"creada": "skill_creada", "mejorada": "skill_mejorada", "nada": "nada_que_aprender"}


def _epoch(ts):
    """La hora de un turno del transcript («2026-11-09T16:00:00.123Z» o local) →
    epoch, o None."""
    m = re.match(r"(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d)(\.\d+)?(Z|[+-]00:?00)?", str(ts or ""))
    if not m:
        return None
    try:
        st = time.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S")
    except ValueError:
        return None
    import calendar
    return float(calendar.timegm(st) if m.group(3) else time.mktime(st))


def _turnos_despues(transcript, desde, toda=False):
    """(turnos del agente con su hora ≥ desde, ¿el motor da sus herramientas?)
    de ESA sesión. Si el motor no anota horas, no se puede saber qué fue
    después: ([], …) — salvo `toda` (la sesión entera es posterior: la
    recibió al arrancar y es la misma que cierra)."""
    nt = _root_import("neutral_transcript")
    if nt is None or not transcript:
        return [], False
    try:
        doc = nt.ingest(transcript) or {}
    except Exception:
        return [], False
    turnos = doc.get("turns") or []
    con_herr = bool((doc.get("session") or {}).get("tools_recorded")) or any(
        t.get("tool_calls") for t in turnos)
    sin_horas = not any(_epoch(t.get("ts")) is not None for t in turnos)
    out = []
    for t in turnos:
        if t.get("role") == "user" or t.get("noise"):
            continue
        e = _epoch(t.get("ts"))
        if (e is not None and e >= desde) or (sin_horas and toda):
            out.append(dict(t, cwd=t.get("cwd") or (doc.get("session") or {}).get("cwd") or ""))
    return out, con_herr


def _skill_md(brain, skill):
    """La ruta del SKILL.md de `skill` («categoría/nombre» o «nombre») dentro de
    skills/, o ''."""
    skill = str(skill or "").strip().strip("/").replace("\\", "/")
    if not skill or ".." in skill.split("/"):
        return ""
    raiz = os.path.join(brain, "skills")
    directo = os.path.join(raiz, *skill.split("/"), "SKILL.md")
    if os.path.isfile(directo):
        return directo
    nombre = skill.split("/")[-1]
    for d, dirs, files in os.walk(raiz):
        dirs[:] = [x for x in dirs if x not in _SKILLS_FUERA and not x.startswith(".")]
        if os.path.basename(d) == nombre and "SKILL.md" in files:
            return os.path.join(d, "SKILL.md")
    return ""


def _cambio_tras(ruta, desde):
    try:
        return bool(ruta) and os.path.getmtime(ruta) >= desde
    except OSError:
        return False


def _la_escribio(turnos, ruta):
    """¿Una herramienta de escritura de esa sesión tocó ESE archivo?"""
    destino = os.path.normcase(os.path.realpath(ruta))
    escrituras = {"edit", "write", "multiedit", "notebookedit", "apply_patch",
                  "write_file", "edit_file", "create_file", "write_to_file",
                  "replace_in_file", "replace_string_in_file", "multi_replace_string_in_file",
                  "fs_write", "fswrite", "fs_edit", "fsedit", "str_replace_editor"}
    for t in turnos:
        for tc in t.get("tool_calls") or ():
            nombre = str(tc.get("name") or "").rsplit(".", 1)[-1].lower()
            if nombre not in escrituras:
                continue
            inp = tc.get("input") or {}
            if not isinstance(inp, dict):
                continue
            rutas = list(tc.get("files_touched") or ()) if nombre == "apply_patch" else []
            for k in ("file_path", "path", "notebook_path", "filePath", "target_file"):
                v = inp.get(k)
                if isinstance(v, str):
                    rutas.append(v)
            base = tc.get("cwd") or t.get("cwd")
            for v in rutas:
                if not isinstance(v, str):
                    continue
                if not os.path.isabs(v):
                    if not isinstance(base, str) or not os.path.isabs(base):
                        continue             # sin cwd registrado, no se usa el del hook
                    v = os.path.join(base, v)
                if os.path.normcase(os.path.realpath(v)) == destino:
                    return True
    return False


def _verificar(brain, rec, resultado, skill, turnos, con_herr):
    """(resultado de la bitácora, detalle) si el reporte se sostiene, o None.
    «creada»/«mejorada» exigen que ESE SKILL.md haya cambiado después de la
    entrega y, si el motor da sus herramientas, que lo escribiera esa sesión
    después de la entrega. Nunca un mtime suelto del cerebro."""
    if resultado == "nada":
        return "nada_que_aprender", ""
    if not con_herr:
        return "sin_comprobar", "sin_autoria"  # termina la cola, nunca acredita un «sí»
    desde = float(rec.get("entregada_t") or 0) - HOLGURA_S
    ruta = _skill_md(brain, skill)
    if not _cambio_tras(ruta, desde):
        return None
    if con_herr and not _la_escribio(turnos, ruta):
        return None
    if resultado == "creada":
        try:
            todos = [os.path.getmtime(os.path.join(os.path.dirname(ruta), f))
                     for f in os.listdir(os.path.dirname(ruta))]
        except OSError:
            todos = []
        if todos and min(todos) < desde:
            resultado = "mejorada"           # la carpeta ya existía: es una mejora
    return _RESULTADO_DE[resultado], os.path.basename(os.path.dirname(ruta))


def _juzgar(brain, ruta, rec, transcript, ahora=None, sesion=""):
    """Juzga UNA entrega: con el reporte del agente (o, sin él, su 🧠 exacto
    después de la entrega en ESA sesión). Con resultado: «¿pasó?» sí. Sin él:
    vuelve a la cola UNA vez («repetida»; el hub la muestra); la segunda,
    «no se hizo». → el resultado ('repetida', 'no_se_hizo' o el de la skill)."""
    ahora = time.time() if ahora is None else ahora
    desde = float(rec.get("entregada_t") or 0) - HOLGURA_S
    toda = bool(sesion) and rec.get("sesion_receptora") == sesion and \
        rec.get("via", "arranque") == "arranque"
    turnos, con_herr = _turnos_despues(transcript, desde, toda)
    hallado = None
    rep = rec.get("reporte") if isinstance(rec.get("reporte"), dict) else None
    if rep and rep.get("resultado") in _REPORTES:
        hallado = _verificar(brain, rec, rep["resultado"], rep.get("skill"), turnos, con_herr)
    if hallado is None and not rep:
        for t in turnos:
            txt = t.get("text") or ""
            if "🧠" not in txt:
                continue
            for res, rx in _SENAL:
                m = rx.search(txt)
                if m:
                    hallado = _verificar(brain, rec, res, m.group(1), turnos, con_herr)
                    break
            if hallado:
                break
    clave = rec.get("clave") or _clave_de(ruta)
    try:
        if hallado:
            os.remove(ruta)
            _resultado(rec.get("decision"), hallado[0], detalle=hallado[1])
            fin = hallado[0]
        else:
            intento = int(rec.get("intento") or 1)
            if intento < INTENTOS:
                nuevo = {k: v for k, v in rec.items()
                         if k not in ("entregada_t", "via", "sesion_receptora", "motor_receptor",
                                      "wid_receptor", "clave", "reporte")}
                nuevo.update(id=uuid.uuid4().hex[:12], intento=intento + 1, repetida=True,
                             repetida_t=round(ahora, 3), t=round(ahora, 3),
                             t_origen=rec.get("t_origen") or rec.get("t"))
                _write_json(_pending_path(brain, clave, nuevo["id"]) if clave
                            else _pending_path(brain), nuevo)
                os.remove(ruta)
                _resultado(rec.get("decision"), "pendiente",
                           detalle="2.ª vez" if not rep else "2.ª vez: el reporte no se sostuvo")
                fin = "repetida"
            else:
                os.remove(ruta)
                _resultado(rec.get("decision"), "no_se_hizo", detalle="%d veces" % intento)
                fin = "no_se_hizo"
    except OSError:
        return ""
    if fin != "repetida":
        _quitar_vista(os.path.dirname(ruta), rec.get("view"))
    try:
        os.remove(_tarea_path(brain, clave))
    except OSError:
        pass
    if rec.get("tanda"):
        visible = _root_import("skill_review_visible")
        try:
            if visible is not None:
                carga = {"brain": brain, "clave": clave,
                    "resultado": fin, "skill": (rep or {}).get("skill") or "",
                    "detalle": hallado[1] if hallado else ""}
                if isinstance(rec.get("indice"), int):
                    carga["indice"] = rec["indice"]
                visible.proved(rec["tanda"], carga, turnos)
        except Exception:
            pass  # comprobar sigue siendo independiente del panel
    _log({"evento": "revision_comprobada", "cerebro": os.path.basename(os.path.normpath(brain)),
          "resultado": fin})
    return fin


def comprobar(brain, pest=None, transcript="", ahora=None):
    """Al cerrar una sesión del cerebro: la revisión ENTREGADA a esta pestaña
    (o a esta sesión) se juzga AHORA, cuando termina la sesión que la recibió
    — nunca a las 24 h con la pestaña abierta (revisor 0.9.1, P2). Las que
    nadie cierra vencen a los 7 días (_ordenar). → [(clave, resultado)]."""
    d = _review_dir(brain)
    try:
        todos = os.listdir(d)
    except OSError:
        return []
    nombres = [n for n in todos if n.startswith("delivered") and n.endswith(".json")]
    if not nombres and not any(n.startswith("pending") for n in todos):
        return []                            # nada que juzgar ni que vencer
    pest = pest or {}
    out = []

    def hacer():
        for n in nombres:
            p = os.path.join(d, n)
            rec, est = _leer_json(p)
            if est != "ok" or not rec.get("entregada_t"):
                continue                     # una entrega de antes de la 0.9.1: no se juzga
            clave = _clave_de(n)
            mia = ((rec.get("wid_receptor") and rec.get("wid_receptor") == pest.get("wid"))
                   or (rec.get("sesion_receptora") and rec.get("sesion_receptora") == pest.get("sesion"))
                   or (clave and clave == clave_pestana(pest))
                   or (not clave and not clave_pestana(pest)))     # sin pestaña: la siguiente sin pestaña
            if mia:
                fin = _juzgar(brain, p, rec, transcript, ahora, pest.get("sesion") or "")
                if fin:
                    out.append((clave, fin))
        _ordenar(brain, ahora)
        return out
    return _bajo_candado(brain, CANDADO_CIERRE_S, hacer, defecto=[])


# ── el reporte explícito: `workspace revision resultado …` ──────────────────
#: Sin clave de pestaña ni id de entrega: lo que se le dice al agente.
SIN_ID = ("falta el id de la entrega: está en el texto de tu tarea de revisión. Repórtalo con "
          "workspace revision resultado --entrega <id> creada|mejorada|nada [<categoría>/<skill>]")


def _por_entrega(brain, entrega):
    """La clave de la entrega ACTIVA con ese id en ESTE cerebro → (clave, error).
    Un id que no está (o ya se juzgó y cerró) se dice tal cual."""
    if not _ENTREGA_RE.fullmatch(entrega):
        return None, "ese id de entrega no tiene forma de id: cópialo tal cual de tu tarea"
    hits = []
    try:
        nombres = os.listdir(_review_dir(brain))
    except OSError:
        nombres = []
    for name in nombres:
        if not (name.startswith("delivered") and name.endswith(".json")):
            continue
        item, status = _leer_json(os.path.join(_review_dir(brain), name))
        if status == "ok" and item.get("entregada_t") and str(item.get("id") or "") == entrega:
            hits.append(_clave_de(name))
    if len(hits) == 1:
        return hits[0], ""
    if hits:
        return None, "hay más de una revisión entregada con el id %s: no reporto a ciegas" % entrega
    return None, ("no hay ninguna revisión de skills abierta con el id %s en este agente "
                  "(no existe o ya se cerró): no anoté nada" % entrega)


def _dueno_sin_clave(brain, pest):
    """Sin clave de pestaña: (usar, clave, error). Con id de entrega, ESA
    entrega (validada en este cerebro); con id de sesión, la única entrega de
    esa sesión. Sin ninguno, solo la «sin pestaña» de siempre (delivered.json,
    la que se entregó también sin clave): una entrega con clave NO se reclama,
    que haya una sola no demuestra de quién es."""
    pest = pest or {}
    sesion = str(pest.get("sesion") or "").strip()
    entrega = str(pest.get("entrega") or "").strip()
    if entrega:
        clave, err = _por_entrega(brain, entrega)
        return (clave is not None), (clave or ""), err
    if not sesion:
        rec, est = _leer_json(_delivered_path(brain, ""))
        if est == "ok" and rec.get("entregada_t"):
            return True, "", ""
        return False, "", SIN_ID
    hits = []
    try:
        nombres = os.listdir(_review_dir(brain))
    except OSError:
        return False, "", SIN_ID
    for name in nombres:
        if not (name.startswith("delivered") and name.endswith(".json")):
            continue
        item, status = _leer_json(os.path.join(_review_dir(brain), name))
        if status == "ok" and item.get("entregada_t") and item.get("sesion_receptora") == sesion:
            hits.append(_clave_de(name))
    if len(hits) != 1:
        return False, "", SIN_ID
    return True, hits[0], ""


def reportar(brain, pest, resultado, skill="", entrega=""):
    """El agente dice qué dejó la revisión que recibió ESTA pestaña. Se valida
    en el acto (la skill existe y cambió después de la entrega) y se guarda en
    la entrega; el juicio final es al cerrar la sesión. `entrega` = el id que
    trae el texto de la tarea: identifica la revisión aunque el motor no
    exporte la clave de su pestaña. → (ok, mensaje)."""
    resultado = str(resultado or "").strip().lower()
    if resultado not in _REPORTES:
        return False, "resultado tiene que ser creada, mejorada o nada"
    if resultado != "nada" and not str(skill or "").strip():
        return False, "falta la skill: workspace revision resultado %s <categoría>/<skill>" % resultado
    entrega = str(entrega or (pest or {}).get("entrega") or "").strip()
    clave = clave_pestana(pest or {})
    if entrega:
        # el id manda: es la prueba de que esta sesión recibió ESA tarea
        por_id, err = _por_entrega(brain, entrega)
        if por_id is None:
            return False, err
        if clave and por_id != clave:
            return False, ("el id %s es de la revisión de otra pestaña, no de esta: no anoté nada"
                           % entrega)
        clave = por_id
    elif not clave:
        usar, clave, err = _dueno_sin_clave(brain, pest)
        if not usar:
            return False, err
    dp = _delivered_path(brain, clave)

    def hacer():
        rec, est = _leer_json(dp)
        if est != "ok" or not rec.get("entregada_t"):
            if entrega:
                return False, ("no hay ninguna revisión de skills abierta con el id %s en este "
                               "agente (no existe o ya se cerró): no anoté nada" % entrega)
            return False, "esta pestaña no tiene una revisión de skills entregada"
        if entrega and str(rec.get("id") or "") != entrega:
            return False, ("la revisión de esa pestaña cambió mientras reportabas (ya no es la %s): "
                           "no anoté nada" % entrega)
        if resultado != "nada":
            ruta = _skill_md(brain, skill)
            if not ruta:
                return False, "no encuentro skills/…/%s/SKILL.md" % skill
            if not _cambio_tras(ruta, float(rec["entregada_t"]) - HOLGURA_S):
                return False, ("%s no cambió después de que recibiste la revisión: guárdala primero"
                               % os.path.relpath(ruta, brain).replace("\\", "/"))
        rec["reporte"] = {"resultado": resultado, "skill": str(skill or "")[:120],
                          "t": round(time.time(), 3)}
        _write_json(dp, rec)
        return True, "anotado: Workspace lo comprueba al cerrar esta sesión"
    return _bajo_candado(brain, CANDADO_ABRIR_S, hacer,
                         defecto=(False, "otro proceso usa la revisión; inténtalo de nuevo"))


def cli(argv=None):
    """`workspace revision resultado [--entrega <id>] <creada|mejorada|nada> [<categoría>/<skill>]`."""
    args = list(sys.argv[1:] if argv is None else argv)
    entrega, resto, i = "", [], 0
    while i < len(args):                       # --entrega en cualquier lugar (también --entrega=x)
        a = args[i]
        if a == "--entrega":
            entrega = args[i + 1] if i + 1 < len(args) else ""
            i += 2
            continue
        if a.startswith("--entrega="):
            entrega = a.split("=", 1)[1]
            i += 1
            continue
        resto.append(a)
        i += 1
    args = resto
    uso = ("uso: workspace revision resultado [--entrega <id>] creada|mejorada|nada "
           "[<categoría>/<skill>]   (el id está en el texto de tu tarea de revisión)")
    if len(args) < 2 or args[0] not in ("resultado", "result") or args[1] in ("-h", "--help"):
        print(uso)
        return 0 if args[1:2] in (["-h"], ["--help"]) else 2
    brain = brain_root(os.getcwd())
    if os.environ.get("WORKSPACE_NO_SKILL_REVIEW") or not review_enabled(brain):
        print("la revisión de skills está apagada para este agente")
        return 2
    ok, msg = reportar(brain, pestana_actual({}), args[1], args[2] if len(args) > 2 else "",
                       entrega=entrega)
    print(msg)
    return 0 if ok else 2


# ── el hub: «1 revisión de skills pendiente · Hacer ahora» ──────────────────
def _avisos_dir():
    return os.path.join(_state_dir(), "skill-review-notices")


def _aviso_cola(brain, motivo):
    """Rastro local independiente del candado: nunca modifica la cola.

    Un aviso por cerebro y motivo limita el tamaño y evita pisar avisos de
    otros cerebros. No guarda conversación ni mensajes de excepción.
    """
    try:
        key = hashlib.sha256(os.path.abspath(brain).encode("utf-8")).hexdigest()[:24]
        _write_json(os.path.join(_avisos_dir(), key + "-" + motivo + ".json"),
                    {"brain": os.path.abspath(brain), "motivo": motivo, "t": time.time()})
    except Exception:
        pass


def avisos_hub(agentes):
    """Avisos persistentes durante siete días, solo de cerebros del hub."""
    brains = {os.path.abspath(a["brain"]) for a in agentes or () if a.get("brain")}
    textos = {
        "lanzamiento_fallido": ("hub.skills_pend.launch_failed",
            "Revisión de skills: no se pudo abrir la pestaña; la revisión sigue pendiente."),
        "pendiente_no_legible": ("hub.skills_pend.unreadable_queue",
            "Revisión de skills: no se pudo leer un pendiente; los demás siguen."),
        "cola_sin_candado": ("hub.skills_pend.lock_failed",
            "Revisión de skills: no se pudo guardar una revisión porque la cola estaba ocupada.")}
    out = []
    try:
        nombres = os.listdir(_avisos_dir())
    except OSError:
        return out
    for n in nombres:
        if not n.endswith(".json"):
            continue
        rec, est = _leer_json(os.path.join(_avisos_dir(), n))
        if est != "ok" or rec.get("brain") not in brains or rec.get("motivo") not in textos:
            continue
        try:
            if time.time() - float(rec["t"]) > VENCE_SECONDS:
                continue
        except (KeyError, TypeError, ValueError):
            continue
        key, es = textos[rec["motivo"]]
        out.append(dict(rec, texto=_tt(key, es)))
    return sorted(out, key=lambda x: x["t"], reverse=True)


TANDA_MAX = 3


def plan_tanda(agentes, ahora=None, modos=None, clave=None, excluir=()):
    """Fotografía de costo ANTES de lanzar; no consume ni entrega nada.

    La unidad es una pestaña, aunque tenga varias sesiones pendientes. La
    estimación incluye una reserva de lectura/razonamiento de 15 mil tokens
    por revisión: no es una factura ni un límite duro del motor.
    """
    ahora = time.time() if ahora is None else ahora
    grupos = []
    filtro_clave = clave
    vistos = set()
    for a in agentes or ():
        brain = str(a.get("brain") or "")
        if not brain or brain in vistos or not review_enabled(brain):
            continue
        vistos.add(brain)
        por = {}
        for ruta, clave, rec in _pendientes(brain):
            if _ya_entregada(brain, rec) or _retirada_local(rec) or _entrega_activa(brain, clave):
                continue
            if ahora - float(rec.get("t_origen") or rec.get("t") or ahora) > VENCE_SECONDS:
                continue
            view = _vista_vigente(brain, rec.get("view"))
            if not view:
                continue
            try:
                caracteres = os.path.getsize(view)  # estimación conservadora UTF-8; no releer la sesión en cada frame
            except (OSError, UnicodeError):
                _aviso_cola(brain, "pendiente_no_legible")
                continue
            cohorte = (clave, int(rec.get("intento") or 1), bool(rec.get("repetida")))
            g = por.setdefault(cohorte, {"brain": brain, "clave": clave, "ids": [],
                "agente": a.get("name") or rec.get("agente") or "", "wid": rec.get("wid") or "",
                "pestana": rec.get("pestana") or "", "motor": review_engine(brain, rec.get("engine")),
                "t": float(rec.get("t_origen") or rec.get("t") or ahora), "tokens": 15000})
            g["ids"].append(rec["id"])
            g["tokens"] += (caracteres + 3) // 4
        grupos.extend(g for g in por.values()
                      if (modos is None or review_mode(brain, g["motor"]) in modos)
                      and (filtro_clave is None or g["clave"] == filtro_clave))
    grupos = [g for g in grupos if (g["brain"], g["clave"]) not in excluir]
    grupos.sort(key=lambda g: (g["t"], g["brain"], g["clave"]))
    tanda = grupos[:TANDA_MAX]
    return {"total": len(grupos), "tokens": sum(g["tokens"] for g in grupos),
            "batch_tokens": sum(g["tokens"] for g in tanda), "revisiones": tanda,
            "restantes": max(0, len(grupos) - len(tanda))}


def pendientes_hub(agentes):
    """Por pestaña con una revisión que volvió a pendiente (sin resultado la
    1.ª vez): [{agente, display, brain, clave, wid, pestana, motor,
    origen_t, al_mensaje, n}] — `n`: cuántas hay en su cola. Barato: un
    `listdir` por cerebro; con la revisión apagada, nada."""
    out = []
    if os.environ.get("WORKSPACE_NO_SKILL_REVIEW"):
        return out
    for a in agentes or ():
        brain = str((a or {}).get("brain") or "")
        d = _review_dir(brain) if brain else ""
        try:
            if not any(n.startswith("pending") for n in os.listdir(d)):
                continue
        except OSError:
            continue
        if not review_enabled(brain):
            continue
        por = {}
        for ruta, clave, rec in _pendientes(brain):
            if _ya_entregada(brain, rec):
                continue
            por.setdefault(clave, []).append(rec)
        for clave, recs in sorted(por.items()):
            if all(_del_monito(r) for r in recs):
                continue                     # del monito: la recibe su terminal o la página al abrir
            rep = [r for r in recs if r.get("repetida")]
            seed = (rep or recs)[0]
            batch_mode = review_mode(brain, seed.get("engine")) in ("button", "on_close")
            if not rep and not batch_mode:
                continue
            r0 = (rep or recs)[0]
            out.append({"agente": a.get("name") or r0.get("agente") or "",
                        "display": a.get("display") or a.get("name") or r0.get("agente") or "",
                        "brain": brain, "clave": clave, "wid": r0.get("wid") or "",
                        "pestana": r0.get("pestana") or "", "motor": r0.get("engine") or "",
                        "origen_t": _desde_creacion(dict(r0, t=r0.get("t_origen") or r0.get("t"))),
                        "al_mensaje": bool(r0.get("al_mensaje")), "n": len(recs), "batch": batch_mode})
    return out


#: La línea que «Hacer ahora» le escribe al agente en su panel (sin nada que
#: una shell o la entrada de un motor interprete: aviso_panel._RARO).
LINEA_PANEL = ("Workspace: el socio pulsó Hacer ahora. Tienes una revisión de skills pendiente, la "
               "segunda y última vez: lee {ruta} y hazla antes de seguir.")
#: Los motores que reciben la tarea con el siguiente mensaje (user_prompt):
#: solo Claude Code emite ese evento (neutral_hooks).
CON_MENSAJE = ("claude-code",)


def _tt(key, es, **kw):
    """Lo que lee el socio en el hub, en su idioma (i18n de la raíz); sin él,
    el español."""
    s = es
    i18n = _root_import("i18n")
    if i18n is not None:
        try:
            v = i18n.t(key)
            s = v if v != key else es
        except Exception:
            s = es
    try:
        return s.format(**kw) if kw else s
    except Exception:
        return s


def _tarea_path(brain, clave):
    return os.path.join(_review_dir(brain), "tarea-%s.md" % (clave or "sin-pestana"))


def _entrada_vacia(ap, reg, motor):
    """¿La línea de entrada del motor está VACÍA? Se lee el panel (`herdr pane
    read`): en Claude Code, la línea «❯» entre dos reglas «───». True solo si
    está vacía con certeza; False si tiene algo; None si no se sabe (otro
    motor, otra forma de pantalla, herdr no contesta). Sin certeza no se
    escribe: podría caer sobre un borrador del socio (revisor 0.9.1, P2)."""
    if motor != "claude-code":
        return None
    try:
        texto = ap.leer(reg, 40)
    except Exception:
        return None
    if not texto:
        return None
    lineas = [ln.rstrip() for ln in texto.split("\n")]
    regla = re.compile(r"^\s*─{10,}")
    for i in range(len(lineas) - 2, 0, -1):
        m = re.match(r"^\s*❯\s?(.*)$", lineas[i])
        if m and regla.match(lineas[i - 1]):
            if not regla.match(lineas[i + 1]):
                return False                 # varias líneas escritas
            return not m.group(1).strip()
    return None


def hacer_ahora(brain, clave, agente=""):
    """«Hacer ahora» en el hub, para la revisión repetida de la pestaña `clave`:
      · abierta en su panel, quieta, sin el foco y con la línea de entrada
        VACÍA (se vuelve a mirar todo bajo el candado, justo antes de
        escribir): primero el archivo de la tarea, luego la línea en su
        panel, y solo si herdr la aceptó queda entregada. Si algo falla, el
        pendiente queda intacto y se dice;
      · abierta en Claude Code (ocupada, con el foco o con algo escrito): le
        llega con su próximo mensaje (mensaje_context);
      · abierta en otro motor: la recibe al volver a abrirla (se dice tal cual);
      · cerrada → el hub la abre en ESA pestaña y la recibe al arrancar.
    → {"accion": escrita|al_mensaje|abrir|nada, "msg", "agente", "args"}."""
    if _entrega_activa(brain, clave):
        return {"accion": "nada", "msg": _tt(
            "hub.skills_pend.active", "esta pestaña ya tiene una revisión por terminar: la siguiente espera")}
    cola = [x for x in _cola(brain, clave) if not _ya_entregada(brain, x[2])]
    if not cola:
        return {"accion": "nada", "msg": _tt("hub.skills_pend.gone", "ya no está pendiente")}
    pp, _c, pending = cola[0]
    if _del_monito(pending):
        return {"accion": "nada", "msg": _tt(
            "hub.skills_pend.monito", "es de su conversación de Compañero: la recibe la próxima vez que lo abras en "
            "su terminal o en la página")}
    agente = agente or pending.get("agente") or ""
    wid, nombre = str(pending.get("wid") or ""), str(pending.get("pestana") or "")
    quien = "%s «%s»" % (agente.capitalize(), nombre) if nombre else agente.capitalize()
    ap = _root_import("aviso_panel")
    reg = ap.panel_de("%s--%s" % (agente, wid)) if (ap is not None and wid and agente) else None
    ep = ap.estado_panel(reg) if reg else {"ok": False}
    motor = (reg or {}).get("motor") if ep.get("ok") else ""
    abierta = bool(ep.get("ok"))
    if not abierta and nombre:
        sr = _root_import("sessions_registry")
        try:
            abierta = sr is not None and sr._slug(nombre) in sr.abiertas_en_ventanas(brain)
        except Exception:
            abierta = False
    if ep.get("ok") and ep.get("quieto") and not ep.get("foco") and motor == "claude-code":
        res = {}

        def escribir():
            if _entrega_activa(brain, clave):
                res["r"] = {"accion": "nada", "msg": _tt(
                    "hub.skills_pend.active", "esta pestaña ya tiene una revisión por terminar: la siguiente espera")}
                return
            if _leer_json(_delivered_path(brain, clave))[1] == "error_lectura":
                res["r"] = {"accion": "nada", "msg": _tt(     # antes de teclear: no se pisa
                    "hub.skills_pend.unreadable",
                    "no pude leer la entrega anterior: queda pendiente")}
                return
            p2, e2 = _leer_json(pp)
            if e2 != "ok" or _ya_entregada(brain, p2):
                res["r"] = {"accion": "nada", "msg": _tt("hub.skills_pend.gone",
                                                        "ya no está pendiente")}
                return
            view = _vista_vigente(brain, p2.get("view"))
            task = _tarea(brain, p2, view) if view else None
            if not task:
                res["r"] = {"accion": "nada", "msg": _tt("hub.skills_pend.no_view",
                                                        "su vista ya no está: queda pendiente")}
                return
            tarea = _tarea_path(brain, clave)
            try:                                       # fase 1: la tarea, en disco
                _escribir(tarea, task)
            except OSError:
                res["r"] = {"accion": "nada", "msg": _tt(
                    "hub.skills_pend.no_task", "no pude escribir la tarea: queda pendiente")}
                return
            ep2 = ap.estado_panel(reg)                 # otra vez, justo antes de escribir
            vacia = _entrada_vacia(ap, reg, motor) if ep2.get("ok") else None
            if not (ep2.get("ok") and ep2.get("quieto") and not ep2.get("foco")) or vacia is not True:
                try:
                    os.remove(tarea)
                except OSError:
                    pass
                if vacia is False:
                    msg = _tt("hub.skills_pend.typed", "{q} tiene algo escrito en su panel: ábrela "
                              "tú; la revisión sigue pendiente", q=quien)
                else:
                    msg = _tt("hub.skills_pend.unsure", "{q} no está quieta o no puedo ver si tiene "
                              "algo escrito: ábrela tú; la revisión sigue pendiente", q=quien)
                res["r"] = {"accion": "nada", "msg": msg}
                return
            linea = LINEA_PANEL.format(ruta=os.path.relpath(tarea, brain).replace("\\", "/"))
            if not ap.escribir(reg, linea):            # fase 2: el panel
                try:
                    os.remove(tarea)
                except OSError:
                    pass
                res["r"] = {"accion": "nada", "msg": _tt(
                    "hub.skills_pend.herdr", "herdr no aceptó el texto: ábrela tú; la revisión "
                    "sigue pendiente")}
                return
            pest = {"wid": wid, "nombre": nombre, "agente": agente, "motor": motor, "sesion": ""}
            if not _entregar_pendiente(brain, pp, p2, pest, via="panel"):   # solo si se escribió
                # la línea YA está en el panel y la entrega no quedó registrada: no se
                # dice «escrita»; se cuenta tal cual (puede repetirse)
                res["r"] = {"accion": "nada", "msg": _tt(
                    "hub.skills_pend.unrecorded", "le escribí la tarea a {q}, pero no pude registrar "
                    "la entrega: la revisión puede repetirse", q=quien)}
                return
            res["r"] = {"accion": "escrita", "msg": _tt(
                "hub.skills_pend.written", "le escribí la tarea a {q} en su panel", q=quien)}
        _bajo_candado(brain, CANDADO_ABRIR_S, escribir)
        return res.get("r") or {"accion": "nada", "msg": _tt(
            "hub.skills_pend.busy", "otro proceso la está entregando: prueba en un momento")}
    if abierta and (motor or pending.get("engine") or "claude-code") in CON_MENSAJE:
        def marcar():
            if _entrega_activa(brain, clave):
                return False
            p2, e2 = _leer_json(pp)
            if e2 == "ok":
                p2["al_mensaje"] = True
                _write_json(pp, p2)
                return True
            return False
        if not _bajo_candado(brain, CANDADO_ABRIR_S, marcar, defecto=False):
            return {"accion": "nada", "msg": _tt(
                "hub.skills_pend.busy", "otro proceso la está entregando: prueba en un momento")}
        return {"accion": "al_mensaje", "msg": _tt(
            "hub.skills_pend.next_msg", "{q} tiene la pestaña abierta: la tarea le llega con tu "
            "próximo mensaje ahí", q=quien)}
    if abierta:
        return {"accion": "nada", "msg": _tt(
            "hub.skills_pend.other_engine", "{q} está abierta en {m}: la recibe al volver a "
            "abrirla (ciérrala y pulsa Hacer ahora)", q=quien,
            m=motor or pending.get("engine") or "?")}
    if wid and nombre and agente:
        return {"accion": "abrir", "agente": agente, "args": ["--open", wid, "--name", nombre],
                "msg": _tt("hub.skills_pend.opening", "abriendo {q} con la tarea", q=quien)}
    return {"accion": "nada", "msg": _tt("hub.skills_pend.from_agents", "ábrela desde Agentes: la "
                                         "tarea le llega al arrancar")}


def hacer_ahora_por_control(brain, clave, mandar, pest=None):
    """«Hacer ahora» desde la página (F6): la tarea de la revisión de la pestaña `clave` le llega al
    agente por la capa de control (`mandar(texto)`: su misma conversación, su mismo motor), sin leer
    ni teclear en su panel. El mismo orden que en el hub: primero la tarea en disco, luego el mensaje
    y, solo si salió, la entrega queda registrada; si no sale, el pendiente queda intacto. `mandar`
    levanta si no pudo. `pest`: {wid, nombre, agente, motor} de quien la recibe.
    → {"accion": "mandada"|"nada", "msg"}."""
    if _entrega_activa(brain, clave):
        return {"accion": "nada", "msg": _tt(
            "hub.skills_pend.active", "esta pestaña ya tiene una revisión por terminar: la siguiente espera")}
    cola = [x for x in _cola(brain, clave) if not _ya_entregada(brain, x[2])]
    if not cola:
        return {"accion": "nada", "msg": _tt("hub.skills_pend.gone", "ya no está pendiente")}
    pp = cola[0][0]
    pest = dict({"wid": "", "nombre": "", "agente": "", "motor": "", "sesion": ""}, **(pest or {}))
    if str(pest.get("nombre") or "").strip() == MONITO or _del_monito(cola[0][2]):
        return {"accion": "nada", "msg": "en Compañero no se hace la revisión de skills: espera a su terminal o a "
                                         "la página"}
    res = {}

    def entregar():
        if _entrega_activa(brain, clave) or _leer_json(_delivered_path(brain, clave))[1] == "error_lectura":
            res["r"] = {"accion": "nada", "msg": _tt(
                "hub.skills_pend.active", "esta pestaña ya tiene una revisión por terminar: la siguiente espera")}
            return
        p2, e2 = _leer_json(pp)
        if e2 != "ok" or _ya_entregada(brain, p2):
            res["r"] = {"accion": "nada", "msg": _tt("hub.skills_pend.gone", "ya no está pendiente")}
            return
        view = _vista_vigente(brain, p2.get("view"))
        task = _tarea(brain, p2, view) if view else None
        if not task:
            res["r"] = {"accion": "nada", "msg": _tt("hub.skills_pend.no_view",
                                                    "su vista ya no está: queda pendiente")}
            return
        tarea = _tarea_path(brain, clave)
        try:                                           # fase 1: la tarea, en disco
            _escribir(tarea, task)
        except OSError:
            res["r"] = {"accion": "nada", "msg": _tt(
                "hub.skills_pend.no_task", "no pude escribir la tarea: queda pendiente")}
            return
        try:                                           # fase 2: por la capa de control
            mandar(LINEA_PANEL.format(ruta=os.path.relpath(tarea, brain).replace("\\", "/")))
        except Exception as e:
            try:
                os.remove(tarea)
            except OSError:
                pass
            res["r"] = {"accion": "nada", "msg": "no salió (%s): la revisión sigue pendiente" % e}
            return
        if not _entregar_pendiente(brain, pp, p2, pest, via="control"):
            res["r"] = {"accion": "nada", "msg": _tt(
                "hub.skills_pend.unrecorded", "le escribí la tarea a {q}, pero no pude registrar "
                "la entrega: la revisión puede repetirse", q=pest.get("agente") or "")}
            return
        res["r"] = {"accion": "mandada", "msg": "le mandé la revisión de skills"}
    _bajo_candado(brain, CANDADO_ABRIR_S, entregar)
    return res.get("r") or {"accion": "nada", "msg": _tt(
        "hub.skills_pend.busy", "otro proceso la está entregando: prueba en un momento")}


if __name__ == "__main__":
    main()
