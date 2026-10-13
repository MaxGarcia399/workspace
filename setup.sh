#!/usr/bin/env bash
# Workspace · bootstrap — instala el harness en UNA máquina, de un comando.
#
# Uso (one-liner):
#   curl -fsSL https://raw.githubusercontent.com/MaxGarcia399/workspace/main/setup.sh | bash
#
# O manual:  git clone https://github.com/MaxGarcia399/workspace.git ~/Desktop/Workspace
#            python3 ~/Desktop/Workspace/install.py
#
# Overrides: WORKSPACE_DIR (destino) · WORKSPACE_REPO (org/repo) · WORKSPACE_TOKEN (fork privado).
set -euo pipefail

DEST="${WORKSPACE_DIR:-$HOME/Desktop/Workspace}"
REPO="${WORKSPACE_REPO:-github.com/MaxGarcia399/workspace.git}"

# >>> workspace-preflight (bloque idéntico en setup.sh y dist/setup.sh —
# tests/test_setup_preflight.py lo verifica). Revisa TODO antes de escribir un
# solo archivo y lo explica sin culpar: junta los problemas y los dice juntos,
# cada uno con qué pasa y cómo se arregla. Define PY (un Python >= 3.9) y puede
# mover DEST fuera de una carpeta sincronizada con la nube si DEST es el default.
# Escape (entornos raros): WORKSPACE_SKIP_PREFLIGHT=1.
ws_pf_bad() {
  WS_PF_FAIL=1
  printf '✖ %s\n' "$1"; shift
  for _l in "$@"; do printf '    %s\n' "$_l"; done
}
ws_pf_cloud() {
  # Etiqueta si la ruta vive en una carpeta sincronizada con la nube; nada si no.
  _lc="$(printf '%s' "$1" | tr 'A-Z' 'a-z')"
  case "$_lc" in
    *"/library/mobile documents"*) echo "iCloud Drive"; return ;;
    *"/library/cloudstorage/"*) echo "una carpeta de nube (Library/CloudStorage)"; return ;;
    */onedrive*) echo "OneDrive"; return ;;
    */dropbox|*/dropbox/*) echo "Dropbox"; return ;;
  esac
  # macOS con «Escritorio y Documentos» en iCloud: ~/Desktop y ~/Documents se sincronizan.
  _icd="$HOME/Library/Mobile Documents/com~apple~CloudDocs"
  for _kf in Desktop Documents; do
    if [ -d "$_icd/$_kf" ]; then
      case "$1" in "$HOME/$_kf"|"$HOME/$_kf/"*) echo "iCloud (tu carpeta $_kf se sincroniza)"; return ;; esac
    fi
  done
}
ws_preflight() {
  WS_PF_FAIL=0
  PY=""
  _os="$(uname -s 2>/dev/null || echo desconocido)"
  # macOS sin Command Line Tools: /usr/bin/git y /usr/bin/python3 son ATAJOS que
  # abren un instalador en vez de funcionar — no cuentan como instalados.
  _noclt=0
  if [ "$_os" = "Darwin" ] && ! xcode-select -p >/dev/null 2>&1; then _noclt=1; fi
  _git="$(command -v git 2>/dev/null || true)"
  if [ "$_noclt" = 1 ] && [ "$_git" = "/usr/bin/git" ]; then _git=""; fi
  if [ -z "$_git" ] || ! "$_git" --version >/dev/null 2>&1; then
    if [ "$_noclt" = 1 ]; then
      ws_pf_bad "Falta git. No hiciste nada mal: macOS no lo trae hasta instalar sus herramientas de línea de comandos." \
        "Arreglo: corre  xcode-select --install  , acepta, y vuelve a correr este instalador."
    else
      ws_pf_bad "Falta git (Workspace se descarga y se actualiza con git). No hiciste nada mal: muchas máquinas no lo traen." \
        "Arreglo: instálalo (Linux: sudo apt install git — o el gestor de tu distro; Mac: xcode-select --install) y reintenta."
    fi
  fi
  _vistos=""
  for _c in python3 python; do
    _p="$(command -v "$_c" 2>/dev/null || true)"
    [ -n "$_p" ] || continue
    if [ "$_noclt" = 1 ] && [ "$_p" = "/usr/bin/$_c" ]; then continue; fi
    _v="$("$_p" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null || true)"
    case "$_v" in [0-9]*.[0-9]*) ;; *) continue ;; esac
    _vistos="${_vistos:+$_vistos, }$_v"
    _maj="${_v%%.*}"; _min="${_v#*.}"
    if [ "$_maj" -gt 3 ] || { [ "$_maj" -eq 3 ] && [ "$_min" -ge 9 ]; }; then PY="$_p"; break; fi
  done
  if [ -z "$PY" ]; then
    if [ -n "$_vistos" ]; then
      ws_pf_bad "Tu Python es $_vistos; Workspace necesita Python 3.9 o más nuevo. No hiciste nada mal: es el que trae tu sistema." \
        "Arreglo: instala uno nuevo (https://www.python.org/downloads/ · Mac: brew install python · Linux: el gestor de tu distro); no hace falta quitar el viejo."
    elif [ "$_noclt" = 1 ]; then
      ws_pf_bad "Falta Python 3. No hiciste nada mal: macOS no lo trae hasta instalar sus herramientas de línea de comandos." \
        "Arreglo: corre  xcode-select --install  (o instala Python 3.9+ de https://www.python.org/downloads/) y reintenta."
    else
      ws_pf_bad "No encontré Python 3. Workspace necesita Python 3.9 o más nuevo. No hiciste nada mal: muchas máquinas no lo traen." \
        "Arreglo: instálalo (https://www.python.org/downloads/ · Mac: brew install python · Linux: sudo apt install python3) y reintenta."
    fi
  fi
  # Ubicación: una carpeta sincronizada con la nube bloquea/duplica los archivos
  # del harness. Una instalación que YA existe no se mueve (solo se avisa).
  _nube="$(ws_pf_cloud "$DEST")"
  if [ -n "$_nube" ] && [ -d "$DEST/.git" ]; then
    printf '! %s está en %s; funciona, pero si ves archivos bloqueados o duplicados, muévelo a una carpeta local.\n' "$DEST" "$_nube"
  elif [ -n "$_nube" ] && [ -z "${WORKSPACE_DIR:-}" ]; then
    _alt="$HOME/$(basename "$DEST")"
    printf '· %s se sincroniza con %s (no hiciste nada mal: es un ajuste del sistema).\n' "$DEST" "$_nube"
    printf '  Instalo en una carpeta local en su lugar → %s\n' "$_alt"
    DEST="$_alt"
  elif [ -n "$_nube" ]; then
    ws_pf_bad "La carpeta elegida ($DEST) está en $_nube: la sincronización bloquea y duplica los archivos del harness." \
      "Arreglo: elige una carpeta local, p. ej.:  WORKSPACE_DIR=\"\$HOME/Workspace\"  y reintenta."
  fi
  # Espacio: el código pesa poco, pero motores, logs y cerebros crecen. 200 MB mínimo.
  if [ ! -d "$DEST/.git" ]; then
    _anc="$DEST"
    while [ ! -d "$_anc" ] && [ "$_anc" != "/" ] && [ "$_anc" != "." ]; do _anc="$(dirname "$_anc")"; done
    _kb="$(df -Pk "$_anc" 2>/dev/null | awk 'NR==2 {print $4}' || true)"
    case "$_kb" in
      ''|*[!0-9]*) ;;
      *) if [ "$_kb" -lt 204800 ]; then
           ws_pf_bad "Queda poco espacio libre en el disco de $DEST ($((_kb / 1024)) MB). Workspace necesita al menos 200 MB." \
             "Arreglo: libera espacio (o elige otra carpeta con WORKSPACE_DIR) y reintenta."
         fi ;;
    esac
  fi
  if [ "$WS_PF_FAIL" = 1 ]; then
    echo ""
    echo "No se instaló ni se cambió nada. Arregla lo de arriba y vuelve a correr el mismo comando."
    return 1
  fi
  return 0
}
if [ "${WORKSPACE_SKIP_PREFLIGHT:-}" = "1" ]; then
  PY="$(command -v python3 || command -v python || true)"
else
  ws_preflight || exit 1
fi
if [ "${WORKSPACE_SETUP_PREFLIGHT_ONLY:-}" = "1" ]; then echo "ok  $DEST ($PY)"; exit 0; fi
# <<< workspace-preflight

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
