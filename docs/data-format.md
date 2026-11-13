# weather.json format

Outpost's updater writes the weather to `/data/weather.json`, and the dashboard reads it from
`http://<outpost>/data/weather.json`. Other tools can read it too, such as a Home Assistant REST sensor.
This page describes format version 1, used since Outpost 0.6.0. The same rules are in a
machine-readable [JSON Schema](schema/weather-v1.json).

## Versions

`schema_version` goes up only for a change that breaks readers: a field renamed or removed, or a
change in what a value means. New fields can appear without a new version, so a reader should
ignore fields it doesn't know.

| Version | Outpost | Change |
| :---: | :--- | :--- |
| 1 | 0.6.0 | First versioned format. No field names a unit; units are in `units`. Sources are in `sources`. |
| none | 0.5.0 and earlier | Fields such as `temperature_f` and `wind_mph`; see "Upgrading from 0.5.0" in the CHANGELOG. |

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
    "fill": { "id": "openmeteo", "name": "Open-Meteo.com", "fields": ["current.uv_index", "forecast.uv_index"] }
  },
  "location": "Cinder Flats",
  "coordinates": { "latitude": 10.0, "longitude": 20.0 },
  "generated_at": "2026-11-12T15:04:05.123456+00:00",
  "update_interval_seconds": 60,
  "units": { "system": "imperial", "temperature": "°F", "speed": "mph", "pressure": "inHg", "distance": "mi" },
  "current": {
    "temperature": 72,
    "feels_like": 70,
    "condition": "Partly Cloudy",
    "icon": "partly-cloudy",
    "humidity": 55,
    "wind_speed": 8,
    "pressure": 30.02,
    "uv_index": 4,
    "visibility": 10
  },
  "forecast": [
    {
      "day": "2026-11-12",
      "high": 75,
      "low": 58,
      "condition": "Mostly Sunny",
      "icon": "sunny",
      "precipitation_chance": 20,
      "uv_index": 5
    }
  ],
  "alerts": [
    {
      "title": "Wind Advisory",
      "description": "Wind Advisory issued November 12 at 9:00AM until November 12 at 6:00PM",
      "severity": "moderate",
      "expires": "2026-11-12T18:00:00-07:00",
      "uri": "https://api.weather.gov/alerts/example"
    }
  ],
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
| `status` | `ok`; `degraded` (the last update failed, so this is the last good data, and `generated_at` shows its age; or the readings are fresh but the alerts lookup failed, so `alerts` are the last ones known, and `last_error` says so); or `error` (no usable data, with every reading `null`). |
| `app`, `version` | `Outpost` and the version that wrote the file. |
| `provider` | The `OUTPOST_PROVIDER` setting, such as `auto`. The provider actually used is in `sources`. |
| `sources` | Where the data came from (below). |
| `location` | `OUTPOST_LOCATION_NAME`. |
| `coordinates` | `latitude` and `longitude` from the settings. |
| `generated_at` | When the data was fetched, as an ISO 8601 time in UTC. |
| `update_interval_seconds` | How often the updater runs. The dashboard calls data old after three missed updates. |
| `units` | The unit of each kind of reading (below). |
| `current`, `forecast`, `alerts` | The weather (below). |
| `last_error` | Why the last update failed, or `null`. |

### `sources`

| Field | Meaning |
| :--- | :--- |
| `weather` | The source of the readings and forecast: `id` (a provider, as in `OUTPOST_PROVIDER`) and `name` (the name to credit). `null` in an error file. |
| `alerts` | The source of `alerts`, in the same form. It can differ from `weather` (`OUTPOST_ALERTS_PROVIDER`), for example Open-Meteo weather with National Weather Service alerts. `null` when there is no source of official alerts, which is different from having none right now (`alerts` is then `[]` either way). |
| `fill` | A second source used for readings the first one left empty, with `fields` listing them (such as `current.uv_index` or `forecast.high`). `null` when nothing was filled. |

The dashboard credits each source by name in its footer. Open-Meteo requires that credit.

### `units`

| Field | Used for | Imperial | Metric |
| :--- | :--- | :--- | :--- |
| `system` | | `imperial` | `metric` |
| `temperature` | `temperature`, `feels_like`, `high`, `low` | `°F`, whole degrees | `°C`, whole degrees |
| `speed` | `wind_speed` | `mph`, whole numbers | `km/h`, whole numbers |
| `pressure` | `pressure` | `inHg`, 2 decimals | `hPa`, whole numbers |
| `distance` | `visibility` | `mi`, 1 decimal | `km`, 1 decimal |

`OUTPOST_UNITS` picks the system (`imperial` by default). Every reading is converted and rounded once,
from the source's own numbers, so switching systems does not add rounding errors.

`humidity` and `precipitation_chance` are always percentages (0 to 100), and `uv_index` has no unit.
The values are labels to show next to the number; a reader that converts values should check
`system`.

### `current`

| Field | Meaning |
| :--- | :--- |
| `temperature`, `feels_like` | Air temperature and how warm it feels. |
| `condition` | A short description from the source, such as `Partly Cloudy`. |
| `icon` | One of the dashboard's icons: `sunny`, `clear-night`, `partly-cloudy`, `partly-cloudy-night`, `cloudy`, `fog`, `drizzle`, `rain`, `sleet`, `snow`, `storm`, `wind`, or `unknown`. |
| `humidity` | Relative humidity, in percent. |
| `wind_speed` | Sustained wind speed. |
| `pressure` | Air pressure. |
| `uv_index` | UV index. |
| `visibility` | How far one can see. |

### `forecast`

One entry per day, starting today.

| Field | Meaning |
| :--- | :--- |
| `day` | The date, such as `2026-11-12`, in the location's time zone. |
| `high`, `low` | The day's highest and lowest temperature. |
| `condition`, `icon` | As in `current`, for the day. |
| `precipitation_chance` | Chance of rain or snow, in percent. |
| `uv_index` | The day's highest UV index. |

### `alerts`

Official alerts, most serious first. Empty when there are none, or when the source has none
(`sources.alerts` is `null`).

| Field | Meaning |
| :--- | :--- |
| `title` | The kind of alert, such as `Wind Advisory`. |
| `description` | The alert's headline. |
| `severity` | `extreme`, `severe`, `moderate`, `minor`, or `unknown` (mock data also uses `test`). |
| `expires` | When it ends, as an ISO 8601 time, or `null`. |
| `uri` | A link to the full alert, or `null`. |
