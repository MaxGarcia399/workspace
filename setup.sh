#!/usr/bin/env bash
# Workspace · bootstrap — instala el harness en UNA máquina, de un comando.
#
# Uso (one-liner):
#   curl -fsSL https://raw.githubusercontent.com/MaxGarcia399/workspace/main/setup.sh | bash
#
# O manual:  git clone https://github.com/MaxGarcia399/workspace.git ~/Workspace
#            python3 ~/Workspace/install.py
#
# Overrides: WORKSPACE_DIR (destino) · WORKSPACE_REPO (org/repo) · WORKSPACE_TOKEN (fork privado).
# Todo lo que hace, en pantalla (en lugar de los cuatro pasos):  … | bash -s -- --detalle
set -euo pipefail

# Instalación nueva → ~/Workspace. Si ya tienes Workspace en otro lado (p. ej.
# ~/Desktop/Workspace), el preflight lo detecta y lo actualiza ahí (ws_pf_dest).
DEST_NUEVO="$HOME/Workspace"
REPO="${WORKSPACE_REPO:-github.com/MaxGarcia399/workspace.git}"

# >>> workspace-vista (bloque idéntico en setup.sh y dist/setup.sh — tests/test_instalar_vista.py
# lo verifica y compara lo que escribe, byte por byte, con instalar_vista.py: mismas filas,
# columnas y colores). O2-a «Una línea viva»: con una terminal de verdad (y de 80×24 o más),
# arriba la marca, cuatro pasos que se palomean en su lugar y los errores en una tarjeta que
# dice qué pasó y qué hago yo. Este script pinta los pasos 1-2 (revisar y descargar);
# install.py, el monito y el resto, sobre las mismas filas. Sin terminal (CI, scripts, ssh sin
# tty), con --detalle o con WORKSPACE_NO_ABRIR=1: el texto de siempre, completo.
# Bash 3.2 (el de la Mac): sin arreglos asociativos, sin ${v,,} ni printf -v. Las columnas van
# con salto de columna (ESC[nG): bash 3.2 cuenta bytes, no letras.
ABRIR=0
TERMINAL=""
WS_VIVO=0
WS_FILA=0
WS_DETALLE=0
WS_T0="$(date +%s 2>/dev/null || echo 0)"
for _a in "$@"; do if [ "$_a" = "--detalle" ]; then WS_DETALLE=1; fi; done
if [ "${WORKSPACE_INSTALL_DETALLE:-}" = "1" ]; then WS_DETALLE=1; fi
# Workspace abre AQUÍ MISMO al terminar (I-a) solo con una terminal de verdad: con
# `curl … | bash` la entrada es el script, no el teclado, así que abre leyendo de la
# terminal por su nombre REAL (la de la salida, p. ej. /dev/ttys003). No sirve `</dev/tty`:
# en macOS kqueue no acepta ese alias y Claude Code (Bun), abierto después desde el hub, se
# cae con «EINVAL kqueue» (prueba N5 del 19-nov). Escape: WORKSPACE_NO_ABRIR=1.
if [ -z "${WORKSPACE_NO_ABRIR:-}" ] && [ -t 1 ]; then
  exec 3>&1
  TERMINAL="$(tty <&3 2>/dev/null || true)"
  exec 3>&-
  case "$TERMINAL" in
    /dev/tty) TERMINAL="" ;;
    /dev/*) if [ -r "$TERMINAL" ] && [ -w "$TERMINAL" ]; then ABRIR=1; fi ;;
    *) TERMINAL="" ;;
  esac
fi
if [ "$ABRIR" = 1 ] && [ "$WS_DETALLE" = 0 ] && [ "${TERM:-dumb}" != "dumb" ]; then
  WS_VIVO=1
  _tam="$(stty size <"$TERMINAL" 2>/dev/null || true)"
  case "$_tam" in
    [0-9]*" "[0-9]*) if [ "${_tam% *}" -lt 24 ] || [ "${_tam#* }" -lt 80 ]; then WS_VIVO=0; fi ;;
  esac
fi
WS_R=$'\033[0m'
WS_B=$'\033[1m'
WS_OK=""
WS_AC=""
WS_AV=""
WS_TN=""
if [ -z "${NO_COLOR:-}" ]; then
  _m="${WORKSPACE_COLOR:-}"
  case "$_m" in
    24|256) ;;
    *)
      _m=256
      if [ "${TERM_PROGRAM:-}" = "Apple_Terminal" ]; then
        _bld="${TERM_PROGRAM_VERSION:-}"
        _bld="${_bld%%.*}"
        case "$_bld" in ''|*[!0-9]*) ;; *) if [ "$_bld" -ge 470 ]; then _m=24; fi ;; esac
      else
        case "$(printf '%s' "${COLORTERM:-}" | tr 'A-Z' 'a-z')" in truecolor|24bit) _m=24 ;; esac
      fi ;;
  esac
  if [ "$_m" = 24 ]; then
    WS_OK=$'\033[38;2;63;191;127m'
    WS_AC=$'\033[38;2;255;79;163m'
    WS_AV=$'\033[38;2;231;164;58m'
    WS_TN=$'\033[38;2;138;138;148m'
  else
    WS_OK=$'\033[38;5;72m'
    WS_AC=$'\033[38;5;205m'
    WS_AV=$'\033[38;5;179m'
    WS_TN=$'\033[38;5;245m'
  fi
fi
case "$(uname -s 2>/dev/null || true)" in
  Darwin) WS_DONDE="tu Mac"; WS_PASO1="Reviso tu Mac" ;;
  *) WS_DONDE="tu computadora"; WS_PASO1="Reviso tu computadora" ;;
esac
ws_ir() {
  # El cursor a la columna 1 de la fila $1 del bloque, con movimientos relativos (sobreviven al scroll).
  _d=$(( $1 - WS_FILA ))
  if [ "$_d" -lt 0 ]; then printf '\033[%dA' "$(( 0 - _d ))"; elif [ "$_d" -gt 0 ]; then printf '\033[%dB' "$_d"; fi
  printf '\r'
  WS_FILA=$1
}
ws_linea() {
  # Reescribe la fila $1 entera con $2 (ya trae sus colores).
  ws_ir "$1"
  printf '\033[K%s' "$2"
}
ws_abajo() {
  # Una fila nueva debajo de la última del bloque, con $1.
  printf '\n\r\033[K%s' "$1"
  WS_FILA=$(( WS_FILA + 1 ))
}
ws_paso_txt() {
  # El texto de un paso: ws_paso_txt hecho|ahora|error|falta TÍTULO [DETALLE].
  case "$1" in
    hecho) _g="${WS_OK}${WS_B}✓${WS_R}"; _t="$(ws_pasado "$2")"; _dc="$WS_TN" ;;
    ahora) _g="${WS_AC}${WS_B}◐${WS_R}"; _t="${WS_B}$2${WS_R}"; _dc="$WS_TN" ;;
    error) _g="${WS_AV}${WS_B}✖${WS_R}"; _t="${WS_B}$2${WS_R}"; _dc="$WS_AV" ;;
    *) _g="${WS_TN}·${WS_R}"; _t="${WS_TN}$2${WS_R}"; _dc="$WS_TN" ;;
  esac
  printf '   %s\033[7G%s\033[28G%s%s%s' "$_g" "$_t" "$_dc" "${3:-}" "$WS_R"
}
ws_pasado() {
  case "$1" in
    "Reviso "*) printf 'Revisé %s' "${1#Reviso }" ;;
    "Descargo "*) printf 'Descargué %s' "${1#Descargo }" ;;
    "Preparo "*) printf 'Preparé %s' "${1#Preparo }" ;;
    *) printf '%s' "$1" ;;
  esac
}
ws_paso() {
  # ws_paso N ESTADO TÍTULO [DETALLE] — la fila del paso N (1..4).
  if [ "$WS_VIVO" = 1 ]; then ws_linea $(( 5 + $1 )) "$(ws_paso_txt "$2" "$3" "${4:-}")"; fi
}
ws_barra_txt() {
  # La barra con el paso $1 en curso (0..3): (k + ½) / 4 llena y «k+1 de 4».
  _n=$(( 24 * (2 * $1 + 1) / 8 ))
  _ll=""
  _va=""
  _i=0
  while [ "$_i" -lt 24 ]; do
    if [ "$_i" -lt "$_n" ]; then _ll="${_ll}━"; else _va="${_va}─"; fi
    _i=$(( _i + 1 ))
  done
  printf '   %s%s%s%s%s  %s%d de 4%s' "$WS_AC" "$_ll" "$WS_TN" "$_va" "$WS_R" "$WS_TN" "$(( $1 + 1 ))" "$WS_R"
}
ws_barra() {
  if [ "$WS_VIVO" = 1 ]; then ws_linea 11 "$(ws_barra_txt "$1")"; ws_ir 12; fi
}
ws_marca_txt() {
  # Las tres líneas de la marca (fila 1..3), sin el monito: lo pone install.py al llegar.
  case "$1" in
    1) printf '\033[15G%s%s❯%s %sworkspace%s%s' "$WS_AC" "$WS_B" "$WS_R" "$WS_B" "$WS_R" "$WS_R" ;;
    2) printf '\033[15GLo instalo en %s. Toma un minuto.%s' "$WS_DONDE" "$WS_R" ;;
    3) printf '\033[15G%sSin cuentas nuevas · se quita con «workspace uninstall»%s%s' "$WS_TN" "$WS_R" "$WS_R" ;;
  esac
}
ws_tarjeta() {
  # ws_tarjeta TÍTULO LÍNEA…: tarjeta ámbar desde la fila 11 (lo de abajo se borra antes). Cada
  # línea ya trae sus colores y cabe en 70 columnas. Deja el cursor en su última fila.
  ws_ir 11
  printf '\033[J'
  _top="╭"
  _bot="╰"
  _i=2
  while [ "$_i" -lt 76 ]; do _top="${_top}─"; _bot="${_bot}─"; _i=$(( _i + 1 )); done
  printf '\033[K  %s%s╮%s\033[5G %s%s%s%s ' "$WS_AV" "$_top" "$WS_R" "$WS_AV" "$WS_B" "$1" "$WS_R"
  shift
  ws_abajo "  ${WS_AV}│${WS_R}  "$'\033[78G'"${WS_AV}│${WS_R}"
  for _l in "$@"; do ws_abajo "  ${WS_AV}│${WS_R}  ${_l}"$'\033[78G'"${WS_AV}│${WS_R}"; done
  ws_abajo "  ${WS_AV}│${WS_R}  "$'\033[78G'"${WS_AV}│${WS_R}"
  ws_abajo "  ${WS_AV}${_bot}╯${WS_R}"
}
ws_sin_tarjeta() {
  # Quita la tarjeta (el problema se arregló) y deja el cursor en su casa (fila 12).
  ws_ir 11
  printf '\033[J'
}
ws_girar() {
  # ws_girar PID FILA: el ◐ de esa fila da vueltas mientras PID vive. Deja el cursor en la fila 12.
  _i=0
  while kill -0 "$1" 2>/dev/null; do
    case $(( _i % 4 )) in 0) _s="◐" ;; 1) _s="◓" ;; 2) _s="◑" ;; *) _s="◒" ;; esac
    ws_ir "$2"
    printf '\033[4G%s%s%s%s' "$WS_AC" "$WS_B" "$_s" "$WS_R"
    ws_ir 12
    _i=$(( _i + 1 ))
    sleep 0.15 2>/dev/null || sleep 1
  done
}
ws_esperar_apple() {
  # Mac sin sus herramientas para desarrolladores (git y Python de Apple): abro su instalador
  # —la persona pulsa «Instalar» en la ventana de Apple— y espero aquí hasta que termine.
  ws_paso 1 error "$WS_PASO1" "falta una pieza de Apple"
  xcode-select --install >/dev/null 2>&1 || true
  ws_tarjeta "Falta una pieza de Apple" \
    "No hiciste nada mal: macOS no trae git hasta que instalas sus" \
    "herramientas para desarrolladores." \
    "" \
    "${WS_AC}${WS_B}▸${WS_R} ${WS_B}Abrí la ventana de Apple. Pulsa «Instalar» y acepta.${WS_R}" \
    "  Aquí sigo solo cuando termine." \
    "" \
    "${WS_TN}Todavía no se instaló ni se cambió nada · Ctrl+C para salir.${WS_R}"
  _f=$(( WS_FILA - 4 ))
  _i=0
  until xcode-select -p >/dev/null 2>&1; do
    case $(( _i % 4 )) in 0) _s="◐" ;; 1) _s="◓" ;; 2) _s="◑" ;; *) _s="◒" ;; esac
    _vuelta=$WS_FILA
    ws_ir "$_f"
    printf '\033[64G%s%s%s esperando%s' "$WS_AC" "$WS_B" "$_s" "$WS_R"
    ws_ir "$_vuelta"
    _i=$(( _i + 1 ))
    sleep 1
  done
  ws_sin_tarjeta
  ws_paso 1 ahora "$WS_PASO1" "listo lo de Apple; reviso otra vez"
}
ws_corto() {
  # Una ruta con ~ en lugar de tu carpeta de usuario.
  case "$1" in "$HOME"/*) printf '~/%s' "${1#"$HOME"/}" ;; *) printf '%s' "$1" ;; esac
}
if [ "$WS_VIVO" = 1 ]; then
  # El bloque entero, de una vez (filas 0..11); el cursor queda en su casa (fila 12).
  printf '\n%s\n%s\n%s\n\n\n%s\n%s\n%s\n%s\n\n%s\n' "$(ws_marca_txt 1)" "$(ws_marca_txt 2)" "$(ws_marca_txt 3)" \
    "$(ws_paso_txt ahora "$WS_PASO1" "git · Python · espacio")" "$(ws_paso_txt falta "Descargo Workspace")" \
    "$(ws_paso_txt falta "Preparo el comando")" "$(ws_paso_txt falta "Abro Workspace")" "$(ws_barra_txt 0)"
  WS_FILA=12
fi
# <<< workspace-vista
# >>> workspace-preflight (bloque idéntico en setup.sh y dist/setup.sh —
# tests/test_setup_preflight.py lo verifica). Revisa TODO antes de escribir un
# solo archivo y lo explica sin culpar: junta los problemas y los dice juntos,
# cada uno con qué pasa y cómo se arregla. Define DEST (WORKSPACE_DIR, la
# instalación que ya existe o DEST_NUEVO) y PY (un Python >= 3.9), y puede
# mover DEST fuera de una carpeta sincronizada con la nube si DEST es el default.
# Con la vista viva (bloque workspace-vista) los problemas van en una tarjeta y
# una Mac sin sus herramientas de Apple se arregla sola: abro su instalador y
# espero. Escape (entornos raros): WORKSPACE_SKIP_PREFLIGHT=1.
ws_pf_bad() {
  WS_PF_FAIL=1
  if [ "${WS_VIVO:-0}" = 1 ]; then
    WS_PF_MSGS="${WS_PF_MSGS:-}$1"$'\n'
    shift
    for _l in "$@"; do WS_PF_MSGS="${WS_PF_MSGS}${_l}"$'\n'; done
    return 0
  fi
  printf '✖ %s\n' "$1"; shift
  for _l in "$@"; do printf '    %s\n' "$_l"; done
}
ws_pf_aviso() {
  # Un aviso que no frena la instalación: en vivo se dice al final; si no, aquí mismo.
  if [ "${WS_VIVO:-0}" = 1 ]; then WS_PF_AVISOS="${WS_PF_AVISOS:-}$1"$'\n'; else printf '%s\n' "$1"; fi
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
  # macOS con «Escritorio y Documentos» en iCloud: ~/Desktop y ~/Documents se
  # sincronizan. Solo se mira iCloud Drive si la ruta CAE en una de esas dos: el
  # default nuevo (~/Workspace) no entra a iCloud ni pide su permiso.
  for _kf in Desktop Documents; do
    case "$1" in
      "$HOME/$_kf"|"$HOME/$_kf/"*)
        if [ -d "$HOME/Library/Mobile Documents/com~apple~CloudDocs/$_kf" ]; then
          echo "iCloud (tu carpeta $_kf se sincroniza)"; return
        fi ;;
    esac
  done
}
ws_pf_dest() {
  # Destino por defecto (sin WORKSPACE_DIR): la instalación que YA tienes, si el
  # comando `workspace` de ~/.local/bin apunta a un checkout de este mismo repo
  # (se lee ese archivo y su .git/config: no se busca en el Escritorio ni se
  # supone dónde está); si no hay ninguna, $1 (la carpeta nueva, fuera de
  # Escritorio, Documentos y Descargas: macOS no pide permiso de carpetas).
  _lch="$HOME/.local/bin/workspace"
  if [ -f "$_lch" ]; then
    _r="$(sed -n 's|^exec "\$PY" "\(.*\)/front\.py".*|\1|p' "$_lch" 2>/dev/null | head -n 1)"
    if [ -n "$_r" ] && [ -f "$_r/.git/config" ] && grep -qF "$REPO" "$_r/.git/config" 2>/dev/null; then
      echo "$_r"; return
    fi
  fi
  echo "$1"
}
if [ -n "${WORKSPACE_DIR:-}" ]; then DEST="$WORKSPACE_DIR"; else DEST="$(ws_pf_dest "$DEST_NUEVO")"; fi
WS_DEST0="$DEST"
ws_pf_revisar() {
  WS_PF_FAIL=0
  WS_PF_CLT=0
  WS_PF_OTRO=0
  WS_PF_MSGS=""
  WS_PF_AVISOS=""
  WS_PF_DET="git"
  DEST="$WS_DEST0"
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
      WS_PF_CLT=1
      ws_pf_bad "Falta git. No hiciste nada mal: macOS no lo trae hasta instalar sus herramientas de línea de comandos." \
        "Arreglo: corre  xcode-select --install  , acepta, y vuelve a correr este instalador."
    else
      WS_PF_OTRO=1
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
    if [ "$_maj" -gt 3 ] || { [ "$_maj" -eq 3 ] && [ "$_min" -ge 9 ]; }; then PY="$_p"; WS_PF_DET="git · Python $_v"; break; fi
  done
  if [ -z "$PY" ]; then
    if [ -n "$_vistos" ]; then
      WS_PF_OTRO=1
      ws_pf_bad "Tu Python es $_vistos; Workspace necesita Python 3.9 o más nuevo. No hiciste nada mal: es el que trae tu sistema." \
        "Arreglo: instala uno nuevo (https://www.python.org/downloads/ · Mac: brew install python · Linux: el gestor de tu distro); no hace falta quitar el viejo."
    elif [ "$_noclt" = 1 ]; then
      WS_PF_CLT=1
      ws_pf_bad "Falta Python 3. No hiciste nada mal: macOS no lo trae hasta instalar sus herramientas de línea de comandos." \
        "Arreglo: corre  xcode-select --install  (o instala Python 3.9+ de https://www.python.org/downloads/) y reintenta."
    else
      WS_PF_OTRO=1
      ws_pf_bad "No encontré Python 3. Workspace necesita Python 3.9 o más nuevo. No hiciste nada mal: muchas máquinas no lo traen." \
        "Arreglo: instálalo (https://www.python.org/downloads/ · Mac: brew install python · Linux: sudo apt install python3) y reintenta."
    fi
  fi
  # Ubicación: una carpeta sincronizada con la nube bloquea/duplica los archivos
  # del harness. Una instalación que YA existe no se mueve (solo se avisa).
  _nube="$(ws_pf_cloud "$DEST")"
  if [ -n "$_nube" ] && [ -d "$DEST/.git" ]; then
    ws_pf_aviso "$(printf '! %s está en %s; funciona, pero si ves archivos bloqueados o duplicados, muévelo a una carpeta local.' "$DEST" "$_nube")"
  elif [ -n "$_nube" ] && [ -z "${WORKSPACE_DIR:-}" ]; then
    _alt="$HOME/$(basename "$DEST")"
    if [ "${WS_VIVO:-0}" != 1 ]; then
      printf '· %s se sincroniza con %s (no hiciste nada mal: es un ajuste del sistema).\n' "$DEST" "$_nube"
      printf '  Instalo en una carpeta local en su lugar → %s\n' "$_alt"
    fi
    DEST="$_alt"
  elif [ -n "$_nube" ]; then
    WS_PF_OTRO=1
    ws_pf_bad "La carpeta elegida ($DEST) está en $_nube: la sincronización bloquea y duplica los archivos de Workspace." \
      "Arreglo: elige una carpeta local, p. ej.:  WORKSPACE_DIR=\"\$HOME/Workspace\"  y reintenta."
  fi
  # Destino ocupado por una carpeta TUYA (no es Workspace ni una copia vieja suya,
  # ni solo tus Cerebros/Respaldos): no se mueve ni se mezcla. ~/Workspace es un
  # nombre común: sin esto, un ~/Workspace con tus proyectos se iba a un respaldo.
  if [ -d "$DEST" ] && [ ! -d "$DEST/.git" ] && [ ! -f "$DEST/front.py" ]; then
    _ajena=0
    for _e in "$DEST"/* "$DEST"/.[!.]*; do
      [ -e "$_e" ] || continue
      case "$(basename "$_e")" in Cerebros|Respaldos|.DS_Store) ;; *) _ajena=1; break ;; esac
    done
    if [ "$_ajena" = 1 ]; then
      WS_PF_OTRO=1
      ws_pf_bad "Ya tienes una carpeta $DEST con tus archivos y no es Workspace: no la toco." \
        "Arreglo: instala en otra carpeta, p. ej.:  WORKSPACE_DIR=\"\$HOME/Workspace-app\"  y vuelve a correr el comando."
    fi
  fi
  # Espacio: el código pesa poco, pero motores, logs y cerebros crecen. 200 MB mínimo.
  if [ ! -d "$DEST/.git" ]; then
    _anc="$DEST"
    while [ ! -d "$_anc" ] && [ "$_anc" != "/" ] && [ "$_anc" != "." ]; do _anc="$(dirname "$_anc")"; done
    _kb="$(df -Pk "$_anc" 2>/dev/null | awk 'NR==2 {print $4}' || true)"
    case "$_kb" in
      ''|*[!0-9]*) ;;
      *) if [ "$_kb" -lt 204800 ]; then
           WS_PF_OTRO=1
           ws_pf_bad "Queda poco espacio libre en el disco de $DEST ($((_kb / 1024)) MB). Workspace necesita al menos 200 MB." \
             "Arreglo: libera espacio (o elige otra carpeta con WORKSPACE_DIR) y reintenta."
         elif [ "$_kb" -ge 1048576 ]; then WS_PF_DET="$WS_PF_DET · $((_kb / 1048576)) GB libres"
         else WS_PF_DET="$WS_PF_DET · $((_kb / 1024)) MB libres"
         fi ;;
    esac
  fi
  if [ "$WS_PF_FAIL" = 1 ]; then
    if [ "${WS_VIVO:-0}" != 1 ]; then
      echo ""
      echo "No se instaló ni se cambió nada. Arregla lo de arriba y vuelve a correr el mismo comando."
    fi
    return 1
  fi
  return 0
}
ws_pf_tarjeta() {
  # En vivo: los problemas, juntos, en una tarjeta (cada uno con su arreglo).
  ws_paso 1 error "$WS_PASO1" "falta algo"
  set --
  while IFS= read -r _l; do
    [ -n "$_l" ] || continue
    case "$_l" in
      Arreglo:*) _pre="${WS_AC}${WS_B}▸${WS_R} "; _l="${_l#Arreglo: }" ;;
      *) _pre="" ;;
    esac
    _primera=1
    while IFS= read -r _w; do
      if [ "$_primera" = 1 ]; then set -- "$@" "${_pre}${_w}"; _primera=0
      elif [ -n "$_pre" ]; then set -- "$@" "  ${_w}"
      else set -- "$@" "${_w}"; fi
    done <<EOF_WS_FOLD
$(printf '%s\n' "$_l" | fold -s -w 66)
EOF_WS_FOLD
    if [ -n "$_pre" ]; then set -- "$@" ""; fi
  done <<EOF_WS_PF
$WS_PF_MSGS
EOF_WS_PF
  ws_tarjeta "Falta algo para instalar" "$@" \
    "${WS_TN}No se instaló ni se cambió nada. Arregla lo de arriba y vuelve a" \
    "correr el mismo comando.${WS_R}"
  printf '\n'
}
ws_preflight() {
  while :; do
    if ws_pf_revisar; then
      ws_paso 1 hecho "$WS_PASO1" "$WS_PF_DET"
      return 0
    fi
    if [ "${WS_VIVO:-0}" = 1 ] && [ "$WS_PF_CLT" = 1 ] && [ "$WS_PF_OTRO" = 0 ]; then
      ws_esperar_apple
      continue
    fi
    if [ "${WS_VIVO:-0}" = 1 ]; then ws_pf_tarjeta; fi
    return 1
  done
}
if [ "${WORKSPACE_SKIP_PREFLIGHT:-}" = "1" ]; then
  PY="$(command -v python3 || command -v python || true)"
else
  ws_preflight || exit 1
fi
if [ "${WORKSPACE_SETUP_PREFLIGHT_ONLY:-}" = "1" ]; then echo "ok  $DEST ($PY)"; exit 0; fi
# <<< workspace-preflight

# >>> workspace-bajar (bloque idéntico en setup.sh y dist/setup.sh — tests/test_instalar_vista.py
# lo verifica). La descarga con la vista viva: va DESPUÉS del preflight (nada se escribe antes).
ws_sin_token() {
  # La salida de git sin el token de WORKSPACE_TOKEN ni la URL con él (git cita la URL al fallar):
  # nunca en pantalla ni en un archivo.
  _tk="${WORKSPACE_TOKEN:-}"
  while IFS= read -r _l || [ -n "$_l" ]; do
    if [ -n "$_tk" ]; then _l="${_l//"$_tk"/***}"; fi
    printf '%s\n' "$_l"
  done | sed -E 's#(https?://)[^/@[:space:]]+@#\1***@#g'
}
ws_bajar() {
  # ws_bajar URL DESTINO [opción de git clone…]: descarga Workspace. En vivo: el paso 2 con sus
  # vueltas, la salida de git a un archivo temporal y, si no hay internet, reintento solo (3
  # veces, 10 s entre una y otra); otro error, en su tarjeta. Sin vivo: `git clone` de siempre.
  # Con WORKSPACE_TOKEN, lo que dice git pasa por ws_sin_token antes de verse o quedarse.
  _url="$1"
  _dst="$2"
  shift 2
  if [ "$WS_VIVO" != 1 ]; then
    if [ -z "${WORKSPACE_TOKEN:-}" ]; then git clone "$@" "$_url" "$_dst"; return; fi
    _rc=0
    git clone "$@" "$_url" "$_dst" 2>&1 | ws_sin_token || _rc=$?
    return "$_rc"
  fi
  _log="$(mktemp "${TMPDIR:-/tmp}/workspace-descarga.XXXXXX" 2>/dev/null || echo "${TMPDIR:-/tmp}/workspace-descarga.$$")"
  _vez=1
  _espera="${WORKSPACE_REINTENTO_S:-10}"
  case "$_espera" in ''|*[!0-9]*) _espera=10 ;; esac
  while :; do
    git clone "$@" "$_url" "$_dst" >"$_log" 2>&1 &
    _pid=$!
    ws_girar "$_pid" 7
    if wait "$_pid"; then rm -f "$_log"; return 0; fi
    if [ -n "${WORKSPACE_TOKEN:-}" ]; then ws_sin_token <"$_log" >"$_log.x" 2>/dev/null && mv -f "$_log.x" "$_log"; fi
    _red=0
    if grep -qiE "resolve host|connect to|timed out|unreachable|connection (refused|reset)|unable to access|network" "$_log" 2>/dev/null; then _red=1; fi
    if [ "$_red" = 1 ] && [ "$_vez" -lt 3 ]; then
      ws_paso 2 error "Descargo Workspace" "sin conexión"
      ws_tarjeta "No pude descargar" \
        "Parece que no hay internet, o GitHub no respondió a tiempo." \
        "" \
        "${WS_AC}${WS_B}▸${WS_R} ${WS_B}Lo intento otra vez solo en ${_espera} s.${WS_R}" \
        "  Si sigue, pega el mismo comando cuando vuelva la conexión." \
        "" \
        "${WS_TN}No se cambió nada en tu computadora.${WS_R}"
      _f=$(( WS_FILA - 5 ))
      _s=$_espera
      while [ "$_s" -gt 0 ]; do
        _vuelta=$WS_FILA
        ws_ir "$_f"
        printf '\033[K  %s│%s  %s%s▸%s %sLo intento otra vez solo en %d s.%s\033[78G%s│%s' "$WS_AV" "$WS_R" \
          "$WS_AC" "$WS_B" "$WS_R" "$WS_B" "$_s" "$WS_R" "$WS_AV" "$WS_R"
        ws_ir "$_vuelta"
        sleep 1
        _s=$(( _s - 1 ))
      done
      ws_sin_tarjeta
      ws_paso 2 ahora "Descargo Workspace" "otra vez ($(( _vez + 1 )) de 3)"
      _vez=$(( _vez + 1 ))
      continue
    fi
    _ult="$(grep -v '^[[:space:]]*$' "$_log" 2>/dev/null | tail -n 1 | ws_sin_token | cut -c1-66 || true)"
    ws_paso 2 error "Descargo Workspace" "$( [ "$_red" = 1 ] && echo "sin conexión" || echo "no se pudo" )"
    if [ "$_red" = 1 ]; then
      ws_tarjeta "No pude descargar" \
        "No hay internet, o GitHub no respondió (lo intenté 3 veces)." \
        "" \
        "${WS_AC}${WS_B}▸${WS_R} ${WS_B}Pega el mismo comando cuando vuelva la conexión.${WS_R}" \
        "" \
        "${WS_TN}No se cambió nada en tu computadora.${WS_R}"
    else
      ws_tarjeta "No pude descargar" \
        "No hiciste nada mal. git dijo:" \
        "  ${WS_TN}${_ult}${WS_R}" \
        "" \
        "${WS_AC}${WS_B}▸${WS_R} ${WS_B}Vuelve a pegar el mismo comando en un rato.${WS_R}" \
        "" \
        "${WS_TN}No se cambió nada en tu computadora.${WS_R}"
    fi
    printf '\n'
    rm -f "$_log"
    return 1
  done
}
ws_traer() {
  # ws_traer DESTINO: trae lo nuevo de una instalación que ya existe. En vivo, en silencio y sin
  # tumbar la instalación si no hay internet (sigue con lo que ya tienes). → 0 si actualizó.
  if [ "$WS_VIVO" != 1 ]; then git -C "$1" pull --ff-only; return; fi
  git -C "$1" pull --ff-only >/dev/null 2>&1 &
  _pid=$!
  ws_girar "$_pid" 7
  wait "$_pid"
}
# <<< workspace-bajar

if [ -n "${WORKSPACE_TOKEN:-}" ]; then URL="https://${WORKSPACE_TOKEN}@${REPO}"; else URL="https://${REPO}"; fi

if [ "$WS_VIVO" != 1 ]; then echo "Workspace → $DEST"; fi
if [ -d "$DEST/.git" ]; then
  if [ "$WS_VIVO" = 1 ]; then
    ws_paso 2 ahora "Descargo Workspace" "ya lo tenías: traigo lo nuevo"
    if ws_traer "$DEST"; then WS_P2="al día · $(ws_corto "$DEST")"; else WS_P2="sin conexión: sigo con lo que tienes"; fi
  else
    echo "· Ya está instalado; actualizando…"
    git -C "$DEST" pull --ff-only
  fi
elif [ -d "$DEST" ]; then
  BK="${DEST}_backup_$(date +%Y%m%d%H%M%S)"
  if [ "$WS_VIVO" != 1 ]; then echo "· Respaldando copia previa → $BK"; fi
  mv "$DEST" "$BK"
  ws_paso 2 ahora "Descargo Workspace" "en $(ws_corto "$DEST")"
  if ! ws_bajar "$URL" "$DEST"; then
    rm -rf "$DEST" 2>/dev/null || true
    mv "$BK" "$DEST"
    if [ "$WS_VIVO" != 1 ]; then echo "✖ No pude descargar Workspace. Tu carpeta quedó como estaba: $DEST"; fi
    exit 1
  fi
  # Tus carpetas (Cerebros/, Respaldos/) vuelven a su lugar: sus rutas no cambian
  # y el respaldo queda solo con lo viejo del harness.
  for _u in Cerebros Respaldos; do
    if [ -d "$BK/$_u" ] && [ ! -e "$DEST/$_u" ]; then
      if mv "$BK/$_u" "$DEST/$_u" && [ "$WS_VIVO" != 1 ]; then echo "· $_u/ sigue en $DEST/$_u"; fi
    fi
  done
  rm -f "$BK/.DS_Store" 2>/dev/null || true
  rmdir "$BK" 2>/dev/null || true
  WS_P2="$(ws_corto "$DEST")"
else
  ws_paso 2 ahora "Descargo Workspace" "en $(ws_corto "$DEST")"
  ws_bajar "$URL" "$DEST" || exit 1
  WS_P2="$(ws_corto "$DEST")"
fi

# Higiene de token: nunca dejarlo persistido en el remote (idempotente).
# Si se clonó con WORKSPACE_TOKEN, .git/config quedaría con el token en texto plano
# para SIEMPRE — lo limpiamos a la URL sin token. El auto-update usa las credenciales
# de la máquina (gh auth / credential manager). Espejo de setup.ps1.
if git -C "$DEST" remote get-url origin 2>/dev/null | grep -q "@"; then
  git -C "$DEST" remote set-url origin "https://${REPO}"
fi
ws_paso 2 hecho "Descargo Workspace" "${WS_P2:-}"
ws_barra 2

# I-a (F0 del onboarding): con una terminal de verdad, Workspace abre AQUÍ MISMO
# al terminar (ABRIR y TERMINAL salen del bloque workspace-vista). Con la vista
# viva, install.py sigue sobre el mismo bloque (paso 3, el monito y el final) y lo
# que hace por dentro va a su bitácora. Sin terminal se queda como antes: dice qué
# escribir. La línea del PATH en ~/.zshrc sigue ahí para las terminales nuevas.
if [ "$WS_VIVO" != 1 ]; then echo "· Instalando…"; fi
if [ "$ABRIR" = 1 ] && [ "$WS_VIVO" = 1 ]; then
  WORKSPACE_INSTALL_ABRE=1 WORKSPACE_INSTALL_VISTA=vivo WORKSPACE_INSTALL_T0="$WS_T0" "$PY" "$DEST/install.py" "$@"
elif [ "$ABRIR" = 1 ]; then
  WORKSPACE_INSTALL_ABRE=1 "$PY" "$DEST/install.py" "$@"   # pasa --socio TU-NOMBRE (y lo que agregues)
else
  "$PY" "$DEST/install.py" "$@"
fi
if [ "$WS_VIVO" = 1 ] && [ -n "${WS_PF_AVISOS:-}" ]; then
  while IFS= read -r _l; do
    if [ -n "$_l" ]; then printf '   %s%s!%s %s\n' "$WS_AV" "$WS_B" "$WS_R" "${_l#! }"; fi
  done <<EOF_WS_AVISOS
$WS_PF_AVISOS
EOF_WS_AVISOS
fi

LANZADOR="$HOME/.local/bin/workspace"
if [ "$ABRIR" = 1 ] && [ -x "$LANZADOR" ]; then
  if [ "$WS_VIVO" != 1 ]; then
    echo ""
    echo "▸ Abriendo Workspace aquí mismo…"
  fi
  exec "$LANZADOR" <"$TERMINAL"
fi

echo ""
echo "✓ Listo. Abre una terminal NUEVA y escribe:  workspace"
echo "  Ahí creas tu primer agente."
echo "  Para actualizar después:  workspace update   (o solo al abrir)."
