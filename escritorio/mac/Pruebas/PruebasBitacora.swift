// Pruebas de Bitacora.swift (ronda 2 · E14: que los errores de la app queden en app.log). Sin XCTest.
//   swiftc -parse-as-library ../Sources/MonitoEscritorio/Bitacora.swift PruebasBitacora.swift -o /tmp/pb && /tmp/pb <carpeta>
// Imprime «ok N» y sale con 0; si algo falla, dice qué y sale con 1. Lo corre tests/test_monito_fuera_app.py con el
// stderr en una tubería (como una app reabierta por Ajustes: su stderr no es un archivo).
import Foundation

var fallos: [String] = []
var hechas = 0

func verdad(_ c: Bool, _ que: String, linea: Int = #line) {
    hechas += 1
    if !c { fallos.append("línea \(linea) · \(que)") }
}

func leer(_ ruta: String) -> String { (try? String(contentsOfFile: ruta, encoding: .utf8)) ?? "" }

@main
struct Pruebas {
    static func main() {
        let carpeta = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : NSTemporaryDirectory()
        let estado = (carpeta as NSString).appendingPathComponent("estado")
        let log = (estado as NSString).appendingPathComponent("app.log")

        // una línea: fecha, de quién es, y siempre un solo renglón (acotado)
        let l = Bitacora.linea("se cayó\nel puente", ahora: Date(timeIntervalSince1970: 0))
        verdad(l.hasSuffix("\n") && l.dropLast().contains("\n") == false, "un solo renglón: \(l)")
        verdad(l.contains(" app · se cayó"), "dice de quién es: \(l)")
        verdad(Bitacora.linea(String(repeating: "x", count: 9000)).count < 2100, "acotada")

        // la versión: lo que abrir.py anotó al lado del paquete (de qué fuentes salió)
        let app = (carpeta as NSString).appendingPathComponent("Monito de prueba.app")
        try? FileManager.default.createDirectory(atPath: app, withIntermediateDirectories: true)
        try? "{\"huella\": \"abc123\", \"tipo\": \"developer_id\", \"cuando\": \"2026-11-22T14:05:45\"}"
            .write(toFile: (carpeta as NSString).appendingPathComponent("Monito de prueba.instalada.json"), atomically: true, encoding: .utf8)
        let v = Bitacora.version(app: URL(fileURLWithPath: app))
        verdad(v["huella"] == "abc123", "lee la huella: \(v)")
        verdad(Bitacora.version(app: URL(fileURLWithPath: "/no/existe.app"))["huella"] == nil, "sin registro: nada")

        // recortar: un app.log gigante no crece para siempre (se queda con lo último)
        try? FileManager.default.createDirectory(atPath: estado, withIntermediateDirectories: true)
        try? (String(repeating: "viejo\n", count: 400) + "ultimo\n").write(toFile: log, atomically: true, encoding: .utf8)
        verdad(Bitacora.recortar(log, maximo: 600), "recorta")
        verdad(leer(log).utf8.count <= 600 && leer(log).hasSuffix("ultimo\n"), "queda lo último")
        verdad(!Bitacora.recortar(log, maximo: 600), "ya cabía: no lo toca")

        // arrancar: el stderr (aquí una tubería) pasa a app.log; queda la línea de arranque y app.version.json
        verdad(!Bitacora.stderrEsArchivo(), "la prueba corre con el stderr en una tubería")
        Bitacora.arrancar(estado: estado, raiz: "/copia/de/workspace", app: URL(fileURLWithPath: app), senales: false)
        verdad(Bitacora.stderrEsArchivo(), "ahora va a un archivo")
        Bitacora.anotar("No pude abrir el puerto local de las manos")
        FileHandle.standardError.write("lo que escribe cualquier otro archivo de la app\n".data(using: .utf8)!)
        let t = leer(log)
        verdad(t.contains("arrancó") && t.contains("abc123"), "la línea de arranque con su versión: \(t)")
        verdad(t.contains(" app · No pude abrir el puerto local de las manos\n"), "lo anotado")
        verdad(t.contains("lo que escribe cualquier otro archivo de la app\n"), "y el stderr de siempre")
        verdad(t.contains("ultimo\n"), "sin borrar lo de antes")
        let vj = leer((estado as NSString).appendingPathComponent("app.version.json"))
        verdad(vj.contains("\"huella\"") && vj.contains("abc123") && vj.contains("\"pid\""), "app.version.json: \(vj)")
        // otra vez: ya es un archivo, no se vuelve a redirigir (abierta con `open --stderr`, se respeta ese)
        verdad(!Bitacora.redirigir(a: (estado as NSString).appendingPathComponent("otro.log")), "un stderr que ya es archivo se respeta")

        if fallos.isEmpty { print("ok \(hechas)") } else { print(fallos.joined(separator: "\n")); exit(1) }
    }
}
