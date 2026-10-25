#!/usr/bin/python
# -*- coding: utf-8 -*-
#
# MyFuelScope – Import historischer Brent-Rohölpreise
#
# Holt die Brent-Spotpreisreihe DCOILBRENTEU von FRED als CSV und importiert
# gültige Beobachtungen ab START_DATE in die lokale SQLite-Datenbank.
# Fehlende Werte werden übersprungen; vorhandene Beobachtungen werden dank
# INSERT OR IGNORE nicht nochmals eingefügt.
#
# Kompatibilität: Python 2.7 auf dem Synology-NAS (DSM 6.2).

import csv
import sqlite3
import urllib2
from StringIO import StringIO
from datetime import datetime

# FRED-CSV: DCOILBRENTEU enthält den Brent-Preis in US-Dollar je Barrel.
CSV_URL = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU'
DB_PATH = '/volume1/MyFuelScope/preise.db'

# Frühestes Datum, das dieses Skript importiert. Ältere Zeilen werden ignoriert.
START_DATE = '2026-10-18'

def main():
    # Lokale Laufzeit zur Protokollierung; Beobachtungsdatum und Laufzeit sind
    # zwei unterschiedliche Zeitangaben.
    print 'Abrufzeit:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    # CSV von FRED abrufen. Bei Netzwerk- oder HTTP-Fehlern abbrechen, ohne
    # die Datenbank zu öffnen oder vorhandene Daten zu verändern.
    try:
        response = urllib2.urlopen(CSV_URL, timeout=30)
        csv_data = response.read()
        response.close()
    except Exception as e:
        print 'FEHLER beim CSV-Abruf:', str(e)
        return

    # CSV anhand der Spaltenüberschriften lesen; alle Zeilen werden danach
    # aufbereitet, bevor die Datenbankverbindung geöffnet wird.
    try:
        reader = csv.DictReader(StringIO(csv_data))
        rows = list(reader)
    except Exception as e:
        print 'FEHLER beim Lesen der CSV:', str(e)
        return

    # Beobachtungsdaten sammeln, um zu erkennen, ob die CSV überhaupt
    # Datumswerte enthält, und das neueste gelieferte Datum auszugeben.
    dates = [r.get('observation_date', '').strip()
             for r in rows
             if r.get('observation_date', '').strip()]

    if not dates:
        print 'FEHLER: Keine Beobachtungsdaten in der CSV gefunden.'
        return

    print 'Neuestes Beobachtungsdatum in CSV:', max(dates)

    # Zähler für die Laufstatistik. "eligible" zählt gültige Werte ab START_DATE,
    # nicht ausschließlich neu eingefügte Zeilen.
    conn = sqlite3.connect(DB_PATH)
    inserted = 0
    skipped = 0
    eligible = 0

    try:
        cursor = conn.cursor()

        for row in rows:
            date = row.get('observation_date', '').strip()
            price = row.get('DCOILBRENTEU', '').strip()

            # Nur Zeilen mit Datum ab START_DATE berücksichtigen.
            if not date or date < START_DATE:
                continue

            # FRED verwendet "." für fehlende Werte. Diese Werte werden nicht
            # geschätzt und nicht als 0 gespeichert.
            if not price or price == '.':
                skipped += 1
                continue

            # Datum und Preis explizit validieren, bevor SQL ausgeführt wird.
            try:
                datetime.strptime(date, '%Y-%m-%d')
                value = float(price)
            except (ValueError, TypeError):
                print 'Ungueltiger Datensatz:', date, price
                continue

            eligible += 1
            # INSERT OR IGNORE verhindert doppelte Beobachtungen, sofern ein
            # entsprechender UNIQUE-/Primärschlüssel in der Tabelle besteht.
            cursor.execute(
                'INSERT OR IGNORE INTO brent_prices '
                '(observation_date, price_usd_per_barrel) VALUES (?, ?)',
                (date, value)
            )

            # rowcount == 1 bedeutet, dass diese Zeile tatsächlich eingefügt wurde.
            if cursor.rowcount == 1:
                inserted += 1

        # Alle erfolgreichen Einfügungen gemeinsam festschreiben und Summen ausgeben.
        conn.commit()
        print 'Importierbare Datensaetze ab', START_DATE + ':', eligible
        print 'Neu eingefuegte Beobachtungen:', inserted
        print 'Fehlende Preiswerte uebersprungen:', skipped
        print 'Brent-Abruf abgeschlossen.'

    except Exception as e:
        # Bei einem Datenbankfehler alle noch nicht festgeschriebenen Änderungen
        # dieses Durchlaufs zurückrollen.
        conn.rollback()
        print 'FEHLER beim Datenbankimport:', str(e)
    finally:
        # Datenbankverbindung auch nach Fehlern zuverlässig schließen.
        conn.close()

if __name__ == '__main__':
    main()
