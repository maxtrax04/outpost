"""
The hourly forecast (weather.json "hourly", docs/data-format.md): the next HOURS hours, starting
with the hour that is under way, one entry per hour (or per step, for a source with longer steps), in
the same form from every provider. Each entry has its start (`time`) and its `end`.

Uses only the Python standard library.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional

HOURS = 24
# Compass points, as the National Weather Service writes wind directions, in degrees
COMPASS = {name: index * 22.5 for index, name in enumerate(
    ("N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"))}


def number(value: Any) -> Optional[float]:
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value == value else None


def amount(value: Any) -> Optional[float]:
    """A precipitation amount in inches, never below 0, or None."""
    value = number(value)
    return max(0.0, value) if value is not None else None


def entry(moment: datetime, temperature: Any, condition: str, icon: str, precipitation_chance: Any = None,
          wind_speed: Any = None, wind_direction: Any = None, precipitation: Any = None,
          end: Optional[datetime] = None) -> Dict[str, Any]:
    """One hour (or one step from `moment` to `end`, an hour later by default). Readings are unrounded,
    in °F, mph, and inches (the rain or snow expected in the step, as water), like the rest of a
    provider's data."""
    chance = number(precipitation_chance)
    end = end if end is not None and end > moment else moment + timedelta(hours=1)
    return {
        "time": moment.astimezone(timezone.utc).isoformat(),
        "end": end.astimezone(timezone.utc).isoformat(),
        "temperature": number(temperature),
        "condition": condition,
        "icon": icon,
        "precipitation_chance": round(min(100.0, max(0.0, chance))) if chance is not None else None,
        "precipitation": amount(precipitation),
        "wind_speed": number(wind_speed),
        "wind_direction": number(wind_direction),
    }


def upcoming(entries: Iterable[Dict[str, Any]], now: Optional[datetime] = None,
             hours: int = HOURS) -> List[Dict[str, Any]]:
    """The hours (or steps) that haven't ended yet, in order, at most `hours` of them."""
    now = now or datetime.now(timezone.utc)
    timed = []
    for item in entries:
        try:
            start = datetime.fromisoformat(item["time"])
        except (KeyError, TypeError, ValueError):
            continue
        try:
            end = datetime.fromisoformat(item["end"])
        except (KeyError, TypeError, ValueError):
            end = start + timedelta(hours=1)
        if start.tzinfo is not None and end.tzinfo is not None and end > now:
            timed.append((start, item))
    timed.sort(key=lambda pair: pair[0])
    seen, result = set(), []
    for start, item in timed:
        if start not in seen:
            seen.add(start)
            result.append(item)
    return result[:hours]
