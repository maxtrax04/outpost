#!/usr/bin/env python3
"""
Outpost server: home's update loop and the API, in one process (docs/api-design.md).

The update loop writes /data/weather.json for home every OUTPOST_UPDATE_INTERVAL seconds, as
`outpost_updater.py --loop` did. The API answers on 127.0.0.1:8081, reached only through nginx at
/api/ (nginx/default.conf):

  GET /api/status                       {"api_version": 1, "version": ..., "location_search": true}
  GET /api/weather                      home: the same as weather.json
  GET /api/weather?lat=..&lon=..&name=..  another place, in the same format
  GET /api/places?q=..                  places matching a name, for the search box (Open-Meteo geocoding)
  GET /api/radar[?lat=..&lon=..]        the map's radar frames for home or another place (outpost_radar.py)
  GET /tiles/radar/...                  a radar tile, through nginx's radar cache

One process, so the providers' response caches and request minimums are shared by home and other
places. Other places are fetched only when a screen asks, at most every PLACE_REFRESH_SECONDS each,
and at most OUTPOST_LOCATION_LIMIT fetches an hour between them. Nothing about them, or about what
was searched for, is written to disk or logged.

Uses only the Python standard library.
"""

import collections
import copy
import json
import math
import re
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import parse_qs, urlsplit

import outpost_map
import outpost_radar
import outpost_updater as u
from providers import geocoding, openmeteo

API_VERSION = 1
HOST = "127.0.0.1"
PORT = 8081

# Coordinates are rounded to this many decimals (about 1 km), so nearby screens share one fetch
COORDINATE_DECIMALS = 2
MAX_NAME_LENGTH = 80
DEFAULT_PLACE_NAME = "Selected location"
# Other places kept in memory, and how long one nobody asks for is kept
MAX_PLACES = 50
FORGET_AFTER_SECONDS = 3600
LIMIT_WINDOW_SECONDS = 3600
# A place being watched is fetched again this often at most: OUTPOST_UPDATE_INTERVAL, or Open-Meteo's
# 15 minutes (the shortest wait any service asks for that changes the answer), whichever is longer
PLACE_REFRESH_SECONDS = max(u.UPDATE_INTERVAL, openmeteo.MIN_REQUEST_SECONDS)


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def coordinate(query: Dict[str, Any], name: str, limit: float) -> float:
    """A latitude or longitude from the query, rounded to COORDINATE_DECIMALS."""
    try:
        value = float(query[name][0])
    except (KeyError, IndexError, ValueError):
        raise ApiError(400, "bad_location", "lat and lon must both be numbers")
    if not math.isfinite(value) or abs(value) > limit:
        raise ApiError(400, "bad_location", f"{name} must be between -{limit:g} and {limit:g}")
    return round(value, COORDINATE_DECIMALS) + 0.0  # + 0.0 turns -0.0 into 0.0


def place_name(query: Dict[str, Any]) -> str:
    """The name to show for a place: plain text, one line, at most MAX_NAME_LENGTH characters."""
    text = (query.get("name") or [""])[0]
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()[:MAX_NAME_LENGTH].strip()
    return text or DEFAULT_PLACE_NAME


class Place:
    def __init__(self, latitude: float, longitude: float) -> None:
        # The name inside the update stays the same, so the fallback (can_keep_previous) always
        # matches; the name a screen asked for is put in its answer instead
        self.location = u.Location(latitude, longitude, DEFAULT_PLACE_NAME)
        self.state = u.LocationState()
        self.lock = threading.Lock()
        self.payload: Optional[Dict[str, Any]] = None
        self.fetched = 0.0
        self.seen = 0.0


class Places:
    """Weather for places other than home, fetched when asked and within OUTPOST_LOCATION_LIMIT."""

    def __init__(self, limit: int, refresh_seconds: float = PLACE_REFRESH_SECONDS,
                 clock: Callable[[], float] = time.time,
                 update: Callable[..., Dict[str, Any]] = u.update_once) -> None:
        self.limit = limit
        self.refresh_seconds = refresh_seconds
        self.clock = clock
        self.update = update
        self._lock = threading.Lock()
        self._places: Dict[Tuple[float, float], Place] = {}
        self._fetches: collections.deque = collections.deque()

    def __len__(self) -> int:
        return len(self._places)

    def _forget(self, now: float) -> None:
        for key in [key for key, place in self._places.items() if now - place.seen > FORGET_AFTER_SECONDS]:
            del self._places[key]
        while len(self._places) >= MAX_PLACES:
            del self._places[min(self._places, key=lambda key: self._places[key].seen)]

    def _take_fetch(self, now: float) -> bool:
        """Count one fetch against the hourly limit; False when the limit is used up."""
        with self._lock:
            while self._fetches and now - self._fetches[0] >= LIMIT_WINDOW_SECONDS:
                self._fetches.popleft()
            if len(self._fetches) >= self.limit:
                return False
            self._fetches.append(now)
            return True

    def weather(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """The place's payload: fetched again when it is older than refresh_seconds and the limit allows."""
        now = self.clock()
        key = (latitude, longitude)
        with self._lock:
            place = self._places.get(key)
            if place is None:
                self._forget(now)
                place = self._places[key] = Place(latitude, longitude)
            place.seen = now

        with place.lock:
            due = place.payload is None or now - place.fetched >= self.refresh_seconds
            if due and self._take_fetch(now):
                place.payload = self.update(place.location, place.state)
                place.fetched = now
            if place.payload is None:
                with self._lock:
                    if self._places.get(key) is place:
                        del self._places[key]
                raise ApiError(429, "location_limit",
                               "Too many places looked up in the last hour; try again later")
            return copy.deepcopy(place.payload)


def home_weather() -> Dict[str, Any]:
    """Home: weather.json as the update loop last wrote it."""
    return u.HomeState().read() or u.build_error_payload("No weather data yet; the first update has not finished")


def status() -> Dict[str, Any]:
    return {"api_version": API_VERSION, "version": u.APP_VERSION, "location_search": u.LOCATION_SEARCH}


def weather(query: Dict[str, Any], places: Places) -> Dict[str, Any]:
    if "lat" not in query and "lon" not in query:
        return home_weather()
    if not u.LOCATION_SEARCH:
        raise ApiError(403, "location_search_off", "Choosing another place is turned off (OUTPOST_LOCATION_SEARCH)")
    latitude = coordinate(query, "lat", 90)
    longitude = coordinate(query, "lon", 180)
    payload = places.weather(latitude, longitude)
    payload["location"] = place_name(query)
    return payload


def search_places(query: Dict[str, Any]) -> Dict[str, Any]:
    """Places matching ?q=, for the search box."""
    if not u.LOCATION_SEARCH:
        raise ApiError(403, "location_search_off", "Choosing another place is turned off (OUTPOST_LOCATION_SEARCH)")
    text = geocoding.clean_query((query.get("q") or [""])[0])
    if not geocoding.MIN_QUERY_LENGTH <= len(text) <= geocoding.MAX_QUERY_LENGTH:
        raise ApiError(400, "bad_query", f"Search for {geocoding.MIN_QUERY_LENGTH} to "
                                         f"{geocoding.MAX_QUERY_LENGTH} characters")
    try:
        places = geocoding.search(text, u.USER_AGENT)
    except RuntimeError as error:
        # The error never includes the search text
        print(f"[Outpost] {error}", file=sys.stderr, flush=True)
        raise ApiError(502, "search_failed", "Place search is not available right now; try again later")
    return {"places": places, "source": geocoding.SOURCE}


def radar_frames(query: Dict[str, Any], radar: Optional[outpost_radar.Radar]) -> Dict[str, Any]:
    """The radar frames for home, or (with location search on) for ?lat=&lon=."""
    if radar is None:
        raise ApiError(404, "radar_off", "The map's radar is off (OUTPOST_MAP, OUTPOST_MAP_RADAR)")
    if "lat" in query or "lon" in query:
        if not u.LOCATION_SEARCH:
            raise ApiError(403, "location_search_off", "Choosing another place is turned off (OUTPOST_LOCATION_SEARCH)")
        latitude, longitude = coordinate(query, "lat", 90), coordinate(query, "lon", 180)
    else:
        latitude, longitude = u.LATITUDE, u.LONGITUDE
    try:
        return radar.answer(latitude, longitude)
    except outpost_radar.RadarError as error:
        print(f"[Outpost] Radar: {error}", file=sys.stderr, flush=True)
        raise ApiError(502, "radar_unavailable", "Radar is not available right now; try again later")


def make_radar() -> Optional[outpost_radar.Radar]:
    map_settings = outpost_map.settings(contact=u.CONTACT)
    return outpost_radar.Radar(map_settings["zoom"], u.USER_AGENT) if map_settings["radar"] else None


def make_handler(places: Places, radar: Optional[outpost_radar.Radar] = None) -> type:
    class Handler(BaseHTTPRequestHandler):
        server_version = "Outpost"
        sys_version = ""

        def do_GET(self) -> None:
            parts = urlsplit(self.path)
            if parts.path.startswith("/tiles/radar/"):
                self.send_tile(parts.path)
                return
            query = parse_qs(parts.query, keep_blank_values=True, max_num_fields=20)
            try:
                if parts.path == "/api/status":
                    self.send_json(200, status())
                elif parts.path == "/api/weather":
                    self.send_json(200, weather(query, places))
                elif parts.path == "/api/places":
                    self.send_json(200, search_places(query))
                elif parts.path == "/api/radar":
                    self.send_json(200, radar_frames(query, radar))
                else:
                    raise ApiError(404, "not_found", "No such API address")
            except ApiError as error:
                self.send_json(error.status, {"error": error.code, "message": error.message})
            except Exception as error:  # never let one request take the server down
                print(f"[Outpost] API error: {error}", file=sys.stderr, flush=True)
                self.send_json(500, {"error": "server_error", "message": "Something went wrong"})

        # The same headers without the body
        do_HEAD = do_GET

        def send_tile(self, path: str) -> None:
            try:
                if radar is None:
                    raise outpost_radar.RadarNotFound("the radar is off")
                body = radar.tile(path)
            except outpost_radar.RadarError as error:
                if not isinstance(error, outpost_radar.RadarNotFound):
                    # Never the address: it says which place a screen shows
                    print(f"[Outpost] Radar tile: {error}", file=sys.stderr, flush=True)
                self.send_bytes(error.status, b"", "text/plain; charset=utf-8", "no-store")
            except Exception as error:  # never let one request take the server down
                print(f"[Outpost] Radar tile error: {type(error).__name__}", file=sys.stderr, flush=True)
                self.send_bytes(500, b"", "text/plain; charset=utf-8", "no-store")
            else:
                # A frame never changes, so nginx and browsers can keep its tiles while it can be shown
                self.send_bytes(200, body, "image/png", f"public, max-age={outpost_radar.FRAME_KEEP_SECONDS}")

        def send_bytes(self, code: int, data: bytes, kind: str, cache: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Cache-Control", cache)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def send_json(self, code: int, body: Dict[str, Any]) -> None:
            data = json.dumps(body).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(data)

        def log_message(self, format: str, *args: Any) -> None:
            # The request line has a viewer's coordinates in it, so requests are not logged
            pass

    return Handler


def make_server(places: Places, host: str = HOST, port: int = PORT,
                radar: Optional[outpost_radar.Radar] = None) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), make_handler(places, radar))
    server.daemon_threads = True
    return server


def main() -> None:
    u.check_theme_folders()
    u.write_config()
    threading.Thread(target=u.run_loop, name="home-updates", daemon=True).start()

    server = make_server(Places(u.LOCATION_LIMIT), radar=make_radar())
    if u.LOCATION_SEARCH:
        search = (f"other places on, at most {u.LOCATION_LIMIT} weather fetches an hour between them, "
                  f"each at most every {PLACE_REFRESH_SECONDS // 60} min")
    else:
        search = "other places off (OUTPOST_LOCATION_SEARCH=false)"
    print(f"[Outpost] API listening on {HOST}:{PORT}; {search}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
