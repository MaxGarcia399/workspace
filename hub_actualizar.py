#!/usr/bin/env python3
r"""WORKSPACE · hub_actualizar — Ajustes › Actualizaciones del hub nuevo (I10), en lugar de la pantalla de antes
(actualizaciones_tui con la caja de section_box, por front._doctor_submenu).

Una tarjeta del hub (la piel H-1: su área, sus botones de tres filas, el mouse y el teclado):
  · arriba, tu versión y si hay algo nuevo (se busca solo, en el fondo, sin bajar nada);
  · tres botones: «Actualizar» (trae lo nuevo y repara: lo recomendado), «Revisar y reparar» (arregla hooks,
    lanzadores, tema…) y «Solo revisar» (no toca nada);
  · los pasos en vivo (✓ ● ⚠ ✗) mientras corre, y al final lo que pasó y lo que queda por hacer, en simple.
El trabajo es el MISMO de siempre (el del doctor y `workspace update`): actualizaciones_tui lo arma y lo corre en un
hilo (su `_inicia_job`); aquí solo se ve con la piel nueva. Si instaló código nuevo, al volver el hub se reabre solo
(su firma cambió: HUB_VIEJO). Esc vuelve al hub (mientras corre, lo detiene entre pasos).

    python3 hub_actualizar.py            # lo que abre el hub
    python3 hub_actualizar.py --render 100x30 [--vista menu|run|done]   # sin terminal, para ver cómo queda
Stdlib."""
import os
import shutil
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

import hub_paleta as P  # noqa: E402

#: Quién «habla» en la tarjeta: Workspace, con su monito.
WS = {"id": "", "n": "Workspace", "c": "#b9a7e6", "f": "bolita"}
#: Los tres botones: (lo que corre, clave del texto, español de red, la línea que lo explica).
OPCIONES = (("update", "puertas.act.actualizar", "Actualizar", "puertas.act.actualizar_d",
             "trae lo nuevo y repara (lo recomendado)"),
            ("repair", "puertas.act.reparar", "Revisar y reparar", "puertas.act.reparar_d",
             "arregla hooks, lanzadores y tema; no trae nada nuevo"),
            ("check", "puertas.act.revisar", "Solo revisar", "puertas.act.revisar_d",
             "mira cómo está todo y no toca nada"))
ICONOS = {"ok": ("✓", "ok"), "run": ("●", "acento"), "warn": ("⚠", "warn"), "fail": ("✗", "err"),
          "skip": ("·", "tx3"), "pend": ("·", "tx3")}


def _t(clave, es, **kw):
    """Como todo el hub de terminal (hub_directo._tp, AG3-a): en el idioma del hub, con el español de red."""
    try:
        import hub_directo
        return hub_directo._tp(clave, es, **kw)
    except Exception:
        return es.format(**kw) if kw else es


def _AT():
    import actualizaciones_tui
    return actualizaciones_tui


def _version():
    try:
        with open(os.path.join(AQUI, "VERSION"), encoding="utf-8") as fh:
            return fh.read().strip()
    except OSError:
        return ""


class Pantalla:
    """El estado (el S de actualizaciones_tui: su chequeo y su trabajo) y lo que hace cada tecla o clic. Sin terminal:
    las pruebas la manejan."""

    def __init__(self, S=None, iniciar=None):
        self.S = S if S is not None else {}
        self.sel = 0
        self.sobre, self.apretado = "", None
        self._iniciar = iniciar

    @property
    def job(self):
        return self.S.get("job")

    def vista(self):
        j = self.job
        if not j:
            return "menu"
        return "done" if j.get("done") else "run"

    def buscar(self):
        """Si hay algo nuevo (en el fondo: fetch, sin bajar nada)."""
        try:
            _AT()._lanza_chk(self.S)
        except Exception:
            self.S["chk"] = {"state": "done", "ok": False, "reason": ""}

    def correr(self, tok):
        if self._iniciar is not None:
            return self._iniciar(self.S, tok)
        try:
            return _AT()._inicia_job(self.S, tok)
        except Exception as e:
            self.S["job"] = {"done": True, "error": "%s: %s" % (type(e).__name__, e), "steps": [], "cancel": False,
                             "findings": [], "n_new": 0, "t0": time.monotonic(), "t1": time.monotonic()}
            return "error"

    def tecla(self, k):
        """→ None (sigue) o "salir"."""
        v = self.vista()
        if v == "menu":
            if k in ("arriba", "izquierda", "shift-tab"):
                self.sel = (self.sel - 1) % len(OPCIONES)
            elif k in ("abajo", "derecha", "tab"):
                self.sel = (self.sel + 1) % len(OPCIONES)
            elif k in ("1", "2", "3"):
                self.sel = int(k) - 1
                self.correr(OPCIONES[self.sel][0])
            elif k == "enter":
                self.correr(OPCIONES[self.sel][0])
            elif k in ("esc", "q", "ctrl-c"):
                return "salir"
            return None
        if v == "run":
            if k in ("esc", "ctrl-c"):
                self.job["cancel"] = True             # se detiene entre pasos (el trabajo lo mira)
            return None
        if k in ("enter", "esc", "q", "ctrl-c"):
            return "salir"
        return None

    def clic(self, zid):
        p, _s, resto = zid.partition(":")
        if p != "act":
            return None
        if resto == "volver":
            return self.tecla("esc") if self.vista() != "run" else self.tecla("esc")
        if resto.startswith("op:"):
            i = int(resto[3:])
            if 0 <= i < len(OPCIONES) and self.vista() == "menu":
                self.sel = i
                self.correr(OPCIONES[i][0])
        return None


def _lineas_estado(S):
    """Tu versión y si hay algo nuevo, en simple."""
    import hub_bloque as B
    C = P.C
    v = _version()
    out = [[(_t("puertas.act.version", "Tienes Workspace {v}.", v=v) if v else
             _t("puertas.act.version_nd", "Tu versión de Workspace."), C["tx"], False)]]
    chk = S.get("chk") or {}
    if chk.get("state") == "busy" or not chk:
        out.append([(_t("puertas.act.buscando", "Buscando si hay algo nuevo…"), C["tx3"], False)])
    elif chk.get("ok") and chk.get("behind"):
        nv = chk.get("new_version") or ""
        txt = (_t("puertas.act.hay_version", "Hay una versión nueva: {nv}.", nv=nv) if nv else
               _t("puertas.act.hay", "Hay {n} cambio(s) nuevo(s).", n=chk["behind"]))
        out.append([(txt, B.OK, True)])
        if chk.get("held"):
            out.append([(_t("puertas.act.pausa", "Esa versión quedó en pausa en esta máquina (algo falló la vez "
                                                 "pasada): «Actualizar» la intenta otra vez."), B.WARN, False)])
    elif chk.get("ok"):
        out.append([(_t("puertas.act.al_dia", "Estás al día."), C["tx2"], False)])
    else:
        out.append([(_t("puertas.act.sin_saber", "No pude saber si hay algo nuevo ({r}).",
                        r=chk.get("reason") or "?"), C["tx3"], False)])
    return out


def _icono(st):
    import hub_bloque as B
    g, c = ICONOS.get(st, ("·", "tx3"))
    col = {"ok": B.OK, "warn": B.WARN, "err": P.ERR, "acento": WS["c"]}.get(c) or P.C.get(c, P.C["tx3"])
    return g, col


def _veredicto(job):
    """(texto, color) de cómo terminó."""
    import hub_bloque as B
    pend = _AT()._pendientes(job) if job.get("findings") else []
    fails = sum(1 for _t2, x in pend if x.get("status") == "fail")
    warns = len(pend) - fails
    if job.get("error"):
        return _t("puertas.act.fin_error", "No terminó: {e}. Escribe `workspace doctor` para ver qué pasó.",
                  e=job["error"]), P.ERR
    if job.get("cancel"):
        return _t("puertas.act.fin_cancelado", "Lo detuviste: lo que ya corrió quedó hecho."), P.C["tx2"]
    if fails:
        return _t("puertas.act.fin_fallos", "Terminó con {n} cosa(s) por arreglar (abajo, qué hacer).", n=fails), P.ERR
    if warns:
        return _t("puertas.act.fin_avisos", "Terminó; {n} cosa(s) para revisar (abajo).", n=warns), B.WARN
    return _t("puertas.act.fin_ok", "Listo: todo quedó bien."), B.OK


def pantalla(w, h, pan, t=None):
    """La tarjeta de Actualizaciones a w × h. → Term (con sus zonas)."""
    import hub_bloque as B
    import hub_directo as D
    import hub_h1 as H
    import hub_monitos as MON
    C = P.C
    T = P.Term(w, h)
    T.fill(0, 0, w, h, B.BG)
    L = B.Lienzo(T, {"sobre": pan.sobre, "apretado": pan.apretado,
                     "foco": "act:op:%d" % pan.sel if pan.vista() == "menu" else "act:volver"})
    cw = max(40, min(100, w - 4))
    x0 = (w - cw) // 2
    alto = max(12, min(h - 2, 30))
    y0 = max(0, (h - alto) // 2)
    H.area(L, x0, y0, cw, alto, B.P1, foco_a=WS)
    tam = 8
    mw, _mh = MON.medidas(tam)
    s = {"t": time.monotonic() if t is None else t, "anim": {}, "agentes": [WS]}
    v = pan.vista()
    MON.dibujar(T, dict(WS, st="trabaja" if v == "run" else "libre"), x0 + 3, y0 + 2, tam, s=s,
                st="trabaja" if v == "run" else "libre", signo=False)
    tx, tw = x0 + mw + 6, cw - mw - 9
    fin = y0 + alto - 1
    T.put(tx, y0 + 1, _t("puertas.act.titulo", "Actualizaciones"), C["tx"], True)
    y = y0 + 3
    if v == "menu":
        for segs in _lineas_estado(pan.S):
            for r in D.envolver(segs, tw)[:2]:
                D._linea(T, tx, y, r, tx + tw)
                y += 1
        y += 1
        for i, (_tok, k, es, kd, esd) in enumerate(OPCIONES):
            if y + 3 > fin - 3:
                break
            xb = B.boton(L, {"agentes": [WS], "sel": 0}, tx, y, _t(k, es), "act:op:%d" % i, B.P1,
                         foco=i == pan.sel, a=WS, wmin=22)
            D._linea_corta(T, xb + 2, y + 1, [(_t(kd, esd), C["tx3"], False)], tx + tw)
            y += 4
    else:
        job = pan.job
        pasos = job.get("steps") or []
        hechos = sum(1 for p in pasos if p.get("st") in ("ok", "warn", "fail", "skip"))
        if v == "run":
            cab = _t("puertas.act.corriendo", "{que}: paso {i} de {n}…", que=job.get("label") or "",
                     i=min(len(pasos), hechos + 1), n=len(pasos))
            T.put(tx, y, P._corto(cab, tw) if hasattr(P, "_corto") else cab[:tw], C["tx2"])
        else:
            txt, col = _veredicto(job)
            for r in D.envolver([(txt, col, True)], tw)[:3]:
                D._linea(T, tx, y, r, tx + tw)
                y += 1
            y -= 1
        y += 2
        cabe = max(1, fin - 4 - y)
        if v == "done":
            pend = _AT()._pendientes(job) if job.get("findings") else []
            filas = []
            for _tit, x in pend:
                g, col = _icono("fail" if x.get("status") == "fail" else "warn")
                filas.append([(g + " ", col, True), (str(x.get("label") or ""), C["tx"], False)])
                if x.get("action"):
                    filas.append([("  → " + str(x["action"]), C["tx3"], False)])
            if not filas and job.get("n_new"):
                filas.append([(_t("puertas.act.llegaron", "Llegaron {n} cambio(s) nuevo(s): al volver, el hub se "
                                                          "abre de nuevo con ellos.", n=job["n_new"]), C["tx2"],
                               False)])
        else:
            filas = []
            visibles = pasos[max(0, len(pasos) - cabe):] if len(pasos) > cabe else pasos
            for p_ in visibles:
                g, col = _icono(p_.get("st"))
                filas.append([(g + " ", col, True), (str(p_.get("label") or ""),
                                                     C["tx"] if p_.get("st") == "run" else C["tx2"], False)])
        for segs in filas:
            for r in D.envolver(segs, tw)[:2]:
                if y >= fin - 3:
                    break
                D._linea(T, tx, y, r, tx + tw)
                y += 1
    # el pie: volver (y lo que hacen las teclas)
    yb = fin - 3
    lab = (_t("puertas.act.detener", "Detener") if v == "run" else _t("puertas.act.volver", "Volver al hub"))
    xb = B.boton(L, {"agentes": [WS], "sel": 0}, tx, yb, lab, "act:volver", B.P1, foco=v != "menu", a=WS)
    pie = ([("↑↓", _t("puertas.act.k_elige", "elige")), ("Enter", _t("puertas.act.k_hace", "hace")),
            ("Esc", _t("puertas.act.k_vuelve", "vuelve al hub"))] if v == "menu" else
           [("Esc", _t("puertas.act.k_detiene", "lo detiene entre pasos"))] if v == "run" else
           [("Enter", _t("puertas.act.k_vuelve", "vuelve al hub"))])
    xk = xb + 2
    for k, lab2 in pie:
        if xk + B.W(k) + B.W(lab2) + 4 > x0 + cw - 2:
            break
        xk = T.key(xk, yb + 1, k, lab2)
    T.flat()
    return P.afinar(T)


def correr(teclado=None, salida=None, pan=None):
    """La pantalla en esta terminal hasta que vuelves al hub. → 0."""
    out = salida or sys.stdout
    if not (sys.stdin.isatty() and out.isatty()) and teclado is None:
        return None
    pan = pan or Pantalla()
    pan.buscar()
    tec = teclado or P._Teclado()
    pin = P.Pintor(out)
    colores = P._colores()
    raton = P.raton_posible() and getattr(tec, "raton_ok", True)
    out.write("\x1b[?1049h\x1b[?25l" + (P.RATON_ON if raton else ""))
    out.flush()
    if raton and hasattr(tec, "raton"):
        tec.raton(True)
    try:
        while True:
            w, h = shutil.get_terminal_size((100, 30))
            T = pantalla(w, h, pan)
            pin.pintar(T, colores)
            k = tec.leer(0.25)
            if not k:
                continue
            if isinstance(k, P.Raton):
                zid = next((z[4] for z in reversed(T.zonas) if z[0] <= k.x < z[0] + z[2]
                            and z[1] <= k.y < z[1] + z[3]), "")
                if k.tipo == "mueve":
                    pan.sobre = zid
                elif k.tipo == "baja" and k.boton == 0:
                    pan.apretado = pan.sobre = zid
                elif k.tipo == "sube" and k.boton == 0:
                    ap, pan.apretado = pan.apretado, None
                    if ap and ap == zid and pan.clic(zid) == "salir":
                        return 0
                continue
            if pan.tecla(k) == "salir":
                return 0
    except KeyboardInterrupt:
        return 0
    finally:
        try:
            out.write((P.RATON_OFF if raton else "") + "\x1b[0m\x1b[?25h\x1b[?1049l")
            out.flush()
        except (OSError, ValueError):
            pass
        tec.soltar()


def _ejemplo(vista):
    pan = Pantalla(S={"chk": {"state": "done", "ok": True, "behind": 3, "new_version": "0.9.3"}})
    if vista in ("run", "done"):
        pan.S["job"] = {"label": "Actualizar", "done": vista == "done", "cancel": False, "error": "",
                        "findings": [], "n_new": 3 if vista == "done" else 0,
                        "steps": [{"label": "Bajar lo nuevo de Workspace", "st": "ok"},
                                  {"label": "Hooks por cerebro", "st": "ok" if vista == "done" else "run"},
                                  {"label": "Tema y lanzadores", "st": "ok" if vista == "done" else "pend"}]}
    return pan


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--render" in argv:
        i = argv.index("--render")
        w, h = (int(x) for x in argv[i + 1].lower().split("x"))
        vista = argv[argv.index("--vista") + 1] if "--vista" in argv else "menu"
        print("\n".join(pantalla(w, h, _ejemplo(vista), t=0.0).ansi(P._colores())))
        return 0
    return correr() or 0


if __name__ == "__main__":
    sys.exit(main())
