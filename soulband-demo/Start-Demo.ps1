$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$demoPython = Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $demoPython)) {
    python -m venv ..\.venv
    if ($LASTEXITCODE -ne 0) { throw 'Could not create Python environment.' }
}
. (Join-Path $PSScriptRoot 'desktop_runtime.ps1')
Repair-SoulbandDesktopRuntime -Python $demoPython
& $demoPython -c "import importlib.util as i,sys;from importlib.metadata import version;sys.exit(0 if all(i.find_spec(m) is not None for m in ['fastapi','uvicorn','httpx','PySide6']) and version('PySide6')=='6.10.3' else 1)"
if ($LASTEXITCODE -ne 0) {
    & $demoPython -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
    Repair-SoulbandDesktopRuntime -Python $demoPython
}
& $demoPython -c "import storage as db; db.mutate(lambda s: s.update(mode='demo',model='qwen2.5:7b',model_configured=True))"
if ($LASTEXITCODE -ne 0) { throw 'Demo configuration failed.' }
& $demoPython desktop.py
if ($LASTEXITCODE -ne 0) { throw 'Demo exited with an error. See data/server.log.' }
