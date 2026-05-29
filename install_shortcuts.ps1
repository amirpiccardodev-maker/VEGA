# Crea shortcut desktop + opzione autostart per Vega (portable)
# Usa $PSScriptRoot per trovare la cartella Vega automaticamente.
param(
    [switch]$Autostart
)

$ErrorActionPreference = "Stop"

# Cartella in cui si trova questo script
$vegaRoot = $PSScriptRoot
if (-not $vegaRoot) {
    $vegaRoot = Split-Path -Parent $MyInvocation.MyCommand.Definition
}

$vbsPath = Join-Path $vegaRoot "Vega.vbs"
$iconPath = Join-Path $vegaRoot "assets\vega.ico"

if (-not (Test-Path $vbsPath)) {
    Write-Host "[ERRORE] Vega.vbs non trovato in $vegaRoot" -ForegroundColor Red
    exit 1
}

$desktop = [Environment]::GetFolderPath("Desktop")
$lnkDesktop = Join-Path $desktop "Vega.lnk"

$wsh = New-Object -ComObject WScript.Shell
$sc = $wsh.CreateShortcut($lnkDesktop)
$sc.TargetPath = $vbsPath
$sc.WorkingDirectory = $vegaRoot
$sc.Description = "Vega - Assistente Personale"
$sc.WindowStyle = 1
if (Test-Path $iconPath) { $sc.IconLocation = $iconPath }
$sc.Save()
Write-Host "[OK] Shortcut creato sul desktop: $lnkDesktop" -ForegroundColor Green

if ($Autostart) {
    $startup = [Environment]::GetFolderPath("Startup")
    $lnkStartup = Join-Path $startup "Vega.lnk"
    $sc2 = $wsh.CreateShortcut($lnkStartup)
    $sc2.TargetPath = $vbsPath
    $sc2.WorkingDirectory = $vegaRoot
    $sc2.Description = "Vega - Avvio Automatico"
    if (Test-Path $iconPath) { $sc2.IconLocation = $iconPath }
    $sc2.Save()
    Write-Host "[OK] Autostart attivato: $lnkStartup" -ForegroundColor Green
} else {
    Write-Host "[INFO] Per attivare avvio automatico al login esegui:" -ForegroundColor Yellow
    Write-Host "       powershell -ExecutionPolicy Bypass -File install_shortcuts.ps1 -Autostart" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "Puoi avviare Vega con:" -ForegroundColor Cyan
Write-Host "  - Doppio click sull'icona del desktop"
Write-Host "  - Vega.vbs (senza finestra console)"
Write-Host "  - Vega.bat (con console, utile per debug)"
