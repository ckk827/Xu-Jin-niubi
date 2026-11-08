$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$demoPython = Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $demoPython)) { throw 'Run the desktop demo setup first.' }
. (Join-Path $PSScriptRoot 'host_process.ps1')
Stop-SoulbandHost -Python $demoPython -Port 8765
Stop-SoulbandHost -Python $demoPython -Port 8766
Write-Host 'Soulband mobile test host: local UI http://127.0.0.1:8765'
Write-Host 'Use the real LAN IPv4 address below on your phone. Keep this console open.'
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.IPAddress -notlike '169.254.*' } | Select-Object IPAddress,InterfaceAlias | Format-Table
Write-Host 'LAN members must pair with a one-time code. Local host retains demo identity controls.'
& $demoPython -m uvicorn app:app --host 0.0.0.0 --port 8765
