param([string]$JdkHome = $env:JAVA_HOME, [string]$SdkRoot = $env:ANDROID_HOME)
$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
if (-not $JdkHome -and (Test-Path -LiteralPath 'D:\JDK17\bin\java.exe')) { $JdkHome = 'D:\JDK17' }
if (-not $SdkRoot -and (Test-Path -LiteralPath 'D:\SoulbandBuild\android-sdk\platforms\android-35\android.jar')) { $SdkRoot = 'D:\SoulbandBuild\android-sdk' }
if (-not $JdkHome -or -not (Test-Path -LiteralPath (Join-Path $JdkHome 'bin\java.exe'))) { throw 'Set JAVA_HOME to JDK 17, or pass -JdkHome.' }
if (-not $SdkRoot -or -not (Test-Path -LiteralPath (Join-Path $SdkRoot 'platforms\android-35\android.jar'))) { throw 'Install Android SDK platform 35 and build-tools 35.0.0; set ANDROID_HOME or pass -SdkRoot.' }
$env:JAVA_HOME = $JdkHome
$apkProjectCa = Join-Path (Split-Path -Parent $PSScriptRoot) 'soulband-demo\data\tls\soulband-ca.crt'
if (-not (Test-Path -LiteralPath $apkProjectCa)) { throw 'Generate the project TLS CA with soulband-demo/prepare_tls.py before building.' }
New-Item -ItemType Directory -Path (Join-Path $PSScriptRoot 'app\src\main\res\raw') -Force | Out-Null
Copy-Item -LiteralPath $apkProjectCa -Destination (Join-Path $PSScriptRoot 'app\src\main\res\raw\soulband_local_ca.pem')
$sdkProperty = $SdkRoot.Replace('\','/').Replace(':','\:')
[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'local.properties'), "sdk.dir=$sdkProperty`n", [Text.UTF8Encoding]::new($false))
& .\gradlew.bat --no-daemon --console=plain assembleDebug lintDebug
if ($LASTEXITCODE -ne 0) { throw 'Android build or lint failed.' }
$apkOutput = Join-Path (Split-Path -Parent $PSScriptRoot) 'output\apk'
New-Item -ItemType Directory -Path $apkOutput -Force | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'app\build\outputs\apk\debug\app-debug.apk') -Destination (Join-Path $apkOutput 'Soulband-v0.4.0-debug.apk')
Get-FileHash -LiteralPath (Join-Path $apkOutput 'Soulband-v0.4.0-debug.apk') -Algorithm SHA256 | Format-List
