#!/usr/bin/env python3
"""WORKSPACE · memoria_buscar — buscar en la memoria de un agente (MCP núcleo · memoria_buscar).

Sobre memory_index: el mismo índice SQLite FTS5 DERIVADO, por máquina y fuera del cerebro
(`<estado>/index/<cerebro>.db`), con tres fuentes y las ideas de MemPalace traducidas a lo nuestro:

  · notas: cada nota de las pestañas (su ficha y su archivo) es una fila con su tipo (decisión, pendiente, hecho,
    nota, dato, preferencia: el «pasillo»), su fecha, su motor y su pestaña (el «cuarto»), para poder filtrar;
  · archivo: lo demás curado que ya indexa memory_index (wiki, memoria-archivo, log-archive, inbox consumido);
  · conversaciones (M2-a): los turnos LITERALES, tu mensaje y la respuesta final del agente, del registro de
    eventos de los 9 motores (arquitectura/registro.py, que ya vive por máquina). Sin herramientas (el registro no
    guarda sus argumentos) y con los renglones que parecen llave tapados (secret_scan). No viaja por Obsidian: lo de
    la PC no aparece en la Mac.

Ranking: BM25 (memory_index) + recencia (+ importancia en lo curado); lo invalidado (`reemplazado_por:`) no sale.
Pocos resultados y cortos (fragmento, de dónde salió y su fecha), para no gastar tokens.

Todo es derivado: cada fuente se rehace sola cuando la suya es más nueva (las conversaciones, de a poco: el
registro solo crece) y `rehacer` lo rehace desde cero. Falla-suave: sin índice o con un error, [] (el agente cae a
buscar en archivos). Stdlib + SQLite FTS5 (Mac, Linux y Windows).

CLI:
    python3 memoria_buscar.py --brain "/ruta/CEREBRO" --rehacer
    python3 memoria_buscar.py --brain "/ruta/CEREBRO" "qué decidimos del gateway" [--tipo decision] [--fuente conversaciones]
"""
import json
import os
import re
import sqlite3
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)

import memory_index as MI  # noqa: E402

TIPOS = ("decision", "pendiente", "hecho", "nota", "dato", "preferencia")
FUENTES = ("todo", "notas", "conversaciones")
TOP = 5
TOP_MAX = 8
FRAGMENTO = 220                  # caracteres por resultado
TOPE_TURNO = 4000                # de tu mensaje y de la respuesta, lo que se indexa
OCULTO = "[renglón oculto: parecía una llave]"
_FECHA = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_ARCHIVO_DE = re.compile(r"^(?P<slug>.+?)-\d{4}-\d{2}(?:-\d{2})?$")


# ── el esquema (en el .db de memory_index; su tabla docs no se toca) ─────────
def _conectar(brain):
    con = MI._connect(MI.db_path(brain))
    con.row_factory = sqlite3.Row
    con.executescript(
        "CREATE TABLE IF NOT EXISTS mb_meta(k TEXT PRIMARY KEY, v TEXT);\n"
        "CREATE VIRTUAL TABLE IF NOT EXISTS mb_notas USING fts5(texto, tipo UNINDEXED, fecha UNINDEXED,"
        " hora UNINDEXED, motor UNINDEXED, pestana UNINDEXED, path UNINDEXED, nid UNINDEXED,"
        " tokenize='unicode61 remove_diacritics 2');\n"
        "CREATE VIRTUAL TABLE IF NOT EXISTS mb_turnos USING fts5(yo, agente, fecha UNINDEXED, motor UNINDEXED,"
        " pestana UNINDEXED, via UNINDEXED, tokenize='unicode61 remove_diacritics 2');\n"
        "CREATE TABLE IF NOT EXISTS mb_fuente(archivo TEXT PRIMARY KEY, pos INTEGER, pend TEXT);")
    return con


def _meta(con, k, v=None):
    if v is None:
        r = con.execute("SELECT v FROM mb_meta WHERE k=?", (k,)).fetchone()
        return r["v"] if r else None
    con.execute("INSERT OR REPLACE INTO mb_meta(k,v) VALUES (?,?)", (k, str(v)))


def _rel(brain, path):
    """La ruta dentro del cerebro, con «/» (también en Windows: «C:\\…\\STATE\\x.md» → «STATE/x.md»)."""
    try:
        return os.path.relpath(path, brain).replace("\\", "/")
    except ValueError:                                     # otra unidad en Windows
        return str(path).replace("\\", "/")


# ── notas: cada nota de las pestañas, una fila ──────────────────────────────
def _archivos_de_notas(brain):
    """[(ruta, slug de su pestaña)]: la ficha de cada pestaña (STATE/sessions/<socio>/<slug>.md) y su archivo
    (…/archivo/<slug>-AAAA-MM.md)."""
    base = os.path.join(brain, "STATE", "sessions")
    out = []
    try:
        socios = sorted(os.listdir(base))
    except OSError:
        return out
    for soc in socios:
        d = os.path.join(base, soc)
        if not os.path.isdir(d) or soc in MI.NUNCA:
            continue
        for fn in sorted(os.listdir(d)):
            if fn.endswith(".md") and not fn.upper().startswith("README"):
                out.append((os.path.join(d, fn), fn[:-3]))
        arch = os.path.join(d, "archivo")
        if os.path.isdir(arch):
            for fn in sorted(os.listdir(arch)):
                if fn.endswith(".md"):
                    m = _ARCHIVO_DE.match(fn[:-3])
                    out.append((os.path.join(arch, fn), m.group("slug") if m else fn[:-3]))
    return out


def _notas_de(texto):
    """Las notas de un archivo de pestaña (las de Workspace: «- fecha hora · motor · tipo: texto»). Las de
    «## Vigente» no: son una vista de las del historial."""
    import memoria
    out, en_vigente = [], False
    for ln in (texto or "").split("\n"):
        if ln.startswith("## "):
            en_vigente = ln[3:].strip().lower() == "vigente"
            continue
        if en_vigente or not ln.startswith("- "):
            continue
        m = memoria._NOTA.match(ln)
        if m:
            out.append({"fecha": m.group("fecha"), "hora": m.group("hora") or "", "motor": m.group("motor"),
                        "tipo": memoria._DESDE_ETIQUETA[m.group("etq")], "id": m.group("id") or "",
                        "texto": m.group("texto").strip()})
    return out


def _huella_notas(brain):
    archivos = _archivos_de_notas(brain)
    mt = 0
    for p, _s in archivos:
        try:
            mt = max(mt, os.path.getmtime(p))
        except OSError:
            continue
    return "%d:%d" % (len(archivos), int(mt))


def _rehacer_notas(brain, con):
    con.execute("DELETE FROM mb_notas")
    filas = []
    for p, slug in _archivos_de_notas(brain):
        try:
            with open(p, encoding="utf-8", errors="replace") as fh:
                texto = fh.read()
        except OSError:
            continue
        rel = _rel(brain, p)
        for n in _notas_de(texto):
            filas.append((n["texto"], n["tipo"], n["fecha"], n["hora"], n["motor"], slug, rel, n["id"]))
    con.executemany("INSERT INTO mb_notas(texto,tipo,fecha,hora,motor,pestana,path,nid) VALUES (?,?,?,?,?,?,?,?)",
                    filas)
    _meta(con, "notas", _huella_notas(brain))
    return len(filas)


# ── conversaciones: los turnos literales del registro de eventos ────────────
def _sin_secretos(texto):
    """Cada renglón que parece una llave se tapa (secret_scan, el mismo de siempre)."""
    try:
        import secret_scan
    except Exception:
        return texto
    out = []
    for ln in str(texto or "").split("\n"):
        try:
            hay = bool(ln.strip()) and bool(secret_scan.scan_text(ln))
        except Exception:
            hay = False
        out.append(OCULTO if hay else ln)
    return "\n".join(out)


def _es_tuyo(prompt):
    """Lo que no es un mensaje tuyo aunque llegue como tal: el arranque que Workspace le manda al motor."""
    import memoria
    t = str(prompt or "").lstrip()
    return bool(t) and not t.startswith(tuple(memoria._ARRANQUES) + (memoria._SEMILLA,))


def _local(ts):
    """«2026-11-18T06:44:07.151Z» (UTC, el del registro) → «2026-11-18 00:44» en la hora de esta máquina (la
    de las notas)."""
    import datetime as dt
    try:
        d = dt.datetime.strptime(str(ts)[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=dt.timezone.utc)
        return d.astimezone().strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(ts or "")[:16].replace("T", " ")


def _turnos_de(eventos, pend):
    """(filas, pend): de los eventos de una pestaña, tu mensaje (user_prompt) con la respuesta final que le sigue
    (turn_end). `pend`: el mensaje que todavía no tenía respuesta en la lectura anterior."""
    filas = []
    for e in eventos:
        d = e.get("datos") or {}
        if e.get("momento") == "user_prompt":
            p = d.get("prompt")
            pend = {"yo": p, "ts": e.get("ts") or "", "motor": e.get("motor") or "",
                    "via": d.get("via") or "terminal"} if _es_tuyo(p) else None
        elif e.get("momento") == "turn_end" and pend:
            resp = str(d.get("last_assistant_message") or "")
            filas.append((_sin_secretos(pend["yo"])[:TOPE_TURNO], _sin_secretos(resp)[:TOPE_TURNO],
                          _local(pend["ts"] or e.get("ts") or ""),
                          pend["motor"] or e.get("motor") or "", pend["via"]))
            pend = None
    return filas, pend


def _refrescar_turnos(brain, con, desde_cero=False):
    """Lee lo nuevo de cada registro (solo crecen: desde donde quedó la vez anterior). → filas nuevas."""
    from arquitectura import registro
    carpeta = registro.carpeta(brain)
    if desde_cero:
        con.execute("DELETE FROM mb_turnos")
        con.execute("DELETE FROM mb_fuente")
    try:
        nombres = sorted(f for f in os.listdir(carpeta) if f.endswith(".jsonl"))
    except OSError:
        return 0
    n = 0
    for f in nombres:
        pestana = f[:-6]
        r = con.execute("SELECT pos, pend FROM mb_fuente WHERE archivo=?", (f,)).fetchone()
        pos, pend = (int(r["pos"]), json.loads(r["pend"]) if r["pend"] else None) if r else (0, None)
        try:
            if os.path.getsize(os.path.join(carpeta, f)) < pos:      # se rehízo el registro: desde el principio
                pos, pend = 0, None
                con.execute("DELETE FROM mb_turnos WHERE pestana=?", (pestana,))
        except OSError:
            continue
        eventos, fin = registro.leer(brain, pestana, pos)
        filas, pend = _turnos_de(eventos, pend)
        con.executemany("INSERT INTO mb_turnos(yo,agente,fecha,motor,pestana,via) VALUES (?,?,?,?,?,?)",
                        [(y, a, fe, m, pestana, v) for y, a, fe, m, v in filas])
        con.execute("INSERT OR REPLACE INTO mb_fuente(archivo,pos,pend) VALUES (?,?,?)",
                    (f, fin, json.dumps(pend, ensure_ascii=False) if pend else ""))
        n += len(filas)
    return n


# ── mantener el índice al día ───────────────────────────────────────────────
def refrescar(brain, desde_cero=False):
    """Pone al día las tres fuentes (lo que cambió); `desde_cero` lo rehace todo. Falla-suave: False si no pudo."""
    brain = os.path.expanduser(str(brain))
    if not os.path.isdir(brain):
        return False
    try:
        if desde_cero or MI.is_stale(brain):
            MI.reindex(brain, out=lambda *a: None)
        con = _conectar(brain)
        try:
            if desde_cero or _meta(con, "notas") != _huella_notas(brain):
                _rehacer_notas(brain, con)
            _refrescar_turnos(brain, con, desde_cero)
            con.commit()
        finally:
            con.close()
        return True
    except Exception:
        return False


def rehacer(brain):
    return refrescar(brain, desde_cero=True)


# ── buscar ──────────────────────────────────────────────────────────────────
def _epoch(fecha):
    try:
        return time.mktime(time.strptime(str(fecha)[:10], "%Y-%m-%d"))
    except (TypeError, ValueError):
        return 0


def _corto(texto, tope=FRAGMENTO):
    t = " ".join(str(texto or "").split())
    return t if len(t) <= tope else t[:tope - 1] + "…"


def _en_fechas(fecha, desde, hasta):
    f = str(fecha or "")[:10]
    if (desde or hasta) and not _FECHA.match(f):
        return False
    return not ((desde and f < desde) or (hasta and f > hasta))


def _pestanas_de(brain, pestana):
    """Las claves con que una pestaña aparece en el índice: su nombre y, en el registro de eventos, el número de su
    ventana (sessions_registry). Falla-suave: solo su nombre."""
    claves = {pestana}
    try:
        import sessions_registry as sr
        for bt in sr._pestanas(brain, archivadas=True):
            if pestana in (bt.get("slug"), bt.get("name"), bt.get("workspace")):
                claves |= {x for x in (bt.get("slug"), bt.get("name"), bt.get("workspace")) if x}
    except Exception:
        pass
    return claves


def _nombre_pestana(brain, clave, cache):
    """El nombre de la pestaña de una conversación (su registro va por el número de su ventana)."""
    if clave not in cache:
        cache[clave] = clave
        try:
            import sessions_registry as sr
            for bt in sr._pestanas(brain, archivadas=True):
                if clave in (bt.get("workspace"), bt.get("slug")):
                    cache[clave] = bt.get("slug") or clave
                    break
        except Exception:
            pass
    return cache[clave]


def buscar(brain, consulta, tipo=None, pestana=None, desde=None, hasta=None, fuente="todo", top=TOP):
    """→ [{fuente, fragmento, de, fecha, tipo, motor, pestana, score}], de lo más útil a lo menos. `tipo` (de nota)
    deja solo notas; `fuente` = todo | notas (lo curado: notas y archivo) | conversaciones (lo literal)."""
    brain = os.path.expanduser(str(brain))
    match = MI._fts_query(consulta)
    if not match:
        return []
    top = max(1, min(int(top or TOP), TOP_MAX))
    refrescar(brain)
    claves = _pestanas_de(brain, pestana) if pestana else None
    out = []
    try:
        con = _conectar(brain)
    except Exception:
        return []
    try:
        if fuente in ("todo", "notas"):
            for r in con.execute("SELECT texto,tipo,fecha,hora,motor,pestana,path,nid, bm25(mb_notas) AS rank"
                                 " FROM mb_notas WHERE mb_notas MATCH ? ORDER BY rank LIMIT ?",
                                 (match, top * 8)):
                if (tipo and r["tipo"] != tipo) or (claves and r["pestana"] not in claves) \
                        or not _en_fechas(r["fecha"], desde, hasta):
                    continue
                out.append({"fuente": "nota", "tipo": r["tipo"], "fecha": (r["fecha"] + " " + r["hora"]).strip(),
                            "motor": r["motor"], "pestana": r["pestana"], "de": r["path"], "id": r["nid"],
                            "fragmento": _corto(r["texto"]),
                            "score": -float(r["rank"]) + MI._recency_boost(_epoch(r["fecha"]))})
        if fuente in ("todo", "notas") and not tipo and not pestana:
            for d in MI.query(brain, consulta, top=top * 3):
                if d["category"] in ("sesion", "sesion-archivo"):
                    continue                                  # sus notas ya salen una por una
                fecha = d.get("fecha") or ""
                if not _en_fechas(fecha, desde, hasta):
                    continue
                out.append({"fuente": "archivo", "tipo": "", "fecha": fecha, "motor": "", "pestana": "",
                            "de": _rel(brain, d["path"]), "id": "", "fragmento": _corto(d["snippet"]),
                            "score": float(d["score"])})
        if fuente in ("todo", "conversaciones") and not tipo:
            nombres = {}
            for r in con.execute("SELECT yo,agente,fecha,motor,pestana,via, bm25(mb_turnos) AS rank"
                                 " FROM mb_turnos WHERE mb_turnos MATCH ? ORDER BY rank LIMIT ?",
                                 (match, top * 8)):
                if (claves and r["pestana"] not in claves) or not _en_fechas(r["fecha"], desde, hasta):
                    continue
                out.append({"fuente": "conversacion", "tipo": "", "fecha": r["fecha"], "motor": r["motor"],
                            "pestana": _nombre_pestana(brain, r["pestana"], nombres), "de": "", "id": "",
                            "fragmento": "tú: «%s» · agente: «%s»" % (_corto(r["yo"], 90), _corto(r["agente"], 110)),
                            "score": -float(r["rank"]) + MI._recency_boost(_epoch(r["fecha"]))})
    except Exception:
        return []
    finally:
        con.close()
    out.sort(key=lambda x: x["score"], reverse=True)
    return out[:top]


ETIQUETA = {"decision": "decisión", "pendiente": "pendiente", "hecho": "hecho", "nota": "nota", "dato": "dato",
            "preferencia": "preferencia"}


def como_texto(resultados, consulta, agente=""):
    """Para el agente: pocas líneas, cada una con su fragmento, de dónde salió y su fecha."""
    if not resultados:
        return ("Nada en la memoria%s con «%s». Si es algo del pasado, dilo así; no lo inventes."
                % ((" de " + agente) if agente else "", _corto(consulta, 80)))
    out = ["%d resultado%s para «%s»%s:" % (len(resultados), "" if len(resultados) == 1 else "s",
                                            _corto(consulta, 80), (" (memoria de %s)" % agente) if agente else "")]
    for i, r in enumerate(resultados, 1):
        partes = [ETIQUETA.get(r["tipo"], "nota") + ((" " + r["id"]) if r["id"] else "") if r["fuente"] == "nota"
                  else ("conversación" if r["fuente"] == "conversacion" else "archivo")]
        partes += [x for x in (r["fecha"], r["motor"], ("pestaña " + r["pestana"]) if r["pestana"] else "") if x]
        out.append("%d. [%s] %s" % (i, " · ".join(partes), r["fragmento"]))
        if r["de"]:
            out.append("   de: " + r["de"])
    out.append("Si necesitas el detalle, lee el archivo del resultado (el fragmento es un recorte).")
    return "\n".join(out)


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="memoria_buscar.py")
    ap.add_argument("consulta", nargs="?", default="")
    ap.add_argument("--brain", default=os.getcwd())
    ap.add_argument("--tipo", choices=TIPOS)
    ap.add_argument("--pestana")
    ap.add_argument("--desde")
    ap.add_argument("--hasta")
    ap.add_argument("--fuente", choices=FUENTES, default="todo")
    ap.add_argument("--max", type=int, default=TOP)
    ap.add_argument("--rehacer", action="store_true", help="rehacer el índice desde cero")
    a = ap.parse_args(argv)
    if a.rehacer:
        print("índice rehecho" if rehacer(a.brain) else "no pude rehacer el índice")
    if a.consulta:
        print(como_texto(buscar(a.brain, a.consulta, a.tipo, a.pestana, a.desde, a.hasta, a.fuente, a.max),
                         a.consulta))
    if not (a.rehacer or a.consulta):
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
