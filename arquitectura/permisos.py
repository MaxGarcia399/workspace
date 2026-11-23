#!/usr/bin/env python3
"""WORKSPACE · arquitectura/permisos — los permisos de la sesión desde lo que eliges en Workspace (F7).

La autonomía del agente (`autonomy` en <cerebro>/.workspace/agent.json) es un nivel:

  · «brain»   → auto (de fábrica, «Automático»; decisión del dueño 18-nov): el modo automático OFICIAL del
                motor, el que revisa cada paso y pregunta lo arriesgado (Claude Code `--permission-mode auto`).
                Si el motor no lo tiene, queda en «editar sin preguntar» y se dice;
  · «ask»     → preguntar: pregunta antes de editar y antes de correr comandos;
  · «edit»    → editar sin preguntar (en su cerebro); los comandos preguntan;
  · «sandbox» → sin permisos: edita y corre comandos sin preguntar, pero SOLO dentro del sandbox oficial del
                motor (sin red y solo en la carpeta). Si el motor no tiene sandbox (o no en este sistema), queda
                en «editar sin preguntar» y se dice.

Cada ficha dice en `permisos.niveles` cómo es cada nivel con las opciones de sesión de su motor: argumentos,
ajustes de la sesión (se juntan con el `--settings` que ya traiga el lanzador, en un archivo del estado de
Workspace) o entorno de la corrida (un JSON que se junta con el que ya esté). Lo que el lanzador de hoy ya pone
para un nivel (p. ej. el `--permission-mode` de Claude Code, que respeta el `defaultMode` del socio) se deja.
Nunca bypassPermissions, `--dangerously-*`, `--yolo` ni un «aprobar todo»; nada en la config global. El modo auto
oficial sí (AUTO_OFICIAL: el de Claude Code y su equivalente en Antigravity). Stdlib.
"""
import hashlib
import json
import os
import re
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ_REPO = os.path.dirname(AQUI)
if RAIZ_REPO not in sys.path:
    sys.path.insert(0, RAIZ_REPO)

NIVELES = ("auto", "preguntar", "editar", "sin_permisos")
#: La autonomía guardada → el nivel. «brain» es la de fábrica (lo que guarda cada agente al crearse): «Automático».
#: «full» (comandos sin preguntar) se retiró: se lee como «brain».
DE_AUTONOMIA = {"brain": "auto", "full": "auto", "ask": "preguntar", "edit": "editar", "sandbox": "sin_permisos"}
#: Lo que nunca sale de aquí, en ningún motor (y la prueba lo vigila en las 9 fichas). Un «auto» suelto también
#: (`--auto` de OpenCode, aprobar todo), salvo el modo auto oficial de AUTO_OFICIAL.
PROHIBIDO = re.compile(r"bypassPermissions|--dangerously|--yolo|--allow-all|--trust-all|--force\b|^--auto$|"
                       r"^auto$|--permission-mode[= ]auto$")
#: El modo automático oficial que sí puede salir (decisión del dueño, 18-nov): el de Claude Code
#: (`--permission-mode auto`, su clasificador) y su equivalente en Antigravity (`--mode auto`). Solo esa
#: bandera con ese valor; `--permission-mode bypassPermissions` y cualquier otro «auto» siguen prohibidos.
AUTO_OFICIAL = ("--permission-mode", "--mode")
#: Las banderas del modo automático de cada motor (las que pone su lanzador con «Automático»): Cursor y Copilot.
#: Regla del dueño (18-nov): un agente en «sandbox» (uno que trabaja solo) NUNCA va en automático; si una
#: llega a su argv (el comando del socio, un lanzador), se quita (sin_auto).
BANDERAS_AUTO = ("--auto-review", "--assisted-approval")


def sin_auto(argv):
    """argv sin el modo automático: `--permission-mode auto`/`--mode auto` (y su forma con «=»), bypassPermissions
    y BANDERAS_AUTO. → (argv, [lo que quitó])."""
    out, quitado, saltar = [], [], False
    for i, a in enumerate(argv):
        if saltar:
            saltar = False
            continue
        if i and a in AUTO_OFICIAL and argv[i + 1:i + 2] and argv[i + 1] in ("auto", "bypassPermissions"):
            quitado += [a, argv[i + 1]]
            saltar = True
            continue
        if i and (a in BANDERAS_AUTO or any(a in ("%s=auto" % f, "%s=bypassPermissions" % f) for f in AUTO_OFICIAL)):
            quitado.append(a)
            continue
        out.append(a)
    return out, quitado


def nivel(cerebro):
    """El nivel que eligió el socio para el agente de este cerebro («auto», el de fábrica, si no dice nada)."""
    try:
        with open(os.path.join(str(cerebro), ".workspace", "agent.json"), encoding="utf-8") as fh:
            v = str((json.load(fh) or {}).get("autonomy") or "").strip().lower()
    except (OSError, ValueError, AttributeError):
        v = ""
    return DE_AUTONOMIA.get(v, "auto")


def _sistema():
    import skill_meta
    return skill_meta.current_os()


def _junta(a, b):
    """b encima de a: los dicts por dentro; las listas se suman sin repetir."""
    if isinstance(a, dict) and isinstance(b, dict):
        out = dict(a)
        for k, v in b.items():
            out[k] = _junta(a.get(k), v) if k in a else v
        return out
    if isinstance(a, list) and isinstance(b, list):
        return a + [x for x in b if x not in a]
    return b


def _valor_de(argv, flag):
    """(índice, forma, valor) de `flag` en argv («--f v» o «--f=v»), o (-1, '', '')."""
    for i, a in enumerate(argv):
        if a == flag and i + 1 < len(argv):
            return i, "dos", argv[i + 1]
        if a.startswith(flag + "="):
            return i, "igual", a.split("=", 1)[1]
    return -1, "", ""


def _sin(argv, flag):
    i, forma, _v = _valor_de(argv, flag)
    if i < 0:
        return argv
    return argv[:i] + argv[i + (2 if forma == "dos" else 1):]


def _carpeta_ajustes():
    import paths
    return os.path.join(paths.state_dir(), "arquitectura", "ajustes")


def _con_ajustes(argv, ajustes):
    """Junta `ajustes` con el `--settings` que ya traiga el argv (un archivo o JSON en línea) y deja UNO, en un
    archivo del estado de Workspace (no del motor ni del cerebro). Levanta si el de antes no se puede leer: no
    se pisa lo que el lanzador puso (la bóveda, los hooks)."""
    i, _forma, v = _valor_de(argv, "--settings")
    base = {}
    if i >= 0:
        texto = v
        if not v.lstrip().startswith("{"):
            with open(v, encoding="utf-8") as fh:
                texto = fh.read()
        base = json.loads(texto)
        if not isinstance(base, dict):
            raise ValueError("--settings no es un objeto")
    junto = _junta(base, ajustes)
    crudo = json.dumps(junto, ensure_ascii=False, sort_keys=True, indent=2)
    ruta = os.path.join(_carpeta_ajustes(), hashlib.sha1(crudo.encode("utf-8")).hexdigest()[:16] + ".json")
    if not os.path.isfile(ruta):
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        tmp = "%s.%d.tmp" % (ruta, os.getpid())
        with open(tmp, "w", encoding="utf-8") as fh:
            fh.write(crudo + "\n")
        os.replace(tmp, ruta)
    return _sin(argv, "--settings")[:1] + ["--settings", ruta] + _sin(argv, "--settings")[1:]


def _auto_oficial(t, previo):
    """¿`t` es el modo auto oficial (AUTO_OFICIAL): «auto» justo tras su bandera, o «--bandera=auto»?"""
    if t == "auto":
        return previo in AUTO_OFICIAL
    return any(t in ("%s=auto" % f, "%s auto" % f) for f in AUTO_OFICIAL)


def revisar(*cosas):
    """Levanta si algo (argumentos, ajustes o entorno) lleva un permiso prohibido. El modo auto oficial
    (AUTO_OFICIAL) pasa; todo lo demás de PROHIBIDO, no."""
    for c in cosas:
        textos = [c] if isinstance(c, str) else [json.dumps(c, ensure_ascii=False)] if isinstance(c, dict) else c
        previo = ""
        for t in textos:
            t = str(t)
            if PROHIBIDO.search(t) and not _auto_oficial(t, previo):
                raise ValueError("permiso prohibido: %s" % t)
            previo = t


def aplicar(motor, cerebro, argv, env, valores, ficha=None):
    """(argv, env, info) con el nivel del socio, según `permisos.niveles` de la ficha. Sin niveles en la ficha:
    nada cambia. info = {nivel, pedido, aplicado, motivo}."""
    if ficha is None:
        from arquitectura import contrato
        ficha = contrato.ficha(motor)
    from arquitectura import nucleo
    argv, env = list(argv), dict(env)
    pedido = nivel(cerebro)
    info = {"nivel": pedido, "pedido": pedido, "aplicado": False, "motivo": ""}
    if pedido == "sin_permisos":
        # el sandbox manda sobre el auto: ni el del lanzador ni el del comando (regla del dueño, 18-nov)
        argv, quitado = sin_auto(argv)
        if quitado:
            info["sin_auto"] = quitado
    niveles = (ficha.get("permisos") or {}).get("niveles") or {}
    if not niveles:
        info["motivo"] = "su ficha no trae niveles por sesión"
        return argv, env, info
    n = pedido
    cfg = niveles.get(n) or {}
    if n == "auto" and cfg.get("no_se_usa"):
        # el motor no tiene ese modo en este camino (Copilot en su terminal): queda en editar, y se dice con su prueba
        info["motivo"] = info["no_se_usa"] = cfg["no_se_usa"]
        n, cfg = "editar", niveles.get("editar") or {}
    elif n == "auto" and ("no" in cfg or not cfg):
        # sin modo automático oficial: «editar sin preguntar», lo de antes del 18-nov
        info["motivo"] = cfg.get("no") or "su ficha no trae modo automático"
        n, cfg = "editar", niveles.get("editar") or {}
    if n == "sin_permisos" and ("no" in cfg or _sistema() not in (cfg.get("sandbox_os") or (_sistema(),))):
        info["motivo"] = cfg.get("no") or "sin sandbox del motor en este sistema"
        n, cfg = "editar", niveles.get("editar") or {}
    info["nivel"] = n
    # lo que pone el lanzador de hoy y este nivel reemplaza (si es del socio, gana el suyo)
    for flag, suyos in (cfg.get("reemplaza") or {}).items():
        i, _f, v = _valor_de(argv, flag)
        if i >= 0 and v not in suyos:
            info["motivo"] = "el socio fijó %s %s" % (flag, v)
            return argv, env, info
        argv = _sin(argv, flag)
    extra = [nucleo.poner(a, valores) for a in cfg.get("argv") or ()]
    extra = [a for a in extra if a not in argv]
    ajustes = nucleo.poner(cfg.get("ajustes") or {}, valores)
    entorno = {}
    for k, v in (cfg.get("env") or {}).items():
        v = nucleo.poner(v, valores)
        try:
            antes, nuevo = json.loads(env.get(k) or "{}"), json.loads(v)
            entorno[k] = json.dumps(_junta(antes, nuevo), ensure_ascii=False, separators=(",", ":")) \
                if isinstance(antes, dict) and isinstance(nuevo, dict) else v
        except ValueError:
            entorno[k] = v
    revisar(extra, ajustes, entorno)
    argv = argv[:1] + extra + argv[1:]
    if ajustes:
        argv = _con_ajustes(argv, ajustes)
    env.update(entorno)
    info["aplicado"] = bool(extra or ajustes or entorno)
    bandera = [nucleo.poner(a, valores) for a in cfg.get("bandera") or ()]
    if bandera and not info["aplicado"]:
        # cierre de la auditoría (19-nov): ese nivel lo pone el lanzador del motor ANTES de esto (Claude Code
        # `--permission-mode auto`, Cursor `--auto-review`, Antigravity `--mode auto`): se comprueba que esté
        if _seguidas(argv, bandera):
            info.update(aplicado=True, por="lanzador", motivo="lo puso su lanzador: %s" % " ".join(bandera))
        else:
            _i, _f, v = _valor_de(argv, bandera[0])
            if _i >= 0 and len(bandera) > 1 and v != bandera[1]:
                info["motivo"] = "el socio fijó %s %s" % (bandera[0], v)
    return argv, env, info


def _seguidas(argv, bandera):
    """¿`bandera` está en argv, seguida («--f v») o en su forma «--f=v»?"""
    argv = [str(a) for a in argv]
    n = len(bandera)
    if any(argv[i:i + n] == list(bandera) for i in range(len(argv) - n + 1)):
        return True
    return n == 2 and "%s=%s" % tuple(bandera) in argv
