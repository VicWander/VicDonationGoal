@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo Creating a safe diagnostic report...
python tools\create_diagnostic_report.py
if errorlevel 1 (
  echo.
  echo Diagnostic report failed.
  pause
  exit /b 1
)
echo.
echo The ZIP is in the diagnostics folder.
pause
