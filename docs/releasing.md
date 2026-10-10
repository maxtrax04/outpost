# Releasing

Outpost uses [Semantic Versioning](https://semver.org/). Before 1.0, bump the minor version
(0.2.0 to 0.3.0) for new features or breaking changes, and the patch version (0.2.0 to 0.2.1) for fixes only.

## Checklist

1. Edit `VERSION` (for example `0.3.0`). The updater, `weather.json`, the dashboard footer, and the
   default User-Agent all read from it.
2. Update the `ARG OUTPOST_VERSION` default near the top of the `Dockerfile` to match.
3. In `CHANGELOG.md`, rename `[Unreleased]` to the new version with today's date, add a fresh empty
   `[Unreleased]` above it, and note any upgrade steps.
4. Run `docker compose up -d --build` and check the dashboard loads and the footer shows the new version.
5. Commit, tag, and push:

   ```bash
   git add -A
   git commit -m "Release v0.3.0"
   git tag -a v0.3.0 -m "Outpost v0.3.0"
   git push origin main --follow-tags
   ```

## Before pushing, every time

- `git status` should not list `.env` or anything in `data/`.
- Any font in `assets/fonts/` has its license file beside it and an entry in `THIRD_PARTY.md`.
