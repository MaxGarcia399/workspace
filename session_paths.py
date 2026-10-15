#!/usr/bin/env python3
"""WORKSPACE · session_paths — ÚNICA fuente de verdad de la carpeta de sesiones.

Claude Code guarda cada sesión en  ~/.claude/projects/<encoded-cwd>/<id>.jsonl
donde <encoded-cwd> es el cwd del proyecto con CADA carácter no-alfanumérico
reemplazado por "-"  (re.sub(r'[^a-zA-Z0-9]', '-', cwd)).

⚠ Claude Code resuelve symlinks (realpath) ANTES de codificar. Por eso aquí se
usa os.path.realpath y NO os.path.abspath: en una máquina donde el cerebro vive
detrás de un symlink (p. ej. un Desktop sincronizado), abspath produce otra
carpeta y el `--resume` falla en silencio (arranca sesión nueva).

Esta fórmula vivía duplicada en engines/claude_code.py, dashboard.py y los
dashboards de zenith/atlas. NO la dupliques de nuevo — si Claude Code cambia el
encoding, se corrige en UN solo lugar. Stdlib puro (Python 3.9+), Mac y Windows.
"""
import json
import os
import re


def encode_path(path):
    """Codificación de Claude Code: cada char no-alfanumérico → '-'."""
    return re.sub(r"[^a-zA-Z0-9]", "-", path)


def session_dir(brain):
    """Carpeta donde Claude Code guarda las sesiones de un cerebro.

    Resuelve symlinks con realpath — igual que Claude Code — antes de codificar.
    """
    real = os.path.realpath(os.path.expanduser(brain))
    return os.path.join(os.path.expanduser("~"), ".claude", "projects",
                        encode_path(real))


def session_file(brain, session_id):
    """Ruta del .jsonl de una sesión concreta (existe ⇒ `claude --resume` sirve)."""
    return os.path.join(session_dir(brain), f"{session_id}.jsonl")


def _has_sessions(d):
    try:
        return any(x.endswith(".jsonl") for x in os.listdir(d))
    except Exception:
        return False


def _recorded_cwd_is(d, brain, max_files=5, max_lines=20):
    """True si alguna sesión de `d` registró como cwd la MISMA carpeta que
    `brain` (Claude Code escribe "cwd" en las líneas del .jsonl). Es la prueba
    de que una carpeta con otra codificación es de este cerebro y no de otra
    carpeta que solo se llama igual."""
    try:
        target = os.path.realpath(os.path.expanduser(brain))
        files = sorted(x for x in os.listdir(d) if x.endswith(".jsonl"))[:max_files]
    except Exception:
        return False
    for fn in files:
        try:
            with open(os.path.join(d, fn), encoding="utf-8", errors="replace") as fh:
                for i, line in enumerate(fh):
                    if i >= max_lines:
                        break
                    m = re.search(r'"cwd"\s*:\s*"((?:[^"\\]|\\.)*)"', line)
                    if not m:
                        continue
                    try:
                        cwd = json.loads('"%s"' % m.group(1))
                    except Exception:
                        continue
                    if os.path.exists(cwd) and os.path.realpath(cwd) == target:
                        return True
        except Exception:
            continue
    return False


def mismatch_candidates(brain):
    """Para el doctor: carpetas en ~/.claude/projects/ con sesiones reales que
    corresponden a ESTE cerebro pero con OTRA codificación (p. ej. abspath sin
    resolver symlinks). Si esto devuelve algo y la carpeta calculada no existe,
    el resume está roto en esta máquina.

    Dos vías: (1) las codificaciones alternativas conocidas de la PROPIA ruta
    del cerebro (abspath / tal cual); (2) una carpeta cuyo nombre termina en el
    nombre del cerebro SOLO si sus sesiones registraron como cwd esta misma
    carpeta. Antes (2) bastaba con el sufijo: cualquier otra carpeta con el
    mismo nombre (otra instalación, otro proyecto) daba un falso "resume no
    funcionará".

    Devuelve [] si la carpeta calculada ya existe (todo bien) o si no hay
    candidatos (cerebro sin sesiones aún)."""
    expected = session_dir(brain)
    if os.path.isdir(expected):
        return []
    projects = os.path.dirname(expected)
    expected_name = os.path.basename(expected)
    alt = {encode_path(os.path.abspath(os.path.expanduser(brain))),
           encode_path(brain)}
    base = encode_path(os.path.basename(os.path.normpath(brain)))
    found = []
    try:
        for d in sorted(os.listdir(projects)):
            full = os.path.join(projects, d)
            if d == expected_name or not os.path.isdir(full):
                continue
            if not _has_sessions(full):
                continue
            if d in alt or (base and d.endswith("-" + base)
                            and _recorded_cwd_is(full, brain)):
                found.append(full)
    except Exception:
        pass
    return found
