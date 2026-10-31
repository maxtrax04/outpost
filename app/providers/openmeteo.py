"""
Open-Meteo provider.

Docs:  https://open-meteo.com/en/docs
Terms: free for non-commercial use, no API key. Attribution is required
       (the dashboard shows it via the "source" field).

Uses only the Python standard library.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional

API_URL = "https://api.open-meteo.com/v1/forecast"
SOURCE = "Open-Meteo.com"
TIMEOUT_SECONDS = 15
FORECAST_DAYS = 5

CURRENT_VARS = [
    "is_day",
    "temperature_2m",
    "apparent_temperature",
    "relative_humidity_2m",
    "weather_code",
    "pressure_msl",
    "wind_speed_10m",
]

# UV index and visibility are only offered hourly, so we read the current hour.
HOURLY_VARS = ["uv_index", "visibility"]

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
    """Call the Open-Meteo forecast API and return the decoded JSON."""
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

    return raw


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


def normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Convert an Open-Meteo response into Outpost's normalized format."""
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
        "temperature_f": _round(current.get("temperature_2m")),
        "feels_like_f": _round(current.get("apparent_temperature")),
        "condition": condition,
        "icon": icon,
        "humidity_percent": _round(current.get("relative_humidity_2m")),
        "wind_mph": _round(current.get("wind_speed_10m")),
        "pressure_inhg": _round(pressure_hpa * HPA_TO_INHG, 2) if pressure_hpa is not None else None,
        "uv_index": _round(_hourly_value(raw, "uv_index")),
        "visibility_miles": _round(visibility_m / METERS_PER_MILE, 1) if visibility_m is not None else None,
    }

    forecast: List[Dict[str, Any]] = []
    days = daily.get("time") or []
    for i, day in enumerate(days[:FORECAST_DAYS]):
        day_condition, day_icon = describe((daily.get("weather_code") or [None] * len(days))[i])
        forecast.append({
            "day": day,
            "high_f": _round((daily.get("temperature_2m_max") or [None] * len(days))[i]),
            "low_f": _round((daily.get("temperature_2m_min") or [None] * len(days))[i]),
            "condition": day_condition,
            "icon": day_icon,
            "precipitation_percent": (daily.get("precipitation_probability_max") or [None] * len(days))[i],
            "uv_index": _round((daily.get("uv_index_max") or [None] * len(days))[i]),
        })

    return {
        "source": SOURCE,
        "current": normalized_current,
        "forecast": forecast,
        "alerts": [],  # Open-Meteo does not provide official alerts
        "alerts_supported": False,
    }


def fetch(latitude: float, longitude: float, user_agent: str) -> Dict[str, Any]:
    """Fetch and normalize weather for a location."""
    return normalize(fetch_raw(latitude, longitude, user_agent))
