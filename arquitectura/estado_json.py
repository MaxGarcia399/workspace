"""Estado JSON local. Las mutaciones toman olock.file_lock sobre la ruta."""
import json
import os
import sys
import time
import uuid

import atomico


def leer(ruta, *, apartar=False, valido=None):
    """Lee un objeto, con BOM opcional. `valido(datos)` revisa su estructura por dentro: un objeto que no la cumple
    (p. ej. un campo que debía ser un objeto y es null) cuenta como dañado, igual que un JSON roto (revisor 5). Solo el
    escritor bajo candado puede apartar el archivo dañado. La operación que lo descubre debe reintentarse."""
    try:
        datos = json.loads(atomico.leer(ruta, encoding="utf-8-sig"))
        if not isinstance(datos, dict):
            raise ValueError("se esperaba un objeto JSON")
        if valido is not None and not valido(datos):
            raise ValueError("la estructura del objeto no es la esperada")
        return datos
    except FileNotFoundError:
        return {}
    except ValueError as e:
        if not apartar:
            return {}
        copia = "%s.corrupt-%s" % (ruta, uuid.uuid4().hex)
        try:
            _apartar(ruta, copia)
        except OSError as fallo:
            print("WORKSPACE · estado dañado en %s y no se pudo apartar: %s" % (ruta, fallo), file=sys.stderr)
            raise
        aviso = "estado dañado en %s, apartado en %s. Vuelve a intentar." % (ruta, copia)
        print("WORKSPACE · " + aviso, file=sys.stderr)
        raise ValueError(aviso) from e


def _apartar(ruta, copia):
    """`os.replace(ruta, copia)` con los reintentos de atomico ante un bloqueo pasajero (Windows: el antivirus o el
    indexador lo abren un instante). A diferencia de atomico.reemplazar, si no se logra el original queda donde
    estaba: nunca se borra."""
    n = atomico.intentos_por_defecto()
    for k in range(n):
        try:
            os.replace(ruta, copia)
            return
        except OSError as e:
            if k < n - 1 and atomico.pasajero(e):
                time.sleep(atomico.ESPERA * (k + 1))
                continue
            raise


def escribir(ruta, datos):
    atomico.escribir(ruta, json.dumps(datos, ensure_ascii=False, indent=1, sort_keys=True), avisar=True)
