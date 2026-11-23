// La bandeja de fichas (Monito ronda 2 · bloque P): UNA ventanita de la app, pegada al monito y siempre en el mismo
// lugar (LugarBandeja), con una ficha por cada cosa que espera tu clic: lo que quiere hacer el monito (el portero), los
// permisos de su motor (la página), lo que quedó para después y lo que ya hizo. La lógica vive en LogicaBandeja.swift.
//   · Las arma la APP con datos del portero o de la página (TextoFicha); nada de lo que pinta es texto del agente,
//     salvo el DATO del pedido (la dirección, el comando), que va aparte, entero y como dato.
//   · Solo cuentan los clics de una persona (BotonTarjeta: EventoReal.dePersona; por accesibilidad no se aprietan), su
//     botón se activa a los 0.6 s de verse y lo coral se sostiene 1.5 s. No toma el teclado ni sale en las fotos.
//   · Tono por riesgo (lavanda, ámbar, coral, menta), el puntito del color del agente, una frase con verbo, el botón
//     principal relleno y grande (36 pt) y «No» como texto simple.
//   · Al llegar una: el monito brinca y enseña su número (la burbuja: WSMActuar.fichas). ~20 s sin tocarla: se dobla
//     (queda el número y un puntito en su carita de la barra de menú). Un clic en el monito la despliega.
//   · «Parar» es un botón rojo aparte, que solo se ve mientras algo se está haciendo. Esc Esc sigue parando todo.
import AppKit

extension NSColor {
    /// «#rrggbb» → color (si no se entiende, lavanda).
    static func hex(_ s: String, alpha: CGFloat = 1) -> NSColor {
        var h = s.trimmingCharacters(in: .whitespaces)
        if h.hasPrefix("#") { h.removeFirst() }
        guard h.count == 6, let n = UInt32(h, radix: 16) else { return NSColor(red: 0.65, green: 0.58, blue: 1, alpha: alpha) }
        return NSColor(red: CGFloat((n >> 16) & 255) / 255, green: CGFloat((n >> 8) & 255) / 255, blue: CGFloat(n & 255) / 255, alpha: alpha)
    }
}

/// Los colores de una ficha por su tono (suaves, sobre la piel lavanda).
struct PielFicha {
    var raya: NSColor
    var orilla: NSColor
    var boton: NSColor

    static let fondo = NSColor.hex("#1f1f23", alpha: 0.985)
    static let texto = NSColor.hex("#ececf1")
    static let texto2 = NSColor.hex("#b3b3bd")
    static let texto3 = NSColor.hex("#84848f")
    static let rojo = NSColor.hex("#e5534b")

    static func de(_ t: TonoBandeja) -> PielFicha {
        switch t {
        case .lavanda: return PielFicha(raya: .hex("#a594ff"), orilla: NSColor(red: 165 / 255, green: 148 / 255, blue: 1, alpha: 0.36), boton: .hex("#a594ff"))
        case .ambar: return PielFicha(raya: .hex("#e7a43a"), orilla: NSColor(red: 231 / 255, green: 164 / 255, blue: 58 / 255, alpha: 0.38), boton: .hex("#f0bd62"))
        case .coral: return PielFicha(raya: .hex("#f07864"), orilla: NSColor(red: 240 / 255, green: 120 / 255, blue: 100 / 255, alpha: 0.42), boton: .hex("#f08a76"))
        case .menta: return PielFicha(raya: .hex("#3fbf7f"), orilla: NSColor(red: 63 / 255, green: 191 / 255, blue: 127 / 255, alpha: 0.40), boton: .hex("#7fd6ad"))
        }
    }
}

/// Un texto que se aprieta («No», «Ver todas», «Olvidar lo leído»): sin relleno; solo clics de una persona.
final class TextoBoton: NSView {
    let titulo: String
    var color: NSColor
    var tam: CGFloat
    var alPulsar: (() -> Void)?
    var alRechazar: (() -> Void)?

    init(_ titulo: String, color: NSColor = PielFicha.texto2, tam: CGFloat = 13.5) {
        self.titulo = titulo
        self.color = color
        self.tam = tam
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false
        setContentCompressionResistancePriority(.required, for: .horizontal)
    }

    required init?(coder: NSCoder) { nil }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func accessibilityPerformPress() -> Bool { false }
    private var atributos: [NSAttributedString.Key: Any] { [.font: NSFont.systemFont(ofSize: tam, weight: .semibold), .foregroundColor: color] }

    override var intrinsicContentSize: NSSize {
        let s = (titulo as NSString).size(withAttributes: atributos)
        return NSSize(width: ceil(s.width) + 12, height: max(36, ceil(s.height) + 12))       // blanco grande para el dedo
    }

    override func draw(_ r: NSRect) {
        let s = (titulo as NSString).size(withAttributes: atributos)
        (titulo as NSString).draw(at: NSPoint(x: bounds.midX - s.width / 2, y: bounds.midY - s.height / 2), withAttributes: atributos)
    }

    override func mouseUp(with e: NSEvent) {
        guard EventoReal.dePersona(e) else { alRechazar?(); return }
        if bounds.contains(convert(e.locationInWindow, from: nil)) { alPulsar?() }
    }
}

/// El fondo de una ficha: su caja, su orilla del tono y la raya de 4 pt a la izquierda.
final class FondoFicha: NSView {
    var piel = PielFicha.de(.lavanda)
    override func draw(_ r: NSRect) {
        let caja = NSBezierPath(roundedRect: bounds.insetBy(dx: 0.5, dy: 0.5), xRadius: 16, yRadius: 16)
        PielFicha.fondo.setFill()
        caja.fill()
        NSGraphicsContext.saveGraphicsState()
        caja.addClip()
        piel.raya.setFill()
        NSRect(x: 0, y: 0, width: 4, height: bounds.height).fill()
        NSGraphicsContext.restoreGraphicsState()
        piel.orilla.setStroke()
        caja.lineWidth = 1
        caja.stroke()
    }
}

/// Una ficha pintada.
@MainActor
final class VistaFicha: NSView {
    static let ancho: CGFloat = 310
    static let altoBoton: CGFloat = 36
    nonisolated private static let sangria: CGFloat = 17

    let ficha: FichaBandeja
    private(set) var principal: BotonTarjeta!
    /// Los renglones que se aprietan (elegir): se arman igual que el principal.
    private var opciones: [BotonTarjeta] = []
    private var casilla: CasillaTarjeta?
    private var nota: NSTextField?
    /// (botón, la casilla marcada)
    var alBoton: ((String, Bool) -> Void)?
    var alRechazar: ((String) -> Void)?

    init(_ f: FichaBandeja) {
        ficha = f
        super.init(frame: NSRect(x: 0, y: 0, width: VistaFicha.ancho, height: 100))
        translatesAutoresizingMaskIntoConstraints = false
        armar()
    }

    required init?(coder: NSCoder) { nil }

    private func etiqueta(_ s: String, _ tam: CGFloat, _ peso: NSFont.Weight = .regular, _ c: NSColor = PielFicha.texto, mono: Bool = false,
                          sangria: CGFloat = VistaFicha.sangria) -> NSTextField {
        let l = NSTextField(wrappingLabelWithString: s)
        l.font = mono ? NSFont.monospacedSystemFont(ofSize: tam, weight: peso) : NSFont.systemFont(ofSize: tam, weight: peso)
        l.textColor = c
        l.maximumNumberOfLines = 0                       // entero: lo que no se ve no se aprueba
        l.lineBreakMode = mono ? .byCharWrapping : .byWordWrapping
        l.preferredMaxLayoutWidth = VistaFicha.ancho - 29 - sangria
        l.isSelectable = false
        return l
    }

    private func sangrada(_ v: NSView) -> NSView {
        let caja = NSStackView(views: [v])
        caja.orientation = .horizontal
        caja.edgeInsets = NSEdgeInsets(top: 0, left: VistaFicha.sangria, bottom: 0, right: 0)
        return caja
    }

    /// La dirección ENTERA, con su sitio resaltado (entero también: lo que engaña es ver solo el principio).
    private func direccion(_ url: String, sitio: String?) -> NSTextField {
        let l = etiqueta(url, 12.5, .regular, PielFicha.texto2, mono: true)
        let a = NSMutableAttributedString(string: url, attributes: [.font: NSFont.monospacedSystemFont(ofSize: 12.5, weight: .regular),
                                                                     .foregroundColor: PielFicha.texto2])
        if let s = sitio, !s.isEmpty, let r = url.range(of: s, options: .caseInsensitive) {
            a.addAttributes([.foregroundColor: PielFicha.texto, .backgroundColor: NSColor(red: 240 / 255, green: 120 / 255, blue: 100 / 255, alpha: 0.20),
                             .font: NSFont.monospacedSystemFont(ofSize: 12.5, weight: .semibold)], range: NSRange(r, in: url))
        }
        l.attributedStringValue = a
        return l
    }

    private func armar() {
        let f = ficha, piel = PielFicha.de(f.tono)
        let fondo = FondoFicha(frame: bounds)
        fondo.piel = piel
        fondo.translatesAutoresizingMaskIntoConstraints = false
        addSubview(fondo)
        let pila = NSStackView()
        pila.orientation = .vertical
        pila.alignment = .leading
        pila.spacing = 6
        pila.translatesAutoresizingMaskIntoConstraints = false
        addSubview(pila)
        NSLayoutConstraint.activate([
            fondo.leadingAnchor.constraint(equalTo: leadingAnchor), fondo.trailingAnchor.constraint(equalTo: trailingAnchor),
            fondo.topAnchor.constraint(equalTo: topAnchor), fondo.bottomAnchor.constraint(equalTo: bottomAnchor),
            pila.leadingAnchor.constraint(equalTo: leadingAnchor, constant: 16), pila.trailingAnchor.constraint(equalTo: trailingAnchor, constant: -13),
            pila.topAnchor.constraint(equalTo: topAnchor, constant: 11), pila.bottomAnchor.constraint(equalTo: bottomAnchor, constant: -12),
            widthAnchor.constraint(equalToConstant: VistaFicha.ancho),
        ])
        // el puntito del color de su agente y la frase con verbo
        let cab = NSStackView()
        cab.orientation = .horizontal
        cab.alignment = .top
        cab.spacing = 8
        let punto = FondoTarjeta(frame: NSRect(x: 0, y: 0, width: 9, height: 9))
        punto.relleno = NSColor.hex(f.color)
        punto.radio = 4.5
        punto.grosor = 0
        punto.translatesAutoresizingMaskIntoConstraints = false
        let cajaPunto = NSView()
        cajaPunto.translatesAutoresizingMaskIntoConstraints = false
        cajaPunto.addSubview(punto)
        NSLayoutConstraint.activate([cajaPunto.widthAnchor.constraint(equalToConstant: 9), cajaPunto.heightAnchor.constraint(equalToConstant: 18),
                                     punto.widthAnchor.constraint(equalToConstant: 9), punto.heightAnchor.constraint(equalToConstant: 9),
                                     punto.leadingAnchor.constraint(equalTo: cajaPunto.leadingAnchor),
                                     punto.topAnchor.constraint(equalTo: cajaPunto.topAnchor, constant: 5)])
        cab.addArrangedSubview(cajaPunto)
        cab.addArrangedSubview(etiqueta(f.titulo, 14, .semibold, PielFicha.texto, sangria: VistaFicha.sangria))
        pila.addArrangedSubview(cab)
        // lo que va a pasar, entero y como dato
        if !f.partes.isEmpty {
            // junto5 · un borrador de correo: Para · Asunto · Texto, cada uno con su etiqueta y ENTERO
            for p in f.partes {
                let e = etiqueta(p.etiqueta.uppercased(), 10, .bold, PielFicha.texto3)
                pila.addArrangedSubview(sangrada(e))
                pila.setCustomSpacing(1, after: pila.arrangedSubviews.last!)
                pila.addArrangedSubview(sangrada(etiqueta(p.valor.isEmpty ? "(vacío)" : p.valor, 12.5, p.etiqueta == "Texto" ? .regular : .semibold,
                                                          p.valor.isEmpty ? PielFicha.texto3 : PielFicha.texto2)))
            }
        } else if !f.detalle.isEmpty {
            switch f.detalleTipo {
            case "url": pila.addArrangedSubview(sangrada(direccion(f.detalle, sitio: f.sitio)))
            case "ruta", "comando", "lista": pila.addArrangedSubview(sangrada(etiqueta(f.detalle, 12, .regular, PielFicha.texto2, mono: true)))
            default: pila.addArrangedSubview(sangrada(etiqueta(f.detalle, 12.5, .regular, PielFicha.texto2)))
            }
        }
        if let l = f.leyo {
            pila.addArrangedSubview(sangrada(etiqueta(l, 11.5, .bold, PielFicha.de(.coral).raya)))
        }
        // fichas de trabajo (carril 6): los renglones de una intención, o los candidatos como botones (tu toque elige y aprueba)
        let anchoDentro = VistaFicha.ancho - 29 - VistaFicha.sangria
        for r in f.renglones {
            if f.elige {
                let o = BotonTarjeta(r.titulo)
                o.alto = VistaFicha.altoBoton
                o.radio = 10
                o.letra = 13
                o.activo = f.armaMs <= 0
                o.alPulsar = { [weak self] in self?.pulsado("r:" + r.id) }
                o.alRechazar = { [weak self] in self?.rechazado("r:" + r.id) }
                o.widthAnchor.constraint(equalToConstant: anchoDentro).isActive = true
                opciones.append(o)
                pila.addArrangedSubview(sangrada(o))
            } else {
                pila.addArrangedSubview(sangrada(etiqueta(r.titulo, 13, .semibold, PielFicha.texto)))
            }
            if !r.detalle.isEmpty {
                let d = etiqueta(r.detalle, 11.5, .regular, PielFicha.texto3)
                pila.setCustomSpacing(2, after: pila.arrangedSubviews.last!)
                pila.addArrangedSubview(sangrada(d))
            }
        }
        // los botones: el principal, relleno y grande; «No», texto simple
        let b = BotonTarjeta(f.principal.titulo, primario: true, color: piel.boton)
        b.alto = VistaFicha.altoBoton
        b.radio = 12
        b.letra = 14
        b.sostener = Double(f.sostenerMs) / 1000
        b.activo = f.armaMs <= 0
        b.alPulsar = { [weak self] in self?.pulsado(f.principal.id) }
        b.alRechazar = { [weak self] in self?.rechazado(f.principal.id) }
        principal = b
        let fila = NSStackView()
        fila.orientation = .horizontal
        fila.spacing = 10
        if f.principal.id.isEmpty {
            // (elegir: no hay botón principal; el toque va en su renglón)
        } else if f.sostenerMs > 0 {
            b.widthAnchor.constraint(equalToConstant: VistaFicha.ancho - 29 - VistaFicha.sangria).isActive = true
            pila.setCustomSpacing(10, after: pila.arrangedSubviews.last!)
            pila.addArrangedSubview(sangrada(b))
        } else {
            fila.addArrangedSubview(b)
        }
        var segundo: BotonTarjeta? = nil
        if let s = f.segundo {
            let x = BotonTarjeta(s.titulo)
            x.alto = VistaFicha.altoBoton
            x.radio = 12
            x.letra = 13
            x.alPulsar = { [weak self] in self?.pulsado(s.id) }
            x.alRechazar = { [weak self] in self?.rechazado(s.id) }
            segundo = x
        }
        var no: TextoBoton? = nil
        if f.conNo {
            let x = TextoBoton(f.noTitulo)
            x.alPulsar = { [weak self] in self?.pulsado("no") }
            x.alRechazar = { [weak self] in self?.rechazado("no") }
            no = x
        }
        // si los tres no caben en un renglón, el segundo botón baja al suyo (nada se encima ni se corta)
        let cabe = VistaFicha.ancho - 29 - VistaFicha.sangria
        let ancho = (f.sostenerMs > 0 || f.principal.id.isEmpty ? 0 : b.intrinsicContentSize.width + 10) + (segundo.map { $0.intrinsicContentSize.width + 10 } ?? 0)
            + (no?.intrinsicContentSize.width ?? 0)
        var abajo: NSView? = nil
        if let x = segundo { if ancho > cabe { abajo = x } else { fila.addArrangedSubview(x) } }
        if let x = no { fila.addArrangedSubview(x) }
        if !fila.arrangedSubviews.isEmpty {
            if f.sostenerMs == 0 { pila.setCustomSpacing(10, after: pila.arrangedSubviews.last!) }
            pila.addArrangedSubview(sangrada(fila))
        }
        if let x = abajo { pila.addArrangedSubview(sangrada(x)) }
        if let c = f.casilla {
            let k = CasillaTarjeta(c)
            k.marcada = f.casillaMarcada
            k.color = piel.boton
            k.resaltada = f.resaltarCasilla
            k.alRechazar = { [weak self] in self?.rechazado("casilla") }
            k.widthAnchor.constraint(equalToConstant: VistaFicha.ancho - 29 - VistaFicha.sangria).isActive = true
            casilla = k
            pila.addArrangedSubview(sangrada(k))
        }
        if f.puedeOlvidar {
            let o = TextoBoton("Olvidar lo leído", color: PielFicha.texto3, tam: 11.5)
            o.alPulsar = { [weak self] in self?.pulsado("olvidar") }
            o.alRechazar = { [weak self] in self?.rechazado("olvidar") }
            pila.addArrangedSubview(sangrada(o))
        }
        if !f.pie.isEmpty {
            let n = etiqueta(f.pie, 11.5, .regular, PielFicha.texto3)
            nota = n
            pila.addArrangedSubview(sangrada(n))
        }
    }

    /// El armado: el botón principal se activa a los 0.6 s de verse (`visto`: desde cuándo se ve en este despliegue).
    func latido(visto: Date, ahora: Date) {
        guard !principal.activo, ficha.armaMs > 0 else { return }
        let ms = ahora.timeIntervalSince(visto) * 1000
        if ms >= Double(ficha.armaMs) { principal.activo = true; principal.progreso = 0; opciones.forEach { $0.activo = true } }
        else { principal.progreso = CGFloat(ms / Double(ficha.armaMs)) }
    }

    private func pulsado(_ id: String) {
        // el principal, nunca antes de armarse (lo coral, además, sostenido: eso lo hace su botón)
        if id == ficha.principal.id, !principal.activo { return }
        if id.hasPrefix("r:"), !principal.activo { return }
        alBoton?(id, casilla?.marcada ?? false)
    }

    private func rechazado(_ boton: String) {
        nota?.stringValue = "Ese clic no vino de tu mouse ni de tu trackpad: no cuenta."
        alRechazar?(boton)
    }

    /// Solo la copia de prueba y las fotos: como si ya se hubiera armado.
    func armarYa() { principal.activo = true; principal.progreso = 0; opciones.forEach { $0.activo = true } }
    var casillaMarcada: Bool { casilla?.marcada ?? false }
}

/// La bandeja en la app: su estado (Bandeja), su ventanita y lo que pasa con cada botón.
@MainActor
final class BandejaApp {
    unowned let monito: Monito
    private(set) var estado = Bandeja()
    var ajustes = AjustesBandeja()
    /// ¿Algo se está haciendo ahora? (entonces sale «Parar») · qué hace «Parar»
    var corriendo: () -> Bool = { false }
    var alParar: () -> Void = {}
    /// Un clic que no vino de una persona (lo anota Actuar en la bitácora).
    var clicRechazado: ((String, String) -> Void)?
    /// Los agentes como los ves: id → (nombre, color).
    private(set) var agentes: [String: (nombre: String, color: String)] = [:]
    /// Lo que hace cada ficha con su botón: (botón, casilla marcada).
    private var acciones: [String: (String, Bool) -> Void] = [:]
    private let panel: PanelTarjeta
    private(set) var vistas: [String: VistaFicha] = [:]
    /// Desde cuándo se ve cada ficha en ESTE despliegue (su armado de 0.6 s vuelve a empezar al desplegar).
    private(set) var vistoDesde: [String: Date] = [:]
    /// Lo que se publicó (para la copia de prueba: Actuar.swift).
    var alPublicar: (([String: Any]) -> Void)?
    private var reloj: Timer?
    private var pintado = ""
    private var ultimoMarco = CGRect.zero
    private var habiaCorriendo = false

    init(monito: Monito) {
        self.monito = monito
        panel = PanelTarjeta(contentRect: NSRect(x: 0, y: 0, width: VistaFicha.ancho + 12, height: 100),
                             styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = true
        panel.level = .modalPanel
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle]
        panel.hidesOnDeactivate = false
        panel.sharingType = .none                 // fuera de las fotos de la pantalla
        panel.title = "Workspace Compañero · fichas"
        if monito.op.fantasma { panel.alphaValue = 0.02; panel.ignoresMouseEvents = true }
        reloj = Timer.scheduledTimer(withTimeInterval: 1.0 / 15.0, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.latido() }
        }
    }

    func nombre(_ a: String) -> String { agentes[a]?.nombre ?? a }
    func color(_ a: String) -> String { agentes[a]?.color ?? "#8b5cf6" }

    func agentesLlegaron(_ lista: [(id: String, nombre: String, color: String)]) {
        agentes = Dictionary(lista.map { ($0.id, (nombre: $0.nombre, color: $0.color)) }, uniquingKeysWith: { x, _ in x })
    }

    // MARK: poner y quitar

    /// Llega (o cambia) una ficha, con lo que hace su botón. Una nueva: el monito brinca y, si lo prendiste, suena.
    func poner(_ f: FichaBandeja, _ accion: @escaping (String, Bool) -> Void) {
        acciones[f.id] = accion
        let r = estado.poner(f, ahora: Date())
        if r == .nueva { llego(1) }
        if r != .igual { repintar() }
    }

    func quitar(_ id: String) {
        acciones[id] = nil
        vistoDesde[id] = nil
        if estado.quitar(id) != nil { repintar() }
    }

    func ficha(_ id: String) -> FichaBandeja? { estado.ficha(id) }

    private func llego(_ n: Int) {
        monito.jsManos("WSMActuar.fichaLlego()")                  // el brinco de «te necesita»
        if ajustes.sonido, !monito.op.fantasma, let s = NSSound(named: "Tink") {
            s.volume = 0.25
            s.play()
        }
    }

    /// «Atlas te pregunta · [Contestar]»: su pregunta sigue en su burbuja (la ficha no lleva texto del agente); aquí
    /// cuenta en el número y te lleva a contestarla.
    func pregunta(agente a: String, hay: Bool) {
        let id = "q:" + a
        guard hay else { quitar(id); return }
        if estado.ficha(id) != nil { return }
        poner(TextoFicha.pregunta(agente: a, nombre: nombre(a), color: color(a), ahora: Date())) { [weak self] boton, _ in
            guard let self = self else { return }
            self.quitar(id)
            if boton == "contestar" { self.monito.contestarPregunta(a) }
        }
    }

    // MARK: los permisos de su motor (el evento «fichas» del puente)

    func deMotor(_ o: [String: Any]) {
        guard let e = PermisoMotor.evento(o) else { return }
        let ahora = Date(), a = e.agente, n = nombre(a), c = color(a)
        var fs = e.esperan.map { TextoFicha.deMotor($0, agente: a, nombre: n, color: c, motor: e.motor, despues: false, ahora: ahora) }
        fs += e.despues.map { TextoFicha.deMotor($0, agente: a, nombre: n, color: c, motor: e.motor, despues: true, ahora: ahora) }
        if e.interrumpidos > 0 { fs.append(TextoFicha.interrumpida(e.interrumpidos, agente: a, nombre: n, color: c, ahora: ahora)) }
        for f in fs { acciones[f.id] = { [weak self] boton, _ in self?.botonDeMotor(f.id, boton) } }
        let nuevas = estado.ponerDeMotor(agente: a, fs, ahora: ahora)
        if nuevas > 0 { llego(nuevas) }
        repintar()
    }

    /// Un botón de una ficha de su motor (o de su grupo): se contesta por el puente, como hoy la tarjeta de la burbuja.
    private func botonDeMotor(_ id: String, _ boton: String) {
        let ms = estado.miembros(id)
        guard let p = ms.first else { return }
        if boton == "sueltas" { if let k = Bandeja.claveGrupo(p) { estado.soltar(k); estado.verTodas = true }; repintar(); return }
        if p.id.hasPrefix("mi:") {                                 // lo que cortó un reinicio
            if boton == "otra_vez" { monito.mandarAlPuente(["op": "mandar", "agente": p.agente, "texto": TextoFicha.otraVez(p), "sin_contexto": true]) }
            estado.quitar(p.id)
            repintar()
            return
        }
        // M-2 · lo cortado no se permite desde la ficha, llegue el botón que llegue
        if ms.contains(where: { $0.cortado }), boton != "no" { return }
        let ids = ms.flatMap { $0.deMotor }
        if p.estado == .despues {
            let d = boton == "no" ? "negar" : "permitir"
            guard boton == "no" || boton == "despues" || boton == "todas" else { return }
            monito.mandarAlPuente(["op": "permiso_despues", "agente": p.agente, "ids": ids, "decision": d])
        } else {
            let d: String
            switch boton {
            case "permitir", "todas": d = "permitir"
            case "permitir_turno": d = "permitir_turno"
            case "no": d = "negar"
            default: return
            }
            for pid in ids { monito.mandarAlPuente(["op": "permiso", "agente": p.agente, "id": pid, "decision": d]) }
        }
        for m in ms { estado.quitar(m.id); acciones[m.id] = nil }
        repintar()
    }

    // MARK: lo que haces

    /// Un botón de una ficha (o del grupo). `persona`: el clic vino de una persona (lo revisó su botón).
    func boton(_ id: String, _ boton: String, casilla: Bool) {
        estado.tocar(ahora: Date())
        if id.hasPrefix("g:") { botonDeMotor(id, boton); return }
        acciones[id]?(boton, casilla)
    }

    /// Un clic en el monito (E2-a): con algo pendiente y doblada, se despliega. → true si eso hizo (no abre la barra).
    func clicEnMonito() -> Bool {
        guard ClicMonito.que(pendientes: estado.cuenta, plegada: estado.plegada) == .desplegar else { return false }
        _ = estado.desplegar(ahora: Date())
        vistoDesde = [:]
        repintar()
        return true
    }

    /// Guardaste al Compañero (Monito.guardarTodo): sus fichas se doblan en su número (no se pierden: un clic en él las
    /// vuelve a enseñar). Lo mismo que hacen solas a los 20 s.
    func plegar() {
        guard !estado.plegada else { return }
        estado.plegar()
        vistoDesde = [:]
        repintar()
    }

    /// Lo que pide la burbuja (el chat grande): un botón de una ficha. Lo que aprueba algo solo vale si hubo un clic de
    /// una persona en el monito hace un instante (`reciente`) y la ficha ya estaba armada; lo coral, solo en su ficha.
    /// Lo último publicado (el número, si está doblada y las fichas): la ventana del chat grande lo pide al abrir.
    var publicado: String? { pintado.isEmpty ? nil : BandejaApp.jsFichas(pintado) }
    /// La página de la ventana puede no tener las manos montadas todavía: se le habla con cuidado.
    static func jsFichas(_ k: String) -> String { "typeof WSMActuar!=='undefined'&&WSMActuar.fichas(\(k))" }

    func deLaBurbuja(_ d: [String: Any], reciente: Bool) {
        guard let id = d["id"] as? String, let b = d["boton"] as? String else { return }
        if (d["op"] as? String) == "ficha_ver" { _ = estado.desplegar(ahora: Date()); vistoDesde = [:]; repintar(); return }
        guard let f = estado.vista().tarjetas.first(where: { $0.id == id }) ?? estado.ficha(id) else { return }
        let inocuo = ["no", "cerrar", "sueltas"].contains(b)
        if !inocuo {
            let armada = Date().timeIntervalSince(f.llego) * 1000 >= Double(f.armaMs)
            // lo coral (se sostiene) y lo que trae casilla (la primera vez, «no me preguntes») solo en su ficha de la app
            if f.sostenerMs > 0 || f.casilla != nil || !f.renglones.isEmpty || !reciente || !armada {
                if !reciente { clicRechazado?(id, b) }
                _ = estado.desplegar(ahora: Date())               // se contesta en su ficha, junto al monito
                repintar()
                return
            }
        }
        guard b == "no" || b == f.principal.id || b == f.segundo?.id else { return }
        boton(id, b, casilla: false)
    }

    // MARK: pintar

    private func latido() {
        let ahora = Date()
        if panel.isVisible, panel.frame.insetBy(dx: -6, dy: -6).contains(NSEvent.mouseLocation), !monito.op.fantasma { estado.tocar(ahora: ahora) }
        let corre = corriendo()
        if estado.tic(ahora: ahora) || corre != habiaCorriendo {
            habiaCorriendo = corre
            repintar()
        } else if panel.isVisible {
            for (id, v) in vistas { v.latido(visto: vistoDesde[id] ?? ahora, ahora: ahora) }
            colocar()
        }
    }

    /// El número del monito, el puntito de la barra de menú y lo que la burbuja necesita para pintarlas (WSFichas).
    private func publicar(_ ts: [FichaBandeja]) {
        let o: [String: Any] = ["n": estado.cuenta, "plegada": estado.plegada, "fichas": ts.map { $0.json() }]
        let k = Permisos.json(o)
        if k != pintado {
            pintado = k
            monito.jsManos("WSMActuar.fichas(\(k))")
            monito.entregas?.ventana?.js(BandejaApp.jsFichas(k))     // junto5: la columna «Te esperan» del chat grande
        }
        monito.puntoEnBarra(estado.punto)
        alPublicar?(o)
    }

    func repintar() {
        let v = estado.vista(), ahora = Date()
        publicar(v.tarjetas)
        let corre = corriendo()
        let visibles = estado.plegada ? [] : v.tarjetas
        if estado.plegada { vistoDesde = [:] }
        guard !visibles.isEmpty || corre else {
            vistas = [:]
            panel.orderOut(nil)
            return
        }
        let pila = NSStackView()
        pila.orientation = .vertical
        pila.alignment = monito.lado.h == "der" ? .trailing : .leading
        pila.spacing = 10
        pila.translatesAutoresizingMaskIntoConstraints = false
        vistas = [:]
        for f in visibles {
            let k = VistaFicha(f)
            k.alBoton = { [weak self] b, c in self?.boton(f.id, b, casilla: c) }
            k.alRechazar = { [weak self] b in self?.clicRechazado?(f.id, b) }
            if vistoDesde[f.id] == nil { vistoDesde[f.id] = ahora }
            k.latido(visto: vistoDesde[f.id]!, ahora: ahora)
            vistas[f.id] = k
            pila.addArrangedSubview(k)
        }
        vistoDesde = vistoDesde.filter { vistas[$0.key] != nil }
        if !estado.plegada, v.ocultas > 0 {
            let mas = TextoBoton("Ver todas (\(v.tarjetas.count + v.ocultas))", color: PielFicha.texto, tam: 13)
            mas.alPulsar = { [weak self] in self?.estado.verTodas = true; self?.estado.tocar(ahora: Date()); self?.repintar() }
            pila.addArrangedSubview(pastilla(mas))
        } else if !estado.plegada, estado.verTodas, v.tarjetas.count > Bandeja.tope {
            let menos = TextoBoton("Ver menos", color: PielFicha.texto, tam: 13)
            menos.alPulsar = { [weak self] in self?.estado.verTodas = false; self?.repintar() }
            pila.addArrangedSubview(pastilla(menos))
        }
        if corre {
            // «Parar»: rojo y aparte; solo mientras algo se está haciendo (E2-a). Esc Esc también para todo.
            let p = BotonTarjeta("■  Parar", primario: true, color: PielFicha.rojo)
            p.alto = VistaFicha.altoBoton
            p.radio = 18
            p.letra = 13.5
            p.tintaClara = true
            p.alPulsar = { [weak self] in self?.alParar() }
            p.alRechazar = { [weak self] in self?.clicRechazado?("parar", "parar") }
            let fila = NSStackView(views: [NSTextField(labelWithString: "Esc Esc"), p])
            (fila.arrangedSubviews[0] as? NSTextField)?.textColor = PielFicha.texto3
            (fila.arrangedSubviews[0] as? NSTextField)?.font = NSFont.systemFont(ofSize: 11.5)
            fila.spacing = 8
            pila.addArrangedSubview(fila)
        }
        let caja = NSView()
        caja.addSubview(pila)
        NSLayoutConstraint.activate([pila.leadingAnchor.constraint(equalTo: caja.leadingAnchor, constant: 6),
                                     pila.trailingAnchor.constraint(equalTo: caja.trailingAnchor, constant: -6),
                                     pila.topAnchor.constraint(equalTo: caja.topAnchor, constant: 6),
                                     pila.bottomAnchor.constraint(equalTo: caja.bottomAnchor, constant: -6)])
        panel.contentView = caja
        caja.layoutSubtreeIfNeeded()
        let t = pila.fittingSize
        panel.setContentSize(NSSize(width: max(t.width, VistaFicha.ancho) + 12, height: ceil(t.height) + 12))
        ultimoMarco = .zero
        colocar()
        panel.orderFrontRegardless()
        if !monito.op.foto.isEmpty {
            let f = monito.op.foto
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.2) { [weak self] in self?.foto(f + "_bandeja.png") }
        }
    }

    private func pastilla(_ t: TextoBoton) -> NSView {
        let f = FondoTarjeta(frame: .zero)
        f.relleno = PielFicha.fondo
        f.tinta = NSColor(white: 1, alpha: 0.2)
        f.grosor = 1
        f.radio = 18
        f.translatesAutoresizingMaskIntoConstraints = false
        f.addSubview(t)
        NSLayoutConstraint.activate([t.leadingAnchor.constraint(equalTo: f.leadingAnchor, constant: 8), t.trailingAnchor.constraint(equalTo: f.trailingAnchor, constant: -8),
                                     t.topAnchor.constraint(equalTo: f.topAnchor), t.bottomAnchor.constraint(equalTo: f.bottomAnchor)])
        return f
    }

    /// Pegada al monito, siempre en el mismo lugar (si su burbuja está abierta ahí, a su lado).
    private func colocar() {
        let nido = monito.nidoActual
        let pantalla = NSScreen.screens.first { $0.frame.intersects(nido) } ?? NSScreen.main ?? NSScreen.screens.first
        let vf = pantalla?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let m = LugarBandeja.marco(tam: panel.frame.size, nido: nido, lado: monito.lado, ocupado: monito.burbujaEnPantalla(), visible: vf)
        if m != ultimoMarco {
            ultimoMarco = m
            panel.setFrame(m, display: true)
        }
    }

    /// Para las pruebas (sin grabar la pantalla): lo que pinta la bandeja, a un PNG, con los botones ya armados.
    func foto(_ ruta: String) {
        vistas.values.forEach { $0.armarYa() }
        guard let v = panel.contentView, v.bounds.width > 0, let rep = v.bitmapImageRepForCachingDisplay(in: v.bounds) else { return }
        v.cacheDisplay(in: v.bounds, to: rep)
        try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: ruta))
    }
}
