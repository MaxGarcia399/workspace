#!/usr/bin/env python3
"""WORKSPACE · voice — dictado por voz GLOBAL, local y privado (F1, macOS).

Push-to-talk por TOGGLE: `workspace voice` una vez arranca la captura del micro;
`workspace voice` de nuevo la termina, transcribe con **whisper.cpp LOCAL** y
deja el texto **copiado** (portapapeles + un sonido): lo pegas con ⌘V en
CUALQUIER campo. De fábrica es «solo copiar»: macOS solo pide el micrófono.
`--pegar` además lo pega donde esté el cursor (⌘V vía System Events), que pide
dos permisos más (Automatización y Accesibilidad): se avisan ANTES, la primera
vez (avisos C4/C5 de deliverables/workspace-avisos).

Decisiones del socio: 100% LOCAL (ningún audio toca la red), toggle, macOS primero.
El atajo global lo enlaza el socio una vez (Atajos de macOS → "ejecutar script"
`workspace voice`); WORKSPACE NO captura un hotkey (evita entitlements/deps).

TODO por SUBPROCESO — cero dependencias de Python (stdlib pura). Binarios externos
(vía `brew`; `workspace voice --check` dice qué falta y `workspace voice --setup`
lo instala — la voz es OPCIONAL: el doctor no la revisa ni la instala):
  · captura:      ffmpeg (-f avfoundation) o sox
  · transcripción: whisper.cpp (whisper-cli / whisper-cpp / main)
  · copiado:      pbcopy (de fábrica) · pegado (--pegar): osascript (keystroke ⌘V)

Higiene: el texto queda en el portapapeles (no se lee lo que había: sin
`pbpaste`, sin el aviso de privacidad del portapapeles de macOS) · WAV temporal
borrado tras transcribir · cota de duración (120s) para no dejar el mic abierto ·
FALLA-SUAVE en cada punto (falta binario/modelo/permiso → mensaje accionable que
apunta a `workspace voice --setup`, NUNCA un stacktrace).
"""
import json
import os
import signal
import subprocess
import sys
import time

MAX_SECONDS = 120                      # cota dura: nunca dejar el mic abierto más
SAMPLE_RATE = "16000"                  # whisper.cpp espera 16 kHz mono
WHISPER_NAMES = ("whisper-cli", "whisper-cpp", "main")   # nombres del CLI de whisper.cpp
_HINT = "corre `workspace voice --setup` para instalar lo que falta (`workspace voice --check` para verlo)"


# ── rutas / estado (lockfile) ───────────────────────────────────────────────
def voice_dir():
    """Dir de estado. Override WORKSPACE_VOICE_DIR (tests / per-máquina)."""
    d = os.environ.get("WORKSPACE_VOICE_DIR")
    if not d:
        d = os.path.join(os.path.expanduser("~"), ".workspace", "voice")
    return d


def _state_path():
    return os.path.join(voice_dir(), "state.json")


def _models_dir():
    return os.path.join(voice_dir(), "models")


def default_model():
    """Modelo por default (override WORKSPACE_WHISPER_MODEL)."""
    env = os.environ.get("WORKSPACE_WHISPER_MODEL")
    if env:
        return os.path.expanduser(env)
    return os.path.join(_models_dir(), "ggml-base.bin")


def _load_state():
    try:
        with open(_state_path(), encoding="utf-8") as fh:
            d = json.load(fh)
        return d if isinstance(d, dict) else None
    except (OSError, ValueError):
        return None


def _save_state(d):
    os.makedirs(voice_dir(), exist_ok=True)
    tmp = _state_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(d, fh)
    os.replace(tmp, _state_path())


def _clear_state():
    try:
        os.remove(_state_path())
    except OSError:
        pass


def _alive(pid):
    """¿El proceso `pid` sigue vivo? (señal 0 no mata, solo consulta)."""
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, ValueError):
        return False


def is_recording():
    st = _load_state()
    return bool(st and _alive(st.get("pid")))


# ── binarios (detección, falla-suave) ───────────────────────────────────────
def _which(name):
    import shutil
    return shutil.which(name)


def _find_whisper():
    for n in WHISPER_NAMES:
        p = _which(n)
        if p:
            return p
    return None


def _recorder_cmd(wav):
    """(nombre, argv) del grabador disponible, o (None, None). Prefiere ffmpeg.
    Ambos: 16 kHz mono, cota MAX_SECONDS. SIGINT cierra el WAV limpio."""
    if _which("ffmpeg"):
        return "ffmpeg", ["ffmpeg", "-hide_banner", "-loglevel", "error",
                          "-f", "avfoundation", "-i", ":0",
                          "-ar", SAMPLE_RATE, "-ac", "1",
                          "-t", str(MAX_SECONDS), "-y", wav]
    if _which("sox") or _which("rec"):
        return "sox", ["sox", "-d", "-r", SAMPLE_RATE, "-c", "1", wav,
                       "trim", "0", str(MAX_SECONDS)]
    return None, None


# ── portapapeles (macOS) ────────────────────────────────────────────────────
# Solo se ESCRIBE (pbcopy): leerlo (pbpaste) para guardarlo y restaurarlo abría
# en macOS 26 «¿Permitir que "Terminal" pegue de…?» y ya no hace falta: el
# texto dictado se queda copiado en los dos modos.
def _clip_set(data):
    """`data` = bytes. Devuelve True si se copió."""
    try:
        p = subprocess.run(["pbcopy"], input=data, timeout=5)
        return p.returncode == 0
    except Exception:
        return False


def copy_text(text, out=print):
    """Deja `text` en el portapapeles (pbcopy). True si quedó copiado."""
    if not _clip_set(text.encode("utf-8")):
        out("VOICE: no pude escribir el portapapeles (pbcopy)")
        return False
    return True


def paste_at_cursor(text, out=print):
    """`--pegar`: copia `text` y lo pega en el campo activo (⌘V vía osascript
    → System Events: pide Automatización y Accesibilidad). El texto se queda
    copiado aunque el pegado falle. True si pegó. Falla-suave (sin
    osascript/permiso → aviso accionable)."""
    if not _which("osascript"):
        out("VOICE: falta osascript (macOS) — no puedo pegar. " + _HINT)
        return False
    if not copy_text(text, out=out):
        return False
    try:
        r = subprocess.run(
            ["osascript", "-e", 'tell application "System Events" to keystroke "v" using command down'],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8)
        ok = r.returncode == 0
        if not ok:
            # típico: falta permiso de Accesibilidad para enviar keystrokes
            out("VOICE: no pude pegar (⌘V). ¿Permiso de Accesibilidad? " + _HINT)
    except Exception as e:
        ok = False
        out("VOICE: fallo al pegar: %s" % e)
    return ok


# ── avisos de una línea ANTES de los diálogos de macOS (la primera vez) ──────
def _aviso_una_vez(clave, out=print):
    """Dice el aviso `clave` (avisos_sistema: micrófono / pegar) la PRIMERA
    vez, antes de que macOS pregunte; luego deja una marca en voice_dir()."""
    marca = os.path.join(voice_dir(), "avisado-" + clave.replace(".", "-"))
    if os.path.exists(marca):
        return False
    try:
        import avisos_sistema
        txt = avisos_sistema.texto(clave)
    except Exception:
        txt = ""
    if txt:
        out("VOICE: " + txt)
    try:
        os.makedirs(voice_dir(), exist_ok=True)
        open(marca, "w").close()
    except OSError:
        pass
    return bool(txt)


# ── transcripción (whisper.cpp local) ───────────────────────────────────────
def transcribe(wav, out=print):
    """Corre whisper.cpp sobre `wav` y devuelve el texto, o None (falla-suave)."""
    whisper = _find_whisper()
    if not whisper:
        out("VOICE: whisper.cpp no está instalado. " + _HINT)
        return None
    model = default_model()
    if not os.path.isfile(model):
        out("VOICE: falta el modelo de whisper (%s). %s" % (os.path.basename(model), _HINT))
        return None
    base = os.path.splitext(wav)[0]
    try:
        r = subprocess.run(
            [whisper, "-m", model, "-f", wav, "-otxt", "-of", base, "-nt"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=MAX_SECONDS + 60)
    except Exception as e:
        out("VOICE: fallo al transcribir: %s" % e)
        return None
    if r.returncode != 0:
        out("VOICE: whisper falló (rc %d). %s" % (r.returncode, _HINT))
        return None
    txt = base + ".txt"
    try:
        with open(txt, encoding="utf-8") as fh:
            text = fh.read().strip()
    except OSError:
        text = (r.stdout or "").strip()       # fallback: stdout de whisper
    finally:
        try:
            os.remove(txt)
        except OSError:
            pass
    return text or None


# ── el toggle ────────────────────────────────────────────────────────────────
def _start(out=print, pegar=False):
    """Arranca la captura del micro en background y guarda el estado (con el
    modo: `pegar` lo pega al terminar; si no, solo lo copia)."""
    if sys.platform != "darwin":
        out("VOICE: F1 es solo macOS por ahora (Windows/Linux = F3).")
        return 2
    wav = os.path.join(voice_dir(), "rec-%d.wav" % int(time.time()))
    tool, cmd = _recorder_cmd(wav)
    if not cmd:
        out("VOICE: no hay grabador (ffmpeg o sox). " + _HINT)
        return 2
    os.makedirs(voice_dir(), exist_ok=True)
    _aviso_una_vez("voz.microfono", out=out)       # antes del diálogo del micro
    if pegar:
        _aviso_una_vez("voz.pegar", out=out)       # antes de Automatización/Accesibilidad
    try:
        # detached: el grabador sobrevive a que `workspace voice` retorne, hasta
        # el 2º toque (SIGINT) o la cota de %ds.
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                             start_new_session=True)
    except Exception as e:
        out("VOICE: no pude arrancar el grabador (%s): %s" % (tool, e))
        return 1
    _save_state({"pid": p.pid, "wav": wav, "tool": tool, "started": int(time.time()),
                 "pegar": bool(pegar)})
    _beep()
    out("VOICE: 🎙 grabando… (toca de nuevo para transcribir y %s · máx %ds)"
        % ("pegar" if pegar else "copiar", MAX_SECONDS))
    return 0


def _stop(out=print, pegar=False):
    """Termina la captura, transcribe y deja el texto copiado (o, con
    `--pegar` al arrancar o al terminar, lo pega). Limpia el estado y el WAV."""
    st = _load_state()
    if not st:
        out("VOICE: no estaba grabando.")
        return 0
    wav = st.get("wav")
    pid = st.get("pid")
    if _alive(pid):
        try:
            os.kill(int(pid), signal.SIGINT)   # cierra el WAV limpio
        except (OSError, ValueError):
            pass
        _wait_file_closed(pid)
    _clear_state()
    if not wav or not os.path.isfile(wav) or os.path.getsize(wav) < 1024:
        out("VOICE: no se capturó audio (¿permiso de micrófono?). " + _HINT)
        _rm(wav)
        return 1
    out("VOICE: transcribiendo…")
    text = transcribe(wav, out=out)
    _rm(wav)
    if not text:
        return 1                       # transcribe ya explicó el porqué
    preview = text if len(text) <= 60 else text[:57] + "…"
    if pegar or st.get("pegar"):
        if paste_at_cursor(text, out=out):
            out("VOICE: ✓ %s" % preview)
            return 0
        if not copy_text(text, out=out):   # sin pegar, igual queda copiado
            return 1
        _beep("Glass")
        out("VOICE: quedó copiado: pégalo con ⌘V · %s" % preview)
        return 0
    if not copy_text(text, out=out):
        return 1
    _beep("Glass")                     # el aviso de que ya está listo para pegar
    out("VOICE: ✓ copiado — pégalo con ⌘V · %s" % preview)
    return 0


def _wait_file_closed(pid, timeout=4.0):
    """Espera a que el grabador muera tras el SIGINT (para que el WAV cierre)."""
    t0 = time.time()
    while _alive(pid) and time.time() - t0 < timeout:
        time.sleep(0.1)


def _beep(sonido="Tink"):
    """Señal sonora corta (best-effort, no bloquea): Tink al arrancar a grabar,
    Glass cuando el texto ya está copiado."""
    try:
        if _which("afplay"):
            subprocess.Popen(["afplay", "/System/Library/Sounds/%s.aiff" % sonido],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _rm(path):
    try:
        if path:
            os.remove(path)
    except OSError:
        pass


def toggle(out=print, pegar=False):
    """El toggle: grabando → termina+transcribe+copia (o pega); si no → arranca."""
    return _stop(out=out, pegar=pegar) if is_recording() else _start(out=out, pegar=pegar)


# ── --check (qué falta) ──────────────────────────────────────────────────────
def check(out=print):
    """Reporta qué necesita la voz para funcionar. rc 0 = todo listo."""
    faltan = []
    if sys.platform != "darwin":
        out("VOICE CHECK: F1 es solo macOS (este SO: %s)." % sys.platform)
        return 2
    whisper = _find_whisper()
    out("· whisper.cpp : %s" % (whisper or "FALTA (brew install whisper-cpp)"))
    if not whisper:
        faltan.append("whisper.cpp")
    model = default_model()
    out("· modelo      : %s" % (model if os.path.isfile(model) else "FALTA (%s)" % os.path.basename(model)))
    if not os.path.isfile(model):
        faltan.append("modelo")
    tool, _ = _recorder_cmd("x.wav")
    out("· grabador    : %s" % (tool or "FALTA (brew install ffmpeg)"))
    if not tool:
        faltan.append("grabador (ffmpeg/sox)")
    out("· copiado     : %s" % ("pbcopy ✓ (de fábrica: el texto queda copiado)"
                                  if _which("pbcopy") else "FALTA pbcopy"))
    if not _which("pbcopy"):
        faltan.append("pbcopy")
    out("· pegar solo  : %s" % ("opcional con --pegar (osascript ✓; macOS pide "
                                 "Automatización y Accesibilidad)" if _which("osascript")
                                 else "opcional con --pegar (falta osascript)"))
    if faltan:
        out("VOICE CHECK: falta → %s · %s" % (", ".join(faltan), _HINT))
        out("Atajo global: enlaza `workspace voice` en Atajos de macOS con una tecla "
            "(Ajustes → Teclado → Atajos, o la app Atajos → 'Ejecutar script de shell').")
        return 1
    out("VOICE CHECK: todo listo ✓ · enlaza `workspace voice` a un atajo de teclado en Atajos de macOS.")
    return 0


# ── CLI ──────────────────────────────────────────────────────────────────────
def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--setup" in argv:              # instalar (red: brew + modelo) vive APARTE:
        import voice_setup             # este módulo jamás toca la red
        return voice_setup.setup()
    if "--check" in argv or "-c" in argv:
        return check()
    pegar = "--pegar" in argv or "--paste" in argv
    if "--stop" in argv:               # forzar stop (p.ej. atajo dedicado)
        return _stop(pegar=pegar)
    if "--start" in argv:
        return _start(pegar=pegar)
    return toggle(pegar=pegar)


if __name__ == "__main__":
    sys.exit(main())
