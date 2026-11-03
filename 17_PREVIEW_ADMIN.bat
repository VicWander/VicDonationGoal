@echo off
setlocal
cd /d "%~dp0"
set "VDG_TITLE_VERSION=dev"
if exist "%~dp0VERSION" set /p VDG_TITLE_VERSION=<"%~dp0VERSION"
title VicDonationGoal v%VDG_TITLE_VERSION% 1.5 - Safe Admin Preview
set VDG_PREVIEW=1
set VDG_PORT=3347
echo Safe admin preview: http://127.0.0.1:3347/admin.html
echo Core only. Integrations, Streamer.bot and speech are disabled.
echo Local changes are saved only in this development copy.
if exist "%~dp0runtime\python\python.exe" (
  "%~dp0runtime\python\python.exe" "%~dp0core\server.py"
) else if exist "%~dp0..\..\runtime\release_clean_python\Scripts\python.exe" (
  "%~dp0..\..\runtime\release_clean_python\Scripts\python.exe" "%~dp0core\server.py"
) else (
  py -3 "%~dp0core\server.py"
)
pause
endlocal
