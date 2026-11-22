"""
Open-Meteo provider.

Docs:  https://open-meteo.com/en/docs
Terms: free for non-commercial use, no API key. Attribution is required
       (the dashboard credits it from the "sources" block of weather.json).
       The free tier allows fewer than 10,000 calls a day, and current conditions change every
       15 minutes, so the same answer is reused for MIN_REQUEST_SECONDS whatever
       OUTPOST_UPDATE_INTERVAL is (the weather, gap filling, and the fallback all share it).

Uses only the Python standard library.
"""

import copy
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from providers import hourly as hours

API_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE = "Open-Meteo.com"
# What this provider supplies. Open-Meteo has no official alerts.
CAPABILITIES = frozenset({"current", "forecast", "uv"})
TIMEOUT_SECONDS = 15
FORECAST_DAYS = 5
# Never ask again for the same place sooner than this (its current conditions are 15-minutely)
MIN_REQUEST_SECONDS = 15 * 60

# url -> {"expires": unix time, "raw": decoded JSON}
_cache: Dict[str, Dict[str, Any]] = {}

CURRENT_VARS = [
    "is_day",
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "weather_code",
    "pressure_msl",
    "wind_speed_10m",
    "wind_gusts_10m",
    "wind_direction_10m",
    "dew_point_2m",
]

# UV index and visibility are only offered hourly, so we read the current hour. The rest are for the
# hourly forecast.
HOURLY_VARS = ["uv_index", "visibility", "temperature_2m", "weather_code", "precipitation_probability",
               "wind_speed_10m", "wind_direction_10m", "is_day"]

DAILY_VARS = [
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "precipitation_probability_max",
    "uv_index_max",
]

HPA_TO_INHG = 0.02952998
METERS_PER_MILE = 1609.344

# WMO weather code -> (description, icon name used by the dashboard)
WMO_CODES = {
    0: ("Clear sky", "sunny"),
    1: ("Mainly clear", "sunny"),
    2: ("Partly cloudy", "partly-cloudy"),
    3: ("Overcast", "cloudy"),
    45: ("Fog", "fog"),
    48: ("Freezing fog", "fog"),
    51: ("Light drizzle", "drizzle"),
    53: ("Drizzle", "drizzle"),
    55: ("Heavy drizzle", "drizzle"),
    56: ("Freezing drizzle", "sleet"),
    57: ("Heavy freezing drizzle", "sleet"),
    61: ("Light rain", "rain"),
    63: ("Rain", "rain"),
    65: ("Heavy rain", "rain"),
    66: ("Freezing rain", "sleet"),
    67: ("Heavy freezing rain", "sleet"),
    71: ("Light snow", "snow"),
    73: ("Snow", "snow"),
    75: ("Heavy snow", "snow"),
    77: ("Snow grains", "snow"),
    80: ("Light showers", "rain"),
    81: ("Showers", "rain"),
    82: ("Violent showers", "rain"),
    85: ("Light snow showers", "snow"),
    86: ("Heavy snow showers", "snow"),
    95: ("Thunderstorm", "storm"),
    96: ("Thunderstorm with hail", "storm"),
    99: ("Severe thunderstorm with hail", "storm"),
}


# Night versions of icons that show the sun
NIGHT_ICONS = {
    "sunny": "clear-night",
    "partly-cloudy": "partly-cloudy-night",
}


def describe(code: Optional[int]) -> tuple:
    """Return (description, icon) for a WMO weather code."""
    return WMO_CODES.get(code, ("Unknown", "unknown"))


def _round(value: Optional[float], digits: int = 0) -> Optional[float]:
    if value is None:
        return None
    result = round(value, digits)
    return int(result) if digits == 0 else result


def fetch_raw(latitude: float, longitude: float, user_agent: str) -> Dict[str, Any]:
    """The Open-Meteo forecast JSON, asked for at most every MIN_REQUEST_SECONDS per place."""
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join(CURRENT_VARS),
        "hourly": ",".join(HOURLY_VARS),
        "daily": ",".join(DAILY_VARS),
        "temperature_unit": "fahrenheit",
        "wind_speed_unit": "mph",
        "timezone": "auto",
        "forecast_days": FORECAST_DAYS,
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
        raise RuntimeError(f"Open-Meteo HTTP {error.code}: {reason or error.reason}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Open-Meteo unreachable: {error.reason}") from error

    if raw.get("error"):
        raise RuntimeError(f"Open-Meteo error: {raw.get('reason', 'unknown')}")

    _cache[url] = {"expires": now + MIN_REQUEST_SECONDS, "raw": raw}
    return copy.deepcopy(raw)


def _hourly_value(raw: Dict[str, Any], name: str) -> Optional[float]:
    """Find the hourly value that matches the current observation's hour."""
    hourly = raw.get("hourly") or {}
    times = hourly.get("time") or []
    values = hourly.get(name) or []
    now = (raw.get("current") or {}).get("time")
    if not now:
        return None
    hour = now[:13]  # "YYYY-MM-DDTHH"
    for stamp, value in zip(times, values):
        if stamp[:13] == hour:
            return value
    return None


def _observed_at(local_time: Any, utc_offset_seconds: Any) -> Optional[str]:
    """'2026-07-15T14:15' at the location (timezone=auto) -> ISO 8601 in UTC, or None."""
    try:
        moment = datetime.fromisoformat(local_time) - timedelta(seconds=int(utc_offset_seconds or 0))
    except (TypeError, ValueError):
        return None
    return moment.replace(tzinfo=timezone.utc).isoformat()


def build_hourly(raw: Dict[str, Any], now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """The next hours (providers/hourly.py) from Open-Meteo's hourly block, in local time (timezone=auto)."""
    block = raw.get("hourly") or {}
    stamps = block.get("time") or []

    def column(name: str) -> List[Any]:
        values = block.get(name)
        return values if isinstance(values, list) and len(values) == len(stamps) else [None] * len(stamps)

    temps, codes, chances = column("temperature_2m"), column("weather_code"), column("precipitation_probability")
    winds, directions, days = column("wind_speed_10m"), column("wind_direction_10m"), column("is_day")
    entries = []
    for index, stamp in enumerate(stamps):
        moment = _observed_at(stamp, raw.get("utc_offset_seconds"))
        if moment is None:
            continue
        condition, icon = describe(codes[index])
        if days[index] == 0:
            icon = NIGHT_ICONS.get(icon, icon)
        entries.append(hours.entry(datetime.fromisoformat(moment), temps[index], condition, icon,
                                   chances[index], winds[index], directions[index]))
    return hours.upcoming(entries, now)


def normalize(raw: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Convert an Open-Meteo response into Outpost's normalized format. Readings are unrounded, in
    °F, mph, inHg, and miles; the updater converts them to OUTPOST_UNITS and rounds them (app/units.py).
    """
    current = raw.get("current")
    daily = raw.get("daily")
    if not current or not daily:
        raise RuntimeError("Open-Meteo response is missing current or daily data")

    condition, icon = describe(current.get("weather_code"))
    if current.get("is_day") == 0:
        icon = NIGHT_ICONS.get(icon, icon)

    pressure_hpa = current.get("pressure_msl")
    visibility_m = _hourly_value(raw, "visibility")

    normalized_current = {
        "temperature": current.get("temperature_2m"),
        "feels_like": current.get("apparent_temperature"),
        "condition": condition,
        "icon": icon,
        "humidity": _round(current.get("relative_humidity_2m")),
        "wind_speed": current.get("wind_speed_10m"),
        "wind_gust": current.get("wind_gusts_10m"),
        "wind_direction": current.get("wind_direction_10m"),
        "dew_point": current.get("dew_point_2m"),
        "observed_at": _observed_at(current.get("time"), raw.get("utc_offset_seconds")),
        "pressure": pressure_hpa * HPA_TO_INHG if pressure_hpa is not None else None,
        "uv_index": _round(_hourly_value(raw, "uv_index")),
        "visibility": visibility_m / METERS_PER_MILE if visibility_m is not None else None,
    }

    forecast: List[Dict[str, Any]] = []
    days = daily.get("time") or []
    for i, day in enumerate(days[:FORECAST_DAYS]):
        day_condition, day_icon = describe((daily.get("weather_code") or [None] * len(days))[i])
        forecast.append({
            "day": day,
            "high": (daily.get("temperature_2m_max") or [None] * len(days))[i],
            "low": (daily.get("temperature_2m_min") or [None] * len(days))[i],
            "condition": day_condition,
            "icon": day_icon,
            "precipitation_chance": (daily.get("precipitation_probability_max") or [None] * len(days))[i],
            "uv_index": _round((daily.get("uv_index_max") or [None] * len(days))[i]),
        })

    return {
        "source": SOURCE,
        "current": normalized_current,
        "forecast": forecast,
        "hourly": build_hourly(raw, now),
        "timezone": raw.get("timezone"),  # the location's (timezone=auto), such as Europe/Oslo
        "alerts": [],  # Open-Meteo does not provide official alerts
    }


def fetch(latitude: float, longitude: float, user_agent: str) -> Dict[str, Any]:
    """Fetch and normalize weather for a location."""
    return normalize(fetch_raw(latitude, longitude, user_agent))
