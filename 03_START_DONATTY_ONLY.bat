@echo off
cd /d "%~dp0integrations\donatty"
title Donation Goal - Donatty Listener

py -3 --version >nul 2>&1
if %errorlevel%==0 (
  py -3 donatty_listener.py
) else (
  python donatty_listener.py
)

pause
