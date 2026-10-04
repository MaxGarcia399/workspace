#!/usr/bin/env python3
"""workflows.steps.spec — pasos det del META-HARNESS (workflows que crean
workflows). Envuelven el runner que ya existe (load_spec/validate_spec/start)
— no reinventan validación ni ejecución:

  · validate          — el ORÁCULO central: ¿el spec objetivo carga y valida?
  · classify_frontier — la FRONTERA composición-vs-primitiva: ¿la tarea pide
                        un paso det que NO existe? (primitiva nueva = trabajo
                        de código con revisión, no de composición).
  · smoke             — ensayo end-to-end: el spec objetivo valida Y planea
                        completo en --dry (sin ejecutar nada real). Verde
                        SOLO si el dry terminó DONE; el run-record del
                        ensayo se borra (no ensucia `wf runs`).
  · scaffold          — andamia el esqueleto guiado en CUARENTENA
                        (`specs/_pending/<target>.json`) — idempotente: si
                        ya existe, no-op verde (invariante 4).
  · promote           — el gate humano aprobó → mueve el spec de `_pending/`
                        a `specs/` (recién ahí es descubrible/corrible).
  · discoverable      — el spec objetivo quedó REGISTRADO (catálogo) y
                        DESCUBRIBLE (sus triggers lo empatan) — la fuga #1:
                        un workflow inencontrable es como si no existiera.

CUARENTENA (client-safe): un spec autorado NO debe quedar corrible ANTES del
gate humano. Por eso `scaffold` (y `componer`, aguas arriba) trabajan sobre
`specs/_pending/` — `wf run`/`list`/`match` solo miran archivos `.json`
directos en SPECS_DIR, así que un spec en cuarentena NO existe para ellos.
`validate`/`smoke` resuelven vía `_load_target` (primero _pending, luego
specs/) para poder verificar el spec DURANTE el run; `promote` es el único
camino de _pending → specs/, y corre DESPUÉS del gate `aprobar-scope`.

Import LAZY de `workflows` DENTRO de cada función: steps es submódulo de
workflows y el import a nivel de módulo sería circular.
"""
import json
import os


def _target(ctx, step):
    """Spec objetivo, en orden de precedencia: `target` del paso →
    `--param target_spec=` → `--param spec=`. None si nadie lo indicó."""
    return (step.get("target")
            or (ctx.get("params") or {}).get("target_spec")
            or (ctx.get("params") or {}).get("spec"))


_SIN_TARGET = ("no se indicó el spec objetivo "
               "(--param target_spec=<nombre>)")


# ── cuarentena `specs/_pending/` ────────────────────────────────────────────
def _base(target):
    """Nombre SANEADO del target (basename, sin `.json`) — mismas reglas que
    `load_spec`. ValueError si el nombre no pasa `_ID_RE` (contrato roto)."""
    import workflows
    base = os.path.basename(str(target or ""))
    if base.endswith(".json"):
        base = base[:-5]
    if not base or not base.strip(".") or not workflows._ID_RE.match(base):
        raise ValueError("nombre de spec inválido: %r" % (target,))
    return base


def _pending_dir():
    """`specs/_pending/` — la cuarentena. Es un SUBDIR de SPECS_DIR:
    `list_specs`/`match_specs`/`load_spec` solo miran `*.json` directos, así
    que lo que vive aquí NO es descubrible ni corrible por el runner."""
    import workflows
    return os.path.join(workflows.SPECS_DIR, "_pending")


def _pending_path(target):
    """Ruta del spec objetivo EN cuarentena (target saneado por `_base`)."""
    return os.path.join(_pending_dir(), _base(target) + ".json")


def _load_target(target):
    """Resuelve el spec objetivo respetando la cuarentena: PRIMERO
    `_pending/<target>.json` (autorado, aún sin aprobar), luego
    `specs/<target>.json` (aprobado). Valida con `validate_spec` — el mismo
    oráculo que `load_spec`, cero drift. Devuelve `(spec_dict, path)`;
    FileNotFoundError si no está en ninguno de los dos."""
    import workflows
    for path in (_pending_path(target),
                 os.path.join(workflows.SPECS_DIR, _base(target) + ".json")):
        if os.path.isfile(path):
            with open(path, encoding="utf-8") as fh:
                return workflows.validate_spec(json.load(fh)), path
    raise FileNotFoundError("no existe el spec `%s` (ni en cuarentena "
                            "_pending/ ni en specs/)" % _base(target))


def validate(ctx, step):
    """Paso det: valida el spec objetivo vía `_load_target` (que aplica la
    MISMA validación que el runner — un solo oráculo, cero drift — y resuelve
    la cuarentena: el spec puede estar aún en `_pending/`). Spec roto =
    error de CONTRATO: permanente, reintentar no lo arregla."""
    target = _target(ctx, step)
    if ctx.get("dry"):
        # dry PRIMERO: nada real corre — no-op ok aunque falte el target
        # (p. ej. `wf run <meta> --dry` sin --param)
        return {"ok": True,
                "detail": ("validaría el spec `%s` (dry)" % target
                           if target else "validaría el spec objetivo (dry)")}
    if not target:
        # config rota (nadie dijo QUÉ validar) — permanente, no transitoria
        return {"ok": False, "detail": _SIN_TARGET, "retriable": False}
    try:
        spec, _ = _load_target(target)
    except (ValueError, FileNotFoundError) as e:
        return {"ok": False,
                "detail": "spec `%s` INVÁLIDO: %s" % (target, e),
                "retriable": False,          # contrato roto = PERMANENTE
                "artifacts": {"spec_valid": False,
                              "spec_validation": str(e)}}
    return {"ok": True,
            "detail": "spec `%s` válido: %d pasos"
                      % (target, len(spec.get("steps") or [])),
            "artifacts": {"spec_valid": True, "spec_validation": "ok"}}


def classify_frontier(ctx, step):
    """Paso det: clasifica la frontera composición-vs-primitiva. SIEMPRE ok
    (es una clasificación, no un pass/fail): deja `needs_primitive` +
    `missing_primitives` para que el spec decida aguas abajo (`when:`).

    Candidatos, en orden: (a) el artefacto `descomposicion` (lo produce un
    paso agent `entender`: dict con `pasos` = [{"kind":…, "run":…}, …]); o
    (b) los `steps` del spec objetivo (mismo target que `validate`). Un paso
    det cuyo `run` NO está en el registry (`steps.known()`) es una primitiva
    FALTANTE — trabajo de código con revisión, no de composición."""
    if ctx.get("dry"):
        return {"ok": True, "detail": "clasificaría la frontera (dry)"}
    from workflows import steps as steplib

    candidatos = None
    desc = (ctx.get("artifacts") or {}).get("descomposicion")
    if isinstance(desc, dict) and isinstance(desc.get("pasos"), list):
        candidatos = desc["pasos"]
    else:
        target = _target(ctx, step)
        if target:
            try:
                # _load_target: el spec puede estar aún en cuarentena
                candidatos = _load_target(target)[0].get("steps") or []
            except Exception as e:
                # falla-suave: clasificar no es validar — el oráculo del
                # contrato es `spec.validate`; aquí solo se reporta.
                return {"ok": True,
                        "detail": "no se pudo cargar el spec `%s` para "
                                  "clasificar (%s) — `spec.validate` es el "
                                  "oráculo del contrato" % (target, e),
                        "artifacts": {"needs_primitive": False,
                                      "missing_primitives": []}}
    if candidatos is None:
        return {"ok": True, "detail": "sin pasos candidatos que clasificar",
                "artifacts": {"needs_primitive": False,
                              "missing_primitives": []}}

    conocidos = set(steplib.known())
    faltantes = set()
    for paso in candidatos:
        if not isinstance(paso, dict) or paso.get("kind") != "det":
            continue
        run = paso.get("run")
        if run and run not in conocidos:
            faltantes.add(str(run))
    faltantes = sorted(faltantes)
    if faltantes:
        detail = ("faltan primitivas: %s → escalar, es trabajo de código "
                  "(con revisión), no de composición" % ", ".join(faltantes))
    else:
        detail = "composición pura: todos los pasos det existen"
    return {"ok": True, "detail": detail,
            "artifacts": {"needs_primitive": bool(faltantes),
                          "missing_primitives": faltantes}}


def smoke(ctx, step):
    """Paso det: SMOKE del spec objetivo — `workflows.start(spec, dry=True)`
    (valida + planea end-to-end, sin ejecutar nada real). Resuelve vía
    `_load_target`: el spec puede estar aún en cuarentena (`_pending/`).
    Verde SOLO si el dry terminó DONE — un dry PAUSADO/atorado (p. ej. un
    paso escalado permanente en `waiting_human`) NO es smoke verde. El
    run-record de ensayo que el dry persiste se BORRA al final: el smoke no
    debe ensuciar `wf runs` ni el board."""
    target = _target(ctx, step)
    if ctx.get("dry"):
        # dry PRIMERO: no-op ok aunque falte el target (nada real corre)
        return {"ok": True,
                "detail": ("correría el smoke --dry de `%s` (dry)" % target
                           if target else
                           "correría el smoke --dry del spec objetivo (dry)")}
    if not target:
        return {"ok": False, "detail": _SIN_TARGET, "retriable": False}
    import workflows
    try:
        spec, _ = _load_target(target)
        state = workflows.start(spec, dry=True)
    except Exception as e:
        return {"ok": False,
                "detail": "smoke --dry de `%s` REVENTÓ: %s: %s"
                          % (target, type(e).__name__, e),
                "retriable": False,          # contrato/spec roto = permanente
                "artifacts": {"smoke_ok": False, "smoke_steps": 0}}
    # el dry del runner PERSISTE un run-record de ensayo (y emite N10) —
    # borrarlo best-effort para no dejar un run-fantasma en `wf runs`/board.
    # try/except: la limpieza JAMÁS falla el paso (el veredicto ya está).
    try:
        rid = state.get("run_id")
        if rid:
            os.remove(workflows.run_path(rid))
    except Exception:
        pass
    pasos = state.get("steps") or []
    # verde = el dry COMPLETÓ (status DONE, y solo DONE): un run pausado en
    # un gate escalado queda `paused_human`/`waiting_human` — NO es "fail",
    # pero tampoco es un ensayo end-to-end completo.
    ok = (state.get("status") == workflows.DONE)
    return {"ok": ok,
            "detail": "smoke --dry de `%s`: %d pasos planeados, status %s"
                      % (target, len(pasos), state.get("status")),
            "artifacts": {"smoke_ok": ok, "smoke_steps": len(pasos)}}


def scaffold(ctx, step):
    """Paso det: andamia el spec objetivo EN CUARENTENA — escribe el
    esqueleto guiado (`workflows.skeleton_spec`, que valida ANTES de
    escribir: lo que nace, nace válido) a `specs/_pending/<target>.json`,
    NO a specs/. Un spec sin aprobar no debe ser corrible/descubrible; el
    único camino a specs/ es `spec.promote`, DESPUÉS del gate humano.
    IDEMPOTENTE (invariante 4): ya en _pending → no-op verde; ya PROMOVIDO
    en specs/ → también no-op verde (jamás re-andamia sobre un aprobado)."""
    target = _target(ctx, step)
    if ctx.get("dry"):
        # dry PRIMERO: no-op ok aunque falte el target (nada real corre)
        return {"ok": True,
                "detail": ("andamiaría el spec `%s` (dry)" % target
                           if target else
                           "andamiaría el spec objetivo (dry)")}
    if not target:
        return {"ok": False, "detail": _SIN_TARGET, "retriable": False}
    import workflows
    try:
        base = _base(target)                 # ValueError si el nombre es basura
        ppath = _pending_path(base)
        final = os.path.join(workflows.SPECS_DIR, base + ".json")
        if os.path.exists(ppath):
            # idempotencia: el efecto ya existe — adoptar, no reventar
            return {"ok": True,
                    "detail": "`%s` ya andamiado (en cuarentena _pending/)"
                              % target,
                    "artifacts": {"scaffold_path": ppath}}
        if os.path.exists(final):
            # ya promovido/aprobado: re-andamiar en _pending dejaría una
            # copia que promote (correctamente) rechazaría — no-op verde.
            return {"ok": True,
                    "detail": "`%s` ya existe en specs/ (aprobado) — nada "
                              "que andamiar" % target,
                    "artifacts": {"scaffold_path": final}}
        spec_dict = workflows.validate_spec(workflows.skeleton_spec(base))
        os.makedirs(_pending_dir(), exist_ok=True)
        with open(ppath, "w", encoding="utf-8") as fh:
            json.dump(spec_dict, fh, indent=2, ensure_ascii=False)
            fh.write("\n")
    except Exception as e:
        # nombre inválido / esqueleto roto = contrato, no transitorio
        return {"ok": False,
                "detail": "no se pudo andamiar `%s`: %s: %s"
                          % (target, type(e).__name__, e),
                "retriable": False}
    return {"ok": True,
            "detail": "esqueleto `%s` creado en cuarentena (_pending/)"
                      % target,
            "artifacts": {"scaffold_path": ppath}}


def promote(ctx, step):
    """Paso det: PROMUEVE el spec de la cuarentena a specs/ — el gate humano
    aprobó → mueve `_pending/<target>.json` a `specs/<target>.json`; recién
    ahí el spec es descubrible (`wf list`/`wf match`) y corrible (`wf run`).
    Valida ANTES de mover (a specs/ solo entra lo válido). RECHAZA si
    `specs/<target>.json` YA existe (jamás sobrescribe un spec aprobado).
    IDEMPOTENTE: _pending ya no existe pero specs/ sí → ya promovido, no-op
    verde. dry → no-op."""
    target = _target(ctx, step)
    if ctx.get("dry"):
        # dry PRIMERO: no-op ok aunque falte el target (nada real corre)
        return {"ok": True,
                "detail": ("promovería el spec `%s` de _pending/ a specs/ "
                           "(dry)" % target if target else
                           "promovería el spec objetivo (dry)")}
    if not target:
        return {"ok": False, "detail": _SIN_TARGET, "retriable": False}
    import workflows
    try:
        base = _base(target)
    except ValueError as e:
        return {"ok": False, "detail": str(e), "retriable": False}
    ppath = _pending_path(base)
    final = os.path.join(workflows.SPECS_DIR, base + ".json")
    if not os.path.isfile(ppath):
        if os.path.isfile(final):
            # idempotencia: ya promovido — adoptar, no reventar
            return {"ok": True,
                    "detail": "`%s` ya promovido (existe en specs/)" % base,
                    "artifacts": {"promoted_path": final}}
        return {"ok": False,
                "detail": "nada que promover: `%s` no está en _pending/ ni "
                          "en specs/" % base,
                "retriable": False}
    if os.path.isfile(final):
        # AMBOS existen: promover pisaría un spec APROBADO — jamás.
        return {"ok": False,
                "detail": "`%s` YA existe en specs/ — no sobrescribo un spec "
                          "aprobado con la copia en cuarentena; resuélvelo a "
                          "mano (¿otro nombre? ¿modificar-harness?)" % base,
                "retriable": False}
    try:
        with open(ppath, encoding="utf-8") as fh:
            workflows.validate_spec(json.load(fh))
    except Exception as e:
        return {"ok": False,
                "detail": "el spec en cuarentena `%s` es INVÁLIDO — no se "
                          "promueve: %s: %s" % (base, type(e).__name__, e),
                "retriable": False}
    try:
        os.replace(ppath, final)             # move atómico (mismo filesystem)
    except OSError as e:
        return {"ok": False,                 # I/O: transitorio, reintentable
                "detail": "no pude mover `%s` a specs/: %s" % (base, e)}
    return {"ok": True,
            "detail": "spec `%s` promovido: _pending/ → specs/ (ya es "
                      "descubrible y corrible)" % base,
            "artifacts": {"promoted_path": final}}


def discoverable(ctx, step):
    """Paso det: verifica que el spec objetivo quedó REGISTRADO (aparece en
    `list_specs`) y DESCUBRIBLE (sus `triggers:` empatan su propia intención
    vía `match_specs` — el mismo matcher que usa `workspace wf match`). Un
    workflow que no aparece en el catálogo ni empata su tarea es como si no
    existiera: verde aquí = el meta-harness entregó algo ENCONTRABLE."""
    target = _target(ctx, step)
    if ctx.get("dry"):
        # dry PRIMERO: no-op ok aunque falte el target (nada real corre)
        return {"ok": True,
                "detail": ("verificaría descubribilidad de `%s` (dry)" % target
                           if target else
                           "verificaría descubribilidad del spec objetivo "
                           "(dry)")}
    if not target:
        return {"ok": False, "detail": _SIN_TARGET, "retriable": False}
    import workflows
    try:
        # DOS namespaces, cada check en el suyo (no mezclar):
        # · en_lista    → FILENAME: list_specs()[].name es el nombre de
        #   archivo (specs/<name>.json), igual que el target saneado.
        # · descubrible → campo `workflow` INTERNO: match_specs()[].name
        #   viene de spec["workflow"] (via match_score). Si filename ≠
        #   workflow, comparar contra el target daría falso-negativo.
        base = _base(target)
        en_lista = any(s.get("name") == base
                       for s in workflows.list_specs())
        spec = workflows.load_spec(target)
        wf_name = spec.get("workflow")
        trigs = [t for t in (spec.get("triggers") or []) if str(t).strip()]
        if not trigs:
            descubrible = False
            por_que = "sin triggers: no es descubrible por tarea (agrégalos)"
        else:
            hits = workflows.match_specs(" ".join(trigs))
            descubrible = wf_name in [c.get("name") for c in hits]
            por_que = ("sus %d triggers lo empatan" % len(trigs)
                       if descubrible else
                       "sus triggers NO lo empatan en `wf match` (¿términos "
                       "demasiado genéricos u opacados por otro spec?)")
    except (ValueError, FileNotFoundError) as e:
        # spec roto/inexistente = contrato: permanente, no transitorio
        return {"ok": False,
                "detail": "descubribilidad de `%s` no verificable: %s"
                          % (target, e),
                "retriable": False}
    except Exception as e:
        return {"ok": False,
                "detail": "descubribilidad de `%s` REVENTÓ: %s: %s"
                          % (target, type(e).__name__, e)}
    ok = en_lista and descubrible
    if ok:
        detail = ("spec `%s` registrado y descubrible — %s"
                  % (target, por_que))
    else:
        fallas = []
        if not en_lista:
            fallas.append("NO aparece en el catálogo (list_specs)")
        if not descubrible:
            fallas.append(por_que)
        detail = "spec `%s`: %s" % (target, " · ".join(fallas))
    return {"ok": ok, "detail": detail,
            "artifacts": {"registrado": bool(en_lista),
                          "descubrible": bool(descubrible)}}
