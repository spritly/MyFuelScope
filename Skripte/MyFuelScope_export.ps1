# Exportiert aktuelle Preise, Tagestiefstände und Verlauf aus der lokalen MyFuelScope-API.
# Bei einem Fehler wird abgebrochen, damit keine unvollständigen Daten veröffentlicht werden.
$ErrorActionPreference = "Stop"

# Lokale API, Zielordner und erlaubte Stations-IDs für diesen Exportlauf.
$base = "http://10.0.0.2:8080"
$targetDir = "E:\MyFuelScope\UploadMegaNz"
$allowedIds = @(1126532, 1354801, 1471187, 1354682, 1354928, 35847)
$utf8NoBom = New-Object System.Text.UTF8Encoding($false)

# Ruft einen API-Endpunkt ab und weist leere Antworten zurück.
function Get-ApiJson {
    param([string]$Path)

    $uri = $base + $Path
    $response = Invoke-RestMethod -Uri $uri -Method Get -TimeoutSec 25
    if ($null -eq $response) {
        throw "Leere API-Antwort: $Path"
    }
    return $response
}

# Prüft Preise invariant zur Windows-Ländereinstellung; fehlende/ungültige Werte werden nicht ersetzt.
function Test-PositivePrice {
    param($Value, [string]$Context)

    if ($null -eq $Value) {
        throw "Fehlender Preis in $Context."
    }

    $parsed = 0.0
    if (-not [double]::TryParse(
        [string]$Value,
        [Globalization.NumberStyles]::Any,
        [Globalization.CultureInfo]::InvariantCulture,
        [ref]$parsed
    ) -or $parsed -le 0) {
        throw "Ungültiger Preis in $Context."
    }
}

# Schreibt JSON mit UTF-8 ohne BOM zunächst in eine temporäre Datei.
function Write-JsonTemp {
    param([string]$Path, $Data)

    $json = ConvertTo-Json -InputObject $Data -Depth 12
    [System.IO.File]::WriteAllText(
        $Path,
        $json + [Environment]::NewLine,
        $utf8NoBom
    )
}

try {
    # Vor dem Abruf sicherstellen, dass das konfigurierte Exportziel existiert.
    if (!(Test-Path -LiteralPath $targetDir)) {
        throw "Exportordner nicht gefunden: $targetDir"
    }

    Write-Host "=== 1/3 Aktuelle Preise abrufen ===" -ForegroundColor Cyan
    # 1) Aktuelle Stationsdaten abrufen und Anzahl, IDs, Pflichtfelder sowie Preise prüfen.
    $currentRaw = @(Get-ApiJson "/api/prices")

    if ($currentRaw.Count -ne 6) {
        throw "Aktuelle Preise: erwartet 6 Datensätze, erhalten $($currentRaw.Count)."
    }

    $current = @()
    $seenCurrent = @{}

    foreach ($item in $currentRaw) {
        $id = 0
        if (-not [int]::TryParse([string]$item.station_id, [ref]$id)) {
            throw "Ungültige station_id in den aktuellen Preisen."
        }
        if ($allowedIds -notcontains $id) {
            throw "Nicht freigegebene station_id $id in den aktuellen Preisen."
        }
        if ($seenCurrent.ContainsKey([string]$id)) {
            throw "Doppelte station_id $id in den aktuellen Preisen."
        }
        $seenCurrent[[string]$id] = $true

        foreach ($field in @("name", "address", "postal_code", "city", "captured_at")) {
            if ($item.PSObject.Properties.Name -notcontains $field) {
                throw "Pflichtfeld '$field' fehlt bei station_id $id."
            }
        }
        if ([string]::IsNullOrWhiteSpace([string]$item.name) -or
            [string]::IsNullOrWhiteSpace([string]$item.captured_at)) {
            throw "Name oder Messzeitpunkt fehlt bei station_id $id."
        }

        # Null ist bei aktuellen Preisen zulässig und bleibt null.
        if ($null -ne $item.price_eur) {
            Test-PositivePrice $item.price_eur "aktuelle Preise, station_id $id"
        }

        $current += [PSCustomObject]@{
            station_id = $id
            name       = [string]$item.name
            address    = [string]$item.address
            postal_code = [string]$item.postal_code
            city       = [string]$item.city
            captured_at = [string]$item.captured_at
            price_eur  = $item.price_eur
        }
    }

    foreach ($id in $allowedIds) {
        if (-not $seenCurrent.ContainsKey([string]$id)) {
            throw "Aktuelle Preise enthalten nicht die freigegebene station_id $id."
        }
    }

    Write-Host "=== 2/3 Tagestiefstände abrufen ===" -ForegroundColor Cyan
    # 2) Tagestiefstände prüfen. Ein nicht vorhandener Tiefstpreis bleibt null.
    $lowsRaw = @(Get-ApiJson "/api/lows")

    if ($lowsRaw.Count -ne 6) {
        throw "Tagestiefstände: erwartet 6 Datensätze, erhalten $($lowsRaw.Count)."
    }

    $lows = @()
    $seenLows = @{}

    foreach ($item in $lowsRaw) {
        $id = 0
        if (-not [int]::TryParse([string]$item.station_id, [ref]$id)) {
            throw "Ungültige station_id bei den Tagestiefständen."
        }
        if ($allowedIds -notcontains $id) {
            throw "Nicht freigegebene station_id $id bei den Tagestiefständen."
        }
        if ($seenLows.ContainsKey([string]$id)) {
            throw "Doppelte station_id $id bei den Tagestiefständen."
        }
        $seenLows[[string]$id] = $true

        # Ein Tagestiefstand darf fehlen; niemals 0 oder einen Ersatzwert erzeugen.
        if ($null -ne $item.low_price) {
            Test-PositivePrice $item.low_price "Tagestiefstand, station_id $id"
            if ([string]::IsNullOrWhiteSpace([string]$item.low_at)) {
                throw "low_at fehlt trotz vorhandenem Tiefstpreis für station_id $id."
            }
        }

        $lows += [PSCustomObject]@{
            station_id = $id
            name       = [string]$item.name
            low_price  = $item.low_price
            low_at     = $item.low_at
        }
    }

    foreach ($id in $allowedIds) {
        if (-not $seenLows.ContainsKey([string]$id)) {
            throw "Tagestiefstände enthalten nicht die freigegebene station_id $id."
        }
    }

    Write-Host "=== 3/3 Tages- und Wochenverlauf abrufen ===" -ForegroundColor Cyan
    # 3) Für jede freigegebene Station Tages- und Wochenverlauf abrufen und validieren.
    $historyStations = @()

    foreach ($id in $allowedIds) {
        $periodData = @{}

        foreach ($period in @("today", "week")) {
            $path = "/api/history?station_id=$id&period=$period"
            $history = Get-ApiJson $path

            if ([int]$history.station_id -ne $id) {
                throw "History-API lieferte für $id eine falsche station_id."
            }
            if ([string]$history.period -ne $period) {
                throw "History-API lieferte für $id einen falschen Zeitraum."
            }
            if ($history.points -isnot [System.Array]) {
                throw "History-Punkte fehlen oder sind ungültig: station_id $id, $period."
            }

            $points = @()
            foreach ($point in $history.points) {
                if ([string]::IsNullOrWhiteSpace([string]$point.captured_at)) {
                    throw "Messzeitpunkt fehlt im Verlauf von station_id $id."
                }
                Test-PositivePrice $point.price_eur "Verlauf, station_id $id, $period"

                $points += [PSCustomObject]@{
                    captured_at = [string]$point.captured_at
                    price_eur   = $point.price_eur
                }
            }

            $periodData[$period] = [PSCustomObject]@{
                label  = [string]$history.label
                start  = [string]$history.start
                end    = [string]$history.end
                count  = $points.Count
                points = $points
            }

            Write-Host "Station $id / $period : $($points.Count) Messpunkte"
        }

        $historyStations += [PSCustomObject]@{
            station_id = $id
            today      = $periodData["today"]
            week       = $periodData["week"]
        }
    }

    $historyOutput = [PSCustomObject]@{
        generated_at = (Get-Date).ToString("yyyy-MM-dd HH:mm:ss")
        stations     = $historyStations
    }

    # Erst wenn alle Datensätze geprüft sind, die drei JSON-Ausgaben vorbereiten.
    # Alle Daten wurden validiert. Zuerst drei temporäre Dateien schreiben.
    $outputs = @(
        @{
            Name = "aktuelle_preise.json"
            Data = $current
        },
        @{
            Name = "tagestiefstaende.json"
            Data = $lows
        },
        @{
            Name = "preisverlauf.json"
            Data = $historyOutput
        }
    )

    $tempFiles = @()
    foreach ($output in $outputs) {
        $temp = Join-Path $targetDir ("." + $output.Name + ".tmp")
        Write-JsonTemp -Path $temp -Data $output.Data
        $tempFiles += [PSCustomObject]@{
            Temp   = $temp
            Target = Join-Path $targetDir $output.Name
        }
    }

    # Der Austausch erfolgt erst nach erfolgreicher Erzeugung aller drei temporären Dateien.
    # Erst nach erfolgreicher Erzeugung aller drei Dateien austauschen.
    foreach ($file in $tempFiles) {
        Move-Item -LiteralPath $file.Temp -Destination $file.Target -Force
    }

    Write-Host "`nEXPORT ERFOLGREICH" -ForegroundColor Green
    Write-Host "Aktuelle Preise: $($current.Count)"
    Write-Host "Tagestiefstände: $($lows.Count)"
    Write-Host "Verlauf: $($historyStations.Count) Stationen, jeweils heute und letzte 7 Tage"
    Write-Host "Aktuelle Datensätze ohne Preis: $(@($current | Where-Object { $null -eq $_.price_eur }).Count)"
    Get-Item (Join-Path $targetDir "aktuelle_preise.json"),
             (Join-Path $targetDir "tagestiefstaende.json"),
             (Join-Path $targetDir "preisverlauf.json") |
        Select-Object Name, Length, LastWriteTime |
        Format-Table -AutoSize
}
catch {
    # Fehler sichtbar melden und einen Fehler-Exitcode liefern.
    Write-Host "`nEXPORT FEHLGESCHLAGEN: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}
finally {
    # Zurückgebliebene temporäre JSON-Dateien unabhängig vom Ausgang aufräumen.
    Get-ChildItem -LiteralPath $targetDir -Filter ".*.json.tmp" -ErrorAction SilentlyContinue |
        Remove-Item -Force -ErrorAction SilentlyContinue
}