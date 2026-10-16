# Changelog

All notable changes to Outpost are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Until 1.0, minor versions may include breaking changes.

## [Unreleased]

### Added
- Day/night auto-dim. By default the display fades down after sunset and back up at sunrise, calculated from
  your coordinates. A fixed nightly schedule is also available. New settings: `OUTPOST_AUTO_DIM`,
  `OUTPOST_DIM_LEVEL`, `OUTPOST_DIM_MODE`, `OUTPOST_DIM_START`, and `OUTPOST_DIM_END`.
  Preview with `?dim=night`, `?dim=day`, or `?dim=0.5`.
- `ROADMAP.md`, issue and pull request templates, and `docs/github-workflow.md`.
- Automated tests (`tests/`) and a GitHub Actions workflow that runs them, builds the Docker image, and smoke-tests the running container on every pull request.
- `scripts/test.sh` and `scripts/test.ps1` to run the tests in Docker without installing anything.

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
