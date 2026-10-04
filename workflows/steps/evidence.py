#!/usr/bin/env python3
"""workflows.steps.evidence — verifies de TRAZA: evidencia real, no claims.

La tesis del verify step: código que lee lo que de verdad pasó (¿existe el
archivo? ¿quedó la traza N10 del paso?) en vez de creerle al agente.

  · artifact_exists — el artefacto declarado por el paso existe en disco.
  · step_event      — el rastro N10 (`events.read_events`) tiene el evento
                      `wf_step` del paso `of` (default: el propio paso) de
                      ESTE run — ¿de verdad corrió?
"""
import os


def artifact_exists(ctx, step):
    """Verify det: `step["artifact"]` existe (ruta del run o relativa al repo)."""
    rel = step.get("artifact") or ""
    if not rel:
        return {"ok": False, "detail": "el paso no declara `artifact`"}
    # el run puede haber materializado el artefacto bajo otro path
    p = (ctx.get("artifacts") or {}).get(rel) or rel
    if not os.path.isabs(p):
        p = os.path.join(ctx.get("repo") or os.getcwd(), p)
    ok = os.path.exists(p)
    return {"ok": ok, "detail": "artefacto `%s` %s (%s)"
            % (rel, "existe" if ok else "NO existe", p)}


def step_event(ctx, step):
    """Verify det: hay traza N10 `wf_step` del paso `of` en este run."""
    target = step.get("of") or step.get("id")
    try:
        import events
        recs = events.read_events(limit=500)
    except Exception:
        return {"ok": False, "detail": "rastro N10 no disponible"}
    for rec in recs:
        pl = rec.get("payload") or {}
        if (pl.get("event") == "wf_step" and pl.get("run") == ctx.get("run_id")
                and pl.get("step") == target):
            return {"ok": True, "detail": "traza N10 encontrada para el paso "
                                          "`%s` de este run" % target}
    return {"ok": False, "detail": "sin traza N10 del paso `%s` en el rastro "
                                   "— no hay evidencia de que corrió" % target}
