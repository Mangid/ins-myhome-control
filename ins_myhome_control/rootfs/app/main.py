import json
import math
import os
import time
import urllib.request

SUPERVISOR = "http://supervisor/core/api"

ENTITIES = {
    "room_temp": "sensor.schlafzimmer_thip_schlafzimmer_temperatur",
    "room_rh": "sensor.schlafzimmer_thip_schlafzimmer_rel_luftfeuchte",
    "wall_corner": "sensor.schlafzimmer_shellypm_nordwand_schlafzimmer_temperatur",
    "wall_center": "sensor.schlafzimmer_shellypm_nordwand_schlafzimmer_temperatur_2",
    "grid_power": "sensor.em540_leistung",
    "ac_thor_power": "sensor.my_pv_ac_thor_9s_leistung",
    "dry_1": "switch.infrarot_schlafzimmer_2",
    "dry_2": "switch.schlafzimmer_schimmeldry_schlafzimmer",
}

# Flexible energy pool: actual grid export + AC-THOR power that can yield to smaller loads.
FLEX_ON_W = 300
FLEX_OFF_W = 100
FLEX_CONFIRM_S = 5 * 60
ELEVATED_CONFIRM_S = 20 * 60
HIGH_CONFIRM_S = 20 * 60
CRITICAL_CONFIRM_S = 5 * 60

def token():
    return os.environ.get("SUPERVISOR_TOKEN", "")

def state(entity_id):
    req = urllib.request.Request(
        f"{SUPERVISOR}/states/{entity_id}",
        headers={"Authorization": f"Bearer {token()}", "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=5) as r:
        return json.load(r)

def number(entity_id):
    try:
        return float(state(entity_id)["state"])
    except Exception:
        return None

def text_state(entity_id):
    try:
        return state(entity_id)["state"]
    except Exception:
        return "unknown"

def dew_point(t, rh):
    a, b = 17.62, 243.12
    g = (a * t / (b + t)) + math.log(rh / 100.0)
    return b * g / (a - g)

def surface_rh(td, tw):
    a, b = 17.62, 243.12
    return 100.0 * math.exp((a * td / (b + td)) - (a * tw / (b + tw)))

def risk(rh):
    if rh >= 90: return "KRITISCH"
    if rh >= 80: return "HOCH"
    if rh >= 70: return "ERHOEHT"
    return "NIEDRIG"

class Since:
    def __init__(self):
        self.values = {}

    def seconds(self, key, active, now):
        if not active:
            self.values.pop(key, None)
            return 0
        self.values.setdefault(key, now)
        return int(now - self.values[key])

timers = Since()
flex_available = False

print("INS MyHome Control 0.1.3 starting | mode=SHADOW", flush=True)

while True:
    try:
        now = time.monotonic()
        t = number(ENTITIES["room_temp"])
        rh = number(ENTITIES["room_rh"])
        corner = number(ENTITIES["wall_corner"])
        center = number(ENTITIES["wall_center"])
        grid = number(ENTITIES["grid_power"])
        ac_thor = number(ENTITIES["ac_thor_power"])

        if None in (t, rh, corner, center):
            print("climate | waiting for valid bedroom sensors", flush=True)
        else:
            td = dew_point(t, rh)
            crh = surface_rh(td, corner)
            mrh = surface_rh(td, center)
            worst = max(crh, mrh)
            level = risk(worst)

            grid_export = max(0.0, -grid) if grid is not None else 0.0
            ac_thor_flex = max(0.0, ac_thor) if ac_thor is not None else 0.0
            flexible_power = grid_export + ac_thor_flex

            elevated_s = timers.seconds("elevated", worst >= 70, now)
            high_s = timers.seconds("high", worst >= 80, now)
            critical_s = timers.seconds("critical", worst >= 90, now)

            flex_on_s = timers.seconds("flex_on", flexible_power >= FLEX_ON_W, now)
            if flex_available:
                if flexible_power < FLEX_OFF_W:
                    flex_available = False
            elif flex_on_s >= FLEX_CONFIRM_S:
                flex_available = True

            if worst >= 90 and critical_s >= CRITICAL_CONFIRM_S:
                recommendation = "BEIDE"
                reason = f"kritische Oberflaechenfeuchte {worst:.1f}% seit {critical_s//60} min"
            elif worst >= 80 and high_s >= HIGH_CONFIRM_S:
                recommendation = "GRUPPE_1"
                reason = f"hohe Oberflaechenfeuchte {worst:.1f}% seit {high_s//60} min; Schutzbedarf unabhaengig von Energiepool"
            elif worst >= 70 and elevated_s >= ELEVATED_CONFIRM_S and flex_available:
                recommendation = "GRUPPE_1"
                reason = (
                    f"erhoehte Oberflaechenfeuchte {worst:.1f}% seit {elevated_s//60} min; "
                    f"flexibler PV-Pool {flexible_power:.0f}W "
                    f"(Netzexport {grid_export:.0f}W + AC-THOR {ac_thor_flex:.0f}W)"
                )
            else:
                recommendation = "HOLD"
                if worst < 70:
                    reason = f"Oberflaechenfeuchte {worst:.1f}% unkritisch"
                elif worst < 80:
                    reason = (
                        f"Oberflaechenfeuchte {worst:.1f}% seit {elevated_s//60} min erhoeht; "
                        f"flexibler PV-Pool {flexible_power:.0f}W, "
                        f"flex_ready={str(flex_available).lower()}; Praeventivheizen ab 20 min + Energie-Freigabe"
                    )
                else:
                    reason = f"Oberflaechenfeuchte {worst:.1f}% hoch; Zeitbedingung noch nicht erreicht"

            dry1 = text_state(ENTITIES["dry_1"])
            dry2 = text_state(ENTITIES["dry_2"])

            print(
                f"energy pool | grid_export={grid_export:.0f}W ac_thor={ac_thor_flex:.0f}W "
                f"flexible={flexible_power:.0f}W flex_ready={str(flex_available).lower()} flex_for={flex_on_s//60}m",
                flush=True,
            )
            print(
                f"bedroom north wall | room={t:.1f}C rh={rh:.1f}% dew={td:.1f}C "
                f"corner={corner:.1f}C/{crh:.1f}% center={center:.1f}C/{mrh:.1f}% "
                f"risk={level} elevated_for={elevated_s//60}m high_for={high_s//60}m critical_for={critical_s//60}m "
                f"dry1={dry1} dry2={dry2}",
                flush=True,
            )
            print(
                f"bedroom mold shadow | recommendation={recommendation} | reason={reason}",
                flush=True,
            )
    except Exception as exc:
        print(f"ERROR | {type(exc).__name__}: {exc}", flush=True)

    time.sleep(30)
