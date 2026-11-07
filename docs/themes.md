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

## Making a theme

1. Copy the `web/themes/retro-crt/` folder to `web/themes/my-theme/`.
2. Change the values in `my-theme/theme.css`. Folder names may use lowercase letters, numbers, and
   hyphens.
3. Rebuild the image and set `OUTPOST_THEME=my-theme`.

Paths in `url(...)` inside `theme.css` are relative to the theme's folder, so a font in
`my-theme/fonts/` is `url("fonts/MyFont.woff2")`.

### Moving a theme from before 0.5.0

Before 0.5.0 a theme was a single file, `web/themes/my-theme.css`. Those files are no longer loaded,
and Outpost logs a warning for each one at startup. Move the file to `web/themes/my-theme/theme.css`;
the `OUTPOST_THEME` value stays the same. If the theme used `url(...)` paths, add `../` to each one,
or move those files into the theme's folder.

### Theme names in the switcher

The switcher lists every folder in `web/themes/` that has a `theme.css`. Its label is the text before
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
| `--title-spacing` | Letter spacing of the "OUTPOST" title |

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
