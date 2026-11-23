// WORKSPACE · MonitoEscritorio — el monito de tu agente en una esquina de la Mac.
//
// La app solo pinta y escucha: el monito y su burbuja son escritorio/web/monito.html (el Monito de la página) en un
// WKWebView; lo que haces sale por escritorio/puente.py, que habla con la página local de Workspace por /api/v2,
// igual que el hub. No hay backend propio ni se contesta nada por ti.
//
//   MonitoEscritorio --html <monito.html> --python <python3> --puente <escritorio/puente.py> [--raiz <repo>]
//                    [--estado <carpeta de estado>/escritorio] [--demo [permisos]]
//
// Sin argumentos (abierta como app por LaunchServices, o reabierta por Ajustes tras dar un permiso) lee los suyos de
// MonitoEscritorio.opciones.json, AL LADO del paquete (lo escribe escritorio/abrir.py): nada de la máquina va dentro
// del paquete firmado, así queda idéntico entre arranques y macOS no vuelve a pedir los permisos.
//
// · ⌥ Espacio lo llama y lo guarda entero, en chico o en grande (Compa, LogicaGrande.swift; atajo global de Carbon: no pide permisos de accesibilidad).
// · El panel no roba el foco: solo lo toma mientras escribes en la barra.
// · Fuera del monito y su burbuja, los clics pasan a la app de abajo.
// · Sus manos (F1): ver y señalar, por un puerto local (escritorio/manos_mcp.py), solo dentro de un turno que salió de
//   su burbuja y sobre la ventana que tenías enfrente. Nunca hace clic ni escribe.
// · Se arrastra a cualquier lugar de cualquier pantalla, sin perderse en los bordes; recuerda dónde lo dejaste.
import AppKit

struct Opciones {
    var html = ""
    var python = "/usr/bin/python3"
    var puente = ""
    var raiz = ""
    /// Para probar sin teclado: al llegar los agentes, elige `agente`, escribe `probar` y lo manda (como tú).
    var probar = ""
    var agente = ""
    /// Archivo donde se anota cada línea que va y viene con el puente (para revisar una prueba).
    var registro = ""
    /// Fotos de lo que pinta el panel (sin permiso de grabar pantalla): <ruta>_00.png, _01… cada 2.5 s.
    var foto = ""
    /// <estado de Workspace>/escritorio: manos.json, app.pid y las miradas (fotos de 7 días y su bitácora).
    var estado = ""
    /// Al abrir, enseña cómo señala (tres lugares) o, con «permisos», la tarjeta de permiso.
    var demo = ""
    /// En qué esquina vive la primera vez: «derecha» (de fábrica) o «izquierda» (para probar una segunda copia sin tapar
    /// la primera). Después, donde lo dejaste (lugar.json, por cada arreglo de pantallas).
    var esquina = "derecha"
    /// Pruebas del movimiento: anota en este archivo, cuadro por cuadro, si la ventana del monito sigue en pantalla, si
    /// tiene el teclado y los huecos de la página (y corre un guion: abrir la barra, Esc…). No lo usa nadie más.
    var medir = ""
    /// Pruebas: la ventana casi transparente (que nadie la vea mientras se mide).
    var fantasma = false
    /// Sin ⌥ Espacio (una segunda copia de prueba no le quita el atajo a la que ya está abierta).
    var sinAtajo = false
    /// A0 · actuar: «ensayo» prende la herramienta `actuar` con su tarjeta de OK, pero nada se hace de verdad. Vacío (de
    /// fábrica): el monito no ofrece actuar.
    var actuar = ""
    /// Pruebas: un archivo de JS que la app corre en la burbuja cuando está lista (+1.5 s): aprieta botones como tú y
    /// cuenta lo que pasó con {op: "guion_log", texto} (va a --registro). Solo por la línea de comando.
    var guion = ""
    /// Pruebas de la voz: un archivo de audio EN VEZ del micrófono (nunca se abre el micrófono ni se pide un permiso a
    /// macOS) y qué se ensaya: «primera» (la frase de la primera vez), «apagado», «sin-espanol», «leer», «sin-parar».
    var vozArchivo = ""
    var vozCaso = ""

    static func leer(_ args: [String]) -> Opciones? {
        var o = Opciones()
        var i = 1
        while i < args.count {
            let k = args[i]
            let v = i + 1 < args.count ? args[i + 1] : ""
            switch k {
            case "--html": o.html = v; i += 2
            case "--python": o.python = v; i += 2
            case "--puente": o.puente = v; i += 2
            case "--raiz": o.raiz = v; i += 2
            case "--probar": o.probar = v; i += 2
            case "--agente": o.agente = v; i += 2
            case "--registro": o.registro = v; i += 2
            case "--foto": o.foto = v; i += 2
            case "--estado": o.estado = v; i += 2
            case "--esquina": o.esquina = v; i += 2
            case "--sin-atajo": o.sinAtajo = true; i += 1
            case "--actuar": o.actuar = v == "ensayo" ? v : ""; i += 2
            case "--medir": o.medir = v; i += 2
            case "--fantasma": o.fantasma = true; i += 1
            case "--guion": o.guion = v; i += 2
            case "--voz-archivo": o.vozArchivo = v; i += 2
            case "--voz-caso": o.vozCaso = v; i += 2
            case "--demo":
                if v == "permisos" || v == "insistir" || v == "senalar" || DemoActuar.tipos.contains(v) { o.demo = v; i += 2 } else { o.demo = "senalar"; i += 1 }
            default: i += 1
            }
        }
        if o.html.isEmpty || o.puente.isEmpty { return nil }
        if o.raiz.isEmpty { o.raiz = ((o.puente as NSString).deletingLastPathComponent as NSString).deletingLastPathComponent }
        return o
    }

    /// Los argumentos guardados en el paquete (y su entorno), para cuando la abren sin argumentos; los que traiga la
    /// línea de comando (`open … --args --demo`) se suman al final.
    static func delPaquete() -> [String]? {
        let alLado = Bundle.main.bundleURL.deletingLastPathComponent().appendingPathComponent("MonitoEscritorio.opciones.json")
        let dentro = Bundle.main.url(forResource: "opciones", withExtension: "json")      // las de antes
        guard let u = FileManager.default.fileExists(atPath: alLado.path) ? alLado : dentro,
              let d = try? Data(contentsOf: u),
              let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
              let args = o["args"] as? [String] else { return nil }
        for (k, v) in (o["env"] as? [String: String]) ?? [:] { setenv(k, v, 1) }
        return [CommandLine.arguments.first ?? "MonitoEscritorio"] + args + CommandLine.arguments.dropFirst().filter { $0.hasPrefix("--demo") || $0 == "permisos" || $0 == "insistir" || $0 == "senalar" || DemoActuar.tipos.contains($0) }
    }
}

let delPaquete = !CommandLine.arguments.contains("--html")
let argumentos = delPaquete ? (Opciones.delPaquete() ?? CommandLine.arguments) : CommandLine.arguments
guard let opciones = Opciones.leer(argumentos) else {
    FileHandle.standardError.write("Uso: MonitoEscritorio --html <monito.html> --python <python3> --puente <puente.py>\n".data(using: .utf8)!)
    exit(2)
}
if delPaquete, let no = opciones.revisarDelPaquete() {
    FileHandle.standardError.write("No abro: sus opciones no son de fiar (\(no)). Vuelve a abrirlo con escritorio/abrir.py.\n".data(using: .utf8)!)
    exit(2)
}

// ronda 2 · E14: lo que le pase a la app desde aquí queda en <estado>/app.log, con su versión (Bitacora.swift)
Bitacora.arrancar(estado: opciones.estado, raiz: opciones.raiz)

let app = NSApplication.shared
app.setActivationPolicy(.accessory)          // sin ícono en el Dock: vive en la esquina y en la barra de menú
let monito = MainActor.assumeIsolated { Monito(opciones: opciones) }
app.delegate = monito
app.run()

extension Opciones {
    /// Lo que se acepta de MonitoEscritorio.opciones.json (está al lado del paquete y cualquier programa tuyo lo puede
    /// editar; con una firma estable, lo que la app arranca usa sus permisos): la burbuja y el puente solo de SU lugar en
    /// la copia de Workspace (`raiz`), y Python solo como ruta entera a un ejecutable. → el motivo si no, o nil.
    /// Es un candado chico: quien puede escribir en la copia de Workspace puede cambiar el puente mismo. Lo de fondo
    /// (antes de clientes): el puente y la burbuja dentro de la app firmada.
    func revisarDelPaquete() -> String? {
        let fm = FileManager.default
        let raiz = (raiz as NSString).standardizingPath
        func es(_ ruta: String, _ rel: String) -> Bool {
            (ruta as NSString).standardizingPath == (raiz as NSString).appendingPathComponent(rel)
        }
        if !es(html, "escritorio/web/monito.html") { return "la burbuja no es la de su copia de Workspace" }
        if !es(puente, "escritorio/puente.py") { return "el puente no es el de su copia de Workspace" }
        if !fm.fileExists(atPath: (raiz as NSString).appendingPathComponent("escritorio/mac/Package.swift")) {
            return "la carpeta no es una copia de Workspace"
        }
        if !python.hasPrefix("/") || !fm.isExecutableFile(atPath: python) { return "python no es un ejecutable" }
        // lo de pruebas (correr JS en la burbuja, escribir solo, medir) solo por la línea de comando, nunca de un archivo
        if !guion.isEmpty || !probar.isEmpty || !medir.isEmpty || !vozArchivo.isEmpty || !vozCaso.isEmpty {
            return "lo de pruebas solo va por la línea de comando"
        }
        return nil
    }
}
