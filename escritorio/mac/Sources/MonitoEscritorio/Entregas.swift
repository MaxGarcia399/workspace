// E1 · entregas en la burbuja (plan «Actuar y entregar», A7-a · A8-a · A10-a · A11-a): lo que hace la app nativa.
//
//   · La tarjeta de una entrega: su miniatura de verdad (QLThumbnailGenerator), la Vista rápida (QLPreviewPanel, la de
//     la barra espaciadora), Copiar el archivo, Compartir de la Mac, un correo nuevo con el archivo (tú lo envías),
//     Guardar en… y ARRASTRARLA a otra app (Mail, Slack, una carpeta): el WKWebView no puede soltar un archivo de verdad,
//     así que la app arranca el arrastre nativo desde las zonas que le marca la burbuja.
//     Solo con archivos que la página dio por buenos (dentro del cerebro del agente, /api/v2/entrega): la burbuja nunca
//     manda una ruta que la app abra por su cuenta.
//   · La tarjeta de un encargo, ARMADA AQUÍ con datos del sistema (Propuesta): lo que escribiste en la burbuja, el
//     archivo de verdad que tenías enfrente (AXDocument), la plantilla, lo que su conversación de trabajo puede hacer y
//     dónde queda. El modelo del monito solo la pide (`encargar`); nada pasa sin tu clic. Con el clic, la app lee el
//     archivo de verdad y lo manda con el encargo (una copia, a su carpeta).
//   · El chat grande (⤢, ronda 2 · bloque G): su propia ventana, que cambia de tamaño y recuerda dónde la dejaste
//     (ChatGrande.swift). Carga la misma página de la burbuja; lo que el puente dice va a las dos y lo que la app
//     contesta (una miniatura, lo que pasó con un botón) también. Solo cuando lo pides; no se cierra sola.
//   · Un enlace de la plática con «Abrir»: solo una página limpia (la regla amarilla del portero) se abre en tu
//     navegador; lo demás no se abre desde el chat: se te copia la dirección y se dice por qué.
// Nada de esto toma el teclado ni activa la app, salvo lo que tú abres (Vista rápida, Guardar en…).
import AppKit
import ApplicationServices
import Quartz
import QuickLookThumbnailing
import UniformTypeIdentifiers
import WebKit

@MainActor
final class Entregas: NSObject, NSDraggingSource, QLPreviewPanelDataSource, QLPreviewPanelDelegate {
    unowned let monito: Monito
    /// Lo que la página dio por bueno: agente+ruta → el archivo de verdad.
    private var conocidas: [String: URL] = [:]
    private var miniaturas: [URL: NSImage] = [:]
    /// Dónde se puede tomar una entrega para arrastrarla (las marca la burbuja).
    private var zonas: [ZonaArrastre] = []
    private var presion: (p: CGPoint, zona: ZonaArrastre)?
    private var monitor: Any?
    private var enVista: URL?
    private var antesDeVer: NSRunningApplication?
    private var cierreVista: NSObjectProtocol?
    /// De los eventos del puente: el nombre y el nivel de cada agente, lo último que le escribiste y su último adjunto.
    private var nombres: [String: String] = [:]
    private var niveles: [String: String] = [:]
    /// Fable v2: quién lee lo que se encarga (su motor) y si Workspace acota sus encargos a su nivel propio.
    private var motores: [String: String] = [:]
    private var acotados: [String: Bool] = [:]
    /// Fable v2 §2.1: tus últimos mensajes a cada agente (el recado de un encargo; solo lo que TÚ escribiste).
    private var recados: [String: Recado] = [:]
    private var adjuntos: [String: String] = [:]
    /// Las tarjetas de encargo que esperan tu clic (y, si la pidió el agente, su herramienta esperando).
    private struct Viva {
        var id, agente, pedido, titulo, plantilla: String
        var archivo: URL?
        var archivoRel: String
        var fin: ((Int, [String: Any]) -> Void)?
        var reloj: Timer?
    }
    private var vivas: [String: Viva] = [:]
    /// Lo que la página dijo que se CORRERÍA al abrirlo: «Abrir» lo enseña en su carpeta.
    private var ejecutables: Set<URL> = []
    /// Pruebas de punta a punta: sin ventanas ni tu portapapeles (LogicaEntregas.Resultado).
    let ensayo = Resultado.ensayo(ProcessInfo.processInfo.environment)
    /// El chat grande (⤢): su ventana (ChatGrande.swift). El panel del monito ya no crece.
    private(set) var ventana: ChatGrande!
    /// De qué página vino lo que se está atendiendo (nil: la burbuja; si no, la ventana del chat grande): de ahí salen
    /// las ventanitas del sistema (Compartir).
    var origen: WKWebView?
    /// Dónde se puede tomar una entrega para arrastrarla, en la ventana del chat grande.
    var zonasGrande: [ZonaArrastre] = []
    /// Lo último que dijo el puente de tus agentes y el que tienes elegido (la ventana lo necesita al abrir).
    private(set) var ultimosAgentes: String?
    private(set) var elegido = ""
    /// Lo que espera la herramienta `encargar` tu clic (menos que el tope de sus motores: Codex, 90 s).
    static let espera: TimeInterval = 70

    init(monito: Monito) {
        self.monito = monito
        super.init()
    }

    var tamPanel: CGSize { CGSize(width: Monito.ancho, height: Monito.alto) }

    /// A la burbuja y, si existe, a la ventana del chat grande (las dos pintan las mismas tarjetas).
    private func js(_ codigo: String) {
        monito.js(codigo)
        ventana?.js(codigo)
    }

    /// La ventana del chat grande está a la vista.
    var grandeVisible: Bool { ventana?.visible == true }
    /// Cómo lo dejaste: «grande» o «chico» (grande.json).
    var modoGrande: String { ventana?.modo ?? "chico" }
    /// Pruebas (--guion): la ventana grande de verdad (si está a la vista, cómo vuelve, dónde está y si tiene el teclado).
    var estadoGrande: String {
        let f = ventana?.panel?.frame ?? .zero
        return "grande=\(grandeVisible) modo=\(modoGrande) marco=\(Int(f.minX)),\(Int(f.minY)),\(Int(f.width)),\(Int(f.height)) tecladoGrande=\(ventana?.panel?.isKeyWindow == true)"
    }
    /// La ventana del chat grande, al frente (`ver`: [agente, encargo] que hay que enseñar adentro).
    func abrirGrande(ver: [String]? = nil) { ventana?.abrir(ver: ver) }
    /// La ventana se esconde y queda anotado cómo vuelve. Solo lo llama Monito.guardarTodo.
    func esconderGrande(vuelve modo: String) { ventana?.esconder(vuelve: modo) }

    func arrancar() {
        ventana = ChatGrande(monito: monito, entregas: self)
        monitor = NSEvent.addLocalMonitorForEvents(matching: [.leftMouseDown, .leftMouseDragged, .leftMouseUp]) { [weak self] e in
            nonisolated(unsafe) let ev = e                  // llega en el hilo principal (AppKit)
            let usado = MainActor.assumeIsolated { self?.raton(ev) ?? false }
            return usado ? nil : e
        }
    }

    private func anotar(_ d: [String: Any]) { monito.manos?.anotar(d) }

    /// La respuesta de un botón en la burbuja (WSMEntregas.hecho): qué pasó, si salió y de qué tarjeta.
    private func hecho(_ que: String, ok: Bool, agente: String, ruta: String, app: String = "") {
        js("WSMEntregas.hecho(\(Permisos.json(Resultado.hecho(que, ok: ok, agente: agente, ruta: ruta, app: app, ensayo: ensayo))))")
    }

    /// La tarjeta pidió algo de un archivo que la app todavía no conoce (la página no lo ha dado por bueno): se dice.
    private func sinRuta(_ agente: String, _ ruta: String) {
        anotar(["entrega": "sin_ruta", "archivo": (ruta as NSString).lastPathComponent])
        hecho("sin_ruta", ok: false, agente: agente, ruta: ruta)
    }

    // MARK: lo que llega del puente (antes de pintarlo)
    /// Una línea del puente → la que sigue a la burbuja (la misma, cambiada, o nil si era para la app).
    func filtrar(_ linea: String) -> String? {
        let l = filtrarLinea(linea)
        if let l = l {
            recordar(l)
            ventana?.recibir(l)                             // lo mismo, a la ventana del chat grande
        }
        return l
    }

    /// Lo que el puente dice UNA vez y no repite (los encargos de cada agente, los botones de la barra): la ventana del
    /// chat grande se abre después y lo necesita para «Te esperan» y los números de la tira.
    private var dichas: [String: String] = [:]
    private func recordar(_ linea: String) {
        guard linea.contains("\"encargos\"") || linea.contains("\"botones\""), let d = linea.data(using: .utf8),
              let o = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any], let t = o["t"] as? String,
              t == "encargos" || t == "botones" else { return }
        dichas[t == "encargos" ? "encargos|" + ((o["agente"] as? String) ?? "") : "botones"] = linea
    }
    /// En su orden: los botones y luego los encargos de cada agente.
    var paraLaVentana: [String] { dichas.keys.sorted().compactMap { dichas[$0] } }

    private func filtrarLinea(_ linea: String) -> String? {
        let marcas = ["\"t\": \"entrega\"", "\"t\": \"agentes\"", "\"t\": \"adjunto\"", "\"t\":\"entrega\""]
        guard marcas.contains(where: { linea.contains($0) }), let d = linea.data(using: .utf8),
              var o = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any], let t = o["t"] as? String else { return linea }
        switch t {
        case "agentes":
            var lista = (o["agentes"] as? [[String: Any]]) ?? []
            for (i, a) in lista.enumerated() {
                guard let id = a["id"] as? String else { continue }
                nombres[id] = (a["n"] as? String) ?? id
                if let n = a["nivel"] as? String { niveles[id] = n }
                if let m = a["motor_nombre"] as? String { motores[id] = m }
                acotados[id] = (a["encargo_acotado"] as? Bool) == true
                // lo que dice la tarjeta de «Pásaselo a…» de ese agente: las mismas piezas que la de encargo (Fable v2)
                lista[i]["encargo"] = Propuesta.nivel(niveles[id] ?? "", motor: motores[id] ?? "", acotado: acotados[id] ?? false)
                lista[i]["lo_lee"] = Propuesta.loLee(motores[id] ?? "")
            }
            o["agentes"] = lista
            if let el = o["elegido"] as? String, !el.isEmpty { elegido = el }
            guard let s = try? JSONSerialization.data(withJSONObject: o), let l = String(data: s, encoding: .utf8) else { return linea }
            ultimosAgentes = l
            return l
        case "adjunto":
            if let a = o["agente"] as? String, let r = o["ruta"] as? String, !r.isEmpty {
                adjuntos[a] = r
                monito.actuar?.leyoArchivo(r, agente: a)      // contenido ajeno en su conversación (la marca lo dice)
            }
            return linea
        case "entrega":
            guard let a = o["agente"] as? String, let r = o["ruta"] as? String else { return linea }
            if let abs = o["abs"] as? String, !abs.isEmpty {
                let u = URL(fileURLWithPath: abs)
                conocidas[Arrastre.clave(a, r)] = u
                if let act = o["actual"] as? String { conocidas[Arrastre.clave(a, act)] = u }
                if (o["ejecutable"] as? Bool) == true { ejecutables.insert(u) }
                miniatura(u, agente: a, ruta: r)
            }
            o["abs"] = nil                                 // la burbuja no necesita la ruta de la Mac
            guard let s = try? JSONSerialization.data(withJSONObject: o), let l = String(data: s, encoding: .utf8) else { return linea }
            return l
        default:
            return linea
        }
    }

    /// Lo que mandas desde la burbuja y la app solo mira (lo que escribiste: el recado de un encargo es tuyo).
    func observar(_ d: [String: Any]) {
        guard let a = d["agente"] as? String, let t = d["texto"] as? String, !t.trimmingCharacters(in: .whitespaces).isEmpty
        else { return }
        recados[a, default: Recado()].anotar(t)
    }

    // MARK: lo que pide la burbuja
    /// → true si era para la app (no va al puente).
    func atender(_ k: String, _ d: [String: Any]) -> Bool {
        let agente = (d["agente"] as? String) ?? ""
        let ruta = (d["ruta"] as? String) ?? ""
        let url = conocidas[Arrastre.clave(agente, ruta)]
        switch k {
        case "responder":
            observar(d)
            return false
        case "elegir":
            // cambiaste de agente en una de las dos páginas: la otra lo sigue (el puente solo habla del elegido)
            if !agente.isEmpty {
                elegido = agente
                let cual = "WSM.elegir(\(Permisos.json(["a": agente])).a, false)"
                if origen == nil { ventana?.js(cual) } else { monito.js(cual) }
            }
            return false
        case "abrir_enlace":
            abrirEnlace((d["url"] as? String) ?? "", agente: agente, clicDePersona: monito.clicDePersona(d))
        case "grande_estado":
            // la burbuja (al cargar) pregunta cómo lo dejaste; y si la ventana grande está a la vista ahora mismo, se
            // le dice: una burbuja recién cargada no deja una ventana huérfana ni abre otra barra encima
            monito.js("WSM.modo('\(modoGrande)')")
            if grandeVisible { monito.js("typeof WSMEntregas!=='undefined'&&WSMEntregas.grandeFuera&&WSMEntregas.grandeFuera(true,'grande')") }
        case "entrega_vista":
            guard let u = url else { sinRuta(agente, ruta); break }
            vistaRapida(u, agente: agente, ruta: ruta)
        case "entrega_copiar":
            guard let u = url else { sinRuta(agente, ruta); break }
            copiar(u, agente: agente, ruta: ruta)
        case "copiar_texto":
            let t = (d["texto"] as? String) ?? ""
            if ensayo {
                let pb = NSPasteboard(name: NSPasteboard.Name(Resultado.pizarra))
                pb.clearContents()
                let ok = pb.setString(t, forType: .string) && pb.string(forType: .string) == t
                anotar(["sistema": "copiar_texto", "letras": t.count, "ok": ok])
                hecho("copiado_texto", ok: ok, agente: agente, ruta: "")
            } else {
                let pb = NSPasteboard.general
                pb.clearContents()
                hecho("copiado_texto", ok: pb.setString(t, forType: .string), agente: agente, ruta: "")
            }
        case "entrega_compartir":
            guard let u = url else { sinRuta(agente, ruta); break }
            compartir(u, rect: d["rect"], agente: agente, ruta: ruta)
        case "entrega_correo":
            guard let u = url else { sinRuta(agente, ruta); break }
            correo(u, agente: agente, ruta: ruta)
        case "entrega_guardar":
            guard let u = url else { sinRuta(agente, ruta); break }
            guardarEn(u, agente: agente, ruta: ruta)
        case "entrega_abrir":
            // «Abrir» / «Mostrar en Finder»: lo que la página ya dio por bueno (/api/v2/entrega) lo abre la app y dice
            // con qué; lo que no conoce, por la página (/api/front/abrir: solo dentro de su cerebro), que contesta sola
            let modo = (d["modo"] as? String) == "revelar" ? "revelar" : "abrir"
            guard let u = url else {
                monito.mandarAlPuente(["op": "abrir", "agente": agente, "ruta": ruta, "modo": modo])
                break
            }
            abrir(u, revelar: modo == "revelar", agente: agente, ruta: ruta)
        case "zonas_arrastre":
            if origen == nil { zonas = ZonaArrastre.leer(d["zonas"]) } else { zonasGrande = ZonaArrastre.leer(d["zonas"]) }
        case "encargo_decidir":
            decidir((d["id"] as? String) ?? "", (d["decision"] as? String) ?? "", d)
        case "encargo_proponer":
            proponer(agente: agente, pedido: (d["pedido"] as? String) ?? "", titulo: (d["titulo"] as? String) ?? "",
                     plantilla: Plantillas.valida(d["plantilla"] as? String), adjunto: (d["archivo"] as? String) ?? "",
                     leyo: false, fin: nil)
        case "frente_adjuntar":
            frenteAdjuntar(agente)
        case "pasar_frente":
            guard let u = documentoDelFrente(), let datos = leer(u) else {
                js("WSMEntregas.hecho({que:'sin_archivo'})")
                return true
            }
            var op: [String: Any] = ["op": "pasar", "agente": agente, "a": (d["a"] as? String) ?? "",
                                     "archivo_nombre": u.lastPathComponent, "archivo_datos": datos,
                                     "ref": (d["ref"] as? String) ?? ""]
            for k in Entregas.casillas where (d[k] as? Bool) == true { op[k] = true }     // su nivel (Fable v2)
            if let n = d["nota"] as? String { op["nota"] = n }
            anotar(["entrega": "pasar", "archivo": u.lastPathComponent, "a": op["a"] ?? ""])
            monito.mandarAlPuente(op)
        case "grande":
            // ⤢ en la burbuja (o «Ver» de un toque): la ventana del chat grande. Lo demás (una burbuja de antes que lo
            // tenía junto al nido) pasa por el mismo lugar que todo: Monito.gesto.
            if (d["abierto"] as? Bool) == true { monito.gesto(.agrandar, ver: d["ver"] as? [String]) }
            else if (d["como"] as? String) == "chico" { monito.gesto(.achicar) }
            else { monito.gesto(.minimizar) }
        default:
            return false
        }
        return true
    }

    // MARK: miniatura de verdad
    private func miniatura(_ u: URL, agente: String, ruta: String) {
        let pedido = QLThumbnailGenerator.Request(fileAt: u, size: CGSize(width: 320, height: 200), scale: 2,
                                                  representationTypes: [.thumbnail, .icon])
        QLThumbnailGenerator.shared.generateBestRepresentation(for: pedido) { rep, _ in
            let img = rep?.nsImage
            let esFoto = rep?.type == .thumbnail
            DispatchQueue.main.async {
                MainActor.assumeIsolated { [weak self] in
                    guard let self = self else { return }
                    let i = img ?? NSWorkspace.shared.icon(forFile: u.path)
                    self.miniaturas[u] = i
                    guard let png = Entregas.png(i, ancho: esFoto ? 640 : 128) else { return }
                    let d: [String: Any] = ["agente": agente, "ruta": ruta, "img": "data:image/png;base64," + png,
                                            "foto": esFoto, "w": Int(i.size.width), "h": Int(i.size.height)]
                    if let j = try? JSONSerialization.data(withJSONObject: d), let s = String(data: j, encoding: .utf8) {
                        self.js("WSMEntregas.miniatura(\(s))")
                    }
                }
            }
        }
    }

    static func png(_ img: NSImage, ancho: CGFloat) -> String? {
        let w = min(ancho, max(img.size.width, 1) * 2)
        let h = w * img.size.height / max(img.size.width, 1)
        guard w >= 1, h >= 1, let rep = NSBitmapImageRep(bitmapDataPlanes: nil, pixelsWide: Int(w), pixelsHigh: Int(h),
                                                         bitsPerSample: 8, samplesPerPixel: 4, hasAlpha: true, isPlanar: false,
                                                         colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0) else { return nil }
        NSGraphicsContext.saveGraphicsState()
        NSGraphicsContext.current = NSGraphicsContext(bitmapImageRep: rep)
        img.draw(in: NSRect(x: 0, y: 0, width: w, height: h))
        NSGraphicsContext.restoreGraphicsState()
        return rep.representation(using: .png, properties: [:])?.base64EncodedString()
    }

    // MARK: Vista rápida
    /// La de la barra espaciadora. Es lo único (con Guardar en…) que activa la app: la pediste tú. Al cerrarla, el
    /// teclado vuelve a la app que tenías enfrente.
    func vistaRapida(_ u: URL, agente: String = "", ruta: String = "") {
        if ensayo {
            anotar(["sistema": "vista_rapida", "archivo": u.lastPathComponent, "ok": true])
            hecho("vista", ok: true, agente: agente, ruta: ruta)
            return
        }
        guard let ql = QLPreviewPanel.shared() else { hecho("vista", ok: false, agente: agente, ruta: ruta); return }
        enVista = u
        antesDeVer = NSWorkspace.shared.frontmostApplication.flatMap { $0.processIdentifier == getpid() ? nil : $0 }
        NSApp.activate()
        ql.dataSource = self
        ql.delegate = self
        ql.hidesOnDeactivate = false
        ql.level = NSWindow.Level(rawValue: NSWindow.Level.floating.rawValue + 1)
        ql.reloadData()
        ql.makeKeyAndOrderFront(nil)
        if cierreVista == nil {
            cierreVista = NotificationCenter.default.addObserver(forName: NSWindow.willCloseNotification, object: ql, queue: .main) { [weak self] _ in
                MainActor.assumeIsolated { self?.vistaCerrada() }
            }
        }
        anotar(["entrega": "vista_rapida", "archivo": u.lastPathComponent, "visible": ql.isVisible])
        monito.anotar("vista rápida: \(u.lastPathComponent) · visible=\(ql.isVisible) · nivel=\(ql.level.rawValue)")
        hecho("vista", ok: ql.isVisible, agente: agente, ruta: ruta)
    }

    private func vistaCerrada() {
        enVista = nil
        if let a = antesDeVer, !a.isTerminated {
            NSApp.yieldActivation(to: a)
            a.activate()
        } else {
            NSApp.deactivate()
        }
        antesDeVer = nil
    }

    nonisolated func numberOfPreviewItems(in panel: QLPreviewPanel!) -> Int {
        MainActor.assumeIsolated { enVista == nil ? 0 : 1 }
    }

    nonisolated func previewPanel(_ panel: QLPreviewPanel!, previewItemAt index: Int) -> QLPreviewItem! {
        MainActor.assumeIsolated { enVista as NSURL? }
    }

    // MARK: Compartir, Guardar en…
    /// El rectángulo del botón en la página → en el WKWebView.
    private func rectEnWeb(_ crudo: Any?) -> NSRect {
        guard let web = origen ?? monito.web else { return .zero }
        let n = ((crudo as? [Any]) ?? []).compactMap { ($0 as? NSNumber)?.doubleValue }
        guard n.count == 4 else { return NSRect(x: web.bounds.midX, y: web.bounds.midY, width: 1, height: 1) }
        let y = web.isFlipped ? n[1] : Double(web.bounds.height) - n[1] - n[3]
        return NSRect(x: n[0], y: y, width: n[2], height: n[3])
    }

    private func compartir(_ u: URL, rect: Any?, agente: String, ruta: String) {
        if ensayo {
            anotar(["sistema": "compartir", "archivo": u.lastPathComponent, "ok": true])
            hecho("compartir", ok: true, agente: agente, ruta: ruta)
            return
        }
        guard let web = origen ?? monito.web else { hecho("compartir", ok: false, agente: agente, ruta: ruta); return }
        let p = NSSharingServicePicker(items: [u])
        p.show(relativeTo: rectEnWeb(rect), of: web, preferredEdge: .minY)
        anotar(["entrega": "compartir", "archivo": u.lastPathComponent])
        hecho("compartir", ok: true, agente: agente, ruta: ruta)
    }

    /// Un correo nuevo con el archivo (lo envías tú). Sin una cuenta de correo en la Mac, se dice.
    private func correo(_ u: URL, agente: String, ruta: String) {
        let s = NSSharingService(named: .composeEmail)
        let puede = s?.canPerform(withItems: [u]) ?? false
        if ensayo {
            anotar(["sistema": "correo", "archivo": u.lastPathComponent, "ok": puede])
            hecho("correo", ok: puede, agente: agente, ruta: ruta)
            return
        }
        if puede { s?.perform(withItems: [u]) }
        anotar(["entrega": "correo", "archivo": u.lastPathComponent, "ok": puede])
        hecho("correo", ok: puede, agente: agente, ruta: ruta)
    }

    /// El archivo al portapapeles (para pegarlo en Mail, Slack o una carpeta). En ensayo, a una pizarra propia.
    private func copiar(_ u: URL, agente: String, ruta: String) {
        let pb = ensayo ? NSPasteboard(name: NSPasteboard.Name(Resultado.pizarra)) : NSPasteboard.general
        pb.clearContents()
        var ok = pb.writeObjects([u as NSURL])
        if ensayo {
            let vuelta = pb.readObjects(forClasses: [NSURL.self]) as? [URL]
            ok = ok && vuelta?.first?.standardizedFileURL == u.standardizedFileURL
            anotar(["sistema": "copiar", "archivo": u.lastPathComponent, "ok": ok])
        }
        hecho("copiado", ok: ok, agente: agente, ruta: ruta)
    }

    /// Abrir con su app de siempre (y decir con cuál) o enseñarlo en el Finder. Lo que se CORRERÍA al abrirlo (un
    /// programa, un script) se enseña en su carpeta, como en la página.
    private func abrir(_ u: URL, revelar: Bool, agente: String, ruta: String) {
        let enCarpeta = revelar || ejecutables.contains(u) || Resultado.correria(u.lastPathComponent)
        if enCarpeta {
            if ensayo { anotar(["sistema": "revelar", "archivo": u.lastPathComponent, "ok": true]) }
            else { NSWorkspace.shared.activateFileViewerSelecting([u]) }
            hecho("revelado", ok: true, agente: agente, ruta: ruta, app: "Finder")
            return
        }
        let conQue = NSWorkspace.shared.urlForApplication(toOpen: u)
        let nombre = Resultado.nombreApp(conQue?.path ?? "")
        if ensayo {
            anotar(["sistema": "abrir", "archivo": u.lastPathComponent, "app": nombre, "ok": conQue != nil])
            hecho("abierto", ok: conQue != nil, agente: agente, ruta: ruta, app: nombre)
            return
        }
        guard conQue != nil else { hecho("abierto", ok: false, agente: agente, ruta: ruta); return }
        NSWorkspace.shared.open(u, configuration: NSWorkspace.OpenConfiguration()) { [weak self] _, error in
            DispatchQueue.main.async {
                MainActor.assumeIsolated {
                    self?.anotar(["entrega": "abrir", "archivo": u.lastPathComponent, "app": nombre, "ok": error == nil])
                    self?.hecho("abierto", ok: error == nil, agente: agente, ruta: ruta, app: nombre)
                }
            }
        }
    }

    private func guardarEn(_ u: URL, agente: String, ruta: String) {
        if ensayo {
            anotar(["sistema": "guardar_en", "archivo": u.lastPathComponent, "ok": true])
            hecho("guardado", ok: true, agente: agente, ruta: ruta)
            return
        }
        let sp = NSSavePanel()
        sp.nameFieldStringValue = u.lastPathComponent
        sp.canCreateDirectories = true
        NSApp.activate()
        sp.begin { [weak self] r in
            MainActor.assumeIsolated {
                defer { NSApp.deactivate() }
                guard r == .OK, let destino = sp.url else { self?.hecho("guardar_cancelado", ok: false, agente: agente, ruta: ruta); return }
                guard destino.standardizedFileURL != u.standardizedFileURL else { self?.hecho("guardado", ok: true, agente: agente, ruta: ruta); return }
                // NSSavePanel ya preguntó si se reemplaza: una copia nueva (la entrega se queda en su carpeta)
                try? FileManager.default.removeItem(at: destino)
                let ok = (try? FileManager.default.copyItem(at: u, to: destino)) != nil
                self?.anotar(["entrega": "guardar_en", "archivo": u.lastPathComponent, "ok": ok])
                if ok { self?.hecho("guardado", ok: true, agente: agente, ruta: ruta) }
                else { self?.hecho("no_guardado", ok: false, agente: agente, ruta: ruta) }
            }
        }
    }

    // MARK: arrastrar una entrega a otra app
    /// → true si el evento fue para arrastrar una entrega (WebKit ya no lo ve).
    private func raton(_ e: NSEvent) -> Bool {
        let enGrande = ventana?.panel != nil && e.window === ventana?.panel
        guard let web = enGrande ? ventana?.web : monito.web, enGrande || e.window === monito.panel else { return false }
        let p = web.convert(e.locationInWindow, from: nil)
        let enPagina = CGPoint(x: p.x, y: web.isFlipped ? p.y : web.bounds.height - p.y)
        // el clic de una PERSONA en la ventana grande (EventoReal), con su lugar en la página: para lo que su página pida
        if enGrande, e.type == .leftMouseDown || e.type == .leftMouseUp, EventoReal.dePersona(e) { ventana?.ultimoClic = ClicReal(cuando: Date(), punto: enPagina) }
        switch e.type {
        case .leftMouseDown:
            presion = Arrastre.zona(en: enPagina, enGrande ? zonasGrande : zonas).map { (enPagina, $0) }
        case .leftMouseDragged:
            guard let pr = presion, Arrastre.empieza(desde: pr.p, ahora: enPagina) else { return false }
            presion = nil
            guard let u = conocidas[Arrastre.clave(pr.zona.agente, pr.zona.ruta)] else { return false }
            arrastrar(u, en: p, evento: e, web: web)
            return true                                 // el arrastre es nativo: WebKit no lo ve
        case .leftMouseUp:
            presion = nil
        default:
            break
        }
        return false
    }

    private func arrastrar(_ u: URL, en p: NSPoint, evento e: NSEvent, web: WKWebView) {
        let item = NSDraggingItem(pasteboardWriter: u as NSURL)
        let img = miniaturas[u] ?? NSWorkspace.shared.icon(forFile: u.path)
        let w: CGFloat = 96, h = max(24, min(96, w * img.size.height / max(img.size.width, 1)))
        item.setDraggingFrame(NSRect(x: p.x - w / 2, y: p.y - h / 2, width: w, height: h), contents: img)
        web.beginDraggingSession(with: [item], event: e, source: self)
        js("WSMEntregas.arrastrando(true)")
        anotar(["entrega": "arrastrar", "archivo": u.lastPathComponent])
    }

    nonisolated func draggingSession(_ s: NSDraggingSession, sourceOperationMaskFor c: NSDraggingContext) -> NSDragOperation {
        c == .outsideApplication ? [.copy] : []
    }

    nonisolated func draggingSession(_ s: NSDraggingSession, endedAt p: NSPoint, operation: NSDragOperation) {
        let soltado = operation != []
        DispatchQueue.main.async {
            MainActor.assumeIsolated { [weak self] in
                self?.js("WSMEntregas.arrastrando(false, \(soltado ? "true" : "false"))")
            }
        }
    }

    // MARK: el archivo de verdad que tienes enfrente
    /// El documento de la ventana que tenías enfrente al llamar al monito (AXDocument: Excel, Word, Pages, Vista
    /// Previa…). Solo con Accesibilidad; nil si no es un archivo o pasa del tope.
    func documentoDelFrente() -> URL? {
        guard Permiso.accesibilidad.concedido else { return nil }
        let pid = monito.fotoBarra?.enfrente?.pid ?? monito.ultimaVentana?.pid ?? monito.manos?.alFrente()?.processIdentifier
        guard let pid = pid else { return nil }
        let ax = AXUIElementCreateApplication(pid)
        var win: CFTypeRef?
        guard AXUIElementCopyAttributeValue(ax, kAXFocusedWindowAttribute as CFString, &win) == .success,
              let w = win, CFGetTypeID(w) == AXUIElementGetTypeID() else { return nil }
        var doc: CFTypeRef?
        AXUIElementCopyAttributeValue(w as! AXUIElement, "AXDocument" as CFString, &doc)
        guard let p = Documento.ruta(doc as? String) else { return nil }
        var dir: ObjCBool = false
        guard FileManager.default.fileExists(atPath: p, isDirectory: &dir), !dir.boolValue,
              let tam = (try? FileManager.default.attributesOfItem(atPath: p))?[.size] as? NSNumber,
              tam.intValue <= Documento.tope else { return nil }
        return URL(fileURLWithPath: p)
    }

    /// El archivo, en base64 (con tu clic: es lo que viaja a su carpeta).
    private func leer(_ u: URL) -> String? {
        guard let d = try? Data(contentsOf: u), d.count <= Documento.tope else { return nil }
        return d.base64EncodedString()
    }

    /// «Resume esto» / «Revisa el archivo» con un archivo enfrente: una copia a su carpeta (el adjunto de siempre) y la
    /// burbuja manda su pedido en cuanto llega.
    private func frenteAdjuntar(_ agente: String) {
        guard let u = documentoDelFrente(), let datos = leer(u) else {
            js("WSMEntregas.hecho({que:'sin_archivo'})")
            return
        }
        anotar(["entrega": "adjuntar_frente", "archivo": u.lastPathComponent])
        js("WSMEntregas.adjuntando(\(Permisos.json(["nombre": u.lastPathComponent])))")
        monito.mandarAlPuente(["op": "adjuntar", "agente": agente, "nombre": u.lastPathComponent, "datos": datos])
    }

    // MARK: la tarjeta de encargo (la arma la app)
    /// La pide el agente (herramienta `encargar`, con `fin`) o un botón de la barra (sin `fin`). → la burbuja la pinta.
    func proponer(agente: String, pedido: String, titulo: String, plantilla: String, adjunto: String, leyo: Bool,
                  fin: ((Int, [String: Any]) -> Void)?) {
        let lo = pedido.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? (recados[agente]?.texto() ?? "") : pedido
        guard !agente.isEmpty, !lo.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            fin?(200, ["ok": false, "texto": "No sé qué te pidió el socio: pregúntale en una línea qué quiere que hagas."])
            return
        }
        let id = "p" + UUID().uuidString.replacingOccurrences(of: "-", with: "").prefix(12).lowercased()
        var archivo: URL? = nil, rel = ""
        if !adjunto.isEmpty { rel = adjunto } else if let u = documentoDelFrente() { archivo = u }
        else if let a = adjuntos[agente], fin != nil { rel = a }
        let casa = NSHomeDirectory()
        let lleva: (nombre: String, donde: String)? = archivo.map { ($0.lastPathComponent, Documento.donde($0.path, casa: casa)) }
            ?? (rel.isEmpty ? nil : ((rel as NSString).lastPathComponent, "ya está en su carpeta"))
        var v = Viva(id: id, agente: agente, pedido: lo, titulo: titulo, plantilla: plantilla, archivo: archivo,
                     archivoRel: rel, fin: fin, reloj: nil)
        if fin != nil {
            v.reloj = Timer.scheduledTimer(withTimeInterval: Entregas.espera, repeats: false) { [weak self] _ in
                MainActor.assumeIsolated { self?.soltarHerramienta(id, "tiempo") }
            }
        }
        vivas[id] = v
        let t = Propuesta.tarjeta(id: id, agente: agente, nombre: nombres[agente] ?? agente, pedido: lo, titulo: titulo,
                                  plantilla: plantilla, archivo: lleva, nivel: niveles[agente] ?? "",
                                  motor: motores[agente] ?? "", acotado: acotados[agente] ?? false, leyo: leyo)
        anotar(["encargo": "propuesto", "agente": agente, "de": fin == nil ? "boton" : "agente",
                "archivo": lleva?.nombre ?? "", "plantilla": plantilla])
        if let j = try? JSONSerialization.data(withJSONObject: t), let s = String(data: j, encoding: .utf8) {
            js("WSMEntregas.propuesta(\(s))")
        }
    }

    /// La herramienta `encargar` del agente (escritorio/manos_mcp.py), ya con el candado del turno revisado.
    func encargar(_ args: [String: Any], leyo: Bool, _ fin: @escaping (Int, [String: Any]) -> Void) {
        guard let agente = monito.turno?.agente, !agente.isEmpty else {
            fin(200, ["ok": false, "texto": "Ahora no hay un turno del monito abierto."])
            return
        }
        let titulo = Texto.limpio(args["titulo"] as? String, tope: 80) ?? ""
        proponer(agente: agente, pedido: "", titulo: titulo, plantilla: Plantillas.valida(args["plantilla"] as? String),
                 adjunto: "", leyo: leyo, fin: fin)
    }

    private func soltarHerramienta(_ id: String, _ decision: String) {
        guard var v = vivas[id], let fin = v.fin else { return }
        v.reloj?.invalidate()
        v.reloj = nil
        v.fin = nil
        vivas[id] = v
        fin(200, ["ok": true, "texto": Decision.texto(decision)])     // decidir (o no todavía) no es un error
    }

    /// Las casillas del nivel de un encargo (Fable v2): solo como sí/no, solo si el socio las marcó.
    static let casillas = ["comandos", "internet", "como_pagina"]

    /// Tu clic en la tarjeta: Encargar (la app lee el archivo de verdad y lo manda con el encargo, con el nivel que
    /// marcaste), Mejor aquí, corto, o No.
    private func decidir(_ id: String, _ decision: String, _ d: [String: Any] = [:]) {
        guard let v = vivas[id], ["encargar", "aqui", "no"].contains(decision) else { return }
        let esperaba = v.fin != nil
        anotar(["encargo": decision, "agente": v.agente, "de": esperaba ? "agente" : "boton",
                "nivel": Entregas.casillas.filter { (d[$0] as? Bool) == true }.joined(separator: ",")])
        if decision == "encargar" {
            // lo que dejaste escrito en la tarjeta (Fable v2 §2.1); vacío, no se encarga
            let editado = (d["pedido"] as? String).map { String($0.trimmingCharacters(in: .whitespacesAndNewlines).prefix(Recado.tope)) }
            let pedido = editado ?? v.pedido
            guard !pedido.isEmpty else { return }
            recados[v.agente]?.vaciar()
            var op: [String: Any] = ["op": "encargar", "agente": v.agente, "pedido": pedido, "ref": id]
            for k in Entregas.casillas where (d[k] as? Bool) == true { op[k] = true }
            if !v.titulo.isEmpty { op["titulo"] = v.titulo }
            if !v.plantilla.isEmpty { op["plantilla"] = v.plantilla }
            if let u = v.archivo {
                guard let datos = leer(u) else {
                    js("WSMEntregas.hecho({que:'sin_archivo', id:'\(id)'})")
                    return
                }
                op["archivo_nombre"] = u.lastPathComponent
                op["archivo_datos"] = datos
            } else if !v.archivoRel.isEmpty {
                op["archivo"] = v.archivoRel
            }
            monito.mandarAlPuente(op)
        }
        soltarHerramienta(id, decision)
        vivas[id] = nil
        js("WSMEntregas.decidido({id:'\(id)', decision:'\(decision)', esperaba:\(esperaba ? "true" : "false")})")
    }

    // MARK: un enlace de la plática («Abrir»)
    /// Tu clic en «Abrir» junto a una dirección que escribió el agente. Solo se abre una página limpia (http/https, a un
    /// sitio con nombre, sin datos: la regla amarilla del portero); lo demás NO se abre desde el chat: se te copia la
    /// dirección y se dice por qué (una dirección con datos puede llevarse lo que el agente leyó). Lo que pasó vuelve a
    /// la plática en una línea ({t: "enlace"}).
    /// M-5 · «Abrir» en un enlace del chat pasa por el PORTERO, como cualquier otra apertura (Actuar.abrirEnlaceDelChat):
    /// una página limpia y sin nada leído se abre con tu clic (un clic de persona sobre ese botón); si el agente leyó
    /// algo, lleva datos o es un sitio nuevo, sale SU ficha junto al monito (coral: se sostiene, con la dirección entera
    /// y lo que leyó); lo rojo no se abre. Queda en la bitácora del portero. Ya no te pisa el portapapeles.
    private func abrirEnlace(_ crudo: String, agente: String, clicDePersona: Bool) {
        let url = crudo.trimmingCharacters(in: .whitespacesAndNewlines)
        func decir(_ ok: Bool, _ t: String) { js("WSM.recibir(\(Permisos.json(["t": "enlace", "ok": ok, "texto": t])))") }
        let sitio = Destino.host(url) ?? "esa dirección"
        guard let a = monito.actuar else { decir(false, "No la abrí: todavía no estoy listo."); return }
        a.abrirEnlaceDelChat(url, agente: agente, clicDePersona: clicDePersona, ensayoDelSistema: ensayo) { [weak self] ok, texto in
            self?.anotar(["enlace": ok ? "abrir" : "no_abierto", "sitio": sitio, "ok": ok])
            decir(ok, texto)
        }
    }
}
