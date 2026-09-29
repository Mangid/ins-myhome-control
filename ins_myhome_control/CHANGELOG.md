# Changelog

## 0.6.0
- Add standalone FUTUS Extension Mix Modbus TCP reader
- Read T3-T6 via Waveshare gateway 10.0.0.86:502, Unit-ID 20
- Never treat failed FUTUS reads as fresh temperature values

## 0.5.1
- Remove obsolete shadow actuator log lines in active mode
- Keep active actuator power feedback and bedroom protection runtime visible

## 0.5.0
- Activate bedroom mould-dry switching through Home Assistant
- Verify both Shelly actuator states with measured power feedback
- Preserve 120-minute minimum runtime and <72% / 20-minute release logic
- Add actuator settling and feedback error diagnostics

## 0.2.0
- Add Home Assistant ingress GUI
- Add room cards for all configured rooms with temperature/humidity
- Calculate dew point and absolute humidity per room
- Add room-climate mould screening
- Use measured surface humidity for bedroom north wall
