@echo off
cd /d "%~dp0soulband-demo"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0soulband-demo\Start-Ready.ps1"
pause
