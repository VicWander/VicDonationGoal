@echo off
cd /d "%~dp0"

echo Installing requests for Streamer.bot bridge...
py -3 -m pip install requests
if %errorlevel% neq 0 (
  python -m pip install requests
)

echo.
echo Done.
pause
