"""WORKSPACE · lang/en/avisos — one-line notices before an optional action that
triggers a system dialog (avisos_sistema.py). Translation of lang/es/avisos.py.

The page that explains each one: manual/en/system-notices.md.
"""

STRINGS = {
    "avisos.motor.codex_win": "The first time, Codex asks Windows for administrator permission to "
                              "set up its safe space. It's Codex's (OpenAI's), not Workspace's. "
                              "Choose Yes; if it's a company PC and you can't, ask your IT team.",
    "avisos.motor.kiro_win": "Kiro's official installer will ask for administrator permission: it "
                             "installs for the whole PC. Choose Yes.",
    "avisos.motor.kiro_mac": "macOS may say that Kiro added a background item: it's part of Kiro. "
                             "You can leave it; it's turned off in Settings → General → Login "
                             "Items.",
    "avisos.google.descargas": "macOS will ask whether your terminal may open your Downloads "
                               "folder: it's to read the file you downloaded from Google. Choose "
                               "Allow.",
    "avisos.google.no_verificada": "Google will say it \"hasn't verified this app\": it's your own "
                                   "app, the one you created in Google Cloud. Choose \"Advanced\" "
                                   "and then \"Go to…\".",
    "avisos.descubrir.protegidas": "To also look in Desktop and Documents, macOS will ask about "
                                   "each folder (and about iCloud Drive if your vaults live "
                                   "there): Allow lets me find your brains; if you say No, nothing "
                                   "happens and I go on with the rest.",
    "avisos.descubrir.confirma": "e again to look there · any other key, no",
    "avisos.descubrir.tecla": "also Desktop/Documents",
    "avisos.voz.microfono": "To dictate, macOS will ask for the microphone (to hear you). The audio "
                            "never leaves your Mac.",
    "avisos.voz.pegar": "To paste on its own, macOS will ask for two more permissions: control "
                        "\"System Events\" and Accessibility (to paste the text where your cursor "
                        "is). If you say No, the text is still copied: paste it with ⌘V.",
}
