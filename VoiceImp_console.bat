@echo off
REM Launch VoiceImp in console mode (no graphical interface).
cd /d "%~dp0"
".venv\Scripts\python.exe" app.py
pause
