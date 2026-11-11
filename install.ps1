# Workspace — instalador corto (Windows).
#   irm https://workspacecli.ai/install.ps1 | iex
# Baja el instalador oficial del repo (siempre el más reciente) y lo corre igual que la guía de instalación.
$ErrorActionPreference = 'Stop'
$f = Join-Path $env:TEMP 'workspace-setup.ps1'
Invoke-RestMethod 'https://raw.githubusercontent.com/MaxGarcia399/workspace/main/setup.ps1' -OutFile $f
powershell -NoProfile -ExecutionPolicy Bypass -File $f
