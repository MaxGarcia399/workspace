#!/usr/bin/env python3
"""WORKSPACE · proyectos_migrate — migra el `proyectos.json` monolítico al almacén
per-nodo v2 (proyectos_fsstore). ONE-SHOT, idempotente, con backup. (stdlib 3.9+).

Lee `~/.claude/workspace/proyectos/proyectos.json` (modelo viejo:
`{projects[{nodes[], chat}], selection}`) y materializa, POR PROYECTO→NODO, la
estructura de carpetas v2:

    <pid>/project.json                 ← membresía + orden + meta (D1)
    <pid>/<nid>/node.json              ← topología del nodo (parent, coords, …)
    <pid>/<nid>/resumen.md             ← sembrado desde `notes` del nodo
    <pid>/<nid>/archivos/              ← vacío (trabajo futuro)
    <pid>/<nid>/sesiones/              ← vacío
    <pid>/<root>/sesiones/_migrado/<fecha>.md   ← el `chat[]` viejo del proyecto

SEGURO POR CONTRATO (anti-vibe — mismo espíritu que proyectos_import):
  · `--dry` (DEFAULT): enseña qué haría y NO escribe NADA (ni backup).
  · `--apply`: antes de tocar disco, BACKUP `proyectos.json` → `proyectos.json.bak.<ts>`.
  · JAMÁS borra ni sobrescribe `proyectos.json` (queda intacto como fuente).
  · IDEMPOTENTE: un proyecto cuya carpeta `<pid>/` ya existe se SALTA.
  · FALLA-SUAVE por proyecto: un proyecto roto no aborta la migración del resto.
  · Lee el JSON CRUDO (no vía store.load): el `chat` NO se recorta a CHAT_KEEP,
    para no perder mensajes en la migración.

Uso:
    python3 proyectos_migrate.py            # ENSAYO: qué se migraría (no escribe)
    python3 proyectos_migrate.py --apply    # migra de verdad (con backup)
"""
import json
import os
import sys
from datetime import datetime, timezone

import proyectos_store as store
import proyectos_fsstore as fs


def source_path():
    """El `proyectos.json` viejo. Solo se LEE y se respalda; nunca se borra."""
    return store.store_path()


def load_raw():
    """proyectos.json → dict CRUDO. Falla-suave: ausente/roto → {}.
    Crudo a propósito: store.load() recorta el chat a CHAT_KEEP y aquí no
    queremos perder mensajes."""
    try:
        with open(source_path(), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def backup(path, out=print):
    """Copia `path` → `path.bak.<ts>` ANTES de escribir nada. Devuelve la ruta
    del backup, o None si no había nada que respaldar / falló."""
    if not os.path.isfile(path):
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dst = "%s.bak.%s" % (path, ts)
    try:
        with open(path, "rb") as src, open(dst, "wb") as d:
            d.write(src.read())
        out("  ✓ backup: %s" % os.path.basename(dst))
        return dst
    except OSError as e:
        out("  ⚠ no se pudo respaldar (%s) — ABORTA por seguridad" % e)
        return None


def _chat_to_markdown(name, chat):
    """El `chat[]` monolítico del proyecto → un markdown legible (nada se pierde)."""
    lines = ["# Chat migrado — %s" % name,
             "",
             "> Migrado del `proyectos.json` v1 (hilo único por proyecto). "
             "En v2 los hilos son por (nodo × agente × día).",
             ""]
    for m in chat:
        if not isinstance(m, dict):
            continue
        role = m.get("role", "?")
        agent = m.get("agent") or ""
        ts = m.get("ts") or ""
        head = "**%s**" % role
        if agent:
            head += " · %s" % agent
        if ts:
            head += " · %s" % ts
        lines += [head, "", str(m.get("text", "")), "", "---", ""]
    return "\n".join(lines)


def _migrate_project(raw, out=print):
    """Materializa UN proyecto v1 → carpetas v2. Devuelve (estado, n_nodos):
    estado ∈ {'migrado', 'saltado', 'error'}. Fail-soft: nunca lanza."""
    try:
        pid = raw.get("id")
        name = store._txt(raw.get("name"), store.NAME_MAX, "Proyecto") or "Proyecto"
        if not fs.valid_id(pid):
            out("  ⚠ %-30s id inválido (%r) — se salta" % (name[:30], pid))
            return ("error", 0)
        if os.path.isdir(fs.project_dir(pid)):
            out("  ⊘ %-30s (ya migrado — se salta)" % name[:30])
            return ("saltado", 0)

        # nodos crudos → normalizados; reconciliar árbol (raíz única, parents sanos)
        nodes = [n for n in (store._norm_node(x) for x in (raw.get("nodes") or []))
                 if n is not None and fs.valid_id(n["id"])][:store.NODES_MAX]
        nodes = fs._reconcile_tree(nodes)
        if not nodes:                       # un proyecto sin nodos: fabrica su raíz
            now = store._now()
            nodes = [{"id": fs._new_id(), "t": name, "x": 0.0, "y": 0.0,
                      "st": "todo", "root": True, "p": None, "notes": "",
                      "created": now, "updated": now}]
        root = next(n for n in nodes if n["root"])

        proj = {"id": pid, "name": name,
                "color": store._color(raw.get("color")),
                "created": raw.get("created") or store._now(),
                "updated": raw.get("updated") or store._now(),
                "nodes": nodes}

        # 1) cada nodo: dirs + resumen.md sembrado desde `notes` + node.json
        for n in nodes:
            fs._seed_node_dir(pid, n, resumen=n.get("notes") or "")
        # 2) project.json (membresía+orden) — al final = 'proyecto comprometido'
        fs._write_project_meta(proj)
        # 3) el chat viejo → sesiones/_migrado/<fecha>.md del nodo RAÍZ
        chat = [m for m in (raw.get("chat") or []) if isinstance(m, dict)]
        if chat:
            fecha = store._now()[:10]       # YYYY-MM-DD
            dst = os.path.join(fs.sesiones_dir(pid, root["id"]),
                               "_migrado", "%s.md" % fecha)
            fs.atomic_write_text(dst, _chat_to_markdown(name, chat))
        out("  + %-30s %2d nodo(s)%s"
            % (name[:30], len(nodes), " · %d msg de chat" % len(chat) if chat else ""))
        return ("migrado", len(nodes))
    except Exception as e:                   # fail-soft DURO: un proyecto roto no aborta
        out("  ⚠ error migrando %r: %s" % (raw.get("id"), e))
        return ("error", 0)


def migrate(apply=False, out=print):
    """Migra proyectos.json → almacén v2. Devuelve (n_migrados, n_nodos).
    apply=False (default) = ENSAYO: no escribe nada (ni backup)."""
    raw = load_raw()
    projects = [p for p in (raw.get("projects") or []) if isinstance(p, dict)]
    if not projects:
        out("  (no hay proyectos v1 que migrar)")
        return (0, 0)

    if apply:
        if backup(source_path(), out=out) is None and os.path.isfile(source_path()):
            return (0, 0)                    # backup falló → no seguimos

    n_p = n_n = 0
    for raw_p in projects:
        if not apply:
            # ENSAYO: solo describe (mismo criterio de skip que el apply)
            pid = raw_p.get("id")
            name = store._txt(raw_p.get("name"), store.NAME_MAX, "Proyecto") or "Proyecto"
            if fs.valid_id(pid) and os.path.isdir(fs.project_dir(pid)):
                out("  ⊘ %-30s (ya migrado — se salta)" % name[:30])
                continue
            nn = len([x for x in (raw_p.get("nodes") or []) if isinstance(x, dict)])
            out("  · %-30s %2d nodo(s)" % (name[:30], nn))
            n_p += 1
            n_n += nn
            continue
        estado, nn = _migrate_project(raw_p, out=out)
        if estado == "migrado":
            n_p += 1
            n_n += nn
    return (n_p, n_n)


def main(argv=None):
    argv = list(argv if argv is not None else sys.argv[1:])
    apply = "--apply" in argv
    print("\n  Migrar proyectos.json (v1) → almacén per-nodo (v2)%s\n"
          % ("" if apply else "   (ENSAYO — no escribe nada)"))
    n_p, n_n = migrate(apply=apply)
    print("\n  %s %d proyecto(s) · %d nodo(s)\n"
          % ("✓ migrados:" if apply else "· se migrarían:", n_p, n_n))
    if not apply:
        print("  El proyectos.json viejo NO se toca. Para hacerlo de verdad "
              "(con backup):  python3 proyectos_migrate.py --apply\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
