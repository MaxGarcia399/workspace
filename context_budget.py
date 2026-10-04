#!/usr/bin/env python3
"""WORKSPACE · context_budget — presupuesto de contexto del motor #2 (spec C14).

Spec congelada (síntesis §10 C14 + §10-bis, Odysseus `context_budget.py` +
Hermes `_compression_threshold_for_model`):

· **Budget adaptativo**: ventana desconocida → piso conocido de 6,000 tokens
  (el default de Odysseus: *"a hard ceiling for every model"* hasta que lo
  escalaron sin perder el piso chico); ventana conocida → `ventana × 0.85`
  con cap duro de 200k.
· **Régimen small-context**: ventanas ≤ 8,192 entran a trimming agresivo.
· **Threshold de compresión POR MODELO** (Hermes): quirk del provider
  (`quirks.compression_thresholds`), default 0.85 — modelos con ventana corta
  comprimen antes.
· **Escalera de degradación de 4 pasos** (`trim_for_context`, Odysseus):
    1. drop mensajes system de RAG/memoria (el preset sobrevive)
    2. truncar el system prompt a 2,000 chars CON MARCA visible
    3. drop turnos viejos protegiendo los últimos 10 + el turno ACTUAL
    4. truncar el mensaje actual con aviso (*"otherwise the model appears
       to 'ignore' large pastes"*)
  Mensajes con `_protected: True` JAMÁS se caen ni se truncan. Toda
  degradación deja marca visible en el contexto — degradar jamás en silencio
  (regla 6 small-model-first).

Forma de mensaje esperada (la mínima común OpenAI/Anthropic-style):
  {"role": "system|user|assistant|tool", "content": str,
   "kind": opcional ("rag"|"memory"), "_protected": opcional bool}

Lo usa el motor real (E-2) en su loop; el motor #1 (claude-code) NO — el
vendor compacta solo. Testeable solo (tests/test_context_budget.py).
Cero dependencias (stdlib, Python 3.9+). Amputable (C10).
"""

# ── constantes de la spec (datos, ajustables sin tocar la lógica) ───────────
DEFAULT_BUDGET = 6_000          # tokens — piso conocido si la ventana es desconocida
HEADROOM = 0.85                 # fracción utilizable de la ventana
CAP = 200_000                   # cap duro (tokens)
SMALL_CONTEXT_LIMIT = 8_192     # ventanas ≤ esto → régimen agresivo
DEFAULT_COMPRESSION_THRESHOLD = 0.85
CHARS_PER_TOKEN = 4             # estimador barato chars→tokens (sin tokenizer)

SYSTEM_TRUNC_LIMIT = 2_000      # chars (paso 2)
PROTECT_LAST_TURNS = 10         # turnos protegidos al final (paso 3)

# marcas VISIBLES de degradación (regla: el modelo chico sabe qué no sabe)
MARK_SYSTEM_TRUNC = ("\n[… system prompt truncado por presupuesto de contexto — "
                     "la versión completa vive en disco]")
MARK_TURNS_DROPPED = ("[… %d turno(s) antiguo(s) descartado(s) por presupuesto "
                      "de contexto — los últimos %d se conservan]")
MARK_CURRENT_TRUNC = ("\n[… mensaje truncado por presupuesto de contexto — "
                      "el original excedía la ventana del modelo]")

LADDER_STEPS = ("drop_rag_memory", "truncate_system", "drop_old_turns",
                "truncate_current")


def estimate_tokens(text):
    """Estimador barato (chars/4). El motor real puede pasar su tokenizer
    a trim_for_context vía count=."""
    return max(0, len(text or "") // CHARS_PER_TOKEN)


def budget(window=None, headroom=HEADROOM, cap=CAP):
    """Presupuesto adaptativo de tokens.
    · window None/0/inválido → DEFAULT_BUDGET (piso conocido)
    · conocido → int(window × headroom), capado en `cap`."""
    try:
        w = int(window or 0)
    except (TypeError, ValueError):
        w = 0
    if w <= 0:
        return DEFAULT_BUDGET
    return min(int(w * headroom), cap)


def is_small_context(window):
    """True si la ventana amerita el régimen de trimming agresivo."""
    try:
        w = int(window or 0)
    except (TypeError, ValueError):
        return False
    return 0 < w <= SMALL_CONTEXT_LIMIT


def compression_threshold(model, provider=None):
    """Threshold de compresión por modelo (Hermes): quirk declarativo
    `quirks.compression_thresholds` del provider — match exacto, luego por
    prefijo; default 0.85. Jamás un if por modelo en código."""
    table = (((provider or {}).get("quirks") or {})
             .get("compression_thresholds") or {})
    m = model or ""
    if m in table:
        return float(table[m])
    for prefix, th in table.items():
        if prefix and m.startswith(prefix):
            return float(th)
    return DEFAULT_COMPRESSION_THRESHOLD


def should_compress(used_tokens, window=None, model="", provider=None):
    """True si el uso cruzó el threshold del modelo sobre su budget."""
    b = budget(window)
    return used_tokens >= b * compression_threshold(model, provider)


# ── escalera de degradación (4 pasos, _protected jamás cae) ─────────────────
def _total(msgs, count):
    return sum(count(str(m.get("content", ""))) for m in msgs)


def _protected(m):
    return bool(m.get("_protected"))


def trim_for_context(messages, budget_tokens, count=estimate_tokens):
    """Aplica la escalera de 4 pasos hasta que el total quepa en
    `budget_tokens`. NO muta la lista original.

    Devuelve (mensajes, pasos_aplicados) — pasos ⊆ LADDER_STEPS, en orden.
    Garantías: mensajes `_protected` jamás se descartan ni truncan; toda
    degradación deja marca visible; si ya cabe, (copia, []). El truncado
    final mide con `count` (el tokenizer inyectado) — pero si los mensajes
    `_protected` por sí solos exceden el presupuesto, el fit NO está
    garantizado (jamás se tocan; el caller decide)."""
    msgs = [dict(m) for m in (messages or [])]
    steps = []
    if _total(msgs, count) <= budget_tokens:
        return msgs, steps

    # Paso 1 — drop system de RAG/memoria (descartables por diseño)
    keep = [m for m in msgs
            if _protected(m) or m.get("kind") not in ("rag", "memory")]
    if len(keep) != len(msgs):
        msgs = keep
        steps.append("drop_rag_memory")
        if _total(msgs, count) <= budget_tokens:
            return msgs, steps

    # Paso 2 — truncar el system prompt CON marca
    did = False
    for m in msgs:
        if (m.get("role") == "system" and not _protected(m)
                and len(str(m.get("content", ""))) > SYSTEM_TRUNC_LIMIT):
            m["content"] = (str(m["content"])[:SYSTEM_TRUNC_LIMIT]
                            + MARK_SYSTEM_TRUNC)
            did = True
    if did:
        steps.append("truncate_system")
        if _total(msgs, count) <= budget_tokens:
            return msgs, steps

    # Paso 3 — drop turnos viejos; proteger los últimos N + el turno ACTUAL
    system = [m for m in msgs if m.get("role") == "system"]
    turns = [m for m in msgs if m.get("role") != "system"]
    if len(turns) > PROTECT_LAST_TURNS + 1:
        tail = turns[-(PROTECT_LAST_TURNS + 1):]          # últimos 10 + actual
        head = turns[:-(PROTECT_LAST_TURNS + 1)]
        kept_head = [m for m in head if _protected(m)]     # _protected jamás cae
        dropped = len(head) - len(kept_head)
        if dropped > 0:
            marker = {"role": "system",
                      "content": MARK_TURNS_DROPPED % (dropped,
                                                       PROTECT_LAST_TURNS)}
            msgs = system + [marker] + kept_head + tail
            steps.append("drop_old_turns")
            if _total(msgs, count) <= budget_tokens:
                return msgs, steps

    # Paso 4 — truncar el mensaje ACTUAL con aviso (último recurso)
    # R3-F4: truncar MIDIENDO con `count` (el tokenizer inyectado), no con la
    # heurística chars/4 — con un tokenizer real (CJK/código denso, ~1-2
    # chars/token) `allowed × CHARS_PER_TOKEN` conservaba hasta ~4× los tokens
    # permitidos y devolvía "éxito" sin re-chequear → el provider rechazaba
    # por contexto igual. Bisección sobre los chars conservados, re-midiendo
    # cada candidato con `count` (asume tokens no-decrecientes al crecer el
    # prefijo — cierto para cualquier tokenizer real).
    # NOTA (honestidad): si el presupuesto ya se lo comen mensajes
    # `_protected` (que JAMÁS se tocan), el fit NO está garantizado — se
    # trunca el actual a su mínimo (solo la marca) como best-effort.
    for m in reversed(msgs):
        if m.get("role") != "system":
            if _protected(m):
                break   # ni el último recurso toca lo protegido
            content = str(m.get("content", ""))
            rest = _total(msgs, count) - count(content)

            def _fits(k):
                return (rest + count(content[:k] + MARK_CURRENT_TRUNC)
                        <= budget_tokens)
            lo, hi = 0, len(content)     # máximo k con _fits(k); si ninguno → 0
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if _fits(mid):
                    lo = mid
                else:
                    hi = mid - 1
            if lo >= len(content):
                break   # cabría entero aun con marca — no marcar de gratis
            m["content"] = content[:lo] + MARK_CURRENT_TRUNC
            steps.append("truncate_current")
            break
    return msgs, steps


if __name__ == "__main__":
    # demo rápida:  python3 context_budget.py [ventana]
    import sys
    w = int(sys.argv[1]) if len(sys.argv) > 1 else 0
    print("ventana %s → budget %d tokens · small-context: %s"
          % (w or "(desconocida)", budget(w or None), is_small_context(w)))
