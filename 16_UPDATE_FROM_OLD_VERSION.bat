@echo off
cd /d "%~dp0"
title VicDonationGoal - Update from an old version
echo Stop BOTH old and new versions before continuing.
echo Select the OLD folder in the window. This NEW folder receives its data.
py -3 --version >nul 2>&1
if %errorlevel%==0 (set PY=py -3) else (set PY=python)
%PY% tools\update_from_old.py
if errorlevel 1 echo Update failed. Keep the old folder and check the message above.
pause
