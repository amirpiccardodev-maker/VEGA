@echo off
REM ================================================================
REM  VEGA - Setup automatico per nuovo PC
REM  Esegui questo file una sola volta dopo aver copiato la cartella.
REM ================================================================
setlocal ENABLEDELAYEDEXPANSION
cd /d "%~dp0"

echo.
echo  ============================================================
echo   V.E.G.A. - INSTALLAZIONE
echo  ============================================================
echo.

REM --- 1. Verifica Python ---
echo [1/5] Verifico Python...
where python >nul 2>nul
if errorlevel 1 (
    echo [ERRORE] Python non trovato!
    echo Installa Python 3.12 o piu' nuovo da https://python.org
    echo IMPORTANTE: durante l'install seleziona "Add to PATH"
    pause
    exit /b 1
)
python --version
echo OK.
echo.

REM --- 2. Crea ambiente virtuale ---
echo [2/5] Creo ambiente virtuale Python...
if exist "venv\Scripts\python.exe" (
    echo Ambiente venv esistente trovato, lo riuso.
) else (
    python -m venv venv
    if errorlevel 1 (
        echo [ERRORE] Impossibile creare venv.
        pause
        exit /b 1
    )
    echo Ambiente venv creato.
)
echo.

REM --- 3. Installa dipendenze ---
echo [3/5] Installo le dipendenze Python (puo' richiedere 5-10 min la prima volta)...
"%~dp0venv\Scripts\python.exe" -m pip install --upgrade pip --quiet
"%~dp0venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERRORE] Installazione dipendenze fallita.
    pause
    exit /b 1
)
echo Dipendenze installate.
echo.

REM --- 4. Genera icona ---
echo [4/5] Genero icona Vega...
"%~dp0venv\Scripts\python.exe" generate_icon.py >nul 2>nul
echo Icona generata.
echo.

REM --- 5. Crea shortcut desktop + autostart ---
echo [5/5] Creo shortcut desktop e attivo avvio automatico...
powershell -ExecutionPolicy Bypass -File "%~dp0install_shortcuts.ps1" -Autostart
echo.

echo  ============================================================
echo   INSTALLAZIONE COMPLETATA
echo  ============================================================
echo.
echo Per avviare Vega:
echo   - Doppio click sull'icona "Vega" sul desktop
echo   - Oppure attendi il prossimo login Windows (autostart attivo)
echo.
echo Primo avvio: scaricamento modelli AI (~250MB, una sola volta).
echo Successivi avvii: 10-15 secondi.
echo.
echo Verifica nel file .env di avere:
echo   ANTHROPIC_API_KEY  (la tua chiave Claude API)
echo   GMAIL_ADDRESS      (per leggere email)
echo   GMAIL_APP_PASSWORD (app password Gmail)
echo.
pause
