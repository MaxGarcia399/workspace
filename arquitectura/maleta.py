#!/usr/bin/env python3
"""WORKSPACE · arquitectura/maleta — la maleta de la pestaña sin IA, desde el registro de eventos (F5).

Lo último de la pestaña en cada motor, para seguir (en el mismo o en otro): lo último que pidió el socio, lo último
que respondió el agente, las herramientas que usó en esa sesión y los pendientes abiertos de la pestaña. Sale del
registro de eventos (arquitectura/registro: lo que anotan los hooks del paquete), nunca de un transcript.

  · Se escribe al cerrar: el hook del paquete en `session_end`.
  · Si la sesión se cortó sin `session_end` (la X, el proceso muerto), se escribe al detectarlo: cuando la
    pestaña se vuelve a abrir (sesion.para_lanzar), antes de que el arranque la lea.
  · La lee el arranque de la siguiente sesión con el paquete de F6 (memoria.paquete → la sección de la maleta):
    el formato es el de siempre (memoria.poner_seccion), una sección por motor.

En los motores con vía por sesión y el paquete encendido, esta es LA maleta: la de hoy (sacada del transcript)
calla (memoria.actualizar_maleta). Los demás siguen con la de hoy. Stdlib; falla-suave."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.dirname(AQUI)
if RAIZ_REPO not in sys.path:
    sys.path.insert(0, RAIZ_REPO)

PEDIDOS = 4
TOPE_PEDIDO = 280
TOPE_RESPUESTA = 700
MAX_HERRAMIENTAS = 8
MAX_PENDIENTES = 5


def _de_la_pestana(eventos, motor):
    """Los eventos de `motor` en su terminal (las corridas de la página tienen su propia maleta)."""
    return [e for e in eventos if e.get("motor") == motor and (e.get("datos") or {}).get("via") != "pagina"]


def ultima_sesion(eventos):
    """Los eventos desde el último inicio de sesión (o todos, si no hubo inicio)."""
    for i in range(len(eventos) - 1, -1, -1):
        if eventos[i]["momento"] == "session_start":
            return eventos[i:]
    return list(eventos)


def cerrada(eventos):
    """¿La última sesión terminó con su session_end?"""
    ses = ultima_sesion(eventos)
    return bool(ses) and ses[-1]["momento"] == "session_end"


def pendientes(brain, tab):
    """Los pendientes abiertos de la pestaña (lo vigente de su memoria), o []."""
    try:
        import memoria
        ficha = memoria.Ficha(memoria._leer_vista(memoria.ficha_path(brain, tab)))
        return [v for v in memoria.vigente(ficha) if v.get("tipo") == "pendiente"]
    except Exception:
        return []


def extracto(eventos, motor, brain="", tab=""):
    """{"lineas", "turnos"} de la sección de `motor`, o None si no hay nada que contar."""
    import memoria
    evs = _de_la_pestana(eventos, motor)
    if not evs:
        return None
    pedidos = [str((e.get("datos") or {}).get("prompt") or "") for e in evs if e["momento"] == "user_prompt"]
    pedidos = [p for p in pedidos if p.strip() and not p.lstrip().startswith(memoria._ARRANQUES)]
    respuestas = [str((e.get("datos") or {}).get("last_assistant_message") or "") for e in evs
                  if e["momento"] == "turn_end"]
    respuestas = [r for r in respuestas if r.strip()]
    turnos = sum(1 for e in evs if e["momento"] == "turn_end")
    usadas = {}
    for e in ultima_sesion(evs):
        if e["momento"] == "pre_tool":
            n = str((e.get("datos") or {}).get("tool_name") or "").strip()
            if n:
                usadas[n] = usadas.get(n, 0) + 1
    if not pedidos and not respuestas:
        return None
    out = []
    if pedidos:
        out.append("Lo último que pidió el socio:")
        out += ["- " + memoria._limpio_o_omitido(p, TOPE_PEDIDO) for p in pedidos[-PEDIDOS:]]
    if respuestas:
        out.append("La última respuesta del agente:")
        out.append("> " + memoria._limpio_o_omitido(respuestas[-1], TOPE_RESPUESTA))
    if usadas:
        top = sorted(usadas.items(), key=lambda kv: (-kv[1], kv[0]))[:MAX_HERRAMIENTAS]
        out.append("Herramientas que usó: " + ", ".join("%s ×%d" % kv if kv[1] > 1 else kv[0] for kv in top))
    abiertos = pendientes(brain, tab) if brain and tab else []
    if abiertos:
        out.append("Pendientes abiertos de la pestaña:")
        out += ["- %s: %s" % (v.get("id") or "?", memoria._limpio_o_omitido(v.get("texto") or "", 200))
                for v in abiertos[:MAX_PENDIENTES]]
    return {"lineas": out, "turnos": turnos}


def escribir(brain, pestana, tab, motor):
    """Rehace la sección de `motor` en la maleta de la pestaña `tab` (memoria), desde los eventos de la pestaña
    `pestana` (registro). Idempotente. True si escribió."""
    try:
        import memoria
        from arquitectura import registro
        if not (brain and pestana and tab and motor):
            return False
        ex = extracto(registro.leer(brain, pestana)[0], motor, brain=brain, tab=tab)
        if not ex:
            return False
        return memoria.poner_seccion(memoria.raiz_cerebro(brain), tab, motor, ex["lineas"], ex["turnos"],
                                     si_cambio=True, espera=2)
    except Exception:
        return False


def al_abrir(brain, pestana, tab):
    """Al abrir la pestaña, antes de que el arranque la lea: rehace la maleta de cada motor de la pestaña desde
    sus eventos. Cubre la sesión que se cortó sin session_end (la X, el proceso muerto) y el hook de cierre que no
    supo el nombre de la pestaña; si nada cambió, no reescribe. → [(motor, cerrada)] de lo que escribió."""
    hechos = []
    try:
        from arquitectura import registro
        evs = registro.leer(brain, pestana)[0]
        motores = []
        for e in evs:
            m = e.get("motor") or ""
            if m and m not in motores and (e.get("datos") or {}).get("via") != "pagina" and not maleta_de_hoy(m):
                motores.append(m)
        for m in motores:
            if escribir(brain, pestana, tab, m):
                hechos.append((m, cerrada(_de_la_pestana(evs, m))))
    except Exception:
        pass
    return hechos


def maleta_de_hoy(motor):
    """¿La maleta de `motor` sigue saliendo de lo de hoy (su transcript, memoria.actualizar_maleta) y no de los eventos?
    Con solo sus hooks (solo_hooks) o con una ficha que lo dice (`sesion.maleta_del_transcript`: sus avisos no dan tu
    mensaje o su respuesta; Copilot y Cursor, cierre de la auditoría del 19-nov). Aquí nunca se lee un transcript: lo
    hace la de hoy, como en Codex, Kiro, Antigravity y OpenClaw. Sin ficha: False."""
    if solo_hooks(motor):
        return True
    try:
        from arquitectura import contrato
        return bool((contrato.ficha(motor).get("sesion") or {}).get("maleta_del_transcript"))
    except Exception:
        return False


def solo_hooks(motor):
    """hooks5: ¿la vía por sesión de `motor` carga SOLO sus hooks (`sesion.sin_nucleo`: Codex, Antigravity)? Su
    maleta sigue saliendo de lo de hoy: sus hooks pueden no correr (Codex los corre cuando el socio los confía) o no
    tener cierre (Antigravity), y dos maletas de un mismo motor se pisarían. Sin ficha: False."""
    try:
        from arquitectura import contrato
        return bool((contrato.ficha(motor).get("sesion") or {}).get("sin_nucleo"))
    except Exception:
        return False


def la_escribe_el_nucleo(motor, env=None):
    """¿La maleta de `motor` sale de los eventos (y la del transcript calla)? Con el paquete por sesión encendido
    y una ficha con vía por sesión (sus hooks anotan el registro), salvo la que sigue con la de hoy (maleta_de_hoy:
    solo sus hooks, o sus avisos no dan tu mensaje o su respuesta)."""
    try:
        from arquitectura import contrato, sesion
        if not sesion.activo(env):
            return False
        s = contrato.ficha(motor).get("sesion") or {}
        return bool(s) and "no" not in s and not s.get("sin_nucleo") and not s.get("maleta_del_transcript")
    except Exception:
        return False
