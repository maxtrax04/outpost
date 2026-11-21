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
- `OUTPOST_PIRATEWEATHER_API_KEY` is a secret. Outpost sends it only to Pirate Weather, in a request header (never in an address), and never writes it to `weather.json`, `config.json`, or the log.
- `OUTPOST_HA_TOKEN` is a secret with access to your Home Assistant. Outpost sends it only to `OUTPOST_HA_URL`, in a request header, and never to a screen or the log. Outpost only reads the entities listed in `OUTPOST_SENSORS`, and never changes anything in Home Assistant; a token from a Home Assistant user with fewer rights limits what a leaked token could do.
- Readings listed in `OUTPOST_SENSORS` can be seen by anyone who can reach the dashboard (at `/api/sensors`). Don't list doors, locks, or presence on a dashboard others can reach.
- Theme files in a folder mounted at `/config/themes` (CSS, fonts, and images only) are served to anyone who
  can reach the dashboard. Mount a folder that holds only themes, read-only.
- With `OUTPOST_COMMUNITY_THEMES` set, Outpost downloads those themes from GitHub (`codeload.github.com`) once each time
  the container starts, sending only `Outpost/<version>` as the User-Agent. Without it, the only outside requests are
  to your weather services. Downloaded themes are kept in `/data/community` and only their CSS, font, and image files
  are served.

## Security headers

Every response from Outpost's web server includes:

| Header | Value | Why |
|---|---|---|
| `Content-Security-Policy` | Everything (scripts, styles, images, fonts, data) only from Outpost itself; no inline scripts or styles; no plugins, forms, or `<base>` | A theme is CSS, and CSS can load files from anywhere. This keeps a theme, or anything injected into the page, from loading remote files or sending your data elsewhere. |
| `X-Content-Type-Options` | `nosniff` | Browsers use the declared file type instead of guessing, so a file cannot be run as a script by mistake. |
| `Referrer-Policy` | `no-referrer` | Your dashboard's address is not sent to other sites. |

Because of the policy, a theme can only use fonts and images from its own folder or `assets/`; a `url()`
pointing at another site is blocked by the browser.

### Showing Outpost inside another page

By default, only Outpost itself may show the dashboard in a frame (`frame-ancestors 'self'`), which stops
other sites from embedding it. To show it in a Home Assistant webpage card, or any other page, list that
page's address in `OUTPOST_FRAME_ANCESTORS`, including the port:

```
OUTPOST_FRAME_ANCESTORS=http://homeassistant.local:8123,https://ha.example.com
```

Separate entries with commas. Spaces also work (that is how the header itself lists them), but a value with
spaces may need quotes depending on where you set it. `self`, `none`, and `https://*.example.com` style wildcards also
work. Anything else is rejected (Outpost logs a warning and uses the default), because the value goes into a
header. Restart the container after changing it.

If a reverse proxy adds its own `Content-Security-Policy` or `X-Frame-Options`, browsers apply both, so the
stricter one wins. Remove the proxy's copy if embedding stops working.

### Planned exceptions

Later features will need the policy to allow a little more. Each will be added only when that feature is,
and only for the sites it needs:

- **Weather map and radar:** none needed. The map's tiles and its radar are fetched through Outpost's own
  nginx (`/tiles/`), so the page still loads everything from Outpost. Only the zoom the map draws is passed
  on, and for radar only frames Outpost has listed, so Outpost is not an open tile proxy.
- **Browser location:** no CSP change. If Outpost ever sends a `Permissions-Policy` header, it must allow
  `geolocation=(self)`.
- **Home Assistant add-on:** no change. Home Assistant shows the add-on's panel in a frame through its
  ingress proxy, on Home Assistant's own address, which `frame-ancestors 'self'` already allows. The
  ingress port (8099) answers only the Supervisor's proxy (172.30.32.2), as Home Assistant asks.
