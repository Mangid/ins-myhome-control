import json, math, os, time, threading, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SUPERVISOR="http://supervisor/core/api"
INVENTORY="/app/house_inventory.json"
STATE_FILE="/config/ins_myhome_control_state.json"
LATEST={"updated":None,"rooms":[],"energy":{},"bedroom_control":{},"outdoor":{}}
TIMERS={}
FLEX_READY=False

def token(): return os.environ.get("SUPERVISOR_TOKEN","")
def ha_state(eid):
    req=urllib.request.Request(f"{SUPERVISOR}/states/{eid}",headers={"Authorization":f"Bearer {token()}","Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=5) as r: return json.load(r)
def num(eid):
    try: return float(ha_state(eid)["state"])
    except Exception: return None
def dew(t,rh):
    a,b=17.62,243.12; g=(a*t/(b+t))+math.log(rh/100.0); return b*g/(a-g)
def abs_humidity(t,rh):
    return 216.7*((rh/100.0)*6.112*math.exp((17.62*t)/(243.12+t)))/(273.15+t)
def surface_rh(td,tw):
    a,b=17.62,243.12
    return 100*math.exp((a*td/(b+td))-(a*tw/(b+tw)))
def room_risk(rh):
    if rh>=70:return "HOCH"
    if rh>=60:return "ERHOEHT"
    return "NIEDRIG"
def surface_risk(rh):
    if rh>=90:return "KRITISCH"
    if rh>=80:return "HOCH"
    if rh>=70:return "ERHOEHT"
    return "NIEDRIG"

def text_state(eid):
    try: return ha_state(eid)["state"]
    except Exception: return "unknown"

def load_persistent():
    global FLEX_READY
    try:
        with open(STATE_FILE,encoding="utf-8") as f:
            data=json.load(f)
        TIMERS.update({k:float(v) for k,v in data.get("timers",{}).items()})
        FLEX_READY=bool(data.get("flex_ready",False))
    except Exception:
        pass

def save_persistent():
    try:
        os.makedirs(os.path.dirname(STATE_FILE),exist_ok=True)
        tmp=STATE_FILE+".tmp"
        with open(tmp,"w",encoding="utf-8") as f:
            json.dump({"timers":TIMERS,"flex_ready":FLEX_READY},f)
        os.replace(tmp,STATE_FILE)
    except Exception as e:
        print(f"state persist warning | {e}",flush=True)

def elapsed(key,active,now):
    if not active:
        if key in TIMERS:
            TIMERS.pop(key,None); save_persistent()
        return 0
    if key not in TIMERS:
        TIMERS[key]=time.time()
        save_persistent()
    return int(time.time()-TIMERS[key])

with open(INVENTORY,encoding="utf-8") as f: INVENTORY_DATA=json.load(f)
ROOM_NAMES={"kitchen":"Küche","wc":"WC","vestibule":"Windfang","living_room":"Wohnzimmer","guest_room":"Gästezimmer","bedroom":"Schlafzimmer","child_room":"Kinderzimmer","bathroom":"Badezimmer","storage":"Lagerraum","garage":"Garage","workshop":"Werkstatt","technical_room":"Technikraum","office":"Büro","hobby_room":"Hobbyraum","wood_boiler_room":"Holzkesselraum","pellet_room":"Pelletraum","boiler_room":"Heizraum"}

def collect_rooms(outdoor_ah=None):
    out=[]
    for floor_key,floor_name in (("ground_floor","EG"),("basement","Keller")):
        for key,cfg in INVENTORY_DATA["areas"].get(floor_key,{}).items():
            t=num(cfg["temperature"]) if cfg.get("temperature") else None
            rh=num(cfg["humidity"]) if cfg.get("humidity") else None
            if t is None or rh is None: continue
            td=dew(t,rh); ah=abs_humidity(t,rh)
            row={"floor":floor_name,"key":key,"name":ROOM_NAMES.get(key,key),"temperature":round(t,1),"humidity":round(rh,1),"dew_point":round(td,1),"absolute_humidity":round(ah,1),"method":"Raumklima","risk":room_risk(rh)}
            if outdoor_ah is not None:
                delta=ah-outdoor_ah
                if delta>=2.0: vent="LUEFTEN"
                elif delta>=0.8: vent="MOEGLICH"
                else: vent="NICHT_SINNVOLL"
                row.update({"ventilation":vent,"humidity_delta":round(delta,1)})
            if key=="bedroom" and floor_key=="ground_floor":
                vals=[]
                for k in ("north_wall_corner","north_wall_center"):
                    if cfg.get(k):
                        tw=num(cfg[k])
                        if tw is not None: vals.append((tw,surface_rh(td,tw)))
                if vals:
                    worst=max(vals,key=lambda x:x[1])
                    row.update({"method":"Oberfläche gemessen","wall_temperature":round(worst[0],1),"surface_humidity":round(worst[1],1),"risk":surface_risk(worst[1])})
            out.append(row)
    order={"KRITISCH":4,"HOCH":3,"ERHOEHT":2,"NIEDRIG":1}
    return sorted(out,key=lambda x:(-order.get(x["risk"],0),x["floor"],x["name"]))

def loop():
    load_persistent()\n    print("INS MyHome Control 0.3.6 starting | mode=SHADOW | gui=8099 | state=/config",flush=True)
    while True:
        try:
            ocfg=INVENTORY_DATA["areas"]["outdoor"]["terrace"]
            ot=num(ocfg["temperature"]); orh=num(ocfg["humidity"])
            oah=abs_humidity(ot,orh) if ot is not None and orh is not None else None
            otd=dew(ot,orh) if ot is not None and orh is not None else None
            rooms=collect_rooms(oah)
            grid=num(INVENTORY_DATA["areas"]["energy"]["grid_power"])
            ac=num(INVENTORY_DATA["areas"]["energy"]["ac_thor_power"])
            export=max(0,-grid) if grid is not None else 0
            acp=max(0,ac) if ac is not None else 0
            flexible=export+acp
            bed=next((r for r in rooms if r["key"]=="bedroom" and r["floor"]=="EG"),None)
            control={}
            if bed and bed.get("surface_humidity") is not None:
                global FLEX_READY
                now=time.monotonic()
                worst=bed["surface_humidity"]
                elev=elapsed("bed_elev",worst>=70,now)
                high=elapsed("bed_high",worst>=80,now)
                crit=elapsed("bed_crit",worst>=90,now)
                flex_for=elapsed("flex",flexible>=300,now)
                if FLEX_READY and flexible<100: FLEX_READY=False
                elif (not FLEX_READY) and flex_for>=300: FLEX_READY=True
                if worst>=90 and crit>=300:
                    rec="BEIDE"; reason=f"Kritisch {worst:.1f}% seit {crit//60} min"
                elif worst>=80 and high>=1200:
                    rec="GRUPPE_1"; reason=f"Hoch {worst:.1f}% seit {high//60} min - Schutzbedarf unabhaengig von PV"
                elif worst>=70 and elev>=1200 and FLEX_READY:
                    rec="GRUPPE_1"; reason=f"Erhoeht {worst:.1f}% seit {elev//60} min - flexibler PV-Pool {flexible:.0f} W"
                else:
                    rec="AUS"
                    reason=(f"{worst:.1f}% seit {elev//60} min erhoeht; Freigabe ab 20 min + Energie" if worst>=70 else f"{worst:.1f}% unkritisch")
                bc=INVENTORY_DATA["areas"]["ground_floor"]["bedroom"]
                control={"recommendation":rec,"reason":reason,"elevated_min":elev//60,"high_min":high//60,"critical_min":crit//60,"flex_ready":FLEX_READY,"flex_min":flex_for//60,"dry1":text_state(bc["mold_dry_1"]),"dry2":text_state(bc["mold_dry_2"])}
                print(f"bedroom mold shadow | recommendation={rec} | elevated_for={elev//60}m flex_ready={str(FLEX_READY).lower()} | reason={reason}",flush=True)
            LATEST.update({"updated":time.strftime("%Y-%m-%d %H:%M:%S"),"rooms":rooms,"energy":{"grid_export":round(export),"ac_thor":round(acp),"flexible":round(flexible)},"bedroom_control":control,"outdoor":{"temperature":round(ot,1) if ot is not None else None,"humidity":round(orh,1) if orh is not None else None,"dew_point":round(otd,1) if otd is not None else None,"absolute_humidity":round(oah,1) if oah is not None else None}})
            if bed: print(f'climate overview | rooms={len(rooms)} bedroom_risk={bed["risk"]} method={bed["method"]}',flush=True)
        except Exception as e: print(f"ERROR | {type(e).__name__}: {e}",flush=True)
        time.sleep(30)

HTML='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>INS MyHome Control</title>
<style>body{font-family:system-ui;margin:0;background:#10151c;color:#edf3f8}.wrap{max-width:1100px;margin:auto;padding:18px}h1{margin:0 0 4px}.sub{color:#9fb0c0;margin-bottom:16px}.top,.grid{display:grid;gap:12px}.top{grid-template-columns:repeat(3,1fr);margin-bottom:18px}.card,.stat{background:#18212b;border:1px solid #283746;border-radius:14px;padding:14px}.grid{grid-template-columns:repeat(auto-fit,minmax(235px,1fr))}.name{font-size:18px;font-weight:700}.floor,.muted{color:#9fb0c0;font-size:13px}.vals{display:flex;gap:14px;margin:10px 0}.big{font-size:22px}.badge{display:inline-block;padding:4px 9px;border-radius:999px;background:#273544}.NIEDRIG{background:#173d2b}.ERHOEHT{background:#594916}.HOCH{background:#64391b}.KRITISCH{background:#6b2228}@media(max-width:650px){.top{grid-template-columns:1fr}}</style></head>
<body><div class="wrap"><h1>INS MyHome Control</h1><div class="sub">Raumklima & Schimmelübersicht · Shadow</div><div class="top" id="energy"></div><div id="outside"></div><div id="bedctl"></div><div id="egtitle"></div><div class="grid" id="eg"></div><div id="ktitle"></div><div class="grid" id="kg"></div></div>
<script>async function load(){let d=await fetch('api/status').then(r=>r.json());document.getElementById('energy').innerHTML='<div class="stat"><div class="muted">Flexibler PV-Pool</div><div class="big">'+d.energy.flexible+' W</div></div><div class="stat"><div class="muted">AC-THOR</div><div class="big">'+d.energy.ac_thor+' W</div></div><div class="stat"><div class="muted">Netzexport</div><div class="big">'+d.energy.grid_export+' W</div></div>';let c=d.bedroom_control||{};document.getElementById('bedctl').innerHTML=c.recommendation?'<div class=\"card\" style=\"margin-bottom:18px\"><div class=\"floor\">Schlafzimmer · Schimmel-DRY Shadow</div><div class=\"name\">Empfehlung: '+c.recommendation+'</div><div style=\"margin:8px 0\">'+c.reason+'</div><div class=\"muted\">≥70%: '+c.elevated_min+' min · ≥80%: '+c.high_min+' min · ≥90%: '+c.critical_min+' min · Energie bereit: '+c.flex_ready+' ('+c.flex_min+' min) · Gruppe 1: '+c.dry1+' · Gruppe 2: '+c.dry2+'</div></div>':'';document.getElementById('outside').innerHTML=d.outdoor.absolute_humidity!==null?'<div class="card" style="margin-bottom:18px"><div class="floor">Außenluft · Terrasse</div><div class="name">'+d.outdoor.temperature+'°C · '+d.outdoor.humidity+'%</div><div>Taupunkt '+d.outdoor.dew_point+'°C · abs. Feuchte '+d.outdoor.absolute_humidity+' g/m³</div></div>':'';function card(r){let v=r.ventilation||'UNBEKANNT';let vt=v==='LUEFTEN'?'Lüften empfohlen':(v==='MOEGLICH'?'Lüften möglich':'Fenster eher geschlossen');return '<div class="card"><div class="floor">'+r.floor+'</div><div class="name">'+r.name+'</div><div class="vals"><div><span class="big">'+r.temperature+'°C</span><div class="muted">Raum</div></div><div><span class="big">'+r.humidity+'%</span><div class="muted">rF</div></div></div><div>Taupunkt '+r.dew_point+'°C · abs. Feuchte '+r.absolute_humidity+' g/m³</div>'+(r.surface_humidity!==undefined?'<div>kritische Oberfläche: '+r.wall_temperature+'°C / '+r.surface_humidity+'%</div>':'')+'<p><span class="badge '+r.risk+'">'+r.risk+'</span> <span class="muted">'+r.method+'</span></p><div><b>'+vt+'</b> <span class="muted">Δ '+(r.humidity_delta!==undefined?r.humidity_delta:'?')+' g/m³</span></div></div>';}document.getElementById('egtitle').innerHTML='<h2>Erdgeschoss</h2>';document.getElementById('ktitle').innerHTML='<h2>Keller</h2>';document.getElementById('eg').innerHTML=d.rooms.filter(r=>r.floor==='EG').map(card).join('');document.getElementById('kg').innerHTML=d.rooms.filter(r=>r.floor==='Keller').map(card).join('');}load();setInterval(load,30000);</script></body></html>'''

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        path=self.path.split("?")[0].rstrip("/")
        if path.endswith("/api/status"):
            body=json.dumps(LATEST,ensure_ascii=False).encode()
            self.send_response(200);self.send_header("Content-Type","application/json; charset=utf-8");self.end_headers();self.wfile.write(body)
        else:
            body=HTML.encode()
            self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.end_headers();self.wfile.write(body)
    def log_message(self,*args): pass

threading.Thread(target=loop,daemon=True).start()
ThreadingHTTPServer(("0.0.0.0",8099),Handler).serve_forever()
