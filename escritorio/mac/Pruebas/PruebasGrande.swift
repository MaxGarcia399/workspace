// Pruebas de LogicaGrande.swift (ronda 2 · bloque G · la ventana del chat grande), sin XCTest:
//   swiftc -parse-as-library ../Sources/MonitoEscritorio/LogicaGrande.swift PruebasGrande.swift -o /tmp/pg && /tmp/pg
// Imprime «ok N» y sale con 0; si algo falla, dice qué y sale con 1. Lo corre tests/test_monito_chat.py.
import CoreGraphics
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

let pantalla = CGRect(x: 0, y: 0, width: 1470, height: 920)
let segunda = CGRect(x: 1470, y: 0, width: 1920, height: 1080)

func lugar() {
    let f = LugarGrande.deFabrica(visible: pantalla)
    igual(f.size, CGSize(width: 980, height: 660), "la primera vez, como el boceto")
    igual(f.midX, pantalla.midX, "centrada")
    verdad(pantalla.contains(f), "dentro de lo visible")
    let chica = LugarGrande.deFabrica(visible: CGRect(x: 0, y: 0, width: 800, height: 500))
    verdad(chica.width <= 720 && chica.height <= 420 + 0.5, "en una pantalla chica, se ajusta")
    verdad(chica.width >= LugarGrande.minimo.width && chica.height >= LugarGrande.minimo.height, "nunca menos que lo mínimo")

    let guardado = CGRect(x: 200, y: 120, width: 1100, height: 700)
    igual(LugarGrande.valido(guardado, visibles: [pantalla]), guardado, "donde la dejaste, tal cual")
    verdad(LugarGrande.valido(nil, visibles: [pantalla]) == nil, "sin nada guardado, nada")
    verdad(LugarGrande.valido(guardado, visibles: []) == nil, "sin pantallas, nada")
    // estaba en la segunda pantalla y ya no está conectada: no se queda perdida
    let enLaOtra = CGRect(x: 1700, y: 200, width: 1000, height: 700)
    igual(LugarGrande.valido(enLaOtra, visibles: [pantalla, segunda]), enLaOtra, "en la segunda pantalla, se queda")
    verdad(LugarGrande.valido(enLaOtra, visibles: [pantalla]) == nil, "sin la segunda pantalla, vuelve al centro")
    // su encabezado (arriba) tiene que verse: con solo la parte de abajo a la vista no se puede tomar
    let muyArriba = CGRect(x: 200, y: 700, width: 900, height: 600)
    verdad(LugarGrande.valido(muyArriba, visibles: [pantalla]) == nil, "con el encabezado fuera de la pantalla, vuelve al centro")
    let asomada = CGRect(x: 1300, y: 100, width: 900, height: 600)
    igual(LugarGrande.valido(asomada, visibles: [pantalla]), asomada, "asomada por un lado pero con de dónde tomarla, se queda")
    // tamaños imposibles: se llevan a lo razonable, sin mover su borde de arriba
    let enana = LugarGrande.valido(CGRect(x: 300, y: 300, width: 100, height: 80), visibles: [pantalla])
    igual(enana?.size, LugarGrande.minimo, "nunca más chica que lo mínimo")
    igual(enana?.maxY, 380, "su borde de arriba no se mueve")
    let enorme = LugarGrande.valido(CGRect(x: 0, y: 0, width: 5000, height: 920), visibles: [pantalla])
    igual(enorme?.width, 1470, "nunca más ancha que la pantalla")
    verdad(LugarGrande.valido(CGRect(x: CGFloat.nan, y: 0, width: 900, height: 600), visibles: [pantalla]) == nil, "números rotos, nada")
}

func archivo() {
    igual(LugarGrande.leer(nil, firma: "a").modo, "chico", "sin archivo: chico")
    verdad(LugarGrande.leer(nil, firma: "a").marco == nil, "sin archivo: sin marco")
    let g = LugarGrande.guardar(modo: "grande", marco: CGRect(x: 10.4, y: 20.6, width: 900, height: 600), firma: "a", en: nil)
    let l = LugarGrande.leer(g, firma: "a")
    igual(l.modo, "grande", "recuerda que lo dejaste en grande")
    igual(l.marco, CGRect(x: 10, y: 21, width: 900, height: 600), "recuerda dónde y de qué tamaño")
    verdad(LugarGrande.leer(g, firma: "b").marco == nil, "otro arreglo de pantallas: su propio lugar")
    igual(LugarGrande.leer(g, firma: "b").modo, "grande", "…pero el modo es el mismo")
    // otro arreglo se suma sin borrar el primero; y chico se guarda sin perder el marco
    let g2 = LugarGrande.guardar(modo: "chico", marco: CGRect(x: 1, y: 2, width: 700, height: 500), firma: "b", en: g)
    igual(LugarGrande.leer(g2, firma: "a").marco, CGRect(x: 10, y: 21, width: 900, height: 600), "el de antes sigue")
    igual(LugarGrande.leer(g2, firma: "b").marco, CGRect(x: 1, y: 2, width: 700, height: 500), "y el nuevo")
    igual(LugarGrande.leer(g2, firma: "a").modo, "chico", "lo dejaste en chico")
    let g3 = LugarGrande.guardar(modo: "grande", marco: nil, firma: "a", en: g2)
    igual(LugarGrande.leer(g3, firma: "a").marco, CGRect(x: 10, y: 21, width: 900, height: 600), "sin marco nuevo, se queda el guardado")
    igual(LugarGrande.leer(["modo": "raro", "marcos": ["a": [1, 2, "x", 4]]], firma: "a").modo, "chico", "un modo raro es chico")
    verdad(LugarGrande.leer(["modo": "grande", "marcos": ["a": [1, 2, "x", 4]]], firma: "a").marco == nil, "un marco roto, nada")
    verdad(LugarGrande.leer(["marcos": "basura"], firma: "a").marco == nil, "basura, nada")
    // no crece sin fin
    var muchos: [String: Any] = [:]
    for i in 0..<20 { muchos = LugarGrande.guardar(modo: "grande", marco: CGRect(x: 0, y: 0, width: 700, height: 500), firma: "p\(i)", en: muchos) }
    verdad(((muchos["marcos"] as? [String: Any])?.count ?? 99) <= 12, "a lo más 12 arreglos de pantallas")
    verdad(LugarGrande.leer(muchos, firma: "p19").marco != nil, "el de ahora nunca se tira")
    verdad(JSONSerialization.isValidJSONObject(muchos), "se puede guardar como JSON")
}

func pedidos() {
    // lo de la ventana misma
    for k in ["listo", "grande", "grande_asa", "grande_estado", "zonas_arrastre", "guion_log", "guion_foto"] {
        igual(OpsGrande.destino(k), .ventana, "«\(k)» es de la ventana")
    }
    // lo que en la ventana no viene al caso: nunca llega a la app (no abre la barra, no mueve el nido, no actúa)
    for k in ["zonas", "barra", "llamar", "arrastrar", "mudanza", "medir", "volver", "manos_listo", "manos_permiso",
              "actuar_modo", "actuar_deshacer", ""] {
        igual(OpsGrande.destino(k), .nada, "«\(k)» no llega a nadie")
    }
    // lo mismo que pide la burbuja: por el mismo camino
    for k in ["mandar", "responder", "permiso", "elegir", "historial", "entregas", "entrega", "entrega_abrir", "entrega_vista",
              "copiar_texto", "adjuntar", "seguir", "encargo_decidir", "abrir_enlace", "terminal"] {
        igual(OpsGrande.destino(k), .app, "«\(k)» va por el camino de la burbuja")
    }
}

/// El Compañero de mentira: lo que la app hace con cada paso (Monito.gesto), sin ventanas.
struct Simulado: Equatable {
    var grande = false
    var chico = false
    var modo = "chico"
    var abierto: Bool { grande || chico }
    mutating func hacer(_ g: Compa.Gesto) {
        switch Compa.paso(g, grandeVisible: grande, barraAbierta: chico, modo: modo) {
        case .guardar:
            modo = Compa.modoAlGuardar(grandeVisible: grande, barraAbierta: chico, modo: modo)
            grande = false
            chico = false
        case .abrir(let como):
            modo = como
            grande = como == "grande"
            chico = como != "grande"
        case .nada:
            break
        }
    }
}

/// Un solo modelo: «abierto» (chico o grande) o «guardado». Todo lo que guarda esconde TODO; llamarlo lo regresa igual.
func compa() {
    let guardan: [Compa.Gesto] = [.atajo, .clicMonito, .menu, .minimizar, .esc, .cerrarVentana]
    let llaman: [Compa.Gesto] = [.atajo, .clicMonito, .menu]
    igual(Set(guardan + [.agrandar, .achicar]).count, Compa.Gesto.allCases.count, "cada gesto tiene su prueba")
    let enGrande = Simulado(grande: true, chico: false, modo: "grande")
    let enChico = Simulado(grande: false, chico: true, modo: "chico")
    // lo que soltaste en el monito con el grande abierto: las dos cosas a la vista
    let enLosDos = Simulado(grande: true, chico: true, modo: "grande")
    for g in guardan {
        for (antes, nombre) in [(enGrande, "en grande"), (enChico, "en chico"), (enLosDos, "con los dos")] {
            var s = antes
            s.hacer(g)
            verdad(!s.grande && !s.chico, "\(g) \(nombre): se guarda TODO (ni la ventana grande ni la burbuja se quedan)")
            igual(s.modo, antes.grande ? "grande" : "chico", "\(g) \(nombre): recuerda cómo estaba")
        }
    }
    // el bug del 23-nov: con el grande a la vista, ⌥ Espacio lo pasaba a chico (nunca se guardaba)
    igual(Compa.paso(.atajo, grandeVisible: true, barraAbierta: false, modo: "grande"), .guardar, "⌥ Espacio en grande: guardar, no «a chico»")
    igual(Compa.paso(.atajo, grandeVisible: false, barraAbierta: true, modo: "chico"), .guardar, "⌥ Espacio en chico: guardar, no «a grande»")
    // llamarlo otra vez trae lo MISMO que estaba abierto
    for g in guardan {
        for l in llaman {
            for antes in [enGrande, enChico] {
                var s = antes
                s.hacer(g)
                s.hacer(l)
                igual(s, antes, "\(g) y luego \(l): vuelve igual (\(antes.modo))")
            }
        }
    }
    // el MISMO comando dos veces: se guarda y regresa
    for l in llaman {
        for antes in [enGrande, enChico] {
            var s = antes
            s.hacer(l)
            verdad(!s.abierto, "\(l): a la primera se guarda")
            s.hacer(l)
            igual(s, antes, "\(l): a la segunda vuelve")
            s.hacer(l)
            verdad(!s.abierto, "\(l): y a la tercera se guarda otra vez")
        }
    }
    // guardado: «─», Esc y cerrar la ventana no abren nada; llamarlo sin modo abre el chico
    for g in [Compa.Gesto.minimizar, .esc, .cerrarVentana] {
        igual(Compa.paso(g, grandeVisible: false, barraAbierta: false, modo: "grande"), .nada, "\(g) ya guardado: nada")
    }
    igual(Compa.paso(.atajo, grandeVisible: false, barraAbierta: false, modo: ""), .abrir("chico"), "sin modo: el chico de siempre")
    igual(Compa.paso(.clicMonito, grandeVisible: false, barraAbierta: false, modo: "grande"), .abrir("grande"), "lo dejaste en grande: vuelve en grande")
    // ⤢ y ⤡ cambian el tamaño y NUNCA guardan (son otro control)
    var s = enChico
    s.hacer(.agrandar)
    igual(s, enGrande, "⤢: de chico a grande")
    s.hacer(.achicar)
    igual(s, enChico, "⤡: de grande a chico")
    for g in [Compa.Gesto.agrandar, .achicar] {
        for antes in [enGrande, enChico, Simulado()] {
            var t = antes
            t.hacer(g)
            verdad(t.abierto, "\(g) nunca lo guarda")
        }
    }
    verdad(Compa.abierto(grandeVisible: true, barraAbierta: false) && Compa.abierto(grandeVisible: false, barraAbierta: true)
           && !Compa.abierto(grandeVisible: false, barraAbierta: false), "abierto = chico o grande")
    igual(Compa.modoAlGuardar(grandeVisible: false, barraAbierta: false, modo: "grande"), "grande", "guardar lo ya guardado no cambia cómo vuelve")
    // el renglón del menú dice lo que va a hacer
    verdad(Compa.renglonMenu(abierto: true).hasPrefix("Guardar a tu Compañero"), "abierto: el menú ofrece guardarlo")
    verdad(Compa.renglonMenu(abierto: false).hasPrefix("Llamar a tu Compañero"), "guardado: el menú ofrece llamarlo")
}

func enlaces() {
    verdad(OpsGrande.enlaceNoSeAbre("https://ejemplo.com/guia", conDatos: false, rara: nil) == nil, "una página limpia se abre")
    verdad(OpsGrande.enlaceNoSeAbre("  http://ejemplo.com  ", conDatos: false, rara: nil) == nil, "con espacios alrededor, también")
    verdad(OpsGrande.enlaceNoSeAbre("https://ejemplo.com/?q=secreto", conDatos: true, rara: nil) != nil, "con datos no se abre desde el chat")
    igual(OpsGrande.enlaceNoSeAbre("https://10.0.0.1/", conDatos: false, rara: "va a un número (IP), no a un sitio con nombre"),
          "va a un número (IP), no a un sitio con nombre", "lo que el portero ve raro, tampoco (y dice por qué)")
    for mala in ["file:///etc/passwd", "javascript:alert(1)", "mailto:a@b.c", "ftp://x.y/z", "x-apple.systempreferences:", "", "ejemplo.com"] {
        verdad(OpsGrande.enlaceNoSeAbre(mala, conDatos: false, rara: nil) != nil, "«\(mala)» no es una página: no se abre")
    }
    verdad(OpsGrande.enlaceNoSeAbre("https://ejemplo.com/" + String(repeating: "a", count: 2100), conDatos: false, rara: nil) != nil, "muy larga, no")
    verdad(OpsGrande.enlaceNoSeAbre("https://ejemplo.com/a\u{0}b", conDatos: false, rara: nil) != nil, "con letras invisibles, no")
}

/// junto5 · lo de las fichas y la voz que pide la ventana llega a la app (el clic que vale: m3).
func clicFicha() {
    // lo de las fichas y la voz que pide la ventana llega a la app (no se pierde ni se queda en la ventana)
    for op in ["ficha_tocar", "ficha_ver", "voz_hola", "voz_tocar", "voz_seguir", "voz_no", "voz_cancelar", "voz_ajustes"] {
        igual(OpsGrande.destino(op), .app, "\(op) va a la app")
    }
}

/// M-3 · las dos ventanas de la app solo cargan SU página; y el clic de persona se ata al botón y se gasta.
func m3() {
    let propia = URL(fileURLWithPath: "/Apps/Workspace Compañero/web/monito.html")
    verdad(Navegacion.permitida(propia, propia: propia, marcoPrincipal: true), "su propia página: sí (la carga y la recarga)")
    verdad(Navegacion.permitida(URL(string: propia.absoluteString + "#algo"), propia: propia, marcoPrincipal: true), "con un ancla: es la misma")
    for (u, que) in [("https://example.org/", "una página de internet (un enlace soltado encima)"), ("http://127.0.0.1:8765/", "una página local"),
                     ("file:///Apps/Workspace%20Compa%C3%B1ero/web/otra.html", "otro archivo de su carpeta"), ("file:///etc/passwd", "un archivo cualquiera"),
                     ("file:///Apps/Workspace%20Compa%C3%B1ero/web/monito.html/../otra.html", "saliéndose con «..»"),
                     ("javascript:alert(1)", "javascript:"), ("data:text/html,<script>1</script>", "data:"), ("about:blank", "about:blank en la ventana"),
                     ("blob:null/abc", "blob:"), ("mailto:a@b.io", "mailto:"), ("x-apple.systempreferences:x", "Ajustes")] {
        verdad(!Navegacion.permitida(URL(string: u), propia: propia, marcoPrincipal: true), "no navega a: \(que)")
    }
    verdad(!Navegacion.permitida(nil, propia: propia, marcoPrincipal: true), "sin dirección: no")
    verdad(!Navegacion.permitida(propia, propia: propia, marcoPrincipal: false), "ni su propia página dentro de un marco")
    verdad(!Navegacion.permitida(URL(string: "https://example.org/"), propia: propia, marcoPrincipal: false), "un marco con otra página: no")
    // el canal con la app: solo de su página, en el marco principal
    verdad(Navegacion.delCanal(propia, propia: propia, marcoPrincipal: true), "su página: se le oye")
    verdad(!Navegacion.delCanal(URL(string: "https://example.org/"), propia: propia, marcoPrincipal: true), "otra página: no se le oye")
    verdad(!Navegacion.delCanal(propia, propia: propia, marcoPrincipal: false), "un marco: no se le oye")
    verdad(!Navegacion.delCanal(nil, propia: propia, marcoPrincipal: true), "sin origen: no")

    // el clic: en ESE botón (su marco en la página), reciente, y vale UNA vez
    let t = Date(timeIntervalSince1970: 1_800_000_000)
    let boton = CGRect(x: 700, y: 180, width: 90, height: 36)
    let enBoton = ClicReal(cuando: t.addingTimeInterval(-0.1), punto: CGPoint(x: 740, y: 200))
    verdad(ClicFicha.vale(enBoton, en: boton, ahora: t), "un clic tuyo SOBRE su botón, hace un instante")
    verdad(!ClicFicha.vale(ClicReal(cuando: t.addingTimeInterval(-0.1), punto: CGPoint(x: 300, y: 400)), en: boton, ahora: t), "un clic en otra parte de la ventana: no")
    verdad(!ClicFicha.vale(ClicReal(cuando: t.addingTimeInterval(-0.7), punto: CGPoint(x: 740, y: 200)), en: boton, ahora: t), "un clic viejo: no")
    verdad(!ClicFicha.vale(ClicReal(cuando: t.addingTimeInterval(3), punto: CGPoint(x: 740, y: 200)), en: boton, ahora: t), "ni «del futuro»")
    verdad(!ClicFicha.vale(nil, en: boton, ahora: t), "sin clic: no")
    verdad(!ClicFicha.vale(enBoton, en: nil, ahora: t), "sin decir cuál botón: no")
    verdad(ClicFicha.vale(ClicReal(cuando: t.addingTimeInterval(-0.1), punto: CGPoint(x: 699, y: 179)), en: boton, ahora: t), "en su orilla (2 pt de holgura): sí")
    // un «botón» del tamaño de la ventana no es un botón (una página no puede declarar todo como su botón)
    for raro in [CGRect(x: 0, y: 0, width: 980, height: 660), CGRect(x: 0, y: 180, width: 600, height: 36), CGRect(x: 700, y: 0, width: 90, height: 300),
                 CGRect(x: 700, y: 180, width: 0, height: 36), CGRect(x: 700, y: 180, width: -90, height: 36), CGRect.null, CGRect.infinite] {
        verdad(!ClicFicha.vale(ClicReal(cuando: t.addingTimeInterval(-0.1), punto: CGPoint(x: 740, y: 200)), en: raro, ahora: t), "un marco que no es de botón: \(raro)")
    }
    igual(ClicFicha.marco([700, 180, 90, 36] as [Any]), boton, "el marco que manda la página")
    for malo in [[700, 180, 90] as [Any], ["a", 1, 2, 3], [Double.nan, 1, 2, 3], [], [1, 2, 3, 4, 5]] {
        verdad(ClicFicha.marco(malo) == nil, "un marco mal dicho: nada")
    }
    verdad(ClicFicha.marco(nil) == nil && ClicFicha.marco("x") == nil, "o que ni viene")
    // se gasta: el mismo clic no aprueba dos fichas
    var c: ClicReal? = enBoton
    verdad(ClicFicha.gastar(&c, en: boton, ahora: t), "la primera vez vale")
    verdad(!ClicFicha.gastar(&c, en: boton, ahora: t), "la segunda, ya no: se gastó")
    var d: ClicReal? = enBoton
    verdad(!ClicFicha.gastar(&d, en: CGRect(x: 0, y: 0, width: 50, height: 30), ahora: t) && d != nil, "si no valió, no se gasta (era para otro botón)")
}

@main
struct Pruebas {
    static func main() {
        lugar()
        archivo()
        pedidos()
        compa()
        enlaces()
        clicFicha()
        m3()
        if fallos.isEmpty {
            print("ok \(hechas)")
            exit(0)
        }
        print("FALLAN \(fallos.count) de \(hechas):")
        fallos.forEach { print("  " + $0) }
        exit(1)
    }
}
