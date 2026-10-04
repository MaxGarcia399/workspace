#!/usr/bin/env python3
"""WORKSPACE · workflows — runner mínimo de pipelines (F1; stdlib puro, 3.9+).

El mapa congelado vive en `workflows/MAPA.md`. Cada pipeline es un SPEC
declarativo (`workflows/specs/<nombre>.json`) y este módulo lo ejecuta:

  lee el spec → corre los pasos EN ORDEN → por cada paso corre su `verify`
  (función Python determinista, registry en `workflows/steps/`) → persiste
  el estado tras CADA paso en `~/.claude/workspace/workflows/runs/<id>.json`
  → `resume <run-id>` retoma desde el último paso verde.

Invariantes (MAPA.md, no se rompen):
  1. Cada paso deja artefacto/estado → el run es RESUMIBLE.
  2. Verify DETERMINISTA por paso — código que lee evidencia, no claims.
  3. Spec CONGELADO: el run guarda una copia completa del spec; un run
     empezado en vN termina en vN aunque el archivo cambie después.
  4. IDEMPOTENCIA (v1.1): "resumible" solo es verdad si re-correr un paso
     EFECTIVO es no-op seguro. Los pasos det de la biblioteca que tocan el
     mundo (worktree.acquire, front.integrate) SON idempotentes (adoptan /
     no-op si su efecto ya existe). Un paso que NO pueda serlo se declara
     `"idempotent": false` en el spec: el runner entonces NO lo re-corre
     solo en resume (escala al socio) y rechaza dárselo a `on_fail: retry`.

Contrato de paso (entrada del spec):
  {"id", "kind": det|agent|human, "run" (det: nombre en steps.REGISTRY),
   "verify" (opcional, mismo registry), "on_fail": stop|retry (def. stop),
   "max_iter" (retry), "idempotent": true|false (def. true — ver invariante
   4), "timeout": segundos>0 (lo honran los pasos con subprocesos y el
   driver real; los det in-process documentan su límite), "when" (v1.2:
   predicado declarativo — falso ⇒ el paso queda `skipped` y el run sigue;
   gramática y seguridad en workflows/grammar.py; v1.4: un paso HUMAN cuyo
   `when` no se puede evaluar con CERTEZA — dato ausente bajo op
   comparativa — FALLA-CERRADO: pausa y consulta al socio, jamás skip
   silencioso), "output_schema" (v1.2:
   contrato de FORMA del artefacto — se valida ANTES del verify semántico;
   roto ⇒ fallo estructural PERMANENTE), "role"/"who",
   "artifact", "reads", "note", …}

  · det   — ejecuta `steps.resolve(run)(ctx, paso)` → {ok, detail, artifacts}.
  · agent — ORQUESTABLE vía driver inyectado (F2, contrato READ→EXECUTE→COMMIT
            en `workflows/driver.py`): el runner arma un `brief` con lo que el
            paso declara LEER (`reads:`), el driver EJECUTA y COMMITEA el
            `artifact:` declarado; el verify del spec corre después contra ese
            artefacto REAL (mismo camino que un det). Retry/max_iter/escalada
            aplican igual. SIN driver (default) o en --dry: STUB DECLARADO —
            queda {stub: true} y su verify se OMITE con detalle explícito —
            nada de verde fingido: el estado dice "stub".
  · human — pausa el run (status paused_human) y avisa por el bus si el paso
            declara "notify" (messages.send, best-effort).
            `workspace wf resume <run-id>` ES la aprobación del socio.

Decisiones de gate (v1.3 — arregla la conflación aprobar/rechazar): antes,
`resume` de un paso human SIEMPRE aprobaba — rechazar no existía como camino.
Ahora el socio puede REGISTRAR su decisión primero (`record_decision`: CLI
`workspace wf decide` o el POST del dev-panel) y `resume` la CONSUME:
  · approve → el paso se aprueba (con la anotación en el detalle) y sigue;
  · reject  → el run queda `rejected` (estado TERMINAL, con la anotación) —
              jamás sigue como si nada;
  · sin decisión registrada → compat total: resume = aprobar (el camino CLI
              histórico, intacto para runs viejos).
`record_decision` SOLO escribe datos al estado (decisions[step]); no avanza
el run ni ejecuta nada — avanzar sigue siendo trabajo de `resume`.

Presentación Lavish (v1.3, OPT-IN): un paso puede declarar `"present":
"lavish"` y el runner emite un HTML autocontenido (workflows/lavish.py,
look WORKSPACE) como artefacto del run: paso human en pausa → gate con botones
Aprobar/Rechazar (`gate-<paso>.html`); paso det/agent verde con artifact →
presentación legible (`present-<paso>.html`). Best-effort absoluto: el HTML
caído jamás toca el resultado del run. Sin `present:` nada cambia.

`on_fail: retry` reintenta hasta `max_iter` (cap DURO — los intentos
persisten entre resumes); agotado → escalada AUTOMÁTICA a paso human
(jamás loop infinito). TAXONOMÍA DE ERRORES (v1.1): un resultado puede
declarar `retriable: false` (error PERMANENTE — config/contrato: reintentar
no lo arregla) y el runner escala YA sin gastar max_iter; las excepciones se
clasifican (`HeadlessError` y errores de contrato = permanentes). Entre
reintentos TRANSITORIOS hay backoff exponencial con jitter (`backoff_delay`,
función pura testeable; el sleep es inyectable vía `_sleep`).
`--dry`: nada real se ejecuta — cada paso reporta qué haría (misma
convención que `_suite_green(dry)` de front.py).

Driver (v1.1): la IDENTIDAD del driver (nombre/backend/model — jamás el
callable) se persiste en `state["driver"]` cuando un run corre con driver
real. `resume` la REHIDRATA si no se re-inyecta uno — un run real jamás
degrada a stub en silencio: sin driver rehidratable los pasos agent FALLAN
con detalle (error permanente), y el runner se NIEGA a marcar DONE si un
run-con-driver terminó con pasos agent en stub.

Eventos: cada paso emite `wf_step` al rastro N10 (`events.emit`) — esa traza
es la evidencia que `steps/evidence.py` lee después.

Observabilidad (v1.5, P1-D): el socio puede VER cuánto tardó una corrida y
qué pasó, sin leer JSONs a mano:
  · `wf_run` al rastro N10 — al ARRANCAR (`phase: start`), al REANUDAR
    (`phase: resume`) y al CERRAR cada pasada (`phase: end`, con el estado
    en que quedó el run — done/failed/rejected/paused_human — su duración
    total y el resumen de conteos). Mismo best-effort que `wf_step`.
  · Duraciones que VIAJAN: cada paso persiste `ms` (tiempo de ejecución
    acumulado entre tentativas, reloj monotónico) en su estado Y en su
    evento `wf_step`; el run persiste `ms` total (pared, desde `created` —
    incluye pausas: eso ES lo que tardó la corrida para el socio).
  · `run_summary(state)` — función PURA: conteos por estado de paso
    (done/skipped/failed/waiting/pending/rejected), stubs, intentos totales
    y ms totales de ejecución. Se persiste en `state["summary"]` al cierre
    de cada pasada; las vistas/dev-panel lo consumen sin recalcular.

Falla-suave SOLO en lo lateral (eventos, bus). El runner en sí es estricto:
spec inválido o paso desconocido levantan ValueError/KeyError ANTES de correr
nada — un pipeline a medias validar no existe.
"""
import contextlib as _contextlib
import datetime as _dt
import difflib as _difflib
import json as _json
import os as _os
import random as _random
import re as _re
import time as _time
import uuid as _uuid

try:                         # lock de run.json (v1.4): POSIX
    import fcntl as _fcntl
except ImportError:          # pragma: no cover — Windows
    _fcntl = None
try:                         # fallback Windows
    import msvcrt as _msvcrt
except ImportError:
    _msvcrt = None

from workflows import driver as _driverlib
from workflows import grammar as _grammar

HERE = _os.path.dirname(_os.path.abspath(__file__))
ROOT = _os.path.dirname(HERE)
SPECS_DIR = _os.path.join(HERE, "specs")

STEP_KINDS = ("det", "agent", "human")
ON_FAIL = ("stop", "retry")

# estados de PASO (`skipped` v1.2: su `when:` fue falso — distinto de ok/stub)
PENDING, OK, FAIL, WAITING = "pending", "ok", "fail", "waiting_human"
SKIPPED = "skipped"
# estados de RUN (`rejected` v1.3: el socio RECHAZÓ un gate — terminal, como
# done; también es el estado del PASO rechazado)
RUNNING, DONE, FAILED, PAUSED = "running", "done", "failed", "paused_human"
REJECTED = "rejected"

# decisiones registrables sobre un gate human PAUSADO (v1.3)
DECISIONS = ("approve", "reject")
_NOTE_MAX = 2000            # cota de la anotación del socio (caracteres)

_ID_RE = _re.compile(r"[A-Za-z0-9._-]+\Z")
_MAX_ITER_CAP = 20          # cota absoluta: ningún spec puede pedir más
_TIMEOUT_CAP = 24 * 3600    # cota absoluta del `timeout:` por paso (24h)

# ── backoff entre reintentos (taxonomía v1.1) ──────────────────────────────
_BACKOFF_BASE = 0.5         # s del primer reintento
_BACKOFF_CAP = 30.0         # s máximos entre reintentos
_sleep = _time.sleep        # inyectable: los tests lo parchan (jamás duermen)
_mono = _time.monotonic     # reloj de duraciones por paso (v1.5) — inyectable:
                            # los tests lo parchan para ms deterministas


def backoff_delay(attempt, base=_BACKOFF_BASE, cap=_BACKOFF_CAP, rand=None):
    """Delay (s) ANTES del reintento que sigue a la tentativa `attempt`.
    Función PURA y testeable: exponencial `base·2^(attempt-1)` con cota `cap`
    y equal-jitter (mitad fija + mitad aleatoria — evita que N runs
    reintenten sincronizados). `rand` inyectable: callable → [0,1)."""
    r = rand if rand is not None else _random.random
    d = min(float(cap), float(base) * (2 ** (max(1, int(attempt)) - 1)))
    return d / 2.0 + r() * (d / 2.0)


def runs_dir():
    """Estado per-máquina de los runs (función, no constante: respeta el
    HOME parchado en tests herméticos — misma regla que _worktrees)."""
    return _os.path.join(_os.path.expanduser("~"), ".claude", "workspace",
                         "workflows", "runs")


def _now():
    return _dt.datetime.now().isoformat(timespec="seconds")


def _emit(payload, event="wf_step"):
    """Traza N10 del runner (`wf_step` por tentativa; `wf_run` por pasada,
    v1.5) — best-effort: el rastro caído jamás tumba el run."""
    try:
        import events
        events.emit(event, payload, emitter="workflows")
    except Exception:
        pass


def _iso_ms(a, b):
    """Milisegundos ENTEROS entre dos timestamps ISO del estado (a → b).
    None si falta alguno o no parsea — jamás levanta (observabilidad
    lateral: un timestamp raro no puede tumbar el run). Precisión: segundos
    (la que `_now()` persiste)."""
    try:
        d0 = _dt.datetime.fromisoformat(a)
        d1 = _dt.datetime.fromisoformat(b)
        return max(0, int((d1 - d0).total_seconds() * 1000))
    except Exception:
        return None


def run_summary(state):
    """Resumen consultable de UN run — función PURA (solo lee el dict, no
    toca disco; testeable con estados sintéticos). Devuelve:

      {steps, done, skipped, failed, waiting, pending, rejected,
       stub, attempts, ms}

    · done/skipped/failed/waiting/rejected = conteos por estado de paso
      (pending agrupa lo que aún no corrió o no terminó en otro estado).
    · stub     = pasos agent que quedaron en stub declarado (verde ≠ real).
    · attempts = tentativas TOTALES (reintentos incluidos).
    · ms       = suma de los `ms` de ejecución por paso (reloj monotónico;
      NO incluye pausas human ni backoff — el wall total del run vive en
      `state["ms"]`)."""
    c = {"steps": 0, "done": 0, "skipped": 0, "failed": 0, "waiting": 0,
         "pending": 0, "rejected": 0, "stub": 0, "attempts": 0, "ms": 0}
    for s in (state or {}).get("steps") or []:
        c["steps"] += 1
        stt = s.get("status")
        key = {OK: "done", SKIPPED: "skipped", FAIL: "failed",
               WAITING: "waiting", REJECTED: "rejected"}.get(stt, "pending")
        c[key] += 1
        if s.get("stub"):
            c["stub"] += 1
        c["attempts"] += int(s.get("attempts") or 0)
        c["ms"] += int(s.get("ms") or 0)
    return c


def _emit_run(state, phase):
    """Evento `wf_run` al rastro N10 (v1.5): una línea por transición de
    PASADA — start (arranque), resume (reanudación), end (la pasada quedó
    en done/failed/rejected/paused_human). Best-effort como todo el rastro."""
    payload = {"phase": phase, "run": state["run_id"],
               "workflow": state["workflow"], "status": state.get("status"),
               "dry": bool(state.get("dry"))}
    if phase == "end":
        payload["ms"] = state.get("ms")
        payload["summary"] = run_summary(state)
    _emit(payload, event="wf_run")


def _close_pass(state):
    """Cierre de UNA pasada del runner (v1.5): persiste la duración total
    del run (`state["ms"]`, pared desde `created` — incluye pausas: eso ES
    lo que tardó la corrida) y el resumen (`state["summary"]`), y emite el
    `wf_run` de fin. Se llama en TODO punto donde una pasada termina
    (done/failed/rejected/paused_human). Devuelve el estado.

    active_run: un cierre TERMINAL (done/failed/rejected) saca el run de la
    pila del activo; una pausa human NO — el board sigue mostrando lo que el
    socio tiene que atender."""
    state["ms"] = _iso_ms(state.get("created"), _now())
    state["summary"] = run_summary(state)
    _save_run(state)
    _emit_run(state, "end")
    if state.get("status") in (DONE, FAILED, REJECTED):
        _active_pop(state["run_id"])
    return state


# ── specs ──────────────────────────────────────────────────────────────────
def _step_produces(sp):
    """Claves de artefacto que el paso PUEDE producir, según su contrato
    DECLARADO (v1.4): `produces:` del spec gana; un det sin él hereda el
    contrato del registry (`steps.produces_of`); un agent sin él produce su
    `artifact:` declarado; human jamás produce. None = contrato OPACO (no
    se puede probar nada aguas abajo — la integridad se vuelve permisiva)."""
    if "produces" in sp:
        return list(sp["produces"])
    if sp.get("kind") == "human":
        return []
    if sp.get("kind") == "det":
        from workflows import steps as steplib
        got = steplib.produces_of(sp.get("run"))
        return list(got) if got is not None else None
    if sp.get("artifact"):
        return [sp["artifact"]]
    return None


def _check_artifact_refs(spec):
    """Integridad referencial del namespace de artefactos (v1.4, P0-A):
    cada `reads:` y cada hoja `when.artifact` debe tener un PRODUCTOR
    upstream (paso anterior cuyo contrato lo declara) o venir de fuera
    (`inputs:` del spec — p. ej. sembrado vía --param). Referencia colgante
    ⇒ ValueError AL CARGAR, no en runtime. Si algún paso upstream tiene
    contrato OPACO (sin `produces:` ni entrada en el registry) la prueba es
    imposible y la referencia se PERMITE (permisivo, documentado en MAPA).
    De paso: si el productor declara `output_schema`, el `path` de cada
    `when` sobre su artefacto se verifica contra ese contrato de forma."""
    name = spec["workflow"]
    disponibles = set(spec.get("inputs") or [])
    esquemas = {}                # clave de artefacto → output_schema productor
    opaco = False                # ¿hay upstream con contrato desconocido?
    for sp in spec["steps"]:
        sid = sp["id"]
        refs = [("reads", k, "") for k in (sp.get("reads") or [])]
        if sp.get("when") is not None:
            refs += [("when", art, path)
                     for art, path in _grammar.when_refs(sp["when"])]
        for origen, clave, path in refs:
            if clave in disponibles:
                if origen == "when" and path and clave in esquemas:
                    cabe = _grammar.path_in_schema(esquemas[clave], path)
                    if cabe is False:
                        raise ValueError(
                            "spec `%s`: paso `%s` con `when` sobre `%s.%s` — "
                            "el path NO cabe en el `output_schema` del "
                            "productor (clave fuera del contrato; decláralo "
                            "en `optional` del schema si es legítimo)"
                            % (name, sid, clave, path))
                continue
            if opaco:
                continue         # no se puede probar que cuelga — permitir
            pista = _difflib.get_close_matches(clave, sorted(disponibles), n=1)
            raise ValueError(
                "spec `%s`: paso `%s` referencia el artefacto `%s` (via %s) "
                "SIN productor upstream ni entrada en `inputs:` — referencia "
                "COLGANTE al cargar, no en runtime%s (disponibles hasta aquí: "
                "%s)" % (name, sid, clave, origen,
                         " (¿quisiste decir `%s`?)" % pista[0] if pista else "",
                         ", ".join(sorted(disponibles)) or "ninguno"))
        prod = _step_produces(sp)
        if prod is None:
            opaco = True
        else:
            disponibles.update(prod)
            if sp.get("artifact") and sp.get("output_schema") is not None:
                esquemas[sp["artifact"]] = sp["output_schema"]


def validate_spec(spec):
    """Valida la forma del spec. Estricto: ValueError con el QUÉ exacto —
    mejor reventar antes de correr que un pipeline a medias. Devuelve spec.

    v1.4 (P0-A): además de la FORMA, valida el CONTRATO — cada `run:` y
    `verify:` debe existir en el registry de pasos (typo = error al cargar,
    con sugerencia), y cada `reads:`/`when.artifact` debe tener productor
    upstream o venir de `inputs:` (_check_artifact_refs)."""
    if not isinstance(spec, dict):
        raise ValueError("spec no es un objeto JSON")
    name = spec.get("workflow")
    if not name or not isinstance(name, str):
        raise ValueError("spec sin campo `workflow`")
    if not isinstance(spec.get("version"), int) or spec["version"] < 1:
        raise ValueError("spec `%s`: `version` debe ser entero ≥1" % name)
    steps = spec.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("spec `%s`: `steps` vacío o ausente" % name)
    inputs = spec.get("inputs")
    if inputs is not None and (
            not isinstance(inputs, list)
            or any(not isinstance(k, str) or not k for k in inputs)):
        raise ValueError("spec `%s`: `inputs` inválido — lista de claves de "
                         "artefacto que llegan de FUERA del pipeline "
                         "(p. ej. sembradas vía --param)" % name)
    trigs = spec.get("triggers")
    if trigs is not None and (
            not isinstance(trigs, list)
            or any(not isinstance(t, str) or not t.strip() for t in trigs)):
        raise ValueError("spec `%s`: `triggers` inválido — lista de palabras/"
                         "frases clave (strings no vacíos) que `workspace wf "
                         "match` empata contra el texto de una tarea" % name)
    from workflows import steps as _steplib   # lazy: import barato, sin ciclos
    conocidos = _steplib.known()
    seen = set()
    for i, sp in enumerate(steps):
        if not isinstance(sp, dict) or not sp.get("id"):
            raise ValueError("spec `%s`: paso #%d sin `id`" % (name, i))
        sid = sp["id"]
        if sid in seen:
            raise ValueError("spec `%s`: id de paso duplicado `%s`" % (name, sid))
        seen.add(sid)
        kind = sp.get("kind")
        if kind not in STEP_KINDS:
            raise ValueError("spec `%s`: paso `%s` con kind inválido %r "
                             "(det|agent|human)" % (name, sid, kind))
        if kind == "det" and not sp.get("run"):
            raise ValueError("spec `%s`: paso det `%s` sin `run`" % (name, sid))
        for campo in ("run", "verify"):
            ref = sp.get(campo)
            if ref is None:
                continue
            if not isinstance(ref, str) or not ref:
                raise ValueError("spec `%s`: paso `%s` con `%s` inválido %r "
                                 "(string no vacío)" % (name, sid, campo, ref))
            if ref not in conocidos:
                # P0-A: typo en run/verify = error de validación CLARO al
                # cargar (con sugerencia), jamás sorpresa en runtime.
                pista = _difflib.get_close_matches(ref, conocidos, n=1)
                raise ValueError(
                    "spec `%s`: paso `%s` con `%s` DESCONOCIDO %r%s — no "
                    "está en el registry de pasos (registrados: %s)"
                    % (name, sid, campo, ref,
                       " (¿quisiste decir `%s`?)" % pista[0] if pista else "",
                       ", ".join(conocidos)))
        prod = sp.get("produces")
        if prod is not None:
            if (not isinstance(prod, list)
                    or any(not isinstance(p, str) or not p for p in prod)):
                raise ValueError("spec `%s`: paso `%s` con `produces` "
                                 "inválido — lista de claves de artefacto "
                                 "(strings no vacíos)" % (name, sid))
            if len(set(prod)) != len(prod):
                raise ValueError("spec `%s`: paso `%s` con claves duplicadas "
                                 "en `produces`" % (name, sid))
            if kind == "human" and prod:
                raise ValueError("spec `%s`: paso `%s` (human) no produce "
                                 "artefactos — `produces` va vacío o ausente"
                                 % (name, sid))
        on_fail = sp.get("on_fail", "stop")
        if on_fail not in ON_FAIL:
            raise ValueError("spec `%s`: paso `%s` con on_fail inválido %r"
                             % (name, sid, on_fail))
        if on_fail == "retry":
            mi = sp.get("max_iter")
            if not isinstance(mi, int) or not (1 <= mi <= _MAX_ITER_CAP):
                raise ValueError("spec `%s`: paso `%s` con on_fail=retry "
                                 "necesita max_iter entero 1..%d"
                                 % (name, sid, _MAX_ITER_CAP))
        idem = sp.get("idempotent")
        if idem is not None and not isinstance(idem, bool):
            raise ValueError("spec `%s`: paso `%s` con `idempotent` inválido "
                             "%r (true|false)" % (name, sid, idem))
        if idem is False and on_fail == "retry":
            raise ValueError("spec `%s`: paso `%s` declara idempotent=false "
                             "Y on_fail=retry — re-correr un paso efectivo "
                             "NO idempotente corrompe (invariante 4); usa "
                             "on_fail=stop" % (name, sid))
        to = sp.get("timeout")
        if to is not None and (not isinstance(to, (int, float))
                               or isinstance(to, bool)
                               or not (0 < to <= _TIMEOUT_CAP)):
            raise ValueError("spec `%s`: paso `%s` con `timeout` inválido %r "
                             "(segundos, 0 < t ≤ %d)"
                             % (name, sid, to, _TIMEOUT_CAP))
        reads = sp.get("reads")
        if reads is not None and (
                not isinstance(reads, list)
                or any(not isinstance(r, str) or not r for r in reads)):
            raise ValueError("spec `%s`: paso `%s` con `reads` inválido — "
                             "debe ser lista de claves (strings no vacíos)"
                             % (name, sid))
        wh = sp.get("when")
        if wh is not None:
            try:
                _grammar.validate_when(wh)
            except ValueError as e:
                raise ValueError("spec `%s`: paso `%s` con `when` inválido — "
                                 "%s" % (name, sid, e))
        pres = sp.get("present")
        if pres is not None and pres != "lavish":
            raise ValueError("spec `%s`: paso `%s` con `present` inválido %r "
                             "— el único modo soportado es \"lavish\" "
                             "(workflows/lavish.py)" % (name, sid, pres))
        osch = sp.get("output_schema")
        if osch is not None:
            if kind == "human":
                raise ValueError("spec `%s`: paso `%s` (human) no puede "
                                 "declarar `output_schema` — no produce "
                                 "artefactos" % (name, sid))
            if not sp.get("artifact"):
                raise ValueError("spec `%s`: paso `%s` declara "
                                 "`output_schema` sin `artifact` — el "
                                 "contrato necesita saber QUÉ artefacto "
                                 "valida" % (name, sid))
            try:
                _grammar.validate_output_schema(osch)
            except ValueError as e:
                raise ValueError("spec `%s`: paso `%s` con `output_schema` "
                                 "inválido — %s" % (name, sid, e))
    _check_artifact_refs(spec)               # P0-A: integridad referencial
    return spec


def load_spec(name):
    """Lee y valida `workflows/specs/<name>.json`. Nombre saneado (sin rutas)."""
    base = _os.path.basename(str(name or ""))
    if base.endswith(".json"):
        base = base[:-5]
    if not base or not _ID_RE.match(base):
        raise ValueError("nombre de spec inválido: %r" % (name,))
    path = _os.path.join(SPECS_DIR, base + ".json")
    if not _os.path.isfile(path):
        raise FileNotFoundError("no existe el spec `%s` (%s)" % (base, path))
    with open(path, encoding="utf-8") as fh:
        return validate_spec(_json.load(fh))


def list_specs():
    """[{name, version, steps, kinds}] de los specs disponibles (ordenados).
    Un spec ilegible se reporta con `error`, no tumba la lista."""
    out = []
    try:
        names = sorted(f[:-5] for f in _os.listdir(SPECS_DIR)
                       if f.endswith(".json"))
    except OSError:
        return out
    for n in names:
        try:
            spec = load_spec(n)
            kinds = {}
            for sp in spec["steps"]:
                kinds[sp["kind"]] = kinds.get(sp["kind"], 0) + 1
            out.append({"name": n, "version": spec["version"],
                        "steps": len(spec["steps"]), "kinds": kinds})
        except Exception as e:
            out.append({"name": n, "error": "%s: %s" % (type(e).__name__, e)})
    return out


# ── `workspace wf match` — candidatos DETERMINISTAS por texto de tarea ────────
# La base del propose-first: dado el texto de una tarea, ¿hay workflow para
# esto? El matching es código puro (cero LLM, mismo texto → misma lista
# SIEMPRE). La PROPUESTA («hay un workflow, ¿lo corro?») la hace el agente en
# el chat — aquí solo se calcula el candidato, jamás se arranca nada.
def _match_norm(s):
    """minúsculas + sin acentos (NFD) — 'código' empata 'codigo' y viceversa."""
    import unicodedata
    s = unicodedata.normalize("NFD", str(s or "").lower())
    return "".join(c for c in s if not unicodedata.combining(c))


def _match_stem(word):
    """Raíz de UNA palabra para el match por prefijo: un infinitivo español
    (-ar/-er/-ir, ≥5 chars) pierde la terminación — 'revisar' empata
    'revisa/revisión', 'construir' empata 'construye/construcción'. Las no
    verbales quedan tal cual (el prefijo ya cubre plurales: 'bug' → 'bugs')."""
    if len(word) >= 5 and word[-2:] in ("ar", "er", "ir"):
        return word[:-2]
    return word


def _match_hit(term, texto):
    """¿El término aparece en el texto? (ambos YA normalizados). Match por
    PREFIJO en frontera de palabra: término multi-palabra = frase literal;
    una palabra = su raíz (_match_stem) al inicio de una palabra del texto.
    Determinista por construcción — regex fija, sin estado."""
    term = term.strip()
    if not term:
        return False
    pat = _re.escape(term if " " in term else _match_stem(term))
    return _re.search(r"(?<![a-z0-9])" + pat, texto) is not None


def match_score(spec, text):
    """Relevancia de UN spec para un texto de tarea — función PURA. Devuelve
    {name, score, hits, via} o None si no empata nada. `triggers:` del spec
    manda (score = nº de triggers que empatan, hits en el orden del spec);
    sin triggers cae a los tokens del nombre + palabras de la nota (`via:
    nombre/nota`) — mejor un fallback tosco que un spec inencontrable."""
    texto = _match_norm(text)
    if not texto.strip():
        return None
    trigs = [t for t in (spec.get("triggers") or []) if str(t).strip()]
    if trigs:
        terms, via = trigs, "triggers"
    else:
        name = str(spec.get("workflow") or "")
        terms = [name] + [t for t in _re.split(r"[-_.]", name) if len(t) >= 3]
        terms += sorted(set(
            _re.findall(r"[a-z0-9]{4,}", _match_norm(spec.get("note")))))
        via = "nombre/nota"
    hits = []
    for t in terms:
        if t not in hits and _match_hit(_match_norm(t), texto):
            hits.append(t)
    if not hits:
        return None
    return {"name": spec.get("workflow"), "score": len(hits),
            "hits": hits, "via": via}


def match_specs(text):
    """Workflows CANDIDATOS para un texto de tarea, ordenados por relevancia
    (score desc, nombre asc — orden TOTAL: el resultado es reproducible).
    Lista vacía = ninguno. Falla-suave: un spec ilegible se ignora (como en
    list_specs) — un JSON roto jamás tumba el matcher."""
    out = []
    try:
        names = sorted(f[:-5] for f in _os.listdir(SPECS_DIR)
                       if f.endswith(".json"))
    except OSError:
        return out
    for n in names:
        try:
            cand = match_score(load_spec(n), text)
        except Exception:
            continue
        if cand:
            out.append(cand)
    out.sort(key=lambda c: (-c["score"], c["name"]))
    return out


# ── `workspace wf new` — andamiar un spec GUIADO (semilla del wf-que-crea-wf) ─
def skeleton_spec(name):
    """El esqueleto GUIADO que genera `workspace wf new <nombre>`: un spec
    VÁLIDO desde que nace (pasa validate_spec tal cual), con un paso de cada
    kind (det · agent · human) y `note:` en cada uno explicando los campos
    (run/verify/produces/when/output_schema/on_fail) en lenguaje de socio,
    apuntando SOLO a pasos reales del registry (steps.known()). El socio
    edita desde algo que funciona — nunca desde una página en blanco."""
    from workflows import steps as _steplib   # lazy, como validate_spec
    return {
        "workflow": name,
        "version": 1,
        "note": ("Esqueleto generado por `workspace wf new` — edítalo a tu "
                 "medida: cambia ids, agrega o borra pasos, y borra las "
                 "`note:` cuando ya no las necesites (son comentarios, el "
                 "runner las ignora). Después de CADA edición: "
                 "`workspace wf run %s --dry` valida el spec y muestra qué "
                 "haría SIN ejecutar nada — si algo falta, el error te dice "
                 "exactamente qué." % name),
        "guia": {
            "que_es": ("Un workflow = pasos que corren EN ORDEN, uno tras "
                       "otro. Tres tipos (`kind`): det = código determinista "
                       "del registry (abajo) · agent = trabajo que se le "
                       "encarga a un agente · human = el workflow PAUSA y te "
                       "pregunta a TI (gate)."),
            "campos": {
                "id": "nombre único del paso (letras, números, guiones)",
                "run": ("solo pasos det: QUÉ función corre — una de "
                        "`pasos_registrados` (abajo), tal cual escrita"),
                "verify": ("opcional: función del registry que COMPRUEBA con "
                           "evidencia que el paso hizo su trabajo — si el "
                           "verify no pasa, el paso NO cuenta como ok"),
                "produces": ("opcional: claves de resultado (artefactos) que "
                             "este paso deja para los siguientes — otro paso "
                             "las puede leer o usar en su `when`"),
                "when": ("opcional: condición sobre un artefacto anterior; "
                         "si no se cumple, el paso se SALTA (ops: exists · "
                         "non_empty · eq · gt · …)"),
                "output_schema": ("opcional (pasos con `artifact`): la FORMA "
                                  "exacta que debe tener el resultado — si "
                                  "no la cumple, el paso falla ANTES de "
                                  "contaminar a los demás"),
                "on_fail": ("qué pasa si el paso falla: `stop` (default, el "
                            "run se detiene) o `retry` (reintenta hasta "
                            "`max_iter` veces)"),
            },
            "pasos_registrados": _steplib.known(),
            "siguiente": ("1) edita este archivo · 2) `workspace wf run %s "
                          "--dry` (ensayo) · 3) `workspace wf run %s` (real) · "
                          "4) `workspace wf board` (verlo en vivo)" % (name, name)),
        },
        "steps": [
            {
                "id": "verificar-base",
                "kind": "det",
                "run": "suite.green",
                "on_fail": "stop",
                "note": ("Paso DETERMINISTA (kind: det): corre código real "
                         "del registry, sin agentes. `run: suite.green` = "
                         "correr la suite de tests del repo y exigirla verde "
                         "(con --dry solo reporta qué haría). Cámbialo por "
                         "cualquier paso de `guia.pasos_registrados`."),
            },
            {
                "id": "trabajar",
                "kind": "agent",
                "role": "implementador",
                "artifact": "resultado",
                "produces": ["resultado"],
                "output_schema": {
                    "type": "object",
                    "required": {"resumen": {"type": "string"}},
                },
                "verify": "evidence.artifact_exists",
                "on_fail": "stop",
                "contract": {
                    "objetivo": "escribe aquí QUÉ debe lograr el agente",
                    "formato": "qué debe entregar y en qué forma",
                    "tools": "qué puede usar (repo, suite, …)",
                    "limites": "qué NO puede hacer (p. ej. no push, no main)",
                },
                "note": ("Paso de AGENTE (kind: agent): se lo encarga a un "
                         "agente según el `contract` (escríbelo en tus "
                         "palabras). Sin `--driver real` queda como STUB "
                         "declarado (el estado lo dice, nada de verde "
                         "fingido). `produces: [resultado]` = deja el "
                         "artefacto `resultado`; `output_schema` = ese "
                         "artefacto DEBE ser un objeto con `resumen` (texto); "
                         "`verify: evidence.artifact_exists` = comprobar que "
                         "el artefacto existe de verdad, no creerle."),
            },
            {
                "id": "aprobar",
                "kind": "human",
                "who": "el socio que corre el workflow",
                "when": {"artifact": "resultado", "op": "non_empty"},
                "note": ("Paso HUMANO (kind: human): el workflow PAUSA aquí "
                         "y espera TU decisión — `workspace wf gate <run-id> "
                         "--open` abre el gate visual (Aprobar/Rechazar), o "
                         "`workspace wf decide <run-id> aprobar approve|reject`"
                         "; luego `workspace wf resume <run-id>` la aplica. "
                         "`when:` = solo pausa si el artefacto `resultado` "
                         "llegó no-vacío; si no, el paso se salta."),
            },
        ],
    }


def new_spec(name):
    """Crea `workflows/specs/<name>.json` desde el esqueleto guiado. Devuelve
    la ruta. Estricto: nombre saneado (mismas reglas que load_spec), JAMÁS
    sobrescribe un spec existente (FileExistsError), y el esqueleto se valida
    con validate_spec ANTES de escribir — lo que nace, nace válido."""
    base = _os.path.basename(str(name or ""))
    if base.endswith(".json"):
        base = base[:-5]
    if not base or not base.strip(".") or not _ID_RE.match(base):
        raise ValueError("nombre de workflow inválido: %r — usa letras, "
                         "números, guiones o puntos (p. ej. mi-flujo)"
                         % (name,))
    path = _os.path.join(SPECS_DIR, base + ".json")
    if _os.path.exists(path):
        raise FileExistsError("ya existe el spec `%s` (%s) — no lo "
                              "sobrescribo; edítalo directo o elige otro "
                              "nombre" % (base, path))
    spec = validate_spec(skeleton_spec(base))
    _os.makedirs(SPECS_DIR, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        _json.dump(spec, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    return path


# ── persistencia de runs ───────────────────────────────────────────────────
def run_path(run_id):
    if not run_id or not _ID_RE.match(str(run_id)):
        raise ValueError("run-id inválido: %r" % (run_id,))
    return _os.path.join(runs_dir(), str(run_id) + ".json")


def _save_run(state):
    """Escritura atómica (tmp + replace) tras CADA paso — el resume depende
    de que el estado en disco jamás quede a medias."""
    path = run_path(state["run_id"])
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp%d" % (path, _os.getpid())
    state["updated"] = _now()
    with open(tmp, "w", encoding="utf-8") as fh:
        _json.dump(state, fh, indent=2, ensure_ascii=False)
    _os.replace(tmp, path)
    return path


def load_run(run_id):
    with open(run_path(run_id), encoding="utf-8") as fh:
        state = _json.load(fh)
    if not isinstance(state, dict) or "spec" not in state:
        raise ValueError("run `%s` corrupto (sin spec congelado)" % run_id)
    return state


def list_runs(limit=20):
    """Últimos runs (estado completo), más reciente primero. Falla-suave → []."""
    out = []
    try:
        d = runs_dir()
        files = [f for f in _os.listdir(d) if f.endswith(".json")]
        files.sort(key=lambda f: _os.path.getmtime(_os.path.join(d, f)),
                   reverse=True)
        for f in files[:max(0, int(limit))]:
            try:
                with open(_os.path.join(d, f), encoding="utf-8") as fh:
                    st = _json.load(fh)
                if isinstance(st, dict) and st.get("run_id"):
                    out.append(st)
            except Exception:
                continue
    except Exception:
        pass
    return out


# ── active_run — pila del run ACTIVO (lectura barata para el board/split) ──
# `~/.claude/workspace/workflows/active_run`: texto plano, un run-id por línea;
# el ACTIVO es la ÚLTIMA (tope de pila — con varios runs a la vez gana el más
# reciente, y al cerrar éste el anterior vuelve a ser el activo). Lo escribe
# start() (push), lo re-escribe resume() (un run retomado vuelve a ser el
# activo) y lo limpia el cierre de pasada cuando el run queda TERMINAL
# (done/failed/rejected); una pausa human NO lo saca — el run sigue siendo
# lo que el socio está mirando. Observabilidad LATERAL best-effort absoluto:
# un fallo aquí jamás toca el resultado del run.
def active_run_path():
    """Ruta del archivo de pila (función, no constante: respeta el HOME
    parchado en tests herméticos — misma regla que runs_dir)."""
    return _os.path.join(_os.path.dirname(runs_dir()), "active_run")


def _active_stack():
    """La pila completa (lista de run-ids, tope al final). Falla-suave → []."""
    try:
        with open(active_run_path(), encoding="utf-8") as fh:
            return [ln.strip() for ln in fh if ln.strip()]
    except OSError:
        return []


def _active_write(stack):
    """Persiste la pila (tmp + replace, como _save_run). Vacía → archivo
    FUERA (sin active_run el board vuelve a su prioridad global de hoy)."""
    path = active_run_path()
    if not stack:
        with _contextlib.suppress(OSError):
            _os.remove(path)
        return
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    tmp = "%s.tmp%d" % (path, _os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write("\n".join(stack) + "\n")
    _os.replace(tmp, path)


def active_run():
    """Run-id ACTIVO (tope de la pila) o None. Lectura BARATA y falla-suave —
    el board/split la hace por tick sin cargar ningún run."""
    stack = _active_stack()
    return stack[-1] if stack else None


def _active_push(run_id):
    """`run_id` pasa a ser el activo (tope; si ya estaba, sube). Best-effort."""
    try:
        _active_write([r for r in _active_stack() if r != run_id]
                      + [str(run_id)])
    except Exception:
        pass


def _active_pop(run_id):
    """Saca `run_id` de la pila (el run cerró) — el anterior vuelve a ser el
    activo. Idempotente y best-effort: popear lo que no está es no-op."""
    try:
        _active_write([r for r in _active_stack() if r != run_id])
    except Exception:
        pass


# ── lock del estado del run (v1.4, P1-C) ───────────────────────────────────
@_contextlib.contextmanager
def _run_lock(run_id):
    """Lock EXCLUSIVO inter-proceso alrededor del read-modify-write del
    estado de UN run (`<run>.json.lock` junto al estado; `list_runs` lo
    ignora — solo lista `.json`).

    Por qué: el POST del dev-panel (`record_decision`) y el CLI/loop
    nocturno (`resume`) mutan el MISMO archivo; sin lock, last-writer-wins
    puede PERDER la decisión del socio o retomar sobre estado stale. Con el
    lock, cada escritor re-lee el estado FRESCO antes de escribir.

    POSIX: `fcntl.flock` (bloqueante). Windows: `msvcrt.locking` (LK_LOCK,
    reintenta ~10s y revienta — mejor un error ruidoso que una decisión
    perdida en silencio). El lock protege el read-modify-write, no la
    ejecución de pasos: mientras un run está `running`, su único escritor
    legítimo es el proceso que lo corre (record_decision rechaza runs no
    pausados tras re-leer bajo el lock)."""
    path = run_path(run_id) + ".lock"        # run_path ya sanea el run-id
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    fh = open(path, "a+")
    try:
        if _fcntl is not None:
            _fcntl.flock(fh.fileno(), _fcntl.LOCK_EX)
        elif _msvcrt is not None:            # pragma: no cover — Windows
            fh.seek(0)
            _msvcrt.locking(fh.fileno(), _msvcrt.LK_LOCK, 1)
        yield
    finally:
        try:
            if _fcntl is not None:
                _fcntl.flock(fh.fileno(), _fcntl.LOCK_UN)
            elif _msvcrt is not None:        # pragma: no cover — Windows
                fh.seek(0)
                _msvcrt.locking(fh.fileno(), _msvcrt.LK_UNLCK, 1)
        except Exception:
            pass
        fh.close()


# ── decisiones de gate (v1.3) ──────────────────────────────────────────────
def record_decision(run_id, step_id, decision, note=""):
    """Registra la DECISIÓN del socio (approve|reject + anotación) sobre un
    paso que espera humano en un run PAUSADO. SOLO escribe datos al estado
    (`decisions[step] = {decision, note, ts}`) — jamás avanza el run ni
    ejecuta nada del payload: consumirla es trabajo de `resume`.

    Estricto por diseño (esta función es la única puerta de la mutación web
    del dev-panel): run debe existir y estar `paused_human`; el paso debe
    existir y estar `waiting_human`; decision ∈ {approve, reject}; la nota es
    texto plano acotado (se guarda como DATO, tal cual). Re-registrar sobre
    el mismo paso mientras siga en pausa es idempotente/última-gana (el socio
    puede cambiar de opinión ANTES del resume). Devuelve el registro."""
    decision = str(decision or "").strip().lower()
    if decision not in DECISIONS:
        raise ValueError("decisión inválida: %r (approve|reject)" % (decision,))
    if note is None:
        note = ""
    if not isinstance(note, str):
        raise ValueError("nota inválida: debe ser texto plano")
    note = note.strip()
    if len(note) > _NOTE_MAX:
        raise ValueError("nota demasiado larga (%d chars; máx %d)"
                         % (len(note), _NOTE_MAX))
    if not isinstance(step_id, str) or not _ID_RE.match(step_id or ""):
        raise ValueError("id de paso inválido: %r" % (step_id,))
    with _run_lock(run_id):                  # v1.4: read-modify-write ATÓMICO
        state = load_run(run_id)             # run_path ya sanea el run-id
        if state.get("status") != PAUSED:
            raise ValueError("el run `%s` no está en pausa (status: %s) — "
                             "solo un gate PAUSADO acepta decisión"
                             % (state.get("run_id"), state.get("status")))
        st = next((s for s in state.get("steps") or []
                   if s.get("id") == step_id), None)
        if st is None:
            raise ValueError("el run `%s` no tiene un paso `%s`"
                             % (state.get("run_id"), step_id))
        if st.get("status") != WAITING:
            raise ValueError("el paso `%s` no espera decisión (status: %s)"
                             % (step_id, st.get("status")))
        rec = {"decision": decision, "note": note, "ts": _now()}
        state.setdefault("decisions", {})[step_id] = rec
        _save_run(state)
    return rec


# ── ciclo de vida ──────────────────────────────────────────────────────────
def start(spec, dry=False, params=None, driver=None):
    """Arranca un run: congela el spec DENTRO del estado y avanza hasta
    terminar, fallar o pausar en un paso human. Devuelve el estado.

    `driver`: callable que orquesta los pasos agent (contrato en
    `workflows/driver.py`). None → default del proceso (`driver.set_default`)
    o, si tampoco hay, stub honesto (comportamiento v1 intacto)."""
    spec = load_spec(spec) if isinstance(spec, str) else validate_spec(spec)
    frozen = _json.loads(_json.dumps(spec))      # copia profunda = congelado
    ts = _dt.datetime.now().strftime("%Y%m%dT%H%M%S")
    run_id = "%s-%s-%s" % (frozen["workflow"], ts, _uuid.uuid4().hex[:6])
    state = {
        "run_id": run_id,
        "workflow": frozen["workflow"],
        "version": frozen["version"],
        "dry": bool(dry),
        "params": dict(params or {}),
        "spec": frozen,
        "status": RUNNING,
        "created": _now(),
        "updated": _now(),
        "current": 0,
        "artifacts": {},
        "steps": [{"id": sp["id"], "kind": sp["kind"], "status": PENDING,
                   "attempts": 0} for sp in frozen["steps"]],
    }
    _save_run(state)
    _active_push(run_id)                     # el run que ARRANCA es el activo
    _emit_run(state, "start")                # v1.5: la corrida arrancó (N10)
    return _advance(state, driver=driver)


def resume(run_id, driver=None):
    """Retoma un run desde el primer paso NO verde, usando el spec CONGELADO
    del propio run (jamás el archivo — un run vN termina en vN).

    Si el run está pausado en un paso human (o en una escalada por max_iter
    agotado / error permanente), `resume` CONSUME la decisión registrada
    (v1.3, `record_decision`): reject → el run queda `rejected` (terminal,
    con la anotación — jamás sigue como si nada); approve → el paso se
    aprueba con la anotación y el pipeline sigue. SIN decisión registrada,
    `resume` ES la aprobación del socio (compat: el camino CLI histórico,
    intacto). Un paso fallido se re-corre — SALVO
    que declare `idempotent: false` (invariante 4): re-correr un paso
    efectivo no idempotente corrompe, así que se escala al socio (el
    SIGUIENTE resume, ya con el mundo arreglado a mano, es la aprobación).

    Driver (v1.1): el callable no se persiste, pero su IDENTIDAD sí
    (state["driver"]). Sin `driver` re-inyectado (ni default del proceso) se
    REHIDRATA desde esa identidad — un run real jamás degrada a stub en
    silencio. Driver no rehidratable (callable externo) y sin re-inyección →
    los pasos agent restantes fallan con detalle honesto."""
    with _run_lock(run_id):                  # v1.4 (P1-C): consumir la
        state = load_run(run_id)             # decisión y arrancar es un
        if state["status"] in (DONE, REJECTED):  # read-modify-write atómico
            return state                     # terminales: nada que retomar
        _emit_run(state, "resume")           # v1.5: reanudación trazada (N10)
        spec_by_id = {sp["id"]: sp for sp in state["spec"]["steps"]}
        for st in state["steps"]:
            if st["status"] == WAITING:
                dec = (state.get("decisions") or {}).get(st["id"]) or {}
                note = (dec.get("note") or "").strip()
                if dec.get("decision") == "reject":
                    # v1.3: RECHAZO registrado — el run NO sigue como si
                    # nada. Terminal (como done): la decisión del socio
                    # queda honrada y auditada; retomar = run nuevo.
                    st["status"] = REJECTED
                    st["detail"] = ("RECHAZADO por el socio (%s)%s"
                                    % (dec.get("ts", "?"),
                                       " · nota: " + note if note else ""))
                    state["status"] = REJECTED
                    return _close_pass(state)   # v1.5: terminal → wf_run end
                st["status"] = OK
                st["approved"] = _now()
                via = ("decisión registrada"
                       if dec.get("decision") == "approve" else "resume")
                st["detail"] = ((st.get("detail") or "") +
                                " · aprobado por el socio vía " + via +
                                (" · nota: " + note if note else ""))
                break
            if st["status"] == FAIL:
                sp = spec_by_id.get(st["id"], {})
                if sp.get("idempotent") is False:
                    # invariante 4: NO re-correr solo un paso efectivo no
                    # idempotente — escalar; el próximo resume = aprobar.
                    st["status"] = WAITING
                    st["escalated"] = True
                    st["detail"] = ("paso `%s` declarado NO idempotente — no "
                                    "se re-corre solo (re-correrlo "
                                    "corrompería su efecto). Revisa/arregla "
                                    "a mano y `workspace wf resume %s` de "
                                    "nuevo = aprobar · último fallo: %s"
                                    % (st["id"], state["run_id"],
                                       st.get("detail", "")))
                    state["status"] = PAUSED
                    _maybe_lavish(state, sp, st, gate=True)
                    _close_pass(state)      # v1.5: pausa = fin de pasada
                    _notify_human(state, sp)
                    return state
                st["status"] = PENDING      # re-correr (attempts intactos)
                break
            if st["status"] not in (OK, SKIPPED):
                break                        # skipped es terminal, como ok:
                                             # su when NO se re-evalúa
        state["status"] = RUNNING
        _save_run(state)
        _active_push(state["run_id"])        # el run retomado vuelve a activo
    if driver is None and _driverlib.get_default() is None:
        driver = _driverlib.rehydrate(state.get("driver"))
    return _advance(state, driver=driver)


def _norm(res):
    """Resultado de un paso/verify → {ok, detail, artifacts, retriable}
    saneado. `retriable` (v1.1): False = error PERMANENTE (config/contrato —
    reintentar no lo arregla); ausente = True (transitorio, el default
    histórico). Un resultado que ni siquiera es dict = bug de contrato del
    paso → permanente."""
    if not isinstance(res, dict):
        return {"ok": False, "detail": "resultado inválido del paso: %r"
                % (res,), "artifacts": {}, "retriable": False}
    arts = res.get("artifacts")
    return {"ok": bool(res.get("ok")),
            "detail": str(res.get("detail", "")),
            "artifacts": arts if isinstance(arts, dict) else {},
            "retriable": bool(res.get("retriable", True))}


def _classify_exc(e):
    """Excepción de un paso/driver → ¿es transitoria (True) o permanente
    (False)? Permanentes: los errores del contrato headless (config de
    backend/seguridad — `headless.py` ya los distingue; el runner los
    RESPETA en vez de tirarlos) y los errores de programación/contrato
    (ValueError/TypeError/KeyError/NotImplementedError). Todo lo demás
    (OSError, timeouts, subprocess…) se trata como transitorio."""
    try:
        import headless as _hl
        if isinstance(e, _hl.HeadlessError):
            return False
    except Exception:
        pass
    return not isinstance(e, (ValueError, TypeError, KeyError,
                              NotImplementedError))


def _agent_brief(state, ctx, sp, st):
    """READ del contrato read-execute-commit: arma el brief CERRADO que el
    driver recibe — solo lo que el paso declara leer (`reads:`), el artefacto
    que debe commitear (`artifact:`) y el contrato de 4 partes del spec.
    El driver no ve el estado del run: ve su brief."""
    reads = {k: state["artifacts"].get(k) for k in (sp.get("reads") or [])}
    workdir = _os.path.join(runs_dir(), state["run_id"] + ".artifacts")
    _os.makedirs(workdir, exist_ok=True)
    return {"run_id": state["run_id"], "workflow": state["workflow"],
            "step": sp["id"], "role": sp.get("role"),
            "contract": sp.get("contract"), "reads": reads,
            "artifact": sp.get("artifact"), "workdir": workdir,
            "params": dict(ctx.get("params") or {}), "repo": ctx.get("repo"),
            "attempt": st["attempts"], "dry": ctx["dry"],
            "timeout": sp.get("timeout")}    # el driver real lo honra (v1.1)


def _settle(state, ctx, sp, st, res):
    """COMMIT + verify de un paso que EJECUTÓ de verdad (det, o agent con
    driver): registra detalle/artefactos en el run, valida el CONTRATO DE
    FORMA (`output_schema`, v1.2) sobre el artefacto real y LUEGO corre el
    `verify:` del spec contra esa evidencia. El resultado del paso NO
    alcanza solo: verde = res.ok Y schema.ok Y verify.ok."""
    from workflows import steps as steplib
    st["detail"] = res["detail"]
    if not res.get("retriable", True):
        st["retriable"] = False              # permanente: _advance no reintenta
    if res["artifacts"]:
        st["artifacts"] = res["artifacts"]
        state["artifacts"].update(res["artifacts"])
    sok = True
    schema = sp.get("output_schema")
    if schema is not None and res["ok"] and not ctx["dry"]:
        # v1.2: contrato de FORMA — verificable por construcción, ANTES del
        # verify semántico. "El agente dijo que lo hizo" no basta: el
        # artefacto real debe TENER la forma que el spec declara.
        aname = sp.get("artifact")
        errs = _grammar.check_artifact(state["artifacts"].get(aname), schema,
                                       present=aname in state["artifacts"],
                                       name=aname)
        if errs:
            sok = False
            st["retriable"] = False          # contrato roto = PERMANENTE:
            st["output_schema"] = {          # reintentar en loop no lo arregla
                "ok": False, "detail": "; ".join(errs)}
            st["detail"] = ("CONTRATO DE SALIDA ROTO (output_schema de `%s`): "
                            "%s · el paso reportó: %s"
                            % (aname, "; ".join(errs), res["detail"]))
        else:
            st["output_schema"] = {"ok": True,
                                   "detail": "contrato de forma cumplido "
                                             "(artefacto `%s`)" % aname}
    vok = True
    if sp.get("verify"):
        if ctx["dry"]:
            st["verify"] = {"ok": None, "detail": "dry: verify omitido"}
        elif not res["ok"]:
            st["verify"] = {"ok": None, "detail": "omitido: el paso falló"}
        elif not sok:
            st["verify"] = {"ok": None, "detail": "omitido: contrato de "
                            "salida roto (output_schema) — no hay forma "
                            "válida que verificar"}
        else:
            vfn = steplib.resolve(sp["verify"])
            try:
                v = _norm(vfn(ctx, sp))
            except Exception as e:
                v = {"ok": False, "detail": "el verify reventó: %s: %s"
                     % (type(e).__name__, e)}
            st["verify"] = {"ok": v["ok"], "detail": v["detail"]}
            vok = v["ok"]
    st["status"] = OK if (res["ok"] and sok and vok) else FAIL
    if ctx["dry"]:
        st["dry"] = True


def _run_step(state, ctx, sp, st):
    """Ejecuta UN paso (una tentativa) y deja su resultado en `st`."""
    m0 = _mono()                             # v1.5: duración de ESTA tentativa
    st["attempts"] = int(st.get("attempts") or 0) + 1
    st.setdefault("t0", _now())
    st.pop("retriable", None)                # taxonomía: fresca por tentativa
    kind = sp["kind"]

    if kind == "human":
        if ctx["dry"]:
            st["status"], st["dry"] = OK, True
            st["detail"] = "dry: paso human omitido (no-op declarado)"
        else:
            st["status"] = WAITING
            st["detail"] = ("esperando al socio (%s) — `workspace wf resume %s`"
                            " = aprobar" % (sp.get("who", "socio"),
                                            state["run_id"]))
    elif kind == "agent":
        drv = ctx.get("driver")
        if drv is None and not ctx["dry"] and state.get("driver"):
            # v1.1: este run corrió con driver REAL (identidad persistida) y
            # no se pudo rehidratar ni re-inyectar — degradar a stub sería
            # VERDE FINGIDO a nivel run. Fallo honesto, permanente (reintentar
            # sin driver jamás lo arregla).
            st["status"] = FAIL
            st["retriable"] = False
            st["detail"] = ("paso agent SIN driver en un run que corrió con "
                            "driver real (%s) — no degrado a stub. Re-corre: "
                            "`workspace wf resume %s --driver real …` (o "
                            "re-inyecta el driver por código)"
                            % ((state.get("driver") or {}).get("name", "?"),
                               state["run_id"]))
        elif drv is None or ctx["dry"]:
            # Default seguro: SIN driver (o en dry) el paso agent sigue siendo
            # STUB declarado — honesto: verify omitido, jamás verde fingido.
            st["status"], st["stub"] = OK, True
            if ctx["dry"]:
                st["dry"] = True
            st["detail"] = ("STUB (rol %s): paso agent sin driver inyectado "
                            "— no-op declarado" % sp.get("role", "?"))
            if sp.get("verify"):
                st["verify"] = {"ok": None, "detail": "omitido: paso agent "
                                "stub (sin salida real que verificar)"}
        else:
            # READ → EXECUTE → COMMIT (workflows/driver.py): brief cerrado,
            # el driver ejecuta, y el verify corre contra el artefacto REAL.
            st["driver"] = _driverlib.name_of(drv)
            st.pop("stub", None)             # un resume con driver ya no es stub
            try:
                res = _norm(drv(_agent_brief(state, ctx, sp, st)))
            except Exception as e:           # el driver reventó ≠ el runner revienta
                res = {"ok": False, "artifacts": {},
                       "retriable": _classify_exc(e),
                       "detail": "el driver reventó: %s: %s"
                                 % (type(e).__name__, e)}
            _settle(state, ctx, sp, st, res)
    else:                                    # det
        from workflows import steps as steplib
        try:
            # resolve DENTRO del try: un nombre desconocido pone el paso en
            # rojo con detalle claro — no deja el run colgado en `running`.
            res = _norm(steplib.resolve(sp["run"])(ctx, sp))
        except Exception as e:               # el paso reventó ≠ el runner revienta
            res = {"ok": False, "artifacts": {},
                   "retriable": _classify_exc(e),
                   "detail": "el paso reventó: %s: %s" % (type(e).__name__, e)}
        _settle(state, ctx, sp, st, res)

    st["t1"] = _now()
    # v1.5: ms de EJECUCIÓN del paso, acumulado entre tentativas (reloj
    # monotónico — no cuenta el backoff entre reintentos ni pausas human).
    st["ms"] = int(st.get("ms") or 0) + max(0, int((_mono() - m0) * 1000))
    payload = {"run": state["run_id"], "workflow": state["workflow"],
               "step": sp["id"], "kind": kind, "status": st["status"],
               "attempt": st["attempts"], "ms": st["ms"], "dry": ctx["dry"]}
    if st.get("driver"):
        payload["driver"] = st["driver"]
    _emit(payload)


def _maybe_lavish(state, sp, st, gate):
    """Presentación Lavish OPT-IN (v1.3): si el paso declara `present:
    "lavish"`, emite el HTML autocontenido (workflows/lavish.py) como
    artefacto del run — gate con botones si el paso quedó esperando al socio
    (`gate=True`), presentación legible si terminó verde. Best-effort
    ABSOLUTO: un HTML caído jamás toca el resultado del run. En --dry no se
    emite nada (no hay artefactos reales que presentar)."""
    if state.get("dry") or sp.get("present") != "lavish":
        return
    try:
        from workflows import lavish
        if gate:
            st["gate_html"] = lavish.write_gate(state, sp["id"])
        else:
            st["present_html"] = lavish.write_present(state, sp["id"])
    except Exception:
        pass


def _notify_human(state, sp):
    """Aviso por el bus al pausar en un paso human, si el paso declara
    `notify` y el knob `wf.notify_bus` no lo apaga. Best-effort absoluto."""
    to = sp.get("notify")
    if state["dry"] or not to:
        return
    try:
        import settings
        if not settings.get("wf.notify_bus", True):
            return
    except Exception:
        pass
    try:
        import messages
        messages.send(from_agent="workspace", to_agent=to, type="encargo",
                      subject="workflow %s en pausa: paso %s"
                      % (state["workflow"], sp["id"]),
                      body="Run `%s` espera al socio en el paso `%s`.\n"
                           "Aprobar y continuar: `workspace wf resume %s`"
                           % (state["run_id"], sp["id"], state["run_id"]))
    except Exception:
        pass


def _advance(state, driver=None):
    """Envoltura de observabilidad (v1.5) sobre `_advance_loop`: toda pasada
    termina en done/failed/rejected/paused_human — al salir se cierra con
    `_close_pass` (ms total + summary persistidos, `wf_run` end al rastro).
    Aditivo: la semántica de la pasada vive intacta en `_advance_loop`."""
    return _close_pass(_advance_loop(state, driver=driver))


def _advance_loop(state, driver=None):
    """Corre pasos en orden desde el primero no-verde; persiste tras cada uno.
    Sale por: DONE (todos ok) · FAILED (on_fail=stop, o el guard anti-stub) ·
    PAUSED (human · retry agotado · error permanente → escalada automática).

    `driver` orquesta los pasos agent (inyectado > default del proceso >
    None = stub honesto). El callable vive solo en el ctx de ESTA pasada;
    su IDENTIDAD (dict de datos) sí se persiste en state["driver"] para que
    `resume` pueda rehidratarlo (v1.1)."""
    frozen = state["spec"]["steps"]
    ctx = {"repo": ROOT, "run_id": state["run_id"],
           "workflow": state["workflow"], "dry": bool(state["dry"]),
           "params": state.get("params") or {},
           "artifacts": state["artifacts"],
           "driver": driver if driver is not None else _driverlib.get_default()}
    if ctx["driver"] is not None and not ctx["dry"]:
        # identidad del driver (datos, jamás el callable) — la lee resume
        state["driver"] = _driverlib.identity_of(ctx["driver"])
    i = 0
    while i < len(frozen):
        if state["steps"][i]["status"] in (OK, SKIPPED):
            i += 1                           # skipped es terminal (v1.2):
            continue                         # jamás se re-evalúa en resume
        state["current"] = i
        sp, st = frozen[i], state["steps"][i]
        if sp.get("when") is not None:
            # v1.2: transición condicional — predicado DECLARATIVO (datos,
            # no código; gramática en workflows/grammar.py) contra los
            # artefactos del run. Falso ⇒ skipped y el run SIGUE.
            if ctx["dry"]:
                st["when"] = {"holds": None, "detail": "dry: `when` no "
                              "evaluado (sin artefactos reales) — el paso "
                              "corre como no-op dry"}
            else:
                holds, wdet, certain = _grammar.eval_when_certain(
                    sp["when"], state["artifacts"])
                st["when"] = {"holds": holds, "detail": wdet,
                              "certain": certain}
                if not holds and sp["kind"] == "human" and not certain:
                    # v1.4 (P1-B): un gate HUMAN jamás se salta en silencio
                    # por un predicado NO evaluable (dato ausente bajo una
                    # op comparativa). FALLA-CERRADO: pausa y consulta al
                    # socio — el default inseguro era `skipped` (el socio
                    # nunca era consultado). Los pasos NO-human conservan
                    # la semántica fail-safe de siempre.
                    st["status"] = WAITING
                    st["escalated"] = True
                    st["when_fail_closed"] = True
                    st["detail"] = ("gate human FALLA-CERRADO: su `when` no "
                                    "se pudo evaluar con certeza (%s) — un "
                                    "gate no se salta en silencio; "
                                    "`workspace wf resume %s` = decisión del "
                                    "socio (o `workspace wf decide`)"
                                    % (wdet, state["run_id"]))
                    st.setdefault("t0", _now())
                    st["t1"] = _now()
                    st.setdefault("ms", 0)   # v1.5: no ejecutó — 0 honesto
                    _emit({"run": state["run_id"],
                           "workflow": state["workflow"], "step": sp["id"],
                           "kind": sp["kind"], "status": WAITING,
                           "attempt": st.get("attempts", 0),
                           "ms": st["ms"], "dry": ctx["dry"]})
                    state["status"] = PAUSED
                    _maybe_lavish(state, sp, st, gate=True)
                    _save_run(state)
                    _notify_human(state, sp)
                    return state
                if not holds:
                    st["status"] = SKIPPED
                    st["detail"] = "omitido (when: %s)" % wdet
                    st.setdefault("t0", _now())
                    st["t1"] = _now()
                    st.setdefault("ms", 0)   # v1.5: no ejecutó — 0 honesto
                    _emit({"run": state["run_id"],
                           "workflow": state["workflow"], "step": sp["id"],
                           "kind": sp["kind"], "status": SKIPPED,
                           "attempt": st.get("attempts", 0),
                           "ms": st["ms"], "dry": ctx["dry"]})
                    _save_run(state)
                    i += 1
                    continue
        _run_step(state, ctx, sp, st)
        if st["status"] == OK:
            # Lavish OPT-IN (v1.3): paso verde con `present` → HTML legible
            # de su artefacto, ANTES de persistir (el puntero viaja al disco)
            _maybe_lavish(state, sp, st, gate=False)
        _save_run(state)                     # ← persistir tras CADA tentativa
        if st["status"] == OK:
            i += 1
            continue
        if st["status"] == WAITING:
            state["status"] = PAUSED
            _maybe_lavish(state, sp, st, gate=True)   # gate Lavish (opt-in)
            _save_run(state)
            _notify_human(state, sp)
            return state
        # FAIL
        if sp.get("on_fail", "stop") == "retry":
            if not st.get("retriable", True):
                # error PERMANENTE (config/contrato): reintentar no lo
                # arregla — escalar YA, sin quemar max_iter en vano.
                st["status"] = WAITING
                st["escalated"] = True
                st["permanent"] = True
                st["detail"] = ("error PERMANENTE (no transitorio) — sin "
                                "reintentos: `workspace wf resume %s` = "
                                "aprobar/seguir tras arreglar la config · "
                                "fallo: %s" % (state["run_id"],
                                               st.get("detail", "")))
                state["status"] = PAUSED
                _maybe_lavish(state, sp, st, gate=True)
                _save_run(state)
                _notify_human(state, sp)
                return state
            if st["attempts"] < int(sp.get("max_iter") or 1):
                # transitorio → reintento (mismo índice) con backoff+jitter:
                # jamás martillar en loop inmediato un recurso caído.
                delay = backoff_delay(st["attempts"])
                st["backoff_s"] = round(delay, 3)
                if not ctx["dry"] and delay > 0:
                    _sleep(delay)
                continue
            # max_iter agotado → escalada AUTOMÁTICA a human: jamás loop infinito
            st["status"] = WAITING
            st["escalated"] = True
            st["detail"] = ("max_iter (%s) agotado — escalado al socio: "
                            "`workspace wf resume %s` = aprobar/seguir · último "
                            "fallo: %s" % (sp.get("max_iter"),
                                           state["run_id"],
                                           st.get("detail", "")))
            state["status"] = PAUSED
            _maybe_lavish(state, sp, st, gate=True)
            _save_run(state)
            _notify_human(state, sp)
            return state
        state["status"] = FAILED
        _save_run(state)
        return state
    if (not ctx["dry"] and state.get("driver")
            and any(s.get("stub") for s in state["steps"])):
        # v1.1: guard anti-verde-fingido a nivel RUN. Un run que corrió con
        # driver real NO se marca DONE si algún paso agent quedó en stub
        # (p. ej. resumido por código viejo, o estado tocado a mano).
        state["status"] = FAILED
        state["stub_guard"] = (
            "DONE denegado: el run corrió con driver real (%s) pero hay "
            "pasos agent en stub — re-córrelos con el driver "
            "(`workspace wf resume %s --driver …`)"
            % ((state.get("driver") or {}).get("name", "?"), state["run_id"]))
        _save_run(state)
        return state
    state["status"] = DONE
    state["current"] = len(frozen)
    _save_run(state)
    return state


# ── métricas (`workspace wf stats`) ──────────────────────────────────────────
def stats():
    """Agregado sobre TODOS los runs persistidos: por workflow, conteo por
    estado + por paso (corridas, fallos acumulados, intentos). Con esto
    "qué paso falla más" es dato, no sensación. Falla-suave → {}."""
    agg = {}
    for st in list_runs(limit=10000):
        try:
            w = agg.setdefault(st["workflow"], {
                "runs": 0, "done": 0, "failed": 0, "paused": 0, "running": 0,
                "rejected": 0, "dry": 0, "steps": {}})
            w["runs"] += 1
            w[{DONE: "done", FAILED: "failed", PAUSED: "paused",
               REJECTED: "rejected"}.get(st.get("status"), "running")] += 1
            if st.get("dry"):
                w["dry"] += 1
            for s in st.get("steps") or []:
                row = w["steps"].setdefault(s.get("id", "?"), {
                    "runs": 0, "fails": 0, "attempts": 0})
                if s.get("attempts"):
                    row["runs"] += 1
                    row["attempts"] += int(s.get("attempts") or 0)
                if s.get("status") == FAIL or s.get("escalated"):
                    row["fails"] += 1
        except Exception:
            continue
    return agg
