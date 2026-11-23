// Los demos de la seguridad para actuar (A0): solo con `abrir.py --demo <tipo>` (nunca por el puerto local), con
// datos de ejemplo fijos, para verlos y fotografiarlos sin un agente:
//   tarjeta      la ficha ámbar de la bandeja (escribir, con «leyó: …») y la coral (mandar: se sostiene 1.5 s)
//   envivo       la banda «en vivo» del modo con tu cursor (A4): cuenta regresiva, bordes, la pausa si mueves el mouse
//   aviso        el aviso tranquilo de segundo plano con Deshacer, en la burbuja
//   automatizar  la tarjeta amable antes del aviso de Automatización de macOS
// Con --foto <prefijo>, cada pieza se guarda a un PNG (lo que pinta, sin grabar la pantalla); con --fantasma, casi
// invisible mientras tanto.
import AppKit

enum DemoActuar {
    static let tipos: Set<String> = ["tarjeta", "envivo", "aviso", "automatizar"]
}

extension Monito {
    func demoActuar(_ tipo: String) {
        let foto = op.foto
        let despues: (Double, @escaping () -> Void) -> Void = { s, f in DispatchQueue.main.asyncAfter(deadline: .now() + s) { f() } }
        switch tipo {
        case "tarjeta":
            let p = Portero(etapa: .ensayo)
            p.abrirTurno("demo", agente: "Luna")
            p.leyo(Fuente(app: "Chrome", bundle: "com.google.Chrome", sitio: "mail.google.com", tipo: "ventana"))
            var campo = Destino()
            campo.app = "Mail"; campo.bundle = "com.apple.mail"; campo.ventana = "Nuevo mensaje"; campo.ventanaId = 1
            campo.rol = "AXTextField"; campo.etiqueta = "Asunto"; campo.marco = CGRect(x: 300, y: 200, width: 400, height: 22)
            var escribir = PedidoAccion(tipo: "escribir")
            escribir.valor = "Cotización de noviembre"
            // las fichas de la bandeja (ronda 2), con datos de ejemplo: la ámbar (con «leyó») y, después, la coral
            guard let f1 = p.pedir(escribir, destinos: [campo]).ficha else { return }
            let b1 = TextoFicha.dePortero(f1, nombre: "Luna", color: "#8b5cf6", ahora: Date())
            bandeja.poner(b1) { [weak self] _, _ in self?.bandeja.quitar(b1.id) }
            despues(5) {
                self.bandeja.quitar(b1.id)
                var boton = campo
                boton.rol = "AXButton"; boton.etiqueta = "Enviar"
                guard let f2 = p.pedir(PedidoAccion(tipo: "presionar"), destinos: [boton]).ficha, f2.salida == .ficha else { return }
                let b2 = TextoFicha.dePortero(f2, nombre: "Luna", color: "#8b5cf6", ahora: Date())
                self.bandeja.poner(b2) { [weak self] _, _ in self?.bandeja.quitar(b2.id) }
                despues(5) { self.bandeja.quitar(b2.id) }
            }
        case "envivo":
            let b = BandaEnVivo(agente: "Luna", color: NSColor(red: 0.73, green: 0.64, blue: 1.0, alpha: 1), pasos: 6)
            if op.fantasma { b.alfa = 0.02 }
            actuar.banda = b
            b.alParar = { [weak self] in self?.actuar.banda = nil }
            b.empezar()
            if !foto.isEmpty {
                despues(0.4) { b.foto(foto + "_banda_cuenta.png") }
                despues(3.6) { b.siguientePaso(); b.siguientePaso(); b.foto(foto + "_banda_en_vivo.png") }
                despues(4.4) { b.pausar(); b.foto(foto + "_banda_pausa.png") }
            }
            despues(8) { b.detener() }
        case "aviso":
            jsManos("WSMActuar.disponible(\(Permisos.json(["prendido": true, "etapa": "ensayo", "modos": ["luna": "segundo_plano"]])))")
            jsManos("WSMActuar.aviso(\(Permisos.json(["id": "demo", "ensayo": true, "texto": "Ensayo · lo habría hecho en segundo plano: Escribir en el campo «Asunto», sin Enter", "deshacer": true, "ensename": true])))")
        case "automatizar":
            actuar.pedirAutomatizacion("com.apple.mail", app: "Mail")
        default:
            break
        }
    }
}
