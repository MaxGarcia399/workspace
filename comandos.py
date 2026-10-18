#!/usr/bin/env python3
"""WORKSPACE · comandos — catálogo ÚNICO de los comandos de `workspace`.

Una sola fuente de verdad por comando (lección Omarchy: «el comando trae su
ayuda»). Cada entrada declara su META una vez y de ahí se DERIVA todo lo
demás — nadie vuelve a listar comandos a mano:

  · `workspace --help` (front._usage)          → usage_text()
  · `workspace <comando> --help` (front.main)  → help_text()
  · la sección «Comandos» del hub              → comandos_tui (visible/usage_of)
  · `workspace comandos --json` (para agentes) → as_json()
  · `workspace comandos --markdown` (manual)   → as_markdown()
  · el RUTEO de front.main                     → resolve(): nombre/alias → id
  · el lint `workspace comandos --check`       → check() (y tests/)

Nombres bilingües: cada comando tiene un nombre ES y uno EN (la ayuda muestra
el del idioma activo) y acepta AMBOS más todos los nombres que existieron
antes (alias para siempre: ningún comando que alguien ya escribe deja de
funcionar). `hidden_aliases` también rutean pero JAMÁS se muestran (p. ej.
el nombre viejo del producto en `migrar-legado`).

Solo comandos de PRODUCTO; los de desarrollo del harness viven en
comandos_dev.py con el MISMO formato, que no viaja en la distribución pública
(make-dist lo quita) y solo se muestran en modo dev.

Cero dependencias (stdlib, Python 3.9+). Mac, Linux y Windows.
"""
import legacy  # alias ocultos del nombre anterior (fuente única)

GROUPS = (
    ("agentes", "tus agentes", "your agents"),
    ("dia", "tu día", "your day"),
    ("trabajo", "trabajo", "work"),
    ("maquina", "esta máquina", "this machine"),
)

LANGS = ("es", "en")


# ── idioma ─────────────────────────────────────────────────────────────────

def lang():
    """Idioma activo de la UI ("es" | "en"). Falla-suave → "es"."""
    try:
        import i18n
        code = i18n.lang()
        return code if code in LANGS else "es"
    except Exception:
        return "es"


def _pick(v, lg):
    """Valor por idioma: dict {"es","en"} → el de `lg` (fallback es); str → tal cual."""
    if isinstance(v, dict):
        return v.get(lg) or v.get("es") or ""
    return v or ""


def usage_of(c, lg=None):
    """Cómo se escribe: `workspace <nombre> <args>` en el idioma `lg`."""
    lg = lg or lang()
    if c.get("usage_fixed"):
        return _pick(c["usage_fixed"], lg)
    name = c["names"].get(lg) or c["names"]["es"]
    args = _pick(c.get("args"), lg)
    return ("workspace %s %s" % (name, args)).rstrip()



def cmd(cid, es, en, group, summary_es, summary_en, when_es, when_en,
        args="", aliases=(), hidden_aliases=(), examples=(), usage=None,
        hidden=False, dangerous=False, requires_args=False, dispatch=True,
        runnable=True, dev=False):
    """META de un comando. Campos:

    cid             id estable (ancla de ruteo, mapas y JSON; jamás se renombra)
    es / en         nombre por idioma (ambos rutean; la ayuda muestra el activo)
    group           id de GROUPS (o el grupo dev de comandos_dev)
    summary_*       qué hace — una línea, ES y EN (el lint exige ambas)
    when_*          cuándo te sirve
    args            argumentos tras el nombre: str o {"es":…, "en":…}
    aliases         otros nombres que rutean y SE MUESTRAN («también: …»)
    hidden_aliases  nombres que rutean pero NUNCA se muestran (legado)
    examples        sufijos de ejemplo: («descubrir»,) → `workspace agentes descubrir`
    usage           uso fijo (pseudo-comandos: `workspace`, `<agente>`)
    hidden          rutea, pero no aparece en ayuda/pantalla/JSON por default
    dangerous       la pantalla Comandos pide «¿Seguro? s/n» antes de correrlo
    requires_args   sin args no hace nada útil: la pantalla muestra el uso y no corre
    dispatch        False = no es un subcomando de front.main (pseudo/flag/externo)
    runnable        False = la pantalla Comandos nunca lo ejecuta (p. ej. el hub)
    dev             comando de desarrollo (solo comandos_dev.py)
    """
    d = {"id": cid, "names": {"es": es, "en": en}, "group": group,
         "summary": {"es": summary_es, "en": summary_en},
         "when": {"es": when_es, "en": when_en},
         "args": args, "aliases": tuple(aliases),
         "hidden_aliases": tuple(hidden_aliases), "examples": tuple(examples),
         "usage_fixed": usage, "hidden": bool(hidden),
         "dangerous": bool(dangerous), "requires_args": bool(requires_args),
         "dispatch": bool(dispatch), "runnable": bool(runnable and dispatch),
         "dev": bool(dev)}
    # Claves de COMPATIBILIDAD (formato anterior: name/usage/es/en/when_*):
    # `name` = id estable (los mapas y los tests lo usan como llave).
    d.update(name=cid, es=summary_es, en=summary_en,
             when_es=when_es, when_en=when_en)
    d["usage"] = usage_of(d, "es")
    return d


def _c(name, usage, group, es, en, when_es, when_en):
    """Constructor del formato VIEJO (por si un árbol trae un comandos_dev.py
    anterior): lo traduce al META nuevo, sin alias."""
    return cmd(name, name, name, group, es, en, when_es, when_en,
               usage=usage, dev=(group == "dev"))


COMMANDS = (
    cmd("workspace", "workspace", "workspace", "agentes",
        "Abre el hub: tus agentes y el menú; escribe para buscar.",
        "Opens the hub: your agents and the menu; type to search.",
        "Para empezar a trabajar.", "To start working.",
        usage="workspace", dispatch=False),
    cmd("<agente>", "<agente>", "<agent>", "agentes",
        "Abre ese agente directo, sin pasar por el hub.",
        "Opens that agent directly, skipping the hub.",
        "Cuando ya sabes con quién quieres hablar.",
        "When you already know who you want to talk to.",
        usage={"es": "<agente>   (p. ej. el nombre de tu agente)",
               "en": "<agent>   (e.g. your agent's name)"}, dispatch=False),
    cmd("agentes", "agentes", "agents", "agentes",
        "Tus agentes y su estado; descubrir busca cerebros, reubicar repara una ruta.",
        "Your agents and their status; descubrir finds brains, reubicar fixes a path.",
        "Si un agente no aparece o dice que no encuentra su cerebro.",
        "If an agent is missing or says its brain cannot be found.",
        args="[descubrir | reubicar | estado]", examples=("descubrir", "estado")),
    cmd("tono", "tono", "tone", "agentes",
        "Ajusta cómo te hablan tus agentes (diales del 1 al 5).",
        "Adjust how your agents talk to you (dials from 1 to 5).",
        "Si quieres respuestas más cortas, más cálidas, más técnicas…",
        "If you want shorter, warmer, more technical answers…",
        aliases=("personalidad",)),
    cmd("onboarding", "bienvenida", "onboarding", "agentes",
        "Vuelve a correr la configuración guiada (continúa donde quedó).",
        "Runs the guided setup again (resumes where it stopped).",
        "Si quedó algo pendiente al instalar.", "If something was left pending at install."),
    cmd("agenda", "agenda", "agenda", "dia",
        "Tu agenda local: eventos con fecha y hora.",
        "Your local agenda: events with date and time.",
        "Para anotar algo rápido sin abrir el calendario.",
        "To jot something down without opening the calendar.",
        args="[add | rm]"),
    cmd("calendario", "calendario", "calendar", "dia",
        "Editor del calendario: mes, altas, cambios y bajas.",
        "Calendar editor: month, add, edit, delete.",
        "Para organizar la semana o el mes.", "To plan the week or the month.",
        aliases=("cal",)),
    cmd("proyectos", "proyectos", "projects", "dia",
        "App «Proyectos»: el mapa de todos tus proyectos con tu agente.",
        "«Proyectos» app: the map of all your projects with your agent.",
        "Para ver en qué va cada proyecto.", "To see where each project stands.",
        args="[stop]", aliases=("proyecto", "mapa")),
    cmd("mail", "correo", "mail", "dia",
        "Envía un correo desde la terminal; con --dry-run lo ves sin enviarlo.",
        "Sends an email from the terminal; --dry-run shows it without sending.",
        "Para mandar un aviso o resumen rápido.", "To send a quick notice or summary.",
        args={"es": "--to <correo> --subject <asunto> [--dry-run]",
              "en": "--to <email> --subject <subject> [--dry-run]"},
        requires_args=True),
    cmd("wf", "wf", "wf", "trabajo",
        "Flujos de trabajo paso a paso (crear un agente, construir una función…).",
        "Step-by-step workflows (create an agent, build a feature…).",
        "Para tareas largas que conviene hacer por pasos.", "For long tasks best done in steps.",
        args="new | list | run | status | resume | stats",
        aliases=("flujos", "workflows"), hidden_aliases=("workflow",),
        examples=("list",), requires_args=True),
    cmd("split", "split", "split", "trabajo",
        "Terminal partida: el chat a un lado y el tablero de flujos al otro.",
        "Split terminal: chat on one side, the workflow board on the other.",
        "Cuando corres un flujo y quieres verlo mientras hablas.",
        "When running a workflow and watching it while you chat.",
        args={"es": "[agente]", "en": "[agent]"}),
    cmd("eval", "evaluar", "eval", "trabajo",
        "Prueba a un agente contra su set de preguntas de referencia.",
        "Tests an agent against its reference question set.",
        "Después de cambiar algo importante en un agente.",
        "After changing something important in an agent.",
        args={"es": "<agente>", "en": "<agent>"}, aliases=("evals",),
        requires_args=True),
    # update: el comando es del núcleo de actualizaciones (front.cmd_update);
    # aquí solo vive su ficha.
    cmd("update", "actualizar", "update", "maquina",
        "Actualiza Workspace y tus cerebros, y repara lo necesario.",
        "Updates Workspace and your brains, and repairs what is needed.",
        "Cuando hay una versión nueva o algo dejó de funcionar.",
        "When there is a new version or something stopped working.",
        args="[--check | --rollback | --force | --auto auto|notify|off]", aliases=("up",),
        hidden_aliases=("--update",), examples=("--rollback", "--auto notify"),
        dangerous=True),
    cmd("version", "version", "version", "maquina",
        "Muestra tu versión, tu última actualización y sus novedades.",
        "Shows your version, your last update and what's new.",
        "Para saber qué tienes o al pedir ayuda.",
        "To know what you have, or when asking for help.",
        aliases=("versión",), hidden_aliases=("--version", "-V")),
    cmd("migrate", "migrar", "migrate", "maquina",
        "Muestra y aplica los ajustes que trae cada actualización.",
        "Shows and applies the adjustments each update brings.",
        "Si el doctor dice que un ajuste quedó pendiente o falló.",
        "If the doctor says an adjustment is pending or failed.",
        args="[--run | --pending | --offer <id> | --decline <id>]", examples=("--run",)),
    cmd("doctor", "doctor", "doctor", "maquina",
        "Revisa que todo esté bien; sin --check también repara. --bundle arma un "
        "ZIP de diagnóstico sin datos personales para pedir ayuda.",
        "Checks that everything is fine; without --check it also repairs. --bundle "
        "builds a diagnostic ZIP without personal data to ask for help.",
        "Si algo se ve raro. --check solo mira, no cambia nada.",
        "If something looks off. --check only looks, changes nothing.",
        args="[--check | --remote | --bundle]", aliases=("doc",), hidden_aliases=("--doctor",),
        examples=("--check", "--bundle")),
    cmd("repair", "reparar", "repair", "maquina",
        "Vuelve a preparar las conexiones de cada cerebro.",
        "Re-prepares the connections of each brain.",
        "Si un agente abre pero no recuerda o no guarda.",
        "If an agent opens but does not remember or save.",
        aliases=("fix",)),
    cmd("configurar-desarrollo", "configurar-desarrollo", "dev-setup", "maquina",
        "Revisa si esta máquina está lista para contribuir a Workspace.",
        "Checks whether this machine is ready to contribute to Workspace.",
        "Si vas a programar en Workspace.", "If you are going to code on Workspace."),
    # Migración recuperable de la instalación anterior (nombre viejo del
    # producto). El nombre viejo del comando sigue ruteando como alias OCULTO.
    cmd("migrar-legado", "migrar-legado", "migrate-legacy", "maquina",
        "Migra o retira la instalación anterior de Workspace, con respaldo.",
        "Migrates or retires the previous Workspace install, with a backup.",
        "Solo si venías de la versión anterior (con el nombre viejo).",
        "Only if you came from the previous version (under the old name).",
        args={"es": "[--apply | --retire | --rollback <respaldo>]",
              "en": "[--apply | --retire | --rollback <backup>]"},
        hidden_aliases=legacy.CLI_ALIASES),
    cmd("uninstall", "desinstalar", "uninstall", "maquina",
        "Desinstala Workspace de esta máquina (tus cerebros se quedan).",
        "Uninstalls Workspace from this machine (your brains stay).",
        "Si ya no lo vas a usar aquí.", "If you will no longer use it here.",
        args={"es": "[--dry-run | --no-backup | --keep-folder | --limpiar-todo]",
              "en": "[--dry-run | --no-backup | --keep-folder | --clean-all]"},
        aliases=("remove",),
        hidden_aliases=("--uninstall",),
        dangerous=True),
    cmd("comandos", "comandos", "commands", "maquina",
        "Esta lista de comandos; --json para agentes, --markdown para el manual.",
        "This list of commands; --json for agents, --markdown for the manual.",
        "Cuando quieres ver o exportar todos los comandos.",
        "When you want to see or export every command.",
        args="[--json | --markdown | --check]", examples=("--json",),
        runnable=False),
    cmd("help", "ayuda", "help", "maquina",
        "Muestra la lista de comandos en la terminal.",
        "Shows the list of commands in the terminal.",
        "Cuando no recuerdas un comando.", "When you do not remember a command.",
        aliases=("--help", "-h")),
    cmd("banner", "--banner", "--banner", "maquina",
        "Imprime el hub sin animación (vista estática, no interactiva).",
        "Prints the hub without animation (static, non-interactive view).",
        "Para capturas o terminales sin teclado.", "For screenshots or keyboard-less terminals.",
        dispatch=False),
    # ── ocultos: rutean, pero no son superficie anunciada del producto ──
    cmd("centro", "centro", "centro", "trabajo",
        "Backend del Centro de Control: misiones, estado y delegación.",
        "Control Center backend: missions, status and delegation.",
        "Lo usan los paneles; a mano, para depurar.", "Used by the panels; by hand, to debug.",
        args="…", hidden=True, requires_args=True),
    cmd("voz", "voz", "voice", "trabajo",
        "Dictado por voz local: graba, transcribe y pega.",
        "Local voice dictation: records, transcribes and pastes.",
        "Desde un atajo de teclado del sistema.", "From a system keyboard shortcut.",
        args="[--check | --setup]", aliases=("dictado",), hidden=True),
    cmd("memoria", "memoria", "memory", "agentes",
        "Memoria de la pestaña: notas con etiqueta, vigente, maleta y resumen.",
        "Tab memory: labelled notes, open items, handoff and summary.",
        "La usa el agente (nota, checkpoint); a mano, para ver o depurar.",
        "Used by the agent (nota, checkpoint); by hand, to view or debug.",
        args="nota|ver|vigente|maleta|checkpoint|status …", hidden=True, requires_args=True),
    cmd("panel", "panel", "panel", "trabajo",
        "Panel del lado derecho de la terminal partida.",
        "Right-hand pane of the split terminal.",
        "Lo abre split; a mano, para depurar.", "Opened by split; by hand, to debug.",
        aliases=("menu",), hidden=True),
)


#: Mapa conceptual de cada comando (por id): (nodos, tramos, nota) — el
#: formato de brain_view.pipeline. Nodos: («largo|corto», color c/ok/b/wh/dk/b2).
#: MAPS es la FUENTE en español; MAPS_EN (abajo) su traducción con la MISMA
#: forma (nodos, colores y tramos) — tests/test_comandos_catalog lo exige.
MAPS = {
    "workspace": ((("terminal", "wh"), ("hub", "c"), ("tu agente", "ok")),
                  ("workspace", "Enter"),
                  "el hub muestra tus agentes y el menú; escribe para buscar"),
    "<agente>": ((("terminal", "wh"), ("pestañas|sesión", "c"), ("tu agente", "ok")),
                 ("nombre del agente", "eliges o creas"),
                 "salta el hub · cada pestaña guarda su propia memoria"),
    "agentes": ((("tus agentes", "c"), ("estado", "wh"), ("reparado", "ok")),
                ("revisa", "descubrir · reubicar"),
                "solo lee y sugiere; reubicar cambia la ruta en esta máquina"),
    "tono": ((("diales 1-5", "c"), ("tu agente", "wh"), ("respuestas", "ok")),
             ("se guarda", "siguiente mensaje"),
             "3 = neutro · solo estilo, jamás identidad ni reglas"),
    "onboarding": ((("motores", "c"), ("apariencia", "wh"), ("agente", "wh"), ("listo", "ok")),
                   ("", "", ""),
                   "continúa donde quedó · listo = motor y agente verificados"),
    "agenda": ((("evento", "c"), ("agenda local|agenda", "wh"), ("hub", "ok")),
               ("add", "aparece en"),
               "se guarda en tu máquina · rm lo quita"),
    "calendario": ((("mes", "c"), ("eventos", "wh"), ("hub", "ok")),
                   ("altas · cambios", "aparece en"),
                   "editor a pantalla completa"),
    "proyectos": ((("proyectos", "c"), ("app local|app", "wh"), ("navegador", "ok")),
                  ("workspace proyectos", "abre"),
                  "corre en tu máquina · stop la cierra"),
    "mail": ((("mensaje", "c"), ("vista previa|previa", "wh"), ("enviado", "ok")),
             ("--dry-run", "sin --dry-run"),
             "usa --dry-run primero para ver exactamente qué saldría"),
    "wf": ((("flujo", "c"), ("pasos", "wh"), ("verificado", "ok")),
           ("run", "cada paso se revisa|verifica"),
           "puede pausar para tu aprobación · resume retoma"),
    "split": ((("chat", "c"), ("terminal partida|partida", "wh"), ("tablero", "wh")),
              ("izquierda", "derecha"),
              "Mac/Linux con tmux o herdr · en Windows abre la sesión sencilla"),
    "eval": ((("preguntas", "c"), ("agente", "wh"), ("puntaje", "ok")),
             ("responde", "compara"),
             "útil después de cambiar algo importante del agente"),
    "update": ((("versión nueva|nueva", "c"), ("¿arranca aquí?|¿arranca?", "wh"), ("al día", "ok")),
               ("descarga", "sí · doctor repara|sí"),
               "si no arranca, vuelve sola a la anterior · --rollback · --auto"),
    "version": ((("tu versión|versión", "c"), ("última actualización|última", "wh"),
                 ("novedades", "ok")),
                ("", ""),
                "solo lee · útil al pedir ayuda"),
    "migrate": ((("actualización", "c"), ("ajustes", "wh"), ("aplicados", "ok")),
                ("trae", "una vez, a la vista|una vez"),
                "cada ajuste corre una vez y queda anotado · --offer / --decline: opcionales"),
    "doctor": ((("revisión", "c"), ("reparación", "wh"), ("todo bien", "ok")),
               ("encuentra", "corrige"),
               "--check solo mira · --bundle: ZIP sin tus datos personales"),
    "repair": ((("conexiones", "c"), ("cada cerebro", "wh")),
               ("las vuelve a preparar",),
               "no toca tus permisos ni tu tema"),
    "configurar-desarrollo": ((("git", "c"), ("checkout", "wh"), ("tests", "wh"), ("listo", "ok")),
                              ("", "", ""),
                              "solo revisa · no toca tu instalación de uso diario"),
    "migrar-legado": ((("instalación vieja|vieja", "dk"), ("respaldo", "wh"), ("Workspace", "ok")),
                      ("plan · --apply", "--retire"),
                      "nunca borra cerebros ni sesiones · --rollback deshace"),
    "uninstall": ((("Workspace", "wh"), ("quitado", "dk")),
                  ("desinstala",),
                  "tus cerebros y conversaciones se quedan"),
    "help": ((("terminal", "wh"), ("lista de comandos|comandos", "c")),
             ("--help",),
             "lo mismo que esta pantalla, en texto"),
    "comandos": ((("catálogo", "c"), ("ayuda · pantalla|ayuda", "wh"), ("JSON · manual|JSON", "ok")),
                 ("se deriva", "--json · --markdown"),
                 "una sola fuente: lo que ves aquí es lo que rutea"),
    "banner": ((("hub", "c"), ("texto", "ok")),
               ("sin animación",),
               "vista estática, no interactiva · para capturas"),
}

#: Traducción EN de MAPS (misma forma; colores idénticos). Nombres de comando,
#: flags y subcomandos (descubrir, --json…) se quedan literales: así se teclean.
MAPS_EN = {
    "workspace": ((("terminal", "wh"), ("hub", "c"), ("your agent", "ok")),
                  ("workspace", "Enter"),
                  "the hub shows your agents and the menu; type to search"),
    "<agente>": ((("terminal", "wh"), ("tabs|session", "c"), ("your agent", "ok")),
                 ("agent name", "pick or create"),
                 "skips the hub · each tab keeps its own memory"),
    "agentes": ((("your agents", "c"), ("status", "wh"), ("repaired", "ok")),
                ("checks", "descubrir · reubicar"),
                "only reads and suggests; reubicar changes the path on this machine"),
    "tono": ((("dials 1-5", "c"), ("your agent", "wh"), ("answers", "ok")),
             ("saved", "next message"),
             "3 = neutral · style only, never identity or rules"),
    "onboarding": ((("engines", "c"), ("appearance", "wh"), ("agent", "wh"), ("ready", "ok")),
                   ("", "", ""),
                   "resumes where it stopped · ready = engine and agent verified"),
    "agenda": ((("event", "c"), ("local agenda|agenda", "wh"), ("hub", "ok")),
               ("add", "shows up in"),
               "saved on your machine · rm removes it"),
    "calendario": ((("month", "c"), ("events", "wh"), ("hub", "ok")),
                   ("add · edit", "shows up in"),
                   "full-screen editor"),
    "proyectos": ((("projects", "c"), ("local app|app", "wh"), ("browser", "ok")),
                  ("workspace projects", "opens"),
                  "runs on your machine · stop closes it"),
    "mail": ((("message", "c"), ("preview", "wh"), ("sent", "ok")),
             ("--dry-run", "without --dry-run"),
             "use --dry-run first to see exactly what would go out"),
    "wf": ((("workflow", "c"), ("steps", "wh"), ("verified", "ok")),
           ("run", "each step is checked|checked"),
           "it can pause for your approval · resume picks it up"),
    "split": ((("chat", "c"), ("split terminal|split", "wh"), ("board", "wh")),
              ("left", "right"),
              "Mac/Linux with tmux or herdr · on Windows opens the plain session"),
    "eval": ((("questions", "c"), ("agent", "wh"), ("score", "ok")),
             ("answers", "compares"),
             "useful after changing something important in the agent"),
    "update": ((("new version|new", "c"), ("starts here?|starts?", "wh"), ("up to date", "ok")),
               ("downloads", "yes · doctor repairs|yes"),
               "if it fails to start, it rolls back · --rollback · --auto"),
    "version": ((("your version|version", "c"), ("last update|last", "wh"),
                 ("what's new", "ok")),
                ("", ""),
                "read-only · handy when asking for help"),
    "migrate": ((("update", "c"), ("adjustments", "wh"), ("applied", "ok")),
                ("brings", "once, in plain sight|once"),
                "each adjustment runs once and is logged · --offer / --decline: optional ones"),
    "doctor": ((("check", "c"), ("repair", "wh"), ("all good", "ok")),
               ("finds", "fixes"),
               "--check only looks · --bundle: ZIP without your personal data"),
    "repair": ((("connections", "c"), ("each brain", "wh")),
               ("prepares them again",),
               "does not touch your permissions or your theme"),
    "configurar-desarrollo": ((("git", "c"), ("checkout", "wh"), ("tests", "wh"), ("ready", "ok")),
                              ("", "", ""),
                              "only checks · does not touch your everyday install"),
    "migrar-legado": ((("old install|old", "dk"), ("backup", "wh"), ("Workspace", "ok")),
                      ("plan · --apply", "--retire"),
                      "never deletes brains or sessions · --rollback undoes it"),
    "uninstall": ((("Workspace", "wh"), ("removed", "dk")),
                  ("uninstalls",),
                  "your brains and conversations stay"),
    "help": ((("terminal", "wh"), ("command list|commands", "c")),
             ("--help",),
             "the same as this screen, as text"),
    "comandos": ((("catalog", "c"), ("help · screen|help", "wh"), ("JSON · manual|JSON", "ok")),
                 ("derived", "--json · --markdown"),
                 "one source: what you see here is what routes"),
    "banner": ((("hub", "c"), ("text", "ok")),
               ("no animation",),
               "static, non-interactive view · for screenshots"),
}


# ── catálogo ───────────────────────────────────────────────────────────────

def dev_commands():
    """Comandos de desarrollo (solo si comandos_dev viaja en este árbol)."""
    try:
        import comandos_dev
        return list(comandos_dev.COMMANDS)
    except Exception:
        return []


def dev_group():
    try:
        import comandos_dev
        return comandos_dev.GROUP
    except Exception:
        return None


def all_commands(dev=True):
    """Producto (+ desarrollo si viaja y `dev`), incluidos los ocultos."""
    return list(COMMANDS) + (dev_commands() if dev else [])


def get(cid, dev=True):
    for c in all_commands(dev):
        if c["id"] == cid:
            return c
    return None


def display_name(c, lg=None):
    """Nombre del comando en el idioma activo (o `lg`)."""
    return c["names"].get(lg or lang()) or c["names"]["es"]


def summary_of(c, lg=None):
    return c["summary"].get(lg or lang()) or c["summary"]["es"]


def when_of(c, lg=None):
    return c["when"].get(lg or lang()) or c["when"]["es"]


def names_of(c, hidden=True):
    """Todos los nombres que rutean a `c` (sin duplicados, orden estable):
    ES, EN, alias y — si `hidden` — alias ocultos."""
    out = []
    pool = [c["names"]["es"], c["names"]["en"]] + list(c["aliases"])
    if hidden:
        pool += list(c["hidden_aliases"])
    for n in pool:
        if n and n not in out:
            out.append(n)
    return out


def shown_aliases(c, lg=None):
    """Los otros nombres VISIBLES (todos menos el del idioma activo)."""
    me = display_name(c, lg)
    return [n for n in names_of(c, hidden=False) if n != me]


def examples_of(c, lg=None):
    lg = lg or lang()
    name = display_name(c, lg)
    return ["workspace %s %s" % (name, _pick(e, lg)) for e in c.get("examples", ())]


def resolve(word, dev=True):
    """Nombre/alias tecleado → id del comando, o None. Solo subcomandos
    reales (dispatch). Exacto (sensible a mayúsculas, como siempre)."""
    if not word:
        return None
    for c in all_commands(dev):
        if c["dispatch"] and word in names_of(c):
            return c["id"]
    return None


def visible(dev=False, hidden=False):
    """Comandos que se muestran: producto (+ dev si `dev`), sin ocultos
    salvo `hidden`."""
    return [c for c in all_commands(dev) if hidden or not c["hidden"]]


def groups(dev=False):
    g = list(GROUPS)
    if dev:
        dg = dev_group()
        if dg and dev_commands():
            g.append(dg)
    return g


def command_map(name, lg=None):
    """Mapa conceptual del comando (por id) en el idioma `lg` (default: el
    activo) o None. En inglés usa MAPS_EN; si una entrada no tiene
    traducción cae a la española (falla-suave; el test la exige)."""
    en = (lg or lang()) == "en"
    m = (MAPS_EN.get(name) if en else None) or MAPS.get(name)
    if m:
        return m
    try:
        import comandos_dev
        return ((getattr(comandos_dev, "MAPS_EN", {}).get(name) if en else None)
                or comandos_dev.MAPS.get(name))
    except Exception:
        return None


# ── derivados: --help · JSON · Markdown ────────────────────────────────────

_TXT = {
    "es": {"usage": "uso: workspace [comando]", "use": "uso", "nocmd": "(sin comando)",
           "hub": "abre el hub (tus agentes y el menú)",
           "also": "también", "when": "Cuándo", "ex": "Ejemplos",
           "danger": "Pide confirmación en la pantalla Comandos.",
           "more": "detalle de cada uno: workspace comandos  ·  para agentes de IA: "
                   "workspace comandos --json",
           "title": "Comandos de Workspace",
           "intro": "Todo lo que puedes escribir en la terminal. Cada comando "
                    "acepta su nombre en español y en inglés."},
    "en": {"usage": "usage: workspace [command]", "use": "usage", "nocmd": "(no command)",
           "hub": "opens the hub (your agents and the menu)",
           "also": "also", "when": "When", "ex": "Examples",
           "danger": "Asks for confirmation in the Commands screen.",
           "more": "details for each: workspace commands  ·  for AI agents: "
                   "workspace commands --json",
           "title": "Workspace commands",
           "intro": "Everything you can type in the terminal. Every command "
                    "accepts its Spanish and its English name."},
}


def _gname(g, lg):
    return g[2] if lg == "en" else g[1]


def usage_text(lg=None, dev=False):
    """`workspace --help` derivado del catálogo, en el idioma `lg`. Un renglón
    por comando, agrupado; `dev` agrega el grupo de desarrollo (si viaja)."""
    lg = lg if lg in LANGS else lang()
    T = _TXT[lg]
    out = [T["usage"], "", "  %-22s %s" % (T["nocmd"], T["hub"])]
    for g in groups(dev):
        rows = [c for c in visible(dev) if c["group"] == g[0]
                and c["id"] not in ("workspace", "<agente>")]
        if not rows:
            continue
        out.append("")
        out.append(_gname(g, lg))
        for c in rows:
            left = usage_of(c, lg)
            if left.startswith("workspace "):
                left = left[len("workspace "):]
            if c["id"] == "help":
                left = "-h, --help"
            if len(left) <= 22:
                out.append("  %-22s %s" % (left, summary_of(c, lg)))
            else:
                out.append("  " + left)
                out.append("  %-22s %s" % ("", summary_of(c, lg)))
    out.append("")
    out.append(T["more"])
    return "\n".join(out) + "\n"


def help_text(cid, lg=None, dev=True):
    """`workspace <comando> --help`: la FICHA de UN comando, derivada del
    catálogo (cómo se escribe, sus otros nombres, qué hace, cuándo sirve y
    ejemplos) en el idioma `lg`. Solo texto: front.main la imprime SIN correr
    el comando. None si `cid` no tiene ficha."""
    c = get(cid, dev)
    if c is None:
        return None
    lg = lg if lg in LANGS else lang()
    T = _TXT[lg]
    out = ["%s: %s" % (T["use"], usage_of(c, lg))]
    al = shown_aliases(c, lg)
    if al:
        out.append("  %s: %s" % (T["also"], ", ".join(al)))
    out += ["", summary_of(c, lg), "%s: %s" % (T["when"], when_of(c, lg))]
    ex = examples_of(c, lg)
    if ex:
        out += ["", "%s:" % T["ex"]] + ["  " + e for e in ex]
    return "\n".join(out) + "\n"


def _public(c, lg):
    return {"id": c["id"], "name": display_name(c, lg), "names": dict(c["names"]),
            "aliases": shown_aliases(c, lg), "group": c["group"],
            "usage": usage_of(c, lg),
            "usage_by_lang": {k: usage_of(c, k) for k in LANGS},
            "summary": dict(c["summary"]), "when": dict(c["when"]),
            "examples": examples_of(c, lg), "hidden": c["hidden"],
            "dangerous": c["dangerous"], "requires_args": c["requires_args"],
            "subcommand": c["dispatch"], "dev": c["dev"]}


def as_json(lg=None, dev=False, hidden=False):
    """Catálogo para AGENTES de IA (`workspace comandos --json`): estable,
    con ambos idiomas. Nunca incluye alias ocultos."""
    lg = lg if lg in LANGS else lang()
    return {"schema": 1, "lang": lg,
            "groups": [{"id": g[0], "title": {"es": g[1], "en": g[2]}} for g in groups(dev)],
            "commands": [_public(c, lg) for c in visible(dev, hidden)]}


def as_markdown(lg=None, dev=False):
    """Capítulo del MANUAL (`workspace comandos --markdown`), derivado."""
    lg = lg if lg in LANGS else lang()
    T = _TXT[lg]
    out = ["# " + T["title"], "", T["intro"], ""]
    for g in groups(dev):
        rows = [c for c in visible(dev) if c["group"] == g[0]]
        if not rows:
            continue
        out += ["## " + _gname(g, lg), ""]
        for c in rows:
            out += ["### `%s`" % usage_of(c, lg), "", summary_of(c, lg), ""]
            out.append("**%s:** %s" % (T["when"], when_of(c, lg)))
            al = shown_aliases(c, lg)
            if al and c["dispatch"]:
                out += ["", "_%s: %s_" % (T["also"], ", ".join("`%s`" % a for a in al))]
            ex = examples_of(c, lg)
            if ex:
                out += ["", "**%s:**" % T["ex"], ""] + ["    " + e for e in ex]
            if c["dangerous"]:
                out += ["", "> " + T["danger"]]
            out.append("")
    return "\n".join(out).rstrip() + "\n"


# ── lint (equivalente a `omarchy commands --check`) ────────────────────────

def check(dispatch_ids=None, dev_gate=None):
    """Lista de problemas del catálogo ([] = sano). Revisa:
      · cada comando tiene nombre, resumen y «cuándo» en ES y EN;
      · ningún nombre/alias colisiona entre comandos (ni ids repetidos);
      · grupo conocido;
      · con `dispatch_ids` (las llaves de la tabla de front.main): catálogo
        con dispatch ⇔ tabla, en ambos sentidos;
      · con `dev_gate` (front._DEV_CMDS): coincide con los nombres de los
        comandos dev que rutean (solo si comandos_dev viaja en el árbol)."""
    probs = []
    cmds = all_commands(dev=True)
    gids = {g[0] for g in groups(dev=True)}
    seen_ids, owner = set(), {}
    for c in cmds:
        cid = c.get("id")
        if cid in seen_ids:
            probs.append("id repetido: %s" % cid)
        seen_ids.add(cid)
        for lg in LANGS:
            if not (c["summary"].get(lg) or "").strip():
                probs.append("%s: falta resumen %s" % (cid, lg.upper()))
            if not (c["when"].get(lg) or "").strip():
                probs.append("%s: falta «cuándo» %s" % (cid, lg.upper()))
            if not (c["names"].get(lg) or "").strip():
                probs.append("%s: falta nombre %s" % (cid, lg.upper()))
        if c["group"] not in gids:
            probs.append("%s: grupo desconocido %r" % (cid, c["group"]))
        for n in names_of(c):
            if not n or n != n.strip() or " " in n:
                probs.append("%s: nombre inválido %r" % (cid, n))
            if n in owner and owner[n] != cid:
                probs.append("colisión: %r lo usan %s y %s" % (n, owner[n], cid))
            owner.setdefault(n, cid)
    has_dev = bool(dev_commands())
    if dispatch_ids is not None:
        table = set(dispatch_ids)
        cat = {c["id"] for c in cmds if c["dispatch"]}
        for cid in sorted(table - cat):
            # Sin comandos_dev (distribución pública) los ids dev no tienen
            # ficha a propósito: los cubre el gate _DEV_CMDS, no el catálogo.
            if has_dev or cid not in set(dev_gate or ()):
                probs.append("despachado pero sin ficha en el catálogo: %s" % cid)
        for cid in sorted(cat - table):
            probs.append("en el catálogo pero front.main no lo despacha: %s" % cid)
    if dev_gate is not None and has_dev:
        names = set()
        for c in dev_commands():
            if c["dispatch"]:
                names.update(names_of(c))
        gate = set(dev_gate)
        for n in sorted(gate - names):
            probs.append("_DEV_CMDS tiene %r sin comando dev en el catálogo" % n)
        for n in sorted(names - gate):
            probs.append("comando dev %r no está en _DEV_CMDS (se colaría al cliente)" % n)
    return probs
