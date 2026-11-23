// Un AXorcist de mentira, SOLO para la revisión rápida de tipos de la app (tests/test_escritorio.py) sin bajar el
// paquete de verdad: declara lo que la app usa de AXorcist 0.2.3, con las mismas firmas, y no hace nada.
// La compilación de verdad (WORKSPACE_PRUEBA_SWIFT=1, `swift build`) usa el AXorcist real: si su API cambia, ahí se ve.
import AppKit
import ApplicationServices

public struct Attribute<T> {
    public let rawValue: String
    public init(_ rawValue: String) { self.rawValue = rawValue }
}

public struct Element: Equatable, Hashable, @unchecked Sendable {
    public let underlyingElement: AXUIElement
    public init(_ element: AXUIElement) { underlyingElement = element }
    @MainActor public static func application(for pid: pid_t) -> Element? { nil }
    @MainActor public static func elementAtPoint(_ point: CGPoint, pid: pid_t = 0) -> Element? { nil }
    @MainActor public func attribute<T>(_ attribute: Attribute<T>) -> T? { nil }
    @MainActor public func focusedWindow() -> Element? { nil }
    @MainActor public func mainWindow() -> Element? { nil }
    @MainActor public func focusedUIElement() -> Element? { nil }
    @MainActor public func menuBar() -> Element? { nil }
    @MainActor public func children(strict: Bool = false) -> [Element]? { nil }
    @MainActor public func role() -> String? { nil }
    @MainActor public func subrole() -> String? { nil }
    @MainActor public func title() -> String? { nil }
    @MainActor public func descriptionText() -> String? { nil }
    @MainActor public func help() -> String? { nil }
    @MainActor public func value() -> Any? { nil }
    @MainActor public func selectedText() -> String? { nil }
    @MainActor public func url() -> URL? { nil }
    @MainActor public func frame() -> CGRect? { nil }
}

public enum AXPermissionHelpers {
    @MainActor public static func hasAccessibilityPermissions() -> Bool { false }
    @MainActor public static func askForAccessibilityIfNeeded() -> Bool { false }
}
