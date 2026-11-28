# Outpost: notes for Claude Code

Self-hosted, themeable dashboard (weather first; later alerts, sensors, power, telemetry) for wall-mounted displays and phones. One Docker container: nginx serves `web/`, a Python updater writes `/data/weather.json` and `/data/config.json`. The look is retro-terminal, and every name, image, and font must be original or openly licensed.

## Commands
- Run: `docker compose up -d --build` (UI on `http://localhost:${OUTPOST_WEB_PORT:-8088}`)
- All tests: `scripts/test.sh` (Windows: `scripts/test.ps1`)
- Python tests: `python -m unittest discover -s tests -b`
- JS tests: `TZ=UTC node --test` (finds `tests/*.test.js`)

## Layout
- `app/`: updater, `outpost_server.py` (runs the update loop and the API on 127.0.0.1:8081, behind nginx at `/api/`), map settings and tile cache snippet (`outpost_map.py`), map radar (`outpost_radar.py`), sensors from Home Assistant or MQTT (`outpost_sensors.py`, /api/sensors; `outpost_mqtt.py`, the MQTT client), Home Assistant add-on mode (`outpost_addon.py`: /data/options.json and Home Assistant's config to settings, ingress listener), health check, community theme download (`outpost_community.py`, run once by `start.sh`), `start.sh`, `providers/{openmeteo,nws,metno,pirateweather,openweathermap,gapfill,geocoding,hourly,airquality}.py`, `units.py`, `regions.py` (offline region checks for auto)
- `web/`: `index.html`, `style.css`, `app.js`, `dim.js`, `effects.js`, `fit.js`, `clock.js`, `themes.js`, `gauges.js`, `data.js` (reads weather.json), `places.js` and `place-panel.js` (location search), `mvt.js`, `map.js`, and `radar.js` (map panel), `sensors.js` (sensor and power panels), `hourly.js` (hourly forecast strip), `manifest.webmanifest`, `themes/<name>/theme.css` (one folder per theme, since 0.5.0)
- `assets/`: `icons/` (13 original SVGs), `logo/` (original logo: mark, wordmark, lockup), `app/` (favicon and PWA icons, built from the logo by `scripts/build-app-icons.js`), `fonts/` (Share Tech Mono 1.003 from Google Fonts, bundled since 0.2.0 with its OFL text)
- `tests/`: unittest and `node --test`; fixtures use made-up locations; `tests/browser/check-themes.js` (Playwright, run by CI against the container); `tests/browser/take-screenshots.js` (the README's pictures in `docs/images/themes/` and `docs/images/phone.png`, run by `scripts/screenshots.sh`)
- `docs/`: `data-format.md` and `schema/weather-v<N>.json` (the weather.json format; a new file per schema_version), `themes.md`, `releasing.md`, `github-workflow.md`
- `unraid/outpost.xml`: the unRAID Community Apps template, built from the README's settings table by `scripts/build_unraid_template.py` (tests/test_unraid.py checks it is current), and `ca_profile.xml` at the root (the Community Apps profile, ca.unraid.net/submit/new); `app/outpost_env.py` drops empty OUTPOST_* variables (unRAID passes every template variable), imported first by every script that reads settings
- `homeassistant/`: the Home Assistant add-on (`repository.yaml`, `outpost/config.json`, DOCS, translations, icon and logo from `scripts/build-app-icons.js`); the release workflow copies it to maxtrax04/outpost-addon with `scripts/publish_addon.py` (betas to its `beta` branch, releases to `main`; needs the ADDON_REPO_TOKEN secret)
- `design/`: design working files (logo concepts, Illustrator masters); git-ignored
- `nginx/default.conf`: web server config; custom themes are mounted at `/config/themes` and win over `web/themes/`
- `examples/themes/`: example themes to mount (not built into the image)

## Rules
1. Privacy: never commit real `data/weather.json`, `.env`, keys, or anyone's real location. Sample data and fixtures use fictional places; tests that check region borders use public city centres.
2. Original content only: no Fallout/Bethesda names, logos, art, or fonts. Keep `THIRD_PARTY.md` accurate.
3. `app/` is Python standard library only (the image has no pip).
4. Every new setting is added to `.env.example`, `README.md` (then rebuild `unraid/outpost.xml`), and has a test.
5. Every user-visible change goes in `CHANGELOG.md` under `[Unreleased]`.
6. Version lives only in the `VERSION` file.
7. Write atomically to `/data`; on provider failure keep last good data marked `degraded`.

## Workflow
Issue -> branch -> PR with `Closes #N` -> CI green -> merge -> tag `vX.Y.Z` (release workflow publishes `ghcr.io/maxtrax04/outpost`). See `docs/releasing.md`.

## Conventions
- Calendar versions `YEAR.MONTH.FIX` from 2026.12.0 (#118; docs/releasing.md): every PR after a release bumps VERSION to the next beta (`2027.1.0-beta.N`) with its own CHANGELOG section; a complete cycle becomes `-rc.N` with its betas folded into one section, and the stable release is the last good candidate unchanged. Breaking changes get a `### Breaking changes` heading with steps.
- Providers return unrounded imperial readings; `app/units.py` converts and rounds once.
- weather.json format 1 is frozen (docs/data-format.md "Versions and compatibility"): add optional fields only; a breaking change is a new schema_version and a new `docs/schema/weather-v<N>.json`.
- The CSP has no `unsafe-inline` or `unsafe-eval`: no inline scripts, styles, or `style=` attributes (CSSOM `style.setProperty` is fine). Playwright's `page.waitForFunction` is blocked by it too; `tests/browser/check-themes.js` polls with `page.evaluate` instead.
- API keys, tokens, and passwords are never logged or shown; coordinates are not logged.
- Maintainer's working notes (release history, current milestone) go in `CLAUDE.local.md`, which is git-ignored.
