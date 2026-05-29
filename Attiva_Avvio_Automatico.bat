@echo off
REM Doppio click su questo file per attivare l'avvio automatico al login Windows.
powershell -ExecutionPolicy Bypass -File "%~dp0install_shortcuts.ps1" -Autostart
echo.
echo Premi un tasto per chiudere...
pause >nul
