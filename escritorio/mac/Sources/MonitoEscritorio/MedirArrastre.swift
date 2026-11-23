// Pruebas del arrastre (solo con --medir y WORKSPACE_MONITO_MEDIR=arrastre): un arrastre con guion, sin mover tu ratón
// ni grabar tu pantalla. La app se manda a sí misma los eventos del ratón (NSApp.sendEvent: pasan por el mismo camino que
// los de verdad, monitores incluidos) y anota, con el reloj del sistema (CACurrentMediaTime):
//   · cada evento que mandó (y dónde estaba el ratón «de prueba»),
//   · dónde dice el servidor de ventanas que están SUS ventanas (CGWindowList, cada 3 ms: solo sus marcos, ni un píxel),
//   · cada cuadro de la pantalla (su display link): dónde está el panel en ese cuadro,
//   · los atorones del hilo principal (un reloj de 2 ms que llega tarde),
//   · los cuadros de la burbuja (requestAnimationFrame: cuándo y dónde está el nido en la página),
//   · cuándo se escribe lugar.json,
// y fotos de lo que pinta el WKWebView en momentos del guion (takeSnapshot: lo suyo, nada más).
// Escribe <medir>.arrastre.json y termina. Lo analiza escritorio/mac/Pruebas/analizar_arrastre.py.
//   WORKSPACE_MONITO_ARRASTRE=misma|otra|clic|burbuja|borde   el guion (de fábrica: misma)
//   WORKSPACE_MONITO_ALFA=0                              la ventana del todo transparente (de fábrica: la de --fantasma)
//   WORKSPACE_MONITO_CALENTAR=1                          un clic antes del guion (para medir el segundo toque)
import AppKit
import QuartzCore
import WebKit

/// El ratón de las pruebas: si tiene un punto, el monito lo usa en vez del de verdad (nil fuera de las pruebas).
@MainActor
enum PruebaRaton {
    static var punto: NSPoint?
    static var boton: Bool?
    static var ahora: NSPoint { punto ?? NSEvent.mouseLocation }
    static var apretado: Bool { boton ?? (NSEvent.pressedMouseButtons & 1 != 0) }
}

@MainActor
final class MedirArrastre: NSObject {
    unowned let monito: Monito
    let archivo: String
    let guion: String
    let t0 = CACurrentMediaTime()
    var eventos: [[Any]] = []
    var cuadros: [[Double]] = []
    var atorones: [[Double]] = []
    var marcas: [[Any]] = []
    var malCG = 0
    /// cuándo tuvo el teclado el panel (el clic de una app de antes se lo quitaba a la app de enfrente)
    var teclado: [[Any]] = []
    var numero = 9000
    var enlace: CADisplayLink?
    var reloj: Timer?
    var ultimoTic = CACurrentMediaTime()
    // lo del hilo de atrás (el servidor de ventanas y lugar.json)
    nonisolated(unsafe) var ventanas: [[Double]] = []
    nonisolated(unsafe) var escrituras: [Double] = []
    let candado = NSLock()
    var muestreo: DispatchSourceTimer?

    init(monito: Monito, archivo: String) {
        self.monito = monito
        self.archivo = archivo
        self.guion = ProcessInfo.processInfo.environment["WORKSPACE_MONITO_ARRASTRE"] ?? "misma"
        super.init()
    }

    func t() -> Double { CACurrentMediaTime() - t0 }
    func marca(_ s: String) { marcas.append([t(), s]) }

    // MARK: lo que se anota
    func empezarAnotar() {
        // el servidor de ventanas: los marcos de las ventanas de esta app que están en pantalla
        let pid = getpid(), lugar = (monito.carpetaEstado as NSString).appendingPathComponent("lugar.json")
        let q = DispatchQueue(label: "workspace.monito.arrastre", qos: .userInteractive)
        let s = DispatchSource.makeTimerSource(queue: q)
        func cuando(_ r: String) -> Double {
            var st = stat()
            return stat(r, &st) == 0 ? Double(st.st_mtimespec.tv_sec) + Double(st.st_mtimespec.tv_nsec) / 1e9 : 0
        }
        var antes = "", mtime = cuando(lugar)          // 0: todavía no existe (crearlo también cuenta)
        let base = t0
        s.schedule(deadline: .now(), repeating: .milliseconds(3), leeway: .microseconds(200))
        s.setEventHandler { [weak self] in
            guard let self = self else { return }
            let ahora = CACurrentMediaTime() - base
            if let l = CGWindowListCopyWindowInfo([.optionOnScreenOnly], kCGNullWindowID) as? [[String: Any]] {
                var fila: [Double] = []
                for w in l where (w[kCGWindowOwnerPID as String] as? Int32) == pid {
                    guard let b = w[kCGWindowBounds as String] as? [String: Double] else { continue }
                    let n = Double((w[kCGWindowNumber as String] as? Int) ?? 0)
                    let a = (w[kCGWindowAlpha as String] as? Double) ?? 1
                    fila += [n, b["X"] ?? 0, b["Y"] ?? 0, b["Width"] ?? 0, b["Height"] ?? 0, a]
                }
                let k = fila.map { String(Int($0 * 10)) }.joined(separator: ",")
                if k != antes {
                    antes = k
                    self.candado.lock(); self.ventanas.append([ahora] + fila); self.candado.unlock()
                }
            }
            let m = cuando(lugar)
            if m != mtime {
                mtime = m
                let ya = CACurrentMediaTime() - base          // la hora de ESTA muestra (la de arriba es de antes de CGWindowList)
                self.candado.lock(); self.escrituras.append(ya); self.candado.unlock()
            }
        }
        s.resume()
        muestreo = s
        // cada cuadro de la pantalla del panel
        let e = monito.panel.displayLink(target: self, selector: #selector(cuadro(_:)))
        e.add(to: .main, forMode: .common)
        enlace = e
        // atorones del hilo principal
        let r = Timer(timeInterval: 0.002, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated {
                guard let self = self else { return }
                let a = CACurrentMediaTime()
                if a - self.ultimoTic > 0.008 { self.atorones.append([self.ultimoTic - self.t0, (a - self.ultimoTic) * 1000]) }
                self.ultimoTic = a
            }
        }
        RunLoop.main.add(r, forMode: .common)
        reloj = r
        // los cuadros de la burbuja: cuándo y dónde está su nido (y si está levantado / de qué lado)
        monito.web.evaluateJavaScript("""
        (function(){ window.__cuadros = []; var t0 = performance.timeOrigin;
          function c(ts){ var n = document.querySelector('.wsm-nido'), r = n ? n.getBoundingClientRect() : {left:0,top:0,width:0,height:0};
            var g = document.querySelector('.wsm-globo'), gr = g && !g.hidden && g.offsetParent ? g.getBoundingClientRect() : null;
            var raiz = document.querySelector('.wsm'), cl = raiz ? raiz.className : '';
            var ba = document.querySelector('.wsm-barra'); if (ba && !ba.hidden && ba.offsetParent) cl += ' ·barra';
            var tr = n ? getComputedStyle(n).transform : '';
            window.__cuadros.push([t0 + ts, +r.left.toFixed(1), +r.top.toFixed(1), +r.width.toFixed(1), +r.height.toFixed(1),
              gr ? +gr.left.toFixed(1) : -1, gr ? +gr.top.toFixed(1) : -1, cl, tr]);
            if (window.__cuadros.length < 20000) requestAnimationFrame(c); }
          requestAnimationFrame(c); return Date.now(); })()
        """) { [weak self] r, _ in
            MainActor.assumeIsolated {
                guard let self = self, let ms = r as? Double else { return }
                // el reloj de la página (ms de época) contra el nuestro
                self.marcas.append([self.t(), "reloj_pagina", ms / 1000 - Date().timeIntervalSince1970])
            }
        }
    }

    @objc func cuadro(_ e: CADisplayLink) {
        let f = monito.panel.frame, w = monito.web.frame, r = PruebaRaton.punto ?? .zero
        cuadros.append([e.timestamp - t0, e.targetTimestamp - t0, t(), Double(f.minX), Double(f.minY), Double(f.width), Double(f.height),
                        Double(w.minX), Double(w.minY), Double(r.x), Double(r.y)])
    }

    // MARK: el ratón de prueba
    func mandar(_ tipo: NSEvent.EventType, _ p: NSPoint) {
        PruebaRaton.punto = p
        PruebaRaton.boton = tipo != .leftMouseUp
        guard let panel = monito.panel else { return }
        let f = panel.frame
        let enVentana = NSPoint(x: p.x - f.minX, y: p.y - f.minY)
        guard let e = NSEvent.mouseEvent(with: tipo, location: enVentana, modifierFlags: [], timestamp: ProcessInfo.processInfo.systemUptime,
                                         windowNumber: panel.windowNumber, context: nil, eventNumber: numero, clickCount: 1,
                                         pressure: tipo == .leftMouseUp ? 0 : 1) else { return }
        if let c = e.cgEvent {
            let h0 = NSScreen.screens.first?.frame.height ?? 0
            if abs(c.location.x - p.x) > 0.5 || abs((h0 - c.location.y) - p.y) > 0.5 { malCG += 1 }
        }
        let nombre = tipo == .leftMouseDown ? "abajo" : tipo == .leftMouseUp ? "arriba" : "arrastra"
        eventos.append([t(), nombre, Double(p.x), Double(p.y)])
        NSApp.sendEvent(e)
        teclado.append([t(), nombre, panel.isKeyWindow])
    }

    /// Un tramo del guion: de `a` a `b` en `ms`, con eventos a 120 Hz (como un ratón), suave al empezar y al acabar.
    func tramo(_ a: NSPoint, _ b: NSPoint, ms: Double, desde: Double) -> Double {
        let n = max(1, Int(ms / (1000.0 / 120.0)))
        for i in 1...n {
            let k = Double(i) / Double(n), s = k < 0.5 ? 2 * k * k : 1 - pow(-2 * k + 2, 2) / 2
            let p = NSPoint(x: a.x + (b.x - a.x) * s, y: a.y + (b.y - a.y) * s)
            DispatchQueue.main.asyncAfter(deadline: .now() + desde + Double(i) * ms / Double(n) / 1000) { [weak self] in
                self?.mandar(.leftMouseDragged, p)
            }
        }
        return desde + ms / 1000
    }

    func foto(_ nombre: String, en s: Double) {
        DispatchQueue.main.asyncAfter(deadline: .now() + s) { [weak self] in
            guard let self = self else { return }
            self.marca("foto " + nombre)
            self.monito.fotografiar(self.archivo + "_" + nombre + ".png")
        }
    }

    // MARK: el guion
    func correr() {
        let env = ProcessInfo.processInfo.environment
        if let a = env["WORKSPACE_MONITO_ALFA"].flatMap({ Double($0) }) { monito.panel.alphaValue = CGFloat(a) }
        let pantallas = NSScreen.screens
        let vf = pantallas[0].visibleFrame
        // un agente de prueba, de color propio, con o sin burbuja
        var arranque = "WSM.recibir({t:'agentes',agentes:[{id:'luna',n:'Luna',c:'#b9a3ff',f:'nube'}],elegido:'luna'});"
        if guion == "burbuja" {
            arranque += "WSM.s.turno={tu:'¿lo muevo?',texto:'',vivo:true};WSM.recibir({t:'respuesta',agente:'luna',texto:'Me voy contigo a donde me lleves.'});"
        }
        monito.js(arranque)
        monito.ponerEn(Lugar.deFabrica(visible: vf), animar: false)
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.4) { [weak self] in self?.arrastrar() }
    }

    func arrastrar() {
        empezarAnotar()
        let pantallas = NSScreen.screens
        let vf = pantallas[0].visibleFrame
        let n = monito.nidoActual
        let agarre = NSPoint(x: n.midX, y: n.midY + 12)
        marca("nido " + "\(Int(n.minX)),\(Int(n.minY)) lado \(monito.lado.h)/\(monito.lado.v)")
        foto("antes", en: 0.05)
        var s = 0.25
        if ProcessInfo.processInfo.environment["WORKSPACE_MONITO_CALENTAR"] == "1" {
            // un clic antes (el primero de una app de antes solo le daba el teclado al panel): mide el segundo
            DispatchQueue.main.asyncAfter(deadline: .now() + s) { [weak self] in self?.marca("calentar"); self?.mandar(.leftMouseDown, agarre) }
            DispatchQueue.main.asyncAfter(deadline: .now() + s + 0.05) { [weak self] in self?.mandar(.leftMouseUp, agarre); self?.numero += 1 }
            s += 0.45
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + s) { [weak self] in self?.mandar(.leftMouseDown, agarre) }
        s += 0.06
        var fin = agarre
        switch guion {
        case "clic":
            DispatchQueue.main.asyncAfter(deadline: .now() + s + 0.02) { [weak self] in self?.mandar(.leftMouseUp, agarre) }
            s += 0.02
        case "otra":
            let o = pantallas.count > 1 ? pantallas[1].visibleFrame : vf
            fin = NSPoint(x: o.minX + o.width * 0.35, y: o.minY + o.height * 0.55)
            s = tramo(agarre, fin, ms: 900, desde: s)
            foto("cruzando", en: s - 0.45)
        case "borde":
            // lo sueltas medio fuera: bajo la barra de menú y pasado el borde derecho de la pantalla principal (sin otra
            // pantalla ahí, o con la otra a la derecha: el resorte lo mete en la visible de la suya)
            fin = NSPoint(x: vf.maxX - 20, y: pantallas[0].frame.maxY - 6)
            s = tramo(agarre, fin, ms: 700, desde: s)
        default:   // misma, burbuja: lejos de la esquina y luego al otro lado (cambia hacia dónde abre)
            let a = NSPoint(x: vf.minX + vf.width * 0.62, y: vf.minY + vf.height * 0.40)
            s = tramo(agarre, a, ms: 500, desde: s)
            foto("levantado", en: s - 0.2)
            fin = NSPoint(x: vf.minX + vf.width * 0.25, y: vf.minY + vf.height * 0.75)
            s = tramo(a, fin, ms: 400, desde: s)
        }
        if guion != "clic" {
            s += 0.15
            let f = fin
            DispatchQueue.main.asyncAfter(deadline: .now() + s) { [weak self] in self?.mandar(.leftMouseUp, f) }
            foto("soltado", en: s + 0.08)
            foto("acomodado", en: s + 0.9)
        } else {
            foto("barra", en: s + 0.5)
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + s + 1.3) { [weak self] in self?.terminar() }
    }

    func terminar() {
        marca("fin")
        enlace?.invalidate()
        reloj?.invalidate()
        muestreo?.cancel()
        PruebaRaton.punto = nil
        PruebaRaton.boton = nil
        monito.web.evaluateJavaScript("JSON.stringify(window.__cuadros||[])") { [weak self] r, _ in
            MainActor.assumeIsolated {
                guard let self = self else { return }
                let pagina = (r as? String).flatMap { try? JSONSerialization.jsonObject(with: Data($0.utf8)) } ?? []
                self.candado.lock()
                let v = self.ventanas, w = self.escrituras
                self.candado.unlock()
                let ps = NSScreen.screens.map { s -> [String: Any] in
                    ["marco": [s.frame.minX, s.frame.minY, s.frame.width, s.frame.height],
                     "visible": [s.visibleFrame.minX, s.visibleFrame.minY, s.visibleFrame.width, s.visibleFrame.height],
                     "escala": s.backingScaleFactor, "hz": s.maximumFramesPerSecond]
                }
                let o: [String: Any] = ["guion": self.guion, "pantallas": ps, "panel": self.monito.panel.windowNumber,
                                        "eventos": self.eventos, "ventanas": v, "cuadros": self.cuadros, "atorones": self.atorones,
                                        "pagina": pagina, "escrituras": w, "marcas": self.marcas, "mal_cg": self.malCG,
                                        "alfa": Double(self.monito.panel.alphaValue), "epoca0": Date().timeIntervalSince1970 - self.t(), "teclado": self.teclado]
                if let d = try? JSONSerialization.data(withJSONObject: o) {
                    FileManager.default.createFile(atPath: self.archivo + ".arrastre.json", contents: d)
                }
                NSApp.terminate(nil)
            }
        }
    }
}
