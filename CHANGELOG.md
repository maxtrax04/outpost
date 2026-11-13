# Changelog

All notable changes to Outpost are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Until 1.0, minor versions may include breaking changes.

## [Unreleased]

## [0.6.0-beta.4] - 2026-11-13

### Added

- MET Norway weather: `OUTPOST_PROVIDER=metno` uses MET Norway's forecast, which covers the whole world and is especially good in the Nordic countries. MET Norway asks for `OUTPOST_CONTACT`, and the footer credits it. Outpost downloads the forecast again only when MET Norway says it has changed (about every 30 minutes), whatever `OUTPOST_UPDATE_INTERVAL` is. MET Norway sends a forecast rather than station readings, so the current conditions are the forecast for this hour, visibility shows `--`, and the UV index is for a clear sky. Forecast days follow the container's `TZ` setting. MET Norway has no alerts in this release; in the US, `OUTPOST_ALERTS_PROVIDER=auto` still adds National Weather Service alerts.

### Changed

- Outpost now always tells weather services what it is: the User-Agent includes the project page, as `Outpost/<version> (+https://github.com/maxtrax04/outpost)`, or `Outpost/<version> (you@example.com; +https://github.com/maxtrax04/outpost)` with `OUTPOST_CONTACT`. So it works with services that refuse anonymous requests even before a contact is set. Setting `OUTPOST_CONTACT` is still recommended, so a service can reach you instead of blocking every Outpost install; the startup reminder says so. `OUTPOST_USER_AGENT` still replaces it all.

## [0.6.0-beta.3] - 2026-11-12

### Added

- `OUTPOST_ALERTS_PROVIDER` picks where official alerts come from, separately from the weather: `auto` (default), `nws`, or `none`. With `auto`, alerts come from the weather provider when it has them; when it doesn't, as with Open-Meteo, they come from the National Weather Service wherever it covers the location (the US). `weather.json` names the alerts source in `sources.alerts`, and the dashboard footer credits it. See "Alerts" in the README.

### Changed

- **With Open-Meteo in the US, the dashboard now shows official alerts** from the National Weather Service, where before it said alerts were not available. This sends your coordinates to the National Weather Service too; set `OUTPOST_ALERTS_PROVIDER=none` to go back to no alerts, and set `OUTPOST_CONTACT`, since NWS asks for it. Outside the US the dashboard looks the same, but Outpost still asks the National Weather Service about every 30 minutes whether it covers the location (sending it the coordinates); `none` stops that too.
- When alerts come from a different source than the weather and that lookup fails, the weather still updates. The dashboard keeps the last alerts and shows the degraded warning, and `last_error` in `weather.json` explains it.

## [0.6.0-beta.2] - 2026-11-12

### Added

- Metric units: `OUTPOST_UNITS=metric` shows °C, km/h, hPa, and km on the dashboard and in `weather.json` (its `units` block says which system is used). The setting was accepted before but did nothing. Each reading is converted and rounded once, from the weather source's own numbers. Theme gauges point to the same place in either system. An unknown value logs a warning and uses imperial.

### Changed

- Changing `OUTPOST_UNITS` and restarting while the weather source is unreachable shows that there is no data, rather than the last saved readings in the other units.

## [0.6.0-beta.1] - 2026-11-12

### Added

- `docs/data-format.md` describes every field of `weather.json`, for anyone reading it from another tool such as Home Assistant, and `docs/schema/weather-v1.json` is the same as a JSON Schema. `weather.json` links to it in a `$schema` field, so editors such as VS Code check the file and describe each field when you open it.

### Changed

- **Breaking for anything that reads `weather.json`:** the file has a versioned format (`"schema_version": 1`), and no field name includes a unit. `temperature_f` is now `temperature`, `feels_like_f` is `feels_like`, `wind_mph` is `wind_speed`, `pressure_inhg` is `pressure`, `visibility_miles` is `visibility`, `humidity_percent` is `humidity`, and in the forecast `high_f`, `low_f`, and `precipitation_percent` are `high`, `low`, and `precipitation_chance`. The units are listed once in a `units` block (for example `"temperature": "°F"`), and the dashboard shows them from there. The dashboard itself looks the same.
- **Breaking for anything that reads `weather.json`:** where the data came from is in a `sources` block, with `weather`, `alerts` (`null` when the source has no official alerts), and `fill` (the second source used for missing readings, and which ones). It replaces `source`, `provider_setting`, `filled_fields`, and `alerts_supported`. `provider` is now always the `OUTPOST_PROVIDER` setting (such as `auto`); the provider actually used is `sources.weather.id`.
- Right after an upgrade, if the first update fails, Outpost no longer shows the weather saved by the old version as "degraded" data, because that file is in the old format. The screen shows that there is no data until an update succeeds.
- The health check also requires `schema_version` to match.

### Upgrading from 0.5.0

- **If you only use the dashboard,** nothing is required. Rebuild or pull, and reload each screen once.
- **If another tool reads `weather.json`** (a Home Assistant REST sensor, a script), rename the fields it uses as listed above. For example, a Home Assistant template `{{ value_json.current.temperature_f }}` becomes `{{ value_json.current.temperature }}`, and `{{ value_json.source }}` becomes `{{ value_json.sources.weather.name }}`. Check `schema_version` to notice future breaking changes. See [docs/data-format.md](docs/data-format.md).

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
