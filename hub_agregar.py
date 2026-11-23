#!/usr/bin/env python3
r"""WORKSPACE · hub_agregar — «Agregar agente» en el hub: la tarjeta que se arma en Inicio (AG4-a · AG5-a · AG6-a ·
AG7-a; O4-b y O5-a en el primer arranque).

Al final de la fila de Inicio duerme un agente gris («Agente nuevo»). Tocarlo, Enter, o cualquier «+ Agregar» del hub
(`Directo.abrir_agregar`) abre la tarjeta grande en su lugar, con su monito a la izquierda (cambia en vivo):
  · 1 de 2 «¿Cómo me veo?»   cara, color, nombre (su comando se arma solo) y, si quieres, para qué; «Ya tengo un agente ›»;
  · 2 de 2 «¿Con qué pienso?» el motor que ya tiene tu sesión queda puesto (▲▼ cambia); si le falta tu sesión,
                             «Entrar a mi cuenta ↗» abre su inicio oficial (y al volver lo reviso) o «Despertar ya»
                             (despierta del todo cuando entres); sin motor, «Instalar Claude Code»; «▸ A tu medida»:
                             cómo habla, qué sí y qué no, sobre ti y dos interruptores;
  · Despertar                los 4 pasos humanos del job oficial (agent_create_job), por la página si contesta o aquí
                             mismo si no (agregar_logica.crear); Esc lo deja en el fondo;
  · ¡Hola!                   festeja; una sola vez, lo que gasta tokens o sale a internet («Me afino con IA», «Busco
                             skills»), con el foco en «No gracias»; luego Inicio con el agente nuevo elegido.
  Primer arranque (modo «primera»): la misma tarjeta con el paso «Tú» antes (3 pasos) y su constancia al terminar.
  «Ya tengo un agente»: lo que encontré en esta computadora (con su monito) y pegar o arrastrar su carpeta, con lo que
  trae antes de conectar. Los errores salen dentro de la tarjeta, en simple, con el botón que los arregla.

Aquí viven su estado (`Tarjeta`: teclas, clics, lo que pide en el fondo) y su dibujo (`pantalla`); hub_directo solo
le pasa las teclas y los clics mientras está abierta. Stdlib."""
import os
import sys
import time

AQUI = os.path.dirname(os.path.abspath(__file__))
if AQUI not in sys.path:
    sys.path.insert(0, AQUI)
import hub_paleta as P  # noqa: E402
import hub_bloque as B  # noqa: E402
import hub_h1 as H  # noqa: E402
import hub_monitos as MON  # noqa: E402
import agregar_logica as AL  # noqa: E402
import agent_create_params as ACP  # noqa: E402

C = P.C
W, corto = B.W, B.corto
BG, P1, P2, P3, P4 = B.BG, B.P1, B.P2, B.P3, B.P4
OK, WARN, LUZ, LUZTX = B.OK, B.WARN, B.LUZ, B.LUZTX
ROJO = "#e5534b"
GRIS = AL.GRIS
NUEVO = AL.NUEVO_ID
try:
    from localhost_front import FORMAS, COLORES
except Exception:                                   # falla-suave: la paleta de los monitos
    FORMAS = ("bolita", "pico", "cuadrito", "gatito", "fantasma", "nube")
    COLORES = ("#ff4fa3", "#3fbf7f", "#3b82f6", "#e7a43a", "#8b5cf6", "#ffffff")
#: Cada cuánto se relee el job (s); cada cuánto los motores mientras alguno se verifica o vuelves de entrar.
JOB_S, MOTORES_S = 0.5, 2.0
#: Cuánto festeja el monito al despertar.
FIESTA_S = 2.4
TOPE_NOMBRE, TOPE_TEXTO, TOPE_RUTA = 40, 600, 1000
#: Teclas de texto: lo que edita el campo con el foco.
CAMPOS = ("tu", "nombre", "para", "como", "quesi", "sobre", "ruta")


def _t(clave, **kw):
    """El texto en el idioma de la tarjeta (agregar_logica.idioma: el del hub; en la v1, español para todos)."""
    return AL._t(clave, **kw)


def dormido():
    """El agente gris que duerme al final de la fila de Inicio (no es un agente: la tarjeta para crear uno)."""
    return {"id": NUEVO, "n": _t("agregar.dormido.nombre"), "c": GRIS, "f": "bolita", "st": "duerme", "nuevo": True,
            "mid": ""}


def avatar_libre():
    """(cara, color) por omisión: los primeros que ningún agente de esta computadora usa (como la página)."""
    usados_f, usados_c = set(), set()
    try:
        import localhost_front as F
        for v in (F.leer_prefs().get("agentes") or {}).values():
            av = (v.get("avatar") or {}) if isinstance(v, dict) else {}
            usados_f.add(av.get("forma"))
            usados_c.add(av.get("color"))
    except Exception:
        pass
    f = next((i for i, x in enumerate(FORMAS) if x not in usados_f), 0)
    c = next((i for i, x in enumerate(COLORES) if x not in usados_c), 0)
    return f, c


def _editar(texto, k, tope):
    """El texto tras la tecla `k` (None si `k` no edita): ⌫ borra, ^U vacía, pegar agrega (en una línea)."""
    if isinstance(k, P.Pegado):
        return (texto + " ".join(str(k).replace("\r", "\n").split("\n")).strip("\n"))[:tope]
    if k == "borrar":
        return texto[:-1]
    if k == "ctrl-u":
        return ""
    if isinstance(k, str) and len(k) == 1 and k.isprintable():
        return (texto + k)[:tope]
    return None


class Tarjeta:
    """El estado de la tarjeta abierta. `app`: el Directo del hub (su srv, su candado, en_fondo, _plan_login…).
    `modo`: crear · cargar · primera."""

    def __init__(self, app, modo="crear", reloj=None):
        self.app, self.reloj = app, reloj or getattr(app, "reloj", None) or time.monotonic
        self.modo = modo if modo in ("crear", "cargar", "primera") else "crear"
        self.primera = self.modo == "primera"
        self.visible = True
        self.desde_cargar = self.modo == "cargar"
        self.paso = "tu" if self.primera else ("cargar" if self.modo == "cargar" else "ver")
        self.tu = AL.nombre_de_la_cuenta() if self.primera else ""
        self.forma, self.color = avatar_libre()
        self.color_puesto = False
        self.nombre = self.para = self.como = self.quesi = self.sobre = ""
        self.sw = [True, False]
        self.motores, self.motores_t, self.pidiendo, self.motor, self.motor_puesto = None, -1e9, False, None, False
        self.verificando_desde = None
        self.via, self.job, self.job_t, self.pidiendo_job = None, None, -1e9, False
        self.sin_sesion, self.comando, self.visible_nombre, self.params = False, "", "", {}
        self.err, self.aviso, self.aviso_t = None, "", -1e9
        self.hola_t, self.ofertas, self.afina, self.skills = None, {}, None, None
        self.cargar = {"estado": "", "lista": [], "avisos": [], "protegidas": False, "mac": AL.es_mac(), "i": 0,
                       "ruta": "", "radio": None, "radio_de": None}
        self.carga = None
        self.tras_ceder, self.terminado = None, None
        self._rev = (None, None)
        self.foco, self.foco_auto = "", True
        if self.paso == "cargar":
            self._buscar()
        r = AL.restos()
        if r and not self.desde_cargar:
            self._error_interrumpida(r)
        self.pedir_motores()
        self._foco_inicial()
        try:                                                # AG3-a: «el hub todavía está solo en español», en tu idioma
            import hub_directo
            aviso = hub_directo.aviso_idioma() if hasattr(hub_directo, "aviso_idioma") else ""
        except Exception:
            aviso = ""
        if aviso and not self.err:
            self._avisar(aviso)

    # ── utilidades ──
    def _fondo(self, fn):
        (getattr(self.app, "en_fondo", None) or AL.en_fondo)(fn)

    def _lock(self):
        return getattr(self.app, "lock", None) or _SinCandado()

    def _srv(self):
        return getattr(self.app, "srv", None)

    def _avisar(self, texto):
        self.aviso, self.aviso_t = texto, self.reloj()

    def total(self):
        return 3 if self.primera else 2

    def num_paso(self):
        orden = (["tu"] if self.primera else []) + ["ver", "motor"]
        p = "motor" if self.paso == "medida" else self.paso
        return orden.index(p) + 1 if p in orden else None

    def color_hex(self):
        """El color del monito: el elegido; si ya tiene nombre, el libre; si no, gris (todavía duerme sin forma)."""
        if self.color_puesto or self.nombre.strip() or self.paso not in ("tu", "ver", "cargar"):
            return COLORES[self.color % len(COLORES)]
        return GRIS

    def revision(self):
        """revisar_nombre del nombre escrito (recordado: se pregunta en cada cuadro)."""
        if self._rev[0] != self.nombre:
            self._rev = (self.nombre, AL.revisar_nombre(self.nombre))
        return self._rev[1]

    def motor_fila(self, mid=None):
        mid = mid or self.motor
        return next((m for m in self.motores or () if m.get("id") == mid), None)

    # ── los motores (O5-a) ──
    def pedir_motores(self, verificar=False):
        if self.pidiendo:
            return
        self.pidiendo = True
        srv = self._srv()

        def hacer():
            lista = AL.motores(srv, verificar=verificar)
            with self._lock():
                self.pidiendo = False
                self.motores_t = self.reloj()
                if lista is None:
                    return
                self.motores = [m for m in lista if m.get("id") != "stub"]
                if not self.motor_puesto or not self.motor_fila():
                    defecto = None
                    try:
                        import settings
                        defecto = settings.get("modelos.default_engine", None)
                    except Exception:
                        pass
                    self.motor = AL.elegir_motor(self.motores, defecto) or (
                        "claude-code" if self.motor_fila("claude-code") else
                        (self.motores[0]["id"] if self.motores else None))
                if self.foco_auto and self.paso == "motor" and not self.err:
                    self._foco_inicial()                # llegaron los motores: el foco, al botón que toca ahora
        self._fondo(hacer)

    def _verificando(self):
        return any(m.get("estado") == "verificando" for m in self.motores or () if m.get("instalado"))

    def estado_motor(self, m):
        """(clave, texto, color): listo · confirmar (no se pudo saber su sesión: se puede despertar igual) · entrar ·
        instalar · viendo · revisar (le falta otra cosa: su modelo, su versión…; el chip lo dice en simple)."""
        if m is None:
            return "viendo", _t("agregar.motor.viendo"), C["tx3"]
        if AL.usable(m):
            return "listo", _t("agregar.motor.listo"), OK
        if not m.get("instalado"):
            return "instalar", _t("agregar.motor.no_instalado"), C["tx3"]
        e = m.get("estado")
        if e == "verificando":
            return "viendo", _t("agregar.motor.viendo"), C["tx3"]
        if e == "sin_sesion" or m.get("sesion") is False:
            return "entrar", _t("agregar.motor.falta"), WARN
        falta = AL.que_le_falta(m)
        if falta == "sin_confirmar":
            return "confirmar", _t("agregar.motor.chip.sin_confirmar"), C["tx3"]
        return "revisar", _t("agregar.motor.chip.%s" % falta), WARN

    def _motor_paso(self, d):
        ms = self.motores or []
        if not ms:
            return
        ids = [m["id"] for m in ms]
        j = (ids.index(self.motor) + d) % len(ids) if self.motor in ids else 0
        self.motor, self.motor_puesto = ids[j], True

    # ── el foco y las teclas ──
    def focos(self):
        """Lo que se enfoca en el paso de ahora, en orden (Tab/↓ el siguiente)."""
        if self.err:
            return [b[0] for b in self.err["botones"]]
        p = self.paso
        if p == "tu":
            return ["agr:tu", "agr:siguiente", "agr:cargar"]
        if p == "ver":
            r = self.revision()
            extra = ["agr:usar"] if r.get("clave") in ("repetido", "programa") and r.get("libre") else []
            return ["agr:cara", "agr:color", "agr:nombre"] + extra + ["agr:para", "agr:siguiente", "agr:cargar"]
        if p == "motor":
            return ["agr:motor", "agr:medida"] + [b[0] for b in self.botones_motor()]
        if p == "medida":
            return ["agr:como", "agr:quesi", "agr:sobre", "agr:sw:0", "agr:sw:1"] + \
                [b[0] for b in self.botones_motor()][:1] + ["agr:cerrar"]
        if p == "creando":
            return ["agr:cancelar"]
        if p == "hola":
            out = []
            for k in ("afinar", "skills"):
                if self.ofertas.get(k) == "?":
                    out += ["agr:of:%s:si" % k, "agr:of:%s:no" % k]
            return out + [b[0] for b in self.botones_hola()]
        if p == "skills":
            sk = self.skills or {}
            return ["agr:sk:%d" % i for i in range(len(sk.get("lista") or []))] + \
                (["agr:instalar_skills"] if sk.get("lista") and sk.get("estado") == "elige" else []) + ["agr:atras"]
        if p == "cargar":
            c = self.cargar
            out = ["agr:enc:%d" % i for i in range(len(c["lista"]))] + ["agr:ruta"]
            if c["mac"] and not c["protegidas"] and c["estado"] == "listo":
                out.append("agr:protegidas")
            return out + [b[0] for b in self.botones_cargar()]
        if p in ("conectando", "conectado"):
            return [b[0] for b in self.botones_conectado()] if p == "conectado" else []
        return []

    def _foco_inicial(self):
        self.foco_auto = True                           # hasta que muevas el foco tú
        fs = self.focos()
        pref = {"tu": "agr:tu", "ver": "agr:nombre", "motor": None, "medida": "agr:como", "cargar": "agr:ruta",
                "hola": None, "creando": "agr:cancelar"}.get(self.paso)
        if self.err:
            self.foco = fs[0] if fs else ""
        elif self.paso == "motor":
            bs = self.botones_motor()
            self.foco = bs[0][0] if bs else "agr:motor"
        elif self.paso == "hola":
            self.foco = next((f for f in fs if f.endswith(":no")), fs[0] if fs else "")
        elif self.paso == "cargar" and self.cargar["lista"]:
            self.foco = "agr:enc:0"
        else:
            self.foco = pref if pref in fs else (fs[0] if fs else "")

    def _mover(self, d):
        fs = self.focos()
        if not fs:
            return
        i = fs.index(self.foco) if self.foco in fs else -1
        self.foco = fs[(i + d) % len(fs)] if i >= 0 else fs[0]

    def _ir(self, paso):
        self.paso, self.err = paso, None
        self._foco_inicial()

    def tecla(self, k):
        """→ None (sigue), «salir», «cerrar» (la tarjeta se cierra) o un plan para el hub (entrar a su cuenta…)."""
        if k == "ctrl-c":
            return "salir"
        if k in ("tab", "shift-tab", "izquierda", "derecha"):
            self.foco_auto = False
        f = self.foco
        campo = f[4:] if f.startswith("agr:") and f[4:] in CAMPOS else None
        primero = {"tu": "agr:tu", "ver": "agr:nombre", "medida": "agr:como"}.get(self.paso)
        if primero and campo is None and not self.err and (isinstance(k, P.Pegado) or (
                isinstance(k, str) and len(k) == 1 and k.isprintable() and k != " " and
                not (self.paso == "hola"))):
            self.foco, campo = primero, primero[4:]           # escribir lleva al primer campo del paso
        if self.paso == "cargar" and campo is None and (isinstance(k, P.Pegado) or
                                                        (isinstance(k, str) and len(k) == 1 and k.isprintable()
                                                         and k not in (" ", "a"))):
            self.foco, campo = "agr:ruta", "ruta"         # pegar o arrastrar una carpeta, desde cualquier fila
        if campo and k not in ("enter", "tab", "shift-tab", "esc", "arriba", "abajo") and \
                not (k in ("izquierda", "derecha") and campo != "ruta"):
            nuevo = _editar(self._campo(campo), k, TOPE_RUTA if campo == "ruta" else
                            (TOPE_NOMBRE if campo in ("tu", "nombre") else TOPE_TEXTO))
            if nuevo is not None:
                if campo == "ruta" and isinstance(k, P.Pegado) and not self._campo("ruta").strip():
                    self._poner(campo, str(k), pegado=True)
                else:
                    self._poner(campo, nuevo)
                return None
        if k == "esc":
            return self._atras()
        if self.paso in ("motor", "medida") and k in ("arriba", "abajo") and f == "agr:motor":
            self._motor_paso(-1 if k == "arriba" else 1)
            return None
        if self.paso == "motor" and k in ("arriba", "abajo") and f != "agr:motor" and not self.err:
            self._motor_paso(-1 if k == "arriba" else 1)        # ▲▼ cambia el motor desde donde estés
            return None
        if k in ("tab", "abajo"):
            self._mover(1)
            return None
        if k in ("shift-tab", "arriba"):
            self._mover(-1)
            return None
        if k in ("izquierda", "derecha"):
            d = 1 if k == "derecha" else -1
            if self.paso in ("ver", "tu") and not self.err and f in ("agr:color",):
                self.color, self.color_puesto = (self.color + d) % len(COLORES), True
            elif self.paso == "ver" and not self.err and f in ("agr:cara", "agr:nombre", "agr:para"):
                self.forma = (self.forma + d) % len(FORMAS)
            else:
                self._mover(d)
            return None
        if k == " " and (f.startswith("agr:sw:") or f.startswith("agr:sk:") or f in ("agr:cara", "agr:color")):
            return self.clic(f)
        if k == "s" and self.paso == "hola" and not self.err:
            return self.clic("agr:sesiones")
        if k == "a" and self.paso == "cargar" and not self.err:
            return self.clic("agr:nuevos")
        if k == "enter":
            if f.startswith("agr:") and f[4:] not in CAMPOS and f not in ("agr:cara", "agr:color", "agr:motor") \
                    and not f.startswith("agr:sw:"):
                return self.clic(f)
            return self._principal()
        return None

    def _campo(self, campo):
        return self.cargar["ruta"] if campo == "ruta" else getattr(self, campo)

    def _poner(self, campo, v, pegado=False):
        if campo == "ruta":
            if pegado:                                    # lo arrastrado o pegado, ya limpio (sin «\ » ni comillas)
                v = AL.limpiar_ruta(v) or v
            self.cargar["ruta"] = v
            self._radiografia()
        else:
            setattr(self, campo, v)

    def _atras(self):
        if self.err:
            t = self.err.get("atras")
            self.err = None
            if t:
                self._ir(t)
            else:
                self._foco_inicial()
            return None
        p = self.paso
        if p == "tu":
            return "cerrar"
        if p == "ver":
            if self.primera:
                self._ir("tu")
                return None
            return "cerrar"
        if p == "motor":
            self._ir("ver")
        elif p == "medida":
            self._ir("motor")
        elif p == "creando":
            self.visible = False                          # sigue en el fondo; aviso al terminar
            return "cerrar"
        elif p == "hola":
            return self._terminar("inicio")
        elif p in ("skills", "afina"):
            if p == "skills" and (self.skills or {}).get("estado") == "instalando":
                return None
            self._ir("hola")
        elif p == "cargar":
            if self.desde_cargar and not self.primera:
                return "cerrar"
            self._ir("tu" if self.primera and not self.nombre else "ver")
        elif p == "conectado":
            return self._terminar("inicio")
        return None

    def _principal(self):
        """Enter en un campo: lo que hace el botón principal del paso."""
        p = self.paso
        if self.err:
            return self.clic(self.err["botones"][0][0])
        if p == "tu":
            return self.clic("agr:siguiente")
        if p == "ver":
            return self.clic("agr:siguiente")
        if p in ("motor", "medida"):
            bs = self.botones_motor()
            return self.clic(bs[0][0]) if bs else None
        if p == "cargar":
            bs = self.botones_cargar()
            return self.clic(bs[0][0]) if bs and bs[0][2] else None
        if p == "hola":
            return self.clic(self.botones_hola()[0][0])
        if p == "conectado":
            return self.clic(self.botones_conectado()[0][0])
        if p == "skills" and (self.skills or {}).get("estado") == "elige":
            return self.clic("agr:instalar_skills")
        return None

    # ── los botones de cada paso: [(rid, etiqueta, principal)] ──
    def botones_motor(self):
        m = self.motor_fila()
        clave = self.estado_motor(m)[0] if self.motores is not None else "viendo"
        n = AL.nombre_motor(self.motor) if self.motor else ""
        if self.motores is not None and not self.motores:
            return [("agr:instalar", _t("agregar.boton.instalar", m="Claude Code"), True),
                    ("agr:despertar", _t("agregar.boton.despertar_igual"), False)]
        if clave == "entrar":
            return [("agr:entrar", _t("agregar.boton.entrar"), True),
                    ("agr:despertar", _t("agregar.boton.despertar_igual"), False)]
        if clave == "instalar":
            return [("agr:instalar", _t("agregar.boton.instalar", m=n), True),
                    ("agr:despertar", _t("agregar.boton.despertar_igual"), False)]
        return [("agr:despertar", _t("agregar.boton.despertar"), True), ("agr:atras", _t("agregar.boton.atras"), False)]

    def botones_hola(self):
        if self.sin_sesion:
            m = self.motor_fila()
            if m is not None and not m.get("instalado"):
                return [("agr:instalar", _t("agregar.boton.instalar", m=AL.nombre_motor(self.motor)), True),
                        ("agr:fin", _t("agregar.boton.inicio"), False)]
            return [("agr:entrar", _t("agregar.boton.entrar"), True), ("agr:fin", _t("agregar.boton.inicio"), False)]
        return [("agr:conversar", _t("agregar.boton.conversar"), True), ("agr:sesiones", _t("agregar.boton.sesiones"),
                                                                       False)]

    def botones_cargar(self):
        c = self.cargar
        out = []
        sel = self._fila_cargar()
        if sel is not None:
            if sel["estado"] in ("nuevo", "otro"):          # «ya está» o «a medias»: no hay nada que conectar
                out.append(("agr:conectar", _t("agregar.boton.conectar_a", n=sel["visible"]), True))
        elif sel is None and (c.get("radio") or {}).get("veredicto") in ("agente", "choque"):
            info = c["radio"]
            out.append(("agr:conectar", _t("agregar.boton.conectar_a",
                                           n=info.get("display") or (info.get("name") or "").capitalize()), True))
        nuevos = [x for x in c["lista"] if x["estado"] == "nuevo"]
        if len(nuevos) >= 2:
            out.append(("agr:nuevos", _t("agregar.boton.los_nuevos", n=len(nuevos)), False))
        out.append(("agr:atras", _t("agregar.boton.atras"), False))
        return out

    def botones_conectado(self):
        if self.sin_sesion_conectado():
            m = self.motor_fila()
            if m is not None and not m.get("instalado"):
                return [("agr:instalar", _t("agregar.boton.instalar", m=AL.nombre_motor(self.motor)), True),
                        ("agr:fin", _t("agregar.boton.inicio"), False)]
            return [("agr:entrar", _t("agregar.boton.entrar"), True), ("agr:fin", _t("agregar.boton.inicio"), False)]
        return [("agr:fin", _t("agregar.boton.inicio") + " ↵", True)]

    def _fila_cargar(self):
        """La fila encontrada con el foco (o None si el foco está en la carpeta pegada o un botón)."""
        f = self.foco
        lista = self.cargar["lista"]
        if f.startswith("agr:enc:"):
            i = int(f[8:])
            self.cargar["i"] = i
            return lista[i] if 0 <= i < len(lista) else None
        if f in ("agr:conectar", "agr:nuevos", "agr:protegidas", "agr:atras") and lista and \
                not self.cargar["ruta"].strip():
            i = self.cargar.get("i") or 0
            return lista[i] if 0 <= i < len(lista) else None
        return None

    # ── los clics (y Enter sobre un botón) ──
    def clic(self, rid):
        self.foco_auto = False
        p, _s, resto = rid.partition(":")
        if p == "bar" and resto == "salir" or rid == "agr:cerrar_tarjeta":
            if self.paso == "creando":
                self.visible = False
            return "cerrar"
        if p != "agr":
            return None
        if self.err:
            return self._clic_error(rid)
        if rid.startswith("agr:cara:"):
            self.forma, self.foco = int(rid[9:]) % len(FORMAS), "agr:cara"
            return None
        if rid.startswith("agr:color:"):
            self.color, self.color_puesto, self.foco = int(rid[10:]) % len(COLORES), True, "agr:color"
            return None
        if rid == "agr:cara":
            self.forma = (self.forma + 1) % len(FORMAS)
            return None
        if rid == "agr:color":
            self.color, self.color_puesto = (self.color + 1) % len(COLORES), True
            return None
        if rid in ("agr:tu", "agr:nombre", "agr:para", "agr:como", "agr:quesi", "agr:sobre", "agr:ruta"):
            self.foco = rid
            return None
        if rid in ("agr:mot:arriba", "agr:mot:abajo", "agr:motor"):
            self._motor_paso(-1 if rid == "agr:mot:arriba" else 1)
            self.foco = "agr:motor"
            return None
        if rid.startswith("agr:sw:"):
            i = int(rid[7:])
            self.sw[i] = not self.sw[i]
            self.foco = rid
            return None
        if rid.startswith("agr:enc:"):
            if self.foco == rid:
                return self.clic("agr:conectar")
            self.foco = rid
            self.cargar["i"] = int(rid[8:])
            return None
        if rid.startswith("agr:sk:"):
            return self._marcar_skill(int(rid[7:]))
        if rid.startswith("agr:of:"):
            _a, _o, cual, que = rid.split(":")
            return self._oferta(cual, que)
        acc = rid[4:]
        fn = getattr(self, "_b_" + acc, None)
        return fn() if fn else None

    def _b_siguiente(self):
        if self.paso == "tu":
            if not self.tu.strip():
                self._avisar(_t("agregar.tu.vacio"))
                return None
            nombre = self.tu.strip()

            def hacer():
                AL.fijar_persona(nombre)
            self._fondo(hacer)
            self._ir("ver")
            return None
        r = self.revision()
        c = r.get("clave")
        if c == "ok":
            self._ir("motor")
            if self.motores is None or self.reloj() - self.motores_t > 30:
                self.pedir_motores()
            return None
        if c == "carpeta_agente":
            self._error_carpeta(r)
            return None
        self.foco = "agr:usar" if c in ("repetido", "programa") and r.get("libre") else "agr:nombre"
        self._avisar(AL.texto_nombre(r))
        return None

    def _b_usar(self):
        """«Usar «nilo-2»»: el nombre libre, escrito como lo escribiste («Nilo» → «Nilo 2»)."""
        r = self.revision()
        libre = r.get("libre")
        if libre:
            n = libre.rsplit("-", 1)[-1]
            propuesto = " ".join(self.nombre.split()) + " " + n
            self.nombre = propuesto if AL.comando_de(propuesto) == libre else libre
            self.foco = "agr:nombre"
        return None

    def _b_cargar(self):
        self.desde_cargar = False
        self._ir("cargar")
        self._buscar()
        return None

    def _b_medida(self):
        self._ir("medida")
        return None

    def _b_cerrar(self):
        self._ir("motor")
        return None

    def _b_atras(self):
        return self._atras()

    def _b_entrar(self):
        mid = self.motor
        if not mid:
            return None
        try:
            import engine_install
            import shutil
            login = list((engine_install.recipe(mid) or {}).get("login_cmd") or [])
            hay = bool(login) and bool(shutil.which(login[0]))
        except Exception:
            hay = False
        if not hay or not hasattr(self.app, "_plan_login"):
            self._avisar(_t("agregar.motor.nota_revisar", m=AL.nombre_motor(mid), e=_t("agregar.motor.falta")))
            return None
        plan = self.app._plan_login(mid)
        if isinstance(plan, dict):
            self.tras_ceder = mid
        return plan

    def _b_instalar(self):
        mid = self.motor if self.motores else "claude-code"
        if not mid:
            mid = "claude-code"
        self.tras_ceder = mid
        # una sola puerta para las acciones de un motor: motor_accion.py (el que cierra las pantallas de antes), que
        # delega instalar/entrar en motores_logica.correr_accion; si todavía no está, motores_logica directo
        unica = os.path.join(AQUI, "motor_accion.py")
        argv = [P.PY, unica, mid, "install"] if os.path.exists(unica) else \
            [P.PY, os.path.join(AQUI, "motores_logica.py"), "instalar", mid]
        return {"programa": "instalar", "motor": mid, "argv": argv}

    def _b_despertar(self):
        r = self.revision()
        if r.get("clave") != "ok":
            self._ir("ver")
            return self._b_siguiente()
        if not self.motor:
            self.motor = "claude-code"
        self.comando = r["comando"]
        self.visible_nombre = " ".join(self.nombre.split())[:TOPE_NOMBRE]
        campos = AL.campos_de_crear(self.comando, self.visible_nombre, self.para, self.como, self.quesi, self.sobre,
                                    forma=FORMAS[self.forma % len(FORMAS)], color=COLORES[self.color % len(COLORES)],
                                    motor=self.motor, autonomia=self.sw[0], revisar_skills=self.sw[1])
        self.params = ACP.desde_tarjeta(self.comando, self.visible_nombre, self.para, self.como, self.quesi,
                                        self.sobre, motor=self.motor, autonomia=self.sw[0],
                                        revisar_skills=self.sw[1], dueno=AL.persona())
        self.via, self.job, self.sin_sesion = None, None, False
        self._ir("creando")
        srv = self._srv()

        def hacer():
            r = AL.crear(campos, srv)
            with self._lock():
                if r.get("ok"):
                    self.via, self.job = r.get("via"), r.get("job")
                    self.sin_sesion = bool(r.get("sin_sesion"))
                    self.job_t = self.reloj()
                else:
                    self._error_crear(r)
        self._fondo(hacer)
        return None

    def _b_cancelar(self):
        if self.via:
            via, srv = self.via, self._srv()
            self._fondo(lambda: AL.cancelar(via, srv))
        return None

    def _b_conversar(self):
        return self._terminar("conversar")

    def _b_sesiones(self):
        return self._terminar("sesiones")

    def _b_fin(self):
        return self._terminar("inicio")

    # ── crear: lo que pasa en el fondo ──
    def tick(self):
        """Lo que se pide solo mientras la tarjeta vive (cada cuadro, sin bloquear)."""
        ahora = self.reloj()
        if self.tras_ceder:                                 # de vuelta de entrar a su cuenta o de instalar
            mid, self.tras_ceder = self.tras_ceder, None
            self.verificando_desde = ahora
            self.pedir_motores(verificar=True)
            self._avisar(_t("agregar.motor.volvio", m=AL.nombre_motor(mid)))
        if self.paso in ("motor", "medida", "hola") and not self.pidiendo and \
                (self._verificando() or (self.verificando_desde is not None and ahora - self.verificando_desde < 20)) \
                and ahora - self.motores_t >= MOTORES_S:
            self.pedir_motores()
        if self.paso == "hola" and self.sin_sesion and AL.usable(self.motor_fila()):
            self.sin_sesion = False                         # entraste: ya despierta del todo
            self._ofrecer()
        if self.via and self.job is not None and not self.job.get("done") and not self.pidiendo_job and \
                ahora - self.job_t >= JOB_S:
            self._pedir_job()
        if self.carga and not (self.carga.get("job") or {}).get("done") and not self.carga.get("pidiendo") and \
                ahora - self.carga.get("t", -1e9) >= JOB_S:
            self._pedir_carga()

    def _pedir_job(self):
        self.pidiendo_job = True
        via, srv = self.via, self._srv()

        def hacer():
            j = AL.estado(via, srv)
            with self._lock():
                self.pidiendo_job, self.job_t = False, self.reloj()
                if j is not None:
                    self.job = j
                    if j.get("done"):
                        self._job_termino()
        if via == "aqui":
            hacer()
        else:
            self._fondo(hacer)

    def _job_termino(self):
        j = self.job or {}
        via, srv = self.via, self._srv()
        self._fondo(lambda: AL.visto(via, srv))
        if j.get("ok"):
            self.hola_t = self.reloj()
            if self.primera:
                AL.marcar_primer_arranque(self.motor or "", [self.comando])
            self._fondo(self._releer)
            if not self.visible:
                self._terminar("aviso")
                return
            self._ir("hola")
            self._ofrecer()
            return
        if j.get("cancel"):
            self.err = {"tipo": "cancelado", "titulo": _t("agregar.err.cancelado"), "texto": "",
                        "botones": [("agr:e:motor", _t("agregar.boton.entendido"), True)], "atras": "motor"}
        else:
            self.err = self._fallo(j.get("error"), atras=True)
        self.paso = "motor"
        self.visible = True
        self._foco_inicial()

    def _releer(self):
        ok = False
        try:
            ok = bool(self.app.releer_agentes())
        except Exception:
            ok = False
        if not ok:                                          # sin la página: los mismos, calculados aquí
            ag = AL.agentes_aqui()
            if ag is not None:
                with self._lock():
                    aid = self.app.id_elegido() if hasattr(self.app, "id_elegido") else ""
                    self.app.d["agentes"] = ag
                    ids = [b["id"] for b in ag]
                    self.app.sel = ids.index(aid) if aid in ids else 0

    def _ofrecer(self):
        """AG6-a: una vez, después de que existe y se puede usar."""
        self.ofertas = {}
        if self.sin_sesion:
            return
        self.ofertas["skills"] = "?"
        motor = self.motor

        def hacer():
            o = AL.oferta_afinar(motor)
            with self._lock():
                if o.get("ok") and self.paso == "hola" and "afinar" not in self.ofertas:
                    self.ofertas = dict({"afinar": "?"}, **self.ofertas)
                    self.afina = {"tokens": o.get("tokens"), "estado": ""}
                    if self.foco in ("", "agr:of:skills:no") or not self.foco.startswith("agr:of:"):
                        self.foco = "agr:of:afinar:no"
        self._fondo(hacer)
        self._foco_inicial()

    def _oferta(self, cual, que):
        if que == "no":
            self.ofertas[cual] = "no"
            self._foco_inicial()
            return None
        if cual == "afinar":
            return self._afinar()
        return self._buscar_skills()

    def _afinar(self):
        self.ofertas["afinar"] = "corriendo"
        self.afina = dict(self.afina or {}, estado="corriendo", pasos=[], res=None)
        self._ir("afina")
        comando, params = self.comando, dict(self.params)

        def progreso(key, st, note=""):
            with self._lock():
                pasos = self.afina.setdefault("pasos", [])
                fila = next((x for x in pasos if x[0] == key), None)
                if fila:
                    fila[1], fila[2] = st, note
                else:
                    pasos.append([key, st, note])

        def hacer():
            try:
                res = AL.afinar(comando, params, progress=progreso)
            except Exception as e:
                res = {"ok": False, "note": str(e)}
            with self._lock():
                self.afina["estado"], self.afina["res"] = ("listo" if res.get("ok") else "fallo"), res
                self.ofertas["afinar"] = self.afina["estado"]
                if self.paso == "afina":
                    self._ir("hola")
        self._fondo(hacer)
        return None

    def _buscar_skills(self):
        self.ofertas["skills"] = "corriendo"
        self.skills = {"estado": "buscando", "lista": [], "elegidas": set(), "res": None, "error": ""}
        self._ir("skills")
        params = dict(self.params)

        def hacer():
            try:
                r = AL.buscar_skills(params)
                lista, err = r.get("candidates") or [], ""
            except Exception as e:
                lista, err = [], str(e)
            with self._lock():
                self.skills.update(lista=lista[:8], estado="elige" if lista else "nada", error=err)
                if self.paso == "skills":
                    self._foco_inicial()
        self._fondo(hacer)
        return None

    def _marcar_skill(self, i):
        sk = self.skills or {}
        if sk.get("estado") != "elige":
            return None
        el = sk["elegidas"]
        if i in el:
            el.discard(i)
        elif len(el) < 5:
            el.add(i)
        self.foco = "agr:sk:%d" % i
        return None

    def _b_instalar_skills(self):
        sk = self.skills or {}
        elegidas = [sk["lista"][i] for i in sorted(sk.get("elegidas") or ()) if i < len(sk["lista"])]
        if not elegidas:
            return None
        sk["estado"] = "instalando"
        comando, params = self.comando, dict(self.params)

        def hacer():
            try:
                res = AL.instalar_skills(comando, params, elegidas)
            except Exception as e:
                res = {"installed": [], "held": [], "errors": [str(e)]}
            with self._lock():
                sk.update(estado="listo", res=res)
                self.ofertas["skills"] = "listo"
                if self.paso == "skills":
                    self._ir("hola")
        self._fondo(hacer)
        return None

    def aviso_listo(self):
        return _t("agregar.crea.aviso_listo", n=self.visible_nombre or self.comando)

    def _terminar(self, como):
        """La tarjeta se cierra: Inicio (o la conversación, o sus sesiones) con el agente nuevo elegido."""
        self.terminado = como
        return "cerrar"

    # ── los errores con su botón ──
    def _error_crear(self, r):
        clave = r.get("clave") or ""
        self.paso = "motor"
        if clave == "localhost.err.crear_carpeta":
            rv = AL.revisar_nombre(self.nombre)
            if rv.get("clave") == "carpeta_agente":
                self._error_carpeta(rv)
                return
            self.err = {"tipo": "carpeta", "titulo": _t("agregar.err.carpeta.titulo", n=self.visible_nombre),
                        "texto": _t("agregar.err.carpeta.texto", r=AL.ruta_corta(rv.get("carpeta") or "")),
                        "botones": [("agr:e:ver", _t("agregar.boton.otro_nombre"), True)], "atras": "ver"}
        elif clave in ("localhost.err.crear_existe", "localhost.err.crear_nombre"):
            self._rev = (None, None)
            self.paso = "ver"
            self.err = None
            self._foco_inicial()
            self._avisar(AL.texto_nombre(self.revision()) if clave.endswith("existe") else _t("agregar.nombre.invalido"))
            return
        elif clave == "localhost.err.crear_en_curso":
            self.err = {"tipo": "en_curso", "titulo": _t("agregar.err.en_curso"), "texto": "",
                        "botones": [("agr:e:motor", _t("agregar.boton.entendido"), True)], "atras": "motor"}
        elif clave == "localhost.err.formato":
            self.err = {"tipo": "formato", "titulo": _t("agregar.err.formato"), "texto": "",
                        "botones": [("agr:e:ver", _t("agregar.boton.atras"), True)], "atras": "ver"}
        else:
            self.err = self._fallo(r.get("texto") or clave)
        self._foco_inicial()

    def _fallo(self, detalle, atras=False):
        """Una creación que falló: la frase amable y, a pedido («Ver detalle»), el error de verdad."""
        bs = [("agr:e:motor", _t("agregar.boton.reintentar"), True), ("agr:e:detalle", _t("agregar.boton.detalle"),
                                                                       False)]
        if atras:
            bs.append(("agr:e:ver", _t("agregar.boton.atras"), False))
        return {"tipo": "fallo", "titulo": _t("agregar.err.fallo_titulo"), "texto": _t("agregar.err.fallo_texto"),
                "detalle": AL.ruta_corta(str(detalle or "")).strip(), "botones": bs, "atras": "motor"}

    def _error_carpeta(self, rv):
        info = rv.get("agente") or {}
        self.err = {"tipo": "carpeta_agente",
                    "titulo": _t("agregar.err.carpeta_agente.titulo", n=self.nombre.strip() or rv.get("comando")),
                    "texto": _t("agregar.err.carpeta_agente.texto", r=AL.ruta_corta(rv.get("carpeta") or "")),
                    "botones": [("agr:e:conectarlo", _t("agregar.boton.conectarlo"), True),
                                ("agr:e:ver", _t("agregar.boton.otro_nombre"), False)],
                    "carpeta": rv.get("carpeta") or info.get("folder") or "", "atras": "ver"}
        self.paso = "ver"
        self._foco_inicial()

    def _error_interrumpida(self, r):
        snap = r.get("snap") or {}
        n = snap.get("display") or (snap.get("name") or "").capitalize()
        est = r.get("estado")
        if est == "creado":
            texto, bs = _t("agregar.err.interrumpida.creado", n=n), [("agr:e:dejarlo", _t("agregar.boton.entendido"),
                                                                      True)]
        elif est == "en_uso":
            texto, bs = _t("agregar.err.interrumpida.ajeno", m=r.get("motivo") or ""), [
                ("agr:e:dejarlo", _t("agregar.boton.entendido"), True)]
        else:
            texto = _t("agregar.err.interrumpida.texto")
            bs = [("agr:e:reintentar", _t("agregar.boton.reintentar"), True),
                  ("agr:e:dejarlo", _t("agregar.boton.dejarlo"), False)]
        self.err = {"tipo": "interrumpida", "titulo": _t("agregar.err.interrumpida.titulo", n=n), "texto": texto,
                    "botones": bs, "restos": r, "atras": None}

    def _clic_error(self, rid):
        e = self.err or {}
        acc = rid[6:] if rid.startswith("agr:e:") else ""
        if acc == "detalle":                                 # S7: el error de verdad, a pedido
            if e.get("detalle"):
                e["texto"] = _t("agregar.err.detalle", e=e["detalle"])
                e["botones"] = [b for b in e["botones"] if b[0] != "agr:e:detalle"]
                self.foco = e["botones"][0][0]
            return None
        if acc in ("ver", "motor", "cargar"):
            self.err = None
            self._ir(acc)
            if acc == "ver":
                self.foco = "agr:nombre"
            return None
        if acc == "conectarlo":
            carpeta = e.get("carpeta") or ""
            self.err = None
            self.desde_cargar = False
            self.paso = "cargar"
            self.cargar["ruta"] = carpeta
            self.cargar["radio"], self.cargar["radio_de"] = AL.radiografia(carpeta), carpeta
            self.foco = "agr:ruta"
            return self._b_conectar()
        if acc in ("dejarlo", "reintentar"):
            r = e.get("restos") or {}
            snap = r.get("snap") or {}
            ok, det = AL.limpiar_restos(r) if acc == "reintentar" else AL.limpiar_restos(dict(r, estado="dejar"))
            self.err = None
            if acc == "reintentar" and ok:
                self.nombre = snap.get("display") or snap.get("name") or ""
                self.motor, self.motor_puesto = snap.get("engine") or self.motor, bool(snap.get("engine"))
                self._rev = (None, None)
                self._ir("ver")
            elif not ok:
                self._avisar(det)
            self._foco_inicial()
            return None
        return None

    # ── ya tengo un agente ──
    def _buscar(self, protegidas=False):
        self.cargar.update(estado="buscando")

        def hacer():
            r = AL.encontrados(protegidas=protegidas)
            with self._lock():
                c = self.cargar
                c.update(estado="listo", lista=r["encontrados"], avisos=r["avisos"], mac=r["mac"],
                         protegidas=r["protegidas"])
                c["i"] = 0
                if self.paso == "cargar" and (self.foco in ("agr:ruta", "") and not c["ruta"].strip()):
                    self._foco_inicial()
        self._fondo(hacer)

    def _b_protegidas(self):
        self._buscar(protegidas=True)
        return None

    def _radiografia(self):
        ruta = self.cargar["ruta"]
        if not ruta.strip():
            self.cargar["radio"], self.cargar["radio_de"] = None, None
            return

        def hacer():
            info = AL.radiografia(ruta)
            with self._lock():
                if self.cargar["ruta"] == ruta:
                    self.cargar["radio"], self.cargar["radio_de"] = info, ruta
        self._fondo(hacer)

    def _b_conectar(self):
        c = self.cargar
        sel = self._fila_cargar()
        if sel is not None:
            if sel["estado"] == "cargado":
                self._avisar(_t("agregar.carpeta.ya", n=sel["visible"]))
                return None
            if sel["estado"] == "incompleto":
                self._avisar(_t("agregar.carpeta.incompleto", n=sel["visible"]))
                return None
            nombre = sel["nombre"] if sel["estado"] == "nuevo" else (AL.libre(sel["nombre"]) or sel["nombre"])
            return self._conectar([(nombre, sel["carpeta"])], sel["visible"], sel)
        info = c.get("radio")
        if not c["ruta"].strip():
            self.foco = "agr:ruta"
            return None
        if info is None or c.get("radio_de") != c["ruta"]:
            info = AL.radiografia(c["ruta"])
            c["radio"], c["radio_de"] = info, c["ruta"]
        v = info.get("veredicto")
        if v == "no_agente" and info.get("adentro"):
            c["ruta"] = info["adentro"]
            self._radiografia()
            return None
        if v not in ("agente", "choque"):
            self._avisar(AL.texto_radiografia(info))
            return None
        nombre = info.get("name") if v == "agente" else (info.get("libre") or info.get("name"))
        vis = info.get("display") or (info.get("name") or "").capitalize()
        return self._conectar([(nombre, info["folder"])], vis, {"forma": None, "color": None})

    def _b_nuevos(self):
        nuevos = [x for x in self.cargar["lista"] if x["estado"] == "nuevo"]
        if len(nuevos) < 1:
            return None
        return self._conectar([(x["nombre"], x["carpeta"]) for x in nuevos],
                              _t("agregar.cargar.listos", n=len(nuevos)), nuevos[0])

    def _conectar(self, items, visible, fila):
        self.carga = {"items": items, "visible": visible, "via": None, "job": None, "t": -1e9, "pidiendo": True,
                      "fila": fila or {}}
        self.paso, self.err = "conectando", None
        self.foco = ""
        srv = self._srv()

        def hacer():
            r = AL.conectar(items, None, srv)
            with self._lock():
                self.carga["pidiendo"] = False
                if r.get("ok"):
                    self.carga.update(via=r.get("via"), job=r.get("job"), t=self.reloj())
                    if (r.get("job") or {}).get("done"):
                        self._carga_termino()
                else:
                    self.paso = "cargar"
                    self._foco_inicial()
                    self._avisar(_t("agregar.cargar.fallo", e=r.get("texto") or r.get("clave") or ""))
        self._fondo(hacer)
        return None

    def _pedir_carga(self):
        self.carga["pidiendo"] = True
        via, srv = self.carga["via"], self._srv()

        def hacer():
            j = AL.estado_carga(via, srv)
            with self._lock():
                self.carga["pidiendo"], self.carga["t"] = False, self.reloj()
                if j is not None:
                    self.carga["job"] = j
                    if j.get("done"):
                        self._carga_termino()
        if via == "aqui":
            hacer()
        else:
            self._fondo(hacer)

    def _carga_termino(self):
        j = self.carga.get("job") or {}
        via, srv = self.carga.get("via"), self._srv()
        self._fondo(lambda: AL.visto_carga(via, srv))
        if j.get("ok") or j.get("nombres"):
            nombres = j.get("nombres") or [n for n, _c in self.carga["items"]]
            self.comando = nombres[0] if nombres else ""
            mid = AL.motor_de(self.comando) or (self.carga.get("fila") or {}).get("motor") or ""
            if mid:
                self.motor, self.motor_puesto = mid, True
            self.pedir_motores()                             # su sesión, al día (la dice la tarjeta)
            fila = self.carga.get("fila") or {}
            if fila.get("forma") in FORMAS and fila.get("color") in COLORES:
                self.forma, self.color, self.color_puesto = FORMAS.index(fila["forma"]), COLORES.index(
                    fila["color"]), True
            if self.primera:
                AL.marcar_primer_arranque("", nombres)
            self.hola_t = self.reloj()
            self._fondo(self._releer)
            self.paso, self.foco = "conectado", "agr:fin"
        else:                                         # S7 · en simple, y lo que pasó de verdad a pedido
            self.paso = "cargar"
            self.err = {"tipo": "fallo_carga", "titulo": _t("agregar.cargar.fallo_titulo"),
                        "texto": _t("agregar.cargar.fallo_texto"),
                        "detalle": AL.ruta_corta(str(j.get("error") or "")).strip(),
                        "botones": [("agr:e:cargar", _t("agregar.boton.entendido"), True),
                                    ("agr:e:detalle", _t("agregar.boton.detalle"), False)], "atras": "cargar"}
            self._foco_inicial()

    # ── lo que se dibuja ──
    def vista(self):
        """Todo lo que pinta `pantalla` (y lo que el hub necesita: cuándo repintar)."""
        self.tick()
        ahora = self.reloj()
        a = self.monito()
        espera = None
        if self.paso in ("creando", "conectando", "afina") or (self.paso == "skills" and (self.skills or {}).get(
                "estado") in ("buscando", "instalando")):
            espera = 0.25
        if self.hola_t is not None and 0 <= ahora - self.hola_t < FIESTA_S:
            espera = 1 / 8.0
        if self.paso in ("motor", "medida") and (self.motores is None or self._verificando()):
            espera = min(espera or 1.0, 1.0)
        verbo = None
        if self.paso in ("motor", "medida", "hola"):
            b = ((self.botones_hola() if self.paso == "hola" else self.botones_motor()) or [("", "", False)])[0][0]
            verbo = {"agr:entrar": _t("agregar.k.entrar"), "agr:instalar": _t("agregar.k.instalar")}.get(b)
        return {"paso": self.paso, "foco": self.foco, "err": dict(self.err) if self.err else None, "verbo": verbo,
                "sin_sesion": self.sin_sesion,
                "a": a, "num": self.num_paso(), "total": self.total(), "primera": self.primera,
                "aviso": self.aviso if ahora - self.aviso_t < 6.0 else "", "espera": espera,
                "hola_t": self.hola_t, "t": ahora, "tarjeta": self}

    def sin_sesion_conectado(self):
        """M2 · el agente conectado: ¿a su motor le falta tu sesión (o no está instalado)? None mientras no se sabe."""
        if not self.motor or self.motores is None or len((self.carga or {}).get("items") or ()) > 1:
            return None
        m = self.motor_fila()
        if m is None or m.get("estado") == "verificando":
            return None
        return not AL.usable(m) and AL.que_le_falta(m) != "sin_confirmar"

    def monito(self):
        st = {"creando": "trabaja", "conectando": "trabaja", "afina": "trabaja", "hola": "libre",
              "conectado": "libre"}.get(self.paso, "duerme")
        if (self.paso == "hola" and self.sin_sesion) or (self.paso == "conectado" and self.sin_sesion_conectado()):
            st = "duerme"
        if self.paso == "skills" and (self.skills or {}).get("estado") in ("buscando", "instalando"):
            st = "trabaja"
        f, c = FORMAS[self.forma % len(FORMAS)], self.color_hex()
        n = " ".join(self.nombre.split()) or _t("agregar.dormido.nombre")
        if self.paso == "cargar":
            fila = self._fila_cargar()
            if fila:
                f, c, n = fila.get("forma") or f, fila.get("color") or c, fila.get("visible") or n
            elif (self.cargar.get("radio") or {}).get("veredicto") in ("agente", "choque", "ya_conectado"):
                info = self.cargar["radio"]
                n = info.get("display") or (info.get("name") or "").capitalize() or n
                f, c = _forma_de(info.get("name") or ""), COLORES[sum(map(ord, info.get("name") or "x")) % 6]
            else:
                f, c, n = "bolita", GRIS, _t("agregar.titulo.cargar")
        if self.paso in ("conectando", "conectado") and self.carga:
            n = self.carga.get("visible") or n
        return {"id": self.comando or NUEVO, "n": n, "c": c, "f": f, "st": st}


class _SinCandado:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _forma_de(nombre):
    try:
        import localhost_front as F
        return F._forma_por_omision(nombre)
    except Exception:
        return "bolita"


# ═════════════════════════════════════════════════════════════════════════════
# el dibujo
# ═════════════════════════════════════════════════════════════════════════════
def geo(w, h):
    """La tarjeta: (x, y, ancho, alto), la columna del monito (x, ancho) y la de las preguntas (x, ancho). Grande desde
    100×30; abajo, compacta (la de una terminal de fábrica, 80×24)."""
    if w < 100 or h < 30:
        cw = max(40, w - 6)
        cx, cy, ch = (w - cw) // 2, 4 if h >= 23 else 3, 17
        izq = (cx + 2, 23 if cw >= 66 else 0)
    else:
        cw, ch = 92, 23
        cx, cy = (w - cw) // 2, 5 + max(0, (h - 36) // 2)
        izq = (cx + 3, 30)
    dx = izq[0] + izq[1] + (3 if izq[1] else 1)
    der = (dx, cx + cw - dx - 3)
    return (cx, cy, cw, ch), izq, der


def _parrafo(T, x, y, texto, ancho, fg=None, b=False, bg=P1, tope=None):
    """`texto` en líneas de `ancho` desde (x, y). → la fila siguiente."""
    ln, n = "", 0
    for p in str(texto or "").split(" "):
        if ln and W(ln) + 1 + W(p) > ancho:
            T.put(x, y, corto(ln, ancho), fg or C["tx2"], b, bg)
            y, ln, n = y + 1, p, n + 1
            if tope and n >= tope:
                return y
        else:
            ln = (ln + " " + p) if ln else p
    if ln:
        T.put(x, y, corto(ln, ancho), fg or C["tx2"], b, bg)
        y += 1
    return y


def _campo(L, x, y, w, texto, rid, foco, ph="", col=None):
    """Una caja de escribir de una fila (pastilla): el foco la ilumina y enseña el cursor ▏."""
    T = L.T
    hov = L.reg(x, y, w, 1, rid)
    fondo = P3 if (foco or hov) else P2
    T.put(x, y, "▐", fondo, False, P1)
    T.fill(x + 1, y, w - 2, 1, fondo)
    if texto:
        t = texto if W(texto) <= w - 4 else "…" + texto[-(w - 5):]
        xx = T.put(x + 2, y, t, C["tx"], True, fondo)
        if foco:
            T.put(min(xx, x + w - 2), y, "▏", col or C["tx"], False, fondo)
    else:
        if foco:
            T.put(x + 2, y, "▏", col or C["tx"], False, fondo)
        T.put(x + 3 if foco else x + 2, y, corto(ph, w - 5), C["tx3"], False, fondo)
    T.put(x + w - 1, y, "▌", fondo, False, P1)


def _boton(L, x, y, lab, rid, col, principal, foco, limite):
    """Un botón de una fila (ficha): el principal del color del agente; el foco o el mouse lo iluminan. Si no cabe
    antes de `limite`, no se dibuja. → la columna siguiente."""
    T = L.T
    lab = " %s " % lab
    if x + W(lab) + 2 > limite:
        return x
    hov = L.reg(x, y, W(lab) + 2, 1, rid)
    if principal:
        fondo = P.mix(col, "#ffffff", 0.18) if (hov or foco) else col
        xx = B.ficha(T, x, y, lab, fondo, P1, LUZTX, True)
    else:
        xx = B.ficha(T, x, y, lab, P4 if (hov or foco) else P3, P1, C["tx"] if (hov or foco) else C["tx2"], foco)
    if foco:                                              # el foco se ve también con el teclado: ▸ delante
        T.put(x - 1, y, "▸", col, True, P1)
    return xx + 1


def _botones(L, x, y, dw, botones, foco, col):
    xx = x
    for rid, lab, principal in botones:
        xx = _boton(L, xx, y, lab, rid, col, principal, foco == rid, x + dw)


def _caras(L, x, y, a, sel, ancho, foco):
    """Las seis caras: chicas en fila (la elegida sobre un plano y de su color) o, sin espacio, ‹ nombre ›. → la fila
    siguiente."""
    T = L.T
    paso = 9 if ancho >= 56 else 8
    if ancho >= 50:
        L.reg(x - 1, y - 1, paso * 6, 5, "agr:cara")      # la fila entera (cada cara, encima, gana)
        for i, f in enumerate(FORMAS):
            xx = x + i * paso
            rid = "agr:cara:%d" % i
            hov = L.reg(xx - 1, y - 1, 8, 5, rid)
            if i == sel or hov:
                T.fill(xx - 1, y - 1, 8, 5, P3 if i == sel else P2)
            MON.dibujar(T, {"id": "cara%d" % i, "c": a["c"] if i == sel else "#6f6f78", "f": f}, xx, y, 6,
                        st="libre", signo=False)
        if foco:
            T.put(x + sel * paso - 2, y + 1, "▸", a["c"] if a["c"] != GRIS else C["tx"], True, P1)
        return y + 4
    T.put(x, y, _t("agregar.ver.cara"), C["tx3"], False, P1)
    L.reg(x + 8, y, 3, 1, "agr:cara:%d" % ((sel - 1) % len(FORMAS)))
    xx = B.ficha(T, x + 8, y, " ‹ ", P4 if foco else P3, P1, C["tx"], True)
    L.reg(xx, y, 11, 1, "agr:cara")
    xx = T.put(xx + 1, y, corto(_nombre_forma(FORMAS[sel]), 10).ljust(10), C["tx"], True, P1)
    L.reg(xx, y, 3, 1, "agr:cara:%d" % ((sel + 1) % len(FORMAS)))
    B.ficha(T, xx, y, " › ", P4 if foco else P3, P1, C["tx"], True)
    if foco:
        T.put(x + 6, y, "▸", a["c"] if a["c"] != GRIS else C["tx"], True, P1)
    return y + 2


def _nombre_forma(f):
    return _t("addagent.ui.forma.%s" % f) if not _t("addagent.ui.forma.%s" % f).startswith("addagent.") else \
        f.capitalize()


def _colores(L, x, y, sel, puesto, ancho, foco):
    T = L.T
    x0 = x
    if ancho < 50:
        T.put(x, y, _t("agregar.ver.color"), C["tx3"], False, P1)
        x += 8
    L.reg(x, y, 6 * len(COLORES), 1, "agr:color")           # la fila entera (cada color, encima, gana)
    for i, c in enumerate(COLORES):
        rid = "agr:color:%d" % i
        hov = L.reg(x + i * 6, y, 5, 1, rid)
        on = puesto and i == sel
        B.ficha(T, x + i * 6, y, " ✓ " if on else ("·" * 3 if hov else "   "), c, P1, LUZTX, True)
    if foco:
        T.put(x0 - 2 if ancho >= 50 else x0 + 6, y, "▸", COLORES[sel], True, P1)
    return y + 2


def _selector(L, x, y, w, nombre, est, col, a, foco):
    """El motor en una caja con ▲▼ (como en Inicio H1-a)."""
    T = L.T
    hov = L.reg(x, y, w - 8, 3, "agr:motor")
    ha = L.reg(x + w - 8, y, 4, 3, "agr:mot:arriba")
    hb = L.reg(x + w - 4, y, 4, 3, "agr:mot:abajo")
    H.area(L, x, y, w, 3, P3, linea=a["c"] if (foco or hov) else H.LN)
    T.put(x + 3, y + 1, "◈", a["c"], True, P3)
    T.put(x + 5, y + 1, corto(nombre, w - 24), LUZ, True, P3)
    T.right(x + w - 8, y + 1, est, col, True)
    T.put(x + w - 6, y + 1, "▲", C["tx"] if ha else C["tx3"], ha, P3)
    T.put(x + w - 4, y + 1, "▼", C["tx"] if hb else C["tx3"], hb, P3)


def _puntitos(T, x, y, n, k, col):
    for i in range(n):
        T.put(x + 2 * i, y, "■" if i == k else "▪", col if i <= k else "#4a4a52", True, P1)


def _error(T, x, y, dw, texto, col=WARN):
    T.put(x, y, "!", col, True, P1)
    return _parrafo(T, x + 2, y, texto, dw - 2, C["tx"])


def _cabecera(L, s, w, a):
    T = L.T
    H.area(L, 1, 0, w - 2, 3, P1)
    xx = T.put(3, 1, "❯", a["c"] if a["c"] != GRIS else C["tx2"], True, P1)
    xx = T.put(xx + 1, 1, "workspace", C["tx"], True, P1)
    T.put(xx + 2, 1, corto(_t("agregar.titulo.nuevo") if not s.get("cargar") else _t("agregar.titulo.cargar"),
                           max(1, w - xx - 14)), C["tx3"], False, P1)
    lab = " ✕ "
    hov = L.reg(w - 3 - W(lab) - 2, 0, W(lab) + 2, 3, "agr:cerrar_tarjeta")
    B.ficha(T, w - 3 - W(lab) - 2, 1, lab, P3 if hov else P2, P1, C["tx"] if hov else C["tx2"])


def teclas(v):
    """Las teclas de abajo para el paso de ahora."""
    p = v["paso"]
    if v.get("err"):
        return [("Enter", _t("agregar.k.boton")), ("Tab", _t("agregar.k.elige")), ("Esc", _t("agregar.k.vuelve"))]
    return {"tu": [("Enter", _t("agregar.k.sigue")), ("Tab", _t("agregar.k.boton")), ("Esc", _t("agregar.k.vuelve"))],
            "ver": [("Tab", _t("agregar.k.campo")), ("←→", _t("agregar.k.cara")), ("Enter", _t("agregar.k.sigue")),
                    ("Esc", _t("agregar.k.vuelve"))],
            "motor": [("↑↓", _t("agregar.k.motor")), ("Enter", v.get("verbo") or _t("agregar.k.despertar")),
                      ("Tab", _t("agregar.k.boton")), ("Esc", _t("agregar.k.atras"))],
            "medida": [("Tab", _t("agregar.k.campo")), ("Espacio", _t("agregar.k.sino")),
                       ("Enter", _t("agregar.k.despertar")), ("Esc", _t("agregar.k.cerrar"))],
            "creando": [("Esc", _t("agregar.k.fondo")), ("Enter", _t("agregar.k.cancelar"))],
            "hola": ([("Enter", v.get("verbo") or _t("agregar.k.entrar")), ("Esc", _t("agregar.k.inicio"))]
                     if v.get("sin_sesion") else
                     [("←→", _t("agregar.k.elige")), ("Enter", _t("agregar.k.boton") if str(v.get("foco") or "")
                                                       .startswith("agr:of:") else _t("agregar.k.conversar")),
                      ("s", _t("agregar.k.sesiones")), ("Esc", _t("agregar.k.inicio"))]),
            "afina": [("Esc", _t("agregar.k.fondo"))],
            "skills": [("Espacio", _t("agregar.k.marca")), ("Enter", _t("agregar.k.instala")),
                       ("Esc", _t("agregar.k.atras"))],
            "cargar": [("↑↓", _t("agregar.k.elige")), ("Enter", _t("agregar.k.conectar")), ("a", _t("agregar.k.nuevos")),
                       ("⌘V", _t("agregar.k.pega")), ("Esc", _t("agregar.k.vuelve"))],
            "conectando": [],
            "conectado": [("Enter", _t("agregar.k.inicio"))]}.get(p, [])


def _abajo(L, s, v, a, w, h):
    T = L.T
    y = h - 1
    T.put(0, y, " " * w, None, False, P1)
    x = T.put(1, y, "❯", a["c"] if a["c"] != GRIS else C["tx2"], True, P1)
    x = T.put(x + 1, y, "workspace", C["tx"], True, P1) + 3
    ks = teclas(v)
    if os.name == "nt":
        ks = [("Ctrl+V", lab) if k == "⌘V" else (k, lab) for k, lab in ks]
    if w < 120:
        ks = [("↵", lab) if k == "Enter" else (k, lab) for k, lab in ks]
    for k, lab in ks:
        if x + W(k) + 3 + W(lab) + 2 > w - 2:
            break
        x = T.key(x, y, k, lab)


def _tarjeta(L, s, v, w, h, titulo, estado, col_estado=None, paso=None):
    """La tarjeta grande con el monito a la izquierda. → (x, y, ancho, y_botones) de la columna de las preguntas."""
    T = L.T
    a = v["a"]
    (cx, cy, cw, ch), (ix, iw), (dx, dw) = geo(w, h)
    linea = a["c"] if a["c"] != GRIS else H.LN
    der = [(_t("agregar.paso_n", n=paso, t=v["total"]), C["tx2"], False)] if paso else None
    H.area(L, cx, cy, cw, ch, P1, titulo=[(corto(titulo, cw - 20), C["tx"], True)], der=der, linea=linea)
    if iw:
        mw, mh = MON.medidas(16)
        mx = ix + (iw - mw) // 2 + 1
        my = cy + 3 if ch < 20 else cy + 5
        L.reg(mx, my, mw, mh, "agr:monito")
        sa = {"t": v["t"], "anim": {a["id"]: {"fiesta": v["hola_t"]}} if v.get("hola_t") is not None else {},
              "agentes": [a]}
        MON.dibujar(T, a, mx, my, 16, s=sa, st=a.get("st"))
        yn = my + mh + 1
        T.center(ix, iw, yn, corto(a["n"], iw - 2), a["c"] if a["c"] != GRIS else C["tx2"], True)
        T.center(ix, iw, yn + 1, corto(estado, iw - 2), col_estado or C["tx3"])
    if paso:
        _puntitos(T, cx + cw // 2 - (v["total"] - 1), cy + ch - 1, v["total"], paso - 1,
                  a["c"] if a["c"] != GRIS else C["tx2"])
    return dx, cy + (2 if ch < 20 else 3), dw, cy + ch - (3 if ch < 20 else 4)


def pantalla(w, h, s):
    """La tarjeta abierta sobre Inicio, en w×h. `s`: la instantánea del hub con `agregar` (Tarjeta.vista()).
    → Term con sus zonas."""
    T = P.Term(w, h)
    T.fill(0, 0, w, h, BG)
    T.scroll_max, T.riel, T.lado, T.focos = 0, None, True, []
    T.geo = {"nivel": "agregar", "panel": None, "franja": None, "cajon": None}
    fondo = ((s.get("datos") or {}).get("preferencias") or {}).get("fondo")
    if w < 60 or h < 20:
        T.center(0, w, h // 2, "Agranda la ventana", C["tx2"])
        return P.afinar(T, fondo)
    v = s["agregar"]
    a = v["a"]
    L = B.Lienzo(T, dict(s, foco=v["foco"]))
    _cabecera(L, dict(s, cargar=v["paso"] in ("cargar", "conectando", "conectado")), w, a)
    try:
        _cuerpo(L, s, v, w, h)
    except Exception:
        if os.environ.get("WORKSPACE_AGREGAR_ESTRICTO"):
            raise
        T.center(0, w, h // 2, "Algo falló al dibujar la tarjeta: Esc vuelve a Inicio.", WARN)
    T.flat()
    _abajo(L, s, v, a, w, h)
    if v.get("aviso"):
        x = 13
        T.put(x, h - 1, " " * max(0, w - x - 1), None, False, P1)
        T.put(x, h - 1, corto(v["aviso"], w - x - 2), C["tx"], False, P1)
    return P.afinar(T, fondo)


def _cuerpo(L, s, v, w, h):
    T = L.T
    tj = v["tarjeta"]
    a = v["a"]
    col = a["c"] if a["c"] != GRIS else P.mix(C["tx2"], "#000000", 0.2)
    p, foco, err = v["paso"], v["foco"], v.get("err")
    if p == "tu":
        x, y, dw, yb = _tarjeta(L, s, v, w, h, _t("agregar.titulo.primero"), _t("agregar.estado.sin_motor"),
                                paso=v["num"])
        if err:
            return _cuerpo_error(L, x, y, dw, yb, err, foco, col)
        T.put(x, y, corto(_t("agregar.tu.titulo"), dw), C["tx"], True, P1)
        yy = _parrafo(T, x, y + 2, _t("agregar.tu.texto"), dw, C["tx2"])
        _campo(L, x, yy + 1, min(30, dw), tj.tu, "agr:tu", foco == "agr:tu", _t("agregar.tu.ph"), col)
        if tj.tu and tj.tu == AL.nombre_de_la_cuenta():
            T.put(x, yy + 2, corto(_t("agregar.tu.de_cuenta"), dw), C["tx3"], False, P1)
        _botones(L, x, yb, dw, [("agr:siguiente", _t("agregar.tu.boton", n=corto(tj.tu.strip() or "…", 14)), True),
                                ("agr:cargar", _t("agregar.boton.ya_tengo"), False)], foco, col)
        return
    if p == "ver":
        x, y, dw, yb = _tarjeta(L, s, v, w, h, _t("agregar.titulo.primero") if v["primera"] else
                                _t("agregar.titulo.nuevo"), _t("agregar.estado.sin_motor"), paso=v["num"])
        if err:
            return _cuerpo_error(L, x, y, dw, yb, err, foco, col)
        T.put(x, y, _t("agregar.ver.titulo"), C["tx"], True, P1)
        yy = y + 2
        if dw >= 50:
            yy = _caras(L, x + 1, yy + 1, dict(a, c=a["c"] if a["c"] != GRIS else COLORES[tj.color]), tj.forma, dw,
                        foco == "agr:cara") + 1
        else:
            yy = _caras(L, x, yy, dict(a, c=a["c"] if a["c"] != GRIS else COLORES[tj.color]), tj.forma, dw,
                        foco == "agr:cara")
        yy = _colores(L, x, yy, tj.color, tj.color_puesto or bool(tj.nombre.strip()), dw, foco == "agr:color")
        T.put(x, yy, _t("agregar.ver.nombre"), C["tx3"], False, P1)
        fw = min(28, dw - 10)
        _campo(L, x + 10, yy, fw, tj.nombre, "agr:nombre", foco == "agr:nombre", _t("agregar.ver.nombre_ph"), col)
        yy += 1
        r = tj.revision()
        if tj.nombre.strip():
            if r.get("estado") == "ok":
                xx = T.put(x + 10, yy, corto(_t("agregar.nombre.ok", n="").rstrip(), dw - 10), C["tx3"], False, P1)
                T.put(xx + 1, yy, corto(r["comando"], max(1, x + dw - xx - 1)), C["tx2"], True, P1)
            else:
                t = AL.texto_nombre(r)
                if r.get("clave") in ("repetido", "programa") and r.get("libre"):
                    lab = _t("agregar.boton.usar", n=r["libre"])
                    lw = W(lab) + 4
                    if W(t) > dw - 14 - lw:
                        t = _t("agregar.nombre.%s_corto" % r["clave"], n=r["comando"])
                    T.put(x + 10, yy, "!", WARN, True, P1)
                    T.put(x + 12, yy, corto(t, max(1, dw - 14 - lw)), C["tx"], False, P1)
                    _boton(L, x + dw - lw, yy, lab, "agr:usar", col, False, foco == "agr:usar", x + dw + 1)
                else:
                    T.put(x + 10, yy, "!", WARN, True, P1)
                    T.put(x + 12, yy, corto(t, dw - 12), C["tx"], False, P1)
        yy += 1
        T.put(x, yy, _t("agregar.ver.para"), C["tx3"], False, P1)
        _campo(L, x + 10, yy, min(38, dw - 10), tj.para, "agr:para", foco == "agr:para", _t("agregar.ver.para_ph"),
               col)
        _botones(L, x, yb, dw, [("agr:siguiente", _t("agregar.boton.siguiente"), True),
                                ("agr:cargar", _t("agregar.boton.ya_tengo"), False)], foco, col)
        return
    if p in ("motor", "medida"):
        m = tj.motor_fila()
        clave, est_txt, est_col = tj.estado_motor(m) if tj.motores is not None else ("viendo",
                                                                                     _t("agregar.motor.viendo"),
                                                                                     C["tx3"])
        x, y, dw, yb = _tarjeta(L, s, v, w, h, " ".join(tj.nombre.split()) or _t("agregar.titulo.nuevo"),
                                _t("agregar.estado.sin_motor"), paso=v["num"])
        if err:
            return _cuerpo_error(L, x, y, dw, yb, err, foco, col)
        if p == "medida":
            return _cuerpo_medida(L, x, y, dw, yb, tj, foco, col)
        T.put(x, y, _t("agregar.motor.titulo"), C["tx"], True, P1)
        sw = min(46, dw)
        nombre = AL.nombre_motor(tj.motor)
        if tj.motores is None:
            T.put(x, y + 2, corto(_t("agregar.motor.viendo_nota"), dw), C["tx2"], False, P1)
            yy = y + 4
        elif not tj.motores:
            T.put(x, y + 2, corto(_t("agregar.motor.ninguno"), dw), C["tx2"], False, P1)
            yy = _parrafo(T, x, y + 4, _t("agregar.motor.nota_ninguno"), dw, C["tx3"])
        else:
            _selector(L, x, y + 2, sw, nombre, est_txt, est_col, dict(a, c=col), foco == "agr:motor")
            if clave == "listo":
                otros = sum(1 for z in tj.motores if AL.usable(z) and z.get("id") != tj.motor)
                nota = _t("agregar.motor.nota_listo", n=otros) if otros else _t("agregar.motor.nota_listo_solo")
            elif clave == "entrar":
                nota = _t("agregar.motor.nota_entrar")
            elif clave == "instalar":
                nota = _t("agregar.motor.nota_no_instalado", m=nombre)
            elif clave in ("revisar", "confirmar"):
                nota = _t("agregar.motor.nota.%s" % AL.que_le_falta(m), m=nombre)
            else:
                nota = _t("agregar.motor.viendo_nota")
            yy = _parrafo(T, x, y + 6, nota, dw, C["tx3"], tope=3 if yb - (y + 6) < 6 else None)
        if yy + 1 < yb:
            hm = L.reg(x, yy + 1, min(dw, 30), 1, "agr:medida")
            T.put(x, yy + 1, "▸ ", col, True, P1)
            T.put(x + 2, yy + 1, corto(_t("agregar.medida.pliegue"), dw - 2),
                  C["tx"] if (hm or foco == "agr:medida") else C["tx2"], foco == "agr:medida", P1)
            if dw >= 66:
                T.put(x + 26, yy + 1, corto(_t("agregar.medida.pliegue_nota"), dw - 26), C["tx3"], False, P1)
        _botones(L, x, yb, dw, tj.botones_motor(), foco, col)
        return
    if p == "creando":
        x, y, dw, yb = _tarjeta(L, s, v, w, h, a["n"], _t("agregar.estado.despertando"), a["c"])
        T.put(x, y, corto(_t("agregar.crea.titulo", n=a["n"]), dw), C["tx"], True, P1)
        pasos = AL.pasos_humanos(tj.job or {}, tj.motor)
        hechos = 0
        for i, (t, st) in enumerate(pasos):
            g, c_ = {"ok": ("✓", OK), "run": ("◐", col), "fail": ("✗", ROJO)}.get(st, ("·", C["tx3"]))
            if st == "run" and int(v["t"] * 4) % 2:
                g = "◓"
            hechos += st == "ok"
            T.put(x, y + 2 + i, g, c_, True, P1)
            T.put(x + 2, y + 2 + i, corto(t, dw - 2), C["tx"] if st in ("ok", "run") else C["tx3"], st == "run", P1)
        bw = min(30, dw)
        k = int(bw * (hechos + (0.5 if any(st == "run" for _t_, st in pasos) else 0)) / 4)
        for i in range(bw):
            T.put(x + i, y + 7, "▰" if i < k else "▱", col if i < k else "#3a3a42", False, P1)
        if yb - (y + 9) >= 1:
            _parrafo(T, x, y + 9, _t("agregar.crea.nota"), dw, C["tx3"], tope=2)
        _botones(L, x, yb, dw, [("agr:cancelar", _t("agregar.boton.cancelar"), False)], foco, col)
        return
    if p == "hola":
        sin = tj.sin_sesion
        x, y, dw, yb = _tarjeta(L, s, v, w, h, a["n"], _t("agregar.estado.falta_entrar", m=AL.nombre_motor(tj.motor))
                                if sin else _t("agregar.estado.despierta"), WARN if sin else OK)
        T.put(x, y, corto(_t("agregar.hola.titulo", n=a["n"]), dw), C["tx"], True, P1)
        txt = _t("agregar.hola.sin_sesion", c=tj.comando, m=AL.nombre_motor(tj.motor)) if sin else \
            _t("agregar.hola.texto", m=AL.nombre_motor(tj.motor), c=tj.comando)
        yy = _parrafo(T, x, y + 2, txt, dw, C["tx2"], tope=max(2, min(5, yb - (y + 2) - 2)))
        afina = tj.afina or {}
        if (afina.get("estado") in ("listo", "fallo")) and yy < yb - 1:
            res = afina.get("res") or {}
            t = _t("agregar.afina.listo", m=AL.nombre_motor(tj.motor)) if afina["estado"] == "listo" else \
                _t("agregar.afina.fallo", e=str(res.get("note") or "")[:80])
            T.put(x, yy, corto(t, dw), OK if afina["estado"] == "listo" else WARN, False, P1)
            yy += 1
        sk = tj.skills or {}
        if sk.get("estado") == "listo" and yy < yb - 1:
            res = sk.get("res") or {}
            T.put(x, yy, corto(_t("agregar.skills.listo", n=len(res.get("installed") or []),
                                  h=len(res.get("held") or [])), dw), OK, False, P1)
            yy += 1
        pend = [k for k in ("afinar", "skills") if tj.ofertas.get(k) == "?"]
        if pend and yy + 2 < yb:
            yy += 1
            lab = _t("agregar.hola.una_vez") + " "
            T.put(x, yy, corto(lab + "─" * max(0, dw - W(lab)), dw), C["tx3"], False, P1)
            for k in pend:
                if yy + 2 > yb - 1:
                    break
                yy += 1
                gl, t, d = (("✦", _t("agregar.hola.afinar"),
                             _t("agregar.hola.afinar_nota", m=AL.nombre_motor(tj.motor),
                                k=_ktok(afina.get("tokens")))) if k == "afinar" else
                            ("⌕", _t("agregar.hola.skills"), _t("agregar.hola.skills_nota")))
                T.put(x, yy, gl, col, True, P1)
                lsi, lno = _t("agregar.boton.si"), _t("agregar.boton.no_gracias")
                anchob = W(lsi) + W(lno) + 9
                T.put(x + 2, yy, corto(t, dw - anchob - 3), C["tx"], False, P1)
                xr = x + dw - anchob
                xr = _boton(L, xr, yy, lsi, "agr:of:%s:si" % k, col, False, foco == "agr:of:%s:si" % k, x + dw + 1)
                _boton(L, xr, yy, lno, "agr:of:%s:no" % k, col, False, foco == "agr:of:%s:no" % k, x + dw + 1)
                if yy + 1 < yb - 1 and h >= 30:
                    yy += 1
                    T.put(x + 2, yy, corto(d, dw - 3), C["tx3"], False, P1)
        _botones(L, x, yb, dw, tj.botones_hola(), foco, col)
        return
    if p == "afina":
        x, y, dw, yb = _tarjeta(L, s, v, w, h, a["n"], _t("agregar.estado.despertando"), a["c"])
        T.put(x, y, corto(_t("agregar.afina.titulo", m=AL.nombre_motor(tj.motor)), dw), C["tx"], True, P1)
        for i, (key, st, note) in enumerate((tj.afina or {}).get("pasos") or []):
            g, c_ = {"ok": ("✓", OK), "run": ("◐", col), "fail": ("✗", ROJO), "warn": ("!", WARN)}.get(st, ("·",
                                                                                                         C["tx3"]))
            T.put(x, y + 2 + i, g, c_, True, P1)
            T.put(x + 2, y + 2 + i, corto(_t("addagent.pers.step.%s" % key) if not _t(
                "addagent.pers.step.%s" % key).startswith("addagent.") else key, dw - 2), C["tx"], False, P1)
        _parrafo(T, x, yb - 2, _t("agregar.crea.nota"), dw, C["tx3"], tope=1)
        return
    if p == "skills":
        sk = tj.skills or {}
        x, y, dw, yb = _tarjeta(L, s, v, w, h, a["n"], _t("agregar.estado.despierta"), OK)
        T.put(x, y, corto(_t("agregar.skills.titulo", n=a["n"]), dw), C["tx"], True, P1)
        est = sk.get("estado")
        if est == "buscando":
            T.put(x, y + 2, corto(_t("agregar.skills.buscando"), dw), C["tx2"], False, P1)
        elif est == "nada":
            _parrafo(T, x, y + 2, _t("agregar.skills.ninguna") if not sk.get("error") else
                     _t("agregar.skills.fallo", e=sk["error"]), dw, C["tx2"])
        elif est == "instalando":
            T.put(x, y + 2, corto(_t("agregar.skills.instalando"), dw), C["tx2"], False, P1)
        else:
            T.put(x, y + 2, corto(_t("agregar.skills.elige", n=5), dw), C["tx3"], False, P1)
            cabe = max(1, yb - (y + 4) - 1)
            for i, c in enumerate((sk.get("lista") or [])[:cabe]):
                rid = "agr:sk:%d" % i
                yy = y + 4 + i
                hov = L.reg(x - 1, yy, dw, 1, rid)
                on = i in (sk.get("elegidas") or ())
                fondo = P3 if (hov or foco == rid) else P1
                if fondo != P1:
                    T.fill(x - 1, yy, dw + 1, 1, fondo)
                T.put(x, yy, "●" if on else "○", col if on else C["tx3"], True, fondo)
                T.put(x + 2, yy, corto(str(c.get("name") or "?"), 22), C["tx"], on, fondo)
                T.put(x + 25, yy, corto(str(c.get("description") or c.get("reason") or ""), max(1, dw - 26)),
                      C["tx3"], False, fondo)
        bs = ([("agr:instalar_skills", _t("agregar.boton.instalar_skills"), True)] if est == "elige" else []) + \
            [("agr:atras", _t("agregar.boton.atras"), False)]
        _botones(L, x, yb, dw, bs, foco, col)
        return
    if p in ("cargar", "conectando", "conectado"):
        return _cuerpo_cargar(L, s, v, w, h, tj, foco, col)


def D_limpio(t):
    return " ".join(str(t or "").split())


def _ktok(n):
    if not n:
        return "?"
    return ("%.1fk" % (n / 1000.0)) if n >= 1000 else str(n)


def _cuerpo_error(L, x, y, dw, yb, err, foco, col):
    T = L.T
    yy = _parrafo(T, x, y, err.get("titulo") or "", dw, C["tx"], True)
    if err.get("texto"):
        _parrafo(T, x, yy + 1, err["texto"], dw, C["tx2"], tope=max(1, yb - yy - 2))
    _botones(L, x, yb, dw, err["botones"], foco, col)


def _cuerpo_medida(L, x, y, dw, yb, tj, foco, col):
    T = L.T
    T.put(x, y, _t("agregar.medida.titulo"), C["tx"], True, P1)
    T.right(x + dw - 1, y, _t("agregar.medida.opcional"), C["tx3"])
    compacto = yb - y < 14
    yy = y + 2
    lw = 15
    for campo, lab, ph in (("como", "agregar.medida.como", "agregar.medida.como_ph"),
                           ("quesi", "agregar.medida.quesi", "agregar.medida.quesi_ph"),
                           ("sobre", "agregar.medida.sobre", "agregar.medida.sobre_ph")):
        T.put(x, yy, corto(_t(lab), lw - 1), C["tx3"], False, P1)
        _campo(L, x + lw, yy, max(10, min(40, dw - lw)), getattr(tj, campo), "agr:" + campo, foco == "agr:" + campo,
               _t(ph), col)
        yy += 1 if compacto else 2
    if compacto:
        yy += 0
    for i, lab in enumerate((_t("agregar.medida.sw_carpeta"), _t("agregar.medida.sw_skills"))):
        rid = "agr:sw:%d" % i
        on = tj.sw[i]
        hov = L.reg(x, yy, dw, 1, rid)
        f = foco == rid
        T.put(x, yy, "●" if on else "○", col if on else C["tx3"], True, P1)
        T.put(x + 2, yy, corto(lab, dw - 8), C["tx"] if (on or hov or f) else C["tx2"], f, P1)
        T.right(x + dw - 1, yy, _t("agregar.medida.si") if on else _t("agregar.medida.no"),
                col if on else C["tx3"], True)
        if f:
            T.put(x - 2, yy, "▸", col, True, P1)
        yy += 1
    if yy + 1 < yb:
        _parrafo(T, x, yy + 1, _t("agregar.medida.nota"), dw, C["tx3"], tope=max(1, yb - yy - 2))
    _botones(L, x, yb, dw, tj.botones_motor()[:1] + [("agr:cerrar", _t("agregar.boton.cerrar"), False)], foco, col)


def _cuerpo_cargar(L, s, v, w, h, tj, foco, col):
    T = L.T
    a = v["a"]
    c = tj.cargar
    p = v["paso"]
    if p == "conectando":
        x, y, dw, yb = _tarjeta(L, s, v, w, h, _t("agregar.titulo.cargar"), _t("agregar.estado.conectando"), a["c"])
        carga = tj.carga or {}
        T.put(x, y, corto(_t("agregar.cargar.conectando", n=carga.get("visible") or ""), dw), C["tx"], True, P1)
        j = carga.get("job") or {}
        if len(carga.get("items") or ()) > 1:          # varios: uno por cerebro (su nombre y su carpeta)
            filas = [(st.get("label") or "", st.get("st")) for st in j.get("pasos") or []]
        else:                                         # uno: las 4 frases de crear (no las de agent_admin)
            filas = AL.pasos_humanos(j, (carga.get("fila") or {}).get("motor") or "", cargar=True)
        for i, (t, st) in enumerate(filas[:max(1, yb - y - 3)]):
            g, c_ = {"ok": ("✓", OK), "run": ("◐", col), "fail": ("✗", ROJO), "warn": ("!", WARN)}.get(st, ("·", C["tx3"]))
            T.put(x, y + 2 + i, g, c_, True, P1)
            T.put(x + 2, y + 2 + i, corto(t, dw - 2), C["tx"] if st in ("ok", "run") else C["tx3"], st == "run", P1)
        return
    if p == "conectado":
        sin = tj.sin_sesion_conectado()
        carga = tj.carga or {}
        j = carga.get("job") or {}
        nombres = j.get("nombres") or []
        estado = (_t("agregar.estado.falta_entrar"), WARN) if sin else (
            (_t("agregar.estado.despierta"), OK) if sin is False else (_t("agregar.estado.conectado"), C["tx3"]))
        x, y, dw, yb = _tarjeta(L, s, v, w, h, a["n"], estado[0], estado[1])
        T.put(x, y, corto(_t("agregar.cargar.listo", n=a["n"]) if len(nombres) <= 1 else
                          _t("agregar.cargar.listos", n=len(nombres)), dw), C["tx"], True, P1)
        yy = y + 2
        if sin:                                       # M2 · lo mismo que dice crear: qué le falta y su botón
            yy = _parrafo(T, x, yy, _t("agregar.hola.sin_sesion", c=tj.comando, m=AL.nombre_motor(tj.motor)), dw,
                          C["tx2"], tope=max(2, yb - yy - 3)) + 1
        for av in (j.get("avisos") or [])[:2]:
            if yy < yb - 1:
                yy = _parrafo(T, x, yy, _t("agregar.cargar.avisos", a=av), dw, WARN, tope=2)
        _botones(L, x, yb, dw, tj.botones_conectado(), foco, col)
        return
    if v.get("err"):                                 # algo falló al conectar: en simple, con su botón
        x, y, dw, yb = _tarjeta(L, s, v, w, h, _t("agregar.titulo.cargar"), _t("agregar.estado.esperando"))
        return _cuerpo_error(L, x, y, dw, yb, v["err"], foco, col)
    radio = c.get("radio") if c.get("radio_de") == c["ruta"] else None
    fila = tj._fila_cargar()
    if fila:
        est = {"nuevo": _t("agregar.estado.listo_conectar"), "cargado": _t("agregar.cargar.est.cargado"),
               "otro": _t("agregar.cargar.est.otro"), "incompleto": _t("agregar.cargar.est.incompleto")}.get(
            fila["estado"], "")
    elif radio and radio.get("veredicto") in ("agente", "choque"):
        est = _t("agregar.estado.listo_conectar")
    else:
        est = _t("agregar.estado.esperando")
    x, y, dw, yb = _tarjeta(L, s, v, w, h, _t("agregar.titulo.cargar"), est)
    lista = c["lista"]
    if c["estado"] == "buscando":
        T.put(x, y, corto(_t("agregar.cargar.buscando"), dw), C["tx2"], True, P1)
        yy = y + 2
    elif not lista:
        T.put(x, y, corto(_t("agregar.cargar.ninguno"), dw), C["tx"], True, P1)
        yy = y + 2
    else:
        T.put(x, y, corto(_t("agregar.cargar.encontre", n=len(lista)) if len(lista) != 1 else
                          _t("agregar.cargar.encontre_1"), dw), C["tx"], True, P1)
        alto = yb - y - 6 - (1 if c["mac"] and not c["protegidas"] else 0)
        paso_f = 2 if alto >= 2 * len(lista) else 1
        cabe = max(1, alto // paso_f)
        i_sel = c.get("i") or 0
        i0 = max(0, min(i_sel - cabe + 1, len(lista) - cabe)) if i_sel >= cabe else 0
        yy = y + 2
        for i in range(i0, min(len(lista), i0 + cabe)):
            e = lista[i]
            rid = "agr:enc:%d" % i
            sel = foco == rid
            hov = L.reg(x - 1, yy, dw + 1, 1, rid)
            fondo = P3 if (sel or hov) else P1
            if fondo != P1:
                T.fill(x - 1, yy, dw + 1, 1, fondo)
            if sel:
                H.marca_sel(T, x - 1, yy, 1, {"c": e["color"]}, fondo)
            T.put(x + 1, yy, "●", e["color"], True, fondo)
            T.put(x + 3, yy, corto(e["visible"], 10).ljust(10), C["tx"], sel, fondo)
            ecol = {"nuevo": OK, "otro": WARN, "incompleto": WARN}.get(e["estado"], C["tx3"])
            et = _t("agregar.cargar.est.%s" % e["estado"])
            T.put(x + 14, yy, corto(e["corta"], max(4, dw - 16 - W(et))), C["tx3"], False, fondo)
            T.right(x + dw - 1, yy, et, ecol, True)
            yy += paso_f
        if i0 + cabe < len(lista):
            T.put(x + 1, yy - (1 if paso_f == 2 else 0), _t("agregar.cargar.mas", n=len(lista) - i0 - cabe),
                  C["tx3"], False, P1)
            yy += 1 if paso_f == 1 else 0
    if c["mac"] and not c["protegidas"] and c["estado"] == "listo" and yy < yb - 4:
        lab = _t("agregar.cargar.protegidas")
        hp = L.reg(x, yy, min(dw, W(lab) + 4), 1, "agr:protegidas")
        f = foco == "agr:protegidas"
        T.put(x, yy, "⌕", col, True, P1)
        T.put(x + 2, yy, corto(lab, dw - 2), C["tx"] if (hp or f) else C["tx2"], f, P1)
        if f:
            T.put(x - 2, yy, "▸", col, True, P1)
        yy += 1
    elif c["protegidas"] and yy < yb - 4:
        T.put(x, yy, corto(_t("agregar.cargar.protegidas_ya"), dw), C["tx3"], False, P1)
        yy += 1
    yy = max(yy, y + 2)
    if yy < yb - 2:
        T.put(x, yy, corto(_t("agregar.cargar.pega"), dw), C["tx3"], False, P1)
        yy += 1
    _campo(L, x, yy, min(56, dw), c["ruta"], "agr:ruta", foco == "agr:ruta", _t("agregar.cargar.ph"), col)
    yy += 1
    if radio and yy < yb:
        vd = radio.get("veredicto")
        t = AL.texto_radiografia(radio)
        if vd in ("agente", "choque"):
            T.put(x, yy, "✓", OK, True, P1)
            _parrafo(T, x + 2, yy, t, dw - 2, C["tx"], tope=max(1, yb - yy - 1))
        elif t:
            T.put(x, yy, "!", WARN if vd in ("incompleto", "ya_conectado", "no_agente") else ROJO, True, P1)
            _parrafo(T, x + 2, yy, t, dw - 2, C["tx"], tope=max(1, yb - yy - 1))
    _botones(L, x, yb, dw, tj.botones_cargar(), foco, col)


# ═════════════════════════════════════════════════════════════════════════════
# desde fuera del hub
# ═════════════════════════════════════════════════════════════════════════════
def correr(modo="crear", **kw):
    """Abre el hub en Inicio con la tarjeta abierta (modo: crear · cargar · primera). Para lo que vive fuera del hub:
    el archivo mínimo add_agent_tui.py, `workspace agregar`, el primer arranque. → lo que devuelve hub_directo.correr
    (None sin terminal, y lo dice en una línea: S6)."""
    import hub_directo
    rc = hub_directo.correr(agregar=modo, **kw)
    if rc is None:                                   # sin terminal: decir dónde vive, no salir callado
        try:
            print(_t("agregar.sin_terminal"))
        except (OSError, ValueError):
            pass
    return rc


if __name__ == "__main__":
    sys.exit(correr((sys.argv[1:] or ["crear"])[0]) or 0)
