$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$memberPython = Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $memberPython)) { throw 'Run the project environment setup first.' }
& $memberPython peer_desktop.py
