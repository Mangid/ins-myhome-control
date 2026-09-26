# INS MyHome Control

Private Home Assistant app for this home.

## V0.1.2 — Flexible PV energy pool

The bedroom mould-protection SHADOW logic now considers both:
- actual grid export from `sensor.em540_leistung`
- current AC-THOR power from `sensor.my_pv_ac_thor_9s_leistung`

The initial flexible energy pool is:

`grid export + AC-THOR power`

This reflects the fact that AC-THOR is a flexible surplus consumer: a small load such as Schimmel-DRY can use part of that PV energy while AC-THOR yields the corresponding power.

The app logs the pool separately and uses it for preventive heating decisions.

Safety/protection logic remains independent of PV availability at high/critical surface humidity.

This version remains **SHADOW only** and does not switch the Schimmel-DRY groups.
