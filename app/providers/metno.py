"""
MET Norway provider (api.met.no Locationforecast 2.0).

Docs:  https://api.met.no/weatherapi/locationforecast/2.0/documentation
Terms: https://api.met.no/doc/TermsOfService
       Free, no API key, worldwide (best in the Nordic countries). MET Norway requires:
       - a User-Agent that identifies the app and how to reach its owner (OUTPOST_CONTACT),
       - coordinates with at most 4 decimals,
       - following the Expires and Last-Modified headers, so the same forecast is not downloaded
         again before it changes (this module caches it),
       - credit to MET Norway, which the dashboard footer shows (data under CC BY 4.0).

MET Norway sends a forecast, not station observations, so "current" is the forecast for this hour.
It has no visibility, and its UV index is for a clear sky. Official alerts come from elsewhere
(OUTPOST_ALERTS_PROVIDER).

Uses only the Python standard library.
"""

import email.utils
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone, tzinfo
from typing import Any, Dict, List, Optional, Tuple
from zoneinfo import ZoneInfo

API_URL = "https://api.met.no/weatherapi/locationforecast/2.0/complete"
SOURCE = "MET Norway (met.no)"
# What this provider supplies (alerts come from OUTPOST_ALERTS_PROVIDER)
CAPABILITIES = frozenset({"current", "forecast", "uv"})
TIMEOUT_SECONDS = 20
FORECAST_DAYS = 5
# Never ask again sooner than this, even if a response says it has already expired
MIN_CACHE_SECONDS = 60

MS_TO_MPH = 2.236936
HPA_TO_INHG = 0.02952998

# MET Norway weather symbols (https://api.met.no/weatherapi/weathericon/2.0/documentation), without the
# _day, _night, or _polartwilight ending -> (condition text, icon name used by the dashboard)
SKY_SYMBOLS = {
    "clearsky": ("Clear sky", "sunny"),
    "fair": ("Fair", "sunny"),
    "partlycloudy": ("Partly cloudy", "partly-cloudy"),
    "cloudy": ("Cloudy", "cloudy"),
    "fog": ("Fog", "fog"),
}
NIGHT_ICONS = {
    "sunny": "clear-night",
    "partly-cloudy": "partly-cloudy-night",
}

# url -> {"expires": unix time, "last_modified": header text or None, "raw": decoded JSON}
_cache: Dict[str, Dict[str, Any]] = {}


def C_TO_F(celsius: float) -> float:
    return celsius * 9 / 5 + 32


# ---------------------------------------------------------------- symbols

def describe(symbol: Optional[str]) -> Tuple[str, str]:
    """
    'lightrainshowers_day' -> ('Light rain showers', 'rain'). Precipitation symbols are built from
    light/heavy, rain/sleet/snow, showers, and 'and thunder', so they are read rather than listed.
    """
    if not symbol:
        return "Unknown", "unknown"
    base, _, variant = symbol.partition("_")
    night = variant == "night"

    if base in SKY_SYMBOLS:
        text, icon = SKY_SYMBOLS[base]
        return text, NIGHT_ICONS.get(icon, icon) if night else icon

    rest = base
    words: List[str] = []
    for prefix in ("light", "heavy"):
        if rest.startswith(prefix):
            words.append(prefix)
            rest = rest[len(prefix):]
    thunder = rest.endswith("andthunder")
    rest = rest.removesuffix("andthunder")
    showers = rest.endswith("showers")
    rest = rest.removesuffix("showers")
    if rest not in ("rain", "sleet", "snow"):
        return "Unknown", "unknown"

    words.append(rest)
    if showers:
        words.append("showers")
    if thunder:
        words.extend(["and", "thunder"])
    text = " ".join(words).capitalize()

    if thunder:
        icon = "storm"
    elif rest == "rain":
        icon = "drizzle" if words[0] == "light" and not showers else "rain"
    else:
        icon = rest
    return text, icon


# ---------------------------------------------------------------- HTTP

def _expires_at(headers: Any, now: float) -> float:
    """When the response may be fetched again (its Expires header), at least MIN_CACHE_SECONDS from now."""
    expires = None
    try:
        parsed = email.utils.parsedate_to_datetime(headers.get("Expires") or "")
        expires = parsed.timestamp()
    except (TypeError, ValueError):
        pass
    return max(expires or 0, now + MIN_CACHE_SECONDS)


def fetch_raw(latitude: float, longitude: float, user_agent: str) -> Dict[str, Any]:
    """The Locationforecast JSON, from the cache until it expires, then revalidated with If-Modified-Since."""
    # MET Norway refuses coordinates with more than 4 decimals
    params = {"lat": f"{latitude:.4f}", "lon": f"{longitude:.4f}"}
    url = f"{API_URL}?{urllib.parse.urlencode(params)}"
    now = time.time()
    cached = _cache.get(url)
    if cached and now < cached["expires"]:
        return cached["raw"]

    headers = {"User-Agent": user_agent, "Accept": "application/json"}
    if cached and cached["last_modified"]:
        headers["If-Modified-Since"] = cached["last_modified"]
    request = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            raw = json.load(response)
            _cache[url] = {
                "expires": _expires_at(response.headers, now),
                "last_modified": response.headers.get("Last-Modified"),
                "raw": raw,
            }
            return raw
    except urllib.error.HTTPError as error:
        if error.code == 304 and cached:
            # Not changed since last time: keep it, until the new expiry time
            cached["expires"] = _expires_at(error.headers, now)
            return cached["raw"]
        if error.code == 403:
            raise RuntimeError("MET Norway HTTP 403: refused (set OUTPOST_CONTACT so Outpost identifies itself)") from error
        if error.code == 429:
            raise RuntimeError("MET Norway HTTP 429: too many requests") from error
        raise RuntimeError(f"MET Norway HTTP {error.code}: {error.reason}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"MET Norway unreachable: {error.reason}") from error
    except ValueError as error:
        raise RuntimeError(f"MET Norway returned invalid JSON: {error}") from error


# ---------------------------------------------------------------- normalizing

def local_zone(longitude: float) -> tzinfo:
    """
    The time zone for grouping the forecast into days: the container's TZ setting, or, without one,
    an offset worked out from the longitude (one hour per 15 degrees).
    """
    name = os.environ.get("TZ", "").strip()
    if name:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    return timezone(timedelta(hours=round(longitude / 15)))


def _time(entry: Dict[str, Any]) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(entry["time"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError):
        return None


def _details(entry: Dict[str, Any], block: str) -> Dict[str, Any]:
    return ((entry.get("data") or {}).get(block) or {}).get("details") or {}


def _symbol(entry: Dict[str, Any], *blocks: str) -> Optional[str]:
    for block in blocks:
        symbol = (((entry.get("data") or {}).get(block) or {}).get("summary") or {}).get("symbol_code")
        if symbol:
            return symbol
    return None


def _number(value: Any) -> Optional[float]:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def build_current(timeseries: List[Dict[str, Any]], now: datetime) -> Dict[str, Any]:
    """The forecast for the current hour: the latest entry that has started, or the first one."""
    entry = timeseries[0]
    for candidate in timeseries:
        start = _time(candidate)
        if start is None or start > now:
            break
        entry = candidate

    instant = _details(entry, "instant")
    condition, icon = describe(_symbol(entry, "next_1_hours", "next_6_hours", "next_12_hours"))
    temperature = _number(instant.get("air_temperature"))
    feels_like = _number(instant.get("apparent_air_temperature"))
    wind = _number(instant.get("wind_speed"))
    pressure = _number(instant.get("air_pressure_at_sea_level"))
    humidity = _number(instant.get("relative_humidity"))
    uv = _number(instant.get("ultraviolet_index_clear_sky"))

    return {
        "temperature": C_TO_F(temperature) if temperature is not None else None,
        # Without a feels-like value, it is the air temperature (as with the National Weather Service)
        "feels_like": C_TO_F(feels_like) if feels_like is not None else (C_TO_F(temperature) if temperature is not None else None),
        "condition": condition,
        "icon": icon,
        "humidity": round(humidity) if humidity is not None else None,
        "wind_speed": wind * MS_TO_MPH if wind is not None else None,
        "pressure": pressure * HPA_TO_INHG if pressure is not None else None,
        "uv_index": round(uv) if uv is not None else None,
        "visibility": None,  # MET Norway does not forecast visibility
    }


def build_forecast(timeseries: List[Dict[str, Any]], zone: tzinfo, today: date) -> List[Dict[str, Any]]:
    """One entry per local day from `today`: highs and lows, chance of precipitation, UV, and the daytime sky."""
    days: Dict[date, Dict[str, Any]] = {}
    for entry in timeseries:
        start = _time(entry)
        if start is None:
            continue
        local = start.astimezone(zone)
        if local.date() < today:
            continue
        day = days.setdefault(local.date(), {"temps": [], "pops": [], "uv": [], "symbols": []})

        instant = _details(entry, "instant")
        six = _details(entry, "next_6_hours")
        for value in (instant.get("air_temperature"), six.get("air_temperature_max"), six.get("air_temperature_min")):
            if _number(value) is not None:
                day["temps"].append(value)
        for block in ("next_1_hours", "next_6_hours", "next_12_hours"):
            pop = _number(_details(entry, block).get("probability_of_precipitation"))
            if pop is not None:
                day["pops"].append(pop)
        uv = _number(instant.get("ultraviolet_index_clear_sky"))
        if uv is not None:
            day["uv"].append(uv)
        # The day's sky: the 12 hours from about 6:00, else the 6 hours from about noon
        symbol = _symbol(entry, "next_12_hours")
        if symbol:
            day["symbols"].append((abs(local.hour - 6), symbol))
        symbol = _symbol(entry, "next_6_hours")
        if symbol:
            day["symbols"].append((10 + abs(local.hour - 12), symbol))

    forecast: List[Dict[str, Any]] = []
    for day_date in sorted(days)[:FORECAST_DAYS]:
        day = days[day_date]
        condition, icon = describe(min(day["symbols"])[1] if day["symbols"] else None)
        forecast.append({
            "day": day_date.isoformat(),
            "high": C_TO_F(max(day["temps"])) if day["temps"] else None,
            "low": C_TO_F(min(day["temps"])) if day["temps"] else None,
            "condition": condition,
            "icon": icon,
            "precipitation_chance": round(max(day["pops"])) if day["pops"] else None,
            "uv_index": round(max(day["uv"])) if day["uv"] else None,
        })
    return forecast


def normalize(raw: Dict[str, Any], longitude: float = 0.0, now: Optional[datetime] = None,
              zone: Optional[tzinfo] = None) -> Dict[str, Any]:
    """
    Outpost's normalized format. Readings are unrounded, in °F, mph, inHg, and miles; the updater
    converts them to OUTPOST_UNITS and rounds them (app/units.py).
    """
    timeseries = ((raw or {}).get("properties") or {}).get("timeseries") or []
    if not timeseries:
        raise RuntimeError("MET Norway response has no forecast")
    now = now or datetime.now(timezone.utc)
    zone = zone or local_zone(longitude)
    return {
        "source": SOURCE,
        "current": build_current(timeseries, now),
        "forecast": build_forecast(timeseries, zone, now.astimezone(zone).date()),
        "alerts": [],
    }


def fetch(latitude: float, longitude: float, user_agent: str) -> Dict[str, Any]:
    """Fetch (or reuse, while it is still current) and normalize the forecast for a location."""
    return normalize(fetch_raw(latitude, longitude, user_agent), longitude)
