@echo off
cd /d "%~dp0integrations\streamerbot"
title Donation Goal - Test Streamer.bot Bridge

py -3 --version >nul 2>&1
if %errorlevel%==0 (
  py -3 streamerbot_bridge.py --test
) else (
  python streamerbot_bridge.py --test
)

pause
