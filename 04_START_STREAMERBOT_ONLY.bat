@echo off
cd /d "%~dp0integrations\streamerbot"
set "VDG_TITLE_VERSION=dev"
if exist "%~dp0VERSION" set /p VDG_TITLE_VERSION=<"%~dp0VERSION"
title VicDonationGoal v%VDG_TITLE_VERSION% - Streamer.bot Bridge

py -3 --version >nul 2>&1
if %errorlevel%==0 (
  py -3 streamerbot_bridge.py --managed
) else (
  python streamerbot_bridge.py --managed
)

pause
