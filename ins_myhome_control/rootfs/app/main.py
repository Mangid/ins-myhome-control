import json, math, os, time, threading, urllib.request, socket, struct
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SUPERVISOR="http://supervisor/core/api"
INVENTORY="/app/house_inventory.json"
STATE_FILE="/config/ins_myhome_control_state.json"
LATEST={"updated":None,"rooms":[],"energy":{},"bedroom_control":{},"outdoor":{},"futus":{}}
TIMERS={}
FLEX_READY=False
VIRTUAL_DRY1=False
VIRTUAL_DRY1_SINCE=None
ACTUATOR_VERIFY_DELAY=15
ACTUATOR_MIN_ON_POWER_W=10.0
ACTUATOR_MAX_OFF_POWER_W=3.0
ACTUATOR_COMMAND_TS={}

def token(): return os.environ.get("SUPERVISOR_TOKEN","")
def ha_state(eid):
    req=urllib.request.Request(f"{SUPERVISOR}/states/{eid}",headers={"Authorization":f"Bearer {token()}","Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=5) as r: return json.load(r)
def num(eid):
    try: return float(ha_state(eid)["state"])
    except Exception: return None
def ha_service(domain,service,entity_id):
    data=json.dumps({"entity_id":entity_id}).encode()
    req=urllib.request.Request(f"{SUPERVISOR}/services/{domain}/{service}",data=data,method="POST",headers={"Authorization":f"Bearer {token()}","Content-Type":"application/json"})
    with urllib.request.urlopen(req,timeout=8) as r: return r.status
def command_switch(entity_id,on):
    wanted="on" if on else "off"
    if text_state(entity_id)==wanted: return False
    try:
        ha_service("switch","turn_on" if on else "turn_off",entity_id)
        ACTUATOR_COMMAND_TS[entity_id]=time.time()
        print(f"actuator command | entity={entity_id} requested={wanted} result=SENT",flush=True)
        return True
    except Exception as e:
        print(f"actuator command | entity={entity_id} requested={wanted} result=ERROR error={type(e).__name__}:{e}",flush=True)
        return False
def actuator_feedback(switch_entity,power_entity,wanted_on):
    relay=text_state(switch_entity); power=num(power_entity)
    settling=switch_entity in ACTUATOR_COMMAND_TS and time.time()-ACTUATOR_COMMAND_TS[switch_entity]<ACTUATOR_VERIFY_DELAY
    if settling: status="SETTLING"
    elif power is None: status="POWER_UNAVAILABLE"
    elif wanted_on: status="CONFIRMED" if relay=="on" and power>=ACTUATOR_MIN_ON_POWER_W else "FEEDBACK_ERROR"
    else: status="CONFIRMED" if relay=="off" and power<=ACTUATOR_MAX_OFF_POWER_W else "FEEDBACK_ERROR"
    return {"relay":relay,"power_w":round(power,1) if power is not None else None,"feedback":status}
FUTUS_HOST="10.0.0.86"
FUTUS_PORT=502
FUTUS_UNIT_ID=20
FUTUS_REGISTER_START=103
FUTUS_REGISTER_COUNT=4
FUTUS_TIMEOUT=5.0
FUTUS_TX=0

def futus_read():
    global FUTUS_TX
    FUTUS_TX=1 if FUTUS_TX>=65535 else FUTUS_TX+1
    pdu=struct.pack(">BHH",3,FUTUS_REGISTER_START,FUTUS_REGISTER_COUNT)
    req=struct.pack(">HHHB",FUTUS_TX,0,len(pdu)+1,FUTUS_UNIT_ID)+pdu
    try:
        with socket.create_connection((FUTUS_HOST,FUTUS_PORT),timeout=FUTUS_TIMEOUT) as s:
            s.settimeout(FUTUS_TIMEOUT); s.sendall(req)
            header=s.recv(7)
            if len(header)!=7: raise ValueError("short Modbus header")
            tx,proto,length,unit=struct.unpack(">HHHB",header)
            if tx!=FUTUS_TX or proto!=0 or unit!=FUTUS_UNIT_ID: raise ValueError("invalid Modbus header")
            body=b""
            while len(body)<length-1:
                part=s.recv(length-1-len(body))
                if not part: raise ValueError("short Modbus response")
                body+=part
            if body[0]!=3 or body[1]!=8: raise ValueError("invalid Modbus payload")
            regs=struct.unpack(">4H",body[2:10])
            def t(v): return round((v-65536 if v>=32768 else v)/10.0,1)
            return {"connected":True,"fresh":True,"t3":t(regs[0]),"t4":t(regs[1]),"t5":t(regs[2]),"t6":t(regs[3]),"last_success":time.time()}
    except Exception as e:
        return {"connected":False,"fresh":False,"t3":None,"t4":None,"t5":None,"t6":None,"error":f"{type(e).__name__}: {e}"}

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
    global FLEX_READY,VIRTUAL_DRY1,VIRTUAL_DRY1_SINCE
    try:
        with open(STATE_FILE,encoding="utf-8") as f:
            data=json.load(f)
        TIMERS.update({k:float(v) for k,v in data.get("timers",{}).items()})
        FLEX_READY=bool(data.get("flex_ready",False))
        VIRTUAL_DRY1=bool(data.get("virtual_dry1",False))
        VIRTUAL_DRY1_SINCE=data.get("virtual_dry1_since")
    except Exception:
        pass

def save_persistent():
    try:
        os.makedirs(os.path.dirname(STATE_FILE),exist_ok=True)
        tmp=STATE_FILE+".tmp"
        with open(tmp,"w",encoding="utf-8") as f:
            json.dump({"timers":TIMERS,"flex_ready":FLEX_READY,"virtual_dry1":VIRTUAL_DRY1,"virtual_dry1_since":VIRTUAL_DRY1_SINCE},f)
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
                if delta>=3.0:
                    vent="SEHR_GUT"
                    vreason=f"Außenluft ist {delta:.1f} g/m³ trockener"
                elif delta>=1.5:
                    vent="LUEFTEN"
                    vreason=f"Außenluft ist {delta:.1f} g/m³ trockener"
                elif delta>=0.6:
                    vent="MOEGLICH"
                    vreason=f"Kleiner Trocknungsvorteil: {delta:.1f} g/m³"
                else:
                    vent="NICHT_SINNVOLL"
                    vreason="Außenluft bringt aktuell kaum Trocknung"
                if floor_key=="basement" and delta<0.6:
                    vreason="Keller: Außenluft bringt kaum Trocknung oder zusätzliche Feuchte"
                row.update({"ventilation":vent,"ventilation_reason":vreason,"humidity_delta":round(delta,1)})
            if key=="bedroom" and floor_key=="ground_floor":
                vals=[]
                for k in ("north_wall_corner","north_wall_center"):
                    if cfg.get(k):
                        tw=num(cfg[k])
                        if tw is not None: vals.append((tw,surface_rh(td,tw)))
                if vals:
                    worst=max(vals,key=lambda x:x[1])
                    row.update({"method":"Oberfläche gemessen","wall_temperature":round(worst[0],1),"surface_humidity":round(worst[1],1),"risk":surface_risk(worst[1])})
                    if outdoor_ah is not None and worst[1]>=80 and row.get("ventilation") in ("SEHR_GUT","LUEFTEN"):
                        row["ventilation_reason"]=f"Schimmelrisiko hoch; Außenluft {row['humidity_delta']:.1f} g/m³ trockener"
            out.append(row)
    order={"KRITISCH":4,"HOCH":3,"ERHOEHT":2,"NIEDRIG":1}
    return sorted(out,key=lambda x:(-order.get(x["risk"],0),x["floor"],x["name"]))

def loop():
    load_persistent()
    print("INS MyHome Control 0.6.0 starting | mode=ACTIVE | gui=8099 | state=/config",flush=True)
    while True:
        try:
            ocfg=INVENTORY_DATA["areas"]["outdoor"]["terrace"]
            ot=num(ocfg["temperature"]); orh=num(ocfg["humidity"])
            oah=abs_humidity(ot,orh) if ot is not None and orh is not None else None
            otd=dew(ot,orh) if ot is not None and orh is not None else None
            futus=futus_read()
            print("futus | connected=%s fresh=%s t3=%s t4=%s t5=%s t6=%s error=%s" % (futus.get("connected"),futus.get("fresh"),futus.get("t3"),futus.get("t4"),futus.get("t5"),futus.get("t6"),futus.get("error")),flush=True)
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
                elif worst>=70 and elev>=10800:
                    rec="GRUPPE_1"; reason=f"Langzeitschutz: {worst:.1f}% seit {elev//60} min erhoeht - unabhaengig von PV"
                elif worst>=70 and elev>=1200 and FLEX_READY:
                    rec="GRUPPE_1"; reason=f"Erhoeht {worst:.1f}% seit {elev//60} min - flexibler PV-Pool {flexible:.0f} W"
                else:
                    rec="AUS"
                    reason=(f"{worst:.1f}% seit {elev//60} min erhoeht; Freigabe ab 20 min + Energie" if worst>=70 else f"{worst:.1f}% unkritisch")
                global VIRTUAL_DRY1,VIRTUAL_DRY1_SINCE
                ts=time.time()
                if rec in ("GRUPPE_1","BEIDE") and not VIRTUAL_DRY1:
                    VIRTUAL_DRY1=True
                    VIRTUAL_DRY1_SINCE=ts
                    save_persistent()
                virtual_runtime=int((ts-VIRTUAL_DRY1_SINCE)/60) if VIRTUAL_DRY1 and VIRTUAL_DRY1_SINCE else 0
                below72=elapsed("bed_below72",worst<72,now)
                if VIRTUAL_DRY1 and rec=="AUS" and virtual_runtime>=120 and below72>=1200:
                    VIRTUAL_DRY1=False
                    VIRTUAL_DRY1_SINCE=None
                    save_persistent()
                bc=INVENTORY_DATA["areas"]["ground_floor"]["bedroom"]
                want1=VIRTUAL_DRY1
                want2=(rec=="BEIDE")
                command_switch(bc["mold_dry_1"],want1)
                command_switch(bc["mold_dry_2"],want2)
                fb1=actuator_feedback(bc["mold_dry_1"],bc["mold_dry_1_power"],want1)
                fb2=actuator_feedback(bc["mold_dry_2"],bc["mold_dry_2_power"],want2)
                print("actuator active | group1=%s power=%sW feedback=%s | group2=%s power=%sW feedback=%s" % (fb1["relay"],fb1["power_w"],fb1["feedback"],fb2["relay"],fb2["power_w"],fb2["feedback"]),flush=True)
                control={"recommendation":rec,"reason":reason,"elevated_min":elev//60,"high_min":high//60,"critical_min":crit//60,"flex_ready":FLEX_READY,"flex_min":flex_for//60,"dry1":text_state(bc["mold_dry_1"]),"dry2":text_state(bc["mold_dry_2"]),"actuator_action":("EINSCHALTEN_BEIDE" if rec=="BEIDE" else ("EINSCHALTEN_GRUPPE_1" if rec=="GRUPPE_1" else "AUS")),"minimum_runtime_min":120,"off_threshold_surface_rh":72,"anti_cycle":True,"virtual_dry1":VIRTUAL_DRY1,"virtual_runtime_min":virtual_runtime,"below72_min":below72//60}
                print(f"bedroom mold | recommendation={rec} | elevated_for={elev//60}m flex_ready={str(FLEX_READY).lower()} | runtime={virtual_runtime}m below72={below72//60}m | reason={reason}",flush=True)
            LATEST.update({"updated":time.strftime("%Y-%m-%d %H:%M:%S"),"rooms":rooms,"energy":{"grid_export":round(export),"ac_thor":round(acp),"flexible":round(flexible)},"bedroom_control":control,"outdoor":{"temperature":round(ot,1) if ot is not None else None,"humidity":round(orh,1) if orh is not None else None,"dew_point":round(otd,1) if otd is not None else None,"absolute_humidity":round(oah,1) if oah is not None else None}})
            if bed: print(f'climate overview | rooms={len(rooms)} bedroom_risk={bed["risk"]} method={bed["method"]}',flush=True)
        except Exception as e: print(f"ERROR | {type(e).__name__}: {e}",flush=True)
        time.sleep(30)

HTML='''<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>INS MyHome Control</title>
<style>body{font-family:system-ui;margin:0;background:#10151c;color:#edf3f8}.wrap{max-width:1100px;margin:auto;padding:18px}h1{margin:0 0 4px}.sub{color:#9fb0c0;margin-bottom:16px}.top,.grid{display:grid;gap:12px}.top{grid-template-columns:repeat(3,1fr);margin-bottom:18px}.card,.stat{background:#18212b;border:1px solid #283746;border-radius:14px;padding:14px}.grid{grid-template-columns:repeat(auto-fit,minmax(235px,1fr))}.name{font-size:18px;font-weight:700}.floor,.muted{color:#9fb0c0;font-size:13px}.vals{display:flex;gap:14px;margin:10px 0}.big{font-size:22px}.badge{display:inline-block;padding:4px 9px;border-radius:999px;background:#273544}.NIEDRIG{background:#173d2b}.ERHOEHT{background:#594916}.HOCH{background:#64391b}.KRITISCH{background:#6b2228}@media(max-width:650px){.top{grid-template-columns:1fr}}</style></head>
<body><div class="wrap"><h1>INS MyHome Control</h1><div class="sub">Raumklima & Schimmelübersicht · Shadow</div><div class="top" id="energy"></div><div id="outside"></div><div id="bedctl"></div><div id="egtitle"></div><div class="grid" id="eg"></div><div id="ktitle"></div><div class="grid" id="kg"></div></div>
<script>async function load(){let d=await fetch('api/status').then(r=>r.json());document.getElementById('energy').innerHTML='<div class="stat"><div class="muted">Flexibler PV-Pool</div><div class="big">'+d.energy.flexible+' W</div></div><div class="stat"><div class="muted">AC-THOR</div><div class="big">'+d.energy.ac_thor+' W</div></div><div class="stat"><div class="muted">Netzexport</div><div class="big">'+d.energy.grid_export+' W</div></div>';let c=d.bedroom_control||{};document.getElementById('bedctl').innerHTML=c.recommendation?'<div class=\"card\" style=\"margin-bottom:18px\"><div class=\"floor\">Schlafzimmer · Schimmel-DRY Shadow</div><div class=\"name\">Empfehlung: '+c.recommendation+'</div><div style=\"margin:8px 0\">'+c.reason+'</div><div class=\"muted\">≥70%: '+c.elevated_min+' min · ≥80%: '+c.high_min+' min · ≥90%: '+c.critical_min+' min · Energie bereit: '+c.flex_ready+' ('+c.flex_min+' min) · Gruppe 1: '+c.dry1+' · Gruppe 2: '+c.dry2+'</div></div>':'';document.getElementById('outside').innerHTML=d.outdoor.absolute_humidity!==null?'<div class="card" style="margin-bottom:18px"><div class="floor">Außenluft · Terrasse</div><div class="name">'+d.outdoor.temperature+'°C · '+d.outdoor.humidity+'%</div><div>Taupunkt '+d.outdoor.dew_point+'°C · abs. Feuchte '+d.outdoor.absolute_humidity+' g/m³</div></div>':'';function card(r){let v=r.ventilation||'UNBEKANNT';let vt=v==='SEHR_GUT'?'Sehr gute Lüftungsbedingungen':(v==='LUEFTEN'?'Lüften empfohlen':(v==='MOEGLICH'?'Lüften möglich':'Fenster eher geschlossen'));return '<div class="card"><div class="floor">'+r.floor+'</div><div class="name">'+r.name+'</div><div class="vals"><div><span class="big">'+r.temperature+'°C</span><div class="muted">Raum</div></div><div><span class="big">'+r.humidity+'%</span><div class="muted">rF</div></div></div><div>Taupunkt '+r.dew_point+'°C · abs. Feuchte '+r.absolute_humidity+' g/m³</div>'+(r.surface_humidity!==undefined?'<div>kritische Oberfläche: '+r.wall_temperature+'°C / '+r.surface_humidity+'%</div>':'')+'<p><span class="badge '+r.risk+'">'+r.risk+'</span> <span class="muted">'+r.method+'</span></p><div><b>'+vt+'</b> <span class="muted">Δ '+(r.humidity_delta!==undefined?r.humidity_delta:'?')+' g/m³</span></div><div class="muted">'+(r.ventilation_reason||'')+'</div></div>';}document.getElementById('egtitle').innerHTML='<h2>Erdgeschoss</h2>';document.getElementById('ktitle').innerHTML='<h2>Keller</h2>';document.getElementById('eg').innerHTML=d.rooms.filter(r=>r.floor==='EG').map(card).join('');document.getElementById('kg').innerHTML=d.rooms.filter(r=>r.floor==='Keller').map(card).join('');}load();setInterval(load,30000);</script></body></html>'''

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
