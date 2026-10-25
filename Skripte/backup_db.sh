#!/bin/sh

# Erstellt ein konsistentes SQLite-Backup und prüft danach dessen Integrität.
# Fehler werden protokolliert und mit Exitcode 1 an den Aufrufer gemeldet.
DB="/volume1/MyFuelScope/preise.db"
BACKUP="/volume1/MyFuelScope/backups/preise.db"
LOG="/volume1/MyFuelScope/backups/backup.log"

# Startzeit im Log festhalten; Ausgaben von SQLite werden ebenfalls dort gesammelt.
echo "[$(/bin/date '+%Y-%m-%d %H:%M:%S')] BACKUP START" >> "$LOG"

if /usr/bin/sqlite3 "$DB" ".backup '$BACKUP'" >> "$LOG" 2>&1; then
    # Ein erfolgreiches .backup allein reicht nicht: die Sicherung wird zusätzlich geprüft.
    CHECK=$(/usr/bin/sqlite3 "$BACKUP" "PRAGMA integrity_check;" 2>&1)
    RC=$?

    if [ "$RC" -eq 0 ] && [ "$CHECK" = "ok" ]; then
        # Nur bei Exitcode 0 und exakt "ok" gilt das Backup als erfolgreich.
        SIZE=$(/usr/bin/stat -c '%s' "$BACKUP")
        echo "[$(/bin/date '+%Y-%m-%d %H:%M:%S')] ERFOLG: Integritätsprüfung ok; Dateigröße ${SIZE} Bytes" >> "$LOG"
    else
        echo "[$(/bin/date '+%Y-%m-%d %H:%M:%S')] FEHLER: Integritätsprüfung fehlgeschlagen: $CHECK" >> "$LOG"
        exit 1
    fi
else
    echo "[$(/bin/date '+%Y-%m-%d %H:%M:%S')] FEHLER: SQLite-Backup fehlgeschlagen" >> "$LOG"
    exit 1
fi
