"""Escritorio · las fichas de los permisos de SU MOTOR (Monito ronda 2 · P5-a y P2-b), del lado del puente.

De la foto de la página (`fichas`: control/ausente.para_la_foto) al evento que la app del monito convierte en fichas:

    {"t": "fichas", "agente", "motor": "Claude Code",
     "esperan": [{"id", "clase", "dato", "opciones", "nota"}],     ← su motor espera tu clic (todos, no solo el primero)
     "despues": [{"id", "clase", "dato", "pedido"}],               ← quedaron para después (no estabas)
     "interrumpidos": 2}                                           ← sin contestar por un reinicio de la página (E9)

`clase` y `dato` salen de lo ESTRUCTURADO del pedido (la herramienta y su entrada: control/base.que_permiso); el texto
de la ficha lo arma la app con su catálogo por clase. De aquí nunca sale una frase escrita por el agente: `dato` es el
dato del pedido (el comando, el archivo, la dirección), que la ficha enseña como dato.

Y lo que haces en una ficha que quedó para después: {"op": "permiso_despues", "agente", "ids", "decision"} →
/api/v2/permiso_despues (un pase de un solo uso para exactamente ese pedido y un mensaje nuevo). Stdlib."""
import json

#: Las clases que la app conoce (su catálogo de frases). Lo que no reconoce es «otra».
CLASES = ("comando", "crear", "cambiar", "borrar", "leer", "buscar", "pagina", "internet", "otra")
TOPE_DATO = 600


def _entrada(detalle):
    if isinstance(detalle, dict):
        return detalle
    try:
        d = json.loads(detalle) if isinstance(detalle, str) and detalle.lstrip().startswith("{") else None
    except ValueError:
        d = None
    return d if isinstance(d, dict) else {}


def clase_y_dato(pm):
    """(clase, dato) de un pedido de la foto: {herramienta, detalle, archivo, que: {clase, comando, ruta}}."""
    c, dato, _ = clase_dato_cortado(pm)
    return c, dato


def clase_dato_cortado(pm):
    """(clase, dato, cortado). M-2: `cortado` = el dato NO cabe entero en la ficha (el comando venía más largo, o los
    datos de una herramienta que la app no conoce): la ficha lo dice y no deja permitirlo ahí. Una herramienta «otra»
    (cualquier MCP) lleva su nombre Y lo que manda, no solo el nombre."""
    pm = pm if isinstance(pm, dict) else {}
    que = pm.get("que") if isinstance(pm.get("que"), dict) else {}
    c = str(que.get("clase") or "otra")
    d = _entrada(pm.get("detalle"))
    dato = ""
    if c == "comando":
        dato = str(que.get("comando") or d.get("command") or d.get("cmd") or "")
    elif c in ("crear", "cambiar", "borrar", "leer"):
        dato = str(que.get("ruta") or pm.get("archivo") or "")
    elif c == "buscar":
        dato = str(d.get("pattern") or d.get("query") or "")
    elif c == "web":
        url, consulta = str(d.get("url") or ""), str(d.get("query") or "")
        c = "pagina" if url else "internet"
        dato = url or consulta
    if c not in CLASES:
        c = "otra"
    cortado = bool(que.get("cortado"))
    if c == "otra":
        nombre, manda = str(pm.get("herramienta") or ""), pm.get("detalle")
        if isinstance(manda, (dict, list)):
            manda = json.dumps(manda, ensure_ascii=False, sort_keys=True)
        manda = str(manda or "").strip()
        if manda.endswith("…"):                       # la página ya lo traía recortado (control/base.corto)
            cortado = True
        dato = (nombre + " " + manda).strip() if manda not in ("", "{}") else nombre
    plano = " ".join(dato.split())
    if len(plano) > TOPE_DATO:
        cortado = True
    return c, plano[:TOPE_DATO], cortado


def evento(aid, fichas, motor="", decididos=None, palabras=None):
    """El evento «fichas» de un agente. `palabras(pm)`: cliente.evento_permiso (sus opciones del monito y su nota de
    grupo); `decididos`: los que ya contestaste aquí (la foto tarda en enterarse)."""
    fichas = fichas if isinstance(fichas, dict) else {}
    ya = decididos or {}
    esperan = []
    for pm in fichas.get("esperan") or []:
        if not isinstance(pm, dict) or not pm.get("id") or pm["id"] in ya:
            continue
        c, dato, cortado = clase_dato_cortado(pm)
        ops, nota = ["permitir", "negar"], ""
        if palabras is not None:
            try:
                ev = palabras(pm)
                ops = [o for o in ev.get("opciones") or [] if o in ("permitir", "permitir_turno", "negar")] or ops
                nota = str((ev.get("grupo") or {}).get("nota") or "")[:240]
            except Exception:
                pass
        esperan.append({"id": str(pm["id"]), "clase": c, "dato": dato, "opciones": ops, "nota": nota})
        if cortado:
            esperan[-1]["cortado"] = True
    despues = []
    for pm in fichas.get("despues") or []:
        if not isinstance(pm, dict) or not pm.get("id"):
            continue
        c, dato, cortado = clase_dato_cortado(pm)
        despues.append({"id": str(pm["id"]), "clase": c, "dato": dato, "pedido": float(pm.get("pedido") or 0)})
        if cortado:
            despues[-1]["cortado"] = True
    try:
        cortados = max(0, min(99, int(fichas.get("interrumpidos") or 0)))
    except (TypeError, ValueError):
        cortados = 0
    return {"t": "fichas", "agente": aid, "motor": str(motor or ""), "esperan": esperan, "despues": despues,
            "interrumpidos": cortados}


def op_despues(puente, aid, op):
    """«Permitir y seguir» (o «No») de fichas que quedaron para después. → True si salió."""
    ids = [str(i) for i in (op.get("ids") or []) if isinstance(i, str) and i][:40]
    d = str(op.get("decision") or "")
    if not ids or d not in ("permitir", "negar"):
        return False
    marca = puente._marca(aid) if d == "permitir" else None
    puente.srv.post("/api/v2/permiso_despues", {"agente": aid, "ids": ids, "decision": d})
    if d == "permitir":                     # salió un mensaje nuevo a su conversación del monito: es un turno
        puente.turnos[aid] = {"marca": marca, "visto": False, "t": puente.reloj()}
        puente.dicho.setdefault(aid, {}).pop("parcial", None)
        puente._abrir_manos(aid)
    return True
