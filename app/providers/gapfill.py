"""
Fill values one provider doesn't publish using a second provider.

Used by OUTPOST_PROVIDER=auto: the National Weather Service is the primary
source, and anything it leaves empty (UV index, or readings from a station
that was missing data) is taken from Open-Meteo. Existing values are never
overwritten, and the condition text, icons, and alerts always stay with the
primary provider.
"""

import copy
from typing import Any, Dict, List, Tuple

CURRENT_FIELDS = [
    "humidity_percent",
    "wind_mph",
    "pressure_inhg",
    "uv_index",
    "visibility_miles",
]

# high_f/low_f can be empty for "today" once NWS has dropped the daytime period
FORECAST_FIELDS = ["uv_index", "high_f", "low_f"]


def has_gaps(data: Dict[str, Any]) -> bool:
    """True if the primary data is missing any value this module can fill."""
    current = data.get("current") or {}
    if any(current.get(field) is None for field in CURRENT_FIELDS):
        return True
    return any(
        day.get(field) is None
        for day in data.get("forecast") or []
        for field in FORECAST_FIELDS
    )


def fill(primary: Dict[str, Any], secondary: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Return (merged copy of primary, sorted list of filled field names such as
    'current.uv_index' or 'forecast.high_f').
    """
    merged = copy.deepcopy(primary)
    filled = set()

    current = merged.setdefault("current", {})
    backup_current = secondary.get("current") or {}
    for field in CURRENT_FIELDS:
        if current.get(field) is None and backup_current.get(field) is not None:
            current[field] = backup_current[field]
            filled.add(f"current.{field}")

    backup_days = {day.get("day"): day for day in secondary.get("forecast") or []}
    for day in merged.get("forecast") or []:
        backup = backup_days.get(day.get("day"))
        if not backup:
            continue
        for field in FORECAST_FIELDS:
            if day.get(field) is None and backup.get(field) is not None:
                day[field] = backup[field]
                filled.add(f"forecast.{field}")

    return merged, sorted(filled)
