@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" (
  echo SignalDesk's Python environment is missing. Run Start-SignalDesk.cmd to set it up.
  goto failed
)
".venv\Scripts\python.exe" -m signaldesk.launcher stop
if errorlevel 1 goto failed
popd
exit /b 0
:failed
popd
pause
exit /b 1
