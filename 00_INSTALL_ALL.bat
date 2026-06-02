@echo off
cd /d "%~dp0"
title VicDonationGoal - Install All

echo ==============================================
echo  VicDonationGoal - first setup
 echo ==============================================
echo.
echo This will install:
echo - Python packages from requirements.txt
echo - Playwright Chromium browser
echo - Local config/data files from examples
echo.

py -3 --version >nul 2>&1
if %errorlevel%==0 (
  set PY=py -3
) else (
  set PY=python
)

echo [1/3] Installing Python packages...
%PY% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
  echo.
  echo ERROR: pip install failed.
  pause
  exit /b 1
)

echo.
echo [2/3] Installing Playwright Chromium...
%PY% -m playwright install chromium
if %errorlevel% neq 0 (
  echo.
  echo ERROR: Playwright Chromium install failed.
  pause
  exit /b 1
)

echo.
echo [3/3] Creating local config/data files...
call "%~dp007_CREATE_LOCAL_CONFIGS.bat"

echo.
echo ==============================================
echo  Done. You can now run 01_START_ALL.bat
echo ==============================================
pause
