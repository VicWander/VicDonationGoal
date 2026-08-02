@echo off
setlocal
cd /d "%~dp0"
echo Installing cloudflared for Tribute...
python tools\install_cloudflared.py
if errorlevel 1 (
  echo.
  echo Installation failed. Read the message above.
) else (
  echo.
  echo cloudflared is ready. Return to Integration Hub and restart Tribute.
)
echo.
pause
endlocal
