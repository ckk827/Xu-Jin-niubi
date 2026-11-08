param([switch]$Lan, [switch]$SmokeTest)
$ErrorActionPreference = 'Stop'
if ($Lan -and $SmokeTest) { throw 'Choose either LAN hosting or the offscreen startup check.' }
Set-Location -LiteralPath $PSScriptRoot
$readyPython = Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $readyPython)) { throw 'Run the existing demo environment setup first.' }
$env:SOULBAND_DB = Join-Path $PSScriptRoot 'data\acceptance-v0.4.sqlite3'
. (Join-Path $PSScriptRoot 'host_process.ps1')
Stop-SoulbandHost -Python $readyPython -Port 8765
Stop-SoulbandHost -Python $readyPython -Port 8766
& $readyPython prepare_model.py
if ($LASTEXITCODE -ne 0) { throw 'Model setup failed. The app was not silently switched to simulation.' }
& $readyPython configure_test.py
if ($LASTEXITCODE -ne 0) { throw 'Acceptance database setup failed.' }
if ($Lan) { & .\Launch-MobileHost.ps1 }
elseif ($SmokeTest) { & $readyPython desktop.py --smoke-test }
else { & $readyPython desktop.py }
