#!/usr/bin/env python3
"""WORKSPACE · agent_create_params — lo que se escribe en «Agregar agente» → los parámetros de agent_admin.create.

Una sola fuente para las tres caras de crear un agente: la tarjeta del hub (hub_agregar), la ventana «Nuevo agente» de
la página (localhost_front.crear_agente) y la pantalla de antes (add_agent_tui, que vuelve a llamar a `desde_form`).
Aquí no se dibuja ni se toca el disco: solo se arma el diccionario que recibe agent_create_job.start.

  · desde_form(vals, …)     el formulario largo de antes (17 campos): el mismo resultado que tenía la pantalla;
  · desde_tarjeta(…)        la tarjeta nueva: nombre (y su comando), para qué, y lo de «A tu medida» (cómo habla, qué
                            sí y qué no, sobre ti) más sus dos interruptores. Visible, rol, idioma y dueño salen solos.

Los textos libres viajan COMPLETOS (con sus saltos de línea) en `intake`: create() los guarda en .workspace/agent.json
y siembra STATE/users/<dueño>.md. La semilla del SOUL y el alcance se aplanan a UNA línea («·»): van a contextos de
una sola línea del template (BRAIN.md / BOOT), donde un salto crudo rompería el markdown.

Stdlib, Python 3.9+. Mac y Windows."""
import re

#: Topes de lo que se escribe en la tarjeta (los mismos de la página para «para qué»).
MAX_NOMBRE, MAX_TEXTO = 40, 600
#: El motor por omisión cuando nadie eligió (el primero de los soportados).
MOTOR_POR_OMISION = "claude-code"


def plano(txt):
    """Un texto de varias líneas en UNA («a · b · c»)."""
    return " · ".join(p.strip() for p in str(txt or "").split("\n") if p.strip())


def slug_dueno(txt):
    """El nombre corto del dueño (minúsculas, dígitos, - y _), o ''."""
    return re.sub(r"[^a-z0-9_-]+", "-", str(txt or "").strip().lower()).strip("-")[:32]


def desde_form(vals, defaults=None, engine=None, autonomy="brain", skill_review=False, elegir=("cara", "color")):
    """Los kwargs de agent_admin.create desde el formulario largo de antes. `vals`: lo escrito por campo (en el orden
    del formulario); `defaults`: lo que vale un campo vacío; `elegir`: los campos que se eligen y no se escriben
    (no van al intake)."""
    defaults = defaults or {}

    def g(k):
        return str(vals.get(k, "") or "").strip() or defaults.get(k, "")

    nombre = str(vals.get("nombre", "") or "").strip().lower()
    owner = slug_dueno(g("dueño"))
    partes = (("Propósito", plano(g("proposito") or g("rol")) or (g("visible") or nombre.capitalize())),
              ("Tono", plano(g("tono"))), ("Estilo", plano(g("estilo"))),
              ("Idioma", plano(g("idioma"))),
              ("Tareas típicas", plano(g("ejemplos"))))
    soul = " ".join("%s: %s." % (t, v) for t, v in partes if v)
    scope = plano(g("alcance"))
    if plano(g("limites")):
        scope = ((scope + " — ") if scope else "") + "Límites: " + plano(g("limites"))
    intake = {k: str(v or "").strip() for k, v in vals.items()
              if k not in elegir and str(v or "").strip()}
    return {"name": nombre, "display": g("visible") or nombre.capitalize(),
            "tagline": plano(g("rol")), "owner": owner, "scope": scope,
            "skills": plano(g("skills")), "soul": soul, "intake": intake,
            "engine": engine or MOTOR_POR_OMISION,
            "autonomy": autonomy, "skill_review": bool(skill_review)}


def idioma_de_la_computadora():
    """«español» o «English»: el idioma en que nace a trabajar (el de Workspace en esta computadora)."""
    try:
        import i18n
        return "English" if i18n.lang() == "en" else "español"
    except Exception:
        return "español"


def desde_tarjeta(comando, visible="", para="", como_habla="", que_si_no="", sobre_ti="", motor=None,
                  autonomia=True, revisar_skills=False, dueno="", idioma=None):
    """Los kwargs de agent_admin.create desde la tarjeta «Agregar agente» (hub y página). `comando`: el nombre corto
    (ya validado); `visible`: como se escribió («Brisa»); `autonomia`: trabaja en su carpeta sin preguntar;
    `dueno`: quien usa esta computadora (identidad.persona)."""
    comando = str(comando or "").strip().lower()
    visible = " ".join(str(visible or "").split())[:MAX_NOMBRE] or comando.capitalize()
    para, como, alcance, sobre = (str(x or "").strip()[:MAX_TEXTO] for x in (para, como_habla, que_si_no, sobre_ti))
    idioma = idioma or idioma_de_la_computadora()
    partes = (("Propósito", plano(para)), ("Estilo", plano(como)), ("Idioma", plano(idioma)))
    soul = " ".join("%s: %s." % (t, v) for t, v in partes if v)
    intake = {k: v for k, v in (("visible", visible if visible != comando.capitalize() else ""), ("proposito", para),
                                ("estilo", como), ("alcance", alcance), ("idioma", idioma),
                                ("dueño", slug_dueno(dueno)), ("dueño_quien", sobre)) if v}
    return {"name": comando, "display": visible, "tagline": plano(para)[:120], "owner": slug_dueno(dueno),
            "scope": plano(alcance), "soul": soul, "intake": intake, "engine": motor or MOTOR_POR_OMISION,
            "autonomy": "brain" if autonomia else "ask", "skill_review": bool(revisar_skills)}
