"""
National Weather Service provider (api.weather.gov).

Covers the United States and its territories only. Free, no API key.
NWS asks for a User-Agent that identifies your app and how to reach you. Outpost builds it
from the OUTPOST_CONTACT setting, for example:  Outpost/0.3.0 (you@example.com)

Data comes from four calls:
  1. /points/{lat},{lon}          -> forecast URL and nearby stations (cached)
  2. forecast URL                 -> multi-day forecast
  3. /stations/{id}/observations/latest -> current conditions
  4. /alerts/active?point=...     -> active watches and warnings

Uses only the Python standard library.
"""

import json
import re
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

BASE_URL = "https://api.weather.gov"
SOURCE = "National Weather Service (weather.gov)"
TIMEOUT_SECONDS = 20
RETRIES = 3
FORECAST_DAYS = 5
STATIONS_TO_TRY = 4
MAX_OBSERVATION_AGE_SECONDS = 3 * 3600
POINT_CACHE_SECONDS = 6 * 3600
NO_COVERAGE_CACHE_SECONDS = 30 * 60
MAX_ALERTS = 5

KMH_TO_MPH = 0.621371
MS_TO_MPH = 2.236936
PA_TO_INHG = 0.0002953
METERS_PER_MILE = 1609.344

NIGHT_ICONS = {
    "sunny": "clear-night",
    "partly-cloudy": "partly-cloudy-night",
}

SEVERITY_ORDER = {"extreme": 0, "severe": 1, "moderate": 2, "minor": 3, "unknown": 4}


class NoCoverageError(RuntimeError):
    """The location is outside NWS coverage (not in the US)."""


class _NotFound(Exception):
    pass


# (latitude, longitude) -> (expires_at, point info or None)
_point_cache: Dict[Tuple[str, str], Tuple[float, Optional[Dict[str, Any]]]] = {}


# ---------------------------------------------------------------- HTTP

def _get(url: str, user_agent: str) -> Dict[str, Any]:
    """GET a JSON document, retrying on temporary server errors."""
    headers = {"User-Agent": user_agent, "Accept": "application/geo+json"}
    last_error: Exception = RuntimeError("NWS request failed")

    for attempt in range(1, RETRIES + 1):
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 404:
                raise _NotFound(url) from error
            if error.code < 500 and error.code != 429:
                raise RuntimeError(f"NWS HTTP {error.code} for {url}") from error
            last_error = RuntimeError(f"NWS HTTP {error.code}")
        except ValueError as error:
            last_error = RuntimeError(f"NWS returned invalid JSON: {error}")
        except OSError as error:
            last_error = RuntimeError(f"NWS unreachable: {getattr(error, 'reason', error)}")

        if attempt < RETRIES:
            time.sleep(2 * attempt)

    raise last_error


# ---------------------------------------------------------------- lookups

def get_point(latitude: float, longitude: float, user_agent: str) -> Dict[str, Any]:
    """Resolve a coordinate to its forecast grid. Cached for several hours."""
    key = (f"{latitude:.4f}", f"{longitude:.4f}")
    cached = _point_cache.get(key)
    if cached and time.time() < cached[0]:
        if cached[1] is None:
            raise NoCoverageError("NWS has no data for this location (US only)")
        return cached[1]

    try:
        data = _get(f"{BASE_URL}/points/{key[0]},{key[1]}", user_agent)
    except _NotFound:
        _point_cache[key] = (time.time() + NO_COVERAGE_CACHE_SECONDS, None)
        raise NoCoverageError("NWS has no data for this location (US only)")

    props = data.get("properties") or {}
    if not props.get("forecast"):
        raise RuntimeError("NWS point lookup did not return a forecast URL")

    point = {
        "forecast_url": props["forecast"],
        "stations_url": props.get("observationStations"),
        "station_ids": None,
    }
    _point_cache[key] = (time.time() + POINT_CACHE_SECONDS, point)
    return point


def _station_ids(point: Dict[str, Any], user_agent: str) -> List[str]:
    if point["station_ids"] is None:
        ids: List[str] = []
        if point.get("stations_url"):
            data = _get(point["stations_url"], user_agent)
            for feature in data.get("features") or []:
                station = (feature.get("properties") or {}).get("stationIdentifier")
                if station:
                    ids.append(station)
        point["station_ids"] = ids
    return point["station_ids"]


def _fresh_observation(point: Dict[str, Any], user_agent: str) -> Optional[Dict[str, Any]]:
    """Return the first nearby station's latest observation that has a recent temperature."""
    try:
        stations = _station_ids(point, user_agent)
    except (RuntimeError, _NotFound):
        return None

    for station in stations[:STATIONS_TO_TRY]:
        try:
            data = _get(f"{BASE_URL}/stations/{station}/observations/latest", user_agent)
        except (RuntimeError, _NotFound):
            continue

        props = data.get("properties") or {}
        if _num(props.get("temperature")) is None:
            continue

        try:
            observed = datetime.fromisoformat(props["timestamp"])
            if (datetime.now(timezone.utc) - observed).total_seconds() > MAX_OBSERVATION_AGE_SECONDS:
                continue
        except Exception:
            continue

        props["_station"] = station
        return props

    return None


# ---------------------------------------------------------------- conversions

def _num(quantity: Any) -> Optional[float]:
    """Read the number from an NWS {"value": ..., "unitCode": ...} object."""
    if isinstance(quantity, dict):
        quantity = quantity.get("value")
    return quantity if isinstance(quantity, (int, float)) else None


def _round(value: Optional[float], digits: int = 0) -> Optional[float]:
    if value is None:
        return None
    result = round(value, digits)
    return int(result) if digits == 0 else result


def _c_to_f(celsius: Optional[float]) -> Optional[float]:
    return None if celsius is None else celsius * 9 / 5 + 32


def _speed_mph(quantity: Any) -> Optional[float]:
    value = _num(quantity)
    if value is None:
        return None
    unit = quantity.get("unitCode", "") if isinstance(quantity, dict) else ""
    return value * (MS_TO_MPH if "m_s-1" in unit else KMH_TO_MPH)


def _period_temp_f(period: Dict[str, Any]) -> Optional[float]:
    value = _num(period.get("temperature"))
    if value is None:
        return None
    return _c_to_f(value) if str(period.get("temperatureUnit", "F")).upper() == "C" else value


def _period_wind_mph(period: Dict[str, Any]) -> Optional[float]:
    """Parse strings such as '10 mph' or '5 to 15 mph' (uses the higher number)."""
    numbers = [int(n) for n in re.findall(r"\d+", str(period.get("windSpeed") or ""))]
    return max(numbers) if numbers else None


def icon_from_text(text: Optional[str], is_day: bool = True) -> str:
    """Map NWS forecast wording (e.g. 'Mostly Cloudy') to an Outpost icon name."""
    t = (text or "").lower()

    if "thunder" in t:
        return "storm"
    if any(k in t for k in ("sleet", "freezing rain", "freezing drizzle", "wintry mix",
                            "ice pellet", "rain and snow", "snow and rain", "rain/snow", "snow/rain")):
        return "sleet"
    if any(k in t for k in ("snow", "flurr", "blizzard")):
        return "snow"
    if "drizzle" in t:
        return "drizzle"
    if "rain" in t or "shower" in t:
        return "rain"
    if any(k in t for k in ("fog", "haze", "mist", "smoke", "dust")):
        return "fog"

    if "partly" in t or "scattered" in t or "few clouds" in t:
        icon = "partly-cloudy"
    elif "cloud" in t or "overcast" in t:
        icon = "cloudy"
    elif "sunny" in t or "clear" in t or "fair" in t:
        icon = "sunny"
    elif any(k in t for k in ("breezy", "windy", "blustery")):
        return "wind"
    else:
        return "unknown"

    return icon if is_day else NIGHT_ICONS.get(icon, icon)


# ---------------------------------------------------------------- normalizing

def build_current(periods: List[Dict[str, Any]], observation: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    first = periods[0] if periods else {}
    is_day = bool(first.get("isDaytime", True))

    if observation:
        temp_f = _c_to_f(_num(observation.get("temperature")))
        feels_c = _num(observation.get("heatIndex"))
        if feels_c is None:
            feels_c = _num(observation.get("windChill"))
        feels_f = _c_to_f(feels_c) if feels_c is not None else temp_f

        pressure_pa = _num(observation.get("seaLevelPressure"))
        if pressure_pa is None:
            pressure_pa = _num(observation.get("barometricPressure"))
        visibility_m = _num(observation.get("visibility"))

        condition = observation.get("textDescription") or first.get("shortForecast") or "Unknown"

        return {
            "temperature_f": _round(temp_f),
            "feels_like_f": _round(feels_f),
            "condition": condition,
            "icon": icon_from_text(condition, is_day),
            "humidity_percent": _round(_num(observation.get("relativeHumidity"))),
            "wind_mph": _round(_speed_mph(observation.get("windSpeed"))),
            "pressure_inhg": _round(pressure_pa * PA_TO_INHG, 2) if pressure_pa is not None else None,
            "uv_index": None,  # NWS does not publish UV index
            "visibility_miles": _round(visibility_m / METERS_PER_MILE, 1) if visibility_m is not None else None,
        }

    # No usable observation: fall back to the forecast's current period
    temp_f = _period_temp_f(first)
    condition = first.get("shortForecast") or "Unknown"
    return {
        "temperature_f": _round(temp_f),
        "feels_like_f": _round(temp_f),
        "condition": condition,
        "icon": icon_from_text(condition, is_day),
        "humidity_percent": _round(_num(first.get("relativeHumidity"))),
        "wind_mph": _period_wind_mph(first),
        "pressure_inhg": None,
        "uv_index": None,
        "visibility_miles": None,
    }


def build_forecast(periods: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge NWS day/night periods into one entry per calendar day."""
    days: Dict[str, Dict[str, Any]] = {}
    order: List[str] = []

    for period in periods:
        date = (period.get("startTime") or "")[:10]
        if len(date) != 10:
            continue

        entry = days.get(date)
        if entry is None:
            entry = days[date] = {"highs": [], "lows": [], "pops": [], "day_text": None, "night_text": None}
            order.append(date)

        temp = _period_temp_f(period)
        if period.get("isDaytime"):
            if temp is not None:
                entry["highs"].append(temp)
            entry["day_text"] = entry["day_text"] or period.get("shortForecast")
        else:
            if temp is not None:
                entry["lows"].append(temp)
            entry["night_text"] = entry["night_text"] or period.get("shortForecast")

        pop = _num(period.get("probabilityOfPrecipitation"))
        if pop is not None:
            entry["pops"].append(pop)

    forecast: List[Dict[str, Any]] = []
    for date in order[:FORECAST_DAYS]:
        entry = days[date]
        text = entry["day_text"] or entry["night_text"] or "Unknown"
        forecast.append({
            "day": date,
            "high_f": _round(max(entry["highs"])) if entry["highs"] else None,
            "low_f": _round(min(entry["lows"])) if entry["lows"] else None,
            "condition": text,
            "icon": icon_from_text(text, is_day=entry["day_text"] is not None),
            "precipitation_percent": _round(max(entry["pops"])) if entry["pops"] else 0,
            "uv_index": None,
        })
    return forecast


def build_alerts(features: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    alerts: List[Dict[str, Any]] = []
    for feature in features or []:
        props = feature.get("properties") or {}
        if props.get("status") not in (None, "Actual") or props.get("messageType") == "Cancel":
            continue
        alerts.append({
            "title": props.get("event") or "Weather alert",
            "description": props.get("headline") or "",
            "severity": (props.get("severity") or "unknown").lower(),
            "expires": props.get("ends") or props.get("expires"),
            "uri": feature.get("id") or props.get("@id"),
        })
    alerts.sort(key=lambda a: SEVERITY_ORDER.get(a["severity"], 4))
    return alerts[:MAX_ALERTS]


def normalize(periods: List[Dict[str, Any]],
              observation: Optional[Dict[str, Any]],
              alert_features: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    if not periods:
        raise RuntimeError("NWS forecast contained no periods")
    return {
        "source": SOURCE,
        "current": build_current(periods, observation),
        "forecast": build_forecast(periods),
        "alerts": build_alerts(alert_features),
        "alerts_supported": True,
    }


# ---------------------------------------------------------------- entry point

def fetch(latitude: float, longitude: float, user_agent: str) -> Dict[str, Any]:
    """Fetch and normalize NWS data. Raises NoCoverageError outside the US."""
    point = get_point(latitude, longitude, user_agent)

    try:
        forecast = _get(point["forecast_url"], user_agent)
    except _NotFound:
        # Grid mapping may have changed; drop the cache so the next run re-resolves it
        _point_cache.clear()
        raise RuntimeError("NWS forecast URL not found; will retry with a fresh lookup")
    periods = (forecast.get("properties") or {}).get("periods") or []

    observation = _fresh_observation(point, user_agent)

    # A failed alert lookup must not look like "no alerts", so let it fail the update
    try:
        alerts = _get(f"{BASE_URL}/alerts/active?point={latitude:.4f},{longitude:.4f}", user_agent)
    except _NotFound:
        raise RuntimeError("NWS alerts lookup returned 404")

    return normalize(periods, observation, alerts.get("features"))
