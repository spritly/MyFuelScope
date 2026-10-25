# Validiert die drei vorbereiteten JSON-Dateien und veröffentlicht ausschließlich diese Dateien via Git.
# Unerwartete Repository-Änderungen führen zum Abbruch, damit nichts Fremdes committet wird.
$ErrorActionPreference = "Stop"

# Quellordner der Exporte und lokaler Klon des GitHub-Pages-Repositories.
$sourceDir = "E:\MyFuelScope\UploadMegaNz"
$repo = "E:\MyFuelScope\Git"
$files = @(
    "aktuelle_preise.json",
    "tagestiefstaende.json",
    "preisverlauf.json"
)
$tempFiles = @()

# Führt Git im Projektverzeichnis aus und bricht bei jedem Fehler ab.
function Run-Git {
    param([string[]]$GitArgs)
    & git -C $repo @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "Git-Befehl fehlgeschlagen: git $($GitArgs -join ' ') (Exitcode $LASTEXITCODE)"
    }
}

try {
    # Vor jedem Export sicherstellen, dass kein lokaler Arbeitsstand überschrieben wird.
    Write-Host "=== Repository-Status prüfen ==="
    $status = @(& git -C $repo status --porcelain)
    if ($LASTEXITCODE -ne 0) {
        throw "Git-Status konnte nicht gelesen werden."
    }
    if ($status.Count -gt 0) {
        throw "Das Repository enthält lokale Änderungen. Veröffentlichung abgebrochen, damit nichts überschrieben wird: $($status -join [Environment]::NewLine)"
    }

    # Neuere GitHub-Commits übernehmen, bevor JSON-Dateien geändert oder committet werden.
    Write-Host "=== Aktuellen GitHub-Stand abrufen ==="
    Run-Git @("fetch", "origin")
    try {
        Run-Git @("pull", "--rebase", "origin", "main")
    }
    catch {
        # Falls ein Rebase-Konflikt auftritt, keinen unvollständigen Rebase zurücklassen.
        & git -C $repo rebase --abort 2>$null | Out-Null
        throw "GitHub-Änderungen konnten nicht konfliktfrei integriert werden. Rebase wurde abgebrochen. Details: $($_.Exception.Message)"
    }

    $status = @(& git -C $repo status --porcelain)
    if ($LASTEXITCODE -ne 0) {
        throw "Git-Status konnte nach dem Aktualisieren nicht gelesen werden."
    }
    if ($status.Count -gt 0) {
        throw "Das Repository ist nach dem Aktualisieren nicht sauber. Veröffentlichung abgebrochen: $($status -join [Environment]::NewLine)"
    }

    # Jede Quelldatei wird vor dem Kopieren anhand ihrer erwarteten Struktur validiert.
    Write-Host "=== Drei JSON-Dateien validieren und übernehmen ==="
    foreach ($name in $files) {
        $source = Join-Path $sourceDir $name
        $target = Join-Path $repo $name
        $temp = "$target.tmp"

        if (!(Test-Path -LiteralPath $source)) {
            throw "Quelldatei fehlt: $source"
        }

        $json = Get-Content -LiteralPath $source -Raw -Encoding UTF8 | ConvertFrom-Json

        switch ($name) {
            "aktuelle_preise.json" {
                if ($json -isnot [System.Array] -or $json.Count -ne 6) {
                    throw "$name muss genau sechs Tankstellen enthalten."
                }
                foreach ($s in $json) {
                    if ($null -eq $s.station_id -or $null -eq $s.name -or $null -eq $s.captured_at) {
                        throw "Pflichtfeld fehlt in $name."
                    }
                    if ($null -ne $s.price_eur -and [double]$s.price_eur -le 0) {
                        throw "Ungültiger Preis in $name bei $($s.name)."
                    }
                }
            }
            "tagestiefstaende.json" {
                if ($json -isnot [System.Array] -or $json.Count -ne 6) {
                    throw "$name muss genau sechs Tankstellen enthalten."
                }
                foreach ($s in $json) {
                    if ($null -eq $s.station_id -or $null -eq $s.name) {
                        throw "Pflichtfeld fehlt in $name."
                    }
                    if ($null -ne $s.low_price -and [double]$s.low_price -le 0) {
                        throw "Ungültiger Tagestiefstpreis in $name bei $($s.name)."
                    }
                }
            }
            "preisverlauf.json" {
                if ($null -eq $json.generated_at -or $json.stations.Count -ne 6) {
                    throw "$name muss generated_at und genau sechs Stationen enthalten."
                }
                foreach ($s in $json.stations) {
                    if ($null -eq $s.station_id -or $null -eq $s.today -or $null -eq $s.week) {
                        throw "Unvollständiger Verlauf in $name."
                    }
                }
            }
        }

        # Unveränderte Bytes kopieren; keine JSON-Neuserialisierung.
        Copy-Item -LiteralPath $source -Destination $temp -Force
        Move-Item -LiteralPath $temp -Destination $target -Force
        $tempFiles += $temp

        Write-Host "OK: $name" -ForegroundColor Green
    }

    $status = @(& git -C $repo status --porcelain)
    if ($LASTEXITCODE -ne 0) {
        throw "Git-Status konnte nicht gelesen werden."
    }

    $otherChanges = @($status | Where-Object {
        $_.Length -ge 4 -and $_.Substring(3) -notin $files
    })
    if ($otherChanges.Count -gt 0) {
        throw "Andere Änderungen im Repository gefunden. Veröffentlichung abgebrochen: $($otherChanges -join [Environment]::NewLine)"
    }

    # Nur die explizit freigegebenen JSON-Dateien für den Commit vormerken.
    Run-Git (@("add", "--") + $files)

    $staged = @(& git -C $repo diff --cached --name-only)
    if ($LASTEXITCODE -ne 0) {
        throw "Gestagte Änderungen konnten nicht geprüft werden."
    }
    $staged = @($staged | Where-Object { $_ })

    if ($staged.Count -eq 0) {
        Write-Host "Keine Änderungen an den drei JSON-Dateien; kein Commit nötig."
        exit 0
    }

    $unexpected = @($staged | Where-Object { $_ -notin $files })
    if ($unexpected.Count -gt 0) {
        throw "Sicherheitsprüfung: Unerwartete Dateien vorgemerkt: $($unexpected -join ', ')"
    }

    # Commit und Push erfolgen nur, wenn die gestagten Änderungen ausschließlich erlaubte Dateien betreffen.
    Run-Git @("commit", "-m", "Update fuel price data")
    Run-Git @("push", "origin", "main")

    Write-Host "VERÖFFENTLICHUNG ERFOLGREICH: Alle drei JSON-Dateien übertragen." -ForegroundColor Green
}
catch {
    # Veröffentlichungsfehler ausgeben und dem Task Scheduler als Fehler signalisieren.
    Write-Host "VERÖFFENTLICHUNG FEHLGESCHLAGEN: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    # Temporäre Kopien bei Erfolg oder Fehler entfernen.
    foreach ($temp in $tempFiles) {
        if (Test-Path -LiteralPath $temp) {
            Remove-Item -LiteralPath $temp -Force -ErrorAction SilentlyContinue
        }
    }
}
