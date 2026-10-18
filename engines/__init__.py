"""WORKSPACE · engines — un adaptador por motor (contrato en CONTRACT.md).

Aquí solo vive la marca del motor de una sesión, que comparten los
lanzadores (interactive, claude_code, _ui) y dispatch.

WORKSPACE_ENGINE significa dos cosas: memoria v1 se la exporta al motor
(memoria.py la lee: cada nota dice de qué motor viene) y dispatch la toma
como «abrir con este motor». Sin distinguirlas, un agente abierto desde la
terminal de otra sesión (o por el propio agente) se abría con el motor de
esa sesión y no con el suyo (revisión de motores 2026-10-17, hallazgo 5).
"""
import os

#: Qué valor de WORKSPACE_ENGINE puso el lanzador de la sesión.
SESSION_ENGINE = "WORKSPACE_SESSION_ENGINE"


def mark_session_engine(env, engine):
    """El motor de la sesión en `env` (dict u os.environ), para memoria v1,
    con la marca de que lo puso el lanzador."""
    env["WORKSPACE_ENGINE"] = str(engine)
    env[SESSION_ENGINE] = str(engine)


def env_engine_override(env=None):
    """El motor que el socio pidió por WORKSPACE_ENGINE, o "" si no pidió
    ninguno: el valor heredado de la sesión desde la que se abre (igual a la
    marca) no es una elección suya."""
    env = os.environ if env is None else env
    val = (env.get("WORKSPACE_ENGINE") or "").strip()
    if val and val == (env.get(SESSION_ENGINE) or "").strip():
        return ""
    return val
