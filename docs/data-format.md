# weather.json format

Outpost's updater writes the weather to `/data/weather.json`, and the dashboard reads it from
`http://<outpost>/data/weather.json` (or `/api/weather`, which gives the same, and other places with
`?lat=..&lon=..`; see "Other places" in the README). Other tools can read it too, such as a Home Assistant REST sensor
(see [home-assistant.md](home-assistant.md)).
This page describes format version 1, used since Outpost 0.6.0. The same rules are in a
machine-readable [JSON Schema](schema/weather-v1.json).

## Versions and compatibility

Format 1 is frozen: from Outpost 0.9.0 on, it is the format other tools can rely on, and it stays
the same through the stable releases. What that promises:

- **Nothing is renamed or removed, and no value changes meaning,** without a new `schema_version`.
  A change like that gets a new version, its own schema file (`schema/weather-v2.json`), and upgrade
  steps in the CHANGELOG; the old schema file stays published.
- **New fields can appear** in format 1, so a reader should ignore fields it doesn't know.
- **Lists of values can grow**, such as a new `icon` or `severity`. A reader should treat a value it
  doesn't know as `unknown`.
- **Types don't change:** a field documented as a whole number stays one, and any reading can be
  `null`.
- **Outpost's own version** (`version`) says nothing about the format; check `schema_version`.

| Version | Outpost | Change |
| :---: | :--- | :--- |
| 1 | 0.6.0 | First versioned format. No field names a unit; units are in `units`. Sources are in `sources`. Added since, without a new version: `hourly`, `precipitation`, `alerts[].onset`, `air_quality`, and `sources.air_quality` (0.8.0); `hourly[].end` (0.9.0). |
| none | 0.5.0 and earlier | Fields such as `temperature_f` and `wind_mph`; see "Upgrading from 0.5.0" in the CHANGELOG. |

Fields added after 0.6.0 are optional in the JSON Schema, so files written by older versions still
match it, but Outpost always writes them from the version that added them.

## Upgrading a tool that reads weather.json

- **From 0.5.0 or earlier** (no `schema_version`): the field names changed, such as `temperature_f`
  to `temperature` and `source` to `sources.weather.name`. The full list is in "Upgrading from 0.5.0"
  in the [CHANGELOG](../CHANGELOG.md).
- **From 0.6.0 or 0.7.0:** nothing to change. Since 0.8.0 there is more to read: the hourly forecast
  (`hourly`), precipitation amounts (`precipitation` and `units.precipitation`), when alerts start
  (`alerts[].onset`), and air quality (`air_quality`, `sources.air_quality`).
- **From 0.8.0:** nothing to change. Since 0.9.0 each `hourly` entry has an `end`, which is how to tell
  whether it is still under way; with OpenWeatherMap's free plan entries are 3 hours long. Percentages
  and the UV index were already whole numbers from every source, and now the schema says so; alert
  severities outside the documented list are written as `unknown`.

## Editors

The `$schema` field links the file to its JSON Schema, so an editor that understands JSON Schema, such as
VS Code, checks `weather.json` and describes each field when you open it. The editor downloads the schema
from GitHub; Outpost itself never does. Each format version has its own schema file, so the link in a file
always matches its `schema_version`.

## Example

```json
{
  "$schema": "https://raw.githubusercontent.com/maxtrax04/outpost/main/docs/schema/weather-v1.json",
  "schema_version": 1,
  "status": "ok",
  "app": "Outpost",
  "version": "0.6.0",
  "provider": "auto",
  "sources": {
    "weather": { "id": "nws", "name": "National Weather Service (weather.gov)" },
    "alerts": { "id": "nws", "name": "National Weather Service (weather.gov)" },
    "fill": { "id": "openmeteo", "name": "Open-Meteo.com", "fields": ["current.uv_index", "forecast.uv_index"] },
    "air_quality": { "id": "openmeteo-air-quality", "name": "Copernicus Atmosphere Monitoring Service (CAMS) via Open-Meteo.com" }
  },
  "location": "Cinder Flats",
  "coordinates": { "latitude": 10.0, "longitude": 20.0 },
  "timezone": "America/Chicago",
  "generated_at": "2026-11-12T15:04:05.123456+00:00",
  "update_interval_seconds": 60,
  "units": { "system": "imperial", "temperature": "°F", "speed": "mph", "pressure": "inHg", "distance": "mi" },
  "current": {
    "temperature": 72,
    "feels_like": 70,
    "condition": "Partly Cloudy",
    "icon": "partly-cloudy",
    "humidity": 55,
    "dew_point": 55,
    "wind_speed": 8,
    "wind_gust": 17,
    "wind_direction": 225,
    "pressure": 30.02,
    "uv_index": 4,
    "visibility": 10,
    "observed_at": "2026-11-12T14:53:00+00:00"
  },
  "forecast": [
    {
      "day": "2026-11-12",
      "high": 75,
      "low": 58,
      "condition": "Mostly Sunny",
      "icon": "sunny",
      "precipitation_chance": 20,
      "precipitation": 0.05,
      "uv_index": 5
    }
  ],
  "hourly": [
    {
      "time": "2026-11-12T15:00:00+00:00",
      "end": "2026-11-12T16:00:00+00:00",
      "temperature": 72,
      "condition": "Partly Cloudy",
      "icon": "partly-cloudy",
      "precipitation_chance": 10,
      "precipitation": 0,
      "wind_speed": 8,
      "wind_direction": 225
    }
  ],
  "alerts": [
    {
      "title": "Wind Advisory",
      "description": "Wind Advisory issued November 12 at 9:00AM until November 12 at 6:00PM",
      "severity": "moderate",
      "onset": "2026-11-12T09:00:00-07:00",
      "expires": "2026-11-12T18:00:00-07:00",
      "uri": "https://api.weather.gov/alerts/example"
    }
  ],
  "air_quality": {
    "index": 42,
    "scale": "us",
    "category": "good",
    "level": 0,
    "us_aqi": 42,
    "european_aqi": 25,
    "pm2_5": 8.1,
    "pm10": 12.4,
    "ozone": 61.0,
    "nitrogen_dioxide": 9.4,
    "sulphur_dioxide": 1.8,
    "carbon_monoxide": 184.0,
    "pollen": null,
    "units": { "pollutants": "µg/m³", "pollen": "grains/m³" },
    "observed_at": "2026-11-12T15:00:00+00:00"
  },
  "last_error": null
}
```

## Fields

Any reading can be `null` when the source doesn't have it.

### Top level

| Field | Meaning |
| :--- | :--- |
| `$schema` | The address of this format's [JSON Schema](schema/weather-v1.json), for editors (see "Editors" above). |
| `schema_version` | The format version, `1`. |
| `status` | `ok`; `degraded` (the last update failed, so this is the last good data, and `generated_at` shows its age; or the readings are fresh but the alerts or air quality lookup failed, so `alerts` or `air_quality` are the last ones known, and `last_error` says so); or `error` (no usable data, with every reading `null`). |
| `app`, `version` | `Outpost` and the version that wrote the file. |
| `provider` | The `OUTPOST_PROVIDER` setting, such as `auto`. The provider actually used is in `sources`. |
| `sources` | Where the data came from (below). |
| `location` | `OUTPOST_LOCATION_NAME`. |
| `coordinates` | `latitude` and `longitude` from the settings. |
| `timezone` | The location's time zone, such as `Europe/Oslo`, from the weather service (Open-Meteo, NWS, Pirate Weather, OpenWeatherMap; with OpenWeatherMap's free plan, from Open-Meteo) or else the container's `TZ` setting. The dashboard shows times in it. `null` when unknown. |
| `generated_at` | When the weather was last fetched successfully, as an ISO 8601 time in UTC. It stays the same while the file is `degraded`, so it shows the data's age. |
| `update_interval_seconds` | How often the updater runs. The dashboard calls data old after three missed updates. |
| `units` | The unit of each kind of reading (below). |
| `current`, `forecast`, `hourly`, `alerts` | The weather (below). `hourly` is new in Outpost 0.8.0, so files from earlier versions don't have it. |
| `air_quality` | Air quality and pollen now (below), or `null`. New in Outpost 0.8.0. |
| `last_error` | Why the last update failed, or `null`. |

### `sources`

| Field | Meaning |
| :--- | :--- |
| `weather` | The source of the readings and forecast: `id` (a provider, as in `OUTPOST_PROVIDER`) and `name` (the name to credit). `null` in an error file. |
| `alerts` | The source of `alerts`, in the same form. It can differ from `weather` (`OUTPOST_ALERTS_PROVIDER`), for example Open-Meteo weather with National Weather Service alerts. With Pirate Weather (`pirateweather`) and OpenWeatherMap (`openweathermap`) an empty `alerts` list can also mean the country is not covered, and alerts are in the language they were published in. OpenWeatherMap gives no severity, so it is worked out from the alert's name (`unknown` when the name doesn't say). `null` when there is no source of official alerts, which is different from having none right now (`alerts` is then `[]` either way). |
| `fill` | A second source used for readings the first one left empty, with `fields` listing them. They can be `current.humidity`, `current.dew_point`, `current.wind_speed`, `current.pressure`, `current.uv_index`, `current.visibility`, `forecast.uv_index`, `forecast.high`, `forecast.low`, `forecast.precipitation`, and `hourly.precipitation`. `null` when nothing was filled. |
| `air_quality` | The source of `air_quality`, in the same form: the Copernicus Atmosphere Monitoring Service's forecasts, through Open-Meteo (`openmeteo-air-quality`), or `mock`. `null` when `air_quality` is. New in Outpost 0.8.0. |

The dashboard credits each source by name in its footer. Open-Meteo, MET Norway, and the Copernicus Atmosphere Monitoring Service require that credit.

### `units`

| Field | Used for | Imperial | Metric |
| :--- | :--- | :--- | :--- |
| `system` | | `imperial` | `metric` |
| `temperature` | `temperature`, `feels_like`, `dew_point`, `high`, `low` (and in `hourly`) | `°F`, whole degrees | `°C`, whole degrees |
| `speed` | `wind_speed`, `wind_gust` (and in `hourly`) | `mph`, whole numbers | `km/h`, whole numbers |
| `pressure` | `pressure` | `inHg`, 2 decimals | `hPa`, whole numbers |
| `distance` | `visibility` | `mi`, 1 decimal | `km`, 1 decimal |
| `precipitation` | `precipitation` in `forecast` and `hourly` | `in`, 2 decimals | `mm`, 1 decimal |

`OUTPOST_UNITS` picks the system (`imperial` by default). Every reading is converted and rounded once,
from the source's own numbers, so switching systems does not add rounding errors.

`humidity` and `precipitation_chance` are always percentages, whole numbers from 0 to 100;
`wind_direction` is always in whole degrees; and `uv_index` is a whole number with no unit.
The values are labels to show next to the number; a reader that converts values should check
`system`.

### `current`

| Field | Meaning |
| :--- | :--- |
| `temperature`, `feels_like` | Air temperature and how warm it feels. |
| `condition` | A short description from the source, such as `Partly Cloudy` (its wording and capitals vary by source). In an `error` file it is `DATA LINK LOST`, the dashboard's own wording, with `icon` `unknown`. |
| `icon` | One of the dashboard's icons: `sunny`, `clear-night`, `partly-cloudy`, `partly-cloudy-night`, `cloudy`, `fog`, `drizzle`, `rain`, `sleet`, `snow`, `storm`, `wind`, or `unknown`. |
| `humidity` | Relative humidity, in percent. |
| `dew_point` | The temperature at which dew forms, in the temperature unit. The closer it is to `temperature`, the more humid it feels. |
| `wind_speed` | Sustained wind speed. |
| `wind_gust` | The strongest gusts, in the same unit as `wind_speed`. `null` when there are none (the National Weather Service reports none in calm weather) or the source doesn't say. |
| `wind_direction` | Where the wind comes from, in whole degrees clockwise from north, 0 to 359 (`270` is a west wind). `null` when calm or not reported. Never filled in from another source. |
| `pressure` | Air pressure. |
| `uv_index` | UV index. |
| `visibility` | How far one can see. |
| `observed_at` | When these readings are from (ISO 8601, UTC). For a weather station, its observation time; for MET Norway, which forecasts "now", the start of the forecast hour. It can be well before `generated_at`: stations often report hourly, and a service's answer is reused for some minutes. `null` when unknown, such as when the National Weather Service has no recent station reading. |

### `forecast`

One entry per day, starting today.

| Field | Meaning |
| :--- | :--- |
| `day` | The date, such as `2026-11-12`, in the location's time zone. |
| `high`, `low` | The day's highest and lowest temperature. |
| `condition`, `icon` | As in `current`, for the day. |
| `precipitation_chance` | Chance of rain or snow, in percent. |
| `precipitation` | How much rain or snow is expected that day, as water (snow melted), in the `precipitation` unit. `0` when none is expected. For today, MET Norway gives only what is still to come; the others give the whole day. |
| `uv_index` | The day's highest UV index. |

### `hourly`

The next 24 hours, starting with the hour under way, in order: one entry per hour, each from `time`
to `end`. Shorter when the source forecasts fewer hours, and empty (`[]`) when it has no hourly
forecast. OpenWeatherMap's free plan forecasts in 3-hour steps, so it gives one entry per 3 hours (8 of
them), and each entry's readings are for its 3 hours. While the file is `degraded`, the first entries
can have ended already, so a reader should skip entries whose `end` has passed.

| Field | Meaning |
| :--- | :--- |
| `time` | When the hour starts, as an ISO 8601 time in UTC. |
| `end` | When it ends, as an ISO 8601 time in UTC: an hour after `time`, or 3 hours with OpenWeatherMap's free plan. New in Outpost 0.9.0; for files from earlier versions, take an hour after `time`. |
| `temperature` | The temperature for that hour. |
| `condition`, `icon` | As in `current`, for that hour (night icons after dark). |
| `precipitation_chance` | Chance of rain or snow in that hour, in percent. `null` when the source doesn't say (MET Norway gives it only for some places, and the National Weather Service not for every hour). |
| `precipitation` | How much rain or snow is expected in that hour, as water, in the `precipitation` unit. |
| `wind_speed` | Sustained wind speed. |
| `wind_direction` | Where the wind comes from, in whole degrees, as in `current`. `null` when calm. |

Sources: Open-Meteo, MET Norway, Pirate Weather, and OpenWeatherMap send hourly forecasts with the rest; the National
Weather Service has a separate hourly forecast, asked for as often as the daily one (every 15 minutes at
most). When that request fails, `hourly` is empty and the rest of the update goes on. The hourly
forecast is not filled in from another source, except `precipitation`.

`precipitation` in `forecast` and `hourly` is new in Outpost 0.8.0, as is the `precipitation` unit
label, so files from earlier versions don't have them. The National Weather Service forecast has no
amounts, so with it they come from Open-Meteo (`sources.fill` lists `forecast.precipitation` and
`hourly.precipitation`).

### `alerts`

Official alerts, most serious first, at most 5. Empty when there are none, or when the source has
none (`sources.alerts` is `null`).

| Field | Meaning |
| :--- | :--- |
| `title` | The kind of alert, such as `Wind Advisory`. |
| `description` | A short summary or the alert's full text, depending on the source: the National Weather Service's headline, MET Norway's area and description, or the full text from Pirate Weather and OpenWeatherMap. It can be long. |
| `severity` | `extreme`, `severe`, `moderate`, `minor`, or `unknown` (when the source doesn't say, or says something else); mock data also uses `test`. |
| `onset` | When it starts, as an ISO 8601 time, or `null`. It can be in the future: a warning for tomorrow morning is sent today. New in Outpost 0.8.0, so files from earlier versions don't have it. |
| `expires` | When it ends, as an ISO 8601 time, or `null`. |
| `uri` | A link to the full alert, or `null`. |

### `air_quality`

Air quality and pollen for the hour under way, from the Copernicus Atmosphere Monitoring Service's
forecasts (a model, not a nearby monitor). New in Outpost 0.8.0, so files from earlier versions don't
have it. `null` when `OUTPOST_AIR_QUALITY=false` or the service has nothing for the place.

| Field | Meaning |
| :--- | :--- |
| `index` | The air quality index on `scale`, a whole number. |
| `scale` | `us` (the US AQI) or `european` (the European Air Quality Index), from `OUTPOST_AIR_QUALITY_INDEX`. With `auto`, the US one in the United States and its territories (by the place's time zone), the European one everywhere else. |
| `category` | The index's band. US AQI: `good` (0 to 50), `moderate` (to 100), `unhealthy-sensitive` (unhealthy for sensitive groups, to 150), `unhealthy` (to 200), `very-unhealthy` (to 300), `hazardous`. European: `good` (0 to 20), `fair` (to 40), `moderate` (to 60), `poor` (to 80), `very-poor` (to 100), `extremely-poor`. |
| `level` | The band's place on its scale, from `0` (good) to `5` (the worst), the same for both scales. |
| `us_aqi`, `european_aqi` | Both indexes, whichever `scale` is. |
| `pm2_5`, `pm10`, `ozone`, `nitrogen_dioxide`, `sulphur_dioxide`, `carbon_monoxide` | Fine particles, coarser particles, and gases, in µg/m³ (`units.pollutants`) whatever `OUTPOST_UNITS` is. |
| `pollen` | `alder`, `birch`, `grass`, `mugwort`, `olive`, and `ragweed` pollen, in grains/m³ (`units.pollen`). `null` where none is forecast: it is only forecast for Europe, in season. |
| `units` | `pollutants` (`µg/m³`) and `pollen` (`grains/m³`). |
| `observed_at` | The hour these values are for, as an ISO 8601 time in UTC. After a failed lookup the last values stay (with `status` `degraded`), so this shows their age. |
