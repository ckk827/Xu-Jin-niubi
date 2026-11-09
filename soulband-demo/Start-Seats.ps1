param([int]$Port = 8802, [switch]$SmokeTest)
$ErrorActionPreference = 'Stop'
# Keep UTF-8 with BOM: the .cmd launcher uses Windows PowerShell 5.1.
Set-Location -LiteralPath $PSScriptRoot

$hostPython = Join-Path (Split-Path -Parent $PSScriptRoot) '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $hostPython)) {
    $hostPython = (Get-Command python -ErrorAction Stop).Source
    Write-Host "没有找到 .venv，暂用系统 Python：$hostPython" -ForegroundColor Yellow
}
& $hostPython -c "import importlib.util as i,sys;sys.exit(0 if all(i.find_spec(m) is not None for m in ['fastapi','uvicorn']) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host '正在安装后端依赖（仅 fastapi/uvicorn/httpx/pydantic 等，不含桌面外壳）...' -ForegroundColor Yellow
    & $hostPython -m pip install --no-cache-dir -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw '依赖安装失败。' }
}

$env:SOULBAND_DB = Join-Path $PSScriptRoot 'data\seats-v0.5.sqlite3'
if ($SmokeTest) {
    $seatTestFolder = Join-Path $PSScriptRoot 'tests\.data'
    New-Item -ItemType Directory -Path $seatTestFolder -Force | Out-Null
    $env:SOULBAND_DB = Join-Path $seatTestFolder ('seat-startup-' + [guid]::NewGuid().ToString('N') + '.sqlite3')
}
. (Join-Path $PSScriptRoot 'host_process.ps1')
& $hostPython -c "import storage as db; db.mutate(lambda s: s.update(mode='demo',model='qwen2.5:7b',model_configured=True))"
if ($LASTEXITCODE -ne 0) { throw 'Demo configuration failed.' }
Stop-SoulbandHost -Python $hostPython -Port $Port

$server = Start-Process -FilePath $hostPython `
    -ArgumentList @('-m', 'uvicorn', 'app:app', '--host', '127.0.0.1', '--port', "$Port") `
    -PassThru -WindowStyle Hidden
$base = "http://127.0.0.1:$Port"
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    Start-Sleep -Milliseconds 500
    try { Invoke-RestMethod "$base/api/health" -TimeoutSec 2 | Out-Null; $ready = $true; break } catch { }
}
if (-not $ready) {
    Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    throw '服务未能启动，请查看上面的日志。'
}

if ($SmokeTest) {
    try {
        foreach ($member in 'm1', 'm2', 'm3', 'm4') {
            $seatBody = @{member_id=$member} | ConvertTo-Json -Compress
            $seat = Invoke-RestMethod "$base/api/demo/seat" -Method Post -ContentType 'application/json' -Body $seatBody
            $seatIdentity = Invoke-RestMethod "$base/api/access/me" -Headers @{Authorization=('Bearer ' + $seat.token)}
            if ($seatIdentity.member_id -ne $member -or -not $seatIdentity.seat -or $seatIdentity.local_demo) {
                throw "Seat identity check failed: $member"
            }
        }
        Write-Host 'Startup check passed: host health and four independent seat sessions; isolated test database.' -ForegroundColor Green
    } finally {
        Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue
    }
    return
}

Write-Host "宿伴 v0.5 同机四座位演示已启动：$base" -ForegroundColor Green
Write-Host '四个浏览器窗口分别代表四位室友；它们走同一套会话与权限，不是绕过鉴权的多个管理员。'
Write-Host '每个窗口首次打开时会向宿主申请一个演示座位（仅限本机），之后在窗口内独立轮询。'
foreach ($member in 'm1', 'm2', 'm3', 'm4') {
    Start-Process "$base/?seat=$member"
    Start-Sleep -Milliseconds 400
}
Write-Host '关闭本窗口前，先按回车停止服务（数据库保留在 data\seats-v0.5.sqlite3）。'
try { [void](Read-Host) } finally { Stop-Process -Id $server.Id -Force -ErrorAction SilentlyContinue }
