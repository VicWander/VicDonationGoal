@echo off
cd /d "%~dp0integrations\streamerbot"
title Donation Goal - Reset Streamer.bot Sent

py -3 --version >nul 2>&1
if %errorlevel%==0 (
  py -3 streamerbot_bridge.py --reset-sent
) else (
  python streamerbot_bridge.py --reset-sent
)

pause
