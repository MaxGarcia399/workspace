"""WORKSPACE · control/permiso_mcp.py — el servidor MCP (stdio) que contesta
los permisos de una corrida `claude -p` con `--permission-prompt-tool`
(la vía documentada para permisos sin pantalla).

Una sola herramienta, `pedir`. Claude Code la llama cuando algo necesita
permiso; la herramienta deja el pedido en la carpeta de la corrida
(WORKSPACE_CONTROL_PERMISOS) y espera la respuesta que escribe el conector
cuando el socio decide en la página. Sin respuesta a tiempo: niega.

Devuelve un solo bloque de texto con {"behavior":"allow"} o
{"behavior":"deny","message":…} (doc de Claude Code, «Permission prompt tool
returned an invalid result»; desde la 2.1.207 el allow no necesita
updatedInput) y sin structuredContent."""
import json
import os
import sys
import time

SERVIDOR = "workspace_permisos"
HERRAMIENTA = "pedir"
NOMBRE_COMPLETO = "mcp__%s__%s" % (SERVIDOR, HERRAMIENTA)
ENTORNO = "WORKSPACE_CONTROL_PERMISOS"
PROTOCOLOS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
#: Lo que espera la herramienta a que el socio conteste (después, niega).
ESPERA = float(os.environ.get("WORKSPACE_CONTROL_PERMISOS_ESPERA") or 600)
NEGADO = "El socio no lo permitió desde la página."


def escribir_json(ruta, datos):
    """Escritura atómica (el otro lado lee por sondeo)."""
    tmp = ruta + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(datos, fh, ensure_ascii=False)
    os.replace(tmp, ruta)


def _pedir(carpeta, args, espera=None):
    args = args if isinstance(args, dict) else {}
    pid = "%d-%d" % (os.getpid(), int(time.monotonic() * 1000))
    escribir_json(os.path.join(carpeta, "pedido-%s.json" % pid), {
        "id": pid, "herramienta": args.get("tool_name") or args.get("toolName") or "?",
        "entrada": args.get("input"), "tool_use_id": args.get("tool_use_id")})
    respuesta = os.path.join(carpeta, "respuesta-%s.json" % pid)
    limite = time.monotonic() + (ESPERA if espera is None else espera)
    while time.monotonic() < limite:
        if os.path.exists(respuesta):
            try:
                with open(respuesta, encoding="utf-8") as fh:
                    r = json.load(fh)
                if isinstance(r, dict) and r.get("behavior") in ("allow", "deny"):
                    try:
                        os.remove(respuesta)         # leída: quien cierra sabe que el motor ya la tiene (E9)
                    except OSError:
                        pass
                    return r
            except (OSError, ValueError):
                pass
        time.sleep(0.05)
    return {"behavior": "deny", "message": "Nadie contestó el permiso a tiempo."}


def atender(msg, carpeta):
    metodo, mid = msg.get("method"), msg.get("id")
    if not isinstance(metodo, str) or mid is None:
        return None
    p = msg.get("params") or {}
    if metodo == "initialize":
        v = p.get("protocolVersion")
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "protocolVersion": v if v in PROTOCOLOS else PROTOCOLOS[0],
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVIDOR, "version": "1"}}}
    if metodo == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if metodo == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [{
            "name": HERRAMIENTA,
            "description": "Pide al socio, en la página de Workspace, permiso para una herramienta.",
            "inputSchema": {"type": "object", "properties": {
                "tool_name": {"type": "string"}, "input": {"type": "object"},
                "tool_use_id": {"type": "string"}}}}]}}
    if metodo == "tools/call" and p.get("name") == HERRAMIENTA:
        if not carpeta or not os.path.isdir(carpeta):
            r = {"behavior": "deny", "message": "Sin carpeta de permisos."}
        else:
            r = _pedir(carpeta, p.get("arguments"))
        return {"jsonrpc": "2.0", "id": mid, "result": {
            "content": [{"type": "text", "text": json.dumps(r, ensure_ascii=False)}]}}
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": "Method not found"}}


def _en_utf8():
    """Su protocolo va en UTF-8. En Windows, sin PYTHONUTF8 (Claude Code no lo exporta), stdin y
    stdout van en cp1252: un nombre con «Ł» en el pedido tumbaba este MCP y una «ó» salía rota."""
    for flujo in (sys.stdin, sys.stdout):
        try:
            flujo.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


def main():
    _en_utf8()
    carpeta = os.environ.get(ENTORNO, "")
    for linea in sys.stdin:
        linea = linea.strip()
        if not linea:
            continue
        try:
            msg = json.loads(linea)
        except ValueError:
            continue
        resp = atender(msg, carpeta) if isinstance(msg, dict) else None
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
