#!/usr/bin/env python3
"""workflows.steps.contracts — gates de PREVENCIÓN (Z23/U13).

Los aprendizajes de la ronda Windows (2026-10) convertidos en pasos del
pipeline que REALMENTE corre al crear features y agentes — no un documento
de consejos:

  contracts.prevention   corre los checks de prevención (rápidos, herméticos)
                         ANTES de la suite completa: roster del equipo,
                         resolución de cerebro fuera del resolver, encoding
                         explícito, no-interactivo/plan sin efectos, estado
                         compartido, capacidades declaradas, formato de agente.
  contracts.plan         el plan de una feature declara el contrato (entidades/
                         estado, plataformas, escenarios de riesgo, migración,
                         evidencia por OS) — template: templates/feature/PLAN.md
  agent.validate_definition  (en steps/agent) usa agent_schema.

Contrato de steps/: fn(ctx, paso) → {"ok", "detail", "artifacts"?}.
"""
import os
import subprocess
import sys

#: Módulos de test que forman la red de PREVENCIÓN. Uno por familia de fallo
#: (PREVENTION-WORKFLOWS.md). Un módulo listado que no exista hace FALLAR el
#: gate (así nadie lo borra en silencio).
PREVENTION_MODULES = (
    "test_no_team_roster",          # roster hardcodeado / defaults del equipo
    "test_agent_state",             # registrado ≠ listo; cambios entre vistas
    "test_agent_manage",            # gestión: retirar conserva datos, revalida
    "test_brain_resolver",          # resolver canónico + guard de auto-resolución
    "test_discovery",               # discovery acotado, sin registrar en silencio
    "test_agent_schema",            # formato de agente portable
    "test_windows_readiness",       # encoding explícito / capturas de texto
    "test_session_open_diagnostics",  # sesiones: fallos visibles, init idempotente
    "test_onboarding_resume",       # primera máquina: etapas recuperables
    "test_engine_install",          # instalación oficial por OS + prereqs
    "test_capabilities",            # capacidades OS+motor declaradas, no ifs sueltos
    "test_plan_inert",              # --plan/--dry-run sin spawn/exec
    "test_headless_contract",       # stdin cerrado / NUL / stdout redirigido
    "test_migrate_legacy",          # migración idempotente con backup/rollback
    "test_bootstrap_contract",      # paquete instalable por OS, una regla de ubicación
    "test_engine_versions",         # motores: versiones verificadas + aviso de deriva
    "test_portabilidad_procesos",   # señales sin os.kill · CLIs por su ruta (.cmd)
)

#: Secciones que TODO plan de feature debe declarar (templates/feature/PLAN.md).
PLAN_SECTIONS = (
    "## Contrato",
    "## Plataformas",
    "## Escenarios",
    "## Migración",
    "## Evidencia",
)


def missing_modules(repo):
    return [m for m in PREVENTION_MODULES
            if not os.path.isfile(os.path.join(repo, "tests", m + ".py"))]


def prevention(ctx, step):
    """Paso det: corre la red de prevención. dry → solo el comando."""
    repo = ctx.get("repo") or os.getcwd()
    cmd = [sys.executable, "-B", "-m", "unittest"] + list(PREVENTION_MODULES)
    if ctx.get("dry"):                      # dry = inerte, sin mirar el disco
        return {"ok": True, "detail": "dry: $ (cd tests) " + " ".join(cmd)}
    miss = missing_modules(repo)
    if miss:
        return {"ok": False, "detail": "faltan módulos de prevención: " + ", ".join(miss)}
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    try:
        rc = subprocess.call(cmd, cwd=os.path.join(repo, "tests"), env=env,
                             timeout=float(step.get("timeout") or 600))
    except subprocess.TimeoutExpired:
        return {"ok": False, "detail": "prevención ABORTADA por timeout"}
    return {"ok": rc == 0,
            "detail": "prevención %s (rc=%s)" % ("VERDE" if rc == 0 else "ROJA", rc),
            "artifacts": {"prevention_rc": rc}}


def plan_missing_sections(text):
    return [s for s in PLAN_SECTIONS if s.lower() not in (text or "").lower()]


def plan(ctx, step):
    """Verify: el plan.md de la feature declara el contrato completo."""
    repo = ctx.get("repo") or os.getcwd()
    rel = (ctx.get("params") or {}).get("plan") or step.get("artifact") or "plan.md"
    path = rel if os.path.isabs(rel) else os.path.join(repo, rel)
    if ctx.get("dry"):
        return {"ok": True, "detail": "dry: verificaría secciones de %s" % path}
    try:
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return {"ok": False, "detail": "no existe el plan: %s (template: "
                                       "templates/feature/PLAN.md)" % path}
    miss = plan_missing_sections(text)
    return {"ok": not miss,
            "detail": "plan completo" if not miss else
                      "al plan le faltan secciones: " + ", ".join(miss)}
