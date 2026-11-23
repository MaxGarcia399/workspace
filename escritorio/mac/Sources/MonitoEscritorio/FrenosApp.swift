// Los frenos (A0): pánico y la banda «en vivo».
//   · Pánico: Esc Esc, ⌥ Espacio o un clic en el monito paran TODO lo que está en vuelo (la tarjeta abierta, lo que se
//     estaba haciendo, la banda). Esc va como atajo global de Carbon (RegisterEventHotKey: no pide Monitoreo de
//     entrada) y SOLO mientras hace algo (o con la banda en vivo); con una tarjeta esperando y el resto del tiempo, tus
//     apps tienen su Esc.
//   · La banda «en vivo» es del modo «con tu cursor» (A4, apagado de fábrica: «Puede tomar mi mouse: nunca»): arriba
//     dice «<agente> está usando tu mouse · paso 3 de 6 · 0:14 · Parar», con los bordes de la pantalla en su color y
//     una cuenta regresiva de 3 s antes de empezar; si mueves el mouse, se pausa. En A0 no mueve nada (no hay mano):
//     es la interfaz y el freno, listos para cuando exista.
import AppKit
import Carbon.HIToolbox

@MainActor
final class EscDeEmergencia {
    private var ref: EventHotKeyRef?
    private var previo: Date?
    var alPanico: (() -> Void)?
    var armado: Bool { ref != nil }

    /// Toma el Esc (mientras algo está en vuelo). → false si macOS no lo dio.
    @discardableResult
    func armar() -> Bool {
        guard ref == nil else { return true }
        Atajo.instalar()
        Atajo.alEsc = { [weak self] in self?.pulso() }
        let id = EventHotKeyID(signature: OSType(0x5753_4D4F), id: 2)       // «WSMO» · 2 = Esc
        let r = RegisterEventHotKey(UInt32(kVK_Escape), 0, id, GetApplicationEventTarget(), 0, &ref)
        if r != noErr { ref = nil }
        return r == noErr
    }

    /// Lo regresa (nada en vuelo): tus apps vuelven a recibir su Esc.
    func soltar() {
        if let r = ref { UnregisterEventHotKey(r) }
        ref = nil
        previo = nil
    }

    private func pulso() {
        let ahora = Date()
        if Frenos.esDobleEsc(previo: previo, ahora: ahora) {
            previo = nil
            alPanico?()
        } else {
            previo = ahora
        }
    }
}

/// Un borde de la pantalla en el color del agente (no toma clics).
final class BordeVista: NSView {
    var color: NSColor = .white
    override func draw(_ r: NSRect) {
        color.withAlphaComponent(0.9).setStroke()
        let p = NSBezierPath(rect: bounds.insetBy(dx: 3, dy: 3))
        p.lineWidth = 6
        p.stroke()
    }
}

@MainActor
final class BandaEnVivo {
    let agente: String
    let color: NSColor
    let pasos: Int
    var alParar: (() -> Void)?
    var alEmpezar: (() -> Void)?
    /// Pruebas: casi transparente (--fantasma), para fotografiarla sin que nadie la vea.
    var alfa: CGFloat = 1
    private let panel: PanelTarjeta
    private var bordes: [NSPanel] = []
    private let texto: NSTextField
    private let parar = BotonTarjeta("Parar")
    private let seguir = BotonTarjeta("Seguir")
    private var reloj: Timer?
    private(set) var paso = 0
    private var desde: Date?
    private var cuenta = Frenos.cuentaRegresiva
    private(set) var pausada = false
    /// Donde el monito dejó el mouse (en A0, donde estaba al empezar): si se mueve más que la tolerancia, se pausa.
    var esperado = NSEvent.mouseLocation

    init(agente: String, color: NSColor, pasos: Int) {
        self.agente = agente
        self.color = color
        self.pasos = max(1, pasos)
        panel = PanelTarjeta(contentRect: NSRect(x: 0, y: 0, width: 560, height: 46), styleMask: [.borderless, .nonactivatingPanel],
                             backing: .buffered, defer: false)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.level = .screenSaver
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle, .stationary]
        panel.sharingType = .none
        texto = NSTextField(labelWithString: "")
        texto.font = NSFont.systemFont(ofSize: 13.5, weight: .medium)
        texto.textColor = NSColor(white: 0.96, alpha: 1)
        let fondo = FondoTarjeta(frame: NSRect(x: 0, y: 0, width: 560, height: 46))
        fondo.tinta = color
        fondo.radio = 23
        fondo.grosor = 2
        let fila = NSStackView(views: [texto, seguir, parar])
        fila.orientation = .horizontal
        fila.spacing = 10
        fila.translatesAutoresizingMaskIntoConstraints = false
        fondo.addSubview(fila)
        NSLayoutConstraint.activate([fila.centerYAnchor.constraint(equalTo: fondo.centerYAnchor),
                                     fila.leadingAnchor.constraint(equalTo: fondo.leadingAnchor, constant: 18),
                                     fila.trailingAnchor.constraint(lessThanOrEqualTo: fondo.trailingAnchor, constant: -8)])
        seguir.isHidden = true
        panel.contentView = fondo
        parar.alPulsar = { [weak self] in self?.detener() }
        seguir.alPulsar = { [weak self] in self?.reanudar() }
    }

    /// Bordes de su color en cada pantalla, la banda arriba y la cuenta regresiva de 3 s.
    func empezar() {
        for s in NSScreen.screens {
            let p = NSPanel(contentRect: s.frame, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
            p.isOpaque = false
            p.backgroundColor = .clear
            p.ignoresMouseEvents = true
            p.level = .screenSaver
            p.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .ignoresCycle, .stationary]
            p.sharingType = .none
            let b = BordeVista(frame: NSRect(origin: .zero, size: s.frame.size))
            b.color = color
            p.contentView = b
            p.alphaValue = alfa
            p.orderFrontRegardless()
            bordes.append(p)
        }
        let s = NSScreen.main ?? NSScreen.screens.first
        let vf = s?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        panel.setFrameOrigin(NSPoint(x: vf.midX - panel.frame.width / 2, y: vf.maxY - panel.frame.height - 10))
        panel.alphaValue = alfa
        panel.ignoresMouseEvents = alfa < 1          // casi invisible (pruebas): que no se coma un clic de nadie
        panel.orderFrontRegardless()
        cuenta = Frenos.cuentaRegresiva
        pintar()
        reloj = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.latido() }
        }
    }

    private var tics = 0

    private func latido() {
        tics += 1
        if cuenta > 0 {
            if tics % 10 == 0 {
                cuenta -= 1
                if cuenta == 0 { desde = Date(); paso = 1; esperado = NSEvent.mouseLocation; alEmpezar?() }
                pintar()
            }
            return
        }
        if !pausada, Frenos.movioElMouse(esperado: esperado, real: NSEvent.mouseLocation) { pausar() }
        if let d = desde, Date().timeIntervalSince(d) > Frenos.topeCursor { detener(); return }
        if tics % 10 == 0 { pintar() }
    }

    func siguientePaso() {
        paso = min(pasos, paso + 1)
        esperado = NSEvent.mouseLocation
        pintar()
    }

    func pausar() {
        pausada = true
        seguir.isHidden = false
        pintar()
    }

    func reanudar() {
        pausada = false
        seguir.isHidden = true
        esperado = NSEvent.mouseLocation
        pintar()
    }

    private func pintar() {
        let seg = desde.map { Int(Date().timeIntervalSince($0)) } ?? 0
        if cuenta > 0 {
            texto.stringValue = "\(agente) va a usar tu mouse · empiezo en \(cuenta)…"
        } else if pausada {
            texto.stringValue = "Pausé: moviste el mouse. ¿Sigo?"
        } else {
            texto.stringValue = Frenos.banda(agente: agente, paso: paso, de: pasos, segundos: seg)
        }
        panel.contentView?.needsDisplay = true
        let ancho = min(640, max(380, texto.intrinsicContentSize.width + 200))
        if abs(panel.frame.width - ancho) > 1 {
            var f = panel.frame
            f.origin.x += (f.width - ancho) / 2
            f.size.width = ancho
            panel.setFrame(f, display: true)
            panel.contentView?.frame = NSRect(origin: .zero, size: f.size)
        }
    }

    /// Parar (el botón, Esc Esc, ⌥ Espacio o el tope de 60 s): se quita todo y te devuelve el mouse.
    func detener() {
        reloj?.invalidate()
        reloj = nil
        panel.orderOut(nil)
        bordes.forEach { $0.orderOut(nil) }
        bordes = []
        alParar?()
        alParar = nil
    }

    /// Para las pruebas: lo que pinta la banda, a un PNG.
    func foto(_ ruta: String) {
        guard let v = panel.contentView, let rep = v.bitmapImageRepForCachingDisplay(in: v.bounds) else { return }
        v.cacheDisplay(in: v.bounds, to: rep)
        try? rep.representation(using: .png, properties: [:])?.write(to: URL(fileURLWithPath: ruta))
    }
}
