@echo off
cd /d "%~dp0"
title VicDonationGoal - Create Local Configs

echo ==============================================
echo  Creating local config/data files if missing
echo ==============================================
echo.

if not exist "core\data" mkdir "core\data"
if not exist "core\integrations\donationalerts" mkdir "core\integrations\donationalerts"
if not exist "integrations\donatty" mkdir "integrations\donatty"
if not exist "integrations\streamerbot" mkdir "integrations\streamerbot"

call :copy_if_missing "core\data\state.example.json" "core\data\state.json"
call :copy_if_missing "core\data\donations.example.json" "core\data\donations.json"
call :copy_if_missing "core\data\rates.example.json" "core\data\rates.json"
call :copy_if_missing "core\integrations\donationalerts\da_config.example.json" "core\integrations\donationalerts\da_config.json"
call :copy_if_missing "integrations\donatty\donatty_config.example.json" "integrations\donatty\donatty_config.json"
call :copy_if_missing "integrations\streamerbot\streamerbot_config.example.json" "integrations\streamerbot\streamerbot_config.json"

echo.
echo Done.
echo.
echo Now edit your local config files:
echo - core\integrations\donationalerts\da_config.json
echo - integrations\donatty\donatty_config.json
echo - integrations\streamerbot\streamerbot_config.json
echo.
pause
exit /b 0

:copy_if_missing
if not exist %2 (
  if exist %1 (
    copy %1 %2 >nul
    echo Created %2
  ) else (
    echo Missing example file: %1
  )
) else (
  echo Exists  %2
)
exit /b 0
