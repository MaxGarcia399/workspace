#!/usr/bin/env python3
"""WORKSPACE · proyectos — app «Proyectos» (server local, stdlib 3.9+, cero deps).

APP INDEPENDIENTE, no una sección del dev panel: pantalla completa, puerto propio
(9122), código propio. La lanza el hub («Proyectos») vía `front.cmd_proyectos` →
`workspace proyectos`. El dashboard de dev (9121) y esta app coexisten sin tocarse.

QUÉ ES: una sola página con la VISTA GENERAL de todos los proyectos. El centro es
un MAPA CONCEPTUAL (nodos conectables); a la izquierda se desliza el DETALLE del
nodo; a la derecha, el CHAT con el agente que el usuario elija. Lo que se pensaba
en una conversación y se perdía queda anclado a un nodo del mapa.

  ┌───────────────────────────────────────────────┐
  │ selector de proyectos (color por proyecto)    │
  ├──────────┬──────────────────────┬─────────────┤
  │ DETALLE  │   MAPA CONCEPTUAL    │   AGENTE    │
  │ (izq)    │      (centro)        │   (der)     │
  └──────────┴──────────────────────┴─────────────┘

PIEZAS
  proyectos-app.html  el front entero (vanilla JS, inline, cero libs)
  proyectos_store.py  persistencia propia (~/.claude/workspace/proyectos/proyectos.json)
  proyectos_chat.py   el copiloto (headless.run_headless → model-agnostic)

SEGURIDAD — se REUSA el guard del dashboard (dashboard.Handler), no se reimplementa:
Host + token de sesión + Origin (las 3 capas contra CSRF/DNS-rebinding, misma
lección ClawBleed) + CSP. Código de seguridad duplicado es código que diverge: esta
app hereda el guard endurecido y cualquier mejora futura le llega gratis. Local-only
(bind a 127.0.0.1); el token nuevo de cada arranque viaja inyectado en el HTML —
mismo modelo de amenaza single-user documentado en dashboard.py.

Endpoints (todos detrás del guard) — v2 (almacén per-nodo):
  GET  /                             → la app (con el token inyectado)
  GET  /api/proyectos/state          → {projects, selection, colors, statuses}
  GET  /api/proyectos/agents         → {agents} (los registrados en esta máquina)
  GET  /api/proyectos/session/list   ?project_id&node_id            → {agents}
  GET  /api/proyectos/session/days   ?project_id&node_id&agent      → {days}
  GET  /api/proyectos/session/read   ?project_id&node_id&agent&dia? → {turns}
  GET  /api/proyectos/files          ?project_id&node_id            → {files}
  GET  /api/proyectos/resumen        ?project_id&node_id            → {text}
  GET  /api/proyectos/file/download  ?project_id&node_id&name  → attachment (binario)
  POST /api/proyectos/project/add    {name?, color?}
  POST /api/proyectos/project/update {project_id, name?, color?}
  POST /api/proyectos/project/delete {project_id}          (archiva a .papelera)
  POST /api/proyectos/node/add       {project_id, parent_id?, t?, x?, y?}
  POST /api/proyectos/node/update    {project_id, node_id, t?|x?|y?|st?|notes?|p?}
  POST /api/proyectos/node/delete    {project_id, node_id}  (archiva a .papelera)
  POST /api/proyectos/select         {project_id?, node_id?}
  POST /api/proyectos/chat           {project_id, node_id?, agent, text}
  POST /api/proyectos/resumen/set    {project_id, node_id, text}
  POST /api/proyectos/file/upload    {project_id, node_id, name, data_b64}

Flags: --port <n> (def 9122) · --host <h> · --no-open
"""
import json
import os
import sys
import webbrowser

from http.server import ThreadingHTTPServer

sys.dont_write_bytecode = True

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import dashboard                      # noqa: E402  guard Y1 + _send/_json/CSP
import proyectos_chat                 # noqa: E402  (api_agents: discovery de agentes)
import proyectos_chat_v2              # noqa: E402  chat v2 (hilo por nodo×agente)
import proyectos_fsstore as fs        # noqa: E402  almacén per-nodo (v2)
import proyectos_api_v2 as apiv2      # noqa: E402  adaptadores HTTP de sesiones/resumen/archivos

APP_HTML = os.path.join(ROOT, "proyectos-app.html")
DEFAULT_PORT = 9122                   # ≠ 9120 (dashboard) y ≠ 9121 (dev panel)
DOWNLOAD_ROUTE = "/api/proyectos/file/download"

# FLIP v2 (rama feat/proyectos-v2): el CRUD, el estado y el chat ahora corren
# sobre el almacén per-nodo (fsstore) + el chat por (nodo×agente). El
# `proyectos_store` monolítico queda como fuente de migración, no de runtime.
GET_ROUTES = {
    "/api/proyectos/state": fs.api_state,
    "/api/proyectos/agents": proyectos_chat.api_agents,
    "/api/proyectos/session/list": apiv2.api_session_agents,
    "/api/proyectos/session/days": apiv2.api_session_days,
    "/api/proyectos/session/read": apiv2.api_session_read,
    "/api/proyectos/files": apiv2.api_files,
    "/api/proyectos/resumen": apiv2.api_resumen_get,
}

POST_ROUTES = {
    "/api/proyectos/project/add": fs.api_add_project,
    "/api/proyectos/project/update": fs.api_update_project,
    "/api/proyectos/project/delete": fs.api_delete_project,
    "/api/proyectos/node/add": fs.api_add_node,
    "/api/proyectos/node/update": fs.api_update_node,
    "/api/proyectos/node/delete": fs.api_delete_node,
    "/api/proyectos/select": fs.api_select,
    "/api/proyectos/chat": proyectos_chat_v2.api_chat_v2,
    "/api/proyectos/resumen/set": apiv2.api_resumen_set,
    "/api/proyectos/file/upload": apiv2.api_file_upload,
}


def _read_app():
    try:
        with open(APP_HTML, encoding="utf-8") as fh:
            return fh.read()
    except OSError:
        return ("<!doctype html><meta charset=utf-8><title>Proyectos</title>"
                "<body style='font:15px system-ui;background:#0e0e11;color:#e6e6e8;"
                "padding:40px'>No encontré <code>proyectos-app.html</code> junto al "
                "server. Reinstala o vuelve a abrir la app desde el hub.")


class Handler(dashboard.Handler):
    """El handler de la app. Hereda del dashboard el guard de 3 capas
    (_guard: Host + token + Origin), el emisor con CSP (_send/_json) y el
    silencio de logs — y REEMPLAZA el ruteo por el de esta app (el modo --dev
    del dashboard no existe aquí)."""

    def _notfound(self, p):
        if p.startswith("/api/"):
            return self._send(
                404,
                json.dumps({"__err": "ruta desconocida: %s — la app «Proyectos» no "
                                     "tiene ese endpoint (¿server viejo? vuelve a "
                                     "abrirla desde el hub)" % p},
                           ensure_ascii=False).encode("utf-8"),
                "application/json; charset=utf-8")
        return self._send(404, b"not found", "text/plain; charset=utf-8")

    def do_GET(self):
        p = self.path.split("?")[0]
        if p in ("/", "/index.html"):
            # En loopback `/` no exige token (solo capa Host) y el HTML lleva el
            # token inyectado, igual que el dev panel: protege de atacantes
            # remotos, no de otro usuario del mismo SO (supuesto single-user —
            # ver «Modelo de amenaza» en dashboard.py).
            if not self._guard(need_token=getattr(self.server, "public", False)):
                return
            # El token se inyecta en el cierre REAL del head (el ÚLTIMO), no en el
            # primer match: el docstring del HTML menciona la etiqueta de cierre
            # en PROSA, y un replace(…, 1) la tomaba a ELLA → el <script> caía
            # dentro del comentario, window.WORKSPACE_TOKEN nunca se definía, y
            # TODA llamada al API daba 403 «bad token» → la app cargaba VACÍA sin
            # error visible. rpartition ancla al último: inmune a que la prosa
            # vuelva a nombrar la etiqueta.
            raw = _read_app()
            head, sep, tail = raw.rpartition("</head>")
            html = (head + "<script>window.WORKSPACE_TOKEN=%s;</script>"
                    % json.dumps(dashboard.TOKEN) + sep + tail) if sep else raw
            return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8")
        if not self._guard(need_token=True):
            return
        from urllib.parse import urlparse, parse_qs
        q = parse_qs(urlparse(self.path).query)
        if p == DOWNLOAD_ROUTE:                      # descarga binaria (attachment)
            try:
                res = apiv2.file_download(q)
            except Exception:
                res = None
            if not res:
                return self._send(404, b"archivo no encontrado",
                                  "text/plain; charset=utf-8")
            return self._download(res[0], res[1])
        fn = GET_ROUTES.get(p)
        if fn:
            try:
                return self._json(fn(q))
            except Exception as e:                  # nunca 500 pelón al front
                return self._json({"__err": type(e).__name__})
        return self._notfound(p)

    def _download(self, name, raw):
        """Sirve `raw` como DESCARGA (attachment), nunca inline ni ejecutable.
        No usa `_send` porque necesita headers propios; replica su endurecimiento:
          · Content-Type octet-stream + X-Content-Type-Options nosniff → el
            navegador NO adivina el tipo ni renderiza (un .svg/.html se baja, no
            se ejecuta).
          · Content-Disposition: attachment + filename* (RFC5987) → descarga con
            nombre unicode seguro, sin problemas de comillas.
          · CSP default-src 'none'; sandbox → aunque algo se abriera, no corre nada.
        Se llama SOLO tras _guard(need_token=True)."""
        from urllib.parse import quote
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Content-Disposition",
                         "attachment; filename*=UTF-8''%s" % quote(name))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
        self.end_headers()
        try:
            self.wfile.write(raw)
        except Exception:
            pass

    def do_POST(self):
        if not self._guard(need_token=True):
            return
        p = self.path.split("?")[0]
        try:
            n = int(self.headers.get("Content-Length", 0))
            data = json.loads(self.rfile.read(n) if n else b"{}")
        except Exception:
            data = {}
        if not isinstance(data, dict):
            data = {}
        fn = POST_ROUTES.get(p)
        if fn:
            try:
                return self._json(fn(data))
            except Exception as e:
                return self._json({"__err": type(e).__name__})
        return self._notfound(p)


def main():
    args = sys.argv[1:]
    host, port, no_open = "127.0.0.1", DEFAULT_PORT, ("--no-open" in args)
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
    url = "http://%s:%d" % (host, port)
    if public:            # fuera de loopback la capa Host no aplica → token en la URL
        url += "/?token=%s" % dashboard.TOKEN
    try:
        srv = ThreadingHTTPServer((host, port), Handler)
    except OSError as e:
        print("WORKSPACE proyectos: no pude abrir http://%s:%d (%s). ¿Ya está "
              "corriendo? Prueba --port otro." % (host, port, e))
        sys.exit(1)
    srv.public = public   # lo lee el guard heredado
    print("WORKSPACE proyectos (mapa de proyectos) → %s   (Ctrl-C para parar)" % url)
    if public:
        print("  ⚠ modo red (bind fuera de localhost) — protegido por token de "
              "sesión; comparte la URL completa solo con quien deba verla.")
    if not no_open:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n  proyectos detenido.")
        srv.shutdown()


if __name__ == "__main__":
    main()
