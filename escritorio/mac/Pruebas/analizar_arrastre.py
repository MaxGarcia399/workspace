#!/usr/bin/env python3
"""Lee lo que anotó el medidor del arrastre (MedirArrastre.swift: <medir>.arrastre.json) y dice, con números:

  · cuánto tarda en moverse desde que aprietas y desde que el ratón pasa el umbral (en ms y en cuadros; tope: uno),
  · si sigue al ratón cuadro a cuadro (huecos entre movimientos del panel mientras el ratón se mueve; tope: 50 ms),
  · los atorones del hilo principal de la app y los cuadros de la burbuja (requestAnimationFrame),
  · si alguna vez quedó montado entre dos pantallas (macOS no lo pinta en ninguna mientras tanto),
  · al soltarlo: cuánto tarda en quedarse quieto y si el nido brincó en la pantalla,
  · cuántas veces se escribió lugar.json mientras lo arrastrabas (debe ser 0) y al soltarlo (1),
  · si el panel se quedó con el teclado,
  · y con el guion «clic»: cuánto tarda en abrirse la barra.

  python3 analizar_arrastre.py <archivo.arrastre.json> [--json]
Stdlib."""
import json
import sys

CUADRO = 1000 / 60


def area(a, b):
    """Lo que se enciman dos rectángulos (x, y, w, h)."""
    w = min(a[0] + a[2], b[0] + b[2]) - max(a[0], b[0])
    h = min(a[1] + a[3], b[1] + b[3]) - max(a[1], b[1])
    return max(0, w) * max(0, h)


def analizar(d):
    pant = [p["marco"] for p in d["pantallas"]]
    h0 = pant[0][1] + pant[0][3]
    ev = d["eventos"]
    abajo = [e for e in ev if e[1] == "abajo"]
    arriba = [e for e in ev if e[1] == "arriba"]
    out = {"guion": d["guion"], "alfa": d.get("alfa")}
    panel = d["panel"]
    # las ventanas de la app según el servidor de ventanas, en AppKit (abajo-izquierda)
    marcos = []                       # (t, {id: (x, y, w, h, alfa)})
    for fila in d["ventanas"]:
        t, resto = fila[0], fila[1:]
        vs = {}
        for i in range(0, len(resto), 6):
            n, x, y, w, h, a = resto[i:i + 6]
            vs[int(n)] = (x, h0 - (y + h), w, h, a)
        marcos.append((t, vs))

    def del_panel(t):
        """El marco del panel en el servidor de ventanas en el tiempo t (la última muestra antes)."""
        r = None
        for tt, vs in marcos:
            if tt > t:
                break
            r = vs.get(panel, r)
        return r

    if not abajo:
        return out
    # el arrastre de verdad: el último «abajo» (si hubo un clic para calentar, ese no)
    t_abajo = abajo[-1][0]
    p0 = abajo[-1][2:4]
    t_arriba = arriba[-1][0] if arriba else None
    out["teclado_tras_apretar"] = next((k[2] for k in d.get("teclado", []) if k[0] >= t_abajo), None)
    out["teclado_al_final"] = d.get("teclado", [[0, 0, None]])[-1][2]
    if d["guion"] == "clic":
        epoca0 = d.get("epoca0", 0)
        barra = next(((c[0] / 1000 - epoca0) for c in d["pagina"] if "·barra" in c[7] and (c[0] / 1000 - epoca0) > t_abajo), None)
        out["clic_a_barra_ms"] = round((barra - t_arriba) * 1000, 1) if barra and t_arriba else None
        return out
    # el umbral: el primer evento a más de 4 pt de donde apretaste
    umbral = next((e for e in ev if e[0] > t_abajo and e[1] == "arrastra" and ((e[2] - p0[0]) ** 2 + (e[3] - p0[1]) ** 2) ** .5 > 4), None)
    ini = del_panel(t_abajo)
    primero = next(((t, vs[panel]) for t, vs in marcos if t > t_abajo and panel in vs and ini and
                    (abs(vs[panel][0] - ini[0]) > .5 or abs(vs[panel][1] - ini[1]) > .5)), None)
    if primero is None:
        out["se_movio"] = False
        return out
    out["se_movio"] = True
    out["apretar_a_moverse_ms"] = round((primero[0] - t_abajo) * 1000, 1)
    out["umbral_a_moverse_ms"] = round((primero[0] - umbral[0]) * 1000, 1) if umbral else None
    # en cuadros de la pantalla: cuántos refrescos pasaron entre el umbral y verlo movido en el servidor de ventanas
    # (1 = el siguiente cuadro; la muestra del servidor es cada 3 ms, así que «ms» puede pasar un poco de 16.7)
    if umbral:
        out["cuadros_hasta_moverse"] = sum(1 for c in d["cuadros"] if umbral[0] < c[0] <= primero[0])
    # lo que se queda atrás del ratón: el nido debía ir a (ratón − agarre); el agarre, el del primer movimiento
    agarre = (p0[0] - ini[0], p0[1] - ini[1])
    errores = []
    for c in d["cuadros"]:
        t, x, y, rx, ry = c[2], c[3] + c[7], c[4] + c[8], c[9], c[10]
        if primero[0] <= t <= (t_arriba or 1e9):
            errores.append(((rx - agarre[0] - x) ** 2 + (ry - agarre[1] - y) ** 2) ** .5)
    if errores:
        errores.sort()
        out["atras_del_raton_pt"] = {"mediana": round(errores[len(errores) // 2], 1), "max": round(errores[-1], 1)}
    # huecos entre movimientos del panel en el servidor mientras el ratón se mueve (del primer movimiento a soltar)
    ultimo_mov = max((e[0] for e in ev if e[1] == "arrastra"), default=t_arriba)
    movs, antes = [], None
    for t, vs in marcos:
        if panel not in vs or t < primero[0] or t > ultimo_mov:
            continue
        v = vs[panel][:2]
        if v != antes:
            movs.append(t)
            antes = v
    huecos = sorted(((movs[i + 1] - movs[i]) * 1000 for i in range(len(movs) - 1)), reverse=True)
    out["movimientos_del_panel"] = len(movs)
    out["hueco_max_ms"] = round(huecos[0], 1) if huecos else None
    out["huecos_mayores_a_50ms"] = sum(1 for h in huecos if h > 50)
    # montado entre dos pantallas: cuánto tiempo, mientras lo arrastras y al soltarlo
    montado, t_prev, desde = 0.0, None, None
    fin_obs = (t_arriba or 0) + 1.0
    for t, vs in marcos:
        if t < t_abajo or t > fin_obs:
            continue
        m = False
        for n, v in vs.items():
            if v[2] * v[3] < 100:          # el relevo del teclado (1×1)
                continue
            # montada de verdad: lo que queda en la otra pantalla es más del 10 % (con el filo de 6 pt del margen de la
            # sombra, macOS la pinta entera en la suya; medido: con 20-30 % en la otra ya no la pinta en ninguna)
            partes = sorted((area(v[:4], p) for p in pant), reverse=True)
            m = m or (len(partes) > 1 and partes[1] > 0.10 * max(partes[0] + partes[1], 1))
        if t_prev is not None and desde:
            montado += t - t_prev
        desde = m
        t_prev = t
    out["montado_entre_pantallas_ms"] = round(montado * 1000)
    # al soltar: cuándo deja de moverse el panel y si el nido brincó en la pantalla
    if t_arriba:
        ult, antes_v = t_arriba, del_panel(t_arriba)
        for t, vs in marcos:
            if t > t_arriba and panel in vs and vs[panel][:4] != (antes_v or (None,))[:4]:
                ult, antes_v = t, vs[panel]
        out["soltar_a_quieto_ms"] = round((ult - t_arriba) * 1000)
        epoca0 = d.get("epoca0", 0)
        pos = []
        for c in d["pagina"]:
            t = c[0] / 1000 - epoca0
            if t < t_abajo:
                continue
            m = del_panel(t)
            if not m:
                continue
            # el nido en la pantalla: el panel (servidor) + el nido en la página (arriba-izquierda del web view)
            wx = next((k[7] for k in d["cuadros"] if k[2] >= t), 0)
            wy = next((k[8] for k in d["cuadros"] if k[2] >= t), 0)
            wh = next((k[6] for k in d["cuadros"] if k[2] >= t), m[3])
            cx = m[0] + wx + c[1] + c[3] / 2
            cy = m[1] + wy + (wh - (c[2] + c[4] / 2))
            if "mudando" in c[7]:            # escondido (la foto de la app lo tapa): no se ve, no cuenta
                continue
            pos.append((t, cx, cy, c[7]))
        brincos = []
        for i in range(1, len(pos)):
            t, x, y, _ = pos[i]
            if t < t_arriba:
                continue
            dx, dy = x - pos[i - 1][1], y - pos[i - 1][2]
            dist = (dx * dx + dy * dy) ** .5
            if dist > 40:
                brincos.append([round((t - t_arriba) * 1000), round(dist)])
        out["brincos_del_nido_al_soltar"] = brincos
        fotos = [t for t, vs in marcos if t > t_arriba and any(n != panel and v[2] * v[3] > 100 for n, v in vs.items())]
        out["foto_del_nido_ms"] = round((fotos[-1] - fotos[0]) * 1000) if len(fotos) > 1 else 0
    # atorones y cuadros de la burbuja durante el arrastre (de apretar a 0.6 s después de soltar)
    hasta = (t_arriba or t_abajo) + 0.6
    at = [a for a in d["atorones"] if t_abajo <= a[0] <= hasta]
    out["hilo_principal_atoron_max_ms"] = round(max((a[1] for a in at), default=0), 1)
    out["hilo_principal_atorones_mayores_a_50ms"] = sum(1 for a in at if a[1] > 50)
    epoca0 = d.get("epoca0", 0)
    pg = [c[0] / 1000 - epoca0 for c in d["pagina"]]
    pg = [t for t in pg if t_abajo <= t <= hasta]
    raf = sorted(((pg[i + 1] - pg[i]) * 1000 for i in range(len(pg) - 1)), reverse=True)
    out["burbuja_cuadro_max_ms"] = round(raf[0], 1) if raf else None
    out["burbuja_cuadros_mayores_a_50ms"] = sum(1 for r in raf if r > 50)
    out["burbuja_cuadros_por_s"] = round(len(pg) / max(hasta - t_abajo, 1e-3), 1)
    # lugar.json
    out["lugar_escrito_al_arrastrar"] = sum(1 for w in d["escrituras"] if t_abajo <= w < (t_arriba or 1e9))
    out["lugar_escrito_al_soltar"] = sum(1 for w in d["escrituras"] if t_arriba and w >= t_arriba)
    return out


def main(argv):
    d = json.load(open(argv[1], encoding="utf-8"))
    r = analizar(d)
    if "--json" in argv:
        print(json.dumps(r, ensure_ascii=False))
    else:
        for k, v in r.items():
            print(f"{k:42} {v}")


if __name__ == "__main__":
    main(sys.argv)
