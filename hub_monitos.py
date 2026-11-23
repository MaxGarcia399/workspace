#!/usr/bin/env python3
r"""WORKSPACE · hub_monitos — el ÚNICO lugar donde el hub de prueba dibuja un monito. SOLO PARA PROBAR: vive en las
ramas zenith/hub-* y nunca entra a main.

Todo lo que pinta un monito (el riel, la fila de monitos, la sección Agentes, el menú de sesiones S-1) llama a
`dibujar()`; nadie más llama a hub_paleta.monito. Así un juego nuevo de sprites (con sus animaciones) entra sin tocar
las pantallas: se registra con `registrar(nombre, dibujar, medidas, espera)` y se elige con WORKSPACE_MONITOS=<nombre>
(o `usar(nombre)`). El de hoy es «m1» (M-1 «Rejilla afinada», hub_monitos_m1); «paleta» (los de hub_paleta) sigue.

Contrato de un juego:
  · dibujar(T, a, x, y, tam, s, st, signo) pinta al agente `a` ({"c": color, "f": forma, "id", ...}) donde va el de
    la Paleta (de la columna x-1 a x+tam, de pie en la fila y + alto) con la animación del cuadro `s`; `tam` = 8 en
    el riel, 16 en S-1;
  · medidas(tam) → (ancho, alto) en celdas, sin el signo de arriba (el riel deja una fila encima para él);
  · espera(s) → cuándo cambia el siguiente cuadro (el hub duerme hasta entonces).
Stdlib."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

#: Los juegos de sprites: nombre → (dibujar, medidas, espera).
JUEGOS = {}
_ELEGIDO = [None]
#: El de hoy: M-1 «Rejilla afinada» (hub_monitos_m1). «paleta» (los de hub_paleta) sigue con WORKSPACE_MONITOS=paleta.
DEFECTO = "m1"


def registrar(nombre, dibujar_, medidas_, espera_=None):
    """Un juego: dibujar(T, a, x, y, tam, s, st, signo); medidas(tam) → (ancho, alto) en celdas; espera(s) → segundos
    hasta que algún monito de la instantánea `s` cambie (None: todos quietos)."""
    JUEGOS[nombre] = (dibujar_, medidas_, espera_)


def usar(nombre):
    """Elige el juego `nombre` para lo que queda de esta corrida (None: el de WORKSPACE_MONITOS o el de hoy)."""
    _ELEGIDO[0] = nombre


def juego():
    n = _ELEGIDO[0] or os.environ.get("WORKSPACE_MONITOS") or DEFECTO
    if n == "paleta" and not _ELEGIDO[0]:              # los de antes: solo en una copia de desarrollo (puertas)
        try:
            import puertas
            if not puertas.dev():
                n = DEFECTO
        except Exception:
            n = DEFECTO
    return n if n in JUEGOS else DEFECTO


def medidas(tam=8):
    return JUEGOS[juego()][1](tam)


def dibujar(T, a, x, y, tam=8, s=None, st=None, signo=True):
    """El monito de `a` en (x, y), de `tam` celdas de ancho (8 en el riel, 16 en S-1). `s`: la instantánea del hub
    (su reloj `t` y sus animaciones `anim`: brinco, fiesta, gel); sin `s`, quieto. `st`: su estado si no es el suyo;
    `signo`: el signo de arriba (✓ ? z …)."""
    st = st or a.get("st") or "libre"
    JUEGOS[juego()][0](T, a, x, y, tam, s, st, signo)


def espera(s):
    """Cada cuánto hay que volver a pintar los monitos de `s` (s), o None si están quietos."""
    fn = JUEGOS[juego()][2]
    return fn(s) if fn else None


# ── «paleta»: los de hub_paleta (hasta H-1) ───────────────────────────────────
def _paleta_dibujar(T, a, x, y, tam, s, st, signo):
    import hub_paleta as P
    fase, mira, puntos = (None, 0, 2)
    if s:
        import hub_directo as D
        fase, mira, puntos = D._anim(s, a.get("id") or "", st)
    P.monito(T, a, x, y, tam, fase=fase, st=st, mira=mira, puntos=puntos, sin_signo=not signo)


def _paleta_medidas(tam):
    return tam, max(1, tam // 2)


def _paleta_espera(s):
    import hub_directo as D
    import hub_paleta as P
    t = s.get("t") or 0.0
    for an in (s.get("anim") or {}).values():
        if an.get("brinco") is not None and 0 <= t - an["brinco"] < P.BRINCO_S:
            return P.CUADRO_S
        if an.get("fiesta") is not None and 0 <= t - an["fiesta"] < D.FIESTA_S:
            return P.CUADRO_S
    if any(b.get("st") == "trabaja" for b in s.get("agentes") or ()):
        return D.PIENSA_S
    return None


registrar("paleta", _paleta_dibujar, _paleta_medidas, _paleta_espera)


# ── «m1»: M-1 «Rejilla afinada» (hub_monitos_m1) ──────────────────────────────
def _m1(nombre):
    def fn(*a):
        import hub_monitos_m1 as M1
        return getattr(M1, nombre)(*a)
    return fn


registrar("m1", _m1("dibujar"), _m1("medidas"), _m1("espera"))
