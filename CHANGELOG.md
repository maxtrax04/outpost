# Changelog

All notable changes to Outpost are documented here.
The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/). Until 1.0, minor versions may include breaking changes.

## [Unreleased]

### Added

- Two decorative themes. `field-station`: a riveted steel instrument panel, with analog dials for the readings, a stamped plate for each panel title, and hazard stripes on the warning shown when the weather data is old or missing. `atomic-broadcast`: a 1950s television set, with the dashboard on its screen fitted to the window, a test card while the weather loads or when it is lost, tuning-dial readings, and alerts as a news crawl along the bottom of the screen. With reduced effects, the crawl stands still and wraps.

## [0.5.0-beta.6] - 2026-11-11

This is a test release. It is published as a pre-release, and the `latest` image tag still points to 0.4.0.

### Added

- Fit to screen, for themes: a theme with `--fit-screen: 1` shrinks the whole dashboard just enough to fit the screen without scrolling, for wall displays and themes styled as a single screen. It never shrinks text below 55%; a screen that would need more scrolls as usual. With `--fit-max-scale` (for example `2`), a theme also lets it grow to fill big screens. Add `?fit=on` or `?fit=off` to the address to try it with any theme.
- `<html data-signal>` tells themes the state of the weather data: `waiting` until it first loads, then `ok`, `degraded`, or `offline`, so a theme can show its own "no signal" screen.
- `--frame-inset-bottom`, for a theme frame with a deeper bottom edge.
- `OUTPOST_MOCK_ALERTS=true` makes the mock provider always include sample alerts (one each of severe, moderate, and minor), for trying how a theme shows alerts.
- Each alert's title, description, and end time are now separate elements (`.alert-title`, `.alert-description`, `.alert-expires`), and `--alert-chars` gives the amount of alert text, so a theme can show alerts differently, such as a scrolling news crawl.
- `ink` theme for ePaper displays: pure black on white (dark red for severe alerts, which black-and-white panels show as black), heavier text, alert levels shown by their borders and spelled out instead of by color, no effects, animation, or night dimming, and the whole dashboard fits the screen down to 800 × 480. Use `?theme=ink` on just the ePaper screen. See "ePaper displays" in the README.
- `OUTPOST_CLOCK` setting: `12` or `24` shows every time on the dashboard (sunrise, sunset, last update, alert end times, and `{time}` in the subtitle) in 12- or 24-hour form, on every theme. The default, `auto`, follows the viewing browser's language as before (not the device's clock setting, which browsers do not share). `?clock=12` or `?clock=24` in the address previews one. The page also gets `data-clock` on `<html>` for themes.
- A "24-hour clock" checkbox in the theme panel lets each screen choose 12- or 24-hour times for itself, saved in its own browser; "Use server default" forgets it. `OUTPOST_CLOCK_TOGGLE=false` removes the checkbox.
- Every theme with scanlines now has a slow rolling band in its own text color drifting down the screen, like a picture tube. Reduced effects removes it, and a theme can change its speed with `--scan-roll` (`none` stops it).

### Changed

- The docs now show `OUTPOST_FRAME_ANCESTORS` as a comma-separated list (`http://homeassistant.local:8123,https://ha.example.com`), which needs no quotes wherever it is set. Lists separated by spaces still work.

### Fixed

- Scanlines were almost invisible on dark themes. They are now drawn in the theme's text color with darker gaps, and the screen edges darken slightly like a picture tube. `--scanlines` still sets the strength.
- After an upgrade, a browser could keep running old cached scripts with the new page. The page and its scripts are now checked for changes on every load (an unchanged file costs only a quick "not modified" reply).
- A theme with a frame around the whole screen (`.frame` with `--frame-inset`) now keeps the content inside the frame on phones and tablets too, not only on wide screens.

### Upgrading from 0.5.0-beta.5

- Nothing is required. New optional settings: `OUTPOST_CLOCK`, `OUTPOST_CLOCK_TOGGLE`, and `OUTPOST_MOCK_ALERTS` (see `.env.example`).
- For an ePaper display, add `?theme=ink` to that screen's address.
- Rebuild with `docker compose up -d --build`, or pull `ghcr.io/maxtrax04/outpost:0.5.0-beta.6`. Reload each screen once afterwards; from this release on, browsers pick up new versions by themselves.

## [0.5.0-beta.5] - 2026-11-07

This is a test release. It is published as a pre-release, and the `latest` image tag still points to 0.4.0.

### Added

- Reduced effects: scanlines, glow, and animation can be turned off in every theme, for readability and for slow wall tablets. `OUTPOST_EFFECTS=reduced` does it for everyone, a device set to reduce motion gets it automatically, and a "Reduced effects" checkbox in the theme panel lets each viewer turn effects off or back on in their browser. `OUTPOST_EFFECTS_TOGGLE=false` removes the checkbox. Add `?effects=reduced` to the address to preview it. See "Reduced effects" in the README, and in `docs/themes.md` for theme authors.

### Upgrading from 0.5.0-beta.4

- Nothing is required. To turn effects off for everyone, add `OUTPOST_EFFECTS=reduced` to your `.env`.
- Rebuild with `docker compose up -d --build`, or pull `ghcr.io/maxtrax04/outpost:0.5.0-beta.5`.

## [0.5.0-beta.4] - 2026-11-07

This is a test release. It is published as a pre-release, and the `latest` image tag still points to 0.4.0.

### Added

- Hooks for decorative themes: every reading is named (`data-metric="humidity"` and so on) and given to CSS as a value from 0 to 1 (`--wx-humidity`, and `--value` on its box), so a theme can draw dials and bars with CSS alone. Panels are named with `data-panel`, panels, readings, and forecast cards are free for `::before` and `::after` decorations, and a new full-screen `.frame` layer with `--frame-inset` takes a bezel. No change to how the existing themes look. See "Decorations and gauges" in `docs/themes.md`.

### Fixed

- Scanlines now cover the logo and weather icons too. Elements with a glow used to sit above them.

### Upgrading from 0.5.0-beta.3

- Nothing is required. Rebuild with `docker compose up -d --build`, or pull `ghcr.io/maxtrax04/outpost:0.5.0-beta.4`.

## [0.5.0-beta.3] - 2026-11-07

This is a test release. It is published as a pre-release, and the `latest` image tag still points to 0.4.0.

### Added

- An original Outpost logo: a riveted stencil plate. The dashboard header shows it in place of the text title, in each theme's colors and glow. The files are in `assets/logo/` (`mark.svg`, `wordmark.svg`, `lockup.svg`), and the README shows it at the top.
- `--title-logo` theme token: `1` shows the logo as the title, `0` shows the word OUTPOST in the theme's font as before. `modern-dark` uses `0`. A custom theme made before this release shows the logo. A theme can also use its own logo file; see "Logo" in `docs/themes.md`.
- `scripts/build-app-icons.js` rebuilds the favicon and home-screen icons from the logo.

### Changed

- The favicon and home-screen icons are the Outpost "OP" plate instead of the sun icon. A phone that already has Outpost on its home screen may keep the old icon until it is removed and added again.
- The header title is now a heading (`<h1>`), so screen readers can jump to it.

### Upgrading from 0.5.0-beta.2

- Nothing is required. A custom theme now shows the logo as its title; to keep the text title, add `--title-logo: 0;` to its `:root` block.
- Rebuild with `docker compose up -d --build`, or pull `ghcr.io/maxtrax04/outpost:0.5.0-beta.3`.

## [0.5.0-beta.2] - 2026-11-07

This is a test release. It is published as a pre-release, and the `latest` image tag still points to 0.4.0.

### Added

- Security headers on every response: a Content-Security-Policy that lets the dashboard load scripts, styles, fonts, images, and data only from Outpost itself, plus `X-Content-Type-Options: nosniff` and `Referrer-Policy: no-referrer`. See "Security headers" in `SECURITY.md`.
- `OUTPOST_FRAME_ANCESTORS` setting: the sites allowed to show Outpost inside a frame, such as `http://homeassistant.local:8123` for a Home Assistant webpage card. By default only Outpost itself may.
- Custom themes without rebuilding: mount a folder of themes at `/config/themes` (one folder per theme, like the built-in ones). They appear in the on-screen switcher and can be chosen with `OUTPOST_THEME`, and a custom theme with the same name as a built-in one replaces it. Only theme files (CSS, fonts, and images) are served from that folder. At startup the log lists the custom themes it found and explains any folder it skipped. See "Adding themes without rebuilding" in `docs/themes.md`, and the README for the unRAID path mapping.
- An example theme to start from, `sonar`, in `examples/themes/`. It is not built into the image.

### Changed

- The nginx configuration is now a file in the repository (`nginx/default.conf`) instead of being generated in the Dockerfile. Theme files are sent with `Cache-Control: no-cache`, so browsers check for edits on reload.
- Themes can only use files served by Outpost. A theme's `url()` or `@import` pointing at another site, or a `data:` URL, is now blocked by the browser.
- CI loads every theme in a real browser under the security headers, on phone and wide screens, and checks that the weather appears and nothing is blocked.

### Fixed

- Choosing any theme other than the one the page starts with (with the on-screen switcher, `?theme=`, or `OUTPOST_THEME`) showed the theme but never loaded the weather, leaving "Waiting for signal..." on screen. This affected 0.4.0 and 0.5.0-beta.1. Themes now load in a new stylesheet that replaces the old one, and loading a theme can no longer hold up the weather.

### Upgrading from 0.5.0-beta.1

- If you show Outpost inside another page, such as a Home Assistant webpage card, add that page's address to `OUTPOST_FRAME_ANCESTORS` (for example `OUTPOST_FRAME_ANCESTORS=http://homeassistant.local:8123`). Without it, the frame stays blank.
- If a custom theme loads fonts or images from another site, download them into the theme's folder.
- Rebuild with `docker compose up -d --build`, or pull `ghcr.io/maxtrax04/outpost:0.5.0-beta.2`.

## [0.5.0-beta.1] - 2026-11-07

This is a test release. It is published as a pre-release, and the `latest` image tag still points to 0.4.0.

### Changed

- **Breaking:** each theme is now a folder, `web/themes/<name>/theme.css`, instead of a single `web/themes/<name>.css` file, so a theme can carry its own fonts and images. `url(...)` paths in a theme are relative to its folder. The `OUTPOST_THEME` values are unchanged.
- At startup, Outpost logs a warning for each old single-file theme it finds in `web/themes/`, with the path to move it to.

### Upgrading from 0.4.0

- If you only use the built-in themes, nothing changes. Rebuild with `docker compose up -d --build`, or pull `ghcr.io/maxtrax04/outpost:0.5.0-beta.1`.
- If you made your own theme, move `web/themes/my-theme.css` to `web/themes/my-theme/theme.css` and rebuild. If it uses `url(...)` paths, add `../` to each one, or move those files into the theme's folder. See [docs/themes.md](docs/themes.md).

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
