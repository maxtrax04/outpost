#!/usr/bin/env python3
"""
Outpost health check.

Exit 0 when /data/weather.json exists, is valid, has the expected fields,
and was generated recently (so a dead updater is detected).
Exit 1 otherwise.
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

DATA_PATH = Path("/data/weather.json")

UPDATE_INTERVAL = int(os.getenv("OUTPOST_UPDATE_INTERVAL", "60"))
MAX_AGE_SECONDS = max(300, UPDATE_INTERVAL * 5)

REQUIRED_TOP_LEVEL = [
    "status",
    "provider",
    "location",
    "generated_at",
    "current",
    "forecast",
]


def main() -> int:
    if not DATA_PATH.exists():
        print("weather.json does not exist")
        return 1

    try:
        with open(DATA_PATH, "r", encoding="utf-8") as file:
            payload = json.load(file)
    except Exception as error:
        print(f"weather.json is not valid JSON: {error}")
        return 1

    missing = [key for key in REQUIRED_TOP_LEVEL if key not in payload]
    if missing:
        print(f"weather.json is missing fields: {', '.join(missing)}")
        return 1

    if not isinstance(payload["current"], dict):
        print("'current' is not an object")
        return 1

    if not isinstance(payload["forecast"], list):
        print("'forecast' is not a list")
        return 1

    try:
        generated = datetime.fromisoformat(payload["generated_at"])
        age = (datetime.now(timezone.utc) - generated).total_seconds()
    except Exception as error:
        print(f"generated_at is not a valid timestamp: {error}")
        return 1

    if age > MAX_AGE_SECONDS:
        print(f"weather.json is stale ({int(age)}s old, limit {MAX_AGE_SECONDS}s)")
        return 1

    print("Outpost healthy")
    return 0


if __name__ == "__main__":
    sys.exit(main())
