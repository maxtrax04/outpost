# Outpost: notes for Claude Code

Self-hosted, themeable dashboard (weather first; later alerts, sensors, power, telemetry) for wall-mounted displays and phones. One Docker container: nginx serves `web/`, a Python updater writes `/data/weather.json` and `/data/config.json`. Look is retro-terminal "Fallout-like" but must stay IP-free.

## Commands
- Run: `docker compose up -d --build` (UI on `http://localhost:${OUTPOST_WEB_PORT:-8088}`)
- All tests: `scripts/test.sh` (Windows: `scripts/test.ps1`)
- Python tests: `python -m unittest discover -s tests -b`
- JS tests: `TZ=UTC node --test tests/`

## Layout
- `app/`: updater, health check, `start.sh`, `providers/{openmeteo,nws,gapfill}.py`
- `web/`: `index.html`, `style.css`, `app.js`, `dim.js`, `themes.js`, `manifest.webmanifest`, `themes/*.css`
- `assets/`: `icons/` (13 original SVGs), `app/` (PWA icons), `fonts/` (user supplies Share Tech Mono)
- `tests/`: unittest and `node --test`; fixtures use made-up locations
- `docs/`: `themes.md`, `releasing.md`, `github-workflow.md`

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
- v0.3.0 released. v0.4.0 (mobile/portrait layout, web app manifest, on-screen theme switcher) is built and browser-tested; confirm it is merged before starting v0.5.0.
- v0.5.0 next: folder-per-theme, external themes, CSP headers, logo, original decorative themes, community themes repo.
- Not verified on real iOS/Android or with the real Share Tech Mono file.
