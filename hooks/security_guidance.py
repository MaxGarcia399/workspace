#!/usr/bin/env python3
"""WORKSPACE hook · PostToolUse — security guidance (N15).

Cuando Claude Code completa un tool de ESCRITURA (Write / Edit / NotebookEdit),
este hook escanea el contenido escrito en busca de ~25 clases de riesgo y
AÑADE una advertencia no-bloqueante al tool-result (lo que el modelo ve como
respuesta al tool).

PRINCIPIOS (del contrato N9 · engines/EVENTS.md):
- Observer puro: JAMÁS bloquea, JAMÁS revierte, JAMÁS modifica el archivo escrito.
- La advertencia es ADITIVA al tool-result: el modelo la lee y puede actuar.
- Falla-suave absoluta: stdin basura / archivo sin escanear / excepción → exit 0 siempre.
- No-ruido: solo patrones con contexto inequívoco de riesgo (anti falsos positivos).

Stdin JSON (PostToolUse de Claude Code):
  · tool_name    — "Write" | "Edit" | "NotebookEdit"
  · tool_input   — dict con los campos del tool (file_path + content/new_string/…)
  · tool_response — respuesta del motor (lo que el tool reportó)
  · cwd          — directorio de trabajo (cerebro)
  · session_id   — id de sesión (opcional)

Salida: si hay findings, imprime a stdout una línea JSON con
  {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                          "additionalContext": "<mensaje>"}}
Es el ÚNICO canal de PostToolUse que Claude Code entrega al modelo como guidance
no-bloqueante (additionalContext). El stdout plano / {"type":"text"} NO llega al
modelo — solo aparece en el debug log (verificado contra la doc oficial de hooks).

Kill-switch: WORKSPACE_NO_SECURITY_GUIDANCE=1 → omite todo (para tests o desactivación
temporal; el env SIEMPRE gana). Canal nuevo: `settings set hooks.security_guidance off`
(settings.py — falla-suave: sin settings, on-by-default como siempre).
Amputable (C10): borrar este archivo = la feature se apaga.

Cross-platform, stdlib (3.9+). Cero dependencias externas.
"""
import json
import os
import re
import sys

try:   # M1/B2 · Windows: UTF-8 en stdout/err — un hook capturado por Claude Code en
       # cp1252 reventaría al imprimir caracteres no-ASCII. No-op en Mac (UTF-8 default).
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# ── Kill-switch ───────────────────────────────────────────────────────────────
KILL_SWITCH = "WORKSPACE_NO_SECURITY_GUIDANCE"

# ── Herramienta: qué tools de escritura escaneamos ───────────────────────────
WRITE_TOOLS = frozenset({"Write", "Edit", "NotebookEdit"})

# ── Límite de bytes para el scan (no analizar archivos gigantes) ──────────────
MAX_SCAN_BYTES = 500_000

# ── Patrones de riesgo (N15) ─────────────────────────────────────────────────
# Cada entrada: (nombre_clase, patrón_compilado)
# Filosofía anti-FP:
#   · Requieren contexto inequívoco (no matchear construcciones legítimas comunes).
#   · Se anclan a palabras completas (\b) y a construcciones concretas.
#   · Priorizan precisión sobre recall.
_PATTERNS = tuple((name, re.compile(rx, re.IGNORECASE | re.MULTILINE))
                  for name, rx in (
    # 1. eval/exec con entrada del usuario
    ("eval_exec_input",
     r"\beval\s*\(\s*(?:input|request\.|sys\.stdin|os\.environ)"
     r"|\bexec\s*\(\s*(?:input|request\.|sys\.stdin|os\.environ)"),

    # 2. subprocess con shell=True
    ("subprocess_shell_true",
     r"\bsubprocess\.[a-z_]+\s*\([^)]{0,200}shell\s*=\s*True"),

    # 3. rm -rf en rutas peligrosas (raíz, home, variables de entorno)
    ("rm_rf_dangerous",
     r"rm\s+-(?:rf|fr)\b[^\n]{0,60}(?:/[^a-zA-Z]|~|\$(?:HOME|PWD|OLDPWD)|\$\{(?:HOME|PWD)\})"),

    # 4. Contraseñas / tokens / API keys hardcodeados en asignaciones
    ("hardcoded_secret",
     r"""(?:password|passwd|secret|api[_-]?key|api[_-]?secret|"""
     r"""access[_-]?token|auth[_-]?token|private[_-]?key|client[_-]?secret)"""
     r"""\s*=\s*['"][^'"]{6,}['"]"""),

    # 5. curl|wget piped to sh (instaladores remotos)
    ("curl_pipe_sh",
     r"\b(?:curl|wget)\b[^\n|]{0,200}\|\s*(?:sudo\s+)?(?:ba|z|da|fi)?sh\b"),

    # 6. pickle.load de fuentes no confiables
    ("pickle_load_unsafe",
     r"\bpickle\.load\s*\(\s*(?:open\s*\([^)]{0,100}(?:request|stdin|"
     r"input|argv|environ)|request\.|sys\.stdin|io\.BytesIO\s*\(\s*(?:"
     r"request|input|stdin))"),

    # 7. SQL via f-string o .format/.% (SQL injection)
    ("sql_injection",
     r"""f['"][^'"]{0,200}(?:SELECT|INSERT|UPDATE|DELETE|WHERE)[^'"]{0,200}['"]"""
     r"""|(?:SELECT|INSERT|UPDATE|DELETE|DROP|CREATE|ALTER)\b[^;'"]{0,200}"""
     r"""(?:['"]\s*%\s*(?:s|\()\s*\w|\s*\+\s*\w+|\.format\s*\()"""),

    # 8. verify=False / TLS deshabilitado
    ("tls_verify_false",
     r"\bverify\s*=\s*False\b"
     r"|\bssl_context\.check_hostname\s*=\s*False\b"
     r"|\bssl_context\.verify_mode\s*=\s*ssl\.CERT_NONE\b"),

    # 9. Bind en 0.0.0.0 (exposición a todas las interfaces)
    ("bind_all_interfaces",
     r"""(?:host|bind|listen)\s*=\s*['"]0\.0\.0\.0['"]"""
     r"""|\.bind\s*\(\s*['"]0\.0\.0\.0"""),

    # 10. os.system con variables (inyección de comandos)
    ("os_system_variable",
     r"\bos\.system\s*\(\s*(?:f['\"]|['\"]?\s*%|.*\+\s*(?:str\()?[a-zA-Z_][a-zA-Z0-9_]*)"),

    # 11. __import__ dinámico con entrada no confiable
    ("dynamic_import_input",
     r"\b__import__\s*\(\s*(?:request\.|input\s*\(|sys\.argv|os\.environ)"),

    # 12. yaml.load sin Loader explícito (yaml.safe_load y yaml.load(…, Loader=…) son seguros)
    ("yaml_load_unsafe",
     r"\byaml\.load\s*\((?![^)]*\bLoader\s*=)[^)]{0,200}\)"),

    # 13. tempfile sin creación segura (tmp_ prefix patterns sin mkstemp/mkdtemp)
    ("insecure_tempfile",
     r"""/tmp/[a-zA-Z0-9_.+-]+['\"]\s*(?:,|\))"""
     r"""|\bopen\s*\(\s*['\"]\/tmp\/[a-zA-Z0-9_.+-]+['\"]"""),

    # 14. chmod 777
    ("chmod_777",
     r"\bchmod\s+(?:0?777|a\+rwx)\b"
     r"|\bos\.chmod\s*\([^)]{0,100},\s*0o?777\b"),

    # 15. IPs hardcodeadas en código de producción (no en tests/config de red)
    ("hardcoded_ip_prod",
     r"""(?:host|server|endpoint|url|target)\s*=\s*['"]"""
     r"""(?!(?:127\.0\.0\.1|0\.0\.0\.0|localhost))"""
     r"""(?:(?:25[0-5]|2[0-4]\d|[01]?\d\d?)\.){3}"""
     r"""(?:25[0-5]|2[0-4]\d|[01]?\d\d?)['"]"""),

    # 16. base64 decode + exec
    ("base64_exec",
     r"\bbase64\b[^\n]{0,100}\|\s*(?:sudo\s+)?(?:ba|z)?sh\b"
     r"|\bbase64\.b64decode\s*\([^)]{0,200}\)\s*\)\s*\)"  # exec(compile(base64...
     r"|\bexec\s*\(\s*base64"),

    # 17. input() directo a eval
    ("input_to_eval",
     r"\beval\s*\(\s*input\s*\("),

    # 18. Path traversal en rutas construidas con input del usuario
    ("path_traversal",
     r"""os\.path\.join\s*\([^)]{0,100}(?:request\.|input\s*\(|sys\.argv|os\.environ)"""
     r"""|open\s*\(\s*(?:request\.|input\s*\(|sys\.argv\[)"""),

    # 19. HTTP en endpoints de autenticación/sesión
    ("http_auth_endpoint",
     r"""['\"]http://[^'"]{0,100}(?:login|auth|token|password|signin|oauth)[^'"]{0,50}['"]"""),

    # 20. debug=True en configuración de app
    ("debug_mode_true",
     r"\bdebug\s*=\s*True\b(?![^\n]*#[^\n]*test)"
     r"|\bapp\.run\s*\([^)]{0,200}\bdebug\s*=\s*True\b"),

    # 21. Deserialización insegura con marshal
    ("marshal_loads",
     r"\bmarshal\.loads\s*\("),

    # 22. Escritura a authorized_keys
    ("authorized_keys_write",
     r">>\s*[^\n]{0,60}\.ssh[/\\]authorized_keys\b"
     r"|open\s*\([^\)]{0,80}authorized_keys[^\)]{0,20},\s*['\"]a['\"]"),

    # 23. assert para seguridad (se elimina con -O)
    ("assert_security_check",
     r"\bassert\s+(?:user|auth|token|permission|is_admin|role|logged)"),

    # 24. Disable CSRF / security middleware
    ("csrf_disabled",
     r"'django\.middleware\.csrf\.CsrfViewMiddleware'\s*,?\s*#?\s*(?:disabled|removed|commented)"
     r"|CSRF_COOKIE_SECURE\s*=\s*False"
     r"|@csrf_exempt"),

    # 25. Expresión regular catastrófica (ReDoS)
    #     [rbfu]* — J1: el prefijo de string raw/bytes/f/unicode (`re.compile(r'…')`)
    #     iba ANTES de la comilla; sin él el patrón se escapaba justo los regex
    #     que MÁS se escriben como raw string. (re.IGNORECASE cubre R/B/F/U.)
    ("redos_pattern",
     r"""re\.compile\s*\(\s*[rbfu]*['"][^'"]{0,200}"""
     r"""(?:\([^)]*\+[^)]*\)\+|\([^)]*\*[^)]*\)\*|\(\.\*\)\+)"""),
))


def _extract_content(tool_name, tool_input):
    """Extrae el texto a escanear del tool_input según el tool.

    Write  → content
    Edit   → new_string (el texto que va a quedar escrito)
    NotebookEdit → source (celda nueva)
    """
    if not isinstance(tool_input, dict):
        return ""
    if tool_name == "Write":
        return str(tool_input.get("content", ""))
    if tool_name == "Edit":
        return str(tool_input.get("new_string", ""))
    if tool_name == "NotebookEdit":
        # new_source o source según la operación
        return str(tool_input.get("new_source", tool_input.get("source", "")))
    return ""


def _file_path(tool_input):
    """Ruta del archivo escrito (para incluirla en el mensaje)."""
    if not isinstance(tool_input, dict):
        return ""
    return str(tool_input.get("file_path", tool_input.get("path", "")))


def scan(text):
    """Escanea `text` y devuelve findings [{class, excerpt}].

    Solo clases distintas (primer match por clase, no inundar con repeticiones).
    Falla-suave: jamás levanta."""
    try:
        text = (text or "")[:MAX_SCAN_BYTES]
        seen = set()
        findings = []
        for name, rx in _PATTERNS:
            if name in seen:
                continue
            m = rx.search(text)
            if m:
                excerpt = re.sub(r"\s+", " ", m.group(0))[:120]
                findings.append({"class": name, "excerpt": excerpt})
                seen.add(name)
        return findings
    except Exception:
        return []


def _format_warning(file_path, findings):
    """Formatea el aviso para el tool-result.

    Breve, accionable, sin bloquear. Se imprime como JSON para que Claude Code
    lo integre correctamente al tool-result (formato guidance PostToolUse)."""
    labels = ", ".join(f["class"] for f in findings)
    path_note = f" en `{file_path}`" if file_path else ""
    lines = [
        f"[WORKSPACE N15] Posibles riesgos de seguridad detectados{path_note}:",
    ]
    for f in findings:
        lines.append(f"  · {f['class']}: {f['excerpt']}")
    lines.append(
        "Revisa antes de proceder. Este aviso es informativo — el archivo "
        "ya fue escrito. Clases: " + labels
    )
    return "\n".join(lines)


def _read_stdin():
    """Lee y parsea el JSON de stdin. {} si falla o vacío."""
    try:
        raw = sys.stdin.read()
        if not raw or not raw.strip():
            return {}
        return json.loads(raw)
    except Exception:
        return {}


def _setting_on(key):
    """Setting bool del store unificado (settings.py, raíz de WORKSPACE).
    Falla-suave → True (on-by-default). El env kill-switch SIEMPRE gana."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)
        import settings as _settings
        return _settings.enabled(key, default=True)
    except Exception:
        return True


def main():
    """Punto de entrada del hook PostToolUse."""
    if os.environ.get(KILL_SWITCH):
        return                                   # env: el kill-switch gana
    if not _setting_on("hooks.security_guidance"):
        return                                   # canal nuevo (settings.py)
    try:
        data = _read_stdin()
        tool_name = data.get("tool_name", "")
        if tool_name not in WRITE_TOOLS:
            return
        tool_input = data.get("tool_input", {})
        content = _extract_content(tool_name, tool_input)
        if not content:
            return
        findings = scan(content)
        if not findings:
            return
        file_path = _file_path(tool_input)
        msg = _format_warning(file_path, findings)
        # PostToolUse: el ÚNICO shape que Claude Code entrega al modelo es
        # hookSpecificOutput.additionalContext (mismo mecanismo que SessionStart).
        # {"type":"text"} plano NO es reconocido → iba solo al debug log (no-op).
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": msg}}, ensure_ascii=False))
    except Exception:
        pass  # falla-suave absoluta: jamás romper el flujo del agente


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # exit 0 siempre — jamás bloquear
