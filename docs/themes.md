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
| `--scanlines` | Scanline strength from `0` (off) to `1` |
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

### Fonts in themes

Only use fonts you can legally ship. The bundled Share Tech Mono is available to every theme,
and system font stacks (like `modern-dark` uses) need no files at all. If your theme needs another
font, put it in the theme's folder (for example `my-theme/fonts/`) with its license file beside it,
and list it in `THIRD_PARTY.md`. A font several themes share can go in `assets/fonts/` instead
(see `assets/fonts/README.md`).

### Icons

Weather icons are tinted with `--text` and glow with `--icon-glow`, so a theme changes their
color without any extra work.
