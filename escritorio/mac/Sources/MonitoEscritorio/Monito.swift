// El panel del monito, su WKWebView, el atajo, el puente y el paso de clics a la app de abajo. Y lo de sus manos (F1):
// la foto del momento al abrir la barra, el puerto local de las herramientas (solo con un turno del escritorio abierto,
// y sobre la ventana que tenías enfrente), la capa de señalar y el ojito. La tarjeta de permiso y el ojito son parte de
// la burbuja (escritorio/web/src/25_manos.js). El monito se arrastra a cualquier pantalla y recuerda dónde lo dejaste:
// el arrastre es nativo (la app toma el ratón en su nido y mueve la ventana; la burbuja solo se levanta y baja).
import AppKit
import Carbon.HIToolbox
import WebKit

/// Un panel que puede tomar el teclado (para la barra) sin activar la app ni robarle el foco a la de enfrente.
final class PanelMonito: NSPanel {
    /// Mientras suelta el teclado (soltarTeclado), no lo vuelve a tomar: así macOS se lo da a la app de enfrente.
    var sinTeclado = false
    override var canBecomeKey: Bool { !sinTeclado }
    override var canBecomeMain: Bool { false }
    /// AppKit no lo empuja bajo la barra de menú: dónde va lo decide la app (Lugar, Agarre). Antes, al arrastrarlo
    /// hacia arriba el panel se topaba con la barra de menú y el monito se quedaba atrás del ratón (hasta 364 pt).
    override func constrainFrameRect(_ r: NSRect, to s: NSScreen?) -> NSRect { r }
}

/// Lo que la página manda por `window.webkit.messageHandlers.ws`. Un objeto aparte para que WebKit no retenga la app.
final class Mensajero: NSObject, WKScriptMessageHandler {
    weak var dueno: Monito?
    func userContentController(_ c: WKUserContentController, didReceive m: WKScriptMessage) {
        let cuerpo = m.body
        // M-3 · el canal solo se le oye a la página propia, en su marco principal
        let origen = m.frameInfo.request.url, principal = m.frameInfo.isMainFrame
        MainActor.assumeIsolated {
            guard let d = dueno, Navegacion.delCanal(origen, propia: d.paginaPropia, marcoPrincipal: principal) else { return }
            d.mensaje(cuerpo)
        }
    }
}

/// El atajo global ⌥ Espacio (Carbon: RegisterEventHotKey no pide permiso de accesibilidad). El mismo manejador atiende
/// el Esc de emergencia (id 2, FrenosApp.swift), que solo se registra mientras algo está en vuelo.
final class Atajo {
    private var ref: EventHotKeyRef?
    private static var manejador: EventHandlerRef?
    static var alPulsar: (() -> Void)?
    static var alEsc: (() -> Void)?
    /// Soltar ⌥ Espacio (voz: mantenerlo es hablar; Voz.swift).
    static var alSoltar: (() -> Void)?

    /// Un solo manejador para los atajos de la app: reparte por su número (1 = ⌥ Espacio, 2 = Esc).
    static func instalar() {
        guard manejador == nil else { return }
        var tipos = [EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed)),
                     EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyReleased))]
        let cb: EventHandlerUPP = { _, ev, _ in
            var id = EventHotKeyID()
            GetEventParameter(ev, EventParamName(kEventParamDirectObject), EventParamType(typeEventHotKeyID), nil,
                              MemoryLayout<EventHotKeyID>.size, nil, &id)
            let n = id.id
            if GetEventKind(ev) == UInt32(kEventHotKeyReleased) {
                if n == 1 { DispatchQueue.main.async { MainActor.assumeIsolated { Atajo.alSoltar?() } } }
                return noErr
            }
            DispatchQueue.main.async { MainActor.assumeIsolated { if n == 2 { Atajo.alEsc?() } else { Atajo.alPulsar?() } } }
            return noErr
        }
        InstallEventHandler(GetApplicationEventTarget(), cb, 2, &tipos, nil, &manejador)
    }

    func registrar(_ alPulsar: @escaping () -> Void) -> Bool {
        Atajo.alPulsar = alPulsar
        Atajo.instalar()
        let id = EventHotKeyID(signature: OSType(0x5753_4D4F), id: 1)    // «WSMO»
        let r = RegisterEventHotKey(UInt32(kVK_Space), UInt32(optionKey), id, GetApplicationEventTarget(), 0, &ref)
        return r == noErr
    }
}

@MainActor
final class Monito: NSObject, NSApplicationDelegate, WKNavigationDelegate, NSWindowDelegate, NSMenuDelegate {
    let op: Opciones
    var panel: PanelMonito!
    var web: WKWebView!
    let mensajero = Mensajero()
    let atajo = Atajo()
    var menu: NSStatusItem?
    /// «Dejarlo ver mi pantalla (foto)…» (su palomita dice si ya puede).
    var menuVer: NSMenuItem?
    var conPunto = false
    var senal: DispatchSourceSignal?

    // el puente (escritorio/puente.py)
    var proc: Process?
    var entrada: FileHandle?
    var resto = Data()
    var reinicios = 0
    var cerrando = false

    // lo que dijo la página
    var listo = false
    var pendientes: [String] = []
    var zonas: [NSRect] = []
    var barraAbierta = false
    /// El renglón «Llamar / Guardar a tu Compañero» del menú de arriba, y lo que decía cuando abriste el menú.
    var menuLlama: NSMenuItem?
    var menuGuarda = false
    /// Pruebas en vivo (--fantasma con --guion): la burbuja nunca toma el teclado de quien está usando la Mac.
    var sinTomarTeclado: Bool { op.fantasma && !op.guion.isEmpty }
    var ultimoRaton = NSPoint(x: -1, y: -1)
    var reloj: Timer?
    var probado = false
    var bitacora: FileHandle?

    // las manos (F1)
    var manos: Manos!
    /// A0: la seguridad para actuar (Actuar.swift): el portero, la tarjeta de OK, los frenos y lo que guarda.
    var actuar: Actuar!
    var capa: Capa!
    var servidor: ServidorManos?
    var manosListas = false
    /// El vuelo de señalar en curso: su número, su reloj de guardia y cómo terminarlo (el monito SIEMPRE regresa).
    var vueloN = 0
    var guardia: Timer?
    var aterrizar: ((FinVuelo) -> Void)?
    var manosPendientes: [String] = []
    /// La foto del momento, tomada al abrir la barra (ANTES de mostrarla): viaja con el siguiente «mandar». Con ella,
    /// la ventana que tenías enfrente (por número): la que miran las manos durante el turno.
    var fotoBarra: (foto: FotoDelMomento, enfrente: Enfrente?, cuando: Date)?
    /// El candado: el turno del escritorio que está abierto (lo abre y lo cierra el puente).
    var turno: TurnoAbierto?
    var ojoDesde: Date?
    var ojos = 0

    /// La ventana del último turno (si contestas una pregunta desde la burbuja, sin volver a llamar al monito).
    var ultimaVentana: Enfrente?
    /// El panelito que se lleva el teclado al cerrar la barra (soltarTeclado).
    var relevo: PanelMonito?
    /// Los íconos de las apps para el chip (por bundle).

    // dónde vive (arrastrarlo)
    var lado = Lado(h: "der", v: "abajo")
    /// El panel donde va (lo que se ve): la ventana es este marco, salvo mientras se arrastra o se acomoda junto al
    /// borde de otra pantalla (Agarre.ventana: la ventana se queda en una pantalla y el contenido se recorre).
    var marco = CGRect.zero
    /// Las pantallas, leídas una vez (al arrancar y cuando cambian), no en cada movimiento del ratón.
    var pantallas = Pantallas()
    /// Un toque en el nido: dónde apretaste, dónde estaba el panel y si ya es arrastre (pasó el umbral).
    var toque: (raton0: NSPoint, panel0: NSPoint, arrastra: Bool)?
    /// El resorte de acomodarlo al soltarlo (o al llevarlo a su esquina) y lo que sigue al llegar.
    var acomodo: (desde: CGPoint, hasta: CGPoint, pantalla: Int, t0: CFTimeInterval, luego: () -> Void)?
    var enlace: CADisplayLink?
    /// La mudanza de lado: su número (una nueva cancela la de antes), lo que queda y la foto del nido que la tapa.
    var mudanza: (n: Int, s: Agarre.Soltado, fantasma: NSPanel?)?
    var mudanzas = 0
    var monitores: [Any] = []
    var ultimoRatonJS: CFTimeInterval = 0
    var manoAbierta = false

    // pruebas del movimiento (--medir)
    var medicion: Medicion?

    /// E1 · entregas en la burbuja (Entregas.swift): miniaturas, Vista rápida, arrastrar, la tarjeta de encargo.
    var entregas: Entregas!
    /// Ronda 2 · la bandeja de fichas pegada al monito (Bandeja.swift): lo que espera tu clic.
    var bandeja: BandejaApp!
    /// El último clic de una PERSONA en el panel del monito (para lo que la burbuja le pide a la bandeja: ficha_tocar).
    var ultimoClic: ClicReal? = nil
    /// M-3 · la única página que cargan la burbuja y la ventana del chat grande: el archivo monito.html de la app.
    var paginaPropia: URL { URL(fileURLWithPath: op.html) }

    /// M-3 · ¿lo que pide la página (un botón de ficha, «Abrir» de un enlace) viene de un clic de una PERSONA, hace un
    /// instante, en ESE panel y sobre ESE botón (`r`: su marco en la página)? Si vale, el clic se gasta.
    func clicDePersona(_ d: [String: Any]) -> Bool {
        let marco = ClicFicha.marco(d["r"]), ahora = Date()
        if entregas?.origen != nil, let v = entregas?.ventana {
            var c = v.ultimoClic
            let ok = ClicFicha.gastar(&c, en: marco, ahora: ahora)
            v.ultimoClic = c
            return ok
        }
        return ClicFicha.gastar(&ultimoClic, en: marco, ahora: ahora)
    }
    /// La voz (Voz.swift): dictar en la caja, mantener ⌥ Espacio para hablar y «Léeme las respuestas».
    var voz: Voz!

    static let ancho: CGFloat = 470
    static let alto: CGFloat = 680

    init(opciones: Opciones) {
        op = opciones
        super.init()
        mensajero.dueno = self
    }

    /// <estado>/escritorio (de abrir.py); sin él, el de siempre de Workspace.
    var carpetaEstado: String {
        op.estado.isEmpty ? (NSHomeDirectory() as NSString).appendingPathComponent(".claude/workspace/escritorio") : op.estado
    }

    // MARK: arrancar
    func applicationDidFinishLaunching(_ n: Notification) {
        armarPanel()
        armarManos()
        voz = Voz(monito: self)
        armarMenu()
        entregas = Entregas(monito: self)
        entregas.arrancar()
        // un toque abre y cierra la barra; mantenerlo es hablar (VozLogica.Pulsacion)
        Atajo.alSoltar = { [weak self] in self?.voz.atajoSube() }
        if !op.sinAtajo && !atajo.registrar({ [weak self] in self?.voz.atajoBaja() }) {
            FileHandle.standardError.write("No pude registrar ⌥ Espacio (¿otra app ya lo usa?). Llama al monito con un clic.\n".data(using: .utf8)!)
        }
        signal(SIGTERM, SIG_IGN)
        let s = DispatchSource.makeSignalSource(signal: SIGTERM, queue: .main)
        s.setEventHandler { NSApp.terminate(nil) }
        s.resume()
        senal = s
        NotificationCenter.default.addObserver(self, selector: #selector(cambiaronPantallas), name: NSApplication.didChangeScreenParametersNotification, object: nil)
        armarArrastre()
        reloj = Timer.scheduledTimer(withTimeInterval: 1.0 / 30.0, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.mirarRaton() }
        }
        if !op.foto.isEmpty {
            var n = 0
            Timer.scheduledTimer(withTimeInterval: 2.5, repeats: true) { [weak self] t in
                MainActor.assumeIsolated {
                    guard let self = self, n < 16 else { t.invalidate(); return }
                    self.fotografiar(String(format: "%@_%02d.png", self.op.foto, n))
                    n += 1
                }
            }
        }
        if !op.medir.isEmpty { medicion = Medicion(monito: self, archivo: op.medir) }
        // el monito nunca toma el teclado al abrir (si lo lanzaron desde una terminal, macOS lo activa: se suelta)
        DispatchQueue.main.async { [weak self] in
            if NSApp.isActive { NSApp.deactivate() }
            if let self = self, self.panel.isKeyWindow, !self.barraAbierta { self.soltarTeclado() }
        }
    }

    /// Lo que pinta el WKWebView, a un PNG (con su transparencia).
    func fotografiar(_ ruta: String) {
        web.takeSnapshot(with: nil) { img, _ in
            guard let img = img, let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
                  let png = rep.representation(using: .png, properties: [:]) else { return }
            try? png.write(to: URL(fileURLWithPath: ruta))
        }
    }

    func applicationWillTerminate(_ n: Notification) {
        cerrando = true
        voz?.cancelar()                                   // el micrófono, apagado
        capa?.cortar()
        servidor?.parar()
        ServidorManos.borrar(en: carpetaEstado)
        cerrarTurno(nil)
        let pid = (carpetaEstado as NSString).appendingPathComponent("app.pid")
        if (try? String(contentsOfFile: pid, encoding: .utf8))?.trimmingCharacters(in: .whitespacesAndNewlines) == String(getpid()) {
            unlink(pid)
        }
        try? entrada?.close()
        proc?.terminate()
    }

    // MARK: dónde vive: su lugar en la pantalla (lugar.json, por arreglo de pantallas)
    var tamPanel: CGSize { entregas?.tamPanel ?? CGSize(width: Monito.ancho, height: Monito.alto) }

    func idPantalla(_ s: NSScreen) -> UInt32 { (s.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value ?? 0 }
    var firmaPantallas: String { Lugar.firma(NSScreen.screens.map { idPantalla($0) }) }
    var rutaLugar: String { (carpetaEstado as NSString).appendingPathComponent("lugar.json") }

    func leerLugares() -> [String: [String: Any]] {
        guard let d = FileManager.default.contents(atPath: rutaLugar),
              let o = try? JSONSerialization.jsonObject(with: d) as? [String: [String: Any]] else { return [:] }
        return o
    }

    func guardarLugar(_ nido: CGRect) {
        guard let i = Lugar.pantalla(de: nido, frames: NSScreen.screens.map { $0.frame }) else { return }
        let s = NSScreen.screens[i]
        let f = Lugar.fraccion(nido, visible: s.visibleFrame)
        var todos = leerLugares()
        todos[firmaPantallas] = ["pantalla": Int(idPantalla(s)), "x": Double(f.x), "y": Double(f.y)]
        if let d = try? JSONSerialization.data(withJSONObject: todos, options: [.sortedKeys]) {
            try? FileManager.default.createDirectory(atPath: carpetaEstado, withIntermediateDirectories: true, attributes: nil)
            FileManager.default.createFile(atPath: rutaLugar, contents: d, attributes: [.posixPermissions: 0o600])
        }
    }

    /// El nido donde lo dejaste en este arreglo de pantallas; si nunca, donde vive de fábrica.
    func nidoGuardado() -> CGRect {
        let pantallas = NSScreen.screens
        if let g = leerLugares()[firmaPantallas], let id = (g["pantalla"] as? NSNumber)?.uint32Value,
           let s = pantallas.first(where: { idPantalla($0) == id }),
           let x = (g["x"] as? NSNumber)?.doubleValue, let y = (g["y"] as? NSNumber)?.doubleValue {
            return Lugar.desdeFraccion(CGPoint(x: x, y: y), visible: s.visibleFrame)
        }
        let vf = (NSScreen.main ?? pantallas.first)?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        return Lugar.deFabrica(visible: vf, izquierda: op.esquina == "izquierda")
    }

    /// El nido de ahora (en AppKit), según el panel (donde va, aunque la ventana se esté recorriendo) y el lado.
    var nidoActual: CGRect { Lugar.nido(enPanel: marco, lado: lado) }

    /// Dónde está la página en la pantalla (AppKit): la ventana más lo que se recorrió el WKWebView dentro.
    var marcoWeb: CGRect {
        CGRect(x: panel.frame.minX + web.frame.minX, y: panel.frame.minY + web.frame.minY, width: web.frame.width, height: web.frame.height)
    }

    /// Pone el nido en `nido` (dentro de su pantalla) y el panel del lado donde hay espacio. `animar`: llega con su
    /// resorte y, si cambia de lado, la burbuja se muda con el monito quieto (irA); si no, de una vez.
    func ponerEn(_ nido: CGRect, animar: Bool) {
        if animar { irA(nido); return }
        guard let s = Agarre.soltar(nido: nido, frames: pantallas.frames, visibles: pantallas.visibles, tam: tamPanel) else { return }
        cancelarMovimiento()
        let cambiaLado = s.lado != lado
        lado = s.lado
        if cambiaLado || !listo { js("WSM.lado('\(s.lado.h)','\(s.lado.v)')") }
        marco = s.panel
        colocar(s.panel)
    }

    /// Cambió una pantalla (se conectó, se desconectó o cambió de resolución): donde lo dejaste en ESTE arreglo, o
    /// dentro de la pantalla donde estaba (o de la más cercana): nunca perdido fuera de la vista.
    @objc func cambiaronPantallas() {
        pantallas = Pantallas.leer()
        if toque != nil { return }
        let g = leerLugares()[firmaPantallas] != nil
        ponerEn(g ? nidoGuardado() : nidoActual, animar: false)
    }

    func armarPanel() {
        pantallas = Pantallas.leer()
        let inicial = Lugar.panel(nido: nidoGuardado(), lado: lado, tam: tamPanel,
                                  visible: (NSScreen.main ?? NSScreen.screens.first)?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900))
        marco = inicial
        panel = PanelMonito(contentRect: inicial, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.level = .floating
        panel.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
        panel.hidesOnDeactivate = false
        panel.isMovable = false
        panel.ignoresMouseEvents = true
        panel.acceptsMouseMovedEvents = true
        if op.fantasma { panel.alphaValue = 0.02 }
        panel.delegate = self

        let conf = WKWebViewConfiguration()
        conf.userContentController.add(mensajero, name: "ws")
        // que WebKit no frene la burbuja cuando el panel no tiene el foco (sus animaciones y su texto en vivo)
        conf.preferences.inactiveSchedulingPolicy = .none
        if !op.medir.isEmpty { conf.userContentController.addUserScript(WKUserScript(source: Medicion.js, injectionTime: .atDocumentEnd, forMainFrameOnly: true)) }
        web = WKWebView(frame: panel.contentLayoutRect, configuration: conf)
        web.setValue(false, forKey: "drawsBackground")      // transparente: se ve la app de abajo
        web.navigationDelegate = self
        // el WKWebView dentro de una caja: mientras lo arrastras junto al borde de otra pantalla, la ventana se queda en
        // una y el contenido se recorre (Agarre.ventana); su tamaño solo cambia con el del panel (colocar)
        let caja = NSView(frame: panel.contentLayoutRect)
        caja.addSubview(web)
        panel.contentView = caja
        let url = URL(fileURLWithPath: op.html)
        web.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
        panel.orderFrontRegardless()
        ponerEn(nidoGuardado(), animar: false)
    }

    func armarMenu() {
        // las pruebas del movimiento y las de --fantasma (que nadie las vea) no ponen su carita en la barra
        if !op.medir.isEmpty || op.fantasma { return }
        let it = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        if let b = it.button {
            b.image = NSImage(systemSymbolName: "face.smiling", accessibilityDescription: "Workspace Compañero")
            b.toolTip = "Workspace Compañero · ⌥ Espacio"
        }
        let m = NSMenu()
        let llamar = NSMenuItem(title: Compa.renglonMenu(abierto: false), action: #selector(menuLlamar), keyEquivalent: "")
        llamar.target = self
        llamar.toolTip = "Abierto, lo guarda con todo (su burbuja y su ventana grande). Guardado, lo trae como lo dejaste."
        m.addItem(llamar)
        menuLlama = llamar
        let casa = NSMenuItem(title: "Traerlo a su esquina", action: #selector(menuEsquina), keyEquivalent: "")
        casa.target = self
        m.addItem(casa)
        m.addItem(.separator())
        let decir = NSMenuItem(title: "Decirle a mi agente qué tengo enfrente", action: #selector(menuDecir(_:)), keyEquivalent: "")
        decir.target = self
        decir.state = decirEnfrente ? .on : .off
        decir.toolTip = "La app y la ventana que tienes enfrente viajan con tu mensaje (no tu pantalla)."
        m.addItem(decir)
        // Grabación de pantalla: opcional, solo si tú la prendes (con su aviso honesto)
        let ver = NSMenuItem(title: "Dejarlo ver mi pantalla (foto)…", action: #selector(menuVerPantalla(_:)), keyEquivalent: "")
        ver.target = self
        ver.toolTip = "Otro permiso de la Mac (Grabación de pantalla). macOS lo vuelve a confirmar cada mes y pide reabrir Compañero."
        m.addItem(ver)
        menuVer = ver
        actuar?.agregarAlMenu(m)                          // A0: confianzas de hoy, vetados, «Puede tomar mi mouse»
        voz?.agregarAlMenu(m)                             // V3-b: «Léeme las respuestas» (apagado de fábrica)
        m.addItem(.separator())
        // qué app es (para nunca probar una vieja sin saberlo) y si su firma conserva los permisos
        let firma = NSMenuItem(title: Monito.lineaFirma(), action: nil, keyEquivalent: "")
        firma.isEnabled = false
        firma.toolTip = EstaApp.estable ? "macOS reconoce esta app por su firma: los permisos se quedan aunque se actualice."
            : "Firmada ad hoc: cada compilación es otra app para macOS y te vuelve a pedir los permisos."
        m.addItem(firma)
        m.delegate = self
        m.addItem(.separator())
        let salir = NSMenuItem(title: "Cerrar Workspace Compañero", action: #selector(menuSalir), keyEquivalent: "")
        salir.target = self
        m.addItem(salir)
        it.menu = m
        menu = it
    }

    /// «Llamar / Guardar a tu Compañero» del menú de arriba: lo mismo que ⌥ Espacio. Hace lo que su renglón decía al
    /// abrir el menú (abrir el menú le quita el teclado a la barra chica, que se cierra sola: entonces no hay nada
    /// que guardar y no se vuelve a abrir por error).
    @objc func menuLlamar() {
        if menuGuarda && !abierto { return }
        if !menuGuarda && abierto { return }
        gesto(.menu)
    }

    /// [Contestar] en la ficha de una pregunta: su burbuja, con ese agente y la barra lista para escribir.
    func contestarPregunta(_ agente: String) {
        js("try{var o=\(Permisos.json(["a": agente]));WSM.elegir(o.a,true);WSM.s.cerrado=false;WSM.pintarGlobo()}catch(e){}")
        if !barraAbierta { abrirBarra() }
    }

    /// El puntito en su carita de la barra de menú: hay fichas dobladas esperándote (P3-b).
    func puntoEnBarra(_ hay: Bool) {
        guard let b = menu?.button, hay != conPunto else { return }
        conPunto = hay
        b.imagePosition = hay ? .imageLeft : .imageOnly
        b.attributedTitle = hay ? NSAttributedString(string: "●", attributes: [
            .foregroundColor: NSColor(red: 0.94, green: 0.74, blue: 0.38, alpha: 1), .font: NSFont.systemFont(ofSize: 7), .baselineOffset: 6])
            : NSAttributedString(string: "")
        b.toolTip = hay ? "Workspace Compañero · tienes algo esperándote (un clic en el monito lo enseña)" : "Workspace Compañero · ⌥ Espacio"
    }

    /// Lo que la burbuja ocupa en la pantalla ahora (su globo, su barra, su panel grande; sin el nido), o nil: la bandeja
    /// de fichas no la tapa.
    func burbujaEnPantalla() -> CGRect? {
        guard let panel = panel, let web = web else { return nil }
        let f = panel.frame, nido = nidoActual.insetBy(dx: -24, dy: -24)
        var u: CGRect? = nil
        for z in zonas {
            let r = CGRect(x: f.minX + web.frame.minX + z.minX, y: f.minY + web.frame.maxY - z.minY - z.height, width: z.width, height: z.height)
            if nido.contains(r) || r.height < 40 { continue }            // el nido, y lo chico pegado a él (su globito)
            u = u?.union(r) ?? r
        }
        return u
    }

    /// «Firma: estable · versión 3» (o «ad hoc»): en el menú y en la bitácora.
    static func lineaFirma() -> String {
        "Firma: \(EstaApp.firmaEnSimple) · versión \(Contrato.version) · \(EstaApp.id)"
    }

    /// «Dejarlo ver mi pantalla (foto)…»: la tarjeta de Grabación de pantalla, solo porque tú la pediste.
    @objc func menuVerPantalla(_ item: NSMenuItem) {
        if Permiso.grabacion.concedido { return }
        manos.permisos.pedir(.pantalla, tuyo: true)
    }

    func menuWillOpen(_ menu: NSMenu) {
        menuGuarda = abierto
        menuLlama?.title = Compa.renglonMenu(abierto: menuGuarda)
        menuVer?.state = Permiso.grabacion.concedido ? .on : .off
        menuVer?.title = Permiso.grabacion.concedido ? "Puede ver mi pantalla (foto)" : "Dejarlo ver mi pantalla (foto)…"
    }
    @objc func menuSalir() { NSApp.terminate(nil) }

    /// «Decirle a mi agente qué tengo enfrente» (prendido de fábrica): la app y su ventana viajan con tu mensaje, sin
    /// pintarse en la barra. Apagado, no viaja nada de tu pantalla. Se recuerda en esta Mac.
    var decirEnfrente: Bool {
        get { (UserDefaults.standard.object(forKey: "decirEnfrente") as? Bool) ?? true }
        set { UserDefaults.standard.set(newValue, forKey: "decirEnfrente") }
    }

    @objc func menuDecir(_ item: NSMenuItem) {
        decirEnfrente.toggle()
        item.state = decirEnfrente ? .on : .off
        if !decirEnfrente { js("WSM.contexto(null)") } else { avisarFoto() }
    }
    @objc func menuEsquina() {
        let vf = (NSScreen.main ?? NSScreen.screens.first)?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let n = Lugar.deFabrica(visible: vf)
        irA(n)
        guardarLugar(n)
    }

    /// Un clic fuera (en otra app) le quita el teclado al monito: la barra se cierra igual que con Esc (si fue el
    /// relevo de soltarTeclado, ya estaba cerrándose).
    func windowDidResignKey(_ n: Notification) {
        guard (n.object as? NSWindow) === panel, barraAbierta, !panel.sinTeclado else { return }
        medicion?.marca("clic fuera: se cierra la barra")
        js("WSM.barra(false)")
    }

    // MARK: la página
    func webView(_ w: WKWebView, didFinish n: WKNavigation!) {}

    /// M-3 · la burbuja solo carga SU página: nada de navegar a otra (un enlace soltado encima, un `location = …`).
    func webView(_ w: WKWebView, decidePolicyFor a: WKNavigationAction, decisionHandler: @escaping @MainActor (WKNavigationActionPolicy) -> Void) {
        let ok = Navegacion.permitida(a.request.url, propia: paginaPropia, marcoPrincipal: a.targetFrame?.isMainFrame ?? false)
        if !ok { anotar("✗ navegación negada (burbuja): " + String((a.request.url?.scheme ?? "?").prefix(20))) }
        decisionHandler(ok ? .allow : .cancel)
    }

    func js(_ codigo: String) {
        web.evaluateJavaScript(codigo, completionHandler: nil)
    }

    /// Un evento del puente (una línea de JSON) → WSM.recibir("…"), como texto: así nada se interpreta de más.
    /// El del turno («t»: «turno») es para la app: abre y cierra el candado de las manos.
    func alMonito(_ linea: String) {
        if linea.contains("\"turno\""), let d = linea.data(using: .utf8),
           let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any], (o["t"] as? String) == "turno" {
            if (o["abierto"] as? Bool) == true, let id = o["id"] as? String { abrirTurno(id, agente: (o["agente"] as? String) ?? "") }
            else { cerrarTurno(o["id"] as? String) }
            return
        }
        // ronda 2 · P5-a: los permisos de su motor (de todos los agentes) son fichas de la app, no de la burbuja
        if linea.contains("\"fichas\""), let d = linea.data(using: .utf8),
           let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any], (o["t"] as? String) == "fichas" {
            anotar("← fichas " + ((o["agente"] as? String) ?? ""))
            bandeja?.deMotor(o)
            return
        }
        let filtrada: String?? = entregas.map { $0.filtrar(linea) }      // E1: lo de entregas que es para la app
        guard let linea = filtrada ?? linea else { return }
        guard listo else { pendientes.append(linea); return }
        anotar("← " + linea)
        voz?.observar(linea)                              // «Léeme las respuestas»: solo la respuesta final
        if linea.contains("\"agentes\""), let d = linea.data(using: .utf8),
           let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any], (o["t"] as? String) == "agentes" {
            let l = ((o["agentes"] as? [[String: Any]]) ?? []).compactMap { a -> (id: String, nombre: String)? in
                guard let id = a["id"] as? String else { return nil }
                return (id, (a["n"] as? String) ?? id)
            }
            bandeja?.agentesLlegaron(((o["agentes"] as? [[String: Any]]) ?? []).compactMap { a in
                guard let id = a["id"] as? String else { return nil }
                return (id, (a["n"] as? String) ?? id, (a["c"] as? String) ?? "#8b5cf6")
            })
            actuar?.agentesLlegaron(l)                    // para su menú y el interruptor de la burbuja
            Entregables.usar(((o["entregables"] as? [Any]) ?? []).compactMap { $0 as? String })     // T1-b: las limpia el portero
        }
        // una pregunta del agente también es una ficha (sin su texto: se contesta en su burbuja)
        if linea.contains("\"pregunta\""), let d = linea.data(using: .utf8),
           let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any], (o["t"] as? String) == "pregunta",
           let a = o["agente"] as? String {
            bandeja?.pregunta(agente: a, hay: o["id"] is String && (o["en_terminal"] as? Bool) != true)
        }
        if !probado && !op.probar.isEmpty && (linea.contains("\"t\": \"agentes\"") || linea.contains("\"t\":\"agentes\"")) {
            probado = true
            let a = (try? JSONSerialization.data(withJSONObject: [op.agente, op.probar])).flatMap { String(data: $0, encoding: .utf8) } ?? "[]"
            DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in self?.js("WSM.probar.apply(null, \(a))") }
        }
        guard let d = try? JSONSerialization.data(withJSONObject: [linea]),
              let s = String(data: d, encoding: .utf8) else { return }
        js("WSM.recibir(\(s.dropFirst().dropLast()))")
    }

    func mensaje(_ cuerpo: Any) {
        guard let d = cuerpo as? [String: Any], let k = d["op"] as? String else { return }
        if k.hasPrefix("manos_") { anotar("⇠ " + k) }
        switch k {
        case "listo":
            listo = true
            js("WSM.lado('\(lado.h)','\(lado.v)')")
            js(Contrato.saludo(guion: !op.guion.isEmpty))     // la app se presenta: su versión y lo que sabe hacer
            if proc == nil { arrancarPuente() }
            let p = pendientes
            pendientes = []
            p.forEach { alMonito($0) }
            medicion?.listo()
            if !op.guion.isEmpty { DispatchQueue.main.asyncAfter(deadline: .now() + 1.5) { [weak self] in self?.correrGuion() } }
        case "guion_log":
            guard !op.guion.isEmpty else { return }               // solo pruebas (--guion)
            anotar("guion: " + String(((d["texto"] as? String) ?? "").prefix(2000)))
        case "guion_foto":
            // solo pruebas (--guion y --foto): lo que pinta la burbuja en ese momento, a <foto>_<nombre>.png
            guard !op.guion.isEmpty, !op.foto.isEmpty else { return }
            let n = ((d["nombre"] as? String) ?? "x").filter { $0.isLetter || $0.isNumber || $0 == "_" || $0 == "-" }.prefix(40)
            fotografiar(op.foto + "_" + n + ".png")
        case "zonas":
            let zs = (d["zonas"] as? [[Any]]) ?? []
            zonas = zs.compactMap { z in
                let n = z.compactMap { ($0 as? NSNumber)?.doubleValue }
                return n.count == 4 ? NSRect(x: n[0], y: n[1], width: n[2], height: n[3]) : nil
            }
            mirarRaton()
        case "manos_listo":
            manosListas = true
            let p = manosPendientes
            manosPendientes = []
            p.forEach { js($0) }
            manos.permisos.repintar()                         // si la burbuja se recargó con una tarjeta a la vista
            if !op.demo.isEmpty {
                let tipo = op.demo
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.6) { [weak self] in
                    if DemoActuar.tipos.contains(tipo) { self?.demoActuar(tipo) } else { self?.manos.demo(tipo) }
                }
            }
        case "manos_permiso":
            manos.permisos.accion((d["accion"] as? String) ?? "", permiso: (d["permiso"] as? String) ?? "")
        case "volver":
            // la burbuja: Esc, un clic en su nido vacío o su reloj de guardia: el monito regresa ya
            if let a = aterrizar { a(.socio) } else { js("WSMManos.volver(true)") }
        case "guion_gesto":
            // solo pruebas (--guion): lo que harías tú (⌥ Espacio, un clic en el Compañero, el menú, cerrar la ventana),
            // por el MISMO camino que la tecla y el ratón de verdad, sin tocar los de nadie
            guard !op.guion.isEmpty else { return }
            switch (d["gesto"] as? String) ?? "" {
            case "atajo": voz?.atajoBaja(); voz?.atajoSube()
            case "clic": clicEnNido()
            case "menu": menuGuarda = abierto; menuLlamar()
            case "cerrar": gesto(.cerrarVentana)
            default: break
            }
        case "guion_estado":
            // solo pruebas (--guion): lo que hay de VERDAD a la vista (las ventanas de AppKit, no lo que cree la página)
            guard !op.guion.isEmpty else { return }
            anotar("guion: estado «\(String(((d["paso"] as? String) ?? "").prefix(60)))» abierto=\(abierto) barra=\(barraAbierta) "
                   + (entregas?.estadoGrande ?? "") + " fichas=\(bandeja?.estado.plegada == false ? "desplegadas" : "dobladas") teclado=\(panel.isKeyWindow) activa=\(NSApp.isActive)")
        case "guardar":
            // la burbuja ya se guardó sola (Esc o su «×»): que se guarde TODO lo demás (la ventana grande, las fichas)
            gesto(.esc)
        case "llamar":
            // un clic en el Compañero (E2-a): abierto, lo guarda todo. Guardado: con fichas pendientes y dobladas, las
            // ENSEÑA; si no, lo trae como lo dejaste. Nunca para nada: parar es el botón rojo «Parar» y Esc Esc.
            if !abierto, bandeja?.clicEnMonito() == true { return }
            gesto(.clicMonito)
        case "arrastrar":
            // el arrastre de antes (lo detectaba la burbuja): ahora lo hace la app desde que aprietas; si la burbuja
            // lo pide (un toque en el filo del nido que la app no tomó), que no se quede «arrastrando»
            js("WSM.arrastre(false)")
        case "mudanza":
            mudanzaSigue((d["fase"] as? NSNumber)?.intValue ?? 0, n: (d["n"] as? NSNumber)?.intValue ?? -1)
        case "medir":
            medicion?.dePagina(d)
        case "mandar":
            // contrato con el puente: la foto del momento (app y bundle siempre; ventana, selección y URL con
            // Accesibilidad). Si la burbuja ya trae «contexto» (o lo quitó el socio: sin_contexto), se respeta.
            entregas?.observar(d)
            let m = Contrato.mandar(d, foto: fotoBarra?.foto.paraMandar(),
                                    edad: fotoBarra.map { Date().timeIntervalSince($0.cuando) } ?? -1, decir: decirEnfrente)
            mandarAlPuente(m)
        case "barra":
            let abierta = (d["abierta"] as? Bool) ?? false
            barraAbierta = abierta
            if abierta {
                if fotoBarra == nil || Date().timeIntervalSince(fotoBarra!.cuando) > 2 { tomarFoto() }
                if actuar?.prendido == true { jsManos("WSMActuar.interruptor()") }      // el interruptor, del agente elegido
                if !sinTomarTeclado {
                    panel.makeKeyAndOrderFront(nil)
                    panel.makeFirstResponder(web)
                }
            } else {
                soltarTeclado()
            }
            medicion?.marca(abierta ? "barra abierta" : "barra cerrada")
        case _ where k.hasPrefix("ficha_"):
            // la burbuja (el chat grande) pide un botón de una ficha: solo vale con un clic de una persona hace un instante
            // (junto5: si lo pide la ventana del chat grande, vale el clic de una persona EN esa ventana)
            bandeja?.deLaBurbuja(d, reciente: clicDePersona(d))
        case _ where k.hasPrefix("voz_"):
            voz?.deLaBurbuja(d)                           // la voz no va al puente: la atiende la app (Voz.swift)
        case _ where k.hasPrefix("actuar_"):
            actuar?.deLaBurbuja(d)                        // lo de actuar no va al puente: lo atiende la app
        default:
            if entregas?.atender(k, d) == true { return }     // E1: lo que hace la app (Vista rápida, copiar, arrastrar…)
            mandarAlPuente(d)
        }
    }

    /// Devuelve el teclado a la app de enfrente SIN esconder al monito.
    /// Antes: orderOut + orderFrontRegardless del panel. Medido (--medir): la ventana salía de la pantalla ~17 ms, WebKit
    /// daba la página por escondida (visibilitychange hidden → visible) y se caía un cuadro de ~50 ms: el «se glitchea un
    /// segundo» al dar Esc. Pedirle a la app de enfrente que se active no sirve (macOS no deja a una app de fondo).
    /// Ahora, un relevo: un panelito de 1×1 invisible toma el teclado (es nuestro: el monito deja de tenerlo sin moverse)
    /// y se va él solo; al irse, macOS le devuelve el teclado a la app de enfrente. El monito nunca sale de la pantalla.
    func soltarTeclado() {
        guard panel.isKeyWindow else { return }
        if (ProcessInfo.processInfo.environment["WORKSPACE_MONITO_SOLTAR"] ?? "") == "orden" { reordenar(); return }
        let r = relevo ?? {
            let p = PanelMonito(contentRect: NSRect(x: panel.frame.minX, y: panel.frame.minY, width: 1, height: 1),
                                styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
            p.isOpaque = false
            p.backgroundColor = .clear
            p.hasShadow = false
            p.level = .floating
            p.ignoresMouseEvents = true
            p.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
            p.sharingType = .none
            relevo = p
            return p
        }()
        r.setFrameOrigin(NSPoint(x: panel.frame.minX, y: panel.frame.minY))
        r.makeKeyAndOrderFront(nil)
        panel.sinTeclado = true
        medicion?.marca("soltar: relevo con el teclado")
        DispatchQueue.main.async { [weak self] in
            r.orderOut(nil)
            self?.panel.sinTeclado = false
            self?.medicion?.marca("soltar: relevo fuera")
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.15) { [weak self] in
                guard let self = self, !self.barraAbierta, self.panel.isKeyWindow else { return }
                self.medicion?.marca("soltar: el relevo no bastó; se reordena")
                self.reordenar()
            }
        }
    }

    private func reordenar() {
        panel.orderOut(nil)
        panel.orderFrontRegardless()
        medicion?.marca("soltar: reordenada")
    }

    /// ⌥ Espacio (un toque; mantenerlo es hablar: Voz.atajoBaja). Abierto, lo guarda todo; guardado, lo trae igual.
    func alternarBarra() {
        if actuar?.enVuelo == true { actuar.panico("⌥ Espacio"); return }      // solo mientras algo se está HACIENDO
        if !abierto { _ = bandeja?.clicEnMonito() }                             // al llamarlo: lo pendiente, a la vista
        gesto(.atajo)
    }

    // MARK: guardar y llamar (UN modelo: Compa, LogicaGrande.swift)
    /// El Compañero está abierto: en chico (la burbuja con su barra) o en grande (su ventana).
    var abierto: Bool { Compa.abierto(grandeVisible: entregas?.grandeVisible == true, barraAbierta: barraAbierta) }

    /// TODOS los caminos pasan por aquí: ⌥ Espacio, un clic en el Compañero, el menú de arriba, «─ Minimizar», Esc,
    /// «×», cerrar la ventana, «⤢» y «⤡ Chico». Qué toca lo decide Compa.paso; ningún camino decide por su cuenta.
    func gesto(_ g: Compa.Gesto, ver: [String]? = nil) {
        let grande = entregas?.grandeVisible == true
        switch Compa.paso(g, grandeVisible: grande, barraAbierta: barraAbierta, modo: entregas?.modoGrande ?? "chico") {
        case .guardar:
            guardarTodo(por: g)
        case .abrir("grande"):
            entregas?.abrirGrande(ver: ver)                  // la burbuja chica se calla sola (WSM.fuera)
        case .abrir:
            // en chico: la ventana grande (si estaba) se esconde y queda anotado «chico»; luego la burbuja con su barra
            entregas?.esconderGrande(vuelve: "chico")
            abrirBarra()
        case .nada:
            break
        }
    }

    /// GUARDAR: se esconde TODO lo del Compañero (su ventana grande, su burbuja con su barra, su toque y sus fichas, que
    /// se doblan en su número) y queda solo él en su nido. Se anota cómo estaba para traerlo igual. Lo único que se
    /// queda es lo que te PIDE algo (un permiso, una pregunta): tu agente está esperándote.
    func guardarTodo(por g: Compa.Gesto) {
        let grande = entregas?.grandeVisible == true
        let modo = Compa.modoAlGuardar(grandeVisible: grande, barraAbierta: barraAbierta, modo: entregas?.modoGrande ?? "chico")
        entregas?.esconderGrande(vuelve: modo)
        js("WSM.guardar(true)")
        bandeja?.plegar()
        barraAbierta = false
        anotar("guardado (\(g)) · vuelve en \(modo)")
    }

    /// ⌥ Espacio o un clic: lo que tienes enfrente ANTES de enseñar la barra (su chip), y luego la barra.
    func abrirBarra() {
        tomarFoto()
        if !sinTomarTeclado {
            panel.makeKeyAndOrderFront(nil)
            panel.makeFirstResponder(web)
        }
        js("WSM.contexto(\(contextoParaBurbuja() ?? "null"));WSM.barra(true)")
    }

    // MARK: clics y ojos
    /// Con cada movimiento del ratón (y 30 veces por segundo, por si acaso): si el cursor está sobre el monito o su
    /// burbuja, el panel toma el clic; si no, lo deja pasar. Sobre el nido, la mano abierta (se puede agarrar). Y le
    /// cuenta al monito dónde está el cursor (a lo más 60 veces por segundo), para que lo siga con los ojos.
    func mirarRaton() {
        guard let panel = panel, let web = web else { return }
        let p = PruebaRaton.ahora, f = panel.frame
        // en coordenadas de la página (arriba-izquierda del WKWebView, que se recorre dentro de la ventana al arrastrarlo)
        let x = p.x - (f.minX + web.frame.minX), y = (f.minY + web.frame.maxY) - p.y
        let dentro = toque != nil || zonas.contains { $0.insetBy(dx: -4, dy: -4).contains(NSPoint(x: x, y: y)) }
        if PruebaRaton.punto != nil { panel.ignoresMouseEvents = true }     // pruebas: tu ratón de verdad pasa de largo
        else if panel.ignoresMouseEvents == dentro { panel.ignoresMouseEvents = !dentro }
        if toque == nil {
            let sobre = dentro && enNido(NSPoint(x: p.x - f.minX, y: p.y - f.minY))
            if sobre != manoAbierta {
                manoAbierta = sobre
                if sobre { NSCursor.openHand.set() } else if dentro { NSCursor.arrow.set() }   // fuera: el de la app de abajo
            }
        }
        let ahora = CACurrentMediaTime()
        if listo && ahora - ultimoRatonJS > 0.015 && (abs(p.x - ultimoRaton.x) > 0.5 || abs(p.y - ultimoRaton.y) > 0.5) {
            ultimoRaton = p
            ultimoRatonJS = ahora
            js("WSM.raton(\(Int(x)),\(Int(y)))")
        }
    }

    // MARK: el puente
    func arrancarPuente() {
        let pr = Process()
        pr.executableURL = URL(fileURLWithPath: op.python)
        pr.arguments = ["-u", op.puente]
        pr.currentDirectoryURL = URL(fileURLWithPath: op.raiz)
        var env = ProcessInfo.processInfo.environment
        env["PYTHONIOENCODING"] = "utf-8"
        pr.environment = env
        let ent = Pipe(), sal = Pipe()
        pr.standardInput = ent
        pr.standardOutput = sal
        pr.standardError = FileHandle.standardError
        sal.fileHandleForReading.readabilityHandler = { [weak self] h in
            let datos = h.availableData
            DispatchQueue.main.async { self?.recibir(datos) }
        }
        pr.terminationHandler = { [weak self] _ in
            DispatchQueue.main.async { self?.seCerroElPuente() }
        }
        do {
            try pr.run()
        } catch {
            alMonito("{\"t\":\"aviso\",\"grave\":true,\"duerme\":true,\"texto\":\"No pude arrancar el puente con Workspace (python3).\"}")
            return
        }
        proc = pr
        entrada = ent.fileHandleForWriting
    }

    func recibir(_ datos: Data) {
        if datos.isEmpty { return }
        resto.append(datos)
        while let i = resto.firstIndex(of: 0x0A) {
            let linea = resto.subdata(in: resto.startIndex..<i)
            resto.removeSubrange(resto.startIndex...i)
            if let s = String(data: linea, encoding: .utf8), !s.isEmpty { alMonito(s) }
        }
    }

    func mandarAlPuente(_ d: [String: Any]) {
        guard let h = entrada, JSONSerialization.isValidJSONObject(d),
              var datos = try? JSONSerialization.data(withJSONObject: d) else { return }
        anotar("→ " + (String(data: datos, encoding: .utf8) ?? ""))
        datos.append(0x0A)
        do { try h.write(contentsOf: datos) } catch {}
    }

    /// Pruebas (--guion): el JS del archivo, en la burbuja (aprieta botones como tú; cuenta con op «guion_log»).
    func correrGuion() {
        guard let codigo = try? String(contentsOfFile: op.guion, encoding: .utf8) else { anotar("guion: no pude leer \(op.guion)"); return }
        web.evaluateJavaScript(codigo) { [weak self] _, e in
            if let e = e { MainActor.assumeIsolated { self?.anotar("guion: ✗ \(e.localizedDescription)") } }
        }
    }

    func anotar(_ s: String) {
        if op.registro.isEmpty { return }
        if bitacora == nil {
            FileManager.default.createFile(atPath: op.registro, contents: nil)
            bitacora = FileHandle(forWritingAtPath: op.registro)
        }
        let t = ISO8601DateFormatter().string(from: Date())
        if let d = (t + " " + s + "\n").data(using: .utf8) { bitacora?.seekToEndOfFile(); bitacora?.write(d) }
    }

    func seCerroElPuente() {
        proc = nil
        entrada = nil
        resto = Data()
        cerrarTurno(nil)
        if cerrando { return }
        alMonito("{\"t\":\"aviso\",\"grave\":true,\"duerme\":true,\"texto\":\"Se cerró mi conexión con Workspace. Me reconecto…\"}")
        reinicios += 1
        if reinicios <= 5 {
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) { [weak self] in self?.arrancarPuente() }
        }
    }
}

// MARK: - arrastrarlo (nativo)
/// Las pantallas, leídas una vez: sus marcos, su parte visible, sus números y el alto de la principal (para pasar del
/// ratón de CoreGraphics, arriba-izquierda, a AppKit).
struct Pantallas {
    var frames: [CGRect] = []
    var visibles: [CGRect] = []
    var alto0: CGFloat = 0

    @MainActor static func leer() -> Pantallas {
        let s = NSScreen.screens
        return Pantallas(frames: s.map { $0.frame }, visibles: s.map { $0.visibleFrame }, alto0: s.first?.frame.maxY ?? 0)
    }
}

/// Lo de antes, medido (NOTA_ARRASTRE): la burbuja detectaba el arrastre y se lo decía a la app, que movía la ventana
/// leyendo el ratón 120 veces por segundo. El primer toque después de usar otra app no llegaba (WebKit no acepta el
/// «primer clic» de una ventana sin activar: solo le quitaba el teclado a la app de enfrente), el panel se topaba con la
/// barra de menú, quedaba montado entre dos pantallas (y macOS no lo pinta en ninguna) y, al soltarlo, la burbuja
/// cambiaba de lado antes de que la ventana llegara (el nido brincaba cientos de puntos).
/// Ahora la app toma el ratón en el nido ANTES que WebKit (un monitor local): un clic llama al monito, un arrastre
/// mueve la ventana con cada evento (sin pasar por la página), sin tomar el teclado; al soltarlo se acomoda con su
/// resorte y, si cambia de lado, la burbuja se muda con el monito quieto (una foto del nido lo tapa mientras tanto).
extension Monito {
    func armarArrastre() {
        let local = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDown, .leftMouseDragged, .leftMouseUp, .mouseMoved]) { [weak self] e in
            nonisolated(unsafe) let ev = e                    // llega en el hilo principal (AppKit)
            let mio = MainActor.assumeIsolated { self?.raton(ev) ?? false }
            return mio ? nil : e
        }
        // el ratón sobre otras apps: en cuanto llega al monito, el panel ya toma el clic (antes, hasta 33 ms después)
        let global = NSEvent.addGlobalMonitorForEvents(matching: [.mouseMoved]) { [weak self] _ in
            MainActor.assumeIsolated { self?.mirarRaton() }
        }
        monitores = [local, global].compactMap { $0 }
        let e = panel.displayLink(target: self, selector: #selector(cuadroDelArrastre(_:)))
        e.add(to: .main, forMode: .common)
        e.isPaused = true
        enlace = e
    }

    /// ¿El punto (en la ventana, AppKit) cae en el nido? Su lugar sale de cómo está puesto el panel (Lugar), no de lo
    /// que dijo la página hace un rato: tras cambiar de lado ya es el bueno. Con 3 pt de más en el filo.
    func enNido(_ p: NSPoint) -> Bool {
        let n = nidoActual.offsetBy(dx: -panel.frame.minX, dy: -panel.frame.minY).insetBy(dx: -3, dy: -3)
        return n.contains(p)
    }

    /// El ratón en la pantalla (AppKit) cuando pasó el evento.
    func global(_ e: NSEvent) -> NSPoint {
        if let c = e.cgEvent { return NSPoint(x: c.location.x, y: pantallas.alto0 - c.location.y) }
        return PruebaRaton.ahora
    }

    /// Lo del ratón en el panel. true: era del nido (WebKit no lo ve; así tampoco se lleva el teclado).
    func raton(_ e: NSEvent) -> Bool {
        if e.type == .mouseMoved { mirarRaton(); return false }
        guard e.window === panel else { return false }
        if e.type == .leftMouseDown || e.type == .leftMouseUp, EventoReal.dePersona(e) {
            let p = web.convert(e.locationInWindow, from: nil)
            ultimoClic = ClicReal(cuando: Date(), punto: CGPoint(x: p.x, y: web.isFlipped ? p.y : web.bounds.height - p.y))
        }
        switch e.type {
        case .leftMouseDown:
            guard toque == nil, enNido(e.locationInWindow) else { return false }
            // volando (señalando): un clic en su nido vacío lo trae de regreso, como antes
            if aterrizar != nil || capa?.ocupada == true { mensaje(["op": "volver"]); return true }
            cancelarMovimiento()
            toque = (global(e), marco.origin, false)
            NSCursor.closedHand.set()
            medicion?.arrastre?.marca("toque")
            return true
        case .leftMouseDragged:
            guard var t = toque else { return false }
            let g = global(e)
            if !t.arrastra {
                guard Agarre.esArrastre(desde: t.raton0, ahora: g) else { return true }
                t.arrastra = true
                toque = t
                empezarArrastre()
            }
            mover(Agarre.origen(panel0: t.panel0, raton0: t.raton0, raton: g), raton: g)
            return true
        case .leftMouseUp:
            guard let t = toque else { return false }
            toque = nil
            manoAbierta = false
            if t.arrastra { soltarArrastre() } else { clicEnNido() }
            mirarRaton()
            return true
        default:
            return false
        }
    }

    func empezarArrastre() {
        medicion?.arrastre?.marca("arrastre")
        js("WSM.agarrar ? WSM.agarrar(true) : WSM.arrastre(true)")     // se levanta (la burbuja de antes: se aparta)
        enlace?.isPaused = false                                       // por si se pierde el «soltar» (ver cuadro…)
    }

    /// El panel a `o` (donde va) y la ventana sin montarse entre dos pantallas: la de `raton` (siempre está en una).
    func mover(_ o: CGPoint, raton g: NSPoint) {
        marco.origin = o
        colocar(Agarre.ventana(marco, en: Agarre.pantalla(de: g, frames: pantallas.frames) ?? 0, frames: pantallas.frames))
    }

    /// La ventana en `v` y la página donde debe verse (marco): si la ventana se recorrió, el contenido al revés.
    func colocar(_ v: CGRect) {
        let w = CGRect(x: marco.minX - v.minX, y: marco.minY - v.minY, width: marco.width, height: marco.height)
        if web.frame != w { web.frame = w }
        if v.size == panel.frame.size { panel.setFrameOrigin(v.origin) } else { panel.setFrame(v, display: false) }
    }

    func soltarArrastre() {
        medicion?.arrastre?.marca("soltar")
        js("WSM.agarrar ? WSM.agarrar(false) : WSM.arrastre(false)")   // baja con su rebote
        guard let s = Agarre.soltar(nido: nidoActual, frames: pantallas.frames, visibles: pantallas.visibles, tam: tamPanel) else { return }
        guardarLugar(s.nido)                                           // una vez, al soltarlo (nunca mientras lo llevas)
        llegar(s)
    }

    /// Llevarlo a `nido` (su esquina, desde el menú) como si lo soltaras ahí: con su resorte y, si hace falta, mudanza.
    func irA(_ nido: CGRect) {
        guard let s = Agarre.soltar(nido: nido, frames: pantallas.frames, visibles: pantallas.visibles, tam: tamPanel) else { return }
        cancelarMovimiento()
        llegar(s)
    }

    /// El nido llega a `s.nido` con el lado de ahora (su resorte; con «reducir movimiento», de una vez) y luego, si
    /// cambia de lado o de alto, la burbuja se muda.
    func llegar(_ s: Agarre.Soltado) {
        let n = nidoActual
        let hasta = CGPoint(x: marco.minX + s.nido.minX - n.minX, y: marco.minY + s.nido.minY - n.minY)
        let luego: () -> Void = { [weak self] in
            guard let self = self else { return }
            if Agarre.seMuda(antes: self.lado, despues: s.lado, tamAntes: self.marco.size, tamDespues: s.panel.size) {
                self.mudarse(s)
            } else {
                self.marco = s.panel
                self.colocar(s.panel)
                self.mirarRaton()
            }
        }
        let lejos = hypot(hasta.x - marco.minX, hasta.y - marco.minY)
        if lejos < 0.5 || NSWorkspace.shared.accessibilityDisplayShouldReduceMotion {
            marco.origin = hasta
            colocar(Agarre.ventana(marco, en: s.pantalla, frames: pantallas.frames))
            luego()
            return
        }
        acomodo = (marco.origin, hasta, s.pantalla, CACurrentMediaTime(), luego)
        enlace?.isPaused = false
    }

    /// Cada cuadro de la pantalla mientras algo se mueve: el resorte del acomodo; y, arrastrando, si el botón ya no
    /// está apretado (se perdió el «soltar»: Mission Control, otra app…), se suelta.
    @objc func cuadroDelArrastre(_ l: CADisplayLink) {
        if let t = toque, t.arrastra, !PruebaRaton.apretado {
            toque = nil
            soltarArrastre()
        }
        if let a = acomodo {
            let t = l.targetTimestamp - a.t0                // el cuadro que se va a ver, no el de ahora
            let k = Resorte.valor(t)                        // pasa de 1 en el rebote: termina por tiempo
            marco.origin = CGPoint(x: a.desde.x + (a.hasta.x - a.desde.x) * k, y: a.desde.y + (a.hasta.y - a.desde.y) * k)
            colocar(Agarre.ventana(marco, en: a.pantalla, frames: pantallas.frames))
            if t >= Resorte.duracion {
                acomodo = nil
                a.luego()
            }
        }
        if toque == nil && acomodo == nil { l.isPaused = true }
    }

    /// Para todo lo que se estaba moviendo (otro toque, un cambio de pantallas, ponerlo en su lugar): el resorte se
    /// queda donde iba (si lo agarras a medio camino, de ahí lo tomas) y una mudanza a medias se termina.
    func cancelarMovimiento() {
        acomodo = nil
        if let m = mudanza { terminarMudanza(m.n) }
    }

    // MARK: la mudanza de lado
    /// Cambia hacia dónde abre (o el alto del panel) sin que el nido se mueva en la pantalla: una foto del nido (una
    /// ventanita encima, idéntica) lo tapa; la burbuja esconde su nido y lo que abre (1), el panel se pone del lado
    /// nuevo y la burbuja se acomoda y vuelve a enseñar el nido y lo que abre (2); al pintarse, la foto se va. Cada fase
    /// contesta cuando ya se pintó; si no contesta en 0.4 s, sigue sola (nunca se queda a medias).
    func mudarse(_ s: Agarre.Soltado) {
        mudanzas += 1
        let n = mudanzas
        mudanza = (n, s, nil)
        medicion?.arrastre?.marca("mudanza")
        let nido = nidoActual.insetBy(dx: -Lugar.adentro, dy: -Lugar.adentro)
        let m = marcoWeb
        let conf = WKSnapshotConfiguration()
        conf.rect = CGRect(x: nido.minX - m.minX, y: m.maxY - nido.maxY, width: nido.width, height: nido.height)
        web.takeSnapshot(with: conf) { [weak self] img, _ in
            MainActor.assumeIsolated {
                guard let self = self, let mu = self.mudanza, mu.n == n else { return }
                if let img = img {
                    let f = PanelMonito(contentRect: nido, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
                    f.sinTeclado = true
                    f.isOpaque = false
                    f.backgroundColor = .clear
                    f.hasShadow = false
                    f.level = self.panel.level
                    f.ignoresMouseEvents = true
                    f.collectionBehavior = self.panel.collectionBehavior
                    f.alphaValue = self.panel.alphaValue
                    let v = NSImageView(frame: NSRect(origin: .zero, size: nido.size))
                    v.image = img
                    v.imageScaling = .scaleAxesIndependently
                    f.contentView = v
                    f.order(.above, relativeTo: self.panel.windowNumber)
                    self.mudanza?.fantasma = f
                }
                self.js("WSM.mudanza ? WSM.mudanza(1, \(n)) : null")
                self.esperarMudanza(n, fase: 1)
            }
        }
    }

    func esperarMudanza(_ n: Int, fase: Int) {
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { [weak self] in
            guard let self = self, let m = self.mudanza, m.n == n else { return }
            self.medicion?.arrastre?.marca("mudanza: la burbuja no contestó la fase \(fase)")
            self.mudanzaSigue(fase, n: n)
        }
    }

    /// La burbuja contestó una fase (o se le acabó el tiempo).
    func mudanzaSigue(_ fase: Int, n: Int) {
        guard let m = mudanza, m.n == n else { return }
        if fase == 1 {
            // escondido el nido de la página (la foto lo tapa): el panel del lado nuevo, la burbuja se acomoda
            let s = m.s
            lado = s.lado
            marco = s.panel
            colocar(s.panel)
            mudanza = (n, s, m.fantasma)
            js("WSM.lado('\(s.lado.h)','\(s.lado.v)');WSM.mudanza ? WSM.mudanza(2, \(n)) : null")
            esperarMudanza(n, fase: 2)
        } else {
            terminarMudanza(n)
        }
    }

    func terminarMudanza(_ n: Int) {
        guard let m = mudanza, m.n == n else { return }
        mudanza = nil
        if lado != m.s.lado || marco != m.s.panel {         // se cortó antes de la fase 1: que quede donde va
            lado = m.s.lado
            marco = m.s.panel
            colocar(m.s.panel)
            js("WSM.lado('\(m.s.lado.h)','\(m.s.lado.v)')")
        }
        js("WSM.mudanza ? WSM.mudanza(0, \(n)) : null")          // por si se cortó: el nido y la burbuja a la vista
        m.fantasma?.orderOut(nil)
        medicion?.arrastre?.marca("mudanza lista")
        mirarRaton()
    }

    /// Un clic en el nido (sin arrastrar): lo mismo que antes hacía la burbuja (si anda volando, regresa; si no, abre
    /// la barra), decidido por ella y hecho aquí de una vez. Una burbuja de antes (sin clicNido): abrir la barra.
    func clicEnNido() {
        medicion?.arrastre?.marca("clic")
        web.evaluateJavaScript("typeof WSM!=='undefined'&&WSM.clicNido?WSM.clicNido():'llamar'") { [weak self] r, _ in
            MainActor.assumeIsolated {
                switch (r as? String) ?? "llamar" {
                case "volver": self?.mensaje(["op": "volver"])
                case "llamar": self?.mensaje(["op": "llamar"])
                default: break
                }
            }
        }
    }
}

// MARK: - el candado por turno
extension Monito {
    var rutaTurno: String { (carpetaEstado as NSString).appendingPathComponent("turno.json") }

    /// El puente abrió un turno (mandaste o contestaste desde la burbuja): las manos miran SOLO la ventana que tenías
    /// enfrente al llamar al monito, y solo con este id (manos_mcp lo lee de turno.json, 600).
    func abrirTurno(_ id: String, agente: String) {
        turno = TurnoAbierto(id: id, desde: Date(), agente: agente)
        // la ventana de ⌥ Espacio; si se respondió una pregunta (sin abrir la barra), la del turno de antes
        let e = fotoBarra.flatMap { $0.enfrente } ?? ultimaVentana ?? manos.tomarEnfrente()
        ultimaVentana = e
        manos.turno(e)
        actuar?.abrirTurno(id, agente: agente, foto: fotoBarra?.foto)
        let info: [String: Any] = ["version": 1, "id": id, "agente": agente, "pid": Int(getpid())]
        if let d = try? JSONSerialization.data(withJSONObject: info, options: [.sortedKeys]) {
            let tmp = rutaTurno + ".\(getpid()).tmp"
            FileManager.default.createFile(atPath: tmp, contents: d, attributes: [.posixPermissions: 0o600])
            chmod(tmp, 0o600)
            if rename(tmp, rutaTurno) != 0 { unlink(tmp) }
        }
        manos.anotar(["turno": "abierto", "agente": agente, "app": e?.nombre ?? "", "ventana": Int(e?.ventana ?? 0)])
    }

    /// Terminó (contestó, se paró o se perdió): las manos ya no miran nada (y si iba volando, regresa).
    func cerrarTurno(_ id: String?) {
        if let id = id, let t = turno, t.id != id { return }       // uno viejo: el abierto es otro
        aterrizar?(.turno)
        if turno != nil { manos?.anotar(["turno": "cerrado"]) }
        actuar?.cerrarTurno()
        turno = nil
        fotoBarra = nil
        manos?.turno(nil)
        unlink(rutaTurno)
    }
}

// MARK: - las manos (F1): ver y señalar
extension Monito {
    func armarManos() {
        let base = URL(fileURLWithPath: op.html).deletingLastPathComponent()
        capa = Capa(html: base.appendingPathComponent("senalar.html"))
        if !op.foto.isEmpty { capa.fotos = op.foto }
        if op.fantasma { capa.alfa = 0.02 }
        manos = Manos(monito: self, carpeta: carpetaEstado)
        // las reglas del portero como datos (Fable v2 §5.6): escritorio/reglas/portero.json de esta copia; sin el archivo,
        // solo lo rojo fijo del código y nada amarillo (falla cerrado)
        let reglas = Reglas.cargar((op.raiz as NSString).appendingPathComponent("escritorio/reglas/portero.json"))
        Reglas.usar(reglas)
        manos.anotar(["reglas": reglas.cargadas ? "cargadas" : "solo el núcleo (sin el archivo)", "vetados": reglas.vetados.count])
        bandeja = BandejaApp(monito: self)
        actuar = Actuar(monito: self, carpeta: carpetaEstado, etapa: op.actuar)
        bandeja.ajustes = actuar.ajustesBandeja
        bandeja.corriendo = { [weak self] in self?.actuar?.enVuelo == true }
        bandeja.alParar = { [weak self] in self?.actuar?.panico("el botón Parar") }
        bandeja.clicRechazado = { [weak self] ficha, boton in
            guard let a = self?.actuar else { return }                 // un clic que no vino de una persona: no cuenta y se anota
            a.portero.registro.append(["cuando": ISO8601DateFormatter().string(from: Date()), "tipo": "clic_rechazado",
                                       "resultado": "no_cuenta", "boton": boton, "ficha": ficha,
                                       "fuente_pid": Int(EventoReal.ultimo.pid), "fuente_estado": Int(EventoReal.ultimo.estado)])
            a.volcar()
        }
        conectarTrabajo()
        manos.permisos.pintar = { [weak self] s in self?.jsManos(s) }
        manos.permisos.ocupado = { [weak self] in
            guard let self = self else { return true }
            return self.turno != nil || self.capa.ocupada || self.aterrizar != nil
        }
        // si la firma cambió y un permiso que tenía ya no está: su renglón muerto se borra y sale UNA tarjeta al abrir
        // (no a medio trabajo); la primera vez, nada (se pide cuando haga falta)
        manos.permisos.alArrancar()
        try? FileManager.default.createDirectory(atPath: carpetaEstado, withIntermediateDirectories: true, attributes: nil)
        try? String(getpid()).write(toFile: (carpetaEstado as NSString).appendingPathComponent("app.pid"), atomically: true, encoding: .utf8)
        unlink(rutaTurno)                                          // uno de antes no vale
        let s = ServidorManos()
        s.atender = { [weak self] nombre, args, quien, fin in
            guard let self = self else { fin(503, ["ok": false, "error": "el monito se está cerrando"]); return }
            // el candado: solo dentro de un turno del escritorio, con su id, y solo si quien llama (el pid dueño de la
            // conexión, comprobado) es el servidor de las manos (escritorio/manos_mcp.py), no cualquier programa
            var porque = Candado.revisar(nombre, turno: self.turno, pedido: quien.turno, ahora: Date())
            if porque == nil, Candado.conTurno.contains(nombre), quien.pid == nil || !quien.comando.contains("manos_mcp") {
                porque = "Solo las manos del monito (su servidor MCP) pueden pedirle esto a la app."
            }
            if let porque = porque {
                self.manos.anotar(["herramienta": nombre, "negado": porque, "quien": ["pid": quien.pid.map { Int($0) } ?? -1, "proceso": quien.proceso, "comando": quien.comando]])
                fin(200, ["ok": false, "error": porque, "sin_turno": true])
                return
            }
            self.manos.atender(nombre, args, quien: quien, fin)
        }
        s.arrancar { [weak self] puerto in
            guard let self = self else { return }
            if puerto == nil {
                FileHandle.standardError.write("No pude abrir el puerto local de las manos: ver y señalar no estarán.\n".data(using: .utf8)!)
                return
            }
            s.anotar(en: self.carpetaEstado, actuar: self.actuar.etapa, agentes: self.actuar.agentesQuePueden)
        }
        servidor = s
    }

    /// Carril 6 (manos de trabajo): sus dos fichas («¿cuál abro?», donde tu toque elige y aprueba; y una intención con
    /// varios renglones y un botón) salen en la bandeja, con la cara de todas. La bandeja no decide nada: le dice a
    /// Trabajo.swift qué tocaste y él va al portero. Son de SU turno: si se acaba, o pasa su rato, la ficha dice «Ya pasó».
    func conectarTrabajo() {
        var abierta: (id: String, base: FichaBandeja, ficha: FichaDeTrabajo, contestar: (RespuestaDeTrabajo) -> Void)?
        /// «Ya pasó · [Pedírselo otra vez]» (lo que no se pudo dejar para después, o ya no es lo mismo).
        func yaPaso(_ base: FichaBandeja, _ motivo: String) {
            let b = TextoFicha.caducada(base, motivo: motivo)
            self.bandeja.poner(b) { [weak self] boton, _ in
                guard let self = self else { return }
                self.bandeja.quitar(b.id)
                if boton == "otra_vez" {
                    self.mandarAlPuente(["op": "mandar", "agente": b.agente, "texto": TextoFicha.otraVez(b), "sin_contexto": true])
                }
            }
        }
        /// junto5 · la ficha se queda para después, con sus renglones: tu toque lo hace la app directo (vale una vez).
        func quedarse(_ id: String, _ base: FichaBandeja, _ f: FichaDeTrabajo) {
            let b = TextoFicha.trabajoDespues(base, ahora: Date())
            self.bandeja.poner(b) { [weak self] boton, _ in
                guard let self = self else { return }
                let renglon: Int?
                if boton.hasPrefix("r:"), let n = Int(boton.dropFirst(2)) { renglon = n }
                else if boton == "todos" { renglon = nil }
                else if boton == "no" { self.manos.trabajo.olvidarDespues(f.id); self.bandeja.quitar(b.id); return }
                else { return }
                self.manos.trabajo.hacerDespues(f.id, renglon: renglon) { [weak self] por in
                    guard let self = self else { return }
                    if por == "espera" {
                        var x = self.bandeja.ficha(b.id) ?? b
                        x.pie = "Otro agente está en su turno: tócalo otra vez en un momento"
                        quedarse(id, x, f)
                        return
                    }
                    self.bandeja.quitar(b.id)
                    if let p = por { yaPaso(base, p) }
                }
            }
        }
        let caducar: (String) -> Void = { [weak self] por in
            guard let self = self, let a = abierta else { return }
            abierta = nil
            a.contestar(.no(por))
            if por == "panico" { self.bandeja.quitar(a.id); return }
            if self.manos.trabajo.quedoParaDespues(a.ficha.id) { quedarse(a.id, a.base, a.ficha); return }
            yaPaso(a.base, por == "turno" ? "se acabó su turno antes de tu toque" : "pasó su rato")
        }
        manos.trabajo.alCerrar = { por in caducar(por) }
        manos.trabajo.presentar = { [weak self] f, contestar in
            guard let self = self else { contestar(.no("no")); return }
            var b = TextoFicha.deTrabajo(id: f.id, elegir: f.forma == .elegir, titulo: f.titulo, boton: f.boton,
                                         renglones: f.renglones.map { RenglonFicha(id: String($0.id), titulo: $0.titulo, detalle: $0.detalle) },
                                         agente: f.agente, nombre: self.bandeja.nombre(f.agente), color: self.bandeja.color(f.agente),
                                         armaMs: f.armaMs, ahora: Date())
            let sinPrimera = b
            // junto5 (E5): la primera vez, ESTA ficha prende «hacer cosas en mi Mac» (tu toque) y abre lo que elijas
            if f.primera { b = TextoFicha.primeraDeTrabajo(b) }
            abierta = (b.id, sinPrimera, f, contestar)
            self.bandeja.poner(b) { [weak self] boton, casilla in
                guard let self = self, let a = abierta, a.id == b.id else { return }
                let r: RespuestaDeTrabajo
                if boton.hasPrefix("r:"), let n = Int(boton.dropFirst(2)) { r = .elegido(n) }
                else if boton == "todos" { r = .todos }
                else if boton == "no" { r = .no("no") }
                else { return }
                abierta = nil
                self.bandeja.quitar(b.id)
                if f.primera, r != .no("no") {
                    self.actuar?.cambiarPuede(f.agente, true, paraTodos: casilla, desde: "su primera ficha (un clic suyo)")
                }
                a.contestar(r)
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + f.vence) { if abierta?.id == b.id { caducar("vencida") } }
        }
    }

    /// JS para las manos de la burbuja (espera a que la burbuja las tenga listas).
    func jsManos(_ s: String) {
        anotar("⇢ " + (manosListas ? "" : "(en espera) ") + String(s.prefix(90)))
        if manosListas {
            web.evaluateJavaScript(s) { [weak self] _, e in
                if let e = e { MainActor.assumeIsolated { self?.anotar("✗ manos: \(e.localizedDescription)") } }
            }
        } else { manosPendientes.append(s) }
    }

    /// La foto del momento, para el siguiente «mandar», y la ventana que tienes enfrente (por número). La app y el
    /// bundle, ya; lo de Accesibilidad, en cuanto se pinta la barra.
    func tomarFoto() {
        guard let m = manos, let app = m.alFrente() else { return }
        let e = m.tomarEnfrente()
        fotoBarra = (FotoDelMomento(app: app.localizedName ?? app.bundleIdentifier ?? "una app", bundle: app.bundleIdentifier ?? ""), e, Date())
        guard Permiso.accesibilidad.concedido else { return }
        DispatchQueue.main.async { [weak self] in
            guard let self = self, let m = self.manos else { return }
            let antes = m.objetivo
            if m.objetivo == nil { m.objetivo = e }                // que la foto sea de ESA ventana
            let f = m.fotoDelMomento()
            m.objetivo = antes
            if self.fotoBarra?.foto.bundle == f.bundle {
                self.fotoBarra = (f, e, self.fotoBarra?.cuando ?? Date())
                self.avisarFoto()
            }
        }
    }

    /// A la burbuja: lo que tienes enfrente (con la ventana, ya leída), si lo dejas viajar.
    func avisarFoto() {
        guard let s = contextoParaBurbuja() else { return }
        js("WSM.contexto(\(s))")
    }

    /// Lo que viaja con tu mensaje: la foto del momento (no se pinta). nil si lo apagaste en el menú.
    func contextoParaBurbuja() -> String? {
        guard decirEnfrente, let f = fotoBarra?.foto,
              let j = try? JSONSerialization.data(withJSONObject: f.paraMandar()) else { return nil }
        return String(data: j, encoding: .utf8)
    }

    /// El ojito de «estoy mirando»: se queda al menos 1.2 s (que se alcance a ver).
    func ojo(_ encendido: Bool, _ texto: String = "") {
        if encendido {
            if ojos == 0 { ojoDesde = Date() }
            ojos += 1
            jsManos("WSMManos.ojo(true, \(Permisos.json(["t": texto])).t)")
        } else {
            let falta = max(0, 1.2 - Date().timeIntervalSince(ojoDesde ?? .distantPast))
            DispatchQueue.main.asyncAfter(deadline: .now() + falta) { [weak self] in
                guard let self = self else { return }
                self.ojos = max(0, self.ojos - 1)
                self.jsManos("WSMManos.ojo(false)")
            }
        }
    }

    /// El monito sale de su nido (donde lo hayas dejado), vuela por la capa a los objetivos y regresa.
    func senalar(_ objetivos: [Objetivo], fin: @escaping (FinVuelo) -> Void) {
        let h0 = NSScreen.screens.first?.frame.height ?? 0
        let ps = NSScreen.screens.map { $0.frame }
        let pf = marcoWeb                                  // la página en la pantalla (aunque se esté arrastrando)
        let nidoAK = nidoActual
        let pNido = Coordenadas.pantalla(de: CGPoint(x: nidoAK.midX, y: h0 - nidoAK.midY), pantallas: ps, altoPrincipal: h0) ?? 0
        let deCada = objetivos.map { Coordenadas.pantalla(de: CGPoint(x: $0.marco.midX, y: $0.marco.midY), pantallas: ps, altoPrincipal: h0) ?? 0 }
        let tramos = Tramos.partir(deCada, nido: pNido)
        let sale = tramos.first?.desdeNido ?? true, regresa = tramos.last?.alNido ?? true
        let ms = objetivos.enumerated().map { Pasos.espera($0.element.etiqueta, ultimo: $0.offset == objetivos.count - 1) }
        // Termine como termine (regresó, lo cortó otro, la capa no contestó, se acabó el turno o lo paraste), una sola
        // vez: el monito vuelve a su nido y la herramienta contesta. Antes, si la capa no avisaba el final, el nido se
        // quedaba vacío para siempre.
        aterrizar?(.cortado)
        vueloN += 1
        let n = vueloN
        var hecho = false, motivo: FinVuelo? = nil
        let terminar: (FinVuelo, Bool) -> Void = { [weak self] f, pop in
            guard !hecho else { return }
            hecho = true
            if let self = self, self.vueloN == n {
                self.guardia?.invalidate()
                self.guardia = nil
                self.aterrizar = nil
            }
            self?.js("WSMManos.volver(\(pop ? "true" : "false"))")
            fin(f)
        }
        aterrizar = { [weak self] f in
            motivo = f
            self?.capa.cortar()                        // si la capa lo tenía, su fin llega abajo; si no, aquí
            terminar(f, true)
        }
        guardia?.invalidate()
        guardia = Timer.scheduledTimer(withTimeInterval: Vuelo.limite(ms: ms, tramos: tramos.count), repeats: false) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self = self, self.vueloN == n else { return }
                self.aterrizar?(.tiempo)
            }
        }
        let seguir: (Any?) -> Void = { [weak self] r in
            guard let self = self else { return }
            var c = "#ffffff", f = "bolita"
            // dónde está el monito: lo dice la burbuja; si no, el nido según su lado
            var nido = Coordenadas.aGlobal(nidoAK.insetBy(dx: 12, dy: 16), altoPrincipal: h0)
            if let s = r as? String, let d = s.data(using: .utf8), let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any] {
                c = (o["c"] as? String) ?? c
                f = (o["f"] as? String) ?? f
                if let x = (o["x"] as? NSNumber)?.doubleValue, let y = (o["y"] as? NSNumber)?.doubleValue,
                   let w = (o["w"] as? NSNumber)?.doubleValue, let hh = (o["h"] as? NSNumber)?.doubleValue {
                    let enAppKit = CGRect(x: pf.minX + x, y: pf.maxY - y - hh, width: w, height: hh)
                    nido = Coordenadas.aGlobal(enAppKit, altoPrincipal: h0)
                }
            }
            guard !hecho else { return }                   // lo pararon antes de despegar
            self.capa.recorrer(objetivos, quien: (c, f), nido: nido, ms: ms) { terminado in
                terminar(motivo ?? (terminado ? .regreso : .cortado), !(terminado && regresa))
            }
        }
        if manosListas {
            web.evaluateJavaScript("WSMManos.salir(\(sale ? "false" : "true"))") { r, _ in
                MainActor.assumeIsolated { seguir(r) }
            }
        } else {
            seguir(nil)
        }
    }
}

// MARK: - pruebas del movimiento (--medir): sin grabar la pantalla
/// Anota cada 4 ms si la ventana del monito sigue en pantalla (CoreGraphics, sin permisos) y si tiene el teclado; la
/// página anota sus huecos entre cuadros y sus cambios de visibilidad. Corre un guion corto: abrir la barra, escribir,
/// Esc, y otra vez (la tecla Esc de verdad se finge en la página: la app recibe lo mismo).
@MainActor
final class Medicion {
    unowned let monito: Monito
    let archivo: String
    var lineas: [String] = []
    let t0 = Date()
    var muestreo: DispatchSourceTimer?
    var ultimo: String = ""
    var arrastre: MedirArrastre?

    static let js = """
    (function () {
      var t0 = performance.now(), prev = t0, n = 0;
      function post(o) { try { window.webkit.messageHandlers.ws.postMessage(Object.assign({ op: 'medir' }, o)); } catch (e) { } }
      function cuadro(t) { var d = t - prev; prev = t; n++; if (d > 34) post({ que: 'hueco', ms: Math.round(d) }); requestAnimationFrame(cuadro); }
      requestAnimationFrame(cuadro);
      document.addEventListener('visibilitychange', function () { post({ que: 'visibilidad', estado: document.visibilityState }); });
      setInterval(function () { post({ que: 'cuadros', n: n }); n = 0; }, 1000);
    })();
    """

    init(monito: Monito, archivo: String) {
        self.monito = monito
        self.archivo = archivo
        marca("inicio")
        let q = DispatchQueue(label: "workspace.monito.medir")
        let t = DispatchSource.makeTimerSource(queue: q)
        let num = monito.panel?.windowNumber ?? 0
        t.schedule(deadline: .now(), repeating: .milliseconds(4))
        t.setEventHandler { [weak self] in
            guard num > 0, let l = CGWindowListCopyWindowInfo([.optionIncludingWindow], CGWindowID(num)) as? [[String: Any]] else { return }
            let en = (l.first?[kCGWindowIsOnscreen as String] as? Bool) ?? false
            DispatchQueue.main.async { MainActor.assumeIsolated { self?.ventana(en) } }
        }
        t.resume()
        muestreo = t
    }

    func ms() -> Int { Int(Date().timeIntervalSince(t0) * 1000) }

    func marca(_ s: String) {
        lineas.append("\(ms()) \(s) · teclado=\(monito.panel?.isKeyWindow ?? false)")
        guardar()
    }

    func ventana(_ en: Bool) {
        let s = en ? "en pantalla" : "FUERA de pantalla"
        if s != ultimo { ultimo = s; marca("ventana: " + s) }
    }

    func dePagina(_ d: [String: Any]) {
        let que = (d["que"] as? String) ?? ""
        if que == "cuadros" { lineas.append("\(ms()) página: \((d["n"] as? NSNumber)?.intValue ?? 0) cuadros en 1 s"); return }
        marca("página: " + que + " " + ((d["ms"] as? NSNumber).map { "\($0) ms" } ?? (d["estado"] as? String ?? "")))
    }

    /// El guion de los lugares (WORKSPACE_MONITO_MEDIR=lugar): lo suelta en cada esquina de cada pantalla y fuera de
    /// todas; anota el panel, el lado y el nido, y fotografía la burbuja abierta (sin tomar el teclado).
    func lugares() {
        var puntos: [(String, CGRect)] = []
        for (i, s) in NSScreen.screens.enumerated() {
            let v = s.visibleFrame, n = Lugar.nido
            puntos += [("p\(i) abajo-der", CGRect(x: v.maxX - 40, y: v.minY - 30, width: n.width, height: n.height)),
                       ("p\(i) abajo-izq", CGRect(x: v.minX - 60, y: v.minY + 5, width: n.width, height: n.height)),
                       ("p\(i) arriba-izq", CGRect(x: v.minX + 3, y: v.maxY + 50, width: n.width, height: n.height)),
                       ("p\(i) arriba-der", CGRect(x: v.maxX - 90, y: v.maxY - 100, width: n.width, height: n.height))]
        }
        puntos.append(("fuera de todas", CGRect(x: -6000, y: 4000, width: 100, height: 118)))
        monito.js("WSM.recibir({t:'agentes',agentes:[{id:'luna',n:'Luna',c:'#ff4fa3',f:'nube'}],elegido:'luna'});"
                  + "WSM.s.turno={tu:'¿y aquí?',texto:'',vivo:true};WSM.recibir({t:'respuesta',agente:'luna',texto:'Aquí abro hacia donde hay espacio.'});")
        for (k, (nombre, r)) in puntos.enumerated() {
            let t = 0.8 + Double(k) * 0.9
            DispatchQueue.main.asyncAfter(deadline: .now() + t) { [weak self] in
                guard let self = self else { return }
                self.monito.ponerEn(r, animar: false)
                self.monito.guardarLugar(Lugar.dentro(self.monito.nidoActual, visible: NSScreen.screens[Lugar.pantalla(de: self.monito.nidoActual, frames: NSScreen.screens.map { $0.frame }) ?? 0].visibleFrame))
                let n = self.monito.nidoActual, f = self.monito.panel.frame
                let i = Lugar.pantalla(de: n, frames: NSScreen.screens.map { $0.frame }) ?? -1
                let vf = i >= 0 ? NSScreen.screens[i].visibleFrame : .zero
                self.marca("lugar \(nombre): nido \(Int(n.minX)),\(Int(n.minY)) en p\(i) · dentro=\(vf.insetBy(dx: Lugar.margen - 0.5, dy: Lugar.margen - 0.5).contains(n)) · lado \(self.monito.lado.h)/\(self.monito.lado.v) · panel \(Int(f.minX)),\(Int(f.minY)) \(Int(f.width))×\(Int(f.height))")
            }
            DispatchQueue.main.asyncAfter(deadline: .now() + t + 0.5) { [weak self] in
                guard let self = self else { return }
                self.monito.fotografiar(self.archivo + String(format: "_lugar%02d.png", k))
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.8 + Double(puntos.count) * 0.9 + 0.6) { [weak self] in
            guard let self = self else { return }
            let g = self.monito.nidoGuardado(), a = self.monito.nidoActual
            self.marca("recordado: nido guardado \(Int(g.minX)),\(Int(g.minY)) = el de ahora \(Int(a.minX)),\(Int(a.minY)): \(abs(g.minX - a.minX) < 2 && abs(g.minY - a.minY) < 2)")
            self.marca("fin")
            NSApp.terminate(nil)
        }
    }

    /// El guion: abrir, escribir, Esc (dos veces), con el monito casi invisible (--fantasma) y sin robar el teclado más
    /// de un segundo cada vez.
    func listo() {
        switch ProcessInfo.processInfo.environment["WORKSPACE_MONITO_MEDIR"] ?? "" {
        case "lugar": lugares(); return
        case "arrastre": arrastre = MedirArrastre(monito: monito, archivo: archivo); arrastre?.correr(); return   // MedirArrastre.swift
        case "nada": return                               // solo anota (otra prueba la maneja desde fuera)
        default: break
        }
        let pasos: [(Double, String)] = [
            (1.0, "WSM.barra(true)"),
            (1.6, "(function(){var t=document.querySelector('.wsm-caja textarea');t.value='hola';t.dispatchEvent(new Event('input'));})()"),
            (2.0, "document.querySelector('.wsm-caja textarea').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}))"),
            (4.0, "WSM.barra(true)"),
            (4.8, "document.querySelector('.wsm-caja textarea').dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}))"),
        ]
        for (t, c) in pasos {
            DispatchQueue.main.asyncAfter(deadline: .now() + t) { [weak self] in
                self?.marca("guion: " + String(c.prefix(40)))
                self?.monito.js(c)
            }
        }
        // cuadros de la página justo después de cada Esc (takeSnapshot: lo que pinta WebKit)
        for (i, t) in [1.95, 2.02, 2.06, 2.12, 2.2, 2.3, 2.5, 4.75, 4.82, 4.86, 4.92, 5.0, 5.1].enumerated() {
            DispatchQueue.main.asyncAfter(deadline: .now() + t) { [weak self] in
                guard let self = self else { return }
                self.monito.fotografiar(self.archivo + String(format: "_cuadro%02d_%04d.png", i, Int(t * 1000)))
            }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + 6.5) { [weak self] in
            self?.marca("fin")
            NSApp.terminate(nil)
        }
    }

    func guardar() {
        try? (lineas.joined(separator: "\n") + "\n").write(toFile: archivo, atomically: true, encoding: .utf8)
    }
}
