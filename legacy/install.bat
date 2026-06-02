@echo off
cd /d "%~dp0"

echo Installing Python libraries...
py -3 -m pip install -r requirements.txt
if %errorlevel% neq 0 (
  python -m pip install -r requirements.txt
)

echo.
echo Done.
pause
