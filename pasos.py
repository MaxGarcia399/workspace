#!/usr/bin/env python3
"""WORKSPACE · pasos — el agente cuenta su avance al usar una skill, y la página lo pinta.

Cuando el socio arranca una skill desde Workspace en el navegador, la página le
escribe al agente qué skill usar y le pide que reporte sus pasos con este comando.
Así cualquier motor (Claude Code, Codex, Kiro…) muestra el mismo pipeline en vivo:

    workspace pasos <id> plan "Leer el brief" "Armar la propuesta" "Revisar"
    workspace pasos <id> ahora 2            # empieza el paso 2
    workspace pasos <id> hecho 2            # termina el paso 2
    workspace pasos <id> pide "Pásame el Excel de ventas" --archivo
    workspace pasos <id> pide "¿Para quién es?" --opcion "Clientes" --opcion "El equipo"
    workspace pasos <id> fin "Propuesta lista en deliverables/x/"

Lo que pide se ve en la caja de escribir de la página y del hub, con sus opciones como botones (pagina_v2 lo enseña
igual que una pregunta del MCP núcleo); la respuesta del socio le llega al agente como su siguiente mensaje.

`workspace pasos` (Windows: `workspace.cmd pasos`) es el comando preaprobado (N2, 17-nov);
`python3 pasos.py <id> …` hace lo mismo y sigue para lo que ya lo usaba.

Guarda `<cerebro>/STATE/ejecuciones/<id>.json` (el cerebro es la carpeta de trabajo
del agente: ningún sandbox se lo impide). Escritura atómica, sin dependencias.
El cerebro sale de WORKSPACE_BRAIN o, si no está, de la carpeta actual.
"""
import datetime
import json
import os
import re
import sys
import tempfile
import time

ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
MAX_PASOS = 30
MAX_TEXTO = 300          # un paso o una nota
MAX_PIDE = 2000          # lo que el agente le pide al socio (preguntas en lista caben enteras)
MAX_RESUMEN = 800
MAX_OPCIONES, MAX_OPCION = 12, 200    # las respuestas de un toque de lo que pide (como las de preguntar)
ANTES_DEL_PLAN = 3       # un «ahora N» / «hecho N» que llega antes que el plan (en paralelo), si N es de los primeros
#: Lo que llega en estos segundos después de su `pide` es de las mismas llamadas en paralelo (Copilot, en vivo 22-nov):
#: no lo borra. Contestarle lo borra Workspace (pagina_v2: el botón, la caja o el archivo), no el agente.
PIDE_JUNTO_S = 8


def _ahora():
    return datetime.datetime.now().isoformat(timespec="seconds")


def cerebro():
    return os.environ.get("WORKSPACE_BRAIN") or os.getcwd()


def carpeta(brain=None):
    return os.path.join(brain or cerebro(), "STATE", "ejecuciones")


def ruta(ejecucion, brain=None):
    if not ID_RE.match(str(ejecucion or "")):
        raise ValueError("id de ejecución inválido")
    return os.path.join(carpeta(brain), ejecucion + ".json")


def leer(ejecucion, brain=None):
    try:
        with open(ruta(ejecucion, brain), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def guardar(ejecucion, datos, brain=None):
    p = ruta(ejecucion, brain)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    datos["actualizado"] = _ahora()
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(p), prefix=".tmp-", suffix=".json")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=1)
        os.replace(tmp, p)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)
    return p


def _limpio(t, tope=MAX_TEXTO, renglones=False):
    """Sin caracteres de control (los saltos de renglón se quedan si `renglones`)."""
    malos = r"[\x00-\x09\x0b-\x1f\x7f]" if renglones else r"[\x00-\x1f\x7f]"
    t = re.sub(malos, " ", str(t or "")).strip()
    return t[:tope]


# ── skills-cierre (22-nov): la ejecución se pausa cuando nadie la cierra ──────────
#: Las que siguen abiertas (corren o te esperan): una de estas es «la que corre» en su conversación y no deja empezar
#: otra. `pausada` (se detuvo sin terminar) y `listo` no bloquean.
ABIERTAS = ("arrancando", "corriendo", "pide")
#: Por qué se detuvo: el turno acabó sin «fin», Parar, un error de su motor, le escribiste otra cosa mientras te
#: esperaba, o «Detener» de esa skill.
MOTIVOS = ("sin_fin", "parado", "error", "otro_mensaje", "detenida")


def abierta(d):
    return (d or {}).get("estado") in ABIERTAS


def paso_actual(d):
    """El número (desde 1) del paso en que va: el de ahora, si no el primero sin hacer; 0 sin plan."""
    ps = (d or {}).get("pasos") or []
    for i, p in enumerate(ps, 1):
        if p.get("estado") == "now":
            return i
    for i, p in enumerate(ps, 1):
        if p.get("estado") != "done":
            return i
    return len(ps)


def pausar(d, motivo, ahora=None):
    """LA pieza que detiene una ejecución abierta sin terminarla (el fin de su turno sin «fin», Parar, un error, tu
    respuesta a otra cosa, «Detener»): queda `pausada` con su motivo, el paso en que iba y lo que quedó pendiente.
    No bloquea otra skill; lo que el agente reporte después la retoma. → True si cambió."""
    if not abierta(d):
        return False
    pide = d.get("pide") or {}
    pendiente = _limpio(pide.get("texto") or d.get("pendiente") or "", MAX_PIDE, renglones=True)
    d["pausa"] = {"motivo": motivo if motivo in MOTIVOS else "sin_fin", "desde": ahora or _ahora(),
                  "paso": paso_actual(d), "pendiente": pendiente}
    d["estado"], d["pide"] = "pausada", None
    d.pop("pendiente", None)
    return True


def _norm(t):
    return " ".join(str(t or "").lower().split())


def soltar_pide(d):
    """Lo que te pedía ya no te espera: le contestaste (o le escribiste otra cosa). `pide` → `corriendo`; lo que pedía
    queda en `pendiente` (si el turno acaba sin que siga, la pausa lo dice: «quedó pendiente: ¿…?») y en `soltada`:
    decisión del 22-nov, el agente contesta lo tuyo y NO vuelve a preguntarlo; el mismo pide no la reabre hasta
    que pulses «Seguir». → True si cambió."""
    if (d or {}).get("estado") != "pide":
        return False
    d["pendiente"] = _limpio((d.get("pide") or {}).get("texto") or "", MAX_PIDE, renglones=True)
    d["soltada"] = d["pendiente"]
    d["estado"], d["pide"] = "corriendo", None
    return True


def contestada(d):
    """Le contestaste lo que pedía (con su botón o en la caja): `pide` → `corriendo`, sin pendiente. → True si cambió."""
    if not soltar_pide(d):
        return False
    d.pop("pendiente", None)
    d.pop("soltada", None)
    return True


def seguir(d):
    """«Seguir» de una pausada: vuelve a correr (su instrucción le dice al agente desde dónde). → True si cambió."""
    if (d or {}).get("estado") != "pausada":
        return False
    d["estado"] = "corriendo"
    d.pop("pausa", None)
    d.pop("soltada", None)                  # con «Seguir», ya puede volver a preguntar
    return True


def cerrar(d):
    """«Cerrar» de una pausada: se queda pausada, ya sin verse. → True si cambió."""
    if (d or {}).get("estado") != "pausada" or (d.get("pausa") or {}).get("cerrada"):
        return False
    d.setdefault("pausa", {})["cerrada"] = True
    return True


def _retomar(d, avanza=True):
    """Lo que reporta el agente sobre una pausada (o una que aún arrancaba) la retoma. `avanza`: siguió con la skill
    (otro paso, lo terminó, otra pregunta): lo que quedó pendiente de antes ya no lo está."""
    if not avanza:
        return
    d.pop("pausa", None)
    d.pop("pendiente", None)
    d.pop("soltada", None)
    if d.get("estado") in ("pausada", "arrancando"):
        d["estado"] = "corriendo"


#: Lo que el agente recibe si vuelve a pedir lo que el socio dejó pendiente al escribirle otra cosa.
NO_REPREGUNTES = ("no vuelvas a preguntar eso: el socio te escribió otra cosa y la skill queda en pausa hasta que él "
                  "pulse «Seguir» (lo ve en su caja: «Quedó pendiente»). Contéstale lo suyo y termina tu turno")


def _segundos_desde(iso):
    try:      # la «Z» (UTC) se lee también en Python 3.9; con zona, se compara contra la hora con zona
        d = datetime.datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        ahora = datetime.datetime.now(d.tzinfo) if d.tzinfo else datetime.datetime.now()
        return (ahora - d).total_seconds()
    except (TypeError, ValueError):
        return float("inf")


def _auto(n):
    return {"texto": "Paso %d" % n, "estado": "todo", "auto": True}


def aplicar(d, accion, args):
    """Aplica una acción al estado `d` (dict). → mensaje corto para el agente."""
    pasos = d.setdefault("pasos", [])
    d.setdefault("estado", "corriendo")
    if d.get("estado") == "listo" and accion in ("plan", "ahora", "hecho", "pide"):
        # C2: una que ya terminó no se reabre (OpenCode reusó un id viejo y la página la volvió a enseñar corriendo)
        raise ValueError("esa ejecución ya terminó (fin): para usar la skill otra vez, actívala de nuevo")
    if accion == "plan":
        textos = [_limpio(a) for a in args if _limpio(a)][:MAX_PASOS]
        if not textos:
            raise ValueError("plan necesita al menos un paso")
        # C4: un `ahora`/`hecho` que llegó antes que el plan conserva su avance; un plan no borra lo que pide
        antes = {i: p.get("estado") for i, p in enumerate(pasos) if p.get("estado") in ("done", "now")}
        d["pasos"] = [{"texto": t, "estado": antes.get(i, "todo")} for i, t in enumerate(textos)]
        pide = d.get("estado") == "pide"
        if d.get("soltada"):                     # un plan no es seguir: lo pendiente sigue pendiente
            return "plan con %d pasos" % len(textos)
        _retomar(d)
        d["estado"] = "pide" if pide else "corriendo"
        return "plan con %d pasos" % len(textos)
    if accion in ("ahora", "hecho"):
        try:
            n = int(args[0])
        except (IndexError, ValueError):
            raise ValueError("%s necesita el número del paso" % accion)
        if not pasos and 1 <= n <= ANTES_DEL_PLAN:
            # C4: llegó antes que el plan (llamadas en paralelo: Copilot y OpenCode): pasos provisionales; el plan les
            # pone su texto. Solo los primeros: un «ahora 9» sin plan sigue siendo un error
            pasos.extend(_auto(i) for i in range(1, n + 1))
        if not 1 <= n <= len(pasos):
            raise ValueError("no hay paso %d (el plan tiene %d)" % (n, len(pasos)))
        mismo = accion == "ahora" and pasos[n - 1]["estado"] == "now"
        if mismo and d.get("soltada"):           # el mismo paso no es seguir con la skill: nada cambia
            return "paso %d: %s" % (n, accion)
        _retomar(d)
        # C4: el mismo «ahora N» del paso que pregunta, o lo que llega en los segundos de su `pide` (en paralelo), no
        # lo borra
        repite = mismo or (
            d.get("estado") == "pide" and _segundos_desde((d.get("pide") or {}).get("desde")) < PIDE_JUNTO_S)
        if accion == "ahora":
            for p in pasos:
                if p["estado"] == "now":
                    p["estado"] = "todo"
            pasos[n - 1]["estado"] = "now"
            if len(args) > 1 and _limpio(args[1]):
                pasos[n - 1]["nota"] = _limpio(args[1])
        else:
            pasos[n - 1]["estado"] = "done"
        if d.get("estado") == "pide" and not repite:
            d["estado"], d["pide"] = "corriendo", None
        return "paso %d: %s" % (n, accion)
    if accion == "pide":
        archivo, opciones, resto, i = False, [], [], 0
        while i < len(args):
            a = args[i]
            if a == "--archivo":
                archivo = True
            elif a == "--opcion":
                if i + 1 >= len(args):
                    raise ValueError("--opcion necesita su texto")
                opciones.append(_limpio(args[i + 1], MAX_OPCION))
                i += 1
            elif a.startswith("--opcion="):
                opciones.append(_limpio(a[len("--opcion="):], MAX_OPCION))
            else:
                resto.append(a)
            i += 1
        texto = _limpio(" ".join(resto), MAX_PIDE, renglones=True)
        if not texto:
            raise ValueError("pide necesita decir qué necesitas")
        if d.get("soltada") and _norm(texto) == _norm(d["soltada"]):
            return NO_REPREGUNTES                # decisión del 22-nov: no la reabre (queda pendiente, en pausa al terminar)
        opciones = list(dict.fromkeys(o for o in opciones if o))
        if len(opciones) == 1 or len(opciones) > MAX_OPCIONES:
            raise ValueError("con opciones, de 2 a %d (--opcion \"…\" por cada una)" % MAX_OPCIONES)
        _retomar(d)
        d["estado"], d["pide"] = "pide", {"texto": texto, "archivo": archivo, "desde": _ahora()}
        if opciones:
            d["pide"]["opciones"] = opciones
        return ("pedido anotado: el socio lo verá en la caja de escribir%s. Termina tu turno aquí; su respuesta te "
                "llega como su próximo mensaje" % (" con %d opciones" % len(opciones) if opciones else ""))
    if accion == "fin":
        if d.get("estado") == "listo":
            return "ya estaba lista"
        for p in pasos:
            if p["estado"] != "done":
                p["estado"] = "done"
        _retomar(d)
        d["estado"], d["pide"], d["resumen"] = "listo", None, _limpio(" ".join(args), MAX_RESUMEN, renglones=True)
        return "listo"
    raise ValueError("acción desconocida: %s (usa plan, ahora, hecho, pide o fin)" % accion)


def actualizar(ejecucion, fn, brain=None):
    """Leer → `fn(d)` → guardar, con el candado de esa ejecución (el servidor de la página y el agente pueden tocarla a
    la vez: Copilot y OpenCode mandan sus llamadas en paralelo). Solo se guarda si `fn` devuelve algo verdadero. →
    (d, lo que devolvió fn); ({}, None) si no existe. Una `fn` que levanta no guarda nada."""
    try:
        p = ruta(ejecucion, brain)
    except ValueError:
        return {}, None
    with _candado(p):
        d = leer(ejecucion, brain)
        if not d:
            return {}, None
        r = fn(d)
        if r:
            guardar(ejecucion, d, brain)
        return d, r


def aplicar_en(ejecucion, accion, args, brain=None):
    """`aplicar` sobre la ejecución guardada, con su candado. → mensaje; ValueError si no existe o no se puede."""
    msg = []

    def hacer(d):
        msg.append(aplicar(d, accion, args))
        return True
    d, _r = actualizar(ejecucion, hacer, brain)
    if not d:
        raise ValueError("la ejecución %s no existe en este cerebro: usa el id que trae la instrucción" % ejecucion)
    return msg[0]


class SinCandado(ValueError):
    """No se pudo tomar el candado de la ejecución: no se escribió nada (el comando lo dice; se puede reintentar)."""


#: Cuántas veces se intenta tomar el candado si el sistema lo niega de pasada (un antivirus en Windows), y la pausa.
CANDADO_INTENTOS = 3
CANDADO_PAUSA_S = 0.1


class _candado(object):
    """El candado entre procesos de una ejecución (olock, fuera de lo que sincroniza el cerebro). Nunca se sigue sin
    él: el servidor de la página y el agente la tocan a la vez (Copilot y OpenCode mandan en paralelo) y sin candado
    uno pisaba al otro. Lo pasajero (el sistema niega el archivo del candado un momento) se reintenta; si sigue, o si
    otro lo tiene más de 5 s, o si olock no se puede usar: SinCandado, sin escribir nada."""

    def __init__(self, p):
        self.p, self._lk = p, None

    def __enter__(self):
        try:
            import olock
        except Exception as e:
            raise SinCandado("no pude tomar el candado de la ejecución (%s): no cambié nada; vuelve a intentarlo" % e)
        ultimo = None
        for intento in range(CANDADO_INTENTOS):
            lk = olock.local_lock(self.p, timeout=5)
            try:
                lk.__enter__()
            except olock.LockTimeout as e:      # otro la tiene: ya esperó 5 s
                ultimo = e
                break
            except OSError as e:                # el sistema lo negó: puede ser de pasada
                ultimo = e
                if intento + 1 < CANDADO_INTENTOS:
                    time.sleep(CANDADO_PAUSA_S * (intento + 1))
                continue
            self._lk = lk
            return self
        raise SinCandado("no pude tomar el candado de la ejecución (%s): no cambié nada; vuelve a intentarlo"
                         % (ultimo or "sin razón"))

    def __exit__(self, *a):
        lk, self._lk = self._lk, None
        return lk.__exit__(*a) if lk is not None else False


#: Lo demás que el agente le dice a Workspace, por este mismo comando preaprobado (interfaz_agente: lo mismo que las
#: herramientas del MCP núcleo, para los motores que no lo tienen). Un id de ejecución es «s-…»: no choca.
INTERFAZ = ("preguntar", "usar", "personalizar", "archivo")


def main(argv):
    if argv and argv[0] in INTERFAZ:
        import interfaz_agente
        return interfaz_agente.main(argv)
    if len(argv) < 2:
        print(__doc__.strip().split("\n\n")[1])
        return 2
    ejecucion, accion, args = argv[0], argv[1], argv[2:]
    try:
        if os.path.isfile(ruta(ejecucion)):
            msg = aplicar_en(ejecucion, accion, args)
        else:                                   # la de antes: el comando la crea si no existe
            d = {}
            msg = aplicar(d, accion, args)
            guardar(ejecucion, d)
    except ValueError as e:
        print("pasos: %s" % e, file=sys.stderr)
        return 2
    print("pasos: %s" % msg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
