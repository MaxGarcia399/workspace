#!/usr/bin/env python3
"""WORKSPACE · transfer — pasar una tarea a un compañero o agente en UNA línea.

Azúcar sobre el bus de mensajes (messages.py · msgs/*.md): NO reimplementa
nada — resuelve el emisor, manda un handoff (o encargo/broadcast) y dice
dónde lo verá el destinatario.

Uso:
    python3 transfer.py atlas "Research dashboard F3"
    python3 transfer.py atlas "Research F3" --cuerpo "Alcance: el feed."
    python3 transfer.py zenith "Deck Soriana v2" --de max --encargo --ok
    python3 transfer.py all "Se libera v1.4" --tipo broadcast

Emisor si no se pasa `--de`: $WORKSPACE_AGENT → `.claude/socio.local` del
cerebro activo ($WORKSPACE_BRAIN o cwd) → $USER/%USERNAME%.

El destinatario lo ve SIN hacer nada:
  · su statusline, área «equipo» (derecha): `▸ N por atender` al instante;
    al cerrarse (`done`) el equipo ve `▪ <quien> entregó «asunto»`.
  · menú `workspace`, sección MENSAJES: navegar / aprobar / rechazar.
  · archivo plano en <cerebro>/msgs/<id>.md (auditable; viaja por git/Sync).

Cerrar el ciclo (lo hace quien recibe):
    python3 messages.py status <id> claimed   # "lo tomo"
    python3 messages.py status <id> done      # "entregado"

stdlib puro, Mac/Windows; falla-suave: si el cerebro del destinatario no
está en esta máquina, lo dice y sale con código 1 (jamás truena).
"""
import os
import sys

sys.dont_write_bytecode = True
ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def _sender(explicit):
    """Emisor: --de → $WORKSPACE_AGENT → socio.local del cerebro activo → $USER."""
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    env = os.environ.get("WORKSPACE_AGENT", "").strip()
    if env:
        return env
    brain = os.environ.get("WORKSPACE_BRAIN", "").strip() or os.getcwd()
    try:
        with open(os.path.join(brain, ".claude", "socio.local"),
                  encoding="utf-8") as fh:
            s = fh.read().strip()
        if s:
            return s.splitlines()[0].strip()
    except Exception:
        pass
    return (os.environ.get("USER") or os.environ.get("USERNAME") or "socio").strip()


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(
        prog="transfer.py",
        description="Pasar una tarea a un agente/compañero (handoff por default). "
                    "Reusa el bus messages.py; el destinatario lo ve en su "
                    "statusline y en la sección MENSAJES del menú workspace.")
    ap.add_argument("to", help="destinatario (zenith/atlas/argus) o 'all'")
    ap.add_argument("subject", help="asunto corto de la tarea")
    ap.add_argument("--cuerpo", "--body", dest="body", default="",
                    help="contexto/alcance (cuerpo Markdown del mensaje)")
    ap.add_argument("--de", "--from", dest="sender", default="",
                    help="emisor (default: $WORKSPACE_AGENT → socio.local → $USER)")
    ap.add_argument("--tipo", dest="mtype", default="handoff",
                    choices=("handoff", "encargo", "broadcast", "reply"),
                    help="tipo de mensaje (default: handoff)")
    ap.add_argument("--encargo", action="store_true",
                    help="atajo: --tipo encargo")
    ap.add_argument("--ok", "--approval", dest="approval", action="store_true",
                    help="requiere aprobación humana (un socio desde el menú)")
    a = ap.parse_args(argv)

    mtype = "encargo" if a.encargo else a.mtype
    sender = _sender(a.sender)
    try:
        import messages
    except Exception:
        print("transfer: no encontré messages.py junto a este script — "
              "¿instalación de WORKSPACE completa? (workspace doctor)")
        return 1
    ids = messages.send(sender, a.to, mtype, a.subject, a.body,
                        requires_approval=a.approval)
    if not ids:
        print("transfer: no se pudo enviar — el cerebro de '%s' no está en esta "
              "máquina o el destinatario no existe en el registry.\n"
              "  · agentes con cerebro aquí: %s\n"
              "  · revisa con: workspace doctor" % (
                  a.to, ", ".join(sorted(messages.registered_brains())) or "(ninguno)"))
        return 1
    for mid in ids:
        m = messages.find(mid) or {}
        print("listo · %s de %s → %s · «%s»" % (mtype, sender, m.get("to") or a.to,
                                                a.subject.strip()))
        print("  id: %s" % mid)
        print("  archivo: %s" % (m.get("path") or ""))
    print("  lo verá en su statusline (área equipo) y en MENSAJES del menú workspace."
          + ("  [pide aprobación]" if a.approval else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
