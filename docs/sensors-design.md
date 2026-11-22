# Sensors and power design note

Status: design for [#35](https://github.com/maxtrax04/outpost/issues/35), decided 2026-11-20 (Home
Assistant and MQTT, a sensor panel and a power panel, in 0.7.0). Step 1 (sensors from Home Assistant) is
built in 0.7.0-beta.13, step 2 (power) in 0.7.0-beta.14, and step 3 (MQTT) in 0.7.0-beta.15. The README's
"Sensors", "Power", and "MQTT" sections are the user guide.

## What

Two optional panels, off until something is listed for them:

- **Sensors:** readings you choose, such as indoor temperature, humidity, a door, or a garage, shown as
  tiles that look like the weather readings.
- **Power:** a home energy view with fixed roles: home use, solar, grid (importing or exporting), and
  battery.

The readings come from **Home Assistant** (any entity, so anything already in it: Zigbee, Z-Wave,
ESPHome, Shelly, utility meters) or straight from an **MQTT** broker, for setups without Home Assistant.

## Decisions

### Outpost's server reads the sources; screens ask Outpost

The screens never talk to Home Assistant or the broker. The Content-Security-Policy allows nothing
else, and the token must stay on the server. `outpost_server.py` gets a `Sensors` object that keeps
the latest value of each listed reading in memory, and a new endpoint, `GET /api/sensors`, returns
them. Nothing is written to `/data`, and `weather.json` doesn't change.

`/api/sensors` only ever returns what the settings list. Nothing in the request chooses an entity or
a topic, so the endpoint can't be used to read the rest of Home Assistant.

### Home Assistant: the REST API, polled

- **Add-on:** it uses the Supervisor token at `http://supervisor/core/api`, which the add-on already
  has (`homeassistant_api: true`, used for the home location). Nothing to set up.
- **Container:** `OUTPOST_HA_URL` (such as `http://homeassistant.local:8123`) and `OUTPOST_HA_TOKEN`
  (a long-lived access token from your Home Assistant profile). The token is secret: it isn't logged,
  and it's never sent to a screen.
- Every `OUTPOST_SENSORS_INTERVAL` seconds (default 10, at least 5), Outpost reads each listed entity
  with `GET /api/states/<entity_id>`. That's a few small local requests, at most 24 entities.
- Label, unit, and device class come from Home Assistant (`friendly_name`, `unit_of_measurement`,
  `device_class`) unless the setting gives a label.

Considered and not chosen: Home Assistant's WebSocket API would push changes as they happen, but it
needs a hand-written WebSocket client (no pip). Polling every 10 seconds is close enough for a wall
screen. It can be added later without changing the settings or `/api/sensors`.

### MQTT: a small subscribe-only client

- A hand-written MQTT 3.1.1 client (standard library `socket`, plus `ssl` for TLS) in
  `app/outpost_mqtt.py`, on its own thread in `outpost_server.py`. It does CONNECT (clean session),
  SUBSCRIBE at QoS 0, keep-alive pings (every 30 s; the connection is dropped after 90 s without a
  word from the broker), and reconnects with a growing delay (5 s, doubling up to 5 minutes). It never
  publishes. Messages over 256 KB are skipped as they arrive, so a large retained message can't use up
  memory or stop the rest.
- Only exact topics are subscribed: no `+` or `#` wildcards, so the broker sends only what's listed.
  Retained messages give a value right away.
- A payload is a number or text, or JSON with the field named after `#` in the source
  (`mqtt:home/garage/climate#temperature`). A dot goes into a field inside another (Tasmota's
  `#ENERGY.Power`) and a number into a list. JSON `true` and `false` read as on and off.
- Settings: `OUTPOST_MQTT_HOST`, `OUTPOST_MQTT_PORT` (1883, or 8883 with TLS), `OUTPOST_MQTT_USERNAME`,
  `OUTPOST_MQTT_PASSWORD` (secret), and `OUTPOST_MQTT_TLS` (default `false`).
- **Add-on:** it asks for the MQTT service (`services: ["mqtt:want"]`), so with the Mosquitto add-on
  installed, the host and login come from the Supervisor (`http://supervisor/services/mqtt`), with
  nothing to set up. `outpost_addon.py` asks only when an `mqtt:` reading is listed and the **MQTT
  broker** option is empty; that option, with its login, is for another broker.
- MQTT has no units or names, so the source can give a unit (see Settings).

### Listing readings

One compact list for the sensor panel, and one setting per power role. Each item is a *source*,
optionally with a label before `=` and a unit in brackets after it:

```
OUTPOST_SENSORS=sensor.living_room_temperature, Garage=binary_sensor.garage_door, Shed=mqtt:shed/climate#temperature [°F]
OUTPOST_POWER_HOME=sensor.house_power
OUTPOST_POWER_SOLAR=sensor.solar_power
OUTPOST_POWER_GRID=sensor.grid_power
OUTPOST_POWER_BATTERY=sensor.battery_level
```

- A source is a Home Assistant entity ID (`sensor.x`, `binary_sensor.x`, and so on) or `mqtt:<topic>`.
- Up to 24 sensor items, plus one per power role. A bad item is skipped and named in the log, and the
  rest still work.
- In the add-on, `sensors` is a list of these items (the Configuration tab shows one box per item), and
  the power roles are text boxes.

### Readings

- **Numbers** are shown with the unit they come with. Outpost doesn't convert them (`OUTPOST_UNITS` is
  for the weather). Values of 100 or more are rounded to a whole number, smaller ones to one decimal.
  Power in W of 1000 or more is shown in kW.
- **On/off** sensors use their device class: door, window, and garage door read Open or Closed, motion
  and occupancy read Detected or Clear, and the rest read On or Off. MQTT values `ON`/`OFF` and
  `true`/`false` count as on/off when the item has no unit. `1` and `0` stay numbers: a count or a level
  that happens to be 1 is more common than a switch that sends 1.
- **Missing:** Home Assistant's `unavailable` or `unknown`, an MQTT topic with no message yet, or a
  source that can't be reached. The tile shows `--` and is marked missing, like a missing weather
  reading. The last value is kept for 15 minutes when Home Assistant or the broker can't be reached, then
  marked missing. An MQTT reading stays while the broker is connected, however long ago it last changed:
  many devices send only on a change, so a door closed all day isn't missing.

### Power panel

Four roles, all optional, shown only when at least one is set:

- **Home:** use now.
- **Solar:** production now.
- **Grid:** positive is importing, negative is exporting (Home Assistant's usual sign). It shows the
  amount without a sign, with "Importing", "Exporting", or "Idle" under it (`data-direction`).
  `OUTPOST_POWER_GRID_INVERT=true` flips the sign for meters that count the other way.
- **Battery:** charge in percent (a unit of `%` is assumed when there is none), as a bar (`--value` and
  `data-gauge`, like the gauges, so Field Station gives it a dial and Atomic Broadcast its tuning bar).
- Each role shows its role name ("Home", "Solar", "Grid", "Battery") unless the setting gives a label.
  Anything but a number reads as missing.

A flow diagram (solar to home to grid, with moving dots) would look good, but it's more to theme and
animate. It can come later. The roles and `/api/sensors` stay the same.

### Dashboard and themes

- `web/sensors.js` reads `api/sensors` every 15 seconds while a panel is shown, and not at all when
  nothing is listed (`/api/status` says whether anything is). That's well under the API's limit of
  5 requests a second.
- `#sensorsPanel` (`data-panel="sensors"`) and `#powerPanel` (`data-panel="power"`) use the same
  `.detail-box` tiles as the weather readings. Every theme, including community themes, styles them
  with no changes. Each tile has `data-sensor-kind` (`number`, `binary`, `text`) and `data-device-class`,
  so a theme can style doors or power on its own.
- **Screen layout:** both panels are in `#homePanels`, power first, side by side when there is room. In
  landscape fitting the wrapper is `display: contents`: power goes under the forecast and the sensors
  under the map, which takes what height is left (a hidden panel's grid row has no height, so power
  needs no layouts of its own). Atomic Broadcast, with its alerts pinned outside the page, puts power
  under the map and the sensors beside the forecast. In portrait they go after the forecast, before the
  map. The tablet fit check runs with both panels shown. With every panel shown and a very long
  condition, Field Station can need more than the smallest scale on a 1024x768 tablet, and then
  scrolls.
- Sensors show the same values for every place a viewer picks: they're about home, not the place shown.

## Privacy and security

- Sensor values are home data. Anyone who can open the dashboard can see them, like the weather. The
  README will say not to list doors, locks, or presence when Outpost is reachable from the internet
  without a login in front of it.
- Tokens and passwords are never logged or sent to a screen. The log names sources and says whether
  they answer, without values.
- Outpost only reads: it never calls a Home Assistant service and never publishes to MQTT.

## Settings

| Setting | Default | Meaning |
| :--- | :--- | :--- |
| `OUTPOST_SENSORS` | *(empty)* | Readings for the sensor panel (see "Listing readings"). |
| `OUTPOST_POWER_HOME` | *(empty)* | Home power use. |
| `OUTPOST_POWER_SOLAR` | *(empty)* | Solar production. |
| `OUTPOST_POWER_GRID` | *(empty)* | Grid power, positive when importing. |
| `OUTPOST_POWER_GRID_INVERT` | `false` | Flip the grid sign. |
| `OUTPOST_POWER_BATTERY` | *(empty)* | Battery charge in percent. |
| `OUTPOST_SENSORS_INTERVAL` | `10` | Seconds between Home Assistant reads (at least 5). |
| `OUTPOST_HA_URL` | *(empty)* | Home Assistant address (not needed in the add-on). |
| `OUTPOST_HA_TOKEN` | *(empty)* | Long-lived access token (not needed in the add-on). |
| `OUTPOST_MQTT_HOST` | *(empty)* | MQTT broker (the add-on uses Mosquitto's when installed). |
| `OUTPOST_MQTT_PORT` | `1883` | Broker port. |
| `OUTPOST_MQTT_USERNAME` | *(empty)* | Broker login. |
| `OUTPOST_MQTT_PASSWORD` | *(empty)* | Broker password. |
| `OUTPOST_MQTT_TLS` | `false` | Connect with TLS. |

## Not in this work

- History or charts (today's solar, a temperature graph). Home Assistant keeps history better.
- Controls (switching a light from the dashboard). Outpost only reads.
- Other sources (InfluxDB, Prometheus, a JSON URL). The `Sensors` object takes sources, so one can be
  added later.

## Plan

Each step is its own PR and beta:

1. **Sensors from Home Assistant (beta.13):** this note, `Sensors` with the Home Assistant source,
   `/api/sensors`, the `OUTPOST_SENSORS` list, the add-on wiring, the sensor panel, the screen layout,
   and the fit check with the panel shown.
2. **Power (beta.14):** the power roles, the power panel, and the battery bar.
3. **MQTT (beta.15):** `outpost_mqtt.py`, the `mqtt:` sources, the MQTT settings, and the add-on's
   Mosquitto service.

Then 0.7.0, released 2026-11-21.
