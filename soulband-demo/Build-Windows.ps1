param([string]$OutputDirectory)
$ErrorActionPreference = 'Stop'
$buildProject = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $buildProject
if (-not $OutputDirectory) { $OutputDirectory = Join-Path $buildProject ('output\windows-' + (Get-Date -Format 'yyyyMMdd-HHmmss')) }
$buildAbsolute = [IO.Path]::GetFullPath($OutputDirectory)
if (Test-Path -LiteralPath $buildAbsolute) { throw 'Choose a new output directory. Existing builds are never deleted or replaced.' }
$buildWork = Join-Path $buildAbsolute '_build'
$buildPython = Join-Path $buildProject '.venv\Scripts\python.exe'
$buildOriginalPath = $env:PATH
try {
    # Poppler carries an incompatible ICU with the same DLL name as Windows ICU.
    # Change only this build process's PATH; Qt must resolve the system ICU.
    $env:PATH = (($env:PATH -split ';') | Where-Object { $_ -notmatch '\\poppler\\Library\\bin\\?$' }) -join ';'
    $buildCa = Join-Path $PSScriptRoot 'data\tls\soulband-ca.crt'
    if (-not (Test-Path -LiteralPath $buildCa)) { throw 'Generate project TLS certificates with prepare_tls.py before packaging.' }
    & $buildPython -m PyInstaller --onedir --windowed --name Soulband-Windows --distpath $buildAbsolute --workpath $buildWork --specpath $buildWork --add-data "${buildCa};." (Join-Path $PSScriptRoot 'peer_desktop.py')
    if ($LASTEXITCODE -ne 0) { throw 'Windows packaging failed.' }
    Write-Host ('Built member client: ' + (Join-Path $buildAbsolute 'Soulband-Windows\Soulband-Windows.exe'))
    Write-Host 'Copy the whole Soulband-Windows directory, not only the exe. Run the packaged smoke check before distributing.'
} finally { $env:PATH = $buildOriginalPath }
