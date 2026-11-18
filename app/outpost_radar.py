#!/usr/bin/env python3
"""
Rain radar for the map panel (docs/map-design.md): NOAA's MRMS base reflectivity mosaic in the US
(regions.noaa_radar_area), RainViewer everywhere else.

The dashboard asks /api/radar which frames there are for the place shown, then draws the tiles of
the latest one (or, with OUTPOST_MAP_RADAR_LOOP, of all of them) from:

  /tiles/radar/noaa/<area>/<frame>/{z}/{x}/{y}.png   a WMS GetMap for that tile's square
  /tiles/radar/rainviewer/<frame>/{z}/{x}/{y}.png    RainViewer's own tile

nginx passes those here and caches them (outpost_map.radar_snippet). A frame never changes, so a
tile can be kept for hours. Only frames listed here in the last FRAME_KEEP_SECONDS, at the zoom
the map is drawn at, are fetched, so Outpost is never an open proxy, and fetches from the radar
services are capped at TILE_FETCHES_PER_MINUTE between all screens.

Tile addresses say roughly which place a screen shows, so they are never logged.

Uses only the Python standard library.
"""

import collections
import json
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import regions

NOAA = "noaa"
RAINVIEWER = "rainviewer"
NOAA_AREAS = ("conus", "alaska", "hawaii", "guam", "carib")
NOAA_WMS = "https://opengeo.ncep.noaa.gov/geoserver/{area}/{area}_bref_qcd/ows"
RAINVIEWER_INDEX = "https://api.rainviewer.com/public/weather-maps.json"
# The index names the tile server; only RainViewer's own are used
RAINVIEWER_HOST = re.compile(r"https://(?:[a-z0-9-]+\.)*rainviewer\.com")
RAINVIEWER_PATH = re.compile(r"/v2/radar/(?P<id>[0-9a-f]{6,40})")
# RainViewer's free tiles stop at zoom 7; the dashboard draws them larger above that
RAINVIEWER_MAX_ZOOM = 7
# Universal Blue, the one color scheme of the free tiles; smoothed, with snow in its own colors
RAINVIEWER_STYLE = "2/1_1"

CREDITS = {
    NOAA: ("NOAA", "https://www.nssl.noaa.gov/projects/mrms/"),
    RAINVIEWER: ("RainViewer", "https://www.rainviewer.com/"),
}

# The loop: the past 2 hours, a frame every 10 minutes (NOAA has one every 2)
LOOP_SECONDS = 2 * 3600
FRAME_STEP_SECONDS = 10 * 60
# How long a list of frames is used before asking again (NOAA adds a frame every 2 minutes,
# RainViewer every 10), and how long a frame's tiles can still be asked for after it was listed
FRAMES_CACHE_SECONDS = 120
FRAME_KEEP_SECONDS = 3 * 3600
TILE_FETCHES_PER_MINUTE = 300
TIMEOUT_SECONDS = 15
MAX_LIST_BYTES = 1_000_000
MAX_TILE_BYTES = 2_000_000
TILE_SIZE = 256
# Half the width of the Web Mercator world, in meters
MERCATOR_HALF = 20037508.342789244

ISO_TIME = re.compile(r"(\d{4})-(\d\d)-(\d\d)T(\d\d):(\d\d):(\d\d)(?:\.\d+)?Z")
NOAA_TIMES = re.compile(r'<Dimension\s+name="time"[^>]*>([^<]*)</Dimension>')
TILE_PATH = re.compile(r"/tiles/radar/(?:noaa/(?P<area>[a-z]+)|rainviewer)/(?P<frame>[A-Za-z0-9]{1,40})"
                       r"/(?P<z>[0-9]{1,2})/(?P<x>[0-9]{1,5})/(?P<y>[0-9]{1,5})\.png")


class RadarError(Exception):
    """A radar service did not answer as expected (the message never includes a tile address)."""
    status = 502


class RadarNotFound(RadarError):
    status = 404


class RadarBusy(RadarError):
    status = 503


Getter = Callable[[str], Tuple[str, bytes]]


def http_get(user_agent: str, max_bytes: int) -> Getter:
    def get(url: str) -> Tuple[str, bytes]:
        request = urllib.request.Request(url, headers={"User-Agent": user_agent})
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                body = response.read(max_bytes + 1)
                kind = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as error:
            raise RadarError(f"the radar service answered HTTP {error.code}") from None
        except (urllib.error.URLError, OSError, ValueError) as error:
            raise RadarError(f"the radar service could not be reached ({type(error).__name__})") from None
        if len(body) > max_bytes:
            raise RadarError("the radar service sent too much")
        return kind, body
    return get


def source_for(latitude: float, longitude: float) -> Tuple[str, Optional[str]]:
    """(NOAA, area) for a place NOAA's mosaic covers, else (RAINVIEWER, None)."""
    area = regions.noaa_radar_area(latitude, longitude)
    return (NOAA, area) if area else (RAINVIEWER, None)


def iso_time(seconds: int) -> str:
    return datetime.fromtimestamp(seconds, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_iso(text: str) -> Optional[int]:
    match = ISO_TIME.fullmatch(text.strip())
    if not match:
        return None
    return int(datetime(*map(int, match.groups()), tzinfo=timezone.utc).timestamp())


def loop_frames(frames: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    The frames to show, oldest first: the latest, and before it one about every FRAME_STEP_SECONDS
    over the past LOOP_SECONDS (a frame up to 30 seconds early still counts as the next step).
    """
    ordered = sorted(frames, key=lambda frame: frame["time"])
    if not ordered:
        return []
    latest = ordered[-1]["time"]
    picked = [ordered[-1]]
    for frame in reversed(ordered[:-1]):
        if latest - frame["time"] > LOOP_SECONDS:
            break
        if picked[-1]["time"] - frame["time"] >= FRAME_STEP_SECONDS - 30:
            picked.append(frame)
    return list(reversed(picked))


def noaa_frames(capabilities: str) -> List[Dict[str, Any]]:
    """Frames from a WMS GetCapabilities answer: its time dimension, as ids like 20261118T012414Z."""
    match = NOAA_TIMES.search(capabilities)
    if not match:
        raise RadarError("NOAA's radar listed no times")
    frames = []
    for text in match.group(1).split(","):
        seconds = parse_iso(text)
        if seconds is not None:
            frames.append({"id": time.strftime("%Y%m%dT%H%M%SZ", time.gmtime(seconds)), "time": seconds,
                           "upstream": iso_time(seconds)})
    if not frames:
        raise RadarError("NOAA's radar listed no times")
    return loop_frames(frames)


def rainviewer_frames(index: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Frames from RainViewer's weather-maps.json: the past radar, with each frame's tile address."""
    host = index.get("host") if isinstance(index, dict) else None
    if not isinstance(host, str) or not RAINVIEWER_HOST.fullmatch(host):
        raise RadarError("RainViewer named an unexpected tile server")
    radar = index.get("radar")
    past = radar.get("past") if isinstance(radar, dict) else None
    frames = []
    for item in past if isinstance(past, list) else []:
        if not isinstance(item, dict) or not isinstance(item.get("time"), int) or not isinstance(item.get("path"), str):
            continue
        match = RAINVIEWER_PATH.fullmatch(item["path"])
        if match:
            frames.append({"id": match.group("id"), "time": item["time"], "upstream": host + item["path"]})
    if not frames:
        raise RadarError("RainViewer listed no radar frames")
    return loop_frames(frames)


def noaa_tile_url(area: str, frame_time: str, z: int, x: int, y: int) -> str:
    """A WMS GetMap for the square of tile z/x/y, in Web Mercator."""
    size = 2 * MERCATOR_HALF / 2 ** z
    west = -MERCATOR_HALF + x * size
    north = MERCATOR_HALF - y * size
    query = urlencode({
        "SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetMap",
        "LAYERS": f"{area}_bref_qcd", "STYLES": "", "CRS": "EPSG:3857",
        "BBOX": f"{west:.2f},{north - size:.2f},{west + size:.2f},{north:.2f}",
        "WIDTH": TILE_SIZE, "HEIGHT": TILE_SIZE, "FORMAT": "image/png", "TRANSPARENT": "true",
        "TIME": frame_time,
    })
    return f"{NOAA_WMS.format(area=area)}?{query}"


def rainviewer_tile_url(upstream: str, z: int, x: int, y: int) -> str:
    return f"{upstream}/{TILE_SIZE}/{z}/{x}/{y}/{RAINVIEWER_STYLE}.png"


def parse_tile_path(path: str) -> Optional[Tuple[str, Optional[str], str, int, int, int]]:
    """(source, area, frame, z, x, y) from a /tiles/radar/... address, or None."""
    match = TILE_PATH.fullmatch(path)
    if not match:
        return None
    area = match.group("area")
    if area is not None and area not in NOAA_AREAS:
        return None
    return (NOAA if area else RAINVIEWER, area, match.group("frame"),
            int(match.group("z")), int(match.group("x")), int(match.group("y")))


class Radar:
    """The radar frames and tiles for the map, at its zoom, shared by every screen."""

    def __init__(self, zoom: int, user_agent: str, list_get: Optional[Getter] = None,
                 tile_get: Optional[Getter] = None, clock: Callable[[], float] = time.time) -> None:
        self.zoom = zoom
        self._list_get = list_get or http_get(user_agent, MAX_LIST_BYTES)
        self._tile_get = tile_get or http_get(user_agent, MAX_TILE_BYTES)
        self._clock = clock
        self._lock = threading.Lock()
        self._lists: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}
        # (list, frame id) -> (until, upstream): the frames whose tiles may be fetched
        self._known: Dict[Tuple[str, str], Tuple[float, str]] = {}
        self._fetches: collections.deque = collections.deque()

    def tile_zoom(self, source: str) -> int:
        return min(self.zoom, RAINVIEWER_MAX_ZOOM) if source == RAINVIEWER else self.zoom

    @staticmethod
    def _list_key(source: str, area: Optional[str]) -> str:
        return f"{NOAA}/{area}" if source == NOAA else RAINVIEWER

    def _fetch_list(self, source: str, area: Optional[str]) -> List[Dict[str, Any]]:
        if source == NOAA:
            url = NOAA_WMS.format(area=area) + "?service=WMS&version=1.3.0&request=GetCapabilities"
            _, body = self._list_get(url)
            return noaa_frames(body.decode("utf-8", "replace"))
        _, body = self._list_get(RAINVIEWER_INDEX)
        try:
            index = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise RadarError("RainViewer sent something other than its index") from None
        return rainviewer_frames(index)

    def frames(self, source: str, area: Optional[str] = None) -> List[Dict[str, Any]]:
        """The frames to show, oldest first, fetched at most every FRAMES_CACHE_SECONDS."""
        key = self._list_key(source, area)
        now = self._clock()
        with self._lock:
            cached = self._lists.get(key)
        if cached and now - cached[0] < FRAMES_CACHE_SECONDS:
            return cached[1]
        try:
            frames = self._fetch_list(source, area)
        except RadarError:
            # The last list, while its frames can still be shown
            if cached and now - cached[0] < FRAME_KEEP_SECONDS:
                return cached[1]
            raise
        with self._lock:
            self._lists[key] = (now, frames)
            for frame in frames:
                self._known[(key, frame["id"])] = (now + FRAME_KEEP_SECONDS, frame["upstream"])
            for known, (until, _) in list(self._known.items()):
                if until < now:
                    del self._known[known]
        return frames

    def answer(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """/api/radar: where the radar comes from, and its frames' tile addresses, oldest first."""
        source, area = source_for(latitude, longitude)
        frames = self.frames(source, area)
        prefix = f"tiles/radar/{NOAA}/{area}" if source == NOAA else f"tiles/radar/{RAINVIEWER}"
        credit, credit_url = CREDITS[source]
        return {
            "source": source,
            "credit": credit,
            "credit_url": credit_url,
            "zoom": self.tile_zoom(source),
            "frames": [{"time": iso_time(frame["time"]), "tiles": f"{prefix}/{frame['id']}/{{z}}/{{x}}/{{y}}.png"}
                       for frame in frames],
        }

    def _upstream(self, source: str, area: Optional[str], frame: str) -> Optional[str]:
        key = self._list_key(source, area)
        with self._lock:
            known = self._known.get((key, frame))
        if known and known[0] >= self._clock():
            return known[1]
        return None

    def _take_fetch(self) -> bool:
        now = self._clock()
        with self._lock:
            while self._fetches and now - self._fetches[0] >= 60:
                self._fetches.popleft()
            if len(self._fetches) >= TILE_FETCHES_PER_MINUTE:
                return False
            self._fetches.append(now)
            return True

    def tile(self, path: str) -> bytes:
        """The PNG for a /tiles/radar/... address."""
        parsed = parse_tile_path(path)
        if not parsed:
            raise RadarNotFound("no such radar tile")
        source, area, frame, z, x, y = parsed
        if z != self.tile_zoom(source) or x >= 2 ** z or y >= 2 ** z:
            raise RadarNotFound("no such radar tile")
        upstream = self._upstream(source, area, frame)
        if upstream is None:
            # A frame listed since this list was fetched (after a restart, say)
            self.frames(source, area)
            upstream = self._upstream(source, area, frame)
        if upstream is None:
            raise RadarNotFound("no such radar frame")
        if not self._take_fetch():
            raise RadarBusy("too many radar tiles fetched in the last minute")
        if source == NOAA:
            url = noaa_tile_url(area or "", upstream, z, x, y)
        else:
            url = rainviewer_tile_url(upstream, z, x, y)
        kind, body = self._tile_get(url)
        if not kind.split(";")[0].strip().lower() == "image/png" or not body.startswith(b"\x89PNG"):
            raise RadarError("the radar service sent something other than a picture")
        return body
