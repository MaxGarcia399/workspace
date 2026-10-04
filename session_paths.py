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


def mismatch_candidates(brain):
    """Para el doctor: carpetas en ~/.claude/projects/ con sesiones reales que
    parecen corresponder a ESTE cerebro pero con OTRA codificación (p. ej.
    abspath sin resolver symlinks, o una ruta vieja). Si esto devuelve algo y la
    carpeta calculada no existe, el resume está roto en esta máquina.

    Devuelve [] si la carpeta calculada ya existe (todo bien) o si no hay
    candidatos (cerebro sin sesiones aún)."""
    expected = session_dir(brain)
    if os.path.isdir(expected):
        return []
    projects = os.path.dirname(expected)
    expected_name = os.path.basename(expected)
    # codificaciones alternativas conocidas + sufijo por nombre de carpeta
    alt = {encode_path(os.path.abspath(os.path.expanduser(brain))),
           encode_path(brain)}
    base = encode_path(os.path.basename(os.path.normpath(brain)))
    found = []
    try:
        for d in sorted(os.listdir(projects)):
            full = os.path.join(projects, d)
            if d == expected_name or not os.path.isdir(full):
                continue
            if (d in alt or (base and d.endswith("-" + base))) and _has_sessions(full):
                found.append(full)
    except Exception:
        pass
    return found
