// E1 · entregas en la burbuja: lo que se decide sin AppKit (se prueba suelto con Pruebas/PruebasEntregas.swift).
//
//   ZonaArrastre / Arrastre   dónde se puede tomar una entrega para arrastrarla a otra app, y cuándo un clic ya es
//                             arrastre (más de 4 pt): la app nativa arranca el arrastre (el WKWebView no puede soltar
//                             un archivo de verdad en Mail o en el Finder)
//   Propuesta                 la tarjeta de un encargo, ARMADA POR LA APP con datos del sistema: lo que escribió el
//                             socio en la burbuja (no lo que dijo el modelo), el archivo de verdad que tenía enfrente,
//                             la plantilla de una lista fija, lo que su conversación de trabajo puede hacer con el nivel
//                             de ESTE encargo (Fable v2: el suyo, no el de la página; subirlo es una casilla), quién lo
//                             lee y dónde queda
//   Decision                  lo que le contesta la herramienta `encargar` al agente según el clic del socio
//   Documento                 el archivo de verdad detrás de la ventana de enfrente (AXDocument), si se puede llevar
import Foundation
import CoreGraphics

struct ZonaArrastre: Equatable {
    var rect: CGRect          // en la página del monito (arriba-izquierda), en puntos
    var agente: String
    var ruta: String

    /// [[x, y, w, h, agente, ruta], …] (lo que manda la burbuja) → zonas válidas.
    static func leer(_ crudo: Any?) -> [ZonaArrastre] {
        guard let lista = crudo as? [[Any]] else { return [] }
        return lista.compactMap { z in
            guard z.count >= 6 else { return nil }
            let n = z.prefix(4).compactMap { ($0 as? NSNumber)?.doubleValue }
            guard n.count == 4, n[2] > 0, n[3] > 0, let a = z[4] as? String, let r = z[5] as? String,
                  !a.isEmpty, !r.isEmpty else { return nil }
            return ZonaArrastre(rect: CGRect(x: n[0], y: n[1], width: n[2], height: n[3]), agente: a, ruta: r)
        }
    }
}

enum Arrastre {
    /// Un clic que se mueve más que esto ya es arrastrar (como el del nido: 5 px en la página).
    static let umbral: CGFloat = 4

    static func empieza(desde a: CGPoint, ahora b: CGPoint) -> Bool {
        abs(b.x - a.x) + abs(b.y - a.y) > umbral
    }

    /// La zona bajo el punto (la de arriba si se enciman: la última que pintó la burbuja).
    static func zona(en p: CGPoint, _ zonas: [ZonaArrastre]) -> ZonaArrastre? {
        zonas.last { $0.rect.contains(p) }
    }

    /// La clave de una entrega conocida: el agente y su ruta (la que pidió la tarjeta).
    static func clave(_ agente: String, _ ruta: String) -> String { agente + "\u{1}" + ruta }
}

/// Los entregables de «Hazme un entregable ▾» (los mismos de encargos.PLANTILLAS).
enum Plantillas {
    static let todas: [(id: String, t: String, d: String)] = [
        ("resumen", "Resumen ejecutivo", "Word · 1 página"),
        ("presentacion", "Presentación", "PowerPoint · 5 láminas"),
        ("tabla", "Tabla limpia", "Excel · con totales y formato"),
        ("minuta", "Minuta con pendientes", "Word · quién, qué y cuándo"),
        ("correo", "Correo listo", "texto para copiar"),
    ]

    static func valida(_ id: String?) -> String {
        guard let id = id, todas.contains(where: { $0.id == id }) else { return "" }
        return id
    }

    static func titulo(_ id: String) -> String? {
        todas.first { $0.id == id }.map { $0.t + " (" + $0.d + ")" }
    }
}

/// Fable v2 §2.1: el recado de un encargo son TUS últimos mensajes de esa plática (solo los tuyos: nada del modelo ni
/// de la pantalla), no solo el último («sí, hazlo»). La tarjeta lo deja editar antes de «Encargar».
struct Recado: Equatable {
    static let cuantos = 3
    /// Una plática vieja ya no viaja (15 min desde tu último mensaje).
    static let vigencia: TimeInterval = 15 * 60
    /// Lo que cabe (encargos.MAX_PEDIDO): lo más nuevo se queda.
    static let tope = 1000
    private(set) var mensajes: [(texto: String, cuando: Date)] = []

    static func == (a: Recado, b: Recado) -> Bool { a.mensajes.map { $0.texto } == b.mensajes.map { $0.texto } }

    mutating func anotar(_ t: String, _ cuando: Date = Date()) {
        let x = t.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !x.isEmpty else { return }
        mensajes.append((x, cuando))
        if mensajes.count > Recado.cuantos { mensajes.removeFirst(mensajes.count - Recado.cuantos) }
    }

    mutating func vaciar() { mensajes = [] }

    /// Del más viejo al más nuevo, un renglón cada uno; "" si la plática ya es vieja.
    func texto(ahora: Date = Date()) -> String {
        guard let ultimo = mensajes.last, ahora.timeIntervalSince(ultimo.cuando) <= Recado.vigencia else { return "" }
        var t = mensajes.map { $0.texto }.joined(separator: "\n")
        if t.count > Recado.tope { t = String(t.suffix(Recado.tope)) }
        return t
    }
}

enum Propuesta {
    /// Lo que puede hacer su conversación de trabajo sin preguntarte con el nivel de su PÁGINA (Configuración →
    /// Permisos). No lo dice el modelo, y no calla nada: «Automático» corre comandos (Fable v2).
    static func puede(_ nivel: String) -> String {
        switch nivel {
        case "auto": return "correr comandos y cambiar archivos sin preguntarte (lo más arriesgado te lo pregunta)"
        case "preguntar": return "te pregunta antes de cambiar archivos y antes de correr comandos (te toco aquí cuando pregunte)"
        case "editar": return "cambiar archivos en su carpeta sin preguntarte; los comandos te los pregunta"
        case "sin_permisos": return "cambiar archivos y correr comandos sin preguntarte, solo en su carpeta y sin internet (el sandbox de su motor)"
        default: return "lo que tenga permitido en la página (Permisos)"
        }
    }

    /// El nivel de UN encargo (Fable v2): de fábrica, su carpeta y sus skills, sin comandos ni internet; cada casilla lo
    /// sube para ESTE encargo. `acotado`: Workspace lo cumple con su motor; si no, trabaja con el nivel de su página y
    /// solo sale si lo eliges. La burbuja arma «Puede» con estas piezas, que dicen la verdad.
    static let base = "leer y guardar solo en su carpeta de este encargo, y usar sus skills"
    static let sin = "sin comandos ni internet"
    static let conComandos = "correr comandos en tu Mac (un comando también puede usar internet)"
    static let conInternet = "buscar y leer páginas de internet"

    static func nivel(_ nivelPagina: String, motor: String, acotado: Bool) -> [String: Any] {
        if acotado {
            return ["acotado": true, "base": base, "sin": sin, "comandos": conComandos, "internet": conInternet,
                    "casillas": [["comandos", "También comandos (para Word, Excel o PowerPoint)"], ["internet", "También internet"]]]
        }
        let m = motor.isEmpty ? "su motor" : motor
        return ["acotado": false, "pagina": puede(nivelPagina),
                "aviso": "Con \(m), Workspace todavía no puede acotar un encargo: si lo encargas, trabaja con el nivel de su página.",
                "casillas": [["como_pagina", "Igual que en su página: " + puede(nivelPagina)]]]
    }

    /// «Puede» con lo de fábrica (sin casillas marcadas).
    static func puedeDeFabrica(_ n: [String: Any]) -> String {
        if (n["acotado"] as? Bool) == true { return base + "; " + sin }
        return (n["pagina"] as? String) ?? puede("")
    }

    /// «Lo lee»: el motor y dónde corre (lo que manda la app viaja a su proveedor).
    static func loLee(_ motor: String) -> [String] { [motor.isEmpty ? "su motor" : motor, "en la nube de su proveedor"] }

    /// El pedido, en una cita corta (lo que tú escribiste o el botón que apretaste).
    static func cita(_ s: String, tope: Int = 220) -> String {
        let t = s.split(whereSeparator: { $0 == "\n" || $0 == "\r" }).joined(separator: " ")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if t.count <= tope { return t }
        return String(t.prefix(tope - 1)) + "…"
    }

    /// La tarjeta (un diccionario que pinta la burbuja tal cual). `archivo`: (nombre, de dónde) del archivo de verdad;
    /// `leyo`: si en este turno el agente leyó tu pantalla.
    static func tarjeta(id: String, agente: String, nombre: String, pedido: String, titulo: String, plantilla: String,
                        archivo: (nombre: String, donde: String)?, nivel: String, motor: String = "", acotado: Bool = false,
                        leyo: Bool) -> [String: Any] {
        var filas: [[String]] = []
        let n = Propuesta.nivel(nivel, motor: motor, acotado: acotado)
        if let a = archivo { filas.append(["Lleva", a.nombre, "el archivo de verdad (" + a.donde + "), no la foto"]) }
        if let p = Plantillas.titulo(plantilla) { filas.append(["Usa", p, ""]) }
        filas.append(["Puede", puedeDeFabrica(n), ""])
        filas.append(["Lo lee"] + loLee(motor))
        filas.append(["Queda en", "su carpeta de entregas", "deliverables/, con versiones"])
        var d: [String: Any] = [
            "id": id, "agente": agente, "cab": "Encargo · con tu OK",
            "quien": "Encargar a \(nombre), en su conversación de trabajo:",
            "pedido": cita(pedido), "titulo": Texto.limpio(titulo, tope: 80) ?? "", "filas": filas,
            // Fable v2 §2.1: el recado entero (tus últimos mensajes, en renglones) y se edita en la tarjeta
            "pedido_completo": String(pedido.trimmingCharacters(in: .whitespacesAndNewlines).prefix(Recado.tope)), "editable": true,
            "botones": [["Encargar", "encargar", true], ["Mejor aquí, corto", "aqui", false], ["No", "no", false]],
            "nivel": n,
        ]
        if leyo { d["nota"] = "Lo que leyó de tu pantalla no viaja como orden: le llega lo que tú pediste." }
        if acotado, ["minuta", "resumen", "presentacion", "tabla"].contains(plantilla) {
            d["formato"] = "Sin comandos lo entrega en texto (.md); para el Office de verdad, marca «También comandos»."
        }
        return d
    }
}

enum Decision {
    /// Lo que la herramienta `encargar` le contesta al agente.
    static func texto(_ d: String, nombre: String = "") -> String {
        switch d {
        case "encargar":
            return "El socio lo encargó: tu conversación de trabajo ya lo tiene (con su archivo y su plantilla) y el monito "
                + "le avisa al terminar. Dile en una línea que te encargaste y que puede seguir con lo suyo."
        case "aqui":
            return "El socio prefirió que lo hagas aquí, corto: contéstale en 1 a 3 frases, sin archivos."
        case "no":
            return "El socio dijo que no. No lo hagas; pregúntale en una línea si quiere otra cosa."
        default:
            return "El socio todavía no decide: la tarjeta sigue en su burbuja. Si la aprieta, lo hace tu conversación de "
                + "trabajo y el monito le avisa. Contesta en una línea."
        }
    }
}

enum Documento {
    /// Lo más grande que se lleva (lo mismo que acepta Workspace para un adjunto).
    static let tope = 20 * 1024 * 1024

    /// La ruta del archivo detrás de un AXDocument («file:///Users/…/Ventas.xlsx»), si es un archivo de verdad.
    static func ruta(_ ax: String?) -> String? {
        guard let s = ax, let u = URL(string: s), u.isFileURL else { return nil }
        let p = u.standardizedFileURL.path
        return p.isEmpty || p == "/" ? nil : p
    }

    /// «~/Documents», «Escritorio»…: de dónde viene, para la tarjeta (sin la ruta entera).
    static func donde(_ ruta: String, casa: String) -> String {
        let carpeta = (ruta as NSString).deletingLastPathComponent
        if carpeta.hasPrefix(casa + "/") || carpeta == casa {
            return "~" + carpeta.dropFirst(casa.count)
        }
        return carpeta
    }
}

/// Lo que contesta cada botón de una entrega (WSMEntregas.hecho en la burbuja): qué pasó, si salió y de qué tarjeta.
/// Antes, un clic que la app no podía atender (no conocía el archivo, no había correo…) no decía nada.
enum Resultado {
    /// Pruebas de punta a punta (WORKSPACE_MONITO_SISTEMA=ensayo): la app no abre ventanas ni toca tu portapapeles; anota
    /// en su bitácora lo que habría hecho y contesta igual (con «ensayo»).
    static func ensayo(_ env: [String: String]) -> Bool { env["WORKSPACE_MONITO_SISTEMA"] == "ensayo" }

    /// En ensayo, copiar va a esta pizarra propia (y se lee de vuelta), nunca a la tuya.
    static let pizarra = "com.workspace.monito.ensayo"

    static func hecho(_ que: String, ok: Bool, agente: String, ruta: String, app: String = "", ensayo: Bool = false) -> [String: Any] {
        var d: [String: Any] = ["que": que, "ok": ok, "agente": agente, "ruta": ruta]
        if !app.isEmpty { d["app"] = app }
        if ensayo { d["ensayo"] = true }
        return d
    }

    /// Lo que el sistema CORRERÍA al abrirlo (la misma lista que la página: localhost_front.EJECUTABLES): «Abrir» lo
    /// enseña en su carpeta.
    static let ejecutables: Set<String> = [
        "app", "command", "tool", "terminal", "sh", "bash", "zsh", "csh", "ksh", "fish", "py", "pyw", "pl", "rb", "php",
        "jar", "pkg", "mpkg", "dmg", "workflow", "action", "scpt", "scptd", "applescript", "fileloc", "webloc", "inetloc",
        "url", "desktop", "exe", "com", "bat", "cmd", "ps1", "psm1", "vbs", "vbe", "js", "jse", "wsf", "wsh", "msi", "msp",
        "lnk", "scr", "hta", "reg", "cpl", "appimage", "run"]

    static func correria(_ nombre: String) -> Bool {
        let n = nombre.hasSuffix("/") ? String(nombre.dropLast()) : nombre
        let ext = (n as NSString).pathExtension.lowercased()
        return !ext.isEmpty && ejecutables.contains(ext)
    }

    /// «/Applications/Safari.app» → «Safari».
    static func nombreApp(_ ruta: String) -> String {
        let r = ruta.hasSuffix("/") ? String(ruta.dropLast()) : ruta
        guard !r.isEmpty else { return "" }
        let n = (r as NSString).lastPathComponent
        return n.hasSuffix(".app") ? String(n.dropLast(4)) : n
    }
}
