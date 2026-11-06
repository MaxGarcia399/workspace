"""AUTOMÁTICA: lo que una versión anterior de Workspace dejó en la config global
de Kiro (`~/.kiro`, o la carpeta de KIRO_HOME) se quita. Todo lo de Workspace
para Kiro vive ahora en el cerebro: el agente `workspace` en
`<cerebro>/.kiro/agents/workspace.json` (doc «custom agents» de Kiro, agentes
del proyecto), que se rehace al abrir cada pestaña.

Qué quita, SOLO si es de Workspace:
  · `~/.kiro/agents/workspace.json`, el agente GLOBAL de una versión anterior
    (aprobaba la memoria por la ruta de un comando). Se reconoce por la marca
    «WORKSPACE ·» de su `description`; uno del socio con ese nombre, o un
    enlace, no se toca. Se respalda antes de borrarlo.
  · los segmentos de la barra (uso y créditos) que prendió Workspace en
    `~/.kiro/settings/cli.json`, según SU propio registro en el estado de
    Workspace (`kiro-statusline.json`) y solo si siguen prendidos: lo que el
    socio prendió o apagó él, y cualquier otra clave, quedan. Se respalda el
    archivo antes de escribirlo. Si los quieres, se prenden en `/settings
    display` de Kiro (lo que documenta Kiro); `workspace migrate --undo <id>`
    devuelve el archivo tal cual estaba si nadie lo cambió después.

Idempotente y TOLERANTE: un archivo ilegible, un enlace o un error se anotan y
la cola sigue (nunca lanza); lo que no se pudo quitar queda anotado y lo
intenta el desinstalador. Compatible hacia atrás: el registro de lo que se
prendió se conserva (sin la parte de «prendido por Workspace»), así una
versión anterior no vuelve a prender nada; y esa versión rehace su propio
agente global si la necesita. Rápida y sin red: no corre el binario de Kiro.
"""
import hashlib
import json
import os
import shutil

TITLE = {"es": "Kiro: Workspace ya no deja nada en tu config global de Kiro (~/.kiro)",
         "en": "Kiro: Workspace no longer leaves anything in your global Kiro config (~/.kiro)"}
KIND = "auto"
MID = "202611052341_kiro_config_en_el_cerebro"
#: El agente global y su marca (fijos: una migración publicada no cambia).
AGENTE = "workspace.json"
MARCA = "WORKSPACE ·"


def _kiro():
    from engines import kiro
    return kiro


def _bdir(ctx):
    return os.path.join(ctx.state_dir, "backups", MID)


def _agente_viejo(ctx):
    """Ruta del agente global de Workspace (archivo normal con su marca), o None."""
    try:
        p = os.path.join(_kiro()._kiro_dir(home=ctx.home), "agents", AGENTE)
        if os.path.islink(p) or not os.path.isfile(p):
            return None
        with open(p, encoding="utf-8-sig") as fh:
            data = json.load(fh)
        ok = isinstance(data, dict) and str(data.get("description") or "").startswith(MARCA)
        return p if ok else None
    except (OSError, ValueError, ImportError):
        return None


def _barras(ctx):
    """{config de Kiro: {clave: [segmentos]}} anotados como prendidos por Workspace."""
    try:
        return _kiro().statusline_de_workspace(home=ctx.home)
    except Exception:
        return {}


def needed(ctx):
    return bool(_agente_viejo(ctx) or _barras(ctx))


def _leer(path):
    """dict de un archivo JSON normal; None si no se puede (o es un enlace)."""
    if os.path.islink(path) or not os.path.isfile(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def _sha(path):
    try:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()
    except OSError:
        return ""



def _reemplazar(tmp, path):
    """os.replace con los reintentos de Windows (antivirus, Kiro u Obsidian con
    el archivo abierto: WinError 5/32); si no se logra, borra el temporal y
    relanza (el paso lo anota y la cola sigue)."""
    try:
        import atomico
    except ImportError:
        os.replace(tmp, path)
        return
    atomico.reemplazar(tmp, path)

def _escribir(path, data):
    """Escritura atómica (tmp + os.replace), con el mismo modo del archivo."""
    try:
        mode = os.stat(path).st_mode & 0o777
    except OSError:
        mode = 0o600
    tmp = "%s.tmp-%d" % (path, os.getpid())
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    try:
        os.chmod(tmp, mode)
    except OSError:
        pass
    _reemplazar(tmp, path)


def _respaldo(ctx, path, nombre):
    """Copia `path` al respaldo de esta migración (sin pisar uno anterior)."""
    d = _bdir(ctx)
    os.makedirs(d, exist_ok=True)
    dest, n = os.path.join(d, nombre), 1
    while os.path.exists(dest):
        n += 1
        dest = os.path.join(d, "%s.%d" % (nombre, n))
    shutil.copy2(path, dest)
    return dest


def _deshacer_path(ctx):
    return os.path.join(_bdir(ctx), "deshacer.json")


def _leer_deshacer(ctx):
    data = _leer(_deshacer_path(ctx))
    return data if isinstance(data, dict) else {}


def _anotar_deshacer(ctx, sp, respaldo, sha, segs):
    data = _leer_deshacer(ctx)
    data[sp] = {"respaldo": respaldo, "sha256": sha, "prendidos": segs}
    os.makedirs(_bdir(ctx), exist_ok=True)
    tmp = _deshacer_path(ctx) + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=1)
    _reemplazar(tmp, _deshacer_path(ctx))


def _quitar_agente(ctx):
    p = _agente_viejo(ctx)
    if not p:
        return
    if ctx.dry_run:
        ctx.log("Kiro: quitaría el agente global de Workspace %s" % p)
        return
    try:
        dest = _respaldo(ctx, p, "agents__" + AGENTE)
        os.remove(p)
        try:
            os.rmdir(os.path.dirname(p))          # solo si quedó vacía
        except OSError:
            pass
        ctx.log("Kiro: quité el agente global de Workspace %s (respaldo en %s); el de "
                "Workspace vive ahora en cada cerebro." % (p, dest))
    except OSError as e:
        ctx.log("Kiro: no pude quitar %s (%s); queda para el desinstalador." % (p, e))


def _quitar_barra(ctx, sp, segs):
    kiro = _kiro()
    if not os.path.lexists(sp):
        if not ctx.dry_run:
            kiro.olvidar_statusline(sp, home=ctx.home)     # ya no hay nada que quitar
        return
    data = _leer(sp)
    if data is None:
        ctx.log("Kiro: %s ilegible o es un enlace; no lo toqué." % sp)
        return
    new, quito = kiro.clean_statusline(data, segs)
    if ctx.dry_run:
        if quito:
            ctx.log("Kiro: quitaría de %s los segmentos de la barra que prendió Workspace" % sp)
        return
    if quito:
        try:
            dest = _respaldo(ctx, sp, "settings__cli.json")
            _escribir(sp, new)
            _anotar_deshacer(ctx, sp, dest, _sha(sp), segs)
        except (OSError, TypeError, ValueError) as e:
            ctx.log("Kiro: no pude quitar la barra de %s (%s); queda para el desinstalador."
                    % (sp, e))
            return
        ctx.log("Kiro: quité de su barra el uso y los créditos que había prendido Workspace "
                "(%s); si los quieres, préndelos en /settings display de Kiro." % sp)
    kiro.olvidar_statusline(sp, home=ctx.home)


def run(ctx):
    try:
        _quitar_agente(ctx)
    except Exception as e:                        # nada traba la cola
        ctx.log("Kiro: agente global sin tocar (%s: %s)" % (type(e).__name__, e))
    for sp, segs in sorted(_barras(ctx).items()):
        try:
            _quitar_barra(ctx, sp, segs)
        except Exception as e:
            ctx.log("Kiro: %s sin tocar (%s: %s)" % (sp, type(e).__name__, e))


def undo(ctx):
    """`workspace migrate --undo <id>`: devuelve cada `cli.json` de Kiro tal cual
    estaba, SOLO si nadie lo cambió desde la migración (mismo sha256), y vuelve
    a anotar esos segmentos como de Workspace (así el desinstalador los quita).
    El agente global no se restaura: aprobaba la memoria por la ruta de un
    comando, el hueco que esta versión cierra. → [(archivo, estado, mensaje)]."""
    out = []
    data = _leer_deshacer(ctx)
    kiro = _kiro()
    for sp, info in sorted(data.items()):
        if not isinstance(info, dict):
            continue
        bak, sha = str(info.get("respaldo") or ""), str(info.get("sha256") or "")
        if not (bak and os.path.isfile(bak)):
            out.append((sp, "refused", "no está el respaldo"))
            continue
        if _sha(sp) != sha:
            out.append((sp, "refused", "cambió después de la migración: no se pisa"))
            continue
        try:
            tmp = "%s.tmp-%d" % (sp, os.getpid())
            shutil.copy2(bak, tmp)
            _reemplazar(tmp, sp)
            st = kiro._read_state(ctx.home)
            pr = st.get("prendidos") if isinstance(st.get("prendidos"), dict) else {}
            st["prendidos"] = dict(pr, **{sp: info.get("prendidos") or {}})
            path = kiro._state_path(ctx.home)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path + ".tmp", "w", encoding="utf-8") as fh:
                json.dump(st, fh, indent=1)
            _reemplazar(path + ".tmp", path)
        except (OSError, ValueError, TypeError) as e:
            out.append((sp, "refused", "%s: %s" % (type(e).__name__, e)))
            continue
        del data[sp]
        out.append((sp, "undone", "restaurado"))
    try:
        if data:
            with open(_deshacer_path(ctx) + ".tmp", "w", encoding="utf-8") as fh:
                json.dump(data, fh, ensure_ascii=False, indent=1)
            _reemplazar(_deshacer_path(ctx) + ".tmp", _deshacer_path(ctx))
        elif os.path.exists(_deshacer_path(ctx)):
            os.remove(_deshacer_path(ctx))
    except OSError:
        pass
    return out
