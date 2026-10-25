# Gesamtsteuerung für den geplanten Windows-Auftrag: erst Export, dann GitHub-Veröffentlichung.
# Bei einem Fehler wird der zweite Schritt nicht mehr gestartet.
$ErrorActionPreference = "Stop"

# Pfade zu PowerShell und den beiden nacheinander ausgeführten Skripten.
$powerShellExe = Join-Path $PSHOME "powershell.exe"
$exportScript = "E:\MyFuelScope\Skripte\MyFuelScope_export.ps1"
$publishScript = "E:\MyFuelScope\Skripte\MyFuelScope_publish_github.ps1"

# Beide Teilskripte in definierter Reihenfolge mit einem frischen PowerShell-Prozess starten.
foreach ($script in @($exportScript, $publishScript)) {
    Write-Host "`n=== Starte: $script ==="

    # NoProfile macht den Lauf unabhängig von persönlichen Profilen; der Exitcode steuert den Ablauf.
    & $powerShellExe -NoProfile -ExecutionPolicy Bypass -File $script
    $result = $LASTEXITCODE

    if ($result -ne 0) {
        Write-Host "FEHLER: $script endete mit Exitcode $result" -ForegroundColor Red
        exit $result
    }
}

# Erfolg nur melden, wenn Export und Veröffentlichung beide ohne Fehler beendet wurden.
Write-Host "`nGESAMTABLAUF ERFOLGREICH: Export und GitHub-Veröffentlichung beendet." -ForegroundColor Green
exit 0
