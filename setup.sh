#!/usr/bin/env bash
# WORKSPACE · bootstrap de DISTRIBUCIÓN — instala el harness (vacío) en UNA máquina, de un comando.
# (Este es el setup.sh que vive en el repo de distribución `workspace-harness`, NO el del equipo.)
#
# Uso — repo PÚBLICO (one-liner limpio, sin token):
#   curl -fsSL https://raw.githubusercontent.com/<tu-org>/workspace-harness/main/setup.sh | bash -s -- --socio TU-NOMBRE
#
# Uso — repo PRIVADO (con token de lectura):
#   WORKSPACE_TOKEN=ghp_xxx bash -c "$(curl -fsSL https://TU-NOMBRE:$WORKSPACE_TOKEN@raw.githubusercontent.com/<tu-org>/workspace-harness/main/setup.sh)" -- --socio TU-NOMBRE
#   (o simplemente: git clone con tu acceso + python3 WORKSPACE/install.py --socio TU-NOMBRE)
#
# El repo de distribución se configura con WORKSPACE_REPO (org/repo de tu instalación).
set -euo pipefail

DEST="${WORKSPACE_DIR:-$HOME/Desktop/WORKSPACE}"
REPO="${WORKSPACE_REPO:-github.com/<tu-org>/workspace-harness.git}"

command -v git >/dev/null 2>&1 || { echo "✖ git no está instalado. Instálalo y reintenta."; exit 1; }
PY="$(command -v python3 || command -v python || true)"
[ -n "$PY" ] || { echo "✖ Python 3 no está instalado."; exit 1; }

if [ -n "${WORKSPACE_TOKEN:-}" ]; then URL="https://${WORKSPACE_TOKEN}@${REPO}"; else URL="https://${REPO}"; fi

echo "WORKSPACE (harness) → $DEST"
if [ -d "$DEST/.git" ]; then
  echo "· Ya está instalado; actualizando…"
  git -C "$DEST" pull --ff-only
elif [ -d "$DEST" ]; then
  BK="${DEST}_backup_$(date +%Y%m%d%H%M%S)"
  echo "· Respaldando copia previa → $BK"
  mv "$DEST" "$BK"
  git clone "$URL" "$DEST"
else
  git clone "$URL" "$DEST"
fi

# Higiene de token: nunca dejarlo persistido en el remote (idempotente).
# Si se clonó con WORKSPACE_TOKEN, .git/config quedaría con el token en texto plano
# para SIEMPRE — lo limpiamos a la URL sin token. El auto-update usa las credenciales
# de la máquina (gh auth / credential manager). Espejo de setup.ps1.
if git -C "$DEST" remote get-url origin 2>/dev/null | grep -q "@"; then
  git -C "$DEST" remote set-url origin "https://${REPO}"
fi

echo "· Instalando (comando workspace + hooks)…"
"$PY" "$DEST/install.py" "$@"        # pasa --socio TU-NOMBRE (y lo que agregues)

echo ""
echo "✓ Listo. Abre una terminal NUEVA y escribe:  workspace"
echo "  → menú vacío → 'Agregar agente' (crear o cargar tu cerebro)."
echo "  Para actualizar después:  workspace update   (o solo al abrir)."
