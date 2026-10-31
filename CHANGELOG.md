# Changelog

All notable changes to Outpost are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Until 1.0, minor versions may include breaking changes.

## [Unreleased]

### Added
- `OUTPOST_CONTACT` setting: your email address or website, sent to weather services in the User-Agent header (`Outpost/<version> (<contact>)`). The National Weather Service asks every client to identify itself, and Outpost now warns at startup if the contact is missing for `nws` or `auto`.
- `CONTRIBUTING.md` (workflow, privacy rules, and content rules) and `SECURITY.md` (how to report a vulnerability privately).
- Sunrise and sunset on the dashboard, calculated in the browser from your coordinates.
- `OUTPOST_SUBTITLE` setting for the line under the title (empty hides it; `{date}` and `{time}` are filled in).
- `OUTPOST_ALERTS_ALWAYS_SHOW` setting. When the Alerts panel is hidden, a one-line note shows when alerts were last checked.
- `alerts_supported` field in `weather.json`, so the dashboard can tell "no alerts" apart from "this source has no alerts".
- Day/night auto-dim. By default the display fades down after sunset and back up at sunrise, calculated from
  your coordinates. A fixed nightly schedule is also available. New settings: `OUTPOST_AUTO_DIM`,
  `OUTPOST_DIM_LEVEL`, `OUTPOST_DIM_MODE`, `OUTPOST_DIM_START`, and `OUTPOST_DIM_END`.
  Preview with `?dim=night`, `?dim=day`, or `?dim=0.5`.
- `ROADMAP.md`, issue and pull request templates, and `docs/github-workflow.md`.
- Automated tests (`tests/`) and a GitHub Actions workflow that runs them, builds the Docker image, and smoke-tests the running container on every pull request.
- `scripts/test.sh` and `scripts/test.ps1` to run the tests in Docker without installing anything.
- Release workflow: pushing a version tag runs the tests, publishes a multi-architecture (amd64 and arm64) image to `ghcr.io/maxtrax04/outpost`, and creates a GitHub Release from the changelog. Pushes to `main` publish an `edge` image.
- Dependabot configuration for the nginx base image and the GitHub Actions used by the workflows.

### Fixed
- Sunrise, sunset, and sun-based dimming now fall back to the coordinates stored in `weather.json` when `config.json` has none (for example an old file left by an earlier version). Empty or null coordinates are no longer treated as latitude 0, longitude 0.
- When no coordinates are available at all, the Sunrise and Sunset boxes now say "No coordinates" instead of "--".
- The updater logs whether the coordinates came from `OUTPOST_LATITUDE` and `OUTPOST_LONGITUDE` or from the built-in example values (it never logs the coordinates themselves).

### Changed
- The Docker image no longer installs pip or curl, and `requirements.txt` is no longer used, because Outpost only uses Python's standard library. A test now fails if a third-party import is added without the Dockerfile installing it.
- `OUTPOST_USER_AGENT` is now an advanced option that replaces the whole User-Agent. Most people should set `OUTPOST_CONTACT` instead.
- The Provider box was removed from the current conditions (the data source is already shown in the footer).
- The header no longer shows "Local Status Display" by default; use `OUTPOST_SUBTITLE` to add a line.
- The Alerts panel is hidden when there are no alerts, unless `OUTPOST_ALERTS_ALWAYS_SHOW=true`.
- With Open-Meteo, the dashboard now says alerts are not provided by the data source instead of "No active alerts".
- Amber Terminal now shows the weather condition in inverse video (dark text on an amber block) so it stands out.
- The nginx base image is pinned to the stable `1.30-alpine` line instead of the floating `alpine` tag.
- The version label on the image is now added by the release workflow, so the Dockerfile no longer needs updating at release time.

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
