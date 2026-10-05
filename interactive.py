#!/usr/bin/env python3
"""WORKSPACE · interactive — contrato INTERACTIVO por motor (build A).

La pieza que faltaba tras connectors (conexión) + neutral_hooks (ciclo de
vida): correr la CONVERSACIÓN EN VIVO de un agente (turnos + tool-use) en un
motor NO-Claude, con los comportamientos del harness (memoria de sesión,
status en vivo, inbox) orquestados por el runner neutral. Es lo que habilita
"un agente por motor/cuenta".

DISTINTO del contrato headless (headless.py = one-shot texto→texto, sin
sesión): aquí hay SESIÓN con estado, N turnos y un loop de tool-calling.

CONTRATO (dos capas):

1. Adaptador de TURNO por motor — un callable que produce UN paso del modelo:

       turn_fn(messages, tools_spec, *, model, timeout) -> (ok, reply | err)

   · `messages`   = historial en formato de chat OpenAI (el formato canónico
                    del estado de sesión v1; un motor con otro protocolo
                    traduce ADENTRO de su turn_fn).
   · `tools_spec` = herramientas anunciables en el shape function-calling de
                    OpenAI ([] = el request JAMÁS anuncia tools).
   · reply (dict) = {"content": str, "tool_calls": [{"id","name",
                    "arguments": dict}], "assistant_message": <msg verbatim
                    para reanudar el hilo>}. err = str (ya redactado).

2. `InteractiveSession` — orquesta el ciclo de vida de `neutral_hooks`
   alrededor de ese callable (contrato: engines/LIFECYCLE.md +
   engines/INTERACTIVE.md):

       start()  → on_session_start   (contexto/memoria → mensaje system)
       turn(p)  → on_pre_turn        (aditivo: contexto → mensaje system)
                  loop{ modelo → [on_pre_tool → tool LOCAL → on_post_tool]* }
                  on_post_turn
       end()    → on_session_end     (cleanup + clear del status)

   El status en vivo (<brain>/STATE/now.json) y el inbox 📨 los publica el
   behavior correspondiente de neutral_hooks — este módulo no duplica nada.
   En paralelo la sesión mantiene el doc NEUTRAL (`neutral_transcript`
   workspace.transcript v1): la traducción motor↔schema neutral vive aquí.

SEGURIDAD (misma postura que connectors, sin debilitar nada):

  · El path interactivo SÍ puede usar tools — pero SOLO las registradas
    explícitamente en el `ToolRegistry` LOCAL de la sesión. Nada del modelo
    ejecuta código: un tool_call a un nombre no registrado devuelve un error
    de texto al modelo, jamás ejecuta.
  · Confirmaciones N2/N3 = responsabilidad de la capa WORKSPACE: el hook
    `tool_gate(name, args) -> bool` se llama ANTES de cada ejecución; False
    ⇒ la herramienta NO corre y el modelo recibe la negativa. (El wiring a
    los tiers reales / MCP es el siguiente paso — documentado, no simulado.)
  · Credenciales: mismas leyes de connectors — `vet_provider` se EJECUTA al
    construir el adaptador (suscripción directa = rechazo, sin bypass); keys
    solo por NOMBRE de env-var, resueltas al llamar; auth "none" ⇒ jamás
    viaja Authorization; errores pasan por redacción (la key nunca al log).
  · Este módulo NO toca el default del harness: claude-code sigue siendo el
    motor primario; todo esto es opt-in por nombre de provider.

Cero dependencias (stdlib, Python 3.9+). Mac y Windows. Amputable (C10):
borra este archivo y nada más cambia (nadie del camino caliente lo importa).
"""
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import uuid

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import connectors        # noqa: E402  (vet + credenciales + redacción)
import model_resolver    # noqa: E402
import neutral_hooks     # noqa: E402  (ciclo de vida neutral — build B)
import neutral_transcript  # noqa: E402  (schema workspace.transcript v1)

DEFAULT_TIMEOUT = 120          # por request de turno (interactivo ≠ batch)
MAX_TOOL_ROUNDS = 8            # cota dura del loop tool-calling por turno
MAX_TOOL_RESULT_CHARS = 8000   # un tool no infla el contexto sin límite
# filtro de quirks.extra_headers — ÚNICA definición, compartida con el path
# headless (connectors.FORBIDDEN_HEADERS); alias local por compat.
_FORBIDDEN_HEADERS = connectors.FORBIDDEN_HEADERS


class InteractiveError(RuntimeError):
    """Error del contrato interactivo (configuración/protocolo)."""


class InteractiveSecurityError(InteractiveError):
    """INVARIANTE violado (provider vetado, header prohibido, …)."""


# ═══════════════════════════════════════════════════════════════════════════
# ToolRegistry — herramientas LOCALES explícitas (las únicas que corren)
# ═══════════════════════════════════════════════════════════════════════════

class ToolRegistry:
    """Registro de herramientas LOCALES de la sesión.

    El modelo solo puede invocar lo que la capa WORKSPACE registró aquí a mano
    (funciones Python locales). No hay descubrimiento dinámico, no hay shell,
    no hay red implícita: si un tool necesita algo, lo hace SU función, bajo
    las mismas leyes del harness (sin credenciales, sin exfiltración).
    Wiring MCP real = siguiente paso (engines/INTERACTIVE.md §TODO)."""

    def __init__(self):
        self._tools = {}

    def register(self, name, fn, description="", parameters=None):
        """Registra `fn(args: dict) -> str`. `parameters` = JSON-schema del
        shape function-calling (default: objeto libre)."""
        if not name or not callable(fn):
            raise InteractiveError("tool inválido: nombre vacío o fn no "
                                   "llamable (%r)" % (name,))
        self._tools[str(name)] = {
            "fn": fn,
            "description": str(description or ""),
            "parameters": parameters or {"type": "object", "properties": {}},
        }

    def names(self):
        return sorted(self._tools)

    def spec(self):
        """Shape function-calling de OpenAI (lo que anuncia el request)."""
        return [{"type": "function",
                 "function": {"name": n,
                              "description": t["description"],
                              "parameters": t["parameters"]}}
                for n, t in sorted(self._tools.items())]

    def run(self, name, args):
        """Ejecuta un tool REGISTRADO. Devuelve (ok, texto). Un nombre no
        registrado JAMÁS ejecuta nada (ok=False + negativa). Excepciones del
        tool → (False, error). El resultado se recorta a MAX_TOOL_RESULT_CHARS
        (marca visible)."""
        t = self._tools.get(name)
        if t is None:
            return False, ("WORKSPACE: herramienta %r no registrada — no se "
                           "ejecuta nada" % (name,))
        try:
            out = t["fn"](args if isinstance(args, dict) else {})
        except Exception as e:
            return False, "WORKSPACE: la herramienta %r falló: %s" % (name, e)
        out = out if isinstance(out, str) else json.dumps(
            out, ensure_ascii=False, default=str)
        if len(out) > MAX_TOOL_RESULT_CHARS:
            out = (out[:MAX_TOOL_RESULT_CHARS]
                   + "\n[… recortado por el harness …]")
        return True, out


# ═══════════════════════════════════════════════════════════════════════════
# Adaptador de turno CONCRETO: openai_compatible (locales + OpenRouter/OpenAI)
# ═══════════════════════════════════════════════════════════════════════════

def make_openai_compatible_turn(provider):
    """turn_fn para un provider OpenAI-compatible (Ollama / LM Studio / vLLM
    / OpenRouter / OpenAI) — el loop de chat CON function/tool-calling del
    protocolo OpenAI. POST {base_url}/chat/completions, stdlib puro.

    Seguridad EJECUTADA al construir (no al documentar): `vet_provider` de
    connectors corre aquí — provider vetado (suscripción directa, key sin
    TLS a host remoto, …) ⇒ InteractiveSecurityError, sin bypass. La key se
    resuelve del env AL LLAMAR (solo su NOMBRE vive en providers/*.json);
    auth "none" ⇒ jamás viaja Authorization; errores redactados."""
    p = dict(provider or {})
    name = p.get("name", "?")
    verrs = connectors.vet_provider(p)
    if verrs:
        raise InteractiveSecurityError(
            "provider %r vetado para el path interactivo: %s"
            % (name, "; ".join(verrs)))
    url = (p.get("base_url") or "").rstrip("/") + "/chat/completions"

    def turn(messages, tools_spec, *, model=None, timeout=DEFAULT_TIMEOUT):
        key = ""
        if p.get("auth_type") == "api_key":
            key, err = connectors._resolve_key(p)
            if not key:
                return False, "%s: %s" % (name, err)
        mdl = model or model_resolver.resolve_model({}, p)["model"]
        if not mdl:
            return False, ("%s: sin modelo — pasa model= o declara "
                           "default_model en providers/%s.json" % (name, name))
        payload = {"model": mdl, "stream": False, "messages": list(messages)}
        if tools_spec:                 # [] ⇒ el request JAMÁS anuncia tools
            payload["tools"] = list(tools_spec)
        hdrs = {"Content-Type": "application/json"}
        extra = (p.get("quirks") or {}).get("extra_headers") or {}
        for k, v in extra.items():
            # un quirk jamás mete una credencial de contrabando
            if (isinstance(k, str) and isinstance(v, str)
                    and k.lower() not in _FORBIDDEN_HEADERS):
                hdrs[k] = v
        if key:                        # auth none ⇒ jamás Authorization
            hdrs["Authorization"] = "Bearer " + key
        req = urllib.request.Request(
            url, data=json.dumps(payload).encode("utf-8"),
            headers=hdrs, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                raw = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as e:
            try:
                # redactar ANTES de truncar (un corte a media key fugaría
                # el prefijo parcial al log)
                body = connectors._redact(
                    e.read().decode("utf-8", errors="replace"), key)[:300]
            except Exception:
                body = ""
            return False, connectors._redact(
                "%s: HTTP %d: %s" % (name, e.code, body), key)
        except Exception as e:         # URLError / timeout / conexión
            return False, connectors._redact("%s: red: %s" % (name, e), key)
        try:
            msg = json.loads(raw)["choices"][0]["message"]
            if not isinstance(msg, dict):
                raise TypeError
        except (ValueError, KeyError, IndexError, TypeError):
            return False, ("%s: respuesta malformada (no es chat.completion):"
                           " %s" % (name, connectors._redact(raw, key)[:200]))
        content = msg.get("content")
        content = content if isinstance(content, str) else ""
        calls = []
        for tc in (msg.get("tool_calls") or []):
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") or {}
            fn = fn if isinstance(fn, dict) else {}
            args_raw = fn.get("arguments", "")
            try:
                args = json.loads(args_raw or "{}")
            except (TypeError, ValueError):
                args = {"_raw": str(args_raw)[:2000]}
            if not isinstance(args, dict):
                args = {"_args": args}
            calls.append({"id": str(tc.get("id", "")),
                          "name": str(fn.get("name", "")),
                          "arguments": args})
        return True, {"content": content, "tool_calls": calls,
                      "assistant_message": msg}

    return turn


# ═══════════════════════════════════════════════════════════════════════════
# InteractiveSession — el orquestador neutral del ciclo de vida
# ═══════════════════════════════════════════════════════════════════════════

class InteractiveSession:
    """Una sesión interactiva sobre CUALQUIER turn_fn del contrato, con el
    ciclo de vida de neutral_hooks alrededor. Falla-suave en los hooks
    (jamás bloquean el turno); el turno del motor sí reporta errores honesto
    (ok=False)."""

    def __init__(self, turn_fn, *, brain=None, agent=None,
                 engine="openai-compatible", model=None, tools=None,
                 system_prompt="", behaviors=None, timeout=DEFAULT_TIMEOUT,
                 max_tool_rounds=MAX_TOOL_ROUNDS, tool_gate=None,
                 session_id=""):
        if not callable(turn_fn):
            raise InteractiveError("turn_fn debe ser callable (contrato de "
                                   "turno — ver docstring del módulo)")
        self.turn_fn = turn_fn
        self.brain = brain
        self.agent = agent
        self.engine = engine
        self.model = model
        self.tools = tools if tools is not None else ToolRegistry()
        self.behaviors = behaviors   # None → DEFAULT_BEHAVIORS de neutral_hooks
        self.timeout = timeout
        self.max_tool_rounds = max(1, int(max_tool_rounds))
        self.tool_gate = tool_gate
        self.session_id = session_id or str(uuid.uuid4())
        self.messages = []           # estado canónico (formato chat OpenAI)
        self.started = False
        self.ended = False
        self._doc = neutral_transcript.empty_doc(
            id=self.session_id, engine=engine, cwd=str(brain or ""))
        if system_prompt:
            self.messages.append({"role": "system", "content": system_prompt})

    # ── ciclo de vida ──────────────────────────────────────────────────────
    def _payload(self, extra=None):
        d = {"session_id": self.session_id, "engine": self.engine}
        if self.brain:
            d["cwd"] = str(self.brain)
        d.update(extra or {})
        return d

    def _hook_kw(self):
        kw = {}
        if self.brain:
            kw["brain"] = str(self.brain)
        if self.behaviors is not None:
            kw["behaviors"] = self.behaviors
        return kw

    def _inject(self, label, ctx):
        """Contexto neutral de los hooks → mensaje system ADITIVO (jamás
        muta el prompt del socio — regla v1 del contrato)."""
        if ctx and ctx.strip():
            self.messages.append(
                {"role": "system",
                 "content": "[WORKSPACE · %s]\n%s" % (label, ctx.strip())})

    def start(self, source="startup"):
        """on_session_start: memoria de sesión / inbox / status "en sesión".
        Devuelve el contexto inyectado (str, '' si nada)."""
        res = neutral_hooks.on_session_start(
            self._payload({"source": source}), **self._hook_kw())
        self._inject("contexto de arranque", res.get("context", ""))
        self.started = True
        return res.get("context", "")

    def turn(self, prompt):
        """UN turno completo del socio: pre_turn (contexto aditivo + status)
        → loop del motor con tool-calling (pre/post_tool por herramienta) →
        post_turn. Devuelve (ok, texto_final)."""
        if self.ended:
            return False, "sesión terminada (end() ya corrió)"
        if not self.started:
            self.start()
        res = neutral_hooks.on_pre_turn(
            self._payload({"prompt": prompt}), **self._hook_kw())
        self._inject("contexto del turno", res.get("context", ""))
        self.messages.append({"role": "user", "content": prompt})
        self._doc["turns"].append(neutral_transcript.make_turn(
            "user", prompt))

        tools_spec = self.tools.spec()
        for _ in range(self.max_tool_rounds):
            ok, reply = self.turn_fn(self.messages, tools_spec,
                                     model=self.model, timeout=self.timeout)
            if not ok:
                return False, str(reply)
            calls = reply.get("tool_calls") or []
            content = reply.get("content") or ""
            if not calls:
                # turno final: texto del asistente
                self.messages.append({"role": "assistant",
                                      "content": content})
                self._doc["turns"].append(neutral_transcript.make_turn(
                    "assistant", content))
                neutral_hooks.on_post_turn(self._payload(), **self._hook_kw())
                return True, content
            # el modelo pidió herramientas: reanudar el hilo con el mensaje
            # del asistente VERBATIM (contrato del protocolo OpenAI)…
            self.messages.append(reply.get("assistant_message")
                                 or {"role": "assistant", "content": content,
                                     "tool_calls": []})
            self._doc["turns"].append(neutral_transcript.make_turn(
                "assistant", content,
                tool_calls=[neutral_transcript.make_tool_call(
                    c["name"], c["arguments"], c["id"]) for c in calls]))
            # …y correr cada herramienta LOCAL con sus hooks alrededor.
            for c in calls:
                self.messages.append({
                    "role": "tool", "tool_call_id": c["id"],
                    "content": self._run_tool(c["name"], c["arguments"])})
        return False, ("el modelo pidió herramientas %d rondas seguidas — "
                       "cota max_tool_rounds alcanzada, turno abortado"
                       % self.max_tool_rounds)

    def _run_tool(self, name, args):
        """pre_tool → gate N2/N3 de la capa WORKSPACE → registry → post_tool.
        Solo METADATA a los hooks (jamás los args — misma ley que la
        telemetría N10)."""
        meta = {"tool_name": name, "engine": self.engine}
        neutral_hooks.on_pre_tool(self._payload(meta), **self._hook_kw())
        gate = self.tool_gate
        if gate is not None:
            try:
                allowed = bool(gate(name, args))
            except Exception:
                allowed = False        # gate roto = fail-closed
            if not allowed:
                out = ("WORKSPACE: herramienta %r denegada por la capa de "
                       "confirmaciones (N2/N3) — no se ejecutó" % (name,))
                neutral_hooks.on_post_tool(
                    self._payload(dict(meta, ok=False)), **self._hook_kw())
                return out
        ok, out = self.tools.run(name, args)
        neutral_hooks.on_post_tool(
            self._payload(dict(meta, ok=ok)), **self._hook_kw())
        return out

    def end(self, reason="exit"):
        """on_session_end: cleanup + clear del status. Idempotente."""
        if self.ended:
            return
        self.ended = True
        neutral_hooks.on_session_end(
            self._payload({"reason": reason}), **self._hook_kw())

    def transcript(self):
        """El doc NEUTRAL (workspace.transcript v1) de la sesión hasta ahora."""
        return self._doc


def session_for_provider(provider_name, **kw):
    """Azúcar: providers/<name>.json → InteractiveSession lista (adaptador
    openai_compatible). Levanta InteractiveError si el provider no carga o
    no es de conexión directa openai_compatible; InteractiveSecurityError si
    el vet lo rechaza. El default del harness NO cambia: esto es opt-in por
    nombre."""
    p, errs = model_resolver.load_provider(provider_name)
    if errs:
        raise InteractiveError("providers/%s.json inválido: %s"
                               % (provider_name, "; ".join(errs)))
    ct = connectors.connection_type(p)
    if ct != "openai_compatible":
        raise InteractiveError(
            "provider %r es %s — el adaptador interactivo concreto v1 solo "
            "cubre openai_compatible (official_cli: ver INTERACTIVE_CLIS; "
            "native_api: A-IMPLEMENTAR)" % (provider_name, ct or "desconocido"))
    return InteractiveSession(make_openai_compatible_turn(p), **kw)


# ═══════════════════════════════════════════════════════════════════════════
# official_cli interactivo — ANDAMIAJE (documentado, A-VERIFICAR)
# ═══════════════════════════════════════════════════════════════════════════

#: Cómo corre la sesión INTERACTIVA de cada CLI oficial y qué puede observar
#: WORKSPACE desde fuera. La suscripción del socio la gestiona el BINARIO
#: OFICIAL (su login) — WORKSPACE jamás ve el token (mismo invariante de
#: connectors.OFFICIAL_CLIS, que cubre el lado headless/ingest).
INTERACTIVE_CLIS = {
    "antigravity": {
        "binary": "agy", "argv": ["agy"], "verified": False,
        "hooks": "wrapper",
        "note": "Flags verified with installed agy --help; live session pending",
    },
    "claude-code": {
        "binary": "claude",
        "argv": ["claude"],
        "verified": True,
        "hooks": "native",
        "note": ("PRIMARIO — va por dispatch + engines/claude_code.py con "
                 "hooks nativos completos (workspace_hook → neutral_hooks). "
                 "run_official_cli_interactive lo RECHAZA a propósito: un "
                 "wrapper encima duplicaría los hooks (double-fire)"),
    },
    "codex": {
        "binary": "codex",
        "argv": ["codex"],
        "verified": False,
        "hooks": "wrapper",
        "note": ("A-VERIFICAR contra un Codex CLI real: `codex` a secas abre "
                 "el TUI interactivo (docs públicas); sin hook-system ⇒ el "
                 "wrapper emite session_start/end desde fuera y el contexto "
                 "de arranque solo puede IMPRIMIRSE al socio (candidato "
                 "A-VERIFICAR: inyectarlo como primer prompt / "
                 "AGENTS.md). Sesión cruda → parse_codex al cerrar"),
    },
    "gemini": {
        "binary": "gemini",
        "argv": ["gemini"],
        "verified": False,
        "hooks": "wrapper",
        "note": ("`gemini` a secas abre el TUI interactivo (CONFIRMADO por "
                 "--help 0.40.1: 'Defaults to interactive mode'); la corrida "
                 "E2E sigue A-VERIFICAR (sin login en esta máquina). El motor "
                 "engines/gemini.py ancla --approval-mode default. Sin "
                 "ingester aún (connectors lo marca A-IMPLEMENTAR) ⇒ sin "
                 "transcript neutral post-hoc"),
    },
}


def interactive_cli_status(cli):
    """Estado del andamiaje interactivo de un CLI oficial (inspección PURA —
    jamás lanza el binario). None si el CLI no está en la tabla."""
    info = INTERACTIVE_CLIS.get(cli)
    if info is None:
        return None
    st = dict(info)
    st["cli"] = cli
    st["binary_in_path"] = bool(shutil.which(info["binary"]))
    hs = connectors.official_cli_status(cli) or {}
    st["ingester_available"] = bool(hs.get("ingester_available"))
    return st


def run_official_cli_interactive(cli, brain=None, argv=None, behaviors=None,
                                 exe_override=None, runner=None, context_sink=None):
    """Lanza un CLI oficial en modo INTERACTIVO envuelto en el ciclo de vida
    neutral: on_session_start → el binario corre con la tty → on_session_end
    al salir. Devuelve el returncode. El contexto de arranque va al
    `context_sink` del motor (codex/antigravity lo inyectan INVISIBLE en su
    doc de proyecto — AGENTS.md/GEMINI.md, generado o anexado marcado); el
    print de abajo es SOLO el último recurso para callers sin sink.

    ⚠ A-VERIFICAR: los argv de codex/gemini vienen de docs públicas; esta
    función queda probada SOLO contra un binario falso en la suite (jamás se
    corre un CLI real ahí). `exe_override`/`runner` son knobs de test.

    claude-code se RECHAZA: su path real es dispatch + hooks nativos; un
    wrapper encima haría double-fire de listeners."""
    info = INTERACTIVE_CLIS.get(cli)
    if info is None:
        raise InteractiveError("CLI oficial desconocido: %r (tabla: %s)"
                               % (cli, ", ".join(sorted(INTERACTIVE_CLIS))))
    if info.get("hooks") == "native":
        raise InteractiveError(
            "%s va por su path nativo (dispatch + engines/) — el wrapper "
            "interactivo duplicaría los hooks" % cli)
    exe = exe_override or shutil.which(info["binary"])
    if not exe:
        raise InteractiveError("%s no está en PATH (binario %r)"
                               % (cli, info["binary"]))
    payload = {"source": "startup", "engine": cli}
    kw = {}
    if brain:
        payload["cwd"] = str(brain)
        kw["brain"] = str(brain)
    if behaviors is not None:
        kw["behaviors"] = behaviors
    res = neutral_hooks.on_session_start(payload, **kw)
    ctx = res.get("context", "")
    if context_sink is not None:
        context_sink(ctx)
    elif ctx.strip():
        # única vía honesta hacia un TUI ajeno: mostrárselo al socio.
        print("[WORKSPACE · contexto de arranque]\n%s\n" % ctx.strip())
    env = dict(os.environ)
    if brain:
        env["WORKSPACE_BRAIN"] = str(brain)
    cmd = [exe] + list(argv if argv is not None else info["argv"][1:])
    try:
        run = runner or subprocess.call
        rc = run(cmd, env=env, cwd=str(brain) if brain else None)
    finally:
        neutral_hooks.on_session_end(
            dict(payload, source="exit"), **kw)
    return rc


# ═══════════════════════════════════════════════════════════════════════════
# REPL mínimo de prueba manual (opt-in explícito; jamás el path default)
# ═══════════════════════════════════════════════════════════════════════════

def _repl(argv):
    import argparse
    ap = argparse.ArgumentParser(
        prog="interactive.py",
        description="REPL interactivo sobre un provider OpenAI-compatible "
                    "(prueba manual del adaptador; el default del harness "
                    "sigue siendo claude-code)")
    ap.add_argument("--provider", required=True,
                    help="nombre en providers/*.json (ollama, lmstudio, …)")
    ap.add_argument("--model", default=None)
    ap.add_argument("--brain", default=None,
                    help="cerebro para status/memoria (opcional)")
    a = ap.parse_args(argv)
    ses = session_for_provider(a.provider, model=a.model, brain=a.brain)
    ctx = ses.start()
    if ctx:
        print("[contexto]\n%s\n" % ctx)
    print("REPL %s — 'salir' o Ctrl-D para terminar" % a.provider)
    try:
        while True:
            try:
                line = input("tú > ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if line.strip().lower() in ("salir", "exit", "quit", ":q"):
                break
            ok, out = ses.turn(line)
            print(("%s > %s" if ok else "⚠ %s: %s")
                  % (a.provider, out))
    finally:
        ses.end()
    return 0


if __name__ == "__main__":
    sys.exit(_repl(sys.argv[1:]))
