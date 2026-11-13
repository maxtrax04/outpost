# Outpost: notes for Claude Code

Self-hosted, themeable dashboard (weather first; later alerts, sensors, power, telemetry) for wall-mounted displays and phones. One Docker container: nginx serves `web/`, a Python updater writes `/data/weather.json` and `/data/config.json`. Look is retro-terminal "Fallout-like" but must stay IP-free.

## Commands
- Run: `docker compose up -d --build` (UI on `http://localhost:${OUTPOST_WEB_PORT:-8088}`)
- All tests: `scripts/test.sh` (Windows: `scripts/test.ps1`)
- Python tests: `python -m unittest discover -s tests -b`
- JS tests: `TZ=UTC node --test` (finds `tests/*.test.js`)

## Layout
- `app/`: updater, health check, community theme download (`outpost_community.py`, run once by `start.sh`), `start.sh`, `providers/{openmeteo,nws,gapfill}.py`
- `web/`: `index.html`, `style.css`, `app.js`, `dim.js`, `effects.js`, `fit.js`, `clock.js`, `themes.js`, `gauges.js`, `data.js` (reads weather.json), `manifest.webmanifest`, `themes/<name>/theme.css` (one folder per theme, since 0.5.0)
- `assets/`: `icons/` (13 original SVGs), `logo/` (original logo: mark, wordmark, lockup), `app/` (favicon and PWA icons, built from the logo by `scripts/build-app-icons.js`), `fonts/` (user supplies Share Tech Mono)
- `tests/`: unittest and `node --test`; fixtures use made-up locations; `tests/browser/check-themes.js` (Playwright, run by CI against the container)
- `docs/`: `data-format.md` and `schema/weather-v<N>.json` (the weather.json format; a new file per schema_version), `themes.md`, `releasing.md`, `github-workflow.md`
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
- v0.6.0 in progress (data model and providers): versioned weather.json (#23, beta.1) and metric units (#24, beta.2) done; next #25 (separate alerts source), MET Norway (#26), Pirate Weather (#27), smarter auto (#28). Providers return unrounded imperial readings; app/units.py converts and rounds once. Ideas, not planned: an ePaper image renderer (#64).
- The CSP has no `unsafe-inline` or `unsafe-eval`: no inline scripts, styles, or `style=` attributes (CSSOM `style.setProperty` is fine). Playwright's `page.waitForFunction` is blocked by it too; `tests/browser/check-themes.js` polls with `page.evaluate` instead.
- Not verified on real iOS/Android, on real ePaper, or with the real Share Tech Mono file.
