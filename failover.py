#!/usr/bin/env python3
"""WORKSPACE · failover — consumo REAL de FAILOVER_REASONS (motor #2, corrida E-3).

Hasta E-2 la taxonomía razón→estrategia (model_resolver.FAILOVER_REASONS)
existía como datos pero nadie la ejecutaba: el motor clasificaba el error y
salía con código 1. Este módulo es el loop que la consume end-to-end, REUSABLE
por cualquier motor genérico (ollama hoy, openai-compat mañana — el motor solo
provee `attempt(model) -> (resultado, razón)`).

Qué ejecuta (spec congelada C1 + robos de OpenClaw, plan §E-3):

· CADENA DE FALLBACK — `run_with_failover(primario, fallbacks, attempt)`
  recorre los modelos en orden: reintentos acotados sobre el mismo modelo
  según la estrategia (model_resolver.FAILOVER_STRATEGIES, datos), y pasa al
  siguiente SOLO si la estrategia lo permite (un 401 con la misma credencial
  no lo arregla otro modelo; una red caída tampoco). Cota dura MAX_ATTEMPTS:
  jamás un loop infinito.

· SELECTION-SOURCE POLICY — elección explícita del socio (cli/env ⇒
  resolución estricta) = cadena de UN modelo: jamás contestarle desde un
  fallback que no pidió. El resolver ya entrega `fallbacks: []` en estricto;
  aquí además NO se filtra su modelo por cooldown (se intenta sí o sí).

· COOLDOWNS CON BACKOFF — un modelo que falló entra en cooldown exponencial
  model-scoped, con el host EXACTO en la llave (`scope()` parsea hostname:port
  — "llama3.1 en localhost" ≠ "llama3.1 en openrouter"). billing ≠ rate_limit:
  VENTANAS DISTINTAS (OpenClaw) — ver COOLDOWN_LADDERS. Persistido per-máquina
  en `~/.claude/workspace/failover/cooldowns.json` (gitignored, reconstruible)
  para que sobreviva entre invocaciones. Falla-suave: estado ilegible = sin
  cooldowns, jamás levanta.

· PERSIST-OVERRIDE ANTES DEL RETRY + ROLLBACK ESTRECHO — la race que OpenClaw
  ya pagó: al decidir un fallback, la decisión se escribe a disco ANTES de
  reintentar (si el proceso muere a mitad, la próxima invocación la ve y
  arranca por el modelo que funcionaba — `active_override`, con TTL para que
  un huérfano no mande para siempre). Al terminar (éxito o cadena agotada) el
  rollback borra SOLO la entrada propia (token-compare): un cambio en vivo
  del socio u otro proceso NO se pisa.

· `FallbackSummaryError` — cuando la cadena se agota, el detalle por intento
  (modelo · razón → estrategia) viaja en la excepción y se loggea vía eventos
  N9 (`model_fallback`, campos planos estilo `fallbackStep1..N`) al rastro
  N10. El motor la captura y la presenta — diagnóstico, no traceback.

El motor #1 (claude-code) NO pasa por aquí: su failover lo hace el vendor
por dentro (opaco — `events.ENGINE_MAP["claude-code"]["model_fallback"]` es
None, honestidad N9).

Cero dependencias (stdlib, Python 3.9+). Cross-platform. Amputable (C10):
borra este archivo y engines/ollama.py vuelve a fallar one-shot sin cadena.
"""
import contextlib
import json
import os
import time
import urllib.parse
import uuid

import events
import model_resolver
try:                                      # N8 — lock cross-platform (amputable)
    from olock import file_lock, LockTimeout
except Exception:                         # sin olock → degrada a sin-lock
    file_lock, LockTimeout = None, None

REASONS = model_resolver.FAILOVER_REASONS
STRATEGIES = model_resolver.FAILOVER_STRATEGIES

# escaleras de cooldown en segundos, por clase — strikes consecutivos suben
# el peldaño (1º fallo → peldaño 1, 2º → 2, …, tope el último). billing y
# rate_limit son CLASES distintas con ventanas distintas (robo de OpenClaw:
# un billing-disable de minutos martilla una cuenta deshabilitada).
COOLDOWN_LADDERS = {
    "rate_limit": (60, 300, 1500),          # 1m → 5m → 25m
    "billing":    (3600, 21600, 86400),     # 1h → 6h → 24h
}
RETRY_PAUSE = 0.5      # pausa entre reintentos in-process (los tests la anulan)
OVERRIDE_TTL = 900     # un override huérfano (crash) vale 15 min, no para siempre
MAX_ATTEMPTS = 12      # cota dura del loop completo — jamás infinito
_EMITTER = "failover.py"

_COOLDOWNS = "cooldowns.json"
_OVERRIDES = "overrides.json"


class FallbackSummaryError(Exception):
    """La cadena de modelos se agotó (o la estrategia fue abort).

    `attempts` = detalle por intento: [{"step", "model", "reason",
    "strategy"}] — para diagnóstico; `flat_fields()` lo aplana estilo
    fallbackStep* (eventos N9 / logs planos)."""

    def __init__(self, attempts):
        self.attempts = [dict(a) for a in (attempts or [])]
        detail = " · ".join(
            "%s→%s" % (a.get("model", "?"), a.get("reason", "?"))
            for a in self.attempts) or "sin intentos"
        super().__init__("cadena de modelos agotada (%d intento(s)): %s"
                         % (len(self.attempts), detail))

    def flat_fields(self):
        out = {}
        for i, a in enumerate(self.attempts, 1):
            out["fallbackStep%d" % i] = "%s · %s → %s" % (
                a.get("model", "?"), a.get("reason", "?"),
                a.get("strategy", "?"))
        return out


# ── estado per-máquina (~/.claude/workspace/failover/ — gitignored) ───────────
def _state_dir():
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace",
                        "failover")


def _load(name):
    """Lee un JSON de estado. Falla-suave: ilegible/corrupto ⇒ {}."""
    try:
        with open(os.path.join(_state_dir(), name), encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _save(name, data):
    """Escribe atómico (tmp + os.replace). Falla-suave: False si no pudo."""
    try:
        d = _state_dir()
        os.makedirs(d, exist_ok=True)
        tmp = os.path.join(d, "%s.tmp-%d" % (name, os.getpid()))
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=1)
        os.replace(tmp, os.path.join(d, name))
        return True
    except Exception:
        return False


def _lock_timeout():
    try:
        return float(os.environ.get("WORKSPACE_FAILOVER_LOCK_TIMEOUT", "5"))
    except (TypeError, ValueError):
        return 5.0


@contextlib.contextmanager
def _locked(name):
    """F6 — sección crítica read-modify-write sobre `name` bajo lock N8. El
    .tmp+os.replace de `_save` hace cada escritura atómica, pero SIN lock dos
    procesos (p.ej. el daemon y una sesión en vivo) pueden leer-modificar-
    escribir a la vez y perder la actualización del otro (lost-update: se
    martillea un endpoint en billing-disable). El lock serializa el RMW.

    Amputable y falla-suave: sin olock corre sin lock (mismo riesgo que antes,
    nunca peor); si el lock no se adquiere a tiempo (LockTimeout), se procede
    igual — el costo de un lost-update raro es menor que perder el cooldown."""
    if not file_lock:
        yield
        return
    d = _state_dir()
    try:
        os.makedirs(d, exist_ok=True)
    except OSError:
        yield
        return
    try:
        with file_lock(os.path.join(d, name), timeout=_lock_timeout()):
            yield
    except LockTimeout:
        yield


def scope(provider_name, base_url=""):
    """Ámbito de cooldown: provider + HOSTNAME EXACTO (con puerto) del
    endpoint efectivo — parseo real con urlsplit, jamás substring (lección
    OpenClaw): "llama3.1@ollama@localhost:11434" no es "llama3.1@openrouter"."""
    host = ""
    try:
        s = urllib.parse.urlsplit(str(base_url or ""))
        host = s.hostname or ""
        if s.port:
            host = "%s:%d" % (host, s.port)
    except (ValueError, AttributeError):
        host = ""
    return "%s@%s" % (provider_name or "?", host or "?")


def _key(scope_, model):
    return "%s/%s" % (scope_, model)


# ── cooldowns (model-scoped, backoff por clase, persistidos) ────────────────
def cooling_until(scope_, model, now=None):
    """Epoch hasta el que `model` está enfriándose en `scope_` (0.0 = no)."""
    now = time.time() if now is None else now
    e = _load(_COOLDOWNS).get(_key(scope_, model))
    if not isinstance(e, dict):
        return 0.0
    try:
        until = float(e.get("until", 0))
    except (TypeError, ValueError):
        return 0.0
    return until if until > now else 0.0


def note_failure(scope_, model, reason, now=None):
    """Registra un fallo. Si la estrategia de la razón pide cooldown
    (cooldown_retry / cooldown_long), aplica el peldaño que toca de SU
    escalera (strikes consecutivos de la MISMA clase suben; cambiar de
    clase reinicia — un rate_limit no hereda strikes de billing).
    Devuelve los segundos aplicados (0 = la razón no enfría)."""
    strategy = REASONS.get(reason, "")
    kind = (STRATEGIES.get(strategy) or {}).get("cooldown", "")
    if kind not in COOLDOWN_LADDERS:
        return 0
    now = time.time() if now is None else now
    with _locked(_COOLDOWNS):                   # F6 — RMW serializado
        data = _load(_COOLDOWNS)
        k = _key(scope_, model)
        prev = data.get(k) if isinstance(data.get(k), dict) else {}
        try:
            strikes = (int(prev.get("strikes", 0))
                       if prev.get("kind") == kind else 0)
        except (TypeError, ValueError):
            strikes = 0
        ladder = COOLDOWN_LADDERS[kind]
        strikes = min(strikes + 1, len(ladder))
        secs = ladder[strikes - 1]
        data[k] = {"kind": kind, "strikes": strikes, "until": now + secs,
                   "reason": reason, "ts": now}
        _save(_COOLDOWNS, data)
    return secs


def note_success(scope_, model):
    """Éxito ⇒ el modelo sale del cooldown y sus strikes se borran."""
    with _locked(_COOLDOWNS):                   # F6 — RMW serializado
        data = _load(_COOLDOWNS)
        if data.pop(_key(scope_, model), None) is not None:
            _save(_COOLDOWNS, data)


# ── override persistido (la race de OpenClaw) ───────────────────────────────
def active_override(agent, now=None):
    """Override VIGENTE para `agent` (dict con model/scope/reason/ts/token)
    o None. TTL OVERRIDE_TTL: un override huérfano de un crash informa a la
    próxima invocación, pero no manda para siempre."""
    if not agent:
        return None
    e = _load(_OVERRIDES).get(str(agent))
    if not isinstance(e, dict) or not e.get("model"):
        return None
    now = time.time() if now is None else now
    try:
        ts = float(e.get("ts", 0))
    except (TypeError, ValueError):
        return None
    return e if 0 <= now - ts <= OVERRIDE_TTL else None


def persist_override(agent, scope_, model, reason=""):
    """Escribe la decisión de fallback ANTES del retry (si el proceso muere
    a mitad, la decisión queda en disco — la race que OpenClaw pagó).
    Devuelve el token para el rollback estrecho ("" si no se pudo escribir;
    falla-suave: sin disco igual se reintenta, solo se pierde la memoria)."""
    if not agent:
        return ""
    token = uuid.uuid4().hex
    with _locked(_OVERRIDES):                    # F6 — RMW serializado
        data = _load(_OVERRIDES)
        data[str(agent)] = {"model": str(model), "scope": str(scope_),
                            "reason": str(reason), "ts": time.time(),
                            "token": token, "owner": _EMITTER}
        ok = _save(_OVERRIDES, data)
    return token if ok else ""


def rollback_override(agent, token):
    """Rollback ESTRECHO: borra el override SOLO si sigue siendo el nuestro
    (mismo token). Si el socio u otro proceso lo cambió en vivo, NO se pisa
    (se deja tal cual). True solo si borró la entrada propia."""
    if not agent or not token:
        return False
    with _locked(_OVERRIDES):                    # F6 — RMW serializado
        data = _load(_OVERRIDES)
        e = data.get(str(agent))
        if isinstance(e, dict) and e.get("token") == token:
            del data[str(agent)]
            return _save(_OVERRIDES, data)
    return False


# ── planeación de la cadena ─────────────────────────────────────────────────
def plan_candidates(primary, fallbacks=(), *, strict=False, agent="",
                    scope_="", now=None):
    """Orden de modelos para esta corrida. Devuelve (candidatos, saltados).

    · estricto (elección explícita del socio): SOLO su modelo — ni cadena ni
      filtro por cooldown (se intenta sí o sí; jamás responder con otro).
    · default: primario + fallback_models (ya sin hidden, los quitó el
      resolver), menos los que están enfriándose (saltados, con su `until`).
      Un override vigente (crash previo) pasa al frente SI es candidato
      legítimo — jamás introduce un modelo fuera de la resolución.
    · si TODOS enfrían, se intenta el primero igual (falla-suave: negarse
      por estado viejo sería peor que probar)."""
    seen, candidates = set(), []
    for m in [primary] + list(fallbacks or []):
        if m and m not in seen:
            seen.add(m)
            candidates.append(m)
    if strict or not candidates:
        return candidates[:1], []
    ov = active_override(agent, now=now)
    if ov and ov.get("model") in candidates:
        candidates.remove(ov["model"])
        candidates.insert(0, ov["model"])
    usable, skipped = [], []
    for m in candidates:
        until = cooling_until(scope_, m, now=now)
        if until:
            skipped.append({"model": m, "until": until})
        else:
            usable.append(m)
    if not usable:
        usable = candidates[:1]
        skipped = [s for s in skipped if s["model"] != usable[0]]
    return usable, skipped


# ── eventos N9 (model_fallback → rastro N10; metadata, jamás contenido) ─────
def _emit(emitter, payload):
    events.emit("model_fallback",
                {k: v for k, v in payload.items() if v not in ("", None, 0)},
                emitter=emitter or _EMITTER)


# ── el loop E-3 (reusable por cualquier motor genérico) ─────────────────────
def run_with_failover(primary, fallbacks, attempt, *, strict=False, agent="",
                      scope_="", session_id="", emitter=_EMITTER):
    """Ejecuta `attempt(model) -> (resultado, razón)` sobre la cadena.

    razón "" = éxito ⇒ devuelve (resultado, modelo, intentos) y limpia el
    cooldown del modelo. razón ∈ FAILOVER_REASONS ⇒ se ejecuta SU estrategia
    (FAILOVER_STRATEGIES, datos): reintentos acotados sobre el mismo modelo,
    cooldown si aplica, y fallback al siguiente SOLO si la estrategia lo
    permite. Antes de cada transición se persiste el override (y al terminar
    se le hace rollback estrecho). Cadena agotada / abort ⇒
    FallbackSummaryError con el detalle por intento. Cota dura MAX_ATTEMPTS."""
    candidates, skipped = plan_candidates(
        primary, fallbacks, strict=strict, agent=agent, scope_=scope_)
    attempts = [{"step": 0, "model": s["model"], "reason": "cooldown",
                 "strategy": "skip"} for s in skipped]
    token, total = "", 0
    try:
        for idx, model in enumerate(candidates):
            retries_used = 0
            while True:
                total += 1
                if total > MAX_ATTEMPTS:
                    raise FallbackSummaryError(attempts)
                result, reason = attempt(model)
                if not reason:
                    note_success(scope_, model)
                    if idx > 0 or retries_used:
                        _emit(emitter, {"agent": agent, "scope": scope_,
                                        "session_id": session_id,
                                        "to_model": model, "step": total,
                                        "recovered": True})
                    return result, model, attempts
                strategy = REASONS.get(reason, "fallback_model")
                plan = STRATEGIES.get(strategy) or {}
                attempts.append({"step": total, "model": model,
                                 "reason": reason, "strategy": strategy})
                if plan.get("cooldown"):
                    note_failure(scope_, model, reason)
                if retries_used < int(plan.get("retries") or 0):
                    retries_used += 1
                    if RETRY_PAUSE > 0:
                        time.sleep(RETRY_PAUSE)
                    continue
                if not plan.get("fallback") or idx + 1 >= len(candidates):
                    raise FallbackSummaryError(attempts)
                nxt = candidates[idx + 1]
                # la race de OpenClaw: PRIMERO persistir la decisión,
                # DESPUÉS reintentar con el siguiente modelo
                token = persist_override(agent, scope_, nxt,
                                         reason=reason) or token
                _emit(emitter, {"agent": agent, "scope": scope_,
                                "session_id": session_id,
                                "from_model": model, "to_model": nxt,
                                "reason": reason, "strategy": strategy,
                                "step": total})
                break               # → siguiente modelo de la cadena
        raise FallbackSummaryError(attempts)
    except FallbackSummaryError as e:
        payload = {"agent": agent, "scope": scope_, "session_id": session_id,
                   "exhausted": True, "attempts": len(e.attempts)}
        payload.update(e.flat_fields())
        _emit(emitter, payload)
        raise
    finally:
        # rollback estrecho: SOLO lo nuestro, jamás un cambio en vivo del socio
        if token:
            rollback_override(agent, token)


if __name__ == "__main__":
    # inspección rápida del estado per-máquina:  python3 failover.py
    cd = _load(_COOLDOWNS)
    ov = _load(_OVERRIDES)
    now = time.time()
    print("cooldowns (%s):" % os.path.join(_state_dir(), _COOLDOWNS))
    if not cd:
        print("   (ninguno)")
    for k, e in sorted(cd.items()):
        left = max(0, float(e.get("until", 0)) - now)
        print("   · %-40s %s strike %s — %ds restantes"
              % (k, e.get("kind"), e.get("strikes"), int(left)))
    print("overrides (%s):" % os.path.join(_state_dir(), _OVERRIDES))
    if not ov:
        print("   (ninguno)")
    for a, e in sorted(ov.items()):
        age = now - float(e.get("ts", 0) or 0)
        print("   · %-12s → %s (%s, hace %ds%s)"
              % (a, e.get("model"), e.get("reason") or "?", int(age),
                 ", EXPIRADO" if age > OVERRIDE_TTL else ""))
