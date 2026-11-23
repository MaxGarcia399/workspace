#!/usr/bin/env python3
"""WORKSPACE · ws — háblale a tu agente desde la terminal, sin abrir nada.

    ws "resume la hoja de ventas"          a tu agente de siempre (el último que elegiste en el monito o aquí)
    ws -a turing "¿qué falló anoche?"      a otro agente (y lo recuerda)
    ws --agentes                           tus agentes

Lo mismo que el monito de escritorio, y en SU conversación (la del escritorio, aparte de la de la página): va por la
página local de Workspace (/api/v2), con el motor de ese agente. Te deja su respuesta en vivo, sus preguntas y la
tarjeta de permiso de su motor: un permiso solo se contesta con tu tecla, nunca solo. Ctrl+C deja de esperar (el
agente sigue y lo ves en el monito).
Stdlib."""
import os
import sys

AQUI = os.path.dirname(os.path.abspath(__file__))
RAIZ = os.path.dirname(AQUI)
if RAIZ not in sys.path:
    sys.path.insert(0, RAIZ)
from escritorio import cliente as C  # noqa: E402

TECLAS = {"p": "permitir", "s": "permitir_siempre", "n": "negar"}
GRIS, FIN = "\033[90m", "\033[0m"


def _color(hexa):
    try:
        r, g, b = int(hexa[1:3], 16), int(hexa[3:5], 16), int(hexa[5:7], 16)
        return "\033[1;38;2;%d;%d;%dm" % (r, g, b)
    except (TypeError, ValueError):
        return "\033[1m"


class Terminal:
    """Lo que el puente emite, escrito en la terminal. `preguntar(texto) → str` lee tu respuesta (None: sin teclado)."""

    def __init__(self, agente, salida=sys.stdout, preguntar=None, color=True):
        self.a, self.out, self.preguntar, self.color = agente, salida, preguntar, color
        self.escrito = ""                 # lo que ya salió del texto en vivo
        self.respuesta = None
        self.error = ""
        self.pendiente = None             # ("permiso"|"pregunta", evento) por contestar
        self.vistos = set()
        self.uso = ""

    def _g(self, s):
        return GRIS + s + FIN if self.color else s

    def _quien(self):
        return (_color(self.a["c"]) + "● " + self.a["n"] + FIN) if self.color else "● " + self.a["n"]

    def emitir(self, ev):
        t = ev.get("t")
        if ev.get("agente") not in (None, self.a["id"]):
            return
        if t == "estado" and ev.get("estado") == "pensando" and "pensando" not in self.vistos:
            self.vistos.add("pensando")
            self.out.write("%s %s\n" % (self._quien(), self._g("· pensando…")))
        elif t == "estado" and ev.get("estado") == "haciendo" and ev.get("hace"):
            self.out.write(self._g("  · %s\n" % ev["hace"]))
        elif t == "parcial":
            self._vivo(ev.get("texto") or "")
        elif t == "respuesta":
            self._vivo(ev.get("texto") or "")
            if self.escrito and not self.escrito.endswith("\n"):
                self.out.write("\n")
            self.respuesta = ev.get("texto") or ""
        elif t == "uso":
            self.uso = ev.get("linea") or ""
        elif t == "permiso" and (ev.get("id") or ev.get("en_terminal")) and ("p", ev.get("id")) not in self.vistos:
            self.vistos.add(("p", ev.get("id")))
            self.pendiente = ("permiso", ev)
        elif t == "pregunta" and ev.get("id") and ("q", ev.get("id")) not in self.vistos:
            self.vistos.add(("q", ev.get("id")))
            self.pendiente = ("pregunta", ev)
        elif t == "aviso" and ev.get("grave") and ev.get("texto"):
            self.error = ev["texto"]
        self.out.flush()

    def _vivo(self, texto):
        texto = texto.rstrip()
        if texto.startswith(self.escrito):
            self.out.write(texto[len(self.escrito):])
        else:                                          # su texto cambió de arriba: se escribe de nuevo, entero
            self.out.write("\n" + texto)
        self.escrito = texto

    def contestar(self, puente):
        """Lo que te pidió (permiso o pregunta), en la terminal. → True si contestaste."""
        k, ev = self.pendiente
        self.pendiente = None
        if self.escrito and not self.escrito.endswith("\n"):
            self.out.write("\n")
            self.escrito += "\n"
        if k == "permiso":
            self.out.write("%s te pide permiso: %s\n" % (self._quien(), ev.get("texto") or ""))
            if ev.get("corto"):
                self.out.write(self._g("  %s\n" % ev["corto"]))
            ops = [o for o in ev.get("opciones") or [] if o in TECLAS.values()]
            if ev.get("en_terminal") or not ops or self.preguntar is None:
                self.out.write(self._g("  Contéstalo en Compañero; aquí sigo esperando.\n"))
                return False
            menu = " · ".join("[%s] %s" % (t, {"permitir": "Permitir", "permitir_siempre": "Siempre", "negar": "No"}[d])
                              for t, d in TECLAS.items() if d in ops)
            while True:
                r = (self.preguntar("  %s › " % menu) or "").strip().lower()[:1]
                if TECLAS.get(r) in ops:
                    return puente.comando({"op": "permiso", "agente": self.a["id"], "id": ev["id"],
                                           "decision": TECLAS[r]})
        ops = ev.get("opciones") or []
        self.out.write("%s te pregunta: %s\n" % (self._quien(), ev.get("texto") or ""))
        if ev.get("en_terminal") or self.preguntar is None:
            self.out.write(self._g("  Contéstalo en su terminal o en la página; aquí sigo esperando.\n"))
            return False
        for i, o in enumerate(ops, 1):
            self.out.write("  %d) %s\n" % (i, o))
        r = (self.preguntar("  › ") or "").strip()
        if r.isdigit() and 1 <= int(r) <= len(ops):
            r = ops[int(r) - 1]
        if not r:
            return False
        self.escrito, self.respuesta = "", None
        return puente.comando({"op": "responder", "agente": self.a["id"], "id": ev["id"], "texto": r})


def _leer(prompt):
    try:
        return input(prompt)
    except EOFError:
        return None


def correr(texto, agente="", srv=None, salida=sys.stdout, preguntar=None, color=None, recordar=None,
           elegido_antes=None, max_vueltas=None):
    """Manda `texto` y espera la respuesta. → código de salida (0 bien · 1 algo falló · 2 uso)."""
    color = salida.isatty() if color is None else color
    srv = srv or C.conectar()
    if srv is None:
        salida.write("No encuentro la página local de Workspace y no la pude prender. Ábrela con: workspace web\n")
        return 1
    if not C.entiende_canal(srv):
        salida.write(C.PAGINA_VIEJA + "\n")       # no se mezcla con la conversación de la página
        return 1
    lista = C.agentes(srv)
    if not lista:
        salida.write("No tienes agentes en Workspace todavía.\n")
        return 1
    ids = [a["id"] for a in lista]
    if agente and agente not in ids:
        salida.write("No conozco a «%s». Tus agentes: %s\n" % (agente, ", ".join(ids)))
        return 2
    antes = C.leer_elegido() if elegido_antes is None else elegido_antes
    aid = agente or (antes if antes in ids else ids[0])
    a = next(x for x in lista if x["id"] == aid)
    term = Terminal(a, salida=salida, preguntar=preguntar, color=color)
    p = C.Puente(srv, term.emitir)
    p.lista, p.elegido = lista, aid
    if agente and recordar:
        recordar(aid)
    if not p.comando({"op": "mandar", "agente": aid, "texto": texto}):
        salida.write((term.error or "No se pudo mandar.") + "\n")
        return 1
    espera, vueltas = 0, 0
    try:
        while term.respuesta is None:
            vueltas += 1
            if max_vueltas is not None and vueltas > max_vueltas:
                return 1
            try:
                d = p.vivo(espera)
            except C.ErrorServidor as e:
                salida.write("Perdí la conexión con Workspace: %s\n" % e.texto)
                return 1
            espera = p.al_vivo(d)
            if term.pendiente:
                term.contestar(p)
            f = p.fotos.get(aid) or {}
            if term.error and f.get("estado") == "error" and aid not in p.turnos:
                salida.write(term.error + "\n")
                return 1
    except KeyboardInterrupt:
        salida.write("\n" + term._g("Dejé de esperar; %s sigue y lo ves en Compañero.\n" % a["n"]))
        return 130
    if term.uso:
        salida.write(term._g(term.uso) + "\n")
    return 0


def main(argv):
    argv = list(argv)
    if not argv or argv[0] in ("-h", "--help", "ayuda"):
        print(__doc__.split("\n\n")[1])
        return 0 if argv else 2
    if argv[0] == "--agentes":
        srv = C.conectar()
        if srv is None:
            print("No encuentro la página local de Workspace. Ábrela con: workspace web")
            return 1
        elegido = C.leer_elegido()
        for a in C.agentes(srv):
            print("%s %s%s" % ("●" if a["id"] == elegido else "·", a["id"], "  (%s)" % a["motor"] if a["motor"] else ""))
        return 0
    agente = ""
    if argv[0] in ("-a", "--agente"):
        if len(argv) < 3:
            print("Uso: ws -a <agente> \"texto\"")
            return 2
        agente, argv = argv[1], argv[2:]
    texto = " ".join(argv).strip()
    if not texto:
        print("¿Qué le digo? Uso: ws \"texto\"")
        return 2
    return correr(texto, agente, preguntar=_leer if sys.stdin.isatty() else None, recordar=C.guardar_elegido)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
