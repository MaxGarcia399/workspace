#!/usr/bin/env python3
"""WORKSPACE · arbol_procesos — correr un programa con tiempo límite sin dejar
procesos vivos ni colgarse al vencer (Windows).

El problema (Windows): `subprocess.run(..., timeout=N)` al vencer mata SOLO al
hijo directo. Los motores que se instalan con npm se lanzan con un `.cmd`
(cursor-agent.cmd, opencode.cmd, openclaw.cmd, copilot.cmd, …): el hijo directo
es cmd.exe y el programa de verdad (node, powershell) es su nieto. Muere cmd.exe,
el nieto sigue vivo con las tuberías de salida abiertas, `communicate()` espera
su fin de archivo para siempre y el nieto queda huérfano. Visto en vivo con
`cursor-agent create-chat` sin cuenta (no termina nunca).

Aquí, al vencer el tiempo, se mata el ÁRBOL entero (`taskkill /T /F`, sin
ventana) mientras el hijo directo todavía vive — `/T` recorre el árbol desde
él — y la salida se recoge con una espera ACOTADA (`ESPERA_TRAS_MATAR`): si
algo fuera del árbol aún tuviera las tuberías, se rinde en vez de colgarse.

  · `run(...)` — misma firma y mismo contrato que `subprocess.run`: devuelve
    `CompletedProcess`, lanza `TimeoutExpired` (con la salida parcial en
    `.stdout`/`.stderr`), `CalledProcessError` con `check=True`, y deja pasar
    las excepciones de arranque (`FileNotFoundError`, …).
  · `matar_arbol(p)` — mata a un `Popen` y a sus descendientes (Windows:
    taskkill /T /F; después `p.kill()` por si taskkill no pudo).

macOS / Linux: `run` le pasa la llamada TAL CUAL a `subprocess.run` (mismos
argumentos, mismo comportamiento que antes). En Windows también, si no hay
tiempo límite o si `subprocess.run`/`Popen` no son los de la biblioteca
estándar (un doble de prueba o un instrumentador los sustituyó: se respeta ese
punto de enganche).

Límite conocido: si el hijo directo ya terminó cuando vence el tiempo (dejó un
nieto vivo con las tuberías), taskkill no puede recorrer el árbol desde él; la
espera acotada evita el cuelgue, pero ese nieto no se alcanza.

Solo stdlib, Python 3.9+. No importa nada de Workspace.
"""
import os
import subprocess

#: Segundos que se espera la salida tras matar el árbol (y que se le da a
#: taskkill). Acotado: un proceso que se escapó del árbol no cuelga a nadie.
ESPERA_TRAS_MATAR = 5.0

_WINDOWS = os.name == "nt"


def _sin_ventana():
    return {"creationflags": getattr(subprocess, "CREATE_NO_WINDOW", 0)} if _WINDOWS else {}


def _taskkill():
    raiz = os.environ.get("SystemRoot") or os.environ.get("windir") or r"C:\Windows"
    tk = os.path.join(raiz, "System32", "taskkill.exe")
    return tk if os.path.isfile(tk) else "taskkill"


def _es_de_la_biblioteca():
    """¿`subprocess.run` y `subprocess.Popen` son los de la biblioteca
    estándar? (Mismo archivo fuente: un doble de prueba vive en otro.)"""
    try:
        a = subprocess.run.__code__.co_filename
        b = subprocess.Popen.__init__.__code__.co_filename
    except AttributeError:
        return False
    return a == b and os.path.basename(a).lower().startswith("subprocess")


def matar_arbol(p):
    """Mata a `p` (un `Popen`) y a todo lo que cuelga de él. Windows: taskkill
    /T /F sin ventana, ANTES de matar al hijo (con el hijo muerto, /T ya no
    encuentra el árbol). Mientras el `Popen` exista, Windows no recicla su PID:
    no se puede matar a un proceso ajeno. Después, `p.kill()` por si taskkill
    no estaba o no pudo. Falla suave: nunca lanza."""
    if _WINDOWS:
        try:
            if p.poll() is None:
                subprocess.run([_taskkill(), "/T", "/F", "/PID", str(p.pid)],
                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=ESPERA_TRAS_MATAR * 6,
                               **_sin_ventana())
        except Exception:
            pass
    try:
        p.kill()
    except Exception:
        pass


def run(*popenargs, **kwargs):
    """`subprocess.run` que en Windows, al vencer `timeout`, mata el árbol de
    procesos y no se cuelga recogiendo la salida. En macOS/Linux (o sin
    timeout) es exactamente `subprocess.run(*popenargs, **kwargs)`."""
    if not _WINDOWS or kwargs.get("timeout") is None or not _es_de_la_biblioteca():
        return subprocess.run(*popenargs, **kwargs)
    return _run_windows(popenargs, dict(kwargs))


def _run_windows(popenargs, kw):
    """Calco de `subprocess.run` (mismas validaciones y excepciones) con un
    solo cambio: al vencer, `matar_arbol` + espera acotada en vez de
    `kill()` + `communicate()` sin límite."""
    timeout = kw.pop("timeout")
    entrada = kw.pop("input", None)
    check = kw.pop("check", False)
    if entrada is not None:
        if kw.get("stdin") is not None:
            raise ValueError("stdin and input arguments may not both be used.")
        kw["stdin"] = subprocess.PIPE
    if kw.pop("capture_output", False):
        if kw.get("stdout") is not None or kw.get("stderr") is not None:
            raise ValueError("stdout and stderr arguments may not be used "
                             "with capture_output.")
        kw["stdout"] = subprocess.PIPE
        kw["stderr"] = subprocess.PIPE
    p = subprocess.Popen(*popenargs, **kw)
    try:
        out, err = p.communicate(entrada, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        matar_arbol(p)
        try:
            exc.stdout, exc.stderr = p.communicate(timeout=ESPERA_TRAS_MATAR)
        except Exception:
            # Algo fuera del árbol aún tiene las tuberías: no se espera más.
            # Los hilos lectores de subprocess son daemon; no se cierran aquí
            # los extremos (cerrarlos esperaría a esos hilos).
            pass
        raise
    except BaseException:
        # Ctrl+C u otro error mientras corría: igual que subprocess.run (mata
        # y relanza), pero al árbol entero y sin esperar sin límite.
        matar_arbol(p)
        try:
            p.wait(timeout=ESPERA_TRAS_MATAR)
        except Exception:
            pass
        raise
    retcode = p.poll()
    if check and retcode:
        raise subprocess.CalledProcessError(retcode, p.args, output=out, stderr=err)
    return subprocess.CompletedProcess(p.args, retcode, out, err)
