@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" goto setup
if not exist ".venv\Scripts\pythonw.exe" goto setup
if not exist "frontend\dist\index.html" goto setup
if not exist "frontend\dist\assets\*.js" goto setup
goto launch
:setup
powershell.exe -NoProfile -ExecutionPolicy Bypass -File ".\scripts\setup.ps1"
if errorlevel 1 goto failed
:launch
".venv\Scripts\python.exe" -m signaldesk.launcher start %*
if errorlevel 1 goto failed
popd
exit /b 0
:failed
popd
pause
exit /b 1
