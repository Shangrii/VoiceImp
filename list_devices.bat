@echo off
REM Show the audio devices to help configure config.json
cd /d "%~dp0"
".venv\Scripts\python.exe" list_devices.py
pause
