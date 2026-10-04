#!/usr/bin/env python3
"""WORKSPACE · secret_scan — detector de SECRETOS reales en cerebros (N14).

Los cerebros se respaldan a git: una clave API commiteada a un repo (aunque
sea privado) es una fuga — git guarda historia para siempre. Este módulo
detecta credenciales REALES (claves API, tokens, private keys) en archivos
que van camino a un commit. Pocos patrones, ALTA precisión: cada clase ancla
en el formato inequívoco del proveedor, y un filtro anti-falsos-positivos
descarta placeholders/ejemplos (`sk-xxxx…`, `your-key-here`, `AKIA…EXAMPLE`).

NO confundir con `hooks/untrusted.py` (N6): aquel detecta INYECCIÓN/EXFIL en
contenido entrante (defensa del flujo headless); este detecta SECRETOS
salientes (higiene de lo que se commitea). Comparten filosofía (regex
ancladas, log/warn — jamás bloquear), no patrones.

Integración — DECISIÓN N14:
· **Doctor, fase 9** (`phase_secrets`): escanea el working tree de cada
  cerebro y reporta **WARN, jamás ✗** — nunca bloquea el flujo del socio
  (regla 3 de la serie N: checks nuevos no convierten una instalación sana
  en fallo). Solo-lectura SIEMPRE (en --check y en fix: escanear no repara).
· **Pre-commit OPT-IN, manual**: `python3 secret_scan.py --staged` escanea
  los archivos staged del repo en cwd y sale con código 1 si hay hallazgos —
  el socio que lo quiera lo agrega ÉL MISMO a su `.git/hooks/pre-commit`.
  WORKSPACE **no instala git hooks automáticamente**: un hook que bloquea
  commits sin consentimiento rompe el flujo del socio y viola el principio
  "nada en el camino crítico". Doctor-WARN + opt-in documentado es el camino.
· **Historia git** (`--history` / `scan_git_history`): escanea commits
  recientes (cap MAX_HISTORY_COMMITS) via `git log -p`. Un secreto commiteado
  y luego borrado SIGUE en la historia — severidad ALTA. Falla-suave si git
  no está. WARN-only, jamás bloquea, solo-lectura.

Anti-fuga del propio reporte: los hallazgos NUNCA incluyen el secreto
completo — solo un prefijo enmascarado (primeros 7 chars + longitud).

Falso positivo legítimo (docs, ejemplos): añade `workspace:allow-secret` en la
misma línea y el escáner la salta.

Cero dependencias (stdlib, Python 3.9+). Mac y Windows. Falla-suave: errores
de I/O ⇒ archivo saltado, jamás excepción al caller. Amputable (C10).
"""
import os
import re
import subprocess
import sys

MAX_FILE_BYTES = 1_000_000      # archivos más grandes no son md de cerebro
MAX_FINDINGS_PER_FILE = 20      # techo anti-flood por archivo
MAX_FINDINGS_PER_SCAN = 200     # techo de cordura por cerebro
MAX_HISTORY_COMMITS = 500       # cap de historia git: no escanear repos infinitos
ALLOW_MARKER = "workspace:allow-secret"
ENV_OVERRIDE = "WORKSPACE_ALLOW_SECRET"   # escape de emergencia por entorno (F3)

# ── patrones (clase, regex) — el grupo `secret` (si existe) es la credencial;
#    sin grupo, el match completo lo es. Anclas por formato del proveedor.
#
#    ORDEN IMPORTA para Anthropic: los subtipos concretos (api03, oat01) van
#    ANTES del genérico sk-ant- para que el finding tenga la clase correcta.
# ──
PATTERNS = tuple((name, re.compile(rx)) for name, rx in (
    # Anthropic OAuth token (mid-2024+) — prefijo más específico, va primero
    ("anthropic_oauth_token", r"\bsk-ant-oat01-[A-Za-z0-9_\-]{40,}"),
    # Anthropic API key estándar (api03); también captura subtipos futuros de
    # sk-ant- que no sean oat01 (el lookahead excluye oat01 ya cubierto arriba)
    ("anthropic_api_key", r"\bsk-ant-(?!oat01-)[A-Za-z0-9_\-]{24,}"),
    # OpenAI project key (default desde mid-2024) — más específico que genérico
    ("openai_project_key", r"\bsk-proj-[A-Za-z0-9_\-]{40,}"),
    # OpenAI service-account key
    ("openai_svcacct_key", r"\bsk-svcacct-[A-Za-z0-9_\-]{40,}"),
    # OpenAI legacy / genérica; lookaheads: no pisar sk-ant- ni sk-proj- ni sk-svcacct-
    ("openai_api_key",
     r"\bsk-(?!ant-)(?!proj-)(?!svcacct-)[A-Za-z0-9_\-]{20,}"),
    # GitHub: ghp_/gho_/ghs_/ghu_/ghr_ + 36+ alfanuméricos
    ("github_token", r"\bgh[pousr]_[A-Za-z0-9]{36,}"),
    # AWS access key id (AKIA permanente / ASIA temporal)
    ("aws_access_key_id", r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b"),
    # Google: AIza + 35 chars
    ("google_api_key", r"\bAIza[0-9A-Za-z_\-]{35}"),
    # bloques PEM de llave privada (RSA/EC/DSA/OPENSSH/PGP/…)
    ("private_key_block", r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    # bearer tokens largos (JWT, OAuth) en headers/snippets
    ("bearer_token",
     r"(?i)\bbearer[ \t]+(?P<secret>[A-Za-z0-9_\-.~+/]{30,}=*)"),
    # Stripe secret/restricted key (live o test) — guion BAJO (no choca con sk- de OpenAI)
    ("stripe_secret_key", r"\b[sr]k_(?:live|test)_[A-Za-z0-9]{24,}"),
    # Slack tokens (bot/user/app/refresh/legacy)
    ("slack_token", r"\bxox[baprs]-[A-Za-z0-9-]{10,}"),
    # SendGrid API key (SG.<22>.<43>)
    ("sendgrid_key", r"\bSG\.[A-Za-z0-9_\-]{22}\.[A-Za-z0-9_\-]{43}\b"),
    # Gmail/Google App Password (SEC/Argus): 16 letras MINÚSCULAS, con o sin
    # espacios cada 4 (así lo muestra Google: "abcd efgh ijkl mnop"). Un
    # [a-z]{16} suelto sería FP masivo (prosa), así que se ANCLA al contexto:
    # el valor debe ser la asignación de una clave *pass(word)* (app_password,
    # gmail_pass, smtp_password, PASSWORD=…), en forma .env/yaml o JSON
    # ("app_password": "…"). La clave es case-insensitive; el VALOR exige
    # minúsculas estrictas vía grupo (?-i:) — un app password jamás trae
    # mayúsculas/dígitos.
    ("gmail_app_password",
     r"(?i)\b(?:(?:gmail|google|smtp|e?mail|app)[ _\-]?)?pass(?:word|wd)?\b"
     r"[\"']?[ \t]*[:=][ \t]*[\"']?"
     r"(?-i:(?P<secret>[a-z]{4}(?:[ ]?[a-z]{4}){3}))(?![A-Za-z0-9])"),
    # Valor de clave JSON sensible (SEC/Argus — forma de mail.json):
    # "password"/"token"/"api_key"/… : "<valor>". env_secret NO cubre esto
    # (su clave va SIN comillas, anclada a inicio de línea). Conservador para
    # no FP-ear docs: solo las claves listadas, valor tipo-credencial (sin
    # espacios ni comillas) de ≥12 chars; los placeholders (`<tu-token>`,
    # `changeme…`, `xxxx…`) los descarta el filtro anti-placeholder de siempre.
    ("json_keyed_secret",
     r"(?i)\"(?:password|passwd|secret|token|api[_\-]?key|app[_\-]?password|"
     r"client[_\-]?secret)\""
     r"[ \t]*:[ \t]*\"(?P<secret>[A-Za-z0-9_\-./+=]{12,})\""),
    # asignación .env-style: VAR con API_KEY/SECRET/TOKEN/PASSWORD + valor real.
    # (?i): el NOMBRE de la var viene tanto en MAYÚSCULA (.env) como minúscula
    # (yaml/código: `api_key:`, `password=`) — la convención dominante. Sin (?i)
    # el gate DURO ignoraba el caso más común (A1, era P1). El valor ya era
    # case-agnóstico, así que (?i) no afloja la captura.
    ("env_secret",
     r"(?im)^[ \t]*(?:export[ \t]+)?"
     r"[A-Z0-9_]*(?:API_?KEY|SECRET|TOKEN|PASSWD|PASSWORD|CREDENTIALS?)"
     r"[A-Z0-9_]*[ \t]*[=:][ \t]*[\"']?"
     r"(?P<secret>[A-Za-z0-9_\-./+]{16,}={0,2})[\"']?[ \t]*(?:#.*)?$"),
))

# ── anti-falsos-positivos: placeholders / ejemplos / redactados ────────────
#
# F12 (Turing 2026-06-25): dos clases de pista, tratadas DISTINTO para no
# generar falsos NEGATIVOS (que un token real se descarte por contener una
# subcadena inocente):
#
#  · _PLACEHOLDER_STRUCTURAL — caracteres que JAMÁS aparecen en una credencial
#    real (un secreto válido nunca trae `<`, `{`, `$`, `…`); se buscan como
#    SUBCADENA porque su sola presencia delata un placeholder/ejemplo.
#
#  · _PLACEHOLDER_WORDS — palabras-señal de docs/ejemplos (`test`, `demo`,
#    `example`, `0000`, `abcd`…). Antes se buscaban como subcadena sobre el
#    secreto COMPLETO → un PAT real como `ghp_aTESTbc…` o `sk-ant-…demo…` se
#    descartaba (FALSO NEGATIVO). Ahora se exige que la palabra aparezca como
#    TOKEN delimitado (frontera de no-alfanumérico), no enterrada dentro de un
#    blob de alta entropía. Así `your-key-here` o `AKIA…EXAMPLE` siguen siendo
#    placeholder, pero un secreto real con esas letras incrustadas NO se pierde.
_PLACEHOLDER_STRUCTURAL = ("...", "…", "<", ">", "{", "}", "$")

_PLACEHOLDER_WORDS = (
    "your", "example", "placeholder", "changeme", "change-me",
    "change_me", "redact", "redacted", "dummy", "sample", "insert", "fake",
    "aqui", "tu-clave", "tu_clave", "your-key-here",
    # Placeholders específicos de docs de Anthropic y OpenAI (N14 hardening)
    "test", "demo", "mock", "stub", "temp", "notreal", "not-real",
    "replace", "abcd",
)

# Relleno: una corrida del MISMO carácter (`xxxx`, `0000`, `aaaa`) delata un
# placeholder/redacción (`sk-ant-xxxxxx…`, `0000…`). A3: la corrida debe
# DOMINAR el valor para contar — antes `(.)\1{3,}` (≥4 en cualquier lado)
# descartaba una clave real que por azar contuviera `aaaa`/`0000` enterrado
# (~1 en 1140 tras lower()). Ahora exigimos run ≥ max(6, ¼ del valor): los
# placeholders reales usan corridas largas (8+); un 4-run casual ya no mata.
def _dominant_filler_run(s):
    """Largo de la corrida más larga de un mismo carácter en `s`."""
    best = run = 0
    prev = None
    for ch in s:
        run = run + 1 if ch == prev else 1
        prev = ch
        if run > best:
            best = run
    return best


def _has_placeholder_word(s):
    """True si alguna palabra-señal aparece como token o anclada en `s`.

    Una credencial real es un blob de alta entropía: una palabra-señal cae
    SIEMPRE enterrada entre caracteres alfanuméricos aleatorios. Un placeholder
    en cambio expone la palabra: o es un token delimitado (`your-key-here`,
    rodeado de `-`/inicio/fin), o aparece anclada al inicio/fin del valor
    (`examplevalue123`, `AKIA…EXAMPLE`). Solo esos dos casos cuentan como
    placeholder; una palabra ENTERRADA en medio (`ghp_a1testb2…`) NO descarta
    el secreto — ese era el falso NEGATIVO de F12.

    Frontera = no-alfanumérico (inicio/fin de string también es frontera)."""
    n = len(s)
    for w in _PLACEHOLDER_WORDS:
        for m in re.finditer(re.escape(w), s):
            i, j = m.start(), m.end()
            before = s[i - 1] if i > 0 else ""
            after = s[j] if j < n else ""
            delimited = (not before.isalnum()) and (not after.isalnum())
            # A2: una palabra anclada al borde solo cuenta si es LARGA (≥6). Antes
            # cualquier runa de 4 (`test`,`demo`,`abcd`) al inicio/fin del valor
            # descartaba un secreto real que casualmente empezara/terminara así.
            # `example`/`placeholder`/`changeme` (≥6) siguen anclando; las runas
            # cortas solo cuentan si están DELIMITADAS (`-test-`).
            anchored = (len(w) >= 6) and ((i == 0) or (j == n))
            if delimited or anchored:
                return True
    return False


def _placeholder(secret):
    """True si `secret` huele a placeholder/ejemplo, no a credencial real."""
    s = (secret or "").lower()
    if not s:
        return True
    # marcadores estructurales: subcadena basta (nunca van en un secreto real)
    if any(h in s for h in _PLACEHOLDER_STRUCTURAL):
        return True
    # corrida de relleno que DOMINA el valor (xxxxxx…, 0000…): placeholder.
    # A3: proporcional, para no matar una clave real con un 4-run incidental.
    if _dominant_filler_run(s) >= max(6, len(s) // 4):
        return True
    # palabras-señal: solo como token delimitado (F12 — no como subcadena)
    if _has_placeholder_word(s):
        return True
    core = re.sub(r"[^a-z0-9]", "", s)
    # casi sin entropía (aaaa…, 121212…, skxxxx…) = relleno, no clave
    return bool(core) and len(set(core)) <= 4


def _mask(secret):
    """Jamás re-imprimir el secreto: prefijo corto + longitud."""
    s = secret or ""
    return s[:7] + "…" + f"[{len(s)} chars]"


def scan_text(text):
    """Escanea `text`; devuelve [{class, line, excerpt}] orden por línea.
    `excerpt` viene ENMASCARADO (nunca el secreto completo)."""
    findings = []
    if not text:
        return findings
    # Normaliza fin de línea: en Windows los archivos se leen con CRLF (\r\n)
    # y el `\r` residual rompe los patrones anclados a `$` (env_secret) — el
    # ancla multilínea casa SOLO antes de `\n`, nunca antes de `\r`. Sin esto
    # un secreto real se escapa en Windows pese a detectarse en POSIX. El
    # conteo de líneas (por `\n`) queda intacto. OS-agnóstico.
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    for cls, rx in PATTERNS:
        for m in rx.finditer(text):
            secret = m.groupdict().get("secret") or m.group(0)
            if cls != "private_key_block" and _placeholder(secret):
                continue
            ls = text.rfind("\n", 0, m.start()) + 1
            le = text.find("\n", m.start())
            le = len(text) if le < 0 else le
            if ALLOW_MARKER in text[ls:le]:
                continue   # excepción explícita del socio en esa línea
            findings.append({"class": cls,
                             "line": text.count("\n", 0, m.start()) + 1,
                             "excerpt": _mask(secret)})
    findings.sort(key=lambda f: f["line"])
    return findings


# ── GATE DURO con escape (F3 · decisión del socio "bloquear con escape") ──────
#
# La Regla de Oro del proyecto ("credenciales JAMÁS al repo") solo se cumple si
# en los chokepoints que WORKSPACE SÍ controla un secreto detectado DETIENE la
# operación, no la deja pasar con un ⚠. `gate_text` es ese punto de decisión,
# centralizado y testeable. Dos escapes FÁCILES y documentados para el falso
# positivo legítimo:
#
#   (a) marcador inline por línea: `workspace:allow-secret` en la misma línea
#       (lo respeta `scan_text` → esa línea ni siquiera produce finding).
#   (b) override de emergencia por entorno: `WORKSPACE_ALLOW_SECRET=1` salta el
#       gate COMPLETO de ese proceso (para el falso positivo que no controlas
#       por línea, p.ej. un blob generado). Granularidad gruesa a propósito:
#       es un martillo de emergencia, no el camino normal — el normal es (a).
#
# El gate NO redacta ni reescribe: o el contenido está limpio (o exento) y pasa
# intacto, o se bloquea. La redacción silenciosa de antes ocultaba el problema;
# el bloqueo lo hace visible y obliga a decidir (mover a env / .gitignore /
# rotar). El mensaje de bloqueo DICE cómo saltarlo (auto-documentado).


class SecretBlocked(RuntimeError):
    """Operación detenida: el contenido trae un secreto sin exención.
    `.findings` lista los hallazgos (enmascarados, nunca el secreto)."""
    def __init__(self, findings, where=""):
        self.findings = findings
        self.where = where
        super().__init__(block_message(findings, where))


def env_override_active(env=None):
    """True si el escape de emergencia por entorno está activo.
    Cualquier valor no vacío y distinto de 0/false/no/off lo activa."""
    env = os.environ if env is None else env
    v = str(env.get(ENV_OVERRIDE, "")).strip().lower()
    return v not in ("", "0", "false", "no", "off")


# F3-audit · el override apaga la detección PARA TODO EL PROCESO. No puede ser
# silencioso: alguien que lo deja "pegado" en su entorno desactiva la Regla de
# Oro sin que nadie lo note. Cada vez que un chokepoint lo respeta, dejamos
# rastro RUIDOSO a stderr nombrando la env var y el sitio. El aviso sale para
# CUALQUIER valor que active el override (no solo "=1").
def _warn_override(where="", out=None):
    """Emite a stderr el aviso de que la detección de secretos está DESACTIVADA
    por el override de entorno. `out` (default sys.stderr) es inyectable para
    test. No levanta jamás (falla-suave: un fallo al avisar no debe romper el
    chokepoint)."""
    try:
        loc = (" en %s" % where) if where else ""
        msg = ("⚠ secret_scan: detección de secretos DESACTIVADA por %s%s — "
               "el contenido pasa SIN escanear. Quita la env var para "
               "reactivar la protección." % (ENV_OVERRIDE, loc))
        stream = sys.stderr if out is None else out
        print(msg, file=stream)
    except Exception:
        pass


def block_message(findings, where=""):
    """Mensaje de bloqueo AUTO-DOCUMENTADO: qué se detectó (enmascarado) y las
    DOS formas de saltarlo. Nunca incluye el secreto completo."""
    loc = (" en %s" % where) if where else ""
    lines = ["secreto(s) detectado(s)%s — operación BLOQUEADA "
             "(Regla de Oro: credenciales JAMÁS al cerebro/repo):" % loc]
    for f in findings[:MAX_FINDINGS_PER_FILE]:
        ln = (":%s" % f["line"]) if f.get("line") else ""
        lines.append("  · [%s]%s  %s" % (f["class"], ln, f.get("excerpt", "")))
    lines += [
        "",
        "Arréglalo: mueve el valor a una variable de entorno o a .gitignore; "
        "si ya se commiteó alguna vez, ROTA la clave.",
        "Si es un FALSO POSITIVO, sáltalo así:",
        "  (a) por línea  → añade  `%s`  al final de ESA línea." % ALLOW_MARKER,
        "  (b) emergencia → exporta  %s=1  y reintenta (salta el gate "
        "completo)." % ENV_OVERRIDE,
    ]
    return "\n".join(lines)


def gate_text(text, where="", env=None):
    """Punto de decisión del gate duro. Devuelve la lista de findings que
    DEBERÍAN bloquear (vacía = pasa). El marcador inline ya filtra por línea en
    `scan_text`; el override de entorno vacía la lista (deja pasar todo).
    No levanta — el caller decide cómo bloquear (raise / exit / return)."""
    if env_override_active(env):
        _warn_override(where)   # F3-audit: el override deja rastro, no calla
        return []
    try:
        return scan_text(text)
    except Exception as exc:
        # A6: el fail-soft es invariante (un crash no bloquea, regla 6) — pero NO
        # MUDO. Un escáner que crashea deja pasar TODO en silencio; eso oculta
        # que la protección se cayó. Espejo del aviso del override: rastro a
        # stderr, jamás levanta.
        try:
            loc = (" en %s" % where) if where else ""
            print("⚠ secret_scan: el escáner FALLÓ%s (%s) — el contenido pasó "
                  "SIN escanear. Revísalo a mano." % (loc, type(exc).__name__),
                  file=sys.stderr)
        except Exception:
            pass
        return []   # falla-suave: un crash del scanner no bloquea (regla 6)


def assert_clean(text, where="", env=None):
    """Variante que LEVANTA SecretBlocked si hay secreto sin exención.
    Para chokepoints que quieren hard-stop con un solo call."""
    findings = gate_text(text, where=where, env=env)
    if findings:
        raise SecretBlocked(findings, where)


def scan_file(path):
    """Escanea un archivo (texto, ≤MAX_FILE_BYTES). Binarios/ilegibles → [].
    Falla-suave: jamás levanta."""
    try:
        if os.path.getsize(path) > MAX_FILE_BYTES:
            return []
        raw = open(path, "rb").read()
        if b"\0" in raw[:4096]:
            return []   # binario
        text = raw.decode("utf-8", errors="replace")
    except Exception:
        return []
    return scan_text(text)[:MAX_FINDINGS_PER_FILE]


def _git_files(repo):
    """Working tree según git: tracked + untracked NO ignorados (lo que de
    verdad puede viajar a un commit; .claude/settings.local.json y demás
    gitignored quedan fuera solos). None si git no responde."""
    try:
        r = subprocess.run(
            ["git", "-C", repo, "ls-files", "--cached", "--others",
             "--exclude-standard", "-z"],
            capture_output=True, timeout=30)
        if r.returncode != 0:
            return None
        out = r.stdout.decode("utf-8", errors="replace")
        return [os.path.join(repo, p) for p in out.split("\0") if p]
    except Exception:
        return None


def _staged_files(repo):
    """Archivos staged (para el modo pre-commit opt-in). [] si no hay/falla."""
    try:
        r = subprocess.run(
            ["git", "-C", repo, "diff", "--cached", "--name-only",
             "--diff-filter=d", "-z"],
            capture_output=True, timeout=30)
        if r.returncode != 0:
            return []
        out = r.stdout.decode("utf-8", errors="replace")
        return [os.path.join(repo, p) for p in out.split("\0") if p]
    except Exception:
        return []


def _walk_files(root):
    """Fallback sin git: walk saltando dot-DIRS (.git/.obsidian/.claude/…)
    y carpetas de máquina — espejo razonable de 'lo que se commitearía'.

    Los dot-FILES (`.env`, `.npmrc`, `.netrc`…) SÍ se escanean (SEC/Argus):
    un dotfile committeado viaja al commit y al distro igual que cualquier
    otro archivo — el gate del distro (make-dist sobre $STAGE, sin .git) era
    CIEGO a ellos y un `.env` con credenciales se embarcaba a clientes sin
    escanear. Los binarios (`.DS_Store`…) los salta `scan_file` (sniff de
    NUL, como `grep -I`); `.git/` jamás se pisa porque los dot-dirs siguen
    excluidos del walk."""
    skip = {"node_modules", "__pycache__"}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in skip]
        for fn in filenames:
            yield os.path.join(dirpath, fn)


def iter_brain_files(brain):
    """Candidatos a escaneo del working tree de un cerebro."""
    if os.path.isdir(os.path.join(brain, ".git")):
        files = _git_files(brain)
        if files is not None:
            for p in files:
                if os.path.isfile(p):
                    yield p
            return
    for p in _walk_files(brain):
        yield p


def scan_brain(brain):
    """Escanea el working tree de un cerebro.
    Devuelve (findings, archivos_escaneados); cada finding trae `path`
    relativo al cerebro. Solo-lectura. Falla-suave por archivo."""
    findings, nfiles = [], 0
    for p in iter_brain_files(brain):
        nfiles += 1
        for fnd in scan_file(p):
            fnd["path"] = os.path.relpath(p, brain)
            findings.append(fnd)
        if len(findings) >= MAX_FINDINGS_PER_SCAN:
            break
    return findings, nfiles


def scan_git_history(brain, max_commits=None):
    """Escanea los últimos N commits del repo `brain` buscando secretos.

    Un secreto que se commiteó y luego se borró SIGUE en la historia git —
    accesible con `git log`. Esta función lo detecta. Severidad: ALTA (un
    secreto en historia ya pública es crítico aunque el HEAD esté limpio).

    Implementación:
    - Usa `git log -p --no-color -n <max_commits>` — solo texto diff puro.
    - Parsea el output linea a linea: encabezados "commit <hash>" y "+líneas"
      del diff; busca secretos solo en líneas añadidas (+) para reducir ruido.
    - Acotado a MAX_HISTORY_COMMITS commits (configurable); documenta el cap.
    - Falla-suave: si git no está disponible, si el directorio no es repo, o
      si el proceso falla por cualquier razón → devuelve [] sin excepciones.
    - Solo-lectura siempre. WARN-only (el caller decide severidad).
    - `workspace:allow-secret` en la línea también silencia el finding de historia.

    Devuelve lista de [{class, commit, path_hint, line_in_diff, excerpt}].
    `path_hint` es el nombre de archivo extraído del encabezado diff (best-effort).
    `commit` es el hash corto del commit donde apareció el secreto.
    """
    if max_commits is None:
        max_commits = MAX_HISTORY_COMMITS

    if not os.path.isdir(os.path.join(brain, ".git")):
        return []   # no es repo git — skip silencioso

    try:
        r = subprocess.run(
            # A5: --all = todas las refs (un secreto en una rama feature no
            # fusionada también está commiteado para siempre); -m = mostrar el
            # diff de los merges (si no, git los omite y el secreto introducido
            # en un merge se escapa pese al ✓ "historia limpia").
            ["git", "-C", brain, "log", "--no-color", "-p", "-m", "--all",
             f"-{max_commits}"],
            capture_output=True, timeout=120,
        )
        if r.returncode != 0:
            return []
        raw = r.stdout.decode("utf-8", errors="replace")
    except Exception:
        return []   # git no disponible o timeout — falla-suave

    findings = []
    current_commit = "unknown"
    current_file = ""
    diff_line_num = 0

    for raw_line in raw.splitlines():
        # Cabecera de commit
        if raw_line.startswith("commit "):
            current_commit = raw_line.split()[1][:12]
            current_file = ""
            diff_line_num = 0
            continue
        # Nombre de archivo en el diff (+++ b/<path>)
        if raw_line.startswith("+++ b/"):
            current_file = raw_line[6:]
            diff_line_num = 0
            continue
        # Líneas añadidas en el diff — solo estas interesan para secretos
        if raw_line.startswith("+") and not raw_line.startswith("+++"):
            diff_line_num += 1
            line_content = raw_line[1:]   # quitar el "+" del diff
            if ALLOW_MARKER in line_content:
                continue
            for fnd in scan_text(line_content):
                fnd["commit"] = current_commit
                fnd["path_hint"] = current_file
                fnd["line_in_diff"] = diff_line_num
                # Renombrar "line" (número en el fragmento de texto) a line_in_diff
                # y quitar "line" para no confundir con línea del archivo original
                fnd.pop("line", None)
                findings.append(fnd)
            if len(findings) >= MAX_FINDINGS_PER_SCAN:
                break

    return findings


def scan_paths(paths):
    """Escanea rutas sueltas (archivos o carpetas). Para el CLI."""
    findings = []
    for p in paths:
        if os.path.isdir(p):
            sub, _ = scan_brain(p)
            for fnd in sub:
                fnd["path"] = os.path.join(p, fnd["path"])
            findings += sub
        elif os.path.isfile(p):
            for fnd in scan_file(p):
                fnd["path"] = p
                findings.append(fnd)
    return findings


def main(argv=None):
    """CLI:  python3 secret_scan.py [--staged] [--history] [ruta…]

    --staged   escanea SOLO los archivos staged del repo en cwd (pre-commit
               opt-in — WORKSPACE jamás instala este hook solo).
    --history  escanea la historia git (últimos MAX_HISTORY_COMMITS commits)
               del repo en ruta. WARN-only: secretos en historia son críticos
               aunque el working tree esté limpio. Falla-suave si sin git.
    sin args   escanea el directorio actual (working tree).
    Exit 1 si hay hallazgos, 0 si está limpio."""
    args = list(argv) if argv is not None else sys.argv[1:]
    staged = "--staged" in args
    history = "--history" in args
    paths = [a for a in args if not a.startswith("-")]

    if history:
        repo = paths[0] if paths else os.getcwd()
        findings = scan_git_history(repo)
        for fnd in findings:
            loc = f"commit:{fnd.get('commit','?')} {fnd.get('path_hint','?')}"
            print(f"  ⚠ {loc}  [{fnd['class']}]  {fnd['excerpt']}")
        if findings:
            print(f"\n  {len(findings)} posible(s) secreto(s) EN HISTORIA GIT — "
                  "CRÍTICO: aunque el archivo ya no exista, el secreto sigue "
                  "accesible con `git log`. Acción: ROTA la clave PRIMERO, "
                  "luego limpia la historia con `git filter-repo`. "
                  f"Falso positivo → marca la línea con `{ALLOW_MARKER}`.")
            return 1
        print(f"  ✓ sin secretos en los últimos {MAX_HISTORY_COMMITS} commits")
        return 0

    if staged:
        repo = paths[0] if paths else os.getcwd()
        findings = []
        for p in _staged_files(repo):
            for fnd in scan_file(p):
                fnd["path"] = os.path.relpath(p, repo)
                findings.append(fnd)
    else:
        findings = scan_paths(paths or [os.getcwd()])
    for fnd in findings:
        print(f"  ⚠ {fnd['path']}:{fnd['line']}  [{fnd['class']}]  "
              f"{fnd['excerpt']}")
    if findings:
        print(f"\n  {len(findings)} posible(s) secreto(s). NO commitees: "
              "muévelo a una env var o a .gitignore; si ya se commiteó "
              "alguna vez, ROTA la clave. Falso positivo → marca la línea "
              f"con `{ALLOW_MARKER}`.")
        return 1
    print("  ✓ sin secretos detectables")
    return 0


if __name__ == "__main__":
    sys.exit(main())
