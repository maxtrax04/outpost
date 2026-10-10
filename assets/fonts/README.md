# Bundled fonts

Outpost ships its fonts with the app so users never have to download anything.
Only fonts under licenses that allow redistribution belong in this folder.

## Current fonts

| Font | File(s) | License | Used for |
|---|---|---|---|
| [Share Tech Mono](https://fonts.google.com/specimen/Share+Tech+Mono) | `ShareTechMono-Regular.ttf`, `ShareTechMono-OFL.txt` | SIL Open Font License 1.1 | All text (Retro CRT theme) |

## Adding Share Tech Mono (one-time, for maintainers)

1. Download it from [Google Fonts](https://fonts.google.com/specimen/Share+Tech+Mono) (**Get font**, then **Download all**).
2. From the download, copy these two files into this folder:
   - `ShareTechMono-Regular.ttf`
   - the license file (usually `OFL.txt`), renamed to `ShareTechMono-OFL.txt`
3. Rebuild the image. The font is then packaged with the app.

Use the font file as downloaded. Do not rename or edit it; the OFL reserves the font's name for the unmodified original.

## Rules for any font added here

- It must be licensed for redistribution (the SIL Open Font License is the usual choice).
- Keep its license file next to it, and list it in `THIRD_PARTY.md`.
- Check the license on the font's own page. Many "free" fonts are free for personal use only.
