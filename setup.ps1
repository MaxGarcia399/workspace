# Workspace · bootstrap (Windows / PowerShell) — instala el harness en UNA máquina.
#
# Uso (una línea, en PowerShell; Workspace abre en esta misma ventana al terminar):
#   irm https://workspacecli.ai/install.ps1 | iex
# o directo del repo, igual:
#   irm https://raw.githubusercontent.com/MaxGarcia399/workspace/main/setup.ps1 | iex
#
# O manual:  git clone https://github.com/MaxGarcia399/workspace.git "$env:LOCALAPPDATA\Workspace"
#            python "$env:LOCALAPPDATA\Workspace\install.py"
#
# A prueba de `irm | iex` (O3-a): con iex este texto corre DENTRO de tu PowerShell, así que todo
# va en `& { … }` (sus variables y funciones no se quedan en tu sesión) y sin `exit`, que cerraba
# la ventana; un error termina el bloque y te deja en tu PowerShell. Como archivo
# (powershell -File setup.ps1) el código de salida se conserva (el `exit` de la última línea).
# Al terminar, recarga el PATH de esta ventana y abre workspace.cmd aquí mismo.
#
# Destino por default: %LOCALAPPDATA%\Workspace (por usuario, sin permisos de admin,
# fuera de Desktop/Documents/OneDrive). Overrides: WORKSPACE_DIR (destino) ·
# WORKSPACE_REPO (org/repo) · WORKSPACE_TOKEN (fork privado) · WORKSPACE_NO_ABRIR=1 (no abrir)
# · WORKSPACE_INSTALL_DETALLE=1 (todo lo que hace, en pantalla).
# Cualquier destino pasa por la MISMA regla que install.py (pathguard) ANTES de clonar.
# Solo validar el destino (sin git ni red): $env:WORKSPACE_SETUP_CHECK_ONLY="1".
# El instalador deja el comando `workspace` como shim .cmd en ~\.local\bin (funciona en
# cmd.exe, PowerShell y la terminal de VS Code) más las funciones del $PROFILE.
# (Solo ASCII fuera de comentarios: Windows PowerShell 5.1 lee .ps1 sin BOM como ANSI.)
& {
$ErrorActionPreference = "Stop"
$script:WorkspaceSetupRc = 0
# Un error que truena el bloque (con "Stop") no llega a la ultima linea: bajo `irm | iex` sus variables se
# quedaban en tu sesion. El trap quita lo mismo que esa linea y deja que el error siga (break).
trap { Remove-Variable -Name WorkspaceSetupRc, pyExe, pyArgs, WsPfOfrecer, WsPfDetalle, WsPfFaltaGit, WsPfFaltaPython -Scope Script -ErrorAction SilentlyContinue; break }

# >>> workspace-path-guard (espejo de pathguard.redirected_root; bloque idéntico en
# setup.ps1 y dist/setup.ps1 — tests/test_bootstrap_contract.py lo verifica)
function Test-WsUnder([string]$Child, [string]$Parent) {
  if (-not $Child -or -not $Parent) { return $false }
  $c = [IO.Path]::GetFullPath($Child).TrimEnd('\').ToLowerInvariant()
  $p = [IO.Path]::GetFullPath($Parent).TrimEnd('\').ToLowerInvariant()
  return ($c -eq $p) -or $c.StartsWith($p + '\')
}
function Get-WsRedirect([string]$Path) {
  # (a) %OneDrive% / %OneDriveConsumer% / %OneDriveCommercial%
  foreach ($v in @('OneDrive', 'OneDriveConsumer', 'OneDriveCommercial')) {
    $r = [Environment]::GetEnvironmentVariable($v)
    if ($r -and (Test-WsUnder $Path $r)) { return "%$v%" }
  }
  # (b) %USERPROFILE%\OneDrive*
  $up = $env:USERPROFILE
  if ($up -and (Test-WsUnder $Path $up)) {
    $full = [IO.Path]::GetFullPath($Path).TrimEnd('\')
    $base = [IO.Path]::GetFullPath($up).TrimEnd('\')
    if ($full.Length -gt $base.Length) {
      $first = ($full.Substring($base.Length).TrimStart('\') -split '\\')[0]
      if ($first -like 'onedrive*') { return "%USERPROFILE%\$first" }
    }
  }
  # (c) known-folders (Desktop / Documents) redirigidos a OneDrive
  foreach ($kf in @('Desktop', 'MyDocuments')) {
    $t = [Environment]::GetFolderPath($kf)
    if ($t -and ($t.ToLowerInvariant() -match '\\onedrive') -and (Test-WsUnder $Path $t)) { return "%OneDrive%\$kf" }
  }
  # (d) fallback: componente \onedrive\ en la ruta
  $n = [IO.Path]::GetFullPath($Path).TrimEnd('\').ToLowerInvariant()
  if ($n -match '\\onedrive(\\|$)') { return 'OneDrive' }
  return ''
}
function Assert-WsLocation([string]$Path) {
  # $true si la ruta sirve. Sin `exit` (con `irm | iex` cerraba la ventana): quien llama
  # deja el codigo 3 y termina.
  $lbl = Get-WsRedirect $Path
  if ($lbl) {
    Write-Host "X  $Path vive en una ruta redirigida a la nube ($lbl)."
    Write-Host "   OneDrive sincroniza y BLOQUEA los archivos de Workspace (locks, latencia)."
    Write-Host "   Usa una ruta local, p.ej.:  `$env:WORKSPACE_DIR=`"$env:LOCALAPPDATA\Workspace`""
    return $false
  }
  return $true
}
# <<< workspace-path-guard

# >>> workspace-vista (bloque idéntico en setup.ps1 y dist/setup.ps1 — tests/test_instalar_vista.py
# lo verifica). O2-a en Windows, modo «lineal»: con una consola de verdad, la marca y una línea
# por paso (la del paso en curso se reescribe en su lugar con `r, sin mover el cursor de fila);
# lo de dentro (git, install.py) va a una bitácora y los errores en una tarjeta. Sin consola
# (tests, CI, salida redirigida), con --detalle o WORKSPACE_INSTALL_DETALLE=1: el texto de
# siempre. Las letras fuera de ASCII van con [char] (PS 5.1 lee el archivo como ANSI).
$wsU = @{ ok = [char]0x2713; giro = [char]0x25D0; mal = [char]0x2716; pto = [char]0x00B7; marca = [char]0x276F
  ab = [char]0x00AB; cb = [char]0x00BB; e = [char]0x00E9; i = [char]0x00ED; o = [char]0x00F3; a = [char]0x00E1
  va = [char]0x25B8; tres = [char]0x2026; esq = [char]0x256D; bar = [char]0x2502; fin = [char]0x2570; lin = [char]0x2500 }
$wsDetalle = ($env:WORKSPACE_INSTALL_DETALLE -eq "1") -or (@($args) -contains '--detalle')
$wsConsola = $false
try {
  $wsConsola = [Environment]::UserInteractive -and -not [Console]::IsInputRedirected -and -not [Console]::IsOutputRedirected
} catch { $wsConsola = $false }
if ($env:WORKSPACE_NO_ABRIR) { $wsConsola = $false }
$wsCorto = $wsConsola -and -not $wsDetalle
$wsT0 = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
function Get-WsPasado([string]$Titulo) {
  if ($Titulo.StartsWith('Reviso ')) { return "Revis$($wsU.e) " + $Titulo.Substring(7) }
  if ($Titulo.StartsWith('Descargo ')) { return "Descargu$($wsU.e) " + $Titulo.Substring(9) }
  if ($Titulo.StartsWith('Preparo ')) { return "Prepar$($wsU.e) " + $Titulo.Substring(8) }
  return $Titulo
}
function Write-WsPaso([string]$Estado, [string]$Titulo, [string]$Detalle, [switch]$Abierto) {
  # Una línea de paso: el glifo en la columna 3, el título en la 6 y el detalle en la 27.
  # -Abierto: sin salto de línea (el paso en curso; la siguiente llamada la reescribe con `r).
  $g = $wsU.pto; $gc = 'DarkGray'; $t = $Titulo; $tc = 'DarkGray'; $dc = 'DarkGray'
  if ($Estado -eq 'hecho') { $g = $wsU.ok; $gc = 'Green'; $t = Get-WsPasado $Titulo; $tc = 'Gray' }
  elseif ($Estado -eq 'ahora') { $g = $wsU.giro; $gc = 'Magenta'; $tc = 'White' }
  elseif ($Estado -eq 'error') { $g = $wsU.mal; $gc = 'Yellow'; $tc = 'White'; $dc = 'Yellow' }
  Write-Host "`r   " -NoNewline
  Write-Host $g -ForegroundColor $gc -NoNewline
  Write-Host "  " -NoNewline
  Write-Host $t.PadRight(21) -ForegroundColor $tc -NoNewline
  if ($Abierto) { Write-Host $Detalle.PadRight(40) -ForegroundColor $dc -NoNewline }
  else { Write-Host $Detalle.PadRight(40) -ForegroundColor $dc }
}
function Write-WsCabeza {
  Write-Host ""
  Write-Host "  " -NoNewline
  Write-Host $wsU.marca -ForegroundColor Magenta -NoNewline
  Write-Host " workspace"
  Write-Host "  Lo instalo en tu PC. Toma un minuto."
  Write-Host "  Sin cuentas nuevas $($wsU.pto) se quita con $($wsU.ab)workspace uninstall$($wsU.cb)" -ForegroundColor DarkGray
  Write-Host ""
}
function Write-WsTarjeta([string]$Titulo, [string[]]$Lineas) {
  # Tarjeta ámbar con borde a la izquierda (sin contar letras: no hay borde derecho).
  Write-Host ""
  Write-Host "  $($wsU.esq)$($wsU.lin) " -ForegroundColor Yellow -NoNewline
  Write-Host $Titulo -ForegroundColor Yellow
  foreach ($l in $Lineas) {
    Write-Host "  $($wsU.bar)  " -ForegroundColor Yellow -NoNewline
    Write-Host $l
  }
  Write-Host "  $($wsU.fin)$($wsU.lin)" -ForegroundColor Yellow
}
function Update-WsPath {
  # Lo nuevo del PATH guardado (Machine y User: lo que dejó un instalador) entra a ESTA ventana,
  # sin perder lo que ya tenía; y ~\.local\bin (el comando workspace) también, solo aquí.
  $have = @{}
  foreach ($d in ($env:Path -split ';')) { if ($d) { $have[$d.TrimEnd('\').ToLowerInvariant()] = $true } }
  $nuevas = @()
  foreach ($sc in @('Machine', 'User')) {
    $p = [Environment]::GetEnvironmentVariable('Path', $sc)
    if (-not $p) { continue }
    foreach ($d in ($p -split ';')) {
      if (-not $d) { continue }
      $d = [Environment]::ExpandEnvironmentVariables($d)
      $k = $d.TrimEnd('\').ToLowerInvariant()
      if (-not $have.ContainsKey($k)) { $have[$k] = $true; $nuevas += $d }
    }
  }
  $bin = Join-Path $HOME ".local\bin"
  if (-not $have.ContainsKey($bin.TrimEnd('\').ToLowerInvariant())) { $nuevas += $bin }
  if ($nuevas.Count -gt 0) { $env:Path = (@($env:Path.TrimEnd(';')) + $nuevas) -join ';' }
}
function Invoke-WsCallado([string]$Log, [scriptblock]$Cmd) {
  # Corre un programa con su salida a $Log. Con "Stop", PS 5.1 vuelve error cada línea de stderr
  # redirigida (git escribe ahí su progreso): aquí manda el código de salida, no stderr.
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try { & $Cmd *> $Log; return [int]$LASTEXITCODE }
  catch { return 1 }
  finally { $ErrorActionPreference = $old }
}
function Hide-WsToken([string]$Texto) {
  # Sin el token de WORKSPACE_TOKEN ni la URL con el (git cita la URL al fallar): nunca en pantalla ni en una bitacora.
  $t = "$Texto"
  if ($env:WORKSPACE_TOKEN) { $t = $t.Replace($env:WORKSPACE_TOKEN, '***') }
  return ($t -replace '(https?://)[^/@\s]+@', '$1***@')
}
function Protect-WsLog([string]$Log) {
  # La bitacora de git, reescrita sin el token antes de leerla, ensenarla o dejarla en %TEMP%.
  if (-not $env:WORKSPACE_TOKEN -or -not (Test-Path $Log)) { return }
  $c = Get-Content $Log -Raw -ErrorAction SilentlyContinue
  if ($null -ne $c) { Set-Content -Path $Log -Value (Hide-WsToken $c) -NoNewline -ErrorAction SilentlyContinue }
}
function Invoke-WsGitSinToken([scriptblock]$Cmd) {
  # git con WORKSPACE_TOKEN en el texto de siempre: lo que diga se ensena sin el token y no queda bitacora.
  $log = Join-Path $env:TEMP ("workspace-git-" + [guid]::NewGuid().ToString('N') + ".log")
  $rc = Invoke-WsCallado $log $Cmd
  if (Test-Path $log) {
    Get-Content $log -ErrorAction SilentlyContinue | ForEach-Object { Write-Host (Hide-WsToken "$_") }
    Remove-Item $log -Force -ErrorAction SilentlyContinue
  }
  return $rc
}
function Install-WsFaltan {
  # Windows sin Git y/o sin Python (la PC nueva tipica no trae ninguno): con el Enter de la
  # persona, lo que falte se instala con winget (el instalador de Microsoft, solo para este
  # usuario). Esc sale sin cambiar nada. Nunca sin preguntar.
  $git = [bool]$script:WsPfFaltaGit
  $py = [bool]$script:WsPfFaltaPython
  if ($git -and $py) {
    $titulo = 'Faltan Git y Python'; $paso = 'faltan Git y Python'; $lo = 'los'
    $l1 = "No hiciste nada mal: Windows no trae Git ni Python. Workspace"
    $l2 = "los necesita (Python en la versi$($wsU.o)n 3.9 o m$($wsU.a)s nueva)."
  } elseif ($git) {
    $titulo = 'Falta Git'; $paso = 'falta Git'; $lo = 'lo'
    $l1 = "No hiciste nada mal: Windows no trae Git. Workspace lo usa"
    $l2 = "para descargarse y actualizarse."
  } else {
    $titulo = 'Falta Python'; $paso = 'falta Python'; $lo = 'lo'
    $l1 = "No hiciste nada mal: Windows no trae Python. Workspace necesita"
    $l2 = "la versi$($wsU.o)n 3.9 o m$($wsU.a)s nueva."
  }
  Write-WsPaso 'error' 'Reviso tu PC' $paso
  Write-WsTarjeta $titulo @(
    $l1,
    $l2,
    "",
    "$($wsU.va) Enter: $lo instalo con winget (el instalador de Microsoft).",
    "  Esc: salgo sin cambiar nada.",
    "",
    "Despu$($wsU.e)s sigo yo, sin que pegues nada otra vez.")
  do { $k = [Console]::ReadKey($true) } until ($k.Key -eq 'Enter' -or $k.Key -eq 'Escape')
  if ($k.Key -ne 'Enter') {
    Write-Host ""
    Write-Host "No se instalo ni se cambio nada. Cuando tengas Git y Python 3.9+, vuelve a pegar el mismo comando."
    return $false
  }
  Write-Host ""
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  # `| Out-Host`: lo que dice winget se ve mientras instala y no se vuelve parte de lo que devuelve esta
  # funcion (sin eso, un `return $false` llegaba como una lista con texto: verdadera).
  $rc = 0; $fase = ''
  try {
    if ($git) {
      $fase = 'Git'
      winget install --id Git.Git -e --source winget --scope user | Out-Host; $rc = [int]$LASTEXITCODE
    }
    if ($rc -eq 0 -and $py) {
      $fase = 'Python'
      winget install --id Python.Python.3.12 -e --source winget --scope user | Out-Host; $rc = [int]$LASTEXITCODE
    }
  }
  catch { $rc = 1 }
  finally { $ErrorActionPreference = $old }
  if ($rc -ne 0 -and $fase -eq 'Git') {
    Write-WsTarjeta 'No pude instalar Git' @(
      "winget no termin$($wsU.o) (c$($wsU.o)digo $rc). No se cambi$($wsU.o) nada de Workspace.",
      "$($wsU.va) Inst$($wsU.a)lalo de https://git-scm.com/download/win",
      "  y vuelve a pegar el mismo comando.")
    return $false
  }
  if ($rc -ne 0) {
    Write-WsTarjeta 'No pude instalar Python' @(
      "winget no termin$($wsU.o) (c$($wsU.o)digo $rc). No se cambi$($wsU.o) nada de Workspace.",
      "$($wsU.va) Inst$($wsU.a)lalo de https://www.python.org/downloads/ (marca 'Add python.exe to PATH')",
      "  y vuelve a pegar el mismo comando.")
    return $false
  }
  Update-WsPath
  Write-Host ""
  return $true
}
# <<< workspace-vista

if ($env:WORKSPACE_DIR) { $dest = $env:WORKSPACE_DIR } else { $dest = Join-Path $env:LOCALAPPDATA "Workspace" }
if ($env:WORKSPACE_REPO) { $repo = $env:WORKSPACE_REPO } else { $repo = "github.com/MaxGarcia399/workspace.git" }

if ($dest -eq (Join-Path $env:LOCALAPPDATA "Workspace")) { $wsDonde = "en tu carpeta de usuario" } else { $wsDonde = $dest }

if (-not (Assert-WsLocation $dest)) { $script:WorkspaceSetupRc = 3; return }
if ($env:WORKSPACE_SETUP_CHECK_ONLY -eq "1") { Write-Host "ok  $dest"; return }
if ($wsCorto) { Write-WsCabeza; Write-WsPaso 'ahora' 'Reviso tu PC' "git $($wsU.pto) Python $($wsU.pto) espacio" -Abierto }

# >>> workspace-preflight (bloque idéntico en setup.ps1 y dist/setup.ps1 —
# tests/test_setup_preflight.py lo verifica). Revisa TODO antes de escribir un
# solo archivo y lo explica sin culpar: junta los problemas y los dice juntos,
# cada uno con qué pasa y cómo se arregla. Deja $pyExe/$pyArgs (Python >= 3.9).
# Ojo: el `python.exe` de %LOCALAPPDATA%\Microsoft\WindowsApps puede ser el ATAJO
# de la Microsoft Store (sin argumentos abre la tienda; con -c falla) — por eso se
# PRUEBA cada candidato con -c en vez de confiar en Get-Command.
# La ubicación (OneDrive) ya la validó Assert-WsLocation arriba. Con consola (bloque
# workspace-vista) y winget, si lo único que falta es Git y/o Python, no se dice aquí: se
# ofrece instalarlo con Enter (Install-WsFaltan) y se vuelve a revisar.
# Escape (entornos raros): $env:WORKSPACE_SKIP_PREFLIGHT="1".
function Get-WsPyVersion([string]$Exe, [string[]]$Pre) {
  $old = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    $out = & $Exe @Pre -c "import sys; print('%d.%d' % sys.version_info[:2])" 2>$null
    if ($LASTEXITCODE -eq 0 -and ("$out".Trim() -match '^(\d+)\.(\d+)$')) { return "$out".Trim() }
  } catch { }
  finally { $ErrorActionPreference = $old }
  return ''
}
function Invoke-WsPreflight([string]$Dest, [switch]$SinOfrecer) {
  $script:pyExe = $null
  $script:pyArgs = @()
  $script:WsPfOfrecer = $false
  $script:WsPfDetalle = "git"
  $fails = New-Object System.Collections.ArrayList
  $faltaPython = $false
  $faltaGit = $false
  $script:WsPfFaltaGit = $false
  $script:WsPfFaltaPython = $false
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    $faltaGit = $true
    [void]$fails.Add(@("Falta git (Workspace se descarga y se actualiza con git). No hiciste nada mal: Windows no lo trae.",
      "Arreglo: instala Git for Windows (https://git-scm.com/download/win o: winget install Git.Git), abre una terminal NUEVA y reintenta."))
  }
  $seen = @()
  $store = $false
  foreach ($name in @('python', 'python3', 'py')) {
    if ($script:pyExe) { break }
    if ($name -eq 'py') { $pre = @('-3') } else { $pre = @() }
    # -All: el atajo de la Store puede ir PRIMERO en el PATH y tapar al Python real.
    foreach ($cmd in @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)) {
      $v = Get-WsPyVersion $cmd.Source $pre
      if (-not $v) {
        if ($cmd.Source -like '*\WindowsApps\*') { $store = $true }
        continue
      }
      $seen += $v
      $parts = $v.Split('.')
      if ([int]$parts[0] -gt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -ge 9)) {
        $script:pyExe = $cmd.Source
        $script:pyArgs = $pre
        $script:WsPfDetalle = "git $($wsU.pto) Python $v"
        break
      }
    }
  }
  if (-not $script:pyExe) {
    $faltaPython = $true
    if ($seen.Count -gt 0) {
      [void]$fails.Add(@("Tu Python es $($seen -join ', '); Workspace necesita Python 3.9 o mas nuevo. No hiciste nada mal: es una version anterior.",
        "Arreglo: instala uno nuevo (https://www.python.org/downloads/ o: winget install Python.Python.3.12), abre una terminal NUEVA y reintenta."))
    } elseif ($store) {
      [void]$fails.Add(@("No encontre Python: el 'python' que hay es el atajo de la Microsoft Store, no un Python instalado. No hiciste nada mal: Windows lo trae asi.",
        "Arreglo: instala Python 3.9+ (https://www.python.org/downloads/ marcando 'Add python.exe to PATH', o: winget install Python.Python.3.12), abre una terminal NUEVA y reintenta."))
    } else {
      [void]$fails.Add(@("No encontre Python 3. Workspace necesita Python 3.9 o mas nuevo. No hiciste nada mal: Windows no lo trae.",
        "Arreglo: instalalo (https://www.python.org/downloads/ marcando 'Add python.exe to PATH', o: winget install Python.Python.3.12), abre una terminal NUEVA y reintenta."))
    }
  }
  # Espacio: el codigo pesa poco, pero motores, logs y cerebros crecen. 200 MB minimo.
  if (-not (Test-Path (Join-Path $Dest ".git"))) {
    try {
      $root = [IO.Path]::GetPathRoot([IO.Path]::GetFullPath($Dest))
      $free = (New-Object IO.DriveInfo $root).AvailableFreeSpace
      if ($free -lt 200MB) {
        [void]$fails.Add(@("Queda poco espacio libre en $root ($([math]::Floor($free / 1MB)) MB). Workspace necesita al menos 200 MB.",
          "Arreglo: libera espacio (o elige otra carpeta con `$env:WORKSPACE_DIR) y reintenta."))
      } else { $script:WsPfDetalle += " $($wsU.pto) $([math]::Floor($free / 1GB)) GB libres" }
    } catch { }
  }
  if (($faltaPython -or $faltaGit) -and $fails.Count -eq ([int]$faltaPython + [int]$faltaGit) -and $wsCorto -and
      -not $SinOfrecer -and (Get-Command winget -ErrorAction SilentlyContinue)) {
    $script:WsPfOfrecer = $true
    $script:WsPfFaltaGit = $faltaGit
    $script:WsPfFaltaPython = $faltaPython
    return $false
  }
  if ($wsCorto -and $fails.Count -gt 0) { Write-WsPaso 'error' 'Reviso tu PC' 'falta algo'; Write-Host "" }
  foreach ($f in $fails) {
    Write-Host "X  $($f[0])"
    Write-Host "   $($f[1])"
  }
  if ($fails.Count -gt 0) {
    Write-Host ""
    Write-Host "No se instalo ni se cambio nada. Arregla lo de arriba y vuelve a correr el mismo comando."
    return $false
  }
  return $true
}
if ($env:WORKSPACE_SKIP_PREFLIGHT -eq "1") {
  $c = Get-Command python -ErrorAction SilentlyContinue
  if (-not $c) { $c = Get-Command py -ErrorAction SilentlyContinue }
  if ($c) { $pyExe = $c.Source } else { $pyExe = "python" }
  $pyArgs = @()
  if ($wsCorto) { Write-WsPaso 'hecho' 'Reviso tu PC' 'sin revisar (WORKSPACE_SKIP_PREFLIGHT)' }
} else {
  $wsOk = Invoke-WsPreflight $dest
  # Solo falta Git y/o Python, hay consola y winget: se ofrece UNA vez (Enter instala, Esc sale).
  if (-not $wsOk -and $script:WsPfOfrecer -and (Install-WsFaltan)) { $wsOk = Invoke-WsPreflight $dest -SinOfrecer }
  if (-not $wsOk) { $script:WorkspaceSetupRc = 1; return }
  if ($wsCorto) { Write-WsPaso 'hecho' 'Reviso tu PC' $script:WsPfDetalle }
}
if ($env:WORKSPACE_SETUP_PREFLIGHT_ONLY -eq "1") { Write-Host "ok  $dest ($pyExe)"; return }
# <<< workspace-preflight

$cleanUrl = "https://$repo"
if ($env:WORKSPACE_TOKEN) { $url = "https://$($env:WORKSPACE_TOKEN)@$repo" } else { $url = $cleanUrl }

if ($wsCorto) {
  # Una linea por paso; git a una bitacora; sin internet, reintento solo (3 veces, 10 s).
  $wsLog = Join-Path $env:TEMP "workspace-descarga.log"
  if (Test-Path (Join-Path $dest ".git")) {
    Write-WsPaso 'ahora' 'Descargo Workspace' "ya lo ten$($wsU.i)as: traigo lo nuevo" -Abierto
    $rc = Invoke-WsCallado $wsLog { git -C "$dest" pull --ff-only }
    if ($rc -eq 0) { $wsP2 = "al d$($wsU.i)a" } else { $wsP2 = "sin conexi$($wsU.o)n: sigo con lo que tienes" }
  } else {
    if (Test-Path $dest) {
      $bk = "${dest}_backup_$(Get-Date -Format yyyyMMddHHmmss)"
      Move-Item $dest $bk
    }
    $vez = 1
    while ($true) {
      Write-WsPaso 'ahora' 'Descargo Workspace' $wsDonde -Abierto
      $rc = Invoke-WsCallado $wsLog { git clone  $url $dest }
      Protect-WsLog $wsLog
      if ($rc -eq 0) { break }
      $txt = ""
      if (Test-Path $wsLog) { $txt = (Get-Content $wsLog -Raw -ErrorAction SilentlyContinue) }
      $red = "$txt" -match 'resolve host|connect to|timed out|unreachable|unable to access|network'
      if ($red -and $vez -lt 3) {
        Write-WsPaso 'error' 'Descargo Workspace' "sin conexi$($wsU.o)n: otra vez en 10 s"
        Start-Sleep -Seconds 10
        $vez++
        continue
      }
      if (Test-Path $dest) { Remove-Item $dest -Recurse -Force -ErrorAction SilentlyContinue }
      if ($bk -and (Test-Path $bk)) { Move-Item $bk $dest }
      Write-WsPaso 'error' 'Descargo Workspace' "no se pudo"
      if ($red) { $porque = "No hay internet, o GitHub no respondi$($wsU.o) (lo intent$($wsU.e) 3 veces)." }
      else { $porque = "No hiciste nada mal. git dijo: " + (Hide-WsToken (("$txt" -split "`n" | Where-Object { $_.Trim() } | Select-Object -Last 1))) }
      Remove-Item $wsLog -ErrorAction SilentlyContinue
      Write-WsTarjeta 'No pude descargar' @($porque, "", "$($wsU.va) Pega el mismo comando cuando vuelva la conexi$($wsU.o)n.", "",
        "No se cambi$($wsU.o) nada en tu computadora.")
      $script:WorkspaceSetupRc = 1
      return
    }
    $wsP2 = $wsDonde
  }
  Remove-Item $wsLog -ErrorAction SilentlyContinue
} else {
  Write-Host "Workspace -> $dest"
  if (Test-Path (Join-Path $dest ".git")) {
    Write-Host "Ya esta instalado; actualizando..."
    try { git -C "$dest" pull --ff-only }
    catch { Write-Host "  no pude actualizar (sin conexion o cambios locales) - sigo con lo que ya tienes" }
  } elseif (Test-Path $dest) {
    $bk = "${dest}_backup_$(Get-Date -Format yyyyMMddHHmmss)"
    Write-Host "Respaldando copia previa (no se borra nada) -> $bk"
    Move-Item $dest $bk
    if ($env:WORKSPACE_TOKEN) { $null = Invoke-WsGitSinToken { git clone $url $dest } } else { git clone $url $dest }
  } else {
    if ($env:WORKSPACE_TOKEN) { $null = Invoke-WsGitSinToken { git clone $url $dest } } else { git clone $url $dest }
  }
}

# Higiene de token: nunca dejarlo persistido en el remote (idempotente).
if (Test-Path (Join-Path $dest ".git")) {
  $remote = git -C "$dest" remote get-url origin
  if ($remote -match "@") { git -C "$dest" remote set-url origin $cleanUrl }
}
if ($wsCorto) { Write-WsPaso 'hecho' 'Descargo Workspace' $wsP2 }

# install.py: con consola, en «lineal» (sus detalles a su bitacora, en pantalla el paso 3 y el
# final). Las variables se quitan despues: bajo `irm | iex` son de TU sesion de PowerShell.
if ($wsCorto) {
  $env:WORKSPACE_INSTALL_ABRE = "1"; $env:WORKSPACE_INSTALL_VISTA = "lineal"; $env:WORKSPACE_INSTALL_T0 = "$wsT0"
} else {
  Write-Host "Instalando (comando workspace + hooks)..."
  if ($wsConsola) { $env:WORKSPACE_INSTALL_ABRE = "1" }
}
try {
  & $pyExe @pyArgs (Join-Path $dest "install.py") @args
  $rc = [int]$LASTEXITCODE
} finally {
  Remove-Item Env:WORKSPACE_INSTALL_ABRE, Env:WORKSPACE_INSTALL_VISTA, Env:WORKSPACE_INSTALL_T0 -ErrorAction SilentlyContinue
}
if ($rc) { $script:WorkspaceSetupRc = $rc; return }

# O3-a: el comando `workspace` en ESTA ventana (sin abrir otra) y Workspace abre aqui mismo.
Update-WsPath
$wsShim = Join-Path $HOME ".local\bin\workspace.cmd"
if ($wsConsola -and (Test-Path $wsShim)) {
  if (-not $wsCorto) { Write-Host ""; Write-Host "> Abriendo Workspace aqui mismo..." }
  & $wsShim
  return
}

Write-Host ""
Write-Host "Listo. Abre una terminal NUEVA y escribe:  workspace"
Write-Host "  -> menu vacio -> 'Agregar agente' (crear o cargar tu cerebro)."
Write-Host "  Para actualizar despues:  workspace update"
} @args
if ($PSCommandPath -and $script:WorkspaceSetupRc) { exit $script:WorkspaceSetupRc }
Remove-Variable -Name WorkspaceSetupRc, pyExe, pyArgs, WsPfOfrecer, WsPfDetalle, WsPfFaltaGit, WsPfFaltaPython -Scope Script -ErrorAction SilentlyContinue
