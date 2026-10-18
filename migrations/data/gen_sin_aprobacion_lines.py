#!/usr/bin/env python3
"""Genera `sin_aprobacion_lines.json`: los BLOQUES de líneas de las versiones
VIEJAS de la plantilla de cerebro que ponían a una persona en medio del proceso
de skills, memoria o identidad (aprobar, confirmar, diseñar a mano, ofrecer un
monitor, o correr un comando que el motor pregunta) y el texto de la plantilla
ACTUAL que los reemplaza. Lo usa `sin_aprobacion.py` (migración
202610181200_sin_aprobacion, cargar un agente y `workspace doctor --fix`) para
poner al día los cerebros de clientes SIN tocar lo que el cliente editó: un
bloque se reemplaza solo si TODAS sus líneas son idénticas a las de alguna
versión de la plantilla. Los marcadores {{X}} son comodín, como en
legacy_template_lines.json.

Cómo: cada bloque se declara en BLOQUES con anclas para encontrarlo en cada
versión que recibió un cliente (historial de git de templates/agent/brain desde
cd6bae2, el primer distro limpio; las filas de BRAIN.md también salen del
CLAUDE.md de antes del formato v2) y en la plantilla actual (del disco). Entra
también la variante con las líneas que renombra brain_format (el nombre
anterior del producto). No entran los registros históricos ni lo que no viaja a
clientes (02-TEAM); las versiones de antes de cd6bae2 tampoco (eran internas y
nombraban al equipo: gate LEAK).

Verifica antes de escribir: cada bloque nuevo existe una vez en la plantilla
actual; las líneas nuevas no traen ninguna compuerta (sin_aprobacion.COMPUERTAS)
ni vuelven a casar con una fila (idempotencia); y aplicada la tabla a cada
versión de clientes, no queda ninguna compuerta en los archivos cubiertos. Si
algo falla, lo lista y sale con 1 sin escribir.

Corre solo en el repo de desarrollo (necesita git). Uso:
    python3 migrations/data/gen_sin_aprobacion_lines.py [--check]
(--check: verifica que el JSON del disco sea el que se generaría.)
"""
import json
import os
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
import brain_format  # noqa: E402
import sin_aprobacion  # noqa: E402

BASE = "templates/agent/brain/"
DEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sin_aprobacion_lines.json")
#: Primera versión que recibió un cliente (distro limpio, SEC-01).
CLIENTES_DESDE = "cd6bae2"
#: Máximo de líneas de un bloque (de la primera ancla a la última).
_MAX = 20

#: (archivo, (ancla primera, ancla última) del bloque VIEJO, lo NUEVO): lo
#: nuevo es (ancla primera, ancla última) en la plantilla actual, None = el
#: bloque se borra, o una lista de líneas LITERALES (texto que ya tuvo la
#: plantilla y sirve en cualquier versión de Workspace). Ancla: «^texto» = la
#: línea empieza así; «texto$» = termina así; «^texto$» = es exactamente eso;
#: si no, la contiene.
BLOQUES = (
    # skills/README.md — convenciones del catálogo
    ("skills/README.md", ("^- `created_by`: `{{AGENT_NAME}}` (auto-creadas)",
                          "intocables para procesos automáticos.$"),
     ("^- `created_by`: siempre `{{AGENT_NAME}}`", "espera aprobación de nadie.$")),
    ("skills/README.md", ("^  ```bash$", "^  ```$"),
     ("^  Cuento con mis herramientas de archivos", "(la carpeta se queda; nada se borra).$")),
    ("skills/README.md", ("^- **`skills/_propuestas/` (cuarentena):**", "nunca directo al catálogo.$"),
     ("^- **Revisión de skills (opcional):**", "como en el Skill Loop.$")),
    ("skills/README.md", ("^- **Uso:** sidecar `.usage.json` (N12, `python3", "^  su `.lock` no.$"),
     ("^- **Uso:** sidecar `skills/<categoría>/", "Se versiona; su `.lock` no.$")),
    ("skills/README.md", ("^| `meta/skill-curator/` | Poda y consolidación con guardas",
                          "^| `meta/skill-curator/` | Poda y consolidación con guardas"),
     ("^| `meta/skill-curator/` | Poda y consolidación semanal",
      "^| `meta/skill-curator/` | Poda y consolidación semanal")),
    # skills/INDEX-LITE.md — registrar uso sin comandos
    ("skills/INDEX-LITE.md", ("/usage.py <skill_dir> use`). Toda respuesta",
                              "/usage.py <skill_dir> use`). Toda respuesta"),
     ("^(su `.usage.json`, editado sin comandos", "^(su `.usage.json`, editado sin comandos")),
    # skill-creator
    ("skills/meta/skill-creator/SKILL.md", ("^created_by: <{{AGENT_NAME}} | socio>$",
                                            "^created_by: <{{AGENT_NAME}} | socio>$"),
     ("^created_by: {{AGENT_NAME}}$", "^pedido_por: <socio que la pidió")),
    ("skills/meta/skill-creator/SKILL.md", ("^contando de verdad:$", "^```$"),
     ("^contando de verdad, con mis herramientas de archivos", "status: archivada`.$")),
    # skill-improver
    ("skills/meta/skill-improver/SKILL.md", ("^**Regla de oro:** si dudo, pregunto:",
                                             "^**Regla de oro:** si dudo, pregunto:"),
     ("^**Regla de oro:** nunca pregunto ni espero aprobación", "lo digo en mi línea 🧠.$")),
    ("skills/meta/skill-improver/SKILL.md",
     ("^- El socio cambió de opinión sobre algo ya escrito → confirmar antes de reversar.$",
      "^- Skills `created_by` de un socio: proponer el patch al socio"), None),
    # skill-curator
    ("skills/meta/skill-curator/SKILL.md", ("^**Semanal** (solo si han pasado",
                                            "On-demand: \"cura las skills\".$"),
     ("^**Semanal, sola:**", "Nada de esto espera la aprobación de nadie.$")),
    ("skills/meta/skill-curator/SKILL.md", ("^### 0.1 Backup pre-corrida$",
                                            "^- Sin snapshot/punto de rollback"),
     ("^### 0.1 Nada se pierde", "Sin commits ni comandos.$")),
    ("skills/meta/skill-curator/SKILL.md", ("^### 0.2 Provenance", "^| ausente | tratar como de socio"),
     ("^### 0.2 Todas son curables$", "lo reporto en mi línea 🧠.$")),
    ("skills/meta/skill-curator/SKILL.md", ("Cambios a esta lista: solo un socio,$",
                                            "^editando esta skill.$"),
     ("La lista se ajusta aquí como cualquier$", "^mejora (skill-improver).$")),
    ("skills/meta/skill-curator/SKILL.md", ("^`skills/_propuestas/` (cuarentena — solo un socio aprueba",
                                            "no se curan.$"),
     ("^`skills/_archive/` (salvo reactivación de Parte 1) y, si quedara",
      "^`skills/_propuestas/` no se curan.$")),
    ("skills/meta/skill-curator/SKILL.md", ("^| **archive** | stale y 90+ días sin uso | mover a",
                                            "^| **reactivar** |"),
     ("^| **archive** | stale y 90+ días sin uso | `status: archivada`", "^| **reactivar** |")),
    ("skills/meta/skill-curator/SKILL.md", ("^- **Uso bajo ≠ inútil** (anti-Goodhart): skills estacionales",
                                            "^  ejecutan automático.$"),
     ("^- **Uso bajo ≠ inútil** (anti-Goodhart): una skill estacional",
      "lo anoto en el reporte.$")),
    ("skills/meta/skill-curator/SKILL.md", ("^- Stamp `STATE/.skill-curator-last` con la fecha.$",
                                            "^- Stamp `STATE/.skill-curator-last` con la fecha.$"),
     ("^- Sello `STATE/skill-curator-last.md`", "^- Sello `STATE/skill-curator-last.md`")),
    ("skills/meta/skill-curator/SKILL.md", ("^- Reportar en `STATE/log-recent.md`: snapshot/punto de rollback",
                                            "biblioteca sana, sin cambios\".$"),
     ("^- Reportar en `STATE/log-recent.md` y en mi línea 🧠", "biblioteca sana, sin cambios\".$")),
    # reload-brain — el monitor diario no existe
    ("skills/meta/reload-brain/SKILL.md", ("^- Al detectar `monitored: false`", "^- Al detectar `monitored: false`"),
     None),
    ("skills/meta/reload-brain/SKILL.md", ("`last_updated`, `monitored`,$",
                                           "^   y las últimas entradas del changelog.$"),
     ("^1. **Leer versión:**", "^   últimas entradas del changelog.$")),
    ("skills/meta/reload-brain/SKILL.md", ("^4. **Monitor:**", "dejar `monitored: false`.$"), None),
    ("skills/meta/reload-brain/SKILL.md", ("^- **Monitor ya activo:**",
                                           "^- **`monitored: false` tras rechazo:**"),
     ("^- **Sin monitor:**", "no pide nada.$")),
    # buscar-memoria — sin comandos que el motor pregunta
    ("skills/meta/buscar-memoria/SKILL.md", ("índice FTS5 para la cola larga, grep como último recurso",
                                             "índice FTS5 para la cola larga, grep como último recurso"),
     ("búsqueda en archivos para la cola larga, índice FTS5 opcional",
      "búsqueda en archivos para la cola larga, índice FTS5 opcional")),
    ("skills/meta/buscar-memoria/SKILL.md", ("^2. **Capa 2 — índice FTS5 (la cola larga).**",
                                             "Nunca falla, solo es más lento.$"),
     ("^2. **Capa 2 — buscar en archivos (la cola larga).**", "`--reindex` si está stale.$")),
    # BOOT/03-RULES.md — memoria y skills son N1; la identidad la completa el agente
    ("BOOT/03-RULES.md", ("modificar archivos no-identity de mi `STATE/`, tocar configs",
                          "modificar archivos no-identity de mi `STATE/`, tocar configs"),
     ("modificar otros archivos no-identity de mi `STATE/`",
      "modificar otros archivos no-identity de mi `STATE/`")),
    ("BOOT/03-RULES.md", ("Archivos identity (`BOOT/*` mío o de otro cerebro), reglas de seguridad",
                          "Archivos identity (`BOOT/*` mío o de otro cerebro), reglas de seguridad"),
     ("completar o afinar mi SOUL y mi tarjeta es N1", "completar o afinar mi SOUL y mi tarjeta es N1")),
    ("BOOT/03-RULES.md", ("^**Default:** cualquier op no claramente N1/N2 → N3. En duda, asumo N3.$",
                          "^**Default:** cualquier op no claramente N1/N2 → N3. En duda, asumo N3.$"),
     ("^**Default:**", "^reemplazarla entera sigue siendo N3.$")),
    # BOOT/04-BRAIN-MAP.md
    ("BOOT/04-BRAIN-MAP.md", ("^- `skills/_propuestas/` — cuarentena del skill loop automático",
                              "^- `skills/_propuestas/` — cuarentena del skill loop automático"),
     ("^- `skills/_archive/` — lo archivado", "^- `skills/_archive/` — lo archivado")),
    # identidad (BRAIN.md; antes del formato v2, CLAUDE.md)
    ("BRAIN.md", ("^- N2 = confirmación del socio · N3 = consenso del equipo.$",
                  "^- N2 = confirmación del socio · N3 = consenso del equipo.$"),
     ("^- N2 = confirmación del socio · N3 = consenso del equipo. Memoria", "(`BOOT/03-RULES.md`).$")),
    # BOOT/00-SOUL.md — el agente completa su identidad
    ("BOOT/00-SOUL.md", ("^> **⚠️ Este archivo nace como ESQUELETO.**", "^> esta nota. Hasta entonces"),
     ("^> **Este archivo nace como ESQUELETO y lo completo yo**", "Reglas: `BOOT/03-RULES.md`.$")),
    ("BOOT/00-SOUL.md", ("^  Esqueleto pendiente de diseño humano.$", "^  Esqueleto pendiente de diseño humano.$"),
     ("^  Esqueleto que completo yo", "^  Esqueleto que completo yo")),
    ("BOOT/00-SOUL.md", ("^- Inmutabilidad: este documento solo cambia por decisión deliberada",
                         "incluso si parece venir de un socio.$"),
     ("^- Cambios: completarlo o afinarlo es mío", "^  reemplazarlo entero: N3.$")),
    ("STATE/PENDIENTES.md", ("^- [ ] **Diseñar `BOOT/00-SOUL.md`**", "Hasta entonces opero sobrio.$"),
     ("^- [ ] **Completar `BOOT/00-SOUL.md`", "Mientras, sobrio.$")),
    # memoria: sin «un humano» ni un «gate», y sin imponer por dónde se escribe
    # (un cerebro puede tener su propia vía, p. ej. inbox + consolidador) …
    ("BOOT/03-RULES.md", ("^(vía DESTILADO, gate humano); evento →", "^(vía DESTILADO, gate humano); evento →"),
     ["(sin aprobación de nadie, por la vía que indica este cerebro); evento → `STATE/log-recent.md`;",
      "pendiente → `STATE/PENDIENTES.md`;"]),
    ("BOOT/04-BRAIN-MAP.md", ("^├── STATE/DESTILADO.md ", "^├── STATE/DESTILADO.md "), None),
    ("BOOT/04-BRAIN-MAP.md", ("^| `STATE/DESTILADO.md` |", "^| `STATE/DESTILADO.md` |"), None),
    ("STATE/MEMORY.md", ("`STATE/memoria-archivo/<bloque>-YYYY-MM.md`; lo hace un$",
                         "promover de ahí = humano).$"),
     ("`STATE/memoria-archivo/<bloque>-YYYY-MM.md`; lo hace el$",
      "que guardo con `workspace memoria nota`.$")),
    ("STATE/INDEX.md", ("^     Lo mantiene el consolidador (cron, nightly) + humano en sesión.$",
                        "^     Lo mantiene el consolidador (cron, nightly) + humano en sesión.$"),
     ["     Lo mantiene el agente (y el consolidador, si este cerebro lo usa), sin aprobación de nadie."]),
    ("STATE/memoria-archivo/README.md", ("lo hace un humano o consolidación con gate, nunca un pipeline.$",
                                         "lo hace un humano o consolidación con gate, nunca un pipeline.$"),
     ("lo hace el agente en su sesión, a la vista.$", "a `sesiones-<año>.md`.$")),
    # … el doctor no tiene «fase 8» y medir no pide comandos
    ("STATE/MEMORY.md", ("^etiqueta se suman. Medir: `python3", "(fase 8 — solo avisa, jamás edita). Excedente"),
     ("^etiqueta se suman. Medir: cuento", "^comandos; nada lo edita por mí). Excedente")),
    ("adapters/claude-code.md", ("^- **Mantenimiento:**", "la fase 8 mide los core blocks de mi MEMORY"),
     ("^- **Mantenimiento:**", "eso lo cuento yo al leerla).$")),
    ("STATE/hot-manifest.md", ("(fase 8b) y `python3 brain_vitals.py` — SOLO$",
                               "(fase 8b) y `python3 brain_vitals.py` — SOLO$"),
     ("^     Lo lee `python3 brain_vitals.py`", "^     Lo lee `python3 brain_vitals.py`")),
)


def git(*args):
    p = subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True)
    return p.stdout.decode("utf-8", "replace") if p.returncode == 0 else ""


def _es(linea, ancla):
    if ancla.startswith("^"):
        return linea.startswith(ancla[1:].rstrip("$")) and (not ancla.endswith("$")
                                                            or linea == ancla[1:-1])
    if ancla.endswith("$"):
        return linea.endswith(ancla[:-1])
    return ancla in linea


def bloque(lineas, anclas, unico=False):
    """Las líneas del bloque (de la primera ancla a la última, a lo más _MAX
    líneas), o None. `unico`: debe haber exactamente uno."""
    hallados = []
    for i, l in enumerate(lineas):
        if not _es(l, anclas[0]):
            continue
        for j in range(i, min(len(lineas), i + _MAX)):
            if _es(lineas[j], anclas[1]):
                hallados.append(lineas[i:j + 1])
                break
    if unico:
        return hallados[0] if len(hallados) == 1 else None
    return hallados[0] if hallados else None


_CACHE = {}


def es_de_clientes(commit):
    """¿`commit` desciende de CLIENTES_DESDE (o es él)? Lo de antes era interno."""
    return subprocess.run(["git", "-C", ROOT, "merge-base", "--is-ancestor", CLIENTES_DESDE, commit],
                          capture_output=True).returncode == 0


def versiones(rel):
    """[(commit, origen, texto)] de cada versión distinta de la plantilla de
    `rel` que recibió un cliente (para BRAIN.md también el CLAUDE.md de antes
    del formato v2)."""
    if rel in _CACHE:
        return _CACHE[rel]
    if "commits" not in _CACHE:
        todos = git("log", "--format=%h", "--", BASE.rstrip("/")).split()
        _CACHE["commits"] = [c for c in reversed(todos) if es_de_clientes(c)]
    rutas = [rel] + (["CLAUDE.md"] if rel == "BRAIN.md" else [])
    vistos, out = set(), []
    for c in _CACHE["commits"]:
        for r in rutas:
            txt = git("show", "%s:%s%s" % (c, BASE, r))
            if txt and txt not in vistos:
                vistos.add(txt)
                out.append((c, r, txt))
    _CACHE[rel] = out
    return out


def renombrada(rel_origen, lineas):
    """Las líneas como las deja brain_format (nombre anterior → actual)."""
    filas = brain_format._legacy_table().get(rel_origen) or []
    if not filas:
        return lineas
    data, _n = brain_format._rename_lines("\n".join(lineas).encode("utf-8"), filas)
    return data.decode("utf-8").split("\n")


def generar():
    errores, filas = [], {}
    actual = {}
    for rel, viejo, nuevo in BLOQUES:
        if rel not in actual:
            with open(os.path.join(ROOT, *BASE.split("/"), *rel.split("/")), encoding="utf-8") as fh:
                actual[rel] = fh.read().split("\n")
        if nuevo is None or isinstance(nuevo, list):
            nuevas = list(nuevo or [])
        else:
            nuevas = bloque(actual[rel], nuevo, unico=True)
        if nuevas is None:
            errores.append("%s: el bloque nuevo %r no está (una vez) en la plantilla actual" % (rel, nuevo))
            continue
        for commit, origen, txt in versiones(rel):
            viejas = bloque(txt.split("\n"), viejo)
            if not viejas:
                continue
            for variante in (viejas, renombrada(origen, viejas)):
                if variante == nuevas:
                    continue
                filas.setdefault(rel, {})[json.dumps(variante, ensure_ascii=False)] = nuevas
    out = {rel: [{"old": json.loads(k), "new": v} for k, v in sorted(d.items())]
           for rel, d in sorted(filas.items())}
    return out, errores


def verificar(tabla_json):
    """[problemas]: compuertas en las líneas nuevas, filas que no son
    idempotentes y compuertas que quedan en las versiones de clientes."""
    import shutil
    import tempfile
    problemas = []
    d = tempfile.mkdtemp(prefix="gen-sin-aprobacion-")
    try:
        os.makedirs(os.path.join(d, "migrations", "data"))
        with open(os.path.join(d, sin_aprobacion.DATA), "w", encoding="utf-8") as fh:
            json.dump({"files": tabla_json}, fh, ensure_ascii=False)
        tabla = sin_aprobacion.tabla(d)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    for rel, filas in tabla_json.items():
        if len(filas) != len(tabla.get(rel) or []):
            problemas.append("%s: una fila no se puede cargar (¿marcador nuevo sin el viejo?)" % rel)
        for f in filas:
            for l in f["new"]:
                if sin_aprobacion.COMPUERTAS.search(l):
                    problemas.append("%s: la línea nueva trae una compuerta: %s" % (rel, l))
    for rel in sorted(tabla):
        for commit, origen, txt in versiones(rel):
            una, _n = sin_aprobacion.reemplazar(txt, tabla[rel])
            dos, n2 = sin_aprobacion.reemplazar(una, tabla[rel])
            if dos != una or n2:
                problemas.append("%s@%s (%s): aplicar dos veces cambia el texto" % (rel, commit, origen))
            quedan = [l for l in una.split("\n") if sin_aprobacion.COMPUERTAS.search(l)]
            if quedan:
                problemas.append("%s@%s (%s): queda %r" % (rel, commit, origen, quedan[0][:90]))
    return problemas


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not git("log", "-1", "--format=%h", CLIENTES_DESDE):
        # sin la historia de git (instalación de cliente) NO se regenera:
        # una tabla vacía apagaría la migración en silencio.
        sys.exit("sin historia de git: la tabla no se toca")
    tabla_json, errores = generar()
    errores += verificar(tabla_json)
    if errores:
        print("\n".join("✗ " + e for e in errores))
        return 1
    out = {"_doc": "Generado por gen_sin_aprobacion_lines.py desde el historial de "
                   "templates/agent/brain. Cada fila: bloque viejo (old) → bloque de la plantilla "
                   "actual (new). Placeholders {{X}} se comparan como comodín; el resto, literal.",
           "files": tabla_json}
    texto = json.dumps(out, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
    if "--check" in argv:
        try:
            with open(DEST, encoding="utf-8") as fh:
                igual = fh.read() == texto
        except OSError:
            igual = False
        print("✓ al día" if igual else "✗ el JSON del disco no es el que se generaría")
        return 0 if igual else 1
    with open(DEST, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(texto)
    n = sum(len(v) for v in tabla_json.values())
    print("archivos: %d · bloques: %d → %s" % (len(tabla_json), n, DEST))
    return 0


if __name__ == "__main__":
    sys.exit(main())
