#!/usr/bin/env python3
"""workflows.steps.integrity — wrap del guard anti-trampa de tests.

Envuelve `dash/dev/test_integrity.check` (gates B2/D3 de phase-gates) como
verify det. CONSERVA su contrato de SEÑAL fail-open: el guard jamás pone el
paso en rojo — si hay señal, el detalle lleva el WARN con las razones y el
run guarda `integrity_flagged` como artefacto (evidencia persistida, que es
lo que al paso ad-hoc le faltaba)."""


def check(ctx, step):
    """Verify det: ¿el diff contra `base` DEBILITA la suite? (WARN, fail-open)."""
    base = step.get("base", "main")
    if ctx.get("dry"):
        return {"ok": True, "detail": "dry: guard anti-trampa omitido "
                                      "(base %s)" % base}
    try:
        from dash.dev import test_integrity
        res = test_integrity.check(base=base, repo=ctx.get("repo"))
    except Exception:
        res = None
    if res is None:                       # git ausente / no-repo / error
        return {"ok": True, "detail": "guard de tests no pudo correr — "
                                      "fail-open (señal, jamás bloqueo)"}
    if res.get("flagged"):
        reasons = res.get("reasons") or []
        return {"ok": True,
                "detail": "WARN guard de tests (fail-open): "
                          + "; ".join(reasons),
                "artifacts": {"integrity_flagged": True,
                              "integrity_reasons": reasons}}
    return {"ok": True, "detail": "guard de tests: sin señal (la suite no "
                                  "se debilitó vs %s)" % base,
            "artifacts": {"integrity_flagged": False}}
