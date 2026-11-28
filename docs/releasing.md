# Releasing

## Versions

Outpost uses calendar versions, `YEAR.MONTH.FIX`, without leading zeros: `2027.3.0`, then `2027.3.1` and
`2027.3.2` for fixes. The month names the release cycle, the month you plan to release in, not the day
it ships (as with Home Assistant), so a cycle started in late February can still be `2027.3`. A new
feature starts a new cycle; a fix to a released version raises `FIX`. Versions before 2026.12.0 (0.x)
used Semantic Versioning.

The version no longer says whether something breaks. Whenever a setting or a behavior changes so that
people need to do something when they upgrade, the CHANGELOG gets a `### Breaking changes` heading with
the steps. The `weather.json` format has its own `schema_version` (docs/data-format.md).

Test versions get a suffix: `-beta.N` while a cycle is being built, then `-rc.N` (release candidates)
once it is complete; see [Beta releases](#beta-releases) and [Release candidates and the stable
release](#release-candidates-and-the-stable-release). `2027.3.0` is valid semver, which
docker/metadata-action and the Home Assistant add-on need; `2027.03.0` would not be.

Pushing a version tag does the rest: the release workflow (`.github/workflows/release.yml`) runs the
tests, builds the image for amd64 and arm64, publishes it to `ghcr.io/maxtrax04/outpost`, and creates
the GitHub Release from the changelog.

## Checklist

1. Edit `VERSION` (for example `2027.3.0`). The updater, `weather.json`, the dashboard footer, and the
   default User-Agent all read from it. This is the only place the version is set by hand.
2. In `CHANGELOG.md`, give the version its section with today's date, below an empty `[Unreleased]`, and
   note any breaking changes with their steps. These notes become the GitHub Release text.
3. Open a pull request with those two changes and wait for the CI checks to pass, then merge it.
4. Update your copy and tag the merge commit:

   ```bash
   git switch main
   git pull
   git tag -a v2027.3.0 -m "Outpost v2027.3.0"
   git push origin v2027.3.0
   ```

5. Watch the **Release** run in the repository's Actions tab. It fails early if the tag does not match
   `VERSION` or the changelog has no entry for it, so a mislabeled image cannot be published.
6. Confirm it worked:
   - The Releases page shows the new release, marked "Latest". The repository's sidebar shows it too.
     (Only versions with a suffix, such as `2027.3.0-rc.1`, are marked as pre-releases. GitHub never labels
     a pre-release "Latest".)
   - `docker pull ghcr.io/maxtrax04/outpost:2027.3.0` downloads the image. If it says `unauthorized` or
     access is denied, the package is still private; see the one-time setup notes below.
7. Close the milestone on GitHub (Milestones, then Close), and move any unfinished issues to the next one.

## Beta releases

A beta lets people try a cycle's changes while it is being built. It uses the same checklist with a
suffix on the version: `2027.3.0-beta.1`, then `2027.3.0-beta.2`, and so on.

1. Once a version has been released, every pull request toward the next one raises the beta number:
   the first sets `VERSION` to `2027.3.0-beta.1`, the next to `2027.3.0-beta.2`, and so on. A local build
   then shows a beta version in the dashboard footer, so it is never mistaken for a released version.
2. In the same pull request, put its changes in a `[2027.3.0-beta.N] - <date>` section of `CHANGELOG.md`,
   below an empty `[Unreleased]` (a test checks that `VERSION` has a section). That section lists only what
   is new in that beta, and becomes its release notes if it is published. Include the steps for breaking
   changes, since beta testers need them first.
3. Merge the pull request. To publish that beta, tag the merge commit `v2027.3.0-beta.N`, as in steps 3
   to 5 above. Not every beta has to be published; an untagged one is only seen in local builds and `edge`.
4. The release is marked as a pre-release, and the image is published only as `2027.3.0-beta.N` (and
   `edge`). `latest` and the cycle tag do not move, and the repository sidebar keeps showing the last
   stable release, so people who are not testing are not affected.
5. Between betas, `VERSION` stays at the last beta, so an `edge` image may show `2027.3.0-beta.1` while it
   already has newer changes.

A fix to a released version can skip the betas: set `VERSION` to `2027.3.1` with its own CHANGELOG
section, or try it first as `2027.3.1-beta.1`.

## Release candidates and the stable release

When a cycle is complete, it gets release candidates, and the last good one becomes the stable release
unchanged. Candidates take fixes only.

1. Set `VERSION` to `2027.3.0-rc.1` and merge every `2027.3.0-beta.N` section and `[Unreleased]` into one
   `## [2027.3.0-rc.1] - <date>` section, removing the beta sections. Its notes then cover everything since
   the last stable release, which is what people upgrading need. Merge, then tag `v2027.3.0-rc.1`.
2. Run it on real displays for a while. A fix makes `2027.3.0-rc.2`: rename the section and add the fix.
3. When a candidate has held up, release it as it is: set `VERSION` to `2027.3.0` and rename its section
   to `## [2027.3.0] - <date>`. Nothing else changes, so the stable release is the code that was tested.
   Merge, then tag `v2027.3.0`.

When a stable release is published, the release workflow turns its betas and release candidates, and any
earlier pre-release (such as the 0.9.0 betas before 2026.12.0), into drafts. They leave the public
Releases page, but stay visible to maintainers with their notes, and their tags and images are kept, so
anyone who pinned one is not affected. To show one again, edit it on GitHub and publish it, or run
`gh release edit v2027.3.0-rc.1 --draft=false`.

## Image tags

| Tag | Meaning |
|---|---|
| `2027.3.0` | That exact release |
| `2027.3` | The newest fix of the 2027.3 cycle |
| `latest` | The newest stable release (never a beta or release candidate) |
| `2027.3.0-rc.1` | That exact pre-release; betas and release candidates get no other tags |
| `edge` | The newest commit on `main`, for early testers (not a release) |

Older 0.x releases keep their tags, such as `0.8.0` and `0.8`.

## Before a release: provider end of life

Check that the weather services Outpost uses still offer the versions it asks for:

- OpenWeatherMap One Call API 3.0 (`app/providers/openweathermap.py`): read
  https://openweathermap.org/api/one-call-3 and its migration guide for an end-of-life date. Outpost
  also warns in its log when OpenWeatherMap's answers carry a `Deprecation` or `Sunset` header, and
  reports HTTP 410 as "an update is needed". If a date has been announced, open an issue to move to the
  newer version well before it.

## unRAID template

`unraid/outpost.xml` is built from the README's settings table by
`python3 scripts/build_unraid_template.py`; `tests/test_unraid.py` fails when it is out of date, so
run it after changing a setting's row. Community Apps reads it from `main`.

`ca_profile.xml` at the repository root is the Community Apps profile (a non-empty `<Profile>` is
required); `tests/test_unraid.py` checks its icon and links match the template's.

To get Outpost listed in Community Apps (once):

1. At https://ca.unraid.net/submit/new, add the repository, run Validate and Scan, and submit.
   It finds the template in `unraid/`. `<Support>` (and the profile's `<Forum>`) point at GitHub
   issues; an unRAID forum thread is optional (if you start one, set `<Support>` in
   `scripts/build_unraid_template.py` and `<Forum>` in `ca_profile.xml` to its address).
2. After a change to the template or profile, run Validate and Scan there again.

## Screenshots

The README's pictures (`docs/images/themes/*.png` and `docs/images/phone.png`) are taken by
`scripts/screenshots.sh`: it builds the image and starts it with the mock data at the example location
(never a real one), and `tests/browser/take-screenshots.js` tidies the readings into a likely day and
takes every built-in theme. Take them again when a theme's look changes, when a theme is added (also add
it to `BUILT_IN` in that script and to the README's table; `tests/test_project.py` checks), and before a
release, so the footer shows that version.

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
- **The Home Assistant add-on** is published by the release workflow's last job into
  [maxtrax04/outpost-addon](https://github.com/maxtrax04/outpost-addon), from `homeassistant/` here, by
  `scripts/publish_addon.py`: every version tag to its `beta` branch, and released versions to `main` too.
  It needs a repository secret, `ADDON_REPO_TOKEN`: a fine-grained personal access token with **Contents:
  Read and write** on the outpost-addon repository only. Without the secret, the job is skipped with a
  notice, and the rest of the release is unaffected. Change the add-on in `homeassistant/` here, never in
  outpost-addon, whose files are replaced on every release.
