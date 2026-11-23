// Actuar: el camino de `actuar` en la app.
//   manos_mcp → /v1/actuar (con el candado del turno) → la app lee el destino REAL (por accesibilidad, la ventana que
//   tenías enfrente al llamar al monito: su app, su ventana, su página, el rol y el nombre del elemento; para abrir, lo
//   que se abriría según el sistema: la app instalada, la ruta real, la app que lo abriría) → el portero
//   (Seguridad.swift) lo clasifica y decide → su FICHA en la bandeja pegada al monito (Bandeja.swift; ronda 2: ya no una
//   tarjeta junto al mouse) → justo antes de hacerlo, se vuelve a leer el destino y el OK se gasta una vez →
//     · A1, primera parte (DE VERDAD, solo para el agente que tiene prendido «Puede hacer cosas en mi Mac»; de fábrica,
//       ninguno): ABRIR (la mano de Hacer.swift): en segundo plano, sin quitarte el foco; un aviso tranquilo con
//       «Cerrar» si se puede deshacer (y si no, lo dice); «a la vista», al frente y el monito vuela a su ventana. Lo
//       demás (escribir, llenar, apretar, mover…), te lo enseña. La confianza, congelada hasta A3.
//     · «ensayo» (A0, solo con --actuar ensayo): no se hace nada; un aviso tranquilo con Deshacer y, si lo pides, el
//       monito te enseña dónde.
// También: la marca de lo que leyó en el turno (para la tarjeta y la confianza), los vetados de «no mirar» para ver y
// leer, no señalar contraseñas ni avisos de permisos, el menú (confianzas de hoy, vetados, «Puede tomar mi mouse»,
// cómo hace las cosas), lo que guarda en <estado>/escritorio (vetados.json, ajustes.json, la copia de las confianzas y
// acciones/bitacora.jsonl, 30 días) y la tarjeta de Automatización (Apple Events) para cuando una acción la necesite.
// Nada de esto pide permisos al arrancar.
//
// Ronda 2 (fichas):
//   · Nada vence a los 40 ni a los 75 s. Si no contestas en `ausenteA`, al agente se le dice «tu socio no está: quedó
//     pendiente» (para que cierre su turno) y la ficha SE QUEDA con el pedido exacto guardado (Despues). Tu clic,
//     cuando vuelvas, lo hace la app directo, sin despertar al agente: se vuelve a leer el destino, el portero lo
//     vuelve a clasificar con lo de HOY y vale una vez. Lo que dependía de la pantalla caduca («Ya pasó»).
//   · «Puede hacer cosas en mi Mac» se prende UNA vez para todos tus agentes (PuedeActuar) y se apaga por agente. La
//     primera vez es UNA sola ficha (prender + hacer), no dos.
//   · Un clic en el monito enseña las fichas; ya no para nada. Parar: su botón rojo (mientras algo se hace) y Esc Esc.
//   · «No me preguntes para …» (H-2): la casilla de la ficha, la oferta al tercer OK y el menú «Lo que hace sin preguntar».
import AppKit
import ApplicationServices
import AXorcist

@MainActor
final class Actuar: NSObject, NSMenuDelegate {
    unowned let monito: Monito
    let portero: Portero
    let carpeta: String
    /// A0: --actuar ensayo (nada se hace de verdad, para todos los agentes). Sin él, lo de verdad lo prende cada agente.
    let ensayo: Bool
    /// A1 · «Puede hacer cosas en mi Mac» (E3-b): una vez para todos tus agentes; se apaga por agente. De fábrica, nadie:
    /// lo prendes en la primera ficha o en el menú de Compañero y se guarda en ajustes.json (que ningún agente lee ni escribe).
    private(set) var puede = PuedeActuar()
    /// El sonido suave de las fichas (apagado de fábrica); la bandeja lo lee de aquí.
    private(set) var ajustesBandeja = AjustesBandeja()
    /// Lo que dice manos.json: «ensayo» o «amarillo» (A1). Con «amarillo», las manos le ofrecen `actuar` a cada agente:
    /// al que puede, de verdad; al que no, «apagado» (si lo llama, la app le enseña al socio la ficha de la primera vez).
    var etapa: String { ensayo ? Etapa.ensayo.rawValue : Etapa.amarillo.rawValue }
    /// Los agentes que pueden (para manos.json: manos_mcp solo le ofrece `actuar` al del turno si está aquí).
    var agentesQuePueden: [String] { ensayo ? [] : puede.lista(conocidos: agentes.map { $0.id }) }
    /// Si el pánico llega mientras la mano abre algo, lo que abrió se cierra (y no se avisa como hecho).
    private var generacion = 0
    /// Una ficha del portero: su pedido exacto y, mientras el agente espera la respuesta, su `fin`.
    private struct Espera {
        var tarjeta: Tarjeta?
        var ficha: Ficha
        var pedido: PedidoAccion
        var args: [String: Any]
        var quien: Llamador
        var fin: ((Int, [String: Any]) -> Void)?
        var primera: Bool
        var base: FichaBandeja
        var desde: Date
    }
    private var esperas: [String: Espera] = [:]
    /// Lo que quedó para después (el pedido exacto de cada ficha) y lo aprobado mientras otro agente tenía su turno.
    private var despues = Despues()
    private var enCola: [String] = []
    private var relojFichas: Timer?
    /// Sin tu clic en este rato, el agente deja de esperar (antes de que sus manos se cansen: manos_mcp, 130 s) y la
    /// ficha se queda para después.
    static let ausenteA: TimeInterval = 60
    static let textoAusente = "Tu socio no está frente a su compu: no contestó. Quedó PENDIENTE en una ficha junto al monito (no lo negó). "
        + "Si la aprueba cuando vuelva, lo hace la app directo: tú no tienes que volver a pedirlo ni intentarlo por otro camino. "
        + "Termina tu turno con un resumen de una frase que diga que eso quedó esperándolo."
    let esc = EscDeEmergencia()
    var banda: BandaEnVivo?
    private var enCurso = 0
    /// Los agentes de la burbuja (para el menú): id → nombre
    var agentes: [(id: String, nombre: String)] = []
    /// Lo hecho (o, en ensayo, «lo que se habría hecho»): id → para su Deshacer (y lo que abrió de verdad, para cerrarlo)
    private struct HechoAviso {
        var texto: String
        var ensayo: Bool
        var marco: CGRect?
        var abierto: Abierto? = nil
    }
    private var hechos: [String: HechoAviso] = [:]
    private let menuSeguridad = NSMenu(title: "Seguridad para actuar")
    private let menuPuede = NSMenu(title: "Puede hacer cosas en mi Mac")
    private let menuRecordado = NSMenu(title: "Lo que hace sin preguntar")
    #if PERSONA_DE_PRUEBA
    private var personaDePruebaReloj: Timer?
    #endif

    init(monito: Monito, carpeta: String, etapa: String) {
        self.monito = monito
        self.carpeta = carpeta
        ensayo = etapa == Etapa.ensayo.rawValue
        // en ensayo nada se hace de verdad; si no, A1 (lo que la mano ya hace de verdad), para el agente que puede
        portero = Portero(etapa: ensayo ? .ensayo : .amarillo)
        super.init()
        esc.alPanico = { [weak self] in self?.panico("Esc Esc") }
        cargar()
        #if PERSONA_DE_PRUEBA
        personaDePruebaArrancar()
        #endif
    }

    /// ¿Algún agente puede actuar (o el ensayo está prendido)? Para la burbuja y el menú.
    var prendido: Bool { ensayo || puede.alguno }
    /// ¿Este agente puede actuar? (el ensayo vale para todos; lo de verdad, solo si lo prendiste para él)
    func prendido(para a: String) -> Bool { ensayo || puede.puede(a) }
    /// ¿Algo se está HACIENDO ahora? (la mano abriendo algo o la banda en vivo): entonces sale el botón rojo «Parar» y
    /// Esc Esc lo para. Una ficha que espera tu clic NO es «en vuelo» (E2-a: un clic en el monito ya no cancela nada).
    var enVuelo: Bool { enCurso > 0 || banda != nil }
    /// ¿Un agente espera ahora mismo la respuesta de una ficha?
    var esperandoClic: Bool { trabajoEsperando || esperas.values.contains { $0.fin != nil } }
    /// Carril 6 (manos de trabajo): su ficha de elegir o de varios renglones está esperando tu toque (Trabajo.swift).
    var trabajoEsperando = false

    // MARK: lo que guarda (en <estado>/escritorio, 600; en lo prohibido de leer para los agentes)

    private func ruta(_ n: String) -> String { (carpeta as NSString).appendingPathComponent(n) }

    private func leerJSON(_ n: String) -> Any? {
        guard let d = FileManager.default.contents(atPath: ruta(n)) else { return nil }
        return try? JSONSerialization.jsonObject(with: d)
    }

    private func escribirJSON(_ n: String, _ o: Any) {
        guard JSONSerialization.isValidJSONObject(o), let d = try? JSONSerialization.data(withJSONObject: o, options: [.sortedKeys, .prettyPrinted]) else { return }
        try? FileManager.default.createDirectory(atPath: carpeta, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let r = ruta(n), tmp = r + ".\(getpid()).tmp"
        FileManager.default.createFile(atPath: tmp, contents: d, attributes: [.posixPermissions: 0o600])
        chmod(tmp, 0o600)
        if rename(tmp, r) != 0 { unlink(tmp) }
    }

    /// Al arrancar: tus vetados (un archivo solo SUMA) y tus ajustes. Las confianzas NO se leen de un archivo: viven en
    /// la memoria de la app y se caen al cerrarla (así ningún programa se puede dar una escribiendo el archivo).
    private func cargar() {
        if let o = leerJSON("vetados.json") as? [String: Any], let l = o["propios"] as? [[String: Any]] {
            _ = portero.vetados.sumarDeArchivo(l)
        }
        // lo que leyó cada agente en su conversación (la marca dura la conversación, no el turno: Fable v2 §1.4)
        if let o = leerJSON(BitacoraAcciones.carpeta + "/lecturas.json") as? [String: Any], let l = o["agentes"] as? [String: [[String: Any]]] {
            portero.cargarLecturas(l.mapValues { Lecturas.deJSON($0) })
        }
        if let o = leerJSON("ajustes.json") as? [String: Any] {
            // «Puede hacer cosas en mi Mac»: solo lo que tú prendiste (de fábrica, nadie). Lo de antes (por agente) sigue
            // valiendo para esos agentes y para nadie más.
            puede = PuedeActuar.deJSON(o)
            ajustesBandeja = AjustesBandeja.deJSON(o)
        }
        if let o = leerJSON("ajustes.json") as? [String: Any], let a = o["agentes"] as? [String: [String: String]] {
            for (k, v) in a {
                if let m = v["modo"].flatMap(Modo.init(rawValue:)), m != .conTuCursor { portero.modos[k] = m }
                // «preguntando» solo hace que te PREGUNTE cada vez (y con tu cursor no existe en A0)
                if let r = v["mouse"].flatMap(MouseAgente.init(rawValue:)) { portero.mouse[k] = r }
            }
        }
        guardarConfianzas()
        // ronda 2 (H-2): lo que el socio recordó («no me preguntes…»); el portero avisa cuando cambia y aquí se guarda
        let rec = ruta(AlmacenRecordados.archivo)
        portero.recordados = AlmacenRecordados.leer(rec)
        portero.alCambiarRecordados = { [weak portero] in if let p = portero { AlmacenRecordados.escribir(p.recordados, rec) } }
    }

    /// acciones/lecturas.json (600, en lo prohibido de leer): solo la app lo escribe; al abrir solo SUMA.
    private func guardarLecturas() {
        try? FileManager.default.createDirectory(atPath: ruta(BitacoraAcciones.carpeta), withIntermediateDirectories: true,
                                                 attributes: [.posixPermissions: 0o700])
        escribirJSON(BitacoraAcciones.carpeta + "/lecturas.json",
                     ["version": 1, "agentes": portero.lecturasGuardables().mapValues { $0.json() }])
    }

    private func guardarVetados() { escribirJSON("vetados.json", ["version": 1, "propios": portero.vetados.json()]) }

    private func guardarAjustes() {
        var a: [String: [String: String]] = [:]
        for (k, m) in portero.modos { a[k, default: [:]]["modo"] = m.rawValue }
        for (k, m) in portero.mouse { a[k, default: [:]]["mouse"] = m.rawValue }
        for k in puede.solo { a[k, default: [:]]["actuar"] = "si" }
        for k in puede.apagados { a[k, default: [:]]["actuar"] = "no" }
        escribirJSON("ajustes.json", ["version": 2, "agentes": a, "actuar_todos": puede.todos, "sonido_fichas": ajustesBandeja.sonido])
    }

    /// Una copia para verlas (la de verdad es la de la memoria de la app).
    private func guardarConfianzas() {
        escribirJSON("confianzas.json", ["version": 1, "nota": "Copia para verlas: las de verdad viven en Compañero abierto y se caen al cerrarlo.",
                                         "confianzas": portero.confianzas.lista.map { $0.json() }])
    }

    /// Lo nuevo del portero a la bitácora de acciones (acciones/bitacora.jsonl, 600), con quién lo pidió.
    func volcar(_ quien: Llamador? = nil) {
        guard !portero.registro.isEmpty else { return }
        let dir = ruta(BitacoraAcciones.carpeta)
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let b = (dir as NSString).appendingPathComponent(BitacoraAcciones.archivo)
        if !FileManager.default.fileExists(atPath: b) { FileManager.default.createFile(atPath: b, contents: nil, attributes: [.posixPermissions: 0o600]) }
        guard let h = FileHandle(forWritingAtPath: b) else { portero.registro = []; return }
        h.seekToEndOfFile()
        for var o in portero.registro {
            if let q = quien { o["quien"] = ["pid": q.pid.map { Int($0) } ?? -1, "proceso": q.proceso] }
            if JSONSerialization.isValidJSONObject(o), let d = try? JSONSerialization.data(withJSONObject: o, options: [.sortedKeys]) {
                h.write(d + Data("\n".utf8))
            }
        }
        try? h.close()
        portero.registro = []
    }

    /// Deja en la bitácora de acciones solo los últimos 30 días.
    func limpiar(ahora: Date = Date()) {
        let b = (ruta(BitacoraAcciones.carpeta) as NSString).appendingPathComponent(BitacoraAcciones.archivo)
        guard let s = try? String(contentsOfFile: b, encoding: .utf8) else { return }
        let lineas = s.components(separatedBy: "\n")
        let quedan = Limpieza.vigentes(lineas, ahora: ahora, dias: BitacoraAcciones.dias)
        if quedan.count != lineas.filter({ !$0.isEmpty }).count {
            try? (quedan.joined(separator: "\n") + "\n").write(toFile: b, atomically: true, encoding: .utf8)
            chmod(b, 0o600)
        }
    }

    // MARK: el turno y lo que leyó

    func abrirTurno(_ id: String, agente: String, foto: FotoDelMomento?) {
        portero.abrirTurno(id, agente: agente)
        if let f = foto, f.seleccion != nil {     // tu mensaje llevó una selección: también es leer tu pantalla
            portero.leyo(Fuente(app: f.app, bundle: f.bundle, ventana: f.ventana, sitio: Destino.host(f.url), tipo: "seleccion"))
            guardarLecturas()
        }
        // lo que leyó antes en su conversación sigue en su cabeza: la burbuja lo vuelve a marcar (también tras reabrir)
        if let f = portero.lecturas.fuentes.first {
            monito.jsManos("WSM.leyo(\(Permisos.json(["app": f.esArchivo ? f.texto : f.app, "agente": agente, "ajeno": f.esArchivo])))")
        }
        limpiar()
    }

    func cerrarTurno() {
        // lo que esperaba tu clic NO se pierde: su ficha se queda para después (P2-b); el agente ya no espera
        for (id, e) in esperas where e.fin != nil {
            dejarParaDespues(id, "Se acabó el turno mientras esperaba al socio: no lo hice. Quedó pendiente en una ficha junto al monito; "
                             + "si la aprueba, lo hace la app directo.")
        }
        portero.cerrarTurno()
        volcar()
        aflojar()
        // lo que aprobaste mientras otro agente tenía su turno: ahora
        let cola = enCola
        enCola = []
        for id in cola { if let e = esperas[id] { aprobarDespues(id, e, casilla: false) } }
    }

    /// Las manos leyeron la ventana del turno (leer_ventana, ver_pantalla o lo de enfrente con datos).
    func leyo(tipo: String) {
        let d = destinoVentana()
        portero.leyo(Fuente(app: d.app, bundle: d.bundle, ventana: d.ventana, sitio: d.sitio, tipo: tipo))
        guardarLecturas()
    }

    /// Contenido ajeno en su conversación: un archivo que viajó a su carpeta y el monito lee (lo soltaste, «Resume esto»).
    func leyoArchivo(_ nombre: String, agente: String) {
        portero.leyo(Fuente.archivo(nombre), agente: agente)
        guardarLecturas()
        monito.jsManos("WSM.leyo(\(Permisos.json(["app": Fuente.archivo(nombre).texto, "agente": agente, "ajeno": true])))")
    }

    /// Ver y leer: si la ventana del turno está vetada para mirar, la frase; si no, nil.
    func noMirar() -> String? {
        let d = destinoVentana()
        guard let v = portero.vetados.noMirar(d) else { return nil }
        portero.registro.append(["cuando": ISO8601DateFormatter().string(from: Date()), "tipo": "mirar", "resultado": "negado",
                                 "app": d.app, "bundle": d.bundle, "sitio": d.sitio ?? "", "motivo": v.nombre + " (vetado)"])
        volcar()
        return "\(v.nombre) está en los vetados del socio («no mirar»): no la miro. Dile que, si quiere, la quite en el menú de Compañero."
    }

    /// Señalar: nunca contraseñas, avisos de permisos ni la tarjeta del monito. nil si se puede.
    func noSenalar(_ el: AXUIElement) -> String? {
        Clasificador.puedeSenalar(Actuar.destino(de: el, base: destinoVentana()), vetados: portero.vetados)
    }

    // MARK: lo que dice el sistema (accesibilidad), nunca el modelo

    static func atributo(_ el: AXUIElement, _ k: String) -> CFTypeRef? {
        var v: CFTypeRef?
        return AXUIElementCopyAttributeValue(el, k as CFString, &v) == .success ? v : nil
    }

    static func cadena(_ el: AXUIElement, _ k: String) -> String? {
        guard let v = atributo(el, k) else { return nil }
        if let s = v as? String { return Texto.limpio(s, tope: 300) }
        if let n = v as? NSNumber { return n.stringValue }
        return nil
    }

    static func marco(_ el: AXUIElement) -> CGRect? {
        guard let p = atributo(el, kAXPositionAttribute), let t = atributo(el, kAXSizeAttribute),
              CFGetTypeID(p) == AXValueGetTypeID(), CFGetTypeID(t) == AXValueGetTypeID() else { return nil }
        var o = CGPoint.zero, s = CGSize.zero
        guard AXValueGetValue(p as! AXValue, .cgPoint, &o), AXValueGetValue(t as! AXValue, .cgSize, &s) else { return nil }
        return CGRect(origin: o, size: s)
    }

    static func elemento(_ v: CFTypeRef?) -> AXUIElement? {
        guard let v = v, CFGetTypeID(v) == AXUIElementGetTypeID() else { return nil }
        return (v as! AXUIElement)
    }

    /// El destino de un elemento, con lo que dice el sistema: su rol, su nombre, su valor, su lugar, su ventana (título y
    /// número), si está en una hoja o un diálogo, y su página (la de `base`, la ventana del turno).
    static func destino(de el: AXUIElement, base: Destino) -> Destino {
        var d = base
        var pid: pid_t = 0
        AXUIElementGetPid(el, &pid)
        if pid != 0 && pid != base.pid, let app = NSRunningApplication(processIdentifier: pid) {
            d.pid = pid
            d.bundle = app.bundleIdentifier ?? ""
            d.app = app.localizedName ?? d.bundle
            d.url = nil
        }
        d.propia = pid == getpid()
        d.rol = cadena(el, kAXRoleAttribute)
        d.subrol = cadena(el, kAXSubroleAttribute)
        d.etiqueta = cadena(el, kAXTitleAttribute) ?? cadena(el, kAXDescriptionAttribute)
            ?? cadena(el, kAXPlaceholderValueAttribute) ?? cadena(el, kAXHelpAttribute)
        if d.etiqueta == nil, let t = elemento(atributo(el, kAXTitleUIElementAttribute)) { d.etiqueta = cadena(t, kAXValueAttribute) }
        d.valor = cadena(el, kAXValueAttribute)
        d.marco = marco(el)
        // un enlace: a dónde va según el sistema (Fable v2: en la web solo el sitio es confiable, no el nombre)
        if let v = atributo(el, kAXURLAttribute), CFGetTypeID(v) == CFURLGetTypeID() { d.enlace = (v as! URL).absoluteString }
        if let w = elemento(atributo(el, kAXWindowAttribute)) {
            d.ventana = cadena(w, kAXTitleAttribute)
            var id: CGWindowID = 0
            if _AXUIElementGetWindow(w, &id) == .success { d.ventanaId = id }
        }
        // ¿dentro de una hoja o un diálogo? (los avisos y las confirmaciones)
        var p = elemento(atributo(el, kAXParentAttribute))
        var vueltas = 0
        while let x = p, vueltas < 40 {
            let r = cadena(x, kAXRoleAttribute), s = cadena(x, kAXSubroleAttribute)
            if r == "AXSheet" || s == "AXDialog" || s == "AXSystemDialog" {
                d.enDialogo = true
                d.dialogo = cadena(x, kAXTitleAttribute) ?? cadena(x, kAXDescriptionAttribute)
                    ?? (r == "AXSheet" ? "una hoja" : "un diálogo")
                break
            }
            if r == "AXApplication" { break }
            p = elemento(atributo(x, kAXParentAttribute))
            vueltas += 1
        }
        return d
    }

    /// La ruta de un archivo que se ve (una fila o un ícono de Finder), según el sistema: su AXURL, o la carpeta de su
    /// ventana (AXDocument) más su nombre. nil si no se sabe (entonces el agente tiene que dar la ruta).
    static func rutaDe(_ el: AXUIElement) -> String? {
        var x: AXUIElement? = el
        for _ in 0..<4 {
            guard let e = x else { break }
            if let v = atributo(e, kAXURLAttribute), CFGetTypeID(v) == CFURLGetTypeID() {
                let u = v as! URL
                if u.isFileURL { return u.path }
            }
            if let f = cadena(e, kAXFilenameAttribute), f.hasPrefix("/") { return f }
            x = elemento(atributo(e, kAXParentAttribute))
        }
        // la carpeta de la ventana (AXDocument) y el nombre que se ve
        guard let w = elemento(atributo(el, kAXWindowAttribute)), let doc = cadena(w, kAXDocumentAttribute),
              let carpeta = URL(string: doc), carpeta.isFileURL else { return nil }
        let nombre = cadena(el, kAXTitleAttribute) ?? cadena(el, kAXValueAttribute) ?? cadena(el, kAXDescriptionAttribute)
        guard let n = nombre, !n.contains("/") else { return nil }
        return carpeta.appendingPathComponent(n).path
    }

    /// «El archivo que tengo seleccionado en Finder»: lo lee la app por accesibilidad (solo leer) en la ventana del turno.
    /// → (ruta, nil) o (nil, la frase) · «falta_accesibilidad» si no hay permiso.
    func seleccionDeFinder(_ base: Destino) -> (String?, String?) {
        guard base.bundle == "com.apple.finder" else {
            return (nil, "No tiene Finder enfrente: pídele que seleccione el archivo en Finder y te vuelva a llamar (o dime su ruta).")
        }
        guard Permiso.accesibilidad.concedido else { return (nil, "falta_accesibilidad") }
        guard let w = ventanaAX(base) else { return (nil, "No encuentro su ventana de Finder.") }
        var cola: [(AXUIElement, Int)] = [(w, 0)], vistos = 0, sel: [AXUIElement] = []
        let tope = Date().addingTimeInterval(0.5)
        while !cola.isEmpty && vistos < 600 && Date() < tope && sel.isEmpty {
            let (e, prof) = cola.removeFirst()
            vistos += 1
            for k in [kAXSelectedRowsAttribute, kAXSelectedChildrenAttribute] {
                if let l = Actuar.atributo(e, k) as? [AXUIElement], !l.isEmpty { sel += l }
            }
            if prof < 8, let hijos = Actuar.atributo(e, kAXChildrenAttribute) as? [AXUIElement] { cola += hijos.prefix(80).map { ($0, prof + 1) } }
        }
        func rutaEn(_ el: AXUIElement, _ prof: Int) -> String? {
            if let r = Actuar.rutaDe(el), FileManager.default.fileExists(atPath: r) { return r }
            guard prof < 3, let hijos = Actuar.atributo(el, kAXChildrenAttribute) as? [AXUIElement] else { return nil }
            for h in hijos.prefix(12) { if let r = rutaEn(h, prof + 1) { return r } }
            return nil
        }
        let rutas = Array(Set(sel.prefix(20).compactMap { rutaEn($0, 0) }))
        if rutas.isEmpty { return (nil, "No veo nada seleccionado en su ventana de Finder: pídele que lo seleccione (o dime la ruta).") }
        if rutas.count > 1 { return (nil, "Tiene \(rutas.count) cosas seleccionadas en Finder: pregúntale cuál (abro una a la vez).") }
        return (rutas[0], nil)
    }

    /// La carpeta de la ventana de Finder del turno (AXDocument), o nil.
    func carpetaDeFinder(_ base: Destino) -> String? {
        guard base.bundle == "com.apple.finder", Permiso.accesibilidad.concedido, let w = ventanaAX(base),
              let doc = Actuar.atributo(w, kAXDocumentAttribute) as? String, let u = URL(string: doc), u.isFileURL else { return nil }
        return u.path
    }

    /// La ventana del turno por accesibilidad (por su número; si no, la del frente de esa app).
    private func ventanaAX(_ base: Destino) -> AXUIElement? {
        let ax = AXUIElementCreateApplication(base.pid)
        let ventanas = (Actuar.atributo(ax, kAXWindowsAttribute) as? [AXUIElement]) ?? []
        return ventanas.first { var id: CGWindowID = 0; return _AXUIElementGetWindow($0, &id) == .success && id == base.ventanaId }
            ?? Actuar.elemento(Actuar.atributo(ax, kAXFocusedWindowAttribute))
    }

    /// La ventana del turno (la que tenías enfrente al llamar al monito): su app, su título, su número y su página.
    func destinoVentana() -> Destino {
        var d = Destino()
        guard let o = monito.manos?.objetivo ?? monito.manos?.tomarEnfrente() else { return d }
        d.pid = o.pid
        d.bundle = o.bundle
        d.app = o.nombre
        d.ventanaId = o.ventana
        d.propia = o.pid == getpid()
        d.navegador = Clasificador.navegadores.contains(o.bundle)     // sin dirección legible: «sitio desconocido»
        if Permiso.accesibilidad.concedido {
            let ax = AXUIElementCreateApplication(o.pid)
            var ventanas: [AXUIElement] = []
            if let l = Actuar.atributo(ax, kAXWindowsAttribute) as? [AXUIElement] { ventanas = l }
            let w = ventanas.first { var id: CGWindowID = 0; return _AXUIElementGetWindow($0, &id) == .success && id == o.ventana }
                ?? Actuar.elemento(Actuar.atributo(ax, kAXFocusedWindowAttribute))
            if let w = w {
                d.ventana = Actuar.cadena(w, kAXTitleAttribute)
                d.url = monito.manos?.urlDe(Element(w))?.absoluteString
            }
        }
        return d
    }

    /// Los destinos de un pedido, leídos del sistema. Elementos: por número de leer_ventana, por su texto o, al escribir,
    /// el campo con el foco; siempre en la ventana del turno. Archivos: su ruta real. → (destinos, error)
    func destinos(_ p: PedidoAccion) -> ([Destino], String?) {
        let base = destinoVentana()
        guard let t = p.tipoConocido else { return ([base], nil) }
        let fm = FileManager.default
        func real(_ r: String) -> String { ((r as NSString).expandingTildeInPath as NSString).resolvingSymlinksInPath }
        // un archivo que se ve (una fila de Finder, por número de leer_ventana o por su nombre): su ruta la da el sistema
        func archivoDe(_ n: Int?, _ texto: String?) -> String? {
            guard n != nil || texto != nil, Permiso.accesibilidad.concedido, let m = monito.manos else { return nil }
            guard let el = (n.flatMap { m.leido($0) }) ?? (texto.flatMap { m.buscarLeido($0) }) else { return nil }
            return Actuar.rutaDe(el)
        }
        switch t {
        case .abrir:
            // A1: lo resuelve la mano con lo que dice el sistema (la app instalada, la ruta real, la app que lo abriría);
            // el portero lo clasifica por ESO, no por la ventana de enfrente (que no se toca)
            let (d, e): (Destino?, String?)
            if let u = p.url { (d, e) = Mano.destinoPagina(u, base: base) }
            else if let a = p.app { (d, e) = Mano.destinoApp(a, base: base) }
            else if p.seleccionado {
                let (r, er) = seleccionDeFinder(base)
                guard let r = r else { return ([], er) }
                (d, e) = Mano.destinoArchivo(r, base: base, enFinder: p.enFinder)
            } else if let r = p.ruta {
                // una ruta a medias («informe.pdf») con Finder enfrente: en la carpeta de esa ventana
                let entera = r.hasPrefix("/") || r.hasPrefix("~") ? r : carpetaDeFinder(base).map { ($0 as NSString).appendingPathComponent(r) } ?? r
                (d, e) = Mano.destinoArchivo(entera, base: base, enFinder: p.enFinder)
            } else if let r = archivoDe(p.elemento, p.texto) { (d, e) = Mano.destinoArchivo(r, base: base, enFinder: p.enFinder) }
            else { return ([], "Para abrir, di la app (app), la ruta (ruta), la dirección (url), el que tiene seleccionado en Finder (seleccionado=true) o el que se ve (su número de leer_ventana).") }
            guard let x = d else { return ([], e) }
            return ([x], nil)
        case .mover, .renombrar, .borrar:
            guard let r = p.ruta ?? archivoDe(p.elemento, p.texto) else {
                return ([], "Falta el archivo: su ruta o su número de leer_ventana.")
            }
            var d = base
            d.ruta = real(r)
            guard fm.fileExists(atPath: d.ruta!) else { return ([], "No encuentro «\(r)».") }
            if t != .borrar {
                guard let a = p.destino else { return ([], "Falta a dónde.") }
                // renombrar con solo el nombre nuevo: en la misma carpeta
                var dest = t == .renombrar && !a.contains("/") ? ((d.ruta! as NSString).deletingLastPathComponent as NSString).appendingPathComponent(a) : real(a)
                var dir: ObjCBool = false
                if fm.fileExists(atPath: dest, isDirectory: &dir), dir.boolValue { dest = (dest as NSString).appendingPathComponent((d.ruta! as NSString).lastPathComponent) }
                d.rutaDestino = dest
                d.destinoExiste = fm.fileExists(atPath: dest)
            }
            return ([d], nil)
        default:
            guard Permiso.accesibilidad.concedido, let m = monito.manos else { return ([], "falta_accesibilidad") }
            func uno(_ n: Int?, _ texto: String?) -> AXUIElement? {
                if let n = n, let el = m.leido(n) { return el }
                if let x = texto { return m.buscarLeido(x) }
                return nil
            }
            if t == .llenar {
                var out: [Destino] = []
                for c in p.campos {
                    guard let el = uno(c.elemento, c.texto) else { return ([], "No encontré el campo «\(c.texto ?? c.elemento.map(String.init) ?? "?")»: llama a leer_ventana() y usa sus números.") }
                    out.append(Actuar.destino(de: el, base: base))
                }
                return (out, nil)
            }
            var el = uno(p.elemento, p.texto)
            if el == nil, t == .escribir, p.elemento == nil, p.texto == nil {
                el = Actuar.elemento(Actuar.atributo(AXUIElementCreateApplication(base.pid), kAXFocusedUIElementAttribute))
            }
            guard let e = el else { return ([], "No encontré ese elemento en la ventana: llama a leer_ventana() y usa sus números (o su texto).") }
            return ([Actuar.destino(de: e, base: base)], nil)
        }
    }

    // MARK: /v1/actuar

    func atender(_ args: [String: Any], quien: Llamador, _ fin: @escaping (Int, [String: Any]) -> Void) {
        let agente = portero.agente
        let puedeYa = prendido(para: agente)
        if !puedeYa {
            // E5: la primera vez es UNA ficha (prender + hacer). Sin turno o sin agente no hay a quién ofrecérselo; y si
            // el socio lo APAGÓ para este agente a propósito, no se le vuelve a ofrecer.
            guard !ensayo, !agente.isEmpty, portero.turno != nil, !puede.apagado(agente) else {
                fin(200, ["ok": false, "error": "Este agente no puede hacer cosas en la Mac del socio: enséñale dónde con senalar(). "
                          + "Si él quiere, lo prende en el menú de Compañero, su carita en la barra de menú («Puede hacer cosas en mi Mac»)."])
                return
            }
        }
        let (q, e) = PedidoAccion.leer(args)
        guard let p = q else { fin(200, ["ok": false, "error": e ?? "Pedido inválido."]); return }
        if esperandoClic {
            fin(200, ["ok": false, "error": "Ya hay una ficha esperando al socio: una acción a la vez."])
            return
        }
        let (ds, err) = destinos(p)
        if err == "falta_accesibilidad" {
            monito.manos.permisos.pedir(.actuar)
            fin(200, ["ok": false, "falta": Permiso.accesibilidad.rawValue, "texto": Para.actuar.paraElAgente])
            return
        }
        if let e = err { fin(200, ["ok": false, "error": e]); return }
        let r = portero.pedir(p, destinos: ds)
        volcar(quien)
        switch r.salida {
        case .tarjeta:
            guard let t = r.tarjeta, let f = r.ficha else { fin(200, ["ok": false, "error": r.motivo]); return }
            enseñarFicha(t, f, p, args, quien, primera: !puedeYa, fin)
        case .confianza, .cero:      // .cero (ronda 2, H-2): lo que el socio recordó («no me preguntes…»): se hace ya, con su ficha verde
            if !puedeYa, let f = r.ficha {
                // lo recordado es de todos, pero este agente todavía no puede: su primera ficha (al «Sí», se vuelve a pedir)
                enseñarFicha(nil, f, p, args, quien, primera: true, fin)
            } else if let a = r.autorizacion {
                hacer(a, p, quien, modo: Modo(rawValue: p.modo ?? "") ?? portero.modo(de: agente), porConfianza: true, agente: agente, fin)
            } else { fin(200, ["ok": false, "error": r.motivo]) }
        case .senalar:
            senalarDestino(ds, r.motivo, fin)
        case .negado, .libre:
            fin(200, ["ok": r.salida == .libre, "texto": r.motivo, "color": r.color.rawValue])
        }
    }

    private func apretar() {
        enCurso += 1
        esc.armar()
    }

    private func aflojar() {
        enCurso = max(0, enCurso - 1)
        if !enVuelo { esc.soltar() }
    }

    // MARK: las fichas del portero (la bandeja pegada al monito)

    /// La ficha de un pedido: la arma la app con el veredicto del portero (TextoFicha), nunca con texto del agente. El
    /// agente espera su respuesta hasta `ausenteA`; después la ficha se queda para después.
    private func enseñarFicha(_ t: Tarjeta?, _ f: Ficha, _ p: PedidoAccion, _ args: [String: Any], _ quien: Llamador, primera: Bool,
                              _ fin: @escaping (Int, [String: Any]) -> Void) {
        let ahora = Date()
        var b = primera ? TextoFicha.primera(f, nombre: nombreDe(f.agente), color: monito.bandeja.color(f.agente), ahora: ahora)
                        : TextoFicha.dePortero(f, nombre: nombreDe(f.agente), color: monito.bandeja.color(f.agente), ahora: ahora)
        if t == nil { b.id = "p:" + UUID().uuidString.lowercased() }
        // lo que escribiría o llenaría (el correo ya lo trae entero en su detalle)
        if let t = t, f.detalleTipo != "correo" { b = TextoFicha.conValores(b, t.valores.map { (campo: $0.campo, valor: $0.valor) }) }
        let id = b.id
        esperas[id] = Espera(tarjeta: t, ficha: f, pedido: p, args: args, quien: quien, fin: fin, primera: primera, base: b, desde: ahora)
        ponerFicha(b)
        if relojFichas == nil {
            relojFichas = Timer.scheduledTimer(withTimeInterval: 0.5, repeats: true) { [weak self] _ in
                MainActor.assumeIsolated { self?.revisarFichas() }
            }
        }
        #if PERSONA_DE_PRUEBA
        if let t = t { personaDePruebaTarjeta(t) }
        #endif
    }

    private func ponerFicha(_ b: FichaBandeja) {
        let id = b.id
        monito.bandeja.poner(b) { [weak self] boton, casilla in self?.contestoFicha(id, boton, casilla: casilla) }
    }

    /// Cada medio segundo, mientras un agente espera: ¿la ficha sigue valiendo con lo que dice el sistema? ¿ya pasó el
    /// rato de esperarte?
    private func revisarFichas() {
        let ahora = Date()
        for (id, e) in esperas where e.fin != nil {
            if let t = e.tarjeta, ahora.timeIntervalSince(e.desde) < Actuar.ausenteA, let c = portero.vigente(t.id, ahora: destinos(e.pedido).0) {
                // cambió lo de enfrente: ese pedido ya no es el que viste
                var x = e
                x.fin = nil
                x.tarjeta = nil
                esperas[id] = x
                volcar(e.quien)
                e.fin?(200, ["ok": false, "texto": "Lo cancelé: \(c). Si todavía hace falta, vuelve a pedirlo."])
                ponerFicha(TextoFicha.caducada(e.base, motivo: c))
            } else if ahora.timeIntervalSince(e.desde) >= Actuar.ausenteA {
                dejarParaDespues(id, Actuar.textoAusente)
            }
        }
        if !esperandoClic { relojFichas?.invalidate(); relojFichas = nil }
    }

    /// El agente deja de esperar (no estabas, o se acabó su turno) y la ficha SE QUEDA, con su pedido exacto guardado. Lo
    /// que dependía de la pantalla no se guarda: caduca y la ficha lo dice.
    private func dejarParaDespues(_ id: String, _ texto: String) {
        guard var e = esperas[id], let fin = e.fin else { return }
        e.fin = nil
        let ds = destinos(e.pedido).0
        if let t = e.tarjeta { _ = portero.responder(t.id, "vencida", ahora: ds) }
        e.tarjeta = nil
        esperas[id] = e
        portero.registro.append(["cuando": ISO8601DateFormatter().string(from: Date()), "tipo": "ficha", "resultado": "para_despues",
                                 "agente": e.ficha.agente, "ficha": id])
        volcar(e.quien)
        fin(200, ["ok": false, "pendiente": true, "texto": texto])
        let g = PedidoGuardado(pedido: e.pedido, huellas: Huella.lote(ds, e.pedido.tipoConocido), agente: e.ficha.agente, tono: e.base.tono,
                               guardado: Date())
        if despues.guardar(id, g) {
            var b = e.primera ? e.base : TextoFicha.despues(e.base, e.ficha)
            b.estado = .despues
            ponerFicha(b)
        } else {
            ponerFicha(TextoFicha.caducada(e.base))
        }
    }

    /// Un botón de una ficha del portero (solo llega de un clic de una persona: BotonTarjeta).
    private func contestoFicha(_ id: String, _ boton: String, casilla: Bool) {
        guard let e = esperas[id] else { monito.bandeja.quitar(id); return }
        switch boton {
        case "no":
            esperas[id] = nil
            despues.olvidar(id)
            enCola.removeAll { $0 == id }
            monito.bandeja.quitar(id)
            if let fin = e.fin {
                let res = e.tarjeta.map { portero.responder($0.id, "no", ahora: destinos(e.pedido).0) }
                volcar(e.quien)
                fin(200, ["ok": false, "texto": res?.motivo ?? "El socio dijo que no. No lo vuelvas a pedir en este turno si él no lo pide."])
            } else {
                portero.registro.append(["cuando": ISO8601DateFormatter().string(from: Date()), "tipo": "ficha", "resultado": "no",
                                         "agente": e.ficha.agente, "ficha": id])
                volcar(e.quien)
            }
        case "olvidar":
            // «Olvidar lo leído»: se borra su marca y el MISMO pedido se vuelve a clasificar con lo de ahora
            let a = e.ficha.agente
            portero.olvidarLecturas(agente: a)
            guardarLecturas()
            portero.registro.append(["cuando": ISO8601DateFormatter().string(from: Date()), "tipo": "olvidar_lecturas",
                                     "resultado": "olvidado", "agente": a, "desde": "su ficha"])
            volcar(e.quien)
            monito.jsManos("WSM.olvido(\(Permisos.json(["agente": a])))")
            guard let fin = e.fin else { return }
            if let t = e.tarjeta { _ = portero.responder(t.id, "cancelada", ahora: destinos(e.pedido).0) }
            esperas[id] = nil
            monito.bandeja.quitar(id)
            atender(e.args, quien: e.quien, fin)
        case "otra_vez":
            // «Ya pasó · Pedírselo otra vez»: un mensaje nuevo al agente (lo arma la app)
            esperas[id] = nil
            monito.bandeja.quitar(id)
            monito.mandarAlPuente(["op": "mandar", "agente": e.ficha.agente, "texto": TextoFicha.otraVez(e.base), "sin_contexto": true])
        case "hazlo":
            guard monito.bandeja.ficha(id)?.estado != .caducada else { return }
            if e.fin != nil { aprobarAhora(id, e, casilla: casilla) } else { aprobarDespues(id, e, casilla: casilla) }
        default:
            break
        }
    }

    /// Tu clic con el agente esperando: el OK de siempre (se vuelve a leer el destino; vale una vez).
    private func aprobarAhora(_ id: String, _ e: Espera, casilla: Bool) {
        guard let fin = e.fin else { return }
        esperas[id] = nil
        monito.bandeja.quitar(id)
        let agente = e.ficha.agente
        // la primera vez: este mismo clic lo prende (para todos tus agentes, si dejaste su casilla) y hace lo pedido
        if e.primera { cambiarPuede(agente, true, paraTodos: casilla, desde: "su primera ficha (un clic suyo)") }
        guard let t = e.tarjeta else { atender(e.args, quien: e.quien, fin); return }      // lo recordado: ahora que puede, se hace
        let ds = destinos(e.pedido).0
        let res = portero.responder(t.id, "hazlo", recordar: !e.primera && casilla, ahora: ds)
        volcar(e.quien)
        guardarConfianzas()
        if let a = res.autorizacion {
            hacer(a, e.pedido, e.quien, modo: Modo(rawValue: e.pedido.modo ?? "") ?? t.modo, porConfianza: false, agente: agente, fin)
        } else {
            fin(200, ["ok": false, "texto": res.motivo])
        }
        if let o = res.ofrecerRecordar { ofrecerRecordar(o, agente: agente) }
    }

    /// Tu clic cuando ya nadie espera (P2-b): la app lo hace directo, sin despertar al agente. El pedido guardado sale
    /// UNA vez y solo si lo que se abriría sigue siendo lo mismo; el portero lo vuelve a clasificar con lo de hoy.
    private func aprobarDespues(_ id: String, _ e: Espera, casilla: Bool) {
        let ds = destinos(e.pedido).0
        switch despues.tomar(id, ahora: Huella.lote(ds, e.pedido.tipoConocido)) {
        case .noEsta:
            esperas[id] = nil
            monito.bandeja.quitar(id)
        case .yaPaso(let c):
            ponerFicha(TextoFicha.caducada(e.base, motivo: "ya no es lo mismo: \(c)"))
        case .hazlo(let g):
            if portero.turno != nil, portero.agente != g.agente {
                // otro agente tiene su turno: tu clic vale, se hace en cuanto termine
                despues.guardar(id, g)
                if !enCola.contains(id) { enCola.append(id) }
                var b = monito.bandeja.ficha(id) ?? e.base
                b.pie = "Dijiste que sí: lo hago en cuanto termine \(nombreDe(portero.agente))"
                ponerFicha(b)
                return
            }
            esperas[id] = nil
            monito.bandeja.quitar(id)
            if e.primera { cambiarPuede(g.agente, true, paraTodos: casilla, desde: "su primera ficha (un clic suyo)") }
            func yaNo(_ motivo: String) {
                var x = e
                x.fin = nil
                x.tarjeta = nil
                esperas[id] = x
                ponerFicha(TextoFicha.caducada(e.base, motivo: motivo))
            }
            hacerGuardado(g, destinos: ds, quien: e.quien, yaNo: yaNo)
        }
    }

    /// Un pedido guardado («aprobar después»), con tu clic y ya sin nadie esperando: el portero lo vuelve a clasificar con
    /// lo de HOY (si no hay turno, abre uno suyo «ficha-…» con ese agente y lo cierra) y, si sigue siendo de un toque,
    /// la mano lo hace. Si hoy es más delicado (coral) que cuando lo viste, no se hace: `yaNo(por qué)`.
    /// (Sin `private`: junto5. También lo usan las fichas de trabajo que se quedaron para después: Trabajo.hacerDespues.)
    /// `hecho`: cómo terminó la mano (si llegó a hacerse).
    func hacerGuardado(_ g0: PedidoGuardado, destinos ds: [Destino], quien: Llamador, yaNo: (String) -> Void,
                       hecho: ((Bool, String) -> Void)? = nil) {
        // (lo que pidió el SOCIO con su clic en un enlace del chat no depende de que el agente pueda hacer cosas: M-5)
        guard g0.delSocio || prendido(para: g0.agente) else { yaNo("ese agente ya no puede hacer cosas en tu Mac"); return }
        // junto5: un borrador guardado no trae sello; vuelve a entrar por su puerta (se arma y se sella de nuevo)
        var g = g0
        if let c = g.correo {
            guard let p = Trabajo.pedidoDeCorreo(c) else { yaNo("ya no pude armar ese borrador"); return }
            g.pedido = p
        }
        let propio = portero.turno == nil
        if propio { portero.abrirTurno("ficha-" + UUID().uuidString.lowercased().prefix(8), agente: g.agente) }
        defer { if propio { portero.cerrarTurno(); volcar(quien) } }
        let r = portero.pedir(g.pedido, destinos: ds)
        volcar(quien)
        // nadie espera: el agente no se despierta
        let mudo: (Int, [String: Any]) -> Void = { _, d in hecho?((d["ok"] as? Bool) ?? false, (d["texto"] as? String) ?? (d["error"] as? String) ?? "") }
        let modo = Modo(rawValue: g.pedido.modo ?? "") ?? portero.modo(de: g.agente)
        switch r.salida {
        case .tarjeta:
            guard let t = r.tarjeta else { yaNo(r.motivo); return }
            if r.ficha?.tono == .coral, g.tono != .coral {
                // hoy es más delicado que cuando lo viste: tu clic de antes no lo cubre
                _ = portero.responder(t.id, "cancelada", ahora: ds)
                yaNo("ahora es más delicado que cuando lo viste" + ((r.ficha?.motivo ?? "").isEmpty ? "" : ": " + (r.ficha?.motivo ?? "")))
                return
            }
            let res = portero.responder(t.id, "hazlo", ahora: ds)
            volcar(quien)
            if let a = res.autorizacion { hacer(a, g.pedido, quien, modo: modo, porConfianza: false, agente: g.agente, mudo) }
            else { yaNo(res.motivo) }
        case .cero, .confianza:
            if let a = r.autorizacion { hacer(a, g.pedido, quien, modo: modo, porConfianza: true, agente: g.agente, mudo) }
            else { yaNo(r.motivo) }
        default:
            yaNo(r.motivo)
        }
    }

    /// M-5 · «Abrir» de un enlace que el agente escribió en el chat. Lo pide el SOCIO con su clic, pero la dirección la
    /// eligió el agente: decide el portero, con lo que ese agente leyó.
    ///   · ámbar (una página limpia, nada leído en el turno) y el clic fue de una persona sobre ese botón → ese clic es
    ///     su toque: se abre (a la vista) y queda en la bitácora;
    ///   · coral (leyó algo, lleva datos, sitio nuevo…), o el clic no se pudo comprobar → su FICHA junto al monito,
    ///     guardada como «para después»: se aprueba ahí (lo coral se sostiene), con la dirección entera;
    ///   · rojo o lo que no se hace → no se abre, y se dice por qué. Nunca se copia nada al portapapeles.
    /// No pide que el agente tenga prendido «hacer cosas»: lo abre el socio, no el agente.
    func abrirEnlaceDelChat(_ url: String, agente: String, clicDePersona: Bool, ensayoDelSistema: Bool,
                            _ decir: @escaping (Bool, String) -> Void) {
        guard !agente.isEmpty else { decir(false, "No la abrí: no sé de qué agente es ese enlace."); return }
        let args: [String: Any] = ["accion": "abrir", "url": url, "modo": "a_la_vista"]
        let (q, e) = PedidoAccion.leer(args)
        guard let p = q else { decir(false, "No la abrí desde aquí: " + (e ?? "no entendí esa dirección.")); return }
        if portero.turno != nil, portero.agente != agente {
            decir(false, "Ahora es el turno de \(nombreDe(portero.agente)): tócalo otra vez cuando termine.")
            return
        }
        let (ds, err) = destinos(p)
        if let e = err { decir(false, "No la abrí desde aquí: \(e)"); return }
        let quien = Llamador(turno: portero.turno, pidDicho: getpid(), puertoDelOtro: 0)
        let propio = portero.turno == nil
        if propio { portero.abrirTurno("enlace-" + UUID().uuidString.lowercased().prefix(8), agente: agente) }
        defer { if propio { portero.cerrarTurno(); volcar(quien) } }
        let r = portero.pedir(p, destinos: ds)
        volcar(quien)
        let sitio = Destino.host(url) ?? "esa dirección"
        func hazlo(_ aut: String, porConfianza: Bool) {
            if ensayoDelSistema { _ = portero.ejecutar(aut, ahora: ds); volcar(quien); decir(true, "Abrí \(sitio) en tu navegador. (ensayo)"); return }
            hacer(aut, p, quien, modo: .aLaVista, porConfianza: porConfianza, agente: agente) { _, d in
                let ok = (d["ok"] as? Bool) ?? false
                decir(ok, ok ? "Abrí \(sitio) en tu navegador." : "No pude abrir \(sitio).")
            }
        }
        switch r.salida {
        case .tarjeta:
            guard let t = r.tarjeta, let f = r.ficha else { decir(false, "No la abrí desde aquí: \(r.motivo)"); return }
            if r.color == .amarillo, t.sostenerMs == 0, clicDePersona {
                let res = portero.responder(t.id, "hazlo", ahora: ds)
                volcar(quien)
                guardarConfianzas()
                if let aut = res.autorizacion { hazlo(aut, porConfianza: false) } else { decir(false, "No la abrí: \(res.motivo)") }
                return
            }
            // su ficha, junto al monito (lo coral se sostiene ahí; un botón de la página no lo decide)
            _ = portero.responder(t.id, "cancelada", ahora: ds)
            volcar(quien)
            // (se queda como «te necesita AHORA»: la acabas de pedir tú; no puede caer detrás de «Ver todas» · M-1)
            var b = TextoFicha.dePortero(f, nombre: nombreDe(agente), color: monito.bandeja.color(agente), ahora: Date())
            b.casilla = nil
            b.id = "p:enlace-" + UUID().uuidString.lowercased()
            b.pie = TextoFicha.piePortero + " · un enlace de su respuesta" + (f.motivo.isEmpty || b.tono != .coral ? "" : " · " + f.motivo)
            var g = PedidoGuardado(pedido: p, huellas: Huella.lote(ds, p.tipoConocido), agente: agente, tono: b.tono, guardado: Date())
            g.delSocio = true
            guard despues.guardar(b.id, g) else { decir(false, "No la abrí desde aquí: \(r.motivo)"); return }
            esperas[b.id] = Espera(tarjeta: nil, ficha: f, pedido: p, args: args, quien: quien, fin: nil, primera: false, base: b, desde: Date())
            ponerFicha(b)
            decir(false, b.tono == .coral ? "Esa dirección pide tu OK aparte\(f.motivo.isEmpty ? "" : " (\(f.motivo))"): su ficha está junto al monito."
                                           : "Su ficha está junto al monito: ábrela ahí.")
        case .cero, .confianza:
            if let aut = r.autorizacion { hazlo(aut, porConfianza: true) } else { decir(false, "No la abrí: \(r.motivo)") }
        default:
            decir(false, "No la abro desde aquí: \(r.motivo)")
        }
    }

    /// H-2: al tercer OK del mismo tipo, la app lo ofrece («Ya van 3. ¿Dejo de preguntarte para abrir apps?»). Solo tu
    /// clic en «Sí» lo recuerda.
    private func ofrecerRecordar(_ t: TipoRecordado, agente: String) {
        let b = TextoFicha.oferta(t, agente: agente, nombre: nombreDe(agente), color: monito.bandeja.color(agente), ahora: Date())
        monito.bandeja.poner(b) { [weak self] boton, _ in
            guard let self = self else { return }
            if boton == "si" { self.portero.recordar(t); self.volcar() }
            self.monito.bandeja.quitar(b.id)
        }
    }

    /// «Abrí YouTube · [Cerrar]»: la ficha verde de lo que ya hizo (también lo que hace sin preguntar).
    private func fichaHecha(_ id: String, _ texto: String, agente: String, deshacer: String?) {
        let b = TextoFicha.hecho(id: id, texto: texto, agente: agente, nombre: nombreDe(agente), color: monito.bandeja.color(agente),
                                 deshacer: deshacer, ahora: Date())
        monito.bandeja.poner(b) { [weak self] boton, _ in
            guard let self = self else { return }
            self.monito.bandeja.quitar(b.id)
            if boton == "deshacer" { self.deLaBurbuja(["op": "actuar_deshacer", "id": id]) }
        }
    }

    /// Con el OK (o la confianza): se vuelve a leer el destino y el OK se gasta una vez. En ensayo, nada de verdad: el
    /// aviso tranquilo con Deshacer y, a la vista, el monito te enseña dónde.
    /// (Sin `private`: carril 6. Trabajo.swift la llama cuando el socio ya tocó SU renglón en la ficha de trabajo. Sin
    /// `agente`, el del turno.)
    func hacer(_ a: String, _ p: PedidoAccion, _ quien: Llamador, modo: Modo, porConfianza: Bool, agente quienEs: String? = nil,
                       _ fin: @escaping (Int, [String: Any]) -> Void) {
        let agente = quienEs ?? portero.agente
        apretar()
        let ds = destinos(p).0
        let e = portero.ejecutar(a, ahora: ds)
        volcar(quien)
        guard e.ejecutada else {
            aflojar()
            fin(200, ["ok": false, "texto": e.motivo])
            return
        }
        // A1 · DE VERDAD: abrir (la mano). El portero ya gastó el OK con el destino de ahora.
        if !e.ensayo, p.tipoConocido == .abrir, let d = ds.first {
            abrirDeVerdad(d, modo: modo, porConfianza: porConfianza, agente: agente, quien, fin)
            return
        }
        let (titulo, que) = ArmarTarjeta.que(p.tipoConocido ?? .presionar, ds)
        _ = titulo
        let id = UUID().uuidString.lowercased()
        hechos[id] = HechoAviso(texto: que, ensayo: e.ensayo, marco: ds.first?.marco)
        let est = Deshacer.estrategia(p.tipoConocido ?? .presionar, ds.first ?? Destino())
        let aviso: [String: Any] = ["id": id, "ensayo": e.ensayo, "color": porConfianza ? "amarillo" : "",
                                    "texto": (e.ensayo ? "Ensayo · lo habría hecho" + (modo == .segundoPlano ? " en segundo plano" : "") + ": " : "Hecho: ") + que
                                        + (p.tipoConocido == .abrir && !ComoAbrir.activar(modo) ? " (sin traerla al frente)" : ""),
                                    "deshacer": est != .ninguna, "confianza": porConfianza, "ensename": !(ds.first?.marco == nil),
                                    "agente": agente]
        avisar(aviso)
        monito.jsManos("WSMActuar.toca('listo')")                    // el monito te toca: terminó
        let decir = e.ensayo
            ? "Ensayo: el socio dijo que sí, pero en esta versión no se hace de verdad (\(que)). Díselo en una frase; el monito le ofrece enseñarle dónde."
            : "Listo: \(que)."
        if modo == .aLaVista, let d = ds.first, let m = d.marco {
            monito.senalar([Objetivo(marco: m, etiqueta: e.ensayo ? "Aquí: lo haces tú" : "Aquí", punto: false)]) { [weak self] _ in
                self?.aflojar()
                fin(200, ["ok": true, "texto": decir, "ensayo": e.ensayo])
            }
            return
        }
        aflojar()
        fin(200, ["ok": true, "texto": decir, "ensayo": e.ensayo])
    }

    /// A1 · abrir DE VERDAD (Hacer.swift): en segundo plano sin quitarte el foco (o, a la vista, al frente y el monito
    /// vuela a su ventana); a la bitácora; el aviso tranquilo con «Cerrar» si se puede deshacer; y al agente, en una frase.
    private func abrirDeVerdad(_ d: Destino, modo: Modo, porConfianza: Bool, agente: String, _ quien: Llamador, _ fin: @escaping (Int, [String: Any]) -> Void) {
        let turno = portero.turno ?? ""
        let g = generacion
        let t0 = Date()
        // carril 6 (E10): solo lo que abrió con un TOQUE tuyo (no lo recordado) se puede leer después en este turno
        abrirConLaMano(d, modo: modo, conToque: !porConfianza) { [weak self] a, err in
            guard let self = self else { return }
            @MainActor func anotar(_ resultado: String, _ extra: [String: Any]) {
                var o: [String: Any] = ["cuando": ISO8601DateFormatter().string(from: Date()), "tipo": "abrir", "resultado": resultado,
                                        "turno": turno, "agente": agente, "etapa": self.portero.etapa.rawValue,
                                        "modo": modo.rawValue, "segundos": Double(Int(Date().timeIntervalSince(t0) * 10)) / 10]
                for (k, v) in extra { o[k] = v }
                self.portero.registro.append(o)
                self.volcar(quien)
            }
            guard let a = a else {
                anotar("fallo", ["motivo": err ?? "", "ruta": d.ruta ?? "", "url": BitacoraAcciones.corto(d.abrirURL, 300) ?? "",
                                 "abrir_app": d.abrirApp ?? ""])
                self.aflojar()
                fin(200, ["ok": false, "texto": "No lo abrí: \(err ?? "no se pudo"). Díselo en una frase."])
                return
            }
            // el pánico llegó mientras abría: lo que abrió se cierra (si lo abrió el monito) y no se avisa como hecho
            if g != self.generacion {
                anotar("parado", ["abierto": a.json()])
                if a.appNueva { Mano.cerrar(a) { _, _ in } }
                fin(200, ["ok": false, "texto": "El socio paró todo mientras lo abría: lo cerré. No lo vuelvas a intentar si él no lo pide."])
                return
            }
            anotar("hecho", ["abierto": a.json()])
            let av = AvisoAbrir.de(d, appNueva: a.appNueva, modo: modo, robo: a.robo, devuelto: a.devuelto)
            let id = UUID().uuidString.lowercased()
            self.hechos[id] = HechoAviso(texto: av.texto, ensayo: false, marco: nil, abierto: a)
            var aviso: [String: Any] = ["id": id, "ensayo": false, "texto": av.texto, "deshacer": av.boton != nil,
                                        "ensename": a.forma != "finder", "agente": agente, "confianza": porConfianza]
            if let b = av.boton { aviso["boton"] = b }
            // la ficha verde «Abrí X · [Cerrar]» (ya no el globito de la burbuja)
            self.fichaHecha(id, av.texto, agente: agente, deshacer: av.boton.map { $0 + " " + a.nombre })
            #if PERSONA_DE_PRUEBA
            self.personaDePruebaAviso(aviso)
            #endif
            self.monito.jsManos("WSMActuar.toca('listo')")
            let listo: [String: Any] = ["ok": true, "texto": av.agente, "ensayo": false]
            if modo == .aLaVista && a.forma != "finder" {
                Mano.esperarVentana(pid: a.pid, archivo: d.ruta, tope: 4) { [weak self] r in
                    guard let self = self else { return }
                    guard let r = r else { self.aflojar(); fin(200, listo); return }
                    self.monito.senalar([Objetivo(marco: r, etiqueta: "Aquí está «\(a.nombre)»", punto: false)]) { [weak self] _ in
                        self?.aflojar()
                        fin(200, listo)
                    }
                }
                return
            }
            self.aflojar()
            fin(200, listo)
        }
    }

    /// Abrir con la mano de verdad (Hacer.swift). Solo la copia de PRUEBA puede traer una mano de mentira (su variable
    /// de entorno, abajo): no abre nada y lo anota (las pruebas en vivo no abren nada en la pantalla de nadie).
    private func abrirConLaMano(_ d: Destino, modo: Modo, conToque: Bool, listo: @escaping @MainActor (Abierto?, String?) -> Void) {
        #if PERSONA_DE_PRUEBA
        if ProcessInfo.processInfo.environment["WORKSPACE_MONITO_MANO"] == "mentira" {
            let a = Abierto(forma: d.abrirURL != nil ? "pagina" : (d.abrirApp != nil ? "app" : "archivo"), bundle: d.abrirApp ?? d.abrirCon ?? "",
                            nombre: d.abrirNombre ?? "su app", pid: 0, appNueva: d.abrirApp != nil && !d.abrirAbierta, activar: false,
                            frenteAntes: "", frenteDespues: "", ruta: d.ruta, url: d.abrirURL)
            personaDePruebaAviso(["tipo": "abierto_de_mentira", "abierto": a.json()])
            DispatchQueue.main.async { listo(a, nil) }
            return
        }
        #endif
        Mano.abrir(d, modo: modo, conToque: conToque, listo: listo)
    }

    /// El nombre del agente como lo ves en la burbuja.
    private func nombreDe(_ a: String) -> String { agentes.first { $0.id == a }?.nombre ?? a }

    /// El aviso tranquilo de la burbuja (y, en la copia de prueba, a su persona de prueba).
    private func avisar(_ a: [String: Any]) {
        monito.jsManos("WSMActuar.aviso(\(Permisos.json(a)))")
        #if PERSONA_DE_PRUEBA
        personaDePruebaAviso(a)
        #endif
    }

    private func senalarDestino(_ ds: [Destino], _ motivo: String, _ fin: @escaping (Int, [String: Any]) -> Void) {
        guard let d = ds.first, let m = d.marco, Clasificador.puedeSenalar(d, vetados: portero.vetados) == nil else {
            fin(200, ["ok": false, "texto": motivo])
            return
        }
        monito.senalar([Objetivo(marco: m, etiqueta: "Aquí: lo haces tú", punto: false)]) { _ in
            fin(200, ["ok": false, "texto": motivo + " El monito le enseñó dónde."])
        }
    }

    // MARK: el pánico

    /// Esc Esc o el botón rojo «Parar»: se para todo lo que se está haciendo, y lo que un agente esperaba se le niega.
    /// Las fichas que quedaron para después no se tocan (nadie las está haciendo). Un clic en el monito ya NO llega aquí.
    func panico(_ por: String) {
        generacion += 1                                               // lo que la mano esté abriendo, se cierra al llegar
        for (id, e) in esperas where e.fin != nil {
            esperas[id] = nil
            monito.bandeja.quitar(id)
            e.fin?(200, ["ok": false, "texto": "El socio paró todo (\(por)). No lo hice; no lo vuelvas a intentar si él no lo pide."])
        }
        monito.manos?.trabajo.cerrar("panico")                        // carril 6: su ficha de trabajo también se cierra
        let n = portero.panico()
        portero.registro.append(["cuando": ISO8601DateFormatter().string(from: Date()), "tipo": "panico", "resultado": "parado",
                                 "motivo": por, "cancelo": n, "turno": portero.turno ?? "", "agente": portero.agente])
        volcar()
        banda?.detener()
        banda = nil
        enCurso = 0
        esc.soltar()
        avisar(["id": "panico", "texto": "Paré todo.", "deshacer": false, "agente": portero.agente])
        monito.bandeja.repintar()                                      // el botón rojo se va
    }

    // MARK: lo que llega de la burbuja (op «actuar_*»)

    func deLaBurbuja(_ d: [String: Any]) {
        switch (d["op"] as? String) ?? "" {
        case "actuar_modo":
            guard let m = (d["modo"] as? String).flatMap(Modo.init(rawValue:)), m != .conTuCursor else { return }
            let a = (d["agente"] as? String) ?? portero.agente
            guard !a.isEmpty else { return }
            portero.modos[a] = m
            guardarAjustes()
            monito.jsManos("WSMActuar.modo(\(Permisos.json(["agente": a, "modo": m.rawValue])))")
        case "actuar_deshacer":
            guard let id = d["id"] as? String, let h = hechos.removeValue(forKey: id) else { return }
            if let a = h.abierto {
                // «Cerrar»: solo lo que abrió el monito (y como ⌘Q: si tiene cambios sin guardar, la app te pregunta)
                Mano.cerrar(a) { [weak self] txt, ok in
                    guard let self = self else { return }
                    self.portero.registro.append(["cuando": ISO8601DateFormatter().string(from: Date()), "tipo": "deshacer",
                                                  "resultado": ok ? "deshecho" : "no_se_pudo", "que": txt, "abierto": a.json(),
                                                  "agente": self.portero.agente])
                    self.volcar()
                    self.avisar(["id": id, "texto": txt, "deshacer": false, "agente": self.portero.agente])
                }
                return
            }
            portero.registro.append(["cuando": ISO8601DateFormatter().string(from: Date()), "tipo": "deshacer",
                                     "resultado": h.ensayo ? "ensayo" : "deshecho", "que": h.texto, "agente": portero.agente])
            volcar()
            avisar(["id": id, "texto": h.ensayo ? "Ensayo: así lo regresaría (\(h.texto))." : "Lo regresé.", "deshacer": false, "agente": portero.agente])
        case "actuar_ensename":
            // del aviso: el monito te enseña dónde (en ensayo, lo haces tú; lo que abrió de verdad, su ventana)
            guard let id = d["id"] as? String, let h = hechos[id] else { return }
            if let a = h.abierto {
                Mano.esperarVentana(pid: a.pid, archivo: a.ruta, tope: 2) { [weak self] r in
                    guard let r = r else { return }
                    self?.monito.senalar([Objetivo(marco: r, etiqueta: "Aquí está «\(a.nombre)»", punto: false)]) { _ in }
                }
                return
            }
            guard let m = h.marco else { return }
            monito.senalar([Objetivo(marco: m, etiqueta: "Aquí: lo haces tú", punto: false)]) { _ in }
        case "actuar_automatizar":
            if let b = d["bundle"] as? String, (d["accion"] as? String) == "seguir" { Automatizar.pedir(b) { [weak self] ok in self?.automatizacion(b, ok) } }
            else { monito.jsManos("WSMActuar.permisoCerrar()") }
        case "actuar_parar":
            panico("el botón Parar")
        default:
            break
        }
    }

    /// Lo de la burbuja al llegar los agentes: su modo (para el interruptor de la barra).
    func agentesLlegaron(_ lista: [(id: String, nombre: String)]) {
        let nuevos = lista.map { $0.id } != agentes.map { $0.id }
        agentes = lista
        // el nombre con que el portero arma el título de la ficha («Atlas quiere abrir…»)
        portero.nombres = Dictionary(lista.map { ($0.id, $0.nombre) }, uniquingKeysWith: { x, _ in x })
        if nuevos, puede.todos { anotarManos() }                     // «todos» incluye a los que acaban de llegar
        let modos = Dictionary(lista.map { ($0.id, portero.modo(de: $0.id).rawValue) }, uniquingKeysWith: { x, _ in x })
        var d: [String: Any] = ["prendido": prendido, "etapa": etapa, "modos": modos]
        if !ensayo { d["agentes"] = agentesQuePueden }               // el interruptor, solo para el que puede
        monito.jsManos("WSMActuar.disponible(\(Permisos.json(d)))")
    }

    // MARK: Automatización (Apple Events): una vez por app, solo cuando una acción la necesite

    /// La tarjeta amable antes del aviso de macOS («para manejar Mail por ti, macOS te va a preguntar una vez»).
    func pedirAutomatizacion(_ bundle: String, app: String) {
        monito.jsManos("WSMActuar.permiso(\(Permisos.json(["bundle": bundle, "texto": "Para manejar \(app) por ti, macOS te va a preguntar una vez si me dejas. Solo lo uso cuando me lo pides y con tu OK.", "boton": "Seguir"])))")
    }

    private func automatizacion(_ b: String, _ ok: Bool) {
        monito.jsManos("WSMActuar.permisoEstado(\(Permisos.json(["texto": ok ? "¡Gracias! Ya puedo manejarla cuando me lo pidas." : "macOS dice que no. Si cambias de opinión, está en Ajustes › Privacidad › Automatización.", "gracias": ok])))")
    }

    // MARK: el menú del monito: «Seguridad para actuar»

    func agregarAlMenu(_ m: NSMenu) {
        let p = NSMenuItem(title: "Puede hacer cosas en mi Mac", action: nil, keyEquivalent: "")
        p.toolTip = "Abrir apps, archivos, carpetas y páginas por ti. Se prende una vez para todos tus agentes y se apaga por agente."
        menuPuede.delegate = self
        p.submenu = menuPuede
        m.addItem(p)
        // H-2: lo que recordaste («no me preguntes para…»), a la vista y con «Quitar»
        let rec = NSMenuItem(title: "Lo que hace sin preguntar", action: nil, keyEquivalent: "")
        rec.toolTip = "Lo que marcaste con «No me preguntes para…». Lo que sale de tu compu o no se deshace nunca aparece aquí."
        menuRecordado.delegate = self
        rec.submenu = menuRecordado
        m.addItem(rec)
        let son = NSMenuItem(title: "Sonido suave al llegar una ficha", action: #selector(alternarSonido(_:)), keyEquivalent: "")
        son.target = self
        son.state = ajustesBandeja.sonido ? .on : .off
        son.toolTip = "Apagado de fábrica. El monito brinca y enseña su número de todos modos."
        m.addItem(son)
        let it = NSMenuItem(title: "Seguridad para actuar", action: nil, keyEquivalent: "")
        menuSeguridad.delegate = self
        it.submenu = menuSeguridad
        m.addItem(it)
    }

    nonisolated func menuNeedsUpdate(_ menu: NSMenu) {
        MainActor.assumeIsolated {
            if menu === menuPuede { rehacerMenuPuede() } else if menu === menuRecordado { rehacerMenuRecordado() } else { rehacerMenu() }
        }
    }

    /// «Puede hacer cosas en mi Mac» (E3-b): una vez para todos tus agentes; se apaga (o se prende) por agente.
    private func rehacerMenuPuede() {
        let m = menuPuede
        m.removeAllItems()
        m.autoenablesItems = false
        m.addItem(item("Abre apps, archivos, carpetas y páginas por ti. Te pregunta en una ficha; lo que marques, ya no.", nil))
        if ensayo { m.addItem(item("Ahora está en ensayo: nada se hace de verdad.", nil)) }
        m.addItem(.separator())
        m.addItem(item("Todos mis agentes", #selector(alternarPuedeTodos), nil, on: puede.todos, activo: !ensayo))
        m.addItem(.separator())
        let lista = agentes.isEmpty ? (portero.agente.isEmpty ? [] : [(id: portero.agente, nombre: portero.agente)]) : agentes
        if lista.isEmpty { m.addItem(item("Tus agentes salen aquí cuando abres la burbuja (⌥ Espacio).", nil)) }
        for a in lista { m.addItem(item(a.nombre, #selector(alternarPuede(_:)), a.id, on: puede.puede(a.id), activo: !ensayo)) }
    }

    /// «Lo que hace sin preguntar» (H-2): lo recordado, con «Quitar». Lo coral nunca llega aquí (el portero no lo recuerda).
    private func rehacerMenuRecordado() {
        let m = menuRecordado
        m.removeAllItems()
        m.autoenablesItems = false
        let l = portero.recordados.lista
        if l.isEmpty {
            m.addItem(item("Todavía nada: te pregunta cada vez.", nil))
            m.addItem(item("Se llena cuando marcas «No me preguntes para…» en una ficha.", nil))
            return
        }
        for x in l { m.addItem(item("\(x.texto) · Quitar", #selector(quitarRecordado(_:)), x.tipo.rawValue)) }
        if l.count > 1 {
            m.addItem(.separator())
            m.addItem(item("Quitar todo (vuelve a preguntarme siempre)", #selector(quitarRecordados)))
        }
        m.addItem(.separator())
        m.addItem(item("Mandar, pagar, borrar o publicar nunca se hacen sin preguntarte.", nil))
    }

    @objc func quitarRecordado(_ i: NSMenuItem) {
        guard let k = i.representedObject as? String, let t = TipoRecordado(rawValue: k) else { return }
        portero.quitarRecordado(t)
        volcar()
    }

    @objc func quitarRecordados() {
        portero.quitarRecordados()
        volcar()
    }

    @objc func alternarSonido(_ i: NSMenuItem) {
        ajustesBandeja.sonido.toggle()
        i.state = ajustesBandeja.sonido ? .on : .off
        monito.bandeja.ajustes = ajustesBandeja
        guardarAjustes()
    }

    @objc func alternarPuedeTodos() {
        guard !ensayo else { return }
        if puede.todos { puede.apagarParaTodos() } else { puede.prender("", paraTodos: true) }
        despuesDeCambiarPuede("todos", puede.todos, desde: "menú")
        avisar(["id": "puede-todos", "deshacer": false, "agente": portero.agente,
                "texto": puede.todos ? "Listo: tus agentes ya pueden abrir apps, archivos y páginas por ti. Te preguntan en una ficha. Lo apagas aquí mismo, por agente."
                                     : "Listo: ningún agente hace cosas en tu Mac; solo te enseñan dónde."])
    }

    @objc func alternarPuede(_ i: NSMenuItem) {
        guard let a = i.representedObject as? String else { return }
        cambiarPuede(a, !puede.puede(a), paraTodos: false, desde: "menú")
    }

    /// Prender o apagar «Puede hacer cosas en mi Mac» para un agente (`paraTodos`: de una vez para todos): se guarda, se
    /// anota, manos.json lo dice (para que sus manos ofrezcan `actuar`) y la burbuja lo cuenta en una línea.
    func cambiarPuede(_ a: String, _ si: Bool, paraTodos: Bool = false, desde: String) {
        guard !a.isEmpty, !ensayo else { return }
        if si { puede.prender(a, paraTodos: paraTodos) } else { puede.apagar(a) }
        despuesDeCambiarPuede(a, si, desde: desde + (si && paraTodos ? " · para todos sus agentes" : ""))
        let n = agentes.first { $0.id == a }?.nombre ?? a
        avisar(["id": "puede-" + a, "agente": a, "deshacer": false,
                "texto": si ? (paraTodos ? "Listo: tus agentes ya pueden abrir apps, archivos y páginas por ti. Se apaga por agente en el menú de Compañero."
                                         : "Listo: \(n) ya puede abrir apps, archivos y páginas por ti. Lo apagas en el menú de Compañero.")
                            : "\(n) ya no hace cosas en tu Mac: solo te enseña dónde."])
    }

    private func despuesDeCambiarPuede(_ a: String, _ si: Bool, desde: String) {
        guardarAjustes()
        portero.registro.append(["cuando": ISO8601DateFormatter().string(from: Date()), "tipo": "ajuste", "resultado": si ? "prendido" : "apagado",
                                 "que": "puede hacer cosas en mi Mac", "agente": a, "desde": desde])
        volcar()
        anotarManos()
        agentesLlegaron(agentes)
    }

    /// manos.json con lo de actuar de ahora (la etapa y los agentes que pueden).
    func anotarManos() { monito.servidor?.anotar(en: carpeta, actuar: etapa, agentes: agentesQuePueden) }

    private func item(_ t: String, _ sel: Selector?, _ rep: Any? = nil, on: Bool = false, activo: Bool = true) -> NSMenuItem {
        let i = NSMenuItem(title: t, action: sel, keyEquivalent: "")
        i.target = self
        i.representedObject = rep
        i.state = on ? .on : .off
        i.isEnabled = activo && sel != nil
        return i
    }

    private func rehacerMenu() {
        let m = menuSeguridad
        m.removeAllItems()
        m.autoenablesItems = false
        m.addItem(item(ensayo ? "Actuar: ensayo (todavía no hace nada de verdad)"
                       : !puede.alguno ? "Actuar: apagado (se prende en «Puede hacer cosas en mi Mac»)"
                       : puede.todos ? "Actuar: abrir, preguntándote (todos tus agentes)"
                       : "Actuar: abrir, preguntándote (\(agentesQuePueden.count == 1 ? "1 agente" : "\(agentesQuePueden.count) agentes"))", nil))
        m.addItem(.separator())
        portero.confianzas.limpiar(Date())
        m.addItem(item("Confianzas de hoy", nil))
        if portero.confianzas.lista.isEmpty { m.addItem(item("   Ninguna", nil)) }
        let hora = DateFormatter()
        hora.dateFormat = "HH:mm"
        for c in portero.confianzas.lista {
            m.addItem(item("   \(c.texto), hasta las \(hora.string(from: c.vence)) · Quitar", #selector(quitarConfianza(_:)), c.id))
        }
        if portero.confianzas.lista.count > 1 { m.addItem(item("   Quitar todas", #selector(quitarConfianzas))) }
        // lo que leyó cada agente en su conversación (la marca de la tarjeta; tumba las confianzas)
        let conLecturas = portero.lecturasGuardables()
        if !conLecturas.isEmpty {
            m.addItem(.separator())
            m.addItem(item("Lo que leyó en su conversación", nil))
            for (a, l) in conLecturas.sorted(by: { $0.key < $1.key }) {
                let nombre = agentes.first { $0.id == a }?.nombre ?? a
                m.addItem(item("   \(nombre): \(l.fuentes.prefix(2).map { $0.texto }.joined(separator: ", "))\(l.fuentes.count > 2 ? "…" : "") · Olvidarlo (si empiezas otra conversación)",
                               #selector(olvidarLecturas(_:)), a))
            }
        }
        m.addItem(.separator())
        let vet = NSMenuItem(title: "Vetados (no tocar · no mirar)", action: nil, keyEquivalent: "")
        let sub = NSMenu()
        sub.autoenablesItems = false
        let fijos = Vetados.fijos
        for v in portero.vetados.propios {
            sub.addItem(item("\(v.nombre) · \(v.que == .noMirar ? "no mirar" : "no tocar") · Quitar", #selector(quitarVetado(_:)), v.id))
        }
        if let e = monito.manos?.alFrente(), let b = e.bundleIdentifier {
            let n = e.localizedName ?? b
            sub.addItem(item("No tocar «\(n)»", #selector(vetar(_:)), ["tipo": "app", "valor": b, "nombre": n, "que": "no_tocar"]))
            sub.addItem(item("No mirar «\(n)»", #selector(vetar(_:)), ["tipo": "app", "valor": b, "nombre": n, "que": "no_mirar"]))
        }
        sub.addItem(.separator())
        sub.addItem(item("Siempre (no se quitan): \(Set(fijos.map { $0.nombre }).count) apps y sitios", nil))
        for n in ["Terminal y otras terminales", "Ajustes del Sistema", "Instalador y avisos del sistema", "Llavero, Contraseñas y gestores",
                  "Bancos y pagos", "Ventanas privadas", "La tarjeta del propio monito"] {
            sub.addItem(item("   🔒 " + n, nil))
        }
        vet.submenu = sub
        m.addItem(vet)
        m.addItem(.separator())
        let lista = agentes.isEmpty ? (portero.agente.isEmpty ? [] : [(id: portero.agente, nombre: portero.agente)]) : agentes
        if !lista.isEmpty {
            let como = NSMenuItem(title: "Cómo hace las cosas", action: nil, keyEquivalent: "")
            let s1 = NSMenu(); s1.autoenablesItems = false
            let raton = NSMenuItem(title: "Puede tomar mi mouse", action: nil, keyEquivalent: "")
            let s2 = NSMenu(); s2.autoenablesItems = false
            for a in lista {
                let modo = portero.modo(de: a.id)
                s1.addItem(item("\(a.nombre): en segundo plano", #selector(elegirModo(_:)), [a.id, Modo.segundoPlano.rawValue], on: modo == .segundoPlano))
                s1.addItem(item("\(a.nombre): a la vista", #selector(elegirModo(_:)), [a.id, Modo.aLaVista.rawValue], on: modo == .aLaVista))
                let r = portero.mouse(de: a.id)
                s2.addItem(item("\(a.nombre): nunca", #selector(elegirMouse(_:)), [a.id, MouseAgente.nunca.rawValue], on: r == .nunca))
                s2.addItem(item("\(a.nombre): preguntando", #selector(elegirMouse(_:)), [a.id, MouseAgente.preguntando.rawValue], on: r == .preguntando))
            }
            como.submenu = s1
            raton.submenu = s2
            m.addItem(como)
            m.addItem(raton)
            m.addItem(.separator())
        }
        m.addItem(item("Ver la bitácora de acciones", #selector(verBitacora)))
    }

    @objc func quitarConfianza(_ i: NSMenuItem) {
        guard let id = i.representedObject as? String else { return }
        portero.confianzas.quitar(id)
        guardarConfianzas()
    }

    @objc func quitarConfianzas() {
        portero.confianzas.lista = []
        guardarConfianzas()
    }

    @objc func olvidarLecturas(_ i: NSMenuItem) {
        guard let a = i.representedObject as? String else { return }
        portero.olvidarLecturas(agente: a)
        guardarLecturas()
        portero.registro.append(["cuando": ISO8601DateFormatter().string(from: Date()), "tipo": "olvidar_lecturas",
                                 "resultado": "olvidado", "agente": a])
        volcar()
        monito.jsManos("WSM.olvido(\(Permisos.json(["agente": a])))")
    }

    @objc func quitarVetado(_ i: NSMenuItem) {
        guard let id = i.representedObject as? String else { return }
        portero.vetados.quitar(id)
        guardarVetados()
    }

    @objc func vetar(_ i: NSMenuItem) {
        guard let o = i.representedObject as? [String: Any], let v = Vetado.deJSON(o) else { return }
        portero.vetados.agregar(v)
        guardarVetados()
    }

    @objc func elegirModo(_ i: NSMenuItem) {
        guard let x = i.representedObject as? [String], x.count == 2, let m = Modo(rawValue: x[1]) else { return }
        portero.modos[x[0]] = m
        guardarAjustes()
        monito.jsManos("WSMActuar.modo(\(Permisos.json(["agente": x[0], "modo": m.rawValue])))")
    }

    @objc func elegirMouse(_ i: NSMenuItem) {
        guard let x = i.representedObject as? [String], x.count == 2, let m = MouseAgente(rawValue: x[1]) else { return }
        portero.mouse[x[0]] = m
        guardarAjustes()
    }

    @objc func verBitacora() {
        let dir = ruta(BitacoraAcciones.carpeta)
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        NSWorkspace.shared.activateFileViewerSelecting([URL(fileURLWithPath: dir)])
    }
}

#if PERSONA_DE_PRUEBA
// Solo la copia de PRUEBA (swift build -Xswiftc -DPERSONA_DE_PRUEBA): abrir.py y probar_rama.py nunca la compilan, así
// que el monito de verdad no la trae. Una «persona de prueba» hace con archivos lo que harías tú con el mouse, para la
// prueba en vivo con un motor de verdad (escritorio/…/actuar-vivo): en <estado>/escritorio/prueba/
//   · la app escribe tarjeta.json (la tarjeta de la ficha que enseña, armada por el portero), fichas.json (la bandeja
//     como está: su número, si está doblada y cada ficha que se ve) y avisos.jsonl (cada aviso);
//   · la persona escribe ficha.json {"id": id de la ficha, "boton": "hazlo|no|permitir|despues|…", "casilla": true|false}
//     (aprieta ESE botón, con su armado de 0.6 s; doblada no se puede: primero monito.json {"clic": true}, un clic en
//     el monito) y parar.json {} (el botón rojo);
//   · la persona escribe respuesta.json {"tarjeta": id, "respuesta": "hazlo|no|a_la_vista|ensename"} (contesta ESA
//     tarjeta, con su armado de 0.6 s igual que un clic), burbuja.json {"op": "actuar_deshacer|actuar_ensename", "id": …}
//     (un clic en el aviso) y puede.json {"agente": …, "puede": true|false} (lo del menú «Puede hacer cosas en mi Mac»).
// Lo que contesta queda en la bitácora como «persona de prueba». La app de prueba además lanza las apps sin recuperar sus
// ventanas de antes (no abre lo tuyo).
extension Actuar {
    private var carpetaPrueba: String { (carpeta as NSString).appendingPathComponent("prueba") }

    func personaDePruebaArrancar() {
        monito.bandeja.alPublicar = { [weak self] o in self?.personaDePruebaFichas(o) }
        Mano.argumentosAlLanzar = ["-ApplePersistenceIgnoreState", "YES"]
        try? FileManager.default.createDirectory(atPath: carpetaPrueba, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        personaDePruebaReloj = Timer.scheduledTimer(withTimeInterval: 0.3, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.personaDePruebaMirar() }
        }
    }

    func personaDePruebaTarjeta(_ t: Tarjeta) {
        var o = t.json()
        o["mostrada"] = Date().timeIntervalSince1970
        if let d = try? JSONSerialization.data(withJSONObject: o, options: [.sortedKeys]) {
            FileManager.default.createFile(atPath: (carpetaPrueba as NSString).appendingPathComponent("tarjeta.json"), contents: d)
        }
    }

    func personaDePruebaAviso(_ a: [String: Any]) {
        var o = a
        o["cuando"] = Date().timeIntervalSince1970
        guard let d = try? JSONSerialization.data(withJSONObject: o, options: [.sortedKeys]) else { return }
        let r = (carpetaPrueba as NSString).appendingPathComponent("avisos.jsonl")
        if !FileManager.default.fileExists(atPath: r) { FileManager.default.createFile(atPath: r, contents: nil) }
        if let h = FileHandle(forWritingAtPath: r) { h.seekToEndOfFile(); h.write(d + Data("\n".utf8)); try? h.close() }
    }

    private func personaDePruebaLeer(_ n: String) -> [String: Any]? {
        let r = (carpetaPrueba as NSString).appendingPathComponent(n)
        guard let d = FileManager.default.contents(atPath: r) else { return nil }
        unlink(r)
        return (try? JSONSerialization.jsonObject(with: d)) as? [String: Any]
    }

    func personaDePruebaFichas(_ o: [String: Any]) {
        var x = o
        x["cuando"] = Date().timeIntervalSince1970
        x["corriendo"] = enVuelo
        if let d = try? JSONSerialization.data(withJSONObject: x, options: [.sortedKeys]) {
            let r = (carpetaPrueba as NSString).appendingPathComponent("fichas.json")
            try? d.write(to: URL(fileURLWithPath: r), options: .atomic)
        }
    }

    private func personaDePruebaMirar() {
        if let o = personaDePruebaLeer("ficha.json"), let id = o["id"] as? String, let b = o["boton"] as? String {
            let ok = monito.bandeja.personaDePrueba(id, b, casilla: o["casilla"] as? Bool)
            portero.registro.append(["cuando": ISO8601DateFormatter().string(from: Date()), "tipo": "persona_de_prueba",
                                     "resultado": ok ? b : "no_valio", "ficha": id])
            volcar()
        }
        if personaDePruebaLeer("monito.json") != nil { monito.mensaje(["op": "llamar"]) }
        if personaDePruebaLeer("parar.json") != nil { panico("el botón Parar") }
        if let o = personaDePruebaLeer("puede.json"), let a = o["agente"] as? String {
            cambiarPuede(a, (o["puede"] as? Bool) ?? false, paraTodos: (o["todos"] as? Bool) ?? false, desde: "persona de prueba")
        }
        // (lo de antes: contestar por el id de la tarjeta del portero)
        if let o = personaDePruebaLeer("respuesta.json"), let t = o["tarjeta"] as? String, let r = o["respuesta"] as? String {
            let ok = monito.bandeja.personaDePrueba("p:" + t, r, casilla: o["casilla"] as? Bool)
            portero.registro.append(["cuando": ISO8601DateFormatter().string(from: Date()), "tipo": "persona_de_prueba",
                                     "resultado": ok ? r : "no_valio", "tarjeta": t])
            volcar()
        }
        if let o = personaDePruebaLeer("burbuja.json"), let op = o["op"] as? String, op.hasPrefix("actuar_") {
            deLaBurbuja(o)
        }
    }
}
#endif

#if PERSONA_DE_PRUEBA
extension BandejaApp {
    /// Solo la copia de PRUEBA: su «persona» aprieta un botón de una ficha (con su armado de 0.6 s, como un clic; doblada
    /// no se ve: primero un clic en el monito).
    func personaDePrueba(_ id: String, _ b: String, casilla: Bool?) -> Bool {
        guard !estado.plegada, let f = estado.vista().tarjetas.first(where: { $0.id == id }) else { return false }
        if b == f.principal.id, let v = vistoDesde[id], Date().timeIntervalSince(v) * 1000 < Double(f.armaMs) { return false }
        boton(id, b, casilla: casilla ?? vistas[id]?.casillaMarcada ?? false)
        return true
    }
}
#endif

/// Automatización (Apple Events): macOS pregunta una vez por app. Solo cuando una acción lo necesite (en A0 ninguna):
/// primero la tarjeta amable del monito y, si dices «Seguir», el aviso de macOS. Nunca al arrancar.
enum Automatizar {
    /// Sin preguntar: 0 = ya puedo; -1744 = macOS preguntaría; -1743 = dijiste que no; -600 = la app no está abierta.
    static func estado(_ bundle: String) -> OSStatus {
        let d = NSAppleEventDescriptor(bundleIdentifier: bundle)
        guard let a = d.aeDesc else { return -600 }
        return AEDeterminePermissionToAutomateTarget(a, typeWildCard, typeWildCard, false)
    }

    /// Con la pregunta de macOS (en segundo plano: espera tu respuesta). `listo(true)` si dijiste que sí.
    static func pedir(_ bundle: String, _ listo: @escaping (Bool) -> Void) {
        DispatchQueue.global(qos: .userInitiated).async {
            let d = NSAppleEventDescriptor(bundleIdentifier: bundle)
            let r = d.aeDesc.map { AEDeterminePermissionToAutomateTarget($0, typeWildCard, typeWildCard, true) } ?? -600
            DispatchQueue.main.async { listo(r == noErr) }
        }
    }
}
