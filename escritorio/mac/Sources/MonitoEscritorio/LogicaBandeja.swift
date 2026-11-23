// La bandeja de fichas (Monito ronda 2 · bloque P), la parte que se prueba suelta (sin AppKit):
//   escritorio/mac/Pruebas/PruebasBandeja.swift, con Logica.swift y Seguridad.swift.
//
// Una ficha por pedido, todas en UNA bandeja pegada al monito (Bandeja.swift la pinta). Aquí vive:
//   · la ficha (FichaBandeja) y sus textos (TextoFicha): los arma la app con datos del portero (Seguridad.Ficha) o de la
//     página (la clase y el dato de un permiso de su motor). NUNCA con texto del agente: de un evento solo se leen
//     `clase`, `dato`, `opciones`, `nota` (de Workspace) e ids; cualquier frase que venga de más se ignora;
//   · la bandeja (Bandeja): llega una → se despliega; ~20 s sin tocarla → se dobla (queda el número y el puntito); las
//     del mismo tipo y bajo riesgo se juntan; tope visible de 3 y «ver todas»;
//   · «aprobar después» (Despues): la ficha guarda el pedido EXACTO de una acción del monito; el clic lo saca UNA vez y
//     solo si lo que se abriría sigue siendo lo mismo; lo que depende de la pantalla caduca;
//   · dónde va la bandeja (LugarBandeja), quién puede hacer cosas (PuedeActuar: una vez para todos, se apaga por
//     agente) y los ajustes chicos (el sonido, apagado de fábrica).
import CoreGraphics
import Foundation

enum TonoBandeja: String {
    /// te pregunta o te avisa · va a hacer algo que se deshace · sale de tu compu o no se deshace · ya quedó
    case lavanda, ambar, coral, menta
}

enum OrigenFicha: String {
    case portero, motor, aviso, oferta
}

enum EstadoFicha: String {
    /// espera tu clic y alguien (el agente) espera la respuesta · quedó para después (nadie espera) · ya pasó · hecho
    case esperando, despues, caducada, hecha
}

struct BotonFicha: Equatable {
    /// hazlo · permitir · permitir_turno · todas · sueltas · otra_vez · cerrar · si · olvidar
    var id: String
    var titulo: String
}

/// Un renglón de una ficha de trabajo (carril 6): un archivo, con lo que dice el sistema de él.
struct RenglonFicha: Equatable {
    var id: String
    /// «Ventas 2025.xlsx»
    var titulo: String
    /// «Documentos › Clientes · 21 nov 2026 · se abre con Excel»
    var detalle: String = ""
}

struct FichaBandeja: Equatable {
    var id: String
    var origen: OrigenFicha
    var tono: TonoBandeja
    var estado: EstadoFicha = .esperando
    var agente: String
    var nombre: String
    /// El color del agente (#rrggbb), para su puntito.
    var color: String = "#8b5cf6"
    /// Una frase con verbo: «Zenith quiere abrir YouTube».
    var titulo: String
    /// Lo que va a pasar, ENTERO (la dirección, la ruta, el comando). Es un dato: se pinta como dato.
    var detalle: String = ""
    /// url · ruta · app · comando · texto
    var detalleTipo: String = "texto"
    var sitio: String? = nil
    var leyo: String? = nil
    var puedeOlvidar = false
    var principal: BotonFicha
    var segundo: BotonFicha? = nil
    var conNo = true
    /// El texto simple de al lado del botón: «No» (o «Listo» en lo que ya quedó).
    var noTitulo = "No"
    var casilla: String? = nil
    var casillaMarcada = false
    var resaltarCasilla = false
    /// En letra chica: de quién viene («el portero del monito», «de su motor · Claude Code»).
    var pie: String = ""
    var armaMs = Tarjeta.armaMs
    var sostenerMs = 0
    var llego: Date
    /// Para juntar: la clase del permiso de su motor.
    var clase: String = ""
    /// Los ids de la página de un permiso de su motor (un grupo trae varios).
    var deMotor: [String] = []
    /// M-2 · un permiso de su motor cuyo dato no cabe entero: no se permite desde la ficha (lo que no se ve no se aprueba).
    var cortado = false
    /// Fichas de trabajo (carril 6). Con `elige`, cada renglón es un botón y tu toque ELIGE Y APRUEBA ese (su botón:
    /// «r:<id>»; no hay botón principal). Sin `elige`, son los renglones de UNA intención con un solo botón.
    var renglones: [RenglonFicha] = []
    var elige = false
    /// junto5 · lo que va a pasar, por partes con su etiqueta (un borrador de correo: Para · Asunto · Texto), cada una
    /// ENTERA. Si las trae, la ficha las pinta en vez de `detalle` (que sigue trayendo lo mismo, junto, para quien no sepa).
    var partes: [ParteFicha] = []

    /// Lo que la burbuja (y el chat grande del carril 3) necesita para pintarla: solo datos de la app.
    func json() -> [String: Any] {
        var d: [String: Any] = ["id": id, "origen": origen.rawValue, "tono": tono.rawValue, "estado": estado.rawValue,
                                "agente": agente, "nombre": nombre, "color": color, "titulo": titulo, "detalle": detalle,
                                "detalle_tipo": detalleTipo, "boton": principal.titulo, "boton_id": principal.id,
                                "con_no": conNo, "no": noTitulo, "pie": pie, "llego_s": llego.timeIntervalSince1970,
                                "sostener": sostenerMs > 0]
        if let s = sitio { d["sitio"] = s }
        if let l = leyo { d["leyo"] = l }
        if let s = segundo { d["segundo"] = s.titulo; d["segundo_id"] = s.id }
        if let c = casilla { d["casilla"] = c }
        if cortado { d["cortado"] = true }
        if !partes.isEmpty { d["partes"] = partes.map { ["e": $0.etiqueta, "v": $0.valor] } }
        if !renglones.isEmpty {
            d["renglones"] = renglones.map { ["id": $0.id, "titulo": $0.titulo, "detalle": $0.detalle] }
            d["elige"] = elige
        }
        return d
    }
}

/// Una parte de lo que va a pasar, con su etiqueta («Para», «Asunto», «Texto»). La etiqueta es de la app; el valor, el dato.
struct ParteFicha: Equatable {
    var etiqueta: String
    var valor: String
}

/// Un permiso de su motor, como lo da el puente (escritorio/fichas_motor.py): la clase y el dato del pedido.
struct PermisoMotor: Equatable {
    var id: String
    var clase: String
    var dato: String
    var opciones: [String] = ["permitir", "negar"]
    /// M-2 · el dato (el comando, lo que manda la herramienta) NO cabe entero en la ficha.
    var cortado = false
    var nota: String = ""
    var pedido: Date? = nil

    static let clases: Set<String> = ["comando", "crear", "cambiar", "borrar", "leer", "buscar", "pagina", "internet", "otra"]
    /// Lo que solo lee o busca: se junta cuando hay varias («Atlas quiere leer 4 páginas»).
    static let bajoRiesgo: Set<String> = ["leer", "buscar", "pagina", "internet"]
    static let topeDato = 600

    /// Un renglón del evento → el permiso. Solo se leen `id`, `clase`, `dato`, `opciones`, `nota` y `pedido`: una frase
    /// que venga de más («texto», «titulo»…) no se usa.
    static func de(_ o: [String: Any]) -> PermisoMotor? {
        guard let id = (o["id"] as? String).flatMap({ Texto.limpio($0, tope: 200) }), !id.isEmpty else { return nil }
        let c = (o["clase"] as? String) ?? "otra"
        var p = PermisoMotor(id: id, clase: clases.contains(c) ? c : "otra",
                             dato: Texto.limpio(o["dato"] as? String, tope: topeDato) ?? "")
        // M-2 · el dato no cabe entero (lo dice el puente, o lo corta la app aquí): la ficha lo dice y no deja permitirlo
        let crudo = (o["dato"] as? String) ?? ""
        p.cortado = (o["cortado"] as? Bool) == true || crudo.count > topeDato
        let ops = ((o["opciones"] as? [String]) ?? []).filter { ["permitir", "permitir_turno", "negar"].contains($0) }
        if !ops.isEmpty { p.opciones = ops }
        p.nota = Texto.limpio(o["nota"] as? String, tope: 240) ?? ""
        if let t = (o["pedido"] as? NSNumber)?.doubleValue, t > 0 { p.pedido = Date(timeIntervalSince1970: t) }
        return p
    }

    /// El evento «fichas» de un agente → (agente, motor, los que esperan, los que quedaron para después).
    static func evento(_ o: [String: Any]) -> (agente: String, motor: String, esperan: [PermisoMotor], despues: [PermisoMotor], interrumpidos: Int)? {
        guard (o["t"] as? String) == "fichas", let a = (o["agente"] as? String).flatMap({ Texto.limpio($0, tope: 80) }) else { return nil }
        func lista(_ k: String) -> [PermisoMotor] { ((o[k] as? [[String: Any]]) ?? []).prefix(40).compactMap(PermisoMotor.de) }
        let cortados = max(0, min(99, (o["interrumpidos"] as? NSNumber)?.intValue ?? 0))
        return (a, Texto.limpio(o["motor"] as? String, tope: 40) ?? "", lista("esperan"), lista("despues"), cortados)
    }
}

/// Los textos de las fichas: catálogos fijos de la app. Lo único que no es de la app es el DATO (la dirección, el
/// comando…), que va en `detalle` y nunca en el título.
enum TextoFicha {
    static let pieMotor = "de su motor"
    static let piePortero = "el portero de Compañero"

    /// «quiere …» / «quería …», por clase del permiso de su motor.
    static let frases: [String: String] = [
        "comando": "correr un comando", "crear": "crear un archivo", "cambiar": "cambiar un archivo",
        "borrar": "borrar un archivo", "leer": "leer un archivo", "buscar": "buscar en sus archivos",
        "pagina": "leer una página de internet", "internet": "buscar en internet", "otra": "usar una de sus herramientas",
    ]
    /// Varias juntas: «leer 4 páginas».
    static func varias(_ clase: String, _ n: Int) -> String {
        switch clase {
        case "leer": return "leer \(n) archivos"
        case "buscar": return "hacer \(n) búsquedas en sus archivos"
        case "pagina": return "leer \(n) páginas de internet"
        case "internet": return "hacer \(n) búsquedas en internet"
        default: return "hacer \(n) cosas"
        }
    }

    /// El tono de un permiso de su motor: lo que solo lee, lavanda si ya nadie espera y ámbar si espera; crear y cambiar,
    /// ámbar; un comando, borrar o una herramienta que no conozco, coral (no sé si se deshace).
    static func tono(_ clase: String, despues: Bool) -> TonoBandeja {
        if PermisoMotor.bajoRiesgo.contains(clase) { return despues ? .lavanda : .ambar }
        if clase == "crear" || clase == "cambiar" { return .ambar }
        return .coral
    }

    static func tipoDeDato(_ clase: String) -> String {
        switch clase {
        case "pagina": return "url"
        case "comando": return "comando"
        case "crear", "cambiar", "borrar", "leer": return "ruta"
        default: return "texto"
        }
    }

    static func nombreLimpio(_ n: String, _ id: String) -> String { Texto.limpio(n, tope: 40) ?? (Texto.limpio(id, tope: 40) ?? "Tu agente") }

    /// La ficha de un permiso de su motor (espera) o de uno que quedó para después.
    static func deMotor(_ p: PermisoMotor, agente: String, nombre: String, color: String, motor: String, despues: Bool, ahora: Date) -> FichaBandeja {
        let n = nombreLimpio(nombre, agente)
        let frase = frases[p.clase] ?? frases["otra"]!
        var f = FichaBandeja(id: (despues ? "md:" : "m:") + agente + ":" + p.id, origen: .motor, tono: tono(p.clase, despues: despues),
                             estado: despues ? .despues : .esperando, agente: agente, nombre: n, color: color,
                             titulo: "\(n) \(despues ? "quería" : "quiere") \(frase)",
                             principal: BotonFicha(id: despues ? "despues" : "permitir", titulo: despues ? "Permitir y seguir" : "Permitir"),
                             llego: p.pedido ?? ahora)
        f.detalle = p.dato
        f.detalleTipo = tipoDeDato(p.clase)
        if f.detalleTipo == "url" { f.sitio = Destino.host(p.dato) }
        f.clase = p.clase
        f.deMotor = [p.id]
        f.pie = pieMotor + (motor.isEmpty ? "" : " · " + motor) + (despues ? " · un solo uso" : "")
        if p.cortado {
            // M-2 · lo que no se ve entero no se aprueba aquí: solo «No». Para permitirlo, se ve completo en la página.
            f.cortado = true
            f.tono = .coral
            f.detalle = p.dato + " …"
            f.principal = BotonFicha(id: "no", titulo: despues ? "Descartar" : "No permitir")
            f.conNo = false
            f.pie = "No cabe entero aquí: para permitirlo, velo completo en la página de Workspace · " + f.pie
            return f
        }
        if !despues, p.opciones.contains("permitir_turno") {
            f.segundo = BotonFicha(id: "permitir_turno", titulo: "Sí, y lo demás de esa carpeta")
            if !p.nota.isEmpty { f.pie += " · " + p.nota }
        }
        return f
    }

    /// Varias del mismo tipo y bajo riesgo, juntas: «Atlas quiere leer 4 páginas · [Permitir las 4] [Ver una por una]».
    static func grupo(_ fs: [FichaBandeja], clave: String) -> FichaBandeja {
        let p = fs[0], n = fs.count, despues = p.estado == .despues
        var g = FichaBandeja(id: "g:" + clave, origen: .motor, tono: p.tono, estado: p.estado, agente: p.agente, nombre: p.nombre,
                             color: p.color, titulo: "\(p.nombre) \(despues ? "quería" : "quiere") \(varias(p.clase, n))",
                             principal: BotonFicha(id: "todas", titulo: "Permitir las \(n)" + (despues ? " y seguir" : "")),
                             llego: fs.map { $0.llego }.min() ?? p.llego)
        g.segundo = BotonFicha(id: "sueltas", titulo: "Ver una por una")
        g.conNo = false                       // «No» está en cada una («Ver una por una»)
        g.detalle = fs.map { $0.detalle }.filter { !$0.isEmpty }.joined(separator: "\n")      // todas, enteras
        g.detalleTipo = "lista"
        g.clase = p.clase
        g.deMotor = fs.flatMap { $0.deMotor }
        g.pie = p.pie
        return g
    }

    /// El botón de una ficha del portero, por lo que haría.
    static func boton(_ f: Ficha) -> String {
        let b: String
        switch f.detalleTipo {
        case "finder": b = "Enseñar"
        case "url", "ruta", "carpeta", "app": b = "Abrir"
        default: b = "Hacerlo"
        }
        return f.sostenerMs > 0 ? "Mantén para \(b.lowercased())" : b
    }

    /// La ficha de una acción del monito, con el veredicto del portero (CONTRATO_PORTERO_FICHAS.md).
    static func dePortero(_ f: Ficha, nombre: String, color: String, ahora: Date) -> FichaBandeja {
        var b = FichaBandeja(id: "p:" + f.id, origen: .portero, tono: f.tono == .coral ? .coral : .ambar, agente: f.agente,
                             nombre: nombreLimpio(nombre, f.agente), color: color, titulo: f.titulo,
                             principal: BotonFicha(id: "hazlo", titulo: boton(f)), llego: ahora)
        b.detalle = f.detalle
        // (un borrador de correo, carril 6: Para, Asunto y el texto, enteros, como texto)
        b.detalleTipo = f.detalleTipo == "url" ? "url" : (f.detalleTipo == "app" ? "app"
            : (f.detalleTipo == "elemento" || f.detalleTipo == "correo" ? "texto" : "ruta"))
        b.sitio = f.sitio
        if f.detalleTipo == "correo" { b.partes = partesCorreo(f.detalle) }      // junto5: Para · Asunto · Texto, cada uno en su renglón
        if let l = f.leyo { b.leyo = "leyó: " + l }
        b.puedeOlvidar = f.puedeOlvidar
        // lo coral nunca trae casilla (aunque alguien se la pusiera al veredicto)
        if b.tono != .coral, f.recordable != nil, let t = f.recordarTexto { b.casilla = t; b.resaltarCasilla = f.ofrecerRecordar }
        b.pie = piePortero + (f.motivo.isEmpty || b.tono != .coral ? "" : " · " + f.motivo)
        b.armaMs = max(f.armaMs, Tarjeta.armaMs)
        b.sostenerMs = f.sostenerMs
        return b
    }

    /// El detalle de un borrador («Para: …\nAsunto: …\n\n<texto>», como lo arma el portero: ArmarFicha) en sus tres partes.
    /// Las direcciones y el asunto no llevan renglones (Borrador los revisa), así que el corte no tiene pierde. Si el
    /// detalle no tiene esa forma, ninguna parte (la ficha enseña el detalle entero, como antes).
    static func partesCorreo(_ detalle: String) -> [ParteFicha] {
        let lineas = detalle.split(separator: "\n", maxSplits: 3, omittingEmptySubsequences: false).map(String.init)
        guard lineas.count >= 2, lineas[0].hasPrefix("Para: "), lineas[1].hasPrefix("Asunto: ") else { return [] }
        guard lineas.count == 2 || lineas[2].isEmpty else { return [] }
        return [ParteFicha(etiqueta: "Para", valor: String(lineas[0].dropFirst("Para: ".count))),
                ParteFicha(etiqueta: "Asunto", valor: String(lineas[1].dropFirst("Asunto: ".count))),
                ParteFicha(etiqueta: "Texto", valor: lineas.count > 3 ? lineas[3] : "")]
    }

    /// Lo que escribiría (lo único que viene del modelo): se enseña ENTERO y como dato, entre comillas, bajo el detalle.
    static func conValores(_ b: FichaBandeja, _ valores: [(campo: String, valor: String)]) -> FichaBandeja {
        guard !valores.isEmpty else { return b }
        var x = b
        let lineas = valores.map { ($0.campo.isEmpty ? "" : $0.campo + ": ") + "«" + $0.valor + "»" }
        x.detalle = ([b.detalle] + lineas).filter { !$0.isEmpty }.joined(separator: "\n")
        return x
    }

    /// La misma, cuando ya nadie espera (no estabas): «Zenith quería abrir YouTube · [Abrir]».
    static func despues(_ b: FichaBandeja, _ f: Ficha) -> FichaBandeja {
        var x = b
        x.estado = .despues
        x.titulo = "\(b.nombre) quería \(f.verbo) \(f.objeto)"
        x.pie = piePortero + " · lo hago yo directo, sin despertar a \(b.nombre)"
        x.casilla = nil                    // «no me preguntes» se decide con el agente esperando, no después
        return x
    }

    /// Lo que dependía de la pantalla: «Ya pasó · [Pedírselo otra vez]».
    static func caducada(_ b: FichaBandeja, motivo: String = "") -> FichaBandeja {
        var x = b
        x.estado = .caducada
        x.tono = .ambar
        x.titulo = "Ya pasó"
        x.detalle = b.titulo                 // el título de SU ficha (de la app), ahora como lo que era
        x.detalleTipo = "texto"
        x.sitio = nil
        x.leyo = nil
        x.principal = BotonFicha(id: "otra_vez", titulo: "Pedírselo otra vez")
        x.segundo = nil
        x.casilla = nil
        x.sostenerMs = 0
        x.conNo = true
        x.pie = motivo.isEmpty ? "lo que había en pantalla ya cambió" : motivo
        return x
    }

    /// La primera vez (E5): UNA ficha que prende «hacer cosas en mi Mac» y hace lo pedido. La casilla viene marcada:
    /// una vez para todos tus agentes (E3-b); se apaga por agente en el menú.
    static func primera(_ f: Ficha, nombre: String, color: String, ahora: Date) -> FichaBandeja {
        var b = dePortero(f, nombre: nombre, color: color, ahora: ahora)
        b.titulo = "¿Dejo que \(b.nombre) abra cosas en tu Mac? Empiezo con \(f.objeto)"
        b.principal = BotonFicha(id: "hazlo", titulo: f.sostenerMs > 0 ? "Mantén para decir que sí" : "Sí")
        b.casilla = "Para todos mis agentes"
        b.casillaMarcada = true
        b.resaltarCasilla = false
        b.pie = "Te pregunta antes de cada cosa · se apaga en el menú de Compañero"
        return b
    }

    /// «Abrí YouTube · [Cerrar]» (lo que ya hizo). `texto`: el aviso de la app (AvisoAbrir), no del agente.
    static func hecho(id: String, texto: String, agente: String, nombre: String, color: String, deshacer: String?, ahora: Date) -> FichaBandeja {
        var b = FichaBandeja(id: "h:" + id, origen: .aviso, tono: .menta, estado: .hecha, agente: agente,
                             nombre: nombreLimpio(nombre, agente), color: color, titulo: texto,
                             principal: BotonFicha(id: "cerrar", titulo: "Cerrar"), llego: ahora)
        // lo que se deshace: su botón lo cierra («Cerrar Calculadora») y «Listo» quita la ficha; si no, [Cerrar] la quita
        if let d = deshacer { b.principal = BotonFicha(id: "deshacer", titulo: d); b.noTitulo = "Listo" }
        b.conNo = deshacer != nil
        b.armaMs = 0
        return b
    }

    /// Las dos fichas de trabajo (carril 6 · CONTRATO_BANDEJA_PIDE_CARRIL6.md). `elegir`: «¿Cuál abro?» y cada archivo es
    /// un botón (tu toque elige y aprueba). Si no: una intención = una ficha, con sus renglones y UN botón («Abrir los 2»).
    /// El título y los renglones los arma la app con lo que dice el sistema; siempre ámbar (lo coral va una por una).
    static func deTrabajo(id: String, elegir: Bool, titulo: String, boton: String, renglones: [RenglonFicha], agente: String,
                          nombre: String, color: String, armaMs: Int = Tarjeta.armaMs, ahora: Date) -> FichaBandeja {
        var b = FichaBandeja(id: "w:" + id, origen: .portero, tono: .ambar, agente: agente, nombre: nombreLimpio(nombre, agente),
                             color: color, titulo: Texto.limpio(titulo, tope: 160) ?? "¿Cuál abro?",
                             principal: BotonFicha(id: elegir ? "" : "todos", titulo: elegir ? "" : (Texto.limpio(boton, tope: 40) ?? "Abrir")),
                             llego: ahora)
        b.renglones = renglones
        b.elige = elegir
        b.noTitulo = elegir ? "Ninguno" : "No"
        b.pie = piePortero + " · se abren detrás de tu ventana"
        b.armaMs = max(armaMs, Tarjeta.armaMs)
        return b
    }

    /// junto5 · la primera vez con una ficha de trabajo (E5): la MISMA ficha prende «hacer cosas en mi Mac» y abre lo
    /// que toques. La casilla viene marcada (una vez para todos tus agentes), como en `primera`.
    static func primeraDeTrabajo(_ b: FichaBandeja) -> FichaBandeja {
        var x = b
        x.titulo = b.elige ? "¿Dejo que \(b.nombre) abra cosas en tu Mac? Elige con cuál empiezo"
                           : "¿Dejo que \(b.nombre) abra cosas en tu Mac? Empiezo con estos \(b.renglones.count)"
        x.casilla = "Para todos mis agentes"
        x.casillaMarcada = true
        x.resaltarCasilla = false
        x.pie = "Te pregunta antes de cada cosa · se apaga en el menú de Compañero"
        return x
    }

    /// junto5 · la misma ficha de trabajo cuando ya nadie espera (no estabas, o se acabó su turno): se queda, con sus
    /// renglones. Tu toque lo hace la app directo, sin despertar al agente.
    static func trabajoDespues(_ b: FichaBandeja, ahora: Date) -> FichaBandeja {
        var x = b
        x.estado = .despues
        let n = b.renglones.count
        x.titulo = b.elige ? "\(b.nombre) quería abrir uno de estos. ¿Cuál abro?" : "\(b.nombre) quería abrir estos \(n) archivos"
        x.casilla = nil
        x.pie = piePortero + " · lo hago yo directo, sin despertar a \(b.nombre)"
        x.llego = ahora                       // se vuelve a armar (0.6 s) al quedarse
        return x
    }

    /// Lo que cortó un reinicio de la página (E9): no fue un «no» tuyo; se le puede pedir otra vez.
    static func interrumpida(_ n: Int, agente: String, nombre: String, color: String, ahora: Date) -> FichaBandeja {
        let quien = nombreLimpio(nombre, agente)
        var b = FichaBandeja(id: "mi:" + agente, origen: .motor, tono: .lavanda, estado: .caducada, agente: agente, nombre: quien,
                             color: color, titulo: n == 1 ? "Workspace se reinició y un permiso de \(quien) quedó sin contestar"
                                : "Workspace se reinició y \(n) permisos de \(quien) quedaron sin contestar",
                             principal: BotonFicha(id: "otra_vez", titulo: "Pedírselo otra vez"), llego: ahora)
        b.pie = "no fue un «no» tuyo"
        return b
    }

    /// «Atlas te pregunta · [Contestar]»: la pregunta misma (texto del agente) NO va en la ficha; se contesta en su burbuja.
    static func pregunta(agente: String, nombre: String, color: String, ahora: Date) -> FichaBandeja {
        var b = FichaBandeja(id: "q:" + agente, origen: .aviso, tono: .lavanda, agente: agente, nombre: nombreLimpio(nombre, agente),
                             color: color, titulo: "\(nombreLimpio(nombre, agente)) te pregunta",
                             principal: BotonFicha(id: "contestar", titulo: "Contestar"), llego: ahora)
        b.noTitulo = "Luego"
        b.pie = "su pregunta está en su burbuja"
        b.armaMs = 0
        return b
    }

    /// Al tercer OK del mismo tipo: «Ya van 3. ¿Dejo de preguntarte para abrir apps?».
    static func oferta(_ t: TipoRecordado, agente: String, nombre: String, color: String, ahora: Date) -> FichaBandeja {
        var b = FichaBandeja(id: "o:" + t.rawValue, origen: .oferta, tono: .lavanda, agente: agente,
                             nombre: nombreLimpio(nombre, agente), color: color, titulo: t.pregunta,
                             principal: BotonFicha(id: "si", titulo: "Sí"), llego: ahora)
        b.pie = "Lo quitas en el menú de Compañero: «Lo que hace sin preguntar»"
        return b
    }

    /// Lo que se le manda al agente con «Pedírselo otra vez» (lo arma la app con el título de SU ficha).
    static func otraVez(_ b: FichaBandeja) -> String {
        b.id.hasPrefix("mi:")
            ? "Ya volví. Lo que quedó sin contestar por el reinicio: si todavía hace falta, vuelve a pedírmelo."
            : "Ya volví. Lo que pediste antes ya pasó (lo que había en mi pantalla cambió): si todavía hace falta, vuelve a pedírmelo."
    }
}

/// La bandeja: qué fichas hay, si está doblada y qué se ve.
struct Bandeja {
    /// Sin tocarla este rato, se dobla (queda el número en el monito y el puntito en su carita de la barra de menú).
    static let plegarA: TimeInterval = 20
    /// Lo más que se ve a la vez; lo demás, «ver todas».
    static let tope = 3
    /// «Abrí YouTube · [Cerrar]» se va sola.
    static let hechaSeVa: TimeInterval = 12
    /// M-1 · «Ya pasó · [Pedírselo otra vez]» tampoco se queda para siempre: a los 15 min se va sola. («Para después» NO
    /// se va: guarda algo que dijiste que verías.)
    static let caducadaSeVa: TimeInterval = 900
    /// Desde cuándo está caducada cada una (su rato cuenta desde que caducó, no desde que llegó).
    private var caduco: [String: Date] = [:]

    /// M-1 · qué tan arriba va: primero lo que tiene a un agente ESPERANDO tu clic, luego lo de después, luego lo que
    /// ya pasó y al final lo que ya quedó. Así una ficha nueva nunca cae detrás de «Ver todas» por culpa de las viejas.
    static func urgencia(_ e: EstadoFicha) -> Int {
        switch e {
        case .esperando: return 0
        case .despues: return 1
        case .caducada: return 2
        case .hecha: return 3
        }
    }

    enum Llegada: Equatable { case nueva, cambio, igual }

    private(set) var fichas: [FichaBandeja] = []
    private(set) var plegada = true
    private(set) var tocada = Date.distantPast
    var verTodas = false
    /// Los grupos que pediste ver «una por una».
    private(set) var sueltos: Set<String> = []

    func ficha(_ id: String) -> FichaBandeja? { fichas.first { $0.id == id } }

    /// Las que esperan tu clic (lo que ya quedó no cuenta).
    var cuenta: Int { fichas.filter { $0.estado != .hecha }.count }
    /// Doblada con algo pendiente: el puntito en la carita de la barra de menú.
    var punto: Bool { plegada && cuenta > 0 }
    var vacia: Bool { fichas.isEmpty }

    /// Llega (o cambia) una ficha. Una nueva despliega la bandeja y cuenta como «tocada» (sus 20 s empiezan).
    @discardableResult
    mutating func poner(_ f: FichaBandeja, ahora: Date) -> Llegada {
        if f.estado == .caducada { if caduco[f.id] == nil { caduco[f.id] = ahora } } else { caduco[f.id] = nil }
        if let i = fichas.firstIndex(where: { $0.id == f.id }) {
            if fichas[i] == f { return .igual }
            var x = f
            x.llego = fichas[i].llego
            if fichas[i] == x { return .igual }
            fichas[i] = x
            return .cambio
        }
        fichas.append(f)
        plegada = false
        tocada = ahora
        return .nueva
    }

    @discardableResult
    mutating func quitar(_ id: String) -> FichaBandeja? {
        guard let i = fichas.firstIndex(where: { $0.id == id }) else { return nil }
        let f = fichas.remove(at: i)
        caduco[id] = nil
        if fichas.count <= Bandeja.tope { verTodas = false }
        return f
    }

    /// Los permisos de su motor de UN agente, como están ahora (la foto de la página manda): las que ya no vienen se
    /// van; las nuevas llegan. → cuántas nuevas.
    @discardableResult
    mutating func ponerDeMotor(agente: String, _ nuevas: [FichaBandeja], ahora: Date) -> Int {
        let ids = Set(nuevas.map { $0.id })
        fichas.removeAll { $0.origen == .motor && $0.agente == agente && !ids.contains($0.id) }
        var n = 0
        for f in nuevas where poner(f, ahora: ahora) == .nueva { n += 1 }
        if fichas.count <= Bandeja.tope { verTodas = false }
        return n
    }

    /// El ratón encima o un clic: no se dobla mientras la usas.
    mutating func tocar(ahora: Date) { tocada = ahora }

    /// Un clic en el monito con algo pendiente: se despliega (NO cancela nada). → false si no había nada que enseñar.
    mutating func desplegar(ahora: Date) -> Bool {
        guard !fichas.isEmpty else { return false }
        plegada = false
        tocada = ahora
        return true
    }

    mutating func plegar() { plegada = true; verTodas = false }

    mutating func soltar(_ clave: String) { sueltos.insert(clave) }

    /// Cada rato: lo hecho se va solo y, sin tocarla 20 s, se dobla. → true si algo cambió.
    mutating func tic(ahora: Date) -> Bool {
        var cambio = false
        let antes = fichas.count
        fichas.removeAll { $0.estado == .hecha && ahora.timeIntervalSince($0.llego) >= Bandeja.hechaSeVa }
        fichas.removeAll { $0.estado == .caducada && ahora.timeIntervalSince(caduco[$0.id] ?? $0.llego) >= Bandeja.caducadaSeVa }
        if fichas.count != antes { cambio = true; caduco = caduco.filter { k, _ in fichas.contains { $0.id == k } } }
        if fichas.isEmpty { if !plegada { plegada = true; cambio = true }; verTodas = false; return cambio }
        if !plegada, ahora.timeIntervalSince(tocada) >= Bandeja.plegarA { plegar(); cambio = true }
        return cambio
    }

    static func claveGrupo(_ f: FichaBandeja) -> String? {
        guard f.origen == .motor, !f.cortado, PermisoMotor.bajoRiesgo.contains(f.clase), f.estado == .esperando || f.estado == .despues else { return nil }
        return f.agente + "|" + f.clase + "|" + f.estado.rawValue
    }

    /// Lo que se pinta: las del mismo tipo y bajo riesgo juntas, ORDENADAS por lo que te necesita ahora (M-1: esperando,
    /// la más nueva arriba; luego después, ya pasó y hecho, en su orden de llegada), y el tope de 3.
    func vista() -> (tarjetas: [FichaBandeja], ocultas: Int) {
        var grupos: [String: [FichaBandeja]] = [:]
        for f in fichas { if let k = Bandeja.claveGrupo(f), !sueltos.contains(k) { grupos[k, default: []].append(f) } }
        var out: [FichaBandeja] = [], hechos: Set<String> = []
        for f in fichas {
            if let k = Bandeja.claveGrupo(f), let g = grupos[k], g.count >= 2 {
                if hechos.insert(k).inserted { out.append(TextoFicha.grupo(g, clave: k)) }
            } else { out.append(f) }
        }
        out = out.enumerated().sorted { a, b in
            let ua = Bandeja.urgencia(a.element.estado), ub = Bandeja.urgencia(b.element.estado)
            if ua != ub { return ua < ub }
            if ua == 0, a.element.llego != b.element.llego { return a.element.llego > b.element.llego }
            return a.offset < b.offset
        }.map { $0.element }
        if verTodas || out.count <= Bandeja.tope { return (out, 0) }
        return (Array(out.prefix(Bandeja.tope)), out.count - Bandeja.tope)
    }

    /// Los miembros de una ficha (ella misma, o las de su grupo).
    func miembros(_ id: String) -> [FichaBandeja] {
        if id.hasPrefix("g:") {
            let k = String(id.dropFirst(2))
            return fichas.filter { Bandeja.claveGrupo($0) == k }
        }
        return ficha(id).map { [$0] } ?? []
    }
}

/// «Aprobar después» una acción del monito: la ficha guarda el pedido EXACTO y lo que se abriría (su huella). Tu clic
/// lo saca UNA vez; si lo que se abriría ya no es lo mismo, o dependía de la pantalla, ya pasó.
struct PedidoGuardado: Equatable {
    var pedido: PedidoAccion
    var huellas: [Huella]
    var agente: String
    var tono: TonoBandeja
    var guardado: Date
    /// junto5 (pedido del portero) · un borrador de correo se guarda SIN su sello: solo para, asunto y texto. Al aprobarlo
    /// después vuelve a entrar por la puerta de siempre (Trabajo.pedidoDeCorreo → Borrador.sellado), que lo arma, lo
    /// revisa y lo sella de nuevo. El pedido guardado, solo, es un mailto crudo: el portero le dice que no.
    var correo: CorreoGuardado? = nil
    /// M-5 · lo pidió el SOCIO (su clic en «Abrir» de un enlace del chat), no el agente con sus manos.
    var delSocio = false
}

struct CorreoGuardado: Equatable {
    var para: [String]
    var asunto: String
    var texto: String
    var argumentos: [String: Any] { ["para": para, "asunto": asunto, "texto": texto] }
}

struct Despues {
    enum Toma: Equatable {
        case hazlo(PedidoGuardado)
        case yaPaso(String)
        case noEsta
    }

    private var guardados: [String: PedidoGuardado] = [:]
    var cuantos: Int { guardados.count }

    /// ¿El pedido depende de lo que había en pantalla? Todo menos abrir una app, una ruta o una dirección dichas enteras.
    static func dependeDePantalla(_ p: PedidoAccion) -> Bool {
        guard p.tipoConocido == .abrir else { return true }
        if p.seleccionado || p.elemento != nil || p.texto != nil { return true }
        if let r = p.ruta, !(r.hasPrefix("/") || r.hasPrefix("~")) { return true }      // «informe.pdf» en la carpeta de enfrente
        return p.url == nil && p.app == nil && p.ruta == nil
    }

    /// → false si no se puede guardar (depende de la pantalla): esa ficha caduca.
    @discardableResult
    mutating func guardar(_ id: String, _ g: PedidoGuardado) -> Bool {
        guard !Despues.dependeDePantalla(g.pedido), !g.huellas.isEmpty else { return false }
        var g = g
        if g.pedido.borrador || g.correo != nil {
            // el sello nunca se guarda: quedan sus tres datos, y el pedido sin marca de borrador
            guard let b = g.correo.map({ Borrador(para: $0.para, asunto: $0.asunto, texto: $0.texto) }) ?? Borrador.de(g.pedido.url ?? "") else { return false }
            g.correo = CorreoGuardado(para: b.para, asunto: b.asunto, texto: b.texto)
            g.pedido.borrador = false
        }
        guardados[id] = g
        return true
    }

    func tiene(_ id: String) -> Bool { guardados[id] != nil }

    /// Tu clic: el pedido sale UNA vez (la segunda, `noEsta`). `ahora`: lo que se abriría hoy; si cambió, ya pasó.
    mutating func tomar(_ id: String, ahora: [Huella]) -> Toma {
        guard let g = guardados.removeValue(forKey: id) else { return .noEsta }
        if let c = Huella.cambioLote(g.huellas, ahora) { return .yaPaso(c) }
        return .hazlo(g)
    }

    mutating func olvidar(_ id: String) { guardados[id] = nil }
}

/// Dónde va la bandeja: pegada al monito, siempre en el mismo lugar (arriba de su nido, alineada con él). Si ahí está
/// su burbuja abierta, a su lado (del lado del centro de la pantalla). Todo en coordenadas de AppKit.
enum LugarBandeja {
    static let hueco: CGFloat = 10

    static func marco(tam: CGSize, nido n: CGRect, lado l: Lado, ocupado: CGRect?, visible vf: CGRect) -> CGRect {
        var x = l.h == "der" ? n.maxX - tam.width : n.minX
        var y = l.v == "abajo" ? n.maxY + hueco : n.minY - hueco - tam.height
        var f = CGRect(x: x, y: y, width: tam.width, height: tam.height)
        if let o = ocupado, o.intersects(f) {
            x = l.h == "der" ? o.minX - hueco - tam.width : o.maxX + hueco
            y = l.v == "abajo" ? n.minY : n.maxY - tam.height
            f.origin = CGPoint(x: x, y: y)
        }
        f.origin.x = min(max(f.minX, vf.minX + 4), max(vf.minX + 4, vf.maxX - tam.width - 4))
        f.origin.y = min(max(f.minY, vf.minY + 4), max(vf.minY + 4, vf.maxY - tam.height - 4))
        return f
    }
}

/// «Puede hacer cosas en mi Mac» (E3-b): se prende UNA vez para todos tus agentes y se apaga por agente. Lo que ya
/// habías prendido agente por agente sigue valiendo para esos (y para nadie más).
struct PuedeActuar: Equatable {
    var todos = false
    var solo: Set<String> = []
    var apagados: Set<String> = []

    func puede(_ a: String) -> Bool { !a.isEmpty && !apagados.contains(a) && (todos || solo.contains(a)) }
    var alguno: Bool { todos || !solo.subtracting(apagados).isEmpty }
    /// ¿El socio lo apagó para este agente a propósito? (no se le vuelve a ofrecer la ficha de prender)
    func apagado(_ a: String) -> Bool { apagados.contains(a) }

    mutating func prender(_ a: String, paraTodos: Bool) {
        if paraTodos { todos = true }
        if !a.isEmpty { solo.insert(a); apagados.remove(a) }
    }

    mutating func apagar(_ a: String) {
        solo.remove(a)
        if todos { apagados.insert(a) }
    }

    mutating func apagarParaTodos() { todos = false; solo = []; apagados = [] }

    /// Para manos.json: los agentes a los que sus manos les ofrecen `actuar` de verdad.
    func lista(conocidos: [String]) -> [String] {
        (todos ? Set(conocidos).union(solo) : solo).subtracting(apagados).sorted()
    }

    /// De ajustes.json: {"actuar_todos": true, "agentes": {id: {"actuar": "si"|"no"}}}.
    static func deJSON(_ o: [String: Any]) -> PuedeActuar {
        var p = PuedeActuar()
        p.todos = (o["actuar_todos"] as? Bool) == true
        for (k, v) in (o["agentes"] as? [String: [String: String]]) ?? [:] where !k.isEmpty {
            if v["actuar"] == "si" { p.solo.insert(k) }
            if v["actuar"] == "no" { p.apagados.insert(k) }
        }
        return p
    }
}

/// Los ajustes chicos de la bandeja (ajustes.json). El sonido suave, APAGADO de fábrica (decisión del dueño, 22-nov).
struct AjustesBandeja: Equatable {
    var sonido = false

    static func deJSON(_ o: [String: Any]) -> AjustesBandeja {
        AjustesBandeja(sonido: (o["sonido_fichas"] as? Bool) == true)
    }
}

/// Un clic en el monito (E2-a): con algo pendiente, enseña las fichas; NUNCA para nada. Parar es su botón rojo (solo
/// mientras algo se está haciendo) y Esc Esc.
enum ClicMonito: Equatable {
    case desplegar, barra

    static func que(pendientes: Int, plegada: Bool) -> ClicMonito { pendientes > 0 && plegada ? .desplegar : .barra }
}
