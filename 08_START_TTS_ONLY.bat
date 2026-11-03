@echo off
cd /d "%~dp0integrations\tts"
set "VDG_TITLE_VERSION=dev"
if exist "%~dp0VERSION" set /p VDG_TITLE_VERSION=<"%~dp0VERSION"
title VicDonationGoal v%VDG_TITLE_VERSION% - TTS Hub

py -3 --version >nul 2>&1
if %errorlevel%==0 (
  py -3 tts_hub.py
) else (
  python tts_hub.py
)

pause
