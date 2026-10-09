# Outpost

A self-hosted dashboard platform for weather, alerts, sensors, power monitoring, and telemetry, with themeable HUD-style displays.

> **Status:** early development (v0.1.0). The dashboard and container work with a built-in mock data source. Real weather providers are in progress. Expect breaking changes until 1.0.

<!-- TODO (public beta): add a hero screenshot here, e.g.
![Outpost dashboard](docs/images/dashboard.png)
-->

## Features

- Single-container deployment: one Docker image, one port, one data volume
- Live conditions, 5-day forecast, and alerts on a retro terminal-style HUD
- Normalized weather data format, so the display doesn't care which provider supplied it
- Built-in health check (including stale-data detection)
- Warning banner when data is old, degraded, or unavailable

## Quick start

Requires Docker and Docker Compose.

```bash
git clone <your-repo-url> outpost
cd outpost
cp .env.example .env      # then edit .env (location, units, provider)
docker compose up -d --build
```

Open `http://localhost:8088`.

To view logs: `docker logs -f outpost`
To stop: `docker compose down`

## Configuration

All settings are environment variables, set in `.env` (Compose) or in your container template.

| Variable | Default | Description |
|---|---|---|
| `OUTPOST_PROVIDER` | `mock` | Weather data source. See [Weather providers](#weather-providers). |
| `OUTPOST_LOCATION_NAME` | `Goodsprings, NV` | Name shown at the top of the dashboard. |
| `OUTPOST_LATITUDE` | `35.8319` | Latitude in decimal degrees. |
| `OUTPOST_LONGITUDE` | `-115.4328` | Longitude in decimal degrees. |
| `OUTPOST_UNITS` | `imperial` | Unit system. |
| `OUTPOST_UPDATE_INTERVAL` | `60` | Seconds between data updates. |
| `OUTPOST_WEB_PORT` | `8088` | Host port for the web UI (Compose only). |

The defaults point at Goodsprings, NV. Set your own latitude and longitude to see your local weather.

## Weather providers

| Provider | `OUTPOST_PROVIDER` | API key | Status |
|---|---|---|---|
| Mock (test data) | `mock` | No | Available |
| [Open-Meteo](https://open-meteo.com) | `openmeteo` | No | Planned (recommended default) |
| [MET Norway](https://api.met.no) | `metno` | No | Planned |
| [Pirate Weather](https://pirateweather.net) | `pirateweather` | Yes | Planned |
| [OpenWeatherMap](https://openweathermap.org) | `openweathermap` | Yes | Planned |

Each provider has its own terms of use, attribution requirements, and rate limits. Please review them before running Outpost publicly or commercially.

## Data and storage

The updater writes normalized weather data to `/data/weather.json` inside the container, and the web server serves it to the dashboard. Mount `/data` as a volume (Compose does this with `./data`) so data survives restarts.

You can read the same file from other tools:

```bash
curl http://localhost:8088/data/weather.json
```

See [docs/data-format.md](docs/data-format.md) for the field reference. <!-- TODO: write this once the schema settles -->

## Running on unRAID

A Community Apps template is planned. Until then, you can add the container manually once an image is published:

- **Port:** container `80` to a host port of your choice
- **Path:** container `/data` to `/mnt/user/appdata/outpost`
- **Variables:** each `OUTPOST_*` setting from the table above

## Project layout

```
app/        Updater, health check, and provider modules (Python)
web/        Dashboard front end (HTML, CSS, JS)
assets/     Icons and fonts
data/       Generated weather.json (runtime, not committed)
```

## Roadmap

- [ ] Real weather providers (Open-Meteo first)
- [ ] Themes: Wasteland Terminal, Retro CRT, Command Center, Modern Dark
- [ ] Published Docker image and unRAID template
- [ ] Alerts from provider data
- [ ] Sensors, power monitoring, and telemetry panels

## Contributing

Issues and pull requests are welcome once the project reaches public beta. See `CONTRIBUTING.md` (planned).

## Changelog

See [CHANGELOG.md](CHANGELOG.md).

## License

Outpost is released under the [MIT License](LICENSE).

Weather data remains subject to each provider's own terms, and any third-party fonts or icons you add keep their own licenses.
