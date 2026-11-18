# Map design note

Status: design for [#32](https://github.com/maxtrax04/outpost/issues/32), decided 2026-11-17. Step 1 (the base map) is
built in 0.7.0-beta.7, step 2 (radar) in 0.7.0-beta.8. The README's "Map" section is the user guide.

## What

An optional map panel, off by default (`OUTPOST_MAP=false`), centered on the place shown (home, a
searched place, or "my location"), with the rain radar on top. It is a fixed picture at a set zoom,
not a map you pan, so it suits wall displays, slow tablets, and ePaper, and fetches only the few
tiles on screen.

## Decisions

### OpenStreetMap vector tiles, drawn by Outpost

The base map uses the OpenStreetMap Foundation's vector tiles (`vector.openstreetmap.org`, the
Shortbread schema), which need no key. Vector tiles are data, not pictures, so the dashboard draws
them itself on a 2D canvas (`web/mvt.js` decodes a tile, `web/map.js` draws it): land, water,
main roads, borders, and place names, in the active theme's colors and font. No map library, no
WebGL, and no font files are needed.

Considered and not chosen:

- **MapLibre GL** draws vector tiles beautifully, but it is about 800 KB, needs WebGL (which many
  wall tablets and ePaper browsers lack), and needs font files for labels.
- **Raster tiles** (OpenStreetMap PNGs, or CARTO, which has needed a key since September 2026)
  can only be tinted toward a theme with CSS filters.
- **OpenFreeMap** is vector only and does not clearly allow proxying.

### Through Outpost, cached, as the tile policy asks

The screen still talks only to Outpost (its Content-Security-Policy allows nothing else). nginx
fetches tiles at `/tiles/base/{z}/{x}/{y}.mvt` from the configured server and caches them. The
[vector tile policy](https://operations.osmfoundation.org/policies/vector/) "generally does not
recommend" a caching proxy, but allows one that sends a User-Agent the Foundation can use to contact
the operator. So:

- nginx sends Outpost's User-Agent with `OUTPOST_CONTACT` in it, and with the default tile server
  the map stays off until `OUTPOST_CONTACT` is set (Outpost says so at startup).
- The cache honors the server's caching headers (it currently says 5 minutes, then revalidates with
  `If-Modified-Since`, which costs a "not modified" answer), and serves the last copy while a tile is
  revalidated or the server is down.
- Only tiles a screen is showing are fetched: nothing is prefetched or downloaded in bulk.
- The tile address is a setting (`OUTPOST_MAP_TILES`), so it can change without an update, for
  example to a self-hosted Shortbread server.
- The map credits "© OpenStreetMap" with a link, in the bottom-right corner.

The tile server's name is resolved when a tile is asked for, not when nginx starts, so the dashboard
still starts without internet.

### Radar: NOAA in the US, RainViewer elsewhere (step 2)

- **In the US**, NOAA's MRMS base-reflectivity mosaic, a public WMS service (`opengeo.ncep.noaa.gov`),
  updated every 2 minutes, for the lower 48 states, Alaska, Hawaii, Guam, and the Caribbean.
  Outpost already knows offline whether a place is in the US (`regions.py`).
- **Elsewhere**, [RainViewer](https://www.rainviewer.com/api.html): free, no key, the past 2 hours in
  10-minute steps, zoom 7 at most (drawn larger above that), one color scheme, and
  "for personal and educational use", which a self-hosted home dashboard is. It must be credited.
- Both go through Outpost and are cached too. nginx cannot work out a WMS bounding box (NOAA's
  GeoServer has no tile cache open to the public), so radar tiles go to the Outpost server
  (`app/outpost_radar.py`), which fetches them and says to keep them for 3 hours: a tile names its
  frame, so it never changes. nginx caches them (`outpost_radar_cache`, 50 MB).
- `/api/radar` lists the frames for a place: the latest, and before it one every 10 minutes over the
  past 2 hours. The server fetches a tile only for a frame it has listed in the last 3 hours, at the
  map's zoom, at most 300 a minute between all screens. Lists are kept for 2 minutes and used while
  a service is down.
- Which service covers a place is worked out offline from rough boxes (`regions.noaa_radar_area`):
  the lower 48 states (which also takes in southern Canada, whose radars the mosaic includes),
  Alaska, Hawaii, Guam, and Puerto Rico, without northern Mexico and the Bahamas.
- The radar is drawn between the base map and its names, at 75% opacity. The base map and the names
  are drawn once into layers of their own, so a loop only puts three layers together for each frame.
- The latest frame is shown. `OUTPOST_MAP_RADAR_LOOP=true` plays the past 2 hours as a loop instead,
  except on ePaper and with reduced effects. `OUTPOST_MAP_RADAR=false` leaves the radar off.

### Themes

The map takes its colors from CSS custom properties, which a theme can set: `--map-land`,
`--map-water`, `--map-road`, `--map-border`, `--map-label`, and `--map-marker`. Without them,
they are worked out from the theme's own colors (`--bg`, `--text`, `--accent`), so every theme,
including community themes, gets a matching map.

## Settings

| Setting | Default | Meaning |
| :--- | :--- | :--- |
| `OUTPOST_MAP` | `false` | Show the map panel. |
| `OUTPOST_MAP_ZOOM` | `7` | 4 (a large region) to 12 (a town). Radar is sharpest at 7 or less. |
| `OUTPOST_MAP_TILES` | `https://vector.openstreetmap.org/shortbread_v1/{z}/{x}/{y}.mvt` | Where vector tiles come from. Must use the Shortbread schema. |
| `OUTPOST_MAP_RADAR` | `true` | Rain radar on the map. |
| `OUTPOST_MAP_RADAR_LOOP` | `false` | Play the past 2 hours instead of the latest frame. |

## Plan

1. **Base map:** the nginx tile cache, `OUTPOST_MAP`, `OUTPOST_MAP_ZOOM`, `OUTPOST_MAP_TILES`, the
   decoder and renderer, theme colors, and the credit.
2. **Radar:** NOAA and RainViewer through Outpost, the loop setting, and their credits.
