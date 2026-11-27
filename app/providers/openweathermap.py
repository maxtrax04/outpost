"""
OpenWeatherMap provider (api.openweathermap.org): One Call API 3.0, or the free services.

Docs:  https://openweathermap.org/api/one-call-3
Terms: needs an API key from https://openweathermap.org with a "One Call by Call" subscription
       (OUTPOST_OPENWEATHERMAP_API_KEY). 1,000 calls a day are free, but a payment card must be on
       file and calls beyond that are billed, so it is never part of OUTPOST_PROVIDER=auto, and only
       home uses it. Outpost keeps each answer for at least 10 minutes (at most 144 calls a day
       however often it updates) and never makes more than DAILY_CALL_LIMIT calls in a UTC day.
       OpenWeather asks for credit, which the dashboard footer gives (sources.weather).

End of life: One Call 3.0 has no end date yet (OpenWeather recommends 4.0 for new integrations, and
says 3.0 "remains available"). Outpost watches for the signs that it is going away: a `Deprecation`
or `Sunset` header (RFC 9745, RFC 8594) on an answer, which retirement_notice() reports for the
updater to warn about, and HTTP 410 Gone, which is an error that says an Outpost update is needed.
docs/releasing.md has the same check by hand before each release.

The key has to go in the address (appid=). The address is never logged or put in an error message,
and the response cache is keyed without it.

Requested with units=imperial: °F and mph. Pressure still comes in hPa, visibility in metres, and
rain and snow in millimetres (snow as water), so those are converted here to inHg, miles, and inches.

Alerts (fetch_alerts) come in the same response: the official warnings national weather services
send OpenWeather. It gives no severity, so it is worked out from the event's name, and an empty list
can also mean the country is not covered.

The free plan (OUTPOST_OPENWEATHERMAP_PLAN=free, fetch_free) needs only an account, no subscription:
current weather (/data/2.5/weather) and the 5 day / 3 hour forecast (/data/2.5/forecast), two calls
kept 10 minutes each (at most 288 a day). The days are worked out from the 3-hour steps, `hourly` has
one entry per 3 hours, and there is no UV index or alerts (the updater fills UV from Open-Meteo) and
no time zone name, only an offset. Dew point is worked out from temperature and humidity.

Uses only the Python standard library.
"""

import email.utils
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone, tzinfo
from typing import Any, Dict, List, Optional, Tuple

from providers import hourly as hours
from zoneinfo import ZoneInfo

API_URL = "https://api.openweathermap.org/data/3.0/onecall"
# The free services: no subscription needed
FREE_WEATHER_URL = "https://api.openweathermap.org/data/2.5/weather"
FREE_FORECAST_URL = "https://api.openweathermap.org/data/2.5/forecast"
SOURCE = "OpenWeather"
# Its alerts (fetch_alerts) are not counted: in the US the updater asks NWS first
CAPABILITIES = frozenset({"current", "forecast", "uv"})
# The free plan has no UV index
FREE_CAPABILITIES = frozenset({"current", "forecast"})
# The free forecast's steps, and how many make the hourly forecast's 24 hours
FREE_STEP_HOURS = 3
FREE_HOURLY_STEPS = 24 // FREE_STEP_HOURS
TIMEOUT_SECONDS = 20
FORECAST_DAYS = 5
# Keep an answer at least this long: at most 144 calls a day, well inside the free 1,000
MIN_CACHE_SECONDS = 600
# Never more calls than this in a UTC day (OpenWeather's free calls are counted per UTC day)
DAILY_CALL_LIMIT = 900
# After the key is refused, wait this long before trying it again (a new key can take a while to work)
REFUSED_KEY_WAIT_SECONDS = 600
# After "too many requests", wait this long
TOO_MANY_WAIT_SECONDS = 3600

HPA_TO_INHG = 0.02952998
METRES_PER_MILE = 1609.344
MM_PER_INCH = 25.4

# (service address, latitude, longitude) -> {"expires": unix time, "raw": decoded JSON}
_cache: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
# No requests before this time (after a refused key or too many requests)
_blocked_until = 0.0
_blocked_reason = ""
# Calls made today: {"day": "YYYY-MM-DD" (UTC), "calls": count}
_calls: Dict[str, Any] = {"day": "", "calls": 0}
# After HTTP 410 (the API is gone), wait this long before asking again
GONE_WAIT_SECONDS = 24 * 3600
# What the last answer said about One Call 3.0 going away: "" when nothing
_retirement = {"notice": ""}


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


def _header_date(value: Any) -> Optional[datetime]:
    """A date from a Sunset header (an HTTP date) or a Deprecation header ("@<unix seconds>", or an
    HTTP date in older drafts)."""
    if not isinstance(value, str) or not value.strip():
        return None
    value = value.strip()
    if value.startswith("@"):
        try:
            return datetime.fromtimestamp(int(value[1:]), timezone.utc)
        except (ValueError, OverflowError, OSError):
            return None
    try:
        moment = email.utils.parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def check_retirement(headers: Any) -> str:
    """
    Note what an answer's headers say about One Call 3.0 going away (Deprecation and Sunset), and
    return the notice: "" when they say nothing.
    """
    get = getattr(headers, "get", None)
    if get is None:
        return _retirement["notice"]
    deprecation, sunset = get("Deprecation"), get("Sunset")
    if not deprecation and not sunset:
        _retirement["notice"] = ""
        return ""
    end = _header_date(sunset)
    when = f" and stops answering on {end.date().isoformat()}" if end else ""
    _retirement["notice"] = (f"OpenWeatherMap says its One Call API 3.0 is being retired{when}. Outpost will need "
                             "an update to keep using OpenWeatherMap; until then, set OUTPOST_PROVIDER to another "
                             "provider if it stops working.")
    return _retirement["notice"]


def retirement_notice() -> str:
    """What OpenWeatherMap's last answer said about One Call 3.0 going away, or ""."""
    return _retirement["notice"]


def fetch_raw(latitude: float, longitude: float, api_key: str, user_agent: str) -> Dict[str, Any]:
    """The One Call JSON, kept for at least MIN_CACHE_SECONDS."""
    return _request(API_URL, {"exclude": "minutely"}, latitude, longitude, api_key, user_agent)


def _request(address: str, extra: Dict[str, str], latitude: float, longitude: float, api_key: str,
             user_agent: str) -> Dict[str, Any]:
    """One service's JSON for a place, kept for at least MIN_CACHE_SECONDS."""
    global _blocked_until, _blocked_reason

    if not api_key:
        raise RuntimeError("OpenWeatherMap needs an API key: set OUTPOST_OPENWEATHERMAP_API_KEY")

    onecall = address == API_URL
    place = (f"{latitude:.4f}", f"{longitude:.4f}")
    now = time.time()
    cached = _cache.get((address, *place))
    if cached and now < cached["expires"]:
        return cached["raw"]
    if now < _blocked_until:
        raise RuntimeError(_blocked_reason)
    if calls_today(now) >= DAILY_CALL_LIMIT:
        raise RuntimeError(f"OpenWeatherMap: {DAILY_CALL_LIMIT} calls made today, the most Outpost makes in a day "
                           "(it resets at midnight UTC)")

    params = {"lat": place[0], "lon": place[1], "units": "imperial", **extra, "appid": api_key}
    # Never log or show this address: it has the key in it
    url = f"{address}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept": "application/json"})
    if _calls["day"] != _today(now):
        _calls.update({"day": _today(now), "calls": 0})
    _calls["calls"] += 1
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            if onecall:
                check_retirement(response.headers)
            raw = json.load(response)
    except urllib.error.HTTPError as error:
        # Only the status goes in messages: the error also holds the address, with the key
        if onecall:
            check_retirement(error.headers)
        if error.code == 410:
            service = "One Call API 3.0" if onecall else "free weather services"
            _blocked_until = now + GONE_WAIT_SECONDS
            _blocked_reason = (f"OpenWeatherMap no longer offers its {service} (HTTP 410 Gone). Outpost needs an "
                               "update to use OpenWeatherMap; until then, set OUTPOST_PROVIDER to another provider")
            raise RuntimeError(_blocked_reason) from None
        if error.code == 401:
            hint = ("that it has a One Call by Call subscription, or set OUTPOST_OPENWEATHERMAP_PLAN=free to use the "
                    "free services" if onecall else "a new key can take up to 2 hours to start working")
            _blocked_until = now + REFUSED_KEY_WAIT_SECONDS
            _blocked_reason = (f"OpenWeatherMap refused the API key (check OUTPOST_OPENWEATHERMAP_API_KEY, and {hint}); "
                               f"trying again in {REFUSED_KEY_WAIT_SECONDS // 60} minutes")
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
    _cache[(address, *place)] = {"expires": now + MIN_CACHE_SECONDS, "raw": raw}
    return raw


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
    numbers = [_number(value) for value in amounts]
    given = [value for value in numbers if value is not None]
    return sum(given) / MM_PER_INCH if given else None


def _hour_amount(block: Any) -> Any:
    """The "1h" amount of an hour's rain or snow block."""
    return block.get("1h") if isinstance(block, dict) else None


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
            "precipitation": hours.amount(_inches(day.get("rain"), day.get("snow"))),
            "uv_index": round(uv) if uv is not None else None,
        })
        if len(forecast) == FORECAST_DAYS:
            break
    return forecast


def build_hourly(entries: Any, now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """The next hours (providers/hourly.py) from the hourly list."""
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
    Outpost's normalized format. Readings are unrounded, in °F, mph, inHg, miles, and inches; the
    updater converts them to OUTPOST_UNITS and rounds them (app/units.py).
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
    """Fetch (or reuse, for at least 10 minutes) and normalize the forecast for a location."""
    return normalize(fetch_raw(latitude, longitude, api_key, user_agent))


# ---------------------------------------------------------------- the free plan

# Day icons stand for a whole day
DAY_ICONS = {"clear-night": "sunny", "partly-cloudy-night": "partly-cloudy"}
# Which 3-hour step's condition stands for a day: the most significant one in daylight
ICON_WEIGHT = {name: rank for rank, name in enumerate((
    "unknown", "sunny", "partly-cloudy", "cloudy", "fog", "wind", "drizzle", "rain", "sleet", "snow", "storm"))}


def dew_point(temperature: Optional[float], humidity: Optional[float]) -> Optional[float]:
    """The dew point in °F from °F and relative humidity (Magnus formula), or None."""
    if temperature is None or humidity is None or not 0 < humidity <= 100:
        return None
    celsius = (temperature - 32) / 1.8
    gamma = math.log(humidity / 100) + 17.62 * celsius / (243.12 + celsius)
    return (243.12 * gamma / (17.62 - gamma)) * 1.8 + 32


def _part(block: Any, name: str) -> Dict[str, Any]:
    value = block.get(name) if isinstance(block, dict) else None
    return value if isinstance(value, dict) else {}


def build_free_current(raw: Dict[str, Any]) -> Dict[str, Any]:
    """The current block from /data/2.5/weather."""
    main, wind = _part(raw, "main"), _part(raw, "wind")
    condition, icon = describe(raw.get("weather"))
    temperature, humidity = _number(main.get("temp")), _number(main.get("humidity"))
    pressure = _number(main.get("pressure"))
    visibility = _number(raw.get("visibility"))
    return {
        "temperature": temperature,
        "feels_like": _number(main.get("feels_like")),
        "condition": condition,
        "icon": icon,
        "humidity": humidity,
        "wind_speed": _number(wind.get("speed")),
        "wind_gust": _number(wind.get("gust")),
        "wind_direction": _number(wind.get("deg")),
        "dew_point": dew_point(temperature, humidity),
        "observed_at": _iso(raw.get("dt")),
        "pressure": pressure * HPA_TO_INHG if pressure is not None else None,
        "uv_index": None,
        "visibility": visibility / METRES_PER_MILE if visibility is not None else None,
    }


def _step_amount(step: Dict[str, Any]) -> Optional[float]:
    """A 3-hour step's rain and snow, in inches (0 when neither is given)."""
    amount = _inches(_part(step, "rain").get("3h"), _part(step, "snow").get("3h"))
    return amount if amount is not None else 0.0


def _free_zone(raw: Dict[str, Any]) -> tzinfo:
    offset = _number(_part(raw, "city").get("timezone"))
    return timezone(timedelta(seconds=offset)) if offset is not None else timezone.utc


def build_free_forecast(raw: Dict[str, Any], current: Optional[Dict[str, Any]] = None,
                        now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """
    Days from the 3-hour steps, by local day: the highest and lowest temperature, the highest chance,
    the rain and snow added up, and the most significant daylight condition. Today starts from now,
    and its high and low include the temperature now.
    """
    zone = _free_zone(raw)
    steps = raw.get("list") if isinstance(raw.get("list"), list) else []
    days: Dict[str, List[Tuple[datetime, Dict[str, Any]]]] = {}
    for step in steps:
        start = _time(step.get("dt")) if isinstance(step, dict) else None
        if start is not None:
            days.setdefault(start.astimezone(zone).date().isoformat(), []).append((start.astimezone(zone), step))
    today = (now or datetime.now(timezone.utc)).astimezone(zone).date().isoformat()
    now_temperature = _number((current or {}).get("temperature"))
    forecast: List[Dict[str, Any]] = []
    for day in sorted(days):
        if day < today:
            continue
        entries = days[day]
        highs = [_number(_part(step, "main").get("temp_max")) for _, step in entries]
        lows = [_number(_part(step, "main").get("temp_min")) for _, step in entries]
        if day == today and now_temperature is not None:
            highs.append(now_temperature)
            lows.append(now_temperature)
        highs = [value for value in highs if value is not None]
        lows = [value for value in lows if value is not None]
        chances = [value for value in (_percent(step.get("pop")) for _, step in entries) if value is not None]
        daylight = [step for moment, step in entries if 6 <= moment.hour < 18] or [step for _, step in entries]
        conditions = [describe(step.get("weather")) for step in daylight]
        condition, icon = max(conditions, key=lambda pair: ICON_WEIGHT.get(DAY_ICONS.get(pair[1], pair[1]), 0))
        forecast.append({
            "day": day,
            "high": max(highs) if highs else None,
            "low": min(lows) if lows else None,
            "condition": condition,
            "icon": DAY_ICONS.get(icon, icon),
            "precipitation_chance": max(chances) if chances else None,
            "precipitation": sum(_step_amount(step) for _, step in entries),
            "uv_index": None,
        })
        if len(forecast) == FORECAST_DAYS:
            break
    return forecast


def build_free_hourly(raw: Dict[str, Any], now: Optional[datetime] = None) -> List[Dict[str, Any]]:
    """The next 24 hours as 3-hour steps, from the one under way (`time` to `end`)."""
    result = []
    for step in raw.get("list") if isinstance(raw.get("list"), list) else []:
        start = _time(step.get("dt")) if isinstance(step, dict) else None
        if start is None:
            continue
        condition, icon = describe(step.get("weather"))
        chance = _number(step.get("pop"))
        wind = _part(step, "wind")
        result.append(hours.entry(start, _number(_part(step, "main").get("temp")), condition, icon,
                                  chance * 100 if chance is not None else None,
                                  _number(wind.get("speed")), _number(wind.get("deg")), _step_amount(step),
                                  end=start + timedelta(hours=FREE_STEP_HOURS)))
    return hours.upcoming(result, now, FREE_HOURLY_STEPS)


def normalize_free(weather: Dict[str, Any], forecast: Dict[str, Any], now: Optional[datetime] = None) -> Dict[str, Any]:
    """Outpost's normalized format from the free services (see normalize). No time zone name is given."""
    weather = weather if isinstance(weather, dict) else {}
    forecast = forecast if isinstance(forecast, dict) else {}
    if not isinstance(weather.get("main"), dict) or not isinstance(forecast.get("list"), list) or not forecast["list"]:
        raise RuntimeError("OpenWeatherMap response is missing current or forecast data")
    current = build_free_current(weather)
    return {
        "source": SOURCE,
        "current": current,
        "forecast": build_free_forecast(forecast, current, now),
        "hourly": build_free_hourly(forecast, now),
        "timezone": None,
        "alerts": [],
    }


def fetch_free(latitude: float, longitude: float, api_key: str, user_agent: str) -> Dict[str, Any]:
    """The free plan: current weather and the 3-hour forecast (two calls, each kept 10 minutes)."""
    weather = _request(FREE_WEATHER_URL, {}, latitude, longitude, api_key, user_agent)
    forecast = _request(FREE_FORECAST_URL, {}, latitude, longitude, api_key, user_agent)
    return normalize_free(weather, forecast)


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


def build_alerts(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Outpost's alert format, most serious first. Repeats of the same alert are dropped."""
    alerts: List[Dict[str, Any]] = []
    seen = set()
    for alert in (raw if isinstance(raw, dict) else {}).get("alerts") or []:
        if not isinstance(alert, dict):
            continue
        title = _text(alert.get("event")) or "Weather alert"
        description = _text(alert.get("description"))
        expires = _iso(alert.get("end"))
        key = (title.lower(), expires, description.lower())
        if key in seen:
            continue
        seen.add(key)
        alerts.append({
            "title": title,
            "description": description,
            "severity": severity(title),
            "onset": _iso(alert.get("start")),
            "expires": expires,
            "uri": None,
        })
    alerts.sort(key=lambda a: SEVERITY_ORDER[a["severity"]])
    return alerts[:MAX_ALERTS]


def fetch_alerts(latitude: float, longitude: float, api_key: str, user_agent: str) -> List[Dict[str, Any]]:
    """
    The location's alerts. They come with the forecast, so when the weather is from OpenWeatherMap
    too this reuses the same response (no extra call).
    """
    return build_alerts(fetch_raw(latitude, longitude, api_key, user_agent))
