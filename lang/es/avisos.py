"""WORKSPACE · lang/es/avisos — avisos de UNA línea antes de una acción opcional
que dispara un diálogo del sistema (avisos_sistema.py). FUENTE (español).

Textos de deliverables/workspace-avisos (tabla, columna «aviso previo»). La
página para el socio que explica cada uno: manual/es/avisos.md.
"""

STRINGS = {
    # B1 · Windows · Codex prepara su espacio seguro (UAC) la primera vez
    "avisos.motor.codex_win": "La primera vez, Codex le pide a Windows permiso de administrador "
                              "para preparar su espacio seguro. Es de Codex (OpenAI), no de "
                              "Workspace. Toca Sí; si tu PC es de la empresa y no puedes, "
                              "pídeselo a tu área de TI.",
    # B2 · Windows · el MSI oficial de Kiro (UAC)
    "avisos.motor.kiro_win": "El instalador oficial de Kiro va a pedir permiso de administrador: "
                             "se instala para toda la PC. Toca Sí.",
    # B5 · Mac · Kiro deja un ítem en segundo plano
    "avisos.motor.kiro_mac": "macOS puede avisar que Kiro agregó un elemento en segundo plano: es "
                             "parte de Kiro. Puedes dejarlo; se apaga en Ajustes → General → "
                             "Ítems de inicio.",
    # C2 · Mac · leer el JSON de Google (normalmente en Descargas)
    "avisos.google.descargas": "macOS te va a preguntar si tu terminal puede abrir tu carpeta "
                               "Descargas: es para leer el archivo que bajaste de Google. Toca "
                               "Permitir.",
    # C3 · navegador · app OAuth propia sin verificar
    "avisos.google.no_verificada": "Google va a decir que «no verificó esta app»: es tu propia "
                                   "app, la que creaste en Google Cloud. Toca «Avanzado» y luego "
                                   "«Ir a…».",
    # C1 · Mac · Descubrir con Escritorio/Documentos (a pedido)
    "avisos.descubrir.protegidas": "Para buscar también en Escritorio y Documentos, macOS te va a "
                                   "preguntar por cada carpeta (y por iCloud Drive si tus bóvedas "
                                   "están ahí): Permitir deja que encuentre tus cerebros; si dices "
                                   "No, no pasa nada y sigo con lo demás.",
    "avisos.descubrir.confirma": "e otra vez para buscar ahí · cualquier otra tecla, no",
    "avisos.descubrir.tecla": "también Escritorio/Documentos",
    # C4 · Mac · voz
    "avisos.voz.microfono": "Para dictar, macOS te va a pedir el micrófono (para oírte). El audio "
                            "no sale de tu Mac.",
    "avisos.voz.pegar": "Para pegar solo, macOS te va a pedir dos permisos más: controlar «System "
                        "Events» y Accesibilidad (para pegar el texto donde está tu cursor). Si "
                        "dices No, el texto igual queda copiado: pégalo con ⌘V.",
}
