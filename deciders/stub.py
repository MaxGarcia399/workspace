"""WORKSPACE · deciders/stub — eco determinista para pruebas (no se ofrece).

Elige SIEMPRE la primera opción con certeza total. Sirve de prueba viva del
contrato y del cambio de decisor sin red ni IA."""
import time

META = {"id": "stub", "label": "Stub (pruebas)", "local": True,
        "kinds": ["choice", "score"], "offer": False, "internal": True,
        "context_tokens": 100000,
        "price_in_per_m": 0.0}


def status():
    return {"ready": True, "detail": "eco"}


def decide(req):
    t0 = time.time()
    opts = [str(o) for o in (req.get("options") or [])]
    if req.get("kind") == "score" and not opts:
        opts = ["yes", "no"]
    if not opts:
        return {"choice": None, "score": None, "probs": {}, "ms": 0,
                "cost_usd": 0.0, "decider": "stub", "ok": False,
                "error": "sin opciones"}
    probs = {o: (1.0 if i == 0 else 0.0) for i, o in enumerate(opts)}
    return {"choice": opts[0], "score": 1.0 if req.get("kind") == "score" else None,
            "probs": probs, "ms": int((time.time() - t0) * 1000),
            "cost_usd": 0.0, "decider": "stub", "ok": True, "error": None}
