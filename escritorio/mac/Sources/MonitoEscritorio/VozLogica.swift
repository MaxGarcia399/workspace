// WORKSPACE · la voz del monito, lo que se puede probar suelto (sin micrófono, sin AppKit): escritorio/mac/Pruebas/PruebasVoz.swift.
//
// V1-a · dictado: hablas, se vuelve texto en la caja y TÚ lo mandas. Nunca se manda solo.
// V2 · quién transcribe: lo nativo de la Mac, en tu Mac (NOTA_VOZ.md trae los números). Nada se instala ni se baja con
//      Workspace; ningún audio sale. Si esta Mac no puede transcribir sin mandar audio fuera, se dice y no se dicta.
// V3-b · «Léeme las respuestas», con la voz de la Mac, apagado de fábrica.
// V4-b · el micrófono de la caja, y MANTENER ⌥ Espacio para hablar (un toque sigue abriendo y cerrando la barra).
import Foundation

enum VozLogica {
    /// Nunca se deja el micrófono abierto más de esto (lo mismo que voice.py).
    static let tope: TimeInterval = 120
    /// Cuánto hay que mantener ⌥ Espacio para que sea «hablar» y no un toque.
    static let mantener: TimeInterval = 0.35
    /// Con la barra cerrada, el micrófono se apaga (por si la burbuja no alcanzó a avisar).
    static let graciaSinBarra: TimeInterval = 1.0

    // MARK: quién transcribe
    /// El camino de esta Mac. `analizador`: macOS 26 o más nuevo (solo pide Micrófono). `clasico`: macOS 14 y 15, solo
    /// si la Mac trae el español para transcribir aquí mismo (pide Micrófono y Reconocimiento de voz). `ninguno`: no
    /// se dicta; jamás se cae a un servicio en línea.
    enum Camino: Equatable {
        case analizador
        case clasico
        case ninguno(String)

        var nombre: String {
            switch self {
            case .analizador: return "analizador"
            case .clasico: return "clasico"
            case .ninguno: return "ninguno"
            }
        }
    }

    /// Lo que la Mac dice de sí misma (lo llena Voz.swift; aquí solo se decide).
    struct Mac: Equatable {
        /// La versión mayor de macOS (14, 15, 26…).
        var mayor = 14
        /// macOS 26+: los idiomas con que su analizador transcribe.
        var analizador: [String] = []
        /// macOS 14/15: los idiomas que el reconocedor de siempre transcribe EN la Mac (supportsOnDeviceRecognition).
        var enLaMac: [String] = []
    }

    /// Sin español en la Mac: se dice y no se dicta. Solo se promete macOS 26 a quien no lo tiene.
    static func sinEspanol(mayor: Int) -> String {
        "Esta Mac no puede dictar en español sin mandar tu voz fuera, y eso no lo hago."
            + (mayor < 26 ? " Con macOS 26 o más nuevo sí puede, sin instalar nada." : "")
    }

    /// El idioma de dictado: el de tu Mac si es español; si no, el español de México.
    static func idioma(preferidos: [String]) -> String {
        for p in preferidos {
            let n = p.replacingOccurrences(of: "_", with: "-")
            let partes = n.split(separator: "-")
            if partes.count >= 2, partes[0].lowercased() == "es", partes[1].count == 2, partes[1].allSatisfy({ $0.isLetter }) {
                return "es-" + partes[1].uppercased()
            }
        }
        return "es-MX"
    }

    /// De los idiomas que hay, el pedido; si no, otro español (primero México y España).
    static func elegir(_ pedido: String, de hay: [String]) -> String? {
        let h = hay.map { $0.replacingOccurrences(of: "_", with: "-") }
        if h.contains(pedido) { return pedido }
        for otro in ["es-MX", "es-ES", "es-US"] where h.contains(otro) { return otro }
        return h.first { $0.lowercased().hasPrefix("es-") }
    }

    static func camino(_ m: Mac, idioma: String) -> (camino: Camino, idioma: String) {
        if m.mayor >= 26, let i = elegir(idioma, de: m.analizador) { return (.analizador, i) }
        if let i = elegir(idioma, de: m.enLaMac) { return (.clasico, i) }
        return (.ninguno(sinEspanol(mayor: m.mayor)), idioma)
    }

    // MARK: los permisos, con su frase honesta
    enum Dado: Equatable { case sinDecidir, si, no }

    enum Paso: Equatable {
        /// La frase, ANTES del aviso de macOS (solo la primera vez que tocas el micrófono).
        case avisar(String)
        /// Dijiste que no en macOS: cómo se prende (con un botón a Ajustes; nunca se abre solo).
        case apagado(String)
        case seguir
    }

    static let fraseMicrofono = "Para dictar uso el micrófono de tu Mac. Tu voz se vuelve texto aquí mismo y no sale de tu Mac. Ahora la Mac te va a pedir permiso."
    static let fraseClasico = "Para dictar uso el micrófono de tu Mac. Tu voz se vuelve texto aquí mismo y no sale de tu Mac. Ahora la Mac te va a pedir dos permisos: Micrófono y Reconocimiento de voz."
    static let microfonoApagado = "El micrófono está apagado para Workspace Compañero. Se prende en Ajustes › Privacidad y seguridad › Micrófono."
    static let reconocimientoApagado = "El Reconocimiento de voz está apagado para Workspace Compañero. Se prende en Ajustes › Privacidad y seguridad › Reconocimiento de voz."

    /// Qué toca al tocar el micrófono. `reconocimiento` solo cuenta en el camino clásico.
    static func paso(_ c: Camino, microfono: Dado, reconocimiento: Dado) -> Paso {
        if microfono == .no { return .apagado(microfonoApagado) }
        if c == .clasico, reconocimiento == .no { return .apagado(reconocimientoApagado) }
        if microfono == .sinDecidir { return .avisar(c == .clasico ? fraseClasico : fraseMicrofono) }
        if c == .clasico, reconocimiento == .sinDecidir { return .avisar(fraseClasico) }
        return .seguir
    }

    // MARK: el texto en la caja
    /// Lo que ya habías escrito + lo dictado: con un espacio si hace falta, sin tocar lo tuyo.
    static func unir(_ base: String, _ dictado: String) -> String {
        let d = dictado.trimmingCharacters(in: .whitespacesAndNewlines)
        if d.isEmpty { return base }
        if base.isEmpty { return d }
        if let u = base.last, u == " " || u == "\n" { return base + d }
        return base + " " + d
    }

    // MARK: ⌥ Espacio: un toque o mantener
    enum Accion: Equatable {
        /// Lo de siempre (abre o cierra la barra; si algo está en vuelo, lo para todo).
        case alternar
        case armarReloj
        case empezar
        case parar
    }

    /// Un toque abre la barra al APRETAR (como siempre) y la cierra al SOLTAR; si lo mantienes, dictas hasta soltar.
    struct Pulsacion: Equatable {
        var abajo = false
        var abrio = false
        var dictando = false

        /// `desdeLaAnterior`: segundos desde el aviso anterior de «apretada» (la tecla mantenida puede repetirlo).
        /// Si macOS nunca avisó que la soltaste, la siguiente pulsación de verdad (más de un segundo después) termina
        /// el dictado o vuelve a empezar: el atajo nunca se queda atorado ni el micrófono prendido.
        mutating func baja(barraAbierta: Bool, enVuelo: Bool, desdeLaAnterior: TimeInterval = 0) -> [Accion] {
            if abajo {
                if desdeLaAnterior < 1 { return [] }            // la tecla repetida
                abajo = false
                if dictando { dictando = false; return [.parar] }
            }
            if enVuelo { return [.alternar] }                   // pánico: para todo, y nada de voz
            abajo = true
            dictando = false
            abrio = !barraAbierta
            return (abrio ? [.alternar] : []) + [.armarReloj]
        }

        /// Pasó `mantener` y la tecla sigue abajo.
        mutating func vence() -> [Accion] {
            guard abajo, !dictando else { return [] }
            dictando = true
            return [.empezar]
        }

        mutating func sube() -> [Accion] {
            guard abajo else { return [] }
            abajo = false
            if dictando { dictando = false; return [.parar] }
            return abrio ? [] : [.alternar]                     // la barra ya estaba: el toque la cierra
        }
    }

    // MARK: M-4 · que el micrófono nunca quede abierto, y que el aviso de la Mac no cancele
    enum AlParar: Equatable { case terminar, recordar, nada }

    /// Llegó «parar» (soltaste ⌥ Espacio, o un toque): si ya oye, termina; si TODAVÍA está arrancando (aún en reposo
    /// leyendo qué puede la Mac, o preparando), se recuerda y termina en cuanto empiece. Antes solo se recordaba en
    /// «preparando»: soltar muy rápido dejaba el micrófono abierto hasta su tope.
    static func alParar(fase: String, arrancando: Bool) -> AlParar {
        if fase == "oyendo" { return .terminar }
        if fase == "preparando" || (fase == "reposo" && arrancando) { return .recordar }
        return .nada
    }

    /// El aviso de permiso de la Mac le quita el foco a la barra, la barra se cierra y la burbuja manda «voz_cancelar»:
    /// ese cierre no es del socio. Mientras la Mac pregunta, no cancela (al dar permiso, empieza a oír). «Ahora no»
    /// (voz_no) sí es suyo.
    static func atiendeCancelar(_ op: String, pidiendoPermiso: Bool) -> Bool {
        !(op == "voz_cancelar" && pidiendoPermiso)
    }

    // MARK: «Léeme las respuestas»
    /// Lo que se lee de una respuesta: sin el bloque del final (🧠, el menú de archivo), sin código, sin ligas ni
    /// signos de formato; y no más de `tope` letras (lo demás lo lees tú).
    static func paraLeer(_ texto: String, tope: Int = 1200) -> String {
        var lineas: [String] = []
        var enCodigo = false
        for cruda in texto.components(separatedBy: "\n") {
            let l = cruda.trimmingCharacters(in: .whitespaces)
            if l.hasPrefix("```") { enCodigo.toggle(); continue }
            if enCodigo { continue }
            if l.hasPrefix("🧠") || l.hasPrefix("📄") { continue }
            if l.range(of: #"^\d — .*\d — "#, options: .regularExpression) != nil { continue }      // el menú de archivo
            if l.hasPrefix("|") || l.range(of: #"^[-=*_]{3,}$"#, options: .regularExpression) != nil { continue }
            lineas.append(l)
        }
        var t = lineas.joined(separator: "\n")
        for (patron, por) in [(#"!?\[([^\]]*)\]\([^)]*\)"#, "$1"), (#"https?://\S+"#, ""), (#"`([^`]*)`"#, "$1"),
                              (#"(\*\*|__|\*|~~)"#, ""), (#"(?m)^#{1,6}\s*"#, ""), (#"(?m)^[-•]\s+"#, ""),
                              (#"(?m)^>\s*"#, ""), (#"\n{2,}"#, "\n"), (#"[ \t]{2,}"#, " ")] {
            t = t.replacingOccurrences(of: patron, with: por, options: .regularExpression)
        }
        t = t.trimmingCharacters(in: .whitespacesAndNewlines)
        if t.count <= tope { return t }
        let corte = String(t.prefix(tope))
        if let fin = corte.lastIndex(where: { ".!?\n".contains($0) }), corte.distance(from: corte.startIndex, to: fin) > tope / 2 {
            return String(corte[...fin]).trimmingCharacters(in: .whitespacesAndNewlines)
        }
        return corte
    }

    /// La respuesta final de un turno (una línea del puente: {"t":"respuesta","texto":…}) → su texto, o nil.
    static func respuesta(_ linea: String) -> String? {
        guard linea.contains("\"respuesta\""), let d = linea.data(using: .utf8),
              let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any], (o["t"] as? String) == "respuesta",
              let t = o["texto"] as? String, !t.isEmpty else { return nil }
        return t
    }

    // MARK: lo que la burbuja pinta
    /// El nivel del micrófono (0…1) de un trozo de audio, para la onda del nido.
    static func nivel(_ muestras: UnsafeBufferPointer<Float>) -> Double {
        if muestras.isEmpty { return 0 }
        var suma: Float = 0
        for m in muestras { suma += m * m }
        let rms = (suma / Float(muestras.count)).squareRoot()
        if rms <= 0.000_01 { return 0 }
        let db = 20 * log10(Double(rms))                        // −50 dB (silencio) … −10 dB (voz fuerte)
        return min(1, max(0, (db + 50) / 40))
    }

    /// WSMVoz.<fn>(<json>), sin interpretar nada del texto dictado.
    static func js(_ fn: String, _ o: [String: Any]) -> String {
        let j = (try? JSONSerialization.data(withJSONObject: o, options: [.sortedKeys])).flatMap { String(data: $0, encoding: .utf8) } ?? "{}"
        return "typeof WSMVoz!=='undefined'&&WSMVoz.\(fn)(\(j))"
    }
}
