// La capa de señalar: un panel transparente por pantalla, encima de todo (también de los menús y de las apps en
// pantalla completa), en todos los escritorios y sin tomar clics. Carga escritorio/web/senalar.html: el mismo monito
// vuela ahí desde donde lo hayas dejado, ilumina lo que te enseña y regresa. Nunca hace clic ni escribe. Un punto suelto
// (sin elemento ni texto) se pinta distinto: «por aquí», más amplio, sin prometer precisión.
//
// Varias pantallas: los pasos se parten en tramos (uno por pantalla seguida); el monito sale del nido si el primer
// tramo es en la pantalla del nido (si no, sale con un «puf» y aparece en la otra), y regresa volando al nido si el
// último tramo es ahí (si no, desaparece allá y reaparece en la esquina).
import AppKit
import WebKit

/// Un panel de la capa: no toma el teclado ni el ratón.
final class PanelCapa: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

/// Recibe lo que dice cada capa (un objeto aparte para que WebKit no retenga la app).
final class OidoCapa: NSObject, WKScriptMessageHandler {
    weak var capa: Capa?
    let pantalla: Int
    init(_ capa: Capa, _ pantalla: Int) { self.capa = capa; self.pantalla = pantalla }
    func userContentController(_ c: WKUserContentController, didReceive m: WKScriptMessage) {
        let cuerpo = m.body
        MainActor.assumeIsolated { capa?.mensaje(pantalla, cuerpo) }
    }
}

/// Lo que se enseña: un rectángulo global (puntos, arriba-izquierda), su etiqueta y si es un punto suelto.
struct Objetivo {
    var marco: CGRect
    var etiqueta: String
    var punto: Bool
}

@MainActor
final class Capa: NSObject {
    let html: URL
    /// Fotos de los cuadros mientras vuela (para revisar el movimiento sin grabar la pantalla): <prefijo>_capaNNN.png
    var fotos = ""
    /// Pruebas: la capa casi transparente (que nadie la vea mientras se mide).
    var alfa: CGFloat = 1
    private var paneles: [(panel: PanelCapa, web: WKWebView, marco: CGRect, listo: Bool, espera: [String])] = []
    private var sucia = true
    private var enCurso: (id: Int, tramos: [Tramo], i: Int, spec: [[String: Any]], fin: (Bool) -> Void)?
    private var turno = 0
    private var foto = 0
    private var reloj: Timer?

    init(html: URL) {
        self.html = html
        super.init()
        NotificationCenter.default.addObserver(self, selector: #selector(cambiaron), name: NSApplication.didChangeScreenParametersNotification, object: nil)
    }

    @objc func cambiaron() { sucia = true }

    /// Una capa por pantalla (se arman la primera vez que hacen falta y se rehacen si cambian las pantallas).
    func preparar() {
        let ps = NSScreen.screens.map { $0.frame }
        if !sucia && ps == paneles.map({ $0.marco }) { return }
        paneles.forEach { $0.panel.orderOut(nil); $0.web.configuration.userContentController.removeScriptMessageHandler(forName: "capa") }
        paneles = []
        for (i, f) in ps.enumerated() {
            let p = PanelCapa(contentRect: f, styleMask: [.borderless, .nonactivatingPanel], backing: .buffered, defer: false)
            p.isOpaque = false
            p.backgroundColor = .clear
            p.hasShadow = false
            p.level = .screenSaver                     // encima de los menús y de lo que esté en pantalla completa
            p.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary, .ignoresCycle]
            p.ignoresMouseEvents = true                // nunca toma un clic: todo pasa a la app de abajo
            p.hidesOnDeactivate = false
            p.isReleasedWhenClosed = false
            p.sharingType = .none                      // fuera de las fotos (de las nuestras y de otras apps)
            p.alphaValue = alfa
            let conf = WKWebViewConfiguration()
            conf.userContentController.add(OidoCapa(self, i), name: "capa")
            // que WebKit no la frene mientras no tiene el foco (la etiqueta se escribe con temporizadores: frenada, en la
            // otra pantalla salía a medias o vacía)
            conf.preferences.inactiveSchedulingPolicy = .none
            let w = WKWebView(frame: NSRect(origin: .zero, size: f.size), configuration: conf)
            w.autoresizingMask = [.width, .height]
            w.setValue(false, forKey: "drawsBackground")
            p.contentView = w
            p.setFrame(f, display: false)
            w.loadFileURL(html, allowingReadAccessTo: html.deletingLastPathComponent())
            paneles.append((p, w, f, false, []))
        }
        sucia = false
    }

    func mensaje(_ i: Int, _ cuerpo: Any) {
        guard i < paneles.count, let d = cuerpo as? [String: Any], let op = d["op"] as? String else { return }
        switch op {
        case "listo":
            paneles[i].listo = true
            let e = paneles[i].espera
            paneles[i].espera = []
            e.forEach { paneles[i].web.evaluateJavaScript($0, completionHandler: nil) }
        case "fin":
            siguiente(desde: i)
        default:
            break
        }
    }

    private func js(_ i: Int, _ s: String) {
        guard i < paneles.count else { return }
        if paneles[i].listo { paneles[i].web.evaluateJavaScript(s, completionHandler: nil) } else { paneles[i].espera.append(s) }
    }

    /// Recorre los objetivos. `quien`: color y forma del monito; `nido`: dónde está el de la esquina (global).
    /// `fin(true)` cuando terminó, `fin(false)` si lo cortó otro señalar. `alNido(pop)` devuelve al monito de la
    /// esquina (pop: reaparece con un brinco porque no regresó volando).
    func recorrer(_ objetivos: [Objetivo], quien: (c: String, f: String), nido: CGRect, ms: [Double],
                  fin: @escaping (Bool) -> Void) {
        cortar()
        preparar()
        let h0 = NSScreen.screens.first?.frame.height ?? 0
        let ps = paneles.map { $0.marco }
        guard !ps.isEmpty else { fin(false); return }
        let deCada = objetivos.map { Coordenadas.pantalla(de: CGPoint(x: $0.marco.midX, y: $0.marco.midY), pantallas: ps, altoPrincipal: h0) ?? 0 }
        let pNido = Coordenadas.pantalla(de: CGPoint(x: nido.midX, y: nido.midY), pantallas: ps, altoPrincipal: h0) ?? 0
        let tramos = Tramos.partir(deCada, nido: pNido)
        var spec: [[String: Any]] = []
        for t in tramos {
            let sf = ps[t.pantalla]
            func local(_ r: CGRect) -> [String: Any] {
                let l = Coordenadas.local(r, pantalla: sf, altoPrincipal: h0)
                return ["x": l.minX, "y": l.minY, "w": l.width, "h": l.height]
            }
            var pasos: [[String: Any]] = []
            for k in t.pasos {
                var p = local(objetivos[k].marco)
                p["etiqueta"] = objetivos[k].etiqueta
                p["punto"] = objetivos[k].punto
                p["n"] = k + 1
                p["de"] = objetivos.count
                p["ms"] = Int((k < ms.count ? ms[k] : 2.6) * 1000)
                pasos.append(p)
            }
            var s: [String: Any] = ["c": quien.c, "f": quien.f, "pasos": pasos]
            if t.desdeNido { s["desde"] = local(nido) }
            if t.alNido { s["hasta"] = local(nido) }
            spec.append(s)
        }
        turno += 1
        enCurso = (turno, tramos, -1, spec, fin)
        // todas las capas del recorrido, a la vista desde el principio (transparentes y sin clics): así cada página ya
        // está despierta cuando le toca su tramo (antes la de la otra pantalla entraba en frío y su etiqueta no salía)
        for k in Set(tramos.map { $0.pantalla }) where k < paneles.count { paneles[k].panel.orderFrontRegardless() }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.12) { [weak self] in self?.siguiente(desde: nil) }
    }

    private func siguiente(desde i: Int?) {
        guard var e = enCurso else { return }
        if let i = i {
            guard e.i >= 0, e.i < e.tramos.count, e.tramos[e.i].pantalla == i else { return }
        }
        e.i += 1
        enCurso = e
        if e.i >= e.tramos.count {
            enCurso = nil
            pararFotos()
            let ps = paneles.map { $0.panel }, t = turno
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { [weak self] in                 // ya sin nada…
                guard let self = self, Vuelo.esconderCapas(programado: t, ahora: self.turno, enCurso: self.enCurso != nil) else { return }
                ps.forEach { $0.orderOut(nil) }                                                       // …si no empezó otro
            }
            e.fin(true)
            return
        }
        let k = e.tramos[e.i].pantalla
        paneles[k].panel.orderFrontRegardless()
        if let d = try? JSONSerialization.data(withJSONObject: e.spec[e.i]), let s = String(data: d, encoding: .utf8) {
            js(k, "WSS.tramo(\(s))")
        }
        empezarFotos(k)
    }

    /// Corta lo que esté señalando (llegó otro señalar o se cierra la app).
    func cortar() {
        if let e = enCurso {
            enCurso = nil
            e.fin(false)
        }
        pararFotos()
        for i in paneles.indices {
            js(i, "WSS.cortar()")
            paneles[i].panel.orderOut(nil)
        }
    }

    var ocupada: Bool { enCurso != nil }

    // MARK: fotos de los cuadros (revisión del movimiento)
    private func empezarFotos(_ k: Int) {
        guard !fotos.isEmpty else { return }
        reloj?.invalidate()
        reloj = Timer.scheduledTimer(withTimeInterval: 0.1, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self = self, k < self.paneles.count, self.foto < 400 else { return }
                let ruta = String(format: "%@_capa%03d_p%d.png", self.fotos, self.foto, k)
                self.foto += 1
                self.paneles[k].web.takeSnapshot(with: nil) { img, _ in
                    guard let img = img, let t = img.tiffRepresentation, let r = NSBitmapImageRep(data: t),
                          let png = r.representation(using: .png, properties: [:]) else { return }
                    try? png.write(to: URL(fileURLWithPath: ruta))
                }
            }
        }
    }

    private func pararFotos() {
        reloj?.invalidate()
        reloj = nil
    }
}
