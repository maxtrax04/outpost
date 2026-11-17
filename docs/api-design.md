# API design note

Status: steps 1 to 3 built (0.7.0-beta.3 to beta.5); design for [#29](https://github.com/maxtrax04/outpost/issues/29). Location search ([#30](https://github.com/maxtrax04/outpost/issues/30))
and "my location" ([#31](https://github.com/maxtrax04/outpost/issues/31)) are built on it, and the map ([#32](https://github.com/maxtrax04/outpost/issues/32)) can use it later.
This page will be replaced by user docs (`docs/api.md`) once the API is built.

## Why

Today one updater writes one file, `/data/weather.json`, for the one location in `OUTPOST_LATITUDE` and
`OUTPOST_LONGITUDE`, and every screen shows that location. To let a viewer look at another place, the
server has to fetch weather for a location the browser asks for. The browser can't fetch it itself: the
dashboard talks only to Outpost (its Content-Security-Policy allows nothing else), so no viewer's browser
contacts a weather service, and API keys stay on the server.

## Decisions

### One Python process, standard library only

The update loop and a small HTTP server run in **one process**, `app/outpost_server.py`, which replaces
`outpost_updater.py --loop` in `start.sh`. It uses `http.server.ThreadingHTTPServer` (Python's standard
library, so the image still has no pip, as rule 3 requires), listening on `127.0.0.1:8081` and reachable only through nginx:

```nginx
location /api/ {
    proxy_pass http://127.0.0.1:8081;
    add_header Cache-Control "no-store";
    include /etc/nginx/outpost/security-headers.conf;
}
```

A single process matters because each provider's response cache and request minimum (0.6.0-beta.10) lives
in memory. With two processes, the home location could be fetched twice, and the per-service limits would
no longer hold. `outpost_updater.py` with no arguments still does one update, for the first update in
`start.sh` and for tests.

A framework (Flask, FastAPI) was considered and not chosen: it would add pip and a dependency to keep
updated, for three small endpoints.

### `weather.json` stays

The home location is still written to `/data/weather.json` on every update, unchanged, for Home Assistant,
scripts, the health check, and older dashboards. `/api/weather` with no location returns that same
data, so a screen that never chooses a place costs nothing extra.

### Location search on by default, with limits

Decided on 2026-11-16 (see #29): viewers can choose other places unless the owner turns it off. When it
is on, anyone who can open the dashboard can make the server fetch weather, using the owner's provider
quotas. Every request is limited by the following:

| Limit | How | Setting |
| :--- | :--- | :--- |
| On or off | `/api/weather` with a location, and `/api/places`, return 403 when off. The dashboard hides the search. | `OUTPOST_LOCATION_SEARCH=true` (default) |
| Nearby places share data | Coordinates are rounded to 2 decimals (about 1 km) before anything is fetched or cached. | none |
| Fetches per hour | At most this many weather fetches an hour for places other than home, new places and refreshes counted together. Over the limit, a place fetched before gets its last answer again (its "Updated" time shows its age), and a new place gets 429, which the dashboard shows as "Too many places looked up; try again later". Home is never limited. | `OUTPOST_LOCATION_LIMIT=30` |
| Pirate Weather budget | Searched places use the Pirate Weather key only while there is quota to spare: Pirate Weather reports the calls left this month and when they reset (`RateLimit-Remaining`, `RateLimit-Reset`), and Outpost keeps back what home needs until the reset (one call per 10 minutes at most), plus 10%. Without that spare quota, or before Pirate Weather has reported it, a searched place uses Open-Meteo instead, so home never runs out. | `OUTPOST_LOCATION_PIRATEWEATHER=true` (default; `false` keeps the key for home only) |
| How long a place is kept | A place nobody has asked for in an hour is dropped. At most 50 are kept in memory, never on disk. | none |
| Searches | Place-name searches are cached for a day, at most 1 search per second goes to the geocoding service, and queries are 2 to 100 characters. | none |
| Per browser | nginx `limit_req` on `/api/`: 5 requests a second per address, with bursts of 20, against scripts hammering the API. Behind a reverse proxy, every viewer shares the proxy's address, so the limit is generous. | none |

The fetch limit is what bounds the cost, since refreshes count too. Thirty fetches an hour is at most
about 60 requests an hour to Open-Meteo, counting the gap fill (its free tier allows 10,000 a day), and a
few more to NWS or MET Norway, which have no fixed quota but ask for reasonable use. A viewer coming back
to a place still in the cache costs nothing. Pirate Weather, the only service with a small monthly quota,
is used for searched places only from the quota home won't need.

For example, with 10,000 calls a month and 10 days to the reset, home needs at most 1,440 calls (1,584
with the margin). If 6,000 are left, searched places may use 4,416 of them. If only 1,500 are left,
searched places use Open-Meteo until the reset.

### Other places are fetched only when asked

The home location keeps updating on its timer. Another place is fetched when a screen asks for it, and its
answer is reused for `OUTPOST_UPDATE_INTERVAL` or the service's own minimum, whichever is longer, the same
as at home. A screen showing a searched place asks every minute, as it does for `weather.json` today, so
the place stays fresh for as long as someone is looking at it. Two screens asking for the same place at the
same moment share one fetch (one lock per place).

Each place uses the same provider choice as home (`OUTPOST_PROVIDER`, with `auto` picking MET Norway in
the Nordic countries, NWS in the US, and so on, worked out offline in `regions.py`) and the same alerts
choice.

### Per-location state instead of reading `weather.json` back

Keeping the last good data when a provider fails, deciding when `auto` switches to Open-Meteo, and
keeping the last alerts when an alerts lookup fails all work today by reading `weather.json` back. They
move to a small `LocationState` per place: the last good payload, kept in memory. For home it is also
loaded from and saved to `weather.json`, so behavior across restarts is unchanged. The module-level
`LATITUDE`/`LONGITUDE`/`LOCATION_NAME` become a `Location` passed through `fetch_weather`,
`resolve_alerts`, and `build_payload`. This refactor changes no behavior and comes first, in its own PR.

## Endpoints

All answers are JSON with `Cache-Control: no-store`. Every error has the form `{"error": "<code>", "message": "<text>"}`.

### `GET /api/weather`

| Parameter | Meaning |
| :--- | :--- |
| *(none)* | The home location: the same as `weather.json`. |
| `lat`, `lon` | Another place, in decimal degrees (rounded to 2 decimals). Both or neither. |
| `name` | The name to show for it, from the search result. Plain text, at most 80 characters. Without it, the dashboard shows "Selected location". |

The answer is a `weather.json` payload in the same format (schema version 1). `location` and
`coordinates` are the requested place, and the coordinates are the rounded ones. A provider failure is not
an HTTP error: as with `weather.json`, `status` is `degraded` or `error`, and the dashboard shows it the
same way. HTTP errors are for the request itself: 400 for bad coordinates, 403 when search is off, 429 over
the hourly limit.

### `GET /api/places?q=<text>`

Searches for places by name, for the search box. It returns up to 8 results:

```json
{ "places": [ { "name": "Cinder Flats", "region": "Example State", "country": "Exampleland",
                "latitude": 10.0, "longitude": 20.0, "timezone": "America/Chicago" } ],
  "source": { "id": "openmeteo", "name": "Open-Meteo.com" } }
```

Searches go to the [Open-Meteo geocoding API](https://open-meteo.com/en/docs/geocoding-api), which needs
no key and is already credited in the footer. Nominatim (OpenStreetMap) was considered; its usage
policy rules out search-as-you-type, and it allows 1 request a second for everyone. The search box
therefore searches when the viewer presses Enter or pauses typing, not on every key.

### `GET /api/status`

`{"location_search": true}` and the API version, so the dashboard knows whether to show the search box
and that the API exists at all.

## Dashboard

- **Where it reads from.** The dashboard reads `api/weather` (with the chosen place, if any). If that fails
  with 404, because the page is served without the API (an old proxy setup or a plain file server), it
  falls back to `data/weather.json`. The paths stay relative (`api/...`, not `/api/...`), so they also
  work under a path prefix, as the Home Assistant add-on's ingress needs (#34).
- **Choosing a place.** A search box and a list of saved places in the theme panel. Saved places and the
  current choice are stored in that browser only (`localStorage`), never on the server (#30).
- **Pinning a screen.** `?lat=..&lon=..&name=..` in the address shows that place on one screen, like
  `?theme=`, for example a wall screen showing a second home. With search off it is refused like any
  other place, since anyone can edit an address.
- **My location.** A button that asks the browser for its location (HTTPS only), then uses it like a
  search result (#31).
- **Night dimming** uses the chosen place's sunrise and sunset, not home's.

## Privacy

- A viewer's chosen place is sent to Outpost and then to the weather services, as home is. It is not
  logged: the log says "fetched a searched place", without coordinates. It is not written to disk.
- Search text is sent to Open-Meteo's geocoding service. The README will say so.
- `weather.json` still contains only home.

## Not in this work

- Viewer-chosen units (`units=metric` per screen). It would be easy later, because readings are converted
  after fetching, but it is not part of #29.
- Authentication. Outpost is meant for a home network. With search on and Outpost exposed to the
  internet, the limits above bound the cost, but anyone can use them; the README will recommend a
  reverse proxy with authentication, or `OUTPOST_LOCATION_SEARCH=false`.
- Map tiles (#32). They will go through nginx's own proxy cache, not this server.

## Plan

Each step is its own PR and beta:

1. **Refactor:** `Location` and `LocationState` replace the module globals and reading the file back. No
   behavior change, and the existing tests pass unchanged.
2. **Server:** `outpost_server.py` with `/api/weather` and `/api/status`, nginx `/api/` with `limit_req`,
   `OUTPOST_LOCATION_SEARCH`, `OUTPOST_LOCATION_LIMIT`, and `OUTPOST_LOCATION_PIRATEWEATHER` (in
   `.env.example`, the README, and tests), and
   the dashboard reading `api/weather` with the `data/weather.json` fallback.
3. **Search (#30):** `/api/places`, the search box and saved places, and `?lat=&lon=&name=`.
4. **My location (#31):** the button, permission and HTTPS handling, and reverse-proxy docs.

## Decided on review (2026-11-16)

1. `OUTPOST_LOCATION_LIMIT` defaults to 30 fetches an hour: about 7 places watched continuously, each
   refreshing every 15 minutes at Open-Meteo's minimum.
2. Searched places may use the Pirate Weather key within the spare quota (above), with
   `OUTPOST_LOCATION_PIRATEWEATHER` to turn that off.
3. A pinned screen (`?lat=&lon=`) is refused when search is off, since anyone who can open the dashboard
   can edit its address.
