#!/usr/bin/env python3
"""WORKSPACE · agente_apartar — archivar un agente o quitarlo de Workspace, sin borrar nada y con «Deshacer».

Antes solo se podía agregar. Dos maneras de apartar a un agente de esta computadora:

  · «Archivar»            sale del registro de esta computadora (agents.local.json) y, con él, de las listas, de Inicio,
                          del riel y de los selectores: todas las vistas leen ese registro. Su carpeta (el cerebro) y
                          sus sesiones no se tocan. Queda en «Archivados» y vuelve con un clic (`volver`).
  · «Quitar de Workspace» lo desregistra en esta computadora con el quitar de siempre (agent_manage.unregister: el
                          registro, lo que Workspace le escribió para Cursor y Kiro y la confianza que le dio en Codex
                          y Antigravity) y además su ruta local (paths.local.json), su comando de la terminal y su
                          entrada de tema. Su carpeta NUNCA se borra: el aviso dice dónde se queda.

Las dos dejan una ficha en `<estado>/agentes-apartados.local.json` con lo que había (su entrada del registro, su tema,
su ruta local, si estaba oculto): con ella `deshacer` lo deja como estaba. Nada se borra: lo único que desaparece del
disco es lo que Workspace genera solo y vuelve a generar (su comando en ~/.local/bin), y lo demás queda en la ficha.

Los casos de borde no bloquean: se avisan antes (`avisos`) y quien llama pide confirmar —
  actual     es el agente con el que estás hablando;
  ultimo     es el único que tienes;
  sesion     tiene una sesión abierta o un trabajo en curso (pending_runs, los jobs de crear y cargar);
  coordina   les manda encargos a otros agentes por el bus (messages): avisa, pero deja;
  a_medias   su carpeta no está completa en esta computadora (¿falta sincronizar?): se puede archivar, quitar y traer
             de vuelta igual, sin inventar una carpeta vacía.

Un agente del registro del equipo (no cargado en esta computadora) no se puede desregistrar: se oculta, como siempre.

Stdlib, falla-suave: cada función devuelve {"ok": True, "msg": …, "deshacer": nombre} o {"ok": False, "error": …}.
"""
import contextlib
import io
import json
import os
import sys
import time

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

#: La ficha de los apartados (por computadora, junto al registro).
ARCHIVO = "agentes-apartados.local.json"
ARCHIVADO, QUITADO = "archivado", "quitado"
#: Las claves de los avisos, en el orden en que se dicen.
CLAVES = ("actual", "ultimo", "sesion", "coordina", "a_medias")
#: Los estados de un cerebro que no está completo en esta computadora (agent_state).
_A_MEDIAS = ("brain_missing", "brain_unreadable", "definition_missing", "invalid_config")


def _t(key, es, **kw):
    """La cadena `key` del catálogo (lang/*/apartar.py) en el idioma activo; sin catálogo, `es` tal cual."""
    s = es
    try:
        import i18n
        v = i18n.t(key)
        if v != key:
            s = v
    except Exception:
        s = es
    if kw:
        try:
            return s.format(**kw)
        except Exception:
            return s
    return s


def _ok(msg, **mas):
    return dict({"ok": True, "msg": msg}, **mas)


def _err(msg):
    return {"ok": False, "error": str(msg)}


def ruta_corta(p):
    """La ruta con «~» en lugar de tu carpeta: lo que se lee en el aviso."""
    home = os.path.expanduser("~")
    return ("~" + p[len(home):]) if p and home and p.startswith(home) and home != os.sep else (p or "")


# ── la ficha ──────────────────────────────────────────────────────────────────
def ruta():
    import paths
    return os.path.join(paths.state_dir(), ARCHIVO)


def _leer():
    """{"version": 1, "agentes": [fichas]}. Sin archivo o ilegible → vacío (no se toca: lo aparta quien escribe)."""
    try:
        with open(ruta(), encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        return {"version": 1, "agentes": []}
    if not isinstance(d, dict) or not isinstance(d.get("agentes"), list):
        return {"version": 1, "agentes": []}
    d["agentes"] = [r for r in d["agentes"] if isinstance(r, dict) and r.get("name")]
    return d


def _danado():
    """¿El archivo existe pero no se puede leer como fichas?"""
    p = ruta()
    if not os.path.lexists(p):
        return False
    try:
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        return not (isinstance(d, dict) and isinstance(d.get("agentes"), list))
    except (OSError, ValueError):
        return True


def _escribir(d):
    """Guarda las fichas (temporal + reemplazo). Un archivo dañado se aparta con otro nombre antes: no se borra."""
    p = ruta()
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if _danado():
        try:
            os.replace(p, "%s.danado-%s" % (p, time.strftime("%Y%m%d-%H%M%S")))
        except OSError:
            pass
    tmp = "%s.tmp-%d" % (p, os.getpid())
    try:
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(d, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
        os.replace(tmp, p)
        return True
    except OSError:
        try:
            os.remove(tmp)
        except OSError:
            pass
        return False


def _candado():
    from olock import file_lock
    return file_lock(ruta(), timeout=10)


def _buscar(nombre):
    n = str(nombre or "").strip().lower()
    return next((r for r in _leer()["agentes"] if str(r.get("name")).lower() == n), None)


def _guardar(ficha):
    with _candado():
        d = _leer()
        d["agentes"] = [r for r in d["agentes"] if r.get("name") != ficha["name"]] + [ficha]
        return _escribir(d)


def _olvidar(nombre):
    with _candado():
        d = _leer()
        quedan = [r for r in d["agentes"] if r.get("name") != nombre]
        if len(quedan) == len(d["agentes"]):
            return True
        d["agentes"] = quedan
        return _escribir(d)


def _entrada(nombre):
    """Su entrada del registro de esta computadora, tal cual está escrita (None si no está cargado aquí)."""
    import agentsreg
    for a in agentsreg.read_local().get("agents", []):
        if isinstance(a, dict) and str(a.get("name", "")).strip().lower() == nombre:
            return dict(a)
    return None


def _oculto(nombre):
    try:
        import agent_manage
        return nombre in agent_manage._hidden()
    except Exception:
        return False


def _ficha(a, modo):
    nombre = a["name"]
    entrada = _entrada(nombre)
    return {"name": nombre, "display": a.get("display") or nombre.capitalize(), "color": a.get("color") or "",
            "brain": a.get("brain") or (entrada or {}).get("brain") or "", "modo": modo,
            "cuando": time.strftime("%Y-%m-%dT%H:%M:%S"), "entrada": entrada, "equipo": entrada is None,
            "oculto": _oculto(nombre)}


def _invalidar():
    try:
        import agent_state
        agent_state.invalidate()
    except Exception:
        pass


@contextlib.contextmanager
def _callado():
    """Mientras se quita o se trae de vuelta, lo que imprimen el instalador y la carga (install.say/ok) no llega a la
    pantalla: el hub pinta en esta misma terminal. El mismo candado y la misma captura que cargar y crear
    (agent_load_job.STDIO_LOCK): una sola cosa cambia la salida del proceso a la vez."""
    try:
        import agent_load_job
        candado = agent_load_job.STDIO_LOCK
    except Exception:
        candado = None
    if candado is not None:
        candado.acquire()
    old = (sys.stdout, sys.stderr, sys.stdin)
    sys.stdout, sys.stderr, sys.stdin = io.StringIO(), io.StringIO(), io.StringIO("")
    try:
        yield
    finally:
        sys.stdout, sys.stderr, sys.stdin = old
        if candado is not None:
            candado.release()


def _actual(agent_id, expected_brain):
    import agent_manage
    return agent_manage._current(agent_id, expected_brain)


# ── archivar ──────────────────────────────────────────────────────────────────
def archivar(agent_id, expected_brain=None):
    """Lo saca de las listas de esta computadora y lo deja en «Archivados». Su carpeta y sus sesiones no se tocan."""
    import agent_manage
    import agentsreg
    a, e = _actual(agent_id, expected_brain)
    if a is None:
        return _err(e)
    nombre = a["name"]
    ficha = _ficha(a, ARCHIVADO)
    if not _guardar(ficha):
        return _err(_t("apartar.err.guardar", "No pude guardar su ficha: no cambié nada."))
    if ficha["equipo"]:                               # del registro del equipo: no se desregistra, se oculta
        r = agent_manage.set_hidden(nombre, True)
        if not r.get("ok"):
            _olvidar(nombre)
            return r
    else:
        try:
            r = agentsreg.remove(nombre)
        except Exception as ex:
            r = (False, "%s: %s" % (type(ex).__name__, ex))
        if isinstance(r, tuple) and not r[0]:
            _olvidar(nombre)
            return _err(_t("apartar.err.archivar", "No pude archivarlo: {e}", e=r[1] if len(r) > 1 else "?"))
    _invalidar()
    return _ok(_t("apartar.archivado", "Archivé a {n}. Su carpeta y sus sesiones siguen en {p}.",
                  n=ficha["display"], p=ruta_corta(ficha["brain"]) or "?"),
               deshacer=nombre, donde=ficha["brain"], modo=ARCHIVADO)


def archivados():
    """Los archivados que se pueden traer de vuelta: [{name, display, color, brain, existe, cuando}], el más reciente
    primero. Uno que ya volvió a estar registrado (lo cargaron a mano) no sale."""
    try:
        import agentsreg
        registrados = {a["name"] for a in agentsreg.agents()}
    except Exception:
        registrados = set()
    out = []
    for r in _leer()["agentes"]:
        if r.get("modo") != ARCHIVADO or (r["name"] in registrados and not r.get("equipo")):
            continue
        if r.get("equipo") and not _oculto(r["name"]):
            continue
        b = r.get("brain") or ""
        out.append({"name": r["name"], "display": r.get("display") or r["name"], "color": r.get("color") or "",
                    "brain": b, "existe": bool(b) and os.path.isdir(os.path.expanduser(b)),
                    "cuando": r.get("cuando") or ""})
    return sorted(out, key=lambda x: x["cuando"], reverse=True)


def aviso_de_archivado(nombre):
    """'' o la línea para quien escribe su comando en la terminal estando archivado."""
    r = _buscar(nombre)
    if not r or r.get("modo") != ARCHIVADO:
        return ""
    return _t("apartar.terminal", "{n} está archivado: tráelo de vuelta en el hub, Agentes › Esta máquina › Archivados "
                                  "(su carpeta sigue en {p}).", n=r.get("display") or r["name"],
              p=ruta_corta(r.get("brain") or "") or "?")


# ── quitar de Workspace ───────────────────────────────────────────────────────
def _escritura_global_permitida():
    """Como el instalador: desde un worktree secundario no se tocan los comandos de ~/.local/bin (salvo la suite)."""
    try:
        import install
        return not (install.running_from_worktree() and os.environ.get(install.FORCE_ENV) != "1")
    except Exception:
        return False


def _quitar_lanzador(nombre):
    """Quita su comando de la terminal, solo si lo escribió Workspace (install.is_workspace_launcher): el archivo de
    ~/.local/bin y, en Windows, su función en workspace-cmds.ps1. Jamás el del hub. → lo quitado."""
    n = str(nombre or "").strip().lower()
    if not n or n == "workspace" or not _escritura_global_permitida():
        return []
    import install
    hechos = []
    propio = os.path.join(install.HOME, ".local", "bin", n + (".cmd" if install.IS_WIN else ""))
    try:
        if install.is_workspace_launcher(propio):
            os.remove(propio)
            hechos.append(propio)
    except OSError:
        pass
    if install.IS_WIN:
        ps1 = os.path.join(install.HOME, ".claude", "workspace-cmds.ps1")
        try:
            with open(ps1, encoding="utf-8") as fh:
                lineas = fh.read().splitlines()
            quedan = [ln for ln in lineas if not ln.startswith("function %s " % n)]
            if len(quedan) != len(lineas):
                install.write_text(ps1, "".join(ln + "\n" for ln in quedan))
                hechos.append(ps1)
        except OSError:
            pass
    return hechos


def _poner_lanzador(nombre):
    try:
        import install
        install.install_launchers([nombre])
        return True
    except Exception:
        return False


def _rutas_tema(nombre):
    import agent_admin
    d = agent_admin.themes_local_dir()
    return os.path.join(d, "themes.local.json"), os.path.join(d, "themes-cc", "%s.json" % nombre)


def _json(p):
    try:
        with open(p, encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _escribir_json(p, d):
    import agent_admin
    return agent_admin._atomic_write_json(p, d)


def _quitar_tema(nombre):
    """(su entrada de themes.local.json, el texto de su themes-cc) y los quita de ahí: quedan en la ficha."""
    temas_p, cc_p = _rutas_tema(nombre)
    entrada, texto = None, None
    temas = _json(temas_p)
    if temas is not None and nombre in temas:
        entrada = temas.pop(nombre)
        if not _escribir_json(temas_p, temas):
            entrada = None
    try:
        with open(cc_p, encoding="utf-8") as fh:
            texto = fh.read()
        os.remove(cc_p)
    except OSError:
        texto = None if not os.path.exists(cc_p) else texto
    return entrada, texto


def _poner_tema(nombre, entrada, texto):
    temas_p, cc_p = _rutas_tema(nombre)
    if entrada is not None:
        temas = _json(temas_p) or {}
        if nombre not in temas:
            temas[nombre] = entrada
            _escribir_json(temas_p, temas)
    if texto is not None:
        try:
            os.makedirs(os.path.dirname(cc_p), exist_ok=True)
            with open(cc_p, "w", encoding="utf-8") as fh:      # el suyo, tal cual (también uno editado a mano)
                fh.write(texto)
        except OSError:
            pass


def _quitar_ruta_local(nombre):
    """Su ruta local de paths.local.json, o None (brain_resolver: el único que toca ese mapa)."""
    import brain_resolver
    return brain_resolver.quitar_ruta_local(nombre)


def _poner_ruta_local(nombre, valor):
    import brain_resolver
    brain_resolver.poner_ruta_local(nombre, valor)


def quitar(agent_id, expected_brain=None):
    """Lo desregistra en esta computadora (registro, ruta local, comando de la terminal y tema). Su carpeta NUNCA se
    borra: el aviso dice dónde se queda."""
    with _callado():
        return _quitar(agent_id, expected_brain)


def _quitar(agent_id, expected_brain):
    import agent_manage
    a, e = _actual(agent_id, expected_brain)
    if a is None:
        return _err(e)
    nombre = a["name"]
    ficha = _ficha(a, QUITADO)
    if not _guardar(ficha):
        return _err(_t("apartar.err.guardar", "No pude guardar su ficha: no cambié nada."))
    try:
        if expected_brain is None:
            r = agent_manage.unregister(agent_id)
        else:
            r = agent_manage.unregister(agent_id, expected_brain=expected_brain)
    except Exception as ex:
        r = _err("%s: %s" % (type(ex).__name__, ex))
    if not isinstance(r, dict) or not r.get("ok"):
        _olvidar(nombre)
        return r if isinstance(r, dict) else _err(r)
    if ficha["equipo"]:                               # el quitar de siempre lo ocultó (viene del registro del equipo)
        _invalidar()
        return _ok(r.get("msg") or "", deshacer=nombre, donde=ficha["brain"], modo=QUITADO)
    for clave, fn in (("lanzador", _quitar_lanzador), ("ruta_local", _quitar_ruta_local)):
        try:
            ficha[clave] = fn(nombre)
        except Exception:
            ficha[clave] = None
    try:
        ficha["tema"], ficha["tema_cc"] = _quitar_tema(nombre)
    except Exception:
        ficha["tema"], ficha["tema_cc"] = None, None
    _guardar(ficha)
    _invalidar()
    return _ok(_t("apartar.quitado", "Quité a {n} de Workspace en esta computadora. Su carpeta se queda en {p}.",
                  n=ficha["display"], p=ruta_corta(ficha["brain"]) or "?"),
               deshacer=nombre, donde=ficha["brain"], modo=QUITADO)


# ── traerlo de vuelta ─────────────────────────────────────────────────────────
def _reponer(ficha):
    """Vuelve a escribir su entrada del registro tal cual estaba, exista o no su carpeta (así estaba registrado)."""
    import agentsreg
    nombre = ficha["name"]
    entrada = dict(ficha.get("entrada") or {"name": nombre, "brain": ficha.get("brain") or ""})
    data = agentsreg.read_local()
    data["agents"] = [x for x in data.get("agents", [])
                      if not (isinstance(x, dict) and str(x.get("name", "")).strip().lower() == nombre)] + [entrada]
    return agentsreg._write_local(data)


def _misma(a, b):
    n = lambda p: os.path.normcase(os.path.realpath(os.path.expanduser(str(p or ""))))  # noqa: E731
    return bool(a) and bool(b) and n(a) == n(b)


def volver(nombre):
    """Trae de vuelta a un archivado (o deshace un quitar): queda como estaba."""
    with _callado():
        return _volver(nombre)


def _volver(nombre):
    import agent_manage
    n = str(nombre or "").strip().lower()
    ficha = _buscar(n)
    if ficha is None:
        return _err(_t("apartar.err.no_esta", "No encuentro a {n} entre los archivados.", n=nombre))
    visible, cerebro = ficha.get("display") or n, ficha.get("brain") or ""
    if ficha.get("equipo"):
        if not ficha.get("oculto"):
            r = agent_manage.set_hidden(n, False)
            if not r.get("ok"):
                return r
    else:
        ya = _entrada(n)
        if ya is not None and not _misma(ya.get("brain"), cerebro):
            return _err(_t("apartar.err.otro", "Ya hay otro agente llamado {n} en esta computadora: no lo pisé. El "
                                               "archivado sigue guardado.", n=visible))
        if ya is None:
            puesto = False
            if ficha.get("modo") == QUITADO and cerebro and os.path.isdir(cerebro):
                try:                                  # lo de siempre al cargar: registro, cableado y su comando
                    import agent_admin
                    puesto = bool(agent_admin.load(cerebro, name=n, out=lambda *_a, **_k: None)[0])
                except Exception:
                    puesto = False
            if not puesto and not _reponer(ficha):
                return _err(_t("apartar.err.volver", "No pude traerlo de vuelta: el registro no se dejó escribir."))
        if ficha.get("modo") == QUITADO:
            if ficha.get("lanzador") and not os.path.isdir(cerebro):
                _poner_lanzador(n)
            _poner_tema(n, ficha.get("tema"), ficha.get("tema_cc"))
            if ficha.get("ruta_local") is not None:
                _poner_ruta_local(n, ficha["ruta_local"])
            if ficha.get("oculto") and not _oculto(n):
                agent_manage._set_hidden(agent_manage._hidden() + [n])
    _olvidar(n)
    _invalidar()
    msg = _t("apartar.volvio", "{n} está de vuelta.", n=visible)
    if not ficha.get("equipo") and not (cerebro and os.path.isdir(cerebro)):
        msg += " " + _t("apartar.volvio.sin_carpeta", "Su carpeta todavía no está en esta computadora ({p}): cuando "
                                                      "termine de sincronizar, queda listo.",
                        p=ruta_corta(cerebro) or "?")
    return _ok(msg, nombre=n)


def deshacer(nombre):
    """El «Deshacer» de archivar y de quitar: lo mismo que traerlo de vuelta."""
    return volver(nombre)


# ── los casos de borde: se avisan, no bloquean ────────────────────────────────
def _con_sesion(a):
    """Los nombres de sus sesiones abiertas ahora (las corridas vivas de su cerebro) o de su trabajo en curso."""
    out = []
    cerebro = a.get("brain") or ""
    if cerebro:
        try:
            import pending_runs
            for rec in pending_runs.pending(cerebro):
                if pending_runs.proc_alive(rec):
                    tab = str(rec.get("tab") or "") or _t("apartar.sesion.sin_nombre", "una sesión")
                    if tab not in out:
                        out.append(tab)
        except Exception:
            pass
    for modulo, etiqueta in (("agent_create_job", _t("apartar.job.crear", "se está creando")),
                             ("agent_load_job", _t("apartar.job.cargar", "se está conectando"))):
        try:
            j = getattr(sys.modules.get(modulo) or __import__(modulo), "_JOB", None)
        except Exception:
            j = None
        if isinstance(j, dict) and not j.get("done"):
            suyos = [str(j.get("name") or "").lower()] + [str(x).lower() for x in (j.get("nombres") or ())]
            if a.get("name") in suyos:
                out.append(etiqueta)
    return out


def _coordina_a(nombre):
    """Los otros agentes registrados a los que `nombre` les mandó encargos por el bus (messages): quien coordina."""
    try:
        import agentsreg
        import messages
        registrados = {a["name"] for a in agentsreg.agents()}
        out = []
        for m in messages.all_messages(limit=400):
            para = str(m.get("to") or "").lower()
            if str(m.get("from") or "").lower() == nombre and m.get("type") in ("encargo", "handoff") \
                    and para != nombre and para in registrados and para not in out:
                out.append(para)
        return sorted(out)
    except Exception:
        return []


def _visible(nombre):
    try:
        import agent_state
        a = agent_state.snapshot().find(nombre)
        return (a or {}).get("display") or str(nombre).capitalize()
    except Exception:
        return str(nombre).capitalize()


def _lista(nombres):
    nombres = list(nombres)
    if len(nombres) <= 1:
        return "".join(nombres)
    return ", ".join(nombres[:-1]) + " " + _t("apartar.y", "y") + " " + nombres[-1]


def avisos(agent_id, actual=None, snap=None):
    """Lo que conviene saber antes de archivar o quitar a ese agente: [{clave, texto}] (CLAVES). Ninguno bloquea."""
    try:
        import agent_state
        snap = snap or agent_state.snapshot()
        a = snap.find(agent_id)
    except Exception:
        return []
    if a is None:
        return []
    nombre, visible = a["name"], a.get("display") or a["name"].capitalize()
    actual = str(actual if actual is not None else os.environ.get("WORKSPACE_AGENT_NAME") or "").strip().lower()
    out = []
    if actual and actual in (nombre, a.get("id")):
        out.append(("actual", _t("apartar.aviso.actual", "Estás hablando con {n} ahora: la conversación abierta "
                                                         "sigue, pero deja de verse en las listas.", n=visible)))
    if len(snap.registered(include_hidden=True)) <= 1:
        out.append(("ultimo", _t("apartar.aviso.ultimo", "Es tu único agente: el hub queda vacío hasta que lo traigas "
                                                         "de vuelta o agregues otro.")))
    ses = _con_sesion(a)
    if ses:
        out.append(("sesion", _t("apartar.aviso.sesion", "Tiene algo abierto ahora ({s}): no se cierra ni se "
                                                         "pierde, solo deja de verse en las listas.",
                                 s=_lista(ses[:3]))))
    otros = _coordina_a(nombre)
    if otros:
        out.append(("coordina", _t("apartar.aviso.coordina", "{n} coordina a otros agentes: les manda encargos a {a}. "
                                                             "Sin él, esos encargos se quedan sin quien los reciba.",
                                   n=visible, a=_lista(_visible(x) for x in otros[:4]))))
    if a.get("status") in _A_MEDIAS:
        out.append(("a_medias", _t("apartar.aviso.a_medias", "Su carpeta no está completa en esta computadora (puede "
                                                             "que falte sincronizar): no se toca.")))
    return [{"clave": k, "texto": t} for k, t in out]


def leer(actual=None):
    """Lo que enseñan el hub y la página: {"archivados": [...], "avisos": {nombre: [...]}}."""
    out = {"archivados": archivados(), "avisos": {}}
    try:
        import agent_state
        snap = agent_state.snapshot()
        for a in snap.registered(include_hidden=True):
            out["avisos"][a["name"]] = avisos(a["name"], actual=actual, snap=snap)
    except Exception:
        pass
    return out


def main(argv=None):
    """`python3 agente_apartar.py lista|archivar <n>|quitar <n>|volver <n>`: para probarlo desde la terminal."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] == "lista":
        print(json.dumps(leer(), ensure_ascii=False, indent=2))
        return 0
    if len(args) == 2 and args[0] in ("archivar", "quitar", "volver"):
        r = {"archivar": archivar, "quitar": quitar, "volver": volver}[args[0]](args[1])
        print(("✓ " + r["msg"]) if r.get("ok") else ("✗ " + str(r.get("error"))))
        return 0 if r.get("ok") else 1
    print(main.__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
