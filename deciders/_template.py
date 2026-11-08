"""WORKSPACE · deciders/_template.py — PLANTILLA y CONTRATO de un decisor.

Para crear uno: copia este archivo a deciders/<id>.py (sin guion bajo) e
implementa decide(). La fachada `decisions.py` lo encuentra sola por nombre
— no se toca nada más. Contrato completo: deciders/CONTRACT.md.

  META = {"id", "label", "local", "kinds", "offer"}                [OBLIGATORIO]
      id     = nombre del archivo (rules, jev…)
      label  = nombre visible
      local  = True si nada sale de esta computadora
      kinds  = ["choice"] y/o ["score"]
      offer  = False para decisores de prueba (no se ofrecen en Ajustes)

  decide(req) -> dict                                               [OBLIGATORIO]
      req = {"kind": "choice"|"score", "question": str,
             "options": [str, ...] (≥2; en score, opcional),
             "context": str (YA sin secretos), "point": str, "timeout_ms": int}
      → {"choice": str|None, "score": float|None, "probs": {opción: p},
         "ms": int, "cost_usd": float|None, "decider": META["id"],
         "ok": bool, "error": str|None}
      JAMÁS levanta: cualquier problema → ok False con un error legible.
      El tiempo límite lo pone la fachada (hilo + join); el decisor solo debe
      no colgarse para siempre.

  status() -> {"ready": bool, "detail": str}                         [OPCIONAL]
      Disponibilidad honesta y BARATA (sin red). Omitida → listo.

Reglas: stdlib (un SDK externo solo con import perezoso dentro de decide),
cross-platform, credenciales solo del entorno, nunca impresas.
"""
import time

META = {"id": "template", "label": "Plantilla", "local": True,
        "kinds": ["choice"], "offer": False}


def status():
    return {"ready": False, "detail": "plantilla"}


def decide(req):
    t0 = time.time()
    return {"choice": None, "score": None, "probs": {},
            "ms": int((time.time() - t0) * 1000), "cost_usd": None,
            "decider": META["id"], "ok": False,
            "error": "plantilla: copia deciders/_template.py a deciders/<id>.py"}
