@echo off
cd /d "%~dp0"
title VicDonationGoal - Create Local Configs

echo ==============================================
echo  Creating local config/data files if missing
echo ==============================================
echo.

if not exist "core\data" mkdir "core\data"
if not exist "integrations\donationalerts" mkdir "integrations\donationalerts"
if not exist "integrations\donatty" mkdir "integrations\donatty"
if not exist "integrations\donatepay" mkdir "integrations\donatepay"
if not exist "integrations\donatestream" mkdir "integrations\donatestream"
if not exist "integrations\donatex" mkdir "integrations\donatex"
if not exist "integrations\streamerbot" mkdir "integrations\streamerbot"
if not exist "integrations\streamelements" mkdir "integrations\streamelements"
if not exist "integrations\streamlabs" mkdir "integrations\streamlabs"
if not exist "integrations\tribute" mkdir "integrations\tribute"
if not exist "integrations\tts" mkdir "integrations\tts"

call :copy_if_missing "core\data\state.example.json" "core\data\state.json"
call :copy_if_missing "core\data\donations.example.json" "core\data\donations.json"
call :copy_if_missing "core\data\rates.example.json" "core\data\rates.json"
call :copy_if_missing "core\data\donor_profiles.example.json" "core\data\donor_profiles.json"
call :copy_if_missing "core\data\donor_adjustments.example.json" "core\data\donor_adjustments.json"
call :copy_if_missing "integrations\donationalerts\donationalerts_config.example.json" "integrations\donationalerts\donationalerts_config.json"
call :copy_if_missing "integrations\integrations_onboarding.example.json" "integrations\integrations_onboarding.json"
call :copy_if_missing "integrations\donatty\donatty_config.example.json" "integrations\donatty\donatty_config.json"
call :copy_if_missing "integrations\donatepay\donatepay_config.example.json" "integrations\donatepay\donatepay_config.json"
call :copy_if_missing "integrations\donatestream\donatestream_config.example.json" "integrations\donatestream\donatestream_config.json"
call :copy_if_missing "integrations\donatex\donatex_config.example.json" "integrations\donatex\donatex_config.json"
call :copy_if_missing "integrations\streamelements\streamelements_config.example.json" "integrations\streamelements\streamelements_config.json"
call :copy_if_missing "integrations\streamlabs\streamlabs_config.example.json" "integrations\streamlabs\streamlabs_config.json"
call :copy_if_missing "integrations\tribute\tribute_config.example.json" "integrations\tribute\tribute_config.json"
call :copy_if_missing "integrations\streamerbot\streamerbot_config.example.json" "integrations\streamerbot\streamerbot_config.json"
call :copy_if_missing "integrations\streamerbot\donation_event_rules.example.json" "integrations\streamerbot\donation_event_rules.json"
call :copy_if_missing "integrations\tts\tts_config.example.json" "integrations\tts\tts_config.json"
call :copy_if_missing "integrations\tts\tts_profiles.example.json" "integrations\tts\tts_profiles.json"
call :copy_if_missing "integrations\tts\tts_rules.example.json" "integrations\tts\tts_rules.json"

echo.
echo Done.
echo.
echo Now edit your local config files:
echo - integrations\donationalerts\donationalerts_config.json
echo - integrations\donatty\donatty_config.json
echo - integrations\donatepay\donatepay_config.json
echo - integrations\donatestream\donatestream_config.json
echo - integrations\donatex\donatex_config.json
echo - integrations\streamelements\streamelements_config.json
echo - integrations\streamlabs\streamlabs_config.json
echo - integrations\tribute\tribute_config.json
echo - integrations\streamerbot\streamerbot_config.json
echo - integrations\streamerbot\donation_event_rules.json
echo - integrations\tts\tts_config.json
echo - integrations\tts\tts_profiles.json
echo - integrations\tts\tts_rules.json
echo.
if /I "%~1"=="--quiet" goto :done
pause

:done
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
