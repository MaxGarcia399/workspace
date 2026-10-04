#!/usr/bin/env python3
"""WORKSPACE · dash.centro — BACKEND del Centro de Control (funcionalidad, sin front).

Paquete de LÓGICA pura (stdlib 3.9+, cero dependencias) que el front del Centro
consumirá después. Diseño fuente: research/design/centro-control/ARQUITECTURA.md
(rama feat/centro-control-proto). Tres piezas:

    tareas.py   — taskboard.json: misiones con las 3 fases (plan→exec→review)
                  y su MÁQUINA DE TRANSICIÓN (protocolo duro en UN solo lugar).
                  Storage per-máquina, atómico, falla-suave (patrón board.py).
    estado.py   — snapshot AGREGADO read-only del estado vivo de cada agente:
                  energía/contexto/reset (usage.json) · tarea actual (now.json)
                  · turno (heartbeat) · worktrees (worktree-owners) · inbox
                  (messages) · misiones (taskboard). Falla-suave POR FUENTE.
    delegar.py  — delegación estructurada: encargo YAML-plano por el bus
                  (messages.send) atado a una misión del taskboard (msg_ids).
    cli.py      — `workspace centro <sub>`: lectura + mutación segura, --json
                  estable (agent-first, token-eficiente).

Superficie HTTP: dash/dev/centro.py (adapter fino auto-descubierto) monta los
endpoints /api/dev/centro/* detrás del guard Y1 existente. ⚠ N3 PENDIENTE
(DECISIONES.md §1): dónde vive el Centro al final (superficie propia con puerto
propio vs sección del dashboard) lo decidel socio/el front — este paquete es
agnóstico: la lógica no sabe de HTTP y el adapter se re-monta donde sea.

Este paquete NO es una sección del dashboard general (dash/ solo auto-descubre
dash/*.py, no subpaquetes) — se importa explícito: `from dash.centro import …`.
"""
