"""Sensors (app/outpost_sensors.py, docs/sensors-design.md): the list, Home Assistant, and /api/sensors."""

import contextlib
import io
import json
import threading
import unittest
import urllib.error
import urllib.request

import helpers
from helpers import ROOT

import outpost_sensors as o
import outpost_server as s


class Clock:
    def __init__(self):
        self.now = 1_800_000_000.0

    def __call__(self):
        return self.now


def state(value, **attributes):
    return {"entity_id": "sensor.x", "state": value, "attributes": attributes}


class FakeHomeAssistant:
    """Answers GET /api/states/<entity> from a dict; records what was asked and with which token."""

    def __init__(self, states):
        self.states = states
        self.asked = []
        self.down = False

    def __call__(self, url, token):
        self.asked.append((url, token))
        if self.down:
            raise o.SourceError("can't connect (URLError)")
        entity = url.rsplit("/", 1)[-1]
        if entity not in self.states:
            raise o.NotFound("not found")
        return self.states[entity]


def quiet():
    return contextlib.redirect_stderr(io.StringIO())


class ListTests(unittest.TestCase):
    def test_sources_labels_and_units(self):
        items, problems = o.parse_items(
            "sensor.living_room_temperature, Garage=binary_sensor.garage_door,"
            " Attic = sensor.attic_temperature [°F],sensor.power[W]")
        self.assertEqual(problems, [])
        self.assertEqual([(i.id, i.source, i.label, i.unit) for i in items], [
            ("s1", "sensor.living_room_temperature", "", ""),
            ("s2", "binary_sensor.garage_door", "Garage", ""),
            ("s3", "sensor.attic_temperature", "Attic", "°F"),
            ("s4", "sensor.power", "", "W"),
        ])

    def test_empty(self):
        for text in (None, "", " , ,"):
            with self.subTest(text=text):
                self.assertEqual(o.parse_items(text), ([], []))

    def test_bad_items_are_skipped_and_named(self):
        items, problems = o.parse_items("sensor.ok, Living Room, Sensor.Upper, a=b=sensor.x, mqtt:shed/+/temp")
        self.assertEqual([item.source for item in items], ["sensor.ok"])
        self.assertEqual(len(problems), 4)
        self.assertIn("Living Room", problems[0])
        self.assertIn("MQTT", problems[3])

    def test_repeats_are_shown_once(self):
        items, _ = o.parse_items("sensor.a, sensor.a, Other=sensor.a")
        self.assertEqual([(item.source, item.label) for item in items], [("sensor.a", ""), ("sensor.a", "Other")])

    def test_at_most_24(self):
        items, problems = o.parse_items(", ".join(f"sensor.s{n}" for n in range(30)))
        self.assertEqual(len(items), o.MAX_ITEMS)
        self.assertEqual(problems, [f"only the first {o.MAX_ITEMS} readings are shown"])

    def test_labels_and_units_are_one_short_line(self):
        items, _ = o.parse_items(f"{'L' * 60}=sensor.a [{'u' * 20}]")
        self.assertEqual(len(items[0].label), o.MAX_LABEL_LENGTH)
        self.assertEqual(len(items[0].unit), o.MAX_UNIT_LENGTH)

    def test_interval(self):
        with quiet():
            self.assertEqual(o.interval_setting(None), 10)
            self.assertEqual(o.interval_setting("30"), 30)
            self.assertEqual(o.interval_setting("1"), o.MIN_INTERVAL)
            self.assertEqual(o.interval_setting("soon"), 10)
            self.assertEqual(o.interval_setting("999999"), o.MAX_INTERVAL)


class ConnectionTests(unittest.TestCase):
    def test_url_and_token(self):
        self.assertEqual(o.connection({"OUTPOST_HA_URL": "http://ha.example:8123/", "OUTPOST_HA_TOKEN": " abc "}),
                         ("http://ha.example:8123", "abc", "Home Assistant"))
        self.assertEqual(o.connection({"OUTPOST_HA_URL": "https://ha.example/api", "OUTPOST_HA_TOKEN": "abc"})[0],
                         "https://ha.example")

    def test_the_add_on_uses_the_supervisor(self):
        self.assertEqual(o.connection({"SUPERVISOR_TOKEN": "xyz"}),
                         (o.SUPERVISOR_URL, "xyz", "Home Assistant (add-on)"))
        # A URL in the settings wins
        self.assertEqual(o.connection({"SUPERVISOR_TOKEN": "xyz", "OUTPOST_HA_URL": "http://ha.example",
                                       "OUTPOST_HA_TOKEN": "abc"})[1], "abc")

    def test_unusable_settings(self):
        for environ in ({}, {"OUTPOST_HA_URL": "http://ha.example"},
                        {"OUTPOST_HA_URL": "ha.example:8123", "OUTPOST_HA_TOKEN": "abc"},
                        {"OUTPOST_HA_URL": "ftp://ha.example", "OUTPOST_HA_TOKEN": "abc"},
                        {"OUTPOST_HA_URL": "http://user:pw@ha.example", "OUTPOST_HA_TOKEN": "abc"},
                        {"OUTPOST_HA_URL": "http://ha.example", "OUTPOST_HA_TOKEN": "has space"},
                        {"OUTPOST_HA_URL": "http://ha.example", "OUTPOST_HA_TOKEN": "line\nbreak"}):
            with self.subTest(environ=environ):
                url, token, why = o.connection(environ)
                self.assertIsNone(url)
                self.assertEqual(token, "")
                self.assertNotIn("abc", why)

    def test_nothing_listed_is_off(self):
        sensors = o.from_environment({"OUTPOST_HA_URL": "http://ha.example", "OUTPOST_HA_TOKEN": "abc"})
        self.assertFalse(sensors.on)
        self.assertIn("OUTPOST_SENSORS and OUTPOST_POWER_* are empty", sensors.describe())

    def test_listed_without_home_assistant_is_off_and_says_why(self):
        sensors = o.from_environment({"OUTPOST_SENSORS": "sensor.a"})
        self.assertFalse(sensors.on)
        self.assertIn("OUTPOST_HA_URL", sensors.describe())

    def test_the_log_never_has_the_token(self):
        sensors = o.from_environment({"OUTPOST_SENSORS": "sensor.a", "OUTPOST_HA_URL": "http://ha.example",
                                      "OUTPOST_HA_TOKEN": "secret-token"})
        self.assertTrue(sensors.on)
        self.assertEqual(sensors.describe(), "1 sensor reading from Home Assistant, every 10 s")


class ReadingTests(unittest.TestCase):
    def read(self, source, value, label="", unit="", **attributes):
        return o.reading(o.Item(1, source, label, unit), state(value, **attributes))

    def test_numbers(self):
        reading = self.read("sensor.t", "21.53", friendly_name="Living room", unit_of_measurement="°C",
                            device_class="temperature")
        self.assertEqual(reading, {"id": "s1", "label": "Living room", "kind": "number", "value": 21.53,
                                   "text": "21.5", "unit": "°C", "device_class": "temperature", "missing": False})
        self.assertEqual(self.read("sensor.h", "45", unit_of_measurement="%")["text"], "45")
        self.assertEqual(self.read("sensor.h", "45.0")["text"], "45.0")
        self.assertEqual(self.read("sensor.p", "1013.25")["text"], "1013")
        self.assertEqual(self.read("sensor.n", "-0.04")["text"], "0.0")

    def test_power_in_kw_from_1000_w(self):
        self.assertEqual(self.read("sensor.p", "850", unit_of_measurement="W")[("text")], "850")
        reading = self.read("sensor.p", "1234", unit_of_measurement="W")
        self.assertEqual((reading["text"], reading["unit"], reading["value"]), ("1.2", "kW", 1.234))

    def test_the_list_wins_over_home_assistant(self):
        reading = self.read("sensor.t", "70", label="Attic", unit="°F", friendly_name="Attic sensor",
                            unit_of_measurement="°C")
        self.assertEqual((reading["label"], reading["unit"]), ("Attic", "°F"))

    def test_without_a_name_the_entity_is_the_label(self):
        self.assertEqual(self.read("sensor.t", "1")["label"], "sensor.t")

    def test_on_and_off_by_device_class(self):
        for device_class, on, off in (("door", "Open", "Closed"), ("garage_door", "Open", "Closed"),
                                      ("motion", "Detected", "Clear"), ("moisture", "Wet", "Dry"),
                                      ("", "On", "Off"), ("something_new", "On", "Off")):
            with self.subTest(device_class=device_class):
                reading = self.read("binary_sensor.b", "on", device_class=device_class)
                self.assertEqual((reading["kind"], reading["value"], reading["text"]), ("binary", True, on))
                self.assertEqual(self.read("binary_sensor.b", "off", device_class=device_class)["text"], off)

    def test_switches_are_on_or_off(self):
        self.assertEqual(self.read("switch.pump", "on")["text"], "On")
        self.assertEqual(self.read("switch.pump", "on")["kind"], "binary")

    def test_other_text_as_home_assistant_says_it(self):
        reading = self.read("lock.front", "locked")
        self.assertEqual((reading["kind"], reading["text"], reading["missing"]), ("text", "Locked", False))
        self.assertEqual(self.read("person.someone", "not_home")["text"], "Not home")

    def test_missing(self):
        for value in ("unavailable", "unknown", "", None, "nan"):
            with self.subTest(value=value):
                reading = self.read("sensor.t", value, unit_of_measurement="°C")
                self.assertTrue(reading["missing"])
                self.assertIsNone(reading["value"])
                self.assertEqual(reading["text"], "")

    def test_odd_attributes_are_ignored(self):
        reading = o.reading(o.Item(1, "sensor.t"), {"state": "5", "attributes": {
            "friendly_name": "Line\nbreak", "device_class": "Bad Class!", "unit_of_measurement": 7}})
        self.assertEqual((reading["label"], reading["device_class"], reading["unit"]), ("Line break", "", ""))
        self.assertEqual(o.reading(o.Item(1, "sensor.t"), {"state": "5", "attributes": []})["text"], "5")


class SensorsTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.home = FakeHomeAssistant({
            "sensor.t": state("21.5", friendly_name="Living room", unit_of_measurement="°C"),
            "binary_sensor.door": state("off", friendly_name="Front door", device_class="door"),
        })
        items, _ = o.parse_items("sensor.t, binary_sensor.door, sensor.gone")
        self.sensors = o.Sensors(items, "http://ha.example", "secret-token", "Home Assistant",
                                 get=self.home, clock=self.clock)

    def test_reads_each_listed_entity_with_the_token(self):
        with quiet():
            self.sensors.poll_once()
        self.assertEqual(self.home.asked, [
            ("http://ha.example/api/states/sensor.t", "secret-token"),
            ("http://ha.example/api/states/binary_sensor.door", "secret-token"),
            ("http://ha.example/api/states/sensor.gone", "secret-token"),
        ])
        answer = self.sensors.answer()
        self.assertEqual([(r["label"], r["text"], r["missing"]) for r in answer["sensors"]],
                         [("Living room", "21.5", False), ("Front door", "Closed", False), ("sensor.gone", "", True)])
        self.assertEqual(answer["updated_at"], "2027-01-15T08:00:00Z")
        self.assertEqual(answer["interval_seconds"], 10)

    def test_before_the_first_read_everything_is_missing(self):
        answer = self.sensors.answer()
        self.assertEqual([r["missing"] for r in answer["sensors"]], [True, True, True])
        self.assertIsNone(answer["updated_at"])

    def test_an_entity_not_in_home_assistant_is_logged_once(self):
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            self.sensors.poll_once()
            self.sensors.poll_once()
        self.assertEqual(log.getvalue().count("sensor.gone is not in Home Assistant"), 1)

    def test_while_home_assistant_is_down_the_last_readings_stay_for_15_minutes(self):
        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            self.sensors.poll_once()
            self.home.down = True
            self.clock.now += 60
            self.sensors.poll_once()
            self.sensors.poll_once()
            self.assertEqual(self.sensors.answer()["sensors"][0]["text"], "21.5")
            # Skipped the rest of the round after the first failure
            self.assertEqual(len(self.home.asked), 5)
            self.clock.now += o.KEEP_SECONDS
            self.assertTrue(self.sensors.answer()["sensors"][0]["missing"])
            self.home.down = False
            self.sensors.poll_once()
        text = log.getvalue()
        self.assertEqual(text.count("can't connect"), 1)
        self.assertIn("answers again", text)
        self.assertNotIn("secret-token", text)
        self.assertNotIn("21.5", text)
        self.assertFalse(self.sensors.answer()["sensors"][0]["missing"])

    def test_answers_are_copies(self):
        with quiet():
            self.sensors.poll_once()
        self.sensors.answer()["sensors"][0]["text"] = "changed"
        self.assertEqual(self.sensors.answer()["sensors"][0]["text"], "21.5")

    def test_run_keeps_going_after_an_error_and_stops(self):
        stop = threading.Event()
        calls = []

        def broken(url, token):
            calls.append(url)
            if len(calls) >= 2:
                stop.set()
            raise RuntimeError("surprise")

        sensors = o.Sensors(o.parse_items("sensor.t")[0], "http://ha.example", "t", "Home Assistant",
                            interval=o.MIN_INTERVAL, get=broken)
        sensors.interval = 0  # no wait between rounds in the test
        with quiet():
            thread = threading.Thread(target=sensors.run, args=(stop,), daemon=True)
            thread.start()
            thread.join(10)
        self.assertFalse(thread.is_alive())
        self.assertGreaterEqual(len(calls), 2)


class PowerTests(unittest.TestCase):
    def setUp(self):
        self.environ = {
            "OUTPOST_HA_URL": "http://ha.example", "OUTPOST_HA_TOKEN": "secret-token",
            "OUTPOST_POWER_HOME": "sensor.house", "OUTPOST_POWER_SOLAR": "Panels=sensor.pv",
            "OUTPOST_POWER_GRID": "sensor.grid", "OUTPOST_POWER_BATTERY": "sensor.battery",
        }

    def item(self, role, source="sensor.x", label="", unit=""):
        return o.Item(0, source, label, unit, role)

    def test_one_reading_per_role(self):
        items, problems = o.parse_power(self.environ)
        self.assertEqual([(i.role, i.id, i.source, i.label) for i in items], [
            ("home", "p-home", "sensor.house", ""), ("solar", "p-solar", "sensor.pv", "Panels"),
            ("grid", "p-grid", "sensor.grid", ""), ("battery", "p-battery", "sensor.battery", ""),
        ])
        self.assertEqual(problems, [])

    def test_bad_or_extra_readings_are_named(self):
        items, problems = o.parse_power({"OUTPOST_POWER_HOME": "sensor.a, sensor.b",
                                         "OUTPOST_POWER_GRID": "not an entity", "OUTPOST_POWER_SOLAR": " "})
        self.assertEqual([(i.role, i.source) for i in items], [("home", "sensor.a")])
        self.assertTrue(any(p.startswith("OUTPOST_POWER_HOME: one reading per role") for p in problems))
        self.assertTrue(any(p.startswith("OUTPOST_POWER_GRID: ") for p in problems))

    def test_roles_are_labelled_unless_the_setting_gives_a_label(self):
        reading = o.power_reading(self.item("home"), state("640", friendly_name="Shelly 3EM", unit_of_measurement="W"))
        self.assertEqual((reading["role"], reading["label"], reading["text"], reading["unit"]), ("home", "Home", "640", "W"))
        reading = o.power_reading(self.item("solar", label="Roof"), state("2350", unit_of_measurement="W"))
        self.assertEqual((reading["label"], reading["text"], reading["unit"]), ("Roof", "2.4", "kW"))

    def test_grid_direction(self):
        grid = self.item("grid")
        cases = [("1200", False, "import", "1.2", 1.2), ("-800", False, "export", "800", -800),
                 ("0", False, "idle", "0", 0), ("-0.0", False, "idle", "0.0", 0),
                 ("1200", True, "export", "1.2", -1.2), ("-0.3", True, "import", "0.3", 0.3)]
        for raw, invert, direction, text, value in cases:
            with self.subTest(raw=raw, invert=invert):
                unit = "kW" if raw.endswith(".3") else "W"
                reading = o.power_reading(grid, state(raw, unit_of_measurement=unit), invert)
                self.assertEqual((reading["direction"], reading["text"], reading["missing"]), (direction, text, False))
                self.assertAlmostEqual(reading["value"], value)

    def test_battery_charge_as_a_fraction(self):
        battery = self.item("battery")
        reading = o.power_reading(battery, state("85", unit_of_measurement="%", device_class="battery"))
        self.assertEqual((reading["text"], reading["unit"], reading["fraction"]), ("85", "%", 0.85))
        self.assertEqual(o.power_reading(battery, state("62.5"))["unit"], "%")
        self.assertEqual(o.power_reading(battery, state("130", unit_of_measurement="%"))["fraction"], 1.0)
        self.assertNotIn("fraction", o.power_reading(battery, state("13.2", unit_of_measurement="kWh")))

    def test_anything_but_a_number_is_missing(self):
        for role in ("home", "grid", "battery"):
            for raw in ("unavailable", "charging", "on"):
                with self.subTest(role=role, raw=raw):
                    reading = o.power_reading(self.item(role, "binary_sensor.x" if raw == "on" else "sensor.x"),
                                              state(raw))
                    self.assertEqual((reading["kind"], reading["text"], reading["missing"]), ("number", "", True))
                    self.assertIsNone(reading["value"])
                    self.assertEqual("direction" in reading, role == "grid")

    def test_read_with_the_sensors_and_answered_in_role_order(self):
        home = FakeHomeAssistant({
            "sensor.t": state("21.5", unit_of_measurement="°C"),
            "sensor.house": state("640", unit_of_measurement="W"),
            "sensor.grid": state("300", unit_of_measurement="W"),
            "sensor.battery": state("85", unit_of_measurement="%"),
        })
        environ = dict(self.environ, OUTPOST_SENSORS="sensor.t", OUTPOST_POWER_GRID_INVERT="true")
        with quiet():
            sensors = o.from_environment(environ)
        sensors.get = home
        self.assertTrue(sensors.invert_grid)
        before = sensors.answer()["power"]
        self.assertEqual([(r["role"], r["label"], r["missing"]) for r in before], [
            ("home", "Home", True), ("solar", "Panels", True), ("grid", "Grid", True), ("battery", "Battery", True)])
        with quiet():
            sensors.poll_once()
        self.assertEqual([url.rsplit("/", 1)[-1] for url, _ in home.asked],
                         ["sensor.t", "sensor.house", "sensor.pv", "sensor.grid", "sensor.battery"])
        answer = sensors.answer()
        self.assertEqual([r["text"] for r in answer["sensors"]], ["21.5"])
        power = {r["role"]: r for r in answer["power"]}
        self.assertEqual(power["home"]["text"], "640")
        self.assertTrue(power["solar"]["missing"])
        self.assertEqual(power["grid"]["direction"], "export")
        self.assertEqual(power["battery"]["fraction"], 0.85)

    def test_power_alone_turns_the_panels_on(self):
        environ = {k: v for k, v in self.environ.items() if k != "OUTPOST_POWER_SOLAR"}
        with quiet():
            sensors = o.from_environment(environ)
        self.assertTrue(sensors.on)
        self.assertEqual(sensors.items, [])
        self.assertEqual(sensors.describe(), "power (home, grid, battery) from Home Assistant, every 10 s")
        self.assertEqual(sensors.answer()["sensors"], [])
        self.assertFalse(o.Sensors([], "http://ha.example", power=[]).on)
        with quiet():
            both = o.from_environment(dict(self.environ, OUTPOST_SENSORS="sensor.t"))
        self.assertEqual(both.describe(),
                         "1 sensor reading and power (home, solar, grid, battery) from Home Assistant, every 10 s")

    def test_grid_invert_setting(self):
        for value, expected in (("", False), ("false", False), ("true", True), ("1", True), ("nope", False)):
            with self.subTest(value=value):
                self.assertIs(o.flag(value), expected)


class HttpGetTests(unittest.TestCase):
    def test_answers_and_errors(self):
        def opener(code=None, body=b"{}", error=None):
            class Response(io.BytesIO):
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return False

            def urlopen(request, timeout):
                self.request = request
                if error:
                    raise error
                if code:
                    raise urllib.error.HTTPError(request.full_url, code, "x", {}, io.BytesIO(b""))
                return Response(body)
            return urlopen

        from unittest import mock
        with mock.patch.object(urllib.request, "urlopen", opener(body=b'{"state": "1"}')):
            self.assertEqual(o.http_get("http://ha.example/api/states/sensor.t", "tok"), {"state": "1"})
        self.assertEqual(self.request.get_header("Authorization"), "Bearer tok")
        for kwargs, kind, text in (({"code": 404}, o.NotFound, "not found"),
                                   ({"code": 401}, o.SourceError, "the token was refused"),
                                   ({"code": 500}, o.SourceError, "HTTP 500"),
                                   ({"error": urllib.error.URLError("down")}, o.SourceError, "can't connect"),
                                   ({"body": b"not json"}, o.SourceError, "not JSON"),
                                   ({"body": b"[1]"}, o.SourceError, "not a state")):
            with self.subTest(kwargs=kwargs), mock.patch.object(urllib.request, "urlopen", opener(**kwargs)):
                with self.assertRaises(kind) as caught:
                    o.http_get("http://ha.example/api/states/sensor.t", "tok")
                self.assertIn(text, str(caught.exception))


class ApiTests(unittest.TestCase):
    def start(self, sensors):
        server = s.make_server(s.Places(limit=1), port=0, sensors=sensors)
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return f"http://127.0.0.1:{server.server_address[1]}"

    def get(self, url):
        try:
            with urllib.request.urlopen(url, timeout=5) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            return error.code, json.load(error)

    def test_sensors_on(self):
        home = FakeHomeAssistant({"sensor.t": state("3", friendly_name="Shed")})
        sensors = o.Sensors(o.parse_items("sensor.t")[0], "http://ha.example", "t", "Home Assistant", get=home)
        with quiet():
            sensors.poll_once()
        base = self.start(sensors)
        self.assertTrue(self.get(base + "/api/status")[1]["sensors"])
        status, body = self.get(base + "/api/sensors?entity=sensor.secret")
        self.assertEqual(status, 200)
        self.assertEqual([(r["label"], r["text"]) for r in body["sensors"]], [("Shed", "3")])
        # Nothing in the request chooses what is read
        self.assertNotIn("sensor.secret", json.dumps(body))
        self.assertEqual(len(home.asked), 1)

    def test_power_on_its_own(self):
        home = FakeHomeAssistant({"sensor.grid": state("-450", unit_of_measurement="W")})
        sensors = o.Sensors([], "http://ha.example", "t", "Home Assistant", get=home,
                            power=[o.Item(0, "sensor.grid", role="grid")])
        with quiet():
            sensors.poll_once()
        base = self.start(sensors)
        self.assertTrue(self.get(base + "/api/status")[1]["sensors"])
        body = self.get(base + "/api/sensors")[1]
        self.assertEqual(body["sensors"], [])
        self.assertEqual([(r["role"], r["text"], r["direction"]) for r in body["power"]], [("grid", "450", "export")])

    def test_sensors_off(self):
        for sensors in (None, o.Sensors([], None)):
            with self.subTest(sensors=sensors):
                base = self.start(sensors)
                self.assertFalse(self.get(base + "/api/status")[1]["sensors"])
                status, body = self.get(base + "/api/sensors")
                self.assertEqual((status, body["error"]), (404, "sensors_off"))

    def test_the_server_starts_the_readings(self):
        server = (ROOT / "app" / "outpost_server.py").read_text(encoding="utf-8")
        self.assertIn("outpost_sensors.from_environment()", server)
        self.assertIn('target=sensors.run, name="sensors"', server)


class AddonTests(unittest.TestCase):
    def test_the_sensor_list_becomes_one_setting(self):
        import outpost_addon as a
        self.assertEqual(a.settings_from_options({"sensors": [" sensor.a ", "", "Garage=binary_sensor.g", 3]}),
                         {"OUTPOST_SENSORS": "sensor.a, Garage=binary_sensor.g"})
        self.assertEqual(a.settings_from_options({"sensors": []}), {})
        self.assertIn("sensors set", a.options_summary({"sensors": ["sensor.a"]}))

    def test_the_power_roles_are_settings(self):
        import outpost_addon as a
        self.assertEqual(a.settings_from_options({"power_home": " sensor.house ", "power_grid_invert": True,
                                                  "power_solar": ""}),
                         {"OUTPOST_POWER_HOME": "sensor.house", "OUTPOST_POWER_GRID_INVERT": "true"})
        config = json.loads((ROOT / "homeassistant" / "outpost" / "config.json").read_text(encoding="utf-8"))
        for role in ("home", "solar", "grid", "battery"):
            self.assertEqual(config["schema"][f"power_{role}"], "str?")
        self.assertEqual(config["schema"]["power_grid_invert"], "bool")
        self.assertIs(config["options"]["power_grid_invert"], False)

    def test_the_add_on_lists_sensors(self):
        config = json.loads((ROOT / "homeassistant" / "outpost" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["schema"]["sensors"], ["str"])
        self.assertEqual(config["options"]["sensors"], [])
        self.assertTrue(config["homeassistant_api"])


class MqttListTests(unittest.TestCase):
    def test_topics_and_fields(self):
        items, problems = o.parse_items("mqtt:shed/temp, Shed=mqtt:shed/climate#temperature [°F], "
                                        "mqtt:tele/plug/SENSOR#ENERGY.Power, mqtt:$SYS/broker/uptime")
        self.assertEqual(problems, [])
        self.assertEqual([(item.topic, item.field, item.label, item.unit) for item in items], [
            ("shed/temp", (), "", ""),
            ("shed/climate", ("temperature",), "Shed", "°F"),
            ("tele/plug/SENSOR", ("ENERGY", "Power"), "", ""),
            ("$SYS/broker/uptime", (), "", ""),
        ])
        self.assertTrue(items[0].mqtt)
        self.assertEqual(items[0].domain, "mqtt")
        self.assertFalse(o.parse_items("sensor.t")[0][0].mqtt)

    def test_labels_from_the_topic_or_field(self):
        items, _ = o.parse_items("mqtt:shed/temp, mqtt:shed/climate#relative_humidity, mqtt:a/garage-door/")
        self.assertEqual([item.default_label() for item in items], ["Temp", "Relative humidity", "Garage door"])

    def test_wildcards_and_bad_topics_are_skipped(self):
        for text in ("mqtt:", "mqtt:shed/+/temp", "mqtt:shed/#", "mqtt:shed#", "mqtt:shed#a..b",
                     "mqtt:shed#a/b"):
            with self.subTest(text=text):
                items, problems = o.parse_items(text)
                self.assertEqual(items, [])
                self.assertEqual(len(problems), 1)
                self.assertIn("MQTT topic", problems[0])


class MqttReadingTests(unittest.TestCase):
    def read(self, source, payload, unit=""):
        item = o.parse_items(f"{source} [{unit}]" if unit else source)[0][0]
        return o.reading(item, o.mqtt_state(item, payload))

    def test_numbers_text_and_on_off(self):
        self.assertEqual(self.read("mqtt:shed/temp", b" 21.54 ", "°C")["text"], "21.5")
        self.assertEqual(self.read("mqtt:shed/temp", b"21.54")["label"], "Temp")
        for payload, text in ((b"ON", "On"), (b"off", "Off"), (b"true", "On"), (b"false", "Off")):
            with self.subTest(payload=payload):
                value = self.read("mqtt:garage/door", payload)
                self.assertEqual((value["kind"], value["text"]), ("binary", text))
        # 1 and 0 stay numbers, and on/off with a unit is text
        self.assertEqual(self.read("mqtt:count", b"1")["kind"], "number")
        self.assertEqual(self.read("mqtt:mode", b"on", "x")["kind"], "text")
        self.assertEqual(self.read("mqtt:garage/state", b"opening")["text"], "Opening")
        self.assertEqual(self.read("mqtt:garage/state", b'"open"')["text"], "Open")

    def test_json_fields(self):
        message = b'{"temperature": 19.26, "battery": 88, "contact": false, "nested": {"list": [5, "x"]}}'
        self.assertEqual(self.read("mqtt:a#temperature", message)["text"], "19.3")
        self.assertEqual(self.read("mqtt:a#battery", message)["text"], "88")
        self.assertEqual(self.read("mqtt:a#contact", message)["text"], "Off")
        self.assertEqual(self.read("mqtt:a#nested.list.0", message)["text"], "5")
        self.assertEqual(self.read("mqtt:a#nested.list.1", message)["text"], "X")
        for source in ("mqtt:a#gone", "mqtt:a#nested", "mqtt:a#nested.list.9", "mqtt:a#temperature.x"):
            with self.subTest(source=source):
                self.assertTrue(self.read(source, message)["missing"])

    def test_missing(self):
        for payload in (b"", b"unavailable", b"\xff\xfe", b"nan"):
            with self.subTest(payload=payload):
                self.assertTrue(self.read("mqtt:a", payload)["missing"])
        self.assertTrue(self.read("mqtt:a#t", b"not json")["missing"])
        self.assertTrue(self.read("mqtt:a#t", b'{"t": null}')["missing"])


class MqttConnectionTests(unittest.TestCase):
    def test_settings(self):
        mqtt, where = o.mqtt_connection({"OUTPOST_MQTT_HOST": " mqtt.example "})
        self.assertEqual((mqtt.host, mqtt.port, mqtt.username, mqtt.password, mqtt.tls),
                         ("mqtt.example", 1883, "", "", False))
        self.assertEqual(where, "an MQTT broker")
        mqtt, _ = o.mqtt_connection({"OUTPOST_MQTT_HOST": "[fd00::5]", "OUTPOST_MQTT_TLS": "true",
                                     "OUTPOST_MQTT_USERNAME": "outpost", "OUTPOST_MQTT_PASSWORD": "secret-password"})
        self.assertEqual((mqtt.host, mqtt.port, mqtt.username, mqtt.password, mqtt.tls),
                         ("fd00::5", 8883, "outpost", "secret-password", True))
        self.assertNotIn("secret-password", repr(mqtt))
        self.assertEqual(o.mqtt_connection({"OUTPOST_MQTT_HOST": "10.0.0.2", "OUTPOST_MQTT_PORT": "1884"})[0].port, 1884)

    def test_unusable_settings(self):
        for environ, why in (({}, "OUTPOST_MQTT_HOST is not set"),
                             ({"OUTPOST_MQTT_HOST": "mqtt://broker"}, "OUTPOST_MQTT_HOST"),
                             ({"OUTPOST_MQTT_HOST": "broker", "OUTPOST_MQTT_PORT": "x"}, "OUTPOST_MQTT_PORT"),
                             ({"OUTPOST_MQTT_HOST": "broker", "OUTPOST_MQTT_PORT": "70000"}, "OUTPOST_MQTT_PORT"),
                             ({"OUTPOST_MQTT_HOST": "broker", "OUTPOST_MQTT_PASSWORD": "secret-password"},
                              "OUTPOST_MQTT_USERNAME")):
            with self.subTest(environ=environ):
                mqtt, text = o.mqtt_connection(environ)
                self.assertIsNone(mqtt)
                self.assertIn(why, text)
                self.assertNotIn("secret-password", text)

    def test_from_environment(self):
        # MQTT alone: on with a broker, off without one
        sensors = o.from_environment({"OUTPOST_SENSORS": "mqtt:shed/temp", "OUTPOST_MQTT_HOST": "broker",
                                      "OUTPOST_MQTT_USERNAME": "u", "OUTPOST_MQTT_PASSWORD": "secret-password"})
        self.assertTrue(sensors.on)
        self.assertIsNone(sensors.url)
        self.assertEqual(sensors.describe(), "1 sensor reading from an MQTT broker")
        sensors = o.from_environment({"OUTPOST_SENSORS": "mqtt:shed/temp"})
        self.assertFalse(sensors.on)
        self.assertIn("OUTPOST_MQTT_HOST is not set", sensors.describe())
        # Both: Home Assistant still works when the broker isn't set up, and the log says so
        sensors = o.from_environment({"OUTPOST_SENSORS": "sensor.a, mqtt:shed/temp",
                                      "OUTPOST_POWER_SOLAR": "mqtt:solar/power",
                                      "OUTPOST_HA_URL": "http://ha.example", "OUTPOST_HA_TOKEN": "t"})
        self.assertTrue(sensors.on)
        self.assertEqual(sensors.describe(), "2 sensor readings and power (solar) from Home Assistant, every 10 s; "
                                             "MQTT readings off: OUTPOST_MQTT_HOST is not set")
        sensors = o.from_environment({"OUTPOST_SENSORS": "sensor.a", "OUTPOST_POWER_SOLAR": "mqtt:solar/power",
                                      "OUTPOST_HA_URL": "http://ha.example", "OUTPOST_HA_TOKEN": "t",
                                      "OUTPOST_MQTT_HOST": "broker"})
        self.assertEqual(sensors.describe(), "1 sensor reading and power (solar) from Home Assistant, every 10 s "
                                             "and an MQTT broker")
        # No broker settings are read when nothing comes from MQTT
        self.assertIsNone(o.from_environment({"OUTPOST_SENSORS": "sensor.a", "OUTPOST_MQTT_HOST": "broker"}).mqtt)


class FakeClient:
    made = []

    def __init__(self, host, port, topics, on_message, **options):
        self.args = (host, port, topics)
        self.options = options
        self.on_message = on_message
        FakeClient.made.append(self)

    def run(self, stop):
        stop.wait()


class MqttSensorsTests(unittest.TestCase):
    def setUp(self):
        self.clock = Clock()
        self.home = FakeHomeAssistant({"sensor.t": state("21.5", friendly_name="Living room")})
        items, _ = o.parse_items("sensor.t, Shed=mqtt:shed/climate#temperature [°C], mqtt:garage/door")
        power, _ = o.parse_power({"OUTPOST_POWER_GRID": "mqtt:meter/grid", "OUTPOST_POWER_HOME": "sensor.t"})
        self.sensors = o.Sensors(items, "http://ha.example", "t", "Home Assistant", get=self.home,
                                 clock=self.clock, power=power,
                                 mqtt=o.MqttSettings("broker", 1883, "u", "secret-password"),
                                 mqtt_client=FakeClient)

    def test_home_assistant_reads_only_its_own_entities(self):
        with quiet():
            self.sensors.poll_once()
        self.assertEqual([url for url, _ in self.home.asked],
                         ["http://ha.example/api/states/sensor.t", "http://ha.example/api/states/sensor.t"])

    def test_messages_become_readings(self):
        self.sensors.mqtt_message("shed/climate", b'{"temperature": 4.04}')
        self.sensors.mqtt_message("garage/door", b"ON")
        self.sensors.mqtt_message("meter/grid", b"-1500")
        self.sensors.mqtt_message("not/listed", b"1")
        answer = self.sensors.answer()
        self.assertEqual([(r["label"], r["text"], r["unit"], r["missing"]) for r in answer["sensors"]], [
            ("sensor.t", "", "", True), ("Shed", "4.0", "°C", False), ("Door", "On", "", False)])
        grid = answer["power"][1]
        self.assertEqual((grid["role"], grid["label"], grid["text"], grid["unit"], grid["direction"]),
                         ("grid", "Grid", "1500", "", "export"))
        self.assertEqual(answer["updated_at"], "2027-01-15T08:00:00Z")

    def test_kept_while_the_broker_is_there(self):
        self.sensors.mqtt_message("garage/door", b"OFF")
        # The door doesn't change for an hour, but the broker is still there
        for _ in range(4):
            self.clock.now += 15 * 60
            self.sensors.mqtt_alive()
        self.assertFalse(self.sensors.answer()["sensors"][2]["missing"])
        # The broker goes away for 15 minutes
        self.clock.now += o.KEEP_SECONDS + 1
        self.assertTrue(self.sensors.answer()["sensors"][2]["missing"])
        # Never heard from at all is missing, whatever the broker does
        self.assertTrue(self.sensors.answer()["sensors"][1]["missing"])

    def test_run_starts_the_client_with_the_topics(self):
        FakeClient.made = []
        sensors = o.Sensors(o.parse_items("mqtt:a, mqtt:b#x, mqtt:a")[0], None, power=[],
                            mqtt=o.MqttSettings("broker", 1884, "u", "secret-password", True),
                            mqtt_client=FakeClient)
        self.assertTrue(sensors.on)
        stop = threading.Event()
        thread = threading.Thread(target=sensors.run, args=(stop,), daemon=True)
        thread.start()
        for _ in range(100):
            if FakeClient.made:
                break
            thread.join(0.05)
        stop.set()
        thread.join(10)
        self.assertFalse(thread.is_alive())
        client = FakeClient.made[0]
        self.assertEqual(client.args, ("broker", 1884, ["a", "b"]))
        self.assertEqual(client.options["password"], "secret-password")
        self.assertTrue(client.options["tls"])
        self.assertEqual(client.on_message, sensors.mqtt_message)


class MqttAddonTests(unittest.TestCase):
    SERVICE = {"result": "ok", "data": {"host": "core-mosquitto", "port": 1883, "ssl": False,
                                        "username": "addons", "password": "secret-password", "protocol": "3.1.1"}}

    def test_the_service_becomes_settings(self):
        import outpost_addon as a
        self.assertEqual(a.from_mqtt_service(self.SERVICE), {
            "OUTPOST_MQTT_HOST": "core-mosquitto", "OUTPOST_MQTT_PORT": "1883", "OUTPOST_MQTT_TLS": "false",
            "OUTPOST_MQTT_USERNAME": "addons", "OUTPOST_MQTT_PASSWORD": "secret-password"})
        for answer in ({}, {"data": None}, {"data": {"host": ""}}, {"result": "error"}):
            with self.subTest(answer=answer):
                self.assertEqual(a.from_mqtt_service(answer), {})

    def run_addon(self, options, service=True):
        import tempfile
        from pathlib import Path
        import outpost_addon as a
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        folder = Path(folder.name)
        (folder / "options.json").write_text(json.dumps(options), encoding="utf-8")
        asked = []

        def get(url, token):
            asked.append(url)
            if url == a.MQTT_SERVICE_URL:
                if not service:
                    raise urllib.error.HTTPError(url, 400, "no service", {}, None)
                return self.SERVICE
            return {}

        log = io.StringIO()
        with contextlib.redirect_stderr(log):
            a.run(folder / "options.json", folder / "addon.env", folder / "addon.conf",
                  {"SUPERVISOR_TOKEN": "token"}, get)
        return (folder / "addon.env").read_text(encoding="utf-8"), log.getvalue(), asked

    def test_mqtt_readings_use_the_mosquitto_add_on(self):
        import outpost_addon as a
        env, log, asked = self.run_addon({"sensors": ["mqtt:shed/temp"], "mqtt_tls": False})
        self.assertIn("export OUTPOST_MQTT_HOST=core-mosquitto", env)
        self.assertIn("export OUTPOST_MQTT_PASSWORD=secret-password", env)
        self.assertIn(a.MQTT_SERVICE_URL, asked)
        self.assertIn("MQTT broker from Home Assistant's MQTT service", log)
        self.assertNotIn("secret-password", log)

    def test_a_broker_in_the_options_wins(self):
        import outpost_addon as a
        env, _, asked = self.run_addon({"power_grid": "mqtt:meter/grid", "mqtt_host": "broker.example",
                                        "mqtt_port": 8883, "mqtt_tls": True})
        self.assertIn("export OUTPOST_MQTT_HOST=broker.example", env)
        self.assertIn("export OUTPOST_MQTT_TLS=true", env)
        self.assertNotIn("core-mosquitto", env)
        self.assertNotIn(a.MQTT_SERVICE_URL, asked)

    def test_without_mqtt_readings_the_service_is_not_asked(self):
        import outpost_addon as a
        env, _, asked = self.run_addon({"sensors": ["sensor.a"], "mqtt_tls": False})
        self.assertNotIn(a.MQTT_SERVICE_URL, asked)
        self.assertNotIn("OUTPOST_MQTT_HOST", env)

    def test_without_the_service_the_log_says_what_to_do(self):
        env, log, _ = self.run_addon({"sensors": ["mqtt:shed/temp"], "mqtt_tls": False}, service=False)
        self.assertNotIn("OUTPOST_MQTT_HOST", env)
        self.assertIn("install the Mosquitto broker add-on", log)

    def test_the_add_on_asks_for_the_mqtt_service(self):
        config = json.loads((ROOT / "homeassistant" / "outpost" / "config.json").read_text(encoding="utf-8"))
        self.assertEqual(config["services"], ["mqtt:want"])
        self.assertEqual(config["schema"]["mqtt_password"], "password?")
        self.assertEqual(config["schema"]["mqtt_tls"], "bool")
        self.assertIs(config["options"]["mqtt_tls"], False)


if __name__ == "__main__":
    unittest.main()
