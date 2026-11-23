// Los permisos de la Mac que piden las manos (los da el socio en Ajustes del Sistema):
//  · Accesibilidad: leer la ventana (botones, textos, selección, URL). AXorcist. Es el ÚNICO del camino de siempre.
//  · Grabación de pantalla: la foto de ver_pantalla. ScreenCaptureKit. Opcional: solo si el socio lo prende desde el
//    menú del monito (macOS lo vuelve a confirmar cada mes y pide reabrir la app); sin él, se lee la ventana como texto.
// Señalar no pide ninguno. Nunca se piden la primera vez al arrancar: solo cuando una herramienta los necesita, con la
// tarjeta del monito (qué y para qué, en una frase), un botón que abre el panel exacto de Ajustes y un «¡Listo!» en
// cuanto macOS dice que ya; y el pedido que lo esperaba sigue solo.
// Por qué se perdían (22-nov): macOS guarda cada permiso con el «requisito designado» de la app (TN3127). Firmada ad hoc,
// es la huella exacta del binario: otra compilación es otra app, aunque Ajustes siga enseñando el renglón prendido. Por
// eso la app anota con qué firma lo tuvo; si al abrir la firma cambió y el permiso ya no está, borra sola SU renglón
// muerto (`tccutil reset` de ESTE identificador) y saca una sola tarjeta.
// La máquina de estados vive en Logica.swift (CicloPermiso, probada en Swift). Aquí solo se pinta y se habla con macOS.
// Cada copia del monito tiene su propio identificador (com.workspace.monito; la de desarrollo, ….dev; la de probar una
// rama, ….prueba): con dos paquetes con el mismo identificador, el permiso que dabas en Ajustes se iba a la otra copia.
import AppKit
import AXorcist
import CoreGraphics
import Security

enum Permiso: String, CaseIterable {
    case accesibilidad
    case grabacion

    var nombre: String { self == .accesibilidad ? "Accesibilidad" : "Grabación de pantalla" }

    /// El panel exacto de Ajustes del Sistema.
    var ajustes: URL {
        let k = self == .accesibilidad ? "Privacy_Accessibility" : "Privacy_ScreenCapture"
        return URL(string: "x-apple.systempreferences:com.apple.preference.security?\(k)")!
    }

    /// Sin preguntar nada. Cuando sí, anota que lo tuvo y con qué firma (para saber, al abrir, si su renglón quedó viejo).
    @MainActor var concedido: Bool {
        if ProcessInfo.processInfo.environment["WORKSPACE_MANOS_SIN_PERMISOS"] == "1" { return false }  // demos y pruebas
        let si = self == .accesibilidad ? AXPermissionHelpers.hasAccessibilityPermissions() : CGPreflightScreenCaptureAccess()
        if si {
            if !loTuvo { loTuvo = true }
            if firmaVista != EstaApp.requisito { firmaVista = EstaApp.requisito }
        }
        return si
    }

    /// Pone a la app en la lista de Ajustes (y macOS enseña su aviso). Solo tras el clic del socio.
    @MainActor func registrar() {
        if self == .accesibilidad { _ = AXPermissionHelpers.askForAccessibilityIfNeeded() } else { _ = CGRequestScreenCaptureAccess() }
    }

    private static var sinPermisos: Bool { ProcessInfo.processInfo.environment["WORKSPACE_MANOS_SIN_PERMISOS"] == "1" }

    /// ¿Esta app ya lo tuvo alguna vez?
    var loTuvo: Bool {
        get { Permiso.sinPermisos ? false : UserDefaults.standard.bool(forKey: "permiso.\(rawValue).visto") }
        nonmutating set { UserDefaults.standard.set(newValue, forKey: "permiso.\(rawValue).visto") }
    }

    /// La firma (requisito designado) que tenía la app la última vez que macOS le dio este permiso.
    var firmaVista: String {
        get { UserDefaults.standard.string(forKey: "permiso.\(rawValue).firma") ?? "" }
        nonmutating set { UserDefaults.standard.set(newValue, forKey: "permiso.\(rawValue).firma") }
    }

    /// ¿Su renglón en Ajustes es de otra versión de esta app? (lo tuvo con otra firma)
    var rancio: Bool { Firma.rancio(loTuvo: loTuvo, vista: firmaVista, actual: EstaApp.requisito) }

    /// La app se cerró mientras lo estabas dando (Grabación de pantalla la reabre; «Salir y volver a abrir» de macOS
    /// también): al abrir, se dice «¡Listo!» o se ofrece arreglarlo. Diez minutos.
    var enCurso: Bool {
        get {
            let t = UserDefaults.standard.double(forKey: "permiso.\(rawValue).encurso")
            return t > 0 && Date().timeIntervalSince1970 - t < 600
        }
        nonmutating set {
            if newValue { UserDefaults.standard.set(Date().timeIntervalSince1970, forKey: "permiso.\(rawValue).encurso") }
            else { UserDefaults.standard.removeObject(forKey: "permiso.\(rawValue).encurso") }
        }
    }
}

/// Esta copia del monito: el nombre con que sale en Ajustes (el de Finder), su identificador y su firma.
enum EstaApp {
    static var nombre: String {
        let b = Bundle.main.bundleURL
        guard b.pathExtension == "app" else { return "Workspace Compañero" }
        return FileManager.default.displayName(atPath: b.path)
    }
    static var id: String { Bundle.main.bundleIdentifier ?? "" }

    /// Su requisito designado (lo que macOS guarda con cada permiso): ad hoc, `cdhash H"…"` (cambia con cada binario);
    /// con una identidad estable, su identificador y su certificado (se queda entre versiones). "" sin firma.
    static let requisito: String = {
        var code: SecCode?
        guard SecCodeCopySelf(SecCSFlags(), &code) == errSecSuccess, let c = code else { return "" }
        var estatico: SecStaticCode?
        guard SecCodeCopyStaticCode(c, SecCSFlags(), &estatico) == errSecSuccess, let s = estatico else { return "" }
        var req: SecRequirement?
        guard SecCodeCopyDesignatedRequirement(s, SecCSFlags(), &req) == errSecSuccess, let r = req else { return "" }
        var texto: CFString?
        guard SecRequirementCopyString(r, SecCSFlags(), &texto) == errSecSuccess, let t = texto else { return "" }
        return t as String
    }()

    static var estable: Bool { Firma.estable(requisito) }

    /// Para el menú y la bitácora: «Developer ID (EQUIPO)», «propia de esta Mac», «ad hoc»…
    static var firmaEnSimple: String { Firma.enSimple(requisito) }
}

/// Lo que se dice en la tarjeta, según para qué hace falta.
enum Para: String {
    /// actuar (A0): hacerlo por ti usa el MISMO permiso de Accesibilidad con que lee (no pide otro). Automatización
    /// (Apple Events) va aparte, una vez por app y solo si una acción la necesita (Actuar.swift, Automatizar).
    case contexto, leer, ventana, pantalla, actuar

    var permiso: Permiso { self == .ventana || self == .pantalla ? .grabacion : .accesibilidad }

    /// Para qué (la tarjeta promete «una sola vez» solo si es cierto: TextoPermiso.pide).
    var frase: String {
        switch self {
        case .contexto: return "Para saber qué tienes enfrente necesito un permiso de tu Mac. Te llevo directo: actívalo y regresa."
        case .leer: return "Para leer tu ventana necesito un permiso de tu Mac. Te llevo directo: actívalo y regresa."
        case .ventana, .pantalla: return "Para ver tu pantalla como foto necesito otro permiso de tu Mac (Grabación de pantalla). Te llevo directo: actívalo y regresa."
        case .actuar: return "Para hacerlo por ti (siempre con tu OK) necesito un permiso de tu Mac, el mismo con el que leo tu ventana. Te llevo directo: actívalo y regresa."
        }
    }

    var gracias: String {
        switch self {
        case .contexto, .leer: return "¡Listo! Ya puedo leer tu ventana."
        case .ventana: return "¡Listo! Ya puedo ver tu ventana."
        case .pantalla: return "¡Listo! Ya puedo ver tu pantalla."
        case .actuar: return "¡Listo! Ya puedo leer tu ventana y, con tu OK, hacerlo por ti."
        }
    }

    /// Lo que la herramienta le contesta al agente cuando falta (corto: el agente lo dice en una frase).
    var paraElAgente: String {
        "Falta el permiso de \(permiso.nombre) de la Mac. El monito ya le enseñó al socio una tarjeta con el botón que abre Ajustes; dile en una frase que lo active y vuelve a intentarlo cuando te diga que ya."
    }

    /// El socio dijo «Ahora no»: que el agente no insista.
    var ahoraNo: String {
        "El socio prefirió no dar el permiso de \(permiso.nombre) por ahora. Sigue sin leer su ventana (pregúntale lo que necesites) y no se lo vuelvas a pedir en esta plática."
    }
}

/// Cómo terminó la espera de un pedido por su permiso.
enum Llegada { case listo, ahoraNo, tarde }

/// La tarjeta de permiso de la Mac: lo que decide CicloPermiso (Logica.swift), pintado en la burbuja, y lo que se habla
/// con macOS (borrar el renglón muerto de esta app, pedirlo, su panel de Ajustes, reabrirse).
@MainActor
final class Permisos {
    /// Pinta en la burbuja (lo hace Monito con el JS de las manos).
    var pintar: ((String) -> Void)?
    /// ¿Hay un turno o un vuelo en curso? (Monito). Si no, tras dar Grabación de pantalla la app se reabre sola.
    var ocupado: (() -> Bool)?
    /// La bitácora de las manos (miradas/bitacora.jsonl): cada paso del permiso, para saber qué pasó.
    var anotar: (([String: Any]) -> Void)?
    private var ciclo = CicloPermiso()
    /// Para qué se pidió cada permiso (la frase de la tarjeta y su «¡Listo!»).
    private var para: [String: Para] = [:]
    /// Los pedidos que esperan su permiso para seguir solos (CicloPermiso dice cuándo).
    private var esperas: [Int: (Llegada) -> Void] = [:]
    private var sig = 0
    private var reloj: Timer?
    private var oido: NSObjectProtocol?
    private let t0 = Date()
    private var ahora: TimeInterval { Date().timeIntervalSince(t0) }
    /// Lo que espera un pedido a que llegue el permiso, a lo más (por debajo del tope de manos_mcp: 110 s).
    nonisolated static let esperaTope: TimeInterval = 95

    /// Pruebas de punta a punta (WORKSPACE_MONITO_SISTEMA=ensayo) y demos: no se abre Ajustes ni el aviso de macOS
    /// (solo se anota). Borrar el renglón de ESTA app sí (no se ve), salvo en los demos sin permisos.
    private let ensayo = ProcessInfo.processInfo.environment["WORKSPACE_MONITO_SISTEMA"] == "ensayo"
    private let demo = ProcessInfo.processInfo.environment["WORKSPACE_MANOS_SIN_PERMISOS"] == "1"

    init() {
        oido = NSWorkspace.shared.notificationCenter.addObserver(forName: NSWorkspace.didActivateApplicationNotification,
                                                                 object: nil, queue: .main) { [weak self] n in
            let a = n.userInfo?[NSWorkspace.applicationUserInfoKey] as? NSRunningApplication
            let clase = CicloPermiso.clase(bundle: a?.bundleIdentifier ?? "", regular: a?.activationPolicy == .regular,
                                           propia: a?.processIdentifier == getpid())
            MainActor.assumeIsolated { self?.aplicar(self?.ciclo.activo(clase, ahora: self?.ahora ?? 0) ?? []) }
        }
    }

    private var concedidos: [String: Bool] {
        [Permiso.accesibilidad.rawValue: Permiso.accesibilidad.concedido, Permiso.grabacion.rawValue: Permiso.grabacion.concedido]
    }

    /// Al abrir (una vez, ya con `pintar`): si la firma cambió y un permiso que tenía ya no está, su renglón muerto se
    /// borra solo y, para Accesibilidad, sale UNA tarjeta; si se reabrió por un permiso, «¡Listo!» o «Arreglar». La
    /// primera vez no pide nada.
    func alArrancar() {
        anotar?(["firma": EstaApp.firmaEnSimple, "requisito": EstaApp.requisito, "version": Contrato.version,
                 "permisos": [Permiso.accesibilidad.rawValue: Permiso.accesibilidad.concedido,
                              Permiso.grabacion.rawValue: Permiso.grabacion.concedido]])
        for p in Permiso.allCases {
            let concedido = p.concedido, rancio = !concedido && p.rancio, reabierto = p.enCurso
            p.enCurso = false
            if rancio { anotar?(["permiso": p.rawValue, "paso": "firma_cambiada", "antes": p.firmaVista]) }
            if reabierto || rancio { para[p.rawValue] = p == .grabacion ? .pantalla : .leer }
            aplicar(ciclo.alArrancar(p.rawValue, concedido: concedido, loTuvo: p.loTuvo, rancio: rancio,
                                     reabierto: reabierto, ahora: ahora))
        }
    }

    /// Una herramienta necesita `q` y no está: la tarjeta (si no hay otra a la vista; si la hay, espera su turno). Si ya
    /// está a la vista, no se reinicia. `tuyo`: lo pediste tú desde el menú (vale aunque antes dijeras «Ahora no»).
    func pedir(_ q: Para, espera: Int? = nil, tuyo: Bool = false) {
        let p = q.permiso
        if para[p.rawValue] == nil || ciclo.visible != p.rawValue { para[p.rawValue] = q }
        aplicar(ciclo.pedir(p.rawValue, loTuvo: p.loTuvo, rancio: p.rancio, concedido: p.concedido, ahora: ahora,
                            espera: espera, tuyo: tuyo))
    }

    /// Pide `q` y espera a que llegue (a lo más `tope`): en cuanto llega, `listo(.listo)` y el pedido sigue solo; con
    /// «Ahora no», `.ahoraNo`; si no llega a tiempo, `.tarde` (la tarjeta se queda).
    func esperar(_ q: Para, tope: TimeInterval = Permisos.esperaTope, _ listo: @escaping (Llegada) -> Void) {
        if q.permiso.concedido { listo(.listo); return }
        sig += 1
        let id = sig
        esperas[id] = listo
        pedir(q, espera: id)
        DispatchQueue.main.asyncAfter(deadline: .now() + tope) { [weak self] in
            MainActor.assumeIsolated {
                guard let self = self, let f = self.esperas.removeValue(forKey: id) else { return }
                self.ciclo.vencer(id)
                f(.tarde)
            }
        }
    }

    /// ¿Dijiste «Ahora no» a ese permiso en esta sesión?
    func descartado(_ p: Permiso) -> Bool { ciclo.descartados.contains(p.rawValue) }

    /// La burbuja se volvió a cargar (manos_listo): la tarjeta que estaba a la vista vuelve a salir (la misma: no se
    /// cuenta otra vez en la bitácora).
    func repintar() {
        repintando = true
        aplicar(ciclo.repintar())
        repintando = false
    }
    private var repintando = false

    /// Lo que eligió el socio en la tarjeta.
    func accion(_ k: String, permiso: String) {
        guard Permiso(rawValue: permiso) != nil else { return }
        switch k {
        case "abrir":
            aplicar(ciclo.abrirAjustes(ahora: ahora))
        case "arreglar", "reiniciar_permiso", "reiniciar_si":      // (los dos últimos: la burbuja de antes)
            aplicar(ciclo.abrirAjustes(ahora: ahora, arreglar: true))
        case "ver_ajustes":
            aplicar(ciclo.verAjustes(ahora: ahora))
        case "ya":
            aplicar(ciclo.ya(concedido: Permiso(rawValue: permiso)?.concedido ?? false, ahora: ahora))
        case "reiniciar":
            aplicar(ciclo.reabrirAhora())
        default:                     // «Ahora no» (o la ×): se cierra y sale la que esperaba
            aplicar(ciclo.cerrar(permiso, concedido: concedidos, ahora: ahora))
        }
    }

    /// Lo que decidió el ciclo → la burbuja y macOS. El reloj de 1 s corre solo mientras hay una tarjeta.
    private func aplicar(_ efectos: [CicloPermiso.Efecto]) {
        for e in efectos {
            switch e {
            case .mostrar(let p, let f):
                let t = ciclo.tarjeta
                let q = queDe(p)
                let texto = TextoPermiso.pide(q.frase, permiso: p, rancio: t?.rancio ?? false, estable: EstaApp.estable)
                js("WSMManos.permiso(\(Permisos.json(["id": p, "permiso": p, "texto": texto, "nota": TextoPermiso.nota(permiso: p, estable: EstaApp.estable), "boton": TextoPermiso.boton, "accion": "abrir"])))")
                if f != .pide { estado(p, f) }
                if !repintando { anotar?(["permiso": p, "paso": "tarjeta", "fase": f.rawValue, "rancio": t?.rancio ?? false]) }
            case .cambiar(let p, let f):
                estado(p, f)
                if f == .ajustes { Permiso(rawValue: p)?.enCurso = true }
                if f == .noLlega || f == .gracias { anotar?(["permiso": p, "paso": f.rawValue]) }
            case .cerrar(let p):
                js("WSMManos.permisoCerrar(\(Permisos.json(["id": p])))")
                anotar?(["permiso": p, "paso": "cerrada", "ahora_no": ciclo.descartados.contains(p)])
                Permiso(rawValue: p)?.enCurso = false
                if ciclo.visible == nil { para[p] = nil }
            case .empujon:
                js("(function(){try{var m=WSM.mono();if(m&&!WSM.quieto())m.salta(.5)}catch(e){}})()")
            case .reabrir:
                Permiso(rawValue: ciclo.visible ?? "")?.enCurso = true
                DispatchQueue.main.asyncAfter(deadline: .now() + 1.4) { Permisos.reabrir() }
            case .borrar(let p):
                guard let q = Permiso(rawValue: p) else { break }
                let ok = demo ? false : Permisos.reiniciar(q)
                q.loTuvo = false
                q.firmaVista = ""
                anotar?(["permiso": p, "paso": "borrar_renglon", "ok": ok, "id": EstaApp.id] as [String: Any])
            case .solicitar(let p):
                if ensayo || demo { anotar?(["permiso": p, "paso": "solicitar", "ensayo": true]) } else { Permiso(rawValue: p)?.registrar() }
            case .ajustes(let p):
                guard let q = Permiso(rawValue: p) else { break }
                if ensayo || demo { anotar?(["permiso": p, "paso": "abrir_ajustes", "ensayo": true]) } else {
                    // un respiro para que el aviso de macOS la ponga en la lista antes de enseñarla
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.35) { NSWorkspace.shared.open(q.ajustes) }
                }
            case .seguir(let ids):
                ids.forEach { esperas.removeValue(forKey: $0)?(.listo) }
            case .sinPermiso(let ids):
                ids.forEach { esperas.removeValue(forKey: $0)?(.ahoraNo) }
            }
        }
        if ciclo.visible != nil, reloj == nil {
            reloj = Timer.scheduledTimer(withTimeInterval: 1.0, repeats: true) { [weak self] _ in
                MainActor.assumeIsolated { self?.cadaSegundo() }
            }
        } else if ciclo.visible == nil {
            reloj?.invalidate(); reloj = nil
        }
    }

    private func queDe(_ p: String) -> Para { para[p] ?? (p == Permiso.grabacion.rawValue ? .pantalla : .leer) }

    private func cadaSegundo() {
        aplicar(ciclo.sondeo(concedidos, ahora: ahora, ocupado: ocupado?() ?? true))     // (concedido anota la firma)
    }

    /// El texto y los botones de cada estado (los de «espera» los pone la burbuja: «Ya lo prendí» · «Ahora no»).
    private func estado(_ p: String, _ f: CicloPermiso.Fase) {
        let q = queDe(p)
        let arreglos = ciclo.tarjeta?.arreglos ?? 0
        let texto: String
        switch f {
        case .pide: texto = TextoPermiso.pide(q.frase, permiso: p, rancio: ciclo.tarjeta?.rancio ?? false, estable: EstaApp.estable)
        case .ajustes: texto = TextoPermiso.ajustes(app: EstaApp.nombre, permiso: p)
        case .noLlega: texto = TextoPermiso.noLlega(permiso: p, app: EstaApp.nombre, arreglos: arreglos)
        case .reiniciar: texto = TextoPermiso.reiniciar
        case .reabre: texto = TextoPermiso.reabre
        case .gracias: texto = q.gracias
        }
        let botones: [[Any]] = TextoPermiso.botones(f, arreglos: arreglos).map { [$0.texto, $0.accion, $0.principal] }
        js("WSMManos.permisoEstado(\(Permisos.json(["id": p, "estado": f.rawValue, "texto": texto, "botones": botones])))")
    }

    private func js(_ s: String) { pintar?(s) }

    static func json(_ o: [String: Any]) -> String {
        (try? JSONSerialization.data(withJSONObject: o)).flatMap { String(data: $0, encoding: .utf8) } ?? "{}"
    }

    /// `tccutil reset <servicio> <identificador de esta app>`: borra solo ESE permiso de ESTA app. → ¿salió bien?
    @discardableResult
    static func reiniciar(_ p: Permiso) -> Bool {
        let args = Llega.reinicio(p.rawValue, id: EstaApp.id)
        guard !args.isEmpty else { return false }
        let t = Process()
        t.executableURL = URL(fileURLWithPath: "/usr/bin/tccutil")
        t.arguments = args
        t.standardOutput = FileHandle.nullDevice
        t.standardError = FileHandle.nullDevice
        do { try t.run() } catch { return false }
        t.waitUntilExit()
        return t.terminationStatus == 0
    }

    /// Se vuelve a abrir (la app, por LaunchServices, con sus opciones de al lado del paquete) y se cierra esta.
    static func reabrir() {
        let b = Bundle.main.bundleURL
        guard b.pathExtension == "app" else {
            NSApp.terminate(nil)       // sin paquete (modo terminal): quien lo abrió lo vuelve a abrir
            return
        }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/sh")
        // espera a que esta se cierre y abre otra (open -n: una nueva aunque esta siga viva un instante)
        p.arguments = ["-c", "sleep 1; /usr/bin/open -n -g \"$0\"", b.path]
        try? p.run()
        NSApp.terminate(nil)
    }
}
