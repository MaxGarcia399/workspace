// Las manos de trabajo (ronda 2, carril 6 · H-4): buscar un archivo por su nombre, abrir documentos (con su app o con la
// que digas) y dejar un BORRADOR de correo. Aquí no se decide nada: cada cosa pasa por el portero (Seguridad.swift) y
// la hace la mano (Hacer.swift) solo con su autorización.
//
//   buscar_archivo   solo NOMBRES, en tus carpetas normales (las del portero). Cuenta como «leyó» en este turno (los
//                    nombres de lo descargado los escribieron otros): lo que siga en el turno pregunta.
//   abrir            · un documento → el camino de siempre (actuar → portero → su ficha → la mano), con «con» si lo dijiste;
//                    · un nombre con varios candidatos → la ficha de ELEGIR: cada candidato es un botón y tu toque elige
//                      Y aprueba (ese toque es el OK de ESE archivo: el portero da la autorización de un solo uso);
//                    · varios archivos → UNA ficha con un renglón por archivo y un solo botón.
//   redactar_correo  un mailto que arma la app (Seguridad.Borrador: solo para, asunto y texto) → actuar → portero → la
//                    ficha con para, asunto y texto ENTEROS → la mano abre el borrador. Nunca envía.
//
// La ficha de elegir y la de varios renglones son de la bandeja de fichas (carril 2, CONTRATO_BANDEJA.md): esta es la
// versión de mientras, con las mismas piezas de la tarjeta de OK (BotonTarjeta: solo cuentan los clics de una persona,
// EventoReal; por accesibilidad no se aprieta). Su carga (FichaDeTrabajo) es la que recibirá la bandeja.
import AppKit

/// La carga de una ficha de trabajo (lo que la bandeja del carril 2 enseñará). TODO lo arma la app con lo que dice el
/// sistema (nombres y carpetas de archivos que existen); nada viene del texto del agente.
struct FichaDeTrabajo {
    enum Forma: String { case elegir, lote }
    struct Renglon {
        var id: Int
        /// «Ventas 2025.xlsx»
        var titulo: String
        /// «Documentos › Clientes · 21 nov 2026 · se abre con Excel»
        var detalle: String
        var ruta: String
    }
    var id: String
    var forma: Forma
    var agente: String
    var nombreAgente: String
    /// «¿Cuál abro?» · «¿Abro estos 2 archivos?»
    var titulo: String
    var renglones: [Renglon]
    /// Cuántos hay en total (elegir enseña hasta 5).
    var total: Int
    /// Solo `lote`: «Abrir los 2».
    var boton: String
    var tono = "ambar"
    var armaMs = 600
    /// Cuánto espera el agente tu toque. Después la ficha NO caduca: se queda para después (junto5), como las demás.
    var vence: TimeInterval = 60        // = Actuar.ausenteA
    /// junto5 (E5) · el agente todavía no puede hacer cosas en tu Mac: esta misma ficha lo prende con tu toque.
    var primera = false

    func json() -> [String: Any] {
        ["id": id, "forma": forma.rawValue, "agente": agente, "titulo": titulo, "total": total, "boton": boton, "tono": tono,
         "arma_ms": armaMs, "vence_s": vence,
         "renglones": renglones.map { ["id": $0.id, "titulo": $0.titulo, "detalle": $0.detalle, "ruta": $0.ruta] }]
    }
}

/// Lo que contestó el socio: el renglón que tocó (elegir), «todos» (lote), o que no (no · vencida · cancelada).
enum RespuestaDeTrabajo: Equatable {
    case elegido(Int)
    case todos
    case no(String)
}

@MainActor
final class Trabajo {
    unowned let monito: Monito
    /// Quién enseña la ficha: la bandeja del carril 2 (Monito.armarManos la conecta; CONTRATO_BANDEJA.md §7). Ya no hay
    /// ventanita junto al ratón. `alCerrar`: el turno se acabó o el socio paró todo (la bandeja cierra su ficha).
    var presentar: ((FichaDeTrabajo, @escaping (RespuestaDeTrabajo) -> Void) -> Void)?
    var alCerrar: ((String) -> Void)?
    private var ocupado = false
    /// junto5 · las fichas de trabajo que se quedaron para después (no estabas, o se acabó su turno): por renglón, el
    /// pedido EXACTO y lo que se abriría (PedidoGuardado), la app elegida («con») y quién lo pidió. Tu toque las saca.
    private struct ParaDespues {
        var ficha: FichaDeTrabajo
        var con: String?
        var quien: Llamador
        var pedidos: [Int: PedidoGuardado]
    }
    private var paraDespues: [String: ParaDespues] = [:]

    init(monito: Monito) {
        self.monito = monito
        #if PERSONA_DE_PRUEBA
        Mano.abridorDePrueba()
        #endif
    }

    private var actuar: Actuar? { monito.actuar }

    /// Al arrancar la app: nada, salvo en la copia de prueba (su guion, sin motor).
    func alArrancar() {
        #if PERSONA_DE_PRUEBA
        guionDePrueba()
        #endif
    }

    #if PERSONA_DE_PRUEBA
    /// Solo la copia de prueba, y solo con WORKSPACE_PRUEBA_TRABAJO=<carpeta>: corre <carpeta>/guion.json (una lista de
    /// {herramienta, args}) por el MISMO camino que el puerto local (Manos.atender), en un turno de prueba con el agente
    /// «prueba-luna» prendido, y deja cada respuesta en <carpeta>/resultados.jsonl. Sin motor y sin abrir nada (el
    /// abridor de prueba solo anota).
    func guionDePrueba() {
        guard let dir = ProcessInfo.processInfo.environment["WORKSPACE_PRUEBA_TRABAJO"], !dir.isEmpty,
              let d = FileManager.default.contents(atPath: (dir as NSString).appendingPathComponent("guion.json")),
              let pasos = (try? JSONSerialization.jsonObject(with: d)) as? [[String: Any]], let a = actuar, let m = monito.manos else { return }
        let agente = "prueba-luna"
        // (WORKSPACE_PRUEBA_SIN_PRENDER: el agente empieza SIN poder, para ver su primera ficha de trabajo)
        if ProcessInfo.processInfo.environment["WORKSPACE_PRUEBA_SIN_PRENDER"] == nil { a.cambiarPuede(agente, true, desde: "guion de prueba") }
        let salida = (dir as NSString).appendingPathComponent("resultados.jsonl")
        FileManager.default.createFile(atPath: salida, contents: nil)
        func anotar(_ o: [String: Any]) {
            guard let x = try? JSONSerialization.data(withJSONObject: o, options: [.sortedKeys]), let h = FileHandle(forWritingAtPath: salida) else { return }
            h.seekToEndOfFile(); h.write(x + Data("\n".utf8)); try? h.close()
        }
        var turnos = 0
        func turnoNuevo() {
            if turnos > 0 { a.cerrarTurno(); m.turno(nil) }
            turnos += 1
            let id = "turno-de-prueba-000\(turnos)-" + UUID().uuidString.lowercased()
            m.turno(Enfrente(pid: getpid(), bundle: "com.workspace.prueba", nombre: "Prueba", ventana: 0, marco: .zero))
            a.abrirTurno(id, agente: agente, foto: nil)
        }
        turnoNuevo()
        func paso(_ i: Int) {
            guard i < pasos.count else {
                a.cerrarTurno(); m.turno(nil)
                FileManager.default.createFile(atPath: (dir as NSString).appendingPathComponent("fin.json"), contents: Data("{}".utf8))
                return
            }
            let h = (pasos[i]["herramienta"] as? String) ?? ""
            if h == "turno_nuevo" { turnoNuevo(); anotar(["paso": i, "herramienta": h]); paso(i + 1); return }
            m.atender(h, (pasos[i]["args"] as? [String: Any]) ?? [:], quien: Llamador(turno: a.portero.turno, pidDicho: getpid(), puertoDelOtro: 0)) { codigo, r in
                var limpio: [String: Any] = ["paso": i, "herramienta": h, "codigo": codigo]
                for (k, v) in r where v is String || v is Bool || v is NSNumber { limpio[k] = v }
                anotar(limpio)
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { MainActor.assumeIsolated { paso(i + 1) } }
            }
        }
        paso(0)
    }
    #endif
    private var casa: String { NSHomeDirectory() }

    private func no(_ fin: (Int, [String: Any]) -> Void, _ texto: String) { fin(200, ["ok": false, "texto": texto]) }

    private static let apagado = "Este agente todavía no tiene prendido «Puede hacer cosas en mi Mac». Dile al socio, en una frase, que lo prenda en el menú de Compañero (su carita en la barra de menú) y te lo vuelva a pedir."

    /// Se acabó el turno (o el pánico): la ficha de trabajo se cierra sin hacer nada.
    func cerrar(_ por: String) {
        alCerrar?(por)
    }

    // MARK: buscar_archivo
    func buscar(_ args: [String: Any], quien: Llamador, _ fin: @escaping (Int, [String: Any]) -> Void) {
        guard let a = actuar, a.prendido(para: a.portero.agente) else { no(fin, Trabajo.apagado); return }
        guard let n = args["nombre"] as? String else { no(fin, "Di qué buscar: «nombre»."); return }
        let casa = self.casa
        // junto5 (pedido del portero): quién lo pidió se anota AL PEDIR. La búsqueda va en otro hilo: si al terminar ya es
        // el turno de otro agente, la marca de «leyó» no puede caerle a ese.
        let pidio = a.portero.agente
        DispatchQueue.global(qos: .userInitiated).async {
            let h = Buscar.archivos(n, casa: casa)
            DispatchQueue.main.async { MainActor.assumeIsolated {
                self.monito.manos?.anotar(["herramienta": "buscar_archivo", "hallados": h.total, "cortado": h.cortado])
                if !h.lista.isEmpty {
                    // los nombres son contenido de otros (lo descargado se llama como quiso quien lo mandó): cuenta como leer.
                    // Siempre para QUIEN LO PIDIÓ: si su turno sigue abierto, «en este turno»; si ya es de otro agente, queda
                    // como leído antes por el que buscó (Portero.leyo(_:agente:) no le pone el turno de otro).
                    a.portero.leyo(Fuente(app: "los nombres de tus archivos", bundle: "workspace.nombres", tipo: "nombres"), agente: pidio)
                }
                fin(200, ["ok": h.error == nil, "texto": Buscar.paraElAgente(h)])
            } }
        }
    }

    // MARK: redactar_correo
    func correo(_ args: [String: Any], quien: Llamador, _ fin: @escaping (Int, [String: Any]) -> Void) {
        guard let a = actuar else { no(fin, Trabajo.apagado); return }
        let (sellado, e) = Borrador.sellado(args)
        guard let pedido = sellado else { no(fin, e ?? "No pude armar el borrador."); return }
        // el camino de siempre: el portero lo clasifica (un borrador limpio: ámbar; si leyó en este turno o lo abriría tu
        // navegador: coral), la ficha enseña para, asunto y texto ENTEROS, y la mano abre el borrador. Nunca envía.
        a.atender(pedido, quien: quien, fin)
    }

    /// junto5 · «aprobar después» de un borrador: la ficha guardó solo para, asunto y texto (nunca el sello). Aquí vuelve
    /// a entrar por la misma puerta que `redactar_correo`: se arma, se revisa y se sella de nuevo, con el sello de HOY.
    static func pedidoDeCorreo(_ c: CorreoGuardado) -> PedidoAccion? {
        guard let a = Borrador.sellado(c.argumentos).0 else { return nil }
        return PedidoAccion.leer(a).0
    }

    // MARK: abrir
    private enum Resuelto {
        case ruta(String)
        case varios(Hallazgo)
        case nada(String)
    }

    private func resolver(_ x: String) -> Resuelto {
        if Buscar.esRuta(x) { return .ruta(x) }
        let h = Buscar.archivos(x, casa: casa)
        if let e = h.error { return .nada(e) }
        if h.lista.isEmpty { return .nada(Buscar.paraElAgente(h)) }
        if h.total == 1, let c = h.lista.first { return .ruta(c.ruta) }
        return .varios(h)
    }

    func abrir(_ args: [String: Any], quien: Llamador, _ fin: @escaping (Int, [String: Any]) -> Void) {
        guard let a = actuar else { no(fin, Trabajo.apagado); return }
        var pedidos = (args["archivos"] as? [String]) ?? []
        if let uno = args["archivo"] as? String { pedidos = [uno] }
        pedidos = pedidos.compactMap { Texto.limpio($0, tope: 1000) }
        guard !pedidos.isEmpty, pedidos.count <= 5 else { no(fin, "Di qué abrir: de 1 a 5 archivos (su nombre o su ruta entera)."); return }
        let con = (args["con"] as? String).flatMap { Texto.limpio($0, tope: 200) }
        let modo = (args["modo"] as? String).flatMap { ["segundo_plano", "a_la_vista"].contains($0) ? $0 : nil }
        guard !ocupado else { no(fin, "Ya hay una ficha esperando al socio: una cosa a la vez."); return }
        let resueltos = pedidos.map(resolver)
        // uno solo
        if resueltos.count == 1, let r = resueltos.first {
            switch r {
            case .nada(let e): no(fin, e)
            case .ruta(let ruta): uno(ruta, con: con, modo: modo, quien, fin)
            case .varios(let h): elegir(h, con: con, modo: modo, a, quien, fin)
            }
            return
        }
        // varios: una sola ficha, un renglón por archivo. Cada uno tiene que ser UN archivo (si un nombre tiene varios
        // candidatos, ese se pide aparte para que el socio elija)
        var rutas: [String] = []
        for (i, r) in resueltos.enumerated() {
            switch r {
            case .ruta(let x): rutas.append(x)
            case .nada(let e): no(fin, "«\(pedidos[i])»: " + e); return
            case .varios:
                no(fin, "Hay varios archivos que se llaman «\(pedidos[i])»: ese ábrelo aparte, con abrir(archivo=\"\(pedidos[i])\"), para que el socio elija cuál en su ficha.")
                return
            }
        }
        lote(rutas, con: con, modo: modo, a, quien, fin)
    }

    /// El pedido de abrir un archivo, como lo lee el portero.
    private func argumentos(_ ruta: String, _ modo: String?) -> [String: Any] {
        var d: [String: Any] = ["accion": "abrir", "ruta": ruta]
        if let m = modo { d["modo"] = m }
        return d
    }

    /// «con Excel»: la app con ese nombre que el SISTEMA dice que abre ese archivo. → el error, o nil.
    private func elegirApp(_ ruta: String, _ con: String?) -> String? {
        guard let c = con else { return nil }
        let real = ((ruta as NSString).expandingTildeInPath as NSString).resolvingSymlinksInPath
        let (b, e) = Mano.appPara(c, archivo: real)
        guard let bundle = b else { return e ?? "No encontré esa app." }
        Mano.conElegida[real] = bundle
        return nil
    }

    /// Un archivo: el camino de siempre (actuar → el portero → su ficha o lo recordado → la mano).
    private func uno(_ ruta: String, con: String?, modo: String?, _ quien: Llamador, _ fin: @escaping (Int, [String: Any]) -> Void) {
        guard let a = actuar else { no(fin, Trabajo.apagado); return }
        if let e = elegirApp(ruta, con) { no(fin, e); return }
        a.atender(argumentos(ruta, modo), quien: quien, fin)
    }

    /// ¿El portero haría esto con una ficha ámbar (un toque)? Solo eso va en una ficha de trabajo; lo demás, por su camino.
    private func ambar(_ ruta: String, _ a: Actuar) -> (PedidoAccion, [Destino])? {
        guard let p = PedidoAccion.leer(argumentos(ruta, nil)).0 else { return nil }
        let (ds, err) = a.destinos(p)
        guard err == nil, !ds.isEmpty, a.portero.clasificar(p, ds).color == .amarillo else { return nil }
        return (p, ds)
    }

    private func renglon(_ i: Int, _ ruta: String, carpeta: String?, fecha: Date?, _ ds: [Destino]) -> FichaDeTrabajo.Renglon {
        var partes: [String] = []
        if let c = carpeta { partes.append(c) }
        if let f = fecha { partes.append(Buscar.fecha(f)) }
        if let n = ds.first?.abrirNombre { partes.append("se abre con " + n) }
        return FichaDeTrabajo.Renglon(id: i, titulo: Texto.limpio((ruta as NSString).lastPathComponent, tope: 90) ?? "archivo",
                                      detalle: partes.joined(separator: " · "), ruta: ruta)
    }

    /// Dónde está, para la ficha: «Documentos › Clientes», o su carpeta.
    private func carpetaDe(_ ruta: String) -> String {
        let real = (ruta as NSString).resolvingSymlinksInPath
        for r in Buscar.raices(casa: casa) {
            let base = (r.ruta as NSString).resolvingSymlinksInPath
            if real.hasPrefix(base + "/") {
                let medio = (String(real.dropFirst(base.count + 1)) as NSString).deletingLastPathComponent
                return medio.isEmpty ? r.nombre : r.nombre + " › " + medio.replacingOccurrences(of: "/", with: " › ")
            }
        }
        return ((real as NSString).deletingLastPathComponent as NSString).lastPathComponent
    }

    /// junto5 (E5) · ¿esta sería su PRIMERA ficha? El agente todavía no puede, pero se le puede ofrecer en la misma ficha
    /// (hay turno y agente, y el socio no lo apagó a propósito para él): igual que Actuar.atender.
    private func esPrimera(_ a: Actuar) -> Bool {
        let ag = a.portero.agente
        return !a.ensayo && !a.prendido(para: ag) && !ag.isEmpty && a.portero.turno != nil && !a.puede.apagado(ag)
    }

    /// Las fichas de trabajo solo de verdad, con el agente prendido o en su primera vez (en ensayo y apagado a propósito,
    /// por el camino de siempre).
    private func puedeFicha(_ a: Actuar) -> String? {
        if a.ensayo { return "En el ensayo no enseño esa ficha: pide un archivo a la vez, con su ruta." }
        if !a.prendido(para: a.portero.agente) && !esPrimera(a) { return Trabajo.apagado }
        if a.enVuelo { return "Ya hay una tarjeta esperando al socio: una cosa a la vez." }
        return nil
    }

    /// Varios candidatos: cada uno es un botón; el toque del socio elige Y aprueba.
    private func elegir(_ h: Hallazgo, con: String?, modo: String?, _ a: Actuar, _ quien: Llamador, _ fin: @escaping (Int, [String: Any]) -> Void) {
        // solo los que el portero abriría con un toque (un script con nombre de documento ni siquiera llegó aquí; un tipo
        // raro o una app que no conoce va por su camino, uno a la vez)
        let buenos = h.lista.compactMap { c in ambar(c.ruta, a).map { (c, $0.1) } }
        guard buenos.count > 1 else {
            uno((buenos.first?.0 ?? h.lista[0]).ruta, con: con, modo: modo, quien, fin)
            return
        }
        if let e = puedeFicha(a) { no(fin, e); return }
        let f = FichaDeTrabajo(id: UUID().uuidString.lowercased(), forma: .elegir, agente: a.portero.agente,
                               nombreAgente: a.portero.nombreVisible(a.portero.agente),
                               titulo: h.total > buenos.count ? "Hay \(h.total) que se llaman así. ¿Cuál abro?" : "¿Cuál abro?",
                               renglones: buenos.enumerated().map { renglon($0.offset, $0.element.0.ruta, carpeta: $0.element.0.carpeta, fecha: $0.element.0.modificado, $0.element.1) },
                               total: h.total, boton: "", primera: esPrimera(a))
        ensenar(f, quien) { [weak self] r in
            guard let self = self else { return }
            guard case .elegido(let i) = r, let x = f.renglones.first(where: { $0.id == i }) else {
                if case .no(let por) = r { self.noContesto(f, por, con: con, modo: modo, quien, fin) } else { self.no(fin, "No eligió ninguno.") }
                return
            }
            if let e = self.elegirApp(x.ruta, con) { self.no(fin, e); return }
            self.aprobado(x.ruta, modo: modo, quien, fin)
        }
    }

    /// Varios archivos: una ficha, un renglón por archivo, un toque.
    private func lote(_ rutas: [String], con: String?, modo: String?, _ a: Actuar, _ quien: Llamador, _ fin: @escaping (Int, [String: Any]) -> Void) {
        let buenos = rutas.compactMap { r in ambar(r, a).map { (r, $0.1) } }
        // si alguno no es de un toque (no existe, es de otro color), cada uno por su camino, en orden: el portero dice qué pasa
        guard buenos.count == rutas.count, puedeFicha(a) == nil else {
            if buenos.count == rutas.count, let e = puedeFicha(a), !a.ensayo, a.prendido(para: a.portero.agente) { no(fin, e); return }
            enFila(rutas, 0, [], true) { [weak self] ruta, sigue in self?.uno(ruta, con: con, modo: modo, quien, sigue) } fin: { fin(200, $0) }
            return
        }
        let f = FichaDeTrabajo(id: UUID().uuidString.lowercased(), forma: .lote, agente: a.portero.agente,
                               nombreAgente: a.portero.nombreVisible(a.portero.agente), titulo: "¿Abro estos \(rutas.count) archivos?",
                               renglones: buenos.enumerated().map { renglon($0.offset, $0.element.0, carpeta: carpetaDe($0.element.0), fecha: nil, $0.element.1) },
                               total: rutas.count, boton: "Abrir los \(rutas.count)", primera: esPrimera(a))
        ensenar(f, quien) { [weak self] r in
            guard let self = self else { return }
            guard r == .todos else {
                if case .no(let por) = r { self.noContesto(f, por, con: con, modo: modo, quien, fin) } else { self.no(fin, "No los abrí.") }
                return
            }
            self.enFila(rutas, 0, [], true) { [weak self] ruta, sigue in
                guard let self = self else { return }
                if let e = self.elegirApp(ruta, con) { sigue(200, ["ok": false, "texto": e]); return }
                self.aprobado(ruta, modo: modo, quien, sigue)
            } fin: { fin(200, $0) }
        }
    }

    /// Uno tras otro; al final, una sola respuesta para el agente.
    private func enFila(_ rutas: [String], _ i: Int, _ textos: [String], _ todoBien: Bool,
                        _ paso: @escaping (String, @escaping (Int, [String: Any]) -> Void) -> Void, fin: @escaping ([String: Any]) -> Void) {
        guard i < rutas.count else { fin(["ok": todoBien, "texto": textos.joined(separator: " ")]); return }
        paso(rutas[i]) { [weak self] _, d in
            let ok = (d["ok"] as? Bool) ?? false
            let t = (d["texto"] as? String) ?? (d["error"] as? String) ?? (ok ? "Listo." : "No se pudo.")
            self?.enFila(rutas, i + 1, textos + ["«\((rutas[i] as NSString).lastPathComponent)»: " + t], todoBien && ok, paso, fin: fin)
        }
    }

    // MARK: junto5 · «aprobar después» de una ficha de trabajo
    /// El socio no contestó (pasó el minuto, o se acabó el turno): como en las demás fichas, NO es un «no». Se guarda el
    /// pedido exacto de cada renglón y lo que se abriría; al agente se le dice que quedó pendiente y cierra su turno. Lo
    /// que dijo que no (o paró todo) sigue igual.
    private func noContesto(_ f: FichaDeTrabajo, _ por: String, con: String?, modo: String?, _ quien: Llamador,
                            _ fin: (Int, [String: Any]) -> Void) {
        guard por == "vencida" || por == "turno", let a = actuar, !f.primera else { no(fin, Trabajo.dijoQueNo(por)); return }
        var pedidos: [Int: PedidoGuardado] = [:]
        for r in f.renglones {
            guard let p = PedidoAccion.leer(argumentos(r.ruta, modo)).0, !Despues.dependeDePantalla(p) else { continue }
            let hs = Huella.lote(a.destinos(p).0, p.tipoConocido)
            if !hs.isEmpty { pedidos[r.id] = PedidoGuardado(pedido: p, huellas: hs, agente: f.agente, tono: .ambar, guardado: Date()) }
        }
        guard pedidos.count == f.renglones.count else { no(fin, Trabajo.dijoQueNo(por)); return }
        paraDespues[f.id] = ParaDespues(ficha: f, con: con, quien: quien, pedidos: pedidos)
        a.portero.registro.append(["cuando": ISO8601DateFormatter().string(from: Date()), "tipo": "ficha_trabajo", "resultado": "para_despues",
                                   "ficha": f.id, "agente": f.agente])
        a.volcar(quien)
        fin(200, ["ok": false, "pendiente": true, "texto": Actuar.textoAusente])
    }

    /// ¿Esa ficha se quedó para después? (la bandeja la deja a la vista, con sus renglones)
    func quedoParaDespues(_ id: String) -> Bool { paraDespues[id] != nil }

    /// Ya no la quiere (dijo «No» o «Ninguno» después).
    func olvidarDespues(_ id: String) { paraDespues[id] = nil }

    /// Tu toque en una ficha de trabajo que se quedó (un clic de una persona, en la bandeja): un renglón (`renglon`) o
    /// todos (nil). Vale UNA vez. Cada archivo vuelve al portero con lo de HOY (Actuar.hacerGuardado): solo si se abriría
    /// lo mismo y sigue siendo de un toque. → `listo(nil)` si se hizo todo; si no, por qué no (la ficha lo dice).
    func hacerDespues(_ id: String, renglon: Int?, _ listo: @escaping (String?) -> Void) {
        guard let a = actuar, let d = paraDespues[id] else { listo("ya pasó"); return }
        if a.portero.turno != nil, a.portero.agente != d.ficha.agente {
            listo("espera"); return                                   // otro agente tiene su turno: se queda, se toca en un momento
        }
        paraDespues[id] = nil
        let cuales = d.ficha.renglones.filter { renglon == nil || $0.id == renglon }
        guard !cuales.isEmpty else { listo("ya pasó"); return }
        var fallo: String? = nil
        func paso(_ i: Int) {
            guard i < cuales.count else { listo(fallo); return }
            let r = cuales[i]
            guard let g = d.pedidos[r.id] else { fallo = fallo ?? "ya pasó"; paso(i + 1); return }
            let ds = a.destinos(g.pedido).0
            if let c = Huella.cambioLote(g.huellas, Huella.lote(ds, g.pedido.tipoConocido)) { fallo = fallo ?? "ya no es lo mismo: \(c)"; paso(i + 1); return }
            if let e = elegirApp(r.ruta, d.con) { fallo = fallo ?? e; paso(i + 1); return }
            // `yaNo` llega en el acto si el portero hoy dice que no; `hecho`, cuando la mano termina (una de las dos)
            var negado = false
            a.hacerGuardado(g, destinos: ds, quien: d.quien, yaNo: { por in negado = true; fallo = fallo ?? por }, hecho: { ok, texto in
                if !ok { fallo = fallo ?? (texto.isEmpty ? "no se pudo abrir" : texto) }
                paso(i + 1)
            })
            if negado { paso(i + 1) }
        }
        paso(0)
    }

    static func dijoQueNo(_ por: String) -> String {
        switch por {
        case "vencida": return "Nadie contestó la ficha: no abrí nada."
        case "turno": return "Se acabó el turno mientras esperaba al socio: no abrí nada."
        case "panico": return "El socio paró todo: no abrí nada. No lo vuelvas a intentar si él no lo pide."
        default: return "El socio dijo que no. No lo vuelvas a pedir en este turno si él no lo pide."
        }
    }

    /// El socio YA tocó este renglón en la ficha que armó la app (un clic de una persona): ese toque es el OK de ESE
    /// archivo. El portero lo vuelve a clasificar ahora; solo si es de un toque (ámbar) da su autorización de un solo uso,
    /// atada al archivo y a la app que lo abre; lo coral y lo rojo no pasan por aquí.
    private func aprobado(_ ruta: String, modo: String?, _ quien: Llamador, _ fin: @escaping (Int, [String: Any]) -> Void) {
        guard let a = actuar, a.prendido(para: a.portero.agente), !a.ensayo else { no(fin, Trabajo.apagado); return }
        let (q, e) = PedidoAccion.leer(argumentos(ruta, modo))
        guard let p = q else { no(fin, e ?? "Pedido inválido."); return }
        let (ds, err) = a.destinos(p)
        if let e = err { no(fin, e); return }
        let r = a.portero.pedir(p, destinos: ds)
        a.volcar(quien)
        let m = Modo(rawValue: p.modo ?? "") ?? a.portero.modo(de: a.portero.agente)
        switch r.salida {
        case .tarjeta:
            guard let t = r.tarjeta else { no(fin, r.motivo); return }
            guard r.color == .amarillo, t.sostenerMs == 0 else {
                _ = a.portero.responder(t.id, "cancelada", ahora: ds)       // lo coral pide su propia ficha, sostenida
                a.volcar(quien)
                no(fin, "Ese necesita su propia ficha (\(r.motivo)): pídelo solo, con abrir(archivo=\"<su ruta>\").")
                return
            }
            let res = a.portero.responder(t.id, "hazlo", ahora: a.destinos(p).0)
            a.volcar(quien)
            guard let aut = res.autorizacion else { no(fin, res.motivo); return }
            a.hacer(aut, p, quien, modo: m, porConfianza: false, fin)
        case .cero, .confianza:
            guard let aut = r.autorizacion else { no(fin, r.motivo); return }
            a.hacer(aut, p, quien, modo: m, porConfianza: false, fin)     // lo tocó en la ficha: fue con su toque
        default:
            no(fin, r.motivo)
        }
    }

    // MARK: la ficha
    private func ensenar(_ f: FichaDeTrabajo, _ quien: Llamador, _ listo: @escaping (RespuestaDeTrabajo) -> Void) {
        guard let a = actuar else { listo(.no("no")); return }
        ocupado = true
        a.trabajoEsperando = true
        func anotar(_ resultado: String, _ extra: [String: Any] = [:]) {
            var o: [String: Any] = ["cuando": ISO8601DateFormatter().string(from: Date()), "tipo": "ficha_trabajo", "forma": f.forma.rawValue,
                                    "resultado": resultado, "ficha": f.id, "agente": f.agente, "turno": a.portero.turno ?? "",
                                    "renglones": f.renglones.map { $0.ruta }]
            for (k, v) in extra { o[k] = v }
            a.portero.registro.append(o)
            a.volcar(quien)
        }
        anotar("pedido")
        let turno = a.portero.turno
        let fin: (RespuestaDeTrabajo) -> Void = { [weak self] r in
            guard let self = self else { return }
            self.ocupado = false
            a.trabajoEsperando = false
            // el turno tiene que ser el mismo en que se pidió
            guard a.portero.turno == turno, turno != nil else { anotar("turno"); listo(.no("turno")); return }
            switch r {
            case .elegido(let i): anotar("elegido", ["renglon": i, "ruta": f.renglones.first { $0.id == i }?.ruta ?? ""])
            case .todos: anotar("todos")
            case .no(let por): anotar(por)
            }
            listo(r)
        }
        guard let p = presentar else { fin(.no("no")); return }       // sin bandeja no hay dónde preguntar: no se hace
        p(f, fin)
        #if PERSONA_DE_PRUEBA
        personaDePrueba(f)
        #endif
    }

    #if PERSONA_DE_PRUEBA
    /// Solo la copia de prueba: deja la ficha en <estado>/escritorio/prueba/ficha_trabajo.json y contesta lo que diga
    /// respuesta_trabajo.json ({"ficha": id, "elige": n} · {"ficha": id, "todos": true} · {"ficha": id, "no": true}).
    private func personaDePrueba(_ f: FichaDeTrabajo) {
        guard let a = actuar else { return }
        let dir = (a.carpeta as NSString).appendingPathComponent("prueba")
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        if let d = try? JSONSerialization.data(withJSONObject: f.json(), options: [.sortedKeys]) {
            FileManager.default.createFile(atPath: (dir as NSString).appendingPathComponent("ficha_trabajo.json"), contents: d)
        }
        let r = (dir as NSString).appendingPathComponent("respuesta_trabajo.json")
        let id = "w:" + f.id
        Timer.scheduledTimer(withTimeInterval: 0.3, repeats: true) { [weak self] t in
            MainActor.assumeIsolated {
                // su ficha vive en la bandeja: la persona de prueba aprieta ahí (con su armado, como un clic)
                // (también cuando la ficha se quedó para después: junto5)
                guard let self = self, self.ocupado || self.paraDespues[f.id] != nil, self.monito.bandeja.ficha(id) != nil else { t.invalidate(); return }
                guard let d = FileManager.default.contents(atPath: r), let o = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any],
                      (o["ficha"] as? String) == f.id else { return }
                let b: String
                if let n = o["elige"] as? Int, f.forma == .elegir { b = "r:\(n)" }
                else if (o["todos"] as? Bool) == true, f.forma == .lote { b = "todos" }
                else { b = "no" }
                if self.monito.bandeja.estado.plegada { self.monito.mensaje(["op": "llamar"]) }
                if self.monito.bandeja.personaDePrueba(id, b, casilla: nil) { unlink(r) }
            }
        }
    }
    #endif
}

#if PERSONA_DE_PRUEBA
extension Mano {
    /// Solo la copia de prueba: con WORKSPACE_PRUEBA_ABRIDOR=<archivo>, nada se abre; cada apertura se anota ahí.
    static func abridorDePrueba() {
        guard let r = ProcessInfo.processInfo.environment["WORKSPACE_PRUEBA_ABRIDOR"], !r.isEmpty else { return }
        abridor = { a, fin in
            let o: [String: Any] = ["forma": a.forma, "app": a.app.path, "urls": a.urls.map { $0.absoluteString }, "activar": a.activar,
                                    "cuando": Date().timeIntervalSince1970]
            if let d = try? JSONSerialization.data(withJSONObject: o, options: [.sortedKeys]) {
                if !FileManager.default.fileExists(atPath: r) { FileManager.default.createFile(atPath: r, contents: nil) }
                if let h = FileHandle(forWritingAtPath: r) { h.seekToEndOfFile(); h.write(d + Data("\n".utf8)); try? h.close() }
            }
            fin(0, nil)
        }
    }
}
#endif
