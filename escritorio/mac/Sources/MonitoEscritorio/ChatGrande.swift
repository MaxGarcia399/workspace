// Ronda 2 · bloque G (G1-a · G2-a · G3-a) · la ventana del chat grande.
//
//   · Una ventana flotante que TÚ cambias de tamaño y mueves (de su encabezado); recuerda tamaño y lugar entre
//     reinicios (por arreglo de pantallas) y si la dejaste en grande o en chico (<estado>/escritorio/grande.json).
//   · No es otro chat: carga la MISMA página de la burbuja (monito.html) con la clase «wsm-ventana», y esa página
//     acomoda en grande sus mismas piezas (la plática, la caja de escribir, las tarjetas). Lo que ahí pides va por el
//     mismo camino que lo de la burbuja (Monito.mensaje → el puente); lo que llega del puente va a las dos páginas.
//   · Mientras está abierta, la burbuja chica se calla (WSM.fuera): lo nuevo aparece adentro de la ventana, que no se
//     cierra sola.
//   · Guardar y llamar tienen UN modelo (Compa, LogicaGrande.swift) y UN lugar (Monito.gesto): «─ Minimizar», Esc, ⌘W,
//     ⌥ Espacio y un clic en el Compañero la guardan con TODO lo demás; al llamarlo vuelve en grande, donde estaba.
//     «⤡ Chico» es otra cosa: el mismo chat, de regreso en la burbuja. Esta ventana nunca decide sola si se queda.
// Como el monito: no activa la app ni sale en el Dock; solo toma el teclado cuando la abres o le picas.
// Lo que se prueba suelto (dónde va, qué se guarda, a quién le toca cada pedido) vive en LogicaGrande.swift.
import AppKit
import WebKit

/// La ventana: toma el teclado (para escribir) sin activar la app.
final class PanelGrande: NSPanel {
    override var canBecomeKey: Bool { true }
    override var canBecomeMain: Bool { false }
}

/// De dónde se toma la ventana para moverla: una franja transparente encima de la página (su encabezado, donde no hay
/// botones). El WKWebView se queda con todos los clics, así que mover la ventana «por su fondo» no funciona con él.
final class AsaGrande: NSView {
    override var mouseDownCanMoveWindow: Bool { true }
    override func mouseDown(with e: NSEvent) {
        if e.clickCount == 2 { window?.zoom(nil); return }      // doble clic: a todo lo visible de la pantalla (y de vuelta)
        window?.performDrag(with: e)
    }
    override func acceptsFirstMouse(for event: NSEvent?) -> Bool { true }
}

/// Lo que la página de la ventana manda por `window.webkit.messageHandlers.ws` (un objeto aparte: WebKit no retiene la app).
final class MensajeroGrande: NSObject, WKScriptMessageHandler {
    weak var dueno: ChatGrande?
    func userContentController(_ c: WKUserContentController, didReceive m: WKScriptMessage) {
        let cuerpo = m.body
        // M-3 · el canal solo se le oye a la página propia, en su marco principal
        let origen = m.frameInfo.request.url, principal = m.frameInfo.isMainFrame
        MainActor.assumeIsolated {
            guard let d = dueno, Navegacion.delCanal(origen, propia: d.monito.paginaPropia, marcoPrincipal: principal) else { return }
            d.mensaje(cuerpo)
        }
    }
}

@MainActor
final class ChatGrande: NSObject, NSWindowDelegate, WKNavigationDelegate {
    unowned let monito: Monito
    unowned let entregas: Entregas
    private(set) var panel: PanelGrande?
    private(set) var web: WKWebView?
    private let mensajero = MensajeroGrande()
    /// Su página ya cargó y dijo «listo».
    private(set) var lista = false
    /// Lo que hay que decirle a su página en cuanto esté lista.
    private var cola: [String] = []
    private var asas: [AsaGrande] = []
    /// Cómo lo dejaste: «grande» (al llamar al monito vuelve la ventana) o «chico» (la burbuja de siempre).
    private(set) var modo = "chico"
    private var marcoGuardado: CGRect?
    /// junto5 · el último clic de una PERSONA en esta ventana (EventoReal; lo anota Entregas.raton). Con él se aceptan
    /// los botones de ficha que pide su página (ficha_tocar), igual que en la burbuja con el suyo.
    var ultimoClic: ClicReal? = nil
    private var guion = false

    init(monito: Monito, entregas: Entregas) {
        self.monito = monito
        self.entregas = entregas
        super.init()
        mensajero.dueno = self
        let g = LugarGrande.leer(leerArchivo(), firma: monito.firmaPantallas)
        modo = g.modo
        marcoGuardado = g.marco
    }

    var visible: Bool { panel?.isVisible == true }
    private var ruta: String { (monito.carpetaEstado as NSString).appendingPathComponent("grande.json") }

    private func leerArchivo() -> [String: Any]? {
        guard let d = FileManager.default.contents(atPath: ruta) else { return nil }
        return (try? JSONSerialization.jsonObject(with: d)) as? [String: Any]
    }

    /// El modo y el marco de ahora, a grande.json (solo tú lo lees: 0600).
    private func guardarEstado() {
        if let p = panel, p.isVisible || marcoGuardado == nil { marcoGuardado = p.frame }
        let o = LugarGrande.guardar(modo: modo, marco: marcoGuardado, firma: monito.firmaPantallas, en: leerArchivo())
        guard let d = try? JSONSerialization.data(withJSONObject: o, options: [.sortedKeys]) else { return }
        try? FileManager.default.createDirectory(atPath: monito.carpetaEstado, withIntermediateDirectories: true, attributes: nil)
        let tmp = ruta + ".tmp"
        guard FileManager.default.createFile(atPath: tmp, contents: d, attributes: [.posixPermissions: 0o600]) else { return }
        _ = try? FileManager.default.replaceItemAt(URL(fileURLWithPath: ruta), withItemAt: URL(fileURLWithPath: tmp))
        if FileManager.default.fileExists(atPath: tmp) { try? FileManager.default.moveItem(atPath: tmp, toPath: ruta) }
    }

    private func anotar(_ s: String) { monito.anotar("grande: " + s) }

    // MARK: armar
    private func armar() {
        let visibles = NSScreen.screens.map { $0.visibleFrame }
        let principal = (NSScreen.main ?? NSScreen.screens.first)?.visibleFrame ?? NSRect(x: 0, y: 0, width: 1440, height: 900)
        let marco = LugarGrande.valido(marcoGuardado, visibles: visibles) ?? LugarGrande.deFabrica(visible: principal)
        let p = PanelGrande(contentRect: marco, styleMask: [.titled, .resizable, .fullSizeContentView, .nonactivatingPanel],
                            backing: .buffered, defer: false)
        p.titlebarAppearsTransparent = true
        p.titleVisibility = .hidden
        p.title = "Workspace · chat"
        for b in [NSWindow.ButtonType.closeButton, .miniaturizeButton, .zoomButton] { p.standardWindowButton(b)?.isHidden = true }
        p.isMovableByWindowBackground = false
        p.isFloatingPanel = true
        p.becomesKeyOnlyIfNeeded = false
        p.level = .floating
        p.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary]
        p.hidesOnDeactivate = false
        p.isReleasedWhenClosed = false
        p.minSize = LugarGrande.minimo
        p.backgroundColor = NSColor(srgbRed: 0x20 / 255.0, green: 0x20 / 255.0, blue: 0x24 / 255.0, alpha: 1)   // --card
        p.appearance = NSAppearance(named: .darkAqua)
        p.delegate = self
        p.setFrame(marco, display: false)
        if monito.op.fantasma { p.alphaValue = 0.02 }          // pruebas: que nadie la vea

        let conf = WKWebViewConfiguration()
        conf.userContentController.add(mensajero, name: "ws")
        // la misma página de la burbuja, que al cargar sabe que es la ventana (pinta el chat en grande, sin nido)
        conf.userContentController.addUserScript(WKUserScript(source: "document.documentElement.classList.add('wsm-ventana');",
                                                              injectionTime: .atDocumentStart, forMainFrameOnly: true))
        conf.preferences.inactiveSchedulingPolicy = .none
        let caja = NSView(frame: NSRect(origin: .zero, size: marco.size))
        caja.autoresizingMask = [.width, .height]
        let w = WKWebView(frame: caja.bounds, configuration: conf)
        w.autoresizingMask = [.width, .height]
        w.setValue(false, forKey: "drawsBackground")
        w.navigationDelegate = self                         // M-3: solo su página
        caja.addSubview(w)
        p.contentView = caja
        let url = URL(fileURLWithPath: monito.op.html)
        w.loadFileURL(url, allowingReadAccessTo: url.deletingLastPathComponent())
        panel = p
        web = w
        guion = !monito.op.guion.isEmpty
    }

    // MARK: abrir y guardar
    /// La ventana, al frente y con el teclado. `ver`: [agente, encargo] que hay que enseñar adentro (el «Ver» del toque).
    func abrir(ver: [String]? = nil) {
        if panel == nil { armar() }
        guard let p = panel else { return }
        let yaEstaba = p.isVisible
        modo = "grande"
        if !yaEstaba {
            // lo que tienes enfrente, como al abrir la barra (viaja callado con tu siguiente mensaje, si lo dejas)
            if monito.fotoBarra == nil || Date().timeIntervalSince(monito.fotoBarra!.cuando) > 2 { monito.tomarFoto() }
            if let m = LugarGrande.valido(p.frame, visibles: NSScreen.screens.map { $0.visibleFrame }) { if m != p.frame { p.setFrame(m, display: false) } }
            else if let v = (NSScreen.main ?? NSScreen.screens.first)?.visibleFrame { p.setFrame(LugarGrande.deFabrica(visible: v), display: false) }
        }
        monito.js("typeof WSMEntregas!=='undefined'&&WSMEntregas.grandeFuera&&WSMEntregas.grandeFuera(true,'grande')")
        correr("WSM.contexto(\(monito.contextoParaBurbuja() ?? "null"))")
        if let v = ver, v.count == 2 { correr("WSMEntregas.ver(\(Permisos.json(["a": v[0], "i": v[1]])).a, \(Permisos.json(["a": v[0], "i": v[1]])).i)") }
        if monito.op.fantasma {
            // pruebas: casi invisible, sin tomar el teclado ni los clics de quien está usando la Mac
            p.ignoresMouseEvents = true
            p.orderFrontRegardless()
        } else {
            p.makeKeyAndOrderFront(nil)
            if let w = web { p.makeFirstResponder(w) }
            correr("WSM.mic.enfocar()")
        }
        guardarEstado()
        if !yaEstaba { anotar("abierta \(Int(p.frame.width))×\(Int(p.frame.height))") }
    }

    /// Se esconde (no se destruye: al volver está como la dejaste) y queda anotado cómo vuelve al llamarlo: `modo`
    /// «grande» (la ventana, donde estaba) o «chico» (la burbuja). Solo lo llama Monito (guardarTodo y «⤡ Chico»):
    /// ningún otro camino quita la ventana, así nunca queda una a medias.
    func esconder(vuelve como: String) {
        let antes = modo
        modo = como == "chico" ? "chico" : "grande"
        let estaba = panel?.isVisible == true
        if estaba, let p = panel { marcoGuardado = p.frame }
        if estaba || modo != antes { guardarEstado() }
        guard estaba else {
            if modo != antes { monito.js("typeof WSM!=='undefined'&&WSM.modo('\(modo)')") }     // la burbuja, al día
            return
        }
        panel?.orderOut(nil)
        monito.js("typeof WSMEntregas!=='undefined'&&WSMEntregas.grandeFuera&&WSMEntregas.grandeFuera(false,'\(modo)')")
        anotar("guardada (\(modo))")
    }

    // MARK: lo que va a su página
    /// M-3 · la ventana solo carga SU página: un enlace soltado encima (o cualquier otra navegación) se niega.
    func webView(_ w: WKWebView, decidePolicyFor a: WKNavigationAction, decisionHandler: @escaping @MainActor (WKNavigationActionPolicy) -> Void) {
        let ok = Navegacion.permitida(a.request.url, propia: monito.paginaPropia, marcoPrincipal: a.targetFrame?.isMainFrame ?? false)
        if !ok { monito.anotar("✗ navegación negada (ventana): " + String((a.request.url?.scheme ?? "?").prefix(20))) }
        decisionHandler(ok ? .allow : .cancel)
    }

    private func correr(_ codigo: String) {
        guard lista, let w = web else { cola.append(codigo); return }
        w.evaluateJavaScript(codigo, completionHandler: nil)
    }

    /// Lo que la app le dice a la burbuja (una miniatura, lo que pasó con un botón…): también a la ventana, si existe.
    func js(_ codigo: String) { if panel != nil { correr(codigo) } }

    /// Una línea del puente (la misma que va a la burbuja): a la ventana también.
    func recibir(_ linea: String) {
        guard panel != nil, let d = try? JSONSerialization.data(withJSONObject: [linea]), let s = String(data: d, encoding: .utf8) else { return }
        correr("WSM.recibir(\(s.dropFirst().dropLast()))")
    }

    // MARK: lo que pide su página
    func mensaje(_ cuerpo: Any) {
        guard let d = cuerpo as? [String: Any], let k = d["op"] as? String else { return }
        switch OpsGrande.destino(k) {
        case .nada:
            return
        case .ventana:
            propia(k, d)
        case .app:
            // lo mismo que si lo pidiera la burbuja; lo que la app conteste con una ventanita (Compartir) sale de aquí
            entregas.origen = web
            monito.mensaje(d)
            entregas.origen = nil
        }
    }

    private func propia(_ k: String, _ d: [String: Any]) {
        switch k {
        case "listo":
            lista = true
            web?.evaluateJavaScript(Contrato.saludo(guion: guion), completionHandler: nil)
            // sus agentes (lo último que dijo el puente) y el que tienes elegido; su plática y su estado, de nuevo
            if let a = entregas.ultimosAgentes { recibir(a) }
            entregas.paraLaVentana.forEach { recibir($0) }     // lo que el puente no repite (encargos, botones)
            let e = entregas.elegido
            if !e.isEmpty {
                correr("WSM.elegir(\(Permisos.json(["a": e])).a, false)")
                monito.mandarAlPuente(["op": "elegir", "agente": e])
            }
            let c = cola
            cola = []
            c.forEach { correr($0) }
            // junto5 · lo que la app solo le decía a la burbuja: las fichas que esperan (su columna «Te esperan») y la voz
            if let f = monito.bandeja?.publicado { correr(f) }
            monito.voz?.saludar()
            if guion { DispatchQueue.main.asyncAfter(deadline: .now() + 1.2) { [weak self] in self?.correrGuion() } }
        case "grande":
            // sus botones: «─ Minimizar» y Esc (todo se guarda), «⤡ Chico» (a la burbuja). Decide Monito.gesto.
            if (d["abierto"] as? Bool) == true { monito.gesto(.agrandar) }
            else if (d["como"] as? String) == "chico" { monito.gesto(.achicar) }
            else { monito.gesto(.minimizar) }
        case "grande_estado":
            correr("WSM.modo('\(modo)')")
        case "grande_asa":
            ponerAsas(d["zonas"])
        case "zonas_arrastre":
            entregas.zonasGrande = ZonaArrastre.leer(d["zonas"])
        case "guion_log":
            guard guion else { return }
            anotar("guion: " + String(((d["texto"] as? String) ?? "").prefix(2000)))
        case "guion_tamano":
            guard guion else { return }
            tamano(CGFloat((d["w"] as? NSNumber)?.doubleValue ?? 980), CGFloat((d["h"] as? NSNumber)?.doubleValue ?? 660))
        case "guion_foto":
            guard guion, !monito.op.foto.isEmpty else { return }
            let n = ((d["nombre"] as? String) ?? "x").filter { $0.isLetter || $0.isNumber || $0 == "_" || $0 == "-" }.prefix(40)
            fotografiar(monito.op.foto + "_" + n + ".png")
        default:
            return
        }
    }

    /// Las franjas de donde se toma la ventana (en puntos de la página, desde arriba-izquierda), encima del WKWebView.
    private func ponerAsas(_ crudo: Any?) {
        guard let caja = panel?.contentView else { return }
        asas.forEach { $0.removeFromSuperview() }
        asas = []
        for z in ((crudo as? [[Any]]) ?? []).prefix(4) {
            let n = z.compactMap { ($0 as? NSNumber)?.doubleValue }
            guard n.count == 4, n[2] > 8, n[3] > 4, n.allSatisfy({ $0.isFinite }) else { continue }
            let a = AsaGrande(frame: NSRect(x: n[0], y: Double(caja.bounds.height) - n[1] - n[3], width: n[2], height: n[3]))
            a.autoresizingMask = [.minYMargin]                 // pegada arriba (la página manda las nuevas al cambiar de tamaño)
            caja.addSubview(a, positioned: .above, relativeTo: web)
            asas.append(a)
        }
    }

    // MARK: la ventana
    func windowDidEndLiveResize(_ n: Notification) { guardarEstado() }
    func windowDidMove(_ n: Notification) {
        guard let p = panel, p.isVisible else { return }
        marcoGuardado = p.frame
        NSObject.cancelPreviousPerformRequests(withTarget: self, selector: #selector(guardarLuego), object: nil)
        perform(#selector(guardarLuego), with: nil, afterDelay: 0.6)
    }
    @objc private func guardarLuego() { guardarEstado() }
    /// ⌘W o cerrarla desde el sistema: se guarda con todo lo demás, no se destruye.
    func windowShouldClose(_ sender: NSWindow) -> Bool {
        monito.gesto(.cerrarVentana)
        return false
    }

    func cerrar() {
        if let p = panel, p.isVisible { marcoGuardado = p.frame; guardarEstado() }
        panel?.orderOut(nil)
    }

    // MARK: pruebas (--guion y --foto): lo que pinta la ventana, a un PNG; y su parte del guion
    func fotografiar(_ ruta: String) {
        web?.takeSnapshot(with: nil) { img, _ in
            guard let img = img, let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
                  let png = rep.representation(using: .png, properties: [:]) else { return }
            try? png.write(to: URL(fileURLWithPath: ruta))
        }
    }

    /// El guion de la ventana: <guion>.grande.js, si existe (aprieta botones como tú; cuenta con op «guion_log»).
    private func correrGuion() {
        let ruta = monito.op.guion + ".grande.js"
        guard let codigo = try? String(contentsOfFile: ruta, encoding: .utf8) else { return }
        web?.evaluateJavaScript(codigo) { [weak self] _, e in
            if let e = e { MainActor.assumeIsolated { self?.anotar("guion: ✗ \(e.localizedDescription)") } }
        }
    }

    /// Pruebas: la ventana a un tamaño dado (sin tocarla con el ratón).
    func tamano(_ w: CGFloat, _ h: CGFloat) {
        guard let p = panel else { return }
        var f = p.frame
        f.origin.y += f.height - h
        f.size = CGSize(width: max(LugarGrande.minimo.width, w), height: max(LugarGrande.minimo.height, h))
        p.setFrame(f, display: true)
    }
}
