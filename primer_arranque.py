#!/usr/bin/env python3
r"""WORKSPACE · primer_arranque — el primer arranque nuevo: el hub abre con la tarjeta «Agregar agente» (su paso «Tú»,
O4-b), en vez del asistente de antes (onboarding_tui, que ya no se abre). Es la red mientras la rama de la tarjeta no
esté en esta copia: con ella, decide agregar_logica.es_primer_arranque (front._primer_arranque).

Lo que se conserva del de antes, con la misma constancia (~/.claude/workspace/onboarded.json; WORKSPACE_ONBOARDED la
pisa en las pruebas):
  · solo la primera vez y solo sin agentes: una máquina que ya tiene agentes se marca «adopcion» en silencio;
  · WORKSPACE_NO_ONBOARDING lo apaga;
  · el idioma: si nadie lo eligió (ni ui.lang ni WORKSPACE_LANG), el del sistema, si Workspace lo trae;
  · el flag se escribe al abrir el hub con la tarjeta: cerrar a medias no vuelve a molestar (`workspace onboarding`
    la abre otra vez cuando quieras).
El motor por omisión lo pone la tarjeta (su paso «¿Con qué pienso?»). Stdlib."""
import datetime
import json
import os
import sys

import paths as _paths  # SSOT del dir de estado (guarda: tests/test_state_dir_guard.py)


def flag_path():
    """La constancia del primer arranque (la misma del de antes)."""
    p = os.environ.get("WORKSPACE_ONBOARDED", "").strip()
    if p:
        return os.path.expanduser(p)
    return os.path.join(_paths.state_dir(), "onboarded.json")


def ya_corrio():
    """¿Ya corrió (o se adoptó) aquí? Un flag ilegible cuenta como SÍ: ante la duda, no re-molestar."""
    try:
        return os.path.exists(flag_path())
    except Exception:
        return True


def marcar(extra=None):
    """Escribe/actualiza la constancia (mezcla sobre lo que haya). Falla-suave."""
    p = flag_path()
    data = {"version": 1}
    try:
        with open(p, encoding="utf-8") as fh:
            prev = json.load(fh)
        if isinstance(prev, dict):
            data.update(prev)
    except Exception:
        pass
    data["ts"] = datetime.datetime.now().isoformat(timespec="seconds")
    data.update(extra or {})
    try:
        os.makedirs(os.path.dirname(p), exist_ok=True)
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception:
        pass
    return data


def _agentes():
    try:
        import agentsreg
        return agentsreg.agents()
    except Exception:
        return []


def toca(argv=None):
    """¿Este arranque del hub es el primero? Solo sin subcomando, sin WORKSPACE_NO_ONBOARDING, sin constancia y sin
    agentes (con agentes: se adopta en silencio). Falla-suave → False."""
    try:
        argv = sys.argv if argv is None else argv
        if len(argv) > 1 or os.environ.get("WORKSPACE_NO_ONBOARDING"):
            return False
        if ya_corrio():
            return False
        if _agentes():
            marcar({"modo": "adopcion", "completo": True})
            return False
        return True
    except Exception:
        return False


def _idioma_del_sistema():
    candidatos = []
    if sys.platform == "darwin":
        try:
            import subprocess
            r = subprocess.run(["/usr/bin/defaults", "read", "-g", "AppleLanguages"], capture_output=True,
                               text=True, encoding="utf-8", errors="replace", timeout=3)
            for tok in (r.stdout or "").replace("(", " ").replace(")", " ").replace(",", " ").split():
                tok = tok.strip().strip('"')
                if tok:
                    candidatos.append(tok)
                    break                          # el primero es el de la interfaz
        except Exception:
            pass
    for var in ("LC_ALL", "LC_MESSAGES", "LANG"):
        v = (os.environ.get(var) or "").strip()
        if v and v not in ("C", "POSIX") and not v.startswith("C."):
            candidatos.append(v)
            break
    try:
        import i18n
        hay = {c for c, _n in i18n.available()}
    except Exception:
        hay = {"es", "en"}
    for c in candidatos:
        code = c.replace("-", "_").split("_")[0].split(".")[0].lower()
        if code in hay:
            return code
    return ""


def idioma_automatico():
    """Si nadie eligió idioma y el del sistema se lee, lo guarda (lo mismo que hacía el de antes). → el código o ''."""
    if os.environ.get("WORKSPACE_LANG"):
        return ""
    try:
        import settings
        if settings.get_stored("ui.lang"):
            return ""
        code = _idioma_del_sistema()
        if code:
            import i18n
            i18n.set_lang(code)
        return code
    except Exception:
        return ""


def empezar():
    """El hub va a abrir con la tarjeta del primer arranque: el idioma del sistema y la constancia. → dónde abre el
    hub (Directo.abrir_al_empezar)."""
    idioma_automatico()
    marcar({"modo": "tarjeta", "completo": False})
    return "agregar:primera"
