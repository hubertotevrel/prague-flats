"""Generate a self-contained Leaflet dashboard from the scored DB.

One HTML file with the data embedded, so it opens by double-click (no server, works on
file://) and also serves as-is from GitHub Pages later. Markers are coloured by score;
the work location is marked; shortlist/hide live in the browser's localStorage.
"""
from __future__ import annotations

import json

from . import config
from .notify import inquiry_draft

_QUERY = """
SELECT l.id, l.score, l.disposition, l.district, l.city_part, l.street,
       l.all_in_czk, l.all_in_estimated, l.commute_min, l.address,
       l.latitude, l.longitude, COALESCE(st.status,'new') AS status,
       (SELECT url FROM sources s WHERE s.listing_id = l.id AND s.is_active = 1
        ORDER BY (s.price_czk + COALESCE(s.charges_czk,0)) LIMIT 1) AS url,
       (SELECT images_json FROM sources s WHERE s.listing_id = l.id AND s.is_active = 1
        AND images_json IS NOT NULL AND images_json NOT IN ('', '[]')
        ORDER BY (s.price_czk + COALESCE(s.charges_czk,0)) LIMIT 1) AS images_json
FROM listings l
LEFT JOIN status_tracker st ON st.listing_id = l.id
WHERE l.passes_filters = 1 AND l.score IS NOT NULL
  AND l.latitude IS NOT NULL AND l.longitude IS NOT NULL
ORDER BY l.score DESC
"""


def _flats(conn) -> list[dict]:
    out = []
    for r in conn.execute(_QUERY):
        try:
            imgs = json.loads(r["images_json"]) if r["images_json"] else []
        except Exception:
            imgs = []
        out.append({
            "id": r["id"],
            "score": round(r["score"], 3),
            "disp": r["disposition"],
            "district": r["district"],
            "cityPart": r["city_part"],
            "allIn": r["all_in_czk"],
            "est": bool(r["all_in_estimated"]),
            "commute": r["commute_min"],
            "address": r["address"],
            "lat": r["latitude"],
            "lon": r["longitude"],
            "url": r["url"],
            "status": r["status"],
            "img": imgs[0] if imgs else None,
            "inquiry": inquiry_draft(r["disposition"], r["street"]),
        })
    return out


def build_html(conn) -> tuple[str, int]:
    flats = _flats(conn)
    html = (_TEMPLATE
            .replace("__FLATS__", json.dumps(flats, ensure_ascii=False))
            .replace("__WORK__", json.dumps({"lat": config.WORK_LAT, "lon": config.WORK_LON,
                                             "label": config.WORK_ADDRESS}))
            .replace("__THRESHOLD__", str(config.NOTIFY_THRESHOLD)))
    return html, len(flats)


_TEMPLATE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Prague flat-hunt</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  :root{--bg:#0f172a;--panel:#fff;--muted:#64748b;--line:#e2e8f0}
  *{box-sizing:border-box} html,body{margin:0;height:100%;font:14px/1.45 system-ui,sans-serif;color:#0f172a}
  #app{display:flex;height:100%}
  #side{width:360px;min-width:300px;display:flex;flex-direction:column;border-right:1px solid var(--line);background:#f8fafc}
  #map{flex:1}
  header{padding:12px 14px;border-bottom:1px solid var(--line);background:#fff}
  header h1{margin:0 0 2px;font-size:16px} header .sub{color:var(--muted);font-size:12px}
  .controls{padding:8px 14px;border-bottom:1px solid var(--line);background:#fff;font-size:12px;color:var(--muted)}
  .controls label{margin-right:10px;cursor:pointer} .controls input{vertical-align:middle}
  #list{overflow:auto;flex:1}
  .card{padding:10px 14px;border-bottom:1px solid var(--line);cursor:pointer;display:flex;gap:10px}
  .card:hover{background:#eef2ff}
  .card.hidden{display:none}
  .dot{width:10px;height:10px;border-radius:50%;margin-top:5px;flex:none}
  .card .meta{flex:1;min-width:0}
  .card .t{font-weight:600} .card .d{color:var(--muted);font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .sc{font-weight:700;font-variant-numeric:tabular-nums}
  .pop{width:230px} .pop img{width:100%;height:120px;object-fit:cover;border-radius:6px;margin-bottom:6px}
  .pop .row{margin:2px 0} .pop .muted{color:var(--muted)}
  .pop a{color:#2563eb} .pop .btns{margin-top:8px;display:flex;gap:6px;flex-wrap:wrap}
  .pop button{font:12px system-ui;padding:4px 8px;border:1px solid var(--line);border-radius:6px;background:#fff;cursor:pointer}
  .pop button:hover{background:#f1f5f9}
  .badge{font-size:11px;padding:1px 6px;border-radius:10px;background:#eef2ff;color:#3730a3}
  .legend{position:absolute;z-index:1000;bottom:14px;right:14px;background:#fff;padding:8px 10px;border-radius:8px;box-shadow:0 1px 6px rgba(0,0,0,.2);font-size:12px}
  .legend span{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:5px}
</style></head>
<body><div id="app">
  <div id="side">
    <header><h1>Prague flat-hunt</h1><div class="sub" id="sub"></div></header>
    <div class="controls">
      <label>min score <input id="minScore" type="range" min="0" max="1" step="0.05" value="0"> <span id="minLbl">0.00</span></label><br>
      <label><input type="checkbox" id="onlyShort"> ★ shortlist only</label>
      <label><input type="checkbox" id="showHidden"> show hidden</label>
    </div>
    <div id="list"></div>
  </div>
  <div id="map"></div>
  <div class="legend">
    <div><span style="background:#16a34a"></span>≥ __THRESHOLD__ (top)</div>
    <div><span style="background:#f59e0b"></span>0.60–__THRESHOLD__</div>
    <div><span style="background:#9ca3af"></span>below</div>
    <div><span style="background:#2563eb"></span>your work</div>
  </div>
</div>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const FLATS = __FLATS__, WORK = __WORK__, THRESHOLD = __THRESHOLD__;
const LS = {
  get(k){ try{return new Set(JSON.parse(localStorage.getItem(k)||'[]'))}catch(e){return new Set()} },
  set(k,s){ localStorage.setItem(k, JSON.stringify([...s])) }
};
let shortlist = LS.get('pf_shortlist'), hidden = LS.get('pf_hidden');

const map = L.map('map').setView([50.075,14.44], 12);
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
  {maxZoom:19, attribution:'© OpenStreetMap'}).addTo(map);
L.marker([WORK.lat, WORK.lon], {title:'Work: '+WORK.label,
  icon:L.divIcon({className:'',html:'<div style="background:#2563eb;color:#fff;border-radius:50%;width:26px;height:26px;display:flex;align-items:center;justify-content:center;font-size:14px;box-shadow:0 0 0 3px #fff">🏢</div>',iconSize:[26,26],iconAnchor:[13,13]})}
).addTo(map).bindPopup('<b>Work</b><br>'+WORK.label);

function color(s){ return s>=THRESHOLD ? '#16a34a' : s>=0.60 ? '#f59e0b' : '#9ca3af'; }
function money(f){ return f.allIn ? f.allIn.toLocaleString('cs-CZ')+(f.est?'~':'')+' Kč' : '—'; }
function esc(t){ return (t||'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

const markers = {};
FLATS.forEach(f=>{
  const m = L.circleMarker([f.lat,f.lon], {radius:7,color:'#fff',weight:1.5,
    fillColor:color(f.score),fillOpacity:.9});
  m.bindPopup(()=>popupHtml(f), {minWidth:230});
  markers[f.id] = m;
});

function popupHtml(f){
  const sl = shortlist.has(f.id), hd = hidden.has(f.id);
  return `<div class="pop">
    ${f.img?`<img src="${f.img.startsWith('//')?'https:'+f.img:f.img}" onerror="this.style.display='none'">`:''}
    <div class="row"><b>${f.score.toFixed(2)}</b> · ${esc(f.disp)} · ${esc(f.district||'')}
      ${f.status&&f.status!=='new'?`<span class="badge">${f.status}</span>`:''}</div>
    <div class="row">${money(f)} all-in · ${f.commute!=null?f.commute+' min to work':'commute ?'}</div>
    <div class="row muted">${esc(f.address||'')}</div>
    <div class="row"><a href="${f.url}" target="_blank" rel="noopener">Open listing ↗</a></div>
    <div class="btns">
      <button onclick="toggle('pf_shortlist',${f.id})">${sl?'★ shortlisted':'☆ shortlist'}</button>
      <button onclick="toggle('pf_hidden',${f.id})">${hd?'undo hide':'hide'}</button>
      <button onclick="copyInq(${f.id})">copy inquiry</button>
    </div></div>`;
}
window.copyInq = id => { const f=FLATS.find(x=>x.id===id);
  navigator.clipboard.writeText(f.inquiry).then(()=>alert('Inquiry copied:\n\n'+f.inquiry)); };
window.toggle = (key,id)=>{ const set = key==='pf_shortlist'?shortlist:hidden;
  set.has(id)?set.delete(id):set.add(id); LS.set(key,set); render(); map.closePopup(); };

function visible(){
  const min = +document.getElementById('minScore').value;
  const onlyShort = document.getElementById('onlyShort').checked;
  const showHidden = document.getElementById('showHidden').checked;
  return FLATS.filter(f=> f.score>=min
    && (showHidden || !hidden.has(f.id))
    && (!onlyShort || shortlist.has(f.id)));
}
function render(){
  const vis = visible(), visIds = new Set(vis.map(f=>f.id));
  FLATS.forEach(f=>{ const m=markers[f.id];
    if(visIds.has(f.id)){ if(!map.hasLayer(m)) m.addTo(map); }
    else if(map.hasLayer(m)) map.removeLayer(m); });
  const list = document.getElementById('list'); list.innerHTML='';
  vis.forEach(f=>{
    const el=document.createElement('div'); el.className='card';
    el.innerHTML=`<div class="dot" style="background:${color(f.score)}"></div>
      <div class="meta"><div class="t"><span class="sc">${f.score.toFixed(2)}</span> ·
        ${esc(f.disp)} · ${money(f)} ${shortlist.has(f.id)?' ★':''}</div>
      <div class="d">${esc(f.district||'')} · ${f.commute!=null?f.commute+' min':'? min'} · ${esc(f.cityPart||f.address||'')}</div></div>`;
    el.onclick=()=>{ map.flyTo([f.lat,f.lon],15); markers[f.id].openPopup(); };
    list.appendChild(el);
  });
  document.getElementById('sub').textContent =
    `${vis.length} shown · ${FLATS.length} match filters · ${shortlist.size} shortlisted`;
}
['minScore','onlyShort','showHidden'].forEach(id=>
  document.getElementById(id).addEventListener('input', ()=>{
    document.getElementById('minLbl').textContent =
      (+document.getElementById('minScore').value).toFixed(2);
    render();
  }));
render();
if(FLATS.length){ const b=L.latLngBounds(FLATS.map(f=>[f.lat,f.lon])); b.extend([WORK.lat,WORK.lon]); map.fitBounds(b.pad(0.1)); }
</script></body></html>
"""
