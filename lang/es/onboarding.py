"""WORKSPACE · lang/es/onboarding — el primer arranque guiado (onboarding_tui).

Subtítulo, fila de etapas, paso 0 (idioma), bienvenida, y los pasos MOTORES /
APARIENCIA / AGENTE / RESUMEN completos: títulos de caja, divisores, labels,
estados de motor, copy por motor, mensajes y hints del pie por vista. `es` es la
FUENTE: cada cadena es byte-idéntica a la que mostraba el código hardcodeado.
"""

STRINGS = {
    "onboarding.subtitle": "primer arranque — deja tu Workspace listo en 3 pasos",

    # fila de etapas (1 motores ── 2 apariencia ── 3 agente)
    "onboarding.etapa.motores": "motores",
    "onboarding.etapa.apariencia": "apariencia",
    "onboarding.etapa.agente": "agente",

    # divisores compartidos entre pasos
    "onboarding.div.tu_eleccion": "tu elección",
    "onboarding.div.que_cambia": "qué cambia",
    "onboarding.continuar": "✦ continuar",

    # línea de ACCIÓN PRIMARIA (P0-B) — por foco, corta y brillante
    "onboarding.action.idioma": "Enter elige el idioma",
    "onboarding.action.bienvenida": "Enter para empezar",
    "onboarding.action.motores_opt": "espacio marca · Enter continúa",
    "onboarding.action.continuar": "Enter continúa al siguiente paso",
    "onboarding.action.apariencia_opt": "Enter aplica «{lbl}»",
    "onboarding.action.autostart": "Enter elige «{lbl}» · Esc salta",
    "onboarding.action.agente": "Enter abre «{lbl}»",
    "onboarding.action.gcal": "Esc salta · Enter conecta",
    "onboarding.action.gcal_done": "Enter te lleva al resumen",
    "onboarding.action.resumen": "Enter te deja en el recinto",

    # paso 0: idioma
    "onboarding.idioma.divisor": "idioma",
    "onboarding.idioma.heading": "Elige el idioma de Workspace.",
    "onboarding.idioma.body": "Puedes cambiarlo cuando quieras desde el menú "
                              "del recinto («Idioma») o en Config. Las "
                              "pantallas de desarrollo quedan en español.",

    # bienvenida
    "onboarding.welcome.title_l": "QUÉ ES WORKSPACE",
    "onboarding.welcome.title_r": "EL PLAN",
    "onboarding.welcome.p1": "Workspace es un hub local para tus agentes de "
                             "IA: cada agente vive en su propio cerebro (una "
                             "carpeta de archivos tuya) y corre sobre un motor "
                             "CLI que ya tengas instalado — Claude Code, Codex "
                             "o Antigravity.",
    "onboarding.welcome.p2": "Todo pasa en tu máquina: cero dependencias, sin "
                             "cuentas nuevas, y Workspace nunca ve ni guarda "
                             "tus credenciales (el login es de cada CLI).",
    "onboarding.welcome.plan_title": "qué viene ahora",
    "onboarding.welcome.step1_t": "1 motores",
    "onboarding.welcome.step1_d": "detecto qué CLIs tienes y eliges cuáles usar",
    "onboarding.welcome.step2_t": "2 apariencia",
    "onboarding.welcome.step2_d": "tema y fondo del hub — se ven al instante",
    "onboarding.welcome.step3_t": "3 agente",
    "onboarding.welcome.step3_d": "crear uno nuevo, cargar uno existente o "
                                  "buscar en tu disco (y afinar su tono)",
    "onboarding.welcome.transparency_title": "transparencia",
    "onboarding.welcome.transparency_p": "Al final: un resumen de lo elegido y "
                                         "dónde quedó guardado. Puedes saltarte "
                                         "esto con q y repetirlo cuando quieras "
                                         "con `workspace onboarding`.",

    # paso 1: MOTORES
    "onboarding.motores.title_l": "MOTORES DETECTADOS",
    "onboarding.motores.title_r": "EL MOTOR",
    "onboarding.motores.div_listo": "listo",
    "onboarding.motores.marcados": "{n} motor(es) marcados",
    "onboarding.motores.estado": "estado",
    "onboarding.motores.div_honesto": "honesto",
    "onboarding.motores.honesto_p": "El estado de sesión se lee del propio CLI "
                                    "de cada motor; Workspace no guarda ni ve "
                                    "credenciales.",
    "onboarding.motores.default_p": "Los motores marcados son tu set de "
                                    "trabajo. «{motor}» queda como default "
                                    "(modelos.default_engine) para los agentes "
                                    "que no declaren el suyo — cada agente "
                                    "puede fijar otro después.",
    "onboarding.motores.none_p": "Sin ningún motor marcado no se puede lanzar "
                                 "agentes. Puedes continuar igual, instalar un "
                                 "CLI después y repetir esto con "
                                 "`workspace onboarding`.",
    # estado de motor (línea completa)
    "onboarding.motores.st.unavailable": "no disponible en esta instalación",
    "onboarding.motores.st.not_installed": "no instalado — falta {falta} en "
                                           "PATH",
    "onboarding.motores.st.cli": "CLI",
    "onboarding.motores.st.checking": "binario ✓ · checando sesión…",
    "onboarding.motores.st.session_ok": "binario ✓ · sesión activa ✓",
    "onboarding.motores.st.login_needed": "binario ✓ · falta login — {det}",
    "onboarding.motores.st.no_session": "sin sesión",
    # estado compacto (resumen)
    "onboarding.motores.short.not_installed": "no instalado",
    "onboarding.motores.short.binary": "binario ✓",
    "onboarding.motores.short.session": "sesión ✓",
    "onboarding.motores.short.login": "falta login",
    # copy honesto por motor: (qué es · cómo se entra · qué cambia)
    "onboarding.motor.claude-code.what": "Claude Code — el CLI oficial de "
                                         "Anthropic (binario `claude`).",
    "onboarding.motor.claude-code.login": "Entra con tu suscripción: corre "
                                          "`claude` una vez y sigue el login.",
    "onboarding.motor.claude-code.changes": "Es el motor con más integración "
                                            "en Workspace: hooks reales, "
                                            "memoria inyectada al agente y "
                                            "sesiones del harness.",
    "onboarding.motor.codex.what": "Codex — el CLI de OpenAI (binario "
                                   "`codex`), con tu suscripción de ChatGPT.",
    "onboarding.motor.codex.login": "Entra con `codex login` en tu terminal.",
    "onboarding.motor.codex.changes": "Workspace lo envuelve; nunca lee ni "
                                      "toca tu token (~/.codex/).",
    "onboarding.motor.antigravity.what": "Antigravity — el CLI `agy` de Google "
                                         "(Gemini).",
    "onboarding.motor.antigravity.login": "La sesión se abre con tu cuenta "
                                          "Google desde el propio CLI.",
    "onboarding.motor.antigravity.changes": "Workspace lo envuelve igual que a "
                                            "los demás motores.",

    # paso 2: APARIENCIA
    "onboarding.apariencia.title_l": "TEMA Y FONDO",
    "onboarding.apariencia.title_r": "LA APARIENCIA",
    "onboarding.apariencia.group.tema": "tema",
    "onboarding.apariencia.group.fondo": "fondo",
    "onboarding.apariencia.activo": "activo",
    "onboarding.apariencia.div_donde": "dónde queda",
    "onboarding.apariencia.changes_p1": "El tema pinta todo el hub — wordmark, "
                                        "cajas, sliders — y se guarda al "
                                        "instante: esta pantalla YA está "
                                        "pintada con él; eso es la vista "
                                        "previa.",
    "onboarding.apariencia.changes_p2": "El fondo es un eje independiente: "
                                        "cambia solo el color de fondo de la "
                                        "terminal y combina con cualquier "
                                        "tema.",
    "onboarding.apariencia.donde_p": "ui.theme y ui.background en "
                                     "~/.claude/workspace/settings.json. Más "
                                     "opciones (color propio #RRGGBB, "
                                     "animaciones, estrellas) en Config → TEMA.",
    # etiquetas de fondo (el id se queda; traducimos el texto visible)
    "onboarding.fondo.tema": "el del tema activo",
    "onboarding.fondo.negro": "negro puro",
    "onboarding.fondo.grafito": "grafito",
    "onboarding.fondo.azul": "azul noche",
    "onboarding.fondo.verde": "verde bosque",
    "onboarding.fondo.violeta": "violeta",

    # paso 3: AGENTE (las vías vienen de add_agent_tui.MENU_OPTS; el literal es
    # byte-idéntico a esa fuente para que `es` no cambie)
    "onboarding.agente.title_l": "TU PRIMER AGENTE",
    "onboarding.agente.title_r": "EL CAMINO",
    "onboarding.agente.div_que_pasa": "qué pasa",
    "onboarding.agente.div_siguiente": "siguiente paso",
    "onboarding.agente.siguiente_p": "Se abre la pantalla real del hub "
                                     "(«Agregar agente») en ese camino. Si "
                                     "queda un agente nuevo conectado, al "
                                     "volver podrás afinar su TONO; después, el "
                                     "resumen.",
    "onboarding.agente.crear.label": "crear agente nuevo",
    "onboarding.agente.crear.desc": "Un agente desde cero: formulario corto → "
                                    "ves el CEREBRO que va a nacer y el harness "
                                    "con el que corre → se crea EN VIVO, paso "
                                    "por paso. Nace autocontenido en "
                                    "~/Desktop/<NOMBRE> - BRAIN, usable al "
                                    "terminar.",
    "onboarding.agente.cargar.label": "cargar agente existente",
    "onboarding.agente.cargar.desc": "Conecta un cerebro que ya existe (una "
                                     "carpeta): ves QUÉ trae (identidad, marcas "
                                     "de cerebro, colisiones) antes de "
                                     "conectar, y el cableado (hooks · "
                                     "statusline · launcher · tema) corre EN "
                                     "VIVO, paso por paso.",
    "onboarding.agente.descubrir.label": "descubrir cerebros en el disco",
    "onboarding.agente.descubrir.desc": "Escanea Desktop / Documents / vaults "
                                        "buscando carpetas con "
                                        ".workspace/agent.json y te deja "
                                        "conectarlas — ves cuáles son nuevas y "
                                        "cuáles ya están. Acción MANUAL — el "
                                        "harness jamás conecta nada solo.",
    "onboarding.agente.ninguno.label": "terminar sin agente",
    "onboarding.agente.ninguno.desc": "También puedes agregarlo cuando quieras "
                                      "desde el recinto («Agregar agente») — "
                                      "crear, cargar o descubrir siguen ahí, "
                                      "idénticos.",

    # paso NUEVO (opcional): AUTOSTART — ¿abre al abrir la terminal o solo
    # con el comando?
    "onboarding.autostart.title_l": "ARRANQUE",
    "onboarding.autostart.title_r": "CÓMO ABRE",
    "onboarding.autostart.div": "arranque",
    "onboarding.autostart.heading": "¿Cuándo abre Workspace?",
    "onboarding.autostart.opt_on": "al abrir la terminal",
    "onboarding.autostart.opt_off": "solo con el comando workspace",
    "onboarding.autostart.on_p": "Cada terminal nueva abre el menú de "
                                 "Workspace: eliges un agente o sigues con una "
                                 "terminal normal (q). Cómodo para entrar "
                                 "directo al hub.",
    "onboarding.autostart.off_p": "La terminal arranca como siempre; escribes "
                                  "`workspace` cuando quieras el hub. Menos "
                                  "invasivo — ideal si compartes la máquina o "
                                  "corres scripts en ella.",
    "onboarding.autostart.div_donde": "dónde queda",
    "onboarding.autostart.donde_p": "ui.autostart en settings.json + un bloque "
                                    "en ~/.zshrc (o tu $PROFILE de "
                                    "PowerShell). Cambiarlo luego: repite "
                                    "`workspace onboarding` o edita ese bloque.",

    # paso NUEVO (opcional): GOOGLE CALENDAR
    "onboarding.gcal.title_l": "GOOGLE CALENDAR",
    "onboarding.gcal.title_r": "OPCIONAL",
    "onboarding.gcal.div_pasos": "cómo",
    "onboarding.gcal.already": "Ya tienes Google Calendar conectado ✓",
    "onboarding.gcal.step1": "Abre Google Calendar en la web "
                             "(calendar.google.com).",
    "onboarding.gcal.step2": "En el calendario que quieras: Configuración y "
                             "uso compartido.",
    "onboarding.gcal.step3": "Baja a «Integrar calendario».",
    "onboarding.gcal.step4": "Copia la «Dirección secreta en formato iCal» "
                             "(termina en .ics).",
    "onboarding.gcal.step5": "Vuelve aquí y pulsa Enter: la pegas en una línea "
                             "normal.",
    "onboarding.gcal.changes_p": "Workspace LEE tus eventos (solo lectura) y "
                                 "los muestra en el calendario del hub. Nunca "
                                 "escribe en tu agenda.",
    "onboarding.gcal.div_seguro": "seguro",
    "onboarding.gcal.seguro_p": "Solo se guarda esa URL iCal, en tu máquina; "
                                "jamás se imprime en pantalla. Puedes quitarla "
                                "cuando quieras desde el calendario.",
    "onboarding.gcal.prompt_url": "Pega la «Dirección secreta en formato iCal» "
                                  "(Enter vacío = cancelar):",
    "onboarding.gcal.prompt_label": "Etiqueta (opcional, Enter = auto): ",
    "onboarding.gcal.connected": "conectado ✓ · {n} eventos",
    "onboarding.gcal.failed": "no se pudo conectar ({err})",
    "onboarding.gcal.cancelled": "conexión cancelada",
    "onboarding.gcal.unavailable": "Google Calendar no está disponible aquí",

    # paso final: RESUMEN
    "onboarding.resumen.title_l": "LO QUE QUEDÓ",
    "onboarding.resumen.title_r": "DÓNDE Y QUÉ SIGUE",
    "onboarding.resumen.div_motores": "motores",
    "onboarding.resumen.div_apariencia": "apariencia",
    "onboarding.resumen.div_agentes": "agentes",
    "onboarding.resumen.div_donde": "dónde quedó",
    "onboarding.resumen.div_adelante": "de aquí en adelante",
    "onboarding.resumen.default": "default: {engine}",
    "onboarding.resumen.sin_cambio": "sin cambio",
    "onboarding.resumen.ninguno_marcado": "ninguno marcado — instala un CLI y "
                                          "repite con `workspace onboarding`",
    "onboarding.resumen.y_mas": "… y {n} más",
    "onboarding.resumen.sin_agentes": "sin agentes aún — «Agregar agente» en "
                                      "el recinto cuando quieras",
    "onboarding.resumen.tono_ok": "tono ajustado para {agente} ✓",
    "onboarding.resumen.fila_config": "config (tema, fondo, motor)",
    "onboarding.resumen.fila_agentes": "agentes registrados",
    "onboarding.resumen.fila_onboarding": "este onboarding",
    "onboarding.resumen.adelante_p1": "Enter te deja en el recinto: ahí lanzas "
                                      "agentes, entras a Config, Tono y "
                                      "«Agregar agente».",
    "onboarding.resumen.adelante_p2": "Repetir este flujo: "
                                      "`workspace onboarding`.",

    # mensajes efímeros (pie, S["msg"])
    "onboarding.msg.default_saved": "motor default: {motor} · guardado ✓",
    "onboarding.msg.default_fail": "no pude guardar el default ({err}) — sigue "
                                   "igual",
    "onboarding.msg.not_installable": "{eid} no está instalado — no se puede "
                                      "marcar",
    "onboarding.msg.applied": "{tipo} «{lbl}» · guardado ✓",
    "onboarding.msg.apply_fail": "no se pudo aplicar {tipo} ({err})",
    "onboarding.msg.autostart_on": "Workspace abrirá al abrir la terminal · "
                                   "guardado ✓",
    "onboarding.msg.autostart_off": "Workspace abrirá solo con el comando · "
                                    "guardado ✓",
    "onboarding.msg.autostart_saved": "preferencia guardada (ajusta el rc a "
                                      "mano si hace falta)",

    # hints del pie (por vista)
    "onboarding.hints.idioma": "↑↓ idioma · Enter elige · Esc/q salta",
    "onboarding.hints.welcome": "Enter empieza · q al hub (vuelve con "
                                "`workspace onboarding`)",
    "onboarding.hints.motores": "↑↓ motor · espacio marca/quita · Enter "
                                "continúa · Esc atrás · q salta",
    "onboarding.hints.apariencia": "↑↓ opción · Enter/espacio aplica (guarda "
                                   "ya) · Esc atrás · q salta",
    "onboarding.hints.autostart": "↑↓ opción · Enter elige · Esc salta · q "
                                  "sale",
    "onboarding.hints.agente": "↑↓ camino · 1-4 directo · Enter abre · Esc "
                               "atrás · q salta",
    "onboarding.hints.gcal": "Enter conecta · Esc salta · q sale",
    "onboarding.hints.resumen": "Enter — al recinto",
}
