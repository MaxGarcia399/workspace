// swift-tools-version:5.9
// WORKSPACE · el monito de escritorio en la Mac: un panel transparente, siempre encima y sin activarse, con el monito
// de la página (WKWebView) en la esquina y el atajo ⌥ Espacio. Sus «manos» de F1 (ver y señalar, nunca actuar):
// AppKit, WebKit, ScreenCaptureKit y Vision del sistema, más AXorcist (MIT) para la accesibilidad (decisión D2-a).
// Logica.swift no usa nada de eso: se prueba suelta (escritorio/mac/Pruebas).
import PackageDescription

let package = Package(
    name: "MonitoEscritorio",
    platforms: [.macOS(.v14)],
    dependencies: [
        // github.com/openclaw/AXorcist · MIT · fijada a una versión exacta (se revisa a mano antes de subirla)
        .package(url: "https://github.com/openclaw/AXorcist.git", exact: "0.2.3")
    ],
    targets: [
        .executableTarget(
            name: "MonitoEscritorio",
            dependencies: [.product(name: "AXorcist", package: "AXorcist")],
            path: "Sources/MonitoEscritorio"
        )
    ]
)
