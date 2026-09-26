from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Callable

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfPower, UnitOfTemperature
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event

from .const import (
    CONF_ROOM_TEMP, CONF_ROOM_HUMIDITY, CONF_WALL_CORNER_TEMP,
    CONF_WALL_CENTER_TEMP, CONF_GRID_POWER,
)

def _f(hass: HomeAssistant, entity_id: str):
    try:
        return float(hass.states.get(entity_id).state)
    except (AttributeError, TypeError, ValueError):
        return None

def dew_point(t: float, rh: float) -> float:
    a, b = 17.62, 243.12
    g = (a * t / (b + t)) + math.log(rh / 100.0)
    return b * g / (a - g)

def surface_rh(td: float, tw: float) -> float:
    a, b = 17.62, 243.12
    return 100.0 * math.exp((a * td / (b + td)) - (a * tw / (b + tw)))

def risk(rh: float) -> str:
    if rh >= 90: return "Kritisch"
    if rh >= 80: return "Hoch"
    if rh >= 70: return "Erhöht"
    return "Niedrig"

@dataclass(frozen=True)
class Desc:
    key: str
    name: str
    unit: str | None
    device_class: SensorDeviceClass | None
    calc: Callable

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities):
    c = entry.data
    source_ids = [c[CONF_ROOM_TEMP], c[CONF_ROOM_HUMIDITY], c[CONF_WALL_CORNER_TEMP],
                  c[CONF_WALL_CENTER_TEMP], c[CONF_GRID_POWER]]

    def values():
        t = _f(hass, c[CONF_ROOM_TEMP]); rh = _f(hass, c[CONF_ROOM_HUMIDITY])
        corner = _f(hass, c[CONF_WALL_CORNER_TEMP]); center = _f(hass, c[CONF_WALL_CENTER_TEMP])
        grid = _f(hass, c[CONF_GRID_POWER])
        td = dew_point(t, rh) if t is not None and rh is not None and 0 < rh <= 100 else None
        crh = surface_rh(td, corner) if td is not None and corner is not None else None
        mrh = surface_rh(td, center) if td is not None and center is not None else None
        return t, rh, corner, center, grid, td, crh, mrh

    descs = [
        Desc("dew_point", "Schlafzimmer Taupunkt", UnitOfTemperature.CELSIUS, SensorDeviceClass.TEMPERATURE,
             lambda v: round(v[5],1) if v[5] is not None else None),
        Desc("surface_rh_corner", "Nordwand Oberflächenfeuchte Ecke", PERCENTAGE, SensorDeviceClass.HUMIDITY,
             lambda v: round(v[6],1) if v[6] is not None else None),
        Desc("surface_rh_center", "Nordwand Oberflächenfeuchte Mitte", PERCENTAGE, SensorDeviceClass.HUMIDITY,
             lambda v: round(v[7],1) if v[7] is not None else None),
        Desc("mold_risk", "Schimmelrisiko Nordwand", None, None,
             lambda v: risk(max(x for x in [v[6],v[7]] if x is not None)) if any(x is not None for x in [v[6],v[7]]) else None),
        Desc("pv_surplus", "PV Überschuss MyHome", UnitOfPower.WATT, SensorDeviceClass.POWER,
             lambda v: round(max(0.0, -v[4]),0) if v[4] is not None else None),
    ]
    async_add_entities([MyHomeSensor(entry, d, values, source_ids) for d in descs])

class MyHomeSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry, desc, values_fn, source_ids):
        self._entry = entry
        self._desc = desc
        self._values_fn = values_fn
        self._source_ids = source_ids
        self._attr_unique_id = f"{entry.entry_id}_{desc.key}"
        self._attr_name = desc.name
        self._attr_native_unit_of_measurement = desc.unit
        self._attr_device_class = desc.device_class
        if desc.device_class in (SensorDeviceClass.TEMPERATURE, SensorDeviceClass.HUMIDITY, SensorDeviceClass.POWER):
            self._attr_state_class = SensorStateClass.MEASUREMENT

    @property
    def device_info(self):
        return {
            "identifiers": {("ins_myhome_control", self._entry.entry_id)},
            "name": "INS MyHome Control",
            "manufacturer": "INS",
            "model": "MyHome Control",
        }

    @property
    def native_value(self):
        return self._desc.calc(self._values_fn())

    async def async_added_to_hass(self):
        @callback
        def changed(event):
            self.async_write_ha_state()
        self.async_on_remove(async_track_state_change_event(self.hass, self._source_ids, changed))
