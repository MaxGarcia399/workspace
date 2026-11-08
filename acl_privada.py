#!/usr/bin/env python3
"""WORKSPACE · acl_privada — en Windows, un archivo SOLO PARA TI.

En Mac/Linux el modo 0600 ya lo hace (quien escribe el archivo lo pone). En
Windows `chmod` no toca la ACL: el archivo hereda la de su carpeta, y en la
PC del socio `C:\\Users\\<tú>\\.claude` daba lectura a `CodexSandboxUsers`
(QA en Windows, 2026-11-07): la bóveda con la llave de Jev y la bitácora se
podían leer desde el sandbox de Codex.

  solo_mio(ruta)   le pone una DACL PROTEGIDA (no hereda nada) con dos
                   entradas: tu usuario (control total) y SYSTEM (control
                   total). Es lo que se llama al CREAR o reescribir el archivo.
  asegurar(ruta)   lo mismo, una sola vez por proceso y por archivo: para
                   apretar los que ya existían (su primer uso).
  describir(ruta)  {"protegida", "sids", "heredadas"} (diagnóstico y pruebas).

Fuera de Windows no hace nada (True). Stdlib (ctypes → advapi32). Falla-suave:
jamás levanta; si no se puede (un disco sin ACL, otro dueño), UNA línea en
`<estado>/logs/acl.log` y sigue — el archivo se usa igual.
"""
import os
import sys
import threading
import time

#: SYSTEM (S-1-5-18): copias de seguridad, el propio Windows.
SID_SYSTEM = "S-1-5-18"
_HECHOS = set()
_LOCK = threading.Lock()
_AVISADO = []


def _es_windows():
    return os.name == "nt"


def _clave(ruta):
    try:
        return os.path.normcase(os.path.abspath(str(ruta)))
    except Exception:
        return str(ruta)


def _avisar(ruta, motivo):
    """UNA línea por proceso en el log (nunca en pantalla: corre en hooks)."""
    if _AVISADO:
        return
    _AVISADO.append(True)
    try:
        import paths
        d = os.path.join(paths.state_dir(), "logs")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "acl.log"), "a", encoding="utf-8") as fh:
            fh.write("%s no pude dejar %s solo para tu usuario (%s); se usa igual\n"
                     % (time.strftime("%Y-%m-%dT%H:%M:%S"), ruta, motivo))
    except Exception:
        pass


# ── Windows (ctypes) ────────────────────────────────────────────────────────
_SE_FILE_OBJECT = 1
_DACL_SECURITY_INFORMATION = 0x00000004
_PROTECTED_DACL_SECURITY_INFORMATION = 0x80000000
_ACL_REVISION = 2
_FILE_ALL_ACCESS = 0x001F01FF
_TOKEN_QUERY = 0x0008
_TOKEN_USER = 1
_SE_DACL_PROTECTED = 0x1000
_INHERITED_ACE = 0x10
_ACL_SIZE_INFORMATION = 2
_W = {}


def _win():
    """advapi32/kernel32 con sus firmas (una vez). Solo en Windows."""
    if _W:
        return _W
    import ctypes
    from ctypes import wintypes
    adv = ctypes.WinDLL("advapi32", use_last_error=True)
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    PSID = ctypes.c_void_p
    PACL = ctypes.c_void_p

    def f(dll, nombre, res, args):
        fn = getattr(dll, nombre)
        fn.restype, fn.argtypes = res, args
        return fn

    _W.update(
        ctypes=ctypes, wintypes=wintypes,
        GetCurrentProcess=f(k32, "GetCurrentProcess", wintypes.HANDLE, []),
        CloseHandle=f(k32, "CloseHandle", wintypes.BOOL, [wintypes.HANDLE]),
        LocalFree=f(k32, "LocalFree", ctypes.c_void_p, [ctypes.c_void_p]),
        OpenProcessToken=f(adv, "OpenProcessToken", wintypes.BOOL,
                           [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]),
        GetTokenInformation=f(adv, "GetTokenInformation", wintypes.BOOL,
                              [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD,
                               ctypes.POINTER(wintypes.DWORD)]),
        ConvertStringSidToSidW=f(adv, "ConvertStringSidToSidW", wintypes.BOOL,
                                 [wintypes.LPCWSTR, ctypes.POINTER(PSID)]),
        ConvertSidToStringSidW=f(adv, "ConvertSidToStringSidW", wintypes.BOOL,
                                 [PSID, ctypes.POINTER(wintypes.LPWSTR)]),
        GetLengthSid=f(adv, "GetLengthSid", wintypes.DWORD, [PSID]),
        CopySid=f(adv, "CopySid", wintypes.BOOL, [wintypes.DWORD, PSID, PSID]),
        InitializeAcl=f(adv, "InitializeAcl", wintypes.BOOL, [PACL, wintypes.DWORD, wintypes.DWORD]),
        AddAccessAllowedAce=f(adv, "AddAccessAllowedAce", wintypes.BOOL,
                              [PACL, wintypes.DWORD, wintypes.DWORD, PSID]),
        SetNamedSecurityInfoW=f(adv, "SetNamedSecurityInfoW", wintypes.DWORD,
                                [wintypes.LPWSTR, ctypes.c_int, wintypes.DWORD, PSID, PSID, PACL,
                                 PACL]),
        GetNamedSecurityInfoW=f(adv, "GetNamedSecurityInfoW", wintypes.DWORD,
                                [wintypes.LPCWSTR, ctypes.c_int, wintypes.DWORD,
                                 ctypes.POINTER(PSID), ctypes.POINTER(PSID),
                                 ctypes.POINTER(PACL), ctypes.POINTER(PACL),
                                 ctypes.POINTER(ctypes.c_void_p)]),
        GetSecurityDescriptorControl=f(adv, "GetSecurityDescriptorControl", wintypes.BOOL,
                                       [ctypes.c_void_p, ctypes.POINTER(wintypes.WORD),
                                        ctypes.POINTER(wintypes.DWORD)]),
        GetAclInformation=f(adv, "GetAclInformation", wintypes.BOOL,
                            [PACL, ctypes.c_void_p, wintypes.DWORD, ctypes.c_int]),
        GetAce=f(adv, "GetAce", wintypes.BOOL, [PACL, wintypes.DWORD,
                                                ctypes.POINTER(ctypes.c_void_p)]),
    )
    return _W


def _sid_usuario():
    """El SID del usuario de ESTE proceso (copiado a un búfer propio)."""
    W = _win()
    ctypes, wintypes = W["ctypes"], W["wintypes"]
    tok = wintypes.HANDLE()
    if not W["OpenProcessToken"](W["GetCurrentProcess"](), _TOKEN_QUERY, ctypes.byref(tok)):
        raise OSError(ctypes.get_last_error(), "OpenProcessToken")
    try:
        n = wintypes.DWORD(0)
        W["GetTokenInformation"](tok, _TOKEN_USER, None, 0, ctypes.byref(n))
        buf = ctypes.create_string_buffer(max(64, n.value))
        if not W["GetTokenInformation"](tok, _TOKEN_USER, buf, len(buf), ctypes.byref(n)):
            raise OSError(ctypes.get_last_error(), "GetTokenInformation")
        psid = ctypes.c_void_p.from_buffer(buf).value      # TOKEN_USER.User.Sid
        largo = W["GetLengthSid"](psid)
        propio = ctypes.create_string_buffer(largo)
        if not W["CopySid"](largo, propio, psid):
            raise OSError(ctypes.get_last_error(), "CopySid")
        return propio
    finally:
        W["CloseHandle"](tok)


def _sid_texto(texto):
    W = _win()
    ctypes = W["ctypes"]
    p = ctypes.c_void_p()
    if not W["ConvertStringSidToSidW"](texto, ctypes.byref(p)):
        raise OSError(ctypes.get_last_error(), "ConvertStringSidToSidW")
    try:
        largo = W["GetLengthSid"](p)
        propio = ctypes.create_string_buffer(largo)
        if not W["CopySid"](largo, propio, p):
            raise OSError(ctypes.get_last_error(), "CopySid")
        return propio
    finally:
        W["LocalFree"](p)


def _aplicar(ruta):
    """La DACL protegida: tu usuario + SYSTEM, control total, sin herencia."""
    W = _win()
    ctypes = W["ctypes"]
    sids = [_sid_usuario(), _sid_texto(SID_SYSTEM)]
    # ACL (8) + por ACE: ACCESS_ALLOWED_ACE sin SidStart (8) + el SID
    tam = 8 + sum(8 + W["GetLengthSid"](ctypes.cast(s, ctypes.c_void_p)) for s in sids)
    tam = (tam + 3) & ~3
    acl = ctypes.create_string_buffer(tam)
    if not W["InitializeAcl"](acl, tam, _ACL_REVISION):
        raise OSError(ctypes.get_last_error(), "InitializeAcl")
    for s in sids:
        if not W["AddAccessAllowedAce"](acl, _ACL_REVISION, _FILE_ALL_ACCESS,
                                        ctypes.cast(s, ctypes.c_void_p)):
            raise OSError(ctypes.get_last_error(), "AddAccessAllowedAce")
    rc = W["SetNamedSecurityInfoW"](str(ruta), _SE_FILE_OBJECT,
                                    _DACL_SECURITY_INFORMATION
                                    | _PROTECTED_DACL_SECURITY_INFORMATION,
                                    None, None, ctypes.cast(acl, ctypes.c_void_p), None)
    if rc != 0:
        raise OSError(rc, "SetNamedSecurityInfoW")


def describir(ruta):
    """{"protegida": bool, "sids": [str], "heredadas": int} de la DACL (solo
    Windows; None fuera o si no se puede leer)."""
    if not _es_windows():
        return None
    try:
        W = _win()
        ctypes, wintypes = W["ctypes"], W["wintypes"]
        dacl, sd = ctypes.c_void_p(), ctypes.c_void_p()
        rc = W["GetNamedSecurityInfoW"](str(ruta), _SE_FILE_OBJECT, _DACL_SECURITY_INFORMATION,
                                        None, None, ctypes.byref(dacl), None, ctypes.byref(sd))
        if rc != 0:
            return None
        try:
            ctl, rev = wintypes.WORD(), wintypes.DWORD()
            W["GetSecurityDescriptorControl"](sd, ctypes.byref(ctl), ctypes.byref(rev))

            class _Info(ctypes.Structure):
                _fields_ = [("AceCount", wintypes.DWORD), ("AclBytesInUse", wintypes.DWORD),
                            ("AclBytesFree", wintypes.DWORD)]
            info = _Info()
            W["GetAclInformation"](dacl, ctypes.byref(info), ctypes.sizeof(info),
                                   _ACL_SIZE_INFORMATION)
            sids, heredadas = [], 0
            for i in range(info.AceCount):
                ace = ctypes.c_void_p()
                if not W["GetAce"](dacl, i, ctypes.byref(ace)):
                    continue
                flags = ctypes.c_ubyte.from_address(ace.value + 1).value
                if flags & _INHERITED_ACE:
                    heredadas += 1
                txt = wintypes.LPWSTR()
                if W["ConvertSidToStringSidW"](ctypes.c_void_p(ace.value + 8), ctypes.byref(txt)):
                    sids.append(txt.value)
                    W["LocalFree"](ctypes.cast(txt, ctypes.c_void_p))
            return {"protegida": bool(ctl.value & _SE_DACL_PROTECTED), "sids": sids,
                    "heredadas": heredadas}
        finally:
            W["LocalFree"](sd)
    except Exception:
        return None


def sid_usuario_texto():
    """El SID de este proceso como texto (pruebas); None fuera de Windows."""
    if not _es_windows():
        return None
    try:
        W = _win()
        ctypes, wintypes = W["ctypes"], W["wintypes"]
        s = _sid_usuario()
        txt = wintypes.LPWSTR()
        if W["ConvertSidToStringSidW"](ctypes.cast(s, ctypes.c_void_p), ctypes.byref(txt)):
            v = txt.value
            W["LocalFree"](ctypes.cast(txt, ctypes.c_void_p))
            return v
    except Exception:
        pass
    return None


# ── la API ──────────────────────────────────────────────────────────────────
def solo_mio(ruta):
    """El archivo, solo para tu usuario (y SYSTEM). → True si quedó (o si no
    es Windows); False si no se pudo (aviso de una línea en el log)."""
    if not _es_windows():
        return True
    try:
        _aplicar(ruta)
        with _LOCK:
            _HECHOS.add(_clave(ruta))
        return True
    except Exception as e:
        _avisar(ruta, "%s: %s" % (type(e).__name__, e))
        return False


def asegurar(ruta):
    """solo_mio una vez por proceso y archivo (si existe): aprieta los que ya
    estaban, sin repetir la llamada en cada escritura."""
    if not _es_windows():
        return True
    k = _clave(ruta)
    with _LOCK:
        if k in _HECHOS:
            return True
    if not os.path.isfile(ruta):
        return True
    return solo_mio(ruta)


if __name__ == "__main__":                      # diagnóstico: python acl_privada.py <ruta>
    for r in sys.argv[1:]:
        print(r, describir(r))
