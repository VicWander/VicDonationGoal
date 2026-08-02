@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"
title VicDonationGoal v1.4.4 - Closed Beta

echo Stopping stale VicDonationGoal processes from previous runs...
call "%~dp013_STOP_ALL.bat" --quiet >nul 2>&1

set APP_VERSION=dev
if exist "%~dp0VERSION" set /p APP_VERSION=<"%~dp0VERSION"

echo ==============================================
echo  VicDonationGoal v%APP_VERSION% - Closed Beta
echo ==============================================
echo.
echo Creating missing local files...
call "%~dp007_CREATE_LOCAL_CONFIGS.bat" --quiet >nul

echo Starting Core server...
start "VicDonationGoal - Core Server" cmd /k call "%~dp002_START_SERVER_ONLY.bat"

echo Waiting for http://127.0.0.1:3333/api/health ...
set CORE_READY=0
for /L %%I in (1,1,30) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r = Invoke-RestMethod -Uri 'http://127.0.0.1:3333/api/health' -TimeoutSec 2; if ($r.ok) { exit 0 } else { exit 1 } } catch { exit 1 }" >nul 2>&1
  if !errorlevel! EQU 0 (
    set CORE_READY=1
    goto :core_ready
  )
  timeout /t 1 /nobreak >nul
)

:core_ready
if "%CORE_READY%"=="0" (
  echo.
  echo ERROR: Core server did not become ready in 30 seconds.
  echo Check the Core Server window. Other modules were not started.
  echo.
  pause
  exit /b 1
)

echo Core server is ready.
echo Starting Streamer.bot bridge...
start "VicDonationGoal - Streamer.bot Bridge" cmd /k call "%~dp004_START_STREAMERBOT_ONLY.bat"
timeout /t 1 /nobreak >nul

echo Starting TTS Hub...
start "VicDonationGoal - TTS Hub" cmd /k call "%~dp008_START_TTS_ONLY.bat"
timeout /t 1 /nobreak >nul

echo.
echo Core, enabled integrations, Streamer.bot Bridge and TTS Hub were launched.
echo Health: http://127.0.0.1:3333/api/health
echo Admin:  http://127.0.0.1:3333/admin.html
echo Integrations are managed by Core through Integration Hub.
echo Widget: http://127.0.0.1:3333/widget.html
echo TTS:    http://127.0.0.1:3333/tts.html
echo.
pause
endlocal
