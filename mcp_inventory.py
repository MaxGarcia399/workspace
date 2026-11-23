"""Read-only MCP inventory. Never launches engines, servers or keyring clients.

Only names, origin and status leave this module. Unsupported syntax is a
read error, never an empty configuration. A file with nothing in it (0 bytes
or only whitespace, as some engines leave their MCP file) IS an empty
configuration: 0 servers, not a read error. Python 3.9+, no required packages.
"""
import ast
from collections import Counter
import json
import os
from pathlib import Path
import re
import stat

import paths

ENGINES = (("claude-code", "Claude"), ("codex", "Codex"),
           ("antigravity", "Antigravity"), ("opencode", "OpenCode"),
           ("openclaw", "OpenClaw"), ("hermes", "Hermes"),
           ("kiro", "Kiro"), ("copilot", "Copilot"), ("cursor", "Cursor"))
LIMIT = 1024 * 1024
ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")


def label(value):
    text = str(value)
    if not re.fullmatch(r"[\w .-]{1,64}", text, re.ASCII):
        return "[hidden]"
    import secret_scan
    return "[hidden]" if secret_scan.scan_text(text) else text


def _parts(text, delimiter=","):
    """Split outside strings/brackets; also reject unbalanced input."""
    out, start, stack, quote, i = [], 0, [], "", 0
    while i < len(text):
        c = text[i]
        if quote:
            if c == "\\" and quote[0] == '"':
                i += 2
                continue
            if text.startswith(quote, i):
                i += len(quote)
                quote = ""
                continue
        elif c in "\"'":
            quote = c * 3 if text.startswith(c * 3, i) else c
            i += len(quote)
            continue
        elif c in "[{(":
            stack.append(c)
        elif c in "]})":
            if not stack or "[{("["]})".index(c)] != stack.pop():
                raise ValueError("syntax")
        elif c == delimiter and not stack:
            out.append(text[start:i].strip())
            start = i + 1
        i += 1
    if quote or stack:
        raise ValueError("syntax")
    return out + [text[start:].strip()]


def _uncomment(text, json_style=False):
    # Preserve string contents while removing comments; no regex over secrets.
    out, i = [], 0
    while i < len(text):
        if text[i] in "\"'":
            q = text[i] * 3 if text.startswith(text[i] * 3, i) else text[i]
            end = i + len(q)
            while end < len(text):
                if text[end] == "\\" and q[0] == '"':
                    end += 2
                elif text.startswith(q, end):
                    end += len(q)
                    break
                else:
                    end += 1
            else:
                raise ValueError("syntax")
            out.append(text[i:end])
            i = end
        elif (json_style and text.startswith("//", i)) or (not json_style and text[i] == "#"):
            end = text.find("\n", i)
            i = len(text) if end < 0 else end
        elif json_style and text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end < 0:
                raise ValueError("syntax")
            out.append(" ")
            i = end + 2
        else:
            out.append(text[i])
            i += 1
    return "".join(out)


def _unique(pairs):
    out = {}
    for key, value in pairs:
        if key in out:
            raise ValueError("duplicate")
        out[key] = value
    return out


def _json(text):
    text = _uncomment(text, True)
    # Restricted JSON5: comments, trailing commas, single quotes and bare keys.
    token = re.compile(r'''"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|[A-Za-z_$][\w$-]*|\s+|.''', re.S)
    tokens = token.findall(text)
    result = []
    for i, item in enumerate(tokens):
        if item.startswith("'"):
            item = json.dumps(ast.literal_eval(item))
        elif re.fullmatch(r"[A-Za-z_$][\w$-]*", item):
            following = next((tokens[j] for j in range(i + 1, len(tokens)) if not tokens[j].isspace()), "")
            if following == ":":
                item = json.dumps(item)
        if item == "," and next((tokens[j] for j in range(i + 1, len(tokens)) if not tokens[j].isspace()), "") in ("}", "]"):
            continue
        result.append(item)
    return json.loads("".join(result), object_pairs_hook=_unique)


def _toml_value(value):
    value = value.strip()
    if value.startswith("'" * 3) and value.endswith("'" * 3):
        return value[3:-3]
    if value.startswith("'") and value.endswith("'"):
        return value[1:-1]
    if value.startswith('"'):
        result = ast.literal_eval(value)
        if not isinstance(result, str):
            raise ValueError("syntax")
        return result
    if value.startswith("[") and value.endswith("]"):
        return [_toml_value(v) for v in _parts(value[1:-1]) if v]
    if value.startswith("{") and value.endswith("}"):
        pairs = []
        for item in _parts(value[1:-1]):
            if not item:
                continue
            pair = _parts(item, "=")
            if len(pair) != 2:
                raise ValueError("syntax")
            pairs.append((_toml_key(pair[0]), _toml_value(pair[1])))
        return _unique(pairs)
    if value in ("true", "false"):
        return value == "true"
    if re.fullmatch(r"[+-]?[0-9][0-9_.:+TZ-]*", value):
        return value
    raise ValueError("unsupported syntax")


def _toml_key(key):
    if key.startswith("'") and key.endswith("'"):
        return key[1:-1]
    if key.startswith('"'):
        value = ast.literal_eval(key)
        if isinstance(value, str):
            return value
    elif re.fullmatch(r"[A-Za-z0-9_-]+", key):
        return key
    raise ValueError("syntax")


def _toml(text):
    try:
        import tomllib
    except ImportError:
        pass
    else:
        return tomllib.loads(text)
    # Conservative fallback. No silent ignoring of unsupported assignments.
    out, current, pending = {}, None, ""
    current = out
    for raw in _uncomment(text).splitlines():
        line = (pending + "\n" + raw).strip() if pending else raw.strip()
        if not line:
            continue
        if line.startswith("[") and not pending:
            array = line.startswith("[[")
            tail = "]]" if array else "]"
            if not line.endswith(tail):
                raise ValueError("syntax")
            keys = [_toml_key(k) for k in _parts(line[2:-2] if array else line[1:-1], ".")]
            current = out
            for key in keys[:-1]:
                current = current.setdefault(key, {})
                if isinstance(current, list):
                    current = current[-1]
            if array:
                current.setdefault(keys[-1], []).append({})
                current = current[keys[-1]][-1]
            else:
                current = current.setdefault(keys[-1], {})
            continue
        try:
            pair = _parts(line, "=")
        except ValueError:
            pending = line
            continue
        if len(pair) != 2:
            raise ValueError("syntax")
        keys, value = [_toml_key(k) for k in _parts(pair[0], ".")], _toml_value(pair[1])
        target = current
        for part in keys[:-1]:
            target = target.setdefault(part, {})
        if keys[-1] in target:
            raise ValueError("duplicate")
        target[keys[-1]] = value
        pending = ""
    if pending:
        raise ValueError("syntax")
    return out


def _yaml(text):
    # Safe, restricted mappings/block lists; reject tags, anchors and blocks.
    out = {}
    stack = [(-1, out, None)]
    for raw in _uncomment(text).splitlines():
        if not raw.strip() or raw.strip() in ("---", "..."):
            continue
        if "\t" in raw or raw.lstrip().startswith(("!", "&", "*")):
            raise ValueError("unsupported syntax")
        indent, line = len(raw) - len(raw.lstrip()), raw.strip()
        while len(stack) > 1 and indent <= stack[-1][0]:
            stack.pop()
        current = stack[-1][1]
        if line.startswith("- "):
            if len(stack) == 1 or stack[-1][2] == "mcp_servers":
                raise ValueError("unsupported syntax")
            # Contents of command arguments do not affect inventory discovery.
            continue
        pair = _parts(line, ":")
        # Unquoted URLs contain ':'; only the first colon is the mapping split.
        if len(pair) < 2:
            raise ValueError("syntax")
        key, value = pair[0], ":".join(pair[1:]).strip()
        key = _toml_key(key)
        if key in current:
            raise ValueError("duplicate")
        if not value:
            current[key] = {}
            stack.append((indent, current[key], key))
        elif value.startswith(("|", ">", "&", "*", "!")):
            raise ValueError("unsupported syntax")
        elif value.startswith(("{", "[")):
            try:
                current[key] = _json(value)
            except ValueError:
                # Flujo YAML sin comillas (Hermes: `cli: [hermes-cli]`): fuera de
                # mcp_servers (o en `args`) no cambia el inventario; lo demás no se adivina.
                if key != "args" and any(k == "mcp_servers" for _i, _d, k in stack):
                    raise
                current[key] = None
        else:
            current[key] = value[1:-1].replace("''", "'") if value.startswith("'") and value.endswith("'") else (ast.literal_eval(value) if value.startswith('"') else value)
    return out


def read(path, kind):
    try:
        if os.path.islink(path):
            return "unreadable", None
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0))
        with os.fdopen(fd, "rb") as stream:
            if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                return "unreadable", None
            raw = stream.read(LIMIT + 1)
        if len(raw) > LIMIT:
            return "unreadable", None
        text = raw.decode("utf-8-sig")
        if not text.strip():
            return "read", {}          # nothing configured: 0 servers (not «unreadable»)
        data = {"json": _json, "toml": _toml, "yaml": _yaml}[kind](text)
        if not isinstance(data, dict):
            raise ValueError("shape")
        return "read", data
    except FileNotFoundError:
        return "missing", None
    except Exception:
        # Never expose exception strings: parser errors may contain credentials.
        return "unreadable", None


def sources(home, projects=(), env=None):
    env = env or {}
    h = Path(home)
    hermes = Path(env.get("HERMES_HOME") or (Path(env.get("LOCALAPPDATA") or home) / "hermes" if os.name == "nt" else h / ".hermes"))
    if hermes.parent.name == "profiles":
        hermes = hermes.parent.parent
    specs = [
        ("claude-code", h / ".claude.json", "json", "mcpServers"),
        ("codex", Path(env.get("CODEX_HOME") or h / ".codex") / "config.toml", "toml", "mcp_servers"),
        ("antigravity", h / ".gemini/config/mcp_config.json", "json", "mcpServers"),
        ("opencode", Path(env.get("XDG_CONFIG_HOME") or h / ".config") / "opencode/opencode.json", "json", "mcp"),
        ("opencode", Path(env.get("XDG_CONFIG_HOME") or h / ".config") / "opencode/opencode.jsonc", "json", "mcp"),
        ("openclaw", Path(env.get("OPENCLAW_CONFIG_PATH") or h / ".openclaw/openclaw.json"), "json", "mcp.servers"),
        ("hermes", hermes / "config.yaml", "yaml", "mcp_servers"),
        ("kiro", h / ".kiro/settings/mcp.json", "json", "mcpServers"),
        ("kiro", h / ".kiro/agents/workspace.json", "json", "mcpServers"),
        ("copilot", Path(paths.state_dir(home)) / "copilot-mcp.json", "json", "mcpServers"),
        ("copilot", h / ".copilot/mcp-config.json", "json", "mcpServers"),
        ("cursor", h / ".cursor/mcp.json", "json", "mcpServers")]
    out = [(e, str(p.absolute()), kind, key, "profile" if "/.kiro/agents/" in str(p).replace("\\", "/") or p.name == "copilot-mcp.json" else "user") for e, p, kind, key in specs]
    profile = label(env.get("WORKSPACE_HERMES_PROFILE") or "workspace")
    oc = label(env.get("WORKSPACE_OPENCLAW_PROFILE") or "workspace")
    out += [("hermes", str((hermes / "profiles" / profile / "config.yaml").absolute()), "yaml", "mcp_servers", "profile"),
            ("openclaw", str((h / (".openclaw-" + oc) / "openclaw.json").absolute()), "json", "mcp.servers", "profile")]
    for project in projects:
        root = Path(project).absolute()
        for engine, relative, kind, key in (
            ("claude-code", ".mcp.json", "json", "mcpServers"),
            ("codex", ".codex/config.toml", "toml", "mcp_servers"),
            ("antigravity", ".agents/mcp_config.json", "json", "mcpServers"),
            ("opencode", "opencode.json", "json", "mcp"),
            ("opencode", "opencode.jsonc", "json", "mcp"),
            ("opencode", ".opencode/opencode.json", "json", "mcp"),
            ("kiro", ".kiro/settings/mcp.json", "json", "mcpServers"),
            ("kiro", ".kiro/agents/workspace.json", "json", "mcpServers"),
            ("copilot", ".mcp.json", "json", "mcpServers"),
            ("copilot", ".github/mcp.json", "json", "mcpServers"),
            ("cursor", ".cursor/mcp.json", "json", "mcpServers")):
            out.append((engine, str(root / relative), kind, key, "project"))
    return out


def _servers(data, key):
    for part in key.split("."):
        data = data.get(part, {})
        if not isinstance(data, dict):
            raise ValueError("shape")
    if key == "mcp" and "servers" in data:
        data = data["servers"]       # OpenCode v2; v1 is directly under mcp.
    if not isinstance(data, dict):
        raise ValueError("shape")
    return data


def _variables(entry):
    out = set()
    for key in ("env", "environment"):
        values = entry.get(key, {})
        if isinstance(values, dict):
            out.update(n for n in values if ENV_NAME.fullmatch(str(n)))
    inherited = entry.get("env_vars", [])
    if isinstance(inherited, list):
        out.update(n for n in inherited if isinstance(n, str) and ENV_NAME.fullmatch(n))
    # Include referenced names, never raw header values or literal tokens.
    for name in re.findall(r"\$\{(?:env:)?([A-Za-z_][A-Za-z0-9_]*)\}|\{env:([A-Za-z_][A-Za-z0-9_]*)\}", json.dumps(entry)):
        out.update(v for v in name if v and ENV_NAME.fullmatch(v))
    name = entry.get("bearer_token_env_var")
    if isinstance(name, str) and ENV_NAME.fullmatch(name):
        out.add(name)
    return sorted(name for name in out if label(name) == name)


def scan(home=None, projects=(), env=None):
    home = os.path.abspath(home or os.path.expanduser("~"))
    env = dict(os.environ if env is None else env)
    records, files = [], []
    for engine, path, kind, key, scope in sources(home, projects, env):
        status, data = read(path, kind)
        if status == "read":
            try:
                servers = _servers(data, key)
                if engine == "claude-code" and scope == "user":
                    for project in projects:
                        local = data.get("projects", {}).get(os.path.abspath(project), {})
                        for name, entry in _servers(local, key).items():
                            if not isinstance(entry, dict):
                                raise ValueError("shape")
                            records.append({"name": label(name), "engine": engine, "state": "manual",
                                            "path": path, "scope": "project", "project": os.path.abspath(project), "variables": _variables(entry)})
                for name, entry in servers.items():
                    if not isinstance(entry, dict):
                        raise ValueError("shape")
                    records.append({"name": label(name), "engine": engine, "state": "manual",
                                    "path": path, "scope": scope, "variables": _variables(entry)})
            except Exception:
                status = "unreadable"
        files.append({"engine": engine, "path": path, "scope": scope, "state": status})
    registry = os.path.join(paths.state_dir(home), "mcps.json")
    status, data = read(registry, "json")
    files.append({"engine": "workspace", "path": registry, "scope": "registry", "state": status})
    if status == "read":
        entries = data.get("servers")
        if not isinstance(entries, dict):
            files[-1]["state"] = "unreadable"
        else:
            for name, entry in entries.items():
                if not isinstance(entry, dict):
                    files[-1]["state"] = "unreadable"
                    continue
                # Registration does not establish assignment or native ownership.
                variables = entry.get("env", [])
                variables = [v for v in variables if isinstance(v, str) and ENV_NAME.fullmatch(v)] if isinstance(variables, list) else []
                records.append({"name": label(name), "engine": "workspace", "state": "registered",
                                "path": registry, "scope": "global" if entry.get("scope", "global") == "global" else "agents",
                                "agents": [label(a) for a in entry.get("scope", [])] if isinstance(entry.get("scope"), list) else [],
                                "variables": sorted(v for v in variables if label(v) == v),
                                "transport": entry.get("transport") if entry.get("transport") in ("sse", "http", "stdio") else "stdio"})
    return {"records": records, "files": files, "engines": ENGINES}


def cell(data, name, engine):
    direct = [r for r in data["records"] if r["name"] == name and r["engine"] == engine]
    errors = [r for r in data["files"] if r["engine"] in (engine, "workspace") and r["state"] == "unreadable"]
    registered = [r for r in data["records"] if r["name"] == name and r["state"] == "registered"]
    if direct:
        return "manual", direct + errors + registered
    if errors:
        return "unreadable", errors + registered
    if engine == "antigravity" and any(r.get("transport") == "sse" for r in registered):
        return "unsupported", registered
    if registered:
        return "registered", registered
    return "absent", []


def counts(data):
    names = {r["name"] for r in data["records"]}
    result = Counter(cell(data, name, engine)[0] for name in names for engine, _ in ENGINES)
    result["unreadable_files"] = sum(f["state"] == "unreadable" for f in data["files"])
    return dict(result)
