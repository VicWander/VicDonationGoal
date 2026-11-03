@echo off
cd /d "%~dp0core"
set "VDG_TITLE_VERSION=dev"
if exist "%~dp0VERSION" set /p VDG_TITLE_VERSION=<"%~dp0VERSION"
title VicDonationGoal v%VDG_TITLE_VERSION% - Core + Integration Manager

py -3 --version >nul 2>&1
if %errorlevel%==0 (
  py -3 server.py
) else (
  python server.py
)

pause
