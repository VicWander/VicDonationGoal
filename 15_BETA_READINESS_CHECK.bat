@echo off
chcp 65001 >nul
cd /d "%~dp0"
python tools\beta_readiness_check.py
set CODE=%ERRORLEVEL%
echo.
if not "%CODE%"=="0" echo Beta Readiness Check found errors.
if "%CODE%"=="0" echo Beta Readiness Check completed successfully.
pause
exit /b %CODE%
