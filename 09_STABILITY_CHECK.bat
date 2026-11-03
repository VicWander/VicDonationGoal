@echo off
cd /d "%~dp0"
set "VDG_TITLE_VERSION=dev"
if exist "%~dp0VERSION" set /p VDG_TITLE_VERSION=<"%~dp0VERSION"
title VicDonationGoal v%VDG_TITLE_VERSION% - Stability Check

py -3 --version >nul 2>&1
if %errorlevel%==0 (
  py -3 tools\stability_check.py
) else (
  python tools\stability_check.py
)

echo.
pause
