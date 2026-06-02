@echo off
cd /d "%~dp0core"
title Donation Goal - Core Server

py -3 --version >nul 2>&1
if %errorlevel%==0 (
  py -3 server.py
) else (
  python server.py
)

pause
