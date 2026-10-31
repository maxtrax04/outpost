# Changelog

All notable changes to Outpost are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Until 1.0, minor versions may include breaking changes.

## [Unreleased]

### Changed
- GitHub Releases are marked "Latest" instead of "Pre-release", so the newest release shows in the repository sidebar. Only versions with a suffix, such as `0.5.0-beta.1`, are published as pre-releases.

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
