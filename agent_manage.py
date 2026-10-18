#!/usr/bin/env python3
"""WORKSPACE · agent_manage — operaciones de GESTIÓN de agentes (U08/Z08).

Mutaciones per-máquina que la pantalla Agentes (y cualquier otra vista) usa
para editar un agente registrado. Cada operación:
  · revalida la entidad contra el estado actual (agent_state.revalidate) —
    si otra ventana la retiró o reemplazó, CANCELA (no redirige);
  · escribe de forma atómica en el store per-máquina que corresponde;
  · devuelve {"ok": bool, "msg"|"error": str} — un commit fallido JAMÁS se
    anuncia como éxito;
  · invalida el estado compartido (las demás vistas lo ven en su próximo
    tick sin reiniciar).

Política (conservadora, revisable por el dueño del producto — ADOPTION-SPEC U08):
  · QUITAR del registro conserva el cerebro, sesiones y preferencias. Nada se
    borra del disco. La eliminación física NO existe aquí (acción distinta y
    explícita, fuera de esta pantalla).
  · Un agente del registry COMMITTEADO (equipo/back-compat) no puede quitarse
    per-máquina sin tocar el repo: se OCULTA (mismo efecto visible) y se dice.
  · Nunca se toca la IDENTIDAD del agent.json (N3). Las dos preferencias que
    el usuario elige al crear el agente (`autonomy`, `skill_review`) sí se
    cambian aquí (Agentes → Enter), por el mismo camino que al crearlo.

Stdlib puro, falla-suave.
"""
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _t(key, es, **kw):
    """i18n falla-suave (lado cliente: estos mensajes los pinta Agentes):
    `key` en el idioma activo; sin i18n / clave faltante → `es` inline."""
    s = es
    try:
        import i18n
        v = i18n.t(key)
        if v != key:
            s = v
    except Exception:
        s = es
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


def _ok(msg):
    return {"ok": True, "msg": msg}


def _err(msg):
    return {"ok": False, "error": msg}


def _invalidate():
    try:
        import agent_state
        agent_state.invalidate()
    except Exception:
        pass


def _current(agent_id, brain=None):
    """(agent, error) tras revalidar contra el estado actual."""
    try:
        import agent_state
        ok, a, why = agent_state.revalidate(agent_id, brain)
    except Exception as e:
        return None, _t("agentes.mg.unreadable", "estado ilegible: {e}", e=e)
    if not ok:
        return None, _t("agentes.mg.changed",
                        "{n} fue {why} desde otra ventana — acción cancelada",
                        n=agent_id,
                        why=why or _t("agentes.mg.changed_why", "cambiado"))
    return a, ""


def _is_loaded(name):
    try:
        import agentsreg
        return agentsreg.find(name) is not None
    except Exception:
        return False




def validate_brain(path):
    """(ok, ruta_absoluta|motivo). Acepta una carpeta legible; la definición
    (.workspace/agent.json, <brain>/agent.json o el de la instalación anterior)
    es recomendada pero no obligatoria para un agente committeado."""
    if not path or not str(path).strip():
        return False, _t("agentes.mg.empty_path", "ruta vacía")
    p = os.path.abspath(os.path.expanduser(str(path).strip().strip('"')))
    if not os.path.isdir(p):
        return False, _t("agentes.mg.not_dir",
                         "no existe o no es carpeta: {p}", p=p)
    try:
        os.listdir(p)
    except OSError as e:
        return False, _t("agentes.mg.no_read",
                         "sin permiso de lectura: {p} ({e})",
                         p=p, e=e.__class__.__name__)
    return True, p




def set_brain(agent_id, new_path, expected_brain=None):
    """Cambia la ruta del cerebro de un agente (reubicación/reparación).
    Cargado → agents.local.json; committeado → paths.local.json brains.<n>."""
    a, e = _current(agent_id, expected_brain)
    if a is None:
        return _err(e)
    ok, p = validate_brain(new_path)
    if not ok:
        return _err(p)
    name = a["name"]
    # Z20/Z03: UNA sola escritura de rutas de cerebro — agentsreg.relocate
    # valida que la carpeta sea SU cerebro y escribe el override que gana.
    try:
        import agentsreg
        ok_, err, _written = agentsreg.relocate(name, p)
    except Exception as ex:
        return _err(_t("agentes.mg.save_fail_ex", "no se pudo guardar: {e}",
                       e=ex))
    if not ok_:
        return _err(err or _t("agentes.mg.save_fail", "no se pudo guardar"))
    _invalidate()
    return _ok("%s → %s" % (name, p))


def _hidden():
    try:
        import settings
        v = settings.get_stored("agentes.hidden")
    except Exception:
        return []
    return list(v) if isinstance(v, list) else []


def _set_hidden(names):
    try:
        import config_engine
        if not names:
            r = config_engine.reset_setting("agentes.hidden", actor="agentes")
        else:
            r = config_engine.set_setting("agentes.hidden", list(names), actor="agentes")
    except Exception as ex:
        return _err(_t("agentes.mg.save_fail_ex", "no se pudo guardar: {e}",
                       e=ex))
    if not r.get("ok"):
        return _err(r.get("error") or _t("agentes.mg.save_fail",
                                          "no se pudo guardar"))
    _invalidate()
    return None


def set_hidden(agent_id, hidden, expected_brain=None):
    a, e = _current(agent_id, expected_brain)
    if a is None:
        return _err(e)
    cur = _hidden()
    name = a["name"]
    new = ([*cur, name] if name not in cur else cur) if hidden \
        else [x for x in cur if x != name]
    if new == cur:
        return _ok(_t("agentes.mg.nochange", "sin cambios"))
    bad = _set_hidden(new)
    if bad:
        return bad
    return _ok(_t("agentes.mg.hidden", "{n} oculto del hub (sigue cargado)",
                  n=name) if hidden else
               _t("agentes.mg.visible", "{n} visible en el hub", n=name))


def set_engine(agent_id, engine_id, expected_brain=None):
    a, e = _current(agent_id, expected_brain)
    if a is None:
        return _err(e)
    try:
        import harnesses
        r = harnesses.set_binding(a["name"], engine_id, a.get("engine_default") or "")
    except Exception as ex:
        return _err(_t("agentes.mg.save_fail_ex", "no se pudo guardar: {e}",
                       e=ex))
    if not r.get("ok"):
        return _err(r.get("error") or _t("agentes.mg.save_fail",
                                          "no se pudo guardar"))
    _invalidate()
    return _ok(_t("agentes.mg.engine", "{n} usará {e}", n=a["name"],
                  e=engine_id))


def cycle_engine(agent_id, expected_brain=None):
    a, e = _current(agent_id, expected_brain)
    if a is None:
        return _err(e)
    try:
        import harnesses
        r = harnesses.cycle(a["name"], a.get("engine_default") or "")
    except Exception as ex:
        return _err(_t("agentes.mg.engine_fail",
                       "no se pudo cambiar el motor: {e}", e=ex))
    if not r.get("ok"):
        return _err(r.get("error") or _t("agentes.mg.save_fail",
                                          "no se pudo guardar"))
    _invalidate()
    return _ok(_t("agentes.mg.engine", "{n} usará {e}", n=a["name"],
                  e=r["engine"]))


def unregister(agent_id, expected_brain=None):
    """Quita el agente del registro de ESTA máquina. Conserva cerebro,
    sesiones y preferencias. Committeado → se oculta (y se explica)."""
    a, e = _current(agent_id, expected_brain)
    if a is None:
        return _err(e)
    name = a["name"]
    if not _is_loaded(name):
        r = set_hidden(name, True)
        if not r["ok"]:
            return r
        return _ok(_t("agentes.mg.team_hidden",
                      "{n} viene del registro del equipo: lo oculté en esta "
                      "máquina (cerebro intacto)", n=name))
    try:
        import agentsreg
        r = agentsreg.remove(name)
    except Exception as ex:
        return _err(_t("agentes.mg.remove_fail", "no se pudo quitar: {e}",
                       e=ex))
    if isinstance(r, tuple) and not r[0]:
        return _err(_t("agentes.mg.remove_fail", "no se pudo quitar: {e}",
                       e=(r[1] if len(r) > 1 else "?")))
    cur = _hidden()
    if name in cur:
        _set_hidden([x for x in cur if x != name])
    _invalidate()
    return _ok(_t("agentes.mg.removed",
                  "{n} quitado del registro · cerebro y sesiones intactos "
                  "en {p}", n=name, p=a.get("brain") or "?"))


# ── permisos y aprendizaje (Agentes → Enter) ─────────────────────────────────────
#: Los niveles que existen: ask|brain. «Comandos sin preguntar» ("full") ya no
#: existe; un "full" de antes se lee como "brain" (la migración lo convierte).
AUTONOMY_ORDER = ("ask", "brain")
AUTONOMY_SETTABLE = ("ask", "brain")


def _definition(brain):
    try:
        import agentsreg
        return agentsreg.load_definition(brain) or {}
    except Exception:
        return {}


def _norm_autonomy(v):
    s = str(v or "").strip().lower()
    return s if s in AUTONOMY_ORDER else "brain"


def _global_review():
    try:
        import settings as _settings
        return bool(_settings.enabled("hooks.skill_review", default=False))
    except Exception:
        return False


def preferences(agent_id, expected_brain=None):
    """Lo que Agentes → Enter muestra del agente: {"ok", "autonomy" (ask|brain|
    full), "skill_review" (efectivo), "review_global" (True = no lo eligió y
    manda el ajuste general)}."""
    a, e = _current(agent_id, expected_brain)
    if a is None:
        return _err(e)
    brain = a.get("brain") or ""
    d = _definition(brain) if brain else {}
    auto = _norm_autonomy(d.get("autonomy"))
    rv = d.get("skill_review")
    explicit = isinstance(rv, bool)
    return {"ok": True, "autonomy": auto,
            "skill_review": rv if explicit else _global_review(),
            "review_global": not explicit}


def _write_pref(a, autonomy=None, skill_review=None):
    """agent.json (+ permisos de Claude Code si cambió la autonomía). Codex y
    Antigravity leen la autonomía al lanzar: aplica desde la próxima sesión."""
    brain = a.get("brain") or ""
    if not brain or not os.path.isdir(brain):
        return _t("agentes.mg.no_brain", "no encuentro su cerebro")
    try:
        import agent_admin
        if not agent_admin._set_preferences(brain, autonomy, skill_review):
            return _t("agentes.mg.no_def",
                      "no pude escribir su .workspace/agent.json")
    except Exception as ex:
        return _t("agentes.mg.save_fail_ex", "no se pudo guardar: {e}", e=ex)
    if autonomy is not None:
        try:
            import install
            cfg = dict(_definition(brain), autonomy=autonomy)
            ok, why = install.apply_permissions(brain, cfg)
        except Exception as ex:
            ok, why = False, str(ex)
        if not ok:
            return _t("agentes.mg.perm_fail",
                      "guardé la preferencia, pero no pude ajustar los "
                      "permisos de Claude Code ({e}) — corre `workspace "
                      "doctor`", e=why)
    _invalidate()
    return ""


def set_autonomy(agent_id, level, expected_brain=None):
    """ask · brain. Reescribe su agent.json y los permisos de Claude Code
    (conserva lo que el usuario agregó a mano)."""
    a, e = _current(agent_id, expected_brain)
    if a is None:
        return _err(e)
    level = str(level or "").strip().lower()
    if level not in AUTONOMY_SETTABLE:
        return _err(_t("agentes.mg.bad_level", "nivel desconocido: {v}",
                       v=level))
    bad = _write_pref(a, autonomy=level)
    if bad:
        return _err(bad)
    return _ok({"ask": _t("agentes.mg.auto_ask",
                          "{n} preguntará antes de escribir en su cerebro "
                          "· desde su próxima sesión", n=a["name"]),
                "brain": _t("agentes.mg.auto_brain",
                            "{n} lee y escribe en su cerebro sin preguntar "
                            "· desde su próxima sesión", n=a["name"])}[level])


def set_skill_review(agent_id, on, expected_brain=None):
    a, e = _current(agent_id, expected_brain)
    if a is None:
        return _err(e)
    bad = _write_pref(a, skill_review=bool(on))
    if bad:
        return _err(bad)
    return _ok(_t("agentes.mg.review_on",
                  "revisión de skills prendida para {n} · la hace al abrir la "
                  "siguiente sesión, a la vista", n=a["name"]) if on else
               _t("agentes.mg.review_off",
                  "revisión de skills apagada para {n}", n=a["name"]))
