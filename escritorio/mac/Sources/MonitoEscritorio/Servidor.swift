// El puerto local de las manos: HTTP mínimo en 127.0.0.1 (nunca en otra interfaz), puerto al azar y una ficha (token)
// al azar que se anotan en <estado>/manos.json (permisos 600). Lo usa escritorio/manos_mcp.py, el servidor MCP que
// Workspace le pone a las sesiones del escritorio. Sin ficha correcta, con otro Host o desde una página web (Origin),
// no pasa nada. Y aunque traiga la ficha, ver/leer/señalar solo pasan con el turno abierto (Candado, en Monito) y se
// anota quién llamó: el pid del proceso dueño de la conexión (verificado con libproc, no lo que dice el pedido).
import Darwin
import Foundation
import Network
import Security

/// Quién hizo el pedido: lo que dice (el turno, su pid) y lo que se comprobó (el pid dueño de la conexión).
struct Llamador {
    var turno: String?
    var pidDicho: pid_t?
    var puertoDelOtro: Int
    var pid: pid_t? = nil
    var proceso: String = ""
    var comando: String = ""
}

final class ServidorManos {
    let token: String
    private(set) var puerto = 0
    private var oyente: NWListener?
    private let cola = DispatchQueue(label: "workspace.monito.manos.http")
    /// (ruta, argumentos, quién llamó, responder) → se llama en el hilo principal.
    var atender: ((String, [String: Any], Llamador, @escaping (Int, [String: Any]) -> Void) -> Void)?

    init() {
        var b = [UInt8](repeating: 0, count: 32)
        if SecRandomCopyBytes(kSecRandomDefault, b.count, &b) != errSecSuccess {
            b = (0..<32).map { _ in UInt8.random(in: 0...255) }
        }
        token = b.map { String(format: "%02x", $0) }.joined()
    }

    /// Escucha en 127.0.0.1 y un puerto libre. `listo(puerto)` (o nil si no se pudo), en el hilo principal.
    func arrancar(_ listo: @escaping (Int?) -> Void) {
        let p = NWParameters.tcp
        p.requiredLocalEndpoint = NWEndpoint.hostPort(host: NWEndpoint.Host("127.0.0.1"), port: .any)
        p.acceptLocalOnly = true
        p.includePeerToPeer = false
        guard let l = try? NWListener(using: p) else { listo(nil); return }
        var avisado = false
        l.stateUpdateHandler = { [weak self, weak l] st in
            switch st {
            case .ready:
                guard !avisado, let n = l?.port?.rawValue else { return }
                avisado = true
                DispatchQueue.main.async { self?.puerto = Int(n); listo(Int(n)) }
            case .failed:
                guard !avisado else { return }
                avisado = true
                DispatchQueue.main.async { listo(nil) }
            default:
                break
            }
        }
        l.newConnectionHandler = { [weak self] c in self?.conexion(c) }
        l.start(queue: cola)
        oyente = l
    }

    func parar() {
        oyente?.cancel()
        oyente = nil
    }

    private func conexion(_ c: NWConnection) {
        // solo conexiones desde esta máquina (además del Host y la ficha)
        if case let .hostPort(host, _) = c.endpoint {
            let h = "\(host)"
            if !(h == "127.0.0.1" || h == "::1" || h.hasPrefix("127.")) { c.cancel(); return }
        }
        c.start(queue: cola)
        cola.asyncAfter(deadline: .now() + 120) { c.cancel() }      // tope: una conexión no se queda colgada
        leer(c, Data())
    }

    private func leer(_ c: NWConnection, _ previo: Data) {
        c.receive(minimumIncompleteLength: 1, maximumLength: 64 * 1024) { [weak self] datos, _, fin, error in
            guard let self = self else { c.cancel(); return }
            var d = previo
            if let datos = datos { d.append(datos) }
            switch HTTP.leer(d) {
            case .falta:
                if fin || error != nil { c.cancel(); return }
                self.leer(c, d)
            case let .malo(codigo):
                self.mandar(c, codigo, ["ok": false, "error": "pedido inválido"])
            case let .listo(pedido, _):
                var puerto = 0
                if case let .hostPort(_, p) = c.endpoint { puerto = Int(p.rawValue) }
                self.despachar(c, pedido, puertoDelOtro: puerto)
            }
        }
    }

    private func despachar(_ c: NWConnection, _ p: PedidoHTTP, puertoDelOtro: Int) {
        if let codigo = HTTP.revisar(p, token: token, puerto: puerto) {
            mandar(c, codigo, ["ok": false, "error": codigo == 401 ? "falta la ficha de manos.json" : "solo desde esta máquina"])
            return
        }
        guard p.ruta.hasPrefix("/v1/") else { mandar(c, 404, ["ok": false, "error": "no existe"]); return }
        let nombre = String(p.ruta.dropFirst(4))
        var args: [String: Any] = [:]
        if !p.cuerpo.isEmpty {
            guard let o = try? JSONSerialization.jsonObject(with: p.cuerpo) as? [String: Any] else {
                mandar(c, 400, ["ok": false, "error": "el cuerpo no es un objeto JSON"])
                return
            }
            args = o
        }
        if p.metodo != "POST" && !(p.metodo == "GET" && nombre == "salud") {
            mandar(c, 405, ["ok": false, "error": "usa POST"])
            return
        }
        // quién es: el pid dueño del otro lado de la conexión (en esta cola, fuera del hilo principal)
        var quien = Llamador(turno: p.cabeceras["x-workspace-turno"], pidDicho: Int32(p.cabeceras["x-workspace-pid"] ?? ""),
                             puertoDelOtro: puertoDelOtro)
        if let pid = Quien.pid(puertoDelOtro: puertoDelOtro, nuestro: puerto, pista: quien.pidDicho) {
            quien.pid = pid
            quien.proceso = Quien.nombre(pid)
            quien.comando = Quien.comando(pid)
        }
        DispatchQueue.main.async { [weak self] in
            guard let self = self, let atender = self.atender else {
                self?.mandar(c, 503, ["ok": false, "error": "el monito no está listo"])
                return
            }
            var contestado = false
            atender(nombre, args, quien) { codigo, cuerpo in
                if contestado { return }
                contestado = true
                self.mandar(c, codigo, cuerpo)
            }
        }
    }

    private func mandar(_ c: NWConnection, _ codigo: Int, _ cuerpo: [String: Any]) {
        let d = (try? JSONSerialization.data(withJSONObject: cuerpo)) ?? Data("{\"ok\":false}".utf8)
        c.send(content: HTTP.respuesta(codigo, d), completion: .contentProcessed { _ in c.cancel() })
    }

    // MARK: manos.json

    /// Escribe <carpeta>/manos.json con permisos 600 (primero a un temporal, luego se renombra).
    @discardableResult
    /// `actuar`: la etapa de actuar que prendió la app («ensayo» en A0; «amarillo» en A1 si algún agente puede; ""
    /// apagado): manos_mcp solo ofrece `actuar` si está aquí. `agentes`: en A1, los que tienen prendido «Puede hacer cosas
    /// en mi Mac» (a los demás, sus manos no se la ofrecen).
    func anotar(en carpeta: String, actuar: String = "", agentes: [String] = []) -> String? {
        let fm = FileManager.default
        try? fm.createDirectory(atPath: carpeta, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let ruta = (carpeta as NSString).appendingPathComponent("manos.json")
        let tmp = ruta + ".\(getpid()).tmp"
        var info: [String: Any] = ["version": 1, "puerto": puerto, "token": token, "pid": Int(getpid()),
                                   "app": "MonitoEscritorio", "host": "127.0.0.1"]
        if !actuar.isEmpty { info["actuar"] = actuar }
        if actuar == Etapa.amarillo.rawValue || actuar == Etapa.naranja.rawValue { info["actuar_agentes"] = agentes }
        guard let d = try? JSONSerialization.data(withJSONObject: info, options: [.sortedKeys]) else { return nil }
        fm.createFile(atPath: tmp, contents: d, attributes: [.posixPermissions: 0o600])
        chmod(tmp, 0o600)
        guard rename(tmp, ruta) == 0 else { unlink(tmp); return nil }
        return ruta
    }

    /// Lo borra al cerrar, solo si sigue siendo el nuestro.
    static func borrar(en carpeta: String) {
        let ruta = (carpeta as NSString).appendingPathComponent("manos.json")
        guard let d = FileManager.default.contents(atPath: ruta),
              let o = try? JSONSerialization.jsonObject(with: d) as? [String: Any],
              (o["pid"] as? NSNumber)?.int32Value == getpid() else { return }
        unlink(ruta)
    }
}

// MARK: quién está del otro lado (libproc: sin permisos, solo procesos del mismo usuario)
enum Quien {
    /// El pid que tiene un socket TCP con puerto local `puertoDelOtro` conectado a nuestro `nuestro`. Primero mira la
    /// pista (el pid que dice el pedido); si no cuadra, busca en todos.
    static func pid(puertoDelOtro: Int, nuestro: Int, pista: pid_t?) -> pid_t? {
        guard puertoDelOtro > 0, nuestro > 0 else { return nil }
        if let p = pista, p > 0, tiene(p, puertoDelOtro, nuestro) { return p }
        let total = proc_listallpids(nil, 0)
        guard total > 0 else { return nil }
        var pids = [pid_t](repeating: 0, count: Int(total) + 64)
        let k = proc_listallpids(&pids, Int32(pids.count * MemoryLayout<pid_t>.size))
        for p in pids.prefix(Int(max(k, 0))) where p > 0 && p != getpid() {
            if tiene(p, puertoDelOtro, nuestro) { return p }
        }
        return nil
    }

    private static func puerto(_ v: Int32) -> Int { Int(UInt16(bigEndian: UInt16(truncatingIfNeeded: v))) }

    private static func tiene(_ pid: pid_t, _ local: Int, _ remoto: Int) -> Bool {
        let n = proc_pidinfo(pid, PROC_PIDLISTFDS, 0, nil, 0)
        guard n > 0 else { return false }
        let paso = MemoryLayout<proc_fdinfo>.stride
        var fds = [proc_fdinfo](repeating: proc_fdinfo(), count: Int(n) / paso + 8)
        let m = proc_pidinfo(pid, PROC_PIDLISTFDS, 0, &fds, Int32(fds.count * paso))
        guard m > 0 else { return false }
        for fd in fds.prefix(Int(m) / paso) where fd.proc_fdtype == UInt32(PROX_FDTYPE_SOCKET) {
            var si = socket_fdinfo()
            let r = proc_pidfdinfo(pid, fd.proc_fd, PROC_PIDFDSOCKETINFO, &si, Int32(MemoryLayout<socket_fdinfo>.size))
            guard r > 0, si.psi.soi_kind == Int32(SOCKINFO_TCP) else { continue }
            let ini = si.psi.soi_proto.pri_tcp.tcpsi_ini
            if puerto(ini.insi_lport) == local && puerto(ini.insi_fport) == remoto { return true }
        }
        return false
    }

    static func nombre(_ pid: pid_t) -> String {
        var b = [CChar](repeating: 0, count: 256)
        let n = proc_name(pid, &b, UInt32(b.count))
        return n > 0 ? String(cString: b) : ""
    }

    /// La línea de comando (para la bitácora: «python3 …/manos_mcp.py»), corta.
    static func comando(_ pid: pid_t) -> String {
        var mib: [Int32] = [CTL_KERN, KERN_PROCARGS2, pid]
        var tam = 0
        guard sysctl(&mib, 3, nil, &tam, nil, 0) == 0, tam > 4 else { return "" }
        var b = [UInt8](repeating: 0, count: tam)
        guard sysctl(&mib, 3, &b, &tam, nil, 0) == 0 else { return "" }
        let argc = Int(b[0]) | Int(b[1]) << 8 | Int(b[2]) << 16 | Int(b[3]) << 24
        var i = 4
        while i < tam && b[i] != 0 { i += 1 }            // la ruta del ejecutable
        while i < tam && b[i] == 0 { i += 1 }
        var args: [String] = []
        while i < tam && args.count < argc {
            var j = i
            while j < tam && b[j] != 0 { j += 1 }
            args.append(String(decoding: b[i..<j], as: UTF8.self))
            i = j + 1
        }
        return String(args.joined(separator: " ").prefix(300))
    }
}
