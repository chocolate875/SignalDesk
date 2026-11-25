@echo off
setlocal DisableDelayedExpansion
pushd "%~dp0" || exit /b 1
if not exist ".venv\Scripts\python.exe" (
  echo SignalDesk's Python environment is missing. Run Start-SignalDesk.cmd to set it up.
  popd
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -X utf8 -m signaldesk.cleanup %*
set "cleanup_status=%errorlevel%"
popd
if "%~1"=="" pause
exit /b %cleanup_status%
