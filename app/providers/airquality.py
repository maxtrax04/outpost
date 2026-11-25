"""
Air quality and pollen (#88): weather.json "air_quality", from the Open-Meteo Air Quality API.

Docs:  https://open-meteo.com/en/docs/air-quality-api
Data:  Copernicus Atmosphere Monitoring Service (CAMS) forecasts, served by Open-Meteo under
       CC BY 4.0; both are credited (SOURCE, shown in the dashboard footer). No API key.
       Its "current" values are hourly, so each place is asked at most once an hour: the answer is
       kept until a few minutes into the next hour (cache_until), whatever OUTPOST_UPDATE_INTERVAL is.
       Pollen is only forecast for Europe, in season; elsewhere it is null. The answer also names the
       place's time zone, which picks the index for OUTPOST_AIR_QUALITY_INDEX=auto (see the updater).

Uses only the Python standard library.
"""

import copy
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

API_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"
SOURCE = "Copernicus Atmosphere Monitoring Service (CAMS) via Open-Meteo.com"
TIMEOUT_SECONDS = 15
# Ask again this long after the hour turns, when that hour's values are there
NEXT_HOUR_DELAY_SECONDS = 5 * 60

# Pollutants in µg/m³, as weather.json names them (the same as Open-Meteo's)
POLLUTANTS = ["pm2_5", "pm10", "ozone", "nitrogen_dioxide", "sulphur_dioxide", "carbon_monoxide"]
# Pollen in grains/m³: weather.json name -> Open-Meteo's
POLLEN = {name: f"{name}_pollen" for name in ("alder", "birch", "grass", "mugwort", "olive", "ragweed")}
CURRENT_VARS = ["us_aqi", "european_aqi"] + POLLUTANTS + list(POLLEN.values())

UNITS = {"pollutants": "µg/m³", "pollen": "grains/m³"}

# Index scales: (highest value of the band, category id). The level is the band's place, 0 to 5.
SCALES = {
    # The US EPA's AQI
    "us": [(50, "good"), (100, "moderate"), (150, "unhealthy-sensitive"), (200, "unhealthy"),
           (300, "very-unhealthy"), (math.inf, "hazardous")],
    # The European Environment Agency's European Air Quality Index
    "european": [(20, "good"), (40, "fair"), (60, "moderate"), (80, "poor"), (100, "very-poor"),
                 (math.inf, "extremely-poor")],
}
SCALE_FIELDS = {"us": "us_aqi", "european": "european_aqi"}

# url -> {"expires": unix time, "raw": decoded JSON}
_cache: Dict[str, Dict[str, Any]] = {}


def cache_until(now: float) -> float:
    """When to ask again: a few minutes into the next hour."""
    return (math.floor(now / 3600) + 1) * 3600 + NEXT_HOUR_DELAY_SECONDS


def fetch_raw(latitude: float, longitude: float, user_agent: str) -> Dict[str, Any]:
    """The Air Quality API's JSON for a place, asked for at most once an hour."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join(CURRENT_VARS),
        # The place's own time zone, so the answer names it (and gives local times with their offset)
        "timezone": "auto",
    }
    url = f"{API_URL}?{urllib.parse.urlencode(params, safe=',')}"
    now = time.time()
    cached = _cache.get(url)
    if cached and now < cached["expires"]:
        return copy.deepcopy(cached["raw"])

    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = json.load(response)
    except urllib.error.HTTPError as error:
        reason = None
        try:
            reason = json.load(error).get("reason")
        except Exception:
            pass
        raise RuntimeError(f"Open-Meteo air quality HTTP {error.code}: {reason or error.reason}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Open-Meteo air quality unreachable: {error.reason}") from error

    if not isinstance(raw, dict) or raw.get("error"):
        reason = raw.get("reason", "unknown") if isinstance(raw, dict) else "not JSON"
        raise RuntimeError(f"Open-Meteo air quality error: {reason}")

    _cache[url] = {"expires": cache_until(now), "raw": raw}
    return copy.deepcopy(raw)


def _number(value: Any, digits: int) -> Optional[float]:
    """A reading, rounded, or None for a missing or broken one (and never below 0)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    result = round(max(0.0, float(value)), digits)
    return int(result) if digits == 0 else result


def category(scale: str, value: Optional[float]) -> Dict[str, Any]:
    """{"category": id, "level": 0..5} for an index value on `scale`, or both None when unknown."""
    if value is None or scale not in SCALES:
        return {"category": None, "level": None}
    for level, (highest, name) in enumerate(SCALES[scale]):
        if value <= highest:
            return {"category": name, "level": level}
    return {"category": None, "level": None}  # pragma: no cover (the last band has no top)


def _observed_at(stamp: Any, offset_seconds: Any = 0) -> Optional[str]:
    """Open-Meteo's local "2026-11-25T08:00", `offset_seconds` ahead of UTC, as an ISO 8601 time in UTC."""
    if not isinstance(stamp, str):
        return None
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        return None
    if when.tzinfo is None:
        offset = offset_seconds if isinstance(offset_seconds, int) and not isinstance(offset_seconds, bool) else 0
        when = when.replace(tzinfo=timezone.utc) - timedelta(seconds=offset)
    return when.astimezone(timezone.utc).isoformat()


def build(current: Optional[Dict[str, Any]], scale: str, offset_seconds: Any = 0) -> Optional[Dict[str, Any]]:
    """
    weather.json "air_quality" from the Air Quality API's "current" block, with the index on `scale`
    ("us" or "european"), or None when it has no readings at all. `offset_seconds` is the answer's
    utc_offset_seconds (its times are local).
    """
    current = current if isinstance(current, dict) else {}
    us_aqi = _number(current.get("us_aqi"), 0)
    european_aqi = _number(current.get("european_aqi"), 0)
    pollutants = {name: _number(current.get(name), 1) for name in POLLUTANTS}
    pollen = {name: _number(current.get(field), 1) for name, field in POLLEN.items()}
    if us_aqi is None and european_aqi is None and all(value is None for value in pollutants.values()):
        return None
    index = us_aqi if scale == "us" else european_aqi
    return {
        "index": index,
        "scale": scale,
        **category(scale, index),
        "us_aqi": us_aqi,
        "european_aqi": european_aqi,
        **pollutants,
        # null where none is forecast (outside Europe, or out of season)
        "pollen": pollen if any(value is not None for value in pollen.values()) else None,
        "units": dict(UNITS),
        "observed_at": _observed_at(current.get("time"), offset_seconds),
    }


def sample(now: datetime, scale: str) -> Dict[str, Any]:
    """Made-up readings for the mock provider, with pollen, so the dashboard and themes can show them all."""
    current: Dict[str, Any] = {
        "time": now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:00"),
        "us_aqi": 63, "european_aqi": 34,
        "pm2_5": 18.4, "pm10": 26.1, "ozone": 71.0, "nitrogen_dioxide": 12.3,
        "sulphur_dioxide": 1.9, "carbon_monoxide": 210.0,
        "alder_pollen": 0.0, "birch_pollen": 12.0, "grass_pollen": 48.5,
        "mugwort_pollen": 0.4, "olive_pollen": 0.0, "ragweed_pollen": 3.2,
    }
    return build(current, scale)  # type: ignore[return-value]
