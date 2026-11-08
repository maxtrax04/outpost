# Outpost: notes for Claude Code

Self-hosted, themeable dashboard (weather first; later alerts, sensors, power, telemetry) for wall-mounted displays and phones. One Docker container: nginx serves `web/`, a Python updater writes `/data/weather.json` and `/data/config.json`. Look is retro-terminal "Fallout-like" but must stay IP-free.

## Commands
- Run: `docker compose up -d --build` (UI on `http://localhost:${OUTPOST_WEB_PORT:-8088}`)
- All tests: `scripts/test.sh` (Windows: `scripts/test.ps1`)
- Python tests: `python -m unittest discover -s tests -b`
- JS tests: `TZ=UTC node --test` (finds `tests/*.test.js`)

## Layout
- `app/`: updater, health check, `start.sh`, `providers/{openmeteo,nws,gapfill}.py`
- `web/`: `index.html`, `style.css`, `app.js`, `dim.js`, `themes.js`, `manifest.webmanifest`, `themes/<name>/theme.css` (one folder per theme, since 0.5.0)
- `assets/`: `icons/` (13 original SVGs), `logo/` (original logo: mark, wordmark, lockup), `app/` (favicon and PWA icons, built from the logo by `scripts/build-app-icons.js`), `fonts/` (user supplies Share Tech Mono)
- `tests/`: unittest and `node --test`; fixtures use made-up locations; `tests/browser/check-themes.js` (Playwright, run by CI against the container)
- `docs/`: `themes.md`, `releasing.md`, `github-workflow.md`
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
- v0.4.0 released. v0.5.0 is being shipped as betas (`0.5.0-beta.N`, see "Beta releases" in `docs/releasing.md`); at 0.5.0, fold the beta CHANGELOG sections into one.
- v0.5.0-beta.1: folder-per-theme (#17, breaking). v0.5.0-beta.2: external themes (#18), security headers and CSP (#19), theme-loading fix. v0.5.0-beta.3: logo (#20). Still to do for v0.5.0: original decorative themes, community themes repo.
- The CSP has no `unsafe-inline` or `unsafe-eval`: no inline scripts, styles, or `style=` attributes (CSSOM `style.setProperty` is fine). Playwright's `page.waitForFunction` is blocked by it too; `tests/browser/check-themes.js` polls with `page.evaluate` instead.
- Not verified on real iOS/Android or with the real Share Tech Mono file.
