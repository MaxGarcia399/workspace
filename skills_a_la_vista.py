"""WORKSPACE · skills_a_la_vista — el cerebro dice cómo se usa una skill a la vista del socio.

Diagnóstico en vivo del 21-nov (C2): pedida en palabras, Copilot, OpenCode y Kiro usaban la skill con la
herramienta de skills de SU motor y no con `usar_skill`: la página y el hub no la enseñaban. La plantilla del cerebro
(BRAIN.md §5 e INDEX-LITE.md) decía «cargar la skill → seguirla» sin nombrar usar_skill, y competía con la guía de
chat. La plantilla nueva ya lo dice; un cerebro que ya existe lo recibe aquí, por las tres puertas de siempre (la
migración 202611220100, cargar un agente y `workspace doctor --fix`), igual que skills_de_plantilla:

  · BRAIN.md gana un párrafo al final de su §5 (si no la encuentra, no se toca), con su marcador. En
    skills/INDEX-LITE.md (300 tokens, siempre cargado) la frase de la plantilla «→ cargar la skill → seguirla» pasa a
    «→ `usar_skill` → seguirla» en su lugar; si el socio la cambió, UNA línea al final que apunta a BRAIN.md §5, solo
    si cabe dejando lugar a la línea de la bandeja de aprendidas (skills_aprendidas); si no, ese archivo no se toca.
    Solo si todavía no nombran usar_skill.
  · Antes de escribir, una copia exacta en `<estado>/backups/<MID>/<agente>-<hash>/<archivo>`; sin copia no se toca.
  · Si el archivo cambió mientras tanto (una edición, un sync), no se toca ni se sella: la próxima puerta reintenta.
  · Se entrega UNA vez por cerebro: deja `.workspace/skills-a-la-vista.json`. Lo que el socio quite después no vuelve.
  · El mismo candado del cerebro que sin_aprobacion y skills_de_plantilla (los tres reescriben INDEX-LITE.md).

Determinista y sin rutas de esta máquina: dos equipos que sincronizan el cerebro escriben los mismos bytes.
"""
import hashlib
import json
import os
import re

import skills_de_plantilla as SP

ROOT = os.path.dirname(os.path.abspath(__file__))
MID = "202611220100_skills_a_la_vista"
MARCADOR = "workspace:skills-a-la-vista"
SELLO = ".workspace/skills-a-la-vista.json"
BLOQUES = {
    "BRAIN.md": (
        "<!-- workspace:skills-a-la-vista -->\n"
        "En la página o el hub de Workspace activo una skill con `usar_skill` (sin esa herramienta,\n"
        "`workspace pasos usar <skill>`), aunque mi motor tenga su propia herramienta de skills: así el socio\n"
        "la ve. Si ya me dieron su ejecución, no la activo otra vez; cuento mi avance con `reportar_avance`, y\n"
        "cada turno dentro de la skill termina con `pide` (y espero su respuesta) o con `fin`. Si mientras espero\n"
        "me escribe otra cosa, le contesto solo eso y no vuelvo a preguntar: queda en pausa hasta que pulse «Seguir».\n"),
    # INDEX-LITE: ver LITE_ANTES/LITE_AHORA. Si el socio cambió esa frase, esta línea al final (apunta a BRAIN.md §5,
    # donde vive el párrafo entero), solo si cabe.
    "skills/INDEX-LITE.md": "«Cargar» una skill = `usar_skill` (BRAIN.md §5).\n",
}
#: INDEX-LITE es lo de skills que se carga siempre (300 tokens, skills_aprendidas.LITE_TOKENS): no gana un párrafo. La
#: frase de la plantilla pasa a nombrar usar_skill en su lugar (y queda más corta); así sigue habiendo lugar para la
#: línea de la bandeja de aprendidas.
LITE_ANTES = "→ cargar la skill → seguirla"
LITE_AHORA = "→ `usar_skill` → seguirla"
ARCHIVOS = tuple(BLOQUES)
_S5 = re.compile(r"^##\s*5\b[^\n]*skill[^\n]*$", re.M | re.I)
_SIG = re.compile(r"^#{1,2}\s", re.M)


def _estado_sello(brain):
    """"falta" | "ok" | "ilegible" (vacío, JSON roto, carpeta o enlace: no es un sello)."""
    path = os.path.join(brain, *SELLO.split("/"))
    if not os.path.lexists(path):
        return "falta"
    if os.path.islink(path) or not os.path.isfile(path):
        return "ilegible"
    try:
        if os.path.getsize(path) == 0:
            return "ilegible"
        with open(path, encoding="utf-8-sig") as fh:
            ok = isinstance(json.load(fh), dict)
    except (OSError, ValueError, UnicodeDecodeError):
        return "ilegible"
    return "ok" if ok else "ilegible"


def _aplica(brain, root):
    if not brain or not os.path.isdir(brain) or os.path.islink(brain) or SP._dentro(brain, root):
        return False
    return any(os.path.isfile(os.path.join(brain, *rel.split("/"))) for rel in ARCHIVOS)


def _a_medias(brain):
    """¿`.workspace/` del cerebro está a medias (un sync)? Su agent.json o el sello de la guía no se leen: entonces no
    se toca nada (queda pendiente), como skills_de_plantilla."""
    return SP._agente(brain)[1] == "ilegible" or SP._estado_sello(brain) == "ilegible"


def _con_bloque(rel, texto):
    """El texto con su párrafo: en BRAIN.md al final de su §5 de skills (antes del encabezado que sigue: una BRAIN.md
    sin ella, como un puntero, no se toca); en INDEX-LITE.md, al final. None si no va."""
    nl = "\r\n" if "\r\n" in texto else "\n"
    bloque = BLOQUES[rel].replace("\n", nl)
    if rel == "BRAIN.md":
        m = _S5.search(texto)
        if m:
            sig = _SIG.search(texto, m.end())
            if sig:
                antes, despues = texto[:sig.start()], texto[sig.start():]
                return antes.rstrip("\r\n") + nl + nl + bloque + nl + despues
            return texto.rstrip("\r\n") + nl + nl + bloque
        return None
    if LITE_ANTES in texto:                       # la frase de la plantilla: en su lugar, más corta
        return texto.replace(LITE_ANTES, LITE_AHORA, 1)
    cuerpo = texto
    if cuerpo and not cuerpo.endswith(("\n", "\r")):
        cuerpo += nl
    return cuerpo + nl + bloque


#: Los estados de brain_format en que BRAIN.md es la identidad sana del cerebro. En cualquier otro (un puntero que llegó
#: por sync, dos identidades, una conversión a medias, un enlace…) BRAIN.md no se toca ni se sella: tocarla a media
#: conversión dejaría dos identidades distintas.
_BRAIN_SANA = ("v2", "v2-client-pointer", "v2-no-pointer")


def _brain_mala(brain):
    if not os.path.isfile(os.path.join(brain, "BRAIN.md")):
        return False
    try:
        import brain_format
        return brain_format.classify(brain, min_age=0)[0] not in _BRAIN_SANA
    except Exception:
        return True


def _brain_pendiente(brain):
    """Formato viejo (identidad en CLAUDE.md, aún sin BRAIN.md): su BRAIN.md llega con la conversión de formato; hasta
    entonces no se sella (si no, nunca recibiría su párrafo)."""
    return not os.path.isfile(os.path.join(brain, "BRAIN.md")) and os.path.isfile(os.path.join(brain, "CLAUDE.md"))


def _plan(brain, rel):
    """(bytes leídos, bytes nuevos) si ese archivo necesita el párrafo; None si no (no existe, enlace, no se lee como
    UTF-8, o ya nombra usar_skill)."""
    if SP._pasa_por_enlace(brain, rel) or (rel == "BRAIN.md" and _brain_mala(brain)):
        return None
    path = os.path.join(brain, *rel.split("/"))
    if not os.path.isfile(path) or os.path.islink(path):
        return None
    crudo = SP._leer_bytes(path)
    try:
        texto = crudo.decode("utf-8") if crudo is not None else None
    except UnicodeDecodeError:
        texto = None
    if texto is None or MARCADOR in texto or "usar_skill" in texto:
        return None
    nuevo = _con_bloque(rel, texto)
    if nuevo is not None and rel == "skills/INDEX-LITE.md" and LITE_ANTES not in texto and not _cabe_en_lite(nuevo):
        return None
    return (crudo, nuevo.encode("utf-8")) if nuevo is not None else None


def _cabe_en_lite(nuevo):
    """¿INDEX-LITE con su línea sigue dentro de su presupuesto HOT, con lugar para la de la bandeja de aprendidas (si
    todavía no la tiene)? La misma regla que la guía (skills_de_plantilla.cabe_en_lite)."""
    return SP.cabe_en_lite(nuevo)


def trabajos(brain, root=ROOT):
    """Los archivos que todavía necesitan su párrafo ([rel]). Vacío si no aplica, ya está al día o ya se entregó."""
    if not _aplica(brain, root) or _estado_sello(brain) != "falta" or _a_medias(brain):
        return []
    return [rel for rel in ARCHIVOS if _plan(brain, rel) is not None]


def backup_dir(state_dir, brain, name=None):
    real = os.path.realpath(brain)
    safe = re.sub(r"[^A-Za-z0-9_.-]", "-", name or os.path.basename(real)) or "cerebro"
    return os.path.join(state_dir, "backups", MID,
                        "%s-%s" % (safe, hashlib.sha256(real.encode("utf-8")).hexdigest()[:8]))


def _sellar(brain):
    path = os.path.join(brain, *SELLO.split("/"))
    if os.path.lexists(path):
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp-%d" % os.getpid()
    try:
        with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
            json.dump({"id": MID, "archivos": list(ARCHIVOS)}, fh, indent=2)
            fh.write("\n")
        try:
            os.link(tmp, path)
        except FileExistsError:
            pass
        except OSError:
            if not os.path.lexists(path):
                os.rename(tmp, path)
    finally:
        if os.path.lexists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


def _escribir(brain, rel, respaldo):
    """True si escribió; "cambio" si el archivo cambió mientras lo respaldaba; False si no hacía falta."""
    plan = _plan(brain, rel)
    if plan is None:
        return False
    crudo, nuevo = plan
    path = os.path.join(brain, *rel.split("/"))
    SP._respaldar(os.path.join(respaldo, *rel.split("/")), crudo)
    tmp = path + ".tmp-%d" % os.getpid()
    try:
        with open(tmp, "wb") as fh:
            fh.write(nuevo)
        if SP._leer_bytes(path) != crudo:
            return "cambio"
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass
    try:                       # el «deshacer» del formato v2 lo reconoce como cambio de Workspace
        import brain_format
        import paths
        brain_format.nota_cambio_de_workspace(brain, rel, crudo, nuevo, paths.state_dir())
    except Exception:
        pass
    return True


def actualizar(brain, root=ROOT, state_dir=None, name=None, dry_run=False, log=None, timeout=30):
    """Agrega el párrafo donde falte (con respaldo) y sella el cerebro. → [rel] escritos. Levanta OSError si el
    respaldo no se pudo guardar (el archivo queda como estaba) y olock.LockTimeout si el candado no se libera."""
    if dry_run:
        return trabajos(brain, root)
    if not _aplica(brain, root):
        return []
    with SP.candado(brain, timeout):
        if _a_medias(brain):
            if log is not None:
                try:
                    log(".workspace/ de este cerebro no se puede leer entero (¿un sync a medias?): no agregué cómo "
                        "usar las skills a la vista; queda para la próxima pasada")
                except Exception:
                    pass
            return []
        estado = _estado_sello(brain)
        if estado != "falta":
            if estado == "ilegible" and log is not None:
                try:
                    log("%s no se puede leer (vacío, dañado, carpeta o enlace): no agregué cómo usar las skills a "
                        "la vista. Bórralo, o espera a que termine el sync" % SELLO)
                except Exception:
                    pass
            return []
        if state_dir is None:
            import paths
            state_dir = paths.state_dir()
        respaldo = backup_dir(state_dir, brain, name)
        hechos, pospuesto = [], False
        for rel in ARCHIVOS:
            r = _escribir(brain, rel, respaldo)
            if r == "cambio":
                pospuesto = True
                if log is not None:
                    try:
                        log("%s cambió mientras lo respaldaba (¿un sync en curso?): reintento en la próxima pasada"
                            % rel)
                    except Exception:
                        pass
            elif r:
                hechos.append(rel)
        if not pospuesto and not _brain_mala(brain) and not _brain_pendiente(brain):
            _sellar(brain)
        return hechos
