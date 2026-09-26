# INS MyHome Control

Private Home Assistant app for this home.

## V0.1 — Bedroom north wall
The first release runs in **SHADOW mode**. It reads the existing Home Assistant sensors and logs:

- bedroom temperature and relative humidity
- dew point
- north-wall temperature at the cold left corner
- north-wall temperature in the centre
- calculated relative humidity at both wall surfaces
- mould-risk level
- real PV surplus from the EM540

The two Schimmel-DRY switches are known to the project, but V0.1 does **not** switch them automatically.

### Current entities
- `sensor.schlafzimmer_thip_schlafzimmer_temperatur`
- `sensor.schlafzimmer_thip_schlafzimmer_rel_luftfeuchte`
- `sensor.schlafzimmer_shellypm_nordwand_schlafzimmer_temperatur`
- `sensor.schlafzimmer_shellypm_nordwand_schlafzimmer_temperatur_2`
- `sensor.em540_leistung`
- `switch.infrarot_schlafzimmer_2`
- `switch.schlafzimmer_schimmeldry_schlafzimmer`
