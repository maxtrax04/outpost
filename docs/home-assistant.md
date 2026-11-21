# Home Assistant

Outpost works with [Home Assistant](https://www.home-assistant.io) in two ways, and they can be combined:

- **[The add-on](#the-add-on)** runs Outpost inside Home Assistant (Home Assistant OS or Supervised), with
  an Outpost panel in the sidebar.
- **[Show the dashboard](#show-the-dashboard)** on a Home Assistant dashboard, with a Webpage card.
- **[Use the readings](#use-the-readings)** in Home Assistant, from Outpost's `weather.json`, as sensors and as
  a weather entity for automations, history graphs, and the built-in weather cards.

The examples use `http://outpost.local:8088` for Outpost and `http://homeassistant.local:8123` for Home
Assistant. Use your own addresses. They were checked with Home Assistant 2026.11.

## The add-on

The add-on (experimental) runs Outpost in Home Assistant itself, from the same image as the Docker setup:

1. Go to **Settings > Apps > Install app** (add-ons are called apps since Home Assistant 2026.2), open
   the menu (⋮) in the top-right corner, choose **Repositories**, and add
   `https://github.com/maxtrax04/outpost-addon` (or `https://github.com/maxtrax04/outpost-addon#beta` for
   beta versions).
2. Install **Outpost** and start it. Open it with **Open web UI** on its page, or turn on **Show in
   sidebar** there for an **Outpost** item in the sidebar.
3. For the map, turn on **Map** in its options and set **Contact** (OpenStreetMap's tiles need it).
4. To show your own sensors on the dashboard, list their entity IDs under **Sensors** in its options, one
   per line (see [Sensors](../README.md#sensors)). The add-on reads them from Home Assistant itself.

It uses Home Assistant's home location, name, time zone, and units unless you set others in its options.
Each option is one of Outpost's [settings](../README.md#settings) (`map_zoom` is `OUTPOST_MAP_ZOOM`, and so
on). Your own themes go in the add-on's configuration folder, under `themes/`.

The sidebar panel is for people logged in to Home Assistant. For a wall tablet, give the add-on a port on
its **Network** settings and open that port on the tablet; then the rest of this page works with that
address too. The add-on's [documentation](https://github.com/maxtrax04/outpost/blob/main/homeassistant/outpost/DOCS.md)
has the details.

## Show the dashboard

### 1. Allow Home Assistant to frame Outpost

Outpost's security headers allow only Outpost itself to show the dashboard in a frame, so by default a
Webpage card stays blank. List the address you open Home Assistant at in `OUTPOST_FRAME_ANCESTORS`,
exactly as the browser shows it (scheme, host, and port), and restart Outpost:

```env
OUTPOST_FRAME_ANCESTORS=http://homeassistant.local:8123
```

List every address you use, separated by commas, such as a local one and a remote one:
`OUTPOST_FRAME_ANCESTORS=http://homeassistant.local:8123,https://ha.example.com`. See
[SECURITY.md](../SECURITY.md#security-headers).

### 2. Add a Webpage card

Edit a dashboard, add a **Webpage** card, and enter Outpost's address. In YAML:

```yaml
type: iframe
url: http://outpost.local:8088/?theme=modern-dark
aspect_ratio: "16:9"
```

- `aspect_ratio` sets the card's height (`16:9`, or a percentage of its width such as `75%`). Add
  `fit=on` to the address (`?theme=modern-dark&fit=on`) to fit the whole dashboard into the card.
- The address takes the same options as any screen: `theme`, `effects=reduced`, `clock=24`, and `fit`.
  See the [README](../README.md#themes).
- For a whole page instead of a card, add a dashboard of the **Webpage** type (Settings, Dashboards, Add
  dashboard) with the same address.

### If the card stays blank

- **Home Assistant on HTTPS, Outpost on HTTP:** browsers block an `http://` page inside an `https://` one,
  and Home Assistant says so too. This is the usual case when you open Home Assistant remotely. Serve
  Outpost over HTTPS as well, for example behind the same reverse proxy, and use its `https://` address
  in the card.
- **The address is not in `OUTPOST_FRAME_ANCESTORS`:** the browser's developer console shows a
  `frame-ancestors` error. Check the scheme and port, and that Outpost was restarted.
- **A reverse proxy adds its own `X-Frame-Options` or `Content-Security-Policy`:** browsers apply both, so
  the proxy's header can block the frame even when Outpost allows it.

## Use the readings

Home Assistant's [RESTful integration](https://www.home-assistant.io/integrations/rest/) reads
`http://outpost.local:8088/data/weather.json`. Every field is described in
[data-format.md](data-format.md).

Home Assistant reads only the file Outpost already wrote, so polling it often does not send any extra
requests to the weather services. Outpost updates the file every `OUTPOST_UPDATE_INTERVAL` seconds
(60 by default), and a `scan_interval` of 60 matches it.

The examples below go in `configuration.yaml` (or a file it includes). Restart Home Assistant after adding
them. The units are imperial. With `OUTPOST_UNITS=metric`, change them as shown in the
[unit table](#units). Home Assistant converts temperatures and speeds to your own unit system.

### Sensors

```yaml
rest:
  - resource: http://outpost.local:8088/data/weather.json
    scan_interval: 60
    sensor:
      - name: Outpost weather
        unique_id: outpost_weather
        # The state is the icon name (sunny, rain, ...); the readings and forecast are attributes
        value_template: "{{ value_json.current.icon }}"
        availability: "{{ value_json.schema_version == 1 and value_json.status != 'error' }}"
        json_attributes:
          - status
          - current
          - forecast
          - units
          - sources
          - generated_at
      - name: Outpost temperature
        unique_id: outpost_temperature
        value_template: "{{ value_json.current.temperature }}"
        availability: "{{ value_json.current.temperature is number }}"
        unit_of_measurement: "°F"
        device_class: temperature
        state_class: measurement
      - name: Outpost humidity
        unique_id: outpost_humidity
        value_template: "{{ value_json.current.humidity }}"
        availability: "{{ value_json.current.humidity is number }}"
        unit_of_measurement: "%"
        device_class: humidity
        state_class: measurement
      - name: Outpost wind speed
        unique_id: outpost_wind_speed
        value_template: "{{ value_json.current.wind_speed }}"
        availability: "{{ value_json.current.wind_speed is number }}"
        unit_of_measurement: "mph"
        device_class: wind_speed
        state_class: measurement
      - name: Outpost wind direction
        unique_id: outpost_wind_direction
        # Not available when the wind is calm
        value_template: "{{ value_json.current.wind_direction }}"
        availability: "{{ value_json.current.wind_direction is number }}"
        unit_of_measurement: "°"
        device_class: wind_direction
        state_class: measurement_angle
      - name: Outpost pressure
        unique_id: outpost_pressure
        value_template: "{{ value_json.current.pressure }}"
        availability: "{{ value_json.current.pressure is number }}"
        unit_of_measurement: "inHg"
        device_class: atmospheric_pressure
        state_class: measurement
      - name: Outpost alerts
        unique_id: outpost_alerts
        # The number of active alerts; the alerts themselves are an attribute
        value_template: "{{ value_json.alerts | count }}"
        json_attributes:
          - alerts
    binary_sensor:
      - name: Outpost severe alert
        unique_id: outpost_severe_alert
        value_template: >-
          {{ value_json.alerts | selectattr('severity', 'in', ['severe', 'extreme']) | list | count > 0 }}
        device_class: safety
      - name: Outpost data problem
        unique_id: outpost_data_problem
        # On when the last update failed and the readings are old, or there are none
        value_template: "{{ value_json.status != 'ok' }}"
        device_class: problem
```

Add more readings the same way: `feels_like` and `dew_point` (temperature), `wind_gust` (wind speed, not
available when there are no gusts), `uv_index` (no unit), and `visibility` (`mi`, `device_class: distance`).

Notes:

- **Missing readings.** A reading the weather source doesn't have is `null` in `weather.json`. The
  `availability` lines make those sensors "unavailable" instead of showing a wrong 0.
- **Old readings.** When Outpost can't reach the weather service, it keeps the last good readings and sets
  `status` to `degraded`, so the sensors keep their last values. The *data problem* sensor turns on then.
  `generated_at` (on the *Outpost weather* sensor) says when they were fetched.
- **Alerts.** An empty list can mean no alerts, or that the source has none for your area: check
  `sources.alerts` on the *Outpost weather* sensor (`null` means there is no alerts source). Severity is
  `extreme`, `severe`, `moderate`, `minor`, or `unknown`.
- **Format changes.** `schema_version` changes only for a change that breaks readers. The first sensor's
  `availability` checks it, so after such a change the sensor shows "unavailable" instead of wrong values.

### Weather entity

A [template weather entity](https://www.home-assistant.io/integrations/weather.template/) turns those
readings into a `weather.outpost` entity, which the built-in weather forecast card shows, with the daily
forecast. It reads the *Outpost weather* sensor above.

```yaml
template:
  - weather:
      - name: Outpost
        unique_id: outpost_weather_entity
        variables:
          reading: "{{ state_attr('sensor.outpost_weather', 'current') or {} }}"
          # Outpost's icons as Home Assistant's weather conditions
          conditions:
            sunny: sunny
            clear-night: clear-night
            partly-cloudy: partlycloudy
            partly-cloudy-night: partlycloudy
            cloudy: cloudy
            fog: fog
            drizzle: rainy
            rain: rainy
            sleet: snowy-rainy
            snow: snowy
            storm: lightning-rainy
            wind: windy
        availability: "{{ has_value('sensor.outpost_weather') }}"
        condition: "{{ conditions.get(states('sensor.outpost_weather'), 'exceptional') }}"
        temperature: "{{ reading.temperature }}"
        apparent_temperature: "{{ reading.feels_like }}"
        dew_point: "{{ reading.dew_point }}"
        humidity: "{{ reading.humidity }}"
        pressure: "{{ reading.pressure }}"
        wind_speed: "{{ reading.wind_speed }}"
        wind_gust_speed: "{{ reading.wind_gust }}"
        wind_bearing: "{{ reading.wind_direction }}"
        visibility: "{{ reading.visibility }}"
        uv_index: "{{ reading.uv_index }}"
        temperature_unit: "°F"
        pressure_unit: "inHg"
        wind_speed_unit: "mph"
        visibility_unit: "mi"
        attribution: >-
          {{ (state_attr('sensor.outpost_weather', 'sources') or {}).get('weather', {}).get('name', '') }}
        forecast_daily: >-
          {% set ns = namespace(days=[]) %}
          {% for day in state_attr('sensor.outpost_weather', 'forecast') or [] %}
            {% set ns.days = ns.days + [{
              'datetime': day.day,
              'condition': conditions.get(day.icon, 'exceptional'),
              'temperature': day.high,
              'templow': day.low,
              'precipitation_probability': day.precipitation_chance,
              'uv_index': day.uv_index,
            }] %}
          {% endfor %}
          {{ ns.days }}
```

The attribution credits the weather source, as Open-Meteo and MET Norway require.

### Units

With `OUTPOST_UNITS=metric`, use these units in the sensors and the weather entity. `weather.json` lists
them in its `units` block.

| Reading | Imperial | Metric |
| :--- | :--- | :--- |
| Temperature, feels like, dew point | `°F` | `°C` |
| Wind speed, gusts | `mph` | `km/h` |
| Pressure | `inHg` | `hPa` |
| Visibility | `mi` | `km` |

Humidity is always `%`, and wind direction always `°`.

## Coming later

A custom integration, so Outpost's readings show up in Home Assistant without the YAML above, is being
considered ([#100](https://github.com/maxtrax04/outpost/issues/100)).
