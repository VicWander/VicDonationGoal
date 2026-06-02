@echo off
cd /d "%~dp0"

start "Donation Goal Server" cmd /k start.bat
start "Donatty Listener" cmd /k start_donatty.bat
