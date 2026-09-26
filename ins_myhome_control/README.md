# INS MyHome Control

Private Home Assistant app for this home.

## V0.1.1 — Bedroom north wall SHADOW decision logic

Reads the bedroom climate, both north-wall surface temperatures and the EM540 grid power.

It calculates:
- dew point
- surface relative humidity at corner and centre
- mould-risk level
- real PV surplus
- duration of elevated/high/critical conditions
- a SHADOW recommendation: `HOLD`, `GRUPPE_1` or `BEIDE`
- a readable reason for every recommendation

Initial conservative logic:
- below 70% surface RH: no heating demand
- 70–80%: preventive Group 1 only after sustained elevated conditions and confirmed PV surplus
- 80–90%: Group 1 after sustained high surface humidity, independent of PV
- 90% or more: both groups after a short confirmation period
- PV surplus is considered available after at least 300 W for 5 minutes and released below 100 W

This version remains **SHADOW only**. It reads the Schimmel-DRY switch states but does not operate them.
