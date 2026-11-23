#!/usr/bin/env python3
"""WORKSPACE · historial_eventos — el historial de la conversación de la página: un registro de eventos, solo de anexar.

Antes el historial se rearmaba fusionando ventanas de pantalla con lo guardado, y cada heurística nueva dejaba otro
hueco: lo viejo se reimportaba al volver a un motor, la ventana entera se pegaba otra vez y el tope se llevaba lo real
(H9 con Antigravity, N1 con Kiro). Ahora es una invariante, no una heurística:

- Un evento por renglón (JSON), con id único: {"id", "rol": "yo" | "agente" | "sistema", "texto", "motor", "t", "ts",
  "envio_id"?, "herr"?, "contexto"?, "importado"?, "tipo"? (los de sistema: motor · contexto · importado · migrado ·
  restaurado)}.
- Solo se anexa: ningún evento se reescribe ni se borra. Uno cuyo id ya está no se vuelve a escribir, y al leer gana
  el primero (dos procesos que anexan lo mismo a la vez no lo duplican).
- Lo que se ENSEÑA tiene tope; lo que se GUARDA no. Pasados ROTAR_EN eventos (o ROTAR_BYTES), los más viejos se anexan al
  archivo viejo (`<nombre>.archivo.jsonl`) y solo después el principal se reescribe sin ellos: el total nunca baja.
- Un renglón que no se lee (un corte a medio sync) se salta: no tumba la conversación.

Además, una vez por cerebro: `migrar` convierte el historial de antes (segmentos) tal cual, con respaldo; y `restaurar`
rehace uno dañado desde su respaldo más lo que vino después (sin las ventanas que se pegaron otra vez).

Solo stdlib. Candados: uno por proceso (hilos) y olock.local_lock entre procesos (en `.claude/locks`, que no viaja).

Uso a mano (restaurar el de un agente; respalda lo que haya antes de escribir):
    python3 historial_eventos.py restaurar --respaldo <navegador.json bueno> --historial <carpeta historial del agente>
"""
import hashlib
import json
import os
import shutil
import sys
import threading
import time

ROTAR_EN = 4000          # eventos en el principal antes de mandar los más viejos al archivo viejo
QUEDAN = 2000            # los que se quedan en el principal al rotar (la página enseña muchos menos)
ROTAR_BYTES = 4 << 20    # o pasado este tamaño (respuestas larguísimas): se va la mitad más vieja
_LOCK = threading.RLock()
_CACHE = {}              # ruta → {"ino", "fin", "eventos", "ids"}: lo leído hasta `fin` (solo crece: se lee lo nuevo)
_CACHE_ARCH = {}         # ruta del archivo viejo → {"firma", "ids", "n"}


def archivo_de(ruta):
    """El archivo viejo de `ruta` (navegador.eventos.jsonl → navegador.eventos.archivo.jsonl)."""
    base, ext = os.path.splitext(ruta)
    return base + ".archivo" + ext


def _renglones(ruta, desde):
    """(eventos, fin): los renglones completos de `ruta` desde el byte `desde`; uno a medio escribir (sin su salto) se
    deja para la siguiente lectura."""
    try:
        with open(ruta, "rb") as f:
            f.seek(desde)
            crudo = f.read()
    except OSError:
        return [], desde
    fin = crudo.rfind(b"\n") + 1
    out = []
    for ln in crudo[:fin].split(b"\n"):
        if not ln.strip():
            continue
        try:
            e = json.loads(ln.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(e, dict) and isinstance(e.get("id"), str) and e["id"] \
                and e.get("rol") in ("yo", "agente", "sistema"):
            out.append(e)
    return out, desde + fin


def _archivados(ruta):
    """{"ids", "n"} del archivo viejo de `ruta` (n: los que se enseñan, sin los de sistema)."""
    arch = archivo_de(ruta)
    try:
        st = os.stat(arch)
        firma = (st.st_ino, st.st_size, st.st_mtime_ns)
    except OSError:
        _CACHE_ARCH.pop(arch, None)
        return {"ids": frozenset(), "n": 0}
    c = _CACHE_ARCH.get(arch)
    if c and c["firma"] == firma:
        return c
    ids, n = set(), 0
    for e in _renglones(arch, 0)[0]:
        if e["id"] not in ids:
            ids.add(e["id"])
            n += e.get("rol") != "sistema"
    c = _CACHE_ARCH[arch] = {"firma": firma, "ids": frozenset(ids), "n": n}
    return c


def leer(ruta):
    """Los eventos del principal, en orden: sin ids repetidos (gana el primero) ni los que ya pasaron al archivo viejo.
    Incremental: si el archivo solo creció, se lee lo nuevo. [] si no existe."""
    with _LOCK:
        try:
            st = os.stat(ruta)
        except OSError:
            _CACHE.pop(ruta, None)
            return []
        c = _CACHE.get(ruta)
        if not c or c["ino"] != st.st_ino or st.st_size < c["fin"]:
            c = {"ino": st.st_ino, "fin": 0, "eventos": [], "ids": set(_archivados(ruta)["ids"])}
        if st.st_size > c["fin"]:
            nuevos, c["fin"] = _renglones(ruta, c["fin"])
            eventos = list(c["eventos"])                 # copia: quien tiene la lista anterior no la ve cambiar
            for e in nuevos:
                if e["id"] not in c["ids"]:
                    c["ids"].add(e["id"])
                    eventos.append(e)
            c["eventos"] = eventos
        _CACHE[ruta] = c
        return c["eventos"]


def total(ruta):
    """Cuántos eventos hay guardados en total (el principal y el archivo viejo)."""
    return len(leer(ruta)) + len(_archivados(ruta)["ids"])


def antes_de(ruta):
    """Cuántos turnos (sin los de sistema) quedaron en el archivo viejo: el índice del primero del principal."""
    return _archivados(ruta)["n"]


def _linea(eventos):
    return "".join(json.dumps(e, ensure_ascii=False, separators=(",", ":")) + "\n" for e in eventos)


def anexar(ruta, eventos):
    """Agrega al final los `eventos` cuyo id no está (ni en el archivo viejo). → los que de verdad se escribieron."""
    import atomico
    import olock
    with _LOCK, olock.local_lock(ruta, timeout=10):
        ids = {e["id"] for e in leer(ruta)} | set(_archivados(ruta)["ids"])
        nuevos = []
        for e in eventos:
            if e.get("id") and e["id"] not in ids:
                ids.add(e["id"])
                nuevos.append(e)
        if not nuevos:
            return []
        datos = _linea(nuevos)
        try:
            with open(ruta, "rb") as f:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    datos = "\n" + datos                 # el último renglón quedó cortado: el nuevo va en el suyo
        except OSError:
            pass
        os.makedirs(os.path.dirname(ruta) or ".", exist_ok=True)
        atomico.anexar(ruta, datos)
        _rotar(ruta)
    return nuevos


def crear(ruta, eventos):
    """El registro nuevo con `eventos` (de una vez, atómico). No pisa uno que ya exista. → True si lo creó."""
    import atomico
    import olock
    with _LOCK, olock.local_lock(ruta, timeout=10):
        if os.path.exists(ruta):
            return False
        vistos, limpios = set(), []
        for e in eventos:
            if e["id"] not in vistos:
                vistos.add(e["id"])
                limpios.append(e)
        atomico.escribir(ruta, _linea(limpios))
        _CACHE.pop(ruta, None)
    return True


def _rotar(ruta):
    """(Con el candado.) Pasados ROTAR_EN eventos o ROTAR_BYTES, los más viejos se ANEXAN al archivo viejo (y se
    sincroniza a disco) y solo después el principal se reescribe sin ellos. Si algo falla en medio, los que quedaron en
    los dos se leen una vez."""
    import atomico
    evs = leer(ruta)
    try:
        tam = os.path.getsize(ruta)
    except OSError:
        return
    n = QUEDAN if len(evs) > ROTAR_EN else len(evs) // 2 if tam > ROTAR_BYTES else 0
    if not 0 < n < len(evs):
        return
    viejos, quedan = evs[:-n], evs[-n:]
    arch = archivo_de(ruta)
    atomico.anexar(arch, _linea(viejos))
    try:
        fd = os.open(arch, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError:
        pass
    if not {e["id"] for e in viejos} <= set(_archivados(ruta)["ids"]):
        return                                           # no quedaron en el archivo viejo: el principal no se toca
    atomico.escribir(ruta, _linea(quedan))
    _CACHE.pop(ruta, None)


# ── el historial de antes (segmentos por motor) → eventos ──
def _id(prefijo, *partes):
    return prefijo + hashlib.sha1("\x1f".join(str(p) for p in partes).encode("utf-8")).hexdigest()[:14]


def _iso(t):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(float(t))) + "Z" if t else ""


def _segmentos(ruta):
    with open(ruta, encoding="utf-8") as f:
        segs = json.load(f).get("segmentos")
    if not isinstance(segs, list):
        raise ValueError("sin segmentos")
    return [s for s in segs if isinstance(s, dict) and isinstance(s.get("turnos"), list)]


def de_segmentos(segs, marca, prefijo="h"):
    """Los turnos de los segmentos, tal cual y en orden, como eventos (`importado`: `marca`), con un evento «motor» al
    principio de cada segmento. Ids estables (mismo historial → mismos ids)."""
    out = []
    for i, s in enumerate(segs):
        motor = str(s.get("motor") or "")
        t0 = float(s.get("desde") or 0) or float(s.get("hasta") or 0)
        out.append({"id": _id(prefijo + "m-", i, motor, s.get("desde")), "rol": "sistema", "tipo": "motor",
                    "motor": motor, "t": t0, "ts": _iso(t0)})
        for j, x in enumerate(s["turnos"]):
            if not isinstance(x, dict) or x.get("rol") not in ("yo", "agente"):
                continue
            e = {"id": _id(prefijo + "-", i, j, x.get("rol"), x.get("texto")), "rol": x["rol"],
                 "texto": str(x.get("texto") or ""), "motor": motor, "t": t0, "ts": str(x.get("ts") or ""),
                 "herr": x.get("herr") if isinstance(x.get("herr"), list) else [], "importado": marca}
            for k in ("contexto", "arranque"):
                if x.get(k):
                    e[k] = True
            out.append(e)
        if s.get("contado"):                               # a ese motor ya se le contó lo de los otros en esa vuelta
            out.append({"id": _id(prefijo + "c-", i, motor, s.get("desde")), "rol": "sistema", "tipo": "contexto",
                        "motor": motor, "t": t0, "ts": _iso(t0)})
    return out


def _respaldar(ruta, etiqueta):
    """Copia `ruta` junto a ella (<nombre>.respaldo-<etiqueta>-AAAAMMDD-HHMMSS<ext>). → el nombre, o "" si no había."""
    if not os.path.exists(ruta):
        return ""
    base, ext = os.path.splitext(ruta)
    nombre = "%s.respaldo-%s-%s%s" % (base, etiqueta, time.strftime("%Y%m%d-%H%M%S"), ext)
    n = 1
    while os.path.exists(nombre):
        n += 1
        nombre = "%s.respaldo-%s-%s-%d%s" % (base, etiqueta, time.strftime("%Y%m%d-%H%M%S"), n, ext)
    shutil.copy2(ruta, nombre)
    return os.path.basename(nombre)


def migrar(viejo, ruta):
    """El historial de antes (`viejo`, segmentos) → el registro `ruta`, tal cual, una vez, con un respaldo del de antes
    junto a él (el de antes no se toca). Ilegible: se respalda y se empieza vacío. → cuántos turnos pasaron."""
    if os.path.exists(ruta):
        return 0
    copia = _respaldar(viejo, "migracion")
    try:
        evs = de_segmentos(_segmentos(viejo), "migrado")
        podados = 0
        with open(viejo, encoding="utf-8") as f:
            podados = sum(int(s.get("podados") or 0) for s in json.load(f).get("segmentos") or [] if isinstance(s, dict))
    except (OSError, ValueError, AttributeError, TypeError):
        evs, podados = [], 0
    n = sum(e["rol"] != "sistema" for e in evs)
    ahora = time.time()
    crear(ruta, [{"id": _id("mig-", ruta, n), "rol": "sistema", "tipo": "migrado", "texto": "", "motor": "",
                  "t": ahora, "ts": _iso(ahora), "n": n, "podados": podados, "respaldo": copia}] + evs)
    return n


# ── restaurar uno dañado: su respaldo + lo de después, sin las ventanas que se pegaron otra vez ──
def _plano(x):
    return " ".join(str(x.get("texto") or "").split())


def _bloques(turnos):
    """(lo del agente antes de tu primer mensaje, [(tu mensaje, [lo del agente después])])."""
    antes, bloques = [], []
    for x in turnos:
        if x.get("rol") == "yo":
            bloques.append((x, []))
        elif bloques:
            bloques[-1][1].append(x)
        else:
            antes.append(x)
    return antes, bloques


def sin_ventanas(previo, nuevos):
    """Lo de verdad nuevo de `nuevos` (un segmento leído de pantalla, sin hora), sabiendo que `previo` (el segmento
    anterior de ese motor) es lo que su pantalla enseñaba al volver. Una ventana de pantalla siempre es el FINAL de la
    conversación hasta ese momento: un tramo de tus mensajes que repite, en orden y hasta el último, lo que ya se tenía
    es esa ventana pegada otra vez (con uno solo, también su respuesta debe ser la misma). Lo del agente va con tu
    mensaje de antes; un mensaje tuyo que es el principio del siguiente era lo escrito en su caja (se mandó con él).
    → (lo nuevo, cuántos turnos se quitaron). El texto de ejemplo de su caja guardado como mensaje tuyo (H10, antes del
    arreglo) no cuenta: no estaba en su conversación."""
    from pantalla_motor import _CAJA_EJEMPLO_RE
    _ag, previos = _bloques(previo)
    previos = [b for b in previos if not _CAJA_EJEMPLO_RE.match(_plano(b[0]))]
    ref = [_plano(y) for y, _a in previos]
    suyos = {k: [_plano(a) for a in ags] for k, (_y, ags) in enumerate(previos)}
    antes, bloques = _bloques(nuevos)
    limpios = [b for i, b in enumerate(bloques)
               if not (i + 1 < len(bloques) and _plano(bloques[i + 1][0]).startswith(_plano(b[0]))
                       and len(_plano(bloques[i + 1][0])) > len(_plano(b[0])))]
    ys = [_plano(y) for y, _a in limpios]
    out, i = [], 0

    def repite(i):
        """¿Desde `i` se repite el final de lo que ya se tenía? → cuántos mensajes tuyos (0: no)."""
        n = len(ref)
        for j in range(n):
            largo = n - j
            if ys[i:i + largo] != ref[j:]:
                continue
            if largo > 1 or all(_plano(a) in suyos.get(n - 1, []) for a in limpios[i][1] if _plano(a)):
                return largo
        return 0
    if bloques and not (limpios and repite(0)):
        ya = {p for v in suyos.values() for p in v}
        out += [a for a in antes if _plano(a) not in ya]   # lo del agente arriba de todo: el final de su turno
    while i < len(limpios):
        largo = repite(i)
        if largo:
            ultimo = len(ref) - 1                          # lo del agente bajo el último repetido: solo lo que falte
            nuevo = [a for a in limpios[i + largo - 1][1] if _plano(a) not in suyos.setdefault(ultimo, [])]
            out += nuevo
            suyos[ultimo] += [_plano(a) for a in nuevo]
            i += largo
            continue
        y, ags = limpios[i]
        out += [y] + ags
        ref.append(ys[i])
        suyos[len(ref) - 1] = [_plano(a) for a in ags]
        i += 1
    return out, len(nuevos) - len(out)


def restaurar(respaldo, actual, registro=None):
    """Los eventos de un historial restaurado: el `respaldo` (segmentos) tal cual, más lo que el `actual` (segmentos,
    el dañado) trae después y no está en el respaldo —los segmentos nuevos sin sus ventanas repetidas, y lo que creció
    al final de un segmento que ya estaba— y, si ya hay `registro` (eventos de después de migrar), lo que la página
    anexó en él. → (eventos, informe)."""
    bueno = _segmentos(respaldo)
    malo = _segmentos(actual) if actual and os.path.exists(actual) else []
    evs = de_segmentos(bueno, "restaurado")
    conocidos = {(s.get("motor"), s.get("desde")): s for s in bueno}
    informe = {"respaldo": sum(len(s["turnos"]) for s in bueno), "despues": 0, "quitados": 0, "pagina": 0}
    hechos = list(bueno)
    for k, s in enumerate(malo):
        previo_bueno = conocidos.get((s.get("motor"), s.get("desde")))
        if previo_bueno is not None:
            extra = s["turnos"][len(previo_bueno["turnos"]):] \
                if s["turnos"][:len(previo_bueno["turnos"])] == previo_bueno["turnos"] else []
            seg = {"motor": s.get("motor"), "desde": s.get("desde"), "turnos": extra}
            if not extra:
                continue
        else:
            previo = next((x for x in reversed(hechos) if x.get("motor") == s.get("motor")), {"turnos": []})
            sin_hora = all(not t.get("ts") for t in s["turnos"])
            turnos, quitados = sin_ventanas(previo["turnos"], s["turnos"]) if sin_hora else (s["turnos"], 0)
            informe["quitados"] += quitados
            seg = {"motor": s.get("motor"), "desde": s.get("desde"), "turnos": turnos}
            hechos.append(seg)
        informe["despues"] += len(seg["turnos"])
        evs += de_segmentos([seg], "restaurado", prefijo="r%d" % k)
    for e in registro or []:
        if not e.get("importado") and e.get("tipo") not in ("migrado", "restaurado"):
            evs.append(e)
            informe["pagina"] += e.get("rol") != "sistema"
    ahora = time.time()
    n = sum(e["rol"] != "sistema" for e in evs)
    evs.insert(0, {"id": _id("rest-", respaldo, n, ahora), "rol": "sistema", "tipo": "restaurado", "texto": "",
                   "motor": "", "t": ahora, "ts": _iso(ahora), "n": n})
    return evs, informe


def restaurar_en(carpeta, respaldo, nombre="navegador"):
    """Restaura el historial de la carpeta `carpeta` (…/STATE/sessions/<socio>/historial) desde `respaldo`. Antes de
    escribir respalda lo que haya (el registro y el historial de antes). → informe."""
    import atomico
    import olock
    ruta = os.path.join(carpeta, nombre + ".eventos.jsonl")
    viejo = os.path.join(carpeta, nombre + ".json")
    with _LOCK, olock.local_lock(ruta, timeout=10):
        registro = leer(ruta)
        evs, informe = restaurar(respaldo, viejo, registro)
        informe["copias"] = [c for c in (_respaldar(ruta, "antes-de-restaurar"), _respaldar(viejo, "antes-de-restaurar"))
                             if c]
        atomico.escribir(ruta, _linea(evs))
        _CACHE.pop(ruta, None)
        informe["total"] = total(ruta)
    return informe


def _main(argv):
    import argparse
    p = argparse.ArgumentParser(prog="historial_eventos")
    sub = p.add_subparsers(dest="cmd")
    r = sub.add_parser("restaurar", help="rehace un historial dañado desde su respaldo")
    r.add_argument("--respaldo", required=True, help="el navegador.json bueno")
    r.add_argument("--historial", required=True, help="la carpeta STATE/sessions/<socio>/historial del agente")
    r.add_argument("--probar", action="store_true", help="solo dice qué haría, sin escribir")
    a = p.parse_args(argv)
    if a.cmd != "restaurar":
        p.print_help()
        return 2
    if a.probar:
        ruta = os.path.join(a.historial, "navegador.eventos.jsonl")
        evs, informe = restaurar(a.respaldo, os.path.join(a.historial, "navegador.json"), leer(ruta))
        informe["total"] = len(evs)
    else:
        informe = restaurar_en(a.historial, a.respaldo)
    print(json.dumps(informe, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
