"""
Unit systems for weather.json (OUTPOST_UNITS).

Providers return readings unrounded in one set of units (°F, mph, inHg, miles, inches of
precipitation). This module
converts them to the chosen system and rounds them, once, just before weather.json is written,
so the numbers are never rounded twice.

Uses only the Python standard library.
"""

import copy
from typing import Any, Callable, Dict, Optional

SYSTEMS = ("imperial", "metric")
DEFAULT_SYSTEM = "imperial"

# The label shown for each kind of reading (the "units" block of weather.json)
LABELS = {
    "imperial": {"temperature": "°F", "speed": "mph", "pressure": "inHg", "distance": "mi", "precipitation": "in"},
    "metric": {"temperature": "°C", "speed": "km/h", "pressure": "hPa", "distance": "km", "precipitation": "mm"},
}

KM_PER_MILE = 1.609344
MM_PER_INCH = 25.4
HPA_PER_INHG = 33.8638866667

# From the providers' units (imperial) to each system
CONVERT: Dict[str, Dict[str, Callable[[float], float]]] = {
    "imperial": {
        "temperature": lambda f: f,
        "speed": lambda mph: mph,
        "pressure": lambda inhg: inhg,
        "distance": lambda miles: miles,
        "precipitation": lambda inches: inches,
    },
    "metric": {
        "temperature": lambda f: (f - 32) * 5 / 9,
        "speed": lambda mph: mph * KM_PER_MILE,
        "pressure": lambda inhg: inhg * HPA_PER_INHG,
        "distance": lambda miles: miles * KM_PER_MILE,
        "precipitation": lambda inches: inches * MM_PER_INCH,
    },
}

# Decimal places shown for each kind of reading
DIGITS = {
    "imperial": {"temperature": 0, "speed": 0, "pressure": 2, "distance": 1, "precipitation": 2},
    "metric": {"temperature": 0, "speed": 0, "pressure": 0, "distance": 1, "precipitation": 1},
}

# Which kind of reading each field is
CURRENT_FIELDS = {
    "temperature": "temperature",
    "feels_like": "temperature",
    "dew_point": "temperature",
    "wind_speed": "speed",
    "wind_gust": "speed",
    "pressure": "pressure",
    "visibility": "distance",
}
FORECAST_FIELDS = {
    "high": "temperature",
    "low": "temperature",
    "precipitation": "precipitation",
}
HOURLY_FIELDS = {
    "temperature": "temperature",
    "wind_speed": "speed",
    "precipitation": "precipitation",
}


def block(system: str) -> Dict[str, str]:
    """The "units" block of weather.json."""
    return {"system": system, **LABELS[system]}


def convert(value: Any, kind: str, system: str) -> Optional[float]:
    """One reading in the given system, rounded for display. Anything that is not a number becomes None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    digits = DIGITS[system][kind]
    result = round(CONVERT[system][kind](value), digits)
    if digits == 0:
        return int(result)
    # 0.0 rather than -0.0
    return result + 0.0


def direction(value: Any) -> Optional[int]:
    """A compass direction in whole degrees, 0 to 359 (360 is north, so 0). Anything else becomes None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return None
    return int(round(value)) % 360


# Readings without a unit, always whole numbers: percentages and the UV index
WHOLE_FIELDS = {
    "current": ("humidity", "uv_index"),
    "forecast": ("precipitation_chance", "uv_index"),
    "hourly": ("precipitation_chance",),
}
PERCENT_FIELDS = {"humidity", "precipitation_chance"}


def whole(value: Any, percent: bool = False) -> Optional[int]:
    """A whole number (a percentage is kept within 0 to 100, a UV index not below 0), or None."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value:
        return None
    return int(round(min(100.0, max(0.0, value)) if percent else max(0.0, value)))


def _whole_fields(entries: Any, names: Any) -> None:
    for entry in entries:
        for name in names:
            if isinstance(entry, dict) and name in entry:
                entry[name] = whole(entry[name], name in PERCENT_FIELDS)


def present(data: Dict[str, Any], system: str) -> Dict[str, Any]:
    """A copy of normalized provider data with every reading in `system`, rounded."""
    result = copy.deepcopy(data)
    _whole_fields([result.get("current") or {}], WHOLE_FIELDS["current"])
    _whole_fields(result.get("forecast") or [], WHOLE_FIELDS["forecast"])
    _whole_fields(result.get("hourly") or [], WHOLE_FIELDS["hourly"])
    current = result.get("current") or {}
    for field, kind in CURRENT_FIELDS.items():
        if field in current:
            current[field] = convert(current[field], kind, system)
    if "wind_direction" in current:
        # Calm has no direction (NWS reports calm as 0°, which would point an arrow north)
        calm = current.get("wind_speed") == 0
        current["wind_direction"] = None if calm else direction(current["wind_direction"])
    for day in result.get("forecast") or []:
        for field, kind in FORECAST_FIELDS.items():
            if field in day:
                day[field] = convert(day[field], kind, system)
    for hour in result.get("hourly") or []:
        for field, kind in HOURLY_FIELDS.items():
            if field in hour:
                hour[field] = convert(hour[field], kind, system)
        if "wind_direction" in hour:
            hour["wind_direction"] = None if hour.get("wind_speed") == 0 else direction(hour["wind_direction"])
    return result
