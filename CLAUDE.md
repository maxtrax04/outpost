# Outpost: notes for Claude Code

Self-hosted, themeable dashboard (weather first; later alerts, sensors, power, telemetry) for wall-mounted displays and phones. One Docker container: nginx serves `web/`, a Python updater writes `/data/weather.json` and `/data/config.json`. Look is retro-terminal "Fallout-like" but must stay IP-free.

## Commands
- Run: `docker compose up -d --build` (UI on `http://localhost:${OUTPOST_WEB_PORT:-8088}`)
- All tests: `scripts/test.sh` (Windows: `scripts/test.ps1`)
- Python tests: `python -m unittest discover -s tests -b`
- JS tests: `TZ=UTC node --test` (finds `tests/*.test.js`)

## Layout
- `app/`: updater, `outpost_server.py` (runs the update loop and the API on 127.0.0.1:8081, behind nginx at `/api/`), map settings and tile cache snippet (`outpost_map.py`), map radar (`outpost_radar.py`), Home Assistant add-on mode (`outpost_addon.py`: /data/options.json and Home Assistant's config to settings, ingress listener), health check, community theme download (`outpost_community.py`, run once by `start.sh`), `start.sh`, `providers/{openmeteo,nws,metno,pirateweather,gapfill,geocoding}.py`, `units.py`, `regions.py` (offline region checks for auto)
- `web/`: `index.html`, `style.css`, `app.js`, `dim.js`, `effects.js`, `fit.js`, `clock.js`, `themes.js`, `gauges.js`, `data.js` (reads weather.json), `places.js` and `place-panel.js` (location search), `mvt.js`, `map.js`, and `radar.js` (map panel), `manifest.webmanifest`, `themes/<name>/theme.css` (one folder per theme, since 0.5.0)
- `assets/`: `icons/` (13 original SVGs), `logo/` (original logo: mark, wordmark, lockup), `app/` (favicon and PWA icons, built from the logo by `scripts/build-app-icons.js`), `fonts/` (user supplies Share Tech Mono)
- `tests/`: unittest and `node --test`; fixtures use made-up locations; `tests/browser/check-themes.js` (Playwright, run by CI against the container)
- `docs/`: `data-format.md` and `schema/weather-v<N>.json` (the weather.json format; a new file per schema_version), `themes.md`, `releasing.md`, `github-workflow.md`
- `homeassistant/`: the Home Assistant add-on (`repository.yaml`, `outpost/config.json`, DOCS, translations, icon and logo from `scripts/build-app-icons.js`); the release workflow copies it to maxtrax04/outpost-addon with `scripts/publish_addon.py` (betas to its `beta` branch, releases to `main`; needs the ADDON_REPO_TOKEN secret)
- `design/`: design working files (logo concepts, Illustrator masters); git-ignored
- `nginx/default.conf`: web server config; custom themes are mounted at `/config/themes` and win over `web/themes/`
- `examples/themes/`: example themes to mount (not built into the image)

## Rules
1. Privacy: never commit real `data/weather.json`, `.env`, or real coordinates. Fixtures use fictional places.
2. Original content only: no Fallout/Bethesda names, logos, art, or fonts. Keep `THIRD_PARTY.md` accurate.
3. `app/` is Python standard library only (the image has no pip).
4. Every new setting is added to `.env.example`, `README.md`, and has a test.
5. Every user-visible change goes in `CHANGELOG.md` under `[Unreleased]`.
6. Version lives only in the `VERSION` file.
7. Write atomically to `/data`; on provider failure keep last good data marked `degraded`.

## Workflow
Issue -> branch -> PR with `Closes #N` -> CI green -> merge -> tag `vX.Y.Z` (release workflow publishes `ghcr.io/maxtrax04/outpost`). See `docs/releasing.md`.

## Current state
- v0.5.0 released (themes and customization; betas 1 to 8 folded into one CHANGELOG section). Built-in themes: retro-crt, amber-terminal, command-center, modern-dark, field-station, atomic-broadcast, ink. Community themes live in maxtrax04/outpost-themes (`username/theme`, downloaded by `OUTPOST_COMMUNITY_THEMES`; its own checks in `.github/scripts/check_themes.py` and Outpost edge in a browser).
- Every PR after a release bumps VERSION to the next beta (see docs/releasing.md "Beta releases").
- v0.6.0 released (data model and providers; betas 1 to 11 folded into one CHANGELOG section): versioned weather.json (#23, beta.1) and metric units (#24, beta.2), a separate alerts source (#25, beta.3, OUTPOST_ALERTS_PROVIDER), MET Norway (#26, beta.4, plus Nordic auto), and Pirate Weather (#27, beta.5) done; auto puts the regional specialists (MET Norway, NWS) first and uses Pirate Weather elsewhere and as their fallback (beta.7); MET Norway alerts (MetAlerts) in Norway, from an offline Norway outline in regions.py (#79, beta.8); wind gusts (#80, beta.9); per-service request minimums (response caches in every provider, OUTPOST_UPDATE_INTERVAL at least 60 s, beta.10); reading time, wind direction, and dew point (#89, beta.11; hourly forecast, precipitation amounts, alert start times, and air quality are planned in the v0.8.0 milestone); #28 done in the same PR; times shown in the location's time zone (beta.6, weather.json "timezone"). Providers return unrounded imperial readings; app/units.py converts and rounds once. Ideas, not planned: an ePaper image renderer (#64).
- v0.7.0 in progress (platform): README badges (beta.1), docs/home-assistant.md (#33, beta.2, checked against a real Home Assistant); the API (#29) follows docs/api-design.md: location search ON by default (OUTPOST_LOCATION_SEARCH), OUTPOST_LOCATION_LIMIT=30 fetches an hour for other places, Pirate Weather for searched places only from spare quota (OUTPOST_LOCATION_PIRATEWEATHER), pinned ?lat=&lon= refused when search is off. Step 2 done (beta.4): outpost_server.py (Places cache: 2-decimal rounding, 15 min refresh, rolling-hour fetch limit, 50 places, forget after 1 h), nginx /api/ with limit_req and no access log, dashboard reads api/weather then data/weather.json (OutpostData.fetchWeather), pirateweather.spare_calls from RateLimit-Remaining/Reset and pirate_key(location). Step 3 done (beta.5, #30): /api/places (providers/geocoding.py, Open-Meteo geocoding, 1-day cache, 1 search/s), web/places.js (choice and saved list in localStorage, ?lat=&lon=&name= pins) and web/place-panel.js (LOCATION in the panel, now role=dialog; button shows when search is on even with one theme). Step 4 done (beta.6, #31): "Use my location" in the panel (getCurrentPosition once, rounded to 2 decimals, saved as "My location", replaced on the next tap; README "My location" covers HTTPS and reverse proxies). Map (#32, docs/map-design.md): OSM vector tiles (vector.openstreetmap.org/shortbread_v1) drawn by web/mvt.js + web/map.js on a canvas in --map-* theme colors; nginx caches tiles via /etc/nginx/outpost/map.conf from app/outpost_map.py (only OUTPOST_MAP_ZOOM, resolver from resolv.conf, UA with OUTPOST_CONTACT, which the default server requires). Step 1 base map done (beta.7). Step 2 radar done (beta.8): app/outpost_radar.py (NOAA MRMS WMS in the US from regions.noaa_radar_area, RainViewer elsewhere, max zoom 7), /api/radar lists frames, /tiles/radar/... goes nginx (outpost_radar_cache) -> outpost_server.py, which fetches only listed frames at the map zoom; web/radar.js draws between map.js's base and overlay layers; OUTPOST_MAP_RADAR (default on), OUTPOST_MAP_RADAR_LOOP (never on ink or reduced effects). Step 1 done (beta.3): `Location` and `LocationState` (`HomeState` is weather.json) passed through fetch_weather, resolve_alerts, update_once; defaults read the module globals at call time, so tests can patch LATITUDE/LONGITUDE/DATA_PATH.
- The CSP has no `unsafe-inline` or `unsafe-eval`: no inline scripts, styles, or `style=` attributes (CSSOM `style.setProperty` is fine). Playwright's `page.waitForFunction` is blocked by it too; `tests/browser/check-themes.js` polls with `page.evaluate` instead.
- Not verified on real iOS/Android, on real ePaper, or with the real Share Tech Mono file.
