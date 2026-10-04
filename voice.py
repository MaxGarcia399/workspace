#!/usr/bin/env python3
"""WORKSPACE · voice — dictado por voz GLOBAL, local y privado (F1, macOS).

Push-to-talk por TOGGLE: `workspace voice` una vez arranca la captura del micro;
`workspace voice` de nuevo la termina, transcribe con **whisper.cpp LOCAL** y
**pega el texto donde esté el cursor**. Sirve para CUALQUIER campo — la terminal
de los chats de agente, el navegador, lo que sea (plan: research/design/voz-global).

Decisiones del socio: 100% LOCAL (ningún audio toca la red), toggle, macOS primero.
El atajo global lo enlaza el socio una vez (Atajos de macOS → "ejecutar script"
`workspace voice`); WORKSPACE NO captura un hotkey (evita entitlements/deps).

TODO por SUBPROCESO — cero dependencias de Python (stdlib pura). Binarios externos
(vía `brew`, los verifica `workspace doctor`):
  · captura:      ffmpeg (-f avfoundation) o sox
  · transcripción: whisper.cpp (whisper-cli / whisper-cpp / main)
  · pegado:       pbcopy/pbpaste + osascript (keystroke ⌘V)

Higiene: portapapeles NO destructivo (se guarda y restaura) · WAV temporal
borrado tras transcribir · cota de duración (120s) para no dejar el mic abierto ·
FALLA-SUAVE en cada punto (falta binario/modelo/permiso → mensaje accionable que
apunta a `workspace doctor`, NUNCA un stacktrace).
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
_HINT = "corre `workspace doctor` para instalar/verificar la voz"


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


# ── portapapeles (macOS, NO destructivo) ────────────────────────────────────
def _clip_get():
    try:
        r = subprocess.run(["pbpaste"], capture_output=True, timeout=5)
        return r.stdout if r.returncode == 0 else None
    except Exception:
        return None


def _clip_set(data):
    """`data` = bytes. Devuelve True si se copió."""
    try:
        p = subprocess.run(["pbcopy"], input=data, timeout=5)
        return p.returncode == 0
    except Exception:
        return False


def paste_at_cursor(text, out=print):
    """Pega `text` en el campo activo SIN destruir el portapapeles: guarda el
    actual → copia el texto → ⌘V vía osascript → restaura el original. Devuelve
    True si pegó. Falla-suave (sin osascript/permiso → aviso accionable)."""
    if not _which("osascript"):
        out("VOICE: falta osascript (macOS) — no puedo pegar. " + _HINT)
        return False
    saved = _clip_get()                # puede ser None (portapapeles vacío)
    if not _clip_set(text.encode("utf-8")):
        out("VOICE: no pude escribir el portapapeles (pbcopy)")
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
    finally:
        if saved is not None:          # restaura SOLO si había algo guardado
            time.sleep(0.15)           # deja que el ⌘V consuma el portapapeles
            _clip_set(saved)
    return ok


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
def _start(out=print):
    """Arranca la captura del micro en background y guarda el estado."""
    if sys.platform != "darwin":
        out("VOICE: F1 es solo macOS por ahora (Windows/Linux = F3).")
        return 2
    wav = os.path.join(voice_dir(), "rec-%d.wav" % int(time.time()))
    tool, cmd = _recorder_cmd(wav)
    if not cmd:
        out("VOICE: no hay grabador (ffmpeg o sox). " + _HINT)
        return 2
    os.makedirs(voice_dir(), exist_ok=True)
    try:
        # detached: el grabador sobrevive a que `workspace voice` retorne, hasta
        # el 2º toque (SIGINT) o la cota de %ds.
        p = subprocess.Popen(cmd, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
                             start_new_session=True)
    except Exception as e:
        out("VOICE: no pude arrancar el grabador (%s): %s" % (tool, e))
        return 1
    _save_state({"pid": p.pid, "wav": wav, "tool": tool, "started": int(time.time())})
    _beep()
    out("VOICE: 🎙 grabando… (toca de nuevo para transcribir y pegar · máx %ds)" % MAX_SECONDS)
    return 0


def _stop(out=print):
    """Termina la captura, transcribe y pega. Limpia el estado y el WAV."""
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
    paste_at_cursor(text, out=out)
    preview = text if len(text) <= 60 else text[:57] + "…"
    out("VOICE: ✓ %s" % preview)
    return 0


def _wait_file_closed(pid, timeout=4.0):
    """Espera a que el grabador muera tras el SIGINT (para que el WAV cierre)."""
    t0 = time.time()
    while _alive(pid) and time.time() - t0 < timeout:
        time.sleep(0.1)


def _beep():
    """Señal sonora corta de que arrancó (best-effort, no bloquea)."""
    try:
        if _which("afplay"):
            subprocess.Popen(["afplay", "/System/Library/Sounds/Tink.aiff"],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def _rm(path):
    try:
        if path:
            os.remove(path)
    except OSError:
        pass


def toggle(out=print):
    """El toggle: grabando → termina+transcribe+pega; si no → arranca."""
    return _stop(out=out) if is_recording() else _start(out=out)


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
    out("· pegado      : %s" % ("osascript ✓" if _which("osascript") else "FALTA osascript"))
    if not _which("osascript"):
        faltan.append("osascript")
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
    if "--check" in argv or "-c" in argv:
        return check()
    if "--stop" in argv:               # forzar stop (p.ej. atajo dedicado)
        return _stop()
    if "--start" in argv:
        return _start()
    return toggle()


if __name__ == "__main__":
    sys.exit(main())
