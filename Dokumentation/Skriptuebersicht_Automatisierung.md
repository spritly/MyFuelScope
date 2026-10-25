# MyFuelScope – Skriptübersicht und Automatisierung

Diese Seite beschreibt die Aufgaben der sieben Projektskripte, ihre Abhängigkeiten und die bekannten Zeitpläne. Sie ist eine Betriebsübersicht, kein Ersatz für die Kommentare im jeweiligen Skript.

## 1. Überblick

| Skript | Ausführungsort | Aufgabe |
|---|---|---|
| `sammle_preise.py` | Synology NAS | Ruft Benzin-95-Preise für die konfigurierten Tankstellen ab und speichert die Ergebnisse in SQLite. |
| `sammle_brent.py` | Synology NAS | Ruft die Brent-Referenzdaten aus der konfigurierten FRED-Datenquelle ab und speichert sie lokal. |
| `backup_db.sh` | Synology NAS | Erstellt eine SQLite-Sicherung und prüft sie mit `PRAGMA integrity_check`. |
| `server.py` | Synology NAS | Stellt die lokale Weboberfläche und die von den Windows-Exporten verwendeten API-Endpunkte bereit. |
| `MyFuelScope_export.ps1` | Windows-PC | Ruft die API ab, validiert Stationsdaten und erzeugt die drei JSON-Dateien. |
| `MyFuelScope_publish_github.ps1` | Windows-PC | Prüft die JSON-Dateien und veröffentlicht ausschließlich diese Dateien im lokalen Git-Repository. |
| `MyFuelScope_update_all.ps1` | Windows-PC | Startet Export und Veröffentlichung in der richtigen Reihenfolge und bricht bei einem Fehler ab. |

## 2. Datenfluss

1. **Datenerfassung auf dem NAS:** `sammle_preise.py` und `sammle_brent.py` schreiben ihre erfassten Daten in die lokale SQLite-Datenbank.
2. **Lokale Web-API:** `server.py` stellt die für die Anzeige und den Export benötigten Daten über HTTP bereit.
3. **JSON-Export unter Windows:** `MyFuelScope_export.ps1` liest die API-Endpunkte aus und validiert die Antworten. Die Ausgaben sind:
   - `aktuelle_preise.json`
   - `tagestiefstaende.json`
   - `preisverlauf.json`
4. **Veröffentlichung:** `MyFuelScope_publish_github.ps1` prüft den Git-Status, validiert die JSON-Dateien und committet/pusht nur die drei freigegebenen Datendateien.
5. **Ablaufsteuerung:** `MyFuelScope_update_all.ps1` führt Export und Veröffentlichung nacheinander aus. Scheitert der Export, wird die Veröffentlichung nicht gestartet.

**Hinweis zu Brent:** Die Brent-Daten werden lokal gesammelt und gespeichert. Nach dem zuletzt dokumentierten Projektstand sind sie noch nicht Teil der drei öffentlichen JSON-Exporte oder der statischen Preisgrafiken.

## 3. Bekannte Zeitpläne

Die folgenden Zeitpläne wurden für die Installation dokumentiert. Vor Änderungen an der produktiven Aufgabenplanung die tatsächlich aktive Konfiguration auf dem NAS bzw. im Windows-Aufgabenplaner prüfen.

| Aufgabe | Zeitplan | Bekannter Aufruf |
|---|---|---|
| Benzinpreise erfassen | Stündlich zur vollen Stunde | `/usr/bin/python /volume1/MyFuelScope/sammle_preise.py` |
| Brent-Daten erfassen | Täglich um 08:10 Uhr NAS-Zeit | `/usr/bin/python /volume1/MyFuelScope/sammle_brent.py` |
| Datenbank sichern | Täglich um 21:10 Uhr NAS-Zeit | `/volume1/MyFuelScope/backup_db.sh` |
| JSON exportieren und veröffentlichen | Stündlich in Windows, Minute :01 | `E:\\MyFuelScope\\Skripte\\MyFuelScope_update_all.ps1` |

Die früher dokumentierten NAS-Cronzeilen lauteten:

```cron
0 * * * * root /usr/bin/python /volume1/MyFuelScope/sammle_preise.py >> /volume1/MyFuelScope/sammle_preise.log 2>&1
10 8 * * * root /usr/bin/python /volume1/MyFuelScope/sammle_brent.py
10 21 * * * root /volume1/MyFuelScope/backup_db.sh
```

Diese Zeilen dienen als Referenz, nicht als Aufforderung, sie erneut einzutragen. Doppelte Zeitplaneinträge können Skripte mehrfach starten.

## 4. Wichtige Pfade und Endpunkte

### NAS

- Datenbank: `/volume1/MyFuelScope/preise.db`
- Benzin-Sammler: `/volume1/MyFuelScope/sammle_preise.py`
- Brent-Sammler: `/volume1/MyFuelScope/sammle_brent.py`
- Backup-Skript: `/volume1/MyFuelScope/backup_db.sh`
- Webserver: `/volume1/MyFuelScope/webapp/server.py`
- Lokale Weboberfläche: `http://10.0.0.2:8080/`

### Windows

- Skripte: `E:\\MyFuelScope\\Skripte`
- Git-Repository: `E:\\MyFuelScope\\Git`
- JSON-Ausgabeordner: `E:\\MyFuelScope\\UploadMegaNz`
- Geplante Aufgabe: `MyFuelScope JSON Export`

### Verwendete API-Endpunkte

- `/api/prices` – aktuelle Stationspreise
- `/api/lows` – Tagestiefstände
- `/api/history?station_id=<ID>&period=today` – Tagesverlauf
- `/api/history?station_id=<ID>&period=week` – Wochenverlauf

## 5. Datenqualität und Fehlerverhalten

- Fehlende Preise müssen als fehlend (`null`) behandelt werden; niemals durch 0 oder geschätzte Werte ersetzen.
- Die Windows-Validierung prüft erwartete Stationsanzahl, erlaubte Stations-IDs, Pflichtfelder und Preise.
- Bei ungültigen oder fehlenden Pflichtdaten soll der Export bzw. die Veröffentlichung abbrechen, statt unvollständige Daten als erfolgreich zu veröffentlichen.
- Das Backup gilt erst nach erfolgreicher SQLite-Integritätsprüfung als erfolgreich.
- Vor einem Git-Push dürfen keine unerwarteten Repository-Änderungen enthalten sein.
- Bei Änderungen an den Skripten zuerst in einem Branch arbeiten, den Diff prüfen und über einen Pull Request nach `main` übernehmen.
- Änderungen an GitHub aktualisieren weder automatisch die NAS-Dateien noch zwingend das lokale Windows-Repository. Diese Aktualisierung ist ein separater Schritt.

## 6. Wartung bei Änderungen

Wenn ein Skript, Pfad, API-Endpunkt, Datenformat oder Zeitplan geändert wird:

1. Die Kommentare im betroffenen Skript anpassen.
2. Diese Übersicht aktualisieren, falls sich Aufgabe, Datenfluss, Pfade oder Zeitplan ändern.
3. Änderungen über einen Branch und Pull Request prüfen.
4. Nach dem Merge die betroffenen Laufzeitkopien kontrolliert aktualisieren.
5. Anschließend den betroffenen Ablauf testen und Logs bzw. erzeugte Dateien prüfen.

## 7. Technische Rahmenbedingungen

Die NAS-Installation verwendet eine Synology DS413j mit DSM 6.2 und Python 2.7. Docker steht auf diesem NAS nicht zur Verfügung. Änderungen an NAS-Skripten müssen daher weiterhin mit der vorhandenen Python- und Shell-Umgebung kompatibel sein.
