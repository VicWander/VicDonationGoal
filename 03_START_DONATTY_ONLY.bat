@echo off
cd /d "%~dp0integrations\donatty"
echo DEBUG MODE: normally Donatty is started and stopped from Integration Hub.
echo.
title VicDonationGoal v1.4.4.1 - Donatty Debug Listener

py -3 --version >nul 2>&1
if %errorlevel%==0 (
  py -3 donatty_listener.py
) else (
  python donatty_listener.py
)

pause
