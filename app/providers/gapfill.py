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
    "humidity",
    "dew_point",
    "wind_speed",
    "pressure",
    "uv_index",
    "visibility",
]

# high/low can be empty for "today" once NWS has dropped the daytime period; NWS has no precipitation amounts
FORECAST_FIELDS = ["uv_index", "high", "low", "precipitation"]

# Matched by the hour's start time
HOURLY_FIELDS = ["precipitation"]


def has_gaps(data: Dict[str, Any]) -> bool:
    """True if the primary data is missing any value this module can fill."""
    current = data.get("current") or {}
    if any(current.get(field) is None for field in CURRENT_FIELDS):
        return True
    if any(day.get(field) is None for day in data.get("forecast") or [] for field in FORECAST_FIELDS):
        return True
    return any(hour.get(field) is None for hour in data.get("hourly") or [] for field in HOURLY_FIELDS)


def fill(primary: Dict[str, Any], secondary: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """
    Return (merged copy of primary, sorted list of filled field names such as
    'current.uv_index', 'forecast.high', or 'hourly.precipitation').
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

    backup_hours = {hour.get("time"): hour for hour in secondary.get("hourly") or []}
    for hour in merged.get("hourly") or []:
        backup = backup_hours.get(hour.get("time"))
        if not backup:
            continue
        for field in HOURLY_FIELDS:
            if hour.get(field) is None and backup.get(field) is not None:
                hour[field] = backup[field]
                filled.add(f"hourly.{field}")

    return merged, sorted(filled)
