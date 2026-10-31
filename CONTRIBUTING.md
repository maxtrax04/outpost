# Contributing to Outpost

Thanks for your interest in Outpost! Bug reports, ideas, themes, providers, and fixes are all welcome.
This page explains how to get started and the few rules that keep the project safe and original.

## Ways to help

- **Report a bug** or **suggest a feature** using the [issue templates](../../issues/new/choose).
- **Pick up an issue.** Look at the [roadmap](ROADMAP.md) and the [milestones](../../milestones), and issues labeled
  `good first issue` or `help wanted`. Comment on the issue before you start so work is not duplicated.
- **Make a theme.** See [docs/themes.md](docs/themes.md).
- **Improve the docs.** Fixes to the README or guides are always appreciated.

## Ground rules

### Privacy: never share your real location

Outpost's files (`.env`, `weather.json`, `config.json`) and its screenshots contain your location, and
sometimes API keys. Before you post anything in an issue, pull request, or screenshot:

- Replace your coordinates and place name with made-up ones (the examples use Goodsprings, NV).
- Remove API keys and your contact email.
- Never commit `.env` or anything in `data/` (the `.gitignore` already excludes them, and CI checks).

### Original and properly licensed content only

- Icons, logos, themes, and images must be your own work or clearly licensed for reuse. List third-party
  fonts and assets, with their licenses, in [THIRD_PARTY.md](THIRD_PARTY.md) and keep the license file beside them.
- **No third-party trademarks, logos, characters, or game artwork**, and do not name themes or features after
  existing franchises or brands. Evoking a mood (retro terminals, atomic-age signage) is fine; copying
  someone else's identity is not.
- Weather data stays subject to each provider's terms. Check them before adding a provider.

### Keep it simple

- The app uses only Python's standard library, in one container. Please open an issue to discuss before adding
  a dependency. (A test fails if a third-party import appears without the Dockerfile installing it.)
- Prefer small, focused pull requests that close one issue.

### Tests and docs go with the change

- Add or update tests for behavior you change. Tests never call the network; use the saved samples in
  `tests/fixtures/` (with made-up locations).
- If you add or change a setting, document it in `.env.example` and the README table. A test checks this.
- Add a line under `[Unreleased]` in [CHANGELOG.md](CHANGELOG.md).

## Setting up

You only need Docker and Git.

```
git clone https://github.com/maxtrax04/outpost.git
cd outpost
cp .env.example .env          # then edit it (use made-up coordinates when sharing anything)
docker compose up -d --build
```

Open `http://localhost:8088`. Rebuild with `docker compose up -d --build` after changing code, because the
files are baked into the image.

Run the tests (no Python or Node install needed):

```
./scripts/test.sh             # Linux and macOS
.\scripts\test.ps1            # Windows PowerShell
```

Windows tip: shell scripts must keep Unix (LF) line endings, or they fail inside the container. The
`.gitattributes` file handles this; CI also checks it.

## Making a change

The full walkthrough, with commands, is in [docs/github-workflow.md](docs/github-workflow.md). In short:

1. Find or open an issue, and say you are working on it.
2. Create a branch from `main`, make your change, and commit with a clear message.
3. Push the branch and open a pull request. The template lists what to check. Write `Closes #<number>` in
   the description so the issue closes when it is merged.
4. Wait for the CI checks to pass, and respond to any feedback.

## Adding things

- **A weather provider:** add a module in `app/providers/` with a `fetch(latitude, longitude, user_agent)` that
  returns the normalized data (see `openmeteo.py` and `nws.py`), wire it into `outpost_updater.py`, add fixtures
  and tests, and add it to the README provider table with its attribution and terms.
- **A theme:** copy a file in `web/themes/`, follow [docs/themes.md](docs/themes.md), and check text contrast
  (a test does this for you).
- **An icon:** follow the steps in the README's Icons section.

## Security problems

Please do not open a public issue for a vulnerability. See [SECURITY.md](SECURITY.md).

## License

Outpost is released under the [MIT License](LICENSE). By contributing, you agree that your contribution is
licensed under the same terms.
