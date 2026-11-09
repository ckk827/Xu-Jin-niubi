param([switch]$Lan, [switch]$SmokeTest, [switch]$Browser)
$ErrorActionPreference = 'Stop'
if ($Lan -and $SmokeTest) { throw 'Choose either LAN hosting or the offscreen startup check.' }
if ($Browser -and ($Lan -or $SmokeTest)) { throw 'Browser mode cannot be combined with LAN or smoke test.' }
Set-Location -LiteralPath $PSScriptRoot
$readyPython = Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $readyPython)) { throw 'Run the existing demo environment setup first.' }
. (Join-Path $PSScriptRoot 'desktop_runtime.ps1')
Repair-SoulbandDesktopRuntime -Python $readyPython
$env:SOULBAND_DB = Join-Path $PSScriptRoot 'data\acceptance-v0.4.sqlite3'
if ($SmokeTest) {
    $readyTestFolder = Join-Path $PSScriptRoot 'tests\.data'
    New-Item -ItemType Directory -Path $readyTestFolder -Force | Out-Null
    $env:SOULBAND_DB = Join-Path $readyTestFolder ('ready-startup-' + [guid]::NewGuid().ToString('N') + '.sqlite3')
}
. (Join-Path $PSScriptRoot 'host_process.ps1')
Stop-SoulbandHost -Python $readyPython -Port 8765
Stop-SoulbandHost -Python $readyPython -Port 8766
& $readyPython configure_test.py
if ($LASTEXITCODE -ne 0) { throw 'Acceptance database setup failed.' }
if ($Lan) { & .\Launch-MobileHost.ps1 }
elseif ($SmokeTest) { & $readyPython desktop.py --smoke-test }
elseif ($Browser) { & $readyPython desktop.py --browser }
else { & $readyPython desktop.py }
if ($LASTEXITCODE -ne 0) { throw 'Soulband UI failed to start. See data/desktop.log and data/server.log.' }
