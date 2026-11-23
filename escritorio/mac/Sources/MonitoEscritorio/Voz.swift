// WORKSPACE · la voz del monito: dictar (hablas → texto en la caja; tú lo mandas) y «Léeme las respuestas».
//
// Quién transcribe: lo nativo de la Mac, EN la Mac (decisión V2; los números, en NOTA_VOZ.md). Nada se instala con
// Workspace y ningún audio sale de tu compu:
//   · macOS 26 o más nuevo: SpeechAnalyzer + SpeechTranscriber. Solo pide Micrófono. Si a la Mac le falta el español,
//     macOS lo baja solo (AssetInventory) y aquí se enseña su avance.
//   · macOS 14 y 15: SFSpeechRecognizer con requiresOnDeviceRecognition, solo si la Mac ya transcribe español aquí
//     mismo (supportsOnDeviceRecognition). Pide Micrófono y Reconocimiento de voz. Si no puede, se dice: nunca en línea.
// Los permisos se piden SOLO al tocar el micrófono por primera vez, después de una frase honesta en la burbuja.
// El micrófono nunca queda abierto: se apaga al soltar, al volver a tocar, al cerrar la barra y a los 120 s.
//
// Lo que decide (camino, permisos, ⌥ Espacio, qué se lee) vive en VozLogica.swift y se prueba suelto.
// Pruebas de punta a punta: --voz-archivo <wav> usa ese archivo EN VEZ del micrófono (nunca se abre el micrófono ni se
// pide un permiso a macOS) y --voz-caso primera|apagado|sin-espanol ensaya la primera vez. Solo por la línea de comando.
import AppKit
import AVFoundation
import Speech

/// Una transcripción en curso: recibe audio y va diciendo el texto (firme: ya no cambia; volátil: lo que va oyendo).
protocol SesionVoz: AnyObject {
    func empezar(formato: AVAudioFormat) async throws
    func dar(_ trozo: AVAudioPCMBuffer)
    /// Ya no hay más audio: termina lo pendiente y entrega el texto final.
    func terminar() async
    func cortar()
}

/// Convierte lo que da el micrófono (o el archivo) al formato que pide quien transcribe.
final class Convertidor {
    let a: AVAudioFormat
    private var conv: AVAudioConverter?
    private var de: AVAudioFormat?

    init(a: AVAudioFormat) { self.a = a }

    func pasar(_ b: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        if b.format == a { return b }
        if de != b.format { conv = AVAudioConverter(from: b.format, to: a); de = b.format }
        guard let conv = conv else { return nil }
        let cabe = AVAudioFrameCount(Double(b.frameLength) * a.sampleRate / b.format.sampleRate) + 64
        guard let o = AVAudioPCMBuffer(pcmFormat: a, frameCapacity: cabe) else { return nil }
        var dado = false
        var e: NSError?
        conv.convert(to: o, error: &e) { _, estado in
            if dado { estado.pointee = .noDataNow; return nil }
            dado = true
            estado.pointee = .haveData
            return b
        }
        return e == nil && o.frameLength > 0 ? o : nil
    }
}

/// macOS 26+: SpeechAnalyzer. En la Mac, sin el permiso de Reconocimiento de voz.
@available(macOS 26.0, *)
final class SesionAnalizador: SesionVoz, @unchecked Sendable {
    let modulo: SpeechTranscriber
    let analizador: SpeechAnalyzer
    let alTexto: @Sendable (String, String) -> Void
    private var entrada: AsyncStream<AnalyzerInput>.Continuation?
    private var conv: Convertidor?
    private var lector: Task<Void, Never>?
    private let candado = NSLock()

    init(idioma: String, alTexto: @escaping @Sendable (String, String) -> Void) {
        // «progresiva»: el texto va saliendo mientras hablas (medido: la primera palabra al segundo). Con solo
        // «volatileResults» no salía nada hasta terminar.
        modulo = SpeechTranscriber(locale: Locale(identifier: idioma), preset: .progressiveTranscription)
        analizador = SpeechAnalyzer(modules: [modulo])
        self.alTexto = alTexto
    }

    /// Si a la Mac le falta el español, macOS lo baja (una vez); `avance` va de 0 a 1. → false si no se pudo.
    func preparar(avance: @escaping @Sendable (Double) -> Void) async -> Bool {
        do {
            guard let pedido = try await AssetInventory.assetInstallationRequest(supporting: [modulo]) else { return true }
            let ojo = pedido.progress.observe(\.fractionCompleted, options: [.initial, .new]) { p, _ in avance(p.fractionCompleted) }
            defer { ojo.invalidate() }
            try await pedido.downloadAndInstall()
            return true
        } catch {
            return false
        }
    }

    func empezar(formato: AVAudioFormat) async throws {
        guard let f = await SpeechAnalyzer.bestAvailableAudioFormat(compatibleWith: [modulo]) else {
            throw NSError(domain: "Voz", code: 1, userInfo: [NSLocalizedDescriptionKey: "sin formato de audio"])
        }
        conv = Convertidor(a: f)
        let (flujo, cont) = AsyncStream<AnalyzerInput>.makeStream()
        candado.withLock { entrada = cont }
        let modulo = self.modulo, alTexto = self.alTexto
        lector = Task {
            var firme = ""
            do {
                for try await r in modulo.results {
                    let t = String(r.text.characters)
                    if r.isFinal { firme += t; alTexto(firme, "") } else { alTexto(firme, t) }
                }
            } catch {}
        }
        try await analizador.start(inputSequence: flujo)
    }

    func dar(_ trozo: AVAudioPCMBuffer) {
        candado.lock(); defer { candado.unlock() }
        guard let e = entrada, let b = conv?.pasar(trozo) else { return }
        e.yield(AnalyzerInput(buffer: b))
    }

    func terminar() async {
        let e = candado.withLock { () -> AsyncStream<AnalyzerInput>.Continuation? in let e = entrada; entrada = nil; return e }
        e?.finish()
        try? await analizador.finalizeAndFinishThroughEndOfInput()
        await lector?.value
    }

    func cortar() {
        candado.lock(); let e = entrada; entrada = nil; candado.unlock()
        e?.finish()
        lector?.cancel()
        let a = analizador
        Task { await a.cancelAndFinishNow() }
    }
}

/// macOS 14 y 15: el reconocedor de siempre, obligado a transcribir EN la Mac.
final class SesionClasica: SesionVoz, @unchecked Sendable {
    let reconocedor: SFSpeechRecognizer?
    let alTexto: @Sendable (String, String) -> Void
    private var pedido: SFSpeechAudioBufferRecognitionRequest?
    private var tarea: SFSpeechRecognitionTask?
    private var fin: CheckedContinuation<Void, Never>?
    private let candado = NSLock()

    init(idioma: String, alTexto: @escaping @Sendable (String, String) -> Void) {
        reconocedor = SFSpeechRecognizer(locale: Locale(identifier: idioma))
        self.alTexto = alTexto
    }

    func empezar(formato: AVAudioFormat) async throws {
        guard let r = reconocedor, r.supportsOnDeviceRecognition else {
            throw NSError(domain: "Voz", code: 2, userInfo: [NSLocalizedDescriptionKey: VozLogica.sinEspanol(mayor: ProcessInfo.processInfo.operatingSystemVersion.majorVersion)])
        }
        let p = SFSpeechAudioBufferRecognitionRequest()
        p.requiresOnDeviceRecognition = true                    // jamás a los servidores de Apple
        p.shouldReportPartialResults = true
        p.addsPunctuation = true
        candado.withLock { pedido = p }
        tarea = r.recognitionTask(with: p) { [weak self] res, error in
            guard let self = self else { return }
            if let res = res {
                let t = res.bestTranscription.formattedString
                if res.isFinal { self.alTexto(t, "") } else { self.alTexto("", t) }
            }
            if error != nil || res?.isFinal == true { self.soltar() }
        }
    }

    private func soltar() {
        candado.lock(); let f = fin; fin = nil; candado.unlock()
        f?.resume()
    }

    func dar(_ trozo: AVAudioPCMBuffer) {
        candado.lock(); defer { candado.unlock() }
        pedido?.append(trozo)
    }

    func terminar() async {
        let p = candado.withLock { () -> SFSpeechAudioBufferRecognitionRequest? in let p = pedido; pedido = nil; return p }
        guard let p = p else { return }
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            candado.withLock { fin = c }
            p.endAudio()
            DispatchQueue.global().asyncAfter(deadline: .now() + 4) { [weak self] in self?.soltar() }   // nunca colgado
        }
    }

    func cortar() {
        candado.lock(); pedido = nil; candado.unlock()
        tarea?.cancel()
        soltar()
    }
}

@MainActor
final class Voz: NSObject {
    enum Fase: String { case reposo, aviso, apagado, preparando, oyendo, escribiendo }

    unowned let monito: Monito
    private(set) var fase = Fase.reposo
    var pulsacion = VozLogica.Pulsacion()
    private var relojAtajo: Timer?
    private var ultimaBaja: CFTimeInterval = 0
    private var guardia: Timer?
    private var sesion: SesionVoz?
    private var motor: AVAudioEngine?
    private var lectorArchivo: Task<Void, Never>?
    private var desde = Date()
    private var sinBarraDesde: Date?
    private var ultimoNivel: CFTimeInterval = 0
    /// Cada dictado tiene su número: lo que llegue de uno anterior ya no se pinta.
    private var vuelta = 0
    private var mac: VozLogica.Mac?
    /// Ensayo (--voz-caso): lo que «contestaría» macOS, sin preguntarle.
    private var ensayoDado: VozLogica.Dado
    private let habla = AVSpeechSynthesizer()
    private var itemLeer: NSMenuItem?
    /// --voz-caso (pruebas): primera · apagado · sin-espanol · sin-parar (el archivo se acaba y sigue «oyendo») ·
    /// guardia (con sin-parar: la barra cerrada apaga el micrófono, como de verdad) · leer.
    nonisolated let casos: [String]

    init(monito: Monito) {
        self.monito = monito
        let casos = monito.op.vozCaso.split(separator: ",").map(String.init)
        ensayoDado = casos.contains("primera") ? .sinDecidir : (casos.contains("apagado") ? .no : .si)
        self.casos = casos
        super.init()
    }

    /// ¿De pruebas? (un archivo en vez del micrófono: nunca se abre el micrófono, no se pregunta nada a macOS y no suena nada)
    var ensayo: Bool { !monito.op.vozArchivo.isEmpty }
    var idioma: String { VozLogica.idioma(preferidos: Locale.preferredLanguages) }

    // MARK: qué puede esta Mac
    private func leerMac() async -> VozLogica.Mac {
        if let m = mac { return m }
        var m = VozLogica.Mac(mayor: ProcessInfo.processInfo.operatingSystemVersion.majorVersion)
        if casos.contains("sin-espanol") { mac = m; return m }
        if #available(macOS 26.0, *), SpeechTranscriber.isAvailable {
            m.analizador = await SpeechTranscriber.supportedLocales.map { $0.identifier(.bcp47) }
        }
        if VozLogica.elegir(idioma, de: m.mayor >= 26 ? m.analizador : []) == nil {
            // el de siempre solo se consulta si hace falta (no pide nada: solo dice si transcribe en la Mac)
            m.enLaMac = Array(Set([idioma, "es-MX", "es-ES", "es-US"])).filter {
                SFSpeechRecognizer(locale: Locale(identifier: $0))?.supportsOnDeviceRecognition == true
            }
        }
        mac = m
        return m
    }

    private func dado(_ s: AVAuthorizationStatus) -> VozLogica.Dado {
        s == .authorized ? .si : (s == .notDetermined ? .sinDecidir : .no)
    }

    private var microfono: VozLogica.Dado {
        ensayo ? ensayoDado : dado(AVCaptureDevice.authorizationStatus(for: .audio))
    }

    private var reconocimiento: VozLogica.Dado {
        if ensayo { return ensayoDado }
        switch SFSpeechRecognizer.authorizationStatus() {
        case .authorized: return .si
        case .notDetermined: return .sinDecidir
        default: return .no
        }
    }

    // MARK: la burbuja (y la ventana del chat grande)
    /// junto5 · dónde se está dictando: en la ventana del chat grande (de ahí vino el toque, o es la que está a la vista
    /// al mantener ⌥ Espacio) o en la burbuja. Lo del dictado va SOLO a esa página; la otra se queda en reposo.
    private(set) var enVentana = false
    private var grande: ChatGrande? { monito.entregas?.ventana }

    private func decir(_ codigo: String) {
        if enVentana { grande?.js(codigo) } else { monito.js(codigo) }
    }

    /// La caja donde se dicta sigue a la vista: la barra de la burbuja, o la ventana del chat grande.
    private var cajaALaVista: Bool { enVentana ? grande?.visible == true : monito.barraAbierta }

    /// Qué puede esta Mac, a las DOS páginas (cada una pinta su micrófono; la ventana lo pide al quedar lista).
    func saludar() {
        Task { [weak self] in
            guard let self = self else { return }
            let c = VozLogica.camino(await self.leerMac(), idioma: self.idioma)
            let k = VozLogica.js("app", ["camino": c.camino.nombre, "atajo": !self.monito.op.sinAtajo, "idioma": c.idioma])
            self.monito.js(k)
            self.grande?.js(k)
        }
    }

    private func pintar(_ f: Fase, _ mas: [String: Any] = [:]) {
        fase = f
        var o = mas
        o["fase"] = f.rawValue
        decir(VozLogica.js("estado", o))
        monito.anotar("voz: " + f.rawValue + ((mas["frase"] as? String).map { " · " + $0 } ?? "") + ((mas["nota"] as? String).map { " · " + $0 } ?? ""))
    }

    func deLaBurbuja(_ d: [String: Any]) {
        switch (d["op"] as? String) ?? "" {
        case "voz_hola":
            saludar()
        case "voz_tocar":
            // en reposo, el toque decide dónde se dicta: en la página que lo pidió
            if fase == .reposo { enVentana = monito.entregas?.origen != nil }
            tocar()
        case "voz_seguir": pedirPermisos()
        case "voz_no", "voz_cancelar":
            // M-4: el aviso de la Mac cierra la barra; ese «cancelar» no es del socio
            guard VozLogica.atiendeCancelar((d["op"] as? String) ?? "", pidiendoPermiso: pidiendoPermiso) else { monito.anotar("voz: (la Mac pregunta: no se cancela)"); return }
            cancelar()
        case "voz_ajustes":
            // tu clic en «Abrir Ajustes» (nunca solo; en un ensayo no se abre nada)
            let k = microfono == .no ? "Privacy_Microphone" : "Privacy_SpeechRecognition"
            if !ensayo, let u = URL(string: "x-apple.systempreferences:com.apple.preference.security?\(k)") { NSWorkspace.shared.open(u) }
            monito.anotar("voz: ajustes " + k)
            pintar(.reposo)
        default: break
        }
    }

    /// El micrófono de la caja: empieza; si ya oye, termina.
    func tocar() {
        switch fase {
        case .oyendo: parar()
        case .aviso, .apagado, .preparando: cancelar()
        case .escribiendo: break
        case .reposo: empezar()
        }
    }

    /// M-4 · entre «empieza» y «ya oye» (o «no se pudo»): un «parar» que llegue aquí se recuerda.
    private var arrancando = false
    /// M-4 · la Mac está preguntando por el micrófono (su aviso le quita el foco a la barra).
    private var pidiendoPermiso = false

    func empezar() {
        guard fase == .reposo else { return }
        callar()
        vuelta += 1
        let v = vuelta
        arrancando = true
        pendienteDeParar = false
        Task { [weak self] in
            guard let self = self else { return }
            let c = VozLogica.camino(await self.leerMac(), idioma: self.idioma)
            guard v == self.vuelta, self.fase == .reposo else { return }
            if case .ninguno(let motivo) = c.camino { self.arrancando = false; self.pintar(.reposo, ["nota": motivo]); return }
            switch VozLogica.paso(c.camino, microfono: self.microfono, reconocimiento: self.reconocimiento) {
            case .avisar(let frase): self.arrancando = false; self.pendienteDeParar = false; self.pintar(.aviso, ["frase": frase])
            case .apagado(let frase): self.arrancando = false; self.pendienteDeParar = false; self.pintar(.apagado, ["frase": frase])
            case .seguir:
                await self.oir(c.camino, c.idioma, v)
                if v == self.vuelta { self.arrancando = false }
            }
        }
    }

    /// «Seguir» en la frase de la primera vez: ahora sí, el aviso de macOS (uno; dos en el camino de siempre).
    private func pedirPermisos() {
        guard fase == .aviso else { return }
        let v = vuelta
        // M-4: desde aquí y hasta que vuelva a oír, lo que cierre la barra es el aviso de la Mac, no el socio
        pidiendoPermiso = true
        Task { [weak self] in
            guard let self = self else { return }
            defer { self.pidiendoPermiso = false }
            if self.ensayo {
                // (--voz-caso aviso-mac: como si el aviso de la Mac estuviera a la vista un rato, quitándole el foco a la barra)
                if self.casos.contains("aviso-mac") { try? await Task.sleep(nanoseconds: 900_000_000) }
                self.ensayoDado = .si
                self.monito.anotar("voz: (ensayo) aquí macOS pediría el Micrófono")
            } else {
                if self.microfono == .sinDecidir { _ = await AVCaptureDevice.requestAccess(for: .audio) }
                let c = VozLogica.camino(await self.leerMac(), idioma: self.idioma).camino
                if c == .clasico, self.microfono == .si, self.reconocimiento == .sinDecidir {
                    _ = await withCheckedContinuation { (k: CheckedContinuation<Bool, Never>) in
                        SFSpeechRecognizer.requestAuthorization { k.resume(returning: $0 == .authorized) }
                    }
                }
            }
            guard v == self.vuelta else { return }
            // el aviso de macOS se lleva el teclado y la barra se cierra sola: se vuelve a abrir, con tu texto
            if !self.enVentana, !self.monito.barraAbierta { self.monito.abrirBarra() }
            self.fase = .reposo
            try? await Task.sleep(nanoseconds: 350_000_000)
            guard v == self.vuelta, self.fase == .reposo else { return }
            let c = VozLogica.camino(await self.leerMac(), idioma: self.idioma)
            switch VozLogica.paso(c.camino, microfono: self.microfono, reconocimiento: self.reconocimiento) {
            case .seguir: await self.oir(c.camino, c.idioma, v)
            case .apagado(let frase): self.pintar(.apagado, ["frase": frase])
            case .avisar: self.pintar(.reposo)                  // cerraste el aviso sin decidir: otra vez será
            }
        }
    }

    // MARK: oír
    private func oir(_ camino: VozLogica.Camino, _ idioma: String, _ v: Int) async {
        let alTexto: @Sendable (String, String) -> Void = { [weak self] firme, volatil in
            DispatchQueue.main.async { MainActor.assumeIsolated {
                guard let self = self, v == self.vuelta, self.fase == .oyendo || self.fase == .escribiendo else { return }
                self.decir(VozLogica.js("dictado", ["firme": firme, "volatil": volatil]))
            } }
        }
        var s: SesionVoz
        if camino == .analizador, #available(macOS 26.0, *) {
            let a = SesionAnalizador(idioma: idioma, alTexto: alTexto)
            pintar(.preparando, ["avance": -1])
            let listo = await a.preparar { [weak self] f in
                DispatchQueue.main.async { MainActor.assumeIsolated {
                    guard let self = self, v == self.vuelta, self.fase == .preparando else { return }
                    self.decir(VozLogica.js("estado", ["fase": "preparando", "avance": f]))
                } }
            }
            guard v == vuelta, fase == .preparando else { return }
            if !listo { pintar(.reposo, ["nota": "No pude preparar el español de la Mac para dictar. Revisa tu conexión y vuelve a tocar el micrófono."]); return }
            s = a
        } else {
            s = SesionClasica(idioma: idioma, alTexto: alTexto)
        }
        do {
            let formato = try abrirFuente(s, v)
            try await s.empezar(formato: formato)
        } catch {
            cerrarFuente()
            s.cortar()
            if v == vuelta { pintar(.reposo, ["nota": "No pude empezar a oír: \(error.localizedDescription)"]) }
            return
        }
        guard v == vuelta else { cerrarFuente(); s.cortar(); return }
        sesion = s
        desde = Date()
        sinBarraDesde = nil
        pintar(.oyendo, ["tope": Int(VozLogica.tope)])
        guardia?.invalidate()
        guardia = Timer.scheduledTimer(withTimeInterval: 0.25, repeats: true) { [weak self] _ in
            MainActor.assumeIsolated { self?.vigilar() }
        }
        arrancando = false
        if pendienteDeParar { pendienteDeParar = false; parar() }
    }

    /// Soltaste ⌥ Espacio antes de que empezara a oír (preparando): en cuanto empiece, termina.
    private var pendienteDeParar = false

    /// El micrófono nunca se queda abierto: a los 120 s, o si la barra lleva cerrada un segundo.
    private func vigilar() {
        guard fase == .oyendo else { return }
        if Date().timeIntervalSince(desde) >= VozLogica.tope { parar(); return }
        if ensayo && !casos.contains("guardia") { return }      // las pruebas dictan con la barra cerrada (no toman tu teclado)
        if cajaALaVista { sinBarraDesde = nil; return }
        if let t = sinBarraDesde {
            if Date().timeIntervalSince(t) >= VozLogica.graciaSinBarra { cancelar() }
        } else { sinBarraDesde = Date() }
    }

    /// Abre el micrófono (o, en pruebas, el archivo) y manda cada trozo a la sesión. → el formato de lo que da.
    private func abrirFuente(_ s: SesionVoz, _ v: Int) throws -> AVAudioFormat {
        let alNivel: @Sendable (Double) -> Void = { [weak self] n in
            DispatchQueue.main.async { MainActor.assumeIsolated {
                guard let self = self, v == self.vuelta, self.fase == .oyendo else { return }
                let ahora = CACurrentMediaTime()
                if ahora - self.ultimoNivel < 0.06 { return }
                self.ultimoNivel = ahora
                self.decir("typeof WSMVoz!=='undefined'&&WSMVoz.nivel(\(String(format: "%.2f", n)))")
            } }
        }
        let trozo: @Sendable (AVAudioPCMBuffer) -> Void = { b in
            s.dar(b)
            if let c = b.floatChannelData { alNivel(VozLogica.nivel(UnsafeBufferPointer(start: c[0], count: Int(b.frameLength)))) }
        }
        if ensayo {
            let archivo = try AVAudioFile(forReading: URL(fileURLWithPath: monito.op.vozArchivo))
            let f = archivo.processingFormat
            lectorArchivo = Task { [weak self] in
                try? await Task.sleep(nanoseconds: 300_000_000)
                while !Task.isCancelled, archivo.framePosition < archivo.length,
                      let b = AVAudioPCMBuffer(pcmFormat: f, frameCapacity: 4096), (try? archivo.read(into: b)) != nil, b.frameLength > 0 {
                    trozo(b)
                    try? await Task.sleep(nanoseconds: UInt64(Double(b.frameLength) / f.sampleRate * 1_000_000_000))   // al paso de hablar
                }
                // «sin-parar»: como un micrófono abierto en un cuarto callado (sigue llegando silencio)
                while !Task.isCancelled, self?.casos.contains("sin-parar") == true,
                      let b = AVAudioPCMBuffer(pcmFormat: f, frameCapacity: 4096) {
                    b.frameLength = 4096
                    trozo(b)
                    try? await Task.sleep(nanoseconds: UInt64(4096 / f.sampleRate * 1_000_000_000))
                }
                if Task.isCancelled { return }
                await MainActor.run { if let self = self, v == self.vuelta, self.fase == .oyendo, !self.casos.contains("sin-parar") { self.parar() } }
            }
            return f
        }
        let m = AVAudioEngine()
        let entrada = m.inputNode
        let f = entrada.outputFormat(forBus: 0)
        if f.sampleRate <= 0 || f.channelCount == 0 {
            throw NSError(domain: "Voz", code: 3, userInfo: [NSLocalizedDescriptionKey: "no encuentro un micrófono en esta Mac"])
        }
        entrada.installTap(onBus: 0, bufferSize: 2048, format: f) { b, _ in trozo(b) }
        m.prepare()
        do { try m.start() } catch { entrada.removeTap(onBus: 0); throw error }
        motor = m
        return f
    }

    private func cerrarFuente() {
        lectorArchivo?.cancel()
        lectorArchivo = nil
        if let m = motor {
            m.inputNode.removeTap(onBus: 0)
            m.stop()
        }
        motor = nil
        guardia?.invalidate()
        guardia = nil
    }

    /// Dejar de oír: el micrófono se apaga YA; lo que faltaba de escribirse termina de caer en la caja. No manda nada.
    func parar() {
        // M-4: si todavía está arrancando (aunque siga «en reposo»), se recuerda: en cuanto empiece a oír, termina
        switch VozLogica.alParar(fase: fase.rawValue, arrancando: arrancando) {
        case .recordar: pendienteDeParar = true; return
        case .nada: pendienteDeParar = false; return
        case .terminar: break
        }
        guard fase == .oyendo, let s = sesion else { return }
        cerrarFuente()
        sesion = nil
        let v = vuelta
        pintar(.escribiendo)
        Task { [weak self] in
            await s.terminar()
            try? await Task.sleep(nanoseconds: 80_000_000)      // el último texto llega por la cola principal
            guard let self = self, v == self.vuelta else { return }
            self.pintar(.reposo, ["listo": true])
        }
    }

    /// Cortar sin esperar (cerraste la barra, «Ahora no», se cierra la app): el micrófono se apaga y no cae más texto.
    func cancelar() {
        vuelta += 1
        pendienteDeParar = false
        arrancando = false
        cerrarFuente()
        sesion?.cortar()
        sesion = nil
        if fase != .reposo { pintar(.reposo) }
    }

    // MARK: ⌥ Espacio (un toque: la barra; mantener: hablar)
    func atajoBaja() {
        let ahora = CACurrentMediaTime()
        let hace = ahora - ultimaBaja
        ultimaBaja = ahora
        hacer(pulsacion.baja(barraAbierta: monito.barraAbierta || grande?.visible == true, enVuelo: monito.actuar?.enVuelo == true, desdeLaAnterior: hace))
    }

    func atajoSube() {
        relojAtajo?.invalidate()
        hacer(pulsacion.sube())
    }

    private func hacer(_ acciones: [VozLogica.Accion]) {
        for a in acciones {
            switch a {
            case .alternar: monito.alternarBarra()
            case .armarReloj:
                relojAtajo?.invalidate()
                relojAtajo = Timer.scheduledTimer(withTimeInterval: VozLogica.mantener, repeats: false) { [weak self] _ in
                    MainActor.assumeIsolated { guard let self = self else { return }; self.hacer(self.pulsacion.vence()) }
                }
            case .empezar:
                // con el chat grande a la vista se dicta ahí (su caja); si no, en la barra de la burbuja
                if fase == .reposo { enVentana = grande?.visible == true }
                if !enVentana, !monito.barraAbierta { monito.abrirBarra() }
                if fase == .reposo { empezar() }
            case .parar:
                parar()
            }
        }
    }

    // MARK: «Léeme las respuestas» (V3-b: apagado de fábrica; la voz de la Mac)
    var leer: Bool {
        get { UserDefaults.standard.bool(forKey: "leerRespuestas") }
        set { UserDefaults.standard.set(newValue, forKey: "leerRespuestas") }
    }

    func agregarAlMenu(_ m: NSMenu) {
        let it = NSMenuItem(title: "Léeme las respuestas", action: #selector(menuLeer(_:)), keyEquivalent: "")
        it.target = self
        it.state = leer ? .on : .off
        it.toolTip = "Tu agente te lee su respuesta con la voz de tu Mac. Se calla si tocas el micrófono o lo apagas aquí."
        m.addItem(it)
        itemLeer = it
    }

    @objc func menuLeer(_ item: NSMenuItem) {
        leer.toggle()
        item.state = leer ? .on : .off
        if !leer { callar() }
    }

    func callar() {
        if habla.isSpeaking { habla.stopSpeaking(at: .immediate) }
    }

    /// Cada línea del puente pasa por aquí: la respuesta final de un turno se lee (si lo prendiste).
    func observar(_ linea: String) {
        guard leer || casos.contains("leer"), let t = VozLogica.respuesta(linea) else { return }
        let texto = VozLogica.paraLeer(t)
        if texto.isEmpty || fase == .oyendo { return }
        if ensayo || monito.op.fantasma { monito.anotar("voz: leería \(texto.count) letras · \(texto.prefix(80))"); return }    // las pruebas no suenan
        callar()
        let u = AVSpeechUtterance(string: texto)
        u.voice = AVSpeechSynthesisVoice(language: idioma) ?? AVSpeechSynthesisVoice(language: "es-MX")
        habla.speak(u)
    }
}
