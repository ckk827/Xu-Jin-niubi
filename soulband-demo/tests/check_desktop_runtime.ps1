param([Parameter(Mandatory = $true)][string]$Folder)
$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'desktop_runtime.ps1')
$fixtureScripts = Join-Path $Folder '.venv\Scripts'
$fixtureQt = Join-Path $Folder '.venv\Lib\site-packages\PySide6'
$fixturePlugin = Join-Path $fixtureQt 'plugins\platforms'
$fixtureData = Join-Path $Folder 'data'
foreach ($fixtureDirectory in @($fixtureScripts, $fixtureQt, $fixturePlugin, $fixtureData)) {
    New-Item -ItemType Directory -Path $fixtureDirectory -Force | Out-Null
}
$fixturePython = Join-Path $fixtureScripts 'python.exe'
$fixtureDll = Join-Path $fixtureQt 'Qt6Core.dll'
$fixtureWorker = Join-Path $fixtureQt 'QtWebEngineProcess.exe'
$fixturePluginDll = Join-Path $fixturePlugin 'qwindows.dll'
$fixtureDatabase = Join-Path $fixtureData 'state.sqlite3'
foreach ($fixtureFile in @($fixturePython, $fixtureDll, $fixtureWorker, $fixturePluginDll, $fixtureDatabase)) {
    Set-Content -LiteralPath $fixtureFile -Value 'integrity-only test fixture'
    & icacls.exe $fixtureFile /setintegritylevel L | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not label disposable fixture.' }
}
foreach ($fixtureDirectory in @($fixtureScripts, $fixtureQt)) {
    & icacls.exe $fixtureDirectory /setintegritylevel '(OI)(CI)L' | Out-Null
    if ($LASTEXITCODE -ne 0) { throw 'Could not label disposable directory.' }
}
$fixtureAccessSection = [Security.AccessControl.AccessControlSections]::Access
$fixtureDacl = [IO.Directory]::GetAccessControl($fixtureQt).GetSecurityDescriptorSddlForm($fixtureAccessSection)
$fixtureBytes = [Convert]::ToBase64String([IO.File]::ReadAllBytes($fixtureDatabase))
if ((Get-SoulbandFileIntegrity -Path $fixtureWorker) -ne 4096) { throw 'Low image fixture was not created.' }
Repair-SoulbandDesktopRuntime -Python $fixturePython
foreach ($fixtureImage in @($fixturePython, $fixtureDll, $fixtureWorker, $fixturePluginDll)) {
    if ((Get-SoulbandFileIntegrity -Path $fixtureImage) -ne 8192) { throw "Not repaired: $fixtureImage" }
}
if ([IO.Directory]::GetAccessControl($fixtureQt).GetSecurityDescriptorSddlForm($fixtureAccessSection) -ne $fixtureDacl) { throw 'DACL was changed.' }
if ((Get-SoulbandFileIntegrity -Path $fixtureDatabase) -ne 4096) { throw 'Business-data label was changed.' }
if ([Convert]::ToBase64String([IO.File]::ReadAllBytes($fixtureDatabase)) -ne $fixtureBytes) { throw 'Business-data contents changed.' }
$fixtureSecondOutput = @(Repair-SoulbandDesktopRuntime -Python $fixturePython 6>&1)
if ($fixtureSecondOutput.Count) { throw 'Repair is not idempotent.' }
$fixtureRejected = $false
try { Repair-SoulbandDesktopRuntime -Python (Join-Path $Folder 'other.exe') } catch { $fixtureRejected = $true }
if (-not $fixtureRejected) { throw 'Non-venv input was accepted.' }
Write-Output 'Desktop integrity fixtures passed: 7'
