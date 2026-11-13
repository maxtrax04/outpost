"""
Pirate Weather provider (api.pirateweather.net).

Docs:  https://docs.pirateweather.net/en/latest/API/
Terms: needs a free API key from https://pirateweather.net (OUTPOST_PIRATEWEATHER_API_KEY), which
       allows 10,000 calls a month. Outpost keeps each forecast for at least 10 minutes (about 4,300
       calls a month however often it updates), and after "quota reached" it waits for the reset
       time the service sends instead of asking again.

The key goes in the `apikey` request header rather than the address, so it never appears in a URL,
a log line, or an error message. Requested in US units: °F, mph, miles (pressure is in millibars,
which are hPa).

Alerts (fetch_alerts) come in the same response: the National Weather Service's for the lower 48 US
states, and elsewhere the official warnings that national weather services publish to the WMO
alert hub (Europe through MeteoAlarm). Which countries are included changes over time, and an empty
list looks the same whether there are no alerts or the country is not covered, so the dashboard
says "none reported by Pirate Weather" rather than "none". Alerts are in the publisher's language.

Uses only the Python standard library.
"""

import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

API_URL = "https://api.pirateweather.net/forecast"
SOURCE = "Pirate Weather"
# What this provider supplies as a weather provider. Its alerts (fetch_alerts) are not counted: the
# updater asks NWS first in the US and uses them only after that (OUTPOST_ALERTS_PROVIDER).
CAPABILITIES = frozenset({"current", "forecast", "uv"})
TIMEOUT_SECONDS = 20
FORECAST_DAYS = 5
# Keep a forecast at least this long, to stay well inside the free 10,000 calls a month
MIN_CACHE_SECONDS = 600
# After "quota reached", wait at most this long before trying again (the reset time is usually sent)
MAX_QUOTA_WAIT_SECONDS = 24 * 3600

HPA_TO_INHG = 0.02952998

# Pirate Weather icon -> (short condition text for forecast days, icon name used by the dashboard)
ICONS = {
    "clear-day": ("Clear", "sunny"),
    "clear-night": ("Clear", "clear-night"),
    "partly-cloudy-day": ("Partly cloudy", "partly-cloudy"),
    "partly-cloudy-night": ("Partly cloudy", "partly-cloudy-night"),
    "cloudy": ("Cloudy", "cloudy"),
    "fog": ("Fog", "fog"),
    "wind": ("Windy", "wind"),
    "rain": ("Rain", "rain"),
    "sleet": ("Sleet", "sleet"),
    "hail": ("Hail", "sleet"),
    "snow": ("Snow", "snow"),
    "thunderstorm": ("Thunderstorms", "storm"),
}

# A summary longer than this is a sentence, too long for the dashboard; the icon's text is used instead
MAX_SUMMARY_LENGTH = 30

# url -> {"expires": unix time, "raw": decoded JSON}
_cache: Dict[str, Dict[str, Any]] = {}
# No requests before this time (after the monthly quota ran out)
_blocked_until = 0.0


def describe(icon: Optional[str], summary: Any = None) -> Tuple[str, str]:
    """(condition text, dashboard icon). A short summary from Pirate Weather wins over the icon's text."""
    text, name = ICONS.get(icon or "", ("Unknown", "unknown"))
    if isinstance(summary, str) and 0 < len(summary.strip()) <= MAX_SUMMARY_LENGTH:
        text = summary.strip()
    return text, name


# ---------------------------------------------------------------- HTTP

def _max_age(headers: Any) -> int:
    match = re.search(r"max-age=(\d+)", headers.get("Cache-Control") or "")
    return int(match.group(1)) if match else 0


def _seconds(value: Any) -> Optional[float]:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def fetch_raw(latitude: float, longitude: float, api_key: str, user_agent: str) -> Dict[str, Any]:
    """The forecast JSON, kept for at least MIN_CACHE_SECONDS."""
    global _blocked_until

    if not api_key:
        raise RuntimeError("Pirate Weather needs an API key: set OUTPOST_PIRATEWEATHER_API_KEY")

    params = {"units": "us", "exclude": "minutely,hourly"}
    # The key travels in the apikey header; the address only needs something in its place
    url = f"{API_URL}/key-in-header/{latitude:.4f},{longitude:.4f}?{urllib.parse.urlencode(params)}"
    now = time.time()
    cached = _cache.get(url)
    if cached and now < cached["expires"]:
        return cached["raw"]
    if now < _blocked_until:
        raise RuntimeError("Pirate Weather monthly quota reached; waiting for it to reset")

    request = urllib.request.Request(url, headers={"apikey": api_key, "User-Agent": user_agent,
                                                   "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = json.load(response)
            _cache[url] = {"expires": now + max(MIN_CACHE_SECONDS, _max_age(response.headers)), "raw": raw}
            return raw
    except urllib.error.HTTPError as error:
        if error.code == 401:
            raise RuntimeError("Pirate Weather HTTP 401: the API key was refused (check "
                               "OUTPOST_PIRATEWEATHER_API_KEY, and that the key is subscribed to the forecast API)") from error
        if error.code == 429:
            reset = _seconds((error.headers or {}).get("Ratelimit-Reset"))
            wait = min(reset, MAX_QUOTA_WAIT_SECONDS) if reset and reset > 0 else 3600
            _blocked_until = now + wait
            raise RuntimeError(f"Pirate Weather HTTP 429: monthly quota reached; trying again in {int(wait // 60)} minutes") from error
        raise RuntimeError(f"Pirate Weather HTTP {error.code}: {error.reason}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"Pirate Weather unreachable: {error.reason}") from error
    except ValueError as error:
        raise RuntimeError(f"Pirate Weather returned invalid JSON: {error}") from error


# ---------------------------------------------------------------- normalizing

def _number(value: Any) -> Optional[float]:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _percent(value: Any) -> Optional[int]:
    """Pirate Weather gives humidity and chances as 0 to 1."""
    number = _number(value)
    return round(number * 100) if number is not None else None


def _zone(raw: Dict[str, Any]) -> tzinfo:
    """The location's time zone, from the response (its name, or else its offset in hours)."""
    try:
        return ZoneInfo(raw.get("timezone") or "")
    except Exception:
        pass
    offset = _number(raw.get("offset"))
    if offset is not None:
        return timezone(timedelta(hours=offset))
    return timezone.utc


def build_current(currently: Dict[str, Any]) -> Dict[str, Any]:
    condition, icon = describe(currently.get("icon"), currently.get("summary"))
    pressure = _number(currently.get("pressure"))
    uv = _number(currently.get("uvIndex"))
    return {
        "temperature": _number(currently.get("temperature")),
        "feels_like": _number(currently.get("apparentTemperature")),
        "condition": condition,
        "icon": icon,
        "humidity": _percent(currently.get("humidity")),
        "wind_speed": _number(currently.get("windSpeed")),
        "pressure": pressure * HPA_TO_INHG if pressure is not None else None,  # millibars = hPa
        "uv_index": round(uv) if uv is not None else None,
        "visibility": _number(currently.get("visibility")),  # miles, up to 10
    }


def build_forecast(days: List[Dict[str, Any]], zone: tzinfo) -> List[Dict[str, Any]]:
    """One entry per day. High and low are the calendar day's (temperatureMax and temperatureMin)."""
    forecast: List[Dict[str, Any]] = []
    for day in days[:FORECAST_DAYS]:
        start = _number(day.get("time"))
        if start is None:
            continue
        condition, icon = describe(day.get("icon"), day.get("summary"))
        uv = _number(day.get("uvIndex"))
        forecast.append({
            "day": datetime.fromtimestamp(start, zone).date().isoformat(),
            "high": _number(day.get("temperatureMax")),
            "low": _number(day.get("temperatureMin")),
            "condition": condition,
            "icon": icon,
            "precipitation_chance": _percent(day.get("precipProbability")),
            "uv_index": round(uv) if uv is not None else None,
        })
    return forecast


def normalize(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Outpost's normalized format. Readings are unrounded, in °F, mph, inHg, and miles; the updater
    converts them to OUTPOST_UNITS and rounds them (app/units.py).
    """
    currently = (raw or {}).get("currently")
    days = ((raw or {}).get("daily") or {}).get("data")
    if not isinstance(currently, dict) or not days:
        raise RuntimeError("Pirate Weather response is missing current or daily data")
    return {
        "source": SOURCE,
        "current": build_current(currently),
        "forecast": build_forecast(days, _zone(raw)),
        "alerts": [],
    }


def fetch(latitude: float, longitude: float, api_key: str, user_agent: str) -> Dict[str, Any]:
    """Fetch (or reuse, for at least 10 minutes) and normalize the forecast for a location."""
    return normalize(fetch_raw(latitude, longitude, api_key, user_agent))


# ---------------------------------------------------------------- alerts

SEVERITIES = ("extreme", "severe", "moderate", "minor")
SEVERITY_ORDER = {name: rank for rank, name in enumerate(SEVERITIES + ("unknown",))}
MAX_ALERTS = 5


def _alert_time(value: Any) -> Optional[str]:
    """Pirate Weather sends times in UNIX seconds, and -999 when there is none."""
    number = _number(value)
    if number is None or number < 0:
        return None
    return datetime.fromtimestamp(number, timezone.utc).isoformat()


def _text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def build_alerts(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Outpost's alert format, most serious first. Severity is lowercased, and anything outside the CAP
    levels (including a blank one) is "unknown". Repeats of the same alert are dropped.
    """
    alerts: List[Dict[str, Any]] = []
    seen = set()
    for alert in (raw or {}).get("alerts") or []:
        if not isinstance(alert, dict):
            continue
        title = _text(alert.get("title")) or "Weather alert"
        description = _text(alert.get("description"))
        expires = _alert_time(alert.get("expires"))
        key = (title.lower(), expires, description.lower())
        if key in seen:
            continue
        seen.add(key)
        severity = _text(alert.get("severity")).lower()
        uri = alert.get("uri")
        alerts.append({
            "title": title,
            "description": description,
            "severity": severity if severity in SEVERITIES else "unknown",
            "expires": expires,
            "uri": uri if isinstance(uri, str) and uri.startswith(("https://", "http://")) else None,
        })
    alerts.sort(key=lambda a: SEVERITY_ORDER[a["severity"]])
    return alerts[:MAX_ALERTS]


def fetch_alerts(latitude: float, longitude: float, api_key: str, user_agent: str) -> List[Dict[str, Any]]:
    """
    The location's alerts. They come with the forecast, so when the weather is from Pirate Weather
    too this reuses the same response (no extra call).
    """
    return build_alerts(fetch_raw(latitude, longitude, api_key, user_agent))
