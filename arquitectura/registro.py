#!/usr/bin/env python3
"""WORKSPACE · arquitectura/registro — el registro de eventos de cada pestaña (F1).

Lo llena el hook del paquete en cada momento (session_start, user_prompt,
pre_tool, post_tool, permission_request, turn_end, compact, session_end) y lo
lee la página: el estado en vivo sale de aquí, no de la pantalla.

- Un evento por renglón (JSON): {"ts", "momento", "motor", "session_id", "datos"}.
  Además el renglón «conversacion» (no es un momento): el número oficial de la
  conversación, fijado al abrir o dicho por el hook de inicio (D3-a).
- Solo se anexa, con UNA escritura O_APPEND por renglón (corto: los datos van
  recortados), así dos hooks a la vez no se mezclan. Nunca se reescribe.
- Vive en la máquina (estado per-máquina de Workspace), sin sincronizarse:
  `<estado>/arquitectura/eventos/<cerebro>/<pestaña>.jsonl`.
- Lo que no se guarda: los argumentos de las herramientas ni su resultado. Del
  mensaje del socio y de la respuesta, solo un recorte.

Un renglón que no se lee (a medio escribir) se salta. Falla-suave: anotar nunca
levanta; leer devuelve [] si no hay nada.
"""
import datetime as _dt
import hashlib
import json
import os
import re

import paths as _paths

MOMENTOS = ("session_start", "user_prompt", "pre_tool", "post_tool", "permission_request",
            "turn_end", "compact", "session_end")
CONVERSACION = "conversacion"
#: Un error del motor (no es un momento del hook: lo anota la página cuando la capa de
#: control lo avisa). El estado en vivo no cambia por él; la página lo enseña en su tarjeta.
ERROR = "error"
#: Lo que dice el agente por el MCP núcleo (F6): en qué está (`tarea_actual`) y lo que una
#: skill le pregunta al socio (`preguntar`), con su respuesta. Tampoco son momentos del hook.
TAREA = "tarea"
PREGUNTA = "pregunta"
RESPUESTA = "respuesta"
#: modo chat: un archivo que el agente le enseña al socio (`mostrar_archivo`): la página lo pinta como su tarjeta en el
#: turno donde lo enseñó. Solo su ruta dentro del cerebro y su título.
ARCHIVO = "archivo"
_NO_MOMENTOS = (CONVERSACION, ERROR, TAREA, PREGUNTA, RESPUESTA, ARCHIVO)
_TIPOS = MOMENTOS + _NO_MOMENTOS
#: Lo que la página misma anota lleva `origen` «pagina» (pagina_v2._al_registro). Los avisos del motor en una corrida
#: de la página llevan via «pagina» SIN ese origen: son su eco. Claude Code abre y cierra una sesión por turno
#: (`claude -p`); el PreInvocation de Antigravity da un user_prompt por cada llamada al modelo.
ORIGEN_PAGINA = "pagina"


def eco_de_la_pagina(e):
    """¿Un aviso del motor en una corrida de la página? No es tu mensaje ni abre o cierra tu sesión: lo tuyo en la
    página lo anota ella (con su origen) y lo de su terminal no lleva via (tampoco en la conversación compartida, F4)."""
    d = e.get("datos") or {}
    return d.get("via") == "pagina" and d.get("origen") != ORIGEN_PAGINA
#: Topes de lo que se guarda de cada campo. Tu mensaje y la respuesta van enteros (la
#: página arma con ellos la conversación, F3) hasta un tope generoso; lo demás, corto.
TOPES = {"prompt": 64000, "last_assistant_message": 64000, "tool_name": 80, "source": 20,
         "reason": 60, "phase": 10, "trigger": 10, "fuente": 20, "paquete": 40, "detalle": 400,
         "via": 12, "permiso_id": 120, "motivo": 20, "mensaje": 600, "tarea": 60,
         "pregunta": 500, "respuesta": 2000, "tipo": 12, "id": 40, "paso": 64, "ruta": 1000, "titulo": 120}
_LISTA_MAX = 20
_SLUG = re.compile(r"[^A-Za-z0-9._-]+")


def carpeta(brain):
    """La carpeta de los registros de un cerebro (una por cerebro, por máquina)."""
    clave = hashlib.sha1(os.path.realpath(str(brain)).encode("utf-8")).hexdigest()[:16]
    return os.path.join(_paths.state_dir(), "arquitectura", "eventos", clave)


def _nombre(pestana):
    s = _SLUG.sub("_", str(pestana or "").strip())[:80].strip("._")
    return s or "_"


def ruta(brain, pestana):
    return os.path.join(carpeta(brain), _nombre(pestana) + ".jsonl")


def _recorta(datos):
    out = {}
    for k, v in (datos or {}).items():
        if isinstance(v, str):
            out[k] = v[:TOPES.get(k, 200)]
        elif isinstance(v, bool) or isinstance(v, (int, float)) or v is None:
            out[k] = v
        elif isinstance(v, list):
            out[k] = [str(x)[:300] for x in v[:_LISTA_MAX]]
    return out


def ahora_utc():
    """La hora de un renglón: UTC con Z y milisegundos («2026-11-18T06:44:07.151Z»), la misma zona
    que los turnos de la página: así se ordenan juntos."""
    d = _dt.datetime.now(_dt.timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (d.microsecond // 1000)


def ts_utc(ts):
    """Una hora de un evento en UTC con Z. Las que se escribieron antes sin zona (hora local de la
    máquina, «2026-11-18T00:44:07.151») se leen como locales. '' si no se entiende."""
    s = str(ts or "").strip()
    if not s:
        return ""
    try:
        d = _dt.datetime.fromisoformat(s[:-1] + "+00:00" if s.endswith(("Z", "z")) else s)
    except ValueError:
        return ""
    if d.tzinfo is None:
        d = d.astimezone()                       # sin zona: la hora local de esta máquina
    d = d.astimezone(_dt.timezone.utc)
    return d.strftime("%Y-%m-%dT%H:%M:%S.") + "%03dZ" % (d.microsecond // 1000)


def anotar(brain, pestana, momento, motor="", session_id="", datos=None):
    """Anexa un renglón. True si quedó escrito. Nunca levanta."""
    try:
        if momento not in _TIPOS:
            return False
        r = ruta(brain, pestana)
        os.makedirs(os.path.dirname(r), exist_ok=True)
        ev = {"ts": ahora_utc(), "momento": momento,
              "motor": str(motor or "")[:40], "session_id": str(session_id or "")[:200],
              "datos": _recorta(datos)}
        linea = (json.dumps(ev, ensure_ascii=False) + "\n").encode("utf-8")
        fd = os.open(r, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
        try:
            os.write(fd, linea)
        finally:
            os.close(fd)
        return True
    except Exception:
        return False


def leer(brain, pestana, desde=0):
    """(eventos, fin): los renglones completos desde el byte `desde`; uno a medio
    escribir se deja para la siguiente lectura. Cada evento trae `pos`, el byte donde
    empieza su renglón: como el archivo solo crece, es su id estable. Su `ts` sale en UTC con Z
    (los renglones de antes, en hora local sin zona, se normalizan aquí)."""
    try:
        with open(ruta(brain, pestana), "rb") as fh:
            fh.seek(desde)
            crudo = fh.read()
    except OSError:
        return [], desde
    fin = crudo.rfind(b"\n") + 1
    out, pos = [], desde
    for ln in crudo[:fin].split(b"\n")[:-1] if fin else []:
        try:
            e = json.loads(ln.decode("utf-8")) if ln.strip() else None
        except (ValueError, UnicodeDecodeError):
            e = None
        if isinstance(e, dict) and e.get("momento") in _TIPOS:
            e["pos"] = pos
            if e.get("ts") and not str(e["ts"]).endswith("Z"):
                e["ts"] = ts_utc(e["ts"]) or e["ts"]
            out.append(e)
        pos += len(ln) + 1
    return out, desde + fin


# ── el número oficial de la conversación (D3-a) ────────────────────────────
def _indice(session_id):
    clave = hashlib.sha1(str(session_id).encode("utf-8")).hexdigest()[:24]
    return os.path.join(_paths.state_dir(), "arquitectura", "sesiones", clave + ".json")


def conversacion(brain, pestana, motor, session_id, fuente, paquete="", ws="", via=""):
    """Guarda en la pestaña el número oficial de su conversación (fijado al abrir:
    fuente «fijado» o «retomada»; o dicho por el hook de inicio: «hook_inicio») y
    el índice número → pestaña, para el hook que no hereda las variables de la
    pestaña (servicios compartidos). `ws` (el nombre de la pestaña, donde va su memoria) y
    `via` («pagina»: una conversación de la página, que no es su terminal) van también en el
    índice: el gateway de OpenClaw corre los avisos y el MCP sin el entorno de la pestaña."""
    if not session_id:
        return False
    datos = {"fuente": fuente, "paquete": paquete}
    if via:
        datos["via"] = via
    ok = anotar(brain, pestana, CONVERSACION, motor, session_id, datos)
    try:
        r = _indice(session_id)
        os.makedirs(os.path.dirname(r), exist_ok=True)
        tmp = r + ".%d.tmp" % os.getpid()
        fila = {"brain": os.path.realpath(str(brain)), "pestana": str(pestana), "motor": motor}
        if ws:
            fila["ws"] = str(ws)
        if via:
            fila["via"] = str(via)
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(fila, fh)
        os.replace(tmp, r)
    except OSError:
        pass
    return ok


def indice(session_id):
    """La fila del índice de un número de conversación ({brain, pestana, motor, ws?, via?}), o None."""
    if not session_id:
        return None
    try:
        with open(_indice(session_id), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) and d.get("brain") and d.get("pestana") else None
    except (OSError, ValueError, TypeError):
        return None


def pestana_de(session_id):
    """(cerebro, pestaña) de un número de conversación ya guardado, o None."""
    if not session_id:
        return None
    try:
        with open(_indice(session_id), encoding="utf-8") as fh:
            d = json.load(fh)
        return d["brain"], d["pestana"]
    except (OSError, ValueError, KeyError, TypeError):
        return None


def numero_oficial(eventos):
    """El número de la conversación de la pestaña: el último fijado, o si no hay,
    el que dijo el último inicio. '' si ninguno."""
    fijado = [e for e in eventos if e["momento"] == CONVERSACION and e.get("session_id")]
    if fijado:
        return fijado[-1]["session_id"]
    inicios = [e for e in eventos if e["momento"] == "session_start" and e.get("session_id")]
    return inicios[-1]["session_id"] if inicios else ""


def numero_de(brain, pestana, motor):
    """F5 · (número, visto) de la conversación de la pestaña EN ESE MOTOR: el último que el motor mismo dijo en
    sus hooks (también tras un /clear o un fork) o, si dijo uno antes, el último que Workspace le pasó al abrir
    (`conversacion`). `visto` = el motor ya lo usó (se retoma); si no, se crea con ese número. Las corridas de la
    página (via «pagina») son otra conversación y no cuentan. ('', False) si no hay."""
    numero, vistos = "", set()
    try:
        eventos = leer(brain, pestana)[0]
    except Exception:
        return "", False
    for e in eventos:
        sid = e.get("session_id") or ""
        if not sid or e.get("motor") != motor or (e.get("datos") or {}).get("via") == "pagina":
            continue
        if e["momento"] != CONVERSACION:
            vistos.add(sid)
        numero = sid
    return numero, numero in vistos


# ── el estado en vivo ──────────────────────────────────────────────────────
def estado(eventos):
    """Lo que dicen los eventos de la pestaña, sin mirar la pantalla:
    {"estado", "desde", "motor", "session_id", "herramienta"?, "turnos", "tarea"?, "pregunta"?}.

    estado: sin_datos · abierto · pensando · usando · esperando_permiso · listo ·
    cerrado. `tarea`: lo último que dijo el agente con tarea_actual (vacío la limpia; abrir
    o cerrar la sesión también). `pregunta`: la que una skill hizo y nadie contestó aún
    ({id, pregunta, tipo, opciones, paso, via}); abrir o cerrar la sesión la retira, y una
    «en el chat» se da por contestada con tu siguiente mensaje (de la página o de su terminal).
    El eco de una corrida de la página (eco_de_la_pagina) no la retira ni la contesta.
    Pura."""
    out = {"estado": "sin_datos", "desde": "", "motor": "", "session_id": numero_oficial(eventos),
           "turnos": 0}
    for e in eventos:
        m = e["momento"]
        datos = e.get("datos") or {}
        if m == TAREA:
            if datos.get("tarea"):
                out["tarea"] = datos["tarea"]
            else:
                out.pop("tarea", None)
            continue
        if m == PREGUNTA:
            out["pregunta"] = {k: datos.get(k) for k in ("id", "pregunta", "tipo", "opciones", "paso", "via")}
            continue
        if m == RESPUESTA:
            if (out.get("pregunta") or {}).get("id") == datos.get("id"):
                out.pop("pregunta", None)
            continue
        if m in _NO_MOMENTOS:
            continue
        eco = eco_de_la_pagina(e)
        if m in ("session_start", "session_end"):
            out.pop("tarea", None)
            if not eco:
                out.pop("pregunta", None)
        if m == "user_prompt" and not eco and (out.get("pregunta") or {}).get("via") != "formulario":
            out.pop("pregunta", None)
        nuevo = {"session_start": "abierto", "user_prompt": "pensando", "pre_tool": "usando",
                 "post_tool": "pensando", "permission_request": "esperando_permiso",
                 "turn_end": "listo", "session_end": "cerrado"}.get(m)
        if m == "compact":
            continue                         # compactar no cambia en qué está
        out["motor"] = e.get("motor") or out["motor"]
        out["turnos"] += m == "turn_end"
        if nuevo != out["estado"] or m == "pre_tool":
            out["desde"] = e.get("ts", "")
        out["estado"] = nuevo
        if m in ("pre_tool", "permission_request"):
            out["herramienta"] = (e.get("datos") or {}).get("tool_name", "")
        else:
            out.pop("herramienta", None)
    return out
