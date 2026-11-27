#!/usr/bin/env python3
"""
Sensors (docs/sensors-design.md): readings from Home Assistant or MQTT for the sensor and power
panels.

OUTPOST_SENSORS lists the readings, separated by commas. Each one is a source, optionally with a
label before "=" and a unit in brackets after it:

    sensor.living_room_temperature, Garage=binary_sensor.garage_door, Shed=mqtt:shed/climate#temperature [°F]

A source is a Home Assistant entity ID, or mqtt:<topic>, with #<field> for a field of a JSON
message (#ENERGY.Power for one inside another). The power panel has one setting per role, each one
source (OUTPOST_POWER_HOME, OUTPOST_POWER_SOLAR, OUTPOST_POWER_GRID, OUTPOST_POWER_BATTERY), and
OUTPOST_POWER_GRID_INVERT flips the grid's sign for meters that count exports as positive.

outpost_server.py reads each Home Assistant entity every OUTPOST_SENSORS_INTERVAL seconds, gets each
MQTT topic as the broker sends it (outpost_mqtt.py), and answers /api/sensors with the latest
values. Only what is listed here is ever read or answered, so a screen can't use Outpost to read
the rest of Home Assistant or the broker. Outpost only reads: it never calls a Home Assistant
service and never publishes to MQTT.

Home Assistant is reached at OUTPOST_HA_URL with the long-lived token OUTPOST_HA_TOKEN or, in the
add-on, through the Supervisor with the token it gives the add-on. The broker is OUTPOST_MQTT_HOST
(and _PORT, _USERNAME, _PASSWORD, _TLS); the add-on fills these in from Home Assistant's MQTT
service. Tokens and passwords are never logged or sent to a screen, and the log names entities and
topics without their values.

Uses only the Python standard library.
"""

import json
import math
import os
import outpost_env  # noqa: F401 (first: an empty OUTPOST_* setting means its default)
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

import outpost_mqtt

MAX_ITEMS = 24
DEFAULT_INTERVAL = 10
MIN_INTERVAL = 5
MAX_INTERVAL = 3600
# A reading is kept this long while its source can't be reached, then shown as missing
KEEP_SECONDS = 15 * 60
TIMEOUT_SECONDS = 5
MAX_ANSWER_BYTES = 200_000
MAX_LABEL_LENGTH = 40
MAX_UNIT_LENGTH = 12
MAX_TEXT_LENGTH = 40

SUPERVISOR_URL = "http://supervisor/core"

# The power panel's roles, in the order shown: (role, label, setting)
POWER_ROLES = (
    ("home", "Home", "OUTPOST_POWER_HOME"),
    ("solar", "Solar", "OUTPOST_POWER_SOLAR"),
    ("grid", "Grid", "OUTPOST_POWER_GRID"),
    ("battery", "Battery", "OUTPOST_POWER_BATTERY"),
)
POWER_LABELS = {role: label for role, label, _ in POWER_ROLES}

# Home Assistant entity IDs are "<domain>.<object id>", in lower case
ENTITY_ID = re.compile(r"[a-z][a-z0-9_]{0,40}\.[a-z0-9_]{1,200}")
DEVICE_CLASS = re.compile(r"[a-z0-9_]{1,40}")
# An MQTT topic to subscribe to: exact (no + or # wildcards), with an optional JSON field after #
MQTT_TOPIC = re.compile(r"[^\s#+\x00=\[\],]{1,200}")
MQTT_FIELD = re.compile(r"[A-Za-z0-9_:\-]{1,60}(?:\.[A-Za-z0-9_:\-]{1,60}){0,5}")
# What MQTT on/off values look like (when the item has no unit; 1 and 0 stay numbers)
MQTT_ON_OFF = ("on", "off", "true", "false")
ITEM = re.compile(r"(?:(?P<label>[^=\[\]]*?)\s*=\s*)?(?P<source>[^\s=\[\]]+)(?:\s*\[(?P<unit>[^\[\]]*)\])?")

MISSING_STATES = ("unavailable", "unknown", "none", "", "nan", "inf", "-inf")
ON_STATES = ("on", "true", "open", "detected", "home")
OFF_STATES = ("off", "false", "closed", "clear", "not_home")
# What on and off read as, by device class (the rest read On and Off)
BINARY_TEXT = {
    **{name: ("Open", "Closed") for name in ("door", "window", "garage_door", "opening")},
    **{name: ("Detected", "Clear") for name in ("motion", "occupancy", "presence", "smoke", "gas", "sound",
                                                 "vibration", "carbon_monoxide")},
    "moisture": ("Wet", "Dry"),
    "lock": ("Unlocked", "Locked"),
    "plug": ("Plugged in", "Unplugged"),
    "connectivity": ("Connected", "Disconnected"),
    "battery": ("Low", "Normal"),
    "problem": ("Problem", "OK"),
}


def _say(message: str) -> None:
    print(f"[Outpost] {message}", file=sys.stderr, flush=True)


def plain_text(text: Any, limit: int) -> str:
    """One line of printable text, at most `limit` characters."""
    if not isinstance(text, str):
        return ""
    text = re.sub(r"[\x00-\x1f\x7f]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()[:limit].strip()


class Item:
    """One listed reading."""

    def __init__(self, number: int, source: str, label: str = "", unit: str = "", role: str = "") -> None:
        # role: "" for the sensor panel, or one of the power panel's POWER_ROLES
        self.id = f"p-{role}" if role else f"s{number}"
        self.source = source
        self.label = label
        self.unit = unit
        self.role = role
        # For an mqtt: source, its topic and the path to its JSON field, if any
        self.topic = ""
        self.field: Tuple[str, ...] = ()
        if source.startswith("mqtt:"):
            topic, _, field = source[5:].partition("#")
            self.topic = topic
            self.field = tuple(field.split(".")) if field else ()

    @property
    def mqtt(self) -> bool:
        return bool(self.topic)

    @property
    def domain(self) -> str:
        """The Home Assistant domain (sensor, binary_sensor, ...), or "mqtt"."""
        return "mqtt" if self.mqtt else self.source.split(".", 1)[0]

    def default_label(self) -> str:
        """The label when neither the list nor the source gives one: for MQTT the field or the last
        part of the topic ("Temperature" for mqtt:shed/climate#temperature), else the entity ID."""
        if not self.mqtt:
            return self.source
        name = self.field[-1] if self.field else self.topic.rstrip("/").rsplit("/", 1)[-1]
        name = plain_text(re.sub(r"[_\-]+", " ", name), MAX_LABEL_LENGTH) or "Sensor"
        return name[:1].upper() + name[1:]

    def __repr__(self) -> str:
        return f"Item({self.source!r}, label={self.label!r}, unit={self.unit!r})"


def parse_items(text: Optional[str]) -> Tuple[List[Item], List[str]]:
    """The readings in an OUTPOST_SENSORS list, and a note for each item that was skipped."""
    items: List[Item] = []
    problems: List[str] = []
    seen = set()
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        shown = plain_text(part, 60)
        match = ITEM.fullmatch(part)
        if not match:
            problems.append(f"\"{shown}\" is not a reading (write it as Label=sensor.name [unit])")
            continue
        source = match.group("source")
        label = plain_text(match.group("label") or "", MAX_LABEL_LENGTH)
        unit = plain_text(match.group("unit") or "", MAX_UNIT_LENGTH)
        if source.startswith("mqtt:"):
            topic, has_field, field = source[5:].partition("#")
            if not MQTT_TOPIC.fullmatch(topic) or (has_field and not MQTT_FIELD.fullmatch(field)):
                problems.append(f"\"{shown}\" is not an MQTT topic (such as mqtt:shed/temperature, or "
                                f"mqtt:shed/climate#temperature for a field of a JSON message; no + or # wildcards)")
                continue
        elif not ENTITY_ID.fullmatch(source):
            problems.append(f"\"{shown}\" is not a Home Assistant entity ID (such as sensor.living_room_temperature) "
                            f"or an MQTT topic (mqtt:shed/temperature)")
            continue
        if (source, label, unit) in seen:
            continue
        if len(items) >= MAX_ITEMS:
            problems.append(f"only the first {MAX_ITEMS} readings are shown")
            break
        seen.add((source, label, unit))
        items.append(Item(len(items) + 1, source, label, unit))
    return items, problems


def flag(value: Optional[str], default: bool = False) -> bool:
    text = (value or "").strip().lower()
    if not text:
        return default
    return text in ("1", "true", "yes", "on")


def parse_power(environ: Mapping[str, str]) -> Tuple[List[Item], List[str]]:
    """The power panel's readings, one per role that is set, and a note for each setting skipped."""
    items: List[Item] = []
    problems: List[str] = []
    for role, _, setting in POWER_ROLES:
        found, notes = parse_items(environ.get(setting))
        problems.extend(f"{setting}: {note}; skipping it" for note in notes)
        if len(found) > 1:
            problems.append(f"{setting}: one reading per role; using the first")
        if found:
            first = found[0]
            items.append(Item(0, first.source, first.label, first.unit, role))
    return items, problems


def interval_setting(value: Optional[str]) -> int:
    """Seconds between reads: OUTPOST_SENSORS_INTERVAL, between MIN_INTERVAL and MAX_INTERVAL."""
    try:
        seconds = int((value or "").strip() or DEFAULT_INTERVAL)
    except ValueError:
        _say(f"OUTPOST_SENSORS_INTERVAL must be a whole number of seconds; using {DEFAULT_INTERVAL}")
        return DEFAULT_INTERVAL
    if seconds < MIN_INTERVAL:
        _say(f"OUTPOST_SENSORS_INTERVAL is at least {MIN_INTERVAL} seconds; using {MIN_INTERVAL}")
    return min(MAX_INTERVAL, max(MIN_INTERVAL, seconds))


def home_assistant_url(value: Optional[str]) -> Optional[str]:
    """OUTPOST_HA_URL as http(s)://host[:port][/path], without a trailing / or /api; None when unusable."""
    text = (value or "").strip().rstrip("/")
    if text.endswith("/api"):
        text = text[:-4]
    try:
        parts = urllib.parse.urlsplit(text)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.hostname or parts.query or parts.fragment \
            or parts.username or parts.password or not all(32 < ord(char) < 127 for char in text):
        return None
    return text


def clean_token(value: Optional[str]) -> str:
    """A token as it goes into a header: printable ASCII with no spaces, or "" when it isn't one."""
    text = (value or "").strip()
    return text if text and len(text) <= 1000 and all(32 < ord(char) < 127 for char in text) else ""


def connection(environ: Mapping[str, str]) -> Tuple[Optional[str], str, str]:
    """(url, token, where) for Home Assistant: OUTPOST_HA_URL and OUTPOST_HA_TOKEN, or in the add-on
    the Supervisor. url is None when there is no usable connection, and `where` then says why."""
    setting = (environ.get("OUTPOST_HA_URL") or "").strip()
    if setting:
        url = home_assistant_url(setting)
        token = clean_token(environ.get("OUTPOST_HA_TOKEN"))
        if url is None:
            return None, "", "OUTPOST_HA_URL is not an http:// or https:// address"
        if not token:
            return None, "", "OUTPOST_HA_TOKEN is not set (a long-lived access token from your Home Assistant profile)"
        return url, token, "Home Assistant"
    supervisor = clean_token(environ.get("SUPERVISOR_TOKEN"))
    if supervisor:
        return SUPERVISOR_URL, supervisor, "Home Assistant (add-on)"
    return None, "", "Home Assistant is not set up (OUTPOST_HA_URL and OUTPOST_HA_TOKEN)"


class MqttSettings:
    """Where the broker is and how to log in. The password is left out of repr."""

    def __init__(self, host: str, port: int = 1883, username: str = "", password: str = "",
                 tls: bool = False) -> None:
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.tls = tls

    def __repr__(self) -> str:
        return f"MqttSettings({self.host!r}, {self.port}, tls={self.tls})"


MQTT_HOST = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9._\-]{0,252})|[0-9A-Fa-f:.]{2,45}")


def mqtt_connection(environ: Mapping[str, str]) -> Tuple[Optional[MqttSettings], str]:
    """The broker from OUTPOST_MQTT_HOST, _PORT, _USERNAME, _PASSWORD, and _TLS, or None and why not."""
    host = (environ.get("OUTPOST_MQTT_HOST") or "").strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if not host:
        return None, "OUTPOST_MQTT_HOST is not set"
    if not MQTT_HOST.fullmatch(host):
        return None, "OUTPOST_MQTT_HOST is not a host name or address (such as mqtt.local or 192.168.1.20)"
    tls = flag(environ.get("OUTPOST_MQTT_TLS"))
    port_text = (environ.get("OUTPOST_MQTT_PORT") or "").strip()
    try:
        port = int(port_text) if port_text else (8883 if tls else 1883)
    except ValueError:
        port = 0
    if not 0 < port < 65536:
        return None, "OUTPOST_MQTT_PORT is not a port number (1883, or 8883 with TLS)"
    username = plain_text(environ.get("OUTPOST_MQTT_USERNAME") or "", 200)
    password = (environ.get("OUTPOST_MQTT_PASSWORD") or "").strip()
    if password and not username:
        return None, "OUTPOST_MQTT_PASSWORD needs OUTPOST_MQTT_USERNAME too"
    return MqttSettings(host, port, username, password, tls), "an MQTT broker"


def mqtt_state(item: Item, payload: bytes) -> Dict[str, Any]:
    """An MQTT message as a Home Assistant-like state, for reading(): the text, or the JSON field."""
    try:
        text = payload.decode("utf-8").strip()
    except UnicodeDecodeError:
        return {"state": "unavailable"}
    if not item.field:
        if len(text) >= 2 and text[0] == text[-1] == '"':
            try:
                quoted = json.loads(text)
            except ValueError:
                quoted = None
            if isinstance(quoted, str):
                text = quoted.strip()
        return {"state": text}
    try:
        value: Any = json.loads(text)
    except ValueError:
        return {"state": "unavailable"}
    for key in item.field:
        if isinstance(value, dict) and key in value:
            value = value[key]
        elif isinstance(value, list) and key.isdigit() and int(key) < len(value):
            value = value[int(key)]
        else:
            return {"state": "unavailable"}
    if isinstance(value, bool):
        return {"state": "on" if value else "off"}
    if isinstance(value, (int, float)):
        return {"state": str(value)}
    if isinstance(value, str):
        return {"state": value.strip()}
    return {"state": "unavailable"}


class SourceError(Exception):
    """Home Assistant could not be asked at all (so the rest of the round is skipped)."""


class NotFound(Exception):
    """Home Assistant answered, but not with this entity."""


def http_get(url: str, token: str) -> Dict[str, Any]:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                                   "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            answer = json.loads(response.read(MAX_ANSWER_BYTES).decode("utf-8"))
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise NotFound("not found")
        if error.code in (401, 403):
            raise SourceError("the token was refused")
        raise SourceError(f"HTTP {error.code}")
    except (urllib.error.URLError, OSError) as error:
        raise SourceError(f"can't connect ({type(error).__name__})")
    except ValueError:
        raise SourceError("the answer is not JSON")
    if not isinstance(answer, dict):
        raise SourceError("the answer is not a state")
    return answer


def number_text(value: float, whole: bool) -> str:
    """At most one decimal under 100, none from 100 up, and none when the source sent a whole number."""
    if whole or abs(value) >= 100:
        return str(int(round(value)))
    text = f"{value:.1f}"
    return "0.0" if text == "-0.0" else text


def reading(item: Item, state: Mapping[str, Any]) -> Dict[str, Any]:
    """What a screen shows for an item, from a Home Assistant state."""
    attributes = state.get("attributes")
    attributes = attributes if isinstance(attributes, dict) else {}
    label = item.label or plain_text(attributes.get("friendly_name"), MAX_LABEL_LENGTH) or item.default_label()
    unit = item.unit or plain_text(attributes.get("unit_of_measurement"), MAX_UNIT_LENGTH)
    device_class = attributes.get("device_class")
    device_class = device_class if isinstance(device_class, str) and DEVICE_CLASS.fullmatch(device_class) else ""
    result: Dict[str, Any] = {"id": item.id, "label": label, "kind": "text", "value": None, "text": "",
                              "unit": unit, "device_class": device_class, "missing": True}

    raw = state.get("state")
    raw = raw.strip() if isinstance(raw, str) else ""
    if raw.lower() in MISSING_STATES:
        return result

    domain = item.domain
    try:
        number = float(raw)
    except ValueError:
        number = None
    if number is not None and math.isfinite(number) and domain != "binary_sensor":
        whole = re.fullmatch(r"-?\d+", raw) is not None
        if unit == "W" and abs(number) >= 1000:
            number, unit, whole = number / 1000, "kW", False
        result.update(kind="number", value=number, text=number_text(number, whole), unit=unit, missing=False)
        return result

    lower = raw.lower()
    if domain == "binary_sensor" or (not unit and (lower in ON_STATES or lower in OFF_STATES)
                                     and domain in ("switch", "light", "input_boolean", "fan")) \
            or (domain == "mqtt" and not unit and lower in MQTT_ON_OFF):
        on = lower in ON_STATES
        if not on and lower not in OFF_STATES:
            return result
        on_text, off_text = BINARY_TEXT.get(device_class, ("On", "Off"))
        result.update(kind="binary", value=on, text=on_text if on else off_text, unit="", missing=False)
        return result

    # Other text, such as a lock's "locked" or a cover's "opening": as Home Assistant says it, capitalized
    text = plain_text(raw.replace("_", " "), MAX_TEXT_LENGTH)
    result.update(text=text[:1].upper() + text[1:], value=text, unit=unit, missing=False)
    return result


def power_reading(item: Item, state: Mapping[str, Any], invert_grid: bool = False) -> Dict[str, Any]:
    """What the power panel shows for a role. Power is a number (anything else is missing). The grid
    is shown without its sign, with "direction": positive is importing (flipped by invert_grid). The
    battery's charge also comes as "fraction", 0 to 1, for a bar."""
    raw = state.get("state")
    raw = raw.strip() if isinstance(raw, str) else ""
    negative = raw.startswith("-")
    if item.role == "grid":
        state = dict(state, state=raw.lstrip("+-"))
    result = reading(item, state)
    result["role"] = item.role
    if not item.label:
        result["label"] = POWER_LABELS.get(item.role, result["label"])
    if result["kind"] != "number":
        result.update(kind="number", value=None, text="", missing=True)
    if item.role == "grid":
        result["direction"] = None
    if result["missing"]:
        return result
    if item.role == "grid":
        signed = -result["value"] if negative else result["value"]
        if invert_grid:
            signed = -signed
        result["value"] = signed if signed != 0 else 0.0
        result["direction"] = "import" if signed > 0 else "export" if signed < 0 else "idle"
    elif item.role == "battery":
        if not result["unit"]:
            result["unit"] = "%"
        if result["unit"] == "%":
            result["fraction"] = round(min(1.0, max(0.0, result["value"] / 100)), 3)
    return result


def missing_reading(item: Item) -> Dict[str, Any]:
    """An item with no reading yet, or none for too long."""
    if item.role:
        value = {"id": item.id, "role": item.role, "label": item.label or POWER_LABELS[item.role],
                 "kind": "number", "value": None, "text": "", "unit": item.unit, "device_class": "",
                 "missing": True}
        if item.role == "grid":
            value["direction"] = None
        return value
    return {"id": item.id, "label": item.label or item.default_label(), "kind": "text", "value": None,
            "text": "", "unit": item.unit, "device_class": "", "missing": True}


Getter = Callable[[str, str], Dict[str, Any]]


class Sensors:
    """The listed readings (the sensor list and the power roles) and their latest values, read from
    Home Assistant and MQTT by `run`."""

    def __init__(self, items: List[Item], url: Optional[str], token: str = "", where: str = "",
                 interval: int = DEFAULT_INTERVAL, get: Getter = http_get,
                 clock: Callable[[], float] = time.time, power: Optional[List[Item]] = None,
                 invert_grid: bool = False, mqtt: Optional[MqttSettings] = None, mqtt_where: str = "",
                 mqtt_client: Callable[..., Any] = outpost_mqtt.Client) -> None:
        self.items = items
        self.power = list(power or [])
        self.invert_grid = invert_grid
        self.mqtt = mqtt
        self.mqtt_where = mqtt_where or ("an MQTT broker" if mqtt else "OUTPOST_MQTT_HOST is not set")
        self.mqtt_client = mqtt_client
        self._mqtt_alive: Optional[float] = None
        self.url = url
        self.token = token
        self.where = where
        self.interval = interval
        self.get = get
        self.clock = clock
        self._lock = threading.Lock()
        self._readings: Dict[str, Dict[str, Any]] = {}
        self._read_at: Dict[str, float] = {}
        self._updated: Optional[float] = None
        self._problem: Optional[str] = None
        self._missing: set = set()

    @property
    def home_assistant_items(self) -> List[Item]:
        return [item for item in self.items + self.power if not item.mqtt]

    @property
    def mqtt_items(self) -> List[Item]:
        return [item for item in self.items + self.power if item.mqtt]

    @property
    def on(self) -> bool:
        """True when there is something to show: readings listed and somewhere to read them."""
        return bool(self.home_assistant_items and self.url is not None) \
            or bool(self.mqtt_items and self.mqtt is not None)

    def _report(self, problem: Optional[str]) -> None:
        if problem != self._problem:
            if problem:
                _say(f"Sensors: {self.where}: {problem}; keeping the last readings for {KEEP_SECONDS // 60} min")
            elif self._problem:
                _say(f"Sensors: {self.where} answers again")
            self._problem = problem

    def _report_missing(self, item: Item, missing: bool) -> None:
        if missing and item.source not in self._missing:
            _say(f"Sensors: {item.source} is not in Home Assistant (check the entity ID)")
            self._missing.add(item.source)
        elif not missing:
            self._missing.discard(item.source)

    def poll_once(self) -> None:
        """Reads every Home Assistant item once. When Home Assistant can't be asked, the rest of the
        round is skipped."""
        items = self.home_assistant_items
        if self.url is None or not items:
            return
        problem = None
        for item in items:
            url = f"{self.url}/api/states/{urllib.parse.quote(item.source)}"
            try:
                state = self.get(url, self.token)
            except NotFound:
                self._report_missing(item, True)
                state = {"state": "unavailable"}
            except SourceError as error:
                problem = str(error)
                break
            else:
                self._report_missing(item, False)
            value = power_reading(item, state, self.invert_grid) if item.role else reading(item, state)
            with self._lock:
                self._readings[item.id] = value
                self._read_at[item.id] = self.clock()
        with self._lock:
            if problem is None:
                self._updated = self.clock()
        self._report(problem)

    def mqtt_message(self, topic: str, payload: bytes) -> None:
        """A message from the broker: the new value of each item with that topic."""
        now = self.clock()
        for item in self.mqtt_items:
            if item.topic == topic:
                state = mqtt_state(item, payload)
                value = power_reading(item, state, self.invert_grid) if item.role else reading(item, state)
                with self._lock:
                    self._readings[item.id] = value
                    self._read_at[item.id] = now
                    self._updated = now
        self.mqtt_alive()

    def mqtt_alive(self) -> None:
        """The broker was heard from, so the MQTT readings are still current: it sends a topic's
        message only when it changes, and again on every connection when it is retained."""
        with self._lock:
            self._mqtt_alive = self.clock()

    def answer(self) -> Dict[str, Any]:
        """/api/sensors: every listed reading, in the listed order, and the power roles that are set,
        in POWER_ROLES order; each marked missing when too old."""
        now = self.clock()

        def latest(item: Item) -> Dict[str, Any]:
            value = self._readings.get(item.id)
            read_at = self._read_at.get(item.id, 0)
            if item.mqtt:
                # Kept while the broker is there, however long ago the topic last changed
                read_at = max(read_at, self._mqtt_alive or 0)
            if value is None or now - read_at > KEEP_SECONDS:
                return missing_reading(item)
            return dict(value)

        with self._lock:
            sensors = [latest(item) for item in self.items]
            power = [latest(item) for item in self.power]
            updated = self._updated
        return {
            "sensors": sensors,
            "power": power,
            "updated_at": (datetime.fromtimestamp(updated, timezone.utc).isoformat().replace("+00:00", "Z")
                           if updated is not None else None),
            "interval_seconds": self.interval,
        }

    def run(self, stop: Optional[threading.Event] = None) -> None:
        """Starts the MQTT client, if there are MQTT readings, and reads Home Assistant every
        `interval` seconds, until `stop` is set; one bad round never stops it."""
        stop = stop or threading.Event()
        if self.mqtt is not None and self.mqtt_items:
            client = self.mqtt_client(
                self.mqtt.host, self.mqtt.port, [item.topic for item in self.mqtt_items], self.mqtt_message,
                username=self.mqtt.username, password=self.mqtt.password, tls=self.mqtt.tls,
                on_alive=self.mqtt_alive)
            threading.Thread(target=client.run, args=(stop,), name="mqtt", daemon=True).start()
        if self.url is None or not self.home_assistant_items:
            stop.wait()
            return
        while not stop.is_set():
            started = self.clock()
            try:
                self.poll_once()
            except Exception as error:  # keep reading whatever goes wrong
                _say(f"Sensors: reading failed ({type(error).__name__})")
            stop.wait(max(1.0, self.interval - (self.clock() - started)))

    def describe(self) -> str:
        """For the startup log: how many readings and from where, never a token or a value."""
        if not self.items and not self.power:
            return "sensors off (OUTPOST_SENSORS and OUTPOST_POWER_* are empty)"
        sources, off = [], []
        if self.home_assistant_items:
            if self.url is None:
                off.append(self.where)
            else:
                sources.append(f"{self.where}, every {self.interval} s")
        if self.mqtt_items:
            if self.mqtt is None:
                off.append(f"MQTT readings off: {self.mqtt_where}")
            else:
                sources.append(self.mqtt_where)
        if not sources:
            return f"sensors off: {'; '.join(off)}"
        counts = []
        if self.items:
            counts.append(f"{len(self.items)} sensor reading{'' if len(self.items) == 1 else 's'}")
        if self.power:
            counts.append(f"power ({', '.join(item.role for item in self.power)})")
        text = f"{' and '.join(counts)} from {' and '.join(sources)}"
        return f"{text}; {'; '.join(off)}" if off else text


def from_environment(environ: Optional[Mapping[str, str]] = None) -> Sensors:
    environ = os.environ if environ is None else environ
    items, problems = parse_items(environ.get("OUTPOST_SENSORS"))
    for problem in problems:
        _say(f"OUTPOST_SENSORS: {problem}; skipping it")
    power, problems = parse_power(environ)
    for problem in problems:
        _say(problem)
    listed = items + power
    url, token, where = connection(environ)
    mqtt, mqtt_where = mqtt_connection(environ) if any(item.mqtt for item in listed) else (None, "")
    return Sensors(items, url if any(not item.mqtt for item in listed) else None, token, where,
                   interval_setting(environ.get("OUTPOST_SENSORS_INTERVAL")), power=power,
                   invert_grid=flag(environ.get("OUTPOST_POWER_GRID_INVERT")),
                   mqtt=mqtt, mqtt_where=mqtt_where)
