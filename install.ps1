# Workspace - short installer (Windows). ASCII only: Windows PowerShell 5.1 reads this file as ANSI.
#   irm https://workspacecli.ai/install.ps1 | iex
# Downloads the official installer from the repo (always the latest) and runs it the same way the install guide does.
$ErrorActionPreference = 'Stop'
$f = Join-Path $env:TEMP 'workspace-setup.ps1'
Invoke-RestMethod 'https://raw.githubusercontent.com/MaxGarcia399/workspace/main/setup.ps1' -OutFile $f
powershell -NoProfile -ExecutionPolicy Bypass -File $f
