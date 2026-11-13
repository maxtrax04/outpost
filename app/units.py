"""
Unit systems for weather.json (OUTPOST_UNITS).

Providers return readings unrounded in one set of units (°F, mph, inHg, miles). This module
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
    "imperial": {"temperature": "°F", "speed": "mph", "pressure": "inHg", "distance": "mi"},
    "metric": {"temperature": "°C", "speed": "km/h", "pressure": "hPa", "distance": "km"},
}

KM_PER_MILE = 1.609344
HPA_PER_INHG = 33.8638866667

# From the providers' units (imperial) to each system
CONVERT: Dict[str, Dict[str, Callable[[float], float]]] = {
    "imperial": {
        "temperature": lambda f: f,
        "speed": lambda mph: mph,
        "pressure": lambda inhg: inhg,
        "distance": lambda miles: miles,
    },
    "metric": {
        "temperature": lambda f: (f - 32) * 5 / 9,
        "speed": lambda mph: mph * KM_PER_MILE,
        "pressure": lambda inhg: inhg * HPA_PER_INHG,
        "distance": lambda miles: miles * KM_PER_MILE,
    },
}

# Decimal places shown for each kind of reading
DIGITS = {
    "imperial": {"temperature": 0, "speed": 0, "pressure": 2, "distance": 1},
    "metric": {"temperature": 0, "speed": 0, "pressure": 0, "distance": 1},
}

# Which kind of reading each field is
CURRENT_FIELDS = {
    "temperature": "temperature",
    "feels_like": "temperature",
    "wind_speed": "speed",
    "pressure": "pressure",
    "visibility": "distance",
}
FORECAST_FIELDS = {
    "high": "temperature",
    "low": "temperature",
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


def present(data: Dict[str, Any], system: str) -> Dict[str, Any]:
    """A copy of normalized provider data with every reading in `system`, rounded."""
    result = copy.deepcopy(data)
    current = result.get("current") or {}
    for field, kind in CURRENT_FIELDS.items():
        if field in current:
            current[field] = convert(current[field], kind, system)
    for day in result.get("forecast") or []:
        for field, kind in FORECAST_FIELDS.items():
            if field in day:
                day[field] = convert(day[field], kind, system)
    return result
