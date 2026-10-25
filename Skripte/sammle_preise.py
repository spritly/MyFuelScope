#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import json
import sqlite3
import subprocess
from datetime import datetime
from HTMLParser import HTMLParser

BASE = '/volume1/MyFuelScope'
DB = os.path.join(BASE, 'preise.db')
TMP = '/tmp'

STATIONS = [
    (35847, 'BP Frohsdorf', 'bp'),
    (1471187, 'Turmoel Quick Guenser Strasse', 'econtrol'),
    (1354682, 'JET Guenser Strasse 92', 'jet_guenser'),
    (1126532, 'Avanti Neunkirchner Strasse 118', 'econtrol'),
    (1354928, 'JET Puchberger Strasse 1', 'jet_puchberger'),
    (1354801, 'Avanti Puchberger Strasse 44', 'econtrol')
]

COORDS = {
    1471187: (47.80411, 16.242),
    1126532: (47.78134, 16.19135),
    1354801: (47.8065, 16.20603)
}

URLS = {
    'bp': 'https://bpretaillocator.geoapp.me/api/v2/locations/AT-410?locale=de_AT&format=json',
    'jet_guenser': 'https://www.jet-austria.at/tankstellen/wiener-neustadt/guenserstrasse-92',
    'jet_puchberger': 'https://www.jet-austria.at/tankstellen/wiener-neustadt/puchberger-strasse-1'
}

def download(url, filename):
    rc = subprocess.call(['wget', '-4', '-q', '-O', filename, url])
    if rc != 0 or not os.path.isfile(filename) or os.path.getsize(filename) == 0:
        raise Exception('Download fehlgeschlagen: ' + url)
    f = open(filename, 'rb')
    try:
        return f.read()
    finally:
        f.close()

def number_from_text(text):
    text = HTMLParser().unescape(text)
    m = re.search(r'([0-9]+,[0-9]{3})', text)
    if not m:
        raise Exception('Preis nicht gefunden')
    return float(m.group(1).replace(',', '.'))

def get_bp():
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
    raw = download(URLS[kind], TMP + '/preisstatistik_' + kind + '.html')
    m = re.search(
        r'id="product_price_fuel_super"[^>]*>(.*?)</div>',
        raw, re.S)
    if not m:
        raise Exception('JET: Superpreis-Feld nicht gefunden')
    price = number_from_text(re.sub(r'<[^>]+>', '', m.group(1)))

    t = re.search(
        r'id="product_price_timestamp_fuel">(.*?)</span>',
        raw, re.S)
    updated = HTMLParser().unescape(t.group(1)) if t else 'unbekannt'
    return price, updated

def get_econtrol(station_id):
    lat, lon = COORDS[station_id]
    url = (
        'https://api.e-control.at/sprit/1.0/search/gas-stations/by-address'
        '?fuelType=SUP&includeClosed=false&latitude=%s&longitude=%s'
        % (lat, lon))
    raw = download(url, TMP + '/preisstatistik_econtrol_%s.json' % station_id)
    data = json.loads(raw)
    for station in data:
        if int(station.get('id', -1)) == station_id:
            for p in station.get('prices', []):
                if p.get('fuelType') == 'SUP' and p.get('amount') is not None:
                    return float(p['amount']), 'vom Anbieter nicht ausgewiesen'
            raise Exception('E-Control: Tankstelle gefunden, aber kein SUP-Preis')
    raise Exception('E-Control: Tankstellen-ID nicht in Antwort enthalten')

def main():
    fetched_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    con = sqlite3.connect(DB)
    cur = con.cursor()
    success = 0
    failures = 0

    try:
        for station_id, name, source in STATIONS:
            try:
                if source == 'bp':
                    price, updated = get_bp()
                elif source.startswith('jet_'):
                    price, updated = get_jet(source)
                else:
                    price, updated = get_econtrol(station_id)

                cur.execute(
                    'INSERT OR REPLACE INTO fuel_prices '
                    '(captured_at, station_id, fuel_type, price_eur) '
                    'VALUES (?, ?, ?, ?)',
                    (fetched_at, station_id, 'SUP', price))

                details = 'station_id=%s; name=%s; price_eur=%.3f; provider_time=%s' % (
                    station_id, name, price, updated)
                cur.execute(
                    'INSERT INTO fetch_log (fetched_at, source, status, details) '
                    'VALUES (?, ?, ?, ?)',
                    (fetched_at, source, 'OK', details))
                print '%s: %.3f EUR/l; Preisstand: %s' % (name, price, updated)
                success += 1

            except Exception as e:
                details = "station_id=%s; name=%s; Fehler=%s" % (station_id, name, str(e))
                cur.execute(
                    "INSERT INTO fetch_log (fetched_at, source, status, details) VALUES (?, ?, ?, ?)",
                    (fetched_at, source, "ERROR", details))
                print "%s: FEHLER: %s" % (name, str(e))
                failures += 1

        con.commit()
        print ''
        print 'Abruf beendet: %s erfolgreich, %s fehlgeschlagen.' % (
            success, failures)
        print 'Abrufzeit: ' + fetched_at
    finally:
        con.close()

if __name__ == "__main__":
    main()
