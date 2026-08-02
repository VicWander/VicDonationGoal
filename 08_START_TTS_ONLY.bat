@echo off
cd /d "%~dp0integrations\tts"
title VicDonationGoal v1.4.4 - TTS Hub

py -3 --version >nul 2>&1
if %errorlevel%==0 (
  py -3 tts_hub.py
) else (
  python tts_hub.py
)

pause
