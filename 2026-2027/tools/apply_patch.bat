@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0apply_patch.ps1" %*
if errorlevel 1 pause
endlocal
