#!/usr/bin/env python3
"""WORKSPACE · memory_index — índice FTS5 DERIVADO de la memoria de un cerebro (E3).

Robo battle-tested (Hermes session_search / OpenClaw): un SQLite FTS5 que cubre
la COLA LARGA que el INDEX.md (E2, 100 líneas) no lista. Es la pata de retrieval
de la Etapa 3 de la arquitectura de memoria (diseño interno del equipo).

Principios (no negociables — son lo que hace que NO rompa git-sync ni multi-máquina):
  · DERIVADO: el .db vive FUERA del cerebro, en ~/.claude/workspace/index/<enc>.db
    (per-máquina, gitignored). Jamás es fuente de verdad → se puede borrar y
    regenerar. Cada máquina indexa los MISMOS .md sincronizados → consistencia
    eventual gratis.
  · Indexa conocimiento curado/archival: destilados, wiki, memoria-archivo,
    log-archive, inbox consumido. NO indexa transcripts crudos (LP-5: ruido).
  · Ranking = BM25 × recencia × importancia (frontmatter de triage, si existe).
    Excluye lo invalidado (`reemplazado_por:` no nulo) salvo --historico.
  · Falla-suave SIEMPRE: archivo podrido → se salta; sin .db → el caller cae al
    read-path de E2 (INDEX.md + grep). Jamás rompe el arranque de un agente.

CLI:
    python3 memory_index.py --brain "/ruta/CEREBRO" --reindex
    python3 memory_index.py --brain "/ruta/CEREBRO" --query "elasticidad casa alonso"
    python3 memory_index.py --brain "/ruta/CEREBRO" --query "…" --top 5 --json
    python3 memory_index.py --brain "/ruta/CEREBRO" --status
"""
import os
import re
import sqlite3
import sys
import time

# session_paths vive en la raíz de WORKSPACE (misma carpeta que este módulo).
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session_paths  # noqa: E402

# ── constantes ──────────────────────────────────────────────────────────────
SCHEMA_VERSION = 1
DEFAULT_TOP = 5
SNIPPET_TOKENS = 14
# Pesos del re-ranking (sobre el bm25 base). Calibrables; conservadores por
# ahora — el bm25 manda, recencia/importancia desempatan.
W_RECENCY = 0.6          # boost máximo por documento fresco
W_IMPORTANCIA = 0.8      # boost máximo por importancia=100
RECENCY_HALFLIFE_DAYS = 120.0   # a los 120 días el boost de recencia cae a la mitad

# Qué se indexa: (subruta relativa al cerebro, glob recursivo, categoría).
# Solo conocimiento curado/archival — NUNCA transcripts crudos.
SOURCES = [
    ("STATE/sessions",       "destilados/", "destilado"),
    ("wiki",                 "",            "wiki"),
    ("STATE/memoria-archivo", "",           "memoria-archivo"),
    ("STATE/log-archive",    "",            "log-archive"),
    ("STATE/inbox/consumed", "",            "inbox"),
]
MAX_BODY_CHARS = 40_000   # cota por documento (cola de costo del índice)


# ── paths del índice (DERIVADO, fuera del cerebro) ──────────────────────────
def index_root():
    return os.path.join(os.path.expanduser("~"), ".claude", "workspace", "index")


def db_path(brain):
    """~/.claude/workspace/index/<enc>.db — <enc> con la MISMA codificación que
    usa Claude Code para las sesiones (realpath → encode), para que sea estable
    por cerebro en esta máquina."""
    return os.path.join(index_root(), session_paths.encode_path(
        os.path.realpath(os.path.expanduser(brain))) + ".db")


# ── frontmatter de triage (E3 §2.2) — parser mínimo, falla-suave ────────────
_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _parse_frontmatter(text):
    """Devuelve dict con los campos de triage que nos importan. Tolera ausencia
    total (artefactos viejos sin frontmatter → importancia neutra, válidos)."""
    out = {"importancia": None, "valido": True, "fecha": "", "tags": ""}
    m = _FM_RE.match(text or "")
    if not m:
        return out
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k = k.strip().lower()
        v = v.strip().strip('"').strip("'")
        if k == "importancia":
            try:
                out["importancia"] = max(0, min(100, int(v)))
            except ValueError:
                pass
        elif k == "reemplazado_por":
            # invalidado si tiene un valor real (no null/none/vacío)
            if v and v.lower() not in ("null", "none", "~", ""):
                out["valido"] = False
        elif k in ("fecha", "fecha_sesion", "valido_desde"):
            if not out["fecha"]:
                out["fecha"] = v
        elif k == "tags":
            out["tags"] = v.strip("[]")
    return out


def _title_of(text, path):
    """Primer encabezado markdown, o el nombre de archivo."""
    for line in (text or "").splitlines():
        s = line.strip()
        if s.startswith("#"):
            return s.lstrip("#").strip()[:160]
    return os.path.splitext(os.path.basename(path))[0]


def _iter_source_files(brain):
    """Genera (abs_path, categoría) de todo lo indexable. Falla-suave: rutas
    inexistentes se saltan."""
    brain = os.path.expanduser(brain)
    for sub, needle, cat in SOURCES:
        # `sub` usa '/' como separador canónico en SOURCES; lo partimos para que
        # os.path.join arme la ruta con os.sep nativo (en Windows, '\'). Si no,
        # join conserva el '/' interno y os.walk propaga separadores MEZCLADOS.
        base = os.path.join(brain, *sub.split("/"))
        if not os.path.isdir(base):
            continue
        for root, _dirs, files in os.walk(base):
            for fn in files:
                if not fn.endswith(".md"):
                    continue
                if fn.upper().startswith("README"):
                    continue
                p = os.path.join(root, fn)
                if needle and needle not in p.replace(os.sep, "/") + "/":
                    continue
                yield p, cat


# ── construir el índice ─────────────────────────────────────────────────────
def _connect(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("PRAGMA journal_mode=WAL")
    return con


def _create_schema(con):
    con.executescript(
        "DROP TABLE IF EXISTS docs;\n"
        "CREATE VIRTUAL TABLE docs USING fts5("
        " body, title,"
        " path UNINDEXED, category UNINDEXED, mtime UNINDEXED,"
        " importancia UNINDEXED, valido UNINDEXED, fecha UNINDEXED,"
        " tokenize='unicode61 remove_diacritics 2');"
    )


def reindex(brain, out=print):
    """Reconstruye el .db desde cero (es derivado: rebuild total es barato y
    siempre consistente). Devuelve nº de documentos indexados. Falla-suave."""
    brain = os.path.expanduser(brain)
    if not os.path.isdir(brain):
        out("INDEX: ERROR — cerebro inexistente: %s" % brain)
        return 0
    path = db_path(brain)
    n = skipped = 0
    try:
        con = _connect(path)
        _create_schema(con)
        rows = []
        for p, cat in _iter_source_files(brain):
            try:
                with open(p, encoding="utf-8", errors="replace") as fh:
                    text = fh.read()
                fm = _parse_frontmatter(text)
                rows.append((
                    text[:MAX_BODY_CHARS],
                    _title_of(text, p),
                    p, cat, "%d" % int(os.path.getmtime(p)),
                    "" if fm["importancia"] is None else "%d" % fm["importancia"],
                    "1" if fm["valido"] else "0",
                    fm["fecha"],
                ))
                n += 1
            except Exception:
                skipped += 1   # archivo podrido → se salta, no rompe
        con.executemany(
            "INSERT INTO docs(body,title,path,category,mtime,importancia,"
            "valido,fecha) VALUES (?,?,?,?,?,?,?,?)", rows)
        con.commit()
        con.close()
    except Exception as e:
        out("INDEX: ERROR — %s (falla-suave; el read-path cae a E2)" % e)
        return 0
    extra = (" · %d saltado(s)" % skipped) if skipped else ""
    out("INDEX: REINDEX — %s · %d documento(s)%s → %s"
        % (os.path.basename(brain.rstrip("/")), n, extra,
           os.path.relpath(path, os.path.expanduser("~"))))
    return n


# ── consultar ───────────────────────────────────────────────────────────────
def _fts_query(q):
    """Sanitiza la consulta del usuario a una MATCH segura: tokens alfanuméricos
    unidos por OR (recall amplio); evita que comillas/operadores FTS la rompan."""
    toks = re.findall(r"\w+", q or "", re.UNICODE)
    return " OR ".join(toks) if toks else ""


def _recency_boost(mtime):
    if not mtime:
        return 0.0
    age_days = max(0.0, (time.time() - mtime) / 86400.0)
    return W_RECENCY * (0.5 ** (age_days / RECENCY_HALFLIFE_DAYS))


def query(brain, q, top=DEFAULT_TOP, historico=False, out=None):
    """Devuelve lista de dicts {path,title,category,score,snippet,...} rankeada
    por BM25 × recencia × importancia. Falla-suave: sin .db o error → []."""
    path = db_path(brain)
    if not os.path.isfile(path):
        return []
    match = _fts_query(q)
    if not match:
        return []
    try:
        con = sqlite3.connect(path)
        con.row_factory = sqlite3.Row
        where = "docs MATCH ?" + ("" if historico else " AND valido='1'")
        cur = con.execute(
            "SELECT path,title,category,mtime,importancia,valido,fecha,"
            " snippet(docs,0,'[',']','…',%d) AS snip,"
            " bm25(docs) AS rank FROM docs WHERE %s"
            " ORDER BY rank LIMIT ?" % (SNIPPET_TOKENS, where),
            (match, max(top * 4, top)))
        cand = cur.fetchall()
        con.close()
    except Exception:
        return []
    scored = []
    for r in cand:
        try:
            mtime = int(r["mtime"]) if r["mtime"] else 0
        except (TypeError, ValueError):
            mtime = 0
        imp = r["importancia"]
        imp_boost = (W_IMPORTANCIA * (int(imp) / 100.0)) if imp else 0.0
        # bm25 de FTS5: MÁS NEGATIVO = mejor. Lo invertimos a "mayor=mejor".
        base = -float(r["rank"])
        score = base + _recency_boost(mtime) + imp_boost
        scored.append({
            "path": r["path"], "title": r["title"], "category": r["category"],
            "fecha": r["fecha"], "importancia": imp or "", "snippet": r["snip"],
            "score": round(score, 3),
        })
    scored.sort(key=lambda d: d["score"], reverse=True)
    return scored[:top]


def is_stale(brain, grace_sec=0):
    """¿El .db está más viejo que la fuente .md más reciente? Para el check de
    frescura del doctor. True si falta el .db o si alguna fuente es más nueva."""
    path = db_path(brain)
    if not os.path.isfile(path):
        return True
    db_mtime = os.path.getmtime(path)
    for p, _cat in _iter_source_files(brain):
        try:
            if os.path.getmtime(p) > db_mtime + grace_sec:
                return True
        except OSError:
            continue
    return False


def doc_count(brain):
    path = db_path(brain)
    if not os.path.isfile(path):
        return 0
    try:
        con = sqlite3.connect(path)
        n = con.execute("SELECT count(*) FROM docs").fetchone()[0]
        con.close()
        return n
    except Exception:
        return 0


# ── CLI ─────────────────────────────────────────────────────────────────────
def main(argv=None):
    import argparse
    import json
    ap = argparse.ArgumentParser(prog="memory_index.py")
    ap.add_argument("--brain", default=os.getcwd())
    ap.add_argument("--reindex", action="store_true")
    ap.add_argument("--query", default="")
    ap.add_argument("--top", type=int, default=DEFAULT_TOP)
    ap.add_argument("--historico", action="store_true",
                    help="incluir artefactos invalidados (reemplazado_por)")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)
    brain = os.path.expanduser(a.brain)

    if a.reindex:
        reindex(brain)
    if a.status:
        stale = is_stale(brain)
        print("INDEX: STATUS — %s · %d doc(s) · %s%s"
              % (os.path.basename(brain.rstrip("/")), doc_count(brain),
                 "stale (reindexar)" if stale else "fresco",
                 " · " + db_path(brain)))
    if a.query:
        res = query(brain, a.query, top=a.top, historico=a.historico)
        if a.json:
            print(json.dumps(res, ensure_ascii=False, indent=2))
        elif not res:
            print("INDEX: sin resultados (¿reindexaste? ¿.db existe?)")
        else:
            for d in res:
                print("  %.2f · [%s] %s" % (d["score"], d["category"], d["title"]))
                print("        %s" % d["snippet"].replace("\n", " ")[:160])
                print("        → %s" % os.path.relpath(d["path"], brain))
    if not (a.reindex or a.status or a.query):
        ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
