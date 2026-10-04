#!/usr/bin/env python3
"""WORKSPACE · workflows.steps — registry por NOMBRE de pasos/verifies det.

Regla de la casa: los pasos det ENVUELVEN lo que ya existe (suite, worktrees,
guard de integridad, rastro N10) — no reinventan nada. Cada función comparte
el mismo contrato:

    fn(ctx, paso) → {"ok": bool, "detail": str, "artifacts": dict opcional}

  ctx  = {"repo", "run_id", "workflow", "dry", "params", "artifacts"}
  paso = la entrada del spec congelado (dict, read-only por convención).

`ctx["dry"]` → NADA real se ejecuta: la función reporta qué haría (misma
convención que `_suite_green(dry)` de front.py).

Añadir un paso (MAPA.md · §cómo se añade): función aquí + su test + entrada
en REGISTRY + referenciarlo en el spec (versión nueva del spec).
"""
import importlib as _importlib

# nombre público → (módulo, función). Import LAZY: resolver un paso no carga
# los demás (front importa `workflows` en el arranque del CLI).
REGISTRY = {
    "suite.green":              ("workflows.steps.suite", "green"),
    "worktree.acquire":         ("workflows.steps.worktree", "acquire"),
    "worktree.verify_acquired": ("workflows.steps.worktree", "verify_acquired"),
    "worktree.release":         ("workflows.steps.worktree", "release"),
    "integrity.check":          ("workflows.steps.integrity", "check"),
    "evidence.artifact_exists": ("workflows.steps.evidence", "artifact_exists"),
    "evidence.step_event":      ("workflows.steps.evidence", "step_event"),
    "front.integrate":          ("workflows.steps.integrate", "run"),
    "triage.route":             ("workflows.steps.triage", "route"),
    "triage.verify_routed":     ("workflows.steps.triage", "verify_routed"),
    "triage.depth_plan":        ("workflows.steps.triage", "depth_plan"),
    # meta-harness (workflows que crean workflows) — workflows/steps/spec.py
    "spec.scaffold":            ("workflows.steps.spec", "scaffold"),
    "spec.classify_frontier":   ("workflows.steps.spec", "classify_frontier"),
    "spec.validate":            ("workflows.steps.spec", "validate"),
    "spec.smoke":               ("workflows.steps.spec", "smoke"),
    "spec.promote":             ("workflows.steps.spec", "promote"),
    "spec.discoverable":        ("workflows.steps.spec", "discoverable"),
    # crear-agente (agentes a nivel harness) — workflows/steps/agent.py
    "agent.create":             ("workflows.steps.agent", "create"),
    "agent.verify_brain":       ("workflows.steps.agent", "verify_brain"),
    "agent.brand":              ("workflows.steps.agent", "brand"),
}

# Contrato del NAMESPACE de artefactos (v1.4): claves que cada paso det
# PUEDE dejar en `state["artifacts"]`. Lo consume `validate_spec` para la
# integridad referencial — un `reads:`/`when.artifact` sin productor
# upstream es error AL CARGAR, no en runtime. Tuple vacía = "no produce
# nada" (contrato CONOCIDO); un nombre sin entrada aquí ni `produces:` en
# el spec = contrato OPACO (aguas abajo no se puede probar nada).
PRODUCES = {
    "suite.green":              ("suite_rc", "suite_timeout_s"),
    "worktree.acquire":         ("worktree_path", "branch", "adopted"),
    "worktree.verify_acquired": (),
    "worktree.release":         ("worktree_release",),
    "integrity.check":          ("integrity_flagged", "integrity_reasons"),
    "evidence.artifact_exists": (),
    "evidence.step_event":      (),
    "front.integrate":          ("integrate_rc", "integrate_noop"),
    "triage.route":             ("triage",),
    "triage.verify_routed":     (),
    "triage.depth_plan":        ("depth_plan",),
    "spec.scaffold":            ("scaffold_path",),
    "spec.classify_frontier":   ("needs_primitive", "missing_primitives"),
    "spec.validate":            ("spec_valid", "spec_validation"),
    "spec.smoke":               ("smoke_ok", "smoke_steps"),
    "spec.promote":             ("promoted_path",),
    "spec.discoverable":        ("registrado", "descubrible"),
    "agent.create":             ("agent_name", "agent_brain"),
    "agent.verify_brain":       ("brain_ok", "brain_gaps"),
    "agent.brand":              ("banner_path", "statusline_path", "dashboard_path"),
}

# Registro dinámico (tests con pasos mock; consumidores que inyectan pasos
# propios sin tocar este archivo). Gana sobre REGISTRY.
EXTRA = {}
EXTRA_PRODUCES = {}


def register(name, fn, produces=None):
    """Registra un callable directo bajo `name` (tests / pasos externos).
    `produces`: claves de artefacto que el paso puede dejar en el run —
    opcional; sin declararlo el contrato del paso queda OPACO para la
    integridad referencial (permisivo aguas abajo, jamás error)."""
    EXTRA[str(name)] = fn
    if produces is not None:
        EXTRA_PRODUCES[str(name)] = tuple(str(p) for p in produces)


def unregister(name):
    EXTRA.pop(str(name), None)
    EXTRA_PRODUCES.pop(str(name), None)


def produces_of(name):
    """Claves de artefacto que el paso `name` puede producir (tuple; vacía =
    'no produce nada', contrato CONOCIDO) o None = contrato opaco."""
    if name in EXTRA_PRODUCES:
        return EXTRA_PRODUCES[name]
    if name in EXTRA:
        return None
    return PRODUCES.get(name)


def resolve(name):
    """Callable del paso `name`. KeyError claro si no existe — el runner
    prefiere reventar ANTES de correr que inventar un paso."""
    if name in EXTRA:
        return EXTRA[name]
    if name not in REGISTRY:
        raise KeyError("paso det desconocido: %r (registrados: %s)"
                       % (name, ", ".join(sorted(REGISTRY))))
    modname, fnname = REGISTRY[name]
    return getattr(_importlib.import_module(modname), fnname)


def known():
    """Nombres registrados (estáticos + dinámicos), ordenados."""
    return sorted(set(REGISTRY) | set(EXTRA))
