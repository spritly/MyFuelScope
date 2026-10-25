#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# MyFuelScope – Erfassung der aktuellen Benzin-95-Preise
#
# Ruft für jede konfigurierte Tankstelle den Preis über die jeweilige
# Datenquelle ab und speichert erfolgreiche Abrufe in der SQLite-Datenbank.
# Jeder Abruf – auch ein fehlgeschlagener – wird in fetch_log protokolliert.
# Ein fehlender Preis wird nicht durch einen Schätzwert oder 0 ersetzt.
#
# Kompatibilität: Python 2.7 auf dem Synology-NAS (DSM 6.2).

import os
import re
import json
import sqlite3
import subprocess
from datetime import datetime
from HTMLParser import HTMLParser

# Gemeinsamer Projektpfad, Datenbankdatei und temporäre Download-Dateien.
BASE = '/volume1/MyFuelScope'
DB = os.path.join(BASE, 'preise.db')
TMP = '/tmp'

# Tankstellen-Konfiguration: (E-Control-ID, Anzeigename, Abrufverfahren).
# Die Kennung bestimmt, welche Funktion den Preis aus der Quelle liest.
STATIONS = [
    (35847, 'BP Frohsdorf', 'bp'),
    (1471187, 'Turmoel Quick Guenser Strasse', 'econtrol'),
    (1354682, 'JET Guenser Strasse 92', 'jet_guenser'),
    (1126532, 'Avanti Neunkirchner Strasse 118', 'econtrol'),
    (1354928, 'JET Puchberger Strasse 1', 'jet_puchberger'),
    (1354801, 'Avanti Puchberger Strasse 44', 'econtrol')
]

# Koordinaten, mit denen E-Control die passende Tankstelle finden kann.
# Die Rückgabe wird zusätzlich anhand der Tankstellen-ID geprüft.
COORDS = {
    1471187: (47.80411, 16.242),
    1126532: (47.78134, 16.19135),
    1354801: (47.8065, 16.20603)
}

# Direkte Quellen für BP und die beiden JET-Webseiten.
# E-Control-URLs werden in get_econtrol() aus den Koordinaten aufgebaut.
URLS = {
    'bp': 'https://bpretaillocator.geoapp.me/api/v2/locations/AT-410?locale=de_AT&format=json',
    'jet_guenser': 'https://www.jet-austria.at/tankstellen/wiener-neustadt/guenserstrasse-92',
    'jet_puchberger': 'https://www.jet-austria.at/tankstellen/wiener-neustadt/puchberger-strasse-1'
}

def download(url, filename):
    """Lädt eine URL mit wget herunter und liefert den Dateiinhalt zurück."""
    # -4 erzwingt IPv4; -q unterdrückt wget-Ausgaben, -O legt die Zieldatei fest.
    rc = subprocess.call(['wget', '-4', '-q', '-O', filename, url])
    # Leere oder fehlende Dateien dürfen nicht als gültige Antwort weiterlaufen.
    if rc != 0 or not os.path.isfile(filename) or os.path.getsize(filename) == 0:
        raise Exception('Download fehlgeschlagen: ' + url)
    f = open(filename, 'rb')
    try:
        return f.read()
    finally:
        f.close()

def number_from_text(text):
    """Liest einen Preis im Format mit drei Nachkommastellen aus Text/HTML."""
    # HTML-Entities (z. B. &euro;) vor der Suche in Textzeichen umwandeln.
    text = HTMLParser().unescape(text)
    m = re.search(r'([0-9]+,[0-9]{3})', text)
    if not m:
        raise Exception('Preis nicht gefunden')
    # Österreichische Dezimalkommas in einen Python-fähigen Dezimalpunkt umwandeln.
    return float(m.group(1).replace(',', '.'))

def get_bp():
    """Liest den Eurosuper-Preis und den vom BP-Dienst gemeldeten Zeitstempel."""
    raw = download(URLS['bp'], TMP + '/preisstatistik_bp.json')
    data = json.loads(raw)
    pricing = data.get('fuel_pricing', {})
    price_text = pricing.get('prices', {}).get('Eurosuper')
    if not price_text:
        raise Exception('BP: kein Eurosuper-Preis')
    price = number_from_text(price_text)
    updated = pricing.get('last_update', 'unbekannt')
    return price, updated

def get_jet(kind):
    """Liest Super 95 und den Zeitstempel aus der jeweiligen JET-HTML-Seite."""
    raw = download(URLS[kind], TMP + '/preisstatistik_' + kind + '.html')
    # Der Preis steht im HTML-Element mit der ID product_price_fuel_super.
    m = re.search(
        r'id="product_price_fuel_super"[^>]*>(.*?)</div>',
        raw, re.S)
    if not m:
        raise Exception('JET: Superpreis-Feld nicht gefunden')
    price = number_from_text(re.sub(r'<[^>]+>', '', m.group(1)))

    # Der Zeitstempel kann fehlen; in diesem Fall bleibt der Preisabruf möglich,
    # der Zeitstempel wird aber ausdrücklich als unbekannt gekennzeichnet.
    t = re.search(
        r'id="product_price_timestamp_fuel">(.*?)</span>',
        raw, re.S)
    updated = HTMLParser().unescape(t.group(1)) if t else 'unbekannt'
    return price, updated

def get_econtrol(station_id):
    """Fragt E-Control ab und sucht die Tankstelle über ihre ID in der Antwort."""
    lat, lon = COORDS[station_id]
    url = (
        'https://api.e-control.at/sprit/1.0/search/gas-stations/by-address'
        '?fuelType=SUP&includeClosed=false&latitude=%s&longitude=%s'
        % (lat, lon))
    raw = download(url, TMP + '/preisstatistik_econtrol_%s.json' % station_id)
    data = json.loads(raw)
    # Die API liefert mehrere Tankstellen im Suchgebiet; nur die exakte ID gilt.
    for station in data:
        if int(station.get('id', -1)) == station_id:
            for p in station.get('prices', []):
                if p.get('fuelType') == 'SUP' and p.get('amount') is not None:
                    # E-Control stellt in dieser Antwort keinen Anbieter-Zeitstempel bereit.
                    return float(p['amount']), 'vom Anbieter nicht ausgewiesen'
            raise Exception('E-Control: Tankstelle gefunden, aber kein SUP-Preis')
    raise Exception('E-Control: Tankstellen-ID nicht in Antwort enthalten')

def main():
    # Ein gemeinsamer Erfassungszeitpunkt ordnet alle Stationsergebnisse dieses
    # Durchlaufs derselben Messung zu; er ist nicht zwingend der Anbieter-Zeitpunkt.
    fetched_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    con = sqlite3.connect(DB)
    cur = con.cursor()
    success = 0
    failures = 0

    try:
        for station_id, name, source in STATIONS:
            try:
                # Je nach Konfiguration die passende Datenquellen-Funktion wählen.
                if source == 'bp':
                    price, updated = get_bp()
                elif source.startswith('jet_'):
                    price, updated = get_jet(source)
                else:
                    price, updated = get_econtrol(station_id)

                # Nur ein erfolgreich gelesener Preis wird in fuel_prices gespeichert.
                # INSERT OR REPLACE verhindert doppelte Datensätze für denselben
                # Schlüssel, sofern die Datenbanktabelle diesen entsprechend definiert.
                cur.execute(
                    'INSERT OR REPLACE INTO fuel_prices '
                    '(captured_at, station_id, fuel_type, price_eur) '
                    'VALUES (?, ?, ?, ?)',
                    (fetched_at, station_id, 'SUP', price))

                # Erfolgreichen Abruf mit Preis und Quell-Zeitstempel nachvollziehbar loggen.
                details = 'station_id=%s; name=%s; price_eur=%.3f; provider_time=%s' % (
                    station_id, name, price, updated)
                cur.execute(
                    'INSERT INTO fetch_log (fetched_at, source, status, details) '
                    'VALUES (?, ?, ?, ?)',
                    (fetched_at, source, 'OK', details))
                print '%s: %.3f EUR/l; Preisstand: %s' % (name, price, updated)
                success += 1

            except Exception as e:
                # Fehler pro Tankstelle werden protokolliert; die übrigen Stationen
                # werden weiter verarbeitet. Es wird kein Ersatzpreis eingetragen.
                details = "station_id=%s; name=%s; Fehler=%s" % (station_id, name, str(e))
                cur.execute(
                    "INSERT INTO fetch_log (fetched_at, source, status, details) VALUES (?, ?, ?, ?)",
                    (fetched_at, source, "ERROR", details))
                print "%s: FEHLER: %s" % (name, str(e))
                failures += 1

        # Preise und Abrufprotokolle dieses Durchlaufs gemeinsam speichern.
        con.commit()
        print ''
        print 'Abruf beendet: %s erfolgreich, %s fehlgeschlagen.' % (
            success, failures)
        print 'Abrufzeit: ' + fetched_at
    finally:
        # Auch bei einem unerwarteten Fehler die Datenbankverbindung schließen.
        con.close()

if __name__ == "__main__":
    main()
