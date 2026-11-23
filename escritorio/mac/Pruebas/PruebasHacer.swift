// Pruebas de la mano de A1 · primera parte (Hacer.swift: abrir DE VERDAD), sin XCTest:
//   swiftc -parse-as-library ../Sources/MonitoEscritorio/Logica.swift ../Sources/MonitoEscritorio/Seguridad.swift \
//          ../Sources/MonitoEscritorio/Hacer.swift PruebasHacer.swift -o /tmp/ph
//   /tmp/ph --reglas ../../reglas/portero.json --solo-logica      lo que no abre nada (resolver apps, archivos, páginas)
//   /tmp/ph --reglas ../../reglas/portero.json --carpeta <carpeta nueva>   además, DE VERDAD: el camino entero
//        portero → tarjeta → «Hazlo» → la mano abre en segundo plano → «Cerrar» lo cierra, con la Calculadora y con un
//        documento de TextEdit que la prueba crea en <carpeta>. Solo si ninguna de las dos estaba abierta (si sí, no las
//        toca: lo dice y sale con 0). Nada más se abre; al final no queda nada abierto ni ningún archivo fuera de <carpeta>.
// Imprime «ok N» (y una línea «evidencia {…}» con lo que pasó de verdad) y sale con 0; si algo falla, dice qué y sale con 1.
import AppKit
import Foundation

nonisolated(unsafe) var fallos: [String] = []
nonisolated(unsafe) var hechas = 0
nonisolated(unsafe) var evidencia: [String: Any] = [:]

func igual<T: Equatable>(_ a: T, _ b: T, _ que: String, linea: Int = #line) {
    hechas += 1
    if a != b { fallos.append("línea \(linea) · \(que): \(a) ≠ \(b)") }
}

func verdad(_ c: Bool, _ que: String, linea: Int = #line) {
    hechas += 1
    if !c { fallos.append("línea \(linea) · \(que)") }
}

/// Espera (sin bloquear el hilo principal: las respuestas de NSWorkspace llegan por él) a que `listo` diga que sí.
@MainActor func esperar(_ tope: TimeInterval, _ listo: () -> Bool) -> Bool {
    let fin = Date().addingTimeInterval(tope)
    while Date() < fin {
        if listo() { return true }
        RunLoop.main.run(until: Date().addingTimeInterval(0.05))
    }
    return listo()
}

@MainActor func corriendo(_ b: String) -> Bool { !NSRunningApplication.runningApplications(withBundleIdentifier: b).isEmpty }

/// Lo que no abre nada: la mano resuelve con lo que dice el sistema (LaunchServices), no con lo que dice el modelo.
@MainActor func logica(_ carpeta: String?) {
    let apps = Mano.instaladas()
    verdad(apps.contains { $0.bundle == "com.apple.calculator" }, "la Calculadora está entre las instaladas")
    verdad(apps.contains { $0.bundle == "com.apple.TextEdit" }, "TextEdit también")
    verdad(apps.contains { $0.bundle == "com.apple.finder" }, "y Finder")
    verdad(apps.allSatisfy { $0.ruta.hasSuffix(".app") }, "solo apps")
    var base = Destino(); base.app = "Terminal"; base.bundle = "com.apple.Terminal"
    let (c1, e1) = Mano.destinoApp("Calculadora", base: base)
    igual(c1?.abrirApp, "com.apple.calculator", "«Calculadora» → la app de verdad (\(e1 ?? ""))")
    verdad((c1?.abrirNombre ?? "").count > 0, "con su nombre: \(c1?.abrirNombre ?? "")")
    igual(Mano.destinoApp("la calculadora", base: base).0?.abrirApp, "com.apple.calculator", "con artículo")
    igual(Mano.destinoApp("Calculator", base: base).0?.abrirApp, "com.apple.calculator", "en inglés")
    igual(Mano.destinoApp("com.apple.calculator", base: base).0?.abrirApp, "com.apple.calculator", "por su identificador")
    let (n1, en1) = Mano.destinoApp("Calcu", base: base)
    verdad(n1 == nil && (en1 ?? "").contains("No encuentro"), "medio nombre: no se adivina (\(en1 ?? ""))")
    verdad(Mano.destinoApp("Una app que no existe 7f3a", base: base).0 == nil, "una que no existe")
    igual(c1?.app, "Terminal", "la ventana de enfrente se queda como origen")
    // páginas: el navegador que la abriría (el de fábrica, según el sistema)
    let (p1, _) = Mano.destinoPagina("https://www.sat.gob.mx/", base: base)
    verdad(!(p1?.abrirCon ?? "").isEmpty, "la página: con qué navegador se abriría (\(p1?.abrirCon ?? "-"))")
    igual(p1?.abrirURL, "https://www.sat.gob.mx/", "la dirección tal cual")
    verdad(Mano.destinoPagina("no es una dirección", base: base).0 == nil, "lo que no es una dirección")
    guard let dir = carpeta else { return }
    // archivos y carpetas: la ruta real (sin enlaces), si es carpeta y con qué app se abriría
    let fm = FileManager.default
    let doc = (dir as NSString).appendingPathComponent("Notas de la junta.txt")
    fm.createFile(atPath: doc, contents: Data("Pendientes de la junta:\n- revisar la cotización\n".utf8))
    let enlace = (dir as NSString).appendingPathComponent("enlace.txt")
    try? fm.removeItem(atPath: enlace)
    try? fm.createSymbolicLink(atPath: enlace, withDestinationPath: doc)
    let (a1, ea) = Mano.destinoArchivo(doc, base: base, enFinder: false)
    igual(a1?.ruta, (doc as NSString).resolvingSymlinksInPath, "la ruta real (\(ea ?? ""))")
    igual(a1?.abrirCon, "com.apple.TextEdit", "un .txt: con TextEdit (la de fábrica en esta Mac)")
    verdad(a1?.esCarpeta == false && a1?.enFinder == false, "un archivo")
    igual(Mano.destinoArchivo(enlace, base: base, enFinder: false).0?.ruta, (doc as NSString).resolvingSymlinksInPath, "un enlace: a dónde va de verdad")
    let (c2, _) = Mano.destinoArchivo(dir, base: base, enFinder: false)
    verdad(c2?.esCarpeta == true && c2?.abrirCon == "com.apple.finder", "una carpeta: en Finder")
    let (f1, _) = Mano.destinoArchivo(doc, base: base, enFinder: true)
    verdad(f1?.enFinder == true && f1?.abrirCon == "com.apple.finder", "mostrar en Finder")
    verdad(Mano.destinoArchivo((dir as NSString).appendingPathComponent("no-esta.txt"), base: base, enFinder: false).0 == nil, "lo que no existe")
    verdad(Mano.destinoArchivo("relativo.txt", base: base, enFinder: false).0 == nil, "una ruta a medias: que diga la entera")
    try? fm.removeItem(atPath: enlace)
}

/// DE VERDAD: el camino entero, con el portero de verdad y una «persona» que dice «Hazlo» a la tarjeta (aquí no hay
/// ventana: la tarjeta la enseña la app; lo que se prueba es lo que pasa después de tu OK).
@MainActor func deVerdad(_ dir: String) {
    let fm = FileManager.default
    for b in ["com.apple.calculator", "com.apple.TextEdit"] where corriendo(b) {
        print("salto la prueba de verdad: \(b) ya estaba abierta (no toco tus apps)")
        evidencia["saltada"] = b
        return
    }
    // la app que lanza se abre sin recuperar sus ventanas de antes (solo en la prueba)
    Mano.argumentosAlLanzar = ["-ApplePersistenceIgnoreState", "YES"]
    var n = 0
    let pt = Portero(etapa: .amarillo, nuevoId: { n += 1; return "h\(n)" })
    pt.abrirTurno("turno-mano", agente: "Luna")
    var base = Destino(); base.app = "Prueba"; base.bundle = "com.workspace.prueba"; base.casa = dir
    // 1 · «ábreme la Calculadora»
    let frente0 = NSWorkspace.shared.frontmostApplication?.bundleIdentifier ?? ""
    var pApp = PedidoAccion(tipo: "abrir"); pApp.app = "Calculadora"
    guard let calc = Mano.destinoApp("Calculadora", base: base).0 else { fallos.append("no encontré la Calculadora"); return }
    let r = pt.pedir(pApp, destinos: [calc])
    igual(r.salida, .tarjeta, "abrir la Calculadora: tarjeta amarilla")
    guard let t = r.tarjeta else { return }
    igual(t.titulo, "¿Abro \(calc.abrirNombre ?? "")?", "la tarjeta con el nombre del sistema")
    let ok = pt.responder(t.id, "hazlo", ahora: [calc])
    guard let aut = ok.autorizacion, pt.ejecutar(aut, ahora: [Mano.destinoApp("Calculadora", base: base).0 ?? calc]).ejecutada else {
        fallos.append("el OK no se pudo usar"); return
    }
    var abierto: Abierto? = nil, error: String? = nil, listo = false
    let t0 = Date()
    Mano.abrir(calc, modo: .segundoPlano) { a, e in abierto = a; error = e; listo = true }
    verdad(esperar(15) { listo }, "la mano contestó")
    verdad(error == nil, "sin error: \(error ?? "")")
    guard let a = abierto else { return }
    evidencia["calculadora"] = a.json().merging(["segundos": Double(Int(Date().timeIntervalSince(t0) * 10)) / 10], uniquingKeysWith: { x, _ in x })
    verdad(a.appNueva, "no estaba abierta: la abrí yo")
    verdad(corriendo("com.apple.calculator"), "la Calculadora está abierta")
    verdad(!a.activar, "en segundo plano no se pidió traerla al frente")
    verdad(!a.robo || a.devuelto, "no se quedó con tu foco (antes \(frente0), después \(a.frenteDespues))")
    verdad(esperar(5) { Mano.marcoDeVentana(pid: a.pid, archivo: nil) != nil }, "su ventana salió (para «a la vista» y «Enséñame»)")
    let av = AvisoAbrir.de(calc, appNueva: a.appNueva, modo: .segundoPlano, robo: a.robo, devuelto: a.devuelto)
    igual(av.boton, "Cerrar", "el aviso ofrece «Cerrar»")
    var cerrado: (String, Bool)? = nil
    Mano.cerrar(a) { txt, ok in cerrado = (txt, ok) }
    verdad(esperar(8) { cerrado != nil }, "Deshacer contestó")
    verdad(cerrado?.1 == true, "Deshacer la cerró: \(cerrado?.0 ?? "")")
    verdad(esperar(5) { !corriendo("com.apple.calculator") }, "la Calculadora ya no está abierta")
    evidencia["calculadora_cerrada"] = cerrado?.0 ?? ""
    // 2 · «abre este archivo» (un documento que la prueba crea en su carpeta)
    let doc = (dir as NSString).appendingPathComponent("Notas de la junta.txt")
    fm.createFile(atPath: doc, contents: Data("Pendientes de la junta:\n- revisar la cotización\n".utf8))
    var pArch = PedidoAccion(tipo: "abrir"); pArch.ruta = doc
    guard let arch = Mano.destinoArchivo(doc, base: base, enFinder: false).0 else { fallos.append("no resolví el archivo"); return }
    let r2 = pt.pedir(pArch, destinos: [arch])
    igual(r2.salida, .tarjeta, "abrir el documento: tarjeta amarilla (\(r2.motivo))")
    guard let t2 = r2.tarjeta else { return }
    igual(t2.donde, "Se abre con \(arch.abrirNombre ?? "")", "la tarjeta dice con qué app")
    let ok2 = pt.responder(t2.id, "hazlo", ahora: [arch])
    guard let aut2 = ok2.autorizacion, pt.ejecutar(aut2, ahora: [Mano.destinoArchivo(doc, base: base, enFinder: false).0 ?? arch]).ejecutada else {
        fallos.append("el OK del documento no se pudo usar"); return
    }
    abierto = nil; error = nil; listo = false
    Mano.abrir(arch, modo: .segundoPlano) { a, e in abierto = a; error = e; listo = true }
    verdad(esperar(15) { listo }, "la mano contestó (documento)")
    verdad(error == nil, "sin error: \(error ?? "")")
    guard let b = abierto else { return }
    evidencia["documento"] = b.json()
    verdad(b.appNueva && corriendo("com.apple.TextEdit"), "TextEdit se abrió con el documento")
    verdad(!b.robo || b.devuelto, "no se quedó con tu foco (antes \(b.frenteAntes), después \(b.frenteDespues))")
    verdad(esperar(6) { Mano.marcoDeVentana(pid: b.pid, archivo: doc) != nil }, "la ventana del documento salió")
    var cerrado2: (String, Bool)? = nil
    Mano.cerrar(b) { txt, ok in cerrado2 = (txt, ok) }
    verdad(esperar(8) { cerrado2 != nil } && cerrado2?.1 == true, "Deshacer cerró TextEdit: \(cerrado2?.0 ?? "")")
    verdad(esperar(5) { !corriendo("com.apple.TextEdit") }, "TextEdit ya no está abierto")
    evidencia["documento_cerrado"] = cerrado2?.0 ?? ""
    // si una app ya estaba abierta, Deshacer no la cierra (y lo dice)
    var ya = b; ya.appNueva = false
    var honesto: (String, Bool)? = nil
    Mano.cerrar(ya) { txt, ok in honesto = (txt, ok) }
    verdad(esperar(2) { honesto != nil } && honesto?.1 == false && (honesto?.0 ?? "").contains("⌘W"), "ya abierta: no la cierro: \(honesto?.0 ?? "")")
    pt.cerrarTurno()
    verdad(pt.registro.contains { ($0["resultado"] as? String) == "hecho" }, "la bitácora dice «hecho»")
}

@main
struct PruebasHacer {
    @MainActor static func main() {
        let args = CommandLine.arguments
        func arg(_ k: String) -> String? { args.firstIndex(of: k).flatMap { $0 + 1 < args.count ? args[$0 + 1] : nil } }
        if let r = arg("--reglas") { Reglas.usar(Reglas.cargar(r)) }
        let carpeta = arg("--carpeta")
        if let c = carpeta { try? FileManager.default.createDirectory(atPath: c, withIntermediateDirectories: true) }
        logica(carpeta)
        if !args.contains("--solo-logica"), let c = carpeta { deVerdad(c) }
        if let d = try? JSONSerialization.data(withJSONObject: evidencia, options: [.sortedKeys]), let s = String(data: d, encoding: .utf8) {
            print("evidencia " + s)
        }
        if fallos.isEmpty { print("ok \(hechas)"); exit(0) }
        print("FALLAN \(fallos.count) de \(hechas):")
        fallos.forEach { print("  " + $0) }
        exit(1)
    }
}
