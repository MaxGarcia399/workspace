#!/usr/bin/env python3
"""workflows.grammar — gramática declarativa del spec (runner v1.2).

Dos primitivas ADITIVAS (un spec sin ellas corre exactamente igual):

`when:` — transición CONDICIONAL de un paso
  Predicado DECLARATIVO evaluado contra los artefactos del run justo antes
  de correr el paso. Falso ⇒ el paso queda `skipped` (estado propio, distinto
  de ok/stub/fail) y el run sigue. Verdadero ⇒ el paso corre normal.

  SEGURIDAD (no negociable): el predicado son DATOS, no código. Aquí no hay
  `eval`, `exec`, imports dinámicos ni acceso a nada fuera del dict de
  artefactos del run: la evaluación es un lookup por clave + un puñado de
  ops acotadas, determinista y sin efectos. Un "predicado malicioso" no
  ejecuta nada: o lo rechaza `validate_when` (op/clave desconocida) o es un
  string inerte que simplemente no matchea.

  Gramática (hoja):
    {"artifact": "<clave en artifacts>",     # requerido
     "path": "a.b.0",                        # opcional: drill-down con puntos
                                             #   (dict → clave · list → índice)
     "op": <op>,                             # requerido
     "value": <escalar JSON>}                # solo para las ops comparativas
  Ops sin `value`:  exists · not_exists · non_empty · empty
  Ops con `value`:  eq · ne · gt · gte · lt · lte  (gt/gte/lt/lte: ambos
                    lados deben ser números; si no, el predicado es falso)
  Combinadores (opcionales, anidables hasta 8 niveles):
    {"all": [p…]} · {"any": [p…]} · {"not": p}

  Semántica con dato AUSENTE (artefacto o path que no existe): fail-safe y
  determinista — exists/non_empty/eq/ne/gt/gte/lt/lte → falso;
  not_exists/empty → verdadero. `non_empty` = presente Y truthy (lista/dict/
  str no vacíos; número ≠ 0); `empty` es su negación exacta.

`output_schema:` — contrato de FORMA de la salida de un paso
  Esquema mínimo (stdlib puro, sin dependencias) que el runner valida contra
  el artefacto declarado del paso ANTES del verify semántico. No cumple ⇒
  fallo ESTRUCTURAL con detalle claro y `retriable: false` (un contrato roto
  es permanente: reintentar en loop no lo arregla — escala al socio).

  Gramática (nodo, recursivo):
    {"type": object|list|string|number|int|bool|any,
     "items": <nodo>,                        # solo list
     "min_items"/"max_items": int ≥ 0,      # solo list
     "required": {clave: <nodo>},           # solo object (claves obligadas)
     "optional": {clave: <nodo>},           # solo object (si están, validan)
     "enum": [escalares]}                    # solo string/number/int/bool
  Claves extra en el objeto validado se PERMITEN (el contrato es mínimo);
  claves desconocidas en el SCHEMA se rechazan (typo ≠ contrato más laxo).

Ambas validaciones de forma (`validate_when` / `validate_output_schema`)
corren en `validate_spec`: un spec malformado revienta ANTES de correr nada.
"""
import json as _json
import os as _os

_MISSING = object()          # dato ausente ≠ dato None (sentinel interno)
_SCALAR = (str, int, float, bool, type(None))

# ── when: mini-DSL ─────────────────────────────────────────────────────────
WHEN_OPS_SIMPLE = ("exists", "not_exists", "non_empty", "empty")
WHEN_OPS_VALUE = ("eq", "ne", "gt", "gte", "lt", "lte")
WHEN_COMBINATORS = ("all", "any", "not")
_WHEN_MAX_DEPTH = 8


def validate_when(pred, _depth=0):
    """Valida la FORMA del predicado. ValueError con el qué exacto — corre en
    validate_spec: un `when` malformado jamás llega a evaluarse. Devuelve pred."""
    if _depth > _WHEN_MAX_DEPTH:
        raise ValueError("predicado anidado más de %d niveles" % _WHEN_MAX_DEPTH)
    if not isinstance(pred, dict) or not pred:
        raise ValueError("el predicado debe ser un objeto no vacío "
                         "(datos declarativos, jamás código)")
    combs = [k for k in WHEN_COMBINATORS if k in pred]
    if combs:
        if len(pred) != 1:
            raise ValueError("combinador `%s` no admite claves hermanas "
                             "(recibí %s)" % (combs[0], sorted(pred)))
        k = combs[0]
        if k == "not":
            validate_when(pred[k], _depth + 1)
        else:
            subs = pred[k]
            if not isinstance(subs, list) or not subs:
                raise ValueError("`%s` requiere una lista no vacía de "
                                 "predicados" % k)
            for p in subs:
                validate_when(p, _depth + 1)
        return pred
    extra = set(pred) - {"artifact", "path", "op", "value"}
    if extra:
        raise ValueError("claves desconocidas en el predicado: %s "
                         "(soportadas: artifact · path · op · value)"
                         % sorted(extra))
    art = pred.get("artifact")
    if not isinstance(art, str) or not art:
        raise ValueError("`artifact` requerido (string no vacío)")
    path = pred.get("path")
    if path is not None and (not isinstance(path, str) or not path):
        raise ValueError("`path` debe ser string no vacío "
                         "(segmentos separados por punto)")
    op = pred.get("op")
    if op not in WHEN_OPS_SIMPLE + WHEN_OPS_VALUE:
        raise ValueError("op desconocida %r (soportadas: %s)"
                         % (op, " · ".join(WHEN_OPS_SIMPLE + WHEN_OPS_VALUE)))
    if op in WHEN_OPS_VALUE:
        if "value" not in pred:
            raise ValueError("op `%s` requiere `value`" % op)
        if not isinstance(pred["value"], _SCALAR):
            raise ValueError("`value` debe ser escalar JSON "
                             "(string/número/bool/null)")
    elif "value" in pred:
        raise ValueError("op `%s` no lleva `value`" % op)
    return pred


def _lookup(pred, artifacts):
    """Valor referido por artifact+path, o _MISSING. Solo lookups por clave/
    índice sobre el dict de artefactos — cero efectos, cero código."""
    art = pred["artifact"]
    if not isinstance(artifacts, dict) or art not in artifacts:
        return _MISSING
    cur = artifacts[art]
    for seg in (pred.get("path") or "").split("."):
        if not seg:
            continue
        if isinstance(cur, dict) and seg in cur:
            cur = cur[seg]
        elif isinstance(cur, list) and seg.isdigit() and int(seg) < len(cur):
            cur = cur[int(seg)]
        else:
            return _MISSING
    return cur


def _is_num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def eval_when(pred, artifacts):
    """Evalúa un predicado YA validado → (bool, detalle legible).
    Determinista, puro, sin efectos: mismo estado ⇒ mismo resultado."""
    holds, det, _ = eval_when_certain(pred, artifacts)
    return holds, det


def eval_when_certain(pred, artifacts):
    """Evalúa un predicado YA validado → (holds, detalle, certain).

    `holds` es EXACTAMENTE el valor fail-safe de siempre (eval_when).
    `certain` (v1.4) dice si ese valor está DEFINIDO por los datos o es solo
    el default fail-safe ante un dato irresoluble:
      · ops de PRESENCIA (exists/not_exists/non_empty/empty) → siempre
        certain: la ausencia ES una respuesta definida para ellas.
      · eq/ne con dato AUSENTE → incierto (no se puede comparar lo que no
        está); gt/gte/lt/lte además exigen números en AMBOS lados — tipos
        incomparables = incierto.
      · combinadores: lógica trivaluada de Kleene — `all` es cierto-falso si
        algún hijo es falso con certeza; `any` es cierto-verdadero si algún
        hijo es verdadero con certeza; si no, la certeza exige TODOS los
        hijos ciertos. `not` hereda la certeza del hijo.
    Un consumidor que no tolere incertidumbre (gate HUMAN del runner) debe
    FALLAR-CERRADO cuando certain=False — jamás saltarse en silencio."""
    if "all" in pred:
        rs = [eval_when_certain(p, artifacts) for p in pred["all"]]
        holds = all(r[0] for r in rs)
        certain = (all(r[2] for r in rs)
                   or any(r[2] and not r[0] for r in rs))
        return holds, "all(%d predicados) → %s" % (
            len(pred["all"]), "verdadero" if holds else "falso"), certain
    if "any" in pred:
        rs = [eval_when_certain(p, artifacts) for p in pred["any"]]
        holds = any(r[0] for r in rs)
        certain = (all(r[2] for r in rs)
                   or any(r[2] and r[0] for r in rs))
        return holds, "any(%d predicados) → %s" % (
            len(pred["any"]), "verdadero" if holds else "falso"), certain
    if "not" in pred:
        inner, det, certain = eval_when_certain(pred["not"], artifacts)
        return (not inner), "not(%s)" % det, certain
    v = _lookup(pred, artifacts)
    op = pred["op"]
    certain = True
    if op == "exists":
        holds = v is not _MISSING
    elif op == "not_exists":
        holds = v is _MISSING
    elif op == "non_empty":
        holds = v is not _MISSING and bool(v)
    elif op == "empty":
        holds = v is _MISSING or not v
    elif op in ("eq", "ne"):
        if v is _MISSING:
            holds = False                    # ausente: ni igual ni distinto
            certain = False                  # … y NADIE puede afirmarlo
        else:
            holds = (v == pred["value"]) if op == "eq" else (v != pred["value"])
    else:                                    # gt · gte · lt · lte
        w = pred["value"]
        if v is _MISSING or not _is_num(v) or not _is_num(w):
            holds = False                    # comparación numérica o nada
            certain = False                  # dato ausente o incomparable
        else:
            holds = {"gt": v > w, "gte": v >= w,
                     "lt": v < w, "lte": v <= w}[op]
    ref = pred["artifact"] + (("." + pred["path"]) if pred.get("path") else "")
    val = (" %r" % (pred["value"],)) if op in WHEN_OPS_VALUE else ""
    return holds, "%s %s%s → %s" % (ref, op, val,
                                    "verdadero" if holds else "falso"), certain


def when_refs(pred):
    """Hojas (artifact, path) de un predicado `when` YA validado — lo que el
    predicado REFERENCIA. Lo consume la integridad referencial del spec."""
    if not isinstance(pred, dict):
        return []
    for comb in ("all", "any"):
        if comb in pred:
            out = []
            for p in pred[comb]:
                out += when_refs(p)
            return out
    if "not" in pred:
        return when_refs(pred["not"])
    return [(pred.get("artifact"), pred.get("path") or "")]


def path_in_schema(schema, path):
    """¿El `path` de un `when` CABE en el `output_schema` del productor?

    → True  = garantizado por el contrato (cada segmento declarado)
    → False = PROBADAMENTE imposible/fuera de contrato: segmento no-índice
              sobre una lista · path restante sobre un escalar · clave no
              declarada en un object que SÍ declara claves (required/
              optional — para permitirla, declárala en `optional`)
    → None  = el contrato no alcanza a decidir (type=any · object sin
              claves declaradas · list sin items) — se permite.
    Estático y puro: corre al CARGAR el spec, jamás en runtime."""
    node = schema
    for seg in [s for s in (path or "").split(".") if s]:
        t = node.get("type")
        if t == "any":
            return None
        if t == "object":
            req = node.get("required") or {}
            opt = node.get("optional") or {}
            if seg in req:
                node = req[seg]
            elif seg in opt:
                node = opt[seg]
            elif req or opt:
                return False
            else:
                return None
        elif t == "list":
            if not seg.isdigit():
                return False
            node = node.get("items")
            if node is None:
                return None
        else:
            return False
    return True


# ── output_schema: contrato de forma ───────────────────────────────────────
SCHEMA_TYPES = ("object", "list", "string", "number", "int", "bool", "any")
_SCHEMA_KEYS = {"type", "items", "required", "optional", "enum",
                "min_items", "max_items"}
_SCHEMA_MAX_DEPTH = 16
_MAX_ERRORS = 10             # cota de detalle: los primeros N errores


def validate_output_schema(node, _depth=0):
    """Valida la FORMA del schema (el schema del schema). ValueError con el
    qué exacto — corre en validate_spec. Devuelve node."""
    if _depth > _SCHEMA_MAX_DEPTH:
        raise ValueError("schema anidado más de %d niveles" % _SCHEMA_MAX_DEPTH)
    if not isinstance(node, dict):
        raise ValueError("cada nodo del schema debe ser un objeto")
    extra = set(node) - _SCHEMA_KEYS
    if extra:
        raise ValueError("claves desconocidas en el schema: %s (soportadas: "
                         "%s)" % (sorted(extra), " · ".join(sorted(_SCHEMA_KEYS))))
    t = node.get("type")
    if t not in SCHEMA_TYPES:
        raise ValueError("`type` inválido %r (soportados: %s)"
                         % (t, " · ".join(SCHEMA_TYPES)))
    if "items" in node:
        if t != "list":
            raise ValueError("`items` solo aplica a type=list (type=%s)" % t)
        validate_output_schema(node["items"], _depth + 1)
    for k in ("required", "optional"):
        if k in node:
            if t != "object":
                raise ValueError("`%s` solo aplica a type=object (type=%s)"
                                 % (k, t))
            if not isinstance(node[k], dict):
                raise ValueError("`%s` debe ser objeto {clave: nodo}" % k)
            for key, sub in node[k].items():
                if not isinstance(key, str) or not key:
                    raise ValueError("clave inválida en `%s`: %r" % (k, key))
                validate_output_schema(sub, _depth + 1)
    if "enum" in node:
        if t not in ("string", "number", "int", "bool"):
            raise ValueError("`enum` solo aplica a tipos escalares (type=%s)" % t)
        vals = node["enum"]
        if (not isinstance(vals, list) or not vals
                or any(not isinstance(x, _SCALAR) for x in vals)):
            raise ValueError("`enum` debe ser lista no vacía de escalares")
    for k in ("min_items", "max_items"):
        if k in node:
            if t != "list":
                raise ValueError("`%s` solo aplica a type=list (type=%s)" % (k, t))
            v = node[k]
            if not isinstance(v, int) or isinstance(v, bool) or v < 0:
                raise ValueError("`%s` debe ser entero ≥ 0 (recibí %r)" % (k, v))
    if ("min_items" in node and "max_items" in node
            and node["min_items"] > node["max_items"]):
        raise ValueError("min_items > max_items")
    return node


def check_value(value, node, path="$"):
    """Valida un VALOR contra un schema YA validado → lista de errores
    (vacía = cumple). Puro y determinista; corta en _MAX_ERRORS."""
    t = node["type"]
    if t == "any":
        ok = True
    elif t == "string":
        ok = isinstance(value, str)
    elif t == "bool":
        ok = isinstance(value, bool)
    elif t == "int":
        ok = isinstance(value, int) and not isinstance(value, bool)
    elif t == "number":
        ok = _is_num(value)
    elif t == "list":
        ok = isinstance(value, list)
    else:                                    # object
        ok = isinstance(value, dict)
    if not ok:
        return ["%s: se esperaba %s, llegó %s"
                % (path, t, type(value).__name__)]
    errs = []
    if "enum" in node and value not in node["enum"]:
        errs.append("%s: %r fuera del enum %s" % (path, value, node["enum"]))
    if t == "list":
        n = len(value)
        if "min_items" in node and n < node["min_items"]:
            errs.append("%s: %d elemento(s), mínimo %d"
                        % (path, n, node["min_items"]))
        if "max_items" in node and n > node["max_items"]:
            errs.append("%s: %d elemento(s), máximo %d"
                        % (path, n, node["max_items"]))
        if "items" in node:
            for i, item in enumerate(value):
                if len(errs) >= _MAX_ERRORS:
                    break
                errs += check_value(item, node["items"], "%s[%d]" % (path, i))
    elif t == "object":
        for key, sub in (node.get("required") or {}).items():
            if key not in value:
                errs.append("%s.%s: falta la clave requerida" % (path, key))
            else:
                errs += check_value(value[key], sub, "%s.%s" % (path, key))
        for key, sub in (node.get("optional") or {}).items():
            if key in value:
                errs += check_value(value[key], sub, "%s.%s" % (path, key))
    return errs[:_MAX_ERRORS]


def check_artifact(value, schema, present=True, name="?"):
    """El artefacto REAL de un paso contra su `output_schema` → lista de
    errores (vacía = contrato cumplido). Normaliza la forma de commit:
    valor-dato (lista/dict) se valida directo; un string que es RUTA de
    archivo se lee (así commitea el driver real); el texto se intenta parsear
    como JSON y, si no lo es, se valida como string plano."""
    if not present:
        return ["artefacto `%s` ausente del run — el paso no lo commiteó"
                % name]
    data = value
    if isinstance(value, str):
        text = value
        if _os.path.isfile(value):
            try:
                with open(value, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
            except OSError as e:
                return ["artefacto `%s` ilegible (%s): %s" % (name, value, e)]
        try:
            data = _json.loads(text)
        except ValueError:
            data = text                      # texto plano: válido si el
    errs = check_value(data, schema)         # schema pide string
    if len(errs) >= _MAX_ERRORS:
        errs = errs[:_MAX_ERRORS] + ["… (detalle cortado en %d errores)"
                                     % _MAX_ERRORS]
    return errs
