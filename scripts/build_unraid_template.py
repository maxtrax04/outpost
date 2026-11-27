#!/usr/bin/env python3
"""
Build the unRAID Community Apps template (unraid/outpost.xml) from the README's settings table, so
every setting, its default, and its description stay the same in both.

    python3 scripts/build_unraid_template.py           write unraid/outpost.xml
    python3 scripts/build_unraid_template.py --check   fail if it is out of date (tests/test_unraid.py)

Uses only the Python standard library.
"""

import re
import sys
from pathlib import Path
from typing import List, Tuple
from xml.sax.saxutils import escape, quoteattr

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
TEMPLATE = ROOT / "unraid" / "outpost.xml"

PROJECT = "https://github.com/maxtrax04/outpost"
RAW = "https://raw.githubusercontent.com/maxtrax04/outpost/main"

# Compose only: unRAID maps the port itself
LEFT_OUT = {"OUTPOST_WEB_PORT"}
# Shown without "Show more settings"
ALWAYS_SHOWN = ["OUTPOST_PROVIDER", "OUTPOST_LOCATION_NAME", "OUTPOST_LATITUDE", "OUTPOST_LONGITUDE",
                "OUTPOST_UNITS", "OUTPOST_THEME", "OUTPOST_CONTACT"]
# Choices, the default first (unRAID shows a list)
CHOICES = {
    "OUTPOST_PROVIDER": ["openmeteo", "auto", "nws", "metno", "pirateweather", "openweathermap", "mock"],
    "OUTPOST_OPENWEATHERMAP_PLAN": ["onecall", "free"],
    "OUTPOST_ALERTS_PROVIDER": ["auto", "nws", "metno", "pirateweather", "openweathermap", "none"],
    "OUTPOST_EFFECTS": ["full", "reduced"],
    "OUTPOST_DIM_MODE": ["sun", "schedule"],
    "OUTPOST_CLOCK": ["auto", "12", "24"],
    "OUTPOST_AIR_QUALITY_INDEX": ["auto", "us", "european"],
    "OUTPOST_UNITS": ["imperial", "metric"],
}
# Where the template's default differs from Outpost's own: mock data is no use on a server, and
# .env.example starts with Open-Meteo too
TEMPLATE_DEFAULTS = {"OUTPOST_PROVIDER": "openmeteo"}

OVERVIEW = ("Outpost is a self-hosted, themeable weather dashboard for wall-mounted displays, tablets, and phones, "
            "with a retro terminal look. It shows current conditions, an hourly and 5-day forecast, official alerts, "
            "air quality, an optional map with rain radar, and sensor and power readings from Home Assistant or MQTT. "
            "Weather comes from Open-Meteo by default (no key needed); the National Weather Service, MET Norway, "
            "Pirate Weather, and OpenWeatherMap are also available. Set your latitude and longitude, then open the "
            "web UI. All settings are described in the README.")


def plain(text: str) -> str:
    """README Markdown as plain text: links become their text, code and emphasis marks go."""
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("`", "").replace("**", "")
    text = re.sub(r"\*\(([^)]*)\)\*", r"(\1)", text)
    return " ".join(text.split())


def settings() -> List[Tuple[str, str, str]]:
    """(name, default, description) for each row of the README's settings table."""
    rows = []
    for line in README.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\| `(OUTPOST_[A-Z0-9_]+)`(?: / `(OUTPOST_[A-Z0-9_]+)`)? \| (.*?) \| (.*) \|$", line)
        if not match:
            continue
        first, second, default, description = match.groups()
        defaults = [part.strip().strip("`") for part in default.split(" / ")] if second else [default]
        for index, name in enumerate([first] + ([second] if second else [])):
            value = defaults[min(index, len(defaults) - 1)].strip()
            value = "" if value.startswith("*(") or value.startswith("(") else value.strip("`")
            rows.append((name, value, plain(description)))
    return rows


def label(name: str) -> str:
    """OUTPOST_MAP_RADAR_LOOP -> "Map radar loop"."""
    words = name.removeprefix("OUTPOST_").lower().split("_")
    small = {"api": "API", "ha": "Home Assistant", "url": "URL", "mqtt": "MQTT", "tls": "TLS", "uv": "UV",
             "pirateweather": "Pirate Weather", "openweathermap": "OpenWeatherMap"}
    text = " ".join(small.get(word, word) for word in words)
    return text[0].upper() + text[1:]


def config_line(name: str, default: str, description: str) -> str:
    default = TEMPLATE_DEFAULTS.get(name, default)
    if name in CHOICES:
        options = CHOICES[name]
        assert options[0] == default, (name, default)
        listed = "|".join(options)
    elif default in ("true", "false"):
        listed = "|".join([default, "false" if default == "true" else "true"])
    else:
        listed = default
    secret = name.endswith(("_API_KEY", "_TOKEN", "_PASSWORD"))
    attributes = {
        "Name": label(name), "Target": name, "Default": listed, "Mode": "", "Description": description,
        "Type": "Variable", "Display": "always" if name in ALWAYS_SHOWN else "advanced",
        "Required": "false", "Mask": "true" if secret else "false",
    }
    text = " ".join(f"{key}={quoteattr(value)}" for key, value in attributes.items())
    return f"  <Config {text}>{escape(default)}</Config>"


def build() -> str:
    rows = [row for row in settings() if row[0] not in LEFT_OUT]
    order = {name: index for index, name in enumerate(ALWAYS_SHOWN)}
    rows.sort(key=lambda row: order.get(row[0], len(order)))
    head = f'''<?xml version="1.0"?>
<!-- Built by scripts/build_unraid_template.py from the README's settings table; edit those, not this. -->
<Container version="2">
  <Name>Outpost</Name>
  <Repository>ghcr.io/maxtrax04/outpost:latest</Repository>
  <Registry>{PROJECT}/pkgs/container/outpost</Registry>
  <Network>bridge</Network>
  <Shell>sh</Shell>
  <Privileged>false</Privileged>
  <Support>{PROJECT}/issues</Support>
  <Project>{PROJECT}</Project>
  <Overview>{escape(OVERVIEW)}</Overview>
  <Category>HomeAutomation: Tools:</Category>
  <WebUI>http://[IP]:[PORT:80]/</WebUI>
  <TemplateURL>{RAW}/unraid/outpost.xml</TemplateURL>
  <Icon>{RAW}/assets/app/icon-512.png</Icon>
  <Config Name="Web UI port" Target="80" Default="8088" Mode="tcp" Description="The port for the dashboard (container port 80)." Type="Port" Display="always" Required="true" Mask="false">8088</Config>
  <Config Name="Data" Target="/data" Default="/mnt/user/appdata/outpost" Mode="rw" Description="Where Outpost keeps weather.json and its settings for the dashboard, so they survive restarts." Type="Path" Display="always" Required="true" Mask="false">/mnt/user/appdata/outpost</Config>
  <Config Name="Your own themes" Target="/config/themes" Default="/mnt/user/appdata/outpost/themes" Mode="ro" Description="Optional: your own themes, one folder each with a theme.css (see docs/themes.md). Restart the container after adding one." Type="Path" Display="advanced" Required="false" Mask="false">/mnt/user/appdata/outpost/themes</Config>
'''
    return head + "\n".join(config_line(*row) for row in rows) + "\n</Container>\n"


def main(argv: List[str]) -> int:
    text = build()
    if "--check" in argv:
        current = TEMPLATE.read_text(encoding="utf-8") if TEMPLATE.exists() else ""
        if current != text:
            print("unraid/outpost.xml is out of date: run python3 scripts/build_unraid_template.py", file=sys.stderr)
            return 1
        return 0
    TEMPLATE.parent.mkdir(exist_ok=True)
    TEMPLATE.write_text(text, encoding="utf-8", newline="\n")
    print(f"Wrote {TEMPLATE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
