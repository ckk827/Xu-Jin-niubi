$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$securePython = Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'
$env:SOULBAND_DB = Join-Path $PSScriptRoot 'data\acceptance-v0.4.sqlite3'
. (Join-Path $PSScriptRoot 'host_process.ps1')
Stop-SoulbandHost -Python $securePython -Port 8765
Stop-SoulbandHost -Python $securePython -Port 8766
$secureAddresses = @(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -ne '127.0.0.1' -and $_.IPAddress -notlike '169.254.*' })
$secureArguments = @('prepare_tls.py')
foreach ($secureAddress in $secureAddresses) { $secureArguments += @('--ip', $secureAddress.IPAddress) }
& $securePython @secureArguments
if ($LASTEXITCODE -ne 0) { throw 'TLS certificate preparation failed.' }
$secureUser = [Security.Principal.WindowsIdentity]::GetCurrent().Name
foreach ($secureKey in @('data\tls\ca.key', 'data\tls\server.key')) {
    & icacls.exe $secureKey /inheritance:r /grant:r "${secureUser}:(F)" '*S-1-5-18:(F)' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Cannot protect TLS private key.' }
}
& $securePython configure_test.py
if ($LASTEXITCODE -ne 0) { throw 'Database preparation failed.' }
Write-Host 'Soulband HTTPS host. Keep this window open. Do not share data/tls/*.key.'
Write-Host 'Local browser: https://127.0.0.1:8766 (first trust the matching soulband-ca.crt).'
$secureAddresses | ForEach-Object { Write-Host ('Member address: https://' + $_.IPAddress + ':8766') }
Write-Host 'Bundled v0.4 clients trust this project CA; browser trust instructions: docs/HTTPS.md.'
& $securePython -m uvicorn app:app --host 0.0.0.0 --port 8766 --ssl-keyfile data/tls/server.key --ssl-certfile data/tls/server.crt
