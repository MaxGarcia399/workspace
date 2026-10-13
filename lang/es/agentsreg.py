"""Errores de registro/reubicación de agentes (agentsreg.py) — FUENTE."""

STRINGS = {
    "agentsreg.err.bad_name": "nombre inválido: {name} (usa minúsculas, dígitos, - o _)",
    "agentsreg.err.no_brain_dir": "la carpeta del cerebro no existe: {path}",
    "agentsreg.err.not_registered": "no hay agente '{name}' registrado (para uno nuevo usa add)",
    "agentsreg.err.no_dir": "la carpeta no existe: {path}",
    "agentsreg.err.no_read": "sin permiso de lectura: {path}",
    "agentsreg.err.other_agent": "{path} declara al agente '{other}', no a '{name}' (usa --force si es intencional)",
    "agentsreg.err.not_a_brain": "{path} no tiene .workspace/agent.json ni se llama como el cerebro declarado ({target}) — usa --force si es intencional",
}
