"""
The hourly forecast (weather.json "hourly", docs/data-format.md): the next HOURS hours, starting
with the hour that is under way, one entry per hour, in the same form from every provider.

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


def entry(moment: datetime, temperature: Any, condition: str, icon: str, precipitation_chance: Any = None,
          wind_speed: Any = None, wind_direction: Any = None) -> Dict[str, Any]:
    """One hour. Readings are unrounded, in °F and mph, like the rest of a provider's data."""
    chance = number(precipitation_chance)
    return {
        "time": moment.astimezone(timezone.utc).isoformat(),
        "temperature": number(temperature),
        "condition": condition,
        "icon": icon,
        "precipitation_chance": round(min(100.0, max(0.0, chance))) if chance is not None else None,
        "wind_speed": number(wind_speed),
        "wind_direction": number(wind_direction),
    }


def upcoming(entries: Iterable[Dict[str, Any]], now: Optional[datetime] = None,
             hours: int = HOURS) -> List[Dict[str, Any]]:
    """The hours that haven't ended yet, in order, at most `hours` of them."""
    now = now or datetime.now(timezone.utc)
    timed = []
    for item in entries:
        try:
            start = datetime.fromisoformat(item["time"])
        except (KeyError, TypeError, ValueError):
            continue
        if start.tzinfo is not None and start + timedelta(hours=1) > now:
            timed.append((start, item))
    timed.sort(key=lambda pair: pair[0])
    seen, result = set(), []
    for start, item in timed:
        if start not in seen:
            seen.add(start)
            result.append(item)
    return result[:hours]
