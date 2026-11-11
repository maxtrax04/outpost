# Themes

A theme is a folder in `web/themes/` with a `theme.css` file that sets a handful of CSS variables
("tokens"). All layout lives in `web/style.css` and only reads those tokens, so a theme never has to
touch the layout.

```
web/themes/
  retro-crt/
    theme.css
  my-theme/
    theme.css
    fonts/       optional: fonts and images that belong to this theme
```

## Choosing a theme

Set `OUTPOST_THEME` in your `.env` (or container settings) to the folder name:

| Value | Look |
|---|---|
| `retro-crt` (default) | Green phosphor terminal, scanlines, glow |
| `amber-terminal` | Single-color amber monochrome monitor |
| `command-center` | Cool blue tactical display, thin borders |
| `modern-dark` | Flat, rounded, no effects; uses system fonts |
| `field-station` | Riveted steel instrument panel with analog dials and hazard stripes |
| `atomic-broadcast` | A 1950s television set: cabinet, test card, and a news crawl for alerts; fits the screen |
| `ink` | Black on white for ePaper displays; no effects, fits the screen |

Restart the container after changing it. The dashboard picks up the change on its next refresh.

To preview a theme without changing anything, add `?theme=name` to the address,
for example `http://localhost:8088/?theme=modern-dark`.

Viewers can also switch themes with the on-screen button in the bottom-left corner. Their choice is
saved in their own browser (local storage) and wins over `OUTPOST_THEME`; "Use server default"
clears it. The address `?theme=` setting wins over both. Set `OUTPOST_THEME_SWITCHER=false` to remove
the button.

If the name is misspelled or the folder has no `theme.css`, Outpost logs a warning and uses `retro-crt`.

## Adding themes without rebuilding

Mount a folder of your own themes at `/config/themes` in the container. Each theme is a folder in it,
laid out exactly like the built-in ones:

```
themes/                 mounted at /config/themes
  sonar/
    theme.css
    grid.svg
```

With Docker Compose, add a line under `volumes:` in `docker-compose.yml`:

```yaml
    volumes:
      - ./data:/data
      - ./themes:/config/themes:ro
```

With plain Docker, add `-v ./themes:/config/themes:ro`. On unRAID, see
[Running on unRAID](../README.md#running-on-unraid) in the README.

Then:

- Restart the container so the new themes appear in the on-screen switcher, or set
  `OUTPOST_THEME=sonar` to make one the default for everyone. Edits to a theme's files show up when
  the page is reloaded.
- A custom theme with the same name as a built-in one (for example `retro-crt`) replaces it. Any file
  the custom folder does not have is taken from the built-in theme.
- Only theme files are served from the folder: `.css`, fonts (`.woff2`, `.woff`, `.ttf`, `.otf`), and
  images (`.png`, `.jpg`, `.jpeg`, `.gif`, `.webp`, `.avif`, `.svg`). Anything else, and any file or
  folder whose name starts with a dot, is never sent to browsers. Everything that is served can be
  downloaded by anyone who can open the dashboard.
- At startup the log lists the custom themes it found, and explains any folder it had to skip (a name
  with capital letters or spaces, or no `theme.css`).

To try it, copy the example theme from the repository: `cp -r examples/themes/sonar themes/`.
`sonar` is a deep teal theme with a faint grid, and shows how a theme uses a file from its own folder.

### Themes in a username folder

A folder that has no `theme.css` but holds theme folders is a username folder, as in the
[community themes](../README.md#community-themes) repository. Its themes are named `<username>/<theme>`:

```
themes/                 mounted at /config/themes
  sonar/                sonar
  maxtrax04/
    weather-desk/       maxtrax04/weather-desk
      theme.css
```

That is how a clone of the community repository works as a mounted folder. A theme there that builds
on a built-in one reaches it one folder further up: `@import url("../../atomic-broadcast/theme.css");`.

Themes are looked up in this order, and the first one found wins: the mounted folder, downloaded community
themes (`OUTPOST_COMMUNITY_THEMES`), then the built-in themes. The same goes for each file a theme uses.

## Making a theme

1. Copy the `web/themes/retro-crt/` folder to `web/themes/my-theme/`, or to `my-theme/` in your
   mounted themes folder.
2. Change the values in `my-theme/theme.css`. Folder names may use lowercase letters, numbers, and
   hyphens.
3. Set `OUTPOST_THEME=my-theme`, then restart the container (mounted folder) or rebuild the image
   (`web/themes/`).

Paths in `url(...)` inside `theme.css` are relative to the theme's folder, so a font in
`my-theme/fonts/` is `url("fonts/MyFont.woff2")`.

A theme can only use files served by Outpost: its own folder, `assets/`, or another theme. Fonts and
images from other sites (such as a web font service), `@import` of a remote stylesheet, and `data:` URLs
are blocked by the browser, because of Outpost's Content-Security-Policy (see
[SECURITY.md](../SECURITY.md#security-headers)). Download the file into the theme's folder instead.

### Moving a theme from before 0.5.0

Before 0.5.0 a theme was a single file, `web/themes/my-theme.css`. Those files are no longer loaded,
and Outpost logs a warning for each one at startup. Move the file to `web/themes/my-theme/theme.css`;
the `OUTPOST_THEME` value stays the same. If the theme used `url(...)` paths, add `../` to each one,
or move those files into the theme's folder.

### Theme names in the switcher

The switcher lists every folder in `web/themes/` and the mounted themes folder that has a `theme.css`.
Its label is the text before
the first colon in the file's opening comment, so `/* Retro CRT: green phosphor terminal */` shows as
"Retro CRT". Without such a comment, the folder name is used with hyphens turned into spaces
("my-theme" becomes "My Theme").

### Tokens

| Token | What it controls |
|---|---|
| `--bg` | Page background color |
| `--bg-glow` | Soft light in the middle of the background (use a transparent color for none) |
| `--panel` | Panel background |
| `--cell-bg` | Background of small boxes inside panels |
| `--text` | Main text and icon color |
| `--text-dim` | Secondary text |
| `--accent` | Location name, condition text, highlights |
| `--warn` | Moderate alerts |
| `--danger` | Severe alerts and the warning banner |
| `--danger-bg` | Warning banner background |
| `--border` | Border color |
| `--border-width` | Panel border thickness |
| `--radius` | Corner rounding (`0` is square) |
| `--text-glow` | Text glow (a `text-shadow` value, or `none`) |
| `--icon-glow` | Icon glow (a `filter` value such as `drop-shadow(...)`, or `none`) |
| `--scanlines` | Scanline strength from `0` (off) to `1`. It also sets the strength of the rolling band, a soft band in `--text` that drifts down the screen |
| `--scan-roll` | How long the rolling band takes to cross the screen (default `9s`); `none` stops it |
| `--font-display` | Title and large temperature |
| `--font-body` | Everything else |
| `--title-logo` | `1` shows the Outpost logo as the title, `0` shows the word OUTPOST in `--font-display` |
| `--title-spacing` | Letter spacing of the text title (when `--title-logo` is `0`) |

### Logo

The header shows the Outpost logo, tinted with `--text` and glowing with `--icon-glow`, when a theme sets
`--title-logo: 1`. With `--title-logo: 0` it shows the word OUTPOST in the theme's display font and
`--title-spacing` instead (`modern-dark` does this). Screen readers read "OUTPOST" either way.

To show your own logo, add a rule to your `theme.css` and put the file in the theme's folder. Draw it in
one color (the color is replaced by `--text`) and set its width-to-height ratio:

```css
.title-logo {
    -webkit-mask-image: url("logo.svg");
    mask-image: url("logo.svg");
    aspect-ratio: 3 / 1;
}
```

A theme can also include normal CSS rules for one-off tweaks (see `command-center/theme.css`),
but prefer tokens so your theme keeps working as the layout evolves.

### Decorations and gauges

Tokens change colors and sizes. For frames, plates, stripes, and dials, a theme adds normal CSS rules
that use the hooks below. All of them are optional. The built-in `field-station` and `atomic-broadcast`
themes use most of them and are a good place to start.

**Places to draw.** `::before` and `::after` are free on these elements, and each one is
`position: relative`, so `position: absolute` places a decoration inside it.

| Selector | What it is |
|---|---|
| `.panel` | Every panel. One panel: `[data-panel="header"]`, `"banner"` (the warning banner), `"current"`, `"forecast"`, or `"alerts"` |
| `.detail-box` | Each reading in the current-weather panel. One reading: `[data-metric="humidity"]` (names below) |
| `.forecast-card` | Each forecast day |
| `.frame` | An empty layer over the whole screen, above the content and scanlines, for a bezel. Set `--frame-inset` (for example `--frame-inset: 32px;` in `:root`) to move the content in from the edges so the bezel does not cover it, and `--frame-inset-bottom` as well for a bezel with a deeper bottom edge |

Decorations must not cover text, and should not catch taps (`.frame` already ignores them).

**Values for gauges.** Each reading is given to CSS as a number from `0` to `1`, so a dial or bar
needs no code. The scale stays the same whatever units the dashboard shows. A value outside the range
stops at `0` or `1`.

| Reading | `data-metric` | Property on the page | `0` | `1` |
|---|---|---|---|---|
| Temperature | `temperature` | `--wx-temperature` | -20 °F | 120 °F |
| Feels like | `feels-like` | `--wx-feels-like` | -20 °F | 120 °F |
| Humidity | `humidity` | `--wx-humidity` | 0% | 100% |
| Wind | `wind` | `--wx-wind` | 0 mph | 60 mph |
| Pressure | `pressure` | `--wx-pressure` | 28.5 inHg (965 hPa) | 31 inHg (1050 hPa) |
| UV index | `uv` | `--wx-uv` | 0 | 11 |
| Visibility | `visibility` | `--wx-visibility` | 0 mi | 10 mi |

The element with that `data-metric` also gets the value as `--value` and a `data-gauge` attribute, so
one rule can draw every dial. When a reading is not available, `--value` and `--wx-<name>` are removed
and the element gets `data-missing`. The `sunrise`, `sunset`, and `updated` boxes have a `data-metric`
but no value.

Each forecast card gets `--wx-high` and `--wx-low` (same scale as temperature), `--wx-rain` (chance of
rain, 0 to 100%), and `--wx-uv`.

For example, a needle in the corner of every reading that has a value:

```css
.detail-box[data-gauge]:not([data-missing])::after {
    content: "";
    position: absolute;
    right: 14px;
    bottom: 10px;
    width: 2px;
    height: 16px;
    background: var(--accent);
    transform-origin: bottom center;
    transform: rotate(calc(-90deg + var(--value) * 180deg));
}
```

Images a theme draws with (a dial face, a bezel, a stripe tile) go in its folder, like any other file.
For a frame that fits any screen shape, use `border-image` with a nine-slice image: its corners keep
their size and its edges stretch, so one file works on a phone, a portrait tablet, and a wide screen.

### Fit to screen

A theme styled as a single screen (a television, a wall panel, a device) can have the whole dashboard
fit the screen without scrolling. Set these in its `:root`:

| Token | What it does |
|---|---|
| `--fit-screen` | `1` turns fitting on |
| `--fit-width` | How wide the page may get while fitting (default `1200px`; `100vw` uses the full width) |
| `--fit-max-scale` | How much the page may grow on big screens, from `1` (the default: shrink only) to `4` |

While it is on, `<html>` has `data-fit="on"` and `--fit-scale` (the scale in use), and `<main>` is zoomed
by that scale. It never shrinks below `0.55`, because tiny text is worse than scrolling: a screen that
would need more (a phone in portrait, say) gets the normal layout and scrolls. Add `?fit=on` or `?fit=off`
to the address to try it with any theme.

Anything inside `<main>` with `position: fixed` is zoomed too, so divide its offsets by the scale, for
example `bottom: calc(10px / var(--fit-scale, 1))`. `.frame` is outside `<main>` and is never zoomed.

### Page state

These attributes on `<html>` let a theme react to the page's state with selectors such as
`:root[data-signal="offline"] .frame::after`.

| Attribute | Values |
|---|---|
| `data-theme` | The theme in use |
| `data-signal` | The weather data: `waiting` (not loaded yet), `ok`, `degraded` (old or partial data, such as the last good data kept after a failed update), or `offline` (the data could not be read) |
| `data-effects` | `full` or `reduced` (see [Reduced effects](#reduced-effects)) |
| `data-clock` | `12`, `24`, or `auto` (the browser's language decides) |
| `data-fit` | `on` while [fitting to the screen](#fit-to-screen) |

### Alerts

Each alert is a `.alert-item` (also a `.detail-box`) with a `.severity-<level>` class: `extreme`, `severe`,
`moderate`, `minor`, or `unknown`. Inside it are `.alert-title`, `.alert-description`, and `.alert-expires`
(the end time, when there is one), separated by `<br>`. The alerts panel (`#alertsPanel`) gets `.alert-active`
when any alert is severe or extreme. `#alerts` gets `--alert-chars`, the amount of alert text, so a theme
that scrolls alerts like a news crawl can keep the speed readable, for example
`animation-duration: calc(var(--alert-chars) * 0.12s)`.

With no alerts, the page shows one of two quiet states, depending on `OUTPOST_ALERTS_ALWAYS_SHOW`:

- `true`: the panel stays, with a "no active alerts" line and no `.alert-item`. Select it with
  `#alertsPanel:not(:has(.alert-item))`.
- `false`: the panel is hidden, and a one-line note, `#alertsStatus`, says when alerts were last checked.

To see how a theme shows alerts, run the mock provider with `OUTPOST_MOCK_ALERTS=true`. It always includes
one severe, one moderate, and one minor alert.

### Reduced effects

When effects are reduced (see "Reduced effects" in the [README](../README.md#reduced-effects)), the page has
`data-effects="reduced"` on `<html>`. Outpost then sets `--scanlines: 0`, `--text-glow: none`, and
`--icon-glow: none` over any theme, and stops all animations and transitions. A theme does not need to
do anything for those.

If a theme adds its own effects, such as a flicker, a glowing bezel, a moving needle, or a busy background
image, turn them off there too:

```css
:root[data-effects="reduced"] .frame { box-shadow: none; }
:root[data-effects="reduced"] body { background-image: none; }
```

Decorations that do not move, such as a plain bezel or a dial face, can stay.

### Fonts in themes

Only use fonts you can legally ship. The bundled Share Tech Mono is available to every theme,
and system font stacks (like `modern-dark` uses) need no files at all. If your theme needs another
font, put it in the theme's folder (for example `my-theme/fonts/`) with its license file beside it,
and list it in `THIRD_PARTY.md`. A font several themes share can go in `assets/fonts/` instead
(see `assets/fonts/README.md`).

### Icons

Weather icons are tinted with `--text` and glow with `--icon-glow`, so a theme changes their
color without any extra work.
