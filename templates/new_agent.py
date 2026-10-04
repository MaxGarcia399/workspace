#!/usr/bin/env python3
"""WORKSPACE · new_agent — instancia un agente nuevo desde el template.

Copia `templates/agent/` (scaffold de cerebro + lado harness), sustituye los
placeholders con los 6 parámetros, y deja el agente listo para registrar:

    python3 templates/new_agent.py hermes \
        --tagline "Motor de ejecución autónoma en VPS" \
        --soul "mensajero-ejecutor: rápido, silencioso, sin preguntas" \
        --skills "ejecución,automatización,monitoreo" \
        --color azul \
        --scope "escribe solo en su cerebro y en /srv/jobs; WORKSPACE solo lectura"

Qué produce:
  · `<DESKTOP>/<UPPER> - BRAIN/`        ← cerebro completo (CLAUDE.md, BOOT, STATE, skills…)
  · `WORKSPACE/agents/<nombre>/`          ← agent.json + brand/ (banner, dashboard, statusline)

Qué NO hace solo (gates deliberados, ver templates/README.md):
  · registrar en `agents/registry.json` (usar --register para hacerlo)
  · `workspace install <socio>` (lo corre el socio)
  · diseñar `BOOT/00-SOUL.md` (queda como esqueleto guiado — trabajo humano, N3)

Flags: --display --brain-dest --agents-dir --register --dry-run --force-color --selftest
Cero dependencias (stdlib, Python 3.9+). Cross-platform (Mac/Windows/Linux).
NO toca cerebros existentes: se niega si el destino ya existe.
"""
import argparse
import datetime
import json
import os
import re
import shutil
import sys
import unicodedata

sys.dont_write_bytecode = True

HERE = os.path.dirname(os.path.abspath(__file__))          # WORKSPACE/templates
WORKSPACE = os.path.dirname(HERE)                            # WORKSPACE/
TEMPLATE = os.path.join(HERE, "agent")
COLORS = ("dorado", "coral", "verde", "azul", "morado", "cyan", "gris")
TAKEN = {"zenith": "dorado", "atlas": "coral", "argus": "verde"}  # paletas ya ocupadas
TEXT_EXT = {".md", ".json", ".py", ".gitignore", ".txt", ".yml", ".yaml"}
PLACEHOLDER = re.compile(r"\{\{[A-Z_]+\}\}")


def slugify(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def is_text(path):
    base = os.path.basename(path)
    ext = os.path.splitext(base)[1] or base   # .gitignore no tiene "ext" clásica
    return ext.lower() in TEXT_EXT


_BAD_CHARS = re.compile(r'["\\\n\r\t]')


def _check_clean(flag, value):
    """Rechaza valores que romperían los archivos generados (la sustitución es
    textual y varios placeholders caen dentro de strings JSON de agent.json:
    una comilla, backslash o salto de línea producen JSON inválido)."""
    if value and _BAD_CHARS.search(value):
        sys.exit(f'new_agent: {flag} contiene caracteres no permitidos '
                 '(comillas dobles, backslash, tabs o saltos de línea) — romperían '
                 'el agent.json generado. Reescribir el valor sin ellos.')


def build_subs(args):
    name = slugify(args.name)
    if not name:
        sys.exit("new_agent: el nombre no produce un slug válido")
    for flag, val in (("--display", args.display), ("--tagline", args.tagline),
                      ("--soul", args.soul), ("--skills", args.skills),
                      ("--scope", args.scope)):
        _check_clean(flag, val)
    display = args.display or name.capitalize()
    cats = " · ".join(c.strip() for c in (args.skills or "").split(",") if c.strip()) \
        or "(definir categorías)"
    return name, {
        "{{AGENT_NAME}}": name,
        "{{AGENT_DISPLAY}}": display,
        "{{AGENT_UPPER}}": name.upper(),
        "{{TAGLINE}}": args.tagline,
        "{{SOUL_HINT}}": args.soul or "(sin semilla — diseñar desde cero)",
        "{{SKILL_CATS}}": cats,
        "{{COLOR}}": args.color,
        "{{SCOPE}}": args.scope,
        "{{DATE}}": datetime.date.today().isoformat(),
    }


def substitute(text, subs):
    for k, v in subs.items():
        text = text.replace(k, v)
    return text


def copy_tree(src, dst, subs, rename_brand=None, manifest=None):
    """Copia recursiva con sustitución de placeholders en archivos de texto."""
    for root, dirs, files in os.walk(src):
        dirs.sort()
        rel = os.path.relpath(root, src)
        out_dir = dst if rel == "." else os.path.join(dst, rel)
        os.makedirs(out_dir, exist_ok=True)
        for f in sorted(files):
            if f == ".DS_Store":
                continue
            sp = os.path.join(root, f)
            out_name = f
            if rename_brand and f.startswith("agent-") and f.endswith(".py"):
                out_name = f.replace("agent-", rename_brand + "-", 1)
            dp = os.path.join(out_dir, out_name)
            if is_text(sp):
                with open(sp, encoding="utf-8") as fh:
                    txt = fh.read()
                with open(dp, "w", encoding="utf-8", newline="\n") as fh:
                    fh.write(substitute(txt, subs))
                shutil.copymode(sp, dp)
            else:
                shutil.copy2(sp, dp)
            if manifest is not None:
                manifest.append(dp)


def leftover_placeholders(paths):
    """Placeholders sin sustituir en los archivos generados (debe ser [])."""
    bad = []
    for p in paths:
        if not is_text(p):
            continue
        with open(p, encoding="utf-8") as fh:
            hits = sorted(set(PLACEHOLDER.findall(fh.read())))
        if hits:
            bad.append((p, hits))
    return bad


def register(agents_dir, name):
    """Mueve el agente a `agents` en registry.json (idempotente)."""
    reg_path = os.path.join(agents_dir, "registry.json")
    with open(reg_path, encoding="utf-8") as fh:
        reg = json.load(fh)
    if any(a.get("name") == name for a in reg.get("agents", [])):
        return False
    reg.setdefault("agents", []).append(
        {"name": name, "dir": name, "engine": "claude-code", "aliases": [name]})
    reg["planned"] = [p for p in reg.get("planned", [])
                      if (p.get("name") if isinstance(p, dict) else p) != name]
    tmp = reg_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(reg, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, reg_path)
    return True


def instantiate(args):
    name, subs = build_subs(args)
    upper = subs["{{AGENT_UPPER}}"]
    brain_dest = os.path.abspath(os.path.expanduser(
        args.brain_dest or os.path.join(os.path.dirname(WORKSPACE), f"{upper} - BRAIN")))
    agents_dir = os.path.abspath(os.path.expanduser(args.agents_dir or
                                                    os.path.join(WORKSPACE, "agents")))
    agent_dest = os.path.join(agents_dir, name)

    # ── guardas: jamás tocar lo existente ──
    if name in TAKEN and not args.brain_dest:
        sys.exit(f"new_agent: '{name}' es un agente existente — no se sobreescribe.")
    for d in (brain_dest, agent_dest):
        if os.path.exists(d):
            sys.exit(f"new_agent: el destino ya existe — no se toca: {d}")
    if args.color not in COLORS:
        sys.exit(f"new_agent: color '{args.color}' no existe. Opciones: {', '.join(COLORS)}")
    clash = [a for a, c in TAKEN.items() if c == args.color]
    if clash and not args.force_color:
        sys.exit(f"new_agent: la paleta '{args.color}' ya es de {clash[0]} "
                 f"(--force-color para usarla igual)")

    if args.dry_run:
        print(f"  [dry-run] cerebro  → {brain_dest}")
        print(f"  [dry-run] harness  → {agent_dest}")
        print("  [dry-run] parámetros:")
        for k, v in subs.items():
            print(f"    {k:<20} {v}")
        return 0

    # ── instanciación ATÓMICA: construir en staging hermano del destino,
    #    validar TODO ahí, y solo entonces os.replace al destino real.
    #    Ante cualquier fallo: rmtree del staging — jamás queda nada a medias
    #    y re-correr no encuentra restos que lo bloqueen. ──
    manifest = []
    stage_brain = brain_dest + ".tmp-new%d" % os.getpid()
    stage_agent = agent_dest + ".tmp-new%d" % os.getpid()
    try:
        copy_tree(os.path.join(TEMPLATE, "brain"), stage_brain, subs,
                  manifest=manifest)
        copy_tree(os.path.join(TEMPLATE, "workspace"), stage_agent, subs,
                  rename_brand=name, manifest=manifest)

        # ── verificación (sobre el staging): sin placeholders huérfanos + JSON válido ──
        bad = leftover_placeholders(manifest)
        if bad:
            for p, hits in bad:
                print(f"  ⚠ placeholders sin sustituir en {p}: {', '.join(hits)}")
            sys.exit("new_agent: instanciación incompleta (ver arriba) — "
                     "no se escribió nada en los destinos")
        try:
            with open(os.path.join(stage_agent, "agent.json"), encoding="utf-8") as fh:
                json.load(fh)   # valida que el JSON quedó bien formado
        except ValueError as e:
            sys.exit(f"new_agent: el agent.json generado es inválido ({e}) — "
                     "no se escribió nada en los destinos")

        # ── commit: mover staging → destino (rename, atómico por árbol) ──
        os.replace(stage_brain, brain_dest)
        try:
            os.replace(stage_agent, agent_dest)
        except BaseException:
            shutil.rmtree(brain_dest, ignore_errors=True)   # no dejar medio agente
            raise
    except BaseException:
        shutil.rmtree(stage_brain, ignore_errors=True)
        shutil.rmtree(stage_agent, ignore_errors=True)
        raise

    did_register = False
    if args.register:
        did_register = register(agents_dir, name)

    print(f"\n  ✓ {subs['{{AGENT_DISPLAY}}']} instanciado — {len(manifest)} archivos")
    print(f"    cerebro:  {brain_dest}")
    print(f"    harness:  {agent_dest}")
    if args.register:
        print("    registry: " + ("agregado a agents/registry.json" if did_register
                                  else "ya estaba registrado (sin cambios)"))
    print("\n  Siguientes pasos (gates deliberados):")
    step = iter(range(1, 9))
    if not did_register:
        print(f"    {next(step)}. Registrar: mover '{name}' a `agents` en "
              f"agents/registry.json (o re-correr con --register).")
    print(f"    {next(step)}. Diseñar BOOT/00-SOUL.md (es esqueleto guiado — lo que "
          "realmente importa diseñar).")
    print(f"    {next(step)}. Hook de auto-aprendizaje: crear "
          "<brain>/.claude/settings.local.json con SOLO el bloque hooks "
          "(SessionEnd → WORKSPACE/hooks/skill_review.py). Ver "
          "cablear-agente-workspace §3 (pitfall del clasificador).")
    print(f"    {next(step)}. `python3 WORKSPACE/install.py <socio>` — launcher, statusline, "
          "socio.local.")
    print(f"    {next(step)}. Verificar: `workspace doctor` + abrir terminal nueva y lanzar "
          f"`{name}`.")
    return 0


# ── selftest: instancia en un tmp SIN tocar lo real, verifica, limpia ──
def selftest():
    import py_compile
    import subprocess
    import tempfile
    tmp = tempfile.mkdtemp(prefix="workspace-new-agent-test-")
    ns = argparse.Namespace(
        name="probus", display=None, tagline="Agente de prueba del template",
        soul="probador: existe para verificar el scaffold", skills="pruebas,verificación",
        color="cyan", scope="solo escribe dentro del tmp del selftest",
        brain_dest=os.path.join(tmp, "PROBUS - BRAIN"),
        agents_dir=os.path.join(tmp, "agents"),
        register=True, dry_run=False, force_color=False)
    os.makedirs(ns.agents_dir)
    with open(os.path.join(ns.agents_dir, "registry.json"), "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "agents": [], "planned": [{"name": "probus"}]}, fh)
    fails = []
    try:
        rc = instantiate(ns)
        if rc not in (0, None):
            fails.append(f"instantiate devolvió {rc}")
        # estructura mínima esperada (E1+E2: INDEX.md + destilados + log-archive)
        expect = ["CLAUDE.md", ".gitignore", "BOOT/00-SOUL.md", "BOOT/04-BRAIN-MAP.md",
                  "STATE/MEMORY.md", "STATE/DESTILADO.md", "STATE/brain-version.md",
                  "STATE/INDEX.md",
                  "STATE/log-archive/README.md",
                  "STATE/sessions/README.md", "STATE/sessions/max/.gitkeep",
                  "STATE/sessions/max/destilados/.gitkeep",
                  "STATE/sessions/fer/destilados/.gitkeep",
                  "STATE/sessions/mau/destilados/.gitkeep",
                  "STATE/memoria-archivo/README.md", "skills/INDEX-LITE.md",
                  "skills/README.md", "skills/meta/skill-creator/SKILL.md",
                  "skills/investigación/deep-research/SKILL.md", "wiki/index.md",
                  "adapters/claude-code.md"]
        for relp in expect:
            if not os.path.exists(os.path.join(ns.brain_dest, relp)):
                fails.append(f"falta {relp}")
        # lado harness: agent.json coherente + brand renombrado + .py compilables
        aj_path = os.path.join(ns.agents_dir, "probus", "agent.json")
        with open(aj_path, encoding="utf-8") as fh:
            aj = json.load(fh)
        if aj["name"] != "probus" or aj["session_env"] != "PROBUS_WS":
            fails.append("agent.json mal sustituido")
        if "statusline" not in aj.get("scripts", {}):
            fails.append("agent.json sin scripts.statusline (pitfall)")
        for kind in ("banner", "dashboard", "statusline"):
            p = os.path.join(ns.agents_dir, "probus", "brand", f"probus-{kind}.py")
            if not os.path.exists(p):
                fails.append(f"brand sin renombrar: {kind}")
            else:
                py_compile.compile(p, doraise=True)
        # registry actualizado
        with open(os.path.join(ns.agents_dir, "registry.json"), encoding="utf-8") as fh:
            reg = json.load(fh)
        if not any(a["name"] == "probus" for a in reg["agents"]) or reg["planned"]:
            fails.append("registry.json no quedó registrado/limpio")
        # humo: banner y statusline corren (statusline necesita JSON por stdin)
        env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
        r = subprocess.run([sys.executable,
                            os.path.join(ns.agents_dir, "probus", "brand", "probus-banner.py")],
                           capture_output=True, env=env)
        if r.returncode != 0:
            fails.append(f"banner no corre: {r.stderr.decode()[:200]}")
        r = subprocess.run([sys.executable,
                            os.path.join(ns.agents_dir, "probus", "brand",
                                         "probus-statusline.py"),
                            "--brain", ns.brain_dest],
                           input=b"{}", capture_output=True, env=env)
        if r.returncode != 0:
            fails.append(f"statusline no corre: {r.stderr.decode()[:200]}")
    except SystemExit as e:
        fails.append(f"abortó: {e}")
    except Exception as e:  # noqa: BLE001 — el selftest reporta, no truena
        fails.append(f"{type(e).__name__}: {e}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    if fails:
        print("  ✗ selftest FALLÓ:")
        for f in fails:
            print(f"    - {f}")
        return 1
    print("  ✓ selftest verde — el template instancia completo en un tmp "
          "(estructura, sustitución, brand compilable, registry) y limpia tras de sí")
    return 0


def main():
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    ap = argparse.ArgumentParser(
        description="Instancia un agente de WORKSPACE desde templates/agent/ "
                    "(los 6 parámetros: nombre, tagline, soul, skills, color, scope)")
    ap.add_argument("name", help="slug del agente (ej. hermes)")
    ap.add_argument("--display", help="nombre visible (default: slug capitalizado)")
    ap.add_argument("--tagline", required=True, help="rol en una línea")
    ap.add_argument("--soul", default="", help="semilla de personalidad (1 línea)")
    ap.add_argument("--skills", default="", help="categorías de dominio, separadas por coma")
    ap.add_argument("--color", default="gris", help=f"paleta: {', '.join(COLORS)}")
    ap.add_argument("--scope", required=True, help="restricciones de scope (1-3 líneas)")
    ap.add_argument("--brain-dest", help="ruta del cerebro (default: hermano de WORKSPACE)")
    ap.add_argument("--agents-dir", help="carpeta agents/ (default: WORKSPACE/agents)")
    ap.add_argument("--register", action="store_true",
                    help="además, registrar en agents/registry.json")
    ap.add_argument("--dry-run", action="store_true", help="mostrar el plan sin escribir")
    ap.add_argument("--force-color", action="store_true",
                    help="permitir una paleta ya usada por otro agente")
    sys.exit(instantiate(ap.parse_args()))


if __name__ == "__main__":
    main()
