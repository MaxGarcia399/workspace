# Workspace · bootstrap (Windows / PowerShell) — instala el harness en UNA máquina.
#
# Uso:
#   irm https://raw.githubusercontent.com/MaxGarcia399/workspace/main/setup.ps1 -OutFile $env:TEMP\workspace-setup.ps1
#   powershell -NoProfile -ExecutionPolicy Bypass -File $env:TEMP\workspace-setup.ps1
#
# O manual:  git clone https://github.com/MaxGarcia399/workspace.git "$env:LOCALAPPDATA\Workspace"
#            python "$env:LOCALAPPDATA\Workspace\install.py"
#
# Destino por default: %LOCALAPPDATA%\Workspace (por usuario, sin permisos de admin,
# fuera de Desktop/Documents/OneDrive). Overrides: WORKSPACE_DIR (destino) ·
# WORKSPACE_REPO (org/repo) · WORKSPACE_TOKEN (fork privado).
# Cualquier destino pasa por la MISMA regla que install.py (pathguard) ANTES de clonar.
# Solo validar el destino (sin git ni red): $env:WORKSPACE_SETUP_CHECK_ONLY="1".
# El instalador deja el comando `workspace` como shim .cmd en ~\.local\bin (funciona en
# cmd.exe, PowerShell y la terminal de VS Code) más las funciones del $PROFILE.
# (Solo ASCII fuera de comentarios: Windows PowerShell 5.1 lee .ps1 sin BOM como ANSI.)
$ErrorActionPreference = "Stop"

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
  $lbl = Get-WsRedirect $Path
  if ($lbl) {
    Write-Host "X  $Path vive en una ruta redirigida a la nube ($lbl)."
    Write-Host "   OneDrive sincroniza y BLOQUEA los archivos del harness (locks, latencia)."
    Write-Host "   Usa una ruta local, p.ej.:  `$env:WORKSPACE_DIR=`"$env:LOCALAPPDATA\Workspace`""
    exit 3
  }
}
# <<< workspace-path-guard

if ($env:WORKSPACE_DIR) { $dest = $env:WORKSPACE_DIR } else { $dest = Join-Path $env:LOCALAPPDATA "Workspace" }
if ($env:WORKSPACE_REPO) { $repo = $env:WORKSPACE_REPO } else { $repo = "github.com/MaxGarcia399/workspace.git" }

Assert-WsLocation $dest
if ($env:WORKSPACE_SETUP_CHECK_ONLY -eq "1") { Write-Host "ok  $dest"; exit 0 }

# >>> workspace-preflight (bloque idéntico en setup.ps1 y dist/setup.ps1 —
# tests/test_setup_preflight.py lo verifica). Revisa TODO antes de escribir un
# solo archivo y lo explica sin culpar: junta los problemas y los dice juntos,
# cada uno con qué pasa y cómo se arregla. Deja $pyExe/$pyArgs (Python >= 3.9).
# Ojo: el `python.exe` de %LOCALAPPDATA%\Microsoft\WindowsApps puede ser el ATAJO
# de la Microsoft Store (sin argumentos abre la tienda; con -c falla) — por eso se
# PRUEBA cada candidato con -c en vez de confiar en Get-Command.
# La ubicación (OneDrive) ya la validó Assert-WsLocation arriba.
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
function Invoke-WsPreflight([string]$Dest) {
  $script:pyExe = $null
  $script:pyArgs = @()
  $fails = New-Object System.Collections.ArrayList
  if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
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
        break
      }
    }
  }
  if (-not $script:pyExe) {
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
      }
    } catch { }
  }
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
} elseif (-not (Invoke-WsPreflight $dest)) {
  exit 1
}
if ($env:WORKSPACE_SETUP_PREFLIGHT_ONLY -eq "1") { Write-Host "ok  $dest ($pyExe)"; exit 0 }
# <<< workspace-preflight

$cleanUrl = "https://$repo"
if ($env:WORKSPACE_TOKEN) { $url = "https://$($env:WORKSPACE_TOKEN)@$repo" } else { $url = $cleanUrl }

Write-Host "Workspace (harness) -> $dest"
if (Test-Path (Join-Path $dest ".git")) {
  Write-Host "Ya esta instalado; actualizando..."
  try { git -C "$dest" pull --ff-only }
  catch { Write-Host "  no pude actualizar (sin conexion o cambios locales) - sigo con lo que ya tienes" }
} elseif (Test-Path $dest) {
  $bk = "${dest}_backup_$(Get-Date -Format yyyyMMddHHmmss)"
  Write-Host "Respaldando copia previa (no se borra nada) -> $bk"
  Move-Item $dest $bk
  git clone $url $dest
} else {
  git clone $url $dest
}

# Higiene de token: nunca dejarlo persistido en el remote (idempotente).
if (Test-Path (Join-Path $dest ".git")) {
  $remote = git -C "$dest" remote get-url origin
  if ($remote -match "@") { git -C "$dest" remote set-url origin $cleanUrl }
}

Write-Host "Instalando (comando workspace + hooks)..."
& $pyExe @pyArgs (Join-Path $dest "install.py") @args
if ($LASTEXITCODE) { exit $LASTEXITCODE }

Write-Host ""
Write-Host "Listo. Abre una terminal NUEVA y escribe:  workspace"
Write-Host "  -> menu vacio -> 'Agregar agente' (crear o cargar tu cerebro)."
Write-Host "  Para actualizar despues:  workspace update"
