#!/usr/bin/env python3
"""WORKSPACE · motores_tui — la puerta de la sección MOTORES: dos cuadritos.

  Motores de agentes    la pantalla de siempre (engines_tui): qué motores
                        tienes, instalarlos y conectar tu cuenta
  Modelos de decisión   modelos_tui: conectar la llave y probar los
                        decisores (Jev hoy; los que vengan, por deciders/)

Los motores trabajan · los decisores eligen. Esc/q en cualquiera de las dos
pantallas regresa aquí; aquí, al hub. Stdlib.
"""
import os
import sys
from theme import screen as _theme_screen  # fondo/tinta del tema

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

try:
    import decisores_tui as DT                                  # noqa: E402
    import modelos_tui as MT                                    # noqa: E402
except Exception:
    # sin decisions.py (o con uno roto) Decisores no carga: como la puerta del
    # hub (front._abrir_motores), `python motores_tui.py` abre la pantalla de
    # motores de siempre — instalar y conectar un motor es esencial
    if __name__ == "__main__":
        import engines_tui
        sys.exit(engines_tui.run())
    raise
import hublayout as HL                                          # noqa: E402
import section_box as SB                                        # noqa: E402

_t = DT._t
CARDS = ("engines", "deciders")


def word():
    return HL.section_word("motores")


def _engines_status():
    """«3 de 9 instalados» — sin preguntar a nadie por la sesión (eso lo hace
    la pantalla de motores al abrir)."""
    try:
        import engines_tui
        rows = engines_tui._rows()
        n = sum(1 for d in rows if d.get("binaries_ok"))
        return _t("motores.menu.engines_st", "{n} de {m} instalados", n=n, m=len(rows)), \
            ("OK" if n else "DK")
    except Exception:
        return "", "DK"


def _deciders_status():
    """«Jev listo» — falla-suave: si algo de Decisores truena, la puerta abre
    igual (el cuadrito de motores es lo esencial)."""
    partes, col = [], "DK"
    try:
        for did in MT.models():
            if did not in MT.DC.deciders():
                continue
            st, c = MT.state(did)
            partes.append("%s %s" % (MT.name(did), st.split(" · ")[0]))
            if c == "OK":
                col = "OK"
    except Exception:
        return "", "DK"
    return " · ".join(partes), col


def initial():
    S = {"i": 0, "msg": "", "go": None}
    refresh(S)
    return S


def refresh(S):
    S["st"] = {"engines": _engines_status(), "deciders": _deciders_status()}


def _label(c):
    return (_t("motores.menu.engines", "Motores de agentes") if c == "engines"
            else _t("motores.menu.deciders", "Modelos de decisión"))


def _what(c):
    return (_t("motores.menu.engines_what", "programan y conversan") if c == "engines"
            else _t("motores.menu.deciders_what", "eligen entre opciones fijas"))


def body(S, K, iw):
    L = [DT.center("%s%s%s" % (K["DIM"], _t("modelos.concept", "los motores trabajan · los decisores "
                                             "eligen"), K["R"]), iw), ""]
    row = []
    for k, (c, w) in enumerate(zip(CARDS, DT.anchos(iw, 2))):
        foco = k == S["i"]
        st, col = (S.get("st") or {}).get(c, ("", "DK"))
        row.append(DT.caja(K, ["%s%s%s" % ((K["WH"] + K["BO"]) if foco else K["GREY"], _label(c), K["R"]),
                               "%s%s%s" % (K["DIM"], _what(c), K["R"]), "",
                               "%s%s%s" % (K[col], st, K["R"])], w,
                           (K["C"] + K["BO"]) if foco else K["B2"], heavy=foco, centrar=True))
    S["_cur"] = len(L) + 2
    L += DT.hjoin(row)
    L.append("")
    pista = (_t("motores.menu.engines_hint", "Instálalos y conecta tu cuenta: Claude Code, Codex, "
                "Antigravity…") if CARDS[S["i"]] == "engines"
             else _t("motores.menu.deciders_hint", "Conecta su llave y prueba los decisores; dónde "
                     "actúan se elige en Decisores."))
    L += [DT.center("%s%s%s" % (K["GREY"], ln, K["R"]), iw) for ln in DT.wrap(pista, iw)]
    return [HL.clip(x, iw) for x in L]


def _info_txt():
    return (_t("motores.menu.info.p", "Dos tipos de modelo. Los motores de agentes trabajan contigo: "
               "programan, escriben y conversan. Los modelos de decisión no conversan: eligen entre "
               "opciones fijas y dicen qué tan seguros están."),
            [_t("motores.menu.info.l1", "Motores de agentes — la pantalla de siempre"),
             _t("motores.menu.info.l2", "Modelos de decisión — conectar la llave, probar"),
             _t("motores.menu.info.l3", "Dónde decide cada uno: sección Decisores")])


def _flujo_que():
    return [(_t("motores.menu.f1", "motores"), _t("motores.menu.f1n", "trabajan contigo")),
            (_t("motores.menu.f2", "decisores"), _t("motores.menu.f2n", "eligen entre opciones")),
            (_t("motores.menu.f3", "Decisores"), _t("motores.menu.f3n", "dónde actúa cada uno"))]


def _flujo_como():
    return [(_t("motores.menu.c1", "una puerta"), _t("motores.menu.c1n", "dos cuadritos")),
            (_t("motores.menu.c2", "lo de siempre"), _t("motores.menu.c2n", "Motores no cambió")),
            (_t("motores.menu.c3", "deciders/"), _t("motores.menu.c3n", "cada modelo con su META"))]


def _como_p():
    return _t("motores.menu.how.p", "Motores de agentes es la misma pantalla de antes, sin cambios. "
              "Modelos de decisión se arma sola con los archivos de deciders/: un modelo nuevo "
              "aparece sin tocar nada más.")


def info_body(K, iw):
    texto, lista = _info_txt()
    L = [DT.titulo(K, _t("decisores.info.what", "qué es"), iw, 0), ""] + DT.flujo(K, _flujo_que(), iw, 0) + [""]
    lw = (iw - 3) // 2
    izq = ["%s%s%s" % (K["WH"], ln, K["R"]) for ln in DT.wrap(texto, lw)]
    der = []
    for x in lista:
        for j, ln in enumerate(DT.wrap(x, lw - 2)):
            der.append("%s%s%s %s%s%s" % (K["C"], "·" if j == 0 else " ", K["R"], K["GREY"], ln, K["R"]))
    for i in range(max(len(izq), len(der))):
        a = izq[i] if i < len(izq) else ""
        b = der[i] if i < len(der) else ""
        L.append(HL.pad(a, lw) + " %s│%s " % (K["DK"], K["R"]) + b)
    L += ["", DT.titulo(K, _t("decisores.info.how", "cómo lo hicimos"), iw, 3), ""] \
        + DT.flujo(K, _flujo_como(), iw, 2) + [""]
    L += ["%s%s%s" % (K["GREY"], ln, K["R"]) for ln in DT.wrap(_como_p(), iw)]
    return [HL.clip(x, iw) for x in L]


def info_blocks():
    texto, lista = _info_txt()
    return [("flow", _flujo_que()), ("gap",), ("p", texto), ("list", lista), ("gap",),
            ("h", _t("decisores.info.how", "cómo lo hicimos")), ("flow", _flujo_como()),
            ("p", _como_p())]


def _chips():
    return ((u"←→", _t("decisores.k.move", "moverse")), ("Enter", _t("decisores.k.open", "abrir")),
            ("?", _t("decisores.k.help", "ayuda")), ("q", _t("decisores.k.quit", "salir")))


def render(S, w, h):
    K = SB.K()
    titulo = _t("motores.box", "MOTORES")
    if S.get("info"):
        cab = "%s · %s" % (_t("decisores.info.title", "AYUDA"), titulo)
        bw = max(60, min(96, w - 10))
        if bw < 70:
            return SB.info_frame(K, w, h, word(), cab, info_blocks(), state=S["info"], box_w=60)
        st = S["info"] if isinstance(S["info"], dict) else {}
        out = SB.frame(K, w, h, word(), cab, lambda iw: info_body(K, iw),
                       ((u"↑↓", _t("decisores.k.move_info", "mover")), ("Esc", _t("decisores.k.close", "cerrar"))),
                       box_w=bw, scroll=st.get("scroll", 0))
        st["scroll"] = max(0, min(st.get("scroll", 0), SB.frame.last_max_scroll))
        return out
    return SB.frame(K, w, h, word(), titulo, lambda iw: body(S, K, iw), _chips(),
                    msg=S.get("msg", ""), cursor_line=lambda: S.get("_cur", 0), box_w=64,
                    stable_rows=10)


def act(S, key):
    """False = salir del bucle: al hub (S["go"] None) o a una pantalla."""
    if SB.info_key(S, key):
        return True
    S["msg"] = ""
    if key in ("q", "Q", "\x1b", "\x03"):
        S["go"] = None
        return False
    if key in ("left", "right", "up", "down", "tab"):
        S["i"] = (S["i"] + (-1 if key in ("left", "up") else 1)) % len(CARDS)
    elif key in ("\r", "\n", " "):
        S["go"] = CARDS[S["i"]]
        return False
    return True


import responsive_ui as _responsive  # noqa: E402
render = _responsive.renderer(render, 'MOTORES')
act = _responsive.action(act)


def open_screen(go):
    """Abre la pantalla elegida (sin volver a aplicar el tema: ya está)."""
    if go == "engines":
        import engines_tui
        return engines_tui.run.__wrapped__()
    return MT.run.__wrapped__()


@_theme_screen
def run():
    S = initial()
    if not MT._interactive():
        print("\n".join(render(S, 112, 44)))
        return 0
    while True:
        S["go"] = None
        MT.loop(S, render, act, busy_fn=lambda _S: False)
        go = S.get("go")
        if not go:
            return 0
        try:
            open_screen(go)
        except KeyboardInterrupt:                      # Ctrl+C adentro: de vuelta a la puerta
            pass
        except Exception as e:
            S["msg"] = "%s: %s" % (_label(go), type(e).__name__)
        refresh(S)


if __name__ == "__main__":
    sys.exit(run())
