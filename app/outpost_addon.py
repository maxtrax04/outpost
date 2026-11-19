#!/usr/bin/env python3
"""
Home Assistant add-on mode (homeassistant/outpost/, docs/home-assistant.md).

Home Assistant's Supervisor writes the add-on's options to /data/options.json. At startup,
start.sh runs this script, which turns them into Outpost's usual settings (the option "map_zoom"
is OUTPOST_MAP_ZOOM, and "timezone" is TZ) in /run/outpost/addon.env, for start.sh to read before
anything else starts. Options left empty fall back to Home Assistant's own home location, time
zone, and units (read from its API with the SUPERVISOR_TOKEN the Supervisor gives the add-on),
then to Outpost's defaults.

It also writes /etc/nginx/outpost/addon.conf: in the add-on, nginx also listens on INGRESS_PORT
for Home Assistant's ingress (the Outpost panel in its sidebar) and answers there only the
Supervisor's proxy, as Home Assistant asks. Outside the add-on the file only says so.

Coordinates and the token are never printed or written anywhere but the settings file.

Uses only the Python standard library.
"""

import json
import os
import re
import shlex
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Dict, Mapping, Optional

OPTIONS_PATH = Path("/data/options.json")
ENV_PATH = Path("/run/outpost/addon.env")
SNIPPET_PATH = Path("/etc/nginx/outpost/addon.conf")
INGRESS_PORT = 8099
# The only address ingress requests come from
INGRESS_PROXY = "172.30.32.2"
HOME_ASSISTANT_CONFIG_URL = "http://supervisor/core/api/config"
TIMEOUT_SECONDS = 10

OPTION_NAME = re.compile(r"[a-z][a-z0-9_]{0,40}")
# Options whose setting is not OUTPOST_<NAME>
SETTING_NAMES = {"timezone": "TZ"}

Getter = Callable[[str, str], Dict[str, Any]]


def _say(message: str) -> None:
    print(f"[Outpost] {message}", file=sys.stderr, flush=True)


def setting_name(option: str) -> Optional[str]:
    if not OPTION_NAME.fullmatch(option):
        return None
    return SETTING_NAMES.get(option, f"OUTPOST_{option.upper()}")


def value_text(value: Any) -> Optional[str]:
    """An option's value as a setting, or None for an empty option (Outpost's default applies)."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return format(value, "f").rstrip("0").rstrip(".") if value == value else None
    if isinstance(value, str):
        text = value.strip()
        return text or None
    return None


def settings_from_options(options: Mapping[str, Any]) -> Dict[str, str]:
    settings = {}
    for option, value in options.items():
        name = setting_name(option)
        text = value_text(value)
        if name and text is not None:
            settings[name] = text
    return settings


def coordinate(value: Any, limit: float) -> Optional[str]:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not abs(value) <= limit:
        return None
    return value_text(float(value))


def from_home_assistant(config: Mapping[str, Any]) -> Dict[str, str]:
    """Home, its time zone, and its units from Home Assistant's /api/config."""
    settings = {}
    latitude, longitude = coordinate(config.get("latitude"), 90), coordinate(config.get("longitude"), 180)
    if latitude is not None and longitude is not None:
        settings["OUTPOST_LATITUDE"], settings["OUTPOST_LONGITUDE"] = latitude, longitude
    name = config.get("location_name")
    if isinstance(name, str) and name.strip():
        settings["OUTPOST_LOCATION_NAME"] = re.sub(r"\s+", " ", name).strip()[:80]
    zone = config.get("time_zone")
    if isinstance(zone, str) and re.fullmatch(r"[A-Za-z0-9_+\-]+(?:/[A-Za-z0-9_+\-]+)*", zone):
        settings["TZ"] = zone
    units = config.get("unit_system")
    temperature = units.get("temperature") if isinstance(units, dict) else None
    if temperature in ("°C", "°F"):
        settings["OUTPOST_UNITS"] = "metric" if temperature == "°C" else "imperial"
    return settings


def combine(options: Dict[str, str], home_assistant: Dict[str, str]) -> Dict[str, str]:
    """The options win; a location set in the options replaces Home Assistant's as a whole."""
    settings = dict(home_assistant)
    if "OUTPOST_LATITUDE" in options or "OUTPOST_LONGITUDE" in options:
        for name in ("OUTPOST_LATITUDE", "OUTPOST_LONGITUDE", "OUTPOST_LOCATION_NAME"):
            settings.pop(name, None)
    settings.update(options)
    return settings


def http_get(url: str, token: str) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                                   "Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        answer = json.loads(response.read(1_000_000).decode("utf-8"))
    return answer if isinstance(answer, dict) else {}


def home_assistant_config(token: str, get: Getter = http_get) -> Dict[str, Any]:
    if not token:
        return {}
    try:
        return get(HOME_ASSISTANT_CONFIG_URL, token)
    except (urllib.error.URLError, OSError, ValueError) as error:
        _say(f"Could not read Home Assistant's location and units ({type(error).__name__}); "
             f"using the add-on's options and Outpost's defaults")
        return {}


def env_text(settings: Mapping[str, str]) -> str:
    lines = ["# Written by /app/outpost_addon.py from the add-on's options; read by start.sh."]
    lines += [f"export {name}={shlex.quote(value)}" for name, value in sorted(settings.items())]
    return "\n".join(lines) + "\n"


def nginx_snippet(addon: bool) -> str:
    header = "# Written by /app/outpost_addon.py at startup; edits here are overwritten.\n"
    if not addon:
        return header + "# Not running as a Home Assistant add-on, so no ingress port.\n"
    return header + (
        "# Home Assistant ingress: the same site on its own port, for the Supervisor's proxy only\n"
        f"listen {INGRESS_PORT};\n"
        "if ($outpost_ingress_refused) {\n"
        "    return 403;\n"
        "}\n"
    )


# Options whose values are choices from a list, so the log can show them
CHOICE_OPTIONS = ("provider", "alerts_provider", "units", "effects", "clock", "dim_mode")


def options_summary(options: Mapping[str, Any]) -> str:
    """The options that are set, for the log: switches as on or off, choices by value, and anything
    else (a key, a contact, coordinates, text) only as "set", so no value of those reaches the log."""
    parts = []
    for option, value in options.items():
        if not isinstance(option, str) or not re.fullmatch(r"[a-z_]{1,40}", option):
            continue
        if isinstance(value, bool):
            parts.append(f"{option} {'on' if value else 'off'}")
        elif value_text(value) is None:
            continue
        elif option in CHOICE_OPTIONS and re.fullmatch(r"[a-z0-9]{1,20}", str(value)):
            parts.append(f"{option} {value}")
        else:
            parts.append(f"{option} set")
    return ", ".join(parts) or "none"


def write_atomically(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def run(options_path: Path = OPTIONS_PATH, env_path: Path = ENV_PATH, snippet_path: Path = SNIPPET_PATH,
        environ: Optional[Mapping[str, str]] = None, get: Getter = http_get) -> bool:
    """Writes the settings and the nginx snippet; True when running as an add-on."""
    environ = os.environ if environ is None else environ
    addon = options_path.is_file()
    write_atomically(snippet_path, nginx_snippet(addon))
    if not addon:
        return False
    try:
        options = json.loads(options_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        _say(f"Could not read the add-on's options ({type(error).__name__}); using the defaults")
        options = {}
    from_options = settings_from_options(options if isinstance(options, dict) else {})
    from_ha = from_home_assistant(home_assistant_config(environ.get("SUPERVISOR_TOKEN", ""), get))
    settings = combine(from_options, from_ha)
    write_atomically(env_path, env_text(settings))
    taken = [label for label, name in (("home location", "OUTPOST_LATITUDE"), ("time zone", "TZ"), ("units", "OUTPOST_UNITS"))
             if name in from_ha and settings.get(name) == from_ha[name] and name not in from_options]
    source = f"; {', '.join(taken)} from Home Assistant" if taken else ""
    _say(f"Home Assistant add-on: {len(from_options)} options set{source}; ingress on port {INGRESS_PORT}")
    # What Home Assistant saved, so a setting that did not stick is easy to see
    _say(f"Add-on options: {options_summary(options if isinstance(options, dict) else {})}")
    return True


if __name__ == "__main__":
    run()
