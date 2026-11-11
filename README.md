<p align="center"><img src="docs/images/logo-banner.svg" alt="Outpost logo: a riveted stencil plate reading OUTPOST" width="480"></p>

# Outpost

[![CI](https://github.com/maxtrax04/outpost/actions/workflows/ci.yml/badge.svg)](https://github.com/maxtrax04/outpost/actions/workflows/ci.yml)

A self-hosted dashboard platform for weather, alerts, sensors, power monitoring, and telemetry, with themeable HUD-style displays.

> **Status:** early development (pre-1.0). The dashboard and container work with a built-in mock source and live Open-Meteo and National Weather Service data. More providers are in progress. Expect breaking changes until 1.0.

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
| `OUTPOST_THEME` | `retro-crt` | Dashboard look. See [Themes](#themes). |
| `OUTPOST_THEME_SWITCHER` | `true` | Show the on-screen theme switcher button. Set `false` for a kiosk display. |
| `OUTPOST_EFFECTS` | `full` | `reduced` turns off scanlines, glow, and animation for everyone. See [Reduced effects](#reduced-effects). |
| `OUTPOST_EFFECTS_TOGGLE` | `true` | Show the "Reduced effects" checkbox in the theme panel. Set `false` so viewers cannot change `OUTPOST_EFFECTS`. |
| `OUTPOST_AUTO_DIM` | `true` | Dim the display at night. See [Day/night dimming](#daynight-dimming). |
| `OUTPOST_DIM_LEVEL` | `0.35` | Night brightness, from `0.05` (very dark) to `1` (no dimming). |
| `OUTPOST_DIM_MODE` | `sun` | `sun` follows sunset and sunrise; `schedule` uses fixed times. |
| `OUTPOST_DIM_START` / `OUTPOST_DIM_END` | `22:00` / `06:00` | Night window for `schedule` mode (24-hour `HH:MM`). |
| `OUTPOST_CLOCK` | `auto` | `12` shows times like 1:05 PM, `24` like 13:05, on every theme. `auto` follows the viewing browser's language, not the device's 12/24-hour clock setting (browsers do not share it), so a browser in US English shows 12-hour times. Each screen can also choose with the "24-hour clock" checkbox in the theme panel (saved in that browser), or `?clock=12` / `?clock=24` in the address. |
| `OUTPOST_CLOCK_TOGGLE` | `true` | Show the "24-hour clock" checkbox in the theme panel. Set `false` so viewers cannot change `OUTPOST_CLOCK`. |
| `OUTPOST_SUBTITLE` | *(empty)* | Optional line under the title. Empty hides it; `{date}` and `{time}` show the current date and time. |
| `OUTPOST_ALERTS_ALWAYS_SHOW` | `false` | `false` hides the Alerts panel when there are none; `true` always shows it. See [Alerts](#alerts). |
| `OUTPOST_MOCK_ALERTS` | `false` | With the `mock` provider, `true` always includes sample alerts (one of each severity), for trying how alerts look. See [Alerts](#alerts). |
| `OUTPOST_LOCATION_NAME` | `Goodsprings, NV` | Name shown at the top of the dashboard. |
| `OUTPOST_LATITUDE` | `35.8319` | Latitude in decimal degrees. |
| `OUTPOST_LONGITUDE` | `-115.4328` | Longitude in decimal degrees. |
| `OUTPOST_UNITS` | `imperial` | Unit system. |
| `OUTPOST_UPDATE_INTERVAL` | `60` | Seconds between data updates. |
| `OUTPOST_CONTACT` | *(empty)* | Your email address or website, so weather services can reach you. Recommended for `nws` and `auto`. It is sent in the User-Agent header. |
| `OUTPOST_USER_AGENT` | *(empty)* | Advanced: replaces the whole User-Agent (normally `Outpost/<version> (<contact>)`). |
| `OUTPOST_FRAME_ANCESTORS` | *(empty)* | Comma-separated list of sites allowed to show Outpost in a frame, such as `http://homeassistant.local:8123` for a Home Assistant webpage card. Empty allows only Outpost itself. See [SECURITY.md](SECURITY.md#security-headers). |
| `OUTPOST_WEB_PORT` | `8088` | Host port for the web UI (Compose only). |

The defaults point at Goodsprings, NV. Set your own latitude and longitude to see your local weather.

## Weather providers

| Provider | `OUTPOST_PROVIDER` | API key | Status |
|---|---|---|---|
| Mock (test data) | `mock` | No | Available |
| [Open-Meteo](https://open-meteo.com) | `openmeteo` | No | Available (recommended default) |
| [National Weather Service](https://www.weather.gov/documentation/services-web-api) | `nws` | No | Available (US only, includes alerts) |
| Auto | `auto` | No | Available (NWS in the US, Open-Meteo elsewhere) |
| [MET Norway](https://api.met.no) | `metno` | No | Planned |
| [Pirate Weather](https://pirateweather.net) | `pirateweather` | Yes | Planned |
| [OpenWeatherMap](https://openweathermap.org) | `openweathermap` | Yes | Planned |

The National Weather Service asks every client to identify itself, so set `OUTPOST_CONTACT` to an email address or website (Outpost warns at startup if it is missing). NWS does not publish a UV index, so with `nws` alone that field shows `--`. With `auto`, anything NWS leaves empty (UV index, and any reading a station is missing) is filled in from Open-Meteo, and the footer credits both sources. Open-Meteo is free for non-commercial use and requires attribution, which the dashboard footer provides. Each provider has its own terms of use, attribution requirements, and rate limits. Please review them before running Outpost publicly or commercially.

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

Five themes are included: `retro-crt` (default), `amber-terminal`, `command-center`, `modern-dark`, and `ink` (black on white, for ePaper; see [ePaper displays](#epaper-displays)). Set `OUTPOST_THEME` to choose the default for everyone, or add `?theme=name` to the address to preview one.

Anyone viewing the dashboard can also pick a theme with the small button in the bottom-left corner (it is faint until you hover or tap it). The choice is remembered in that browser only, with a "Use server default" option to undo it. Set `OUTPOST_THEME_SWITCHER=false` to remove the button, for example on a wall display.

Themes are small CSS files, so making your own is easy. Mount a folder of your own themes at `/config/themes` to add them without rebuilding the image; [examples/themes/](examples/themes/) has one to start from. See [docs/themes.md](docs/themes.md).

<!-- TODO (public beta): add a screenshot of each theme here -->

### Reduced effects

Scanlines, glow, and animation can be turned off in every theme, which helps readability and slow wall tablets:

- **For everyone:** set `OUTPOST_EFFECTS=reduced`.
- **Automatically:** a device set to reduce motion (in its accessibility settings) gets reduced effects.
- **Per browser:** the "Reduced effects" checkbox in the theme panel turns them off or back on in that browser, and wins over the two above. "Use server default" forgets it. Set `OUTPOST_EFFECTS_TOGGLE=false` to remove the checkbox, so everyone gets `OUTPOST_EFFECTS`. The checkbox is in the theme panel, so `OUTPOST_THEME_SWITCHER=false` removes it too.
- **To preview:** add `?effects=reduced` (or `?effects=full`) to the address.

## Alerts

The Alerts panel lists active weather warnings from the National Weather Service (`nws`, or `auto` inside the US). Open-Meteo does not provide alerts at all, so with that source the dashboard says so instead of claiming there are none.

By default the panel is hidden when there is nothing to show, and a one-line note below the forecast says when alerts were last checked, for example `Alerts: none (checked 2:15 PM)`. Set `OUTPOST_ALERTS_ALWAYS_SHOW=true` to keep the panel visible. Severe and extreme alerts turn the panel red.

To see how alerts look without waiting for real weather, use `OUTPOST_PROVIDER=mock` with `OUTPOST_MOCK_ALERTS=true`: the dashboard then always shows three sample alerts, one each of severe, moderate, and minor.

The dashboard also shows today's sunrise and sunset (or "Midnight sun" / "Polar night" near the poles), calculated in the browser from your coordinates (no weather service needed). Times appear in the viewing device's time zone.

## Phones, tablets, and tall screens

The dashboard adapts to the screen: phones get a compact layout with the forecast as one row per day, tablets and wide screens keep five forecast cards in a row, phones turned sideways use a short header, and tall portrait screens (a monitor or tablet mounted upright) scale everything up and center it vertically. Notches and rounded corners are respected.

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
