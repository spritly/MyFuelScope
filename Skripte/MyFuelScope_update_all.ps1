$ErrorActionPreference = "Stop"

$powerShellExe = Join-Path $PSHOME "powershell.exe"
$exportScript = "E:\MyFuelScope\Skripte\MyFuelScope_export.ps1"
$publishScript = "E:\MyFuelScope\Skripte\MyFuelScope_publish_github.ps1"

foreach ($script in @($exportScript, $publishScript)) {
    Write-Host "`n=== Starte: $script ==="

    & $powerShellExe -NoProfile -ExecutionPolicy Bypass -File $script
    $result = $LASTEXITCODE

    if ($result -ne 0) {
        Write-Host "FEHLER: $script endete mit Exitcode $result" -ForegroundColor Red
        exit $result
    }
}

Write-Host "`nGESAMTABLAUF ERFOLGREICH: Export und GitHub-Veröffentlichung beendet." -ForegroundColor Green
exit 0
