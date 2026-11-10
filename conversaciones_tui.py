#!/usr/bin/env python3
"""WORKSPACE · conversaciones_tui — la sección CONVERSACIONES del hub.

«Lo que tus agentes se dicen entre sí: sigue cada charla y corta cuando
quieras.» Las salas de varios agentes (salas.py, el dueño de
`conversaciones/<id>/`) con la UI que el socio aprobó: el prototipo v7
(prototipo_conversaciones.py, que se queda como está para comparar). Misma
pintura, mismo comportamiento; aquí los datos son reales y las acciones
también.

Tamaños (también al redimensionar en vivo):
  · ventanita (< 70 col o < 24 filas, el uso principal): como WhatsApp en el
    celular — la LISTA (tarjetas de 2 líneas ordenadas por actividad, ⚠ en
    rojo) o el CHAT («‹ título», integrantes, burbujas con su color), nunca
    mezclados; el pie dice lo que sirve en cada nivel y `?` todas las teclas;
  · chico (70–109): apilado, cabecera de 2 líneas, botones cortos;
  · mediano (110–149): lista y chat a todo lo ancho;
  · completo (≥ 150 × 45): el wordmark grande, la lista más ancha (44).
  Con poco alto se quita, en orden: el título grande, el pie, la descripción.

Cabecera estilo WhatsApp (tema, descripción, fichas de integrantes; `i` o clic
en el tema = info del grupo: participantes, turno, sync, objetivo, hecho
cuando, espera). Solo los problemas quedan arriba, en rojo: el sync caído o un
integrante cerrado con un pedido pendiente. Cada burbuja con el color de su
participante (agente + pestaña); el socio neutro y a la derecha; sin
truecolor, una barra de color.

Acciones (de verdad, por la API de salas.py; nada se edita a mano):
  e  Escribir: publica como socio, un `pide` al último agente que habló (o a
     quien nombres al empezar con «@nombre»)
  p  Pausar / Reanudar     c  Cerrar (dos veces)     r  Archivar (cerrada)
  b  Borrar (archivada; dos veces: lápida + purga)
  t  la espera de la sala (15 min … 24 h)
  m  Esperar 30 min más · x  Cancelar pedido (cuando venció)
  a  Abrir a <agente>: la sección sale y el hub abre su pestaña con
     `dispatch --open <id> --name <nombre>` (el mismo pedido de siempre)
  i  info del grupo · ? teclas · q salir

Refresco en vivo con stat incremental (salas.Almacen: un stat por carpeta, se
lee solo lo nuevo; la presencia se recalcula cada PRESENCIA_S). Estado propio,
solo local y fuera del cerebro: qué leyó el socio y en qué orden llegó cada
mensaje (para marcar «llegó tarde por el sync») — `<estado>/salas/hub.json`.

Mouse primero (Mac/Linux, SGR-1006 con movimiento): toda la fila, toda la
burbuja, el botón con su borde; reacciona al PRESIONAR, resalta bajo el
puntero, la rueda desplaza la columna de debajo. En Windows, teclado completo.
Stdlib, Python 3.9+.
"""
import json
import os
import re
import sys
import time
import uuid

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import hublayout as HL                                          # noqa: E402
import messages                                                 # noqa: E402
import salas                                                    # noqa: E402
import section_box as SB                                        # noqa: E402
import ventanita as VT                                          # noqa: E402
from _width import eaw as _eaw, sane as _sane                   # noqa: E402
from theme import screen as _theme_screen                       # noqa: E402

try:
    import i18n                                                 # noqa: E402
except Exception:
    i18n = None


def _t(key, es, **kw):
    s = es
    if i18n is not None:
        try:
            v = i18n.t(key)
            s = v if v != key else es
        except Exception:
            s = es
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


LW = 40                       # ancho de la lista (mediano; completo: LW_GRANDE)
LW_GRANDE = 44


def modo(w, h):
    """El tamaño, según la ventana: ventanita (monitor) · chico · mediano · completo."""
    if VT.es_ventanita(w, h):
        return "ventanita"
    if w < 110:
        return "chico"
    if w >= 150 and h >= 45:
        return "completo"
    return "mediano"


#: Mínimo de filas de mensajes antes de seguir quitando cosas por el alto.
MIN_MENSAJES = 10
ANCHO_DOS = 110               # desde aquí, dos columnas
ESPERAS = tuple((salas.espera_txt(m), m) for m in salas.ESPERAS)
ANCHO_ESPERA = 24             # el botón «[t] espera 30 min ▾»: fijo, no se mueve
#: Cada cuánto se mira si cambió algo (un stat por carpeta).
REFRESCO_S = 2.0
#: Cada cuánto se recalcula la presencia aunque no cambie ningún archivo.
PRESENCIA_S = 10.0
#: Cada cuánto se redibuja igual (los «faltan …» de la espera).
RELOJ_S = 20.0
ESTADO_ARCHIVO = os.path.join("salas", "hub.json")


def FILTROS():
    return (_t("conv.filter.active", "Activas"), _t("conv.filter.all", "Todas"),
            _t("conv.filter.archived", "Archivadas"))


# ═══════════════════════════════════════════════════════════════════════════
# Datos: las salas del almacén → la forma que pinta la UI aprobada
# ═══════════════════════════════════════════════════════════════════════════

def _hora(t):
    return time.strftime("%H:%M", time.localtime(t))


def _cuando(t, ahora=None):
    """La hora de un mensaje; si no es de hoy, con el día corto: «ayer 23:10»,
    «8 nov 23:10» (con el año si es de otro). Meses del catálogo, no del
    locale del sistema (igual en Mac y Windows)."""
    h = _hora(t)
    lt = time.localtime(t)
    hoy = time.localtime(time.time() if ahora is None else ahora)
    if lt[:3] == hoy[:3]:
        return h
    ayer = time.localtime(time.mktime((hoy.tm_year, hoy.tm_mon, hoy.tm_mday - 1, 12, 0, 0, 0, 0, -1)))
    if lt[:3] == ayer[:3]:
        return _t("conv.when.yesterday", "ayer {h}", h=h)
    meses = _t("conv.when.months", "ene feb mar abr may jun jul ago sep oct nov dic").split()
    mes = meses[lt.tm_mon - 1] if len(meses) == 12 else str(lt.tm_mon)
    if lt.tm_year == hoy.tm_year:
        return _t("conv.when.date", "{d} {m} {h}", d=lt.tm_mday, m=mes, h=h)
    return _t("conv.when.date_year", "{d} {m} {y} {h}", d=lt.tm_mday, m=mes, y=lt.tm_year, h=h)


def _dur(seg):
    return salas.falta_txt(seg)


def _espera_txt(mins):
    return dict((mm, lab) for lab, mm in ESPERAS).get(mins, salas.espera_txt(mins))


def _ruta_local():
    import paths
    return os.path.join(paths.state_dir(), ESTADO_ARCHIVO)


def _local():
    """{"leidos": {sala: [ids]}, "llegada": {sala: {"orden": [ids], "tarde":
    {id: id del que iba último}}}} — solo de esta máquina. Ilegible: se
    aparta (no se pisa) y va "ilegible": refrescar marca todo como leído (los
    «● N» no vuelven) y lo avisa. Con BOM se lee."""
    ruta = _ruta_local()
    d, est = salas._leer_json_estado(ruta)
    if est == "transitorio":             # no se pudo leer ahora: no se pisa; se relee al refrescar
        return {"leidos": {}, "llegada": {}, "_sin_apartar": True}
    if est == "ilegible":
        if not salas._apartar(ruta):     # sin apartarlo no se pisa: se reintenta al refrescar
            return {"leidos": {}, "llegada": {}, "ilegible": True, "_sin_apartar": True}
        return {"leidos": {}, "llegada": {}, "ilegible": True}
    if est != "ok":
        if salas._apartado_de(ruta):     # se apartó y el nuevo no se guardó: recuperación
            return {"leidos": {}, "llegada": {}, "ilegible": True}
        return {"leidos": {}, "llegada": {}}
    try:
        le = d.get("leidos") if isinstance(d.get("leidos"), dict) else {}
        ll = d.get("llegada") if isinstance(d.get("llegada"), dict) else {}
        return {"leidos": {str(k): [str(x) for x in v] for k, v in le.items()
                           if isinstance(v, list)},
                "llegada": {str(k): {"orden": [str(x) for x in (v.get("orden") or [])],
                                     "tarde": {str(a): str(b) for a, b in
                                               (v.get("tarde") or {}).items()}}
                            for k, v in ll.items() if isinstance(v, dict)}}
    except Exception:
        return {"leidos": {}, "llegada": {}}


def _guardar_local(est):
    if est.get("_sin_apartar"):          # el dañado sigue ahí: no se pisa
        return False
    try:
        import atomico
        atomico.escribir(_ruta_local(), json.dumps(
            {"version": 1, "leidos": est.get("leidos", {}), "llegada": est.get("llegada", {})},
            ensure_ascii=False) + "\n")
        return True
    except Exception:
        return False


_DISPLAY = {}


def _nombre_agente(a):
    """El nombre para mostrar del agente: el `display` de su agent.json si lo
    tiene; si no, el nombre con mayúscula. Se cachea por proceso."""
    if not a:
        return "?"
    if a not in _DISPLAY:
        n = ""
        try:
            import dispatch
            for e in dispatch.load_registry().get("agents", []):
                if e.get("name") == a:
                    n = str((dispatch.load_agent_cfg(e) or {}).get("display") or "")
                    break
        except Exception:
            n = ""
        _DISPLAY[a] = n or a.replace("-", " ").title().replace(" ", "-")
    return _DISPLAY[a]


def _nombre_motor(m):
    if not m:
        return ""
    try:
        import engines_tui
        return engines_tui.engine_name(m)
    except Exception:
        return m


_EST = {"escuchando": "escuchando", "trabajando": "trabajando", "cerrada": "cerrado",
        "desconocido": "desconocido"}


def _estado_txt(e):
    return {"escuchando": _t("conv.state.listening", "escuchando"),
            "trabajando": _t("conv.state.working", "trabajando"),
            "cerrado": _t("conv.state.closed", "pestaña cerrada"),
            "desconocido": _t("conv.state.unknown", "sin noticias"),
            "sin_entrar": _t("conv.state.not_in", "pestaña abierta, aún no entra"),
            "sin_unirse": _t("conv.state.not_joined", "aún no se une")}.get(e, e)


def _estado_invitado(sala, token, est, ahora, brains):
    """El estado de quien está invitado pero todavía no entró: con su pestaña
    abierta (lo dice la presencia o el registro de esta máquina) o «aún no
    se une» — nunca «sin pestaña», que no se puede saber."""
    if salas.pestana_abierta(sala, token, brains, ahora):
        return "sin_entrar"
    return "sin_unirse" if est.get("estado") != "cerrada" else "cerrado"


def _p(pid, agente, pestana, motor, maquina, estado, **kw):
    d = {"id": pid, "agente": agente, "pestana": pestana, "motor": motor,
         "maquina": maquina, "estado": estado}
    d.update(kw)
    return d


def _sis(txt, rojo=False, t=0.0):
    return {"k": "sis", "txt": txt, "rojo": rojo, "t": t}


def _clave(m):
    return salas._clave_orden(m)


def _llegada(local, sala):
    """Marca lo que llegó tarde por el sync: un mensaje nuevo que en el orden
    de pantalla (turno, participante, id) va ANTES que alguno que ya se
    veía — también con el mismo turno (dos máquinas que publican viendo el
    mismo turno: el choque más común). Va al final, tras el que iba último
    cuando llegó, bajo «llegó tarde por el sync» (nunca escondido a media
    conversación). Devuelve True si cambió el estado local."""
    reg = local["llegada"].get(sala["id"])
    ids = [m["id"] for m in sala["mensajes"]]
    if reg is None:
        local["llegada"][sala["id"]] = {"orden": ids, "tarde": {}}
        return True
    conocidos = set(reg["orden"])
    nuevos = [m for m in sala["mensajes"] if m["id"] not in conocidos]
    if not nuevos:
        return False
    for m in sorted(nuevos, key=lambda x: (x.get("mtime") or 0, x["id"])):
        vistos = [x for x in sala["mensajes"] if x["id"] in conocidos]
        if vistos:
            ult = max(vistos, key=_clave)
            if _clave(m) < _clave(ult):
                reg["tarde"][m["id"]] = ult["id"]
        reg["orden"].append(m["id"])
        conocidos.add(m["id"])
    return True


def _orden_pantalla(sala, tarde):
    """Los mensajes en el orden de pantalla: por (turno, participante, id), y
    los que llegaron tarde tras el que iba último cuando llegaron."""
    normales = [m for m in sala["mensajes"] if m["id"] not in tarde]
    por_ancla = {}
    for mid, ancla in tarde.items():
        por_ancla.setdefault(ancla, []).append(mid)
    por_id = {m["id"]: m for m in sala["mensajes"]}
    out = []
    for m in normales:
        out.append(m)
        for mid in por_ancla.get(m["id"], ()):
            if mid in por_id:
                out.append(por_id[mid])
    vistos = {m["id"] for m in out}
    out += [m for m in sala["mensajes"] if m["id"] not in vistos]
    return out


def _pid(conv_parts, token):
    """El destino de un mensaje → el id de su ficha (o «yo» si es el socio)."""
    if salas.es_socio(token):
        return "yo"
    if token in conv_parts:
        return token
    a = salas.agente_de(token)
    if ("?" + a) in conv_parts:
        return "?" + a
    return next((k for k, p in conv_parts.items() if p.get("slug") == a), token)


def _texto_evento(sala, e, nombres):
    """La línea de sistema de un evento, o None si no se pinta."""
    if not e.get("valido"):
        return None
    a, h = e["accion"], _hora(e["t"])
    tu = salas.es_socio(e.get("de"))
    quien = _t("conv.you_lower", "ti") if tu else nombres(e.get("de"))
    if a == "pausa":
        return _sis(_t("conv.sis.paused", "pausada por {a} · {h}", a=quien, h=h), t=e["t"])
    if a == "reanudar":
        return _sis(_t("conv.sis.resumed", "reanudada por {a} · {h}", a=quien, h=h), t=e["t"])
    if a == "cierre":
        if tu:
            return _sis(_t("conv.sis.closed_you", "cerrada por ti · los participantes paran · {h}",
                           h=h), True, e["t"])
        return _sis(_t("conv.sis.closed", "cerrada por {a} · {h}", a=quien, h=h), t=e["t"])
    if a == "archivar":
        return _sis(_t("conv.sis.archived", "archivada por {a}", a=quien), t=e["t"])
    if a == "espera":
        return _sis(_t("conv.sis.wait", "espera por respuesta: {e} · {h}",
                       e=_espera_txt(e["minutos"]), h=h), t=e["t"])
    p = sala["pedidos"].get(e.get("pedido") or "")
    para = ", ".join(nombres(d) for d in (p or {}).get("a", ())) or "?"
    if a == "mas_tiempo":
        return _sis(_t("conv.sis.more", "{e} más para {a} · {h}",
                       e=_espera_txt(e["minutos"]), a=para, h=h), t=e["t"])
    if a == "cancelar":
        return _sis(_t("conv.sis.cancelled", "pedido a {a} cancelado por {b} · {h}",
                       a=para, b=quien, h=h), t=e["t"])
    if a == "soltar" and e.get("por") == salas.POR_DECISOR:
        return _sis(_t("conv.sis.released_decider",
                       "◆ el decisor soltó el pedido a {a} (solo informa) · {h}", a=quien, h=h),
                    t=e["t"])
    if a == "soltar":
        return _sis(_t("conv.sis.released", "{a} soltó un pedido sin responder · {h}",
                       a=quien, h=h), t=e["t"])
    if a == "delegar":
        return _sis(_t("conv.sis.delegated", "{a} le pasó un pedido a {b} · {h}",
                       a=quien, b=nombres(e.get("en")), h=h), t=e["t"])
    if a == "tope":
        return _sis(_t("conv.sis.cap", "tope de turnos: {n} · {h}", n=e["minutos"], h=h),
                    t=e["t"])
    return None


_NOTA = {"alterado": ("conv.note.altered", "alterado: alguien editó este archivo; no se entregó"),
         "no_participa": ("conv.note.outsider", "de alguien que no participa: no se entregó"),
         "despues_del_cierre": ("conv.note.after", "llegó después del cierre: no se entregó"),
         "tope": ("conv.note.cap", "pasó el tope de turnos: no se entregó")}


def conv_de(sala, local, ahora=None, conocidas=None, brains=None):
    """Una sala → el dict que pinta la UI (el mismo del prototipo, con datos
    reales). Los no leídos solo cuentan para «● N» en la lista; cada mensaje
    lleva su hora (no «● nuevo»)."""
    ahora = ahora or time.time()
    parts = {}
    for k, p in sala["participantes"].items():
        est = salas.estado_participante(sala, k, ahora, brains)
        estado = (_EST.get(est.get("estado"), "desconocido") if p.get("unido")
                  else _estado_invitado(sala, k, est, ahora, brains))
        parts[k] = _p(k, _nombre_agente(p["agente"]), p.get("pestana") or "",
                      _nombre_motor(p.get("motor")),
                      messages.nombre_maquina(p.get("maquina"), conocidas) if p.get("maquina") else "",
                      estado, slug=p["agente"],
                      sesion=p.get("sesion") or "", maquina_eti=p.get("maquina") or "",
                      creador=p.get("creador"), unido=p.get("unido"))
    for a in sala["invitados"]:
        if not any(p.get("slug") == a for p in parts.values()):
            est = salas.estado_participante(sala, "?" + a, ahora, brains)
            parts["?" + a] = _p("?" + a, _nombre_agente(a), "", "", "",
                                _estado_invitado(sala, "?" + a, est, ahora, brains), slug=a,
                                sesion="",
                                maquina_eti="", creador=False, unido=False)

    def nombre(token):
        pid = _pid(parts, token)
        if pid == "yo":
            return _t("conv.you", "Tú")
        q = parts.get(pid)
        return q["agente"] if q else (salas.agente_de(token) or "?")
    reg = local["llegada"].get(sala["id"]) or {"tarde": {}}
    tarde = reg.get("tarde") or {}
    leidos = set(local["leidos"].get(sala["id"], ()))
    eventos = [x for x in (_texto_evento(sala, e, nombre) for e in sala["eventos"]
                           if e["accion"] not in ("unirse", "invitar", "espera_pedido", "lapida"))
               if x]
    avs = _avisos_panel(sala)
    for (_mid, clave), av in avs.items():           # lo que Workspace tecleó en un panel (aquí)
        if av.get("estado") == "avisado":
            eventos.append(_sis(_t("conv.sis.notified", "◆ avisé a {a} en su panel · {h}",
                                   a=nombre(clave), h=_hora(av.get("t") or 0)), t=av.get("t") or 0))
    unidos = [e for e in sala["eventos"] if e["accion"] == "unirse" and e.get("valido")
              and e["de"] in parts]
    items, msgs = [], []
    deli = salas.delicados() if (salas.decisor_encendido()
                                 and salas.decisor_encendido("workspace.security")) else {}
    for m in _orden_pantalla(sala, tarde):
        de = "yo" if salas.es_socio(m["de"]) else _pid(parts, m["de"])
        p = sala["pedidos"].get(m["id"])
        ped = None
        if p:
            ped = {"id": p["id"], "a": [_pid(parts, d) for d in p["a"]],
                   "listos": [_pid(parts, d) for d in p["listos"]], "mas": p["mas"],
                   "soltados": [_pid(parts, d) for d in p.get("soltados", ())],
                   "estado": {"esperando": "esperando", "cancelado": "cancelado",
                              "listo": "listo", "cerrado": "cerrado"}[p["estado"]],
                   "espera": p["espera"], "vence": p["vence"]}
        nota = ""
        if m["motivo"]:
            k, es = _NOTA.get(m["motivo"], ("", m["motivo"]))
            nota = _t(k, es) if k else es
        elif m["id"] in deli:                 # Decisores › Seguridad lo subió (solo sube)
            nota = _t("conv.note.delicate", "⚠ delicado: confírmalo con el socio")
        elif m.get("menciones_cortadas"):
            nota = _t("conv.note.mentions", "más de 2 menciones: solo cuentan dos")
        elif de == "yo":
            nota = _t("conv.note.socio", "guía: lo delicado se aprueba en la pestaña")
        msgs.append({"k": "msg", "id": m["id"], "de": de, "para": [_pid(parts, d) for d in m["destinos"]],
                     "t": m["t"], "tipo": m["tipo"],
                     "texto": [m.get("resumen") or salas._linea(m.get("cuerpo"), 200, 1)],
                     "cuerpo": m.get("cuerpo") or "",
                     "tarde": m["id"] in tarde, "pedido": ped, "nota": nota,
                     "alterado": m["firma"] == "alterado", "motivo": m["motivo"]})
    # los eventos, en su momento entre los mensajes; las uniones, juntas
    pend = sorted(eventos, key=lambda x: x["t"])
    j_pend = sorted(unidos, key=lambda e: e["t"])

    def unir(hasta=None):
        lote = []
        while j_pend and (hasta is None or j_pend[0]["t"] <= hasta):
            lote.append(j_pend.pop(0))
        if lote:
            ns = list(dict.fromkeys(nombre_corto({"parts": list(parts.values())}, e["de"])
                                    for e in lote))
            h = _hora(lote[-1]["t"])
            txt = (_t("conv.sis.joined_1", "{a} se unió · {h}", a=ns[0], h=h) if len(ns) == 1 else
                   _t("conv.sis.joined_n", "{a} y {b} se unieron · {h}",
                      a=", ".join(ns[:-1]), b=ns[-1], h=h))
            items.append(_sis(txt, t=lote[-1]["t"]))
    for m in msgs:
        if not m["tarde"]:
            unir(m["t"])
            while pend and pend[0]["t"] <= m["t"]:
                items.append(pend.pop(0))
        else:
            items.append(_sis(_t("conv.sis.late", "llegó tarde por el sync")))
        items.append(m)
    unir()
    items += pend
    s_sync = salas.salud_sync(sala, ahora, conocidas)
    no_leidos = [m for m in msgs if m["id"] not in leidos and m["de"] != "yo"]
    conv = {"id": sala["id"], "titulo": sala["titulo"], "turno": [sala["turnos"], sala["tope"]],
            "espera": sala["espera"], "nuevos": len(no_leidos), "archivada": sala["archivada"],
            "pausada": sala["pausada"] and not sala["cerrada"], "cerrada": sala["cerrada"],
            "objetivo": sala["objetivo"], "sync": s_sync["linea"],
            "sync_caido": s_sync["linea"] if s_sync["caido"] else "",
            "hecho": sala["hecho_cuando"], "parts": list(parts.values()), "items": items,
            "creada": sala["creada"], "_sala": sala}
    conv["abrir"] = _a_quien_abrir(conv)
    conv["avisar"] = _a_quien_avisar(sala, avs, parts, brains)
    return conv


def _avisos_panel(sala):
    """{(mid, clave): registro} de lo que aviso_panel hizo en ESTA máquina."""
    try:
        import aviso_panel
        return aviso_panel.avisos_de(sala["id"])
    except Exception:
        return {}


def _a_quien_avisar(sala, avs, parts, brains):
    """El botón «Avisar»: el primer despertar pendiente para una pestaña de ESTA
    máquina con panel registrado, que no escucha y a la que Workspace no le
    escribió (tenía el foco o trabajaba, o aún no le toca al barrido). →
    {mid, token, nota, pid, motivo} o None. Sin llamar a herdr (eso, al
    apretar el botón)."""
    try:
        import aviso_panel
        for mid, token, nota in aviso_panel.despertares(sala):
            cands = aviso_panel._candidatos(sala, token)
            if not cands or aviso_panel.panel_de(cands[0]) is None:
                continue
            av = avs.get((mid, cands[0])) or {}
            if av.get("estado") == "avisado":
                continue
            est = salas.estado_participante(sala, cands[0], brains=brains)
            if est.get("estado") == "escuchando":
                continue
            return {"mid": mid, "token": token, "nota": nota, "pid": _pid(parts, token),
                    "motivo": av.get("estado") or ""}
    except Exception:
        pass
    return None


def _a_quien_abrir(conv):
    """A quién ofrecer «Abrir a …»: quien debe una respuesta y no escucha;
    si no, el primero que no escucha (nunca quien abrió si hay otro)."""
    al = alerta(conv, time.time())
    if al:
        pend = [x for x in al["pedido"]["a"] if x not in al["pedido"]["listos"]]
        if pend:
            return pend[0]
    for it in _msgs(conv):
        p = it.get("pedido")
        if p and p["estado"] == "esperando":
            for pid in p["a"]:
                if pid not in p["listos"] and part(conv, pid)["estado"] != "escuchando":
                    return pid
    otros = [q for q in conv["parts"] if not q.get("creador")] + \
        [q for q in conv["parts"] if q.get("creador")]
    return next((q["id"] for q in otros if q["estado"] != "escuchando"), None)


# ── reglas del modelo ───────────────────────────────────────────────────────
def fin_pedido(conv, msg):
    return msg["pedido"]["vence"]


def vencido(conv, msg, ahora):
    p = msg.get("pedido")
    return bool(p and p["estado"] == "esperando" and ahora >= fin_pedido(conv, msg))


def alerta(conv, ahora):
    return next((it for it in conv["items"] if it["k"] == "msg" and vencido(conv, it, ahora)), None)


def part(conv, pid):
    return next((p for p in conv["parts"] if p["id"] == pid),
                _p(pid, _nombre_agente(salas.agente_de(pid)) if pid else "?", "", "", "",
                   "desconocido", slug=salas.agente_de(pid), sesion="", maquina_eti=""))


def _abrev(pestana):
    """«WORKSPACE 6» → «W6»; una sola palabra, tal cual (≤ 8). Ya no se
    pinta (salía críptico): queda como alias de «@nombre» al escribir."""
    palabras = re.findall(r"[^\W\d_]+|\d+", pestana or "")
    if len(palabras) > 1:
        return "".join(w if w.isdigit() else w[0].upper() for w in palabras)
    return (palabras[0] if palabras else "")[:8]


#: Columnas de la pestaña en «Agente·pestaña» (con su «…» si se recorta).
PESTANA_MAX = 14


def _etiqueta_pestana(pestana, agente="", n=PESTANA_MAX):
    """La pestaña como se lee: sin lo que va entre paréntesis, sin repetir
    el agente al principio y recortada por palabras a ≤ n columnas con «…».
    «Bot general (admin y meta-operativo)» del agente «Bot» →
    «general»; «WORKSPACE 6» → «WORKSPACE 6»."""
    palabras = re.sub(r"[(\[{][^)\]}]*[)\]}]?", " ", pestana or "").split() \
        or (pestana or "").split()
    ag = re.findall(r"\w+", _sin_acentos(agente))
    if ag:                                               # «Bot general» de Bot
        toks, k = [], 0
        while k < len(palabras) and len(toks) < len(ag):
            toks += re.findall(r"\w+", _sin_acentos(palabras[k]))
            k += 1
        if toks == ag and k < len(palabras):
            palabras = palabras[k:]
    txt = " ".join(palabras)
    if HL.vis(txt) <= n:
        return txt
    out = ""
    for x in palabras:
        cand = (out + " " + x).strip()
        if HL.vis(cand) > n - 1:
            break
        out = cand
    out = out.rstrip(",;:·-–—/")
    return (out + "…") if out else HL.clip(txt, n)


def _etiquetas(conv):
    """{pid: etiqueta}: el agente; si el mismo agente está en varias
    pestañas, + su pestaña legible («Agente·general»). Nunca dos iguales: si
    el recorte empata, más largo; si aun así, un número («Agente·Pruebas 2»).
    Se guarda en `conv` mientras no cambien los participantes."""
    firma = tuple((q["id"], q["agente"], q.get("pestana") or "") for q in conv["parts"])
    hecho = conv.get("_etiquetas")
    if hecho and hecho[0] == firma:
        return hecho[1]
    grupos = {}
    for q in conv["parts"]:
        grupos.setdefault(q["agente"], []).append(q)
    out = {}
    for ag, qs in grupos.items():
        if len(qs) == 1:
            out[qs[0]["id"]] = ag
            continue

        def etq(q, n):
            return "%s·%s" % (ag, _etiqueta_pestana(q["pestana"], ag, n)) if q.get("pestana") else ag
        e = {q["id"]: etq(q, PESTANA_MAX) for q in qs}
        for n in (PESTANA_MAX * 2, 200):                 # el recorte empató: más largo
            rep = [x for x in e.values() if list(e.values()).count(x) > 1]
            for q in qs:
                if e[q["id"]] in rep:
                    e[q["id"]] = etq(q, n)
        out.update(e)
    usados = set()
    for q in conv["parts"]:                              # aun iguales: un número
        e, k = out[q["id"]], 2
        while out[q["id"]] in usados:
            out[q["id"]] = "%s %d" % (e, k)
            k += 1
        usados.add(out[q["id"]])
    conv["_etiquetas"] = (firma, out)
    return out


def nombre_corto(conv, pid):
    """El agente; si el mismo agente está en dos pestañas, + la pestaña
    legible («Agente·general», ver _etiquetas). El socio es «Tú»."""
    if pid == "yo":
        return _t("conv.you", "Tú")
    e = _etiquetas(conv).get(pid)
    return e if e is not None else part(conv, pid)["agente"]


def color_de(K, conv, pid):
    """Un color por participante (agente + pestaña); rojo queda reservado."""
    if pid == "yo":
        return K["WH"]
    ids = [p["id"] for p in conv["parts"]]
    cs = [K["C"], K["OK"], K["B2"], K["B"]] + list(K.get("WCOL") or [])
    return cs[(ids.index(pid) if pid in ids else 0) % len(cs)]


_RGB = re.compile(r"38;2;(\d+);(\d+);(\d+)")
_IDX = re.compile(r"38;5;(\d+)")


def _rgb(seq):
    """RGB de una secuencia de color de la paleta (truecolor o 256)."""
    m = _RGB.search(seq or "")
    if m:
        return tuple(int(x) for x in m.groups())
    m = _IDX.search(seq or "")
    if m:
        try:
            import tuitheme
            return tuitheme._idx_rgb(int(m.group(1)))
        except Exception:
            pass
    return None


def _fondo_tema():
    try:
        import tuitheme
        osc = getattr(tuitheme.palette(), "OSC", None) or {}
        h = osc.get("bg") or ""
        if len(h) == 7 and h.startswith("#"):
            return int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    except Exception:
        pass
    return (12, 20, 36)


def truecolor():
    try:
        import tuitheme
        return tuitheme.color_mode() == "truecolor"
    except Exception:
        return False


def _mezcla(a, b, f):
    return tuple(int(round(b[i] + (a[i] - b[i]) * f)) for i in range(3))


def tinte(seq, frac):
    """El fondo de una burbuja: su color al `frac` sobre el fondo del tema
    (solo en truecolor; si no, '' y queda la barra de color)."""
    rgb = _rgb(seq)
    if not rgb or not truecolor():
        return ""
    return "\x1b[48;2;%d;%d;%dm" % _mezcla(rgb, _fondo_tema(), frac)


def apagado(seq, frac=0.55):
    """El mismo color, más apagado (lo informativo): mezclado con el fondo."""
    rgb = _rgb(seq)
    if not rgb:
        return seq
    r, g, b = _mezcla(rgb, _fondo_tema(), frac)
    if truecolor():
        return "\x1b[38;2;%d;%d;%dm" % (r, g, b)
    try:
        import tuitheme
        return "\x1b[38;5;%dm" % tuitheme.nearest256((r, g, b))
    except Exception:
        return seq


def mencion_defecto(conv):
    """A quién va lo que escribe el socio si no dice nada: al último que habló."""
    s = conv.get("_sala")
    if s is not None:
        return _pid({q["id"]: q for q in conv["parts"]}, salas.mencion_defecto(s))
    for it in reversed(conv["items"]):
        if it["k"] == "msg" and it["de"] != "yo":
            return it["de"]
    return conv["parts"][0]["id"] if conv["parts"] else "yo"


def _sin_acentos(s):
    import unicodedata
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii").lower()


def para_escrito(conv, texto):
    """Lo que escribe el socio: «@nombre …» al principio elige a quién va
    (uno o dos); si no, a mencion_defecto. → (ids de las fichas, texto)."""
    resto, pids = texto, []
    while True:
        m = re.match(r"\s*@([^\s,:]+)[,:]?\s*", resto)
        if not m:
            break
        quien = _sin_acentos(m.group(1))
        hit = next((q["id"] for q in conv["parts"]
                    if quien in (_sin_acentos(nombre_corto(conv, q["id"])).replace(" ", ""),
                                 _sin_acentos("%s·%s" % (q["agente"], _abrev(q.get("pestana")))),
                                 _sin_acentos(q["agente"]))), None)
        if hit is None:
            break
        if hit not in pids:
            pids.append(hit)
        resto = resto[m.end():]
    return (pids or [mencion_defecto(conv)]), resto


# ═══════════════════════════════════════════════════════════════════════════
# Dibujo: columnas de líneas + zonas de clic [(fila0, fila1, col0, col1, acción)]
# ═══════════════════════════════════════════════════════════════════════════

# (las piezas de la ventanita viven en ventanita.py: las comparten las secciones)
Col, _c, _ink, _der = VT.Col, VT.c, VT.ink, VT.der


def _cola(s, w):
    """El FINAL de `s` en ≤ w columnas, con «…» a la izquierda si no cabe:
    el borrador muestra lo último que escribes (HL.clip deja el principio).
    Texto plano; mide con el ancho de terminal (_width), acentos y anchos."""
    if w <= 0:
        return ""
    s = _sane(s)
    if HL.vis(s) <= w:
        return s
    out, usado = [], 0
    for ch in reversed(s):
        cw = _eaw(ch)
        if usado + cw > w - 1:
            break
        out.append(ch)
        usado += cw
    cola = "".join(reversed(out))
    while cola and _eaw(cola[0]) == 0:                  # sin un acento suelto tras «…»
        cola = cola[1:]
    return "…" + cola


def _boton(K, label, w, encima=False, rojo=False, activo=False):
    """El botón-cuadrito de las secciones (section_box.boton), de ANCHO FIJO:
    bajo el mouse o activo, el borde grueso en el acento; rojo = lo que pide
    acción."""
    if rojo and not encima:
        return SB.caja(K, [_c(K, "ERR", label, True)], w, K["ERR"], centrar=True)
    return SB.boton(K, label, w, encima or activo, False, "C")


def _b(acc, niveles, rojo=False, primero=False):
    """Un botón de la fila: `niveles` de la etiqueta más larga a la más corta;
    cada nivel es (lo que se ve, *moldes): el ancho de ese nivel es el del
    molde más largo, así «Pausar»/«Reanudar» o «Cerrar»/«¿Seguro?» ocupan lo
    mismo y nada se mueve entre dos clics. `primero` = se acorta antes que
    los demás (el «[a] Abrir a …»)."""
    return {"acc": acc, "niveles": [n if isinstance(n, tuple) else (n,) for n in niveles],
            "rojo": rojo, "primero": primero}


def _botones(C, specs, hover, gap=2):
    """Los botones SIEMPRE en una fila, sin cortarse, encimarse ni apilarse:
    si no caben, se acortan DE A UNO, un nivel cada vez — primero los que van
    primero (los de nombre variable: «[v] Avisar a X» → «[v] Avisar» → «[v]»,
    el más ancho antes), luego el más ancho de los demás (a igual ancho, el
    de más a la derecha); solo si de verdad no cabe, todos a su letra y, al
    final, con menos aire entre ellos."""
    K = C.K

    def ancho(sp, k):
        return max(HL.vis(x) for x in sp["niveles"][k]) + 4

    def total(v, g):
        return sum(ancho(sp, k) for sp, k in zip(specs, v)) + g * (len(specs) - 1)
    v, g = [0] * len(specs), gap
    while total(v, g) > C.w:
        cands = [i for i, sp in enumerate(specs) if v[i] < len(sp["niveles"]) - 1]
        if not cands:
            if g <= 1:
                break
            g = 1
            continue
        i = max(cands, key=lambda i: (bool(specs[i]["primero"]), ancho(specs[i], v[i]), i))
        v[i] += 1
    bloques = [_boton(K, sp["niveles"][k][0], ancho(sp, k), hover == sp["acc"], sp["rojo"])
               for sp, k in zip(specs, v)]
    a, x = len(C.lineas), 0
    C.add(SB.hjoin(bloques, g))
    for sp, k in zip(specs, v):
        w = ancho(sp, k)
        if x < C.w:
            C.zonas.append((a, a + 2, x, min(C.w - 1, x + w - 1), sp["acc"]))
        x += w + g


#: Ancho fijo de cada pestaña del filtro (cabe «❮ Archivadas ❯»): no se mueven.
ANCHO_TAB = 16


def _filtros(S, K, iw):
    """Las pestañas del filtro con el estilo de Decisores (`❮ Activas ❯   Todas
    Archivadas`), centradas y de ancho fijo: (línea, zonas en columnas)."""
    partes, zonas = [], []
    fs = FILTROS()
    total = ANCHO_TAB * len(fs)
    x = max(0, (iw - total) // 2)
    izq = x
    for j, f in enumerate(fs):
        if j == S["filtro"]:
            s = _c(K, "C", SB.center("%s %s %s" % (K["BL"], f, K["BR"]), ANCHO_TAB), True)
        elif S.get("hover") == ("filtro", j):
            s = _c(K, "WH", SB.center(f, ANCHO_TAB), True)
        else:
            s = _c(K, "DK", SB.center(f, ANCHO_TAB))
        partes.append(s)
        zonas.append((x, x + ANCHO_TAB - 1, ("filtro", j)))
        x += ANCHO_TAB
    return " " * izq + "".join(partes), zonas


_PRES = {"escuchando": ("OK", "●"), "trabajando": ("B", "◐"), "cerrado": ("ERR", "○"),
         "desconocido": ("DIM", "·"), "sin_entrar": ("B", "◌"), "sin_unirse": ("DIM", "·")}


def _pres_conv(conv):
    """La presencia que se pinta en la tarjeta: la del otro lado más
    despierto (verde si alguien escucha, rojo si todos cerraron)."""
    est = [p["estado"] for p in conv["parts"][1:]] or ["desconocido"]
    for e in ("escuchando", "trabajando", "cerrado"):
        if e in est:
            return e
    return "desconocido"


def _no_contesto(conv, al):
    pend = [x for x in al["pedido"]["a"] if x not in al["pedido"]["listos"]] or al["pedido"]["a"]
    return nombre_corto(conv, pend[0]) if pend else "?"


def lista_col(S, K, w):
    C = Col(K, w)
    C.contar = "conv"
    ahora = time.time()
    convs = convs_filtradas(S)
    if not S["convs"]:
        C.add([""] if S.get("_dos") else _vacio_chat(K, w) + [""])   # en dos columnas, en el chat
    elif not convs:
        C.add(["", SB.center(_c(K, "GREY", _t("conv.list.nothing", "nada en «{f}»",
                                               f=FILTROS()[S["filtro"]])), w), ""])
    for conv in convs:
        sel = conv["id"] == S["abierta"]
        hov = S.get("hover") == ("conv", conv["id"])
        k, g = _PRES[_pres_conv(conv)] if not conv["cerrada"] else ("DIM", "■")
        ult = max([it["t"] for it in conv["items"] if it["k"] == "msg"] or [conv["creada"]])
        top = _der("%s %s" % (_c(K, k, g, True), _c(K, "WH", HL.clip(conv["titulo"], w - 13), True)),
                   _c(K, "DIM", _cuando(ult, ahora)), w - 4)
        quien = " · ".join(dict.fromkeys(p["agente"] for p in conv["parts"]))
        l2 = _c(K, "DIM", HL.clip(quien, w - 10))
        if conv["nuevos"]:
            l2 = _der(l2, _c(K, "OK", "● %d" % conv["nuevos"], True), w - 4)
        al = alerta(conv, ahora)
        if al:
            l3 = _c(K, "ERR", _t("conv.list.late", "{a} no contestó a tiempo",
                                 a=_no_contesto(conv, al)), True)
        elif conv["pausada"]:
            l3 = _c(K, "B", _t("conv.list.paused", "en pausa"))
        else:
            msgs = _msgs(conv)
            l3 = _c(K, "C" if sel else "GREY",
                    HL.clip("«%s»" % msgs[-1]["texto"][0], w - 4)) if msgs else ""
            if conv["cerrada"]:                          # se ve en la tarjeta, en todo tamaño
                cerr = _t("conv.list.closed", "cerrada")
                l3 = _c(K, "GREY", HL.clip(cerr + (" · «%s»" % msgs[-1]["texto"][0] if msgs
                                                    else ""), w - 4))
        borde = (K["C"] + K["BO"]) if sel else (K["C"] if hov else K["DK"])
        C.add(SB.caja(K, [top, l2, l3], w, borde, heavy=sel), ("conv", conv["id"]))
    C.add(_boton(K, _t("conv.new_btn", "+ Nueva conversación"), w,
                 S.get("hover") == ("nueva",)), ("nueva",))
    return C


def _leyenda(K, conv, w):
    """PARTICIPANTES: una línea por participante, columnas alineadas: agente |
    pestaña | motor | máquina (si hay más de una) | estado."""
    varias = len({p["maquina"] for p in conv["parts"] if p["maquina"]}) > 1
    ws = [max([HL.vis(p[k] or "—") for p in conv["parts"]] or [1])
          for k in ("agente", "pestana", "motor", "maquina")]
    out = [SB.titulo(K, _t("conv.legend", "participantes"), w, 0)]
    for p in conv["parts"]:
        col = color_de(K, conv, p["id"])
        k, g = _PRES.get(p["estado"], ("DIM", "·"))
        fila = (_ink(col, "●", K) + " " + _ink(col, SB.pad(p["agente"], ws[0]), K, True) + "   "
                + _c(K, "WH", SB.pad(p["pestana"] or "—", ws[1])) + "   "
                + _c(K, "GREY", SB.pad(p["motor"] or "—", ws[2])) + "   "
                + (_c(K, "GREY", SB.pad(p["maquina"] or "—", ws[3])) + "   " if varias else "")
                + _c(K, k, "%s %s" % (g, _estado_txt(p["estado"])), p["estado"] == "cerrado"))
        out.append(fila)
    return out


def _linea_espera(K, conv, msg, ahora):
    p = msg["pedido"]
    if p["estado"] == "cancelado":
        return _c(K, "GREY", _t("conv.wait.cancelled", "pedido cancelado"))
    solt = p.get("soltados") or ()
    nombres = "  ".join(nombre_corto(conv, x) + (
        _t("conv.wait.dropped_mark", " (soltado)") if x in solt else
        " ✓" if x in p["listos"] else "") for x in p["a"])
    if p["estado"] == "listo":
        if solt and all(x in solt for x in p["listos"]):
            return _c(K, "GREY", _t("conv.wait.dropped", "soltado: ")) + _c(K, "WH", nombres)
        return _c(K, "GREY", _t("conv.wait.done", "respondido: ")) + _c(K, "WH", nombres)
    if p["estado"] == "cerrado":
        return _c(K, "GREY", _t("conv.wait.closed", "sin respuesta: la sala se cerró · ")) + \
            _c(K, "WH", nombres)
    fin = fin_pedido(conv, msg)
    if ahora >= fin:
        return _c(K, "GREY", _t("conv.wait.prefix", "esperando a: ")) + _c(K, "ERR", nombres, True) + \
            _c(K, "GREY", _t("conv.wait.expired", "  ·  venció {h}", h=_hora(fin)))
    sin = ""
    av = conv.get("avisar") or {}
    if av.get("mid") == msg["id"] and av.get("motivo") in ("foco", "trabajando"):
        sin = _t("conv.wait.no_notice", "  ·  sin aviso ({m}): [v] Avisar",
                 m=_t("conv.wait.focus", "tiene el foco") if av["motivo"] == "foco"
                 else _t("conv.wait.busy", "trabajando"))
    return _c(K, "GREY", _t("conv.wait.prefix", "esperando a: ")) + _c(K, "WH", nombres) + \
        _c(K, "GREY", _t("conv.wait.due", "  ·  vence {h}, faltan {d}", h=_hora(fin),
                         d=_dur(fin - ahora))) + (_c(K, "C", sin) if sin else "")


def _con_linea(msg):
    """Solo el pedido pendiente (o el cancelado) lleva su línea «esperando a
    …»: uno ya respondido no repite nada (Spec_Prototipo_v2)."""
    p = msg.get("pedido")
    return bool(p) and p["estado"] in ("esperando", "cancelado")


def _sistema(K, txt, w, rojo=False):
    t = " %s " % txt
    lado = max(2, (w - HL.vis(t)) // 2)
    return (_c(K, "DK", "─" * lado) + _c(K, "ERR" if rojo else "GREY", t)
            + _c(K, "DK", "─" * max(0, w - lado - HL.vis(t))))


def _quien(K, conv, msg):
    q = _ink(color_de(K, conv, msg["de"]), nombre_corto(conv, msg["de"]), K, True)
    if msg["para"]:
        q += _c(K, "GREY", " → ") + ", ".join(
            _ink(color_de(K, conv, x), nombre_corto(conv, x), K) for x in msg["para"])
    return q


def _caja_color(K, cuerpo, w, borde, fondo, heavy=False, barra=""):
    """Una burbuja redondeada con fondo de color: el fondo se repone tras cada
    reset para que no se corte a media línea. Sin fondo (no truecolor), una
    barra de color a la izquierda deja ver de quién es."""
    tl, tr, bl, br, v, h = SB.HEAVY if heavy else SB.LIGHT
    R = K["R"]
    iw = w - 4 - (2 if barra else 0)
    out = ["%s%s%s%s%s" % (borde, tl, h * (w - 2), tr, R)]
    for ln in cuerpo:
        dentro = HL.pad(HL.clip(ln, iw), iw)
        if fondo:
            dentro = fondo + dentro.replace(R, R + fondo) + R
        lado = (barra + "▌" + R + fondo + " ") if barra else ""
        out.append("%s%s%s%s %s%s%s %s%s%s%s" % (borde, v, R, fondo, lado, dentro, fondo, R,
                                                 borde, v, R))
    out.append("%s%s%s%s%s" % (borde, bl, h * (w - 2), br, R))
    return out


def _burbuja(S, K, conv, msg, w, ahora, idx):
    """El mensaje con el color de su participante: fondo tenue, borde en su
    color y nombre brillante; el texto en blanco. El socio va neutro y a la
    derecha; lo informativo, apagado. Elegida = borde grueso; bajo el mouse =
    borde en negrita. Alterado = borde rojo."""
    sel = S["nivel"] in ("chat", "mensaje") and S.get("sel_msg") == idx
    hov = S.get("hover") == ("msg", idx)
    socio = msg["de"] == "yo"
    info = msg["tipo"] == "info"
    col = K["GREY"] if socio else color_de(K, conv, msg["de"])
    cab = _quien(K, conv, msg)
    bw = (w - 1) if not socio else max(30, min(w - 1, int(w * 0.7)))
    barra = "" if truecolor() else (apagado(col) if info else col)
    iw = bw - 4 - (2 if barra else 0)
    cab = _der(cab, _c(K, "GREY", _cuando(msg["t"], ahora)), iw)
    tinta = "GREY" if info else "WH"
    cuerpo = [cab]
    for linea in msg["texto"]:
        cuerpo += [_c(K, tinta, x) for x in SB._wrap(linea, max(10, iw))]
    if msg.get("nota"):
        cuerpo.append(_c(K, "ERR" if msg.get("motivo") else "B2", HL.clip(msg["nota"], iw)))
    if _con_linea(msg):
        cuerpo.append(_linea_espera(K, conv, msg, ahora))
    if socio:
        fondo = tinte(K["WH"], 0.07)
        borde = K["GREY"] + (K["BO"] if (sel or hov) else "")
    else:
        fondo = tinte(col, 0.08 if info else 0.15)
        borde = (apagado(col) if info else col) + (K["BO"] if (sel or hov) else "")
    if msg.get("alterado"):
        borde = K["ERR"] + (K["BO"] if (sel or hov) else "")
    lineas = _caja_color(K, cuerpo, bw, borde, fondo, heavy=sel, barra=barra)
    sang = (w - bw) if socio else 1
    return [" " * sang + x for x in lineas]


def _vacio_chat(K, w):
    return ["", SB.center(_c(K, "GREY", _t("conv.none", "Todavía no hay conversaciones.")), w),
            "", SB.center(_c(K, "DIM", _t("conv.none_hint", "Las abre un agente: pídele en su "
                                                             "pestaña que hable con otro.")), w)]


def chat_col(S, K, w):
    C = Col(K, w)
    conv = conv_abierta(S)
    if conv is None:
        if not S["convs"]:
            C.add(_vacio_chat(K, w))
        else:
            C.add(["", SB.center(_c(K, "GREY", _t("conv.pick", "elige una conversación")), w)])
        return C
    if S["nivel"] == "mensaje":
        return mensaje_col(S, K, w, conv)
    ahora = time.time()
    abierta = bool(S.get("desplegada"))
    # cabecera estilo WhatsApp: el tema, la descripción y las fichas de los
    # integrantes; a la derecha el botón chico de la espera
    ancho_izq = w - ANCHO_ESPERA - 2
    hov_tit = S.get("hover") == ("info",)
    fichas, zf, x = [], [], 0
    for q in conv["parts"]:
        k, g = _PRES.get(q["estado"], ("DIM", "·"))
        txt = nombre_corto(conv, q["id"])
        enc = S.get("hover") == ("ficha", q["id"])
        ficha = _c(K, k, g, True) + " " + _ink(color_de(K, conv, q["id"]), txt, K, True)
        if enc:
            ficha = _c(K, "DK", "[") + ficha + _c(K, "DK", "]")
        else:
            ficha = " " + ficha + " "
        zf.append((x, x + HL.vis(txt) + 3, ("ficha", q["id"])))
        fichas.append(ficha)
        x += HL.vis(txt) + 5
    titulo = _c(K, "C" if hov_tit else "WH", HL.clip(conv["titulo"], ancho_izq - 4), True) \
        + (_c(K, "DIM", "  ⓘ") if hov_tit else "")
    a = len(C.lineas)
    etq = _t("conv.wait_btn", "[t] espera {e} ▾", e=_espera_txt(conv["espera"]))
    if S.get("_corto"):
        # 2 líneas: el tema con la espera como control de una línea, y las fichas
        ctl = SB.pad(etq, ANCHO_ESPERA)
        ctl = _c(K, "C" if (abierta or S.get("hover") == ("espera",)) else "GREY", ctl,
                 abierta or S.get("hover") == ("espera",))
        C.add([SB.pad(titulo, w - ANCHO_ESPERA) + ctl, HL.clip(" ".join(fichas), w)])
        C.zonas.append((a, a, 0, min(ancho_izq, HL.vis(conv["titulo"]) + 3), ("info",)))
        for c0, c1, acc in zf:
            C.zonas.append((a + 1, a + 1, c0, min(c1, w - 1), acc))
        C.zonas.append((a, a, w - ANCHO_ESPERA, w - 1, ("espera",)))
    else:
        izq = [titulo, _c(K, "DIM", HL.clip(conv["objetivo"], ancho_izq)),
               HL.clip(" ".join(fichas), ancho_izq)]
        boton = _boton(K, etq, ANCHO_ESPERA, S.get("hover") == ("espera",) or abierta)
        C.add([SB.pad(x, w - ANCHO_ESPERA) + y for x, y in zip(izq, boton)])
        C.zonas.append((a, a, 0, min(ancho_izq, HL.vis(conv["titulo"]) + 3), ("info",)))
        for c0, c1, acc in zf:
            C.zonas.append((a + 2, a + 2, c0, min(c1, ancho_izq), acc))
        C.zonas.append((a, a + 2, w - ANCHO_ESPERA, w - 1, ("espera",)))
    # una línea fija: el detalle de la ficha bajo el mouse, o un problema (en
    # rojo), o nada — siempre la misma altura, para que nada se mueva
    det = S.get("hover") if (S.get("hover") or ("",))[0] == "ficha" else None
    if det:
        q = part(conv, det[1])
        linea = _ink(color_de(K, conv, q["id"]), nombre_corto(conv, q["id"]), K, True) + _c(
            K, "GREY", _t("conv.detail", "  ·  pestaña {p} · {m} · {q} · {e}",
                          p=q["pestana"] or "—", m=q["motor"] or "—", q=q["maquina"] or "—",
                          e=_estado_txt(q["estado"])))
    else:
        prob = problema(conv)
        linea = _c(K, "ERR", prob, True) if prob else ""
    C.add([linea])
    if abierta:                                          # el desplegable, en su lugar fijo
        a = len(C.lineas)
        anch, gap = 10, 1
        x0 = max(0, w - (anch * len(ESPERAS) + gap * (len(ESPERAS) - 1)))
        cuadros = []
        for lab, mins in ESPERAS:
            on = mins == conv["espera"]
            hov = S.get("hover") == ("pon_espera", mins) or S.get("sel_espera") == mins
            cuadros.append(SB.boton(K, lab, anch, hov, on, "C") if not on else
                           SB.caja(K, [_c(K, "C", lab, True)], anch, K["C"] + K["BO"], heavy=True,
                                   centrar=True))
        fila = SB.hjoin(cuadros, gap)
        C.add([" " * x0 + x for x in fila])
        for j, (lab, mins) in enumerate(ESPERAS):
            c0 = x0 + j * (anch + gap)
            C.zonas.append((a, a + 2, c0, c0 + anch - 1, ("pon_espera", mins)))
        C.add([SB.pad("", max(0, x0)) + _c(K, "DK", _t("conv.wait.each",
                                                       "cada pedido puede traer la suya"))])
    C.add([_c(K, "DK", "─" * w)])
    if S.get("info"):
        return info_col(S, K, C, conv)
    C.fijas = len(C.lineas)
    C.abajo = True
    msgs = _msgs(conv)
    for it in conv["items"]:
        if it["k"] == "sis":
            C.add([_sistema(K, it["txt"], w, it["rojo"])])
        else:
            idx = msgs.index(it)
            C.add(_burbuja(S, K, conv, it, w, ahora, idx), ("msg", idx))
    inicio = len(C.lineas)
    C.add([""])
    al = alerta(conv, ahora)
    if al:
        q = _no_contesto(conv, al)
        qid = next((x for x in al["pedido"]["a"] if x not in al["pedido"]["listos"]), None)
        cerrada = part(conv, qid)["estado"] == "cerrado" if qid else False
        dentro = Col(K, w - 5)
        dur = _dur(fin_pedido(conv, al) - al["t"])
        dentro.add([_c(K, "ERR", (_t("conv.alert.closed",
                                     "{a} no contestó en {d} y su pestaña está cerrada.", a=q, d=dur)
                                  if cerrada else
                                  _t("conv.alert.late", "{a} no contestó en {d}.", a=q, d=dur)),
                       True),
                    _c(K, "DIM", _t("conv.alert.what",
                                    "Dejaron de esperarlo y te avisaron. ¿Qué hacemos?")), ""])
        _botones(dentro, [_b(("abrir_a",), [_t("conv.btn.open_to", "[a] Abrir a {a}", a=q),
                                            _t("conv.btn.open", "[a] Abrir"), "[a]"], primero=True),
                          _b(("mas30",), [_t("conv.btn.more", "[m] Esperar 30 min más"), "[m]"]),
                          _b(("cancelar",), [_t("conv.btn.cancel", "[x] Cancelar pedido"), "[x]"])],
                 S.get("hover"))
        a = len(C.lineas)
        C.add([" " + x for x in SB.caja(K, dentro.lineas, w - 1, K["ERR"])])
        for f0, f1, c0, c1, acc in dentro.zonas:
            C.zonas.append((a + 1 + f0, a + 1 + f1, 3 + c0, 3 + c1, acc))
        C.add([""])
    if S.get("escribiendo") is not None:
        pids, _resto = para_escrito(conv, S["escribiendo"])
        C.add([_c(K, "WH", _t("conv.you", "Tú"), True) + _c(K, "GREY", " → ")
               + ", ".join(_ink(color_de(K, conv, p), nombre_corto(conv, p), K, True) for p in pids)
               + _c(K, "DIM", _t("conv.compose", "   Enter publica · Esc cancela"))]
              + [" " + x for x in SB.caja(K, [_c(K, "WH", _cola(S["escribiendo"], w - 7))
                                               + _c(K, "C", "▏")], w - 1, K["C"] + K["BO"], heavy=True)])
    else:
        specs = []
        if not conv["cerrada"]:
            specs.append(_b(("escribir",), [_t("conv.btn.write", "[e] Escribir"), "[e]"]))
        q = conv["abrir"]
        if not conv["cerrada"] and not al and q and part(conv, q)["estado"] != "escuchando":
            niv = [_t("conv.btn.open_to", "[a] Abrir a {a}", a=nombre_corto(conv, q)),
                   _t("conv.btn.open", "[a] Abrir"), "[a]"]
            if S.get("_modo") == "chico":                # chico: la letra y una palabra
                niv = niv[1:]
            specs.append(_b(("abrir_a",), niv, primero=True))
        av = conv.get("avisar")
        if not conv["cerrada"] and av:
            niv = [_t("conv.btn.notify_to", "[v] Avisar a {a}", a=nombre_corto(conv, av["pid"])),
                   _t("conv.btn.notify", "[v] Avisar"), "[v]"]
            if S.get("_modo") == "chico":
                niv = niv[1:]
            specs.append(_b(("avisar",), niv, primero=True))   # nombre variable: se acorta antes
        if not conv["cerrada"]:
            pau, rea = _t("conv.btn.pause", "[p] Pausar"), _t("conv.btn.resume", "[p] Reanudar")
            specs.append(_b(("pausar",), [(rea if conv["pausada"] else pau, rea), "[p]"]))
            conf = S.get("confirmar") == conv["id"]
            cer, seg = _t("conv.btn.close", "[c] Cerrar"), _t("conv.btn.sure", "[c] ¿Seguro?")
            specs.append(_b(("cerrar",), [(seg if conf else cer, seg), "[c]"], rojo=conf))
        elif not conv["archivada"]:
            specs.append(_b(("archivar",), [_t("conv.btn.archive", "[r] Archivar"), "[r]"]))
        else:
            conf = S.get("confirmar") == ("borrar", conv["id"])
            bor, seg = _t("conv.btn.delete", "[b] Borrar"), _t("conv.btn.delete_sure", "[b] ¿Seguro?")
            specs.append(_b(("borrar",), [(seg if conf else bor, seg), "[b]"], rojo=conf))
        _botones(C, specs, S.get("hover"))
    C.pie = len(C.lineas) - inicio
    return C


def problema(conv):
    """Lo único que se queda arriba sin pedirlo: un integrante cerrado con un
    pedido pendiente para él (o el sync caído)."""
    if conv.get("sync_caido"):
        return conv["sync_caido"]
    if (conv.get("_sala") or {}).get("firma") == "alterado":
        return _t("conv.problem.altered", "alguien editó a mano el archivo de la sala")
    for it in _msgs(conv):
        p = it.get("pedido")
        if p and p["estado"] == "esperando":
            for pid in p["a"]:
                if pid not in p["listos"] and part(conv, pid)["estado"] == "cerrado":
                    return _t("conv.problem.closed", "La pestaña de {a} está cerrada y tiene un pedido pendiente",
                              a=nombre_corto(conv, pid))
    return ""


def _info_filas(conv):
    t = conv["turno"]
    return ((_t("conv.info.turn", "turno"), _t("conv.info.turn_v", "{n} de {m} (tope)", n=t[0], m=t[1])),
            (_t("conv.info.sync", "sync"), conv["sync"]),
            (_t("conv.info.goal", "objetivo"), conv["objetivo"]),
            (_t("conv.info.done", "hecho cuando"), conv.get("hecho") or "—"),
            (_t("conv.info.wait", "espera"), _t("conv.info.wait_v", "{e} por pedido",
                                                e=_espera_txt(conv["espera"]))))


def info_col(S, K, C, conv):
    """Info del grupo (`i` o clic en el tema): lo que no está en la vista
    normal — la tabla completa, el turno contra el tope, el sync y el «hecho
    cuando»."""
    C.fijas = len(C.lineas)
    C.add([SB.titulo(K, _t("conv.info.title", "info del grupo"), C.w, 0)]
          + _leyenda(K, conv, C.w)[1:] + [""])
    for etq, val in _info_filas(conv):
        C.add([_c(K, "GREY", SB.pad(etq, 14)) + _c(K, "WH", val)])
    inicio = len(C.lineas)
    C.add([""])
    _botones(C, [_b(("info",), [_t("conv.btn.info_back", "[i] Volver al chat"), "[i]"])],
             S.get("hover"))
    C.pie = len(C.lineas) - inicio
    return C


def mensaje_col(S, K, w, conv):
    C = Col(K, w)
    msgs = _msgs(conv)
    if not msgs:
        S["nivel"] = "chat"
        return chat_col(S, K, w)
    msg = msgs[min(S.get("sel_msg") or 0, len(msgs) - 1)]
    p = part(conv, msg["de"])
    tarde = _t("conv.msg.late_sync", " · llegó tarde por el sync") if msg["tarde"] else ""
    if msg["de"] == "yo":
        origen = "hub · " + _t("conv.socio", "socio")
    else:
        origen = "%s · %s" % (p["pestana"] or "—", p["motor"] or "—")
    C.add([_der(_quien(K, conv, msg), _c(K, "GREY", _cuando(msg["t"])), w),
           _c(K, "GREY", origen + tarde),
           "", SB.titulo(K, _t("conv.msg.full", "mensaje completo"), w, 1)])
    C.fijas = len(C.lineas)
    if msg.get("nota"):
        C.add([_c(K, "ERR" if msg.get("motivo") else "B2", x) for x in SB._wrap(msg["nota"], w)] + [""])
    for par in msg["cuerpo"].split("\n"):
        C.add([_c(K, "WH", x) for x in SB._wrap(par, w)] if par.strip() else [""])
    if msg.get("pedido"):
        C.add(["", _linea_espera(K, conv, msg, time.time())])
    inicio = len(C.lineas)
    C.add([""])
    _botones(C, [_b(("volver",), [_t("conv.btn.back_chat", "← Volver al chat"), "←"])],
             S.get("hover"))
    C.pie = len(C.lineas) - inicio
    return C


def _ventana(C, alto, scroll):
    """(líneas a la vista, fila→pantalla, desplazamiento, máximo, alto del
    medio): ventanita.ventana con los «▲/▼ N más» de Conversaciones."""
    return VT.ventana(C, alto, scroll,
                      lambda n: _t("conv.more_up", "▲ {n} más arriba", n=n),
                      lambda n: _t("conv.more_down", "▼ {n} más abajo", n=n))


def CHIPS(S=None):
    """Lo que dice el pie (en cuadritos, como Decisores). Con el borrador
    abierto, las teclas de escribir (lo demás no responde mientras tanto)."""
    if S is not None and S.get("escribiendo") is not None:
        return (("Enter", _t("conv.k.post", "publica")), ("Esc", _t("conv.k.cancel", "cancela")),
                ("⌫", _t("conv.k.erase", "borra")))
    return (("↑↓", _t("conv.k.pick", "elegir")), ("→", _t("conv.k.enter", "entrar")),
            ("←", _t("conv.k.back", "volver")), ("Tab", _t("conv.k.filter", "filtro")),
            ("q", _t("conv.k.quit", "salir")))


CAJA_MAX = 150


def render(S, w, h):
    """La pantalla según el tamaño: el monitor en la ventanita; si no, la
    sección con lo que quepa — con poco alto se quita, en orden, el título
    grande, el pie y la descripción, hasta que los mensajes tengan su sitio."""
    K = SB.K()
    w, h = max(1, int(w)), max(1, int(h))
    if w < 30 or h < 6:
        import responsive_ui as RU
        return RU.size_notice(HL.section_word("conversaciones"), w, h, 30, 6)
    m = modo(w, h)
    S["_modo"] = m
    if m == "ventanita":
        return render_monitor(S, K, w, h)
    titulos = ["full", "compact", "none"] if m == "completo" else ["compact", "none"]
    pasos = [(t, 3, True) for t in titulos[:1]]
    pasos += [(t, 3, True) for t in titulos[1:]]
    pasos += [(titulos[-1], 1, True), (titulos[-1], 0, True), (titulos[-1], 0, False)]
    lineas = None
    for titulo, pie, desc in pasos:
        S["_corto"] = (m == "chico") or not desc
        lineas = _render_seccion(S, K, w, h, m, titulo, pie)
        info = (S.get("_cols") or {}).get("chat") or (S.get("_cols") or {}).get("lista")
        if info and info["alto_m"] >= MIN_MENSAJES:
            break
    return lineas


def _render_seccion(S, K, w, h, m, nivel_titulo, nivel_pie):
    W, H = max(1, w - 1), max(1, h - 1)
    pw = max(40, W)                                      # a todo lo ancho
    iw = pw - 4
    dos = m in ("mediano", "completo")
    S["_dos"] = dos
    lw = LW_GRANDE if m == "completo" else LW
    word = HL.section_word("conversaciones")
    top = SB._header(K, w, word, nivel_titulo) if nivel_titulo != "none" else []
    pie = SB._chips(K, CHIPS(S), W, nivel_pie) if nivel_pie else []
    fijo = len(top) + (1 if top else 0) + 2 + 1 + len(pie)    # aire, bordes, aviso
    alto = max(4, H - fijo - 2)                         # menos la fila de filtros y su aire
    filtros, zf = _filtros(S, K, iw)
    if dos:
        cw = iw - lw - 2
        cols = [("lista", lista_col(S, K, lw), 0), ("chat", chat_col(S, K, cw), lw + 2)]
    elif S["nivel"] == "lista":
        cols = [("lista", lista_col(S, K, iw), 0)]
    else:
        cols = [("chat", chat_col(S, K, iw), 0)]
    filas = [""] * alto
    zonas_body = [(0, 0, a, b, acc) for a, b, acc in zf]
    S["_cols"] = {}
    for nombre, C, x0 in cols:
        clave = "mensaje" if (nombre == "chat" and S["nivel"] == "mensaje") else nombre
        vis, a_pant, st, maxs, alto_m = _ventana(C, alto, S["scroll"].get(clave))
        S["_cols"][nombre] = {"x0": x0, "w": C.w, "max": maxs, "st": st, "col": C,
                              "alto_m": alto_m, "clave": clave}
        for j in range(alto):
            filas[j] = (SB.pad(filas[j], x0) if x0 else "") + SB.pad(vis[j] if j < len(vis) else "", C.w)
        for a, b, c0, c1, acc in C.zonas:
            ys = [y for y in (a_pant(r) for r in range(a, b + 1)) if y is not None]
            if ys:
                zonas_body.append((2 + min(ys), 2 + max(ys), x0 + c0, x0 + min(c1, C.w - 1), acc))
    cuerpo = [filtros, ""] + filas
    caja = SB.caja(K, cuerpo, pw, K["DK"], title=word, tcol=K["C"] + K["BO"])
    lp = max(0, (W - pw) // 2)
    aviso = SB._center(_c(K, "B2", S.get("aviso", "")), W) if S.get("aviso") else ""
    L = list(top) + ([""] if top else []) + [HL.clip(" " * lp + x, W) for x in caja] + [aviso]
    L += [""] * max(0, H - len(L) - len(pie)) + pie
    L = (L[:H - len(pie)] + pie) if len(L) > H else L
    L += [""] * max(0, H - len(L))
    # zonas a coordenadas de pantalla (0-based): fila 0 del cuerpo = tras el
    # encabezado, su aire y el borde de arriba; columna 0 = tras «│ »
    y0 = len(top) + (1 if top else 0) + 1
    x0 = lp + 2
    S["_zonas"] = [(y0 + a, y0 + b, x0 + c0, x0 + c1, acc) for a, b, c0, c1, acc in zonas_body]
    S["_xcols"] = {n: (x0 + info["x0"], info["w"]) for n, info in S["_cols"].items()}
    return [HL.clip(x, W) for x in L[:H]]


# ═══════════════════════════════════════════════════════════════════════════
# Ventanita: WhatsApp en el celular (v6) — la lista o el chat, nunca mezclados
# ═══════════════════════════════════════════════════════════════════════════

def _ultimo_t(conv, ahora=None):
    return max([m["t"] for m in _msgs(conv)] or [conv.get("creada") or ahora or time.time()])


def lista_monitor(S):
    """Las conversaciones del filtro, ordenadas por actividad: la que recibe
    un mensaje sube sola (eso es monitorear, sin mezclar nada)."""
    return sorted(convs_filtradas(S), key=_ultimo_t, reverse=True)


def _mon(S):
    return S.setdefault("mon", {"vista": "lista", "sel": S.get("abierta"), "scroll": None,
                                "visto": None, "ayuda": False})


def _fila_lista(S, K, conv, w, sel, hover, ahora):
    """Una tarjeta redondeada (la elegida, de borde grueso, como en el
    mediano) con 2 líneas: el título a lo ancho con la hora y los nuevos (o
    ⚠); debajo el último mensaje con el autor en su color, o la alerta."""
    iw = w - 4
    al = alerta(conv, ahora)
    prob = "" if al else problema(conv)
    if al or prob:
        marca = _c(K, "ERR", "⚠", True)
    elif conv["nuevos"]:
        marca = _c(K, "OK", "● %d" % conv["nuevos"], True)
    else:
        marca = ""
    der = _c(K, "DIM", _cuando(_ultimo_t(conv, ahora), ahora)) + (" " + marca if marca else "")
    tit = _c(K, "WH", conv["titulo"], sel)
    l1 = _der(HL.clip(tit, max(4, iw - HL.vis(der) - 1)), der, iw)
    if al:
        l2 = _c(K, "ERR", _t("conv.list.late", "{a} no contestó a tiempo", a=_no_contesto(conv, al)))
    elif prob:
        l2 = _c(K, "ERR", prob)
    else:
        msgs = _msgs(conv)
        if msgs:
            m = msgs[-1]
            col = K["GREY"] if m["de"] == "yo" else color_de(K, conv, m["de"])
            l2 = _ink(col, nombre_corto(conv, m["de"]), K, True) + _c(K, "GREY", ": ") + \
                _c(K, "GREY" if m["tipo"] == "info" else "WH", m["texto"][0])
        else:
            l2 = _c(K, "GREY", _t("conv.mon.none", "sin mensajes"))
        if conv["cerrada"]:
            l2 = _c(K, "GREY", _t("conv.mon.closed", "cerrada · ")) + l2
    borde = (K["C"] + K["BO"]) if sel else (K["C"] if hover else K["DK"])
    return SB.caja(K, [l1, HL.clip(l2, iw)], w, borde, heavy=sel)


def _chat_monitor(S, K, w):
    """El chat compacto: cabecera «‹ título» (clic = volver) con la espera,
    los integrantes en una línea y los mensajes con barra y nombre en su
    color; los seguidos del mismo autor A LOS MISMOS destinatarios van en
    una burbuja (no repiten el nombre). Si cambia a quién, burbuja nueva:
    «Ana → Caro, Eli» no se lleva el pedido que fue Ana → Beto."""
    conv = conv_abierta(S)
    C = Col(K, w)
    C.anclas = []                        # dónde empieza cada burbuja (no se corta arriba)
    C.marcas = {}                        # índice → fila de su primera línea (donde va la ❯)
    elegido = _sel_mon(S, conv)          # el mensaje elegido: ❯ a la izquierda de su inicio
    esp = _c(K, "C" if S.get("desplegada") else "GREY", "[t] %s" % _espera_txt(conv["espera"]),
             bool(S.get("desplegada")))
    cab = _c(K, "C", "‹ ", True) + _c(K, "WH", conv["titulo"], True)
    C.add([_der(HL.clip(cab, w - HL.vis(esp) - 2), esp, w)])
    C.zonas.append((0, 0, 0, max(2, min(w - HL.vis(esp) - 2, HL.vis(conv["titulo"]) + 2)), ("mon_volver",)))
    C.zonas.append((0, 0, w - HL.vis(esp) - 1, w - 1, ("espera",)))
    fichas = "  ".join(_c(K, _PRES.get(q["estado"], ("DIM", "·"))[0], _PRES.get(q["estado"], ("DIM", "·"))[1], True)
                       + " " + _ink(color_de(K, conv, q["id"]), nombre_corto(conv, q["id"]), K, True)
                       for q in conv["parts"])
    C.add([HL.clip("  " + fichas, w)], ("info",))
    prob = problema(conv)
    if prob:
        C.add([HL.clip(_c(K, "ERR", "  ⚠ " + prob, True), w)])
    C.add([_c(K, "DK", "─" * w)])                     # la cabecera, separada del chat
    C.fijas = len(C.lineas)
    C.abajo = True                       # con burbujas, arriba nunca media burbuja
    ahora = time.time()
    msgs = _msgs(conv)
    grupo = []                           # mensajes seguidos del mismo autor: una burbuja

    def cerrar_grupo():
        if not grupo:
            return
        primero = grupo[0]
        socio = primero["de"] == "yo"
        info = all(m["tipo"] == "info" for m in grupo)
        col = K["GREY"] if socio else color_de(K, conv, primero["de"])
        borde = apagado(col) if info else col
        if any(m.get("alterado") for m in grupo):
            borde = K["ERR"]
        bw = max(20, int(w * 0.8)) if socio else w
        iw = bw - 4
        cuerpo = [_der(_quien(K, conv, primero), _c(K, "GREY", _cuando(primero["t"], ahora)), iw)]
        empieza = []
        for j, m in enumerate(grupo):
            empieza.append((len(cuerpo) if j else 0, msgs.index(m)))
            tinta = "GREY" if m["tipo"] == "info" else "WH"
            hora = _c(K, "GREY", _cuando(m["t"], ahora))
            # los que siguen: su hora a la derecha (el texto, más angosto: cabe entero)
            lineas = [x for linea in m["texto"]
                      for x in SB._wrap(linea, max(8, iw - (HL.vis(hora) + 1 if j else 0)))]
            if j and lineas:
                lineas[0] = _der(lineas[0], hora, iw)
            cuerpo += [_c(K, tinta, x) for x in lineas]
            if m.get("nota") and m.get("motivo"):
                cuerpo.append(_c(K, "ERR", HL.clip(m["nota"], iw)))
            if _con_linea(m):
                cuerpo.append(HL.clip(_linea_espera(K, conv, m, ahora), iw))
        caja = _caja_color(K, cuerpo, bw, borde, tinte(col, 0.12))
        for off, idx in empieza:         # el elegido: el ❯ del hub en lugar del borde izquierdo
            pre = borde + SB.LIGHT[4]
            if idx == elegido and caja[1 + off].startswith(pre):
                caja[1 + off] = (K["C"] + K["BO"] + (K.get("PTR") or "❯") + K["R"]
                                 + caja[1 + off][len(pre):])
        sang = w - bw
        base = len(C.lineas)
        C.add([" " * sang + x for x in caja])
        C.anclas.append(base)
        for off, idx in empieza:
            C.marcas[idx] = base + 1 + off
        # una zona POR MENSAJE (el clic en el segundo de la burbuja abre el segundo)
        filas = [base] + [base + 1 + off for off, _i in empieza[1:]] + [base + len(caja)]
        for k, (_off, idx) in enumerate(empieza):
            C.zonas.append((filas[k], filas[k + 1] - 1, sang, w - 1, ("msg", idx)))
        del grupo[:]

    for it in conv["items"]:
        if it["k"] == "sis":
            cerrar_grupo()
            C.add([_sistema(K, HL.clip(it["txt"], w - 6), w, it["rojo"])])
            continue
        if grupo and (grupo[0]["de"], grupo[0]["para"]) != (it["de"], it["para"]):
            cerrar_grupo()                   # otro autor, u otros destinatarios: otra burbuja
        grupo.append(it)
    cerrar_grupo()
    return C


def _ayuda(K, w, vista):
    comunes = [("Tab", _t("conv.help.filter", "filtro: Activas · Todas · Archivadas")),
               ("?", _t("conv.help.keys", "estas teclas")), ("q", _t("conv.k.quit", "salir"))]
    if vista == "mensaje":                               # aquí las letras no hacen nada
        filas = [("Esc ←", _t("conv.help.back_chat", "volver al chat")),
                 ("↑ ↓", _t("conv.help.scroll_msg", "desplazar el mensaje"))]
    elif vista == "chat":
        filas = [("Esc ←", _t("conv.help.back", "volver a la lista")),
                 ("↑ ↓", _t("conv.help.scroll", "elegir un mensaje (❯)")),
                 ("Enter", _t("conv.help.read", "leer completo el elegido")),
                 ("e", _t("conv.help.write", "escribir")),
                 ("t", _t("conv.help.wait", "espera por respuesta")),
                 ("i", _t("conv.help.info", "info del grupo")),
                 ("a", _t("conv.help.open", "abrir al agente")),
                 ("v", _t("conv.help.notify", "avisarle en su panel (esta máquina)")),
                 ("p", _t("conv.help.pause", "pausar / reanudar")),
                 ("c", _t("conv.help.close", "cerrar (dos veces)")),
                 ("r · b", _t("conv.help.archive", "archivar · borrar (cerrada)")),
                 ("m · x", _t("conv.help.expired", "si venció: más tiempo · cancelar"))]
    else:
        filas = [("↑ ↓", _t("conv.help.pick", "elegir una conversación")),
                 ("Enter →", _t("conv.help.enter", "abrirla")),
                 ("e t i", _t("conv.help.eti", "escribir · espera · info")),
                 ("p c a", _t("conv.help.pca", "pausar · cerrar · abrir al agente"))]
    return VT.ayuda(K, w, filas + comunes, _t("conv.help.title", " TECLAS"),
                    _t("conv.help.any", "  (cualquier tecla cierra)"))


def _pie_mon(vista, escribiendo=False):
    if escribiendo:
        return _t("conv.mon.foot_write", "Enter publica · Esc cancela · ⌫ borra")
    if vista == "mensaje":
        return _t("conv.mon.foot_msg", "↑↓ desplazar · Esc volver al chat · ? teclas")
    if vista == "chat":
        return _t("conv.mon.foot_chat", "Esc volver · Enter leer · e escribir · ? teclas")
    return _t("conv.mon.foot_list", "↑↓ elegir · Enter abrir · Tab filtro · ? teclas")


def render_monitor(S, K, w, h):
    W, H = max(1, w - 1), max(1, h - 1)
    mon = _mon(S)
    ahora = time.time()
    convs = lista_monitor(S)
    if mon["vista"] in ("chat", "mensaje") and not conv_abierta(S):
        mon["vista"] = "lista"
    if mon["vista"] == "mensaje" and not _msgs(conv_abierta(S)):
        mon["vista"] = "chat"
    if mon.get("sel") not in [c["id"] for c in convs] and convs:
        mon["sel"] = convs[0]["id"]
    zonas = []
    extra = []                                           # líneas fijas abajo (escribir / espera)
    conv = conv_abierta(S)
    if mon["vista"] == "chat" and conv and S.get("escribiendo") is not None:
        pids, _resto = para_escrito(conv, S["escribiendo"])
        # «Tú → a quién» ocupa a lo más media línea: el resto es para lo último
        # que escribes y el cursor, que siempre se ven
        pre = HL.clip(_c(K, "WH", " " + _t("conv.you", "Tú"), True) + _c(K, "GREY", " → ")
                      + ", ".join(_ink(color_de(K, conv, p), nombre_corto(conv, p), K, True)
                                  for p in pids), max(4, W // 2)) + _c(K, "C", " › ", True)
        extra = [HL.clip(pre + _c(K, "WH", _cola(S["escribiendo"], W - HL.vis(pre) - 1))
                         + _c(K, "C", "▏"), W)]
    elif S.get("desplegada") and conv:
        partes = []
        for lab, mins in ESPERAS:
            on = mins == S.get("sel_espera", conv["espera"])
            partes.append(_c(K, "C", "[%s]" % lab, True) if on else _c(K, "GREY", " %s " % lab))
        extra = [HL.clip(_c(K, "GREY", " " + _t("conv.mon.wait", "espera") + " ") + "".join(partes), W)]
    alto = max(1, H - 1 - len(extra))                    # menos el pie
    if mon.get("ayuda"):
        cuerpo = _ayuda(K, W, mon["vista"])
    elif S.get("info") and conv:
        cuerpo = ([_c(K, "C", "‹ ", True) + _c(K, "WH", HL.clip(conv["titulo"], W - 4), True),
                   SB.titulo(K, _t("conv.info.title", "info del grupo"), W, 0)]
                  + _leyenda(K, conv, W)[1:]
                  + [_c(K, "GREY", SB.pad(k, 13)) + _c(K, "WH", v) for k, v in _info_filas(conv)])
    elif mon["vista"] == "mensaje" and conv:          # el mensaje completo, solo él
        C = mensaje_col(S, K, W, conv)
        vis, a_pant, st, maxs, _alto_m = _ventana(C, alto, mon.get("scroll_m") or 0)
        mon["_info_m"] = {"max": maxs, "st": st}
        mon["scroll_m"] = st
        cuerpo = vis
        zonas += VT.zonas_en(C, a_pant, W)
    elif mon["vista"] == "chat" and conv:
        C = _chat_monitor(S, K, W)
        vis, a_pant, st, maxs, alto_m = _ventana(C, alto, mon.get("scroll"))
        if mon.pop("_rueda", None) is not None:          # la rueda movió la vista: elige lo que se ve
            sel = _sel_mon(S, conv)
            if a_pant(C.marcas.get(sel, -1)) is None:
                medio = C.fijas + st + alto_m // 2
                vistos = [i for i, r in C.marcas.items() if a_pant(r) is not None]
                nuevo = (min(vistos, key=lambda i: (abs(C.marcas[i] - medio), -i)) if vistos else
                         next((z[4][1] for z in C.zonas if z[4][0] == "msg" and z[0] <= medio <= z[1]),
                              sel))
                msgs = _msgs(conv)
                mon["sel_id"] = msgs[nuevo]["id"] if 0 <= nuevo < len(msgs) else None
                C = _chat_monitor(S, K, W)                       # la ❯ en el nuevo
                vis, a_pant, st, maxs, alto_m = _ventana(C, alto, mon.get("scroll"))
        else:                                            # ↑↓, al entrar, tras un resize: la ❯ a la vista
            vis, a_pant, st, maxs, alto_m = _sel_a_la_vista(
                C, alto, mon, conv, _sel_mon(S, conv), bool(mon.pop("_ver_sel", False)),
                (vis, a_pant, st, maxs, alto_m))
        mon["_info"] = {"max": maxs, "st": st}
        cuerpo = vis
        zonas += VT.zonas_en(C, a_pant, W)
        if mon.get("scroll") is not None and mon.get("visto") is not None:
            n_nuevos = max(0, len(_msgs(conv)) - mon["visto"])
            if n_nuevos:
                txt = (_t("conv.mon.newer_1", "↓ 1 nuevo") if n_nuevos == 1 else
                       _t("conv.mon.newer_n", "↓ {n} nuevos", n=n_nuevos))
                cuerpo = list(cuerpo[:alto - 1]) + [SB.center(_c(K, "OK", txt, True), W)]
                zonas.append((alto - 1, alto - 1, 0, W - 1, ("mon_abajo",)))
    else:
        nuevos = sum(c["nuevos"] for c in convs)
        filtro = "" if S["filtro"] == 0 else _c(K, "DIM", "  " + FILTROS()[S["filtro"]])
        cab = _der(_c(K, "WH", " " + HL.section_word("conversaciones"), True) + filtro,
                   _c(K, "OK", "● %d" % nuevos, True) if nuevos else "", W)
        C = Col(K, W)
        C.add([cab])
        C.zonas.append((0, 0, 16, W - 1, ("mon_filtro",)))
        C.fijas = 1
        for conv_i in convs:
            hov = S.get("hover") == ("mon_conv", conv_i["id"])
            C.add(_fila_lista(S, K, conv_i, W, conv_i["id"] == mon["sel"], hov, ahora),
                  ("mon_conv", conv_i["id"]))
        if not convs:
            if not S["convs"]:
                C.add(["", HL.clip(_c(K, "GREY", "  " + _t("conv.none", "Todavía no hay "
                                                                   "conversaciones.")), W),
                       HL.clip(_c(K, "DIM", "  " + _t("conv.none_hint", "Las abre un agente: pídele "
                                                                          "en su pestaña que hable "
                                                                          "con otro.")), W)])
            else:
                C.add(["", HL.clip(_c(K, "GREY", _t("conv.mon.nothing", "  nada en «{f}» · Tab cambia",
                                                    f=FILTROS()[S["filtro"]])), W)])
        # la elegida, a la vista
        filas = {z[4][1]: z for z in C.zonas if z[4][0] == "mon_conv"}
        st = VT.seguir(C, filas.get(mon["sel"]), mon.get("scroll_l") or 0, alto)
        mon["scroll_l"] = st
        vis, a_pant, st, maxs, _alto_m = _ventana(C, alto, st)
        cuerpo = vis
        zonas += VT.zonas_en(C, a_pant, W)
    S["_zonas"] = zonas
    S["_xcols"] = {"mon": (0, W)}
    return VT.componer(K, W, H, cuerpo, alto, _pie_mon(
        mon["vista"], mon["vista"] == "chat" and conv is not None
        and S.get("escribiendo") is not None), S.get("aviso", ""), extra)


def _sel_a_la_vista(C, alto, mon, conv, sel, pedido, actual):
    """La ventana del chat con la ❯ del elegido a la vista: si no se ve (o
    ↑↓ la movieron: `pedido`), el desplazamiento mínimo que muestra el
    mensaje entero o, si es más alto que la ventana, su inicio. Se mide
    contra el desplazamiento REAL (el alineado a una burbuja puede quedar
    bajo el máximo) y, si alinear tapa el objetivo, se fija en el máximo en
    vez de «seguir lo último»."""
    vis, a_pant, st, maxs, alto_m = actual
    marca = C.marcas.get(sel)
    z = next((z for z in C.zonas if z[4] == ("msg", sel)), None)
    if marca is None or z is None or (a_pant(marca) is not None and not pedido):
        return actual
    a, b, m = z[0] - C.fijas, z[1] - C.fijas, marca - C.fijas
    cands = []
    if b - a + 3 <= alto_m:                              # cabe entero: lo justo
        if a - 1 < st:
            cands.append(a - 1)
        elif b + 1 >= st + alto_m:
            cands.append(b - alto_m + 2)
        else:
            cands.append(st)
    cands.append(m - 1)                                  # si no, su inicio arriba
    for c in cands:
        c = max(0, c)
        for scroll in ((None, maxs) if c >= maxs else (c,)):
            v = _ventana(C, alto, scroll)
            if v[1](marca) is not None:
                if scroll != mon.get("scroll"):
                    if scroll is None:
                        mon.update(scroll=None, visto=None)
                    else:
                        if mon.get("scroll") is None:
                            mon["visto"] = len(_msgs(conv))
                        mon["scroll"] = scroll
                return v
    return actual


def _sel_mon(S, conv):
    """El índice del mensaje elegido en el chat de la ventanita (por su id: un
    mensaje que llega tarde no cambia cuál es); sin elegir, el último."""
    msgs = _msgs(conv) if conv else []
    sid = _mon(S).get("sel_id")
    i = next((k for k, m in enumerate(msgs) if m["id"] == sid), None)
    return i if i is not None else len(msgs) - 1


def _abrir_mon(S, cid):
    mon = _mon(S)
    elegir_conv(S, cid)
    mon.update(vista="chat", sel=cid, scroll=None, visto=None, sel_id=None)   # elige el último


def accion_monitor(S, key):
    """Las teclas y clics de la ventanita. False = salir."""
    mon = _mon(S)
    convs = lista_monitor(S)
    ids = [c["id"] for c in convs]
    if isinstance(key, tuple):
        if key[0] == "hover":
            nuevo = zona_en(S, key[1], key[2])
            if nuevo == S.get("hover"):
                return "igual"
            S["hover"] = nuevo
            return True
        if key[0] == "rueda":
            if mon["vista"] == "mensaje":
                info = mon.get("_info_m") or {}
                mon["scroll_m"] = max(0, min(info.get("max", 0), (mon.get("scroll_m") or 0)
                                             + 3 * key[1]))
            elif mon["vista"] == "chat":
                info = mon.get("_info") or {}
                # siguiendo lo último, el alineado a una burbuja puede dejar st
                # por debajo del máximo: se parte del máximo (si no, no sube)
                st = min(info.get("st", 0), info.get("max", 0))
                nuevo = max(0, min(info.get("max", 0), st + 3 * key[1]))
                if nuevo >= info.get("max", 0):
                    mon.update(scroll=None, visto=None)
                else:
                    if mon.get("scroll") is None and conv_abierta(S):
                        mon["visto"] = len(_msgs(conv_abierta(S)))
                    mon["scroll"] = nuevo
                mon["_rueda"] = key[1]                   # la selección sigue a lo que se ve
            elif ids:
                i = ids.index(mon["sel"]) if mon["sel"] in ids else 0
                mon["sel"] = ids[max(0, min(len(ids) - 1, i + key[1]))]
            return True
        if key[0] == "mouse":
            acc = zona_en(S, key[1], key[2])
            if not acc:
                return True
            if acc[0] == "mon_conv":
                _abrir_mon(S, acc[1])
            elif acc[0] == "msg" and mon["vista"] == "chat":     # el mensaje: lo elige y lo abre
                conv = conv_abierta(S)
                msgs = _msgs(conv) if conv else []
                if 0 <= acc[1] < len(msgs):
                    S["sel_msg"] = acc[1]
                    mon.update(vista="mensaje", scroll_m=0, sel_id=msgs[acc[1]]["id"])
            elif acc[0] == "volver" and mon["vista"] == "mensaje":
                mon["vista"] = "chat"
            elif acc[0] == "mon_volver":
                return accion_monitor(S, "\x1b")
            elif acc[0] == "mon_abajo":
                mon.update(scroll=None, visto=None)
            elif acc[0] == "mon_filtro":
                accion_de(S, ("filtro", (S["filtro"] + 1) % len(FILTROS())))
            else:
                return accion_de(S, acc)
            return True
        return True
    if mon.get("ayuda"):
        mon["ayuda"] = False
        return key not in ("q", "\x03")
    if key not in ("c", "b"):
        S["aviso"] = ""
    if S.get("escribiendo") is not None or S.get("desplegada"):
        publica = S.get("escribiendo") is not None and key in ("\r", "\n")
        r = accion(S, key, monitor=False)                # la línea de texto / la espera: igual que siempre
        if publica:                                      # lo que escribes tú: el chat baja a verlo
            mon.update(scroll=None, visto=None)
        return r
    if key in ("q", "\x03"):
        return False
    if key == "?":
        mon["ayuda"] = True
        return True
    if key in ("tab", "right_tab"):                      # Tab: el filtro, como en los otros tamaños
        accion_de(S, ("filtro", (S["filtro"] + (1 if key == "tab" else -1)) % len(FILTROS())))
        mon["vista"] = "lista" if mon["vista"] == "chat" and S["abierta"] not in [
            c["id"] for c in lista_monitor(S)] else mon["vista"]
        return True
    if key in ("\x1b", "left"):
        if S.get("info"):
            S["info"] = False
        elif mon["vista"] == "mensaje":                  # del mensaje, al chat
            mon["vista"] = "chat"
        elif mon["vista"] == "chat":
            mon["vista"] = "lista"
            mon["sel"] = S["abierta"]
        return True
    if mon["vista"] == "lista":
        if key in ("up", "down") and ids:
            i = ids.index(mon["sel"]) if mon["sel"] in ids else 0
            mon["sel"] = ids[max(0, min(len(ids) - 1, i + (1 if key == "down" else -1)))]
        elif key in ("\r", "\n", "right") and ids:
            _abrir_mon(S, mon["sel"] if mon["sel"] in ids else ids[0])
        elif key in _LETRAS and ids:
            if mon["sel"] in ids and mon["sel"] != S["abierta"]:
                elegir_conv(S, mon["sel"])
            if key in ("e", "t", "i"):                   # escribir, la espera o la info: en su chat
                mon["vista"] = "chat"
            return accion_de(S, _LETRAS[key])
        return True
    conv = conv_abierta(S)
    if mon["vista"] == "mensaje":                        # ↑↓ desplazan el mensaje completo
        if key in ("up", "down"):
            info = mon.get("_info_m") or {}
            mon["scroll_m"] = max(0, min(info.get("max", 0), (mon.get("scroll_m") or 0)
                                         + (1 if key == "down" else -1)))
        return True
    if key in ("\r", "\n") and conv and _msgs(conv):      # Enter: el elegido (❯), completo
        if S.get("info"):                                # con la info encima, nada detrás
            return True
        S["sel_msg"] = _sel_mon(S, conv)
        mon.update(vista="mensaje", scroll_m=0)
        return True
    if key in ("up", "down") and conv and _msgs(conv):  # ↑↓: de mensaje en mensaje
        msgs = _msgs(conv)
        i = max(0, min(len(msgs) - 1, _sel_mon(S, conv) + (1 if key == "down" else -1)))
        if i == len(msgs) - 1:                           # en el último: sigue lo que llega
            mon.update(sel_id=None, scroll=None, visto=None)
        else:
            mon.update(sel_id=msgs[i]["id"], _ver_sel=True)
    elif key in _LETRAS and conv:
        return accion_de(S, _LETRAS[key])
    return True


# ═══════════════════════════════════════════════════════════════════════════
# Estado, refresco y acciones (de verdad)
# ═══════════════════════════════════════════════════════════════════════════

def initial(brains=None):
    S = {"convs": [], "filtro": 0, "abierta": None, "nivel": "lista", "sel_msg": None,
         "scroll": {"lista": 0, "chat": None, "mensaje": 0}, "escribiendo": None, "aviso": "",
         "confirmar": None, "desplegada": False, "hover": None, "request": None,
         "cerebros": brains, "al": salas.Almacen(), "local": _local()}
    try:
        import aviso_panel
        S["_barrido"] = aviso_panel.Barrido(brains)
    except Exception:
        S["_barrido"] = None
    refrescar(S, forzar=True)
    vis = convs_filtradas(S)
    if vis:
        elegir_conv(S, vis[0]["id"])
    return S


def _brains(S):
    bm = S.get("cerebros")
    return bm if isinstance(bm, dict) else messages.registered_brains()


def _del_socio(sala, cache):
    """¿Esta sala es del socio de esta máquina? (en un cerebro compartido, la
    de otro socio no se muestra)."""
    if not sala.get("dueno"):
        return True
    h = sala["hogar"]
    if h not in cache:
        cache[h] = salas._socio_de(h)
    return not cache[h] or cache[h] == sala["dueno"]


def _firma_presencia(bm):
    out = []
    for b in messages._brain_paths(bm):
        try:
            out.append(os.stat(os.path.join(b, messages.MSGS_DIR, messages.PRESENCIA_DIR)).st_mtime_ns)
        except OSError:
            out.append(None)
    return tuple(out)


def _firma_avisos():
    try:
        import aviso_panel
        return os.stat(aviso_panel.ruta_avisos()).st_mtime_ns
    except Exception:
        return None


def refrescar(S, forzar=False, ahora=None):
    """Rehace las conversaciones si cambió algo (stat incremental: el almacén
    lee solo lo nuevo) o si toca recalcular la presencia. True si las
    rehizo (hay que redibujar)."""
    ahora = time.time() if ahora is None else ahora
    bm = _brains(S)
    try:
        ss = salas.todas(bm, S["al"])
    except Exception:
        ss = []
    firma = (tuple((s["id"], S["al"].salas.get(s["dir"], {}).get("ver")) for s in ss)
             + (_firma_presencia(bm), _firma_avisos()))
    if (not forzar and firma == S.get("_firma")
            and ahora - S.get("_t_modelo", 0) < PRESENCIA_S):
        return False
    S["_firma"], S["_t_modelo"] = firma, ahora
    cache, cambio = {}, False
    try:
        conocidas = messages.maquinas_conocidas(bm)
    except Exception:
        conocidas = {}
    convs = []
    for s in ss:
        if not _del_socio(s, cache):
            continue
        cambio = _llegada(S["local"], s) or cambio
        try:
            convs.append(conv_de(s, S["local"], ahora, conocidas, bm))
        except Exception:
            continue
    convs.sort(key=lambda c: c["creada"], reverse=True)   # nada se mueve si no lo moviste tú
    S["convs"] = convs
    if S["local"].get("_sin_apartar"):                   # se RELEE antes de reintentar: si otro
        nuevo = _local()                                 # ya lo arregló, o ya no está, se usa eso
        if nuevo.get("_sin_apartar"):                    # sigue sin poderse: tras varios, se dice
            S["_fallos_local"] = S.get("_fallos_local", 0) + 1
            if S["_fallos_local"] >= 3:
                S["aviso"] = _t("conv.aviso.local_unreadable", "No puedo leer lo leído ({r}): "
                                "no lo guardo hasta poder.", r=_ruta_local())
        else:
            S["_fallos_local"] = 0
        if not nuevo.get("_sin_apartar"):
            if nuevo.get("ilegible") or nuevo["leidos"] or nuevo["llegada"]:
                S["local"] = nuevo
            else:                                        # vacío: lo de memoria, ya guardable
                S["local"].pop("_sin_apartar", None)
    if S["local"].get("ilegible"):                       # lo leído se dañó: lo de ahora, leído
        for c in convs:
            cambio = _marcar_leida(S, c) or cambio
        if not S["local"].get("_sin_apartar"):           # el aviso, cuando de verdad se apartó
            S["local"].pop("ilegible", None)
            cambio = True
            S["aviso"] = _t("conv.aviso.local_broken", "El registro de lo leído estaba dañado: "
                            "lo aparté y marqué todo como leído.")
    abierta = conv_abierta(S)
    if abierta is not None:
        cambio = _marcar_leida(S, abierta) or cambio
    if cambio:
        _guardar_local(S["local"])
    return True


def _marcar_leida(S, conv):
    ids = [m["id"] for m in _msgs(conv)]
    le = S["local"]["leidos"].setdefault(conv["id"], [])
    nuevos = [i for i in ids if i not in le]
    if nuevos:
        le.extend(nuevos)
    conv["nuevos"] = 0
    return bool(nuevos)


def convs_filtradas(S):
    """Activas = abiertas o en pausa (sin las cerradas ni las archivadas) ·
    Todas · Archivadas."""
    f = S["filtro"]
    if f == 1:
        return list(S["convs"])
    if f == 2:
        return [c for c in S["convs"] if c["archivada"]]
    return [c for c in S["convs"] if not c["archivada"] and not c["cerrada"]]


def conv_abierta(S):
    return next((c for c in S["convs"] if c["id"] == S["abierta"]), None)


def _msgs(conv):
    return [it for it in conv["items"] if it["k"] == "msg"]


def elegir_conv(S, cid):
    """La conversación se muestra al instante (sin Enter); sus no leídos
    quedan leídos (el «● N» de la lista se limpia, como en WhatsApp)."""
    if cid != S["abierta"]:
        S.update(abierta=cid, sel_msg=None, confirmar=None, desplegada=False, escribiendo=None,
                 info=False)
        S["scroll"]["chat"] = None                       # abre en lo último
    conv = conv_abierta(S)
    if conv and _marcar_leida(S, conv):
        _guardar_local(S["local"])


def entrar(S):
    conv = conv_abierta(S)
    if conv:
        S["nivel"] = "chat"
        if S.get("sel_msg") is None and _msgs(conv):
            S["sel_msg"] = len(_msgs(conv)) - 1


def volver(S):
    if S.get("info"):
        S["info"] = False
        return
    if S.get("escribiendo") is not None:
        S["escribiendo"] = None
    elif S.get("desplegada"):
        S["desplegada"] = False
    elif S["nivel"] == "mensaje":
        S["nivel"] = "chat"
    elif S["nivel"] == "chat":
        S["nivel"] = "lista"
    S["confirmar"] = None


def _socio(conv):
    return salas.socio_de_sala(conv["_sala"])


def _hacer(S, conv, fn, ok_txt):
    """Corre una acción del socio por la API y rehace la vista. El aviso dice
    si salió."""
    try:
        fn()
    except salas.Error as e:
        S["aviso"] = _t("conv.aviso.fail", "No se pudo: {e}", e=e)
        return False
    except Exception as e:
        S["aviso"] = _t("conv.aviso.fail", "No se pudo: {e}", e="%s: %s" % (type(e).__name__, e))
        return False
    S["aviso"] = ok_txt
    refrescar(S, forzar=True)
    return True


def _pedido_abrir(conv, q):
    """Lo que el hub corre para abrir a ese participante en su pestaña de
    siempre (`--open <id> --name <nombre>`, que retoma su conversación) o, si
    todavía no tiene, una nueva con el título de la sala."""
    if q.get("sesion") and q.get("pestana"):
        args = ["--open", q["sesion"], "--name", q["pestana"]]
    else:
        nombre = re.sub(r"\s+", " ", conv["titulo"]).strip()[:40] or "conversacion"
        args = ["--open", q.get("sesion") or str(uuid.uuid4()), "--name", nombre]
    return {"agente": q.get("slug"), "args": args}


def _abrir_a(S, conv):
    """«Abrir a …»: si su pestaña es de esta máquina y no está viva, la
    sección sale con el pedido y el hub la abre. False = salir."""
    al = alerta(conv, time.time())
    qid = conv["abrir"]
    if al:
        qid = next((x for x in al["pedido"]["a"] if x not in al["pedido"]["listos"]), qid)
    if not qid:
        S["aviso"] = _t("conv.aviso.nobody", "No hay a quién abrir.")
        return True
    q = part(conv, qid)
    if q["estado"] in ("escuchando", "trabajando", "sin_entrar"):
        S["aviso"] = _t("conv.aviso.alive", "{a} ya tiene su pestaña abierta.",
                        a=nombre_corto(conv, qid))
        return True
    eti = q.get("maquina_eti")
    if eti and eti not in messages.mi_maquina()["alias"]:
        S["aviso"] = _t("conv.aviso.remote", "{a} está en {m}: ábrelo allá.",
                        a=nombre_corto(conv, qid), m=q.get("maquina") or eti)
        return True
    if not q.get("slug"):
        return True
    S["request"] = _pedido_abrir(conv, q)
    return False


def _avisar(S, conv):
    """«Avisar» a mano: la misma línea en su panel de herdr, sin mirar foco ni si
    trabaja (lo decidió el socio); la verificación del panel es la misma."""
    av = conv.get("avisar")
    if not av:
        S["aviso"] = _t("conv.aviso.nobody_notify", "No hay a quién avisar en esta máquina.")
        return True
    try:
        import aviso_panel
        _est, txt = aviso_panel.avisar(conv["_sala"], av["mid"], av["token"], av["nota"],
                                       manual=True, brains=_brains(S), quien="socio")
    except Exception as e:
        txt = "no pude avisar: %s" % type(e).__name__
    S["aviso"] = txt
    refrescar(S, forzar=True)
    return True


def accion_de(S, acc):
    """Lo que hace una acción (clic, tecla o botón). False = salir de la sección."""
    conv = conv_abierta(S)
    tipo = acc[0]
    if tipo == "filtro":
        S["filtro"] = acc[1]
        vis = convs_filtradas(S)
        if vis and S["abierta"] not in [c["id"] for c in vis]:
            elegir_conv(S, vis[0]["id"])
        if not S.get("_dos"):
            S["nivel"] = "lista"
        S["scroll"]["lista"] = 0
        return True
    if tipo == "conv":
        elegir_conv(S, acc[1])
        if S.get("_dos"):
            S["nivel"] = "lista"
        else:
            entrar(S)
        return True
    if tipo == "nueva":
        S["aviso"] = _t("conv.aviso.new", "Las abre un agente: pídele en su pestaña «abre una "
                                          "conversación con … sobre …».")
        return True
    if tipo == "volver":
        volver(S)
        return True
    if tipo == "info":
        S["info"] = not S.get("info")
        S["desplegada"] = False
        return True
    if tipo == "ficha":
        S["info"] = True
        return True
    if conv is None:
        return True
    sid = conv["id"]
    bm = _brains(S)
    if tipo == "msg":
        if S["nivel"] in ("chat", "mensaje") and S.get("sel_msg") == acc[1]:
            S["nivel"] = "mensaje"
            S["scroll"]["mensaje"] = 0
        else:
            S.update(nivel="chat", sel_msg=acc[1])
    elif tipo == "espera":
        S["desplegada"] = not S.get("desplegada")
        S["sel_espera"] = conv["espera"]
        S["info"] = False
    elif tipo == "pon_espera":
        S["desplegada"] = False
        _hacer(S, conv, lambda: salas.accion_socio(sid, "espera", _socio(conv), bm, minutos=acc[1]),
               _t("conv.aviso.wait_set", "Espera por respuesta: {e}.", e=_espera_txt(acc[1])))
    elif tipo == "escribir" and not conv["cerrada"]:
        if conv["pausada"]:
            S["aviso"] = _t("conv.aviso.paused_write", "Está en pausa: reanúdala para escribir.")
        else:
            S["escribiendo"] = ""
    elif tipo == "pausar" and not conv["cerrada"]:
        accion = "reanudar" if conv["pausada"] else "pausa"
        _hacer(S, conv, lambda: salas.accion_socio(sid, accion, _socio(conv), bm),
               _t("conv.aviso.resumed", "Sigue: los agentes retoman al leerlo.") if conv["pausada"]
               else _t("conv.aviso.paused", "En pausa: los agentes paran al leerlo."))
        S["scroll"]["chat"] = None
    elif tipo == "cerrar" and not conv["cerrada"]:
        if S.get("confirmar") != conv["id"]:
            S["confirmar"] = conv["id"]
            S["aviso"] = _t("conv.aviso.confirm_close", "¿Cerrar «{t}»? Pulsa Cerrar (o c) otra vez.",
                            t=conv["titulo"])
        else:
            S["confirmar"] = None
            _hacer(S, conv, lambda: salas.accion_socio(sid, "cierre", _socio(conv), bm),
                   _t("conv.aviso.closed", "Cerrada: a todos les llega el cierre."))
            S["scroll"]["chat"] = None
    elif tipo == "archivar" and conv["cerrada"] and not conv["archivada"]:
        _hacer(S, conv, lambda: salas.accion_socio(sid, "archivar", _socio(conv), bm),
               _t("conv.aviso.archived", "Archivada: está en «Archivadas»."))
    elif tipo == "borrar" and conv["archivada"]:
        if S.get("confirmar") != ("borrar", conv["id"]):
            S["confirmar"] = ("borrar", conv["id"])
            S["aviso"] = _t("conv.aviso.confirm_delete", "¿Borrar «{t}»? Pulsa Borrar (o b) otra vez.",
                            t=conv["titulo"])
        else:
            S["confirmar"] = None
            if _hacer(S, conv, lambda: salas.accion_socio(sid, "lapida", _socio(conv), bm),
                      _t("conv.aviso.deleted", "Borrada (el historial de Obsidian puede guardar "
                                               "una copia).")):
                S.update(abierta=None, nivel="lista")
                vis = convs_filtradas(S)
                if vis:
                    elegir_conv(S, vis[0]["id"])
    elif tipo == "abrir_a" and not conv["cerrada"]:
        return _abrir_a(S, conv)
    elif tipo == "avisar" and not conv["cerrada"]:
        return _avisar(S, conv)
    elif tipo == "mas30":
        al = alerta(conv, time.time())
        if al:
            q = _no_contesto(conv, al)
            _hacer(S, conv, lambda: salas.accion_socio(sid, "mas_tiempo", _socio(conv), bm,
                                                       pedido=al["id"], minutos=30),
                   _t("conv.aviso.more", "Le das 30 min más a {a}.", a=q))
    elif tipo == "cancelar":
        al = alerta(conv, time.time())
        if al:
            q = _no_contesto(conv, al)
            _hacer(S, conv, lambda: salas.accion_socio(sid, "cancelar", _socio(conv), bm,
                                                       pedido=al["id"]),
                   _t("conv.aviso.cancelled", "Pedido a {a} cancelado.", a=q))
            S["scroll"]["chat"] = None
    return True


def publicar(S):
    conv = conv_abierta(S)
    txt = (S.get("escribiendo") or "").strip()
    S["escribiendo"] = None
    if not conv or not txt:
        return
    pids, resto = para_escrito(conv, txt)
    if not resto.strip():
        return
    destinos = []
    for pid in pids:
        if pid == "yo":
            continue
        destinos.append(salas.agente_de(pid) if pid.startswith("?") else pid)
    if _hacer(S, conv, lambda: salas.publicar_socio(conv["id"], resto, destinos or None,
                                                    _socio(conv), _brains(S)),
              _t("conv.aviso.posted", "Publicado para {a}.",
                 a=", ".join(nombre_corto(conv, p) for p in pids))):
        conv = conv_abierta(S) or conv
        S["sel_msg"] = len(_msgs(conv)) - 1
        S["scroll"]["chat"] = None


zona_en = VT.zona_en


def _columna_en(S, x):
    for nombre, (x0, w) in (S.get("_xcols") or {}).items():
        if x0 + 1 <= x <= x0 + w:
            return nombre
    return None


_LETRAS = {"e": ("escribir",), "p": ("pausar",), "c": ("cerrar",), "a": ("abrir_a",),
           "v": ("avisar",),
           "t": ("espera",), "m": ("mas30",), "x": ("cancelar",), "i": ("info",),
           "r": ("archivar",), "b": ("borrar",)}


def accion(S, key, monitor=True):
    """Una tecla o un evento del mouse. False = salir; "igual" = nada que redibujar."""
    if monitor and S.get("_modo") == "ventanita":
        return accion_monitor(S, key)
    if isinstance(key, tuple):
        tipo = key[0]
        if tipo == "hover":
            nuevo = zona_en(S, key[1], key[2])
            if nuevo == S.get("hover"):
                return "igual"
            S["hover"] = nuevo
            return True
        if tipo == "rueda":                              # la columna bajo el puntero
            col = _columna_en(S, key[2])
            info = (S.get("_cols") or {}).get(col)
            if info:
                clave = info["clave"]
                st = min(info["st"], info["max"])        # alineado bajo el máximo: desde ahí
                S["scroll"][clave] = max(0, min(info["max"], st + 3 * key[1]))
                if clave == "chat" and S["scroll"]["chat"] >= info["max"]:
                    S["scroll"]["chat"] = None           # en lo último: sigue lo que llega
            return True
        if tipo == "mouse":
            S["aviso"] = ""
            acc = zona_en(S, key[1], key[2])
            if S.get("escribiendo") is not None and acc != ("escribir",):
                S["escribiendo"] = None
            if S.get("desplegada") and (not acc or acc[0] not in ("espera", "pon_espera")):
                S["desplegada"] = False
            if acc:
                return accion_de(S, acc)
            return True
        return True
    if key not in ("c", "b"):
        S["aviso"] = ""
    if S.get("escribiendo") is not None:                 # una línea de texto
        if key == "\x1b":
            S["escribiendo"] = None
        elif key in ("\r", "\n"):
            publicar(S)
        elif key in ("\x7f", "\x08"):
            S["escribiendo"] = S["escribiendo"][:-1]
        elif key == "\x03":
            return False
        elif isinstance(key, str) and len(key) == 1 and key.isprintable():
            S["escribiendo"] += key
        return True
    if key in ("q", "\x03"):
        return False
    if key in ("tab", "right_tab"):                      # Tab SOLO cambia el filtro
        accion_de(S, ("filtro", (S["filtro"] + (1 if key == "tab" else -1)) % len(FILTROS())))
        return True
    conv = conv_abierta(S)
    if S.get("desplegada") and conv:                     # el desplegable de la espera
        mins = [mm for _l, mm in ESPERAS]
        cur = S.get("sel_espera", conv["espera"])
        cur = mins.index(cur) if cur in mins else 0
        if key in ("left", "up"):
            S["sel_espera"] = mins[max(0, cur - 1)]
        elif key in ("right", "down"):
            S["sel_espera"] = mins[min(len(mins) - 1, cur + 1)]
        elif key in ("\r", "\n"):
            accion_de(S, ("pon_espera", S.get("sel_espera", mins[cur])))
        elif key in ("\x1b", "t"):
            S["desplegada"] = False
        return True
    if key in ("\x1b", "left"):
        volver(S)
        return True
    if S["nivel"] == "lista":
        ids = [c["id"] for c in convs_filtradas(S)]
        if key in ("up", "down") and ids:
            i = ids.index(S["abierta"]) if S["abierta"] in ids else 0
            elegir_conv(S, ids[max(0, min(len(ids) - 1, i + (1 if key == "down" else -1)))])
        elif key in ("right", "\r", "\n") and ids:
            entrar(S)
    elif S["nivel"] == "chat" and conv:
        n = len(_msgs(conv))
        if key in ("up", "down") and n:
            cur = S["sel_msg"] if S.get("sel_msg") is not None else n - 1
            S["sel_msg"] = max(0, min(n - 1, cur + (1 if key == "down" else -1)))
            S["_ver_sel"] = True
        elif key in ("right", "\r", "\n") and S.get("sel_msg") is not None:
            S["nivel"] = "mensaje"
            S["scroll"]["mensaje"] = 0
    elif S["nivel"] == "mensaje" and key in ("up", "down"):
        info = (S.get("_cols") or {}).get("chat") or {}
        S["scroll"]["mensaje"] = max(0, min(info.get("max", 0),
                                            info.get("st", 0) + (1 if key == "down" else -1)))
    if key in _LETRAS and conv and S["nivel"] != "mensaje":
        if S["nivel"] == "lista" and not S.get("_dos"):
            entrar(S)                                    # angosta: el chat a la vista
        return accion_de(S, _LETRAS[key])
    return True


def pantalla(S, w, h):
    """render; tras moverse con las flechas por el chat, si el mensaje elegido
    quedó fuera de vista, desplaza LO JUSTO (nada se mueve solo)."""
    S["_alto_mon"] = max(1, h - 3)
    lines = render(S, w, h)
    if S.get("_modo") == "ventanita":
        S.pop("_ver_sel", None)
        return lines
    if S.pop("_ver_sel", False):
        info = (S.get("_cols") or {}).get("chat")
        if info and info["clave"] == "chat":
            C = info["col"]
            z = next((z for z in C.zonas if z[4] == ("msg", S["sel_msg"])), None)
            if z:
                a, b, st, alto_m = z[0] - C.fijas, z[1] - C.fijas, info["st"], info["alto_m"]
                nuevo = a - 1 if a - 1 < st else (b - alto_m + 2 if b + 1 >= st + alto_m else st)
                nuevo = max(0, nuevo)
                if nuevo != st:
                    S["scroll"]["chat"] = None if nuevo >= info["max"] else nuevo
                    lines = render(S, w, h)
    return lines


# ═══════════════════════════════════════════════════════════════════════════
# Bucle: teclas + mouse (presionar, mover, rueda)
# ═══════════════════════════════════════════════════════════════════════════

def lector(fd, mouse=True):
    """El lector de las secciones (section_box.KeyReader). Con `mouse`, en el
    modo «todo»: ('mouse', x, y) al PRESIONAR el botón izquierdo,
    ('hover', x, y) al moverse, ('rueda', ±1, x, y); soltar → "". La lectura
    del SGR-1006 es la de section_box (mouse_event), la misma que usa el
    resto del hub."""
    return SB.KeyReader(fd, mouse="todo" if mouse else False)


def _size():
    try:
        ts = os.get_terminal_size()
        return max(1, ts.columns), max(1, ts.lines)
    except Exception:
        return 120, 40


def _draw(tout, S, first=False):
    import responsive_ui as RU
    w, h = _size()
    try:
        RU.paint(tout, pantalla(S, w, h), first=first)
    except Exception:
        pass


def _bucle(S, teclas, tout):
    _draw(tout, S, first=True)
    ult, ult_reloj, tam = time.time(), time.time(), _size()
    while True:
        key = teclas.get(0.25)
        if key is None:
            ahora_tam = _size()
            ahora = time.time()
            # al redimensionar (SIGWINCH): el tamaño se mira cada 0.25 s y se
            # redibuja entero en el nuevo (paint limpia si cambió); lo que
            # llega, con un stat por carpeta cada REFRESCO_S
            redibujar = ahora_tam != tam
            if ahora - ult >= REFRESCO_S:
                ult = ahora
                if S.get("_barrido") is not None:      # avisa en su panel a quien no escucha
                    S["_barrido"].tal_vez()
                redibujar = refrescar(S) or redibujar
            if ahora - ult_reloj >= RELOJ_S:
                ult_reloj, redibujar = ahora, True
            if redibujar:
                tam = ahora_tam
                _draw(tout, S)
            continue
        if key:
            r = accion(S, key)
            if r is False:
                break
            if r == "igual":
                continue
        # redibujar EN EL MOMENTO, también tras el «soltar» de un clic (que
        # llega pegado y devuelve "")
        if not teclas.pending():
            _draw(tout, S)
    return 0


_MOUSE_ON = "\033[?1000h\033[?1003h\033[?1006h"
_MOUSE_OFF = "\033[?1003l\033[?1000l\033[?1006l"


def _run_unix(S):
    import termios
    import tty
    fd = os.open("/dev/tty", os.O_RDWR)
    tout = open("/dev/tty", "w")
    old = termios.tcgetattr(fd)
    mouse = not os.environ.get("WORKSPACE_NO_MOUSE")
    try:
        tty.setraw(fd)
        tout.write("\033[?1049h\033[?25l" + (_MOUSE_ON if mouse else ""))
        return _bucle(S, lector(fd, mouse), tout)
    except KeyboardInterrupt:
        return 0
    finally:
        try:
            tout.write((_MOUSE_OFF if mouse else "") + "\033[?25h\033[?1049l")
            tout.flush()
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
            os.close(fd)
        except Exception:
            pass


def _run_windows(S):
    tout = sys.stdout
    tout.write("\033[?1049h\033[?25l")
    try:
        return _bucle(S, SB.WinKeyReader(), tout)
    except KeyboardInterrupt:
        return 0
    finally:
        try:
            tout.write("\033[?25h\033[?1049l")
            tout.flush()
        except Exception:
            pass


def texto_plano(S=None, w=120, h=40):
    """Sin terminal interactiva (o para revisar): la sección en texto, sin
    colores."""
    S = S or initial()
    return "\n".join(HL._plain(x) for x in pantalla(S, w, h))


def _interactivo():
    try:
        import _console
        return _console.interactive()
    except Exception:
        try:
            return sys.stdin.isatty() and sys.stdout.isatty()
        except Exception:
            return False


@_theme_screen
def run():
    """La sección. Devuelve None, o el pedido de abrir una pestaña de agente
    ({"agente", "args"}) para que el hub lo lance como lanza cualquier
    pestaña."""
    S = initial()
    if not _interactivo():
        print(texto_plano(S))
        return None
    try:
        if os.name == "nt":
            _run_windows(S)
        else:
            _run_unix(S)
    except Exception as e:
        try:
            sys.stdout.write("\033[?25h\033[?1049l")
        except Exception:
            pass
        print("conversaciones: %s" % e)
    return S.get("request")


if __name__ == "__main__":
    r = run()
    if r:
        print("abrir: %s %s" % (r.get("agente"), " ".join(r.get("args") or [])))
    sys.exit(0)
