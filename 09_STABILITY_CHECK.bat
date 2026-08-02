@echo off
cd /d "%~dp0"
title VicDonationGoal v1.4.4 - Stability Check

py -3 --version >nul 2>&1
if %errorlevel%==0 (
  py -3 tools\stability_check.py
) else (
  python tools\stability_check.py
)

echo.
pause
