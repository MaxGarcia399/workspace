#!/usr/bin/env python3
"""WORKSPACE · dash — framework modular de secciones del dashboard (ciclo D, corrida D-1).

Una SECCIÓN nueva del dashboard = UN módulo autocontenido en este paquete:

    dash/<feature>.py   →  endpoints :  GET_ROUTES / POST_ROUTES (opcionales)
    dash/<feature>.js   →  front     :  registerSection({...})  (se inyecta al HTML)

Contrato del módulo Python (todo opcional — un módulo puede ser solo JS):
  GET_ROUTES  : dict { "/api/<x>": fn(brain, socio, query) -> obj JSON-serializable }
  POST_ROUTES : dict { "/api/<x>": fn(brain, socio, data)  -> obj JSON-serializable }
                `query` = dict de la querystring (parse_qs) · `data` = body JSON dict.

🔒 Seguridad: TODOS los endpoints de módulos quedan detrás del guard Y1
(Host + token + Origin) — dashboard.Handler lo aplica ANTES de rutear, el
módulo no puede saltárselo. Read-only por default; si un módulo escribe,
sigue el protocolo append-only del vault (nunca pisa canónico).

Contrato del módulo JS (dash/<feature>.js, vanilla, sin libs externas):
  registerSection({id, label, render, mount?, noPoll?, fill?})
  Helpers globales disponibles: get(path) · esc(s) · $(sel) · AUTH · TOKEN.

Cómo añadir una sección (corridas D-2…D-6): ver dash/README.md. Regla de oro:
una feature = un .py + un .js NUEVOS — no se toca dashboard.py ni dashboard.html.
"""
import os
import importlib.util

HERE = os.path.dirname(os.path.abspath(__file__))
_MODULES = None


def load_modules():
    """Importa cada dash/<name>.py (no '_*') una sola vez, en orden alfabético."""
    global _MODULES
    if _MODULES is None:
        mods = []
        for f in sorted(os.listdir(HERE)):
            if not f.endswith(".py") or f.startswith("_"):
                continue
            name = f[:-3]
            try:
                spec = importlib.util.spec_from_file_location(
                    "dash_mod_" + name, os.path.join(HERE, f))
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
            except Exception:
                continue   # un módulo roto NO tumba el dashboard entero
            mod.__dash_name__ = name
            mods.append(mod)
        _MODULES = mods
    return _MODULES


def get_routes():
    """{path: handler} de todos los módulos. dashboard.py los rutea DESPUÉS de
    los core (un módulo no puede pisar /api/status etc.) y SIEMPRE tras _guard."""
    out = {}
    for m in load_modules():
        out.update(getattr(m, "GET_ROUTES", {}) or {})
    return out


def post_routes():
    out = {}
    for m in load_modules():
        out.update(getattr(m, "POST_ROUTES", {}) or {})
    return out


def js_blobs():
    """[(nombre, js)] de cada dash/*.js — dashboard.py los inyecta al final del
    <body> del HTML servido (después del script base: registerSection ya existe).
    Se leen del disco en cada request (editar el .js = refrescar el navegador)."""
    out = []
    for f in sorted(os.listdir(HERE)):
        if not f.endswith(".js") or f.startswith("_"):
            continue
        try:
            out.append((f[:-3], open(os.path.join(HERE, f), encoding="utf-8").read()))
        except Exception:
            pass
    return out
