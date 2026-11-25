# Changelog

All notable changes to Outpost are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Until 1.0, minor versions may include breaking changes.

## [Unreleased]

## [0.8.0-beta.6] - 2026-11-25

### Added

- Air quality on the dashboard (#88): under the current condition, "Air quality 34 Fair", then the index's name and, in Europe during the season, the two most plentiful kinds of pollen ("European AQI · Pollen: grass 49, birch 12"). It is hidden when there is none, or with `OUTPOST_AIR_QUALITY=false`. The footer credits the Copernicus Atmosphere Monitoring Service and Open-Meteo. Every built-in theme still fits a tablet with it shown. Themes can color it by band with `data-level` (0 to 5) or `data-category`, and get `--wx-air-quality`; see docs/themes.md.

### Changed

- `OUTPOST_AIR_QUALITY_INDEX=auto` (the default) now uses the US AQI only for places in the United States and its territories, and the European Air Quality Index everywhere else, including wherever that can't be told. It goes by the time zone the air quality service reports for the place, so places just across the border, such as Toronto or Tijuana, get the European index. In beta.5 every place outside Europe got the US AQI.

## [0.8.0-beta.5] - 2026-11-25

### Added

- Air quality and pollen in `weather.json` (#88): `air_quality` has an air quality index with its band (such as "moderate") and a level from 0 to 5, both the US AQI and the European Air Quality Index, PM2.5, PM10, ozone, nitrogen dioxide, sulphur dioxide, and carbon monoxide, and, in Europe during the season, alder, birch, grass, mugwort, olive, and ragweed pollen. It comes from the Copernicus Atmosphere Monitoring Service's forecasts through Open-Meteo's air quality API (no key), asked once an hour per place, and is credited in `sources.air_quality`. Other places get their own. The format stays version 1 (new fields, nothing renamed). See "air_quality" in docs/data-format.md. The dashboard shows it in a later beta.
- `OUTPOST_AIR_QUALITY` (default `true`) turns it off, and `OUTPOST_AIR_QUALITY_INDEX` picks the index: `auto` (the European one in Europe, the US AQI elsewhere), `us`, or `european`. Both are also Home Assistant add-on options.
- If the air quality lookup fails, the last readings stay and the file is marked degraded, as with alerts; the weather still updates.

## [0.8.0-beta.4] - 2026-11-24

### Added

- Alert start times (#87): each alert in `weather.json` has `onset`, when it starts, next to `expires`, from every alerts source: the National Weather Service (`onset`, or when it took effect), MET Norway's MetAlerts, and Pirate Weather. The format stays version 1 (a new field, nothing renamed).
- An alert that hasn't started yet says so on the dashboard: "From Nov 25, 6:00 AM until Nov 26, 6:00 PM" instead of only "Until ...", so a warning for tomorrow no longer looks as if it is in effect now. It still shows, and still turns the alerts panel red when serious. Themes can style it with `.alert-item[data-upcoming]`.

## [0.8.0-beta.3] - 2026-11-24

### Added

- Precipitation amounts (#86): how much rain or snow is expected, as water (snow melted), for each forecast day and each hour, in `weather.json` as `precipitation` in `forecast` and `hourly`, in inches or millimetres by `OUTPOST_UNITS` (the new `precipitation` label in `units`). Open-Meteo, MET Norway, and Pirate Weather supply it; the National Weather Service forecast has none, so with it the amounts come from Open-Meteo, in the same request that already fills in the UV index. The format stays version 1 (new fields, nothing renamed).
- The dashboard shows the amount after the chance of rain on each forecast day when some is expected ("Rain: 40% · 0.25 in"). Every built-in theme still fits a tablet. Themes get `--wx-amount` on each forecast card and can style `.forecast-amount`.
- docs/home-assistant.md: the `weather.outpost` entity gets the amounts in its daily and hourly forecasts (`precipitation_unit`).

## [0.8.0-beta.2] - 2026-11-22

### Added

- The hourly forecast on the dashboard (#85): one box at the top of the forecast panel, between the current conditions and the days, with the next hours (as many as fit on one line, up to 12), each with its time ("Now" for the hour under way), weather icon, temperature, and chance of rain or snow. Times follow the dashboard's 12- or 24-hour clock and the location's time zone. It is on by default; `OUTPOST_HOURLY=false` hides it. Every built-in theme still fits a tablet with it shown.
- Themes can style it: `#hourlyPanel` and `.hourly-hour`, with `data-icon` and `data-now` (see docs/themes.md).

## [0.8.0-beta.1] - 2026-11-22

### Added

- An hourly forecast in `weather.json` (#85): `hourly` lists the next 24 hours, from the hour under way, each with its time, temperature, condition and icon, chance of rain or snow, and wind. It comes from every weather source: Open-Meteo, MET Norway, and Pirate Weather send it with the rest, and the National Weather Service's separate hourly forecast is asked for as often as the daily one. The format stays version 1 (a new field, nothing renamed). See "hourly" in docs/data-format.md. The dashboard shows it in a later beta.
- docs/home-assistant.md: the `weather.outpost` entity gets the hourly forecast too, for Home Assistant's hourly forecast card.

## [0.7.0] - 2026-11-21

Platform: each screen can show another place (location search, "Use my location", and pinned screens), a map with rain radar, a Home Assistant add-on, sensor and power panels with readings from Home Assistant or MQTT, and every built-in theme fitted to a tablet or wall display without scrolling. **Other places are allowed by default**; see "Upgrading from 0.6.0" below.

### Added

- Location search (#30). Under LOCATION in the panel (the button in the bottom-left corner), type a place name and pick a result, and that screen shows the weather there. Home and the places chosen before stay in the list, kept in that browser only; `x` forgets one. Night dimming, sunrise, and sunset follow the place shown. Searches go to Open-Meteo's geocoding service, which needs no key; each search is kept for a day, at most one a second is sent, and what was searched for is never logged.
- "Use my location" in the panel (#31). On a phone or laptop it asks the browser once where the device is, then shows the weather there as "My location", saved with the other places; tap it again to update it. The position is rounded to about 1 km in the browser before it is stored or sent. When the browser refuses, the panel says why. Browsers share a location only with HTTPS pages; README "My location" covers HTTPS with Caddy, Tailscale, or a reverse proxy you already run.
- `?lat=..&lon=..&name=..` in the address pins one screen to a place, for example a wall screen showing a second home.
- Limits that protect your weather services' quotas (see "Other places" in the README): `OUTPOST_LOCATION_SEARCH` (default `true`) allows other places, `OUTPOST_LOCATION_LIMIT` (default 30) caps the weather fetches an hour for all other places together, and `OUTPOST_LOCATION_PIRATEWEATHER` (default `true`) lets other places use the Pirate Weather key, but only from the quota home won't need before the monthly reset. Coordinates are rounded to about 1 km, so nearby screens share one fetch; each place is fetched at most every 15 minutes, and only while a screen shows it. When the hourly limit is used up, a place already shown gets its last data again and a new one is refused, and the screen says why. Other places are kept only in memory, never written to disk, and never logged.
- Outpost's API (docs/api-design.md): `/api/weather` (home, or another place with `?lat=..&lon=..`, in the `weather.json` format), `/api/places`, `/api/radar`, `/api/sensors`, and `/api/status`. The web server allows each address 5 API requests a second.
- A map panel (#32, docs/map-design.md). `OUTPOST_MAP=true` shows a fixed map under the forecast, centered on the place shown and marked with a ring, drawn from OpenStreetMap's vector tiles in the theme's colors and font: land, water, main roads, borders, and place names. It needs no map library and no WebGL, so it also works on slow tablets and ePaper. `OUTPOST_MAP_ZOOM` sets the zoom (4 to 12, default 7). With OpenStreetMap's tiles the map needs `OUTPOST_CONTACT`, as their usage policy asks; `OUTPOST_MAP_TILES` points it at another tile server with the same Shortbread schema.
- Rain radar on the map, on whenever the map is (`OUTPOST_MAP_RADAR=false` turns it off). In the US (the lower 48 states, Alaska, Hawaii, Guam, and Puerto Rico) it comes from NOAA's MRMS radar mosaic, new every 2 minutes; elsewhere from RainViewer, new every 10 minutes, which stops at zoom 7 and is drawn larger above that. The frame's time is in the top-left corner. `OUTPOST_MAP_RADAR_LOOP=true` plays the past 2 hours instead of the latest frame (never on ePaper or with reduced effects).
- Outpost fetches map tiles and radar itself and keeps them, so screens never contact OpenStreetMap, NOAA, or RainViewer, and screens showing the same area share one copy. Tile and radar requests are not logged.
- A Home Assistant add-on (#34, experimental), in `homeassistant/` and published to [maxtrax04/outpost-addon](https://github.com/maxtrax04/outpost-addon) by the release workflow: beta versions on its `beta` branch, released versions on `main`. It runs the same image and adds an Outpost panel to Home Assistant's sidebar for every user. It uses Home Assistant's home location, name, time zone, and units unless they are set in its options, and each option is one of Outpost's settings; switches start at Outpost's defaults. A wall tablet that isn't logged in to Home Assistant can open Outpost on a port of its own, which is off until you set one, and custom themes go in the add-on's configuration folder. Its log lists the options Outpost received at each start (switches as on or off, choices by value, keys and other text only as "set").
- `docs/home-assistant.md`: the add-on, showing the dashboard in a Webpage card (and what to do when it stays blank), and ready-to-paste configuration that reads `weather.json` as Home Assistant sensors and as a `weather.outpost` entity with the daily forecast.
- A sensor panel (#35, docs/sensors-design.md): list readings in `OUTPOST_SENSORS`, such as `sensor.living_room_temperature, Garage=binary_sensor.garage_door`. Names and units come from Home Assistant, or from a label before `=` and a unit in brackets. Doors read Open or Closed, motion Detected or Clear, and other on/off sensors On or Off. Home Assistant is reached at `OUTPOST_HA_URL` with a long-lived access token in `OUTPOST_HA_TOKEN`, every `OUTPOST_SENSORS_INTERVAL` seconds (default 10); the add-on needs neither. Outpost reads only what is listed and never changes anything. See "Sensors" in the README.
- A power panel: home use, solar, grid, and battery, one reading each in `OUTPOST_POWER_HOME`, `OUTPOST_POWER_SOLAR`, `OUTPOST_POWER_GRID`, and `OUTPOST_POWER_BATTERY` (each optional). The grid reads Importing or Exporting under the amount (positive is importing; `OUTPOST_POWER_GRID_INVERT=true` flips it), and the battery's charge shows as a bar, or on the theme's own gauge in Field Station and Atomic Broadcast. See "Power" in the README.
- Sensor and power readings straight from an MQTT broker: write `mqtt:<topic>` wherever an entity goes (`Shed=mqtt:shed/temperature [°C]`), with `#field` for a field of a JSON message (`mqtt:zigbee2mqtt/garage#contact`, `#ENERGY.Power` for one inside another). Set the broker with `OUTPOST_MQTT_HOST`, `OUTPOST_MQTT_PORT`, `OUTPOST_MQTT_USERNAME`, `OUTPOST_MQTT_PASSWORD`, and `OUTPOST_MQTT_TLS`; the add-on uses the Mosquitto broker add-on with nothing to set. Outpost subscribes only to the exact topics listed, never publishes, and keeps a reading while the broker is connected. MQTT and Home Assistant readings can be mixed. See "MQTT" in the README.
- For theme authors (docs/themes.md): map colors (`--map-land`, `--map-water`, `--map-road`, `--map-border`, `--map-label`, `--map-halo`, `--map-marker`; without them the map follows the theme's colors), sensor tiles (`.detail-box.sensor` with `data-sensor-kind`, `data-device-class`, `data-state`, and `data-missing`), power tiles (`.detail-box.power` with `data-power-role`, `data-direction`, and, on the battery, `--value` and `data-gauge`), and the screen layout ("Fit to screen").
- The README shows the latest release and the license as badges beside the CI status.

### Changed

- Every built-in theme fits a tablet or wall display without scrolling, in landscape and portrait, with the map, alerts, sensors, and power shown. While the page is fitted to the screen it has a screen layout: a one-line header; in landscape, the current conditions, forecast, and power on the left and the map, sensors, and alerts on the right (Atomic Broadcast, whose alerts run along the bottom, puts power under the map); in portrait, the map takes the height left over. Phones (narrower than 600 px) still scroll.
- The dashboard reads the weather from the API, and from `data/weather.json` when the page is served without it. While another place's weather loads, the readings are blanked, so one place's readings never show under another's name.
- The panel button also appears when there is only one theme, if location search is on. `OUTPOST_THEME_SWITCHER=false` still removes it, search included.
- One process runs both the update loop and the API (`app/outpost_server.py`, in place of `outpost_updater.py --loop`), so home and other places share each weather service's request limits. Each place's last good data is kept separately, so one place's outage never shows another's readings.
- The web server's access log no longer records query strings or the Referer header, since a pinned screen's address carries a place.

### Upgrading from 0.6.0

- **Other places are on by default.** Anyone who can open the dashboard can look at the weather elsewhere, up to `OUTPOST_LOCATION_LIMIT` fetches an hour (default 30). Set `OUTPOST_LOCATION_SEARCH=false` to show only home; pinned `?lat=&lon=` addresses are then refused.
- If you start the container with your own command that runs `outpost_updater.py --loop`, run `outpost_server.py` instead. `--loop` still updates `weather.json`, but without the API there is no location search, radar, or sensors. With the image's own start script nothing changes.
- `weather.json` is unchanged (`schema_version` 1), so tools that read it need no changes.

## [0.6.0] - 2026-11-14

Data model and providers: a versioned `weather.json` format, metric units, two new weather providers (MET Norway and Pirate Weather), alerts from a separate source (the National Weather Service with Open-Meteo, MET Norway's warnings for Norway, and Pirate Weather's worldwide alerts), smarter automatic provider choice, times in the location's time zone, wind gusts, wind direction, dew point, and limits on how often each weather service is asked. **If another tool reads `weather.json`**, its field names changed; see "Upgrading from 0.5.0" below.

### Added

- Metric units: `OUTPOST_UNITS=metric` shows °C, km/h, hPa, and km on the dashboard and in `weather.json`. The setting was accepted before but did nothing. Each reading is converted and rounded once, from the weather source's own numbers, and theme gauges point to the same place in either system. An unknown value logs a warning and uses imperial.
- MET Norway weather: `OUTPOST_PROVIDER=metno` uses MET Norway's forecast, which covers the whole world and is especially good in the Nordic countries. MET Norway asks for `OUTPOST_CONTACT`, and the footer credits it. MET Norway sends a forecast rather than station readings, so the current conditions are the forecast for this hour, visibility shows `--`, and the UV index is for a clear sky. Forecast days follow the container's `TZ` setting.
- Pirate Weather: `OUTPOST_PROVIDER=pirateweather` uses [Pirate Weather](https://pirateweather.net), which covers the whole world, with a free API key in `OUTPOST_PIRATEWEATHER_API_KEY`. The free tier allows 10,000 calls a month, so Outpost asks at most every 10 minutes (about 4,300 calls a month), and if the quota still runs out it waits for the reset Pirate Weather reports. When Pirate Weather refuses the key, Outpost waits 10 minutes before trying again (a newly subscribed key can take up to 20 minutes to start working). The key is sent only to Pirate Weather, in a request header, and never appears in an address, the log, or Outpost's files.
- `OUTPOST_ALERTS_PROVIDER` picks where official alerts come from, separately from the weather: `auto` (default), `nws`, `metno`, `pirateweather`, or `none`. `weather.json` names the alerts source in `sources.alerts`, and the dashboard footer credits it. See "Alerts" in the README. With `auto`, alerts come from the weather provider when it has them, and otherwise from:
  - the National Weather Service in the US (including Alaska, Hawaii, and the territories);
  - MET Norway's warnings (MetAlerts) in Norway, including Svalbard and Jan Mayen. Only warnings for land are used, not gale warnings for sea areas. Levels follow MET Norway's colours (yellow is moderate, orange severe, red extreme), and each warning shows its area and description in English, its end time, and a link to MET Norway's page about it;
  - Pirate Weather elsewhere, with a key. It passes on the official warnings that national weather services publish to the WMO's global alert hub, including Europe's through MeteoAlarm. Not every country takes part, so an empty list is shown as "none reported by Pirate Weather". Alerts are in the language they were published in, repeats are removed, and severities are standardized.
- Wind gusts: the Wind reading gets a second line, such as "Gusts 18 mph", when the gusts are stronger than the wind (`current.wind_gust`). Gusts are never filled in from another source.
- Wind direction: the Wind reading shows where the wind comes from, such as "SW 12 mph", and says "Calm" when there is no wind (`current.wind_direction`, in degrees).
- Dew point: a "Dew point 54°F" line in the Humidity box (`current.dew_point`).
- When the readings are from: `current.observed_at` in `weather.json` (a station's observation time, or the forecast hour for MET Norway). When the readings are over an hour old, such as from a station that reports rarely, the Updated box adds "Reading from 2:40 PM".
- `timezone` in `weather.json`: the location's time zone, such as `Europe/Oslo`, from the weather service, or else the container's `TZ` setting (MET Norway, mock data).
- `docs/data-format.md` describes every field of `weather.json`, for anyone reading it from another tool such as Home Assistant, and `docs/schema/weather-v1.json` is the same as a JSON Schema. `weather.json` links to it in a `$schema` field, so editors such as VS Code check the file and describe each field.
- For theme authors (see `docs/themes.md`): `--wx-gust`, `--wx-dew-point`, and `--wx-wind-direction` (a fraction of a turn, for rotating an arrow), and a shared `.reading-note` class for the second lines in the reading boxes (gusts, dew point, reading time).

### Changed

- **Breaking for anything that reads `weather.json`:** the file has a versioned format (`"schema_version": 1`), and no field name includes a unit. `temperature_f` is now `temperature`, `feels_like_f` is `feels_like`, `wind_mph` is `wind_speed`, `pressure_inhg` is `pressure`, `visibility_miles` is `visibility`, `humidity_percent` is `humidity`, and in the forecast `high_f`, `low_f`, and `precipitation_percent` are `high`, `low`, and `precipitation_chance`. The units are listed once in a `units` block (for example `"temperature": "°F"`), and the dashboard shows them from there.
- **Breaking for anything that reads `weather.json`:** where the data came from is in a `sources` block, with `weather`, `alerts` (`null` when there are no official alerts), and `fill` (the second source used for missing readings, and which ones). It replaces `source`, `provider_setting`, `filled_fields`, and `alerts_supported`. `provider` is now always the `OUTPOST_PROVIDER` setting (such as `auto`); the provider actually used is `sources.weather.id`.
- `OUTPOST_PROVIDER=auto` picks the regional specialists first: MET Norway in Norway, Sweden, Finland, Denmark, Iceland, the Faroe Islands, Svalbard, and Jan Mayen (with anything it lacks, such as visibility, filled in from Open-Meteo), and the National Weather Service in the US. Everywhere else it uses Pirate Weather with a key, and Open-Meteo without one (or if Pirate Weather fails). The region is worked out from the coordinates, without asking any service. When MET Norway or the National Weather Service fails, Pirate Weather takes over at once if you have a key; otherwise the last good data stays on screen, marked degraded, during a short outage, and once it is stale (three missed updates, at least 5 minutes) Open-Meteo takes over until the specialist answers again.
- **With Open-Meteo in the US, the dashboard now shows official alerts** from the National Weather Service, where before it said alerts were not available. This sends your coordinates to the National Weather Service too; set `OUTPOST_ALERTS_PROVIDER=none` to go back to no alerts, and set `OUTPOST_CONTACT`, since NWS asks for it. When alerts come from a different source than the weather and that lookup fails, the weather still updates, the last alerts stay, and the degraded warning explains why.
- Times on the dashboard (sunrise and sunset, "Updated", alert end times, and `{date}` and `{time}` in the subtitle) are shown as they are at the weather location, not in the viewing device's time zone. When the screen's own time zone differs, the zone is added, as in `4:12 PM GMT+1`.
- Each weather service is asked no more often than it allows, however short `OUTPOST_UPDATE_INTERVAL` is; between requests its last answer is reused. Open-Meteo is asked at most every 15 minutes, the National Weather Service's forecast every 15 minutes, its station readings every 5, and its alerts every minute, MET Norway only when its forecast or warnings may have changed, and Pirate Weather every 10 minutes. The updater lists these limits when it starts.
- `OUTPOST_UPDATE_INTERVAL` is at least 60 seconds. A shorter value is raised to 60, with a warning in the log.
- Outpost always tells weather services what it is: the User-Agent includes the project page, as `Outpost/<version> (+https://github.com/maxtrax04/outpost)`, or `Outpost/<version> (you@example.com; +https://github.com/maxtrax04/outpost)` with `OUTPOST_CONTACT`. Setting `OUTPOST_CONTACT` is still recommended. `OUTPOST_USER_AGENT` still replaces it all.
- Right after an upgrade, or after changing `OUTPOST_UNITS`, if the first update fails the screen shows that there is no data, rather than the last saved readings in the old format or units.
- The health check also requires `schema_version` to match.

### Upgrading from 0.5.0

- **If you only use the dashboard,** nothing is required. Rebuild with `docker compose up -d --build`, or pull `ghcr.io/maxtrax04/outpost:0.6.0` (or `latest`), and reload each screen once.
- **If another tool reads `weather.json`** (a Home Assistant REST sensor, a script), rename the fields it uses as listed above. For example, a Home Assistant template `{{ value_json.current.temperature_f }}` becomes `{{ value_json.current.temperature }}`, and `{{ value_json.source }}` becomes `{{ value_json.sources.weather.name }}`. Check `schema_version` to notice future breaking changes. See [docs/data-format.md](docs/data-format.md).
- **If you use Open-Meteo in the US,** you now also get National Weather Service alerts, which sends your coordinates to the National Weather Service. Set `OUTPOST_CONTACT`, or `OUTPOST_ALERTS_PROVIDER=none` to turn them off.
- **If you use `OUTPOST_PROVIDER=auto` in the Nordic countries,** the weather now comes from MET Norway instead of Open-Meteo. Set `OUTPOST_PROVIDER=openmeteo` to keep Open-Meteo.
- **If `OUTPOST_UPDATE_INTERVAL` is below 60,** it is raised to 60.
- New optional settings (see `.env.example`): `OUTPOST_ALERTS_PROVIDER` and `OUTPOST_PIRATEWEATHER_API_KEY`. `OUTPOST_UNITS=metric` now works.

## [0.5.0] - 2026-11-11

Themes and customization: three new built-in themes, community themes you can download, your own themes without rebuilding, an original logo, reduced effects, a 12- or 24-hour clock, and security headers. If you made your own theme for 0.4.0, see "Upgrading from 0.4.0" below.

### Added

- `field-station` theme: a riveted steel instrument panel, with analog dials for the readings, a stamped plate for each panel title, and hazard stripes on the warning shown when the weather data is old or missing.
- `atomic-broadcast` theme: a 1950s television set, with the dashboard on its screen fitted to the window, a test card while the weather loads or when it is lost, tuning-dial readings, and alerts as a news crawl along the bottom of the screen.
- `ink` theme for ePaper displays: pure black on white (dark red for severe alerts, which black-and-white panels show as black), heavier text, alert levels shown by their borders and spelled out instead of by color, no effects, animation, or night dimming, and the whole dashboard fits the screen down to 800 × 480. Use `?theme=ink` on just the ePaper screen. See "ePaper displays" in the README.
- Community themes: `OUTPOST_COMMUNITY_THEMES` lists themes from the [outpost-themes](https://github.com/maxtrax04/outpost-themes) repository, named `username/theme`, to download when the container starts. They are downloaded once per start and kept in the data volume, so they keep working offline; a failed download keeps the copies from before and logs one warning. Themes taken off the list are removed, and a theme that builds on another theme by the same person brings it along. `OUTPOST_COMMUNITY_THEMES_REF` picks a branch, tag, or commit. To use them with no internet at all, mount a clone of the repository at `/config/themes`. The theme switcher shows these themes by name, adding the username only when two themes share a name. See "Community themes" in the README.
- Your own themes without rebuilding: mount a folder of themes at `/config/themes` (one folder per theme, like the built-in ones). They appear in the theme switcher and can be chosen with `OUTPOST_THEME`, and one with the same name as a built-in theme replaces it. Only theme files (CSS, fonts, and images) are served from that folder, and the log lists the themes it found and explains any folder it skipped. An example theme to start from, `sonar`, is in `examples/themes/`. See "Adding themes without rebuilding" in `docs/themes.md`.
- An original Outpost logo, a riveted stencil plate, shown in the dashboard header in each theme's colors. The files are in `assets/logo/`, and `scripts/build-app-icons.js` rebuilds the favicon and home-screen icons from it.
- Reduced effects: scanlines, glow, and animation can be turned off in every theme, for readability and for slow wall tablets. `OUTPOST_EFFECTS=reduced` does it for everyone, a device set to reduce motion gets it automatically, and a "Reduced effects" checkbox in the theme panel lets each viewer choose in their own browser (`OUTPOST_EFFECTS_TOGGLE=false` removes it). `?effects=reduced` previews it.
- `OUTPOST_CLOCK`: `12` or `24` shows every time on the dashboard in 12- or 24-hour form, on every theme. The default, `auto`, follows the viewing browser's language (browsers do not share the device's clock setting). A "24-hour clock" checkbox in the theme panel lets each screen choose for itself (`OUTPOST_CLOCK_TOGGLE=false` removes it), and `?clock=12` or `?clock=24` previews one.
- Security headers on every response: a Content-Security-Policy that lets the dashboard load scripts, styles, fonts, images, and data only from Outpost itself, plus `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`. See "Security headers" in `SECURITY.md`.
- `OUTPOST_FRAME_ANCESTORS`: the sites allowed to show Outpost inside a frame, such as `http://homeassistant.local:8123` for a Home Assistant webpage card, separated by commas. By default only Outpost itself may.
- Themes with scanlines have a slow rolling band in their own text color drifting down the screen, like a picture tube.
- `OUTPOST_MOCK_ALERTS=true` makes the mock provider always include sample alerts, one of each severity, for trying how a theme shows alerts.
- For theme authors (all in `docs/themes.md`):
  - Gauge values: every reading is named (`data-metric="humidity"` and so on) and given to CSS as a value from 0 to 1 (`--wx-humidity`, and `--value` on its box), so dials and bars need no code.
  - Places to draw: panels are named with `data-panel`; panels, readings, and forecast cards are free for `::before` and `::after`; and a full-screen `.frame` layer with `--frame-inset` and `--frame-inset-bottom` takes a bezel.
  - Fit to screen: `--fit-screen: 1` fits the whole dashboard on the screen, with `--fit-width`, `--fit-max-scale` (grow on big screens), and `--fit-min-scale` (how far it may shrink). `?fit=on` or `?fit=off` tries it with any theme.
  - Page state on `<html>`: `data-signal` (`waiting`, `ok`, `degraded`, or `offline`), `data-effects`, `data-clock`, and `data-fit`.
  - Alerts: separate `.alert-title`, `.alert-description`, and `.alert-expires` elements, and `--alert-chars`, the amount of alert text, for a theme that scrolls them.
  - `--title-logo` (`1` shows the logo as the title, `0` the word OUTPOST in the theme's font), and `--scan-roll` for the rolling band's speed.

### Changed

- **Breaking for custom themes:** each theme is now a folder, `<name>/theme.css`, instead of a single `<name>.css` file, so it can carry its own fonts and images. `url(...)` paths in a theme are relative to its folder. The `OUTPOST_THEME` values are unchanged, and Outpost logs a warning for each old single-file theme it finds.
- `retro-crt`, `amber-terminal`, `command-center`, `modern-dark`, and `field-station` fill wide screens instead of staying a 1200-pixel column in the middle: about 1.5 times on a 2560 × 1440 display, and more than twice on 4K. Ultrawide screens get a centered 16:9 area. Laptops, phones, and portrait screens keep their layout.
- Themes can only use files served by Outpost. A theme's `url()` or `@import` pointing at another site, or a `data:` URL, is blocked by the browser.
- The favicon and home-screen icons are the Outpost "OP" plate instead of the sun icon.
- The header title is a heading (`<h1>`), so screen readers can jump to it.
- The nginx configuration is a file in the repository (`nginx/default.conf`). Theme files, the page, and its scripts are checked for changes on every load, so edits and upgrades show up on reload.

### Fixed

- Choosing any theme other than the one the page starts with (with the theme switcher, `?theme=`, or `OUTPOST_THEME`) showed the theme but never loaded the weather, leaving "Waiting for signal..." on screen.
- After an upgrade, a browser could keep running old cached scripts with the new page.
- Scanlines were almost invisible on dark themes, and did not cover the weather icons. They are now drawn in the theme's text color with darker gaps, over everything, and the screen edges darken slightly like a picture tube.

### Upgrading from 0.4.0

- **If you only use the built-in themes,** nothing is required. Rebuild with `docker compose up -d --build`, or pull `ghcr.io/maxtrax04/outpost:0.5.0` (or `latest`). Reload each screen once afterwards; from this release on, browsers pick up new versions by themselves.
- **If you made your own theme,** move `web/themes/my-theme.css` to `my-theme/theme.css`, either in `web/themes/` (then rebuild) or in a folder mounted at `/config/themes` (no rebuild). Add `../` to each `url(...)` path, or move those files into the theme's folder. Download any font or image it loads from another site into its folder. It now shows the logo as its title; to keep the text title, add `--title-logo: 0;` to its `:root` block. See [docs/themes.md](docs/themes.md).
- **If you show Outpost inside another page,** such as a Home Assistant webpage card, add that page's address to `OUTPOST_FRAME_ANCESTORS` (for example `OUTPOST_FRAME_ANCESTORS=http://homeassistant.local:8123`). Without it, the frame stays blank.
- A phone with Outpost on its home screen may keep the old icon until it is removed and added again.
- New optional settings (see `.env.example`): `OUTPOST_EFFECTS`, `OUTPOST_EFFECTS_TOGGLE`, `OUTPOST_CLOCK`, `OUTPOST_CLOCK_TOGGLE`, `OUTPOST_COMMUNITY_THEMES`, `OUTPOST_COMMUNITY_THEMES_REF`, `OUTPOST_FRAME_ANCESTORS`, and `OUTPOST_MOCK_ALERTS`.

## [0.4.0] - 2026-11-07

### Added

- Mobile and portrait layouts: a compact phone layout (three columns of detail boxes, one forecast row per day), a short header for phones turned sideways, and a scaled-up, vertically centered layout for tall portrait screens. Content stays clear of notches and uses the dynamic viewport height.
- Web app manifest, icons, and home-screen tags, so Outpost can be added to a phone's home screen and opens without browser bars. The browser's address bar color follows the active theme. The icon is a placeholder until the logo is designed.
- On-screen theme switcher (bottom-left corner, faint until used). The choice is saved in the viewer's browser, wins over `OUTPOST_THEME`, and can be reset. Setting: `OUTPOST_THEME_SWITCHER` (default `true`). The theme list and names come from the files in `web/themes/`.

### Changed

- GitHub Releases are marked "Latest" instead of "Pre-release", so the newest release shows in the repository sidebar. Only versions with a suffix, such as `0.5.0-beta.1`, are published as pre-releases.
- `config.json` now includes a `themes` list (each theme's id and display name) and a `ui.theme_switcher` flag, for the on-screen switcher.
- The nginx base image moved from `1.30-alpine` to `1.31-alpine`.
- `scripts/test.sh`, `scripts/test.ps1`, and CI now run every JavaScript test file (`node --test`) instead of only `tests/dim.test.js`.

### Upgrading from 0.3.0

- No settings need to change. Rebuild with `docker compose up -d --build`, or pull `ghcr.io/maxtrax04/outpost:0.4.0`.
- On a wall display or kiosk, set `OUTPOST_THEME_SWITCHER=false` to hide the theme button.
- Viewers who pick a theme with the switcher keep it in that browser even if `OUTPOST_THEME` changes later. Choose "Use server default" in the switcher to go back.

## [0.3.0] - 2026-10-31

### Added
- Dashboard:
  - Sunrise and sunset boxes, calculated in the browser from your coordinates (or "Midnight sun" and "Polar night" near the poles).
  - Day/night auto-dim. The display fades down after sunset and back up at sunrise, calculated from your coordinates, or follows a fixed nightly schedule. Settings: `OUTPOST_AUTO_DIM`, `OUTPOST_DIM_LEVEL`, `OUTPOST_DIM_MODE`, `OUTPOST_DIM_START`, `OUTPOST_DIM_END`. Preview with `?dim=night`, `?dim=day`, or `?dim=0.5`.
  - `OUTPOST_SUBTITLE` setting for an optional line under the title (`{date}` and `{time}` are filled in).
  - `OUTPOST_ALERTS_ALWAYS_SHOW` setting. When the Alerts panel is hidden, a one-line note shows when alerts were last checked.
  - `alerts_supported` field in `weather.json`, so the dashboard can tell "no alerts" apart from "this source has no alerts".
- `OUTPOST_CONTACT` setting: your email address or website, sent to weather services in the User-Agent header (`Outpost/<version> (<contact>)`). The National Weather Service asks every client to identify itself, and Outpost warns at startup if the contact is missing for `nws` or `auto`.
- Published Docker images for amd64 and arm64 at `ghcr.io/maxtrax04/outpost`: `docker pull ghcr.io/maxtrax04/outpost:0.3.0`. Tags: `0.3.0`, `0.3`, `latest`, and `edge` (the newest commit on `main`).
- Automation: a CI workflow (tests, Docker build, and a smoke test of the running container on every pull request), a release workflow that publishes the image and creates the GitHub Release from the changelog when a version tag is pushed, and Dependabot for the nginx base image and GitHub Actions.
- Automated tests (`tests/`) with `scripts/test.sh` and `scripts/test.ps1` to run them in Docker without installing anything.
- Project files: `ROADMAP.md`, `CONTRIBUTING.md`, `SECURITY.md`, issue and pull request templates, and `docs/github-workflow.md`.

### Changed

- The Provider box was removed from the current conditions (the data source is already shown in the footer).
- The header no longer shows "Local Status Display" by default; use `OUTPOST_SUBTITLE` to add a line.
- The Alerts panel is hidden when there are no alerts, unless `OUTPOST_ALERTS_ALWAYS_SHOW=true`.
- With Open-Meteo, the dashboard now says alerts are not provided by the data source instead of "No active alerts".
- Amber Terminal shows the weather condition in inverse video (dark text on an amber block) so it stands out.
- The Docker image no longer installs pip or curl, and `requirements.txt` is no longer used, because Outpost only uses Python's standard library. A test fails if a third-party import is added without the Dockerfile installing it.
- The nginx base image is pinned to the stable `1.30-alpine` line instead of the floating `alpine` tag.
- `OUTPOST_USER_AGENT` is now an advanced option that replaces the whole User-Agent. Most people should set `OUTPOST_CONTACT` instead.
- The version number now lives only in the `VERSION` file; the image labels are added by the release workflow.

### Fixed

- Sunrise, sunset, and sun-based dimming fall back to the coordinates stored in `weather.json` when `config.json` has none. Empty or null coordinates are no longer treated as latitude 0, longitude 0, and the Sunrise and Sunset boxes say "No coordinates" when none are available.
- The updater logs whether the coordinates came from `OUTPOST_LATITUDE` and `OUTPOST_LONGITUDE` or from the built-in example values (it never logs the coordinates themselves).

### Upgrading from 0.2.0

- Auto-dim is on by default. Set `OUTPOST_AUTO_DIM=false` to turn it off.
- If you use `nws` or `auto`, add `OUTPOST_CONTACT=you@example.com` to your `.env`.
- To keep the old header and always-visible alerts, set `OUTPOST_SUBTITLE=Local Status Display` and `OUTPOST_ALERTS_ALWAYS_SHOW=true`.
- If you maintain your own copy of the project, delete `requirements.txt`, which is no longer used.
- Rebuild with `docker compose up -d --build`, or switch to the published image (see the README).

## [0.2.0] - 2026-10-09

### Added

- Live weather from Open-Meteo (`OUTPOST_PROVIDER=openmeteo`), no API key needed.
- National Weather Service provider (`nws`) for US locations, including active watches and warnings.
  Alerts are sorted by severity and styled amber (moderate) or red (severe/extreme).
- `auto` provider: NWS inside the US, Open-Meteo elsewhere. Values NWS does not publish (such as UV index)
  are filled in from Open-Meteo, and the footer credits both sources.
- Theme system with four themes: `retro-crt` (default), `amber-terminal`, `command-center`, and `modern-dark`.
  Choose with `OUTPOST_THEME` or preview with `?theme=name`. See `docs/themes.md`.
- Original 13-icon weather set (clear, cloudy, fog, drizzle, rain, sleet, snow, storm, wind, day and night
  variants, and an unknown fallback). Icons take their color from the active theme.
- Bundled Share Tech Mono font (SIL Open Font License) with notices in `THIRD_PARTY.md`.
- `OUTPOST_USER_AGENT` setting (NWS asks clients to identify themselves).
- `.env.example`, `docs/themes.md`, and a full README with configuration and provider tables.
- Dashboard shows the data source and app version in the footer.
- Health check now also fails when `weather.json` is stale, so a stopped updater is detected.

### Changed

- Outpost now runs as a single container (nginx plus the updater) instead of two.
- The front end is split into `index.html`, `style.css`, and `app.js`; visuals are driven by theme variables.
- When an update fails, the dashboard keeps showing the last good data with a warning banner instead of going blank.
- The page warns about stale data after three missed updates (minimum five minutes), based on `OUTPOST_UPDATE_INTERVAL`.
- Default and example location is now Goodsprings, NV.
- The version number now lives in one file, `VERSION`.

### Fixed

- Updater syntax errors, and `start.sh` calling a file that did not exist.
- Typo in the web volume path (`/user/share`) in `docker-compose.yml`.
- Misspelled `tempurature_f` key, which is now `temperature_f`; stray colon in the `low_f` key.
- Dashboard icons not being included in the container image.
- Forecast not rendering because its container element was missing.

### Upgrading from 0.1.0

- Rename `OUTPOST_SOURCE` to `OUTPOST_PROVIDER` and `OUTPOST_PORT` to `OUTPOST_WEB_PORT` in your `.env`.
- Move `index.html`, `style.css`, and `app.js` into `web/`, and add `web/themes/`.
- Rebuild the image with `docker compose up -d --build`.

## [0.1.0]

### Added

- Initial foundation: Docker build and Compose startup, a mock weather provider, normalized `weather.json`
  written to a shared volume and served by nginx, and a first dashboard that reads it.
