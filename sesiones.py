#!/usr/bin/env python3
"""WORKSPACE · sesiones — `workspace sesiones`: la lista única de pestañas y
archivar sin borrar (sesiones v2, frente B).

  workspace sesiones lista [--archivadas] [--agente X] [--json]
  workspace sesiones archivar <nombre> [--agente X]
  workspace sesiones desarchivar <nombre> | --ultimas [--agente X]
  workspace sesiones conversacion on|off|ver [--agente X | --cerebro RUTA]

  (también en inglés: list / archive / unarchive, --archived, --last, --agent)

De qué agente: `--agente X`; si no, el de la ventana donde se corre
(WORKSPACE_BRAIN / WORKSPACE_AGENT_NAME), el cerebro de la carpeta actual o,
sin nada de eso, todos los agentes registrados (`archivar <nombre>` busca en
cuál está esa pestaña; si está en varios, pide --agente). `desarchivar
--ultimas` sin agente deshace el último lote de ESTA máquina (el aviso del
archivo automático puede abarcar varios cerebros).

Todo el trabajo lo hace sessions_registry (archivar/desarchivar/archivadas/
desarchivar_ultimas/tabs); aquí solo se resuelve el agente y se imprime.
`conversacion` prende o apaga, POR CEREBRO, que la conversación de Claude Code
viaje con él (conversaciones.fijar_permiso: lo ven todas las máquinas y personas
que usan ese cerebro).
Stdlib, 3.9+, Mac/Windows/Linux. Sale con 0 si hizo lo pedido, 1 si no.
"""
import argparse
import json
import os
import sys

_ROOT = os.path.dirname(os.path.abspath(__file__))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

import sessions_registry as reg  # noqa: E402

_COMANDOS = {"lista": "lista", "list": "lista", "ls": "lista",
             "archivar": "archivar", "archive": "archivar",
             "desarchivar": "desarchivar", "unarchive": "desarchivar",
             "restore": "desarchivar", "recuperar": "desarchivar",
             "conversacion": "conversacion", "conversación": "conversacion",
             "conversation": "conversacion"}
_CONV_ACCION = {"on": "on", "si": "on", "sí": "on", "yes": "on", "prender": "on",
                "claude-code": "on",
                "off": "off", "no": "off", "apagar": "off",
                "ver": "ver", "estado": "ver", "status": "ver", "show": "ver", "": "ver"}


def _t(key, es, **kw):
    return reg._t(key, es, **kw)


def _parser():
    p = argparse.ArgumentParser(
        prog="workspace sesiones",
        description="Tus pestañas: la lista única (la del cerebro) y archivar sin borrar.")
    p.add_argument("comando", choices=sorted(_COMANDOS))
    p.add_argument("nombre", nargs="*")
    p.add_argument("--archivadas", "--archived", dest="archivadas", action="store_true")
    p.add_argument("--ultimas", "--last", dest="ultimas", action="store_true")
    p.add_argument("--agente", "--agent", dest="agente", default=None)
    p.add_argument("--cerebro", "--brain", dest="cerebro", default=None)
    p.add_argument("--json", action="store_true")
    return p


# ── de qué agente y qué cerebro ─────────────────────────────────────────────
def _registrados():
    """[(agente, cerebro)] de los agentes registrados con su cerebro en disco,
    sin repetir cerebros. Falla-suave → []."""
    out, vistos = [], set()
    try:
        import dispatch
        for entry in dispatch.load_registry().get("agents", []):
            try:
                brain = dispatch.resolve_brain(entry["name"], dispatch.load_agent_cfg(entry))
            except Exception:
                continue
            if not brain or not os.path.isdir(brain):
                continue
            key = reg._brain_key(brain)
            if key not in vistos:
                vistos.add(key)
                out.append((entry["name"], brain))
    except Exception:
        pass
    return out


def _agente_de(brain, registrados=None):
    key = reg._brain_key(brain)
    for name, b in (registrados if registrados is not None else _registrados()):
        if reg._brain_key(b) == key:
            return name
    return ""


def _raiz(path):
    try:
        import memoria
        return memoria.raiz_cerebro(path)
    except Exception:
        return os.path.abspath(path)


def destinos(agente=None, cerebro=None):
    """([(agente, cerebro)], explícito). Explícito = el usuario (o la ventana)
    dijo de qué agente; si no, todos los registrados. ValueError con el
    mensaje si el agente pedido no existe."""
    if agente:
        try:
            import dispatch
            entry = dispatch.find_agent(agente)
            brain = dispatch.resolve_brain(entry["name"], dispatch.load_agent_cfg(entry)) \
                if entry else ""
        except Exception:
            entry, brain = None, ""
        if not entry or not brain or not os.path.isdir(brain):
            raise ValueError(_t("sesiones.cli.sin_agente", "no conozco al agente «{agente}»",
                                agente=agente))
        return [(entry["name"], brain)], True
    if cerebro:
        brain = _raiz(cerebro)
        return [(os.environ.get("WORKSPACE_AGENT_NAME") or _agente_de(brain), brain)], True
    env = (os.environ.get("WORKSPACE_BRAIN") or "").strip()
    if env and os.path.isdir(env):
        brain = _raiz(env)
        return [(os.environ.get("WORKSPACE_AGENT_NAME") or _agente_de(brain), brain)], True
    todos = _registrados()
    aqui = _raiz(os.getcwd())
    for name, b in todos:
        if reg._brain_key(b) == reg._brain_key(aqui):
            return [(name, b)], True
    return todos, False


# ── comandos ────────────────────────────────────────────────────────────────
def _lista(dest, archivadas, como_json):
    data = []
    for agent, brain in dest:
        filas = reg.archivadas(brain, agent) if archivadas else reg.tabs(brain, agent)
        n_arch = 0 if archivadas else len(reg.archivadas(brain, agent))
        huer = sorted((h.get("name") or sl) for sl, h in reg.huerfanas(brain).items()
                      if isinstance(h, dict) and h.get("agente", agent) in ("", agent))
        data.append({"agente": agent, "cerebro": brain,
                     "pestanas": [{"name": t["name"], "slug": t["slug"],
                                   "archivada": t.get("archivada", ""),
                                   "last_opened": t.get("last_opened", "")} for t in filas],
                     "archivadas": n_arch, "huerfanas": huer})
    if como_json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
        return 0
    varios = len(data) > 1
    for d in data:
        if varios:
            print("%s · %s" % (d["agente"] or "?", d["cerebro"]))
        sangria = "  " if varios else ""
        if not d["pestanas"]:
            print(sangria + (_t("sesiones.cli.ninguna_arch", "(ninguna archivada)") if archivadas
                             else _t("sesiones.cli.ninguna", "(sin pestañas)")))
        for t in d["pestanas"]:
            extra = ("  · " + t["archivada"]) if archivadas and t["archivada"] else ""
            print("%s- %s%s" % (sangria, t["name"], extra))
        if d["archivadas"]:
            print(sangria + _t("sesiones.cli.cuantas_arch",
                               "{n} archivada(s): workspace sesiones lista --archivadas",
                               n=d["archivadas"]))
        if archivadas and d["huerfanas"]:
            print(sangria + _t("sesiones.cli.huerfanas",
                               "{n} solo en esta máquina, sin memoria en el cerebro "
                               "(no se muestran): {nombres}",
                               n=len(d["huerfanas"]), nombres=", ".join(d["huerfanas"])))
            print(sangria + _t("sesiones.cli.huerfanas_hint",
                               "recupera una con: workspace sesiones desarchivar <nombre>"))
    return 0


def _donde(dest, nombre, quiere):
    """Los (agente, cerebro) donde la pestaña `nombre` puede recibir la acción:
    `quiere` = "activa" (para archivar) o "archivada" (para desarchivar, que
    también recupera una huérfana)."""
    sl = reg._slug(nombre)
    out = []
    for agent, brain in dest:
        rutas = reg._rutas_tab(brain, nombre)
        if rutas:
            out.append((agent, brain))
        elif quiere == "archivada" and sl in reg.huerfanas(brain):
            out.append((agent, brain))
    return out


def _archivar(dest, explicito, nombre):
    cand = dest if explicito else _donde(dest, nombre, "activa")
    if not explicito and len(cand) > 1:
        cand = [(a, b) for a, b in cand if not reg.esta_archivada(b, nombre)] or cand
    if not cand or not reg._rutas_tab(cand[0][1], nombre):
        print("✗ " + _t("sesiones.cli.no_existe", "no encuentro la pestaña «{name}»", name=nombre))
        return 1
    if len(cand) > 1:
        print("✗ " + _t("sesiones.cli.varios", "«{name}» existe en varios agentes ({agentes}): "
                        "di cuál con --agente", name=nombre,
                        agentes=", ".join(a or "?" for a, _b in cand)))
        return 1
    agent, brain = cand[0]
    visible = reg._nombre_visible(brain, nombre)
    if reg.esta_archivada(brain, nombre):
        print(_t("sesiones.cli.ya_archivada", "«{name}» ya estaba archivada", name=visible))
        return 0
    if not reg.archivar(brain, agent, nombre):
        print("✗ " + _t("sesiones.cli.no_pude", "no pude cambiar «{name}» (¿el archivo no es "
                        "UTF-8 o está bloqueado?)", name=visible))
        return 1
    print(_t("sesiones.cli.archivada", "✓ archivada «{name}» ({agente}) · deshacer: "
             "workspace sesiones desarchivar --ultimas", name=visible, agente=agent or "?"))
    return 0


def _desarchivar(dest, explicito, nombre):
    cand = dest if explicito else _donde(dest, nombre, "archivada")
    if not explicito and len(cand) > 1:
        cand = [(a, b) for a, b in cand if reg.esta_archivada(b, nombre)
                or reg._slug(nombre) in reg.huerfanas(b)] or cand
    if not cand:
        print("✗ " + _t("sesiones.cli.no_existe", "no encuentro la pestaña «{name}»", name=nombre))
        return 1
    if len(cand) > 1:
        print("✗ " + _t("sesiones.cli.varios", "«{name}» existe en varios agentes ({agentes}): "
                        "di cuál con --agente", name=nombre,
                        agentes=", ".join(a or "?" for a, _b in cand)))
        return 1
    agent, brain = cand[0]
    tenia = bool(reg._rutas_tab(brain, nombre))
    if tenia and not reg.esta_archivada(brain, nombre):
        print(_t("sesiones.cli.ya_activa", "«{name}» ya estaba en tus pestañas",
                 name=reg._nombre_visible(brain, nombre)))
        return 0
    if not reg.desarchivar(brain, agent, nombre):
        print("✗ " + (_t("sesiones.cli.no_pude", "no pude cambiar «{name}» (¿el archivo no es "
                         "UTF-8 o está bloqueado?)", name=nombre) if tenia
                      else _t("sesiones.cli.no_existe", "no encuentro la pestaña «{name}»",
                              name=nombre)))
        return 1
    print(_t("sesiones.cli.desarchivada", "✓ «{name}» volvió a tus pestañas ({agente})",
             name=reg._nombre_visible(brain, nombre), agente=agent or "?"))
    return 0


def _ultimas(dest, explicito):
    brain = dest[0][1] if explicito and len(dest) == 1 else None
    agent = dest[0][0] if brain else None
    nombres = reg.desarchivar_ultimas(brain, agent)
    if not nombres:
        print(_t("sesiones.cli.nada", "nada que deshacer"))
        return 0
    print(_t("sesiones.cli.recuperadas", "✓ recuperé: {nombres}", nombres=", ".join(nombres)))
    return 0


def _conversacion(dest, explicito, accion):
    """`workspace sesiones conversacion on|off|ver`: el permiso del CEREBRO para
    que la conversación de Claude Code viaje con él."""
    import conversaciones as conv
    acc = _CONV_ACCION.get(accion.strip().lower())
    if acc is None:
        print("✗ " + _t("sesiones.cli.conv.uso",
                        "usa: workspace sesiones conversacion on|off|ver [--agente X]"))
        return 1
    if acc == "ver":
        for agent, brain in dest:
            quien = agent or os.path.basename(brain.rstrip("/\\"))
            if conv.origen(brain) == "cerebro":
                print(_t("sesiones.cli.conv.ver_si", "{agente}: la conversación de Claude Code "
                         "viaja (lo decidió el cerebro)", agente=quien)
                      if conv.activo("claude-code", brain) else
                      _t("sesiones.cli.conv.ver_no", "{agente}: la conversación de Claude Code se "
                         "queda en cada máquina (lo decidió el cerebro)", agente=quien))
            else:
                print(_t("sesiones.cli.conv.ver_maquina", "{agente}: el cerebro no ha decidido; "
                         "manda el ajuste de esta máquina (sesiones.llevar_conversacion = "
                         "{valor})", agente=quien, valor=conv.modo_maquina()))
        return 0
    if not explicito or len(dest) != 1:
        print("✗ " + _t("sesiones.cli.conv.cual", "di de qué agente con --agente (o --cerebro)"))
        return 1
    agent, brain = dest[0]
    quien = agent or os.path.basename(brain.rstrip("/\\"))
    try:
        conv.fijar_permiso(brain, "claude-code" if acc == "on" else "off")
    except ValueError as e:
        print("✗ " + _t("sesiones.cli.conv.no_pude", "no pude guardar el permiso en el cerebro "
                        "de {agente}: {error}", agente=quien, error=str(e)))
        return 1
    if acc == "on":
        print("✓ " + _t("sesiones.cli.conv.on", "en el cerebro de {agente} la conversación de "
                        "Claude Code viaja (lo ven todos los que usan este cerebro)",
                        agente=quien))
        print("  " + _t("sesiones.cli.conv.on_hint", "con Obsidian Sync, prende «Sync all other "
                        "types» en cada dispositivo; para privacidad, usa un cerebro aparte"))
    else:
        print("✓ " + _t("sesiones.cli.conv.off", "en el cerebro de {agente} la conversación de "
                        "Claude Code se queda en cada máquina", agente=quien))
    return 0


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    a = _parser().parse_intermixed_args(argv)
    cmd = _COMANDOS[a.comando]
    nombre = " ".join(a.nombre).strip()
    try:
        dest, explicito = destinos(a.agente, a.cerebro)
    except ValueError as e:
        print("✗ " + str(e))
        return 1
    if not dest and not (cmd == "desarchivar" and a.ultimas):
        print("✗ " + _t("sesiones.cli.sin_cerebro",
                        "no encuentro ningún cerebro: abre un agente o usa --agente"))
        return 1
    if cmd == "lista":
        return _lista(dest, a.archivadas, a.json)
    if cmd == "conversacion":
        return _conversacion(dest, explicito, nombre)
    if cmd == "desarchivar" and a.ultimas:
        return _ultimas(dest, explicito)
    if not nombre:
        print("✗ " + _t("sesiones.cli.falta_nombre", "falta el nombre de la pestaña"))
        return 1
    if cmd == "archivar":
        return _archivar(dest, explicito, nombre)
    return _desarchivar(dest, explicito, nombre)


if __name__ == "__main__":
    raise SystemExit(main())
