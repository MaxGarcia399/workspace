// Ronda 2 · bloque G (chat grande) · la parte que se prueba suelta (escritorio/mac/Pruebas/PruebasGrande.swift): dónde y
// de qué tamaño va la ventana, qué se guarda entre reinicios y a quién le toca cada cosa que pide su página.
// Sin AppKit ni WebKit: solo números y texto.
import CoreGraphics
import Foundation

/// La ventana del chat grande recuerda su tamaño y su lugar (por cada arreglo de pantallas, como el nido) y si la
/// dejaste en grande o en chico. Vive en <estado>/escritorio/grande.json.
enum LugarGrande {
    /// Lo más chica que se deja: caben la tira, la plática y la caja de escribir.
    static let minimo = CGSize(width: 560, height: 420)
    /// La primera vez: como el boceto (la plática al centro y «Te esperan» a la derecha).
    static let fabrica = CGSize(width: 980, height: 660)
    /// Lo que debe quedar a la vista de su encabezado para poder tomarla y moverla.
    static let asomo = CGSize(width: 140, height: 40)

    /// La primera vez: centrada en lo visible de la pantalla, sin pasarse de ella.
    static func deFabrica(visible v: CGRect) -> CGRect {
        let w = max(minimo.width, min(fabrica.width, v.width - 80)), h = max(minimo.height, min(fabrica.height, v.height - 80))
        return CGRect(x: (v.midX - w / 2).rounded(), y: (v.midY - h / 2).rounded(), width: w.rounded(), height: h.rounded())
    }

    /// El marco guardado, si todavía sirve en estas pantallas: su tamaño dentro de lo razonable y su encabezado (la franja
    /// de arriba; AppKit cuenta desde abajo) a la vista en alguna. Si no (se desconectó esa pantalla, cambió la
    /// resolución), nil: la ventana vuelve al centro, nunca queda perdida fuera de la vista.
    static func valido(_ r: CGRect?, visibles: [CGRect]) -> CGRect? {
        guard var m = r, m.width.isFinite, m.height.isFinite, m.minX.isFinite, m.minY.isFinite, !visibles.isEmpty else { return nil }
        let grande = visibles.max(by: { $0.width * $0.height < $1.width * $1.height }) ?? visibles[0]
        m.size.width = max(minimo.width, min(m.width, max(minimo.width, grande.width)))
        let arriba = m.maxY                                   // el borde de arriba se queda donde estaba
        m.size.height = max(minimo.height, min(m.height, max(minimo.height, grande.height)))
        m.origin.y = arriba - m.height
        let cabeza = CGRect(x: m.minX, y: m.maxY - asomo.height, width: m.width, height: asomo.height)
        let seVe = visibles.contains { v in
            let c = v.intersection(cabeza)
            return !c.isNull && c.width >= asomo.width && c.height >= asomo.height - 1
        }
        return seVe ? m.integral : nil
    }

    /// grande.json → el modo («grande» o «chico») y el marco de ESTE arreglo de pantallas (si lo hay).
    static func leer(_ o: [String: Any]?, firma: String) -> (modo: String, marco: CGRect?) {
        let modo = (o?["modo"] as? String) == "grande" ? "grande" : "chico"
        guard let m = (o?["marcos"] as? [String: Any])?[firma] as? [Any] else { return (modo, nil) }
        let n = m.compactMap { ($0 as? NSNumber)?.doubleValue }
        guard n.count == 4, n.allSatisfy({ $0.isFinite }) else { return (modo, nil) }
        return (modo, CGRect(x: n[0], y: n[1], width: n[2], height: n[3]))
    }

    /// Lo que se guarda: el modo y el marco de este arreglo, sin perder los de otros arreglos (a lo más 12).
    static func guardar(modo: String, marco: CGRect?, firma: String, en anterior: [String: Any]?) -> [String: Any] {
        var marcos = (anterior?["marcos"] as? [String: Any]) ?? [:]
        if let m = marco, m.width.isFinite, m.height.isFinite {
            marcos[firma] = [Double(m.minX.rounded()), Double(m.minY.rounded()), Double(m.width.rounded()), Double(m.height.rounded())]
        }
        if marcos.count > 12 { for k in marcos.keys.sorted().prefix(marcos.count - 12) where k != firma { marcos[k] = nil } }
        return ["modo": modo == "grande" ? "grande" : "chico", "marcos": marcos]
    }
}

/// Lo que la página del chat grande le pide a la app. Es la MISMA página de la burbuja (las mismas piezas), así que
/// pide lo mismo; pero ahí no hay nido ni barra, y la app solo tiene UNA burbuja con manos: cada pedido tiene dueño.
enum OpsGrande {
    enum Dueno: Equatable {
        /// Es de la ventana misma (su tamaño, su asa, sus pruebas).
        case ventana
        /// Lo mismo que si lo pidiera la burbuja: mandar, responder, permitir, abrir una entrega… (Monito.mensaje).
        case app
        /// No viene al caso en la ventana (el nido, la barra, las manos, actuar): se ignora, no llega a nadie.
        case nada
    }

    static let propias: Set<String> = ["listo", "grande", "grande_asa", "grande_estado", "zonas_arrastre", "guion_log", "guion_foto", "guion_tamano"]
    static let ajenas: Set<String> = ["zonas", "barra", "llamar", "arrastrar", "mudanza", "medir", "volver"]

    static func destino(_ op: String) -> Dueno {
        if propias.contains(op) { return .ventana }
        if ajenas.contains(op) || op.hasPrefix("manos_") || op.hasPrefix("actuar_") || op.isEmpty { return .nada }
        return .app
    }

    /// Un enlace de la plática con «Abrir»: solo se abre una página limpia (la regla amarilla del portero); lo demás no
    /// se abre desde el chat. `conDatos` y `rara` vienen del portero (Destino.conDatos, Destino.direccionRara).
    /// → nil si se abre; si no, por qué no (para decírselo al socio).
    static func enlaceNoSeAbre(_ url: String, conDatos: Bool, rara: String?, tope: Int = 2000) -> String? {
        let u = url.trimmingCharacters(in: .whitespacesAndNewlines)
        let bajo = u.lowercased()
        guard bajo.hasPrefix("http://") || bajo.hasPrefix("https://") else { return "no es una página http ni https" }
        if u.count > tope { return "la dirección es muy larga" }
        if u.unicodeScalars.contains(where: { $0.value < 0x20 || $0.value == 0x7F }) { return "la dirección trae letras invisibles" }
        if conDatos { return "la dirección lleva datos (lo que va después de «?» o «#»)" }
        return rara
    }
}

/// Guardar y llamar al Compañero: UN solo modelo (23-nov).
///   · Tiene UN estado «abierto» (chico: la burbuja con su barra; o grande: su ventana) y UNO «guardado» (solo él en su nido).
///   · Todo lo que guarda hace lo mismo y esconde TODO: ⌥ Espacio estando abierto, un clic en él estando abierto, «─
///     Minimizar», Esc, «×» de la burbuja, cerrar la ventana y «Guardar» del menú de arriba.
///   · Llamarlo (⌥ Espacio, un clic, el menú) trae lo que estaba abierto, grande o chico, donde estaba.
///   · Cambiar de tamaño es otro control («⤢» a grande, «⤡ Chico» a chico) y nunca guarda.
/// Antes cada camino decidía por su cuenta: ⌥ Espacio con el grande a la vista lo pasaba a chico y un clic en el
/// Compañero solo traía la ventana al frente; no había forma de guardarlo todo con el mismo comando que lo abrió.
enum Compa {
    enum Gesto: CaseIterable, Hashable {
        /// ⌥ Espacio (un toque; mantenerlo es hablar).
        case atajo
        /// Un clic en el Compañero, sin arrastrarlo.
        case clicMonito
        /// «Llamar / Guardar a tu Compañero» en el menú de arriba.
        case menu
        /// «─ Minimizar» de la ventana grande.
        case minimizar
        /// Esc (en la burbuja o en la ventana grande) y «×» de la burbuja.
        case esc
        /// ⌘W o cerrar la ventana grande desde el sistema.
        case cerrarVentana
        /// «⤢»: el mismo chat, en su ventana grande.
        case agrandar
        /// «⤡ Chico»: el mismo chat, en la burbuja.
        case achicar
    }

    enum Paso: Equatable {
        /// Se esconde todo y queda solo el Compañero en su nido.
        case guardar
        /// Se abre así: «grande» o «chico».
        case abrir(String)
        case nada
    }

    static func abierto(grandeVisible: Bool, barraAbierta: Bool) -> Bool { grandeVisible || barraAbierta }

    /// Qué hace cada gesto, según lo que hay a la vista y cómo lo dejaste (`modo`: «grande» o «chico»).
    static func paso(_ g: Gesto, grandeVisible: Bool, barraAbierta: Bool, modo: String) -> Paso {
        let hay = abierto(grandeVisible: grandeVisible, barraAbierta: barraAbierta)
        switch g {
        case .atajo, .clicMonito, .menu:
            return hay ? .guardar : .abrir(modo == "grande" ? "grande" : "chico")
        case .minimizar, .esc, .cerrarVentana:
            return hay ? .guardar : .nada
        case .agrandar:
            return .abrir("grande")
        case .achicar:
            return .abrir("chico")
        }
    }

    /// Cómo vuelve al llamarlo: como estaba al guardarlo (si ya estaba guardado, como ya estaba anotado).
    static func modoAlGuardar(grandeVisible: Bool, barraAbierta: Bool, modo: String) -> String {
        if grandeVisible { return "grande" }
        if barraAbierta { return "chico" }
        return modo == "grande" ? "grande" : "chico"
    }

    /// El renglón del menú de arriba dice lo que va a hacer.
    static func renglonMenu(abierto: Bool) -> String {
        (abierto ? "Guardar a tu Compañero" : "Llamar a tu Compañero") + "  (⌥ Espacio)"
    }
}

/// Un clic de una PERSONA (EventoReal) en un panel de la app: cuándo y dónde, en puntos de su página (desde arriba a la
/// izquierda). Lo anota AppKit; la página no puede fabricarlo.
struct ClicReal: Equatable {
    var cuando: Date
    var punto: CGPoint
}

/// Un botón pedido desde una PÁGINA de la app (un botón de ficha, «Abrir» de un enlace) solo vale si hubo un clic de una
/// persona hace un instante, EN ESE MISMO panel y SOBRE ESE botón (M-3: ya no «cualquier clic en la ventana»), y ese
/// clic vale UNA vez: se gasta al usarlo. El clic de la burbuja no aprueba lo que pide la ventana, ni al revés (cada
/// panel lleva el suyo).
enum ClicFicha {
    /// Lo que dura un clic para contar.
    static let vigencia: TimeInterval = 0.6
    /// Lo más que mide un botón de verdad (uno de ficha: hasta ~310 × 36). Un «botón» del tamaño de la ventana no lo es.
    static let anchoMax: CGFloat = 420
    static let altoMax: CGFloat = 64
    static let holgura: CGFloat = 2

    /// El marco del botón que manda la página ([x, y, ancho, alto], de getBoundingClientRect), o nil si viene mal.
    static func marco(_ r: Any?) -> CGRect? {
        guard let l = r as? [Any], l.count == 4 else { return nil }
        let n = l.compactMap { ($0 as? NSNumber)?.doubleValue }
        guard n.count == 4, n.allSatisfy({ $0.isFinite }) else { return nil }
        return CGRect(x: n[0], y: n[1], width: n[2], height: n[3])
    }

    static func vale(_ c: ClicReal?, en boton: CGRect?, ahora: Date) -> Bool {
        guard let c = c, let b = boton, !b.isNull, !b.isInfinite, b.width > 0, b.height > 0, b.width <= anchoMax, b.height <= altoMax else { return false }
        let hace = ahora.timeIntervalSince(c.cuando)
        guard hace >= 0, hace < vigencia else { return false }
        return b.insetBy(dx: -holgura, dy: -holgura).contains(c.punto)
    }

    /// Lo mismo, y si valió el clic se gasta (no aprueba otra cosa).
    static func gastar(_ c: inout ClicReal?, en boton: CGRect?, ahora: Date) -> Bool {
        guard vale(c, en: boton, ahora: ahora) else { return false }
        c = nil
        return true
    }
}

/// M-3 · las ventanas de la app (la burbuja y el chat grande) solo cargan SU página, el archivo monito.html: ni un
/// enlace soltado encima, ni un `location = …`, ni un marco. Y el canal con la app (messageHandlers.ws) solo se le oye a
/// esa página, en su marco principal.
enum Navegacion {
    private static func esLaPropia(_ u: URL?, _ propia: URL) -> Bool {
        guard let u = u, u.isFileURL, propia.isFileURL, u.query == nil else { return false }
        // la ruta tal cual (sin «..» que resolver: una ruta con «..» no es la suya)
        guard !u.pathComponents.contains(".."), !u.pathComponents.contains(".") else { return false }
        return u.path == propia.path
    }

    static func permitida(_ u: URL?, propia: URL, marcoPrincipal: Bool) -> Bool {
        marcoPrincipal && esLaPropia(u, propia)
    }

    static func delCanal(_ origen: URL?, propia: URL, marcoPrincipal: Bool) -> Bool {
        marcoPrincipal && esLaPropia(origen, propia)
    }
}
