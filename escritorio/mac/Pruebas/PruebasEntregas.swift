// Pruebas de LogicaEntregas.swift (E1 · entregas en la burbuja), sin XCTest:
//   swiftc -parse-as-library ../Sources/MonitoEscritorio/Logica.swift ../Sources/MonitoEscritorio/LogicaEntregas.swift \
//          PruebasEntregas.swift -o /tmp/pe && /tmp/pe
// Imprime «ok N» y sale con 0; si algo falla, dice qué y sale con 1. Lo corre tests/test_escritorio_entregas.py.
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

func zonas() {
    let z = ZonaArrastre.leer([[10, 20, 200, 80, "luna", "deliverables/a/A_v1.pptx"], [0, 0, 0, 10, "x", "y"],
                               [1, 2, 3], ["a", 1, 1, 1, "x", "y"], [10, 60, 200, 80, "luna", "deliverables/a/B_v1.docx"]])
    igual(z.count, 2, "solo las zonas bien formadas (sin alto cero, sin números, sin agente)")
    igual(Arrastre.zona(en: CGPoint(x: 50, y: 30), z)?.ruta, "deliverables/a/A_v1.pptx", "la de arriba")
    igual(Arrastre.zona(en: CGPoint(x: 50, y: 70), z)?.ruta, "deliverables/a/B_v1.docx", "si se enciman, la última pintada")
    verdad(Arrastre.zona(en: CGPoint(x: 300, y: 30), z) == nil, "fuera de toda zona, nada")
    verdad(ZonaArrastre.leer("basura").isEmpty && ZonaArrastre.leer(nil).isEmpty, "lo que no es lista, nada")
}

func umbral() {
    verdad(!Arrastre.empieza(desde: .zero, ahora: CGPoint(x: 2, y: 2)), "4 pt o menos sigue siendo un clic")
    verdad(Arrastre.empieza(desde: .zero, ahora: CGPoint(x: 3, y: 2)), "más de 4 pt ya es arrastrar")
    igual(Arrastre.clave("luna", "a/b.md"), "luna\u{1}a/b.md", "la clave de una entrega conocida")
}

func plantillas() {
    igual(Plantillas.valida("presentacion"), "presentacion", "una de la lista")
    igual(Plantillas.valida("rm -rf"), "", "lo que no está en la lista no pasa")
    igual(Plantillas.valida(nil), "", "sin plantilla")
    igual(Plantillas.titulo("minuta"), "Minuta con pendientes (Word · quién, qué y cuándo)", "su título")
}

func tarjeta() {
    let t = Propuesta.tarjeta(id: "p1", agente: "luna", nombre: "Luna", pedido: "Hazme 5 láminas\npara el director",
                              titulo: "Avance de ventas", plantilla: "presentacion",
                              archivo: ("Ventas_nov.xlsx", "~/Documents"), nivel: "auto", motor: "Claude Code",
                              acotado: true, leyo: true)
    igual(t["cab"] as? String, "Encargo · con tu OK", "la cabecera")
    igual(t["quien"] as? String, "Encargar a Luna, en su conversación de trabajo:", "a quién")
    igual(t["pedido"] as? String, "Hazme 5 láminas para el director", "lo que pidió, en un renglón")
    let filas = (t["filas"] as? [[String]]) ?? []
    igual(filas.map { $0[0] }, ["Lleva", "Usa", "Puede", "Lo lee", "Queda en"], "sus filas, en orden")
    igual(filas[0][1], "Ventas_nov.xlsx", "el archivo de verdad")
    verdad(filas[0][2].contains("no la foto"), "y lo dice")
    // Fable v2: el encargo tiene SU nivel (no el de la página) y la tarjeta dice la verdad
    verdad(filas[2][1].contains("solo en su carpeta de este encargo"), "lo que puede: su carpeta: \(filas[2][1])")
    verdad(filas[2][1].contains("sin comandos ni internet"), "de fábrica, sin comandos ni internet")
    verdad(!filas[2][1].contains("correr comandos"), "no dice que corre comandos si no es cierto")
    igual(filas[3][1], "Claude Code", "lo lee su motor")
    igual(filas[3][2], "en la nube de su proveedor", "y dónde")
    let niv = (t["nivel"] as? [String: Any]) ?? [:]
    igual(niv["acotado"] as? Bool, true, "su nivel lo cumple Workspace con este motor")
    igual(((niv["casillas"] as? [[String]]) ?? []).map { $0[0] }, ["comandos", "internet"], "subirlo: una casilla por cosa")
    verdad((niv["comandos"] as? String)?.contains("correr comandos") == true, "con la casilla, lo dice")
    verdad((niv["comandos"] as? String)?.contains("internet") == true, "y que un comando también puede usar internet")
    verdad((t["formato"] as? String)?.contains("texto") == true, "una presentación sin comandos: va en texto, y lo dice")
    verdad((t["nota"] as? String)?.contains("no viaja como orden") == true, "si leyó tu pantalla, lo dice")
    let b = (t["botones"] as? [[Any]]) ?? []
    igual(b.map { ($0[1] as? String) ?? "" }, ["encargar", "aqui", "no"], "Encargar · Mejor aquí, corto · No")
    let sin = Propuesta.tarjeta(id: "p2", agente: "eco", nombre: "Eco", pedido: "x", titulo: "", plantilla: "",
                                archivo: nil, nivel: "preguntar", motor: "Claude Code", acotado: true, leyo: false)
    igual(((sin["filas"] as? [[String]]) ?? []).map { $0[0] }, ["Puede", "Lo lee", "Queda en"], "sin archivo ni plantilla")
    // un Word sin comandos: lo entrega en texto (y se dice)
    let word = Propuesta.tarjeta(id: "p4", agente: "luna", nombre: "Luna", pedido: "Hazme la minuta", titulo: "", plantilla: "minuta",
                                 archivo: nil, nivel: "auto", motor: "Claude Code", acotado: true, leyo: false)
    verdad((word["formato"] as? String)?.contains("También comandos") == true, "para el Word, marca «También comandos»")
    // un motor que Workspace todavía no acota: la verdad (su página) y tu elección
    let cop = Propuesta.tarjeta(id: "p3", agente: "eco", nombre: "Eco", pedido: "x", titulo: "", plantilla: "",
                                archivo: ("Cotizacion.pdf", "~/Downloads"), nivel: "auto", motor: "Copilot", acotado: false, leyo: false)
    let cf = (cop["filas"] as? [[String]]) ?? []
    verdad(cf.first { $0[0] == "Puede" }?[1].contains("correr comandos") == true, "con Automático: corre comandos (y lo dice)")
    let cn = (cop["nivel"] as? [String: Any]) ?? [:]
    igual(cn["acotado"] as? Bool, false, "no acotado")
    igual(((cn["casillas"] as? [[String]]) ?? []).map { $0[0] }, ["como_pagina"], "encargarlo así es tu elección")
    verdad((cn["aviso"] as? String)?.contains("Copilot") == true, "y dice por qué")
    verdad(Propuesta.puede("auto").contains("correr comandos"), "Automático corre comandos: la tarjeta no lo calla")
    verdad(Propuesta.puede("sin_permisos").contains("sin internet"), "en su caja: sin internet")
    verdad(sin["nota"] == nil, "sin la nota si no leyó")
    verdad(Propuesta.puede("preguntar").contains("te pregunta"), "con «preguntar», te pregunta")
    verdad(Propuesta.puede("").contains("Permisos"), "sin nivel, lo que diga la página")
    igual(Propuesta.cita(String(repeating: "a", count: 300)).count, 220, "un pedido largo se recorta")
}

// Fable v2 §2.1: el encargo lleva tus últimos mensajes (no solo el último) y lo puedes editar antes de Encargar
func recado() {
    let t0 = Date(timeIntervalSince1970: 1_795_000_000)
    var r = Recado()
    r.anotar("hazme la minuta", t0)
    r.anotar("la del martes, con pendientes por persona", t0.addingTimeInterval(40))
    igual(r.texto(ahora: t0.addingTimeInterval(60)), "hazme la minuta\nla del martes, con pendientes por persona",
          "tus mensajes de esa plática, del más viejo al más nuevo")
    r.anotar("sí, hazlo", t0.addingTimeInterval(70))
    r.anotar("y que diga quién va", t0.addingTimeInterval(80))
    igual(r.texto(ahora: t0.addingTimeInterval(90)).components(separatedBy: "\n").count, Recado.cuantos, "solo los últimos \(Recado.cuantos)")
    verdad(r.texto(ahora: t0.addingTimeInterval(90)).hasSuffix("y que diga quién va"), "el último al final")
    igual(r.texto(ahora: t0.addingTimeInterval(90 + Recado.vigencia + 1)), "", "una plática vieja ya no viaja")
    var g = Recado()
    g.anotar(String(repeating: "a", count: 900), t0)
    g.anotar(String(repeating: "b", count: 900), t0)
    verdad(g.texto(ahora: t0).count <= Recado.tope && g.texto(ahora: t0).hasSuffix("b"), "cabe en el tope (lo más nuevo se queda)")
    g.vaciar()
    igual(g.texto(ahora: t0), "", "tras encargar, de cero")
    let t = Propuesta.tarjeta(id: "p9", agente: "luna", nombre: "Luna", pedido: "hazme la minuta\nla del martes", titulo: "",
                              plantilla: "minuta", archivo: nil, nivel: "auto", motor: "Claude Code", acotado: true, leyo: false)
    igual(t["editable"] as? Bool, true, "la tarjeta deja editar lo que se encarga")
    igual(t["pedido_completo"] as? String, "hazme la minuta\nla del martes", "con todo el recado, en renglones")
}

func decision() {
    verdad(Decision.texto("encargar").contains("conversación de trabajo ya lo tiene"), "encargado")
    verdad(Decision.texto("aqui").contains("aquí, corto"), "mejor aquí")
    verdad(Decision.texto("no").contains("dijo que no"), "no")
    verdad(Decision.texto("tiempo").contains("todavía no decide"), "sin decidir")
}

func documento() {
    igual(Documento.ruta("file:///Users/x/Documents/Ventas%20nov.xlsx"), "/Users/x/Documents/Ventas nov.xlsx", "un archivo")
    verdad(Documento.ruta("https://ejemplo.mx/a.xlsx") == nil, "una página no es un archivo")
    verdad(Documento.ruta(nil) == nil && Documento.ruta("") == nil && Documento.ruta("file:///") == nil, "sin documento")
    igual(Documento.donde("/Users/x/Documents/a.xlsx", casa: "/Users/x"), "~/Documents", "de dónde, sin la ruta entera")
    igual(Documento.donde("/Volumes/Equipo/a.xlsx", casa: "/Users/x"), "/Volumes/Equipo", "fuera de tu carpeta")
}

func candadoYFoto() {
    let t = TurnoAbierto(id: String(repeating: "a", count: 32), desde: Date(), agente: "luna")
    verdad(Candado.revisar("encargar", turno: nil, pedido: nil, ahora: Date()) != nil, "encargar solo dentro de un turno")
    verdad(Candado.revisar("encargar", turno: t, pedido: t.id, ahora: Date()) == nil, "con el turno, sí (solo propone)")
    var f = FotoDelMomento(app: "Microsoft Excel", bundle: "com.microsoft.Excel")
    f.documento = "Ventas_nov.xlsx"
    igual(f.paraMandar()["documento"] as? String, "Ventas_nov.xlsx", "el nombre del archivo viaja (los botones de la barra)")
}

func resultados() {
    // cada botón de una entrega contesta en la burbuja (WSMEntregas.hecho), también cuando no se pudo
    let h = Resultado.hecho("copiado", ok: true, agente: "luna", ruta: "deliverables/a/A_v1.md")
    igual(h["que"] as? String, "copiado", "qué pasó")
    igual(h["ok"] as? Bool, true, "salió")
    igual(h["agente"] as? String, "luna", "de quién")
    igual(h["ruta"] as? String, "deliverables/a/A_v1.md", "qué tarjeta")
    verdad(h["ensayo"] == nil, "de verdad no dice ensayo")
    let e = Resultado.hecho("abierto", ok: true, agente: "luna", ruta: "x.html", app: "Safari", ensayo: true)
    igual(e["app"] as? String, "Safari", "con qué app se abrió")
    igual(e["ensayo"] as? Bool, true, "en ensayo lo dice")
    verdad(Resultado.ensayo(["WORKSPACE_MONITO_SISTEMA": "ensayo"]), "la costura de las pruebas")
    verdad(!Resultado.ensayo([:]) && !Resultado.ensayo(["WORKSPACE_MONITO_SISTEMA": "1"]), "de fábrica, de verdad")
    // abrir algo que se CORRERÍA lo enseña en su carpeta (como la página: localhost_front.EJECUTABLES)
    for n in ["instalar.command", "x.sh", "Algo.app", "s.py", "a.scpt", "w.webloc", "b.JAR"] { verdad(Resultado.correria(n), "se correría: \(n)") }
    for n in ["Minuta_v1.docx", "Tabla.xlsx", "Presentacion_v2.html", "notas.md", "foto.png", "sin-extension"] { verdad(!Resultado.correria(n), "se abre: \(n)") }
    igual(Resultado.nombreApp("/Applications/Safari.app"), "Safari", "el nombre de la app")
    igual(Resultado.nombreApp("/System/Applications/TextEdit.app/"), "TextEdit", "con diagonal al final")
    igual(Resultado.nombreApp(""), "", "sin app")
    igual(Resultado.pizarra, "com.workspace.monito.ensayo", "en ensayo se copia a una pizarra propia, no a la tuya")
}

@main
struct Pruebas {
    static func main() {
        zonas()
        umbral()
        plantillas()
        tarjeta()
        decision()
        recado()
        documento()
        candadoYFoto()
        resultados()
        if fallos.isEmpty {
            print("ok \(hechas)")
            exit(0)
        }
        print("FALLAN \(fallos.count) de \(hechas):")
        fallos.forEach { print("  " + $0) }
        exit(1)
    }
}
