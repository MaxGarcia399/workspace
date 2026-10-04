#!/usr/bin/env python3
"""WORKSPACE · heartbeat — control central de la cola de trabajo autónomo.

El "heartbeat" es el pulso del plan de saturación 20X: cuando el socio está ausente, un cron
despierta a Opus, que consulta ESTE módulo para saber si puede lanzar trabajo
de la cola (`research/auto-backlog.md`) sin reventar el presupuesto del plan
5h (`~/.claude/workspace/usage.json`, lo escribe la statusline).

Qué ES este módulo: la fuente de verdad de modo + presupuesto + cola, y el
árbitro (`decide()`) que dice la acción canónica. Qué NO es: un lanzador —
heartbeat NUNCA lanza nada por sí mismo; el lanzamiento lo hace Opus (el cron),
que además es quien SABE si el socio está activo (`idle_ok`) y si ya corre un agente
(`has_running`) — este módulo no adivina la actividad del socio.

Config (`~/.claude/workspace/heartbeat.json`, falla-suave si falta):
    {"mode": "auto"|"manual"|"off", "budget_cap_pct": 85, "grace_min": 12,
     "quiet_hours": "HH:MM-HH:MM"}
  Desde el settings unificado (settings.py) también se puede configurar como
  `latido.mode` / `latido.budget_cap_pct` / `latido.grace_min` /
  `latido.quiet_hours`. Precedencia: defaults < settings < heartbeat.json
  (el archivo histórico GANA mientras exista; `settings set latido.*` lo
  sincroniza para no divergir).
  - mode auto   → el cron puede lanzar solo.
  - mode manual → el heartbeat solo reporta; lanzar queda en manos del socio.
  - mode off    → apagado total.
  - budget_cap_pct → colchón: con `five_hour_pct >=` este tope, pausa.
  - grace_min   → minutos de gracia tras actividad del socio (la aplica el cron).
  - quiet_hours → rango (puede cruzar medianoche) en que decide() devuelve
    "quiet" — sin lanzamientos autónomos; vacío/inválido = sin silencio.
  Además decide() respeta el flag del job `heartbeat-cron` (settings jobs):
  con el job off devuelve "off" — el toggle de CRONS del config es real.

API: get_mode() · set_mode(m) · get_config() · budget_ok() · next_task() ·
pending_tasks() · reorder(move=…|order=…) · decide(mode, budget_ok,
has_running, idle_ok[, agent]) · state()

CLI:  python3 heartbeat.py status        ← resumen humano
      python3 heartbeat.py state|--json  ← state() en JSON (para UIs/cron)
      python3 heartbeat.py auto|manual|off  ← cambia el modo

Stdlib puro, cross-platform (3.9+), read-mostly (solo escribe SU config),
amputable: borrar este archivo no rompe nada más (todos sus consumidores lo
importan falla-suave).
"""
import datetime
import hashlib
import json
import os
import re
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))

# Lock N8 (R3-F2) para el RMW del backlog — falla-suave (mismo patrón que
# messages.py/dream.py): sin olock, reorder sigue funcionando sin lock.
try:
    from olock import file_lock
except Exception:
    file_lock = None

VALID_MODES = ("auto", "manual", "off")
DEFAULTS = {"mode": "auto", "budget_cap_pct": 85, "grace_min": 12,
            "quiet_hours": ""}
CAP_RANGE_FALLBACK = (50, 95)  # espejo del SETTINGS_SCHEMA (latido.budget_cap_pct)
USAGE_STALE_SEC = 20 * 60      # usage.json con stamped más viejo = desconocido

# "HH:MM-HH:MM" (24h). Parser canónico abajo (parse_quiet_hours); settings.py
# lleva un espejo (_QUIET_RX) solo para rechazar basura al ESCRIBIR.
_QUIET_RE = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)-([01]?\d|2[0-3]):([0-5]\d)$")


# ── rutas (funciones, no constantes: respetan HOME parchado en tests) ──────
def _workspace_dir():
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace")


def config_path():
    return os.path.join(_workspace_dir(), "heartbeat.json")


def usage_path():
    return os.path.join(_workspace_dir(), "usage.json")


def backlog_path():
    return os.path.join(ROOT, "research", "auto-backlog.md")


def _read_json(path):
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


# ── config / modo ──────────────────────────────────────────────────────────
def _settings_layer():
    """Capa del store unificado (settings.py · latido.*) — el canal NUEVO.
    Precedencia documentada: defaults < settings < heartbeat.json (el canal
    histórico GANA mientras exista — back-compat total). Falla-suave: sin
    settings.py / sin store / valores podridos → {} (todo como antes)."""
    try:
        import settings as _settings
        out = {}
        for skey, ckey in (("latido.mode", "mode"),
                           ("latido.budget_cap_pct", "budget_cap_pct"),
                           ("latido.grace_min", "grace_min"),
                           ("latido.quiet_hours", "quiet_hours")):
            v = _settings.get_stored(skey)   # SOLO store: sin delegación
            if v is not None:                # (evita leer heartbeat.json 2×)
                out[ckey] = v
        return out
    except Exception:
        return {}


def _cap_range():
    """Rango válido de budget_cap_pct — leído del SETTINGS_SCHEMA de
    settings.py (la fuente de verdad para `latido.budget_cap_pct`); sin
    settings.py / sin range → espejo local. Mismo rango en ambos canales:
    una edición manual de heartbeat.json a 100 NO debe permitir lanzar
    al 99%."""
    try:
        import settings as _settings
        lo, hi = _settings._BY_KEY["latido.budget_cap_pct"]["range"]
        return float(lo), float(hi)
    except Exception:
        return float(CAP_RANGE_FALLBACK[0]), float(CAP_RANGE_FALLBACK[1])


def get_config():
    """Config efectiva: defaults + settings unificado (latido.*) +
    heartbeat.json, saneando tipos. heartbeat.json, si existe, GANA
    (back-compat). Falla-suave: archivo ausente/corrupto/valores inválidos
    → la capa anterior (settings → defaults auto/85/12)."""
    cfg = dict(DEFAULTS)
    cfg.update(_settings_layer())
    raw = _read_json(config_path())
    mode = raw.get("mode")
    if isinstance(mode, str) and mode.strip().lower() in VALID_MODES:
        cfg["mode"] = mode.strip().lower()
    try:
        cap = float(raw.get("budget_cap_pct"))
        lo, hi = _cap_range()   # mismo rango que el schema (50–95), no 1–100
        if lo <= cap <= hi:
            cfg["budget_cap_pct"] = cap
        # fuera de rango → falla-suave: queda la capa anterior (settings →
        # default 85); jamás se acepta un tope que deje lanzar al 99%.
    except (TypeError, ValueError):
        pass
    try:
        grace = int(raw.get("grace_min"))
        if grace >= 0:
            cfg["grace_min"] = grace
    except (TypeError, ValueError):
        pass
    qh = raw.get("quiet_hours")
    if isinstance(qh, str):
        qh = qh.strip()
        # vacío = silencio apagado (válido); con contenido, SOLO si parsea —
        # basura editada a mano jamás apaga el latido por accidente.
        if qh == "" or parse_quiet_hours(qh) is not None:
            cfg["quiet_hours"] = qh
    return cfg


def get_mode():
    return get_config()["mode"]


# ── intensidad: qué tan POTENTE es el trabajo por tick del latido ───────────
# El latido no solo decide SI trabajar (decide()), sino CUÁNTO. La intensidad
# (settings `latido.intensity`) dimensiona el tick: cuántos items, tope de
# tokens, si puede lanzar subagentes/workflow. Es el "qué tan potente" que
# controla el socio. El protocolo en protocols/heartbeat/ lo consume.
INTENSITY_PROFILES = {
    "light":  {"max_items": 1, "max_tokens": 80_000,    "subagents": False,
               "desc": "1 item chico, mínimos tokens, rápido"},
    "normal": {"max_items": 1, "max_tokens": 250_000,   "subagents": False,
               "desc": "1 item con tests + commit"},
    "deep":   {"max_items": 3, "max_tokens": 800_000,   "subagents": True,
               "desc": "varios items o 1 grande; subagentes ok"},
    "max":    {"max_items": 8, "max_tokens": 2_000_000, "subagents": True,
               "desc": "workflow multi-agente exhaustivo por tick (muchos tokens)"},
}
DEFAULT_INTENSITY = "normal"


def intensity():
    """Nivel de intensidad del latido (light/normal/deep/max). Falla-suave → normal."""
    try:
        import settings as _settings
        v = _settings.get("latido.intensity", DEFAULT_INTENSITY)
        return v if v in INTENSITY_PROFILES else DEFAULT_INTENSITY
    except Exception:
        return DEFAULT_INTENSITY


def intensity_profile():
    """Parámetros de trabajo del tick según la intensidad: {max_items, max_tokens,
    subagents, desc, level}. Un tope explícito (`latido.max_tokens_per_tick` > 0)
    overridea el max_tokens del perfil. Falla-suave → perfil 'normal'."""
    level = intensity()
    prof = dict(INTENSITY_PROFILES[level])
    prof["level"] = level
    try:
        import settings as _settings
        mt = _settings.get("latido.max_tokens_per_tick", 0)
        if isinstance(mt, int) and mt > 0:
            prof["max_tokens"] = mt
    except Exception:
        pass
    return prof


def set_mode(mode):
    """Persiste el modo en heartbeat.json (preserva las demás claves del
    archivo). `mode` inválido → ValueError. Devuelve la config efectiva."""
    if not isinstance(mode, str) or mode.strip().lower() not in VALID_MODES:
        raise ValueError("modo inválido: %r (válidos: %s)"
                         % (mode, "/".join(VALID_MODES)))
    mode = mode.strip().lower()
    raw = _read_json(config_path())
    raw["mode"] = mode
    raw.setdefault("budget_cap_pct", DEFAULTS["budget_cap_pct"])
    raw.setdefault("grace_min", DEFAULTS["grace_min"])
    os.makedirs(_workspace_dir(), exist_ok=True)
    # F2: escritura ATÓMICA (tmp + os.replace). settings._sync_heartbeat_json ya
    # escribe este MISMO heartbeat.json atómico; set_mode no debía ser la
    # excepción (ventana de truncado/lost-update sobre el archivo de config).
    _p = config_path()
    _tmp = "%s.tmp%d" % (_p, os.getpid())
    with open(_tmp, "w", encoding="utf-8") as fh:
        json.dump(raw, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    os.replace(_tmp, _p)
    try:                       # espejo al store unificado (migración gradual:
        import settings as _settings   # el día que heartbeat.json se retire,
        _settings.set_stored("latido.mode", mode)  # el store ya está al día)
    except Exception:
        pass                   # falla-suave: el canal histórico ya quedó
    return get_config()


# ── horas de silencio (latido.quiet_hours — rango sin trabajo autónomo) ────
def parse_quiet_hours(s):
    """'HH:MM-HH:MM' → (inicio_min, fin_min) en minutos desde medianoche, o
    None si el formato no parsea / el rango es vacío (inicio == fin). El
    rango puede cruzar medianoche (22:30-06:00). Falla-suave: jamás levanta."""
    try:
        m = _QUIET_RE.match((s or "").strip())
        if not m:
            return None
        start = int(m.group(1)) * 60 + int(m.group(2))
        end = int(m.group(3)) * 60 + int(m.group(4))
        if start == end:
            return None                  # rango vacío = sin silencio
        return (start, end)
    except Exception:
        return None


def in_quiet_hours(cfg=None, now=None):
    """¿Estamos DENTRO del rango de silencio? El latido no lanza trabajo
    autónomo ahí (decide() → action "quiet"). `now` = datetime para tests.
    Sin rango configurado / formato inválido → False (falla-suave: una
    config rota JAMÁS apaga el latido sola)."""
    try:
        cfg = cfg or get_config()
        rng = parse_quiet_hours(cfg.get("quiet_hours", ""))
        if rng is None:
            return False
        start, end = rng
        now = now or datetime.datetime.now()
        t = now.hour * 60 + now.minute
        if start < end:                  # rango diurno: 01:00-07:00
            return start <= t < end
        return t >= start or t < end     # cruza medianoche: 22:30-06:00
    except Exception:
        return False


# ── presupuesto (usage.json de la statusline) ──────────────────────────────
def read_usage(now=None):
    """usage.json normalizado: {pct, resets_at, stamped, stale} o None si el
    archivo falta / es ilegible / no trae five_hour_pct numérico. `stale` =
    stamped ausente o más viejo que USAGE_STALE_SEC (la statusline dejó de
    escribir → el dato ya no es confiable)."""
    raw = _read_json(usage_path())
    try:
        pct = float(raw["five_hour_pct"])
    except (KeyError, TypeError, ValueError):
        return None
    now = time.time() if now is None else now
    try:
        stamped = float(raw.get("stamped"))
        stale = (now - stamped) > USAGE_STALE_SEC
    except (TypeError, ValueError):
        stamped, stale = None, True
    resets_at = raw.get("five_hour_resets_at")
    if not isinstance(resets_at, (int, float)):
        resets_at = None
    return {"pct": pct, "resets_at": resets_at, "stamped": stamped,
            "stale": stale}


def budget_ok(cfg=None, now=None):
    """¿Hay presupuesto del plan 5h para trabajo autónomo?

    True  → five_hour_pct < budget_cap_pct (hay colchón).
    False → tope alcanzado (pct >= cap).
    None  → DESCONOCIDO: usage.json falta, es ilegible, o su `stamped` tiene
            más de 20 min (statusline muerta). Política cauta documentada:
            `decide()` trata None como pausa — sin dato fresco NO se gasta a
            ciegas (podríamos estar al 99%). Quien quiera otra política puede
            distinguir None de False.
    """
    u = read_usage(now=now)
    if u is None or u["stale"]:
        return None
    cfg = cfg or get_config()
    return u["pct"] < cfg["budget_cap_pct"]


# ── cola (research/auto-backlog.md) ────────────────────────────────────────
_ITEM_RE = re.compile(r"^\s*[-*]\s*\[ \]\s+(.+?)\s*$")
_SECTION_RE = re.compile(r"^##\s+(.+?)\s*$")


def _is_gated(section_title):
    t = (section_title or "").lower()
    # "gated" cuenta, pero "no-gated" / "no gated" NO (la sección de robos
    # se llama "Robos restantes (no-gated)" y es perfectamente elegible).
    return "🧊" in t or bool(re.search(r"(?<!no.)\bgated\b", t))


def _clean_title(s):
    s = s.replace("**", "").strip()
    return re.sub(r"\s+", " ", s)


def _item_id(section, title, nth):
    """Id estable de un ítem pendiente para referenciarlo desde UIs: hash
    corto de (sección, título, nº de ocurrencia). Estable entre requests
    mientras el ítem no cambie de texto; `nth` desambigua duplicados."""
    raw = "%s\n%s\n%d" % (section, title, nth)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:10]


def _scan_items(lines):
    """Escanea las líneas del backlog y devuelve los ítems `[ ]` ACCIONABLES
    (mismas reglas que pending_tasks: salta preámbulo, `[x]`, sección 🧊
    gated, y TODO lo que esté dentro de un code fence ```/~~~ — un `- [ ]`
    de ejemplo documentado NO es una tarea lanzable), cada uno con su línea
    de origen: {"id", "title", "section", "line": índice, "raw": línea
    exacta}."""
    out, section, gated, seen = [], None, True, {}
    in_fence = False
    for i, ln in enumerate(lines):
        stripped = ln.strip()
        if stripped.startswith("```") or stripped.startswith("~~~"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        m = _SECTION_RE.match(ln)
        if m:
            section = _clean_title(m.group(1))
            gated = _is_gated(section)
            continue
        if gated or section is None:
            continue
        m = _ITEM_RE.match(ln)
        if m:
            title = _clean_title(m.group(1))
            nth = seen.get((section, title), 0)
            seen[(section, title)] = nth + 1
            out.append({"id": _item_id(section, title, nth), "title": title,
                        "section": section, "line": i, "raw": ln})
    return out


def pending_tasks(path=None):
    """Ítems `[ ]` del backlog EN ORDEN (orden = prioridad), saltando la
    sección gated (🧊 — esos requieren gate del socio, el heartbeat no los toca)
    y el preámbulo (reglas antes de la primera `##`). Cada ítem:
    {"id", "title", "section"} — `id` es el handle estable para reorder().
    Falla-suave: archivo ausente → []."""
    try:
        with open(path or backlog_path(), encoding="utf-8") as fh:
            lines = fh.read().splitlines()
    except Exception:
        return []
    return [{"id": it["id"], "title": it["title"], "section": it["section"]}
            for it in _scan_items(lines)]


def next_task(path=None):
    """Primer `[ ]` elegible del backlog (la tarea que tocaría lanzar) o None
    si la cola está vacía. {"title", "section"}."""
    pend = pending_tasks(path)
    return pend[0] if pend else None


# ── reorden de la cola (escritura CORRECTNESS-CRÍTICA del backlog) ─────────
#
# Diseño — reorden POR SECCIÓN, por permutación de slots:
#   · Un ítem JAMÁS cambia de sección (🔥/🛠️/🔬 tienen semántica propia);
#     mover ▲/▼ se detiene en el borde de su sección. El primer `[ ]` global
#     que next_task() devuelve sigue siendo controlable: es el primero de la
#     primera sección con pendientes, y dentro de ella el orden es libre.
#   · Solo se permutan las LÍNEAS `[ ]` accionables entre sus MISMAS
#     posiciones de línea dentro de cada sección. Toda otra línea (preámbulo,
#     `##`, `[x]`, separadores, y la sección 🧊 gated COMPLETA) queda
#     byte-idéntica en su posición original — el archivo nunca cambia de
#     largo ni de estructura. (Cada ítem = una línea, igual que el parser.)
#   · Antes de escribir se VERIFICAN invariantes (multiset de líneas igual,
#     no-slots intactos, mismos ítems tras re-parsear); cualquier duda →
#     falla-suave: NO se escribe y se reporta. Escritura atómica
#     (tmp + os.replace) para nunca dejar el archivo a medias.

def reorder(move=None, order=None, path=None):
    """Reordena los `[ ]` pendientes accionables de `auto-backlog.md`.

    Exactamente UNA de las dos entradas:
      move  = {"id": <id de pending_tasks>, "dir": "up"|"down"} — mueve el
              ítem un lugar dentro de SU sección (en el borde: no-op).
      order = [ids…] — permutación COMPLETA de los ids pendientes actuales;
              dentro de cada sección los ítems quedan en el orden relativo
              en que aparecen en la lista (jamás cambian de sección).

    Devuelve {"ok": True, "changed": bool, "items": [{id,title,section}…]}
    o {"ok": False, "error": str} SIN haber escrito nada. Nunca levanta.
    """
    try:
        return _reorder(move, order, path)
    except Exception as e:                       # cinturón: jamás reventar
        return {"ok": False, "error": "reorder falló: %s" % e}


def _reorder(move, order, path):
    if (move is None) == (order is None):
        return {"ok": False, "error": "dar exactamente uno: move u order"}
    path = path or backlog_path()
    # R3-F2: el RMW COMPLETO (leer → permutar → os.replace) va bajo lock N8.
    # Sin él, otro writer que marque `[x]` entre el read y el replace pierde
    # su escritura (el ítem revierte a `[ ]` → el cron relanza tarea hecha).
    # El read ocurre DENTRO del lock (está en _reorder_rmw). LockTimeout la
    # atrapa el cinturón de reorder() → falla-suave sin escribir.
    if file_lock is not None:
        with file_lock(path, timeout=5):
            return _reorder_rmw(move, order, path)
    return _reorder_rmw(move, order, path)


def _reorder_rmw(move, order, path):
    try:
        with open(path, encoding="utf-8", newline="") as fh:
            text = fh.read()
    except Exception as e:
        return {"ok": False, "error": "no se pudo leer el backlog: %s" % e}
    # Partir preservando el terminador ORIGINAL de CADA línea. splitlines()
    # corta por \r\n, \r, \n y también \v, \f, \x85, U+2028/29… — re-unir
    # todo con UN solo `nl` global reescribiría bytes FUERA de los slots (un
    # backlog con EOL mixtos saldría homogeneizado; un U+2028 pegado desde
    # Obsidian/browser se convertiría en \n partiendo la línea) y rompería
    # el invariante "toda otra línea queda byte-idéntica". Aquí cada slot
    # conserva SU terminador y solo permutamos los cuerpos.
    lines, ends = [], []
    for raw in text.splitlines(keepends=True):
        if raw.endswith("\r\n"):
            lines.append(raw[:-2]); ends.append("\r\n")
        elif raw and raw[-1] in "\n\r\v\f\x1c\x1d\x1e\x85\u2028\u2029":
            lines.append(raw[:-1]); ends.append(raw[-1])
        else:                                    # última línea sin terminador
            lines.append(raw); ends.append("")
    items = _scan_items(lines)
    if not items:
        return {"ok": False, "error": "sin pendientes accionables"}

    # ítems agrupados por sección, en orden de archivo
    sections = {}                                # sección → [ítems]
    for it in items:
        sections.setdefault(it["section"], []).append(it)

    if move is not None:
        if not isinstance(move, dict):
            return {"ok": False, "error": "move debe ser {id, dir}"}
        iid, direction = move.get("id"), move.get("dir")
        if direction not in ("up", "down"):
            return {"ok": False, "error": "dir inválida (up/down)"}
        target = next((it for it in items if it["id"] == iid), None)
        if target is None:
            return {"ok": False, "error": "id desconocido: %r" % (iid,)}
        group = sections[target["section"]]
        k = group.index(target)
        j = k - 1 if direction == "up" else k + 1
        if j < 0 or j >= len(group):             # borde de sección → no-op
            return {"ok": True, "changed": False,
                    "items": pending_tasks(path)}
        group[k], group[j] = group[j], group[k]
    else:
        if (not isinstance(order, list)
                or not all(isinstance(x, str) for x in order)):
            return {"ok": False, "error": "order debe ser lista de ids"}
        current = [it["id"] for it in items]
        if sorted(order) != sorted(current):
            return {"ok": False,
                    "error": "order no es permutación exacta de los "
                             "pendientes actuales"}
        rank = {iid: i for i, iid in enumerate(order)}
        for sec in sections:
            sections[sec].sort(key=lambda it: rank[it["id"]])

    # permutación de slots: cada sección reusa SUS posiciones de línea
    new_lines = list(lines)
    for sec, group in sections.items():
        slots = sorted(it["line"] for it in group)
        for slot, it in zip(slots, group):
            new_lines[slot] = it["raw"]

    # ── invariantes (si una falla, NO se escribe) ──
    if len(new_lines) != len(lines):
        return {"ok": False, "error": "invariante rota: nº de líneas"}
    if sorted(new_lines) != sorted(lines):
        return {"ok": False, "error": "invariante rota: líneas perdidas o "
                                      "duplicadas"}
    slots_all = {it["line"] for it in items}
    if any(new_lines[i] != lines[i] for i in range(len(lines))
           if i not in slots_all):
        return {"ok": False, "error": "invariante rota: línea fuera de la "
                                      "cola tocada"}
    re_items = _scan_items(new_lines)
    if (sorted(it["id"] for it in re_items)
            != sorted(it["id"] for it in items)):
        return {"ok": False, "error": "invariante rota: el resultado no "
                                      "re-parsea a los mismos ítems"}
    for it in re_items:                          # gated jamás se cuela
        if _is_gated(it["section"]):
            return {"ok": False, "error": "invariante rota: ítem gated"}

    changed = new_lines != lines
    if changed:                                  # escritura atómica
        # re-unir cuerpo + terminador ORIGINAL de cada slot: los EOL quedan
        # exactamente donde estaban (mixtos incluidos) y el archivo conserva
        # (o no) su newline final tal cual — cero bytes tocados fuera de la
        # permutación.
        out = "".join(b + e for b, e in zip(new_lines, ends))
        tmp = path + ".reorder-tmp-%d" % os.getpid()
        try:
            with open(tmp, "w", encoding="utf-8", newline="") as fh:
                fh.write(out)
            os.replace(tmp, path)
        except Exception as e:
            try:
                os.remove(tmp)
            except OSError:
                pass
            return {"ok": False, "error": "no se pudo escribir: %s" % e}
    return {"ok": True, "changed": changed,
            "items": [{"id": it["id"], "title": it["title"],
                       "section": it["section"]} for it in re_items]}


# ── árbitro ────────────────────────────────────────────────────────────────
def _cron_job_enabled():
    """Flag del job `heartbeat-cron` (settings.py jobs) — el toggle de CRONS
    del config. Falla-suave: sin settings.py / store roto → True (el latido
    no se apaga solo por un módulo ausente)."""
    try:
        import settings as _settings
        return bool(_settings.is_job_enabled("heartbeat-cron"))
    except Exception:
        return True


def decide(mode, budget_ok, has_running, idle_ok, backlog=None, agent=""):
    """La acción canónica del heartbeat. SOLO decide y reporta — jamás lanza.

    Entradas: `mode` (auto/manual/off), `budget_ok` (True/False/None de
    budget_ok()), y las dos señales que SOLO el caller (el cron) conoce:
    `has_running` (¿ya corre un agente?) e `idle_ok` (¿el socio lleva ausente
    más de grace_min?). Además decide() consulta solo dos configs más,
    falla-suave: el flag del job `heartbeat-cron` (settings jobs — off ⇒
    "off") y las horas de silencio (latido.quiet_hours — dentro del rango ⇒
    "quiet"). Precedencia: off → quiet → pause → cede → wait → empty → go.
    `agent` (opcional): aceptado por compatibilidad de firma; sin efecto.

    Devuelve {"action", "task", "reason"}:
      off    modo off/manual, o el job heartbeat-cron deshabilitado en
             settings (solo `auto` + job on habilitan lanzamiento autónomo)
      quiet  dentro de latido.quiet_hours — sin lanzamientos en el rango
      pause  sin presupuesto — False = tope alcanzado; None = dato desconocido
             (política cauta: a ciegas no se gasta)
      cede   el socio está activo — no competir con él por la ventana
      wait   ya hay un agente corriendo — no doble-lanzar
      empty  cola vacía (reponer ítems en auto-backlog.md)
      go     lanzar `task` (el primer [ ] elegible)
    """
    if not _cron_job_enabled():
        return {"action": "off", "task": None,
                "reason": "job heartbeat-cron deshabilitado (settings.py "
                          "jobs enable heartbeat-cron lo prende)"}
    if mode != "auto":
        why = ("modo off" if mode == "off"
               else "modo %s — lanzamiento solo a mano" % mode)
        return {"action": "off", "task": None, "reason": why}
    try:
        cfg_quiet = get_config()
    except Exception:
        cfg_quiet = None                 # cinturón: una config rota no decide
    if cfg_quiet and in_quiet_hours(cfg_quiet):
        return {"action": "quiet", "task": None,
                "reason": "horas de silencio (%s) — sin lanzamientos "
                          "autónomos en el rango"
                          % cfg_quiet.get("quiet_hours", "")}
    if budget_ok is not True:
        why = ("presupuesto 5h en tope (colchón alcanzado)"
               if budget_ok is False
               else "presupuesto desconocido (usage.json ausente/viejo) — cauto")
        return {"action": "pause", "task": None, "reason": why}
    if not idle_ok:
        return {"action": "cede", "task": None,
                "reason": "socio activo — no competir por la ventana"}
    if has_running:
        return {"action": "wait", "task": None,
                "reason": "ya hay un agente corriendo — no doble-lanzar"}
    task = next_task(backlog)
    if task is None:
        return {"action": "empty", "task": None,
                "reason": "cola vacía — reponer auto-backlog.md"}
    return {"action": "go", "task": task,
            "reason": "presupuesto OK + socio ausente + nada corriendo"}


# ── estado para UIs (dashboard / banner / cron) ────────────────────────────
def state():
    """Snapshot JSON-serializable del heartbeat para cualquier UI:
    {mode, budget:{pct, resets_at, ok, cap, stale}, pending:[títulos],
     items:[{id,title,section}…] (handles para reorder), next, count,
     grace_min, quiet_hours, quiet}. Falla-suave en cada pieza."""
    cfg = get_config()
    u = read_usage()
    pend = pending_tasks()
    return {
        "mode": cfg["mode"],
        "intensity": intensity_profile(),
        "quiet_hours": cfg.get("quiet_hours", ""),
        "quiet": in_quiet_hours(cfg),
        "budget": {
            "pct": u["pct"] if u else None,
            "resets_at": u["resets_at"] if u else None,
            "ok": budget_ok(cfg),
            "cap": cfg["budget_cap_pct"],
            "stale": u["stale"] if u else True,
        },
        "pending": [t["title"] for t in pend],
        "items": pend,
        "next": pend[0]["title"] if pend else None,
        "count": len(pend),
        "grace_min": cfg["grace_min"],
    }


# ── CLI ────────────────────────────────────────────────────────────────────
def _fmt_reset(epoch):
    try:
        return datetime.datetime.fromtimestamp(float(epoch)).strftime("%H:%M")
    except Exception:
        return "?"


def _cli_status():
    st = state()
    b = st["budget"]
    ok = b["ok"]
    budget = ("?" if b["pct"] is None else "%.0f%%" % b["pct"])
    extra = (" · DESCONOCIDO (statusline sin dato fresco)" if ok is None
             else (" · EN PAUSA (tope %d%%)" % b["cap"] if ok is False else ""))
    reset = (" · resetea " + _fmt_reset(b["resets_at"])) if b["resets_at"] else ""
    ip = st.get("intensity", {})
    print("heartbeat · modo %s · intensidad %s (%s · ≤%dk tok/tick)"
          % (st["mode"], ip.get("level", "?"), ip.get("desc", ""),
             int(ip.get("max_tokens", 0) / 1000)))
    if st.get("quiet_hours"):
        print("  silencio %s%s" % (st["quiet_hours"],
                                   " · AHORA (sin lanzamientos)"
                                   if st.get("quiet") else ""))
    print("  uso 5h   %s%s%s" % (budget, reset, extra))
    print("  cola     %d pendiente(s)" % st["count"])
    for i, t in enumerate(st["pending"]):
        print("    %s %s" % ("→" if i == 0 else "·", t))
    if not st["count"]:
        print("    (vacía — reponer research/auto-backlog.md)")
    return 0


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    cmd = args[0] if args else "status"
    if cmd in ("state", "--json", "json"):
        print(json.dumps(state(), ensure_ascii=False, indent=2))
        return 0
    if cmd in VALID_MODES:
        cfg = set_mode(cmd)
        print("heartbeat → modo %s" % cfg["mode"])
        return 0
    if cmd in ("status", "--status"):
        return _cli_status()
    print("uso: heartbeat.py status|state|--json|auto|manual|off",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
