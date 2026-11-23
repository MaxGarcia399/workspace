// Pruebas de VozLogica.swift (la voz del monito), sin XCTest y sin micrófono:
//   swiftc -parse-as-library ../Sources/MonitoEscritorio/VozLogica.swift PruebasVoz.swift -o /tmp/pv && /tmp/pv
// Imprime «ok N» y sale con 0; si algo falla, dice qué y sale con 1. Lo corre tests/test_monito_voz.py.
import Foundation

var fallos: [String] = []
var hechas = 0

func igual<T: Equatable>(_ a: T, _ b: T, _ que: String, linea: Int = #line) {
    hechas += 1
    if a != b { fallos.append("línea \(linea) · \(que): \(a) ≠ \(b)") }
}

func verdad(_ c: Bool, _ que: String, linea: Int = #line) {
    hechas += 1
    if !c { fallos.append("línea \(linea) · \(que)") }
}

func camino() {
    typealias M = VozLogica.Mac
    var r = VozLogica.camino(M(mayor: 26, analizador: ["es-MX", "es-ES", "en-US"], enLaMac: ["es-MX"]), idioma: "es-MX")
    igual(r.camino, .analizador, "macOS 26 con español: el analizador (solo Micrófono)")
    igual(r.idioma, "es-MX", "el idioma pedido")
    r = VozLogica.camino(M(mayor: 15, analizador: ["es-MX"], enLaMac: ["es_ES", "en-US"]), idioma: "es-MX")
    igual(r.camino, .clasico, "macOS 15: el de siempre, aunque alguien diga que hay analizador")
    igual(r.idioma, "es-ES", "sin el de México, otro español que sí esté en la Mac")
    r = VozLogica.camino(M(mayor: 26, analizador: ["en-US"], enLaMac: ["es-MX"]), idioma: "es-MX")
    igual(r.camino, .clasico, "macOS 26 sin español en el analizador: el de siempre, en la Mac")
    r = VozLogica.camino(M(mayor: 14, analizador: [], enLaMac: ["en-US"]), idioma: "es-MX")
    igual(r.camino, .ninguno(VozLogica.sinEspanol(mayor: 14)), "sin español en la Mac no se dicta (nunca en línea)")
    verdad(VozLogica.sinEspanol(mayor: 14).contains("no lo hago") && VozLogica.sinEspanol(mayor: 14).contains("macOS 26"), "y lo dice claro")
    verdad(!VozLogica.sinEspanol(mayor: 26).contains("macOS 26"), "a quien ya tiene macOS 26 no se le promete macOS 26")
    igual(VozLogica.idioma(preferidos: ["en-US", "es_ES"]), "es-ES", "el español de tu Mac")
    igual(VozLogica.idioma(preferidos: ["en-US", "fr-FR"]), "es-MX", "sin español entre tus idiomas: México")
    igual(VozLogica.idioma(preferidos: ["es-419", "es"]), "es-MX", "un español sin país que sirva: México")
}

func permisos() {
    typealias V = VozLogica
    igual(V.paso(.analizador, microfono: .sinDecidir, reconocimiento: .sinDecidir), .avisar(V.fraseMicrofono),
          "la primera vez: la frase, antes del aviso de macOS")
    verdad(V.fraseMicrofono.contains("no sale de tu Mac") && !V.fraseMicrofono.contains("Reconocimiento"),
           "la frase dice lo que pasa y solo nombra el permiso que se pide")
    igual(V.paso(.analizador, microfono: .si, reconocimiento: .sinDecidir), .seguir,
          "el analizador no pide Reconocimiento de voz")
    igual(V.paso(.clasico, microfono: .sinDecidir, reconocimiento: .sinDecidir), .avisar(V.fraseClasico), "el de siempre: dos")
    verdad(V.fraseClasico.contains("dos permisos"), "y lo dice")
    igual(V.paso(.clasico, microfono: .si, reconocimiento: .sinDecidir), .avisar(V.fraseClasico), "falta el segundo")
    igual(V.paso(.clasico, microfono: .si, reconocimiento: .si), .seguir, "con los dos")
    igual(V.paso(.analizador, microfono: .no, reconocimiento: .si), .apagado(V.microfonoApagado), "dijiste que no: cómo se prende")
    igual(V.paso(.clasico, microfono: .si, reconocimiento: .no), .apagado(V.reconocimientoApagado), "el otro apagado")
}

func caja() {
    igual(VozLogica.unir("", " hola mundo "), "hola mundo", "caja vacía")
    igual(VozLogica.unir("Oye,", "ábreme el Excel"), "Oye, ábreme el Excel", "con su espacio")
    igual(VozLogica.unir("Oye, ", "ábreme"), "Oye, ábreme", "sin doble espacio")
    igual(VozLogica.unir("lo mío", "  "), "lo mío", "sin dictado, lo tuyo queda igual")
}

func atajo() {
    typealias A = VozLogica.Accion
    var p = VozLogica.Pulsacion()
    igual(p.baja(barraAbierta: false, enVuelo: false), [A.alternar, A.armarReloj], "un toque con la barra cerrada la abre al apretar")
    igual(p.baja(barraAbierta: true, enVuelo: false), [], "la tecla repetida no cuenta")
    igual(p.sube(), [], "…y soltar no la vuelve a cerrar")
    igual(p.vence(), [], "el reloj de un toque ya suelto no dicta")

    p = VozLogica.Pulsacion()
    igual(p.baja(barraAbierta: true, enVuelo: false), [A.armarReloj], "con la barra abierta, apretar espera")
    igual(p.sube(), [A.alternar], "un toque la cierra al soltar")

    p = VozLogica.Pulsacion()
    _ = p.baja(barraAbierta: true, enVuelo: false)
    igual(p.vence(), [A.empezar], "mantenerlo: a dictar")
    igual(p.vence(), [], "una sola vez")
    igual(p.sube(), [A.parar], "soltar: deja de oír (y la barra se queda, con tu texto)")

    p = VozLogica.Pulsacion()
    igual(p.baja(barraAbierta: false, enVuelo: false), [A.alternar, A.armarReloj], "mantener con la barra cerrada: se abre…")
    igual(p.vence(), [A.empezar], "…y dicta")
    igual(p.sube(), [A.parar], "y al soltar no se cierra")

    // macOS nunca avisó que la soltaste: el atajo no se queda atorado ni el micrófono prendido
    p = VozLogica.Pulsacion()
    _ = p.baja(barraAbierta: true, enVuelo: false)
    _ = p.vence()
    igual(p.baja(barraAbierta: true, enVuelo: false, desdeLaAnterior: 0.05), [], "mantenida (se repite): sigue dictando")
    igual(p.baja(barraAbierta: true, enVuelo: false, desdeLaAnterior: 4), [A.parar], "otra pulsación de verdad: deja de oír")
    igual(p.baja(barraAbierta: true, enVuelo: false, desdeLaAnterior: 3), [A.armarReloj], "y la que sigue ya es normal")
    p = VozLogica.Pulsacion()
    _ = p.baja(barraAbierta: false, enVuelo: false)
    igual(p.baja(barraAbierta: true, enVuelo: false, desdeLaAnterior: 5), [A.armarReloj], "sin dictar y sin aviso de soltar: empieza de nuevo")
    igual(p.sube(), [A.alternar], "y el toque cierra la barra")

    p = VozLogica.Pulsacion()
    igual(p.baja(barraAbierta: true, enVuelo: true), [A.alternar], "con algo en vuelo, ⌥ Espacio sigue siendo el pánico")
    igual(p.vence(), [], "y no dicta")
    igual(p.sube(), [], "ni hace nada al soltar")
}

func leer() {
    let t = """
    ## Listo
    Abrí **el Excel** de `ventas` y vendimos $245,000. Mira [el reporte](https://ejemplo.mx/r?a=1).
    ```
    print("no se lee")
    ```
    - Uno
    - Dos

    📄 /Users/x/deliverables/a/A_v1.pdf
      1 — abrir el archivo        2 — revelar en Finder        3 — seguir con la conversación
    🧠 check ✓ — nada nuevo
    """
    let l = VozLogica.paraLeer(t)
    verdad(l.hasPrefix("Listo\nAbrí el Excel de ventas y vendimos $245,000. Mira el reporte."), "sin signos de formato: \(l)")
    verdad(!l.contains("print") && !l.contains("https") && !l.contains("🧠") && !l.contains("revelar") && !l.contains("deliverables"),
           "sin código, ligas, el bloque del final ni el menú de archivo: \(l)")
    verdad(l.hasSuffix("Uno\nDos"), "las viñetas, sin su guion: \(l)")
    let largo = String(repeating: "Una frase completa. ", count: 200)
    let c = VozLogica.paraLeer(largo, tope: 300)
    verdad(c.count <= 300 && c.hasSuffix("."), "lo largo se corta en un punto")
    igual(VozLogica.respuesta(#"{"t":"respuesta","agente":"luna","texto":"Hola"}"#), "Hola", "la respuesta final")
    verdad(VozLogica.respuesta(#"{"t":"parcial","texto":"la respuesta va"}"#) == nil, "un trozo a medias no se lee")
    verdad(VozLogica.respuesta(#"{"t":"respuesta","texto":""}"#) == nil && VozLogica.respuesta("basura \"respuesta\"") == nil, "nada o basura, nada")
}

func pintar() {
    let silencio = [Float](repeating: 0, count: 256)
    let voz = (0..<256).map { Float(sin(Double($0) / 4)) * 0.2 }
    igual(silencio.withUnsafeBufferPointer { VozLogica.nivel($0) }, 0, "silencio")
    let n = voz.withUnsafeBufferPointer { VozLogica.nivel($0) }
    verdad(n > 0.6 && n <= 1, "voz: \(n)")
    let js = VozLogica.js("dictado", ["firme": "dijo \"hola\"); alert(1)//", "volatil": ""])
    verdad(js.hasPrefix("typeof WSMVoz!=='undefined'&&WSMVoz.dictado({") && js.contains(#"\"hola\""#), "el texto viaja como JSON, no como código: \(js)")
    verdad(VozLogica.tope == 120 && VozLogica.mantener > 0.2 && VozLogica.mantener < 0.6, "el tope del micrófono y lo que es mantener")
}

/// M-4 · soltar ⌥ Espacio SIEMPRE cierra el micrófono, llegue cuando llegue; y el aviso de la Mac no cancela el dictado.
func m4() {
    // «parar» según en qué va el arranque
    igual(VozLogica.alParar(fase: "oyendo", arrancando: false), .terminar, "oyendo: termina")
    igual(VozLogica.alParar(fase: "preparando", arrancando: true), .recordar, "preparando: se recuerda y termina al empezar")
    igual(VozLogica.alParar(fase: "reposo", arrancando: true), .recordar, "soltaste antes de que empezara siquiera a preparar: TAMBIÉN se recuerda (antes se perdía y el micrófono quedaba abierto)")
    igual(VozLogica.alParar(fase: "reposo", arrancando: false), .nada, "en reposo de verdad: nada que parar")
    igual(VozLogica.alParar(fase: "aviso", arrancando: false), .nada, "con la frase de la primera vez a la vista: nada está oyendo")
    igual(VozLogica.alParar(fase: "apagado", arrancando: false), .nada, "apagado")
    igual(VozLogica.alParar(fase: "escribiendo", arrancando: false), .nada, "ya está terminando")
    // todas las combinaciones del atajo: mantener y soltar en cualquier momento acaba con «parar» recordado o hecho
    for cuando in ["reposo", "preparando", "oyendo"] {
        var p = VozLogica.Pulsacion()
        _ = p.baja(barraAbierta: true, enVuelo: false)
        igual(p.vence(), [.empezar], "mantener: empieza")
        igual(p.sube(), [.parar], "soltar manda «parar»")
        verdad(VozLogica.alParar(fase: cuando, arrancando: cuando != "oyendo") != .nada, "y «parar» no se pierde si el arranque va en «\(cuando)»")
    }
    // el aviso de permiso de la Mac le quita el foco a la barra: ese «cancelar» no es tuyo
    verdad(!VozLogica.atiendeCancelar("voz_cancelar", pidiendoPermiso: true), "mientras la Mac pregunta, el cierre de la barra no cancela")
    verdad(VozLogica.atiendeCancelar("voz_cancelar", pidiendoPermiso: false), "fuera de eso, cerrar la barra sí apaga el micrófono")
    verdad(VozLogica.atiendeCancelar("voz_no", pidiendoPermiso: true), "«Ahora no» es tuyo: siempre cuenta")
}

@main
enum Pruebas {
    static func main() {
        camino(); permisos(); caja(); atajo(); leer(); pintar(); m4()
        if fallos.isEmpty { print("ok \(hechas)"); exit(0) }
        fallos.forEach { print("✗ " + $0) }
        exit(1)
    }
}
