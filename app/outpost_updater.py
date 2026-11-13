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
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import units
from providers import gapfill, nws, openmeteo

DATA_PATH = Path("/data/weather.json")

# The weather.json format (docs/data-format.md). Raise it only for a change that breaks readers:
# a renamed or removed field, or a changed meaning. New fields do not change it.
SCHEMA_VERSION = 1

# Where editors find the JSON Schema for this format (written to weather.json as "$schema")
SCHEMA_URL = f"https://raw.githubusercontent.com/maxtrax04/outpost/main/docs/schema/weather-v{SCHEMA_VERSION}.json"

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
def read_version() -> str:
    """Version comes from the VERSION file (the single place to bump it)."""
    here = Path(__file__).resolve().parent
    for candidate in (here / "VERSION", here.parent / "VERSION"):
        try:
            version = candidate.read_text(encoding="utf-8").strip()
            if version:
                return version
        except OSError:
            continue
    return "dev"

APP_VERSION = read_version()

PROVIDER = get_env("OUTPOST_PROVIDER", "mock").lower()
UPDATE_INTERVAL = get_int_env("OUTPOST_UPDATE_INTERVAL", 60)

LOCATION_NAME = get_env("OUTPOST_LOCATION_NAME", "Goodsprings, NV")
LATITUDE = get_float_env("OUTPOST_LATITUDE", 35.8319)
LONGITUDE = get_float_env("OUTPOST_LONGITUDE", -115.4328)
def units_setting(value: Optional[str]) -> str:
    """OUTPOST_UNITS: imperial (default; °F, mph, inHg, miles) or metric (°C, km/h, hPa, km)."""
    value = (value or "").strip().lower()
    if not value:
        return units.DEFAULT_SYSTEM
    if value in units.SYSTEMS:
        return value
    print(f"[Outpost] Unknown OUTPOST_UNITS \"{value}\" (use imperial or metric); using imperial", file=sys.stderr, flush=True)
    return units.DEFAULT_SYSTEM

UNITS = units_setting(os.getenv("OUTPOST_UNITS"))

def units_block() -> Dict[str, str]:
    """The "units" block of weather.json: the unit system and the label for each kind of reading."""
    return units.block(UNITS)

def clean_header_text(name: str, value: str) -> str:
    """
    Text that goes into an HTTP header must be plain printable ASCII (no line breaks), and short.
    Anything else is ignored with a warning rather than sent to a weather service.
    """
    value = value.strip()
    if not value:
        return ""
    if len(value) > 120 or not all(32 <= ord(char) < 127 for char in value):
        print(
            f"[Outpost] {name} must be plain text, at most 120 characters, with no special characters; ignoring it",
            file=sys.stderr,
            flush=True
        )
        return ""
    return value

def build_user_agent(version: str, contact: str = "", override: str = "") -> str:
    """
    The User-Agent sent to weather services: "Outpost/<version> (<contact>)".
    OUTPOST_USER_AGENT, if set, replaces the whole thing.
    """
    if override:
        return override
    if contact:
        return f"Outpost/{version} ({contact})"
    return f"Outpost/{version}"

def load_contact_settings() -> Tuple[str, str]:
    """Returns (contact, user_agent) from OUTPOST_CONTACT and OUTPOST_USER_AGENT."""
    contact = clean_header_text("OUTPOST_CONTACT", os.getenv("OUTPOST_CONTACT", ""))
    override = clean_header_text("OUTPOST_USER_AGENT", os.getenv("OUTPOST_USER_AGENT", ""))
    return contact, build_user_agent(APP_VERSION, contact, override)

CONTACT, USER_AGENT = load_contact_settings()

DEFAULT_THEME = "retro-crt"
THEME = get_env("OUTPOST_THEME", DEFAULT_THEME).strip().lower()
THEMES_DIR = Path("/usr/share/nginx/html/themes")
# People mount their own themes here. nginx checks it first too (see nginx/default.conf).
CUSTOM_THEMES_DIR = Path("/config/themes")
# Community themes downloaded by outpost_community.py (OUTPOST_COMMUNITY_THEMES)
COMMUNITY_THEMES_DIR = Path("/data/community/themes")

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()

def write_json(payload: Dict[str, Any], path: Optional[Path] = None) -> None:
    path = path or DATA_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = path.with_suffix(".json.tmp")

    with temp_path.open("w", encoding="utf-8") as file:
        json.dump(payload, file, indent=2)

    temp_path.replace(path)

def build_dim_config() -> Dict[str, Any]:
    """Day/night dimming settings from the environment, with bad values replaced by defaults."""

    def warn(message: str) -> None:
        print(f"[Outpost] {message}", file=sys.stderr, flush=True)

    enabled = os.getenv("OUTPOST_AUTO_DIM", "true").strip().lower() not in ("0", "false", "no", "off")

    try:
        level = float(os.getenv("OUTPOST_DIM_LEVEL", "0.35"))
    except ValueError:
        warn("OUTPOST_DIM_LEVEL must be a number between 0.05 and 1; using 0.35")
        level = 0.35
    level = min(1.0, max(0.05, level))

    mode = os.getenv("OUTPOST_DIM_MODE", "sun").strip().lower()
    if mode not in ("sun", "schedule"):
        warn(f"OUTPOST_DIM_MODE must be 'sun' or 'schedule', got '{mode}'; using sun")
        mode = "sun"

    times = {}
    for name, default in (("OUTPOST_DIM_START", "22:00"), ("OUTPOST_DIM_END", "06:00")):
        value = os.getenv(name, default).strip()
        if not re.fullmatch(r"([01]?\d|2[0-3]):[0-5]\d", value):
            warn(f"{name} must look like HH:MM (24-hour), got '{value}'; using {default}")
            value = default
        times[name] = value

    return {
        "enabled": enabled,
        "level": level,
        "mode": mode,
        "start": times["OUTPOST_DIM_START"],
        "end": times["OUTPOST_DIM_END"],
    }

def env_flag(name: str, default: bool) -> bool:
    """True/false setting: 1, true, yes, or on (any case) mean true."""
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")

EFFECTS_VALUES = ("full", "reduced")

def effects_setting() -> str:
    """OUTPOST_EFFECTS: full (default) or reduced (no scanlines, glow, or animation for anyone)."""
    value = os.getenv("OUTPOST_EFFECTS", "").strip().lower()
    if not value:
        return "full"
    if value in EFFECTS_VALUES:
        return value
    print(f"[Outpost] Unknown OUTPOST_EFFECTS \"{value}\" (use full or reduced); using full", file=sys.stderr, flush=True)
    return "full"

CLOCK_VALUES = ("auto", "12", "24")
CLOCK_ALIASES = {"12h": "12", "24h": "24"}

def clock_setting() -> str:
    """OUTPOST_CLOCK: auto (default, each browser's language decides), 12, or 24."""
    value = os.getenv("OUTPOST_CLOCK", "").strip().lower()
    if not value:
        return "auto"
    value = CLOCK_ALIASES.get(value, value)
    if value in CLOCK_VALUES:
        return value
    print(f"[Outpost] Unknown OUTPOST_CLOCK \"{value}\" (use auto, 12, or 24); using auto", file=sys.stderr, flush=True)
    return "auto"

def build_ui_config() -> Dict[str, Any]:
    """Dashboard display settings from the environment."""
    subtitle = os.getenv("OUTPOST_SUBTITLE", "").strip()
    if len(subtitle) > 80:
        print("[Outpost] OUTPOST_SUBTITLE is longer than 80 characters; shortening it", file=sys.stderr, flush=True)
        subtitle = subtitle[:80].rstrip()

    return {
        "subtitle": subtitle,
        "alerts_always_show": env_flag("OUTPOST_ALERTS_ALWAYS_SHOW", False),
        "theme_switcher": env_flag("OUTPOST_THEME_SWITCHER", True),
        "effects": effects_setting(),
        "effects_toggle": env_flag("OUTPOST_EFFECTS_TOGGLE", True),
        "clock": clock_setting(),
        "clock_toggle": env_flag("OUTPOST_CLOCK_TOGGLE", True),
    }

THEME_FILE = "theme.css"
FOLDER_NAME_PATTERN = r"[a-z0-9-]+"
# A theme id is a folder name, or <username>/<theme> for a community theme (a theme folder inside
# a folder named after the person who made it)
THEME_NAME_PATTERN = rf"{FOLDER_NAME_PATTERN}(?:/{FOLDER_NAME_PATTERN})?"

def theme_dirs() -> List[Path]:
    """
    Where themes are looked up, in order: the mounted custom folder, downloaded community themes,
    then the built-in themes. nginx serves theme files in the same order.
    """
    return [CUSTOM_THEMES_DIR, COMMUNITY_THEMES_DIR, THEMES_DIR]

def find_theme(theme_id: str) -> Optional[Path]:
    """
    The theme.css for a theme id, or None. Each theme is a folder, <id>/theme.css, so it can carry
    its own fonts and images. The first folder in theme_dirs() that has the theme wins.
    """
    if not re.fullmatch(THEME_NAME_PATTERN, theme_id):
        return None
    for folder in theme_dirs():
        css = folder / theme_id / THEME_FILE
        if css.is_file():
            return css
    return None

def theme_label(path: Path) -> str:
    """
    A theme's display name: the text before the first colon in its opening comment
    (for example "/* Retro CRT: green phosphor ... */"), or the folder name made readable.
    """
    try:
        head = path.read_text(encoding="utf-8")[:300]
    except OSError:
        head = ""
    match = re.match(r"\s*/\*\s*([^:*\n]{1,40}?)\s*:", head)
    if match:
        return match.group(1).strip()
    return path.parent.name.replace("-", " ").title()

def is_theme_folder(path: Path) -> bool:
    return path.is_dir() and re.fullmatch(FOLDER_NAME_PATTERN, path.name) is not None and (path / THEME_FILE).is_file()

def is_owner_folder(path: Path) -> bool:
    """A folder named after a person, holding their themes (<username>/<theme>/theme.css)."""
    return (path.is_dir() and re.fullmatch(FOLDER_NAME_PATTERN, path.name) is not None
            and not (path / THEME_FILE).is_file()
            and any(is_theme_folder(child) for child in path.iterdir()))

def theme_ids_in(folder: Path) -> List[str]:
    """
    The valid themes in one folder: theme folders directly inside it (a usable name and a
    theme.css), and <username>/<theme> folders one level down.
    """
    if not folder.is_dir():
        return []
    ids = []
    for path in folder.iterdir():
        if is_theme_folder(path):
            ids.append(path.name)
        elif is_owner_folder(path):
            ids.extend(f"{path.name}/{child.name}" for child in path.iterdir() if is_theme_folder(child))
    return sorted(ids)

def list_themes() -> List[Dict[str, str]]:
    """
    Every theme from the theme folders, for the on-screen theme switcher. Names are shown without
    the username, unless two themes have the same name: then those get it, as "Name (username)".
    """
    ids = sorted({theme_id for folder in theme_dirs() for theme_id in theme_ids_in(folder)})
    themes = [{"id": theme_id, "name": theme_label(find_theme(theme_id))} for theme_id in ids]
    counts: Dict[str, int] = {}
    for theme in themes:
        counts[theme["name"]] = counts.get(theme["name"], 0) + 1
    for theme in themes:
        if counts[theme["name"]] > 1 and "/" in theme["id"]:
            theme["name"] = f"{theme['name']} ({theme['id'].split('/')[0]})"
    return themes

def check_theme_folders() -> None:
    """Log what was found in the custom themes folder, and anything there that cannot be used."""
    def warn(message: str) -> None:
        print(f"[Outpost] {message}", file=sys.stderr, flush=True)

    # Before 0.5.0 a theme was a single <id>.css file. Those are no longer loaded.
    for folder in theme_dirs():
        if folder.is_dir():
            for path in sorted(folder.glob("*.css")):
                warn(f"Ignoring {folder / path.name}: themes are now folders. Move it to {folder / path.stem / THEME_FILE}")

    if not CUSTOM_THEMES_DIR.is_dir():
        return

    for path in sorted(CUSTOM_THEMES_DIR.iterdir()):
        if not path.is_dir() or path.name.startswith("."):
            continue
        if not re.fullmatch(FOLDER_NAME_PATTERN, path.name):
            warn(f"Ignoring theme folder '{path.name}': names may use only lowercase letters, numbers, and hyphens")
        elif is_owner_folder(path):
            for child in sorted(path.iterdir()):
                if child.is_dir() and not child.name.startswith(".") and not is_theme_folder(child):
                    warn(f"Ignoring theme folder '{path.name}/{child.name}': it needs a name of lowercase letters, "
                         f"numbers, and hyphens, and a {THEME_FILE}")
        elif not (path / THEME_FILE).is_file():
            warn(f"Ignoring theme folder '{path.name}': it has no {THEME_FILE}")

    custom = theme_ids_in(CUSTOM_THEMES_DIR)
    if custom:
        built_in = set(theme_ids_in(THEMES_DIR))
        names = ", ".join(f"{theme_id} (replaces the built-in one)" if theme_id in built_in else theme_id for theme_id in custom)
        print(f"[Outpost] Custom themes in {CUSTOM_THEMES_DIR}: {names}", flush=True)

def write_config() -> None:
    """
    Write settings the web page needs (currently just the theme) to
    /data/config.json. Unknown theme names fall back to the default.
    """
    theme = THEME

    if not re.fullmatch(THEME_NAME_PATTERN, theme):
        print(f"[Outpost] Invalid OUTPOST_THEME '{theme}'; using {DEFAULT_THEME}", file=sys.stderr, flush=True)
        theme = DEFAULT_THEME
    elif any(folder.is_dir() for folder in theme_dirs()) and find_theme(theme) is None:
        searched = " or ".join(str(folder) for folder in theme_dirs())
        print(f"[Outpost] Theme '{theme}' not found in {searched}; using {DEFAULT_THEME}", file=sys.stderr, flush=True)
        theme = DEFAULT_THEME

    write_json(
        {
            "theme": theme,
            "app": APP_NAME,
            "version": APP_VERSION,
            "latitude": LATITUDE,
            "longitude": LONGITUDE,
            "dim": build_dim_config(),
            "ui": build_ui_config(),
            "themes": list_themes()
        },
        DATA_PATH.with_name("config.json")
    )

    # Coordinates are deliberately not logged, because logs get pasted into bug reports
    if os.getenv("OUTPOST_LATITUDE") and os.getenv("OUTPOST_LONGITUDE"):
        coordinates = "from OUTPOST_LATITUDE and OUTPOST_LONGITUDE"
    else:
        coordinates = "NOT SET, using the built-in example coordinates (set OUTPOST_LATITUDE and OUTPOST_LONGITUDE)"
    print(
        f"[Outpost] Settings written. Location: {LOCATION_NAME}; coordinates {coordinates}; "
        f"theme: {theme}; provider: {PROVIDER}",
        flush=True
    )

def mock_sample_alerts(now: datetime) -> List[Dict[str, Any]]:
    """Sample alerts for the mock provider: one of each severity, most serious first (as NWS sends them)."""
    def until(hours: int) -> str:
        return (now + timedelta(hours=hours)).replace(microsecond=0).isoformat()

    return [
        {
            "title": "Severe Thunderstorm Warning",
            "description": "Sample alert: storms with 60 mph wind gusts and quarter-size hail moving east at 30 mph.",
            "severity": "severe",
            "expires": until(2),
            "uri": None,
        },
        {
            "title": "Wind Advisory",
            "description": "Sample alert: southwest winds 25 to 35 mph with gusts to 50 mph.",
            "severity": "moderate",
            "expires": until(6),
            "uri": None,
        },
        {
            "title": "Air Quality Alert",
            "description": "Sample alert: smoke may cause unhealthy air for sensitive groups.",
            "severity": "minor",
            "expires": until(12),
            "uri": None,
        },
    ]

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
            "high": high,
            "low": low,
            "condition": condition,
            "icon": icon,
            "precipitation_chance": random.randint(0, 60),
            "uv_index": random.randint(0,8)
        })
    
    alerts = []

    if current_condition == "Thunderstorm watch":
        alerts.append({
            "title": "Outpost Test Alert",
            "description": "Mock alert generated for dashboard validation.",
            "severity": "test",
            "expires": None,
            "uri": None
        })

    # OUTPOST_MOCK_ALERTS=true: always include sample alerts of each kind, for trying how a theme
    # shows them (the mock otherwise has an alert only now and then)
    if env_flag("OUTPOST_MOCK_ALERTS", False):
        alerts.extend(mock_sample_alerts(now))

    mock_source = source_entry("mock", "Outpost Mock Provider")
    return build_payload(
        status="ok",
        sources={"weather": mock_source, "alerts": mock_source, "fill": None},
        current={
            "temperature": base_temp,
            "feels_like": feels_like,
            "condition": current_condition,
            "icon": current_icon,
            "humidity": random.randint(35, 85),
            "wind_speed": random.randint(0, 25),
            "pressure": round(random.uniform(29.70, 30.35), 2),
            "uv_index": random.randint(0, 8),
            "visibility": random.randint(5, 10)
        },
        forecast=forecast,
        alerts=alerts,
    )

def source_entry(source_id: str, name: str, **extra: Any) -> Dict[str, Any]:
    """One entry of the "sources" block: the provider's id (as in OUTPOST_PROVIDER) and the name to credit."""
    return {"id": source_id, "name": name, **extra}

def build_payload(
    status: str,
    sources: Dict[str, Any],
    current: Dict[str, Any],
    forecast: List[Dict[str, Any]],
    alerts: List[Dict[str, Any]],
    last_error: Optional[str] = None,
) -> Dict[str, Any]:
    """
    weather.json, in the format described in docs/data-format.md. Readings arrive in the providers'
    units, unrounded, and are converted to OUTPOST_UNITS and rounded here.
    """
    readings = units.present({"current": current, "forecast": forecast}, UNITS)
    return {
        "$schema": SCHEMA_URL,
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "app": APP_NAME,
        "version": APP_VERSION,
        "provider": PROVIDER,
        "sources": sources,
        "location": LOCATION_NAME,
        "coordinates": {
            "latitude": LATITUDE,
            "longitude": LONGITUDE
        },
        "generated_at": utc_now(),
        "update_interval_seconds": UPDATE_INTERVAL,
        "units": units_block(),
        "current": readings["current"],
        "forecast": readings["forecast"],
        "alerts": alerts,
        "last_error": last_error
    }

def build_error_payload(error_message: str) -> Dict[str, Any]:
    return build_payload(
        status="error",
        sources={"weather": None, "alerts": None, "fill": None},
        current={
            "temperature": None,
            "feels_like": None,
            "condition": "DATA LINK LOST",
            "icon": "unknown",
            "humidity": None,
            "wind_speed": None,
            "pressure": None,
            "uv_index": None,
            "visibility": None
        },
        forecast=[],
        alerts=[],
        last_error=error_message,
    )

def build_live_payload(provider_name: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Wrap normalized provider data with Outpost metadata."""
    weather = source_entry(provider_name, data.get("source") or provider_name)
    return build_payload(
        status="ok",
        sources={
            "weather": weather,
            # null when the provider has no official alerts (the dashboard then says so)
            "alerts": weather if data.get("alerts_supported") else None,
            "fill": data.get("fill"),
        },
        current=data["current"],
        forecast=data["forecast"],
        alerts=data.get("alerts", []) if data.get("alerts_supported") else [],
    )

def can_keep_previous(previous: Dict[str, Any]) -> bool:
    """
    True if the last weather.json can be shown again as degraded data: it has a reading, is in the
    current format and units, and is for the same provider setting and location. Data from before
    an upgrade or a settings change is not shown, because it would be read or labeled wrongly.
    """
    saved_units = previous.get("units")
    return (
        previous.get("schema_version") == SCHEMA_VERSION
        and isinstance(saved_units, dict)
        and saved_units == units_block()
        and (previous.get("current") or {}).get("temperature") is not None
        and previous.get("provider") == PROVIDER
        and previous.get("location") == LOCATION_NAME
    )

def write_degraded_or_error(error_message: str) -> None:
    """
    On a failed update, keep showing the last good data (marked degraded)
    when can_keep_previous allows it. Otherwise write an error payload.
    generated_at is left alone so the data visibly ages.
    """
    try:
        with DATA_PATH.open("r", encoding="utf-8") as file:
            previous = json.load(file)

        if isinstance(previous, dict) and can_keep_previous(previous):
            previous["status"] = "degraded"
            previous["last_error"] = error_message
            previous["update_interval_seconds"] = UPDATE_INTERVAL
            write_json(previous)
            return
    except Exception:
        pass

    write_json(build_error_payload(error_message=error_message))

def fetch_nws_with_gap_fill() -> Dict[str, Any]:
    """
    NWS data, plus Open-Meteo for anything NWS does not publish (such as UV
    index). If Open-Meteo is unavailable, NWS data is used as-is.
    """
    data = nws.fetch(LATITUDE, LONGITUDE, USER_AGENT)

    if gapfill.has_gaps(data):
        try:
            backup = openmeteo.fetch(LATITUDE, LONGITUDE, USER_AGENT)
            data, filled = gapfill.fill(data, backup)
            if filled:
                data["fill"] = source_entry("openmeteo", openmeteo.SOURCE, fields=filled)
                print(f"[Outpost] Filled from Open-Meteo: {', '.join(filled)}", flush=True)
        except Exception as error:
            print(f"[Outpost] Gap fill skipped (Open-Meteo failed): {error}", file=sys.stderr, flush=True)

    return data

_warned_user_agent = False

def has_contact_info() -> bool:
    """True if a contact was configured (an advanced User-Agent override counts if it contains one)."""
    return bool(CONTACT) or "@" in USER_AGENT or "http" in USER_AGENT.lower()

def warn_about_user_agent() -> None:
    """The National Weather Service asks every client to include contact information."""
    global _warned_user_agent
    if _warned_user_agent:
        return
    _warned_user_agent = True
    if not has_contact_info():
        print(
            "[Outpost] Warning: no contact information is set. The National Weather Service asks for one. "
            "Set OUTPOST_CONTACT to an email address or website, for example OUTPOST_CONTACT=you@example.com",
            file=sys.stderr,
            flush=True
        )

def update_once() -> None:
    try:
        print(f"[Outpost] Starting update. Provider={PROVIDER}", flush=True)

        if PROVIDER == "mock":
            payload = build_mock_payload()
        elif PROVIDER == "openmeteo":
            data = openmeteo.fetch(LATITUDE, LONGITUDE, USER_AGENT)
            payload = build_live_payload("openmeteo", data)
        elif PROVIDER == "nws":
            warn_about_user_agent()
            data = nws.fetch(LATITUDE, LONGITUDE, USER_AGENT)
            payload = build_live_payload("nws", data)
        elif PROVIDER == "auto":
            # National Weather Service inside the US, Open-Meteo everywhere else
            warn_about_user_agent()
            try:
                data = fetch_nws_with_gap_fill()
                payload = build_live_payload("nws", data)
            except nws.NoCoverageError:
                data = openmeteo.fetch(LATITUDE, LONGITUDE, USER_AGENT)
                payload = build_live_payload("openmeteo", data)
        else:
            raise RuntimeError(
                f"Provider '{PROVIDER}' is not implemented yet. Use OUTPOST_PROVIDER=mock, openmeteo, nws, or auto."
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

    check_theme_folders()
    write_config()

    if args.loop:
        run_loop()
    else:
        update_once()

if __name__ == "__main__":
    main()