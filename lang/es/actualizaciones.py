"""WORKSPACE · lang/es/actualizaciones — ACTUALIZACIONES (actualizaciones_tui) — revisar/reparar/actualizar (FUENTE ES).

Los literales ESPAÑOL tal cual (byte-idénticos a lo que el código mostraba
hardcodeado). Su traducción vive en `lang/en/actualizaciones.py`. Ver
`lang/README.md`.

Nota de frontera: los títulos de las FASES del doctor y sus hallazgos
(label/detail/action) nacen en `doctor.py` (el motor, compartido con el camino
clásico de terminal), fuera del alcance de esta pantalla → se interpolan en
español ({fase} en varias claves). Igual que el mini-panel TONO del `dia`: es
una frontera de módulo, no un olvido.
"""

STRINGS = {
    # ── acciones (menú): label · tag · descripción (3 líneas) ───────────────
    "actualizaciones.act.check.label": "revisar",
    "actualizaciones.act.check.tag": "solo lectura",
    "actualizaciones.act.check.d1": "Diagnóstico completo del harness: motores, cerebros registrados, hooks, launchers y prerequisitos.",
    "actualizaciones.act.check.d2": "NO escribe ni cambia nada — ves cada fase correr en vivo y al final la tabla de salud.",
    "actualizaciones.act.check.d3": "También consulta si hay actualización disponible.",
    "actualizaciones.act.repair.label": "revisar y reparar",
    "actualizaciones.act.repair.tag": "arregla lo roto",
    "actualizaciones.act.repair.d1": "Las mismas fases del diagnóstico, pero REPARANDO lo que encuentre: hooks stale, launchers, tema, settings.",
    "actualizaciones.act.repair.d2": "Idempotente: correrlo dos veces no rompe nada.",
    "actualizaciones.act.repair.d3": "Al final te dice si hay actualización para traer.",
    "actualizaciones.act.update.label": "actualizar todo",
    "actualizaciones.act.update.tag": "recomendado",
    "actualizaciones.act.update.d1": "Trae lo nuevo del harness Y de cada cerebro registrado (cada repo en su rama actual) y repara al final.",
    "actualizaciones.act.update.d2": "Seguro: repo sucio / sin red → avisa y sigue con los demás.",
    "actualizaciones.act.update.d3": "Al final: resumen de qué llegó y qué quedó pendiente.",

    # ── letra chica (cómo funciona) ─────────────────────────────────────────
    "actualizaciones.fine.1": "nada se borra: solo verifica, recablea o trae commits",
    "actualizaciones.fine.2": "puedes correrlo cuando quieras — es idempotente",
    "actualizaciones.fine.3": "cada paso se ve en vivo; al final, resumen y pendientes",

    # ── subtítulos (encabezado de pantalla) ─────────────────────────────────
    "actualizaciones.sub.menu": "actualizaciones — revisar · reparar · actualizar",
    "actualizaciones.sub.run": "actualizaciones — {label} · en curso",
    "actualizaciones.sub.done": "actualizaciones — {label} · resultado",

    # ── títulos de caja ─────────────────────────────────────────────────────
    "actualizaciones.box.left": "ACTUALIZACIONES",
    "actualizaciones.box.what": "QUÉ HACE · {label}",
    "actualizaciones.box.steps": "PASOS · {label}",
    "actualizaciones.box.live": "EN VIVO",
    "actualizaciones.box.summary": "RESUMEN · {label}",
    "actualizaciones.box.pending_n": "PENDIENTES · {n}",
    "actualizaciones.box.pending": "PENDIENTES",

    # ── encabezados de sección (divisores) ──────────────────────────────────
    "actualizaciones.sec.state": "estado",
    "actualizaciones.sec.on_confirm": "al confirmar",
    "actualizaciones.sec.how": "cómo funciona",
    "actualizaciones.sec.progress": "progreso",
    "actualizaciones.sec.latest": "lo último",
    "actualizaciones.sec.arrived": "qué llegó",
    "actualizaciones.sec.update": "actualización",
    "actualizaciones.sec.next": "siguiente",

    # ── hints (acción de cada tecla) ────────────────────────────────────────
    "actualizaciones.hint.action": "acción",
    "actualizaciones.hint.run": "ejecuta",
    "actualizaciones.hint.direct": "directo",
    "actualizaciones.hint.auto": "automáticas sí/aviso/no",
    "actualizaciones.auto.line": "actualizaciones {mode} · a cambia",
    "actualizaciones.msg.auto_set": "listo: actualizaciones {mode}",
    "actualizaciones.msg.auto_env": "WORKSPACE_NO_AUTOUPDATE=1 está puesto en tu terminal y manda: quítalo para elegir aquí",
    "actualizaciones.msg.auto_fail": "no pude guardar el ajuste ({err})",
    "actualizaciones.hint.back_menu": "vuelve",
    "actualizaciones.hint.cancel_run": "cancela al terminar el paso en curso",
    "actualizaciones.hint.scroll_pending": "desplaza pendientes",
    "actualizaciones.hint.enter_q": "Enter o q",

    # ── detalle del menú (al confirmar) ─────────────────────────────────────
    "actualizaciones.detail.runs_here": "corre aquí mismo — verás cada paso en vivo",
    "actualizaciones.detail.equiv": "equivale en terminal: ",

    # ── chequeo de actualización (línea de estado del menú) ─────────────────
    "actualizaciones.chk.searching": "buscando actualizaciones…",
    "actualizaciones.chk.new": "↓ {n} nueva{s} — «actualizar todo» las trae",
    "actualizaciones.chk.uptodate": "✓ al día con origin",
    "actualizaciones.chk.branch": "(rama {branch})",
    "actualizaciones.chk.unverified": "sin verificar: {reason}",

    # ── versión ─────────────────────────────────────────────────────────────
    "actualizaciones.ver.unavailable": "versión no disponible",

    # ── vista EN VIVO ───────────────────────────────────────────────────────
    "actualizaciones.live.preparing": "preparando…",
    "actualizaciones.live.starting": "arrancando…",
    "actualizaciones.run.steps_auto": "los pasos corren solos",
    "actualizaciones.steps.before": "↑ {n} paso(s) anteriores",
    "actualizaciones.steps.after": "↓ {n} paso(s) más",

    # ── pasos del plan (labels) ─────────────────────────────────────────────
    "actualizaciones.step.fetch": "traer {label}",
    "actualizaciones.step.check_update": "buscar actualización",
    "actualizaciones.repo.brain": "cerebro {name}",

    # ── aviso worktree ──────────────────────────────────────────────────────
    "actualizaciones.aviso.worktree": "WORKSPACE es un git worktree — reparación desactivada (solo diagnóstico)",

    # ── notas de paso (badge corto) ─────────────────────────────────────────
    "actualizaciones.note.fixed": "{n} reparada{s}",
    "actualizaciones.note.uptodate": "al día",
    "actualizaciones.note.sync": "local",
    "actualizaciones.note.offline": "sin red",

    # ── fase: live ──────────────────────────────────────────────────────────
    "actualizaciones.live.phase_ok": "{fase}: todo bien ({n} chequeos)",
    "actualizaciones.live.step_error": "error interno del paso: {name}: {msg}",

    # ── pull de un repo (resultado por repo) ────────────────────────────────
    "actualizaciones.pull.sync": "carpeta local (no se actualiza por git)",
    "actualizaciones.pull.brain_unresolved": "cerebro no resuelto — repáralo con «revisar y reparar»",
    "actualizaciones.pull.not_git": "no es repo git (instalación por sync) — sin auto-update",
    "actualizaciones.pull.no_remote": "sin remote configurado — nada que jalar",
    "actualizaciones.pull.dirty": "cambios locales sin commitear — no jalo encima; commitea/guarda y reintenta",
    "actualizaciones.pull.no_tracking": "la rama '{branch}' no rastrea a origin",
    "actualizaciones.pull.offline": "sin conexión con origin — se queda como está",
    "actualizaciones.pull.divergent": "historia divergente — resuélvelo a mano (git pull --ff-only)",
    "actualizaciones.pull.failed": "el pull falló",
    "actualizaciones.pull.updated": "actualizado: +{n} commit(s) → {new} (rama {branch})",
    "actualizaciones.pull.uptodate": "ya al día (rama {branch})",

    # ── chequeo final (revisar/reparar) ─────────────────────────────────────
    "actualizaciones.chk.available": "hay versión nueva — «actualizar» la trae",
    "actualizaciones.chk.harness_uptodate": "harness al día con origin (rama {branch})",
    "actualizaciones.chk.cannot_verify": "no pude verificar updates ({reason})",

    # ── razones de «sin update» (interpoladas como {reason}) ────────────────
    "actualizaciones.reason.not_git": "no es repo git (instalación por sync)",
    "actualizaciones.reason.no_remote": "sin remote configurado",
    "actualizaciones.reason.branch_undeterminable": "rama no determinable",
    "actualizaciones.reason.offline": "sin conexión con origin",
    "actualizaciones.reason.no_data": "sin dato",

    # ── veredicto (resultado) ───────────────────────────────────────────────
    "actualizaciones.verdict.error": "✗ algo tronó: {err}",
    "actualizaciones.verdict.cancelled": "— cancelado; lo corrido quedó aplicado",
    "actualizaciones.verdict.fails": "✗ {n} punto(s) requieren acción",
    "actualizaciones.verdict.warns": "⚠ {n} aviso(s) — nada roto, revísalos cuando puedas",
    "actualizaciones.verdict.ok": "✓ todo en orden",

    # ── resumen ─────────────────────────────────────────────────────────────
    "actualizaciones.sum.fixed_word": "reparados",
    "actualizaciones.sum.duration": "duró {dur} · {n} pasos",
    "actualizaciones.sum.ws_new": "llegaron {n} cambios",
    "actualizaciones.sum.more": "… y {n} más",
    "actualizaciones.sum.nothing_new": "nada nuevo",
    "actualizaciones.sum.available": "↓ hay versión nueva — en el menú: «actualizar»",
    "actualizaciones.sum.uptodate": "✓ al día",
    "actualizaciones.sum.cannot_verify": "no se pudo verificar ({reason})",
    "actualizaciones.sum.next_pending": "cada pendiente (derecha) trae su acción sugerida; para reparar lo automático corre `workspace doctor` en la terminal",
    "actualizaciones.sum.next_clear": "nada que hacer — sigue trabajando",

    # ── panel de pendientes ─────────────────────────────────────────────────
    "actualizaciones.pend.error_cmd": "corre `workspace doctor` en la terminal",
    "actualizaciones.pend.none": "✓ ninguno — todo verde",
    "actualizaciones.pend.more": "… ↓ {n} línea(s) más",

    # ── mensajes de transición (pie) ────────────────────────────────────────
    "actualizaciones.msg.cancelling": "cancelando — el paso en curso termina solo…",
    "actualizaciones.msg.done_pending": "{label} terminado — {n} pendiente(s) anotados",
    "actualizaciones.msg.done_ok": "{label} terminado ✓",
    "actualizaciones.msg.done_fallback": "listo",

    # ── submenú de respaldo (cuando actualizaciones_tui no está disponible) ───
    "actualizaciones.fallback.header": "Actualizaciones",
    "actualizaciones.fallback.q": "— ¿qué quieres hacer?",
    "actualizaciones.fallback.o1": "Revisar nomás",
    "actualizaciones.fallback.o1d": "— diagnóstico, no toca nada",
    "actualizaciones.fallback.o2": "Revisar y reparar",
    "actualizaciones.fallback.o2d": "— arregla hooks, launchers, tema…",
    "actualizaciones.fallback.o3": "Actualizar todo",
    "actualizaciones.fallback.o3d": "— trae lo nuevo + repara (recomendado)",
    "actualizaciones.fallback.back": "Volver",
    "actualizaciones.fallback.prompt": "Opción [1]:",
    # ── actualizador con red de seguridad (updater.py) ──
    "actualizaciones.pull.updated_version": "actualizado a v{v} (+{n} cambio(s))",
    "actualizaciones.pull.rolled_back": "la versión nueva no arrancó aquí: volví a la anterior (no tienes que hacer nada)",
    "actualizaciones.pull.held": "versión fijada: la última no arrancó aquí y aún no hay una más nueva",
    "actualizaciones.note.new_version": "versión nueva",
    "actualizaciones.live.new_doctor_ok": "revisión con la versión nueva: todo en orden",
    "actualizaciones.live.new_doctor_warn": "la versión nueva encontró pendientes: corre `workspace doctor` para verlos",
    "actualizaciones.pull.paused_manual": "volviste a la versión anterior: la nueva queda en pausa hasta una más reciente",

    # ── rediseño 2026-10-14: la cajita (menú, en curso, resultado, `i`) ─────
    "actualizaciones.o.update": "actualizar",
    "actualizaciones.o.update_to": "actualizar a v{v}",
    "actualizaciones.o.repair": "revisar y reparar",
    "actualizaciones.o.check": "solo revisar",
    "actualizaciones.o.rollback": "volver a v{v}",
    "actualizaciones.o.rollback_confirm": "Enter otra vez vuelve a v{v} · nada se borra",
    "actualizaciones.o.recheck": "buscar de nuevo",
    "actualizaciones.o.auto": "automáticas",
    "actualizaciones.auto.v.auto": "sí",
    "actualizaciones.auto.v.notify": "solo avisar",
    "actualizaciones.auto.v.off": "no",
    "actualizaciones.f.version": "versión",
    "actualizaciones.f.state": "estado",
    "actualizaciones.st.searching": "buscando…",
    "actualizaciones.st.new": "hay versión nueva",
    "actualizaciones.st.new_v": "hay versión nueva: v{v}",
    "actualizaciones.st.uptodate": "✓ al día",
    "actualizaciones.st.unverified": "sin verificar · {reason}",
    "actualizaciones.st.held": "la nueva quedó en pausa (volviste a la anterior)",
    "actualizaciones.k.pick": "elige",
    "actualizaciones.k.apply": "aplica",
    "actualizaciones.k.info": "cómo funciona",
    "actualizaciones.k.back": "vuelve",
    "actualizaciones.k.scroll": "desplaza",
    "actualizaciones.k.confirm": "confirma",
    "actualizaciones.k.cancel": "cancela",
    "actualizaciones.box.running": "{label} · EN CURSO",
    "actualizaciones.box.result": "{label} · RESULTADO",
    "actualizaciones.sec.pending": "pendientes",
    "actualizaciones.sec.pending_n": "pendientes · {n}",
    "actualizaciones.msg.rollback_ok": "listo: quedó la v{v} · al salir, Workspace se reabre con ella",
    "actualizaciones.msg.rollback_fail": "no pude volver: {reason}",
    "actualizaciones.msg.rollback_cancel": "cancelado · nada cambió",
    "actualizaciones.info.title": "CÓMO FUNCIONAN LAS ACTUALIZACIONES",
    "actualizaciones.info.detail": "detalle",
    "actualizaciones.info.h_now": "tu versión",
    "actualizaciones.info.h_how": "cómo llega una versión nueva",
    "actualizaciones.info.n1": "trae lo nuevo",
    "actualizaciones.info.c1": "solo avanza; no toca lo que cambiaste",
    "actualizaciones.info.n2": "prueba que arranca",
    "actualizaciones.info.c2": "aquí, en tu máquina",
    "actualizaciones.info.n3": "aplica los ajustes",
    "actualizaciones.info.c3": "con respaldo",
    "actualizaciones.info.p1": "Si la versión nueva no arranca en tu máquina, Workspace vuelve solo a la que tenías y la deja fija hasta que publiquemos una más nueva: nunca te quedas sin poder usarlo.",
    "actualizaciones.info.p2": "Lo que cambia es el programa. Tus agentes, sus cerebros y tus ajustes no se tocan; si una versión necesita ajustar algo, lo hace con respaldo y queda anotado.",
    "actualizaciones.info.h_opts": "las opciones",
    "actualizaciones.info.o_update": "trae la versión nueva y luego revisa y repara; aparece solo cuando hay una",
    "actualizaciones.info.o_repair": "revisa lo esencial (agentes, hooks, comandos, motor) y arregla lo roto; puedes correrlo cuando quieras",
    "actualizaciones.info.o_check": "lo mismo, sin cambiar nada: solo te dice qué encontró",
    "actualizaciones.info.k_rollback": "volver",
    "actualizaciones.info.o_rollback": "regresa a la versión que tenías antes de la última actualización y la deja fija; aparece solo si hay a cuál",
    "actualizaciones.info.o_auto": "sí: se actualiza sola al abrir un agente, con la red de seguridad · solo avisar: te dice que hay versión nueva · no: solo cuando tú lo pidas",
    "actualizaciones.info.h_cmds": "lo mismo desde la terminal",
    "actualizaciones.info.c_update": "actualizar",
    "actualizaciones.info.c_repair": "revisar y reparar",
    "actualizaciones.info.c_check": "solo revisar",
    "actualizaciones.info.c_rollback": "volver a la anterior",
}
