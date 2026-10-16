# Releasing

Outpost uses [Semantic Versioning](https://semver.org/). Before 1.0, bump the minor version
(0.3.0 to 0.4.0) for new features or breaking changes, and the patch version (0.3.0 to 0.3.1) for fixes only.

Pushing a version tag does the rest: the release workflow (`.github/workflows/release.yml`) runs the
tests, builds the image for amd64 and arm64, publishes it to `ghcr.io/maxtrax04/outpost`, and creates
the GitHub Release from the changelog.

## Checklist

1. Edit `VERSION` (for example `0.4.0`). The updater, `weather.json`, the dashboard footer, and the
   default User-Agent all read from it. This is the only place the version is set by hand.
2. In `CHANGELOG.md`, rename `[Unreleased]` to the new version with today's date, add a fresh empty
   `[Unreleased]` above it, and note any upgrade steps. These notes become the GitHub Release text.
3. Open a pull request with those two changes and wait for the CI checks to pass, then merge it.
4. Update your copy and tag the merge commit:

   ```bash
   git switch main
   git pull
   git tag -a v0.4.0 -m "Outpost v0.4.0"
   git push origin v0.4.0
   ```

5. Watch the **Release** run in the repository's Actions tab. It fails early if the tag does not match
   `VERSION` or the changelog has no entry for it, so a mislabeled image cannot be published.
6. Confirm it worked:
   - The Releases page shows the new release (versions before 1.0 are marked as pre-releases).
   - `docker pull ghcr.io/maxtrax04/outpost:0.4.0` downloads the image.

## Image tags

| Tag | Meaning |
|---|---|
| `0.4.0` | That exact release |
| `0.4` | The newest patch release of 0.4 |
| `latest` | The newest release |
| `edge` | The newest commit on `main`, for early testers (not a release) |

## Before pushing, every time

- `git status` should not list `.env` or anything in `data/`.
- Any font in `assets/fonts/` has its license file beside it and an entry in `THIRD_PARTY.md`.

## One-time setup notes

- The first image publish creates the package on ghcr.io. Packages inherit the repository's visibility, so
  make the package public (Package settings, then Change visibility) when the repository goes public.
- If publishing fails with a permission error, check Settings, then Actions, then General, then
  Workflow permissions in the repository.
