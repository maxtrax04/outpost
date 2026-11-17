"""
Searching for places by name, for the dashboard's location search (/api/places, docs/api-design.md).

Docs:  https://open-meteo.com/en/docs/geocoding-api
Terms: the same as Open-Meteo's weather: free for non-commercial use, no API key, credited in the
       dashboard's footer. Searches are cached for a day, and at most one a second is sent.

The search text goes to Open-Meteo; it is never logged.

Uses only the Python standard library.
"""

import collections
import copy
import json
import math
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List

API_URL = "https://geocoding-api.open-meteo.com/v1/search"
SOURCE = {"id": "openmeteo", "name": "Open-Meteo.com"}
TIMEOUT_SECONDS = 10
MAX_RESULTS = 8
# Search text, after tidying: shorter finds nothing useful, longer is not a place name
MIN_QUERY_LENGTH = 2
MAX_QUERY_LENGTH = 100
CACHE_SECONDS = 24 * 3600
MAX_CACHED = 500
# At most one search a second goes to Open-Meteo (the others wait their turn)
MIN_GAP_SECONDS = 1.0

# casefolded query -> (expires, places), least recently used first
_cache: "collections.OrderedDict[str, tuple]" = collections.OrderedDict()
_lock = threading.Lock()
_last_request = [0.0]


def clean_query(text: str) -> str:
    """The search text on one line, with runs of spaces made one."""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text or "")
    return re.sub(r"\s+", " ", text).strip()


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _number(value: Any, limit: float):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    value = float(value)
    return value if math.isfinite(value) and abs(value) <= limit else None


def parse(raw: Any) -> List[Dict[str, Any]]:
    """The usable places in a geocoding answer, at most MAX_RESULTS."""
    results = raw.get("results") if isinstance(raw, dict) else None
    places = []
    for result in results if isinstance(results, list) else []:
        if not isinstance(result, dict):
            continue
        name = _text(result.get("name"))
        latitude = _number(result.get("latitude"), 90)
        longitude = _number(result.get("longitude"), 180)
        if not name or latitude is None or longitude is None:
            continue
        places.append({
            "name": name,
            "region": _text(result.get("admin1")),
            "country": _text(result.get("country")),
            "latitude": latitude,
            "longitude": longitude,
            "timezone": _text(result.get("timezone")),
        })
        if len(places) == MAX_RESULTS:
            break
    return places


def _request(query: str, user_agent: str) -> Any:
    params = {"name": query, "count": MAX_RESULTS, "language": "en", "format": "json"}
    request = urllib.request.Request(f"{API_URL}?{urllib.parse.urlencode(params)}",
                                     headers={"User-Agent": user_agent})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"place search failed: HTTP {error.code}") from None
    except (urllib.error.URLError, OSError, ValueError) as error:
        # The message never includes the search text
        raise RuntimeError(f"place search failed: {type(error).__name__}") from None


def search(query: str, user_agent: str, clock: Callable[[], float] = time.time,
           sleep: Callable[[float], None] = time.sleep) -> List[Dict[str, Any]]:
    """Places matching query (already tidied by clean_query). Raises RuntimeError when the search fails."""
    key = query.casefold()
    with _lock:
        now = clock()
        cached = _cache.get(key)
        if cached and now < cached[0]:
            _cache.move_to_end(key)
            return copy.deepcopy(cached[1])

        wait = _last_request[0] + MIN_GAP_SECONDS - now
        if wait > 0:
            sleep(wait)
        _last_request[0] = clock()
        places = parse(_request(query, user_agent))

        _cache[key] = (clock() + CACHE_SECONDS, places)
        _cache.move_to_end(key)
        while len(_cache) > MAX_CACHED:
            _cache.popitem(last=False)
        return copy.deepcopy(places)
