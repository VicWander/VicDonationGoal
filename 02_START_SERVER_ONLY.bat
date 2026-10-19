@echo off
cd /d "%~dp0core"
title VicDonationGoal v1.4.4.1 - Core + Integration Manager

py -3 --version >nul 2>&1
if %errorlevel%==0 (
  py -3 server.py
) else (
  python server.py
)

pause
