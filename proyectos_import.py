#!/usr/bin/env python3
"""WORKSPACE · proyectos_import — trae el tablero viejo (threads) al mapa nuevo.

Un solo trabajo: leer `~/.claude/workspace/board/board.json` (la sección «Proyectos»
del dev panel: proyectos con un ÁRBOL recursivo de temas) y materializarlo en
`~/.claude/workspace/proyectos/proyectos.json` (el mapa conceptual: nodos con
`p` = id del padre + coordenadas).

Los dos modelos dicen lo mismo con distinta forma, así que el mapeo es directo:

    board                         proyectos
    ─────                         ─────────
    project.title            →    project.name
    project (raíz)           →    nodo root (t = nombre del proyecto)
    item.title               →    nodo.t          (p = id del nodo padre)
    item.children[] (recur.) →    nodos hijos     (el árbol se arma por `p`)
    item.archived            →    st = "done"     (lo archivado = cerrado)

Lo que el modelo viejo tiene y el nuevo NO (fechas, links, tags, hasSketch) se
conserva en `notes` del nodo — no se tira información en una migración.

LAYOUT: el modelo viejo no tiene coordenadas (era una lista). Se calcula un
árbol RADIAL determinista alrededor de la raíz: cada nivel es un anillo, y los
hermanos se reparten el arco de su padre. Determinista a propósito — reimportar
da el mismo mapa, y el socio mueve los nodos después (eso sí persiste).

SEGURO POR CONTRATO:
  · SOLO LEE board.json. Jamás lo escribe ni lo borra (13 proyectos reales).
  · Reusa proyectos_store para escribir → misma validación, mismo lock, misma
    escritura atómica que la app. Este módulo no toca el JSON a mano.
  · `--dry` (default): enseña qué haría y NO escribe nada.
  · No duplica: un proyecto ya importado (mismo nombre) se SALTA salvo --force.

Uso:
    python3 proyectos_import.py            # ensayo: qué se importaría
    python3 proyectos_import.py --apply    # importa de verdad
    python3 proyectos_import.py --apply --force   # reimporta (duplica nombres)
"""
import itertools
import json
import math
import os
import sys

import proyectos_store as store

#: tamaño REAL de un nodo (CSS: max-width 190px, ~46px de alto) + aire. La
#: geometría de abajo lo usa para GARANTIZAR que los nodos quepan en su anillo.
NODE_W = 205.0
NODE_H = 62.0
#: primer anillo y separación mínima entre anillos. OJO: debe superar el ANCHO
#: (no el alto) del nodo. Dos nodos de anillos vecinos al MISMO ángulo quedan
#: separados solo radialmente; si ese salto es < NODE_W, sobre el eje horizontal
#: (donde el salto es todo dx y dy≈0) las cajas se solapan. Con salto ≥ NODE_W+ε
#: no hay ángulo en que ambas condiciones (|dx|<W y |dy|<H) se cumplan.
RING_0 = 260.0
RING_MIN = NODE_W + 30.0
#: escalón radial entre hermanos par/impar: los separa en RADIO para que
#: puedan estar más juntos en ÁNGULO sin tocarse (mapa ~mitad de grande).
STAGGER = NODE_H + 34.0
#: NO se le pone tope al radio: un tope CANCELA la garantía de que quepan (el
#: nodo más apretado del anillo manda) y los nodos se vuelven a encimar — que es
#: justo el bug que esto arregla. Un mapa grande no es problema: el fit() del
#: front lo encuadra y el socio hace zoom.


def board_path():
    """El tablero viejo. Solo lectura — esta ruta jamás se escribe aquí."""
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace",
                        "board", "board.json")


def load_board():
    """board.json → dict. Falla-suave: si no existe o está roto → vacío."""
    try:
        with open(board_path(), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _kids(item):
    """Hijos de un item del board (el modelo usa `children`; toleramos `items`)."""
    for key in ("children", "items"):
        v = item.get(key)
        if isinstance(v, list):
            return v
    return []


def _notes_of(item):
    """Lo que el modelo viejo tenía y el nuevo no: se preserva como notas.
    Nada de la migración se tira en silencio."""
    bits = []
    if item.get("notes"):
        bits.append(str(item["notes"]))
    if item.get("date"):
        bits.append("fecha: %s" % item["date"])
    if item.get("tag"):
        bits.append("tag: %s" % item["tag"])
    links = item.get("links")
    if isinstance(links, list) and links:
        bits.append("links: " + ", ".join(str(x) for x in links[:8]))
    if item.get("hasSketch"):
        bits.append("(tenía sketch en el tablero viejo)")
    return "\n".join(bits)[:store.NOTES_MAX]


def _flatten(project):
    """El árbol del board → lista plana [(item, id_padre_o_None, nivel)],
    en orden de recorrido. `None` de padre = cuelga de la raíz del proyecto."""
    out = []

    def walk(items, parent_key, depth):
        for i, it in enumerate(items or []):
            if not isinstance(it, dict):
                continue
            key = (parent_key, i)                    # id posicional estable
            out.append((it, parent_key, depth, key))
            walk(_kids(it), key, depth + 1)

    walk(_kids(project), None, 0)
    return out


def _radial(flat):
    """Coordenadas de un árbol radial determinista alrededor de (0,0).

    Dos reglas hacen que NO se encimen, y las dos importan:

    1. **El arco se reparte por PESO, no en partes iguales.** Cada rama recibe
       una tajada proporcional a sus HOJAS. Repartir igual (lo ingenuo) le daba
       a una rama de 15 hijos el mismo espacio que a una de 2 → las grandes se
       apilaban unas sobre otras. Con peso, cada rama recibe el espacio que su
       tamaño pide.
    2. **El radio del anillo se CALCULA para que quepan.** Un nodo de ancho
       NODE_W dentro de un arco de `w` radianes necesita radio ≥ NODE_W/w (la
       longitud de arco R·w debe cubrir el nodo). El anillo toma el radio del
       nodo más apretado de su nivel → nadie se solapa con su hermano. Y cada
       anillo va al menos RING_MIN más afuera que el anterior → ningún nivel
       pisa al siguiente.

    Determinista: reimportar da el MISMO mapa, así el `--dry` no miente. El
    socio mueve los nodos después y ESO sí se guarda."""
    kids = {}
    for it, parent, depth, key in flat:
        kids.setdefault(parent, []).append(key)

    def leaves(k):
        """Hojas del subárbol = su peso. Sin recursión profunda: iterativo."""
        stack, n = [k], 0
        while stack:
            cur = stack.pop()
            ch = kids.get(cur, [])
            if not ch:
                n += 1
            else:
                stack.extend(ch)
        return max(1, n)

    by_depth = {}
    for it, parent, depth, key in flat:
        by_depth.setdefault(depth, []).append(key)

    # ── 1) wedges por peso: (centro, apertura) ─────────────────────────────
    wedge = {None: (0.0, 2 * math.pi)}
    for d in sorted(by_depth):
        # agrupar los de este nivel por su padre para repartir SU arco
        groups = {}
        for it, parent, depth, key in flat:
            if depth == d:
                groups.setdefault(parent, []).append(key)
        for parent, group in groups.items():
            c, w = wedge.get(parent, (0.0, 2 * math.pi))
            total = sum(leaves(k) for k in group) or 1
            a = c - w / 2.0
            for k in group:
                span = w * (leaves(k) / total)
                wedge[k] = (a + span / 2.0, span)
                a += span

    # ── 2) radio por anillo: el nodo más apretado manda, con ESCALONADO ────
    # Sin escalonar, un nivel angosto exige radio = NODE_W/wedge y el mapa se
    # vuelve gigante y vacío (42 nodos ⇒ 2800px, ilegible). Escalonando los
    # hermanos en DOS radios (par/impar), dos vecinos angulares ya no compiten
    # por el mismo arco: basta la MITAD de arco por nodo → la mitad de radio.
    # Mismo aire visual, mapa la mitad de grande.
    radius, prev = {}, 0.0
    for d in sorted(by_depth):
        need = max((NODE_W / 2.0) / max(wedge[k][1], 1e-6) for k in by_depth[d])
        base = RING_0 if d == 0 else prev + RING_MIN
        radius[d] = max(base, need)          # la geometría manda: sin tope
        prev = radius[d] + STAGGER           # el escalón cuenta para el siguiente

    # ── 3) plantar (escalonando hermanos par/impar) ────────────────────────
    orden = {}                                   # índice del nodo entre sus hermanos
    for parent, group in kids.items():
        for i, k in enumerate(group):
            orden[k] = i
    pos = {None: (0.0, 0.0)}
    for it, parent, depth, key in flat:
        ang, _ = wedge[key]
        r = radius[depth] + (STAGGER if orden.get(key, 0) % 2 else 0.0)
        pos[key] = (round(math.cos(ang) * r, 1), round(math.sin(ang) * r, 1))

    # ── 4) relajación: separar los pares que aún se tocan ──────────────────
    # Los pasos 1-3 garantizan hermanos-en-anillo y anillos-vecinos, pero NO
    # pares ARBITRARIOS: dos nodos de ramas distintas pueden coincidir casi a la
    # misma altura y solaparse igual. Esta pasada los empuja por el eje más
    # barato hasta que nadie se toca. Determinista (orden fijo, sin azar) y
    # barata (n² con n≤cientos). La raíz no se mueve: es el centro del mapa.
    keys = [k for _, _, _, k in flat]
    for _ in range(80):
        movido = False
        for a, b in itertools.combinations(keys, 2):
            ax, ay = pos[a]
            bx, by = pos[b]
            ox = NODE_W - abs(bx - ax)          # cuánto se solapan en x
            oy = NODE_H - abs(by - ay)          # y en y
            if ox <= 0 or oy <= 0:
                continue                        # no se tocan
            if ox / NODE_W <= oy / NODE_H:      # separar por donde cueste menos
                d = (ox / 2.0 + 1.0) * (1.0 if bx >= ax else -1.0)
                pos[a] = (ax - d, ay)
                pos[b] = (bx + d, by)
            else:
                d = (oy / 2.0 + 1.0) * (1.0 if by >= ay else -1.0)
                pos[a] = (ax, ay - d)
                pos[b] = (bx, by + d)
            movido = True
        if not movido:
            break
    return {k: (round(v[0], 1), round(v[1], 1)) for k, v in pos.items()}


def plan(board, existing_names):
    """Qué se importaría: [{name, nodes, skip}] — sin escribir nada."""
    out = []
    for p in board.get("projects", []):
        if not isinstance(p, dict) or p.get("archived"):
            continue
        name = (p.get("title") or "Proyecto").strip()[:store.NAME_MAX]
        out.append({"name": name,
                    "nodes": len(_flatten(p)),
                    "skip": name in existing_names})
    return out


def import_board(apply=False, force=False, out=print):
    """Importa board.json → proyectos.json. Devuelve (n_proyectos, n_nodos).
    `apply=False` (default) = ENSAYO: no escribe nada."""
    board = load_board()
    projects = [p for p in board.get("projects", [])
                if isinstance(p, dict) and not p.get("archived")]
    if not projects:
        out("  (el tablero viejo está vacío — nada que importar)")
        return (0, 0)

    cur = store.load()
    existing = {str(p.get("name", "")) for p in cur.get("projects", [])}
    palette = store.COLORS

    n_p = n_n = 0
    for idx, p in enumerate(projects):
        name = (p.get("title") or "Proyecto").strip()[:store.NAME_MAX]
        if name in existing and not force:
            out("  ⊘ %-42s (ya importado — se salta)" % name[:42])
            continue
        flat = _flatten(p)
        pos = _radial(flat)
        out("  %s %-42s %2d nodo(s)" % ("+" if apply else "·", name[:42], len(flat)))
        n_p += 1
        n_n += len(flat)
        if not apply:
            continue

        # 1) el proyecto (la API le pone su nodo raíz sola, con el nombre)
        res = store.api_add_project({"name": name,
                                     "color": palette[idx % len(palette)]})
        if not res.get("ok"):
            out("    ⚠ no se pudo crear: %s" % res.get("error"))
            continue
        proj = res["project"]
        pid = proj["id"]
        root = next((n for n in proj.get("nodes", []) if n.get("root")), None)
        root_id = root["id"] if root else None
        # las notas del proyecto viejo viven en su raíz (no se tiran)
        notes_p = _notes_of(p)
        if root_id and notes_p:
            store.api_update_node({"project_id": pid, "node_id": root_id,
                                   "notes": notes_p})

        # 2) los items del árbol, en orden (el padre SIEMPRE existe antes)
        idmap = {None: root_id}
        for it, parent, depth, key in flat:
            x, y = pos[key]
            r = store.api_add_node({
                "project_id": pid, "parent_id": idmap.get(parent, root_id),
                "t": (it.get("title") or "sin título")[:store.TITLE_MAX],
                "x": x, "y": y})
            if not r.get("ok"):
                continue
            nid = r["node"]["id"]
            idmap[key] = nid
            notes = _notes_of(it)
            st = "done" if it.get("archived") else "todo"
            if notes or st != "todo":
                store.api_update_node({"project_id": pid, "node_id": nid,
                                       "notes": notes, "st": st})
    return (n_p, n_n)


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    apply = "--apply" in argv
    force = "--force" in argv
    print("\n  Importar tablero viejo → mapa de Proyectos%s\n"
          % ("" if apply else "   (ENSAYO — no escribe nada)"))
    n_p, n_n = import_board(apply=apply, force=force)
    print("\n  %s %d proyecto(s) · %d nodo(s)\n"
          % ("✓ importados:" if apply else "· se importarían:", n_p, n_n))
    if not apply:
        print("  Para hacerlo de verdad:  python3 proyectos_import.py --apply\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
