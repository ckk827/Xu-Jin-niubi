function Stop-SoulbandHost {
    param([string]$Python, [int]$Port)
    # Some Windows builds return null State for bound listeners. Inspect the
    # bound local endpoint and then verify ownership, rather than trusting State.
    $hostEndpoints = @(Get-NetTCPConnection -LocalPort $Port -ErrorAction SilentlyContinue | Where-Object { $_.RemotePort -eq 0 -and $_.OwningProcess -gt 0 })
    foreach ($hostPid in @($hostEndpoints.OwningProcess | Select-Object -Unique)) {
        $hostProcess = Get-CimInstance Win32_Process -Filter "ProcessId = $hostPid"
        $hostExpected = '*' + [WildcardPattern]::Escape($Python) + '*uvicorn app:app*--port ' + $Port + '*'
        if (-not $hostProcess -or $hostProcess.CommandLine -notlike $hostExpected) { throw "Port $Port belongs to another program. It was not stopped." }
        Stop-Process -Id $hostPid -ErrorAction Stop
    }
}
