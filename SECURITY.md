# Security policy

## Supported versions

Security fixes are made for the latest release and for `main`. Outpost is before 1.0, so please update to the
newest release before reporting a problem.

## Reporting a vulnerability

Please **do not** open a public issue for security problems.

Report it privately using GitHub's private vulnerability reporting: open the repository's **Security** tab and
choose **Report a vulnerability**. Include:

- what the problem is and why it matters,
- steps to reproduce it,
- the Outpost version (shown in the dashboard footer) and how you run it.

Remove your real location, API keys, and contact details from anything you attach.

This is a small project maintained in spare time, so replies are best effort. You will be credited in the fix
unless you prefer otherwise.

## What to keep in mind when running Outpost

- Outpost is designed for a trusted home or office network. It has no login, so do not expose it directly to
  the internet; put it behind a reverse proxy with authentication if you need remote access.
- `weather.json` and `config.json` contain your location. Anyone who can reach the dashboard can read them.
- Your `OUTPOST_CONTACT` value is sent to weather services in the User-Agent header.
