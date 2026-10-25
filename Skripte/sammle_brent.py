#!/usr/bin/python
# -*- coding: utf-8 -*-

import csv
import sqlite3
import urllib2
from StringIO import StringIO
from datetime import datetime

CSV_URL = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id=DCOILBRENTEU'
DB_PATH = '/volume1/MyFuelScope/preise.db'
START_DATE = '2026-10-18'

def main():
    print 'Abrufzeit:', datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    try:
        response = urllib2.urlopen(CSV_URL, timeout=30)
        csv_data = response.read()
        response.close()
    except Exception as e:
        print 'FEHLER beim CSV-Abruf:', str(e)
        return

    try:
        reader = csv.DictReader(StringIO(csv_data))
        rows = list(reader)
    except Exception as e:
        print 'FEHLER beim Lesen der CSV:', str(e)
        return

    dates = [r.get('observation_date', '').strip()
             for r in rows
             if r.get('observation_date', '').strip()]

    if not dates:
        print 'FEHLER: Keine Beobachtungsdaten in der CSV gefunden.'
        return

    print 'Neuestes Beobachtungsdatum in CSV:', max(dates)

    conn = sqlite3.connect(DB_PATH)
    inserted = 0
    skipped = 0
    eligible = 0

    try:
        cursor = conn.cursor()

        for row in rows:
            date = row.get('observation_date', '').strip()
            price = row.get('DCOILBRENTEU', '').strip()

            if not date or date < START_DATE:
                continue

            if not price or price == '.':
                skipped += 1
                continue

            try:
                datetime.strptime(date, '%Y-%m-%d')
                value = float(price)
            except (ValueError, TypeError):
                print 'Ungueltiger Datensatz:', date, price
                continue

            eligible += 1
            cursor.execute(
                'INSERT OR IGNORE INTO brent_prices '
                '(observation_date, price_usd_per_barrel) VALUES (?, ?)',
                (date, value)
            )

            if cursor.rowcount == 1:
                inserted += 1

        conn.commit()
        print 'Importierbare Datensaetze ab', START_DATE + ':', eligible
        print 'Neu eingefuegte Beobachtungen:', inserted
        print 'Fehlende Preiswerte uebersprungen:', skipped
        print 'Brent-Abruf abgeschlossen.'

    except Exception as e:
        conn.rollback()
        print 'FEHLER beim Datenbankimport:', str(e)
    finally:
        conn.close()

if __name__ == '__main__':
    main()
