@echo off
REM Launch the VoiceImp graphical interface.
cd /d "%~dp0"
start "" ".venv\Scripts\pythonw.exe" gui.py
