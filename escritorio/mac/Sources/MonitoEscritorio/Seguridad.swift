// La seguridad para actuar (A0, «seguridad primero»): todo lo que el monito pudiera hacer en la Mac pasa por aquí ANTES
// de existir la mano que lo hace.
//   · El color de cada acción, con UN solo clasificador (Clasificador.color) que usan todos los caminos que actúan:
//       verde · libre (ver, señalar, preguntar: D-79) · amarillo · con tu OK (abrir, escribir sin Enter, llenar sin
//       enviar, mover, renombrar) · naranja · OK cada vez (mandar, subir, compartir, borrar a la Papelera, aceptar un
//       aviso) · rojo · nunca (pagar, contraseñas y llavero, ajustes del sistema, instalar, Terminal, avisos de permisos,
//       banca): el monito solo puede señalar.
//     Lo decide lo que dice el SISTEMA del destino (la app, la ventana, el rol y el nombre del elemento, la ruta real),
//     no lo que dice el modelo. Si el modelo dice «Asunto» y el sistema dice «Contraseña», se cancela.
//   · Los vetados (no tocar / no mirar): los fijos (en código; no se quitan) y los tuyos (los agregas en el menú; un
//     archivo solo puede SUMAR, nunca quitar).
//   · La tarjeta de OK la arma la app con esos datos: un OK = una acción y un destino; si cambia la ventana, la página o
//     el elemento, se cancela; sale lejos del mouse; se activa a los 0.6 s y la naranja se sostiene 1.5 s.
//   · Los modos: en segundo plano (de fábrica: sin volar ni robarte el foco; solo un aviso con Deshacer), a la vista
//     (solo si lo pides: el monito vuela a cada control), enséñame (señala y tú lo haces) y con tu cursor (apagado:
//     «Puede tomar mi mouse: nunca» de fábrica, por agente).
//   · La etapa: «ensayo» (A0): nada se hace de verdad; el portero decide y anota, y después del OK el monito te enseña
//     dónde. «amarillo» (A1, primera parte): lo que la mano ya hace DE VERDAD (abrir: apps, archivos, carpetas, páginas
//     http/https y mostrar en Finder; LoQueHago) con su tarjeta; lo demás (escribir, llenar, apretar, mover…), te lo
//     enseña. La confianza, congelada hasta A3. «naranja» (A3) es para después.
//   · La confianza «confío en este agente para X en esta app»: agente × app (× sitio en un navegador) × solo amarillo;
//     vence al fin del día y se cae si en SU CONVERSACIÓN leyó otra fuente (tu pantalla u otro contenido ajeno: lo leído
//     en el turno 1 sigue en la cabeza del agente en el turno 2, Fable v2 §1.4). Vive en la memoria de la app (un
//     archivo no la crea); lo leído dura la conversación del agente hasta que el socio lo borre o empiece otra.
//   · Deshacer por tipo de acción y la bitácora local de lo que hizo (30 días).
//   · Ronda 2 (revisión v4: E1, H-1, H-2, H-3), en A1:
//       – Lo leído tiene GRADOS (Lecturas.grado): solo el nombre de la app y el título de la ventana no cuentan;
//         contenido en un turno anterior: una página limpia, normal; contenido en este turno (o un archivo ajeno):
//         siempre ficha, con la dirección entera y qué leyó. La marca se apaga al terminar el día y el socio la borra.
//       – Lo naranja de abrir una PÁGINA es una ficha coral con la dirección entera (ya no «no lo hago»). Lo que
//         engaña al leerlo (un usuario antes del sitio, un nombre disfrazado) es rojo: ni con ficha.
//       – Lo recordado (Recordados): «no me preguntes para abrir apps / archivos de tus carpetas / sitios conocidos»,
//         por TIPO, nunca más amplio, nunca lo coral, nunca en el turno en que leyó; solo con clics del socio. Lo que
//         pasa sin preguntar no puede llevar datos (una app, un documento, `https://sitio-conocido/`).
//       – El veredicto para la ficha (Ficha): cero · ficha ámbar · ficha coral · no. La arma la app con esto.
// Solo Foundation y CoreGraphics: se compila con la app, con sus pruebas (Pruebas/PruebasSeguridad.swift) y con el
// portero de línea de comandos de las pruebas de ataques (Herramientas/portero.swift). Usa Busqueda y Texto de
// Logica.swift.
import CoreGraphics
import Foundation

// MARK: colores

enum ColorAccion: String, Comparable, CaseIterable {
    case verde, amarillo, naranja, rojo

    var rango: Int {
        switch self {
        case .verde: return 0
        case .amarillo: return 1
        case .naranja: return 2
        case .rojo: return 3
        }
    }

    static func < (a: ColorAccion, b: ColorAccion) -> Bool { a.rango < b.rango }

    var nombre: String {
        switch self {
        case .verde: return "libre"
        case .amarillo: return "con tu OK"
        case .naranja: return "OK cada vez"
        case .rojo: return "nunca: lo haces tú"
        }
    }
}

// MARK: lo que se puede pedir (lista cerrada: lo que no está aquí es rojo)

enum TipoAccion: String, CaseIterable {
    case abrir, escribir, llenar, presionar, elegir, mover, renombrar, borrar, enviar, compartir, subir

    /// El color de partida; el destino puede subirlo (nunca bajarlo).
    var base: ColorAccion {
        switch self {
        case .abrir, .escribir, .llenar, .presionar, .elegir, .mover, .renombrar: return .amarillo
        case .borrar, .enviar, .compartir, .subir: return .naranja
        }
    }

    /// Lo de archivos (la ruta la resuelve el sistema).
    var deArchivo: Bool { self == .mover || self == .renombrar || self == .borrar }

    /// Lo que escribe un valor en un campo.
    var escribe: Bool { self == .escribir || self == .llenar }
}

// MARK: lo que dice el sistema del destino (la app lo lee; el modelo nunca lo escribe)

struct Destino: Equatable {
    var app: String = ""
    var bundle: String = ""
    var pid: Int32 = 0
    /// Workspace Compañero misma (su tarjeta de OK incluida): nunca se toca ni se mira.
    var propia: Bool = false
    var ventana: String? = nil
    var ventanaId: UInt32 = 0
    /// La URL de la ventana (navegador), si se pudo leer.
    var url: String? = nil
    /// AXRole / AXSubrole del elemento.
    var rol: String? = nil
    var subrol: String? = nil
    /// Su nombre según el sistema: título, descripción o marcador.
    var etiqueta: String? = nil
    /// Su valor de ahora (para deshacer).
    var valor: String? = nil
    var marco: CGRect? = nil
    /// Está dentro de una hoja o un diálogo (y su título).
    var enDialogo: Bool = false
    var dialogo: String? = nil
    /// Archivos: la ruta real (resuelta) y, al mover o renombrar, a dónde.
    var ruta: String? = nil
    var rutaDestino: String? = nil
    var destinoExiste: Bool = false
    /// Abrir: la dirección o la app que se pidió (resueltas por la app).
    var abrirURL: String? = nil
    var abrirApp: String? = nil
    /// Abrir un archivo o una dirección: la app que lo abriría (la predeterminada, según el sistema).
    var abrirCon: String? = nil
    /// La app de la ventana es un navegador (Fable v2 §1.2: si no se pudo leer su dirección, «sitio desconocido»).
    var navegador: Bool = false
    /// Un enlace: a dónde va (su AXURL), según el sistema.
    var enlace: String? = nil
    /// Abrir (A1): el nombre que da el sistema a la app que se abre (o a la que abriría el archivo o la página), si ya
    /// está abierta, si la ruta es una carpeta (no un paquete) y si es «mostrarlo en Finder» (no abrirlo).
    var abrirNombre: String? = nil
    var abrirAbierta: Bool = false
    var esCarpeta: Bool = false
    var enFinder: Bool = false
    /// La carpeta de inicio del socio (para las rutas protegidas).
    var casa: String = NSHomeDirectory()

    /// El sitio (host) de la ventana, en minúsculas y sin «www.».
    var sitio: String? { Destino.host(url) }

    /// Un navegador cuya dirección no se pudo leer: podría ser cualquier sitio (falla cerrado).
    var sitioDesconocido: Bool { navegador && sitio == nil }

    /// ¿La dirección lleva datos? (algo después de «?» o «#»: con datos, siempre naranja)
    static func conDatos(_ u: String?) -> Bool {
        guard let u = u else { return false }
        if let c = URLComponents(string: u), (c.query?.isEmpty == false || c.fragment?.isEmpty == false) { return true }
        return u.contains("?") || u.contains("#")
    }

    static func host(_ u: String?) -> String? {
        guard let u = u, let c = URLComponents(string: u), let h = c.host?.lowercased(), !h.isEmpty else { return nil }
        return h.hasPrefix("www.") ? String(h.dropFirst(4)) : h
    }

    /// A1 · una página que se puede abrir con una tarjeta amarilla: http o https, sin datos (?…, #…), sin usuario ni
    /// puerto, a un nombre de verdad (con punto; no un número ni un nombre disfrazado «xn--») y con un camino corto (hasta
    /// 40 letras y 3 pedazos: un camino largo también puede llevar datos). nil si es así; si no, por qué (naranja).
    static func direccionRara(_ u: String) -> String? {
        guard let c = URLComponents(string: u), let esq = c.scheme?.lowercased(), esq == "http" || esq == "https" else {
            return "no es una página http ni https"
        }
        if c.user != nil || c.password != nil { return "la dirección lleva un usuario" }
        if let p = c.port, p != 80 && p != 443 { return "la dirección va a otro puerto" }
        guard let h = c.host?.lowercased(), h.contains("."), !h.hasPrefix("."), !h.hasSuffix(".") else { return "no va a un sitio con nombre" }
        if h.allSatisfy({ $0.isNumber || $0 == "." }) || h.contains(":") { return "va a un número (IP), no a un sitio con nombre" }
        // un nombre con letras de otros alfabetos (o su forma «xn--») puede disfrazarse de otro sitio
        let crudo = (c.percentEncodedHost ?? h).lowercased()
        if crudo.contains("xn--") || h.contains("xn--") || !h.unicodeScalars.allSatisfy({ $0.isASCII }) || crudo.contains("%") {
            return "el nombre del sitio está disfrazado (xn--)"
        }
        let camino = c.percentEncodedPath
        if camino.count > 41 || camino.split(separator: "/").count > 3 { return "el camino de la dirección es largo (podría llevar datos)" }
        return nil
    }

    /// Ronda 2 (H-1, H-3) · «solo el sitio»: `https://nombre/` y nada más (sin camino, sin datos, sin puerto, sin usuario,
    /// un nombre de letras comunes). Una dirección así no puede llevar nada escondido salvo su propio nombre. Se revisa la
    /// dirección TAL CUAL (letra por letra), no solo lo que entiende quien la parte: lo raro no pasa. `soloHttps`: para
    /// abrir sin preguntar, además tiene que ser https.
    static func soloElSitio(_ u: String, soloHttps: Bool = false) -> Bool {
        guard u.unicodeScalars.allSatisfy({ $0.isASCII }) else { return false }
        let l = u.lowercased()
        var resto: Substring
        if l.hasPrefix("https://") { resto = l.dropFirst(8) } else if l.hasPrefix("http://"), !soloHttps { resto = l.dropFirst(7) } else { return false }
        if resto.hasSuffix("/") { resto = resto.dropLast() }
        guard !resto.isEmpty, resto.allSatisfy({ ($0 >= "a" && $0 <= "z") || ($0 >= "0" && $0 <= "9") || $0 == "." || $0 == "-" }) else { return false }
        return direccionRara(u) == nil && !conDatos(u) && direccionDisfrazada(u) == nil
    }

    /// Ronda 2 · una dirección que ENGAÑA al leerla en la ficha: lleva un usuario («https://banco.com@otro.io»: se lee el
    /// primero y va al segundo), una diagonal invertida o un espacio, o el nombre del sitio está escrito con letras de otro
    /// alfabeto (o su forma «xn--», o con «%»). Esas no se abren ni con ficha: la ficha enseñaría algo que parece otro
    /// sitio. nil si no engaña; si sí, por qué.
    static func direccionDisfrazada(_ u: String) -> String? {
        let l = u.lowercased()
        guard l.hasPrefix("http://") || l.hasPrefix("https://") else { return nil }
        if u.contains("\\") || u.contains(where: { $0.isWhitespace }) { return "la dirección lleva una diagonal invertida o un espacio" }
        let sinEsquema = l.dropFirst(l.hasPrefix("https://") ? 8 : 7)
        let autoridad = sinEsquema.prefix { $0 != "/" && $0 != "?" && $0 != "#" }
        if autoridad.contains("@") { return "la dirección lleva un usuario antes del sitio (se lee un sitio y va a otro)" }
        if autoridad.contains("%") || autoridad.contains("xn--") || !autoridad.unicodeScalars.allSatisfy({ $0.isASCII }) {
            return "el nombre del sitio está disfrazado (letras de otro alfabeto, «xn--» o «%»)"
        }
        if let c = URLComponents(string: u) {
            if c.user != nil || c.password != nil { return "la dirección lleva un usuario antes del sitio (se lee un sitio y va a otro)" }
            let h = (c.host ?? "").lowercased(), crudo = (c.percentEncodedHost ?? h).lowercased()
            if crudo.contains("xn--") || h.contains("xn--") || crudo.contains("%") || !h.unicodeScalars.allSatisfy({ $0.isASCII }) {
                return "el nombre del sitio está disfrazado (letras de otro alfabeto, «xn--» o «%»)"
            }
        }
        return nil
    }

    /// ¿Es una ventana privada del navegador? (lo dice su título)
    var privada: Bool {
        guard let v = ventana.map(Busqueda.normal) else { return false }
        return ["private browsing", "navegacion privada", "incognito", "inprivate", "ventana privada", "modo privado"]
            .contains { (" " + v + " ").contains(" " + $0 + " ") }
    }
}

// MARK: carril 6 (manos de trabajo) · el borrador de correo: un mailto que arma la APP (solo para, asunto y texto)

/// Un borrador de correo (H3-a): se abre en la app de correo del socio y NUNCA se envía solo («Enviar» lo aprieta él).
/// Viaja como un `mailto:` que arma la app, letra por letra: solo las direcciones, `subject` y `body`, en ese orden y una
/// vez cada uno; nada de lo que escriba el agente puede volverse otro encabezado (cc, bcc, otro body, un adjunto). Un
/// mailto que no sea EXACTAMENTE así no es un borrador (para el portero es «una dirección con datos», como siempre).
/// Los mismos casos que Python (escritorio/reglas/casos_correo.json).
struct Borrador: Equatable {
    var para: [String]
    var asunto: String
    var texto: String

    static let maxPara = 5
    static let maxDireccion = 100
    static let maxAsunto = 150
    static let maxTexto = 1200
    static let maxMailto = 2000
    /// Carril 1 (portero): renglones vacíos seguidos y renglones en total que caben a la vista en la ficha.
    static let maxVacios = 2
    static let maxRenglones = 40

    /// ¿El texto trae relleno que escondería parte del correo en la ficha? nil si no; si sí, por qué.
    static func relleno(_ texto: String) -> String? {
        let renglones = texto.replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\r", with: "\n")
            .split(separator: "\n", omittingEmptySubsequences: false)
        if renglones.count > maxRenglones { return "El texto lleva más renglones de los que la ficha enseña a la vista (máximo \(maxRenglones)): acórtalo." }
        var seguidos = 0
        for r in renglones {
            seguidos = r.allSatisfy({ $0.isWhitespace }) ? seguidos + 1 : 0
            if seguidos > maxVacios { return "El texto lleva muchos renglones vacíos seguidos (máximo \(maxVacios)): quítalos." }
        }
        return nil
    }

    /// Una dirección sola (ana@ejemplo.com): letras comunes, sin nombre, sin espacios, sin «?», «&», «%» ni comas.
    static func direccion(_ d: String) -> Bool {
        guard d.count <= maxDireccion, d.unicodeScalars.allSatisfy({ $0.isASCII }) else { return false }
        let partes = d.split(separator: "@", omittingEmptySubsequences: false)
        guard partes.count == 2, !partes[0].isEmpty else { return false }
        func letra(_ c: Character) -> Bool { c.isASCII && (c.isLetter || c.isNumber) }
        guard partes[0].allSatisfy({ letra($0) || "._+-".contains($0) }) else { return false }
        let sitio = partes[1].split(separator: ".", omittingEmptySubsequences: false)
        return sitio.count >= 2 && sitio.allSatisfy { !$0.isEmpty && $0.allSatisfy { letra($0) || $0 == "-" } }
    }

    private static let libres = CharacterSet(charactersIn: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")

    private static func pct(_ s: String) -> String { s.addingPercentEncoding(withAllowedCharacters: libres) ?? "" }

    /// (el mailto, nil) o (nil, por qué no).
    static func armar(para: [String], asunto: String, texto: String) -> (String?, String?) {
        if para.count > maxPara { return (nil, "Un borrador lleva hasta \(maxPara) destinatarios.") }
        for d in para where !direccion(d) {
            return (nil, "«\(Texto.limpio(d, tope: 60) ?? "")» no es una dirección de correo sola (como ana@ejemplo.com): sin nombre, sin copia y una por renglón.")
        }
        if asunto.unicodeScalars.contains(where: { $0 == "\n" || $0 == "\r" }) { return (nil, "El asunto va en un solo renglón.") }   // por letra: «\r\n» junto es UN carácter para Swift
        if PedidoAccion.invisible(asunto) || PedidoAccion.invisible(texto) { return (nil, "El correo lleva caracteres invisibles: no lo preparo.") }
        if asunto.count > maxAsunto { return (nil, "El asunto es más largo de lo que la ficha enseña entero (máximo \(maxAsunto) letras).") }
        if texto.count > maxTexto {
            return (nil, "El texto es más largo de lo que la ficha enseña entero (máximo \(maxTexto) letras): acórtalo o propónselo como encargo (encargar, plantilla «correo»).")
        }
        if asunto.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && texto.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            return (nil, "El correo no lleva asunto ni texto.")
        }
        // carril 1 (portero) · lo que no se ve no se aprueba: un texto con renglones vacíos de relleno empuja lo que sigue
        // fuera de lo que el socio alcanza a leer en la ficha. Hasta `maxVacios` renglones vacíos seguidos y `maxRenglones`.
        if let por = relleno(texto) { return (nil, por) }
        let cuerpo = texto.replacingOccurrences(of: "\r\n", with: "\n").replacingOccurrences(of: "\r", with: "\n")
            .replacingOccurrences(of: "\n", with: "\r\n")
        let u = "mailto:" + para.map { pct($0).replacingOccurrences(of: "%40", with: "@") }.joined(separator: ",")
            + "?subject=" + pct(asunto) + "&body=" + pct(cuerpo)
        if u.utf8.count > maxMailto {
            return (nil, "El correo es más largo de lo que cabe en un borrador (con acentos y renglones pesa más): acórtalo o propónselo como encargo (encargar, plantilla «correo»).")
        }
        return (u, nil)
    }

    /// Los argumentos de `redactar_correo` → el borrador, o el error en una frase. Nada más que para, asunto y texto.
    static func leer(_ a: [String: Any]) -> (Borrador?, String?) {
        if let extra = a.keys.sorted().first(where: { !["para", "asunto", "texto"].contains($0) }) {
            return (nil, "Un borrador solo lleva para, asunto y texto (no «\(Texto.limpio(extra, tope: 30) ?? "")»): no hay copia ni copia oculta.")
        }
        var para: [String] = []
        if let l = a["para"] as? [Any] {
            for x in l {
                guard let d = x as? String else { return (nil, "«para» es una lista de direcciones.") }
                para.append(d)
            }
        } else if let d = a["para"] as? String {
            if !d.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { para = [d] }
        } else if a["para"] != nil, !(a["para"] is NSNull) {
            return (nil, "«para» es una lista de direcciones.")
        }
        guard let asunto = a["asunto"] as? String, let texto = a["texto"] as? String else { return (nil, "Faltan «asunto» y «texto».") }
        let (u, e) = armar(para: para, asunto: asunto, texto: texto)
        guard let m = u, let b = de(m) else { return (nil, e ?? "No pude armar el borrador.") }
        return (b, nil)
    }

    /// El mailto de este borrador (ya revisado).
    var mailto: String? { Borrador.armar(para: para, asunto: asunto, texto: texto).0 }

    /// El borrador de un mailto LIMPIO, o nil si no es exactamente lo que arma `armar` (otro encabezado, dos body, otro
    /// orden, algo sin codificar, una letra invisible…).
    static func de(_ u: String) -> Borrador? {
        guard u.hasPrefix("mailto:"), u.utf8.count <= maxMailto else { return nil }
        let resto = String(u.dropFirst("mailto:".count))
        guard resto.filter({ $0 == "?" }).count == 1, !resto.contains("#") else { return nil }
        let dos = resto.split(separator: "?", maxSplits: 1, omittingEmptySubsequences: false).map(String.init)
        guard dos.count == 2 else { return nil }
        let q = dos[1].split(separator: "&", omittingEmptySubsequences: false).map(String.init)
        guard q.count == 2, q[0].hasPrefix("subject="), q[1].hasPrefix("body=") else { return nil }
        var para: [String] = []
        if !dos[0].isEmpty {
            for x in dos[0].split(separator: ",", omittingEmptySubsequences: false) {
                guard let d = String(x).removingPercentEncoding else { return nil }
                para.append(d)
            }
        }
        guard let asunto = String(q[0].dropFirst("subject=".count)).removingPercentEncoding,
              let cuerpo = String(q[1].dropFirst("body=".count)).removingPercentEncoding else { return nil }
        let texto = cuerpo.replacingOccurrences(of: "\r\n", with: "\n")
        guard armar(para: para, asunto: asunto, texto: texto).0 == u else { return nil }
        return Borrador(para: para, asunto: asunto, texto: texto)
    }

    /// ¿Esta dirección es un borrador limpio?
    static func es(_ u: String?) -> Bool { u.flatMap(de) != nil }

    /// El sello de ESTA app (uno nuevo cada vez que arranca; no sale del proceso): solo un pedido que la app armó con
    /// `redactar_correo` lo lleva (`_borrador`). Un `actuar(abrir, url: "mailto:…")` que arme el agente, aunque tenga la
    /// misma forma, NO es un borrador: sigue siendo «una dirección con datos» (no se hace), como siempre.
    static let sello = UUID().uuidString

    /// junto5 · la ÚNICA puerta por la que un borrador recibe el sello: sus tres datos → se arma, se revisa y se sella con
    /// el sello de ESTE arranque. La usan `redactar_correo` (Trabajo.correo) y «aprobar después» (que guarda solo para,
    /// asunto y texto: el sello nunca se guarda). → los argumentos para Actuar.atender / PedidoAccion.leer, o el error.
    static func sellado(_ a: [String: Any]) -> ([String: Any]?, String?) {
        let (b, e) = leer(a)
        guard let u = b?.mailto else { return (nil, e ?? "No pude armar el borrador.") }
        return (["accion": "abrir", "url": u, "_borrador": sello], nil)
    }

    /// ¿Este pedido es un borrador que armó la app? (su sello y un mailto limpio)
    static func es(_ p: PedidoAccion, _ d: Destino?) -> Bool { p.borrador && p.tipoConocido == .abrir && es(d?.abrirURL) }

    /// «Ana (ana@ejemplo.com)» no: solo las direcciones, como van.
    var paraQuien: String { para.isEmpty ? "sin destinatario (lo pones tú)" : para.joined(separator: ", ") }
}

// MARK: lo que pide el modelo (nunca es la autoridad: solo dice el tipo y a qué apunta)

struct CampoPedido: Equatable {
    var elemento: Int? = nil
    var texto: String? = nil
    var valor: String = ""
}

struct PedidoAccion: Equatable {
    var tipo: String
    /// Cómo cree el modelo que se llama el elemento (si lo dijo): si no se parece a lo que dice el sistema, se cancela.
    var esperado: String? = nil
    var elemento: Int? = nil
    var texto: String? = nil
    var valor: String? = nil
    var campos: [CampoPedido] = []
    var ruta: String? = nil
    var destino: String? = nil
    var url: String? = nil
    var app: String? = nil
    /// segundo_plano (de fábrica) · a_la_vista · ensename · con_tu_cursor
    var modo: String? = nil
    /// Abrir (A1): «el archivo que tengo seleccionado en Finder» (la app lee cuál) y «enséñamelo en Finder» (no abrirlo).
    var seleccionado: Bool = false
    var enFinder: Bool = false
    /// Carril 6 · el pedido lo armó la APP con `redactar_correo` (lleva su sello): un borrador de correo. El agente no lo
    /// puede poner (lo que llega del puerto local pierde las llaves que empiezan con «_», y el sello no sale del proceso).
    var borrador: Bool = false

    var tipoConocido: TipoAccion? { TipoAccion(rawValue: tipo) }

    static let maxCampos = 10
    /// Fable v2 §1.5: lo que no se ve no se aprueba. Lo más que se pide es lo que la tarjeta enseña ENTERO: un texto de
    /// hasta 300 letras, un campo de un lote de hasta 120 (600 en total) y una dirección de hasta 300.
    static let maxValor = 300
    static let maxCampo = 120
    static let maxLote = 600
    static let maxURL = 300

    /// ¿Lleva algo que no se ve en la tarjeta? (controles salvo Enter y tab; de formato: ancho cero, dirección del texto)
    static func invisible(_ s: String) -> Bool {
        s.unicodeScalars.contains { u in
            if u == "\n" || u == "\r" || u == "\t" { return false }
            if CharacterSet.controlCharacters.contains(u) { return true }
            return u.properties.generalCategory == .format
        }
    }

    /// Los argumentos de `actuar` (manos_mcp) → el pedido, o el error en una frase.
    static func leer(_ a: [String: Any]) -> (PedidoAccion?, String?) {
        guard let t = (a["accion"] as? String).flatMap({ Texto.limpio($0, tope: 40) }) else {
            return (nil, "Falta «accion»: abrir, escribir, llenar, presionar, elegir, mover, renombrar, borrar, enviar, compartir o subir.")
        }
        func num(_ v: Any?) -> Int? {
            if let n = v as? NSNumber, !(v is Bool) { return n.intValue }
            return nil
        }
        func cad(_ k: String, _ tope: Int = 1000) -> String? { (a[k] as? String).flatMap { Texto.limpio($0, tope: tope) } }
        var p = PedidoAccion(tipo: t.lowercased())
        p.esperado = cad("esperado", 120)
        p.elemento = num(a["elemento"])
        p.texto = cad("texto", 120)
        if let v = a["valor"] as? String {
            guard v.count <= maxValor else {
                return (nil, "El texto es más largo de lo que la tarjeta enseña entero (máximo \(maxValor) letras): pártelo.")
            }
            guard !invisible(v) else { return (nil, "El texto lleva caracteres invisibles: no lo escribo.") }
            p.valor = v
        }
        p.ruta = cad("ruta")
        p.destino = cad("destino")
        // carril 6: un borrador que armó la app (su sello) se enseña por renglones, entero: puede pasar de 300 letras
        let esBorrador = (a["_borrador"] as? String) == Borrador.sello && Borrador.es(a["url"] as? String)
        if let u = a["url"] as? String, !esBorrador {
            guard u.count <= maxURL else {
                return (nil, "La dirección es más larga de lo que la tarjeta enseña entera (máximo \(maxURL) letras).")
            }
            guard !invisible(u) else { return (nil, "La dirección lleva caracteres invisibles: no la abro.") }
        }
        p.url = esBorrador ? (a["url"] as? String) : cad("url", maxURL)
        p.borrador = esBorrador
        p.app = cad("app", 200)
        p.modo = cad("modo", 30)
        // solo un sí de verdad (un booleano de JSON, no «sí» ni 1)
        func si(_ v: Any?) -> Bool { (v as? NSNumber).map { CFGetTypeID($0) == CFBooleanGetTypeID() && $0.boolValue } ?? false }
        p.seleccionado = si(a["seleccionado"])
        p.enFinder = si(a["en_finder"])
        if let cs = a["campos"] as? [[String: Any]] {
            guard cs.count <= maxCampos else { return (nil, "Un lote llena hasta \(maxCampos) campos.") }
            for c in cs {
                guard let v = c["valor"] as? String else { return (nil, "Cada campo lleva su «valor».") }
                guard v.count <= maxCampo else {
                    return (nil, "Un campo es más largo de lo que la tarjeta enseña entero (máximo \(maxCampo) letras).")
                }
                guard !invisible(v) else { return (nil, "Un campo lleva caracteres invisibles: no lo lleno.") }
                p.campos.append(CampoPedido(elemento: num(c["elemento"]), texto: (c["texto"] as? String).flatMap { Texto.limpio($0, tope: 120) }, valor: v))
            }
            guard p.campos.reduce(0, { $0 + $1.valor.count }) <= maxLote else {
                return (nil, "El lote es más largo de lo que la tarjeta enseña entero (máximo \(maxLote) letras en total).")
            }
        }
        return (p, nil)
    }
}

// MARK: los vetados (no tocar / no mirar)

enum QueVeta: String {
    case noTocar = "no_tocar"
    /// No mirar incluye no tocar.
    case noMirar = "no_mirar"
}

struct Vetado: Equatable {
    /// app (bundle; con «*» al final es un prefijo) · sitio (host y sus subdominios) · titulo (lo contiene la ventana)
    var tipo: String
    var valor: String
    var nombre: String
    var que: QueVeta
    /// Los de fábrica: están en el código y no se quitan.
    var fijo: Bool = false

    var id: String { tipo + ":" + valor.lowercased() }

    func aplica(_ d: Destino) -> Bool {
        let v = valor.lowercased()
        switch tipo {
        case "app":
            let b = d.bundle.lowercased()
            if v.hasSuffix("*") { return !b.isEmpty && b.hasPrefix(String(v.dropLast())) }
            let pedida = d.abrirApp?.lowercased()
            return b == v || pedida == v
        case "sitio":
            for h in [d.sitio, Destino.host(d.abrirURL)].compactMap({ $0 }) where h == v || h.hasSuffix("." + v) { return true }
            // un navegador sin dirección legible (Fable v2 §1.2): los de fábrica, por su nombre en la ventana
            if d.sitioDesconocido, fijo, nombre.count >= 4 {
                let t = Busqueda.normal(d.ventana ?? ""), n = Busqueda.normal(nombre)
                if !t.isEmpty, !n.isEmpty, (" " + t + " ").contains(" " + n + " ") { return true }
            }
            return false
        case "titulo":
            let t = Busqueda.normal(d.ventana ?? "")
            return !t.isEmpty && (" " + t + " ").contains(" " + Busqueda.normal(v) + " ")
        default:
            return false
        }
    }

    func json() -> [String: Any] { ["tipo": tipo, "valor": valor, "nombre": nombre, "que": que.rawValue, "fijo": fijo] }

    static func deJSON(_ o: [String: Any]) -> Vetado? {
        guard let t = o["tipo"] as? String, ["app", "sitio", "titulo"].contains(t),
              let v = (o["valor"] as? String).flatMap({ Texto.limpio($0, tope: 200) }) else { return nil }
        let q = QueVeta(rawValue: (o["que"] as? String) ?? "") ?? .noTocar
        return Vetado(tipo: t, valor: v, nombre: (o["nombre"] as? String).flatMap { Texto.limpio($0, tope: 80) } ?? v, que: q, fijo: false)
    }
}

struct Vetados: Equatable {
    static func app(_ b: String, _ n: String, _ q: QueVeta = .noTocar) -> Vetado { Vetado(tipo: "app", valor: b, nombre: n, que: q, fijo: true) }
    static func sitio(_ h: String, _ n: String, _ q: QueVeta = .noMirar) -> Vetado { Vetado(tipo: "sitio", valor: h, nombre: n, que: q, fijo: true) }

    /// Los de fábrica: los de las reglas (escritorio/reglas/portero.json), que siempre incluyen el núcleo de abajo.
    static var fijos: [Vetado] { Reglas.actual.vetados }

    /// El núcleo de los de fábrica (rojo en código: no se quita aunque falte el archivo). Terminales, ajustes,
    /// instaladores y avisos del sistema: no tocar (mirar sí, para explicarte). Contraseñas, llavero, banca y ventanas
    /// privadas: ni mirar.
    static let nucleo: [Vetado] = [
        app("com.apple.Terminal", "Terminal"), app("com.googlecode.iterm2", "iTerm"), app("dev.warp.Warp-Stable", "Warp"),
        app("net.kovidgoyal.kitty", "kitty"), app("org.alacritty", "Alacritty"), app("io.alacritty", "Alacritty"),
        app("com.github.wez.wezterm", "WezTerm"), app("co.zeit.hyper", "Hyper"), app("com.mitchellh.ghostty", "Ghostty"),
        app("com.apple.systempreferences", "Ajustes del Sistema"), app("com.apple.preference.*", "Ajustes del Sistema"),
        app("com.apple.settings.*", "Ajustes del Sistema"), app("com.apple.Settings", "Ajustes del Sistema"),
        app("com.apple.installer", "Instalador"), app("com.apple.SecurityAgent", "Aviso de contraseña del sistema"),
        app("com.apple.coreservices.uiagent", "Avisos de seguridad del sistema"),
        app("com.apple.UserNotificationCenter", "Avisos del sistema"),
        app("com.apple.LocalAuthentication.UIAgent", "Touch ID"), app("com.apple.AppStore", "App Store"),
        app("com.apple.ScriptEditor2", "Editor de Scripts"), app("com.apple.Automator", "Automator"),
        app("com.apple.shortcuts", "Atajos"), app("com.apple.ActivityMonitor", "Monitor de Actividad"),
        app("com.apple.DiskUtility", "Utilidad de Discos"),
        app("com.apple.keychainaccess", "Acceso a Llaveros", .noMirar), app("com.apple.Passwords", "Contraseñas", .noMirar),
        app("com.1password.1password", "1Password", .noMirar), app("com.agilebits.onepassword7", "1Password", .noMirar),
        app("com.agilebits.onepassword-osx", "1Password", .noMirar), app("com.bitwarden.desktop", "Bitwarden", .noMirar),
        app("com.lastpass.LastPass", "LastPass", .noMirar), app("com.dashlane.dashlanephonefinal", "Dashlane", .noMirar),
        app("in.sinew.Enpass-Desktop", "Enpass", .noMirar), app("org.keepassxc.keepassxc", "KeePassXC", .noMirar),
        app("com.nordsec.nordpass", "NordPass", .noMirar),
        // banca y pagos (México y los de siempre); los tuyos los agregas en el menú de Compañero
        sitio("bbva.mx", "BBVA"), sitio("bbva.com", "BBVA"), sitio("banorte.com", "Banorte"),
        sitio("santander.com.mx", "Santander"), sitio("banamex.com", "Banamex"), sitio("citibanamex.com", "Citibanamex"),
        sitio("hsbc.com.mx", "HSBC"), sitio("scotiabank.com.mx", "Scotiabank"), sitio("inbursa.com", "Inbursa"),
        sitio("bancoazteca.com.mx", "Banco Azteca"), sitio("banregio.com", "Banregio"), sitio("bancoppel.com", "BanCoppel"),
        sitio("bb.com.mx", "BanBajío"), sitio("afirme.com", "Afirme"), sitio("nu.com.mx", "Nu"),
        sitio("heybanco.com", "Hey Banco"), sitio("mercadopago.com.mx", "Mercado Pago"), sitio("mercadopago.com", "Mercado Pago"),
        sitio("paypal.com", "PayPal"), sitio("chase.com", "Chase"), sitio("bankofamerica.com", "Bank of America"),
        sitio("wellsfargo.com", "Wells Fargo"), sitio("citi.com", "Citi"), sitio("capitalone.com", "Capital One"),
        sitio("americanexpress.com", "American Express"), sitio("wise.com", "Wise"), sitio("revolut.com", "Revolut"),
        sitio("coinbase.com", "Coinbase"), sitio("binance.com", "Binance"), sitio("dashboard.stripe.com", "Stripe"),
        sitio("vault.bitwarden.com", "Bitwarden"), sitio("1password.com", "1Password"), sitio("lastpass.com", "LastPass"),
        // donde viven tus contraseñas de cuenta: mirar sí (para explicarte), tocar no
        sitio("accounts.google.com", "Cuenta de Google", .noTocar), sitio("myaccount.google.com", "Cuenta de Google", .noTocar),
        sitio("appleid.apple.com", "Cuenta de Apple", .noTocar), sitio("account.apple.com", "Cuenta de Apple", .noTocar),
        sitio("login.microsoftonline.com", "Cuenta de Microsoft", .noTocar), sitio("account.microsoft.com", "Cuenta de Microsoft", .noTocar),
        Vetado(tipo: "titulo", valor: "Private Browsing", nombre: "Ventanas privadas", que: .noMirar, fijo: true),
        Vetado(tipo: "titulo", valor: "Navegación privada", nombre: "Ventanas privadas", que: .noMirar, fijo: true),
        Vetado(tipo: "titulo", valor: "Incognito", nombre: "Ventanas privadas", que: .noMirar, fijo: true),
        Vetado(tipo: "titulo", valor: "InPrivate", nombre: "Ventanas privadas", que: .noMirar, fijo: true),
    ]

    var propios: [Vetado] = []

    var todos: [Vetado] { Vetados.fijos + propios }

    /// El más estricto que aplica (no mirar antes que no tocar), o nil.
    func revisar(_ d: Destino) -> Vetado? {
        let v = todos.filter { $0.aplica(d) }
        return v.first { $0.que == .noMirar } ?? v.first
    }

    /// Si no se puede MIRAR (leer la ventana, la foto, lo de enfrente): el vetado, o nil.
    func noMirar(_ d: Destino) -> Vetado? {
        if d.propia { return Vetado(tipo: "app", valor: d.bundle, nombre: "La tarjeta del monito", que: .noMirar, fijo: true) }
        if d.privada { return Vetado(tipo: "titulo", valor: d.ventana ?? "", nombre: "Ventanas privadas", que: .noMirar, fijo: true) }
        return todos.first { $0.que == .noMirar && $0.aplica(d) }
    }

    /// Agregar uno tuyo (desde el menú de Compañero). → false si ya estaba.
    @discardableResult
    mutating func agregar(_ v: Vetado) -> Bool {
        var n = v
        n.fijo = false
        guard !todos.contains(where: { $0.id == n.id && ($0.que == n.que || $0.que == .noMirar) }) else { return false }
        propios.removeAll { $0.id == n.id }
        propios.append(n)
        return true
    }

    /// Quitar uno tuyo (solo desde el menú de Compañero). Los fijos no se quitan.
    @discardableResult
    mutating func quitar(_ id: String) -> Bool {
        guard !Vetados.fijos.contains(where: { $0.id == id }) else { return false }
        let antes = propios.count
        propios.removeAll { $0.id == id }
        return propios.count != antes
    }

    /// Lo que diga un archivo (vetados.json) solo SUMA a los que ya había: quitar uno es desde el menú de Compañero, así
    /// un programa que escriba ese archivo no puede abrirle la puerta a nada.
    mutating func sumarDeArchivo(_ lista: [[String: Any]]) -> Int {
        var n = 0
        for o in lista { if let v = Vetado.deJSON(o), agregar(v) { n += 1 } }
        return n
    }

    func json() -> [[String: Any]] { propios.map { $0.json() } }
}

// MARK: el clasificador (UNO para todo camino que actúa)

struct Clasificacion: Equatable {
    var color: ColorAccion
    /// Por qué (en simple, para la bitácora y para el agente).
    var porque: [String]
    /// Si es rojo: ¿al menos se puede señalar? (nunca contraseñas, avisos de permisos ni la tarjeta del monito)
    var puedeSenalar: Bool = true
    /// El vetado que lo hizo rojo, si fue uno.
    var vetado: Vetado? = nil
}

// MARK: las reglas como DATOS (Fable v2 §5.6): una sola copia para la app de Mac y la de Windows

/// Las listas del portero (palabras, extensiones, esquemas, navegadores, apps que corren código, vetados de fábrica)
/// viven en escritorio/reglas/portero.json: la app las carga al abrir (Reglas.cargar) y la de Windows lee el mismo
/// archivo; los casos de examen que las dos pasan igual están en casos_portero.json.
///   · Lo rojo fijo está TAMBIÉN aquí, en código (Reglas.Nucleo): palabras de contraseñas, pagos y del sistema, avisos de
///     permisos, lo ejecutable, los navegadores y lo que corre código, y los vetados de fábrica. El archivo solo SUMA a
///     eso: si falta o dice otra cosa, lo rojo sigue.
///   · Lo que deja pasar (los botones inocuos, los tipos de documento, los roles que solo cambian lo que se ve) existe
///     solo si el archivo se cargó: sin él, NADA es amarillo (falla cerrado). Los esquemas, además, nunca pasan de
///     http, https, mailto y file.
struct Reglas {
    var palabras: [String: [String]]
    var ejecutables: Set<String>
    var documentos: Set<String>
    var esquemas: Set<String>
    var navegadores: Set<String>
    var correnCodigo: Set<String>
    var rolesInocuos: Set<String>
    var vetados: [Vetado]
    /// ¿Vino del archivo? (sin él: solo el núcleo, y nada es amarillo)
    var cargadas: Bool
    var origen: String
    /// Ronda 2 · direcciones acortadas (no se ve a dónde llevan: naranja). Núcleo ∪ archivo.
    var acortadores: Set<String> = Nucleo.acortadores
    /// Ronda 2 (H-1) · sitios conocidos de fábrica (solo del archivo): abrir SOLO el sitio puede recordarse. Los que el
    /// socio ya abrió con su OK se suman en lo recordado (Recordados.sitios).
    var sitiosConocidos: Set<String> = []
    /// Ronda 2 (H-1) · tus carpetas normales, dentro de tu carpeta de inicio (solo del archivo; nunca escondidas, Library ni
    /// rutas con «/»): abrir un documento de ahí puede recordarse.
    var carpetasNormales: [String] = []

    /// Lo rojo fijo, en código (no se quita).
    enum Nucleo {
        static let contrasena = ["contrasena", "contrasenas", "password", "passwords", "passcode", "clave de acceso", "clave secreta",
                             "clave de seguridad", "nip", "pin", "cvv", "cvc", "codigo de seguridad", "security code",
                             "numero de tarjeta", "card number", "clabe", "token", "codigo de verificacion", "verification code",
                             "otp", "2fa", "frase de recuperacion", "seed phrase", "recovery phrase", "llave privada",
                             "private key", "api key", "secret", "secreto"]
        static let pagar = ["pagar", "pago", "paga", "pay", "pay now", "comprar", "compra", "buy", "buy now", "checkout",
                        "finalizar compra", "realizar pedido", "place order", "confirmar pedido", "confirmar pago",
                        "transferir", "transferencia", "enviar dinero", "send money", "suscribirse", "subscribe",
                        "donar", "donate", "retirar", "withdraw", "agregar tarjeta", "add card", "pagar ahora"]
        static let sistema = ["instalar", "install", "permitir", "allow", "autorizar", "authorize", "conceder", "grant",
                          "desbloquear", "unlock", "abrir de todos modos", "open anyway", "confiar", "trust",
                          "iniciar sesion", "sign in", "log in", "login", "mostrar contrasena", "show password",
                          "cambiar contrasena", "change password", "olvide mi contrasena", "forgot password",
                          "vaciar papelera", "empty trash", "borrar definitivamente", "delete permanently",
                          "eliminar cuenta", "delete account"]
        static let avisoDePermiso = ["permiso", "permission", "would like to", "quiere acceder", "wants to", "desea controlar",
                                 "wants access", "administrador", "administrator", "contrasena", "password",
                                 "accesibilidad", "accessibility", "grabacion de pantalla", "screen recording"]
        static let ejecutables: Set<String> = ["app", "pkg", "mpkg", "dmg", "command", "sh", "zsh", "bash", "tool", "terminal",
                                           "scpt", "scptd", "applescript", "workflow", "prefpane", "mobileconfig", "kext",
                                           "dylib", "plugin", "osax", "action", "jar", "exe", "msi", "bundle", "xpc",
                                           "shortcut", "service", "qlgenerator", "saver", "appex"]
        static let navegadores: Set<String> = ["com.apple.Safari", "com.apple.SafariTechnologyPreview", "com.google.Chrome",
                                           "com.google.Chrome.canary", "company.thebrowser.Browser", "com.brave.Browser",
                                           "com.microsoft.edgemac", "org.mozilla.firefox", "com.operasoftware.Opera",
                                           "com.vivaldi.Vivaldi", "com.kagi.kagimacOS", "app.zen-browser.zen",
                                           "company.thebrowser.dia", "com.openai.atlas"]
        static let correnCodigo: Set<String> = ["org.python.PythonLauncher", "com.apple.ScriptEditor2", "com.apple.Automator",
                                            "com.apple.shortcuts", "com.apple.Terminal", "com.apple.dt.Xcode",
                                            "com.microsoft.VSCode", "com.googlecode.iterm2", "dev.warp.Warp-Stable",
                                            "com.mitchellh.ghostty", "com.apple.installer", "com.apple.archiveutility"]
        /// Lo más que un archivo puede dejar abrir como dirección.
        static let esquemasMaximos: Set<String> = ["http", "https", "mailto", "file"]
        /// Ronda 2 · acortadores: la ficha enseñaría «bit.ly/abc» y no a dónde va.
        static let acortadores: Set<String> = ["bit.ly", "t.co", "tinyurl.com", "goo.gl", "is.gd", "ow.ly", "buff.ly", "rebrand.ly",
                                           "cutt.ly", "shorturl.at", "lnkd.in", "rb.gy", "tiny.cc", "t.ly", "v.gd", "s.id"]
        /// Ronda 2 · lo más que el archivo puede nombrar como «carpeta normal» (un archivo no puede sumar otras).
        static let carpetasNormalesMaximas: Set<String> = ["Documents", "Desktop", "Downloads", "Documentos", "Escritorio", "Descargas"]
    }

    /// Las listas de PALABRAS que solo pueden crecer (lo rojo); las demás (lo naranja y lo inocuo) vienen del archivo.
    static let palabrasDelNucleo: [String: [String]] = ["contrasena": Nucleo.contrasena, "pagar": Nucleo.pagar,
                                                         "sistema": Nucleo.sistema, "avisoDePermiso": Nucleo.avisoDePermiso]

    static let nucleo = Reglas(palabras: palabrasDelNucleo, ejecutables: Nucleo.ejecutables, documentos: [],
                               esquemas: Nucleo.esquemasMaximos, navegadores: Nucleo.navegadores,
                               correnCodigo: Nucleo.correnCodigo, rolesInocuos: [], vetados: Vetados.nucleo,
                               cargadas: false, origen: "")

    /// Las de ahora (la app las pone al abrir; sin archivo, el núcleo).
    nonisolated(unsafe) static var actual = Reglas.nucleo

    static func usar(_ r: Reglas) { actual = r }

    /// El núcleo más lo que diga el archivo (lo rojo: unión; lo que deja pasar: del archivo; esquemas: nunca más que
    /// los máximos). Si no se puede leer: el núcleo (y nada amarillo).
    static func cargar(_ ruta: String) -> Reglas {
        guard let d = FileManager.default.contents(atPath: ruta),
              let o = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any] else { return Reglas.nucleo }
        return deJSON(o, origen: ruta)
    }

    static func deJSON(_ o: [String: Any], origen: String = "") -> Reglas {
        func lista(_ x: Any?) -> [String] { ((x as? [Any]) ?? []).compactMap { $0 as? String }.filter { !$0.isEmpty } }
        let pal = (o["palabras"] as? [String: Any]) ?? [:]
        var palabras: [String: [String]] = [:]
        for (k, v) in pal { palabras[k] = lista(v).map(Busqueda.normal).filter { !$0.isEmpty } }
        for (k, base) in palabrasDelNucleo { palabras[k] = base + (palabras[k] ?? []).filter { !base.contains($0) } }
        let ext = (o["extensiones"] as? [String: Any]) ?? [:]
        let apps = (o["apps"] as? [String: Any]) ?? [:]
        var vet = Vetados.nucleo
        for x in (o["vetados"] as? [[String: Any]]) ?? [] {
            guard var v = Vetado.deJSON(x), !vet.contains(where: { $0.id == v.id }) else { continue }
            v.fijo = true
            vet.append(v)
        }
        var r = Reglas(palabras: palabras,
                      ejecutables: Nucleo.ejecutables.union(lista(ext["ejecutables"]).map { $0.lowercased() }),
                      documentos: Set(lista(ext["documentos"]).map { $0.lowercased() }).subtracting(Nucleo.ejecutables),
                      esquemas: Set(lista(o["esquemas"]).map { $0.lowercased() }).intersection(Nucleo.esquemasMaximos),
                      navegadores: Nucleo.navegadores.union(lista(apps["navegadores"])),
                      correnCodigo: Nucleo.correnCodigo.union(lista(apps["corren_codigo"])),
                      rolesInocuos: Set(lista(apps["roles_inocuos"])), vetados: vet, cargadas: true, origen: origen)
        let sitios = (o["sitios"] as? [String: Any]) ?? [:]
        r.acortadores = Nucleo.acortadores.union(lista(sitios["acortadores"]).map { $0.lowercased() })
        // un sitio conocido es un nombre entero y común (sin «/», «@», «:», «%» ni «xn--»): lo demás se ignora
        r.sitiosConocidos = Set(lista(sitios["conocidos"]).map { $0.lowercased() }.filter { h in
            h.contains(".") && !h.contains("xn--") && h.allSatisfy { ($0 >= "a" && $0 <= "z") || ($0 >= "0" && $0 <= "9") || $0 == "." || $0 == "-" }
        })
        r.carpetasNormales = lista(o["carpetas_normales"]).filter { Nucleo.carpetasNormalesMaximas.contains($0) }
        return r
    }

    func json() -> [String: Any] {
        ["cargadas": cargadas, "origen": origen, "vetados": vetados.count, "palabras": palabras.mapValues { $0.count },
         "ejecutables": ejecutables.count, "documentos": documentos.count, "esquemas": esquemas.sorted(),
         "acortadores": acortadores.count, "sitios_conocidos": sitiosConocidos.count, "carpetas_normales": carpetasNormales]
    }
}

enum Clasificador {
    // Palabras, ya normalizadas (Busqueda.normal), que se buscan como palabras o frases enteras. Vienen de las reglas
    // (escritorio/reglas/portero.json + lo rojo fijo del núcleo).
    static func palabras(_ k: String) -> [String] { Reglas.actual.palabras[k] ?? [] }
    static var contrasena: [String] { palabras("contrasena") }
    static var pagar: [String] { palabras("pagar") }
    static var sistema: [String] { palabras("sistema") }
    static var mandar: [String] { palabras("mandar") }
    static var borrar: [String] { palabras("borrar") }
    /// Aceptar o confirmar algo (una invitación, un cambio, unos términos): naranja en cualquier lugar.
    static var confirmar: [String] { palabras("confirmar") }
    /// En un aviso o una hoja, también estos.
    static var aceptar: [String] { palabras("aceptar") }
    static var consentir: [String] { palabras("consentir") }
    static var guardarWeb: [String] { palabras("guardarWeb") }
    /// Fable v2 §1.3: en una app, amarillo SOLO estos botones (el nombre ENTERO, no «contiene»: «Cancelar suscripción»
    /// no es «Cancelar»), y las pestañas. Lo demás es naranja aunque suene inofensivo (Archivar, Imprimir, Continuar…):
    /// si alguien aprueba sin leer todo lo amarillo, no debe pasar nada grave. En la web, ni estos: el nombre lo
    /// escribió el sitio.
    static var inocuos: Set<String> { Set(palabras("inocuos")) }
    /// Roles que solo cambian lo que se ve (con un nombre que no dice mandar, borrar, pagar…).
    static var rolesInocuos: Set<String> { Reglas.actual.rolesInocuos }
    /// Fable v2 §1.3: abrir un archivo es amarillo SOLO con estos tipos (documentos, imágenes, texto) y si la app que lo
    /// abriría no corre código (un navegador, un lanzador) ni está vetada.
    static var documentos: Set<String> { Reglas.actual.documentos }
    /// Navegadores (abren y corren páginas) y apps que corren lo que abren: si una de ellas abriría el archivo, no es
    /// amarillo (naranja; lo que corre código, rojo).
    static var navegadores: Set<String> { Reglas.actual.navegadores }
    static var correnCodigo: Set<String> { Reglas.actual.correnCodigo }
    static var avisoDePermiso: [String] { palabras("avisoDePermiso") }

    /// ¿`texto` (ya normalizado) contiene alguna de `frases` como palabra o frase entera?
    static func tiene(_ texto: String, _ frases: [String]) -> Bool {
        let t = " " + texto + " "
        return frases.contains { t.contains(" " + $0 + " ") }
    }

    /// Extensiones que instalan o corren algo: abrirlas es rojo.
    static var ejecutables: Set<String> { Reglas.actual.ejecutables }
    /// Esquemas de dirección que se pueden abrir (lo demás es rojo).
    static var esquemas: Set<String> { Reglas.actual.esquemas }

    /// Carpetas donde nada se mueve, renombra ni borra.
    static func protegida(_ ruta: String, casa: String) -> Bool {
        let r = (ruta as NSString).standardizingPath
        let c = (casa as NSString).standardizingPath
        let enCasa = c.count > 1 && (r == c || r.hasPrefix(c + "/"))
        if !enCasa {
            for p in ["/System", "/Library", "/Applications", "/usr", "/bin", "/sbin", "/private", "/etc", "/var", "/opt", "/cores"]
            where r == p || r.hasPrefix(p + "/") { return true }
            return !r.hasPrefix("/Volumes/")                                              // fuera de tu carpeta: no
        }
        let dentro = r == c ? "" : String(r.dropFirst(c.count + 1))
        if dentro.isEmpty { return true }                                                 // tu carpeta entera
        if dentro.hasPrefix("Library/Mobile Documents/") || dentro.hasPrefix("Library/CloudStorage/") { return false }
        if dentro == "Library" || dentro.hasPrefix("Library/") || dentro == "Applications" || dentro.hasPrefix("Applications/") { return true }
        // lo escondido (.ssh, .claude, .zshrc…) y su contenido
        return dentro.split(separator: "/").contains { $0.hasPrefix(".") }
    }

    /// Carpetas que se sincronizan o salen de tu Mac (iCloud, Dropbox, Google Drive, OneDrive, discos y red).
    static func saleDeTuMac(_ ruta: String, casa: String) -> Bool {
        let r = (ruta as NSString).standardizingPath
        let c = (casa as NSString).standardizingPath
        if r.hasPrefix("/Volumes/") { return true }
        for p in ["Library/Mobile Documents", "Library/CloudStorage", "Dropbox", "Google Drive", "OneDrive", "Box", "iCloud Drive"]
        where r == c + "/" + p || r.hasPrefix(c + "/" + p + "/") || r.hasPrefix(c + "/" + p + " ") { return true }
        return false
    }

    /// ¿Parece un campo de contraseña o de datos de pago? (por lo que dice el SISTEMA del elemento)
    static func campoSecreto(_ d: Destino) -> Bool {
        if d.rol == "AXSecureTextField" || d.subrol == "AXSecureTextField" { return true }
        return tiene(Busqueda.normal(d.etiqueta ?? ""), contrasena)
    }

    /// ¿El destino es un aviso de permisos o de contraseña del sistema? (el monito ni lo señala)
    static func avisoDelSistema(_ d: Destino) -> Bool {
        let b = d.bundle.lowercased()
        if ["com.apple.securityagent", "com.apple.usernotificationcenter", "com.apple.coreservices.uiagent",
            "com.apple.localauthentication.uiagent"].contains(b) { return true }
        if d.enDialogo, tiene(Busqueda.normal(d.dialogo ?? ""), avisoDePermiso) { return true }
        return false
    }

    /// Fable v2 §1b: abrir y lo de archivos se deciden por SU destino (la app que se abre, la dirección, la ruta y la
    /// app que lo abriría), no por la ventana de enfrente, que no tocan. Escribir, llenar, apretar, elegir, mandar,
    /// compartir y subir tocan la ventana: ahí manda la de enfrente.
    static func objetivo(_ t: TipoAccion, _ d: Destino) -> Destino {
        var o = Destino()
        o.casa = d.casa
        o.ruta = d.ruta
        o.rutaDestino = d.rutaDestino
        o.destinoExiste = d.destinoExiste
        o.abrirURL = d.abrirURL
        o.abrirApp = d.abrirApp
        o.abrirCon = d.abrirCon
        o.abrirNombre = d.abrirNombre
        o.abrirAbierta = d.abrirAbierta
        o.esCarpeta = d.esCarpeta
        o.enFinder = d.enFinder
        // la página de enfrente NO viaja (A1: con el banco enfrente, abrir la Calculadora no es «tocar el banco»); «el
        // mismo sitio» se compara aparte, con la de enfrente
        if let a = d.abrirApp { o.bundle = a } else if let c = d.abrirCon { o.bundle = c }
        o.app = o.bundle
        return o
    }

    /// El color de un pedido sobre sus destinos (uno; varios en un lote). Lo decide el sistema; el modelo solo dice el
    /// tipo. Un lote toma el color del peor campo.
    static func color(_ p: PedidoAccion, _ destinos: [Destino], vetados: Vetados) -> Clasificacion {
        guard let t = p.tipoConocido else {
            return Clasificacion(color: .rojo, porque: ["no conozco la acción «\(p.tipo)»"], puedeSenalar: false)
        }
        guard !destinos.isEmpty else { return Clasificacion(color: .rojo, porque: ["no encontré a qué se refiere"], puedeSenalar: false) }
        if t == .llenar && destinos.count > PedidoAccion.maxCampos {
            return Clasificacion(color: .rojo, porque: ["un lote llena hasta \(PedidoAccion.maxCampos) campos"], puedeSenalar: false)
        }
        if t == .llenar, Set(destinos.map { "\($0.pid)·\($0.ventanaId)" }).count > 1 {
            return Clasificacion(color: .rojo, porque: ["un lote es en una sola ventana"], puedeSenalar: false)
        }
        var peor = Clasificacion(color: t.base, porque: [])
        for (i, d) in destinos.enumerated() {
            let valor = t == .llenar ? (i < p.campos.count ? p.campos[i].valor : "") : (p.valor ?? "")
            let c = uno(t, d, valor: valor, pedido: p, vetados: vetados)
            if c.color > peor.color || (c.color == peor.color && peor.porque.isEmpty) {
                peor = c
            } else if c.color == .rojo, !c.puedeSenalar {
                peor.puedeSenalar = false
            }
        }
        if peor.porque.isEmpty { peor.porque = [t.base == .naranja ? "sale de tu compu o no se deshace" : "cambia algo que se ve y se deshace"] }
        if peor.color == .amarillo && !Reglas.actual.cargadas {
            // sin el archivo de reglas no sé qué es inocuo: nada es amarillo (falla cerrado)
            return Clasificacion(color: .naranja, porque: ["no tengo las reglas completas (escritorio/reglas/portero.json)"])
        }
        return peor
    }

    private static func uno(_ t: TipoAccion, _ frente: Destino, valor: String, pedido p: PedidoAccion, vetados: Vetados) -> Clasificacion {
        // abrir y archivos: por su destino real (la ventana de enfrente no se toca); lo demás, por la ventana
        let porDestino = t == .abrir || t.deArchivo
        let d = porDestino ? objetivo(t, frente) : frente
        // lo que nunca: la tarjeta del monito, los avisos del sistema y lo vetado
        if !porDestino {
            if d.propia { return Clasificacion(color: .rojo, porque: ["es la tarjeta del propio monito"], puedeSenalar: false) }
            if avisoDelSistema(d) { return Clasificacion(color: .rojo, porque: ["es un aviso de permisos del sistema"], puedeSenalar: false) }
        }
        if let v = vetados.revisar(d) {
            return Clasificacion(color: .rojo, porque: ["\(v.nombre) está en tus vetados"], puedeSenalar: v.que == .noTocar, vetado: v)
        }
        if !porDestino, d.privada { return Clasificacion(color: .rojo, porque: ["es una ventana privada"], puedeSenalar: false) }
        let aqui = frente.sitio                             // de dónde se pide (para «el mismo sitio»)
        let nombre = Busqueda.normal(d.etiqueta ?? "")
        // en la web el nombre de un botón lo escribió el sitio: solo el sitio es confiable. Sin dirección legible en un
        // navegador: «sitio desconocido» (falla cerrado)
        let web = d.sitio != nil || d.sitioDesconocido
        let desconocido = !porDestino && d.sitioDesconocido
        let porDesconocido = "no pude leer la dirección de la página: podría ser cualquier sitio"
        switch t {
        case .escribir, .llenar:
            if campoSecreto(d) { return Clasificacion(color: .rojo, porque: ["es un campo de contraseña o de pago"], puedeSenalar: false) }
            if valor.contains("\n") || valor.contains("\r") {
                return Clasificacion(color: .naranja, porque: ["lleva un Enter: podría mandarlo"])
            }
            if desconocido { return Clasificacion(color: .naranja, porque: [porDesconocido]) }
            return Clasificacion(color: .amarillo, porque: ["escribe sin Enter; se puede regresar"])
        case .presionar, .elegir:
            if campoSecreto(d) { return Clasificacion(color: .rojo, porque: ["toca una contraseña"], puedeSenalar: false) }
            if tiene(nombre, pagar) { return Clasificacion(color: .rojo, porque: ["es pagar o comprar"]) }
            if tiene(nombre, sistema) { return Clasificacion(color: .rojo, porque: ["instala, da un permiso o es de contraseñas"]) }
            if tiene(nombre, consentir) { return Clasificacion(color: .naranja, porque: ["es aceptar términos"]) }
            if tiene(nombre, mandar) { return Clasificacion(color: .naranja, porque: ["manda algo fuera de tu compu"]) }
            if tiene(nombre, borrar) { return Clasificacion(color: .naranja, porque: ["borra algo"]) }
            if tiene(nombre, confirmar) { return Clasificacion(color: .naranja, porque: ["acepta o confirma algo"]) }
            if d.enDialogo, tiene(nombre, aceptar) { return Clasificacion(color: .naranja, porque: ["acepta un aviso"]) }
            if desconocido { return Clasificacion(color: .naranja, porque: [porDesconocido]) }
            if web, tiene(nombre, guardarWeb) { return Clasificacion(color: .naranja, porque: ["guarda en un sitio: sale de tu compu"]) }
            if t == .elegir {
                return Clasificacion(color: .amarillo, porque: ["elige una opción que se puede regresar"])
            }
            if web {
                // un enlace al MISMO sitio y sin datos: amarillo (lo dice su dirección, no su nombre); lo demás, naranja
                if d.rol == "AXLink", let e = d.enlace, let h = Destino.host(e), h == d.sitio, !Destino.conDatos(e) {
                    return Clasificacion(color: .amarillo, porque: ["un enlace a otra página del mismo sitio"])
                }
                return Clasificacion(color: .naranja, porque: ["en un sitio, un botón puede mandar algo (su nombre lo escribió el sitio)"])
            }
            if nombre.isEmpty { return Clasificacion(color: .naranja, porque: ["el botón no dice qué hace"]) }
            if inocuos.contains(nombre) || rolesInocuos.contains(d.rol ?? "") {
                return Clasificacion(color: .amarillo, porque: ["solo cambia lo que se ve"])
            }
            return Clasificacion(color: .naranja, porque: ["un botón que no sé si se deshace"])
        case .abrir:
            if let a = d.abrirApp, !a.isEmpty {
                if correnCodigo.contains(a) { return Clasificacion(color: .rojo, porque: ["esa app corre lo que abre"]) }
                // ronda 2: abrir una app es SOLO la app; con algo adentro (una dirección o un archivo, como «open -a App
                // algo») no es «abrir una app»: se pide cada cosa por su nombre
                if !(d.abrirURL ?? "").isEmpty || !(d.ruta ?? "").isEmpty {
                    return Clasificacion(color: .rojo, porque: ["abrir una app con algo adentro (una dirección o un archivo) no se hace: una cosa a la vez"], puedeSenalar: false)
                }
                return Clasificacion(color: .amarillo, porque: ["abre una app"])
            }
            if let u = d.abrirURL, !u.isEmpty {
                let c = URLComponents(string: u)
                let esq = (c?.scheme ?? "").lowercased()
                guard esquemas.contains(esq) else { return Clasificacion(color: .rojo, porque: ["esa dirección («\(esq):») no se abre"]) }
                if esq == "file" { return archivoParaAbrir(c?.path ?? "", con: d.abrirCon, casa: d.casa, vetados: vetados) }
                if let con = d.abrirCon, correnCodigo.contains(con) { return Clasificacion(color: .rojo, porque: ["la abriría una app que corre lo que abre"]) }
                // ronda 2: una dirección que engaña al leerla (usuario antes del sitio, nombre disfrazado) no se abre ni
                // con ficha: la ficha enseñaría algo que parece otro sitio
                if let por = Destino.direccionDisfrazada(u) { return Clasificacion(color: .rojo, porque: [por], puedeSenalar: false) }
                // carril 6 · un borrador de correo limpio (solo para, asunto y texto; lo arma la app): amarillo. No sale de tu
                // compu hasta que TÚ aprietes Enviar. Si lo abriría un navegador (tu correo web), naranja: ahí sí viaja a un sitio
                if esq == "mailto", Borrador.es(p, d) {
                    guard let con = d.abrirCon, !con.isEmpty else { return Clasificacion(color: .naranja, porque: ["no sé con qué app de correo se abriría"]) }
                    if navegadores.contains(con) { return Clasificacion(color: .naranja, porque: ["el borrador se abriría en tu navegador (tu correo web)"]) }
                    return Clasificacion(color: .amarillo, porque: ["prepara un borrador de correo; no lo envía"])
                }
                if Destino.conDatos(u) { return Clasificacion(color: .naranja, porque: ["la dirección lleva datos"]) }
                if esq == "mailto" { return Clasificacion(color: .amarillo, porque: ["abre un correo nuevo vacío, sin mandarlo"]) }
                if u.count > PedidoAccion.maxURL { return Clasificacion(color: .naranja, porque: ["la dirección es muy larga"]) }
                if let por = Destino.direccionRara(u) { return Clasificacion(color: .naranja, porque: [por]) }
                if let h = Destino.host(u), Reglas.actual.acortadores.contains(h) {
                    return Clasificacion(color: .naranja, porque: ["es una dirección acortada: no se ve a dónde lleva"])
                }
                // A1: una página limpia es amarilla a cualquier sitio; lo que leyó puede subirla (Clasificador.porLoLeido,
                // con grados: ronda 2, H-3)
                if let h = Destino.host(u), let a = aqui, h == a { return Clasificacion(color: .amarillo, porque: ["abre una página del mismo sitio"]) }
                return Clasificacion(color: .amarillo, porque: ["abre una página en tu navegador (sin datos)"])
            }
            if let r = d.ruta {
                if d.enFinder { return paraMostrar(r, casa: d.casa) }
                if d.esCarpeta { return carpetaParaAbrir(r, casa: d.casa) }
                return archivoParaAbrir(r, con: d.abrirCon, casa: d.casa, vetados: vetados)
            }
            return Clasificacion(color: .rojo, porque: ["no sé qué abrir"], puedeSenalar: false)
        case .mover, .renombrar, .borrar:
            guard let r = d.ruta else { return Clasificacion(color: .rojo, porque: ["no encontré el archivo"], puedeSenalar: false) }
            if protegida(r, casa: d.casa) { return Clasificacion(color: .rojo, porque: ["es una carpeta del sistema o escondida"]) }
            if t == .borrar { return Clasificacion(color: .naranja, porque: ["a la Papelera"]) }
            guard let a = d.rutaDestino else { return Clasificacion(color: .rojo, porque: ["falta a dónde"], puedeSenalar: false) }
            if protegida(a, casa: d.casa) && !saleDeTuMac(a, casa: d.casa) { return Clasificacion(color: .rojo, porque: ["el destino es una carpeta del sistema o escondida"]) }
            if saleDeTuMac(a, casa: d.casa) { return Clasificacion(color: .naranja, porque: ["el destino se sincroniza o sale de tu Mac"]) }
            if d.destinoExiste { return Clasificacion(color: .naranja, porque: ["ya hay algo con ese nombre: se reemplazaría"]) }
            if Rutas.ext(a) != Rutas.ext(r), Clasificador.ejecutables.contains(Rutas.ext(a)) {
                return Clasificacion(color: .rojo, porque: ["lo volvería un programa"])
            }
            return Clasificacion(color: .amarillo, porque: ["se puede regresar"])
        case .enviar, .compartir, .subir:
            if tiene(nombre, pagar) { return Clasificacion(color: .rojo, porque: ["es pagar"]) }
            return Clasificacion(color: .naranja, porque: ["sale de tu compu"])
        }
    }

    /// Abrir un archivo (Fable v2 §1.3): lo ejecutable, rojo; si lo abriría una app que corre código o está vetada,
    /// rojo; amarillo SOLO un tipo de la lista blanca abierto por una app conocida que no es un navegador; lo demás,
    /// naranja (sin saber con qué se abriría, también).
    private static func archivoParaAbrir(_ r: String, con: String?, casa: String, vetados: Vetados) -> Clasificacion {
        let e = Rutas.ext(r)
        if ejecutables.contains(e) { return Clasificacion(color: .rojo, porque: ["instala o corre un programa (.\(e))"]) }
        // A1: también por DÓNDE está: lo escondido (.ssh, .claude…), Library y lo de fuera de tu carpeta no se abre
        if protegida(r, casa: casa) { return Clasificacion(color: .rojo, porque: ["está en una carpeta escondida o del sistema (o fuera de tu carpeta)"]) }
        if let c = con {
            var h = Destino(); h.bundle = c; h.casa = casa
            if let v = vetados.revisar(h) {
                return Clasificacion(color: .rojo, porque: ["lo abriría \(v.nombre), que está en tus vetados"], puedeSenalar: v.que == .noTocar, vetado: v)
            }
            if correnCodigo.contains(c) { return Clasificacion(color: .rojo, porque: ["lo abriría una app que corre lo que abre"]) }
        }
        if e == "webloc" || e == "inetloc" { return Clasificacion(color: .naranja, porque: ["abre una dirección de internet"]) }
        // junto5 (decisión de Zenith) · una página (.html) de la carpeta de ENTREGABLES de uno de tus cerebros la hizo tu
        // agente para ti («abre la presentación que me hiciste»): ámbar, un toque, aunque la abra tu navegador. Nunca se
        // recuerda (TipoRecordado.de) y, si leyó contenido en este turno, sube a coral (porLoLeido). Lo vetado y lo que
        // corre lo que abre ya se negaron arriba; un HTML de cualquier otra carpeta sigue como estaba.
        if entregableHTML(r, casa: casa) {
            guard let c = con else { return Clasificacion(color: .naranja, porque: ["no sé con qué app se abriría"]) }
            return Clasificacion(color: .amarillo, porque: ["es un entregable de tu agente (una página): se abre en " + (navegadores.contains(c) ? "tu navegador" : "su app")])
        }
        guard documentos.contains(e) else { return Clasificacion(color: .naranja, porque: ["no es un tipo de documento que conozca (.\(e))"]) }
        guard let c = con else { return Clasificacion(color: .naranja, porque: ["no sé con qué app se abriría"]) }
        if navegadores.contains(c) { return Clasificacion(color: .naranja, porque: ["lo abriría un navegador (puede correr código)"]) }
        return Clasificacion(color: .amarillo, porque: ["abre un documento con su app"])
    }

    /// A1 · abrir una carpeta (en Finder): las tuyas sí (también tu carpeta de inicio); las escondidas, las de Library y las
    /// del sistema, no.
    private static func carpetaParaAbrir(_ r: String, casa: String) -> Clasificacion {
        if ejecutables.contains(Rutas.ext(r)) { return Clasificacion(color: .rojo, porque: ["es un programa o un paquete, no una carpeta"]) }
        let a = (r as NSString).standardizingPath, c = (casa as NSString).standardizingPath
        if a != c && protegida(r, casa: casa) { return Clasificacion(color: .rojo, porque: ["es una carpeta escondida o del sistema"]) }
        return Clasificacion(color: .amarillo, porque: ["abre la carpeta en Finder"])
    }

    /// A1 · mostrar en Finder: no lo abre ni lo corre (hasta un instalador se puede enseñar); lo escondido y lo del sistema
    /// (fuera de tu carpeta y de tus discos), no.
    private static func paraMostrar(_ r: String, casa: String) -> Clasificacion {
        let a = (r as NSString).standardizingPath, c = (casa as NSString).standardizingPath
        let dentro = a == c || a.hasPrefix(c + "/") || a.hasPrefix("/Volumes/") || a.hasPrefix("/Applications/")
        let escondido = a.split(separator: "/").contains { $0.hasPrefix(".") }
        let lib = a.hasPrefix(c + "/Library/") && !a.hasPrefix(c + "/Library/Mobile Documents/") && !a.hasPrefix(c + "/Library/CloudStorage/")
        if !dentro || escondido || lib { return Clasificacion(color: .rojo, porque: ["está en una carpeta escondida o del sistema"]) }
        return Clasificacion(color: .amarillo, porque: ["te enseña dónde está en Finder (no lo abre)"])
    }

    /// Ronda 2 (H-3) · lo que leyó cuenta para abrir una página, CON GRADOS (antes: cualquier lectura → naranja → «no»):
    ///   · no leyó contenido (o solo el nombre de la app y el título de la ventana, que no cuentan): como estaba;
    ///   · leyó contenido en un turno ANTERIOR: solo el sitio, como estaba; con camino, amarillo (la ficha enseña la
    ///     dirección entera y qué leyó); con datos ya era naranja (ficha coral);
    ///   · leyó contenido en ESTE turno (o hay un archivo ajeno en su conversación): solo el sitio, de un sitio conocido,
    ///     amarillo con ficha siempre (nunca sin preguntar); con camino, o a un sitio que el socio nunca ha abierto,
    ///     naranja (ficha coral: el camino, o el NOMBRE de un sitio nuevo, podría llevarse lo que leyó).
    /// Nunca baja el color. Lo que protege es que el socio vea la dirección ENTERA antes de que salga. `sitioConocido`: el
    /// sitio es de los de fábrica o el socio ya lo abrió con su OK (Recordados.conocido).
    /// junto5 (decisiones de Zenith): un borrador a una dirección NUEVA (a la que el socio no ha aprobado un borrador
    /// antes) cuando leyó contenido en un turno ANTERIOR también es naranja (coral); y una página de entregables,
    /// mientras haya algo leído (en este turno o antes, el mismo día), naranja (coral, se sostiene) en vez de un toque.
    static func porLoLeido(_ c: Clasificacion, _ p: PedidoAccion, _ ds: [Destino], leido: LoLeido, sitioConocido: Bool = true,
                           direccionNueva: Bool = false) -> Clasificacion {
        if c.color == .amarillo, let d = ds.first, Borrador.es(p, d), leido.grado == .antes, direccionNueva, let f = leido.fuente {
            return Clasificacion(color: .naranja, porque: ["antes leyó \(f.texto) y el correo va a una dirección a la que no le has preparado un borrador: podría llevar lo que leyó"])
        }
        // (revisión de resultados: mientras la marca de «leyó» siga VIVA, en este turno o en uno anterior del día: «espera
        // al siguiente mensaje» es justo el ataque. Una página corre código al abrirse y no enseña ninguna dirección.)
        if c.color == .amarillo, p.tipoConocido == .abrir, let d = ds.first, !d.esCarpeta, !d.enFinder, entregableHTML(d.ruta, casa: d.casa),
           leido.grado != .nada, let f = leido.fuente {
            let cuando = leido.grado == .esteTurno ? "en este turno leyó" : "antes leyó"
            return Clasificacion(color: .naranja, porque: ["es una página: puede conectarse a internet al abrirse, y \(cuando) \(f.texto)"])
        }
        // carril 6 · un borrador de correo en un turno donde leyó contenido: naranja (ficha coral, se sostiene): el
        // borrador podría llevar lo que leyó. Sigue sin enviarse; el socio lo ve ENTERO antes de decir que sí.
        if c.color == .amarillo, let d = ds.first, Borrador.es(p, d), leido.grado == .esteTurno, let f = leido.fuente {
            return Clasificacion(color: .naranja, porque: ["en este turno leyó \(f.texto): el borrador podría llevar lo que leyó"])
        }
        guard p.tipoConocido == .abrir, c.color == .amarillo, let d = ds.first, let u = d.abrirURL,
              let esq = URLComponents(string: u)?.scheme?.lowercased(), esq == "http" || esq == "https",
              leido.grado == .esteTurno, let f = leido.fuente else { return c }
        if !Destino.soloElSitio(u) {
            return Clasificacion(color: .naranja, porque: ["en este turno leyó \(f.texto) y la dirección lleva un camino: podría llevarse lo que leyó"])
        }
        if !sitioConocido {
            return Clasificacion(color: .naranja, porque: ["en este turno leyó \(f.texto) y es un sitio que no has abierto antes: su nombre podría llevarse lo que leyó"])
        }
        return c
    }

    /// junto5 · las páginas locales: corren código en el navegador, así que solo las de entregables se abren (y con ficha).
    static let paginasLocales: Set<String> = ["html", "htm"]
    static func entregableHTML(_ ruta: String?, casa: String) -> Bool {
        guard let r = ruta, paginasLocales.contains(Rutas.ext(r)) else { return false }
        return enEntregables(r, casa: casa)
    }

    /// T1-b · ¿la ruta es un archivo de la carpeta de entregables (`deliverables/`) de uno de los cerebros del socio? Solo
    /// documentos (no la carpeta ni «enséñalo en Finder»: eso lo decide quien llama), con la ruta ya resuelta (sin enlaces).
    static func enEntregables(_ ruta: String, casa: String) -> Bool {
        let r = ((ruta as NSString).resolvingSymlinksInPath as NSString).standardizingPath
        guard !protegida(r, casa: casa) else { return false }
        return Entregables.actuales.contains { r.hasPrefix($0 + "/") }
    }

    /// Ronda 2 (H-1) · ¿la ruta está en una de tus carpetas normales (Documentos, Escritorio, Descargas)? Solo ahí
    /// abrir un documento puede recordarse.
    static func carpetaNormal(_ ruta: String, casa: String) -> Bool {
        let r = (ruta as NSString).standardizingPath, c = (casa as NSString).standardizingPath
        guard c.count > 1, !protegida(r, casa: casa) else { return false }
        return Reglas.actual.carpetasNormales.contains { n in
            let base = c + "/" + n
            return r == base || r.hasPrefix(base + "/")
        }
    }

    /// ¿Se puede SEÑALAR este destino? (enséñame y rojo). Nunca contraseñas, avisos de permisos ni la tarjeta del monito.
    static func puedeSenalar(_ d: Destino, vetados: Vetados) -> String? {
        if d.propia { return "Eso es la tarjeta del propio monito: no la señalo." }
        if avisoDelSistema(d) { return "Es un aviso de permisos del sistema: ese lo decides tú, sin que te señale." }
        if campoSecreto(d) { return "Es un campo de contraseña: no lo señalo." }
        if let v = vetados.noMirar(d) { return "\(v.nombre) está en tus vetados: ni lo miro ni lo señalo." }
        return nil
    }
}

enum Rutas {
    static func ext(_ r: String) -> String { (r as NSString).pathExtension.lowercased() }
}

// MARK: ¿el elemento es el que dice el modelo?

enum Coincide {
    /// nil si coincide (o el modelo no dijo cómo se llama); si no, la frase. Compara lo que dijo el modelo con lo que dice
    /// el sistema: si el modelo dice «Asunto» y el sistema dice «Contraseña», no se hace.
    static func revisar(esperado: String?, sistema: String?, rol: String?) -> String? {
        guard let e = esperado.flatMap({ Texto.limpio($0, tope: 120) }) else { return nil }
        guard let s = sistema.flatMap({ Texto.limpio($0, tope: 300) }) else {
            return rol == "AXSecureTextField" ? "El elemento real es un campo de contraseña, no «\(e)»: no lo hago." : nil
        }
        let p = max(Busqueda.puntos(e, s), Busqueda.puntos(s, e))
        return p >= 50 ? nil : "El elemento real dice «\(s)», no «\(e)»: no lo hago."
    }
}

// MARK: los modos y la etapa

enum Modo: String, CaseIterable {
    case segundoPlano = "segundo_plano"
    case aLaVista = "a_la_vista"
    case ensename = "ensename"
    case conTuCursor = "con_tu_cursor"

    /// De fábrica: en segundo plano (callado: no vuela, no te quita el foco; un aviso con Deshacer). «A la vista» solo
    /// si lo pides o con su botón; con tu cursor, apagado (y por agente).
    static let deFabrica = Modo.segundoPlano

    var comoLoHago: String {
        switch self {
        case .segundoPlano: return "Lo hago en segundo plano: sigue usando tu compu; te aviso al terminar."
        case .aLaVista: return "Lo hago a la vista: el monito vuela a cada control. Tu mouse sigue tuyo."
        case .ensename: return "Te enseño dónde y tú lo haces."
        case .conTuCursor: return "Tomo tu mouse un momento, con la banda arriba. Esc Esc lo para."
        }
    }
}

enum Etapa: String {
    /// A0: nada se hace de verdad. El portero decide con la política completa (amarillo y naranja con su tarjeta) y lo
    /// anota; tras el OK, el monito te enseña dónde.
    case ensayo
    /// A1: lo amarillo que la mano ya hace de verdad (primera parte: abrir; LoQueHago), con su tarjeta; lo que todavía no
    /// hace y lo naranja: te enseña dónde. Sin confianza (congelada hasta A3).
    case amarillo
    /// A3: también lo naranja, con OK cada vez.
    case naranja
}

enum MouseAgente: String {
    case nunca, preguntando
    static let deFabrica = MouseAgente.nunca
}

enum Salida: String {
    /// `cero` (ronda 2, H-2): lo recordado por el socio («no me preguntes para abrir apps»): se hace ya, con su aviso verde.
    case libre, tarjeta, confianza, senalar, negado, cero
}

struct Veredicto: Equatable {
    var salida: Salida
    var color: ColorAccion
    var motivo: String
}

/// A1 · primera parte: lo que la mano ya hace DE VERDAD. Abrir: una app (por su nombre, resuelta por el sistema), un
/// archivo o una carpeta (su ruta real), una página http o https, o mostrar un archivo en Finder. Lo demás (escribir,
/// llenar, apretar, elegir, mover, renombrar, borrar, mandar…) todavía no: el monito te enseña dónde y lo haces tú.
enum LoQueHago {
    static let todaviaNo = "en esta versión solo abro apps, archivos, carpetas y páginas"

    /// nil si esta versión lo hace de verdad; si no, por qué (en simple).
    static func deVerdad(_ p: PedidoAccion, _ ds: [Destino]) -> String? {
        guard p.tipoConocido == .abrir, let d = ds.first else { return todaviaNo }
        if d.abrirApp != nil || d.ruta != nil { return nil }
        if let u = d.abrirURL, let e = URLComponents(string: u)?.scheme?.lowercased(), e == "http" || e == "https" { return nil }
        if Borrador.es(p, d) { return nil }                             // carril 6: un borrador de correo (no lo envía)
        return "por ahora solo abro páginas http y https"
    }
}

enum Politica {
    /// Qué pasa con una acción de `color` en `modo`. `confianza`: si aplica una confianza tuya (solo amarillo; solo en
    /// ensayo: en A1 está congelada hasta A3). `hace`: si no es nil, esta versión todavía no lo hace de verdad (por qué).
    /// Ronda 2: `fichaNaranja`: lo naranja que en A1 SÍ se hace con su ficha coral (abrir una página: la ficha enseña la
    /// dirección entera). `cero`: aplica algo que el socio recordó («no me preguntes…»; solo amarillo, solo A1).
    static func decidir(_ c: Clasificacion, modo: Modo, etapa: Etapa, mouse: MouseAgente, confianza: Bool, hace: String? = nil,
                        fichaNaranja: Bool = false, cero: Bool = false) -> Veredicto {
        switch c.color {
        case .verde:
            return Veredicto(salida: .libre, color: .verde, motivo: "libre")
        case .rojo:
            let por = c.porque.first ?? "es de lo que nunca hago"
            return c.puedeSenalar
                ? Veredicto(salida: .senalar, color: .rojo, motivo: "Esto lo haces tú (\(por)): solo te enseño dónde.")
                : Veredicto(salida: .negado, color: .rojo, motivo: "Esto no lo hago ni lo señalo (\(por)).")
        case .amarillo, .naranja:
            break
        }
        if modo == .ensename {
            return Veredicto(salida: .senalar, color: c.color, motivo: "Te enseño dónde y tú lo haces.")
        }
        if modo == .conTuCursor {
            if mouse == .nunca {
                return Veredicto(salida: .negado, color: c.color, motivo: "Este agente no puede tomar tu mouse (en el menú de Compañero: «Puede tomar mi mouse: nunca»).")
            }
            if c.color == .naranja { return Veredicto(salida: .negado, color: c.color, motivo: "Con tu cursor solo hago lo amarillo.") }
            return Veredicto(salida: .tarjeta, color: c.color, motivo: "¿Tomo tu mouse? Te pregunto.")
        }
        if etapa != .ensayo, let por = hace {
            return Veredicto(salida: .senalar, color: c.color, motivo: "Todavía no lo hago por ti (\(por)): te enseño dónde y lo haces tú.")
        }
        if c.color == .naranja {
            if etapa == .amarillo {
                let por = c.porque.first ?? "sale de tu compu o no se deshace"
                if fichaNaranja {
                    return Veredicto(salida: .tarjeta, color: .naranja, motivo: "Te pido tu OK cada vez (\(por)).")
                }
                return Veredicto(salida: .senalar, color: .naranja,
                                 motivo: "En esta versión todavía no lo hago por ti (\(por)): te enseño dónde y lo haces tú.")
            }
            return Veredicto(salida: .tarjeta, color: .naranja, motivo: "Lo naranja pide tu OK cada vez.")
        }
        if confianza && etapa == .ensayo { return Veredicto(salida: .confianza, color: .amarillo, motivo: "Confías en este agente para esto en esta app hoy.") }
        if cero && etapa == .amarillo && modo != .ensename {
            return Veredicto(salida: .cero, color: .amarillo, motivo: "Ya no te pregunto para esto (lo recordaste).")
        }
        return Veredicto(salida: .tarjeta, color: .amarillo, motivo: "Te pido tu OK.")
    }
}

// MARK: de dónde vino lo que leyó (la marca de «leyó tu pantalla»)

struct Fuente: Equatable {
    var app: String
    var bundle: String
    var ventana: String? = nil
    var sitio: String? = nil
    /// ventana (leer_ventana) · foto (ver_pantalla) · contexto (lo de enfrente) · seleccion (tu mensaje la llevó) ·
    /// archivo (contenido ajeno: un archivo que leyó en su conversación)
    var tipo: String = "ventana"
    /// Ronda 2 (H-3) · cuándo lo leyó y en qué turno (los pone el portero al anotarla): la marca se apaga al terminar el
    /// día, y «en este turno» pesa más que «en un turno anterior».
    var cuando: Date? = nil
    var turno: String? = nil

    /// Ronda 2 (H-3) · solo el nombre de la app y el título de la ventana NO cuentan como leer (esos datos ya viajan en
    /// cada mensaje del socio): tipo «titulo».
    static let soloTitulo = "titulo"
    var cuenta: Bool { tipo != Fuente.soloTitulo }

    /// Lo que leyó `contexto_escritorio`: si trajo una selección o el texto de lo que hay bajo el ratón, leyó CONTENIDO
    /// («contexto»); si solo la app y el título, no cuenta («titulo»).
    static func tipoDeContexto(seleccion: String?, bajoElRaton: String?) -> String {
        if let s = seleccion, !s.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty { return "contexto" }
        if let b = bajoElRaton, b.contains("«") { return "contexto" }
        return soloTitulo
    }

    /// Un archivo que leyó en su conversación (lo soltaste en el monito o viajó con «Resume esto»): contenido ajeno.
    static func archivo(_ nombre: String) -> Fuente {
        let n = Texto.limpio((nombre as NSString).lastPathComponent, tope: 80) ?? "archivo"
        return Fuente(app: n, bundle: "archivo:" + n.lowercased(), tipo: "archivo")
    }

    var esArchivo: Bool { tipo == "archivo" }

    var texto: String {
        if esArchivo { return "el archivo «" + app + "»" }
        var s = app
        if let h = sitio { s += " · " + h } else if let v = ventana.flatMap({ Texto.limpio($0, tope: 60) }) { s += " · «" + v + "»" }
        return s
    }

    func json() -> [String: Any] {
        var d: [String: Any] = ["app": app, "bundle": bundle, "tipo": tipo]
        if let v = ventana { d["ventana"] = v }
        if let h = sitio { d["sitio"] = h }
        if let c = cuando { d["cuando"] = c.timeIntervalSince1970 }
        if let t = turno { d["turno"] = t }
        return d
    }

    static func deJSON(_ o: [String: Any]) -> Fuente? {
        guard let a = o["app"] as? String else { return nil }
        return Fuente(app: a, bundle: (o["bundle"] as? String) ?? "", ventana: o["ventana"] as? String,
                      sitio: (o["sitio"] as? String) ?? Destino.host(o["url"] as? String), tipo: (o["tipo"] as? String) ?? "ventana",
                      cuando: (o["cuando"] as? NSNumber).map { Date(timeIntervalSince1970: $0.doubleValue) }, turno: o["turno"] as? String)
    }
}

struct Lecturas: Equatable {
    var fuentes: [Fuente] = []

    mutating func anotar(_ f: Fuente) {
        if let i = fuentes.firstIndex(where: { $0.bundle == f.bundle && $0.sitio == f.sitio && ($0.ventana == f.ventana || f.sitio != nil) }) {
            // la misma fuente otra vez: cuenta la lectura más nueva (su hora y su turno)
            if let c = f.cuando, c >= (fuentes[i].cuando ?? .distantPast) { fuentes[i].cuando = c; fuentes[i].turno = f.turno; fuentes[i].tipo = f.tipo }
        } else {
            fuentes.append(f)
        }
    }

    /// Ronda 2 (H-3) · las que siguen valiendo: las que cuentan (no «solo el título»), con su hora, leídas hoy (la marca se
    /// apaga sola al terminar el día). Una lectura del turno abierto no se apaga a media noche: sigue hasta que acabe.
    func vigentes(ahora: Date, calendario: Calendar = .current, turno: String? = nil) -> Lecturas {
        Lecturas(fuentes: fuentes.filter { f in
            guard f.cuenta, let c = f.cuando else { return false }
            if let t = turno, f.turno == t { return true }
            return Confianzas.finDelDia(c, calendario: calendario) >= ahora
        })
    }

    /// Ronda 2 (H-3) · el grado de lo leído para el turno `turno`: nada · antes (contenido, en un turno anterior) · este
    /// turno (contenido leído en este turno, o un archivo ajeno en su conversación: pesa igual). Con la fuente que lo dice.
    func grado(turno: String?) -> LoLeido {
        let cuentan = fuentes.filter { $0.cuenta }
        if let t = turno, let f = cuentan.last(where: { $0.turno == t && !$0.esArchivo }) { return LoLeido(grado: .esteTurno, fuente: f) }
        if let f = cuentan.last(where: { $0.esArchivo }) { return LoLeido(grado: .esteTurno, fuente: f) }
        if let f = cuentan.last { return LoLeido(grado: .antes, fuente: f) }
        return LoLeido(grado: .nada, fuente: nil)
    }

    /// La primera fuente que NO es esta app (y este sitio, si la confianza es de un sitio): si existe, una confianza
    /// para esta app se cae en esta conversación (lo que leyó de otra parte pudo traer órdenes, y sigue en su cabeza).
    func ajena(bundle: String, sitio: String?) -> Fuente? {
        fuentes.first { f in
            if f.bundle != bundle { return true }
            if let s = sitio { return f.sitio != s }
            return false
        }
    }

    /// «Leyó tu pantalla en esta conversación: Chrome · mail.google.com, Mail · «Re: …»» (hasta 3); con un archivo,
    /// «… contenido ajeno …». nil si no leyó nada.
    var resumen: String? {
        guard !fuentes.isEmpty else { return nil }
        let pantalla = fuentes.contains { !$0.esArchivo }, ajeno = fuentes.contains { $0.esArchivo }
        let que = pantalla && ajeno ? "Leyó tu pantalla y contenido ajeno" : pantalla ? "Leyó tu pantalla" : "Leyó contenido ajeno"
        let l = fuentes.prefix(3).map { $0.texto }
        return que + " en esta conversación: " + l.joined(separator: ", ") + (fuentes.count > 3 ? " y \(fuentes.count - 3) más" : "")
    }

    /// Lo que la app guarda (acciones/lecturas.json) para que la marca siga al volver a abrir el monito.
    func json() -> [[String: Any]] { fuentes.map { $0.json() } }

    static func deJSON(_ l: [[String: Any]]) -> Lecturas {
        var x = Lecturas()
        for o in l { if let f = Fuente.deJSON(o) { x.anotar(f) } }
        return x
    }
}

/// Ronda 2 (H-3) · qué tanto pesa lo que leyó.
enum GradoLeido: String {
    case nada
    case antes
    case esteTurno = "este_turno"
}

struct LoLeido: Equatable {
    var grado: GradoLeido = .nada
    var fuente: Fuente? = nil
}

// MARK: ronda 2 (H-2) · lo recordado: «no me preguntes para abrir apps / archivos / páginas»

/// Los TRES tipos que el socio puede recordar, y ninguno más. Lo naranja (coral) y lo rojo no tienen tipo: nunca se
/// recuerdan. Un tipo nunca cubre más que esto:
///   · abrir_app: abrir una app (sola: sin dirección ni archivo adentro);
///   · abrir_archivo: abrir (o enseñar en Finder) un documento o una carpeta de tus carpetas normales (Documentos,
///     Escritorio, Descargas); nunca un programa ni un script (esos ni son amarillos);
///   · abrir_pagina: abrir SOLO el sitio (`https://sitio/`), de un sitio conocido (de fábrica o que ya abriste con tu OK).
enum TipoRecordado: String, CaseIterable {
    case abrirApp = "abrir_app"
    case abrirArchivo = "abrir_archivo"
    case abrirPagina = "abrir_pagina"

    /// «Abrir apps» (el menú: «Lo que hace sin preguntar»)
    var texto: String {
        switch self {
        case .abrirApp: return "Abrir apps"
        case .abrirArchivo: return "Abrir archivos y carpetas de Documentos, Escritorio y Descargas (y los entregables de tus agentes)"
        case .abrirPagina: return "Abrir sitios conocidos (solo el sitio, sin datos)"
        }
    }

    private var cosas: String {
        switch self {
        case .abrirApp: return "apps"
        case .abrirArchivo: return "archivos de tus carpetas"
        case .abrirPagina: return "sitios conocidos"
        }
    }

    /// La casilla de la ficha.
    var casilla: String { "No me preguntes para abrir " + cosas }
    /// Al tercer OK.
    var pregunta: String { "Ya van \(Recordados.ofrecerA). ¿Dejo de preguntarte para abrir \(cosas)?" }

    /// El tipo de un pedido, por lo que dice el SISTEMA de su destino (nunca el modelo), o nil si no es de ninguno. Solo
    /// lo amarillo de abrir, de un solo destino.
    static func de(_ p: PedidoAccion, _ ds: [Destino], color: ColorAccion) -> TipoRecordado? {
        guard p.tipoConocido == .abrir, color == .amarillo, ds.count == 1, let d = ds.first else { return nil }
        if let a = d.abrirApp, !a.isEmpty {
            return (d.abrirURL ?? "").isEmpty && (d.ruta ?? "").isEmpty ? .abrirApp : nil
        }
        if let u = d.abrirURL, !u.isEmpty { return Destino.soloElSitio(u, soloHttps: true) ? .abrirPagina : nil }
        if let r = d.ruta, !r.isEmpty {
            // junto5: una página (.html) nunca se recuerda, esté donde esté (corre código en el navegador): siempre su ficha
            if !d.esCarpeta, Clasificador.paginasLocales.contains(Rutas.ext(r)) { return nil }
            if Clasificador.carpetaNormal(r, casa: d.casa) { return .abrirArchivo }
            // T1-b: un DOCUMENTO de la carpeta de entregables de uno de tus cerebros (no la carpeta, no Finder)
            return !d.esCarpeta && !d.enFinder && Clasificador.enEntregables(r, casa: d.casa) ? .abrirArchivo : nil
        }
        return nil
    }
}

/// T1-b · las carpetas de entregables (`<cerebro>/deliverables`) de los cerebros del socio: cuentan como «carpetas
/// normales» para ABRIR DOCUMENTOS sin preguntar («abre la presentación que me hiciste»). Las dice quien hospeda al
/// portero (el puente, que conoce los cerebros); aquí se LIMPIAN: ruta entera y resuelta (sin enlaces), que termine en
/// `deliverables`, dentro de la carpeta del socio y nunca escondida ni de Library. Lo demás se ignora.
enum Entregables {
    static let nombre = "deliverables"
    static let tope = 50
    nonisolated(unsafe) static var actuales: [String] = []

    static func limpias(_ rutas: [String], casa: String) -> [String] {
        var out: [String] = []
        for x in rutas.prefix(200) {
            guard x.hasPrefix("/"), !PedidoAccion.invisible(x) else { continue }
            let r = ((x as NSString).resolvingSymlinksInPath as NSString).standardizingPath
            guard (r as NSString).lastPathComponent == nombre, !Clasificador.protegida(r, casa: casa), !out.contains(r) else { continue }
            out.append(r)
            if out.count >= tope { break }
        }
        return out
    }

    static func usar(_ rutas: [String], casa: String = NSHomeDirectory()) { actuales = limpias(rutas, casa: casa) }
}

struct Recordado: Equatable {
    var tipo: TipoRecordado
    var desde: Date
    var texto: String { tipo.texto }
}

/// Lo que el socio recordó (por tipo, para todos sus agentes), los sitios que ya abrió con su OK y cuántos OK lleva de
/// cada tipo. Solo cambia con un clic de una persona (la casilla de la ficha o el menú del monito).
struct Recordados: Equatable {
    private(set) var lista: [Recordado] = []
    /// Sitios (host entero) que el socio ya abrió con su OK.
    private(set) var sitios: [String] = []
    /// junto5 · direcciones de correo a las que el socio ya aprobó un borrador (enteras, en minúsculas).
    private(set) var correos: [String] = []
    private(set) var oks: [String: Int] = [:]

    /// Al tercer OK del mismo tipo, el monito lo ofrece.
    static let ofrecerA = 3
    /// Lo más que se hace sin preguntar en un turno; después, ficha.
    static let topePorTurno = 5
    static let topeSitios = 300

    func tiene(_ t: TipoRecordado) -> Bool { lista.contains { $0.tipo == t } }

    mutating func dar(_ t: TipoRecordado, ahora: Date) {
        guard !tiene(t) else { return }
        lista.append(Recordado(tipo: t, desde: ahora))
    }

    @discardableResult
    mutating func quitar(_ t: TipoRecordado) -> Bool {
        let antes = lista.count
        lista.removeAll { $0.tipo == t }
        return lista.count != antes
    }

    mutating func quitarTodos() { lista = [] }

    /// Un OK más de ese tipo. → cuántos lleva.
    @discardableResult
    mutating func contar(_ t: TipoRecordado) -> Int {
        oks[t.rawValue] = min((oks[t.rawValue] ?? 0) + 1, 1_000_000)
        return oks[t.rawValue] ?? 0
    }

    func cuenta(_ t: TipoRecordado) -> Int { oks[t.rawValue] ?? 0 }

    /// El socio abrió esta página con su OK: su sitio ya es conocido (el nombre entero; nunca uno disfrazado).
    mutating func conocer(_ u: String) {
        guard Destino.direccionDisfrazada(u) == nil, let h = Destino.host(u), Recordados.nombreComun(h), !sitios.contains(h) else { return }
        sitios.append(h)
        if sitios.count > Recordados.topeSitios { sitios.removeFirst(sitios.count - Recordados.topeSitios) }
    }

    /// Aprobaste un borrador para estas direcciones. → true si alguna era nueva.
    @discardableResult
    mutating func conocerCorreos(_ ds: [String]) -> Bool {
        var cambio = false
        for d in ds.map({ $0.lowercased() }) where Borrador.direccion(d) && !correos.contains(d) { correos.append(d); cambio = true }
        if correos.count > Recordados.topeSitios { correos.removeFirst(correos.count - Recordados.topeSitios) }
        return cambio
    }

    /// ¿Este borrador (su mailto) va a alguna dirección a la que el socio no le ha aprobado un borrador? Sin destinatario
    /// (lo pone él) no es nueva; lo que no es un borrador limpio, tampoco aplica.
    func direccionNueva(_ mailto: String?) -> Bool {
        guard let b = mailto.flatMap(Borrador.de) else { return false }
        return b.para.contains { !correos.contains($0.lowercased()) }
    }

    static func nombreComun(_ h: String) -> Bool {
        h.contains(".") && !h.contains("xn--") && h.count <= 120
            && h.allSatisfy { ($0 >= "a" && $0 <= "z") || ($0 >= "0" && $0 <= "9") || $0 == "." || $0 == "-" }
    }

    /// ¿El sitio de `u` es conocido? (el nombre ENTERO, igual: «youtube.com.otro.io» no es «youtube.com»)
    func conocido(_ u: String) -> Bool {
        guard let h = Destino.host(u) else { return false }
        return sitios.contains(h) || Reglas.actual.sitiosConocidos.contains(h)
    }

    func json() -> [String: Any] {
        ["version": 1,
         "nota": "Lo que Workspace Compañero hace sin preguntar (lo marcaste en una ficha). Se quita en su menú: «Lo que hace sin preguntar».",
         "recordados": lista.map { ["tipo": $0.tipo.rawValue, "desde": $0.desde.timeIntervalSince1970] as [String: Any] },
         "sitios": sitios, "correos": correos, "oks": oks]
    }

    /// De un archivo: solo los tres tipos (otro tipo se ignora: nada más amplio entra por aquí), sitios de nombre común.
    static func deJSON(_ o: [String: Any]) -> Recordados {
        var r = Recordados()
        for x in (o["recordados"] as? [[String: Any]]) ?? [] {
            guard let t = (x["tipo"] as? String).flatMap(TipoRecordado.init(rawValue:)), !r.tiene(t) else { continue }
            r.lista.append(Recordado(tipo: t, desde: Date(timeIntervalSince1970: (x["desde"] as? NSNumber)?.doubleValue ?? 0)))
        }
        for h in ((o["sitios"] as? [Any]) ?? []).compactMap({ ($0 as? String)?.lowercased() }) where nombreComun(h) && !r.sitios.contains(h) {
            r.sitios.append(h)
        }
        if r.sitios.count > topeSitios { r.sitios = Array(r.sitios.suffix(topeSitios)) }
        r.conocerCorreos(((o["correos"] as? [Any]) ?? []).compactMap { $0 as? String })
        for (k, v) in (o["oks"] as? [String: Any]) ?? [:] {
            if TipoRecordado(rawValue: k) != nil, let n = (v as? NSNumber)?.intValue, n > 0 { r.oks[k] = min(n, 1_000_000) }
        }
        return r
    }
}

/// Dónde vive lo recordado: `<estado>/escritorio/recordados.json` (600, con lo demás de actuar, en lo prohibido de leer
/// para los agentes). Solo la app lo escribe. Es un permiso de Workspace sobre SU herramienta: no toca los permisos de
/// ningún motor ni su configuración.
enum AlmacenRecordados {
    static let archivo = "recordados.json"

    static func leer(_ ruta: String) -> Recordados {
        guard let d = FileManager.default.contents(atPath: ruta), d.count < 200_000,
              let o = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any] else { return Recordados() }
        return Recordados.deJSON(o)
    }

    @discardableResult
    static func escribir(_ r: Recordados, _ ruta: String) -> Bool {
        guard let d = try? JSONSerialization.data(withJSONObject: r.json(), options: [.sortedKeys, .prettyPrinted]) else { return false }
        let fm = FileManager.default
        try? fm.createDirectory(atPath: (ruta as NSString).deletingLastPathComponent, withIntermediateDirectories: true,
                                attributes: [.posixPermissions: 0o700])
        let tmp = ruta + ".\(ProcessInfo.processInfo.processIdentifier).tmp"
        guard fm.createFile(atPath: tmp, contents: d, attributes: [.posixPermissions: 0o600]) else { return false }
        if rename(tmp, ruta) != 0 { unlink(tmp); return false }
        return true
    }
}

// MARK: ronda 2 · el veredicto para la ficha (la arma la app con esto; nunca con texto del agente)

enum SalidaFicha: String {
    case cero, ficha, no
}

enum TonoFicha: String {
    case verde, ambar, coral, no
}

/// Lo que la ficha necesita (contrato con el carril de fichas: CONTRATO_PORTERO_FICHAS.md).
struct Ficha: Equatable {
    var salida: SalidaFicha
    var tono: TonoFicha
    /// La tarjeta (para responder) si es ficha; la autorización si es cero.
    var id: String = ""
    var agente: String = ""
    /// Una frase con verbo: «Atlas quiere abrir youtube.com».
    var titulo: String = ""
    var verbo: String = ""
    var objeto: String = ""
    /// Lo que va a pasar, ENTERO: la dirección completa, la ruta completa o el nombre de la app.
    var detalle: String = ""
    /// url · ruta · carpeta · finder · app · elemento
    var detalleTipo: String = "elemento"
    /// Con una dirección: el sitio, para resaltarlo.
    var sitio: String? = nil
    /// La fuente leída que cuenta («Safari · mail.google.com») y cuándo: este_turno · antes.
    var leyo: String? = nil
    var leyoCuando: String? = nil
    var puedeOlvidar = false
    /// abrir_app · abrir_archivo · abrir_pagina, o nil (sin casilla: lo coral, lo rojo, lo que no es de un tipo, y todo si
    /// leyó en este turno).
    var recordable: String? = nil
    var recordarTexto: String? = nil
    var ofrecerRecordar = false
    var motivo: String = ""
    var puedeSenalar = false
    var como: String = ""
    var deshacer: String = ""
    var armaMs: Int = 0
    var sostenerMs: Int = 0
    var vence: TimeInterval = 0
    var pedido: Date = Date(timeIntervalSince1970: 0)

    func json() -> [String: Any] {
        var d: [String: Any] = ["salida": salida.rawValue, "tono": tono.rawValue, "id": id, "agente": agente, "titulo": titulo,
                                "verbo": verbo, "objeto": objeto, "detalle": detalle, "detalle_tipo": detalleTipo,
                                "puede_olvidar": puedeOlvidar, "ofrecer_recordar": ofrecerRecordar, "motivo": motivo,
                                "puede_senalar": puedeSenalar, "como": como, "deshacer": deshacer, "arma_ms": armaMs,
                                "sostener_ms": sostenerMs, "vence_s": vence, "pedido_s": pedido.timeIntervalSince1970]
        if let x = sitio { d["sitio"] = x }
        if let x = leyo { d["leyo"] = x }
        if let x = leyoCuando { d["leyo_cuando"] = x }
        if let x = recordable { d["recordable"] = x }
        if let x = recordarTexto { d["recordar_texto"] = x }
        return d
    }
}

enum ArmarFicha {
    /// El verbo y lo que toca, con lo que dice el sistema.
    static func verboYObjeto(_ t: TipoAccion?, _ ds: [Destino]) -> (verbo: String, objeto: String, detalle: String, tipo: String, sitio: String?) {
        let d = ds.first ?? Destino()
        let app = d.app.isEmpty ? "esta app" : d.app
        guard let t = t else { return ("hacer", "algo que no conozco", "", "elemento", nil) }
        switch t {
        case .abrir:
            if let a = d.abrirApp, !a.isEmpty { let n = d.abrirNombre ?? a; return ("abrir", n, n, "app", nil) }
            if let b = Borrador.de(d.abrirURL ?? "") {                            // carril 6: para, asunto y texto, ENTEROS
                return ("preparar un correo para", b.paraQuien, "Para: \(b.paraQuien)\nAsunto: \(b.asunto)\n\n\(b.texto)", "correo", nil)
            }
            if let u = d.abrirURL, !u.isEmpty {
                let h = Destino.host(u)
                return ("abrir", h ?? "una dirección", u, "url", h)               // la dirección, ENTERA
            }
            let r = d.ruta ?? ""
            if d.enFinder { return ("enseñarte en Finder", ArmarTarjeta.archivo(r), r, "finder", nil) }
            if d.esCarpeta { return ("abrir la carpeta", ArmarTarjeta.archivo(r), r, "carpeta", nil) }
            return ("abrir", r.isEmpty ? "algo" : ArmarTarjeta.archivo(r), r, "ruta", nil)
        case .escribir: return ("escribir en", app, ArmarTarjeta.elemento(d), "elemento", d.sitio)
        case .llenar: return ("llenar \(ds.count == 1 ? "1 campo" : "\(ds.count) campos") en", app, ArmarTarjeta.donde(d), "elemento", d.sitio)
        case .presionar: return ("apretar", ArmarTarjeta.elemento(d), ArmarTarjeta.donde(d), "elemento", d.sitio)
        case .elegir: return ("elegir", ArmarTarjeta.elemento(d), ArmarTarjeta.donde(d), "elemento", d.sitio)
        case .mover: return ("mover", ArmarTarjeta.archivo(d.ruta), (d.ruta ?? "") + " → " + (d.rutaDestino ?? ""), "ruta", nil)
        case .renombrar: return ("renombrar", ArmarTarjeta.archivo(d.ruta), (d.ruta ?? "") + " → " + (d.rutaDestino ?? ""), "ruta", nil)
        case .borrar: return ("mandar a la Papelera", ArmarTarjeta.archivo(d.ruta), d.ruta ?? "", "ruta", nil)
        case .enviar: return ("mandar algo con", ArmarTarjeta.elemento(d), ArmarTarjeta.donde(d), "elemento", d.sitio)
        case .compartir: return ("compartir con", ArmarTarjeta.elemento(d), ArmarTarjeta.donde(d), "elemento", d.sitio)
        case .subir: return ("subir algo con", ArmarTarjeta.elemento(d), ArmarTarjeta.donde(d), "elemento", d.sitio)
        }
    }

    /// La ficha de un veredicto. `nombre`: cómo ve el socio al agente. Todo sale del portero y del sistema.
    static func de(_ v: Veredicto, pedido p: PedidoAccion, destinos ds: [Destino], agente: String, nombre: String, id: String,
                   tarjeta t: Tarjeta?, leido: LoLeido, recordable: TipoRecordado?, oks: Int, puedeSenalar: Bool, ahora: Date,
                   turno: String? = nil) -> Ficha {
        let (verbo, objeto, detalle, tipo, sitio) = verboYObjeto(p.tipoConocido, ds)
        var f: Ficha
        switch v.salida {
        case .cero, .confianza, .libre:
            f = Ficha(salida: .cero, tono: .verde)
            f.titulo = "\(nombre) \(tercera(verbo)) \(objeto)"
        case .tarjeta:
            f = Ficha(salida: .ficha, tono: v.color == .naranja ? .coral : .ambar)
            f.titulo = "\(nombre) quiere \(verbo) \(objeto)"
        case .senalar, .negado:
            f = Ficha(salida: .no, tono: .no)
            f.titulo = "\(nombre) no puede \(verbo) \(objeto)"
            f.puedeSenalar = v.salida == .senalar && puedeSenalar
        }
        f.id = id
        f.agente = agente
        f.verbo = verbo
        f.objeto = objeto
        f.detalle = detalle
        f.detalleTipo = tipo
        f.sitio = sitio
        f.motivo = v.motivo
        f.pedido = ahora
        if leido.grado != .nada, let x = leido.fuente {
            f.leyo = x.texto
            f.leyoCuando = leido.grado.rawValue
            // «Olvidar lo leído» se ofrece cuando sirve YA: lo que leyó en el turno abierto se olvida al terminar el turno
            f.puedeOlvidar = turno == nil || x.turno != turno
        }
        if let t = t {
            f.como = t.comoLoHago
            f.deshacer = t.deshacer
            f.armaMs = t.armaMs
            f.sostenerMs = t.sostenerMs
            f.vence = t.vence
        }
        // la casilla: solo en una ficha ámbar de uno de los tres tipos, y nunca si leyó en este turno
        if f.salida == .ficha, f.tono == .ambar, leido.grado != .esteTurno, let r = recordable {
            f.recordable = r.rawValue
            f.recordarTexto = r.casilla
            f.ofrecerRecordar = oks + 1 >= Recordados.ofrecerA
        }
        return f
    }

    /// «abrir» → «abre» (el aviso de lo que se hace sin preguntar).
    static func tercera(_ verbo: String) -> String {
        let partes = verbo.split(separator: " ", maxSplits: 1).map(String.init)
        guard let v = partes.first else { return verbo }
        let c: [String: String] = ["abrir": "abre", "enseñarte": "te enseña", "escribir": "escribe", "llenar": "llena", "apretar": "aprieta",
                                   "elegir": "elige", "mover": "mueve", "renombrar": "renombra", "mandar": "manda", "compartir": "comparte",
                                   "subir": "sube", "hacer": "hace"]
        return ([c[v] ?? v] + partes.dropFirst()).joined(separator: " ")
    }
}

// MARK: «confío en este agente para X en esta app»

struct Confianza: Equatable {
    var id: String
    var agente: String
    var bundle: String
    var app: String
    /// En un navegador, el sitio (la confianza es de ese sitio, no de todo internet).
    var sitio: String?
    var desde: Date
    var vence: Date

    var texto: String { "\(agente) · lo amarillo en \(app)" + (sitio.map { " (\($0))" } ?? "") }

    func json() -> [String: Any] {
        var d: [String: Any] = ["id": id, "agente": agente, "bundle": bundle, "app": app,
                                "desde": desde.timeIntervalSince1970, "vence": vence.timeIntervalSince1970]
        if let s = sitio { d["sitio"] = s }
        return d
    }
}

struct Confianzas: Equatable {
    var lista: [Confianza] = []
    /// Lo más que se hace por confianza en un turno; después, tarjeta.
    static let topePorTurno = 10

    /// El fin del día (23:59:59 de hoy, en la hora de la Mac).
    static func finDelDia(_ d: Date, calendario: Calendar = .current) -> Date {
        let inicio = calendario.startOfDay(for: d)
        return calendario.date(byAdding: DateComponents(day: 1, second: -1), to: inicio) ?? d.addingTimeInterval(86_400)
    }

    @discardableResult
    mutating func dar(id: String, agente: String, destino d: Destino, ahora: Date, calendario: Calendar = .current) -> Confianza {
        let c = Confianza(id: id, agente: agente, bundle: d.bundle, app: d.app.isEmpty ? d.bundle : d.app,
                          sitio: d.sitio, desde: ahora, vence: Confianzas.finDelDia(ahora, calendario: calendario))
        lista.removeAll { $0.agente == c.agente && $0.bundle == c.bundle && $0.sitio == c.sitio }
        lista.append(c)
        return c
    }

    @discardableResult
    mutating func quitar(_ id: String) -> Bool {
        let antes = lista.count
        lista.removeAll { $0.id == id }
        return lista.count != antes
    }

    mutating func limpiar(_ ahora: Date) { lista.removeAll { $0.vence <= ahora } }

    /// La confianza que aplica (o nil) y, si hay una pero no aplica, por qué.
    func aplica(agente: String, destino d: Destino, color: ColorAccion, lecturas: Lecturas, usadas: Int, ahora: Date) -> (Confianza?, String?) {
        guard let c = lista.first(where: { $0.agente == agente && $0.bundle == d.bundle && ($0.sitio == nil || $0.sitio == d.sitio) }) else {
            return (nil, nil)
        }
        if color != .amarillo { return (nil, "la confianza es solo para lo amarillo") }
        if c.vence <= ahora { return (nil, "tu confianza ya venció") }
        if usadas >= Confianzas.topePorTurno { return (nil, "ya hizo \(usadas) cosas por confianza en este turno") }
        if let f = lecturas.ajena(bundle: c.bundle, sitio: c.sitio) { return (nil, "en esta conversación leyó otra fuente (\(f.texto))") }
        return (c, nil)
    }
}

// MARK: un OK = una acción y un destino

struct Huella: Equatable {
    var pid: Int32
    var bundle: String
    var ventanaId: UInt32
    var ventana: String
    var pagina: String
    var rol: String
    var etiqueta: String
    var marco: [Int]
    var ruta: String

    static func de(_ d: Destino) -> Huella {
        var pagina = ""
        if let u = d.url, let c = URLComponents(string: u) { pagina = (c.host ?? "") + c.path }
        let m = d.marco.map { [Int($0.minX.rounded()), Int($0.minY.rounded()), Int($0.width.rounded()), Int($0.height.rounded())] } ?? []
        return Huella(pid: d.pid, bundle: d.bundle, ventanaId: d.ventanaId, ventana: d.ventana ?? "", pagina: pagina,
                      rol: d.rol ?? "", etiqueta: d.etiqueta ?? "", marco: m, ruta: (d.ruta ?? "") + "→" + (d.rutaDestino ?? ""))
    }

    /// nil si es el mismo destino; si no, qué cambió (en simple).
    func cambio(_ o: Huella, tolerancia: Int = 2) -> String? {
        if pid != o.pid || bundle != o.bundle { return "cambió la app" }
        if ventanaId != o.ventanaId || ventana != o.ventana { return "cambió la ventana" }
        if pagina != o.pagina { return "cambió la página" }
        if rol != o.rol || etiqueta != o.etiqueta { return "cambió el elemento" }
        if ruta != o.ruta { return "cambió el archivo" }
        if marco.count == 4, o.marco.count == 4, zip(marco, o.marco).contains(where: { abs($0 - $1) > tolerancia }) { return "el elemento se movió" }
        if marco.count != o.marco.count { return "cambió el elemento" }
        return nil
    }

    static func lote(_ ds: [Destino]) -> [Huella] { ds.map(Huella.de) }

    /// A1 · abrir no toca la ventana de enfrente: su OK es por LO QUE SE ABRE (la app, la app que lo abriría, la ruta
    /// real, la página). Si cambias de ventana mientras lo piensas, sigue valiendo; si cambia lo que se abriría, no.
    static func deAbrir(_ d: Destino) -> Huella {
        Huella(pid: 0, bundle: d.abrirApp ?? d.abrirCon ?? "", ventanaId: 0, ventana: "", pagina: d.abrirURL ?? "",
               rol: d.enFinder ? "finder" : (d.esCarpeta ? "carpeta" : ""), etiqueta: "", marco: [], ruta: (d.ruta ?? "") + "→")
    }

    /// Las huellas de un pedido: abrir, por lo que se abre; lo demás, por la ventana (como siempre).
    static func lote(_ ds: [Destino], _ t: TipoAccion?) -> [Huella] { t == .abrir ? ds.map(Huella.deAbrir) : lote(ds) }

    static func cambioLote(_ a: [Huella], _ b: [Huella]) -> String? {
        guard a.count == b.count else { return "cambió lo que se iba a llenar" }
        for (x, y) in zip(a, b) { if let c = x.cambio(y) { return c } }
        return nil
    }
}

struct Autorizacion: Equatable {
    var id: String
    var tarjeta: String
    var tipo: String
    var huellas: [Huella]
    var desde: Date
    var porConfianza: String? = nil
    /// Ronda 2: se dio sin preguntar, por algo recordado (su tipo).
    var porRecordado: String? = nil
    var usada = false

    /// Un OK vale poco tiempo (si tardas, te vuelvo a preguntar).
    static let vigencia: TimeInterval = 30
}

// MARK: la tarjeta de OK (la arma la app con lo del sistema)

struct ValorTarjeta: Equatable {
    var campo: String
    var valor: String
}

struct Tarjeta: Equatable {
    var id: String
    var color: ColorAccion
    var agente: String
    /// «¿Escribo en Mail?»
    var titulo: String
    /// «Escribir en el campo «Asunto»» (con el rol y el nombre que da el sistema)
    var que: String
    /// Lo que escribiría (lo único que viene del modelo, y se enseña tal cual, como dato)
    var valores: [ValorTarjeta]
    /// «Mail · «Nuevo mensaje»» (+ el sitio)
    var donde: String
    /// «Leyó tu pantalla: Chrome · mail.google.com» o nil
    var leyo: String?
    var modo: Modo
    var comoLoHago: String
    var deshacer: String
    /// El botón se activa a los 0.6 s; la naranja además se sostiene 1.5 s.
    var armaMs: Int
    var sostenerMs: Int
    var puedeConfiar: Bool
    var confiarTexto: String?
    var ensayo: Bool
    var vence: TimeInterval
    /// Los botones, en orden: hazlo · a_la_vista (si va en segundo plano) · ensename · no
    var botones: [String]
    /// Ronda 2 (H-2): si su casilla es «No me preguntes para abrir …», de qué tipo (nil: sin esa casilla).
    var recordable: String? = nil

    static let armaMs = 600
    static let sostenerMs = 1500
    /// Sin respuesta, se cancela (antes de que el motor deje de esperar a actuar: manos_mcp, 85 s).
    static let vence: TimeInterval = 75

    func json() -> [String: Any] {
        var d: [String: Any] = ["id": id, "color": color.rawValue, "agente": agente, "titulo": titulo, "que": que,
                                "valores": valores.map { ["campo": $0.campo, "valor": $0.valor] }, "donde": donde,
                                "modo": modo.rawValue, "como": comoLoHago, "deshacer": deshacer, "arma_ms": armaMs,
                                "sostener_ms": sostenerMs, "puede_confiar": puedeConfiar, "ensayo": ensayo,
                                "vence_s": vence, "botones": botones]
        if let l = leyo { d["leyo"] = l }
        if let c = confiarTexto { d["confiar"] = c }
        if let r = recordable { d["recordable"] = r }
        return d
    }
}

enum ArmarTarjeta {
    /// El nombre del elemento como lo dice el sistema: «el campo «Asunto»», «el botón «Siguiente»».
    static let articulo: [String: String] = [
        "campo": "el campo", "área de texto": "el área de texto", "búsqueda": "la búsqueda", "botón": "el botón",
        "casilla": "la casilla", "opción": "la opción", "pestaña": "la pestaña", "menú desplegable": "el menú",
        "enlace": "el enlace", "lista": "la lista", "celda": "la celda", "fecha": "la fecha", "interruptor": "el interruptor",
        "opción de menú": "la opción de menú", "menú": "el menú", "contraseña": "el campo de contraseña",
        "botón de menú": "el botón",
    ]

    /// El nombre del elemento como lo dice el sistema: «el campo «Asunto»», «el botón «Siguiente»».
    static func elemento(_ d: Destino) -> String {
        let rol = Recorte.rolSimple(d.rol ?? "", subrol: d.subrol)
        let r = d.rol == nil ? "lo de" : (articulo[rol] ?? "el " + rol)
        if let e = d.etiqueta.flatMap({ Texto.limpio($0, tope: 60) }) { return r + " «" + e + "»" }
        return r + " (sin nombre)"
    }

    static func archivo(_ r: String?) -> String { "«" + ((r ?? "") as NSString).lastPathComponent + "»" }

    static func carpeta(_ r: String?) -> String { "«" + (((r ?? "") as NSString).deletingLastPathComponent as NSString).lastPathComponent + "»" }

    static func que(_ t: TipoAccion, _ ds: [Destino]) -> (titulo: String, que: String) {
        let d = ds.first ?? Destino()
        let app = d.app.isEmpty ? "esta app" : d.app
        switch t {
        case .escribir: return ("¿Escribo en \(app)?", "Escribir en \(elemento(d)), sin Enter")
        case .llenar: return ("¿Lleno \(ds.count == 1 ? "1 campo" : "\(ds.count) campos") en \(app)?", "Llenar \(ds.count == 1 ? "1 campo" : "\(ds.count) campos"), sin enviar")
        case .presionar: return ("¿Aprieto en \(app)?", "Apretar \(elemento(d))")
        case .elegir: return ("¿Elijo en \(app)?", "Elegir \(elemento(d))")
        case .abrir:
            if let a = d.abrirApp { let n = d.abrirNombre ?? a; return ("¿Abro \(n)?", "Abrir la app «\(n)»") }
            if Borrador.es(d.abrirURL) { return ("¿Preparo este correo?", "Dejar un borrador de correo (no lo envío: «Enviar» lo aprietas tú)") }
            if let u = d.abrirURL { return ("¿Abro esta página?", "Abrir «" + u + "»") }      // entera (Fable v2 §1.5)
            if d.enFinder { return ("¿Te enseño \(archivo(d.ruta)) en Finder?", "Mostrar \(archivo(d.ruta)) en Finder (no lo abre)") }
            if d.esCarpeta { return ("¿Abro la carpeta \(archivo(d.ruta))?", "Abrir la carpeta \(archivo(d.ruta)) en Finder") }
            return ("¿Abro \(archivo(d.ruta))?", "Abrir el archivo \(archivo(d.ruta)) (en \(carpeta(d.ruta)))")
        case .mover: return ("¿Muevo \(archivo(d.ruta))?", "Mover \(archivo(d.ruta)) de \(carpeta(d.ruta)) a \(carpeta(d.rutaDestino))")
        case .renombrar: return ("¿Le cambio el nombre?", "Renombrar \(archivo(d.ruta)) a \(archivo(d.rutaDestino))")
        case .borrar: return ("¿Mando \(archivo(d.ruta)) a la Papelera?", "Mandar \(archivo(d.ruta)) a la Papelera")
        case .enviar: return ("¿Mando esto?", "Mandar con \(elemento(d))")
        case .compartir: return ("¿Lo comparto?", "Compartir con \(elemento(d))")
        case .subir: return ("¿Lo subo?", "Subir con \(elemento(d))")
        }
    }

    /// Abrir: dónde (la ventana de enfrente no cuenta: no se toca). Con lo que dice el sistema.
    static func dondeAbrir(_ d: Destino) -> String {
        if d.abrirApp != nil { return "Tu Mac" + (d.abrirAbierta ? " · ya está abierta" : "") }
        if Borrador.es(d.abrirURL) { return "En tu app de correo" + (d.abrirNombre.map { ": " + $0 } ?? "") }
        if d.abrirURL != nil { return "En tu navegador" + (d.abrirNombre.map { ": " + $0 } ?? "") }
        if d.enFinder || d.esCarpeta { return "En Finder" }
        if let n = d.abrirNombre { return "Se abre con " + n }
        return "No sé con qué app se abriría"
    }

    /// Abrir: cómo (en segundo plano, detrás de tu ventana; a la vista, al frente y el monito te enseña dónde).
    static func comoAbrir(_ d: Destino, _ m: Modo) -> String {
        if d.enFinder { return "Finder sale al frente con el archivo marcado." }
        switch m {
        case .segundoPlano: return "Lo abro detrás de tu ventana: no te quito el foco."
        case .aLaVista: return "Lo abro al frente y el monito te enseña dónde quedó."
        default: return m.comoLoHago
        }
    }

    static func donde(_ d: Destino) -> String {
        var s = d.app.isEmpty ? (d.bundle.isEmpty ? "Tu Mac" : d.bundle) : d.app
        if let v = d.ventana.flatMap({ Texto.limpio($0, tope: 70) }) { s += " · «" + v + "»" }
        if let h = d.sitio { s += " · " + h }
        return s
    }

    /// `recordable` (ronda 2, A1): la casilla es «No me preguntes para abrir …» (un tipo de los tres); solo amarillo.
    static func de(id: String, pedido p: PedidoAccion, destinos ds: [Destino], color: ColorAccion, agente: String,
                   modo: Modo, etapa: Etapa, lecturas: Lecturas, recordable: TipoRecordado? = nil) -> Tarjeta {
        let t = p.tipoConocido ?? .presionar
        let (titulo, que) = que(t, ds)
        var valores: [ValorTarjeta] = []
        // lo que escribiría, ENTERO (Fable v2 §1.5: lo que no se ve no se aprueba; lo que no cabe ni se pide)
        if t == .escribir, let v = p.valor { valores.append(ValorTarjeta(campo: ds.first?.etiqueta ?? "", valor: v)) }
        if t == .llenar {
            for (i, d) in ds.enumerated() where i < p.campos.count {
                valores.append(ValorTarjeta(campo: d.etiqueta ?? Recorte.rolSimple(d.rol ?? ""), valor: p.campos[i].valor))
            }
        }
        let d0 = ds.first ?? Destino()
        // carril 6 · un borrador: para, asunto y texto, cada uno ENTERO en su renglón (lo que no se ve no se aprueba)
        if p.borrador, t == .abrir, let b = Borrador.de(d0.abrirURL ?? "") {
            valores = [ValorTarjeta(campo: "Para", valor: b.paraQuien), ValorTarjeta(campo: "Asunto", valor: b.asunto),
                       ValorTarjeta(campo: "Texto", valor: b.texto)]
        }
        // la confianza solo en ensayo (A0): en A1 está congelada hasta A3 (Fable v2)
        let confiable = color == .amarillo && modo != .conTuCursor && !d0.bundle.isEmpty && etapa == .ensayo
        let abrir = t == .abrir
        var botones = ["hazlo"]
        if modo == .segundoPlano { botones.append("a_la_vista") }
        if modo != .ensename { botones.append("ensename") }
        botones.append("no")
        let est = Deshacer.estrategia(t, d0)
        if etapa != .ensayo, color == .amarillo, modo != .conTuCursor, let r = recordable {
            // A1: la casilla de la tarjeta es «no me preguntes» por TIPO (la confianza por app sigue congelada)
            var k = Tarjeta(id: id, color: color, agente: agente, titulo: titulo, que: que, valores: valores,
                            donde: abrir ? dondeAbrir(d0) : donde(d0), leyo: lecturas.resumen, modo: modo,
                            comoLoHago: abrir ? comoAbrir(d0, modo) : modo.comoLoHago,
                            deshacer: abrir ? Deshacer.textoAbrir(d0) : Deshacer.texto(est),
                            armaMs: Tarjeta.armaMs, sostenerMs: 0, puedeConfiar: true, confiarTexto: r.casilla,
                            ensayo: false, vence: Tarjeta.vence, botones: botones)
            k.recordable = r.rawValue
            return k
        }
        return Tarjeta(id: id, color: color, agente: agente, titulo: titulo, que: que, valores: valores,
                       donde: abrir ? dondeAbrir(d0) : donde(d0), leyo: lecturas.resumen, modo: modo,
                       comoLoHago: abrir ? comoAbrir(d0, modo) : modo.comoLoHago,
                       deshacer: abrir ? Deshacer.textoAbrir(d0) : Deshacer.texto(est),
                       armaMs: Tarjeta.armaMs, sostenerMs: color == .naranja ? Tarjeta.sostenerMs : 0,
                       puedeConfiar: confiable,
                       confiarTexto: confiable ? "Confío en \(agente) para lo amarillo en \(d0.app.isEmpty ? d0.bundle : d0.app)\(d0.sitio.map { " (\($0))" } ?? "") hoy" : nil,
                       ensayo: etapa == .ensayo, vence: Tarjeta.vence, botones: botones)
    }
}

/// El botón de la tarjeta: se activa a los 0.6 s de aparecer; el naranja, además, hay que sostenerlo 1.5 s.
enum Armado {
    static func activo(_ t: Tarjeta, mostradaHace: TimeInterval) -> Bool { mostradaHace * 1000 >= Double(t.armaMs) }

    /// ¿Ya se puede dar el OK? `sostenidoHace`: cuánto lleva apretado el botón (nil si no está apretado).
    static func listo(_ t: Tarjeta, mostradaHace: TimeInterval, sostenidoHace: TimeInterval?) -> Bool {
        guard activo(t, mostradaHace: mostradaHace) else { return false }
        if t.sostenerMs == 0 { return true }
        guard let s = sostenidoHace else { return false }
        return s * 1000 >= Double(t.sostenerMs)
    }
}

/// Dónde sale la tarjeta: lejos del mouse (en la otra mitad de la pantalla, a lo ancho y a lo alto), dentro de lo que
/// se ve, y nunca a menos de `distancia` del puntero. Todo en coordenadas de AppKit (y hacia arriba).
enum LugarTarjeta {
    static func marco(tam: CGSize, raton r: CGPoint, visible vf: CGRect, margen m: CGFloat = 24, distancia: CGFloat = 160) -> CGRect {
        let izq = r.x > vf.midX                  // el mouse a la derecha → la tarjeta a la izquierda
        let abajo = r.y > vf.midY                // el mouse arriba → la tarjeta abajo
        var x = izq ? vf.minX + m : vf.maxX - m - tam.width
        var y = abajo ? vf.minY + m : vf.maxY - m - tam.height
        x = min(max(x, vf.minX + 4), max(vf.minX + 4, vf.maxX - tam.width - 4))
        y = min(max(y, vf.minY + 4), max(vf.minY + 4, vf.maxY - tam.height - 4))
        var f = CGRect(x: x, y: y, width: tam.width, height: tam.height)
        if distanciaA(f, r) < distancia {        // pantalla chica: lo más lejos posible a lo alto
            f.origin.y = abajo ? vf.minY + 4 : max(vf.minY + 4, vf.maxY - tam.height - 4)
        }
        return f
    }

    static func distanciaA(_ f: CGRect, _ p: CGPoint) -> CGFloat {
        let dx = max(f.minX - p.x, 0, p.x - f.maxX), dy = max(f.minY - p.y, 0, p.y - f.maxY)
        return (dx * dx + dy * dy).squareRoot()
    }
}

// MARK: deshacer, por tipo de acción

enum EstrategiaDeshacer: String {
    case cerrar = "cerrar"
    case regresarValor = "regresar_valor"
    case regresarArchivo = "regresar_archivo"
    case regresarNombre = "regresar_nombre"
    case sacarDePapelera = "sacar_de_papelera"
    case ninguna = "ninguna"
}

/// Lo que se hizo (para deshacerlo).
struct Hecho: Equatable {
    var tipo: TipoAccion
    var antes: Destino
    /// Escribir/llenar/elegir: lo que quedó en el campo.
    var escrito: String? = nil
    /// Mover/renombrar/borrar: dónde quedó.
    var rutaFinal: String? = nil
    /// Abrir una app: no estaba abierta antes (si ya estaba, no se cierra).
    var appNueva: Bool = false
}

enum Deshacer {
    static func estrategia(_ t: TipoAccion, _ d: Destino) -> EstrategiaDeshacer {
        switch t {
        case .abrir:
            // «Cerrar» solo lo que abrí yo: una app (o la app de un archivo) que no estaba abierta; nunca tu navegador ni Finder
            if d.abrirURL != nil || d.enFinder || d.esCarpeta || d.abrirAbierta { return .ninguna }
            return d.abrirApp != nil || d.ruta != nil ? .cerrar : .ninguna
        case .escribir, .llenar: return .regresarValor
        case .elegir: return d.rol == "AXCheckBox" || d.rol == "AXRadioButton" || d.rol == "AXPopUpButton" || d.rol == "AXTab" ? .regresarValor : .ninguna
        case .mover: return .regresarArchivo
        case .renombrar: return .regresarNombre
        case .borrar: return .sacarDePapelera
        case .presionar, .enviar, .compartir, .subir: return .ninguna
        }
    }

    static func texto(_ e: EstrategiaDeshacer) -> String {
        switch e {
        case .cerrar: return "Se deshace: lo cierro."
        case .regresarValor: return "Se deshace: regreso lo que decía antes."
        case .regresarArchivo: return "Se deshace: lo regreso a su carpeta."
        case .regresarNombre: return "Se deshace: le regreso su nombre."
        case .sacarDePapelera: return "Se deshace: lo saco de la Papelera."
        case .ninguna: return "No se deshace solo: si hace falta, te enseño cómo regresar."
        }
    }

    /// Abrir: lo que dice la tarjeta de su Deshacer (honesto: lo que no se cierra solo, lo dice).
    static func textoAbrir(_ d: Destino) -> String {
        let n = d.abrirNombre ?? d.abrirApp ?? d.abrirCon ?? "su app"
        if Borrador.es(d.abrirURL) { return "Es un borrador: si no lo quieres, cierras su ventana sin enviarlo." }
        if d.abrirURL != nil { return "La pestaña la cierras tú (⌘W): no manejo tu navegador." }
        if d.enFinder || d.esCarpeta { return "La ventana de Finder la cierras tú (⌘W)." }
        if d.abrirApp != nil { return d.abrirAbierta ? "\(n) ya está abierta: no la cierro después." : "Se deshace: «Cerrar» la cierra." }
        return d.abrirAbierta ? "\(n) ya está abierta: esa ventana la cierras tú (⌘W)." : "Se deshace: «Cerrar» cierra \(n)."
    }

    /// ¿Todavía se puede deshacer? nil = sí; si no, por qué (en simple). `ahora`: el campo como está ahora;
    /// `existe`: si una ruta existe.
    static func posible(_ h: Hecho, ahora: Destino?, existe: (String) -> Bool) -> String? {
        var antes = h.antes
        if h.tipo == .abrir { antes.abrirAbierta = !h.appNueva }          // lo que vale es lo que pasó al abrir
        switch estrategia(h.tipo, antes) {
        case .ninguna:
            if h.tipo == .abrir, antes.ruta != nil, antes.abrirURL == nil, !antes.esCarpeta, !antes.enFinder {
                return "Su app ya estaba abierta: esa ventana la cierras tú (⌘W)."
            }
            return "Eso no se deshace solo."
        case .regresarValor:
            guard let a = ahora else { return "El campo ya no está." }
            if (a.valor ?? "") != (h.escrito ?? "") { return "Ya lo cambiaste tú: no lo piso." }
            return nil
        case .regresarArchivo, .regresarNombre:
            guard let f = h.rutaFinal, existe(f) else { return "El archivo ya no está donde lo dejé." }
            guard let o = h.antes.ruta else { return "No sé dónde estaba." }
            if existe(o) { return "Ya hay otro archivo donde estaba: no lo piso." }
            return nil
        case .sacarDePapelera:
            guard let f = h.rutaFinal, existe(f) else { return "Ya no está en la Papelera." }
            if let o = h.antes.ruta, existe(o) { return "Ya hay otro archivo donde estaba: no lo piso." }
            return nil
        case .cerrar:
            if !h.appNueva {
                return h.antes.abrirApp != nil ? "La app ya estaba abierta: no la cierro." : "Su app ya estaba abierta: esa ventana la cierras tú (⌘W)."
            }
            return nil
        }
    }
}

/// Mover y renombrar archivos (y regresarlos), solo dentro de `raiz`. Lo usa el portero de pruebas sobre carpetas de
/// prueba; en A0 la app no lo llama (en ensayo nada se hace de verdad).
enum Archivos {
    static func dentro(_ r: String, _ raiz: String) -> Bool {
        let a = (r as NSString).standardizingPath, b = (raiz as NSString).standardizingPath
        return a.hasPrefix(b + "/")
    }

    /// → nil si se hizo; si no, por qué.
    static func mover(_ de: String, a: String, raiz: String, fm: FileManager = .default) -> String? {
        guard dentro(de, raiz), dentro(a, raiz) else { return "fuera de la carpeta de prueba" }
        guard fm.fileExists(atPath: de) else { return "no existe" }
        guard !fm.fileExists(atPath: a) else { return "ya hay algo con ese nombre" }
        do { try fm.moveItem(atPath: de, toPath: a) } catch { return "no se pudo: \(error.localizedDescription)" }
        return nil
    }

    /// Deshacer un mover o renombrar (con lo de Deshacer.posible).
    static func deshacer(_ h: Hecho, raiz: String, fm: FileManager = .default) -> String? {
        if let p = Deshacer.posible(h, ahora: nil, existe: { fm.fileExists(atPath: $0) }) { return p }
        guard let f = h.rutaFinal, let o = h.antes.ruta else { return "no sé qué regresar" }
        return mover(f, a: o, raiz: raiz, fm: fm)
    }
}

// MARK: Fable v2 §1.5 · solo cuentan los clics de una persona

/// La tarjeta de OK acepta solo clics del mouse o el trackpad. El sistema dice de dónde viene cada evento: uno que mandó
/// otro programa (publicado con las funciones de eventos de CoreGraphics, a toda la sesión o a un proceso, o un «clic» por AppleScript o por accesibilidad) trae el número de ese
/// proceso (`eventSourceUnixProcessID`) y no el estado del HID; uno del mouse de verdad lo arma el sistema (proceso 0,
/// estado HID). Límite honesto: un programa con Accesibilidad que falsifique esos campos no se distingue así; para eso
/// están el armado de 0.6 s, el sostener de la naranja y la bitácora (cada clic rechazado queda anotado).
enum EventoReal {
    static func esDeUnaPersona(pid: Int64, estado: Int64) -> Bool {
        pid == 0 && estado == Int64(CGEventSourceStateID.hidSystemState.rawValue)
    }

    static func de(_ e: CGEvent?) -> Bool {
        guard let e = e else { return false }
        return esDeUnaPersona(pid: e.getIntegerValueField(.eventSourceUnixProcessID),
                              estado: e.getIntegerValueField(.eventSourceStateID))
    }
}

// MARK: Fable v2 §1b · abrir sin traer la app al frente (en segundo plano)

enum ComoAbrir {
    /// ¿Abrir trae la app al frente? En segundo plano, NO: lo que estabas tecleando no cae en otra parte
    /// (NSWorkspace.OpenConfiguration.activates). Solo «a la vista» (lo pediste) la trae.
    static func activar(_ m: Modo) -> Bool { m == .aLaVista }
}

// MARK: A1 · el aviso tranquilo de lo que abrió (y lo que se le dice al agente), honesto con lo que se deshace

struct AvisoAbrir: Equatable {
    /// El aviso de la burbuja («Abrí Calculadora detrás de tu ventana.»)
    var texto: String
    /// Lo que se le dice al agente (para que lo cuente en una frase)
    var agente: String
    /// «Cerrar» si se puede deshacer (una app que no estaba abierta); nil si no
    var boton: String?

    static func de(_ d: Destino, appNueva: Bool, modo: Modo, robo: Bool, devuelto: Bool) -> AvisoAbrir {
        let n = d.abrirNombre ?? d.abrirApp ?? d.abrirCon ?? "su app"
        let detras = !ComoAbrir.activar(modo) && !d.enFinder
        let tras = detras ? " detrás de tu ventana" : ""
        let quieto = detras ? " en segundo plano (no le quité el foco)" : ""
        var texto: String, agente: String, boton: String? = nil
        if d.enFinder {
            texto = "Te enseño \(ArmarTarjeta.archivo(d.ruta)) en Finder."
            agente = "Listo: le enseñé \(ArmarTarjeta.archivo(d.ruta)) en Finder (la ventana la cierra él)."
        } else if d.abrirApp != nil {
            if appNueva {
                texto = "Abrí \(n)\(tras)."
                agente = "Listo: abrí la app «\(n)»\(quieto). El monito le ofrece «Cerrar»."
                boton = "Cerrar"
            } else {
                texto = "\(n) ya estaba abierta" + (detras ? ": la dejé detrás de tu ventana." : ": la traje al frente.")
                agente = "Listo: «\(n)» ya estaba abierta" + (detras ? " (la dejé detrás de su ventana)." : " (la traje al frente).")
            }
        } else if let b = Borrador.de(d.abrirURL ?? "") {
            texto = "Dejé el borrador en \(n)\(tras). No lo envié: «Enviar» lo aprietas tú."
            agente = "Listo: dejé el borrador para \(b.paraQuien) en \(n)\(quieto). NO se envió: «Enviar» lo aprieta él. Díselo así."
        } else if let u = d.abrirURL {
            let h = Destino.host(u) ?? u
            texto = "Abrí \(h) en \(n)\(tras). La pestaña la cierras tú (⌘W)."
            agente = "Listo: abrí la página en \(n)\(quieto). La pestaña la cierra él."
        } else if d.esCarpeta {
            texto = "Abrí la carpeta \(ArmarTarjeta.archivo(d.ruta)) en Finder\(tras). La ventana la cierras tú (⌘W)."
            agente = "Listo: abrí la carpeta \(ArmarTarjeta.archivo(d.ruta)) en Finder\(quieto)."
        } else {
            let a = ArmarTarjeta.archivo(d.ruta)
            if appNueva {
                texto = "Abrí \(a) con \(n)\(tras)."
                agente = "Listo: abrí \(a) con \(n)\(quieto). El monito le ofrece «Cerrar»."
                boton = "Cerrar"
            } else {
                texto = "Abrí \(a) con \(n)\(tras). \(n) ya estaba abierta: esa ventana la cierras tú (⌘W)."
                agente = "Listo: abrí \(a) con \(n)\(quieto)."
            }
        }
        if robo {
            texto += " \(n) se puso al frente sola" + (devuelto ? "; te regresé a tu ventana." : ".")
            agente += " (La app se puso al frente sola" + (devuelto ? "; el monito le regresó su ventana.)" : ".)")
        }
        return AvisoAbrir(texto: texto, agente: agente, boton: boton)
    }
}

// MARK: AC3-b · prender «Puede hacer cosas en mi Mac» desde la burbuja (solo con la confirmación nativa y un clic real)

/// Un agente que no lo tiene prendido pidió hacer algo: su pedido ESPERA (hasta `espera`) a que lo prendas. El botón
/// «Prender para <agente>» de la burbuja (o cualquier op que llegue a la app) solo puede ABRIR la confirmación nativa de
/// la app, y solo para el pedido que espera; únicamente un clic de una persona en su [Prender], a tiempo, lo prende
/// (`confirmar` devuelve a quién). Una vez: después ya no espera nada. Lo prendido se guarda como desde el menú.
struct Encendido: Equatable {
    /// Lo que espera el pedido (el botón de la burbuja y la confirmación); luego viene su tarjeta de OK (75 s): las manos
    /// y el motor esperan más que la suma (manos_mcp.TOPES["actuar"]).
    static let espera: TimeInterval = 40

    struct Pedido: Equatable {
        var id: String
        var agente: String
        var desde: Date
    }

    private(set) var pedido: Pedido?
    /// La confirmación nativa está enseñada (una a la vez).
    private(set) var confirmando = false

    func vencido(_ ahora: Date) -> Bool {
        guard let p = pedido else { return true }
        return ahora.timeIntervalSince(p.desde) > Encendido.espera
    }

    /// Un pedido de `agente` empieza a esperar. → false si ya hay uno (vivo) o no hay agente.
    mutating func pedir(id: String, agente: String, ahora: Date) -> Bool {
        guard !agente.isEmpty, !id.isEmpty, pedido == nil || vencido(ahora) else { return false }
        pedido = Pedido(id: id, agente: agente, desde: ahora)
        confirmando = false
        return true
    }

    /// El botón de la burbuja: ¿la app enseña su confirmación? Solo para ESE pedido (id y agente), a tiempo y una vez.
    mutating func abrir(id: String, agente: String, ahora: Date) -> Bool {
        guard let p = pedido, p.id == id, p.agente == agente, !confirmando, !vencido(ahora) else { return false }
        confirmando = true
        return true
    }

    /// [Prender] en la confirmación nativa: solo con ella enseñada, a tiempo y con un clic de una persona. → el agente a
    /// prender (y el pedido deja de esperar), o nil (no prende nada).
    mutating func confirmar(id: String, persona: Bool, ahora: Date) -> String? {
        guard persona, confirmando, let p = pedido, p.id == id, !vencido(ahora) else { return nil }
        pedido = nil
        confirmando = false
        return p.agente
    }

    /// Ahora no, el pánico, el fin del turno o vencido: ya no espera. → el pedido que esperaba.
    @discardableResult
    mutating func cancelar() -> Pedido? {
        let p = pedido
        pedido = nil
        confirmando = false
        return p
    }
}

// MARK: A1 · las apps instaladas, por su nombre (el de tu idioma también) o su identificador

/// Una app instalada, según el sistema: su identificador, sus nombres (el del archivo, el del paquete, el de cada idioma)
/// y dónde está. La lista la arma la app (Hacer.swift, Mano.instaladas) con LaunchServices y el disco.
struct AppConocida: Equatable {
    var bundle: String
    var nombres: [String]
    var ruta: String
}

enum Apps {
    /// Las que se llaman así: por su identificador, por un nombre entero («Calculadora», «la Calculadora», «Calculator.app»)
    /// o, si es la única, por una palabra entera de su nombre de 4 letras o más («Word» → «Microsoft Word»). Medio nombre
    /// no se adivina. Varias con el mismo nombre: todas (la app pregunta cuál).
    static func buscar(_ nombre: String, en lista: [AppConocida]) -> [AppConocida] {
        var n = nombre.trimmingCharacters(in: .whitespacesAndNewlines)
        if n.lowercased().hasSuffix(".app") { n = String(n.dropLast(4)) }
        guard !n.isEmpty else { return [] }
        func unicas(_ l: [AppConocida]) -> [AppConocida] {
            var vistos = Set<String>()
            return l.filter { vistos.insert($0.bundle.lowercased()).inserted }
        }
        if n.contains("."), !n.contains(" ") {
            let x = lista.filter { $0.bundle.lowercased() == n.lowercased() }
            if !x.isEmpty { return unicas(x) }
        }
        var q = Busqueda.normal(n)
        for art in ["la app ", "la aplicacion ", "el programa ", "app ", "aplicacion ", "el ", "la ", "los ", "las ", "the "] where q.hasPrefix(art) {
            q = String(q.dropFirst(art.count))
            break
        }
        guard !q.isEmpty else { return [] }
        let exactas = lista.filter { $0.nombres.contains { Busqueda.normal($0) == q } }
        if !exactas.isEmpty { return unicas(exactas) }
        guard q.count >= 4, !q.contains(" ") else { return [] }
        let palabra = unicas(lista.filter { $0.nombres.contains { (" " + Busqueda.normal($0) + " ").contains(" " + q + " ") } })
        return palabra.count == 1 ? palabra : []
    }
}

// MARK: los frenos (pánico, la banda «en vivo», la pausa si mueves el mouse)

enum Frenos {
    /// Esc Esc: dos Esc en menos de esto.
    static let dobleEsc: TimeInterval = 0.6
    /// Con tu cursor: una tarea, hasta 60 s; antes, una cuenta regresiva de 3 s.
    static let topeCursor: TimeInterval = 60
    static let cuentaRegresiva = 3
    /// Si el mouse se mueve más que esto de donde lo dejó el monito, se pausa.
    static let toleranciaMouse: CGFloat = 6

    static func esDobleEsc(previo: Date?, ahora: Date) -> Bool {
        guard let p = previo else { return false }
        let d = ahora.timeIntervalSince(p)
        return d >= 0 && d <= dobleEsc
    }

    static func movioElMouse(esperado e: CGPoint, real r: CGPoint) -> Bool {
        abs(e.x - r.x) > toleranciaMouse || abs(e.y - r.y) > toleranciaMouse
    }

    static func reloj(_ s: Int) -> String { String(format: "%d:%02d", max(0, s) / 60, max(0, s) % 60) }

    /// «Luna está usando tu mouse · paso 3 de 6 · 0:14»
    static func banda(agente: String, paso: Int, de: Int, segundos: Int) -> String {
        "\(agente) está usando tu mouse · paso \(paso) de \(de) · " + reloj(segundos)
    }

    /// «Empiezo en 3…»
    static func cuenta(_ n: Int) -> String { n > 0 ? "\(n)…" : "Empiezo" }
}

// MARK: la bitácora de acciones (local, 30 días)

enum BitacoraAcciones {
    static let dias: Double = 30
    static let carpeta = "acciones"
    static let archivo = "bitacora.jsonl"

    static func corto(_ s: String?, _ n: Int = 200) -> String? { s.map { $0.count > n ? String($0.prefix(n)) + "…" : $0 } }
}

// MARK: el portero: la máquina que decide (la usa la app y, por línea de comandos, las pruebas de ataques)

struct Respuesta {
    var salida: Salida
    var color: ColorAccion = .verde
    var motivo: String = ""
    var tarjeta: Tarjeta? = nil
    var autorizacion: String? = nil
    var ensayo: Bool = false
    var ejecutada = false
    /// Ronda 2 · lo que la ficha necesita (siempre viene en la respuesta de `pedir`).
    var ficha: Ficha? = nil
    /// Ronda 2 (H-2) · al contestar: ese fue el tercer OK de este tipo y no está recordado («Ya van 3. ¿Dejo de preguntarte…?»).
    var ofrecerRecordar: TipoRecordado? = nil

    func json() -> [String: Any] {
        var d: [String: Any] = ["salida": salida.rawValue, "color": color.rawValue, "motivo": motivo, "ensayo": ensayo,
                                "ejecutada": ejecutada]
        if let t = tarjeta { d["tarjeta"] = t.json() }
        if let a = autorizacion { d["autorizacion"] = a }
        if let f = ficha { d["ficha"] = f.json() }
        if let o = ofrecerRecordar { d["ofrecer_recordar"] = o.rawValue; d["pregunta_recordar"] = o.pregunta }
        return d
    }
}

final class Portero {
    var etapa: Etapa
    var vetados = Vetados()
    var confianzas = Confianzas()
    /// Por agente: el modo de fábrica y si puede tomar el mouse.
    var modos: [String: Modo] = [:]
    var mouse: [String: MouseAgente] = [:]
    var reloj: () -> Date
    var calendario: Calendar
    var nuevoId: () -> String
    /// Las líneas nuevas de la bitácora (quien hospeda al portero las escribe y vacía esta lista).
    var registro: [[String: Any]] = []

    private(set) var turno: String?
    private(set) var agente = ""
    /// Lo que leyó cada agente en SU conversación del monito (no en el turno: lo del turno 1 sigue en su cabeza en el
    /// turno 2). Ronda 2 (H-3): con su hora y su turno; se apaga sola al terminar el día, o si el socio la borra
    /// («Olvidar lo leído») o empieza otra conversación. Solo el nombre de la app y el título no cuentan.
    private var lecturasPor: [String: Lecturas] = [:]
    var lecturas: Lecturas { lecturas(de: agente) }
    func lecturas(de a: String) -> Lecturas {
        (lecturasPor[a] ?? Lecturas()).vigentes(ahora: reloj(), calendario: calendario, turno: a == agente ? turno : nil)
    }
    private(set) var usadasConfianza = 0
    /// Ronda 2 (H-2) · lo que el socio recordó («no me preguntes para abrir apps / archivos / páginas»). Solo cambia con
    /// un clic de una persona (la casilla de la ficha, o el menú). Quien hospeda al portero lo carga y lo guarda.
    var recordados = Recordados()
    var alCambiarRecordados: (() -> Void)?
    /// Cómo ve el socio a cada agente (para el título de la ficha); sin nombre, su id.
    var nombres: [String: String] = [:]
    private(set) var ceroEnTurno = 0
    private(set) var ejecutadasCero = 0
    /// Cuántas veces se ejecutó algo (o, en ensayo, se habría ejecutado), y por qué vía.
    private(set) var ejecutadas: [(autorizacion: String, porConfianza: Bool)] = []

    private struct Pendiente {
        var tarjeta: Tarjeta
        var pedido: PedidoAccion
        var destinos: [Destino]
        var huellas: [Huella]
        var desde: Date
        /// La casilla que traía la ficha (nil: sin casilla).
        var recordable: TipoRecordado? = nil
    }
    private var pendientes: [String: Pendiente] = [:]
    private var autorizaciones: [String: Autorizacion] = [:]

    init(etapa: Etapa = .ensayo, reloj: @escaping () -> Date = Date.init, calendario: Calendar = .current,
         nuevoId: @escaping () -> String = { UUID().uuidString.lowercased() }) {
        self.etapa = etapa
        self.reloj = reloj
        self.calendario = calendario
        self.nuevoId = nuevoId
    }

    var tarjetasAbiertas: [Tarjeta] { pendientes.values.map { $0.tarjeta } }

    func modo(de a: String) -> Modo { modos[a] ?? Modo.deFabrica }
    func mouse(de a: String) -> MouseAgente { mouse[a] ?? MouseAgente.deFabrica }

    // — el turno —
    /// Un turno nuevo de la burbuja. Lo que leyó antes en su conversación NO se borra (sigue en la cabeza del agente).
    func abrirTurno(_ id: String, agente a: String) {
        if turno != nil { cerrarTurno() }
        turno = id
        agente = a
        usadasConfianza = 0
        ceroEnTurno = 0
    }

    /// Terminó el turno: lo que esperaba tu OK se cancela y ningún OK sobrevive.
    func cerrarTurno() {
        for (_, p) in pendientes { anotar(p.pedido, p.destinos, p.tarjeta.color, salida: "tarjeta", resultado: "cancelada", motivo: "se acabó el turno", tarjeta: p.tarjeta.id) }
        pendientes = [:]
        autorizaciones = [:]
        turno = nil
        usadasConfianza = 0
        ceroEnTurno = 0
        for a in olvidarAlCerrar { lecturasPor[a] = nil }       // lo que el socio pidió olvidar a medio turno
        olvidarAlCerrar = []
    }

    /// Leyó tu pantalla o contenido ajeno en la conversación del agente del turno (o de `agente`).
    /// Ronda 2 (H-3): el portero le pone la hora y el turno (quien llama no los decide). Solo el nombre de la app y el
    /// título de la ventana (tipo «titulo») no cuentan: no se anotan.
    func leyo(_ f: Fuente, agente a: String? = nil) {
        let k = a ?? agente
        guard !k.isEmpty, f.cuenta else { return }
        var x = f
        x.cuando = reloj()
        x.turno = k == agente ? turno : nil
        lecturasPor[k, default: Lecturas()].anotar(x)
    }

    /// «Olvidar lo leído» (el socio, en la ficha o en el menú de Compañero). Lo de turnos anteriores se borra ya. Lo que
    /// leyó en el turno que está ABIERTO sigue pesando hasta que ese turno acabe (sigue en la cabeza del agente: si no,
    /// un clic en «Olvidar» a media trampa le abriría la puerta en ese mismo turno) y se borra al cerrarlo.
    func olvidarLecturas(agente a: String) {
        guard a == agente, let t = turno else { lecturasPor[a] = nil; olvidarAlCerrar.remove(a); return }
        let deEsteTurno = (lecturasPor[a]?.fuentes ?? []).filter { $0.turno == t }
        lecturasPor[a] = deEsteTurno.isEmpty ? nil : Lecturas(fuentes: deEsteTurno)
        if !deEsteTurno.isEmpty { olvidarAlCerrar.insert(a) }
    }
    private var olvidarAlCerrar: Set<String> = []
    /// Otra conversación con ese agente: de cero (su cabeza también empieza de cero).
    func nuevaConversacion(agente a: String) { lecturasPor[a] = nil; olvidarAlCerrar.remove(a) }

    /// Lo que la app guarda y recupera al abrir (acciones/lecturas.json, 600): la marca sigue aunque cierres el monito.
    /// Solo las que siguen valiendo (las de ayer ya no se guardan).
    func lecturasGuardables() -> [String: Lecturas] {
        var d: [String: Lecturas] = [:]
        for a in lecturasPor.keys { let l = lecturas(de: a); if !l.fuentes.isEmpty { d[a] = l } }
        return d
    }
    /// Del archivo: solo SUMA, y solo las que traen su hora y son de hoy (una marca vieja, sin hora, ya no cuenta).
    func cargarLecturas(_ d: [String: Lecturas]) {
        for (a, l) in d where !a.isEmpty {
            for f in l.vigentes(ahora: reloj(), calendario: calendario).fuentes { lecturasPor[a, default: Lecturas()].anotar(f) }
        }
    }

    // — lo recordado (H-2): solo desde un clic de una persona —
    /// «No me preguntes para abrir …» (la casilla de la ficha, o «sí» a la oferta del tercer OK).
    func recordar(_ t: TipoRecordado) {
        guard !recordados.tiene(t) else { return }
        recordados.dar(t, ahora: reloj())
        registro.append(linea(["tipo": "recordar", "resultado": "recordado", "que": t.rawValue]))
        alCambiarRecordados?()
    }

    /// El menú del monito («Lo que hace sin preguntar»): quitar uno, o todos.
    @discardableResult
    func quitarRecordado(_ t: TipoRecordado) -> Bool {
        guard recordados.quitar(t) else { return false }
        registro.append(linea(["tipo": "recordar", "resultado": "quitado", "que": t.rawValue]))
        alCambiarRecordados?()
        return true
    }

    func quitarRecordados() {
        guard !recordados.lista.isEmpty else { return }
        recordados.quitarTodos()
        registro.append(linea(["tipo": "recordar", "resultado": "quitado", "que": "todos"]))
        alCambiarRecordados?()
    }

    /// Pánico (Esc Esc, ⌥ Espacio, clic en el monito): todo lo que está en vuelo se cancela. → cuántas cosas paró.
    @discardableResult
    func panico() -> Int {
        let n = pendientes.count + autorizaciones.values.filter { !$0.usada }.count
        for (_, p) in pendientes { anotar(p.pedido, p.destinos, p.tarjeta.color, salida: "tarjeta", resultado: "cancelada", motivo: "pánico", tarjeta: p.tarjeta.id) }
        pendientes = [:]
        autorizaciones = [:]
        return n
    }

    /// Solo clasificar (sin tarjeta ni nada): lo usa señalar y las pruebas.
    func clasificar(_ p: PedidoAccion, _ ds: [Destino]) -> Clasificacion { Clasificador.color(p, ds, vetados: vetados) }

    /// Un pedido de `actuar`. Fuera de turno no hay nada (el candado de la app ya lo frena antes).
    func pedir(_ p: PedidoAccion, destinos ds: [Destino]) -> Respuesta {
        let ahora = reloj()
        confianzas.limpiar(ahora)
        func no(_ m: String, _ col: ColorAccion = .verde) -> Respuesta {
            var f = Ficha(salida: .no, tono: .no)
            f.agente = agente
            f.motivo = m
            f.pedido = ahora
            let (verbo, objeto, detalle, tipo, sitio) = ArmarFicha.verboYObjeto(p.tipoConocido, ds)
            f.verbo = verbo; f.objeto = objeto; f.detalle = detalle; f.detalleTipo = tipo; f.sitio = sitio
            f.titulo = "\(nombreVisible(agente)) no puede \(verbo) \(objeto)"
            return Respuesta(salida: .negado, color: col, motivo: m, ficha: f)
        }
        guard turno != nil else { return no("Nadie me llamó: solo actúo dentro de un turno de la burbuja.") }
        // ¿el elemento es el que dice el modelo? (lo dice el sistema)
        for d in ds {
            if let m = Coincide.revisar(esperado: p.esperado, sistema: d.etiqueta, rol: d.rol) {
                let c = clasificar(p, ds)
                anotar(p, ds, c.color, salida: "negado", resultado: "no_coincide", motivo: m)
                return no(m, c.color)
            }
        }
        if p.tipoConocido == .llenar, p.campos.count != ds.count {
            anotar(p, ds, .rojo, salida: "negado", resultado: "negado", motivo: "campos sin destino")
            return no("Algunos campos no se encontraron en la ventana.", .rojo)
        }
        // lo que leyó puede subir el color, con grados (ronda 2, H-3)
        let leido = lecturas.grado(turno: turno)
        let c = Clasificador.porLoLeido(clasificar(p, ds), p, ds, leido: leido,
                                        sitioConocido: (ds.first?.abrirURL).map { recordados.conocido($0) } ?? false,
                                        direccionNueva: recordados.direccionNueva(ds.first?.abrirURL))
        // el modo: el que pidió el socio (el modelo lo pasa si él lo dijo) o el de fábrica del agente (segundo plano)
        let modo = Modo(rawValue: p.modo ?? "") ?? modo(de: agente)
        var conf: Confianza? = nil, porQueNo: String? = nil
        // la confianza solo en ensayo: en A1 (de verdad) está congelada hasta A3
        if etapa == .ensayo && c.color == .amarillo && modo != .conTuCursor && modo != .ensename, let d0 = ds.first {
            (conf, porQueNo) = confianzas.aplica(agente: agente, destino: d0, color: c.color, lecturas: lecturas, usadas: usadasConfianza, ahora: ahora)
        }
        let hace = etapa == .ensayo ? nil : LoQueHago.deVerdad(p, ds)
        // ronda 2 · A1: lo naranja de abrir una PÁGINA es ficha coral con la dirección entera (ya no «no lo hago»)
        // (junto5: también una página de entregables, que en el turno en que leyó sube a coral)
        let pagina = p.tipoConocido == .abrir && (Portero.esPagina(ds.first?.abrirURL) || Borrador.es(p, ds.first)
            || ds.first.map { !$0.esCarpeta && !$0.enFinder && $0.abrirCon != nil && Clasificador.entregableHTML($0.ruta, casa: $0.casa) } == true)
        // ronda 2 (H-2) · lo recordado: solo A1, solo lo que la mano hace, solo amarillo de uno de los tres tipos; nunca si
        // leyó contenido en este turno, ni más de `topePorTurno` en un turno; una página, solo de un sitio conocido
        let tipoRec = etapa == .amarillo && hace == nil && (modo == .segundoPlano || modo == .aLaVista) ? TipoRecordado.de(p, ds, color: c.color) : nil
        var cero = false
        if let t = tipoRec, recordados.tiene(t) {
            if leido.grado == .esteTurno, let f = leido.fuente {
                porQueNo = "en este turno leyó \(f.texto)"
            } else if ceroEnTurno >= Recordados.topePorTurno {
                porQueNo = "ya hizo \(ceroEnTurno) cosas sin preguntarte en este turno"
            } else if t == .abrirPagina, !((ds.first?.abrirURL).map { recordados.conocido($0) } ?? false) {
                porQueNo = "es un sitio que no has abierto antes"
            } else {
                cero = true
            }
        }
        let v = Politica.decidir(c, modo: modo, etapa: etapa, mouse: mouse(de: agente), confianza: conf != nil, hace: hace,
                                 fichaNaranja: pagina, cero: cero)
        let nombre = nombreVisible(agente)
        func ficha(_ id: String, _ t: Tarjeta?, _ rec: TipoRecordado?) -> Ficha {
            ArmarFicha.de(v, pedido: p, destinos: ds, agente: agente, nombre: nombre, id: id, tarjeta: t, leido: leido,
                          recordable: rec, oks: rec.map { recordados.cuenta($0) } ?? 0, puedeSenalar: c.puedeSenalar, ahora: ahora,
                          turno: turno)
        }
        switch v.salida {
        case .libre:
            anotar(p, ds, v.color, salida: "libre", resultado: "libre", motivo: v.motivo)
            return Respuesta(salida: .libre, color: v.color, motivo: v.motivo, ficha: ficha("", nil, nil))
        case .negado, .senalar:
            anotar(p, ds, v.color, salida: v.salida.rawValue, resultado: v.salida == .senalar ? "senalado" : "negado", motivo: v.motivo)
            return Respuesta(salida: v.salida, color: v.color, motivo: v.motivo, ficha: ficha("", nil, nil))
        case .confianza:
            guard let k = conf else { break }
            usadasConfianza += 1
            let a = Autorizacion(id: nuevoId(), tarjeta: "", tipo: p.tipo, huellas: Huella.lote(ds, p.tipoConocido), desde: ahora, porConfianza: k.id)
            autorizaciones[a.id] = a
            anotar(p, ds, v.color, salida: "confianza", resultado: "autorizado", motivo: v.motivo, confianza: k.id)
            return Respuesta(salida: .confianza, color: v.color, motivo: v.motivo, autorizacion: a.id, ensayo: etapa == .ensayo,
                             ficha: ficha(a.id, nil, nil))
        case .cero:
            guard let t = tipoRec, cero else { break }
            ceroEnTurno += 1
            let a = Autorizacion(id: nuevoId(), tarjeta: "", tipo: p.tipo, huellas: Huella.lote(ds, p.tipoConocido), desde: ahora, porRecordado: t.rawValue)
            autorizaciones[a.id] = a
            let m = "Ya no te pregunto para esto: lo recordaste («\(t.casilla)»)."
            anotar(p, ds, v.color, salida: "cero", resultado: "autorizado", motivo: m, recordado: t.rawValue)
            var f = ficha(a.id, nil, nil)
            f.motivo = m
            if let d0 = ds.first { f.como = ArmarTarjeta.comoAbrir(d0, modo); f.deshacer = Deshacer.textoAbrir(d0) }
            return Respuesta(salida: .cero, color: v.color, motivo: m, autorizacion: a.id, ensayo: false, ficha: f)
        case .tarjeta:
            break
        }
        // la casilla «no me preguntes»: solo si la ficha es de un tipo y no leyó contenido en este turno
        let rec = v.color == .amarillo && leido.grado != .esteTurno ? tipoRec : nil
        let t = ArmarTarjeta.de(id: nuevoId(), pedido: p, destinos: ds, color: v.color, agente: agente, modo: modo,
                                etapa: etapa, lecturas: lecturas, recordable: rec)
        pendientes[t.id] = Pendiente(tarjeta: t, pedido: p, destinos: ds, huellas: Huella.lote(ds, p.tipoConocido), desde: ahora,
                                     recordable: t.recordable.flatMap(TipoRecordado.init(rawValue:)))
        let m = porQueNo.map { "Te pido tu OK (\($0))." } ?? v.motivo
        anotar(p, ds, v.color, salida: "tarjeta", resultado: "pedido", motivo: m, tarjeta: t.id)
        var f = ficha(t.id, t, rec)
        f.motivo = v.color == .naranja ? (c.porque.first ?? m) : m
        return Respuesta(salida: .tarjeta, color: v.color, motivo: m, tarjeta: t, ensayo: etapa == .ensayo, ficha: f)
    }

    /// Cómo ve el socio al agente (limpio y corto: va en el título de la ficha); sin nombre, su id.
    func nombreVisible(_ a: String) -> String {
        nombres[a].flatMap { Texto.limpio($0, tope: 40) } ?? (a.isEmpty ? "El agente" : a)
    }

    /// ¿Una página (http o https)?
    static func esPagina(_ u: String?) -> Bool {
        guard let u = u, let e = URLComponents(string: u)?.scheme?.lowercased() else { return false }
        return e == "http" || e == "https"
    }

    /// ¿La tarjeta sigue valiendo con lo que dice el sistema ahora? nil = sí; si no, qué cambió (y se cancela).
    func vigente(_ tarjeta: String, ahora ds: [Destino]) -> String? {
        guard let p = pendientes[tarjeta] else { return "ya no está" }
        if let c = Huella.cambioLote(p.huellas, Huella.lote(ds, p.pedido.tipoConocido)) {
            pendientes[tarjeta] = nil
            anotar(p.pedido, p.destinos, p.tarjeta.color, salida: "tarjeta", resultado: "cancelada", motivo: c, tarjeta: tarjeta)
            return c
        }
        if reloj().timeIntervalSince(p.desde) > p.tarjeta.vence {
            pendientes[tarjeta] = nil
            anotar(p.pedido, p.destinos, p.tarjeta.color, salida: "tarjeta", resultado: "vencida", motivo: "nadie contestó", tarjeta: tarjeta)
            return "nadie contestó a tiempo"
        }
        return nil
    }

    /// Lo que elegiste en la tarjeta: hazlo · a_la_vista · ensename · no · vencida · cancelada. `confiar`: la casilla
    /// «Confío en este agente…» (solo amarillo). `ahora`: el destino como está al contestar (si cambió, no vale).
    /// Ronda 2 (H-2) · `recordar`: la casilla «No me preguntes para abrir …» (solo cuenta si la ficha la traía; en A1,
    /// `confiar` hace lo mismo: es la misma casilla de la tarjeta).
    func responder(_ tarjeta: String, _ r: String, confiar: Bool = false, recordar: Bool = false, ahora ds: [Destino]) -> Respuesta {
        guard let p = pendientes.removeValue(forKey: tarjeta) else {
            return Respuesta(salida: .negado, motivo: "Esa tarjeta ya no está (se canceló o ya la contestaste).")
        }
        let c = p.tarjeta.color
        switch r {
        case "hazlo", "a_la_vista":
            if let cambio = Huella.cambioLote(p.huellas, Huella.lote(ds, p.pedido.tipoConocido)) {
                anotar(p.pedido, p.destinos, c, salida: "tarjeta", resultado: "cancelada", motivo: cambio, tarjeta: tarjeta)
                return Respuesta(salida: .negado, color: c, motivo: "No lo hice: \(cambio) desde que te pregunté.")
            }
            if reloj().timeIntervalSince(p.desde) > p.tarjeta.vence {
                anotar(p.pedido, p.destinos, c, salida: "tarjeta", resultado: "vencida", motivo: "tarde", tarjeta: tarjeta)
                return Respuesta(salida: .negado, color: c, motivo: "La tarjeta ya había vencido.")
            }
            var conf: String? = nil
            if confiar, p.tarjeta.puedeConfiar, c == .amarillo, let d0 = p.destinos.first {
                conf = confianzas.dar(id: nuevoId(), agente: p.tarjeta.agente, destino: d0, ahora: reloj(), calendario: calendario).id
            }
            // ronda 2 (H-2), solo A1: cuenta el OK de su tipo; con la casilla, lo recuerda; al tercero, lo ofrece. Una
            // página que abriste con tu OK deja su sitio como conocido.
            var ofrecer: TipoRecordado? = nil, recordo: String? = nil
            if etapa == .amarillo {
                var cambio = false
                if c == .amarillo, let t = p.recordable {
                    let n = recordados.contar(t)
                    cambio = true
                    if (recordar || confiar), !recordados.tiene(t) {
                        recordados.dar(t, ahora: reloj())
                        recordo = t.rawValue
                    } else if n == Recordados.ofrecerA, !recordados.tiene(t) {
                        ofrecer = t
                    }
                }
                if p.pedido.tipoConocido == .abrir, let u = p.destinos.first?.abrirURL, Portero.esPagina(u), !recordados.conocido(u) {
                    recordados.conocer(u)
                    cambio = true
                }
                // junto5: un borrador que aprobaste deja sus direcciones como conocidas (la siguiente ya no es «nueva»)
                if p.pedido.borrador, let b = Borrador.de(p.destinos.first?.abrirURL ?? ""), recordados.conocerCorreos(b.para) { cambio = true }
                if cambio { alCambiarRecordados?() }
            }
            let a = Autorizacion(id: nuevoId(), tarjeta: tarjeta, tipo: p.pedido.tipo, huellas: p.huellas, desde: reloj())
            autorizaciones[a.id] = a
            anotar(p.pedido, p.destinos, c, salida: "tarjeta", resultado: "autorizado", motivo: r == "a_la_vista" ? "OK, a la vista" : "OK",
                   tarjeta: tarjeta, confianza: conf, recordado: recordo)
            var res = Respuesta(salida: .tarjeta, color: c, motivo: r == "a_la_vista" ? "El socio dijo que sí, a la vista." : "El socio dijo que sí.",
                                autorizacion: a.id, ensayo: etapa == .ensayo)
            res.tarjeta = p.tarjeta
            res.ofrecerRecordar = ofrecer
            return res
        case "ensename":
            anotar(p.pedido, p.destinos, c, salida: "tarjeta", resultado: "ensename", motivo: "prefirió que le enseñe", tarjeta: tarjeta)
            return Respuesta(salida: .senalar, color: c, motivo: "El socio prefiere que le enseñes dónde y lo hace él.")
        case "vencida", "cancelada":
            anotar(p.pedido, p.destinos, c, salida: "tarjeta", resultado: r, motivo: r == "vencida" ? "nadie contestó" : "cambió lo de enfrente", tarjeta: tarjeta)
            return Respuesta(salida: .negado, color: c, motivo: r == "vencida" ? "Nadie contestó la tarjeta: no lo hice." : "Lo de enfrente cambió: lo cancelé.")
        default:
            anotar(p.pedido, p.destinos, c, salida: "tarjeta", resultado: "no", motivo: "dijo que no", tarjeta: tarjeta)
            return Respuesta(salida: .negado, color: c, motivo: "El socio dijo que no. No lo vuelvas a pedir en este turno si él no lo pide.")
        }
    }

    /// Justo antes de hacerlo: el OK vale UNA vez, para ESE destino y por poco tiempo. → ejecutada (o en ensayo, «se
    /// habría hecho»), o negado con el motivo.
    func ejecutar(_ autorizacion: String, ahora ds: [Destino]) -> Respuesta {
        guard var a = autorizaciones[autorizacion], !a.usada else {
            return Respuesta(salida: .negado, motivo: "Ese OK no existe o ya se usó: un OK vale para una sola acción.")
        }
        if let cambio = Huella.cambioLote(a.huellas, Huella.lote(ds, TipoAccion(rawValue: a.tipo))) {
            autorizaciones[autorizacion] = nil
            registro.append(linea(["tipo": a.tipo, "resultado": "cancelada", "motivo": cambio, "autorizacion": a.id]))
            return Respuesta(salida: .negado, motivo: "No lo hice: \(cambio) desde el OK.")
        }
        if reloj().timeIntervalSince(a.desde) > Autorizacion.vigencia {
            autorizaciones[autorizacion] = nil
            return Respuesta(salida: .negado, motivo: "El OK ya venció: te vuelvo a preguntar.")
        }
        a.usada = true
        autorizaciones[autorizacion] = nil
        ejecutadas.append((a.id, a.porConfianza != nil))
        if a.porRecordado != nil { ejecutadasCero += 1 }
        registro.append(linea(["tipo": a.tipo, "resultado": etapa == .ensayo ? "ensayo" : "hecho", "autorizacion": a.id,
                               "tarjeta": a.tarjeta, "confianza": a.porConfianza ?? "", "recordado": a.porRecordado ?? ""]))
        var r = Respuesta(salida: a.porRecordado != nil ? .cero : (a.porConfianza == nil ? .tarjeta : .confianza),
                          motivo: etapa == .ensayo ? "Ensayo: no se hizo de verdad." : "Hecho.",
                          ensayo: etapa == .ensayo)
        r.ejecutada = true
        return r
    }

    // — la bitácora —
    private func linea(_ o: [String: Any]) -> [String: Any] {
        var d = o
        d["cuando"] = ISO8601DateFormatter().string(from: reloj())
        d["turno"] = turno ?? ""
        d["agente"] = agente
        d["etapa"] = etapa.rawValue
        return d
    }

    private func anotar(_ p: PedidoAccion, _ ds: [Destino], _ c: ColorAccion, salida: String, resultado: String, motivo: String,
                        tarjeta: String? = nil, confianza: String? = nil, recordado: String? = nil) {
        let d0 = ds.first ?? Destino()
        var o: [String: Any] = ["tipo": p.tipo, "color": c.rawValue, "salida": salida, "resultado": resultado, "motivo": motivo,
                                "modo": p.modo ?? modo(de: agente).rawValue, "app": d0.app, "bundle": d0.bundle,
                                "ventana": d0.ventana ?? "", "sitio": d0.sitio ?? "",
                                "elementos": ds.map { ["rol": $0.rol ?? "", "etiqueta": $0.etiqueta ?? "",
                                                       "marco": $0.marco.map { [Int($0.minX), Int($0.minY), Int($0.width), Int($0.height)] } ?? [],
                                                       "valor_antes": BitacoraAcciones.corto($0.valor) ?? ""] as [String: Any] },
                                "leyo": lecturas.fuentes.map { $0.json() }]
        if let v = p.valor { o["valor"] = BitacoraAcciones.corto(v) ?? "" }
        if !p.campos.isEmpty { o["valores"] = p.campos.map { BitacoraAcciones.corto($0.valor) ?? "" } }
        if let r = d0.ruta { o["ruta"] = r }
        if let r = d0.rutaDestino { o["destino"] = r }
        if let u = d0.abrirURL { o["url"] = BitacoraAcciones.corto(u, 300) ?? "" }
        if let a = d0.abrirApp { o["abrir_app"] = a }
        if let c = d0.abrirCon { o["abrir_con"] = c }
        if d0.enFinder { o["en_finder"] = true }
        if d0.esCarpeta { o["carpeta"] = true }
        if let t = tarjeta { o["tarjeta"] = t }
        if let k = confianza { o["confianza"] = k }
        if let k = recordado { o["recordado"] = k }
        let g = lecturas.grado(turno: turno).grado
        if g != .nada { o["leyo_grado"] = g.rawValue }
        registro.append(linea(o))
    }
}

// MARK: JSON ↔ portero (lo usan la app, para su puerto, y el portero de línea de comandos)

enum PorteroJSON {
    static func destino(_ o: [String: Any]) -> Destino {
        var d = Destino()
        d.app = (o["app"] as? String) ?? ""
        d.bundle = (o["bundle"] as? String) ?? ""
        d.pid = (o["pid"] as? NSNumber)?.int32Value ?? 0
        d.propia = (o["propia"] as? Bool) ?? false
        d.ventana = o["ventana"] as? String
        d.ventanaId = (o["ventana_id"] as? NSNumber)?.uint32Value ?? 0
        d.url = o["url"] as? String
        d.rol = o["rol"] as? String
        d.subrol = o["subrol"] as? String
        d.etiqueta = o["etiqueta"] as? String
        d.valor = o["valor"] as? String
        if let m = o["marco"] as? [NSNumber], m.count == 4 {
            d.marco = CGRect(x: m[0].doubleValue, y: m[1].doubleValue, width: m[2].doubleValue, height: m[3].doubleValue)
        }
        d.enDialogo = (o["en_dialogo"] as? Bool) ?? false
        d.dialogo = o["dialogo"] as? String
        d.ruta = o["ruta"] as? String
        d.rutaDestino = o["ruta_destino"] as? String
        d.destinoExiste = (o["destino_existe"] as? Bool) ?? false
        d.abrirURL = o["abrir_url"] as? String
        d.abrirApp = o["abrir_app"] as? String
        d.abrirCon = o["abrir_con"] as? String
        d.navegador = (o["navegador"] as? Bool) ?? false
        d.enlace = o["enlace"] as? String
        d.abrirNombre = o["abrir_nombre"] as? String
        d.abrirAbierta = (o["abrir_abierta"] as? Bool) ?? false
        d.esCarpeta = (o["es_carpeta"] as? Bool) ?? false
        d.enFinder = (o["en_finder"] as? Bool) ?? false
        if let c = o["casa"] as? String { d.casa = c }
        return d
    }

    static func destinos(_ v: Any?) -> [Destino] { ((v as? [[String: Any]]) ?? []).map(destino) }
}
