"""Shared classic-terminal Google connector for onboarding and Calendar."""
import getpass
import os

import google_auth
from i18n import t as _translate


def t(key, fallback):
    value = _translate(key)
    return fallback if value == key else value


def result_message(result):
    if result.get("ok"):
        return t("cal.oauth.connected", "Google conectado · solo lectura")
    error = result.get("error", "failed")
    return t("cal.oauth.error." + error,
             t("cal.oauth.error.failed", "No se pudo conectar Google"))


def connect():
    login = None
    try:
        if not google_auth.configured():
            print(t("cal.oauth.setup", "Workspace necesita un cliente OAuth de escritorio registrado en Google Cloud."))
            print(t("cal.oauth.import", "Arrastra el JSON del cliente a esta terminal (Enter cancela):"))
            path = input("  > ").strip().strip("\"'")
            # Dragging a macOS path escapes spaces; accept it without shell execution.
            path = os.path.expanduser(path.replace("\\ ", " "))
            if not path:
                return {"ok": False, "error": "cancelled"}
            result = google_auth.import_client(path)
            if not result.get("ok"):
                return result
        label = input(t("cal.oauth.label", "Nombre del calendario (Enter = Google): ")).strip()
        print(t("cal.oauth.wait", "Autoriza Calendar en el navegador · Ctrl+C cancela · espera máxima 3 minutos"))
        login = google_auth.Login(label=label or "Google")
        while not login.done.wait(0.2):
            pass
        result = login.result
        if result.get("ok"):
            import gcal
            gcal.invalidate()
            # Fetch in background: the TUI returns immediately after consent.
            gcal.events()
        return result
    except (EOFError, KeyboardInterrupt):
        if login:
            login.cancel()
        return {"ok": False, "error": "cancelled"}
    except Exception:
        if login:
            login.cancel()
        return {"ok": False, "error": "failed"}


def choose_connection():
    """Offer browser authorization first, retain hidden iCal paste as fallback."""
    import gcal
    try:
        choice = input(t("cal.oauth.choose", "1 · Conectar con Google en el navegador   2 · URL iCal   Enter · cancelar\n  > ")).strip()
        if choice == "1":
            return connect()
        if choice != "2":
            return {"ok": False, "error": "cancelled"}
        url = getpass.getpass(t("cal.oauth.ical", "Dirección secreta iCal (oculta): ")).strip()
        if not url:
            return {"ok": False, "error": "cancelled"}
        label = input(t("cal.oauth.label", "Nombre del calendario (Enter = Google): ")).strip()
        return gcal.add_account(label, url)
    except (EOFError, KeyboardInterrupt):
        return {"ok": False, "error": "cancelled"}
