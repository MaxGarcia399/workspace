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


# ── Decisores · uso «Seguridad» (apagado de fábrica) ─────────────────────────
#: El decisor solo se consulta cuando el escaneo YA encontró algo (las
#: escrituras sin hallazgos siguen sin costo) y ve el fragmento recortado.
DECISOR_FRAGMENTO = 1500
#: Clases cuyo match ES el secreto: su valor se tapa antes de que salga nada.
CLASES_SECRETO = ("hardcoded_secret",)
#: El literal entre comillas al final de un match de hardcoded_secret.
_LITERAL_FINAL = re.compile(r"""(['"])([^'"]{6,})(['"])\s*$""")


def enmascarar(content):
    """El texto con el VALOR de cada secreto que este mismo escáner encontró
    (hardcoded_secret: lo de entre comillas) tapado — en su lugar y en CADA
    otra aparición (un comentario, un log, un print) — antes de armar nada
    para el decisor. Lo que el detector de este hook marca es más amplio que
    la redacción general (6+ caracteres tras `password=`, `self.password =
    …`): sin esto el uso «Seguridad» mandaba justo el secreto que acababa de
    encontrar. Después, la fachada además pasa redact() (credenciales de línea
    de comandos, «clave = valor», Bearer…)."""
    text = content or ""
    valores = []
    for name, rx in _PATTERNS:
        if name not in CLASES_SECRETO:
            continue

        def tapar(m, name=name):
            def literal(q):
                valores.append(q.group(2))
                return "%s[secret:%s]%s" % (q.group(1), name, q.group(3))
            return _LITERAL_FINAL.sub(literal, m.group(0))
        text = rx.sub(tapar, text)
    for v in sorted(set(valores), key=len, reverse=True):
        if len(v.strip()) >= 4:
            text = text.replace(v, "[secret:hardcoded_secret]")
    return text


# ── lo que el archivo DICE no cuenta: solo el código ─────────────────────────
# Prueba real 2026-11-07: un docstring «es prueba, no se ejecuta» bajó a
# «bajo» un shell=True con un argumento de fuera. Antes de mandar el fragmento
# se le quitan los comentarios, los docstrings y la PROSA de los textos entre
# comillas (los comandos, rutas, SQL y direcciones se quedan: son conducta).
# Python con tokenize; los demás lenguajes, lo razonable (#, //, /* */,
# <!-- -->). Nunca falla: si nada sirve, va el texto tal cual (y el decisor de
# todos modos solo puede SUBIR el riesgo, nunca bajarlo).
#: Lo que se limpia (el corte final, DECISOR_FRAGMENTO, va después).
DECISOR_VENTANA = DECISOR_FRAGMENTO * 40
_PROSA = "…"
_EXT_PY = (".py", ".pyw", ".pyi", ".ipynb")
_EXT_HASH = (".sh", ".bash", ".zsh", ".ksh", ".fish", ".rb", ".pl", ".pm", ".r", ".yml",
             ".yaml", ".toml", ".ps1", ".psm1", ".conf", ".cfg", ".env", ".tf", ".nix",
             ".ex", ".exs", ".coffee", ".jl", ".mk", ".cmake")
_EXT_C = (".js", ".mjs", ".cjs", ".ts", ".tsx", ".jsx", ".java", ".c", ".h", ".cc", ".cpp",
          ".hpp", ".cs", ".go", ".rs", ".swift", ".kt", ".kts", ".scala", ".dart", ".groovy",
          ".gradle", ".sol", ".zig", ".scss", ".less")
_EXT_MARCADO = (".html", ".htm", ".xml", ".xhtml", ".svg", ".md", ".vue", ".svelte")
_NOMBRES_HASH = ("dockerfile", "makefile", "gemfile", "rakefile", "procfile", "vagrantfile")
_PALABRA = re.compile(r"[^\W\d_]{2,}")
#: Lo que delata código dentro de unas comillas (y no prosa): operadores,
#: rutas, variables, banderas de comando.
_ES_CODIGO = re.compile(r"[*=/\\$%{}<>|&\[\]#@~^`]|(?:^|\s)--?[A-Za-z]")
_SQL = re.compile(r"\s*(select|insert|update|delete|drop|create|alter|truncate|grant|revoke|"
                  r"exec|execute|call|merge|replace|with|union)\b", re.IGNORECASE)


def es_prosa(texto):
    """¿Este texto entre comillas es prosa (una frase para personas) y no un
    comando, una ruta, SQL o un dato? Tres palabras o más, sin nada de código,
    y con puntuación de frase o cinco palabras o más."""
    t = (texto or "").strip()
    if len(t) < 12:
        return False
    palabras = _PALABRA.findall(t)
    if len(palabras) < 3 or _ES_CODIGO.search(t) or _SQL.match(t):
        return False
    return bool(re.search(r"[.,;:!?¿¡]", t)) or len(palabras) >= 5


def _familia(file_path):
    nombre = os.path.basename(str(file_path or "")).lower()
    ext = os.path.splitext(nombre)[1]
    if ext in _EXT_PY:
        return "py"
    if ext in _EXT_HASH or nombre in _NOMBRES_HASH:
        return "hash"
    if ext == ".php":
        return "php"
    if ext in _EXT_C:
        return "c"
    if ext == ".css":
        return "css"
    if ext == ".sql":
        return "sql"
    if ext in _EXT_MARCADO:
        return "marcado"
    return "otro"


_FAMILIAS = {
    #        comentario de línea · bloques
    "hash": (("#",), ()),
    "py": (("#",), ()),                       # el respaldo de Python si tokenize no puede
    "c": (("//",), (("/*", "*/"),)),
    "php": (("//", "#"), (("/*", "*/"),)),
    "css": ((), (("/*", "*/"),)),
    "sql": (("--",), (("/*", "*/"),)),
    "marcado": ((), (("<!--", "-->"),)),
    # sin extensión conocida: los bloques y las líneas que EMPIEZAN con # o //
    "otro": ((), (("/*", "*/"), ("<!--", "-->"))),
}


def _sin_comentarios(src, familia):
    """Quita comentarios fuera de las comillas y deja «"…"» en el lugar de la
    prosa entre comillas. Lo razonable, no un parser: comillas con escape \\,
    triples (Python, respaldo), sin cruzar de línea las simples."""
    linea, bloques = _FAMILIAS.get(familia, _FAMILIAS["otro"])
    out, i, n = [], 0, len(src)
    inicio_linea = True
    while i < n:
        ch = src[i]
        if ch == "\n":
            out.append(ch)
            i += 1
            inicio_linea = True
            continue
        if inicio_linea and ch in " \t":
            out.append(ch)
            i += 1
            continue
        hecho = False
        for a, b in bloques:
            if src.startswith(a, i):
                j = src.find(b, i + len(a))
                fin = n if j < 0 else j + len(b)
                out.append("\n" * src.count("\n", i, fin))
                i, hecho = fin, True
                break
        if hecho:
            continue
        marcas = linea + (("#", "//") if familia == "otro" and inicio_linea else ())
        for a in marcas:
            if not src.startswith(a, i):
                continue
            if a == "#" and not (inicio_linea or src[i - 1] in " \t;("):
                continue                      # ${#x}, $#, url#frag: no es comentario
            if a == "#" and src.startswith("#!", i) and i == 0:
                continue                      # el shebang se queda
            j = src.find("\n", i)
            i, hecho = (n if j < 0 else j), True
            break
        if hecho:
            continue
        inicio_linea = False
        if ch in "\"'`":
            delim = ch * 3 if src.startswith(ch * 3, i) else ch
            j = i + len(delim)
            while j < n and not src.startswith(delim, j):
                if src[j] == "\\":
                    j += 2
                    continue
                if len(delim) == 1 and src[j] == "\n":
                    break                     # una comilla suelta (un apóstrofo)
                j += 1
            cerrada = j < n and src.startswith(delim, j)
            cuerpo = src[i + len(delim):j]
            out.append(delim + (_PROSA if cerrada and es_prosa(cuerpo) else cuerpo)
                       + (delim if cerrada else ""))
            i = j + len(delim) if cerrada else j
            continue
        out.append(ch)
        i += 1
    return "".join(out)


_LITERAL_PY = re.compile(r"^([A-Za-z]*)('{3}|\"{3}|'|\")(.*)\2$", re.DOTALL)


def _literal_sin_prosa(tok):
    """Un literal de Python con su prosa tapada (en un f-string, solo los
    trozos de texto: las {expresiones} se quedan)."""
    m = _LITERAL_PY.match(tok)
    if not m:
        return tok
    pre, q, cuerpo = m.groups()
    if "f" in pre.lower():
        trozos = re.split(r"(\{[^{}]*\})", cuerpo)
        nuevo = "".join(t if t.startswith("{") or not es_prosa(t) else _PROSA for t in trozos)
    else:
        nuevo = _PROSA if es_prosa(cuerpo) else cuerpo
    return pre + q + nuevo + q


def _python_sin_prosa(src):
    """Python con tokenize: fuera los COMMENT, los docstrings (un texto suelto
    como sentencia) y la prosa de los literales. Levanta si no tokeniza."""
    import io
    import tokenize
    fs_ini = getattr(tokenize, "FSTRING_START", None)
    fs_mid = getattr(tokenize, "FSTRING_MIDDLE", None)
    fs_fin = getattr(tokenize, "FSTRING_END", None)
    toks = list(tokenize.generate_tokens(io.StringIO(src).readline))
    inicios = [0]
    for ln in src.splitlines(True):
        inicios.append(inicios[-1] + len(ln))

    def off(rc):
        return inicios[rc[0] - 1] + rc[1] if rc[0] - 1 < len(inicios) else len(src)

    cambios, sentencia, k = [], True, 0
    corte = (tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT, tokenize.ENCODING)
    while k < len(toks):
        t = toks[k]
        if t.type == tokenize.COMMENT:
            cambios.append((off(t.start), off(t.end), ""))
            k += 1
            continue
        if sentencia and (t.type == tokenize.STRING or (fs_ini is not None and t.type == fs_ini)):
            j, prof = k, 0                     # la corrida de literales de la sentencia
            while j < len(toks):
                tj = toks[j]
                if fs_ini is not None and tj.type == fs_ini:
                    prof += 1
                elif fs_fin is not None and tj.type == fs_fin:
                    prof -= 1
                elif prof == 0 and tj.type not in (tokenize.STRING, tokenize.NL, tokenize.COMMENT):
                    break
                j += 1
            sig = toks[j] if j < len(toks) else None
            if sig is None or sig.type in (tokenize.NEWLINE, tokenize.ENDMARKER):
                cambios.append((off(t.start), off(toks[j - 1].end), '"%s"' % _PROSA))
                k, sentencia = j, False
                continue
        if t.type == tokenize.STRING:
            nuevo = _literal_sin_prosa(t.string)
            if nuevo != t.string:
                cambios.append((off(t.start), off(t.end), nuevo))
        elif fs_mid is not None and t.type == fs_mid and es_prosa(t.string) \
                and src[off(t.start):off(t.end)] == t.string:
            cambios.append((off(t.start), off(t.end), _PROSA))
        if t.type in corte:
            sentencia = True
        elif t.type not in (tokenize.NL, tokenize.COMMENT):
            sentencia = False
        k += 1
    out, pos = [], 0
    for a, b, nuevo in sorted(cambios):
        if a < pos:
            continue
        out.append(src[pos:a])
        out.append(nuevo)
        pos = b
    out.append(src[pos:])
    return "".join(out)


def solo_codigo(content, file_path=""):
    """El fragmento sin comentarios, docstrings ni prosa entre comillas —
    lo único que el decisor juzga es la conducta. Falla-suave: Python con
    tokenize → si no tokeniza (un trozo de un Edit), el escáner de `#` →
    si algo truena, el texto tal cual."""
    src = content or ""
    familia = _familia(file_path)
    try:
        if familia == "py":
            try:
                limpio = _python_sin_prosa(src)
            except Exception:
                limpio = _sin_comentarios(src, "py")
        else:
            limpio = _sin_comentarios(src, familia)
    except Exception:
        return src
    out, vacias = [], 0
    for ln in limpio.split("\n"):             # sin los huecos que dejaron los comentarios
        ln = ln.rstrip()
        vacias = vacias + 1 if not ln.strip() else 0
        if vacias <= 1:
            out.append(ln)
    return "\n".join(out).strip("\n")


def _decisor(file_path, findings, content):
    """¿Qué tan riesgoso es este cambio? (bajo · medio · alto). None si el uso
    está apagado, falla o tarda (≤1.5 s): el aviso sale como siempre."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.insert(0, root)
        import decisions
        if not decisions.enabled("workspace.security"):
            return None
        cabeza = "Archivo: %s\nHallazgos del escaneo: %s\nFragmento escrito:\n" % (
            file_path or "?", ", ".join(f["class"] for f in findings))
        # 1) solo el código (lo que el archivo dice no cuenta); 2) tapar los
        # secretos ANTES de recortar, sobre una ventana más grande que el corte;
        # la fachada redacta y recorta al final (redactar antes de truncar)
        codigo = solo_codigo((content or "")[:DECISOR_VENTANA], file_path)
        fragmento = enmascarar(codigo[:DECISOR_FRAGMENTO * 4])
        # al_agente: su línea ◆ le llega en el aviso (additionalContext)
        return decisions.gate("workspace.security", context=cabeza + fragmento,
                              context_max=len(cabeza) + DECISOR_FRAGMENTO, al_agente=True)
    except Exception:
        return None


def _con_decisor(msg, v, file_path, findings):
    """El aviso según el decisor. Complementa, nunca sustituye NI SUAVIZA: el
    decisor puede SUBIR el riesgo, nunca bajarlo (el aviso del escáner queda
    entero con cualquier respuesta).
      · None / observe → el aviso de siempre (solo quedó anotado);
      · apply «alto»   → el aviso pide corregir antes de seguir + la línea ◆;
      · lo demás (suggest; «decide» bajo el umbral; «medio»/«bajo», que nunca
        se aplican) → el aviso de siempre + la línea ◆, marcada como solo una
        sugerencia."""
    if not v or v.get("mode") not in ("suggest", "apply"):
        return msg
    try:
        from decision_errors import _t                  # sigue ui.lang
    except Exception:
        def _t(key, es, **kw):
            return es.format(**kw)
    choice = str(v.get("choice") or "").strip().lower()
    pct = int(round(float(v.get("p") or 0) * 100))
    linea = _linea_visible(v)
    if linea:                                     # + el recordatorio, junto a la línea
        try:
            import decision_visible
            linea += "\n" + decision_visible.para_el_socio()
        except Exception:
            pass
    if v.get("mode") == "apply" and choice == "alto":
        return _t("decisores.hook.security_high", "[WORKSPACE N15 · riesgo ALTO según el decisor "
                  "({p} % seguro)] Corrígelo antes de seguir; si es intencional, explícale al "
                  "socio por qué en una línea.", p=pct) + "\n" + msg + ("\n" + linea if linea else "")
    return msg + ("\n" + linea if linea else "")


def _linea_visible(v):
    """La línea «◆ <modelo>: subió el aviso a riesgo alto · 92 % · …» (decision_visible) o ''."""
    try:
        import decision_visible
        if v and v.get("mode") == "apply" and str(v.get("choice") or "").strip().lower() != "alto":
            v = dict(v, mode="suggest")           # defensa: «bajo»/«medio» jamás se aplican
        return decision_visible.linea_seguridad(v)
    except Exception:
        return ""


def _read_stdin():
    """Lee y parsea el JSON de stdin. {} si falla o vacío. Lector único de los
    hooks (_utf8): BYTES → UTF-8 (en Windows stdin es cp1252)."""
    try:
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        if root not in sys.path:
            sys.path.append(root)
        import _utf8
        return _utf8.json_de_stdin()
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
        v = _decisor(file_path, findings, content)
        msg = _con_decisor(msg, v, file_path, findings)
        # PostToolUse: el ÚNICO shape que Claude Code entrega al modelo es
        # hookSpecificOutput.additionalContext (mismo mecanismo que SessionStart).
        # {"type":"text"} plano NO es reconocido → iba solo al debug log (no-op).
        salida = {"hookSpecificOutput": {"hookEventName": "PostToolUse",
                                         "additionalContext": msg}}
        # …y lo que el socio VE (systemMessage): la línea ◆ del decisor, solo
        # con el uso encendido en suggest/decide — apagado, la salida de siempre
        visible = _linea_visible(v)
        if visible:
            salida = dict({"systemMessage": visible}, **salida)
        print(json.dumps(salida, ensure_ascii=False))
    except Exception:
        pass  # falla-suave absoluta: jamás romper el flujo del agente


if __name__ == "__main__":
    try:
        main()
    except Exception:
        pass  # exit 0 siempre — jamás bloquear
