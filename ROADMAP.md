# Roadmap

Outpost is a self-hosted dashboard platform. It starts as a themeable weather display for wall-mounted screens and is meant to grow from there.

This page is the big picture. The [milestones and issues on GitHub](../../milestones) are the source of truth, and plans will change as the project grows.

**Current release:** 0.2.0 (see [CHANGELOG.md](CHANGELOG.md))

## Principles

- **Self-hosted and private.** The dashboard talks only to your own server. Nothing is sent to a cloud service run by this project.
- **Simple to run.** One container, a few settings, sensible defaults.
- **Original content.** Icons, themes, and logos are original or properly licensed, with no third-party trademarks or artwork.
- **Stable data.** The `weather.json` format will be versioned and frozen before 1.0 so other tools can rely on it.

## Milestones

### v0.3.0 - CI and housekeeping

Automated builds and tests, published images, and tidy project settings.

- [ ] Add a CI workflow that builds the image and runs tests on every pull request
- [ ] Move the ad hoc tests into a tests/ folder
- [ ] Publish a multi-architecture Docker image to GHCR on version tags
- [ ] Enable Dependabot for the Docker base image and GitHub Actions
- [ ] Create the v0.2.0 tag and GitHub Release
- [ ] Replace OUTPOST_USER_AGENT with a simple OUTPOST_CONTACT setting
- [ ] Review requirements.txt and trim the Dockerfile
- [ ] Add CONTRIBUTING.md with workflow, privacy, and IP guidelines

### v0.4.0 - Dashboard polish and mobile

Cleaner dashboard, better alerts behavior, and a layout that works on phones and portrait screens.

- [ ] Remove the Provider box and add sunrise and sunset
- [ ] Make the header subtitle configurable and remove the default text
- [ ] Say so when a data source does not provide alerts
- [ ] Add an option to always show the Alerts panel
- [ ] Amber Terminal: make the weather condition text stand out
- [ ] Mobile and portrait layout
- [ ] Add a web app manifest for Add to Home Screen
- [ ] On-screen theme switcher that remembers the choice in the browser

### v0.5.0 - Themes and customization

Make themes easy to create and share, and give Outpost its own logo and look.

- [ ] Switch to one folder per theme
- [ ] Support external themes from a mounted folder
- [ ] Add nginx security headers, including a Content-Security-Policy
- [ ] Design an original OUTPOST logo as an SVG
- [ ] Add original decorative themes with bezels and gauges
- [ ] Create a community themes repository

### v0.6.0 - Data model and providers

A stable data format, metric units, and more weather providers with smarter automatic selection.

- [ ] Define a versioned, unit-neutral weather.json schema
- [ ] Support metric units
- [ ] Split the weather source from the alerts source
- [ ] Add the MET Norway provider
- [ ] Add the Pirate Weather provider
- [ ] Smarter automatic provider selection

### v0.7.0 - Platform

A small API that enables location search, browser location, a weather map, and Home Assistant support.

- [ ] Design a small HTTP API to replace the file-based flow
- [ ] Location search and saved locations
- [ ] Use the browser's location (requires HTTPS)
- [ ] Optional weather map and radar
- [ ] Home Assistant: document the iframe card and REST sensor
- [ ] Home Assistant add-on
- [ ] Sensor and power-monitoring panels

### v1.0.0 - First stable release

Stable data format, published image, unRAID template, and a full public-beta review.

- [ ] unRAID Community Apps template
- [ ] Add screenshots of every theme to the README
- [ ] Public beta checklist: privacy, license, and content audit
- [ ] Freeze the weather.json schema and publish upgrade notes

## Ideas (not scheduled)

These are good ideas that need more thought before they get a milestone.

- Auto-rotating pages and a tabbed details view
- Environment Canada alerts
- MET Norway alerts for Norway
- Translations

## Why this order

- **Housekeeping first.** Automated checks and a published image make every later change safer and are required for the unRAID template.
- **Polish and mobile next.** These are small, visible improvements.
- **Themes before a community.** External themes need a stable folder layout and security headers before others can safely share them.
- **Data format before integrations.** Home Assistant and community themes will read `weather.json`, so its shape and units are settled first.
- **Providers after the data format.** New providers (and metric units) build on the stable format.
- **The API unlocks the rest.** Location search, browser location, and a map all need a small server-side API.

## Suggest something

Open an issue using the feature request template. Please check this page and the existing issues first. See [docs/github-workflow.md](docs/github-workflow.md) for how work is organized.
