#!/usr/bin/env python3
"""workflows.steps.triage — router DETERMINISTA de hallazgos de review (P2 #2).

Cierra el hueco [AD-HOC]→[DET] del MAPA (P2): Python puro que rutea los
hallazgos del paso `find` — sin LLM, sin red, sin efectos, orden de entrada
preservado (mismo input ⇒ mismo output, siempre).

REGLA DURA (MAPA.md · P2): un hallazgo PLAUSIBLE ⇒ JAMÁS auto-fix.
Solo CONFIRMED entra a la cola de `fix`; TODO lo demás (PLAUSIBLE, veredicto
desconocido, formato inválido) escala al socio — fail-safe: en la duda, humano.

Profundidad por riesgo (P2 #5): low→lint · medium→review ·
high→ultra+verificar+socio. Riesgo desconocido se trata como high
(conservador: un dato malo jamás compra MENOS escrutinio).

Entrada de hallazgos, en orden de prioridad:
  1. `ctx["artifacts"]["findings"]` — lista dejada por el paso `find`
     (valor-dato), o RUTA a un JSON (así commitea el driver real: el
     artefacto es el archivo que escribió en el workdir del run).
  2. JSON en disco: `--param findings=<ruta>` o `step["findings"]`.
  3. Nada declarado → 0 hallazgos (find es STUB v1), colas vacías.
Cada hallazgo: dict con veredicto (`verdict`/`veredicto` =
CONFIRMED|PLAUSIBLE) y riesgo (`risk`/`riesgo`/`severity`/`severidad`).
"""
import json
import os

CONFIRMED, PLAUSIBLE = "CONFIRMED", "PLAUSIBLE"

# P2 #5 — profundidad por riesgo (del MAPA congelado v1)
DEPTH_BY_RISK = {"low": "lint", "medium": "review",
                 "high": "ultra+verificar+socio"}
_RISK_ALIASES = {"low": "low", "bajo": "low", "baja": "low",
                 "medium": "medium", "medio": "medium", "media": "medium",
                 "high": "high", "alto": "high", "alta": "high"}


def _verdict(finding):
    """Veredicto normalizado (mayúsculas) o '' si no viene."""
    return str(finding.get("verdict") or finding.get("veredicto")
               or "").strip().upper()


def _risk(finding):
    """Riesgo normalizado a low|medium|high, o None si no se reconoce."""
    raw = str(finding.get("risk") or finding.get("riesgo")
              or finding.get("severity") or finding.get("severidad")
              or "").strip().lower()
    return _RISK_ALIASES.get(raw)


def route_findings(findings):
    """Función PURA — el router entero. Lista de hallazgos → colas ruteadas.

    · CONFIRMED → cola `fix` (auto).
    · PLAUSIBLE → cola `escalar` (humano) — REGLA DURA, jamás auto-fix.
    · veredicto desconocido / hallazgo malformado → `escalar` (fail-safe).
    Determinista: preserva el orden de entrada, sin sets, sin azar, sin I/O.
    """
    fix, escalar = [], []
    for i, f in enumerate(findings):
        if not isinstance(f, dict):
            escalar.append({"finding": f, "index": i, "queue": "escalar",
                            "risk": "unknown",
                            "depth": DEPTH_BY_RISK["high"],
                            "reason": "hallazgo malformado (no es objeto) — "
                                      "fail-safe: escala al socio"})
            continue
        risk = _risk(f)
        item = dict(f)
        item.update({"index": i, "risk": risk or "unknown",
                     "depth": DEPTH_BY_RISK[risk or "high"]})
        verdict = _verdict(f)
        if verdict == CONFIRMED:
            item["queue"] = "fix"
            item["reason"] = "CONFIRMED → auto-fix"
            fix.append(item)
        else:
            item["queue"] = "escalar"
            if verdict == PLAUSIBLE:
                item["reason"] = ("PLAUSIBLE ⇒ jamás auto-fix "
                                  "(regla dura del MAPA · P2)")
            else:
                item["reason"] = ("veredicto %r desconocido — fail-safe: "
                                  "escala al socio" % (verdict or None,))
            escalar.append(item)
    return {"fix": fix, "escalar": escalar,
            "counts": {"total": len(findings), "fix": len(fix),
                       "escalar": len(escalar)}}


def _load_findings(ctx, step):
    """(hallazgos, origen legible). ValueError si el archivo no es una lista."""
    arts = ctx.get("artifacts") or {}
    if isinstance(arts.get("findings"), list):
        return arts["findings"], "artefacto `findings` del run"
    if isinstance(arts.get("findings"), str) and arts["findings"].strip():
        # el driver real commitea el artefacto como ARCHIVO en el workdir
        # del run — el artefacto es la ruta, el contenido es el JSON.
        path = arts["findings"]
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, list):
            raise ValueError("findings en %s no es una lista JSON" % path)
        return data, "artefacto `findings` (archivo %s)" % path
    rel = (ctx.get("params") or {}).get("findings") or step.get("findings")
    if not rel:
        return [], "sin hallazgos declarados (find STUB v1)"
    path = rel if os.path.isabs(rel) else os.path.join(
        ctx.get("repo") or os.getcwd(), rel)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    if not isinstance(data, list):
        raise ValueError("findings en %s no es una lista JSON" % path)
    return data, "archivo %s" % path


def route(ctx, step):
    """Paso det (P2 #2): rutea hallazgos y deja el artefacto `triage`."""
    if ctx.get("dry"):
        return {"ok": True,
                "detail": "dry: rutearía hallazgos (CONFIRMED→fix · "
                          "PLAUSIBLE→escalar, jamás auto-fix)"}
    try:
        findings, origen = _load_findings(ctx, step)
    except Exception as e:
        return {"ok": False, "detail": "no pude leer hallazgos: %s: %s"
                % (type(e).__name__, e)}
    res = route_findings(findings)
    c = res["counts"]
    return {"ok": True,
            "detail": "triage det (%s): %d hallazgo(s) → fix=%d · escalar=%d"
                      % (origen, c["total"], c["fix"], c["escalar"]),
            "artifacts": {"triage": res}}


def verify_routed(ctx, step):
    """Verify det de la INVARIANTE dura: 0 hallazgos no-CONFIRMED en la cola
    de auto-fix. Lee el artefacto `triage` del run — evidencia, no claims."""
    tri = (ctx.get("artifacts") or {}).get("triage")
    if not isinstance(tri, dict):
        return {"ok": False, "detail": "sin artefacto `triage` en el run — "
                                       "no hay evidencia del ruteo"}
    fix, escalar = tri.get("fix"), tri.get("escalar")
    if not isinstance(fix, list) or not isinstance(escalar, list):
        return {"ok": False, "detail": "artefacto `triage` malformado "
                                       "(fix/escalar no son listas)"}
    malos = [it for it in fix
             if not (isinstance(it, dict) and _verdict(it) == CONFIRMED)]
    if malos:
        return {"ok": False,
                "detail": "INVARIANTE ROTA: %d hallazgo(s) no-CONFIRMED en la "
                          "cola de auto-fix (PLAUSIBLE ⇒ jamás auto-fix)"
                          % len(malos)}
    return {"ok": True,
            "detail": "invariante ok: %d en fix (todos CONFIRMED) · %d "
                      "escalado(s) al socio" % (len(fix), len(escalar))}


def depth_plan(ctx, step):
    """Paso det (P2 #5, ex AD-HOC): resume la profundidad por riesgo del
    triage — low→lint · medium→review · high→ultra+verificar+socio."""
    if ctx.get("dry"):
        return {"ok": True,
                "detail": "dry: resumiría la profundidad por riesgo "
                          "(low→lint · medium→review · "
                          "high→ultra+verificar+socio)"}
    tri = (ctx.get("artifacts") or {}).get("triage")
    if not isinstance(tri, dict):
        return {"ok": False, "detail": "sin artefacto `triage` en el run — "
                                       "el paso triage va primero"}
    plan = {}
    for cola in ("fix", "escalar"):
        for it in tri.get(cola) or []:
            d = (it.get("depth") if isinstance(it, dict) else None) \
                or DEPTH_BY_RISK["high"]
            plan[d] = plan.get(d, 0) + 1
    detalle = " · ".join("%s=%d" % (k, plan[k]) for k in sorted(plan)) \
        or "sin hallazgos"
    return {"ok": True, "detail": "profundidad por riesgo: " + detalle,
            "artifacts": {"depth_plan": plan}}
