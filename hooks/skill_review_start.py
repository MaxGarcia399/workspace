#!/usr/bin/env python3
"""WORKSPACE hook · SessionStart — entrega al agente la revisión de skills
pendiente (si la hay) como parte de su contexto de arranque. La hace el agente
en su sesión, a la vista; nada corre sin ventana. Lógica: skill_review.py."""
import os
import sys

try:   # Windows: UTF-8 en stdout (la tarea lleva acentos y emoji)
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import skill_review  # noqa: E402

if __name__ == "__main__":
    sys.exit(skill_review.start_main())
