function Test-SoulbandHostInvocation {
    param($Process, [int]$Port)
    if (-not $Process -or -not $Process.CommandLine -or -not $Process.ExecutablePath) { return $false }
    $hostExecutable = [regex]::Escape($Process.ExecutablePath)
    $hostModulePattern = '^\s*"?' + $hostExecutable + '"?\s+-m\s+uvicorn\s+app:app(?=\s|$)'
    $hostPortPattern = '(?:^|\s)--port(?:\s+|=)(?:"' + $Port + '"|' + $Port + ')(?=\s|$)'
    return ($Process.CommandLine -match $hostModulePattern -and $Process.CommandLine -match $hostPortPattern)
}

function Stop-SoulbandHost {
    param([string]$Python, [int]$Port)
    $hostPythonPath = [IO.Path]::GetFullPath($Python)
    # Bound listeners can have a null State on some Windows builds.
    $hostEndpoints = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.RemotePort -eq 0 -and $_.OwningProcess -gt 0 })
    $hostVerified = @()
    foreach ($hostPid in @($hostEndpoints.OwningProcess | Select-Object -Unique)) {
        $hostProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $hostPid"
        $hostOwned = $false
        if (Test-SoulbandHostInvocation -Process $hostProcess -Port $Port) {
            $hostOwned = [string]::Equals($hostProcess.ExecutablePath, $hostPythonPath, [StringComparison]::OrdinalIgnoreCase)
            if (-not $hostOwned -and $hostProcess.ParentProcessId -gt 0) {
                # A Windows venv launcher delegates to its base Python (e.g. Anaconda).
                # Verify that the direct parent is this project's exact venv launcher
                # running the same command; a generic Python/uvicorn process is not enough.
                $hostParent = Get-CimInstance Win32_Process -Filter ("ProcessId = " + $hostProcess.ParentProcessId)
                $hostOwned = ($hostParent -and
                    [string]::Equals($hostParent.ExecutablePath, $hostPythonPath, [StringComparison]::OrdinalIgnoreCase) -and
                    $hostParent.CreationDate -and $hostProcess.CreationDate -and
                    $hostParent.CreationDate -le $hostProcess.CreationDate -and
                    (Test-SoulbandHostInvocation -Process $hostParent -Port $Port))
            }
        }
        if (-not $hostOwned) {
            throw "Port $Port is occupied by PID $hostPid and is not a verified host from this project. It was not stopped."
        }
        $hostVerified += $hostPid
    }
    # Validate every owner before stopping any process (IPv4 and IPv6 may differ).
    foreach ($hostPid in $hostVerified) { Stop-Process -Id $hostPid -ErrorAction Stop }
    if ($hostVerified.Count -eq 0) { return }
    for ($hostWait = 0; $hostWait -lt 50; $hostWait++) {
        $hostRemaining = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.RemotePort -eq 0 -and $_.OwningProcess -gt 0 })
        if ($hostRemaining.Count -eq 0) { return }
        Start-Sleep -Milliseconds 100
    }
    throw "Port $Port did not become free after the old project host exited. Please try again."
}
