# Themes

A theme is one CSS file in `web/themes/` that sets a handful of CSS variables ("tokens").
All layout lives in `web/style.css` and only reads those tokens, so a theme never has to
touch the layout.

## Choosing a theme

Set `OUTPOST_THEME` in your `.env` (or container settings) to the file name without `.css`:

| Value | Look |
|---|---|
| `retro-crt` (default) | Green phosphor terminal, scanlines, glow |
| `amber-terminal` | Single-color amber monochrome monitor |
| `command-center` | Cool blue tactical display, thin borders |
| `modern-dark` | Flat, rounded, no effects; uses system fonts |

Restart the container after changing it. The dashboard picks up the change on its next refresh.

To preview a theme without changing anything, add `?theme=name` to the address,
for example `http://localhost:8088/?theme=modern-dark`.

If the name is misspelled or the file doesn't exist, Outpost logs a warning and uses `retro-crt`.

## Making a theme

1. Copy `web/themes/retro-crt.css` to `web/themes/my-theme.css`.
2. Change the values. Theme names may use lowercase letters, numbers, and hyphens.
3. Rebuild the image and set `OUTPOST_THEME=my-theme`.

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

A theme file can also include normal CSS rules for one-off tweaks (see `command-center.css`),
but prefer tokens so your theme keeps working as the layout evolves.

### Fonts in themes

Only use fonts you can legally ship. The bundled Share Tech Mono is available to every theme,
and system font stacks (like `modern-dark` uses) need no files at all. If your theme needs another
font, add it to `assets/fonts/` with its license and list it in `THIRD_PARTY.md`
(see `assets/fonts/README.md`).

### Icons

Weather icons are tinted with `--text` and glow with `--icon-glow`, so a theme changes their
color without any extra work.
