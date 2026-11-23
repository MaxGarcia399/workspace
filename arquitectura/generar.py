#!/usr/bin/env python3
"""WORKSPACE · arquitectura/generar — UNA fuente, los 4 formatos del paquete.

    python3 -m arquitectura.generar <destino>     arma <destino>/{claude,agent-plugins,opencode}

  · claude/         plugin de Claude Code (.claude-plugin/plugin.json, hooks/hooks.json,
                    .mcp.json, skills/). Lo cargan Claude Code, Copilot, OpenClaw y
                    Antigravity (agy plugin import claude). Con antigravity/: los hooks
                    de Antigravity en SU forma (hooks5), para el proyecto por sesión.
  · agent-plugins/  Agent Plugins 1.0 (plugin.json + skills/ + mcp.json) y los hooks de
                    cada motor que lo usa (Codex, Cursor, Kiro, Hermes) en su carpeta,
                    con el dialecto y la ruta de su ficha.
  · opencode/       plugin JS de OpenCode (package.json + index.js) con skills/.
  · openclaw/       plugin NATIVO de OpenClaw (openclaw.plugin.json + package.json + index.js):
                    sus avisos tipados (api.on), el servidor MCP en su manifiesto (mcpServers) y
                    las skills del paquete (sin las del cerebro: en el gateway un plugin es de
                    todos los agentes; las del cerebro le llegan por el skills/ de su workspace).

Todo sale de arquitectura/paquete/ (la fuente), de las fichas (qué evento oficial
cae en cada momento) y de momentos.json. Los hooks llaman al MISMO lanzador fijo
(lanzador/hook.py <destino> <momento>). Salida determinista y sin rutas de la
máquina: donde la ficha no da la variable con la carpeta del paquete queda
{{RAIZ}}, que se fija al instalar. `validar(destino)` revisa los 4 formatos.
"""
import json
import os
import re
import shutil
import subprocess
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.dirname(AQUI)
FUENTE = os.path.join(AQUI, "paquete")
if RAIZ_REPO not in sys.path:
    sys.path.insert(0, RAIZ_REPO)
from arquitectura import contrato  # noqa: E402

FORMATOS = ("claude", "agent-plugins", "opencode", "openclaw")
#: Los formatos que NO llevan las skills del cerebro (F7): el plugin de OpenClaw lo carga el gateway para TODOS
#: los agentes del perfil (VERIFICADO 2026.10.7: sus avisos llegan de las sesiones de cualquier agente), así que
#: las skills de un cerebro irían al menú de los demás. Las del cerebro le llegan por el skills/ de su workspace.
SIN_SKILLS_DEL_CEREBRO = ("openclaw",)
RAIZ = "{{RAIZ}}"
#: El Python que corre los hooks y el MCP: se fija al instalar con el de Workspace (sesion._fijar_raiz). Un
#: `python3` escrito tal cual no existe en Windows (el instalador de python.org no lo crea).
PY = "{{PY}}"
#: La raíz del Workspace que instaló el paquete (sesion._fijar_raiz). Solo la usa el plugin de OpenClaw: sus avisos
#: y su MCP los abre el gateway, que no hereda WORKSPACE_ROOT (openclaw_gateway._clean_env).
WS = "{{WS}}"
#: El nombre que le da OpenClaw a las herramientas del servidor MCP del plugin: <servidor>__<herramienta>; y el
#: argumento que el aviso before_tool_call le suma a cada una con la clave de la sesión (lo que el servidor no sabe:
#: el gateway lo abre por sesión, sin decirle de cuál).
CLAVE_SESION_OPENCLAW = "_workspace_sesion"
#: Cota del hook si el momento no tiene listeners de hoy.
_TOPE = 10
#: Eventos del bus de OpenCode (ctx.event.subscribe); el resto son hooks
#: ctx.<dominio>.hook(<nombre>) según su documentación de plugins V2.
#: Los eventos de su servidor (ctx.event.subscribe); los demás nombres de su ficha son hooks (ctx.<dominio>.hook).
EVENTOS_OPENCODE = ("session.created", "session.idle", "session.execution.succeeded", "permission.asked")
#: Lo que nunca puede salir en un paquete: rutas de una máquina.
_RUTA_ABS = re.compile(r"(/Users/|/home/|[A-Za-z]:\\\\|/private/|/tmp/)")


def _version():
    try:
        with open(os.path.join(RAIZ_REPO, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip() or "0.0.0"
    except OSError:
        return "0.0.0"


def _manifiesto():
    with open(os.path.join(FUENTE, "workspace.json"), encoding="utf-8") as fh:
        return json.load(fh)


def _json(ruta, data):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")


def _texto(ruta, texto):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    with open(ruta, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(texto)


def _copiar_comun(dst):
    """skills/ y lanzador/ de la fuente, sin cachés."""
    ign = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")
    for sub in ("skills", "lanzador"):
        shutil.copytree(os.path.join(FUENTE, sub), os.path.join(dst, sub), ignore=ign)


def tope(momento):
    """Segundos para el hook: la suma de los listeners de hoy de su evento N9 (+ el
    tablero al abrir, + post_tool_write), como install.build_hooks, + arranque."""
    import events
    n9 = {m["nombre"]: m["n9"] for m in contrato.momentos()["momentos"]}.get(momento)
    if not n9:
        return _TOPE
    evs = [n9] + (["post_tool_write"] if momento == "post_tool" else [])
    total = sum(int(l.get("timeout") or 10) for e in evs for l in events.listeners_for(e))
    if momento == "session_start":
        total += 10
    return (total or _TOPE) + 5


def comando(manif, raiz, destino, momento):
    """El comando fijo de un hook: igual para todos los momentos salvo sus 2 argumentos."""
    return '"%s" "%s/%s" %s %s' % (PY, raiz, manif["lanzador_hook"], destino, momento)


def _raiz_de(ficha):
    var = ficha["paquete"]["hooks"]["raiz_var"]
    return "${%s}" % var if var else RAIZ


def _mcp(manif, raiz):
    return {"mcpServers": {manif["servidor_mcp"]: {
        "command": PY, "args": ["%s/%s" % (raiz, manif["lanzador_mcp"])]}}}


def _con_herramienta(momento):
    return momento in ("pre_tool", "post_tool", "permission_request")


# ── dialectos de hooks ─────────────────────────────────────────────────────
def hooks_claude(manif, ficha, destino):
    """{"hooks": {Evento: [{matcher?, hooks: [{type, command, timeout}]}]}} — Claude
    Code y los que copian su forma (Codex, Copilot)."""
    raiz, out = _raiz_de(ficha), {}
    for momento in contrato.nombres_momentos():
        evs = ficha["momentos"][momento]["eventos"]
        if not evs:
            continue
        grupo = {"hooks": [{"type": "command", "timeout": tope(momento),
                            "command": comando(manif, raiz, destino, momento)}]}
        if _con_herramienta(momento):
            grupo["matcher"] = "*"
        out.setdefault(evs[0], []).append(grupo)
    return {"hooks": out}


def hooks_cursor(manif, ficha, destino):
    """hooks.json de Cursor: {"version": 1, "hooks": {evento: [{type, command, timeout}]}}."""
    raiz, out = _raiz_de(ficha), {}
    for momento in contrato.nombres_momentos():
        evs = ficha["momentos"][momento]["eventos"]
        if evs and evs[0] not in out:
            out[evs[0]] = [{"type": "command", "timeout": tope(momento),
                            "command": comando(manif, raiz, destino, momento)}]
    return {"version": 1, "hooks": out}


def perfil_kiro(manif, ficha, destino):
    """Perfil del agente `workspace` de Kiro V3: hooks en línea, MCP y skills."""
    raiz, hooks = _raiz_de(ficha), []
    for momento in contrato.nombres_momentos():
        evs = ficha["momentos"][momento]["eventos"]
        if not evs:
            continue
        h = {"name": "workspace-" + momento, "trigger": evs[0], "timeout": tope(momento),
             "action": {"type": "command", "command": comando(manif, raiz, destino, momento)}}
        if _con_herramienta(momento):
            h["matcher"] = "*"
        hooks.append(h)
    return {"name": "workspace", "description": manif["descripcion"], "hooks": hooks,
            "mcpServers": _mcp(manif, raiz)["mcpServers"],
            "resources": ["skill://%s/skills/**/SKILL.md" % raiz]}


def hooks_hermes(manif, ficha, destino):
    """Bloque `hooks:` del config.yaml del perfil de Hermes (YAML a mano: sin deps)."""
    raiz = _raiz_de(ficha)
    filas = ["# Hooks de Workspace para el perfil de Hermes (generado; no editar).", "hooks:"]
    vistos = set()
    for momento in contrato.nombres_momentos():
        evs = ficha["momentos"][momento]["eventos"]
        if not evs or evs[0] in vistos:
            continue
        vistos.add(evs[0])
        filas += ["  %s:" % json.dumps(evs[0]),
                  "    - command: %s" % json.dumps(comando(manif, raiz, destino, momento)),
                  "      timeout: %d" % tope(momento)]
    return "\n".join(filas) + "\n"


#: Antigravity (hooks5, 18-nov): su `hooks.json` (el del proyecto, `<workspace>/.agents/hooks.json` según su
#: changelog, y el de sus plugins) NO es el de Claude Code. Lo dice su lector de plugins (`agy plugin validate`,
#: 1.5.11): arriba van NOMBRES de hook, cada uno {Evento: [entradas]}; la forma de Claude ({"hooks": {…}}) «loads
#: as a single hook named `hooks`» y «The loader skips this whole file» (por eso el probador real 3 no vio nada).
#: Los eventos que acepta: los de abajo. Los de herramienta van en grupos {matcher, hooks: [...]}.
EVENTOS_AGY = ("SessionStart", "PreInvocation", "PostInvocation", "Stop", "PreToolUse", "PostToolUse")
AGY_NOMBRE = "workspace"
#: Dónde va, dentro del formato del paquete del motor (el de Claude, el que importa agy), con su plugin.json.
AGY_RUTA = "antigravity"


def hooks_antigravity(manif, ficha, destino):
    """hooks.json de Antigravity: {"workspace": {Evento: [entradas]}}. Sin `timeout`: su unidad no está
    documentada (la de Claude son segundos), y con el suyo de fábrica el lanzador sobra."""
    out = {}
    for momento in contrato.nombres_momentos():
        evs = ficha["momentos"][momento]["eventos"]
        if not evs or evs[0] in out:
            continue
        h = {"type": "command", "command": comando(manif, RAIZ, destino, momento)}
        out[evs[0]] = [{"matcher": "*", "hooks": [h]}] if _con_herramienta(momento) else [h]
    return {AGY_NOMBRE: out}


_INDEX_JS = """// Workspace · plugin de OpenCode (V2). Generado por arquitectura/generar.py: no editar.
// Cada momento llama al lanzador fijo del paquete con el evento en JSON por stdin. La forma de la API es la de su
// documentación de plugins de servidor (opencode.ai/docs/build/plugins/server): ctx.<dominio>.hook(nombre,
// (evento) => …) y ctx.event.subscribe({ types }), un iterable asíncrono. Los campos que llegan (sessionID,
// prompt.text, tool/input, el data de cada evento) los vio la caja negra (v2.1.4, 19-nov).
import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const RAIZ = dirname(fileURLToPath(import.meta.url));
const LANZADOR = join(RAIZ, "lanzador", "hook.py");
const HOOKS = %(hooks)s;
const EVENTOS = %(eventos)s;
// La respuesta del agente que cierra el turno: su último session.text.ended en esa conversación (el evento del
// final del turno no la trae). Se olvida al empezar el siguiente.
const TEXTO = "session.text.ended";
const EMPIEZA = "session.execution.started";

function lanzar(momento, datos) {
  try {
    const r = spawnSync(%(python)s, [LANZADOR, "opencode", momento], {
      input: JSON.stringify(datos ?? {}), encoding: "utf8", timeout: 10000,
    });
    return { salida: r.stdout || "", codigo: r.status, motivo: (r.stderr || "").trim() };
  } catch {
    return { salida: "", codigo: 0, motivo: "" };
  }
}

// En los nombres que lee el traductor del lanzador (session_id, prompt, tool): OpenCode los llama sessionID,
// prompt.text y, en un permiso, action.
function plano(evento) {
  const d = Object.assign({}, evento ?? {});
  if (typeof d.sessionID === "string" && !d.session_id) d.session_id = d.sessionID;
  if (d.prompt && typeof d.prompt === "object") d.prompt = typeof d.prompt.text === "string" ? d.prompt.text : "";
  if (!d.tool && typeof d.action === "string") d.tool = d.action;
  return d;
}

async function escuchar(flujo) {
  const ultimo = {};
  try {
    for await (const ev of flujo) {
      const datos = plano(ev?.data);
      const sid = datos.session_id || "";
      if (ev?.type === TEXTO) {
        if (typeof datos.text === "string") ultimo[sid] = datos.text;
        continue;
      }
      if (ev?.type === EMPIEZA) delete ultimo[sid];
      const momento = EVENTOS[ev?.type];
      if (!momento) continue;
      if (momento === "turn_end" && typeof ultimo[sid] === "string") {
        datos.last_assistant_message = ultimo[sid];
        delete ultimo[sid];
      }
      lanzar(momento, datos);
    }
  } catch {
    // el servidor se apaga: no hay más eventos
  }
}

export default {
  id: "workspace",
  setup(ctx) {
    for (const [nombre, momento] of Object.entries(HOOKS)) {
      const [dominio, ...resto] = nombre.split(".");
      ctx[dominio]?.hook?.(resto.join("."), (evento, salida) => {
        // V2 trae la entrada de la herramienta en evento.input; la forma de antes, en el segundo argumento (args)
        const r = lanzar(momento, plano(Object.assign({}, evento, salida && salida.args ? { args: salida.args } : {})));
        // F7: lo prohibido (leer llaves o secretos) se niega antes de la herramienta: el lanzador sale con 2
        if (momento === "pre_tool" && r.codigo === 2) throw new Error(r.motivo || "Workspace no lo deja.");
      });
    }
    const flujo = ctx.event?.subscribe?.({ types: [...Object.keys(EVENTOS), TEXTO, EMPIEZA] });
    if (flujo && typeof flujo[Symbol.asyncIterator] === "function") void escuchar(flujo);
  },
};
"""


def plugin_opencode(manif, ficha):
    hooks, eventos = {}, {}
    for momento in contrato.nombres_momentos():
        evs = ficha["momentos"][momento]["eventos"][:1]   # uno por momento, como los demás
        for ev in evs:
            (eventos if ev in EVENTOS_OPENCODE else hooks).setdefault(ev, momento)
    return _INDEX_JS % {"hooks": json.dumps(hooks, indent=2, sort_keys=True),
                        "eventos": json.dumps(eventos, indent=2, sort_keys=True),
                        "python": json.dumps(PY)}


_INDEX_OPENCLAW = """// Workspace · plugin nativo de OpenClaw. Generado por arquitectura/generar.py: no editar.
// Sus avisos tipados (api.on, docs/plugins/hooks.md) llaman al lanzador fijo del paquete con el evento en JSON por
// stdin, como en los demás motores. El gateway lo carga para TODOS los agentes de su perfil: cada aviso lleva la
// clave de su sesión (ctx.sessionKey) y Workspace halla la pestaña con ella. Antes de cada herramienta del servidor
// MCP de Workspace le suma esa clave (el servidor la abre el gateway por sesión, sin decirle de cuál).
import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const HOOKS = %(hooks)s;
const PY = %(python)s;
const WS = %(ws)s;
const SERVIDOR = %(servidor)s;
const CLAVE_SESION = %(clave)s;
const TOPE_MS = 12000;

function python() {
  if (existsSync(PY)) return PY;
  return process.platform === "win32" ? "python" : "python3";
}

function deWorkspace(clave) {
  return /^agent:[^:]+:ws-/.test(String(clave || ""));
}

// El lanzador, sin frenar al gateway (asíncrono). Falla abierto: si no contesta a tiempo, sigue.
function lanzar(raiz, momento, datos) {
  return new Promise((resolve) => {
    let salida = "", motivo = "", hecho = false;
    const fin = (codigo) => {
      if (!hecho) { hecho = true; resolve({ codigo, salida, motivo: motivo.trim() }); }
    };
    try {
      const env = Object.assign({}, process.env);
      if (existsSync(join(WS, "arquitectura", "registro.py"))) env.WORKSPACE_ROOT = WS;
      const p = spawn(python(), [join(raiz, "lanzador", "hook.py"), "openclaw", momento],
                      { stdio: ["pipe", "pipe", "pipe"], windowsHide: true, env });
      const reloj = setTimeout(() => { try { p.kill(); } catch {} fin(0); }, TOPE_MS);
      p.stdout.on("data", (d) => { salida += d; });
      p.stderr.on("data", (d) => { motivo += d; });
      p.on("error", () => { clearTimeout(reloj); fin(0); });
      p.on("close", (c) => { clearTimeout(reloj); fin(c); });
      p.stdin.on("error", () => {});
      p.stdin.end(JSON.stringify(datos || {}));
    } catch {
      fin(0);
    }
  });
}

function texto(c) {
  if (typeof c === "string") return c;
  if (Array.isArray(c)) return c.map((x) => (x && typeof x.text === "string" ? x.text : "")).join("");
  return "";
}

function ultimaRespuesta(mensajes) {
  const ms = Array.isArray(mensajes) ? mensajes : [];
  for (let i = ms.length - 1; i >= 0; i--) {
    const m = ms[i];
    if (m && m.role === "assistant") {
      const t = texto(m.content);
      if (t) return t.slice(-4000);
    }
  }
  return "";
}

// Lo que el lanzador entiende (traductor.py): el número de la conversación es la clave de la sesión.
function datos(evento, ev, ctx) {
  ev = ev || {};
  ctx = ctx || {};
  const d = { hook_event_name: evento, session_id: ctx.sessionKey || "", agent_id: ctx.agentId || "",
              cwd: ctx.workspaceDir || "" };
  if (evento === "before_prompt_build") d.prompt = String(ev.prompt || "").slice(0, 4000);
  if (evento === "before_tool_call") { d.tool_name = ev.toolName || ""; d.tool_input = ev.params || {}; }
  if (evento === "after_tool_call") {
    d.tool_name = ev.toolName || "";
    if (ev.error) d.error = String(ev.error).slice(0, 300);
  }
  if (evento === "agent_end") d.last_assistant_message = ultimaRespuesta(ev.messages);
  if (evento === "session_end") d.reason = ev.reason || "";
  return d;
}

export default {
  id: %(id)s,
  name: %(nombre)s,
  description: %(descripcion)s,
  register(api) {
    const raiz = (api && api.rootDir) || dirname(fileURLToPath(import.meta.url));
    for (const [evento, momento] of Object.entries(HOOKS)) {
      api.on(evento, async (ev, ctx) => {
        const clave = (ctx && ctx.sessionKey) || "";
        let params;
        if (evento === "before_tool_call" && clave && String((ev && ev.toolName) || "").startsWith(SERVIDOR + "__")) {
          params = Object.assign({}, (ev && ev.params) || {}, { [CLAVE_SESION]: clave });
        }
        // lo prohibido se mira en todas las sesiones; lo demás, solo en las que abrió Workspace
        if (momento !== "pre_tool" && !deWorkspace(clave)) return undefined;
        const r = await lanzar(raiz, momento, datos(evento, ev, ctx));
        // solo la negativa del lanzador (sale con 2 y su motivo empieza con «Workspace»): Python también sale con 2
        // si no encuentra el archivo, y eso no puede frenar una herramienta
        if (momento === "pre_tool" && r.codigo === 2 && /^Workspace/.test(r.motivo)) {
          return { block: true, blockReason: r.motivo };
        }
        return params ? { params } : undefined;
      });
    }
  },
};
"""


def plugin_openclaw(manif, ficha):
    """{archivo: contenido} del plugin nativo de OpenClaw: manifiesto (con el servidor MCP y las skills), package.json
    e index.js con los avisos tipados de la ficha (todos los eventos de cada momento: compact son dos)."""
    hooks = {}
    for momento in contrato.nombres_momentos():
        m = ficha["momentos"][momento]
        if m.get("estado") != "si":                    # los «servidor» van por el gateway, no por este plugin
            continue
        for ev in m["eventos"]:
            hooks.setdefault(ev, momento)
    servidor = manif["servidor_mcp"]
    manifiesto = {
        "id": manif["nombre"], "name": "Workspace", "description": manif["descripcion"],
        "activation": {"onStartup": True},
        "configSchema": {"type": "object", "additionalProperties": False},
        "skills": ["./skills"],
        "mcpServers": {servidor: {"transport": "stdio", "command": PY, "args": ["./" + manif["lanzador_mcp"]],
                                  "env": {"WORKSPACE_ROOT": WS, "WORKSPACE_ENGINE": "openclaw"}}},
    }
    index = _INDEX_OPENCLAW % {
        "hooks": json.dumps(hooks, indent=2, sort_keys=True), "python": json.dumps(PY), "ws": json.dumps(WS),
        "servidor": json.dumps(servidor), "clave": json.dumps(CLAVE_SESION_OPENCLAW),
        "id": json.dumps(manif["nombre"]), "nombre": json.dumps("Workspace"),
        "descripcion": json.dumps(manif["descripcion"], ensure_ascii=False)}
    return manifiesto, index


_DIALECTOS = {"claude": hooks_claude, "cursor": hooks_cursor, "kiro": perfil_kiro,
              "hermes": hooks_hermes}


# ── los 4 formatos ─────────────────────────────────────────────────────────
def armar(destino, fichas_dir=None, version=None, cerebro=None):
    """Arma los 4 formatos en `destino` (que debe estar vacío o no existir).
    Devuelve {formato: carpeta}. F7: con `cerebro`, cada formato trae también sus skills
    (arquitectura/skills_cerebro: la vista plana skills/<nombre>/ con el sello de Workspace)."""
    if os.path.isdir(destino) and os.listdir(destino):
        raise ValueError("el destino no está vacío: %s" % destino)
    manif, fs = _manifiesto(), contrato.fichas(fichas_dir)
    version = version or _version()
    meta = {"name": manif["nombre"], "version": version, "description": manif["descripcion"]}
    out = {f: os.path.join(destino, f) for f in FORMATOS}

    # 1 · plugin de Claude Code (los momentos y eventos de la ficha de claude-code)
    d = out["claude"]
    _copiar_comun(d)
    _json(os.path.join(d, ".claude-plugin", "plugin.json"),
          dict(meta, author={"name": manif["autor"]}))
    cc = fs["claude-code"]
    _json(os.path.join(d, cc["paquete"]["hooks"]["ruta"]), hooks_claude(manif, cc, "claude"))
    _json(os.path.join(d, ".mcp.json"), _mcp(manif, _raiz_de(cc)))
    # hooks5 · los hooks de Antigravity en SU forma (los del proyecto por sesión: arquitectura/sesion), con un
    # plugin.json para que su lector de plugins (`agy plugin validate`) los revise tal cual (el probador lo hace)
    if "antigravity" in fs:
        _json(os.path.join(d, AGY_RUTA, "hooks.json"), hooks_antigravity(manif, fs["antigravity"], "antigravity"))
        _json(os.path.join(d, AGY_RUTA, "plugin.json"), meta)

    # 2 · Agent Plugins 1.0 + los hooks de cada motor que lo usa
    d = out["agent-plugins"]
    _copiar_comun(d)
    _json(os.path.join(d, "plugin.json"), meta)
    _json(os.path.join(d, "mcp.json"), _mcp(manif, RAIZ))
    for motor, f in fs.items():
        if f["paquete"]["formato"] != "agent-plugins":
            continue
        h = f["paquete"]["hooks"]
        hecho = _DIALECTOS[h["dialecto"]](manif, f, motor)
        ruta = os.path.join(d, h["ruta"])
        if isinstance(hecho, str):
            _texto(ruta, hecho)
        else:
            _json(ruta, hecho)

    # 3 · plugin JS de OpenCode
    d = out["opencode"]
    _copiar_comun(d)
    _json(os.path.join(d, "package.json"),
          {"name": "workspace-opencode", "version": version, "private": True,
           "type": "module", "main": "index.js", "description": manif["descripcion"]})
    _texto(os.path.join(d, "index.js"), plugin_opencode(manif, fs["opencode"]))

    # 4 · plugin nativo de OpenClaw (su manifiesto lleva el servidor MCP y las skills; los avisos, en index.js)
    d = out["openclaw"]
    _copiar_comun(d)
    manifiesto, index = plugin_openclaw(manif, fs["openclaw"])
    _json(os.path.join(d, "openclaw.plugin.json"), dict(manifiesto, version=version))
    _json(os.path.join(d, "package.json"),
          {"name": "workspace-openclaw", "version": version, "private": True, "type": "module",
           "description": manif["descripcion"], "openclaw": {"extensions": ["./index.js"]}})
    _texto(os.path.join(d, "index.js"), index)

    # F7 · las skills del cerebro en el menú / de cada motor (las del paquete se quedan)
    if cerebro:
        from arquitectura import skills_cerebro
        for f in FORMATOS:
            if f not in SIN_SKILLS_DEL_CEREBRO:
                skills_cerebro.escribir(cerebro, os.path.join(out[f], "skills"))
    return out


# ── validar lo armado ──────────────────────────────────────────────────────
def _leer_json(ruta, errs):
    try:
        with open(ruta, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as e:
        errs.append("%s: %s" % (ruta, e))
        return None


def _skills(d, errs):
    base = os.path.join(d, "skills")
    nombres = sorted(os.listdir(base)) if os.path.isdir(base) else []
    if not nombres:
        errs.append("%s: sin skills" % d)
    for n in nombres:
        try:
            with open(os.path.join(base, n, "SKILL.md"), encoding="utf-8") as fh:
                texto = fh.read()
        except OSError:
            errs.append("%s/skills/%s: sin SKILL.md" % (d, n))
            continue
        m = re.match(r"^---\n(.*?)\n---\n", texto, re.S)
        campos = dict(re.findall(r"^(\w[\w-]*):\s*(.+)$", m.group(1), re.M)) if m else {}
        if campos.get("name") != n or not campos.get("description"):
            errs.append("%s/skills/%s: frontmatter sin name = carpeta o sin description" % (d, n))


def _comandos(hooks_cmds, ficha_eventos, nombre, errs, eventos_usados):
    for ev in eventos_usados:
        if ev not in ficha_eventos:
            errs.append("%s: %r no es un evento oficial de su ficha" % (nombre, ev))
    for c in hooks_cmds:
        if "lanzador/hook.py" not in c:
            errs.append("%s: un hook no llama al lanzador fijo: %s" % (nombre, c))


def _eventos_ficha(f):
    return {e for m in f["momentos"].values() for e in m["eventos"]}


def _validar_agy(ruta, ficha, errs):
    """El hooks.json de Antigravity con la forma que lee su cargador (ver hooks_antigravity): un solo nombre arriba
    (nunca «hooks», la forma de Claude), eventos suyos, y en los de herramienta grupos {matcher, hooks}."""
    etiqueta = "claude/%s/hooks.json" % AGY_RUTA
    data = _leer_json(ruta, errs)
    if data is None:
        return
    if not isinstance(data, dict) or list(data) != [AGY_NOMBRE]:
        errs.append("%s: arriba va solo el nombre %r (la forma de Claude, con «hooks», agy la salta entera)"
                    % (etiqueta, AGY_NOMBRE))
        return
    cmds = []
    for ev, entradas in data[AGY_NOMBRE].items():
        if ev not in EVENTOS_AGY:
            errs.append("%s: %r no es un evento de agy" % (etiqueta, ev))
        for e in entradas if isinstance(entradas, list) else [None]:
            if not isinstance(e, dict):
                errs.append("%s: %s con una entrada que no es objeto" % (etiqueta, ev))
            elif ev in ("PreToolUse", "PostToolUse"):
                if not isinstance(e.get("hooks"), list) or "command" in e:
                    errs.append("%s: %s va en grupos {matcher, hooks: [...]}" % (etiqueta, ev))
                else:
                    cmds += [h.get("command", "") for h in e["hooks"] if isinstance(h, dict)]
            elif "command" not in e:
                errs.append("%s: %s sin command (agy salta el archivo entero)" % (etiqueta, ev))
            else:
                cmds.append(e["command"])
    if not cmds:
        errs.append("%s: sin hooks" % etiqueta)
    _comandos(cmds, _eventos_ficha(ficha), etiqueta, errs, data[AGY_NOMBRE])


def _validar_openclaw(d, ficha, node, errs):
    """El plugin nativo de OpenClaw: el manifiesto que lee su cargador (id, configSchema, skills, el servidor MCP que
    abre el lanzador del paquete), su package.json con la entrada, y que index.js registra solo eventos de su ficha."""
    if ficha is None or not os.path.isdir(d):
        return
    m = _leer_json(os.path.join(d, "openclaw.plugin.json"), errs) or {}
    if m.get("id") != "workspace" or not isinstance(m.get("configSchema"), dict):
        errs.append("openclaw: openclaw.plugin.json sin id workspace o sin configSchema")
    srv = (m.get("mcpServers") or {}).get("workspace") or {}
    if srv.get("transport") != "stdio" or "lanzador/mcp.py" not in " ".join(srv.get("args") or []):
        errs.append("openclaw: el manifiesto no abre el servidor workspace con lanzador/mcp.py")
    if m.get("skills") != ["./skills"]:
        errs.append("openclaw: el manifiesto no declara sus skills (./skills)")
    pk = _leer_json(os.path.join(d, "package.json"), errs) or {}
    if pk.get("type") != "module" or (pk.get("openclaw") or {}).get("extensions") != ["./index.js"]:
        errs.append("openclaw: package.json sin type module o sin openclaw.extensions [./index.js]")
    try:
        with open(os.path.join(d, "index.js"), encoding="utf-8") as fh:
            js = fh.read()
    except OSError:
        errs.append("openclaw: falta index.js")
        return
    hm = re.search(r"^const HOOKS = (\{.*?\});$", js, re.M | re.S)
    evs = list(json.loads(hm.group(1))) if hm else []
    if not evs:
        errs.append("openclaw/index.js: sin avisos")
    _comandos(["lanzador/hook.py"] if "\"lanzador\", \"hook.py\"" in js else [""], _eventos_ficha(ficha),
              "openclaw/index.js", errs, evs)
    if node:
        r = subprocess.run([node, "--check", os.path.join(d, "index.js")],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        if r.returncode:
            errs.append("openclaw/index.js: %s" % r.stdout.decode("utf-8", "replace")[:300])


def validar(destino, fichas_dir=None):
    """Errores de los 4 formatos armados en `destino` (lista vacía = válidos)."""
    errs, fs = [], contrato.fichas(fichas_dir)
    for f in FORMATOS:
        d = os.path.join(destino, f)
        if not os.path.isdir(d):
            errs.append("falta el formato %s" % f)
            continue
        _skills(d, errs)
        for lz in ("hook.py", "mcp.py", "comun.py"):
            if not os.path.isfile(os.path.join(d, "lanzador", lz)):
                errs.append("%s: falta lanzador/%s" % (f, lz))

    d = os.path.join(destino, "claude")
    pj = _leer_json(os.path.join(d, ".claude-plugin", "plugin.json"), errs) or {}
    if not re.match(r"^[a-z0-9][a-z0-9-]*$", str(pj.get("name", ""))) or not pj.get("version"):
        errs.append("claude: plugin.json sin name en kebab-case o sin version")
    hj = _leer_json(os.path.join(d, "hooks", "hooks.json"), errs) or {}
    grupos = hj.get("hooks", {})
    cmds = [h.get("command", "") for gs in grupos.values() for g in gs for h in g.get("hooks", [])
            if h.get("type") == "command"]
    _comandos(cmds, _eventos_ficha(fs["claude-code"]), "claude/hooks.json", errs, grupos)
    if len(cmds) != sum(len(g.get("hooks", [])) for gs in grupos.values() for g in gs):
        errs.append("claude/hooks.json: un hook sin type command")
    mj = _leer_json(os.path.join(d, ".mcp.json"), errs) or {}
    if "workspace" not in mj.get("mcpServers", {}):
        errs.append("claude/.mcp.json: sin el servidor workspace")
    if "antigravity" in fs:
        _validar_agy(os.path.join(d, AGY_RUTA, "hooks.json"), fs["antigravity"], errs)

    d = os.path.join(destino, "agent-plugins")
    ap = _leer_json(os.path.join(d, "plugin.json"), errs) or {}
    if ap.get("name") != pj.get("name") or not ap.get("version"):
        errs.append("agent-plugins: plugin.json sin el mismo name o sin version")
    if "workspace" not in (_leer_json(os.path.join(d, "mcp.json"), errs) or {}).get("mcpServers", {}):
        errs.append("agent-plugins/mcp.json: sin el servidor workspace")
    for motor, f in fs.items():
        if f["paquete"]["formato"] != "agent-plugins":
            continue
        h, ruta = f["paquete"]["hooks"], os.path.join(d, f["paquete"]["hooks"]["ruta"])
        etiqueta = "agent-plugins/%s" % h["ruta"]
        if h["dialecto"] == "hermes":
            try:
                with open(ruta, encoding="utf-8") as fh:
                    yaml = fh.read()
            except OSError:
                errs.append("%s: falta" % etiqueta)
                continue
            evs = [json.loads(x) for x in re.findall(r'^  ("[^"]+"):$', yaml, re.M)]
            cmds = [json.loads(x) for x in re.findall(r'^    - command: (".*")$', yaml, re.M)]
            if not yaml.startswith("#") or "\nhooks:\n" not in yaml or len(evs) != len(cmds):
                errs.append("%s: YAML con forma inesperada" % etiqueta)
        else:
            data = _leer_json(ruta, errs)
            if data is None:
                continue
            if h["dialecto"] == "kiro":
                evs = [x.get("trigger") for x in data.get("hooks", [])]
                cmds = [x.get("action", {}).get("command", "") for x in data.get("hooks", [])]
            elif h["dialecto"] == "cursor":
                evs = list(data.get("hooks", {}))
                cmds = [x.get("command", "") for xs in data.get("hooks", {}).values() for x in xs]
                if data.get("version") != 1:
                    errs.append("%s: version distinta de 1" % etiqueta)
            else:
                evs = list(data.get("hooks", {}))
                cmds = [x.get("command", "") for gs in data.get("hooks", {}).values()
                        for g in gs for x in g.get("hooks", [])]
        if not cmds:
            errs.append("%s: sin hooks" % etiqueta)
        _comandos(cmds, _eventos_ficha(f), etiqueta, errs, evs)

    d = os.path.join(destino, "opencode")
    pk = _leer_json(os.path.join(d, "package.json"), errs) or {}
    if pk.get("type") != "module" or not os.path.isfile(os.path.join(d, str(pk.get("main")))):
        errs.append("opencode: package.json sin type module o sin su main")
    node = shutil.which("node")
    if node and os.path.isfile(os.path.join(d, "index.js")):
        r = subprocess.run([node, "--check", os.path.join(d, "index.js")],
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=30)
        if r.returncode:
            errs.append("opencode/index.js: %s" % r.stdout.decode("utf-8", "replace")[:300])

    _validar_openclaw(os.path.join(destino, "openclaw"), fs.get("openclaw"), node, errs)

    from arquitectura import skills_cerebro
    for base, ds, archivos in os.walk(destino):
        # las skills del cerebro (F7) son del socio: su texto puede nombrar rutas suyas, no las del paquete
        ds[:] = [x for x in ds if not skills_cerebro.es_nuestra(os.path.join(base, x))]
        for a in archivos:
            ruta = os.path.join(base, a)
            if a == "sonda.json":
                errs.append("%s: un paquete nunca lleva la sonda" % ruta)
            if a.endswith((".json", ".js", ".py", ".yaml", ".md")):
                with open(ruta, encoding="utf-8") as fh:
                    if _RUTA_ABS.search(fh.read()):
                        errs.append("%s: lleva una ruta de la máquina" % os.path.relpath(ruta, destino))
    return errs


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("uso: python3 -m arquitectura.generar <destino>")
        return 2
    armar(argv[0])
    errs = validar(argv[0])
    for e in errs:
        print("✗ " + e)
    print("✓ %d formatos en %s" % (len(FORMATOS), argv[0]) if not errs else "✗ %d errores" % len(errs))
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
