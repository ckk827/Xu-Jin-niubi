$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$demoPython = Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $demoPython)) {
    python -m venv ..\.venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment.' }
}
& $demoPython -c "import importlib.util as i,sys;sys.exit(0 if all(i.find_spec(m) is not None for m in ['fastapi','uvicorn','httpx','PySide6']) else 1)"
if ($LASTEXITCODE -ne 0) {
    & $demoPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
}
& $demoPython desktop.py
if ($LASTEXITCODE -ne 0) { throw 'Demo exited with an error. See data/server.log.' }
