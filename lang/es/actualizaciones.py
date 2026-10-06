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
    "actualizaciones.hint.back_menu": "vuelve al menú",
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
    "actualizaciones.note.sync": "sync",
    "actualizaciones.note.offline": "sin red",

    # ── fase: live ──────────────────────────────────────────────────────────
    "actualizaciones.live.phase_ok": "{fase}: todo bien ({n} chequeos)",
    "actualizaciones.live.step_error": "error interno del paso: {name}: {msg}",

    # ── pull de un repo (resultado por repo) ────────────────────────────────
    "actualizaciones.pull.sync": "gestionado por Obsidian Sync (git no aplica)",
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
    "actualizaciones.chk.available": "hay {n} actualización(es) — «actualizar todo» las trae",
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
    "actualizaciones.sum.ws_new": "WORKSPACE: +{n} commit(s) nuevos",
    "actualizaciones.sum.more": "… y {n} más",
    "actualizaciones.sum.nothing_new": "nada nuevo del harness",
    "actualizaciones.sum.available": "↓ {n} disponible(s) — elige «actualizar todo» para traerlas",
    "actualizaciones.sum.uptodate": "✓ al día con origin (rama {branch})",
    "actualizaciones.sum.cannot_verify": "no se pudo verificar ({reason})",
    "actualizaciones.sum.next_pending": "cada pendiente (derecha) trae su acción sugerida; lo manual también se arregla conversando: corre `workspace doctor` en la terminal",
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
}
