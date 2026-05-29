@echo off
REM ============================================
REM PUSH VEGA TO GITHUB — script one-shot
REM ============================================
REM
REM PREREQUISITI:
REM 1. Hai creato la repo su https://github.com/new (NON inizializzarla)
REM    Nome: vega (o quello che vuoi)
REM 2. Hai copiato l'URL HTTPS (es. https://github.com/amirpiccardo/vega.git)
REM
REM USO: doppio click su questo file, oppure da terminale: push_to_github.bat
REM ============================================

setlocal
cd /d "%~dp0"

echo.
echo ========================================
echo  PUSH VEGA SU GITHUB
echo ========================================
echo.

REM Verifica git
git --version >nul 2>&1
if errorlevel 1 (
    echo [ERRORE] Git non e' installato.
    echo Scarica da: https://git-scm.com/download/win
    pause
    exit /b 1
)

REM Verifica che siamo in repo git
git rev-parse --git-dir >nul 2>&1
if errorlevel 1 (
    echo [ERRORE] Questa cartella non e' un repository git.
    pause
    exit /b 1
)

REM Mostra commits pendenti
echo.
echo Commits pronti da pushare:
git log --oneline -5
echo.

REM Chiedi URL GitHub
set /p REPO_URL="Incolla qui l'URL HTTPS della tua repo GitHub (es. https://github.com/amirpiccardo/vega.git): "

if "%REPO_URL%"=="" (
    echo [ERRORE] URL vuoto. Annullato.
    pause
    exit /b 1
)

REM Configura remote (rimuovi se esiste e ri-aggiungi)
git remote remove origin 2>nul
git remote add origin "%REPO_URL%"
echo.
echo Remote 'origin' configurato:
git remote -v
echo.

REM Imposta main come branch default
git branch -M main

REM Verifica file sensibili (sicurezza finale)
echo.
echo Verifica file sensibili non tracciati...
git ls-files | findstr /I ".env memory.json tasks.db memory_graph.db auth.json canaries.json" >nul
if not errorlevel 1 (
    echo.
    echo [ATTENZIONE] Alcuni file sensibili sembrano tracciati! Verifica .gitignore.
    echo.
    git ls-files | findstr /I ".env memory.json tasks.db memory_graph.db auth.json canaries.json"
    echo.
    set /p CONFIRM="Continuare comunque? (s/n): "
    if /i not "%CONFIRM%"=="s" exit /b 1
)

REM Push
echo.
echo ========================================
echo  PUSH IN CORSO...
echo ========================================
echo.
echo Se ti chiede credenziali:
echo  - apparira' un popup browser per autenticare via GitHub
echo  - clicca "Authorize" e ritorna qui
echo.

git push -u origin main

if errorlevel 1 (
    echo.
    echo ========================================
    echo  PUSH FALLITO
    echo ========================================
    echo Possibili motivi:
    echo  - Auth fallita (riprova: 'git push' rimuove cache credenziali)
    echo  - Repo non esiste su GitHub (creala su https://github.com/new)
    echo  - URL sbagliato (verifica con: git remote -v)
    echo.
    pause
    exit /b 1
)

echo.
echo ========================================
echo  PUSH COMPLETATO!
echo ========================================
echo.
echo Vai a: %REPO_URL:.git=%
echo.
echo Prossimi step opzionali:
echo  - Aggiungi topics su GitHub (ai, assistant, gdpr, nis2, italian, ...)
echo  - Crea release v1.0
echo  - Abilita Issues e Discussions
echo.
pause
