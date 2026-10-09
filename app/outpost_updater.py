#!/usr/bin/env python3
"""
Outpost updater - Phase 1

Purpose:
- Validate Docker build
- Validate Docker Compose startup
- Validate volume writes
- Validate Nginx can serve generated JSON
- Validate browser dashboard can consume normalized JSON

Phase 1 Provider:
- mock

Future Providers:
- openmeteo
- pirateweather
- metno
- openweathermap
"""

import argparse
import json
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from providers import openmeteo

DATA_PATH = Path("/data/weather.json")

def get_env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Get environment variable or return default."""
    value = os.getenv(name, default)
    if value is None:
        raise ValueError(f"Environment variable {name} is not set and no default provided.")
    return value

def get_int_env(name: str, default: Optional[int] = None) -> Optional[int]:
    """Get environment variable as int or return default."""
    value = os.getenv(name)
    if value is None:
        if default is not None:
            return default
        raise ValueError(f"Environment variable {name} is not set and no default provided.")
    try:
        return int(value)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be an integer, got '{value}'.") 
    
def get_float_env(name: str, default: Optional[float] = None) -> Optional[float]:
    """Get environment variable as float or return default."""
    value = os.getenv(name)
    if value is None:
        if default is not None:
            return default
        raise ValueError(f"Environment variable {name} is not set and no default provided.")
    try:
        return float(value)
    except ValueError:
        raise ValueError(f"Environment variable {name} must be a float, got '{value}'.")

APP_NAME = "Outpost"
APP_VERSION = "0.1.0"

PROVIDER = get_env("OUTPOST_PROVIDER", "mock").lower()
UPDATE_INTERVAL = get_int_env("OUTPOST_UPDATE_INTERVAL", 60)

LOCATION_NAME = get_env("OUTPOST_LOCATION_NAME", "Goodsprings, NV")
LATITUDE = get_float_env("OUTPOST_LATITUDE", 35.8319)
LONGITUDE = get_float_env("OUTPOST_LONGITUDE", -115.4328)
UNITS = get_env("OUTPOST_UNITS", "imperial").lower()
USER_AGENT = get_env("OUTPOST_USER_AGENT", "Outpost/0.1.0")

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def write_json(payload: Dict[str, Any]) -> None:
    DATA_PATH.parent.mkdir(parents=True, exist_ok=True)

    temp_path = DATA_PATH.with_suffix(".json.tmp")

    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)

    temp_path.replace(DATA_PATH)

def build_mock_payload() -> Dict[str, Any]:
    """
    Build predictable-but-changing mock data.

    This intentionally looks weather-like so the dashboard can be tested,
    but it does not call any external weather service.
    """

    now = datetime.now(timezone.utc)

    base_temp = random.randint(65, 85)
    feels_like = base_temp + random.randint(-2, 6)

    condition_options = [
        ("Clear sky", "sunny"),
        ("Partly cloudy", "partly-cloudy"),
        ("Cloudy", "cloudy"),
        ("Fog", "fog"),
        ("Drizzle", "drizzle"),
        ("Light rain", "rain"),
        ("Snow", "snow"),
        ("Thunderstorm watch", "storm")
    ]

    current_condition, current_icon = random.choice(condition_options)

    forecast = []

    for offset in range(5):
        day = now + timedelta(days=offset)
        high = base_temp + random.randint(0, 12)
        low = base_temp - random.randint(5, 16)
        condition, icon = random.choice(condition_options)

        forecast.append({
            "day": day.date().isoformat(),
            "high_f": high,
            "low_f": low,
            "condition": condition,
            "icon": icon,
            "precipitation_percent": random.randint(0, 60),
            "uv_index": random.randint(0,8)
        })
    
    alerts = []

    if current_condition == "Thunderstorm watch":
        alerts.append({
            "title": "Outpost Test Alert",
            "description": "Mock alert generated for dashboard validation.",
            "severity": "test",
            "uri": None
        })
    
    return {
        "status": "ok",
        "app": APP_NAME,
        "version": APP_VERSION,
        "provider": "mock",
        "source": "Outpost Mock Provider",
        "location": LOCATION_NAME,
        "generated_at": utc_now(),
        "coordinates": {
            "latitude": LATITUDE,
            "longitude": LONGITUDE
        },
        "units": UNITS,
        "update_interval_seconds": UPDATE_INTERVAL,
        "current": {
            "temperature_f": base_temp,
            "feels_like_f": feels_like,
            "condition": current_condition,
            "icon": current_icon,
            "humidity_percent": random.randint(35, 85),
            "wind_mph": random.randint(0, 25),
            "pressure_inhg": round(random.uniform(29.70, 30.35), 2),
            "uv_index": random.randint(0, 8),
            "visibility_miles": random.randint(5, 10)
        },
        "forecast": forecast,
        "alerts": alerts,
        "last_error": None
    }

def build_error_payload(error_message: str) -> Dict[str, Any]:
    return {
        "status": "error",
        "app": APP_NAME,
        "version": APP_VERSION,
        "provider": PROVIDER,
        "source": None,
        "location": LOCATION_NAME,
        "generated_at": utc_now(),
        "coordinates": {
            "latitude": LATITUDE,
            "longitude": LONGITUDE
        },
        "units": UNITS,
        "update_interval_seconds": UPDATE_INTERVAL,
        "current": {
            "temperature_f": None,
            "feels_like_f": None,
            "condition": "DATA LINK LOST",
            "icon": "unknown",
            "humidity_percent": None,
            "wind_mph": None,
            "pressure_inhg": None,
            "uv_index": None,
            "visibility_miles": None
        },
        "forecast": [],
        "alerts": [],
        "last_error": error_message
    }

def build_live_payload(provider_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap normalized provider data with Outpost metadata."""
    return {
        "status": "ok",
        "app": APP_NAME,
        "version": APP_VERSION,
        "provider": provider_name,
        "source": data.get("source"),
        "location": LOCATION_NAME,
        "generated_at": utc_now(),
        "coordinates": {
            "latitude": LATITUDE,
            "longitude": LONGITUDE
        },
        "units": UNITS,
        "update_interval_seconds": UPDATE_INTERVAL,
        "current": data["current"],
        "forecast": data["forecast"],
        "alerts": data.get("alerts", []),
        "last_error": None
    }

def write_degraded_or_error(error_message: str) -> None:
    """
    On a failed update, keep showing the last good data (marked degraded)
    when it is for the same provider and location. Otherwise write an
    error payload. generated_at is left alone so the data visibly ages.
    """
    try:
        with DATA_PATH.open("r", encoding="utf-8") as file:
            previous = json.load(file)

        has_data = previous.get("current", {}).get("temperature_f") is not None
        same_setup = (
            previous.get("provider") == PROVIDER
            and previous.get("location") == LOCATION_NAME
        )

        if has_data and same_setup:
            previous["status"] = "degraded"
            previous["last_error"] = error_message
            previous["update_interval_seconds"] = UPDATE_INTERVAL
            write_json(previous)
            return
    except Exception:
        pass

    write_json(build_error_payload(error_message=error_message))

def update_once() -> None:
    try:
        print(f"[Outpost] Starting update. Provider={PROVIDER}", flush=True)

        if PROVIDER == "mock":
            payload = build_mock_payload()
        elif PROVIDER == "openmeteo":
            data = openmeteo.fetch(LATITUDE, LONGITUDE, USER_AGENT)
            payload = build_live_payload("openmeteo", data)
        else:
            raise RuntimeError(
                f"Provider '{PROVIDER}' is not implemented yet. Use OUTPOST_PROVIDER=mock or openmeteo."
            )

        write_json(payload)

        print(f"[Outpost] Update complete. Wrote {DATA_PATH}. Status={payload.get('status')}", flush=True)

    except Exception as error:
        error_message = str(error)

        print(
            f"[Outpost] Update failed: {error_message}",
            file=sys.stderr,
            flush=True
        )

        write_degraded_or_error(error_message)

def run_loop() -> None:
    print(f"[Outpost] Updater loop started. Interval={UPDATE_INTERVAL}s", flush=True)

    while True:
        update_once()
        time.sleep(UPDATE_INTERVAL)

def main() -> None:
    parser = argparse.ArgumentParser(description="Outpost updater")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Run continuously"
    )

    args = parser.parse_args()

    if args.loop:
        run_loop()
    else:
        update_once()

if __name__ == "__main__":
    main()