#!/usr/bin/env python3
"""
The map panel's settings, and the nginx snippet that fetches and caches its tiles (docs/map-design.md).

The dashboard asks Outpost for /tiles/base/{z}/{x}/{y}.mvt, and nginx fetches each tile from
OUTPOST_MAP_TILES (OpenStreetMap's vector tiles by default) and caches it, honoring the tile
server's caching headers. As the OpenStreetMap vector tile policy asks of a caching proxy, nginx
sends a User-Agent the operator can be reached through (OUTPOST_CONTACT), so with the default
tile server the map stays off until OUTPOST_CONTACT is set.

Only the tiles at OUTPOST_MAP_ZOOM are passed on, so Outpost is never an open tile proxy. The
tile server's name is looked up when a tile is asked for, not when nginx starts, so the dashboard
still starts without internet.

With OUTPOST_MAP_RADAR (on by default), radar tiles at /tiles/radar/... go to the Outpost server
(app/outpost_radar.py), which fetches them from NOAA or RainViewer, and nginx caches them too.

Uses only the Python standard library.
"""

import os
import re
import sys
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Tuple

SNIPPET_PATH = Path("/etc/nginx/outpost/map.conf")
RESOLV_CONF = Path("/etc/resolv.conf")
# Docker's own DNS server, for when /etc/resolv.conf names none
FALLBACK_RESOLVER = "127.0.0.11"

DEFAULT_TILES = "https://vector.openstreetmap.org/shortbread_v1/{z}/{x}/{y}.mvt"
# Tile servers whose policy asks a caching proxy for a contact
CONTACT_REQUIRED_HOSTS = ("vector.openstreetmap.org",)
DEFAULT_ZOOM = 7
MIN_ZOOM = 4
MAX_ZOOM = 12
ATTRIBUTION = "© OpenStreetMap"
ATTRIBUTION_URL = "https://www.openstreetmap.org/copyright"

# scheme://host[:port]/path/{z}/{x}/{y}.ext, with nothing nginx could read as syntax or a variable
TILES_PATTERN = re.compile(
    r"(?P<scheme>https?)://(?P<host>[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]*[A-Za-z0-9])?)*)"
    r"(?::(?P<port>\d{1,5}))?(?P<prefix>/(?:[A-Za-z0-9._~-]+/)*)\{z\}/\{x\}/\{y\}(?P<suffix>[A-Za-z0-9._~-]*)"
)


def _warn(message: str) -> None:
    print(f"[Outpost] {message}", file=sys.stderr, flush=True)


def flag(value: Optional[str], default: bool) -> bool:
    text = (value or "").strip().lower()
    if not text:
        return default
    return text not in ("0", "false", "no", "off")


def zoom_setting(value: Optional[str]) -> Tuple[int, Optional[str]]:
    text = (value or "").strip()
    if not text:
        return DEFAULT_ZOOM, None
    try:
        zoom = int(text)
    except ValueError:
        zoom = -1
    if MIN_ZOOM <= zoom <= MAX_ZOOM:
        return zoom, None
    return DEFAULT_ZOOM, (f"OUTPOST_MAP_ZOOM must be a whole number from {MIN_ZOOM} to {MAX_ZOOM}, "
                          f"got \"{text}\"; using {DEFAULT_ZOOM}")


def tiles_setting(value: Optional[str]) -> Tuple[Dict[str, str], Optional[str]]:
    """The parts of OUTPOST_MAP_TILES: scheme, host, port, prefix, suffix, and the template itself."""
    text = (value or "").strip() or DEFAULT_TILES
    match = TILES_PATTERN.fullmatch(text)
    warning = None
    if not match or (match.group("port") and not 0 < int(match.group("port")) < 65536):
        warning = (f"OUTPOST_MAP_TILES must look like https://example.org/tiles/{{z}}/{{x}}/{{y}}.mvt; "
                   f"using {DEFAULT_TILES}")
        text = DEFAULT_TILES
        match = TILES_PATTERN.fullmatch(text)
    parts = {name: match.group(name) or "" for name in ("scheme", "host", "port", "prefix", "suffix")}
    parts["template"] = text
    return parts, warning


def settings(env: Optional[Mapping[str, str]] = None, contact: str = "") -> Dict[str, Any]:
    """
    {"enabled", "zoom", "tiles" (the parts), "problems" (warnings to print)}. "enabled" is what
    the dashboard is told: off when OUTPOST_MAP is, or when the tile server needs a contact and
    OUTPOST_CONTACT is not set.
    """
    env = os.environ if env is None else env
    problems: List[str] = []
    zoom, warning = zoom_setting(env.get("OUTPOST_MAP_ZOOM"))
    if warning:
        problems.append(warning)
    tiles, warning = tiles_setting(env.get("OUTPOST_MAP_TILES"))
    if warning:
        problems.append(warning)

    enabled = flag(env.get("OUTPOST_MAP"), False)
    if enabled and tiles["host"].lower() in CONTACT_REQUIRED_HOSTS and not contact.strip():
        problems.append(f"The map is off: {tiles['host']} asks Outpost to say how to reach you, so set "
                        f"OUTPOST_CONTACT (an email address or website), or set OUTPOST_MAP_TILES to another tile server")
        enabled = False
    radar = enabled and flag(env.get("OUTPOST_MAP_RADAR"), True)
    radar_loop = radar and flag(env.get("OUTPOST_MAP_RADAR_LOOP"), False)
    return {"enabled": enabled, "zoom": zoom, "tiles": tiles, "radar": radar, "radar_loop": radar_loop,
            "problems": problems}


def config(map_settings: Dict[str, Any]) -> Dict[str, Any]:
    """The "map" block of config.json, for the dashboard."""
    return {
        "enabled": map_settings["enabled"],
        "zoom": map_settings["zoom"],
        "attribution": ATTRIBUTION,
        "attribution_url": ATTRIBUTION_URL,
        "radar": map_settings["radar"],
        "radar_loop": map_settings["radar_loop"],
    }


def resolvers(text: str) -> List[str]:
    """The name servers in a resolv.conf, ready for nginx's resolver directive (IPv6 in brackets)."""
    found = []
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[0] == "nameserver":
            address = parts[1].split("%")[0]
            if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", address):
                found.append(address)
            elif re.fullmatch(r"[0-9A-Fa-f:]+", address) and ":" in address:
                found.append(f"[{address}]")
    return found


def nginx_text(value: str) -> str:
    """Text safe inside a double-quoted nginx string: no quotes, backslashes, or $ (a variable)."""
    return re.sub(r'["\\$\x00-\x1f\x7f]', "", value)


def nginx_snippet(map_settings: Dict[str, Any], user_agent: str, servers: List[str]) -> str:
    header = "# Written by /app/outpost_map.py at startup; edits here are overwritten.\n"
    if not map_settings["enabled"]:
        return header + "# The map is off, so no tiles are fetched (nginx/default.conf answers /tiles/ with 404).\n"

    tiles = map_settings["tiles"]
    host = tiles["host"]
    authority = f"{host}:{tiles['port']}" if tiles["port"] else host
    zoom = map_settings["zoom"]
    lines = [
        header,
        "# Map tiles (docs/map-design.md): only the zoom the dashboard draws, cached as the tile server says.",
        f"resolver {' '.join(servers or [FALLBACK_RESOLVER])} ipv6=off valid=300s;",
        "resolver_timeout 5s;",
        "",
        f'location ~ "^/tiles/base/{zoom}/(?<outpost_tile_x>[0-9]{{1,4}})/(?<outpost_tile_y>[0-9]{{1,4}})\\.mvt$" {{',
        "    # Tile numbers say roughly which place a screen shows, so they are not logged",
        "    access_log off;",
        "    error_log /var/log/nginx/error.log crit;",
        "    limit_req zone=outpost_tile_rate burst=40 nodelay;",
        "    limit_req_status 429;",
        f'    set $outpost_tile_server "{authority}";',
        f"    proxy_pass {tiles['scheme']}://$outpost_tile_server{tiles['prefix']}{zoom}/$outpost_tile_x/$outpost_tile_y{tiles['suffix']};",
        "    proxy_http_version 1.1;",
        f'    proxy_set_header Host "{authority}";',
        f'    proxy_set_header User-Agent "{nginx_text(user_agent)}";',
        '    proxy_set_header Accept-Encoding "gzip";',
        '    proxy_set_header Cookie "";',
        '    proxy_set_header Authorization "";',
        '    proxy_set_header Connection "";',
        "    proxy_ssl_server_name on;",
        f"    proxy_ssl_name {host};",
        "    proxy_ssl_verify on;",
        "    proxy_ssl_trusted_certificate /etc/ssl/certs/ca-certificates.crt;",
        "    proxy_ssl_verify_depth 4;",
        "    proxy_connect_timeout 10s;",
        "    proxy_read_timeout 20s;",
        "    proxy_cache outpost_tile_cache;",
        f'    proxy_cache_key "{authority}{tiles["prefix"]}{zoom}/$outpost_tile_x/$outpost_tile_y{tiles["suffix"]}";',
        "    # The server's Cache-Control and Expires win; 7 days only when it sends neither",
        "    proxy_cache_valid 200 7d;",
        "    proxy_cache_valid 404 1h;",
        "    proxy_cache_revalidate on;",
        "    proxy_cache_lock on;",
        "    proxy_cache_background_update on;",
        "    proxy_cache_use_stale error timeout updating http_500 http_502 http_503 http_504;",
        "    proxy_ignore_headers Set-Cookie;",
        "    proxy_hide_header Set-Cookie;",
        "    gunzip on;",
        "    include /etc/nginx/outpost/security-headers.conf;",
        "}",
        "",
    ]
    if map_settings["radar"]:
        lines += radar_snippet()
    return "\n".join(lines)


# /tiles/radar/noaa/<area>/<frame>/{z}/{x}/{y}.png or /tiles/radar/rainviewer/<frame>/{z}/{x}/{y}.png
RADAR_TILE_PATTERN = (r"^/tiles/radar/(?:noaa/(?:conus|alaska|hawaii|guam|carib)|rainviewer)/[A-Za-z0-9]{1,40}"
                      r"/[0-9]{1,2}/[0-9]{1,5}/[0-9]{1,5}\.png$")


def radar_snippet() -> List[str]:
    """
    Radar tiles: the Outpost server fetches them (it works out NOAA's map area for each tile, and
    accepts only frames it has listed and the map's zoom), and nginx keeps them. A frame never
    changes, so the server says to keep its tiles for hours.
    """
    return [
        "# Radar tiles (app/outpost_radar.py): fetched by the Outpost server, cached here.",
        f'location ~ "{RADAR_TILE_PATTERN}" {{',
        "    access_log off;",
        "    error_log /var/log/nginx/error.log crit;",
        "    # A radar loop asks for a hundred or more tiles at once: they wait their turn, not refused",
        "    limit_req zone=outpost_radar_rate burst=300;",
        "    limit_req_status 429;",
        "    proxy_pass http://127.0.0.1:8081;",
        "    proxy_cache outpost_radar_cache;",
        "    proxy_cache_valid 200 3h;",
        "    proxy_cache_lock on;",
        "    proxy_cache_use_stale error timeout updating;",
        "    include /etc/nginx/outpost/security-headers.conf;",
        "}",
        "",
    ]


def write_snippet(map_settings: Dict[str, Any], user_agent: str, path: Path = SNIPPET_PATH,
                  resolv_conf: Path = RESOLV_CONF) -> None:
    try:
        servers = resolvers(resolv_conf.read_text(encoding="utf-8"))
    except OSError:
        servers = []
    if map_settings["enabled"] and not servers:
        _warn(f"No name server in {resolv_conf}; map tiles will use {FALLBACK_RESOLVER}")
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(nginx_snippet(map_settings, user_agent, servers), encoding="utf-8")
    temp.replace(path)


def summary(map_settings: Dict[str, Any]) -> str:
    if not map_settings["enabled"]:
        return "map off"
    if not map_settings["radar"]:
        radar = "no radar"
    else:
        radar = "radar loop" if map_settings["radar_loop"] else "radar"
    return f"map on (zoom {map_settings['zoom']}, tiles from {map_settings['tiles']['host']}, {radar})"
