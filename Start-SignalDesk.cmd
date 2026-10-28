@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" goto setup
if not exist "frontend\dist\index.html" goto setup
goto launch
:setup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup.ps1"
if errorlevel 1 (
  pause
  exit /b 1
)
:launch
start "" ".venv\Scripts\pythonw.exe" -m signaldesk.desktop
endlocal
