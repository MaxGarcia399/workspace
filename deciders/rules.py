"""WORKSPACE · deciders/rules — el decisor SIN IA, de uso INTERNO.

Determinista y local: cuenta las palabras que cada opción comparte con el
contexto (coincidencia exacta, y media por raíz de 4 letras) y, con menos
peso, con la pregunta; un empujón mínimo a las primeras opciones rompe
empates; un softmax lo vuelve probabilidades. Misma entrada → misma salida.
Nada sale de la computadora, no cuesta nada. Stdlib."""
import math
import re
import time

META = {"id": "rules", "label": "Reglas", "local": True,
        "kinds": ["choice", "score"], "offer": False,
        # INTERNO: para pruebas y `tools/decisores_live_check.py --dry`; ninguna
        # pantalla lo muestra (el socio no lo elige).
        "internal": True,
        # local y sin costo: el límite solo cuida la memoria y el tiempo
        "context_tokens": 100000, "price_in_per_m": 0.0, "builtin": True}

_WORD = re.compile(r"[a-záéíóúüñ0-9]+")


def status():
    return {"ready": True, "detail": "local"}


def _words(s):
    return {w for w in _WORD.findall(str(s or "").lower()) if len(w) > 2}


def _probs(context, question, options):
    base, preg = _words(context), _words(question)
    raw = []
    n = len(options)
    for i, o in enumerate(options):
        ws = _words(o)
        hit = (len(ws & base)
               + sum(0.5 for w in ws for b in base if w != b and w[:4] == b[:4])
               + 0.3 * len(ws & preg))
        raw.append(hit + 0.15 * (n - i) / n)
    top = max(raw)
    ex = [math.exp(1.6 * (r - top)) for r in raw]
    tot = sum(ex)
    return {o: e / tot for o, e in zip(options, ex)}


def decide(req):
    t0 = time.time()
    try:
        kind = req.get("kind") or "choice"
        opts = [str(o) for o in (req.get("options") or []) if str(o).strip()]
        if kind == "score" and not opts:
            opts = ["yes", "no"]
        if len(opts) < 2:
            raise ValueError("hacen falta al menos 2 opciones")
        probs = _probs(req.get("context", ""), req.get("question", ""), opts)
        choice = max(opts, key=lambda o: (probs[o], -opts.index(o)))
        return {"choice": choice,
                "score": probs[opts[0]] if kind == "score" else None,
                "probs": probs, "ms": int((time.time() - t0) * 1000),
                "cost_usd": 0.0, "decider": "rules", "ok": True, "error": None}
    except Exception as e:
        return {"choice": None, "score": None, "probs": {},
                "ms": int((time.time() - t0) * 1000), "cost_usd": 0.0,
                "decider": "rules", "ok": False, "error": str(e)[:120]}
