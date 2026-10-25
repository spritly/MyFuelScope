#!/bin/sh

DB="/volume1/MyFuelScope/preise.db"
BACKUP="/volume1/MyFuelScope/backups/preise.db"
LOG="/volume1/MyFuelScope/backups/backup.log"

echo "[$(/bin/date '+%Y-%m-%d %H:%M:%S')] BACKUP START" >> "$LOG"

if /usr/bin/sqlite3 "$DB" ".backup '$BACKUP'" >> "$LOG" 2>&1; then
    CHECK=$(/usr/bin/sqlite3 "$BACKUP" "PRAGMA integrity_check;" 2>&1)
    RC=$?

    if [ "$RC" -eq 0 ] && [ "$CHECK" = "ok" ]; then
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
