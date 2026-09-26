# INS MyHome Control

Private Home Assistant control project for my own home.

## V0.1
The first module observes the north wall in the bedroom:
- room temperature and humidity
- wall temperature at the cold corner and wall centre
- dew point
- calculated surface relative humidity
- mould-risk status
- PV surplus from the EM540

V0.1 is observation/shadow only. It does **not** switch the Schimmel-DRY heaters automatically yet.

## Installation
Install as a custom Home Assistant integration (for example through HACS as a custom repository), restart Home Assistant, then add **INS MyHome Control** under Settings → Devices & services.

## Current default entities
These defaults match the current home installation and can be changed in the integration setup:
- Room temperature: `sensor.schlafzimmer_thip_schlafzimmer_temperatur`
- Room humidity: `sensor.schlafzimmer_thip_schlafzimmer_rel_luftfeuchte`
- Cold corner wall temperature: `sensor.schlafzimmer_shellypm_nordwand_schlafzimmer_temperatur`
- Wall centre temperature: `sensor.schlafzimmer_shellypm_nordwand_schlafzimmer_temperatur_2`
- Grid power: `sensor.em540_leistung`
