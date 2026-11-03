@echo off
cd /d "%~dp0integrations\donatty"
echo DEBUG MODE: normally Donatty is started and stopped from Integration Hub.
echo.
set "VDG_TITLE_VERSION=dev"
if exist "%~dp0VERSION" set /p VDG_TITLE_VERSION=<"%~dp0VERSION"
title VicDonationGoal v%VDG_TITLE_VERSION% - Donatty Debug Listener

py -3 --version >nul 2>&1
if %errorlevel%==0 (
  py -3 donatty_listener.py
) else (
  python donatty_listener.py
)

pause
