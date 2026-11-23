// El portero de la seguridad para actuar, por línea de comandos: el MISMO código que usa la app (Seguridad.swift) para
// que las pruebas de ataques (escritorio/trampas) y las de Python pasen por el clasificador y la tarjeta de verdad, sin
// abrir la app ni tocar nada. Una línea de JSON entra, una sale.
//   swiftc -parse-as-library ../Sources/MonitoEscritorio/Logica.swift ../Sources/MonitoEscritorio/Seguridad.swift \
//          portero.swift -o portero
//
//   {"op":"etapa","etapa":"ensayo"}                         {"op":"reloj","t":<segundos>}      (pruebas: el reloj)
//   {"op":"turno","id":"…","agente":"…"}                    {"op":"fin_turno"}
//   {"op":"leyo","fuente":{app,bundle,ventana,sitio,tipo}}  {"op":"panico"}   {"op":"olvidar","agente":"…"}
//   {"op":"vetar","vetados":[{tipo,valor,nombre,que}]}       {"op":"mouse","agente":"…","valor":"nunca|preguntando"}
//   {"op":"confiar","agente":"…","destino":{…}}             (una confianza que el socio ya dio hoy)
//   {"op":"clasificar","pedido":{…},"destinos":[{…}]}
//   {"op":"pedir","pedido":{…},"destinos":[{…}]}
//   {"op":"vigente","tarjeta":"…","destinos":[{…}]}
//   {"op":"responder","tarjeta":"…","respuesta":"hazlo|a_la_vista|ensename|no|vencida|cancelada","confiar":false,"destinos":[…]}
//   {"op":"ejecutar","autorizacion":"…","destinos":[…]}
//   {"op":"senalable","destino":{…}}   {"op":"mirar","destino":{…}}   {"op":"cuentas"}   {"op":"reglas"}
//   ronda 2 · {"op":"recordar","tipo":"abrir_app|abrir_archivo|abrir_pagina"}   {"op":"quitar_recordado","tipo":"…"|"todos"}
//             {"op":"recordados"}   {"op":"cargar_recordados","datos":{…}}   (lo que traería recordados.json)
//             {"op":"nombres","mapa":{"luna":"Luna"}}   {"op":"cargar_lecturas","agentes":{"luna":[{…}]}}   {"op":"lecturas"}
//             {"op":"contexto","seleccion":"…","bajo_el_raton":"…"}   (¿contexto_escritorio leyó contenido o solo el título?)
//             responder acepta "recordar": true (la casilla «No me preguntes…»)
//   portero --reglas <escritorio/reglas/portero.json>   (sin ellas, solo el núcleo rojo: nada es amarillo)
// Cada respuesta trae "registro": las líneas nuevas de la bitácora.
import Foundation

@main
struct PorteroCLI {
    static func main() {
        // las reglas (escritorio/reglas/portero.json): --reglas <ruta>; sin ellas, solo el núcleo rojo (nada amarillo)
        let args = CommandLine.arguments
        if let i = args.firstIndex(of: "--reglas"), i + 1 < args.count { Reglas.usar(Reglas.cargar(args[i + 1])) }
        var fijo: Date? = nil                     // las pruebas pueden fijar el reloj; si no, la hora de verdad
        // el día termina a la medianoche UTC (las pruebas fijan el reloj: que no dependa de la zona de quien las corre)
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(identifier: "UTC") ?? .current
        let p = Portero(etapa: .ensayo, reloj: { fijo ?? Date() }, calendario: utc)
        func salida(_ o: [String: Any]) {
            var d = o
            d["registro"] = p.registro
            p.registro = []
            if let j = try? JSONSerialization.data(withJSONObject: d, options: [.sortedKeys]), let s = String(data: j, encoding: .utf8) {
                print(s)
            } else {
                print("{\"error\":\"no se pudo escribir la respuesta\"}")
            }
            fflush(stdout)
        }
        while let linea = readLine() {
            guard let d = linea.data(using: .utf8), let o = (try? JSONSerialization.jsonObject(with: d)) as? [String: Any],
                  let op = o["op"] as? String else {
                salida(["error": "no es un objeto JSON con «op»"])
                continue
            }
            let ds = PorteroJSON.destinos(o["destinos"])
            switch op {
            case "etapa":
                p.etapa = Etapa(rawValue: (o["etapa"] as? String) ?? "") ?? .ensayo
                salida(["ok": true, "etapa": p.etapa.rawValue])
            case "reloj":
                fijo = (o["t"] as? NSNumber).map { Date(timeIntervalSince1970: $0.doubleValue) }
                salida(["ok": true])
            case "turno":
                p.abrirTurno((o["id"] as? String) ?? "", agente: (o["agente"] as? String) ?? "")
                salida(["ok": true])
            case "fin_turno":
                p.cerrarTurno()
                salida(["ok": true])
            case "leyo":
                if let f = (o["fuente"] as? [String: Any]).flatMap(Fuente.deJSON) { p.leyo(f) }
                salida(["ok": true, "resumen": p.lecturas.resumen ?? ""])
            case "reglas":
                salida(Reglas.actual.json())
            case "olvidar":
                p.olvidarLecturas(agente: (o["agente"] as? String) ?? "")
                salida(["ok": true])
            case "panico":
                salida(["ok": true, "cancelo": p.panico()])
            case "vetar":
                let n = p.vetados.sumarDeArchivo((o["vetados"] as? [[String: Any]]) ?? [])
                salida(["ok": true, "sumados": n])
            case "mouse":
                if let a = o["agente"] as? String { p.mouse[a] = MouseAgente(rawValue: (o["valor"] as? String) ?? "") ?? .nunca }
                salida(["ok": true])
            case "modo":
                if let a = o["agente"] as? String, let m = Modo(rawValue: (o["valor"] as? String) ?? "") { p.modos[a] = m }
                salida(["ok": true])
            case "confiar":
                let dd = PorteroJSON.destino((o["destino"] as? [String: Any]) ?? [:])
                let c = p.confianzas.dar(id: UUID().uuidString.lowercased(), agente: (o["agente"] as? String) ?? "", destino: dd, ahora: fijo ?? Date())
                salida(["ok": true, "confianza": c.json()])
            case "clasificar":
                let (q, e) = PedidoAccion.leer((o["pedido"] as? [String: Any]) ?? [:])
                guard let pedido = q else { salida(["error": e ?? "pedido inválido"]); continue }
                let c = p.clasificar(pedido, ds)
                salida(["color": c.color.rawValue, "porque": c.porque, "puede_senalar": c.puedeSenalar])
            case "pedir":
                let (q, e) = PedidoAccion.leer((o["pedido"] as? [String: Any]) ?? [:])
                guard let pedido = q else {
                    // un pedido que ni se puede leer (muy largo, con letras invisibles): no, con su ficha de «no»
                    var f = Ficha(salida: .no, tono: .no)
                    f.agente = p.agente
                    f.motivo = e ?? "pedido inválido"
                    salida(["salida": "negado", "color": "rojo", "motivo": e ?? "pedido inválido", "ficha": f.json()]); continue
                }
                salida(p.pedir(pedido, destinos: ds).json())
            case "vigente":
                let c = p.vigente((o["tarjeta"] as? String) ?? "", ahora: ds)
                salida(["vigente": c == nil, "cambio": c ?? ""])
            case "responder":
                salida(p.responder((o["tarjeta"] as? String) ?? "", (o["respuesta"] as? String) ?? "no",
                                   confiar: (o["confiar"] as? Bool) ?? false, recordar: (o["recordar"] as? Bool) ?? false, ahora: ds).json())
            case "ejecutar":
                salida(p.ejecutar((o["autorizacion"] as? String) ?? "", ahora: ds).json())
            case "mirar":
                let dd = PorteroJSON.destino((o["destino"] as? [String: Any]) ?? [:])
                let v = p.vetados.noMirar(dd)
                salida(["puede": v == nil, "vetado": v?.nombre ?? ""])
            case "senalable":
                let dd = PorteroJSON.destino((o["destino"] as? [String: Any]) ?? [:])
                let por = Clasificador.puedeSenalar(dd, vetados: p.vetados)
                salida(["puede": por == nil, "motivo": por ?? ""])
            case "cuentas":
                salida(["ejecutadas": p.ejecutadas.count, "por_confianza": p.ejecutadas.filter { $0.porConfianza }.count,
                        "sin_preguntar": p.ejecutadasCero,
                        "tarjetas_abiertas": p.tarjetasAbiertas.count, "confianzas": p.confianzas.lista.map { $0.json() }])
            case "recordar":
                guard let t = (o["tipo"] as? String).flatMap(TipoRecordado.init(rawValue:)) else {
                    salida(["ok": false, "error": "no es un tipo que se pueda recordar"]); continue
                }
                p.recordar(t)                   // (en la app: solo desde un clic de una persona)
                salida(["ok": true, "recordados": p.recordados.json()])
            case "quitar_recordado":
                if (o["tipo"] as? String) == "todos" { p.quitarRecordados() }
                else if let t = (o["tipo"] as? String).flatMap(TipoRecordado.init(rawValue:)) { p.quitarRecordado(t) }
                salida(["ok": true, "recordados": p.recordados.json()])
            case "recordados":
                salida(["recordados": p.recordados.json(), "lista": p.recordados.lista.map { ["tipo": $0.tipo.rawValue, "texto": $0.texto] }])
            case "cargar_recordados":
                p.recordados = Recordados.deJSON((o["datos"] as? [String: Any]) ?? [:])
                salida(["ok": true, "recordados": p.recordados.json()])
            case "entregables":             // T1-b: las carpetas de entregables de los cerebros (las limpia el portero)
                Entregables.usar(((o["rutas"] as? [Any]) ?? []).compactMap { $0 as? String }, casa: (o["casa"] as? String) ?? NSHomeDirectory())
                salida(["ok": true, "entregables": Entregables.actuales])
            case "borrador":                // carril 6: un borrador que arma la APP (con su sello), como redactar_correo
                let (b, e) = Borrador.leer((o["correo"] as? [String: Any]) ?? [:])
                guard let u = b?.mailto else {
                    var f = Ficha(salida: .no, tono: .no); f.agente = p.agente; f.motivo = e ?? "No pude armar el borrador."
                    salida(["salida": "negado", "color": "rojo", "motivo": f.motivo, "ficha": f.json()]); continue
                }
                var dd = ds
                if dd.isEmpty { dd = [Destino()] }
                dd[0].abrirURL = u
                let (q, _) = PedidoAccion.leer(["accion": "abrir", "url": u, "_borrador": Borrador.sello, "modo": (o["modo"] as? String) ?? ""])
                guard let pedido = q else { salida(["salida": "negado", "color": "rojo", "motivo": "no se pudo leer"]); continue }
                var r = p.pedir(pedido, destinos: dd).json()
                r["mailto"] = u
                salida(r)
            case "nombres":
                p.nombres = (o["mapa"] as? [String: String]) ?? [:]
                salida(["ok": true])
            case "cargar_lecturas":
                p.cargarLecturas(((o["agentes"] as? [String: Any]) ?? [:]).mapValues { Lecturas.deJSON(($0 as? [[String: Any]]) ?? []) })
                salida(["ok": true, "guardables": p.lecturasGuardables().mapValues { $0.json() }])
            case "lecturas":
                let g = p.lecturas.grado(turno: p.turno)
                salida(["fuentes": p.lecturas.json(), "grado": g.grado.rawValue, "guardables": p.lecturasGuardables().mapValues { $0.json() }])
            case "contexto":
                salida(["tipo": Fuente.tipoDeContexto(seleccion: o["seleccion"] as? String, bajoElRaton: o["bajo_el_raton"] as? String)])
            default:
                salida(["error": "no conozco «\(op)»"])
            }
        }
    }
}
