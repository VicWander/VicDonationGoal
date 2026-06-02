@echo off
cd /d "%~dp0"

echo Installing Donatty Auto Listener dependencies...
echo.

py -3 -m pip install requests playwright
if %errorlevel% neq 0 (
  python -m pip install requests playwright
)

echo.
echo Installing Playwright Chromium browser...
echo This can take a few minutes.
echo.

py -3 -m playwright install chromium
if %errorlevel% neq 0 (
  python -m playwright install chromium
)

echo.
echo Done.
pause
