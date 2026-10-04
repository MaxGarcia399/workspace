#!/usr/bin/env python3
"""WORKSPACE · dashboard — server web local del harness. Cero dependencias (stdlib 3.9+).

> **Extracción del dashboard general (2026-06-26):** la superficie del dashboard
> *general* cliente-facing (status/agentes/sesiones/actividad/cerebro + secciones
> `dash/*`) se extrajo de `main` y vive preservada en la rama **`feat/dashboard`**.
> Lo que queda en `main` es **SOLO el dashboard de DEV** (`workspace dev`): este
> server corre EXCLUSIVAMENTE en modo `--dev`. Para retomar el general:
> `git switch feat/dashboard`.

`workspace dev` → levanta http://127.0.0.1:9121 (modo `--dev`) y abre el navegador:
panel «mission control de developer» (git-graph + switch de ramas + pipeline de
promoción). Superficie aparte, local-only. Las secciones del panel se auto-
descubren en `dash/dev/` (ver `dash/dev/README.md`).

Seguridad (P0, spec dashboard-fase2 §4 — la lección ClawBleed): defensa en 3 capas
contra CSRF/DNS-rebinding sobre los endpoints de escritura (p. ej. switch de rama):
  A. Host   — el header Host debe ser nuestro localhost (corta DNS-rebinding).
  B. Token  — token de sesión (secrets) inyectado en el HTML servido; toda /api/* lo
              exige por header X-WORKSPACE-Token (o ?token= que no acepta headers).
              Una web cross-site no puede leer nuestro HTML (CORS) → nunca lo obtiene.
  C. Origin — si un POST trae Origin, debe ser nuestro localhost (defensa en profundidad).
Bind fuera de loopback (--host explícito) = modo red: la capa A no puede enumerar hosts
→ el token se vuelve obligatorio para TODO (incluido `/`; la URL con ?token= se imprime).

Modelo de amenaza — supuesto SINGLE-USER (riesgo aceptado, revisión Argus 2026-06):
estas capas defienden contra atacantes REMOTOS (web cross-site, DNS-rebinding), NO
contra otros usuarios locales del mismo SO. En modo loopback `/` se sirve SIN token
y el HTML lleva `window.WORKSPACE_TOKEN` inyectado → cualquier usuario local que pueda
hablar con 127.0.0.1:<port> obtiene el token con un GET a `/`. En una Mac personal
de un solo usuario (el escenario WORKSPACE) eso es el propio socio. Si el harness
llegara a correr en máquinas multi-usuario (servidores compartidos, labs), habría
que exigir el token también en `/` en loopback (imprimiendo la URL con ?token= como
ya hace el modo red) — hoy NO se hace para no romper el flujo `workspace dev` → abrir
el navegador sin fricción.

Flags: --dev (obligatorio en main) · --port <n> (def 9120) · --host <h> · --no-open
"""
import os, sys, json, webbrowser, secrets, hmac
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs
sys.dont_write_bytecode = True

try:   # B2 · Windows: UTF-8 en stdout/err. `workspace dev` lanza este server DETACHED
       # (sin consola) con stdout a un log que por defecto es cp1252 → un print con
       # '→' (→, línea ~207) reventaba con UnicodeEncodeError y MATABA el server
       # antes de escuchar → el navegador daba 'conexión rechazada'. No-op en Mac.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

# Token de sesión del server (nuevo en cada arranque). Viaja al front dentro del HTML.
TOKEN = secrets.token_urlsafe(16)

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
import dash  # noqa: E402,F401  paquete dash (necesario para `import dash.dev`); ya no
#                trae secciones generales (extraídas a feat/dashboard) — su descubrimiento
#                devuelve el conjunto vacío. Lo conservamos: dash._common lo usa el bus.
try:
    import dash.dev as _devdash  # noqa: E402  framework modular del DASHBOARD DE DEV:
    #                   cada sección de dev = dash/dev/<x>.py + <x>.js auto-descubierto
    #                   (dash/dev/README.md). En la DISTRO a clientes dash/dev/ se excluye
    #                   (make-dist.sh) → el modo --dev no aplica para clientes.
except Exception:
    _devdash = None

DEV_HTML = os.path.join(ROOT, "dashboard-dev.html")

try:
    import hubtheme as _hubtheme  # noqa: E402  motor de TEMAS (F1): al servir el
    #                   shell de dev se inyecta el skin del tema activo (settings
    #                   ui.theme / env WORKSPACE_THEME) como <style id="theme-css">
    #                   + body[data-theme=…]. Falla-suave: sin hubtheme el shell
    #                   se sirve tal cual (data-theme queda en el default olympo).
except Exception:
    _hubtheme = None

# Superficie de DEV: este server sirve SOLO el dashboard de dev (visor/switch de
# ramas git + pipeline). Lo activa `--dev` (vía `workspace dev`). Local-only, guard Y1.
# En `main` es el ÚNICO modo: el dashboard general se extrajo a feat/dashboard, así que
# sin --dev el server no expone ninguna superficie (404 a todo). DEV_MODE existe como
# flag para conservar el contrato histórico del handler (tests lo mockean).
DEV_MODE = False


def _read(path, limit=8000):
    try:
        return open(path, encoding="utf-8").read()[:limit]
    except Exception:
        return ""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass  # silencio

    # ── Guard de seguridad (capas A Host · B token · C Origin — ver docstring) ──
    def _allowed_hosts(self):
        port = self.server.server_address[1]
        return {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

    def _deny(self, why):
        # Para /api/* el cuerpo es JSON: el front parsea la respuesta como JSON
        # y un text/plain aquí reventaba en Safari como «SyntaxError: The string
        # did not match the expected pattern» en vez de un error legible.
        if self.path.split("?")[0].startswith("/api/"):
            self._send(403, json.dumps({"__err": why}).encode("utf-8"),
                       "application/json; charset=utf-8")
        else:
            self._send(403, why.encode("utf-8"), "text/plain; charset=utf-8")
        return False

    def _guard(self, need_token):
        public = getattr(self.server, "public", False)
        if not public:                                   # capa A — DNS-rebinding
            host = (self.headers.get("Host") or "").lower()
            if host not in self._allowed_hosts():
                return self._deny("bad host")
        if need_token or public:                         # capa B — CSRF (timing-safe)
            q = parse_qs(urlparse(self.path).query)
            tok = self.headers.get("X-WORKSPACE-Token") or (q.get("token") or [""])[0]
            if not hmac.compare_digest(tok or "", TOKEN):
                return self._deny("bad token")
        if self.command == "POST":                       # capa C — Origin en POSTs
            origin = self.headers.get("Origin") or ""
            if origin:
                netloc = (urlparse(origin).netloc or "").lower()
                ok = (netloc == (self.headers.get("Host") or "").lower()) if public \
                    else (netloc in self._allowed_hosts())
                if not ok:
                    return self._deny("bad origin")
        return True

    def _send(self, code, body, ctype):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        # CSP (defensa-en-profundidad, complementa el saneo de hubtheme F2):
        # aunque un tema/skin colara un recurso externo, el navegador NO lo
        # fetchea. Lo que el panel REALMENTE usa: CSS+JS inline del shell y
        # de dash/dev/*.js ('unsafe-inline'), fetch a su propio origen
        # (connect-src 'self'), imágenes data: (bocetos PNG del board) o del
        # propio server, fuentes del sistema (font-src por si un tema trae
        # @font-face con data:). TODO lo externo queda bloqueado.
        # 'self' en script/style-src: el dev panel ahora vendorea xterm.js/css
        # (dash/dev/vendor/, servidos en /vendor/) para la sección Terminal.
        # connect-src 'self' cubre el WebSocket ws:// al mismo origen (terminal).
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; font-src 'self' data:; frame-src 'self'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'none'")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        try:
            self.wfile.write(body)
        except Exception:
            pass

    def _json(self, obj):
        self._send(200, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                   "application/json; charset=utf-8")

    def _notfound(self, p):
        """404 ruta-consciente: JSON para /api/* (el front espera JSON; un
        `not found` text/plain era el «SyntaxError: The string did not match
        the expected pattern» de Safari cuando un server VIEJO — arrancado
        antes de un update — no conocía una ruta nueva del JS fresco), texto
        plano para el resto."""
        if p.startswith("/api/"):
            return self._send(
                404,
                json.dumps({"__err": "ruta desconocida: %s — este dashboard no "
                                     "tiene ese endpoint (¿server viejo? "
                                     "reinicia con `workspace dev`)" % p},
                           ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8")
        return self._send(404, b"not found", "text/plain; charset=utf-8")

    def _serve_vendor(self, p):
        """Sirve archivos vendoreados del dev panel (xterm.js/css) desde
        dash/dev/vendor/. Solo lectura, path sanitizado (guard realpath: sin `..`
        fuera del dir), tipos conocidos. Detrás del guard Y1."""
        base = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "dash", "dev", "vendor")
        full = os.path.normpath(os.path.join(base, p[len("/vendor/"):]))
        if not (full == base or full.startswith(base + os.sep)) or not os.path.isfile(full):
            return self._notfound(p)
        ext = os.path.splitext(full)[1].lower()
        ctype = {".js": "application/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8",
                 ".map": "application/json; charset=utf-8"}.get(
                     ext, "application/octet-stream")
        try:
            with open(full, "rb") as f:
                body = f.read()
        except Exception:
            return self._notfound(p)
        return self._send(200, body, ctype)

    def do_GET(self):
        p = self.path.split("?")[0]
        if DEV_MODE:
            # Superficie de DEV (shell mission-control): sirve SOLO la página de dev +
            # los endpoints de sus módulos auto-descubiertos (dash/dev/), todo detrás
            # del mismo guard Y1.
            if p in ("/", "/index.html"):
                # En loopback `/` NO exige token (solo capa A) y el HTML inyecta
                # window.WORKSPACE_TOKEN — protege de atacantes remotos, no de otros
                # usuarios locales. Supuesto single-user: ver "Modelo de amenaza"
                # en el docstring del módulo.
                if not self._guard(need_token=getattr(self.server, "public", False)):
                    return
                html = _read(DEV_HTML, 10 ** 7).replace(
                    "</head>", '<script>window.WORKSPACE_TOKEN=%s;</script></head>' % json.dumps(TOKEN))
                # TEMA activo (motor F1): tokens+skin del tema al <head> y su id
                # al body[data-theme] — el look llega pintado desde el server (sin
                # flash) y el switcher del shell solo swapea en vivo. Falla-suave.
                if _hubtheme is not None:
                    try:
                        T = _hubtheme.load()
                        html = html.replace(
                            "</head>", _hubtheme.style_block(T) + "\n</head>")
                        html = html.replace('data-theme="olympo"',
                                            'data-theme="%s"' % T["id"], 1)
                    except Exception:
                        pass
                # secciones de dev (dash/dev/<x>.js): inyectadas tras el script base del
                # shell (registerDevSection ya existe). AL FINAL un script que dispara
                # window.__bootDev() — el shell arranca GARANTIZADO tras registrar TODA
                # sección, sin depender del evento `load` (que puede tardar/bloquearse).
                if _devdash is not None:
                    inject = "".join('\n<script data-dev="%s">\n%s\n</script>' % (n, js)
                                     for n, js in _devdash.js_blobs())
                    inject += ('\n<script data-dev-boot="1">'
                               'window.__bootDev && window.__bootDev();</script>')
                    html = html.replace("</body>", inject + "\n</body>")
                return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
            if p.startswith("/vendor/"):
                # libs vendoreadas (xterm.js/css) — PÚBLICAS y estáticas. Solo capa A
                # (loopback): un <script src> del browser no puede mandar el token.
                if not self._guard(need_token=getattr(self.server, "public", False)):
                    return
                return self._serve_vendor(p)
            if not self._guard(need_token=True):
                return
            if _devdash is not None:
                # WebSocket (terminal): si es un Upgrade a una ruta WS registrada,
                # el handler HIJACKEA el socket (no vuelve por el flujo normal).
                if self.headers.get("Upgrade", "").lower() == "websocket":
                    wsfn = _devdash.ws_routes().get(p)
                    if wsfn:
                        self.close_connection = True   # el socket ya no es HTTP
                        try:
                            wsfn(self)
                        except Exception:
                            pass
                        return
                mfn = _devdash.get_routes().get(p)   # módulos dash/dev/ — ya pasaron _guard
                if mfn:
                    q = parse_qs(urlparse(self.path).query)
                    try:
                        return self._json(mfn(q))
                    except Exception as e:
                        return self._json({"__err": str(e)})
            return self._notfound(p)
        # Sin --dev no hay superficie general en main (extraída a feat/dashboard):
        # el server responde 404 a todo (tras el guard, para no filtrar nada).
        if not self._guard(need_token=getattr(self.server, "public", False)):
            return
        return self._notfound(p)

    def do_POST(self):
        # Endpoints de escritura. Solo el modo --dev tiene POSTs (p. ej. /api/dev/switch).
        if not self._guard(need_token=True):
            return
        p = self.path.split("?")[0]
        try:
            n = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(n) if n else b"{}"
            data = json.loads(body or b"{}")
        except Exception:
            data = {}
        if DEV_MODE:
            # Solo POSTs de módulos dash/dev/ (p.ej. /api/dev/switch); cualquier otro = 404.
            if _devdash is not None:
                mfn = _devdash.post_routes().get(p)   # ya pasó _guard arriba
                if mfn:
                    try:
                        return self._json(mfn(data))
                    except Exception as e:
                        return self._json({"__err": str(e)})
            return self._notfound(p)
        return self._notfound(p)


def main():
    global DEV_MODE
    args = sys.argv[1:]
    DEV_MODE = "--dev" in args
    host, port, no_open = "127.0.0.1", 9120, ("--no-open" in args)
    if "--port" in args:
        try:
            port = int(args[args.index("--port") + 1])
        except Exception:
            pass
    if "--host" in args:
        try:
            host = args[args.index("--host") + 1]
        except Exception:
            pass
    public = host not in ("127.0.0.1", "localhost", "::1")
    url = f"http://{host}:{port}"
    if public:   # modo red: el token va en la URL (la capa Host no aplica fuera de loopback)
        url += f"/?token={TOKEN}"
    try:
        srv = ThreadingHTTPServer((host, port), Handler)
    except OSError as e:
        print(f"WORKSPACE dashboard: no pude abrir http://{host}:{port} ({e}). "
              "¿Ya está corriendo? Prueba --port otro.")
        sys.exit(1)
    srv.public = public   # lo lee Handler._guard
    if DEV_MODE:
        label = "dashboard de DEV (ramas/versiones)"
    else:
        label = "dashboard (sin superficie — el general se extrajo a feat/dashboard; usa --dev)"
    print(f"WORKSPACE {label} → {url}   (Ctrl-C para parar)")
    if public:
        print("  ⚠ modo red (bind fuera de localhost) — protegido por token de sesión; "
              "comparte la URL completa solo con el equipo.")
    if not no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  dashboard detenido.")
        srv.shutdown()


if __name__ == "__main__":
    main()
