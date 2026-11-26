<p align="center"><img src="docs/images/logo-banner.svg" alt="Outpost logo: a riveted stencil plate reading OUTPOST" width="480"></p>

# Outpost

[![CI](https://github.com/maxtrax04/outpost/actions/workflows/ci.yml/badge.svg)](https://github.com/maxtrax04/outpost/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/maxtrax04/outpost)](https://github.com/maxtrax04/outpost/releases/latest)
[![License: MIT](https://img.shields.io/github/license/maxtrax04/outpost)](LICENSE)

A self-hosted dashboard platform for weather, alerts, sensors, power monitoring, and telemetry, with themeable HUD-style displays.

> **Status:** early development (pre-1.0). The dashboard and container work with a built-in mock source and live Open-Meteo, National Weather Service, MET Norway, Pirate Weather, and OpenWeatherMap data. More providers are in progress. Expect breaking changes until 1.0.

<!-- TODO (public beta): add a hero screenshot here, e.g.
![Outpost dashboard](docs/images/dashboard.png)
-->

## Features

- Single-container deployment: one Docker image, one port, one data volume
- Live conditions, 5-day forecast, and alerts on a retro terminal-style HUD
- Normalized weather data format, so the display doesn't care which provider supplied it
- Built-in health check (including stale-data detection)
- Warning banner when data is old, degraded, or unavailable
- Works with Home Assistant: an add-on (experimental), a Webpage card for the dashboard, sensors and a weather entity from its data ([how](docs/home-assistant.md)), and your Home Assistant sensors and home power on the dashboard ([Sensors](#sensors), [Power](#power)), or straight from an MQTT broker ([MQTT](#mqtt))
- Themes: seven built in (from green-phosphor terminals to a 1950s television and black-on-white for ePaper), more from the [community](https://github.com/maxtrax04/outpost-themes), or your own, with no rebuild

## Quick start

Requires Docker and Docker Compose.

```bash
git clone https://github.com/maxtrax04/outpost.git
cd outpost
cp .env.example .env      # then edit .env (location, units, provider)
docker compose up -d --build
```

Open `http://localhost:8088`.

To view logs: `docker logs -f outpost`
To stop: `docker compose down`

## Run the published image

To skip building, replace the `build:` section of your compose file with the image:

```yaml
services:
  outpost:
    image: ghcr.io/maxtrax04/outpost:latest
    container_name: outpost
    ports:
      - "8088:80"
    env_file:
      - .env
    volumes:
      - ./data:/data
    restart: unless-stopped
```

Or with plain Docker:

```
docker run -d --name outpost -p 8088:80 --env-file .env -v ./data:/data ghcr.io/maxtrax04/outpost:latest
```

Images are built for amd64 (PCs, unRAID) and arm64 (Raspberry Pi). Use a version tag such as `0.4.0` to stay on a specific release, or `edge` to try the latest changes from `main`.

## Configuration

All settings are environment variables, set in `.env` (Compose) or in your container template.

| Variable | Default | Description |
|---|---|---|
| `OUTPOST_PROVIDER` | `mock` | Weather data source. See [Weather providers](#weather-providers). |
| `OUTPOST_PIRATEWEATHER_API_KEY` | *(empty)* | Your free [Pirate Weather](https://pirateweather.net) API key, for `pirateweather`, or for `auto` to use Pirate Weather outside the Nordic countries and the US (and as a fallback there). Keep it private; it is only sent to Pirate Weather. |
| `OUTPOST_OPENWEATHERMAP_API_KEY` | *(empty)* | Your [OpenWeatherMap](https://openweathermap.org) API key with a "One Call by Call" subscription, for `openweathermap`. Only home uses it. Keep it private; it is only sent to OpenWeatherMap. See [OpenWeatherMap](#openweathermap). |
| `OUTPOST_ALERTS_PROVIDER` | `auto` | Where official alerts come from: `auto` (the weather provider's own; else NWS in the US; else MET Norway in Norway; else OpenWeatherMap when the weather is from it; else Pirate Weather when you have a key), `nws`, `metno`, `pirateweather`, `openweathermap`, or `none`. See [Alerts](#alerts). |
| `OUTPOST_THEME` | `retro-crt` | Dashboard look. See [Themes](#themes). |
| `OUTPOST_THEME_SWITCHER` | `true` | Show the on-screen button for the panel with the location search, themes, and display options. Set `false` for a kiosk display. |
| `OUTPOST_COMMUNITY_THEMES` | (empty) | Community themes to download when the container starts, as `username/theme` separated by commas. See [Community themes](#community-themes). |
| `OUTPOST_COMMUNITY_THEMES_REF` | `main` | Which version of the community themes to download: a branch, tag, or commit. |
| `OUTPOST_EFFECTS` | `full` | `reduced` turns off scanlines, glow, and animation for everyone. See [Reduced effects](#reduced-effects). |
| `OUTPOST_EFFECTS_TOGGLE` | `true` | Show the "Reduced effects" checkbox in the theme panel. Set `false` so viewers cannot change `OUTPOST_EFFECTS`. |
| `OUTPOST_AUTO_DIM` | `true` | Dim the display at night. See [Day/night dimming](#daynight-dimming). |
| `OUTPOST_DIM_LEVEL` | `0.35` | Night brightness, from `0.05` (very dark) to `1` (no dimming). |
| `OUTPOST_DIM_MODE` | `sun` | `sun` follows sunset and sunrise; `schedule` uses fixed times. |
| `OUTPOST_DIM_START` / `OUTPOST_DIM_END` | `22:00` / `06:00` | Night window for `schedule` mode (24-hour `HH:MM`). |
| `OUTPOST_CLOCK` | `auto` | `12` shows times like 1:05 PM, `24` like 13:05, on every theme. `auto` follows the viewing browser's language, not the device's 12/24-hour clock setting (browsers do not share it), so a browser in US English shows 12-hour times. Each screen can also choose with the "24-hour clock" checkbox in the theme panel (saved in that browser), or `?clock=12` / `?clock=24` in the address. |
| `OUTPOST_CLOCK_TOGGLE` | `true` | Show the "24-hour clock" checkbox in the theme panel. Set `false` so viewers cannot change `OUTPOST_CLOCK`. |
| `OUTPOST_SUBTITLE` | *(empty)* | Optional line under the title. Empty hides it; `{date}` and `{time}` show the current date and time. |
| `OUTPOST_HOURLY` | `true` | The hourly forecast at the top of the forecast panel: the next hours with their temperature and chance of rain. `false` hides it. |
| `OUTPOST_AIR_QUALITY` | `true` | Air quality and pollen on the dashboard and in `weather.json`, from the Copernicus Atmosphere Monitoring Service's forecasts through Open-Meteo. `false` turns it off. See [Air quality](#air-quality). |
| `OUTPOST_AIR_QUALITY_INDEX` | `auto` | `us` (US AQI) or `european` (European Air Quality Index); `auto` uses the US AQI in the US and its territories and the European one everywhere else. |
| `OUTPOST_ALERTS_ALWAYS_SHOW` | `false` | `false` hides the Alerts panel when there are none; `true` always shows it. See [Alerts](#alerts). |
| `OUTPOST_MOCK_ALERTS` | `false` | With the `mock` provider, `true` always includes sample alerts (one of each severity), for trying how alerts look. See [Alerts](#alerts). |
| `OUTPOST_LOCATION_NAME` | `Goodsprings, NV` | Name shown at the top of the dashboard. |
| `OUTPOST_LATITUDE` | `35.8319` | Latitude in decimal degrees. |
| `OUTPOST_LONGITUDE` | `-115.4328` | Longitude in decimal degrees. |
| `OUTPOST_LOCATION_SEARCH` | `true` | Whether screens may show places other than home. See [Other places](#other-places). |
| `OUTPOST_LOCATION_LIMIT` | `30` | Weather fetches an hour for places other than home, all of them together (0 or more). See [Other places](#other-places). |
| `OUTPOST_LOCATION_PIRATEWEATHER` | `true` | Whether other places may use the Pirate Weather key, only from the quota home won't need before the monthly reset. `false` keeps it for home. |
| `OUTPOST_MAP` | `false` | Show a map of the place shown, drawn from OpenStreetMap. Needs `OUTPOST_CONTACT` with the default tile server. See [Map](#map). |
| `OUTPOST_MAP_ZOOM` | `7` | How close the map is: 4 (a large region) to 12 (a town). |
| `OUTPOST_MAP_TILES` | *(OpenStreetMap)* | Another server for the map's vector tiles, such as `https://tiles.example.org/{z}/{x}/{y}.mvt`. It must use the Shortbread schema. |
| `OUTPOST_MAP_RADAR` | `true` | Rain radar on the map: NOAA in the US, RainViewer elsewhere. See [Map](#map). |
| `OUTPOST_MAP_RADAR_LOOP` | `false` | Play the past 2 hours of radar as a loop instead of showing the latest frame (never on ePaper or with reduced effects). |
| `OUTPOST_SENSORS` | *(empty)* | Home Assistant entities or MQTT topics for the sensor panel, separated by commas, such as `sensor.living_room_temperature, Garage=binary_sensor.garage_door, Shed=mqtt:shed/temperature`. See [Sensors](#sensors) and [MQTT](#mqtt). |
| `OUTPOST_POWER_HOME` | *(empty)* | Home Assistant entity (or `mqtt:` topic) with the home's power use, for the power panel. See [Power](#power). |
| `OUTPOST_POWER_SOLAR` | *(empty)* | Entity with solar production. |
| `OUTPOST_POWER_GRID` | *(empty)* | Entity with grid power, positive when importing and negative when exporting. |
| `OUTPOST_POWER_GRID_INVERT` | `false` | `true` for a grid meter that counts exports as positive. |
| `OUTPOST_POWER_BATTERY` | *(empty)* | Entity with the battery's charge in percent. |
| `OUTPOST_SENSORS_INTERVAL` | `10` | Seconds between sensor and power readings from Home Assistant (at least 5). MQTT readings arrive when they change. |
| `OUTPOST_HA_URL` | *(empty)* | Your Home Assistant, such as `http://homeassistant.local:8123`, for the sensors and power. Not needed in the add-on. |
| `OUTPOST_HA_TOKEN` | *(empty)* | A long-lived access token for `OUTPOST_HA_URL`. Keep it private; it is only sent to Home Assistant. Not needed in the add-on. |
| `OUTPOST_MQTT_HOST` | *(empty)* | Your MQTT broker, such as `mqtt.local` or `192.168.1.20`, for `mqtt:` readings. See [MQTT](#mqtt). The add-on uses the Mosquitto broker add-on when this is empty. |
| `OUTPOST_MQTT_PORT` | `1883` | The broker's port (`8883` by default with TLS). |
| `OUTPOST_MQTT_USERNAME` | *(empty)* | The broker login, if it needs one. |
| `OUTPOST_MQTT_PASSWORD` | *(empty)* | The broker password. Keep it private; it is only sent to the broker. |
| `OUTPOST_MQTT_TLS` | `false` | `true` to connect with TLS. The broker's certificate must be valid for `OUTPOST_MQTT_HOST`. |
| `OUTPOST_UNITS` | `imperial` | `imperial` (°F, mph, inHg, miles) or `metric` (°C, km/h, hPa, km), for the dashboard and `weather.json`. |
| `OUTPOST_UPDATE_INTERVAL` | `60` | Seconds between data updates (at least 60). Each weather service is still asked no more often than it allows; see [Request limits](#request-limits). |
| `OUTPOST_CONTACT` | *(empty)* | Your email address or website, so weather services can reach you. Recommended for `nws`, `metno`, and `auto` (and NWS alerts). It is sent in the User-Agent header, after the project page that Outpost always includes. |
| `OUTPOST_USER_AGENT` | *(empty)* | Advanced: replaces the whole User-Agent (normally `Outpost/<version> (<contact>; +https://github.com/maxtrax04/outpost)`). |
| `OUTPOST_FRAME_ANCESTORS` | *(empty)* | Comma-separated list of sites allowed to show Outpost in a frame, such as `http://homeassistant.local:8123` for a Home Assistant webpage card. Empty allows only Outpost itself. See [SECURITY.md](SECURITY.md#security-headers). |
| `OUTPOST_WEB_PORT` | `8088` | Host port for the web UI (Compose only). |

The defaults point at Goodsprings, NV. Set your own latitude and longitude to see your local weather.

## Weather providers

| Provider | `OUTPOST_PROVIDER` | API key | Status |
|---|---|---|---|
| Mock (test data) | `mock` | No | Available |
| [Open-Meteo](https://open-meteo.com) | `openmeteo` | No | Available (recommended default) |
| [National Weather Service](https://www.weather.gov/documentation/services-web-api) | `nws` | No | Available (US only, includes alerts) |
| Auto | `auto` | No | Available (MET Norway in the Nordic countries, NWS in the US, elsewhere Pirate Weather if you have a key, otherwise Open-Meteo) |
| [MET Norway](https://api.met.no) | `metno` | No | Available (worldwide, best in the Nordic countries) |
| [Pirate Weather](https://pirateweather.net) | `pirateweather` | Yes (free) | Available (worldwide) |
| [OpenWeatherMap](https://openweathermap.org) | `openweathermap` | Yes (1,000 calls a day free, then billed) | Available (worldwide; never chosen by `auto`) |

### How `auto` chooses

| Your location | Weather from | Filled in from | Alerts (with `OUTPOST_ALERTS_PROVIDER=auto`) |
|---|---|---|---|
| Norway, Sweden, Finland, Denmark, Iceland, the Faroe Islands, Svalbard, Jan Mayen | MET Norway (if it fails: Pirate Weather with a key, then Open-Meteo once the data is stale) | Open-Meteo (visibility, later UV) | MET Norway in Norway; elsewhere Pirate Weather with a key, else none (NWS is not asked) |
| The United States and its territories | National Weather Service (if it fails: Pirate Weather with a key, then Open-Meteo once the data is stale) | Open-Meteo (UV, missing station readings) | National Weather Service |
| Everywhere else, with `OUTPOST_PIRATEWEATHER_API_KEY` set | Pirate Weather (Open-Meteo if it fails) | Open-Meteo, for anything missing | Pirate Weather |
| Everywhere else, without a key | Open-Meteo | (nothing missing) | None |

The Nordic check is done from your coordinates alone; the US check is the National Weather Service answering that it covers them. To always use one provider, set `OUTPOST_PROVIDER` to it.

The National Weather Service asks every client to identify itself, so set `OUTPOST_CONTACT` to an email address or website (Outpost warns at startup if it is missing). NWS does not publish a UV index, so with `nws` alone that field shows `--`. With `auto`, Outpost uses MET Norway in Norway, Sweden, Finland, Denmark, Iceland, the Faroe Islands, Svalbard, and Jan Mayen, where its forecast is at its best; the National Weather Service in the US; and everywhere else Pirate Weather if `OUTPOST_PIRATEWEATHER_API_KEY` is set, otherwise Open-Meteo. When MET Norway or NWS fails, Pirate Weather takes over at once if you have a key. Otherwise the last good data stays on screen (marked degraded) during a short outage, and once it is stale (three missed updates, at least 5 minutes) Open-Meteo takes over until MET Norway or NWS answers again. The Nordic check uses rough areas around those countries, worked out from your coordinates without asking any service, so near a border set `OUTPOST_PROVIDER` yourself if it picks the wrong one. Anything MET Norway or NWS leaves empty (such as visibility from MET Norway, or UV index and any reading a station is missing from NWS) is filled in from Open-Meteo, and the footer credits both sources. MET Norway requires every request to say what is asking (Outpost always sends its project page) and asks for a contact, so set `OUTPOST_CONTACT`; it also requires credit, which the footer gives; its data is shared under CC BY 4.0. Outpost downloads its forecast only when it has changed (MET Norway says when, about every 30 minutes), whatever `OUTPOST_UPDATE_INTERVAL` is. MET Norway sends a forecast rather than station readings, so "now" is the forecast for this hour, visibility shows `--`, and UV index is for a clear sky. Forecast days follow the container's `TZ` setting, so set it to your time zone. Pirate Weather needs a free API key from [pirateweather.net](https://pirateweather.net): sign up, subscribe the key to the forecast API, and set `OUTPOST_PIRATEWEATHER_API_KEY`. The free tier allows 10,000 calls a month, so Outpost asks at most every 10 minutes (about 4,300 a month) whatever `OUTPOST_UPDATE_INTERVAL` is, and if the quota still runs out it waits for the reset instead of asking again. Its alerts come with the forecast; see [Alerts](#alerts). Open-Meteo is free for non-commercial use and requires attribution, which the dashboard footer provides. Each provider has its own terms of use, attribution requirements, and rate limits. Please review them before running Outpost publicly or commercially.

### OpenWeatherMap

`OUTPOST_PROVIDER=openweathermap` uses OpenWeatherMap's One Call API 3.0. It needs an API key from
[openweathermap.org](https://openweathermap.org) with a "One Call by Call" subscription, set in
`OUTPOST_OPENWEATHERMAP_API_KEY`. That subscription gives 1,000 calls a day free, but needs a payment
card on file and bills calls beyond that, so `auto` never uses it. Outpost asks at most every 10 minutes
(at most 144 calls a day), never makes more than 900 calls in a day (counted from midnight UTC, as
OpenWeatherMap does), and only home uses the key: other places get Open-Meteo. To be sure nothing is
ever billed, also set a daily call limit of 1,000 in your OpenWeatherMap account. A refused key is tried
again after 10 minutes, and after "too many requests" Outpost waits an hour. The key has to go in the
request's address, so Outpost never logs that address or puts it in an error message.

Every reading comes from the one answer, including UV index, visibility, and precipitation amounts, so
nothing is filled in from Open-Meteo. Its alerts come in the same answer; see [Alerts](#alerts). The
footer credits OpenWeather, as its terms ask.

### Request limits

However short you set `OUTPOST_UPDATE_INTERVAL`, Outpost asks each weather service no more often than this. Between requests, it reuses the service's last answer. The updater lists these limits in its log when it starts.

| Service | Asked at most | Why |
|---|---|---|
| Open-Meteo | Every 15 minutes | Its current conditions change every 15 minutes, and the free tier allows fewer than 10,000 calls a day |
| National Weather Service | Forecast every 15 minutes, station readings every 5, alerts every minute | NWS asks clients to cache; forecasts change about hourly, alerts at any time |
| MET Norway (weather and warnings) | When MET Norway says the data may have changed (about every 30 minutes for the forecast) | Its terms require following the `Expires` header |
| Pirate Weather | Every 10 minutes | The free tier allows 10,000 calls a month |
| OpenWeatherMap | Every 10 minutes, and never more than 900 times a day | 1,000 calls a day are free; more are billed |
| Open-Meteo air quality | Once an hour, a few minutes after the hour | Its values are hourly |

`OUTPOST_UPDATE_INTERVAL` itself is at least 60 seconds; a shorter value is raised to 60, with a warning in the log. A shorter interval than these limits is still useful: alerts and fallbacks are checked on every update.

### Air quality

With `OUTPOST_AIR_QUALITY` on (the default), `weather.json` also has the air quality for the hour
under way: an air quality index, its band (such as "moderate"), fine particles (PM2.5 and PM10),
ozone, and other gases, and pollen in Europe during the season. It comes from the
[Copernicus Atmosphere Monitoring Service](https://atmosphere.copernicus.eu)'s forecasts through
[Open-Meteo's air quality API](https://open-meteo.com/en/docs/air-quality-api), which needs no key;
the footer credits both, as their terms (CC BY 4.0) require. These are model forecasts on a grid
(about 11 km in Europe, 45 km elsewhere), not readings from a monitor near you. The index is the US
AQI in the United States and its territories and the European Air Quality Index everywhere else
(told apart by the place's time zone, which the air quality service reports);
`OUTPOST_AIR_QUALITY_INDEX` picks one for every place. The dashboard shows it under the current
condition ("Air quality 34 Fair", with the index's name and, when there is some, the most pollen).
See "air_quality" in [docs/data-format.md](docs/data-format.md).

### Other places

Besides home, a screen can show the weather somewhere else. Open the panel with the button in the bottom-left corner, type a place name under LOCATION, and pick a result. Searches go to [Open-Meteo's geocoding service](https://open-meteo.com/en/docs/geocoding-api) (through Outpost, which keeps each search for a day and sends at most one a second). The chosen place and the places chosen before are kept in that browser only, never on the server. Choose Home to go back, or `x` to forget a place.

To pin one screen to a place, add it to the address: `http://outpost.local:8088/?lat=41.5&lon=-101.25&name=Cinder%20Flats`. That screen then shows that place whatever is chosen in the panel.

Outpost fetches the weather for that screen through its own API (`/api/weather?lat=..&lon=..&name=..`), so the screen still talks only to Outpost. The night dimming, sunrise, and sunset follow the place shown. Because anyone who can open the dashboard can ask for other places, Outpost limits what that costs:

- Coordinates are rounded to 2 decimals (about 1 km), so nearby screens share one fetch.
- A place is fetched only while a screen shows it, and at most every 15 minutes (or `OUTPOST_UPDATE_INTERVAL`, if longer). A place nobody has looked at for an hour is forgotten. Other places are kept only in memory: not in `weather.json`, on disk, or in the log.
- `OUTPOST_LOCATION_LIMIT` (30 by default) caps the weather fetches an hour for all other places together. When it is used up, a place already shown gets its last data again, and a new one is refused until the hour has passed. Home is never limited.
- With a Pirate Weather key, other places use it only while Pirate Weather reports calls to spare after what home needs until the monthly reset, plus 10%. Otherwise they use Open-Meteo (and, outside the US and Norway, have no alerts). `OUTPOST_LOCATION_PIRATEWEATHER=false` keeps the key for home.
- The web server allows each address 5 API requests a second.

`OUTPOST_LOCATION_SEARCH=false` turns other places off: the search leaves the panel, and pinned addresses are refused too, since anyone can edit an address. `OUTPOST_THEME_SWITCHER=false` removes the panel, search included, from every screen. If Outpost can be reached from the internet, turn it off or put Outpost behind a reverse proxy with a login.

### My location

On a phone or laptop, **Use my location** in the panel asks the browser where the device is, once, and shows the weather there as "My location". It is saved with the other places; tap the button again to update it, since Outpost does not follow the device around. If the browser refuses (permission denied, no position found, or it took too long), the panel says why and the search still works.

Browsers share a location only with HTTPS pages (and `http://localhost`), so on a plain `http://outpost.local:8088` address the button says "(needs HTTPS)". To use it, put Outpost behind a reverse proxy with a certificate. Outpost needs nothing special for this: its paths are relative and the API is under `/api/`. Some ways:

- **Caddy**, which gets a certificate on its own:

  ```
  outpost.example.com {
      reverse_proxy 192.168.1.20:8088
  }
  ```

  For a name that only exists on your home network, use Caddy's DNS challenge, or `tls internal` (then each device has to trust Caddy's local certificate authority).
- **Tailscale**: `tailscale serve --bg 8088` on the machine running Outpost gives it an `https://<machine>.<tailnet>.ts.net` address for the devices on your tailnet.
- **A proxy you already run** (Nginx Proxy Manager, Traefik, SWAG on unRAID): add a host that points to port 8088, with a certificate.

Inside another page's frame, such as Home Assistant's Webpage card, browsers don't share a location; search for the place instead.

Privacy: the browser may ask your device's location service to work out the position. Outpost rounds it to 2 decimals (about 1 km) in the browser before it is stored or sent anywhere. From there it is treated like any searched place: kept in that browser, sent to Outpost and on to the weather services, and never logged or written to disk on the server.

## Map

Set `OUTPOST_MAP=true` for a map panel under the forecast, centered on the place shown (home, a searched place, or "my location") and marked with a ring. It is a fixed picture, not a map you pan, so it suits wall displays and ePaper too. Rain radar is drawn on top (see [Radar](#radar)).

The map is drawn from [OpenStreetMap](https://www.openstreetmap.org)'s vector tiles, in the active theme's colors and font: land, water, main roads, borders, and place names. Outpost fetches the tiles and keeps them for as long as the tile server says (it then checks for changes, which costs almost nothing), so screens never contact OpenStreetMap themselves. Only tiles a screen shows are fetched, at `OUTPOST_MAP_ZOOM` only.

OpenStreetMap asks a server that fetches and keeps its tiles for a way to reach its operator, so with the default tile server the map stays off until `OUTPOST_CONTACT` is set (Outpost says so at startup). Its tiles are free, and their [usage policy](https://operations.osmfoundation.org/policies/vector/) allows normal viewing like this. If you run your own tile server with the same Shortbread schema, point `OUTPOST_MAP_TILES` at it.

### Radar

With the map on, rain radar is drawn over it, with the time of the frame in the top-left corner (`OUTPOST_MAP_RADAR=false` leaves it off):

- **In the US** (the lower 48 states, Alaska, Hawaii, Guam, and Puerto Rico), it comes from NOAA's [MRMS](https://www.nssl.noaa.gov/projects/mrms/) radar mosaic, which is new every 2 minutes and works at every zoom.
- **Elsewhere**, from [RainViewer](https://www.rainviewer.com/), which is new every 10 minutes. Its free radar stops at zoom 7, so at a closer `OUTPOST_MAP_ZOOM` it is drawn larger and looks softer. RainViewer's free radar is for personal and educational use, which a home dashboard is.

Which one is used is worked out from the place's coordinates alone, with rough boxes, so a place close to the US border can get the other one. Outpost fetches the radar and keeps it, so screens never contact NOAA or RainViewer, and every screen showing the same area shares one copy.

The latest frame is shown, and it is updated every couple of minutes. `OUTPOST_MAP_RADAR_LOOP=true` plays the past 2 hours instead, a frame every 10 minutes. ePaper (the `ink` theme) and [reduced effects](#reduced-effects) always get the latest frame alone, since an animation would make an ePaper panel flash. On ePaper, each new frame is a redraw, every 2 to 10 minutes.

A theme can choose the map's colors with `--map-land`, `--map-water`, `--map-road`, `--map-border`, `--map-label`, `--map-halo`, and `--map-marker`; see [docs/themes.md](docs/themes.md#map-colors). Without them, the map follows the theme's own colors.

## Sensors

Outpost can show readings from [Home Assistant](https://www.home-assistant.io) beside the weather: indoor temperature, humidity, a door, the garage, anything Home Assistant has. List the entities in `OUTPOST_SENSORS`, separated by commas:

```bash
OUTPOST_SENSORS=sensor.living_room_temperature, sensor.living_room_humidity, Garage=binary_sensor.garage_door
OUTPOST_HA_URL=http://homeassistant.local:8123
OUTPOST_HA_TOKEN=your-long-lived-access-token
```

- **Names and units** come from Home Assistant. Put a label before `=` to show another name, and a unit in brackets after the entity to show another unit: `Attic=sensor.attic_temperature [°F]`. Outpost doesn't convert sensor readings (`OUTPOST_UNITS` is for the weather).
- **Numbers** under 100 show one decimal, larger ones none. Power over 1000 W shows in kW.
- **Doors, windows, and garage doors** read Open or Closed, motion and occupancy Detected or Clear, and other on/off sensors On or Off. Other text, like a lock's "locked", is shown as it is.
- **Missing readings** show `--`: an entity that is unavailable, or one that isn't in Home Assistant (the log says which). If Home Assistant can't be reached, the last readings stay for 15 minutes.
- **The token** is a long-lived access token from your Home Assistant profile (Security tab). It is only sent to Home Assistant, and never to a screen. In the [Home Assistant add-on](docs/home-assistant.md), Outpost reads Home Assistant on its own: list the entities under **Sensors** in its options, and leave the URL and token out.

Outpost reads each entity every `OUTPOST_SENSORS_INTERVAL` seconds (10 by default), and screens ask Outpost every 15 seconds. It only reads the entities you list, and it never changes anything in Home Assistant.

Anyone who can open the dashboard sees these readings. If Outpost can be reached from the internet without a login in front of it, don't list doors, locks, or who is home.

### Power

The power panel shows your home's energy at a glance: what the home uses, what solar makes, what goes to or comes from the grid, and the battery's charge. Give each part you have one Home Assistant entity; leave out the ones you don't have:

```bash
OUTPOST_POWER_HOME=sensor.house_power
OUTPOST_POWER_SOLAR=sensor.solar_power
OUTPOST_POWER_GRID=sensor.grid_power
OUTPOST_POWER_BATTERY=sensor.battery_level
```

- **Home** and **Solar** show the power now, in W or kW (from 1000 W).
- **Grid** reads Importing or Exporting under the amount. Positive means importing, Home Assistant's usual way. If your meter counts exports as positive, set `OUTPOST_POWER_GRID_INVERT=true`.
- **Battery** shows the charge in percent, with a bar (a dial in Field Station).
- A label before `=` replaces the name, as for sensors: `Roof=sensor.solar_power`.

Power uses the same Home Assistant connection (`OUTPOST_HA_URL` and `OUTPOST_HA_TOKEN`, or nothing in the add-on) and is read with the sensors, every `OUTPOST_SENSORS_INTERVAL` seconds. Any of the parts can come from MQTT instead (see below). On a wide screen, power and sensors sit side by side; on a landscape tablet, power goes under the forecast.

### MQTT

Without Home Assistant, or for a device that only talks MQTT (a Tasmota plug, a Zigbee2MQTT sensor, an ESP board), Outpost can read topics straight from your MQTT broker. Write `mqtt:` and the topic wherever an entity goes, in `OUTPOST_SENSORS` or a power part:

```bash
OUTPOST_SENSORS=Shed=mqtt:shed/temperature [°C], Garage=mqtt:zigbee2mqtt/garage_door#contact
OUTPOST_POWER_HOME=mqtt:tele/house_meter/SENSOR#ENERGY.Power [W]
OUTPOST_MQTT_HOST=mqtt.local
OUTPOST_MQTT_USERNAME=outpost
OUTPOST_MQTT_PASSWORD=your-broker-password
```

- **The message** is a number or text (`21.5`, `ON`), or JSON with the field named after `#`: `mqtt:zigbee2mqtt/shed#temperature` reads `{"temperature": 21.5, ...}`. A dot goes into a field inside another (`#ENERGY.Power`), and a number into a list (`#values.0`).
- **Names and units:** MQTT has none, so give a label before `=` and a unit in brackets. Without a label the tile shows the field or the last part of the topic.
- **On and off:** `ON`, `OFF`, `true`, and `false` read On or Off (JSON `true` and `false` too). `1` and `0` stay numbers.
- **Exact topics only:** no `+` or `#` wildcards, so the broker sends only what is listed. Retained messages show at once; other topics show `--` until their first message.
- **Missing:** a reading stays while the broker is connected, however long ago it changed. If the broker can't be reached for 15 minutes, its readings show `--`. Outpost connects again on its own, waiting longer each time (up to 5 minutes).
- **In the add-on**, with the [Mosquitto broker add-on](https://github.com/home-assistant/addons/tree/master/mosquitto) installed, Outpost gets the broker and a login from Home Assistant: nothing to set. To use another broker, set **MQTT broker** and its login in the options.

Outpost only subscribes: it never publishes, and the password is never logged or sent to a screen. MQTT and Home Assistant readings can be mixed in one list.

## Data and storage

The updater writes normalized weather data to `/data/weather.json` inside the container, and the web server serves it to the dashboard. Mount `/data` as a volume (Compose does this with `./data`) so data survives restarts.

You can read the same file from other tools:

```bash
curl http://localhost:8088/data/weather.json
```

Every field is described in [docs/data-format.md](docs/data-format.md), with a [JSON Schema](docs/schema/weather-v1.json). The file has a `schema_version`, which goes up only when a change would break a tool that reads it.



## Running on unRAID

A Community Apps template is planned. Until then, you can add the container manually once an image is published:

- **Port:** container `80` to a host port of your choice
- **Path:** container `/data` to `/mnt/user/appdata/outpost`
- **Path (optional, your own themes):** container `/config/themes` to `/mnt/user/appdata/outpost/themes`, access mode Read Only. Put each theme in its own folder there, for example `/mnt/user/appdata/outpost/themes/sonar/theme.css`, then restart the container. See [docs/themes.md](docs/themes.md#adding-themes-without-rebuilding).
- **Variables:** each `OUTPOST_*` setting from the table above

## Project layout

```
app/        Updater, health check, and provider modules (Python)
web/        Dashboard front end (HTML, CSS, JS)
assets/     Weather icons, app (home-screen) icons, the logo, and fonts
tests/      Automated tests and sample data
data/       Generated weather.json and config.json (runtime, not committed)
```

## Themes

Seven themes are included: `retro-crt` (default), `amber-terminal`, `command-center`, `modern-dark`, `field-station` (a steel instrument panel with dials), `atomic-broadcast` (a 1950s television set), and `ink` (black on white, for ePaper; see [ePaper displays](#epaper-displays)). Set `OUTPOST_THEME` to choose the default for everyone, or add `?theme=name` to the address to preview one. More themes are in the [community themes](#community-themes) repository.

Anyone viewing the dashboard can also pick a theme with the small button in the bottom-left corner (it is faint until you hover or tap it). The choice is remembered in that browser only, with a "Use server default" option to undo it. Set `OUTPOST_THEME_SWITCHER=false` to remove the button, for example on a wall display.

Themes are small CSS files, so making your own is easy. Mount a folder of your own themes at `/config/themes` to add them without rebuilding the image; [examples/themes/](examples/themes/) has one to start from. See [docs/themes.md](docs/themes.md).

<!-- TODO (public beta): add a screenshot of each theme here -->

### Community themes

More themes, made by Outpost users, are in the [outpost-themes](https://github.com/maxtrax04/outpost-themes) repository. Each is named after the person who made it, such as `maxtrax04/weather-desk`, and shows in the theme switcher by its name alone (with the username added only if two themes share a name).

List the ones you want, and Outpost downloads them when the container starts:

```
OUTPOST_COMMUNITY_THEMES=maxtrax04/weather-desk,maxtrax04/wristcomp
```

- They are downloaded once per start, not again while it runs, so restart the container to get updates. They are kept in your data volume, so after the first download they keep working with no internet. If a download fails, Outpost uses the copies it has, logs one warning, and carries on; nothing waits for it.
- Themes you take off the list are removed at the next start. A theme that builds on another theme by the same person (such as `maxtrax04/weather-desk-live` on `maxtrax04/weather-desk`) brings it along automatically.
- Use one with `OUTPOST_THEME=maxtrax04/weather-desk` or `?theme=maxtrax04/weather-desk`, like any other theme.
- `OUTPOST_COMMUNITY_THEMES_REF` picks a version of the repository (a branch, tag, or commit) instead of the latest.
- Themes are only CSS, fonts, and images, and Outpost's security headers stop them from running scripts or loading anything from other sites.

To use community themes with no internet at all, clone the repository and mount it as your custom themes folder instead: `- ./outpost-themes:/config/themes:ro`. Themes in it keep the same names. Your own themes can sit beside them.

### Reduced effects

Scanlines, glow, and animation can be turned off in every theme, which helps readability and slow wall tablets:

- **For everyone:** set `OUTPOST_EFFECTS=reduced`.
- **Automatically:** a device set to reduce motion (in its accessibility settings) gets reduced effects.
- **Per browser:** the "Reduced effects" checkbox in the theme panel turns them off or back on in that browser, and wins over the two above. "Use server default" forgets it. Set `OUTPOST_EFFECTS_TOGGLE=false` to remove the checkbox, so everyone gets `OUTPOST_EFFECTS`. The checkbox is in the theme panel, so `OUTPOST_THEME_SWITCHER=false` removes it too.
- **To preview:** add `?effects=reduced` (or `?effects=full`) to the address.

## Alerts

The Alerts panel lists active weather warnings. `OUTPOST_ALERTS_PROVIDER` picks where they come from:

- **`auto` (default):** from the weather provider, if it has alerts (`nws`, and `auto` inside the US). If it has none, as with Open-Meteo, Outpost asks the National Weather Service, which covers the US (including Alaska, Hawaii, and the territories). In Norway (including Svalbard and Jan Mayen), they come from MET Norway, which issues Norway's official warnings. Outside the US, if you have set `OUTPOST_PIRATEWEATHER_API_KEY`, alerts come from Pirate Weather. Otherwise the dashboard says alerts are not available rather than claiming there are none. This sends your coordinates to the National Weather Service as well, even outside the US (where it answers that it has no data, which Outpost then remembers for about 30 minutes), except in the Nordic countries, which Outpost recognizes by itself. Use `none` if you don't want that. Set `OUTPOST_CONTACT` too, since NWS asks for it.
- **`nws`:** always from the National Weather Service, whatever the weather provider. Outside the US there are none, and the log says so once.
- **`metno`:** always MET Norway's warnings (MetAlerts), the official ones for Norway, for land (not the gale warnings for sea areas). Outpost works out from your coordinates whether you are in Norway, since MET Norway has no warnings elsewhere; outside Norway there are none, and the log says so once.
- **`pirateweather`:** always from Pirate Weather (needs `OUTPOST_PIRATEWEATHER_API_KEY`). Pirate Weather passes on the official warnings that national weather services publish to the WMO's global alert hub (in Europe through MeteoAlarm), plus the National Weather Service's for the lower 48 US states. Which countries take part changes over time, and an empty list looks the same whether there are no alerts or your country isn't covered, so the dashboard then says "none reported by Pirate Weather" rather than "none". Alerts are in the language the weather service published them in. If you also get the weather from Pirate Weather, the alerts come in the same request and use none of your quota.
- **`openweathermap`:** always from OpenWeatherMap (needs `OUTPOST_OPENWEATHERMAP_API_KEY`; home only). With `auto` they are used when the weather comes from OpenWeatherMap too, outside the US and Norway, since they come in the same request. They are the official warnings that national weather services send OpenWeatherMap, which gives no severity, so Outpost works it out from the name ("Warning" is severe, "Watch" moderate, "Advisory" minor, and MeteoAlarm's red, orange, and yellow extreme, severe, and moderate). As with Pirate Weather, an empty list can also mean the country isn't covered, so the dashboard then says "none reported by OpenWeather".
- **`none`:** no alerts.

If the alerts lookup fails while the weather comes through, the dashboard keeps the last alerts it had and shows the degraded warning, so a failed check never looks like "no alerts". The footer names the alerts source when it differs from the weather source.

By default the panel is hidden when there is nothing to show, and a one-line note below the forecast says when alerts were last checked, for example `Alerts: none (checked 2:15 PM)`. Set `OUTPOST_ALERTS_ALWAYS_SHOW=true` to keep the panel visible. Severe and extreme alerts turn the panel red.

To see how alerts look without waiting for real weather, use `OUTPOST_PROVIDER=mock` with `OUTPOST_MOCK_ALERTS=true`: the dashboard then always shows three sample alerts, one each of severe, moderate, and minor.

The dashboard also shows today's sunrise and sunset (or "Midnight sun" / "Polar night" near the poles), calculated in the browser from your coordinates (no weather service needed). Times on the dashboard (sunrise and sunset, "Updated", and when alerts end) are shown as they are at the weather location, in the time zone the weather service reports (or the container's `TZ` setting for MET Norway). When the screen is in a different time zone, the zone is added, as in `4:12 PM GMT+1`, so it is clear whose time it is.

## Phones, tablets, and tall screens

The dashboard adapts to the screen. Tablets, wall displays, and wide screens get the whole dashboard on one screen without scrolling, in every built-in theme: a one-line header, and in landscape the current conditions and forecast on the left with the map and alerts on the right; in portrait the map takes the height left over. Everything is scaled to fill the screen. Phones get a compact layout that scrolls, with the forecast as one row per day. Notches and rounded corners are respected.

**Add it to your home screen** to open it like an app, without browser bars:

- **iPhone or iPad (Safari):** tap Share, then Add to Home Screen.
- **Android (Chrome):** open the menu, then Add to Home screen (or Install app).

Outpost provides the icon and settings for this. Note that browsers only offer a full "Install app" prompt over HTTPS; on a plain `http://` address on your home network, Add to Home Screen still works but creates a shortcut. The icon is a placeholder until Outpost gets its own logo.

### ePaper displays

ePaper screens use very little power, which suits a dashboard on the wall. Open the `ink` theme on that screen only by adding `?theme=ink` to its address (for example `http://outpost.local:8088/?theme=ink`), so your other screens keep their own theme.

- `ink` is pure black on white, so it suits black-and-white panels. Severe alerts are dark red, which a color panel shows in red and a black-and-white panel shows in black. Alert levels are also spelled out and shown by their borders, so they don't depend on color.
- It has no scanlines, glow, or animation, and no night dimming, since paper has no light to dim.
- It fits the whole dashboard on the screen without scrolling, down to 800 × 480 panels. On short screens each alert gets one line (its title and end time).
- Every change on the screen makes an ePaper panel redraw, which on many panels is a visible flash. To avoid extra redraws, don't put `{time}` in `OUTPOST_SUBTITLE` (it changes every minute). You can also set `OUTPOST_THEME_SWITCHER=false` if nobody will change the theme from that screen.
- Color ePaper also works with the other themes and [reduced effects](#reduced-effects), but their dark backgrounds and dim colors look muddy on most panels.

This needs a web browser on the device, such as an ePaper tablet. Panels that only download a picture to show (many microcontroller and e-reader setups) aren't supported.

## Day/night dimming

Outpost can dim itself at night so a wall-mounted display isn't glaring in a dark room. It is on by default.

- **`sun` mode (default):** brightness follows the sun's position at your latitude and longitude. The display fades down over about 30 minutes after sunset and back up around sunrise. No internet connection or weather service is needed for this.
- **`schedule` mode:** dims between `OUTPOST_DIM_START` and `OUTPOST_DIM_END` with a 30-minute fade. Times use the clock of the device showing the dashboard, so make sure its time zone is correct.
- **Preview:** add `?dim=night`, `?dim=day`, or `?dim=0.5` to the address to try a brightness without waiting for dark.

Dimming is done in the browser, so it doesn't change your display's backlight. It also helps reduce burn-in on OLED screens.

## Icons

Outpost ships an original, monochrome icon set (13 icons covering clear, cloudy, fog, drizzle, rain, sleet, snow, storm, wind, day and night variants, and an "unknown" fallback). Icons are plain SVGs in `assets/icons/` and are tinted with CSS, so themes can recolor them.

![Outpost icon set](docs/images/icon-set.png)

To add or change an icon, draw it on a 64x64 grid with a 3px stroke, square caps, and `currentColor`, then add its name to the `ICONS` list in `web/app.js`.

### Logo

The Outpost logo is an original stencil plate design in `assets/logo/`: `mark.svg` (the square "OP" plate), `wordmark.svg` (the plate reading OUTPOST, shown in the dashboard header), and `lockup.svg` (both together). Like the icons, they are one-color SVGs tinted with CSS, so each theme shows them in its own colors. A theme can show the plain text title instead (see `--title-logo` in [docs/themes.md](docs/themes.md#tokens)).

The favicon and home-screen icons in `assets/app/` are made from `mark.svg`. After changing the mark, rebuild them with `scripts/build-app-icons.js` (the command is at the top of the file); a test fails if the favicon no longer matches the mark.

## Development

Tests run automatically on every pull request (see `.github/workflows/ci.yml`). To run them yourself without installing anything, you only need Docker:

```
./scripts/test.sh          # Linux and macOS
.\scripts\test.ps1        # Windows PowerShell
```

Or, with Python 3.12+ and Node 22+ installed:

```
python -m unittest discover -s tests -b
node --test
```

Tests never call the network; weather responses are saved samples in `tests/fixtures/` with made-up locations.

## Roadmap

See [ROADMAP.md](ROADMAP.md) for where Outpost is going, and the [milestones](../../milestones) for the work in progress. Ideas are welcome as issues.

## Contributing

Issues and pull requests are welcome. Please read [CONTRIBUTING.md](CONTRIBUTING.md) first; it covers the workflow, privacy rules (never post your real location), and content rules. To report a security problem, see [SECURITY.md](SECURITY.md).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

Outpost is released under the [MIT License](LICENSE).

Weather data remains subject to each provider's own terms, and any third-party fonts or icons you add keep their own licenses.
