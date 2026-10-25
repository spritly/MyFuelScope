#!/usr/bin/python
# -*- coding: utf-8 -*-

import json
import sqlite3
import datetime
import urlparse
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer

DB_PATH = '/volume1/MyFuelScope/preise.db'
HOST = '10.0.0.2'
PORT = 8080


def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_prices():
    conn = db_connect()
    try:
        rows = conn.execute("""
            SELECT s.station_id, s.name, s.address, s.postal_code, s.city,
                   f.captured_at, f.price_eur
            FROM stations s
            LEFT JOIN fuel_prices f
              ON f.station_id = s.station_id
             AND f.fuel_type = 'SUP'
             AND f.captured_at = (
                 SELECT MAX(f2.captured_at)
                 FROM fuel_prices f2
                 WHERE f2.station_id = s.station_id
                   AND f2.fuel_type = 'SUP'
             )
            ORDER BY
                CASE WHEN f.price_eur IS NULL THEN 1 ELSE 0 END,
                f.price_eur ASC, s.name ASC
        """).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def get_history(station_id, period):
    now = datetime.datetime.now()
    if period == 'today':
        start = now.strftime('%Y-%m-%d') + ' 00:00:00'
        label = 'Heute'
    else:
        start = (now - datetime.timedelta(days=7)).strftime('%Y-%m-%d %H:%M:%S')
        label = 'Letzte 7 Tage'
    end = now.strftime('%Y-%m-%d %H:%M:%S')
    conn = db_connect()
    try:
        rows = conn.execute("""
            SELECT captured_at, price_eur
            FROM fuel_prices
            WHERE station_id = ? AND fuel_type = 'SUP'
              AND captured_at >= ? AND captured_at <= ?
            ORDER BY captured_at ASC
        """, (station_id, start, end)).fetchall()
        return {
            'station_id': station_id,
            'period': period,
            'label': label,
            'start': start,
            'end': end,
            'count': len(rows),
            'points': [dict(row) for row in rows]
        }
    finally:
        conn.close()


def get_lows():
    today = datetime.datetime.now().strftime('%Y-%m-%d') + ' 00:00:00'
    now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    conn = db_connect()
    try:
        rows = conn.execute("""
            SELECT s.station_id, s.name, s.address, s.postal_code, s.city,
                   MIN(f.price_eur) AS low_price
            FROM stations s
            LEFT JOIN fuel_prices f
              ON f.station_id = s.station_id
             AND f.fuel_type = 'SUP'
             AND f.captured_at >= ? AND f.captured_at <= ?
            GROUP BY s.station_id, s.name, s.address, s.postal_code, s.city
            ORDER BY s.name
        """, (today, now)).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            if item['low_price'] is not None:
                hit = conn.execute("""
                    SELECT MIN(captured_at) FROM fuel_prices
                    WHERE station_id = ? AND fuel_type = 'SUP'
                      AND captured_at >= ? AND captured_at <= ?
                      AND price_eur = ?
                """, (item['station_id'], today, now, item['low_price'])).fetchone()
                item['low_at'] = hit[0]
            else:
                item['low_at'] = None
            result.append(item)
        return result
    finally:
        conn.close()


HTML = u"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MyFuelScope</title>
<link rel="icon" type="image/png" href="/images/appfavicon.png">
<style>
* { box-sizing:border-box; }
body { font-family:Arial,sans-serif; background:#f1f5f9; color:#172033; margin:0; padding:18px; }
main { max-width:1100px; margin:auto; }
header { display:flex; align-items:center; gap:16px; margin-bottom:12px; flex-wrap:wrap; }
.applogo { display:block; width:auto; height:auto; max-width:280px; max-height:64px; object-fit:contain; }
h1 { margin:0; font-size:27px; } h2 { margin-top:24px; }
.muted { color:#64748b; }
.best,.panel,.station { background:white; border-radius:12px; padding:17px; margin:12px 0; box-shadow:0 2px 8px #0001; }
.best { border-left:5px solid #16a34a; }
.price { font-size:25px; font-weight:bold; color:#15803d; margin-top:8px; }
#stations { display:grid; grid-template-columns:repeat(auto-fit,minmax(260px,1fr)); gap:12px; }
.station { margin:0; }
.brand { display:flex; align-items:center; justify-content:flex-start; width:100%; height:42px; margin-bottom:10px; color:#334155; font-size:12px; font-weight:bold; letter-spacing:.3px; }
.brand img { display:block; max-width:132px; max-height:40px; width:auto; height:auto; object-fit:contain; object-position:left center; }
.brand-bp,.brand-jet,.brand-avanti,.brand-turmol { background:transparent; }
.name { font-size:18px; font-weight:bold; }
.address,.captured,.low { color:#64748b; margin-top:8px; font-size:14px; }
.address { white-space:pre-line; }
.best-name { display:flex; align-items:center; gap:10px; flex-wrap:wrap; }
.best-name img { display:block; max-width:120px; max-height:38px; width:auto; height:auto; object-fit:contain; }
.low strong { color:#15803d; }
.controls { display:flex; gap:10px; flex-wrap:wrap; align-items:center; margin:10px 0; }
select { font-size:16px; padding:9px; border:1px solid #cbd5e1; border-radius:8px; background:white; max-width:100%; }
.charts { display:grid; grid-template-columns:repeat(auto-fit,minmax(300px,1fr)); gap:12px; }
.chartbox { min-width:0; }
.chartbox h3 { margin:0 0 8px; }
.chart { width:100%; min-height:190px; display:block; overflow:visible; }
.chartmeta { font-size:13px; color:#64748b; margin-top:5px; }
.error { color:#b91c1c; }
@media(max-width:480px) { body {padding:10px;} h1{font-size:23px;} .best,.panel,.station{padding:13px;} }
</style>
</head>
<body>
<main>
<header><img class="applogo" src="/images/applogo.png" alt="MyFuelScope"><div class="muted">Benzin 95 - Preisstatistik</div></header>
<p id="status" class="muted">Lade Preisdaten ...</p>
<section class="best">
<h2 style="margin-top:0">Aktuell günstigste Tankstelle</h2>
<div id="bestName" class="best-name">Preise werden geladen ...</div><div id="bestPrice" class="price">-</div><div id="bestAddress" class="address"></div>
</section>
<h2>Tankstellen <span id="count" class="muted"></span></h2>
<div id="stations">Preisdaten werden geladen ...</div>
<section class="panel">
<h2 style="margin-top:0">Preisverlauf</h2>
<div class="controls"><label for="stationSelect">Tankstelle:</label><select id="stationSelect"><option>Wird geladen ...</option></select></div>
<div class="charts">
<div class="chartbox"><h3>Laufender Tag</h3><svg id="chartToday" class="chart" viewBox="0 0 500 220" role="img" aria-label="Preisverlauf heute"></svg><div id="metaToday" class="chartmeta"></div></div>
<div class="chartbox"><h3>Letzte 7 Tage</h3><svg id="chartWeek" class="chart" viewBox="0 0 500 220" role="img" aria-label="Preisverlauf der letzten sieben Tage"></svg><div id="metaWeek" class="chartmeta"></div></div>
</div>
</section>
</main>
<script>
(function () {
  var stations = [];
  function el(id) { return document.getElementById(id); }
  function addText(parent, tag, cls, value) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    node.textContent = value == null ? '' : String(value);
    parent.appendChild(node);
    return node;
  }
  function price(value) {
    var n = Number(value);
    return isFinite(n) ? n.toFixed(3).replace('.', ',') + ' €' : 'Keine Messung';
  }
  function timeText(value, withDate) {
    if (!value) return 'unbekannt';
    var s = String(value);
    var date = s.substring(0,10).split('-').reverse().join('.');
    var time = s.substring(11,16);
    return withDate ? date + ' ' + time : time;
  }
  function brandClass(name) {
    name = (name || '').toLowerCase();
    if (name.indexOf('bp') === 0) return 'brand brand-bp';
    if (name.indexOf('jet') === 0) return 'brand brand-jet';
    if (name.indexOf('avanti') === 0) return 'brand brand-avanti';
    return 'brand brand-turmol';
  }
  function brandText(name) {
    name = (name || '').toLowerCase();
    if (name.indexOf('bp') === 0) return 'bp';
    if (name.indexOf('jet') === 0) return 'JET';
    if (name.indexOf('avanti') === 0) return 'AVANTI';
    return 'TURMÖL';
  }
  function renderStations(data) {
    var root = el('stations'); root.textContent = '';
    var available = data.filter(function(s) { return s.price_eur !== null && s.price_eur !== undefined; });
    available.sort(function(a,b) { return Number(a.price_eur)-Number(b.price_eur); });
    var best = available.length ? available[0] : null;
    el('count').textContent = '(' + data.length + ')';
    var bestName = el('bestName');
    bestName.textContent = '';
    if (best) {
      var bestLogo = document.createElement('img');
      var bestLowerName = (best.name || '').toLowerCase();
      bestLogo.src = bestLowerName.indexOf('bp') === 0 ? '/images/bp.png' :
                     bestLowerName.indexOf('jet') === 0 ? '/images/jet.png' :
                     bestLowerName.indexOf('avanti') === 0 ? '/images/avanti.png' : '/images/turmoel.png';
      bestLogo.alt = best.name || 'Tankstellenlogo';
      bestLogo.onerror = function() { bestLogo.style.display = 'none'; };
      bestName.appendChild(bestLogo);
      addText(bestName, 'span', '', best.name);
    } else {
      bestName.textContent = 'Keine Preise vorhanden';
    }
    el('bestPrice').textContent = best ? price(best.price_eur) : '-';
    el('bestAddress').textContent = best ? [best.address, [best.postal_code,best.city].filter(Boolean).join(' ')].filter(Boolean).join('\\n') : '';
    data.forEach(function(s) {
      var card = document.createElement('article'); card.className = 'station';
      var logo = document.createElement("div");
      logo.className = brandClass(s.name);
      var logoImg = document.createElement("img");
      var lowerName = (s.name || "").toLowerCase();
      logoImg.src = lowerName.indexOf("bp") === 0 ? "/images/bp.png" :
                    lowerName.indexOf("jet") === 0 ? "/images/jet.png" :
                    lowerName.indexOf("avanti") === 0 ? "/images/avanti.png" : "/images/turmoel.png";
      logoImg.alt = s.name || "Tankstellenlogo";
      logoImg.onerror = function() { logo.textContent = brandText(s.name); };
      logo.appendChild(logoImg);
      card.appendChild(logo);
      addText(card,'div','name',s.name || 'Tankstelle');
      addText(card,'div','address',[s.address, [s.postal_code,s.city].filter(Boolean).join(' ')].filter(Boolean).join('\\n'));
      addText(card,'div','price',price(s.price_eur));
      addText(card,'div','captured','Letzte Erfassung: ' + timeText(s.captured_at,true));
      var low = addText(card,'div','low','Tagestiefststand: wird geladen ...');
      low.setAttribute('data-station-id',s.station_id);
      root.appendChild(card);
    });
    if (!data.length) root.textContent = 'Keine Tankstellen vorhanden.';
    var select = el('stationSelect'); select.textContent = '';
    data.forEach(function(s) {
      var opt = document.createElement('option'); opt.value = s.station_id; opt.textContent = s.name;
      select.appendChild(opt);
    });
    if (data.length) loadCharts();
  }
  function drawChart(svgId, metaId, data, period) {
    var svg = el(svgId); while (svg.firstChild) svg.removeChild(svg.firstChild);
    var ns = 'http://www.w3.org/2000/svg';
    function node(tag, attrs, text) {
      var n = document.createElementNS(ns,tag);
      Object.keys(attrs || {}).forEach(function(k){ n.setAttribute(k,attrs[k]); });
      if (text !== undefined) n.textContent = text;
      svg.appendChild(n); return n;
    }
    var pts = data.points || [];
    if (!pts.length) {
      node('text',{x:250,y:105,'text-anchor':'middle',fill:'#64748b','font-size':14},'Noch keine Messwerte');
      el(metaId).textContent = '0 Messpunkte'; return;
    }
    var values = pts.map(function(p){return Number(p.price_eur);});
    var min = Math.min.apply(null,values), max = Math.max.apply(null,values);
    var span = max-min; if (span < 0.005) span = 0.01;
    var low = min - span*0.15, high = max + span*0.15;
    var left=52, right=480, top=18, bottom=175, width=right-left, height=bottom-top;
    for (var i=0;i<4;i++) {
      var y=top+(height*i/3), val=high-((high-low)*i/3);
      node('line',{x1:left,y1:y,x2:right,y2:y,stroke:'#e2e8f0','stroke-width':1});
      node('text',{x:left-7,y:y+4,'text-anchor':'end',fill:'#64748b','font-size':11},val.toFixed(3).replace('.',','));
    }
    var first = pts[0].captured_at, last = pts[pts.length-1].captured_at;
    var t0 = new Date(first.replace(' ','T') + (first.length===16?':00':'')).getTime();
    var t1 = new Date(last.replace(' ','T') + (last.length===16?':00':'')).getTime();
    if (!isFinite(t0) || !isFinite(t1) || t0===t1) { t0=0; t1=pts.length-1; }
    var coords=[];
    pts.forEach(function(p,i) {
      var t = new Date(p.captured_at.replace(' ','T') + (p.captured_at.length===16?':00':'')).getTime();
      var x = left + ((t-t0)/(t1-t0))*width;
      if (!isFinite(x)) x=left+(i/Math.max(1,pts.length-1))*width;
      var y = bottom - ((Number(p.price_eur)-low)/(high-low))*height;
      coords.push(x.toFixed(1)+','+y.toFixed(1));
    });
    node('polyline',{points:coords.join(' '),fill:'none',stroke:'#0f766e','stroke-width':2.5,'stroke-linejoin':'round','stroke-linecap':'round'});
    [0,Math.floor((pts.length-1)/2),pts.length-1].forEach(function(idx) {
      var p=pts[idx], x=left+(idx/Math.max(1,pts.length-1))*width;
      node('text',{x:x,y:198,'text-anchor':idx===0?'start':(idx===pts.length-1?'end':'middle'),fill:'#64748b','font-size':10},timeText(p.captured_at,period==='week'));
    });
    el(metaId).textContent = pts.length + ' Messpunkte · ' + timeText(first,true) + ' bis ' + timeText(last,true) + ' · Tief ' + price(min);
  }
  function loadCharts() {
    var id = el('stationSelect').value;
    if (!id) return;
    [['today','chartToday','metaToday'],['week','chartWeek','metaWeek']].forEach(function(item) {
      var req = new XMLHttpRequest();
      req.open('GET','/api/history?station_id='+encodeURIComponent(id)+'&period='+item[0]+'&_='+new Date().getTime(),true);
      req.timeout=10000;
      req.onload=function() {
        if (req.status<200 || req.status>=300) { el(item[2]).textContent='Fehler beim Laden des Verlaufs (HTTP '+req.status+')'; return; }
        try { drawChart(item[1],item[2],JSON.parse(req.responseText),item[0]); }
        catch(e) { el(item[2]).textContent='Datenfehler: '+e.message; }
      };
      req.onerror=function(){el(item[2]).textContent='Netzwerkfehler beim Verlauf.';};
      req.send(null);
    });
  }
  function loadLows() {
    var req = new XMLHttpRequest(); req.open('GET','/api/lows?_='+new Date().getTime(),true); req.timeout=10000;
    req.onload=function() {
      if(req.status<200 || req.status>=300) return;
      try {
        var lows=JSON.parse(req.responseText);
        lows.forEach(function(s) {
          var target=document.querySelector('.low[data-station-id="'+s.station_id+'"]');
          if(!target) return;
          if(s.low_price===null || s.low_price===undefined) target.textContent='Tagestiefststand: noch keine Messung';
          else {
            target.textContent='';
            addText(target,'span','', 'Tagestiefststand: ');
            addText(target,'strong','', price(s.low_price) + ' um ' + timeText(s.low_at,false));
          }
        });
      } catch(e) {}
    };
    req.send(null);
  }
  function load() {
    var req = new XMLHttpRequest(); req.open('GET','/api/prices?_='+new Date().getTime(),true); req.timeout=10000;
    req.onload=function() {
      if(req.status<200 || req.status>=300) { el('status').className='error'; el('status').textContent='API-Fehler: HTTP '+req.status; return; }
      try {
        var data=JSON.parse(req.responseText);
        if(!Array.isArray(data)) throw new Error('Unerwartetes Datenformat');
        stations=data; renderStations(data); loadLows();
        el('status').className='muted';
        el('status').textContent='aktualisiert: '+new Date().toLocaleTimeString('de-AT',{hour:'2-digit',minute:'2-digit'})+' Uhr';
      } catch(e) { el('status').className='error'; el('status').textContent='Datenfehler: '+e.message; }
    };
    req.onerror=function(){el('status').className='error';el('status').textContent='Netzwerkfehler beim Laden.';};
    req.ontimeout=function(){el('status').className='error';el('status').textContent='Zeitüberschreitung beim Laden.';};
    req.send(null);
  }
  el('stationSelect').addEventListener('change',loadCharts);
  load(); window.setInterval(load,60000);
}());
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def send_body(self, status, content_type, body):
        if isinstance(body, unicode):
            body = body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path, params = urlparse.urlparse(self.path)[2], urlparse.parse_qs(urlparse.urlparse(self.path)[4])
        try:
            if path.startswith('/images/'):
                filename = path[len('/images/'):]
                if filename not in ('bp.png', 'turmoel.png', 'jet.png', 'avanti.png', 'applogo.png', 'appfavicon.png'):
                    self.send_error(404)
                    return
                image_path = '/volume1/MyFuelScope/webapp/images/' + filename
                try:
                    with open(image_path, 'rb') as image_file:
                        image_body = image_file.read()
                except IOError:
                    self.send_error(404)
                    return
                self.send_body(200, 'image/png', image_body)
                return
            if path == '/api/prices':
                self.send_body(200, 'application/json; charset=utf-8',
                               json.dumps(get_prices(), ensure_ascii=True))
                return
            if path == '/api/lows':
                self.send_body(200, 'application/json; charset=utf-8',
                               json.dumps(get_lows(), ensure_ascii=True))
                return
            if path == '/api/history':
                try:
                    station_id = int(params.get('station_id', [''])[0])
                except (ValueError, TypeError):
                    self.send_body(400, 'application/json; charset=utf-8',
                                   json.dumps({'error':'station_id ungueltig'}))
                    return
                period = params.get('period', ['today'])[0]
                if period not in ('today', 'week'):
                    self.send_body(400, 'application/json; charset=utf-8',
                                   json.dumps({'error':'period muss today oder week sein'}))
                    return
                conn = db_connect()
                try:
                    exists = conn.execute('SELECT 1 FROM stations WHERE station_id=?',
                                          (station_id,)).fetchone()
                finally:
                    conn.close()
                if not exists:
                    self.send_body(404, 'application/json; charset=utf-8',
                                   json.dumps({'error':'Tankstelle nicht gefunden'}))
                    return
                self.send_body(200, 'application/json; charset=utf-8',
                               json.dumps(get_history(station_id, period), ensure_ascii=True))
                return
            if path != '/':
                self.send_error(404)
                return
            self.send_body(200, 'text/html; charset=utf-8', HTML)
        except Exception as exc:
            self.send_body(500, 'application/json; charset=utf-8',
                           json.dumps({'error':str(exc)}, ensure_ascii=True))

    def log_message(self, fmt, *args):
        print '[%s] %s' % (self.log_date_time_string(), fmt % args)


if __name__ == '__main__':
    print 'MyFuelScope startet auf http://%s:%d/' % (HOST, PORT)
    HTTPServer((HOST, PORT), Handler).serve_forever()
