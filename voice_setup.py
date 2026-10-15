#!/usr/bin/env python3
"""WORKSPACE · voice_setup — `workspace voice --setup`: instala lo que el
dictado por voz necesita (macOS): whisper.cpp y ffmpeg con Homebrew, y el
modelo base de whisper (~150MB).

Vive APARTE de voice.py a propósito: el dictado es 100% local y voice.py no
toca la red (tests/test_voice.py lo vigila). Preparar la voz sí descarga
(brew + el modelo), y SOLO corre cuando el usuario lo pide — nunca el doctor
ni una actualización (la voz es opcional: cada usuario decide).
Idempotente: lo que ya está, se salta. Stdlib, Python 3.9+.
"""
import os
import subprocess
import sys

import voice

MODEL_URL = ("https://huggingface.co/ggerganov/whisper.cpp/resolve/main/"
             "ggml-base.bin")


def _download_model(dest, out=print):
    """Baja ggml-base a `dest`. Falla-suave (devuelve False)."""
    curl = voice._which("curl")
    if not curl:
        out("VOICE SETUP: falta curl para bajar el modelo; descárgalo a mano: %s → %s"
            % (MODEL_URL, dest))
        return False
    try:
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        r = subprocess.run([curl, "-fsSL", "-o", dest, MODEL_URL], timeout=600)
        return r.returncode == 0 and os.path.isfile(dest)
    except Exception:
        return False


def setup(out=print):
    """Instala lo que falta y termina con el mismo reporte que `--check`."""
    if sys.platform != "darwin":
        out("VOICE SETUP: F1 es solo macOS (este SO: %s)." % sys.platform)
        return 2
    pkgs = []
    if not voice._find_whisper():
        pkgs.append("whisper-cpp")
    if not voice._recorder_cmd("x.wav")[0]:
        pkgs.append("ffmpeg")
    if pkgs:
        brew = voice._which("brew")
        if not brew:
            out("VOICE SETUP: falta Homebrew (https://brew.sh) para instalar: %s"
                % ", ".join(pkgs))
        else:
            out("VOICE SETUP: brew install %s …" % " ".join(pkgs))
            try:
                subprocess.run([brew, "install"] + pkgs, timeout=1800)
            except Exception as e:
                out("VOICE SETUP: brew falló (%s)" % type(e).__name__)
    model = voice.default_model()
    if not os.path.isfile(model):
        out("VOICE SETUP: bajando el modelo de whisper (~150MB) a %s …" % model)
        _download_model(model, out=out)
    return voice.check(out=out)


if __name__ == "__main__":
    sys.exit(setup())
