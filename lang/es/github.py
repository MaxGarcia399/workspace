"""WORKSPACE · lang/es/github — la sección GitHub (github_tui). FUENTE ES.

Cada cadena es el literal español EXACTO que github_tui mostraba hardcodeado:
sin `ui.lang` el default queda byte-idéntico. La traducción vive en
`lang/en/github.py`. Reusa `common.ago.*` (antigüedad) y `common.hint.pick`
(«elige»). Ver `lang/README.md`."""

STRINGS = {
    # ── cabecera + hints del pie/cabecera ───────────────────────────────────
    "github.subtitle": "github — tus repos: ramas locales + PRs · issues · releases",
    "github.box.repos": "REPOS",
    "github.box.detail": "DETALLE · {name}",
    "github.box.connect": "CONECTAR",
    "github.hint.focus": "foco",
    "github.hint.open": "abre",
    "github.hint.query": "consulta GitHub",
    "github.hint.connect": "conecta",
    "github.hint.disconnect": "desconecta",
    "github.hint.branch": "rama",
    "github.hint.map": "mapa local",
    "github.hint.back": "vuelve",
    "github.hint.type_manual": "para teclear a mano",
    "github.hint.cancel": "cancela",
    "github.hint.write_target": "owner/nombre, URL o carpeta",
    "github.hint.back_selector": "vuelve al selector",
    "github.key.type": "escribe",

    # ── ventana (bordes honestos ↑/↓) ───────────────────────────────────────
    "github.more_up": "↑ {n} más arriba",
    "github.more_down": "↓ {n} más abajo",

    # ── línea de estado (la puerta de la sesión) ────────────────────────────
    "github.state.gh": "gh: {acct}",
    "github.state.session_active": "sesión activa",
    "github.state.repos_one": "{n} repo",
    "github.state.repos_many": "{n} repos",
    "github.state.cloud_hint": "nube solo con f — nada corre solo",
    "github.state.querying": "consultando {repos}…",
    "github.state.no_session": "✗ sin sesión de GitHub",
    "github.state.connect_cta": "conéctate: gh auth login",
    "github.state.local_still": "lo local sigue: m abre el mapa de ramas",
    "github.state.reverify": "r re-verifica",

    # ── filas del listado de repos ──────────────────────────────────────────
    "github.repo.no_github": "{name} (sin github)",
    "github.repo.querying": "consultando…",
    "github.repo.pr_iss": "{pr}PR·{iss}iss",
    "github.repo.only_local": "solo local",
    "github.repo.not_queried": "sin consultar",

    # ── caja REPOS: divisores + guía de primer uso ──────────────────────────
    "github.div.this_harness": "este harness",
    "github.div.connected": "conectados",
    "github.repos.none_yet": "ninguno todavía — es 1 paso:",
    "github.repos.pick_detected": "elige un repo local detectado",
    "github.repos.or_paste": "(o pega owner/nombre · también con click aquí)",

    # ── caja CONECTAR (selector de repos locales) ───────────────────────────
    "github.connect.title": "conectar un repo — elige uno local o escríbelo",
    "github.div.detected": "repos locales detectados",
    "github.connect.scanning": "buscando repos en tu disco… (solo lectura local, cero red)",
    "github.connect.none_found": "no encontré repos git en las carpetas comunes — escríbelo abajo",
    "github.connect.no_origin": "sin origin github",
    "github.connect.already": "ya",
    "github.div.manual": "a mano",
    "github.connect.manual_row": "escribir owner/nombre · URL de github.com · o una carpeta",
    "github.connect.bullet1": "Enter conecta lo elegido — solo se apunta en tu lista per-máquina (github-repos.json)",
    "github.connect.bullet3": "escribe cualquier letra y pasas directo al campo de texto · Esc cancela",

    # ── caja A MANO (campo de texto) ────────────────────────────────────────
    "github.write.title": "conectar un repo de GitHub — a mano",
    "github.write.bullet1": "owner/nombre · URL de github.com · o una carpeta local clonada",
    "github.write.bullet2": "solo se apunta en tu lista per-máquina (~/.claude/workspace/github-repos.json)",
    "github.write.bullet4": "Enter conecta · Esc vuelve al selector",

    # nota compartida por CONECTAR y A MANO (texto idéntico)
    "github.note.no_clone": "no clona, no toca la red, no guarda tokens — la sesión la maneja gh",

    # ── filas del DETALLE (por tipo) ────────────────────────────────────────
    "github.item.draft_suffix": " ·borrador",
    "github.item.here_copy": "aquí está tu copia",
    "github.item.enter_switch": "Enter cambia a esta rama",
    "github.item.protected": "protegida",
    "github.item.draft": "borrador",
    "github.item.published": "publicado",

    # ── caja DETALLE ────────────────────────────────────────────────────────
    "github.det.no_repos": "sin repos",
    "github.det.private": "privado",
    "github.det.public": "público",
    "github.det.querying": "consultando GitHub…",
    "github.det.queried": "consultado {ago} — f refresca",
    "github.det.not_queried_full": "sin consultar — f trae PRs, issues, ramas, commits y releases",
    "github.det.not_queried": "sin consultar",
    "github.det.local_copy": "copia local · {path}",
    "github.det.no_local": "sin copia local — todo se abre en el navegador",
    "github.det.local_branches": "ramas · copia local · {n}",
    "github.det.more_branches": "… y {n} más — m abre el mapa completo",

    "github.div.disconnected": "github desconectado",
    "github.det.off_bullet1": "sin sesión NO se toca la red: cero consultas desde aquí",
    "github.det.off_bullet2": "gh guarda tu sesión en el keyring del sistema — esta pantalla nunca ve tokens",
    "github.det.off_bullet3": "lo local sigue completo: m abre el mapa de ramas y worktrees",

    "github.div.no_github": "sin github",
    "github.det.nogh1": "este repo no tiene origin de github.com — la nube no aplica",
    "github.det.nogh_switch": "Enter o c en una rama de arriba cambia la copia local (árbol limpio)",
    "github.det.nogh2": "m abre su mapa local de ramas y worktrees",

    "github.div.will_see": "qué verás al consultar",
    "github.det.preview1": "PRs abiertos con el estado de sus checks (✓ × ●)",
    "github.det.preview2": "issues abiertos · ramas remotas · commits recientes",
    "github.det.preview3": "releases y corridas de Actions",
    "github.det.preview4": "nada corre solo: f consulta, con tu sesión gh",

    "github.div.prs": "revisiones abiertas · PR",
    "github.div.issues": "issues abiertos",
    "github.div.branches": "ramas remotas",
    "github.div.commits": "commits recientes · {branch}",
    "github.det.default_branch": "default",
    "github.div.releases": "releases",
    "github.div.runs": "actions",
    "github.det.none": "ninguno",
    "github.det.more_open": "… y {n} más — Enter/o abre el repo en el navegador",

    "github.div.failed_queries": "consultas fallidas",

    "github.div.actions": "acciones",
    "github.det.act_enter_branch": "Enter abre lo elegido en tu navegador — y en «ramas · copia local» cambia a esa rama",
    "github.det.act_enter": "Enter abre lo elegido en tu navegador — nunca modifica nada",
    "github.det.act_checkout": "c cambia la copia local a la rama elegida (árbol limpio, jamás --force) · m abre su mapa de ramas",
    "github.det.act_query": "f consulta GitHub otra vez · x desconecta (solo tu lista)",
    "github.det.act_off": "f está apagada sin sesión — gh auth login y r",

    # ── confirmación de x (desconectar) ─────────────────────────────────────
    "github.confirm.disconnect": "⚠ desconectar {slug} — Enter confirma · Esc cancela (solo sale de tu lista; nada se borra)",

    # ── puerta de seguridad: auth_check ─────────────────────────────────────
    "github.auth.no_gh": "GitHub CLI (gh) no está instalado — la nube queda apagada; lo local sigue completo",
    "github.auth.no_session": "sin sesión de GitHub — conéctate: gh auth login (r re-verifica al volver)",

    # ── mensajes de estado (S["msg"]) ───────────────────────────────────────
    "github.msg.cancel_norepo": "cancelado — sin repo no hay conexión",
    "github.msg.not_git": "esa carpeta no es un repositorio git",
    "github.msg.no_origin": "ese repo no tiene origin de github.com — conéctalo con owner/nombre",
    "github.msg.unparsed": "no entendí el repo: usa owner/nombre, una URL de github.com o una carpeta local clonada",
    "github.msg.already_local": "{slug} ya estaba conectado — registré su copia local ✓",
    "github.msg.already": "{slug} ya está conectado",
    "github.msg.write_fail": "no pude escribir github-repos.json — nada cambió",
    "github.msg.connected": "{slug} conectado ✓ — f consulta su estado",
    "github.msg.disconnected": "{slug} desconectado ✓ — solo salió de tu lista; nada se borró",

    "github.msg.query_failed": "consulta fallida",
    "github.msg.bad_response": "respuesta no válida",
    "github.msg.no_response": "sin respuesta",
    "github.msg.query_prefix": "consulta: ",

    "github.msg.queried_ok": "{slug} consultado ✓",
    "github.msg.queried_fail_one": "{slug} consultado — {n} consulta fallida (ver detalle)",
    "github.msg.queried_fail_many": "{slug} consultado — {n} consultas fallidas (ver detalle)",

    "github.msg.cmd_fail": "falló `{cmd}`: {detail}",

    "github.msg.only_github": "solo abro URLs de github.com — esta no lo es",
    "github.msg.opened": "abierto en el navegador ✓ — {url}",
    "github.msg.open_fail": "no pude abrir el navegador: {err}",

    "github.msg.not_branch": "esa fila no es una rama",
    "github.msg.no_local_clone": "sin copia local — Enter la abre en el navegador; clónala para poder cambiarte de rama",
    "github.msg.job_running": "hay un cambio de rama en curso — espera a que termine",
    "github.msg.cant_confirm_clean": "no pude confirmar si el árbol local está limpio — no lo toco",
    "github.msg.dirty_one": "la copia local tiene {n} cambio sin commitear — commit o stash antes de cambiar de rama",
    "github.msg.dirty_many": "la copia local tiene {n} cambios sin commitear — commit o stash antes de cambiar de rama",
    "github.msg.already_on": "la copia local ya está en {branch}",
    "github.msg.now_on": "la copia local ahora está en {branch} ✓",
    "github.msg.switching": "cambiando a {branch}… ({mode} en segundo plano)",

    "github.msg.no_page": "este repo no tiene página de GitHub",

    "github.msg.cancelled": "cancelado",
    "github.msg.nothing_disconnect": "nada que desconectar",
    "github.msg.cancel_kept": "cancelado — el repo sigue en tu lista",
    "github.msg.no_github_map": "este repo no tiene GitHub — m abre su mapa local de ramas",
    "github.msg.no_session_query": "sin sesión de GitHub no consulto nada — corre gh auth login y luego r",
    "github.msg.nothing_to_query": "este repo no tiene GitHub que consultar",
    "github.msg.already_querying": "ya estoy consultando {slug} — un momento",
    "github.msg.querying_bg": "consultando {slug} en segundo plano — la pantalla sigue viva",
    "github.msg.harness_no_disconnect": "el harness no se desconecta — es la base de esta pantalla",
    "github.msg.no_map": "sin copia local no hay mapa — a abre el selector de repos locales (o pega su carpeta)",
    "github.msg.checkout_hint": "c cambia la copia local a una RAMA — elige una en «ramas» (Tab + ↑↓ o click)",
    "github.msg.reloaded_ok": "sesión y lista releídas ✓ — gh: {acct}",
    "github.msg.reloaded_no": "lista releída — sigue sin sesión de GitHub",
    "github.msg.no_session_word": "sin sesión",

    # ── listado sin tty ─────────────────────────────────────────────────────
    "github.list.prefix": "github: {status}",
    "github.list.session": "sesión gh {acct} ✓",
    "github.list.active": "activa",
    "github.list.extra": " · {pr} PR · {iss} issues · {ago}",
}
