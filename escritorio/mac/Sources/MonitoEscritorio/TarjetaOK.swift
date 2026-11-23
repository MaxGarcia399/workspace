// Las piezas de las fichas (antes, de la tarjeta de OK): el panel que no toma el teclado, el botón dibujado a mano que
// solo acepta clics de una persona, la casilla y el fondo. Desde la ronda 2 la tarjeta de OK y la confirmación de
// «Prender» ya no son ventanitas sueltas junto a tu mouse: son FICHAS de la bandeja pegada al monito (Bandeja.swift),
// con estas mismas piezas y las mismas reglas:
//   · No toman el teclado (Enter no aprueba nada; nadie las contesta escribiendo) y no salen en las fotos de la pantalla.
//   · Solo cuentan los clics de una persona (EventoReal: el mouse o el trackpad, no otro programa que mande eventos ni
//     la accesibilidad); el botón se activa a los 0.6 s y lo coral se sostiene 1.5 s.
//   · Enseñan ENTERO lo que se haría (sin recortar renglones).
import AppKit

extension EventoReal {
    /// El evento de AppKit → ¿lo mandó una persona? (su CGEvent: de qué proceso y de qué estado viene)
    @MainActor static func dePersona(_ e: NSEvent) -> Bool {
        let si = de(e.cgEvent)
        if !si, let c = e.cgEvent {                    // para la bitácora: de dónde dijo el sistema que venía
            ultimo = (c.getIntegerValueField(.eventSourceUnixProcessID), c.getIntegerValueField(.eventSourceStateID))
        }
        return si
    }
    /// El último clic rechazado: (proceso, estado) según el sistema (para diagnosticar en la bitácora).
    @MainActor static var ultimo: (pid: Int64, estado: Int64) = (-1, -1)
}

/// Un panel que nunca toma el teclado ni activa la app: los clics le llegan igual (acceptsFirstMouse en sus botones).
final class PanelTarjeta: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

/// Un botón dibujado a mano (se ve igual en la foto de prueba) que acepta el primer clic sin activar la app. Con
/// `sostener` > 0, hay que mantenerlo apretado ese tiempo (la barra se llena); si lo sueltas antes, no pasa nada.
final class BotonTarjeta: NSView {
    var titulo: String { didSet { needsDisplay = true } }
    var primario: Bool
    var color: NSColor
    var activo = true { didSet { needsDisplay = true } }
    /// 0…1: la barra de «se está armando» (0.6 s) o de «mantén» (1.5 s).
    var progreso: CGFloat = 0 { didSet { needsDisplay = true } }
    var sostener: TimeInterval = 0
    /// Su alto, su esquina y su letra (las fichas: 36 pt, relleno y grande).
    var alto: CGFloat = 32 { didSet { invalidateIntrinsicContentSize() } }
    var radio: CGFloat = 16
    var letra: CGFloat = 13 { didSet { invalidateIntrinsicContentSize() } }
    /// Letras claras sobre un relleno oscuro (el rojo de «Parar»).
    var tintaClara = false
    var alPulsar: (() -> Void)?
    /// Un clic que no vino de una persona (otro programa lo mandó): no cuenta y se anota.
    var alRechazar: (() -> Void)?
    private var apretadoDesde: Date?
    private var reloj: Timer?

    init(_ titulo: String, primario: Bool = false, color: NSColor = .white) {
        self.titulo = titulo
        self.primario = primario
        self.color = color
        super.init(frame: NSRect(x: 0, y: 0, width: 10, height: 32))
        translatesAutoresizingMaskIntoConstraints = false
        setContentCompressionResistancePriority(.required, for: .horizontal)
    }

    required init?(coder: NSCoder) { nil }

    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    /// Por accesibilidad no se aprieta (un programa con Accesibilidad no «da» el OK).
    override func accessibilityPerformPress() -> Bool { false }

    override var intrinsicContentSize: NSSize {
        let w = (titulo as NSString).size(withAttributes: [.font: NSFont.systemFont(ofSize: letra, weight: primario ? .bold : .medium)]).width
        return NSSize(width: ceil(w) + 32, height: alto)
    }

    override func draw(_ r: NSRect) {
        let b = bounds.insetBy(dx: 0.5, dy: 0.5)
        let p = NSBezierPath(roundedRect: b, xRadius: radio, yRadius: radio)
        if primario {
            (activo ? color : color.withAlphaComponent(0.35)).setFill()
            p.fill()
            if progreso > 0 && progreso < 1 {
                NSGraphicsContext.saveGraphicsState()
                p.addClip()
                NSColor.white.withAlphaComponent(0.28).setFill()
                NSRect(x: b.minX, y: b.minY, width: b.width * progreso, height: b.height).fill()
                NSGraphicsContext.restoreGraphicsState()
            }
        } else {
            NSColor(white: 1, alpha: 0.07).setFill()
            p.fill()
            NSColor(white: 1, alpha: 0.18).setStroke()
            p.stroke()
        }
        let tinta: NSColor = primario ? (tintaClara ? NSColor(white: 1, alpha: activo ? 1 : 0.6) : NSColor(white: 0.07, alpha: activo ? 1 : 0.55))
            : NSColor(white: 0.92, alpha: 1)
        let a: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: letra, weight: primario ? .bold : .medium), .foregroundColor: tinta]
        let s = (titulo as NSString).size(withAttributes: a)
        (titulo as NSString).draw(at: NSPoint(x: b.midX - s.width / 2, y: b.midY - s.height / 2), withAttributes: a)
    }

    override func mouseDown(with e: NSEvent) {
        guard activo else { return }
        guard EventoReal.dePersona(e) else { alRechazar?(); return }
        if sostener <= 0 { return }
        apretadoDesde = Date()
        reloj?.invalidate()
        reloj = Timer.scheduledTimer(withTimeInterval: 1.0 / 60.0, repeats: true) { [weak self] t in
            MainActor.assumeIsolated {
                guard let self = self, let d = self.apretadoDesde else { t.invalidate(); return }
                let f = min(1, CGFloat(Date().timeIntervalSince(d) / self.sostener))
                self.progreso = f
                if f >= 1 {
                    t.invalidate()
                    self.apretadoDesde = nil
                    self.alPulsar?()
                }
            }
        }
    }

    override func mouseUp(with e: NSEvent) {
        guard activo else { return }
        guard EventoReal.dePersona(e) else { alRechazar?(); return }
        if sostener > 0 {                        // lo soltaste antes de tiempo: no pasa nada
            reloj?.invalidate()
            apretadoDesde = nil
            progreso = 0
            return
        }
        if bounds.contains(convert(e.locationInWindow, from: nil)) { alPulsar?() }
    }
}

/// Una casilla dibujada a mano («Confío en este agente…»), con el primer clic.
final class CasillaTarjeta: NSView {
    var marcada = false { didSet { needsDisplay = true } }
    /// El color de su palomita (el del tono de su ficha) y si se resalta (al tercer OK: «¿dejo de preguntarte?»).
    var color = NSColor(red: 0.95, green: 0.76, blue: 0.31, alpha: 1) { didSet { needsDisplay = true } }
    var resaltada = false { didSet { needsDisplay = true } }
    let texto: String
    init(_ texto: String) {
        self.texto = texto
        super.init(frame: .zero)
        translatesAutoresizingMaskIntoConstraints = false
    }
    required init?(coder: NSCoder) { nil }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
    override func accessibilityPerformPress() -> Bool { false }
    var alRechazar: (() -> Void)?
    override var intrinsicContentSize: NSSize { NSSize(width: NSView.noIntrinsicMetric, height: 24) }
    override func draw(_ r: NSRect) {
        let c = NSRect(x: 1, y: bounds.midY - 8, width: 16, height: 16)
        let p = NSBezierPath(roundedRect: c, xRadius: 5, yRadius: 5)
        (marcada ? color : NSColor(white: 1, alpha: 0.08)).setFill()
        p.fill()
        (resaltada && !marcada ? color : NSColor(white: 1, alpha: 0.35)).setStroke()
        p.lineWidth = resaltada && !marcada ? 2 : 1.5
        p.stroke()
        if marcada {
            let v = NSBezierPath()
            v.move(to: NSPoint(x: c.minX + 3, y: c.midY))
            v.line(to: NSPoint(x: c.minX + 6, y: c.minY + 3.5))
            v.line(to: NSPoint(x: c.maxX - 3, y: c.maxY - 3))
            v.lineWidth = 2
            NSColor(white: 0.07, alpha: 1).setStroke()
            v.stroke()
        }
        let a: [NSAttributedString.Key: Any] = [.font: NSFont.systemFont(ofSize: 12.5, weight: resaltada ? .semibold : .regular),
                                                .foregroundColor: resaltada ? NSColor(white: 0.96, alpha: 1) : NSColor(white: 0.78, alpha: 1)]
        let alto = (texto as NSString).size(withAttributes: a).height
        (texto as NSString).draw(in: NSRect(x: 25, y: bounds.midY - alto / 2, width: bounds.width - 25, height: alto + 1), withAttributes: a)
    }
    override func mouseUp(with e: NSEvent) {
        guard EventoReal.dePersona(e) else { alRechazar?(); return }
        marcada.toggle()
    }
}

/// El fondo de la tarjeta, dibujado (no con capas: así sale igual en su foto de prueba).
final class FondoTarjeta: NSView {
    var tinta: NSColor = .white
    var radio: CGFloat = 18
    var relleno: NSColor = NSColor(red: 0.085, green: 0.08, blue: 0.105, alpha: 0.98)
    var grosor: CGFloat = 1.5
    override func draw(_ r: NSRect) {
        let p = NSBezierPath(roundedRect: bounds.insetBy(dx: grosor / 2 + 0.5, dy: grosor / 2 + 0.5), xRadius: radio, yRadius: radio)
        relleno.setFill()
        p.fill()
        if grosor > 0 {
            tinta.withAlphaComponent(0.85).setStroke()
            p.lineWidth = grosor
            p.stroke()
        }
    }
}
