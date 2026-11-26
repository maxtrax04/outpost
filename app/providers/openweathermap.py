"""
OpenWeatherMap provider (One Call API 4.0, api.openweathermap.org/data/4.0/onecall).

Docs:  https://openweathermap.org/api/one-call-4
Terms: needs an API key from https://openweathermap.org with a "One Call API" subscription
       (OUTPOST_OPENWEATHERMAP_API_KEY). 1,000 calls a day are free, but a payment card must be on
       file and calls beyond that are billed, so it is never part of OUTPOST_PROVIDER=auto, and only
       home uses it. OpenWeather asks for credit, which the dashboard footer gives (sources.weather).

Version 4.0 has an endpoint per kind of data, and each request is a call. Outpost asks for the current
conditions at most every 10 minutes, the hourly timeline every 30, and the daily timeline every hour
(about 216 calls a day however often it updates), each alert's details once, and never makes more than
DAILY_CALL_LIMIT calls in a UTC day.

The key has to go in the address (appid=). The address is never logged or put in an error message,
and the response cache is keyed without it.

Requested with units=imperial: °F and mph. Pressure still comes in hPa, visibility in metres, and
rain and snow in millimetres (snow as water), so those are converted here to inHg, miles, and inches.

Alerts (fetch_alerts): the records list the IDs of the alerts in effect, and each alert's details are
a call of their own. They are the official warnings national weather services send OpenWeather, with no
severity, so it is worked out from the event's name; an empty list can also mean the country is not
covered.

Uses only the Python standard library.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Dict, List, Optional, Tuple

from providers import hourly as hours
from zoneinfo import ZoneInfo

API_URL = "https://api.openweathermap.org/data/4.0/onecall"
SOURCE = "OpenWeather"
# Its alerts (fetch_alerts) are not counted: in the US the updater asks NWS first
CAPABILITIES = frozenset({"current", "forecast", "uv"})
TIMEOUT_SECONDS = 20
FORECAST_DAYS = 5
# How long each answer is kept, by endpoint: about 216 calls a day, well inside the free 1,000
CACHE_SECONDS = {"current": 600, "timeline/1h": 1800, "timeline/1day": 3600}
MIN_CACHE_SECONDS = min(CACHE_SECONDS.values())
# An alert's details are kept until it ends, at least an hour and at most a day
ALERT_CACHE_MIN_SECONDS = 3600
ALERT_CACHE_MAX_SECONDS = 24 * 3600
# Never more calls than this in a UTC day (OpenWeather's free calls are counted per UTC day)
DAILY_CALL_LIMIT = 900
# After the key is refused, wait this long before trying it again (a new key can take a while to work)
REFUSED_KEY_WAIT_SECONDS = 600
# After "too many requests", wait this long
TOO_MANY_WAIT_SECONDS = 3600

HPA_TO_INHG = 0.02952998
METRES_PER_MILE = 1609.344
MM_PER_INCH = 25.4

# (endpoint, latitude, longitude) or ("alert", id) -> {"expires": unix time, "raw": decoded JSON}
_cache: Dict[Tuple[str, ...], Dict[str, Any]] = {}
# No requests before this time (after a refused key or too many requests)
_blocked_until = 0.0
_blocked_reason = ""
# Calls made today: {"day": "YYYY-MM-DD" (UTC), "calls": count}
_calls: Dict[str, Any] = {"day": "", "calls": 0}


# ---------------------------------------------------------------- conditions

def _group(code: int, night: bool) -> Tuple[str, str]:
    """(short condition text, dashboard icon) for an OpenWeather condition code."""
    if 200 <= code < 300:
        return "Thunderstorms", "storm"
    if 300 <= code < 400:
        return "Drizzle", "drizzle"
    if code == 511:
        return "Freezing rain", "sleet"
    if 500 <= code < 600:
        return "Rain", "rain"
    if 611 <= code <= 616:
        return "Sleet", "sleet"
    if 600 <= code < 700:
        return "Snow", "snow"
    if code == 771:
        return "Squalls", "wind"
    if code == 781:
        return "Tornado", "storm"
    if 700 <= code < 800:
        return "Fog", "fog"
    if code == 800:
        return "Clear", "clear-night" if night else "sunny"
    if code in (801, 802):
        return "Partly cloudy", "partly-cloudy-night" if night else "partly-cloudy"
    if code in (803, 804):
        return "Cloudy", "cloudy"
    return "Unknown", "unknown"


# A description longer than this is too long for the dashboard; the code's own text is used instead
MAX_DESCRIPTION_LENGTH = 30


def describe(weather: Any) -> Tuple[str, str]:
    """(condition text, dashboard icon) from a `weather` list: its first entry's code and icon."""
    first = weather[0] if isinstance(weather, list) and weather and isinstance(weather[0], dict) else {}
    code = first.get("id")
    if not isinstance(code, int) or isinstance(code, bool):
        return "Unknown", "unknown"
    icon = first.get("icon")
    text, name = _group(code, isinstance(icon, str) and icon.endswith("n"))
    description = first.get("description")
    if isinstance(description, str) and 0 < len(description.strip()) <= MAX_DESCRIPTION_LENGTH and name != "unknown":
        text = description.strip()[0].upper() + description.strip()[1:]
    return text, name


# ---------------------------------------------------------------- HTTP

def _today(now: float) -> str:
    return datetime.fromtimestamp(now, timezone.utc).date().isoformat()


def calls_today(now: Optional[float] = None) -> int:
    """The calls made so far in this UTC day."""
    now = time.time() if now is None else now
    return _calls["calls"] if _calls["day"] == _today(now) else 0


def _request(path: str, params: Dict[str, str], api_key: str, user_agent: str, now: float) -> Any:
    """One call to the API (counted). Errors never include the address, which has the key in it."""
    global _blocked_until, _blocked_reason

    if now < _blocked_until:
        raise RuntimeError(_blocked_reason)
    if calls_today(now) >= DAILY_CALL_LIMIT:
        raise RuntimeError(f"OpenWeatherMap: {DAILY_CALL_LIMIT} calls made today, the most Outpost makes in a day "
                           "(it resets at midnight UTC)")
    # Never log or show this address
    url = f"{API_URL}/{path}?{urllib.parse.urlencode({**params, 'units': 'imperial', 'appid': api_key})}"
    request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    if _calls["day"] != _today(now):
        _calls.update({"day": _today(now), "calls": 0})
    _calls["calls"] += 1
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        # Only the status goes in messages: the error also holds the address
        if error.code == 401:
            _blocked_until = now + REFUSED_KEY_WAIT_SECONDS
            _blocked_reason = ("OpenWeatherMap refused the API key (check OUTPOST_OPENWEATHERMAP_API_KEY, and that it "
                               "has a One Call API subscription); trying again in "
                               f"{REFUSED_KEY_WAIT_SECONDS // 60} minutes")
            raise RuntimeError(f"OpenWeatherMap HTTP 401: {_blocked_reason}") from None
        if error.code == 429:
            _blocked_until = now + TOO_MANY_WAIT_SECONDS
            _blocked_reason = "OpenWeatherMap said too many requests; waiting before asking again"
            raise RuntimeError(f"OpenWeatherMap HTTP 429: too many requests; trying again in "
                               f"{TOO_MANY_WAIT_SECONDS // 60} minutes") from None
        raise RuntimeError(f"OpenWeatherMap HTTP {error.code}") from None
    except urllib.error.URLError as error:
        reason = error.reason if not isinstance(error.reason, str) or "appid" not in error.reason else "request failed"
        raise RuntimeError(f"OpenWeatherMap unreachable: {reason}") from None
    except ValueError:
        raise RuntimeError("OpenWeatherMap returned invalid JSON") from None
    except OSError as error:
        raise RuntimeError(f"OpenWeatherMap unreachable: {error.strerror or type(error).__name__}") from None


def _endpoint(path: str, latitude: float, longitude: float, api_key: str, user_agent: str) -> Dict[str, Any]:
    """One endpoint's answer for a place, kept for CACHE_SECONDS[path]."""
    place = (f"{latitude:.4f}", f"{longitude:.4f}")
    key = (path,) + place
    now = time.time()
    cached = _cache.get(key)
    if cached and now < cached["expires"]:
        return cached["raw"]
    raw = _request(path, {"lat": place[0], "lon": place[1]}, api_key, user_agent, now)
    if not isinstance(raw, dict):
        raise RuntimeError("OpenWeatherMap returned an unexpected answer")
    _cache[key] = {"expires": now + CACHE_SECONDS[path], "raw": raw}
    return raw


def _records(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    data = raw.get("data")
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def fetch_raw(latitude: float, longitude: float, api_key: str, user_agent: str) -> Dict[str, Any]:
    """
    The current conditions and the hourly and daily timelines, as
    {"timezone", "timezone_offset", "current": record, "hourly": [...], "daily": [...]}.
    """
    if not api_key:
        raise RuntimeError("OpenWeatherMap needs an API key: set OUTPOST_OPENWEATHERMAP_API_KEY")
    current = _endpoint("current", latitude, longitude, api_key, user_agent)
    hourly = _endpoint("timeline/1h", latitude, longitude, api_key, user_agent)
    daily = _endpoint("timeline/1day", latitude, longitude, api_key, user_agent)
    records = _records(current)
    return {
        "timezone": current.get("timezone"),
        "timezone_offset": current.get("timezone_offset"),
        "current": records[0] if records else None,
        "hourly": _records(hourly),
        "daily": _records(daily),
    }


# ---------------------------------------------------------------- normalizing

def _number(value: Any) -> Optional[float]:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value == value else None


def _time(value: Any) -> Optional[datetime]:
    number = _number(value)
    return datetime.fromtimestamp(number, timezone.utc) if number is not None and number >= 0 else None


def _iso(value: Any) -> Optional[str]:
    moment = _time(value)
    return moment.isoformat() if moment else None


def _inches(*amounts: Any) -> Optional[float]:
    """Millimetres of rain and snow (as water) together, in inches; None when neither is given."""
    given = [value for value in (_number(amount) for amount in amounts) if value is not None]
    return sum(given) / MM_PER_INCH if given else None


def _hour_amount(block: Any) -> Any:
    """The millimetres in an hour from a rain or snow block ({"1h": mm/h})."""
    return block.get("1h") if isinstance(block, dict) else None


def _day_amount(block: Any) -> Any:
    """
    The millimetres in a day from a daily record's rain or snow. OpenWeather's pages disagree on its
    form: a number is the day's total, and {"1h": mm/h} the average rate over the day.
    """
    if isinstance(block, dict):
        rate = _number(block.get("1h"))
        return rate * 24 if rate is not None else None
    return block


def _zone(raw: Dict[str, Any]) -> tzinfo:
    """The location's time zone, from the response (its name, or else its offset in seconds)."""
    try:
        return ZoneInfo(raw.get("timezone") or "")
    except Exception:
        pass
    offset = _number(raw.get("timezone_offset"))
    if offset is not None:
        return timezone(timedelta(seconds=offset))
    return timezone.utc


def build_current(current: Dict[str, Any]) -> Dict[str, Any]:
    condition, icon = describe(current.get("weather"))
    pressure = _number(current.get("pressure"))
    visibility = _number(current.get("visibility"))
    uv = _number(current.get("uvi"))
    return {
        "temperature": _number(current.get("temp")),
        "feels_like": _number(current.get("feels_like")),
        "condition": condition,
        "icon": icon,
        "humidity": _number(current.get("humidity")),
        "wind_speed": _number(current.get("wind_speed")),
        "wind_gust": _number(current.get("wind_gust")),
        "wind_direction": _number(current.get("wind_deg")),
        "dew_point": _number(current.get("dew_point")),  # °F (units=imperial)
        "observed_at": _iso(current.get("dt")),
        "pressure": pressure * HPA_TO_INHG if pressure is not None else None,  # hPa
        "uv_index": round(uv) if uv is not None else None,
        "visibility": visibility / METRES_PER_MILE if visibility is not None else None,  # metres, up to 10 km
    }


def _percent(value: Any) -> Optional[int]:
    """OpenWeather gives chances as 0 to 1."""
    number = _number(value)
    return round(min(1.0, max(0.0, number)) * 100) if number is not None else None


def build_forecast(days: Any, zone: tzinfo) -> List[Dict[str, Any]]:
    """One entry per day (dt is midday there). High and low are the day's temp.max and temp.min."""
    forecast: List[Dict[str, Any]] = []
    for day in days if isinstance(days, list) else []:
        start = _time(day.get("dt")) if isinstance(day, dict) else None
        if start is None:
            continue
        temps = day.get("temp") if isinstance(day.get("temp"), dict) else {}
        condition, icon = describe(day.get("weather"))
        uv = _number(day.get("uvi"))
        forecast.append({
            "day": start.astimezone(zone).date().isoformat(),
            "high": _number(temps.get("max")),
            "low": _number(temps.get("min")),
            "condition": condition,
            "icon": icon,
            "precipitation_chance": _percent(day.get("pop")),
            "precipitation": hours.amount(_inches(_day_amount(day.get("rain")), _day_amount(day.get("snow")))),
            "uv_index": round(uv) if uv is not None else None,
        })
        if len(forecast) == FORECAST_DAYS:
            break
    return forecast


def build_hourly(entries: Any, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """The next hours (providers/hourly.py) from the hourly timeline (up to 20 hours)."""
    result = []
    for item in entries if isinstance(entries, list) else []:
        start = _time(item.get("dt")) if isinstance(item, dict) else None
        if start is None:
            continue
        condition, icon = describe(item.get("weather"))
        chance = _number(item.get("pop"))
        result.append(hours.entry(start, _number(item.get("temp")), condition, icon,
                                  chance * 100 if chance is not None else None,
                                  _number(item.get("wind_speed")), _number(item.get("wind_deg")),
                                  _inches(_hour_amount(item.get("rain")), _hour_amount(item.get("snow")))))
    return hours.upcoming(result, now)


def normalize(raw: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """
    Outpost's normalized format, from fetch_raw's answer. Readings are unrounded, in °F, mph, inHg,
    miles, and inches; the updater converts them to OUTPOST_UNITS and rounds them (app/units.py).
    """
    raw = raw if isinstance(raw, dict) else {}
    current = raw.get("current")
    days = raw.get("daily")
    if not isinstance(current, dict) or not isinstance(days, list) or not days:
        raise RuntimeError("OpenWeatherMap response is missing current or daily data")
    zone = raw.get("timezone")
    return {
        "source": SOURCE,
        "current": build_current(current),
        "forecast": build_forecast(days, _zone(raw)),
        "hourly": build_hourly(raw.get("hourly"), now),
        "timezone": zone if isinstance(zone, str) else None,
        "alerts": [],
    }


def fetch(latitude: float, longitude: float, api_key: str, user_agent: str) -> Dict[str, Any]:
    """Fetch (or reuse) and normalize the forecast for a location."""
    return normalize(fetch_raw(latitude, longitude, api_key, user_agent))


# ---------------------------------------------------------------- alerts

SEVERITIES = ("extreme", "severe", "moderate", "minor")
SEVERITY_ORDER = {name: rank for rank, name in enumerate(SEVERITIES + ("unknown",))}
MAX_ALERTS = 5

# Words in an event's name that tell its severity, checked in this order. MeteoAlarm's colors
# (yellow, orange, red) come first, then the National Weather Service's kinds of product.
SEVERITY_WORDS = (
    ("red", "extreme"), ("extreme", "extreme"),
    ("orange", "severe"), ("amber", "severe"),
    ("yellow", "moderate"),
    ("warning", "severe"), ("watch", "moderate"),
    ("advisory", "minor"), ("statement", "minor"),
)


def _text(value: Any) -> str:
    return " ".join(value.split()) if isinstance(value, str) else ""


def severity(event: str) -> str:
    """The severity an event's name makes clear, such as "Red Wind Warning" (extreme), else "unknown"."""
    words = set(event.lower().replace("-", " ").split())
    for word, level in SEVERITY_WORDS:
        if word in words:
            return level
    return "unknown"


def _description(value: Any) -> str:
    """The alert's text: English when there is a choice ([{language, description}]), else the first."""
    if isinstance(value, str):
        return _text(value)
    texts = [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []
    english = [item for item in texts if str(item.get("language", "")).lower().startswith("en")]
    for item in english + texts:
        text = _text(item.get("description"))
        if text:
            return text
    return ""


def alert_ids(raw: Dict[str, Any]) -> List[str]:
    """The IDs of the alerts listed in the current conditions and the hourly timeline, in order, once each."""
    raw = raw if isinstance(raw, dict) else {}
    records = ([raw.get("current")] if isinstance(raw.get("current"), dict) else []) + \
              [item for item in raw.get("hourly") or [] if isinstance(item, dict)]
    ids: List[str] = []
    for record in records:
        for alert_id in record.get("alerts") or []:
            if isinstance(alert_id, str) and alert_id.strip() and alert_id not in ids:
                ids.append(alert_id)
    return ids


def build_alert(detail: Dict[str, Any]) -> Dict[str, Any]:
    """One alert in Outpost's format, from the alert endpoint's answer."""
    tags = [_text(tag) for tag in detail.get("tags") or [] if _text(tag)] if isinstance(detail.get("tags"), list) else []
    title = _text(detail.get("event")) or (tags[0] if tags else "") or "Weather alert"
    return {
        "title": title,
        "description": _description(detail.get("description")),
        "severity": severity(title),
        "onset": _iso(detail.get("start")),
        "expires": _iso(detail.get("end")),
        "uri": None,
    }


def build_alerts(details: Any) -> List[Dict[str, Any]]:
    """Outpost's alert format, most serious first. Repeats of the same alert are dropped."""
    alerts: List[Dict[str, Any]] = []
    seen = set()
    for detail in details if isinstance(details, list) else []:
        if not isinstance(detail, dict):
            continue
        alert = build_alert(detail)
        key = (alert["title"].lower(), alert["expires"], alert["description"].lower())
        if key in seen:
            continue
        seen.add(key)
        alerts.append(alert)
    alerts.sort(key=lambda a: SEVERITY_ORDER[a["severity"]])
    return alerts[:MAX_ALERTS]


def _alert_detail(alert_id: str, api_key: str, user_agent: str) -> Dict[str, Any]:
    """One alert's details, kept until it ends (one call each)."""
    key = ("alert", alert_id)
    now = time.time()
    cached = _cache.get(key)
    if cached and now < cached["expires"]:
        return cached["raw"]
    raw = _request(f"alert/{urllib.parse.quote(alert_id, safe='')}", {}, api_key, user_agent, now)
    if not isinstance(raw, dict):
        raise RuntimeError("OpenWeatherMap returned an unexpected alert")
    end = _number(raw.get("end"))
    keep = min(ALERT_CACHE_MAX_SECONDS, max(ALERT_CACHE_MIN_SECONDS, (end or 0) - now))
    _cache[key] = {"expires": now + keep, "raw": raw}
    return raw


def fetch_alerts(latitude: float, longitude: float, api_key: str, user_agent: str) -> List[Dict[str, Any]]:
    """
    The location's alerts. Their IDs come with the current conditions and the hourly timeline (shared
    with the weather when it is from OpenWeatherMap too), and each one's details are a call, made once.
    """
    if not api_key:
        raise RuntimeError("OpenWeatherMap needs an API key: set OUTPOST_OPENWEATHERMAP_API_KEY")
    # Only the two endpoints that list alerts, so alerts alone don't ask for the daily timeline
    current = _records(_endpoint("current", latitude, longitude, api_key, user_agent))
    hourly = _records(_endpoint("timeline/1h", latitude, longitude, api_key, user_agent))
    ids = alert_ids({"current": current[0] if current else None, "hourly": hourly})[:MAX_ALERTS * 2]
    return build_alerts([_alert_detail(alert_id, api_key, user_agent) for alert_id in ids])
