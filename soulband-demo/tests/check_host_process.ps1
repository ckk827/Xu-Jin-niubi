$ErrorActionPreference = 'Stop'
. (Join-Path (Split-Path -Parent $PSScriptRoot) 'host_process.ps1')
$script:fixturePython = 'C:\Soulband Project\.venv\Scripts\python.exe'
$script:fixtureBase = 'C:\Anaconda\python.exe'
$script:fixturePort = 19876
$script:fixtureChecks = 0

function Get-NetTCPConnection { param($LocalPort, $ErrorAction) return $script:fixtureEndpoints }
function Get-CimInstance {
    param($ClassName, $Filter)
    $fixtureId = [int]([regex]::Match($Filter, '\d+').Value)
    return $script:fixtureProcesses[$fixtureId]
}
function Stop-Process {
    param([int]$Id, $ErrorAction)
    $script:fixtureStopped += $Id
    $script:fixtureEndpoints = @($script:fixtureEndpoints | Where-Object { $_.OwningProcess -ne $Id })
}
function New-FixtureProcess {
    param([int]$Identity, [string]$Executable, [string]$Arguments, [int]$Parent = 0)
    return [pscustomobject]@{ProcessId=$Identity; ParentProcessId=$Parent; ExecutablePath=$Executable;
        CommandLine=('"' + $Executable + '" ' + $Arguments); CreationDate=[datetime]'2026-01-01'}
}
function Invoke-FixtureCase {
    param([string]$Name, [array]$Processes, [array]$Owners, [array]$ExpectedStops)
    $script:fixtureProcesses = @{}
    foreach ($fixtureProcess in $Processes) { $script:fixtureProcesses[$fixtureProcess.ProcessId] = $fixtureProcess }
    $script:fixtureEndpoints = @($Owners | ForEach-Object { [pscustomobject]@{RemotePort=0; OwningProcess=$_} })
    $script:fixtureStopped = @()
    $fixtureFailed = $false
    try { Stop-SoulbandHost -Python $script:fixturePython -Port $script:fixturePort } catch { $fixtureFailed = $true }
    if ($null -eq $ExpectedStops) {
        if (-not $fixtureFailed -or $script:fixtureStopped.Count -ne 0) { throw "Unrelated process was not protected: $Name" }
    } else {
        if ($fixtureFailed -or (($script:fixtureStopped -join ',') -ne ($ExpectedStops -join ','))) { throw "Host stop failed: $Name" }
    }
    $script:fixtureChecks++
}

$fixtureArgs = '-m uvicorn app:app --host 127.0.0.1 --port 19876'
$fixtureDirect = New-FixtureProcess 101 $script:fixturePython $fixtureArgs
$fixtureChild = New-FixtureProcess 102 $script:fixtureBase $fixtureArgs 101
$fixtureOther = New-FixtureProcess 103 'C:\Other\.venv\Scripts\python.exe' $fixtureArgs
Invoke-FixtureCase 'direct venv, quoted path containing spaces' @($fixtureDirect) @(101) @(101)
Invoke-FixtureCase 'Anaconda child of the exact venv launcher' @($fixtureDirect,$fixtureChild) @(102) @(102)
Invoke-FixtureCase 'different project' @($fixtureOther) @(103) $null
Invoke-FixtureCase 'base Python without verified venv parent' @($fixtureChild) @(102) $null
Invoke-FixtureCase 'different module' @((New-FixtureProcess 104 $script:fixturePython '-m http.server 19876')) @(104) $null
Invoke-FixtureCase 'port prefix is not an exact port match' @((New-FixtureProcess 105 $script:fixturePython '-m uvicorn app:app --port 198760')) @(105) $null
Invoke-FixtureCase 'uvicorn text inside script arguments' @((New-FixtureProcess 106 $script:fixturePython 'other.py -m uvicorn app:app --port 19876')) @(106) $null
Invoke-FixtureCase 'validate all owners before stopping any' @($fixtureDirect,$fixtureOther) @(101,103) $null
Invoke-FixtureCase 'matching parent but different command' @((New-FixtureProcess 101 $script:fixturePython '-m http.server 19876'),$fixtureChild) @(102) $null
Write-Output ("Process ownership fixtures passed: " + $script:fixtureChecks)
