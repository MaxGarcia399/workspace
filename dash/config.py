#!/usr/bin/env python3
"""WORKSPACE · dash/config — API de la Config profunda (adapter fino sobre
config_engine, detrás del guard Y1).

🔒 Seguridad — el orden importa:
  · TODOS los endpoints quedan detrás del guard Y1 (Host + token + Origin):
    dashboard.Handler aplica `_guard` ANTES de rutear módulos de dash/ — este
    módulo NO puede ser alcanzado sin pasarlo (contrato de dash/__init__.py).
  · Este adapter NO añade lógica de escritura: TODA la validación, el gate de
    secretos, backups, verificación y rollback viven en config_engine (una
    sola fuente — la API no puede "saltarse" nada).
  · Tier B exige `confirm: true` EXPLÍCITO en el body (el engine lo impone;
    sin confirm devuelve el plan, no escribe).
  · Tier C jamás escribe: /api/config/propose genera la propuesta por el bus.
  · N3: el flip de agentes del equipo NO tiene endpoint — no existe forma de
    ejecutarlo por HTTP, ni con token.

Contrato del framework (dash/__init__.py):
  GET_ROUTES  fn(brain, socio, query) · POST_ROUTES fn(brain, socio, data).
`socio` viaja como `actor` al changelog (auditoría de quién cambió qué).
"""
import os
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import config_engine as _ce   # noqa: E402


# ── GET (read-only, cero efectos) ───────────────────────────────────────────
def _schema(brain, socio, query):
    return _ce.describe()


def _stats(brain, socio, query):
    return _ce.stats()


def _log(brain, socio, query):
    try:
        n = int((query.get("n") or ["50"])[0])
    except Exception:
        n = 50
    return {"log": _ce.read_log(max(1, min(n, 1000)))}


# ── POST (writes — todo delega en el engine; tier B exige confirm) ─────────
def _set(brain, socio, data):
    return _ce.set_setting(str(data.get("key", "")), data.get("value"),
                           actor=socio or "")


def _reset(brain, socio, data):
    return _ce.reset_setting(str(data.get("key", "")), actor=socio or "")


def _job(brain, socio, data):
    return _ce.set_job(str(data.get("id", "")), data.get("enabled"),
                       actor=socio or "")


def _agent_set(brain, socio, data):
    return _ce.set_agent_field(str(data.get("agent", "")),
                               str(data.get("field", "")),
                               data.get("value"),
                               confirm=data.get("confirm") is True,
                               actor=socio or "")


def _propose(brain, socio, data):
    return _ce.propose_change(str(data.get("agent", "")),
                              str(data.get("field", "")),
                              data.get("value"),
                              actor=socio or "",
                              note=str(data.get("note", "")))


def _mcp_set(brain, socio, data):
    return _ce.mcp_set(str(data.get("name", "")), data.get("cmd"),
                       scope=data.get("scope", "global"),
                       env=data.get("env") or [], actor=socio or "")


def _mcp_remove(brain, socio, data):
    return _ce.mcp_remove(str(data.get("name", "")), actor=socio or "")


def _routing(brain, socio, data):
    return _ce.set_task_routing(data.get("routing") or {}, actor=socio or "")


def _theme_local(brain, socio, data):
    return _ce.set_theme_local(str(data.get("agent", "")),
                               data.get("palette"), actor=socio or "")


GET_ROUTES = {
    "/api/config/schema": _schema,
    "/api/config/stats": _stats,
    "/api/config/log": _log,
}

POST_ROUTES = {
    "/api/config/set": _set,               # tier A
    "/api/config/reset": _reset,           # tier A
    "/api/config/job": _job,               # tier A
    "/api/config/agent-set": _agent_set,   # tier B (exige confirm:true)
    "/api/config/propose": _propose,       # tier C (propuesta por el bus)
    "/api/config/mcp-set": _mcp_set,       # capa gestionada de MCPs
    "/api/config/mcp-remove": _mcp_remove,
    "/api/config/routing": _routing,       # routing por tarea (formato congelado)
    "/api/config/theme-local": _theme_local,  # tema personal per-máquina
}
