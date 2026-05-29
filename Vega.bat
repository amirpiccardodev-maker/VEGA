@echo off
REM Launcher con console visibile (per debug). Per uso normale usa Vega.vbs
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" -X utf8 "%~dp0server.py"
