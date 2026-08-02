@echo off
setlocal
cd /d "%~dp0"
set QUIET=
if /I "%~1"=="--quiet" set QUIET=--quiet

py -3 --version >nul 2>&1
if %errorlevel%==0 (
  py -3 tools\stop_all.py --all-vicdonationgoal %QUIET%
) else (
  python tools\stop_all.py --all-vicdonationgoal %QUIET%
)

if not defined QUIET pause
endlocal
