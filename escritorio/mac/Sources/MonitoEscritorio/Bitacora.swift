// WORKSPACE · MonitoEscritorio/Bitacora — que lo que le pasa a la app quede escrito (ronda 2 · E14).
//
// Por qué: <estado>/escritorio/app.log llevaba vacío desde el 21-nov. `abrir.py` le pasa ese archivo a `open --stderr`,
// pero (1) cuando la app se reabre sola (Ajustes de macOS tras dar un permiso, un doble clic) su stderr no va a ningún
// lado, y (2) la app casi nunca escribía nada. Si fallaba, no quedaba rastro.
//
// Qué hace, una vez, al arrancar (main.swift → Bitacora.arrancar):
//   · si su stderr no es ya un archivo, lo manda a <estado>/app.log (agregando; 600). Así TODO lo que cualquier archivo
//     de la app escriba a stderr, lo que diga AppKit y lo que diga el puente (Python hereda ese stderr) queda ahí;
//   · anota que arrancó, con su versión (de qué fuentes salió: lo que abrir.py dejó al lado del paquete) y su pid;
//   · deja <estado>/app.version.json para que las herramientas (Python) comparen su versión con la de la app (E7: la
//     app abierta era más vieja que sus herramientas y nadie lo decía);
//   · anota una excepción sin atrapar y una caída (señal), y que se cerró.
// Para anotar algo desde cualquier otro archivo: `Bitacora.anotar("No pude …")` (una línea, con su hora).
// Solo Foundation: se prueba suelta (escritorio/mac/Pruebas/PruebasBitacora.swift). Nunca anota lo que el socio
// escribe ni lo que hay en su pantalla: solo lo que le pasa a la app.
import Foundation

enum Bitacora {
    /// Lo más que mide una línea.
    static let tope = 2000
    /// Lo más que mide app.log al arrancar: si pasa, se queda con lo último.
    static let maximo = 1_000_000

    /// ¿El stderr de este proceso ya va a un archivo? (abierta con `open --stderr app.log`: se respeta ese).
    static func stderrEsArchivo() -> Bool {
        var st = stat()
        return fstat(2, &st) == 0 && (st.st_mode & S_IFMT) == S_IFREG
    }

    /// «2026-11-22 14:05:01 app · texto»: un solo renglón, acotado.
    static func linea(_ texto: String, ahora: Date = Date()) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "yyyy-MM-dd HH:mm:ss"
        var t = texto.replacingOccurrences(of: "\r", with: " ").replacingOccurrences(of: "\n", with: " ⏎ ")
        if t.count > tope { t = String(t.prefix(tope - 1)) + "…" }
        return f.string(from: ahora) + " app · " + t + "\n"
    }

    /// Una línea a app.log (el stderr). Desde cualquier hilo; nunca falla.
    static func anotar(_ texto: String) {
        let d = Array(linea(texto).utf8)
        d.withUnsafeBufferPointer { p in _ = write(2, p.baseAddress, p.count) }
    }

    /// Si el archivo pasa de `maximo`, se queda con su última parte (desde un renglón entero). → si lo recortó.
    @discardableResult
    static func recortar(_ ruta: String, maximo: Int = Bitacora.maximo) -> Bool {
        guard let attr = try? FileManager.default.attributesOfItem(atPath: ruta),
              let tam = (attr[.size] as? NSNumber)?.intValue, tam > maximo,
              let datos = FileManager.default.contents(atPath: ruta) else { return false }
        var cola = datos.suffix(max(0, maximo / 2))
        if let salto = cola.firstIndex(of: 10) { cola = cola.suffix(from: cola.index(after: salto)) }
        return (try? Data(cola).write(to: URL(fileURLWithPath: ruta), options: .atomic)) != nil
    }

    /// El stderr a `ruta` (agregando), si no era ya un archivo. → si lo cambió.
    @discardableResult
    static func redirigir(a ruta: String) -> Bool {
        if stderrEsArchivo() { return false }
        try? FileManager.default.createDirectory(atPath: (ruta as NSString).deletingLastPathComponent,
                                                 withIntermediateDirectories: true, attributes: nil)
        recortar(ruta)
        let fd = open(ruta, O_WRONLY | O_CREAT | O_APPEND, 0o600)
        if fd < 0 { return false }
        let hecho = dup2(fd, 2) >= 0
        close(fd)
        return hecho
    }

    /// De qué fuentes salió esta app: lo que abrir.py anotó al lado del paquete («<app sin .app>.instalada.json»).
    /// → ["huella", "tipo", "cuando"] (lo que haya); vacío si no hay registro (corrida suelta, sin paquete).
    static func version(app: URL) -> [String: String] {
        let registro = app.deletingPathExtension().appendingPathExtension("instalada.json")
        guard app.pathExtension == "app", let d = try? Data(contentsOf: registro),
              let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any] else { return [:] }
        var out: [String: String] = [:]
        for k in ["huella", "tipo", "cuando"] {
            if let v = o[k] as? String, !v.isEmpty { out[k] = String(v.prefix(80)) }
        }
        return out
    }

    /// <estado>/app.version.json: lo que las herramientas comparan con sus propias fuentes (escritorio/cliente.py).
    static func escribirVersion(estado: String, version: [String: String], app: URL, raiz: String) {
        var d: [String: Any] = ["pid": Int(getpid()), "app": app.path, "raiz": raiz,
                                "bundle": Bundle.main.bundleIdentifier ?? "",
                                "desde": ISO8601DateFormatter().string(from: Date())]
        for (k, v) in version { d[k] = v }
        guard let datos = try? JSONSerialization.data(withJSONObject: d, options: [.sortedKeys]) else { return }
        let ruta = (estado as NSString).appendingPathComponent("app.version.json")
        try? FileManager.default.createDirectory(atPath: estado, withIntermediateDirectories: true, attributes: nil)
        if (try? datos.write(to: URL(fileURLWithPath: ruta), options: .atomic)) != nil { chmod(ruta, 0o600) }
    }

    /// Al arrancar la app (una vez). `estado`: <estado de Workspace>/escritorio ("" = el de siempre). `senales`: anotar
    /// también una caída (las pruebas lo apagan).
    static func arrancar(estado: String, raiz: String, app: URL = Bundle.main.bundleURL, senales: Bool = true) {
        let carpeta = estado.isEmpty ? (NSHomeDirectory() as NSString).appendingPathComponent(".claude/workspace/escritorio") : estado
        let propio = redirigir(a: (carpeta as NSString).appendingPathComponent("app.log"))
        let v = version(app: app)
        escribirVersion(estado: carpeta, version: v, app: app, raiz: raiz)
        anotar("arrancó · pid \(getpid()) · versión \(v["huella"].map { String($0.prefix(16)) } ?? "sin registro")"
               + (v["tipo"].map { " · firma \($0)" } ?? "") + " · copia \(raiz)" + (propio ? " · (reabierta sin su registro: lo tomé yo)" : ""))
        NSSetUncaughtExceptionHandler { e in
            Bitacora.anotar("excepción sin atrapar: \(e.name.rawValue) · \(e.reason ?? "")")
        }
        atexit { Bitacora.anotar("se cerró") }
        if senales { caidas() }
    }

    /// Una caída (señal del sistema) deja su línea antes de morir. Dentro de un manejador de señal solo se puede
    /// escribir bytes ya armados: nada de String ni de fechas.
    private static func caidas() {
        for s in [SIGSEGV, SIGBUS, SIGILL, SIGABRT, SIGTRAP, SIGFPE] {
            signal(s) { n in
                let m: StaticString = "app · se cayó (señal del sistema número "
                _ = write(2, m.utf8Start, m.utf8CodeUnitCount)
                var b: (UInt8, UInt8, UInt8, UInt8) = (48 + UInt8((n / 10) % 10), 48 + UInt8(n % 10), 41, 10)
                withUnsafeBytes(of: &b) { p in _ = write(2, p.baseAddress, 4) }
                signal(n, SIG_DFL)
                raise(n)
            }
        }
    }
}
