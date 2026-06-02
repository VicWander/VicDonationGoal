@echo off
cd /d "%~dp0"
title Donation Goal Widget - Start All

echo ==============================================
echo  Starting Donation Goal Widget stack
echo ==============================================
echo.
echo Opening:
echo - Core server + OBS widget
echo - Donatty listener
echo - Streamer.bot bridge
echo.

start "Donation Goal - Core Server" cmd /k call "%~dp002_START_SERVER_ONLY.bat"
timeout /t 2 /nobreak >nul

start "Donation Goal - Donatty Listener" cmd /k call "%~dp003_START_DONATTY_ONLY.bat"
timeout /t 1 /nobreak >nul

start "Donation Goal - Streamer.bot Bridge" cmd /k call "%~dp004_START_STREAMERBOT_ONLY.bat"

echo.
echo All windows were opened.
echo Admin:  http://127.0.0.1:3333/admin.html
echo Widget: http://127.0.0.1:3333/widget.html
echo.
pause
