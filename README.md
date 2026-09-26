# INS MyHome Control

Private Home Assistant app for my own home.

## V0.1
The first module observes the bedroom north wall in SHADOW mode:
- room temperature and humidity
- wall temperature at the cold left corner and wall centre
- dew point
- calculated surface relative humidity
- mould-risk status
- PV surplus from the EM540

V0.1 does not switch the Schimmel-DRY heaters automatically.

## Home Assistant installation
Add this repository to **Settings → Apps → App Store → Repositories**:

https://github.com/Mangid/ins-myhome-control

Then install **INS MyHome Control** and start it. Check the app log for the first bedroom north-wall measurements.
