@echo off
cd /d "%~dp0integrations\streamerbot"
title Donation Goal - Streamer.bot Bridge

py -3 --version >nul 2>&1
if %errorlevel%==0 (
  py -3 streamerbot_bridge.py
) else (
  python streamerbot_bridge.py
)

pause
