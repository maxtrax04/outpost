# Releasing

Outpost uses [Semantic Versioning](https://semver.org/). Before 1.0, bump the minor version
(0.3.0 to 0.4.0) for new features or breaking changes, and the patch version (0.3.0 to 0.3.1) for fixes only.
Test versions get a suffix, such as `0.5.0-beta.1`; see [Beta releases](#beta-releases).

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
   - The Releases page shows the new release, marked "Latest". The repository's sidebar shows it too.
     (Only versions with a suffix, such as `0.5.0-beta.1`, are marked as pre-releases. GitHub never labels a
     pre-release "Latest", so the sidebar shows only a tag count when every release is a pre-release.)
   - `docker pull ghcr.io/maxtrax04/outpost:0.4.0` downloads the image. If it says `unauthorized` or access
     is denied, the package is still private; see the one-time setup notes below.
7. Close the milestone on GitHub (Milestones, then Close), and move any unfinished issues to the next one.

## Beta releases

A beta lets people try a version, especially one with breaking changes, before it is final. It uses the
same checklist with a suffix on the version: `0.5.0-beta.1`, then `0.5.0-beta.2`, and so on.

1. While you work, changes go under `[Unreleased]` as usual.
2. To publish a beta, set `VERSION` to `0.5.0-beta.1` and rename `[Unreleased]` to
   `[0.5.0-beta.1] - <date>` with a fresh empty `[Unreleased]` above it. That section lists only what is
   new since the previous beta, and becomes that beta's release notes. Include upgrade steps for breaking
   changes, since beta testers need them first.
3. Open the pull request, merge it, and tag the merge commit `v0.5.0-beta.1`, as in steps 3 to 5 above.
4. The release is marked as a pre-release, and the image is published only as `0.5.0-beta.1` (and `edge`).
   `latest` and `0.5` do not move, and the repository sidebar keeps showing the last full release, so
   people who are not testing are not affected.
5. Between betas, `VERSION` stays at the last beta, so an `edge` image may show `0.5.0-beta.1` while it
   already has newer changes.

For the final release, set `VERSION` to `0.5.0` and merge every `0.5.0-beta.N` section and `[Unreleased]`
into one `## [0.5.0] - <date>` section, removing the beta sections. Its notes then cover everything since
0.4.0, which is what people upgrading from the last full release need. The beta tags and GitHub pre-releases
stay as the record of each beta.

## Image tags

| Tag | Meaning |
|---|---|
| `0.4.0` | That exact release |
| `0.4` | The newest patch release of 0.4 |
| `latest` | The newest release (never a beta) |
| `0.5.0-beta.1` | That exact beta; betas get no other tags |
| `edge` | The newest commit on `main`, for early testers (not a release) |

## Before pushing, every time

- `git status` should not list `.env` or anything in `data/`.
- Any font in `assets/fonts/` or in a theme's folder has its license file beside it and an entry in
  `THIRD_PARTY.md`.

## One-time setup notes

- **Make the package public after the first publish.** The first image publish creates the package on
  ghcr.io, and new packages start out private, even in a public repository. Until you change that,
  `docker pull` fails with `unauthorized` for everyone else. To fix it: open the package (the repository's
  sidebar, under Packages), choose Package settings, then Danger Zone, Change visibility, Public.
  Test with `docker logout ghcr.io` followed by `docker pull ghcr.io/maxtrax04/outpost:<version>`.
- If publishing fails with a permission error, check Settings, then Actions, then General, then
  Workflow permissions in the repository.
