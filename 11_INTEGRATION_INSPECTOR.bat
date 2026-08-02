@echo off
chcp 65001 >nul
cd /d "%~dp0"
python tools\integration_inspector.py
pause
