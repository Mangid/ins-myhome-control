import json
import math
import time
import urllib.request
import urllib.error

SUPERVISOR = "http://supervisor/core/api"
TOKEN_FILE = "/var/run/secrets/homeassistant"

ENTITIES = {
    "room_temp": "sensor.schlafzimmer_thip_schlafzimmer_temperatur",
    "room_rh": "sensor.schlafzimmer_thip_schlafzimmer_rel_luftfeuchte",
    "wall_corner": "sensor.schlafzimmer_shellypm_nordwand_schlafzimmer_temperatur",
    "wall_center": "sensor.schlafzimmer_shellypm_nordwand_schlafzimmer_temperatur_2",
    "grid_power": "sensor.em540_leistung",
    "dry_1": "switch.infrarot_schlafzimmer_2",
    "dry_2": "switch.schlafzimmer_schimmeldry_schlafzimmer",
}

def token():
    import os
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

print("INS MyHome Control 0.1.0 starting | mode=SHADOW", flush=True)

while True:
    try:
        t = number(ENTITIES["room_temp"])
        rh = number(ENTITIES["room_rh"])
        corner = number(ENTITIES["wall_corner"])
        center = number(ENTITIES["wall_center"])
        grid = number(ENTITIES["grid_power"])

        if None in (t, rh, corner, center):
            print("climate | waiting for valid bedroom sensors", flush=True)
        else:
            td = dew_point(t, rh)
            crh = surface_rh(td, corner)
            mrh = surface_rh(td, center)
            worst = max(crh, mrh)
            surplus = max(0.0, -grid) if grid is not None else None
            print(
                f"bedroom north wall | room={t:.1f}C rh={rh:.1f}% "
                f"dew={td:.1f}C corner={corner:.1f}C/{crh:.1f}% "
                f"center={center:.1f}C/{mrh:.1f}% risk={risk(worst)} "
                f"pv_surplus={surplus:.0f}W" if surplus is not None else
                f"bedroom north wall | room={t:.1f}C rh={rh:.1f}% "
                f"dew={td:.1f}C corner={corner:.1f}C/{crh:.1f}% "
                f"center={center:.1f}C/{mrh:.1f}% risk={risk(worst)}",
                flush=True,
            )
    except Exception as exc:
        print(f"ERROR | {type(exc).__name__}: {exc}", flush=True)
    time.sleep(30)
